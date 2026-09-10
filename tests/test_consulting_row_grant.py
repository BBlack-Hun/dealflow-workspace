"""**이 컨설턴트의 줄을 고칠 수 있는 사람**을 관리자가 지정한다.

지금까지 투자컨설턴트 현황의 고치는 범위는 둘뿐이었다 — 관리자는 전부,
나머지는 자기 줄만(`routers/consulting.py` 의 `may_edit_row`). 그 사이가
없어서, 특정 컨설턴트의 시트를 팀원 둘이 함께 손보게 하려면 그 둘을 관리자로
올리는 수밖에 없었다(그러면 **모든** 컨설턴트의 줄이 열린다).

    관리자          전체를 본다 · 전체를 고친다
    팀원(허용됨)    팀 전체를 본다 · 자기 줄과 **맡은 담당자의 줄**을 고친다   ← 새로 생긴 층
    투자컨설턴트    자기 줄만 본다 · 자기 줄만 고친다   (개인 표다)

이 파일이 잠그는 것은 넷이다.

  1. **맡은 만큼만.** 맡긴 담당자의 줄은 고쳐지고 다른 담당자의 줄은 그대로
     막힌다. 안 맡긴 팀원은 지금까지와 똑같다.
  2. **화면과 서버가 같다.** 고칠 수 있게 그려 놓고 누르면 404 가 나거나 그
     반대가 되면 안 된다 — `tests/test_consulting_ownership.py` 가 쓰는 그
     훑기를 그대로 가져와 견준다(규칙을 옮겨 적으면 두 벌이 된다).
  3. **컨설턴트에게는 이 길이 없다.** 그 화면은 각자의 개인 표이고 서로를
     덮는다(`deps.may_view_all_consulting`). 맡겨 줘도 남의 줄에 닿으면 안 된다.
  4. **고친 것이 수정 로그에 남는다.** 이 권한으로 고치는 것은 정확히 `남의
     것` 이다 — 권한을 넓히는 근거가 로그였으므로, 안 남으면 이 기능의 가장
     큰 구멍이다.

**상태 코드만 보지 않는다.** 막혔다는 검사는 값을 되읽어 확인한다 — 404 를
주면서 값은 바꿔 두는 것이 가장 나쁜 실패다(옆 파일과 같은 규칙이다).
"""
from __future__ import annotations

import pytest

from .conftest import DEMO_PASSWORD
from .test_consulting_ownership import (PROBE, _can_edit_row,
                                        _can_rename_column, _editable_columns,
                                        _editable_rows, _visible_rows)

# 로그인 번호. 옆 파일과 겹치지 않게 뒤 두 자리를 따로 쓴다.
PHONES = {
    "member": "01000000001",      # conftest 의 u1
    "other": "01000000002",       # conftest 의 u2 — 맡은 것이 없는 팀원
    "consultant_a": "01000000091",
    "consultant_b": "01000000092",
    "admin": "01000000093",
}


@pytest.fixture()
def stage(db, users):
    """컨설턴트 둘, 팀원 둘, 관리자 하나 — 그리고 각자의 줄.

    컨설턴트가 **둘**이어야 이 검사가 뜻이 있다. 하나뿐이면 `맡은 사람의 줄만`
    과 `남의 줄 전부` 가 같은 집합이라, 맡기는 단위가 `컨설턴트 한 사람` 인지
    `남의 줄 전체` 인지를 가릴 수가 없다.
    """
    from app.models import ConsultingColumn, ConsultingCompany, User
    from app.services import auth as auth_svc

    pw = auth_svc.hash_password(DEMO_PASSWORD)
    member, other = users["u1"], users["u2"]
    member.can_view_consulting = 1
    other.can_view_consulting = 1
    people = {"member": member, "other": other}
    for key, role in (("consultant_a", "consultant"), ("consultant_b", "consultant"),
                      ("admin", "admin")):
        people[key] = User(name=f"{key}시험", phone=PHONES[key], role=role,
                           can_view_consulting=1, password_hash=pw)
        db.add(people[key])
    db.commit()

    rows = {}
    for key, who in people.items():
        rows[key] = ConsultingCompany(user_id=who.id, company_name=f"샘플기업-{key}",
                                      region=f"지역-{key}", position=1)
        db.add(rows[key])
    # 주인 없는 줄 — 맡긴다고 해서 여기까지 열리면 안 된다(배정 전이라는 뜻이다).
    rows["unassigned"] = ConsultingCompany(user_id=None, company_name="샘플기업-미배정",
                                           region="지역-미배정", position=1)
    db.add(rows["unassigned"])
    db.add(ConsultingColumn(label="8월 리마인드", position=0))
    db.commit()
    return {"people": people, "rows": rows}


