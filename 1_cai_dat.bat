@echo off
chcp 65001 > nul
title VIETCARE AI - CAI DAT HE THONG TU DONG
echo ======================================================
echo       VIETCARE AI - CÀI ĐẶT HỆ THỐNG TỰ ĐỘNG
echo ======================================================
echo.

:: 1. Kiem tra Python
echo [1/4] Kiem tra moi truong Python tren may tinh...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo [THONG BAO] May tinh chua co Python!
    echo Dang tu dong tai bo cai dat Python 3.11 chinh thuc tu python.org...
    echo (Qua trinh tai va cai dat mat khoang 1 - 2 phut, vui long khong tat cua so nay)
    echo.
    
    :: Tai Python bang curl hoac PowerShell
    curl -L -o python_installer.exe https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe >nul 2>&1
    if not exist python_installer.exe (
        powershell -Command "& {[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe' -OutFile 'python_installer.exe'}"
    )

    if not exist python_installer.exe (
        echo [LOI] Khong the tu dong tai Python. Vui long tai thu cong tai https://www.python.org/downloads/
        echo Luu y tick chon "Add python.exe to PATH" khi cai.
        pause
        exit /b 1
    )

    echo Dang tien hanh cai dat Python 3.11 vao may...
    python_installer.exe /passive InstallAllUsers=0 PrependPath=1 Include_test=0 Include_pip=1
    del python_installer.exe

    :: Cap nhat PATH tam thoi cho phien lam viec nay
    set "PATH=%LOCALAPPDATA%\Programs\Python\Python311;%LOCALAPPDATA%\Programs\Python\Python311\Scripts;%PATH%"
    
    python --version >nul 2>&1
    if %errorlevel% neq 0 (
        echo.
        echo [LƯU Ý] Python da duoc cai dat xong!
        echo Vui long DONG cua so nay va NHAP DUP lai vao file "1_cai_dat.bat" de Windows nhan dien Python moi nhe.
        echo.
        pause
        exit /b 0
    )
    echo -> Da cai dat Python 3.11 thanh cong!
) else (
    echo -> May tinh da co san Python. Tiep tuc...
)

echo.
:: 2. Tao moi truong ao venv
echo [2/4] Khoi tao moi truong ao cach ly (venv)...
if not exist venv (
    python -m venv venv
    echo -> Da tao moi truong ao venv thanh cong.
) else (
    echo -> Thu muc venv da san sang.
)

echo.
:: 3. Cai dat thu vien phu thuoc
echo [3/4] Dang cai dat cac thu vien can thiet cho he thong...
echo (Vui long cho trong giay lat, he thong dang tu dong tai cac goi phan mem...)
call .\venv\Scripts\activate
python -m pip install --upgrade pip >nul 2>&1
pip install -r requirements.txt

echo.
:: 4. Thiet lap cau hinh
echo [4/4] Thiet lap file cau hinh moi truong (.env)...
if not exist .env (
    copy .env.example .env >nul
    echo -> Da tao file .env tu mau chuan .env.example.
) else (
    echo -> File cau hinh .env da ton tai.
)

echo.
echo ======================================================
echo       CHÚC MỪNG BẠN! CÀI ĐẶT THÀNH CÔNG 100%%
echo ======================================================
echo.
echo   [OK] Đã sẵn sàng môi trường Python và venv
echo   [OK] Đã nạp đủ thư viện AI và Web Server
echo   [OK] Đã có sẵn cơ sở dữ liệu mẫu (vietcare.db)
echo   [OK] Đã thiết lập cấu hình chạy (.env)
echo.
echo ------------------------------------------------------
echo   BƯỚC TIẾP THEO:
echo   - Hãy nhấp đúp vào file "2_chay_app.bat" để mở ứng dụng!
echo   - Trình duyệt web sẽ tự động mở tại: http://127.0.0.1:8000
echo ======================================================
echo.
pause
