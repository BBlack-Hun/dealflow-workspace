"""스타트업DB 탭에 **재료**를 돌려준다 — `기업 한줄 소개` = `business_desc`

## 무엇이 문제였나

두 탭이 **같은 칸**을 보고 있었다(0051 이 그렇게 합쳤다).

    IR 기업 현황  머리글 `기업 한줄 소개`  → one_liner
    스타트업DB    머리글 `기업 한줄 소개`  → one_liner   ← 같은 칸

그런데 `one_liner` 에는 자동 조합의 **결과**가 들어 있다
(`app/services/one_liner.py`):

    사업 설명 | 매출 23년 2억, 24년 4억 | 누적투자금액 11억 | Pre Value 200억

스타트업DB 는 그 조각들을 **넣는 자리**다. 넣는 자리에 조합 결과가 서 있으면
"이 줄을 바꾸려면 무엇을 고쳐야 하는가" 를 화면에서 알 수 없고, 매출·누적투자
금액은 바로 옆 칸에 또 적혀 있어 같은 숫자가 한 줄에 두 번 보인다.

그래서 이 판부터 **두 탭이 다른 칸을 본다**:

    IR 기업 현황  머리글 `딜 소개 문구 회사개요`  → one_liner      (조합 결과)
    스타트업DB    머리글 `기업 한줄 소개`         → business_desc  (재료)

**칸을 새로 파지 않는다.** `business_desc` 는 0020 부터 있던 칸이고 조합의
첫 토막이 곧 그 값이다(0051 이 화면에서만 뗐을 뿐 지우지 않았다). 새 칸을
파면 같은 뜻이 세 칸에 흩어진다 — 0051 이 어렵게 없앤 상태로 되돌아간다.

## 이 판이 자료에 하는 일 — **빈 칸 채우기 하나**

화면만 바꾸면 `business_desc` 가 빈 줄에서 스타트업DB 탭의 소개가 **통째로
빈 칸이 된다.** 운영 사본 344곳 중 58곳이 그렇다. 그 58곳의 글자는 0051 이후
**스타트업DB 탭에서 사람이 그 자리에 직접 쳐 넣은 것**이다(그 탭이 그동안
`one_liner` 을 보여 줬으므로). 화면을 바꾼다는 이유로 사람이 그 자리에 적은
글을 사라지게 할 수는 없다.

    business_desc 가 비어 있고 one_liner 에 값이 있으면 → 그 값을 옮겨 적는다

**덮어쓰지 않는다.** `one_liner` 은 한 글자도 안 건드리고, `business_desc` 에
이미 값이 있는 줄은 지나간다. 잃는 자료가 없다.

### 조합 결과를 재료 칸에 집어넣지는 않는가

안 된다 — 그러면 `매출 13억 | 누적투자금액 11억` 이 '사업 설명' 이 되어
다음 조합부터 한 줄이 통째로 어긋난다. 그래서 두 가지로 막는다.

  1. **재어 보았다.** 운영 사본에서 `one_liner` 이 자동 조합값과 글자까지
     같은 줄(AUTO)은 67곳인데 **그 67곳은 전부 `business_desc` 가 차 있다.**
     당연하다 — 재료가 비면 조합이 매출부터 시작하는데, 그런 줄은 없었다.
     즉 재료가 빈 줄의 `one_liner` 은 사람이 쓴 글이다.
  2. 그래도 다른 사본에서 그런 줄이 나올 수 있으니, **조합 토막으로 시작하는
     줄은 건너뛴다**(`_HEADLESS`). 운영 사본에서는 0곳이 걸렸다.

## 두 번 돌려도 안전한가

두 번째에는 `business_desc` 가 이미 차 있어 후보가 하나도 없다. 아무 일도
일어나지 않는다.

## 되돌리면

**이 판이 채운 줄만** 다시 비운다. 그 줄을 가려내는 근거는 0051 이 남긴
`desc_backup` 이다 — 거기 적힌 `business_desc` 가 비어 있으면 이 칸은 원래
비어 있던 자리다. 지금 값이 `one_liner` 과 글자까지 같을 때만 비운다: 다르면
그 사이에 사람이 고쳐 쓴 것이라 되돌리기가 그 손글씨를 지우면 안 된다.

**근거가 없는 줄은 그대로 둔다.** 0051 이후에 생긴 기업은 `desc_backup` 이
아예 없어서 "원래 비어 있었다" 를 증명할 길이 없다. 이미 차 있던 재료를
비우는 쪽으로 틀리면 되돌릴 수가 없으니, 못 가리면 안 건드린다.
(되돌린 줄의 글자도 사라지지 않는다 — 같은 글자가 `one_liner` 에 그대로 있다.)

Revision ID: 0058_startup_db_one_liner
Revises: 0057_send_item_files
"""
from __future__ import annotations

