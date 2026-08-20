"""DB 에 남은 데모·테스트 흔적을 지운다.

개발 중에 들어간 가상 담당자·기업·사용자와, 발송 테스트로 쌓인 이력을 없앤다.
실데이터(임포트한 투자사·기업)와 팀 기본 문구, 관리자 계정은 건드리지 않는다.

지우는 것을 이름이 아니라 **부트스트랩이 만든 목록**을 기준으로 판단한다.
'샘플' 같은 낱말로 지우면 실기업 이름에 그 글자가 들어갔을 때 같이 날아간다.

발송 이력(send_jobs/send_items/deal_batches)은 전부 테스트 발송이라 기본으로 지운다.
이력이 남아 있으면 '첫 연락 / 재연락' 판정이 어긋나 9월 첫 발송의 인사말이 틀린다.
남기고 싶으면 --keep-history 를 준다.

기본은 미리보기다. 실제로 지우려면 --yes 를 붙인다.

    python scripts/purge_demo.py              # 무엇이 지워지는지만 출력
    python scripts/purge_demo.py --yes        # 실행
    python scripts/purge_demo.py --yes --keep-history
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import delete, or_, select  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.models import (  # noqa: E402
    AgentDevice,
    ContactActivity,
    DealBatch,
    DealBatchCompany,
    IrCompany,
    SendItem,
    SendJob,
    Session as SessionRow,
    User,
    VcContact,
)
from scripts.bootstrap import (  # noqa: E402
    ADMIN_PHONE,
    DEMO_COMPANIES,
    DEMO_CONTACTS,
    DEMO_EXTRA_CONTACTS,
    DEMO_USERS,
)

# 예전 시드 판(版)이 만들고 목록에서 빠진 가상 담당자. 이름으로만 남아 있어서
# 목록에 적어 두지 않으면 영영 지워지지 않는다(전부 가상 투자사명이다).
LEGACY_DEMO_CONTACTS = [("이서준", "다라인베스트먼트"), ("정민아", "자차인베스트")]

DEMO_COMPANY_NAMES = [c["name"] for c in DEMO_COMPANIES]
DEMO_USER_PHONES = [u["phone"] for u in DEMO_USERS]
# (이름, 투자사) 쌍으로 잡아야 동명이인 실담당자를 지우지 않는다.
DEMO_CONTACT_KEYS = (
    [(c["name"], c["firm"]) for c in DEMO_CONTACTS]
    + [(c["name"], c["firm"]) for group in DEMO_EXTRA_CONTACTS.values() for c in group]
    + LEGACY_DEMO_CONTACTS
)


def _demo_contacts(db):
    conds = [(VcContact.name == n) & (VcContact.firm == f) for n, f in DEMO_CONTACT_KEYS]
    return db.execute(select(VcContact).where(or_(*conds))).scalars().all()


def _demo_users(db):
    return db.execute(
        select(User).where(User.phone.in_(DEMO_USER_PHONES))
    ).scalars().all()


def _demo_companies(db):
    return db.execute(
        select(IrCompany).where(IrCompany.name.in_(DEMO_COMPANY_NAMES))
    ).scalars().all()


def purge(db, *, keep_history: bool = False, apply: bool = False) -> dict:
    counts = {}

    contacts = _demo_contacts(db)
    companies = _demo_companies(db)
    users = _demo_users(db)

    counts["가상 담당자"] = [f"{c.name}({c.firm})" for c in contacts]
    counts["가상 기업"] = [c.name for c in companies]
    counts["가상 사용자"] = [f"{u.name}/{u.phone}" for u in users]

    if not keep_history:
        counts["발송 잡"] = db.query(SendJob).count()
        counts["발송 건"] = db.query(SendItem).count()
        counts["회차"] = db.query(DealBatch).count()

    if not apply:
        return counts

    contact_ids = [c.id for c in contacts]
    company_ids = [c.id for c in companies]
    user_ids = [u.id for u in users]
    assert ADMIN_PHONE not in {u.phone for u in users}, "관리자 계정은 지우지 않는다"

    # 발송 이력 — 자식(send_items, deal_batch_companies)부터 지운다.
    if not keep_history:
        db.execute(delete(SendItem))
        db.execute(delete(SendJob))
        db.execute(delete(DealBatchCompany))
        db.execute(delete(DealBatch))
    elif contact_ids:
        # 이력을 남기더라도 지워질 담당자를 가리키는 건은 함께 지운다(고아 방지).
        db.execute(delete(SendItem).where(SendItem.contact_id.in_(contact_ids)))

    if contact_ids:
        db.execute(delete(ContactActivity).where(ContactActivity.contact_id.in_(contact_ids)))
        db.execute(delete(VcContact).where(VcContact.id.in_(contact_ids)))
    if company_ids:
        db.execute(delete(DealBatchCompany).where(DealBatchCompany.company_id.in_(company_ids)))
        db.execute(delete(IrCompany).where(IrCompany.id.in_(company_ids)))
    if user_ids:
        # 가상 사용자에게 딸린 담당자·활동까지 정리해야 화면에 유령이 남지 않는다.
        left = db.execute(
            select(VcContact.id).where(VcContact.user_id.in_(user_ids))
        ).scalars().all()
        if left:
            db.execute(delete(ContactActivity).where(ContactActivity.contact_id.in_(left)))
            db.execute(delete(SendItem).where(SendItem.contact_id.in_(left)))
            db.execute(delete(VcContact).where(VcContact.id.in_(left)))
        db.execute(delete(AgentDevice).where(AgentDevice.user_id.in_(user_ids)))
        db.execute(delete(SessionRow).where(SessionRow.user_id.in_(user_ids)))
        db.execute(delete(SendJob).where(SendJob.user_id.in_(user_ids)))
        db.execute(delete(User).where(User.id.in_(user_ids)))

    db.commit()
    return counts


def main() -> None:
    ap = argparse.ArgumentParser(description="데모·테스트 데이터 삭제")
    ap.add_argument("--yes", action="store_true", help="실제로 지운다 (없으면 미리보기)")
    ap.add_argument("--keep-history", action="store_true", help="발송 이력은 남긴다")
    args = ap.parse_args()

    db = SessionLocal()
    try:
        counts = purge(db, keep_history=args.keep_history, apply=args.yes)
        head = "지웠습니다" if args.yes else "지울 대상 (미리보기)"
        print(f"[purge] {head}")
        for label, value in counts.items():
            if isinstance(value, list):
                print(f"  {label} {len(value)}건 {value if value else ''}")
            else:
                print(f"  {label} {value}건")
        if not args.yes:
            print("\n실제로 지우려면 --yes 를 붙여 다시 실행하세요.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
