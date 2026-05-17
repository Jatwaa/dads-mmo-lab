@echo off
:: Dad's MMO Lab — Windows Launcher
:: Double-click this file (or add it to Steam as a Non-Steam Game).

title Dad's MMO Lab

if not exist "venv\Scripts\python.exe" (
    echo   Run setup.bat first to install dependencies.
    pause
    exit /b 1
)

venv\Scripts\python launcher\main.py
