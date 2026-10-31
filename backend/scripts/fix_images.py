import httpx
from bs4 import BeautifulSoup
from backend.app.core.database import SessionLocal
from backend.app.models.product import Product

headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

CATEGORY_PAGES = [
    "https://vietro.com.vn/dieu-hoa-daikin",
    "https://vietro.com.vn/dieu-hoa-panasonic",
    "https://vietro.com.vn/tivi-samsung",
    "https://vietro.com.vn/tivi-sony",
    "https://vietro.com.vn/tu-lanh-samsung",
    "https://vietro.com.vn/tu-lanh-panasonic",
    "https://vietro.com.vn/may-giat-samsung",
    "https://vietro.com.vn/may-giat-aqua",
    "https://vietro.com.vn/quat-daikiosan"
]

FALLBACK_IMAGES = {
    "Điều hòa": "https://vietro.com.vn/uploads/product/dieu-hoa-daikin-ftf50xv1v-2hp-new-2026-1784704390.png",
    "Tivi": "https://vietro.com.vn/uploads/product/smart-tivi-crystal-uhd-samsung-4k-75-inch-ua75u8500h-new-2026-1788755252.png",
    "Tủ lạnh": "https://vietro.com.vn/uploads/product/tu-lanh-panasonic-inverter-306-lit-nr-tv341vgmv-1662973715.jpg",
    "Máy giặt": "https://vietro.com.vn/uploads/product/may-giat-thong-minh-ai-ecobubble-10kg-ww10tp44dsbsv-1663041498.jpg",
    "Quạt làm mát": "https://vietro.com.vn/uploads/product/quat-lam-mat-daikiosan-dm103-1654157774.png"
}

def update_product_images():
    db = SessionLocal()
    client = httpx.Client(headers=headers, timeout=15, verify=False)
    img_map = {}

    print("Cào lại đường dẫn ảnh chính xác từ vietro.com.vn...")
    for url in CATEGORY_PAGES:
        try:
            r = client.get(url)
            if r.status_code == 200:
                soup = BeautifulSoup(r.text, "html.parser")
                for box in soup.select(".box"):
                    h3 = box.select_one("h3.p-tt")
                    img = box.select_one(".img img")
                    if h3 and img:
                        name = h3.text.strip()
                        src = img.get("data-src") or img.get("src")
                        if src and not src.endswith("sale.svg"):
                            if src.startswith("/"):
                                src = f"https://vietro.com.vn{src}"
                            img_map[name.lower()] = src
        except Exception as e:
            print(f"Lỗi tải {url}: {e}")

    print(f"Thu thập được {len(img_map)} ảnh sản phẩm chuẩn.")
    
    products = db.query(Product).all()
    updated_count = 0
    for p in products:
        p_name_lower = p.name.lower()
        new_img = None
        # Try matching exact or substring
        for name_key, img_url in img_map.items():
            if name_key in p_name_lower or p_name_lower in name_key or p.model.lower() in name_key:
                new_img = img_url
                break
        
        # Fallback to authentic category image if still not matched or was sale.svg
        if not new_img or "sale.svg" in (p.image_url or ""):
            new_img = new_img or FALLBACK_IMAGES.get(p.category, FALLBACK_IMAGES["Điều hòa"])

        if new_img and new_img != p.image_url:
            p.image_url = new_img
            updated_count += 1

    db.commit()
    print(f"Đã cập nhật thành công {updated_count} ảnh sản phẩm trong cơ sở dữ liệu!")
    db.close()

if __name__ == "__main__":
    update_product_images()
