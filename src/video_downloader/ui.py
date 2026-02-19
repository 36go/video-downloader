from __future__ import annotations

import os
import queue
import threading
import time
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import customtkinter as ctk
from tkinter import filedialog, messagebox

from video_downloader.downloader import download_many, normalize_urls


def _fmt_bytes(n: Optional[float]) -> str:
    if not n:
        return "-"
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(n)
    i = 0
    while size >= 1024 and i < len(units) - 1:
        size /= 1024
        i += 1
    if i == 0:
        return f"{int(size)} {units[i]}"
    return f"{size:.2f} {units[i]}"


def _fmt_eta(seconds: Optional[float]) -> str:
    if seconds is None:
        return "-"
    try:
        s = int(seconds)
    except Exception:
        return "-"
    if s < 0:
        return "-"
    m, s = divmod(s, 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h:d}:{m:02d}:{s:02d}"
    return f"{m:d}:{s:02d}"


@dataclass
class _UiEvent:
    kind: str
    payload: object = None


class App(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()

        ctk.set_appearance_mode("System")
        ctk.set_default_color_theme("blue")

        self.title("Video Downloader")
        self.geometry("980x650")
        self.minsize(900, 600)

        self._q: "queue.Queue[_UiEvent]" = queue.Queue()
        self._cancel_event: Optional[threading.Event] = None
        self._worker: Optional[threading.Thread] = None

        self._build_ui()
        self.after(100, self._poll_queue)

    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(6, weight=1)

        title = ctk.CTkLabel(self, text="Video Downloader", font=ctk.CTkFont(size=28, weight="bold"))
        title.grid(row=0, column=0, padx=18, pady=(18, 6), sticky="w")

        subtitle = ctk.CTkLabel(
            self,
            text="YouTube + Instagram (yt-dlp_x86.exe) | Missing tools are installed automatically",
            font=ctk.CTkFont(size=13),
            text_color=("gray30", "gray70"),
        )
        subtitle.grid(row=1, column=0, padx=18, pady=(0, 12), sticky="w")

        form = ctk.CTkFrame(self)
        form.grid(row=2, column=0, padx=18, pady=(0, 12), sticky="ew")
        form.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(form, text="URL(s) (one per line)").grid(row=0, column=0, padx=14, pady=(14, 4), sticky="w")
        self.urls = ctk.CTkTextbox(form, height=90)
        self.urls.grid(row=1, column=0, padx=14, pady=(0, 12), sticky="ew")

        path_row = ctk.CTkFrame(form, fg_color="transparent")
        path_row.grid(row=2, column=0, padx=14, pady=(0, 12), sticky="ew")
        path_row.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(path_row, text="Save to").grid(row=0, column=0, sticky="w")

        self.output_dir_var = ctk.StringVar(value=str(Path.home() / "Downloads"))
        self.output_dir = ctk.CTkEntry(path_row, textvariable=self.output_dir_var)
        self.output_dir.grid(row=1, column=0, pady=(4, 0), sticky="ew")

        browse_out = ctk.CTkButton(path_row, text="Browse", width=100, command=self._browse_output)
        browse_out.grid(row=1, column=1, padx=(10, 0), pady=(4, 0))

        cookies_row = ctk.CTkFrame(form, fg_color="transparent")
        cookies_row.grid(row=3, column=0, padx=14, pady=(0, 14), sticky="ew")
        cookies_row.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(cookies_row, text="Instagram cookies.txt (optional)").grid(row=0, column=0, sticky="w")

        self.cookies_var = ctk.StringVar(value="")
        self.cookies = ctk.CTkEntry(cookies_row, textvariable=self.cookies_var, placeholder_text="cookies.txt (Netscape format)")
        self.cookies.grid(row=1, column=0, pady=(4, 0), sticky="ew")

        browse_cookies = ctk.CTkButton(cookies_row, text="Browse", width=100, command=self._browse_cookies)
        browse_cookies.grid(row=1, column=1, padx=(10, 0), pady=(4, 0))

        actions = ctk.CTkFrame(self)
        actions.grid(row=3, column=0, padx=18, pady=(0, 12), sticky="ew")
        actions.grid_columnconfigure(2, weight=1)

        self.download_btn = ctk.CTkButton(actions, text="Download", command=self._start_download)
        self.download_btn.grid(row=0, column=0, padx=12, pady=12)

        self.cancel_btn = ctk.CTkButton(
            actions,
            text="Cancel",
            fg_color="#444",
            hover_color="#333",
            command=self._cancel,
            state="disabled",
        )
        self.cancel_btn.grid(row=0, column=1, padx=(0, 12), pady=12)

        self.open_folder_btn = ctk.CTkButton(actions, text="Open Folder", command=self._open_folder)
        self.open_folder_btn.grid(row=0, column=3, padx=12, pady=12)

        self.help_btn = ctk.CTkButton(actions, text="Tools Help", command=self._open_ffmpeg_help)
        self.help_btn.grid(row=0, column=4, padx=(0, 12), pady=12)

        self.status_var = ctk.StringVar(value="Ready.")
        self.status = ctk.CTkLabel(self, textvariable=self.status_var, anchor="w")
        self.status.grid(row=4, column=0, padx=18, pady=(0, 6), sticky="ew")

        self.progress = ctk.CTkProgressBar(self)
        self.progress.grid(row=5, column=0, padx=18, pady=(0, 12), sticky="ew")
        self.progress.set(0)

        log_frame = ctk.CTkFrame(self)
        log_frame.grid(row=6, column=0, padx=18, pady=(0, 18), sticky="nsew")
        log_frame.grid_columnconfigure(0, weight=1)
        log_frame.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(log_frame, text="Log").grid(row=0, column=0, padx=14, pady=(12, 4), sticky="w")
        self.log = ctk.CTkTextbox(log_frame)
        self.log.grid(row=1, column=0, padx=14, pady=(0, 14), sticky="nsew")
        self._log_line("Tip: Missing yt-dlp/FFmpeg tools are downloaded automatically on first run.")
        self._log_line("Tip: Instagram retries automatically with browser cookies if needed.")

    def _browse_output(self) -> None:
        path = filedialog.askdirectory(initialdir=self.output_dir_var.get() or str(Path.home()))
        if path:
            self.output_dir_var.set(path)

    def _browse_cookies(self) -> None:
        path = filedialog.askopenfilename(
            title="Select cookies.txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
        )
        if path:
            self.cookies_var.set(path)

    def _open_folder(self) -> None:
        path = self.output_dir_var.get().strip()
        if not path:
            return
        try:
            os.startfile(path)  # type: ignore[attr-defined]
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def _open_ffmpeg_help(self) -> None:
        webbrowser.open("https://github.com/yt-dlp/yt-dlp#installation")

    def _set_busy(self, busy: bool) -> None:
        self.download_btn.configure(state="disabled" if busy else "normal")
        self.cancel_btn.configure(state="normal" if busy else "disabled")
        self.open_folder_btn.configure(state="disabled" if busy else "normal")

    def _start_download(self) -> None:
        if self._worker and self._worker.is_alive():
            return

        urls_text = self.urls.get("1.0", "end").strip()
        urls = normalize_urls(urls_text)
        if not urls:
            messagebox.showwarning("Missing URL", "Paste a YouTube/Instagram URL first.")
            return

        output_dir = self.output_dir_var.get().strip()
        if not output_dir:
            messagebox.showwarning("Missing folder", "Choose an output folder.")
            return

        cookies_path = self.cookies_var.get().strip() or None
        if cookies_path and not os.path.isfile(cookies_path):
            messagebox.showwarning("Cookies file not found", "cookies.txt path does not exist.")
            return

        self.progress.set(0)
        self.status_var.set("Starting...")
        self._set_busy(True)

        self._cancel_event = threading.Event()

        def run() -> None:
            started = time.time()

            def log(msg: str) -> None:
                self._q.put(_UiEvent("log", msg))

            def on_progress(url: str, d: dict) -> None:
                self._q.put(_UiEvent("progress", {"url": url, "data": d}))

            try:
                download_many(
                    urls,
                    output_dir=output_dir,
                    cookies_path=cookies_path,
                    on_progress=on_progress,
                    log=log,
                    cancel_event=self._cancel_event,
                )
                self._q.put(_UiEvent("done", time.time() - started))
            except Exception as e:
                self._q.put(_UiEvent("error", str(e)))

        self._worker = threading.Thread(target=run, daemon=True)
        self._worker.start()

    def _cancel(self) -> None:
        if self._cancel_event:
            self._cancel_event.set()
            self.status_var.set("Cancelling...")
            self._log_line("Cancel requested...")

    def _log_line(self, line: str) -> None:
        self.log.insert("end", line.rstrip() + "\n")
        self.log.see("end")

    def _poll_queue(self) -> None:
        try:
            while True:
                ev = self._q.get_nowait()
                if ev.kind == "log":
                    self._log_line(str(ev.payload))
                elif ev.kind == "progress":
                    payload = ev.payload if isinstance(ev.payload, dict) else {}
                    url = str(payload.get("url", ""))
                    d = payload.get("data") if isinstance(payload.get("data"), dict) else {}
                    self._handle_progress(url, d)
                elif ev.kind == "done":
                    seconds = float(ev.payload or 0)
                    self.progress.set(1)
                    self.status_var.set(f"Done in {seconds:.1f}s.")
                    self._set_busy(False)
                elif ev.kind == "error":
                    self.status_var.set("Error.")
                    self._set_busy(False)
                    messagebox.showerror("Download failed", str(ev.payload))
                else:
                    self._log_line(f"[internal] unknown event: {ev.kind}")
        except queue.Empty:
            pass
        self.after(100, self._poll_queue)

    def _handle_progress(self, url: str, d: dict) -> None:
        status = d.get("status")
        if status == "downloading":
            downloaded = d.get("downloaded_bytes") or 0
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            speed = d.get("speed")
            eta = d.get("eta")
            if total:
                self.progress.set(min(1.0, float(downloaded) / float(total)))
            self.status_var.set(
                f"Downloading: {url} | {_fmt_bytes(downloaded)}/{_fmt_bytes(total)} | {_fmt_bytes(speed)}/s | ETA {_fmt_eta(eta)}"
            )
        elif status == "finished":
            self.progress.set(1)
            filename = d.get("filename") or ""
            self.status_var.set(f"Processing: {os.path.basename(filename)}")
        else:
            if url:
                self.status_var.set(f"{status or 'Working'}: {url}")


def run_app() -> None:
    app = App()
    app.mainloop()
