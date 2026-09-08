"""보기(demo) 자료 — **`/setup` 의 시험 자리에서, 실을 진짜가 없을 때만.**

## 왜 이것이 필요한가

시험 자리는 "눌러서 실제로 어떤 글자가 나가는지 먼저 본다" 는 자리다. 그런데
기업 리마인드는 **그 달 IR 자료를 요청한 투자사가 한 곳도 없으면** 글을 짓지
않는다(`ir_kakao.compose` 가 `None` 을 낸다). 요청이 0곳인 것은 흔한 일이고,
특히 **발송기를 새 PC 에 처음 깔 때**가 그렇다 — 정작 시험이 필요한 그 순간에
단추를 눌러 볼 수가 없다. 그러면 그 자리를 만든 뜻이 사라진다.

미팅 후기도 같은 자리에 걸린다. 문구 자체는 요청 수를 안 읽지만
(`deals.review_message` 는 이름·직함·투자사 셋만 쓴다), **고를 미팅이 하나도
없으면** 고르개가 비어 단추가 서지 않는다.

## ★ 진짜가 있으면 진짜를 쓴다 — 여기로 떨어지는 것은 **없을 때뿐**이다

시험의 값어치는 실제 자료가 만드는 모양에 있다. 담당자 성함이 빈 줄, 이름에
괄호가 섞인 줄, 목록이 길어 두 통으로 나뉘는 글 — 지어낸 자료로는 그중 어느
것도 안 보인다. 그래서 부르는 쪽(`routers/setup.py`)은 **진짜로 먼저 지어 보고,
지어지지 않을 때만** 이 파일로 온다.

## ★ 가짜라는 것이 문구에 분명히 보여야 한다

시험방으로만 나가더라도 **진짜와 구별이 안 되면 사람이 헷갈린다.** 시험방에
쌓인 글을 나중에 열어 본 사람은 그것이 실제로 나간 글인지 지어낸 글인지 알
길이 없고, 지어낸 문장을 보고 "대표에게 이렇게 나갔구나" 로 읽는다.

**두 겹으로 드러낸다.** 한 겹이면 그 한 겹이 잘려 나갈 때 표시가 통째로
사라진다.

1. **맨 앞 한 줄**(`MARK`). 카톡에서 먼저 읽히는 자리다. 기업 리마인드는
   `ir_kakao.assemble(prefix=...)` 이 **머리말 앞**에 얹고, 미팅 후기는
   `marked()` 가 얹는다.
2. **이름 자체가 보기 이름**(`COMPANY`·`CONTACT`·`INVESTOR_*`). 글이 여러 통으로
   나뉘면 맨 앞 한 줄은 **첫 통에만** 실리는데(`ir_kakao.pack`), 둘째 통을 따로
   본 사람에게도 `보기기업` 은 그대로 보인다. 이름을 그럴듯하게 지으면 표시
   줄 하나에 전부를 건다.

이름을 `(주)한빛소프트` 처럼 있을 법하게 짓지 않는 까닭이 그것이다 — 있을 법한
이름은 **실재하는 회사와 겹칠 수도** 있다. 이 저장소는 공개다.

## 여기서 문구를 조립하지 않는다

기업 리마인드는 `ir_kakao.assemble` 을, 미팅 후기는 `deals.review_message` 를
그대로 지난다. 이 파일이 내는 것은 **줄과 이름뿐**이다 — 조립을 여기 다시
적으면 두 벌이 되고, 두 벌은 반드시 어긋난다. 그러면 보기 자료로 본 모양이
진짜 모양과 달라져, 시험이 거짓말을 하는 것을 막으려다 거짓말을 하게 된다.

## 실제 발송 길로 샐 수 없다

이 파일을 부르는 곳은 `routers/setup.py` 의 시험 잡 두 곳뿐이고, 그 잡은
`TEST_SEND_KIND` 로만 서고 시험방(`config.TEST_ROOM`)으로만 간다. 운영에는
시험방이 없어 그 자리 자체가 없다(`setup.test_tools_on`). 스타트업 화면은
여기를 부르지 않는다 — 요청이 0곳이면 여전히 **아무것도 만들지 않는다**
(#131 · #135: "빈 목록을 보내면 대표는 우리가 아무것도 안 한 줄로 읽는다").
검사가 그 둘을 못박는다(`tests/test_setup_test_tools.py`).
"""
from __future__ import annotations

from typing import List, Optional

from sqlalchemy.orm import Session

