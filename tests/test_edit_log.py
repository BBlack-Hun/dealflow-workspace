"""수정 로그 — **남의 것 · 공용을 고치면 남고, 자기 것만 고치면 안 남는다.**

이 검사가 지키는 것은 넷이다.

1. **한 곳을 지난다.** 로그를 남기는 자리는 세션 이벤트 하나뿐이다
   (`app/services/edit_log.py`). 라우터마다 호출을 흩뿌리지 않았으므로,
   앞으로 생기는 새 경로도 저절로 지난다. 그 '한 곳' 이 실제로 한 곳인지를
   **표를 훑어** 확인한다.
2. **빠진 곳이 있으면 여기서 걸린다.** `tests/test_consultant_access.py` 가
   앱에 등록된 라우트를 통째로 훑는 그 방식을 본떴다 — 쓰기 라우트가 하나
   늘면 아래 `WRITE_ROUTES` 에 적기 전까지 검사가 빨개진다. 손으로 적은
   목록이 낡는 것을 막는 것이 아니라, **낡을 수 없게** 만드는 쪽이다.
3. **비밀값이 안 들어간다.** `tests/test_llm_brief.py` 가 칸마다 표식을 심어
   훑는 방식을 그대로 쓴다 — 허용 목록에 없는 칸의 값이 하나라도 새면 잡힌다.
4. **볼 수 없는 사람은 못 본다.**
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from sqlalchemy import Integer, String, Text

from .conftest import DEMO_PASSWORD

APP_DIR = Path(__file__).resolve().parent.parent / "app"


# ═══════════════════════════════════════════════════════════════════════════
# 무대
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture()
def people(db, users):
    """관리자 · 투자컨설턴트. conftest 의 두 계정은 둘 다 일반 팀원이다."""
    from app.models import User
    from app.services import auth as auth_svc

    pw = auth_svc.hash_password(DEMO_PASSWORD)
    rows = [
        User(id=71, name="관리자시험", phone="01080000001", role="admin",
             can_view_consulting=1, password_hash=pw),
        User(id=73, name="컨설턴트시험", phone="01080000003", role="consultant",
             can_view_consulting=1, password_hash=pw),
    ]
    db.add_all(rows)
    db.commit()
    return {"admin": rows[0], "consultant": rows[1]}


@pytest.fixture()
def portal(db, users, people):
    """역할별로 따로 로그인한 클라이언트.

    한 클라이언트로 로그인을 갈아타면 쿠키가 덮여서 어느 사람으로 부른
    것인지 알 수 없게 된다(다른 검사들과 같은 얼개).
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
        "admin": sign_in("01080000001"),
        "consultant": sign_in("01080000003"),
        "u1": sign_in("01000000001"),
        "u2": sign_in("01000000002"),
    }


@pytest.fixture()
def groundwork(db, users):
    """FK 가 가리킬 앞줄 — 미팅·IR 요청은 담당자와 기업이 있어야 선다."""
    from app.models import IrCompany, VcContact

    db.add_all([VcContact(user_id=users["u2"].id, name="앞줄담당", firm="가나벤처스"),
                IrCompany(name="앞줄기업")])
    db.commit()


def _logs(db):
    from app.models import EditLog

    db.expire_all()
    return db.query(EditLog).order_by(EditLog.id).all()


def _changed(log) -> dict:
    """`{칸 이름: 실린 것}`. 값을 안 남기는 칸은 `"바뀜"` 이다."""
    out = {}
    for item in json.loads(log.changes_json):
        out[item["field"]] = ("바뀜" if item.get("changed")
                              else (item.get("before"), item.get("after")))
    return out


# ═══════════════════════════════════════════════════════════════════════════
# 1. 남의 것을 고치면 남는다
# ═══════════════════════════════════════════════════════════════════════════

def test_editing_someone_elses_contact_is_written_down(portal, db, users):
    """곧 팀원이 서로의 명단을 고친다 — 그 순간 이 줄이 있어야 한다.

    이 표가 곧 **발송 대상**이라, 남이 바꾼 것을 아무도 모르면 그대로 오발송이다.
    """
    from app.models import VcContact

    row = VcContact(user_id=users["u1"].id, name="가담당", firm="가나벤처스",
                    connect_stage="connected", kakao_room_name="가나 방", memo="처음")
    db.add(row)
    db.commit()

    r = portal["admin"].patch(f"/api/contacts/{row.id}",
                              json={"kakao_room_name": "다라 방"})
    assert r.status_code == 200, r.text

    logs = _logs(db)
    assert len(logs) == 1
    log = logs[0]
    assert log.scope == "others"
    assert log.action == "update"
    assert log.table_name == "vc_contacts"
    assert log.row_id == row.id
    assert log.actor_user_id == 71          # 고친 사람(관리자)
    assert log.target_user_id == users["u1"].id   # 당한 사람
    assert log.screen == "투자사 관리 현황"
    assert log.row_label == "가담당"
    assert log.method == "PATCH"
    assert log.path == f"/api/contacts/{row.id}"
    assert _changed(log)["kakao_room_name"] == ("가나 방", "다라 방")


def test_the_owner_of_the_row_is_recorded_so_they_can_be_told_later(portal, db,
                                                                    users):
    """**누구 것이 바뀌었나**가 칸으로 남는다.

    지금 화면은 관리자만 보지만, 나중에 당사자에게 알리려면 이 칸이 있어야
    한다 — 없으면 그때 표를 다시 세워야 한다.
    """
    from app.models import VcContact

    row = VcContact(user_id=users["u2"].id, name="나담당", firm="다라벤처스")
    db.add(row)
    db.commit()

    portal["admin"].patch(f"/api/contacts/{row.id}", json={"group_name": "가군"})
    assert _logs(db)[0].target_user_id == users["u2"].id


def test_deleting_someone_elses_row_is_written_down(portal, db, users):
    """지운 것이야말로 남아야 한다 — 줄이 사라지면 물어볼 데가 없다."""
    from app.models import VcContact

    row = VcContact(user_id=users["u1"].id, name="가담당", firm="가나벤처스")
    db.add(row)
    db.commit()
    rid = row.id

    assert portal["admin"].delete(f"/api/contacts/{rid}").status_code == 200
    logs = _logs(db)
    assert [(x.action, x.scope, x.row_id) for x in logs] == [("delete", "others", rid)]


# ═══════════════════════════════════════════════════════════════════════════
# 2. 공용 자료를 고치면 남는다 — 화면마다 실제로 눌러 본다
# ═══════════════════════════════════════════════════════════════════════════

