"""미팅 결과 문의 문자 — **담당 팀원에게만**, 하루 한 번.

## 왜 이 검사가 있나

이 앱이 바깥으로 HTTP 를 부르는 것은 이번이 처음이고, 나가는 것이 **돈이 드는
문자**다. 잘못되면 조용히 새는 것이 아니라 폰이 울리고 요금이 나간다. 그래서
지키는 것을 못박아 둔다.

1. **안 켜면 아무 일도 없다.** 설정이 비면 실도 안 뜨고 발송도 안 한다.
2. **같은 날 두 번 안 간다.** 실은 30분마다 깨어난다 — 막지 않으면 하루 스무 통.
3. **담당 팀원에게만 간다.** 남의 미팅이 내 문자에 섞이지 않는다.
4. **팀원 아닌 번호로는 못 간다.** 투자사에게 갈 길을 만들지 않는 것이 이
   기능에서 넘으면 안 되는 선이다.
5. **밤과 주말에는 안 울린다.**
6. 건수가 하나일 때 `외 0건` 이 되지 않는다. 문구는 단문(90바이트)에 들어간다.
7. 업체가 실패해도 앱이 멈추지 않고, **실패한 것이 화면에 남는다.**
8. 번호·문구가 로그나 DB 에 그대로 남지 않는다.

## 진짜 문자는 한 통도 안 나간다

`no_real_api` 가 **모든 검사에** 자동으로 붙어, 업체를 실제로 부르는 자리
(`sms._vendor_send`)를 폭발하게 만들어 둔다. 가짜 발송기(`outbox`)를 안 끼운
검사가 실수로 발송 경로를 타면 그 자리에서 터진다.

날짜는 전부 `now=` 로 못박는다. 자정이나 주말에 결과가 바뀌는 검사를 만들지
않는다.
"""
from __future__ import annotations

from datetime import datetime

import pytest

# 검사가 기준으로 삼는 순간. 2026-09-07 은 **월요일**이고 오전 10시다.
MONDAY_10AM = datetime(2026, 9, 7, 10, 0)
SATURDAY_10AM = datetime(2026, 9, 12, 10, 0)
MONDAY_3AM = datetime(2026, 9, 7, 3, 0)

# 미팅을 언제 완료했는지는 상관없다 — 물어볼 날이 지났으면 오늘 물어본다.
# 실제 오늘이 언제든 지나 있도록 아주 옛날로 둔다.
LONG_PAST = "2020-01-06"


@pytest.fixture(autouse=True)
def no_real_api(monkeypatch):
    """**검사에서 진짜 문자 업체를 부르면 그 자리에서 터진다.**

    계정도 없고 발신번호 등록도 안 됐다. 실제 API 를 부르는 코드는 한 번도
    돌지 않아야 한다 — 잊지 않기를 바라는 대신 여기서 막는다.
    """
    from app.services import sms

    def boom(*args, **kwargs):
        raise AssertionError("검사에서 진짜 문자 업체를 부르면 안 된다")

    monkeypatch.setattr(sms, "_vendor_send", boom)


@pytest.fixture()
def sms_on(monkeypatch):
    """설정이 다 갖춰진 상태. 값은 전부 가짜다."""
    monkeypatch.setenv("DEALFLOW_SMS_API_KEY", "test-key")
    monkeypatch.setenv("DEALFLOW_SMS_API_SECRET", "test-secret")
    monkeypatch.setenv("DEALFLOW_SMS_FROM", "02-000-0000")
    monkeypatch.setenv("DEALFLOW_DOMAIN", "deal.example.org")


@pytest.fixture()
def outbox(monkeypatch):
    """가짜 발송기. 나간 문자를 담아 두기만 한다."""
    from app.services import sms

    sent = []

    def fake_send(to, text, settings=None):
        sent.append({"to": to, "text": text})
        return "M-test"

    monkeypatch.setattr(sms, "send", fake_send)
    return sent


def _contact(db, user, name, firm):
    from app.models import VcContact

    row = VcContact(user_id=user.id, name=name, firm=firm,
                    source_sheet="내 명단", connect_stage="connected")
    db.add(row)
    db.flush()
    return row


