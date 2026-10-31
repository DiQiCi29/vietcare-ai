import re
import logging
from datetime import datetime, date, timedelta
import httpx
from bs4 import BeautifulSoup

from backend.app.core.database import SessionLocal, Base, engine
from backend.app.core.security import get_password_hash
from backend.app.models.user import User, Customer, UserRole
from backend.app.models.product import Product, SoldItem
from backend.app.models.policy import WarrantyPolicy
from backend.app.models.warranty import WarrantyRequest, RequestStatusHistory, RequestStatus, ReceptionChannel

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

CATEGORY_URLS = [
    {"url": "https://vietro.com.vn/dieu-hoa-daikin", "category": "Điều hòa", "brand": "Daikin", "warranty_months": 24},
    {"url": "https://vietro.com.vn/dieu-hoa-panasonic", "category": "Điều hòa", "brand": "Panasonic", "warranty_months": 24},
    {"url": "https://vietro.com.vn/tivi-samsung", "category": "Tivi", "brand": "Samsung", "warranty_months": 24},
    {"url": "https://vietro.com.vn/tivi-sony", "category": "Tivi", "brand": "Sony", "warranty_months": 24},
    {"url": "https://vietro.com.vn/tu-lanh-samsung", "category": "Tủ lạnh", "brand": "Samsung", "warranty_months": 24},
    {"url": "https://vietro.com.vn/tu-lanh-panasonic", "category": "Tủ lạnh", "brand": "Panasonic", "warranty_months": 24},
    {"url": "https://vietro.com.vn/may-giat-samsung", "category": "Máy giặt", "brand": "Samsung", "warranty_months": 24},
    {"url": "https://vietro.com.vn/may-giat-aqua", "category": "Máy giặt", "brand": "Aqua", "warranty_months": 24},
    {"url": "https://vietro.com.vn/quat-daikiosan", "category": "Quạt làm mát", "brand": "Daikiosan", "warranty_months": 12},
]

def extract_model(name: str, brand: str) -> str:
    """Extract model code from product title"""
    # Look for capitalized alphanumeric codes with digits (e.g. FTF50XV1V, QA55Q60B, WA10T5260BV)
    tokens = re.findall(r'[A-Za-z0-9\-\/]{5,}', name)
    filtered = [t for t in tokens if any(char.isdigit() for char in t) and not t.lower().startswith("202") and not t.lower() in ["inverter", "bluetooth", "android"]]
    if filtered:
        return filtered[0].strip("/-")
    # Fallback: slugify part of the name
    clean = re.sub(r'[^A-Za-z0-9]', '', name)
    return clean[:12].upper()

