"""기업별 소개 이력 — 이 기업을 언제 마지막으로 보냈나.

매 회차 같은 기업을 또 보내면 받는 쪽에서는 이쪽이 지난번을 기억 못 한다고 읽는다.
그래서 기업을 고를 때 **최근에 보낸 것**이 눈에 띄어야 한다.

이력은 두 곳에 있다.
- `deal_batch_companies` — 이 시스템으로 보낸 회차
- `contact_activities` — 시트에서 옮겨 온 지난 발송 기록(문구 안에 기업명이 적혀 있다)

시스템으로 보내기 시작한 것이 최근이라, 지금은 두 번째가 대부분이다.
둘을 합쳐 **가장 최근 날짜**를 쓴다.
"""
from __future__ import annotations

import json
from datetime import date
from typing import Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import ContactActivity, DealBatch, DealBatchCompany, IrCompany
from .sheet_import import normalize_company_name

# 이 안에 보낸 기업은 '최근에 보냄'으로 표시한다.
# 월 2회 보내므로 두 회차(약 한 달) 안에 또 나가면 겹쳐 보인다.
RECENT_DAYS = 45


def _key(name: Optional[str]) -> str:
    """비교용 이름. (주)·띄어쓰기 차이로 다른 기업이 되지 않게 맞춘다."""
    return normalize_company_name(name or "").replace(" ", "").lower()


def last_sent_map(db: Session) -> Dict[str, str]:
    """{정규화한 기업명: 마지막으로 소개한 날(YYYY-MM-DD)}."""
    out: Dict[str, str] = {}

    def note(name: Optional[str], when: Optional[str]) -> None:
        key = _key(name)
        if not key or not when:
            return
        day = when[:10]
        if key not in out or day > out[key]:
            out[key] = day

    # 시트에서 옮겨 온 지난 발송 기록
    for act in db.execute(
        select(ContactActivity).where(ContactActivity.kind == "deal_intro")
    ).scalars().all():
        if not act.happened_at:
            continue
        try:
            names = json.loads(act.company_names or "[]")
        except (TypeError, ValueError):
            continue
        for name in names:
            note(name, act.happened_at)

    # 이 시스템으로 보낸 회차
    rows = db.execute(
        select(DealBatchCompany, DealBatch, IrCompany)
        .join(DealBatch, DealBatch.id == DealBatchCompany.batch_id)
        .join(IrCompany, IrCompany.id == DealBatchCompany.company_id)
    ).all()
    for _link, batch, company in rows:
        note(company.name, batch.sent_date)

    return out


def annotate(companies: List[IrCompany], sent_map: Dict[str, str],
             today: Optional[date] = None) -> Dict[int, dict]:
    """{기업 id: {last_sent, days_ago, recent}}."""
    today = today or date.today()
    out: Dict[int, dict] = {}
    for company in companies:
        when = sent_map.get(_key(company.name))
        if not when:
            out[company.id] = {"last_sent": "", "days_ago": None, "recent": False}
            continue
        try:
            days = (today - date.fromisoformat(when)).days
        except ValueError:
            days = None
        out[company.id] = {
            "last_sent": when,
            "days_ago": days,
            "recent": days is not None and 0 <= days <= RECENT_DAYS,
        }
    return out
