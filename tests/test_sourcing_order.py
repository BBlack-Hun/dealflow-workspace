"""딜 소싱 명단의 차례 — **참여 요청일 최신순**.

`참여 요청일` 은 사람이 손으로 적은 **글자**라 표기가 섞여 있다(실측 40줄 중
`2026-07-01 00:00:00` 16곳 · `2026/05/21` 9곳 · 빈 곳 10곳). 글자로 세우면
`/`(0x2F) 가 `-`(0x2D) 보다 커서 `2026/05/21` 이 `2026-08-11` 위로 올라온다 —
최신순이라고 해 놓고 석 달 전 줄이 맨 위에 서는 것이라, 여기 픽스처는 일부러
**글자 정렬이었으면 틀렸을 배치**로 짜 두었다.

날짜는 못 박는다. `오늘` 로 지으면 하루 지나 깨지는 검사가 된다.
"""
from __future__ import annotations

import re

import pytest

from .conftest import DEMO_PASSWORD

BUCKET = "시리즈 A 이상"
OTHER = "M&A 찾는 투자사"
OTHER_HTML = OTHER.replace("&", "&amp;")

# 원본 시트에서 옮겨 온 차례(`position`)와 참여 요청일이 **일부러 어긋나 있다** —
# 요청일로 세우면 시트 차례가 뒤집혀야 하고, 같은 날인 두 줄에서만 시트 차례가
# 남는다.
ROWS = [
    # position, 이름, 참여 요청일(적힌 그대로)
    (0, "가나", "2026/05/21"),            # 슬래시 — 가장 오래됐다
    (1, "나다", "2026-08-11 00:00:00"),   # 하이픈 + 시각
    (2, "다라", "2026-07-01 00:00:00"),
    (3, "마바", "2026/09/02"),            # 가장 최근
    (4, "바사", "2026/07/01"),            # `다라` 와 **같은 날**, 표기만 다르다
    (5, "아자", "미정"),                  # 날짜가 아니다
    (6, "자차", None),                    # 빈 곳
]

#: 요청일 최신순. 같은 날(`다라`·`바사`)에서는 시트 차례가 남고, 못 읽는 값과
#: 빈 값은 맨 아래다.
EXPECTED = ["마바", "나다", "다라", "바사", "가나", "아자", "자차"]

#: 같은 값을 **글자**로 내림차순 세웠을 때의 차례. 한글(`미정`)이 숫자보다 커서
#: 맨 위로 오고, 슬래시 표기가 하이픈 표기를 통째로 밀어 올린다.
LETTER_ORDER = ["아자", "마바", "바사", "가나", "나다", "다라", "자차"]


@pytest.fixture()
def seeded(client, db, users):
    from app.models import SourcingContact

    db.add_all([
        SourcingContact(bucket=BUCKET, position=pos, name=name,
                        requested_at=when, firm="샘플벤처스")
        for pos, name, when in ROWS
    ])
    # 다른 갈래. 명단 전체에서 **가장 최근** 줄이 여기 있어서, 갈래 차례를
    # 명단에서 훑어 세면 이 갈래가 위로 올라온다.
    db.add(SourcingContact(bucket=OTHER, position=1000, name="차카",
                           requested_at="2026-12-24 00:00:00",
                           firm="샘플인베스트"))
    db.commit()
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    return client


def _tbody(body: str) -> str:
    return body[body.index("<tbody>"):body.index("</tbody>")]


def names_on(body: str) -> list:
    """표에 뜬 차례 그대로의 이름."""
    return re.findall(r'data-field="name">([^<]*)<', _tbody(body))


def dates_on(body: str) -> list:
    """표에 뜬 차례 그대로의 참여 요청일 — **적힌 글자 그대로**."""
    return [x.strip() for x in
            re.findall(r'data-field="requested_at">([^<]*)<', _tbody(body))]


# --- 섞인 표기 --------------------------------------------------------------

def test_the_fixture_would_fail_a_letter_sort():
    """픽스처에 **판별력이 있는가**. 두 차례가 같아지면 이 파일은 아무것도 못 지킨다."""
    assert EXPECTED != LETTER_ORDER
    assert sorted(EXPECTED) == sorted(LETTER_ORDER)


def test_the_newest_requested_comes_first(seeded):
    """섞인 표기를 날짜로 읽어 세운다."""
    assert names_on(seeded.get("/sourcing", params={"tab": BUCKET}).text) == EXPECTED


def test_letters_would_have_put_the_older_slash_row_on_top(seeded):
    """`/` 가 `-` 보다 커서, 글자로 세우면 5월 줄이 8월·7월 줄 위로 올라온다."""
    order = names_on(seeded.get("/sourcing", params={"tab": BUCKET}).text)
    assert order != LETTER_ORDER
    assert order.index("나다") < order.index("가나")   # 8/11 이 5/21 보다 위
    assert order.index("다라") < order.index("가나")   # 7/1  이 5/21 보다 위
    assert order[0] == "마바"                          # 9/2 가 맨 위


