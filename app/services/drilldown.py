"""숫자를 누르면 뜨는 **상세 목록** 하나 (#175 · #177 · #178 · #179 · #182).

대시보드 `반응` 다섯 칸 · `달별 반응` 의 숫자 · 업무 보고의 미팅 카드 넷(잡은 미팅 ·
진행한 미팅 · 결과 물어봄 · 아직 안 물어봄) · 연간 보고의 반응 다섯 칸이 모두 이것을
연다(`/reactions/list` — `routers/drilldown.py`). 표 모양도 하나다.

## 숫자와 목록이 같은 조건이다

줄은 **숫자를 센 그 함수**가 내놓은 것이다 — 반응은 `dashboard.reaction_hits`, 미팅
카드는 `report.meeting_cards`. 여기서 다시 고르지 않는다. 화면 숫자는 묶음 수(반응:
투자사 · 기업 수, 미팅 카드: 건수)이고, 목록의 `NO` 가 묶음마다 하나 선다 — 마지막
`NO` 가 곧 그 숫자다(tests/test_drilldown.py 가 지킨다). 한 투자사가 기업 셋을
요청했으면 NO 하나에 줄이 셋이다.

## 칸은 원천에서 읽는다 — 새로 베껴 두지 않는다

  · 심사역 이름 · 투자사명 · 연락처 · 회사주소 — 투자사 명단 줄(`VcContact`). 회사주소가
    빈 줄은 **같은 투자사의 다른 심사역 줄**에 적힌 주소를 보인다(i241 — 회사주소는 사람이
    아니라 회사 값이다. 여럿이면 가장 많이 적힌 것).
  · 스타트업명 · 기업 담당자 · 그 연락처 · Pre Value · 연도 매출 · 누적투자금액 ·
    투자유치희망금액 — IR 기업 현황 줄(`_finder`: IR 번호 → IR 기업명 → Series A 같은 이름
    → 꼬리표 뗀 이름 → 시트 이력 글에서 기업명 조각). Series A 줄이면 같은 뜻의 칸을
    `company_sync.slot` 으로 찾는다. IR 기업 현황과 Series A · 스타트업 명단의 같은 이름
    칸은 이미 서로 따라 고친다(`company_sync`) — 그래서 어느 메뉴에서 적어도 여기 같은
    값이 보인다.

## 시트 이력 글에서도 기업을 찾는다(i241)

시트에서 옮겨 온 요청 · 미팅 줄의 기업명은 사람이 적은 글 그대로라 `샘플가 전달` ·
`1.샘플나 요청 -> 8/4(화) 전달 완료` 같은 꼴이 많고, IR 쪽 이름에는 `[딜소개 불가/…]` ·
`(영문명)` 같은 꼬리표가 붙어 있다. 글자 그대로만 맞추면 운영 값으로 `IR 요청받은 기업`
539줄 중 220줄(41%)이 기업을 못 찾아 기업 칸이 통째로 비었다. 그래서 못 찾은 줄만
  ① 양쪽 꼬리표(`[…]` · 법인 표기 아닌 `(…)`)를 떼고 맞추고,
  ② 그래도 없으면 글을 `company_names.split`(딜소개 칸을 쪼개는 그 규칙)으로 조각내
     조각 · 조각 안 낱말을 **글자 그대로** 맞춘다 — 부분일치는 하지 않는다.
     맞는 기업이 **딱 하나**일 때만 붙인다(여럿이면 어느 것인지 모르므로 비운다).
스타트업명 칸은 적힌 글 그대로 둔다 — 그 글이 그날의 기록이다.
  · 미팅 일시 · 미팅 결과 — 미팅 기록(`Meeting`). 미팅 줄이 아닌 것(IR 요청 · 시트 이력)은
    같은 심사역 × 기업의 가장 최근 미팅(취소 제외)을 붙인다. 결과 글자는 `OUTCOMES`
    를 읽고, 모르는 값이면 적힌 그대로 둔다 — 결과 칸은 따로 손보는 중이다(#176 · #183).

연도 매출은 지난 두 해 · 올해 · 내년 예상(`revenue_years.shown` · `recent_label` · `forecast`)
— 2026년이면 24~27년(27년은 예상매출). IR 기업 현황 탭과 같은 글자다.
"""
from __future__ import annotations

import re
from collections import Counter
from datetime import date
from typing import Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import IrCompany, Meeting, User, VcContact
from . import (amount, company_names, company_sync, dashboard, investor_firms, pipeline,
               report, revenue_years)
