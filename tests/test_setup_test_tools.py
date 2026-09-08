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


# ══════════════════════════════════════════════════════════════════════════
#  ⑦ 기업 리마인드 문구 시험 — **스타트업 화면과 같은 함수가 만든다**
# ══════════════════════════════════════════════════════════════════════════
#
# 같은 뜻의 문구가 **둘**이었다. 문구 화면의 `startup_sms`(기업 리마인드 —
# 문자)는 목록 없는 글을 냈고, 스타트업 메뉴의 카톡 문구 화면(#135)은 IR 자료를
# 요청한 투자사 목록을 붙인 글을 냈다. 둘 다 "요청한 투자사가 있다, 미팅이
# 잡히면 연락드리겠다" 를 그 기업 대표에게 알리는 글이다. 쓰는 사람은 어느
# 것을 보낼지 알 수 없었고, 언젠가 한쪽만 고쳐질 참이었다.
#
# 그래서 **하나로 모았다** — 짓는 자리는 `services/ir_kakao.py` 하나이고,
# `services/startup_msg.py` 는 지웠다. 머리말은 문구틀에서 오고 목록은 코드가
# 붙인다.
#
# 여기서 보는 것은 여섯이다.
#   ★ 시험 자리와 스타트업 화면이 **글자까지 같은 문구**를 낸다
#   ★ 머리말을 문구틀에서 고치면 **둘 다** 따라온다
#     시험방으로만 간다 — 고르는 것은 기업이지 방이 아니다
#     문구틀이 비어 있으면 **기본 머리말**로 짓고, 그 사실을 화면이 적는다
#     요청이 0곳이면 **아무것도 만들지 않는다**(빈 목록은 안 보낸다)
#     가려진 투자사명이 시험방으로도 안 샌다

THE_COMPANY_FIELD = 'name="company_id"'
REMIND = "/setup/test/startup-remind"

#: 전부 지어낸 이름이다 — 이 저장소는 공개다.
THE_FIRM = "가나벤처스"


def _this_month() -> str:
    from app import clock

    return clock.today().strftime("%Y-%m")


@pytest.fixture()
def a_company(db, users):
    """시험에 쓸 스타트업 한 곳 — **계약을 마쳤고 요청이 한 건 있다.**

    둘 다 있어야 문구가 만들어진다(`ir_kakao.for_company`). 계약을 안 했거나
    요청이 0곳이면 짓지 않는 것이 이 저장소의 결이다(#131 · #135).
    """
    from app.models import IrCompany, IrRequest, VcContact

    row = IrCompany(name="샘플애그", contact_name="홍길동", contract_status="paid")
    firm = VcContact(user_id=1, name="김심사", firm=THE_FIRM)
    db.add_all([row, firm])
    db.flush()
    db.add(IrRequest(user_id=1, contact_id=firm.id, company_id=row.id,
                     company_name=row.name,
                     requested_at=f"{_this_month()}-03"))
    db.commit()
    return row


@pytest.fixture()
def a_template(db):
    """팀 기본 `startup_sms` 문구 하나 — **머리말만** 담는다.

    목록은 문구틀이 아니라 코드가 붙인다. 여기에는 머리말이 쓰는 자리
    (`{달}`·`{기업들}`)와, 옛 문구가 쓰던 자리(`{담당자명}` …)를 함께 담아
    **글자 그대로 새는 `{…}` 가 없는지**까지 함께 본다.
    """
    from app.models import MessageTemplate

    row = MessageTemplate(
        user_id=None, kind="startup_sms", name="기본",
        body=("안녕하세요 {담당자명} {직함}\n"
              "{달} 말까지 {기업들}\n"
              "IR 자료 요청한투자사 리스트 입니다.\n"
              "투자사: {투자사}/ 개수: {개수}/ 목록: {기업목록}/ 링크: {자료링크}"),
        is_active=1)
    db.add(row)
    db.commit()
    return row


def _sole_item(db):
    from app.models import SendItem

    items = db.query(SendItem).order_by(SendItem.id).all()
    assert len(items) == 1, items
    return items[0]


def _screen_text(client, company_id: int) -> str:
    """스타트업 화면이 보여 주는 문구 전문 — 화면에 실제로 박힌 글자 그대로."""
    import re

    r = client.get(f"/startup/ir-kakao/{company_id}")
    assert r.status_code == 200, r.status_code
    body = re.search(r'id="ir-kakao-message"[^>]*>(.*?)</textarea>', r.text,
                     re.S)
    assert body, "화면에 문구 칸이 없다"
    return body.group(1)


def test_the_remind_test_is_gone_without_a_test_room(logged_in, db, a_company,
                                                     a_template):
    """★ 안전선은 하나다 — 시험방이 없으면 화면에도 없고 주소로도 없다."""
    assert THE_COMPANY_FIELD not in logged_in.get("/setup").text
    r = _press(logged_in, REMIND, company_id=a_company.id)
    assert r.status_code == 404
    assert _jobs(db) == []


