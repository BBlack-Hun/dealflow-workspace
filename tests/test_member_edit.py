"""관리자가 팀원의 이름과 로그인 ID 를 고친다 — 팀 현황(`/team`).

이 기능이 생긴 이유. 입퇴사가 생기면 **계정을 지우지 않고 넘겨야 한다.**
담당 투자사(`VcContact.user_id`)와 발송 이력(`SendJob.user_id`)이 계정에
붙어 있어서, 퇴사자 계정을 정지하고 입사자 계정을 새로 만들면 그 이력이
통째로 끊긴다. 그래서 **입사자 이름과 휴대폰번호로 갈아 끼워 그대로 물려준다.**

여기서 못 박는 것.

1. **관리자만 한다.** 팀원도 투자컨설턴트도 남의 계정을 건드릴 수 없다.
2. **바꾼 번호로 실제로 로그인되고, 옛 번호로는 안 된다.** 로그인 ID 가
   휴대폰번호이므로 이게 안 되면 계정을 넘긴 것이 아니다.
3. **이미 쓰는 번호로는 못 바꾼다.** 두 계정이 같은 번호를 가지면 그 번호로
   온 로그인이 어느 계정으로 갈지 알 수 없다.
4. **잘못된 형식은 막힌다.** 계정 생성과 같은 기준(숫자 10자리 이상).
5. **담당 투자사와 발송 이력이 그대로 붙어 있다.** ← 이 기능의 핵심이다.
   이게 끊기면 계정을 새로 만드는 것과 다를 바가 없다.
6. **번호를 바꾸면 열린 세션이 끊긴다.** 넘겨받는 사람이 쓰기 전에 퇴사자
   세션이 살아 있으면 안 된다.
7. **번호를 바꾸면 발송 프로그램 연결키를 새로 발급한다.** 그대로 두면
   퇴사자 PC 에 남은 키로 새 담당자의 발송 잡을 가로채 실제 투자사에게
   보낸다.
8. **본인 것은 못 바꾼다.** 제 번호를 잘못 적으면 그 자리에서 세션이 끊겨
   어느 번호로도 못 들어온다(형제 라우터들도 본인을 막는다).
9. **없는 계정은 404.**
"""
from __future__ import annotations

import pytest

from .conftest import DEMO_PASSWORD, DEMO_TOKEN

# 넘겨받는 사람의 번호. 공개 저장소라 실제로 존재하는 번호를 쓰지 않는다.
NEW_PHONE = "01000000077"
NEW_NAME = "입사자"


@pytest.fixture()
def people(db, users):
    """관리자 하나 · 투자컨설턴트 하나. conftest 의 두 계정은 둘 다 팀원이다."""
    from app.models import User
    from app.services import auth as auth_svc

    pw = auth_svc.hash_password(DEMO_PASSWORD)
    rows = [
        User(id=91, name="관리자", phone="01000000091", role="admin", password_hash=pw),
        User(id=92, name="컨설턴트", phone="01000000092", role="consultant", password_hash=pw),
    ]
    db.add_all(rows)
    db.commit()
    return {"admin": rows[0], "consultant": rows[1],
            "member": users["u1"], "other": users["u2"]}


@pytest.fixture()
def portal(db, users, people):
    """앱 하나 + 역할별로 따로 로그인한 클라이언트.

    한 클라이언트로 로그인을 갈아타면 쿠키가 덮여서 어느 사람으로 부른
    것인지 알 수 없게 된다(test_password_reset.py 와 같은 이유).
    """
    from fastapi.testclient import TestClient

    from app.main import create_app

    app = create_app()

    def sign_in(phone: str):
        client = TestClient(app)
        r = client.post("/login", data={"phone": phone, "password": DEMO_PASSWORD},
                        follow_redirects=False)
        assert r.status_code == 303
        return client

    return {
        "app": app,
        "admin": sign_in("01000000091"),
        "consultant": sign_in("01000000092"),
        "member": sign_in("01000000001"),
    }


def _edit(client, member_id: int, *, name: str = NEW_NAME, phone: str = NEW_PHONE):
    return client.post(f"/team/members/{member_id}/profile",
                       data={"name": name, "phone": phone},
                       follow_redirects=False)


