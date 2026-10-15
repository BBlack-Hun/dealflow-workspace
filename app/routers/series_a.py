"""IR 기업 현황 메뉴의 `Series A 이상 기업` 탭 — 표 그리기 · 고치기 · 더하기 · 지우기.

**화면 주소는 옆 두 탭과 같다** — `/companies?tab=series-a`. 그 주소를 받는
`companies.companies_page` 가 이리로 넘긴다(`render_page`). 같은 메뉴의 세 탭이
주소 하나를 쓰면 왼쪽 메뉴의 `IR 기업 현황` 이 셋 다에서 켜져 있고, 투자컨설턴트
차단(`deps.CONSULTANT_PATHS`)도 저절로 같다.

## 한 줄이 무엇인가

**딜 소싱으로 받은 딜 한 건**이다(`models.SeriesACompany` — 옆 두 탭의
`ir_companies` 와 왜 따로인지도 거기 있다). 같은 기업이 IR 기업 현황에도
있으면 이름 옆에 `IR 현황` 딱지를 세워 그 탭으로 잇는다 — 이름은
`deal_history._key` 로 맞춘다(기업 이름을 맞추는 규칙은 저장소에 그 하나다).

## 권한은 옆 두 탭과 **같은 판정**을 읽는다

  · 보기 · 고치기 · 더하기 — 로그인한 사람(투자컨설턴트는 미들웨어가 끊는다).
  · 지우기 — `companies.can_delete_company`(관리자 · 팀원). 화면의 [삭제] 를
    보일지도 같은 함수가 정한다. 여기서 역할을 새로 적으면 한쪽만 낡는다.

## 차례 — 수신 일자 최신순

이 표를 여는 물음이 "최근에 무엇이 들어왔나" 라 받은 날이 맨 위다. 날짜로 못
읽는 줄은 맨 아래, 그 안에서는 이름순(`sort_rows`) — 스타트업DB 탭이
`수신일` 로 서는 규칙(`companies.sort_for_tab`)과 같다.
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..clock import today
from ..db import get_db
from ..deps import get_current_user, templates
from ..models import IrCompany, SeriesACompany, User
from ..services import deal_history, series_a_share
from ..services.series_a_import import day_text
from ..ui import base_ctx

router = APIRouter(tags=["series-a"])

#: `/companies?tab=…` 의 값.
TAB = "series-a"

_DATED = re.compile(r"\d{4}-\d{2}-\d{2}")


def received_sort_key(text: Optional[str]) -> str:
    """`수신 일자` 를 세울 값(`data-s-received_at`). 날짜로 적힌 것만, 아니면 빈 값.

    빈 값은 `table_sort.js` 가 방향과 상관없이 늘 끝에 둔다 — 서버의 차례
    (`sort_rows`)와 같은 자리다.
    """
    found = _DATED.search(text or "")
    return found.group(0) if found else ""


def short_series(value: Optional[str]) -> str:
    """`Series A (누적투자금 10억이상, …)` → `Series A`.

    IR 기업 현황의 `투자라운드` 와 **같은 함수**를 쓴다(`companies._short`) —
    두 탭이 같은 값을 다른 모양으로 줄이면 필터에 같은 라운드가 두 벌로 뜬다.
    """
    from .companies import _short

    return _short(value)


def search_text(c: SeriesACompany) -> str:
    """줄에 실어 둘 검색용 글자. 표에 보이는 칸은 다 찾아져야 한다."""
    parts = [c.name, c.received_at, c.deal_type, c.assignee_name, c.shared_by,
             c.source_firm, c.sector_major, c.sector_minor, c.series,
             c.detail, c.deal_pitch]
    return " ".join(filter(None, parts)).lower()


def ir_names(db: Session) -> Dict[str, str]:
    """IR 기업 현황의 `{비교용 이름: 그 탭에 적힌 이름}` — `IR 현황` 딱지의 재료."""
    out: Dict[str, str] = {}
    for (name,) in db.execute(select(IrCompany.name)):
        key = deal_history._key(name)
        if key:
            out.setdefault(key, name)
    return out


def row_dict(c: SeriesACompany, known: Dict[str, str],
             people: Optional[Dict[int, List[str]]] = None) -> dict:
    ir_name = known.get(deal_history._key(c.name), "")
    # **Series A 딜 공유로 이 기업을 받은 심사역** — 딜 제안 관리 › 딜 소싱 제안의
    # [Series A 딜 공유]가 적은 기록(`services/series_a_share.py`). 대기 · 보내는
    # 중 · 보냄만 센다(중단 · 실패한 건은 안 센다).
    shared = (people or {}).get(c.id, [])
    return {
        "id": c.id,
        "name": c.name or "",
        "received_at": c.received_at or "",
        "received_sort": received_sort_key(c.received_at),
        "deal_type": c.deal_type or "",
        "assignee_name": c.assignee_name or "",
        "shared_by": c.shared_by or "",
        "source_firm": c.source_firm or "",
        "sector_major": c.sector_major or "",
        "sector_minor": c.sector_minor or "",
        "series": c.series or "",
        "series_short": short_series(c.series),
        "detail": c.detail or "",
        "deal_pitch": c.deal_pitch or "",
        # IR 기업 현황에 같은 기업이 있으면 그 탭에 적힌 이름 — 딱지가 그 이름으로
        # 그 탭을 연다(`/companies?q=…` 가 검색칸을 채운다).
        "ir_name": ir_name,
        "shared_count": len(shared),
        "shared_names": shared,
        "search": search_text(c),
    }


def sort_rows(rows: List[dict]) -> List[dict]:
    """수신 일자 최신순 · 날짜 없는 줄은 맨 아래 · 같은 날은 이름순(머리말)."""
    dated = [r for r in rows if r["received_sort"]]
    undated = [r for r in rows if not r["received_sort"]]
    dated.sort(key=lambda r: r["name"])
    dated.sort(key=lambda r: r["received_sort"], reverse=True)
    undated.sort(key=lambda r: r["name"])
    return dated + undated


def table_rows(db: Session) -> List[dict]:
    known = ir_names(db)
    people = series_a_share.shared_people(db)
    rows = [row_dict(c, known, people)
            for c in db.execute(select(SeriesACompany)).scalars().all()]
    return sort_rows(rows)


def pick_rows(db: Session) -> List[dict]:
    """딜 제안 관리 › 딜 소싱 제안 › [Series A 딜 공유]의 **기업 고르개** 줄.

    이 탭과 같은 줄 · 같은 차례(수신 일자 최신순 — `sort_rows`)에 둘을 더한다.
      · `pitch` — 기업 덩어리에 실릴 `소개`(`series_a_share.pitch_of`). 고를 때
        무엇이 나갈지 보인다.
      · `sent_to` — 이 기업을 이미 받은 심사역 번호들(대기 · 보낸 것). 화면이
        지금 고른 받는 분과 견주어 `이미 받은 분 N명` 을 세고, 고른 기업을 다
        받은 분을 뺀다(`deals.js`).
      · `own_by` — **이 딜을 공유해 준** 시리즈 A 갈래 심사역 번호들
        (`series_a_share.own_by_company`). 그 분께는 이 기업이 늘 빠진다 — 화면이
        지금 고른 받는 분과 견주어 `본인 공유 N명 제외` 를 센다.
    """
    known = ir_names(db)
    sent = series_a_share.contacts_by_company(db)
    companies = db.execute(select(SeriesACompany)).scalars().all()
    own = series_a_share.own_by_company(db, companies)
    rows = []
    for c in companies:
        data = row_dict(c, known)
        data["pitch"] = series_a_share.pitch_of(c)
        data["sent_to"] = sorted(sent.get(c.id, ()))
        data["own_by"] = own.get(c.id, [])
        rows.append(data)
    return sort_rows(rows)


def count(db: Session) -> int:
    """탭 이름 옆의 수 — 이 표의 줄 수."""
    return int(db.execute(select(func.count()).select_from(SeriesACompany)).scalar_one())


def render_page(request: Request, db: Session, user: User, msg: str = "", q: str = ""):
    """`/companies?tab=series-a` — `companies.companies_page` 가 부른다."""
    from .companies import can_delete_company, tab_counts

    rows = table_rows(db)
    ctx = base_ctx(request, db, user, active="su")
    ctx.update({
        "rows": rows,
        "co_tab": TAB,
        "msg": msg,
        "q": q,
        "counts": tab_counts(db),
        "in_ir": sum(1 for r in rows if r["ir_name"]),
        # [삭제] 를 보일지 — 라우터가 막는 것과 **같은 판정**이다.
        "can_delete": can_delete_company(user),
    })
    return templates.TemplateResponse("companies_series_a.html", ctx)


# --- 고치기 · 더하기 · 지우기 ------------------------------------------------

class SeriesAIn(BaseModel):
    """칸 이름은 **모델 칸 이름 그대로**다 — 표의 `data-field` 가 이 이름으로 보낸다."""

    name: Optional[str] = None
    received_at: Optional[str] = None
    deal_type: Optional[str] = None
    assignee_name: Optional[str] = None
    shared_by: Optional[str] = None
    source_firm: Optional[str] = None
    sector_major: Optional[str] = None
    sector_minor: Optional[str] = None
    series: Optional[str] = None
    detail: Optional[str] = None
    deal_pitch: Optional[str] = None


def _assign(row: SeriesACompany, body: SeriesAIn) -> None:
    for field, value in body.model_dump(exclude_unset=True).items():
        text = (value or "").strip()
        if field == "name":
            # 기업명은 비울 수 없다 — 빈 이름의 줄은 무엇에 대한 줄인지 모른다.
            if text:
                row.name = text
        elif field == "received_at":
            # 시트 가져오기와 **같은 모양**으로 맞춘다(`2026.7.1` → `2026-07-01`).
            # 다르게 넣으면 같은 딜이 다음 가져오기에서 다른 열쇠로 읽힌다.
            row.received_at = day_text(text) or None
        else:
            setattr(row, field, text or None)


def _result(row: SeriesACompany, db: Session) -> dict:
    """PATCH 응답 — 화면이 **브라우저에서 다시 만들 수 없는 값**을 함께 준다.

    `투자라운드` 의 짧은 꼴 · 세울 날짜 · IR 현황 딱지는 서버 규칙에서 나온다.
    화면에 같은 규칙을 또 적으면 두 벌이 되어 한쪽만 고쳐진다.
    """
    data = row_dict(row, ir_names(db))
    return {key: data[key] for key in ("id", "name", "received_at", "received_sort",
                                       "series", "series_short", "ir_name")}


@router.post("/api/series-a-companies")
def create_row(body: SeriesAIn, db: Session = Depends(get_db),
               user: User = Depends(get_current_user)):
    """[기업 추가] — 기업명만 받아 **오늘 받은 딜**로 세운다. 나머지는 표에서 고친다."""
    if not (body.name or "").strip():
        raise HTTPException(status_code=400, detail="기업명을 입력하세요")
    row = SeriesACompany(name=body.name.strip())
    _assign(row, body)
    if not row.received_at:
        row.received_at = today().isoformat()
    db.add(row)
    db.commit()
    return _result(row, db)


@router.patch("/api/series-a-companies/{row_id}")
def update_row(row_id: int, body: SeriesAIn, db: Session = Depends(get_db),
               user: User = Depends(get_current_user)):
    row = db.get(SeriesACompany, row_id)
    if row is None:
        raise HTTPException(status_code=404, detail="줄을 찾을 수 없습니다")
    _assign(row, body)
    db.commit()
    return _result(row, db)


@router.delete("/api/series-a-companies/{row_id}")
def delete_row(row_id: int, db: Session = Depends(get_db),
               user: User = Depends(get_current_user)):
    """지우기 — 옆 두 탭과 **같은 판정**(관리자 · 팀원).

    권한을 먼저 본다 — 없는 번호에 404 를 먼저 주면 번호만 바꿔 가며 어느 줄이
    있는지 알아낼 수 있다(`companies.delete_company` 와 같은 자리 · 같은 이유).
    이 줄을 가리키는 표는 Series A 딜 공유 기록(`series_a_shares`) 하나다 —
    막지 않고 **함께 지운다**(`series_a_share.delete_for_company`). 나간 문구는
    발송 건에 그대로 남고, 화면의 확인창이 몇 명의 기록이 함께 지워지는지 말한다
    (`series_a.js`).
    """
    from .companies import require_delete_company

    require_delete_company(user)
    row = db.get(SeriesACompany, row_id)
    if row is None:
        raise HTTPException(status_code=404, detail="줄을 찾을 수 없습니다")
    series_a_share.delete_for_company(db, row_id)
    db.delete(row)
    db.commit()
    return {"deleted": row_id}
