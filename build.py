"""
빌드 스크립트 - VocalSeparator Mac (.app) / Windows (.exe)
사용법: python3 build.py
"""

import subprocess
import sys
import platform
import os

APP_NAME = "Voice-Separator"


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
        # 불필요 패키지 제외
        "--exclude-module", "scipy",
        "--exclude-module", "matplotlib",
        "--exclude-module", "PIL",
        "--exclude-module", "Pillow",
        "--exclude-module", "noisereduce",
        "--exclude-module", "sklearn",
        "--exclude-module", "pandas",
        "--exclude-module", "notebook",
        "--exclude-module", "IPython",
        "--collect-all", "demucs",
        "--collect-all", "julius",
        "--collect-all", "openunmix",
        "--collect-all", "customtkinter",
        "--collect-all", "tkinterdnd2",
        "--hidden-import", "torch",
        "--hidden-import", "torchaudio",
        "--hidden-import", "demucs",
        "--hidden-import", "demucs.pretrained",
        "--hidden-import", "demucs.hdemucs",
        "--hidden-import", "demucs.htdemucs",
        "--hidden-import", "demucs.apply",
        "--hidden-import", "demucs.states",
        "--hidden-import", "demucs.spec",
        "--hidden-import", "julius",
        "--hidden-import", "soundfile",
        "--hidden-import", "cffi",
        "--hidden-import", "tqdm",
        "--hidden-import", "omegaconf",
        "--hidden-import", "einops",
        "--hidden-import", "customtkinter",
        "--hidden-import", "tkinterdnd2",
        "--hidden-import", "darkdetect",
        "--hidden-import", "numpy",
        "--add-data", f"{dnd_path}{';' if system == 'Windows' else ':'}tkinterdnd2",
        "app.py",
    ]

    if system == "Darwin":
        cmd.extend(["--osx-bundle-identifier", "com.voiceseparator.app"])
        print("Building macOS .app bundle...")
    elif system == "Windows":
        print("Building Windows .exe...")

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
