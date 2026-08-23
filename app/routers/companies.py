"""딜 기업 DB — 소개할 기업을 보고 고치는 화면.

딜소개 문구는 여기 있는 값으로 조립된다. 그래서 이 화면의 진짜 목적은
목록 구경이 아니라 **"왜 이 기업은 소개 목록에 안 뜨는가"를 그 자리에서 고치는 것**이다.
그래서 표에 `소개 가능` 열을 두고, 안 되는 이유를 함께 보여준다.

**소개 가능** = 딜 소개 문구에 들어가는 칸이 **하나도 빠지지 않은** 상태다.

    회사명 | 사업분야 | 년매출 | 누적투자금액 | 투자유치 진행금액
    | Pre Value | 특이사항(기업 특장점) | IR 자료

하나라도 비면 '내용 부족'이다. 예전에는 '분야나 한줄소개 + 숫자 하나'만 있으면
가능으로 봤는데, 그러면 문구가 반쯤 빈 채로 나간다. 무엇이 비었는지도
화면에서 바로 보여준다.
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

# 소개 문구에 들어가는 칸. (모델 속성, 화면 이름)
REQUIRED_FIELDS = [
    ("name", "회사명"),
    ("sector_major", "사업분야"),
    ("revenue_recent", "년매출"),
    ("funding_total", "누적투자금액"),
    ("raise_target", "투자유치 진행금액"),
    ("pre_value", "Pre Value"),
    ("competitiveness", "특이사항"),
    ("ir_drive_url", "IR 자료"),
]



def eok(value: Optional[int]) -> str:
    """저장값(백만원)을 억으로. `1830` → `18.3`.

    표에 백만원을 그대로 두면 `1,000` 이 10억이라 아무도 못 읽는다. 딜소개
    문구는 이미 억으로 나가고 있어서 표와 문구가 서로 다른 숫자를 보여줬다.
    """
    from ..services.message_composer import format_eok

    return format_eok(value) or ""


def _short(value: Optional[str]) -> str:
    """괄호 앞까지. 표 한 칸에 설명까지 넣으면 정작 이름이 안 보인다."""
    return (value or "").split(" (")[0].strip()


def missing_fields(c: IrCompany) -> List[str]:
    """비어 있는 칸의 **화면 이름** 목록. 무엇을 채워야 하는지 바로 알 수 있게."""
    out = []
    for attr, label in REQUIRED_FIELDS:
        value = getattr(c, attr, None)
        if value is None or (isinstance(value, str) and not value.strip()):
            out.append(label)
    return out


def is_ready(c: IrCompany) -> bool:
    """딜 소개 문구를 온전히 만들 수 있는가."""
    if c.summary_status == "insufficient":
        return False
    return not missing_fields(c)


def blocked_reason(c: IrCompany) -> str:
    """소개 목록에 안 뜨는 이유(뜨면 빈 문자열)."""
    if is_ready(c):
        return ""
    if c.summary_status == "insufficient":
        return "보류로 표시됨"
    missing = missing_fields(c)
    head = ", ".join(missing[:3])
    more = f" 외 {len(missing) - 3}개" if len(missing) > 3 else ""
    return f"{head}{more} 없음"


def company_rows(db: Session) -> List[dict]:
    companies = db.execute(select(IrCompany).order_by(IrCompany.name)).scalars().all()
    return [
        {
            "id": c.id,
            "name": c.name,
            "sector_major": c.sector_major or "",
            "sector_minor": c.sector_minor or "",
            "series": c.series or "",
            # 실제 값은 "Pre A, Bridge (누적투자금 5억미만, 년매출액 10억이상)" 처럼 길다.
            # 괄호 안은 297행에 똑같이 반복되는 **설명**이라 표에서는 앞부분만 보인다
            # (전체는 툴팁과 편집창에서 본다).
            "series_short": _short(c.series),
            "one_liner": c.one_liner or "",
            "revenue_recent": c.revenue_recent,
            "funding_total": c.funding_total,
            "raise_target": c.raise_target,
            "pre_value": c.pre_value,
            "competitiveness": c.competitiveness or "",
            "funding_status": c.funding_status or "",
            "ir_drive_url": c.ir_drive_url or "",
            # 자료 링크 유무가 곧 'IR 요청이 오면 바로 보낼 수 있는가' 다.
            "has_ir": bool((c.ir_drive_url or "").strip()),
            "contract_status": c.contract_status or "no",
            "contract_label": CONTRACT_LABELS.get(c.contract_status or "no", "-"),
            "contract_month": c.contract_month or "",
            "is_top_deal": bool(c.is_top_deal),
            "summary_status": c.summary_status or "draft",
            "summary_label": SUMMARY_LABELS.get(c.summary_status or "draft", "작성 중"),
            "introducible": is_ready(c),
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
            "with_ir": sum(1 for r in rows if r["has_ir"]),
        },
        "required_fields": [label for _a, label in REQUIRED_FIELDS],
        "summary_labels": SUMMARY_LABELS,
        "contract_labels": CONTRACT_LABELS,
    })
    return templates.TemplateResponse("companies.html", ctx)


@router.post("/companies/ir-links", include_in_schema=False)
def bulk_ir_links(pasted: str = Form(""), db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    """IR 자료 링크를 한 번에 붙여넣는다.

    297개를 하나씩 여닫으며 넣을 수는 없다. 시트에서 **기업명과 링크 두 열을
    복사해 붙이면** 그대로 들어가게 한다(탭 또는 쉼표로 나뉜다).

    이름이 안 맞는 줄은 **조용히 버리지 않고** 몇 건인지 알려 준다 —
    넣은 줄 알았는데 안 들어간 것이 제일 나쁘다.
    """
    from urllib.parse import quote

    matched, missed, blank = _apply_ir_links(db, pasted)
    db.commit()

    parts = [f"{matched}건 반영"]
    if missed:
        shown = ", ".join(missed[:5])
        more = f" 외 {len(missed) - 5}건" if len(missed) > 5 else ""
        parts.append(f"못 찾은 기업 {len(missed)}건: {shown}{more}")
    if blank:
        parts.append(f"링크가 없는 줄 {blank}건")
    return RedirectResponse(f"/companies?msg={quote(' · '.join(parts))}",
                            status_code=303)


def _apply_ir_links(db: Session, pasted: str) -> tuple:
    """붙여넣은 텍스트 → (반영 수, 못 찾은 기업명, 링크 없는 줄 수)."""
    from ..services.sheet_import import normalize_company_name

    by_key = {}
    for company in db.execute(select(IrCompany)).scalars().all():
        key = normalize_company_name(company.name or "").replace(" ", "").lower()
        if key:
            by_key.setdefault(key, company)

    matched, missed, blank = 0, [], 0
    for line in (pasted or "").splitlines():
        line = line.strip()
        if not line:
            continue
        # 탭이 먼저다 — 시트에서 복사하면 탭으로 나뉘고, 기업명에 쉼표가 있을 수 있다.
        parts = line.split("\t") if "\t" in line else line.rsplit(",", 1)
        if len(parts) < 2:
            blank += 1
            continue
        name, url = parts[0].strip(), parts[-1].strip()
        if not url or not url.lower().startswith("http"):
            blank += 1
            continue
        key = normalize_company_name(name).replace(" ", "").lower()
        company = by_key.get(key)
        if company is None:
            missed.append(name[:20])
            continue
        company.ir_drive_url = url
        matched += 1
    return matched, missed, blank


# --- 편집 -------------------------------------------------------------------

class CompanyIn(BaseModel):
    # PATCH 로 한 칸만 고치는 일이 잦다(표에서 눌러 바로 수정). 그때 기업명까지
    # 같이 보내라고 하면 칸 하나 고치는 데 이름이 필요해진다 — 만들 때만 필수다.
    name: Optional[str] = None
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
        elif isinstance(value, str):
            setattr(company, field, value.strip() or None)
        else:
            # 0 을 None 으로 바꾸면 안 된다 — '매출 0' 과 '아직 안 적음'은 다르다.
            setattr(company, field, value)


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
    if not (body.name or "").strip():
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
    return {"id": company.id, "introducible": is_ready(company),
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
