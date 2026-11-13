"""투자사 [방 연결 확인] — 찾은 방 후보를 눌러 방 이름에 넣고 그 분만 다시 확인 (11/13).

사용자: "방 찾기를 했을 때 찾아진 방이 있잖아? 그 방 이름이 사유에 나오게 되는데,
자동으로 연결 안 해 줄 거면 그걸 클릭해서 카톡방에 입력 후 해당 투자사만 재검사".

지키는 것:
  · 찾은 제목은 건에 **구조로** 담긴다 — 사유 글(셋까지 · 60자)처럼 자르지 않는다.
  · 진행 화면 폴링(`/api/jobs/N`)이 확정 못 한 건에만 후보를 싣는다 — 확인됨 건 · 이
    기능 전에 끝난 건(후보를 모른다)에는 없다.
  · 누르면 방 이름이 그 제목으로(수정 로그 · 연결 완료) · 그 한 줄짜리 새 확인 회차.
  · 남의 줄은 403 · 그 사이 방 이름이 바뀐 줄은 덮지 않는다 · 한 번에 한 후보.

여기 이름 · 회사 · 방 제목은 모두 지어낸 값이다.
"""
from __future__ import annotations

import json
import sqlite3

from app.models import EditLog, SendItem, SendJob, User, VcContact
from app.services import sheet_import

from .conftest import DEMO_PASSWORD, DEMO_TOKEN, OTHER_TOKEN, auth
from .test_migrations import _alembic

LONG = ("홍길동 심사역님 가나다벤처스 · 라마바파트너스 · 사아인베스트먼트 공동 투자 검토방 "
        "(2026 하반기 시리즈A 라운드 딜 공유 · 우리 쪽 담당 셋)")
ROOMS = [LONG, "홍길동 이사님 사아파트너스", "홍길동", "홍길동 대표 자차랩스 IR", "홍길동 멘토링방"]


def _row(db, name="홍길동", firm="가나다벤처스", room=None, user_id=1, **kw):
    row = VcContact(user_id=user_id, name=name, title="심사역", firm=firm, channel_kakao=1,
                    kakao_room_name=room, room_verified="unverified",
                    connect_stage=kw.pop("connect_stage", "not_started"), status="active", **kw)
    db.add(row)
    db.commit()
    return row


def _queue(client, ids):
    r = client.post("/api/contacts/verify-rooms", json={"contact_ids": ids})
    assert r.status_code == 200, r.text
    return r.json()["job_id"]


def _claim(client, token=DEMO_TOKEN):
    r = client.get("/api/agent/poll?kinds=verify_room", headers=auth(token))
    assert r.status_code == 200, r.text
    return r.json()["items"]


def _report(client, item_id, verdict="ambiguous", candidates=None, token=DEMO_TOKEN):
    body = {"status": "sent" if verdict == "verified" else "failed", "verify_result": verdict}
    if candidates is not None:
        body["candidates"] = candidates
    r = client.post(f"/api/agent/items/{item_id}/result", json=body, headers=auth(token))
    assert r.status_code == 200, r.text


def _finish(client, job_id, token=DEMO_TOKEN):
    r = client.post(f"/api/agent/jobs/{job_id}/status", json={"status": "done_with_errors"},
                    headers=auth(token))
    assert r.status_code == 200, r.text


def _searched(client, db, row, rooms=ROOMS, verdict="ambiguous"):
    """방 이름이 빈 줄 하나를 이름으로 찾고 결과를 받은 회차 — (회차 id, 건 id)."""
    job_id = _queue(client, [row.id])
    [item] = _claim(client)
    _report(client, item["id"], verdict, candidates=rooms)
    _finish(client, job_id)
    return job_id, item["id"]


def _item_view(client, job_id, item_id):
    r = client.get(f"/api/jobs/{job_id}")
    assert r.status_code == 200, r.text
    return next(i for i in r.json()["items"] if i["id"] == item_id)


def _pick(client, job_id, item_id, title):
    return client.post(f"/api/jobs/{job_id}/items/{item_id}/room-pick", json={"title": title})


def _fresh(db, model, row_id):
    db.expire_all()
    return db.get(model, row_id)


# ── 후보는 건에 구조로 · 자르지 않고 ─────────────────────────────────────────