def test_a_shared_company_edit_is_written_down(portal, db):
    """IR 기업은 주인이 없다 — 누가 고쳐도 팀 전체에 그대로 보인다."""
    from app.models import IrCompany

    co = IrCompany(name="가나기업", sector_major="AI")
    db.add(co)
    db.commit()

    assert portal["u1"].patch(f"/api/companies/{co.id}",
                              json={"series": "Seed"}).status_code == 200
    log = _logs(db)[0]
    assert log.scope == "shared"
    assert log.target_user_id is None
    assert log.screen == "IR 기업 현황"
    assert log.row_label == "가나기업"
    assert _changed(log)["series"] == (None, "Seed")


def test_a_shared_sourcing_row_edit_is_written_down(portal, db):
    from app.models import SourcingContact

    row = SourcingContact(bucket="AI", name="가소싱", firm="가나벤처스")
    db.add(row)
    db.commit()

    assert portal["u1"].patch(f"/api/sourcing/{row.id}",
                              json={"firm": "다라벤처스"}).status_code == 200
    log = _logs(db)[0]
    assert (log.scope, log.screen) == ("shared", "딜 소싱")
    assert _changed(log)["firm"] == ("가나벤처스", "다라벤처스")


def test_a_team_wide_template_edit_is_written_down(portal, db):
    """주인이 없는 문구가 **팀 기본 문구**다 — 관리자만 고치고, 고치면 남는다."""
    from app.models import MessageTemplate

    tpl = MessageTemplate(user_id=None, kind="deal_intro", name="기본",
                          body="안녕하세요", is_active=1)
    db.add(tpl)
    db.commit()

    r = portal["admin"].post(f"/templates/{tpl.id}/edit",
                             data={"name": "기본 인사", "body": "안녕하세요!"},
                             follow_redirects=False)
    assert r.status_code == 303, r.text
    log = _logs(db)[0]
    assert (log.scope, log.screen) == ("shared", "딜 제안 문구")
    # 이름은 값이 남고, 본문은 `바뀜` 만 남는다.
    assert _changed(log)["name"] == ("기본", "기본 인사")
    assert _changed(log)["body"] == "바뀜"


def test_a_shared_consulting_row_edit_is_written_down(portal, db, users):
    """투자컨설턴트 표의 남의 줄. 관리자는 전체를 고칠 수 있다."""
    from app.models import ConsultingCompany

    row = ConsultingCompany(user_id=users["u1"].id, sheet="default",
                            company_name="가나기업", region="서울")
    db.add(row)
    db.commit()

    assert portal["admin"].patch(f"/api/consulting/{row.id}",
                                 json={"region": "부산"}).status_code == 200
    log = _logs(db)[0]
    assert (log.scope, log.screen) == ("others", "투자컨설턴트")
    assert log.row_label == "가나기업"


def test_a_shared_reference_sheet_edit_is_written_down(portal, db):
    """참고 자료는 화면마다 하나씩 서 있고 주인이 없다."""
    from app.models import RefSheet

    sheet = RefSheet(page="contacts", title="연결 순서", kind="text", is_active=1,
                     content_json=json.dumps({"body": "전화 → 초대"}))
    db.add(sheet)
    db.commit()

    r = portal["u1"].post(f"/ref-sheets/{sheet.id}/rename",
                          data={"title": "연결 차례"}, follow_redirects=False)
    assert r.status_code == 303, r.text
    log = _logs(db)[0]
    assert log.scope == "shared"
    # 어느 화면 자료인지는 줄의 `page` 칸이 말한다.
    assert log.screen == "투자사 관리 현황"
    assert _changed(log)["title"] == ("연결 순서", "연결 차례")


def test_a_new_shared_column_is_written_down(portal, db):
    """공용 열을 **세운 것**도 남는다 — 하나 지우면 팀 전체 줄에서 사라지는 그 열이다."""
    from app.models import ConsultingColumn

    r = portal["admin"].post("/consulting/columns", data={"label": "9월 리마인드"},
                             follow_redirects=False)
    assert r.status_code == 303, r.text
    made = [x for x in _logs(db) if x.table_name == "consulting_columns"]
    assert len(made) == 1
    assert made[0].action == "create"
    assert made[0].scope == "shared"
    assert made[0].row_label == "9월 리마인드"
    assert db.query(ConsultingColumn).count() >= 1


def test_changing_someone_elses_account_is_written_down(portal, db, users):
    """팀 현황에서 남의 권한을 바꾸는 것도 **공용 화면에서 남의 것을 고치는 일**이다."""
    r = portal["admin"].post(f"/team/members/{users['u1'].id}/role",
                             data={"role": "admin"}, follow_redirects=False)
    assert r.status_code == 303
    log = [x for x in _logs(db) if x.table_name == "users"][0]
    assert log.scope == "others"
    assert log.target_user_id == users["u1"].id
    assert _changed(log)["role"] == ("user", "admin")


# ═══════════════════════════════════════════════════════════════════════════
# 3. 자기 것만 고치면 **안** 남는다
# ═══════════════════════════════════════════════════════════════════════════

def test_editing_my_own_contact_leaves_nothing(portal, db, users):
    """자기 것까지 남기면 하루에 수백 줄이 쌓여 아무도 안 본다.

    로그가 잡음으로 덮이는 것이 이 기능이 죽는 가장 흔한 길이다.
    """
    from app.models import VcContact

    row = VcContact(user_id=users["u1"].id, name="가담당", firm="가나벤처스")
    db.add(row)
    db.commit()

    for _ in range(3):
        assert portal["u1"].patch(f"/api/contacts/{row.id}",
                                  json={"memo": "내 메모"}).status_code == 200
    assert _logs(db) == []


def test_changing_my_own_password_leaves_nothing(portal, db):
    """자기 계정을 고치는 것은 자기 것이다 — 남의 것을 고칠 때만 남는다."""
    r = portal["u1"].post("/account/password",
                          data={"current_password": DEMO_PASSWORD,
                                "new_password": "dealflow999",
                                "confirm_password": "dealflow999"},
                          follow_redirects=False)
    assert r.status_code == 303, r.text
    assert [x for x in _logs(db) if x.table_name == "users"] == []


def test_logging_in_leaves_nothing(db, users):
    """로그인은 자기 계정의 마지막 접속 시각을 건드린다 — 남길 일이 아니다."""
    from fastapi.testclient import TestClient

    from app.main import create_app

    c = TestClient(create_app())
    c.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    assert _logs(db) == []


# ═══════════════════════════════════════════════════════════════════════════
# 4. 읽기(GET)는 안 남는다
# ═══════════════════════════════════════════════════════════════════════════

