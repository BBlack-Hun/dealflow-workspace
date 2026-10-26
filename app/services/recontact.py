"""보류한 2차·후속 미팅 — **90일마다 재접촉 시기**(개선 과제 #68).

팀원 요청: 2차·3차 미팅 뒤 "다음에 다시 검토하겠다" · "이번에는 참여하지 않겠다"
는 투자사에 3개월마다 다시 연락한다. 담당자 결정 — **알림만 띄운다**(아무것도
보내지 않는다) · **거절한 곳은 뺀다**.

## 무엇이 뜨나

같은 투자사(회사명이 비면 같은 심사역) × 같은 기업의 **마지막 완료 미팅**이
2차 · 기타(`pipeline.MEETING_KINDS` 의 `second` · `etc`)이고 결과가 보류(`hold`)인
것. 결과를 거절 · 투자 검토로 고쳤거나 그 뒤 미팅을 마쳤으면 그쪽이 말한다 —
뒤 미팅도 보류면 그 미팅이 이어서 뜬다.

## 언제 뜨나

미팅 날부터 90일마다. 그 뒤 **연락**이 있었으면 그날부터 다시 센다. 연락으로
치는 것(그 투자사 × 그 기업에 대한 것만):

  * 그 뒤 잡은 미팅(취소 제외) — 미팅 날
  * 결과 문의 기록(`Meeting.followup_at` — `/ir` [물어봤음] · [다시 기록])
  * IR 자료 요청 받음 · 전달(`IrRequest.requested_at` · `delivered_at`)
  * 활동 이력의 IR 요청 · 전달(`ContactActivity` `ir_request` · `ir_delivery`)

딜 소개는 치지 않는다 — 기업 여럿을 한 통에 싣는 정기 발송이라 이 기업 이야기를
나눴다는 뜻이 아니다. 자동 결과 문의(A7)도 치지 않는다 — 답을 들으면 사람이
[다시 기록] 으로 적고, 그때 결과 문의 기록이 선다.

스케줄러가 없다 — 화면이 열 때 센다.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from typing import Iterable, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import ContactActivity, IrRequest, Meeting, VcContact
from .deal_history import _key as company_key
from .investor_firms import firm_key
from .last_activity import _activity_day
from .pipeline import MEETING_KINDS, _as_date

#: 며칠마다 다시 연락하나 — 팀원 요청 '3개월마다'.
CYCLE_DAYS = 90
#: 뜨는 미팅 구분 — 2차 · 기타(그 뒤 미팅). 1차는 뺀다.
KINDS = ("second", "etc")
#: 오늘 할 일 줄의 제목 — 매출예상리스트 상자 머리(`forecast.html`)도 같은 말이다.
TITLE = "재접촉 시기 — 보류한 2차·후속 미팅"


def due(db: Session, owners: Optional[Iterable[int]], today: date) -> List[dict]:
    """재접촉 시기가 된 보류 미팅 — 시기가 이른 차례. `owners` 가 None 이면 팀 전체.

    담당은 미팅 주인(`Meeting.user_id`)이다. 연락은 누가 했든 센다 — 다른 팀원이
    그 투자사와 그 기업 이야기를 했으면 이미 연락한 것이다.
    """
    owners = None if owners is None else set(owners)
    meetings = list(db.execute(select(Meeting).where(Meeting.status != "canceled")
                               .order_by(Meeting.id)).scalars())
    held = [m for m in meetings if m.status == "done" and m.kind in KINDS
            and m.outcome == "hold" and (owners is None or m.user_id in owners)]
    if not held:
        return []

    people = {cid: (name or "", firm or "") for cid, name, firm in db.execute(
        select(VcContact.id, VcContact.name, VcContact.firm))}

    def investor(contact_id: int) -> str:
        return firm_key(people.get(contact_id, ("", ""))[1]) or f"#{contact_id}"

    by_investor = defaultdict(list)
    for m in meetings:
        by_investor[investor(m.contact_id)].append(m)
    asks = defaultdict(list)
    for q in db.execute(select(IrRequest)).scalars():
        asks[investor(q.contact_id)].append(q)
    acts = defaultdict(list)
    for a in db.execute(select(ContactActivity).where(
            ContactActivity.kind.in_(("ir_request", "ir_delivery")))).scalars():
        acts[investor(a.contact_id)].append(a)

    out = []
    for m in held:
        key = investor(m.contact_id)

        def same(company_id, name) -> bool:
            # 매출예상리스트와 같은 규칙 — 둘 다 번호가 있으면 번호, 아니면 이름.
            if m.company_id and company_id:
                return company_id == m.company_id
            return company_key(name) == company_key(m.company_name)

        pair = [x for x in by_investor[key] if same(x.company_id, x.company_name)]
        if any(x.status == "done" and (x.scheduled_at, x.id) > (m.scheduled_at, m.id)
               for x in pair):
            continue
        days = [x.scheduled_at for x in pair] + [x.followup_at for x in pair]
        days += [d for q in asks[key] if same(q.company_id, q.company_name)
                 for d in (q.requested_at, q.delivered_at)]
        days += [_activity_day(a) for a in acts[key]
                 if any(same(None, n) for n in a.companies)]
        known = [d for d in map(_as_date, days) if d]
        if not known:
            continue
        last = max(known)
        cycles = max(1, (today - last).days // CYCLE_DAYS)
        when = last + timedelta(days=CYCLE_DAYS * cycles)
        if when > today:
            continue
        name, firm = people.get(m.contact_id, ("", ""))
        out.append({
            "meeting_id": m.id,
            "user_id": m.user_id,
            "contact_id": m.contact_id,
            "name": name or "-",
            "firm": firm,
            "company_name": m.company_name or "",
            "kind_label": MEETING_KINDS.get(m.kind, m.kind),
            "met_on": m.scheduled_at,
            "last_contact": last.isoformat(),
            "days": (today - last).days,
            "due": when.isoformat(),
        })
    out.sort(key=lambda r: (r["due"], r["meeting_id"]))
    return out
