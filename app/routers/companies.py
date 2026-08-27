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
from ..services.one_liner import (
    AUTO, SOURCE_FIELDS, apply_one_liner, compose_one_liner, origin, sync_one_liner,
)
from ..ui import base_ctx

router = APIRouter(tags=["companies"])

SUMMARY_LABELS = {
    "done": "작성 완료",
    "draft": "작성 중",
    "insufficient": "보류",
}
# 계약 상태. **운영에서 쓰는 다섯 가지** 그대로 둔다 —
# 완료/진행중/없음 셋으로 뭉치면 '무료'와 '유료'가 같은 칸에 들어가고,
# '딜소개불가'(더 이상 소개하면 안 되는 기업)가 '없음'에 섞여 사고가 난다.
CONTRACT_LABELS = {
    "none": "미계약",
    "free": "무료계약완료",
    "paid": "유료계약완료",
    "review": "계약검토중",
    "blocked": "딜소개 불가",
}
# 예전 값 → 지금 값. 이미 쌓인 데이터를 화면에서 그대로 읽을 수 있어야 한다.
CONTRACT_ALIAS = {"yes": "paid", "pending": "review", "no": "none", "": "none"}

# 더 이상 소개하면 안 되는 기업. 발송 화면 목록에서 아예 빠진다 —
# 목록에 있는 것만으로 실수로 고를 수 있다.
BLOCKED_CONTRACT = "blocked"


def contract_key(value) -> str:
    key = (value or "none").strip()
    return CONTRACT_ALIAS.get(key, key)

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


# 핵심/TOP Deal 은 시트에 `핵심` · `TOP` · `핵심, TOP` · `TOP, 핵심` 으로
# 적혀 있다. 뒤 둘은 같은 뜻인데 글자가 달라서 필터가 두 줄로 센다.
TOP_ORDER = ["핵심", "TOP"]


