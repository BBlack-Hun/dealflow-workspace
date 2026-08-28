"""명단마다 다른 표 — 배치 · 숨김 · 달마다 늘어나는 열

투자사 관리 현황에 **성격이 다른 명단**이 섞여 있었다. 스타트업 리마인드
명단은 투자사 명함 칸(부서·직함·근무처 팩스·명함 등록일)을 그대로 쓰고 있어
대부분의 칸이 비었고, 그러면서도 투자사 수에는 함께 세어져 있었다.

세 가지를 더한다.

  sheet_owners.layout     이 명단을 어떤 표로 보여 줄지(칸 배치)
  sheet_owners.is_hidden  투자사로 세지 않는 명단인지
  contact_columns         달마다 하나씩 늘어나는 열(`7월 리마인드 TEL` …)
  vc_contacts.notes       그 열들과 명단 전용 칸의 값 {"칸키": "내용"}

**이름으로 거르지 않는다.** 명단 이름을 코드에 심으면 다음 명단에서 또 심어야
하고, 심는 것을 잊은 화면만 조용히 틀린 수를 보여 준다.

Revision ID: 0037_contact_list_layout
Revises: 0036_local_time_storage
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0037_contact_list_layout"
down_revision = "0036_local_time_storage"
branch_labels = None
depends_on = None


def _inspector():
    return sa.inspect(op.get_bind())


def _has_table(name: str) -> bool:
    return name in _inspector().get_table_names()


def _has_column(table: str, column: str) -> bool:
    return column in {c["name"] for c in _inspector().get_columns(table)}


def _has_index(table: str, name: str) -> bool:
    return name in {i["name"] for i in _inspector().get_indexes(table)}


# 이 저장소는 **같은 마이그레이션을 두 번 돌리는 일이 실제로 있다** — 스탬프가
# 어긋난 DB 로 컨테이너가 뜨면 `duplicate column name` 으로 죽고, 다시 뜨고,
# 또 죽는 크래시 루프가 된다. 담당자 306명이 든 DB 라 그 상태로는 손댈 수도
# 없다. 그래서 있으면 건너뛴다(0002·0003·0004 가 쓰는 방식과 같다).

_SHEET_OWNER_COLUMNS = [
    # 기존 명단은 전부 투자사 명함 표다 — 지금 보이는 것이 바뀌면 안 된다.
    ("layout", lambda: sa.Column("layout", sa.String(), nullable=False,
                                 server_default="investor")),
    ("is_hidden", lambda: sa.Column("is_hidden", sa.Integer(), nullable=False,
                                    server_default="0")),
]

_CONTACT_COLUMNS = [
    ("notes", lambda: sa.Column("notes", sa.Text(), nullable=True)),
    # 줄 단위 숨김. 원본 시트가 17~32번 줄을 숨긴 채로 돌아다녀서, 열여섯 줄만
    # 보고 "없는 기업" 이라고 판단한 일이 있었다 — 앱에도 같은 조작이 필요하지만
    # 되돌릴 길은 화면에 보여야 한다.
    ("is_hidden", lambda: sa.Column("is_hidden", sa.Integer(), nullable=False,
                                    server_default="0")),
]


def upgrade() -> None:
    for table, columns in (("sheet_owners", _SHEET_OWNER_COLUMNS),
                           ("vc_contacts", _CONTACT_COLUMNS)):
        missing = [make() for name, make in columns if not _has_column(table, name)]
        if missing:
            with op.batch_alter_table(table) as b:
                for column in missing:
                    b.add_column(column)

    if not _has_table("contact_columns"):
        op.create_table(
            "contact_columns",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("sheet", sa.String(), nullable=False),
            sa.Column("label", sa.String(), nullable=False),
            sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.String(), nullable=True),
            sa.Column("updated_at", sa.String(), nullable=True),
        )
    # 표를 그릴 때마다 명단 하나의 열을 순서대로 읽는다.
    if not _has_index("contact_columns", "ix_contact_columns_sheet"):
        op.create_index("ix_contact_columns_sheet", "contact_columns", ["sheet"])


def downgrade() -> None:
    if _has_index("contact_columns", "ix_contact_columns_sheet"):
        op.drop_index("ix_contact_columns_sheet", table_name="contact_columns")
    if _has_table("contact_columns"):
        op.drop_table("contact_columns")
    for table, columns in (("vc_contacts", _CONTACT_COLUMNS),
                           ("sheet_owners", _SHEET_OWNER_COLUMNS)):
        present = [name for name, _make in columns if _has_column(table, name)]
        if present:
            with op.batch_alter_table(table) as b:
                for name in present:
                    b.drop_column(name)
