"""한 발송기로 두 계정 보내기 — `users.send_via_user_id`.

한 PC 의 한 카톡에 두 계정의 발송기가 붙어 있으면 서로 부딪친다. 관리자가
팀 현황에서 한 계정을 다른 계정 발송기로 돌리면, 그 발송기 하나가 둘 다
보낸다. 잡 · 이력 · 하루 상한은 그대로 맡긴 계정 것이다.

여기서 u2(윤서아) 가 u1(강민준) 발송기로 보낸다.
"""
from __future__ import annotations

from .conftest import DEMO_PASSWORD, DEMO_TOKEN, OTHER_TOKEN, auth

KINDS = "deal_intro,ir_delivery,verify_room"


def _via(db, member_id=2, via=1):
    from app.models import User

    db.get(User, member_id).send_via_user_id = via
    db.commit()


def _job(db, user_id=2, kind="deal_intro", n=3):
    from app.models import SendItem, SendJob

    job = SendJob(user_id=user_id, kind=kind, status="queued", total=n)
    db.add(job)
    db.flush()
    for i in range(n):
        db.add(SendItem(job_id=job.id, room_name=f"홍길동{i} 심사역님 가나다벤처스",
                        message="안녕하세요" if kind != "verify_room" else "",
                        status="pending"))
    db.commit()
    return job


def _poll(client, token, kinds=KINDS):
    return client.get(f"/api/agent/poll?kinds={kinds}&cap=60", headers=auth(token))


def _admin(db):
    from app.models import User
    from app.services import auth as auth_svc

    db.add(User(id=9, name="관리자", phone="01000000009", role="admin",
                password_hash=auth_svc.hash_password(DEMO_PASSWORD)))
    db.commit()


# ── 내주는 자리 ──────────────────────────────────────────────────────────────

def test_delegate_agent_gets_the_delegators_job_and_it_stays_theirs(client, db, users):
    _via(db)
    job = _job(db)

    res = _poll(client, DEMO_TOKEN)
    assert res.status_code == 200
    body = res.json()
    assert body["job_id"] == job.id
    # 방 제목은 줄에 실린 그대로 — 같은 카톡이라 그 제목으로 찾는다.
    assert body["items"][0]["room_name"] == "홍길동0 심사역님 가나다벤처스"

    db.expire_all()
    from app.models import SendJob
    assert db.get(SendJob, job.id).user_id == 2  # 주인은 그대로

    # 보내는 도중 묻는 자리도 남의 잡으로 치지 않는다.
    state = client.get(f"/api/agent/jobs/{job.id}/state", headers=auth(DEMO_TOKEN)).json()
    assert state["canceled"] is False


def test_delegate_agent_reports_the_delegators_results(client, db, users):
    """맡은 발송기가 보낸 결과 · 회분 보고는 맡긴 계정의 잡에 그대로 적힌다."""
    from app.models import SendJob

    _via(db)
    job = _job(db, n=1)
    item_id = _poll(client, DEMO_TOKEN).json()["items"][0]["id"]

    assert client.post(f"/api/agent/items/{item_id}/result", json={"status": "sent"},
                       headers=auth(DEMO_TOKEN)).status_code == 200
    assert client.post(f"/api/agent/jobs/{job.id}/status", json={"status": "done"},
                       headers=auth(DEMO_TOKEN)).status_code == 200
    db.expire_all()
    assert db.get(SendJob, job.id).status == "done"


def test_own_agent_finishes_what_it_took_before_delegating(client, db, users):
    """맡기기 전에 물고 간 회분은 본인 발송기가 끝까지 보고한다(`job_state` 와 같다)."""
    from app.models import SendJob

    job = _job(db, n=1)
    item_id = _poll(client, OTHER_TOKEN).json()["items"][0]["id"]
    _via(db)

    assert client.post(f"/api/agent/items/{item_id}/result", json={"status": "sent"},
                       headers=auth(OTHER_TOKEN)).status_code == 200
    assert client.post(f"/api/agent/jobs/{job.id}/status", json={"status": "done"},
                       headers=auth(OTHER_TOKEN)).status_code == 200
    db.expire_all()
    assert db.get(SendJob, job.id).status == "done"


def test_own_agent_of_a_delegating_account_gets_nothing(client, db, users):
    _via(db)
    _job(db)
    assert _poll(client, OTHER_TOKEN).status_code == 204


def test_without_delegation_nothing_changes(client, db, users):
    job = _job(db)
    assert _poll(client, DEMO_TOKEN).status_code == 204
    assert _poll(client, OTHER_TOKEN).json()["job_id"] == job.id
    state = client.get(f"/api/agent/jobs/{job.id}/state", headers=auth(DEMO_TOKEN)).json()
    assert state["canceled"] is True


