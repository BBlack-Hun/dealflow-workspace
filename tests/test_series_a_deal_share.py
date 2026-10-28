"""딜 소싱 제안의 [보낼 문구 › Series A 딜 공유] — 받은 딜을 시리즈 A 심사역께 소개.

여기서 못 박는 것.

  ① 화면 — [보낼 문구]에 셋째 칩 · ① 칸에 `Series A 이상 딜 소싱` 고르개(이미 받은
     심사역 번호를 싣는다) · [이미 이 기업들을 받은 분 제외](기본 켬)
  ② 글 — 인사말(처음 안내와 같은 손, 빈 직함은 갈래 호칭) + 문구 + 기업마다 한
     덩어리(`[기업N]` · 분야 · 투자라운드 · 소개 — **기업명은 가린다**, 소개 속 이름도
     번호로). 소개는 딜소개 문구, 없으면
     상세 내용 첫 문장(~120자, 줄바꿈 없이). 차례 = 고른 차례. `{기업 목록}` 이
     없는 문구는 첫 문단 뒤에 들어간다
  ③ 받는 사람 — 시리즈 A 갈래 · 참여만. 방 없음 · 불참여 · 다른 갈래는 빼고 이유를 말한다
  ④ 기록 — 누구에게 어느 기업이 나갔나(`series_a_shares`). 이미 받은 기업은 그 분
     문구에서 빼고, 다 받은 분은 뺀다. 중단한 회차는 안 센다
  ⑤ 보이는 곳 — `Series A 이상 딜 소싱` 탭 줄의 받은 분 수(`data-shared` — 칸은
     #24 에서 뺐다) · 딜 소싱 줄의
     `Series A 딜 공유 N건` · 딜 소싱 화면의 [Series A 딜 소개]
  ⑥ 문구 — 갈래마다 하나 · 문구 화면 구간 · 심는 기본 글(메일 주소 · 실명 없음)

이름 · 회사 · 기업은 전부 가상값이다(공개 저장소).
"""
from __future__ import annotations

import html
import json
import re
import shutil
import subprocess
from datetime import date
from pathlib import Path
from urllib.parse import quote

import pytest

from .conftest import DEMO_PASSWORD

JS_DIR = Path(__file__).resolve().parent / "js"

SERIES_A = "시리즈 A 이상 딜 소싱 참여 심사역"
MNA = "M&A 찾는 투자사"
TODAY = date(2026, 10, 15)
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+")
SHARE = "sourcing_deal_share"

BIO_PITCH = "표적 항암제 후보물질 개발"
LONG_DETAIL = (
    "- 공장 자동화용 협동로봇을 만드는 샘플로보틱스입니다. 다음 줄은 넘기지 않습니다.\n"
    "- 국내 제조사 12곳 납품\n"
    "- 후속 라운드 준비 중")


@pytest.fixture()
def today(monkeypatch):
    from app import clock

    monkeypatch.setattr(clock, "today", lambda: TODAY)
    return TODAY


