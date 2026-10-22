"""딜 소싱 제안 탭의 [보낼 문구 › 월간 리마인드] — 손으로 보내는 이 달 리마인드.

여기서 못 박는 것.

  ① 화면에 [보낼 문구] 고르개가 선다(참여 안내 (처음) / 월간 리마인드)
  ② 리마인드 글은 `sourcing_remind` 문구(갈래마다 하나)에서 오고, `{월}` 은
     이 달로 채워지며, 인사말은 처음 안내와 같은 손으로 사람마다 붙는다
     (빈 직함은 갈래 호칭) — 운영자가 고친 저장 문구의 `{월}` 도 채워진다
  ③ 이 달 `딜 받음` 인 분은 기본으로 빠지고(뺀 분과 이유를 돌려준다),
     [이번 달 딜 받음 포함] 이면 들어간다
  ④ 처음 안내는 그대로다(글 · 잡 종류 · 회차 표시)
  ⑤ 심는 기본 글에는 메일 주소가 없다(공개 저장소 — 운영자가 문구 화면에서 넣는다)

이름·주소는 전부 가상값이다(공개 저장소).
"""
from __future__ import annotations

import re
import shutil
import subprocess
from datetime import date
from pathlib import Path

import pytest

from .conftest import DEMO_PASSWORD

REMIND_JS = Path(__file__).resolve().parent / "js" / "sourcing_remind_test.js"

SERIES_A = "시리즈 A 이상 딜 소싱 참여 심사역"
MNA = "M&A 찾는 투자사"
TODAY = date(2026, 10, 13)
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+")


@pytest.fixture()
def today(monkeypatch):
    from app import clock

    monkeypatch.setattr(clock, "today", lambda: TODAY)
    return TODAY


@pytest.fixture()
def people(client, db, users, today):
    """시리즈 A 갈래 둘(직함 있음 · 비어 있음) + M&A 하나. 방은 모두 있다."""
    from app.models import SourcingContact

    rows = {
        "a": SourcingContact(bucket=SERIES_A, position=0, name="가심사", title="심사역",
                             firm="가나벤처스", kakao_room_name="가심사 소싱방"),
        "b": SourcingContact(bucket=SERIES_A, position=1, name="나심사", title=None,
                             firm="다라인베스트", kakao_room_name="나심사 소싱방"),
        "m": SourcingContact(bucket=MNA, position=1000, name="마투자", title="이사",
                             firm="마바캐피탈", kakao_room_name="마투자 소싱방"),
    }
    db.add_all(rows.values())
    db.commit()
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    return rows


def _preview(client, ids, topic="sourcing_remind", **extra):
    r = client.post("/api/deals/preview",
                    json={"contact_ids": ids, "mode": "sourcing", "topic": topic, **extra})
    assert r.status_code == 200, r.text
    return {p["name"]: p for p in r.json()["previews"]}


# ── ① 고르개 ────────────────────────────────────────────────────────────────

def test_the_tab_has_a_message_picker(people, client):
    body = client.get("/deals").text
    bar = body[body.index('id="sourcing-topic"'):]
    bar = bar[:bar.index("</div>")]
    assert 'data-value="sourcing_intro"' in bar and "참여 안내 (처음)" in bar
    assert 'data-value="sourcing_remind"' in bar and "월간 리마인드" in bar
    # 처음 안내가 기본이다 — 지금까지 이 탭이 하던 일
    assert re.search(r'class="chip active" data-value="sourcing_intro"', bar)
    # 이 달 딜 받음 제외 안내와 포함 칸
    assert 'id="received-note"' in body and 'id="include-received"' in body


# ── ② 리마인드 글 ───────────────────────────────────────────────────────────

