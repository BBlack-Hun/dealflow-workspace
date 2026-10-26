"""관리자 문구 → 팀 전체 — [모든 팀원에게 적용] 과 [되돌리기].

관리자가 팀 기본 문구를 고쳐도 팀원의 발송은 그대로였다(고른 것 > 내 것 >
팀 것). 모두가 같은 말로 나가야 할 때 관리자가 한 번에 덮는 길이고, 덮는
것이 **사람이 손으로 정해 둔 것**이라 되돌릴 수 있어야 한다.

여기서 못 박는 것.

  ① 단추는 관리자에게만, 정해 둔 종류의 팀 문구에만 — 팀원은 403
  ② 확인창의 숫자 == 실제로 바뀌는 것
  ③ 적용하면 딜소개를 보내는 모두(안 고른 사람 · 관리자 포함)의 선택이 이 문구가
     되고, **그 자리의** 개인 문구만 꺼진다 — `pick` 이 모두에게 이 문구를 준다
  ④ 덮기 전 상태가 백업에 남고, 남의 개인 문구가 꺼진 것이 수정 로그에 남는다
  ⑤ 되돌리면 전 선택과 개인 문구가 돌아온다 — 그 사이 바뀐 것은 건드리지 않고,
     두 번은 안 된다
  ⑥ 판(0103)이 올라가고 내려간다
"""
from __future__ import annotations

import html
import json
import re
import sqlite3

import pytest

from .conftest import DEMO_PASSWORD
from .test_migrations import _alembic

KIND = "closing_day1"
TEAM_A = "가 안내문입니다. 팀 기본 첫 번째."
TEAM_B = "나 안내문입니다. 팀 기본 두 번째."
MINE_U1 = "강민준이 손본 안내문입니다."


# ═══════════════════════════════════════════════════════════════════════════
# 무대
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture()
def people(db, users):
    """관리자 · 투자컨설턴트 · 정지된 팀원. conftest 의 둘(u1 · u2)은 일반 팀원이다."""
    from app.models import User
    from app.services import auth as auth_svc

    pw = auth_svc.hash_password(DEMO_PASSWORD)
    rows = {
        "admin": User(id=71, name="관리자시험", phone="01080000001", role="admin",
                      password_hash=pw),
        "consultant": User(id=73, name="컨설턴트시험", phone="01080000003",
                           role="consultant", password_hash=pw),
        "sleeper": User(id=75, name="정지시험", phone="01080000005", role="user",
                        is_active=0, password_hash=pw),
    }
    db.add_all(rows.values())
    db.commit()
    return {**rows, **users}


@pytest.fixture()
def portal(db, people):
    """사람마다 따로 로그인한 클라이언트 — 한 클라이언트로 갈아타면 쿠키가 덮인다."""
    from fastapi.testclient import TestClient

    from app.main import create_app

    app = create_app()

    def sign_in(phone: str):
        client = TestClient(app)
        r = client.post("/login", data={"phone": phone, "password": DEMO_PASSWORD},
                        follow_redirects=False)
        assert r.status_code == 303
        return client

    return {"admin": sign_in("01080000001"), "u1": sign_in("01000000001"),
            "u2": sign_in("01000000002")}


@pytest.fixture()
def stage(db, people):
    """안내문(딜소개) 자리에 팀 문구 둘 · u1 의 개인 문구 · 사람마다 다른 선택.

      관리자   아무것도 안 고름
      u1       제 개인 문구를 고름
      u2       팀 문구 B 를 고름
      컨설턴트 (보낼 문구가 없는 계정)

    다른 자리에도 u1 의 개인 문구를 하나 둔다 — 적용이 그 자리를 넘어가면 안 된다.
    """
    from app.models import MessageTemplate, TemplateChoice

    a = MessageTemplate(user_id=None, kind=KIND, name="가", body=TEAM_A, is_active=1)
    b = MessageTemplate(user_id=None, kind=KIND, name="나", body=TEAM_B, is_active=1)
    mine = MessageTemplate(user_id=people["u1"].id, kind=KIND, name="내 문구",
                           body=MINE_U1, is_active=1)
    other_kind = MessageTemplate(user_id=people["u1"].id, kind="opening_first",
                                 name="내 인사", body="강민준의 인사말입니다.",
                                 is_active=1)
    remind_team = MessageTemplate(user_id=None, kind="closing_remind", name="리마인드",
                                  body="리마인드 팀 문구입니다.", is_active=1)
    db.add_all([a, b, mine, other_kind, remind_team])
    db.commit()
    db.add_all([
        TemplateChoice(user_id=people["u1"].id, kind=KIND, variant="",
                       template_id=mine.id),
        TemplateChoice(user_id=people["u2"].id, kind=KIND, variant="",
                       template_id=b.id),
    ])
    db.commit()
    return {"a": a.id, "b": b.id, "mine": mine.id, "other_kind": other_kind.id,
            "remind_team": remind_team.id}


