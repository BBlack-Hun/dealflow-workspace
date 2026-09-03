"""딜 소개의 번호 — **한 곳에서 만들고, 딜소개와 IR 이 같이 읽는다.**

딜소개 문구는 `1) …` `2) …` 로 나가고 투자사는 **그 번호로 기억해서** 답한다
("2번 자료 주세요"). 그래서 자료를 보낼 때도 같은 번호로 짚어 줘야 서로 같은
기업 이야기를 한다. 번호를 새로 매기면 받는 쪽은 자기 목록에서 찾다가 못 찾는다.

## 왜 한 곳인가

번호를 정하는 규칙은 하나다 — **딜 소개에서 고른 차례가 곧 번호.** 그 규칙이
쓰이는 자리는 셋인데, 셋이 따로 적혀 있으면 한쪽만 낡는다.

  · 나가는 문구의 `1) 2) 3)`            (`message_composer.compose_message`)
  · 회차에 남는 번호                     (`DealBatchCompany.position`)
  · 자료 전달의 `2번 기업 …`              (`company_list`)

앞의 둘은 `numbered()` 한 자리에서 나오고, 셋째는 그렇게 남은 번호를
`for_contact()` 로 **되읽는다.** 자료 전달은 번호를 만들지 않는다.

## 실제로 갈렸던 자리

되읽는 쪽이 "이 담당자에게 **마지막으로 나간 회차**" 를 봤다. 회차는 딜소개만
만드는 것이 아니라 리마인드·자료 전달·소싱 제안도 만든다.

  · 자료를 한 번 보내고 나면 그 회차가 마지막이 되어, 다음 자료 전달이
    **1 부터 다시** 매겨졌다(딜소개에서 2·3번이던 기업이 1·2번으로).
  · 리마인드를 한 통 보내면 기업이 없는 회차가 마지막이 되어, 번호가
    **통째로 사라졌다**.

그래서 되읽을 때 보는 것은 **번호를 붙여 내보낸 그 회차뿐**이다 — 기업 목록에
번호를 붙이는 발송은 딜 소개(`STAGE_DAY1`) 하나다(`compose_message` 가 그
단계에서만 번호를 붙인다).
"""
from __future__ import annotations

from typing import Dict, List, Sequence, Tuple

#: 딜 소개 발송의 잡 종류(`SendJob.kind`). 회차를 만드는 발송은 여럿이라,
#: 번호를 되읽을 때 어느 회차를 볼지 가리는 데 쓴다.
KIND_DEAL_INTRO = "deal_intro"


def numbered(items: Sequence) -> List[Tuple[int, object]]:
    """`(번호, 항목)` 짝 — **고른 차례가 곧 번호다.**

    나가는 문구의 `1) 2) 3)` 도, 회차에 남는 `position` 도 여기서 나온다.
    두 곳이 각자 세면 문구의 번호와 남은 번호가 갈리고, 그러면 다음에 자료를
    보낼 때 엉뚱한 기업을 짚는다.
    """
    return list(enumerate(items, start=1))


def for_contact(db, contact_id: int) -> Dict[int, int]:
    """이 담당자가 **딜 소개로 받은 마지막 회차**에서 각 기업이 몇 번이었는지.

    `{기업 id: 번호}`. 그런 회차가 없으면 빈 사전 — 번호를 지어내지 않는다.
    """
    from sqlalchemy import select

    from ..models import DealBatchCompany, SendItem, SendJob
    from .message_composer import STAGE_DAY1

    batch_id = db.execute(
        select(SendJob.batch_id)
        .join(SendItem, SendItem.job_id == SendJob.id)
        .where(SendItem.contact_id == contact_id,
               SendItem.status == "sent",
               # 기업 목록에 번호를 붙여 내보낸 발송은 딜 소개뿐이다. 리마인드·
               # 자료 전달·소싱 제안도 회차를 남기지만 번호를 정한 적이 없다.
               SendItem.stage == STAGE_DAY1,
               SendJob.kind == KIND_DEAL_INTRO,
               SendJob.batch_id.isnot(None))
        .order_by(SendItem.id.desc()).limit(1)
    ).scalar()
    if batch_id is None:
        return {}
    return {
        row.company_id: row.position
        for row in db.execute(
            select(DealBatchCompany).where(DealBatchCompany.batch_id == batch_id)
        ).scalars().all()
    }


def company_list(db, contact_id: int, companies) -> str:
    """'1번 기업 샘플애그' · 여럿이면 '1번 기업 샘플애그, 3번 기업 …'.

    번호는 **딜 소개에서 붙인 그 번호**다(`for_contact`). 고른 차례로 다시
    세지 않는다 — 자료를 요청받은 차례와 투자사가 기억하는 번호는 다르다.

    딜 소개에 없던 기업은 번호를 붙이지 않는다 — 없는 번호를 지어내면 받는
    쪽이 자기 목록에서 찾다가 못 찾는다.
    """
    positions = for_contact(db, contact_id)
    parts = []
    for company in companies:
        no = positions.get(company.id)
        parts.append(f"{no}번 기업 {company.name}" if no else company.name)
    return ", ".join(parts)
