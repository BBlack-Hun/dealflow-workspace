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
from ..deps import NotAdmin, admin_only, get_current_user, templates
from ..models import IrCompany, User
from ..services import auth as auth_svc
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

# 화면에 보이는 말 → 저장하는 값.
#
# 표에서 `계약여부` 칸을 눌러 고치면 inline_edit.js 는 **칸에 보이는 글자**를
# 그대로 보낸다(`딜소개 불가`). 스키마에 칸이 있으니 PATCH 는 200 을 주는데,
# 들어간 글자는 어느 상태에도 안 맞아 되읽을 때 `미계약` 으로 돌아오고
# `blocked` 도 안 걸렸다 — **고쳐지지도, 막히지도 않는** 상태다.
# 그래서 받는 쪽이 말과 값을 같은 것으로 본다. 시트 가져오기가 이미 그렇게
# 하고 있다(scripts/import_company_sheets.py 의 CONTRACT_FROM_SHEET).
#
# 띄어쓰기는 지우고 견준다 — 사람은 `딜소개 불가` 와 `딜소개불가` 를 같은
# 말로 쓴다. 한 글자 차이로 안 걸리는 것이 바로 지금 난 사고다.
CONTRACT_FROM_LABEL = {label.replace(" ", ""): key
                       for key, label in CONTRACT_LABELS.items()}

# 더 이상 소개하면 안 되는 기업. 발송 화면 목록에서 아예 빠진다 —
# 목록에 있는 것만으로 실수로 고를 수 있다.
BLOCKED_CONTRACT = "blocked"

# 계약서를 실제로 받았는가. `계약여부`(맺기로 했는가)와 다른 사실이라 칸이 따로다.
#
# **여기에는 말↔값 짝이 없다.** 화면에 보이는 글자가 곧 저장되는 값이다 —
# 위 `CONTRACT_FROM_LABEL` 이 생긴 사고(표는 `딜소개 불가` 를 보내는데 저장은
# `blocked` 여야 했던 것)가 여기서는 **날 자리가 없게** 값을 고른 것이다.
#
# **빈 값이 셋째 값이다.** `O`/`X` 둘뿐이면 아직 아무도 확인하지 않은 기업을
# 적을 방법이 없어서, 전부 `X`("확인했는데 안 왔다")로 시작하는 수밖에 없다 —
# 그건 단언이지 사실이 아니다. 비워 두면 화면에서 빈 칸이고 필터에서는
# `(비어 있음)` 으로 골라진다(`static/js/filters.js` 의 `EMPTY`).
RECEIVED_CHOICES = ("O", "X")


def received_key(value) -> Optional[str]:
    """`계약서 수신됨` 에 저장할 값. 비었으면 `None`(아직 안 정함).

    대소문자만 맞춰 준다 — 눌러 고치는 칸은 `O`/`X` 를 눌러 고르지만 직접
    타이핑도 되는 자리라 소문자 `o` 가 들어온다. 그대로 두면 필터 목록이
    `o` 와 `O` 두 벌로 갈려, 한쪽을 골랐을 때 방금 고친 그 기업만 사라진다
    (이 저장소가 단계·계약여부에서 겪은 그 부류다).

    모르는 글자(`△`·`확인중`)는 지어내지 않고 그대로 돌려준다 — 부르는 쪽이
    `RECEIVED_CHOICES` 에 있는지 보고 막는다.
    """
    text = (value or "").strip()
    if not text:
        return None
    upper = text.upper()
    return upper if upper in RECEIVED_CHOICES else text


def contract_key(value) -> str:
    """무엇으로 적혀 오든 **저장하는 값 하나**로.

    받는 것은 세 가지다: 지금 값(`blocked`) · 예전 값(`yes`) · 화면에 보이는
    말(`딜소개 불가`). 모르는 말은 지어내지 않고 그대로 돌려준다 — 부르는
    쪽이 `CONTRACT_LABELS` 에 있는지 보고 막는다.
    """
    key = (value or "none").strip()
    key = CONTRACT_FROM_LABEL.get(key.replace(" ", ""), key)
    return CONTRACT_ALIAS.get(key, key)


def can_delete_company(user: User) -> bool:
    """이 사람에게 [삭제] 를 보여도 되는가 — **판정은 `deps.admin_only` 하나**다.

    화면과 라우터가 각자 `role == "admin"` 을 들고 있으면 반드시 한쪽이 낡는다.
    이 저장소가 반복해 당한 유형이다(팀 전체가 뜨는데 눌러 고치면 404 나던
    담당자 줄, `막힘` 이라 떠 있는데 실제로는 열려 있던 컨설턴트 줄). 같은
    함수를 부르므로 **단추가 보이는 사람은 반드시 지울 수 있고, 안 보이는
    사람은 주소를 직접 쳐도 막힌다.**
    """
    try:
        admin_only(user)
    except NotAdmin:
        return False
    return True

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