def _due_meeting(db, user, contact, when="2020-01-06"):
    """결과를 물어볼 때가 지난 미팅 하나.

    `pipeline` 이 '오늘 물어볼 것' 으로 세는 조건 그대로다 — 완료됐고,
    아직 안 물어봤고, 거절로 끝나지 않았고, 물어볼 날이 지났다.
    """
    from app.models import Meeting

    row = Meeting(user_id=user.id, contact_id=contact.id, scheduled_at=when,
                  status="done", done_at=when, followup_due=when,
                  followup_done=0, outcome="reviewing")
    db.add(row)
    db.flush()
    return row


@pytest.fixture()
def due(db, users):
    """u1 에게 결과 문의 3건, u2 에게 1건. 담당자는 서로 다르다."""
    u1, u2 = users["u1"], users["u2"]
    for index, (name, firm) in enumerate(
            [("가담당", "가나벤처스"), ("나담당", "다라벤처스"),
             ("다담당", "마바벤처스")]):
        _due_meeting(db, u1, _contact(db, u1, name, firm),
                     when=f"2020-01-0{index + 4}")
    _due_meeting(db, u2, _contact(db, u2, "라담당", "사아벤처스"))
    db.commit()
    return {"u1": u1, "u2": u2}


# --- 안 켜면 아무 일도 없다 --------------------------------------------------

def test_nothing_happens_without_settings(db, due, outbox):
    """설정이 없으면 **조용히** 아무것도 안 한다(메일이 지금 그렇다)."""
    from app.services import followup_sms

    result = followup_sms.run_once(db, now=MONDAY_10AM)

    assert result["skipped"] == "설정 없음"
    assert outbox == []


def test_the_thread_does_not_even_start(db, due):
    """실도 뜨지 않는다 — 안 켠 사람의 서버에서 도는 것이 없어야 한다."""
    from app.services import followup_sms

    assert followup_sms.start_scheduler() is None


def test_address_is_part_of_being_configured(db, due, outbox, monkeypatch):
    """열쇠가 있어도 **주소가 없으면 켜진 것이 아니다.**

    링크 없는 문자는 화면으로 갈 길이 없어 받아도 할 수 있는 것이 없다.
    """
    from app.services import followup_sms

    monkeypatch.setenv("DEALFLOW_SMS_API_KEY", "test-key")
    monkeypatch.setenv("DEALFLOW_SMS_API_SECRET", "test-secret")
    monkeypatch.setenv("DEALFLOW_SMS_FROM", "0200000000")
    monkeypatch.setenv("DEALFLOW_DOMAIN", "")

    assert followup_sms.run_once(db, now=MONDAY_10AM)["skipped"] == "설정 없음"
    assert outbox == []
    assert "서비스 주소(DEALFLOW_DOMAIN)" in followup_sms.status(db)["missing"]


# --- 담당 팀원에게만 ---------------------------------------------------------

def test_each_member_gets_only_their_own(db, due, sms_on, outbox):
    """남의 미팅이 내 문자에 섞이지 않는다. 건수도 각자의 것이다."""
    from app.services import followup_sms

    result = followup_sms.run_once(db, now=MONDAY_10AM)

    assert result["sent"] == 2
    by_phone = {row["to"]: row["text"] for row in outbox}
    assert set(by_phone) == {"01000000001", "01000000002"}
    assert "외 2건" in by_phone["01000000001"]        # u1 은 3건
    assert "라담당님(사아벤처스)" in by_phone["01000000002"]
    assert "외" not in by_phone["01000000002"]        # u2 는 1건
    assert "라담당" not in by_phone["01000000001"]


def test_the_name_matches_the_top_of_the_screen(db, due, sms_on, outbox):
    """문자에 적힌 이름은 **화면 맨 위에 뜨는 그 사람**이다.

    문자를 보고 화면을 열었을 때 다른 이름이 먼저 보이면, 받은 사람은 문자가
    말한 건을 목록에서 찾아 헤맨다. 순서는 `pipeline` 이 정하는 그대로 쓴다.
    """
    from app.services import pipeline, followup_sms

    followup_sms.run_once(db, now=MONDAY_10AM)

    top = pipeline.today_items(db, due["u1"])["due_followups"][0]
    text = next(row["text"] for row in outbox if row["to"] == "01000000001")
    assert f"{top['name']}님({top['firm']})" in text


