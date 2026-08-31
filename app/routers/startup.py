"""스타트업 리마인드 — 우리가 챙기는 스타트업 쪽 안내문·스크립트.

## 왜 화면을 나누는가

이 자료들은 투자사 관리 현황의 참고 탭에 같이 붙어 있었다. 그 화면의 나머지
자료는 **심사역에게 딜을 보내는 이야기**다(전화응대 스크립트 · 딜소개 스크립트 ·
투자사 성격정리). 그 사이에 **스타트업 대표에게 보내는** 매월 리마인드 가이드가
섞여 있어서, 지금 누구에게 하는 말인지 탭을 열어 읽어 봐야 알 수 있었다.
말 거는 상대가 다르면 문구도 순서도 다르다 — 섞여 있으면 잘못된 문구를 집는다.

## 이 화면이 하는 일

참고 자료를 여는 것뿐이다. 고치고 · 이름 바꾸고 · 감추는 것은 이미 있는
`/ref-sheets/…` 가 그대로 한다(`routers/contacts.py` 의 `ref_router`) —
화면마다 조작을 새로 만들면 한쪽만 고쳐진다.

## 명단은 아직 여기 없다

`스타트업(16)` 명단(사람 데이터)은 투자사 관리 현황의 탭으로 남아 있다.
사람 데이터를 옮기는 것은 명단 소유·월별 칸·발송 대상 판정이 함께 따라오는
일이라, 확인 없이 옮기면 되돌리기 어렵다. 이 화면은 **자료부터** 옮긴다.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_current_user, templates
from ..models import User
from ..services import ref_panel
from ..ui import base_ctx

router = APIRouter(tags=["startup"])

# 자료가 어느 화면에 붙는지 정하는 값(`RefSheet.page`). 주소 조각과 **같아야
# 한다** — 고칠 권한 판정이 `/{page}` 를 열 수 있는 사람인지로 본다.
PAGE = "startup"


@router.get("/startup", response_class=HTMLResponse)
def startup_page(
    request: Request,
    ref: str = "",
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    ctx = base_ctx(request, db, user, "startup")
    ctx.update(ref_panel.panel_ctx(db, PAGE, ref))
    # 이 화면에는 명단 탭이 없다. 패널이 [닫기]·[저장] 뒤에 돌아갈 자리를
    # 만들 때 쓰는 값이라 비워서 넘긴다 — 없으면 그 자리에서 터진다.
    ctx["selected_sheet"] = ""
    return templates.TemplateResponse("startup.html", ctx)
