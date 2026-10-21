"""IR 요청 후 미팅 없음 — 자료를 달라던 투자사가 **아직 만나지 않은** 기업(지금 기준).

## 한 줄 = (투자사 심사역 한 사람, 기업) 한 쌍

**사람**은 (투자사, 이름)으로 본다 — 같은 분이 팀원 명단마다 따로 들어 있어
(`VcContact` 줄이 둘) 줄 번호로 맞추면 한쪽 명단의 미팅이 다른 쪽 요청에 안 붙는다.
시트 임포트가 같은 사람을 맞추는 키도 (이름, 투자사)다(`sheet_import.apply_sheet_a`).
같은 기업이라도 홍 심사역은 만났고 이 심사역은 안 만났으면 이 심사역 줄이 선다.

## 기록은 두 곳에 있다 — 둘 다 읽는다

    요청   `ir_requests`(이 앱에서 적은 것) + `contact_activities` 의 `ir_request`(시트 이력)
    미팅   `meetings`(이 앱) + `contact_activities` 의 미팅 갈래(시트 이력)

앱 표만 읽으면 시트 시절에 만난 쌍이 전부 "미팅 없음" 으로 선다 — 요청을 두 곳에서
읽는 `ir_monthly.monthly_requests` 와 같은 까닭이고, 기업 이름 맞추기도 그 파일의
`_Index`(완전 일치 → 한 곳에만 걸리는 부분 일치)를 그대로 쓴다. 못 맞춘 이름은
지어내지 않고 **이름끼리** 맞춘다. 기업 이름이 없는 시트 요청(`핵심 딜 8개사`)은
쌍을 만들 수 없어 세기만 한다(`skipped`).

미팅으로 치는 것 — 갈래 판정은 `meeting_kind` 한 곳이다.

- 완료: 앱 `done` · 시트 `meeting_done` · 옛 값 `meeting`(안 했다는 말이 없을 때 —
  `meeting_kind.MET` 이 옛 값을 만난 것으로 세는 것과 같다) · IR 요청 글의 `미팅완료`
- 예정: 앱 `scheduled` · 시트 `meeting_set` · IR 요청 글의 `미팅확정` → `미팅 예정` 쪽
- 안 친다: 취소한 미팅(없던 일) · `meeting_request`(청했을 뿐 — 아직 안 만났다)

미팅은 **팀 누가 적었든** 센다. 요청은 내가 받고 미팅은 다른 팀원이 잡았어도 그
투자사는 이미 만난 것이다. 요청의 담당은 앱은 적은 사람, 시트는 그 명단 주인이다.

`보내지 않음`(`dropped`) 요청도 싣는다 — 상태 칸에 그대로 적히고 화면에서 뺄 수 있다.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import ContactActivity, IrCompany, IrRequest, Meeting, User, VcContact
from . import meeting_kind as mk
from . import pipeline
from .ir_monthly import _Index, _key

#: 줄의 요청 상태 — 앱 요청은 `ir_requests.status`, 시트 이력은 전달 여부를 모른다.
LABELS = {"delivered": pipeline.LABEL_DELIVERED, "open": pipeline.LABEL_REQUESTED,
          "dropped": pipeline.REQUEST_STATUS["dropped"], "sheet": "시트 이력"}
#: 한 쌍에 요청이 여럿이면 가장 멀리 간 상태가 그 줄의 상태다.
_RANK = {"sheet": 0, "dropped": 1, "open": 2, "delivered": 3}
SOURCES = {"app": "앱", "sheet": "시트 이력", "both": "앱 · 시트"}

#: IR 요청 칸 글에 붙은 **안 만났다는 말**. `미팅 진행하지 않겠다` 는 `of_content` 가
#: `미팅 진행` 으로 읽어 완료가 된다. 여기서만 거른다 — `meeting_kind._NEGATIVE` 에
#: 넣으면 시트를 읽어 넣을 때 그런 줄이 `meeting`(만난 것으로 세는 옛 값)으로 떨어진다.
_NOT_MET = ("않", "미팅x", "미팅 x")


def _person(contact: VcContact) -> tuple:
    firm, name = _key(contact.firm), re.sub(r"\s+", "", contact.name or "")
    return (firm, name) if firm and name else ("#", contact.id)


def _meeting_of(act: ContactActivity) -> Optional[str]:
    """시트 이력 한 줄 → `done` · `scheduled` · None(미팅 아님)."""
    if act.kind == "ir_request":
        if any(w in (act.content or "").lower() for w in _NOT_MET):
            return None
        kind = mk.of_content(act.content or "")
    elif act.kind == mk.LEGACY:
        kind = None if mk.negated(f"{act.content or ''} {act.raw_text or ''}") else mk.DONE
    else:
        kind = act.kind
    return {mk.DONE: "done", mk.SET: "scheduled"}.get(kind)


def rows(db: Session, user_id: Optional[int], today: date) -> Tuple[List[dict], int]:
    """(완료 미팅이 없는 쌍들 — 경과일 긴 것부터, 기업 이름이 없어 뺀 시트 요청 수).

    `user_id` 가 없으면 팀 전체.
    """
    companies = db.execute(select(IrCompany)).scalars().all()
    index, names = _Index(companies), {c.id: c.name for c in companies}

    def company(company_id: Optional[int], name: Optional[str]) -> tuple:
        """→ (맞춤 키, 보일 이름). 번호 → 이름으로 찾은 번호 → 이름 그대로."""
        cid = company_id if company_id in names else index.find(name)[0]
        return (cid, names[cid]) if cid else (_key(name), (name or "").strip())

    contacts = {c.id: c for c in db.execute(select(VcContact)).scalars()}
    items: List[dict] = []
    done, planned = set(), {}
    skipped = 0

    def met(contact: VcContact, key, state: Optional[str], day: str) -> None:
        pair = (_person(contact), key)
        if state == "done":
            done.add(pair)
        elif state == "scheduled":
            planned[pair] = max(planned.get(pair, ""), day or "")

    for r in db.execute(select(IrRequest)).scalars():
        contact = contacts.get(r.contact_id)
        if contact is not None:
            key, name = company(r.company_id, r.company_name)
            items.append({"contact": contact, "key": key, "name": name,
                          "date": r.requested_at or "", "owner": r.user_id, "src": "app",
                          "state": r.status if r.status in _RANK else "open",
                          "delivered_at": (r.delivered_at or "")[:10]
                          if r.status == "delivered" else ""})

    for m in db.execute(select(Meeting).where(Meeting.status != "canceled")).scalars():
        contact = contacts.get(m.contact_id)
        if contact is not None and (m.company_id or m.company_name):
            met(contact, company(m.company_id, m.company_name)[0],
                "done" if m.status == "done" else "scheduled", m.scheduled_at)

    acts = db.execute(select(ContactActivity).where(
        ContactActivity.kind.in_(("ir_request", mk.DONE, mk.SET, mk.LEGACY)),
        ContactActivity.undone_at.is_(None))).scalars()
    for a in acts:
        contact = contacts.get(a.contact_id)
        if contact is None:
            continue
        day = (a.happened_at or "")[:10] or (a.month or "")
        found = [company(None, n) for n in a.companies]
        state = _meeting_of(a)
        for key, name in found:
            met(contact, key, state, day)
            if a.kind == "ir_request":
                items.append({"contact": contact, "key": key, "name": name, "date": day,
                              "owner": contact.user_id, "src": "sheet", "state": "sheet",
                              "delivered_at": ""})
        if a.kind == "ir_request" and not found and user_id in (None, contact.user_id):
            skipped += 1

    groups: Dict[tuple, List[dict]] = {}
    for it in items:
        pair = (_person(it["contact"]), it["key"])
        if it["key"] and pair not in done and user_id in (None, it["owner"]):
            groups.setdefault(pair, []).append(it)

    owners = dict(db.execute(select(User.id, User.name)).all())
    out = []
    for pair, its in groups.items():
        its.sort(key=lambda i: i["date"])
        last = its[-1]
        contact = last["contact"]
        state = max((i["state"] for i in its), key=_RANK.get)
        delivered = sorted(i["delivered_at"] for i in its if i["delivered_at"])
        since = pipeline._as_date(last["date"])
        srcs = {i["src"] for i in its}
        out.append({
            "contact_name": contact.name,
            "contact_title": contact.title or "",
            "firm": contact.firm or "",
            "company": last["name"],
            # 우리 DB 에 있는 기업이면 IR 기업 현황에서 그 이름으로 찾는다.
            "company_q": last["name"] if isinstance(pair[1], int) else "",
            "first_at": its[0]["date"],
            "last_at": last["date"],
            "days": (today - since).days if since else None,   # 최근 요청에서 오늘까지
            "count": len(its),
            "state": state,
            "status_label": LABELS[state],
            "delivered_at": delivered[-1] if delivered else "",
            "src": "both" if len(srcs) > 1 else srcs.pop(),
            # 딜 진행 관리로 이을 수 있는 사람 — 앱 요청을 적은 사람만(그 화면은 제 것만 보인다).
            "app_owner_ids": {i["owner"] for i in its if i["src"] == "app"},
            "owners": ", ".join(sorted({owners.get(i["owner"], "") for i in its} - {""})),
            "scheduled": pair in planned,
            "scheduled_on": planned.get(pair, ""),
        })
    out.sort(key=lambda r: (-(r["days"] if r["days"] is not None else -1), r["company"]))
    return out, skipped
