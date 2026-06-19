# One-time Piper setup for test_piper.py
# Needs ~200 MB free disk space (Piper binary + voice model).

$ErrorActionPreference = "Stop"
$AgentRoot = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$PiperDir = Join-Path $AgentRoot "piper"
$ModelsDir = Join-Path $AgentRoot "models"
$ZipPath = Join-Path $PiperDir "piper_windows_amd64.zip"

New-Item -ItemType Directory -Force -Path $PiperDir, $ModelsDir | Out-Null

$freeGb = [math]::Round((Get-PSDrive C).Free / 1GB, 2)
if ($freeGb -lt 0.2) {
    Write-Error "Only ${freeGb} GB free on C:. Free at least 0.2 GB, then re-run this script."
}

$piperExe = Get-ChildItem -Recurse $PiperDir -Filter piper.exe -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $piperExe) {
    Write-Host "Downloading Piper..."
    Invoke-WebRequest `
        -Uri "https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_windows_amd64.zip" `
        -OutFile $ZipPath
    Write-Host "Extracting..."
    Expand-Archive -Path $ZipPath -DestinationPath $PiperDir -Force
    Remove-Item $ZipPath -Force
    $piperExe = Get-ChildItem -Recurse $PiperDir -Filter piper.exe | Select-Object -First 1
}

if (-not $piperExe) {
    Write-Error "piper.exe not found after extract. Check $PiperDir"
}

$modelOnnx = Join-Path $ModelsDir "en_US-libritts-high.onnx"
$modelJson = Join-Path $ModelsDir "en_US-libritts-high.onnx.json"
if (-not (Test-Path $modelOnnx)) {
    Write-Host "Downloading voice model (~130 MB)..."
    Invoke-WebRequest `
        -Uri "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/libritts/high/en_US-libritts-high.onnx" `
        -OutFile $modelOnnx
}
if (-not (Test-Path $modelJson)) {
    Invoke-WebRequest `
        -Uri "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/libritts/high/en_US-libritts-high.onnx.json" `
        -OutFile $modelJson
}

$envLocal = Join-Path $AgentRoot ".env.local"
$lines = @(
    "PIPER_EXE=$($piperExe.FullName)",
    "PIPER_MODEL=$modelOnnx",
    "PIPER_SPEAKER=0"
)
if (Test-Path $envLocal) {
    $content = Get-Content $envLocal -Raw
    foreach ($key in @("PIPER_EXE", "PIPER_MODEL", "PIPER_SPEAKER")) {
        $content = [regex]::Replace($content, "(?m)^$key=.*$", "")
    }
    $content = ($content.TrimEnd() + "`r`n`r`n" + ($lines -join "`r`n") + "`r`n")
    Set-Content -Path $envLocal -Value $content -Encoding UTF8
} else {
    Set-Content -Path $envLocal -Value ($lines -join "`r`n") -Encoding UTF8
}

Write-Host ""
Write-Host "Piper ready:"
Write-Host "  $($piperExe.FullName)"
Write-Host "  $modelOnnx"
Write-Host ""
Write-Host "Test:"
Write-Host "  .\.venv\Scripts\python.exe scripts/test_piper.py --text `"Hi, this is Sarah on a recorded line.`""
