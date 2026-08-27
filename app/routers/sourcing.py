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
from ..models import SendItem, SourcingContact, User
from ..services import sourcing_link
from ..ui import base_ctx

router = APIRouter(tags=["sourcing"])

# 표 컬럼 — 원본 시트 순서 그대로. 쓰던 사람이 같은 자리에서 같은 것을 찾는다.
#
# 네 번째 값은 **머리글에 필터를 세울 칸인가**. 여기 한 곳에서만 정한다 —
# 전에는 템플릿이 `field in ('assignee_name', 'sectors', 'round_size')` 라는 같은
# 목록을 머리글과 행에 나눠 적고 있어서, 한쪽만 고치면 선언은 있는데 행이 값을
# 안 싣는(=열어도 늘 빈 목록) 필터가 조용히 생긴다.
#
# 거는 기준은 **고를 만한 값이 몇 가지로 모이는가**다(실데이터 39행 기준):
#   담당자 5종 · 투자분야 6종 · 참여 요청일 12종 · 라운드 사이즈 13종 ·
#   직함 18종                                        → 건다
#   이름 35 · 회사 29 · 휴대폰 29 · 이메일 26종      → 줄마다 달라 고를 것이 없다
#   메모(자유 문장, 최대 75자)                       → 목록 한 줄에 담기지 않는다
#   카톡방 이름(39행 모두 빈칸, 채우면 방 제목이라
#               역시 줄마다 다르다)                  → 지금도 앞으로도 거를 값이 없다
#
# 폭은 **이름이 아니라 단추**에 맞춘다. 필터가 하나뿐인 칸은 filters.js 가 이름
# 글자를 지우고 `담당자 ▾` 단추를 그 자리에 세우는데, 단추는 ` ▾` 와 자기
# padding·테두리만큼 이름보다 넓다 — 담당자(72px)가 그래서 두 줄로 접혀 있었다.
COLUMNS = [
    ("requested_at", "참여 요청일", "124px", True),
    ("name", "이름", "96px", False),
    ("assignee_name", "담당자", "100px", True),
    ("phone", "휴대폰", "116px", False),
    ("title", "직함", "88px", True),
    ("email", "이메일 주소", "170px", False),
    ("firm", "회사", "150px", False),
    ("sectors", "투자분야", "120px", True),
    ("round_size", "라운드 사이즈", "134px", True),
    ("memo", "메모", "", False),
    # 여기서 딜 소싱 제안을 보낸다 — 방 이름이 없으면 보낼 길이 없다.
    # 발송 화면(딜 제안 관리)에서 고를 수 있으려면 이 칸이 먼저 차야 한다.
    ("kakao_room_name", "카톡방 이름", "170px", False),
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
    rows = rows_of(db, selected)
    ctx = base_ctx(request, db, user, active="sourcing")
    # 투자사 관리 현황에서 이미 방을 연결해 둔 사람이면 다시 적을 이유가 없다.
    linked = sourcing_link.linked_rooms(db, rows)
    ctx.update({
        "linked_rooms": linked,
        "tabs": tabs,
        "selected": selected,
        "columns": COLUMNS,
        "rows": rows,
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


@router.post("/api/sourcing")
def add_row(body: SourcingIn, bucket: str = "",
            db: Session = Depends(get_db),
            user: User = Depends(get_current_user)):
    """갈래에 사람을 새로 넣는다.

    지금까지는 시트를 다시 올려야만 늘릴 수 있었다 — 전화로 한 명 승낙받고
    바로 적을 곳이 없어서, 메모지에 적어 뒀다가 나중에 시트에 옮겼다.

    **갈래는 반드시 있어야 한다.** 갈래가 곧 문구라, 갈래 없는 줄은 어떤
    문구로 보낼지 정할 수 없다.
    """
    name = (body.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="이름을 입력하세요")
    target = (bucket or "").strip()
    if not target:
        raise HTTPException(status_code=400, detail="갈래를 고르세요")

    # 새 줄은 그 갈래의 맨 아래로. 시트의 번호를 사람이 매번 세지 않아도 되게.
    last = db.execute(
        select(func.max(SourcingContact.position))
        .where(SourcingContact.bucket == target)
    ).scalar() or 0
    row = SourcingContact(bucket=target, position=last + 1, name=name)
    for field, value in body.model_dump(exclude_unset=True).items():
        if field != "name" and value:
            setattr(row, field, value.strip() or None)
    db.add(row)
    db.commit()
    return {"id": row.id, "bucket": target}


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


@router.delete("/api/sourcing/{row_id}")
def delete_row(row_id: int, db: Session = Depends(get_db),
               user: User = Depends(get_current_user)):
    """명단에서 한 줄을 뺀다.

    넣는 길만 있고 빼는 길이 없었다 — 전화로 급히 적다가 이름을 잘못 넣거나
    같은 사람을 두 번 넣어도 시트를 통째로 다시 올리는 것 말고는 방법이
    없었다(`scripts/import_sourcing.py` 는 갈래를 통째로 갈아엎는다).

    **지우는 것은 그 갈래의 그 줄 하나다.** 같은 사람이 여러 갈래에 들어가
    있으면 각각이 다른 줄이라(`SourcingContact` 주석 참고) 나머지는 남는다.
    이름으로 싸잡아 지우면 "시리즈 A 에서만 빼려고 눌렀는데 M&A 에서도
    사라지는" 일이 된다.

    **주인 검사는 하지 않는다 — 이 표에는 주인이 없다.**
    `sourcing_contacts` 에는 `user_id` 칸이 아예 없다. 소싱 명단은 IR 기업현황
    과 같은 **팀 공용**이라(발송도 담당자로 거르지 않는다 —
    `routers/deals.py` 의 `_load_recipients`), 여기서 볼 수 있는 경계는
    **로그인했는가** 하나뿐이고 그것은 위의 추가·수정과 똑같다.
    투자컨설턴트는 이 주소에 닿기 전에 끊긴다 — 역할 판정은 `app/main.py`
    미들웨어 한 곳에서만 한다(`deps.CONSULTANT_PATHS` 에 소싱이 없다).
    """
    row = db.get(SourcingContact, row_id)
    if row is None:
        raise HTTPException(status_code=404, detail="찾을 수 없습니다")

    # 딸린 것: 이 사람에게 보낸 발송 이력(`send_items.sourcing_contact_id`).
    #
    # **보낸 이력이 있으면 지우지 않는다.** 발송 건은 이 줄을 번호로 가리키고,
    # 화면과 기록에 뜨는 받는 사람 이름은 그 번호를 따라가 읽는다
    # (`models.py` 의 `SendItem.recipient_name`). 그래서 그냥 지우면:
    #   · 운영 DB — 이 칸에는 외래키가 서 있지 않다(alembic 0029 가 그냥
    #     Integer 로 붙였다). 막히지 않고 **조용히 넘어가고**, 발송 건은 없는
    #     번호를 가리킨 채 남아 "누구에게 보냈나" 가 빈칸이 된다.
    #   · 테스트 DB — 모델대로 외래키가 서 있어 같은 코드가 IntegrityError 로
    #     터진다. 한쪽은 넘어가고 한쪽은 500 인, 두 곳의 결과가 갈리는 상태다.
    # 이력까지 같이 지우는 길도 있지만, 발송 이력은 "누구에게 언제 보냈나" 의
    # 근거라 명단 한 줄보다 무겁다. 그래서 **막는다** — 계정 삭제가
    # `AgentDevice` 때문에 막혔던 것과 같은 자리이고, IR 기업현황도 같은
    # 이유로 같은 답을 냈다(`routers/companies.py` 의 `delete_company`).
    # 잘못 넣은 줄은 아직 아무에게도 안 보낸 줄이라 이 문에 걸리지 않는다.
    sent = db.execute(
        select(func.count()).select_from(SendItem)
        .where(SendItem.sourcing_contact_id == row_id)
    ).scalar_one()
    if sent:
        raise HTTPException(
            status_code=400,
            detail=f"이미 {sent}건을 보낸 사람이라 삭제할 수 없습니다 — "
                   "발송 이력이 이 줄을 가리킵니다. 더 보내지 않으려면 "
                   "카톡방 이름을 비워주세요(방이 없으면 발송이 거부됩니다).",
        )

    db.delete(row)
    db.commit()
    return {"deleted": row_id}