from .dashboard import ReactionHit

#: 기업명 꼬리표 — `[딜소개 불가/…]` · `(딜 클로징 …)` · `(영문명)`. 법인 표기 `(주)` 류는 남긴다
#: (`pipeline._key` 가 뗀다).
_TAG = re.compile(r"\[[^\]]*\]|\((?![주유재사합]\))[^)]*\)")

#: 반응 칸 이름 — 대시보드 패널의 글자 그대로(`REACTION_ROWS` + 달로 못 가르는 하나).
REACTION_LABELS = {**{r["key"]: r["label"] for r in dashboard.REACTION_ROWS},
                   "meeting_call": "미팅완료 리마인드 TEL"}
MEETING_LABELS = dict(report.MEETING_CARDS)

#: 금액으로 읽는 칸 — 단위를 붙여 보인다(`18.3` → `18.3억`, 문구가 쓰는 `amount.phrase`).
_MONEY = {"pre_value", "funding_total", "raise_target", "revenue_recent",
          *revenue_years.FIELDS}


def columns(year: Optional[int] = None, meeting: bool = False) -> List[tuple]:
    """목록 칸 `[(열쇠, 머리글)]` — 화면이 이 차례 그대로 그린다.

    첫 칸(`day`)은 미팅 카드 목록이면 **미팅 날**(`Meeting.scheduled_at` — 카드가 그 날로 달을
    가른다)이라 `미팅 일자`, 반응 목록이면 반응이 일어난 날이라 `날짜` 다(`meeting=`).

    연도 매출은 지난 두 해 · 올해(`revenue_recent`) · 내년 예상(`revenue_years.forecast`) —
    2026년이면 `24년 매출` ~ `27년 예상매출`. 이름은 IR 기업 현황 탭과 같은 글자다.
    """
    ahead = revenue_years.forecast(year)
    years = ([(f, f"{yy}년 매출") for f, yy in revenue_years.shown(year)[-2:]]
             + [("revenue_recent", revenue_years.recent_label(year))]
             + ([ahead] if ahead else []))
    return ([("day", "미팅 일자" if meeting else "날짜"), ("vc_name", "심사역 이름"),
             ("firm", "투자사명"), ("phone", "연락처"), ("address", "회사주소"),
             ("company", "스타트업명"), ("ceo_name", "기업 담당자"),
             ("ceo_phone", "기업 담당자 연락처"), ("pre_value", "Pre Value")]
            + years
            + [("funding_total", "누적투자금액"), ("raise_target", "투자유치희망금액"),
               ("meeting_at", "미팅 일시"), ("outcome", "미팅 결과")])


def _company_value(company, field: str) -> str:
    """기업 줄의 `field`(IR 칸 이름) 값. Series A 줄이면 같은 뜻의 칸에서 읽는다."""
    if company is None:
        return ""
    if not isinstance(company, IrCompany):
        field = company_sync.slot(company, field, {}) if field in company_sync.FIELDS else field
        if not field:
            return ""
    text = str(getattr(company, field, None) or "").strip()
    return (amount.phrase(text) or text) if text and field in _MONEY else text


def _bare(name: Optional[str]) -> str:
    """꼬리표를 뗀 비교용 이름(`_TAG` → `pipeline._key`)."""
    return pipeline._key(_TAG.sub(" ", name or ""))


def _finder(db: Session):
    """`pipeline.company_finder` + 못 찾은 줄만 한 번 더(머리말 `시트 이력 글에서도`)."""
    find = pipeline.company_finder(db)
    bare: Dict[str, object] = {}
    for c in db.execute(select(IrCompany).order_by(IrCompany.id)).scalars():
        bare.setdefault(_bare(c.name), c)
    for row in pipeline.series_a_rows(db).values():
        bare.setdefault(_bare(row.name), row)
    bare.pop("", None)

    def loose(company_id: Optional[int], name: Optional[str]):
        got = find(company_id, name)
        if got is None:
            got = bare.get(_bare(name))
        if got is not None or not (name or "").strip():
            return got
        found: Dict[int, object] = {}
        for piece in company_names.split(name).names:
            hit = bare.get(_bare(piece))
            words = piece.split()
            cands = [hit] if hit is not None else [
                bare.get(_bare(w)) for w in words
                if len(words) > 1 and len(w) >= 2 and not company_names.is_noise_word(w)]
            found.update((id(c), c) for c in cands if c is not None)
        return next(iter(found.values())) if len(found) == 1 else None
    return loose


