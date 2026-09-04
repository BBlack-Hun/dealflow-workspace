"""자료 자동 첨부를 **계정마다** 켜고 끈다 — 폴더를 넣는 것이 곧 권한이던 것을 푼다

## 무엇이 바뀌나

지금까지 자동 첨부(발송기가 IR 자료 파일을 붙여 보내는 길)를 켜는 문은
**하나뿐이었다.**

    `/setup` 에서 자료 폴더 경로를 넣는다  →  켜진다

그 칸(`agent_devices.ir_root`)은 **본인이 넣는다.** 그러니 문이 곧 스위치였고,
**누구든 스스로 켤 수 있었다.** 이 기능은 정해진 사람만 쓰기로 했는데, 코드에는
그 사람을 가릴 자리가 아예 없었다.

이제 판정은 칸 하나다(`deps.may_auto_attach` → `users.can_auto_attach_ir`).
`ir_root` 는 다시 **"어느 폴더인가"** 라는 제 뜻으로 돌아가고, **"쓸 수 있는가"**
는 관리자가 팀 현황에서 정한다. 옆칸 `can_view_consulting`(0007·0054) 과 같은
모양이다.

## 왜 데이터를 손대야 하나

**코드만 바꾸면 배포한 그 순간 사고가 난다.** 새 칸의 기본값은 `0` 이라, 지금
자료 폴더를 넣어 두고 발송기에게 자료를 맡기고 있는 계정이 **배포하는 그 순간
자동 첨부를 잃는다** — 아무도 끄지 않았는데. 그 사람은 다음 회차에 문구만
나간 것을 받는 쪽에서 알게 된다.

그래서 **지금 켜져 있는 계정을 켜 둔 상태로 옮긴다.** 무엇이 "지금 켜져 있는
계정" 인가는 옮기기 전 코드의 판정 그대로다 — `agent_devices.ir_root` 가
비어 있지 않은 계정(`services/ir_attach.py: auto_attach_enabled` 의 그때 모습).
공백만 든 값은 그 판정이 빈 것으로 보았으므로 여기서도 그렇게 본다.

정지된 계정(`is_active = 0`)도 함께 켠다 — 다시 살렸을 때 예전과 같아야 한다.
되살리는 자리가 권한까지 다시 챙기게 두면 그쪽이 낡는다(0054 와 같은 판단).

옮기고 나면 **화면에 보이는 것은 이전과 똑같고**, 달라지는 것은 이제부터
관리자가 끌 수 있다는 것뿐이다.

## 되돌리기

**칸을 지운다.** 되돌리면 코드도 함께 돌아가 판정이 다시 `ir_root 가 찼는가`
하나가 되는데, 그 코드는 이 칸을 아예 읽지 않는다 — 그러니 값을 되짚어 둘
자리가 없다. `ir_root` 는 손대지 않았으므로 내려간 순간 달라지는 것도 없다.

칸을 두고 내려가면 다음에 다시 올릴 때 무엇이 이 판이 켠 값이고 무엇이 사람이
켠 값인지 아무도 구분하지 못한다. 그때는 위 `upgrade()` 가 다시 돌아 **그 시점에
폴더가 찬 계정**을 기준으로 새로 세운다 — 그것이 이 판의 정의다.

Revision ID: 0059_ir_auto_attach_access
Revises: 0058_startup_db_one_liner
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0059_ir_auto_attach_access"
down_revision = "0058_startup_db_one_liner"
branch_labels = None
depends_on = None

TABLE = "users"
COLUMN = "can_auto_attach_ir"


def _has_column() -> bool:
    """빈 DB 길에서는 `0001` 이 모델 전체를 이미 만들어 둔다.

    그 자리에 또 붙이면 `duplicate column name` 으로 **부팅이 죽는다**
    (`tests/test_migrations.py` 가 지키는 규칙이다).
    """
    insp = sa.inspect(op.get_bind())
    if TABLE not in insp.get_table_names():
        return False
    return COLUMN in {c["name"] for c in insp.get_columns(TABLE)}


def _turn_on_whoever_has_a_folder() -> None:
    """지금 자동 첨부가 켜져 있는 계정 = **자료 폴더를 넣어 둔 계정.**

    옮기기 전 코드의 판정을 그대로 옮겨 적는다 — 이 판은 한 번 돌고 끝나므로
    그때 상태를 여기 굳혀 둔다(그 함수가 나중에 바뀌어도 이미 옮긴 데이터가
    따라 움직여서는 안 된다. 0054 가 `ROLES_ALWAYS_ON` 을 굳혀 둔 것과 같다).

    모델(`app.models`)을 부르지 않는다 — 마이그레이션은 **그때의 표**를 보아야
    하는데 모델은 늘 최신이라, 나중에 칸이 하나 늘면 옛 DB 에서 이 판이 없는
    칸을 찾는다.
    """
    users = sa.table(TABLE,
                     sa.column("id", sa.Integer),
                     sa.column(COLUMN, sa.Integer))
    devices = sa.table("agent_devices",
                       sa.column("user_id", sa.Integer),
                       sa.column("ir_root", sa.String))
    # 공백만 든 값은 켜진 것이 아니다 — 옮기기 전 판정이 `strip()` 뒤에 보았다.
    has_folder = sa.select(devices.c.user_id).where(
        devices.c.ir_root.isnot(None),
        sa.func.trim(devices.c.ir_root) != "")
    op.execute(users.update()
               .where(users.c.id.in_(has_folder))
               .values(**{COLUMN: 1}))


def upgrade() -> None:
    if not _has_column():
        # SQLite 의 `ADD COLUMN` 은 NOT NULL 에 기본값이 있어야 받는다.
        # 옆칸 `can_view_consulting`(0007) 과 같은 모양으로 붙인다.
        op.add_column(TABLE, sa.Column(COLUMN, sa.Integer(),
                                       nullable=False, server_default="0"))
    # 칸을 새로 붙였든(운영) 0001 이 이미 만들어 두었든(빈 DB) **똑같이 돈다.**
    # 빈 DB 에는 계정이 없어 아무 줄도 안 바뀌고, 운영에서는 이 한 줄이
    # 배포 순간의 사고를 막는다. 위 `if` 안에 넣으면 그 차이를 알아채기 어렵다.
    _turn_on_whoever_has_a_folder()


def downgrade() -> None:
    """칸을 지운다 — 위 `## 되돌리기` 참고."""
    if _has_column():
        op.drop_column(TABLE, COLUMN)
