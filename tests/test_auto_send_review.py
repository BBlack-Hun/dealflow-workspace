"""미팅 후기 — **대기 목록은 저절로 서고, 보내는 것은 사람이다.**

## 왜 이 검사가 있나

물어볼 때가 되면 서버가 그 투자사에게 보낼 **발송 목록**을 만들어 둔다. 목록은
`draft` 로 서서 발송 프로그램이 집어가지 않고, 그 계정이 진행 화면에서
[발송 시작] 을 눌러야 나간다. 잘못 담긴 것을 **나가기 전에** 볼 수 있는 자리가
그 한 번이라, 그 한 번이 사라지지 않는 것을 여기서 못박는다.

1. **설정이 켜져 있어도 누르기 전에는 한 통도 안 나간다.** 발송 프로그램이
   폴링해도 집어갈 것이 없다.
2. **누르면 그때 나간다.**
3. **대기 목록에 몇 건이 서는지** 누르기 전에 알 수 있다.
4. **같은 건은 두 번 서지 않는다.** 실은 30분마다 깨어난다 — 막지 않으면 결과를
   적기 전까지 **매일** 같은 투자사 앞으로 목록이 선다.
5. **안 켜면 아무 일도 없다.** 설정 줄이 없으면 실도 안 뜨고 목록도 안 선다.
6. 정해진 한 계정 것으로만 선다. 다른 팀원 것은 섞이지 않는다.
7. 때가 안 된 미팅은 안 걸린다.
8. **밤·주말에는 안 선다.** 세운 뒤 곧바로 눌러 보내는 자리라 업무시간 안이어야
   한다.
9. 하루 상한을 넘지 않는다.
10. **문구가 화면 것과 글자 하나까지 같다**(`deals.review_message`).
11. 시험방 설정이 있으면 그리로 간다.

## 진짜로는 한 통도 안 나간다

이 검사는 **발송 목록까지만** 만든다. 실제로 카톡을 보내는 것은 각 PC 의 발송
프로그램이고, 검사는 그것을 띄우지 않는다.

날짜는 전부 `now=` 로 못박는다. 오늘이 무슨 요일이냐에 따라 결과가 달라지는
검사를 만들지 않는다.
"""
from __future__ import annotations

from datetime import datetime

import pytest

from tests.conftest import DEMO_PASSWORD, DEMO_TOKEN

# 2026-09-07 은 **월요일**이다. 09-12 는 토요일.
MONDAY_11AM = datetime(2026, 9, 7, 11, 0)
MONDAY_7AM = datetime(2026, 9, 7, 7, 0)
MONDAY_9PM = datetime(2026, 9, 7, 21, 0)
SATURDAY_11AM = datetime(2026, 9, 12, 11, 0)

# 미팅을 언제 했는지는 상관없다 — 물어볼 날이 지났으면 오늘 물어본다.
# 실제 오늘이 언제든 지나 있도록 아주 옛날로 둔다.
LONG_PAST = "2020-01-06"
# 아주 먼 뒷날. 이 날짜로는 결과를 물어볼 때가 오지 않는다.
FAR_FUTURE = "2999-01-04"


def _contact(db, user, name, firm, *, room=None, **kw):
    """카톡방까지 갖춘 투자사 담당자. 방 이름은 **사람마다 다르다** — 같은
    이름을 쓰면 누구에게 갔는지 세는 검사가 헛돈다."""
    from app.models import VcContact

    row = VcContact(user_id=user.id, name=name, firm=firm, title="심사역",
                    source_sheet="내 명단", connect_stage="connected",
                    kakao_room_name=(f"{firm} Deal 공유" if room is None
                                     else room), **kw)
    db.add(row)
    db.flush()
    return row


def _meeting(db, user, contact, when=LONG_PAST):
    """결과를 물어볼 때가 지난 미팅 하나.

    `pipeline` 이 '오늘 물어볼 것' 으로 세는 조건 그대로다(결과 문의 문자
    검사가 쓰는 것과 같은 모양).
    """
    from app.models import Meeting

    row = Meeting(user_id=user.id, contact_id=contact.id, scheduled_at=when,
                  status="done", done_at=when, followup_due=when,
                  followup_done=0, outcome="reviewing")
    db.add(row)
    db.flush()
    return row