def _choices(db, kind=KIND, variant=""):
    from app.models import TemplateChoice

    db.expire_all()
    return {c.user_id: c.template_id for c in db.query(TemplateChoice)
            .filter_by(kind=kind, variant=variant).all()}


def _active(db, template_id):
    from app.models import MessageTemplate

    db.expire_all()
    return db.get(MessageTemplate, template_id).is_active


def _backups(db):
    from app.models import TemplateApplyBackup

    db.expire_all()
    return db.query(TemplateApplyBackup).order_by(TemplateApplyBackup.id).all()


def _apply(client, template_id, **form):
    return client.post(f"/templates/{template_id}/apply-all", data=form,
                       follow_redirects=False)


def _undo(client, backup_id):
    return client.post(f"/templates/apply-all/{backup_id}/undo",
                       follow_redirects=False)


def _msg(response) -> str:
    from urllib.parse import parse_qs, urlparse

    return parse_qs(urlparse(response.headers["location"]).query).get("msg", [""])[0]


def _confirm_for(page: str, template_id: int) -> str:
    """그 문구의 [모든 팀원에게 적용] 단추가 띄우는 확인창 글."""
    flat = re.sub(r"\s+", " ", page)
    m = re.search(r'formaction="/templates/%d/apply-all" '
                  r"onclick='return confirm\((.*?)\)'" % template_id, flat)
    assert m, f"{template_id} 의 적용 단추가 없다"
    return json.loads(html.unescape(m.group(1)))


# ═══════════════════════════════════════════════════════════════════════════
# ① 누구에게 · 어느 문구에
# ═══════════════════════════════════════════════════════════════════════════

def test_관리자는_정해_둔_종류의_팀_문구에서만_적용_단추를_본다(portal, db, people, stage):
    from app.models import MessageTemplate

    opening = MessageTemplate(user_id=None, kind="opening_first", name="기본 인사",
                              body="안녕하세요 팀 인사입니다.", is_active=1)
    sourcing = MessageTemplate(user_id=None, kind="sourcing_intro", name="시리즈 A 이상",
                               body="[시리즈 A 이상] 갈래 문구입니다.", is_active=1)
    db.add_all([opening, sourcing])
    db.commit()

    page = portal["admin"].get("/templates")
    assert page.status_code == 200
    body = page.text
    for tid in (stage["a"], stage["b"], opening.id, sourcing.id):
        assert f'formaction="/templates/{tid}/apply-all"' in body, tid
    # 정해 두지 않은 종류의 팀 문구 · 남의 개인 문구에는 없다
    for tid in (stage["remind_team"], stage["mine"], stage["other_kind"]):
        assert f"/templates/{tid}/apply-all" not in body, tid


def test_팀원은_단추를_못_보고_눌러도_403(portal, db, people, stage):
    body = portal["u1"].get("/templates").text
    assert "apply-all" not in body
    assert "모든 팀원에게 적용" not in body

    before = _choices(db)
    r = _apply(portal["u1"], stage["a"])
    assert r.status_code == 403
    assert _choices(db) == before
    assert _active(db, stage["mine"]) == 1
    assert _backups(db) == []


def test_팀원은_되돌리기도_403(portal, db, people, stage):
    assert _apply(portal["admin"], stage["a"]).status_code == 303
    backup = _backups(db)[0]
    r = _undo(portal["u2"], backup.id)
    assert r.status_code == 403
    assert _backups(db)[0].restored_at is None
    assert _choices(db)[people["u1"].id] == stage["a"]