def test_reading_screens_leaves_nothing(portal, db, users):
    """화면을 여는 동안 무엇이 저장되더라도 로그에는 안 남는다.

    미들웨어가 **쓰기 메서드일 때만** 문맥을 심으므로, 판정이 한 곳에 있다.
    """
    from app.models import IrCompany, VcContact

    db.add_all([VcContact(user_id=users["u2"].id, name="나담당", firm="다라벤처스"),
                IrCompany(name="가나기업")])
    db.commit()

    for path in ("/", "/contacts", "/companies", "/deals", "/sourcing",
                 "/templates", "/followups", "/team", "/team/edit-log"):
        portal["admin"].get(path, follow_redirects=False)
    assert _logs(db) == []


def test_a_get_route_is_never_declared_as_one_that_writes():
    """읽기 라우트가 아래 목록에 섞여 들어오는 것을 막는다."""
    from app.services import edit_log as svc

    for method, _path in WRITE_ROUTES:
        assert method in svc.WRITE_METHODS


# ═══════════════════════════════════════════════════════════════════════════
# 5. 비밀값은 어떤 경우에도 안 남는다
# ═══════════════════════════════════════════════════════════════════════════

def test_no_secret_looking_column_is_on_the_value_allow_list():
    """허용 목록은 사람이 손으로 늘리는 자리다 — 한 겹 더 둔다."""
    from app.services import edit_log as svc

    bad = sorted(name for name in svc.VALUE_FIELDS
                 if any(hint in name for hint in svc.SECRET_HINTS))
    assert not bad, "비밀값으로 읽히는 칸이 허용 목록에 있습니다: " + ", ".join(bad)


def test_a_password_change_by_an_admin_never_carries_the_value(portal, db, users):
    """관리자가 남의 비밀번호를 초기화한다 — **바뀌었다는 것만** 남는다.

    바뀐 사실은 남아야 한다. 비밀번호를 누가 언제 갈아 끼웠는지는 이 로그가
    답해야 하는 물음 그 자체다 — 값만 안 남으면 된다.
    """
    from app.models import User

    before = db.get(User, users["u1"].id).password_hash

    r = portal["admin"].post(f"/team/members/{users['u1'].id}/reset-password",
                             follow_redirects=False)
    assert r.status_code == 303, r.text

    log = [x for x in _logs(db) if x.table_name == "users"][0]
    changed = _changed(log)
    assert changed["password_hash"] == "바뀜"
    assert changed["must_change_password"] == "바뀜"

    db.expire_all()
    after = db.get(User, users["u1"].id).password_hash
    dumped = json.dumps([x.changes_json for x in _logs(db)], ensure_ascii=False)
    assert before not in dumped and after not in dumped
    assert before != after


def _mark_every_field_without_a_value(model, row):
    """**값을 남기지 않기로 한 칸마다** 그 칸 이름이 든 표식을 심는다.

    `tests/test_llm_brief.py` 가 쓰는 방식 그대로다. **모델의 칸을 훑으므로**
    손으로 적은 목록처럼 낡지 않는다 — 다음 사람이 칸을 하나 더해도 그 칸에
    표식이 심긴다.
    """
    from app.services import edit_log as svc

    marks = {}
    for column in model.__table__.columns:
        name = column.key
        if name in svc.VALUE_FIELDS or name in ("id", "created_at", "updated_at"):
            continue
        if not isinstance(column.type, (String, Text)):
            continue
        mark = f"표식-{name}-표식"
        marks[name] = mark
        setattr(row, name, mark)
    return marks


@pytest.mark.parametrize("table", sorted(
    t for t in __import__("app.services.edit_log", fromlist=["x"]).WATCHED))
def test_no_field_off_the_allow_list_leaks_its_value(db, users, groundwork, table):
    """**칸이 늘어도 걸리는 검사.**

    보는 표마다, 값을 남기지 않기로 한 글자 칸 전부에 표식을 심고 고쳐 본다.
    나간 로그에 표식이 하나라도 섞이면 그 자리에서 잡힌다.
    """
    from app.services import edit_log as svc

    model = _model_for(table)
    row = _sample_row(db, model, owner_is=users["u2"].id)
    db.add(row)
    db.commit()

    marks = _mark_every_field_without_a_value(model, row)
    if not marks:
        pytest.skip(f"{table} 에는 값을 안 남기는 글자 칸이 없습니다")

    with _acting_as(users["u1"].id, "PATCH", "/시험"):
        db.commit()

    dumped = json.dumps([x.changes_json for x in _logs(db)], ensure_ascii=False)
    leaked = sorted(name for name, mark in marks.items() if mark in dumped)
    assert not leaked, f"{table} 의 이 칸 값이 로그에 새어 나갔습니다: " + ", ".join(leaked)


def test_the_marking_sweep_actually_marks_the_fields_that_matter(db, users):
    """표식을 심을 칸이 없으면 위 검사는 언제나 통과한다 — 그것도 잡는다."""
    from app.models import User, VcContact

    contact = VcContact(user_id=users["u2"].id, name="나담당")
    marks = _mark_every_field_without_a_value(VcContact, contact)
    for must in ("memo", "notes", "phone", "email", "sourcing_note", "tips_note"):
        assert must in marks, f"{must} 칸에 표식을 못 심었습니다"

    account = User(name="시험", phone="01000000099")
    marks = _mark_every_field_without_a_value(User, account)
    assert "password_hash" in marks, "비밀번호 칸에 표식을 못 심었습니다"


def test_a_long_value_is_cut_so_the_log_cannot_balloon(db, users):
    """허용 목록에 있는 칸이라도 값이 길면 자른다."""
    from app.models import VcContact
    from app.services import edit_log as svc

    row = VcContact(user_id=users["u2"].id, name="나담당")
    db.add(row)
    db.commit()

    with _acting_as(users["u1"].id, "PATCH", "/시험"):
        row.kakao_room_name = "가" * 500
        db.commit()

    after = _changed(_logs(db)[0])["kakao_room_name"][1]
    assert len(after) == svc.VALUE_MAX + 1 and after.endswith("…")


# ═══════════════════════════════════════════════════════════════════════════
# 6. 남겨야 하는데 안 남기는 곳이 있으면 여기서 깨진다
# ═══════════════════════════════════════════════════════════════════════════
#
# **표를 훑고, 라우트를 훑는다.** 둘을 다 하는 이유가 있다.
#
#   * 로그를 남기는 판정은 **표**가 한다(세션 이벤트). 그래서 새 표가 조용히
#     빠지는 것을 막는 것이 첫째다.
#   * 그래도 **라우트**를 훑는다. 로그를 남기는 자리를 라우터에서 뺐다는 것이
#     이 판의 알맹이라, 그 사실이 실제로 유지되는지는 라우트 쪽에서 봐야
#     한다(`tests/test_consultant_access.py` 와 같은 이유).

