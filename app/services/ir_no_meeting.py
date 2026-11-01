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
`_Index`(완전 일치 → 한 곳에만 걸리는 부분 일치)를 그대로 쓴다. 앱 요청은 못 맞춘
이름도 **이름끼리** 맞춘다(사람이 적은 기업명이다). 시트 이력은 IR 기업 현황에서 찾은
기업만 싣는다 — 그 칸에는 `미팅 요청 완료 -> 검토 중` 같은 메모가 기업 이름 자리에
섞여 들어와 있어, 못 맞춘 조각을 기업으로 세우면 메모가 줄로 선다. 못 맞춘 조각과
기업 이름 없이 개수만 적힌 줄(`핵심 딜 8개사`)은 세기만 한다(`skipped` —
`ir_monthly` 가 못 맞춘 요청을 세는 것과 같다).

미팅으로 치는 것 — 갈래 판정은 `meeting_kind` 한 곳이다.

- 완료: 앱 `done` · 시트 `meeting_done` · 옛 값 `meeting`(안 했다는 말이 없을 때 —
  `meeting_kind.MET` 이 옛 값을 만난 것으로 세는 것과 같다) · IR 요청 글의 `미팅완료`
  · 시트 `meeting_set` 과 IR 요청 글의 `미팅확정`(시트 시절엔 확정 뒤 완료로 고쳐 적지
  않았다 — 만난 것으로 본다. 날짜가 오늘보다 뒤면 예정)
- 예정: 앱 `scheduled` 중 날짜가 오늘이거나 뒤인 것(날짜 미기재 포함) → `미팅 예정` 쪽
- 안 친다: 취소한 미팅(없던 일) · `meeting_request`(청했을 뿐 — 아직 안 만났다) ·
  앱 `scheduled` 인데 날짜가 지났고 완료 처리가 안 된 것(비고 `예정일 지남`)

같은 투자사의 다른 심사역이 그 기업을 만났어도 줄은 사람마다 선다 — 비고에 적는다.

미팅은 **팀 누가 적었든** 센다. 요청은 내가 받고 미팅은 다른 팀원이 잡았어도 그
투자사는 이미 만난 것이다. 요청의 담당은 앱은 적은 사람, 시트는 그 명단 주인이다.

`보내지 않음`(`dropped`) 요청도 싣는다 — 상태 칸에 그대로 적히고, 화면은 기본으로 뺀다(칩으로 본다).
`드랍`(`lost`)도 같다. 드랍 뒤에 새 요청 · 전달이 오면 그 줄은 다시 산다(아래 `_state`).

## 명단 기록 — 세 번째 출처(#116 2차)

명단 월별 `IR 요청` 칸에 손으로 적은 `…전달`(`memo_delivered.entries`)도 줄로 싣는다 —
읽기만 하고(출처 `명단 기록`), 앱 전달 기록과 겹치면 안 싣는다(`memo_delivered.overlaps` —
업무 보고 수와 같은 판정). 기업은 시트 이력처럼 IR 기업 현황에서 찾은 것만이다.

## 드랍 의심 — 전달 뒤 `DROP_SUSPECT_DAYS`일 동안 미팅이 없다(#116 2차 B안)

자료를 보낸 뒤 피드백 없이 끝난 건을 사람이 확정하게 띄운다. 조건은 넷 다:

- 줄 상태가 전달 완료(앱 `delivered` 또는 명단 기록의 전달)
- 같은 **투자사** · 같은 기업에 완료 · 예정 미팅이 없다 — 다른 심사역이 만났거나 잡았어도,
  예정일이 지난 채 완료 처리 안 된 미팅이 있어도 뺀다(미팅 기록을 고칠 일이지 드랍이 아니다)
- 마지막 전달일에서 오늘까지 `DROP_SUSPECT_DAYS`일 이상
- 다만 그 뒤 **미팅 요청을 보냈으면**(`pipeline.meeting_ask_state` — 앱 발송 · 손 표시)
  `어레인지중` 이고, 시계는 미팅 요청 보낸 날부터 다시 센다

날짜를 못 읽은 건(날짜 없는 명단 기록)은 띄우지 않는다 — 근거 없는 경보가 제일 나쁘다.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (ContactActivity, IrCompany, IrRequest, Meeting, SeriesACompany,
                      User, VcContact)
from . import meeting_kind as mk
from . import pipeline
from .ir_monthly import _Index, _key

#: 줄의 요청 상태 — 앱 요청은 `ir_requests.status`, 시트 이력은 전달 여부를 모른다.
LABELS = {"delivered": pipeline.LABEL_DELIVERED, "open": pipeline.LABEL_REQUESTED,
          "dropped": pipeline.REQUEST_STATUS["dropped"], "sheet": "시트 이력",
          "lost": pipeline.REQUEST_STATUS["lost"]}