def test_적용할_수_없는_문구는_400(portal, db, people, stage):
    from app.models import MessageTemplate

    off = MessageTemplate(user_id=None, kind=KIND, name="꺼진 팀", body="꺼짐",
                          is_active=0)
    db.add(off)
    db.commit()
    for tid in (stage["remind_team"],     # 정해 두지 않은 종류
                stage["mine"],            # 개인 문구
                off.id):                  # 꺼진 팀 문구
        assert _apply(portal["admin"], tid).status_code == 400, tid
    assert _apply(portal["admin"], 999999).status_code == 404
    assert _backups(db) == []


def test_종류_목록은_한_곳이고_화면에_있는_종류다():
    """종류를 늘릴 때 고칠 곳이 하나여야 한다 — 단추 · 막기 · 되돌리기가 같은 목록을 읽는다."""
    from app.routers import templates_crud
    from app.services import template_apply

    assert set(template_apply.KINDS) == {
        "sourcing_intro", "opening_first", "opening_re", "closing_day1"}
    assert set(template_apply.KINDS) <= set(templates_crud.KIND_LABELS)


# ═══════════════════════════════════════════════════════════════════════════
# ② 확인창의 숫자 == 실제
# ═══════════════════════════════════════════════════════════════════════════

def test_확인창의_숫자가_실제로_바뀌는_것과_같다(portal, db, people, stage):
    """관리자(안 고름) · u1(제 문구) · u2(B) — 셋이 바뀌고, u1 의 개인 문구 하나가 꺼진다.
    투자컨설턴트와 정지된 계정은 세지 않는다."""
    page = portal["admin"].get("/templates").text
    text = _confirm_for(page, stage["a"])
    assert "팀원 3명의 선택이 이 문구로 바뀌고" in text
    assert "개인 문구 1개가 꺼집니다" in text
    assert "되돌릴 수 있게 먼저 백업합니다" in text
    assert "관리자 계정의 선택도 함께 바뀝니다" in text
    assert "팀원 3명의 선택 · 개인 문구 1개가 바뀝니다" in re.sub(r"\s+", " ", page)

    r = _apply(portal["admin"], stage["a"])
    assert r.status_code == 303
    assert "선택 3명 · 개인 문구 1개 꺼짐" in _msg(r)
    from app.services import template_apply

    assert template_apply.counts(_backups(db)[0]) == (3, 1)
    changed = {uid for uid, tid in _choices(db).items() if tid == stage["a"]}
    assert changed == {people["admin"].id, people["u1"].id, people["u2"].id}


def test_바뀔_것이_없으면_적지_않고_단추_대신_알린다(portal, db, people, stage):
    assert _apply(portal["admin"], stage["a"]).status_code == 303
    r = _apply(portal["admin"], stage["a"])
    assert r.status_code == 303
    assert "바뀔 것이 없습니다" in _msg(r)
    assert len(_backups(db)) == 1

    page = portal["admin"].get("/templates").text
    assert f'formaction="/templates/{stage["a"]}/apply-all"' not in page
    assert "모든 팀원이 이미 이 문구를 씁니다" in page
    # 같은 자리의 다른 팀 문구에는 여전히 단추가 있다 — u1 의 개인 문구는 이미
    # 꺼져 있어 선택만 바뀐다. 0 인 쪽은 말하지 않는다.
    text = _confirm_for(page, stage["b"])
    assert "팀원 3명의 선택이 이 문구로 바뀝니다" in text
    assert "개인 문구" not in text
    assert "팀원 3명의 선택이 바뀝니다" in page


def test_선택은_그대로이고_개인_문구만_꺼질_때도_그렇게_묻는다(portal, db, people, stage):
    """모두 이미 이 문구를 골랐는데 누가 새 개인 문구를 만들었다 — 선택은 안 바뀌고
    그 문구만 꺼진다. 그래도 덮는 일이라 백업을 남긴다."""
    assert _apply(portal["admin"], stage["a"]).status_code == 303
    r = portal["u1"].post("/templates/new", data={"kind": KIND, "name": "새 내 문구",
                                                  "body": "적용 뒤에 새로 만든 문구"},
                          follow_redirects=False)
    assert r.status_code == 303

    page = portal["admin"].get("/templates").text
    text = _confirm_for(page, stage["a"])
    assert text.startswith("팀원의 선택은 이미 모두 이 문구이고, 개인 문구 1개가 꺼집니다")
    r = _apply(portal["admin"], stage["a"])
    assert "선택 0명 · 개인 문구 1개 꺼짐" in _msg(r)
    assert len(_backups(db)) == 2


