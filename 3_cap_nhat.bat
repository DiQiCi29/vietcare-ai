@echo off
chcp 65001 > nul
title VIETCARE AI - CAP NHAT PHIEN BAN MOI
echo ======================================================
echo       VIETCARE AI - CẬP NHẬT PHIÊN BẢN MỚI
echo ======================================================
echo.

echo [1/2] Đang tải những cập nhật mới nhất từ GitHub về máy...
git pull origin main
if %errorlevel% neq 0 (
    echo.
    echo [LỖI] Không thể tải bản cập nhật!
    echo Vui lòng kiểm tra lại kết nối Internet và thử lại nhé.
    echo.
    pause
    exit /b 1
)

echo.
echo [2/2] Kiểm tra và cập nhật các gói thư viện mới (nếu có)...
if exist venv (
    call .\venv\Scripts\activate
    pip install -r requirements.txt
)

echo.
echo ======================================================
echo       CẬP NHẬT HOÀN TẤT THÀNH CÔNG!
echo ======================================================
echo.
echo   * Mã nguồn và các tính năng mới đã được đồng bộ vào máy của bạn.
echo   * Bây giờ bạn có thể nhấp đúp vào file "2_chay_app.bat" để mở app.
echo ======================================================
echo.
pause
