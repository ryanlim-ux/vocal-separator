@echo off
chcp 65001 >nul
title 패키지 설치

echo ============================================
echo   필수 패키지 설치 (빌드 없이 .bat으로 실행할 때)
echo ============================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo [오류] Python이 설치되어 있지 않습니다.
    echo https://www.python.org/downloads/ 에서 Python 3.10 이상을 설치하세요.
    pause
    exit /b 1
)

echo [1/3] 기본 패키지 설치 중...
pip install demucs torch torchaudio soundfile customtkinter tkinterdnd2 numpy

echo [2/3] Pro 추가 패키지 설치 중...
pip install audio-separator onnxruntime

echo [3/3] ffmpeg 확인...
ffmpeg -version >nul 2>&1
if errorlevel 1 (
    echo.
    echo [주의] ffmpeg가 설치되어 있지 않습니다.
    echo https://ffmpeg.org/download.html 에서 다운로드 후 PATH에 추가하세요.
    echo 또는: winget install ffmpeg
)

echo.
echo ============================================
echo   설치 완료!
echo   Voice-Separator.bat 또는 Vocal-Separator.bat 으로 실행하세요.
echo ============================================
pause
