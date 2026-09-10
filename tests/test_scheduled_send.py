"""예약 발송 — **정한 시각에 나간다. 그 전에도, 한참 뒤에도 나가지 않는다.**

## 왜 이 검사가 있나

딜 소개는 한 회차가 55~114명이고, 나간 뒤에는 되돌릴 수 없다. 예약이 붙으면
사람이 화면을 보고 있지 않은 순간에 그 일이 일어난다 — 그래서 **언제 나가고
언제 안 나가는가**가 이 기능의 전부다. 여기서 못박는 것은 여섯 가지다.

1. **정한 시각 전에는 발송기가 집어갈 것이 없다.** 회차는 `draft` 로 서 있고,
   발송기는 `queued` 만 집어간다(`routers/agent_api.py: poll`).
2. **시각이 되면 나간다** — 사람이 [발송 시작] 을 누른 것과 **같은 길**로
   (`routers/jobs.py: _requeue`).
3. **지나 버린 예약은 저절로 안 나간다.** 서버가 멈춰 있었거나 한참 뒤에
   깨어난 경우다. 몇 시간 늦게 조용히 나가면 받는 쪽에는 한밤중에 오는 것으로
   보인다. 화면이 `예약 시각이 지났습니다` 라고 말하고, 사람이 누르면 그때 나간다.
4. **09~19시 밖은 서버가 거절한다.** 화면 고르개만 좁혀 두면 주소로 폼을
   흉내 내는 순간 뚫린다.
5. **아직 안 나간 것은 취소하거나 시각을 바꿀 수 있고, 나간 것에는 안 된다.**
6. **두 번 풀리지 않는다.** 두 번 풀리면 같은 사람에게 두 번 나간다.

그리고 **몇 명에게 언제 가는지가 사람 눈에 보이는가** — 예약해 놓고 잊는 것이
이 기능에서 가장 흔한 사고다.

## 시계에 기대지 않는다  ★

시각은 전부 `now=` 로 못박는다. 실제 시계로 재면 **밤에만 깨지는 검사**가 된다.
예약 시각도 실제 오늘과 아무 관계 없는 먼 뒷날로 둔다 — 검사를 돌리는 날이
언제든 그 시각이 '지금' 이 되는 일이 없게.

## 진짜로는 한 통도 안 나간다

여기서 만드는 것은 발송 **목록**까지다. 실제로 카톡을 보내는 것은 각 PC 의
발송 프로그램이고, 검사는 그것을 띄우지 않는다.
"""
from __future__ import annotations

from datetime import datetime

import pytest

from .conftest import DEMO_PASSWORD, DEMO_TOKEN

#: 2099-03-12 는 **목요일**이다. 실제 오늘이 언제든 이 시각이 '지금' 일 수 없다.
AT = "2099-03-12T14:00"
BEFORE = datetime(2099, 3, 12, 13, 59)
ON_TIME = datetime(2099, 3, 12, 14, 0)
#: 정한 시각으로부터 90분 — `EXPIRE_MINUTES`(60) 를 넘겼다.
LONG_AFTER = datetime(2099, 3, 12, 15, 30)

#: 고를 수 없는 시각들. 밤 9시는 퇴근한 사람의 폰이고, 아침 8시는 출근 전이다.
TOO_LATE = "2099-03-12T21:00"
TOO_EARLY = "2099-03-12T08:00"
#: 이미 지난 날. 예약으로 걸 수 없다 — 지금 보내려면 [발송 시작] 이다.
GONE_BY = "2020-01-06T10:00"


@pytest.fixture()
def seed(client, db, users):
    """u1 로 로그인 + 소개 가능한 기업 1개 + 카톡방이 등록된 담당자 2명.

    두 명인 것은 일부러다 — **몇 명에게 가는지**를 화면이 말하는지 보려면
    한 명으로는 1 과 다른 수를 구분할 수 없다.
    """
    from app.models import IrCompany, VcContact

    company = IrCompany(
        name="샘플애그", sector_major="애그테크", series="Seed",
        one_liner="B2B 농산물 선도거래 플랫폼", summary="요약문",
        summary_status="done", revenue_recent=12,
    )
    people = [
        VcContact(user_id=users["u1"].id, name="가담당", title="심사역",
                  firm="가나벤처스", kakao_room_name="가담당 심사역님 가나벤처스",
                  room_verified="verified"),
        VcContact(user_id=users["u1"].id, name="나담당", title="팀장",
                  firm="다라벤처스", kakao_room_name="나담당 팀장님 다라벤처스",
                  room_verified="verified"),
    ]
    db.add(company)
    db.add_all(people)
    db.commit()
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    return {"company_id": company.id,
            "contact_ids": [c.id for c in people],
            "user": users["u1"]}


