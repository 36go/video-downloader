from __future__ import annotations

import os
import re
import shutil
import subprocess
import threading
import urllib.request
import zipfile
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Optional

ProgressDict = dict

_YTDLP_EXE_NAME = "yt-dlp_x86.exe"
_YTDLP_URL = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp_x86.exe"
_FFMPEG_URL = "https://github.com/yt-dlp/FFmpeg-Builds/releases/latest/download/ffmpeg-master-latest-win64-gpl.zip"
_PROGRESS_PREFIX = "__VD_PROGRESS__:"
_FILE_PREFIX = "__VD_FILE__:"
_PROGRESS_RE = re.compile(
    r"^(?P<status>[^|]*)\|(?P<downloaded>[^|]*)\|(?P<total>[^|]*)\|(?P<estimate>[^|]*)\|(?P<speed>[^|]*)\|(?P<eta>.*)$"
)


class DownloadError(RuntimeError):
    pass


@dataclass(frozen=True)
class DownloadRequest:
    url: str
    output_dir: str
    cookies_path: Optional[str] = None
    # If set, forces the merged container.
    # Use None to default to mp4.
    merge_output_format: Optional[str] = None


@dataclass(frozen=True)
class _ToolPaths:
    ytdlp_path: Path
    ffmpeg_location: Optional[Path]


def _to_int(value: str) -> Optional[int]:
    value = (value or "").strip()
    if not value or value in {"NA", "None"}:
        return None
    try:
        return int(float(value))
    except ValueError:
        return None


def _to_float(value: str) -> Optional[float]:
    value = (value or "").strip()
    if not value or value in {"NA", "None"}:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _tools_root() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        root = Path(local_app_data) / "VideoDownloader" / "tools"
    else:
        root = Path.home() / ".video_downloader" / "tools"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _download_file(url: str, destination: Path, log: Callable[[str], None]) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    tmp = destination.with_suffix(destination.suffix + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    downloaded = 0
    next_percent_log = 10
    try:
        with urllib.request.urlopen(req, timeout=120) as response, tmp.open("wb") as out:
            total = int(response.headers.get("Content-Length") or 0)
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                out.write(chunk)
                downloaded += len(chunk)
                if total > 0:
                    pct = int(downloaded * 100 / total)
                    if pct >= next_percent_log:
                        log(f"Downloading tools... {pct}%")
                        next_percent_log += 10
        tmp.replace(destination)
    except Exception:
        if tmp.exists():
            tmp.unlink()
        raise


def _ensure_ytdlp(root: Path, log: Callable[[str], None]) -> Path:
    ytdlp_path = root / _YTDLP_EXE_NAME
    if ytdlp_path.exists():
        return ytdlp_path
    log(f"{_YTDLP_EXE_NAME} not found. Downloading official binary...")
    _download_file(_YTDLP_URL, ytdlp_path, log)
    return ytdlp_path


def _find_ffmpeg_bin(search_root: Path) -> Optional[Path]:
    for ffmpeg_exe in search_root.rglob("ffmpeg.exe"):
        return ffmpeg_exe.parent
    return None


def _ensure_ffmpeg(root: Path, log: Callable[[str], None]) -> Optional[Path]:
    ffmpeg_in_path = shutil.which("ffmpeg")
    if ffmpeg_in_path:
        return Path(ffmpeg_in_path).resolve().parent

    local_bin = root / "ffmpeg-bin"
    if (local_bin / "ffmpeg.exe").exists():
        return local_bin

    archive_path = root / "ffmpeg-win64.zip"
    extract_dir = root / "ffmpeg-extract"
    log("FFmpeg not found. Downloading official FFmpeg build...")
    _download_file(_FFMPEG_URL, archive_path, log)

    if extract_dir.exists():
        shutil.rmtree(extract_dir)
    extract_dir.mkdir(parents=True, exist_ok=True)

    try:
        with zipfile.ZipFile(archive_path) as zf:
            zf.extractall(extract_dir)
        bin_dir = _find_ffmpeg_bin(extract_dir)
        if not bin_dir:
            raise DownloadError("Downloaded FFmpeg archive did not contain ffmpeg.exe.")

        if local_bin.exists():
            shutil.rmtree(local_bin)
        shutil.move(str(bin_dir), str(local_bin))
    finally:
        if extract_dir.exists():
            shutil.rmtree(extract_dir, ignore_errors=True)
        if archive_path.exists():
            archive_path.unlink()

    if not (local_bin / "ffmpeg.exe").exists():
        raise DownloadError("FFmpeg installation failed: ffmpeg.exe not found after extraction.")
    return local_bin


def _ensure_tools(log: Callable[[str], None]) -> _ToolPaths:
    root = _tools_root()
    ytdlp_path = _ensure_ytdlp(root, log)
    ffmpeg_location = _ensure_ffmpeg(root, log)
    return _ToolPaths(ytdlp_path=ytdlp_path, ffmpeg_location=ffmpeg_location)


def _parse_progress(payload: str) -> Optional[ProgressDict]:
    match = _PROGRESS_RE.match(payload.strip())
    if not match:
        return None
    status = match.group("status").strip() or "downloading"
    downloaded = _to_int(match.group("downloaded"))
    total = _to_int(match.group("total"))
    estimate = _to_int(match.group("estimate"))
    speed = _to_float(match.group("speed"))
    eta = _to_float(match.group("eta"))

    d: ProgressDict = {"status": status}
    if downloaded is not None:
        d["downloaded_bytes"] = downloaded
    if total is not None:
        d["total_bytes"] = total
    elif estimate is not None:
        d["total_bytes_estimate"] = estimate
    if speed is not None:
        d["speed"] = speed
    if eta is not None:
        d["eta"] = eta
    return d


def _terminate_process(process: subprocess.Popen[str]) -> None:
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def _run_ytdlp(
    request: DownloadRequest,
    tools: _ToolPaths,
    *,
    on_progress: Optional[Callable[[ProgressDict], None]],
    log: Callable[[str], None],
    cancel_event: Optional[threading.Event],
) -> None:
    out_template = os.path.join(request.output_dir, "%(title).200s [%(id)s].%(ext)s")
    merge_format = request.merge_output_format or "mp4"

    cmd = [
        str(tools.ytdlp_path),
        "-f",
        "bv*+ba/b",
        "--merge-output-format",
        merge_format,
        "--no-playlist",
        "--retries",
        "10",
        "--fragment-retries",
        "10",
        "--concurrent-fragments",
        "4",
        "--windows-filenames",
        "--newline",
        "--progress-template",
        f"download:{_PROGRESS_PREFIX}%(progress.status)s|%(progress.downloaded_bytes)s|%(progress.total_bytes)s|%(progress.total_bytes_estimate)s|%(progress.speed)s|%(progress.eta)s",
        "--print",
        f"after_move:{_FILE_PREFIX}%(filepath)s",
        "-o",
        out_template,
    ]

    if request.cookies_path:
        cmd.extend(["--cookies", request.cookies_path])

    if tools.ffmpeg_location:
        cmd.extend(["--ffmpeg-location", str(tools.ffmpeg_location)])

    cmd.append(request.url)
    recent_lines: deque[str] = deque(maxlen=20)

    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )
    assert process.stdout is not None

    for line in process.stdout:
        if cancel_event and cancel_event.is_set():
            _terminate_process(process)
            raise DownloadError("Cancelled by user")

        cleaned = line.strip()
        if not cleaned:
            continue

        if cleaned.startswith(_PROGRESS_PREFIX):
            payload = cleaned[len(_PROGRESS_PREFIX) :]
            d = _parse_progress(payload)
            if d and on_progress:
                on_progress(d)
            continue

        if cleaned.startswith(_FILE_PREFIX):
            final_path = cleaned[len(_FILE_PREFIX) :]
            if on_progress:
                on_progress({"status": "finished", "filename": final_path})
            log(f"Saved: {final_path}")
            continue

        recent_lines.append(cleaned)
        log(cleaned)

    return_code = process.wait()
    if cancel_event and cancel_event.is_set():
        raise DownloadError("Cancelled by user")
    if return_code != 0:
        details = "\n".join(recent_lines) if recent_lines else f"yt-dlp exited with code {return_code}."
        raise DownloadError(details)


