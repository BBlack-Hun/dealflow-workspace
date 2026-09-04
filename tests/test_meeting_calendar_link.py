"""미팅 → **구글 캘린더에 추가** 링크.

이 링크가 하는 일은 주소 문자열 하나를 만들어 화면에 놓는 것뿐이다. 그래서
검사할 것도 주소 하나지만, 틀리면 조용히 틀린다 — 캘린더 화면은 뜨는데
엉뚱한 시각이 잡히거나(시간대), 안 넣기로 한 것이 들어가 있거나.

여기서 지키는 것
1. **한 일정에 그날 그 담당자의 미팅이 다 담긴다.** 첫 미팅부터 마지막 미팅
   + 한 시간까지. 건마다 따로 넣으면 하루에 같은 자리로 칸이 셋 생긴다.
2. **없는 값을 지어내지 않는다.** 주소·번호·시각이 빈 담당자가 실제로 있다.
   빈 줄로 남기지도, `-` 로 채우지도 않는다 — 줄이 통째로 빠진다.
3. **시간대는 한국.** 안 적으면 구글이 보는 사람의 시간대로 읽어, 해외에서
   열면 다른 시각에 잡힌다.
4. **참석자를 넣지 않는다.** ← 여기가 제일 위험하다. ``add=`` 를 붙이면
   사람이 [저장] 을 누르는 순간 구글이 그 주소로 **초대 메일을 실제로 보낸다.**
   되돌릴 수 없다.
5. 한글과 공백이 주소에서 제대로 감싸진다.

**날짜를 박지 않는다** — 예전에 기대값에 날짜를 적어 둔 검사가 그날이 되자
깨졌다. 오늘을 기준으로 만들고 오늘을 기준으로 견준다.

**이름·상호·번호·주소는 전부 가짜다.** 이 저장소는 공개되어 있다.
"""
from __future__ import annotations

from datetime import date, timedelta
from urllib.parse import parse_qs, urlparse

import pytest

from app.services import calendar_link

# 검사에 쓰는 가짜 담당자 한 사람. 실제 명단과 아무 관계가 없다.
WHO = dict(contact_name="홍길동", contact_title="상무", firm="마바벤처스",
           phone="010-0000-0000", address="서울특별시 마포구 가나로 100")


def _query(url: str) -> dict:
    """주소의 물음표 뒤를 풀어 본다. 값이 하나뿐인 칸은 벗겨서 돌려준다."""
    parsed = urlparse(url)
    assert parsed.scheme == "https"
    assert parsed.netloc == "calendar.google.com"
    assert parsed.path == "/calendar/render"
    return {k: v[0] for k, v in parse_qs(parsed.query).items()}


def _label(when: date) -> str:
    """`2026-08-24(월)` — 기대값에도 요일을 날짜에서 계산해 넣는다."""
    return f"{when.isoformat()}({calendar_link.WEEKDAYS[when.weekday()]})"


def _meet(when: date, at: str = "", company: str = "", assignee: str = "") -> dict:
    return {"date": when.isoformat(), "time": at,
            "company": company, "assignee": assignee}


# ── 1) 묶인 일정 ────────────────────────────────────────────────────────────

def test_같은_날_같은_담당자의_미팅_둘이_한_일정에_담긴다():
    """투자사 한 분을 만나 그 자리에서 기업을 잇달아 소개한다. 건마다 따로
    넣으면 같은 장소로 하루에 칸이 둘 생기고, 정작 **몇 시부터 몇 시까지
    비워야 하는지**가 안 보인다."""
    when = date.today() + timedelta(days=3)
    q = _query(calendar_link.group_url(
        user_name="강민준", meetings=[
            _meet(when, "13:20", "가나컴퍼니", "관리1팀"),
            _meet(when, "14:30", "다라컴퍼니", "관리1팀"),
        ], **WHO))

    assert q["text"] == (
        "[강민준/관리1팀/마포구] 가나컴퍼니, 다라컴퍼니 IR 미팅"
        " / 투자사 마바벤처스 홍길동 상무")
    assert q["details"].split("\n") == [
        "홍길동 상무",
        "010-0000-0000",
        "마바벤처스 상무",
        "서울특별시 마포구 가나로 100",
        "",
        "",
        "- 업체1 : 가나컴퍼니",
        f"- 미팅 일정 : {_label(when)} 13:20",
        "",
        "- 업체2 : 다라컴퍼니",
        f"- 미팅 일정 : {_label(when)} 14:30",
    ]


