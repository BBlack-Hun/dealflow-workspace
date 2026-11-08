@echo off
REM dealflow 발송 에이전트 실행 (Windows) — KakaoDesktopSender
REM 사전 조건:
REM   1) Python 3.12 설치
REM   2) 카카오톡 데스크톱 앱에 로그인된 상태
REM   3) agent\config.yaml 의 server_url / token 을 웹 화면에서 발급받은 값으로 설정
REM
REM ⚠ 리스크 고지: 카카오 운영정책상 자동화는 계정 제재 소지가 있습니다.
REM   수동 감독 모드(발송 중 지켜보기), 방 제목 정확 일치, 발송 상한을 준수하세요.

setlocal
cd /d "%~dp0\.."

REM venv 를 만들 파이썬: python 이 진짜 파이썬이면 그것, 아니면 py 런처
REM (PATH 에 안 넣은 python.org 설치 · Microsoft Store 별칭만 잡히는 PC 대비)
set "PY="
python --version 2>&1 | findstr /b /c:"Python 3" >nul && set "PY=python"
if not defined PY (
  py -3 --version 2>&1 | findstr /b /c:"Python 3" >nul && set "PY=py -3"
)

if not exist ".venv-agent" (
  if not defined PY ( echo [ERROR] Python 3 not found - install it or turn off the Store alias & exit /b 1 )
  echo [setup] creating venv...
  %PY% -m venv .venv-agent
)
call .venv-agent\Scripts\activate.bat

echo [setup] installing agent (windows) requirements...
pip install -r requirements-agent-windows.txt

echo [run] starting agent (sender=auto -> kakao_windows on Windows)...
python -m agent.main --config agent\config.yaml

endlocal
