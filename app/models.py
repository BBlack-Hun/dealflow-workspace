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
    # user       — 딜소개를 하는 사람 (기본)
    # admin      — 팀 전체를 본다
    # consultant — **투자컨설턴트 현황만** 본다. 딜소개를 하지 않는 사람이라
    #              발송·투자사 명단을 보여줄 이유가 없다(볼 수 있으면 실수로
    #              건드린다). 계정 자체가 그 화면 전용이다.
    role: Mapped[str] = mapped_column(String, default="user")
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
    # 시트에 있는데 앱에 칸이 없어 통째로 버려지던 값들.
    # "명함 받은 날" 은 언제부터 아는 사이인지를 말해 준다 — 오래 알던 분께
    # 처음 연락하는 문구를 보내면 어색하다.
    office_fax: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    card_registered_at: Mapped[Optional[str]] = mapped_column(String, nullable=True)

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
    department: Mapped[Optional[str]] = mapped_column(String, nullable=True)   # 부서
    # 카톡방까지 연결됐는가. 발송 대상이 되기 전 단계를 여기서 관리한다.
    # connected(연결 완료) | in_progress(진행 중) | declined(참여 안 함) | not_started(미착수)
    connect_stage: Mapped[str] = mapped_column(String, default="not_started")
    # 시트의 '담당자' 원문. 그 이름의 계정이 아직 없어도 **버리지 않는다** —
    # 버리면 누구 담당인지가 사라져 임포트한 사람에게 전부 붙어 버린다.
    assignee_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # 어떤 돈인가 (vc | ac | angel | cvc | pe | securities | bank | public | other)
    firm_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
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
    # 연도별 매출. 시트가 22~25년을 따로 들고 있다 — 한 해만 남기면 성장 추세가
    # 사라진다("작년 대비" 가 딜소개에서 자주 쓰인다).
    #
    # **글자로 담는다.** 원본에 `8.2억` · `1,224백만원` · `150억 ~ 200억` 이
    # 한 칸에 섞여 있어서, 숫자로 바꾸려면 단위를 판별해야 한다. 잘못 읽으면
    # 100배가 틀어진 채 딜소개 문구에 실려 나간다 — 적은 그대로가 안전하다.
    revenue_2022: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    revenue_2023: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    revenue_2024: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    revenue_2025: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    founded_year: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # 스타트업DB 시트의 `사업분야` — **카테고리가 아니라 사업 설명**이다.
    # (카테고리는 sector_major/minor 로 따로 있다.)
    # 한줄 소개의 **첫 토막**이 이 값이다:
    #   {사업 설명} | 매출 N억 | 누적투자금액 N억 | … | {특이사항}
    business_desc: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # `핵심` · `TOP` · `핵심, TOP`. 켜짐/꺼짐 하나로는 어느 쪽인지 알 수 없다.
    # `is_top_deal` 은 그대로 둔다 — 발송 화면의 '추천 딜' 이 그 값을 쓴다.
    top_deal_kind: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # 기보·신보·중진공 — 보증/정책자금 이력. 투자사가 자주 묻는다.
    guarantee: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # 이 기업을 맡은 팀원. 투자사 쪽 `assignee_name` 과 같은 성격이다.
    assignee_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)

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
    # 받는 사람은 둘 중 **하나**다. 투자사 담당자(딜소개·IR·후속)이거나,
    # 딜 소싱 명단(우리 딜을 같이 볼 사람)이거나. 소싱은 다른 표에 있어서
    # 가리키는 칸이 따로 있고, 그래서 이 칸이 빌 수 있다.
    contact_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("vc_contacts.id"), nullable=True)
    sourcing_contact_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("sourcing_contacts.id"), nullable=True)
    # FK to send_sequences arrives in Sprint 3 — kept nullable, no constraint yet.
    sequence_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    stage: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # 1 day1 | 2 remind | 3 meeting
    # 어디로 나가는가. kakao = 각자 PC의 발송 프로그램, email = 서버가 SMTP 로 직접.
    # 나가는 길이 달라서, 이 값이 없으면 메일 건을 카톡 프로그램이 집어간다.
    channel: Mapped[str] = mapped_column(String, default="kakao")
    room_name: Mapped[str] = mapped_column(String)  # 카톡방 제목 · 메일이면 받는 주소
    subject: Mapped[Optional[str]] = mapped_column(String, nullable=True)   # 메일 제목
    message: Mapped[str] = mapped_column(Text)      # rendered final text snapshot (immutable)
    # **여러 통으로 나눠 보낼 때**의 순서(JSON 배열). IR 자료 전달이 그렇다 —
    # 링크를 먼저 한 통씩 던지고 마지막에 설명을 붙인다. 카톡에서는 링크가
    # 각자 미리보기 카드로 떠야 하고, 설명이 그 아래 와야 읽힌다.
    #
    # 비어 있으면 `message` 를 한 통으로 보낸다(지금까지의 동작).
    # `message` 는 항상 **합친 전문**이라, 이 칸을 모르는 예전 발송 프로그램도
    # 순서가 맞는 한 통을 보낸다.
    parts_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # pending | sending | sent | failed | canceled
    status: Mapped[str] = mapped_column(String, default="pending")
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    screenshot_path: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    sent_at: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    job: Mapped["SendJob"] = relationship(back_populates="items")
    contact: Mapped[Optional["VcContact"]] = relationship()
    sourcing_contact: Mapped[Optional["SourcingContact"]] = relationship()

    @property
    def recipient_name(self) -> Optional[str]:
        """누구에게 갔는가. 화면·기록에서 이 값만 쓴다 —
        받는 사람이 두 표에 나뉘어 있는 것을 부르는 쪽이 알 필요는 없다."""
        who = self.contact or self.sourcing_contact
        return who.name if who else None


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