def top_deal_kind(value: Optional[str]) -> Optional[str]:
    """`TOP, 핵심` → `핵심, TOP`. 적힌 순서와 상관없이 한 가지 모양으로."""
    text = (value or "").strip()
    if not text:
        return None
    found = [k for k in TOP_ORDER if k.lower() in text.lower()]
    return ", ".join(found) if found else text


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
    # 344행 × 두 번 조립하지 않도록 한 번만 만들어 둔다.
    made = {c.id: compose_one_liner(c) for c in companies}
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
            # 스타트업DB 칸들을 이어 붙이면 나올 한 줄. **바로 미리보기**다 —
            # 표를 보는 사람이 "지금 값 vs 자동으로 만들면 이렇게 된다"를 나란히
            # 볼 수 있어야, 덮을지 손으로 쓴 것을 지킬지 고를 수 있다.
            "one_liner_suggestion": made[c.id],
            # 지금 소개가 자동 조합과 **글자까지 같은가**. 같으면 사람이 손댄 적이
            # 없다는 뜻이라 스타트업DB 를 고칠 때 그냥 갱신해도 잃을 것이 없다.
            "one_liner_auto": origin(c.one_liner, made[c.id]) == AUTO,
            "revenue_recent": c.revenue_recent,
            "funding_total": c.funding_total,
            "raise_target": c.raise_target,
            "pre_value": c.pre_value,
            # 스타트업DB 탭 — 시트를 그대로 옮겨 담은 칸들.
            # 금액은 적은 그대로(글자)다: 원본에 `8.2억`·`1,224백만원`·
            # `150억 ~ 200억` 이 섞여 있어 숫자로 바꾸면 100배가 틀어진다.
            "ceo": c.contact_name or "",
            # 홍보메일 답장을 받은 날. 시트의 맨 앞 칸이다.
            "received_at": c.received_at or "",
            "phone": c.contact_phone or "",
            "email": c.contact_email or "",
            "revenue_2022": c.revenue_2022 or "",
            "revenue_2023": c.revenue_2023 or "",
            "revenue_2024": c.revenue_2024 or "",
            "revenue_2025": c.revenue_2025 or "",
            "founded_year": c.founded_year or "",
            "guarantee": c.guarantee or "",
            "business_desc": c.business_desc or "",
            "top_deal_kind": c.top_deal_kind or "",
            "assignee": c.assignee_name or "",
            "competitiveness": c.competitiveness or "",
            "funding_status": c.funding_status or "",
            "ir_drive_url": c.ir_drive_url or "",
            # 자료 링크 유무가 곧 'IR 요청이 오면 바로 보낼 수 있는가' 다.
            "has_ir": bool((c.ir_drive_url or "").strip()),
            "contract_status": c.contract_status or "no",
            "contract_label": CONTRACT_LABELS.get(
                contract_key(c.contract_status), "미계약"),
            # 더 이상 소개하면 안 되는 기업 — 표에서 눈에 띄어야 실수로
            # 고르지 않는다(발송 화면 목록에서는 아예 빠진다).
            "blocked": contract_key(c.contract_status) == BLOCKED_CONTRACT,
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
                   user: User = Depends(get_current_user), msg: str = "", q: str = "",
                   tab: str = ""):
    rows = company_rows(db)
    ctx = base_ctx(request, db, user, active="su")
    ctx.update({
        "rows": rows,
        # 시트의 하단 탭 두 개. 같은 레코드를 다르게 보는 것뿐이라, 한쪽에서
        # 고치면 다른 쪽이 저절로 따라온다 — 맞춰 주는 코드가 없어야 안 어긋난다.
        "co_tab": "db" if tab == "db" else "status",
        "msg": msg,
        "q": q,          # 발송 화면에서 '기업 정보 채우기' 로 넘어온 경우 그 기업을 바로 띄운다
        "counts": {
            "total": len(rows),
            "introducible": sum(1 for r in rows if r["introducible"]),
            "blocked": sum(1 for r in rows if not r["introducible"]),
            "with_ir": sum(1 for r in rows if r["has_ir"]),
            # 스타트업DB 탭에 볼 것이 있는 기업 — 대표자·연락처 같은 기초자료가
            # 하나라도 들어온 곳. 전체와 나란히 놓으면 얼마나 채웠는지 보인다.
            "with_info": sum(1 for r in rows
                             if r["ceo"] or r["phone"] or r["business_desc"]),
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
    contact_name: Optional[str] = None
    contact_phone: Optional[str] = None
    contact_email: Optional[str] = None
    revenue_2022: Optional[str] = None
    revenue_2023: Optional[str] = None
    revenue_2024: Optional[str] = None
    revenue_2025: Optional[str] = None
    founded_year: Optional[str] = None
    guarantee: Optional[str] = None
    received_at: Optional[str] = None
    business_desc: Optional[str] = None
    top_deal_kind: Optional[str] = None
    assignee_name: Optional[str] = None
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
        if field == "top_deal_kind":
            # 골라 넣으면 '추천 딜' 도 함께 켜진다 — 두 곳을 따로 켜게 하면
            # 한쪽만 켜 둔 채 잊는다.
            company.top_deal_kind = top_deal_kind(value)
            company.is_top_deal = 1 if company.top_deal_kind else 0
        elif field == "is_top_deal":
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


# 조합에 쓰이는 칸 이름. 이 중 하나라도 고쳤을 때만 한줄 소개를 다시 맞춘다 —
# 계약여부처럼 상관없는 칸을 고쳤는데 소개가 바뀌면 사람이 이유를 알 수 없다.
ONE_LINER_SOURCES = {attr for attr, _label in SOURCE_FIELDS}


def _one_liner_result(company: IrCompany, synced: dict) -> dict:
    """PATCH/POST 응답에 실을 한줄 소개 상태.

    **덮지 않았을 때도 만들어 둔 값을 함께 돌려준다.** 조용히 넘어가면 사람은
    스타트업DB 를 채웠는데 왜 소개가 그대로인지 알 수 없다 — 화면이 이 값으로
    "이렇게 바꿀까요?" 를 물을 수 있어야 한다.
    """
    return {
        "one_liner": company.one_liner or "",
        "one_liner_suggestion": synced["suggestion"],
        "one_liner_applied": synced["applied"],
        # 손으로 쓴 소개가 있어서 자동 조합을 **안 덮고 지켰다**는 표시.
        "one_liner_kept_manual": synced["kept"] and bool(synced["suggestion"]),
    }


@router.post("/api/companies")
def create_company(body: CompanyIn, db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)):
    if not (body.name or "").strip():
        raise HTTPException(status_code=400, detail="기업명을 입력하세요")
    company = IrCompany(name=body.name.strip(), owner_user_id=user.id,
                        summary_status=body.summary_status or "draft")
    _assign(company, body)
    # 새로 만드는 기업은 소개가 비어 있다 — 스타트업DB 칸을 함께 적어 넣었다면
    # 그 자리에서 한 줄을 만들어 둔다(지울 손글씨가 없으니 잃을 것도 없다).
    synced = sync_one_liner(company, previous_auto=None,
                            manual_edit=bool((body.one_liner or "").strip()))
    db.add(company)
    db.commit()
    return {"id": company.id, **_one_liner_result(company, synced)}


@router.patch("/api/companies/{company_id}")
def update_company(company_id: int, body: CompanyIn,
                   db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)):
    company = db.get(IrCompany, company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="기업을 찾을 수 없습니다")

    sent = body.model_dump(exclude_unset=True)
    # 고치기 **전** 칸들로 만든 한 줄. 지금 저장된 소개가 이것과 같으면 그건
    # 이 코드가 만든 값이라 갱신해도 잃을 것이 없다(one_liner.sync_one_liner 참고).
    previous_auto = compose_one_liner(company)
    # 소개 칸에 **글자를 적어 보낸** 경우만 손편집이다. 비워서 보낸 것은
    # "자동 조합을 다시 넣어 달라"는 뜻으로 받는다 — 비운 칸을 다시 비워 두면
    # 되돌릴 방법이 없다.
    manual_edit = "one_liner" in sent and bool((sent.get("one_liner") or "").strip())

    _assign(company, body)

    touched = bool(ONE_LINER_SOURCES & set(sent)) or "one_liner" in sent
    synced = (sync_one_liner(company, previous_auto, manual_edit=manual_edit) if touched
              else {"applied": False, "suggestion": compose_one_liner(company),
                    "kept": False, "origin": ""})
    db.commit()
    return {"id": company.id, "introducible": is_ready(company),
            "blocked_reason": blocked_reason(company),
            **_one_liner_result(company, synced)}


@router.get("/api/companies/{company_id}/one-liner")
def preview_one_liner(company_id: int, db: Session = Depends(get_db),
                      user: User = Depends(get_current_user)):
    """스타트업DB 칸들로 만들면 어떤 한 줄이 되는지 **미리** 본다(저장하지 않는다)."""
    company = db.get(IrCompany, company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="기업을 찾을 수 없습니다")
    suggestion = compose_one_liner(company)
    return {
        "id": company.id,
        "current": company.one_liner or "",
        "suggestion": suggestion,
        # auto  = 지금 소개가 자동 조합 그대로다
        # manual= 사람이 쓴 소개다(덮으려면 아래 POST 로 명시해야 한다)
        # empty = 아직 비어 있다
        "origin": origin(company.one_liner, suggestion),
        "differs": (company.one_liner or "").strip() != suggestion,
    }


@router.post("/api/companies/{company_id}/one-liner")
def use_auto_one_liner(company_id: int, db: Session = Depends(get_db),
                       user: User = Depends(get_current_user)):
    """사람이 "자동 조합을 쓰겠다"고 고른 경우 — 손으로 쓴 소개까지 덮는다.

    자동 갱신은 손글씨를 절대 안 덮기 때문에, **덮는 길은 여기 하나뿐**이다.
    누르는 사람이 무엇을 지우는지 알고 누르도록 이전 값을 함께 돌려준다.
    """
    company = db.get(IrCompany, company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="기업을 찾을 수 없습니다")
    before = company.one_liner or ""
    suggestion = apply_one_liner(company)
    db.commit()
    return {"id": company.id, "one_liner": company.one_liner or "",
            "previous": before, "applied": bool(suggestion)}


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
