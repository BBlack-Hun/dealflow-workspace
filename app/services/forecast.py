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
    성공보수율              이은 IR 기업에 이어 둔(`/ir-link`) 투자컨설턴트 줄의
                           `success_fee` · 스타트업 명단 줄의 `성공보수율 %` —
                           글자 칸이라 `3.5%` · `3프로` 꼴만 읽고, 읽은 값이 **하나로
                           모일 때만** 쓴다(둘이 다르면 사람이 적는다)
    예상 수수료(억)          희망 투자유치금액(구간이면 아래 · `amount.eok`) × 보수율 ÷ 100
                           — 두 칸 모두 사람이 적은 값이 있으면 그 값으로 셈한다

이 표의 매출은 **우리 수수료(성공보수)**다. 합계(`totals`)는 예상 수수료를 더한다.

## 심사역은 이 차례로 정한다

1. 미팅(없으면 IR 요청)의 상대가 **한 명**이면 그 사람
2. 아니면 그 회사가 담당자 명단에 **한 명뿐**이면 그 사람
3. 그래도 안 정해지면 정하지 않고 후보 딱지를 띄운다(사람이 [이걸로])

사람이 성함을 적었으면 전화번호는 그 이름의 명단 줄에서 읽는다.
"""
from __future__ import annotations

import re
from collections import defaultdict
from decimal import Decimal
from typing import Dict, Iterable, List, Optional

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..models import (ConsultingCompany, IrRequest, Meeting, RevenueForecast, User,
                      VcContact)
from . import amount, ir_link, sheet_owner
from .contact_columns import load_notes
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
    # 2판(0111) — 우리 수수료. 미팅 다음 · 결과 앞: 진행을 보고 내리는 예상이라
    # 한 묶음으로 결과 곁에 둔다(값매김 칸 사이에 끼우면 프리 · 포스트가 갈린다).
    ("fee_rate", "성공보수율(%)",
     "이어 둔 투자컨설턴트 계약 · 스타트업 명단의 성공보수율(하나로 모일 때만)"),
    ("expected_fee", "예상 수수료(억)",
     "희망 투자유치금액(구간이면 아래) × 성공보수율 ÷ 100"),
    ("expected_month", "예상 시기", None),
    ("likelihood", "가능성", None),
    ("result_note", "결과 상세", None),
)
AUTO = tuple(f for f, _l, src in COLUMNS if src)
FIELDS = tuple(f for f, _l, _s in COLUMNS)

#: IR 기업 칸 → 자동 칸.
_FROM_COMPANY = {"ceo_name": "contact_name", "ceo_phone": "contact_phone",
                 "pre_value": "pre_value", "raise_target": "raise_target"}

#: 가능성 칸의 보기 — 합계도 이 차례로 나눈다.
CHANCES = ("상", "중", "하")

_RATE_RE = re.compile(r"^(\d+(?:\.\d+)?)\s*(?:%|％|프로|퍼센트)?$")
_MONTH_RE = re.compile(r"^(\d{4})\s*[-./]\s*(\d{1,2})$")


class InputError(ValueError):
    """사람에게 그대로 보일 까닭 — 라우터가 400 으로 돌려준다."""


def rate(value) -> Optional[Decimal]:
    """성공보수율 글자 → % 수. `3.5` · `3.5%` · `3프로` 만 읽는다.

    `3~4%` · `협의` · `계약금 90만` 처럼 수 하나가 아닌 글자는 None — 짐작해 읽으면
    그 짐작이 수수료 합계가 된다. 100 을 넘는 수도 보수율이 아니다.
    """
    hit = _RATE_RE.match(_text(value))
    found = Decimal(hit.group(1)) if hit else None
    return found if found is not None and found <= 100 else None


def number(value: Decimal) -> str:
    """억 · % 수를 화면 글자로 — 만원(0.0001억)까지, 꼬리 0 은 뗀다(`0.35`)."""
    return format(value.quantize(Decimal("0.0001")).normalize(), "f")


def fee_of(target, fee_rate) -> str:
    """예상 수수료(억) = 희망 투자유치금액 × 보수율 ÷ 100. 하나라도 못 읽으면 빈칸."""
    base, pct = amount.eok(target), rate(fee_rate)
    return "" if base is None or pct is None else number(base * pct / 100)


def clean(field: str, text: str) -> str:
    """적는 값을 맞춘다 — 못 받는 값은 `InputError`. 빈 값은 지우기라 그대로 둔다."""
    if not text:
        return text
    if field == "fee_rate":
        if rate(text) is None:
            raise InputError("성공보수율은 % 숫자 하나로 적으세요 — 예: 3.5")
        return number(rate(text))
    if field == "expected_fee" and amount.state(text) == amount.UNREADABLE:
        raise InputError("예상 수수료는 억 단위 숫자로 적으세요 — 예: 0.5 · 5천만원")
    if field == "expected_month":
        hit = _MONTH_RE.match(text)
        if not hit or not 1 <= int(hit.group(2)) <= 12:
            raise InputError("예상 시기는 YYYY-MM 으로 적으세요 — 예: 2027-03")
        return f"{hit.group(1)}-{int(hit.group(2)):02d}"
    if field == "likelihood" and text not in CHANCES:
        raise InputError("가능성은 상 · 중 · 하 중에서 고르세요")
    return text


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
        # 성공보수율 — 이은 IR 기업에 이어 둔 투자컨설턴트 줄 · 스타트업 명단 줄.
        # 두 명단은 서로 다른 기업 무리라(`IrCompany.contract_received` 주석) 둘 다 본다.
        linked = {r.ir_company_id for r in rows if r.ir_company_id} or {0}
        found = list(db.execute(select(ConsultingCompany.ir_company_id,
                                       ConsultingCompany.success_fee)
                                .where(ConsultingCompany.ir_company_id.in_(linked))))
        found += [(company_id, load_notes(notes).get("success_fee"))
                  for company_id, notes in db.execute(
                      select(VcContact.ir_company_id, VcContact.notes)
                      .where(VcContact.ir_company_id.in_(linked)))]
        self.rates: Dict[int, set] = defaultdict(set)
        for company_id, text in found:
            if rate(text) is not None:
                self.rates[company_id].add(rate(text))

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
        rates = self.rates.get(company.id, set()) if company else set()
        auto["fee_rate"] = (number(next(iter(rates))) if len(rates) == 1 else "", 0)
        mine_or_auto = {f: _text(getattr(row, f)) or auto[f][0]
                        for f in ("raise_target", "fee_rate")}
        auto["expected_fee"] = (fee_of(mine_or_auto["raise_target"],
                                       mine_or_auto["fee_rate"]), 0)

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


def totals(views: List[dict]) -> tuple:
    """`([(이름, 억)], 빠진 줄 수)` — 예상 수수료 합계와 가능성별 합계(화면 · 엑셀).

    받은 줄(= 화면 범위)만 더한다. 수수료를 수로 못 읽는 줄(빈칸 · `~`)은 빠지고
    그 수를 센다 — 조용히 빠지지 않게. 구간은 아래를 더한다(`amount.eok`).
    """
    sums = dict.fromkeys(CHANCES + ("",), Decimal(0))
    missing = 0
    for v in views:
        fee = amount.eok(v["cells"]["expected_fee"]["value"])
        if fee is None:
            missing += 1
            continue
        chance = v["cells"]["likelihood"]["value"]
        sums[chance if chance in CHANCES else ""] += fee
    out = [("합계", sum(sums.values(), Decimal(0)))]
    out += [(f"가능성 {c}", sums[c]) for c in CHANCES]
    if sums[""]:
        out.append(("가능성 미정", sums[""]))
    return out, missing


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
    """받은 칸을 적는다. 자동 칸은 **원본과 같으면 비운다**(빈칸 = 자동).

    값부터 모두 맞춰 본다(`clean`) — 하나라도 못 받으면 아무것도 안 적는다.
    """
    values = {f: clean(f, _text(v)) for f, v in values.items() if f in FIELDS}
    for field in FIELDS:
        if field in values and field not in AUTO:
            text = values[field]
            if field == "company_name":
                set_company_name(db, row, text)
            else:
                setattr(row, field, text or None)
    for field in AUTO:
        if field in values:
            text = values[field]
            if text and text == Source(db, [row]).view(row)["auto"][field]:
                text = ""
            setattr(row, field, text or None)
