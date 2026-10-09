"""스타트업 명단 줄의 카톡방 후보 — 칸 하나

`vc_contacts.room_candidates` — 좌측 [스타트업] 명단 줄을 회사명으로 카톡에서
찾아 나온 **방 제목 목록**(JSON). 사람이 [방 매칭] 화면에서 골라 확정한다
(`services/startup_room_pick.py`). 모양은 `ir_companies.room_candidates`(0082)와
같고, 읽고 쓰는 함수도 같다(`services/room_match.save_candidates` · `candidates`).

## 이미 있는 줄은 NULL 이다

**빈 목록과 안 찾아본 것은 다르다** — 0082 와 같은 까닭이다. 빈 `{"rooms": []}`
를 넣어 두면 화면이 "찾았는데 0건" 으로 읽어서, 한 번도 안 찾아본 줄에
[방 후보 찾기] 를 권하지 못한다.

## 빈 DB 에서는 아무 일도 하지 않는다

`0001_initial` 이 `create_all()` 로 지금 모델 전체를 만들어, 새 DB 는 이 칸을
이미 갖고 시작한다. 있는지 보고 넣는다(0082 · 0084 와 같은 방식).

## 되돌리기

되돌려도 잃는 것은 **후보 목록뿐**이다. 사람이 확정한 방 이름은
`kakao_room_name` 에 남는다 — 그 칸은 이 판이 만든 것이 아니다.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0085_contact_room_candidates"
down_revision = "0084_send_job_topic"
branch_labels = None
depends_on = None


def _columns(table: str) -> set:
    inspector = sa.inspect(op.get_bind())
    if table not in inspector.get_table_names():
        return set()
    return {c["name"] for c in inspector.get_columns(table)}


def upgrade() -> None:
    have = _columns("vc_contacts")
    if not have:
        return
    if "room_candidates" not in have:
        op.add_column("vc_contacts",
                      sa.Column("room_candidates", sa.Text(), nullable=True))


def downgrade() -> None:
    if "room_candidates" in _columns("vc_contacts"):
        with op.batch_alter_table("vc_contacts") as batch:
            batch.drop_column("room_candidates")
