"""공지 — 올리는 자리(관리자)와 **확인했다고 적는 자리**(모두).

라우터를 따로 두는 이유
-----------------------
공지를 올리고 내리는 것은 팀 현황의 일이지만, **[확인] 을 누르는 것은 모든
화면에서 일어난다** — 판이 밑틀(`base.html`)에 서기 때문이다. 그 길을 팀
현황 라우터 안에 두면 `관리자 화면의 파일에 전원이 두드리는 주소가 있는`
모양이 되어, 다음 사람이 그 파일을 통째로 관리자 전용으로 막는 날 조용히
깨진다(그런 사고가 이 저장소에 이미 있었다 — 좌측 메뉴와 라우터가 갈렸던 일).

**화면을 그리지 않는다.** 공지에는 전용 화면이 없다: 보는 자리는 밑틀,
적는 자리는 팀 현황이다. 여기 있는 것은 셋 다 눌렀을 때 일어나는 일뿐이고,
끝나면 누르기 전에 보던 화면으로 되돌린다.
"""
from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, Form
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import admin_only, get_current_user
from ..models import User
from ..services import notices as svc

router = APIRouter(tags=["notices"])


def _back(where: str, fallback: str = "/") -> RedirectResponse:
    """누르기 전에 보던 화면으로. **밖으로 나가는 주소는 받지 않는다.**

    돌아갈 곳이 폼에 실려 오는데(판이 모든 화면에 서므로 서버는 어디서
    눌렸는지를 그 값으로만 안다), 그대로 믿으면 남의 사이트로 보내는 링크를
    만들 수 있다. `/` 로 시작하되 `//` 가 아닌 것만 통과시킨다.
    """
    where = (where or "").strip()
    if not where.startswith("/") or where.startswith("//"):
        where = fallback
    return RedirectResponse(where, status_code=303)


@router.post("/notices/seen", include_in_schema=False)
def mark_seen(back: str = Form(""), notice_id: List[int] = Form(default=[]),
              db: Session = Depends(get_db),
              user: User = Depends(get_current_user)):
    """**확인했습니다** — 이 사람에게 이 공지들이 다시 뜨지 않는다.

    번호는 **그때 화면에 실제로 떠 있던 것**만 온다(숨은 칸). `지금 켜져 있는
    것 전부` 로 두면 화면을 열어 둔 사이에 올라온 공지가 뜨지도 않고 읽음이
    된다.

    누구나 부를 수 있다 — 자기 것을 읽었다고 적는 일이라 관리자만의 일이
    아니고, 투자컨설턴트에게도 열려 있다(`deps.CONSULTANT_PATHS`). 막으면
    그 계정에서는 같은 공지가 **영영** 떠 있게 된다.
    """
    svc.mark_seen(db, user, notice_id)
    return _back(back)


@router.post("/team/notices", include_in_schema=False)
def publish(title: str = Form(""), body: str = Form(""),
            db: Session = Depends(get_db),
            user: User = Depends(get_current_user)):
    """공지를 올린다 — 관리자만. 올린 순간부터 팀 전원의 화면 위에 선다."""
    admin_only(user)
    svc.publish(db, user, title, body)
    return _back("/team")


@router.post("/team/notices/{notice_id}/off", include_in_schema=False)
def turn_off(notice_id: int, db: Session = Depends(get_db),
             user: User = Depends(get_current_user)):
    """내린다 — 관리자만. 아직 확인하지 않은 사람에게도 그 순간부터 안 뜬다."""
    admin_only(user)
    svc.turn_off(db, notice_id)
    return _back("/team")


@router.post("/team/notices/{notice_id}/on", include_in_schema=False)
def turn_on(notice_id: int, db: Session = Depends(get_db),
            user: User = Depends(get_current_user)):
    """잘못 내린 것을 다시 올린다 — 관리자만.

    **이미 확인한 사람에게는 다시 안 뜬다**(`services/notices.turn_on`).
    """
    admin_only(user)
    svc.turn_on(db, notice_id)
    return _back("/team")
