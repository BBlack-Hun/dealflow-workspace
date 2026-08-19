"""자주 조회하는 컬럼에 인덱스 추가

실데이터가 들어오면서 규모가 커졌다(담당자 134, 기업 300, 활동 1,000+, 발송 이력 누적).
아래는 화면·에이전트가 매번 타는 경로라 인덱스가 없으면 전체 스캔이 된다.

특히 send_jobs(user_id, status)는 **에이전트가 2~3초마다 폴링**하는 조건이라
행이 쌓일수록 부담이 커진다.

Revision ID: 0005_indexes
Revises: 0004_auth
"""
import sqlalchemy as sa
from alembic import op

revision = "0005_indexes"
down_revision = "0004_auth"
branch_labels = None
depends_on = None

# (인덱스명, 테이블, 컬럼들)
INDEXES = (
    # 화면: 내 투자사 목록 — 항상 본인 것만 조회
    ("ix_vc_contacts_user", "vc_contacts", ["user_id"]),
    # 임포트: (이름 + 투자사) 로 멱등 upsert
    ("ix_vc_contacts_name_firm", "vc_contacts", ["name", "firm"]),
    # 임포트/발송: 기업명으로 조회
    ("ix_ir_companies_name", "ir_companies", ["name"]),
    # ★ 에이전트 폴링: status='queued' AND user_id=? 를 반복 조회
    ("ix_send_jobs_user_status", "send_jobs", ["user_id", "status"]),
    # 발송 진행 화면: 잡의 건별 목록
    ("ix_send_items_job", "send_items", ["job_id"]),
    # 담당자 상세: 그 사람에게 보낸 이력 / 첫 연락 여부 판단
    ("ix_send_items_contact", "send_items", ["contact_id"]),
    # 로그인: 휴대폰번호로 사용자 조회 (unique 제약이 있어도 명시)
    ("ix_users_phone", "users", ["phone"]),
    # 세션 정리: 사용자별 세션 일괄 해제
    ("ix_sessions_user", "sessions", ["user_id"]),
    # 문구 조합: 사용자/팀 기본 템플릿 조회
    ("ix_message_templates_user_kind", "message_templates", ["user_id", "kind"]),
)


def _existing(table: str) -> set:
    insp = sa.inspect(op.get_bind())
    if table not in insp.get_table_names():
        return set()
    return {i["name"] for i in insp.get_indexes(table)}


def upgrade() -> None:
    for name, table, cols in INDEXES:
        if name not in _existing(table):
            op.create_index(name, table, cols)


def downgrade() -> None:
    for name, table, _cols in INDEXES:
        if name in _existing(table):
            op.drop_index(name, table_name=table)
