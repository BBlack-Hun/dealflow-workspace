"""`사업분야` 와 `기업 한줄 소개` 를 한 칸으로 합친다 — 정본은 `one_liner`

## 무엇이 문제였나

두 탭이 **같은 것을 다른 칸에 적고 있었다.**

    IR 기업 현황  머리글 `기업 한줄 소개`  → one_liner
    스타트업DB    머리글 `사업분야`        → business_desc

이름이 다르니 서로 다른 칸처럼 보이지만 둘 다 **사업 설명**이다(카테고리는
`sector_major/minor` 가 따로 들고 있다 — 0020 참고). 그래서 스타트업DB 에서
설명을 고쳤는데 IR 화면의 소개는 그대로인 일이 생겼다.

`business_desc` → `one_liner` 자동 조합은 이미 있다(`app/services/one_liner.py`).
다만 그것은 **사람이 쓴 소개를 절대 덮지 않는다.** 운영 321곳 중 235곳에 두 칸이
다 들어 있고 그중 97곳은 글자가 서로 달라서, 그 97곳에서는 자동 조합이 일부러
건너뛴다 — 고친 사람 눈에는 "안 바뀐다" 로 보인다. 칸을 하나로 합쳐야 끝난다.

## 무엇을 하나

1. **백업 칸(`desc_backup`)을 만든다.** 합치기 전 두 값을 있는 그대로,
   `{"one_liner": …, "business_desc": …}` JSON 한 덩이로 담는다. 키 이름이 곧
   어느 칸에서 온 값인지다. 값이 하나라도 있는 줄은 전부 담는다 — 일부만 담으면
   "백업이 없다" 가 "원래 비어 있었다" 인지 "안 담았다" 인지 알 수 없다.
   비어 있던 칸은 `null` 로 적는다: `""` 로 뭉개면 되돌릴 때 NULL 이던 칸에
   빈 글자가 들어간다.

2. **`business_desc` 만 있고 `one_liner` 이 빈 줄에 값을 옮긴다**(운영 23곳).
   그 23곳은 IR 화면에도 안 보이고 딜 소개 문구에도 안 실린다
   (`app/services/message_composer.py` 가 `one_liner` 을 읽는다).
   **덮어쓰지 않는다 — 빈 곳만 채운다.**

3. `business_desc` 칸은 **지우지 않는다.** 화면에서만 뗀다(탭을 지우는 것은
   다음 일이다). 지금 지우면 백업과 원본이 같은 판에서 함께 사라진다.

## 두 번 돌려도 안전한가

백업은 **아직 백업이 없는 줄에만** 적는다. 두 번째로 돌아가면 `one_liner` 은
이미 채워진 뒤라, 다시 찍으면 "원래 비어 있었다" 는 사실이 덮여 없어진다 —
되돌릴 근거가 그 순간 사라진다. 칸은 이미 있으면 건너뛴다(0020 과 같은 방식).

## 되돌리면

옮긴 23곳의 `one_liner` 을 백업에 적힌 값(= 비어 있던 상태)으로 되돌리고 칸을
지운다. **되돌린 뒤에 사람이 손댄 줄은 건드리지 않는다** — 지금 값이 이 판이
써 넣은 값(백업의 `business_desc`)과 글자까지 같을 때만 되돌린다. 다르면 그
사이에 사람이 고쳐 쓴 것이라, 되돌리기가 그 손글씨를 지우면 안 된다.

`business_desc` 는 이 판이 한 글자도 안 바꿨으므로 되돌릴 것이 없다.

Revision ID: 0051_one_liner_single_source
Revises: 0050_deal_queue
"""
from __future__ import annotations

import json

import sqlalchemy as sa
from alembic import op

revision = "0051_one_liner_single_source"
down_revision = "0050_deal_queue"
branch_labels = None
depends_on = None

TABLE = "ir_companies"
BACKUP = "desc_backup"
# 백업 JSON 의 키 — **모델 칸 이름 그대로**다. 화면 이름으로 적으면 머리글을
# 고치는 날 백업을 못 읽는다.
KEEP = ("one_liner", "business_desc")


