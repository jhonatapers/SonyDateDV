param(
    [string]$Python = ".\.venv\Scripts\python.exe",
    [string]$FFmpegDir = ""
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (Test-Path "dist\SonyDVDate.exe") {
    throw "dist\SonyDVDate.exe ja existe. Mova ou remova a distribuicao anterior antes de compilar."
}
if ($FFmpegDir) {
    $ffmpeg = Join-Path $FFmpegDir "ffmpeg.exe"
    $ffprobe = Join-Path $FFmpegDir "ffprobe.exe"
} else {
    $ffmpeg = (Get-Command ffmpeg.exe -ErrorAction Stop).Source
    $ffprobe = (Get-Command ffprobe.exe -ErrorAction Stop).Source
}
foreach ($file in @($ffmpeg, $ffprobe, "fonts\sonycam-original.ttf")) {
    if (-not (Test-Path -LiteralPath $file -PathType Leaf)) {
        throw "Arquivo necessario nao encontrado: $file"
    }
}
$font = (Resolve-Path "fonts\sonycam-original.ttf").Path
$ffmpeg = (Resolve-Path -LiteralPath $ffmpeg).Path
$ffprobe = (Resolve-Path -LiteralPath $ffprobe).Path

& $Python -m PyInstaller --noconfirm --onefile --windowed --name SonyDVDate `
    --specpath build --workpath build\work --distpath dist `
    --add-data "$font;fonts" `
    --add-data "$ffmpeg;bin" --add-data "$ffprobe;bin" run_gui.py
if ($LASTEXITCODE -ne 0) {
    throw "Falha ao empacotar a aplicacao (codigo $LASTEXITCODE)."
}
Write-Host "Executavel criado em dist\SonyDVDate.exe."
