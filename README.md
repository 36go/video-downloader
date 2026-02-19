# Video Downloader

Windows desktop app to download videos from YouTube and Instagram using `yt-dlp_x86.exe`.

Core command style:

```powershell
yt-dlp_x86.exe -f "bv*+ba/b" --merge-output-format mp4 <video-url>
```

## Features
- Highest quality download flow with MP4 output.
- Audio-safe format priority (`mp4 video + m4a audio`) to avoid silent files.
- Auto-install missing tools on first run:
  - `yt-dlp_x86.exe`
  - `ffmpeg.exe`
- Instagram Reels retries:
  - direct download
  - retry with browser cookies (Chrome, Edge, Firefox) when needed
- Optional `cookies.txt` support for Instagram.

## Requirements
- Windows 10/11
- Python 3.10+

## Run from source
```powershell
git clone https://github.com/36go/video-downloader.git
cd video-downloader
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m video_downloader
```

## Build EXE
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
.\scripts\build_exe.ps1
```

Output: `dist\VideoDownloader.exe`

## GitHub Releases
Workflow file: `.github/workflows/release.yml`

```powershell
git tag v0.1.1
git push origin v0.1.1
```

Release uploads `VideoDownloader.exe` directly.