@pytest.fixture()
def sign_in(db, users):
    """역할 이름 → 그 사람으로 로그인한 클라이언트(사람마다 따로)."""
    from fastapi.testclient import TestClient

    from app.main import create_app

    app = create_app()

    def _open(who: str):
        client = TestClient(app)
        r = client.post("/login", data={"phone": PHONES[who], "password": DEMO_PASSWORD},
                        follow_redirects=False)
        assert r.status_code == 303
        return client

    _open.app = app
    return _open


def grant(db, owner_id: int, editor_id: int):
    """맡긴다 — 화면을 안 지나는 지름길(화면 쪽은 따로 검사한다)."""
    from app.models import ConsultingRowGrant

    db.add(ConsultingRowGrant(user_id=owner_id, editor_user_id=editor_id))
    db.commit()


def _grants(db) -> set:
    from app.models import ConsultingRowGrant

    db.expire_all()
    return {(g.user_id, g.editor_user_id)
            for g in db.query(ConsultingRowGrant).all()}


# ═══════════════════════════════════════════════════════════════════════════
# 1. 맡은 만큼만
# ═══════════════════════════════════════════════════════════════════════════

def test_a_granted_member_edits_that_consultants_rows(stage, sign_in, db):
    """맡긴 담당자의 줄은 고쳐진다 — 되읽어 확인한다."""
    grant(db, stage["people"]["consultant_a"].id, stage["people"]["member"].id)
    assert _can_edit_row(sign_in("member"), db, stage["rows"]["consultant_a"].id)


def test_the_grant_does_not_reach_the_other_consultant(stage, sign_in, db):
    """**맡기는 단위는 담당자 한 사람이다.** 여기가 이 기능의 알맹이다.

    이것이 깨지면 `한 사람의 시트를 맡긴다` 가 `남의 줄 전부를 연다` 가 된다 —
    관리자로 올리는 것과 다를 바가 없어져 기능이 있을 이유가 사라진다.
    """
    grant(db, stage["people"]["consultant_a"].id, stage["people"]["member"].id)
    client = sign_in("member")
    assert _can_edit_row(client, db, stage["rows"]["consultant_a"].id)
    assert not _can_edit_row(client, db, stage["rows"]["consultant_b"].id)
    assert not _can_edit_row(client, db, stage["rows"]["other"].id)


def test_the_grant_does_not_open_the_unassigned_rows(stage, sign_in, db):
    """주인 없는 줄은 여전히 아무도 못 고친다.

    맡기는 단위가 **사람**이라 주인이 없는 줄에는 맡길 상대가 없다. 배정할
    것이 남았다는 뜻이지, 먼저 본 사람이 갖는 것이 아니다.
    """
    grant(db, stage["people"]["consultant_a"].id, stage["people"]["member"].id)
    assert not _can_edit_row(sign_in("member"), db, stage["rows"]["unassigned"].id)


def test_a_member_without_a_grant_is_unchanged(stage, sign_in, db):
    """안 맡긴 팀원에게는 아무 것도 안 달라진다."""
    grant(db, stage["people"]["consultant_a"].id, stage["people"]["member"].id)
    client = sign_in("other")
    assert not _can_edit_row(client, db, stage["rows"]["consultant_a"].id)
    assert not _can_edit_row(client, db, stage["rows"]["consultant_b"].id)
    # 자기 줄은 그대로 고쳐진다 — 막는 김에 자기 것까지 막지 않았는가.
    assert _can_edit_row(client, db, stage["rows"]["other"].id)


