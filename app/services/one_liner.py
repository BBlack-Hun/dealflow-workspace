"""스타트업DB 칸 → IR 기업현황의 `기업 한줄 소개` 자동 조합.

시트를 쓰던 사람은 **스타트업DB 탭**(사업분야 · 연도별 매출 · 누적투자금액 ·
투자유치희망금액 · Pre Value · 특이사항)에 값을 넣는다. 그런데 정작 딜소개에
쓰이는 것은 옆 탭의 `한줄 소개` 한 칸이라, 같은 내용을 **두 번 적고 있었다.**
그래서 여기서 그 칸들을 이어 붙여 한 줄을 만든다.

    사업분야 | 매출 … | 누적투자금액 N억 | N억 투자유치중 | Pre Value N억 | 특이사항

**형식은 지어낸 것이 아니라 실데이터에서 세어 뽑았다.** 344행의 `한줄 소개`·
`사업분야` 를 `|` 로 쪼개 표기를 세어 보면 아래가 가장 많다 — 사람이 쌓아 온
표기가 정답이라, 새로 만드는 줄도 같은 모양이어야 섞어 놓고 봤을 때 티가 안 난다.

    · 매출          `매출 13억`      (연도가 둘 이상이면 `매출 23년 A, 24년 B, 25년 C`)
    · 누적투자금액   `누적투자금액 11억`   (`누적투자 …` 보다 흔하다)
    · 투자유치       `30억 투자유치중`     (`투자유치 30억` 보다 두 배 넘게 흔하다)
    · Pre Value     `Pre Value 200억`   (대소문자는 이 모양이 가장 많다)

**금액은 고치지 않는다.** 연도별 매출은 원본에 `8.2억` · `1,224백만원` ·
`150억 ~ 200억` · `4월 기준 3억` 이 한 칸에 섞여 있어서, 숫자로 바꾸려면 단위를
판별해야 한다. 잘못 읽으면 100배가 틀어진 채 딜소개 문구에 실려 나간다 —
**적힌 그대로** 옮기고 단위를 붙이거나 다듬지 않는다.
(누적투자금액·투자유치·Pre Value 는 모델이 이미 백만원 정수라, 화면·딜소개와
같은 `format_eok` 로 억으로 옮긴다. 표와 문구가 다른 숫자를 보이면 안 된다.)

`funding_status`(투자현황)는 **쓰지 않는다.** 이름만 보면 '진행 상태' 같지만
실데이터 344행 중 335행이 `한줄 소개` 와 **글자까지 똑같은 사본**이고, 나머지도
`메일함에 없음, 자료 필요` 같은 메모다. 그대로 붙이면 한 줄 소개 안에 한 줄
소개가 통째로 한 번 더 들어간다.
"""
from __future__ import annotations

import re
from typing import List, Optional

from .message_composer import format_eok

# 조합에 쓰는 칸. 다른 곳(화면 안내·테스트)에서 "무엇이 합쳐지는가"를 물을 때
# 목록을 두 벌로 적지 않게 여기 한 군데만 둔다.
SOURCE_FIELDS = [
    # 이름이 `사업분야` 였다. 그런데 IR 기업 현황에 `사업분야 대분류`
    # (`sector_major`)가 따로 있어서 **같은 말이 서로 다른 두 칸**을 가리켰다 —
    # 하나는 갈래(`헬스케어`)고 이 칸은 문장이다. [수정] 창에 이 칸을 세우면서
    # 화면 이름을 `사업 설명` 으로 정했고(모델 주석이 부르는 말 그대로다),
    # 여기도 같은 글자로 맞춘다. 두 벌로 두면 화면과 이 목록이 갈린다.
    ("business_desc", "사업 설명"),
    ("revenue_2023", "23년 매출"),
    ("revenue_2024", "24년 매출"),
    ("revenue_2025", "25년 매출"),
    ("funding_total", "누적투자금액"),
    ("raise_target", "투자유치 진행금액"),
    ("pre_value", "Pre Value"),
    ("competitiveness", "특이사항"),
]

# 연도별 매출 칸 — **오래된 해부터** 적어 둔다(맨 뒤가 가장 최근이다).
# 22년은 일부러 뺀다: 소개 문구에 22년 매출을 적은 예가 시트에 하나도 없다.
REVENUE_YEARS = ["revenue_2023", "revenue_2024", "revenue_2025"]


def _text(value: Optional[str]) -> str:
    return (value or "").strip() if isinstance(value, str) else ""


# 시트에서 옮겨 온 글자 안의 **구분자 흔들림**. `|` 를 치려다 같은 자리의 다른
# 글자를 친 흔적이 그대로 남아 있다 — 대문자 `I` · 소문자 `l` · 한글 자모 `ㅣ`.
# 344행의 사업분야·특이사항 중 22개 값이 여기 걸린다(전부 눈으로 확인했다).
# `I`·`l` 은 **앞뒤에 공백이 있을 때만** 구분자로 본다 — 그래야 낱말 속 글자를
# 가르지 않는다. `ㅣ` 는 홀로 쓰이는 낱자라 붙어 있어도 낱말의 일부일 수 없다.
_SEPARATOR = re.compile(r"\s*\|\s*|\s+[Il]\s+|\s*ㅣ\s*")
# `-` 하나만 적힌 토막. 시트에서 '해당 없음'을 그렇게 적어 뒀다.
# 그대로 이어 붙이면 `… | - | …` 라는 **빈 칸이 보이는 줄**이 된다.
_PLACEHOLDER = re.compile(r"^[-–—·.\s]*$")


