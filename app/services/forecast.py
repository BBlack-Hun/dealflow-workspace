"""업무 보고 › `매출예상리스트` — 자동 칸을 원본에서 읽는다(개선 과제 #46).

줄(`RevenueForecast`)은 **사람이 적은 값만** 든다. 비어 있는 자동 칸은 화면 ·
엑셀이 열릴 때마다 여기서 원본을 읽어 채운다 — 옮겨 적으면 두 벌이 된다.

    심사역 · 전화번호       투자사 관리 현황(`vc_contacts`) — 줄 담당자의 명단만,
                           투자사로 세는 줄만(`sheet_owner.is_investor`),
                           회사는 `investor_firms.firm_key` 로 맞춘다
    대표자 · 연락처 ·       이은 IR 기업(`IrCompany.contact_name` · `contact_phone`
    프리밸류 · 희망금액      · `pre_value` · `raise_target`)
    미팅 날짜 셋            줄 담당자의 미팅 — 같은 기업 + 상대 심사역이 같은 회사,
                           취소 제외. 예정일은 아직 안 한(`scheduled`) 것만.
                           가장 이른 날, 더 있으면 `외 N건`

## 심사역은 이 차례로 정한다

1. 미팅(없으면 IR 요청)의 상대가 **한 명**이면 그 사람
2. 아니면 그 회사가 담당자 명단에 **한 명뿐**이면 그 사람
3. 그래도 안 정해지면 정하지 않고 후보 딱지를 띄운다(사람이 [이걸로])

사람이 성함을 적었으면 전화번호는 그 이름의 명단 줄에서 읽는다.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Dict, Iterable, List, Optional

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..models import IrRequest, Meeting, RevenueForecast, User, VcContact
from . import ir_link, sheet_owner
from .deal_history import _key as company_key
from .investor_firms import firm_key

#: 화면 · 엑셀의 칸 차례 — `(칸, 머리글, 자동이면 출처)`. 둘이 같은 목록을 읽는다.
COLUMNS = (
    ("firm", "투자사명", None),
    ("vc_name", "심사역 성함", "투자사 관리 현황 — 이 줄 담당자의 명단"),
    ("vc_phone", "전화번호", "투자사 관리 현황 — 그 심사역의 휴대폰"),
    ("company_name", "기업명", None),
    ("ceo_name", "대표자 성함", "스타트업DB — 대표자명"),
    ("ceo_phone", "연락처", "스타트업DB — 대표자 연락처"),
    ("pre_value", "프리밸류", "스타트업DB — Pre Value"),
    ("raise_target", "희망 투자유치금액", "스타트업DB — 투자유치희망금액"),
    ("post_value", "포스트밸류", None),
    ("ceo_share", "대표이사 지분율", None),
    ("meeting_plan", "투자사 미팅 예정일", "딜 진행 관리 미팅 — 예정(아직 안 한 것)"),
    ("meeting1_done", "1차 미팅 완료일", "딜 진행 관리 미팅 — 1차 · 완료"),
    ("meeting2_done", "2차 미팅 완료일", "딜 진행 관리 미팅 — 2차 · 완료"),
    ("result_note", "결과 상세", None),
)
AUTO = tuple(f for f, _l, src in COLUMNS if src)
FIELDS = tuple(f for f, _l, _s in COLUMNS)

#: IR 기업 칸 → 자동 칸.
_FROM_COMPANY = {"ceo_name": "contact_name", "ceo_phone": "contact_phone",
                 "pre_value": "pre_value", "raise_target": "raise_target"}


def _text(value) -> str:
    return (value or "").strip()


def _company_label(company) -> str:
    """같은 이름의 IR 기업을 가르는 글자 — 이름 · 투자라운드 · 대표자."""
    return " · ".join(p for p in (company.name, company.series, company.contact_name) if p)


def _dates(meetings: List[Meeting]) -> tuple:
    """`(가장 이른 날, 나머지 건수)`."""
    days = sorted(m.scheduled_at for m in meetings if m.scheduled_at)
    return (days[0], len(days) - 1) if days else ("", 0)


class Source:
    """줄 여럿의 원본을 **한 번에** 떠 둔 것 — 줄마다 표를 훑지 않는다."""

    def __init__(self, db: Session, rows: Iterable[RevenueForecast]) -> None:
        rows = list(rows)
        owners = {r.user_id for r in rows} or {0}
        self.idx = ir_link.index(db)
        self.meetings: Dict[int, List[Meeting]] = defaultdict(list)
        for m in db.execute(select(Meeting).where(
                Meeting.user_id.in_(owners), Meeting.status != "canceled")
                .order_by(Meeting.scheduled_at, Meeting.id)).scalars():
            self.meetings[m.user_id].append(m)
        self.requests: Dict[int, List[IrRequest]] = defaultdict(list)
        for q in db.execute(select(IrRequest).where(IrRequest.user_id.in_(owners))
                            .order_by(IrRequest.requested_at, IrRequest.id)).scalars():
            self.requests[q.user_id].append(q)
        wanted = ({m.contact_id for ms in self.meetings.values() for m in ms}
                  | {q.contact_id for qs in self.requests.values() for q in qs}
                  or {0})
        self.contacts: Dict[int, VcContact] = {}
        self.roster: Dict[tuple, List[VcContact]] = defaultdict(list)
        hidden = sheet_owner.hidden_labels(db)
        for c in db.execute(select(VcContact).where(or_(
                VcContact.user_id.in_(owners), VcContact.id.in_(wanted)))
                .order_by(VcContact.id)).scalars():
            self.contacts[c.id] = c
            # 스타트업 명단 줄(대표)을 심사역으로 잡지 않는다.
            if c.user_id in owners and firm_key(c.firm) and sheet_owner.is_investor(c, hidden):
                self.roster[(c.user_id, firm_key(c.firm))].append(c)

    def view(self, row: RevenueForecast) -> dict:
        """이 줄의 칸마다 `{text, value, auto}` + 기업 연결 · 심사역 후보."""
        key = firm_key(row.firm)
        company = self.idx.by_id.get(row.ir_company_id) if row.ir_company_id else None
        name_key = company_key(row.company_name)

        def same(company_id, company_name, contact_id) -> bool:
            if row.ir_company_id and company_id:
                hit = company_id == row.ir_company_id
            else:
                hit = bool(name_key) and company_key(company_name) == name_key
            contact = self.contacts.get(contact_id)
            return hit and bool(key) and contact is not None \
                and firm_key(contact.firm) == key

        meets = [m for m in self.meetings[row.user_id]
                 if same(m.company_id, m.company_name, m.contact_id)]
        asks = [q for q in self.requests[row.user_id]
                if same(q.company_id, q.company_name, q.contact_id)]

        people: List[VcContact] = []
        for contact_id in [m.contact_id for m in meets] or [q.contact_id for q in asks]:
            if self.contacts[contact_id] not in people:
                people.append(self.contacts[contact_id])
        roster = self.roster.get((row.user_id, key), []) if key else []
        person = people[0] if len(people) == 1 else (
            roster[0] if len(roster) == 1 else None)
        candidates = [] if person else (people or roster)
        named = next((c for c in people + roster if c.name == _text(row.vc_name)), None)
        caller = named if _text(row.vc_name) else person

        auto = {"vc_name": (person.name if person else "", 0),
                "vc_phone": (_text(caller.phone) if caller else "", 0),
                "meeting_plan": _dates([m for m in meets if m.status == "scheduled"]),
                "meeting1_done": _dates([m for m in meets if m.status == "done"
                                         and m.kind != "second"]),
                "meeting2_done": _dates([m for m in meets if m.status == "done"
                                         and m.kind == "second"])}
        for field, attr in _FROM_COMPANY.items():
            auto[field] = (_text(getattr(company, attr, "")) if company else "", 0)

        cells = {}
        for field in FIELDS:
            mine = _text(getattr(row, field))
            if mine or field not in auto:
                cells[field] = {"text": mine, "value": mine, "auto": False}
            else:
                value, more = auto[field]
                cells[field] = {"text": value + (f" 외 {more}건" if more else ""),
                                "value": value, "auto": bool(value)}
        return {
            "id": row.id,
            "owner": row.user_id,
            "cells": cells,
            "auto": {f: v for f, (v, _n) in auto.items()},
            "company": ({"id": company.id, "name": company.name or "",
                         "href": ir_link.company_href(company)} if company else None),
            "company_candidates": ([] if company else [
                {"id": c.id, "label": _company_label(c)}
                for c in self.idx.candidates(row.company_name)]),
            "vc_candidates": ([] if _text(row.vc_name) else [
                {"name": c.name, "label": " · ".join(p for p in (c.name, c.title) if p)}
                for c in candidates]),
        }


def views(db: Session, rows: Iterable[RevenueForecast]) -> List[dict]:
    rows = list(rows)
    source = Source(db, rows)
    return [source.view(r) for r in rows]


def company_options(db: Session) -> List[dict]:
    """[줄 추가] · 기업명 칸의 자동완성 보기 — 후보를 찾는 그 IR 기업 목록(`ir_link.index`).

    같은 이름이 여럿이면 `label` 에 투자라운드 · 대표자를 붙여 가른다. 고른 값은 이름
    글자일 뿐이고, 잇는 규칙은 그대로다(`set_company_name` — 하나면 잇고 여럿이면 [이걸로]).
    """
    idx = ir_link.index(db)
    twins = idx.duplicate_keys()
    return [{"value": _text(c.name),
             "label": _company_label(c) if ir_link.compare_key(c.name) in twins else ""}
            for c in sorted(idx.by_id.values(), key=lambda c: (_text(c.name), c.id))
            if _text(c.name)]


def firm_options(db: Session, owners: Iterable[int]) -> Dict[int, List[str]]:
    """투자사명 칸의 자동완성 보기 — 줄 담당자 명단의 회사명(심사역 자동 칸이 읽는 그 명단).

    투자사로 세는 줄만 싣는다(`sheet_owner.investors`) — 스타트업 명단 회사명은 뺀다.
    """
    found: Dict[int, Dict[str, str]] = defaultdict(dict)
    for c in sheet_owner.investors(db, list(db.execute(
            select(VcContact).where(VcContact.user_id.in_(set(owners) or {0}))
            .order_by(VcContact.id)).scalars())):
        if firm_key(c.firm):
            found[c.user_id].setdefault(firm_key(c.firm), _text(c.firm))
    return {user_id: sorted(names.values()) for user_id, names in found.items()}


def rows_for(db: Session, who: Optional[User]) -> List[RevenueForecast]:
    """화면 범위의 줄 — `who` 가 None 이면 팀 전체."""
    query = select(RevenueForecast).order_by(RevenueForecast.id)
    if who is not None:
        query = query.where(RevenueForecast.user_id == who.id)
    return list(db.execute(query).scalars())


def set_company_name(db: Session, row: RevenueForecast, name: str) -> None:
    """기업명을 바꾸면 연결을 풀고 다시 찾는다 — 후보가 하나면 바로 잇는다."""
    if name == _text(row.company_name):
        return
    row.company_name = name or None
    found = ir_link.index(db).candidates(name)
    row.ir_company_id = found[0].id if len(found) == 1 else None


def assign(db: Session, row: RevenueForecast, values: Dict[str, Optional[str]]) -> None:
    """받은 칸을 적는다. 자동 칸은 **원본과 같으면 비운다**(빈칸 = 자동)."""
    for field in FIELDS:
        if field in values and field not in AUTO:
            text = _text(values[field])
            if field == "company_name":
                set_company_name(db, row, text)
            else:
                setattr(row, field, text or None)
    for field in AUTO:
        if field in values:
            text = _text(values[field])
            if text and text == Source(db, [row]).view(row)["auto"][field]:
                text = ""
            setattr(row, field, text or None)