def _firm_addresses(db: Session) -> Dict[str, str]:
    """투자사(`investor_firms.firm_key`) → 그 회사 심사역 줄에 가장 많이 적힌 회사주소."""
    seen: Dict[str, Counter] = {}
    for firm, address in db.execute(select(VcContact.firm, VcContact.address)):
        key, text = investor_firms.firm_key(firm), (address or "").strip()
        if key and text:
            seen.setdefault(key, Counter())[text] += 1
    return {k: n.most_common(1)[0][0] for k, n in seen.items()}


def _meeting_at(m: Optional[Meeting]) -> str:
    if m is None:
        return ""
    text = " ".join(x for x in ((m.scheduled_at or ""), (m.scheduled_time or "")) if x)
    if m.status != "done":
        text += f" · {pipeline.MEETING_STATUS.get(m.status, m.status)}"
    return text


def lines(db: Session, hits: List[ReactionHit], fields: List[str]) -> tuple:
    """센 줄 → 표의 줄. `(줄들, 묶음 수)` — 묶음 수가 곧 화면의 숫자다."""
    contact_ids = {h.contact_id for h in hits} or {0}
    contacts = {c.id: c for c in db.execute(
        select(VcContact).where(VcContact.id.in_(contact_ids))).scalars()}
    find = _finder(db)
    addresses = _firm_addresses(db)

    def pair(contact_id, company, name):
        return contact_id, company if company is not None else (name or "").strip()

    # 미팅 줄이 아닌 것에 붙일 미팅 — 같은 심사역 × 기업의 가장 최근 것(취소 제외).
    latest: Dict[tuple, Meeting] = {}
    for m in db.execute(select(Meeting).where(Meeting.contact_id.in_(contact_ids),
                                              Meeting.status != "canceled")
                        .order_by(Meeting.scheduled_at)).scalars():
        latest[pair(m.contact_id, find(m.company_id, m.company_name), m.company_name)] = m

    groups: Dict[object, List[ReactionHit]] = {}
    for h in hits:
        groups.setdefault(h.group, []).append(h)
    # 최근 것이 위 — 묶음은 그 안의 가장 최근 날로, 묶음 안도 최근 순.
    order = sorted(groups.values(), key=lambda hs: max(x.day for x in hs), reverse=True)
    out = []
    for no, rows in enumerate(order, 1):
        for i, h in enumerate(sorted(rows, key=lambda x: x.day, reverse=True)):
            contact = contacts.get(h.contact_id)
            company = find(h.company_id, h.company)
            meeting = h.meeting or latest.get(pair(h.contact_id, company, h.company))
            cell = {
                "day": h.day,
                "vc_name": contact.name if contact else "",
                "firm": (contact.firm or "") if contact else "",
                "phone": (contact.phone or "") if contact else "",
                "address": ((contact.address or "").strip()
                            or addresses.get(investor_firms.firm_key(contact.firm), "")
                            if contact else ""),
                "company": h.company or (company.name if company is not None else ""),
                "ceo_name": _company_value(company, "contact_name"),
                "ceo_phone": _company_value(company, "contact_phone"),
                "meeting_at": _meeting_at(meeting),
                "outcome": (pipeline.OUTCOMES.get(meeting.outcome or "", meeting.outcome or "")
                            if meeting is not None else ""),
            }
            for f in fields:
                if f not in cell:
                    cell[f] = _company_value(company, f)
            out.append({"no": no if i == 0 else None,
                        "cells": [cell[f] for f in fields]})
    return out, len(order)


def _period_label(month: str, year: int) -> str:
    if month:
        y, m = (int(x) for x in month.split("-"))
        return f"{y}년 {m}월"
    return f"{year}년" if year else "전체 기간"


def _parse(month: str, year: str) -> tuple:
    """주소의 `month` · `year` → (`2026-09` 또는 빈 글자, 해 또는 0). 못 읽으면 LookupError."""
    try:
        if month:
            y, m = (int(x) for x in month.split("-")[:2])
            date(y, m, 1)
            return f"{y:04d}-{m:02d}", 0
        return "", int(year) if year else 0
    except (ValueError, TypeError):
        raise LookupError("기간을 읽을 수 없습니다")