def _clean(value: Optional[str]) -> str:
    """시트에서 온 긴 글자를 한 줄에 붙일 수 있게 다듬는다.

    **내용은 손대지 않는다.** 구분자를 ` | ` 한 가지로 맞추고, `-` 하나만 적힌
    빈 토막을 뺄 뿐이다. 저장된 값 자체는 그대로 두고 **보여줄 때만** 다듬는다 —
    사람이 적어 둔 원문을 코드가 고쳐 쓰기 시작하면 되돌릴 수가 없다.
    """
    text = _text(value)
    if not text:
        return ""
    parts = [p.strip() for p in _SEPARATOR.split(text)]
    return " | ".join(p for p in parts if p and not _PLACEHOLDER.match(p))


def _is_amount(value: str) -> bool:
    """이 매출 칸이 **금액**인가, 아니면 '아직 못 찾았다'는 메모인가.

    실데이터 매출 칸에는 `최근데이터 확인X`(55) · `확인안됨`(40) · `검색안됨`(36) ·
    `매출액 없음`(1) 이 들어 있다. 그대로 옮기면 소개 문구가
    `매출 24년 확인안됨` 이 되어 그냥 안 쓴 것만 못하다.

    가르는 기준은 **숫자가 한 자라도 있는가** 하나다. 메모들은 전부 숫자가 없고,
    반대로 `4월 기준 3억`·`1.5억 목표`·`10억 이상` 처럼 말이 섞인 금액은 숫자가
    있어서 살아남는다 — 금액이면 손대지 않고 그대로 내보낸다.
    """
    return any(ch.isdigit() for ch in value)


def _revenue_segment(company) -> str:
    """`매출 …` 토막 — 23·24·25년 칸 중 **가장 최근에 적힌 한 해**를 쓴다.

    값은 **적힌 그대로**다. 단위를 붙이거나 고치지 않는다.

    처음에는 세 해를 다 늘어놓았다(`매출 23년 2억, 24년 4억, 25년 11억`).
    그런데 실데이터에 대 보니 사람은 그렇게 안 쓴다 — 기존 `한줄 소개` 에 매출이
    적힌 88곳을 두 방식으로 만들어 대조하면:

        · `매출 {가장 최근 해}`      글자까지 동일 36곳 (40.9%)
        · 세 해를 늘어놓는 방식       글자까지 동일  6곳 ( 6.8%)

    사용자가 준 예시 두 개(`… | 매출 13억 | …`, `… | 매출 8.9억 | …`)도 전부
    **한 해치 한 덩어리**다. 연도별 추이는 스타트업DB 탭에 그대로 남아 있으니,
    한 줄 소개에서는 가장 최근 숫자 하나만 들고 나온다.
    (세 해를 다 보이고 싶어지면 이 함수만 고치면 된다.)
    """
    written = [_text(getattr(company, attr, None)) for attr in REVENUE_YEARS]
    written = [value for value in written if value and _is_amount(value)]
    return f"매출 {written[-1]}" if written else ""


def _eok_segment(value: Optional[int], template: str) -> str:
    """백만원 정수 → `{}` 자리에 억을 넣은 토막. 비어 있으면 토막 자체를 뺀다."""
    if value is None:
        return ""
    amount = format_eok(value)
    return "" if amount is None else template.format(amount)


def compose_one_liner(company) -> str:
    """스타트업DB 칸들을 이어 붙인 `기업 한줄 소개` 한 줄.

    **빈 칸은 토막째 빠진다.** 실데이터는 대부분 일부만 차 있어서(누적투자금액은
    344곳 중 42곳뿐이다) 자리를 비워 두면 `… | | …` 가 줄줄이 남는다.

    사업분야에 **이미 재무까지 적혀 있는 경우가 많다** — 시트를 쓰던 사람이 그
    한 칸에 `설명 | 매출 13억 | 누적투자금액 11억 | …` 을 통째로 적어 왔다.
    같은 항목을 또 붙이면 `매출 13억 … 매출 13억` 처럼 **중복되고 숫자가 어긋난다.**
    그래서 딜소개 문구(message_composer.auto_company_summary)와 똑같이, 항목마다
    '앞에서 이미 말했는가'를 보고 없을 때만 덧붙인다.
    """
    head = _clean(getattr(company, "business_desc", None))
    segments: List[str] = [head] if head else []

    # 이미 말한 내용. 사업분야에 통째로 적혀 온 줄과 겹치지 않게 한다.
    said = head

    revenue = _revenue_segment(company)
    if revenue and "매출" not in said:
        segments.append(revenue)

    funding = _eok_segment(getattr(company, "funding_total", None), "누적투자금액 {}억")
    if funding and "누적투자" not in said:
        segments.append(funding)

    raising = _eok_segment(getattr(company, "raise_target", None), "{}억 투자유치중")
    if raising and "투자유치" not in said and "투자 유치" not in said:
        segments.append(raising)

    pre = _eok_segment(getattr(company, "pre_value", None), "Pre Value {}억")
    if pre and not any(k in said.lower() for k in ("pre value", "pre-value", "프리벨류", "밸류")):
        segments.append(pre)

    edge = _clean(getattr(company, "competitiveness", None))
    if edge and edge not in said:
        segments.append(edge)

    return " | ".join(segments)


