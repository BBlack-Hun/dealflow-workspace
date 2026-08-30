"""투자컨설턴트 첫 탭 이름 `중요 스타트업` → `스타트업` (자료도 함께 옮긴다)

## 왜 이름만 바꾸면 안 되는가

탭은 줄에 적힌 시트 이름을 그대로 올린다(`routers/consulting.py` 의
`sheet_tabs`). 코드의 이름만 바꾸면 이미 들어간 줄은 옛 이름을 지고 있어서
**빈 `스타트업` 탭과 줄이 다 들어 있는 `중요 스타트업` 유령 탭**이 나란히 선다.
쓰는 사람 눈에는 자료가 사라진 것처럼 보이고, 새로 올리면 두 벌이 된다.

## 왜 스크립트가 아니라 마이그레이션인가

셋 다 이 자리가 맞다고 가리킨다.

  · **배포와 같은 순간에 돌아야 한다.** 새 코드가 뜬 뒤 사람이 스크립트를
    부르기까지의 사이가 곧 유령 탭이 보이는 시간이다. 컨테이너는 이미
    기동할 때 마이그레이션을 돌린다(`RUN_MIGRATIONS=1`).
  · **한 번만 돌아야 한다.** 스크립트는 누가 언제 돌렸는지 남지 않아, 운영에
    적용됐는지 확인할 방법이 스크립트를 또 돌려 보는 것뿐이다.
  · **되돌릴 수 있어야 한다.** `downgrade` 가 그대로 옛 이름으로 되돌린다.

## 두 번 돌려도 죽지 않는가

`WHERE sheet = '중요 스타트업'` 이라 두 번째에는 걸리는 줄이 0이다. 스키마를
건드리지 않으므로 `duplicate column name` 부류의 사고가 날 자리도 없다.

## 칸 기본값(server_default)은 왜 그대로 두는가

0028 이 `server_default='중요 스타트업'` 으로 칸을 만들었다. SQLite 에서 그것을
바꾸려면 표를 통째로 다시 만들어야 하는데(batch_alter_table), 실자료가 든 표를
재작성하는 위험이 얻는 것보다 크다. 앱은 줄을 넣을 때 늘 값을 실어 보내므로
(`models.py` 의 `default="스타트업"`) 이 기본값이 쓰이는 길은 **SQL 로 직접
넣을 때**뿐이다.

Revision ID: 0039_consulting_startup_tab
Revises: 0038_meeting_time
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0039_consulting_startup_tab"
down_revision = "0038_meeting_time"
branch_labels = None
depends_on = None

OLD = "중요 스타트업"
NEW = "스타트업"

# 줄과 월 열이 **같이** 옮겨져야 한다. 한쪽만 옮기면 그 탭의 표에 월 열이
# 통째로 사라지고(열은 시트마다 갈린다), 적어 둔 기록이 어느 달 것인지 모르게 된다.
TABLES = ("consulting_companies", "consulting_columns")


def _move(frm: str, to: str) -> None:
    for name in TABLES:
        table = sa.table(name, sa.column("sheet", sa.String))
        op.execute(table.update().where(table.c.sheet == frm).values(sheet=to))


def upgrade() -> None:
    _move(OLD, NEW)


def downgrade() -> None:
    _move(NEW, OLD)
