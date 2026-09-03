"""IR 자료 폴더 자리를 **기기마다** 들고 있는다

## 무엇이 바뀌나

IR 자료 파일은 이제 **사람이 PC 카톡에서 직접 첨부**하는 대신 발송기가 붙여
보낸다(0053 에서 구글 드라이브 링크 방식을 폐기했다). 그러려면 발송기가 그 PC 의
**어느 폴더**를 뒤져야 하는지 알아야 하는데, 그 자리는 PC 마다 다르다.

`agent_devices` 에 칸 하나를 더한다. 값은 **본인이 웹에서 넣고**, 발송기가
박동(`POST /api/agent/heartbeat`) 응답으로 받아 간다.

## 왜 `users` 가 아니라 `agent_devices` 인가

계정이 아니라 **기기**의 성질이기 때문이다. `hostname`·`sender` 와 같은 자리다.
같은 사람이 PC 를 바꾸면 함께 바뀌어야 하고, 계정에 매달아 두면 PC 를 옮긴 날
엉뚱한 경로를 그대로 들고 간다. `agent_devices` 는 이미 `user_id` 가 유일해서
사람마다 한 줄이라, 계정별 설정을 두는 자리로도 그대로 맞는다.

## 왜 `config.yaml` 이 아닌가

발송기를 새로 내려받으면 서버가 `config.yaml` 을 즉석에서 다시 만든다
(`app/routers/setup.py: CONFIG_TEMPLATE`). 손으로 적어 둔 값은 그때 데모 값으로
되돌아간다. 서버가 들고 있으면 갱신해도 남는다.

## 되돌리기

칸을 지운다. 값은 사람이 화면에서 다시 넣으면 되는 것이고, 이 칸이 없으면
발송기는 "자료 폴더가 정해지지 않았다"고 **분명히 실패한다** — 조용히 아무 데나
뒤지지 않으므로 내려간 상태로도 위험하지 않다.

Revision ID: 0055_agent_ir_root
Revises: 0054_consulting_per_account
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0055_agent_ir_root"
down_revision = "0054_consulting_per_account"
branch_labels = None
depends_on = None

TABLE = "agent_devices"
COLUMN = "ir_root"


def _has_column() -> bool:
    """빈 DB 길에서는 `0001` 이 모델 전체를 이미 만들어 둔다.

    그 자리에 또 붙이면 `duplicate column name` 으로 **부팅이 죽는다**
    (`tests/test_migrations.py` 가 지키는 규칙이다).
    """
    bind = op.get_bind()
    cols = sa.inspect(bind).get_columns(TABLE)
    return any(c["name"] == COLUMN for c in cols)


def upgrade() -> None:
    if not _has_column():
        op.add_column(TABLE, sa.Column(COLUMN, sa.String(), nullable=True))


def downgrade() -> None:
    if _has_column():
        op.drop_column(TABLE, COLUMN)
