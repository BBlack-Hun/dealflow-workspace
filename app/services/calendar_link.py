"""미팅을 **구글 캘린더에 옮겨 담는 링크** 한 줄.

왜 링크인가
-----------
미팅은 이 앱에 적히지만 사람이 실제로 보는 것은 자기 구글 캘린더다. 지금은
날짜와 시각을 눈으로 읽어 캘린더에 **다시 타이핑한다** — 그러다 한 건을
빠뜨리면 그 미팅은 알림 없이 지나간다.

캘린더 API 로 직접 넣는 길도 있지만 그쪽은 OAuth 동의화면·토큰 보관·갱신이
따라오고, 서버가 남의 캘린더를 쓰기 권한으로 들고 있게 된다. 링크는
**주소 문자열 하나**다 — 인증도 비밀값도 새 의존성도 없고, 누르면 그 브라우저에
로그인된 계정의 '일정 추가' 화면이 뜬다. 저장은 사람이 누른다.

양식은 **팀이 실제로 쓰는 일정 모양**이다
------------------------------------------
제목·설명을 이 앱이 보기 좋게 지어내면, 사람은 캘린더에서 그것을 지우고
쓰던 모양으로 다시 적는다. 그래서 여기가 만드는 것은 팀이 이미 손으로 적어
오던 그 양식이다::

    [{적은 사람}/{기업 담당자}/{지역구}] {기업들} IR 미팅 / 투자사 {투자사} {이름} {직함}

**틀만 여기 있고 값은 전부 DB 에서 온다.**

한 일정에 여러 미팅을 담는다
----------------------------
투자사 담당자 한 분을 만나러 가면 그 자리에서 기업 두셋을 잇달아 소개한다.
그것을 미팅 건마다 따로 캘린더에 넣으면 같은 장소·같은 사람으로 하루에
칸이 셋 생기고, 정작 **몇 시부터 몇 시까지 비워야 하는지**가 안 보인다.
**같은 담당자 · 같은 날**은 한 일정으로 묶고, 첫 미팅 시각부터 마지막 미팅
시각 + 한 시간까지를 잡는다. 어느 기업을 몇 시에 보는지는 설명에 줄줄이 적는다.

참석자를 넣지 않는 이유
-----------------------
주소에 ``add=<메일>`` 을 붙일 수 있지만 **붙이지 않는다.** 사람이 [저장] 을
누르는 순간 구글이 그 주소로 **초대 메일을 실제로 보낸다.** 이쪽 화면에서
미팅을 정리하려던 것이 투자사 담당자에게 나가는 메일이 된다. 되돌릴 수 없다.

장소는 **적혀 있을 때만** 넣는다 — 투자사 담당자의 주소(`VcContact.address`)다.
없으면 칸 자체를 안 만든다. 빈 장소를 넣으면 캘린더가 그 자리를 지도로
찍으려다 엉뚱한 곳을 가리킨다.

주소로 못 정하는 것
-------------------
``action=TEMPLATE`` 주소가 받는 칸은 제목·시각·장소·설명·시간대뿐이다.
**알림(30분 전)** 과 **어느 캘린더에 담을지**는 주소로 못 정한다 — 구글이
그 칸을 안 받는다. 되는 척 만들지 않는다: 사람이 저장 화면에서 고르면 된다.

주소 규격
---------
``calendar.google.com/calendar/render?action=TEMPLATE`` 은 널리 쓰이지만
구글 공식 문서로 보증된 규격은 아니다. 바뀌면 링크가 '일정 추가' 화면을
못 띄운다 — 그래도 잃는 것은 이 링크 하나뿐이고, 미팅 기록 자체는 그대로다.
"""
from __future__ import annotations

import os
import re
from datetime import date, datetime, time, timedelta
from typing import Iterable, List, Mapping, Optional, Sequence, Tuple
from urllib.parse import quote, urlencode

BASE_URL = "https://calendar.google.com/calendar/render"

#: 마지막 미팅이 끝나고도 잡아 두는 시간(분). **이 앱에서 이 값은 여기 한 곳뿐이다.**
#: 끝나는 시각을 따로 받지 않기로 했으므로(투자사 미팅은 대개 한 시간이다)
#: 마지막 미팅 시각 + 이만큼이 일정의 끝이 된다. 사람이 캘린더에서 늘리고 줄이면 그만이다.
DEFAULT_MINUTES = 60

#: ``TZ`` 를 못 읽었을 때 쓸 시간대. 이 앱은 한국 시간으로 돈다.
DEFAULT_TZ = "Asia/Seoul"

#: 요일 한 글자. 날짜에서 **계산**한다 — 미팅에는 요일 칸이 없다.
WEEKDAYS = "월화수목금토일"

