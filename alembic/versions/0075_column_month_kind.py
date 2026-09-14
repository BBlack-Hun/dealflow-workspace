"""달마다 늘어나는 칸의 **달·종류를 이름에서 값으로** 올린다

## 왜 지금인가

`contact_columns` · `consulting_columns` 는 달마다 칸이 는다(`9월 리마인드 문자`
· `9월 마지막주 리마인드 카톡  or  TEL`). 어느 달 칸인지는 **이름 안에만** 있어,
그것을 묻는 자리마다 이름을 다시 뜯는다. 그리고 이름에는 **해가 없다** — 12월
칸과 1월 칸이 나란히 서면 어느 해 것인지 이름으로는 가릴 수가 없다.

달을 고르면 그 달 값만 보이는 화면으로 가려면 먼저 **달이 값이어야** 한다.
이 판이 그 첫 걸음이고, 여기서는 아직 **아무도 이 두 칸을 읽지 않는다.**

## 값을 한 글자도 옮기지 않는다

칸 행도, 줄마다의 값도 그대로다. `VcContact.notes` 의 열쇠(`c{id}`)와
`ConsultingCompany.notes` 의 열쇠(`{id}`)도 그대로 둔다 — 열쇠를 다시 적는
이전은 한 줄만 어긋나도 기록이 화면에서 통째로 사라진다(0039·0067 이 그
유형이다). `label` 도 그대로다. 원본 시트·엑셀과 나란히 놓고 대조하는 글자다.

**이 판은 `UPDATE` 만 한다.** `INSERT` 도 `DELETE` 도 없다.

## 달을 어떻게 읽나 — 확실한 것부터 셋

1. **세운 기록과 맞춰 본다.** `monthly_column_runs` 는 앱이 그 달 칸을 세우면서
   무슨 이름으로 세웠는지 적어 둔 줄이다(`labels`). 그 표(`target`·`scope`) 몫에
   이 이름이 있으면 해까지 그 줄이 말해 준다 — 짐작이 아니다.
2. **만들어진 날에서 거꾸로 센다.** 기록이 없으면(시트에서 실려 온 옛 칸들)
   이름의 달까지 `created_at` 에서 거꾸로 몇 달인지 세어 해를 물린다.
   `services/monthly_columns.months_back` 이 그 셈이고, 새 달 칸의 본을 고를 때
   쓰는 것과 **같은 셈**이다.
3. **못 읽으면 비워 둔다.** `카톡방 연결여부` 처럼 애초에 월별 칸이 아닌 것들이다.
   `month` · `kind` 둘 다 `NULL` 로 남기고 손대지 않는다 — 지어내면 없던 달이
   생기고, 그 달을 고른 사람에게 엉뚱한 칸이 보인다.

`kind` 는 이름에서 달과 보낸날을 뗀 뒷말이다(`services/monthly_columns.kind_of`).
**앱이 새 달 칸 이름을 지을 때 남겨 두는 바로 그 부분**이라, 규칙을 새로 만들지
않고 그 함수를 그대로 부른다 — 두 벌이 되면 어느 날 한쪽만 고쳐져, 새로 서는
칸과 여기서 읽어 낸 뒷말이 서로 다른 글자가 된다. 안쪽 공백은 줄이지 않는다
(`마지막주 리마인드 카톡  or  TEL` 의 두 칸짜리 공백은 시트에 그대로 있다).

## 되돌리기

칸 둘을 지운다(SQLite 라 `batch_alter_table`). 값을 한 글자도 안 옮겼으므로
**되돌린 DB 는 이전 전과 같은 자료**다 — `scripts/check_month_backfill.py` 가
`notes` 열쇠 집합의 해시로 그것을 잰다.

Revision ID: 0075_column_month_kind
Revises: 0074_company_amounts_as_text
"""
from __future__ import annotations

import json
from datetime import date, datetime

import sqlalchemy as sa
from alembic import op

revision = "0075_column_month_kind"
down_revision = "0074_company_amounts_as_text"
branch_labels = None
depends_on = None