def test_both_notations_land_on_the_same_day():
    """표기가 달라도 같은 날이다 — 글자가 아니라 날짜로 읽는다는 뜻이다."""
    from datetime import date

    from app.models import SourcingContact
    from app.routers.sourcing import requested_on

    def when(value):
        return requested_on(SourcingContact(bucket=BUCKET, name="가나",
                                            requested_at=value))

    assert when("2026/07/01") == when("2026-07-01 00:00:00") == date(2026, 7, 1)
    assert when("2026.07.01") == when("2026-7-1") == date(2026, 7, 1)
    # 뒤에 말이 붙어도 앞의 날짜로 자리를 잡는다 — 통째로 밀어 내는 것보다 낫다
    assert when("2026-07-01 (재확인)") == date(2026, 7, 1)
    # 못 읽는 값·빈 값·달력에 없는 날은 없는 것으로 본다
    for value in ("미정", "", None, "6월 말쯤", "2026-02-31"):
        assert when(value) is None, value


# --- 못 읽는 값과 빈 값 -----------------------------------------------------

def test_unreadable_and_empty_go_to_the_bottom(seeded):
    """위로 올리면 '최신순' 이 거짓이 되고, 사이에 섞으면 어디까지가 날짜순인지
    눈으로 가를 수 없다."""
    body = seeded.get("/sourcing", params={"tab": BUCKET}).text
    assert names_on(body)[-2:] == ["아자", "자차"]

    # 날짜가 있는 줄은 하나도 그 아래로 내려가지 않는다
    shown = dates_on(body)
    assert shown[-2:] == ["미정", ""]
    assert all(x.startswith("2026") for x in shown[:-2])


def test_the_written_value_is_left_alone(seeded, db):
    """표기를 통일하려고 저장된 글자를 바꾸면 사람이 적어 둔 원문이 사라진다 —
    읽을 때만 날짜로 해석한다."""
    from app.models import SourcingContact

    shown = dates_on(seeded.get("/sourcing", params={"tab": BUCKET}).text)
    assert "2026/05/21" in shown and "2026-08-11 00:00:00" in shown

    stored = {r.name: r.requested_at for r in db.query(SourcingContact).all()}
    assert stored == {name: when for _pos, name, when in ROWS} | {
        "차카": "2026-12-24 00:00:00"}


# --- `position` 이 지키는 것 -------------------------------------------------
#
# `position` 은 **원본 시트에서 옮겨 온 차례**(`scripts/import_sourcing.py` 가
# `시트번호 * 1000 + 줄번호` 로 넣는다)이자 새 줄이 그 갈래 맨 아래로 가는
# 근거다. 사람이 끌어 옮기는 차례가 아니라 고칠 길이 아예 없다. 요청일 정렬을
# 앞에 세우되, 그 두 뜻은 그대로 남긴다.

def test_the_same_day_keeps_the_sheet_order(seeded):
    """요청일이 같은 두 줄은 여전히 시트에서 옮겨 온 차례다."""
    order = names_on(seeded.get("/sourcing", params={"tab": BUCKET}).text)
    assert order.index("다라") < order.index("바사")


def test_the_bucket_tabs_are_still_in_sheet_order(seeded):
    """갈래 차례까지 요청일로 세우면, 누가 어느 날 수락했느냐에 따라 왼쪽 탭이
    매일 자리를 바꾼다. 가장 최근 줄은 뒤 갈래에 있지만 탭 차례는 그대로다."""
    body = seeded.get("/sourcing", params={"tab": "all"}).text
    # 좌측 메뉴도 `<nav>` 라, 닫는 자리는 **탭 줄이 시작한 뒤**에서 찾는다.
    head = body.index('<nav class="sheet-tabs">')
    nav = body[head:body.index("</nav>", head)]
    assert nav.index(BUCKET) < nav.index(OTHER_HTML)


def test_a_new_row_still_lands_at_the_bottom_of_its_bucket(seeded, db):
    """전화로 승낙받아 넣은 줄은 요청일이 비어 있다 — 번호도 화면 자리도 맨 아래."""
    from app.models import SourcingContact

    made = seeded.post("/api/sourcing", params={"bucket": BUCKET},
                       json={"name": "타파"})
    assert made.status_code == 200, made.text
    assert db.get(SourcingContact, made.json()["id"]).position == 7

    assert names_on(seeded.get("/sourcing", params={"tab": BUCKET}).text)[-1] == "타파"


# --- 한 곳에서만 정한다 ------------------------------------------------------

def test_the_send_picker_reads_the_same_order(seeded):
    """같은 명단이 화면마다 다른 순서로 뜨면 어느 쪽이 최신인지 알 수 없다.

    딜 제안 관리의 [딜 소싱 제안] 목록도 `rows_of` 를 지난다.
    """
    picker = seeded.get("/deals").text
    picker = picker[picker.index('id="sourcing-list"'):]
    cards = [x.strip() for x in re.findall(r'<div class="pick-name">([^<]*)<', picker)]
    # 갈래를 가리지 않은 전체 명단이라, 12월 줄을 가진 다른 갈래가 맨 위다
    assert cards == ["차카"] + EXPECTED


def test_the_send_picker_buckets_keep_the_sheet_order(seeded):
    """갈래 칩도 좌측 [딜 소싱] 탭과 같은 차례여야 한다 — 명단을 훑어 세면
    그날의 날짜를 따라 흔들린다."""
    bar = seeded.get("/deals").text
    bar = bar[bar.index('id="bucket-filter"'):]
    assert re.findall(r'data-value="([^"]*)"', bar[:bar.index("</div>")]) == [
        "", BUCKET, OTHER_HTML]