#: 앱에 등록된 **쓰기 라우트 전부**와 그 갈래.
#:
#:   WATCHED  보는 표를 건드릴 수 있는 길 — 남의 것·공용이면 로그가 남는다
#:   SELF     자기 것만 건드린다 — 남지 않는 것이 맞다
#:   MACHINE  발송·기기·세션 같은 기계 기록 — 사람이 고친 자료가 아니다
#:
#: **손으로 적는 것이 맞다.** 갈래를 고르는 일에는 이유가 필요하고, 새 길이
#: 하나 생기면 그 사실이 눈에 띄어야 한다. 적기 전까지 검사가 빨개진다.
WATCHED, SELF, MACHINE = "WATCHED", "SELF", "MACHINE"

WRITE_ROUTES = {
    # ── 공용·타인 화면 (설계가 말한 그 49개 + 참고 자료 6개) ────────────────
    ("POST", "/companies/ir-files"): WATCHED,
    ("POST", "/api/companies"): WATCHED,
    ("PATCH", "/api/companies/{company_id}"): WATCHED,
    ("POST", "/api/companies/{company_id}/one-liner"): WATCHED,
    ("POST", "/api/one-liner/bulk"): WATCHED,
    ("POST", "/api/one-liner/bulk/undo"): WATCHED,
    ("DELETE", "/api/companies/{company_id}"): WATCHED,

    ("POST", "/ir/requests"): WATCHED,
    ("POST", "/ir/deliver-guide"): WATCHED,
    ("POST", "/ir/requests/{request_id}/deliver"): WATCHED,
    ("POST", "/ir/requests/{request_id}/drop"): WATCHED,
    ("POST", "/ir/requests/{request_id}/delete"): WATCHED,
    ("POST", "/ir/meetings"): WATCHED,
    ("POST", "/ir/meetings/{meeting_id}/mode"): WATCHED,
    ("POST", "/ir/meetings/{meeting_id}/done"): WATCHED,
    ("POST", "/ir/meetings/{meeting_id}/followup"): WATCHED,
    ("PATCH", "/api/meetings/{meeting_id}"): WATCHED,
    ("POST", "/ir/meetings/{meeting_id}/cancel"): WATCHED,

    ("POST", "/api/consulting"): WATCHED,
    ("PATCH", "/api/consulting/{company_id}"): WATCHED,
    ("DELETE", "/api/consulting/{company_id}"): WATCHED,
    ("POST", "/consulting/sheets/rename"): WATCHED,
    ("POST", "/consulting/columns"): WATCHED,
    ("POST", "/consulting/columns/{column_id}/rename"): WATCHED,
    ("POST", "/consulting/columns/{column_id}/delete"): WATCHED,
    ("POST", "/consulting/import"): WATCHED,

    ("POST", "/templates/choose"): WATCHED,
    ("POST", "/templates/copy"): WATCHED,
    ("POST", "/templates/new"): WATCHED,
    ("POST", "/templates/{template_id}/edit"): WATCHED,
    ("POST", "/templates/{template_id}/delete"): WATCHED,

    ("POST", "/sourcing/buckets/rename"): WATCHED,
    ("POST", "/api/sourcing"): WATCHED,
    ("PATCH", "/api/sourcing/{row_id}"): WATCHED,
    ("DELETE", "/api/sourcing/{row_id}"): WATCHED,

    ("POST", "/api/contacts/verify-rooms"): WATCHED,
    ("POST", "/api/contacts/assign"): WATCHED,
    ("POST", "/api/contacts/{contact_id}/transfer"): WATCHED,
    ("POST", "/api/contacts/sheets/assign"): WATCHED,
    ("POST", "/api/contacts/sheets/hide"): WATCHED,
    ("POST", "/api/contacts/sheets/deal-list"): WATCHED,
    ("POST", "/api/contacts/sheets/rename"): WATCHED,
    ("POST", "/api/contacts/columns"): WATCHED,
    ("POST", "/api/contacts/columns/{column_id}/rename"): WATCHED,
    ("POST", "/api/contacts/columns/{column_id}/hide"): WATCHED,
    ("POST", "/api/contacts/columns/{column_id}/delete"): WATCHED,
    ("POST", "/api/contacts"): WATCHED,
    ("PATCH", "/api/contacts/{contact_id}"): WATCHED,
    ("DELETE", "/api/contacts/{contact_id}"): WATCHED,
    # 감춘 줄을 골라 한꺼번에 지운다. **줄마다 한 줄씩** 남는다
    # (`confirm` 없이 부르면 세어 보기만 하고 아무 것도 안 지운다).
    ("POST", "/api/contacts/bulk-delete"): WATCHED,
    ("POST", "/ref-sheets/new"): WATCHED,
    ("PATCH", "/api/ref-sheets/{sheet_id}/cell"): WATCHED,
    ("PATCH", "/api/ref-sheets/{sheet_id}/column"): WATCHED,
    ("POST", "/ref-sheets/{sheet_id}/body"): WATCHED,
    ("POST", "/ref-sheets/{sheet_id}/rename"): WATCHED,
    ("POST", "/ref-sheets/{sheet_id}/delete"): WATCHED,

    # ── 팀 현황 — 남의 계정과 팀 공용 스위치 ────────────────────────────────
    ("POST", "/team/members"): WATCHED,
    ("POST", "/team/members/{member_id}/profile"): WATCHED,
    ("POST", "/team/members/{member_id}/role"): WATCHED,
    ("POST", "/team/members/{member_id}/consulting"): WATCHED,
    # 누구의 줄을 누가 고쳐도 되는가 — 권한을 넓힌 것 자체가 남아야 한다.
    ("POST", "/team/members/{member_id}/consulting-editors"): WATCHED,
    ("POST", "/team/members/{member_id}/auto-attach"): WATCHED,
    ("POST", "/team/members/{member_id}/reset-password"): WATCHED,
    ("POST", "/team/members/{member_id}/deactivate"): WATCHED,
    ("POST", "/team/auto-send"): WATCHED,
    ("POST", "/team/startup-send"): WATCHED,

    # 시트 가져오기 — 남의 명단까지 통째로 갈아 끼운다.
    ("POST", "/api/import/contacts"): WATCHED,
    # 발송 날짜 규칙은 팀 전체의 일정이다.
    ("POST", "/followups/rules/{key}"): WATCHED,

    # ── 자기 것만 ───────────────────────────────────────────────────────────
    ("POST", "/login"): SELF,
    ("POST", "/account/password"): SELF,
    ("POST", "/todo/tasks"): SELF,
    ("PATCH", "/api/todo/tasks/{task_id}"): SELF,
    ("POST", "/todo/tasks/{task_id}/delete"): SELF,
    ("POST", "/todo/routines"): SELF,
    ("PATCH", "/api/todo/routines/{routine_id}"): SELF,
    ("POST", "/todo/routines/{routine_id}/delete"): SELF,
    ("POST", "/todo/carry-over"): SELF,
    ("POST", "/setup/ir-root"): SELF,

    # ── 기계 기록 ───────────────────────────────────────────────────────────
    ("POST", "/logout"): MACHINE,
    ("POST", "/api/agent/heartbeat"): MACHINE,
    ("POST", "/api/agent/diagnostics"): MACHINE,
    ("POST", "/api/agent/items/{item_id}/result"): MACHINE,
    ("POST", "/api/agent/jobs/{job_id}/status"): MACHINE,
    ("POST", "/api/deals/preview"): MACHINE,
    ("POST", "/api/deals/send"): MACHINE,
    ("POST", "/api/deals/queue"): MACHINE,
    ("POST", "/api/deals/queue/{item_id}/start"): MACHINE,
    ("POST", "/api/deals/queue/{item_id}/cancel"): MACHINE,
    ("POST", "/api/jobs/{job_id}/cancel"): MACHINE,
    ("POST", "/api/jobs/{job_id}/retry"): MACHINE,
    ("POST", "/api/jobs/{job_id}/resend-canceled"): MACHINE,
    ("POST", "/api/jobs/{job_id}/resume"): MACHINE,
    ("POST", "/api/jobs/{job_id}/start"): MACHINE,
    ("POST", "/api/jobs/{job_id}/schedule"): MACHINE,
    ("DELETE", "/api/jobs/{job_id}/schedule"): MACHINE,
    ("POST", "/followups/backfill"): MACHINE,
    ("POST", "/followups/{sequence_id}/responded"): MACHINE,
    ("POST", "/followups/{sequence_id}/stop"): MACHINE,
    ("POST", "/followups/{sequence_id}/resume"): MACHINE,
    ("POST", "/deals/startup-ir/send"): MACHINE,
    ("POST", "/api/llm-brief/resolve"): MACHINE,
    ("POST", "/api/import/contacts/sheets"): MACHINE,
    # 자료 전체를 파일째 갈아 끼운다 — ORM 을 지나지 않는다.
    ("POST", "/team/restore/apply"): MACHINE,
    ("POST", "/team/mail-test"): MACHINE,
    ("POST", "/setup/test/attach"): MACHINE,
    ("POST", "/setup/test/startup-remind"): MACHINE,
    ("POST", "/setup/test/meeting-review"): MACHINE,
    ("POST", "/setup/test/room"): MACHINE,
}

