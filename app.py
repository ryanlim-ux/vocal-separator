"""
Voice-Separator - 보이스/배경음악 분리 앱
demucs (htdemucs) 모델을 사용하여 Voice / Instrumental 2-stem 분리
"""

import os
import sys
import threading
import tkinter as tk
from pathlib import Path
import subprocess
import shutil
import tempfile
import traceback
import numpy as np

import customtkinter as ctk
from tkinterdnd2 import TkinterDnD, DND_FILES

SUPPORTED_FORMATS = {".mp3", ".wav", ".flac", ".ogg", ".m4a", ".aac", ".wma", ".aiff", ".mp4", ".webm"}

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

C = {
    "bg":         "#0f0f1a",
    "card":       "#1a1a2e",
    "card_hover": "#222240",
    "accent":     "#6c5ce7",
    "accent_h":   "#7f71ef",
    "accent2":    "#e94560",
    "text":       "#f0f0f5",
    "dim":        "#6b7394",
    "success":    "#00cec9",
    "error":      "#ff6b6b",
    "border":     "#2d2d50",
    "drop_bg":    "#12122a",
    "drop_active":"#1e1e40",
    "entry":      "#12122a",
}


def _find_ffmpeg():
    # 0) exe와 같은 폴더 (PyInstaller 번들)
    if getattr(sys, 'frozen', False):
        exe_dir = os.path.dirname(sys.executable)
        bundled = os.path.join(exe_dir, "ffmpeg.exe")
        if os.path.isfile(bundled):
            return bundled
    # 1) shutil.which로 PATH에서 찾기
    found = shutil.which("ffmpeg")
    if found:
        return found
    # 2) 잘 알려진 경로 직접 확인
    candidates = []
    if sys.platform == "win32":
        candidates = [
            r"C:\ffmpeg\bin\ffmpeg.exe",
            r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
        ]
        # winget 설치 경로 탐색
        winget_base = os.path.join(os.environ.get("LOCALAPPDATA", ""),
                                   "Microsoft", "WinGet", "Packages")
        if os.path.isdir(winget_base):
            for d in os.listdir(winget_base):
                if "ffmpeg" in d.lower():
                    bin_path = os.path.join(winget_base, d)
                    for root, dirs, files in os.walk(bin_path):
                        if "ffmpeg.exe" in files:
                            candidates.append(os.path.join(root, "ffmpeg.exe"))
    else:
        candidates = ["/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg", "/usr/bin/ffmpeg"]
    for p in candidates:
        if os.path.isfile(p):
            return p
    return "ffmpeg"


FFMPEG = _find_ffmpeg()

_ffmpeg_dir = os.path.dirname(FFMPEG)
if _ffmpeg_dir and _ffmpeg_dir not in os.environ.get("PATH", ""):
    os.environ["PATH"] = _ffmpeg_dir + os.pathsep + os.environ.get("PATH", "")


class DnDCTk(ctk.CTk, TkinterDnD.DnDWrapper):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.TkdndVersion = TkinterDnD._require(self)


