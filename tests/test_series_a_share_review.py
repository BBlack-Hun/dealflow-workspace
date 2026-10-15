"""Series A 딜 공유 — PR #287 · #288 머지 뒤 리뷰에서 나온 고장.

여기서 못 박는 것.

  ① 상세 내용이 소수로 시작해도 정수부가 글머리표로 떨어지지 않는다(`3.5억`)
  ② 사람이 고친 문구로 보내면 **글에 실제로 든 기업만** 기록한다(`[기업N] 기업명` 줄)
  ③ `{개수}` · 메일 제목이 그 분께 나가는 기업 수다(0 이 아니다)
  ④ 문구 화면에서 저장한 CRLF 글도 문단 자리를 찾는다 · 저장할 때 LF 로 바꾼다
  ⑤ 시각을 놓쳤거나 버려진 draft 회차는 7일이 지나면 '받음' 으로 안 센다
  ⑥ 본인 판정 — `회사명 이름 직함` · `직함 이름` · 여러 사람 · 영문 직함 · `대표 겸 파트너`
  ⑦ 회사 표기 차이(한영 · 약칭)는 같은 회사 · 확정한 공유 심사역(`shared_by_contact_id`)
  ⑧ /deals 는 이미 받은 분 · 본인 공유를 미리 세지 않는다 — 고를 때 JSON 으로 읽는다

이름 · 회사 · 기업은 전부 가상값이다(공개 저장소).
"""
from __future__ import annotations

import html
import json
import re
import shutil
import sqlite3
import subprocess
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

from .conftest import DEMO_PASSWORD
from .test_migrations import _alembic

JS_DIR = Path(__file__).resolve().parent / "js"
SERIES_A = "시리즈 A 이상 딜 소싱 참여 심사역"
MNA = "M&A 찾는 투자사"
SHARE = "sourcing_deal_share"
TODAY = date(2026, 10, 15)


@pytest.fixture()
def today(monkeypatch):
    from app import clock

    monkeypatch.setattr(clock, "today", lambda: TODAY)
    return TODAY


@pytest.fixture()
def world(client, db, users, today):
    """시리즈 A 갈래 셋 + M&A 하나, 기업 넷(하나는 홍길동이 공유해 준 딜)."""
    from app.models import SeriesACompany, SourcingContact

    people = {
        "a": SourcingContact(bucket=SERIES_A, position=0, name="홍길동", title="이사",
                             firm="가나벤처스", kakao_room_name="홍길동 소싱방",
                             email="a@example.com"),
        "b": SourcingContact(bucket=SERIES_A, position=1, name="김철수", title="심사역",
                             firm="다라인베스트먼트", kakao_room_name="김철수 소싱방"),
        "c": SourcingContact(bucket=SERIES_A, position=2, name="홍길동", title="팀장",
                             firm="마바캐피탈", kakao_room_name="동명이인 소싱방"),
        "m": SourcingContact(bucket=MNA, position=1000, name="박영희", title="대표",
                             firm="사아파트너스", kakao_room_name="박영희 소싱방"),
    }
    companies = {
        "x": SeriesACompany(name="샘플엑스", received_at="2026-10-05",
                            deal_pitch="엑스 소개"),
        "y": SeriesACompany(name="샘플와이", received_at="2026-10-04",
                            deal_pitch="와이 소개"),
        "z": SeriesACompany(name="샘플제트", received_at="2026-10-03",
                            deal_pitch="제트 소개"),
        # 홍길동(가나벤처스)이 공유해 준 딜 — 시트에 `회사명 이름 직함` 으로 적혔다
        "own": SeriesACompany(name="샘플오운", received_at="2026-10-02",
                              shared_by="가나 Ventures 홍길동 Partner",
                              source_firm="가나 Ventures"),
    }
    db.add_all(list(people.values()) + list(companies.values()))
    db.commit()
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    return {"p": people, "c": companies}


def _ids(world, *keys, kind="p"):
    return [world[kind][k].id for k in keys]


def _preview(client, contact_ids, series_ids, **extra):
    r = client.post("/api/deals/preview", json={
        "contact_ids": contact_ids, "mode": "sourcing", "topic": SHARE,
        "series_a_ids": series_ids, **extra})
    assert r.status_code == 200, r.text
    return {p["contact_id"]: p for p in r.json()["previews"]}