# --- 화면이 부르는 것과 같은 주소들 --------------------------------------------

def _book(client, seed, at=AT, **over):
    """발송 화면에서 **시각을 골라** 목록을 만든다(`static/js/deals.js: send`)."""
    body = {"company_ids": [seed["company_id"]],
            "contact_ids": seed["contact_ids"],
            "title": "예약 회차", "scheduled_at": at}
    body.update(over)
    return client.post("/api/deals/send", json=body)


def _job(db, job_id):
    from app.models import SendJob

    db.expire_all()
    return db.get(SendJob, job_id)


def _claim_by_agent(client, token=DEMO_TOKEN):
    """발송 프로그램이 지금 집어갈 것이 있는지 물어본다. 없으면 204 다.

    실제 폴링과 같은 주소·같은 값이다(`agent/main.py`).
    """
    return client.get("/api/agent/poll",
                      params={"kinds": "deal_intro,ir_delivery,sourcing_intro"},
                      headers={"Authorization": f"Bearer {token}"})


def _tick(db, now):
    """예약을 살피는 실이 깰 때 하는 일 그대로(`services/scheduled_send.py`)."""
    from app.services import scheduled_send

    result = scheduled_send.run_once(db, now=now)
    db.expire_all()
    return result


# --- 1. 시각 전에는 아무것도 못 가져간다  ★ ------------------------------------

def test_nothing_is_picked_up_before_the_hour(client, db, seed):
    """예약을 걸어 두면 회차는 `draft` 로 서고, **발송기는 줄 것이 없다.**

    이 검사가 이 기능의 알맹이다. `queued` 로 만들어 두고 폴링 쪽에서 시각을
    보고 거르는 길을 골랐다면, 거르는 자리가 한 군데만 새도 55명에게 한꺼번에
    나간다.
    """
    made = _book(client, seed)
    assert made.status_code == 200, made.text
    job = _job(db, made.json()["job_id"])

    assert job.status == "draft"
    assert job.scheduled_at.startswith("2099-03-12T14:00")
    assert _claim_by_agent(client).status_code == 204
    assert {i.status for i in job.items} == {"pending"}

    # 1분 전에 실이 깨어나도 마찬가지다.
    assert _tick(db, BEFORE)["count"] == 0
    assert _job(db, job.id).status == "draft"
    assert _claim_by_agent(client).status_code == 204


# --- 2. 시각이 되면 나간다 -----------------------------------------------------

def test_it_goes_out_when_the_hour_comes(client, db, seed):
    """정한 시각이 되면 `queued` 가 되고, 발송기가 그때 집어간다.

    푸는 길은 [발송 시작] 과 **같다**(`jobs._requeue`) — 두 벌로 두면 한쪽만
    고쳐져 카톡은 나가는데 메일은 안 나가는 식이 된다.
    """
    job_id = _book(client, seed).json()["job_id"]

    assert _tick(db, ON_TIME) == {"released": [job_id], "count": 1}
    assert _job(db, job_id).status == "queued"

    claimed = _claim_by_agent(client)
    assert claimed.status_code == 200
    assert claimed.json()["job_id"] == job_id
    assert len(claimed.json()["items"]) == 2


# --- 3. 지나 버린 예약은 저절로 안 나간다  ★ -----------------------------------

def test_a_missed_hour_never_goes_out_on_its_own(client, db, seed):
    """한참 뒤에 깨어나면 **보내지 않는다.**

    몇 시간 늦게 조용히 나가는 것이 더 위험하다 — 받는 쪽에서는 한밤중에 오는
    것으로 보인다. 서 있는 채로 두고, 화면이 그렇게 말한다.
    """
    from app.services import scheduled_send

    job_id = _book(client, seed).json()["job_id"]

    assert _tick(db, LONG_AFTER)["count"] == 0
    job = _job(db, job_id)
    assert job.status == "draft"
    assert job.released_at is None
    assert _claim_by_agent(client).status_code == 204

    assert scheduled_send.state(job, LONG_AFTER) == scheduled_send.STATE_EXPIRED
    said = scheduled_send.sentence(job, LONG_AFTER)
    assert "예약 시각이 지났습니다" in said and "2명에게" in said