def download(
    request: DownloadRequest,
    *,
    on_progress: Optional[Callable[[ProgressDict], None]] = None,
    log: Optional[Callable[[str], None]] = None,
    cancel_event: Optional[threading.Event] = None,
) -> None:
    """Download a single URL using yt-dlp_x86.exe."""

    def _log(msg: str) -> None:
        if log:
            log(msg)

    os.makedirs(request.output_dir, exist_ok=True)
    tools = _ensure_tools(_log)

    _log(f"Starting: {request.url}")
    _run_ytdlp(
        request,
        tools,
        on_progress=on_progress,
        log=_log,
        cancel_event=cancel_event,
    )
    _log("Done.")


def normalize_urls(text: str) -> list[str]:
    urls: list[str] = []
    for raw in (text or "").splitlines():
        u = raw.strip()
        if not u:
            continue
        # allow accidental space-separated pastes
        urls.extend([p.strip() for p in u.split() if p.strip()])

    # de-dupe while preserving order
    seen: set[str] = set()
    out: list[str] = []
    for u in urls:
        if u in seen:
            continue
        seen.add(u)
        out.append(u)
    return out


def download_many(
    urls: Iterable[str],
    *,
    output_dir: str,
    cookies_path: Optional[str] = None,
    merge_output_format: Optional[str] = None,
    on_progress: Optional[Callable[[str, ProgressDict], None]] = None,
    log: Optional[Callable[[str], None]] = None,
    cancel_event: Optional[threading.Event] = None,
) -> None:
    for url in urls:
        if cancel_event and cancel_event.is_set():
            raise DownloadError("Cancelled by user")

        download(
            DownloadRequest(
                url=url,
                output_dir=output_dir,
                cookies_path=cookies_path,
                merge_output_format=merge_output_format,
            ),
            on_progress=(lambda d, _url=url: on_progress(_url, d)) if on_progress else None,
            log=log,
            cancel_event=cancel_event,
        )
