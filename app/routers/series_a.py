"""IR 기업 현황 메뉴의 `Series A 이상 딜 소싱` 탭 — 표 그리기 · 고치기 · 더하기 · 지우기.

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
  · 딜소개 문구 올리기(파일로 `딜소개 문구` 칸 채우기) — 관리자만
    (`can_upload_pitch` — 사용자 결정). 단추와 길이 같은 함수를 지난다.

## 차례 — 수신 일자 최신순

이 표를 여는 물음이 "최근에 무엇이 들어왔나" 라 받은 날이 맨 위다. 날짜로 못
읽는 줄은 맨 아래, 그 안에서는 이름순(`sort_rows`) — 스타트업DB 탭이
`수신일` 로 서는 규칙(`companies.sort_for_tab`)과 같다.
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional, Set

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..clock import today
from ..db import get_db
from ..deps import NotAdmin, get_current_user, templates
from ..models import IrCompany, SeriesACompany, SourcingContact, User
from ..services import custom_columns, deal_history, series_a_share, sourcing_sync
from ..services.series_a_import import day_text
from ..ui import base_ctx

router = APIRouter(tags=["series-a"])

#: `/companies?tab=…` 의 값.
TAB = "series-a"

_DATED = re.compile(r"\d{4}-\d{2}-\d{2}")

#: 사람이 탭에서 적기만 하는 칸(#24 · 0112) — 대표자 · 매출 · 금액. 시트에 없고
#: 서버가 다듬지도 않는다(적은 그대로, 금액 단위는 억). 응답 · 검색이 이 한 목록을
#: 읽는다 — 화면은 `companies_series_a.html` 에 손으로 적었다(다른 칸과 같다).
TYPED = ("ceo_name", "ceo_phone", "ceo_email",
         "revenue_2024", "revenue_2025", "revenue_2026", "revenue_2027",
         "funding_total", "raise_target", "pre_value")


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
             c.detail, c.deal_pitch, c.ir_file_name] + [getattr(c, f) for f in TYPED]
    return " ".join(filter(None, parts)).lower()


def ir_names(db: Session) -> Dict[str, tuple]:
    """IR 기업 현황의 `{비교용 이름: (그 탭에 적힌 이름, IR 자료 파일 이름)}` —
    `IR 현황` 딱지와 그 줄의 `IR 자료` 칸(IR 쪽 자료를 보여만 준다)의 재료."""
    out: Dict[str, tuple] = {}
    for name, file_name in db.execute(select(IrCompany.name, IrCompany.ir_file_name)):
        key = deal_history._key(name)
        if key:
            out.setdefault(key, (name, (file_name or "").strip()))
    return out


def row_dict(c: SeriesACompany, known: Dict[str, tuple],
             people: Optional[Dict[int, Set[int]]] = None,
             sharer: Optional[dict] = None) -> dict:
    ir_name, ir_file = known.get(deal_history._key(c.name), ("", ""))
    # **Series A 딜 공유로 이 기업을 받은 심사역** — 딜 제안 관리 › 딜 소싱 제안의
    # [Series A 딜 공유]가 적은 기록(`services/series_a_share.py`). 대기 · 보내는
    # 중 · 보냄만 센다(중단 · 실패한 건은 안 센다).
    #
    # **수만** 싣는다. 표의 `공유한 심사역` 칸은 뺐고(#24 — 옆 `공유 심사역` 과
    # 같은 뜻으로 읽혔다), 이 수를 읽는 곳은 [삭제] 확인창 하나다(`series_a.js` —
    # "공유 기록도 함께 지워진다"). 누구인지(이름 · 회사)는 그 칸의 풍선말에만
    # 쓰였으므로 더 읽지 않는다.
    shared = (people or {}).get(c.id, ())
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
        **{f: getattr(c, f) or "" for f in TYPED},
        # IR 기업 현황에 같은 기업이 있으면 그 탭에 적힌 이름 — 딱지가 그 이름으로
        # 그 탭을 연다(`/companies?q=…` 가 검색칸을 채운다).
        "ir_name": ir_name,
        # `IR 자료` 칸 — 이 줄에 적은 파일 이름. IR 기업 현황에 같은 기업이 있으면
        # 이 칸 대신 **IR 쪽 파일 이름**(`ir_file`)을 보여만 준다 — [자료 보내기]는 그
        # 이름의 요청을 IR 줄로 잇고 IR 쪽 자료를 붙인다(`_check_ir_file` 이 여기 적기를 막는다).
        "ir_file_name": c.ir_file_name or "",
        "ir_file": ir_file,
        "shared_count": len(shared),
        # `공유 심사역` 칸 아래 — 확정한 분 · 이름이 같은 후보(`series_a_share.
        # sharer_views`). 화면(`series_a.js`)이 이 값으로 [이 분으로 확정]/[해제]를 그린다.
        "sharer": sharer or {"confirmed": None, "candidates": []},
        # `공유 심사역` 오른쪽 `휴대폰` 칸(#25) — [이 분으로 확정]한 분의 딜 소싱 줄 번호.
        # 확정한 분이 없으면 빈칸이고 고칠 수 없다(`_set_sharer_phone`).
        "sharer_phone": ((sharer or {}).get("confirmed") or {}).get("phone", ""),
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
    people = series_a_share.contacts_by_company(db)
    companies = db.execute(select(SeriesACompany)).scalars().all()
    sharers = series_a_share.sharer_views(db, companies)
    rows = [row_dict(c, known, people, sharers.get(c.id)) for c in companies]
    return sort_rows(rows)


def pick_rows(db: Session) -> List[dict]:
    """딜 제안 관리 › 딜 소싱 제안 › [Series A 딜 공유]의 **기업 고르개** 줄.

    이 탭과 같은 줄 · 같은 차례(수신 일자 최신순 — `sort_rows`)에 `pitch`(기업
    덩어리에 실릴 `소개` — `series_a_share.pitch_of`)를 더한다. 고를 때 무엇이
    나갈지 보인다.

    **누가 이미 받았나 · 누가 공유해 준 딜인가는 여기서 세지 않는다.** /deals 는
    딜 소개 · 후속 문구에도 열리는 화면이라, 열 때마다 기록 전체와 딜 소싱 명단
    전체를 견주면 쓰지도 않을 셈에 화면이 느려진다. 화면이 [Series A 딜 공유]를
    고를 때 · 창으로 돌아올 때 `share_state` 를 읽는다(`deals.js`). 화면에 이 값이
    없거나 낡아도 보내는 것은 틀리지 않는다 — 미리보기와 발송이 서버에서 다시
    센다(`series_a_share.plan`). IR 기업 현황 이름(`IR 현황` 딱지)도 고르개는 안
    쓰므로 읽지 않는다.
    """
    rows = []
    for c in db.execute(select(SeriesACompany)).scalars().all():
        data = row_dict(c, {})
        data["pitch"] = series_a_share.pitch_of(c)
        rows.append(data)
    return sort_rows(rows)


@router.get("/api/series-a-share/state")
def share_state(db: Session = Depends(get_db),
                user: User = Depends(get_current_user)):
    """고르개 카드마다 — `sent_to`(이 기업을 이미 받은 심사역 번호들: 대기 · 보낸 것)와
    `own_by`(**이 딜을 공유해 준** 시리즈 A 갈래 심사역 번호들).

    화면이 지금 고른 받는 분과 견주어 `이미 받은 분 N명` · `본인 공유 N명 제외` 를
    세고, 보낼 기업이 안 남는 분을 받는 사람에서 뺀다(`deals.js`). 고를 때 · 창으로
    돌아올 때 읽는다(`pick_rows` 머리말).

    `autofill` — [후보 자동 채우기]가 체크할 기업 번호 · 차례(`series_a_share.autofill`).
    덜 나간 순을 이 자리의 `sent` 로 세므로 고르개 줄(`pick_rows`)이 아니라 여기 싣는다.
    """
    sent = series_a_share.contacts_by_company(db)
    companies = db.execute(select(SeriesACompany)).scalars().all()
    own = series_a_share.own_by_company(db, companies)
    rows = sort_rows([row_dict(c, {}) for c in companies])
    return {"companies": [{"id": c.id, "sent_to": sorted(sent.get(c.id, ())),
                           "own_by": own.get(c.id, [])} for c in companies],
            "autofill": series_a_share.autofill(rows, sent)}


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
        # [딜소개 문구 올리기] 를 보일지 — 관리자만(`can_upload_pitch`).
        "can_upload_pitch": can_upload_pitch(user),
    })
    # 관리자가 붙인 추가 칸 — 옆 두 탭과 **같은 칸**(`custom_columns.TARGETS`).
    ctx.update(custom_columns.view(db, "companies", "series_a_companies"))
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
    # 직접 적는 칸(`TYPED`) — 적은 그대로 저장한다(`_assign` 의 마지막 갈래).
    ceo_name: Optional[str] = None
    ceo_phone: Optional[str] = None
    ceo_email: Optional[str] = None
    revenue_2024: Optional[str] = None
    revenue_2025: Optional[str] = None
    revenue_2026: Optional[str] = None
    revenue_2027: Optional[str] = None
    funding_total: Optional[str] = None
    raise_target: Optional[str] = None
    pre_value: Optional[str] = None
    # 보낼 IR 자료 **파일 이름**(0118) — IR 기업 현황의 `IR 자료 파일명` 과 같은 규칙.
    ir_file_name: Optional[str] = None
    # `휴대폰`(#25) — 이 줄의 칸이 아니라 확정한 공유 심사역의 딜 소싱 줄에 적는다.
    sharer_phone: Optional[str] = None


#: 확정한 공유 심사역이 없는데 `휴대폰` 을 적으려 할 때.
NO_SHARER_PHONE = ("공유 심사역을 [이 분으로 확정]한 뒤에 적을 수 있습니다 — "
                   "번호는 그 분의 딜 소싱 줄에 저장됩니다")


def _set_sharer_phone(db: Session, row: SeriesACompany, raw: Optional[str]) -> None:
    """`휴대폰` 칸 — 확정한 분의 **딜 소싱 줄**에 적는다(#25). 이어진 투자사 관리 현황
    줄은 flush 때 따라 고쳐진다(`sourcing_sync.before_flush`). 번호가 바뀌어 투자사 줄과
    새로 맞게 되면 잇는 것도 딜 소싱 표에서 고칠 때와 같다(`routers/sourcing.update_row`)."""
    person = (db.get(SourcingContact, row.shared_by_contact_id)
              if row.shared_by_contact_id else None)
    if person is None:
        raise HTTPException(status_code=400, detail=NO_SHARER_PHONE)
    key_before = sourcing_sync.link_key(person)
    person.phone = (raw or "").strip() or None
    if sourcing_sync.link_key(person) != key_before:
        sourcing_sync.auto_link(db, person)


#: IR 기업 현황에도 있는 기업의 `IR 자료` 를 여기 적으려 할 때.
IR_TWIN_FILE = ("IR 기업 현황에도 있는 기업입니다 — IR 자료는 IR 기업 현황에서 등록하세요"
                "(딜 진행 관리의 [자료 보내기]는 그쪽 자료를 붙입니다)")


def _check_ir_file(db: Session, row: SeriesACompany, body: SeriesAIn) -> None:
    """`IR 자료` 칸 — IR 기업 현황의 같은 칸과 **같은 판정**으로 거른다.

    파일 이름 하나만 받는다(`companies._looks_like_a_file_name` — 발송기가 거부하는
    경로 · 주소를 넣는 자리에서 먼저 막는다). IR 기업 현황에 같은 이름(이름을 고치는
    중이면 고친 이름)의 기업이 있으면 받지 않는다 — 그 이름의 요청은 IR 줄로 이어져
    IR 쪽 자료가 나가므로, 여기 적으면 안 쓰이는 두 번째 벌이 된다. 비우기는 늘 된다.
    """
    from .companies import _looks_like_a_file_name

    text = (body.ir_file_name or "").strip()
    if not text:
        return
    if not _looks_like_a_file_name(text):
        raise HTTPException(status_code=400,
                            detail="자료 폴더 안의 파일 이름만 적습니다 — 폴더 경로·주소는 받지 않습니다")
    name = (body.name or "").strip() or row.name
    if deal_history._key(name) in ir_names(db):
        raise HTTPException(status_code=400, detail=IR_TWIN_FILE)


def _assign(row: SeriesACompany, body: SeriesAIn) -> None:
    for field, value in body.model_dump(exclude_unset=True, exclude={"sharer_phone"}).items():
        text = (value or "").strip()
        if field == "shared_by" and text != (row.shared_by or "").strip():
            # 공유 심사역을 **다른 글자로** 고쳤다 — 확정해 둔 분을 푼다. 옛 분이
            # 확정된 채 남으면 새로 적은 분께 자기 딜이 나간다. 같은 글자로 다시
            # 저장한 것은 그대로 둔다.
            row.shared_by_contact_id = None
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
    data = row_dict(row, ir_names(db), sharer=series_a_share.sharer_view(db, row))
    # 고친 칸은 **서버가 저장한 값**으로 다시 그리고(`series_a.js`), 검색 글자도
    # 갈아 끼운다 — 표에서 고치는 칸은 전부 돌려준다.
    return {key: data[key] for key in (
        "id", "name", "received_at", "deal_type", "assignee_name", "shared_by",
        "source_firm", "sector_major", "sector_minor", "series", "detail",
        "deal_pitch", *TYPED, "ir_file_name", "received_sort", "series_short", "ir_name",
        "ir_file", "search", "sharer", "sharer_phone")}


@router.post("/api/series-a-companies")
def create_row(body: SeriesAIn, db: Session = Depends(get_db),
               user: User = Depends(get_current_user)):
    """[기업 추가] — 기업명만 받아 **오늘 받은 딜**로 세운다. 나머지는 표에서 고친다."""
    if not (body.name or "").strip():
        raise HTTPException(status_code=400, detail="기업명을 입력하세요")
    row = SeriesACompany(name=body.name.strip())
    if "ir_file_name" in body.model_fields_set:
        _check_ir_file(db, row, body)
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
    if "ir_file_name" in body.model_fields_set:
        _check_ir_file(db, row, body)
    _assign(row, body)
    if "sharer_phone" in body.model_fields_set:
        _set_sharer_phone(db, row, body.sharer_phone)
    db.commit()
    return _result(row, db)


class SharerIn(BaseModel):
    """확정할 딜 소싱 줄 번호 — 비우면(`null`) 확정을 푼다."""

    contact_id: Optional[int] = None


@router.put("/api/series-a-companies/{row_id}/sharer")
def set_sharer(row_id: int, body: SharerIn, db: Session = Depends(get_db),
               user: User = Depends(get_current_user)):
    """`공유 심사역` 을 딜 소싱 명단의 **그 분 줄로 확정**한다 — [이 분으로 확정] · [해제].

    확정한 줄은 Series A 딜 공유가 이름 · 회사로 짐작하지 않고 그 분께만 이 딜을
    뺀다(`series_a_share.is_own`). 받는 갈래(`series_a_share.BUCKET`)의 분만 고를 수
    있다 — 다른 갈래 분은 이 글을 받지 않으니 확정해도 뺄 사람이 없다. 권한은 칸
    고치기와 같다(로그인한 사람 — 이 탭은 팀 공용).
    """
    row = db.get(SeriesACompany, row_id)
    if row is None:
        raise HTTPException(status_code=404, detail="줄을 찾을 수 없습니다")
    if body.contact_id is not None:
        person = db.get(SourcingContact, body.contact_id)
        if person is None or not series_a_share.is_share_bucket(person.bucket):
            raise HTTPException(
                status_code=400,
                detail=f"'{series_a_share.BUCKET}' 갈래의 딜 소싱 심사역만 확정할 수 있습니다")
    row.shared_by_contact_id = body.contact_id
    db.commit()
    return {"id": row.id, "sharer": series_a_share.sharer_view(db, row)}


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


# --- 딜소개 문구 올리기 (관리자) ---------------------------------------------
#
# 시트 파일로 `딜소개 문구` 칸만 채운다(`services/series_a_pitch_upload.py` 머리말).
# 미리보기(`dry_run`) → 같은 파일을 다시 보내 반영 — `data_io.import_contacts` 와
# 같은 짜임이고, 화면도 그 업로드 창을 따른다(`series_a_pitch.js`).

def can_upload_pitch(user: User) -> bool:
    """[딜소개 문구 올리기] 를 보여도 되는가 — **관리자만**(사용자 결정 2026-10-16).

    화면(`render_page`)과 라우터(`upload_pitch`)가 **이 함수 하나**를 지난다 —
    단추가 보이는 사람은 반드시 올릴 수 있고, 안 보이는 사람은 주소를 직접 쳐도
    막힌다. 관리자 판정 자체는 `companies._is_admin`(→ `deps.admin_only`)이다.
    """
    from .companies import _is_admin

    return _is_admin(user)


def _bad(detail: str, tabs: List[str]) -> JSONResponse:
    """400 — 무엇이 문제인지와 **파일의 탭들**(`sheets`). 탭이 여럿인 워크북에서
    이 시트로 보이는 탭을 못 고르면, 화면이 그 목록으로 고르개를 세운다."""
    if tabs:
        detail += " · 이 파일의 탭: " + ", ".join(tabs)
    return JSONResponse({"detail": detail, "sheets": tabs}, status_code=400)


@router.post("/api/import/series-a-pitch")
def upload_pitch(
    file: UploadFile = File(...),
    sheet: str = Form(""),
    # [이미 적힌 문구도 덮어쓰기]. 꺼 두면 **빈 칸만** 채운다.
    overwrite: bool = Form(False),
    dry_run: bool = Form(True),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """[딜소개 문구 올리기]. 기본은 미리보기 — 반영하려면 `dry_run=false`.

    주소는 `/api/import/…` 다 — 올리는 길을 한 갈래에 둔다(`data_io` 머리말: 표의
    `/{row_id}` 길과 부딪히지 않게).

    **내려받은 파일 막기(`spreadsheet.is_export_file`)는 걸지 않는다.** 그 막이는
    내보낸 투자사 표를 되올리면 활동이 부풀기 때문인데, 이 표는 내려받는 길이
    없고 다른 표를 내보낸 파일은 머리글(`SIGNATURE`)에서 걸린다.
    """
    from ..services import series_a_import as sai
    from ..services import series_a_pitch_upload as pitch
    from ..services import spreadsheet as sp
    from ..services.import_diff import shorten
    from .data_io import DIFF_ROWS

    if not can_upload_pitch(user):
        raise NotAdmin()
    data = file.file.read()
    filename = file.filename or ""
    # 크기 상한 · 형식을 **먼저** 보고(`read_tabs`) 워크북은 한 번만 연다 — 탭 고르개에
    # 실을 탭 이름도 여기서 읽는다. 탭 이름을 따로 읽으면 상한을 보기 전에 한 번 더
    # 열었다(PR #311 리뷰).
    try:
        book = sp.read_tabs(filename, data)
    except sp.SpreadsheetError as exc:   # 큰 파일 · 빈 파일 · 형식 · 깨진 파일
        return _bad(str(exc), [])
    tabs = [title for title, _rows in book] if filename.lower().endswith(
        sp.EXCEL_SUFFIXES) else []
    try:
        used, rows = sai.pick_upload(filename, book, sheet or None)
        parsed = sai.parse(rows)
    except ValueError as exc:     # 탭 못 고름 · 머리글 없음
        return _bad(str(exc), tabs)
    # 줄을 맞추는 열쇠(기업명 · 수신 일자 · 공유 심사역 · **회사**)와 바꿀 칸이 다
    # 있어야 한다. `회사` 가 없으면 열쇠가 하나도 안 맞아 문구가 통째로 '못 맞춘 줄' 로
    # 빠진다 — 조용히 끝내지 않고 막는다(PR #311 리뷰). 열쇠를 줄여 맞추는 길은 고르지
    # 않았다: 같은 기업 · 같은 날 · 같은 심사역이 두 회사에서 오면 엉뚱한 줄을 덮는다.
    missing = [sai.HEADERS[a][0] for a in (*pitch.IDENT, pitch.FIELD)
               if sai.HEADERS[a][0] in parsed.missing]
    if missing:
        return _bad(" · ".join(f"`{m}`" for m in missing) + " 칸이 없습니다 — 머리글 줄에 "
                    "줄을 맞추는 `기업명` · `수신 일자` · `공유 심사역` · `회사`(시트 "
                    "가져오기와 같은 열쇠)와 `딜 소개 문구` 칸이 있어야 합니다", tabs)

    p = pitch.plan(db, parsed.records, overwrite=overwrite)
    if dry_run:
        db.rollback()   # 미리보기가 DB 를 건드리고 끝나면 안 된다
    else:
        pitch.apply(p)
        db.commit()

    # 반영 뒤 화면 위에 뜨는 한 줄(`series_a_pitch.js` 가 `msg` 로 넘긴다).
    head = (f"바뀔 줄 {len(p.changes)}" if dry_run
            else f"딜 소개 문구 {len(p.changes)}줄을 바꿨습니다")
    summary = (f"{head}(빈 칸 채움 {p.filled} · 덮어씀 {p.overwritten})"
               f" · 못 맞춘 줄 {len(p.unmatched)} · 애매해서 건너뛴 줄 {len(p.ambiguous)}")
    return {
        "dry_run": dry_run,
        "overwrite": overwrite,
        "sheets": tabs,
        "sheet_used": used,
        "file_rows": p.records,
        "no_name": parsed.no_name,
        "matched": p.matched,
        "unmatched": len(p.unmatched),
        # 못 맞춘 줄 중 **문구가 적힌 줄** — 이 문구들이 안 들어간다.
        "unmatched_with_pitch": sum(1 for v in p.unmatched if v.get(pitch.FIELD)),
        "ambiguous": len(p.ambiguous),
        "duplicates": p.duplicates,
        "changed": len(p.changes),
        "filled": p.filled,
        "overwritten": p.overwritten,
        "same": p.same,
        "kept": p.kept,
        "blank": p.blank,
        # 목록은 `DIFF_ROWS` 줄까지만 싣는다 — 수는 위에 다 있다(`data_io` 와 같은 판단).
        # 문구는 줄여 싣는다(`import_diff.shorten` — 투자사 업로드 미리보기와 같은 자).
        "changes": [dict(pitch.ident(c.row), id=c.row.id, how=c.how,
                         before=shorten(c.before), after=shorten(c.after))
                    for c in p.changes[:DIFF_ROWS]],
        "unmatched_rows": [dict(pitch.ident(v), has_pitch=bool(v.get(pitch.FIELD)))
                           for v in p.unmatched[:DIFF_ROWS]],
        "ambiguous_rows": [dict(pitch.ident(v), has_pitch=bool(v.get(pitch.FIELD)))
                           for v in p.ambiguous[:DIFF_ROWS]],
        "summary": summary,
    }