def _turn_on(db, user, *, from_hour=10, until_hour=17, max_per_day=10,
             enabled=True):
    from app.services import auto_send

    return auto_send.save(db, auto_send.KIND_REVIEW, enabled=enabled,
                          user_id=user.id, from_hour=from_hour,
                          until_hour=until_hour, max_per_day=max_per_day)


@pytest.fixture()
def due(db, users):
    """u1 에게 결과 문의 3건, u2 에게 1건. 담당자는 서로 다르다."""
    u1, u2 = users["u1"], users["u2"]
    mine = []
    for index, (name, firm) in enumerate(
            [("가담당", "가나벤처스"), ("나담당", "다라벤처스"),
             ("다담당", "마바벤처스")]):
        contact = _contact(db, u1, name, firm)
        mine.append(_meeting(db, u1, contact, when=f"2020-01-0{index + 4}"))
    other = _meeting(db, u2, _contact(db, u2, "라담당", "사아벤처스"))
    db.commit()
    return {"u1": u1, "u2": u2, "mine": mine, "other": other}


def _press_send(client, db, job_id, phone="01000000001"):
    """그 계정으로 진행 화면의 **[발송 시작]** 을 누른다.

    화면이 부르는 것과 같은 주소다(`static/js/progress.js`). 누르는 사람은 그
    회차 주인이어야 한다 — 남의 회차는 라우터가 없는 것으로 답한다.
    """
    client.post("/login", data={"phone": phone, "password": DEMO_PASSWORD})
    answer = client.post(f"/api/jobs/{job_id}/start")
    db.expire_all()
    return answer


def _claim_by_agent(client, token=DEMO_TOKEN):
    """발송 프로그램이 지금 집어갈 것이 있는지 물어본다.

    실제 폴링과 같은 주소·같은 값이다(`agent/main.py`). 집어갈 것이 없으면
    204 다 — **누르기 전에는 그래야 한다.**
    """
    return client.get("/api/agent/poll",
                      params={"kinds": "deal_intro,ir_delivery,sourcing_intro"},
                      headers={"Authorization": f"Bearer {token}"})


def _jobs(db):
    from app.models import SendJob

    from sqlalchemy import select

    return db.execute(select(SendJob).order_by(SendJob.id)).scalars().all()


def _items(db, job):
    return list(job.items)


# --- 0. 사람이 누르기 전에는 한 통도 안 나간다  ★ ------------------------------

def test_nothing_goes_out_until_a_person_presses_send(db, due, client):
    """켜 두어도 **누르기 전에는 발송 프로그램이 집어갈 것이 없다.**

    이 검사가 이 기능의 알맹이다. 목록은 `draft` 로 서고, 발송 프로그램은
    `queued` 인 회차만 집어간다(`routers/agent_api.py: poll`).
    """
    from app.models import SendJob
    from app.services import auto_send

    _turn_on(db, due["u1"])
    result = auto_send.run_once(db, now=MONDAY_11AM)

    assert result["created"] == 3
    job = db.get(SendJob, result["job_id"])
    assert job.status == "draft"
    # 발송기가 물어봐도 줄 것이 없다.
    assert _claim_by_agent(client).status_code == 204
    assert {i.status for i in job.items} == {"pending"}


def test_it_goes_out_after_the_press(db, due, client):
    """누르면 그때 `queued` 가 되고, 발송 프로그램이 집어간다."""
    from app.models import SendJob
    from app.services import auto_send

    _turn_on(db, due["u1"])
    job_id = auto_send.run_once(db, now=MONDAY_11AM)["job_id"]

    assert _press_send(client, db, job_id).status_code == 200
    assert db.get(SendJob, job_id).status == "queued"

    claimed = _claim_by_agent(client)
    assert claimed.status_code == 200
    assert claimed.json()["job_id"] == job_id


def test_the_list_says_how_many_and_to_whom_before_the_press(db, due, client):
    """누르기 전에 **몇 건인지·누구에게 가는지**가 보인다.

    진행 화면이 읽는 값 그대로다(`/api/jobs/{id}` → `progress.js`). 발송은
    되돌릴 수 없어서, 누른 뒤에 아는 것은 늦다.
    """
    from app.services import auto_send

    _turn_on(db, due["u1"])
    job_id = auto_send.run_once(db, now=MONDAY_11AM)["job_id"]

    client.post("/login", data={"phone": "01000000001",
                                "password": DEMO_PASSWORD})
    seen = client.get(f"/api/jobs/{job_id}").json()

    assert seen["status"] == "draft"
    assert seen["counts"]["pending"] == 3
    assert seen["counts"]["sent"] == 0
    assert {row["contact_name"] for row in seen["items"]} == {
        "가담당", "나담당", "다담당"}
    assert all(row["room_name"] for row in seen["items"])