def test_remind_uses_the_code_default_with_the_month_and_greeting(people, client):
    got = _preview(client, [people["a"].id, people["b"].id, people["m"].id])

    a = got["가심사"]["message"]
    assert a.startswith("안녕하세요, 가심사 심사역님"), a
    assert "Series A 이상 딜 네트워크에 함께해 주셔서 감사합니다." in a
    assert "10월에 공유해 주실 딜은 카톡 또는 메일로 전달 부탁드립니다." in a
    assert "{월}" not in a
    # 처음 안내 글이 아니다
    assert "참여 방법 안내" not in a

    # 빈 직함은 갈래 호칭으로 — 처음 안내와 같은 규칙(`sourcing_msg.honorific`)
    assert got["나심사"]["message"].startswith("안녕하세요, 나심사 심사역님")

    # 시리즈 A 가 아닌 갈래에 `Series A 이상` 이라고 하지 않는다 — M&A 갈래는 M&A 말로
    # 쓴 뼈대다(`sourcing_msg.remind_mna_body` — 기본 뼈대로 떨어지지 않는다).
    m = got["마투자"]["message"]
    assert m.startswith("안녕하세요, 마투자 이사님")
    assert "Series A" not in m and "Deal Sourcing 네트워크" not in m
    assert "M&A 딜 네트워크에 함께해 주셔서 감사합니다." in m
    assert "10월에 공유해 주실 M&A 딜(매각 · 인수 희망 기업)은" in m


def test_remind_reads_the_stored_template_and_fills_the_month(people, client, db):
    """운영자가 문구 화면에서 고친 글(주소를 넣은 것)에도 `{월}` 이 채워진다."""
    from app.models import MessageTemplate

    db.add(MessageTemplate(
        user_id=None, kind="sourcing_remind", name=SERIES_A, is_active=1,
        body="Series A 이상 딜 네트워크에 함께해 주셔서 감사합니다.\n\n"
             "{월}월에 공유해 주실 딜은 카톡 또는 메일(deal@example.com)로 전달 부탁드립니다."))
    # 처음 안내 문구가 따로 있어도 리마인드는 그것을 안 쓴다
    db.add(MessageTemplate(user_id=None, kind="sourcing_intro", name=SERIES_A,
                           is_active=1, body="처음 안내 저장 문구"))
    db.commit()

    got = _preview(client, [people["a"].id, people["m"].id])
    a = got["가심사"]["message"]
    assert "10월에 공유해 주실 딜은 카톡 또는 메일(deal@example.com)로" in a
    assert "{월}" not in a and "처음 안내 저장 문구" not in a
    # 다른 갈래는 그 갈래 문구가 없으니 코드 뼈대 그대로
    assert "deal@example.com" not in got["마투자"]["message"]

    # 처음 안내를 고르면 처음 안내 저장 문구다(④)
    intro = _preview(client, [people["a"].id], topic="sourcing_intro")
    assert "처음 안내 저장 문구" in intro["가심사"]["message"]


def test_a_picked_template_of_the_other_kind_is_not_used(people, client, db):
    """옛 고르개에 남은 처음 안내 번호가 리마인드에 실려 와도 처음 안내가 안 나간다."""
    from app.models import MessageTemplate

    intro = MessageTemplate(user_id=None, kind="sourcing_intro", name=SERIES_A,
                            is_active=1, body="참여 가능하시면 말씀 부탁드립니다")
    mine = MessageTemplate(user_id=1, kind="sourcing_remind", name=SERIES_A,
                           is_active=1, body="내 리마인드 {월}월")
    db.add_all([intro, mine])
    db.commit()

    got = _preview(client, [people["a"].id], closing_template_id=intro.id)
    assert "참여 가능하시면" not in got["가심사"]["message"]
    got = _preview(client, [people["a"].id], closing_template_id=mine.id)
    assert "내 리마인드 10월" in got["가심사"]["message"]


def test_the_sample_preview_follows_the_topic(people, client):
    """아무도 안 골랐을 때의 기본 문구도 고른 글로 보인다."""
    r = client.post("/api/deals/preview", json={
        "contact_ids": [], "mode": "sourcing", "topic": "sourcing_remind",
        "bucket": SERIES_A})
    sample = r.json()["previews"][0]
    assert sample["sample"] is True
    assert "10월에 공유해 주실 딜은" in sample["message"]


