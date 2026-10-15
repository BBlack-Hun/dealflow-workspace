"""Series A 딜 공유 — **본인이 공유한 딜은 빼고 사람마다 앞에서부터 N개**.

사용자: "딜소싱 네트워크로 딜을 보낼때는 심사역 본인이 공유한 딜 제외하고 2개씩 보낼 예정"

여기서 못 박는 것.

  ① 본인인지 — `공유 심사역`(직함까지 적힌 자유 글자)과 받는 분 이름을 직함 · 존칭 ·
     괄호 · 띄어쓰기를 떼고 견준다. 회사가 양쪽에 다 있으면 회사도 같아야 하고
     (`(주)` · 띄어쓰기 무시), 한쪽이 비었으면 이름만으로 본다. 이름이 같아도 회사가
     다르면 본인이 아니다
  ② 사람당 N개(기본 2, 1~10) — 고른 차례에서 본인 공유(늘) · 이미 받은 기업(제외를
     켰을 때)을 빼고 앞에서부터. 모자라면 남은 만큼, 하나도 없으면 그 분은 빠진다
     (`보낼 기업 없음 (본인 공유/이미 받음)`)
  ③ 기록은 실제로 나간 기업만
  ④ 미리보기 — 나가는 기업 · 뺀 기업과 까닭(`본인이 공유한 딜`)
  ⑤ 화면 — 고르개가 읽는 `own_by`(`/api/series-a-share/state`) · 사람당 칸(기본 2) · 안내 글

이름 · 회사 · 기업은 전부 가상값이다(공개 저장소).
"""
from __future__ import annotations

import re
from datetime import date
from types import SimpleNamespace

import pytest

from .conftest import DEMO_PASSWORD

SERIES_A = "시리즈 A 이상 딜 소싱 참여 심사역"
SHARE = "sourcing_deal_share"
TODAY = date(2026, 10, 15)
NOTHING = "보낼 기업 없음 (본인 공유/이미 받음)"


# ── ① 본인인지 ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("raw", [
    "가나다 이사", "가나다 이사님", "가나다이사", "가나다이사님", "가나다 님", "가나다님",
    "가나다 대표이사", "가나다 수석심사역", "가나다 이사/변호사", "가나다 (샘플벤처스)",
    "가나다 이사(샘플벤처스)", " 가나다   팀장 ", "가나다상무이사",
])
def test_titles_and_honorifics_are_stripped(raw):
    from app.services import series_a_share

    assert series_a_share.person_key(raw) == "가나다", raw


def test_a_title_like_name_is_not_cut_down_to_one_letter():
    from app.services import series_a_share

    # `김이사` 를 `김` 으로 자르면 성이 같은 아무나와 맞는다.
    assert series_a_share.person_key("김이사") == "김이사"
    assert series_a_share.person_key("김이사 이사님") == "김이사"
    # 직함만 적힌 칸은 사람이 아니다.
    assert series_a_share.person_keys("이사") == set()
    assert series_a_share.person_keys("") == set()


def test_two_people_in_one_cell_are_both_sharers():
    from app.services import series_a_share

    assert series_a_share.person_keys("가나다 이사, 라마바 팀장") == {"가나다", "라마바"}
    assert series_a_share.person_keys("가나다 이사 및 라마바 팀장") == {"가나다", "라마바"}


def _row(shared_by, firm):
    from app.models import SeriesACompany

    return SeriesACompany(name="샘플", shared_by=shared_by, source_firm=firm)


def _who(name, firm):
    return SimpleNamespace(id=1, name=name, firm=firm)


def test_name_and_firm_must_both_match_when_both_have_a_firm():
    from app.services import series_a_share as sas

    row = _row("가나다 이사", "(주)샘플 벤처스")
    assert sas.is_own(row, _who("가나다", "샘플벤처스"))          # (주) · 띄어쓰기 무시
    assert sas.is_own(row, _who("가나다 이사님", "샘플벤처스 주식회사"))
    # 이름이 같아도 회사가 다르면 동명이인 — 본인으로 보지 않는다.
    assert not sas.is_own(row, _who("가나다", "다른인베스트"))
    # 이름이 다르면 회사가 같아도 아니다.
    assert not sas.is_own(row, _who("라마바", "샘플벤처스"))


def test_name_alone_decides_when_a_firm_is_missing():
    from app.services import series_a_share as sas

    # 줄에 회사가 없다 — 이름만으로.
    assert sas.is_own(_row("가나다이사님", ""), _who("가나다", "샘플벤처스"))
    assert sas.is_own(_row("가나다 이사", None), _who("가나다", None))
    # 받는 분 회사가 비었다 — 견줄 것이 없을 뿐 어긋난 것이 아니다.
    assert sas.is_own(_row("가나다 이사", "샘플벤처스"), _who("가나다", ""))
    # 공유 심사역이 빈 줄은 아무의 것도 아니다.
    assert not sas.is_own(_row("", "샘플벤처스"), _who("가나다", "샘플벤처스"))


