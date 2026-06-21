"""
seed_data.py - Tạo dữ liệu mẫu cho hệ thống
================================================
Chạy script này sau khi đã tạo database:
    python seed_data.py

Sẽ tạo:
  - 1 Admin account (admin / admin123)
  - 5 User accounts mẫu
  - 8 Danh mục thực phẩm
  - 40+ Sản phẩm thực phẩm
  - Một số đơn hàng mẫu (để Recommendation System có dữ liệu)
"""
import random
from app import create_app
from extensions import db
from models import User, Category, Product, Order, OrderItem

app = create_app()


def seed():
    with app.app_context():
        # Xóa dữ liệu cũ (nếu có) rồi tạo lại bảng
        db.drop_all()
        db.create_all()
        print("✅ Đã tạo lại toàn bộ bảng trong database.")

        # ============================
        # 1. TẠO TÀI KHOẢN
        # ============================
        admin = User(
            username='admin',
            email='admin@foodstore.vn',
            role='admin',
            full_name='Quản Trị Viên',
            phone='0901234567',
            address='123 Nguyễn Huệ, Q.1, TP.HCM'
        )
        admin.set_password('admin123')
        db.session.add(admin)

        users = []
        user_data = [
            ('nguyen_van_a', 'a@email.com', 'Nguyễn Văn A', '0911111111'),
            ('tran_thi_b', 'b@email.com', 'Trần Thị B', '0922222222'),
            ('le_van_c', 'c@email.com', 'Lê Văn C', '0933333333'),
            ('pham_thi_d', 'd@email.com', 'Phạm Thị D', '0944444444'),
            ('hoang_van_e', 'e@email.com', 'Hoàng Văn E', '0955555555'),
        ]
        for uname, email, fname, phone in user_data:
            u = User(
                username=uname, email=email, role='user',
                full_name=fname, phone=phone,
                address=f'{random.randint(1, 200)} Lê Lợi, TP.HCM'
            )
            u.set_password('123456')
            db.session.add(u)
            users.append(u)

        db.session.flush()  # Flush để lấy ID
        print(f"✅ Đã tạo 1 admin + {len(users)} users.")

        # ============================
        # 2. TẠO DANH MỤC
        # ============================
        categories_data = [
            ('Rau củ quả', 'Các loại rau xanh, củ quả tươi ngon', 'fa-leaf'),
            ('Trái cây', 'Trái cây tươi theo mùa', 'fa-apple-whole'),
            ('Thịt tươi', 'Thịt heo, bò, gà tươi sống', 'fa-drumstick-bite'),
            ('Hải sản', 'Cá, tôm, mực, nghêu tươi sống', 'fa-fish'),
            ('Đồ uống', 'Nước ngọt, nước ép, sữa các loại', 'fa-mug-hot'),
            ('Gia vị', 'Nước mắm, dầu ăn, bột nêm', 'fa-pepper-hot'),
            ('Đồ khô & Mì', 'Mì gói, bún khô, phở khô', 'fa-bowl-rice'),
            ('Bánh kẹo', 'Bánh ngọt, kẹo, snack các loại', 'fa-cookie-bite'),
        ]
        categories = []
        for name, desc, icon in categories_data:
            cat = Category(name=name, description=desc, icon=icon)
            db.session.add(cat)
            categories.append(cat)

        db.session.flush()
        print(f"✅ Đã tạo {len(categories)} danh mục.")

        # ============================
        # 3. TẠO SẢN PHẨM
        # ============================
        products_data = [
            # (Tên, Mô tả, Giá, Đơn vị, Tồn kho, category_index, total_sold)
            # ---- Rau củ quả (index 0) ----
            ('Rau muống', 'Rau muống xanh, giòn ngọt tự nhiên, trồng an toàn', 15000, 'bó', 100, 0, 120),
            ('Cà chua', 'Cà chua chín đỏ, ngọt tự nhiên, giàu vitamin C', 25000, 'kg', 80, 0, 95),
            ('Khoai tây', 'Khoai tây Đà Lạt, củ to đều, bở ngon', 30000, 'kg', 60, 0, 70),
            ('Bắp cải', 'Bắp cải xanh tươi, giòn ngọt Đà Lạt', 20000, 'kg', 50, 0, 55),
            ('Hành tây', 'Hành tây tím, vị ngọt nhẹ, thơm đặc trưng', 18000, 'kg', 70, 0, 40),
            # ---- Trái cây (index 1) ----
            ('Chuối già', 'Chuối già Nam Mỹ, quả dài, ngọt dẻo', 28000, 'nải', 90, 1, 110),
            ('Táo Fuji', 'Táo Fuji nhập khẩu, giòn ngọt, nhiều nước', 75000, 'kg', 40, 1, 85),
            ('Cam sành', 'Cam sành Vĩnh Long, nhiều nước, ngọt thanh', 35000, 'kg', 60, 1, 100),
            ('Xoài cát', 'Xoài cát Hòa Lộc, thơm ngọt đặc sản miền Tây', 55000, 'kg', 45, 1, 90),
            ('Dưa hấu', 'Dưa hấu đỏ không hạt, ngọt mát giải khát', 22000, 'kg', 30, 1, 65),
            # ---- Thịt tươi (index 2) ----
            ('Thịt ba chỉ heo', 'Ba chỉ heo tươi, lớp mỡ đều, thích hợp nướng', 120000, 'kg', 50, 2, 130),
            ('Ức gà', 'Ức gà phi lê tươi, ít mỡ, giàu protein', 85000, 'kg', 70, 2, 105),
            ('Thịt bò Úc', 'Thịt bò Úc nhập khẩu, mềm ngọt tự nhiên', 280000, 'kg', 30, 2, 60),
            ('Sườn non heo', 'Sườn non heo tươi, nhiều thịt, ít mỡ', 135000, 'kg', 40, 2, 75),
            ('Thịt đùi gà', 'Đùi gà góc tư tươi ngon, da giòn', 65000, 'kg', 55, 2, 88),
            # ---- Hải sản (index 3) ----
            ('Tôm sú', 'Tôm sú tươi sống, size lớn 20-25 con/kg', 250000, 'kg', 25, 3, 50),
            ('Cá hồi Na Uy', 'Phi lê cá hồi Na Uy tươi, giàu Omega-3', 350000, 'kg', 20, 3, 45),
            ('Mực ống', 'Mực ống tươi, thịt dày, ngọt tự nhiên', 180000, 'kg', 35, 3, 55),
            ('Nghêu lụa', 'Nghêu lụa tươi, đã ngâm sạch cát', 45000, 'kg', 40, 3, 70),
            ('Cá basa', 'Phi lê cá basa tươi, thịt trắng mềm', 65000, 'kg', 50, 3, 80),
            # ---- Đồ uống (index 4) ----
            ('Sữa tươi Vinamilk', 'Sữa tươi tiệt trùng Vinamilk có đường 1L', 32000, 'hộp', 100, 4, 150),
            ('Nước cam ép', 'Nước cam ép nguyên chất TH True Juice 1L', 42000, 'chai', 60, 4, 80),
            ('Trà xanh 0 độ', 'Trà xanh không độ chai 500ml, thanh mát', 10000, 'chai', 200, 4, 200),
            ('Cà phê sữa đá', 'Cà phê sữa đá Highlands lon 235ml', 15000, 'lon', 150, 4, 170),
            ('Nước dừa tươi', 'Nước dừa xiêm đóng chai 500ml', 20000, 'chai', 80, 4, 60),
            # ---- Gia vị (index 5) ----
            ('Nước mắm Phú Quốc', 'Nước mắm nhĩ Phú Quốc 40 độ đạm, chai 500ml', 55000, 'chai', 80, 5, 90),
            ('Dầu ăn Tường An', 'Dầu ăn Tường An cao cấp 1L', 42000, 'chai', 70, 5, 85),
            ('Bột nêm Knorr', 'Bột nêm Knorr từ thịt heo 900g', 45000, 'gói', 90, 5, 110),
            ('Tương ớt Chinsu', 'Tương ớt Chinsu chai 500g, cay vừa', 22000, 'chai', 100, 5, 75),
            ('Hạt nêm Vedan', 'Hạt nêm Vedan vị heo 400g', 28000, 'gói', 85, 5, 65),
            # ---- Đồ khô & Mì (index 6) ----
            ('Mì Hảo Hảo', 'Mì tôm chua cay Hảo Hảo, gói 75g', 4500, 'gói', 500, 6, 300),
            ('Phở khô Bích Chi', 'Phở khô Bích Chi gói 200g', 12000, 'gói', 100, 6, 60),
            ('Bún gạo Safoco', 'Bún gạo khô Safoco 400g', 18000, 'gói', 80, 6, 50),
            ('Nui ống Meizan', 'Nui ống Meizan 400g, dùng nấu súp', 15000, 'gói', 60, 6, 40),
            ('Cháo yến Thiên Hoàng', 'Cháo yến sào Thiên Hoàng hộp 50g', 25000, 'hộp', 45, 6, 35),
            # ---- Bánh kẹo (index 7) ----
            ('Bánh Oreo', 'Bánh quy Oreo socola kem vani 133g', 22000, 'gói', 120, 7, 95),
            ('Kẹo dẻo Haribo', 'Kẹo dẻo Haribo Goldbears 80g', 30000, 'gói', 80, 7, 70),
            ('Snack Poca', 'Snack khoai tây Poca vị tảo biển 52g', 12000, 'gói', 150, 7, 130),
            ('Bánh mì sandwich', 'Bánh mì sandwich Kinh Đô gói 100g', 18000, 'gói', 60, 7, 55),
            ('Socola KitKat', 'Socola KitKat thanh 2F 17g', 8000, 'thanh', 200, 7, 160),
        ]

        products = []
        for name, desc, price, unit, stock, cat_idx, sold in products_data:
            p = Product(
                name=name, description=desc, price=price,
                unit=unit, stock=stock,
                category_id=categories[cat_idx].id,
                total_sold=sold, is_active=True
            )
            db.session.add(p)
            products.append(p)

        db.session.flush()
        print(f"✅ Đã tạo {len(products)} sản phẩm.")

        # ============================
        # 4. TẠO ĐƠN HÀNG MẪU
        # (Quan trọng cho Collaborative Filtering)
        # ============================
        order_count = 0
        for user in users:
            # Mỗi user đặt 2-4 đơn hàng
            num_orders = random.randint(2, 4)
            for _ in range(num_orders):
                # Mỗi đơn có 2-5 sản phẩm ngẫu nhiên
                order_products = random.sample(products, random.randint(2, 5))
                total = 0
                order = Order(
                    user_id=user.id,
                    status=random.choice(['completed', 'completed', 'completed', 'pending']),
                    shipping_name=user.full_name,
                    shipping_phone=user.phone,
                    shipping_address=user.address
                )
                db.session.add(order)
                db.session.flush()

                for prod in order_products:
                    qty = random.randint(1, 3)
                    item = OrderItem(
                        order_id=order.id,
                        product_id=prod.id,
                        quantity=qty,
                        price_at_purchase=prod.price
                    )
                    total += float(prod.price) * qty
                    db.session.add(item)

                order.total_amount = total
                order_count += 1

        db.session.commit()
        print(f"✅ Đã tạo {order_count} đơn hàng mẫu.")
        print("\n🎉 SEED HOÀN TẤT! Thông tin đăng nhập:")
        print("   Admin: admin / admin123")
        print("   User:  nguyen_van_a / 123456 (và các user b, c, d, e)")


if __name__ == '__main__':
    seed()
