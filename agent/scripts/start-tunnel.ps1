# Expose localhost:8765 to the internet for Twilio phone tests.
# Usage: .\scripts\start-tunnel.ps1
# Copy the https URL into dashboard/.env.local as LOCAL_SERVER_URL=

$Port = if ($env:AGENT_PORT) { $env:AGENT_PORT } else { "8765" }

$ngrokPaths = @(
    "$env:LOCALAPPDATA\Microsoft\WinGet\Packages\Ngrok.Ngrok_Microsoft.Winget.Source_8wekyb3d8bbwe\ngrok.exe",
    "$env:LOCALAPPDATA\Microsoft\WinGet\Links\ngrok.exe"
)

foreach ($path in $ngrokPaths) {
    if (Test-Path $path) {
        Write-Host "Starting ngrok on port $Port ..."
        Write-Host "Copy the https://.... URL into LOCAL_SERVER_URL in dashboard/.env.local"
        Write-Host ""
        & $path http $Port
        exit $LASTEXITCODE
    }
}

if (Get-Command cloudflared -ErrorAction SilentlyContinue) {
    Write-Host "Starting cloudflared on port $Port ..."
    Write-Host "Copy the https://....trycloudflare.com URL into LOCAL_SERVER_URL"
    Write-Host ""
    cloudflared tunnel --url "http://localhost:$Port"
    exit $LASTEXITCODE
}

Write-Host "No tunnel found. Install one of:"
Write-Host "  winget install Ngrok.Ngrok"
Write-Host "  winget install Cloudflare.cloudflared"
exit 1
