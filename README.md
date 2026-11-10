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
| **Khách hàng DEV** (dùng hằng ngày) | `0900000000` | Không cần, vào thẳng | Xem giao diện, thử mọi chức năng khách hàng với 6 thiết bị mẫu. Không tốn lượt OTP |
| **Khách hàng (OTP)** (chỉ dùng khi demo) | Số thật đã đăng ký Twilio | Mã OTP qua SMS, **giới hạn 40 lượt** | Tra cứu sản phẩm đã mua, gửi yêu cầu bảo hành, đính kèm ảnh/video, chat tư vấn AI |
| **CSKH** | `cskh` | `123456` | Tiếp nhận phiếu bảo hành, kiểm tra SLA (4h làm việc), phân công Kỹ thuật viên |
| **Kỹ thuật viên** | `ktv_minh` | `123456` | Xem ca phân công, kiểm tra chi tiết lỗi, cập nhật tiến trình xử lý |
| **Trưởng phòng / Admin** | `admin` | `123456` | Dashboard tổng quan, thống kê hiệu suất KTV, giám sát các phiếu quá hạn SLA |

Nhân viên đăng nhập ở tab **Nhân viên** bằng mật khẩu. Khách hàng nhập số điện thoại ở tab **Khách hàng** rồi nhập mã OTP.

> [!CAUTION]
> **TIẾT KIỆM LƯỢT OTP:** nếu chỉ **xem web, xem giao diện hoặc thử chức năng** của khách hàng, hãy **luôn dùng tài khoản DEV `0900000000`**: vào thẳng, không cần OTP, không tốn lượt.
> Tài khoản khách hàng có OTP gửi SMS thật qua Twilio (bản dùng thử) và **chỉ có 40 lượt xác thực** (100 SMS, hết hạn sau 30 ngày). Mỗi lần bấm *Tiếp tục* hoặc *Gửi lại mã* tốn 1 SMS, nhập đúng mã tốn 1 lượt.
> **Chỉ dùng tài khoản OTP khi thật sự cần, để dành cho buổi demo.**

**Tài khoản dev (không cần OTP):** nhập số `0900000000` ở tab *Khách hàng* là vào thẳng, không gửi SMS nên không tốn lượt Twilio. Tài khoản có sẵn 6 sản phẩm: còn hạn, sắp hết hạn và đã hết hạn. Nếu máy chưa có tài khoản này, tạo bằng lệnh:
```powershell
.\venv\Scripts\python.exe -m backend.scripts.seed_dev_account
```
Danh sách số bỏ qua OTP nằm ở `OTP_BYPASS_PHONES` trong `.env`, nhiều số cách nhau bằng dấu phẩy. Đặt `OTP_BYPASS_PHONES=""` để tắt.

---

## 🔐 Đăng Nhập OTP Cho Khách Hàng

**Chế độ demo (mặc định):** khi chưa cấu hình Twilio, mã OTP hiện ngay trên màn hình đăng nhập và trong cửa sổ server. Không cần tài khoản hay Internet.

**Gửi SMS thật bằng Twilio Verify (bản dùng thử miễn phí):**
1. Đăng ký tại [twilio.com/try-twilio](https://www.twilio.com/try-twilio) **bằng số điện thoại Việt Nam** (bản dùng thử chỉ gửi SMS trong nước của số đăng ký).
2. Trong Console: vào **Verify → Services → Create new**, đặt tên `VietCare`, bật kênh **SMS**. Sao chép **Service SID** (bắt đầu bằng `VA`).
3. Thêm số của các thành viên demo vào **Phone Numbers → Verified Caller IDs** (tối đa 5 số, số đăng ký đã có sẵn).
4. Điền vào file `.env`: `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN` (trang chủ Console) và `TWILIO_VERIFY_SERVICE_SID`, rồi khởi động lại app.
5. Gán số thật cho một khách hàng mẫu để nhận SMS:
   ```powershell
   .\venv\Scripts\python.exe -m backend.scripts.set_customer_phone 0905123456 09xxxxxxxx
   ```

Giới hạn bản dùng thử: 30 ngày, 40 lượt xác thực, 100 SMS, nội dung tin theo mẫu của Twilio. Mỗi số phải chờ 30 giây mới gửi lại được mã. Mã có hiệu lực 5 phút.

---

## 🛠️ Công Nghệ Sử Dụng
- **Backend**: FastAPI, SQLAlchemy (SQLite), Pydantic
- **Frontend**: HTML5, Vanilla JavaScript, CSS3
- **AI & RAG**: Google Gemini API, ChromaDB