class VoiceSeparatorApp:
    def __init__(self):
        self.root = DnDCTk()
        self.root.title("Voice-Separator | 음성 분리기")
        self.root.geometry("900x720")
        self.root.configure(fg_color=C["bg"])
        self.root.minsize(820, 680)

        self.files = []
        self.output_dir = tk.StringVar(value=str(Path.home() / "Downloads"))
        self.output_format = tk.StringVar(value="wav")
        self.is_processing = False
        self.should_stop = False

        self.suffix_voice = tk.StringVar(value="_voice")
        self.suffix_inst = tk.StringVar(value="_inst")
        self.save_to_source = tk.BooleanVar(value=True)

        self._build_ui()

    def run(self):
        self.root.mainloop()

    def _card(self, parent, **kwargs):
        return ctk.CTkFrame(parent, fg_color=C["card"], corner_radius=16,
                            border_width=1, border_color=C["border"], **kwargs)

    def _label(self, parent, text, size=13, bold=False, color=None):
        weight = "bold" if bold else "normal"
        return ctk.CTkLabel(parent, text=text,
                            font=ctk.CTkFont(size=size, weight=weight),
                            text_color=color or C["text"])

    def _build_ui(self):
        main = ctk.CTkScrollableFrame(self.root, fg_color=C["bg"],
                                       scrollbar_button_color=C["border"],
                                       scrollbar_button_hover_color=C["dim"])
        main.pack(fill="both", expand=True, padx=20, pady=16)

        header = ctk.CTkFrame(main, fg_color="transparent")
        header.pack(fill="x", pady=(0, 20))
        self._label(header, "Voice-Separator | 음성 분리기", size=28, bold=True).pack(side="left")
        self._label(header, "Voice / Instrumental Splitter", size=13,
                    color=C["dim"]).pack(side="left", padx=(12, 0), pady=(8, 0))

        self._build_file_section(main)
        self._build_output_section(main)
        self._build_action_section(main)

    # ─── 파일 섹션 ───

    def _build_file_section(self, parent):
        card = self._card(parent)
        card.pack(fill="x", pady=(0, 12))
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=20, pady=16)

        top = ctk.CTkFrame(inner, fg_color="transparent")
        top.pack(fill="x")
        self._label(top, "입력 파일", size=15, bold=True).pack(side="left")
        self.file_count_label = self._label(top, "0개 선택됨", size=13, color=C["accent"])
        self.file_count_label.pack(side="right")

        self.drop_frame = ctk.CTkFrame(inner, fg_color=C["drop_bg"], corner_radius=12,
                                        border_width=2, border_color=C["border"], height=120)
        self.drop_frame.pack(fill="x", pady=(12, 0))
        self.drop_frame.pack_propagate(False)
        self.drop_label = self._label(self.drop_frame,
                                       "여기에 오디오 파일을 드래그하여 추가\n또는 아래 버튼으로 파일/폴더 선택",
                                       size=13, color=C["dim"])
        self.drop_label.pack(expand=True)

        self.drop_frame.drop_target_register(DND_FILES)
        self.drop_frame.dnd_bind("<<DropEnter>>", self._on_drop_enter)
        self.drop_frame.dnd_bind("<<DropLeave>>", self._on_drop_leave)
        self.drop_frame.dnd_bind("<<Drop>>", self._on_drop)
        self.root.drop_target_register(DND_FILES)
        self.root.dnd_bind("<<Drop>>", self._on_drop)

        btn_row = ctk.CTkFrame(inner, fg_color="transparent")
        btn_row.pack(fill="x", pady=(10, 0))
        for text, cmd in [("파일 추가", self._add_files), ("폴더 추가", self._add_folder),
                          ("전체 삭제", self._clear_files)]:
            hover = C["accent2"] if text == "전체 삭제" else C["border"]
            ctk.CTkButton(btn_row, text=text, width=100, height=34, corner_radius=8,
                          fg_color=C["card_hover"], hover_color=hover,
                          text_color=C["text"], font=ctk.CTkFont(size=12),
                          command=cmd).pack(side="left", padx=(0, 6))

        self.file_listbox = tk.Listbox(
            inner, height=4, bg=C["drop_bg"], fg=C["text"],
            selectbackground=C["accent"], selectforeground="white",
            font=("Helvetica", 11), borderwidth=0, highlightthickness=0,
            relief="flat", activestyle="none")
        self.file_listbox.pack(fill="x", pady=(10, 0))
        self.file_listbox.bind("<Delete>", self._delete_selected)
        self.file_listbox.bind("<BackSpace>", self._delete_selected)

    # ─── 출력 설정 ───

    def _build_output_section(self, parent):
        card = self._card(parent)
        card.pack(fill="x", pady=(0, 12))
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=20, pady=16)

        self._label(inner, "출력 설정", size=15, bold=True).pack(anchor="w")

        src_row = ctk.CTkFrame(inner, fg_color="transparent")
        src_row.pack(fill="x", pady=(12, 0))
        ctk.CTkCheckBox(src_row, text="각 파일의 원본 위치에 저장",
                        variable=self.save_to_source, font=ctk.CTkFont(size=12),
                        fg_color=C["accent"], hover_color=C["accent_h"],
                        border_color=C["border"], text_color=C["text"],
                        command=self._on_source_toggle).pack(side="left")

        self.folder_frame = ctk.CTkFrame(inner, fg_color="transparent")
        self.folder_frame.pack(fill="x", pady=(8, 0))
        self._label(self.folder_frame, "저장 폴더", size=12, color=C["dim"]).pack(anchor="w")
        fr = ctk.CTkFrame(self.folder_frame, fg_color="transparent")
        fr.pack(fill="x", pady=(4, 0))
        self.dir_entry = ctk.CTkEntry(fr, textvariable=self.output_dir, height=36,
                     corner_radius=8, fg_color=C["entry"], border_color=C["border"],
                     text_color=C["text"], font=ctk.CTkFont(size=12))
        self.dir_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.dir_change_btn = ctk.CTkButton(fr, text="변경", width=70, height=36,
                      corner_radius=8, fg_color=C["card_hover"],
                      hover_color=C["border"], text_color=C["text"],
                      font=ctk.CTkFont(size=12), command=self._choose_output_dir)
        self.dir_change_btn.pack(side="left")

        if self.save_to_source.get():
            self.dir_entry.configure(state="disabled")
            self.dir_change_btn.configure(state="disabled")

        row2 = ctk.CTkFrame(inner, fg_color="transparent")
        row2.pack(fill="x", pady=(14, 0))

        fmt_f = ctk.CTkFrame(row2, fg_color="transparent")
        fmt_f.pack(side="left")
        self._label(fmt_f, "출력 포맷", size=12, color=C["dim"]).pack(anchor="w")
        ctk.CTkOptionMenu(fmt_f, variable=self.output_format,
                          values=["wav", "mp3", "flac"], width=90, height=34,
                          corner_radius=8, fg_color=C["entry"],
                          button_color=C["card_hover"], button_hover_color=C["border"],
                          dropdown_fg_color=C["card"], dropdown_hover_color=C["accent"],
                          font=ctk.CTkFont(size=12)).pack(pady=(4, 0))

        suf_f = ctk.CTkFrame(row2, fg_color="transparent")
        suf_f.pack(side="left", fill="x", expand=True, padx=(24, 0))
        self._label(suf_f, "파일명 접미사 (원본파일명 + 접미사.포맷)",
                    size=12, color=C["dim"]).pack(anchor="w")

        s_row = ctk.CTkFrame(suf_f, fg_color="transparent")
        s_row.pack(fill="x", pady=(4, 0))
        for lbl, var in [("Voice", self.suffix_voice), ("Inst", self.suffix_inst)]:
            self._label(s_row, lbl, size=11).pack(side="left", padx=(10, 0))
            ctk.CTkEntry(s_row, textvariable=var, width=80, height=28,
                         corner_radius=6, fg_color=C["entry"],
                         border_color=C["border"], text_color=C["text"],
                         font=ctk.CTkFont(size=11)).pack(side="left", padx=(4, 0))

        self.preview_label = self._label(inner, "", size=11, color=C["dim"])
        self.preview_label.pack(anchor="w", pady=(10, 0))
        self._update_preview()
        for var in (self.suffix_voice, self.suffix_inst):
            var.trace_add("write", lambda *_: self._update_preview())

    # ─── 실행 ───

    def _build_action_section(self, parent):
        card = self._card(parent)
        card.pack(fill="x", pady=(0, 12))
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=20, pady=16)

        self.progress_var = tk.DoubleVar(value=0)
        self.progress_bar = ctk.CTkProgressBar(inner, variable=self.progress_var,
                                                height=8, corner_radius=4,
                                                fg_color=C["drop_bg"],
                                                progress_color=C["accent"])
        self.progress_bar.pack(fill="x")
        self.progress_bar.set(0)

        self.status_label = self._label(inner, "대기 중", size=12, color=C["dim"])
        self.status_label.pack(anchor="w", pady=(8, 12))

        btn_row = ctk.CTkFrame(inner, fg_color="transparent")
        btn_row.pack(fill="x")

        self.start_btn = ctk.CTkButton(
            btn_row, text="분리 시작", width=140, height=42, corner_radius=10,
            fg_color=C["accent"], hover_color=C["accent_h"],
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self._start_processing)
        self.start_btn.pack(side="left", padx=(0, 8))

        self.stop_btn = ctk.CTkButton(
            btn_row, text="중지", width=80, height=42, corner_radius=10,
            fg_color=C["card_hover"], hover_color=C["accent2"],
            font=ctk.CTkFont(size=13), state="disabled",
            command=self._stop_processing)
        self.stop_btn.pack(side="left")

        ctk.CTkButton(
            btn_row, text="출력 폴더 열기", width=130, height=42, corner_radius=10,
            fg_color=C["card_hover"], hover_color=C["border"],
            font=ctk.CTkFont(size=13),
            command=self._open_output_dir).pack(side="right")

    def _update_preview(self):
        ex = "MySong"
        names = [f"{ex}{self.suffix_voice.get()}.wav",
                 f"{ex}{self.suffix_inst.get()}.wav"]
        self.preview_label.configure(text=f"예시:  {' / '.join(names)}")

    # ─── DnD ───

    def _on_drop_enter(self, event):
        self.drop_frame.configure(fg_color=C["drop_active"], border_color=C["accent"])

    def _on_drop_leave(self, event):
        self.drop_frame.configure(fg_color=C["drop_bg"], border_color=C["border"])

    def _on_drop(self, event):
        self.drop_frame.configure(fg_color=C["drop_bg"], border_color=C["border"])
        raw = event.data
        paths = []
        i = 0
        while i < len(raw):
            if raw[i] == '{':
                end = raw.index('}', i)
                paths.append(raw[i+1:end])
                i = end + 2
            elif raw[i] == ' ':
                i += 1
            else:
                end = raw.find(' ', i)
                if end == -1:
                    end = len(raw)
                paths.append(raw[i:end])
                i = end + 1
        audio_files = []
        for p in paths:
            p = p.strip()
            if not p:
                continue
            if os.path.isdir(p):
                for rd, _, fns in os.walk(p):
                    for f in fns:
                        if Path(f).suffix.lower() in SUPPORTED_FORMATS:
                            audio_files.append(os.path.join(rd, f))
            elif Path(p).suffix.lower() in SUPPORTED_FORMATS:
                audio_files.append(p)
        if audio_files:
            self._insert_files(audio_files)

    # ─── 파일 관리 ───

    def _add_files(self):
        from tkinter import filedialog
        paths = filedialog.askopenfilenames(
            title="오디오 파일 선택",
            filetypes=[("Audio", " ".join(f"*{e}" for e in SUPPORTED_FORMATS)), ("All", "*.*")])
        self._insert_files(paths)

    def _add_folder(self):
        from tkinter import filedialog
        folder = filedialog.askdirectory(title="오디오 폴더 선택")
        if not folder:
            return
        paths = []
        for rd, _, fns in os.walk(folder):
            for f in fns:
                if Path(f).suffix.lower() in SUPPORTED_FORMATS:
                    paths.append(os.path.join(rd, f))
        if paths:
            self._insert_files(paths)

    def _insert_files(self, paths):
        existing = set(self.files)
        for p in paths:
            if p not in existing:
                self.files.append(p)
                self.file_listbox.insert(tk.END, f"  {os.path.basename(p)}")
        self.file_count_label.configure(text=f"{len(self.files)}개 선택됨")
        self.drop_label.configure(text=f"{len(self.files)}개 파일 준비됨  —  추가 파일을 드래그하세요")

    def _clear_files(self):
        self.files.clear()
        self.file_listbox.delete(0, tk.END)
        self.file_count_label.configure(text="0개 선택됨")
        self.drop_label.configure(text="여기에 오디오 파일을 드래그하여 추가\n또는 아래 버튼으로 파일/폴더 선택")

    def _delete_selected(self, event=None):
        for idx in reversed(self.file_listbox.curselection()):
            self.files.pop(idx)
            self.file_listbox.delete(idx)
        self.file_count_label.configure(text=f"{len(self.files)}개 선택됨")

    def _on_source_toggle(self):
        state = "disabled" if self.save_to_source.get() else "normal"
        self.dir_entry.configure(state=state)
        self.dir_change_btn.configure(state=state)

    def _choose_output_dir(self):
        from tkinter import filedialog
        d = filedialog.askdirectory(title="출력 폴더 선택")
        if d:
            self.output_dir.set(d)

    def _open_output_dir(self):
        d = self.output_dir.get()
        if os.path.isdir(d):
            if sys.platform == "darwin":
                subprocess.Popen(["open", d])
            elif sys.platform == "win32":
                os.startfile(d)
            else:
                subprocess.Popen(["xdg-open", d])

    # ─── 오디오 변환 ───

    def _convert_to_wav(self, src, dst):
        cmd = [FFMPEG, "-y", "-i", src, "-ar", "44100", "-ac", "2", "-sample_fmt", "s16", dst]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg 변환 실패: {result.stderr[:500]}")

    def _convert_from_wav(self, src, dst, fmt):
        if fmt == "wav":
            shutil.copy2(str(src), str(dst))
            return
        codec_map = {"mp3": "libmp3lame", "flac": "flac"}
        codec = codec_map.get(fmt, fmt)
        cmd = [FFMPEG, "-y", "-i", str(src), "-acodec", codec]
        if fmt == "mp3":
            cmd.extend(["-b:a", "320k"])
        cmd.append(str(dst))
        subprocess.run(cmd, capture_output=True, text=True, timeout=300)

    # ─── 처리 ───

    def _set_status(self, text, color=None):
        self.status_label.configure(text=text, text_color=color or C["dim"])

    def _start_processing(self):
        if not self.files:
            return
        self.is_processing = True
        self.should_stop = False
        self.start_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self.progress_bar.set(0)
        threading.Thread(target=self._process_files, daemon=True).start()

    def _stop_processing(self):
        self.should_stop = True
        self.root.after(0, self._set_status, "중지 요청됨...", C["error"])

    def _process_files(self):
        total = len(self.files)
        use_source = self.save_to_source.get()
        output_base = self.output_dir.get()
        if not use_source:
            os.makedirs(output_base, exist_ok=True)
        fmt = self.output_format.get()
        ok, fail = 0, 0

        for i, filepath in enumerate(self.files):
            if self.should_stop:
                self.root.after(0, self._set_status, f"중지됨 ({ok}/{total} 완료)", C["error"])
                break
            basename = os.path.basename(filepath)
            filename = Path(filepath).stem
            out_dir = os.path.dirname(filepath) if use_source else output_base
            self.root.after(0, self._set_status,
                           f"처리 중 ({i+1}/{total}): {basename}", C["accent"])
            self.root.after(0, self.progress_bar.set, i / total)
            try:
                self._separate_track(filepath, filename, out_dir, fmt)
                ok += 1
            except Exception as e:
                fail += 1
                print(f"Error [{basename}]: {e}", file=sys.stderr)
                traceback.print_exc()

        if not self.should_stop:
            self.root.after(0, self.progress_bar.set, 1.0)
            if fail == 0:
                self.root.after(0, self._set_status, f"완료! {ok}개 모두 성공", C["success"])
            else:
                self.root.after(0, self._set_status,
                               f"완료! {ok}개 성공, {fail}개 실패", C["error"])
        self.is_processing = False
        self.root.after(0, lambda: self.start_btn.configure(state="normal"))
        self.root.after(0, lambda: self.stop_btn.configure(state="disabled"))

    def _separate_track(self, filepath, filename, output_base, fmt):
        """demucs htdemucs로 Voice/Instrumental 2-stem 분리"""
        import torch
        import soundfile as sf
        from demucs.pretrained import get_model
        from demucs.apply import apply_model

        with tempfile.TemporaryDirectory() as tmp_dir:
            wav_path = os.path.join(tmp_dir, "input.wav")
            self._convert_to_wav(filepath, wav_path)

            model = get_model("htdemucs")
            model.eval()
            device = "cpu"
            if torch.cuda.is_available():
                device = "cuda"
            elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                device = "mps"
            model.to(device)

            data, sr = sf.read(wav_path, dtype="float32")
            waveform = torch.tensor(data.T, dtype=torch.float32)

            if waveform.ndim == 1:
                waveform = waveform.unsqueeze(0).repeat(2, 1)
            elif waveform.shape[0] == 1:
                waveform = waveform.repeat(2, 1)

            if sr != model.samplerate:
                import torchaudio
                waveform = torchaudio.transforms.Resample(sr, model.samplerate)(waveform)
                sr = model.samplerate

            ref = waveform.mean(0)
            waveform_norm = (waveform - ref.mean()) / ref.std()
            mix = waveform_norm.unsqueeze(0).to(device)

            with torch.no_grad():
                sources = apply_model(model, mix, device=device)

            sources = sources[0] * ref.std() + ref.mean()

            source_map = {}
            for idx, name in enumerate(model.sources):
                source_map[name] = sources[idx].cpu().numpy()

            voice_np = source_map["vocals"]
            inst_np = source_map["drums"] + source_map["bass"] + source_map["other"]

            os.makedirs(output_base, exist_ok=True)

            def save_audio(audio_np, out_path):
                tmp_wav = os.path.join(tmp_dir, os.path.basename(out_path) + ".tmp.wav")
                sf.write(tmp_wav, audio_np.T, sr)
                self._convert_from_wav(tmp_wav, out_path, fmt)

            save_audio(voice_np,
                       os.path.join(output_base, f"{filename}{self.suffix_voice.get()}.{fmt}"))
            save_audio(inst_np,
                       os.path.join(output_base, f"{filename}{self.suffix_inst.get()}.{fmt}"))


def main():
    app = VoiceSeparatorApp()
    app.run()


if __name__ == "__main__":
    main()