def test_a_missed_booking_still_goes_out_if_a_person_presses(client, db, seed):
    """지나 버린 예약도 **사람이 누르면 그때 나간다.** 회차는 그대로 남아 있다."""
    job_id = _book(client, seed).json()["job_id"]
    _tick(db, LONG_AFTER)

    assert client.post(f"/api/jobs/{job_id}/start").status_code == 200
    assert _job(db, job_id).status == "queued"
    assert _claim_by_agent(client).json()["job_id"] == job_id


# --- 4. 09~19 밖은 **서버가** 거절한다 -----------------------------------------

@pytest.mark.parametrize("at", [TOO_LATE, TOO_EARLY, GONE_BY])
def test_the_server_refuses_hours_outside_the_window(client, db, seed, at):
    """화면을 거치지 않고 들어와도 막힌다. **회차도 만들지 않는다.**

    만들어 놓고 거절하면 아무도 안 볼 `draft` 회차가 쌓인다 — 그리고 그중
    하나를 누가 눌러 보는 날 그것이 사고다.
    """
    from app.models import SendJob
    from sqlalchemy import select

    answer = _book(client, seed, at=at)
    assert answer.status_code == 400, answer.text
    assert db.execute(select(SendJob)).scalars().all() == []


@pytest.mark.parametrize("at", [TOO_LATE, TOO_EARLY, GONE_BY])
def test_the_server_refuses_the_same_hours_on_a_standing_job(client, db, seed, at):
    """이미 서 있는 회차에 시각을 다는 자리도 같은 잣대다.

    거는 자리가 둘이므로(발송 화면 · 진행 화면) **둘 다** 본다 — 한쪽만 막으면
    그쪽이 뚫린 채로 남는다.
    """
    job_id = _book(client, seed, at=AT).json()["job_id"]
    answer = client.post(f"/api/jobs/{job_id}/schedule", json={"at": at})

    assert answer.status_code == 400, answer.text
    # 원래 걸려 있던 예약이 망가지지 않는다.
    assert _job(db, job_id).scheduled_at.startswith("2099-03-12T14:00")


# --- 5. 취소 · 시각 변경 -------------------------------------------------------

def test_you_can_move_a_booking_that_has_not_gone_out(client, db, seed):
    """시각을 바꾼다. 바꾼 시각에 나간다."""
    job_id = _book(client, seed).json()["job_id"]

    moved = client.post(f"/api/jobs/{job_id}/schedule",
                        json={"at": "2099-03-12T16:30"})
    assert moved.status_code == 200, moved.text
    assert moved.json()["state"] == "waiting"

    # 옛 시각에는 안 나간다.
    assert _tick(db, ON_TIME)["count"] == 0
    assert _job(db, job_id).status == "draft"
    # 새 시각에 나간다.
    assert _tick(db, datetime(2099, 3, 12, 16, 30))["count"] == 1
    assert _job(db, job_id).status == "queued"


def test_you_can_drop_a_booking_and_the_list_stays(client, db, seed):
    """예약을 취소해도 **회차는 남는다.**

    시각만 잘못 고른 것일 수 있다. 그때 회차까지 사라지면 대상을 처음부터 다시
    골라야 하고, 손으로 맞추다 한 명이라도 틀리면 그것이 곧 사고다.
    """
    job_id = _book(client, seed).json()["job_id"]

    dropped = client.delete(f"/api/jobs/{job_id}/schedule")
    assert dropped.status_code == 200, dropped.text
    assert dropped.json()["state"] == "none"

    job = _job(db, job_id)
    assert job.scheduled_at is None
    assert job.status == "draft"
    assert len(job.items) == 2
    # 시각이 되어도 나가지 않는다 — 뗀 예약이다.
    assert _tick(db, ON_TIME)["count"] == 0
    assert _claim_by_agent(client).status_code == 204
    # 사람이 누르면 그때 나간다.
    assert client.post(f"/api/jobs/{job_id}/start").status_code == 200


