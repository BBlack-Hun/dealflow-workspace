"""`월간 계약 업무현황표` — 한 칸에 뭉쳐 있던 줄을 칸으로 나눈다

## 무엇이 뭉쳐 있었나

그 시트는 머리글 있는 표가 아니라 월 묶음 아래 슬래시 한 줄이었다.

    6월  (무료계약 2개사 / 유료계약 3개사)
    기업명 / 계약금액 / 성공보수율 / 계약일
    ○○○/ 무료/ 3.5%/ 미정

읽어 오면서 다른 탭의 칸을 빌려 담았다 — `지역` 칸에 `6월`, `기업 관리` 칸에
`무료`/`유료`, 그리고 **네 가지가 `기업명` 한 칸에** 들어갔다. 한 칸에 뭉쳐
있으면 계약금으로 거를 수도, 보수율만 고칠 수도 없다.

## 어느 조각이 어느 칸인가 — 시트가 적어 두었다

추측이 아니다. 시트의 그 줄 바로 위에 머리글이 있다:
`기업명 / 계약금액 / 성공보수율 / 계약일`. 그 순서를 그대로 따른다.

## 조각 수가 줄마다 다르면

  모자라면  뒤 칸을 비워 둔다. 시트에서 빠지는 것은 늘 뒤쪽이다
            (`○○/ 무료/ 4%` = 계약일이 아직 없다). 앞에서 채우면 보수율 칸에
            계약일이 들어가고, 그때는 어느 것이 밀린 값인지 알 수가 없다.
  넘치면    남는 조각을 마지막 칸에 그대로 이어 둔다. 버리면 시트에 있던 값이
            앱에서 사라진다.

값은 **적힌 그대로** 옮긴다. `3%` 인지 `3프로` 인지, `유료 90만` 인지는
계약서에 적힌 말이라 앱이 고쳐 쓸 것이 아니다.

## 되돌릴 수 있는가

`source_line` 에 **나누기 전 한 줄**을 그대로 남긴다. 나눈 결과가 틀렸으면
거기서 다시 나눌 수 있고, `downgrade` 는 그 값을 `company_name` 으로 되돌린다.

`계약일` 이 이미 적혀 있는 줄은 **아예 건드리지 않는다.** 그 칸은 다른 탭에서
`미팅일` 로 쓰던 자리라, 값이 있는데 덮으면 되돌릴 근거가 없다.

## 두 번 돌려도 죽지 않는가

칸은 있으면 건너뛴다(0037 이 쓰는 방식과 같다 — 스탬프가 어긋난 DB 로 컨테이너가
뜨면 `duplicate column name` 으로 죽고 다시 뜨는 크래시 루프가 된다).
나누기는 `source_line IS NULL` 인 줄만 보므로 두 번째에는 걸리는 줄이 0이다.

Revision ID: 0040_contract_sheet_columns
Revises: 0039_consulting_startup_tab
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0040_contract_sheet_columns"
down_revision = "0039_consulting_startup_tab"
branch_labels = None
depends_on = None

SHEET = "월간 계약 업무현황표"

# 시트가 적어 둔 순서. `app/routers/consulting.py` 의 `CONTRACT_PARTS` 와 같은
# 값이다 — **일부러 베껴 둔다.** 마이그레이션은 돌아간 그때의 규칙으로 고정되어야
# 하는데, 앱 함수를 불러 쓰면 나중에 규칙이 바뀌는 순간 이미 돌아간 마이그레이션의
# 뜻까지 소급해 바뀐다. 둘이 갈리지 않는 것은 테스트가 지킨다
# (`tests/test_consulting_contract_sheet.py`).
PARTS = ["company_name", "contract_fee", "success_fee", "meeting_at"]

_NEW_COLUMNS = [
    ("success_fee", lambda: sa.Column("success_fee", sa.String(), nullable=True)),
    ("contract_fee", lambda: sa.Column("contract_fee", sa.String(), nullable=True)),
    ("source_line", lambda: sa.Column("source_line", sa.Text(), nullable=True)),
]


def _has_column(table: str, column: str) -> bool:
    return column in {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def split_contract_line(line: str) -> dict:
    """`기업명/ 유료 90만/ 3프로/ 미정` → 칸마다 하나씩. 나눌 것이 없으면 빈 dict."""
    parts = [p.strip() for p in (line or "").split("/")]
    if len(parts) < 2:
        return {}
    out = dict(zip(PARTS, parts))
    if len(parts) > len(PARTS):
        out[PARTS[-1]] = " / ".join(parts[len(PARTS) - 1:])
    return out


def _table() -> sa.Table:
    return sa.table(
        "consulting_companies",
        sa.column("id", sa.Integer),
        sa.column("sheet", sa.String),
        sa.column("company_name", sa.Text),
        sa.column("meeting_at", sa.String),
        sa.column("success_fee", sa.String),
        sa.column("contract_fee", sa.String),
        sa.column("source_line", sa.Text),
    )


def upgrade() -> None:
    missing = [make() for name, make in _NEW_COLUMNS
               if not _has_column("consulting_companies", name)]
    if missing:
        with op.batch_alter_table("consulting_companies") as b:
            for column in missing:
                b.add_column(column)

    t = _table()
    bind = op.get_bind()
    rows = bind.execute(
        sa.select(t.c.id, t.c.company_name).where(
            t.c.sheet == SHEET,
            t.c.source_line.is_(None),
            t.c.company_name.like("%/%"),
            # 계약일 자리에 이미 값이 있는 줄은 건드리지 않는다 — 덮으면
            # 되돌릴 근거가 없다.
            sa.func.coalesce(t.c.meeting_at, "") == "",
        )
    ).all()

    for row_id, line in rows:
        parts = split_contract_line(line)
        if not parts:
            continue
        bind.execute(t.update().where(t.c.id == row_id).values(
            source_line=line,
            company_name=parts.get("company_name") or line,
            contract_fee=parts.get("contract_fee"),
            success_fee=parts.get("success_fee"),
            meeting_at=parts.get("meeting_at"),
        ))


def downgrade() -> None:
    """나눈 것만 되돌린다 — `source_line` 이 있는 줄이 그것이다."""
    t = _table()
    bind = op.get_bind()
    if _has_column("consulting_companies", "source_line"):
        bind.execute(
            t.update().where(t.c.source_line.isnot(None)).values(
                company_name=t.c.source_line,
                meeting_at=None, success_fee=None, contract_fee=None,
                source_line=None)
        )
    present = [name for name, _make in _NEW_COLUMNS
               if _has_column("consulting_companies", name)]
    if present:
        with op.batch_alter_table("consulting_companies") as b:
            for name in present:
                b.drop_column(name)
