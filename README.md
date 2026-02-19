# Video Downloader | تطبيق تحميل الفيديوهات

Desktop app (Python) to download videos from **YouTube** and **Instagram**.

التطبيق يستخدم `yt-dlp_x86.exe` مباشرة بنفس الأسلوب:

```powershell
yt-dlp_x86.exe -f "bv*+ba/b" --merge-output-format mp4 <video-url>
```

## Features | المميزات
- Highest quality by default: `-f "bv*+ba/b"`.
- Output merged as `mp4`.
- Auto-install missing tools on first run:
  - `yt-dlp_x86.exe`
  - `ffmpeg.exe` (for best merge quality)
- Optional `cookies.txt` for Instagram.

## Important | مهم
Use this tool only for content you own or have permission to download.

رجاءً استخدم هذا التطبيق فقط للمحتوى الذي تملكه أو لديك صلاحية لتحميله.

## Requirements | المتطلبات
- Windows 10/11
- Python 3.10+

## Install (English)
```powershell
git clone https://github.com/36go/video-downloader.git
cd video-downloader
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m video_downloader
```

## التثبيت (عربي)
```powershell
git clone https://github.com/36go/video-downloader.git
cd video-downloader
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m video_downloader
```

## Instagram notes | ملاحظات الانستغرام
Instagram downloads can be unreliable without cookies.

1. Export browser cookies as Netscape format `cookies.txt`.
2. Select the file in the app.

## Build EXE (Windows) | بناء ملف exe
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
.\scripts\build_exe.ps1
```

Output: `dist\VideoDownloader.exe`

## GitHub Releases | النشر على GitHub Releases
Workflow file: `.github/workflows/release.yml`

1. Commit your changes.
2. Create and push a tag:
```powershell
git tag v0.1.1
git push origin v0.1.1
```

Release will include `VideoDownloader.exe` مباشرة داخل الـ Release.