def crawl_products(db):
    logger.info("=== BẮT ĐẦU CÀO DỮ LIỆU SẢN PHẨM TỪ VIETRO.COM.VN ===")
    total_added = 0
    client = httpx.Client(headers=HEADERS, timeout=20.0, verify=False)

    for cat_info in CATEGORY_URLS:
        try:
            logger.info(f"Đang cào: {cat_info['url']} ({cat_info['category']} - {cat_info['brand']})")
            resp = client.get(cat_info['url'])
            if resp.status_code != 200:
                logger.warning(f"Lỗi HTTP {resp.status_code} khi tải {cat_info['url']}")
                continue

            soup = BeautifulSoup(resp.text, "html.parser")
            h3_elements = soup.select("h3.p-tt")
            logger.info(f"-> Tìm thấy {len(h3_elements)} sản phẩm")

            # Take up to 6 products per category for a diverse, balanced catalog
            count_per_cat = 0
            for h3 in h3_elements:
                if count_per_cat >= 6:
                    break
                a_tag = h3.find("a")
                if not a_tag:
                    continue
                name = a_tag.text.strip()
                if not name:
                    continue

                # Find image
                parent_box = h3.find_parent("div", class_="box") or h3.find_parent("div")
                img_url = None
                if parent_box:
                    img_tag = parent_box.find("img")
                    if img_tag:
                        img_url = img_tag.get("data-src") or img_tag.get("src")
                        if img_url and img_url.startswith("/"):
                            img_url = f"https://vietro.com.vn{img_url}"

                model = extract_model(name, cat_info["brand"])

                # Check if model already exists
                existing = db.query(Product).filter(Product.model == model).first()
                if not existing:
                    product = Product(
                        name=name,
                        model=model,
                        brand=cat_info["brand"],
                        category=cat_info["category"],
                        default_warranty_months=cat_info["warranty_months"],
                        image_url=img_url or "https://vietro.com.vn/uploads/files/Untitled-2-01%20copy.png",
                        specifications=f"Sản phẩm chính hãng {cat_info['brand']} phân phối bởi Viettronimex Đà Nẵng. Bảo hành {cat_info['warranty_months']} tháng."
                    )
                    db.add(product)
                    db.commit()
                    total_added += 1
                    count_per_cat += 1
                    logger.info(f"  + Đã lưu sản phẩm: {name} (Model: {model})")
        except Exception as e:
            logger.error(f"Lỗi khi cào {cat_info['url']}: {e}")

    logger.info(f"=== HOÀN TẤT CÀO SẢN PHẨM: Đã thêm {total_added} sản phẩm vào CSDL ===")

