"""참고 자료 패널이 쓰는 값 — **어느 화면의 자료인가**를 한 곳에서 정한다.

화면 셋이 같은 패널(`_ref_panel.html`)을 쓴다: 투자사 관리 현황 · 투자컨설턴트 ·
스타트업 리마인드. 자료가 어느 화면에 붙는지는 `RefSheet.page` 한 칸이 정하는데,
그것을 꺼내 오는 질의는 화면마다 따로 적혀 있었다.

**그러면 조건 하나가 갈린다.** 실제로 화면이 둘일 때도 `is_active == 1`(지운 탭
감추기)과 `order_by(position, id)`(탭 순서)를 양쪽이 각자 들고 있었다 — 한쪽만
고치는 날 지운 탭이 그 화면에만 남거나 탭 순서가 화면마다 달라진다. 이 저장소가
반복해서 당한 부류다(좌측 메뉴 목록과 라우터 목록이 갈려 컨설턴트에게 다 열려
있던 일, 투자사 수가 화면마다 갈린 일). 화면이 셋이 되는 지금이 모을 자리다.

`page` 값은 그 화면의 주소 조각과 같다(`contacts` · `consulting` · `startup`).
자료를 고칠 권한도 그 사실을 그대로 읽는다(`routers/contacts.py` 의
`_editable_ref` 가 `/{page}` 를 열 수 있는 사람인지 본다) — 여기서 다른 이름을
지으면 그쪽 판정이 통째로 어긋난다.
"""
from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import RefSheet


def sheets(db: Session, page: str) -> list:
    """이 화면에 붙은 **살아 있는** 참고 자료. 탭에 그리는 순서 그대로.

    지운 탭은 감추기만 한 것이라(`is_active = 0`) 여기서 걸러야 화면에서 사라진다.
    """
    return db.execute(
        select(RefSheet)
        .where(RefSheet.is_active == 1, RefSheet.page == page)
        .order_by(RefSheet.position, RefSheet.id)
    ).scalars().all()


def panel_ctx(db: Session, page: str, ref) -> dict:
    """탭 목록 + 지금 펼친 자료 + 그 내용.

    `ref` 는 주소에서 온 값이라 글자일 수도, 없을 수도, 남의 화면 자료 번호일
    수도 있다 — **이미 가져온 탭 목록 안에서만** 찾는다. 번호로 다시 조회하면
    다른 화면의 자료가 이 화면에 열린다.
    """
    rows = sheets(db, page)
    picked = next((s for s in rows if str(s.id) == str(ref)), None)
    return {
        "ref_sheets": rows,
        "ref": picked,
        # 펼친 자료가 없으면 빈 dict — 화면이 `ref_content.body` 를 읽어도
        # 죽지 않는다(`None` 이면 그 자리에서 터진다).
        "ref_content": json.loads(picked.content_json or "{}") if picked else {},
    }