#: 제목 가운데 토막의 고정 문구. 미팅 구분(1차/2차)은 여기 들어가지 않는다 —
#: 팀이 쓰는 제목이 `IR 미팅` 한 가지다.
MEETING_LABEL = "IR 미팅"

#: 주소에서 지역을 집을 때 볼 꼬리. 구/군이 먼저다 —
#: `경기도 가나시 다라구` 에서 사람이 말하는 '지역구' 는 `다라구` 다.
DISTRICT_TAILS = ("구", "군")
CITY_TAIL = "시"

#: 주소 토막 끝에 붙어 오는 문장부호. `마포구,` 를 `마포구` 로 읽는다.
_TRIM = " ,.·:;()[]"


def timezone_name() -> str:
    """캘린더에 넘길 시간대 이름(``Asia/Seoul``).

    ``clock.py`` 와 같은 손잡이를 쓴다 — 한국 시간이라는 것은 compose 의 ``TZ``
    하나가 정하고, 코드에는 ``+09:00`` 을 박지 않는다. 다만 캘린더는 오프셋이
    아니라 **이름**을 받으므로 ``astimezone()`` 대신 환경변수를 읽는다.

    ``TZ`` 는 ``:Asia/Seoul`` 처럼 콜론이 붙거나 아예 비어 있을 수 있다.
    지역/도시 꼴이 아니면 캘린더가 못 알아들으므로 기본값으로 돌아간다.
    """
    name = (os.environ.get("TZ") or "").strip().lstrip(":")
    return name if "/" in name else DEFAULT_TZ


def _text(value: Optional[str]) -> str:
    """적어 둔 글자. 줄바꿈·겹공백은 한 칸으로 — 제목 한 줄에 들어갈 값이다."""
    return re.sub(r"\s+", " ", value or "").strip()


def _at(value: Optional[str]) -> Optional[time]:
    """적어 둔 ``HH:MM``. 못 읽으면 ``None`` — **지어내지 않는다.**

    저장할 때 ``pipeline.clean_time`` 이 이미 걸러 둔 값이라 여기 걸릴 일은
    드물지만, 걸리면 ``00:00`` 으로 채우는 대신 **시각을 모르는 것**으로 둔다.
    자정 미팅을 만들어 두면 사람이 그 시간에 맞춰 나갈 준비를 한다.
    """
    text = _text(value)
    if not text:
        return None
    try:
        return time.fromisoformat(text)
    except ValueError:
        return None


def _day(value: Optional[str]) -> Optional[date]:
    try:
        return date.fromisoformat((value or "")[:10])
    except ValueError:
        return None


def _who(*parts: Optional[str]) -> str:
    """빈 것은 자리를 차지하지 않는다 — `홍길동  상무` 처럼 두 칸이 나지 않게."""
    return " ".join(p for p in (_text(x) for x in parts) if p)


def _uniq(values: Iterable[Optional[str]]) -> List[str]:
    """적힌 순서를 지키며 겹치는 것만 지운다.

    같은 담당자를 하루에 두 번 만나며 **같은 기업**을 두 자리에 올리는 일이
    있다. 제목에 그 이름이 두 번 서면 읽는 사람이 다른 기업으로 센다.
    """
    out: List[str] = []
    for value in values:
        text = _text(value)
        if text and text not in out:
            out.append(text)
    return out


def phone_for(phone: Optional[str] = None, office_phone: Optional[str] = None) -> str:
    """설명에 적을 번호 하나. **휴대폰이 먼저다.**

    가는 길에 늦는다고 거는 번호는 사무실이 아니라 손에 든 쪽이고, 명단에도
    휴대폰이 훨씬 많이 채워져 있다. 휴대폰이 없으면 유선으로 내려가고,
    **둘 다 없으면 빈 문자열**이다 — 설명에서 그 줄이 통째로 빠진다.
    지어내거나 `-` 로 채우지 않는다.
    """
    return _text(phone) or _text(office_phone)


def district_of(address: Optional[str] = None) -> str:
    """주소에서 **지역구** 한 토막. `서울특별시 마포구 가나로 …` → `마포구`.

    제목 앞머리에 어디로 가는지가 있어야 아침에 동선을 짠다. 그렇다고 주소를
    통째로 제목에 실으면 달력 칸에서 그 줄만 남고 기업 이름이 잘린다.

    규칙은 둘뿐이다.

    1. 끝이 `구`·`군` 인 첫 토막 (`마포구` · `다라구` · `가나군`)
    2. 없으면, **맨 앞 토막을 뺀** 뒤 끝이 `시` 인 첫 토막 (`경남 창원시` → `창원시`)
       맨 앞을 빼는 이유: 그 자리는 `서울특별시` 처럼 광역 이름이라 지역구가 아니다.

    둘 다 못 찾으면 **빈 문자열이다 — 지어내지 않는다.** 도로명만 적힌 주소,
    영문 주소, 아예 안 적힌 담당자가 실제로 있다. 못 읽었으면 제목에서 그
    자리가 통째로 빠질 뿐, 틀린 동네를 적어 두지 않는다.
    """
    tokens = [t.strip(_TRIM) for t in _text(address).split(" ")]
    tokens = [t for t in tokens if len(t) >= 2]
    for token in tokens:
        if token.endswith(DISTRICT_TAILS):
            return token
    for token in tokens[1:]:
        if token.endswith(CITY_TAIL):
            return token
    return ""


