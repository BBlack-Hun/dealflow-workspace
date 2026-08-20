"""빈 DB 를 쓸 수 있는 상태로 만든다 — 그 이상은 하지 않는다.

예전엔 이 자리에 데모 데이터(가상 담당자·기업·사용자)가 함께 들어 있었고
컨테이너가 뜰 때마다 실행됐다. 실데이터를 넣고 나니 화면과 발송 대상에
샘플 기업·가상 담당자가 섞여 보였다. 그래서 둘을 갈랐다.

- **부트스트랩**(항상): 팀 기본 문구 5종 + 관리자 계정 1개.
  이게 없으면 문구를 조합할 수 없고 아무도 로그인할 수 없다.
- **데모 데이터**(``DEALFLOW_SEED_DEMO=1`` 일 때만): 가상 사용자·담당자·기업.
  처음 화면을 둘러보거나 mock 에이전트를 돌릴 때만 쓴다.

이미 들어간 데모 데이터를 지우려면 ``scripts/purge_demo.py`` 를 쓴다.

단독 실행:  python scripts/bootstrap.py
여러 번 실행해도 안전하다(있으면 건너뛴다).
"""
from __future__ import annotations

import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app import config  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.models import (  # noqa: E402
    AgentDevice,
    IrCompany,
    MessageTemplate,
    User,
    VcContact,
)
from app.services import auth as auth_svc  # noqa: E402
from app.services.room_name import build_room_name  # noqa: E402

# 실제 운영 중인 딜소개 스크립트 형식을 기본값으로 사용한다.
#   안녕하세요, 박민수 팀장님
#   우리브이씨 ASSET입니다.
#   (빈 줄)
#   핵심 딜 7개사 간단히 공유드립니다.
#   관심 가시는 기업 있으시면 IR Deck 공유드리겠습니다.
#   (빈 줄) 1) … 2) …
# 주의: 시트의 직함은 이미 '팀장님/대표님'처럼 '님'을 포함하므로 {직함} 뒤에 '님'을 또 쓰지 않는다.
TEAM_TEMPLATES = [
    ("opening_first", "안녕하세요, {담당자명} {직함}\n우리브이씨 ASSET입니다."),
    ("opening_re", "안녕하세요, {담당자명} {직함}\n우리브이씨 ASSET입니다."),
    ("closing_day1", "핵심 딜 {개수}개사 간단히 공유드립니다.\n관심 가시는 기업 있으시면 IR Deck 공유드리겠습니다."),
    ("closing_remind", "지난번 공유드린 기업들 검토 중 궁금하신 점 있으시면 말씀 부탁드립니다."),
    ("closing_meeting", "다음주 또는 다다음주 20~30분 정도 간단히 미팅 가능하실지요?"),
    # 딜소개를 보냈는데 반응이 없을 때, 기업 목록 없이 이 문구만 보낸다.
    # 목록을 또 밀어 넣기보다 무엇을 보고 싶은지 되묻는 편이 답이 온다.
    ("ask_preference", "선호하는 기업분야 말씀해주시면 맞추어 딜 공유해드리겠습니다."),
]

# 관리자 계정. 실제 팀원 계정은 관리자가 scripts/add_user.py 로 만든다.
ADMIN_PHONE = "01099998888"
ADMIN_NAME = "관리자"

# ── 아래는 DEALFLOW_SEED_DEMO=1 일 때만 들어간다 (전부 가상) ──────────────
DEMO_USERS = [
    dict(name="김영희", phone="01000000002", role="user"),
    dict(name="이철수", phone="01000000003", role="user"),
]

DEMO_CONTACTS = [
    dict(group_name="A그룹", name="홍길동", title="대표님", firm="가나벤처스",
         round_size="라운드 30~100억",
         kakao_room_name="홍길동 대표님 가나벤처스 Deal 공유 우리브이씨 Asset",
         room_verified="verified", stages="SeriesA,SeriesB", sectors="AI,SaaS",
         memo="AI 인프라 선호, 리드 가능"),
    dict(group_name="B그룹", name="김서연", title="심사역", firm="마바벤처스",
         round_size="라운드 10~30억",
         kakao_room_name="김서연 심사역님 마바벤처스 Deal 공유 우리브이씨 Asset",
         room_verified="verified", stages="Seed,SeriesA", sectors="헬스케어,바이오",
         memo="헬스케어 딜 활발"),
    dict(group_name="A그룹", name="박준호", title="파트너", firm="사아파트너스",
         round_size="라운드 50~200억",
         kakao_room_name="박준호 파트너님 사아파트너스 Deal 공유 우리브이씨 Asset",
         room_verified="unverified", stages="SeriesB,Pre-IPO", sectors="핀테크,플랫폼",
         memo="후기 라운드 중심"),
]

