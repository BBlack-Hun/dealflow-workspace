"""투자컨설턴트 현황 — 구글시트를 그대로 옮긴 표.

원본 시트를 여러 사람이 같이 고치다 보니 어디까지 반영됐는지 알기 어려웠다.
여기로 옮겨 **한 곳에서 고치고, 누가 언제 고쳤는지 남게** 한다.

정해진 사람만 보는 화면이다(관리자 + `can_view_consulting` 이 켜진 계정).
대표자 연락처·이메일이 들어 있어서 팀 전체에 열어 둘 표가 아니다.

시트의 값은 대부분 자유 문장이다 — 미팅일이 `9/16 PM2 (화상미팅)` 처럼 적혀 있다.
형식을 강제하면 원본을 옮길 수 없으므로 그대로 문자열로 받는다.

월별 리마인드 열(`8월 마지막주 리마인드 톡 or TEL` …)은 달마다 하나씩 늘어난다.
테이블 컬럼으로 두면 매달 마이그레이션을 해야 하므로 행으로 두고,
내용은 기업 행의 JSON 에 담는다.
"""
from __future__ import annotations

import json
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_current_user, templates
from ..models import ConsultingColumn, ConsultingCompany, User
from ..services import spreadsheet as sp
from ..ui import base_ctx

router = APIRouter(tags=["consulting"])

# 시트의 고정 열. (화면 표시 이름, 모델 속성)
FIXED_COLUMNS = [
    ("NO", "position"),
    ("지역", "region"),
    ("미팅일(화상, 회의실)", "meeting_at"),
    ("기업명 / 계약일 / 무료유료 / 계약금, 성과수수료 %", "company_name"),
    ("기업 관리 [ 드랍 이유 상세하게 기입 / 관리중 / 백업팀으로 전환 ]", "management"),
]
TAIL_COLUMNS = [
    ("대표자", "ceo_name"),
    ("연락처", "phone"),
    ("이메일", "email"),
]


def require_access(user: User) -> None:
    """관리자이거나, 이 화면을 보도록 허용된 계정이어야 한다.

    투자컨설턴트 계정은 이 화면이 전부다 — 따로 켜 줄 필요가 없다.
    """
    if user.role in ("admin", "consultant") or user.can_view_consulting:
        return
    raise HTTPException(status_code=403, detail="이 화면을 볼 권한이 없습니다")


# 표에 한 번에 보여줄 월 수. 달마다 한 칸씩 늘어나는 표라, 그냥 두면 한 해
# 뒤에는 열두 칸이 되어 가로로 밀어야 읽힌다. 실제로 챙기는 것은 최근 몇
# 달뿐이다.
VISIBLE_MONTHS = 3


# 원본 시트 이름. 관리하는 사람이 달라 한 표에 쏟으면 자기 명단을 못 찾는다.
SHEETS = ["중요 스타트업", "경영본부 전달 기업"]
DEFAULT_SHEET = SHEETS[0]


def sheet_tabs(db: Session) -> List[dict]:
    """시트별 인원. 탭에 건수를 띄운다."""
    rows = dict(db.execute(
        select(ConsultingCompany.sheet, func.count())
        .group_by(ConsultingCompany.sheet)
    ).all())
    # 시트에 자료가 아직 없어도 탭은 보여야 한다 — 없는 줄 알고 또 만든다.
    names = SHEETS + [s for s in rows if s not in SHEETS]
    return [{"key": n, "label": n, "count": rows.get(n, 0)} for n in names]


def _columns(db: Session, sheet: str = "") -> List[ConsultingColumn]:
    stmt = select(ConsultingColumn).order_by(ConsultingColumn.position,
                                             ConsultingColumn.id)
    if sheet:
        stmt = stmt.where(ConsultingColumn.sheet == sheet)
    return db.execute(stmt).scalars().all()


def _split_columns(columns: List[ConsultingColumn], show_all: bool = False) -> tuple:
    """(보여줄 월, 접어 둔 월).

    **접었다는 것을 사람이 알아야 한다** — 그냥 안 보이면 지워진 줄 안다.
    화면에 몇 달이 접혀 있는지 적고, 눌러서 펼 수 있게 한다.
    """
    if show_all or len(columns) <= VISIBLE_MONTHS:
        return columns, []
    return columns[:VISIBLE_MONTHS], columns[VISIBLE_MONTHS:]


def _notes(company: ConsultingCompany) -> Dict[str, str]:
    try:
        return json.loads(company.notes or "{}")
    except (TypeError, ValueError):
        return {}