def test_고친_채로_누르면_적용하지_않는다(portal, db, people, stage):
    """적용되는 것은 저장된 문구다 — 화면에 고친 글이 떠 있는 채로 덮으면 무엇이
    나갔는지 어긋난다."""
    r = _apply(portal["admin"], stage["a"], name="가", body=TEAM_A + " 고침")
    assert r.status_code == 303
    assert "먼저 [저장]" in _msg(r)
    assert _backups(db) == []
    assert _choices(db)[people["u1"].id] == stage["mine"]

    # 저장된 그대로(브라우저가 보내는 \r\n 이어도) 보내면 적용된다
    r = _apply(portal["admin"], stage["a"], name="가", body=TEAM_A + "\r\n")
    assert "모든 팀원에게 적용했습니다" in _msg(r)


def test_본문을_다_지운_채_누르면_적용하지_않는다(portal, db, people, stage):
    """빈 칸도 고친 것이다 — 칸이 안 온 것(저장된 문구 적용)과 섞이면 안 된다."""
    r = _apply(portal["admin"], stage["a"], name="가", body="")
    assert "먼저 [저장]" in _msg(r)
    assert _backups(db) == []
    assert _choices(db)[people["u1"].id] == stage["mine"]


# ═══════════════════════════════════════════════════════════════════════════
# ③ 적용하면
# ═══════════════════════════════════════════════════════════════════════════

def test_적용하면_모두에게_이_문구가_나간다(portal, db, people, stage):
    from app.services import template_pick

    assert _apply(portal["admin"], stage["a"]).status_code == 303

    choices = _choices(db)
    for key in ("admin", "u1", "u2"):
        assert choices[people[key].id] == stage["a"], key
        assert template_pick.pick(db, people[key].id, KIND).id == stage["a"], key
    # 보낼 문구가 없는 계정 · 정지된 계정에는 선택을 만들지 않는다
    assert people["consultant"].id not in choices
    assert people["sleeper"].id not in choices

    # 그 자리의 개인 문구는 꺼지되 지우지 않는다 · 다른 팀 문구는 그대로
    assert _active(db, stage["mine"]) == 0
    assert _active(db, stage["b"]) == 1
    # 다른 자리(다른 종류)는 건드리지 않는다
    assert _active(db, stage["other_kind"]) == 1
    assert template_pick.pick(db, people["u1"].id, "opening_first").id == stage["other_kind"]

    # 죽은 선택을 남기지 않는다 — 화면을 열 때 치울 것이 없다
    for key in ("admin", "u1", "u2"):
        assert template_pick.prune(db, people[key].id) == 0


def test_딜_소싱은_그_갈래만_덮는다(portal, db, people):
    from app.models import MessageTemplate, TemplateChoice
    from app.services import template_pick

    one, two = "시리즈 A 이상", "M&A 찾는 투자사"
    team_one = MessageTemplate(user_id=None, kind="sourcing_intro", name=one,
                               body=f"[{one}] 팀 문구", is_active=1)
    team_two = MessageTemplate(user_id=None, kind="sourcing_intro", name=two,
                               body=f"[{two}] 팀 문구", is_active=1)
    mine_one = MessageTemplate(user_id=people["u1"].id, kind="sourcing_intro",
                               name=one, body=f"[{one}] 내 문구", is_active=1)
    mine_two = MessageTemplate(user_id=people["u1"].id, kind="sourcing_intro",
                               name=two, body=f"[{two}] 내 문구", is_active=1)
    db.add_all([team_one, team_two, mine_one, mine_two])
    db.commit()
    db.add(TemplateChoice(user_id=people["u1"].id, kind="sourcing_intro",
                          variant=two, template_id=mine_two.id))
    db.commit()

    page = portal["admin"].get("/templates").text
    assert "개인 문구 1개가 꺼집니다" in _confirm_for(page, team_one.id)
    assert _apply(portal["admin"], team_one.id).status_code == 303

    assert _active(db, mine_one.id) == 0
    assert _active(db, mine_two.id) == 1
    assert _choices(db, "sourcing_intro", two) == {people["u1"].id: mine_two.id}
    assert _choices(db, "sourcing_intro", one)[people["u1"].id] == team_one.id
    assert template_pick.pick(db, people["u1"].id, "sourcing_intro", one).id == team_one.id
    assert template_pick.pick(db, people["u1"].id, "sourcing_intro", two).id == mine_two.id
    assert _backups(db)[0].variant == one


