"""스타트업 — 우리가 챙기는 스타트업의 명단과 안내문.

## 왜 화면을 나누는가

명단도 자료도 투자사 관리 현황에 같이 붙어 있었다. 그 화면의 나머지는 **심사역
에게 딜을 보내는 이야기**다(전화응대 스크립트 · 딜소개 스크립트 · 투자사
성격정리). 그 사이에 **스타트업 대표에게 매월 안부를 묻는** 명단과 가이드가
섞여 있어서, 지금 누구에게 하는 말인지 탭을 열어 읽어 봐야 알 수 있었다.
말 거는 상대가 다르면 문구도 순서도 다르다 — 섞여 있으면 잘못된 문구를 집는다.

## 명단이 여기 오는 것을 무엇이 정하나

**이름이 아니다.** 명단에 붙은 배치(`SheetOwner.layout`)가 정하고, 그 배치가
어느 화면에 사는지는 `services/contact_columns.py` 의 `Layout.page` 한 곳에
적혀 있다. 이름으로 가르면 명단이 하나 늘 때마다 또 심어야 하고, 심는 것을
잊은 화면만 조용히 옛 명단을 보여 준다.

같은 값이 **투자사 관리 현황에서 그 탭을 빼는 일까지** 한다. 두 화면이 각자
"내 명단은 이런 것" 이라고 적어 두면 한쪽만 고쳐지는 날 명단이 두 곳에 다
뜬다 — 그러면 어느 쪽이 최신인지 알 수 없다.

## 이 화면이 하는 일

**투자사 관리 현황과 같은 것을 한다.** 명단별 탭 · 명단이 정한 표 · 달마다
늘어나는 칸 · 감춘 줄 · 인라인 수정 · 필터 · 수정창 · 엑셀 내려받기가 전부
같은 코드다(`routers/pages.py` 의 `list_page`, `templates/contacts.html`).
새로 짜면 그중 하나만 고쳐지는 날 **화면은 뜨는데 고칠 수가 없다** 가 된다.

참고 자료도 마찬가지로 이미 있는 `/ref-sheets/…` 가 그대로 다룬다
(`routers/contacts.py` 의 `ref_router`).

## 투자사 집계·발송 대상은 그대로 빠져 있다

이 명단들은 `SheetOwner.is_hidden` 으로 **투자사로 세지 않는다.** 화면을
옮긴다고 그 값이 바뀌지 않는다 — 옮기는 것과 세는 것은 다른 값이 정한다.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_current_user, templates
from ..models import User
from ..services import ir_kakao, ir_monthly
from ..ui import base_ctx
from .pages import STARTUP_PAGE, list_page

router = APIRouter(tags=["startup"])

# 자료가 어느 화면에 붙는지 정하는 값(`RefSheet.page`). 주소 조각과 **같아야
# 한다** — 고칠 권한 판정이 `/{page}` 를 열 수 있는 사람인지로 본다.
# 명단이 어느 화면에 서는지도 같은 값이다(`Layout.page`).
PAGE = STARTUP_PAGE.page


@router.get("/startup", response_class=HTMLResponse)
def startup_page(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    sheet: str = "",
    ref: str = "",
    contact: int = 0,
    months: str = "",
    hidden: int = 0,
    msg: str = "",
):
    """스타트업 — 명단과 참고 자료.

    받는 값이 투자사 관리 현황과 **한 글자도 다르지 않다.** 하나라도 빠지면
    그 조작만 이 화면에서 안 먹는다(달 칸 펴기·감춘 줄 함께 보기 등).
    """
    return list_page(request, db, user, STARTUP_PAGE, sheet=sheet, ref=ref,
                     contact=contact, months=months, hidden=hidden, msg=msg)


# ── 이번 달 귀사 IR 자료를 요청한 투자사 ─────────────────────────────────────
#
# ## 왜 여기인가
#
# 업무 보고(`/report`)가 아니다. 그 화면은 **우리 팀원 단위**로 잘리는데(누가
# 얼마나 했는가), 이 문서는 **스타트업 한 곳 단위**다(귀사에 몇 곳이 물어봤는가).
# 받는 사람도 다르다 — 보고는 우리가 보고, 이 문서는 스타트업 대표가 본다.
#
# ## 세는 자리는 화면에 없다
#
# 두 출처를 합치고 못 맞춘 것을 세는 일은 전부 `services/ir_monthly.py` 에 있다.
# 화면이 직접 세면 나중에 발송이 붙을 때 발송 쪽에서 또 세게 되고, 두 숫자가
# 갈리는 날 문서에는 `3곳`, 화면에는 `2곳` 이 뜬다.
#
# ## 이름을 가리는 자리도 화면에 없다
#
# `services/ir_mask.py` 하나다. 화면에 가리는 규칙을 적으면 엑셀·발송이 각자
# 적게 되고, 낡은 쪽이 이름을 그대로 내보낸다.


@router.get("/startup/ir-report", response_class=HTMLResponse)
def ir_report_list(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    month: str = "",
):
    """계약을 마친 기업마다 **그 달에 몇 곳이 요청했는지**. 문서로 들어가는 문.

    요청이 0곳인 기업도 목록에 남는다(까닭은 `ir_monthly.overview`).
    """
    months = ir_monthly.month_options(db)
    # 고른 달은 **모양만 본다.** 목록(`months`)은 기록이 있는 달로 만드는데,
    # 기록이 하나도 없는 달을 열지 못하면 "그 달에 정말 요청이 없었는가" 를
    # 화면에서 확인할 수가 없다 — 계약 기업 대부분이 그런 달이다.
    selected = month if ir_monthly.is_month(month) else ir_monthly.this_month()
    if selected not in months:
        months = sorted(set(months) | {selected}, reverse=True)
    ctx = base_ctx(request, db, user, STARTUP_PAGE.key)
    ctx.update(ir_monthly.overview(db, selected))
    ctx.update({"months": months, "selected": selected})
    return templates.TemplateResponse("startup_ir_report.html", ctx)


@router.get("/startup/ir-report/{company_id}", response_class=HTMLResponse)
def ir_report_doc(
    company_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    month: str = "",
    who: int = 0,
):
    """문서 한 장 — 스타트업 대표에게 그대로 주는 화면.

    ### 인쇄가 곧 PDF 다

    새 라이브러리를 들이지 않는다. 사람이 `인쇄 → PDF 로 저장` 을 누르고, 그때
    좌측 메뉴·단추·안내가 전부 빠지도록 `@media print` 가 정리한다(app.css).
    PDF 를 서버에서 만들면 글꼴·줄바꿈이 화면과 달라져 **보이는 것과 나가는 것이
    다른** 상태가 된다.

    ### `who=1` — 담당자 이름을 실을지

    기본은 **안 싣는다.** 회사명만으로도 알릴 것은 다 알리고, 사람 이름은 새는
    자리를 하나 더 만든다(성 한 글자 + 가려진 회사명이 붙으면 짐작하기 훨씬
    쉬워진다). 필요할 때만 켠다 — 가리는 규칙은 켜든 끄든 같은 함수를 지난다.
    """
    # 목록 화면과 **같은 판정**을 지난다. 여기서만 다르게 읽으면 목록에서
    # 누른 달과 문서가 세는 달이 어긋난다.
    selected = month if ir_monthly.is_month(month) else ir_monthly.this_month()
    got = ir_monthly.report(db, company_id, selected)
    ctx = base_ctx(request, db, user, STARTUP_PAGE.key)
    ctx.update({"report": got, "show_person": bool(who), "selected": selected})
    return templates.TemplateResponse("startup_ir_doc.html", ctx,
                                      status_code=200 if got else 404)


# ── 카톡으로 나가는 글 ───────────────────────────────────────────────────────
#
# ## 문서와 무엇이 다른가
#
# 위 문서(#131)는 **인쇄해서 주는 한 장**이고, 이것은 **카톡에 붙여 넣는 글**이다.
# 사용자가 실제로 보내던 것이 글 쪽이었다. 문서는 지우지 않는다 — Windows 파일
# 첨부 시험에 쓰인다.
#
# 다른 점이 둘 더 있다.
#   · **누적이다.** `7월 말까지` 는 7월 한 달이 아니라 그때까지 쌓인 것 전부다.
#   · 담당자 이름을 켤 자리가 없다. 실물에 투자사만 적혀 있다 — 새는 자리를
#     하나 덜 만드는 쪽이라 굳이 켜는 길을 내지 않는다.
#
# ## 한 대표에게 기업이 여럿일 때 — **묶지 않는다**
#
# 실물은 한 글에 기업 둘(`(주)가 , (주)나`)을 담고 있었다. 그래서 "같은 대표의
# 기업을 어떻게 묶을 것인가" 를 먼저 봤다. 앱이 대표를 아는 칸은 셋이다 —
# `IrCompany.contact_name` · `contact_phone` · `contact_email`. **어느 것도
# 묶을 근거가 되지 못했다.**
#
#   · `contact_phone` · `contact_email` — 계약 기업 중 채워진 것이 전부
#     **서로 다른 값**이었다. 겹치는 짝이 하나도 없다. 이 둘로 묶으면 묶이는
#     기업이 0곳이라, 묶는 길을 내도 하는 일이 없다.
#   · `contact_name` — 겹치는 짝이 딱 하나 있었는데, **그 둘은 전화번호가
#     서로 달랐다.** 즉 같은 이름의 **다른 사람**일 가능성이 크다. 명단의
#     이름은 대부분 세 글자 한국 이름이라 동명이인이 흔하다.
#
# 이름으로 묶었다면 이 저장소에서 지금 일어날 일은 **딱 한 건**이고, 그 한 건이
# 하필 **틀린 묶음**이다 — 남의 회사 IR 요청 목록이 엉뚱한 대표에게 간다.
# 이 일에서 되돌릴 수 없는 사고는 그것 하나뿐이라, 얻는 것이 0이고 잃을 것이
# 그것인 거래는 하지 않는다.
#
# **그래서 화면은 기업 하나씩 부른다.** 글을 짓는 함수(`ir_kakao.compose`)는
# 기업을 **여럿** 받게 두었다 — 실물의 모양이 그것이고, 나중에 "이 기업들은
# 한 대표" 라고 말해 주는 칸이 생기면 함수는 그대로 두고 부르는 쪽만 바꾸면
# 된다. 없는 근거를 이름으로 지어내는 대신, 근거가 들어올 자리를 비워 둔다.


@router.get("/startup/ir-kakao/{company_id}", response_class=HTMLResponse)
def ir_kakao_message(
    company_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    month: str = "",
):
    """카톡에 붙여 넣을 글 한 통 — 보고 [문구 복사] 를 누르는 자리.

    **여기서 보내지 않는다.** 스타트업 카톡방이 자료에 없다(`IrCompany` 에 방
    칸 자체가 없다). 보내는 시늉을 내는 단추를 세우면 눌러 놓고 나간 줄 아는
    사람이 생긴다 — 짓고 · 보여 주고 · 복사하는 데까지만이다.

    요청이 **한 곳도 없으면 404** 다. 글을 짓지 않는 판정은 `ir_kakao.compose`
    한 곳에 있다 — 화면이 따로 세면 두 판정이 갈린다.
    """
    # 문서 화면과 **같은 판정**을 지난다.
    selected = month if ir_monthly.is_month(month) else ir_monthly.this_month()
    msg = ir_kakao.for_company(db, company_id, selected)
    ctx = base_ctx(request, db, user, STARTUP_PAGE.key)
    ctx.update({"msg": msg, "selected": selected, "company_id": company_id})
    return templates.TemplateResponse("startup_ir_kakao.html", ctx,
                                      status_code=200 if msg else 404)