def test_member_without_a_phone_is_skipped(db, due, sms_on, outbox):
    """번호가 없는 팀원은 건너뛴다 — 보낼 곳이 없는 것은 고장이 아니다."""
    from app.models import SmsNotice
    from app.services import followup_sms

    due["u1"].phone = None
    db.commit()

    result = followup_sms.run_once(db, now=MONDAY_10AM)

    assert result["sent"] == 1
    assert [row["to"] for row in outbox] == ["01000000002"]
    # 보내지도 않은 줄을 남기지 않는다 — 화면이 보냈다고 읽는다.
    assert db.query(SmsNotice).filter_by(user_id=due["u1"].id).count() == 0


def test_a_number_that_is_not_a_team_member_is_refused(db, due, sms_on):
    """**투자사에게 갈 길을 만들지 않는다.**

    번호는 `users.phone` 에서만 꺼내지만, 마지막 문을 하나 더 둔다.
    """
    from app.models import VcContact
    from app.services import followup_sms

    investor = db.query(VcContact).filter_by(name="가담당").first()
    investor.phone = "010-9999-8888"
    db.commit()

    with pytest.raises(followup_sms.NotTeamPhone):
        followup_sms.assert_team_phone(db, investor.phone)

    # 팀원 번호는 하이픈이 섞여 있어도 통과한다(같은 규칙으로 숫자만 남긴다).
    assert followup_sms.assert_team_phone(db, "010-0000-0001") == "01000000001"


def test_a_member_who_left_is_not_a_recipient(db, due, sms_on, outbox):
    """쉬는 계정에는 안 간다 — 나간 사람 폰이 계속 울리지 않게."""
    from app.services import followup_sms

    due["u1"].is_active = 0
    db.commit()

    with pytest.raises(followup_sms.NotTeamPhone):
        followup_sms.assert_team_phone(db, "01000000001")
    followup_sms.run_once(db, now=MONDAY_10AM)
    assert [row["to"] for row in outbox] == ["01000000002"]


# --- 같은 날 두 번 안 간다 ---------------------------------------------------

def test_only_once_a_day(db, due, sms_on, outbox):
    """실은 30분마다 깨어난다 — 막지 않으면 하루에 스무 통이 간다."""
    from app.services import followup_sms

    followup_sms.run_once(db, now=MONDAY_10AM)
    assert len(outbox) == 2

    again = followup_sms.run_once(db, now=datetime(2026, 9, 7, 10, 30))
    assert again["sent"] == 0
    assert len(outbox) == 2                      # 늘지 않았다

    tomorrow = followup_sms.run_once(db, now=datetime(2026, 9, 8, 9, 0))
    assert tomorrow["sent"] == 2                 # 다음 날은 다시 간다
    assert len(outbox) == 4


def test_a_failed_day_is_not_retried_the_same_day(db, due, sms_on, monkeypatch):
    """실패해도 그날은 다시 안 보낸다.

    업체가 받아 놓고 응답만 실패했을 수 있다. 다시 보내면 **돈이 두 번 나가고
    폰이 30분마다 울린다.** 결과 문의는 사라지지 않으므로 다음 날 다시 간다.
    """
    from app.services import followup_sms, sms

    calls = []

    def always_fails(to, text, settings=None):
        calls.append(to)
        raise sms.SmsSendFailed("업체가 접수하지 않았습니다 (3000): 잔액 부족")

    monkeypatch.setattr(sms, "send", always_fails)

    assert followup_sms.run_once(db, now=MONDAY_10AM)["failed"] == 2
    assert followup_sms.run_once(db, now=datetime(2026, 9, 7, 11, 0))["failed"] == 0
    assert len(calls) == 2


# --- 물어볼 것이 없으면 ------------------------------------------------------

def test_nothing_to_ask_means_no_message(db, users, sms_on, outbox):
    """미팅 자체가 없으면 아무 문자도 안 간다."""
    from app.services import followup_sms

    result = followup_sms.run_once(db, now=MONDAY_10AM)

    assert (result["sent"], result["failed"]) == (0, 0)
    assert outbox == []


def test_an_answered_followup_stops_the_message(db, due, sms_on, outbox):
    """물어본 건은 빠진다 — 판단은 `pipeline` 한 곳에서 온다."""
    from app.models import Meeting
    from app.services import followup_sms

    for meeting in db.query(Meeting).filter_by(user_id=due["u1"].id).all():
        meeting.followup_done = 1
    db.commit()

    followup_sms.run_once(db, now=MONDAY_10AM)

    assert [row["to"] for row in outbox] == ["01000000002"]


# --- 언제 보내는가 -----------------------------------------------------------