def test_two_members_can_be_granted_on_the_same_consultant(stage, sign_in, db):
    """사용자가 원한 그 모양 — **팀원 둘**에게 한 사람의 시트를 맡긴다."""
    owner = stage["people"]["consultant_a"].id
    grant(db, owner, stage["people"]["member"].id)
    grant(db, owner, stage["people"]["other"].id)
    row = stage["rows"]["consultant_a"].id
    assert _can_edit_row(sign_in("member"), db, row)
    assert _can_edit_row(sign_in("other"), db, row)


def test_a_deletion_follows_the_same_rule(stage, sign_in, db):
    """지우는 것도 같은 판정 하나를 지난다(`owned()`)."""
    from app.models import ConsultingCompany

    grant(db, stage["people"]["consultant_a"].id, stage["people"]["member"].id)
    client = sign_in("member")
    mine = stage["rows"]["consultant_b"].id
    assert client.delete(f"/api/consulting/{mine}").status_code == 404
    db.expire_all()
    assert db.get(ConsultingCompany, mine) is not None

    theirs = stage["rows"]["consultant_a"].id
    assert client.delete(f"/api/consulting/{theirs}").status_code == 200
    db.expire_all()
    assert db.get(ConsultingCompany, theirs) is None


# ═══════════════════════════════════════════════════════════════════════════
# 2. 화면이 그리는 것과 서버가 막는 것이 같다
# ═══════════════════════════════════════════════════════════════════════════

def test_the_screen_marks_exactly_the_rows_a_grantee_can_edit(stage, sign_in, db):
    """옆 파일의 뼈대를 그대로 가져온다 — **훑어서 견준다.**

    줄을 손으로 나열하면 줄이 하나 늘 때 그 줄만 조용히 검사 밖으로 빠진다.
    `data-readonly` 가 붙지 않은 줄(=화면이 고칠 수 있다고 그린 줄)과 실제로
    고쳐지는 줄이 **같은 집합**이어야 한다.
    """
    from app.models import ConsultingCompany

    grant(db, stage["people"]["consultant_a"].id, stage["people"]["member"].id)
    client = sign_in("member")
    seen = _visible_rows(client)
    marked = _editable_rows(client)
    everything = {r.id for r in db.query(ConsultingCompany).all()}
    assert seen, "화면에 아무 줄도 없다 — 검사가 헛돈다"
    # 맡긴 줄이 실제로 `고칠 수 있음` 으로 그려져 있어야 검사가 뜻이 있다.
    assert stage["rows"]["consultant_a"].id in marked
    # 그리고 **못 고치는 줄이 반드시 남는다** — 다 열린 상태로 통과하면
    # 이 검사는 아무 것도 안 밟는다.
    assert everything - marked

    editable = {rid for rid in everything if _can_edit_row(client, db, rid)}
    assert editable == marked, (
        f"화면이 고칠 수 있다고 그린 줄 {sorted(marked)} 과 "
        f"실제로 고쳐지는 줄 {sorted(editable)} 이 다르다")
    assert editable <= seen, f"화면에 안 뜨는 줄이 고쳐진다 {sorted(editable - seen)}"


def test_the_screen_stops_marking_when_the_grant_is_taken_away(stage, sign_in, db):
    """뺀 뒤에는 화면도 서버도 **같이** 닫힌다."""
    from app.models import ConsultingRowGrant

    owner = stage["people"]["consultant_a"].id
    grant(db, owner, stage["people"]["member"].id)
    row = stage["rows"]["consultant_a"].id
    assert row in _editable_rows(sign_in("member"))

    db.query(ConsultingRowGrant).delete()
    db.commit()
    assert row not in _editable_rows(sign_in("member"))
    assert not _can_edit_row(sign_in("member"), db, row)