def _where(response) -> str:
    """돌아가라고 알려 준 주소 — 한글이 퍼센트 인코딩돼 있어 풀어서 본다.

    `RedirectResponse` 가 Location 헤더를 인코딩한다. 안 풀고 견주면 안내
    문구를 확인하는 검사가 전부 조용히 어긋난다.
    """
    from urllib.parse import unquote

    return unquote(response.headers["location"])


def _can_log_in(app, phone: str, password: str = DEMO_PASSWORD):
    """새 클라이언트로 로그인해 본다 — 되면 도착지, 안 되면 None."""
    from fastapi.testclient import TestClient

    client = TestClient(app)
    r = client.post("/login", data={"phone": phone, "password": password},
                    follow_redirects=False)
    if r.status_code != 303 or "error=1" in r.headers.get("location", ""):
        return None
    return r.headers["location"]


# --- 관리자만 한다 ----------------------------------------------------------

def test_a_team_member_cannot_rename_anyone(portal, db, people):
    """팀원이 남의 로그인 ID 를 바꿀 수 있으면 남의 계정을 가져갈 수 있다."""
    other = people["other"]
    before = (other.name, other.phone)

    assert _edit(portal["member"], other.id).status_code == 403

    db.refresh(other)
    assert (other.name, other.phone) == before


def test_a_consultant_cannot_rename_anyone(portal, db, people):
    """컨설턴트는 미들웨어가 자기 화면으로 돌려보낸다 — 403 이 아니라 303 이다."""
    member = people["member"]
    before = (member.name, member.phone)

    r = _edit(portal["consultant"], member.id)
    assert r.status_code == 303
    assert r.headers["location"] == "/consulting"

    db.refresh(member)
    assert (member.name, member.phone) == before


# --- 계정을 실제로 넘기는가 -------------------------------------------------

def test_the_newcomer_logs_in_with_the_new_number(portal, db, people):
    """로그인 ID 가 휴대폰번호다 — 새 번호로 못 들어가면 넘긴 것이 아니다."""
    member = people["member"]
    old_phone = member.phone

    assert _edit(portal["admin"], member.id).status_code == 303

    assert _can_log_in(portal["app"], NEW_PHONE) is not None
    # 옛 번호는 더 이상 통하지 않는다 — 퇴사자가 계속 들어올 수 있으면 안 된다.
    assert _can_log_in(portal["app"], old_phone) is None

    db.refresh(member)
    assert member.name == NEW_NAME


def test_the_number_is_normalized_before_it_is_stored(portal, db, people):
    """하이픈을 넣어 저장해도 하이픈 없이 로그인돼야 한다.

    저장과 비교가 같은 규칙으로 정규화되지 않으면, 관리자가 `010-…` 로 적어
    넘긴 계정에 새 담당자가 `010…` 로는 못 들어간다
    (`auth.normalize_phone` 주석이 그 이유다).
    """
    member = people["member"]

    assert _edit(portal["admin"], member.id, phone="010-0000-0077").status_code == 303

    db.refresh(member)
    assert member.phone == NEW_PHONE            # 숫자만 남는다
    assert _can_log_in(portal["app"], NEW_PHONE) is not None
    assert _can_log_in(portal["app"], "010-0000-0077") is not None


def test_the_password_is_left_alone(portal, db, people):
    """비밀번호는 여기서 건드리지 않는다 — 필요하면 [비밀번호 초기화]가 따로 있다."""
    member = people["member"]
    before = member.password_hash

    _edit(portal["admin"], member.id)

    db.refresh(member)
    assert member.password_hash == before
    assert member.must_change_password == 0


# --- 이 기능의 핵심: 이력이 끊기지 않는가 -----------------------------------

