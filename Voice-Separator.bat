@echo off
chcp 65001 >nul
title Voice-Separator
cd /d "%~dp0.."
python app.py
if errorlevel 1 (
    echo.
    echo [오류] 실행 실패. Python과 필요 패키지가 설치되어 있는지 확인하세요.
    echo 먼저 install_and_build.bat 을 실행하세요.
    pause
)