def _send(client, contact_ids, series_ids, **extra):
    return client.post("/api/deals/send", json={
        "contact_ids": contact_ids, "mode": "sourcing", "topic": SHARE,
        "series_a_ids": series_ids, **extra})


def _recorded(db, contact_id):
    from app.models import SeriesACompany, SeriesAShare

    rows = (db.query(SeriesAShare).filter_by(sourcing_contact_id=contact_id)
            .order_by(SeriesAShare.send_item_id, SeriesAShare.position).all())
    return [db.get(SeriesACompany, r.series_a_company_id).name for r in rows]


# ── ① 소수로 시작하는 상세 내용 ─────────────────────────────────────────────

def test_a_decimal_at_the_start_keeps_its_integer_part():
    from app.models import SeriesACompany
    from app.services import series_a_share as sas

    row = SeriesACompany(name="샘플", detail="3.5억 규모 투자를 마쳤습니다. 다음 문장")
    assert sas.pitch_of(row) == "3.5억 규모 투자를 마쳤습니다.", sas.pitch_of(row)
    assert sas._flat("12.5% 성장\n2.0 버전 출시") == "12.5% 성장 · 2.0 버전 출시"
    # 진짜 글머리 번호는 그대로 뗀다
    assert sas._flat("1. 첫 항목\n2) 둘째 항목\n- 셋째") == "첫 항목 · 둘째 항목 · 셋째"


# ── ② 고친 문구 = 기록 ──────────────────────────────────────────────────────

def test_an_edited_message_records_only_the_companies_it_carries(world, client, db):
    a = world["p"]["a"]
    xyz = _ids(world, "x", "y", "z", kind="c")
    text = _preview(client, [a.id], xyz, per_person=3)[a.id]["message"]
    assert "[기업3] 샘플제트" in text
    # 사람이 셋째 덩어리를 지우고 보냈다
    edited = text[:text.index("[기업3]")].rstrip() + "\n\n감사합니다.\n"
    r = _send(client, [a.id], xyz, per_person=3,
              overrides=[{"contact_id": a.id, "message": edited}])
    assert r.status_code == 200, r.text
    assert _recorded(db, a.id) == ["샘플엑스", "샘플와이"], \
        "글에 없는 기업을 받은 것으로 적었다 — 그 분은 그 기업을 영영 못 받는다"


def test_an_old_edit_from_a_smaller_pick_does_not_record_the_new_company(world, client, db):
    """기업을 더 고른 뒤 예전에 고친 글이 되살아나 나가도, 기록은 나간 글을 따른다."""
    b = world["p"]["b"]
    x, y, z = _ids(world, "x", "y", "z", kind="c")
    old = _preview(client, [b.id], [x, y], per_person=3)[b.id]["message"]
    r = _send(client, [b.id], [x, y, z], per_person=3,
              overrides=[{"contact_id": b.id, "message": old + "\n덧붙인 말"}])
    assert r.status_code == 200, r.text
    assert _recorded(db, b.id) == ["샘플엑스", "샘플와이"]
    # 그래서 샘플제트는 다음 공유에서 그대로 나간다
    again = _preview(client, [b.id], [z])[b.id]
    assert "[기업1] 샘플제트" in again["message"]


def test_an_edit_without_any_company_block_records_nothing(world, client, db):
    a = world["p"]["a"]
    r = _send(client, [a.id], _ids(world, "x", kind="c"),
              overrides=[{"contact_id": a.id, "message": "안녕하세요, 곧 따로 연락드리겠습니다."}])
    assert r.status_code == 200, r.text
    assert _recorded(db, a.id) == []


def test_an_untouched_message_still_records_the_plan(world, client, db):
    a = world["p"]["a"]
    r = _send(client, [a.id], _ids(world, "x", "y", "z", kind="c"))
    assert r.status_code == 200, r.text
    assert _recorded(db, a.id) == ["샘플엑스", "샘플와이"]       # 사람당 2개


# ── ③ {개수} · 메일 제목 ───────────────────────────────────────────────────