# ═══════════════════════════════════════════════════════════════════════════
# 3. 보기 권한과의 관계 — **못 보면 못 고친다**
# ═══════════════════════════════════════════════════════════════════════════

def test_a_grant_is_inert_while_the_screen_is_switched_off(stage, sign_in, db):
    """`투자현황` 을 끄면 맡긴 것도 **같이** 멎는다.

    이 관계를 이렇게 정한 이유. 관리자가 팀 현황에서 투자현황을 끄면 그 사람은
    이 화면에 못 들어온다(`require_access`). 그때 맡긴 것만 살아 있으면 **막아
    둔 줄 알았던 사람이 주소로 남의 줄을 계속 고친다** — 화면이 거짓말을 하는,
    이 저장소가 반복해 겪은 그 자리다.

    조건을 새로 적지 않고 `deps.may_view_all_consulting` 을 그대로 태워서
    답하므로(`may_edit_row`), 보는 사람이 늘거나 줄면 여기도 같이 움직인다.
    """
    grant(db, stage["people"]["consultant_a"].id, stage["people"]["member"].id)
    row = stage["rows"]["consultant_a"].id
    assert _can_edit_row(sign_in("member"), db, row)

    stage["people"]["member"].can_view_consulting = 0
    db.commit()
    assert not _can_edit_row(sign_in("member"), db, row)


def test_switching_the_screen_back_on_brings_the_grant_back(stage, sign_in, db):
    """껐다 켜면 그대로 돌아온다 — 끄는 것이 맡긴 것을 **지우지는 않는다.**"""
    grant(db, stage["people"]["consultant_a"].id, stage["people"]["member"].id)
    row = stage["rows"]["consultant_a"].id
    stage["people"]["member"].can_view_consulting = 0
    db.commit()
    assert not _can_edit_row(sign_in("member"), db, row)
    stage["people"]["member"].can_view_consulting = 1
    db.commit()
    assert _can_edit_row(sign_in("member"), db, row)


# ═══════════════════════════════════════════════════════════════════════════
# 4. 투자컨설턴트에게는 이 길이 없다
# ═══════════════════════════════════════════════════════════════════════════

def test_a_consultant_cannot_reach_another_table_through_a_grant(stage, sign_in, db):
    """맡겨 줘도 컨설턴트는 남의 줄에 못 닿는다 — **보지도, 고치지도** 못한다.

    이 화면은 컨설턴트 한 사람의 개인 표다. 각자 올린 시트가 서로를 덮고
    (월별 리마인드 열이 사람마다 다르다) 남의 담당 기업이 보이면 안 된다
    (`deps.may_view_all_consulting`). 새 권한이 그 벽을 도는 문이 되면 안 된다.
    """
    a, b = stage["people"]["consultant_a"], stage["people"]["consultant_b"]
    grant(db, a.id, b.id)
    client = sign_in("consultant_b")
    row = stage["rows"]["consultant_a"].id
    assert row not in _visible_rows(client), "컨설턴트에게 남의 줄이 보인다"
    assert row not in _editable_rows(client)
    assert not _can_edit_row(client, db, row)


def test_a_consultant_still_edits_their_own_rows(stage, sign_in, db):
    """막는 김에 자기 것까지 막지 않았는가."""
    grant(db, stage["people"]["consultant_a"].id,
          stage["people"]["consultant_b"].id)
    assert _can_edit_row(sign_in("consultant_b"), db,
                         stage["rows"]["consultant_b"].id)


# ═══════════════════════════════════════════════════════════════════════════
# 5. 월 칸은 넓히지 않는다
# ═══════════════════════════════════════════════════════════════════════════