def _ordered(meetings: Sequence[Mapping]) -> List[Mapping]:
    """설명에 적을 차례 — **이른 시각부터.**

    화면의 미팅 표는 최근 것이 위로 오게 내림차순인데, 일정 설명은 그날
    움직이는 차례라 그대로 쓰면 거꾸로 적힌다. 시각을 안 적어 둔 건은
    맨 뒤로 — 앞에 세우면 그 자리가 첫 일정으로 읽힌다.
    """
    def key(item: Mapping) -> Tuple:
        at = _text(item.get("time"))
        return (_text(item.get("date")), not at, at)

    return sorted(meetings, key=key)


def _when_label(when: Optional[str], at: Optional[str]) -> str:
    """`2026-08-24(월) 13:20`. 시각을 모르면 날짜와 요일까지만."""
    day = _day(when)
    if day is None:
        return ""
    label = f"{day.isoformat()}({WEEKDAYS[day.weekday()]})"
    clock = _text(at)
    return f"{label} {clock}" if clock else label


def _span(meetings: Sequence[Mapping]) -> str:
    """``dates`` 값. **첫 미팅부터 마지막 미팅 + 한 시간까지.**

    한 건이든 세 건이든 같은 길로 간다 — 한 건이면 시작과 끝이 같은 미팅이라
    그냥 한 시간짜리가 된다.

    묶음에 **시각을 안 적어 둔 건이 섞이면** 그 건은 폭을 정하는 데 쓰지
    않는다. 자정으로 치면 아침 아홉 시부터 비워 놓게 되고, 묶음 전체를 종일로
    돌리면 적어 둔 시각이 사라진다. 그 건은 설명에 날짜만 적혀 남는다.

    아무 건에도 시각이 없으면 **종일**이다. 종일 일정의 끝날짜는 다음 날이다 —
    구글은 끝을 포함하지 않는 것으로 읽으므로 같은 날을 두 번 적으면 길이가
    0인 일정이 된다.
    """
    days = [d for d in (_day(m.get("date")) for m in meetings) if d is not None]
    if not days:
        return ""
    moments = [datetime.combine(day, at)
               for day, at in ((_day(m.get("date")), _at(m.get("time"))) for m in meetings)
               if day is not None and at is not None]
    if not moments:
        return f"{min(days):%Y%m%d}/{max(days) + timedelta(days=1):%Y%m%d}"
    start, end = min(moments), max(moments) + timedelta(minutes=DEFAULT_MINUTES)
    return f"{start:%Y%m%dT%H%M%S}/{end:%Y%m%dT%H%M%S}"


def title_for(*, user_name: str = "", contact_name: str = "", contact_title: str = "",
              firm: str = "", address: str = "",
              meetings: Sequence[Mapping] = ()) -> str:
    """캘린더에 뜰 제목.

    ``[적은 사람/기업 담당자/지역구] 기업들 IR 미팅 / 투자사 마바벤처스 홍길동 상무``

    앞머리의 세 자리는 **손으로 적어 오던 순서 그대로**다: 누가 적었는지,
    그 기업을 우리 팀에서 누가 맡고 있는지, 어디로 가는지.

    **기업 담당자가 서로 다른 기업을 한 자리에서 소개하는 날이 있다.** 그때는
    한 사람을 골라 적지 않고 **적힌 이름을 다 적는다**(쉼표). 하나를 고르면
    나머지 기업의 담당자에게는 그 미팅이 제 것으로 안 보인다 — 제목이 짧아지는
    대신 사람이 빠진다.

    비어 있는 자리는 **자리를 차지하지 않는다.** 주소를 안 적어 둔 담당자가
    실제로 있고, 그 자리에 빈 칸이 남으면(`[강민준//]`) 무엇이 빠졌는지가 아니라
    **뭔가 깨졌다**로 읽힌다.
    """
    ordered = _ordered(meetings)
    head = "/".join(p for p in (
        _text(user_name),
        ", ".join(_uniq(m.get("assignee") for m in ordered)),
        district_of(address),
    ) if p)
    companies = ", ".join(_uniq(m.get("company") for m in ordered))
    body = _who(companies, MEETING_LABEL)
    who = _who(firm, contact_name, contact_title)
    text = " ".join(p for p in (f"[{head}]" if head else "", body) if p)
    if who:
        text = f"{text} / 투자사 {who}".strip(" /")
    # 이름도 소속도 기업도 없는 건은 없지만, 있어도 빈 제목으로 두지 않는다.
    return text or MEETING_LABEL


