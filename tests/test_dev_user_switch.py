"""개발용 사용자 전환 (쿠키) + 사용자별 격리.

★ 인증 테스트가 아니다. 이 전환은 인증이 아니며(누구나 쿠키를 바꿀 수 있다),
정식 로그인(휴대폰번호 + 비밀번호)은 다음 스프린트에 붙는다. 여기서 확인하는 건
"사용자를 바꾸면 보이는 데이터와 에이전트가 실제로 갈리는가"다.
"""
from app.deps import DEV_USER_COOKIE
from app.models import AgentDevice, SendItem, SendJob, VcContact

from .conftest import DEMO_TOKEN, OTHER_TOKEN, auth


def _seed_two_users_contacts(db):
    db.add_all([
        VcContact(user_id=1, name="홍길동", title="대표님", firm="가나벤처스",
                  channel_kakao=1, kakao_room_name="홍길동 대표님 가나벤처스", status="active"),
        VcContact(user_id=2, name="장하늘", title="심사역", firm="바사벤처스",
                  channel_kakao=1, kakao_room_name="장하늘 심사역님 바사벤처스", status="active"),
    ])
    db.commit()


def test_default_user_without_cookie(client, db):
    _seed_two_users_contacts(db)
    html = client.get("/contacts").text
    assert "홍길동" in html and "장하늘" not in html


def test_switching_user_changes_visible_data(client, db):
    _seed_two_users_contacts(db)
    r = client.get("/dev/switch-user", params={"user_id": 2, "next": "/contacts"},
                   follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/contacts"
    assert client.cookies.get(DEV_USER_COOKIE) == "2"

    html = client.get("/contacts").text
    assert "장하늘" in html and "홍길동" not in html


def test_switch_only_redirects_inside_the_app(client, db):
    """next 로 외부 주소를 넣어도 앱 안으로만 돌아간다."""
    r = client.get("/dev/switch-user", params={"user_id": 2, "next": "https://example.com"},
                   follow_redirects=False)
    assert r.headers["location"] == "/deals"


def test_unknown_user_keeps_current(client, db):
    r = client.get("/dev/switch-user", params={"user_id": 999, "next": "/contacts"},
                   follow_redirects=False)
    assert r.status_code == 303
    assert client.cookies.get(DEV_USER_COOKIE) is None


def test_agent_badge_follows_the_selected_user(client, db, users):
    """Mac 화면에서 Windows 에이전트가 '내 에이전트'로 보이면 안 된다."""
    dev1 = db.query(AgentDevice).filter_by(user_id=1).one()
    dev1.hostname = "mac-mini"
    db.query(AgentDevice).filter_by(user_id=2).one().hostname = "win-desktop"
    db.commit()

    assert client.get("/api/agent-status").json()["hostname"] == "mac-mini"
    client.get("/dev/switch-user", params={"user_id": 2})
    assert client.get("/api/agent-status").json()["hostname"] == "win-desktop"


def test_setup_page_shows_the_selected_users_token(client, db, users):
    """기기마다 다른 사용자를 골라 받아야 한다 → 화면이 누구 토큰인지 밝혀야 한다."""
    html = client.get("/setup").text
    assert "강민준" in html and DEMO_TOKEN in html

    client.get("/dev/switch-user", params={"user_id": 2})
    html2 = client.get("/setup").text
    assert "윤서아" in html2 and OTHER_TOKEN in html2 and DEMO_TOKEN not in html2


def test_downloaded_agent_zip_carries_the_selected_users_token(client, db, users):
    client.get("/dev/switch-user", params={"user_id": 2})
    r = client.get("/download/agent?os_kind=windows")
    assert r.status_code == 200

    import io
    import zipfile

    with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
        cfg = zf.read("agent/config.yaml").decode("utf-8")
    assert OTHER_TOKEN in cfg and DEMO_TOKEN not in cfg


def test_send_job_goes_only_to_its_owners_agent(client, db, users):
    """사용자 A의 잡은 A 토큰 에이전트만 받는다 (사용자 1명 = 에이전트 1대)."""
    _seed_two_users_contacts(db)
    contact = db.query(VcContact).filter_by(user_id=1).one()
    job = SendJob(user_id=1, kind="deal_intro", status="queued", total=1)
    db.add(job)
    db.flush()
    db.add(SendItem(job_id=job.id, contact_id=contact.id,
                    room_name=contact.kakao_room_name, message="본문", status="pending"))
    db.commit()

    # 다른 사용자의 에이전트는 이 잡을 보지 못한다
    assert client.get("/api/agent/poll", headers=auth(OTHER_TOKEN)).status_code == 204
    claimed = client.get("/api/agent/poll", headers=auth(DEMO_TOKEN))
    assert claimed.status_code == 200 and claimed.json()["job_id"] == job.id
