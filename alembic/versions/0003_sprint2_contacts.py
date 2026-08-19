"""Sprint 2: contact_activities + vc_contacts.invited_status

시트 A의 월별 3열 세트(1차 딜소개 / IR 자료 요청 / 미팅 요청)는 달이 갈수록
컬럼이 오른쪽으로 늘어난다(SHEET_FINDINGS §2). 이를 컬럼이 아니라 **행**으로
정규화해야 월이 늘어도 스키마가 그대로다 — contact_activities 가 그 그릇이다.

딜소개 셀은 회차마다 형식이 다르다(`핵심 딜 8개사` / `A, B, C` / `1.A  2.B  3.C`).
파싱 결과(기업 목록·개수·요일)와 함께 **원문 조각(raw_text)** 을 남긴다. 파싱이
틀렸을 때 무엇을 잘못 읽었는지 추적할 수 있어야 하기 때문이다.

invited_status(초대완료여부)는 시트 A에만 있고 모델에 없던 필드다
(SHEET_FINDINGS §4 TODO). 카톡방 초대가 끝났는지가 발송 가능 여부의 선행 조건이라
담당자 행에 그대로 둔다.

※ 0001 이 Base.metadata.create_all() 로 현재 모델 전체를 만들기 때문에, 새 DB에서는
  여기 도착했을 때 이미 테이블·컬럼이 존재한다. 새 DB와 기존 DB **양쪽 모두**
  head 까지 올라가야 하므로 모든 변경을 존재 여부로 감싼다.

Revision ID: 0003_sprint2_contacts
Revises: 0002_agent_sender
"""
from alembic import op
import sqlalchemy as sa

revision = "0003_sprint2_contacts"
down_revision = "0002_agent_sender"
branch_labels = None
depends_on = None

# 명단 시트들에만 있는 칸 — 표기가 자유로워(O/X/△/문장) 원문을 그대로 담는다.
CONTACT_COLUMNS = (
    ("invited_status", sa.String()),   # 초대완료여부
    ("interest_level", sa.String()),   # 관심도(월말 기준)
    ("kakao_joined", sa.String()),     # 카톡방 참여여부
    ("office_phone", sa.String()),     # 유선전화
    ("address", sa.String()),
    ("source_sheet", sa.String()),     # 어느 명단 시트에서 왔는지(병합 추적용)
)

ACTIVITY_COLUMNS = (
    ("weekday", sa.String()),          # 시트에 적힌 요일(월~일) — 표시는 사용자가 쓴 값을 따른다
    ("company_names", sa.Text()),      # 원문 기업명 JSON 배열 (DB에 없는 기업이 많아 원문 보존)
    ("company_count", sa.Integer()),   # '핵심 딜 8개사'처럼 개수만 있는 회차 대응
    ("raw_text", sa.Text()),           # 파싱 전 원문 조각 (파싱 오류 추적용)
)

# 기업 쪽 연락 담당자(우리 팀 담당자 owner_user_id 와 다른 사람).
COMPANY_COLUMNS = (
    ("contact_name", sa.String()),
    ("contact_phone", sa.String()),
    ("contact_email", sa.String()),
)


def _inspector():
    return sa.inspect(op.get_bind())


def _has_table(name: str) -> bool:
    return name in _inspector().get_table_names()


def _has_column(table: str, column: str) -> bool:
    return column in {c["name"] for c in _inspector().get_columns(table)}


def _has_index(table: str, name: str) -> bool:
    return name in {i["name"] for i in _inspector().get_indexes(table)}


def upgrade() -> None:
    for name, type_ in CONTACT_COLUMNS:
        if not _has_column("vc_contacts", name):
            op.add_column("vc_contacts", sa.Column(name, type_, nullable=True))

    for name, type_ in COMPANY_COLUMNS:
        if not _has_column("ir_companies", name):
            op.add_column("ir_companies", sa.Column(name, type_, nullable=True))

    if not _has_table("contact_activities"):
        op.create_table(
            "contact_activities",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("contact_id", sa.Integer(), sa.ForeignKey("vc_contacts.id"), nullable=False),
            sa.Column("month", sa.String(), nullable=True),
            sa.Column("kind", sa.String(), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("happened_at", sa.String(), nullable=True),
            sa.Column("source", sa.String(), nullable=False, server_default="import"),
            *[sa.Column(name, type_, nullable=True) for name, type_ in ACTIVITY_COLUMNS],
            sa.Column("created_at", sa.String(), nullable=True),
            sa.Column("updated_at", sa.String(), nullable=True),
        )
    else:
        for name, type_ in ACTIVITY_COLUMNS:
            if not _has_column("contact_activities", name):
                op.add_column("contact_activities", sa.Column(name, type_, nullable=True))

    # 상세 패널 타임라인은 담당자 1명분을 월별로 읽는다.
    if not _has_index("contact_activities", "ix_contact_activities_contact"):
        op.create_index("ix_contact_activities_contact", "contact_activities",
                        ["contact_id", "month"])


def downgrade() -> None:
    if _has_index("contact_activities", "ix_contact_activities_contact"):
        op.drop_index("ix_contact_activities_contact", table_name="contact_activities")
    if _has_table("contact_activities"):
        op.drop_table("contact_activities")
    for name, _type in CONTACT_COLUMNS:
        if _has_column("vc_contacts", name):
            op.drop_column("vc_contacts", name)
    for name, _type in COMPANY_COLUMNS:
        if _has_column("ir_companies", name):
            op.drop_column("ir_companies", name)
