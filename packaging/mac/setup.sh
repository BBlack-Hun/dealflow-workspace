#!/usr/bin/env bash
# dealflow 발송 에이전트 설치 (macOS)
#
# 필수(requests, pyyaml)와 선택(Quartz)을 나눠 설치한다.
# 한 번에 설치하면 Quartz 빌드 실패가 전체를 롤백시켜 requests 까지 안 깔린다(실기 발생).

set -uo pipefail

# 이 스크립트는 두 위치에서 실행된다:
#   1) 저장소:      packaging/mac/setup.sh  → 저장소 루트로 올라가야 함
#   2) 배포 zip:    setup.sh (agent/ 와 같은 위치) → 그 자리가 곧 루트
# agent/ 디렉터리가 보이는 곳을 루트로 삼는다. (../.. 로 무조건 올라가면
# zip 에서 실행할 때 압축 푼 폴더 밖에 venv 를 만들어 버린다 — 실기 확인)
cd "$(dirname "$0")" || exit 1
if [ ! -d "agent" ] && [ -d "../../agent" ]; then
  cd ../.. || exit 1
fi
if [ ! -d "agent" ]; then
  echo "[오류] agent/ 폴더를 찾을 수 없습니다. 압축을 푼 폴더에서 실행하세요."
  exit 1
fi

VENV=".venv-agent"

echo "============================================"
echo "  dealflow 발송 에이전트 설치 (macOS)"
echo "============================================"
echo

# --- Python 선택 ------------------------------------------------------
# `python3` 가 pyenv 등으로 3.9 를 가리키는 경우가 흔하다(실기 확인).
# 3.9 에는 Quartz 휠이 없어 소스 빌드로 넘어가 실패하므로,
# 설치된 것 중 **3.10 이상을 우선** 찾아 쓴다. PYTHON 환경변수로 강제 지정 가능.
pick_python() {
  if [ -n "${PYTHON:-}" ]; then echo "$PYTHON"; return; fi
  for c in python3.13 python3.12 python3.11 python3.10 \
           /opt/homebrew/bin/python3 /usr/local/bin/python3 python3; do
    if command -v "$c" >/dev/null 2>&1; then
      v="$("$c" -c 'import sys; print(sys.version_info[0]*100+sys.version_info[1])' 2>/dev/null || echo 0)"
      if [ "$v" -ge 310 ] 2>/dev/null; then echo "$c"; return; fi
    fi
  done
  command -v python3 >/dev/null 2>&1 && echo "python3" || echo ""
}

PY="$(pick_python)"
if [ -z "$PY" ]; then
  echo "[오류] python3 를 찾을 수 없습니다. https://www.python.org/downloads/ 에서 설치하세요."
  exit 1
fi

VER="$("$PY" -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
MAJOR="${VER%%.*}"; MINOR="${VER##*.}"
echo "[1/4] Python $VER ($(command -v "$PY"))"
QUARTZ_OK=1
if [ "$MAJOR" -eq 3 ] && [ "$MINOR" -lt 10 ]; then
  echo "      ⚠ Python 3.10 이상을 권장합니다."
  echo "        3.9 에서는 채팅방 자동 열기용 Quartz 설치가 실패할 수 있습니다"
  echo "        (미리 빌드된 휠이 없어 컴파일러가 필요). 발송 자체는 정상 동작합니다."
  QUARTZ_OK=0
fi

# --- 가상환경 --------------------------------------------------------
echo "[2/4] 가상환경 준비..."
if [ ! -d "$VENV" ]; then
  "$PY" -m venv "$VENV" || { echo "[오류] 가상환경 생성 실패"; exit 1; }
else
  echo "      이미 있음 — 건너뜀"
fi
"$VENV/bin/python" -m pip install --quiet --upgrade pip >/dev/null 2>&1

# --- 필수 패키지 (실패하면 중단) --------------------------------------
echo "[3/4] 필수 패키지 설치 (requests, pyyaml)..."
if ! "$VENV/bin/pip" install --quiet "requests>=2.31" "pyyaml>=6.0"; then
  echo "[오류] 필수 패키지 설치 실패 — 네트워크를 확인하세요."
  exit 1
fi
echo "      완료"

# --- 선택 패키지 (실패해도 계속) --------------------------------------
echo "[4/4] 선택 패키지 설치 (Quartz — 채팅방 자동 열기)..."
QUARTZ_INSTALLED=0
if "$VENV/bin/pip" install --quiet "pyobjc-framework-Quartz>=10" 2>/dev/null; then
  QUARTZ_INSTALLED=1
  echo "      완료"
else
  echo "      건너뜀 (설치 실패 — 발송에는 지장 없음)"
fi

echo
echo "============================================"
echo "  설치 완료"
echo
if [ "$QUARTZ_INSTALLED" -eq 1 ]; then
  echo "  ✅ 채팅방 자동 열기 사용 가능"
else
  echo "  ⚠️  채팅방 자동 열기 불가 (Quartz 미설치)"
  echo "     → 카카오톡에서 보낼 채팅방 창을 미리 열어두세요."
  if [ "$QUARTZ_OK" -eq 0 ]; then
    echo "     → 자동 열기까지 원하면 Python 3.10+ 로 다시 설치하세요."
  else
    echo "     → 또는  xcode-select --install  후 재시도하세요."
  fi
fi
echo
echo "  다음 순서:"
echo "    1) 시스템 설정 → 개인정보 보호 및 보안 → 손쉬운 사용 에서 터미널 허용"
echo "    2) 카카오톡 로그인"
echo "    3) 아래 명령으로 실행:"
echo
echo "       $VENV/bin/python -m agent.main --config agent/config.yaml"
echo "============================================"