def test_the_remind_test_appears_with_the_company_picker(logged_in, rehearsal,
                                                         a_company, a_template):
    html = logged_in.get("/setup").text
    assert THE_COMPANY_FIELD in html
    assert a_company.name in html, "고를 기업이 목록에 없다"


def test_the_picker_lists_every_company(logged_in, rehearsal, db, a_company,
                                        a_template):
    """**거르지 않는다.** 누구에게 보내는가는 이번에 정하는 일이 아니고,
    담당자 성함이 빈 줄이야말로 문구가 어떻게 나가는지 봐야 할 줄이다."""
    from app.models import IrCompany

    db.add(IrCompany(name="이름없는곳", contact_name=None, contract_status="none"))
    db.commit()
    html = logged_in.get("/setup").text
    assert "이름없는곳" in html


def test_the_remind_goes_to_the_test_room_only(logged_in, rehearsal, db,
                                               a_company, a_template):
    """방을 고르는 칸이 아예 없다 — 밀어 넣어도 시험방으로 간다."""
    r = logged_in.post(REMIND,
                       data={"company_id": a_company.id, "room_name": "엉뚱한방"},
                       follow_redirects=False)
    _job_id(r)
    assert _sole_item(db).room_name == TEST_ROOM


def test_the_test_and_the_startup_screen_say_the_same_thing(logged_in, rehearsal,
                                                            db, a_company,
                                                            a_template):
    """★ 이 일의 알맹이 — 두 자리가 **글자 하나까지 같은 문구**를 낸다.

    갈리면 시험이 거짓말을 한다: 여기서 본 글과 대표가 받을 글이 달라진다.
    """
    import html as html_mod

    _job_id(_press(logged_in, REMIND, company_id=a_company.id))
    sent = _sole_item(db).message
    shown = html_mod.unescape(_screen_text(logged_in, a_company.id))
    assert sent == shown, f"시험 자리와 화면이 다른 글을 낸다\n{sent!r}\n{shown!r}"


def test_the_headline_comes_from_the_template_for_both(logged_in, rehearsal, db,
                                                       a_company, a_template):
    """★ 머리말을 문구 화면에서 고치면 **두 자리가 함께** 바뀐다."""
    import html as html_mod

    a_template.body = "고쳐 적은 머리말\n{달} 말까지 {기업들}"
    db.commit()

    _job_id(_press(logged_in, REMIND, company_id=a_company.id))
    sent = _sole_item(db).message
    assert sent.startswith("고쳐 적은 머리말\n")
    assert html_mod.unescape(_screen_text(logged_in, a_company.id)) == sent


def test_the_list_is_added_by_the_code_not_the_template(logged_in, rehearsal, db,
                                                        a_company, a_template):
    """머리말만 고쳐 적어도 **목록은 붙는다** — 목록은 문구틀 몫이 아니다."""
    from app.services import ir_mask

    a_template.body = "머리말 한 줄뿐"
    db.commit()
    _job_id(_press(logged_in, REMIND, company_id=a_company.id))
    sent = _sole_item(db).message
    assert sent.startswith("머리말 한 줄뿐\n\n")
    assert ir_mask.mask_company(THE_FIRM) in sent, "요청 목록이 안 붙었다"


def test_the_month_and_the_companies_are_filled_by_the_code(logged_in, rehearsal,
                                                            db, a_company,
                                                            a_template):
    """`{달}`·`{기업들}` 은 자료라 코드가 채운다 — 사람이 갈아 끼우지 않는다."""
    from app.services import ir_kakao

    _job_id(_press(logged_in, REMIND, company_id=a_company.id))
    sent = _sole_item(db).message
    assert f"{ir_kakao.month_label(_this_month())} 말까지 {a_company.name}" in sent


def test_no_substitution_is_left_behind(logged_in, rehearsal, db, a_company,
                                        a_template):
    """`{…}` 가 **글자 그대로** 나간 사고를 이 저장소는 이미 겪었다.

    운영에 저장돼 있던 옛 문구가 `{담당자명}` 을 쓰고 있으므로, 머리말을
    문구틀로 옮긴 뒤에도 그 자리는 여전히 채워져야 한다.
    """
    _job_id(_press(logged_in, REMIND, company_id=a_company.id))
    sent = _sole_item(db).message
    assert "안녕하세요 홍길동님" in sent, "옛 문구의 자리가 안 채워졌다"
    assert "{" not in sent and "}" not in sent


def test_the_masked_firm_never_leaks_into_the_test_room(logged_in, rehearsal, db,
                                                        a_company, a_template):
    """가리는 자리는 `ir_mask` 하나다 — 시험 길로 샌다면 가린 것이 아니다."""
    from app.services import ir_mask

    _job_id(_press(logged_in, REMIND, company_id=a_company.id))
    sent = _sole_item(db).message
    assert THE_FIRM not in sent
    assert ir_mask.mask_company(THE_FIRM) in sent