class SourcingContact(TimestampMixin, Base):
    """딜 소싱에 참여하는 심사역·투자사.

    투자사 관리 현황(딜소개를 **보내는** 명단)과는 성격이 다르다. 여기는
    "우리 딜을 같이 볼 사람" 이라 시리즈 A 이상·개인 참여·M&A·후속투자처럼
    **찾는 것**으로 나뉜다. 같은 사람이 여러 갈래에 들어갈 수 있다.

    `bucket` 이 그 갈래(원본 시트의 탭 이름)다.
    """

    __tablename__ = "sourcing_contacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bucket: Mapped[str] = mapped_column(String)          # 시트 탭 이름
    position: Mapped[int] = mapped_column(Integer, default=0)

    name: Mapped[str] = mapped_column(String)
    title: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    firm: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    assignee_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    requested_at: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    share_method: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    sectors: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    round_size: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    tips: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    memo: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    kakao_reply: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    call_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # 소싱 명단은 투자사 관리 현황과 거의 겹치지 않는다 — 39명 중 7명뿐이다.
    # 기존 담당자를 찾아 붙이는 방식으로는 나머지 32명에게 못 보내므로
    # 여기도 자기 카톡방을 가진다.
    kakao_room_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    room_verified: Mapped[str] = mapped_column(String, default="unverified")


class RefSheet(TimestampMixin, Base):
    """참고 시트 — 원본 스프레드시트의 '자료' 탭들.

    투자사 명단 말고도 시트에는 스크립트·가이드·성격 정리 같은 탭이 여럿
    있었다. 매번 구글 시트를 따로 열어 보던 자료라 화면 안으로 들여온다.

    모양이 제각각이다:
      table — `투자사 성격정리` 처럼 진짜 표 (머리글 + 행)
      text  — `딜소개 스크립트` 처럼 줄글

    **지울 수 있어야 한다.** 다 옮겨 놓고 쓰면서 추리는 것이 순서라,
    안 쓰는 탭이 남아 있으면 자리만 차지한다.
    """

    __tablename__ = "ref_sheets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String)
    kind: Mapped[str] = mapped_column(String, default="text")   # table | text
    # table 이면 {"columns": [...], "rows": [[...]]}, text 면 {"body": "..."}
    content_json: Mapped[str] = mapped_column(Text, default="{}")
    position: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[int] = mapped_column(Integer, default=1)