def test_the_hint_is_the_requested_sentence():
    from app.services import series_a_share as sas

    assert sas.PER_PERSON_DEFAULT == 2
    assert sas.per_person_hint() == (
        "기업을 2~4개 고르면 사람마다 본인 공유·이미 받은 기업을 빼고 앞에서부터 2개씩 나갑니다.")
    assert sas.per_person_hint(10).startswith("기업을 10개 고르면")


# ── ② ~ ⑤ 화면 · 미리보기 · 발송 ────────────────────────────────────────────

@pytest.fixture()
def today(monkeypatch):
    from app import clock

    monkeypatch.setattr(clock, "today", lambda: TODAY)
    return TODAY


@pytest.fixture()
def world(client, db, users, today):
    """시리즈 A 갈래 셋, 기업 다섯(셋은 이 중 누군가가 공유해 준 딜).

    c1 — 가심사가 공유(이름 + 회사)
    c2 — 나심사가 공유(줄에 회사 없음 — 이름만, 직함 붙여 씀)
    c3 — `가심사` 라는 다른 회사 분이 공유(동명이인 — 가심사 본인 것이 아니다)
    c4 — 다심사가 공유(받는 분 쪽 회사에 `(주)`, 이름 칸에 직함)
    c5 — 공유 심사역 없음
    """
    from app.models import SeriesACompany, SourcingContact

    people = {
        "a": SourcingContact(bucket=SERIES_A, position=0, name="가심사", title="심사역",
                             firm="가나벤처스", kakao_room_name="가심사 소싱방"),
        "b": SourcingContact(bucket=SERIES_A, position=1, name="나심사", title="이사",
                             firm="다라인베스트", kakao_room_name="나심사 소싱방"),
        "c": SourcingContact(bucket=SERIES_A, position=2, name="다심사 대표", title=None,
                             firm="(주)마바캐피탈", kakao_room_name="다심사 소싱방"),
    }
    companies = {
        "c1": SeriesACompany(name="샘플원", received_at="2026-10-05",
                             shared_by="가심사 이사", source_firm="가나벤처스"),
        "c2": SeriesACompany(name="샘플투", received_at="2026-10-04",
                             shared_by="나심사이사님", source_firm=""),
        "c3": SeriesACompany(name="샘플쓰리", received_at="2026-10-03",
                             shared_by="가심사 팀장", source_firm="다른벤처스"),
        "c4": SeriesACompany(name="샘플포", received_at="2026-10-02",
                             shared_by="다심사 대표", source_firm="마바 캐피탈"),
        "c5": SeriesACompany(name="샘플파이브", received_at="2026-10-01"),
    }
    db.add_all(list(people.values()) + list(companies.values()))
    db.commit()
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    return {"p": people, "c": companies}


def _ids(world, *keys, kind="p"):
    return [world[kind][k].id for k in keys]


def _all(world):
    return _ids(world, "c1", "c2", "c3", "c4", "c5", kind="c")


def _preview(client, contact_ids, series_ids, **extra):
    r = client.post("/api/deals/preview", json={
        "contact_ids": contact_ids, "mode": "sourcing", "topic": SHARE,
        "series_a_ids": series_ids, **extra})
    assert r.status_code == 200, r.text
    return {p["name"]: p for p in r.json()["previews"]}


def _send(client, contact_ids, series_ids, **extra):
    return client.post("/api/deals/send", json={
        "contact_ids": contact_ids, "mode": "sourcing", "topic": SHARE,
        "series_a_ids": series_ids, **extra})


def _sent_names(db, job_id):
    """발송 건마다 기록된 기업 이름(차례대로) — `{받는 분 이름: [기업…]}`."""
    from app.models import SendItem, SeriesACompany, SeriesAShare

    out = {}
    for item in db.query(SendItem).filter_by(job_id=job_id):
        rows = (db.query(SeriesAShare).filter_by(send_item_id=item.id)
                .order_by(SeriesAShare.position).all())
        out[item.sourcing_contact.name] = [db.get(SeriesACompany, r.series_a_company_id).name
                                           for r in rows]
    return out