def test_an_unknown_topic_stops(people, client):
    """모르는 값을 처음 안내로 짐작해 보내지 않는다."""
    r = client.post("/api/deals/preview", json={
        "contact_ids": [people["a"].id], "mode": "sourcing", "topic": "sourcing_x"})
    assert r.status_code == 400
    r = client.post("/api/deals/send", json={
        "contact_ids": [people["a"].id], "mode": "sourcing", "topic": "sourcing_x"})
    assert r.status_code == 400


# ── ③ 이 달 딜 받음 ─────────────────────────────────────────────────────────

def _mark(db, row):
    from app.services import sourcing_receipts

    sourcing_receipts.mark(db, row.id, sourcing_receipts.month_of())
    db.commit()


def test_received_this_month_is_left_out_by_default(people, client, db):
    from app.models import DealBatch, SendItem, SendJob

    _mark(db, people["a"])
    r = client.post("/api/deals/send", json={
        "contact_ids": [people["a"].id, people["b"].id], "mode": "sourcing",
        "topic": "sourcing_remind"})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["total"] == 1
    assert [(s["name"], "이번 달 딜 받음" in s["reason"]) for s in out["skipped"]] == [
        ("가심사", True)]

    job = db.get(SendJob, out["job_id"])
    # 잡 종류는 처음 안내와 같다(발송 프로그램이 아는 종류) — 글은 topic 이 말한다
    assert (job.kind, job.topic, job.status) == ("sourcing_intro", "sourcing_remind", "queued")
    assert "딜 소싱 리마인드" in db.get(DealBatch, job.batch_id).title
    item = db.query(SendItem).filter_by(job_id=job.id).one()
    assert item.sourcing_contact_id == people["b"].id
    assert item.room_name == "나심사 소싱방"
    assert "10월에 공유해 주실 딜은" in item.message
    assert item.message.startswith("안녕하세요, 나심사 심사역님")


def test_received_can_be_included(people, client, db):
    from app.models import SendItem

    _mark(db, people["a"])
    r = client.post("/api/deals/send", json={
        "contact_ids": [people["a"].id, people["b"].id], "mode": "sourcing",
        "topic": "sourcing_remind", "include_received": True})
    assert r.status_code == 200, r.text
    assert r.json()["total"] == 2 and r.json()["skipped"] == []
    names = {i.recipient_name for i in db.query(SendItem).filter_by(job_id=r.json()["job_id"])}
    assert names == {"가심사", "나심사"}

    # 미리보기는 넣은 분을 한 번 더 짚는다
    got = _preview(client, [people["a"].id, people["b"].id])
    assert "이번 달 딜 받음" in got["가심사"]["warnings"]
    assert "이번 달 딜 받음" not in got["나심사"]["warnings"]


def test_when_everyone_received_nothing_is_made(people, client, db):
    from app.models import SendJob

    _mark(db, people["a"])
    r = client.post("/api/deals/send", json={
        "contact_ids": [people["a"].id], "mode": "sourcing", "topic": "sourcing_remind"})
    assert r.status_code == 400
    assert "이번 달 딜 받음" in r.json()["detail"]
    assert db.query(SendJob).count() == 0


def test_received_last_month_does_not_count(people, client, db):
    from app.services import sourcing_receipts

    sourcing_receipts.mark(db, people["a"].id, "2026-09")
    db.commit()
    r = client.post("/api/deals/send", json={
        "contact_ids": [people["a"].id], "mode": "sourcing", "topic": "sourcing_remind"})
    assert r.status_code == 200 and r.json()["total"] == 1


def test_the_screen_marks_who_received_this_month(people, client, db):
    _mark(db, people["a"])
    body = client.get("/deals").text
    picker = body[body.index('id="sourcing-list"'):]
    marked = re.findall(r'data-received="1"[\s\S]*?class="contact-cb" value="(\d+)"', picker)
    assert marked == [str(people["a"].id)]
    # 카드에 `10월 딜 받음` 표시가 그 사람에게만 보인다
    assert len(re.findall(r'class="tag soft received-tag">10월 딜 받음', picker)) == 1


