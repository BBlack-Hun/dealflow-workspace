"""자료 칸의 이름을 **내용에 맞춘다** — `ir_drive_url` → `ir_file_name`

## 왜 이름을 바꾸나

이 칸은 원래 **구글 드라이브 링크**를 담았다. 그 방식은 폐기했고(0053), 자료는
이제 발송기가 **파일로 붙여 보낸다**(0055). 그래서 사람들은 이미 이 칸에
**파일명을 적어 쓰고 있다** — 칸 이름만 `…_url` 로 남아 있었다.

이름이 내용과 어긋난 칸은 다음 사람이 어긋난 값을 넣게 만든다. 여기서는 그
값이 그대로 **투자사 카톡방에 나갈 파일 경로**가 되므로, 어긋난 채로 두면
안 된다.

`app/models.py` 와 화면·발송 경로가 **같은 커밋에서 함께** 옮겨간다
(`tests/test_migrations.py::test_the_fresh_schema_matches_the_models` 가
이주 결과와 모델을 칸 단위로 대조한다).

## 남아 있던 옛 링크는 어떻게 하나

**실측**(운영 DB, 이 판을 쓰기 직전):

    ir_companies            344곳
    값이 있는 칸              3곳
      · 전부 `https://drive.google.com/…`
      · 파일명 꼴              0곳

이 3개는 이제 **틀린 값**이다 — 파일명 자리에 주소가 있으면 발송기가 거부한다
(`agent/sender/base.py: check_ir_file_name`). 그래서 칸에서 뺀다.

### 그런데 지우지는 않는다

그 3곳의 자료는 **그 드라이브 링크에만 있다.** 칸에서 지우면 파일을 어디서
내려받아 자료 폴더에 넣어야 하는지 아무도 모른다 — 자료를 잃는 것과 같다.
그래서 값을 **비고(`note`)로 옮긴다.** 사람이 그 링크를 열어 파일을 내려받고,
자료 폴더에 넣은 다음, 파일명을 이 칸에 적으면 끝난다.

옮긴 줄은 한눈에 알아보게 표식으로 시작한다(아래 `MARK`). 되돌릴 때 이 판이
적은 줄만 골라내는 근거이기도 하다.

## 되돌리기

칸 이름을 되돌리고, 비고로 옮겨 둔 링크를 **칸으로 되돌려 놓는다** — 올린
자리를 그대로 되짚는다(0054 와 같은 규칙).

**사람이 그 사이에 파일명을 적어 둔 줄은 건드리지 않는다**(0051 과 같은 규칙).
그 줄은 링크를 되돌리면 사람이 적은 파일명이 지워진다. 그런 줄은 값도 비고의
줄도 그대로 두고 넘어간다 — 둘 다 남아 있으면 사람이 보고 고를 수 있지만,
덮어 쓴 값은 되찾을 수 없다.

Revision ID: 0056_ir_file_name
Revises: 0055_agent_ir_root
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0056_ir_file_name"
down_revision = "0055_agent_ir_root"
branch_labels = None
depends_on = None

TABLE = "ir_companies"
OLD = "ir_drive_url"
NEW = "ir_file_name"

#: 비고로 옮긴 링크 줄의 머리. **이 판이 적은 줄인지 가리는 유일한 근거**라
#: 글자를 바꾸면 되돌리기가 제 줄을 못 찾는다.
MARK = "옛 IR 자료 링크(구글 드라이브): "

#: `scheme://` 이 들어 있으면 주소다. 발송기의 판단(`_URL_LIKE`)과 같은 자리를
#: 본다 — 거기서 거부당할 값이 곧 여기서 옮길 값이다.
URL_LIKE = "%://%"


def _columns() -> set:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(TABLE)}


def _rename(before: str, after: str) -> None:
    """빈 DB 길에서는 `0001` 이 **이미 새 이름으로** 표를 만들어 둔다.

    그 자리에서 또 바꾸면 `no such column` 으로 부팅이 죽는다
    (`tests/test_migrations.py` 가 지키는 규칙이다).
    """
    cols = _columns()
    if before not in cols or after in cols:
        return
    with op.batch_alter_table(TABLE) as batch:
        batch.alter_column(before, new_column_name=after)


def upgrade() -> None:
    _rename(OLD, NEW)

    # 주소가 남아 있는 줄을 **비고로 옮긴다.** 칸은 비우고, 값은 남긴다.
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(f"SELECT id, {NEW} AS value, note FROM {TABLE} "
                f"WHERE {NEW} LIKE :pat"),
        {"pat": URL_LIKE},
    ).fetchall()
    for row in rows:
        line = MARK + (row.value or "").strip()
        note = (row.note or "").strip()
        bind.execute(
            sa.text(f"UPDATE {TABLE} SET {NEW} = NULL, note = :note WHERE id = :id"),
            {"note": f"{note}\n{line}" if note else line, "id": row.id},
        )


def downgrade() -> None:
    # 칸 이름을 되돌리기 **전에** 값을 되돌린다 — 한 이름만 보고 일하면 된다.
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(f"SELECT id, {NEW} AS value, note FROM {TABLE} WHERE note LIKE :pat"),
        {"pat": f"%{MARK}%"},
    ).fetchall()
    for row in rows:
        if (row.value or "").strip():
            # 사람이 그 사이에 파일명을 적었다 — 덮지 않는다(위 `## 되돌리기`).
            continue
        lines = (row.note or "").split("\n")
        moved = [ln[len(MARK):].strip() for ln in lines if ln.startswith(MARK)]
        if not moved:
            continue
        kept = "\n".join(ln for ln in lines if not ln.startswith(MARK)).strip()
        bind.execute(
            sa.text(f"UPDATE {TABLE} SET {NEW} = :value, note = :note WHERE id = :id"),
            # 표식이 여럿이면 **마지막에 옮긴 것**이 그 칸의 마지막 값이었다.
            {"value": moved[-1], "note": kept or None, "id": row.id},
        )

    _rename(NEW, OLD)
