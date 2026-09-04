"""미팅 → **구글 캘린더에 추가** 링크.

이 링크가 하는 일은 주소 문자열 하나를 만들어 화면에 놓는 것뿐이다. 그래서
검사할 것도 주소 하나지만, 틀리면 조용히 틀린다 — 캘린더 화면은 뜨는데
엉뚱한 시각이 잡히거나(시간대), 안 넣기로 한 것이 들어가 있거나.

여기서 지키는 것
1. **시각이 있으면 한 시간짜리**, 시각이 없으면 **종일**. 없는 시각을
   ``00:00`` 으로 채우지 않는다 — 모델이 못박아 둔 원칙이다.
2. **시간대는 한국.** 안 적으면 구글이 보는 사람의 시간대로 읽어, 해외에서
   열면 다른 시각에 잡힌다.
3. **참석자를 넣지 않는다.** ← 여기가 제일 위험하다. ``add=`` 를 붙이면
   사람이 [저장] 을 누르는 순간 구글이 그 주소로 **초대 메일을 실제로 보낸다.**
   되돌릴 수 없다.
4. 한글과 공백이 주소에서 제대로 감싸진다.

**날짜를 박지 않는다** — 예전에 기대값에 날짜를 적어 둔 검사가 그날이 되자
깨졌다. 오늘을 기준으로 만들고 오늘을 기준으로 견준다.
"""
from __future__ import annotations

from datetime import date, timedelta
from urllib.parse import parse_qs, urlparse

import pytest

from app.services import calendar_link


def _query(url: str) -> dict:
    """주소의 물음표 뒤를 풀어 본다. 값이 하나뿐인 칸은 벗겨서 돌려준다."""
    parsed = urlparse(url)
    assert parsed.scheme == "https"
    assert parsed.netloc == "calendar.google.com"
    assert parsed.path == "/calendar/render"
    return {k: v[0] for k, v in parse_qs(parsed.query).items()}


# ── 1) 시각이 있는 미팅 ─────────────────────────────────────────────────────

def test_시각을_적어_둔_미팅은_한_시간짜리_일정이_된다():
    """끝나는 시각을 따로 받지 않는다. 투자사 미팅은 대개 한 시간이고,
    사람이 캘린더에서 늘리고 줄이면 그만이다."""
    when = date.today() + timedelta(days=3)
    url = calendar_link.meeting_url(when.isoformat(), "14:30", name="홍길동")

    q = _query(url)
    assert q["action"] == "TEMPLATE"
    assert q["dates"] == f"{when:%Y%m%d}T143000/{when:%Y%m%d}T153000"


def test_소요시간은_한_곳에서만_정해진다():
    """값이 코드 여기저기 흩어져 있으면 한 군데만 고쳐져 갈린다.
    ``DEFAULT_MINUTES`` 를 바꿨을 때 주소가 따라오면 한 곳이 맞다."""
    when = date.today()
    before = calendar_link.meeting_url(when.isoformat(), "09:00")
    assert _query(before)["dates"].endswith("T100000")

    original = calendar_link.DEFAULT_MINUTES
    try:
        calendar_link.DEFAULT_MINUTES = 30
        after = calendar_link.meeting_url(when.isoformat(), "09:00")
    finally:
        calendar_link.DEFAULT_MINUTES = original
    assert _query(after)["dates"].endswith("T093000")


def test_자정_직전_미팅은_다음_날로_넘어간다():
    """한 시간을 더하면 날짜가 바뀐다. 문자열을 잘라 붙이면 ``T240000`` 이 된다."""
    when = date.today()
    q = _query(calendar_link.meeting_url(when.isoformat(), "23:30"))
    tomorrow = when + timedelta(days=1)
    assert q["dates"] == f"{when:%Y%m%d}T233000/{tomorrow:%Y%m%d}T003000"


# ── 2) 시각이 없는 미팅 ─────────────────────────────────────────────────────

def test_시각이_없는_미팅은_종일_일정이_된다():
    """날짜만 아는 단계가 실제로 있다("다음 주 화요일쯤"). 없는 시각을
    ``00:00`` 으로 채우면 **자정 미팅**이 생기고, 사람은 그 시각을 진짜로 읽는다."""
    when = date.today() + timedelta(days=5)
    q = _query(calendar_link.meeting_url(when.isoformat(), ""))

    # 종일 일정에는 `T` 가 없다 — 있으면 시각을 지어낸 것이다.
    assert "T" not in q["dates"]
    assert "0000" not in q["dates"]
    # 구글은 끝날짜를 포함하지 않는다. 하루짜리는 **다음 날**로 끝난다.
    assert q["dates"] == f"{when:%Y%m%d}/{when + timedelta(days=1):%Y%m%d}"