def test_the_investors_and_the_send_history_stay_on_the_account(portal, db, people):
    """**이게 이 기능의 존재 이유다.**

    담당 투자사와 발송 이력은 계정(`user_id`)에 붙어 있다. 퇴사자 계정을 지우고
    새로 만들면 그 연결이 끊겨, 새 담당자는 빈 명단으로 시작하고 지난 회차에
    무엇을 누구에게 보냈는지 알 수 없게 된다.
    """
    from app.models import SendItem, SendJob, VcContact

    member = people["member"]
    keeper = VcContact(user_id=member.id, name="투자사담당", firm="가나벤처스")
    db.add_all([keeper, VcContact(user_id=member.id, name="투자사담당2",
                                  firm="다라벤처스")])
    job = SendJob(user_id=member.id, kind="opening_first", status="done")
    db.add(job)
    db.flush()
    db.add(SendItem(job_id=job.id, contact_id=keeper.id, room_name="가나벤처스 방",
                    message="지난 회차 본문", status="sent"))
    db.commit()
    job_id = job.id

    assert _edit(portal["admin"], member.id).status_code == 303

    db.expire_all()
    from sqlalchemy import select

    contacts = db.execute(
        select(VcContact).where(VcContact.user_id == member.id)).scalars().all()
    assert len(contacts) == 2, "담당 투자사가 계정에서 떨어졌다"
    assert {c.firm for c in contacts} == {"가나벤처스", "다라벤처스"}

    jobs = db.execute(select(SendJob).where(SendJob.user_id == member.id)).scalars().all()
    assert [j.id for j in jobs] == [job_id], "발송 이력이 계정에서 떨어졌다"

    # 계정 자체가 그대로다 — 지우고 새로 만든 것이 아니다.
    db.refresh(member)
    assert member.id == people["member"].id
    assert member.is_active == 1


# --- 이미 쓰는 번호 · 잘못된 형식 -------------------------------------------

def test_a_number_that_is_already_taken_is_refused(portal, db, people):
    """두 계정이 같은 번호면 그 번호로 온 로그인이 어디로 갈지 알 수 없다."""
    member, other = people["member"], people["other"]
    before = member.phone

    r = _edit(portal["admin"], member.id, phone=other.phone)
    assert r.status_code == 303
    assert "이미+등록된+번호입니다" in _where(r)
    # 고치라고 수정칸은 펴 둔 채로 돌려보낸다.
    assert f"edit={member.id}" in _where(r)

    db.refresh(member)
    assert member.phone == before
    assert member.name != NEW_NAME, "번호가 막혔는데 이름만 바뀌면 반쯤 저장된 것이다"


def test_the_check_ignores_hyphens_in_the_taken_number(portal, db, people):
    """`010-…` 로 적으면 통과하던 식이면 중복 검사가 없는 것과 같다."""
    member, other = people["member"], people["other"]
    typed = f"{other.phone[:3]}-{other.phone[3:7]}-{other.phone[7:]}"

    r = _edit(portal["admin"], member.id, phone=typed)
    assert "이미+등록된+번호입니다" in _where(r)

    db.refresh(member)
    assert member.phone != other.phone


def test_keeping_the_same_number_is_not_a_duplicate(portal, db, people):
    """이름만 고치려고 번호를 그대로 두고 저장하는 것이 정상 동작이다."""
    member = people["member"]

    r = _edit(portal["admin"], member.id, phone=member.phone)
    assert r.status_code == 303
    assert "이미+등록된" not in _where(r)

    db.refresh(member)
    assert member.name == NEW_NAME


@pytest.mark.parametrize("bad", ["0101234", "", "010-abc-defg", "없음"])
def test_a_number_that_is_not_a_number_is_refused(portal, db, people, bad):
    """계정 생성과 같은 기준으로 거른다 — 두 곳이 갈리면 하나는 곧 낡는다."""
    member = people["member"]
    before = (member.name, member.phone)

    r = _edit(portal["admin"], member.id, phone=bad)
    assert r.status_code == 303
    assert "휴대폰번호를+다시+확인해+주세요" in _where(r)

    db.refresh(member)
    assert (member.name, member.phone) == before


# --- 세션 · 발송 프로그램 연결키 ---------------------------------------------