def seed_warranty_policies(db):
    logger.info("=== NẠP CHÍNH SÁCH BẢO HÀNH (KNOWLEDGE BASE CHO RAG) ===")
    
    policies = [
        # 1. Chính sách chung Viettronimex
        {
            "product_category": "Chung",
            "brand": "Viettronimex",
            "error_group": "Điều kiện bảo hành chung",
            "title": "Điều kiện bảo hành miễn phí tại Viettronimex",
            "content": "Sản phẩm được bảo hành miễn phí nếu đáp ứng đầy đủ các điều kiện sau: (1) Còn trong thời hạn bảo hành tính từ ngày mua hàng ghi nhận trên hệ thống; (2) Số Serial trên sản phẩm trùng khớp với dữ liệu đăng ký; (3) Tem niêm phong bảo hành còn nguyên vẹn, không bị rách, vỡ hay tẩy xóa; (4) Hư hỏng do lỗi kỹ thuật của nhà sản xuất phát sinh trong điều kiện sử dụng bình thường.",
            "is_covered": True,
            "conditions": "Có hóa đơn hoặc số điện thoại mua hàng trùng khớp trên hệ thống Viettronimex."
        },
        {
            "product_category": "Chung",
            "brand": "Viettronimex",
            "error_group": "Từ chối bảo hành",
            "title": "Các trường hợp từ chối bảo hành tại Viettronimex",
            "content": "Viettronimex từ chối bảo hành miễn phí (chuyển sang sửa chữa có tính phí nếu khách yêu cầu) đối với các trường hợp: (1) Hư hỏng do tác động vật lý: rơi vỡ, va đập, nứt gãy, trầy xước, móp méo; (2) Hư hỏng do ẩm ướt, hoen rỉ, ngấm nước, chập cháy do nguồn điện không ổn định, sét đánh, thiên tai; (3) Hư hỏng do côn trùng hoặc động vật xâm nhập (chuột cắn, gián bò vào bo mạch); (4) Tự ý tháo gỡ, sửa chữa bởi bên thứ ba không thuộc ủy quyền; (5) Các phụ kiện tiêu hao hoặc đi kèm: pin, remote, dây nguồn, dây tín hiệu, cánh quạt vỡ do va chạm.",
            "is_covered": False,
            "conditions": "Khách hàng có thể sử dụng dịch vụ sửa chữa tính phí, Viettronimex hỗ trợ miễn phí 100% tiền công, chỉ tính tiền vật tư/linh kiện."
        },
        {
            "product_category": "Chung",
            "brand": "Viettronimex",
            "error_group": "Chính sách bảo trì",
            "title": "Chính sách bảo trì bảo dưỡng và linh kiện thay thế",
            "content": "Tất cả sản phẩm mua tại Viettronimex đều được hưởng quyền lợi bảo trì trong suốt thời hạn bảo hành. Trong trường hợp cần thay thế linh phụ kiện ngoài bảo hành, Viettronimex cam kết miễn phí 100% công thợ thay thế, giá linh kiện được tính đúng theo bảng giá niêm yết của hãng sản xuất.",
            "is_covered": True,
            "conditions": "Áp dụng cho mọi khách hàng mua sắm tại hệ thống Viettronimex Đà Nẵng."
        },

        # 2. Điều hòa (Daikin, Panasonic, Samsung)
        {
            "product_category": "Điều hòa",
            "brand": "Daikin",
            "error_group": "Lỗi máy nén / Bo mạch",
            "title": "Chính sách bảo hành điều hòa Daikin",
            "content": "Điều hòa Daikin chính hãng được bảo hành 1 năm cho toàn bộ thân máy và 5 năm cho máy nén Inverter. Lỗi bo mạch dàn lạnh hoặc dàn nóng do linh kiện sản xuất được thay thế miễn phí trong 24 tháng đầu.",
            "is_covered": True,
            "conditions": "Máy được lắp đặt đúng tiêu chuẩn kỹ thuật của hãng, không bị ẩm mạch do nước tràn."
        },
        {
            "product_category": "Điều hòa",
            "brand": "Chung",
            "error_group": "Chảy nước dàn lạnh",
            "title": "Xử lý và bảo hành sự cố điều hòa chảy nước dàn lạnh",
            "content": "Sự cố điều hòa bị chảy nước dàn lạnh thường do máng nước bị bụi bẩn tắc nghẽn sau thời gian dài sử dụng (cần vệ sinh) hoặc ống thoát nước bị gập, tắc. Nếu máy mới lắp đặt trong vòng 30 ngày bị chảy nước do lỗi lắp đặt hoặc nứt máng nước từ nhà sản xuất, kỹ thuật viên sẽ xử lý miễn phí. Nếu do bụi bẩn tích tụ sau 6 tháng sử dụng, đây thuộc dịch vụ bảo dưỡng/vệ sinh định kỳ.",
            "is_covered": True,
            "conditions": "Kỹ thuật viên sẽ kiểm tra trực tiếp để phân biệt giữa lỗi lắp đặt/máng nước hay do bụi bẩn cần vệ sinh."
        },
        {
            "product_category": "Điều hòa",
            "brand": "Chung",
            "error_group": "Không lạnh / Kém lạnh",
            "title": "Điều hòa không mát, mát yếu hoặc thiếu gas",
            "content": "Nếu điều hòa bị mất gas do hở mối hàn tại dàn lạnh/dàn nóng từ nhà sản xuất, sản phẩm được hàn kín và nạp gas miễn phí. Nếu hở rò rỉ gas do va chạm ngoại lực hoặc ống đồng bên ngoài thi công bị gãy, chi phí nạp gas và ống đồng sẽ tính theo quy định.",
            "is_covered": True,
            "conditions": "Còn trong thời hạn bảo hành và áp suất rò rỉ được kỹ thuật viên đo đạc xác nhận."
        },

        # 3. Tivi (Samsung, Sony, LG)
        {
            "product_category": "Tivi",
            "brand": "Samsung",
            "error_group": "Màn hình / Kẻ sọc",
            "title": "Chính sách bảo hành màn hình Tivi Samsung",
            "content": "Tivi Samsung bảo hành 24 tháng cho màn hình và bo mạch. Các lỗi sọc màn hình, chết điểm ảnh (trên 5 điểm), nhấp nháy panel do lỗi sản xuất được thay thế panel chính hãng miễn phí. Lưu ý: Màn hình bị nứt, bể, có dấu hiệu va đập, tì đè hoặc ngấm nước tiểu trẻ em/ẩm mốc sẽ bị từ chối bảo hành.",
            "is_covered": True,
            "conditions": "Màn hình không có vết nứt vỡ cơ học bên trong lẫn bên ngoài kính."
        },
        {
            "product_category": "Tivi",
            "brand": "Sony",
            "error_group": "Lỗi nháy đèn đỏ / Mất nguồn",
            "title": "Chính sách bảo hành Tivi Sony nháy đèn đỏ báo lỗi",
            "content": "Tivi Sony nhấp nháy đèn nguồn màu đỏ (2 nháy, 4 nháy, 6 nháy...) là tín hiệu bo nguồn hoặc bo cao áp bị lỗi tự ngắt để bảo vệ máy. Trường hợp này được bảo hành miễn phí nếu tivi còn hạn bảo hành và không bị sét đánh hoặc chập nguồn điện.",
            "is_covered": True,
            "conditions": "Không có mùi khét do chập cháy nguồn điện quá áp hoặc sét đánh."
        },

        # 4. Tủ lạnh (Samsung, Panasonic)
        {
            "product_category": "Tủ lạnh",
            "brand": "Samsung",
            "error_group": "Không đông đá / Kêu to",
            "title": "Chính sách bảo hành máy nén tủ lạnh Samsung",
            "content": "Tủ lạnh Samsung Inverter được bảo hành máy nén (Digital Inverter Compressor) lên đến 10 năm hoặc 20 năm (tùy dòng máy), thân tủ và hệ thống xả đá bảo hành 24 tháng. Lỗi ngăn đông không lạnh do hỏng cảm biến nhiệt hoặc quạt gió được thay thế miễn phí trong 2 năm đầu.",
            "is_covered": True,
            "conditions": "Dàn tản nhiệt không bị chuột cắn thủng ống."
        },

        # 5. Máy giặt (Samsung, Aqua)
        {
            "product_category": "Máy giặt",
            "brand": "Samsung",
            "error_group": "Rung lắc / Không vắt / Báo lỗi",
            "title": "Bảo hành động cơ máy giặt và bo điều khiển",
            "content": "Máy giặt Samsung được bảo hành 11 năm cho động cơ truyền động trực tiếp (Digital Inverter) và 2 năm cho bo mạch điều khiển. Các mã lỗi như 4C (không cấp nước), 5C (không xả nước), dC (chưa đóng cửa) sẽ được kỹ thuật viên hướng dẫn kiểm tra lưới lọc trước, nếu hỏng van cấp/xả do kỹ thuật sẽ được bảo hành.",
            "is_covered": True,
            "conditions": "Không để máy ngoài trời mưa ngập hoặc gián làm tổ trong bo mạch."
        },

        # 6. Quạt làm mát
        {
            "product_category": "Quạt làm mát",
            "brand": "Daikiosan",
            "error_group": "Không bơm nước / Cháy motor",
            "title": "Bảo hành quạt điều hòa Daikiosan",
            "content": "Quạt làm mát không khí Daikiosan bảo hành 12 tháng cho motor quạt và hệ thống bơm nước. Nếu motor bị kẹt do nước vào hoặc bơm nước ngưng hoạt động do lỗi sản xuất sẽ được đổi mới linh kiện. Gãy cánh quạt do dị vật rơi vào không thuộc phạm vi bảo hành miễn phí.",
            "is_covered": True,
            "conditions": "Motor còn nguyên tem nhà máy."
        }
    ]

    for p_data in policies:
        existing = db.query(WarrantyPolicy).filter(
            WarrantyPolicy.title == p_data["title"]
        ).first()
        if not existing:
            pol = WarrantyPolicy(**p_data)
            db.add(pol)
    db.commit()
    logger.info(f"-> Đã nạp thành công {len(policies)} chính sách bảo hành vào Knowledge Base!")

