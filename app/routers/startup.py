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
from ..deps import get_current_user
from ..models import User
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