def test_a_job_that_already_went_out_takes_no_booking(client, db, seed):
    """이미 나간 회차에는 걸지도 떼지도 못한다 — 그쪽은 [중단] 이 맡는다.

    나간 회차에 시각을 달 수 있으면 화면이 "아직 안 나갔다" 고 거짓말을 한다.
    """
    job_id = _book(client, seed).json()["job_id"]
    _tick(db, ON_TIME)

    assert client.post(f"/api/jobs/{job_id}/schedule",
                       json={"at": "2099-03-12T16:00"}).status_code == 400
    assert client.delete(f"/api/jobs/{job_id}/schedule").status_code == 400


def test_only_the_owner_can_book(client, db, seed, users):
    """남의 회차에는 손대지 못한다 — 조작은 주인만(`jobs._job_or_404`)."""
    job_id = _book(client, seed).json()["job_id"]

    client.post("/login", data={"phone": "01000000002", "password": DEMO_PASSWORD})
    assert client.post(f"/api/jobs/{job_id}/schedule",
                       json={"at": "2099-03-12T16:00"}).status_code == 404
    assert client.delete(f"/api/jobs/{job_id}/schedule").status_code == 404


# --- 6. 두 번 풀리지 않는다  ★ -------------------------------------------------

def test_a_booking_is_never_released_twice(client, db, seed):
    """같은 예약이 두 번 풀리면 **같은 사람에게 두 번 나간다.**

    실이 두 번 깨어나도, 웹 프로세스가 여럿이어도 한 번만 풀려야 한다. 자리를
    잡는 방식은 발송기의 선점과 같다(`agent_api.poll` 의 원자적 UPDATE).
    """
    from app.services import scheduled_send

    job_id = _book(client, seed).json()["job_id"]

    assert _tick(db, ON_TIME)["count"] == 1
    assert _tick(db, ON_TIME)["count"] == 0
    assert _tick(db, datetime(2099, 3, 12, 14, 30))["count"] == 0

    # 자물쇠가 **상태와 따로** 걸려 있는지까지 본다. 회차가 어떤 까닭으로든
    # 다시 `draft` 로 돌아가도(사람이 되살리는 길들이 있다) 그 예약은 이미
    # 풀린 것이라 다시 풀리면 안 된다.
    job = _job(db, job_id)
    assert job.released_at
    job.status = "draft"
    db.commit()
    assert scheduled_send.release(db, job, ON_TIME) is False
    assert _tick(db, ON_TIME)["count"] == 0


def test_pressing_start_closes_the_booking(client, db, seed):
    """사람이 먼저 눌렀으면 그 예약은 거기서 끝난다 — 나중에 또 풀리지 않는다."""
    from app.services import scheduled_send

    job_id = _book(client, seed).json()["job_id"]
    assert client.post(f"/api/jobs/{job_id}/start").status_code == 200

    job = _job(db, job_id)
    assert job.status == "queued"
    assert job.released_at
    assert _tick(db, ON_TIME)["count"] == 0
    assert scheduled_send.state(job, ON_TIME) == scheduled_send.STATE_RELEASED


# --- 예약해 둔 것이 **사람 눈에 보인다** ---------------------------------------

def test_the_progress_screen_says_when_and_to_how_many(client, db, seed):
    """진행 화면이 `3/12(목) 14:00 에 2명에게 나갑니다` 라고 말한다.

    화면이 판정하거나 문장을 짓지 않는다 — 서버가 만든 것을 그대로 적는다
    (`static/js/progress.js: renderSchedule`). 두 곳에서 지으면 어긋난다.
    """
    job_id = _book(client, seed).json()["job_id"]

    shown = client.get(f"/api/jobs/{job_id}").json()
    booked = shown["scheduled"]
    assert booked["state"] == "waiting"
    assert booked["count"] == 2
    assert booked["label"] == "3/12(목) 14:00"
    assert booked["sentence"] == "3/12(목) 14:00 에 2명에게 나갑니다"
    # 화면의 시각 칸에 도로 채워 넣을 값, 그리고 고를 수 있는 폭.
    assert booked["input"] == "2099-03-12T14:00"
    assert (booked["earliest"], booked["latest"]) == (9, 19)