def seed_users_and_customers(db):
    logger.info("=== NẠP TÀI KHOẢN MẪU (NHÂN VIÊN & KHÁCH HÀNG) ===")

    # 1. Staff Accounts
    staff_list = [
        {"name": "Quản Trị Viên", "username": "admin", "email": "admin@vietro.com.vn", "role": UserRole.ADMIN, "phone": "0905000001"},
        {"name": "CSKH Thu Hà", "username": "cskh", "email": "cskh@vietro.com.vn", "role": UserRole.CSKH, "phone": "0905000002"},
        {"name": "KTV Lê Văn Minh", "username": "ktv_minh", "email": "ktv.minh@vietro.com.vn", "role": UserRole.TECHNICIAN, "phone": "0905000003"},
        {"name": "KTV Hoàng Nam", "username": "ktv_nam", "email": "ktv.nam@vietro.com.vn", "role": UserRole.TECHNICIAN, "phone": "0905000004"},
    ]

    for s in staff_list:
        existing = db.query(User).filter(User.username == s["username"]).first()
        if not existing:
            user = User(
                name=s["name"],
                username=s["username"],
                email=s["email"],
                role=s["role"],
                phone=s["phone"],
                hashed_password=get_password_hash("123456"),
                is_active=True
            )
            db.add(user)
    db.commit()
    logger.info("-> Đã nạp 4 tài khoản nhân viên (Admin, CSKH, 2 KTV, mật khẩu: 123456)")

    # 2. Demo Customers
    customers_data = [
        {
            "full_name": "Nguyễn Văn An",
            "phone": "0905123456",
            "email": "an.nguyen@example.com",
            "address": "120 Nguyễn Văn Linh, Q. Hải Châu, TP. Đà Nẵng",
            "is_first_login_changed": True
        },
        {
            "full_name": "Trần Thị Bích",
            "phone": "0914987654",
            "email": "bich.tran@example.com",
            "address": "45 Điện Biên Phủ, Q. Thanh Khê, TP. Đà Nẵng",
            "is_first_login_changed": False
        }
    ]

    for c in customers_data:
        existing = db.query(Customer).filter(Customer.phone == c["phone"]).first()
        if not existing:
            cust = Customer(
                full_name=c["full_name"],
                phone=c["phone"],
                email=c["email"],
                address=c["address"],
                is_first_login_changed=c["is_first_login_changed"],
                hashed_password=get_password_hash("123456")
            )
            db.add(cust)
    db.commit()
    logger.info("-> Đã nạp 2 khách hàng mẫu (SĐT: 0905123456, 0914987654 - Mật khẩu: 123456)")

    # 3. Bind Sold Items to Customers
    customer_an = db.query(Customer).filter(Customer.phone == "0905123456").first()
    customer_bich = db.query(Customer).filter(Customer.phone == "0914987654").first()

    # Find some products in DB
    ac_product = db.query(Product).filter(Product.category == "Điều hòa").first()
    tv_product = db.query(Product).filter(Product.category == "Tivi").first()
    wm_product = db.query(Product).filter(Product.category == "Máy giặt").first()

    if customer_an and ac_product:
        # Item 1: Still valid warranty (Bought 5 months ago)
        p_date = date.today() - timedelta(days=150)
        e_date = p_date + timedelta(days=ac_product.default_warranty_months * 30)
        existing_sold1 = db.query(SoldItem).filter(SoldItem.serial_number == "DK-2025-998877").first()
        if not existing_sold1:
            item1 = SoldItem(
                customer_id=customer_an.id,
                product_id=ac_product.id,
                serial_number="DK-2025-998877",
                purchase_date=p_date,
                warranty_expire_date=e_date,
                notes="Lắp đặt tại phòng khách tầng 2"
            )
            db.add(item1)

    if customer_an and tv_product:
        # Item 2: Expired warranty (Bought 26 months ago)
        p_date2 = date.today() - timedelta(days=800)
        e_date2 = p_date2 + timedelta(days=tv_product.default_warranty_months * 30)
        existing_sold2 = db.query(SoldItem).filter(SoldItem.serial_number == "TV-2023-445566").first()
        if not existing_sold2:
            item2 = SoldItem(
                customer_id=customer_an.id,
                product_id=tv_product.id,
                serial_number="TV-2023-445566",
                purchase_date=p_date2,
                warranty_expire_date=e_date2,
                notes="Tivi phòng sinh hoạt chung"
            )
            db.add(item2)

    if customer_bich and wm_product:
        # Item 3: Still valid warranty (Bought 3 months ago)
        p_date3 = date.today() - timedelta(days=90)
        e_date3 = p_date3 + timedelta(days=wm_product.default_warranty_months * 30)
        existing_sold3 = db.query(SoldItem).filter(SoldItem.serial_number == "WM-2025-112233").first()
        if not existing_sold3:
            item3 = SoldItem(
                customer_id=customer_bich.id,
                product_id=wm_product.id,
                serial_number="WM-2025-112233",
                purchase_date=p_date3,
                warranty_expire_date=e_date3,
                notes="Máy giặt ban công"
            )
            db.add(item3)

    db.commit()
    logger.info("-> Đã gắn các sản phẩm đã mua (SoldItems) cho khách hàng test!")

    # 4. Seed 1 Sample Warranty Request with full timeline
    ktv_minh = db.query(User).filter(User.username == "ktv_minh").first()
    item_ac = db.query(SoldItem).filter(SoldItem.serial_number == "DK-2025-998877").first()
    
    if item_ac and ktv_minh:
        existing_req = db.query(WarrantyRequest).filter(WarrantyRequest.request_code == "BH-2026-0001").first()
        if not existing_req:
            req = WarrantyRequest(
                request_code="BH-2026-0001",
                customer_id=customer_an.id,
                sold_item_id=item_ac.id,
                error_group="Chảy nước dàn lạnh",
                error_description="Máy lạnh bật khoảng 30 phút thì bắt đầu có nước nhỏ giọt từ góc phải dàn lạnh xuống sàn nhà.",
                support_address="120 Nguyễn Văn Linh, Q. Hải Châu, TP. Đà Nẵng",
                channel=ReceptionChannel.WEB,
                status=RequestStatus.ASSIGNED,
                technician_id=ktv_minh.id,
                appointment_date=datetime.utcnow() + timedelta(days=1),
                repeat_call_count=1,
                created_at=datetime.utcnow() - timedelta(hours=4)
            )
            db.add(req)
            db.commit()

            # Add status histories
            h1 = RequestStatusHistory(
                request_id=req.id,
                status=RequestStatus.RECEIVED,
                notes="Khách hàng gửi yêu cầu bảo hành từ website",
                created_at=datetime.utcnow() - timedelta(hours=4)
            )
            h2 = RequestStatusHistory(
                request_id=req.id,
                status=RequestStatus.VERIFYING,
                notes="CSKH kiểm tra thông tin máy: Model còn trong hạn bảo hành chính hãng.",
                created_at=datetime.utcnow() - timedelta(hours=3)
            )
            h3 = RequestStatusHistory(
                request_id=req.id,
                status=RequestStatus.ASSIGNED,
                notes="Đã phân công KTV Lê Văn Minh, hẹn khách ngày mai đến kiểm tra thực tế.",
                created_at=datetime.utcnow() - timedelta(hours=2)
            )
            db.add_all([h1, h2, h3])
            db.commit()
            logger.info("-> Đã nạp 1 yêu cầu bảo hành mẫu BH-2026-0001 kèm timeline lịch sử!")

def main():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        crawl_products(db)
        seed_warranty_policies(db)
        seed_users_and_customers(db)
        logger.info("🎉 HOÀN THÀNH TẤT CẢ DỮ LIỆU BAN ĐẦU CHO HỆ THỐNG!")
    finally:
        db.close()

if __name__ == "__main__":
    main()
