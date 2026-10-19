"""관리자가 팀원 화면 그대로 보기 (#3).

## 지키는 것

1. 관리자만 켠다 — 팀원은 켜는 길(403)도, 쿠키를 손으로 심는 길도 막힌다.
2. 켜면 "내 것" 을 읽는 화면이 그 팀원 것으로 바뀐다(대시보드 · 딜 제안 관리 ·
   딜 진행 관리 · 주간업무). 관리자 권한은 그대로다(팀 현황이 열린다).
3. 켜져 있는 동안 발송·예약·방 확인 길은 **전부** 403 — 끄면 다시 된다.
4. 고친 것은 관리자 이름으로 남는다(수정 로그 · `누가` 칸).
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from .conftest import DEMO_PASSWORD, DEMO_TOKEN

BLOCKED = "팀원 화면으로 보는 중에는 발송·예약·방 확인을 할 수 없습니다"

# 발송 회차를 세우거나 · 예약을 걸고 풀거나 · 발송기에 방 확인을 시키는 길 전부.
# 하나가 늘면 여기와 라우터(`dependencies=[Depends(no_send_as_member)]`)를 같이 고친다.
SEND_ROUTES = {
    ("POST", "/api/deals/send"),
    ("POST", "/api/deals/queue"),
    ("POST", "/api/deals/queue/{item_id}/start"),
    ("POST", "/api/deals/queue/{item_id}/cancel"),
    ("POST", "/api/deals/manual-sends"),
    ("POST", "/api/deals/manual-sends/{batch_key}/undo"),
    ("POST", "/api/jobs/{job_id}/start"),
    ("POST", "/api/jobs/{job_id}/cancel"),
    ("POST", "/api/jobs/{job_id}/retry"),
    ("POST", "/api/jobs/{job_id}/resend-canceled"),
    ("POST", "/api/jobs/{job_id}/resume"),
    ("POST", "/api/jobs/{job_id}/schedule"),
    ("DELETE", "/api/jobs/{job_id}/schedule"),
    ("POST", "/api/contacts/verify-rooms"),
    ("POST", "/api/startup-msg/send"),
    ("POST", "/api/startup-rooms/search"),
    ("POST", "/deals/startup-ir/send"),
    ("POST", "/deals/startup-ir/rooms/search"),
    ("POST", "/sourcing/rooms/search"),
    ("POST", "/setup/test/attach"),
    ("POST", "/setup/test/startup-remind"),
    ("POST", "/setup/test/meeting-review"),
    ("POST", "/setup/test/room"),
    ("POST", "/team/mail-test"),
    ("POST", "/team/sender-rooms/check"),
    ("POST", "/team/automations/{key}/check"),
    ("POST", "/team/automations/{key}"),
    ("POST", "/team/automation-team"),
    ("POST", "/team/startup-send"),
}


@pytest.fixture()
def admin(db, users):
    from app.models import User
    from app.services import auth as auth_svc

    row = User(id=9, name="관리자", phone="01000000009", role="admin",
               password_hash=auth_svc.hash_password(DEMO_PASSWORD))
    db.add(row)
    db.commit()
    return row


def _login(client, phone):
    client.post("/login", data={"phone": phone, "password": DEMO_PASSWORD})


def _view_as(client, member_id):
    return client.post("/account/view-as", data={"member_id": member_id, "next": "/"},
                       follow_redirects=False)


def _off(client):
    return client.post("/account/view-as/off", data={"next": "/"}, follow_redirects=False)


def _guarded_routes():
    from app.deps import no_send_as_member
    from app.main import create_app

    out = set()
    for route in create_app().routes:
        deps = [d.dependency for d in getattr(route, "dependencies", [])]
        if no_send_as_member in deps:
            out |= {(m, route.path) for m in route.methods}
    return out


def _fill(path):
    return (path.replace("{item_id}", "1").replace("{job_id}", "1")
            .replace("{batch_key}", "x").replace("{key}", "a1"))


# ── 1. 관리자만 켠다 ────────────────────────────────────────────────────────

def test_member_cannot_turn_it_on(client, users, admin):
    _login(client, "01000000001")
    r = _view_as(client, users["u2"].id)
    assert r.status_code == 403
    assert "dealflow_view_as" not in r.headers.get("set-cookie", "")


def test_forged_cookie_does_nothing_for_a_member(client, users, admin):
    _login(client, "01000000001")
    client.cookies.set("dealflow_view_as", str(users["u2"].id))
    page = client.get("/").text
    assert "안녕하세요, 강민준님" in page
    assert 'data-testid="view-as-banner"' not in page
    # 발송 길도 그대로다 — 쿠키 하나로 막히지 않는다.
    r = client.post("/api/contacts/verify-rooms", json={"contact_ids": []})
    assert r.json().get("detail") != BLOCKED


def test_admin_cannot_pick_self_or_consultant(client, db, users, admin):
    from app.models import User

    db.add(User(id=7, name="컨설턴트", phone="01000000007", role="consultant",
                is_active=1))
    db.commit()
    _login(client, "01000000009")
    assert _view_as(client, admin.id).status_code == 404
    assert _view_as(client, 7).status_code == 404
    assert _view_as(client, 999).status_code == 404
    # 고르개에는 팀원만 선다.
    page = client.get("/").text
    assert 'data-testid="view-as-form"' in page
    assert '<option value="1"' in page and '<option value="7"' not in page


# ── 2. 그 팀원 화면을 본다 ────────────────────────────────────────────────────

def test_admin_sees_member_screens(client, db, users, admin):
    from app.models import SendSequence, VcContact

    mine = VcContact(user_id=users["u1"].id, name="팀원담당", firm="가나벤처스",
                     kakao_room_name="팀원담당 방", connect_stage="connected")
    db.add(mine)
    db.flush()
    db.add(SendSequence(user_id=users["u1"].id, contact_id=mine.id, stage=1,
                        next_stage=2, next_due_date="2099-01-01", status="active",
                        day1_sent_at="2026-09-01T10:00:00"))
    db.commit()
    _login(client, "01000000009")
    assert "팀원담당" not in client.get("/deals").text

    r = _view_as(client, users["u1"].id)
    assert r.status_code == 303 and "dealflow_view_as" in r.headers["set-cookie"]

    home = client.get("/").text
    assert "안녕하세요, 강민준님" in home
    assert 'data-testid="view-as-banner"' in home
    assert "강민준 화면으로 보는 중" in home
    assert "내 화면으로 돌아가기" in home
    # 내 계정 칸은 로그인한 본인이다(비밀번호 · 로그아웃이 본인 것).
    assert '<div class="me-name">관리자 · 관리자</div>' in home
    assert 'data-testid="view-as-banner"' in client.get("/deals").text
    assert 'data-name="팀원담당"' in client.get("/deals").text
    assert "팀원담당" in client.get("/ir").text            # 딜 진행 관리
    # 관리자 권한은 그대로 — 팀 현황은 관리자 본인 화면으로 열리고 띠도 선다.
    team = client.get("/team")
    assert team.status_code == 200 and "강민준 화면으로 보는 중" in team.text

    assert _off(client).status_code == 303
    page = client.get("/deals").text
    assert "팀원담당" not in page and 'data-testid="view-as-banner"' not in page


def test_existing_member_picker_defaults_to_that_member(client, db, users, admin):
    from datetime import date

    from app.models import WeeklyTask
    from app.services import weekly

    week = weekly.week_start(date.today()).isoformat()
    db.add_all([WeeklyTask(user_id=users["u1"].id, week_start=week,
                           category="미팅", title="팀원 할 일"),
                WeeklyTask(user_id=admin.id, week_start=week,
                           category="미팅", title="관리자 할 일")])
    db.commit()
    _login(client, "01000000009")
    _view_as(client, users["u1"].id)
    page = client.get("/todo").text
    assert "팀원 할 일" in page and "관리자 할 일" not in page
    # 화면마다의 팀원 고르개도 그대로 쓸 수 있다.
    other = client.get(f"/todo?member={users['u2'].id}")
    assert other.status_code == 200 and "윤서아 님의 주간업무를 보는 중" in other.text


def test_switching_returns_to_the_same_address(client, users, admin):
    """켜고 끈 뒤 주소의 조건(`?…`)까지 그대로 돌아온다 — 빠지면 다른 화면이 된다."""
    _login(client, "01000000009")
    here = "/todo?a=1&b=2"
    assert 'name="next" value="/todo?a=1&amp;b=2"' in client.get(here).text
    r = client.post("/account/view-as", data={"member_id": users["u1"].id, "next": here},
                    follow_redirects=False)
    assert r.headers["location"] == here
    # 보는 중에는 고르개와 띠의 [내 화면으로 돌아가기] 둘 다 같은 주소를 싣는다.
    assert client.get(here).text.count('name="next" value="/todo?a=1&amp;b=2"') == 2
    r = client.post("/account/view-as/off", data={"next": here}, follow_redirects=False)
    assert r.headers["location"] == here


def test_own_device_token_never_shows_the_members(client, users, admin):
    _login(client, "01000000009")
    _view_as(client, users["u1"].id)
    page = client.get("/setup").text
    assert DEMO_TOKEN not in page


# ── 3. 발송·예약·방 확인은 전부 막힌다 ────────────────────────────────────────

def test_every_send_route_carries_the_one_guard():
    assert _guarded_routes() == SEND_ROUTES


@pytest.mark.parametrize("method, path", sorted(SEND_ROUTES))
def test_send_routes_are_blocked_while_viewing(client, users, admin, method, path):
    _login(client, "01000000009")
    _view_as(client, users["u1"].id)
    r = client.request(method, _fill(path), json={})
    assert r.status_code == 403
    assert r.json()["detail"] == BLOCKED

    _off(client)
    r = client.request(method, _fill(path), json={})
    assert not (r.status_code == 403 and r.json().get("detail") == BLOCKED)


def test_send_works_again_after_switching_back(client, db, users, admin):
    from app.models import IrCompany, VcContact

    company = IrCompany(name="샘플애그", one_liner="소개", revenue_recent=10)
    own = VcContact(user_id=admin.id, name="관리자담당", firm="가나벤처스",
                    kakao_room_name="관리자담당 방", room_verified="verified",
                    connect_stage="connected")
    db.add_all([company, own])
    db.commit()
    body = {"company_ids": [company.id], "contact_ids": [own.id]}
    _login(client, "01000000009")
    _view_as(client, users["u1"].id)
    assert client.post("/api/deals/send", json=body).status_code == 403
    assert client.post("/api/contacts/verify-rooms",
                       json={"contact_ids": [own.id]}).status_code == 403

    _off(client)
    r = client.post("/api/deals/send", json=body)
    assert r.status_code == 200, r.text
    assert r.json()["job_id"]
    r = client.post("/api/contacts/verify-rooms", json={"contact_ids": [own.id]})
    assert r.status_code == 200, r.text


@pytest.mark.skipif(shutil.which("node") is None,
                    reason="node 미설치 — 브라우저 로직 테스트 생략")
def test_send_buttons_are_stopped_in_the_browser():
    """`data-send` 단추를 누르기 전에 막는지 — `view_as.js` 를 그대로 돌린다
    (tests/js/view_as_test.js)."""
    script = Path(__file__).resolve().parent / "js" / "view_as_test.js"
    out = subprocess.run([shutil.which("node"), str(script)],
                         capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stdout + out.stderr


def test_send_buttons_are_marked_on_the_member_screen(client, users, admin):
    _login(client, "01000000009")
    _view_as(client, users["u1"].id)
    page = client.get("/deals").text
    assert f'data-view-as-note="{BLOCKED}"' in page
    assert "js/view_as.js" in page
    assert 'id="send-btn" class="primary-btn" disabled data-send' in page

    _off(client)
    page = client.get("/deals").text
    assert "data-view-as-note" not in page and "js/view_as.js" not in page


# ── 4. 고친 것은 관리자 이름으로 남는다 ──────────────────────────────────────

def test_edits_are_recorded_under_the_admin(client, db, users, admin):
    from sqlalchemy import select

    from app.models import DealFollowup, EditLog, VcContact

    contact = VcContact(user_id=users["u1"].id, name="팀원담당", firm="가나벤처스",
                        connect_stage="connected")
    db.add(contact)
    db.commit()
    _login(client, "01000000009")
    _view_as(client, users["u1"].id)

    r = client.patch(f"/api/contacts/{contact.id}", json={"memo": "관리자가 적음"})
    assert r.status_code == 200, r.text
    # 끄는 것은 언제나 된다 — 끈 사람도 `누가` 칸에 남는다.
    r = client.post(f"/ir/contacts/{contact.id}/call-needed", data={"on": "0"},
                    follow_redirects=False)
    assert r.status_code == 303, r.text

    db.expire_all()
    logs = db.execute(select(EditLog).where(EditLog.table_name == "vc_contacts")).scalars().all()
    assert logs and {log.actor_user_id for log in logs} == {admin.id}
    flag = db.execute(select(DealFollowup)
                      .where(DealFollowup.contact_id == contact.id)).scalars().one()
    assert flag.call_by == admin.id
    # 팀원 줄은 그대로 팀원 것이다 — 역할이 원본에 쓰이지 않았다.
    assert db.get(VcContact, contact.id).user_id == users["u1"].id
    assert db.get(type(admin), users["u1"].id).role == "user"


def test_logout_and_login_clear_the_switch(client, users, admin):
    _login(client, "01000000009")
    _view_as(client, users["u1"].id)
    assert client.cookies.get("dealflow_view_as")
    client.get("/logout")
    assert client.cookies.get("dealflow_view_as") is None
    # 로그아웃 없이 다시 로그인해도(같은 브라우저의 다음 사람) 물려받지 않는다.
    _login(client, "01000000009")
    _view_as(client, users["u1"].id)
    assert client.cookies.get("dealflow_view_as")
    _login(client, "01000000002")
    assert client.cookies.get("dealflow_view_as") is None
