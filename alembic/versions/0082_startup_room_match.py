"""스타트업 대표 카톡방 맞추기 — 확인 표시 한 칸, 후보 목록 한 칸

## 왜 두 칸인가

**적어 둔 이름**과 **그 이름이 진짜인지**와 **고를 수 있는 후보**는 서로
다른 것이다. 앞의 것은 이미 있다(`ir_companies.kakao_room_name`, 0070).

- `ir_companies.room_verified` — 그 제목을 카톡에서 확인했는가.
  `unverified | verified | ambiguous | not_found`. `vc_contacts.room_verified`
  와 **같은 모양·같은 값**이다. **발송을 막는 칸이 아니다** — 보낼 수 있는지는
  방 이름이 적혀 있는가 하나로 갈린다(`services/startup_send.rows`).
- `ir_companies.room_candidates` — 카톡에서 회사명으로 찾아 나온 **방 제목
  목록**(JSON). 방 제목은 규칙으로 지어낼 수 없어서, 사람이 고를 후보를
  담아 둘 자리가 필요했다(`services/room_match.py` 머리말).

## 빈 DB 에서는 아무 일도 하지 않는다

`0001_initial` 이 `create_all()` 로 지금 모델 전체를 만든다 — 새 DB 는 두 칸을
이미 갖고 시작한다. 그대로 `add_column` 하면 `duplicate column` 으로 **부팅이
죽는다**(`tests/test_migrations.py` 가 지키는 그것이다). 그래서 있는지 보고 넣는다.
0070 이 같은 표에 칸을 넣을 때 쓴 방식 그대로다.

## 이미 있는 줄에 무엇이 들어가나

`room_verified` 는 `server_default` 로 `unverified` 를 넣는다. NULL 로 두면
325줄이 "아직 모름" 도 아닌 빈 값을 지고, 읽는 쪽마다 `or "unverified"` 를
한 번씩 적게 된다 — 모델 기본값(`default="unverified"`)은 **새로 만드는 줄**
에만 걸리므로 이미 있는 줄은 이 판이 채워 줘야 한다.

`room_candidates` 는 NULL 로 둔다. **빈 목록과 안 찾아본 것은 다르다** —
빈 `{"rooms": []}` 를 넣어 두면 화면이 "찾았는데 0건" 으로 읽어서, 한 번도
안 찾아본 기업에 [카톡에서 방 찾기] 를 권하지 못한다.

## 되돌리기를 비워 두지 않는다

비어 있으면 그 판을 지나는 되돌리기 전체가 계획 단계에서 멎는다(0012 가 그랬다).
SQLite 는 `drop_column` 에 표를 다시 만들어야 해서 `batch_alter_table` 로 한다.
되돌려도 **잃는 것은 확인 표시와 후보 목록뿐**이고, 사람이 고른 방 이름은
`kakao_room_name` 에 남는다 — 그 칸은 이 판이 만든 것이 아니다.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0082_startup_room_match"
down_revision = "0081_consulting_field_stamps"
branch_labels = None
depends_on = None


def _columns(table: str) -> set:
    inspector = sa.inspect(op.get_bind())
    if table not in inspector.get_table_names():
        return set()
    return {c["name"] for c in inspector.get_columns(table)}


def upgrade() -> None:
    have = _columns("ir_companies")

    if "room_verified" not in have:
        # **`server_default` 를 반드시 준다.** 모델의 `default=` 는 ORM 이 줄을
        # 만들 때만 걸려서, ORM 을 지나지 않는 INSERT 가 터진다
        # (`IrCompany.room_verified` 에 적어 두었다). 기본값이 붙어 있으면
        # 이미 있는 325줄도 그 값으로 채워진다.
        #
        # `nullable=False` 는 **뜻을 적어 두는 것**이다 — SQLite 의
        # `ALTER TABLE ADD COLUMN` 은 이 칸에 `NOT NULL` 을 걸지 않고 기본값만
        # 남긴다(표를 통째로 다시 만들어야 걸린다). 빈 DB 로 선 쪽은
        # `create_all()` 이라 `NOT NULL` 이 걸린다 — 모양이 그만큼 갈리지만
        # **들어오는 값은 같다**(둘 다 `unverified`). 표를 다시 만드는 값이
        # 그 차이보다 크다.
        op.add_column("ir_companies",
                      sa.Column("room_verified", sa.String(), nullable=False,
                                server_default="unverified"))
        # 혹시 NULL 이 남는 DB(기본값을 안 쓰는 다른 엔진)에서도 모양을 맞춘다.
        op.execute("UPDATE ir_companies SET room_verified = 'unverified' "
                   "WHERE room_verified IS NULL")

    if "room_candidates" not in have:
        op.add_column("ir_companies",
                      sa.Column("room_candidates", sa.Text(), nullable=True))


def downgrade() -> None:
    have = _columns("ir_companies")
    if "room_candidates" in have:
        with op.batch_alter_table("ir_companies") as batch:
            batch.drop_column("room_candidates")
    if "room_verified" in have:
        with op.batch_alter_table("ir_companies") as batch:
            batch.drop_column("room_verified")