def company_rows(db: Session, sheet: str = "") -> List[dict]:
    cols = _columns(db, sheet)
    stmt = select(ConsultingCompany).order_by(ConsultingCompany.position,
                                              ConsultingCompany.id)
    if sheet:
        stmt = stmt.where(ConsultingCompany.sheet == sheet)
    companies = db.execute(stmt).scalars().all()
    out = []
    for order, c in enumerate(companies, start=1):
        notes = _notes(c)
        out.append({
            "id": c.id,
            # 화면의 NO 는 **보이는 순서대로 1부터**다. 시트에서 옮겨 온 번호는
            # 중간이 비거나 3부터 시작해서, 몇 번째 줄인지 세는 데 쓸 수 없다.
            "no": order,
            "position": c.position,
            "region": c.region or "",
            "meeting_at": c.meeting_at or "",
            "company_name": c.company_name or "",
            "management": c.management or "",
            "ceo_name": c.ceo_name or "",
            "phone": c.phone or "",
            "email": c.email or "",
            "notes": {str(col.id): notes.get(str(col.id), "") for col in cols},
            "updated_at": (c.updated_at or "")[:10],
            "search": " ".join(filter(None, [
                c.company_name, c.region, c.management, c.ceo_name,
                c.email, c.meeting_at, *notes.values(),
            ])).lower(),
        })
    return out


@router.get("/consulting", response_class=HTMLResponse, include_in_schema=False)
def consulting_page(request: Request, db: Session = Depends(get_db),
                    user: User = Depends(get_current_user), msg: str = "",
                    months: str = "", sheet: str = ""):
    require_access(user)
    tabs = sheet_tabs(db)
    selected = sheet if any(t["key"] == sheet for t in tabs) else DEFAULT_SHEET
    rows = company_rows(db, selected)
    # 달마다 한 칸씩 늘어나는 표라, 최근 몇 달만 펴 둔다.
    # `months=all` 은 일부러 다 본다는 뜻이다.
    shown, hidden = _split_columns(_columns(db, selected),
                                   show_all=(months == "all"))
    ctx = base_ctx(request, db, user, active="consult")
    ctx.update({
        "rows": rows,
        "sheet_tabs": tabs,
        "selected_sheet": selected,
        "columns": shown,
        # **접었다는 것을 사람이 알아야 한다** — 그냥 안 보이면 지워진 줄 안다.
        "hidden_columns": hidden,
        "show_all_months": months == "all",
        "fixed_columns": FIXED_COLUMNS,
        "tail_columns": TAIL_COLUMNS,
        "msg": msg,
        "counts": {
            "total": len(rows),
            "managed": sum(1 for r in rows if "관리" in r["management"]),
            "dropped": sum(1 for r in rows if "드랍" in r["management"]),
            "contacted": sum(1 for r in rows if any(r["notes"].values())),
        },
    })
    return templates.TemplateResponse("consulting.html", ctx)


# --- 편집 -------------------------------------------------------------------

class CompanyIn(BaseModel):
    position: Optional[int] = None
    region: Optional[str] = None
    meeting_at: Optional[str] = None
    company_name: Optional[str] = None
    management: Optional[str] = None
    ceo_name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    # {"열id": "내용"} — 월별 리마인드
    notes: Optional[Dict[str, str]] = None


def _assign(company: ConsultingCompany, body: CompanyIn) -> None:
    data = body.model_dump(exclude_unset=True)
    notes = data.pop("notes", None)
    for field, value in data.items():
        setattr(company, field,
                value.strip() if isinstance(value, str) else value)
    if notes is not None:
        # 통째로 덮지 않고 병합한다 — 화면이 보내지 않은 달의 기록이 사라지면 안 된다.
        merged = _notes(company)
        merged.update({k: (v or "").strip() for k, v in notes.items()})
        company.notes = json.dumps({k: v for k, v in merged.items() if v},
                                   ensure_ascii=False)


@router.get("/api/consulting/{company_id}")
def get_company(company_id: int, db: Session = Depends(get_db),
                user: User = Depends(get_current_user)):
    require_access(user)
    row = next((r for r in company_rows(db) if r["id"] == company_id), None)
    if row is None:
        raise HTTPException(status_code=404, detail="기업을 찾을 수 없습니다")
    return row


@router.post("/api/consulting")
def create_company(body: CompanyIn, db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)):
    require_access(user)
    if not (body.company_name or "").strip():
        raise HTTPException(status_code=400, detail="기업명을 입력하세요")
    if body.position is None:
        # 새 줄은 맨 아래로. 시트의 NO 를 사람이 매번 세지 않아도 되게.
        last = db.execute(
            select(ConsultingCompany.position)
            .order_by(ConsultingCompany.position.desc()).limit(1)
        ).scalar()
        body.position = (last or 0) + 1
    company = ConsultingCompany()
    _assign(company, body)
    db.add(company)
    db.commit()
    return {"id": company.id}