def test_found_rooms_are_kept_whole_on_the_item(logged_in, db, users):
    row = _row(db)
    job_id, item_id = _searched(logged_in, db, row)
    item = _fresh(db, SendItem, item_id)
    assert item.status == "failed"
    # 사유 글은 예전처럼 셋까지 · 잘려 있다 — 그 글을 쪼개 읽지 않는다.
    assert "외 2개" in item.error and LONG not in item.error
    saved = json.loads(item.room_candidates)
    assert saved["rooms"] == ROOMS and saved["was"] == ""
    # 진행 화면 폴링이 제목을 그대로 싣는다.
    view = _item_view(logged_in, job_id, item_id)["room_pick"]
    assert view == {"rooms": ROOMS, "picked": "", "job_id": None, "note": ""}


def test_found_rooms_are_capped_and_duplicates_get_no_button(logged_in, db, users):
    row = _row(db)
    many = [f"홍길동 심사역님 방 {n}" for n in range(12)]
    job_id, item_id = _searched(logged_in, db, row, ["홍길동 겹친방", "홍길동  겹친방"] + many)
    saved = json.loads(_fresh(db, SendItem, item_id).room_candidates)
    assert len(saved["rooms"]) == 10 and saved["same"] == ["홍길동 겹친방"]
    rooms = _item_view(logged_in, job_id, item_id)["room_pick"]["rooms"]
    # 같은 제목이 둘 걸린 방은 넣어도 어느 방인지 못 가른다 — 단추를 안 세운다.
    assert "홍길동 겹친방" not in rooms and rooms == many[:9]


def test_a_confirmed_item_has_no_buttons(logged_in, db, users):
    row = _row(db)
    title = "홍길동 심사역님 가나다벤처스 딜방"
    job_id, item_id = _searched(logged_in, db, row, [title], verdict="verified")
    assert _fresh(db, VcContact, row.id).kakao_room_name == title
    assert _item_view(logged_in, job_id, item_id)["room_pick"] is None
    r = _pick(logged_in, job_id, item_id, title)
    assert r.status_code == 409


def test_an_item_from_before_this_feature_has_no_buttons(logged_in, db, users):
    """이 칸 전에 끝난 건 — 사유 글에 찾은 방이 적혀 있어도 후보를 모른다."""
    row = _row(db)
    job = SendJob(user_id=1, kind="verify_room", status="done_with_errors", total=1, sent=0,
                  failed=1)
    db.add(job)
    db.flush()
    item = SendItem(job_id=job.id, contact_id=row.id, room_name="", message="",
                    status="failed",
                    error="찾은 방이 여럿입니다 — 찾은 방: '홍길동 A', '홍길동 B' (맞는 방이면 …)")
    db.add(item)
    db.commit()
    assert _item_view(logged_in, job.id, item.id)["room_pick"] is None
    assert _pick(logged_in, job.id, item.id, "홍길동 A").status_code == 409


# ── 누르면 — 방 이름 · 수정 로그 · 연결 완료 · 한 줄짜리 새 확인 회차 ───────────────

def test_picking_puts_the_title_and_rechecks_only_that_row(logged_in, db, users):
    row = _row(db)
    other = _row(db, "김서연", "라마바파트너스")
    job_id, item_id = _searched(logged_in, db, row)
    title = ROOMS[1]

    r = _pick(logged_in, job_id, item_id, title)
    assert r.status_code == 200, r.text
    new_job = r.json()["job_id"]
    assert r.json()["href"] == f"/jobs/{new_job}" and new_job != job_id

    got = _fresh(db, VcContact, row.id)
    assert got.kakao_room_name == title
    assert got.connect_stage == sheet_import.STAGE_CONNECTED   # 방 이름만 넣으면 연결 완료
    assert got.room_verified == "unverified"                    # 확인은 새 회차가 한다
    assert _fresh(db, VcContact, other.id).kakao_room_name is None
    # 자기 줄이어도 수정 로그에 남는다 — 전 → 후.
    logs = [e for e in db.query(EditLog).all()
            if (e.table_name, e.row_id) == ("vc_contacts", row.id)]
    assert logs and "kakao_room_name" in logs[-1].changes_json
    assert title in logs[-1].changes_json

    # 그 한 줄만 · 적어 둔 이름 그대로 대조하는 새 회차.
    recheck = db.get(SendJob, new_job)
    assert (recheck.kind, recheck.topic, recheck.status, recheck.total) == (
        "verify_room", None, "queued", 1)
    [again] = recheck.items
    assert (again.contact_id, again.room_name, again.status) == (row.id, title, "pending")

    # 옛 회차의 그 건에는 단추 대신 넣은 이름과 새 회차 링크.
    view = _item_view(logged_in, job_id, item_id)["room_pick"]
    assert (view["picked"], view["job_id"], view["rooms"]) == (title, new_job, [])
    # 한 번에 한 후보 — 또 누르면 막힌다.
    assert _pick(logged_in, job_id, item_id, ROOMS[2]).status_code == 409

    # 발송기가 새 회차를 적어 둔 이름 그대로 대조한다 → 확인됨.
    [claimed] = _claim(logged_in)
    assert claimed["exact"] is True and claimed["room_name"] == title
    _report(logged_in, claimed["id"], "verified", candidates=[title])
    assert _fresh(db, VcContact, row.id).room_verified == "verified"