def test_끝나는_시각은_마지막_미팅_한_시간_뒤다():
    """첫 미팅에 한 시간을 더하면 뒤 미팅이 일정 밖으로 나간다 — 캘린더에는
    비어 있는 것으로 보이고 그 시간에 다른 약속이 잡힌다."""
    when = date.today() + timedelta(days=2)
    q = _query(calendar_link.group_url(meetings=[
        _meet(when, "13:20", "가나컴퍼니"),
        _meet(when, "14:30", "다라컴퍼니"),
    ], **WHO))

    assert q["dates"] == f"{when:%Y%m%d}T132000/{when:%Y%m%d}T153000"


def test_적어_둔_차례가_거꾸로여도_이른_시각부터_적힌다():
    """화면의 미팅 표는 최근 것이 위로 오게 내림차순이다. 그대로 실으면
    설명이 오후부터 거꾸로 적히고, 시작 시각도 뒤 미팅이 된다."""
    when = date.today() + timedelta(days=2)
    q = _query(calendar_link.group_url(meetings=[
        _meet(when, "14:30", "다라컴퍼니"),
        _meet(when, "13:20", "가나컴퍼니"),
    ], **WHO))

    assert q["dates"].startswith(f"{when:%Y%m%d}T132000/")
    assert q["details"].index("가나컴퍼니") < q["details"].index("다라컴퍼니")


def test_소요시간은_한_곳에서만_정해진다():
    """값이 코드 여기저기 흩어져 있으면 한 군데만 고쳐져 갈린다.
    ``DEFAULT_MINUTES`` 를 바꿨을 때 주소가 따라오면 한 곳이 맞다."""
    when = date.today()
    before = calendar_link.group_url(meetings=[_meet(when, "09:00")])
    assert _query(before)["dates"].endswith("T100000")

    original = calendar_link.DEFAULT_MINUTES
    try:
        calendar_link.DEFAULT_MINUTES = 30
        after = calendar_link.group_url(meetings=[_meet(when, "09:00")])
    finally:
        calendar_link.DEFAULT_MINUTES = original
    assert _query(after)["dates"].endswith("T093000")


def test_자정_직전_미팅은_다음_날로_넘어간다():
    """한 시간을 더하면 날짜가 바뀐다. 문자열을 잘라 붙이면 ``T240000`` 이 된다."""
    when = date.today()
    q = _query(calendar_link.group_url(meetings=[_meet(when, "23:30")]))
    tomorrow = when + timedelta(days=1)
    assert q["dates"] == f"{when:%Y%m%d}T233000/{tomorrow:%Y%m%d}T003000"


# ── 2) 기업이 하나뿐일 때 ───────────────────────────────────────────────────

def test_기업이_하나여도_업체1_로_적는다():
    """번호를 뗀 양식을 따로 두면 하루 뒤에 미팅이 하나 더 붙는 순간 같은
    일정의 모양이 바뀐다 — 사람이 눈으로 좇던 자리가 옮겨 간다."""
    when = date.today() + timedelta(days=1)
    q = _query(calendar_link.group_url(
        user_name="강민준",
        meetings=[_meet(when, "10:00", "가나컴퍼니", "관리1팀")], **WHO))

    assert q["text"] == ("[강민준/관리1팀/마포구] 가나컴퍼니 IR 미팅"
                        " / 투자사 마바벤처스 홍길동 상무")
    assert q["details"].endswith(
        f"- 업체1 : 가나컴퍼니\n- 미팅 일정 : {_label(when)} 10:00")
    assert q["dates"] == f"{when:%Y%m%d}T100000/{when:%Y%m%d}T110000"


def test_같은_기업을_하루에_두_번_봐도_제목에_한_번만_선다():
    """제목에 같은 이름이 두 번 서면 읽는 사람이 다른 기업으로 센다.
    설명에는 **두 자리 그대로** 남는다 — 두 번 만나는 것이 사실이다."""
    when = date.today() + timedelta(days=1)
    q = _query(calendar_link.group_url(meetings=[
        _meet(when, "10:00", "가나컴퍼니"),
        _meet(when, "16:00", "가나컴퍼니"),
    ], **WHO))

    assert q["text"].count("가나컴퍼니") == 1
    assert q["details"].count("가나컴퍼니") == 2


