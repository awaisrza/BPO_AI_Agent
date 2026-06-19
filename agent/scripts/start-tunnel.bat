@echo off
set PORT=8765
if not "%AGENT_PORT%"=="" set PORT=%AGENT_PORT%

set "SCRIPT_DIR=%~dp0"
set "NGROK=%SCRIPT_DIR%..\tools\ngrok.exe"
if exist "%NGROK%" (
  echo Starting ngrok %NGROK% on port %PORT% ...
  echo Copy the https URL into LOCAL_SERVER_URL in dashboard/.env.local
  echo.
  "%NGROK%" http %PORT%
  exit /b %ERRORLEVEL%
)

set NGROK=%LOCALAPPDATA%\Microsoft\WinGet\Packages\Ngrok.Ngrok_Microsoft.Winget.Source_8wekyb3d8bbwe\ngrok.exe
if exist "%NGROK%" (
  echo WARNING: winget ngrok is old. Run: agent\tools\download-ngrok.bat
  echo Starting ngrok on port %PORT% ...
  "%NGROK%" http %PORT%
  exit /b %ERRORLEVEL%
)

where cloudflared >nul 2>&1
if %ERRORLEVEL%==0 (
  echo Starting cloudflared on port %PORT% ...
  cloudflared tunnel --url http://localhost:%PORT%
  exit /b %ERRORLEVEL%
)

echo No tunnel found. Run: agent\tools\download-ngrok.bat
exit /b 1
