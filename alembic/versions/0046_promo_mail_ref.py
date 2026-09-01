"""`홍보메일 발송 제목 리스트` 를 스타트업 화면으로 옮긴다

제목이 전부 스타트업을 향한다(`7년 미만 스타트업 성장 프로그램`,
`[5억 투자 매칭 프로그램]`). 0043 에서 옮길지 판단이 갈려 남겨 두었던
자료인데 — 40개사 리마인드는 문자·전화 흐름이고 이것은 신규 유치용
메일이라 성격이 한 단계 다르다 — 사용자가 스타트업 쪽으로 정했다.

제목으로 찾는다. 이 표에 사람이 붙인 이름 말고 다른 열쇠가 없다. 이름이
바뀌어 있으면 아무것도 안 옮기고 조용히 지나간다 — 엉뚱한 자료를 옮기는
것보다 안 옮기는 편이 낫다.
"""
from alembic import op
import sqlalchemy as sa

revision = "0046_promo_mail_ref"
down_revision = "0045_consulting_sheets"
branch_labels = None
depends_on = None

TITLE = "홍보메일 발송 제목 리스트"


def _move(to_page: str, from_page: str) -> None:
    op.execute(sa.text(
        "UPDATE ref_sheets SET page = :to WHERE title = :title AND page = :frm"
    ).bindparams(to=to_page, title=TITLE, frm=from_page))


def upgrade() -> None:
    _move("startup", "contacts")


def downgrade() -> None:
    _move("contacts", "startup")