# ── 3) 기업 담당자 ──────────────────────────────────────────────────────────

def test_기업_담당자가_서로_다르면_둘_다_적는다():
    """하나를 골라 적으면 나머지 기업의 담당자에게는 그 미팅이 제 것으로
    안 보인다. 제목이 짧아지는 대신 사람이 빠진다."""
    when = date.today() + timedelta(days=1)
    q = _query(calendar_link.group_url(user_name="강민준", meetings=[
        _meet(when, "13:00", "가나컴퍼니", "관리1팀"),
        _meet(when, "15:00", "다라컴퍼니", "관리2팀"),
    ], **WHO))

    assert q["text"].startswith("[강민준/관리1팀, 관리2팀/마포구]")


def test_기업_담당자가_같으면_한_번만_적는다():
    when = date.today() + timedelta(days=1)
    q = _query(calendar_link.group_url(user_name="강민준", meetings=[
        _meet(when, "13:00", "가나컴퍼니", "관리1팀"),
        _meet(when, "15:00", "다라컴퍼니", "관리1팀"),
    ], **WHO))

    assert q["text"].startswith("[강민준/관리1팀/마포구]")


def test_담당자를_안_적어_둔_기업은_그_자리가_빈다():
    """빈 칸을 남기면(`[강민준//마포구]`) 무엇이 빠졌는지가 아니라
    **뭔가 깨졌다**로 읽힌다."""
    when = date.today() + timedelta(days=1)
    q = _query(calendar_link.group_url(
        user_name="강민준", meetings=[_meet(when, "13:00", "가나컴퍼니")], **WHO))

    assert q["text"].startswith("[강민준/마포구] 가나컴퍼니 IR 미팅")


# ── 4) 지역구 ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize("address, expected", [
    ("서울특별시 마포구 가나로 100", "마포구"),
    ("서울시 성동구 다라길 1, 2층", "성동구"),
    ("서울 종로구 마바대로 3", "종로구"),
    # 광역 뒤에 시가 오면 그 시가 지역이다. **맨 앞 토막은 건너뛴다** —
    # 거기는 `서울특별시` 처럼 광역 이름이라 지역구가 아니다.
    ("경기도 가나시 다라구 마바로 7", "다라구"),
    ("경상남도 가나시 다라로 9", "가나시"),
    ("경기도 가나군 다라면 마바리 12", "가나군"),
])
def test_주소에서_지역구_한_토막을_집는다(address, expected):
    """제목 앞머리에 어디로 가는지가 있어야 아침에 동선을 짠다. 주소를
    통째로 실으면 달력 칸에서 그 줄만 남고 기업 이름이 잘린다."""
    assert calendar_link.district_of(address) == expected


@pytest.mark.parametrize("address", [
    None, "", "   ",
    "세종특별자치시 가나로 100",        # 구·군·시 토막이 없다
    "12F, 34 Gana-daero, Seoul",       # 영문 주소
])
def test_지역구를_못_읽으면_지어내지_않는다(address):
    """틀린 동네를 적어 두면 사람이 그리로 간다. 못 읽었으면 그 자리가
    통째로 빠질 뿐이다."""
    assert calendar_link.district_of(address) == ""


# ── 5) 주소 ─────────────────────────────────────────────────────────────────

def test_담당자_주소가_장소로_들어간다():
    when = date.today() + timedelta(days=1)
    q = _query(calendar_link.group_url(meetings=[_meet(when, "10:00")], **WHO))
    assert q["location"] == "서울특별시 마포구 가나로 100"


def test_주소가_없으면_장소_칸을_만들지_않는다():
    """빈 장소를 넣으면 캘린더가 그 자리를 지도로 찍으려다 엉뚱한 곳을 가리킨다.
    제목의 지역구 자리도 함께 빠지고, 설명에서 주소 줄이 사라진다."""
    when = date.today() + timedelta(days=1)
    q = _query(calendar_link.group_url(
        user_name="강민준", contact_name="홍길동", contact_title="상무",
        firm="마바벤처스", phone="010-0000-0000", address="",
        meetings=[_meet(when, "10:00", "가나컴퍼니", "관리1팀")]))

    assert "location" not in q
    assert q["text"].startswith("[강민준/관리1팀] 가나컴퍼니 IR 미팅")
    assert q["details"].split("\n\n\n")[0].split("\n") == [
        "홍길동 상무", "010-0000-0000", "마바벤처스 상무"]