def search_text(c: IrCompany) -> str:
    """줄에 실어 둘 검색용 글자 한 덩이. 화면(companies.js)은 이것만 본다.

    기업명·분야만 담고 있었다. 그런데 표에는 대표자·연락처·이메일이 버젓이
    보이므로, 눈앞의 값을 그대로 쳐도 아무 줄이 안 걸렸다 — 사람에게는
    "검색이 고장났다" 로 보인다. 보이는 칸으로는 찾아져야 한다.

    전화번호는 **적은 그대로와 숫자만 남긴 꼴을 함께** 싣는다. 원본에
    `010-1234-5678` · `01012345678` · `010 1234 5678` 이 섞여 있어서, 한 모양만
    실어 두면 다른 모양으로 친 사람에게는 없는 줄이 된다. 숫자만 남긴 꼴이
    있으면 뒷자리(`5678`)로도 닿는다 — 실제로 번호는 이렇게 찾는다.

    친 글자 쪽을 숫자만 남기는 일은 companies.js 가 맡는다. 양쪽이 다 있어야
    `010 1234 5678` 로 쳐서 `010-1234-5678` 인 줄에 닿는다.

    숫자만 남긴 꼴이 원본과 같으면(이미 숫자뿐인 번호) 넣지 않는다 — 같은
    글자가 두 번 실려도 걸리는 것은 똑같고, 줄만 길어진다.
    """
    phone = (c.contact_phone or "").strip()
    digits = auth_svc.normalize_phone(phone)
    parts = [
        c.name, c.contact_name, c.contact_email, phone,
        digits if digits != phone else "",
        c.sector_major, c.sector_minor, c.series,
        c.one_liner, c.funding_status, c.competitiveness,
    ]
    return " ".join(filter(None, parts)).lower()


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
            # **저장된 글자 그대로가 아니라 맞춰서** 돌려준다. 예전 값(`no`·`yes`)이
            # 그대로 나가면 수정 패널의 <select> 에 같은 option 이 없어 고른 것이
            # 없는 상태가 되고, 그대로 [저장]하면 빈 값이 날아가 NOT NULL 인
            # 이 칸에서 **저장 전체가 500** 이 났다 — 344개 중 244개가 그랬다.
            # 사람에게는 "IR 링크를 고쳤더니 저장 오류" 로 보였다(패널은 모든
            # 칸을 한 번에 보내므로, 터진 칸이 아니라 마지막에 만진 칸을 의심하게 된다).
            "contract_status": contract_key(c.contract_status),
            "contract_label": CONTRACT_LABELS.get(
                contract_key(c.contract_status), "미계약"),
            # 더 이상 소개하면 안 되는 기업 — 표에서 눈에 띄어야 실수로
            # 고르지 않는다(발송 화면 목록에서는 아예 빠진다).
            "blocked": contract_key(c.contract_status) == BLOCKED_CONTRACT,
            # 아직 안 정한 기업은 **빈 글자**로 나간다. 표에서는 빈 칸이고,
            # 필터는 그것을 `(비어 있음)` 으로 모은다 — 없는 값을 지어내
            # `X` 로 채우면 "확인했는데 안 왔다" 는 뜻이 되어 버린다.
            "contract_received": c.contract_received or "",
            "contract_month": c.contract_month or "",
            "is_top_deal": bool(c.is_top_deal),
            "summary_status": c.summary_status or "draft",
            "summary_label": SUMMARY_LABELS.get(c.summary_status or "draft", "작성 중"),
            "introducible": is_ready(c),
            "blocked_reason": blocked_reason(c),
            "note": c.note or "",
            # 검색용 — 화면에서 즉시 필터링한다. 무엇이 들어가는지는 `search_text`.
            "search": search_text(c),
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
        # [삭제]를 보일지. 라우터가 막는 것과 **같은 판정**을 읽는다 —
        # 보이는데 못 누르거나, 안 보이는데 주소로는 되는 상태를 만들지 않는다.
        "can_delete": can_delete_company(user),
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
    contract_received: Optional[str] = None
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
        elif field == "contract_status":
            # 표에서 누르면 **보이는 글자**(`딜소개 불가`)가, 수정 패널에서는
            # 값(`blocked`)이 온다. 저장은 반드시 값이어야 한다 — 발송 화면이
            # 컬럼을 그대로 견주기 때문이다(routers/pages.py 의 `/deals`).
            #
            # 모르는 말은 조용히 넣지 않고 막는다. 넣어 두면 되읽을 때 `미계약`
            # 으로 보여 **고친 적 없는 것처럼** 되고, `딜소개 불가` 로 바꿔 둔
            # 줄 알았던 기업이 발송 목록에 그대로 남는다.
            key = contract_key(value)
            if key not in CONTRACT_LABELS:
                raise HTTPException(
                    status_code=400,
                    detail="모르는 계약여부입니다: "
                           f"{value!r} — {' · '.join(CONTRACT_LABELS.values())} "
                           "중에서 고르세요")
            company.contract_status = key
        elif field == "contract_received":
            # 빈 값은 지우는 것이다 — `미정` 으로 되돌릴 길이 있어야 한다.
            # (잘못 찍은 `O` 를 `X` 로만 고칠 수 있으면 그것도 거짓말이 된다.)
            key = received_key(value)
            if key is not None and key not in RECEIVED_CHOICES:
                raise HTTPException(
                    status_code=400,
                    detail="모르는 계약서 수신 여부입니다: "
                           f"{value!r} — {' · '.join(RECEIVED_CHOICES)} 중에서 "
                           "고르거나, 아직 안 정했으면 비워 두세요")
            company.contract_received = key
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


