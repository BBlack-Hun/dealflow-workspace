"""문구를 **누가 무엇으로** 쓰는가 — 고르는 규칙이 사는 한 곳.

팀 기본 문구(`user_id IS NULL`)는 한 종류에 여러 개 둘 수 있다. 예전에는
그중 `.first()` 로 아무거나 집었는데, 정렬을 주지 않은 조회의 순서는 DB 가
정하는 것이라 **같은 회차에서 사람마다 다른 문구가 나갈 수 있었다**. 무엇이
나갔는지 뒤에서 알 방법도 없다.

그래서 고르는 일을 사람에게 돌려준다. 사용자는 문구 화면에서 한 번 고르고
(`TemplateChoice`), 발송은 그 선택을 따른다. 고치는 것은 여전히 관리자만이다
— 고르는 것과 고치는 것은 다른 권한이다.

규칙이 딜소개(`routers/deals.py`)와 딜 소싱(`services/sourcing_msg.py`)에
따로 적히면 언젠가 어긋나고, 그러면 같은 사람이 화면마다 다른 문구를 받는다.
양쪽이 여기를 부른다.
"""
from __future__ import annotations

from typing import List, Optional

from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from ..models import MessageTemplate, TemplateChoice

#: 문구 `name` 이 **갈래**를 뜻하는 종류. 딜 소싱은 갈래마다 호칭·전달 개수·
#: 찾는 범위가 달라, 이름이 다르면 알아보라고 붙인 딱지가 아니라 아예 다른
#: 문구다(`services/sourcing_msg.py`). 그래서 갈래끼리는 서로 겨루지 않고
#: 갈래 **안에서만** 고른다. 나머지 종류의 이름('기본 인사' · '연말 인사')은
#: 사람이 알아보려고 붙인 것이라 한 자리를 놓고 함께 겨룬다.
NAME_IS_A_BUCKET = {"sourcing_intro"}


def variant_of(kind: str, name: Optional[str]) -> str:
    """이 문구가 서 있는 자리(갈래) 이름. 갈래가 없는 종류는 늘 빈 문자열."""
    if kind not in NAME_IS_A_BUCKET:
        return ""
    return (name or "").strip()


def candidates(db: Session, user_id: int, kind: str,
               variant: str = "") -> List[MessageTemplate]:
    """이 사람이 이 자리에 쓸 수 있는 문구들 — 팀 기본 + 내 것, 살아 있는 것만.

    id 순으로 준다. 정렬을 주지 않으면 같은 질문에 다른 순서가 돌아와
    미리보기와 실제 발송이 갈릴 수 있다.
    """
    variant = variant_of(kind, variant)
    stmt = (
        select(MessageTemplate)
        .where(MessageTemplate.kind == kind,
               MessageTemplate.is_active == 1,
               or_(MessageTemplate.user_id.is_(None),
                   MessageTemplate.user_id == user_id))
        .order_by(MessageTemplate.id)
    )
    if kind in NAME_IS_A_BUCKET:
        # 갈래가 정해졌으면 그 갈래만, 갈래가 없으면 이름 없는 문구만.
        # 여기서 이름을 안 보면 '대표님·5개사' 문구가 개인 참여 심사역께 간다.
        stmt = stmt.where(MessageTemplate.name == variant if variant
                          else MessageTemplate.name.is_(None))
    return list(db.execute(stmt).scalars().all())


def chosen_id(db: Session, user_id: int, kind: str, variant: str = "") -> Optional[int]:
    """이 사람이 이 자리에 골라 둔 문구 번호(고르지 않았으면 None)."""
    return db.execute(
        select(TemplateChoice.template_id)
        .where(TemplateChoice.user_id == user_id,
               TemplateChoice.kind == kind,
               TemplateChoice.variant == variant_of(kind, variant))
    ).scalars().first()