# ── 6) 전화번호 ─────────────────────────────────────────────────────────────

def test_휴대폰이_먼저고_없으면_유선으로_내려간다():
    """가는 길에 늦는다고 거는 번호는 사무실이 아니라 손에 든 쪽이다."""
    assert calendar_link.phone_for("010-0000-0000", "02-000-0000") == "010-0000-0000"
    assert calendar_link.phone_for("", "02-000-0000") == "02-000-0000"
    assert calendar_link.phone_for(None, None) == ""


def test_번호가_아예_없으면_그_줄이_통째로_빠진다():
    """빈 줄로 남기면 이름 아래에 빈 자리가 생겨 무엇이 빠졌는지 알 수 없고,
    `-` 로 채우면 '알아봤는데 없더라' 로 읽힌다."""
    when = date.today() + timedelta(days=1)
    q = _query(calendar_link.group_url(
        contact_name="홍길동", contact_title="상무", firm="마바벤처스",
        address="서울특별시 마포구 가나로 100",
        meetings=[_meet(when, "10:00", "가나컴퍼니")]))

    head = q["details"].split("\n\n\n")[0].split("\n")
    assert head == ["홍길동 상무", "마바벤처스 상무", "서울특별시 마포구 가나로 100"]
    assert "" not in head


def test_유선만_있으면_유선이_적힌다():
    when = date.today() + timedelta(days=1)
    q = _query(calendar_link.group_url(
        contact_name="홍길동", contact_title="상무", office_phone="02-000-0000",
        meetings=[_meet(when, "10:00")]))

    assert q["details"].split("\n")[:2] == ["홍길동 상무", "02-000-0000"]


# ── 7) 시각이 없는 미팅 ─────────────────────────────────────────────────────

def test_시각을_모르는_건은_일정의_폭을_정하지_않는다():
    """자정으로 치면 아침 아홉 시부터 비워 놓게 되고, 묶음 전체를 종일로
    돌리면 적어 둔 시각이 사라진다. 그 건은 **설명에 날짜만** 적혀 남는다."""
    when = date.today() + timedelta(days=4)
    q = _query(calendar_link.group_url(meetings=[
        _meet(when, "", "가나컴퍼니"),
        _meet(when, "13:00", "다라컴퍼니"),
    ], **WHO))

    assert q["dates"] == f"{when:%Y%m%d}T130000/{when:%Y%m%d}T140000"
    # 시각 없는 건이 사라지지 않는다 — 다만 맨 뒤로 간다.
    assert q["details"].endswith(f"- 업체2 : 가나컴퍼니\n- 미팅 일정 : {_label(when)}")
    assert q["details"].count("업체") == 2


def test_아무_건에도_시각이_없으면_종일_일정이_된다():
    """날짜만 아는 단계가 실제로 있다("다음 주 화요일쯤"). 없는 시각을
    ``00:00`` 으로 채우면 **자정 미팅**이 생기고, 사람은 그 시각을 진짜로 읽는다."""
    when = date.today() + timedelta(days=5)
    q = _query(calendar_link.group_url(meetings=[_meet(when)], **WHO))

    # 종일 일정에는 `T` 가 없다 — 있으면 시각을 지어낸 것이다.
    assert "T" not in q["dates"]
    assert "0000" not in q["dates"]
    # 구글은 끝날짜를 포함하지 않는다. 하루짜리는 **다음 날**로 끝난다.
    assert q["dates"] == f"{when:%Y%m%d}/{when + timedelta(days=1):%Y%m%d}"


@pytest.mark.parametrize("bad", [None, "", "  ", "오후 두시", "25:00"])
def test_읽을_수_없는_시각도_종일로_간다(bad):
    """저장할 때 `clean_time` 이 이미 걸렀지만, 걸리면 자정으로 채우지 않는다."""
    when = date.today()
    q = _query(calendar_link.group_url(
        meetings=[{"date": when.isoformat(), "time": bad}]))
    assert q["dates"] == f"{when:%Y%m%d}/{when + timedelta(days=1):%Y%m%d}"


