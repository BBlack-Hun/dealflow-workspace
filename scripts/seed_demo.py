"""Demo seed (ROADMAP task 1.3) — idempotent.

Team default templates (2 openings + 3 closings), one demo user + admin,
3 kakao-connected contacts, 3 introducible companies, and the agent device
carrying the demo token that the mock agent container uses.

Run standalone:  python scripts/seed_demo.py
Idempotent: safe to run on every container start.
"""
from __future__ import annotations

import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app import config  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.services import auth as auth_svc  # noqa: E402
from app.models import (  # noqa: E402
    AgentDevice,
    IrCompany,
    MessageTemplate,
    User,
    VcContact,
)
from app.services.room_name import build_room_name  # noqa: E402

# 실제 운영 중인 딜소개 스크립트 형식을 기본값으로 사용한다.
#   안녕하세요, 박민수 팀장님
#   우리브이씨 ASSET입니다.
#   (빈 줄)
#   핵심 딜 7개사 간단히 공유드립니다.
#   관심 가시는 기업 있으시면 IR Deck 공유드리겠습니다.
#   (빈 줄) 1) … 2) …
# 주의: 시트의 직함은 이미 '팀장님/대표님'처럼 '님'을 포함하므로 {직함} 뒤에 '님'을 또 쓰지 않는다.
# 데모 계정 비밀번호. 운영에서는 관리자가 계정을 만들고 각자 변경한다.
# (must_change_password=1 이면 첫 로그인 후 변경 화면으로 보낸다)
DEMO_PASSWORD = config.INITIAL_PASSWORD

TEAM_TEMPLATES = [
    ("opening_first", "안녕하세요, {담당자명} {직함}\n우리브이씨 ASSET입니다."),
    ("opening_re", "안녕하세요, {담당자명} {직함}\n우리브이씨 ASSET입니다."),
    ("closing_day1", "핵심 딜 {개수}개사 간단히 공유드립니다.\n관심 가시는 기업 있으시면 IR Deck 공유드리겠습니다."),
    ("closing_remind", "지난번 공유드린 기업들 검토 중 궁금하신 점 있으시면 말씀 부탁드립니다."),
    ("closing_meeting", "다음주 또는 다다음주 20~30분 정도 간단히 미팅 가능하실지요?"),
]

# 개발용 추가 사용자 (가상). Mac·Windows 두 기기로 **동시에** 테스트하려면 기기마다
# 다른 사용자를 골라야 한다 — 같은 사용자로 두 대를 붙이면 먼저 poll 한 쪽이 잡을
# 가져가 발송이 어디로 갈지 예측할 수 없다(사용자 1명 = 에이전트 1대).
# 정식 로그인(휴대폰번호 + 비밀번호)은 다음 스프린트. 번호는 하이픈 없이 숫자만.
EXTRA_USERS = [
    dict(name="김영희", phone="01000000002", role="user"),
    dict(name="이철수", phone="01000000003", role="user"),
]

# 사용자별 담당자 — 화면에서 '내 것만 보인다'가 실제로 확인되게 소량만 넣는다.
EXTRA_CONTACTS = {
    "01000000002": [
        dict(group_name="A그룹", name="장하늘", title="심사역", firm="바사벤처스",
             stages="Seed", sectors="커머스", memo="커머스 초기 위주"),
        dict(group_name="B그룹", name="문재원", title="대표님", firm="아자캐피탈",
             stages="SeriesB", sectors="제조", memo="후기 라운드"),
    ],
    "01000000003": [
        dict(group_name="A그룹", name="오세라", title="팀장님", firm="카타인베스트",
             stages="SeriesA", sectors="모빌리티", memo="모빌리티 관심"),
    ],
}

DEMO_CONTACTS = [
    dict(group_name="A그룹", name="홍길동", title="대표님", firm="가나벤처스",
         round_size="라운드 30~100억", kakao_room_name="홍길동 대표님 가나벤처스 Deal 공유 우리브이씨 Asset",
         room_verified="verified", stages="SeriesA,SeriesB", sectors="AI,SaaS",
         memo="AI 인프라 선호, 리드 가능"),
    dict(group_name="B그룹", name="김서연", title="심사역", firm="마바벤처스",
         round_size="라운드 10~30억", kakao_room_name="김서연 심사역님 마바벤처스 Deal 공유 우리브이씨 Asset",
         room_verified="verified", stages="Seed,SeriesA", sectors="헬스케어,바이오",
         memo="헬스케어 딜 활발"),
    dict(group_name="A그룹", name="박준호", title="파트너", firm="사아파트너스",
         round_size="라운드 50~200억", kakao_room_name="박준호 파트너님 사아파트너스 Deal 공유 우리브이씨 Asset",
         room_verified="unverified", stages="SeriesB,Pre-IPO", sectors="핀테크,플랫폼",
         memo="후기 라운드 중심"),
]