def test_the_count_slot_is_the_number_sent_to_that_person(world, client, db, users):
    from app.models import MessageTemplate

    t = MessageTemplate(user_id=users["u1"].id, kind=SHARE, name=SERIES_A, is_active=1,
                        body="이번에 {개수}곳을 소개합니다.\n\n{기업 목록}\n\n감사합니다.")
    db.add(t)
    db.commit()
    a = world["p"]["a"]
    got = _preview(client, [a.id], _ids(world, "x", "y", "z", kind="c"),
                   closing_template_id=t.id)
    assert "이번에 2곳을 소개합니다." in got[a.id]["message"], got[a.id]["message"]
    got = _preview(client, [a.id], _ids(world, "x", kind="c"), closing_template_id=t.id)
    assert "이번에 1곳을 소개합니다." in got[a.id]["message"]


def test_the_mail_subject_counts_the_companies_sent(world):
    from app.routers import deals

    req = SimpleNamespace(subject="Series A 딜 {개수}곳 공유", title="", mode="sourcing")
    assert deals._mail_subject(req, world["p"]["a"], [], count=2) == "Series A 딜 2곳 공유"
    # 다른 글은 지금까지와 같다(후속 문구는 0)
    assert deals._mail_subject(req, world["p"]["a"], []) == "Series A 딜 0곳 공유"


# ── ④ CRLF ─────────────────────────────────────────────────────────────────

def test_a_crlf_template_gets_the_companies_after_its_first_paragraph():
    from app.services import message_composer as mc
    from app.services import series_a_share as sas

    out = sas.slot("첫 문단입니다.\r\n\r\n둘째 문단입니다.")
    assert out == f"첫 문단입니다.\n\n{sas._SLOT}\n\n둘째 문단입니다.", out
    out = sas.slot("위\r\n\r\n{기업 목록}\r\n\r\n아래")
    assert "\r" not in out and out == f"위\n\n{sas._SLOT}\n\n아래"
    done = sas.fill(mc.ComposeResult(text=f"가\r\n\r\n{sas._SLOT}\r\n\r\n나", char_count=0,
                                     too_long=False, warnings=[], parts=[]), "[기업1] 샘플")
    assert done.text == "가\n\n[기업1] 샘플\n\n나\n"


def test_saving_a_template_turns_crlf_into_lf(logged_in, db):
    from app.models import MessageTemplate

    r = logged_in.post("/templates/new", data={
        "kind": SHARE, "name": SERIES_A, "body": "가\r\n\r\n{기업 목록}\r\n나"},
        follow_redirects=False)
    assert r.status_code == 303
    t = db.query(MessageTemplate).filter_by(kind=SHARE).one()
    assert t.body == "가\n\n{기업 목록}\n나"
    r = logged_in.post(f"/templates/{t.id}/edit", data={"name": SERIES_A, "body": "다\r\n라\r"},
                       follow_redirects=False)
    assert r.status_code == 303
    db.refresh(t)
    assert t.body == "다\n라"


# ── ⑤ 버려진 draft ─────────────────────────────────────────────────────────

def test_an_abandoned_draft_stops_counting_after_seven_days(world, client, db):
    from app.models import SendItem, SendJob
    from app.services import series_a_share as sas

    a = world["p"]["a"]
    x = world["c"]["x"].id
    r = _send(client, [a.id], [x], draft=True)
    assert r.status_code == 200, r.text
    job = db.get(SendJob, r.json()["job_id"])
    item = db.query(SendItem).filter_by(job_id=job.id).one()
    assert job.status == "draft" and item.status == "pending"
    # 막 만든 draft 는 센다 — [발송 시작] 전에 목록을 또 만들어 두 번 나가지 않게
    assert sas.companies_by_contact(db, contact_ids=[a.id]) == {a.id: {x}}

    # 7일 안(오늘 포함 7일 — `twin_send.WINDOW_DAYS` 와 같은 폭)이면 아직 센다
    item.created_at = "2026-10-09T10:00:00+09:00"
    db.commit()
    assert sas.companies_by_contact(db, contact_ids=[a.id]) == {a.id: {x}}
    # 그보다 오래 서 있는 draft(시각을 놓쳤거나 버려진 회차)는 안 센다
    item.created_at = "2026-10-07T10:00:00+09:00"
    db.commit()
    assert sas.companies_by_contact(db, contact_ids=[a.id]) == {}
    assert sas.contacts_by_company(db) == {}
    assert "[기업1] 샘플엑스" in _preview(client, [a.id], [x])[a.id]["message"]
    # 내보낸 회차(대기 중)는 오래돼도 센다 — 나간 것 · 나갈 것은 받은 것이다
    job.status = "queued"
    db.commit()
    assert sas.companies_by_contact(db, contact_ids=[a.id]) == {a.id: {x}}


