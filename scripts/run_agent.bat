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

if not exist ".venv-agent" (
  echo [setup] creating venv...
  python -m venv .venv-agent
)
call .venv-agent\Scripts\activate.bat

echo [setup] installing agent (windows) requirements...
pip install -r requirements-agent-windows.txt

echo [run] starting agent (sender=auto -> kakao_windows on Windows)...
python -m agent.main --config agent\config.yaml

endlocal