def test_room_checks_go_to_the_delegate_agent(client, db, users):
    _via(db)
    job = _job(db, kind="verify_room", n=1)
    assert _poll(client, OTHER_TOKEN, kinds="verify_room").status_code == 204
    assert _poll(client, DEMO_TOKEN, kinds="verify_room").json()["job_id"] == job.id


def test_daily_cap_stays_per_account(client, db, users):
    """하루 상한은 잡 주인(맡긴 계정)의 것이다 — 발송기 주인 것이 아니다."""
    from app.models import User

    _via(db)
    db.get(User, 2).daily_send_cap = 2
    db.commit()
    _job(db, n=3)
    assert len(_poll(client, DEMO_TOKEN).json()["items"]) == 2


# ── 배지 ────────────────────────────────────────────────────────────────────

def test_badge_shows_the_delegate_agent(db, users):
    from app import clock
    from app.deps import agent_status
    from app.models import AgentDevice
    from sqlalchemy import select

    dev = db.execute(select(AgentDevice).where(AgentDevice.user_id == 1)).scalar_one()
    dev.last_poll_at = clock.now_iso()
    db.commit()
    assert agent_status(db, 2)["online"] is False

    _via(db)
    state = agent_status(db, 2)
    assert state["online"] is True
    assert state["label"] == "강민준 발송기로 보냄 · 연결됨 · mac-test"
    assert agent_status(db, 1)["label"] == "발송 프로그램 연결됨 · mac-test"


# ── 팀 현황에서 정하기 ───────────────────────────────────────────────────────

def test_admin_sets_and_clears_on_the_team_page(client, db, users):
    from app.models import User

    _admin(db)
    client.post("/login", data={"phone": "01000000009", "password": DEMO_PASSWORD})
    res = client.post("/team/members/2/send-via", data={"via": "1"}, follow_redirects=False)
    assert res.status_code == 303
    db.expire_all()
    assert db.get(User, 2).send_via_user_id == 1

    page = client.get("/team").text
    assert 'action="/team/members/2/send-via"' in page
    assert "강민준 발송기로 보냄" in page
    assert "윤서아 것도 보냄" in page

    client.post("/team/members/2/send-via", data={"via": "0"})
    db.expire_all()
    assert db.get(User, 2).send_via_user_id is None


def test_cannot_chain(client, db, users):
    from app.models import AgentDevice, User

    _admin(db)
    db.add(User(id=3, name="박지호", phone="01000000003", role="user"))
    db.flush()
    db.add(AgentDevice(user_id=3, token="agt_test_token_user3"))
    db.commit()
    _via(db)  # 2 → 1
    client.post("/login", data={"phone": "01000000009", "password": DEMO_PASSWORD})

    # 맡긴 계정(2)에게 다시 맡기기 · 맡은 계정(1)을 남에게 맡기기 — 둘 다 사슬이다.
    client.post("/team/members/3/send-via", data={"via": "2"})
    client.post("/team/members/1/send-via", data={"via": "3"})
    db.expire_all()
    assert db.get(User, 3).send_via_user_id is None
    assert db.get(User, 1).send_via_user_id is None


def test_delegate_must_be_active_and_have_a_token(client, db, users):
    from app.models import User

    _admin(db)
    db.add(User(id=3, name="박지호", phone="01000000003", role="user"))  # 연결키 없음
    db.get(User, 1).is_active = 0
    db.commit()
    client.post("/login", data={"phone": "01000000009", "password": DEMO_PASSWORD})

    client.post("/team/members/2/send-via", data={"via": "3"})
    client.post("/team/members/2/send-via", data={"via": "1"})
    db.expire_all()
    assert db.get(User, 2).send_via_user_id is None


def test_consultant_agent_is_not_offered(client, db, users):
    """투자컨설턴트는 딜소개를 보내지 않는다 — 연결키가 있어도 맡길 발송기가 아니다."""
    from app.models import User

    _admin(db)
    db.get(User, 1).role = "consultant"
    db.commit()
    client.post("/login", data={"phone": "01000000009", "password": DEMO_PASSWORD})

    page = client.get("/team").text
    assert "강민준 발송기로</option>" not in page
    client.post("/team/members/2/send-via", data={"via": "1"})
    db.expire_all()
    assert db.get(User, 2).send_via_user_id is None


def test_members_cannot_set_it(client, db, users):
    from app.models import User

    client.post("/login", data={"phone": "01000000002", "password": DEMO_PASSWORD})
    res = client.post("/team/members/2/send-via", data={"via": "1"}, follow_redirects=False)
    assert res.status_code in (303, 403)
    db.expire_all()
    assert db.get(User, 2).send_via_user_id is None