# (표 이름, `MonthlyColumnRun.target` 값) — 두 표가 같은 모양이라 같은 길을 간다.
TABLES = (("contact_columns", "contact"), ("consulting_columns", "consulting"))


def _has_column(table: str, column: str) -> bool:
    return column in {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def _as_date(raw) -> date | None:
    """`created_at` 의 앞 열 글자만 본다 — 시각도 시간대도 달을 가리지 않는다."""
    if isinstance(raw, datetime):
        return raw.date()
    if isinstance(raw, date):
        return raw
    try:
        return datetime.strptime(str(raw)[:10], "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def _runs(bind, target: str) -> dict:
    """`{표: {이름: [달, …]}}` — 앱이 그 칸을 세우며 적어 둔 기록."""
    if "monthly_column_runs" not in sa.inspect(bind).get_table_names():
        return {}
    out: dict = {}
    for scope, month, labels in bind.execute(sa.text(
            "SELECT scope, month, labels FROM monthly_column_runs "
            "WHERE target = :t ORDER BY id"), {"t": target}).all():
        try:
            names = json.loads(labels or "[]")
        except (TypeError, ValueError):
            continue
        if not isinstance(names, list):
            continue
        per_sheet = out.setdefault(scope or "", {})
        for name in names:
            if isinstance(name, str):
                per_sheet.setdefault(name, []).append(month)
    return out


def _backfill(bind, table: str, target: str) -> None:
    """이름에만 있던 달·종류를 값으로 올린다. **`UPDATE` 만 한다.**"""
    # 마이그레이션이 규칙을 따로 갖지 않는다 — 앱이 새 달 칸 이름을 지을 때
    # 쓰는 그 함수를 그대로 부른다(0074 도 `services.amount` 를 이렇게 쓴다).
    from app.services import monthly_columns as mc

    runs = _runs(bind, target)
    rows = bind.execute(sa.text(
        f"SELECT id, sheet, label, created_at FROM {table} ORDER BY id")).all()
    for col_id, sheet, label, created in rows:
        month = mc.month_key_of(label, _as_date(created), runs.get(sheet or "", {}))
        if month is None:
            # 달을 못 읽는 칸은 **손대지 않는다.** 이미 들어 있는 값이 있어도
            # 마찬가지다 — 여기서 비우면 사람이 적어 둔 것을 지우는 셈이다.
            continue
        bind.execute(
            sa.text(f"UPDATE {table} SET month = :m, kind = :k WHERE id = :i"),
            {"m": month, "k": mc.kind_of(label), "i": col_id})


def upgrade() -> None:
    bind = op.get_bind()
    for table, target in TABLES:
        # **두 번 돌려도 죽지 않아야 한다.** `0001_initial` 이 `create_all()` 로
        # 지금 모델 전체를 만들기 때문에 빈 DB 는 이 칸을 이미 갖고 시작한다
        # (`tests/test_migrations.py` 가 지키는 그것이다).
        for column in ("month", "kind"):
            if not _has_column(table, column):
                op.add_column(table, sa.Column(column, sa.String(), nullable=True))
        _backfill(bind, table, target)


def downgrade() -> None:
    # **되돌리기가 비어 있으면 그 판을 지나는 되돌리기 전체가 계획 단계에서
    # 멎는다**(0012 가 그랬다 — `tests/test_migrations.py` 참고).
    # 값을 안 옮겼으므로 이 둘을 지우면 이전 전과 같은 자료로 돌아간다.
    for table, _ in TABLES:
        # 있는 것만 지운다. 빈 `batch_alter_table` 로도 들어가지 않는다 —
        # SQLite 에서 그 블록은 표를 다시 만들어 옮기는 길이라, 할 일이 없는데도
        # 지나가게 두면 아무 이유 없이 표를 통째로 옮겨 쓰는 셈이다.
        drop = [c for c in ("month", "kind") if _has_column(table, c)]
        if not drop:
            continue
        with op.batch_alter_table(table) as batch:
            for column in drop:
                batch.drop_column(column)
