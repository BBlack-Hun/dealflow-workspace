#!/bin/bash
# GitHub Actions 가 main 에 머지될 때마다 부른다.
#
# 이 스크립트는 authorized_keys 의 command= 로 묶여 있다 — 배포 키로는
# 이것 말고 아무것도 실행되지 않는다. 저장소가 공개라 키가 샐 경우를 생각했다.
#
# ## 저장소 사본과 서버 사본
#
# 실제로 도는 것은 서버의 /home/dealflow/deploy.sh 다. 이 파일은 그것의 **기록용
# 사본**이고, 배포가 이 파일을 서버 사본으로 옮겨 주지 않는다 — 배포 키가 묶인
# 파일을 배포가 스스로 바꾸게 두지 않는다. 고친 뒤에는 사람이 한 번 깐다
# (deploy/README.md `배포 스크립트`):
#
#   sudo install -o dealflow -g dealflow -m 755 \
#     /home/dealflow/app/deploy/deploy.sh /home/dealflow/deploy.sh
set -euo pipefail
APP=/home/dealflow/app
DATA=/home/dealflow/data
cd "$APP"

PREV=$(git rev-parse HEAD)
echo "지금 버전: ${PREV:0:8}"

# 받아서 견주는 것이 먼저다. 바뀐 것이 없으면 백업도 뜨지 않는다 — 할 일 없는
# 실행(배포만 다시 누르기 등)마다 DB 사본이 한 벌씩 쌓이지 않게.
git fetch --quiet origin main
NEW=$(git rev-parse origin/main)
if [ "$PREV" = "$NEW" ]; then
  echo "이미 최신입니다 — 할 일 없음"
  exit 0
fi

# 마이그레이션이 데이터를 건드린다. 되돌릴 수 있게 바꾸기 직전에 뜬다.
STAMP=$(date +%Y%m%d-%H%M%S)
docker compose -f deploy/docker-compose.prod.yml exec -T web \
  python scripts/db_snapshot.py "/app/data/dealflow.db" "/app/data/predeploy-$STAMP.db" >/dev/null
rm -f "$DATA/predeploy-$STAMP.db-wal" "$DATA/predeploy-$STAMP.db-shm"
echo "배포 전 백업: predeploy-$STAMP.db"

git reset --hard --quiet "$NEW"
echo "새 버전: ${NEW:0:8}"

cd "$APP/deploy"
docker compose -f docker-compose.prod.yml up -d --build 2>&1 | tail -5

# 떴는지 실제로 확인한다. 컨테이너가 올라온 것과 앱이 답하는 것은 다르다.
for i in $(seq 1 30); do
  if curl -fsS -m 5 http://localhost/health >/dev/null 2>&1; then
    echo "배포 성공: ${NEW:0:8}"
    # 2주 지난 배포 전 백업은 지운다. 곁딸린 -wal·-shm 도 같이 — 앱이 백업 목록을
    # 그리며 읽기만 해도 생겨서, 본체만 지우면 짝 없는 것이 쌓인다.
    find "$DATA" -maxdepth 1 \( -name "predeploy-*.db" -o -name "predeploy-*.db-wal" \
      -o -name "predeploy-*.db-shm" \) -mtime +14 -delete
    exit 0
  fi
  sleep 3
done

# 안 뜨면 되돌린다. 사람이 잘 때 배포가 나가도 화면은 살아 있어야 한다.
echo "헬스체크 실패 — ${PREV:0:8} 로 되돌립니다"
cd "$APP" && git reset --hard --quiet "$PREV"
cd "$APP/deploy" && docker compose -f docker-compose.prod.yml up -d --build 2>&1 | tail -3
echo "되돌렸습니다. 데이터 백업: predeploy-$STAMP.db"
exit 1
