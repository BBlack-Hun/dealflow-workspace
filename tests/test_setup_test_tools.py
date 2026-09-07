"""`/setup` 의 시험용 자리 — 발송기가 실제로 도는지 화면에서 눌러 본다.

## 무엇이 없었나

파일 첨부가 되는지, 카톡방 이름이 맞는지 보려면 **사람이 DB 에 잡을 손으로
심어야 했다.** 발송기를 새 PC 에 깔 때마다 그 짓을 반복했고, 심을 줄 모르는
사람은 확인할 방법이 아예 없었다.

## 무엇을 지키나

1. ★ **시험방이 없으면 자리 자체가 없다** — 화면에도 없고 주소로도 안 된다.
   운영에는 `DEALFLOW_TEST_ROOM` 이 없으니 이 자리는 **저절로 닫힌다.**
   그것이 이 기능의 안전선이라 제일 먼저·제일 많이 본다
2. 파일 시험은 **시험방으로만** 간다 — 사람이 방을 고를 수 없다
3. 방 이름 시험은 **아무것도 보내지 않는다** — 이미 있는 `verify_room` 길을
   그대로 빌린다(새 종류를 만들면 발송기를 갱신할 때까지 큐에 멈춘다)
4. 누가 쓸 수 있나 — `/setup` 의 결을 그대로 따른다(새 규칙을 만들지 않는다)
5. **오류 문구가 화면에 그대로 보인다** — 그 문구가 이 시험의 알맹이다
6. 시험 잡이 **발송 이력·통계에 섞이지 않는다**
"""
from __future__ import annotations

import json

import pytest

from .conftest import DEMO_PASSWORD, DEMO_TOKEN, auth

#: 검사용 시험방. 실제 값은 `.env` 로 들어오고 저장소에는 올리지 않는다.
TEST_ROOM = "나와의 채팅"

#: 화면에서 시험용 자리를 알아보는 표식.
THE_PANEL = "🧪 시험용"
THE_FILE_FIELD = 'name="file_name"'
THE_ROOM_FIELD = 'name="room_name"'


@pytest.fixture()
def rehearsal(monkeypatch):
    """시험 모드 ON. `config.TEST_ROOM` 은 화면·라우터가 함께 읽는 한 값이다."""
    from app import config

    monkeypatch.setattr(config, "TEST_ROOM", TEST_ROOM)
    return TEST_ROOM


@pytest.fixture()
def may_attach(db, users):
    """자료 자동 첨부를 켜 준 계정(u1). 파일 시험은 이 계정만 쓴다."""
    users["u1"].can_auto_attach_ir = 1
    db.commit()
    return users["u1"]


def _jobs(db):
    from app.models import SendJob

    return db.query(SendJob).order_by(SendJob.id).all()


def _press(client, path: str, **fields):
    """단추를 누른다. **따라가지 않는다** — 어디로 보내는지가 곧 결과다."""
    return client.post(path, data=fields, follow_redirects=False)


def _job_id(response) -> int:
    """`/jobs/12` 로 되돌려 보내는 응답에서 회차 번호만."""
    assert response.status_code in (302, 303), response.status_code
    location = response.headers["location"]
    assert location.startswith("/jobs/"), location
    return int(location.rsplit("/", 1)[1])


# ══════════════════════════════════════════════════════════════════════════
#  ① ★ 시험방이 없으면 — 화면에도 없고 주소로도 안 된다
# ══════════════════════════════════════════════════════════════════════════
#
# 운영에는 시험방 설정이 없다. 그러니 이 자리는 운영에서 **저절로** 닫혀야
# 하고, 그것이 이 기능이 안전한 유일한 이유다. 화면만 감추면 주소로 그대로
# 부를 수 있다 — 이 저장소가 여러 번 겪은 사고다(사이드바와 라우터가 갈려
# 컨설턴트에게 전부 열려 있던 일, 자료 폴더 칸이 문이자 스위치였던 일).

def test_without_a_test_room_the_panel_is_not_drawn(logged_in, may_attach):
    """`DEALFLOW_TEST_ROOM` 이 비어 있으면(검사 기본값) 자리가 아예 없다."""
    html = logged_in.get("/setup").text
    assert THE_PANEL not in html
    assert THE_FILE_FIELD not in html
    assert THE_ROOM_FIELD not in html