def test_only_the_owner_can_press(db, due, client):
    """남의 계정은 누를 수 없다 — 그 회차는 **없는 것으로** 답한다."""
    from app.models import SendJob
    from app.services import auto_send

    _turn_on(db, due["u1"])
    job_id = auto_send.run_once(db, now=MONDAY_11AM)["job_id"]

    answer = _press_send(client, db, job_id, phone="01000000002")

    assert answer.status_code == 404
    assert db.get(SendJob, job_id).status == "draft"


def test_pressing_twice_does_not_send_twice(db, due, client):
    """두 번 눌러도 두 번 나가지 않는다 — 이미 시작된 회차는 거절한다."""
    from app.services import auto_send

    _turn_on(db, due["u1"])
    job_id = auto_send.run_once(db, now=MONDAY_11AM)["job_id"]

    assert _press_send(client, db, job_id).status_code == 200
    assert client.post(f"/api/jobs/{job_id}/start").status_code == 400


# --- 1. 안 켜면 아무 일도 없다 -----------------------------------------------

def test_nothing_happens_when_it_is_off(db, due):
    """설정 줄이 아예 없다 — **기본이 꺼짐**이다(메일·문자가 그렇다)."""
    from app.services import auto_send

    result = auto_send.run_once(db, now=MONDAY_11AM)

    assert result["skipped"] == "꺼짐"
    assert result["created"] == 0
    assert _jobs(db) == []


def test_a_row_that_is_not_enabled_is_still_off(db, due):
    """계정만 골라 두고 켜지 않은 상태 — 그것도 꺼짐이다."""
    from app.services import auto_send

    _turn_on(db, due["u1"], enabled=False)

    assert auto_send.run_once(db, now=MONDAY_11AM)["skipped"] == "꺼짐"
    assert _jobs(db) == []


def test_enabled_without_an_account_is_not_on(db, due):
    """켜기만 하고 **보내는 계정이 없으면** 켜진 것이 아니다.

    반쯤 켜진 상태를 두면 화면에는 `켜짐` 이라 떠 있고 아무 일도 안 일어난다 —
    조용히 안 도는 것이 제일 나쁘다.
    """
    from app.services import auto_send

    auto_send.save(db, auto_send.KIND_REVIEW, enabled=True, user_id=None,
                   from_hour=10, until_hour=17, max_per_day=10)

    assert auto_send.run_once(db, now=MONDAY_11AM)["skipped"] == "꺼짐"
    assert auto_send.status(db)["on"] is False
    assert _jobs(db) == []


def test_the_thread_does_not_even_start(db, due):
    """실도 뜨지 않는다 — 안 켠 사람의 서버에서 도는 것이 없어야 한다."""
    from app.services import auto_send

    assert auto_send.start_scheduler() is None


def test_a_stopped_account_stops_the_whole_thing(db, due):
    """보내기로 한 계정이 정지되면 **멈춘다.** 남의 계정으로 대신 보내지 않는다."""
    from app.services import auto_send

    _turn_on(db, due["u1"])
    due["u1"].is_active = 0
    db.commit()

    assert auto_send.run_once(db, now=MONDAY_11AM)["skipped"] == "보내는 계정 없음"
    assert _jobs(db) == []


# --- 2. 같은 건은 두 번 안 간다 ----------------------------------------------

def test_the_same_meeting_never_goes_twice(db, due):
    """실이 다시 깨어나도 **한 번 나간 건은 다시 안 나간다.**

    `sms_notices` 는 `(종류, 날, 사람)` 이었지만 여기는 날짜를 열쇠에 넣을 수
    없다 — 결과 문의는 담당자가 결과를 적기 전까지 목록에 남아 있어서, 날짜로
    잡으면 **다음 날 또 나간다.**
    """
    from app.services import auto_send

    _turn_on(db, due["u1"])

    first = auto_send.run_once(db, now=MONDAY_11AM)
    assert first["created"] == 3

    again = auto_send.run_once(db, now=MONDAY_11AM)
    assert again["created"] == 0
    assert again["skipped"] == "세울 것 없음"
    assert len(_jobs(db)) == 1