#: 공용·타인 화면을 맡은 라우터. 여기 있는 파일의 쓰기 라우트는 **전부**
#: `WATCHED` 여야 한다 — 목록에 손으로 적는 갈래를 실제와 묶어 두는 자리다.
SHARED_ROUTERS = ("companies", "ir", "consulting", "templates_crud",
                  "sourcing", "contacts")


def _write_routes(app):
    out = {}
    for route in app.routes:
        methods = getattr(route, "methods", None) or ()
        path = getattr(route, "path", "")
        endpoint = getattr(route, "endpoint", None)
        if not path or endpoint is None:
            continue
        for method in methods:
            if method in ("GET", "HEAD", "OPTIONS"):
                continue
            out[(method, path)] = getattr(endpoint, "__module__", "").split(".")[-1]
    return out


def test_every_write_route_is_accounted_for(portal):
    """**라우트를 통째로 훑는다** — 쓰기 길이 하나 늘면 여기서 먼저 걸린다.

    `tests/test_consultant_access.py` 가 앱에 등록된 라우트를 훑는 그 방식이다.
    새 길을 낸 사람은 위 목록에서 갈래를 골라야 하고, 고르는 동안 "이 길이
    남의 것을 건드리나" 를 한 번 생각하게 된다. 적어 두지 않으면 통과할 수 없다.
    """
    found = _write_routes(portal["app"])
    missing = sorted(f"{m} {p}" for (m, p) in found if (m, p) not in WRITE_ROUTES)
    assert not missing, (
        "쓰기 라우트가 수정 로그 목록에 없습니다. tests/test_edit_log.py 의 "
        "WRITE_ROUTES 에 WATCHED · SELF · MACHINE 중 하나로 적어 주세요:\n"
        + "\n".join(missing))

    gone = sorted(f"{m} {p}" for (m, p) in WRITE_ROUTES if (m, p) not in found)
    assert not gone, "없어진 라우트가 목록에 남아 있습니다:\n" + "\n".join(gone)


def test_every_write_route_of_a_shared_screen_is_marked_watched(portal):
    """공용·타인 화면의 라우터에 붙은 쓰기는 **전부** 보는 쪽이어야 한다.

    이 검사가 위 목록을 실제와 묶는다 — 없으면 새 길에 `MACHINE` 이라고
    적어 두는 것만으로 검사를 통과시킬 수 있다.
    """
    slipped = sorted(f"{m} {p} ({mod}.py)"
                     for (m, p), mod in _write_routes(portal["app"]).items()
                     if mod in SHARED_ROUTERS and WRITE_ROUTES.get((m, p)) != WATCHED)
    assert not slipped, ("공용·타인 화면의 쓰기 라우트인데 보는 쪽이 아닙니다:\n"
                         + "\n".join(slipped))


def test_the_six_shared_routers_still_hold_the_forty_nine_paths(portal):
    """설계가 센 숫자를 못 박는다 — 늘거나 줄면 설명이 필요하다."""
    counted = {}
    for (_m, _p), mod in _write_routes(portal["app"]).items():
        if mod in SHARED_ROUTERS:
            counted[mod] = counted.get(mod, 0) + 1
    # contacts 는 명단 라우터 15 + 참고 자료 6 이다(참고 자료는 주소에 접두가
    # 없어 파일만 같이 쓴다). 15번째가 감춘 줄 한꺼번에 지우기(`/bulk-delete`)다.
    assert counted == {"companies": 7, "ir": 11, "consulting": 8,
                       "templates_crud": 5, "sourcing": 4, "contacts": 21}


