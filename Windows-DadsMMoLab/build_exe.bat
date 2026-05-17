@echo off
:: Dad's MMO Lab — Build standalone EXE with PyInstaller
:: Output: dist\DadsMmoLab.exe  (no Python required on target machine)

title Dad's MMO Lab — Build EXE
echo.
echo   Building standalone EXE...
echo.

if not exist "venv\Scripts\python.exe" (
    echo   Run setup.bat first.
    pause
    exit /b 1
)

call venv\Scripts\pip install pyinstaller --quiet

venv\Scripts\pyinstaller ^
    --onefile ^
    --windowed ^
    --name "DadsMmoLab" ^
    --add-data "launcher\assets;assets" ^
    --paths launcher ^
    launcher\main.py

echo.
if exist "dist\DadsMmoLab.exe" (
    echo   =============================================
    echo    Build SUCCESS!
    echo    EXE: dist\DadsMmoLab.exe
    echo   =============================================
) else (
    echo   Build FAILED — check output above.
)
echo.
pause