#: 한 쌍에 요청이 여럿이면 가장 멀리 간 상태가 그 줄의 상태다(`lost` 는 `_state` 가 따로 본다).
_RANK = {"sheet": 0, "dropped": 1, "lost": 1, "open": 2, "delivered": 3}
SOURCES = {"app": "앱", "sheet": "시트 이력", "memo": "명단 기록"}
#: 전달 뒤 미팅 요청을 보낸 줄의 상태 글자 — '어레인지중' = 앱의 `미팅 요청 보냄`.
LABEL_ARRANGING = "어레인지중"
#: 전달(또는 미팅 요청) 뒤 이 날 수 동안 미팅이 없으면 드랍 의심(11/01 결정).
DROP_SUSPECT_DAYS = 21

#: IR 요청 칸 글에 붙은 **안 만났다는 말**. `미팅 진행하지 않겠다` 는 `of_content` 가
#: `미팅 진행` 으로 읽어 완료가 된다. 여기서만 거른다 — `meeting_kind._NEGATIVE` 에
#: 넣으면 시트를 읽어 넣을 때 그런 줄이 `meeting`(만난 것으로 세는 옛 값)으로 떨어진다.
_NOT_MET = ("않", "미팅x", "미팅 x")
NOTE_OVERDUE = "예정일 지남(완료 처리 안 됨)"
NOTE_COLLEAGUE = "같은 투자사 다른 심사역 미팅 있음"


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


def _when(item: dict) -> str:
    return item["delivered_at"] or item["date"]


def _state(its: List[dict]) -> str:
    """쌍의 상태 — 드랍이 **가장 늦은 일**이면 드랍, 아니면 남은 것 중 가장 멀리 간 상태.

    드랍 뒤에 새 요청 · 전달이 오면 다시 산 것이다 — 그래서 드랍만은 순위로 고르지 않는다.
    """
    live = [i for i in its if i["state"] != "lost"]
    lost = max((_when(i) for i in its if i["state"] == "lost"), default="")
    if lost and all(_when(i) <= lost for i in live):
        return "lost"
    return max((i["state"] for i in live), key=_RANK.get)


