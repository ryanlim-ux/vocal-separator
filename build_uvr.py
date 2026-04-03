"""
빌드 스크립트 - Vocal Separator Pro (UVR/MDX-Net Edition)
Python 3.11 필요: /opt/homebrew/bin/python3.11 build_uvr.py
"""

import subprocess
import sys
import platform
import os

APP_NAME = "VocalSeparatorPro"


def build():
    system = platform.system()

    import tkinterdnd2
    dnd_path = os.path.dirname(tkinterdnd2.__file__)

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name", APP_NAME,
        "--windowed",
        "--onedir",
        "--noconfirm",
        # 패키지 수집
        "--collect-all", "audio_separator",
        "--collect-all", "customtkinter",
        "--collect-all", "tkinterdnd2",
        "--collect-all", "librosa",
        # hidden imports
        "--hidden-import", "torch",
        "--hidden-import", "soundfile",
        "--hidden-import", "cffi",
        "--hidden-import", "numpy",
        "--hidden-import", "scipy",
        "--hidden-import", "onnxruntime",
        "--hidden-import", "customtkinter",
        "--hidden-import", "tkinterdnd2",
        "--hidden-import", "darkdetect",
        "--hidden-import", "audio_separator",
        "--hidden-import", "audio_separator.separator",
        "--hidden-import", "onnx2torch",
        "--hidden-import", "ml_collections",
        "--hidden-import", "beartype",
        "--hidden-import", "rotary_embedding_torch",
        "--add-data", f"{dnd_path}:tkinterdnd2",
        "app_uvr.py",
    ]

    if system == "Darwin":
        cmd.extend(["--osx-bundle-identifier", "com.vocalseparator.pro"])
        print("Building macOS .app bundle (Pro)...")
    elif system == "Windows":
        print("Building Windows .exe (Pro)...")

    print(f"Running PyInstaller...")
    result = subprocess.run(cmd, cwd=os.path.dirname(os.path.abspath(__file__)))

    if result.returncode == 0:
        dist = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dist", APP_NAME)
        if system == "Darwin":
            print(f"\n{'='*50}")
            print(f"  빌드 성공!")
            print(f"  macOS 앱: {dist}.app")
            print(f"  실행: open \"{dist}.app\"")
            print(f"{'='*50}")
        elif system == "Windows":
            print(f"\n빌드 성공! {dist}\\{APP_NAME}.exe")
    else:
        print("빌드 실패!")
        sys.exit(1)


if __name__ == "__main__":
    build()