def test_each_person_gets_the_first_two_that_are_not_their_own(world, client, db):
    from app.models import SendItem

    # per_person 를 안 실으면 기본 2.
    r = _send(client, _ids(world, "a", "b", "c"), _all(world))
    assert r.status_code == 200, r.text
    assert r.json()["total"] == 3 and r.json()["skipped"] == []
    got = _sent_names(db, r.json()["job_id"])
    # 가심사 — 샘플원은 본인 공유라 빼고 앞에서부터 둘(샘플쓰리는 동명이인 딜이라 간다)
    assert got["가심사"] == ["샘플투", "샘플쓰리"]
    # 나심사 — 샘플투(줄에 회사 없음 · 이름만)를 빼고
    assert got["나심사"] == ["샘플원", "샘플쓰리"]
    # 다심사 — 본인 공유(샘플포)는 어차피 셋째 뒤. 앞의 둘
    assert got["다심사 대표"] == ["샘플원", "샘플투"]

    # 글도 기록과 같다 — 번호는 그 분께 나가는 차례로 1부터.
    msgs = {i.sourcing_contact.name: i.message
            for i in db.query(SendItem).filter_by(job_id=r.json()["job_id"])}
    a = msgs["가심사"]
    assert "[기업1] 샘플투" in a and "[기업2] 샘플쓰리" in a
    assert "샘플원" not in a and "샘플포" not in a and "[기업3]" not in a


def test_per_person_count_follows_the_picked_order(world, client, db):
    c1, c2, c3, c4, c5 = _all(world)
    r = _send(client, _ids(world, "c"), [c5, c4, c3, c2, c1], per_person=3)
    assert r.status_code == 200, r.text
    # 다심사 — 고른 차례에서 본인 공유(샘플포)를 빼고 앞의 셋
    assert _sent_names(db, r.json()["job_id"]) == {"다심사 대표": ["샘플파이브", "샘플쓰리", "샘플투"]}

    r = _send(client, _ids(world, "b"), [c5, c4, c3, c2, c1], per_person=1)
    assert _sent_names(db, r.json()["job_id"]) == {"나심사": ["샘플파이브"]}


def test_fewer_than_n_left_still_goes_and_none_left_is_skipped(world, client, db):
    c1, c2, c3, c4, c5 = _all(world)
    # 가심사 — 샘플원(본인) 빼면 하나뿐 → 하나만 간다.
    r = _send(client, _ids(world, "a"), [c1, c5])
    assert r.status_code == 200, r.text
    assert _sent_names(db, r.json()["job_id"]) == {"가심사": ["샘플파이브"]}

    # 이제 가심사는 샘플파이브를 받았다 — 본인 공유 + 이미 받음뿐이면 빠진다.
    r = _send(client, _ids(world, "a", "b"), [c1, c5])
    assert r.status_code == 200, r.text
    assert r.json()["total"] == 1
    assert r.json()["skipped"] == [{"contact_id": world["p"]["a"].id, "name": "가심사",
                                    "reason": NOTHING}]
    assert _sent_names(db, r.json()["job_id"]) == {"나심사": ["샘플원", "샘플파이브"]}

    # 고른 분 모두 보낼 것이 없으면 아무것도 안 만든다.
    r = _send(client, _ids(world, "a"), [c1, c5])
    assert r.status_code == 400 and NOTHING in r.json()["detail"]


def test_turning_off_the_exclusion_never_brings_their_own_deal_back(world, client, db):
    c1, c2, c3, c4, c5 = _all(world)
    assert _send(client, _ids(world, "a"), [c5]).status_code == 200
    # 제외를 끄면 이미 받은 샘플파이브는 다시 가지만, 본인 공유(샘플원)는 그래도 빠진다.
    r = _send(client, _ids(world, "a"), [c1, c5], include_shared=True)
    assert r.status_code == 200, r.text
    assert _sent_names(db, r.json()["job_id"]) == {"가심사": ["샘플파이브"]}
    r = _send(client, _ids(world, "a"), [c1], include_shared=True)
    assert r.status_code == 400 and NOTHING in r.json()["detail"]


def test_history_records_only_what_was_actually_sent(world, client, db):
    from app.models import SeriesAShare

    r = _send(client, _ids(world, "a", "b", "c"), _all(world))
    assert r.status_code == 200
    rows = db.query(SeriesAShare).all()
    assert len(rows) == 6, "사람마다 2개 — 고른 다섯이 다 적혔다"
    a = world["p"]["a"].id
    assert {x.series_a_company_id for x in rows if x.sourcing_contact_id == a} == set(
        _ids(world, "c2", "c3", kind="c"))
    # 안 간 기업(샘플포 · 샘플파이브)은 아직 아무도 안 받았다 — 다음에 고르면 간다.
    c4, c5 = _ids(world, "c4", "c5", kind="c")
    assert not [x for x in rows if x.series_a_company_id in (c4, c5)]
    r = _send(client, _ids(world, "a"), _all(world))
    assert _sent_names(db, r.json()["job_id"]) == {"가심사": ["샘플포", "샘플파이브"]}