def rows(db: Session, user_id: Optional[int], today: date) -> Tuple[List[dict], int]:
    """(완료 미팅이 없는 쌍들 — 경과일 긴 것부터, 기업을 못 찾아 뺀 시트 요청 수).

    `user_id` 가 없으면 팀 전체.
    """
    companies = db.execute(select(IrCompany)).scalars().all()
    index = _Index(companies, db.execute(select(SeriesACompany.name)).scalars())
    names = {c.id: c.name for c in companies}

    def company(company_id: Optional[int], name: Optional[str]) -> tuple:
        """→ (맞춤 키, 보일 이름). 번호 → 이름으로 찾은 번호 → 이름 그대로."""
        cid = company_id if company_id in names else index.find(name)[0]
        return (cid, names[cid]) if cid else (_key(name), (name or "").strip())

    contacts = {c.id: c for c in db.execute(select(VcContact)).scalars()}
    items: List[dict] = []
    done, planned, overdue = set(), {}, set()
    skipped = 0
    now = today.isoformat()

    def met(contact: VcContact, key, state: Optional[str], day: str) -> None:
        pair = (_person(contact), key)
        if state == "done":
            done.add(pair)
        elif state == "scheduled":
            planned[pair] = max(planned.get(pair, ""), day or "")
        elif state == "overdue":
            overdue.add(pair)

    requests = db.execute(select(IrRequest)).scalars().all()
    for r in requests:
        contact = contacts.get(r.contact_id)
        if contact is not None:
            key, name = company(r.company_id, r.company_name)
            items.append({"contact": contact, "key": key, "name": name,
                          "date": r.requested_at or "", "owner": r.user_id, "src": "app",
                          "state": r.status if r.status in _RANK else "open", "id": r.id,
                          "delivered_at": (r.delivered_at or "")[:10]
                          if r.status in pipeline.SENT_STATUSES else ""})
    asks = pipeline.meeting_ask_state(db, requests, today=today)

    # 명단 칸의 `…전달` — 앱 전달 기록과 겹치면 뺀다(업무 보고 수와 같은 판정).
    from . import memo_delivered    # 그 모듈이 이 모듈의 `_person` 을 읽는다 — 순환을 피한다
    app_sent = memo_delivered.app_delivered(db)
    for e in memo_delivered.entries(db, today):
        contact = contacts.get(e["contact_id"])
        cid = index.find(e["company"])[0] if e["company"] else None
        if contact is None or not cid or memo_delivered.overlaps(e, app_sent):
            continue
        day = e["date"] or e["month"]
        items.append({"contact": contact, "key": cid, "name": names[cid], "date": day,
                      "owner": e["owner"], "src": "memo", "state": "delivered",
                      "delivered_at": e["date"],
                      "memo": {"contact_id": e["contact_id"], "month": e["month"],
                               "company": e["company"]}})

    for m in db.execute(select(Meeting).where(Meeting.status != "canceled")).scalars():
        contact = contacts.get(m.contact_id)
        if contact is not None and (m.company_id or m.company_name):
            day = (m.scheduled_at or "")[:10]
            met(contact, company(m.company_id, m.company_name)[0],
                "done" if m.status == "done" else
                "overdue" if day and day < now else "scheduled", day)

    acts = db.execute(select(ContactActivity).where(
        ContactActivity.kind.in_(("ir_request", mk.DONE, mk.SET, mk.LEGACY)),
        ContactActivity.undone_at.is_(None))).scalars()
    for a in acts:
        contact = contacts.get(a.contact_id)
        if contact is None:
            continue
        day = (a.happened_at or "")[:10] or (a.month or "")
        ids = [index.find(n)[0] for n in a.companies]
        found = [(cid, names[cid]) for cid in ids if cid]
        state = _meeting_of(a)
        if state == "scheduled" and day <= now:     # 시트의 지난 `미팅확정` = 만났다
            state = "done"
        for key, name in found:
            met(contact, key, state, day)
            if a.kind == "ir_request":
                items.append({"contact": contact, "key": key, "name": name, "date": day,
                              "owner": contact.user_id, "src": "sheet", "state": "sheet",
                              "delivered_at": ""})
        if a.kind == "ir_request" and user_id in (None, contact.user_id):
            skipped += (len(ids) - len(found)) if ids else 1

    groups: Dict[tuple, List[dict]] = {}
    for it in items:
        pair = (_person(it["contact"]), it["key"])
        if it["key"] and pair not in done and user_id in (None, it["owner"]):
            groups.setdefault(pair, []).append(it)

    # 같은 투자사(사람 키의 앞자리)에서 그 기업을 만난 사람이 있나 — 이 줄의 사람은 안 만났다.
    firm_met = {(p[0], key) for p, key in done if p[0] != "#"}
    # 드랍 의심은 투자사 단위 — 누가 만났든 · 잡았든(예정일 지남 포함) 미팅이 있으면 아니다.
    firm_seen = firm_met | {(p[0], key) for p, key in (*planned, *overdue) if p[0] != "#"}
    owners = dict(db.execute(select(User.id, User.name)).all())
    out = []
    for pair, its in groups.items():
        its.sort(key=lambda i: i["date"])
        last = its[-1]
        contact = last["contact"]
        state = _state(its)
        delivered = sorted(i["delivered_at"] for i in its
                           if i["delivered_at"] and (state == "lost") == (i["state"] == "lost"))
        since = pipeline._as_date(last["date"])
        srcs = {i["src"] for i in its}
        # 어레인지중 — 마지막 전달 뒤에 미팅 요청이 나갔다(판정은 `meeting_ask_state` 한 곳).
        asked = max((asks[i["contact"].id]["asked_at"] for i in its
                     if i["src"] == "app" and i["contact"].id in asks), default="")
        asked = asked if state == "delivered" and delivered and asked >= delivered[-1] else ""
        clock = pipeline._as_date(asked or (delivered[-1] if delivered else ""))
        quiet = (today - clock).days if clock and state == "delivered" else None
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
            "status_label": LABEL_ARRANGING if asked else LABELS[state],
            "asked_at": asked,
            # 마지막 전달(미팅 요청을 보냈으면 그날)에서 오늘까지 — 드랍 의심의 시계.
            "quiet_days": quiet,
            "suspect": bool(quiet is not None and quiet >= DROP_SUSPECT_DAYS
                            and pair not in planned and pair not in overdue
                            and (pair[0][0], pair[1]) not in firm_seen),
            # [드랍 확정] · [드랍 취소] 가 고칠 앱 요청 — 명단 기록은 [앱 기록으로] 옮긴다.
            "sent_ids": [i["id"] for i in its if i["src"] == "app" and i["state"] == "delivered"],
            "lost_ids": [i["id"] for i in its if i["src"] == "app" and i["state"] == "lost"],
            "memos": [i["memo"] for i in its if i["src"] == "memo"],
            "delivered_at": delivered[-1] if delivered else "",
            "src": "both" if len(srcs) > 1 else next(iter(srcs)),
            "srcs": srcs,
            "src_label": " · ".join(v for k, v in SOURCES.items() if k in srcs),
            # 딜 진행 관리로 이을 수 있는 사람 — 앱 요청을 적은 사람만(그 화면은 제 것만 보인다).
            "app_owner_ids": {i["owner"] for i in its if i["src"] == "app"},
            "owners": ", ".join(sorted({owners.get(i["owner"], "") for i in its} - {""})),
            "scheduled": pair in planned,
            "scheduled_on": planned.get(pair, ""),
            "note": " · ".join(
                ([NOTE_OVERDUE] if pair in overdue and pair not in planned else [])
                + ([NOTE_COLLEAGUE] if (pair[0][0], pair[1]) in firm_met else [])),
        })
    out.sort(key=lambda r: (-(r["days"] if r["days"] is not None else -1), r["company"]))
    return out, skipped
