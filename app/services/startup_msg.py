"""스타트업에 **매월 보내는 리마인드 문구** — 짓는 자리는 여기 하나다.

## 무엇이 없었나

문구는 이미 있었다 — `startup_sms`(`딜 제안 문구` 화면의 **기업 리마인드 —
문자**). 그런데 **그 문구를 짓는 코드가 한 줄도 없었다.** 저장소 전체에서
`startup_sms` 가 나오는 곳은 종류를 등록한 한 줄과 시드 한 줄뿐이었다.
즉 지금까지는 사람이 문구 화면에서 글을 복사해 손으로 보냈다.

손으로 복사하면 `{담당자명}` 같은 자리를 사람이 눈으로 갈아 끼운다. 그러면
갈아 끼우는 것을 잊은 문구가 그대로 나가고(이 저장소는 `{자료링크}` 가 글자
그대로 나간 적이 있다), 문구를 고쳐도 복사해 둔 쪽은 안 바뀐다.

## 왜 화면이 아니라 함수인가

지금 이 함수를 부르는 곳은 `/setup` 의 **시험용** 자리 하나다
(`routers/setup.py: test_startup_remind`). 시험방으로 한 통 보내 **문구가
어떤 모양으로 나가는지** 눈으로 보는 자리다.

명단 전체에 월말 리마인드를 실제로 돌리는 길은 **아직 없다.** 그건 대상
고르기·중복 방지·이력 남기기가 따라붙는 별개의 일이다. 다만 그 길을 낼 때
문구 짓는 일을 **다시 짜지 않아도 되게** 여기 빼 둔다 — 시험 화면 안에 묻어
두면 실전 길이 제 나름대로 또 짓고, 두 벌은 반드시 어긋난다(`template_pick`
머리말이 딜소개와 딜 소싱을 한 곳으로 모은 것과 같은 자리, 같은 이유).

## 문구틀의 어느 자리가 채워지나  ★

`message_composer.render_template` 이 바꿔치기하는 자리는 여덟이고, 그것은
**투자사에게 보내는 문구**를 두고 만든 목록이다. 받는 쪽이 스타트업이면
맞는 자리와 안 맞는 자리가 갈린다.

    {담당자명}  ← 기업 쪽 연락 담당자(`IrCompany.contact_name`)      채워진다
    {기업명}    ← 그 기업 이름(`IrCompany.name`)                     채워진다
    {직함}      ← 없다 → 존칭만 '님'                                 아래 참고
    {투자사}    ← 없다 → 빈칸                                        아래 참고
    {개수}·{기업목록}·{자료링크}·{ir_drive_url}                       빈칸

### `{직함}` — **'님' 이다. '대표' 를 지어 넣지 않는다.**

스타트업 명단에는 **직함 칸이 없다.** 있는 것은 성함·연락처·이메일뿐이다
(`models.IrCompany` 의 `contact_name`/`contact_phone`/`contact_email`).
그래서 `{직함}` 은 직함이 비었을 때의 **이미 있는 규칙**을 그대로 탄다 —
`honorific_title("")` 이 '님' 을 주고, `_fix_honorific` 이 앞 공백을 지워
`홍길동 {직함}` 이 `홍길동님` 이 된다.

딜 소싱은 이 자리에 '대표'/'심사역' 을 채워 넣는다(`sourcing_msg.honorific`).
**여기서는 따라 하지 않는다.** 소싱 쪽은 갈래 이름이 "그 사람이 투자사
대표다" 라고 말해 주는 **자료**지만, 스타트업 명단에는 그 사람이 대표라고
말해 주는 칸이 없다. 없는 것을 '대표' 로 채우면 재무 담당자에게 대표님이
나가고, 자료가 없으니 **시험을 해도 그 틀림이 드러나지 않는다.**

지어내지 않으면 대신 시험에서 **보인다**: `홍길동님` 이 떴는데 `홍길동
대표님` 을 원했다면, 문구틀에 '대표님' 을 글자로 적으면 된다 — 시드 문구가
이미 그렇게 적혀 있다(`안녕하세요 {담당자명} 대표님.`).

### `{투자사}` — **빈칸이다.**

받는 쪽이 스타트업이라 투자사가 없다. 기업 이름을 여기 넣는 길도 있지만
그러면 `{투자사}에서 검토 요청이…` 같은 문구가 **그 기업 이름으로** 나간다.
기업 이름을 부를 자리는 `{기업명}` 으로 따로 있다.

빼지 않고 빈칸으로 두는 것은 `{자료링크}` 와 같은 이유다 — 바꿔치기 목록에서
빼면 모르는 `{…}` 로 남아 **글자 그대로** 카톡방에 나간다.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from ..models import IrCompany, User
from . import message_composer as mc
from . import template_pick

#: 이 문구의 종류. 화면 이름은 `기업 리마인드 — 문자`
#: (`routers/templates_crud.py: KINDS`).
KIND = "startup_sms"


def body_for(db: Session, user: User) -> Optional[str]:
    """이 사람이 쓸 문구의 **원문**. 없거나 비어 있으면 `None`.

    무엇을 쓸지(고른 것 > 내 것 > 팀 것)는 `template_pick` 이 정한다. 딜소개·
    딜 소싱과 같은 곳을 읽어야 같은 사람이 화면마다 다른 문구를 받지 않는다.

    **뼈대(폴백)를 두지 않는다.** 딜소개는 문구가 없어도 코드에 적힌 한 문장을
    내보내는데, 그건 회차가 이미 잡혀 있어 "안 나가는 것" 이 더 나쁘기 때문이다.
    여기는 사람이 눌러야 나가는 자리라, 문구가 없으면 **없다고 말하는 편**이
    맞다 — 코드에 적힌 문장을 대신 내보내면 그것이 팀이 정한 문구인 줄 안다.
    """
    found = template_pick.pick(db, user.id, KIND)
    body = (found.body if found else "") or ""
    return body if body.strip() else None


def contact_of(company: IrCompany) -> mc.ContactView:
    """문구틀에 꽂을 상대 — **기업 쪽 연락 담당자**다.

    `title` 도 `firm` 도 주지 않는다. 무엇이 왜 비는지는 이 파일 머리말에 있다.
    빈 채로 두면 `render_template` 이 이미 정해 둔 길을 탄다.
    """
    return mc.ContactView(name=(company.contact_name or "").strip())


def compose(db: Session, user: User, company: IrCompany) -> Optional[str]:
    """이 기업에 보낼 월말 리마인드 문구 **완성본**. 문구틀이 없으면 `None`.

    합치지 않고 **바꿔치기만** 한다. 딜소개는 인사말 + 안내문 + 기업 목록을
    쌓아 올리지만(`compose_message`), 이 문구는 인사부터 맺음까지 한 덩이로
    적혀 있다 — 시드 문구가 `안녕하세요 …` 로 시작해 `문의드립니다.` 로 끝난다.
    인사말을 또 얹으면 인사가 두 번 나간다(0025 가 고친 그 사고다).
    """
    body = body_for(db, user)
    if body is None:
        return None
    return mc.render_template(body, contact_of(company),
                              company_name=(company.name or "").strip()).strip()
