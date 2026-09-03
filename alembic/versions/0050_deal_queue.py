"""딜 제안 관리의 **예약 큐** — 그룹 + 기업 묶음 + 문구를 미리 줄 세운다

## 무엇을 만드나

표 둘.

    deal_queue_items      예약 한 줄 — 그룹 이름 · 회차명 · 문구 · 상태
    deal_queue_companies  그 줄에 붙인 기업(순서 그대로)

## 왜 `deal_batches` 에 칸 하나를 더하지 않았나

`DealBatch` 는 모양만 보면 이미 `기업 묶음 + 문구` 라, `group_name` 한 칸만
더하면 될 것 같다. 그런데 그 표를 읽는 곳을 **전부 세어 보니** 회차를 세는
자리가 아니라 **"보낸 것" 을 세는 자리**였고, 예약 줄을 섞으면 세 곳이 조용히
틀린다.

  · `app/services/deal_history.py` 의 `last_sent_map` — `deal_batches` 를
    **조건 없이 통째로** 훑는다(WHERE 가 아예 없다). 예약 줄이 섞이면 아직
    안 보낸 기업이 `최근에 소개함` 으로 찍혀, 발송 화면의 기업 목록에서
    `최근 45일 내 소개한 N개 숨기기` 에 걸려 사라진다.
  · `app/routers/companies.py` 의 삭제 막이 — `deal_batch_companies` 에 줄이
    하나라도 있으면 **"이미 발송한 회차에 들어 있어"** 라며 막는다. 예약해
    둔 것뿐인데 보냈다고 말하는 거짓말이 된다.
  · `scripts/purge_demo.py` — `deal_batches` 를 **WHERE 없이 지운다**.
    데모 정리 한 번에 예약이 통째로 쓸려 나간다.

업무보고·대시보드 숫자는 전부 `send_jobs`/`send_items` 를 세고 있어서 그쪽은
영향이 없었다. 그래도 표를 나눈다 — `deal_batches` 에는 유일 제약도 자연키도
없어서, 칸 하나로 갈라 둔 것을 지켜 주는 것은 **앞으로 쓰는 모든 질의가 잊지
않고 거르는 것**뿐이기 때문이다. 이 저장소는 그것을 이미 한 번 놓쳤다
(`app/models.py` 의 `SEND_KINDS` 주석: "세는 곳이 여럿이라 각자 걸러 두면 한
곳이 빠진다 — 실제로 네 곳이 빠져 있었다"). 예약은 기록이 아니라 계획이라,
회차 이력과 같은 표에 있을 이유도 없다.

## 받는 사람은 담지 않는다

`deal_queue_items` 에는 **그룹 이름만** 있고 대상 명단 칸이 없다. 굳혀 두면
예약해 둔 사이에 카톡방을 나갔거나 `검토중단` 이 된 분께 그대로 나간다.
[시작] 을 누를 때 `sheet_owner.recipients` 로 그때의 명단을 다시 계산한다.

**예약 시각 칸도 없다.** 이 앱에는 예약을 실행할 장치가 일부러 없다(크론도
워커도 없다) — 시각 칸을 두면 화면은 약속을 하는데 지킬 사람이 없다.

## 두 번 돌려도 죽지 않는가

표가 이미 있으면 건너뛴다(0035 와 같은 방식). 마이그레이션이 도중에 끊기면
표만 만들어진 채로 남는데, 그대로 다시 돌리면 `table already exists` 로 죽고
다시 뜨는 크래시 루프가 된다 — 이 저장소에서 실제로 그렇게 멎었다.

## 되돌리면

표 둘을 지운다. **회차 이력은 하나도 안 건드린다** — 예약을 [시작] 하면 회차
(`deal_batches`)와 발송 잡이 따로 만들어지고, 그것들은 이 표를 참조하지 않는다.
잃는 것은 아직 안 누른 예약뿐이고, 그것은 이 표에서 처음 생긴 값이라 되돌릴
곳이 없다(0049 의 `deal_pitch` 와 같은 사정).

Revision ID: 0050_deal_queue
Revises: 0049_consulting_deal_pitch
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0050_deal_queue"
down_revision = "0049_consulting_deal_pitch"
branch_labels = None
depends_on = None

ITEMS = "deal_queue_items"
COMPANIES = "deal_queue_companies"
INDEX = "ix_deal_queue_items_user_id"


def _has_index(table: str, name: str) -> bool:
    insp = sa.inspect(op.get_bind())
    if table not in insp.get_table_names():
        return False
    return name in {i["name"] for i in insp.get_indexes(table)}


def upgrade() -> None:
    # **이미 있으면 건너뛴다.** 마이그레이션이 도중에 끊기면(컨테이너가 다시
    # 뜨는 등) 표만 만들어진 채로 남는데, 그대로 다시 돌리면 `table already
    # exists` 로 영영 못 지나간다 — 이 저장소에서 실제로 그렇게 멎었다
    # (0035 와 같은 방식).
    have = set(sa.inspect(op.get_bind()).get_table_names())

    if ITEMS not in have:
        op.create_table(
            ITEMS,
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"),
                      nullable=False),
            # **빈 문자열이 `(그룹 없음)` 이다** — NULL 이 아니다.
            # `sheet_owner.group_of()` 가 돌려주는 값을 그대로 담아야, 그룹이
            # 없다는 것을 말하는 방법이 두 가지가 되지 않는다(NULL 로 넣고
            # "" 로 찾는 날 예약이 조용히 사라진다).
            sa.Column("group_name", sa.String(), nullable=False,
                      server_default=""),
            sa.Column("title", sa.String(), nullable=False),
            sa.Column("opening_template_id", sa.Integer(),
                      sa.ForeignKey("message_templates.id"), nullable=True),
            sa.Column("closing_template_id", sa.Integer(),
                      sa.ForeignKey("message_templates.id"), nullable=True),
            # waiting | started | canceled — 이름은 app/services/deal_queue.py 에.
            sa.Column("status", sa.String(), nullable=False,
                      server_default="waiting"),
            # [시작] 으로 만들어진 발송 잡. 회차(`batch_id`)는 두지 않는다 —
            # 잡이 이미 들고 있어서, 두 벌로 두면 어긋날 자리만 생긴다.
            sa.Column("job_id", sa.Integer(), sa.ForeignKey("send_jobs.id"),
                      nullable=True),
            sa.Column("started_at", sa.String(), nullable=True),
            sa.Column("created_at", sa.String(), nullable=True),
            sa.Column("updated_at", sa.String(), nullable=True),
        )

    # **인덱스는 표를 만드는 것과 따로 본다.** 빈 DB 는 0001 의 `create_all()` 이
    # 표를 이미 만들어 둔 채로 오는데, 모델에는 이 인덱스가 선언돼 있지 않다.
    # 표 만들기 안에 넣어 두면 그 길에서 통째로 건너뛰어, **새 서버만 인덱스
    # 없이** 도는 DB 가 된다(0005 가 쓰는 방식).
    if not _has_index(ITEMS, INDEX):
        op.create_index(INDEX, ITEMS, ["user_id"])

    if COMPANIES not in have:
        op.create_table(
            COMPANIES,
            sa.Column("item_id", sa.Integer(),
                      sa.ForeignKey("deal_queue_items.id"), primary_key=True),
            sa.Column("company_id", sa.Integer(),
                      sa.ForeignKey("ir_companies.id"), primary_key=True),
            # 순서가 곧 문구의 번호다(`1번 기업 …`) — 뒤섞이면 받는 쪽이
            # 기억하는 번호와 어긋난다.
            sa.Column("position", sa.Integer(), nullable=False,
                      server_default="1"),
        )


def downgrade() -> None:
    have = set(sa.inspect(op.get_bind()).get_table_names())
    # 자식 표를 먼저 지운다 — 부모를 먼저 지우면 참조가 남는다.
    if COMPANIES in have:
        op.drop_table(COMPANIES)
    if ITEMS in have:
        if _has_index(ITEMS, INDEX):
            op.drop_index(INDEX, table_name=ITEMS)
        op.drop_table(ITEMS)
