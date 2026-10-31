@echo off
chcp 65001 > nul
echo ======================================================
echo     VIETCARE AI - CÀI ĐẶT HỆ THỐNG TỰ ĐỘNG
echo ======================================================
echo.

:: 1. Kiem tra Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [LOI] May tinh chua cai dat Python hoac chua tick chon "Add python.exe to PATH"!
    echo Vui long tai va cai dat Python tu https://www.python.org/
    echo.
    pause
    exit /b 1
)

echo 1. Dang khoi tao moi truong ao (venv)...
if not exist venv (
    python -m venv venv
    echo - Da tao moi truong ao venv thanh cong.
) else (
    echo - Moi truong ao venv da ton tai.
)

echo.
echo 2. Dang kich hoat moi truong va cai dat cac thu vien can thiet...
call .\venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt

echo.
echo 3. Thiet lap file cau hinh moi truong (.env)...
if not exist .env (
    copy .env.example .env
    echo - Da tao file .env tu mau .env.example.
) else (
    echo - File .env da ton tai.
)

echo.
echo ======================================================
echo     CAI DAT HOAN TAT!
echo     Bay gio ban co the nhap dup vao "2_chay_app.bat" de mo ung dung.
echo ======================================================
echo.
pause

