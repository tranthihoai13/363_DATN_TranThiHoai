"""
download_images.py - Tải ảnh thực phẩm cho tất cả sản phẩm
Sử dụng Unsplash Source API (miễn phí, không cần API key)
"""
import os
import sys
import time
import urllib.request
import ssl

# Bỏ qua SSL verification cho đơn giản
ssl._create_default_https_context = ssl._create_unverified_context

# Thêm thư mục hiện tại vào path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from extensions import db
from models import Product

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'uploads')

# Map: product_id hoặc tên -> keyword tìm kiếm ảnh tiếng Anh
PRODUCT_IMAGE_KEYWORDS = {
    # Rau củ quả
    'Rau muống': 'morning+glory+vegetable',
    'Cà chua': 'fresh+tomatoes',
    'Khoai tây': 'potatoes',
    'Bắp cải': 'cabbage+vegetable',
    'Hành tây': 'onion',
    # Trái cây
    'Chuối già': 'bananas+fruit',
    'Táo Fuji': 'red+apple+fruit',
    'Cam sành': 'fresh+oranges',
    'Xoài cát': 'mango+fruit',
    'Dưa hấu': 'watermelon',
    # Thịt tươi
    'Thịt ba chỉ heo': 'pork+belly+meat',
    'Ức gà': 'chicken+breast+meat',
    'Thịt bò Úc': 'beef+steak+raw',
    'Sườn non heo': 'pork+ribs',
    'Thịt đùi gà': 'chicken+leg+meat',
    # Hải sản
    'Tôm sú': 'shrimp+seafood',
    'Cá hồi Na Uy': 'salmon+fillet',
    'Mực ống': 'squid+seafood',
    'Nghêu lụa': 'clams+seafood',
    'Cá basa': 'fish+fillet+white',
    # Đồ uống
    'Sữa tươi Vinamilk': 'milk+bottle',
    'Nước cam ép': 'orange+juice',
    'Trà xanh 0 độ': 'green+tea+bottle',
    'Cà phê sữa đá': 'iced+coffee',
    'Nước dừa tươi': 'coconut+water',
    # Gia vị
    'Nước mắm Phú Quốc': 'fish+sauce+bottle',
    'Dầu ăn Tường An': 'cooking+oil+bottle',
    'Bột nêm Knorr': 'seasoning+powder',
    'Tương ớt Chinsu': 'chili+sauce',
    'Hạt nêm Vedan': 'bouillon+seasoning',
    # Đồ khô & Mì
    'Mì Hảo Hảo': 'instant+noodles',
    'Phở khô Bích Chi': 'rice+noodles+dry',
    'Bún gạo Safoco': 'rice+vermicelli',
    'Nui ống Meizan': 'pasta+macaroni',
    'Cháo yến Thiên Hoàng': 'porridge+congee',
    # Bánh kẹo
    'Bánh Oreo': 'oreo+cookies',
    'Kẹo dẻo Haribo': 'gummy+bears+candy',
    'Snack Poca': 'potato+chips+snack',
    'Bánh mì sandwich': 'sandwich+bread',
    'Socola KitKat': 'chocolate+bar',
}


def download_image(keyword, filename, idx):
    """Tải ảnh từ loremflickr (redirect đến ảnh Flickr thực)"""
    url = f"https://loremflickr.com/400/300/{keyword}"
    filepath = os.path.join(UPLOAD_DIR, filename)
    
    if os.path.exists(filepath):
        print(f"  ⏭️  Đã có: {filename}")
        return True
    
    try:
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        response = urllib.request.urlopen(req, timeout=15)
        data = response.read()
        
        if len(data) > 1000:  # Kiểm tra ảnh hợp lệ (>1KB)
            with open(filepath, 'wb') as f:
                f.write(data)
            print(f"  ✅ [{idx}/40] Tải thành công: {filename} ({len(data)//1024}KB)")
            return True
        else:
            print(f"  ⚠️  [{idx}/40] Ảnh quá nhỏ: {filename}")
            return False
    except Exception as e:
        print(f"  ❌ [{idx}/40] Lỗi tải {filename}: {e}")
        return False


def generate_fallback_image(product_name, filename):
    """Tạo ảnh placeholder đơn giản bằng Pillow nếu tải thất bại"""
    try:
        from PIL import Image, ImageDraw, ImageFont
        
        # Màu theo danh mục
        colors = [
            (45, 106, 79),    # xanh lá đậm
            (82, 183, 136),   # xanh lá tươi 
            (255, 107, 53),   # cam
            (247, 178, 103),  # vàng cam
            (181, 131, 141),  # hồng đất
            (212, 163, 115),  # nâu ấm
        ]
        import hashlib
        color_idx = int(hashlib.md5(product_name.encode()).hexdigest(), 16) % len(colors)
        bg_color = colors[color_idx]
        
        img = Image.new('RGB', (400, 300), bg_color)
        draw = ImageDraw.Draw(img)
        
        # Vẽ pattern trang trí
        lighter = tuple(min(255, c + 30) for c in bg_color)
        for i in range(0, 400, 40):
            draw.line([(i, 0), (i + 150, 300)], fill=lighter, width=2)
        
        # Vẽ tên sản phẩm
        try:
            font = ImageFont.truetype("arial.ttf", 24)
            font_small = ImageFont.truetype("arial.ttf", 16)
        except:
            font = ImageFont.load_default()
            font_small = font
        
        # Text shadow + text
        text = product_name[:20]
        bbox = draw.textbbox((0, 0), text, font=font)
        tw = bbox[2] - bbox[0]
        x = (400 - tw) // 2
        draw.text((x + 1, 131), text, fill=(0, 0, 0, 80), font=font)
        draw.text((x, 130), text, fill='white', font=font)
        
        # Icon thực phẩm
        draw.text((180, 90), "🍽️", fill='white', font=font_small)
        
        filepath = os.path.join(UPLOAD_DIR, filename)
        img.save(filepath, 'JPEG', quality=85)
        print(f"  🎨 Tạo placeholder: {filename}")
        return True
    except ImportError:
        print(f"  ⚠️  Không có Pillow, bỏ qua placeholder cho {filename}")
        return False
    except Exception as e:
        print(f"  ❌ Lỗi tạo placeholder: {e}")
        return False


def main():
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    
    app = create_app()
    with app.app_context():
        products = Product.query.all()
        print(f"\n🖼️  Bắt đầu tải ảnh cho {len(products)} sản phẩm...")
        print(f"📁 Thư mục lưu: {UPLOAD_DIR}\n")
        
        success = 0
        for idx, product in enumerate(products, 1):
            # Tạo tên file an toàn
            safe_name = product.name.lower()
            for char in ' /\\:*?"<>|()':
                safe_name = safe_name.replace(char, '_')
            filename = f"product_{product.id}_{safe_name[:30]}.jpg"
            
            # Tìm keyword phù hợp
            keyword = PRODUCT_IMAGE_KEYWORDS.get(product.name, 'food+fresh')
            
            # Thử tải ảnh
            downloaded = download_image(keyword, filename, idx)
            
            # Nếu tải thất bại, tạo placeholder
            if not downloaded:
                downloaded = generate_fallback_image(product.name, filename)
            
            if downloaded:
                product.image = filename
                success += 1
            
            # Delay nhỏ để không bị rate limit
            time.sleep(0.5)
        
        db.session.commit()
        print(f"\n🎉 Hoàn thành! {success}/{len(products)} sản phẩm có ảnh.")
        print(f"📁 Ảnh lưu tại: {UPLOAD_DIR}")


if __name__ == '__main__':
    main()