def test_it_does_not_come_back_the_next_day(db, due):
    """**다음 날에도** 안 나간다 — 결과를 안 적었어도 물어본 것은 한 번이다."""
    from app.services import auto_send

    _turn_on(db, due["u1"])
    auto_send.run_once(db, now=MONDAY_11AM)

    tomorrow = auto_send.run_once(db, now=datetime(2026, 9, 8, 11, 0))

    assert tomorrow["created"] == 0
    assert len(_jobs(db)) == 1


def test_the_mark_is_left_before_sending(db, due, monkeypatch):
    """표시는 **잡을 만들기 전에** 남긴다.

    성공한 뒤에 남기면, 잡은 만들어졌는데 응답만 실패했을 때 30분 뒤에 한 통 더
    나간다. 잡 만들기를 터뜨려 두고 표시가 남았는지 본다 — 남아 있어야 다음
    회차에 같은 건을 다시 집지 않는다.
    """
    from sqlalchemy import select

    from app.models import AutoSendRun
    from app.routers import deals as deals_view
    from app.services import auto_send

    _turn_on(db, due["u1"])

    def boom(*args, **kwargs):
        raise RuntimeError("발송 목록을 못 만들었다")

    monkeypatch.setattr(deals_view, "create_send_list", boom)
    result = auto_send.run_once(db, now=MONDAY_11AM)

    assert result["created"] == 0
    assert _jobs(db) == []
    rows = db.execute(select(AutoSendRun)).scalars().all()
    assert len(rows) == 3
    assert {r.status for r in rows} == {"failed"}
    assert "못 만들었다" in rows[0].error
    # 그리고 **다시 시도하지 않는다** — 사람이 사유를 보고 손으로 보낸다.
    assert auto_send.run_once(db, now=MONDAY_11AM)["skipped"] == "세울 것 없음"


# --- 3. 정해진 한 계정 것으로만 ----------------------------------------------

def test_only_the_chosen_account_sends(db, due):
    """잡은 그 계정 것이고, 담긴 사람도 그 계정 담당뿐이다.

    잡이 그 계정 것이어야 **그 계정의 기기 토큰으로만** 내려간다
    (`routers/agent_api.py: poll` 이 `SendJob.user_id == device.user_id`).
    """
    from app.services import auto_send

    _turn_on(db, due["u1"])
    auto_send.run_once(db, now=MONDAY_11AM)

    job = _jobs(db)[0]
    assert job.user_id == due["u1"].id
    rooms = {item.room_name for item in _items(db, job)}
    assert len(rooms) == 3
    names = {item.recipient_name for item in _items(db, job)}
    assert "라담당" not in names          # u2 담당은 섞이지 않는다


def test_the_other_member_gets_nothing(db, due):
    """다른 팀원 계정으로는 아무 잡도 서지 않는다 — 사용자가 정한 `다른 팀원 x`."""
    from app.services import auto_send

    _turn_on(db, due["u1"])
    auto_send.run_once(db, now=MONDAY_11AM)

    assert {job.user_id for job in _jobs(db)} == {due["u1"].id}


def test_a_contact_without_a_room_is_left_alone(db, users):
    """카톡방 이름이 없는 담당자는 **걸리지 않고, 자리도 안 잡는다.**

    `create_send_list` 는 그런 사람이 섞이면 목록 전체를 거절한다(사람이
    화면에서 빼도록). 자동에는 뺄 사람이 없으니 미리 거른다 — 한 사람 때문에
    그날 자동 발송이 통째로 멈추면 멈춘 것을 아무도 모른다.

    자리를 안 잡으므로 **방 이름을 채우면 다음 회차에 그대로 나간다.**
    """
    from sqlalchemy import select

    from app.models import AutoSendRun
    from app.services import auto_send

    u1 = users["u1"]
    ok = _contact(db, u1, "가담당", "가나벤처스")
    blank = _contact(db, u1, "나담당", "다라벤처스", room="")
    reachable = _meeting(db, u1, ok)
    _meeting(db, u1, blank)
    db.commit()
    _turn_on(db, u1)

    assert auto_send.run_once(db, now=MONDAY_11AM)["created"] == 1
    assert db.execute(select(AutoSendRun.ref_id)).scalars().all() == [
        reachable.id]

    blank.kakao_room_name = "다라벤처스 Deal 공유"
    db.commit()
    assert auto_send.run_once(db, now=datetime(2026, 9, 8, 11, 0))["created"] == 1


