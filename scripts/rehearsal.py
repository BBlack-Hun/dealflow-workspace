"""리허설 준비 — 실제 투자사를 건드리지 않고 전 과정을 걸어 본다.

회차 당일에 처음 해 보면 늦다. 전날 한 번 끝까지 걸어 봐야 하는데, 그러려면
**실제 담당자 방으로 나가지 않는 안전한 상대**가 필요하다.

이 스크립트는 리허설용 담당자 한 명과 기업 두 개를 만든다. 담당자의 카톡방은
`DEALFLOW_TEST_ROOM`(대개 '나와의 채팅')으로 두어, 발송 프로그램이 실제로
움직여도 **나에게만** 간다.

    python scripts/rehearsal.py --check          # 지금 상태만 본다
    python scripts/rehearsal.py --setup          # 리허설 담당자·기업 만들기
    python scripts/rehearsal.py --teardown       # 리허설 흔적 지우기

실데이터는 건드리지 않는다. 만드는 것과 지우는 것 모두 이름으로 찾는다.
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app import config  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.models import (  # noqa: E402
    IrCompany,
    IrRequest,
    Meeting,
    SendSequence,
    SheetOwner,
    User,
    VcContact,
)
from app.services import readiness  # noqa: E402

# 리허설용 이름. 실데이터와 절대 겹치지 않게 접두어를 붙인다.
MARK = "[리허설]"
SHEET = f"{MARK} 명단"
CONTACT = f"{MARK} 테스트 담당자"
COMPANIES = [
    (f"{MARK} 샘플애그", "애그테크", "B2B 농산물 선도거래 플랫폼", 1200),
    (f"{MARK} 샘플메디", "헬스케어", "뇌영상 분석 AI 솔루션", 420),
]


def _user(db, phone: str = "") -> User:
    if phone:
        row = db.execute(select(User).where(User.phone == phone)).scalars().first()
        if row is None:
            raise SystemExit(f"그런 번호의 계정이 없습니다: {phone}")
        return row
    row = db.execute(
        select(User).where(User.role != "admin").order_by(User.id)
    ).scalars().first()
    if row is None:
        raise SystemExit("계정이 없습니다. scripts/add_user.py 로 먼저 만드세요.")
    return row


def setup(db, user: User) -> None:
    room = config.TEST_ROOM
    if not room:
        raise SystemExit(
            "DEALFLOW_TEST_ROOM 이 비어 있습니다.\n"
            "리허설은 실제 담당자 방으로 나가면 안 되므로 먼저 켜 주세요:\n"
            '  .env 에  DEALFLOW_TEST_ROOM="나와의 채팅"  을 넣고 다시 띄웁니다.'
        )

    sheet = db.execute(
        select(SheetOwner).where(SheetOwner.label == SHEET)
    ).scalars().first()
    if sheet is None:
        db.add(SheetOwner(label=SHEET, user_id=user.id))
    else:
        sheet.user_id = user.id

    contact = db.execute(
        select(VcContact).where(VcContact.name == CONTACT)
    ).scalars().first()
    if contact is None:
        contact = VcContact(name=CONTACT)
        db.add(contact)
    contact.user_id = user.id
    contact.title = "심사역"
    contact.firm = f"{MARK} 테스트투자"
    contact.source_sheet = SHEET
    contact.channel_kakao = 1
    contact.connect_stage = "connected"
    # 실제 방으로 나가지 않게 테스트 방 이름을 그대로 쓴다.
    contact.kakao_room_name = room
    contact.room_verified = "verified"

    for name, sector, one_liner, revenue in COMPANIES:
        company = db.execute(
            select(IrCompany).where(IrCompany.name == name)
        ).scalars().first()
        if company is None:
            company = IrCompany(name=name)
            db.add(company)
        company.sector_major = sector
        company.one_liner = one_liner
        company.revenue_recent = revenue
        company.summary_status = "done"
        company.ir_drive_url = "https://drive.google.com/file/d/rehearsal/view"

    db.commit()
    print(f"리허설 준비 완료 — 담당자 '{CONTACT}' · 기업 {len(COMPANIES)}개")
    print(f"  모든 발송이 '{room}' 방으로만 갑니다.")
    print()
    print("이 순서로 걸어 보세요:")
    print("  1) 회차 준비 점검(/readiness) 에서 막힌 것이 없는지")
    print(f"  2) 딜 제안 관리(/deals) 에서 '{MARK}' 기업 2개 + 위 담당자 선택 → 발송")
    print("  3) 발송 진행 화면에서 성공 확인 (카톡에 실제로 도착하는지)")
    print("  4) 후속 관리(/followups) 에 리마인드가 잡혔는지")
    print("  5) IR·미팅 관리(/ir) 에서 요청 기록 → [자료 보내기] → 요청이 닫히는지")
    print("  6) 미팅 등록 → 완료 → 결과 문의 날짜가 잡히는지")
    print()
    print("끝나면:  python scripts/rehearsal.py --teardown")


def teardown(db) -> None:
    contacts = db.execute(
        select(VcContact).where(VcContact.name.like(f"{MARK}%"))
    ).scalars().all()
    ids = [c.id for c in contacts]

    removed = {"요청": 0, "미팅": 0, "후속": 0, "담당자": 0, "기업": 0, "명단": 0}
    if ids:
        for model, label in ((IrRequest, "요청"), (Meeting, "미팅"),
                             (SendSequence, "후속")):
            rows = db.execute(
                select(model).where(model.contact_id.in_(ids))
            ).scalars().all()
            for row in rows:
                db.delete(row)
            removed[label] = len(rows)

    # 발송 이력은 남긴다 — 리허설을 실제로 했다는 기록은 있는 편이 낫다.
    for contact in contacts:
        # 담당자를 지우면 발송 이력이 주인을 잃으므로 명단에서만 뺀다.
        contact.source_sheet = None
        contact.connect_stage = "not_started"
        contact.kakao_room_name = None
        removed["담당자"] += 1

    for name, *_rest in COMPANIES:
        company = db.execute(
            select(IrCompany).where(IrCompany.name == name)
        ).scalars().first()
        if company is not None:
            company.summary_status = "insufficient"   # 소개 목록에서 빠진다
            company.ir_drive_url = None
            removed["기업"] += 1

    sheet = db.execute(
        select(SheetOwner).where(SheetOwner.label == SHEET)
    ).scalars().first()
    if sheet is not None:
        db.delete(sheet)
        removed["명단"] = 1

    db.commit()
    print("리허설 흔적 정리:", removed)
    print("  발송 이력은 남겼습니다 — 리허설을 실제로 했다는 기록입니다.")


def check(db, user: User) -> None:
    print(f"계정: {user.name} ({user.phone})")
    print(f"테스트 방: {config.TEST_ROOM or '(꺼짐 — 실제 담당자 방으로 나갑니다)'}")
    print()
    result = readiness.report(db, user)
    print(f"다음 회차: {result['next_send']} · {result['days_left']}일 남음")
    print(f"보낼 수 있는 상태: {'예' if result['ready'] else '아니오'}")
    print()
    for item in result["checks"]:
        mark = {"ok": "OK  ", "warn": "주의", "block": "막힘"}[item["level"]]
        print(f"  [{mark}] {item['title']:16} {item['detail']}")
        if item["action"]:
            print(f"          → {item['action']}")


def main() -> None:
    ap = argparse.ArgumentParser(description="리허설 준비 · 정리 · 점검")
    ap.add_argument("--setup", action="store_true", help="리허설 담당자·기업 만들기")
    ap.add_argument("--teardown", action="store_true", help="리허설 흔적 지우기")
    ap.add_argument("--check", action="store_true", help="지금 상태만 본다")
    ap.add_argument("--phone", default="", help="어느 계정으로 (기본: 첫 일반 계정)")
    args = ap.parse_args()

    db = SessionLocal()
    try:
        if args.teardown:
            teardown(db)
        elif args.setup:
            setup(db, _user(db, args.phone))
        else:
            check(db, _user(db, args.phone))
    finally:
        db.close()


if __name__ == "__main__":
    main()
