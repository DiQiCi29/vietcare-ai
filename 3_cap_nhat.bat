@echo off
chcp 65001 > nul
echo ======================================================
echo     VIETCARE AI - CẬP NHẬT PHIÊN BẢN MỚI NHẤT
echo ======================================================
echo.

echo 1. Đang kéo mã nguồn mới nhất từ GitHub về...
git pull origin main
if %errorlevel% neq 0 (
    echo.
    echo [LỖI] Không thể kéo code về. Vui lòng kiểm tra lại kết nối mạng!
    echo.
    pause
    exit /b 1
)

echo.
echo 2. Đang kiểm tra và cập nhật các thư viện mới (nếu có)...
if exist venv (
    call .\venv\Scripts\activate
    pip install -r requirements.txt
)

echo.
echo ======================================================
echo     CẬP NHẬT HOÀN TẤT!
echo     Bạn có thể nhấp đúp vào "2_chay_app.bat" để tiếp tục sử dụng.
echo ======================================================
echo.
pause