def test_a_grant_does_not_open_the_month_columns(stage, sign_in, db):
    """요청은 **줄**에 대한 것이다 — 칸 이름을 바꾸고 지우는 것은 관리자만.

    칸은 탭에 붙어 있어 주인이 없고, 하나 지우면 그 달 기록이 **팀 전체의
    줄에서** 사라진다(`models.ConsultingColumn`). 맡기는 단위가 `담당자 한
    사람` 인데 칸에는 담당이 없으므로, 맡겨도 열릴 것이 없는 것이 맞다.
    """
    from app.models import ConsultingColumn

    grant(db, stage["people"]["consultant_a"].id, stage["people"]["member"].id)
    client = sign_in("member")
    everything = {c.id for c in db.query(ConsultingColumn).all()}
    assert everything, "칸이 하나도 없다 — 검사가 헛돈다"
    assert _editable_columns(client) == set(), "맡겼더니 [✕] 가 섰다"
    for cid in everything:
        assert not _can_rename_column(client, db, cid)


# ═══════════════════════════════════════════════════════════════════════════
# 6. 주는 것은 관리자만 — 팀 현황
# ═══════════════════════════════════════════════════════════════════════════

def _post_grant(client, owner_id: int, editor_ids):
    return client.post(f"/team/members/{owner_id}/consulting-editors",
                       data={"editor": [str(i) for i in editor_ids]},
                       follow_redirects=False)


def test_only_an_admin_can_hand_out_the_grant(stage, sign_in, db):
    """관리자 말고는 못 준다 — **표를 되읽어** 확인한다.

    상태 코드로 견주지 않는다. 막히는 자리가 사람마다 다르기 때문이다 —
    팀원은 관리자 전용 문에서 403 을 받고(`deps.admin_only`), 투자컨설턴트는
    그 앞의 미들웨어가 `/team` 자체를 허용 목록에 안 넣어 자기 화면으로
    돌려보낸다(`deps.CONSULTANT_PATHS`). 물음은 하나다 — **맡겨졌는가.**
    """
    owner = stage["people"]["consultant_a"].id
    editor = stage["people"]["member"].id
    for who in ("member", "other", "consultant_a"):
        _post_grant(sign_in(who), owner, [editor])
        assert _grants(db) == set(), f"{who} 가 눌렀는데 맡겨졌다"

    assert _post_grant(sign_in("admin"), owner, [editor]).status_code == 303
    assert _grants(db) == {(owner, editor)}


def test_only_an_admin_can_take_the_grant_away(stage, sign_in, db):
    """빼는 쪽도 같은 문이다."""
    owner = stage["people"]["consultant_a"].id
    editor = stage["people"]["member"].id
    grant(db, owner, editor)
    for who in ("member", "other", "consultant_a"):
        _post_grant(sign_in(who), owner, [])
        assert _grants(db) == {(owner, editor)}, f"{who} 가 뺐다"

    assert _post_grant(sign_in("admin"), owner, []).status_code == 303
    assert _grants(db) == set()


def test_the_form_replaces_the_whole_list(stage, sign_in, db):
    """체크상자는 **켜져 있는 것 전부**를 보낸다 — 그대로 갈아 끼운다.

    하나씩 더하고 빼는 길이면 화면에 없는 사람이 서버에만 남을 수 있다.
    """
    owner = stage["people"]["consultant_a"].id
    one, two = stage["people"]["member"].id, stage["people"]["other"].id
    _post_grant(sign_in("admin"), owner, [one, two])
    assert _grants(db) == {(owner, one), (owner, two)}
    _post_grant(sign_in("admin"), owner, [two])
    assert _grants(db) == {(owner, two)}


def test_a_grant_to_oneself_is_not_written_down(stage, sign_in, db):
    """자기 줄은 원래 자기가 고친다 — 줄을 만들 이유가 없다."""
    owner = stage["people"]["consultant_a"].id
    _post_grant(sign_in("admin"), owner, [owner])
    assert _grants(db) == set()


def test_pressing_twice_does_not_leave_two_rows(stage, sign_in, db):
    """같은 짝이 두 줄이면 뺄 때 하나만 지워져 **화면에는 빠졌는데 서버는
    아직 허락하는** 상태가 된다."""
    owner = stage["people"]["consultant_a"].id
    editor = stage["people"]["member"].id
    _post_grant(sign_in("admin"), owner, [editor])
    _post_grant(sign_in("admin"), owner, [editor])
    assert _grants(db) == {(owner, editor)}


