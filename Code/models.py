"""
models.py - Định nghĩa Database Models (Flask-SQLAlchemy + Flask-Login)
=======================================================================
Gồm 5 bảng chính:
  1. User         - Người dùng (Admin / Khách hàng)
  2. Category     - Danh mục thực phẩm
  3. Product      - Sản phẩm thực phẩm
  4. Order        - Đơn hàng
  5. OrderItem    - Chi tiết từng sản phẩm trong đơn hàng

Quan hệ (Relationships):
  - User    1 ──── N  Order        (1 user có nhiều đơn hàng)
  - Order   1 ──── N  OrderItem    (1 đơn hàng có nhiều sản phẩm)
  - Product 1 ──── N  OrderItem    (1 sản phẩm nằm trong nhiều đơn)
  - Category 1 ──── N Product      (1 danh mục chứa nhiều sản phẩm)
"""
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from extensions import db


# ============================================================
# 1. MODEL: USER (Người dùng)
# ============================================================
class User(UserMixin, db.Model):
    """
    Bảng users - Lưu thông tin người dùng.
    Kế thừa UserMixin để tích hợp Flask-Login (is_authenticated, get_id,...).
    """
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)

    # Phân quyền: 'user' (mặc định) hoặc 'admin'
    role = db.Column(db.String(20), nullable=False, default='user')

    # Thông tin bổ sung
    full_name = db.Column(db.String(150), nullable=True)
    phone = db.Column(db.String(20), nullable=True)
    address = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationship: 1 User -> N Orders
    orders = db.relationship('Order', backref='user', lazy='dynamic')

    def set_password(self, password):
        """Hash mật khẩu trước khi lưu vào DB (bảo mật)."""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        """So sánh mật khẩu nhập vào với hash đã lưu."""
        return check_password_hash(self.password_hash, password)

    @property
    def is_admin(self):
        """Kiểm tra user có phải Admin không."""
        return self.role == 'admin'

    def __repr__(self):
        return f'<User {self.username} ({self.role})>'


# ============================================================
# 2. MODEL: CATEGORY (Danh mục thực phẩm)
# ============================================================
class Category(db.Model):
    """
    Bảng categories - Phân loại sản phẩm.
    VD: Rau củ, Trái cây, Thịt cá, Đồ uống, Gia vị,...
    """
    __tablename__ = 'categories'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    description = db.Column(db.Text, nullable=True)
    icon = db.Column(db.String(50), nullable=True)  # CSS class cho icon (VD: fa-carrot)

    # Relationship: 1 Category -> N Products
    products = db.relationship('Product', backref='category', lazy='dynamic')

    def __repr__(self):
        return f'<Category {self.name}>'


# ============================================================
# 3. MODEL: PRODUCT (Sản phẩm thực phẩm)
# ============================================================
class Product(db.Model):
    """
    Bảng products - Thông tin chi tiết sản phẩm.
    Được sử dụng bởi cả phần CRUD (Admin) và Recommendation System.
    """
    __tablename__ = 'products'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(200), nullable=False, index=True)
    description = db.Column(db.Text, nullable=True)

    # Giá tiền (đơn vị: VNĐ) - dùng Numeric để tính toán chính xác
    price = db.Column(db.Numeric(12, 2), nullable=False)

    # Đơn vị tính (kg, hộp, chai, gói,...)
    unit = db.Column(db.String(30), nullable=False, default='kg')

    # Số lượng tồn kho
    stock = db.Column(db.Integer, nullable=False, default=0)

    # Đường dẫn ảnh sản phẩm (lưu trong static/uploads/)
    image = db.Column(db.String(300), nullable=True, default='default_food.png')

    # Khóa ngoại liên kết đến Category
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id'), nullable=False)

    # Trạng thái: True = đang bán, False = ẩn
    is_active = db.Column(db.Boolean, default=True)

    # Số lượt mua (dùng cho Top Trending / Cold Start)
    total_sold = db.Column(db.Integer, default=0)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationship: 1 Product -> N OrderItems
    order_items = db.relationship('OrderItem', backref='product', lazy='dynamic')

    @property
    def formatted_price(self):
        """Trả về giá đã format theo VNĐ. VD: 125,000đ"""
        return f"{int(self.price):,}đ".replace(",", ".")

    def __repr__(self):
        return f'<Product {self.name} - {self.formatted_price}>'


# ============================================================
# 4. MODEL: ORDER (Đơn hàng)
# ============================================================
class Order(db.Model):
    """
    Bảng orders - Lưu thông tin đơn hàng.
    Trạng thái đơn: pending -> confirmed -> shipping -> completed / cancelled
    """
    __tablename__ = 'orders'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)

    # Khóa ngoại liên kết đến User
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    # Tổng tiền đơn hàng (tính tại thời điểm đặt)
    total_amount = db.Column(db.Numeric(14, 2), nullable=False, default=0)

    # Trạng thái đơn hàng
    status = db.Column(db.String(30), nullable=False, default='pending')

    # Thông tin giao hàng
    shipping_name = db.Column(db.String(150), nullable=True)
    shipping_phone = db.Column(db.String(20), nullable=True)
    shipping_address = db.Column(db.Text, nullable=True)
    note = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationship: 1 Order -> N OrderItems
    items = db.relationship('OrderItem', backref='order', lazy='joined',
                            cascade='all, delete-orphan')

    # ---- Các trạng thái hợp lệ ----
    STATUS_CHOICES = {
        'pending': 'Chờ xử lý',
        'confirmed': 'Đã xác nhận',
        'shipping': 'Đang giao hàng',
        'completed': 'Hoàn thành',
        'cancelled': 'Đã hủy',
    }

    @property
    def status_label(self):
        """Trả về nhãn tiếng Việt của trạng thái."""
        return self.STATUS_CHOICES.get(self.status, self.status)

    @property
    def formatted_total(self):
        """Trả về tổng tiền đã format."""
        return f"{int(self.total_amount):,}đ".replace(",", ".")

    def __repr__(self):
        return f'<Order #{self.id} - {self.status}>'


# ============================================================
# 5. MODEL: ORDER ITEM (Chi tiết đơn hàng)
# ============================================================
class OrderItem(db.Model):
    """
    Bảng order_items - Lưu từng dòng sản phẩm trong đơn hàng.
    Đây chính là bảng trung gian thể hiện quan hệ N-N giữa Order và Product,
    đồng thời cũng là nguồn dữ liệu chính cho Collaborative Filtering.
    """
    __tablename__ = 'order_items'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)

    # Khóa ngoại
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)

    # Số lượng mua
    quantity = db.Column(db.Integer, nullable=False, default=1)

    # Giá tại thời điểm mua (snapshot - không thay đổi khi sản phẩm điều chỉnh giá)
    price_at_purchase = db.Column(db.Numeric(12, 2), nullable=False)

    @property
    def subtotal(self):
        """Tính thành tiền = số lượng × đơn giá."""
        return self.quantity * self.price_at_purchase

    @property
    def formatted_subtotal(self):
        """Trả về thành tiền đã format."""
        return f"{int(self.subtotal):,}đ".replace(",", ".")

    def __repr__(self):
        return f'<OrderItem: {self.quantity}x Product#{self.product_id}>'