def test_changing_the_number_cuts_the_open_sessions(portal, db, people):
    """넘겨받는 사람이 쓰기 전에 퇴사자 세션이 살아 있으면 안 된다.

    세션은 번호가 아니라 쿠키의 토큰으로 산다 — 남겨 두면 퇴사자 PC 는 로그인
    화면을 다시 거치지 않고 새 담당자의 화면을 그대로 쓴다.
    """
    member = people["member"]
    assert portal["member"].get("/dashboard").status_code == 200

    _edit(portal["admin"], member.id)

    r = portal["member"].get("/dashboard", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"].startswith("/login")


def test_changing_only_the_name_leaves_the_session_alone(portal, db, people):
    """오타를 고치는 일에 그 사람을 로그아웃시킬 이유가 없다."""
    member = people["member"]

    _edit(portal["admin"], member.id, name="이름고침", phone=member.phone)

    assert portal["member"].get("/dashboard").status_code == 200


def test_changing_the_number_reissues_the_agent_token(portal, db, people):
    """퇴사자 PC 에 남은 키로 새 담당자의 발송 잡을 가로채면 안 된다.

    그 잡은 실제 투자사에게 나가는 것이라, 잘못 나가면 되돌릴 수 없다.
    """
    from sqlalchemy import select

    from app.models import AgentDevice

    member = people["member"]

    _edit(portal["admin"], member.id)

    db.expire_all()
    device = db.execute(
        select(AgentDevice).where(AgentDevice.user_id == member.id)).scalars().first()
    assert device is not None, "연결키가 통째로 사라지면 새 담당자가 발송을 못 한다"
    assert device.token != DEMO_TOKEN, "퇴사자 PC 의 키가 그대로 살아 있다"
    # 붙어 있던 PC 의 흔적도 지운다 — 안 지우면 팀 현황이 이제 못 붙는 기기를
    # '연결됨'으로 계속 보여 준다.
    assert not device.last_poll_at
    assert not device.hostname

    # 옛 키로는 에이전트가 더 이상 못 붙는다.
    from .conftest import auth

    assert portal["app"] is not None
    from fastapi.testclient import TestClient

    agent = TestClient(portal["app"])
    assert agent.get("/api/agent/poll", headers=auth(DEMO_TOKEN)).status_code == 401
    assert agent.get("/api/agent/poll", headers=auth(device.token)).status_code != 401


def test_changing_only_the_name_keeps_the_agent_token(portal, db, people):
    """이름 오타를 고쳤다고 남의 발송 프로그램을 끊을 이유가 없다."""
    from sqlalchemy import select

    from app.models import AgentDevice

    member = people["member"]

    _edit(portal["admin"], member.id, name="이름고침", phone=member.phone)

    db.expire_all()
    device = db.execute(
        select(AgentDevice).where(AgentDevice.user_id == member.id)).scalars().first()
    assert device.token == DEMO_TOKEN


# --- 본인 · 없는 계정 -------------------------------------------------------

def test_an_admin_cannot_change_their_own_number(portal, db, people):
    """제 번호를 잘못 적으면 그 자리에서 세션이 끊겨 어느 번호로도 못 들어온다.

    되돌리려면 DB 를 직접 고쳐야 하는데, 그게 이 화면이 없애려던 상황이다.
    형제 라우터들(권한·초기화·정지)도 같은 이유로 본인을 막는다.
    """
    admin = people["admin"]
    before = (admin.name, admin.phone)

    r = _edit(portal["admin"], admin.id)
    assert r.status_code == 303

    db.refresh(admin)
    assert (admin.name, admin.phone) == before
    # 세션도 살아 있어야 한다 — 막았는데 로그아웃되면 막은 의미가 없다.
    assert portal["admin"].get("/team").status_code == 200


def test_editing_an_account_that_is_not_there_is_404(portal):
    assert _edit(portal["admin"], 999_999).status_code == 404


# --- 화면에 길이 있는가 -----------------------------------------------------

def test_the_button_and_the_form_are_on_the_team_screen(portal, people):
    """라우터만 있고 단추가 없으면 관리자는 여전히 서버에 들어가야 한다."""
    member, admin = people["member"], people["admin"]

    body = portal["admin"].get("/team").text
    assert f'href="/team?edit={member.id}"' in body
    # 본인 줄에는 없다.
    assert f'href="/team?edit={admin.id}"' not in body
    # 평소에는 수정칸이 펴져 있지 않다.
    assert f'action="/team/members/{member.id}/profile"' not in body

    opened = portal["admin"].get(f"/team?edit={member.id}").text
    assert f'action="/team/members/{member.id}/profile"' in opened
    # 지금 값이 채워져 있어야 고칠 자리만 고친다.
    assert f'value="{member.phone}"' in opened


def test_the_form_does_not_open_on_the_admins_own_row(portal, people):
    """라우터가 막는 것을 화면도 막는다 — 열리는데 저장이 안 되면 이유를 알 수 없다."""
    admin = people["admin"]
    body = portal["admin"].get(f"/team?edit={admin.id}").text
    assert f'action="/team/members/{admin.id}/profile"' not in body