def test_the_booking_shows_up_in_todays_work(client, db, seed):
    """**오늘 할 일에도 선다.** 예약해 놓고 잊는 것이 가장 흔한 사고다.

    회차 화면은 그 주소를 아는 사람만 다시 열어 보고, 예약은 걸어 두면 화면을
    닫는다. 아침에 여는 화면에 서 있어야 그것을 기억한다.
    """
    from app.services import today as today_svc

    job_id = _book(client, seed).json()["job_id"]

    rows = [t for t in today_svc.build(db, seed["user"])["items"]
            if t["href"] == f"/jobs/{job_id}"]
    assert len(rows) == 1
    assert rows[0]["title"] == "예약해 둔 발송"
    assert rows[0]["detail"] == "3/12(목) 14:00 에 2명에게 나갑니다"
    assert rows[0]["count"] == 2


def test_a_missed_booking_is_urgent_in_todays_work(client, db, seed):
    """지나 버린 예약은 **급한 일**로 선다 — 사람이 정해 줘야 나간다."""
    from app.services import scheduled_send

    job_id = _book(client, seed).json()["job_id"]
    rows = scheduled_send.standing_for(db, seed["user"], LONG_AFTER)

    assert [r["job_id"] for r in rows] == [job_id]
    assert rows[0]["level"] == "urgent"
    assert rows[0]["state"] == "expired"


def test_a_released_booking_leaves_todays_work(client, db, seed):
    """나간 것은 할 일이 아니다 — 목록에서 빠진다."""
    from app.services import scheduled_send

    _book(client, seed)
    _tick(db, ON_TIME)

    assert scheduled_send.standing_for(db, seed["user"], ON_TIME) == []


# --- 서 있는 것과 막힌 것 -------------------------------------------------------

def test_the_screen_can_tell_a_standing_job_from_a_stuck_one(client, db, seed):
    """발송기가 안 붙어 있으면 잡은 **막힌 것이 아니라 서 있는 것**이다.

    그 둘을 구분하지 못하면 사람이 [중단] 을 누르거나 회차를 다시 만든다 —
    다시 만들면 이미 받은 사람을 손으로 골라내야 한다.

    회차 **주인의** 기기를 본다. 관리자가 남의 회차를 열어 봐도 실제로 그 잡을
    집어갈 기기는 주인 것이다.
    """
    job_id = _book(client, seed).json()["job_id"]
    _tick(db, ON_TIME)

    shown = client.get(f"/api/jobs/{job_id}").json()
    assert shown["status"] == "queued"
    assert shown["agent"]["online"] is False

    # 발송기가 한 번 물어보고 나면 붙어 있는 것으로 보인다.
    _claim_by_agent(client)
    assert client.get(f"/api/jobs/{job_id}").json()["agent"]["online"] is True


# --- 예약을 안 걸면 지금까지와 똑같다 -------------------------------------------

def test_without_a_time_nothing_changes(client, db, seed):
    """시각을 안 고르면 **만드는 즉시 나간다** — 지금까지 그대로다."""
    made = _book(client, seed, at="")
    assert made.status_code == 200, made.text

    job = _job(db, made.json()["job_id"])
    assert job.status == "queued"
    assert job.scheduled_at is None
    assert made.json()["scheduled"]["state"] == "none"
    assert _claim_by_agent(client).json()["job_id"] == job.id


# --- 시각을 재는 규칙 자체 ------------------------------------------------------

def test_the_deadline_never_leaves_the_window():
    """포기하는 시각이 **고를 수도 없던 시간대로 넘어가지 않는다.**

    18:40 예약이 19:40 에 풀리면 막아 둔 창을 뒷문으로 넘는 셈이다.
    """
    from app.services import scheduled_send

    late = datetime(2099, 3, 12, 18, 40).astimezone()
    assert scheduled_send.deadline(late).hour == 19
    assert scheduled_send.deadline(late).minute == 0

    early = datetime(2099, 3, 12, 10, 0).astimezone()
    assert scheduled_send.deadline(early) - early == \
        __import__("datetime").timedelta(minutes=scheduled_send.EXPIRE_MINUTES)


def test_the_window_is_the_one_auto_send_already_decided():
    """09~19시는 **한 곳에서만** 정한다 — 같은 판단을 두 번 적지 않는다."""
    from app.services import auto_send, scheduled_send

    assert scheduled_send.EARLIEST_HOUR is auto_send.EARLIEST_HOUR
    assert scheduled_send.LATEST_HOUR is auto_send.LATEST_HOUR