def test_it_does_not_ring_at_dawn(db, due, sms_on, outbox):
    """새벽 3시에 폰이 울리면 안 된다."""
    from app.services import followup_sms

    assert followup_sms.run_once(db, now=MONDAY_3AM)["skipped"] == "보내는 시간대가 아님"
    assert outbox == []


def test_it_does_not_ring_at_night(db, due, sms_on, outbox):
    """밤 9시에 알려도 그날 할 수 있는 것이 없다. 아침에 그대로 간다."""
    from app.services import followup_sms

    late = followup_sms.run_once(db, now=datetime(2026, 9, 7, 21, 0))
    assert late["skipped"] == "보내는 시간대가 아님"
    assert followup_sms.run_once(db, now=datetime(2026, 9, 8, 9, 0))["sent"] == 2


def test_not_on_the_weekend(db, due, sms_on, outbox):
    """결과 문의는 평일에 하는 일이다. 토요일 알림은 할 수 없는 일을 알린다."""
    from app.services import followup_sms

    assert followup_sms.run_once(db, now=SATURDAY_10AM)["skipped"] == "보내는 시간대가 아님"
    assert outbox == []


# --- 문구 -------------------------------------------------------------------

LINK = "https://deal.example.org/ir#meetings"


def _rows(*pairs):
    return [{"name": name, "firm": firm} for name, firm in pairs]


def test_a_single_item_has_no_zero_count(sms_on):
    """`외 0건` 이 되지 않게."""
    from app.services import followup_sms

    text = followup_sms.compose(_rows(("홍길동", "가나벤처스")), LINK)

    assert text.startswith("[결과 문의] 홍길동님(가나벤처스)\n")
    assert "외" not in text


def test_more_items_are_counted_as_others(sms_on):
    """3건이면 맨 앞 한 사람 + `외 2건`."""
    from app.services import followup_sms

    text = followup_sms.compose(
        _rows(("홍길동", "가나벤처스"), ("김철수", "다라벤처스"),
              ("이영희", "마바벤처스")), LINK)

    assert "홍길동님(가나벤처스) 외 2건" in text


def test_the_message_carries_the_link(db, due, sms_on, outbox):
    """링크는 결과 문의 목록이 있는 화면으로 간다. 주소는 설정에서 온다."""
    from app.services import followup_sms

    followup_sms.run_once(db, now=MONDAY_10AM)

    assert all(row["text"].endswith(LINK) for row in outbox)


def test_the_message_stays_a_short_message(sms_on):
    """**단문 90바이트를 넘기지 않는다** — 넘으면 장문이 되어 값이 뛴다.

    이름·회사명이 길면 회사명을 먼저 버리고, 그래도 넘으면 이름까지 버린다.
    링크와 건수는 끝까지 남는다.
    """
    from app.services import followup_sms, sms

    long_firm = followup_sms.compose(
        _rows(("남궁민수", "아주아주긴이름벤처스파트너스유한회사"),
              ("김철수", "다라벤처스")), LINK)

    assert sms.byte_len(long_firm) <= sms.SMS_MAX_BYTES
    assert "남궁민수님 외 1건" in long_firm      # 회사명만 빠졌다
    assert long_firm.endswith(LINK)

    plain = followup_sms.compose(_rows(("홍길동", "가나벤처스")), LINK)
    assert sms.byte_len(plain) <= sms.SMS_MAX_BYTES


def test_a_very_long_name_falls_back_to_the_count(sms_on):
    """이름까지 버려야 할 만큼 길면 건수만 남긴다 — 링크는 남는다."""
    from app.services import followup_sms, sms

    text = followup_sms.compose(_rows(("가" * 40, "나" * 40)), LINK)

    assert sms.byte_len(text) <= sms.SMS_MAX_BYTES
    assert "[결과 문의] 미팅 1건" in text
    assert text.endswith(LINK)


# --- 업체가 실패할 때 --------------------------------------------------------

def test_one_failure_does_not_stop_the_rest(db, due, sms_on, monkeypatch):
    """한 사람이 실패해도 나머지는 간다. 그리고 앱은 멈추지 않는다."""
    from app.services import followup_sms, sms

    def flaky(to, text, settings=None):
        if to == "01000000001":
            raise sms.SmsSendFailed("문자 업체에 연결하지 못했습니다: timed out")
        return "M-ok"

    monkeypatch.setattr(sms, "send", flaky)

    result = followup_sms.run_once(db, now=MONDAY_10AM)

    assert (result["sent"], result["failed"]) == (1, 1)