def test_a_paused_contact_is_left_alone(db, users):
    """`검토중단` 인 분께는 안 나간다 — 사람이 보내지 말라고 정해 둔 것이다."""
    from app.services import auto_send
    from app.services import sheet_owner

    u1 = users["u1"]
    held = _contact(db, u1, "가담당", "가나벤처스",
                    status=sheet_owner.STATUS_PAUSED)
    _meeting(db, u1, held)
    db.commit()
    _turn_on(db, u1)

    assert auto_send.run_once(db, now=MONDAY_11AM)["skipped"] == "세울 것 없음"
    assert _jobs(db) == []


# --- 4. 때가 안 된 미팅 -------------------------------------------------------

def test_a_meeting_that_is_not_due_is_not_picked(db, users):
    """물어볼 날이 아직 안 왔으면 안 나간다."""
    from app.services import auto_send

    u1 = users["u1"]
    _meeting(db, u1, _contact(db, u1, "가담당", "가나벤처스"), when=FAR_FUTURE)
    db.commit()
    _turn_on(db, u1)

    assert auto_send.run_once(db, now=MONDAY_11AM)["skipped"] == "세울 것 없음"
    assert _jobs(db) == []


def test_a_meeting_already_asked_about_is_not_picked(db, users):
    """이미 물어본 미팅은 안 나간다 — 판단은 `pipeline` 것 그대로다."""
    from app.services import auto_send

    u1 = users["u1"]
    meeting = _meeting(db, u1, _contact(db, u1, "가담당", "가나벤처스"))
    meeting.followup_done = 1
    db.commit()
    _turn_on(db, u1)

    assert auto_send.run_once(db, now=MONDAY_11AM)["skipped"] == "세울 것 없음"


# --- 5. 밤·주말에는 안 나간다 -------------------------------------------------

def test_it_does_not_go_out_at_dawn(db, due):
    """이른 아침에는 안 나간다. 받는 쪽이 **투자사**다."""
    from app.services import auto_send

    _turn_on(db, due["u1"])

    assert auto_send.run_once(db, now=MONDAY_7AM)["skipped"] == "목록을 세우는 시간대가 아님"
    assert _jobs(db) == []


def test_it_does_not_go_out_at_night(db, due):
    """밤에도 안 나간다."""
    from app.services import auto_send

    _turn_on(db, due["u1"])

    assert auto_send.run_once(db, now=MONDAY_9PM)["skipped"] == "목록을 세우는 시간대가 아님"


def test_it_does_not_go_out_on_the_weekend(db, due):
    """토요일에는 안 나간다. 월요일에 그대로 나간다 — 결과 문의는 사라지지 않는다."""
    from app.services import auto_send

    _turn_on(db, due["u1"])

    assert auto_send.run_once(db, now=SATURDAY_11AM)["skipped"] == "목록을 세우는 시간대가 아님"
    assert _jobs(db) == []
    assert auto_send.run_once(db, now=datetime(2026, 9, 14, 11, 0))["created"] == 3


def test_the_window_cannot_be_set_to_dawn(db, users):
    """**새벽 시각은 저장되지 않는다.** 고르개가 아니라 코드가 막는다.

    화면만 좁혀 두면 주소로 폼을 흉내 내는 한 번이 새벽 3시에 투자사 카톡방을
    연다.
    """
    from app.services import auto_send

    setting = _turn_on(db, users["u1"], from_hour=3, until_hour=23)

    assert setting.from_hour == auto_send.EARLIEST_HOUR
    assert setting.until_hour == auto_send.LATEST_HOUR


def test_a_backwards_window_becomes_an_hour(db, users):
    """뒤집힌 창(마감이 시작보다 이르다)은 **한 시간짜리**가 된다.

    그대로 두면 `within_window` 가 늘 거짓이라 켜 두고도 영영 안 나간다.
    """
    from app.services import auto_send

    setting = _turn_on(db, users["u1"], from_hour=16, until_hour=10)

    assert (setting.from_hour, setting.until_hour) == (16, 17)
    assert auto_send.within_window(setting, datetime(2026, 9, 7, 16, 30))
    assert not auto_send.within_window(setting, MONDAY_11AM)


# --- 6. 하루 상한 -------------------------------------------------------------

