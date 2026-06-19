@echo off
set TOOLS=%~dp0
set ZIP=%TOOLS%ngrok.zip
echo Downloading latest ngrok for Windows...
powershell -NoProfile -Command "Invoke-WebRequest -Uri 'https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-windows-amd64.zip' -OutFile '%ZIP%'"
if errorlevel 1 (
  echo Download failed.
  exit /b 1
)
powershell -NoProfile -Command "Expand-Archive -Path '%ZIP%' -DestinationPath '%TOOLS%' -Force"
del "%ZIP%"
"%TOOLS%ngrok.exe" version
echo.
echo Done. Add authtoken once:
echo   agent\tools\ngrok.exe config add-authtoken YOUR_TOKEN
echo Then start tunnel:
echo   agent\scripts\start-tunnel.bat
