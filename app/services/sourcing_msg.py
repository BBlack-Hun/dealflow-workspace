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

from typing import Optional

from sqlalchemy.orm import Session

from ..models import User
from . import template_pick

#: 이 종류의 템플릿은 갈래(`name`)마다 하나씩 있다.
#: 갈래가 곧 자리라는 사실은 `template_pick.NAME_IS_A_BUCKET` 에 적혀 있다.
KIND = "sourcing_intro"

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


def scope(bucket: str) -> Optional[str]:
    """이 갈래가 찾는 딜의 범위. 없으면 범위 줄을 넣지 않는다."""
    low = (bucket or "").lower()
    if _SERIES_A_HINT in low:
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
    slots = [bucket, ""] if (bucket or "").strip() else [""]
    for variant in slots:
        found = template_pick.pick(db, user.id, KIND, variant)
        if found:
            return found.body
    return default_body(bucket)
