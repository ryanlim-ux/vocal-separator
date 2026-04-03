"""
Vocal-Separator (UVR/MDX-Net + Demucs 6-Stem Edition)

모드 1 (2-Stem): MDX-Net → Vocal / Inst
모드 2 (Separation): Demucs htdemucs_6s → Vocal, Sub Vocal, Drums, Bass, Guitar, Piano, Other
    - 체크된 악기만 개별 파일로 출력
    - 체크 해제된 악기는 Inst로 통합
    - Vocal, Sub Vocal, Inst는 필수 (항상 출력)
"""

import multiprocessing
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
import logging

import customtkinter as ctk
from tkinterdnd2 import TkinterDnD, DND_FILES

logging.getLogger("audio_separator").setLevel(logging.WARNING)

SUPPORTED_FORMATS = {".mp3", ".wav", ".flac", ".ogg", ".m4a", ".aac", ".wma", ".aiff", ".mp4", ".webm"}

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

C = {
    "bg":         "#0f0f1a",
    "card":       "#1a1a2e",
    "card_hover": "#222240",
    "accent":     "#00b894",
    "accent_h":   "#00d9a6",
    "accent2":    "#e94560",
    "text":       "#f0f0f5",
    "dim":        "#6b7394",
    "success":    "#00cec9",
    "error":      "#ff6b6b",
    "border":     "#2d2d50",
    "drop_bg":    "#12122a",
    "drop_active":"#1e1e40",
    "entry":      "#12122a",
    "pro":        "#fdcb6e",
}

UVR_MODELS = {
    "UVR-MDX-NET-Voc_FT (권장)": "UVR-MDX-NET-Voc_FT.onnx",
    "UVR-MDX-NET-Inst_HQ_3": "UVR-MDX-NET-Inst_HQ_3.onnx",
    "UVR_MDXNET_KARA_2": "UVR_MDXNET_KARA_2.onnx",
    "Kim Vocal 2": "Kim_Vocal_2.onnx",
}

# Separation 모드에서 선택 가능한 악기 (demucs 6-stem 기준)
# vocals와 other는 mid-side로 vocal/sub vocal 분리에 사용
# 나머지 4개는 개별 악기
SEP_INSTRUMENTS = [
    ("drums",  "Drums"),
    ("bass",   "Bass"),
    ("guitar", "Guitar"),
    ("piano",  "Piano"),
]


def _find_ffmpeg():
    for p in ["/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg", "/usr/bin/ffmpeg"]:
        if os.path.isfile(p):
            return p
    if sys.platform == "win32":
        for p in [r"C:\ffmpeg\bin\ffmpeg.exe", r"C:\Program Files\ffmpeg\bin\ffmpeg.exe"]:
            if os.path.isfile(p):
                return p
    return "ffmpeg"


FFMPEG = _find_ffmpeg()
_ffmpeg_dir = os.path.dirname(FFMPEG)
if _ffmpeg_dir and _ffmpeg_dir not in os.environ.get("PATH", ""):
    os.environ["PATH"] = _ffmpeg_dir + os.pathsep + os.environ.get("PATH", "")


def mid_side_split(stereo_np):
    left, right = stereo_np[0], stereo_np[1]
    mid = (left + right) / 2.0
    side = (left - right) / 2.0
    return np.stack([mid, mid], axis=0), np.stack([side, -side], axis=0)


class DnDCTk(ctk.CTk, TkinterDnD.DnDWrapper):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.TkdndVersion = TkinterDnD._require(self)