def test_an_empty_template_still_makes_the_message(logged_in, rehearsal, db,
                                                   a_company):
    """문구틀이 비어 있으면 **코드에 적힌 머리말**로 짓는다.

    #133 은 반대로 막았지만, 그 판단을 그대로 두면 스타트업 화면이 404 가 된다 —
    요청이 실제로 와 있는데 "요청이 없다" 는 뜻의 안내가 뜬다. 대신 화면이
    **기본 머리말로 지었다**고 적는다.
    """
    from app.services import ir_kakao

    _job_id(_press(logged_in, REMIND, company_id=a_company.id))
    sent = _sole_item(db).message
    assert sent.startswith(ir_kakao.HELLO)
    assert ir_kakao.LEAD in sent

    html = logged_in.get(f"/startup/ir-kakao/{a_company.id}").text
    assert "기본 머리말" in html, "문구틀이 빈 줄 모르고 지나간다"
    assert "/templates#startup_sms" in html, "고칠 자리로 가는 고리가 없다"


def test_a_whitespace_only_template_counts_as_empty(logged_in, rehearsal, db,
                                                    a_company):
    from app.models import MessageTemplate
    from app.services import ir_kakao

    db.add(MessageTemplate(user_id=None, kind="startup_sms", name="빈 것",
                           body="   \n  ", is_active=1))
    db.commit()
    _job_id(_press(logged_in, REMIND, company_id=a_company.id))
    assert _sole_item(db).message.startswith(ir_kakao.HELLO)


def test_a_company_with_no_requests_makes_nothing(logged_in, rehearsal, db,
                                                  a_template):
    """요청이 0곳이면 **잡을 만들지 않는다** — 빈 목록을 보내면 받는 대표는
    우리가 아무것도 안 한 줄로 읽는다."""
    from app.models import IrCompany
    from app.routers.setup import TEST_INPUT_MISSING

    company = IrCompany(name="조용한곳", contract_status="paid")
    db.add(company)
    db.commit()

    r = _press(logged_in, REMIND, company_id=company.id)
    assert r.status_code == 303
    assert r.headers["location"] == "/setup?test=no_requests"
    assert _jobs(db) == []
    assert TEST_INPUT_MISSING["no_requests"] in logged_in.get(
        "/setup?test=no_requests").text


def test_a_company_without_a_contract_makes_nothing(logged_in, rehearsal, db,
                                                    a_company, a_template):
    """계약을 안 마친 기업도 같은 길이다 — 판정은 `ir_kakao` 한 곳이 한다."""
    a_company.contract_status = "none"
    db.commit()
    r = _press(logged_in, REMIND, company_id=a_company.id)
    assert r.headers["location"] == "/setup?test=no_requests"
    assert _jobs(db) == []


def test_a_long_message_is_sent_in_parts(logged_in, rehearsal, db, a_company,
                                          a_template):
    """한 통에 안 들어가면 **나뉜 채로** 나간다 — 합쳐 보내면 실제로는 잘린다."""
    from app.models import IrRequest, VcContact

    for i in range(400):
        firm = VcContact(user_id=1, name="김심사",
                         firm=f"마바사아자캐피탈파트너스{i}")
        db.add(firm)
        db.flush()
        db.add(IrRequest(user_id=1, contact_id=firm.id, company_id=a_company.id,
                         company_name=a_company.name,
                         requested_at=f"{_this_month()}-05"))
    db.commit()

    _job_id(_press(logged_in, REMIND, company_id=a_company.id))
    item = _sole_item(db)
    assert item.parts_json, "여러 통인데 나눠 보내지 않는다"
    assert len(json.loads(item.parts_json)) > 1


def test_a_short_message_carries_no_parts(logged_in, rehearsal, db, a_company,
                                          a_template):
    """한 통이면 `parts_json` 은 비운다 — `SendItem` 이 정해 둔 약속이다."""
    _job_id(_press(logged_in, REMIND, company_id=a_company.id))
    assert _sole_item(db).parts_json is None


def test_no_company_picked_just_comes_back(logged_in, rehearsal, db, a_template):
    from app.routers.setup import TEST_INPUT_MISSING

    r = _press(logged_in, REMIND, company_id="")
    assert r.headers["location"] == "/setup?test=need_company"
    assert _jobs(db) == []
    assert TEST_INPUT_MISSING["need_company"] in logged_in.get(
        "/setup?test=need_company").text


def test_a_company_that_is_not_there_makes_nothing(logged_in, rehearsal, db,
                                                   a_template):
    r = _press(logged_in, REMIND, company_id=99999)
    assert r.headers["location"] == "/setup?test=need_company"
    assert _jobs(db) == []


