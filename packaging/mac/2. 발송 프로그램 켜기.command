#!/usr/bin/env bash
# 더블클릭으로 발송 프로그램을 켠다. 이 창은 켜 둔 채로 두어야 발송이 나간다.
cd "$(dirname "$0")" || exit 1
clear
echo "============================================"
echo " dealflow 발송 프로그램"
echo "============================================"
echo
echo " * 이 창을 닫으면 발송이 멈춥니다. 켜 둔 채로 두세요."
echo " * 카카오톡에 로그인되어 있어야 합니다."
echo
if [ ! -x ".venv-agent/bin/python" ]; then
  echo "[안내] 아직 설치가 안 되어 있습니다."
  echo "       '1. 설치하기' 를 먼저 더블클릭하세요."
  echo
  read -r -p "엔터를 누르면 닫힙니다. "
  exit 1
fi
.venv-agent/bin/python -m agent.main --config agent/config.yaml
echo
read -r -p "발송 프로그램이 종료되었습니다. 엔터를 누르면 닫힙니다. "
