@echo off
chcp 65001 >nul
title Voice-Separator & Vocal-Separator Windows Build

echo ============================================
echo   Voice-Separator / Vocal-Separator
echo   Windows 빌드 스크립트
echo ============================================
echo.

:: Python 확인
python --version >nul 2>&1
if errorlevel 1 (
    echo [오류] Python이 설치되어 있지 않습니다.
    echo https://www.python.org/downloads/ 에서 Python 3.10 이상을 설치하세요.
    echo 설치 시 "Add Python to PATH" 체크를 반드시 해주세요.
    pause
    exit /b 1
)

echo [1/4] Python 패키지 설치 중...
pip install demucs torch torchaudio soundfile customtkinter tkinterdnd2 numpy pyinstaller >nul 2>&1
if errorlevel 1 (
    echo [경고] 일부 패키지 설치 실패. 계속 진행합니다...
)

echo [2/4] Voice-Separator (일반판) 빌드 중...
cd /d "%~dp0.."
python -m PyInstaller --name "Voice-Separator" --windowed --onedir --noconfirm ^
    --exclude-module scipy --exclude-module matplotlib --exclude-module PIL ^
    --exclude-module Pillow --exclude-module noisereduce ^
    --collect-all demucs --collect-all julius --collect-all openunmix ^
    --collect-all customtkinter --collect-all tkinterdnd2 ^
    --hidden-import torch --hidden-import torchaudio --hidden-import demucs ^
    --hidden-import demucs.pretrained --hidden-import demucs.hdemucs ^
    --hidden-import demucs.htdemucs --hidden-import demucs.apply ^
    --hidden-import demucs.states --hidden-import demucs.spec ^
    --hidden-import julius --hidden-import soundfile --hidden-import cffi ^
    --hidden-import tqdm --hidden-import omegaconf --hidden-import einops ^
    --hidden-import customtkinter --hidden-import tkinterdnd2 ^
    --hidden-import darkdetect --hidden-import numpy ^
    app.py
if errorlevel 1 (
    echo [오류] Voice-Separator 빌드 실패!
    pause
    exit /b 1
)
echo [OK] Voice-Separator 빌드 성공!

echo.
echo [3/4] Vocal-Separator (Pro) 추가 패키지 설치 중...
pip install audio-separator onnxruntime >nul 2>&1

echo [4/4] Vocal-Separator (Pro) 빌드 중...
python -m PyInstaller --name "Vocal-Separator" --windowed --onedir --noconfirm ^
    --collect-all audio_separator --collect-all customtkinter --collect-all tkinterdnd2 ^
    --collect-all librosa ^
    --hidden-import torch --hidden-import soundfile --hidden-import cffi ^
    --hidden-import numpy --hidden-import scipy --hidden-import onnxruntime ^
    --hidden-import customtkinter --hidden-import tkinterdnd2 --hidden-import darkdetect ^
    --hidden-import audio_separator --hidden-import audio_separator.separator ^
    --hidden-import onnx2torch --hidden-import ml_collections ^
    --hidden-import beartype --hidden-import rotary_embedding_torch ^
    app_uvr.py
if errorlevel 1 (
    echo [오류] Vocal-Separator 빌드 실패!
    pause
    exit /b 1
)
echo [OK] Vocal-Separator 빌드 성공!

:: 빌드 잔재 정리
rmdir /s /q build 2>nul
del /q *.spec 2>nul

echo.
echo ============================================
echo   빌드 완료!
echo.
echo   Voice-Separator:  dist\Voice-Separator\Voice-Separator.exe
echo   Vocal-Separator:  dist\Vocal-Separator\Vocal-Separator.exe
echo ============================================
pause