def details_for(*, contact_name: str = "", contact_title: str = "", firm: str = "",
                phone: str = "", office_phone: str = "", address: str = "",
                meetings: Sequence[Mapping] = ()) -> str:
    """일정 설명 — 만날 사람과, 그날 무엇을 몇 시에 보는지.

    ::

        홍길동 상무
        010-0000-0000
        마바벤처스 상무
        서울특별시 마포구 가나로 100


        - 업체1 : 가나컴퍼니
        - 미팅 일정 : 2026-08-24(월) 13:20

        - 업체2 : 다라컴퍼니
        - 미팅 일정 : 2026-08-24(월) 14:30

    **적혀 있는 것만 적는다.** 번호도 주소도 없는 담당자가 실제로 있다. 그
    줄을 빈 채로 남기면 이름 아래에 빈 줄이 둘 생겨 무엇이 빠진 자리인지
    알 수 없고, `-` 로 채우면 '알아봤는데 없더라' 로 읽힌다 — 둘 다 안 한다.
    **줄이 통째로 빠진다.**

    기업이 하나뿐이어도 ``업체1`` 로 적는다. 번호를 뗀 양식을 따로 두면 하루
    뒤에 미팅이 하나 더 붙는 순간 같은 일정의 모양이 바뀐다 — 사람이 눈으로
    좇던 자리가 옮겨 간다.
    """
    head = [line for line in (
        _who(contact_name, contact_title),
        phone_for(phone, office_phone),
        _who(firm, contact_title),
        _text(address),
    ) if line]

    blocks: List[str] = []
    for number, item in enumerate(_ordered(meetings), start=1):
        lines = []
        company = _text(item.get("company"))
        if company:
            lines.append(f"- 업체{number} : {company}")
        when = _when_label(item.get("date"), item.get("time"))
        if when:
            lines.append(f"- 미팅 일정 : {when}")
        if lines:
            blocks.append("\n".join(lines))

    parts = [p for p in ("\n".join(head), "\n\n".join(blocks)) if p]
    # 사람 정보와 미팅 목록 사이는 **빈 줄 둘**이다. 붙여 놓으면 주소 다음
    # 줄에 `- 업체1` 이 와서 주소의 일부처럼 읽힌다.
    return "\n\n\n".join(parts)


def group_url(*, user_name: str = "", contact_name: str = "", contact_title: str = "",
              firm: str = "", phone: str = "", office_phone: str = "",
              address: str = "", meetings: Sequence[Mapping] = ()) -> str:
    """구글 캘린더 '일정 추가' 주소 하나. 날짜를 못 읽으면 빈 문자열이다.

    ``meetings`` 는 **한 일정에 담을 미팅들**이다 — 같은 담당자·같은 날.
    각 항목은 ``{"date": "2026-08-24", "time": "13:20", "company": "가나컴퍼니",
    "assignee": "관리1팀"}`` 꼴이고, ``time`` 과 ``company`` 는 비어 있을 수 있다.

    빈 문자열이면 화면이 링크를 아예 안 그린다 — 눌러도 아무 일 없는 링크보다
    없는 편이 낫다.
    """
    span = _span(meetings)
    if not span:
        return ""
    params = [
        ("action", "TEMPLATE"),
        ("text", title_for(user_name=user_name, contact_name=contact_name,
                           contact_title=contact_title, firm=firm,
                           address=address, meetings=meetings)),
        ("dates", span),
        ("ctz", timezone_name()),
    ]
    where = _text(address)
    if where:
        params.append(("location", where))
    details = details_for(contact_name=contact_name, contact_title=contact_title,
                          firm=firm, phone=phone, office_phone=office_phone,
                          address=address, meetings=meetings)
    if details:
        params.append(("details", details))
    # 공백을 `+` 로 바꾸는 기본 방식 대신 `%20` 으로 감싼다 — 주소를 사람이
    # 눈으로 확인하거나 다른 곳에 붙여 넣을 때 `+` 가 그대로 남는 자리가 있다.
    # `/` 는 그대로 둔다(`dates` 의 시작/끝 구분, `Asia/Seoul`, 제목의 구분자)
    # — 널리 쓰이는 주소 모양과 같아야 눈으로 견줄 수 있다. 질의 문자열
    # 안에서는 안전하다.
    return f"{BASE_URL}?{urlencode(params, safe='/', quote_via=quote)}"