# --- 손으로 쓴 소개를 지키는 규칙 ---------------------------------------------
#
# 지금 344곳 중 293곳에 **사람이 쓴 한줄 소개**가 들어 있다. 스타트업DB 를 고칠
# 때마다 무턱대고 덮으면 그게 소리 없이 사라진다 — 되돌릴 수 없다.
#
# 그렇다고 '비었을 때만 채운다'로 두면, 이미 293곳이 차 있어서 **스타트업DB 를
# 채워도 한줄 소개가 그대로**다. 그건 요청의 핵심을 못 지킨다.
#
# 그래서 **자동으로 만든 값인지 사람이 쓴 값인지 가려내서** 다르게 다룬다.
# 가려내는 방법은 '표시를 남기는 것'이 아니라 **다시 만들어 맞춰 보는 것**이다 —
# 고치기 **전** 칸들로 한 줄을 만들어, 지금 저장된 소개와 글자까지 같으면 그건
# 이 코드가 만든 값이니 새 값으로 갱신해도 잃을 것이 없다. 다르면 사람이 손을
# 댄 것이니 **그대로 둔다.** (모델에 '자동/수동' 칸을 새로 파지 않아도 되고,
# 이미 쌓인 344행에 표시를 소급해 넣을 필요도 없다.)
#
# 사람이 쓴 소개가 있어 자동 갱신을 건너뛴 경우에도 **조용히 넘어가지 않는다.**
# 만들어 둔 값을 `suggestion` 으로 함께 돌려주어 화면이 "이 값으로 바꾸기"를
# 권할 수 있게 하고, 사람이 그걸 고르면 apply_one_liner 로 덮는다.
# 즉 자동 조합을 쓸지 손으로 쓴 것을 지킬지는 **언제나 사람이 고른다.**

AUTO = "auto"        # 이 코드가 만든 값 그대로다 → 갱신해도 잃을 것이 없다
MANUAL = "manual"    # 사람이 손댄 값이다 → 덮지 않는다
EMPTY = "empty"      # 아직 비어 있다 → 채운다


def origin(current: Optional[str], previous_auto: Optional[str]) -> str:
    """지금 저장된 소개가 자동으로 만든 값인가, 사람이 쓴 값인가.

    `previous_auto` 는 **고치기 전** 칸들로 만든 한 줄이다.
    """
    text = _text(current)
    if not text:
        return EMPTY
    return AUTO if text == _text(previous_auto) else MANUAL


def sync_one_liner(company, previous_auto: Optional[str], manual_edit: bool = False) -> dict:
    """스타트업DB 를 고친 뒤 `한줄 소개` 를 맞춘다.

    `manual_edit` 은 이번 요청이 한줄 소개 자체를 손으로 고친 경우다 — 방금 사람이
    적은 문장을 같은 요청 안에서 자동 조합으로 덮으면 타이핑이 눈앞에서 사라진다.

    돌려주는 값:
      applied     실제로 갱신했는가
      suggestion  만들어 둔 한 줄(안 덮었을 때 화면이 권할 값)
      kept        사람이 쓴 소개를 지키느라 건너뛰었는가
      origin      갱신 전 소개의 출처(auto/manual/empty)
    """
    suggestion = compose_one_liner(company)
    where = origin(getattr(company, "one_liner", None), previous_auto)

    if manual_edit:
        # 방금 손으로 적었다. 그 값이 곧 사람의 결정이다.
        return {"applied": False, "suggestion": suggestion, "kept": True, "origin": MANUAL}
    if not suggestion:
        # 조합할 내용이 하나도 없다. **있는 소개를 비우지는 않는다** —
        # 스타트업DB 가 비었다는 이유로 멀쩡한 소개를 지우면 그게 제일 나쁘다.
        return {"applied": False, "suggestion": "", "kept": where == MANUAL, "origin": where}
    if where == MANUAL:
        return {"applied": False, "suggestion": suggestion, "kept": True, "origin": MANUAL}

    company.one_liner = suggestion
    return {"applied": True, "suggestion": suggestion, "kept": False, "origin": where}


def apply_one_liner(company) -> str:
    """사람이 "자동 조합을 쓰겠다"고 고른 경우 — 손으로 쓴 소개까지 덮는다.

    조합할 내용이 없으면 아무것도 하지 않는다(빈 줄로 지우지 않는다).
    """
    suggestion = compose_one_liner(company)
    if suggestion:
        company.one_liner = suggestion
    return suggestion
