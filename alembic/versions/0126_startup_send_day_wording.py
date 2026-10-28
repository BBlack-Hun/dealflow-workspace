"""#73 스타트업 월간 발송 문구 — `{달} 말 기준` → `{날짜} 기준`(보내는 날)

10/28 사용자 결정("추천대로"): 월간 발송(A5)이 월말이 아니라 **홀수 달 3주차 목요일 ·
짝수 달 4주차 수요일**에 나간다. 그러면 `11월 말 기준` 이 11/19 에 나가 틀린 말이
된다 — 그래서 머리말의 그 구절을 보내는 날(`{날짜}` → `11월 19일`)로 바꾼다.

**바꾸는 것은 그 구절 하나뿐이다** — 기업 리마인드 머리말 셋(`startup_sms` ·
`startup_sms_v2` · `startup_sms_v3`)의 팀 · 개인 문구에서 글자 `{달} 말 기준` 을
`{날짜} 기준` 으로. 나머지 문장은 그대로다(팀이 고쳐 쓴 문장은 건드리지 않는다).

## 수정 로그

이주는 요청 밖에서 돌아 수정 로그에 남지 않는다 — 운영 반영 기록과 PR 이 그 자리다.

## 되돌리기

같은 구절을 거꾸로 돌린다(`{날짜} 기준` → `{달} 말 기준`). 옛 앱은 `{날짜}` 를 모른다.

Revision ID: 0126_startup_send_day_wording
Revises: 0125_series_a_contract
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0126_startup_send_day_wording"
down_revision = "0125_series_a_contract"
branch_labels = None
depends_on = None

KINDS = ("startup_sms", "startup_sms_v2", "startup_sms_v3")
OLD = "{달} 말 기준"
NEW = "{날짜} 기준"


def _swap(old: str, new: str) -> None:
    bind = op.get_bind()
    if "message_templates" not in sa.inspect(bind).get_table_names():
        return
    bind.execute(
        sa.text("UPDATE message_templates SET body = REPLACE(body, :old, :new) "
                "WHERE kind IN :kinds AND body LIKE :like")
        .bindparams(sa.bindparam("kinds", expanding=True)),
        {"old": old, "new": new, "kinds": list(KINDS), "like": f"%{old}%"})


def upgrade() -> None:
    _swap(OLD, NEW)


def downgrade() -> None:
    _swap(NEW, OLD)
