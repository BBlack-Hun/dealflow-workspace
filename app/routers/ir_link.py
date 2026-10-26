"""IR 기업 연결 화면 — `/ir-link`.

스타트업 명단 줄 · 투자컨설턴트 줄을 IR 기업 현황의 기업에 **사람이** 잇는다.
무엇을 왜 그렇게 하는지는 `services/ir_link.py` 머리말에 있다. 여기는 **누가
어느 줄에 손댈 수 있는가**와 화면에 무엇을 실을지만 정한다.

## 누구의 줄이 서는가 — 판정을 새로 짓지 않는다

  · 스타트업 명단  그 화면이 보여 주는 판정 그대로다(`sheet_owner.managed`
                   — 관리자는 팀 전체, 팀원은 자기 줄). 하나를 고칠 때도 그
                   화면의 수정창과 같은 문(`routers/contacts._owned`)을 지난다.
  · 투자컨설턴트   그 화면이 **고칠 수 있다**고 그리는 줄만(`consulting.scope`
                   + `may_edit_row`). 하나를 고칠 때도 같은 문
                   (`consulting.owned`)이다. 볼 수만 있는 남의 줄은 여기 안
                   선다 — 서 있는데 [연결] 이 404 를 내는 화면이 되지 않게.

투자컨설턴트(역할)는 이 화면에 못 들어온다(`deps.CONSULTANT_PATHS` 밖이다) —
IR 기업 현황 자체가 그 사람에게 닫혀 있다.

## 잇기 — 새 줄은 저절로, 있던 줄은 확인 화면을 거쳐

새로 생기는 줄은 이름이 정확히 하나 맞으면 저절로 이어진다(10/22 결정 2 —
`services/company_sync._auto_link`). 이미 있던 줄은 [후보가 하나인 줄 일괄
연결] 이 **확인 화면을 한 번 거쳐** 잇는다(`GET /ir-link/bulk`) — 몇 줄이 어느
기업에 붙는지를 먼저 보이고, 누른 뒤에도 서버가 그 짝이 **아직 그대로인지**를
줄마다 다시 본다(그 사이 누가 잇거나 IR 기업이 늘어 후보가 둘이 되었으면 건너뛴다).
이름으로 이은 줄은 `자동 연결` 로 보이고 [연결 해제] 로 푼다.

## 값 다름

잇는 순간에는 빈칸만 채우므로(`company_sync` 머리말), 양쪽에 다른 값이 있던 칸은
그대로 남는다. `값 다름` 칩이 그 줄을 모으고, 칸마다 [IR 값으로] · [이 줄 값으로]
를 골라 맞춘다(`POST /ir-link/resolve`). 고른 뒤로는 이어진 줄 모두가 같아진다.
연락처 · 이메일은 [둘 다 남기기] 도 선다 — `IR 값, 이 줄 값` 으로 잇는다
(10/23 결정, `company_sync.keep_both`).

## 수정 로그

잇고 푼 것은 줄마다 남는다 — 자기 줄이어도(`edit_log.ALWAYS_FIELDS`).
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_current_user, may_view_consulting, templates
from ..models import ConsultingCompany, IrCompany, User, VcContact
from ..services import company_sync, contact_columns, ir_link, sheet_owner
from ..ui import base_ctx
from . import consulting as consulting_router
from .companies import CONTRACT_LABELS, contract_key
from .companies import tab_counts as company_tab_counts
from .contacts import _owned as owned_contact

router = APIRouter(tags=["ir-link"])

HREF = "/ir-link"
#: 좌측 메뉴에서 불이 들어올 자리. 이 화면은 메뉴에 따로 서지 않는다 —
#: IR 기업 현황의 탭 하나다(`_company_tabs.html`). 스타트업 툴바에서도 닿는다.
ACTIVE = "su"
TITLE = "IR 기업 연결"

TAB_LABELS = {ir_link.STARTUP: "스타트업 명단", ir_link.CONSULTING: "투자컨설턴트"}

#: 거르기 칩. 빈 값이 전체다.
SHOW_LINKED = "linked"
SHOW_CANDIDATE = "cand"     # 안 이었고 후보가 있다(하나든 여럿이든)
SHOW_NONE = "none"          # 안 이었고 후보도 없다
SHOW_DIFF = "diff"          # 이었는데 IR 과 값이 다른 칸이 있다(`company_sync.differences`)
SHOWS = ("", SHOW_LINKED, SHOW_CANDIDATE, SHOW_NONE, SHOW_DIFF)


# ── 누구의 줄인가 ───────────────────────────────────────────────────────────

def tabs_for(user: User) -> List[str]:
    """이 사람에게 서는 탭. 투자컨설턴트 탭은 그 화면을 볼 수 있는 사람만."""
    out = [ir_link.STARTUP]
    if may_view_consulting(user):
        out.append(ir_link.CONSULTING)
    return out


def startup_rows(db: Session, user: User,
                 include_hidden: bool = False) -> List[VcContact]:
    """이 사람이 손댈 수 있는 **스타트업 명단 줄.**

    `team_wide=True` 를 넘겨도 판정은 `managed` 안에서 다시 본다
    (`deps.may_manage_team_contacts` — 관리자만 팀 전체다). 어느 명단이
    스타트업 화면에 사는지는 배치가 정한다(`sheet_owner.page_labels`).

    감춘 줄은 기본으로 뺀다 — 그 명단 화면도 기본으로 안 보여 준다. 줄 하나를
    펴 놓고 잇는 자리(`?row=`)에서는 감춘 줄도 받는다(수정창에서 넘어온다).
    """
    labels = sheet_owner.page_labels(db, contact_columns.PAGE_STARTUP)
    rows = [c for c in sheet_owner.managed(db, user, team_wide=True,
                                           include_hidden=True)
            if sheet_owner.on_page(c, labels)]
    if not include_hidden:
        rows = [c for c in rows if not c.is_hidden]
    rows.sort(key=lambda c: (ir_link.row_name(c), c.id))
    return rows


def consulting_rows(db: Session, user: User) -> List[ConsultingCompany]:
    """이 사람이 **고칠 수 있는** 투자컨설턴트 줄."""
    if not may_view_consulting(user):
        return []
    stmt = select(ConsultingCompany).order_by(
        ConsultingCompany.sheet, ConsultingCompany.position, ConsultingCompany.id)
    rows = db.execute(consulting_router.scope(stmt, ConsultingCompany, user)
                      ).scalars().all()
    grants = consulting_router.grant_owner_ids(db, user)
    return [r for r in rows
            if consulting_router.may_edit_row(db, user, r.user_id, grants=grants)]


def rows_for(db: Session, user: User, kind: str,
             include_hidden: bool = False) -> list:
    if kind == ir_link.CONSULTING:
        return consulting_rows(db, user)
    return startup_rows(db, user, include_hidden=include_hidden)


def editable_row(db: Session, user: User, kind: str, row_id: int):
    """고칠 수 있는 줄 하나 — 아니면 **없는 것으로** 답한다(404).

    판정은 그 줄이 사는 화면의 문 그대로다(머리말).
    """
    if kind == ir_link.CONSULTING:
        consulting_router.require_access(user)
        return consulting_router.owned(db, ConsultingCompany, row_id, user, "기업")
    contact = owned_contact(db, row_id, user)
    labels = sheet_owner.page_labels(db, contact_columns.PAGE_STARTUP)
    if not sheet_owner.on_page(contact, labels):
        # 투자사 명단 줄은 IR 기업에 잇는 줄이 아니다 — 거기 `firm` 은 투자사다.
        raise HTTPException(status_code=404, detail="스타트업 명단 줄을 찾을 수 없습니다")
    return contact


# ── 화면에 싣는 모양 ────────────────────────────────────────────────────────

def company_view(company: IrCompany, counts: Dict[int, int],
                 dup_ids: set) -> dict:
    """IR 기업 하나 — 고를 때 견줄 칸(수신일 · 담당자 · 계약 상태)."""
    return {
        "id": company.id,
        "name": company.name or "",
        "received_at": company.received_at or "",
        "assignee": company.assignee_name or "",
        # 계약을 부르는 말은 IR 기업 현황과 **한 곳**이다(`CONTRACT_LABELS`).
        "contract": CONTRACT_LABELS.get(contract_key(company.contract_status), "미계약"),
        # 이 기업에 이미 이어 둔 줄 수(스타트업 + 투자컨설턴트).
        "links": counts.get(company.id, 0),
        # 비교용 이름이 같은 IR 기업이 또 있다 — 고르기 전에 알아야 한다.
        "dup": company.id in dup_ids,
        "href": ir_link.company_href(company),
    }


def _where(db: Session, row, owners: Dict[int, str]) -> Tuple[str, str]:
    """(어느 명단·탭, 담당) — 줄을 알아보는 데 쓰는 두 칸."""
    if isinstance(row, ConsultingCompany):
        where = row.sheet or ""
    else:
        where = ", ".join(sheet_owner.labels_of(row.source_sheet))
    owner = owners.get(row.user_id or 0, "")
    return where, owner


def row_view(db: Session, idx: ir_link.Index, row, counts: Dict[int, int],
             dup_ids: set, owners: Dict[int, str],
             diffs: Optional[Dict[int, list]] = None) -> dict:
    st = ir_link.state(idx, row)
    linked = ir_link.linked_company(idx, row)
    found = [] if linked else idx.candidates(ir_link.row_name(row))
    where, owner = _where(db, row, owners)
    return {
        "id": row.id,
        "name": ir_link.row_name(row),
        "where": where,
        "owner": owner,
        "hidden": bool(getattr(row, "is_hidden", 0)),
        "state": st,
        "state_label": ir_link.STATE_LABELS[st],
        "linked": company_view(linked, counts, dup_ids) if linked else None,
        # 이름으로 이어졌는가(일괄 연결 · 새 줄 저절로) — `자동 연결` 표시.
        "auto": bool(linked and row.ir_link_auto),
        "diffs": (diffs or {}).get(row.id, []) if linked else [],
        "candidates": [company_view(c, counts, dup_ids) for c in found],
    }


def _owners(db: Session) -> Dict[int, str]:
    return {u.id: u.name for u in db.execute(select(User)).scalars().all()}


def tally(views: List[dict]) -> dict:
    """머리의 숫자 — **감춘 줄은 안 센다**(목록에도 안 선다)."""
    shown = [v for v in views if not v["hidden"]]
    by = {s: sum(1 for v in shown if v["state"] == s)
          for s in (ir_link.LINKED, ir_link.SINGLE, ir_link.MULTI, ir_link.NONE)}
    return {
        "total": len(shown),
        "linked": by[ir_link.LINKED],
        "single": by[ir_link.SINGLE],
        "multi": by[ir_link.MULTI],
        "candidate": by[ir_link.SINGLE] + by[ir_link.MULTI],
        "none": by[ir_link.NONE],
        "diff": sum(1 for v in shown if v["diffs"]),
    }


def _keep(view: dict, show: str) -> bool:
    if show == SHOW_LINKED:
        return view["state"] == ir_link.LINKED
    if show == SHOW_CANDIDATE:
        return view["state"] in (ir_link.SINGLE, ir_link.MULTI)
    if show == SHOW_NONE:
        return view["state"] == ir_link.NONE
    if show == SHOW_DIFF:
        return bool(view["diffs"])
    return True


def bulk_pairs(db: Session, user: User, kind: str,
               idx: Optional[ir_link.Index] = None) -> List[Tuple[object, IrCompany]]:
    """일괄 연결이 받는 짝 — **후보가 정확히 하나인, 아직 안 이은 줄**만.

    감춘 줄은 안 받는다(목록에 안 서는 줄을 한꺼번에 잇지 않는다).
    """
    idx = idx or ir_link.index(db)
    out = []
    for row in rows_for(db, user, kind):
        company = ir_link.single_candidate(idx, row)
        if company is not None:
            out.append((row, company))
    return out


def _back(kind: str, show: str = "", msg: str = "", row: int = 0,
          anchor: int = 0) -> str:
    params = {"tab": kind}
    if show in SHOWS and show:
        params["show"] = show
    if row:
        params["row"] = row
    if msg:
        params["msg"] = msg
    url = f"{HREF}?{urlencode(params)}"
    return url + (f"#row-{anchor}" if anchor else "")


def _kind(value: str) -> str:
    if value not in ir_link.KINDS:
        raise HTTPException(status_code=400, detail="탭이 올바르지 않습니다")
    return value


# ── 화면 ────────────────────────────────────────────────────────────────────

@router.get(HREF, response_class=HTMLResponse, include_in_schema=False)
def ir_link_page(request: Request, db: Session = Depends(get_db),
                 user: User = Depends(get_current_user), tab: str = "",
                 show: str = "", row: int = 0, q: str = "", msg: str = ""):
    tabs = tabs_for(user)
    kind = tab if tab in tabs else tabs[0]
    show = show if show in SHOWS else ""
    idx = ir_link.index(db)
    counts = ir_link.link_counts(db)
    dup_ids = {c.id for group in idx.duplicate_keys().values() for c in group}
    owners = _owners(db)

    rows = rows_for(db, user, kind, include_hidden=bool(row))
    diffs = company_sync.differences(db, rows)
    views = [row_view(db, idx, r, counts, dup_ids, owners, diffs) for r in rows]
    totals = tally(views)

    focus = None
    results: List[dict] = []
    query = ""
    if row:
        focus = next((v for v in views if v["id"] == row), None)
        if focus is not None:
            # 검색어를 안 넣었으면 그 줄의 기업명으로 시작한다 — 대개 그것으로
            # 찾으려고 펴 놓은 자리다.
            query = (q or focus["name"]).strip()
            results = [company_view(c, counts, dup_ids)
                       for c in ir_link.search(idx, query)]
        shown = [focus] if focus else []
    else:
        shown = [v for v in views if not v["hidden"] and _keep(v, show)]

    tab_counts = {k: len(rows_for(db, user, k)) for k in tabs}

    ctx = base_ctx(request, db, user, ACTIVE)
    ctx.update({
        "page_title": TITLE,
        "tabs": [{"key": k, "label": TAB_LABELS[k], "count": tab_counts[k]}
                 for k in tabs],
        "kind": kind,
        "kind_label": TAB_LABELS[kind],
        "show": show,
        "rows": shown,
        "totals": totals,
        "focus": focus,
        "focus_missing": bool(row) and focus is None,
        "query": query,
        "results": results,
        "search_limit": ir_link.SEARCH_LIMIT,
        "dup_groups": len(idx.duplicate_keys()),
        "msg": msg,
        "back": _back(kind, show),
        "home_href": "/startup" if kind == ir_link.STARTUP else "/consulting",
        # 위의 IR 기업 현황 탭 줄(`_company_tabs.html`) — 이 화면이 그 넷째 탭이다.
        "co_tab": "ir-link",
        "counts": company_tab_counts(db),
    })
    return templates.TemplateResponse("ir_link.html", ctx)


@router.get(HREF + "/bulk", response_class=HTMLResponse, include_in_schema=False)
def bulk_confirm(request: Request, db: Session = Depends(get_db),
                 user: User = Depends(get_current_user), tab: str = ""):
    """일괄 연결 **확인 화면** — 몇 줄이 어느 기업에 붙는지 먼저 보인다."""
    tabs = tabs_for(user)
    kind = tab if tab in tabs else tabs[0]
    pairs = bulk_pairs(db, user, kind)
    owners = _owners(db)
    views = []
    for r, c in pairs:
        where, owner = _where(db, r, owners)
        views.append({"row_id": r.id, "name": ir_link.row_name(r),
                      "where": where, "owner": owner,
                      "company_id": c.id, "company": c.name or "",
                      # 받는 쪽(`bulk_link`)이 지금 다시 센 짝과 견주는 글자.
                      "token": f"{r.id}:{c.id}"})
    ctx = base_ctx(request, db, user, ACTIVE)
    ctx.update({
        "page_title": TITLE,
        "kind": kind,
        "kind_label": TAB_LABELS[kind],
        "pairs": views,
        "back": _back(kind),
    })
    return templates.TemplateResponse("ir_link_bulk.html", ctx)


# ── 잇기 · 풀기 ─────────────────────────────────────────────────────────────

@router.post(HREF + "/link", include_in_schema=False)
def link_row(tab: str = Form(...), row_id: int = Form(...),
             company_id: int = Form(...), show: str = Form(""),
             db: Session = Depends(get_db),
             user: User = Depends(get_current_user)):
    """[이 기업으로 연결] — 줄 하나를 IR 기업 하나에."""
    kind = _kind(tab)
    row = editable_row(db, user, kind, row_id)
    company = db.get(IrCompany, company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="IR 기업을 찾을 수 없습니다")
    name = ir_link.row_name(row) or f"#{row.id}"
    if ir_link.link(db, row, company):
        db.commit()
        msg = f"‘{name}’ 줄을 IR 기업 ‘{company.name}’ 에 이었습니다."
    else:
        msg = f"‘{name}’ 줄은 이미 ‘{company.name}’ 에 이어져 있습니다."
    # 줄 하나를 펴 놓고 이었으면 목록으로 돌아가 그 줄로 내려간다.
    return RedirectResponse(_back(kind, show, msg, anchor=row.id), status_code=303)


@router.post(HREF + "/unlink", include_in_schema=False)
def unlink_row(tab: str = Form(...), row_id: int = Form(...),
               show: str = Form(""), focus: int = Form(0),
               db: Session = Depends(get_db),
               user: User = Depends(get_current_user)):
    """[연결 해제] — 이은 것만 푼다. 줄도 IR 기업도 그대로다."""
    kind = _kind(tab)
    row = editable_row(db, user, kind, row_id)
    name = ir_link.row_name(row) or f"#{row.id}"
    if ir_link.unlink(db, row):
        db.commit()
        msg = f"‘{name}’ 줄의 IR 기업 연결을 풀었습니다."
    else:
        msg = f"‘{name}’ 줄은 이어진 IR 기업이 없습니다."
    return RedirectResponse(_back(kind, show, msg, row=focus, anchor=row.id),
                            status_code=303)


@router.post(HREF + "/bulk", include_in_schema=False)
def bulk_link(tab: str = Form(...), pair: List[str] = Form(default=[]),
              db: Session = Depends(get_db),
              user: User = Depends(get_current_user)):
    """확인 화면에서 보인 짝을 잇는다 — **그 짝이 아직 그대로인 줄만.**

    받는 것은 확인 화면이 보여 준 `줄:기업` 짝이다. 서버가 지금 다시 세어 본
    짝과 **같을 때만** 잇는다 — 그 사이 누가 그 줄을 이었거나, 같은 이름의 IR
    기업이 하나 더 생겨 후보가 둘이 되었으면 건너뛰고 수를 알린다. 확인 화면에
    없던 줄은 받지 않는다(보이지 않은 것을 잇지 않는다).
    """
    kind = _kind(tab)
    if kind == ir_link.CONSULTING:
        consulting_router.require_access(user)
    now = {row.id: (row, company) for row, company in bulk_pairs(db, user, kind)}
    done = skipped = 0
    seen = set()
    for token in pair:
        try:
            row_id, company_id = (int(x) for x in token.split(":", 1))
        except (TypeError, ValueError):
            skipped += 1
            continue
        if row_id in seen:
            continue
        seen.add(row_id)
        hit = now.get(row_id)
        if hit is None or hit[1].id != company_id:
            skipped += 1
            continue
        # 이름으로 이은 것이라 `자동 연결` 로 적는다 — 화면에서 보고 풀 수 있게.
        if ir_link.link(db, hit[0], hit[1], auto=True):
            done += 1
    db.commit()
    msg = f"{done}줄을 이었습니다."
    if skipped:
        msg += f" {skipped}줄은 그 사이 바뀌어 건너뛰었습니다(다시 확인해 주세요)."
    return RedirectResponse(_back(kind, msg=msg), status_code=303)


@router.post(HREF + "/resolve", include_in_schema=False)
def resolve_diff(tab: str = Form(...), row_id: int = Form(...),
                 field: str = Form(...), pick: str = Form(...), show: str = Form(""),
                 db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    """`값 다름` 한 칸 맞추기 — [IR 값으로](`pick=ir`) · [이 줄 값으로](`pick=row`)
    · [둘 다 남기기](`pick=both` — 연락처 · 이메일만).

    문은 잇기 · 풀기와 같다(`editable_row`). 나머지 이어진 줄은 flush 가 따라 고친다.
    """
    kind = _kind(tab)
    row = editable_row(db, user, kind, row_id)
    name = ir_link.row_name(row) or f"#{row.id}"
    try:
        company_sync.resolve(db, row, field, pick)
    except ValueError as exc:
        return RedirectResponse(_back(kind, show, f"‘{name}’ — {exc}", anchor=row.id),
                                status_code=303)
    db.commit()
    label = company_sync.LABELS.get(field, field)
    if pick == "both":
        msg = f"‘{name}’ 의 {label} 을(를) 둘 다 남겼습니다 — 앞이 IR 값(정)입니다."
    else:
        side = "IR 값" if pick == "ir" else "이 줄 값"
        msg = f"‘{name}’ 의 {label} 을(를) {side}으로 맞췄습니다."
    return RedirectResponse(_back(kind, show, msg, anchor=row.id), status_code=303)