def _has_column(table: str, column: str) -> bool:
    return column in {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def _blank(value) -> bool:
    """빈 칸인가 — NULL 과 공백만 든 글자를 같이 본다.

    화면이 `c.one_liner or ""` 로 읽어서 둘 다 빈 칸으로 보이므로, 세는 쪽도
    같이 봐야 미리보기 숫자와 화면이 어긋나지 않는다.
    """
    return not (value or "").strip()


def _preview(conn) -> list:
    """**바꾸기 전에** 두 칸의 상태를 세어 로그로 남긴다.

    데이터를 옮기는 판이다. 무엇이 몇 건 바뀌는지 먼저 적어 두지 않으면,
    끝난 뒤에 "원래 몇 건이었나" 를 되짚을 방법이 없다.
    """
    rows = conn.execute(sa.text(
        f"SELECT id, one_liner, business_desc FROM {TABLE} ORDER BY id")).fetchall()

    both = [r for r in rows if not _blank(r[1]) and not _blank(r[2])]
    same = [r for r in both if (r[1] or "").strip() == (r[2] or "").strip()]
    db_only = [r for r in rows if _blank(r[1]) and not _blank(r[2])]
    ir_only = [r for r in rows if not _blank(r[1]) and _blank(r[2])]
    empty = [r for r in rows if _blank(r[1]) and _blank(r[2])]

    print(f"[0051] 합치기 전 — 전체 {len(rows)}곳")
    print(f"[0051]   둘 다 있음 {len(both)}곳 "
          f"(글자까지 같음 {len(same)} · 다름 {len(both) - len(same)})")
    print(f"[0051]   사업분야만 {len(db_only)}곳   ← 한줄 소개로 옮긴다")
    print(f"[0051]   한줄 소개만 {len(ir_only)}곳")
    print(f"[0051]   둘 다 빔 {len(empty)}곳")
    return rows


def upgrade() -> None:
    conn = op.get_bind()

    # 칸이 이미 있으면 건너뛴다 — 빈 DB 는 0001 의 `create_all()` 이 지금 모델
    # 전체를 만들어 준 채로 온다(0020 과 같은 방식).
    if not _has_column(TABLE, BACKUP):
        op.add_column(TABLE, sa.Column(BACKUP, sa.Text(), nullable=True))

    rows = _preview(conn)

    # ── 백업 ────────────────────────────────────────────────────────────
    # **아직 백업이 없는 줄에만** 적는다. 두 번째로 돌면 `one_liner` 이 이미
    # 채워진 뒤라, 다시 찍는 순간 "원래 비어 있었다" 는 사실이 덮인다.
    have = {r[0] for r in conn.execute(sa.text(
        f"SELECT id FROM {TABLE} WHERE {BACKUP} IS NOT NULL")).fetchall()}

    backed = 0
    kept_desc = 0
    for cid, one_liner, business_desc in rows:
        if cid in have:
            continue
        if _blank(one_liner) and _blank(business_desc):
            # 지킬 것이 없다. `{}` 를 적어 두면 "백업이 있다" 는 줄과 섞인다.
            continue
        # 값은 **손대지 않고 그대로** 담는다. NULL 은 `null` 로 남겨야
        # 되돌릴 때 NULL 이던 칸에 빈 글자가 들어가지 않는다.
        blob = json.dumps(dict(zip(KEEP, (one_liner, business_desc))),
                          ensure_ascii=False)
        conn.execute(sa.text(f"UPDATE {TABLE} SET {BACKUP} = :b WHERE id = :i"),
                     {"b": blob, "i": cid})
        backed += 1
        if not _blank(business_desc):
            kept_desc += 1

    # ── 옮기기 — 빈 곳만 채운다 ─────────────────────────────────────────
    moved = 0
    for cid, one_liner, business_desc in rows:
        if not _blank(one_liner) or _blank(business_desc):
            continue
        conn.execute(sa.text(f"UPDATE {TABLE} SET one_liner = :v WHERE id = :i"),
                     {"v": business_desc, "i": cid})
        moved += 1

    print(f"[0051] 백업 {backed}곳 (그중 사업분야가 든 곳 {kept_desc})")
    print(f"[0051] 사업분야 → 기업 한줄 소개 {moved}곳을 옮겼습니다 (빈 곳만)")


def downgrade() -> None:
    conn = op.get_bind()
    if not _has_column(TABLE, BACKUP):
        return

    rows = conn.execute(sa.text(
        f"SELECT id, one_liner, {BACKUP} FROM {TABLE} "
        f"WHERE {BACKUP} IS NOT NULL ORDER BY id")).fetchall()

    back = 0
    skipped = 0
    for cid, one_liner, blob in rows:
        try:
            saved = json.loads(blob)
        except (ValueError, TypeError):
            # 깨진 백업 때문에 되돌리기 전체가 멎으면 안 된다 — 그 줄만 둔다.
            skipped += 1
            continue
        if not isinstance(saved, dict):
            skipped += 1
            continue
        was, desc = saved.get("one_liner"), saved.get("business_desc")
        # 이 판이 실제로 바꾼 줄인가 — 원래 비어 있었고 사업분야에 값이 있던 줄.
        if not (_blank(was) and not _blank(desc)):
            continue
        # 되돌린 뒤에 사람이 손댄 줄은 건드리지 않는다. 지금 값이 이 판이 써 넣은
        # 값과 글자까지 같을 때만 되돌린다.
        if (one_liner or "") != desc:
            skipped += 1
            continue
        conn.execute(sa.text(f"UPDATE {TABLE} SET one_liner = :v WHERE id = :i"),
                     {"v": was, "i": cid})
        back += 1

    print(f"[0051] 한줄 소개 {back}곳을 되돌렸습니다"
          + (f" (그 뒤 손댄 {skipped}곳은 그대로 둡니다)" if skipped else ""))
    op.drop_column(TABLE, BACKUP)