def test_every_table_is_either_watched_or_explained(db):
    """**표를 통째로 훑는다** — 표가 하나 늘면 여기서 걸린다.

    로그를 남길지 말지는 표가 정하므로, 새 표가 조용히 빠지는 것이 이 기능이
    죽는 가장 조용한 길이다.
    """
    import app.models  # noqa: F401
    from app.db import Base
    from app.services import edit_log as svc

    known = set(svc.WATCHED) | set(svc.UNWATCHED)
    unknown = sorted(set(Base.metadata.tables) - known)
    assert not unknown, (
        "새 표가 수정 로그 분류에 없습니다. app/services/edit_log.py 의 "
        "WATCHED 나 UNWATCHED 에 이유와 함께 적어 주세요: " + ", ".join(unknown))

    stale = sorted(known - set(Base.metadata.tables))
    assert not stale, "없어진 표가 분류에 남아 있습니다: " + ", ".join(stale)


def test_every_unwatched_table_says_why():
    from app.services import edit_log as svc

    blank = sorted(t for t, why in svc.UNWATCHED.items() if len((why or "").strip()) < 10)
    assert not blank, "이유가 비어 있습니다: " + ", ".join(blank)


def test_every_watched_table_can_answer_who_owns_it_and_which_screen(db):
    """보기로 한 표가 실제로 그 칸을 갖고 있는가 · 화면 이름이 나오는가.

    `owner="user_id"` 라고 적어 두었는데 모델에 그 칸이 없으면 판정이 조용히
    `공용` 으로 굴러떨어진다 — 남의 것이 공용으로 읽히는 것이 제일 나쁘다.
    """
    from app.services import edit_log as svc
    from app.ui import screen_label

    for table, watch in svc.WATCHED.items():
        model = _model_for(table)
        if watch.owner is not None:
            assert watch.owner in model.__table__.columns, \
                f"{table} 에 {watch.owner} 칸이 없습니다"
        if not callable(watch.href):
            assert screen_label(watch.href), \
                f"{table} 의 화면 이름을 좌측 메뉴에서 못 찾았습니다: {watch.href}"
        assert len(watch.why.strip()) >= 10, f"{table} 의 이유가 비어 있습니다"


# ── ORM 을 지나지 않는 쓰기 ──────────────────────────────────────────────────
#
# 세션 이벤트는 flush 를 지나는 것만 본다. `db.execute(delete(...))` ·
# `db.query(...).delete()` 는 그 자리를 건너뛰므로, **보는 표에 그런 자리가
# 새로 생기면** 로그에 구멍이 난다. 지금 있는 것은 아래 하나뿐이다.

KNOWN_BULK = {
    ("app/routers/consulting.py", "ConsultingCompany"):
        "시트를 다시 올릴 때 **자기 줄만** 지우고 새로 넣는다"
        "(`ConsultingCompany.user_id == user.id`). 한꺼번에 지우기라 flush 를 "
        "지나지 않아 안 남는다 — 사람이 줄을 고른 것이 아니라 시트 한 장을 "
        "통째로 갈아 끼우는 길이고, 무엇이 들어왔는지는 새로 선 줄이 말한다. "
        "**사람이 줄을 골라 지우는 길은 이렇게 하면 안 된다** — 투자사 관리 "
        "현황의 [선택 삭제] 가 줄마다 `db.delete()` 로 지우는 이유가 그것이다.",
}

_BULK = re.compile(r"\.delete\(\s*\)|execute\(\s*delete\(|execute\(\s*update\(|"
                   r"bulk_(update|insert)_mappings|bulk_save_objects")


def test_no_new_write_sneaks_past_the_flush(db):
    """한꺼번에 지우고 고치는 자리가 새로 생기면 여기서 걸린다."""
    import app.models  # noqa: F401
    from app.db import Base
    from app.services import edit_log as svc

    classes = {}
    for mapper in Base.registry.mappers:
        table = mapper.class_.__tablename__
        if table in svc.WATCHED:
            classes[mapper.class_.__name__] = table

    found = {}
    for path in sorted(APP_DIR.rglob("*.py")):
        lines = path.read_text(encoding="utf-8").splitlines()
        for i, line in enumerate(lines):
            if not _BULK.search(line):
                continue
            # **그 문장만 본다.** 앞뒤로 넓게 잡으면 함수 서명의
            # `user: User` 같은 글자까지 딸려 와 엉뚱한 표가 걸린다.
            window = "\n".join(lines[max(0, i - 2):i + 4])
            for name in classes:
                if re.search(rf"\b{name}\s*[.)]|\(\s*{name}\s*[,)]", window):
                    key = (str(path.relative_to(APP_DIR.parent)), name)
                    found.setdefault(key, i + 1)

    new = sorted(f"{f}:{line} ({name})" for (f, name), line in found.items()
                 if (f, name) not in KNOWN_BULK)
    assert not new, (
        "ORM 을 지나지 않는 쓰기가 보는 표에 새로 생겼습니다. 줄마다 저장하도록 "
        "고치거나, 왜 안 남겨도 되는지를 KNOWN_BULK 에 적어 주세요:\n"
        + "\n".join(new))

    gone = sorted(f"{f} ({name})" for (f, name) in KNOWN_BULK if (f, name) not in found)
    assert not gone, "없어진 자리가 KNOWN_BULK 에 남아 있습니다:\n" + "\n".join(gone)


# ═══════════════════════════════════════════════════════════════════════════
# 7. 보는 표마다 **실제로** 남는가 — 하나씩 고쳐 본다
# ═══════════════════════════════════════════════════════════════════════════

def _model_for(table: str):
    import app.models  # noqa: F401
    from app.db import Base

    for mapper in Base.registry.mappers:
        if mapper.class_.__tablename__ == table:
            return mapper.class_
    raise AssertionError(f"{table} 을(를) 만드는 모델이 없습니다")


class _acting_as:
    """미들웨어가 심는 문맥을 검사에서 흉내 낸다."""

    def __init__(self, user_id: int, method: str, path: str) -> None:
        self.args = (user_id, method, path)

    def __enter__(self):
        from app.services import edit_log as svc

        self.token = svc.begin(*self.args)
        return self

    def __exit__(self, *exc):
        from app.services import edit_log as svc

        svc.end(self.token)
        return False