@router.patch("/api/consulting/{company_id}")
def update_company(company_id: int, body: CompanyIn,
                   db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)):
    require_access(user)
    company = db.get(ConsultingCompany, company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="기업을 찾을 수 없습니다")
    _assign(company, body)
    db.commit()
    return {"id": company.id}


@router.delete("/api/consulting/{company_id}")
def delete_company(company_id: int, db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)):
    require_access(user)
    company = db.get(ConsultingCompany, company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="기업을 찾을 수 없습니다")
    db.delete(company)
    db.commit()
    return {"deleted": company_id}


# --- 월별 열 ----------------------------------------------------------------

@router.post("/consulting/columns", include_in_schema=False)
def add_column(label: str = Form(...), db: Session = Depends(get_db),
               user: User = Depends(get_current_user)):
    """달이 바뀌면 열을 하나 늘린다. 새 열이 **맨 앞**에 오도록 한다.

    시트에서도 최근 달이 왼쪽이다 — 지금 챙겨야 할 달이 먼저 보여야 한다.
    """
    require_access(user)
    label = label.strip()
    if not label:
        return RedirectResponse("/consulting?msg=열+이름을+입력하세요", status_code=303)
    for col in _columns(db):
        col.position += 1
    db.add(ConsultingColumn(label=label, position=0))
    db.commit()
    return RedirectResponse(f"/consulting?msg={label}+열을+추가했습니다", status_code=303)


