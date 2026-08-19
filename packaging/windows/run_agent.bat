@echo off
REM dealflow sending agent - run
setlocal
cd /d "%~dp0"

if not exist ".venv-agent" (
  echo [ERROR] Not installed yet. Run setup.bat first.
  pause
  exit /b 1
)

echo ============================================
echo   dealflow sending agent
echo ============================================
echo.
echo  - Make sure KakaoTalk is logged in.
echo  - DO NOT touch mouse/keyboard while sending.
echo  - Press Ctrl+C to stop.
echo.
echo  Connecting to server... (keep this window open)
echo --------------------------------------------

.venv-agent\Scripts\python -m agent.main --config agent\config.yaml

echo.
echo Agent stopped.
pause
endlocal