# ── ⑥ 본인 판정 — 이름 ──────────────────────────────────────────────────────

@pytest.mark.parametrize("raw", [
    "가나벤처스 홍길동 이사", "가나벤처스 홍길동", "홍길동 이사 가나벤처스",
    "이사 홍길동", "수석심사역 홍길동님",
    "홍길동 CEO", "CEO 홍길동", "홍길동 Partner", "홍길동 partner", "홍길동 VP",
    "홍길동 MD", "홍길동 Managing Director", "홍길동CEO", "홍길동 CFO",
    "홍길동 대표 겸 파트너", "홍길동 대표겸파트너", "홍길동대표겸파트너",
    "홍길동 이사/변호사", "홍길동 (가나벤처스)", "가나 Ventures 홍길동 Partner",
])
def test_the_name_is_found_in_any_common_writing(raw):
    from app.services import series_a_share as sas

    assert sas.person_keys(raw) == {"홍길동"}, (raw, sas.person_keys(raw))


def test_a_firm_word_that_is_not_a_firm_suffix_is_dropped_by_the_row_firm():
    from app.services import series_a_share as sas

    assert sas.person_keys("가나 홍길동 이사", firm="가나벤처스") == {"홍길동"}
    assert sas.person_keys("홍길동 이사", firm="가나벤처스") == {"홍길동"}


@pytest.mark.parametrize("raw", [
    "홍길동 이사/김철수 팀장", "홍길동 CEO, 김철수 CFO", "홍길동/김철수",
    "홍길동 대표 겸 파트너 / 김철수 VP", "홍길동 이사 및 김철수 팀장",
])
def test_several_people_in_one_cell_are_each_a_sharer(raw):
    from app.services import series_a_share as sas

    assert sas.person_keys(raw) == {"홍길동", "김철수"}, (raw, sas.person_keys(raw))


def test_names_that_look_like_titles_are_not_cut_short():
    from app.services import series_a_share as sas

    assert sas.person_keys("김이사") == {"김이사"}
    assert sas.person_keys("이겸호 이사") == {"이겸호"}
    assert sas.person_keys("이겸이사") == {"이겸"}
    assert sas.person_keys("이사") == set()
    assert sas.person_keys("CEO / Partner") == set()


# ── ⑦ 본인 판정 — 회사 · 확정 ───────────────────────────────────────────────

def _row(shared_by, firm, confirmed=None):
    from app.models import SeriesACompany

    return SeriesACompany(name="샘플", shared_by=shared_by, source_firm=firm,
                          shared_by_contact_id=confirmed)


def _who(name, firm, cid=1):
    return SimpleNamespace(id=cid, name=name, firm=firm)


@pytest.mark.parametrize("row_firm, their_firm", [
    ("가나인베스트먼트", "가나 Investment"),
    ("가나인베스트", "가나인베스트먼트"),
    ("가나 Investment Partners", "가나인베스트먼트파트너스"),
    ("가나 Partners", "가나파트너스"),
    ("가나벤처스", "가나 Ventures"),
    ("가나캐피탈", "가나 Capital"),
    ("가나자산운용", "가나AM"),
    ("가나자산운용", "가나 Asset Management"),
    ("가나", "가나벤처스"),                      # 약칭
    ("(주)가나벤처스", "가나벤처스 주식회사"),
])
def test_spelling_variants_of_the_same_firm_are_the_same_firm(row_firm, their_firm):
    from app.services import series_a_share as sas

    assert sas.is_own(_row("홍길동 이사", row_firm), _who("홍길동", their_firm))
    assert sas.is_own(_row("홍길동 이사", their_firm), _who("홍길동", row_firm))


@pytest.mark.parametrize("row_firm, their_firm", [
    ("가나벤처스", "다라인베스트먼트"),
    ("가나벤처스", "다라벤처스"),
    ("마바 Partners", "가나파트너스"),
    ("가나벤처스", "가나캐피탈"),
])
def test_clearly_different_firms_mean_a_namesake(row_firm, their_firm):
    from app.services import series_a_share as sas

    assert not sas.is_own(_row("홍길동 이사", row_firm), _who("홍길동", their_firm))