def test_날짜를_못_읽으면_링크를_만들지_않는다():
    """눌러도 아무 일 없는 링크보다 없는 편이 낫다 — 화면이 안 그린다."""
    assert calendar_link.group_url(meetings=[]) == ""
    assert calendar_link.group_url(meetings=[{"date": ""}]) == ""
    assert calendar_link.group_url(meetings=[{"date": None}]) == ""
    assert calendar_link.group_url(meetings=[{"date": "다음 주"}]) == ""


# ── 8) 시간대 ───────────────────────────────────────────────────────────────

def test_시간대가_한국으로_붙는다():
    """안 붙이면 구글이 **보는 사람의** 시간대로 읽는다."""
    q = _query(calendar_link.group_url(
        meetings=[_meet(date.today(), "10:00")]))
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


# ── 9) 참석자 ───────────────────────────────────────────────────────────────

def test_참석자를_넣지_않는다():
    """``add=`` 를 붙이면 사람이 [저장] 을 누르는 순간 구글이 그 주소로
    **초대 메일을 실제로 보낸다.** 이쪽 화면을 정리하려던 것이 투자사
    담당자에게 나가는 메일이 된다. 되돌릴 수 없다."""
    when = date.today()
    url = calendar_link.group_url(user_name="강민준", meetings=[
        _meet(when, "13:20", "가나컴퍼니", "관리1팀"),
        _meet(when, "14:30", "다라컴퍼니", "관리1팀"),
    ], **WHO)

    q = _query(url)
    assert "add" not in q, "참석자가 주소에 들어갔다 — 저장하면 초대 메일이 나간다"
    # 메일 주소가 어느 칸으로도 새어 들어가지 않는다.
    assert "@" not in url and "%40" not in url


def test_담당자_메일이_주소에_실리지_않는다(db, users):
    """미팅 줄은 담당자를 물고 있어 메일을 꺼내 붙이기 쉽다. 붙이면 사고다."""
    from app.models import Meeting, User, VcContact
    from app.services import pipeline

    contact = VcContact(user_id=users["u1"].id, name="홍길동", title="상무",
                        firm="마바벤처스", email="hong@example.invalid",
                        connect_stage="connected")
    db.add(contact)
    db.flush()
    db.add(Meeting(user_id=users["u1"].id, contact_id=contact.id,
                   company_name="가나컴퍼니",
                   scheduled_at=(date.today() + timedelta(days=2)).isoformat(),
                   scheduled_time="15:00"))
    db.commit()

    row = pipeline.meeting_rows(db, db.get(User, 1))[0]
    assert "hong@example.invalid" not in row["gcal_url"]
    assert "add=" not in row["gcal_url"]


# ── 10) 감싸기 ──────────────────────────────────────────────────────────────

def test_한글과_공백이_주소에서_감싸진다():
    """감싸지 않으면 주소가 공백에서 끊기고, 한글은 브라우저마다 다르게 넘어간다."""
    when = date.today()
    url = calendar_link.group_url(
        user_name="강민준",
        meetings=[_meet(when, "14:00", "가나컴퍼니", "관리1팀")], **WHO)

    assert " " not in url
    assert "홍길동" not in url                    # 날것으로 실리지 않는다
    assert "%20" in url                           # 공백은 `+` 가 아니라 `%20`
    assert "\n" not in url and "%0A" in url       # 설명의 줄바꿈
    # 감싸 놓고 되풀면 적은 그대로다.
    assert "홍길동" in _query(url)["text"]
    assert "가나로" in _query(url)["location"]


# ── 11) 화면 ────────────────────────────────────────────────────────────────

@pytest.fixture()
def scheduled_meetings(db, users):
    """예정된 미팅 셋 — 같은 날 같은 담당자 둘(묶인다) 과 날짜만 아는 하나."""
    from app.models import IrCompany, Meeting, VcContact

    contact = VcContact(user_id=users["u1"].id, name="홍길동", title="상무",
                        firm="마바벤처스", phone="010-0000-0000",
                        address="서울특별시 마포구 가나로 100",
                        connect_stage="connected")
    company = IrCompany(name="가나컴퍼니", assignee_name="관리1팀")
    other = IrCompany(name="다라컴퍼니", assignee_name="관리2팀")
    db.add_all([contact, company, other])
    db.flush()
    soon = date.today() + timedelta(days=4)
    later = date.today() + timedelta(days=6)
    rows = [
        Meeting(user_id=users["u1"].id, contact_id=contact.id,
                company_id=company.id, company_name="가나컴퍼니",
                scheduled_at=soon.isoformat(), scheduled_time="13:20"),
        Meeting(user_id=users["u1"].id, contact_id=contact.id,
                company_id=other.id, company_name="다라컴퍼니",
                scheduled_at=soon.isoformat(), scheduled_time="14:30"),
        Meeting(user_id=users["u1"].id, contact_id=contact.id,
                scheduled_at=later.isoformat()),
    ]
    db.add_all(rows)
    db.commit()
    return {"contact": contact, "when": soon, "rows": rows}