def test_a_written_name_that_fell_back_is_replaced_from_its_value(logged_in, db, users):
    """적어 둔 이름으로 못 찾아 이름으로 다시 찾은 건 — 찾을 때의 이름(`was`)이 지금과 같으면
    그 이름을 고른 제목으로 바꾼다."""
    old = "홍길동 옛 방 이름"
    row = _row(db, room=old)
    job_id = _queue(logged_in, [row.id])
    [first] = _claim(logged_in)
    _report(logged_in, first["id"], "not_found", candidates=[])
    r = logged_in.post(f"/api/agent/jobs/{job_id}/status", json={"status": "done"},
                       headers=auth(DEMO_TOKEN))
    assert r.json()["status"] == "queued"              # 남은 건 때문에 큐로 돌아간다
    [second] = _claim(logged_in)                       # 같은 건이 이름으로 한 번 더
    assert second["id"] == first["id"] and second["room_name"] == ""
    _report(logged_in, second["id"], "ambiguous", candidates=ROOMS[:2])
    _finish(logged_in, job_id)

    item = _fresh(db, SendItem, first["id"])
    assert item.status == "failed" and json.loads(item.room_candidates)["was"] == old
    r = _pick(logged_in, job_id, item.id, ROOMS[0])
    assert r.status_code == 200, r.text
    assert _fresh(db, VcContact, row.id).kakao_room_name == ROOMS[0]


# ── 막는 것 ──────────────────────────────────────────────────────────────────

def test_someone_elses_row_is_refused(logged_in, db, users):
    row = _row(db)
    job_id, item_id = _searched(logged_in, db, row)
    # 결과를 받은 뒤 그 줄이 다른 팀원 명단으로 넘어갔다.
    got = _fresh(db, VcContact, row.id)
    got.user_id = users["u2"].id
    db.commit()
    r = _pick(logged_in, job_id, item_id, ROOMS[1])
    assert r.status_code == 403, r.text
    assert _fresh(db, VcContact, row.id).kakao_room_name is None
    assert db.query(SendJob).count() == 1


def test_another_member_cannot_touch_my_round(client, db, users):
    row = _row(db)
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    job_id, item_id = _searched(client, db, row)
    client.post("/logout")
    client.cookies.clear()
    client.post("/login", data={"phone": "01000000002", "password": DEMO_PASSWORD})
    r = _pick(client, job_id, item_id, ROOMS[1])
    assert r.status_code == 404
    assert _fresh(db, VcContact, row.id).kakao_room_name is None


def test_a_name_changed_meanwhile_is_not_overwritten(logged_in, db, users):
    row = _row(db)
    job_id, item_id = _searched(logged_in, db, row)
    # 사람이 그 사이 수정 창에서 방 이름을 넣었다.
    r = logged_in.patch(f"/api/contacts/{row.id}", json={"kakao_room_name": "사람이 넣은 방"})
    assert r.status_code == 200, r.text

    r = _pick(logged_in, job_id, item_id, ROOMS[1])
    assert r.status_code == 409
    assert "사람이 넣은 방" in r.json()["detail"]
    assert _fresh(db, VcContact, row.id).kakao_room_name == "사람이 넣은 방"
    assert db.query(SendJob).count() == 1


def test_a_title_that_was_not_found_is_refused(logged_in, db, users):
    row = _row(db)
    job_id, item_id = _searched(logged_in, db, row)
    assert _pick(logged_in, job_id, item_id, "아무 방 이름").status_code == 409
    assert _fresh(db, VcContact, row.id).kakao_room_name is None


def test_a_row_marked_left_meanwhile_is_not_filled(logged_in, db, users):
    row = _row(db)
    job_id, item_id = _searched(logged_in, db, row)
    got = _fresh(db, VcContact, row.id)
    got.connect_stage = sheet_import.STAGE_LEFT_ROOM
    db.commit()
    assert _pick(logged_in, job_id, item_id, ROOMS[1]).status_code == 409
    assert _fresh(db, VcContact, row.id).kakao_room_name is None


