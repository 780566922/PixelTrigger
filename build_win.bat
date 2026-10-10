@echo off
REM ============================================================
REM  PixelTrigger - Windows one-click build script
REM  Usage : double-click this file, or run  build_win.bat
REM  Output: dist\PixelTrigger.exe  (single portable file)
REM  Requires: Python 3.10+ installed and available as "python"
REM ============================================================
setlocal
cd /d "%~dp0"

echo [1/4] Checking Python...
where python >nul 2>nul
if errorlevel 1 (
    echo ERROR: Python not found. Install Python 3.10+ and tick "Add Python to PATH".
    pause
    exit /b 1
)
python --version

echo.
echo [2/4] Preparing virtual environment...
if not exist ".build_win\venv" (
    python -m venv .build_win\venv
)
call ".build_win\venv\Scripts\activate.bat"

echo.
echo [3/4] Installing dependencies...
python -m pip install --upgrade pip -q
python -m pip install -q pyinstaller Pillow

echo.
echo [4/4] Building EXE (may take a few minutes)...
python gen_version.py
pyinstaller --noconfirm --clean --onefile --windowed ^
    --name PixelTrigger ^
    --icon icon.ico ^
    --add-data "donation.png;." ^
    --add-data "icon.ico;." ^
    --add-data "version.txt;." ^
    --hidden-import platform_backend ^
    --hidden-import PIL.ImageGrab ^
    color_watcher.py

if errorlevel 1 (
    echo.
    echo BUILD FAILED
    pause
    exit /b 1
)

echo.
echo ============================================================
echo  Done!  Output: dist\PixelTrigger.exe
echo ============================================================
pause