def _sample_row(db, model, *, owner_is=None):
    """이 표의 줄 하나 — **비어 있으면 안 되는 칸만** 채운다.

    손으로 표마다 줄을 적어 두면 표가 하나 늘 때 그 표만 검사에서 빠진다.
    """
    from sqlalchemy import select
    from app.services import edit_log as svc

    watch = svc.WATCHED[model.__tablename__]
    row = model()
    for column in model.__table__.columns:
        if column.primary_key:
            continue
        if column.foreign_keys:
            target = list(column.foreign_keys)[0].column.table.name
            found = db.execute(
                select(_model_for(target))).scalars().first()
            if found is not None:
                setattr(row, column.key, found.id)
            continue
        if column.nullable or column.default is not None \
                or column.server_default is not None:
            continue
        setattr(row, column.key,
                1 if isinstance(column.type, Integer) else "시험값")
    if watch.owner and watch.owner != "id" and owner_is is not None:
        setattr(row, watch.owner, owner_is)
    return row


def _a_logged_field(db, model, row):
    """값이 로그에 실리는 칸 하나와 **거기 넣어 볼 값**. 없으면 `(None, None)`.

    **글자 칸만 찾던 자리다.** 값을 남기는 칸이 전부 번호인 표가 생기자
    (`consulting_row_grants` — `누구의 줄을 누가 고치나` 두 번호가 전부다)
    찾지 못해 검사가 그 표에서 멎었다. 이 검사가 묻는 것은 `값이 실리는 칸을
    고치면 로그가 남는가` 이지 **그 칸이 글자인가**가 아니므로 번호 칸도
    그대로 고른다.

    두 가지를 지킨다.

    · **주인 칸은 마지막에 고른다.** 담당을 옮기는 것은 보통의 수정과 다른
      길을 지나므로(`_row_scope` 가 고치기 **전**의 주인으로 판정한다), 다른
      칸이 있으면 그쪽으로 검사한다.
    · **번호 칸은 실재하는 줄을 가리키게 바꾼다.** 아무 숫자나 넣으면 없는
      계정을 가리켜 저장 자체가 막힌다(`PRAGMA foreign_keys=ON`).
    """
    from sqlalchemy import select
    from app.services import edit_log as svc

    watch = svc.WATCHED[model.__tablename__]
    columns = [c for c in model.__table__.columns if c.key in svc.VALUE_FIELDS]
    # 주인 칸을 뒤로 민다.
    columns.sort(key=lambda c: c.key == watch.owner)
    for column in columns:
        if isinstance(column.type, String):
            return column.key, "바꾼값"
        if not isinstance(column.type, Integer):
            continue
        now = getattr(row, column.key, None)
        if not column.foreign_keys:
            return column.key, (now or 0) + 1
        target = list(column.foreign_keys)[0].column.table.name
        ids = [r.id for r in
               db.execute(select(_model_for(target))).scalars().all()]
        other = next((i for i in ids if i != now), None)
        if other is not None:
            return column.key, other
    return None, None


@pytest.mark.parametrize("table", sorted(
    t for t in __import__("app.services.edit_log", fromlist=["x"]).WATCHED
    if t != "users"))
def test_every_watched_table_actually_leaves_a_line(db, users, groundwork, table):
    """표가 늘어도 저절로 도는 검사.

    보는 표에 새 이름을 적어 두기만 하고 실제로는 안 남는 상태를 잡는다.
    """
    from app.services import edit_log as svc

    model = _model_for(table)
    row = _sample_row(db, model, owner_is=users["u2"].id)
    db.add(row)
    db.commit()
    before = len(_logs(db))

    changed, value = _a_logged_field(db, model, row)
    assert changed, f"{table} 에 값을 남기는 칸이 하나도 없습니다"

    with _acting_as(users["u1"].id, "PATCH", "/시험"):
        setattr(row, changed, value)
        db.commit()

    logs = [x for x in _logs(db)[before:] if x.table_name == table]
    assert len(logs) == 1, f"{table} 을 고쳤는데 로그가 남지 않았습니다"
    assert logs[0].scope in ("others", "shared")
    assert changed in _changed(logs[0])


def test_a_table_that_is_watched_but_edited_by_its_owner_leaves_nothing(db, users, groundwork):
    """주인이 자기 줄을 고치면 안 남는다 — 표마다 확인한다."""
    from app.services import edit_log as svc

    for table, watch in svc.WATCHED.items():
        if not watch.owner or watch.owner == "id":
            continue
        model = _model_for(table)
        row = _sample_row(db, model, owner_is=users["u1"].id)
        db.add(row)
        db.commit()
        before = len(_logs(db))
        changed, value = _a_logged_field(db, model, row)
        assert changed, f"{table} 에 값을 남기는 칸이 하나도 없습니다"
        with _acting_as(users["u1"].id, "PATCH", "/시험"):
            setattr(row, changed, value)
            db.commit()
        assert len(_logs(db)) == before, f"{table} — 자기 줄을 고쳤는데 남았습니다"


def test_nothing_is_written_without_a_request_behind_it(db, users):
    """배경에서 도는 실(발송·백업)이 만든 줄은 남지 않는다.

    문맥이 없으면 아무 일도 없다 — 그것이 이 판의 안전장치다.
    """
    from app.models import VcContact

    row = VcContact(user_id=users["u2"].id, name="나담당")
    db.add(row)
    row.kakao_room_name = "배경에서 바뀜"
    db.commit()
    assert _logs(db) == []


# ═══════════════════════════════════════════════════════════════════════════
# 8. 볼 권한이 없으면 못 본다
# ═══════════════════════════════════════════════════════════════════════════

def test_only_an_admin_can_open_the_log(portal, db, users):
    """팀원에게 열면 팀 전체의 근무 일지가 된다 — 팀 현황과 같은 판단이다."""
    from app.models import VcContact

    row = VcContact(user_id=users["u2"].id, name="나담당", firm="다라벤처스")
    db.add(row)
    db.commit()
    portal["admin"].patch(f"/api/contacts/{row.id}", json={"group_name": "가군"})

    ok = portal["admin"].get("/team/edit-log")
    assert ok.status_code == 200
    assert "나담당" in ok.text

    # 관리자 전용 화면은 주소창으로 열면 **안내창**이 뜬다(403 날것이 아니라).
    # 판정과 답은 `deps.admin_block_response` 한 곳에 있고, 다른 관리자 화면과
    # 같은 모양이다(tests/test_admin_guard.py).
    blocked = portal["u1"].get("/team/edit-log", follow_redirects=False)
    assert blocked.status_code == 200
    assert "관리자만 볼 수 있습니다" in blocked.text
    assert "나담당" not in blocked.text


