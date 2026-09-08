"""투자컨설턴트 월 칸을 **사람마다**에서 **탭마다**로

## 왜 지금인가

`consulting_columns` 는 오래 `user_id` 를 달고 있었다. 컨설턴트가 한 사람뿐인
동안에는 사람과 탭이 일대일이라 아무 차이가 없었다 — 운영의 월 칸 여덟 개가
전부 한 사람 것이고, 그 사람 표를 열면 그 여덟 개가 그대로 선다.

**두 사람째가 들어오는 순간** 그 전제가 깨진다. 이 화면의 본래 자리는 팀이
컨설턴트들의 표를 `담당: 전체` 로 나란히 놓고 보는 자리인데
(`routers/consulting.py` 의 `scope`), 거기서 세 가지가 한꺼번에 무너진다.

  · 머리글이 `8월 마지막주 리마인드 …` · `8월 마지막주 리마인드 …` 로 **사람
    수만큼 겹쳐** 서고, 줄마다 자기 담당의 칸에만 값이 있어 표의 절반이 늘
    빈칸이다. 어느 칸이 누구 것인지는 화면 어디에도 안 나온다.
  · `지난달 리마인드 미완료` KPI 가 거짓말을 한다. 지난달 칸을 **이름으로**
    찾는데(`_prev_month_label`) 먼저 걸린 한 사람의 칸만 보므로, 나머지
    담당의 줄은 그 칸이 비어 있어 전부 미완료로 세어진다.
  · 담당을 옮기면 그 줄의 기록이 통째로 안 보인다. `notes` 의 열쇠가 옛
    담당의 칸 id 인데 새 담당의 표에는 그 칸이 없다.

## 왜 탭마다가 맞나

탭 셋(스타트업 → 경영본부 전달 → 계약)은 팀이 함께 쓰는 **업무 단계**다
(`models.ConsultingSheet`). `마지막주 리마인드` 는 그 단계의 리듬이지 사람의
취향이 아니다 — 사람마다 다른 달을 챙기는 표가 아니라, 같은 달을 각자의
기업에 대해 챙기는 표다.

같은 모양을 옆 표가 이미 그렇게 풀어 두었다. `contact_columns` 는 처음부터
**명단마다**이고 자동 생성도 명단 단위로 돈다. 같은 모양에 장치를 두 벌 두면
배울 것도 고칠 곳도 두 벌이 된다.

## 무엇을 합치나 — **이름이 같으면 같은 칸이다**

탭 안에서 `label` 이 같은 칸들을 하나로 모은다. 남기는 것은 **id 가 가장 작은
칸**(먼저 만들어진 칸)이고, 없어지는 칸을 가리키던 `notes` 의 열쇠는 남는 칸의
id 로 **다시 적는다**. 이 다시 적기를 빼먹으면 기록이 화면에서 통째로 사라진다
— 값은 JSON 에 그대로 있는데 그 열쇠에 해당하는 칸이 없어 아무 데도 안 붙는다.
0039 가 고쳐야 했던 유형이라 여기서 같이 옮긴다.

이름이 다른 칸은 **합치지 않는다.** `8월 마지막주 리마인드 톡 or TEL` 과
`8월 리마인드` 는 같은 달이지만 같은 칸이 아니다 — 시트가 그렇게 부르고 있고,
이 저장소는 적힌 것을 고쳐 쓰지 않는다. 같은 달 칸이 둘 서 있는 것은 사람이
보고 정리할 일이지 마이그레이션이 단정할 일이 아니다.

`user_id` 만 있고 `sheet` 가 빈 옛 칸은 모델 기본값(`스타트업`)이 아니라 **적혀
있는 그대로** 둔다. 빈 값끼리는 빈 값끼리 합쳐진다.

## 자동 생성 기록도 같이 옮긴다

`monthly_column_runs.scope` 가 투자컨설턴트 쪽에서 `"{user_id}:{탭}"` 이었다.
그대로 두면 새 열쇠(`"{탭}"`)로는 그 달을 아무도 안 맡은 것이 되어, 사람이
지운 이번 달 칸이 다음 요청에 되살아난다. 열쇠를 다시 적고, 같은 (탭, 달) 이
둘 이상이면 하나만 남긴다 — 그 표에서 그 달은 한 번 선 것이다.

## 되돌리기

`user_id` 를 다시 세우되 **비워 둔다.** 합치면서 어느 칸이 누구 것이었는지가
사라졌고, 지어내면 남의 표에 없던 칸이 생긴다. 되돌린 직후에는 컨설턴트 화면에
월 칸이 안 보이고(옛 코드가 `user_id` 로 걸렀다) 관리자가 배정하면 된다 —
**칸에 적힌 기록은 `notes` 에 그대로 남는다.** 다시 올리면 같은 자리로 돌아온다.

Revision ID: 0067_consulting_columns_per_sheet
Revises: 0066_ir_meeting_offered_at
"""
from __future__ import annotations

