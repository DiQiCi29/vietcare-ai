@echo off
chcp 65001 > nul
title VIETCARE AI - MAY CHU DANG CHAY
echo ======================================================
echo       VIETCARE AI - KHỞI ĐỘNG HỆ THỐNG
echo ======================================================
echo.

if not exist venv (
    echo [LỖI] Chưa tìm thấy môi trường ảo venv!
    echo Bạn ơi, hãy nhấp đúp vào file "1_cai_dat.bat" trước để hệ thống cài đặt nhé.
    echo.
    pause
    exit /b 1
)

echo [1/2] Đang kích hoạt môi trường ứng dụng...
call .\venv\Scripts\activate

echo [2/2] Đang khởi động máy chủ Web và mở trình duyệt...
start http://127.0.0.1:8000

echo.
echo ======================================================
echo       ỨNG DỤNG ĐÃ KHỞI ĐỘNG THÀNH CÔNG!
echo ======================================================
echo.
echo   * Địa chỉ web: http://127.0.0.1:8000
echo.
echo   * TÀI KHOẢN ĐĂNG NHẬP MẪU:
echo     - Khách hàng:    SĐT: 0905123456   - MK: 123456
echo     - CSKH:          TK:  cskh         - MK: 123456
echo     - Kỹ thuật viên: TK:  ktv_minh     - MK: 123456
echo     - Trưởng phòng:  TK:  admin        - MK: 123456
echo.
echo   * LƯU Ý QUAN TRỌNG:
echo     - Hãy GIỮ NGUYÊN cửa sổ này trong suốt quá trình dùng app.
echo     - Khi muốn tắt app, chỉ cần đóng cửa sổ này lại hoặc bấm Ctrl + C.
echo ======================================================
echo.

python -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
pause