def test_without_a_test_room_the_routes_are_not_there(logged_in, may_attach, db):
    """★ 주소로 직접 불러도 안 된다. **404 — 막힌 것이 아니라 없는 것이다.**"""
    r1 = _press(logged_in, "/setup/test/attach", file_name="회사소개서.pdf")
    r2 = _press(logged_in, "/setup/test/room", room_name="아무방")
    assert r1.status_code == 404, "시험방이 없는데 파일 시험이 열려 있다"
    assert r2.status_code == 404, "시험방이 없는데 방 이름 시험이 열려 있다"
    assert _jobs(db) == [], "자리가 없어야 하는데 잡이 만들어졌다"


def test_a_blank_test_room_is_the_same_as_none(logged_in, may_attach, monkeypatch, db):
    """공백만 넣어 둔 것도 '없음' 이다 — `.env` 에 실수로 띄어쓰기가 남는다."""
    from app import config

    monkeypatch.setattr(config, "TEST_ROOM", "   ")
    assert THE_PANEL not in logged_in.get("/setup").text
    assert _press(logged_in, "/setup/test/attach", file_name="a.pdf").status_code == 404
    assert _jobs(db) == []


def test_the_screen_and_the_routes_read_one_function(rehearsal):
    """판정이 두 곳에 적히면 한쪽만 낡는다 — 화면과 라우터가 같은 함수를 읽는다."""
    from app.routers import setup as setup_router

    assert setup_router.test_tools_on() is True


# ══════════════════════════════════════════════════════════════════════════
#  ② 파일 첨부 시험 — 시험방으로만 간다
# ══════════════════════════════════════════════════════════════════════════

def test_the_panel_appears_in_rehearsal_mode(logged_in, rehearsal, may_attach):
    html = logged_in.get("/setup").text
    assert THE_PANEL in html
    assert THE_FILE_FIELD in html and THE_ROOM_FIELD in html
    # 시험용이라는 것과 어디로 가는지가 화면에 적혀 있어야 한다 — 남겨 두는
    # 자리라 "이건 시험이다" 가 안 보이면 실발송으로 오해한다.
    assert TEST_ROOM in html


def test_the_file_test_goes_to_the_test_room_only(logged_in, rehearsal, may_attach, db):
    """★ 방을 고르는 칸이 없고, 잡의 방 이름은 **시험방**이다."""
    from app.models import TEST_SEND_KIND

    r = _press(logged_in, "/setup/test/attach", file_name="회사소개서.pdf")
    job_id = _job_id(r)

    job = _jobs(db)[0]
    assert job.id == job_id
    assert job.kind == TEST_SEND_KIND
    assert job.status == "queued" and job.total == 1
    item = job.items[0]
    assert item.room_name == TEST_ROOM, "시험방이 아닌 곳으로 간다"
    assert json.loads(item.files_json) == ["회사소개서.pdf"]
    assert item.contact_id is None and item.sourcing_contact_id is None


def test_a_typed_room_name_cannot_redirect_the_file_test(logged_in, rehearsal,
                                                         may_attach, db):
    """방 이름을 함께 실어 보내도 **시험방으로만** 간다.

    방 이름을 적는 칸이 옆에 있으니(방 이름 시험) 그 값을 이쪽으로 밀어 넣는
    시도가 자연스럽다. 라우터가 그 값을 아예 받지 않는다.
    """
    r = _press(logged_in, "/setup/test/attach", file_name="회사소개서.pdf", room_name="진짜투자사방")
    _job_id(r)
    assert _jobs(db)[0].items[0].room_name == TEST_ROOM


def test_the_file_test_sends_files_first_then_one_message(logged_in, rehearsal,
                                                          may_attach, db):
    """실제 자료 전달과 **같은 모양**이라야 시험이 시험 구실을 한다.

    파일과 문구가 함께 실리고, 차례(파일 먼저 문구 나중)는 발송기가 지킨다
    (`agent/main.py: send_item`). 여기서는 둘 다 실렸는지만 본다.
    """
    from app.routers.setup import TEST_FILE_MESSAGE

    _job_id(_press(logged_in, "/setup/test/attach", file_name="a.pdf"))
    item = _jobs(db)[0].items[0]
    assert item.files_json and item.message == TEST_FILE_MESSAGE
    assert "시험" in item.message, "받는 사람이 시험인 줄 알아야 한다"