from ..models import User, VcContact
from . import ir_kakao, ir_mask
from . import message_composer as mc

#: 글 맨 앞에 얹는 한 줄. **이 한 줄이 가짜라는 첫 겹이다.**
#: 문장을 짧게 두는 까닭은 아래 진짜 문구가 어떤 모양인지 보러 온 자리이기
#: 때문이다 — 표시가 길면 정작 볼 것을 밀어낸다.
MARK = "[보기 자료] 실제 자료가 없어 지어낸 예시입니다 — 실제 발송이 아닙니다."

#: 보기 기업·대표. **이름 자체가 보기라고 말한다**(위 머리말 2번).
COMPANY = "보기기업"
CONTACT = "보기대표"

#: 보기 투자사 셋. 첫 글자가 서로 다르다 — 가려진 뒤에도(`ir_mask`) 세 줄이
#: 서로 다른 곳으로 보여야 실제 목록의 모양이 드러난다.
FIRMS = ("보기벤처스", "예시캐피탈", "가상인베스트먼트")

#: 요청 날짜로 쓸 일(日). 그 달 안의 서로 다른 날이면 된다 — 실물처럼 날짜가
#: 흩어져 있어야 정렬된 목록의 모양이 보인다.
DAYS = (3, 11, 22)

#: 보기 투자사 담당자 — 미팅 후기가 쓰는 값 셋(`deals._to_contact_view`).
INVESTOR_NAME = "보기담당"
INVESTOR_TITLE = "심사역"
INVESTOR_FIRM = "보기벤처스"


def marked(text: str) -> str:
    """글 맨 앞에 표시 줄을 얹는다.

    기업 리마인드는 이 함수를 쓰지 않는다 — 거기서는 표시가 **머리말보다 앞**에
    있어야 하고 통 나누기가 그 뒤에 오므로, 조립하는 자리
    (`ir_kakao.assemble`)가 `prefix` 로 받아 얹는다. 합쳐 놓고 나중에 자르면
    표시 줄이 통 경계에 걸린다.
    """
    return f"{MARK}\n{text}"


def startup_remind(db: Session, user: Optional[User],
                   month: str) -> ir_kakao.KakaoMessage:
    """보기 자료로 지은 **기업 리마인드 문구** 한 통.

    머리말은 **진짜와 같은 문구틀**에서 온다(`ir_kakao.head_body`) — 보러 온
    것이 그 머리말이기 때문이다. 지어내는 것은 기업 이름과 요청 목록뿐이다.

    투자사 이름은 진짜와 **같은 자리에서 가린다**(`ir_mask`). 지어낸 이름이라
    안 가려도 새지 않지만, 가리기까지가 이 문구의 모양이다 — 안 가리고 보여
    주면 "실제로는 이렇게 나가는구나" 를 틀리게 배운다.
    """
    lines: List[ir_kakao.Line] = [
        ir_kakao.Line(date=ir_kakao.day_label(f"{month}-{day:02d}"),
                      company=COMPANY, firm=ir_mask.mask_company(firm))
        for day, firm in zip(DAYS, FIRMS)
    ]
    # 머리말에 꽂을 상대. `ir_kakao.contact_of` 와 **같은 모양**이다 — 이름만
    # 주고 직함·투자사는 비운다(스타트업 명단에 그 칸 자체가 없다).
    return ir_kakao.assemble(db, user, month, [COMPANY], lines,
                             mc.ContactView(name=CONTACT), prefix=MARK)


def review_contact(user: User) -> VcContact:
    """보기 투자사 담당자 한 줄 — **DB 에 넣지 않는다.**

    `deals.review_message` 는 담당자에서 이름·직함·투자사만 읽고, 딜소개 이력을
    한 번 물어본다(`_has_history`). `id` 를 `0` 으로 둔 까닭이 그것이다 —
    자동 증가 키는 1부터라 어느 줄과도 안 맞고, 그래서 이력은 늘 '없음' 으로
    나온다. **처음 인사**가 붙는 쪽이고, 지어낸 사람이니 그것이 사실이다.

    `db.add` 를 하지 않으므로 이 줄은 어디에도 남지 않는다. 남기면 시험 한 번에
    명단이 한 줄씩 늘고, 그 줄이 언젠가 실제 발송 대상 목록에 선다.
    """
    return VcContact(id=0, user_id=user.id, name=INVESTOR_NAME,
                     title=INVESTOR_TITLE, firm=INVESTOR_FIRM)
