"""IR 기업 연결 — 칸 둘

- `vc_contacts.ir_company_id` — 좌측 [스타트업] 명단 줄이 IR 기업 현황의 어느
  기업인가.
- `consulting_companies.ir_company_id` — 투자컨설턴트 줄이 어느 기업인가.

둘 다 `ir_companies.id` 를 가리키고 **비어 있어도 된다**(아직 안 이었다).
잇는 것은 사람이다(`/ir-link` · `services/ir_link.py`). 이 판은 칸만 세운다 —
값을 하나도 채우지 않는다. 이름이 같다고 저절로 이어 두면, 같은 이름의 IR
기업이 둘인 곳에서 엉뚱한 쪽에 붙는다.

## 외래키를 칸에 붙여서 세운다

`op.add_column` 에 `ForeignKey` 를 실으면 SQLite 에서는 알렘빅이 제약을 **경고만
남기고 건너뛴다**(ALTER 로 제약을 못 붙인다). 그러면 빈 DB 로 세운 서버
(`0001_initial` 의 `create_all` — 외래키가 있다)와 이 판을 지난 서버의 표가
갈린다. SQLite 는 `ADD COLUMN … REFERENCES …` 는 받으므로 그 한 줄을 그대로
쓴다 — 표를 통째로 다시 만들지 않는다(`vc_contacts` 를 가리키는 표가 여럿이다).

## 빈 DB 에서는 아무 일도 하지 않는다

`0001_initial` 이 지금 모델 전체를 만들어 새 DB 는 이 칸을 이미 갖고 시작한다.
있는지 보고 넣는다(0082 · 0084 · 0085 · 0086 과 같은 방식).

## 판 순서

처음에는 `0086_send_guard` 위의 `0088` 이었다. main 이 0087~0095 를 먼저 썼고
열려 있는 손 기록 되돌리기 판(`0096_activity_sequence_trace`, #268)이 그 위에
서서, 이 판은 그 다음(`0097`)에 선다 — 이 판은 #268 위에 쌓였다. 같은 부모를
둘이 가리키면 머리가 둘이 되어 부팅에서 멎는다(`tests/test_migrations.py` 가 잡는다).

## 되돌리기

되돌리면 **이어 둔 것만** 사라진다(기업 줄 · 명단 줄 · 컨설턴트 줄은 그대로).
외래키가 걸린 칸은 SQLite 가 `DROP COLUMN` 을 거절하므로 표를 다시 만드는
길(`batch_alter_table`)로 뺀다.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0097_ir_company_link"
down_revision = "0096_activity_sequence_trace"
branch_labels = None
depends_on = None

COLUMN = "ir_company_id"
TABLES = ("vc_contacts", "consulting_companies")


def _columns(table: str) -> set:
    inspector = sa.inspect(op.get_bind())
    if table not in inspector.get_table_names():
        return set()
    return {c["name"] for c in inspector.get_columns(table)}


def upgrade() -> None:
    sqlite = op.get_bind().dialect.name == "sqlite"
    for table in TABLES:
        have = _columns(table)
        if not have or COLUMN in have:
            continue
        if sqlite:
            op.execute(f"ALTER TABLE {table} ADD COLUMN {COLUMN} INTEGER "
                       f"REFERENCES ir_companies (id)")
        else:
            op.add_column(table, sa.Column(
                COLUMN, sa.Integer(), sa.ForeignKey("ir_companies.id"),
                nullable=True))


def downgrade() -> None:
    for table in TABLES:
        if COLUMN in _columns(table):
            with op.batch_alter_table(table) as batch:
                batch.drop_column(COLUMN)