def test_묶인_두_줄이_같은_주소를_들고_있다(db, users, scheduled_meetings):
    """줄마다 다른 일정이 나오면 하루에 칸이 둘 생긴다. 같은 주소여야
    어느 줄에서 눌러도 그 일정 하나가 뜬다."""
    from app.models import User
    from app.services import pipeline

    rows = {r["id"]: r for r in pipeline.meeting_rows(db, db.get(User, 1))}
    first, second, alone = scheduled_meetings["rows"]

    assert rows[first.id]["gcal_url"] == rows[second.id]["gcal_url"]
    assert rows[first.id]["gcal_count"] == 2
    assert rows[alone.id]["gcal_url"] != rows[first.id]["gcal_url"]
    assert rows[alone.id]["gcal_count"] == 1

    q = _query(rows[first.id]["gcal_url"])
    when = scheduled_meetings["when"]
    assert q["dates"] == f"{when:%Y%m%d}T132000/{when:%Y%m%d}T153000"
    # 기업 담당자는 **IR 기업 현황의 `담당자` 칸**에서 온다.
    assert q["text"].startswith("[강민준/관리1팀, 관리2팀/마포구]")


def test_취소된_건은_예정된_건과_한_일정에_섞이지_않는다(db, users):
    """사람이 저장하는 순간 안 가는 미팅이 캘린더에 적힌다."""
    from app.models import Meeting, User, VcContact
    from app.services import pipeline

    contact = VcContact(user_id=users["u1"].id, name="홍길동", title="상무",
                        firm="마바벤처스", connect_stage="connected")
    db.add(contact)
    db.flush()
    when = date.today() + timedelta(days=3)
    keep = Meeting(user_id=users["u1"].id, contact_id=contact.id,
                   company_name="가나컴퍼니", scheduled_at=when.isoformat(),
                   scheduled_time="13:00")
    gone = Meeting(user_id=users["u1"].id, contact_id=contact.id,
                   company_name="다라컴퍼니", scheduled_at=when.isoformat(),
                   scheduled_time="16:00", status="canceled")
    db.add_all([keep, gone])
    db.commit()

    rows = {r["id"]: r for r in pipeline.meeting_rows(db, db.get(User, 1))}
    assert rows[keep.id]["gcal_count"] == 1
    assert "다라컴퍼니" not in _query(rows[keep.id]["gcal_url"])["details"]


def test_예정된_미팅_줄에_캘린더_링크가_있다(logged_in, scheduled_meetings):
    """새 탭에서 열려야 한다 — 같은 탭이면 적던 것을 두고 화면을 떠난다."""
    html = logged_in.get("/ir").text

    assert "구글 캘린더에 추가" in html
    assert html.count("calendar.google.com/calendar/render") >= 3, \
        "시각이 없는 미팅에는 링크가 안 붙었다"
    for part in ('target="_blank"', 'rel="noopener"'):
        assert part in html


def test_묶인_줄에는_몇_건짜리인지_적힌다(logged_in, scheduled_meetings):
    """안 적으면 두 줄에서 두 번 눌러 같은 일정을 두 개 만든다."""
    html = logged_in.get("/ir").text
    assert "2건" in html


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


# ── 12) 주소로 못 정하는 것 ─────────────────────────────────────────────────

def test_알림과_담을_캘린더는_주소에_없다():
    """``action=TEMPLATE`` 가 받는 칸이 아니다. 붙여 봐야 구글이 버리는데,
    코드에 남아 있으면 다음 사람이 '되는 것' 으로 읽는다. 되는 척 하지 않는다 —
    사람이 저장 화면에서 고른다(화면의 링크 설명에 적어 두었다)."""
    when = date.today()
    q = _query(calendar_link.group_url(meetings=[_meet(when, "10:00")], **WHO))

    assert set(q) <= {"action", "text", "dates", "ctz", "location", "details"}
