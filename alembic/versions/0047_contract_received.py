"""IR 기업 현황에 `계약서 수신됨` 칸

## 왜 `계약여부` 로는 모자란가

`계약여부` 는 **계약을 맺기로 했는가**를 적는 칸이다(`유료계약완료` ·
`무료계약완료` · `계약검토중` · `미계약` · `딜소개 불가`). 계약서 종이가
실제로 우리 손에 들어왔는지는 그것과 다른 사실이라, `유료계약완료` 인데
서류는 아직인 기업을 지금은 표에 적을 자리가 없다.

## 왜 기본값을 안 주는가 — **321줄이 전부 `미정`(NULL) 으로 남는다**

값은 `O`/`X` 둘이다. 그런데 아직 아무도 확인하지 않은 기업에 `X` 를 찍어
두면 그것은 "확인했는데 안 왔다" 는 **거짓 단언**이 된다. 받은 곳이 몇
곳인지 세는 순간 그 거짓말이 그대로 숫자가 된다.

그래서 `nullable=True` 에 `server_default` 를 두지 않는다. 이미 들어 있는
줄은 전부 NULL 로 남아 화면에서 빈 칸으로 보이고, 필터에서는 `(비어 있음)`
으로 골라진다(`static/js/filters.js` 의 `EMPTY`). 이 저장소의 다른 `O`/`X`
칸들이 이미 그 모양이다(`vc_contacts.kakao_joined` · 명단의
`IR 자료 회신 여부` · `IR dack 유무` — 셋 다 nullable 이고 빈칸을 남긴다).

`ir_companies.contract_status` 만 NOT NULL 인데, 거기서는 `none`(미계약)이
**실제 상태**라 빈칸일 이유가 없어서다. 여기는 반대다.

## downgrade

칸만 지운다. SQLite 는 `ALTER TABLE … DROP COLUMN` 을 예전 판에서 못 하므로
다른 마이그레이션과 같이 `batch_alter_table`(표를 다시 만들어 옮긴다)로 간다.
내리면 적어 둔 `O`/`X` 는 함께 사라진다 — 되돌릴 값이 이 칸 말고는 없다.

Revision ID: 0047_contract_received
Revises: 0046_promo_mail_ref
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0047_contract_received"
down_revision = "0046_promo_mail_ref"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    return column in {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    # 이미 있으면 건너뛴다 — 빈 DB 는 0001 이 만들어 준 채로 온다(0018 참고).
    if not _has_column("ir_companies", "contract_received"):
        with op.batch_alter_table("ir_companies") as b:
            # 기본값 없음 = 이미 있는 줄은 전부 NULL(아직 안 정함).
            b.add_column(sa.Column("contract_received", sa.String(), nullable=True))


def downgrade() -> None:
    if _has_column("ir_companies", "contract_received"):
        with op.batch_alter_table("ir_companies") as b:
            b.drop_column("contract_received")