def test_draft_and_schedule_work_the_same(people, client, db):
    """[발송 시작] 을 기다리는 회차 · 예약도 처음 안내와 같은 길이다."""
    from app.models import SendJob

    r = client.post("/api/deals/send", json={
        "contact_ids": [people["b"].id], "mode": "sourcing", "topic": "sourcing_remind",
        "draft": True})
    assert r.status_code == 200
    job = db.get(SendJob, r.json()["job_id"])
    assert (job.status, job.topic) == ("draft", "sourcing_remind")


def test_the_screen_sends_the_topic_and_drops_the_received():
    """고르개 · 제외 · 포함 · 명단 다시 읽기 — 브라우저 쪽(`tests/js`)."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("node 미설치 — 브라우저 로직 테스트 생략 "
                    "(호스트에서 `node tests/js/sourcing_remind_test.js`)")
    result = subprocess.run([node, str(REMIND_JS)], capture_output=True, text=True,
                            timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr


# ── ④ 처음 안내는 그대로 ───────────────────────────────────────────────────

def test_intro_is_unchanged(people, client, db):
    from app.models import DealBatch, SendItem, SendJob

    default = _preview(client, [people["a"].id], topic="")
    named = _preview(client, [people["a"].id], topic="sourcing_intro")
    assert default["가심사"]["message"] == named["가심사"]["message"]
    assert "Deal Sourcing 네트워크 참여 방법 안내 드립니다." in default["가심사"]["message"]

    # 처음 안내는 이 달 딜 받음을 보지 않는다(지금까지 그대로). 받는 분은 제안 대기중이다
    _mark(db, people["a"])
    people["a"].participation = "딜 소싱 참여 제안 대기중"
    db.commit()
    r = client.post("/api/deals/send", json={
        "contact_ids": [people["a"].id], "mode": "sourcing"})
    assert r.status_code == 200 and r.json()["skipped"] == []
    job = db.get(SendJob, r.json()["job_id"])
    assert (job.kind, job.topic) == ("sourcing_intro", None)
    assert "딜 소싱 제안" in db.get(DealBatch, job.batch_id).title
    item = db.query(SendItem).filter_by(job_id=job.id).one()
    assert "참여 방법 안내" in item.message


# ── 문구 화면 ───────────────────────────────────────────────────────────────

def test_the_template_kind_is_bucket_named_and_editable():
    from app.routers.templates_crud import KIND_LABELS, VARIABLES
    from app.services import sourcing_msg, template_pick

    assert sourcing_msg.REMIND_KIND == "sourcing_remind"   # 자동 리마인드(#277)와 같은 이름
    assert "sourcing_remind" in template_pick.NAME_IS_A_BUCKET
    assert "sourcing_remind" in KIND_LABELS
    assert "{월}" in dict(VARIABLES)


def test_the_templates_page_shows_the_remind_with_the_month(people, client, db):
    from app.models import MessageTemplate

    db.add(MessageTemplate(user_id=None, kind="sourcing_remind", name=SERIES_A,
                           is_active=1, body="{월}월 딜 부탁드립니다"))
    db.commit()
    body = client.get("/templates").text
    section = body[body.index('id="sourcing_remind"'):]
    section = section[:section.index('class="tpl-new"')]
    assert "딜 소싱 제안 — 월간 리마인드" in section
    # 미리보기는 인사말 + 이 달로 채운 글, 고칠 칸에는 저장된 글 그대로
    assert "10월 딜 부탁드립니다" in section
    assert "{월}월 딜 부탁드립니다" in section
    # 그 밖의 문구에 또 서지 않는다
    others = body[body.index('id="others"'):]
    assert 'id="sourcing_remind"' not in others


def test_renaming_a_bucket_takes_the_remind_along(people, client, db):
    from app.models import MessageTemplate
    from app.services import sourcing_buckets

    # 원본 시트의 갈래(시리즈 A · M&A · 구주·후속 · 대표 · 개인참여)는 이름을 못 바꾼다
    # — 투자사 관리 현황과 이어진 갈래다(`sourcing_sync.BRANCHES` ·
    # `tests/test_sourcing_vc_sync.py`). 그래서 옮겨 가는지는 잇지 않는 갈래로 본다.
    from app.models import SourcingContact

    lp = "해외 LP  찾는 투자사"
    db.add(SourcingContact(bucket=lp, position=1, name="가대표"))
    db.add(MessageTemplate(user_id=None, kind="sourcing_remind", name=lp,
                           is_active=1, body="리마인드"))
    db.commit()
    sourcing_buckets.rename(db, lp, "해외 LP 찾는 투자사 (2026)")
    db.commit()
    row = db.query(MessageTemplate).filter_by(kind="sourcing_remind").one()
    assert row.name == "해외 LP 찾는 투자사 (2026)"


# ── ⑤ 심는 글 ───────────────────────────────────────────────────────────────

def test_the_seeded_text_has_no_email_address(db, users):
    from app.models import MessageTemplate, SourcingContact
    from app.services import sourcing_msg
    from scripts.bootstrap import SOURCING_REMIND_BUCKET, seed_sourcing_remind

    for bucket in (SERIES_A, MNA, "딜 소싱  참여 투자사 대표", ""):
        text = sourcing_msg.remind_default_body(bucket)
        assert "@" not in text and not EMAIL.search(text), bucket
        assert "{월}" in text          # 달은 보낼 때 채운다

    # 명단이 비었으면 운영의 갈래 이름으로 하나
    assert seed_sourcing_remind(db) == 1
    db.commit()
    row = db.query(MessageTemplate).filter_by(kind="sourcing_remind").one()
    assert (row.user_id, row.name) == (None, SOURCING_REMIND_BUCKET)
    assert row.body == sourcing_msg.remind_default_body(SERIES_A)
    assert row.body.splitlines() == [
        "Series A 이상 딜 네트워크에 함께해 주셔서 감사합니다.",
        "",
        "{월}월에 공유해 주실 딜은 카톡 또는 메일로 전달 부탁드립니다.",
        "지난번 공유드린 딜 중 관심 있는 기업이 있으시면 IR Deck을 보내 드리겠습니다.",
        "",
        "딜을 전달해 주실 때 기업 담당자 성함과 연락처도 함께 알려 주시면,",
        "투자 검토 의향이 있는 투자사와 바로 연결해 드리겠습니다.",
        "",
        "이미 전달해 주셨다면 이 메시지는 넘겨 주셔도 됩니다.",
        "감사합니다.",
    ]

    # 다시 돌아도 덮지 않는다 — 운영자가 넣은 주소가 남아야 한다
    row.body = row.body.replace("메일로", "메일(deal@example.com)로")
    db.commit()
    assert seed_sourcing_remind(db) == 0
    db.commit()
    assert "deal@example.com" in db.query(MessageTemplate).filter_by(
        kind="sourcing_remind").one().body

    # 명단에 시리즈 A 갈래가 있으면 **그 이름**으로 심는다(문구 이름 = 갈래).
    # 띄어쓰기만 다른 이름(`딜소싱`)은 이미 심은 갈래라 또 심지 않는다 — 한 자리에
    # 팀 문구가 둘이면 아무것도 안 집힌다(`tests/test_sourcing_bucket_whitespace.py`).
    db.add_all([SourcingContact(bucket="시리즈 A 이상 딜소싱 참여 심사역", name="가"),
                SourcingContact(bucket="시리즈 A 이상 개인 참여 심사역", name="다"),
                SourcingContact(bucket=MNA, name="나")])
    db.commit()
    # M&A 갈래에도 하나 — M&A 말로 쓴 글이다(`sourcing_msg.remind_mna_body`).
    assert seed_sourcing_remind(db) == 2
    db.commit()
    names = {r.name for r in db.query(MessageTemplate).filter_by(kind="sourcing_remind")}
    assert names == {SOURCING_REMIND_BUCKET, "시리즈 A 이상 개인 참여 심사역", MNA}
    mna = db.query(MessageTemplate).filter_by(kind="sourcing_remind", name=MNA).one()
    assert mna.body == sourcing_msg.remind_mna_body()
    assert "@" not in mna.body and "{월}" in mna.body


def test_bootstrap_seeds_it(db, users):
    from app.models import MessageTemplate
    from scripts.bootstrap import bootstrap

    bootstrap(db)
    db.commit()
    assert db.query(MessageTemplate).filter_by(kind="sourcing_remind").count() == 1
