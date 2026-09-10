"""금액 칸 넷을 **정수(백만원) → 글자(억)** 로 옮긴다.

## 왜 옮기나

`revenue_recent` · `funding_total` · `raise_target` · `pre_value` 는
`Integer`(백만원)였다. 그래서 화면 입력이 `<input type="number">` 였고,
**금액을 정확히 모를 때 적을 길이 없었다** — `5-10억 사이` · `~` 같은
표기를 넣고 싶다는 요청이 여기서 막혀 있었다.

숫자 하나로 뭉개면 사람이 적은 뜻이 사라지고, 뭉갠 숫자가 그대로 투자사에게
나간다. 그래서 **사람이 적은 글자를 그대로** 담는다. 숫자로 쓰는 곳(문구·
한줄소개·소개가능 판정·LLM 자료·엑셀·매칭)은 `services/amount.py` **한 곳**을
지나 숫자를 뽑는다.

## 단위가 백만원에서 억으로 바뀐다 (1억 미만은 만원도 쓴다)

표도 `(억)` 이고 수정 창도 `단위: 억` 이다. 사람이 보는 단위와 저장하는 단위가
같아야 `5-10억` 을 적었을 때 곱하거나 나눌 자리가 생기지 않는다 — 곱할 자리가
있으면 글자 값에서 그 자리가 막히고, 막힌 자리를 우회하는 **두 번째 길**이
생긴다.

## 한 줄도 잃지 않는다

옮기는 규칙은 `amount.from_million` 이다. **되읽으면 원래 정수가 그대로 나온다**
— `million(from_million(v)) == v` 가 0~30000 백만원 전 구간에서 성립하고,
`tests/test_amount_range.py` 가 그것을 잰다.

처음에는 화면 계산 그대로(소수 한 자리) 옮겼다. 화면 글자가 한 글자도 안 바뀌는
대신 **저장값이 조금 달라진다.** 운영 자료로 재 보니 값이 든 262칸 중 10칸이
그랬고, 그중 하나가 이랬다:

    raise_target  1(백만원)  →  `"0"`     ← 값이 통째로 사라진다

`1백만원` 이 `0`(= 없음)이 되는 것은 반올림이 아니라 **다른 사실로 바뀌는
것**이다. 화면 글자를 지키자고 값을 잃을 수는 없다. 그래서:

  1. 억으로 적어 잃는 것이 없으면 **억으로**(`560 → "5.6"` · `21000 → "210"` ·
     `50 → "0.5"`). 262칸 중 **252칸**이 이쪽이라 화면이 안 바뀐다.
  2. 잃는데 1억 미만이면 **만원으로**(`47 → "4700만원"` · `1 → "100만원"`).
     이 판이 `천만원` 표기를 받게 되면서 생긴 길이다.
  3. 잃는데 1억 이상이면 **억을 끊지 않고**(`318 → "3.18"` · `1224 → "12.24"`).

## 화면 글자가 바뀌는 줄은 10칸이다

위 2·3번으로 간 칸들이다. 전부 **반올림된 값 → 정확한 값**이고, 그중 한 칸은
`0`(없음)이라는 **거짓말이 사라지는** 것이다. 값이 커지거나 작아지는 칸은 없다.
LLM 구간 경계(10억·50억·100억)를 넘나드는 칸은 **0칸**이다(운영 자료로 쟀다).

## 되돌리기

`downgrade` 는 `amount.million` 으로 되돌린다. **이 판이 옮긴 줄은 한 줄도
잃지 않고 원래 정수로 돌아온다**(`4700만원 → 47` · `3.18 → 318` · `0.5 → 50`).

사람이 새로 적은 값 중 **정수로 옮길 수 없는 것**(`~` · `5~10억` 처럼 구간을
적어 둔 줄)만 `NULL` 이 된다. 구간이라는 사실은 정수 칸에 담을 자리가 없어서다 —
하한 정수로 눌러 담으면 `5~10억` 이 `5억` 이라는 **틀린 단정**으로 남고, 그것이
그대로 투자사에게 나간다. 빈 칸은 사람이 다시 채우지만 그럴듯한 숫자는 아무도
다시 안 본다.

## 빈 DB

`0001_initial` 이 `create_all()` 로 지금 모델을 만들어, 새 DB 는 이미 글자
칸으로 시작한다. 그때는 아무 일도 하지 않는다(칸 종류를 보고 판단한다).
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0074_company_amounts_as_text"
down_revision = "0073_consulting_row_grant"
branch_labels = None
depends_on = None

TABLE = "ir_companies"
FIELDS = ("revenue_recent", "funding_total", "raise_target", "pre_value")


def _kinds() -> dict:
    return {c["name"]: c["type"] for c in sa.inspect(op.get_bind()).get_columns(TABLE)}


def _to_text(value):
    """백만원 정수 → 억 글자. **앱과 같은 함수를 쓴다**(두 벌로 적으면 갈린다)."""
    from app.services import amount

    if value is None or value == "":
        return None
    try:
        return amount.from_million(int(value))
    except (TypeError, ValueError):
        # 이미 글자가 들어 있는 줄(두 번 돌린 경우)은 그대로 둔다.
        return str(value)


def _to_million(value):
    """억 글자 → 백만원 정수. **정수로 담을 수 없는 값은 버린다.**

    구간(`5~10억`)을 하한 정수로 눌러 담으면 `5억` 이라는 **틀린 단정**이 남고,
    그것이 그대로 딜소개 문구에 실려 투자사에게 나간다. 빈 칸이 되는 편이 낫다 —
    빈 칸은 사람이 다시 채우지만, 그럴듯한 숫자는 아무도 다시 안 본다.
    """
    from app.services import amount

    if amount.state(value) != amount.NUMBER:
        return None
    return amount.million(value)


def _rewrite(kind, convert) -> None:
    """칸 종류를 바꾸고 값을 옮긴다. SQLite 는 `batch_alter_table` 이 필요하다."""
    bind = op.get_bind()
    rows = bind.execute(sa.text(
        f"SELECT id, {', '.join(FIELDS)} FROM {TABLE}")).fetchall()

    with op.batch_alter_table(TABLE) as batch:
        for name in FIELDS:
            batch.alter_column(name, type_=kind, existing_nullable=True)

    for row in rows:
        values = {name: convert(row[i + 1]) for i, name in enumerate(FIELDS)}
        bind.execute(
            sa.text(f"UPDATE {TABLE} SET "
                    + ", ".join(f"{name} = :{name}" for name in FIELDS)
                    + " WHERE id = :id"),
            {**values, "id": row[0]})


def upgrade() -> None:
    kinds = _kinds()
    # 빈 DB 는 0001 이 이미 글자 칸으로 만들어 준다 — 그때는 손댈 것이 없다.
    if not any(isinstance(kinds.get(name), sa.Integer) for name in FIELDS):
        return
    _rewrite(sa.String(), _to_text)


def downgrade() -> None:
    kinds = _kinds()
    if not any(isinstance(kinds.get(name), sa.String) for name in FIELDS):
        return
    _rewrite(sa.Integer(), _to_million)