# ═══════════════════════════════════════════════════════════════════════════
# 7. 팀 현황이 말하는 것과 실제가 같다
# ═══════════════════════════════════════════════════════════════════════════

def _row(html: str, name: str) -> str:
    rows = [chunk for chunk in html.split("<tr") if f"<b>{name}</b>" in chunk]
    assert rows, f"{name} 줄이 표에 없다"
    return rows[0]


def _grant_cell(row: str) -> str:
    import re

    found = re.search(r'<td class="grant-cell".*?</td>', row, re.S)
    assert found, "줄 편집 허용 칸이 없다"
    return " ".join(re.sub(r"<[^>]+>", " ", found.group(0)).split())


def test_the_team_screen_names_who_may_edit_that_consultants_rows(stage, sign_in, db):
    """맡긴 사람의 이름이 그 담당자 줄에 선다 — 맡긴 뒤에만."""
    people = stage["people"]
    before = _grant_cell(_row(sign_in("admin").get("/team").text,
                              people["consultant_a"].name))
    assert "없음" in before
    assert people["member"].name not in before

    grant(db, people["consultant_a"].id, people["member"].id)
    after = _grant_cell(_row(sign_in("admin").get("/team").text,
                             people["consultant_a"].name))
    assert people["member"].name in after
    # 옆 담당자 줄에는 안 선다 — 맡기는 단위가 사람이라는 것을 화면도 말한다.
    other = _grant_cell(_row(sign_in("admin").get("/team").text,
                             people["consultant_b"].name))
    assert people["member"].name not in other


def test_the_team_screen_says_so_when_a_grant_stopped_working(stage, sign_in, db):
    """맡겨는 두었는데 안 통하는 줄은 **감추지 않고 `막힘` 으로 그린다.**

    감추면 관리자는 맡겨 둔 줄 아는데 그 사람 화면에서는 안 고쳐진다 — 왜
    안 되는지 알 길이 없어진다. 판정은 고치는 함수 하나가 답한다.
    """
    people = stage["people"]
    grant(db, people["consultant_a"].id, people["member"].id)
    cell = _grant_cell(_row(sign_in("admin").get("/team").text,
                            people["consultant_a"].name))
    assert "막힘" not in cell

    people["member"].can_view_consulting = 0
    db.commit()
    cell = _grant_cell(_row(sign_in("admin").get("/team").text,
                            people["consultant_a"].name))
    assert people["member"].name in cell and "막힘" in cell


def _candidates(html: str) -> set:
    import re

    return {int(v) for v in
            re.findall(r'<input type="checkbox" name="editor" value="(\d+)"', html)}


def test_the_picker_offers_only_people_a_grant_would_actually_reach(stage, sign_in, db):
    """세워 두고 눌러도 아무 일이 없는 칸을 만들지 않는다.

    고를 사람을 화면이 추리지 않는다 — 목록도 고치는 판정 하나로 뽑는다
    (`routers/dashboard.py` 의 `_grant_candidates`). 그래서 이미 전부 고치는
    관리자와, 맡겨도 안 통하는 투자컨설턴트가 저절로 빠진다.
    """
    people = stage["people"]
    owner = people["consultant_a"].id
    body = sign_in("admin").get(f"/team?grant={owner}").text
    offered = _candidates(body)
    assert {people["member"].id, people["other"].id} <= offered
    assert people["admin"].id not in offered, "이미 전부 고치는 관리자가 서 있다"
    assert people["consultant_b"].id not in offered, "맡겨도 안 통하는 사람이 서 있다"
    assert owner not in offered, "자기 자신이 서 있다"


def test_someone_whose_screen_is_off_is_not_offered(stage, sign_in, db):
    """투자현황이 막힌 팀원은 맡겨도 안 통한다 — 그러니 세우지 않는다."""
    people = stage["people"]
    people["other"].can_view_consulting = 0
    db.commit()
    offered = _candidates(
        sign_in("admin").get(f"/team?grant={people['consultant_a'].id}").text)
    assert people["member"].id in offered
    assert people["other"].id not in offered