def build(db: Session, user: User, key: str, month: str = "", year: str = "",
          scope: str = "", member: int = 0) -> dict:
    """`/reactions/list` 한 장. 범위(누구 것)는 업무 보고와 같은 `report.scope_for` 다 —
    관리자만 팀 전체(`scope=team`) · 팀원 한 사람(`member=`)을 본다. 모르는 칸 · 기간이면
    LookupError(화면은 404)."""
    month, year_ = _parse(month, year)
    who, team_wide, _viewing = report.scope_for(db, user, scope, member)
    owner = who or user
    if key in REACTION_LABELS:
        if month and key == "meeting_call":
            # 달로 못 가르는 칸이다(`dashboard._reaction_summary`) — 숫자도 없으니 목록도 없다.
            raise LookupError("이 칸은 달로 가르지 않습니다")
        ids = dashboard.reaction_ids(db, owner, team_wide=team_wide)
        hits = dashboard.reaction_hits(db, ids, month, year_)[key]
        label, unit = REACTION_LABELS[key], ("개" if key == "requested_companies" else "곳")
    elif key in MEETING_LABELS:
        # 연간 카드는 달마다 센 것을 더한 수다(`report.yearly`) — 목록도 달마다 이어 붙인다.
        if not month:
            year_ = year_ or date.today().year
        spans = ([tuple(int(x) for x in month.split("-"))] if month
                 else [(year_, m) for m in range(1, 13)])
        meetings = [m for y, mon in spans
                    for m in report.meeting_cards(report.month_meetings(db, y, mon, who))[key]]
        hits = [ReactionHit(m.id, m.contact_id, (m.company_name or "").strip(),
                            m.company_id, m.scheduled_at or "", m) for m in meetings]
        label, unit = MEETING_LABELS[key], "건"
    else:
        raise LookupError("모르는 칸입니다")

    cols = columns(meeting=key in MEETING_LABELS)
    rows, count = lines(db, hits, [c[0] for c in cols])
    whose = ("팀 전체" if team_wide else
             "내 것" if owner.id == user.id else f"{owner.name} 님")
    return {"title": label, "key": key, "count": count, "unit": unit, "rows": rows,
            "headers": [c[1] for c in cols], "period": _period_label(month, year_),
            "whose": whose, "back": _back(key, month, year_, scope, member)}


def _back(key: str, month: str, year: int, scope: str, member: int) -> str:
    """돌아갈 곳 — 대시보드에서 왔으면 대시보드, 업무 보고에서 왔으면 그 달 · 그 해 보고."""
    tail = (f"&scope={scope}" if scope == "team" else "") + (f"&member={member}" if member else "")
    if key in MEETING_LABELS:
        return f"/report?month={month}{tail}" if month else f"/report?span=year&year={year}{tail}"
    if year:
        return f"/report?span=year&year={year}{tail}"
    return "/"


def href(key: str, *, month: str = "", year: int = 0, scope: str = "",
         member: int = 0) -> str:
    """숫자에 걸 주소(연간 반응 칸이 쓴다). 대시보드 · 월간 카드는 템플릿이 같은 꼴로 짓는다."""
    parts = [f"key={key}"]
    if month:
        parts.append(f"month={month}")
    if year:
        parts.append(f"year={year}")
    if scope == "team":
        parts.append("scope=team")
    if member:
        parts.append(f"member={member}")
    return "/reactions/list?" + "&".join(parts)


def _year_ids(db: Session, user: User, scope: str, member: int) -> List[int]:
    """연간 반응 칸의 모집단 — 이 보고와 같은 범위(`report.scope_for`)."""
    who, team_wide, _viewing = report.scope_for(db, user, scope, member)
    return dashboard.reaction_ids(db, who or user, team_wide=team_wide)


def year_cells(db: Session, user: User, year: int, scope: str = "",
               member: int = 0) -> List[dict]:
    """업무 보고 연간 보기의 반응 다섯 칸(#182) — 대시보드 패널과 같은 칸 · 같은 셈, 그 해치."""
    got = dashboard._reaction_summary(db, _year_ids(db, user, scope, member), year=year)
    return [{"key": k, "label": REACTION_LABELS[k], "value": got[k],
             "href": href(k, year=year, scope=scope, member=member)}
            for k in dashboard.REACTION_KEYS]


def year_results(db: Session, user: User, year: int, scope: str = "",
                 member: int = 0) -> List[dict]:
    """연간 반응 칸 옆 `미팅 결과`(#182 의 `미팅완료 결과` · #183) — 대시보드 칸과 같은 셈을
    그 해치로. 모집단은 위 다섯 칸과 같다(`_year_ids`)."""
    return dashboard.meeting_results(db, _year_ids(db, user, scope, member), year=year)