def test_a_failure_is_visible_on_the_team_screen(db, due, sms_on, monkeypatch):
    """**조용히 삼키지 않는다.** 왜 못 갔는지가 화면에 남는다."""
    from app.services import followup_sms, sms

    def always_fails(to, text, settings=None):
        raise sms.SmsSendFailed("업체가 접수하지 않았습니다 (3000): 잔액 부족")

    monkeypatch.setattr(sms, "send", always_fails)
    followup_sms.run_once(db, now=MONDAY_10AM)

    rows = followup_sms.status(db, today=MONDAY_10AM.date())["today"]
    assert [row["status"] for row in rows] == ["failed", "failed"]
    assert "잔액 부족" in rows[0]["error"]


def test_a_sent_message_is_visible_too(db, due, sms_on, outbox):
    """보낸 것도 남는다 — 몇 건짜리였는지까지."""
    from app.services import followup_sms

    followup_sms.run_once(db, now=MONDAY_10AM)

    rows = followup_sms.status(db, today=MONDAY_10AM.date())["today"]
    assert [(row["status"], row["count"]) for row in rows] == [("sent", 3), ("sent", 1)]


def test_the_stored_reason_does_not_keep_the_number(db, due, sms_on, monkeypatch):
    """업체가 번호를 되돌려줘도 그것을 그대로 적어 두지 않는다."""
    from app.models import SmsNotice
    from app.services import followup_sms, sms

    def leaky(to, text, settings=None):
        raise sms.SmsSendFailed(f"수신거부 번호입니다: {to}")

    monkeypatch.setattr(sms, "send", leaky)
    followup_sms.run_once(db, now=MONDAY_10AM)

    stored = db.query(SmsNotice).first().error
    assert "01000000001" not in stored
    assert "수신거부" in stored


# --- 업체에 매인 자리 --------------------------------------------------------

def test_the_signature_follows_the_vendor_recipe(sms_on):
    """서명은 `HMAC-SHA256(date + salt, apiSecret)` 이다.

    표준 라이브러리로 되는 것을 확인해 둔다 — 이것 때문에 업체 SDK 를
    새 의존성으로 넣을 이유가 없다. **그물을 타지 않는 계산이다.**
    """
    import hashlib
    import hmac
    from datetime import timezone

    from app.services import sms

    settings = sms.load_settings()
    stamp = datetime(2026, 9, 7, 1, 0, tzinfo=timezone.utc)
    header = sms._auth_header(settings, now=stamp, salt="abc123")

    expected = hmac.new(b"test-secret", b"2026-09-07T01:00:00.000Zabc123",
                        hashlib.sha256).hexdigest()
    assert f"apiKey={settings.api_key}" in header
    assert "date=2026-09-07T01:00:00.000Z" in header
    assert header.endswith(f"signature={expected}")
    assert "test-secret" not in header       # 열쇠 자체는 나가지 않는다


def test_settings_never_show_the_secret(sms_on):
    """화면에는 **있음/없음만** 나간다."""
    from app.services import followup_sms

    shown = followup_sms.status()

    assert shown["has_secret"] is True
    assert "test-secret" not in repr(shown)
    assert shown["configured"] is True


# --- 팀 현황 화면 ------------------------------------------------------------

@pytest.fixture()
def admin(client, db, users):
    from .conftest import DEMO_PASSWORD

    users["u2"].role = "admin"
    db.commit()
    client.post("/login", data={"phone": "01000000002", "password": DEMO_PASSWORD})
    return client


def test_the_screen_says_it_is_not_turned_on(admin):
    """설정이 없으면 **무엇이 없는지**를 메일과 나란히 알려 준다."""
    body = admin.get("/team").text

    assert "결과 문의 문자 알림" in body
    assert "API 키" in body and "발신번호" in body
    assert "서비스 주소(DEALFLOW_DOMAIN)" in body


def test_the_screen_shows_the_secret_only_as_stored(admin, sms_on):
    """켜져 있으면 켜졌다고 알리되, **비밀값 자체는 화면에 없다.**"""
    body = admin.get("/team").text

    assert "솔라피(SOLAPI)" in body
    assert "평일 09:00~20:00" in body
    assert "test-secret" not in body
    assert "test-key" not in body