def test_a_confirmed_sharer_decides_alone():
    from app.services import series_a_share as sas

    row = _row("홍길동 이사", "가나벤처스", confirmed=7)
    assert sas.is_own(row, _who("전혀 다른 분", "다른회사", cid=7))
    assert not sas.is_own(row, _who("홍길동", "가나벤처스", cid=8)), \
        "확정했는데 이름만 같은 다른 줄을 또 본인으로 셌다"


def test_own_by_company_matches_is_own_for_every_pair(world, db):
    from app.models import SeriesACompany, SourcingContact
    from app.services import series_a_share as sas

    rows = db.query(SeriesACompany).all()
    people = db.query(SourcingContact).filter_by(bucket=SERIES_A).all()
    want = {}
    for row in rows:
        ids = sorted(p.id for p in people if sas.is_own(row, p))
        if ids:
            want[row.id] = ids
    assert sas.own_by_company(db, rows) == want
    assert want == {world["c"]["own"].id: [world["p"]["a"].id]}


# ── ⑦ 확정 — 화면 · 주소 ───────────────────────────────────────────────────

def _sharer_attr(body, row_id):
    tr = body[body.index(f'<tr data-id="{row_id}"'):]
    tr = tr[:tr.index("</tr>")]
    found = re.search(r"data-sharer='([^']*)'", tr)
    assert found, tr
    return json.loads(html.unescape(found.group(1)))


def test_the_tab_suggests_sharers_by_name(world, client):
    own = world["c"]["own"]
    a, c = world["p"]["a"], world["p"]["c"]
    info = _sharer_attr(client.get("/companies?tab=series-a").text, own.id)
    assert info["confirmed"] is None
    got = {x["id"]: x for x in info["candidates"]}
    # 이름이 같은 두 분 — 회사까지 맞는 분은 `자동`, 회사가 다른 분은 이름만 같다
    assert set(got) == {a.id, c.id}
    assert got[a.id]["auto"] is True and got[c.id]["auto"] is False
    assert "가나벤처스" in got[a.id]["label"]


def test_confirming_a_sharer_decides_who_is_left_out(world, client, db):
    from app.models import SeriesACompany

    own = world["c"]["own"]
    a, b = world["p"]["a"], world["p"]["b"]
    url = f"/api/series-a-companies/{own.id}/sharer"
    r = client.put(url, json={"contact_id": b.id})
    assert r.status_code == 200, r.text
    assert r.json()["sharer"]["confirmed"]["id"] == b.id
    db.expire_all()
    assert db.get(SeriesACompany, own.id).shared_by_contact_id == b.id

    got = _preview(client, [a.id, b.id], [own.id])
    assert "[기업1] 샘플오운" in got[a.id]["message"], "확정을 무시하고 이름으로 또 뺐다"
    assert "샘플오운" not in got[b.id]["message"]
    state = client.get("/api/series-a-share/state").json()
    assert {x["id"]: x["own_by"] for x in state["companies"]}[own.id] == [b.id]

    # 해제하면 이름으로 다시 본다
    r = client.put(url, json={"contact_id": None})
    assert r.status_code == 200 and r.json()["sharer"]["confirmed"] is None
    got = _preview(client, [a.id], [own.id])
    assert "샘플오운" not in got[a.id]["message"]


def test_only_a_person_of_the_bucket_can_be_confirmed(world, client):
    own = world["c"]["own"]
    url = f"/api/series-a-companies/{own.id}/sharer"
    r = client.put(url, json={"contact_id": world["p"]["m"].id})
    assert r.status_code == 400 and SERIES_A in r.json()["detail"]
    assert client.put(url, json={"contact_id": 99999}).status_code == 400
    assert client.put("/api/series-a-companies/99999/sharer",
                      json={"contact_id": None}).status_code == 404


def test_rewriting_the_sharer_text_drops_the_confirmation(world, client, db):
    from app.models import SeriesACompany

    own = world["c"]["own"]
    client.put(f"/api/series-a-companies/{own.id}/sharer",
               json={"contact_id": world["p"]["a"].id})
    # 같은 글자로 다시 저장 — 확정은 그대로
    r = client.patch(f"/api/series-a-companies/{own.id}",
                     json={"shared_by": "가나 Ventures 홍길동 Partner"})
    assert r.status_code == 200
    db.expire_all()
    assert db.get(SeriesACompany, own.id).shared_by_contact_id == world["p"]["a"].id
    # 다른 사람으로 고치면 확정을 푼다 — 옛 사람이 확정된 채 남으면 새 사람에게 자기 딜이 간다
    r = client.patch(f"/api/series-a-companies/{own.id}", json={"shared_by": "김철수 심사역"})
    assert r.status_code == 200
    assert r.json()["sharer"]["confirmed"] is None
    assert [x["id"] for x in r.json()["sharer"]["candidates"]] == [world["p"]["b"].id]
    db.expire_all()
    assert db.get(SeriesACompany, own.id).shared_by_contact_id is None