def test_retrying_drops_the_old_candidates(logged_in, db, users):
    """[불일치 재확인] — 새 결과가 후보를 다시 담는다(앞 결과의 단추가 남지 않는다)."""
    row = _row(db)
    job_id, item_id = _searched(logged_in, db, row)
    r = logged_in.post(f"/api/jobs/{job_id}/retry")
    assert r.status_code == 200, r.text
    assert _item_view(logged_in, job_id, item_id)["room_pick"] is None   # 대기 중
    [again] = _claim(logged_in)
    _report(logged_in, again["id"], "not_found", candidates=[])
    assert _fresh(db, SendItem, item_id).room_candidates is None
    assert _item_view(logged_in, job_id, item_id)["room_pick"] is None


# ── 관리자 '팀원 화면으로 보기' — 방 확인은 열린 길이다 ─────────────────────────

def test_admin_viewing_a_member_can_pick(u1_admin, logged_in, db, users):
    member = db.get(User, users["u2"].id)
    row = _row(db, user_id=member.id)
    r = logged_in.post("/account/view-as", data={"member_id": member.id, "next": "/"},
                       follow_redirects=False)
    assert r.status_code == 303
    job_id = _queue(logged_in, [row.id])
    [item] = _claim(logged_in, OTHER_TOKEN)            # 그 팀원 PC 발송기가 집어간다
    _report(logged_in, item["id"], candidates=ROOMS[:2], token=OTHER_TOKEN)

    r = _pick(logged_in, job_id, item["id"], ROOMS[1])
    assert r.status_code == 200, r.text
    assert db.get(SendJob, r.json()["job_id"]).user_id == member.id
    assert _fresh(db, VcContact, row.id).kakao_room_name == ROOMS[1]
    # 관리자 이름으로 수정 로그(남의 줄).
    log = [e for e in db.query(EditLog).all()
           if (e.table_name, e.row_id) == ("vc_contacts", row.id)][-1]
    assert (log.actor_user_id, log.scope) == (users["u1"].id, "others")


def test_progress_page_shows_buttons_only_to_whoever_operates(u1_admin, logged_in, db, users):
    row = _row(db)
    job_id, _ = _searched(logged_in, db, row)
    page = logged_in.get(f"/jobs/{job_id}").text
    assert "window.DEALFLOW_JOB_PICK = true" in page

    # 관리자가 남의 회차를 조회만 할 때는 단추가 없다.
    other = _row(db, "김서연", "라마바파트너스", user_id=users["u2"].id)
    job = SendJob(user_id=users["u2"].id, kind="verify_room", status="done", total=1, sent=0,
                  failed=1)
    db.add(job)
    db.flush()
    db.add(SendItem(job_id=job.id, contact_id=other.id, room_name="", message="",
                    status="failed"))
    db.commit()
    page = logged_in.get(f"/jobs/{job.id}").text
    assert "window.DEALFLOW_JOB_PICK = false" in page


# ── 마이그레이션 0138 — 올리고 내리기 ──────────────────────────────────────────

def _send_item_columns(path) -> set:
    con = sqlite3.connect(path)
    try:
        return {r[1] for r in con.execute('PRAGMA table_info("send_items")')}
    finally:
        con.close()


def test_migration_adds_and_drops_the_column(tmp_path):
    db = tmp_path / "old.db"
    done = _alembic(db, "upgrade", "0137_ir_delivered_time")
    assert done.returncode == 0, done.stdout + done.stderr
    # 0001 은 지금 모델로 표를 만든다 — 운영 DB 처럼 칸이 없는 모양으로 되돌린다.
    con = sqlite3.connect(db)
    con.execute("ALTER TABLE send_items DROP COLUMN room_candidates")
    con.commit()
    con.close()
    assert "room_candidates" not in _send_item_columns(db)

    done = _alembic(db, "upgrade", "head")
    assert done.returncode == 0, done.stdout + done.stderr
    assert "room_candidates" in _send_item_columns(db)
    done = _alembic(db, "downgrade", "0137_ir_delivered_time")
    assert done.returncode == 0, done.stdout + done.stderr
    assert "room_candidates" not in _send_item_columns(db)
    done = _alembic(db, "upgrade", "head")
    assert done.returncode == 0, done.stdout + done.stderr
    assert "room_candidates" in _send_item_columns(db)
