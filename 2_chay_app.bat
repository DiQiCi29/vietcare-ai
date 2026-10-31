@echo off
chcp 65001 > nul
echo ======================================================
echo     VIETCARE AI - KHỞI ĐỘNG HỆ THỐNG
echo ======================================================
echo.

if not exist venv (
    echo [LOI] Chua tim thay thu muc venv!
    echo Vui long nhap dup vao file "1_cai_dat.bat" truoc de cai dat.
    echo.
    pause
    exit /b 1
)

echo 1. Dang kich hoat moi truong ao...
call .\venv\Scripts\activate

echo 2. Dang khoi dong may chu web va mo trinh duyet...
start http://127.0.0.1:8000

echo.
echo ======================================================
echo     HE THONG VIETCARE AI DANG CHAY TAI:
echo     http://127.0.0.1:8000
echo.
echo     Giữ nguyen cua so nay khi dang su dung.
echo     Nhan to hop phim Ctrl + C de dung ung dung.
echo ======================================================
echo.

python -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
pause