def test_the_remind_carries_no_files(logged_in, rehearsal, db, a_company,
                                     a_template):
    """파일을 안 붙이므로 **파일 못 붙이는 발송기도** 이 잡을 집어간다."""
    _job_id(_press(logged_in, REMIND, company_id=a_company.id))
    assert _sole_item(db).files_json is None

    from agent.main import SUPPORTED_KINDS

    r = logged_in.get("/api/agent/poll",
                      params={"kinds": ",".join(SUPPORTED_KINDS), "files": 0},
                      headers=auth(DEMO_TOKEN))
    assert r.status_code == 200, "파일이 없는데도 안 내려갔다"
    assert r.json()["kind"] == "test_send"


def test_the_remind_does_not_need_auto_attach(logged_in, rehearsal, db, users,
                                              a_company, a_template):
    """파일을 안 붙이는데 자료 폴더 권한으로 막으면 없는 이유로 막는 것이다."""
    assert not users["u1"].can_auto_attach_ir
    html = logged_in.get("/setup").text
    assert THE_FILE_FIELD not in html, "파일 시험은 여전히 그 계정만"
    assert THE_COMPANY_FIELD in html
    _job_id(_press(logged_in, REMIND, company_id=a_company.id))


def test_the_remind_reuses_the_test_kind(logged_in, rehearsal, db, a_company,
                                         a_template):
    """새 잡 종류를 만들지 않는다 — 만들면 발송기를 갱신할 때까지 큐에 선다.
    `SEND_KINDS` 에 없는 종류라 이력·통계에도 저절로 안 섞인다."""
    from app.models import SEND_KINDS, TEST_SEND_KIND

    _job_id(_press(logged_in, REMIND, company_id=a_company.id))
    assert _jobs(db)[0].kind == TEST_SEND_KIND
    assert TEST_SEND_KIND not in SEND_KINDS


def test_the_remind_job_belongs_to_whoever_pressed_it(logged_in, rehearsal, db,
                                                      users, a_company,
                                                      a_template):
    _job_id(_press(logged_in, REMIND, company_id=a_company.id))
    assert _jobs(db)[0].user_id == users["u1"].id


def test_you_have_to_be_logged_in_for_the_remind(client, rehearsal, db,
                                                 a_company, a_template):
    r = client.post(REMIND, data={"company_id": a_company.id},
                    follow_redirects=False)
    assert r.status_code == 303 and "/login" in r.headers["location"]
    assert _jobs(db) == []