class ConsultingColumn(TimestampMixin, Base):
    """투자컨설턴트 현황표의 '월별 리마인드' 열.

    원본 시트에는 `8월 마지막주 리마인드 톡 or TEL` 같은 열이 달마다 하나씩 늘어난다.
    이걸 테이블 컬럼으로 두면 매달 마이그레이션을 해야 하므로 **행으로** 둔다.
    열 이름을 그대로 보관해 화면이 시트와 같아 보이게 한다.
    """

    __tablename__ = "consulting_columns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # 월 컬럼도 시트마다 다르다 — `중요 스타트업` 은 6·7·8월, `경영본부 전달
    # 기업` 은 6·7월처럼. 섞으면 없는 달의 빈 칸이 생긴다.
    sheet: Mapped[str] = mapped_column(String, default="중요 스타트업")
    label: Mapped[str] = mapped_column(String)          # 시트의 열 이름 그대로
    position: Mapped[int] = mapped_column(Integer, default=0)   # 왼→오 순서


class ConsultingCompany(TimestampMixin, Base):
    """투자컨설턴트 현황표 한 줄 = 기업 하나.

    시트가 원본이라 값은 대부분 자유 문장이다(미팅일이 `9/16 PM2 (화상미팅)` 처럼
    적혀 있다). 형식을 강제하면 원본을 옮길 수 없으므로 문자열로 받는다.
    월별 리마인드 내용은 열이 늘어나므로 JSON 으로 담는다(키 = 열 id).
    """

    __tablename__ = "consulting_companies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # 어느 시트에서 왔는가. 원본이 `중요 스타트업`·`경영본부 전달 기업` 처럼
    # 나뉘어 있고 관리하는 사람이 다르다 — 한 표에 쏟으면 자기 명단을 못 찾는다.
    sheet: Mapped[str] = mapped_column(String, default="중요 스타트업")
    position: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)   # 시트의 NO
    region: Mapped[Optional[str]] = mapped_column(String, nullable=True)      # 지역
    meeting_at: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # 미팅일
    company_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # 기업명/계약일/무료유료/수수료
    management: Mapped[Optional[str]] = mapped_column(Text, nullable=True)    # 기업 관리
    ceo_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)    # 대표자
    phone: Mapped[Optional[str]] = mapped_column(String, nullable=True)       # 연락처
    email: Mapped[Optional[str]] = mapped_column(String, nullable=True)       # 이메일
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)         # {"열id": "내용"}


class ScheduleRule(TimestampMixin, Base):
    """발송 주기 규칙 — 코드가 아니라 DB 가 정한다.

    "매월 첫째·셋째 수요일", "딜소개 6~7일 뒤 리마인드" 같은 값은 운영하며 바뀐다
    (실제로 '매주'에서 '월 2회'로 한 번 바뀌었다). 코드에 박아 두면 바뀔 때마다
    배포해야 하고, 언제부터 바뀐 규칙인지도 남지 않는다.

    두 종류를 한 테이블에 담는다.
    - `monthly_weekday` : 회차일. weekday + nth_weeks 를 쓴다 (수요일 · 1,3번째)
    - `offset_days`     : 후속. offset_min_days ~ offset_max_days 뒤 (6~7일 뒤)
    """

    __tablename__ = "schedule_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String, unique=True)   # deal_cycle | remind | meeting
    label: Mapped[str] = mapped_column(String)
    kind: Mapped[str] = mapped_column(String)               # monthly_weekday | offset_days
    weekday: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)      # 0=월 … 2=수
    nth_weeks: Mapped[Optional[str]] = mapped_column(String, nullable=True)     # "1,3"
    offset_min_days: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    offset_max_days: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # 주말에 걸리면 다음 영업일로 민다. 토요일에 딜소개를 보내지는 않는다.
    skip_weekend: Mapped[int] = mapped_column(Integer, default=1)
    effective_from: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    is_active: Mapped[int] = mapped_column(Integer, default=1)
    # 규칙에서 벗어난 일회성 회차일(YYYY-MM-DD, 쉼표로 여러 개).
    # 실제로 "다음 회차는 8/26" 처럼 규칙 밖 날짜가 정해져 내려온다.
    # 규칙을 고치면 그 달 이후가 전부 따라 바뀌므로, 한 번짜리는 여기 둔다.
    extra_dates: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # 반대로 규칙상 잡히지만 건너뛰는 날.
    skip_dates: Mapped[Optional[str]] = mapped_column(String, nullable=True)