DEMO_EXTRA_CONTACTS = {
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

DEMO_COMPANIES = [
    dict(name="샘플애그", sector_major="애그테크", sector_minor="B2B 유통", series="SeriesA",
         one_liner="B2B 농산물 선도거래 'Presell'",
         ir_drive_url="https://drive.google.com/file/d/1AbC/view",
         contract_status="yes", contract_month="2026-07", is_top_deal=1,
         funding_status="Series A 진행 중", revenue_recent=3090, funding_total=560,
         raise_target=5000, pre_value=21000, competitiveness="상급 유통사 12곳 계약",
         summary_status="done"),
    dict(name="샘플메디", sector_major="헬스케어", sector_minor="의료AI", series="Seed",
         one_liner="뇌영상 분석 AI 솔루션",
         ir_drive_url="https://drive.google.com/file/d/2DeF/view",
         contract_status="pending", is_top_deal=0, funding_status="Seed 마감 임박",
         revenue_recent=420, funding_total=1500, raise_target=3000, pre_value=8000,
         competitiveness="대학병원 3곳 PoC", summary_status="done"),
    dict(name="샘플페이", sector_major="핀테크", sector_minor="결제", series="SeriesB",
         one_liner="가맹점 정산 자동화 플랫폼",
         ir_drive_url="https://drive.google.com/file/d/3GhI/view",
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


def bootstrap(db) -> dict:
    """어떤 환경에서도 필요한 최소한 — 팀 기본 문구 + 관리자 계정."""
    made = {"templates": 0, "users": 0}

    for kind, body in TEAM_TEMPLATES:
        exists = db.execute(
            select(MessageTemplate).where(
                MessageTemplate.user_id.is_(None), MessageTemplate.kind == kind
            )
        ).scalar_one_or_none()
        if exists is None:
            db.add(MessageTemplate(user_id=None, kind=kind, body=body, is_active=1))
            made["templates"] += 1

    _admin, created = _get_or_create(
        db, User, phone=ADMIN_PHONE,
        defaults=dict(name=ADMIN_NAME, role="admin"),
    )
    made["users"] += int(created)
    return made


def seed_demo(db) -> dict:
    """둘러보기·mock 에이전트용 가상 데이터. 운영 DB 에는 들어가지 않는다."""
    made = {"users": 0, "contacts": 0, "companies": 0, "agents": 0}

    owner, created = _get_or_create(
        db, User, id=config.CURRENT_USER_ID,
        defaults=dict(name="데모", phone="01012345678", role="user", weekly_goal_sends=30),
    )
    made["users"] += int(created)

    for spec in DEMO_COMPANIES:
        _obj, c = _get_or_create(db, IrCompany, name=spec["name"],
                                 defaults=dict(owner_user_id=owner.id, **spec))
        made["companies"] += int(c)

    for spec in DEMO_CONTACTS:
        _obj, c = _get_or_create(
            db, VcContact, name=spec["name"], firm=spec["firm"],
            defaults=dict(user_id=owner.id, channel_kakao=1, channel_email=1,
                          status="active", **spec),
        )
        made["contacts"] += int(c)

    _dev, c = _get_or_create(
        db, AgentDevice, user_id=owner.id,
        defaults=dict(token=config.DEMO_AGENT_TOKEN, hostname="demo-agent",
                      agent_version="0.1.0"),
    )
    made["agents"] += int(c)

    # 기기 두 대로 동시에 테스트하려면 사용자를 갈라야 한다 — 같은 사용자로 두 대를
    # 붙이면 먼저 poll 한 쪽이 잡을 가져가 발송이 어디로 갈지 알 수 없다.
    for spec in DEMO_USERS:
        extra, c = _get_or_create(db, User, phone=spec["phone"],
                                  defaults=dict(name=spec["name"], role=spec["role"]))
        made["users"] += int(c)
        for contact in DEMO_EXTRA_CONTACTS.get(spec["phone"], []):
            _obj, c = _get_or_create(
                db, VcContact, name=contact["name"], firm=contact["firm"],
                defaults=dict(
                    user_id=extra.id, channel_kakao=1, status="active",
                    invited_status="완료",
                    kakao_room_name=build_room_name(contact["name"], contact.get("title"),
                                                    contact["firm"]),
                    room_verified="unverified", **contact),
            )
            made["contacts"] += int(c)
        # 공개 저장소에 고정 토큰을 늘리지 않도록 무작위 발급 — 값은 /setup 에서 본다.
        _dev, c = _get_or_create(
            db, AgentDevice, user_id=extra.id,
            defaults=dict(token=f"agt_{secrets.token_hex(16)}", hostname="", agent_version=""),
        )
        made["agents"] += int(c)

    return made


def main() -> None:
    db = SessionLocal()
    try:
        made = bootstrap(db)
        print(f"[bootstrap] 팀 기본 문구/관리자: {made}")

        if config.SEED_DEMO:
            demo = seed_demo(db)
            print(f"[bootstrap] 데모 데이터(DEALFLOW_SEED_DEMO=1): {demo}")
        else:
            print("[bootstrap] 데모 데이터 생략 (넣으려면 DEALFLOW_SEED_DEMO=1)")

        # 비밀번호가 없는 계정에만 초기 비밀번호를 넣는다(기존 계정은 건드리지 않음).
        filled = 0
        for u in db.query(User).all():
            if not u.password_hash:
                u.password_hash = auth_svc.hash_password(config.INITIAL_PASSWORD)
                u.must_change_password = 1
                filled += 1
        db.commit()
        if filled:
            print(f"[bootstrap] 초기 비밀번호를 넣은 계정 {filled}개 (첫 로그인 후 변경 요구)")
    finally:
        db.close()


if __name__ == "__main__":
    main()