@pytest.mark.parametrize("bad", [None, "", "  ", "오후 두시", "25:00"])
def test_읽을_수_없는_시각도_종일로_간다(bad):
    """저장할 때 `clean_time` 이 이미 걸렀지만, 걸리면 자정으로 채우지 않는다."""
    when = date.today()
    q = _query(calendar_link.meeting_url(when.isoformat(), bad))
    assert q["dates"] == f"{when:%Y%m%d}/{when + timedelta(days=1):%Y%m%d}"


def test_날짜를_못_읽으면_링크를_만들지_않는다():
    """눌러도 아무 일 없는 링크보다 없는 편이 낫다 — 화면이 안 그린다."""
    assert calendar_link.meeting_url("") == ""
    assert calendar_link.meeting_url(None) == ""
    assert calendar_link.meeting_url("다음 주") == ""


# ── 3) 시간대 ───────────────────────────────────────────────────────────────

def test_시간대가_한국으로_붙는다():
    """안 붙이면 구글이 **보는 사람의** 시간대로 읽는다."""
    q = _query(calendar_link.meeting_url(date.today().isoformat(), "10:00"))
    assert q["ctz"] == "Asia/Seoul"


def test_시간대는_TZ_하나가_정한다(monkeypatch):
    """``clock.py`` 와 같은 손잡이다 — 코드에 시간대를 박아 두지 않는다."""
    monkeypatch.setenv("TZ", "America/New_York")
    assert calendar_link.timezone_name() == "America/New_York"
    # 콜론이 붙는 꼴(`:Asia/Seoul`)도 실제로 쓰인다.
    monkeypatch.setenv("TZ", ":Asia/Tokyo")
    assert calendar_link.timezone_name() == "Asia/Tokyo"
    # 캘린더가 못 알아듣는 값이면 기본값으로 돌아간다.
    monkeypatch.setenv("TZ", "KST-9")
    assert calendar_link.timezone_name() == "Asia/Seoul"
    monkeypatch.delenv("TZ")
    assert calendar_link.timezone_name() == "Asia/Seoul"


# ── 4) 참석자 ───────────────────────────────────────────────────────────────

def test_참석자를_넣지_않는다():
    """``add=`` 를 붙이면 사람이 [저장] 을 누르는 순간 구글이 그 주소로
    **초대 메일을 실제로 보낸다.** 이쪽 화면을 정리하려던 것이 투자사
    담당자에게 나가는 메일이 된다. 되돌릴 수 없다."""
    url = calendar_link.meeting_url(
        date.today().isoformat(), "14:00",
        name="홍길동", title="심사역", firm="가나벤처스",
        kind_label="1차 미팅", company_name="샘플애그", note="자료 검토 뒤 논의")

    q = _query(url)
    assert "add" not in q, "참석자가 주소에 들어갔다 — 저장하면 초대 메일이 나간다"
    # 메일 주소가 어느 칸으로도 새어 들어가지 않는다.
    assert "@" not in url
    # 장소 칸은 만들지 않았다 — 없는 값을 지어내지 않는다.
    assert "location" not in q


def test_담당자_메일이_주소에_실리지_않는다(db, users):
    """미팅 줄은 담당자를 물고 있어 메일을 꺼내 붙이기 쉽다. 붙이면 사고다."""
    from app.models import Meeting, User, VcContact
    from app.services import pipeline

    contact = VcContact(user_id=users["u1"].id, name="홍길동", title="심사역",
                        firm="가나벤처스", email="hong@example.invalid",
                        connect_stage="connected")
    db.add(contact)
    db.flush()
    db.add(Meeting(user_id=users["u1"].id, contact_id=contact.id,
                   company_name="샘플애그",
                   scheduled_at=(date.today() + timedelta(days=2)).isoformat(),
                   scheduled_time="15:00"))
    db.commit()

    row = pipeline.meeting_rows(db, db.get(User, 1))[0]
    assert "hong@example.invalid" not in row["gcal_url"]
    assert "add=" not in row["gcal_url"]


# ── 5) 제목과 설명 ──────────────────────────────────────────────────────────

def test_제목에_누구를_만나는지가_앞에_온다():
    """달력 칸은 좁아 뒤가 잘린다. 잘려도 누구인지는 남아야 한다."""
    q = _query(calendar_link.meeting_url(
        date.today().isoformat(), "14:00",
        name="홍길동", title="심사역", firm="가나벤처스",
        kind_label="1차 미팅", company_name="샘플애그"))

    assert q["text"] == "홍길동 심사역 · 가나벤처스 1차 미팅 (샘플애그)"