@router.post("/consulting/columns/{column_id}/rename", include_in_schema=False)
def rename_column(column_id: int, label: str = Form(...),
                  db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    require_access(user)
    col = db.get(ConsultingColumn, column_id)
    if col is None:
        raise HTTPException(status_code=404, detail="열을 찾을 수 없습니다")
    if label.strip():
        col.label = label.strip()
        db.commit()
    return RedirectResponse("/consulting?msg=열+이름을+바꿨습니다", status_code=303)


@router.post("/consulting/columns/{column_id}/delete", include_in_schema=False)
def delete_column(column_id: int, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    """열을 지우면 그 달의 기록도 함께 사라진다 — 화면에서 한 번 더 묻는다."""
    require_access(user)
    col = db.get(ConsultingColumn, column_id)
    if col is None:
        raise HTTPException(status_code=404, detail="열을 찾을 수 없습니다")
    key = str(col.id)
    for company in db.execute(select(ConsultingCompany)).scalars().all():
        notes = _notes(company)
        if key in notes:
            notes.pop(key)
            company.notes = json.dumps(notes, ensure_ascii=False)
    db.delete(col)
    db.commit()
    return RedirectResponse("/consulting?msg=열을+삭제했습니다", status_code=303)


# --- 업로드 · 내려받기 ------------------------------------------------------

@router.post("/consulting/import", include_in_schema=False)
def import_sheet(file: UploadFile = File(...), sheet: str = Form(""),
                 replace: bool = Form(False),
                 db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    """원본 시트를 올려 통째로 반영한다.

    이 표는 시트가 원본이라 '한 줄씩 맞추기'보다 **통째로 갈아끼우는** 편이 맞다.
    다만 여기서 고친 내용이 날아갈 수 있으므로 화면에서 한 번 더 확인받는다.
    """
    require_access(user)
    data = file.file.read()
    try:
        rows = sp.read_rows(file.filename or "", data, sheet or None)
    except sp.SpreadsheetError as exc:
        return RedirectResponse(f"/consulting?msg={exc}", status_code=303)

    parsed = parse_rows(rows)
    if not parsed["companies"]:
        return RedirectResponse(
            "/consulting?msg=읽을+내용을+찾지+못했습니다.+'NO'와+'기업명'이+있는+시트인지+확인하세요",
            status_code=303)

    report = apply_rows(db, parsed, replace=replace)
    return RedirectResponse(
        f"/consulting?msg=기업+{report['created']}건+추가·{report['updated']}건+갱신"
        f"+(열+{report['columns']}개)",
        status_code=303)


CONSULTING_EXPORT_HEADERS = [label for label, _ in FIXED_COLUMNS]


@router.get("/api/export/consulting.xlsx")
def export_consulting(db: Session = Depends(get_db),
                      user: User = Depends(get_current_user)):
    require_access(user)
    cols = _columns(db)
    headers = (CONSULTING_EXPORT_HEADERS + [c.label for c in cols]
               + [label for label, _ in TAIL_COLUMNS])
    rows = [
        [r["no"], r["region"], r["meeting_at"], r["company_name"], r["management"]]
        + [r["notes"].get(str(c.id), "") for c in cols]
        + [r["ceo_name"], r["phone"], r["email"]]
        for r in company_rows(db)
    ]
    try:
        content = sp.write_xlsx("투자컨설턴트 현황", headers, rows)
    except sp.SpreadsheetError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    from datetime import date

    return Response(content=content, media_type=sp.XLSX_MEDIA_TYPE,
                    headers=sp.content_disposition(
                        f"투자컨설턴트 현황_{date.today().isoformat()}.xlsx"))


# --- 시트 읽기 --------------------------------------------------------------

def _norm(value) -> str:
    return " ".join(str(value or "").split())


def parse_rows(rows: List[List[str]]) -> dict:
    """시트 → {열 이름들, 기업 행들}.

    머리행은 위치가 아니라 **내용**으로 찾는다. 시트 위쪽에 제목·빈 줄이 있고
    사람이 행을 넣다 빼다 하므로 '4번째 줄'이라고 못 박으면 곧 깨진다.
    """
    header_idx = None
    for i, row in enumerate(rows[:30]):
        cells = [_norm(c) for c in row]
        if "NO" in cells and any("기업" in c for c in cells):
            header_idx = i
            break
    if header_idx is None:
        return {"columns": [], "companies": []}

    header = [_norm(c) for c in rows[header_idx]]

    def find(*tokens) -> Optional[int]:
        for j, h in enumerate(header):
            if all(t in h for t in tokens):
                return j
        return None

    idx = {
        "position": find("NO"),
        "region": find("지역"),
        "meeting_at": find("미팅일"),
        "company_name": find("기업명"),
        "management": find("기업 관리"),
        "ceo_name": find("대표자"),
        "phone": find("연락처"),
        "email": find("이메일"),
    }
    # 나머지 = 월별 리마인드 열. 이름을 그대로 쓴다(시트와 같아 보여야 한다).
    used = {v for v in idx.values() if v is not None}
    note_cols = [(j, header[j]) for j in range(len(header))
                 if j not in used and header[j]]

    companies = []
    for row in rows[header_idx + 1:]:
        cells = list(row) + [""] * (len(header) - len(row))
        name = _norm(cells[idx["company_name"]]) if idx["company_name"] is not None else ""
        no = _norm(cells[idx["position"]]) if idx["position"] is not None else ""
        if not name and not no:
            continue
        if not name:
            continue        # 번호만 있고 기업명이 없는 줄은 빈 칸이다
        item = {"notes": {}}
        for field, j in idx.items():
            if j is None:
                continue
            raw = cells[j]
            item[field] = _norm(raw)
        for j, label in note_cols:
            text = _norm(cells[j])
            if text:
                item["notes"][label] = text
        companies.append(item)

    return {"columns": [label for _j, label in note_cols], "companies": companies}


def apply_rows(db: Session, parsed: dict, replace: bool = False) -> dict:
    """읽은 내용을 DB 에 반영. 기업명이 같으면 갱신, 없으면 추가."""
    if replace:
        db.query(ConsultingCompany).delete()
        db.commit()

    # 열 먼저 — 기업의 notes 가 열 id 를 키로 쓴다
    existing_cols = {c.label: c for c in _columns(db)}
    for pos, label in enumerate(parsed["columns"]):
        col = existing_cols.get(label)
        if col is None:
            col = ConsultingColumn(label=label, position=pos)
            db.add(col)
            existing_cols[label] = col
    db.flush()

    by_name = {(c.company_name or "").strip(): c
               for c in db.execute(select(ConsultingCompany)).scalars().all()}

    created = updated = 0
    for item in parsed["companies"]:
        name = item.get("company_name", "")
        company = by_name.get(name)
        if company is None:
            company = ConsultingCompany()
            db.add(company)
            by_name[name] = company
            created += 1
        else:
            updated += 1
        for field in ("region", "meeting_at", "company_name", "management",
                      "ceo_name", "phone", "email"):
            value = item.get(field)
            if value:
                setattr(company, field, value)
        raw_no = item.get("position") or ""
        digits = "".join(ch for ch in raw_no if ch.isdigit())
        if digits:
            company.position = int(digits)
        notes = _notes(company)
        for label, text in item["notes"].items():
            col = existing_cols.get(label)
            if col is not None:
                notes[str(col.id)] = text
        company.notes = json.dumps(notes, ensure_ascii=False)

    db.commit()
    return {"created": created, "updated": updated,
            "columns": len(parsed["columns"])}