def test_정지된_계정이_고른_개인_문구도_빈_선택으로_남기지_않는다(portal, db, people, stage):
    """정지된 계정은 덮을 대상이 아니지만, 그 사람이 고른 개인 문구를 끄면
    꺼진 문구를 가리키는 선택이 남는다 — 그 선택도 옮기고 되돌릴 때 돌린다."""
    from app.models import MessageTemplate, TemplateChoice
    from app.services import template_pick

    theirs = MessageTemplate(user_id=people["sleeper"].id, kind=KIND, name="쉬는 문구",
                             body="정지된 계정의 문구", is_active=1)
    db.add(theirs)
    db.commit()
    db.add(TemplateChoice(user_id=people["sleeper"].id, kind=KIND, variant="",
                          template_id=theirs.id))
    db.commit()

    assert _apply(portal["admin"], stage["a"]).status_code == 303
    assert _choices(db)[people["sleeper"].id] == stage["a"]
    assert template_pick.prune(db, people["sleeper"].id) == 0

    assert _undo(portal["admin"], _backups(db)[0].id).status_code == 303
    assert _choices(db)[people["sleeper"].id] == theirs.id
    assert _active(db, theirs.id) == 1


# ═══════════════════════════════════════════════════════════════════════════
# ④ 백업 · 수정 로그
# ═══════════════════════════════════════════════════════════════════════════

def test_백업에_덮기_전_상태가_남는다(portal, db, people, stage):
    assert _apply(portal["admin"], stage["a"]).status_code == 303
    [backup] = _backups(db)
    assert backup.user_id == people["admin"].id
    assert (backup.kind, backup.variant, backup.template_id) == (KIND, "", stage["a"])
    assert backup.created_at and backup.restored_at is None
    previous = {p["user_id"]: p["template_id"] for p in json.loads(backup.previous_json)}
    assert previous == {people["u1"].id: stage["mine"],
                        people["u2"].id: stage["b"],
                        people["admin"].id: None}     # 안 고른 사람은 null
    assert [t["id"] for t in json.loads(backup.turned_off_json)] == [stage["mine"]]


def test_남의_개인_문구를_끄고_켠_것이_수정_로그에_남는다(portal, db, people, stage):
    from app.models import EditLog

    assert _apply(portal["admin"], stage["a"]).status_code == 303
    db.expire_all()
    logs = db.query(EditLog).filter_by(table_name="message_templates",
                                       row_id=stage["mine"]).all()
    assert len(logs) == 1
    log = logs[0]
    assert (log.scope, log.actor_user_id, log.target_user_id) == (
        "others", people["admin"].id, people["u1"].id)
    changes = {c["field"]: (c.get("before"), c.get("after"))
               for c in json.loads(log.changes_json)}
    assert changes["is_active"] == (1, 0)

    assert _undo(portal["admin"], _backups(db)[0].id).status_code == 303
    db.expire_all()
    logs = db.query(EditLog).filter_by(table_name="message_templates",
                                       row_id=stage["mine"]).order_by(EditLog.id).all()
    assert len(logs) == 2
    changes = {c["field"]: (c.get("before"), c.get("after"))
               for c in json.loads(logs[1].changes_json)}
    assert changes["is_active"] == (0, 1)


# ═══════════════════════════════════════════════════════════════════════════
# ⑤ 되돌리기
# ═══════════════════════════════════════════════════════════════════════════

def test_되돌리면_전_선택과_개인_문구가_돌아온다(portal, db, people, stage):
    from app.services import template_pick

    assert _apply(portal["admin"], stage["a"]).status_code == 303
    page = portal["admin"].get("/templates").text
    backup = _backups(db)[0]
    # 언제 · 누가 · 어느 문구로 덮었는지가 [되돌리기] 옆에 있다
    assert f'action="/templates/apply-all/{backup.id}/undo"' in page
    assert "관리자시험 님이 ‘가’ 문구를 모든 팀원에게" in re.sub(r"\s+", " ", page)
    assert backup.created_at[:16].replace("T", " ") in page

    r = _undo(portal["admin"], backup.id)
    assert r.status_code == 303
    assert "되돌렸습니다 — 선택 3명 · 개인 문구 1개" in _msg(r)
    assert "그대로 두었습니다" not in _msg(r)

    assert _choices(db) == {people["u1"].id: stage["mine"], people["u2"].id: stage["b"]}
    assert _active(db, stage["mine"]) == 1
    assert template_pick.pick(db, people["u1"].id, KIND).id == stage["mine"]
    assert template_pick.pick(db, people["u2"].id, KIND).id == stage["b"]
    # 관리자는 다시 '고른 것 없음' — 팀 문구가 둘이라 코드 폴백으로 돌아간다
    assert template_pick.pick(db, people["admin"].id, KIND) is None
    assert _backups(db)[0].restored_at
    # 되돌린 뒤에는 [되돌리기] 가 사라진다
    assert "/templates/apply-all/" not in portal["admin"].get("/templates").text


