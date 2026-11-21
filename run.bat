@echo off
title Intel Arc Optimizer - Shader Cleaner

cd /d "%~dp0"

:: Check administrator privileges
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [i] Requesting administrator privileges...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

:: Launch via py or python
where py >nul 2>&1
if %errorlevel% equ 0 (
    py -3 "%~dp0main.py"
    goto finish
)

where python >nul 2>&1
if %errorlevel% equ 0 (
    python "%~dp0main.py"
    goto finish
)

echo [ERROR] Python not found. Please install Python 3.10+ and PySide6:
echo pip install PySide6
pause
exit /b

:finish
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Application exited with error code %errorlevel%.
    pause
)
