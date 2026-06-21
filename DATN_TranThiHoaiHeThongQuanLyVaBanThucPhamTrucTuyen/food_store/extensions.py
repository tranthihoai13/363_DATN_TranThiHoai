"""
extensions.py - Khởi tạo các Flask extensions
Tách riêng để tránh circular import giữa app.py và models.py.
"""
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager

# Khởi tạo SQLAlchemy instance (chưa bind vào app)
db = SQLAlchemy()

# Khởi tạo Flask-Login manager
login_manager = LoginManager()
login_manager.login_view = 'login'  # Redirect đến trang login nếu chưa đăng nhập
login_manager.login_message = 'Vui lòng đăng nhập để tiếp tục.'
login_manager.login_message_category = 'warning'
