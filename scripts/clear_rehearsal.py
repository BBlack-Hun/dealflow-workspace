"""리허설로 생긴 발송 기록만 지운다.

리허설은 실제 발송과 같은 길을 탄다 — 그래야 진짜로 나가는지 확인이 된다.
그래서 `send_jobs` · `send_items` · `deal_batches` 에 기록이 남고, 그대로 두면
발송 건수·회차 목록·'이 사람에게 보낸 적 있나'(첫연락/재연락 판단)가 전부
어긋난다.

**DB 를 통째로 되돌리지 않는다.** 리허설 중에 명단이나 문구를 고쳤을 수도
있는데, 스냅샷으로 되돌리면 그 수정까지 사라진다. 발송 기록만 골라 지운다.

    python scripts/clear_rehearsal.py --since 2026-08-26          # 미리보기
    python scripts/clear_rehearsal.py --since 2026-08-26 --apply
    python scripts/clear_rehearsal.py --job 12 --apply            # 특정 회차만
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.models import (DealBatch, DealBatchCompany, SendItem,  # noqa: E402
                        SendJob, SendSequence)


def main() -> int:
    ap = argparse.ArgumentParser(description="리허설 발송 기록 정리")
    ap.add_argument("--since", default="",
                    help="이 날짜(YYYY-MM-DD) 이후에 만든 회차만")
    ap.add_argument("--job", type=int, action="append", default=[],
                    help="지울 회차 번호(여러 번 쓸 수 있음)")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    if not args.since and not args.job:
        ap.error("--since 또는 --job 중 하나는 필요합니다 "
                 "(전부 지우는 실수를 막기 위해서입니다)")

    db = SessionLocal()
    stmt = select(SendJob).order_by(SendJob.id)
    if args.job:
        stmt = stmt.where(SendJob.id.in_(args.job))
    if args.since:
        stmt = stmt.where(SendJob.created_at >= args.since)
    jobs = db.execute(stmt).scalars().all()

    if not jobs:
        print("지울 회차가 없습니다.")
        return 0

    print(f"지울 회차 {len(jobs)}건:")
    total_items = 0
    for job in jobs:
        n = db.query(SendItem).filter_by(job_id=job.id).count()
        total_items += n
        batch = db.get(DealBatch, job.batch_id) if job.batch_id else None
        title = batch.title if batch else "(회차 없음)"
        print(f"   #{job.id:3} {job.kind:14} {title[:26]:28} 건수 {n:3} "
              f"· {(job.created_at or '')[:16]}")
    print(f"\n발송 건 {total_items}건 · 회차 {len(jobs)}건")

    # 후속 예약도 리허설에서 생긴다 — 남겨 두면 있지도 않은 발송의 후속이 뜬다.
    #
    # 잡이 가리키는 회차만 보고 지웠더니, 발송 뒤에 **잡과 무관하게** 그 회차를
    # 가리키게 된 예약이 남아 회차 삭제가 FK 로 막혔다. 회차를 가리키는 것은
    # 전부 함께 지운다.
    batch_ids = [j.batch_id for j in jobs if j.batch_id]
    seqs = db.execute(
        select(SendSequence).where(SendSequence.batch_id.in_(batch_ids))
    ).scalars().all() if batch_ids else []
    if seqs:
        print(f"함께 지울 후속 예약 {len(seqs)}건")

    if not args.apply:
        print("\n미리보기입니다. 지우려면 --apply 를 붙이세요.")
        return 0

    for seq in seqs:
        db.delete(seq)
    for job in jobs:
        db.query(SendItem).filter_by(job_id=job.id).delete()
        db.delete(job)
    # 회차(배치)는 잡을 지운 뒤에 — 잡이 먼저 사라져야 참조가 남지 않는다.
    for bid in set(batch_ids):
        db.query(DealBatchCompany).filter_by(batch_id=bid).delete()
        # 이 회차를 가리키는 예약이 더 있으면 회차를 못 지운다(FK).
        # 위에서 이미 지웠지만, 다른 경로로 생긴 것이 있으면 여기서 끊는다.
        db.query(SendSequence).filter_by(batch_id=bid).update({"batch_id": None})
        db.query(SendJob).filter_by(batch_id=bid).update({"batch_id": None})
        db.flush()
        batch = db.get(DealBatch, bid)
        if batch is not None:
            db.delete(batch)
    db.commit()

    print(f"\n지웠습니다. 남은 회차 {db.query(SendJob).count()}건 · "
          f"발송 건 {db.query(SendItem).count()}건")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
