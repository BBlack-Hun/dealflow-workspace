"""딜 소싱 — 우리 딜을 같이 볼 사람 명단.

투자사 관리 현황(딜소개를 **보내는** 명단)과는 성격이 다르다. 여기는
시리즈 A 이상·개인 참여·M&A·후속투자처럼 **찾는 것**으로 나뉘고, 같은
사람이 여러 갈래에 들어갈 수 있다.

여기서는 **보고 고친다.** 실제로 보내는 것은 딜 제안 관리의 [딜 소싱 제안]
탭이고, 그 대상이 이 표다 — 그래서 카톡방 이름 칸이 여기 있다.
"""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_current_user, templates
from ..models import SourcingContact, User
from ..ui import base_ctx

router = APIRouter(tags=["sourcing"])

# 표 컬럼 — 원본 시트 순서 그대로. 쓰던 사람이 같은 자리에서 같은 것을 찾는다.
COLUMNS = [
    ("requested_at", "참여 요청일", "96px"),
    ("name", "이름", "96px"),
    ("assignee_name", "담당자", "72px"),
    ("phone", "휴대폰", "116px"),
    ("title", "직함", "84px"),
    ("email", "이메일 주소", "170px"),
    ("firm", "회사", "150px"),
    ("sectors", "투자분야", "120px"),
    ("round_size", "라운드 사이즈", "130px"),
    ("memo", "메모", ""),
    # 여기서 딜 소싱 제안을 보낸다 — 방 이름이 없으면 보낼 길이 없다.
    # 발송 화면(딜 제안 관리)에서 고를 수 있으려면 이 칸이 먼저 차야 한다.
    ("kakao_room_name", "카톡방 이름", "170px"),
]


def buckets(db: Session) -> List[dict]:
    """갈래별 인원. 탭에 건수를 띄운다 — 어디에 사람이 있는지 알아야 한다."""
    rows = db.execute(
        select(SourcingContact.bucket, func.count(), func.min(SourcingContact.position))
        .group_by(SourcingContact.bucket)
    ).all()
    out = [{"key": b, "label": b, "count": n, "pos": pos or 0} for b, n, pos in rows]
    return sorted(out, key=lambda x: (x["pos"], x["label"]))


def rows_of(db: Session, bucket: str) -> List[SourcingContact]:
    stmt = select(SourcingContact).order_by(SourcingContact.position, SourcingContact.id)
    if bucket:
        stmt = stmt.where(SourcingContact.bucket == bucket)
    return db.execute(stmt).scalars().all()


@router.get("/sourcing", response_class=HTMLResponse, include_in_schema=False)
def sourcing_page(request: Request, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user), tab: str = ""):
    tabs = buckets(db)
    # 아무 것도 고르지 않았으면 첫 갈래를 연다. 전체를 먼저 보여주면 갈래가
    # 나뉜 뜻이 사라진다.
    selected = tab if any(t["key"] == tab for t in tabs) else (
        tabs[0]["key"] if tabs and tab != "all" else "")
    ctx = base_ctx(request, db, user, active="sourcing")
    ctx.update({
        "tabs": tabs,
        "selected": selected,
        "columns": COLUMNS,
        "rows": rows_of(db, selected),
        "total": sum(t["count"] for t in tabs),
    })
    return templates.TemplateResponse("sourcing.html", ctx)


class SourcingIn(BaseModel):
    name: Optional[str] = None
    title: Optional[str] = None
    firm: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    assignee_name: Optional[str] = None
    requested_at: Optional[str] = None
    share_method: Optional[str] = None
    sectors: Optional[str] = None
    round_size: Optional[str] = None
    tips: Optional[str] = None
    memo: Optional[str] = None
    kakao_reply: Optional[str] = None
    call_note: Optional[str] = None
    kakao_room_name: Optional[str] = None


@router.patch("/api/sourcing/{row_id}")
def update_row(row_id: int, body: SourcingIn, db: Session = Depends(get_db),
               user: User = Depends(get_current_user)):
    """표에서 눌러 바로 고친다 — 다른 표와 같은 조작이다."""
    row = db.get(SourcingContact, row_id)
    if row is None:
        raise HTTPException(status_code=404, detail="찾을 수 없습니다")
    for field, value in body.model_dump(exclude_unset=True).items():
        if value is None:
            continue
        # 이름은 비울 수 없다 — 누구인지 모르는 줄이 남는다.
        if field == "name" and not value.strip():
            continue
        if field == "kakao_room_name" and value.strip() != (row.kakao_room_name or ""):
            # 이름이 바뀌었으면 예전 확인 결과는 다른 방 이야기다.
            row.room_verified = "unverified"
        setattr(row, field, value.strip() or None)
    db.commit()
    return {"ok": True}
