@echo off
REM dealflow sending agent - first-time setup
setlocal
cd /d "%~dp0"

echo ============================================
echo   dealflow agent - SETUP
echo ============================================
echo.

REM Pick the Python to use. "where python" is not enough: the Microsoft Store
REM alias (WindowsApps\python.exe) is found but is not a real Python, and a
REM python.org install without "Add python.exe to PATH" has only the py launcher.
set "PY="
python --version 2>&1 | findstr /b /c:"Python 3" >nul && set "PY=python"
if not defined PY (
  py -3 --version 2>&1 | findstr /b /c:"Python 3" >nul && set "PY=py -3"
)
if not defined PY (
  echo [ERROR] Python not found.
  echo         Install from https://www.python.org/downloads/
  echo         IMPORTANT: check "Add python.exe to PATH" during install.
  echo         Already installed? Turn off the Store alias: Settings ^> Apps ^>
  echo         Advanced app settings ^> App execution aliases ^> python.exe, python3.exe
  echo.
  pause
  exit /b 1
)

REM Show which Python is installed. Install failures are usually a version
REM mismatch, so a screenshot of this window should reveal the version.
for /f "delims=" %%v in ('%PY% --version 2^>^&1') do echo       using %%v  [%PY%]
echo.

echo [1/2] creating virtual environment...
if not exist ".venv-agent" (
  %PY% -m venv .venv-agent
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