def test_a_consultant_never_reaches_the_log(portal):
    """투자컨설턴트는 자기 화면 하나만 쓴다 — 미들웨어가 먼저 끊는다."""
    from app import deps

    r = portal["consultant"].get("/team/edit-log", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == deps.CONSULTANT_HOME


def test_a_visitor_who_is_not_logged_in_gets_nothing(client):
    r = client.get("/team/edit-log", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"].startswith("/login")


def test_the_team_screen_points_at_the_log(portal):
    """찾아갈 수 있어야 쓸모가 있다."""
    assert 'href="/team/edit-log"' in portal["admin"].get("/team").text


# ═══════════════════════════════════════════════════════════════════════════
# 9. 화면이 읽을 수 있게 나오는가
# ═══════════════════════════════════════════════════════════════════════════

def test_the_screen_shows_names_not_account_numbers(portal, db, users):
    """담당 칸은 번호로 남는다 — 번호를 그대로 보여 주면 아무도 못 읽는다."""
    from app.models import VcContact

    row = VcContact(user_id=users["u1"].id, name="가담당", firm="가나벤처스")
    db.add(row)
    db.commit()

    # 관리자가 담당을 넘긴다 — 판정은 **넘기기 전의 주인**으로 한다.
    with _acting_as(71, "PATCH", "/시험"):
        row.user_id = users["u2"].id
        db.commit()

    log = _logs(db)[0]
    assert (log.scope, log.target_user_id) == ("others", users["u1"].id)

    body = portal["admin"].get("/team/edit-log").text
    assert users["u1"].name in body and users["u2"].name in body
    assert f">{users['u1'].id}<" not in body


def test_the_screen_can_be_narrowed_to_shared_or_to_someone_elses(portal, db,
                                                                  users):
    from app.models import IrCompany, VcContact

    mine = VcContact(user_id=users["u1"].id, name="가담당", firm="가나벤처스")
    company = IrCompany(name="가나기업")
    db.add_all([mine, company])
    db.commit()

    portal["admin"].patch(f"/api/contacts/{mine.id}", json={"group_name": "가군"})
    portal["admin"].patch(f"/api/companies/{company.id}", json={"series": "Seed"})

    others = portal["admin"].get("/team/edit-log?scope=others").text
    assert "가담당" in others and "가나기업" not in others

    shared = portal["admin"].get("/team/edit-log?scope=shared").text
    assert "가나기업" in shared and "가담당" not in shared

    by_screen = portal["admin"].get("/team/edit-log?screen=IR 기업 현황").text
    assert "가나기업" in by_screen and "가담당" not in by_screen


def test_the_screen_never_prints_a_value_it_did_not_keep(portal, db, users):
    """메모는 `바뀜` 으로만 뜬다 — 화면이 로그보다 더 말하면 안 된다."""
    from app.models import VcContact

    row = VcContact(user_id=users["u1"].id, name="가담당", memo="옛 메모")
    db.add(row)
    db.commit()

    portal["admin"].patch(f"/api/contacts/{row.id}", json={"memo": "새 메모"})
    body = portal["admin"].get("/team/edit-log").text
    assert "옛 메모" not in body and "새 메모" not in body
    assert "바뀜" in body


def test_the_filter_list_comes_from_the_watched_tables(portal):
    """걸러 보기 목록을 손으로 적어 두면 표가 늘 때 그 화면만 빠진다."""
    from app.services import edit_log as svc

    body = portal["admin"].get("/team/edit-log").text
    for name in svc.screens():
        assert name in body, f"{name} 이 걸러 보기 목록에 없습니다"


# ═══════════════════════════════════════════════════════════════════════════
# 10. 보관 정책은 적혀만 있다 (지우는 것은 이번에 만들지 않았다)
# ═══════════════════════════════════════════════════════════════════════════

def test_the_retention_policy_is_written_down_and_not_yet_enforced(portal):
    """정책을 코드에 적어 두고, 화면에도 그대로 적는다.

    **지우는 코드는 아직 없다.** 화면이 "13개월 보관" 이라고만 말하고 실제로는
    영원히 쌓이는 상태가 가장 나쁘다 — 그래서 화면도 아직 안 지운다고 말한다.
    """
    from app.services import edit_log as svc

    assert svc.RETENTION_MONTHS == 13
    body = portal["admin"].get("/team/edit-log").text
    assert f"{svc.RETENTION_MONTHS}개월" in body
    assert "아직 만들지 않았습니다" in body


def test_handing_a_row_over_is_judged_by_who_owned_it_before(db, users):
    """담당을 넘기는 일 — **넘긴 뒤의 주인**으로 보면 아무 것도 안 남는다.

    남의 줄을 내게 가져오면 `내 것을 고쳤다` 가 되고, 내 줄을 남에게 넘기면
    `남의 것을 고쳤다` 가 된다. 둘 다 거꾸로다.
    """
    from app.models import VcContact

    # 남의 줄을 내게 가져온다 — 남는다.
    taken = VcContact(user_id=users["u2"].id, name="나담당")
    db.add(taken)
    db.commit()
    with _acting_as(users["u1"].id, "PATCH", "/시험"):
        taken.user_id = users["u1"].id
        db.commit()
    logs = _logs(db)
    assert len(logs) == 1
    assert (logs[0].scope, logs[0].target_user_id) == ("others", users["u2"].id)

    # 내 줄을 남에게 넘긴다 — 내 것이었으므로 안 남는다.
    given = VcContact(user_id=users["u1"].id, name="가담당")
    db.add(given)
    db.commit()
    with _acting_as(users["u1"].id, "PATCH", "/시험"):
        given.user_id = users["u2"].id
        db.commit()
    assert len(_logs(db)) == 1


def test_a_new_or_deleted_row_only_carries_the_fields_worth_keeping(db, users):
    """줄이 통째로 생기거나 사라질 때 `메모 바뀜` 은 아무 것도 말해 주지 않는다.

    그때 알고 싶은 것은 **무슨 줄이었나**(이름 · 담당 · 단계)이지, 어느 칸에
    손이 닿았느냐가 아니다. 줄 전체가 생겼거나 사라진 것은 `추가`·`삭제`
    표시가 이미 말한다.
    """
    from app.models import VcContact

    with _acting_as(users["u1"].id, "POST", "/시험"):
        row = VcContact(user_id=users["u2"].id, name="나담당", memo="긴 메모",
                        phone="010-0000-0000", connect_stage="connected")
        db.add(row)
        db.commit()

    made = _changed(_logs(db)[-1])
    assert made["name"] == (None, "나담당")
    assert made["connect_stage"] == (None, "connected")
    assert "memo" not in made and "phone" not in made

    with _acting_as(users["u1"].id, "DELETE", "/시험"):
        db.delete(row)
        db.commit()

    gone = _logs(db)[-1]
    assert gone.action == "delete"
    assert _changed(gone)["name"] == ("나담당", None)
    assert "memo" not in _changed(gone)