def test_설명에_지금_있는_값이_담긴다():
    q = _query(calendar_link.meeting_url(
        date.today().isoformat(), "14:00",
        name="홍길동", title="심사역", firm="가나벤처스",
        kind_label="2차 미팅", company_name="샘플애그", note="자료 검토 뒤 논의"))

    assert q["details"].splitlines() == [
        "담당자: 홍길동 심사역",
        "소속: 가나벤처스",
        "구분: 2차 미팅",
        "대상 기업: 샘플애그",
        "메모: 자료 검토 뒤 논의",
    ]


def test_안_적어_둔_것은_지어내지도_빈_자리로_남기지도_않는다():
    """빈 칸을 `-` 로 채우면 캘린더에서는 '알아봤는데 없더라' 로 읽힌다."""
    q = _query(calendar_link.meeting_url(
        date.today().isoformat(), name="홍길동", kind_label="1차 미팅"))

    assert q["text"] == "홍길동 1차 미팅"          # 빈 괄호도 가운뎃점도 없다
    assert q["details"] == "담당자: 홍길동\n구분: 1차 미팅"
    assert "대상 기업" not in q["details"]


# ── 6) 감싸기 ───────────────────────────────────────────────────────────────

def test_한글과_공백이_주소에서_감싸진다():
    """감싸지 않으면 주소가 공백에서 끊기고, 한글은 브라우저마다 다르게 넘어간다."""
    url = calendar_link.meeting_url(
        date.today().isoformat(), "14:00",
        name="홍길동", title="심사역", firm="가나벤처스",
        kind_label="1차 미팅", company_name="샘플애그", note="자리 옮겨 진행")

    assert " " not in url
    assert "홍길동" not in url                    # 날것으로 실리지 않는다
    assert "%20" in url                           # 공백은 `+` 가 아니라 `%20`
    assert "\n" not in url and "%0A" in url       # 설명의 줄바꿈
    # 감싸 놓고 되풀면 적은 그대로다.
    assert "홍길동" in _query(url)["text"]
    assert "자리 옮겨 진행" in _query(url)["details"]


# ── 7) 화면 ─────────────────────────────────────────────────────────────────

@pytest.fixture()
def scheduled_meetings(db, users):
    """예정된 미팅 둘 — 시각을 적어 둔 것과 날짜만 아는 것."""
    from app.models import Meeting, VcContact

    contact = VcContact(user_id=users["u1"].id, name="홍길동", title="심사역",
                        firm="가나벤처스", connect_stage="connected")
    db.add(contact)
    db.flush()
    soon = date.today() + timedelta(days=4)
    rows = [
        Meeting(user_id=users["u1"].id, contact_id=contact.id,
                company_name="샘플애그", scheduled_at=soon.isoformat(),
                scheduled_time="14:30"),
        Meeting(user_id=users["u1"].id, contact_id=contact.id,
                scheduled_at=soon.isoformat()),
    ]
    db.add_all(rows)
    db.commit()
    return {"contact": contact, "when": soon, "timed": rows[0], "bare": rows[1]}


def test_예정된_미팅_줄에_캘린더_링크가_있다(logged_in, scheduled_meetings):
    """새 탭에서 열려야 한다 — 같은 탭이면 적던 것을 두고 화면을 떠난다."""
    html = logged_in.get("/ir").text

    assert "구글 캘린더에 추가" in html
    assert html.count("calendar.google.com/calendar/render") >= 2, \
        "시각이 없는 미팅에는 링크가 안 붙었다"
    for part in ('target="_blank"', 'rel="noopener"'):
        assert part in html


def test_화면의_링크에도_참석자가_없다(logged_in, scheduled_meetings):
    """규칙이 한 곳에 있어도 화면이 따로 조립하면 거기서 새어 나간다."""
    html = logged_in.get("/ir").text
    for chunk in html.split("calendar.google.com/calendar/render")[1:]:
        link = chunk.split('"')[0]
        assert "add=" not in link
        assert "%40" not in link and "@" not in link


def test_화면이_주소를_따로_조립하지_않는다():
    """같은 규칙을 두 군데 적으면 한쪽만 고쳐져 갈린다."""
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    made = [p for p in (root / "app").rglob("*")
            if p.is_file() and p.suffix in {".py", ".html", ".js"}
            and "calendar.google.com" in p.read_text(encoding="utf-8")]
    assert [p.name for p in made] == ["calendar_link.py"]