def pick(db: Session, user_id: int, kind: str,
         variant: str = "") -> Optional[MessageTemplate]:
    """이 사람이 이 자리에 쓸 문구.

    **고른 것 > 내 것 > 팀 것(하나뿐일 때) > 없음(부르는 쪽 폴백)** 순이다.

    - 고른 것이 먼저인 이유: 그것이 이 기능의 전부다. 골라 뒀는데 다른 것이
      나가면 고른 뜻이 없다.
    - 내 것이 팀 것보다 앞인 이유: 예전부터 그랬고(개인 문구는 팀 기본을
      덮는다), 자기가 만든 것을 두고 팀 것이 나가면 왜 만들었는지 알 수 없다.
    """
    rows = candidates(db, user_id, kind, variant)
    picked = chosen_id(db, user_id, kind, variant)
    for t in rows:
        # 고른 것이 지워졌거나 꺼졌으면 후보에 없다 — 없는 것으로 보고 넘어간다.
        if t.id == picked:
            return t

    mine = [t for t in rows if t.user_id == user_id]
    if mine:
        # 내 문구가 여럿이면 가장 먼저 만든 것. 내 것이라 남과 어긋날 일은
        # 없지만, 순서를 고정해 두지 않으면 미리보기와 실제 발송이 갈린다.
        return mine[0]

    team = [t for t in rows if t.user_id is None]
    if len(team) == 1:
        return team[0]

    # 팀 기본이 여럿인데 아무것도 안 골랐다 → **아무것도 돌려주지 않는다.**
    #
    # 여기서 코드가 하나를 집으면 그것은 관리자가 정한 것이 아니라 조회
    # 순서가 정한 것이다. 순서는 언제든 흔들리고(문구를 지웠다 다시 만들면
    # 바뀐다), 그러면 같은 회차에서 사람마다 다른 문구가 나간다 — 고쳐야 했던
    # 바로 그 동작이다. 부르는 쪽 폴백은 코드에 적힌 한 문장이라 누구에게나
    # 같고, 문구 화면에는 "골라 주세요" 가 떠 있다.
    return None


def set_choice(db: Session, user_id: int, kind: str, template_id: int,
               variant: str = "") -> None:
    """이 자리에 쓸 문구를 정한다. 한 자리에 하나뿐이라 있으면 갈아 끼운다."""
    variant = variant_of(kind, variant)
    row = db.execute(
        select(TemplateChoice)
        .where(TemplateChoice.user_id == user_id,
               TemplateChoice.kind == kind,
               TemplateChoice.variant == variant)
    ).scalars().first()
    if row is None:
        db.add(TemplateChoice(user_id=user_id, kind=kind, variant=variant,
                              template_id=template_id))
    else:
        row.template_id = template_id


def clear_choice(db: Session, user_id: int, kind: str, variant: str = "") -> None:
    """선택을 지운다 — 다시 기본 규칙(내 것 > 팀 것)으로 돌아간다."""
    db.execute(
        delete(TemplateChoice)
        .where(TemplateChoice.user_id == user_id,
               TemplateChoice.kind == kind,
               TemplateChoice.variant == variant_of(kind, variant))
    )


def forget_template(db: Session, template_id: int) -> None:
    """이 문구를 고른 사람들의 선택을 거둔다.

    문구를 지우기 **전에** 부른다. 선택이 남아 있으면 없는 문구를 가리킨 채
    남고(외래키가 켜져 있으면 삭제 자체가 막힌다), 그 사람은 골라 둔 줄 알지만
    실제로는 다른 문구가 나간다.
    """
    db.execute(delete(TemplateChoice).where(TemplateChoice.template_id == template_id))


def prune(db: Session, user_id: int) -> int:
    """죽은 선택을 치운다 — 지워졌거나 꺼졌거나 남의 개인 문구가 된 것.

    문구를 지우는 길이 화면 말고도 있고(시드 스크립트·손질), 비활성으로만
    돌려놓는 경우도 있다. 읽을 때마다 조용히 무시하기만 하면 선택이 남은 채
    쌓여, 화면에는 "고름" 인데 실제로는 다른 문구가 나가는 상태가 이어진다.
    문구 화면을 열 때 한 번 훑어 실제 상태와 맞춘다.
    """
    rows = db.execute(
        select(TemplateChoice).where(TemplateChoice.user_id == user_id)
    ).scalars().all()
    dead = 0
    for choice in rows:
        t = db.get(MessageTemplate, choice.template_id)
        alive = (t is not None and t.is_active == 1 and t.kind == choice.kind
                 and t.user_id in (None, user_id)
                 and variant_of(t.kind, t.name) == choice.variant)
        if not alive:
            db.delete(choice)
            dead += 1
    return dead
