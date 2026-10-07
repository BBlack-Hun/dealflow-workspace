"""스타트업 월간 발송 — **보낼 시각을 골라 둘 수 있다.**

딜 제안 발송이 쓰는 **그 예약**(`services/scheduled_send.py`)을 그대로 탄다.
예약을 한 벌 더 만들지 않았다는 것, 그리고 스타트업 쪽에만 있는 규칙
(**정해진 한 계정만**)이 예약을 지나서도 지켜진다는 것을 여기서 못박는다.

1. 시각 전에는 발송기가 집어갈 것이 없고, 시각이 되면 나간다.
2. 09~19시 밖은 서버가 거절하고, 회차도 서지 않는다.
3. 시각이 되기 전에 보내는 계정이 바뀌면 **풀리지 않는다** — 예약이 막힌
   계정의 뒷문이 되면 안 된다.
4. 화면이 `N곳에` 로 센다 — 받는 쪽은 사람이 아니라 기업 대표방이다.

이름·회사명은 전부 지어낸 값이다. 예약 시각은 2099년이라 검사를 돌리는 날이
언제든 '지금' 이 되지 않는다.
"""
from __future__ import annotations

from datetime import datetime

from tests.conftest import DEMO_TOKEN
from tests.test_startup_monthly_send import (  # noqa: F401 - 픽스처를 함께 쓴다
    _jobs, _login, _poll, _turn_on, seeded)

#: 2099-03-12 는 목요일이다.
AT = "2099-03-12T14:00"
BEFORE = datetime(2099, 3, 12, 13, 59)
ON_TIME = datetime(2099, 3, 12, 14, 0)


def _make(client, seeded, at=AT):
    """화면의 폼 그대로 — 보낼 시각을 함께 고른다."""
    return client.post("/deals/startup-ir/send", follow_redirects=False, data={
        "month": seeded["month"],
        "company_ids": [seeded["ok"].id],
        "title": "검사 회차",
        "scheduled_at": at,
    })


def _tick(db, now):
    from app.services import scheduled_send

    result = scheduled_send.run_once(db, now=now)
    db.expire_all()
    return result


def test_화면에_보낼_시각_칸이_있다(db, seeded, client):
    _turn_on(db, user_id=1)
    page = _login(client).get("/deals/startup-ir").text

    assert 'data-testid="startup-send-schedule"' in page
    assert 'type="datetime-local" name="scheduled_at"' in page
    assert "09:00~19:00" in page


def test_시각_전에는_안_나가고_시각이_되면_나간다(db, seeded, client):
    _turn_on(db, user_id=1)
    made = _make(_login(client), seeded)

    assert made.status_code == 303
    job = _jobs(db)[0]
    assert made.headers["location"] == f"/jobs/{job.id}"
    assert job.status == "draft"
    assert job.scheduled_at.startswith("2099-03-12T14:00")

    assert _poll(client).status_code == 204
    assert _tick(db, BEFORE)["count"] == 0
    assert _poll(client).status_code == 204

    assert _tick(db, ON_TIME) == {"released": [job.id], "count": 1}
    claimed = _poll(client)
    assert claimed.status_code == 200
    assert claimed.json()["job_id"] == job.id
    assert claimed.json()["kind"] == "startup_ir"


def test_시각을_안_고르면_지금까지와_같다(db, seeded, client):
    _turn_on(db, user_id=1)
    _make(_login(client), seeded, at="")
    job = _jobs(db)[0]

    assert job.status == "draft"
    assert job.scheduled_at is None
    assert _tick(db, ON_TIME)["count"] == 0
    assert _poll(client).status_code == 204


def test_업무시간_밖은_거절하고_회차도_안_선다(db, seeded, client):
    _turn_on(db, user_id=1)
    made = _make(_login(client), seeded, at="2099-03-12T21:00")

    assert made.status_code == 303
    assert made.headers["location"].startswith("/deals/startup-ir?")
    assert _jobs(db) == []


def test_수를_곳으로_센다(db, users, seeded, client):
    from app.services import scheduled_send

    _turn_on(db, user_id=1)
    _make(_login(client), seeded)
    job = _jobs(db)[0]

    said = scheduled_send.sentence(job, BEFORE)
    assert said == "3/12(목) 14:00 에 1곳에 나갑니다"
    shown = client.get(f"/api/jobs/{job.id}").json()["scheduled"]
    assert shown["unit"] == "곳"
    assert shown["sentence"] == said

    # 오늘 할 일도 같은 문장을 읽는다(`today.build` → `standing_for`).
    standing = scheduled_send.standing_for(db, users["u1"], BEFORE)
    assert [b["sentence"] for b in standing] == [said]


def test_진행_화면에서도_걸_수_있다(db, seeded, client):
    """시각을 안 고르고 세운 회차도 진행 화면의 [예약] 으로 건다 — 같은 주소다."""
    _turn_on(db, user_id=1)
    _make(_login(client), seeded, at="")
    job = _jobs(db)[0]

    page = client.get(f"/jobs/{job.id}").text
    assert 'id="schedule-box"' in page

    booked = client.post(f"/api/jobs/{job.id}/schedule", json={"at": AT})
    assert booked.status_code == 200, booked.text
    assert booked.json()["state"] == "waiting"
    db.expire_all()  # 걸어 둔 것은 다른 세션(요청)이 적었다
    assert _tick(db, ON_TIME)["count"] == 1


def test_계정이_바뀌면_예약이_풀리지_않는다(db, seeded, client):
    """걸 때는 그 계정이었어도, **푸는 순간에 다시 본다.**"""
    _turn_on(db, user_id=1)
    _make(_login(client), seeded)
    job = _jobs(db)[0]

    _turn_on(db, user_id=2)

    assert _tick(db, ON_TIME)["count"] == 0
    db.expire_all()
    assert _jobs(db)[0].status == "draft"
    assert _jobs(db)[0].released_at is None
    assert _poll(client, token=DEMO_TOKEN).status_code == 204

    # 사람이 직접 누르거나 다시 걸어도 같다 — 없는 자리다.
    assert client.post(f"/api/jobs/{job.id}/start").status_code == 404
    assert client.post(f"/api/jobs/{job.id}/schedule",
                       json={"at": AT}).status_code == 404