import json

import sqlalchemy as sa
from alembic import op

revision = "0067_consulting_columns_per_sheet"
down_revision = "0066_ir_meeting_offered_at"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    return column in {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def _merge_columns(bind) -> None:
    """탭 안에서 이름이 같은 칸을 하나로. `notes` 의 열쇠를 다시 적는다."""
    rows = bind.execute(sa.text(
        "SELECT id, sheet, label FROM consulting_columns ORDER BY id")).all()
    keep: dict = {}
    remap: dict = {}
    for col_id, sheet, label in rows:
        key = (sheet or "", label or "")
        if key in keep:
            remap[str(col_id)] = str(keep[key])
        else:
            keep[key] = col_id
    if not remap:
        return
    # 기록을 먼저 옮기고 칸을 지운다. 순서가 반대면 지운 칸을 가리키는 열쇠가
    # 잠깐 남는데, 그 사이에 죽으면 되살릴 근거가 없다.
    for row_id, notes in bind.execute(sa.text(
            "SELECT id, notes FROM consulting_companies "
            "WHERE notes IS NOT NULL AND notes != ''")).all():
        try:
            values = json.loads(notes)
        except (TypeError, ValueError):
            continue
        if not isinstance(values, dict) or not (values.keys() & remap.keys()):
            continue
        merged: dict = {}
        for key, value in values.items():
            target = remap.get(key, key)
            # 두 칸에 다 적혀 있으면 **둘 다 남긴다.** 하나를 버리면 사람이
            # 적어 둔 글이 조용히 사라진다 — 어느 쪽이 맞는지는 아무도 모른다.
            if merged.get(target) and value and merged[target] != value:
                merged[target] = f"{merged[target]} / {value}"
            elif value:
                merged[target] = value
        bind.execute(
            sa.text("UPDATE consulting_companies SET notes = :n WHERE id = :i"),
            {"n": json.dumps(merged, ensure_ascii=False), "i": row_id})
    bind.execute(sa.text(
        "DELETE FROM consulting_columns WHERE id IN ("
        + ",".join(str(int(x)) for x in remap) + ")"))


def _merge_runs(bind) -> None:
    """`"{user_id}:{탭}"` → `"{탭}"`. 같은 (탭, 달) 은 하나만 남긴다."""
    if "monthly_column_runs" not in sa.inspect(bind).get_table_names():
        return
    rows = bind.execute(sa.text(
        "SELECT id, scope, month FROM monthly_column_runs "
        "WHERE target = 'consulting' ORDER BY id")).all()
    seen = set()
    drop = []
    for run_id, scope, month in rows:
        sheet = (scope or "").split(":", 1)[1] if ":" in (scope or "") else scope
        key = (sheet, month)
        if key in seen:
            drop.append(run_id)
            continue
        seen.add(key)
        if sheet != scope:
            bind.execute(
                sa.text("UPDATE monthly_column_runs SET scope = :s WHERE id = :i"),
                {"s": sheet, "i": run_id})
    if drop:
        bind.execute(sa.text(
            "DELETE FROM monthly_column_runs WHERE id IN ("
            + ",".join(str(int(x)) for x in drop) + ")"))


def upgrade() -> None:
    bind = op.get_bind()
    # **두 번 돌려도 죽지 않아야 한다.** `0001_initial` 이 `create_all()` 로 지금
    # 모델 전체를 만들기 때문에 빈 DB 는 이미 `user_id` 없이 시작한다
    # (`tests/test_migrations.py` 가 지키는 그것이다).
    if not _has_column("consulting_columns", "user_id"):
        return
    _merge_columns(bind)
    _merge_runs(bind)
    # SQLite 는 칸을 바로 못 지운다 — 표를 다시 만들어 옮긴다.
    with op.batch_alter_table("consulting_columns") as batch:
        batch.drop_column("user_id")


def downgrade() -> None:
    # **되돌리기가 비어 있으면 그 판을 지나는 되돌리기 전체가 계획 단계에서
    # 멎는다**(0012 가 그랬다 — `tests/test_migrations.py` 참고).
    #
    # 비워 둔 채로 세운다. 누구 것이었는지는 합치면서 사라졌고, 지어내면 남의
    # 표에 없던 칸이 생긴다(위 설명 참고). 기록은 `notes` 에 그대로 있다.
    if not _has_column("consulting_columns", "user_id"):
        op.add_column("consulting_columns",
                      sa.Column("user_id", sa.Integer(), nullable=True))