def test_deleting_the_confirmed_person_clears_the_link(world, client, db):
    from app.models import SeriesACompany

    own = world["c"]["own"]
    b = world["p"]["b"]
    client.put(f"/api/series-a-companies/{own.id}/sharer", json={"contact_id": b.id})
    r = client.delete(f"/api/sourcing/{b.id}")
    assert r.status_code == 200, r.text
    db.expire_all()
    assert db.get(SeriesACompany, own.id).shared_by_contact_id is None


# ── ⑧ /deals 는 미리 세지 않는다 ──────────────────────────────────────────

def test_the_deals_page_does_not_count_shares_up_front(world, client, monkeypatch):
    from app.services import series_a_share as sas

    def boom(*_a, **_k):
        raise AssertionError("/deals 를 열 때마다 세지 않는다")

    monkeypatch.setattr(sas, "own_by_company", boom)
    monkeypatch.setattr(sas, "contacts_by_company", boom)
    r = client.get("/deals")
    assert r.status_code == 200
    assert 'class="sa-cb"' in r.text


def test_the_share_state_endpoint_says_who_got_and_who_shared(world, client):
    a, b = world["p"]["a"], world["p"]["b"]
    x, own = world["c"]["x"], world["c"]["own"]
    assert _send(client, [b.id], [x.id]).status_code == 200
    state = client.get("/api/series-a-share/state").json()
    by_id = {row["id"]: row for row in state["companies"]}
    assert by_id[x.id]["sent_to"] == [b.id] and by_id[x.id]["own_by"] == []
    assert by_id[own.id]["own_by"] == [a.id]
    assert set(by_id) == set(_ids(world, "x", "y", "z", "own", kind="c"))


# ── ⑦ 판(0101) ─────────────────────────────────────────────────────────────

def test_the_migration_adds_the_confirmed_sharer_column_and_takes_it_back(tmp_path):
    db = tmp_path / "m.db"
    done = _alembic(db, "upgrade", "0095_series_a_shares")
    assert done.returncode == 0, done.stdout + done.stderr
    con = sqlite3.connect(db)
    try:
        # 운영 DB 는 이 칸이 없는 표에서 출발한다(0001 의 create_all 은 이미 칸이 있다)
        cols = [r[1] for r in con.execute('PRAGMA table_info("series_a_companies")')
                if r[1] != "shared_by_contact_id"]
        keep = ", ".join(cols)
        con.execute(f"CREATE TABLE sa_old AS SELECT {keep} FROM series_a_companies")
        con.execute("DROP TABLE series_a_companies")
        con.execute("ALTER TABLE sa_old RENAME TO series_a_companies")
        con.commit()
    finally:
        con.close()
    done = _alembic(db, "upgrade", "0101_series_a_shared_by")
    assert done.returncode == 0, done.stdout + done.stderr
    con = sqlite3.connect(db)
    try:
        cols = {r[1] for r in con.execute('PRAGMA table_info("series_a_companies")')}
    finally:
        con.close()
    assert "shared_by_contact_id" in cols
    done = _alembic(db, "downgrade", "0095_series_a_shares")
    assert done.returncode == 0, done.stdout + done.stderr
    con = sqlite3.connect(db)
    try:
        cols = {r[1] for r in con.execute('PRAGMA table_info("series_a_companies")')}
    finally:
        con.close()
    assert "shared_by_contact_id" not in cols


# ── 브라우저 쪽 ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("name", ["series_a_sharer_test.js"])
def test_the_screen_logic_runs_in_node(name):
    node = shutil.which("node")
    if node is None:
        pytest.skip(f"node 미설치 — 호스트에서 `node tests/js/{name}`")
    result = subprocess.run([node, str(JS_DIR / name)], capture_output=True, text=True,
                            timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