import json
import re

import sqlalchemy as sa
from alembic import op

revision = "0058_startup_db_one_liner"
down_revision = "0057_send_item_files"
branch_labels = None
depends_on = None

TABLE = "ir_companies"
BACKUP = "desc_backup"

# 조합 토막으로 **시작하는** 줄. 재료가 빈 채로 조합된 줄이 이 모양이다
# (`compose_one_liner` 이 붙이는 차례 그대로 — 매출 · 누적투자금액 ·
# `N억 투자유치중` · Pre Value). 이런 줄에는 옮겨 적을 '설명' 이 없다.
_HEADLESS = re.compile(
    r"^(매출\b|누적투자금액\b|Pre ?Value\b|[0-9][0-9.,]*억 투자유치중)", re.I)


def _blank(value) -> bool:
    """빈 칸인가 — NULL 과 공백만 든 글자를 같이 본다.

    화면이 `c.business_desc or ""` 로 읽어 둘 다 빈 칸으로 보이므로, 세는
    쪽도 같이 봐야 로그의 숫자와 화면이 어긋나지 않는다.
    """
    return not (value or "").strip()


def upgrade() -> None:
    conn = op.get_bind()
    rows = conn.execute(sa.text(
        f"SELECT id, one_liner, business_desc FROM {TABLE} ORDER BY id")).fetchall()

    # 바꾸기 전에 먼저 센다 — 끝난 뒤에는 "원래 몇 건이었나" 를 되짚을 수 없다.
    blank_desc = [r for r in rows if _blank(r[2])]
    print(f"[0058] 전체 {len(rows)}곳 — 재료(business_desc)가 빈 곳 {len(blank_desc)}")

    moved = skipped = 0
    for cid, one_liner, business_desc in rows:
        if not _blank(business_desc) or _blank(one_liner):
            continue
        if _HEADLESS.match(one_liner.strip()):
            # 재료 없이 조합된 줄이다. 옮겨 적으면 매출이 '설명' 이 된다.
            skipped += 1
            continue
        conn.execute(
            sa.text(f"UPDATE {TABLE} SET business_desc = :v WHERE id = :i"),
            {"v": one_liner, "i": cid})
        moved += 1

    print(f"[0058] 딜 소개 문구 → 기업 한줄 소개 {moved}곳을 옮겼습니다 (빈 곳만)"
          + (f", 조합 토막으로 시작하는 {skipped}곳은 건너뜁니다" if skipped else ""))


def downgrade() -> None:
    conn = op.get_bind()
    have_backup = BACKUP in {c["name"] for c
                             in sa.inspect(conn).get_columns(TABLE)}
    if not have_backup:
        # 0051 아래로 이미 내려간 DB. 가려낼 근거가 없으니 건드리지 않는다.
        print("[0058] `desc_backup` 이 없어 되돌릴 근거가 없습니다 — 그대로 둡니다")
        return

    rows = conn.execute(sa.text(
        f"SELECT id, one_liner, business_desc, {BACKUP} FROM {TABLE} "
        f"WHERE {BACKUP} IS NOT NULL ORDER BY id")).fetchall()

    back = kept = 0
    for cid, one_liner, business_desc, blob in rows:
        try:
            saved = json.loads(blob)
        except (ValueError, TypeError):
            # 깨진 백업 하나 때문에 되돌리기 전체가 멎으면 안 된다.
            continue
        if not isinstance(saved, dict):
            continue
        # 0051 이 찍어 둔 그때의 재료 칸. 값이 있었다면 이 판이 채운 줄이 아니다.
        if not _blank(saved.get("business_desc")):
            continue
        if _blank(business_desc):
            continue
        # 되돌린 뒤에 사람이 손댄 줄은 건드리지 않는다 — 지금 값이 이 판이
        # 써 넣은 값(= `one_liner`)과 글자까지 같을 때만 비운다.
        if (business_desc or "") != (one_liner or ""):
            kept += 1
            continue
        conn.execute(
            sa.text(f"UPDATE {TABLE} SET business_desc = NULL WHERE id = :i"),
            {"i": cid})
        back += 1

    print(f"[0058] 기업 한줄 소개 {back}곳을 되돌렸습니다"
          + (f" (그 뒤 손댄 {kept}곳은 그대로 둡니다)" if kept else ""))
