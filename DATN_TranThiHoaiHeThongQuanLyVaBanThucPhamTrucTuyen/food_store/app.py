"""
app.py - Ứng dụng Flask chính
================================
Chứa toàn bộ routing cho:
  - Auth (Đăng ký, Đăng nhập, Đăng xuất)
  - Trang chủ, Cửa hàng, Chi tiết sản phẩm
  - Giỏ hàng, Thanh toán, Lịch sử đơn hàng
  - Admin: Dashboard, CRUD Sản phẩm, Quản lý đơn hàng
"""
import os
import json
from datetime import datetime, timedelta, timezone
from collections import defaultdict
from functools import wraps
from flask import (
    Flask, render_template, request, redirect, url_for,
    flash, session, jsonify, abort
)
from flask_login import (
    login_user, logout_user, login_required, current_user
)
from werkzeug.utils import secure_filename
from sqlalchemy import func, extract, cast, Date, inspect, text

from config import Config
from extensions import db, login_manager
from models import User, Category, Product, Order, OrderItem
from recommendation import build_recommender, get_recommendations_for_user
from vnpay import build_payment_url, verify_response


# ==========================================================
# FACTORY FUNCTION: Tạo Flask App
# ==========================================================
def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Khởi tạo extensions
    db.init_app(app)
    login_manager.init_app(app)

    # Tạo thư mục uploads nếu chưa có
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

    return app


app = create_app()

# Biến global cho recommender (cache)
_recommender = None


def get_recommender():
    """Lấy hoặc khởi tạo recommender (lazy loading)."""
    global _recommender
    if _recommender is None:
        _recommender = build_recommender(db.session, alpha=app.config['RECOMMENDATION_ALPHA'])
    return _recommender


def refresh_recommender():
    """Làm mới recommender khi có dữ liệu mới."""
    global _recommender
    _recommender = None


# ==========================================================
# FLASK-LOGIN: User Loader
# ==========================================================
@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


# ==========================================================
# DECORATOR: Admin Required
# ==========================================================
def admin_required(f):
    """Decorator kiểm tra quyền Admin."""
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if not current_user.is_admin:
            abort(403)
        return f(*args, **kwargs)
    return decorated_function


# ==========================================================
# HELPER: Upload ảnh
# ==========================================================
def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']


def save_upload(file):
    """Lưu file upload và trả về tên file."""
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        # Thêm timestamp để tránh trùng tên
        import time
        name, ext = os.path.splitext(filename)
        filename = f"{name}_{int(time.time())}{ext}"
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        return filename
    return None


# ==========================================================
# HELPER: VNPAY / ORDER PAYMENT
# ==========================================================
VN_TIMEZONE = timezone(timedelta(hours=7))
_payment_columns_checked = False


def vietnam_now():
    return datetime.now(VN_TIMEZONE).replace(tzinfo=None)


def get_client_ip():
    forwarded_for = request.headers.get('X-Forwarded-For', '')
    if forwarded_for:
        return forwarded_for.split(',')[0].strip()
    return request.remote_addr or '127.0.0.1'


def ensure_order_payment_columns():
    """Bo sung cot moi khi DB cu duoc tao bang db.create_all()."""
    global _payment_columns_checked
    if _payment_columns_checked:
        return

    inspector = inspect(db.engine)
    if not inspector.has_table('orders'):
        _payment_columns_checked = True
        return

    existing_columns = {col['name'] for col in inspector.get_columns('orders')}
    column_definitions = {
        'payment_method': "VARCHAR(20) NOT NULL DEFAULT 'cod'",
        'payment_status': "VARCHAR(30) NOT NULL DEFAULT 'unpaid'",
        'payment_message': "VARCHAR(255) NULL",
        'paid_at': "DATETIME NULL",
        'vnpay_txn_ref': "VARCHAR(100) NULL",
        'vnpay_transaction_no': "VARCHAR(100) NULL",
        'vnpay_bank_code': "VARCHAR(50) NULL",
        'vnpay_response_code': "VARCHAR(10) NULL",
        'vnpay_transaction_status': "VARCHAR(10) NULL",
    }

    for column_name, definition in column_definitions.items():
        if column_name not in existing_columns:
            db.session.execute(text(f"ALTER TABLE orders ADD COLUMN {column_name} {definition}"))
    db.session.commit()
    _payment_columns_checked = True


@app.before_request
def before_request():
    ensure_order_payment_columns()


def get_vnpay_return_url():
    return url_for('vnpay_return', _external=True)


def get_vnpay_ipn_url():
    return url_for('vnpay_ipn', _external=True)


def is_vnpay_configured():
    return bool(app.config['VNPAY_TMN_CODE'] and app.config['VNPAY_HASH_SECRET'])


def create_mock_vnpay_txn_ref(order):
    created_at = vietnam_now()
    txn_ref = f"MOCK{order.id}{created_at.strftime('%Y%m%d%H%M%S')}"
    order.vnpay_txn_ref = txn_ref
    return txn_ref


