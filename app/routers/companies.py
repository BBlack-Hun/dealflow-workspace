"""딜 기업 DB — 소개할 기업을 보고 고치는 화면.

딜소개 문구는 여기 있는 값으로 조립된다. 그래서 이 화면의 진짜 목적은
목록 구경이 아니라 **"왜 이 기업은 소개 목록에 안 뜨는가"를 그 자리에서 고치는 것**이다.
그래서 표에 `소개 가능` 열을 두고, 안 되는 이유를 함께 보여준다.

소개 가능 조건(IrCompany.introducible)은 문구에 실제로 들어가는 것만 본다.
- 소개할 내용(분야 또는 한줄소개)이 있고
- 숫자(매출·누적투자·희망투자·Pre Value)가 하나라도 있고
- 사람이 '보류'로 내리지 않았을 것
"""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_current_user, templates
from ..models import IrCompany, User
from ..ui import base_ctx

router = APIRouter(tags=["companies"])

SUMMARY_LABELS = {
    "done": "작성 완료",
    "draft": "작성 중",
    "insufficient": "보류",
}
CONTRACT_LABELS = {"yes": "완료", "pending": "진행 중", "no": "없음"}


def blocked_reason(c: IrCompany) -> str:
    """소개 목록에 안 뜨는 이유를 사람 말로 돌려준다(뜨면 빈 문자열)."""
    if c.introducible:
        return ""
    if c.summary_status == "insufficient":
        return "보류로 표시됨"
    has_text = bool((c.sector_major or "").strip() or (c.one_liner or "").strip())
    has_number = any(v for v in (c.revenue_recent, c.funding_total,
                                 c.raise_target, c.pre_value))
    missing = []
    if not has_text:
        missing.append("분야 또는 한줄소개")
    if not has_number:
        missing.append("숫자(매출·투자금 중 하나)")
    return " · ".join(missing) + " 없음" if missing else "내용 부족"


def company_rows(db: Session) -> List[dict]:
    companies = db.execute(select(IrCompany).order_by(IrCompany.name)).scalars().all()
    return [
        {
            "id": c.id,
            "name": c.name,
            "sector_major": c.sector_major or "",
            "sector_minor": c.sector_minor or "",
            "series": c.series or "",
            "one_liner": c.one_liner or "",
            "revenue_recent": c.revenue_recent,
            "funding_total": c.funding_total,
            "raise_target": c.raise_target,
            "pre_value": c.pre_value,
            "competitiveness": c.competitiveness or "",
            "funding_status": c.funding_status or "",
            "ir_drive_url": c.ir_drive_url or "",
            "contract_status": c.contract_status or "no",
            "contract_label": CONTRACT_LABELS.get(c.contract_status or "no", "-"),
            "contract_month": c.contract_month or "",
            "is_top_deal": bool(c.is_top_deal),
            "summary_status": c.summary_status or "draft",
            "summary_label": SUMMARY_LABELS.get(c.summary_status or "draft", "작성 중"),
            "introducible": c.introducible,
            "blocked_reason": blocked_reason(c),
            "note": c.note or "",
            # 검색용 — 화면에서 즉시 필터링한다
            "search": " ".join(filter(None, [
                c.name, c.sector_major, c.sector_minor, c.series,
                c.one_liner, c.funding_status, c.competitiveness,
            ])).lower(),
        }
        for c in companies
    ]


@router.get("/companies", response_class=HTMLResponse, include_in_schema=False)
def companies_page(request: Request, db: Session = Depends(get_db),
                   user: User = Depends(get_current_user), msg: str = "", q: str = ""):
    rows = company_rows(db)
    ctx = base_ctx(request, db, user, active="su")
    ctx.update({
        "rows": rows,
        "msg": msg,
        "q": q,          # 발송 화면에서 '기업 정보 채우기' 로 넘어온 경우 그 기업을 바로 띄운다
        "counts": {
            "total": len(rows),
            "introducible": sum(1 for r in rows if r["introducible"]),
            "blocked": sum(1 for r in rows if not r["introducible"]),
            "top": sum(1 for r in rows if r["is_top_deal"]),
        },
        "summary_labels": SUMMARY_LABELS,
        "contract_labels": CONTRACT_LABELS,
    })
    return templates.TemplateResponse("companies.html", ctx)


# --- 편집 -------------------------------------------------------------------

class CompanyIn(BaseModel):
    name: str
    sector_major: Optional[str] = None
    sector_minor: Optional[str] = None
    series: Optional[str] = None
    one_liner: Optional[str] = None
    revenue_recent: Optional[int] = None
    funding_total: Optional[int] = None
    raise_target: Optional[int] = None
    pre_value: Optional[int] = None
    competitiveness: Optional[str] = None
    funding_status: Optional[str] = None
    ir_drive_url: Optional[str] = None
    contract_status: Optional[str] = None
    contract_month: Optional[str] = None
    is_top_deal: Optional[bool] = None
    summary_status: Optional[str] = None
    note: Optional[str] = None


def _assign(company: IrCompany, body: CompanyIn) -> None:
    data = body.model_dump(exclude_unset=True)
    for field, value in data.items():
        if field == "is_top_deal":
            company.is_top_deal = 1 if value else 0
        elif field == "name":
            if value and value.strip():
                company.name = value.strip()
        else:
            setattr(company, field, (value.strip() if isinstance(value, str) else value) or None)


@router.get("/api/companies")
def list_companies(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return {"rows": company_rows(db)}


@router.get("/api/companies/{company_id}")
def get_company(company_id: int, db: Session = Depends(get_db),
                user: User = Depends(get_current_user)):
    company = db.get(IrCompany, company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="기업을 찾을 수 없습니다")
    row = next(r for r in company_rows(db) if r["id"] == company_id)
    return row


@router.post("/api/companies")
def create_company(body: CompanyIn, db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)):
    if not body.name.strip():
        raise HTTPException(status_code=400, detail="기업명을 입력하세요")
    company = IrCompany(name=body.name.strip(), owner_user_id=user.id,
                        summary_status=body.summary_status or "draft")
    _assign(company, body)
    db.add(company)
    db.commit()
    return {"id": company.id}


@router.patch("/api/companies/{company_id}")
def update_company(company_id: int, body: CompanyIn,
                   db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)):
    company = db.get(IrCompany, company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="기업을 찾을 수 없습니다")
    _assign(company, body)
    db.commit()
    return {"id": company.id, "introducible": company.introducible,
            "blocked_reason": blocked_reason(company)}


@router.delete("/api/companies/{company_id}")
def delete_company(company_id: int, db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)):
    """기업 삭제. 이미 보낸 회차에 들어간 기업은 지우지 않는다(이력이 깨진다)."""
    from ..models import DealBatchCompany

    company = db.get(IrCompany, company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="기업을 찾을 수 없습니다")
    used = db.execute(
        select(DealBatchCompany).where(DealBatchCompany.company_id == company_id)
    ).scalars().first()
    if used:
        raise HTTPException(
            status_code=400,
            detail="이미 발송한 회차에 포함된 기업이라 삭제할 수 없습니다. "
                   "대신 '보류'로 표시하면 소개 목록에서 빠집니다.",
        )
    db.delete(company)
    db.commit()
    return {"deleted": company_id}