def test_the_daily_cap_holds(db, due):
    """상한이 2건이면 그날은 2건까지. **회당이 아니라 하루다.**

    실은 30분마다 깨어난다 — 회당 상한만 두면 하루에 그 열 배가 나간다.
    """
    from app.services import auto_send

    _turn_on(db, due["u1"], max_per_day=2)

    assert auto_send.run_once(db, now=MONDAY_11AM)["created"] == 2
    assert auto_send.run_once(db, now=MONDAY_11AM)["skipped"] == "오늘 상한"
    assert len(_items(db, _jobs(db)[0])) == 2

    # 남은 것은 **다음 영업일**에 이어 나간다.
    assert auto_send.run_once(db, now=datetime(2026, 9, 8, 11, 0))["created"] == 1


def test_the_cap_cannot_exceed_the_documented_limit(db, users):
    """이 도구가 지켜 온 **1회 발송 상한 60건**을 넘길 수 없다.

    목록을 그보다 크게 세우면, 사람이 눌러도 발송기가 앞의 60건만 처리하고
    나머지는 대기로 남는다.
    """
    from app.services import auto_send

    assert _turn_on(db, users["u1"], max_per_day=500).max_per_day == \
        auto_send.HARD_MAX_PER_DAY
    assert _turn_on(db, users["u1"], max_per_day=0).max_per_day == 1


# --- 7. 목록은 남고, 사람이 본다 ---------------------------------------------

def test_the_list_stays_in_the_send_history(db, due):
    """평범한 발송 회차라 `/jobs` 와 `최근 발송 회차` 에 그대로 남는다.

    회차명은 화면이 만드는 것과 **같은 자리**에서 나오고(`cadence`), 거기에
    `자동` 이 붙어 사람이 손으로 만든 회차와 갈린다.
    """
    from app.models import DealBatch, SendJob
    from app.services import auto_send

    _turn_on(db, due["u1"])
    result = auto_send.run_once(db, now=MONDAY_11AM)

    job = db.get(SendJob, result["job_id"])
    assert job.kind == "deal_intro"
    batch = db.get(DealBatch, job.batch_id)
    assert "미팅 후기 자동" in batch.title


def test_the_team_screen_shows_the_list_waiting_to_be_sent(db, due):
    """팀 현황이 **아직 아무도 안 누른 목록**을 회차 번호와 함께 보여 준다.

    세워 두고 아무도 안 누르면 결과 문의가 그대로 밀리는데, 저절로 서는 것이라
    밀리는 줄도 모른다.
    """
    from app.services import auto_send

    _turn_on(db, due["u1"])
    result = auto_send.run_once(db, now=MONDAY_11AM)
    state = auto_send.status(db, today=MONDAY_11AM.date())

    assert state["waiting"] == [{"job_id": result["job_id"], "count": 3}]
    rows = state["today"]
    assert len(rows) == 3
    assert {r["status"] for r in rows} == {"ready"}
    assert {r["job_id"] for r in rows} == {result["job_id"]}
    assert "가담당(가나벤처스)" in {r["name"] for r in rows}


def test_the_sender_sees_it_in_their_today_list(db, due):
    """그 계정의 **오늘 할 일**에 뜬다 — 누르라고 알려 주는 자리다.

    남의 할 일에는 안 뜬다. 누를 수 있는 사람은 그 회차 주인뿐이다.
    """
    from app.services import auto_send, today as today_svc

    _turn_on(db, due["u1"])
    result = auto_send.run_once(db, now=MONDAY_11AM)

    mine = today_svc.build(db, due["u1"])["items"]
    waiting = [i for i in mine if i["href"] == f"/jobs/{result['job_id']}"]
    assert len(waiting) == 1
    assert waiting[0]["count"] == 3

    other = today_svc.build(db, due["u2"])["items"]
    assert not [i for i in other if i["href"].startswith("/jobs/")]


def test_the_waiting_list_disappears_once_it_is_started(db, due, client):
    """누르고 나면 대기 목록에서 사라진다 — 그다음은 진행 화면이 말한다."""
    from app.services import auto_send

    _turn_on(db, due["u1"])
    result = auto_send.run_once(db, now=MONDAY_11AM)
    _press_send(client, db, result["job_id"])

    assert auto_send.status(db, today=MONDAY_11AM.date())["waiting"] == []
    assert auto_send.waiting_for(db, due["u1"]) == []


# --- 8. 문구는 화면 것과 같다 -------------------------------------------------

