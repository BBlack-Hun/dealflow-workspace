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

참석자를 넣지 않는 이유
-----------------------
주소에 ``add=<메일>`` 을 붙일 수 있지만 **붙이지 않는다.** 사람이 [저장] 을
누르는 순간 구글이 그 주소로 **초대 메일을 실제로 보낸다.** 이쪽 화면에서
미팅을 정리하려던 것이 투자사 담당자에게 나가는 메일이 된다. 되돌릴 수 없다.

장소도 넣지 않는다 — 지금 미팅에 장소 칸이 없다. 없는 값을 지어내지 않는다.

주소 규격
---------
``calendar.google.com/calendar/render?action=TEMPLATE`` 은 널리 쓰이지만
구글 공식 문서로 보증된 규격은 아니다. 바뀌면 링크가 '일정 추가' 화면을
못 띄운다 — 그래도 잃는 것은 이 링크 하나뿐이고, 미팅 기록 자체는 그대로다.
"""
from __future__ import annotations

import os
from datetime import date, datetime, time, timedelta
from typing import Optional
from urllib.parse import quote, urlencode

BASE_URL = "https://calendar.google.com/calendar/render"

#: 시각을 적어 둔 미팅의 기본 소요시간(분). **이 앱에서 이 값은 여기 한 곳뿐이다.**
#: 끝나는 시각을 따로 받지 않기로 했으므로(투자사 미팅은 대개 한 시간이다)
#: 시작 + 이만큼이 끝이 된다. 사람이 캘린더에서 늘리고 줄이면 그만이다.
DEFAULT_MINUTES = 60

#: ``TZ`` 를 못 읽었을 때 쓸 시간대. 이 앱은 한국 시간으로 돈다.
DEFAULT_TZ = "Asia/Seoul"


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


def _at(value: Optional[str]) -> Optional[time]:
    """적어 둔 ``HH:MM``. 못 읽으면 ``None`` — **지어내지 않는다.**

    저장할 때 ``pipeline.clean_time`` 이 이미 걸러 둔 값이라 여기 걸릴 일은
    드물지만, 걸리면 ``00:00`` 으로 채우는 대신 **종일 일정**으로 간다.
    자정 미팅을 만들어 두면 사람이 그 시간에 맞춰 나갈 준비를 한다.
    """
    text = (value or "").strip()
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


def _dates(when: date, at: Optional[time]) -> str:
    """``dates`` 값. 시각을 알면 한 시간짜리, 모르면 **종일**.

    종일 일정의 끝날짜는 **다음 날**이다. 구글은 끝을 포함하지 않는 것으로
    읽으므로, 같은 날을 두 번 적으면 길이가 0인 일정이 된다.
    """
    if at is None:
        return f"{when:%Y%m%d}/{when + timedelta(days=1):%Y%m%d}"
    start = datetime.combine(when, at)
    end = start + timedelta(minutes=DEFAULT_MINUTES)
    return f"{start:%Y%m%dT%H%M%S}/{end:%Y%m%dT%H%M%S}"


def _who(name: str, title: str) -> str:
    return " ".join(p for p in (name.strip(), title.strip()) if p)


def title_for(*, name: str = "", title: str = "", firm: str = "",
              kind_label: str = "", company_name: str = "") -> str:
    """캘린더에 뜰 제목 — ``홍길동 심사역 · 가나벤처스 1차 미팅 (샘플애그)``.

    달력의 한 칸은 좁아 뒤가 잘린다. **누구를 만나는지**를 앞에 둔다.
    화면의 미팅 표와 같은 순서다(이름 · 직함 · 소속) — 두 곳을 나란히 보는
    사람이 같은 줄로 읽을 수 있게.

    비어 있는 값은 자리를 차지하지 않는다. 대상 기업을 안 적어 둔 미팅에
    괄호만 남으면 무엇이 빠졌는지 모른다.
    """
    head = " · ".join(p for p in (_who(name, title), firm.strip()) if p)
    text = " ".join(p for p in (head, kind_label.strip()) if p)
    company = company_name.strip()
    if company:
        text = f"{text} ({company})".strip()
    # 이름도 소속도 구분도 없는 건은 없지만, 있어도 빈 제목으로 두지 않는다.
    return text or "미팅"


def details_for(*, name: str = "", title: str = "", firm: str = "",
                kind_label: str = "", company_name: str = "",
                note: str = "") -> str:
    """일정 설명. 제목에서 잘린 것과 메모가 여기 남는다.

    **적혀 있는 것만 적는다.** 빈 칸을 ``-`` 로 채우면 캘린더에서는 그것이
    '알아봤는데 없더라' 로 읽힌다 — 그냥 안 적은 것과 다르다.
    """
    lines = [
        ("담당자", _who(name, title)),
        ("소속", firm.strip()),
        ("구분", kind_label.strip()),
        ("대상 기업", company_name.strip()),
        ("메모", note.strip()),
    ]
    return "\n".join(f"{key}: {value}" for key, value in lines if value)


def meeting_url(scheduled_at: Optional[str], scheduled_time: Optional[str] = None,
                *, name: str = "", title: str = "", firm: str = "",
                kind_label: str = "", company_name: str = "",
                note: str = "") -> str:
    """구글 캘린더 '일정 추가' 주소. 날짜를 못 읽으면 빈 문자열이다.

    빈 문자열이면 화면이 링크를 아예 안 그린다 — 눌러도 아무 일 없는 링크보다
    없는 편이 낫다.
    """
    when = _day(scheduled_at)
    if when is None:
        return ""
    params = [
        ("action", "TEMPLATE"),
        ("text", title_for(name=name, title=title, firm=firm,
                           kind_label=kind_label, company_name=company_name)),
        ("dates", _dates(when, _at(scheduled_time))),
        ("ctz", timezone_name()),
    ]
    details = details_for(name=name, title=title, firm=firm,
                          kind_label=kind_label, company_name=company_name,
                          note=note)
    if details:
        params.append(("details", details))
    # 공백을 `+` 로 바꾸는 기본 방식 대신 `%20` 으로 감싼다 — 주소를 사람이
    # 눈으로 확인하거나 다른 곳에 붙여 넣을 때 `+` 가 그대로 남는 자리가 있다.
    # `/` 는 그대로 둔다(`dates` 의 시작/끝 구분, `Asia/Seoul`) — 널리 쓰이는
    # 주소 모양과 같아야 눈으로 견줄 수 있다. 질의 문자열 안에서는 안전하다.
    return f"{BASE_URL}?{urlencode(params, safe='/', quote_via=quote)}"