def test_되돌리기는_두_번_안_된다(portal, db, people, stage):
    assert _apply(portal["admin"], stage["a"]).status_code == 303
    backup_id = _backups(db)[0].id
    assert _undo(portal["admin"], backup_id).status_code == 303

    # 되돌린 뒤 u1 이 다시 팀 문구 A 를 골랐다 — 두 번째 되돌리기가 이것을 덮으면 안 된다
    portal["u1"].post("/templates/choose", data={"kind": KIND, "template_id": stage["a"]})
    r = _undo(portal["admin"], backup_id)
    assert r.status_code == 303
    assert "이미 되돌린" in _msg(r)
    assert _choices(db)[people["u1"].id] == stage["a"]
    assert _undo(portal["admin"], 999999).status_code == 404


def test_그_사이_다시_고르거나_고친_것은_건드리지_않는다(portal, db, people, stage):
    from app.models import MessageTemplate

    assert _apply(portal["admin"], stage["a"]).status_code == 303
    # u2 가 다시 B 를 골랐다 · u1 이 꺼진 제 문구를 고쳤다
    portal["u2"].post("/templates/choose", data={"kind": KIND, "template_id": stage["b"]})
    r = portal["u1"].post(f"/templates/{stage['mine']}/edit",
                          data={"name": "내 문구", "body": "적용 뒤에 고친 문구"},
                          follow_redirects=False)
    assert r.status_code == 303

    r = _undo(portal["admin"], _backups(db)[0].id)
    assert r.status_code == 303
    # 관리자 하나만 돌아갔다. 건너뛴 셋: u2 의 새 선택 · 고친 u1 문구 · 그 문구를
    # 가리키던 u1 의 전 선택(꺼진 채라 고를 수 없다)
    assert "선택 1명 · 개인 문구 0개" in _msg(r)
    assert "그 사이 바뀐 3건은 그대로 두었습니다" in _msg(r)

    choices = _choices(db)
    assert choices[people["u2"].id] == stage["b"]
    assert choices[people["u1"].id] == stage["a"]        # 살아 있는 문구에 그대로
    assert people["admin"].id not in choices
    db.expire_all()
    mine = db.get(MessageTemplate, stage["mine"])
    assert (mine.is_active, mine.body) == (0, "적용 뒤에 고친 문구")


def test_지웠거나_이미_다시_켠_개인_문구는_건너뛴다(portal, db, people, stage):
    from app.models import MessageTemplate

    theirs = MessageTemplate(user_id=people["u2"].id, kind=KIND, name="윤서아 문구",
                             body="윤서아의 안내문", is_active=1)
    db.add(theirs)
    db.commit()
    theirs_id = theirs.id

    assert _apply(portal["admin"], stage["a"]).status_code == 303
    assert _active(db, theirs_id) == 0
    # u2 는 제 꺼진 문구를 지웠고, u1 의 문구는 손질로 이미 다시 켜졌다
    assert portal["u2"].post(f"/templates/{theirs_id}/delete",
                             follow_redirects=False).status_code == 303
    db.get(MessageTemplate, stage["mine"]).is_active = 1
    db.commit()

    r = _undo(portal["admin"], _backups(db)[0].id)
    assert "개인 문구 0개" in _msg(r)
    db.expire_all()
    assert db.get(MessageTemplate, theirs_id) is None
    # u1 의 전 선택(제 문구)은 다시 켜져 있으니 돌아간다
    assert _choices(db)[people["u1"].id] == stage["mine"]


