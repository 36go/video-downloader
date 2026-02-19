param(
  [string]$Name = "VideoDownloader"
)

$ErrorActionPreference = "Stop"

python -m pip install --upgrade pip | Out-Host
python -m pip install -r requirements.txt | Out-Host
python -m pip install -r requirements-dev.txt | Out-Host

python -m PyInstaller --noconsole --onefile --clean --name $Name --paths src src/video_downloader/__main__.py | Out-Host

Write-Host ""
Write-Host "Built: dist\\$Name.exe"
