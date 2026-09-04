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
  · 화면의 [보낼 자료] 목록에 적히는 번호   (`numbered_companies` → 화면 둘)

되읽는 쪽 둘은 **번호 오름차순**으로 늘어선다(자료를 그 차례로 붙인다).
만드는 쪽(`numbered`)은 여전히 고른 차례가 곧 번호다 — 그건 다른 일이다.

앞의 둘은 `numbered()` 한 자리에서 나오고, 뒤의 둘은 그렇게 남은 번호를
`for_contact()` 로 **되읽는다.** 자료 전달은 번호를 만들지 않는다.

뒤의 둘이 한 함수(`numbered_companies`)를 같이 쓰는 것도 같은 이유다. 자료는
사람이 PC 카톡에 손으로 붙이는데 **화면에 적힌 번호가 곧 붙이는 차례**라,
화면이 따로 세면 문구가 짚은 것과 다른 자료가 붙는다.

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

from typing import Dict, List, Optional, Sequence, Tuple

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


def numbered_companies(db, contact_id: int,
                       companies) -> List[Tuple[Optional[int], object]]:
    """`(번호, 기업)` 짝 — **번호 오름차순**, 번호가 없으면 `None`.

    나가는 문구(`company_list`)와 화면의 [보낼 자료] 목록이 **여기 하나만
    본다.** 화면이 따로 세면 목록에는 `2번`, 문구에는 `3번 기업 …` 이 되어
    사람이 자료를 엉뚱한 차례로 붙인다 — 자료를 손으로 첨부하는 지금은
    화면에 적힌 번호가 곧 붙이는 차례다.

    ## 왜 번호순인가

    예전에는 **고른 차례**로 두었다(자료를 청한 차례). 그런데 이 목록을 보는
    사람이 하는 일은 **번호대로 파일을 붙이는 것**이라, 목록이 `3번 · 1번 ·
    2번` 으로 서 있으면 붙일 때마다 눈으로 되짚어야 한다. 자료가 여럿일수록
    틀리기 쉽고, 틀리면 받는 쪽은 자기가 청한 번호와 다른 자료를 받는다.

    **문구도 같이 바뀐다** — 문구를 짓는 `company_list` 가 이 함수를 그대로
    쓰기 때문이다. 목록만 번호순이고 문구가 고른 차례면 `1번, 3번` 을 보며
    `3번, 1번` 차례로 붙이게 된다. 한 함수에서 나오니 갈릴 자리가 없다.

    **딜 소개의 번호 매기기는 그대로다**(`numbered` — 고른 차례가 곧 번호).
    그건 번호를 **만드는** 자리이고 여기는 만들어진 번호를 **되읽는** 자리다.

    ## 번호 없는 기업은 끝에

    지난 딜 소개에 없던 기업은 번호가 없다. 번호가 붙은 줄 사이에 끼우면
    오름차순으로 훑던 눈이 끊긴다 — 붙이는 차례를 세는 것이 이 목록의 일이라,
    셀 수 있는 것을 먼저 두고 못 세는 것을 뒤에 둔다. 그들끼리는 **고른 차례**
    그대로다(정렬이 안정적이라 저절로 그렇게 된다).
    """
    positions = for_contact(db, contact_id)
    pairs = [(positions.get(company.id), company) for company in companies]
    # 번호 있는 것 먼저(오름차순) · 없는 것은 뒤에, 둘 다 고른 차례를 지킨다.
    return sorted(pairs, key=lambda pair: (pair[0] is None, pair[0] or 0))


def company_list(db, contact_id: int, companies) -> str:
    """'1번 기업 샘플애그' · 여럿이면 '1번 기업 샘플애그, 3번 기업 …'.

    번호는 **딜 소개에서 붙인 그 번호**다(`for_contact`). 고른 차례로 다시
    세지 않는다 — 자료를 요청받은 차례와 투자사가 기억하는 번호는 다르다.

    짚는 차례는 **번호 오름차순**이다 — 화면의 [보낼 자료] 목록과 같은 함수에서
    나오므로(`numbered_companies`) 둘이 갈릴 자리가 없다.

    딜 소개에 없던 기업은 번호를 붙이지 않는다 — 없는 번호를 지어내면 받는
    쪽이 자기 목록에서 찾다가 못 찾는다.
    """
    return ", ".join(
        f"{no}번 기업 {company.name}" if no else company.name
        for no, company in numbered_companies(db, contact_id, companies)
    )