def test_an_empty_file_name_just_comes_back(logged_in, rehearsal, may_attach, db):
    """빈 칸으로 누르면 날것의 오류가 아니라 **화면으로 돌아온다.**"""
    r = logged_in.post("/setup/test/attach", data={"file_name": "  "},
                       follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/setup?test=need_file"
    assert _jobs(db) == [], "빈 칸인데 잡이 만들어졌다"
    assert "적어주세요" in logged_in.get("/setup?test=need_file").text


def test_the_job_is_made_for_the_person_who_pressed_it(logged_in, rehearsal,
                                                       may_attach, db, users):
    """잡은 그 사람의 기기 토큰으로만 내려간다 — 로그인한 사람 것이어야 한다."""
    _job_id(_press(logged_in, "/setup/test/attach", file_name="a.pdf"))
    assert _jobs(db)[0].user_id == users["u1"].id


def test_the_file_job_reaches_a_sender_that_can_attach(logged_in, rehearsal,
                                                       may_attach):
    """★ 발송기가 실제로 집어간다 — 파일을 붙일 줄 안다고 밝힌 발송기만.

    파일이 실린 잡을 구형 발송기가 받으면 **문구만** 나간다. 그 판정은 이미
    있고(`routers/agent_api.py: poll` 의 `files`), 시험 잡도 그 길을 탄다.
    """
    from agent.main import SUPPORTED_KINDS

    _job_id(_press(logged_in, "/setup/test/attach", file_name="a.pdf"))

    kinds = ",".join(SUPPORTED_KINDS)
    blind = logged_in.get("/api/agent/poll", params={"kinds": kinds, "files": 0},
                          headers=auth(DEMO_TOKEN))
    assert blind.status_code == 204, "파일을 못 붙이는 발송기가 시험 잡을 물었다"

    got = logged_in.get("/api/agent/poll", params={"kinds": kinds, "files": 1},
                        headers=auth(DEMO_TOKEN))
    assert got.status_code == 200
    body = got.json()
    assert body["kind"] == "test_send"
    assert body["items"][0]["room_name"] == TEST_ROOM
    assert body["items"][0]["files"] == ["a.pdf"]


def test_an_old_sender_does_not_pick_up_the_test_job(logged_in, rehearsal, may_attach):
    """이 종류를 모르는 발송기에는 **안 내려간다** — 큐에 그대로 선다.

    막히는 것이 아니라 서 있는 것이다. 발송기를 갱신하면 그다음 폴링에 이어
    나간다(`verify_room` 이 같은 이유로 같은 방식이다).
    """
    _job_id(_press(logged_in, "/setup/test/attach", file_name="a.pdf"))
    # 종류를 안 밝히는 구형 발송기 = 발송 잡만 받는다
    old = logged_in.get("/api/agent/poll", params={"files": 1}, headers=auth(DEMO_TOKEN))
    assert old.status_code == 204


def test_the_agent_knows_this_kind(rehearsal):
    """서버가 만드는 종류를 발송기가 안 받으면 잡이 큐에 멈춘다(소싱이 그랬다)."""
    from agent.main import SEND_KINDS, SUPPORTED_KINDS, TEST_KIND
    from app.models import TEST_SEND_KIND

    assert TEST_KIND == TEST_SEND_KIND
    assert TEST_KIND in SUPPORTED_KINDS
    assert TEST_KIND not in SEND_KINDS, "시험 잡은 발송 이력에 섞이면 안 된다"


# ══════════════════════════════════════════════════════════════════════════
#  ③ 방 이름 시험 — 아무것도 보내지 않는다
# ══════════════════════════════════════════════════════════════════════════

def test_the_room_test_borrows_the_existing_road(logged_in, rehearsal, db):
    """★ 새 길을 내지 않는다 — 이미 있는 `verify_room` 잡이다.

    각자 PC 에 깔려 도는 발송기가 그대로 처리하고(`process_verify_job`),
    진행 화면의 어휘도 이미 그 잡에 맞춰져 있다.
    """
    r = _press(logged_in, "/setup/test/room", room_name="가나스타트업 대표님")
    job = _jobs(db)[0]
    assert job.id == _job_id(r)
    assert job.kind == "verify_room"
    item = job.items[0]
    assert item.room_name == "가나스타트업 대표님"


def test_the_room_test_sends_nothing(logged_in, rehearsal, db):
    """★ 보낼 것이 **없어야** 한다 — 문구도, 파일도.

    아주 낡은 발송기가 이 잡을 발송으로 오해해도 보낼 내용이 없다
    (`routers/contacts.py: verify_rooms` 가 같은 이유로 같은 값을 넣는다).
    """
    _job_id(_press(logged_in, "/setup/test/room", room_name="아무방"))
    item = _jobs(db)[0].items[0]
    assert item.message == "", "확인 잡에 보낼 문구가 실렸다"
    assert item.files_json is None, "확인 잡에 파일이 실렸다"
    assert item.parts_json is None


def test_any_room_name_is_allowed_because_nothing_is_sent(logged_in, rehearsal, db):
    """명단에 없는 이름이어야 쓸모가 있다 — 스타트업 방은 아직 아무도 안 채웠다."""
    _job_id(_press(logged_in, "/setup/test/room", room_name="없는회사 팀장님"))
    assert _jobs(db)[0].items[0].contact_id is None


def test_the_room_test_searches_the_typed_name(logged_in, rehearsal):
    """담당자가 없으니 서버는 검색어를 따로 주지 않는다 →
    발송기가 **적어 넣은 방 이름 그대로** 검색한다(`agent/main.py`)."""
    from agent.main import SUPPORTED_KINDS

    _job_id(_press(logged_in, "/setup/test/room", room_name="가나스타트업 대표님"))
    got = logged_in.get("/api/agent/poll",
                        params={"kinds": ",".join(SUPPORTED_KINDS)},
                        headers=auth(DEMO_TOKEN)).json()
    item = got["items"][0]
    assert got["kind"] == "verify_room"
    assert "query" not in item and "name" not in item
    assert item["room_name"] == "가나스타트업 대표님" and item["message"] == ""


def test_the_room_test_result_touches_no_contact(logged_in, rehearsal, db, users):
    """결과가 남의 담당자 배지를 건드리면 안 된다 — 담당자가 없으니 건너뛴다."""
    from app.models import VcContact

    db.add(VcContact(user_id=users["u1"].id, name="홍길동", firm="가나벤처스",
                     kakao_room_name="아무방", room_verified="verified"))
    db.commit()

    from app.models import SendJob

    job_id = _job_id(_press(logged_in, "/setup/test/room", room_name="아무방"))
    job = db.get(SendJob, job_id)
    logged_in.post(f"/api/agent/items/{job.items[0].id}/result",
                   json={"status": "failed", "verify_result": "not_found"},
                   headers=auth(DEMO_TOKEN))
    db.expire_all()
    who = db.query(VcContact).filter_by(name="홍길동").first()
    assert who.room_verified == "verified", "시험이 담당자 배지를 건드렸다"


def test_an_empty_room_name_just_comes_back(logged_in, rehearsal, db):
    r = logged_in.post("/setup/test/room", data={"room_name": ""},
                       follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/setup?test=need_room"
    assert _jobs(db) == []


# ══════════════════════════════════════════════════════════════════════════
#  ④ 누가 쓸 수 있나 — `/setup` 의 결을 그대로 따른다
# ══════════════════════════════════════════════════════════════════════════

def test_you_have_to_be_logged_in(client, rehearsal, db):
    """로그인해야 `/setup` 이 열린다 — 시험용 자리도 같은 문 안에 있다."""
    r = client.post("/setup/test/room", data={"room_name": "아무방"},
                    follow_redirects=False)
    assert r.status_code == 303 and "/login" in r.headers["location"]
    assert _jobs(db) == []


def test_a_consultant_cannot_reach_it(client, db, rehearsal):
    """투자컨설턴트에게는 `/setup` 자체가 없다 — 새 규칙을 만들지 않는다."""
    from app.models import User
    from app.services import auth as auth_svc

    db.add(User(name="컨설턴트", phone="01000000007", role="consultant",
                password_hash=auth_svc.hash_password(DEMO_PASSWORD)))
    db.commit()
    client.post("/login", data={"phone": "01000000007", "password": DEMO_PASSWORD})

    r = client.post("/setup/test/room", data={"room_name": "아무방"},
                    follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/consulting"
    assert _jobs(db) == []


def test_the_file_test_needs_auto_attach(logged_in, rehearsal, db, users):
    """파일 시험은 **자료 자동 첨부를 켜 준 계정**만.

    발송기는 자료 폴더를 알아야 파일 이름을 실제 자리로 조립하는데, 그 폴더는
    켜진 계정에만 내려간다(`routers/agent_api.py: heartbeat`). 꺼진 계정에
    단추를 그려 두면 눌러 봐야 무조건 실패하고 고칠 자리도 없다.
    """
    from app.routers.setup import AUTO_ATTACH_BLOCKED

    assert not users["u1"].can_auto_attach_ir     # 기본값은 꺼짐
    html = logged_in.get("/setup").text
    assert THE_PANEL in html, "방 이름 시험은 누구나 쓴다"
    assert THE_FILE_FIELD not in html, "못 쓰는 사람에게 칸이 그려졌다"
    assert THE_ROOM_FIELD in html

    r = _press(logged_in, "/setup/test/attach", file_name="a.pdf")
    assert r.status_code == 403 and AUTO_ATTACH_BLOCKED in r.text
    assert _jobs(db) == [], "막혔는데 잡이 만들어졌다"


# ══════════════════════════════════════════════════════════════════════════
#  ⑤ ★ 오류 문구가 화면에 그대로 보인다 — 이것이 이 시험의 알맹이다
# ══════════════════════════════════════════════════════════════════════════
#
# 발송기가 보내기 직전에 거는 관문이 왜 막았는지를 문구에 담는다. 사람은 그
# 문구를 읽고 폴더나 파일 이름을 고친다 — 요약하거나 갈아 끼우면 고칠 수가 없다.

#: 발송기(`agent/sender/kakao_mac.py`·`kakao_windows.py`)가 만드는 실제 문구들.
GATE_ERRORS = [
    "시트에 없는 파일: '회사소개서.pdf' (시트에 있는 것: ['다른파일.pdf'])",
    "방이 다릅니다: 앞에 있는 창 '엉뚱한방' != 대상 '나와의 채팅'",
    "개수가 다릅니다: 시트는 2개인데 보내려던 것은 1개",
]


@pytest.mark.parametrize("gate_error", GATE_ERRORS)
def test_the_gate_error_shows_up_word_for_word(logged_in, rehearsal, may_attach,
                                               db, gate_error):
    """★ 발송기가 올린 사유가 진행 화면 자료에 **글자 그대로** 실린다."""
    from app.models import SendJob

    job_id = _job_id(_press(logged_in, "/setup/test/attach", file_name="회사소개서.pdf"))
    item_id = db.get(SendJob, job_id).items[0].id

    logged_in.post(f"/api/agent/items/{item_id}/result",
                   json={"status": "failed", "error": gate_error},
                   headers=auth(DEMO_TOKEN))

    shown = logged_in.get(f"/api/jobs/{job_id}").json()["items"][0]
    assert shown["status"] == "failed"
    assert shown["error"] == gate_error, "사유가 갈아 끼워졌다 — 고칠 수가 없다"


def test_the_progress_screen_prints_the_reason(logged_in, rehearsal, may_attach):
    """그 자료를 그리는 화면이 실제로 사유 칸을 가지고 있는가."""
    import pathlib

    job_id = _job_id(_press(logged_in, "/setup/test/attach", file_name="a.pdf"))
    html = logged_in.get(f"/jobs/{job_id}").text
    assert "사유 / 시각" in html

    js = pathlib.Path("app/static/js/progress.js").read_text(encoding="utf-8")
    assert "esc(i.error" in js, "사유를 화면에 적는 자리가 사라졌다"


def test_the_room_test_lands_on_the_verify_wording(logged_in, rehearsal):
    """방 이름 시험은 아무것도 안 보내므로 화면도 그렇게 말해야 한다."""
    job_id = _job_id(_press(logged_in, "/setup/test/room", room_name="아무방"))
    html = logged_in.get(f"/jobs/{job_id}").text
    assert "문구는 전송하지 않습니다" in html


# ══════════════════════════════════════════════════════════════════════════
#  ⑥ 시험 잡은 발송 이력·통계에 섞이지 않는다
# ══════════════════════════════════════════════════════════════════════════

def test_a_test_send_is_not_counted_as_a_send(client, db, users, rehearsal):
    """섞이면 숫자가 더러워진다 — 방 확인이 116건으로 찍혔던 그 자리다."""
    from datetime import date, timedelta

    from app.models import SendItem, SendJob, TEST_SEND_KIND
    from app.services import dashboard as dash

    today = date.today()
    monday = today - timedelta(days=today.weekday())
    when = monday.isoformat() + "T09:00:00+09:00"

    job = SendJob(user_id=users["u1"].id, kind=TEST_SEND_KIND, status="done",
                  total=1, sent=1, failed=0)
    db.add(job)
    db.flush()
    db.add(SendItem(job_id=job.id, room_name=TEST_ROOM, message="[시험]",
                    status="sent", sent_at=when))
    db.commit()

    kpi = next(k for k in dash.user_dashboard(db, users["u1"], top_n=10)["kpis"]
               if k["key"] == "sent")
    assert kpi["value"] == 0, "시험 발송이 이번 주 보낸 건수에 섞였다"


def test_the_counting_places_all_read_one_list(rehearsal):
    """세는 자리가 저마다 걸러 두면 한 곳이 빠진다 — 실제로 네 곳이 빠져 있었다."""
    from app.models import SEND_KINDS, TEST_SEND_KIND

    assert TEST_SEND_KIND not in SEND_KINDS