@pytest.fixture()
def world(client, db, users, today):
    """시리즈 A 갈래 넷(직함 있음 · 비어 있음 · 방 없음 · 불참여) + M&A 하나, 기업 셋."""
    from app.models import SeriesACompany, SourcingContact

    people = {
        "a": SourcingContact(bucket=SERIES_A, position=0, name="가심사", title="심사역",
                             firm="가나벤처스", kakao_room_name="가심사 소싱방",
                             assignee_name="강민준"),
        "b": SourcingContact(bucket=SERIES_A, position=1, name="나심사", title=None,
                             firm="다라인베스트", kakao_room_name="나심사 소싱방",
                             assignee_name="윤서아"),
        "c": SourcingContact(bucket=SERIES_A, position=2, name="다심사", title="이사",
                             firm="마바캐피탈"),                      # 방 없음
        "d": SourcingContact(bucket=SERIES_A, position=3, name="라심사", title="팀장",
                             firm="사아파트너스", kakao_room_name="라심사 소싱방",
                             participation="불참여"),
        "m": SourcingContact(bucket=MNA, position=1000, name="마투자", title="대표",
                             firm="자차캐피탈", kakao_room_name="마투자 소싱방"),
    }
    companies = {
        "bio": SeriesACompany(name="샘플바이오", received_at="2026-10-01",
                              deal_type="딜 소싱 네트워크", sector_major="바이오",
                              sector_minor="신약", series="Series A (누적투자금 10억이상)",
                              detail="길게 적힌 상세 내용", deal_pitch="표적 항암제 후보물질 개발"),
        "robo": SeriesACompany(name="샘플로보틱스", received_at="2026-09-20",
                               deal_type="후속 투자 연계", sector_major="로봇",
                               sector_minor="", series="Series B", detail=LONG_DETAIL),
        "food": SeriesACompany(name="샘플푸드", received_at="2026-08-01"),
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
    return {p["name"]: p for p in r.json()["previews"]}


def _send(client, contact_ids, series_ids, **extra):
    return client.post("/api/deals/send", json={
        "contact_ids": contact_ids, "mode": "sourcing", "topic": SHARE,
        "series_a_ids": series_ids, **extra})


# ── ① 화면 ──────────────────────────────────────────────────────────────────

def test_the_tab_offers_the_share_topic_and_a_company_picker(world, client):
    body = client.get("/deals").text
    bar = body[body.index('id="sourcing-topic"'):]
    bar = bar[:bar.index("</div>")]
    assert f'data-value="{SHARE}"' in bar and "Series A 딜 공유" in bar
    # 받는 갈래가 하나뿐 — 칩이 그 이름을 싣는다(다른 갈래 카드를 화면이 뺀다).
    assert f'data-bucket="{SERIES_A}"' in bar
    # 처음 안내가 기본인 것은 그대로
    assert re.search(r'class="chip active" data-value="sourcing_intro"', bar)

    picker = body[body.index('id="series-a-picker"'):]
    picker = picker[:picker.index('id="sa-filter-note"')]
    assert "hidden" in picker[:picker.index(">")], "처음부터 떠 있으면 IR 기업 목록과 섞인다"
    names = re.findall(r'class="sa-cb" value="\d+" data-name="([^"]+)"', picker)
    assert names == ["샘플바이오", "샘플로보틱스", "샘플푸드"], names   # 수신 일자 최신순
    for word in ("Series A", "딜 소싱 네트워크", "바이오 / 신약", "수신 2026-10-01",
                 "표적 항암제 후보물질 개발"):
        assert word in picker, word
    assert 'id="sa-pick-search"' in picker and 'id="sa-only-picked"' in picker

    # 제외는 기본으로 켜져 있다
    note = body[body.index('id="shared-note"'):]
    note = note[:note.index("</div>")]
    assert re.search(r'id="exclude-shared" checked', note)
    assert "이미 이 기업들을 받은 분 제외" in note
    # 카드마다 딱지 자리
    picker2 = body[body.index('id="sourcing-list"'):]
    assert 'class="tag warn share-tag" hidden' in picker2
    # 회차명도 이 글의 이름으로 한 벌(`pages.py` 의 `TOPIC_TITLES`)
    titles = json.loads(html.unescape(re.search(r"data-titles='([^']*)'", body).group(1)))
    assert "(Series A 딜 공유)" in titles[SHARE], titles


def test_the_picker_reads_who_already_got_each_company(world, client, db):
    """누가 이미 받았나는 /deals 를 그릴 때 세지 않고, 고를 때 JSON 으로 읽는다
    (`routers/series_a.share_state` — `deals.js` 가 카드에 채운다)."""
    _send(client, _ids(world, "a"), _ids(world, "bio", kind="c"))
    body = client.get("/deals").text
    card = re.search(r'<label class="pick-card" data-sent-to="([^"]*)"[^>]*>\s*'
                     r'<input type="checkbox" class="sa-cb" value="(\d+)"', body)
    assert card and card.group(2) == str(world["c"]["bio"].id)
    assert card.group(1) == "", "그릴 때 세지 않는다 — 고를 때 읽는다"
    assert 'class="tag soft sa-count" hidden' in body
    state = client.get("/api/series-a-share/state").json()
    got = {row["id"]: row["sent_to"] for row in state["companies"]}
    assert got[world["c"]["bio"].id] == [world["p"]["a"].id]
    assert got[world["c"]["robo"].id] == []


# ── ② 글 ────────────────────────────────────────────────────────────────────

def test_the_message_is_greeting_text_and_one_block_per_company(world, client):
    got = _preview(client, _ids(world, "a", "b"), _ids(world, "robo", "bio", "food", kind="c"),
                   per_person=3)
    a = got["가심사"]["message"]
    assert a.startswith("안녕하세요, 가심사 심사역님"), a
    # 빈 직함은 갈래 호칭(처음 안내와 같은 규칙)
    assert got["나심사"]["message"].startswith("안녕하세요, 나심사 심사역님")

    assert "Series A 이상 딜 네트워크를 통해 공유드릴 딜이 있어 연락드립니다." in a
    assert "{기업 목록}" not in a and "SERIES_A_COMPANIES" not in a
    # 고른 차례 그대로 — 로보틱스가 [기업1]. 기업명은 싣지 않는다(번호가 대신한다).
    assert a.index("[기업1]\n · 분야: 로봇") < a.index("[기업2]\n · 분야: 바이오") < a.index(
        "[기업3]")
    for name in ("샘플로보틱스", "샘플바이오", "샘플푸드"):
        assert name not in a, name
    # 덩어리 모양 — 번호 · 분야(대분류/소분류) · 투자라운드(괄호 앞) · 소개
    assert ("[기업2]\n · 분야: 바이오 / 신약\n · 투자라운드: Series A\n"
            " · 소개: 표적 항암제 후보물질 개발") in a
    # 딜소개 문구가 없으면 상세 내용 첫 문장 — 글머리표를 떼고 한 줄로, 이름은 번호로
    assert (" · 소개: 공장 자동화용 협동로봇을 만드는 [기업1]입니다.\n") in a
    assert "다음 줄은" not in a and "납품" not in a
    # 빈 칸은 그 줄째 빠진다 — 분야도 라운드도 소개도 없는 기업
    food = a[a.index("[기업3]"):]
    assert "분야" not in food.split("\n\n")[0] and "소개" not in food.split("\n\n")[0]
    # 기업 목록 뒤로 문구의 나머지가 이어진다
    assert a.index("[기업3]") < a.index("관심 있는 기업이 있으시면 편하게 말씀 부탁드립니다.")
    assert a.rstrip().endswith("감사합니다.")


def test_a_long_detail_is_cut_on_one_line():
    from app.models import SeriesACompany
    from app.services import series_a_share

    row = SeriesACompany(name="샘플", detail=("가나다라 " * 60).strip() + "\n둘째 줄")
    pitch = series_a_share.pitch_of(row)
    assert len(pitch) <= series_a_share.PITCH_MAX + 1 and pitch.endswith("…")
    assert "\n" not in pitch and "둘째" not in pitch
    # 문장으로 안 끝난 줄들은 ` · ` 로 잇는다(줄바꿈을 그냥 지우면 붙어 버린다)
    row = SeriesACompany(name="샘플", detail="스마트팜 관제\n후속 라운드 준비")
    assert series_a_share.pitch_of(row) == "스마트팜 관제 · 후속 라운드 준비"
    # 딜소개 문구는 적힌 그대로(빈 줄 겹침만 다듬는다)
    row = SeriesACompany(name="샘플", deal_pitch="첫 줄\n\n\n둘째 줄", detail="무시")
    assert series_a_share.pitch_of(row) == "첫 줄\n둘째 줄"


def test_the_name_inside_the_pitch_becomes_the_number_too():
    """소개 글에 적힌 기업명도 그 덩어리의 번호로 — 적힌 그대로와 법인 표기를 뗀 것 둘 다."""
    from app.models import SeriesACompany
    from app.services import series_a_share as sas

    row = SeriesACompany(name="(주)샘플가", deal_pitch="샘플가는 (주)샘플가 이름으로 수출한다")
    assert sas.block(3, row) == "[기업3]\n · 소개: [기업3]는 [기업3] 이름으로 수출한다"
    # 한 글자 이름은 바꾸지 않는다 — 낱말 속 글자까지 번호가 된다
    row = SeriesACompany(name="가", deal_pitch="가공 식품")
    assert sas.block(1, row) == "[기업1]\n · 소개: 가공 식품"


def test_an_edited_message_is_matched_by_the_whole_block_not_the_number():
    """고친 글의 기록(`companies_in`)은 번호가 아니라 덩어리 글자로 찾는다(이름이 없다)."""
    from app.models import SeriesACompany
    from app.services import series_a_share as sas

    x = SeriesACompany(id=1, name="샘플엑스", sector_major="바이오")
    y = SeriesACompany(id=2, name="샘플와이", sector_major="바이오", deal_pitch="샘플와이 신약")
    # 와이만 남은 글 — 엑스 덩어리(`분야: 바이오` 한 줄)가 와이 덩어리의 앞부분이어도 엑스가 아니다
    text = "인사\n\n" + sas.block(2, y) + "\n\n감사합니다."
    assert sas.companies_in(text, [x, y]) == [y]
    # 번호가 달라도(받는 분마다 차례가 다르다) 같은 덩어리면 그 기업 · 글에 나온 차례
    text = sas.block(1, y) + "\n\n" + sas.block(2, x)
    assert sas.companies_in(text, [x, y]) == [y, x]


def test_a_stored_template_without_the_slot_gets_blocks_after_the_first_paragraph(
        world, client, db):
    from app.models import MessageTemplate

    db.add(MessageTemplate(user_id=None, kind=SHARE, name=SERIES_A, is_active=1,
                           body="이번 주 공유 딜입니다.\n\n궁금하시면 말씀 주세요."))
    db.commit()
    a = _preview(client, _ids(world, "a"), _ids(world, "bio", kind="c"))["가심사"]["message"]
    assert a.index("이번 주 공유 딜입니다.") < a.index("[기업1]\n · 분야: 바이오") < a.index(
        "궁금하시면 말씀 주세요.")

    # 붙여 쓴 `{기업목록}`(딜 소개 · 자료 전달의 말)도 같은 자리로 받는다
    row = db.query(MessageTemplate).filter_by(kind=SHARE).one()
    row.body = "머리말\n{기업목록}\n꼬리말 {담당자명}"
    db.commit()
    a = _preview(client, _ids(world, "a"), _ids(world, "bio", kind="c"))["가심사"]["message"]
    assert "머리말\n[기업1]\n · 분야: 바이오" in a and "꼬리말 가심사" in a
    assert "{기업목록}" not in a


def test_the_company_text_does_not_go_through_the_honorific_fixer(world, client, db):
    """상세 내용의 `대표 님` 같은 띄어쓰기를 인사말 다듬기가 건드리지 않는다."""
    world["c"]["food"].deal_pitch = "창업자 김 대표 님이 직접 운영"
    db.commit()
    a = _preview(client, _ids(world, "a"), _ids(world, "food", kind="c"))["가심사"]["message"]
    assert "창업자 김 대표 님이 직접 운영" in a


def test_companies_are_required_and_must_exist(world, client):
    r = client.post("/api/deals/preview", json={
        "contact_ids": _ids(world, "a"), "mode": "sourcing", "topic": SHARE,
        "series_a_ids": []})
    assert r.status_code == 400 and "1~10" in r.json()["detail"]
    r = _send(client, _ids(world, "a"), [])
    assert r.status_code == 400
    r = _send(client, _ids(world, "a"), [99999])
    assert r.status_code == 404
    r = _send(client, _ids(world, "a"), list(range(1, 12)))
    assert r.status_code == 400


def test_the_sample_preview_shows_the_slot_or_the_picked_companies(world, client):
    r = client.post("/api/deals/preview", json={
        "contact_ids": [], "mode": "sourcing", "topic": SHARE, "series_a_ids": []})
    sample = r.json()["previews"][0]
    assert sample["sample"] is True
    assert "고른 기업이 이 자리에" in sample["message"]
    r = client.post("/api/deals/preview", json={
        "contact_ids": [], "mode": "sourcing", "topic": SHARE,
        "series_a_ids": _ids(world, "bio", kind="c")})
    sample = r.json()["previews"][0]["message"]
    assert "[기업1]\n · 분야: 바이오 / 신약" in sample and "샘플바이오" not in sample


# ── ③ 받는 사람 · ④ 기록 ────────────────────────────────────────────────────

def test_sending_skips_no_room_left_and_other_bucket_and_records_shares(world, client, db):
    from app.models import DealBatch, SendItem, SendJob, SeriesAShare

    r = _send(client, _ids(world, "a", "b", "c", "d", "m"),
              _ids(world, "bio", "robo", kind="c"))
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["total"] == 2
    reasons = {s["name"]: s["reason"] for s in out["skipped"]}
    assert set(reasons) == {"다심사", "라심사", "마투자"}
    assert "카톡방 없음" in reasons["다심사"]
    assert "불참여" in reasons["라심사"]
    assert SERIES_A in reasons["마투자"]

    job = db.get(SendJob, out["job_id"])
    # 잡 종류는 그대로(발송 프로그램이 아는 종류) — 글은 topic 이 말한다
    assert (job.kind, job.topic, job.status) == ("sourcing_intro", SHARE, "queued")
    assert "Series A 딜 공유" in db.get(DealBatch, job.batch_id).title
    items = db.query(SendItem).filter_by(job_id=job.id).all()
    assert {i.room_name for i in items} == {"가심사 소싱방", "나심사 소싱방"}
    assert all("[기업1]\n · 분야: 바이오 / 신약" in i.message for i in items)
    assert not any("샘플바이오" in i.message or "샘플로보틱스" in i.message for i in items)

    shares = db.query(SeriesAShare).all()
    assert len(shares) == 4
    by_item = {}
    for s in shares:
        by_item.setdefault(s.send_item_id, []).append(
            (s.position, s.series_a_company_id))
    for got in by_item.values():
        assert sorted(got) == [(1, world["c"]["bio"].id), (2, world["c"]["robo"].id)]


def test_already_received_companies_are_dropped_per_person(world, client, db):
    from app.models import SendItem

    bio, robo = _ids(world, "bio", "robo", kind="c")
    assert _send(client, _ids(world, "a"), [bio]).status_code == 200

    # 미리보기 — 가심사는 바이오를 빼고, 나심사는 둘 다
    got = _preview(client, _ids(world, "a", "b"), [bio, robo])
    a, b = got["가심사"], got["나심사"]
    assert [c["name"] for c in a["series_a"]["send"]] == ["샘플로보틱스"]
    assert BIO_PITCH not in a["message"] and "[기업1]\n · 분야: 로봇" in a["message"]
    assert any("이미 받은 기업 1곳" in w and "샘플바이오" in w for w in a["warnings"])
    assert [c["name"] for c in b["series_a"]["send"]] == ["샘플바이오", "샘플로보틱스"]
    assert "[기업1]\n · 분야: 바이오" in b["message"] and "[기업2]\n · 분야: 로봇" in b["message"]

    r = _send(client, _ids(world, "a", "b"), [bio, robo])
    assert r.status_code == 200 and r.json()["total"] == 2
    msgs = {i.recipient_name: i.message
            for i in db.query(SendItem).filter_by(job_id=r.json()["job_id"])}
    assert BIO_PITCH not in msgs["가심사"]

    # 이제 둘 다 둘 다 받았다 — 고른 분 모두 빠지면 아무것도 안 만든다
    r = _send(client, _ids(world, "a", "b"), [bio, robo])
    assert r.status_code == 400 and "보낼 기업 없음" in r.json()["detail"]
    got = _preview(client, _ids(world, "a"), [bio])
    assert any("보낼 기업 없음 (본인 공유/이미 받음)" in w for w in got["가심사"]["warnings"])

    # 한 분만 다 받았으면 그 분만 빼고 이유를 돌려준다
    food = world["c"]["food"].id
    assert _send(client, _ids(world, "a"), [food]).status_code == 200
    r = _send(client, _ids(world, "a", "b"), [food])
    assert r.status_code == 200 and r.json()["total"] == 1
    assert [s["name"] for s in r.json()["skipped"]] == ["가심사"]

    # [이미 이 기업들을 받은 분 제외]를 끄면 그대로 다 간다
    r = _send(client, _ids(world, "a", "b"), [bio, robo], include_shared=True)
    assert r.status_code == 200 and r.json()["total"] == 2
    msgs = {i.recipient_name: i.message
            for i in db.query(SendItem).filter_by(job_id=r.json()["job_id"])}
    assert f"[기업1]\n · 분야: 바이오 / 신약\n · 투자라운드: Series A\n · 소개: {BIO_PITCH}" in msgs["가심사"]


def test_a_canceled_round_does_not_count(world, client, db):
    bio = world["c"]["bio"].id
    r = _send(client, _ids(world, "a"), [bio], draft=True)
    assert r.status_code == 200
    # 대기(draft) 중인 회차도 센다 — 두 번 세우지 않게
    assert _send(client, _ids(world, "a"), [bio]).status_code == 400
    assert client.post(f"/api/jobs/{r.json()['job_id']}/cancel").status_code == 200
    # 중단했으면 안 받은 것이다
    assert _send(client, _ids(world, "a"), [bio]).status_code == 200


def test_an_edited_message_records_the_companies_it_still_carries(world, client, db):
    """고친 글로 보내도 기록은 **그 글에 든 기업**이다(`series_a_share.companies_in`).

    덩어리(`[기업1]` · 분야 · 투자라운드 · 소개)를 남겨 두고 둘레를 고쳤으면 그 기업을
    적고, 덩어리째 지웠으면 안 적는다 — 글에 없는 기업을 '받음' 으로 적으면 그 분은
    영영 못 받는다(PR #287 리뷰). 기업명은 글에 없으므로 덩어리 글자로 찾는다.
    """
    from app.models import SeriesAShare

    a = world["p"]["a"].id
    robo = ("[기업1]\n · 분야: 로봇\n · 투자라운드: Series B\n"
            " · 소개: 공장 자동화용 협동로봇을 만드는 [기업1]입니다.")
    r = _send(client, [a], _ids(world, "robo", kind="c"),
              overrides=[{"contact_id": a,
                          "message": f"직접 고친 문구\n\n{robo}\n\n감사합니다."}])
    assert r.status_code == 200
    assert db.query(SeriesAShare).filter_by(sourcing_contact_id=a).count() == 1
    b = world["p"]["b"].id
    r = _send(client, [b], _ids(world, "robo", kind="c"),
              overrides=[{"contact_id": b, "message": "직접 고친 문구"}])
    assert r.status_code == 200
    assert db.query(SeriesAShare).filter_by(sourcing_contact_id=b).count() == 0


def test_company_names_go_out_as_numbers_but_stay_on_team_screens(world, client, db):
    """사용자 요청(10/27): 딜 소싱에서 딜을 소개할 때도 기업명은 `[기업1]` `[기업2]` 로 가린다.

    가리는 것은 **나가는 글**(미리보기 글 · 발송 건)뿐이다. 미리보기의 `보내는 기업` 줄과
    딜 소싱 화면의 `Series A 딜 공유 N건` 은 팀이 보는 것이라 이름 그대로다.
    """
    from app.models import SendItem

    ids = _ids(world, "robo", "bio", kind="c")
    p = _preview(client, _ids(world, "a"), ids)["가심사"]
    assert [(c["label"], c["name"]) for c in p["series_a"]["send"]] == [
        ("[기업1]", "샘플로보틱스"), ("[기업2]", "샘플바이오")]
    r = _send(client, _ids(world, "a"), ids)
    assert r.status_code == 200, r.text
    item = db.query(SendItem).filter_by(job_id=r.json()["job_id"]).one()
    for text in (p["message"], item.message):
        assert "[기업1]" in text and "[기업2]" in text
        assert "샘플로보틱스" not in text and "샘플바이오" not in text, text
    page = client.get(f"/sourcing?tab={quote(SERIES_A)}").text
    assert "샘플로보틱스 · 샘플바이오" in page


# ── ⑤ 보이는 곳 ─────────────────────────────────────────────────────────────

def test_the_series_a_tab_counts_who_got_each_company(world, client, db):
    """받은 분 수는 줄에 그대로 실린다(`data-shared` — [삭제] 확인창이 읽는다).

    표의 `공유한 심사역` 칸은 #24 에서 뺐다(옆 `공유 심사역` 과 같은 뜻으로
    읽혔다) — 머리글에도 줄에도 그 칸이 없어야 한다(`tests/test_series_a_drop_shared_column.py`).
    """
    _send(client, _ids(world, "a", "b"), _ids(world, "bio", kind="c"))
    page = client.get("/companies?tab=series-a").text
    head = re.search(r'id="sa-table".*?</thead>', page, re.S).group(0)
    heads = [re.sub(r"<[^>]+>", "", h).strip()
             for h in re.findall(r"<th\b[^>]*>(.*?)</th>", head, re.S)]
    assert heads[:3] == ["NO", "기업명", "수신일"], heads   # #87 — 옆 두 탭과 같은 이름
    assert "공유한 심사역" not in heads
    rows = re.findall(r"<tr data-id=.*?</tr>", page, re.S)
    bio = next(r for r in rows if "샘플바이오" in r)
    assert 'class="sa-shared"' not in bio
    assert 'data-shared="2"' in bio
    food = next(r for r in rows if "샘플푸드" in r)
    assert 'data-shared="0"' in food


def test_deleting_a_company_takes_its_share_records_along(world, client, db):
    from app.models import SendItem, SeriesAShare

    bio = world["c"]["bio"].id
    _send(client, _ids(world, "a"), [bio])
    r = client.delete(f"/api/series-a-companies/{bio}")
    assert r.status_code == 200, r.text
    assert db.query(SeriesAShare).count() == 0
    # 나간 문구는 발송 이력에 그대로 남는다
    assert db.query(SendItem).count() == 1


def test_the_sourcing_screen_has_the_button_and_the_row_note(world, client, db):
    _send(client, _ids(world, "a"), _ids(world, "bio", "robo", kind="c"))
    page = client.get(f"/sourcing?tab={quote(SERIES_A)}").text
    btn = re.search(r'<a [^>]*id="sourcing-share-btn"[^>]*>([^<]*)</a>', page)
    assert btn, "시리즈 A 탭에 [Series A 딜 소개] 단추가 없다"
    assert f'data-base="/deals?mode=sourcing&amp;topic={SHARE}"' in btn.group(0)
    # 처음에는 아무도 안 골랐다 — 잠긴 채, 주소 없이(보이는 줄 전부로 대신하지 않는다).
    assert btn.group(1) == "Series A 딜 소개 (선택 0명)"
    assert 'aria-disabled="true"' in btn.group(0) and " href=" not in btn.group(0)
    assert "왼쪽 체크박스로 받을 분을 고르세요" in page
    # 체크한 참여 분을 `contacts=` 로 싣는다(불참여는 빼고 몇 명인지 말한다)
    assert 'shareBtn.setAttribute("href"' in page and '"&contacts="' in page
    # 빼는 갈래는 서버가 실어 준 `data-part-kind` 로 — 불참여 · 참여 확인 전을 따로 센다
    assert 'if (kind === "left") { out += 1; return; }' in page
    assert 'if (kind === "pending") { pending += 1; return; }' in page

    note = re.findall(r'data-testid="sourcing-share-note"\s*title="([^"]*)">([^<]*)<', page)
    assert note == [("샘플로보틱스 · 샘플바이오", "Series A 딜 공유 2건")], note

    # 다른 갈래 탭에는 단추가 없다. 고르는 칸은 선다 — [방 후보 찾기]가 고른 분만 찾는다
    other = client.get(f"/sourcing?tab={quote(MNA)}").text
    assert re.search(r'class="sheet-tab active"\s+href="/sourcing\?tab=M%26A', other)
    assert 'id="sourcing-share-btn"' not in other
    assert 'id="sourcing-check-all"' in other and 'class="js-sourcing-pick"' in other


def test_the_series_a_tab_has_a_pick_column_before_no(world, client):
    """체크박스 칸은 맨 왼쪽(`NO` 앞) — 그 뒤 차례는 `COLUMNS` 그대로(#87 · 이름 → 회사 …)."""
    from app.routers.sourcing import COLUMNS
    from app.services.sourcing_remind_log import MONTHS

    page = client.get(f"/sourcing?tab={quote(SERIES_A)}").text
    head = page[page.index("<thead>"):page.index("</thead>")]
    ths = re.findall(r"<th[\s>].*?</th>", head, re.S)
    # 고르는 칸 + NO + 컬럼 + 월간 리마인드 달 칸(#14)
    assert len(ths) == len(COLUMNS) + 2 + MONTHS
    assert 'id="sourcing-check-all"' in ths[0] and 'type="checkbox"' in ths[0]
    labels = [re.sub(r"<[^>]+>", "", x).strip() for x in ths]
    assert labels[:5] == ["", "NO", "이름", "회사", "직함"], labels

    body = page[page.index("<tbody>"):page.index("</tbody>")]
    rows = re.findall(r"<tr data-id=\"(\d+)\".*?</tr>", body, re.S)
    first = body[:body.index("</tr>")]
    tds = re.findall(r"<td[\s>]", first)
    assert len(tds) == len(COLUMNS) + 2 + MONTHS, "머리글과 칸 수가 어긋났다 — 표가 한 칸 밀린다"
    cells = re.findall(r"<td[^>]*>", first)
    assert 'class="pick-col"' in cells[0] and "rowno" in cells[1]
    picks = re.findall(r'class="js-sourcing-pick" value="(\d+)"', body)
    assert picks == rows, "줄마다 고르는 칸이 있어야 한다(같은 번호로)"
    order = re.findall(r'data-field="(\w+)"', first)
    assert order == [f for f, _label, _w, _filt in COLUMNS], order


# ── ⑥ 문구 ──────────────────────────────────────────────────────────────────

def test_the_template_kind_is_bucket_named_and_on_the_templates_page(world, client):
    from app.routers.templates_crud import KIND_LABELS, VARIABLES
    from app.services import series_a_share, sourcing_msg, template_pick

    assert series_a_share.KIND == SHARE == sourcing_msg.SHARE_KIND
    assert SHARE in template_pick.NAME_IS_A_BUCKET and SHARE in sourcing_msg.TOPICS
    assert SHARE in KIND_LABELS and "{기업 목록}" in dict(VARIABLES)

    body = client.get("/templates").text
    section = body[body.index(f'id="{SHARE}"'):]
    section = section[:section.index('class="tpl-new"')]
    assert "딜 소싱 제안 — Series A 딜 공유" in section
    assert "고른 기업이 이 자리에" in section       # 미리보기는 기업 자리 안내
    others = body[body.index('id="others"'):]
    assert f'id="{SHARE}"' not in others


def test_the_seeded_text_is_the_requested_one_without_addresses(db, users):
    from app.models import MessageTemplate
    from app.services import series_a_share
    from scripts.bootstrap import bootstrap, seed_series_a_share

    text = series_a_share.default_body()
    assert "@" not in text and not EMAIL.search(text)
    assert text.splitlines() == [
        "Series A 이상 딜 네트워크를 통해 공유드릴 딜이 있어 연락드립니다.",
        "",
        "{기업 목록}",
        "",
        "관심 있는 기업이 있으시면 편하게 말씀 부탁드립니다.",
        "IR Deck 전달과 기업 담당자 연결 도와드리겠습니다.",
        "",
        "감사합니다.",
    ]

    assert seed_series_a_share(db) == 1
    db.commit()
    row = db.query(MessageTemplate).filter_by(kind=SHARE).one()
    assert (row.user_id, row.name, row.body) == (None, SERIES_A, text)

    # 다시 돌아도 덮지 않는다 — 운영자가 고친 글이 남아야 한다
    row.body = "고친 글 {기업 목록}"
    db.commit()
    assert seed_series_a_share(db) == 0
    bootstrap(db)
    db.commit()
    assert db.query(MessageTemplate).filter_by(kind=SHARE).one().body == "고친 글 {기업 목록}"


@pytest.mark.parametrize("name", ["series_a_share_test.js",        # 딜 제안 관리
                                  "sourcing_share_link_test.js"])  # 딜 소싱 단추
def test_the_screen_logic_runs_in_node(name):
    """고르개 · 차례 · 이미 받은 분 · 제외 · 링크 — 브라우저 쪽(`tests/js`)."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("node 미설치 — 브라우저 로직 테스트 생략 "
                    f"(호스트에서 `node tests/js/{name}`)")
    result = subprocess.run([node, str(JS_DIR / name)], capture_output=True, text=True,
                            timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
