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

from sqlalchemy import delete, or_, select, update  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.services import sourcing_sync  # noqa: E402
from app.models import (  # noqa: E402
    AgentDevice,
    Automation,
    AutomationSend,
    AutoSendRun,
    SenderRoom,
    ConsultingCompany,
    ContactActivity,
    DealBatch,
    DealBatchCompany,
    DealFollowup,
    IrCompany,
    SendItem,
    SendJob,
    Session as SessionRow,
    User,
    VcContact,
    WeeklyRoutine,
    WeeklyRoutineRun,
    WeeklyTask,
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


def _detach_items(db, item_ids) -> None:
    """지울 발송 건을 가리키는 2단계 자동화 '보냈다' 줄에서 건만 뗀다(줄은 남긴다)."""
    db.execute(update(AutomationSend).where(AutomationSend.item_id.in_(item_ids))
               .values(item_id=None))


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
    #
    # 2단계 자동화의 '보냈다' 줄(`automation_sends`)과 회차 자리(`auto_send_runs`)
    # 는 발송 건 · 회차를 가리킨다(외래키). **줄은 지우지 않고 가리킴만 뗀다** —
    # 줄이 사라지면 그 대상이 보낸 적 없는 것으로 보여 다시 실릴 수 있다. 떼어 낸
    # 줄은 중복 막기가 '보낸 것' 으로 센다(`automation_runner.sent_refs`).
    if not keep_history:
        db.execute(update(AutomationSend).values(item_id=None, job_id=None))
        db.execute(update(AutoSendRun).values(job_id=None))
        db.execute(delete(SendItem))
        db.execute(delete(SendJob))
        db.execute(delete(DealBatchCompany))
        db.execute(delete(DealBatch))
    elif contact_ids:
        # 이력을 남기더라도 지워질 담당자를 가리키는 건은 함께 지운다(고아 방지).
        _detach_items(db, select(SendItem.id).where(SendItem.contact_id.in_(contact_ids)))
        db.execute(delete(SendItem).where(SendItem.contact_id.in_(contact_ids)))

    if contact_ids:
        db.execute(delete(ContactActivity).where(ContactActivity.contact_id.in_(contact_ids)))
        # 보내는 계정 카톡 기준 방 제목 — 담당자 줄을 가리킨다(외래키).
        db.execute(delete(SenderRoom).where(SenderRoom.contact_id.in_(contact_ids)))
        # 리마인드 뒤 `전화 필요` 표시 · 메모 — 담당자 줄을 가리킨다(외래키).
        db.execute(delete(DealFollowup).where(DealFollowup.contact_id.in_(contact_ids)))
        # 딜 소싱 줄이 이 담당자를 가리키면 연결만 끊는다(줄은 남는다) — 한꺼번에
        # 지우기는 flush 를 지나지 않아 앱이 대신 끊어 주지 못한다.
        sourcing_sync.detach(db, contact_ids)
        db.execute(delete(VcContact).where(VcContact.id.in_(contact_ids)))
    if company_ids:
        db.execute(delete(DealBatchCompany).where(DealBatchCompany.company_id.in_(company_ids)))
        # 사람이 이어 둔 연결(`services/ir_link.py`)은 **끊기만** 한다 — 줄은
        # 남는다. 안 끊으면 외래키가 기업 줄을 못 지우게 막는다.
        for model in (VcContact, ConsultingCompany):
            db.execute(update(model).where(model.ir_company_id.in_(company_ids))
                       .values(ir_company_id=None))
        db.execute(delete(IrCompany).where(IrCompany.id.in_(company_ids)))
    if user_ids:
        # 가상 사용자에게 딸린 담당자·활동까지 정리해야 화면에 유령이 남지 않는다.
        left = db.execute(
            select(VcContact.id).where(VcContact.user_id.in_(user_ids))
        ).scalars().all()
        if left:
            db.execute(delete(ContactActivity).where(ContactActivity.contact_id.in_(left)))
            _detach_items(db, select(SendItem.id).where(SendItem.contact_id.in_(left)))
            db.execute(delete(SendItem).where(SendItem.contact_id.in_(left)))
            db.execute(delete(SenderRoom).where(SenderRoom.contact_id.in_(left)))
            db.execute(delete(DealFollowup).where(DealFollowup.contact_id.in_(left)))
            sourcing_sync.detach(db, left)
            db.execute(delete(VcContact).where(VcContact.id.in_(left)))
        db.execute(delete(AgentDevice).where(AgentDevice.user_id.in_(user_ids)))
        db.execute(delete(SessionRow).where(SessionRow.user_id.in_(user_ids)))
        # 2단계 자동화 — 가상 계정이 보내는 계정이었거나(`automations.user_id`) 그
        # 계정 카톡의 방 제목(`sender_rooms`) · 그 계정 회차를 가리키는 줄.
        db.execute(update(Automation).where(Automation.user_id.in_(user_ids))
                   .values(user_id=None))
        db.execute(delete(SenderRoom).where(SenderRoom.sender_user_id.in_(user_ids)))
        # 가상 계정이 남의 줄에 `전화 필요` 를 켜거나 메모했으면 **누가** 칸만 뗀다
        # (표시 · 메모는 그 담당자 줄의 것이라 남는다).
        db.execute(update(DealFollowup).where(DealFollowup.call_by.in_(user_ids))
                   .values(call_by=None))
        db.execute(update(DealFollowup).where(DealFollowup.memo_by.in_(user_ids))
                   .values(memo_by=None))
        jobs = select(SendJob.id).where(SendJob.user_id.in_(user_ids))
        _detach_items(db, select(SendItem.id).where(SendItem.job_id.in_(jobs)))
        db.execute(update(AutomationSend).where(AutomationSend.job_id.in_(jobs))
                   .values(job_id=None))
        db.execute(update(AutoSendRun).where(AutoSendRun.job_id.in_(jobs))
                   .values(job_id=None))
        runs = select(AutoSendRun.id).where(AutoSendRun.user_id.in_(user_ids))
        db.execute(update(AutomationSend).where(AutomationSend.run_id.in_(runs))
                   .values(run_id=None))
        db.execute(delete(AutoSendRun).where(AutoSendRun.user_id.in_(user_ids)))
        db.execute(delete(SendItem).where(SendItem.job_id.in_(jobs)))
        db.execute(delete(SendJob).where(SendJob.user_id.in_(user_ids)))
        # 주간 업무 — **만든 표시 → 줄 → 규칙** 차례다. 셋 다 `users.id` 를
        # 가리키고, 앞의 둘은 규칙까지 가리킨다(SQLite 는 `foreign_keys=ON`).
        #
        # 여기 없으면 가상 계정이 `/todo` 를 한 번이라도 연 순간부터 이 스크립트가
        # `FOREIGN KEY constraint failed` 로 죽는다 — 화면을 열기만 해도 그 주
        # 목록이 채워지기 때문에(`services/weekly.py` 의 `fill_week`), 데모를
        # 써 본 DB 는 거의 다 그 상태가 된다.
        db.execute(delete(WeeklyRoutineRun).where(WeeklyRoutineRun.user_id.in_(user_ids)))
        db.execute(delete(WeeklyTask).where(WeeklyTask.user_id.in_(user_ids)))
        db.execute(delete(WeeklyRoutine).where(WeeklyRoutine.user_id.in_(user_ids)))
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