def test_an_inert_grant_can_still_be_taken_away(stage, sign_in, db):
    """안 통하게 된 사람도 **고르는 칸에는 남는다** — 안 남기면 뺄 길이 없다."""
    people = stage["people"]
    owner = people["consultant_a"].id
    grant(db, owner, people["other"].id)
    people["other"].can_view_consulting = 0
    db.commit()
    offered = _candidates(sign_in("admin").get(f"/team?grant={owner}").text)
    assert people["other"].id in offered
    assert _post_grant(sign_in("admin"), owner, []).status_code == 303
    assert _grants(db) == set()


# ═══════════════════════════════════════════════════════════════════════════
# 8. 이 권한으로 고친 것은 수정 로그에 남는다
# ═══════════════════════════════════════════════════════════════════════════
#
# **권한을 넓히는 근거가 로그였다.** 남의 줄을 고칠 수 있는 사람이 늘어나는
# 만큼 "이거 누가 바꿨지" 가 늘어나므로, 안 남으면 이 기능의 가장 큰 구멍이다.

def _logs(db, table: str = ""):
    from app.models import EditLog

    db.expire_all()
    rows = db.query(EditLog).order_by(EditLog.id).all()
    return [r for r in rows if not table or r.table_name == table]


def test_an_edit_made_through_a_grant_is_written_down(stage, sign_in, db):
    """맡아서 고친 것은 정확히 `남의 것` 이다 — 누가 · 누구의 · 무엇을."""
    people, rows = stage["people"], stage["rows"]
    grant(db, people["consultant_a"].id, people["member"].id)
    r = sign_in("member").patch(f"/api/consulting/{rows['consultant_a'].id}",
                                json={"region": PROBE})
    assert r.status_code == 200

    logs = _logs(db, "consulting_companies")
    assert len(logs) == 1, "맡아서 고쳤는데 로그가 남지 않았습니다"
    log = logs[0]
    assert log.scope == "others"
    assert log.actor_user_id == people["member"].id
    assert log.target_user_id == people["consultant_a"].id
    assert log.row_id == rows["consultant_a"].id
    assert log.screen and log.path.endswith(str(rows["consultant_a"].id))


def test_editing_my_own_row_still_leaves_nothing(stage, sign_in, db):
    """맡았다고 해서 **자기 줄**까지 로그가 쌓이지는 않는다.

    남기면 하루에 수백 줄이 쌓여 아무도 안 본다 — 볼 수 있는 로그여야
    쓸모가 있다(`services/edit_log.py` 머리말).
    """
    grant(db, stage["people"]["consultant_a"].id, stage["people"]["member"].id)
    r = sign_in("member").patch(f"/api/consulting/{stage['rows']['member'].id}",
                                json={"region": PROBE})
    assert r.status_code == 200
    assert _logs(db, "consulting_companies") == []


def test_handing_out_the_grant_is_itself_written_down(stage, sign_in, db):
    """**권한을 넓힌 것 자체**가 남는다.

    로그에 `남의 줄이 고쳐졌다` 만 있고 그 사람이 언제부터 고칠 수 있었는지가
    없으면, 넓힌 뒤에 생긴 변경을 되짚을 수가 없다.
    """
    people = stage["people"]
    owner, editor = people["consultant_a"].id, people["member"].id
    assert _post_grant(sign_in("admin"), owner, [editor]).status_code == 303

    logs = _logs(db, "consulting_row_grants")
    assert len(logs) == 1, "맡긴 것이 로그에 안 남았습니다"
    assert logs[0].scope == "others"
    assert logs[0].actor_user_id == people["admin"].id
    assert logs[0].target_user_id == owner
    assert logs[0].action == "create"

    assert _post_grant(sign_in("admin"), owner, []).status_code == 303
    logs = _logs(db, "consulting_row_grants")
    assert len(logs) == 2, "뺀 것이 로그에 안 남았습니다"
    assert logs[1].action == "delete"
