"""SQLAlchemy models — Sprint 1 subset (ROADMAP task 1.2).

Tables: users, vc_contacts, ir_companies, message_templates,
deal_batches (+ deal_batch_companies), send_jobs, send_items, agent_devices.

Fields follow DATA_MODEL §2. Forward-compatible nullable columns (e.g.
send_items.sequence_id / stage) are included without FKs to tables that
arrive in later sprints (send_sequences → Sprint 3), so schemas don't drift.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class TimestampMixin:
    created_at: Mapped[str] = mapped_column(String, default=_now_iso)
    updated_at: Mapped[str] = mapped_column(String, default=_now_iso, onupdate=_now_iso)


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    phone: Mapped[Optional[str]] = mapped_column(String, unique=True, nullable=True)
    name: Mapped[str] = mapped_column(String)
    role: Mapped[str] = mapped_column(String, default="user")  # user | admin
    weekly_goal_sends: Mapped[int] = mapped_column(Integer, default=30)
    is_active: Mapped[int] = mapped_column(Integer, default=1)
    # 로그인 ID 는 phone(숫자만). 비밀번호는 해시만 저장한다.
    password_hash: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # 관리자가 계정을 만들거나 초기화하면 첫 로그인 때 변경을 요구한다.
    must_change_password: Mapped[int] = mapped_column(Integer, default=0)
    last_login_at: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # 일부 화면은 팀 전체가 아니라 정해진 사람만 본다(투자현황 등).
    # 사람 이름을 코드에 박으면 사람이 바뀔 때마다 배포해야 하므로 계정 속성으로 둔다.
    # 관리자는 이 값과 무관하게 볼 수 있다.
    can_view_consulting: Mapped[int] = mapped_column(Integer, default=0)


class Session(TimestampMixin, Base):
    """로그인 세션. 쿠키에는 토큰만 담고 서버가 소유자를 판단한다."""

    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    token: Mapped[str] = mapped_column(String, unique=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    expires_at: Mapped[str] = mapped_column(String)
    user_agent: Mapped[Optional[str]] = mapped_column(String, nullable=True)


class MessageTemplate(TimestampMixin, Base):
    __tablename__ = "message_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # NULL user_id = team default template (seeded). User-owned overrides take priority.
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    # opening_first | opening_re | closing_day1 | closing_remind | closing_meeting | ir_delivery
    kind: Mapped[str] = mapped_column(String)
    # 같은 종류(kind)의 템플릿을 여러 개 두고 골라 쓰기 위한 이름.
    # 예: opening_first 에 '기본 인사', '연말 인사' 를 각각 만들어 회차마다 선택.
    name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    body: Mapped[str] = mapped_column(Text)
    is_active: Mapped[int] = mapped_column(Integer, default=1)


class VcContact(TimestampMixin, Base):
    __tablename__ = "vc_contacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    group_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    name: Mapped[str] = mapped_column(String)
    title: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    firm: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    round_size: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # 시트 A '초대완료여부' (카톡방 초대 상태) — SHEET_FINDINGS §2/§4.
    # 시트마다 표기가 제각각(완료 / O / 초대완료)이라 정규화하지 않고 원문을 보존한다.
    invited_status: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # 명단 시트들에만 있는 칸들. 표기가 자유로워(O/X/△/문장) 원문을 그대로 둔다.
    interest_level: Mapped[Optional[str]] = mapped_column(String, nullable=True)   # 관심도(월말 기준)
    kakao_joined: Mapped[Optional[str]] = mapped_column(String, nullable=True)     # 카톡방 참여여부
    office_phone: Mapped[Optional[str]] = mapped_column(String, nullable=True)     # 유선전화
    address: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # 어느 명단 시트에서 온 정보인지(여러 시트에 나뉜 같은 사람을 병합하므로 추적이 필요).
    source_sheet: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    channel_kakao: Mapped[int] = mapped_column(Integer, default=0)
    channel_email: Mapped[int] = mapped_column(Integer, default=0)
    email: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # Kakao chat-room name — agent search key, must match exactly.
    kakao_room_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # unverified | verified | ambiguous | not_found
    room_verified: Mapped[str] = mapped_column(String, default="unverified")
    stages: Mapped[Optional[str]] = mapped_column(String, nullable=True)   # CSV: Seed,SeriesA
    sectors: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # CSV: AI,헬스케어
    status: Mapped[str] = mapped_column(String, default="active")  # active | no_response | paused
    memo: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class ContactActivity(TimestampMixin, Base):
    """담당자 활동 이력 (DATA_MODEL §2.6).

    시트 A는 월이 갈수록 **3열 세트(딜소개/IR요청/미팅)가 오른쪽으로 무한히 늘어난다**
    (SHEET_FINDINGS §2). 서비스에서는 그 셀들을 이 테이블의 **행**으로 정규화한다.
    시트 대비 개선의 핵심 지점이라 임포트의 1급 산출물이다.
    """

    __tablename__ = "contact_activities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    contact_id: Mapped[int] = mapped_column(ForeignKey("vc_contacts.id"))
    month: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # 2026-08
    # deal_intro | ir_request | meeting | memo
    kind: Mapped[str] = mapped_column(String)
    content: Mapped[str] = mapped_column(Text)
    happened_at: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # 2026-08-13
    # 시트에 적힌 요일(월~일). 날짜에서 계산할 수도 있지만, 연도 추정이 틀리면
    # 계산값이 어긋나므로 **사용자가 쓴 값**을 그대로 보존해 표시에 쓴다.
    weekday: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # 회차에 포함된 기업명 원문 JSON 배열. ir_companies 에 없는 기업이 훨씬 많아
    # 매칭 여부와 무관하게 원문을 남긴다.
    company_names: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # '핵심 딜 8개사'처럼 개수만 적힌 회차 대응(기업 목록 없음).
    company_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # 파싱 전 원문 조각 — 파싱이 틀렸을 때 무엇을 잘못 읽었는지 추적하는 근거.
    raw_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String, default="import")  # import | system

    contact: Mapped["VcContact"] = relationship()

    @property
    def companies(self) -> list:
        """company_names(JSON) → 리스트. 값이 깨져 있어도 화면을 죽이지 않는다."""
        import json

        if not self.company_names:
            return []
        try:
            data = json.loads(self.company_names)
        except (ValueError, TypeError):
            return []
        return [str(x) for x in data] if isinstance(data, list) else []


class IrCompany(TimestampMixin, Base):
    __tablename__ = "ir_companies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    sector_major: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    sector_minor: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    series: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    one_liner: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    owner_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    ir_drive_url: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    contract_status: Mapped[str] = mapped_column(String, default="no")  # yes | no | pending
    contract_month: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    is_top_deal: Mapped[int] = mapped_column(Integer, default=0)
    funding_status: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # 기업 쪽 연락 담당자(시트 '스타트업' 명단의 성함/연락처/이메일).
    # owner_user_id(우리 팀 담당자)와 다른 사람이다 — 섞이지 않게 이름을 구분해 둔다.
    contact_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    contact_phone: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    contact_email: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # Amounts in 백만원 (millions of KRW); displayed in 억 (÷100).
    revenue_recent: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    funding_total: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    raise_target: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    pre_value: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    competitiveness: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Deal summary: cached auto-composed text; manual edit takes priority.
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    summary_status: Mapped[str] = mapped_column(String, default="draft")  # done | draft | insufficient

    @property
    def introducible(self) -> bool:
        """딜소개 문구를 만들 수 있는가 (= 발송 대상에 띄울 수 있는가).

        조건은 **실제 문구에 들어가는 것**만 본다. 문구 형식은
        `[분야] | 한줄소개 | 매출 … | 누적투자 … | Pre Value …` 이므로
        시리즈(기업구분)는 문구에 쓰이지 않는다 — 예전엔 이걸 필수로 걸어두어
        실데이터 297개 중 소개 가능이 0개가 됐다.

        - summary_status 는 사람의 판단 스위치로 남긴다(insufficient=보류).
        - 소개할 내용(분야 또는 한줄소개)과 숫자 하나 이상은 있어야 한다.
          숫자가 하나도 없으면 '이름만 나열'이 되어 소개가 되지 않는다.
        """
        if not self.name or self.summary_status == "insufficient":
            return False
        has_text = bool(self.sector_major or self.one_liner)
        has_number = any(
            v not in (None, 0)
            for v in (self.revenue_recent, self.funding_total,
                      self.raise_target, self.pre_value)
        )
        return has_text and has_number


class DealBatch(TimestampMixin, Base):
    __tablename__ = "deal_batches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    title: Mapped[str] = mapped_column(String)
    sent_date: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    cycle_type: Mapped[str] = mapped_column(String, default="adhoc")  # regular | weekly | adhoc
    opening_template_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("message_templates.id"), nullable=True
    )
    body_override: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    companies: Mapped[list["DealBatchCompany"]] = relationship(
        back_populates="batch", cascade="all, delete-orphan", order_by="DealBatchCompany.position"
    )


class DealBatchCompany(Base):
    __tablename__ = "deal_batch_companies"

    batch_id: Mapped[int] = mapped_column(ForeignKey("deal_batches.id"), primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("ir_companies.id"), primary_key=True)
    position: Mapped[int] = mapped_column(Integer, default=1)  # 1~3

    batch: Mapped["DealBatch"] = relationship(back_populates="companies")
    company: Mapped["IrCompany"] = relationship()


class SendJob(TimestampMixin, Base):
    __tablename__ = "send_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    kind: Mapped[str] = mapped_column(String, default="deal_intro")  # deal_intro | ir_delivery
    batch_id: Mapped[Optional[int]] = mapped_column(ForeignKey("deal_batches.id"), nullable=True)
    ir_request_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # Sprint 2
    # draft | queued | running | paused | done | done_with_errors | canceled
    status: Mapped[str] = mapped_column(String, default="draft")
    total: Mapped[int] = mapped_column(Integer, default=0)
    sent: Mapped[int] = mapped_column(Integer, default=0)
    failed: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    finished_at: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    items: Mapped[list["SendItem"]] = relationship(
        back_populates="job", cascade="all, delete-orphan", order_by="SendItem.id"
    )


class SendItem(TimestampMixin, Base):
    __tablename__ = "send_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("send_jobs.id"))
    contact_id: Mapped[int] = mapped_column(ForeignKey("vc_contacts.id"))
    # FK to send_sequences arrives in Sprint 3 — kept nullable, no constraint yet.
    sequence_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    stage: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # 1 day1 | 2 remind | 3 meeting
    room_name: Mapped[str] = mapped_column(String)  # snapshot at send time
    message: Mapped[str] = mapped_column(Text)      # rendered final text snapshot (immutable)
    # pending | sending | sent | failed | canceled
    status: Mapped[str] = mapped_column(String, default="pending")
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    screenshot_path: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    sent_at: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    job: Mapped["SendJob"] = relationship(back_populates="items")
    contact: Mapped["VcContact"] = relationship()


class AgentDevice(TimestampMixin, Base):
    __tablename__ = "agent_devices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True)
    token: Mapped[str] = mapped_column(String, unique=True)
    hostname: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    last_poll_at: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    agent_version: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # 어떤 발송기가 붙었는지(mock/kakao_windows/kakao_mac/telegram).
    # mock 이 붙은 채로 실발송을 시도하면 잡을 가로채므로 화면에 드러내야 한다.
    sender: Mapped[Optional[str]] = mapped_column(String, nullable=True)