def test_a_consultant_cannot_reach_the_remind(client, db, rehearsal, a_company,
                                              a_template):
    from app.models import User
    from app.services import auth as auth_svc

    db.add(User(name="컨설턴트", phone="01000000007", role="consultant",
                password_hash=auth_svc.hash_password(DEMO_PASSWORD)))
    db.commit()
    client.post("/login", data={"phone": "01000000007", "password": DEMO_PASSWORD})

    r = client.post(REMIND, data={"company_id": a_company.id},
                    follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/consulting"
    assert _jobs(db) == []


def test_there_is_only_one_composer(rehearsal):
    """★ **짓는 자리가 하나다.** 두 벌이 남으면 이번에 모은 뜻이 없다.

    - `services/startup_msg.py` 는 없다(#133 이 냈던 파일이다).
    - 시험 자리도 스타트업 화면도 `ir_kakao` 를 부르고, 제 손으로 조립하지 않는다.
    """
    import inspect
    import pathlib

    from app.routers import setup as setup_router
    from app.routers import startup as startup_router
    from app.services import ir_kakao

    root = pathlib.Path(__file__).resolve().parent.parent
    assert not (root / "app" / "services" / "startup_msg.py").exists(), \
        "목록 없는 옛 문구를 짓는 자리가 남아 있다"

    assert ir_kakao.KIND == "startup_sms"
    for fn in (setup_router.test_startup_remind, startup_router.ir_kakao_message):
        src = inspect.getsource(fn)
        assert "ir_kakao." in src, "짓는 자리를 안 지난다"
        assert "render_template" not in src and "compose_message" not in src, \
            "화면이 제 손으로 문구를 조립한다"


# ══════════════════════════════════════════════════════════════════════════
#  ⑧ 미팅 후기 문구 시험 — **받는 사람이 투자사다**
# ══════════════════════════════════════════════════════════════════════════
#
# 바로 위 기업 리마인드는 **스타트업**으로 나가고, 이것은 미팅을 마친
# **투자사**로 나간다. 나란히 선 두 단추가 서로 반대쪽 명단을 향하므로,
# 화면에서 그 차이가 보이는지도 여기서 함께 본다.
#
# 여기도 짓는 자리를 새로 만들지 않았다 — `meeting_review` 는 **발송 화면의
# 미팅 후기 탭**이 이미 짓는다. 그래서 그 길을 부른다. 위 기업 리마인드가
# 두 벌을 두었다가 하나로 모은 자리다.
#
# 보는 것은 여섯이다.
#   ★ 시험방이 없으면 이 자리도 없다(① 과 같은 안전선)
#     시험방으로만 간다 — 고르는 것은 미팅이지 방이 아니다
#     문구틀이 만든 것과 **글자 하나까지** 같다(발송 화면과 같은 길)
#     문구틀이 비어 있을 때 — 여기서는 **막지 않는다**(발송 화면이 폴백을 보낸다)
#     존칭이 겹치지 않는다 — `대리 심사역 심사역님` 을 고쳐 온 자리다
#     시험 잡이 발송 이력·통계에 안 섞인다

THE_MEETING_FIELD = 'name="meeting_id"'
REVIEW = "/setup/test/meeting-review"


def _days_ago(n: int) -> str:
    from datetime import date, timedelta

    return (date.today() - timedelta(days=n)).isoformat()


@pytest.fixture()
def an_investor(db, users):
    """미팅을 한 투자사 담당자. **문구에 꽂히는 값은 이 셋뿐이다.**"""
    from app.models import VcContact

    row = VcContact(user_id=users["u1"].id, name="김영주", title="심사역",
                    firm="가나벤처스")
    db.add(row)
    db.commit()
    return row


@pytest.fixture()
def a_meeting(db, users, an_investor):
    """끝난 미팅 한 건 — 결과 문의 날짜가 이미 지났다(`followup_due_now`)."""
    from app.models import Meeting

    row = Meeting(user_id=users["u1"].id, contact_id=an_investor.id,
                  scheduled_at=_days_ago(15), kind="first", status="done",
                  done_at=_days_ago(15), outcome="reviewing",
                  followup_due=_days_ago(5), followup_done=0)
    db.add(row)
    db.commit()
    return row


@pytest.fixture()
def a_review_template(db):
    """팀 기본 `meeting_review` 문구. 바꿔치기 자리를 전부 담아 둔다."""
    from app.models import MessageTemplate

    row = MessageTemplate(
        user_id=None, kind="meeting_review", name="기본",
        body=("{투자사} {담당자명} {직함}, 지난번 미팅은 어떻게 보셨는지요?\n"
              "기업명: {기업명}/ 개수: {개수}/ 목록: {기업목록}/ 링크: {자료링크}"),
        is_active=1)
    db.add(row)
    db.commit()
    return row


def test_the_review_test_is_gone_without_a_test_room(logged_in, db, a_meeting,
                                                     a_review_template):
    """★ 안전선은 하나다 — 시험방이 없으면 화면에도 없고 주소로도 없다."""
    assert THE_MEETING_FIELD not in logged_in.get("/setup").text
    r = _press(logged_in, REVIEW, meeting_id=a_meeting.id)
    assert r.status_code == 404
    assert _jobs(db) == []


def test_the_review_test_appears_with_the_meeting_picker(logged_in, rehearsal,
                                                         a_meeting, an_investor,
                                                         a_review_template):
    html = logged_in.get("/setup").text
    assert THE_MEETING_FIELD in html
    # 누구에게 갈 문구인지가 고르개에 적혀 있어야 한다.
    assert an_investor.name in html and an_investor.firm in html


def test_the_screen_says_which_list_each_message_goes_to(logged_in, rehearsal,
                                                         a_meeting, a_company,
                                                         a_template,
                                                         a_review_template):
    """★ 두 문구 시험이 **반대쪽 명단**으로 간다는 것이 화면에 보여야 한다.

    나란히 선 단추라 제목만으로는 구별이 안 된다. 헷갈려서 반대로 누르면
    시험방으로 가긴 하지만 **시험이 거짓말을 한다** — 스타트업에게 갈 문구를
    보고 투자사에게 갈 문구라고 믿는다.
    """
    html = logged_in.get("/setup").text
    assert "받는 사람 → 스타트업" in html
    assert "받는 사람 → 투자사" in html
    assert "스타트업에게 가는 문구가 아닙니다" in html


def test_the_review_goes_to_the_test_room_only(logged_in, rehearsal, db,
                                               a_meeting, a_review_template):
    """방을 고르는 칸이 아예 없다 — 밀어 넣어도 시험방으로 간다."""
    r = logged_in.post(REVIEW,
                       data={"meeting_id": a_meeting.id, "room_name": "진짜투자사방"},
                       follow_redirects=False)
    _job_id(r)
    assert _sole_item(db).room_name == TEST_ROOM


def test_the_review_sends_what_the_send_screen_would_send(logged_in, rehearsal,
                                                          db, users, a_meeting,
                                                          an_investor,
                                                          a_review_template):
    """★ 이 시험의 알맹이 — 발송 화면의 **미팅 후기 탭이 보내는 그 문구**다.

    앞에 머리말 한 줄도 얹지 않는다. 얹으면 실제로 나갈 모양을 볼 수 없다.
    """
    from app.routers import deals as deals_view

    _job_id(_press(logged_in, REVIEW, meeting_id=a_meeting.id))
    made = deals_view.review_message(db, users["u1"], an_investor)
    assert _sole_item(db).message == made


def test_which_slots_get_filled_and_which_stay_blank(db, users, an_investor,
                                                     a_review_template):
    """문구틀의 자리마다 무엇이 들어가나 — 이 판단이 곧 문구의 모양이다.

    월말 리마인드와 **반대**다. 받는 쪽이 투자사라 `{투자사}` 가 채워진다.
    """
    from app.routers import deals as deals_view

    text = deals_view.review_message(db, users["u1"], an_investor)
    # 채워지는 셋 — 받는 사람에서 온다.
    assert "가나벤처스" in text
    assert "김영주" in text
    assert "심사역님" in text
    # 기업을 고르지 않는 방식이라 기업 쪽 자리는 빈칸이다.
    # **`{개수}` 만 다르다** — 고른 기업 수가 `0` 으로 적힌다(빈칸이 아니다).
    assert "기업명: / 개수: 0/ 목록: / 링크:" in text
    # 무엇보다 **바꿔치기가 남지 않는다** — `{…}` 가 그대로 나간 사고가 있었다.
    assert "{" not in text and "}" not in text


def test_the_greeting_comes_along(db, users, an_investor, a_review_template):
    """발송 화면이 인사말을 붙이므로(`opening_is_included`) 여기도 붙는다.

    문구만 보내면 사람은 인사말이 빠진 줄 모르고 문구틀에 인사를 또 적는다.
    """
    from app.routers import deals as deals_view

    text = deals_view.review_message(db, users["u1"], an_investor)
    assert text.startswith("안녕하세요")
    assert deals_view.opening_is_included(deals_view.MODE_REVIEW)


def test_the_honorific_is_not_doubled(db, users, a_review_template):
    """★ `대리 심사역 심사역님` 을 고쳐 온 자리다 — 존칭이 겹치면 안 된다."""
    from app.models import VcContact
    from app.routers import deals as deals_view

    # ① 직함에 '님' 이 이미 붙어 있다
    already = VcContact(user_id=users["u1"].id, name="한지우", title="대표님",
                        firm="다라벤처스")
    # ② 이름 칸에 직함이 섞여 있다 — 여기에 직함을 또 붙이면 겹친다
    carried = VcContact(user_id=users["u1"].id, name="최가온 대리 심사역",
                        title="심사역", firm="마바벤처스")
    # ③ 직함이 비어 있다 — '님' 만 붙고 앞 공백이 지워진다
    bare = VcContact(user_id=users["u1"].id, name="박하늘", title="", firm="사아벤처스")
    db.add_all([already, carried, bare])
    db.commit()

    for who in (already, carried, bare):
        text = deals_view.review_message(db, users["u1"], who)
        assert "님님" not in text, text
        assert " 님" not in text, text
    assert "한지우 대표님" in deals_view.review_message(db, users["u1"], already)
    assert "최가온 대리 심사역님" in deals_view.review_message(db, users["u1"], carried)
    assert "심사역 심사역님" not in deals_view.review_message(db, users["u1"], carried)
    assert "박하늘님" in deals_view.review_message(db, users["u1"], bare)


def test_an_empty_template_still_shows_what_goes_out_today(logged_in, rehearsal,
                                                           db, users, a_meeting,
                                                           an_investor):
    """★ 문구틀이 없어도 **막지 않는다** — 월말 리마인드와 반대다.

    월말 리마인드는 보내는 코드가 아예 없어서 "문구틀에 적으라" 고 되돌려
    보낸다. 여기는 발송 화면이 **문구틀이 없어도 코드에 적힌 한 문장을
    실제로 내보낸다**(`FOLLOW_UP_MODES` 의 폴백). 저장소 기본 시드에도
    `meeting_review` 문구가 없으니, 지금 나가는 것이 바로 그 폴백이다 —
    여기서 막으면 오늘 실제로 나가는 문구를 볼 자리가 없어진다.
    """
    from app.models import MessageTemplate
    from app.routers.deals import FOLLOW_UP_MODES, MODE_REVIEW

    assert db.query(MessageTemplate).filter_by(kind="meeting_review").count() == 0
    _job_id(_press(logged_in, REVIEW, meeting_id=a_meeting.id))
    text = _sole_item(db).message
    assert FOLLOW_UP_MODES[MODE_REVIEW][1] in text, "발송 화면과 다른 문구가 나갔다"
    assert "{" not in text and "}" not in text


def test_the_picker_is_not_narrowed_to_due_followups(logged_in, rehearsal, db,
                                                     users, an_investor,
                                                     a_meeting):
    """**거르지 않는다.**

    문구는 미팅을 읽지 않는다(이름·직함·투자사 셋뿐이다) — 걸러도 나오는 글자가
    같다. 그런데 거르면 발송기를 새 PC 에 깔 때 고르개가 비어 버린다. 대신
    결과 문의 차례인 것에 표를 달아 위로 올린다.
    """
    from app.models import Meeting, VcContact

    other = VcContact(user_id=users["u1"].id, name="정다래", title="팀장",
                      firm="자차벤처스")
    db.add(other)
    db.flush()
    # 아직 안 끝난 미팅 — 결과 문의 차례가 아니다
    db.add(Meeting(user_id=users["u1"].id, contact_id=other.id,
                   scheduled_at=_days_ago(-3), kind="first", status="scheduled"))
    db.commit()

    html = logged_in.get("/setup").text
    assert "정다래" in html, "결과 문의 차례가 아니라고 목록에서 빠졌다"
    # 차례인 것이 먼저 오고, 그 표가 붙는다.
    assert "[결과 문의 차례] 김영주" in html
    assert html.index("김영주") < html.index("정다래")


def test_the_due_mark_reads_the_one_judgment(db, users, a_meeting):
    """밀렸는지는 여기서 새로 재지 않는다 — 대시보드와 같은 값을 읽는다."""
    from app.routers.setup import _test_meetings
    from app.services import pipeline

    due_ids = {m["id"] for m in pipeline.today_items(db, users["u1"])["due_followups"]}
    marked = {m["id"] for m in _test_meetings(db, users["u1"]) if m["due"]}
    assert marked == due_ids


def test_a_meeting_pointing_at_someone_elses_contact_is_not_offered(
        logged_in, rehearsal, db, users, a_meeting):
    """내 미팅이라도 **담당자가 내 명단에 없으면** 안 그린다.

    문구는 담당자에서 나온다. 남의 명단에 있는 사람으로 문구를 만들면 그 사람의
    이름·투자사가 내 시험방에 실려 나간다 — 시험방이라도 남의 자료다.
    """
    from app.models import Meeting, VcContact

    theirs = VcContact(user_id=users["u2"].id, name="남의담당", title="심사역",
                       firm="남의벤처스")
    db.add(theirs)
    db.flush()
    crossed = Meeting(user_id=users["u1"].id, contact_id=theirs.id,
                      scheduled_at=_days_ago(2), kind="first", status="done",
                      done_at=_days_ago(2), followup_due=_days_ago(1))
    db.add(crossed)
    db.commit()

    assert "남의담당" not in logged_in.get("/setup").text
    r = _press(logged_in, REVIEW, meeting_id=crossed.id)
    assert r.headers["location"] == "/setup?test=need_meeting"
    assert _jobs(db) == []


def test_a_meeting_that_is_not_there_makes_nothing(logged_in, rehearsal, db,
                                                   a_review_template):
    r = _press(logged_in, REVIEW, meeting_id=99999)
    assert r.headers["location"] == "/setup?test=need_meeting"
    assert _jobs(db) == []


def test_someone_elses_meeting_makes_nothing(logged_in, rehearsal, db, users):
    """남의 미팅으로는 만들 수 없다 — 그 사람의 담당자 이름이 실려 나간다."""
    from app.models import Meeting, VcContact

    theirs = VcContact(user_id=users["u2"].id, name="남의담당", title="심사역",
                       firm="남의벤처스")
    db.add(theirs)
    db.flush()
    meeting = Meeting(user_id=users["u2"].id, contact_id=theirs.id,
                      scheduled_at=_days_ago(9), kind="first", status="done",
                      done_at=_days_ago(9), followup_due=_days_ago(1))
    db.add(meeting)
    db.commit()

    assert "남의담당" not in logged_in.get("/setup").text
    r = _press(logged_in, REVIEW, meeting_id=meeting.id)
    assert r.headers["location"] == "/setup?test=need_meeting"
    assert _jobs(db) == []


def test_no_meeting_picked_just_comes_back(logged_in, rehearsal, db, a_meeting):
    from app.routers.setup import TEST_INPUT_MISSING

    r = _press(logged_in, REVIEW, meeting_id="")
    assert r.headers["location"] == "/setup?test=need_meeting"
    assert _jobs(db) == []
    assert TEST_INPUT_MISSING["need_meeting"] in logged_in.get(
        "/setup?test=need_meeting").text


def test_the_review_carries_no_files(logged_in, rehearsal, db, a_meeting,
                                     a_review_template):
    """파일을 안 붙이므로 **파일 못 붙이는 발송기도** 이 잡을 집어간다."""
    _job_id(_press(logged_in, REVIEW, meeting_id=a_meeting.id))
    assert _sole_item(db).files_json is None

    from agent.main import SUPPORTED_KINDS

    r = logged_in.get("/api/agent/poll",
                      params={"kinds": ",".join(SUPPORTED_KINDS), "files": 0},
                      headers=auth(DEMO_TOKEN))
    assert r.status_code == 200, "파일이 없는데도 안 내려갔다"
    assert r.json()["kind"] == "test_send"


def test_the_review_does_not_need_auto_attach(logged_in, rehearsal, db, users,
                                              a_meeting, a_review_template):
    """파일을 안 붙이는데 자료 폴더 권한으로 막으면 없는 이유로 막는 것이다."""
    assert not users["u1"].can_auto_attach_ir
    html = logged_in.get("/setup").text
    assert THE_FILE_FIELD not in html, "파일 시험은 여전히 그 계정만"
    assert THE_MEETING_FIELD in html
    _job_id(_press(logged_in, REVIEW, meeting_id=a_meeting.id))


def test_the_review_reuses_the_test_kind(logged_in, rehearsal, db, a_meeting,
                                         a_review_template):
    """새 잡 종류를 만들지 않는다 — 만들면 발송기를 갱신할 때까지 큐에 선다.
    `SEND_KINDS` 에 없는 종류라 이력·통계에도 저절로 안 섞인다."""
    from app.models import SEND_KINDS, TEST_SEND_KIND

    _job_id(_press(logged_in, REVIEW, meeting_id=a_meeting.id))
    assert _jobs(db)[0].kind == TEST_SEND_KIND
    assert TEST_SEND_KIND not in SEND_KINDS


def test_the_review_is_not_counted_as_a_send(logged_in, rehearsal, db, users,
                                             a_meeting, a_review_template):
    """★ 섞이면 숫자가 더러워진다 — 방 확인이 116건으로 찍혔던 그 자리다."""
    from app.services import dashboard as dash

    _job_id(_press(logged_in, REVIEW, meeting_id=a_meeting.id))
    item = _sole_item(db)
    item.status = "sent"
    from app.deps import now_iso

    item.sent_at = now_iso()
    db.commit()

    kpi = next(k for k in dash.user_dashboard(db, users["u1"], top_n=10)["kpis"]
               if k["key"] == "sent")
    assert kpi["value"] == 0, "시험 발송이 이번 주 보낸 건수에 섞였다"


def test_the_review_does_not_touch_the_meeting(logged_in, rehearsal, db,
                                               a_meeting, a_review_template):
    """시험은 **아무것도 적지 않는다** — 결과를 물었다고 표시하면 안 된다.

    실제로 물어본 것이 아닌데 `followup_done` 이 서면 그 미팅은 목록에서 사라져
    아무도 결과를 안 묻게 된다.
    """
    from app.models import Meeting

    _job_id(_press(logged_in, REVIEW, meeting_id=a_meeting.id))
    db.expire_all()
    row = db.get(Meeting, a_meeting.id)
    assert not row.followup_done and not row.followup_at and not row.followup_note


def test_the_review_job_belongs_to_whoever_pressed_it(logged_in, rehearsal, db,
                                                      users, a_meeting,
                                                      a_review_template):
    _job_id(_press(logged_in, REVIEW, meeting_id=a_meeting.id))
    assert _jobs(db)[0].user_id == users["u1"].id


def test_you_have_to_be_logged_in_for_the_review(client, rehearsal, db, a_meeting,
                                                 a_review_template):
    r = client.post(REVIEW, data={"meeting_id": a_meeting.id},
                    follow_redirects=False)
    assert r.status_code == 303 and "/login" in r.headers["location"]
    assert _jobs(db) == []


def test_a_consultant_cannot_reach_the_review(client, db, rehearsal, a_meeting,
                                              a_review_template):
    from app.models import User
    from app.services import auth as auth_svc

    db.add(User(name="컨설턴트", phone="01000000007", role="consultant",
                password_hash=auth_svc.hash_password(DEMO_PASSWORD)))
    db.commit()
    client.post("/login", data={"phone": "01000000007", "password": DEMO_PASSWORD})

    r = client.post(REVIEW, data={"meeting_id": a_meeting.id},
                    follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/consulting"
    assert _jobs(db) == []


def test_the_composer_is_the_send_screens_own(rehearsal):
    """★ 짓는 자리를 **새로 만들지 않았다.**

    `meeting_review` 는 발송 화면이 이미 짓는다. 그 길을 부를 수 있게 입구만
    냈다 — 여기서 다시 조립하면 두 벌이 되고, 두 벌은 반드시 어긋난다
    (기업 리마인드가 그 값을 치른 자리다).
    """
    import inspect

    from app.routers import deals as deals_view
    from app.routers import setup as setup_router

    assert callable(deals_view.review_message)
    assert deals_view.MODE_TEMPLATE_KIND[deals_view.MODE_REVIEW] == "meeting_review"
    src = inspect.getsource(setup_router.test_meeting_review)
    assert "review_message" in src
    assert "compose_message" not in src and "render_template" not in src
