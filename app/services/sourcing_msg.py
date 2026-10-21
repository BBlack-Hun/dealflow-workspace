"""딜 소싱 제안 문구 — 갈래마다 다른 초대장.

딜소개(우리가 고른 기업을 보여 주는 것)와는 부탁하는 내용이 다르다. 여기서는
**당신이 검토하다 뺀 딜을 우리에게 달라**고 청한다. 그래서 갈래마다
세 가지가 갈린다:

  호칭   — 직함이 비어 있을 때 '대표님' 인가 '심사역님' 인가
  개수   — 대표는 5개사, 개인 참여 심사역은 2개사
  범위   — 시리즈 A 이상 갈래와 M&A·후속 갈래가 찾는 딜이 다르다

이 세 가지가 틀리면 문구 자체가 결례가 된다("2개사만 주세요"를 대표께 보내는
식). 그래서 갈래를 문구의 1급 입력으로 둔다.

실제로 나가는 문구(딜 수신 메일 주소가 들어간 원본 스크립트)는 **DB 에만**
있다 — `scripts/import_sourcing_scripts.py` 가 원본 시트에서 넣는다.
여기 있는 것은 그 시드가 없을 때 쓰는 뼈대다.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy.orm import Session

from .. import clock
from ..models import User
from . import template_pick

#: 이 종류의 템플릿은 갈래(`name`)마다 하나씩 있다.
#: 갈래가 곧 자리라는 사실은 `template_pick.NAME_IS_A_BUCKET` 에 적혀 있다.
KIND = "sourcing_intro"

#: **월간 리마인드** — 이미 참여한 분께 이 달 딜을 청하는 문구. 처음 안내
#: (`KIND`)와 부탁하는 말이 다르다(참여 방법이 아니라 "이번 달 것을 보내 달라").
#:
#: 갈래마다 하나씩인 것도 처음 안내와 같다(`template_pick.NAME_IS_A_BUCKET`) —
#: 첫 줄이 `Series A 이상 딜 네트워크…` 처럼 갈래를 부른다.
#:
#: **이름을 바꾸지 않는다.** 자동 리마인드(#277)가 같은 종류 이름으로 같은
#: 저장 문구를 읽는다 — 손으로 보내는 것과 저절로 나가는 것이 한 문구다.
REMIND_KIND = "sourcing_remind"

#: **Series A 딜 공유** — 시리즈 A 갈래 심사역께 `Series A 이상 딜 소싱` 탭의 받은
#: 딜을 소개하는 글. 글을 짓고 누가 무엇을 받았는지 적는 일은
#: `services/series_a_share.py` 가 한다(이름도 거기서 이 값을 쓴다). 여기 두는
#: 까닭은 [보낼 문구] 고르개(`TOPICS` · `topic_of`)가 이 파일에 있어서다 — 그
#: 파일이 이 파일을 부르므로 거꾸로는 못 부른다.
SHARE_KIND = "sourcing_deal_share"

#: 딜 소싱 제안 탭의 [보낼 문구] — 순서가 곧 화면의 차례다.
TOPICS = (KIND, REMIND_KIND, SHARE_KIND)

#: 문구 속 이 달. 리마인드는 "10월에 공유해 주실 딜은…" 처럼 달을 말한다.
#: 저장된 문구(운영자가 `/templates` 에서 고친 것 포함)에도 같은 자리가 채워진다
#: — 채우는 곳은 `fill_month` 하나다.
MONTH_TOKEN = "{월}"

# 갈래 이름에 들어 있는 말로 성격을 읽는다. 시트 탭 이름이 조금씩 바뀌어도
# (`딜 소싱  참여 투자사 대표` 처럼 공백이 두 칸이거나) 따라가야 한다.
_CEO_HINT = "대표"
_SERIES_A_HINT = "시리즈 a"
_MNA_HINTS = ("m&a", "후속", "공동투자", "앵커")


def honorific(bucket: str) -> str:
    """직함이 비어 있을 때 뭐라고 부를 것인가.

    인사말은 시트에 적힌 직함을 그대로 쓴다(`김철수 팀장님`). 그런데 소싱
    명단에는 직함이 빈 줄이 있고, 그러면 `안녕하세요, 홍길동` 으로 나가
    무례해진다. 갈래가 그 사람이 누구인지 이미 말해 주므로 그것을 쓴다.

    '님' 은 인사말이 붙인다 — 여기서 붙이면 '심사역님님' 이 된다.
    """
    return "대표" if _CEO_HINT in (bucket or "") else "심사역"


def deal_count(bucket: str) -> int:
    """한 달에 몇 개사를 청하는가.

    투자사 대표는 팀 전체가 본 딜을 쥐고 있어 5개사, 개인 자격으로 참여하는
    심사역은 자기가 본 것만이라 2개사다.
    """
    return 5 if _CEO_HINT in (bucket or "") else 2


def is_series_a(bucket: str) -> bool:
    """시리즈 A 이상 갈래인가 — 이름에 든 말로 읽는다(`scope` 와 같은 판단)."""
    return _SERIES_A_HINT in (bucket or "").lower()


def is_mna(bucket: str) -> bool:
    """M&A 갈래인가(`M&A 찾는 투자사`) — 월간 리마인드 뼈대가 M&A 말로 바뀐다.
    구주·후속 갈래는 이름에 `m&a` 가 없어 여기 안 걸린다(그 갈래는 기본 뼈대)."""
    return "m&a" in (bucket or "").lower()


def scope(bucket: str) -> Optional[str]:
    """이 갈래가 찾는 딜의 범위. 없으면 범위 줄을 넣지 않는다."""
    low = (bucket or "").lower()
    if is_series_a(low):
        return ("[ 프리 IPO 전단계 , 시리즈 A 이상 , 100억 이상 투자유치기업 딜 , "
                "바이아웃 딜 , M&A 딜 , 프리밸류 200억 이상 딜 ]")
    if any(h in low for h in _MNA_HINTS):
        return "[ M&A , 후속투자 , 공동투자 , 앵커투자 딜 ]"
    return None


def default_body(bucket: str) -> str:
    """시드가 없을 때 쓰는 뼈대.

    딜 수신 메일 주소는 여기 넣지 않는다 — 갈래마다 다르고, 바뀌면 배포해야
    한다. 원본 스크립트를 넣으면 그것이 이 자리를 대신한다.
    """
    lines = [
        "Deal Sourcing 네트워크 참여 방법 안내 드립니다.",
        "",
        "투자 방향이나 Fit 차이로 검토 제외된 딜을",
        "투자사 간 재공유하는 네트워크입니다.",
    ]
    where = scope(bucket)
    if where:
        lines += ["", where]
    lines += [
        "",
        f" . 매월 1~3주 검토 제외 딜 , {deal_count(bucket)}개사 전달 주시면",
        " . 컨텍브이씨 ASSET 취합 > 월초 통합하여 공유 드립니다",
        " . 클로즈드 방식 운영되고 있습니다.",
        "",
        "참여 가능하시면 편히 말씀 부탁드립니다.",
    ]
    return "\n".join(lines)


def body_for(db: Session, user: User, bucket: str) -> str:
    """이 갈래에 쓸 문구. **갈래 문구 > 갈래 없는 문구 > 뼈대** 순.

    갈래를 먼저 보는 이유는 이 파일의 첫머리 그대로다 — 호칭·개수·범위가
    갈래마다 다르고, 어긋나면 문구 자체가 결례가 된다. 갈래 문구가 없으면
    갈래 없는 기본 문구를 찾고, 그것도 없으면 뼈대를 만든다: 문구가 없다고
    발송 화면이 비면 왜 안 되는지 알 수 없다.

    갈래 **안에서** 무엇을 쓸지(고른 것 > 내 것 > 팀 것)는 `template_pick` 이
    정한다. 딜소개와 여기가 각자 규칙을 들고 있으면 언젠가 어긋나고, 그러면
    같은 사람이 화면마다 다른 문구를 받는다.
    """
    return _picked(db, user, KIND, bucket) or default_body(bucket)


def _picked(db: Session, user: User, kind: str, bucket: str) -> Optional[str]:
    """이 종류에서 이 갈래에 쓸 저장 문구 — **갈래 문구 > 갈래 없는 문구**.

    처음 안내와 리마인드가 같은 차례로 고른다. 한쪽만 다른 차례를 들면 같은
    갈래 사람이 문구마다 다른 규칙을 받는다.
    """
    slots = [bucket, ""] if (bucket or "").strip() else [""]
    for variant in slots:
        found = template_pick.pick(db, user.id, kind, variant)
        if found:
            return found.body
    return None


def remind_default_body(bucket: str) -> str:
    """리마인드 문구틀이 없을 때 나가는 글.

    **글자까지 `scripts/bootstrap.py` 가 시리즈 A 갈래에 심는 문구와 같다** —
    새로 깐 서버와 문구틀을 지운 사람이 서로 다른 글을 받지 않게. 다른 갈래는
    첫 줄만 갈래 이름을 부르지 않는 말로 바꾼다(시리즈 A 가 아닌 분께
    `Series A 이상 딜 네트워크` 라고 하면 남의 갈래 이야기다).

    **메일 주소를 넣지 않는다**(공개 저장소). 운영에서는 `/templates` 의 이
    문구에 실제 주소를 적는다 — 그 저장 문구가 이 글을 대신한다.

    **M&A 갈래는 M&A 말로 쓴다**(`remind_mna_body` — 사용자 결정 2026-10-21). 같은
    뼈대(감사 · 이 달 딜 · 지난 딜 · 담당자 연락처 · 맺음)에서 찾는 딜만 바꾼 글이다.
    `scripts/bootstrap.py` 가 그 갈래에도 팀 문구로 심는다 — `/templates` 에서 고친다.
    """
    if is_mna(bucket):
        return remind_mna_body()
    first = ("Series A 이상 딜 네트워크에 함께해 주셔서 감사합니다."
             if is_series_a(bucket)
             else "Deal Sourcing 네트워크에 함께해 주셔서 감사합니다.")
    return "\n".join([
        first,
        "",
        f"{MONTH_TOKEN}월에 공유해 주실 딜은 카톡 또는 메일로 전달 부탁드립니다.",
        "지난번 공유드린 딜 중 관심 있는 기업이 있으시면 IR Deck을 보내 드리겠습니다.",
        "",
        "딜을 전달해 주실 때 기업 담당자 성함과 연락처도 함께 알려 주시면,",
        "투자 검토 의향이 있는 투자사와 바로 연결해 드리겠습니다.",
        "",
        "이미 전달해 주셨다면 이 메시지는 넘겨 주셔도 됩니다.",
        "감사합니다.",
    ])


def remind_mna_body() -> str:
    """M&A 갈래의 월간 리마인드 뼈대 — 위 `remind_default_body` 와 같은 차례의 글.
    메일 주소 · 실명은 넣지 않는다(공개 저장소)."""
    return "\n".join([
        "M&A 딜 네트워크에 함께해 주셔서 감사합니다.",
        "",
        f"{MONTH_TOKEN}월에 공유해 주실 M&A 딜(매각 · 인수 희망 기업)은 카톡 또는 메일로 전달 부탁드립니다.",
        "지난번 공유드린 딜 중 관심 있는 기업이 있으시면 기업 소개 자료를 보내 드리겠습니다.",
        "",
        "딜을 전달해 주실 때 기업 담당자 성함과 연락처도 함께 알려 주시면,",
        "인수 · 투자 검토 의향이 있는 곳과 바로 연결해 드리겠습니다.",
        "",
        "이미 전달해 주셨다면 이 메시지는 넘겨 주셔도 됩니다.",
        "감사합니다.",
    ])


def fill_month(body: str, day: Optional[date] = None) -> str:
    """`{월}` → 이 달 숫자(`10`). 저장 문구든 뼈대든 **여기 하나**를 지난다.

    운영자가 문구 화면에서 고친 글에도 `{월}` 이 남아 있을 수 있다 — 채우지
    않으면 `{월}월에` 가 글자 그대로 심사역 카톡방에 나간다.
    """
    month = (day or clock.today()).month
    return (body or "").replace(MONTH_TOKEN, str(month))


def remind_body_for(db: Session, user: User, bucket: str,
                    day: Optional[date] = None) -> str:
    """이 갈래에 쓸 **월간 리마인드** 글(`{월}` 을 채운 것).

    고르는 차례는 처음 안내(`body_for`)와 같다 — 갈래 문구 > 갈래 없는 문구 >
    코드 뼈대. 자동 리마인드(#277)도 이 함수를 부르면 손으로 보낸 것과 같은
    글이 나간다.
    """
    body = _picked(db, user, REMIND_KIND, bucket) or remind_default_body(bucket)
    return fill_month(body, day)


def topic_of(raw: Optional[str]) -> Optional[str]:
    """화면이 보낸 [보낼 문구] → 문구 종류. 비면 처음 안내, 모르는 값이면 `None`.

    모르는 값을 처음 안내로 짐작하지 않는다 — 리마인드를 고른 사람에게 참여
    방법 안내가 나가면 이미 참여한 분께 "참여 가능하시면…" 이 간다.
    """
    text = (raw or "").strip()
    if not text:
        return KIND
    return text if text in TOPICS else None
