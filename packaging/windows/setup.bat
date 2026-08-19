@echo off
REM dealflow sending agent - first-time setup
setlocal
cd /d "%~dp0"

echo ============================================
echo   dealflow agent - SETUP
echo ============================================
echo.

where python >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Python not found.
  echo         Install from https://www.python.org/downloads/
  echo         IMPORTANT: check "Add python.exe to PATH" during install.
  echo.
  pause
  exit /b 1
)

echo [1/2] creating virtual environment...
if not exist ".venv-agent" (
  python -m venv .venv-agent
  if errorlevel 1 ( echo [ERROR] venv failed & pause & exit /b 1 )
) else (
  echo       already exists - skipped
)

echo [2/2] installing packages... this may take a few minutes
.venv-agent\Scripts\python -m pip install --upgrade pip >nul 2>nul
.venv-agent\Scripts\pip install -r requirements.txt
if errorlevel 1 ( echo [ERROR] install failed & pause & exit /b 1 )

echo.
echo ============================================
echo   SETUP DONE
echo.
echo   Next:
echo     1) Log in to KakaoTalk
echo     2) Check agent\config.yaml (server_url)
echo     3) Run  run_agent.bat
echo ============================================
echo.
pause
endlocal