def create_vnpay_url(order, bank_code=None):
    if not is_vnpay_configured():
        raise ValueError('VNPAY_TMN_CODE và VNPAY_HASH_SECRET chưa được cấu hình.')

    created_at = vietnam_now()
    expire_at = created_at + timedelta(minutes=app.config['VNPAY_EXPIRE_MINUTES'])
    txn_ref = f"FM{order.id}{created_at.strftime('%Y%m%d%H%M%S')}"
    order.vnpay_txn_ref = txn_ref

    params = {
        'vnp_Version': '2.1.0',
        'vnp_Command': 'pay',
        'vnp_TmnCode': app.config['VNPAY_TMN_CODE'],
        'vnp_Amount': int(float(order.total_amount) * 100),
        'vnp_CurrCode': 'VND',
        'vnp_TxnRef': txn_ref,
        'vnp_OrderInfo': f'Thanh toan don hang FreshMart {order.id}',
        'vnp_OrderType': app.config['VNPAY_ORDER_TYPE'],
        'vnp_Locale': app.config['VNPAY_LOCALE'],
        'vnp_ReturnUrl': get_vnpay_return_url(),
        'vnp_IpAddr': get_client_ip(),
        'vnp_CreateDate': created_at.strftime('%Y%m%d%H%M%S'),
        'vnp_ExpireDate': expire_at.strftime('%Y%m%d%H%M%S'),
    }
    if bank_code:
        params['vnp_BankCode'] = bank_code

    return build_payment_url(
        app.config['VNPAY_PAYMENT_URL'],
        params,
        app.config['VNPAY_HASH_SECRET']
    )


def restore_order_stock(order):
    for item in order.items:
        if item.product:
            item.product.stock += item.quantity
            item.product.total_sold = max(0, item.product.total_sold - item.quantity)


def apply_vnpay_result(order, params):
    response_code = params.get('vnp_ResponseCode')
    transaction_status = params.get('vnp_TransactionStatus')

    order.vnpay_transaction_no = params.get('vnp_TransactionNo')
    order.vnpay_bank_code = params.get('vnp_BankCode')
    order.vnpay_response_code = response_code
    order.vnpay_transaction_status = transaction_status

    if response_code == '00' and transaction_status == '00':
        order.payment_status = 'paid'
        order.payment_message = 'VNPAY thanh toán thành công'
        order.status = 'confirmed'
        order.paid_at = vietnam_now()
    else:
        if order.payment_status == 'pending':
            restore_order_stock(order)
        order.payment_status = 'failed'
        order.payment_message = f'VNPAY lỗi {response_code or transaction_status or "unknown"}'
        order.status = 'cancelled'
    refresh_recommender()


# ==========================================================
# CONTEXT PROCESSOR: Truyền biến chung cho mọi template
# ==========================================================
@app.context_processor
def inject_globals():
    """Inject categories và cart count vào tất cả template."""
    categories = Category.query.all()
    cart = session.get('cart', {})
    cart_count = sum(item['quantity'] for item in cart.values())
    return dict(
        all_categories=categories,
        cart_count=cart_count
    )