DEMO_COMPANIES = [
    dict(name="샘플애그", sector_major="애그테크", sector_minor="B2B 유통", series="SeriesA",
         one_liner="B2B 농산물 선도거래 'Presell'", ir_drive_url="https://drive.google.com/file/d/1AbC/view",
         contract_status="yes", contract_month="2026-07", is_top_deal=1,
         funding_status="Series A 진행 중", revenue_recent=3090, funding_total=560,
         raise_target=5000, pre_value=21000, competitiveness="상급 유통사 12곳 계약",
         summary_status="done"),
    dict(name="샘플메디", sector_major="헬스케어", sector_minor="의료AI", series="Seed",
         one_liner="뇌영상 분석 AI 솔루션", ir_drive_url="https://drive.google.com/file/d/2DeF/view",
         contract_status="pending", is_top_deal=0, funding_status="Seed 마감 임박",
         revenue_recent=420, funding_total=1500, raise_target=3000, pre_value=8000,
         competitiveness="대학병원 3곳 PoC", summary_status="done"),
    dict(name="샘플페이", sector_major="핀테크", sector_minor="결제", series="SeriesB",
         one_liner="가맹점 정산 자동화 플랫폼", ir_drive_url="https://drive.google.com/file/d/3GhI/view",
         contract_status="no", is_top_deal=1, funding_status="Series B 라운드 오픈",
         revenue_recent=12000, funding_total=8000, raise_target=15000, pre_value=60000,
         competitiveness="월 거래액 300억 돌파", summary_status="done"),
]


def _get_or_create(db, model, defaults=None, **filters):
    obj = db.execute(select(model).filter_by(**filters)).scalar_one_or_none()
    if obj:
        return obj, False
    params = dict(filters)
    if defaults:
        params.update(defaults)
    obj = model(**params)
    db.add(obj)
    db.flush()
    return obj, True


def main() -> None:
    db = SessionLocal()
    created = {"users": 0, "templates": 0, "contacts": 0, "companies": 0, "agents": 0}
    try:
        # Users
        user, c = _get_or_create(
            db, User, id=config.CURRENT_USER_ID,
            defaults=dict(name="정훈", phone="01012345678", role="user", weekly_goal_sends=30),
        )
        created["users"] += int(c)
        _admin, c = _get_or_create(
            db, User, phone="01099998888",
            defaults=dict(name="김리더", role="admin"),
        )
        created["users"] += int(c)

        # Team default templates (user_id NULL)
        for kind, body in TEAM_TEMPLATES:
            existing = db.execute(
                select(MessageTemplate).where(
                    MessageTemplate.user_id.is_(None), MessageTemplate.kind == kind
                )
            ).scalar_one_or_none()
            if existing is None:
                db.add(MessageTemplate(user_id=None, kind=kind, body=body, is_active=1))
                created["templates"] += 1

        # Companies (owned by demo user)
        for spec in DEMO_COMPANIES:
            _obj, c = _get_or_create(db, IrCompany, name=spec["name"],
                                     defaults=dict(owner_user_id=user.id, **spec))
            created["companies"] += int(c)

        # Contacts (owned by demo user, kakao connected)
        for spec in DEMO_CONTACTS:
            _obj, c = _get_or_create(
                db, VcContact, name=spec["name"], firm=spec["firm"],
                defaults=dict(user_id=user.id, channel_kakao=1, channel_email=1,
                              status="active", **spec),
            )
            created["contacts"] += int(c)

        # Agent device with demo token (shared with mock agent container)
        _dev, c = _get_or_create(
            db, AgentDevice, user_id=user.id,
            defaults=dict(token=config.DEMO_AGENT_TOKEN, hostname="demo-agent", agent_version="0.1.0"),
        )
        created["agents"] += int(c)

        # 개발용 추가 사용자 + 각자의 담당자·토큰
        for spec in EXTRA_USERS:
            extra, c = _get_or_create(db, User, phone=spec["phone"],
                                      defaults=dict(name=spec["name"], role=spec["role"]))
            created["users"] += int(c)
            for contact in EXTRA_CONTACTS.get(spec["phone"], []):
                _obj, c = _get_or_create(
                    db, VcContact, name=contact["name"], firm=contact["firm"],
                    defaults=dict(
                        user_id=extra.id, channel_kakao=1, status="active",
                        invited_status="완료",
                        kakao_room_name=build_room_name(contact["name"], contact.get("title"),
                                                        contact["firm"]),
                        room_verified="unverified", **contact),
                )
                created["contacts"] += int(c)
            # 토큰은 사용자마다 달라야 기기별로 잡이 갈린다. 공개 저장소에 고정 토큰을
            # 더 늘리지 않도록 무작위로 발급하고, 값은 /setup 화면에서 확인한다.
            _dev, c = _get_or_create(
                db, AgentDevice, user_id=extra.id,
                defaults=dict(token=f"agt_{secrets.token_hex(16)}", hostname="", agent_version=""),
            )
            created["agents"] += int(c)

        # 비밀번호가 없는 계정에 데모 비밀번호를 넣는다(기존 계정은 건드리지 않음).
        for u in db.query(User).all():
            if not u.password_hash:
                u.password_hash = auth_svc.hash_password(DEMO_PASSWORD)
                u.must_change_password = 1

        db.commit()
        print(f"[seed] 데모 비밀번호: {DEMO_PASSWORD} (첫 로그인 후 변경 요구)")
        print(f"[seed] done. created={created} (idempotent; existing rows kept)")
        print(f"[seed] demo user id={user.id}, agent token={config.DEMO_AGENT_TOKEN}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