class SendSequence(TimestampMixin, Base):
    """담당자 한 명의 후속 흐름 — 딜소개 → 리마인드 → 미팅 요청.

    딜소개가 **성공한 뒤에만** 시작한다. 발송 목록을 만든 시점에 시작하면
    실패한 건까지 후속이 예약되어, 받은 적 없는 사람에게 "지난번 공유드린" 이 나간다.

    답이 오면 멈춘다(`responded`). IR 요청이나 미팅이 잡혔는데도 리마인드가
    계속 나가는 것이 이 기능에서 가장 나쁜 실패다.
    """

    __tablename__ = "send_sequences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    contact_id: Mapped[int] = mapped_column(ForeignKey("vc_contacts.id"))
    batch_id: Mapped[Optional[int]] = mapped_column(ForeignKey("deal_batches.id"), nullable=True)
    # 지금까지 보낸 마지막 단계 (1 딜소개 · 2 리마인드 · 3 미팅요청)
    stage: Mapped[int] = mapped_column(Integer, default=1)
    # active(예약됨) | responded(답 옴) | stopped(사람이 중단) | done(끝까지 보냄)
    status: Mapped[str] = mapped_column(String, default="active")
    day1_sent_at: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    last_sent_at: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    next_stage: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)   # 2 | 3
    next_due_date: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # YYYY-MM-DD
    stopped_reason: Mapped[Optional[str]] = mapped_column(String, nullable=True)


class SheetOwner(TimestampMixin, Base):
    """명단(시트) 하나 = 담당 팀원 한 명.

    담당은 사람이 아니라 **명단 단위**로 정해진다. "○○○ 딜소개현황" 은 그 사람의
    명단이고, 신규 연결 명단은 다른 팀원의 명단이다. 한 사람이 두 명단에 겹쳐
    있어도 담당은 명단이 정한다.

    이걸 두지 않으면 시트를 올린 사람에게 팀 전체가 붙는다 — 실제로 한 사람의
    대시보드에 333명이 '내 담당'으로 잡혔다.

    `user_id` 가 비어 있으면 아직 그 팀원의 계정이 없다는 뜻이다. 그 명단은
    누구의 대시보드에도 잡히지 않고, 계정을 만들어 연결하면 그때 넘어간다.
    """

    __tablename__ = "sheet_owners"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    label: Mapped[str] = mapped_column(String, unique=True)     # source_sheet 값
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    assignee_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # 시트의 담당자 원문