def test_the_message_is_the_one_the_screen_makes(db, users):
    """자동으로 나가는 글이 **발송 화면의 미팅 후기 탭과 글자 하나까지 같다.**

    조립 규칙을 자동 발송 쪽에 다시 적으면 두 벌이 되고, 두 벌은 반드시
    어긋난다 — 화면에서 확인한 글과 다른 글이 투자사에게 간다.
    """
    from app.routers import deals as deals_view
    from app.services import auto_send

    u1 = users["u1"]
    contact = _contact(db, u1, "가담당", "가나벤처스")
    _meeting(db, u1, contact)
    db.commit()
    _turn_on(db, u1)

    auto_send.run_once(db, now=MONDAY_11AM)

    item = _items(db, _jobs(db)[0])[0]
    assert item.message == deals_view.review_message(db, u1, contact)


def test_the_test_room_still_wins(db, users, monkeypatch):
    """시험방이 설정돼 있으면 **거기로만** 간다 — 지금 발송이 그렇다.

    `create_send_list` 를 그대로 지나므로 이 판단이 두 벌이 되지 않는다.
    """
    from app import config
    from app.services import auto_send

    monkeypatch.setattr(config, "TEST_ROOM", "테스트방")

    u1 = users["u1"]
    _meeting(db, u1, _contact(db, u1, "가담당", "가나벤처스"))
    db.commit()
    _turn_on(db, u1)

    auto_send.run_once(db, now=MONDAY_11AM)

    item = _items(db, _jobs(db)[0])[0]
    assert item.room_name == "테스트방"


# --- 9. 설정 화면 -------------------------------------------------------------

def test_the_settings_live_on_the_team_page(client, db, users):
    """설정 칸은 **팀 현황**에 있다 — 관리자만 들어오는 화면이다.

    `/setup` 은 본인이 자기 PC 를 손보는 화면이라 거기 두면 누구든 스스로 켤 수
    있다(자료 자동 첨부가 그 이유로 이미 이 화면으로 옮겨 왔다).
    """
    users["u1"].role = "admin"
    db.commit()
    client.post("/login", data={"phone": "01000000001",
                                "password": DEMO_PASSWORD})

    page = client.get("/team").text

    assert "미팅 후기 발송 준비" in page
    assert 'action="/team/auto-send"' in page


def test_only_an_admin_can_turn_it_on(client, db, users):
    """관리자가 아니면 켤 수 없다. **새 규칙을 만들지 않았다** — 옆칸 둘과 같은 문."""
    from app.services import auto_send

    client.post("/login", data={"phone": "01000000001",
                                "password": DEMO_PASSWORD})

    answer = client.post("/team/auto-send",
                         data={"kind": auto_send.KIND_REVIEW, "enabled": "on",
                               "user_id": users["u1"].id, "from_hour": 10,
                               "until_hour": 17, "max_per_day": 10},
                         follow_redirects=False)

    assert answer.status_code in (303, 403)
    assert auto_send.load(db, auto_send.KIND_REVIEW) is None


def test_turning_it_on_and_off_from_the_screen(client, db, users):
    """화면에서 켜고 **한 번에 끈다.** 끄는 길이 분명해야 한다."""
    from app.services import auto_send

    users["u1"].role = "admin"
    db.commit()
    client.post("/login", data={"phone": "01000000001",
                                "password": DEMO_PASSWORD})
    form = {"kind": auto_send.KIND_REVIEW, "user_id": users["u1"].id,
            "from_hour": 10, "until_hour": 17, "max_per_day": 5}

    client.post("/team/auto-send", data={**form, "enabled": "on"},
                follow_redirects=False)
    db.expire_all()
    assert auto_send.status(db)["on"] is True

    client.post("/team/auto-send", data={**form, "enabled": ""},
                follow_redirects=False)
    db.expire_all()
    assert auto_send.status(db)["on"] is False


def test_it_will_not_turn_on_without_an_account(client, db, users):
    """보내는 계정을 안 고르면 켜지지 않는다."""
    from app.services import auto_send

    users["u1"].role = "admin"
    db.commit()
    client.post("/login", data={"phone": "01000000001",
                                "password": DEMO_PASSWORD})

    client.post("/team/auto-send",
                data={"kind": auto_send.KIND_REVIEW, "enabled": "on",
                      "user_id": 0, "from_hour": 10, "until_hour": 17,
                      "max_per_day": 10}, follow_redirects=False)
    db.expire_all()

    assert auto_send.status(db)["on"] is False