def test_deactivating_the_delegate_returns_to_own_agent(client, db, users):
    from app.models import User

    _admin(db)
    _via(db)
    client.post("/login", data={"phone": "01000000009", "password": DEMO_PASSWORD})
    client.post("/team/members/1/deactivate")
    db.expire_all()
    assert db.get(User, 2).send_via_user_id is None


# ── 회차가 도는 중에는 바꾸지 않는다 ─────────────────────────────────────────

def test_cannot_change_while_a_job_is_in_flight(client, db, users):
    """보내는 도중 맡긴 곳을 바꾸면 이미 나간 건의 보고가 안 받아져 다시 나간다."""
    from app.models import SendJob, User

    _admin(db)
    _via(db)  # 2 → 1
    client.post("/login", data={"phone": "01000000009", "password": DEMO_PASSWORD})

    for status in ("queued", "running", "paused"):
        job = _job(db)                       # 윤서아(2) 회차
        job.status = status
        db.commit()
        res = client.post("/team/members/2/send-via", data={"via": "0"},
                          follow_redirects=False)
        assert "%EC%95%84%EC%A7%81" in res.headers["location"]   # '아직' — 까닭을 보여 준다
        db.expire_all()
        assert db.get(User, 2).send_via_user_id == 1, f"{status} 회차가 있는데 바뀌었다"
        db.get(SendJob, job.id).status = "done"
        db.commit()

    # 다 끝나면 바뀐다.
    client.post("/team/members/2/send-via", data={"via": "0"})
    db.expire_all()
    assert db.get(User, 2).send_via_user_id is None


def test_delegates_own_jobs_do_not_block(client, db, users):
    """대신 보내 주는 계정(1) 본인의 회차는 막지 않는다 — 그 회차는 그 발송기가 계속 맡는다."""
    from app.models import User

    _admin(db)
    _via(db)  # 2 → 1
    for status in ("queued", "running", "paused"):
        _job(db, user_id=1).status = status
    db.commit()
    client.post("/login", data={"phone": "01000000009", "password": DEMO_PASSWORD})

    client.post("/team/members/2/send-via", data={"via": "0"})
    db.expire_all()
    assert db.get(User, 2).send_via_user_id is None
    # 다시 맡길 때도 마찬가지다.
    client.post("/team/members/2/send-via", data={"via": "1"})
    db.expire_all()
    assert db.get(User, 2).send_via_user_id == 1


def test_mail_only_or_draft_jobs_do_not_block(client, db, users):
    """메일 회차는 서버가 보내고, 예약(draft)은 아직 아무 발송기도 안 쥐었다."""
    from app.models import SendItem, SendJob, User

    _admin(db)
    mail = SendJob(user_id=2, kind="deal_intro", status="queued", total=1)
    db.add(mail)
    db.flush()
    db.add(SendItem(job_id=mail.id, channel="email", room_name="vc@example.com",
                    message="-", status="pending"))
    _job(db).status = "draft"
    db.commit()
    client.post("/login", data={"phone": "01000000009", "password": DEMO_PASSWORD})

    client.post("/team/members/2/send-via", data={"via": "1"})
    db.expire_all()
    assert db.get(User, 2).send_via_user_id == 1


# ── 정지하면 아직 안 나간 회차를 취소한다 ───────────────────────────────────

def test_deactivating_cancels_only_their_unsent_jobs(client, db, users):
    from app.models import SendItem, SendJob

    _admin(db)
    draft = _job(db, user_id=1)
    draft.status = "draft"
    queued = _job(db, user_id=1)
    running = _job(db, user_id=1)
    running.status = "running"
    done = _job(db, user_id=1, n=1)
    done.status = "done"
    db.query(SendItem).filter_by(job_id=done.id).update({"status": "sent"})
    others = _job(db, user_id=2)            # 남의 회차
    db.commit()
    client.post("/login", data={"phone": "01000000009", "password": DEMO_PASSWORD})

    res = client.post("/team/members/1/deactivate", follow_redirects=False)
    assert res.status_code == 303

    db.expire_all()
    status = {j.id: db.get(SendJob, j.id).status
              for j in (draft, queued, running, done, others)}
    assert status == {draft.id: "canceled", queued.id: "canceled", running.id: "running",
                      done.id: "done", others.id: "queued"}
    items = {j.id: {i.status for i in db.get(SendJob, j.id).items}
             for j in (draft, queued, done, others)}
    assert items == {draft.id: {"canceled"}, queued.id: {"canceled"},
                     done.id: {"sent"}, others.id: {"pending"}}
