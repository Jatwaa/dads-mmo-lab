@echo off
:: Dad's MMO Lab — Windows Launcher Setup
:: Run this once to create the virtual environment and install dependencies.

title Dad's MMO Lab — Setup
echo.
echo   =============================================
echo    Dad's MMO Lab — Windows Launcher Setup
echo   =============================================
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo   ERROR: Python not found.
    echo   Download from https://www.python.org/downloads/
    echo   Make sure to check "Add Python to PATH" during install.
    pause
    exit /b 1
)

echo   Python found.
echo.

:: Create venv
if not exist "venv\" (
    echo   Creating virtual environment...
    python -m venv venv
) else (
    echo   Virtual environment already exists.
)

:: Install dependencies
echo.
echo   Installing dependencies...
call venv\Scripts\pip install --upgrade pip --quiet
call venv\Scripts\pip install -r requirements.txt

echo.
echo   =============================================
echo    Setup complete!
echo    Run  launch.bat  to start the launcher.
echo   =============================================
echo.
pause
