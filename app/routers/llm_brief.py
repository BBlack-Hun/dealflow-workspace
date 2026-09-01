"""맞추기용 자료 꺼내기 · 번호를 이름으로 되돌리기.

**화면 단추와 API 는 같은 주소다.** 발송 화면의 [자료 내려받기] 는 아래
`/api/llm-brief.json` 을 그대로 여는 링크이고, [화면에서 보기] 도 같은 곳을
부른다. 화면용 함수를 따로 두면 한쪽이 낡는다 — 이 저장소가 반복해 당한
사고다(좌측 메뉴 목록과 라우터 목록이 갈려 컨설턴트에게 다 열려 있던 일,
투자사 수가 화면마다 117명·123명으로 갈린 일). 만드는 일은 전부
`services/llm_brief.py` 에 있고 여기는 그것을 부르기만 한다.

누가 받을 수 있는가 — **관리자와 팀원.** 투자컨설턴트는 안 된다.
투자컨설턴트는 딜 소개를 보내지도, 담당 투자사를 갖지도 않는다
(`deps.sends_deals`). 그 계정에 투자사의 선호·메모가 통째로 나가는 것은
자기 화면 하나만 쓰는 계정에 줄 이유가 없는 자료다. **따로 막지 않는다** —
`deps.CONSULTANT_PATHS` 가 허용 목록이라 여기 적지 않은 새 주소는 기본으로
막힌다. 라우터마다 검사를 흩뿌리면 다음 라우터에서 또 잊는다.
(`tests/test_consultant_access.py` 가 등록된 라우트를 통째로 훑어 확인하고,
`tests/test_llm_brief.py` 가 이 두 주소를 이름으로 못 박는다.)
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_current_user
from ..models import User
from ..services import llm_brief

router = APIRouter(tags=["llm-brief"])


@router.get("/api/llm-brief.json")
def brief_json(db: Session = Depends(get_db),
               user: User = Depends(get_current_user)) -> Response:
    """맞추는 데 쓸 자료 — 투자사는 번호로, IR 기업은 이름으로.

    **줄을 나눠 내보낸다**(`indent=2`). 한 줄로 뭉치면 더 짧지만, 이 자료는
    앱 밖으로 나가는 것이라 **내보내기 전에 사람이 눈으로 훑어** 이름이
    섞이지 않았는지 확인할 수 있어야 한다. 그 확인이 이 기능에서 가장
    중요한 동작이므로 읽기 쉬운 쪽을 고른다.
    """
    body = json.dumps(llm_brief.brief(db, user), ensure_ascii=False, indent=2)
    return Response(content=body, media_type="application/json; charset=utf-8")


class ResolveIn(BaseModel):
    # LLM 의 답을 **통째로** 붙여 넣는다. 번호만 골라 적게 하면 옮기다 틀린다.
    text: str = ""


@router.post("/api/llm-brief/resolve")
def resolve_refs(payload: ResolveIn, db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)) -> dict:
    """`V-31` 로 답해 온 것을 앱 안에서 이름으로 되돌린다.

    번호로 내보내는 기능은 되돌리는 길이 없으면 반쪽이다. **앱 안에서만**
    이름이 붙는 자리라, 찾는 범위는 자료를 꺼낼 때와 같다
    (`services/llm_brief.resolve` 참고).
    """
    return llm_brief.resolve(db, user, payload.text)