def test_preview_says_what_goes_and_what_was_dropped_and_why(world, client, db):
    got = _preview(client, _ids(world, "a", "b"), _all(world))
    a = got["가심사"]
    assert a["series_a"]["send"] == [
        {"id": world["c"]["c2"].id, "name": "샘플투", "label": "[기업1]"},
        {"id": world["c"]["c3"].id, "name": "샘플쓰리", "label": "[기업2]"}]
    assert [(d["name"], d["reason"]) for d in a["series_a"]["dropped"]] == [
        ("샘플원", "본인이 공유한 딜"),
        ("샘플포", "사람당 2개 — 이번엔 안 보냄"),
        ("샘플파이브", "사람당 2개 — 이번엔 안 보냄")]
    assert "본인이 공유한 딜 1곳은 이 분 문구에서 뺐습니다: 샘플원" in a["warnings"]
    assert "[기업1] 샘플투" in a["message"] and "샘플원" not in a["message"]

    # 이미 받은 것 · 모자람 · 하나도 없음도 같은 자리에서 말한다.
    c1, c2, c3, c4, c5 = _all(world)
    assert _send(client, _ids(world, "a"), [c5]).status_code == 200
    a = _preview(client, _ids(world, "a"), [c1, c5, c4])["가심사"]
    assert [(d["name"], d["reason"]) for d in a["series_a"]["dropped"]] == [
        ("샘플원", "본인이 공유한 딜"), ("샘플파이브", "이미 받음")]
    assert [s["name"] for s in a["series_a"]["send"]] == ["샘플포"]
    assert any("사람당 2개 중 1개만 나갑니다" in w for w in a["warnings"])
    a = _preview(client, _ids(world, "a"), [c1, c5])["가심사"]
    assert a["series_a"]["send"] == []
    assert any(NOTHING in w for w in a["warnings"])
    # 보낼 기업이 없는 분의 글 — 기본 문구의 자리 안내가 서지 않는다.
    assert NOTHING in a["message"] and "고른 기업이 이 자리에" not in a["message"]

    # 다른 글(처음 안내)에는 이 칸이 없다.
    r = client.post("/api/deals/preview", json={
        "contact_ids": _ids(world, "a"), "mode": "sourcing"})
    assert r.json()["previews"][0]["series_a"] is None


def test_the_sample_preview_shows_only_the_first_n(world, client):
    r = client.post("/api/deals/preview", json={
        "contact_ids": [], "mode": "sourcing", "topic": SHARE,
        "series_a_ids": _all(world), "per_person": 2})
    text = r.json()["previews"][0]["message"]
    assert "[기업1] 샘플원" in text and "[기업2] 샘플투" in text and "[기업3]" not in text


@pytest.mark.parametrize("n", [0, 11, -1])
def test_per_person_outside_one_to_ten_is_refused(world, client, n):
    r = client.post("/api/deals/preview", json={
        "contact_ids": _ids(world, "a"), "mode": "sourcing", "topic": SHARE,
        "series_a_ids": _all(world), "per_person": n})
    assert r.status_code == 400 and "1~10" in r.json()["detail"]
    r = _send(client, _ids(world, "a"), _all(world), per_person=n)
    assert r.status_code == 400 and "1~10" in r.json()["detail"]


def test_the_picker_reads_who_shared_each_deal_and_has_the_count_box(world, client):
    body = client.get("/deals").text
    picker = body[body.index('id="series-a-picker"'):]
    picker = picker[:picker.index('id="sa-filter-note"')]
    # 누가 공유해 준 딜인가는 그릴 때 세지 않는다 — 고를 때 JSON 으로 읽는다
    # (`routers/series_a.share_state`).
    assert set(re.findall(r'data-own-by="([^"]*)"', picker)) == {""}
    state = client.get("/api/series-a-share/state").json()
    cards = {row["id"]: row["own_by"] for row in state["companies"]}
    p, c = world["p"], world["c"]
    assert cards[c["c1"].id] == [p["a"].id]
    assert cards[c["c2"].id] == [p["b"].id]
    assert cards[c["c3"].id] == [], "동명이인(회사 다름)을 본인으로 셌다"
    assert cards[c["c4"].id] == [p["c"].id]
    assert cards[c["c5"].id] == []
    assert picker.count('class="tag warn sa-own" hidden') == 5

    box = re.search(r'<input type="number" id="sa-per-person"[^>]*>', picker).group(0)
    assert 'value="2"' in box and 'min="1"' in box and 'max="10"' in box
    hint = re.search(r'id="sa-per-person-hint">([^<]*)<', picker).group(1)
    assert hint == ("기업을 2~4개 고르면 사람마다 본인 공유·이미 받은 기업을 빼고 "
                    "앞에서부터 2개씩 나갑니다.")
    assert "사람당 보낼 기업 수" in picker