def _contract_result(company: IrCompany) -> dict:
    """PATCH/POST 응답에 실을 계약여부 · 계약서 수신됨.

    **되읽기까지 맞아야 화면이 안 어긋난다.** 표는 값(`blocked`)이 아니라
    말(`딜소개 불가`)을 보여 주는데, 응답이 값만 주면 화면은 방금 누른 글자를
    그대로 남겨 두는 수밖에 없다 — 새로고침하면 다른 글자가 나온다.
    `blocked` 도 같이 준다: 그 줄에 표시를 입히는 것은 화면의 몫이다.

    `계약서 수신됨` 은 보이는 글자가 곧 값이라 짝지을 것이 없지만, 소문자
    `o` 를 대문자로 맞춰 넣는다 — **맞춘 값**을 돌려줘야 화면이 그것으로
    되그린다. 안 그러면 칸에는 `o`, DB 에는 `O` 가 남아 필터 목록이 두 벌로
    갈린다(빈 값은 빈 글자로 준다 — 표의 빈 칸과 같은 모양이다).
    """
    key = contract_key(company.contract_status)
    return {"contract_status": key,
            "contract_label": CONTRACT_LABELS.get(key, "미계약"),
            "blocked": key == BLOCKED_CONTRACT,
            "contract_received": company.contract_received or ""}


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
            **_contract_result(company),
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
    """기업 삭제 — **관리자만**. 이미 보낸 회차에 들어간 기업은 지우지 않는다.

    판정은 `deps.admin_only` 하나를 그대로 쓴다(`can_delete_company` 가 화면
    쪽에서 같은 함수를 읽는다). 여기 `role != "admin"` 을 새로 적으면 단추를
    보일지 정하는 쪽과 갈린다.

    **권한을 먼저 본다.** 없는 번호에 404 를 먼저 주면, 권한 없는 사람이 번호만
    바꿔 가며 어느 기업이 있는지 알아낼 수 있다.
    """
    from ..models import DealBatchCompany
    from ..services import deal_queue

    admin_only(user)
    company = db.get(IrCompany, company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="기업을 찾을 수 없습니다")
    used = db.execute(
        select(DealBatchCompany).where(DealBatchCompany.company_id == company_id)
    ).scalars().first()
    if used:
        # **이력이 붙은 기업은 관리자여도 지우지 않는다.** 회차는 "그날 누구에게
        # 무엇을 보냈는가" 의 기록이고, 기업을 지우면 그 회차가 무엇을 보낸
        # 회차였는지 알 수 없게 된다 — 업무 보고가 그 줄을 읽는다.
        #
        # 안내가 가리키던 '보류'는 **틀린 길이었다.** 보류(내용 부족)는 발송
        # 화면에서 뒤로 밀릴 뿐 그대로 뜬다(routers/pages.py 가 일부러 감추지
        # 않는다). 목록에서 실제로 빠지는 것은 `딜소개 불가` 하나뿐이다.
        raise HTTPException(
            status_code=400,
            detail=f"'{company.name}' 은 이미 발송한 회차에 들어 있어 삭제할 수 "
                   "없습니다 — 지우면 그 회차에 무엇을 보냈는지가 사라집니다. "
                   "계약여부를 '딜소개 불가' 로 두면 발송 목록에서 빠집니다.",
        )
    if company_id in deal_queue.used_company_ids(db):
        # **예약은 기록이 아니라 계획이다.** 위와 같은 말("이미 발송한 회차에
        # 들어 있어")을 하면 안 된다 — 아직 아무에게도 안 나갔는데 보냈다고
        # 말하는 것이라, 사람이 회차 이력을 뒤지다가 못 찾는다.
        #
        # 그렇다고 그냥 지우면 예약 줄이 없는 기업을 가리킨 채 남아, [시작] 을
        # 누르는 순간 `기업 … 없음` 으로 죽는다. 그때는 왜 죽는지 화면에서
        # 알 길이 없다. 조용히 예약에서 빼는 것도 답이 아니다 — 세 곳으로
        # 예약해 둔 회차가 말없이 두 곳이 되어 나간다.
        raise HTTPException(
            status_code=400,
            detail=f"'{company.name}' 은 딜 제안 관리의 **예약**에 들어 있어 "
                   "삭제할 수 없습니다 — 아직 나가지 않은 예약입니다. "
                   "그 예약을 취소한 뒤 지우세요.",
        )
    # 취소한 예약이 붙들고 있던 줄은 놓아 준다. 접어 둔 계획 하나 때문에
    # 기업이 영영 안 지워지면 안 되고(예약 줄을 지우는 단추는 없다), 그 막이는
    # 외래키가 하는 것이라 화면에는 이유 없는 서버 오류로만 뜬다.
    deal_queue.release_company(db, company_id)
    db.delete(company)
    db.commit()
    return {"deleted": company_id}