class VocalSeparatorPro:
    def __init__(self):
        self.root = DnDCTk()
        self.root.title("Vocal-Separator")
        self.root.geometry("920x920")
        self.root.configure(fg_color=C["bg"])
        self.root.minsize(840, 860)

        self.files = []
        self.output_dir = tk.StringVar(value=str(Path.home() / "Downloads"))
        self.mode = tk.StringVar(value="2stem")
        self.output_format = tk.StringVar(value="wav")
        self.model_name = tk.StringVar(value=list(UVR_MODELS.keys())[0])
        self.is_processing = False
        self.should_stop = False

        # 2-stem 접미사
        self.suffix_2s_vocal = tk.StringVar(value="_vocal")
        self.suffix_2s_inst = tk.StringVar(value="_inst")

        # Separation 접미사 (필수)
        self.suffix_vocal = tk.StringVar(value="_vocal")
        self.suffix_subvocal = tk.StringVar(value="_sub")
        self.suffix_inst = tk.StringVar(value="_inst")

        # Separation 악기 체크박스 + 접미사
        self.sep_checks = {}   # key → BooleanVar
        self.sep_suffixes = {} # key → StringVar
        for key, label in SEP_INSTRUMENTS:
            self.sep_checks[key] = tk.BooleanVar(value=False)
            self.sep_suffixes[key] = tk.StringVar(value=f"_{key}")

        self.save_to_source = tk.BooleanVar(value=False)

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

    def _make_entry(self, parent, textvariable, width=80):
        return ctk.CTkEntry(parent, textvariable=textvariable, width=width, height=28,
                            corner_radius=6, fg_color=C["entry"],
                            border_color=C["border"], text_color=C["text"],
                            font=ctk.CTkFont(size=11))

    def _bind_click_recursive(self, widget, callback):
        widget.bind("<ButtonRelease-1>", callback)
        for child in widget.winfo_children():
            self._bind_click_recursive(child, callback)

    def _build_ui(self):
        main = ctk.CTkScrollableFrame(self.root, fg_color=C["bg"],
                                       scrollbar_button_color=C["border"],
                                       scrollbar_button_hover_color=C["dim"])
        main.pack(fill="both", expand=True, padx=20, pady=16)

        header = ctk.CTkFrame(main, fg_color="transparent")
        header.pack(fill="x", pady=(0, 20))
        self._label(header, "Vocal-Separator", size=28, bold=True).pack(side="left")
        self._label(header, "MDX-Net / Demucs 6-Stem", size=13,
                    color=C["dim"]).pack(side="left", padx=(12, 0), pady=(8, 0))

        self._build_file_section(main)
        self._build_mode_section(main)
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
                                        border_width=2, border_color=C["border"], height=110)
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

    # ─── 분리 모드 ───

    def _build_mode_section(self, parent):
        card = self._card(parent)
        card.pack(fill="x", pady=(0, 12))
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=20, pady=16)

        self._label(inner, "분리 모드", size=15, bold=True).pack(anchor="w")

        modes = ctk.CTkFrame(inner, fg_color="transparent")
        modes.pack(fill="x", pady=(12, 0))

        # 2-Stem 카드
        self.mode2_card = ctk.CTkFrame(modes, fg_color=C["accent"], corner_radius=12,
                                        border_width=0, height=58, cursor="hand2")
        self.mode2_card.pack(fill="x", pady=(0, 8))
        self.mode2_card.pack_propagate(False)
        m2i = ctk.CTkFrame(self.mode2_card, fg_color="transparent")
        m2i.pack(fill="x", padx=16, pady=12)
        self.mode2_dot = ctk.CTkLabel(m2i, text="●", font=ctk.CTkFont(size=14),
                                       text_color="white", width=20)
        self.mode2_dot.pack(side="left")
        self._label(m2i, "2-Stem", size=14, bold=True).pack(side="left", padx=(4, 12))
        self._label(m2i, "Vocal  /  Inst    (MDX-Net)", size=12, color="#d4f0e0").pack(side="left")

        # Separation 카드
        self.sep_card = ctk.CTkFrame(modes, fg_color=C["card_hover"], corner_radius=12,
                                      border_width=1, border_color=C["border"], cursor="hand2")
        self.sep_card.pack(fill="x")
        sep_top = ctk.CTkFrame(self.sep_card, fg_color="transparent")
        sep_top.pack(fill="x", padx=16, pady=(12, 0))
        self.sep_dot = ctk.CTkLabel(sep_top, text="○", font=ctk.CTkFont(size=14),
                                     text_color=C["dim"], width=20)
        self.sep_dot.pack(side="left")
        self._label(sep_top, "Separation", size=14, bold=True).pack(side="left", padx=(4, 12))
        self._label(sep_top, "악기별 분리    (Demucs 6-Stem)", size=12, color=C["dim"]).pack(side="left")

        # 악기 체크박스 영역
        self.inst_frame = ctk.CTkFrame(self.sep_card, fg_color="transparent")
        self.inst_frame.pack(fill="x", padx=40, pady=(8, 12))

        # 필수 항목 표시
        req_row = ctk.CTkFrame(self.inst_frame, fg_color="transparent")
        req_row.pack(fill="x", pady=(0, 4))
        self._label(req_row, "필수 출력:  Vocal  /  Sub Vocal  /  Inst", size=11, color=C["dim"]).pack(side="left")

        # 악기 체크박스 (체크하면 개별 파일, 해제하면 inst에 통합)
        chk_row = ctk.CTkFrame(self.inst_frame, fg_color="transparent")
        chk_row.pack(fill="x", pady=(2, 0))
        self._label(chk_row, "개별 분리:", size=11, color=C["dim"]).pack(side="left", padx=(0, 8))
        for key, label in SEP_INSTRUMENTS:
            ctk.CTkCheckBox(chk_row, text=label, variable=self.sep_checks[key],
                            font=ctk.CTkFont(size=11), width=90, height=24,
                            fg_color=C["accent"], hover_color=C["accent_h"],
                            border_color=C["border"], text_color=C["text"],
                            command=self._update_preview).pack(side="left", padx=(0, 6))

        # 모드 카드 클릭 바인딩 (sep_card는 상단만)
        self._bind_click_recursive(self.mode2_card, lambda e: self._set_mode("2stem"))
        for w in [sep_top, self.sep_dot]:
            w.bind("<ButtonRelease-1>", lambda e: self._set_mode("separation"))
        self.sep_card.bind("<ButtonRelease-1>", lambda e: self._set_mode("separation"))

    def _set_mode(self, mode):
        self.mode.set(mode)
        self._on_mode_change()

    def _on_mode_change(self):
        if self.mode.get() == "2stem":
            self.mode2_card.configure(fg_color=C["accent"], border_width=0)
            self.sep_card.configure(fg_color=C["card_hover"], border_width=1, border_color=C["border"])
            self.mode2_dot.configure(text="●", text_color="white")
            self.sep_dot.configure(text="○", text_color=C["dim"])
        else:
            self.sep_card.configure(fg_color=C["accent"], border_width=0)
            self.mode2_card.configure(fg_color=C["card_hover"], border_width=1, border_color=C["border"])
            self.sep_dot.configure(text="●", text_color="white")
            self.mode2_dot.configure(text="○", text_color=C["dim"])
        self._update_preview()

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

        # 포맷
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

        # 미리보기
        self.preview_label = self._label(inner, "", size=11, color=C["dim"])
        self.preview_label.pack(anchor="w", pady=(10, 0))
        self._update_preview()

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
        if self.mode.get() == "2stem":
            names = [f"{ex}_vocal.wav", f"{ex}_inst.wav"]
        else:
            names = [f"{ex}_vocal.wav", f"{ex}_sub.wav"]
            for key, label in SEP_INSTRUMENTS:
                if self.sep_checks[key].get():
                    names.append(f"{ex}_{key}.wav")
            names.append(f"{ex}_inst.wav")
        self.preview_label.configure(text=f"출력 예시:  {' / '.join(names)}")

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
        mode = self.mode.get()
        fmt = self.output_format.get()
        model_file = UVR_MODELS[self.model_name.get()]

        # Separation 모드에서 체크된 악기 목록
        checked_instruments = [k for k, v in self.sep_checks.items() if v.get()]

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
                if mode == "2stem":
                    self._separate_2stem(filepath, filename, out_dir, fmt, model_file)
                else:
                    self._separate_full(filepath, filename, out_dir, fmt, checked_instruments)
                ok += 1
            except Exception as e:
                fail += 1
                log_path = os.path.join(str(Path.home() / "Downloads"), "VocalSeparatorPro_error.log")
                with open(log_path, "a") as lf:
                    lf.write(f"\n{'='*60}\n{basename}: {e}\n")
                    traceback.print_exc(file=lf)
                self.root.after(0, self._set_status, f"오류: {basename}: {e}"[:80], C["error"])

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

    def _separate_2stem(self, filepath, filename, out_dir, fmt, model_file):
        """MDX-Net으로 Vocal/Inst 2-stem 분리"""
        from audio_separator.separator import Separator

        with tempfile.TemporaryDirectory() as tmp_dir:
            separator = Separator(output_dir=tmp_dir, output_format="WAV")
            separator.load_model(model_filename=model_file)
            result_files = separator.separate(filepath)

            vocal_path = inst_path = None
            for f in result_files:
                full = os.path.join(tmp_dir, f) if not os.path.isabs(f) else f
                if not os.path.exists(full):
                    full = os.path.join(tmp_dir, os.path.basename(f))
                fl = os.path.basename(full).lower()
                if "vocal" in fl or "primary" in fl:
                    vocal_path = full
                elif "instrument" in fl or "no_vocal" in fl or "accompaniment" in fl:
                    inst_path = full

            os.makedirs(out_dir, exist_ok=True)
            sv, si = self.suffix_2s_vocal.get(), self.suffix_2s_inst.get()
            if vocal_path:
                self._convert_from_wav(vocal_path, os.path.join(out_dir, f"{filename}{sv}.{fmt}"), fmt)
            if inst_path:
                self._convert_from_wav(inst_path, os.path.join(out_dir, f"{filename}{si}.{fmt}"), fmt)

    def _separate_full(self, filepath, filename, out_dir, fmt, checked_instruments):
        """Demucs 6-stem으로 악기별 분리 + Mid-Side 보컬 분리"""
        from audio_separator.separator import Separator
        import soundfile as sf

        with tempfile.TemporaryDirectory() as tmp_dir:
            # htdemucs_6s: vocals, drums, bass, guitar, piano, other
            separator = Separator(output_dir=tmp_dir, output_format="WAV")
            # MPS에서 6-stem 채널 제한 → CPU 강제
            separator.torch_device = "cpu"
            separator.torch_device_cpu = "cpu"
            separator.torch_device_mps = None
            separator.load_model("htdemucs_6s.yaml")
            result_files = separator.separate(filepath)

            # 결과 파일 매핑 (stem name → path)
            stems = {}
            for f in result_files:
                full = os.path.join(tmp_dir, f) if not os.path.isabs(f) else f
                if not os.path.exists(full):
                    full = os.path.join(tmp_dir, os.path.basename(f))
                fl = os.path.basename(full).lower()
                for stem_name in ["vocals", "drums", "bass", "guitar", "piano", "other"]:
                    if f"({stem_name})" in fl or f"_{stem_name}_" in fl or f"_{stem_name}." in fl:
                        stems[stem_name] = full
                        break

            os.makedirs(out_dir, exist_ok=True)

            # ── Vocal / Sub Vocal (Mid-Side from vocals stem) ──
            if "vocals" in stems:
                data, sr = sf.read(stems["vocals"], dtype="float32")
                vocals_np = data.T
                if vocals_np.ndim == 1:
                    vocals_np = np.stack([vocals_np, vocals_np], axis=0)
                main_v, back_v = mid_side_split(vocals_np)

                main_wav = os.path.join(tmp_dir, "vocal_main.wav")
                back_wav = os.path.join(tmp_dir, "vocal_back.wav")
                sf.write(main_wav, main_v.T, sr)
                sf.write(back_wav, back_v.T, sr)
                self._convert_from_wav(main_wav,
                    os.path.join(out_dir, f"{filename}{self.suffix_vocal.get()}.{fmt}"), fmt)
                self._convert_from_wav(back_wav,
                    os.path.join(out_dir, f"{filename}{self.suffix_subvocal.get()}.{fmt}"), fmt)

            # ── 체크된 악기: 개별 파일로 출력 ──
            for key in checked_instruments:
                if key in stems:
                    suffix = self.sep_suffixes[key].get()
                    self._convert_from_wav(stems[key],
                        os.path.join(out_dir, f"{filename}{suffix}.{fmt}"), fmt)

            # ── Inst: 체크 해제된 악기 + other를 합산 ──
            unchecked = [k for k in ["drums", "bass", "guitar", "piano"] if k not in checked_instruments]
            inst_stems = unchecked + ["other"]  # other는 항상 inst에 포함

            inst_arrays = []
            inst_sr = 44100
            for key in inst_stems:
                if key in stems:
                    data, sr = sf.read(stems[key], dtype="float32")
                    inst_sr = sr
                    arr = data.T
                    if arr.ndim == 1:
                        arr = np.stack([arr, arr], axis=0)
                    inst_arrays.append(arr)

            if inst_arrays:
                # 길이 통일 후 합산
                max_len = max(a.shape[1] for a in inst_arrays)
                inst_sum = np.zeros((2, max_len), dtype=np.float32)
                for a in inst_arrays:
                    inst_sum[:, :a.shape[1]] += a

                inst_wav = os.path.join(tmp_dir, "inst_mix.wav")
                sf.write(inst_wav, inst_sum.T, inst_sr)
                self._convert_from_wav(inst_wav,
                    os.path.join(out_dir, f"{filename}{self.suffix_inst.get()}.{fmt}"), fmt)


def main():
    log_path = os.path.join(str(Path.home() / "Downloads"), "VocalSeparatorPro_error.log")
    try:
        app = VocalSeparatorPro()
        app.run()
    except Exception as e:
        with open(log_path, "a") as lf:
            lf.write(f"\n{'='*60}\nFATAL: {e}\n")
            traceback.print_exc(file=lf)
        raise


if __name__ == "__main__":
    multiprocessing.freeze_support()
    if sys.platform == "darwin":
        multiprocessing.set_start_method("fork", force=True)
    main()