# ==========================================================
# ROUTE: AUTH (Đăng ký / Đăng nhập / Đăng xuất)
# ==========================================================

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('home'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        full_name = request.form.get('full_name', '').strip()
        phone = request.form.get('phone', '').strip()

        # Validate
        errors = []
        if not username or len(username) < 3:
            errors.append('Tên đăng nhập phải từ 3 ký tự trở lên.')
        if not email or '@' not in email:
            errors.append('Email không hợp lệ.')
        if len(password) < 6:
            errors.append('Mật khẩu phải từ 6 ký tự trở lên.')
        if password != confirm_password:
            errors.append('Mật khẩu xác nhận không khớp.')
        if User.query.filter_by(username=username).first():
            errors.append('Tên đăng nhập đã tồn tại.')
        if User.query.filter_by(email=email).first():
            errors.append('Email đã được sử dụng.')

        if errors:
            for e in errors:
                flash(e, 'danger')
            return render_template('register.html')

        # Tạo user mới
        user = User(
            username=username, email=email,
            full_name=full_name, phone=phone, role='user'
        )
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        flash('Đăng ký thành công! Vui lòng đăng nhập.', 'success')
        return redirect(url_for('login'))

    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('home'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password):
            login_user(user)
            flash(f'Chào mừng {user.full_name or user.username}!', 'success')
            next_page = request.args.get('next')
            if next_page:
                return redirect(next_page)
            if user.is_admin:
                return redirect(url_for('admin_dashboard'))
            return redirect(url_for('home'))
        else:
            flash('Sai tên đăng nhập hoặc mật khẩu.', 'danger')

    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    session.pop('cart', None)  # Xóa giỏ hàng khi logout
    flash('Đã đăng xuất thành công.', 'success')
    return redirect(url_for('home'))


# ==========================================================
# ROUTE: TRANG CHỦ (HOME)
# ==========================================================

@app.route('/')
def home():
    # Lấy danh mục
    categories = Category.query.all()

    # Sản phẩm mới nhất
    new_products = Product.query.filter_by(is_active=True).order_by(
        Product.created_at.desc()
    ).limit(8).all()

    # Sản phẩm bán chạy
    trending_products = Product.query.filter_by(is_active=True).order_by(
        Product.total_sold.desc()
    ).limit(8).all()

    # Sản phẩm gợi ý (Recommendation System)
    recommended_products = []
    try:
        recommender = get_recommender()
        user_id = current_user.id if current_user.is_authenticated else None
        rec_ids = get_recommendations_for_user(
            recommender, user_id, db.session,
            top_n=app.config['RECOMMENDATION_TOP_N']
        )
        if rec_ids:
            recommended_products = Product.query.filter(
                Product.id.in_(rec_ids),
                Product.is_active == True
            ).all()
            # Sắp xếp theo thứ tự gợi ý
            id_order = {pid: idx for idx, pid in enumerate(rec_ids)}
            recommended_products.sort(key=lambda p: id_order.get(p.id, 999))
    except Exception:
        # Fallback: trending nếu recommendation lỗi
        recommended_products = trending_products

    return render_template('home.html',
                           categories=categories,
                           new_products=new_products,
                           trending_products=trending_products,
                           recommended_products=recommended_products)


# ==========================================================
# ROUTE: CỬA HÀNG (SHOP)
# ==========================================================

@app.route('/shop')
def shop():
    page = request.args.get('page', 1, type=int)
    per_page = 12
    search = request.args.get('q', '').strip()
    category_id = request.args.get('category', type=int)
    sort = request.args.get('sort', 'newest')

    query = Product.query.filter_by(is_active=True)

    # Tìm kiếm theo tên
    if search:
        query = query.filter(Product.name.ilike(f'%{search}%'))

    # Lọc theo danh mục
    if category_id:
        query = query.filter_by(category_id=category_id)

    # Sắp xếp
    if sort == 'price_asc':
        query = query.order_by(Product.price.asc())
    elif sort == 'price_desc':
        query = query.order_by(Product.price.desc())
    elif sort == 'bestseller':
        query = query.order_by(Product.total_sold.desc())
    else:  # newest
        query = query.order_by(Product.created_at.desc())

    products = query.paginate(page=page, per_page=per_page, error_out=False)

    # Gợi ý sản phẩm cho user (hiển thị sidebar)
    recommended_products = []
    try:
        recommender = get_recommender()
        user_id = current_user.id if current_user.is_authenticated else None
        rec_ids = get_recommendations_for_user(recommender, user_id, db.session, top_n=4)
        if rec_ids:
            recommended_products = Product.query.filter(
                Product.id.in_(rec_ids), Product.is_active == True
            ).all()
            id_order = {pid: idx for idx, pid in enumerate(rec_ids)}
            recommended_products.sort(key=lambda p: id_order.get(p.id, 999))
    except Exception:
        pass

    return render_template('shop.html',
                           products=products,
                           search=search,
                           category_id=category_id,
                           sort=sort,
                           recommended_products=recommended_products)


# ==========================================================
# ROUTE: CHI TIẾT SẢN PHẨM
# ==========================================================

@app.route('/product/<int:product_id>')
def product_detail(product_id):
    product = Product.query.get_or_404(product_id)

    # Sản phẩm tương tự (Content-based)
    similar_products = []
    try:
        recommender = get_recommender()
        similar = recommender.get_similar_products(product_id, top_n=4)
        if similar:
            similar_ids = [pid for pid, score in similar]
            similar_products = Product.query.filter(
                Product.id.in_(similar_ids),
                Product.is_active == True
            ).all()
    except Exception:
        # Fallback: cùng danh mục
        similar_products = Product.query.filter(
            Product.category_id == product.category_id,
            Product.id != product.id,
            Product.is_active == True
        ).limit(4).all()

    return render_template('product_detail.html',
                           product=product,
                           similar_products=similar_products)


# ==========================================================
# ROUTE: TRANG GỢI Ý SẢN PHẨM (RECOMMENDATION PAGE)
# ==========================================================

@app.route('/recommendations')
def recommendations_page():
    """Trang hiển thị chi tiết hệ thống gợi ý sản phẩm."""
    user_id = current_user.id if current_user.is_authenticated else None

    # 1. Gợi ý Hybrid cho user
    hybrid_products = []
    hybrid_scores = []
    try:
        recommender = get_recommender()
        if user_id:
            from models import OrderItem as OI
            purchased = db.session.query(OI.product_id).join(
                Order, OI.order_id == Order.id
            ).filter(Order.user_id == user_id).distinct().all()
            purchased_ids = [p[0] for p in purchased]
            hybrid_raw = recommender.get_hybrid_recommendations(
                user_id=user_id, purchased_product_ids=purchased_ids, top_n=8
            )
        else:
            hybrid_raw = []

        if hybrid_raw:
            hybrid_ids = [pid for pid, score in hybrid_raw]
            hybrid_score_map = {pid: round(score * 100, 1) for pid, score in hybrid_raw}
            products_map = {p.id: p for p in Product.query.filter(
                Product.id.in_(hybrid_ids), Product.is_active == True
            ).all()}
            for pid in hybrid_ids:
                if pid in products_map:
                    hybrid_products.append(products_map[pid])
                    hybrid_scores.append(hybrid_score_map.get(pid, 0))
    except Exception:
        pass

    # 2. Content-based: Sản phẩm tương tự với SP đã mua gần nhất
    content_products = []
    last_bought_product = None
    try:
        recommender = get_recommender()
        if user_id:
            last_order = Order.query.filter_by(user_id=user_id).order_by(
                Order.created_at.desc()
            ).first()
            if last_order and last_order.items:
                last_item = last_order.items[0]
                last_bought_product = last_item.product
                similar = recommender.get_similar_products(last_item.product_id, top_n=4)
                if similar:
                    sim_ids = [pid for pid, _ in similar]
                    content_products = Product.query.filter(
                        Product.id.in_(sim_ids), Product.is_active == True
                    ).all()
    except Exception:
        pass

    # 3. Top Trending (fallback / bổ sung)
    trending_products = Product.query.filter_by(is_active=True).order_by(
        Product.total_sold.desc()
    ).limit(8).all()

    # 4. Sản phẩm theo danh mục yêu thích
    fav_category_products = []
    fav_category_name = None
    try:
        if user_id:
            fav_cat = db.session.query(
                Category.id, Category.name, func.count(OrderItem.id).label('cnt')
            ).join(Product, OrderItem.product_id == Product.id
            ).join(Category, Product.category_id == Category.id
            ).join(Order, OrderItem.order_id == Order.id
            ).filter(Order.user_id == user_id
            ).group_by(Category.id, Category.name
            ).order_by(func.count(OrderItem.id).desc()
            ).first()
            if fav_cat:
                fav_category_name = fav_cat.name
                fav_category_products = Product.query.filter(
                    Product.category_id == fav_cat.id,
                    Product.is_active == True
                ).order_by(Product.total_sold.desc()).limit(4).all()
    except Exception:
        pass

    return render_template('recommendations.html',
                           hybrid_products=hybrid_products,
                           hybrid_scores=hybrid_scores,
                           content_products=content_products,
                           last_bought_product=last_bought_product,
                           trending_products=trending_products,
                           fav_category_products=fav_category_products,
                           fav_category_name=fav_category_name)


# ==========================================================
# ROUTE: GIỎ HÀNG (CART)
# ==========================================================

@app.route('/cart')
def cart():
    cart_data = session.get('cart', {})
    items = []
    total = 0

    for product_id, item in cart_data.items():
        product = db.session.get(Product, int(product_id))
        if product:
            subtotal = float(product.price) * item['quantity']
            items.append({
                'product': product,
                'quantity': item['quantity'],
                'subtotal': subtotal
            })
            total += subtotal

    # Gợi ý sản phẩm dựa trên giỏ hàng (Content-based: tương tự SP trong giỏ)
    suggested_products = []
    try:
        recommender = get_recommender()
        cart_product_ids = [int(pid) for pid in cart_data.keys()]
        seen_ids = set(cart_product_ids)
        for cpid in cart_product_ids[:3]:  # lấy 3 SP đầu trong giỏ
            similar = recommender.get_similar_products(cpid, top_n=3)
            for pid, score in similar:
                if pid not in seen_ids:
                    seen_ids.add(pid)
                    p = db.session.get(Product, pid)
                    if p and p.is_active:
                        suggested_products.append(p)
                if len(suggested_products) >= 4:
                    break
            if len(suggested_products) >= 4:
                break
    except Exception:
        pass

    return render_template('cart.html', items=items, total=total,
                           suggested_products=suggested_products)


@app.route('/cart/add', methods=['POST'])
def cart_add():
    product_id = request.form.get('product_id', type=int)
    quantity = request.form.get('quantity', 1, type=int)

    if not product_id or quantity < 1:
        flash('Thông tin không hợp lệ.', 'danger')
        return redirect(request.referrer or url_for('shop'))

    product = db.session.get(Product, product_id)
    if not product:
        flash('Sản phẩm không tồn tại.', 'danger')
        return redirect(url_for('shop'))

    cart = session.get('cart', {})
    pid_str = str(product_id)

    if pid_str in cart:
        cart[pid_str]['quantity'] += quantity
    else:
        cart[pid_str] = {'quantity': quantity}

    session['cart'] = cart
    flash(f'Đã thêm "{product.name}" vào giỏ hàng!', 'success')
    return redirect(request.referrer or url_for('shop'))


@app.route('/cart/update', methods=['POST'])
def cart_update():
    product_id = request.form.get('product_id')
    quantity = request.form.get('quantity', type=int)

    cart = session.get('cart', {})
    if product_id in cart:
        if quantity and quantity > 0:
            cart[product_id]['quantity'] = quantity
        else:
            del cart[product_id]
    session['cart'] = cart
    return redirect(url_for('cart'))


@app.route('/cart/remove/<product_id>')
def cart_remove(product_id):
    cart = session.get('cart', {})
    if product_id in cart:
        del cart[product_id]
        session['cart'] = cart
        flash('Đã xóa sản phẩm khỏi giỏ hàng.', 'success')
    return redirect(url_for('cart'))


# ==========================================================
# ROUTE: THANH TOÁN (CHECKOUT)
# ==========================================================

@app.route('/checkout', methods=['GET', 'POST'])
@login_required
def checkout():
    cart_data = session.get('cart', {})
    if not cart_data:
        flash('Giỏ hàng trống!', 'warning')
        return redirect(url_for('cart'))

    if request.method == 'POST':
        shipping_name = request.form.get('shipping_name', '').strip()
        shipping_phone = request.form.get('shipping_phone', '').strip()
        shipping_address = request.form.get('shipping_address', '').strip()
        note = request.form.get('note', '').strip()
        payment_method = request.form.get('payment_method', 'cod')
        vnpay_bank_code = request.form.get('vnpay_bank_code', '').strip()

        if not shipping_name or not shipping_phone or not shipping_address:
            flash('Vui lòng điền đầy đủ thông tin giao hàng.', 'danger')
            return redirect(url_for('checkout'))

        if payment_method not in Order.PAYMENT_METHOD_CHOICES:
            flash('Phương thức thanh toán không hợp lệ.', 'danger')
            return redirect(url_for('checkout'))

        # Tạo đơn hàng
        order = Order(
            user_id=current_user.id,
            status='pending_payment' if payment_method == 'vnpay' else 'pending',
            payment_method=payment_method,
            payment_status='pending' if payment_method == 'vnpay' else 'unpaid',
            shipping_name=shipping_name,
            shipping_phone=shipping_phone,
            shipping_address=shipping_address,
            note=note
        )
        db.session.add(order)
        db.session.flush()

        total = 0
        for product_id, item in cart_data.items():
            product = db.session.get(Product, int(product_id))
            if not product or not product.is_active:
                db.session.rollback()
                flash('Một sản phẩm trong giỏ không còn khả dụng.', 'danger')
                return redirect(url_for('cart'))
            if product.stock < item['quantity']:
                db.session.rollback()
                flash(f'Sản phẩm "{product.name}" không đủ tồn kho.', 'danger')
                return redirect(url_for('cart'))

            order_item = OrderItem(
                order_id=order.id,
                product_id=product.id,
                quantity=item['quantity'],
                price_at_purchase=product.price
            )
            db.session.add(order_item)
            total += float(product.price) * item['quantity']

            # Giam ton kho va tang so luot ban
            product.stock -= item['quantity']
            product.total_sold += item['quantity']

        order.total_amount = total

        if payment_method == 'vnpay':
            if not is_vnpay_configured():
                if not app.config['VNPAY_ALLOW_MOCK']:
                    db.session.rollback()
                    flash('VNPAY chưa được cấu hình. Vui lòng nhập VNPAY_TMN_CODE và VNPAY_HASH_SECRET thật trong config hoặc biến môi trường.', 'danger')
                    return redirect(url_for('checkout'))
                create_mock_vnpay_txn_ref(order)
                payment_url = url_for('vnpay_mock_payment', order_id=order.id)
            else:
                payment_url = create_vnpay_url(order, vnpay_bank_code)
            db.session.commit()
            session.pop('cart', None)
            refresh_recommender()
            flash(f'Đơn hàng #{order.id} đã được tạo. Vui lòng hoàn tất thanh toán VNPAY.', 'info')
            return redirect(payment_url)

        db.session.commit()

        # Xóa giỏ hàng và làm mới recommender
        session.pop('cart', None)
        refresh_recommender()

        flash(f'Đặt hàng thành công! Mã đơn: #{order.id}', 'success')
        return redirect(url_for('order_history'))

    # GET: Hiển thị form checkout
    items = []
    total = 0
    for product_id, item in cart_data.items():
        product = db.session.get(Product, int(product_id))
        if product:
            subtotal = float(product.price) * item['quantity']
            items.append({
                'product': product,
                'quantity': item['quantity'],
                'subtotal': subtotal
            })
            total += subtotal

    return render_template('checkout.html', items=items, total=total)


# ==========================================================
# ROUTE: VNPAY RETURN / IPN
# ==========================================================

@app.route(app.config['VNPAY_RETURN_PATH'])
def vnpay_return():
    params = request.args.to_dict()
    if not params:
        flash('Không nhận được dữ liệu phản hồi từ VNPAY.', 'danger')
        return redirect(url_for('order_history') if current_user.is_authenticated else url_for('home'))

    if not verify_response(params, app.config['VNPAY_HASH_SECRET']):
        flash('Chữ ký phản hồi VNPAY không hợp lệ.', 'danger')
        return redirect(url_for('order_history') if current_user.is_authenticated else url_for('home'))

    order = Order.query.filter_by(vnpay_txn_ref=params.get('vnp_TxnRef')).first()
    if not order:
        flash('Không tìm thấy đơn hàng tương ứng với giao dịch VNPAY.', 'danger')
        return redirect(url_for('order_history') if current_user.is_authenticated else url_for('home'))

    expected_amount = int(float(order.total_amount) * 100)
    returned_amount = int(params.get('vnp_Amount', 0))
    if returned_amount != expected_amount:
        flash('Số tiền phản hồi từ VNPAY không khớp với đơn hàng.', 'danger')
        return redirect(url_for('order_history') if current_user.is_authenticated else url_for('home'))

    if order.payment_status == 'pending':
        apply_vnpay_result(order, params)
        db.session.commit()

    if order.payment_status == 'paid':
        flash(f'Thanh toán VNPAY thành công cho đơn hàng #{order.id}.', 'success')
    else:
        flash(f'Thanh toán VNPAY chưa thành công cho đơn hàng #{order.id}.', 'warning')

    return redirect(url_for('order_history') if current_user.is_authenticated else url_for('home'))


@app.route(app.config['VNPAY_IPN_PATH'])
def vnpay_ipn():
    params = request.args.to_dict()
    if not params:
        return jsonify({'RspCode': '99', 'Message': 'Input data required'})

    if not verify_response(params, app.config['VNPAY_HASH_SECRET']):
        return jsonify({'RspCode': '97', 'Message': 'Invalid signature'})

    order = Order.query.filter_by(vnpay_txn_ref=params.get('vnp_TxnRef')).first()
    if not order:
        return jsonify({'RspCode': '01', 'Message': 'Order not found'})

    expected_amount = int(float(order.total_amount) * 100)
    returned_amount = int(params.get('vnp_Amount', 0))
    if returned_amount != expected_amount:
        return jsonify({'RspCode': '04', 'Message': 'Invalid amount'})

    if order.payment_status != 'pending':
        return jsonify({'RspCode': '02', 'Message': 'Order already confirmed'})

    try:
        apply_vnpay_result(order, params)
        db.session.commit()
        return jsonify({'RspCode': '00', 'Message': 'Confirm Success'})
    except Exception:
        db.session.rollback()
        return jsonify({'RspCode': '99', 'Message': 'Unknown error'})


@app.route('/payment/vnpay/mock/<int:order_id>', methods=['GET', 'POST'])
@login_required
def vnpay_mock_payment(order_id):
    order = Order.query.get_or_404(order_id)
    if order.user_id != current_user.id and not current_user.is_admin:
        abort(403)

    if order.payment_method != 'vnpay':
        flash('Đơn hàng này không dùng phương thức VNPAY.', 'warning')
        return redirect(url_for('order_history'))

    if request.method == 'POST':
        action = request.form.get('action')
        response_code = '00' if action == 'success' else '24'
        params = {
            'vnp_TxnRef': order.vnpay_txn_ref or create_mock_vnpay_txn_ref(order),
            'vnp_Amount': int(float(order.total_amount) * 100),
            'vnp_ResponseCode': response_code,
            'vnp_TransactionStatus': response_code,
            'vnp_TransactionNo': f"MOCK{order.id}{vietnam_now().strftime('%H%M%S')}",
            'vnp_BankCode': 'NCB',
        }

        if order.payment_status == 'pending':
            apply_vnpay_result(order, params)
            db.session.commit()

        if order.payment_status == 'paid':
            flash(f'Thanh toán VNPAY demo thành công cho đơn hàng #{order.id}.', 'success')
        else:
            flash(f'Thanh toán VNPAY demo thất bại cho đơn hàng #{order.id}.', 'warning')
        return redirect(url_for('order_history'))

    return render_template('vnpay_mock.html', order=order)


# ==========================================================
# ROUTE: LỊCH SỬ ĐƠN HÀNG
# ==========================================================

@app.route('/orders')
@login_required
def order_history():
    orders = Order.query.filter_by(user_id=current_user.id).order_by(
        Order.created_at.desc()
    ).all()
    return render_template('order_history.html', orders=orders)


# ==========================================================
# ROUTE: ADMIN - DASHBOARD
# ==========================================================

@app.route('/admin')
@admin_required
def admin_dashboard():
    total_products = Product.query.count()
    total_users = User.query.filter_by(role='user').count()
    total_orders = Order.query.count()
    total_revenue = db.session.query(
        func.coalesce(func.sum(Order.total_amount), 0)
    ).filter(Order.status == 'completed').scalar()

    # Đơn hàng gần đây
    recent_orders = Order.query.order_by(Order.created_at.desc()).limit(5).all()

    # Sản phẩm bán chạy
    top_products = Product.query.order_by(Product.total_sold.desc()).limit(5).all()

    # ==========================================================
    # DỮ LIỆU CHO 10 CHARTS
    # ==========================================================

    # CHART 1: Doanh thu theo ngày (7 ngày gần nhất) - Line Chart
    today = datetime.utcnow().date()
    revenue_daily = {}
    for i in range(6, -1, -1):
        d = today - timedelta(days=i)
        revenue_daily[d.strftime('%d/%m')] = 0
    daily_data = db.session.query(
        cast(Order.created_at, Date).label('day'),
        func.sum(Order.total_amount)
    ).filter(
        Order.created_at >= today - timedelta(days=6),
        Order.status != 'cancelled'
    ).group_by('day').all()
    for day, amount in daily_data:
        key = day.strftime('%d/%m') if hasattr(day, 'strftime') else str(day)
        if key in revenue_daily:
            revenue_daily[key] = float(amount or 0)
    chart_revenue_labels = json.dumps(list(revenue_daily.keys()))
    chart_revenue_data = json.dumps(list(revenue_daily.values()))

    # CHART 2: Đơn hàng theo trạng thái - Doughnut Chart
    status_counts = db.session.query(
        Order.status, func.count(Order.id)
    ).group_by(Order.status).all()
    status_map = {'pending_payment': 'Chờ thanh toán', 'pending': 'Chờ xử lý',
                  'confirmed': 'Đã xác nhận', 'shipping': 'Đang giao',
                  'completed': 'Hoàn thành', 'cancelled': 'Đã hủy'}
    chart_status_labels = json.dumps([status_map.get(s, s) for s, _ in status_counts])
    chart_status_data = json.dumps([c for _, c in status_counts])

    # CHART 3: Sản phẩm theo danh mục - Bar Chart
    cat_product_counts = db.session.query(
        Category.name, func.count(Product.id)
    ).join(Product, Category.id == Product.category_id).group_by(Category.name).all()
    chart_cat_labels = json.dumps([name for name, _ in cat_product_counts])
    chart_cat_data = json.dumps([count for _, count in cat_product_counts])

    # CHART 4: Top 10 sản phẩm bán chạy - Horizontal Bar Chart
    top10 = Product.query.order_by(Product.total_sold.desc()).limit(10).all()
    chart_top10_labels = json.dumps([p.name[:20] for p in top10])
    chart_top10_data = json.dumps([p.total_sold for p in top10])

    # CHART 5: Doanh thu theo danh mục - Pie Chart
    rev_by_cat = db.session.query(
        Category.name, func.sum(OrderItem.quantity * OrderItem.price_at_purchase)
    ).join(Product, OrderItem.product_id == Product.id
    ).join(Category, Product.category_id == Category.id
    ).join(Order, OrderItem.order_id == Order.id
    ).filter(Order.status != 'cancelled'
    ).group_by(Category.name).all()
    chart_rev_cat_labels = json.dumps([name for name, _ in rev_by_cat])
    chart_rev_cat_data = json.dumps([float(amt or 0) for _, amt in rev_by_cat])

    # CHART 6: Số đơn hàng theo ngày (7 ngày) - Bar Chart
    orders_daily = {}
    for i in range(6, -1, -1):
        d = today - timedelta(days=i)
        orders_daily[d.strftime('%d/%m')] = 0
    daily_orders = db.session.query(
        cast(Order.created_at, Date).label('day'),
        func.count(Order.id)
    ).filter(
        Order.created_at >= today - timedelta(days=6)
    ).group_by('day').all()
    for day, count in daily_orders:
        key = day.strftime('%d/%m') if hasattr(day, 'strftime') else str(day)
        if key in orders_daily:
            orders_daily[key] = count
    chart_orders_daily_labels = json.dumps(list(orders_daily.keys()))
    chart_orders_daily_data = json.dumps(list(orders_daily.values()))

    # CHART 7: Tồn kho theo danh mục - Stacked Bar
    stock_by_cat = db.session.query(
        Category.name,
        func.sum(Product.stock).label('stock'),
        func.sum(Product.total_sold).label('sold')
    ).join(Product, Category.id == Product.category_id
    ).group_by(Category.name).all()
    chart_stock_labels = json.dumps([name for name, _, _ in stock_by_cat])
    chart_stock_in = json.dumps([int(s or 0) for _, s, _ in stock_by_cat])
    chart_stock_sold = json.dumps([int(s or 0) for _, _, s in stock_by_cat])

    # CHART 8: Giá trung bình sản phẩm theo danh mục - Bar Chart
    avg_price_cat = db.session.query(
        Category.name, func.avg(Product.price)
    ).join(Product, Category.id == Product.category_id
    ).group_by(Category.name).all()
    chart_avg_price_labels = json.dumps([name for name, _ in avg_price_cat])
    chart_avg_price_data = json.dumps([round(float(p or 0), 0) for _, p in avg_price_cat])

    # CHART 9: Top 5 khách hàng chi tiêu nhiều nhất - Bar Chart
    top_customers = db.session.query(
        User.full_name, func.sum(Order.total_amount)
    ).join(Order, User.id == Order.user_id
    ).filter(Order.status != 'cancelled'
    ).group_by(User.id, User.full_name
    ).order_by(func.sum(Order.total_amount).desc()
    ).limit(5).all()
    chart_cust_labels = json.dumps([name or 'N/A' for name, _ in top_customers])
    chart_cust_data = json.dumps([float(amt or 0) for _, amt in top_customers])

    # CHART 10: Đăng ký user theo tháng (6 tháng gần nhất) - Area/Line Chart
    user_monthly = {}
    for i in range(5, -1, -1):
        d = today.replace(day=1) - timedelta(days=i * 30)
        key = d.strftime('%m/%Y')
        user_monthly[key] = 0
    monthly_reg = db.session.query(
        extract('month', User.created_at).label('m'),
        extract('year', User.created_at).label('y'),
        func.count(User.id)
    ).filter(User.role == 'user'
    ).group_by('y', 'm').all()
    for m, y, count in monthly_reg:
        key = f'{int(m):02d}/{int(y)}'
        if key in user_monthly:
            user_monthly[key] = count
    chart_user_labels = json.dumps(list(user_monthly.keys()))
    chart_user_data = json.dumps(list(user_monthly.values()))

    return render_template('admin/dashboard.html',
                           total_products=total_products,
                           total_users=total_users,
                           total_orders=total_orders,
                           total_revenue=total_revenue,
                           recent_orders=recent_orders,
                           top_products=top_products,
                           # Chart data
                           chart_revenue_labels=chart_revenue_labels,
                           chart_revenue_data=chart_revenue_data,
                           chart_status_labels=chart_status_labels,
                           chart_status_data=chart_status_data,
                           chart_cat_labels=chart_cat_labels,
                           chart_cat_data=chart_cat_data,
                           chart_top10_labels=chart_top10_labels,
                           chart_top10_data=chart_top10_data,
                           chart_rev_cat_labels=chart_rev_cat_labels,
                           chart_rev_cat_data=chart_rev_cat_data,
                           chart_orders_daily_labels=chart_orders_daily_labels,
                           chart_orders_daily_data=chart_orders_daily_data,
                           chart_stock_labels=chart_stock_labels,
                           chart_stock_in=chart_stock_in,
                           chart_stock_sold=chart_stock_sold,
                           chart_avg_price_labels=chart_avg_price_labels,
                           chart_avg_price_data=chart_avg_price_data,
                           chart_cust_labels=chart_cust_labels,
                           chart_cust_data=chart_cust_data,
                           chart_user_labels=chart_user_labels,
                           chart_user_data=chart_user_data)


# ==========================================================
# ROUTE: ADMIN - QUẢN LÝ SẢN PHẨM (CRUD)
# ==========================================================

@app.route('/admin/products')
@admin_required
def admin_products():
    page = request.args.get('page', 1, type=int)
    products = Product.query.order_by(Product.id.desc()).paginate(
        page=page, per_page=15, error_out=False
    )
    return render_template('admin/products.html', products=products)


@app.route('/admin/products/add', methods=['GET', 'POST'])
@admin_required
def admin_product_add():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        description = request.form.get('description', '').strip()
        price = request.form.get('price', type=float)
        unit = request.form.get('unit', 'kg').strip()
        stock = request.form.get('stock', 0, type=int)
        category_id = request.form.get('category_id', type=int)

        if not name or not price or not category_id:
            flash('Vui lòng điền đầy đủ thông tin bắt buộc.', 'danger')
            return redirect(url_for('admin_product_add'))

        # Upload ảnh
        image = 'default_food.png'
        if 'image' in request.files:
            file = request.files['image']
            saved = save_upload(file)
            if saved:
                image = saved

        product = Product(
            name=name, description=description,
            price=price, unit=unit, stock=stock,
            category_id=category_id, image=image
        )
        db.session.add(product)
        db.session.commit()
        refresh_recommender()

        flash(f'Đã thêm sản phẩm "{name}" thành công!', 'success')
        return redirect(url_for('admin_products'))

    categories = Category.query.all()
    return render_template('admin/product_form.html',
                           product=None, categories=categories)


@app.route('/admin/products/edit/<int:product_id>', methods=['GET', 'POST'])
@admin_required
def admin_product_edit(product_id):
    product = Product.query.get_or_404(product_id)

    if request.method == 'POST':
        product.name = request.form.get('name', '').strip()
        product.description = request.form.get('description', '').strip()
        product.price = request.form.get('price', type=float)
        product.unit = request.form.get('unit', 'kg').strip()
        product.stock = request.form.get('stock', 0, type=int)
        product.category_id = request.form.get('category_id', type=int)
        product.is_active = 'is_active' in request.form

        # Upload ảnh mới (nếu có)
        if 'image' in request.files:
            file = request.files['image']
            if file.filename:
                saved = save_upload(file)
                if saved:
                    product.image = saved

        db.session.commit()
        refresh_recommender()

        flash(f'Đã cập nhật sản phẩm "{product.name}"!', 'success')
        return redirect(url_for('admin_products'))

    categories = Category.query.all()
    return render_template('admin/product_form.html',
                           product=product, categories=categories)


@app.route('/admin/products/delete/<int:product_id>', methods=['POST'])
@admin_required
def admin_product_delete(product_id):
    product = Product.query.get_or_404(product_id)
    product.is_active = False  # Soft delete - không xóa hẳn
    db.session.commit()
    refresh_recommender()
    flash(f'Đã ẩn sản phẩm "{product.name}".', 'success')
    return redirect(url_for('admin_products'))


# ==========================================================
# ROUTE: ADMIN - QUẢN LÝ ĐƠN HÀNG
# ==========================================================

@app.route('/admin/orders')
@admin_required
def admin_orders():
    page = request.args.get('page', 1, type=int)
    status_filter = request.args.get('status', '')

    query = Order.query
    if status_filter:
        query = query.filter_by(status=status_filter)

    orders = query.order_by(Order.created_at.desc()).paginate(
        page=page, per_page=15, error_out=False
    )
    return render_template('admin/orders.html',
                           orders=orders, status_filter=status_filter)


@app.route('/admin/orders/<int:order_id>/update', methods=['POST'])
@admin_required
def admin_order_update(order_id):
    order = Order.query.get_or_404(order_id)
    new_status = request.form.get('status')

    if new_status in Order.STATUS_CHOICES:
        order.status = new_status
        db.session.commit()
        flash(f'Đã cập nhật đơn hàng #{order.id} → {order.status_label}', 'success')
    else:
        flash('Trạng thái không hợp lệ.', 'danger')

    return redirect(url_for('admin_orders'))


# ==========================================================
# ERROR HANDLERS
# ==========================================================

@app.errorhandler(404)
def not_found(e):
    return render_template('base.html', error_code=404,
                           error_msg='Trang không tìm thấy'), 404


@app.errorhandler(403)
def forbidden(e):
    return render_template('base.html', error_code=403,
                           error_msg='Bạn không có quyền truy cập'), 403


# ==========================================================
# CHẠY ỨNG DỤNG
# ==========================================================
if __name__ == '__main__':
    with app.app_context():
        db.create_all()  # Tạo bảng nếu chưa có
        ensure_order_payment_columns()
    app.run(debug=True, port=5000)