def test_나중에_적용한_것부터_되돌린다(portal, db, people, stage):
    """A 를 적용하고 B 를 적용했으면 B 의 '전' 이 A 다 — 차례를 거꾸로만 된다."""
    assert _apply(portal["admin"], stage["a"]).status_code == 303
    assert _apply(portal["admin"], stage["b"]).status_code == 303
    first, second = _backups(db)

    r = _undo(portal["admin"], first.id)
    assert "더 나중에 적용한 것" in _msg(r)
    assert _backups(db)[0].restored_at is None
    # 화면에는 마지막 것만 되돌리라고 띄운다
    page = portal["admin"].get("/templates").text
    assert f"/templates/apply-all/{second.id}/undo" in page
    assert f"/templates/apply-all/{first.id}/undo" not in page

    assert _undo(portal["admin"], second.id).status_code == 303
    assert set(_choices(db).values()) == {stage["a"]}
    assert _undo(portal["admin"], first.id).status_code == 303
    assert _choices(db) == {people["u1"].id: stage["mine"], people["u2"].id: stage["b"]}
    assert _active(db, stage["mine"]) == 1


def test_갈래_이름을_바꾸면_되돌릴_버퍼도_따라간다(portal, db, people):
    """갈래 이름은 문구 · 선택 · 버퍼가 같은 글자로 잇는다 — 버퍼만 옛 이름에 남으면
    새 이름 갈래에서 [되돌리기] 가 사라진다."""
    from app.models import MessageTemplate, SourcingContact
    from app.services import sourcing_buckets

    db.add(SourcingContact(bucket="옛 갈래", name="소싱담당", firm="가나벤처스"))
    team = MessageTemplate(user_id=None, kind="sourcing_intro", name="옛 갈래",
                           body="옛 갈래 문구", is_active=1)
    db.add(team)
    db.commit()
    assert _apply(portal["admin"], team.id).status_code == 303

    sourcing_buckets.rename(db, "옛 갈래", "새 갈래")
    db.commit()
    assert _backups(db)[0].variant == "새 갈래"
    r = _undo(portal["admin"], _backups(db)[0].id)
    assert "되돌렸습니다" in _msg(r)
    assert _choices(db, "sourcing_intro", "새 갈래") == {}


# ═══════════════════════════════════════════════════════════════════════════
# 화면
# ═══════════════════════════════════════════════════════════════════════════

def test_적용_뒤에도_화면이_관리자와_팀원_모두에게_열린다(portal, db, people, stage):
    assert _apply(portal["admin"], stage["a"]).status_code == 303
    for who in ("admin", "u1", "u2"):
        assert portal[who].get("/templates").status_code == 200, who
    # 제 문구가 왜 안 나가는지 보인다
    body = portal["u1"].get("/templates").text
    assert "꺼진 문구 — 발송에 쓰이지 않습니다" in body
    # 팀원에게는 [되돌리기] 도 없다
    assert "/templates/apply-all/" not in body


# ═══════════════════════════════════════════════════════════════════════════
# ⑥ 판(0103)
# ═══════════════════════════════════════════════════════════════════════════

def _tables(db_path) -> set:
    con = sqlite3.connect(db_path)
    try:
        return {r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        con.close()


def test_되돌릴_버퍼_판은_머리_뒤에_표를_세우고_되돌리면_지운다(tmp_path):
    db_path = tmp_path / "m.db"
    done = _alembic(db_path, "upgrade", "0100_sender_rooms")
    assert done.returncode == 0, done.stdout + done.stderr
    # 운영 DB 는 이 표가 없는 채로 출발한다(0001 의 create_all 은 이미 표가 있다)
    con = sqlite3.connect(db_path)
    try:
        con.execute("DROP TABLE template_apply_backups")
        con.commit()
    finally:
        con.close()
    assert "template_apply_backups" not in _tables(db_path)

    done = _alembic(db_path, "upgrade", "0103_template_apply_backups")
    assert done.returncode == 0, done.stdout + done.stderr
    con = sqlite3.connect(db_path)
    try:
        cols = {r[1] for r in con.execute('PRAGMA table_info("template_apply_backups")')}
    finally:
        con.close()
    assert cols == {"id", "user_id", "kind", "variant", "template_id", "previous_json",
                    "turned_off_json", "restored_at", "created_at", "updated_at"}

    done = _alembic(db_path, "downgrade", "0100_sender_rooms")
    assert done.returncode == 0, done.stdout + done.stderr
    assert "template_apply_backups" not in _tables(db_path)
