"""
config.py - Cấu hình ứng dụng Flask
Chứa thông tin kết nối Database, Secret Key, và các cấu hình chung.
"""
import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


class Config:
    # Secret key cho session và CSRF protection
    SECRET_KEY = os.environ.get('SECRET_KEY', 'food-store-secret-key-2024')

    # ============================================================
    # CẤU HÌNH MYSQL - Flask-SQLAlchemy
    # Format: mysql+pymysql://username:password@host:port/database
    # ============================================================
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        'DATABASE_URL',
        'mysql+pymysql://root:123456@localhost:3306/food_store_db'
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False  # Tắt tracking để tiết kiệm bộ nhớ

    # Cấu hình upload ảnh sản phẩm
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads')
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024  # Giới hạn file upload 5MB
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

    # Tham số α cho Hybrid Recommendation (mặc định 0.5)
    RECOMMENDATION_ALPHA = 0.5
    RECOMMENDATION_TOP_N = 8  # Số sản phẩm gợi ý hiển thị
# C:\DATN_TranThiHoaiHeThongQuanLyVaBanThucPhamTrucTuyen (1)\food_store\config.py
    # ============================================================
    # CAU HINH VNPAY - Sandbox mac dinh, co the override bang env
    # ============================================================
    VNPAY_PAYMENT_URL = os.environ.get(
        'VNPAY_PAYMENT_URL',
        'https://sandbox.vnpayment.vn/paymentv2/vpcpay.html'
    )
    #VNPAY_TMN_CODE = os.environ.get('VNPAY_TMN_CODE', '')
    #VNPAY_HASH_SECRET = os.environ.get('VNPAY_HASH_SECRET', '')
    VNPAY_TMN_CODE = 'GSJESLWY'
    VNPAY_HASH_SECRET = 'J50RMXUKHLQ1CLX1WKJ6GQ2MHV4DSXE0'
    VNPAY_RETURN_PATH = os.environ.get('VNPAY_RETURN_PATH', '/payment/vnpay/return')
    VNPAY_IPN_PATH = os.environ.get('VNPAY_IPN_PATH', '/payment/vnpay/ipn')
    VNPAY_ORDER_TYPE = os.environ.get('VNPAY_ORDER_TYPE', 'other')
    VNPAY_LOCALE = os.environ.get('VNPAY_LOCALE', 'vn')
    VNPAY_EXPIRE_MINUTES = int(os.environ.get('VNPAY_EXPIRE_MINUTES', '15'))
    #VNPAY_ALLOW_MOCK = os.environ.get('VNPAY_ALLOW_MOCK', '1') == '1'
    VNPAY_ALLOW_MOCK = False
