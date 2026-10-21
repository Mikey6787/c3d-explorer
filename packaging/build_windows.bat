@echo off
echo ========================================================
echo  Building C3D Explorer Standalone Executable ^& Installer
echo ========================================================

:: Always navigate to the project root (parent directory of packaging/)
cd /d "%~dp0.."

:: 1. Check Python installation
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not in PATH!
    echo Please install Python 3.10+ and check 'Add Python to PATH'.
    pause
    exit /b 1
)

:: 2. Install requirements
echo [1/3] Installing dependencies and PyInstaller...
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install pyinstaller pillow

:: 2.5 Generate multi-resolution Windows app.ico from AppIcon-Dark.png
echo Generating Windows application icon...
python -c "from PIL import Image; img=Image.open('assets/icons/AppIcon-Dark.png').convert('RGBA'); img.save('assets/icons/app.ico', format='ICO', sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])"

:: 3. Run PyInstaller
echo [2/3] Building executable with PyInstaller...
pyinstaller --clean --distpath dist --workpath build packaging\c3d_explorer.spec
if %errorlevel% neq 0 (
    echo [ERROR] PyInstaller build failed!
    pause
    exit /b 1
)

:: 4. Run Inno Setup if installed
echo [3/3] Checking for Inno Setup compiler...
set ISCC="C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if exist %ISCC% (
    echo Compiling Windows Setup Installer...
    %ISCC% packaging\installer.iss
    echo [SUCCESS] Setup installer generated in dist_installer\C3D_Explorer_Windows_Setup.exe
) else (
    echo [INFO] Inno Setup 6 not found at default location.
    echo Standalone executable is available at: dist\C3DExplorer\C3DExplorer.exe
    echo To create the Setup.exe installer, download Inno Setup from https://jrsoftware.org/isdl.php
)

echo ========================================================
echo  Build process complete!
echo ========================================================
pause
