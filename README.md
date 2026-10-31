# VietCare AI - Hệ Thống Quản Lý Bảo Hành Thông Minh

VietCare AI là giải pháp số hóa toàn diện quy trình tiếp nhận, phân công và xử lý bảo hành điện máy - gia dụng, tích hợp trợ lý AI tư vấn và theo dõi chuẩn mực SLA.

---

## 🚀 Hướng Dẫn Cài Đặt & Chạy Ứng Dụng (Dành Cho Windows)

### Bước 1: Yêu cầu chuẩn bị
- Cài đặt **Python 3.10 hoặc 3.11** từ [python.org](https://www.python.org/).
- ⚠️ **Lưu ý quan trọng**: Trong quá trình cài đặt, nhớ tích chọn ô **`Add python.exe to PATH`**.

### Bước 2: Cài đặt tự động (Chỉ làm 1 lần)
- Nhấp đúp chuột vào file **`1_cai_dat.bat`**
- Chương trình sẽ tự động tạo môi trường ảo `venv` và cài đặt toàn bộ thư viện cần thiết.

### Bước 3: Khởi chạy ứng dụng
- Nhấp đúp chuột vào file **`2_chay_app.bat`**
- Hệ thống sẽ tự động bật server và mở trình duyệt tại địa chỉ: `http://127.0.0.1:8000`

### Bước 4: Cập nhật code mới (Khi có bản cập nhật)
- Nhấp đúp chuột vào file **`3_cap_nhat.bat`** để tự động kéo code mới nhất về máy.

---

## 👥 Danh Sách Tài Khoản Đăng Nhập Mẫu

| Phân hệ / Vai trò | Tên đăng nhập | Mật khẩu | Chức năng kiểm tra |
| :--- | :--- | :--- | :--- |
| **Khách hàng** | `0905123456` | `123456` | Tra cứu sản phẩm đã mua, gửi yêu cầu bảo hành, đính kèm ảnh/video, chat tư vấn AI |
| **CSKH** | `cskh` | `123456` | Tiếp nhận phiếu bảo hành, kiểm tra SLA (4h làm việc), phân công Kỹ thuật viên |
| **Kỹ thuật viên** | `ktv_minh` | `123456` | Xem ca phân công, kiểm tra chi tiết lỗi, cập nhật tiến trình xử lý |
| **Trưởng phòng / Admin** | `admin` | `123456` | Dashboard tổng quan, thống kê hiệu suất KTV, giám sát các phiếu quá hạn SLA |

---

## 🛠️ Công Nghệ Sử Dụng
- **Backend**: FastAPI, SQLAlchemy (SQLite), Pydantic
- **Frontend**: HTML5, Vanilla JavaScript, CSS3
- **AI & RAG**: Google Gemini API, ChromaDB