class IrRequest(TimestampMixin, Base):
    """투자사가 "이 기업 IR 자료 주세요" 한 건.

    딜소개를 보내면 여기서 답이 온다. 요청을 받고 자료를 보내기까지가 이 화면의 일이다.
    받은 것을 놓치면 그 회차에서 가장 뜨거운 반응을 흘려보내는 셈이라,
    **열린 요청**이 먼저 보여야 한다.

    기업은 우리 DB 에 없을 수도 있다(투자사가 다른 이름으로 부르거나, 아직
    등록 안 된 기업). 그래서 `company_id` 는 비워 둘 수 있고 이름은 늘 남긴다.
    """

    __tablename__ = "ir_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    contact_id: Mapped[int] = mapped_column(ForeignKey("vc_contacts.id"))
    company_id: Mapped[Optional[int]] = mapped_column(ForeignKey("ir_companies.id"),
                                                      nullable=True)
    company_name: Mapped[str] = mapped_column(String)      # 요청받은 그대로
    requested_at: Mapped[str] = mapped_column(String)      # YYYY-MM-DD
    # open(요청받음) | delivered(자료 전달함) | dropped(보내지 않기로 함)
    status: Mapped[str] = mapped_column(String, default="open")
    delivered_at: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class Meeting(TimestampMixin, Base):
    """투자사 미팅 한 건.

    미팅이 잡히면 그날까지 챙겨야 하고, 끝나면 **열흘 뒤 결과를 물어야** 한다.
    그 열흘을 사람이 기억하는 대신 여기 적어 둔다.
    """

    __tablename__ = "meetings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    contact_id: Mapped[int] = mapped_column(ForeignKey("vc_contacts.id"))
    company_id: Mapped[Optional[int]] = mapped_column(ForeignKey("ir_companies.id"),
                                                      nullable=True)
    company_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    scheduled_at: Mapped[str] = mapped_column(String)      # YYYY-MM-DD
    kind: Mapped[str] = mapped_column(String, default="first")   # first | second | etc
    # scheduled(예정) | done(완료) | canceled(취소)
    status: Mapped[str] = mapped_column(String, default="scheduled")
    done_at: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # 미팅 결과 — reviewing(검토 중) | investing(투자 검토) | hold(보류) | pass(거절)
    outcome: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # 미팅 뒤 결과를 물어볼 날. 완료 처리하면 자동으로 잡힌다.
    followup_due: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    followup_done: Mapped[int] = mapped_column(Integer, default=0)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class WeeklyRoutine(TimestampMixin, Base):
    """매주 되풀이하는 업무. 요일이 오면 그 주 목록에 저절로 생긴다.

    시트에는 목록 아래에 규칙이 글로 적혀 있었다("* 이메일 발송 — 매주 화요일,
    목요일"). 사람이 그걸 읽고 매주 손으로 옮겨 적다 보니 빠지는 주가 생겼다.
    """

    __tablename__ = "weekly_routines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    category: Mapped[str] = mapped_column(String)          # 항목
    title: Mapped[str] = mapped_column(Text)               # 세부업무
    weekdays: Mapped[str] = mapped_column(String, default="")   # "0,2" = 월,수
    # 언제 하는 일인지 — 시트에 "화요일 오전" 처럼 시간대까지 적혀 있었다.
    # 비어 있으면 하루 중 아무 때나(예: 이메일 정리).
    time_of_day: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # am | pm
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[int] = mapped_column(Integer, default=1)


class WeeklyTask(TimestampMixin, Base):
    """주간 업무 한 줄 — 항목 · 세부업무 · 일시 · 상태.

    시트의 체크리스트를 그대로 옮긴다. 손으로 적던 것이라 **고칠 수 있어야** 한다.
    시스템이 아는 일(후속 발송·IR 요청 등)은 여기 넣지 않고 화면에서 따로 보여준다 —
    같은 것을 두 곳에 적으면 어긋난다.
    """

    __tablename__ = "weekly_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    week_start: Mapped[str] = mapped_column(String)        # 그 주 월요일 (YYYY-MM-DD)
    category: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    title: Mapped[str] = mapped_column(Text)
    due_date: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # todo(예정) | doing(진행중) | done(완료)
    status: Mapped[str] = mapped_column(String, default="todo")
    position: Mapped[int] = mapped_column(Integer, default=0)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # 반복 업무에서 생긴 줄이면 그 규칙. 같은 주에 두 번 만들지 않으려고 쓴다.
    routine_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("weekly_routines.id"), nullable=True)

