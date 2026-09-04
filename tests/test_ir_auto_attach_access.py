"""자료 자동 첨부는 **관리자가 켜 준 계정만** 쓴다 (0059).

## 무엇이 바뀌었나

예전에는 이 기능을 켜는 문이 하나였다 — `/setup` 에서 자료 폴더 경로를 넣으면
켜졌다. 그 칸은 **본인이 넣는 값**이라(`agent_devices.ir_root`) 문이 곧
스위치였고, **누구든 스스로 켤 수 있었다.** 정해진 사람만 쓰게 하려는데 그
사람을 가릴 자리가 코드에 없었다.

이제 판정은 칸 하나다(`users.can_auto_attach_ir` → `deps.may_auto_attach`).
`can_view_consulting`(#107) 과 같은 자리, 같은 모양이다 — 이름을 코드에 박지
않고 관리자가 팀 현황에서 계정마다 켜고 끈다.

## 무엇을 지키나

1. 꺼진 계정은 **화면에도 라우터에도** 못 닿는다 — 칸을 감추기만 하면 주소로
   그대로 부를 수 있다(이 저장소가 여러 번 겪은 사고다)
2. 켠 계정은 **지금까지 그대로** 된다
3. 껐다 켜면 **넣어 둔 폴더가 살아 있다** — 끄는 것은 안 읽는 것이지 지우는
   것이 아니다
4. 안내 문구가 두 계정에 **다르게** 나간다 — 못 쓰는 사람을 없는 자리로
   보내지 않는다
5. **본인 것도 끄고 켠다** — 투자현황과 다른 판단이다(아래 이유)

이주가 무엇을 켜는지는 `test_ir_auto_attach_migration.py` 가 본다.
"""
from __future__ import annotations

import pytest

from .conftest import DEMO_PASSWORD, DEMO_TOKEN, auth

# 실제 경로를 적지 않는다 — 이 저장소는 공개다.
MY_FOLDER = "/Users/tester/Share/자료폴더"

#: 자료 폴더를 정하러 가라는 안내. **쓸 수 있는 계정에만** 보인다 —
#: 꺼진 계정에는 `/setup` 에 그 자리가 아예 없어서 가 봐야 헛걸음이다.
GO_SET_THE_FOLDER = "이 PC 의 자료 폴더를 정하세요"
#: `/setup` 의 자료 폴더 칸.
THE_FOLDER_FIELD = 'name="ir_root"'


def _device(db, user_id):
    from app.models import AgentDevice

    return db.query(AgentDevice).filter_by(user_id=user_id).first()


def _allow(db, user, on=True):
    user.can_auto_attach_ir = 1 if on else 0
    db.commit()


@pytest.fixture()
def admin(db, users):
    """켜고 끄는 사람. 팀 현황은 관리자만 연다."""
    from app.services import auth as auth_svc

    from app.models import User

    boss = User(name="관리자", phone="01000000009", role="admin",
                password_hash=auth_svc.hash_password(DEMO_PASSWORD))
    db.add(boss)
    db.commit()
    return boss


@pytest.fixture()
def as_admin(db, admin):
    """관리자 세션 — **`logged_in` 과 다른 클라이언트다.**

    conftest 의 `client` 는 테스트 하나에 한 개라, 거기에 대고 다시 로그인하면
    먼저 들어와 있던 세션이 덮인다. 이 파일은 `관리자가 켠다 → 그 사람 화면이
    달라진다` 를 **한 테스트 안에서 함께** 봐야 해서(표시와 실제가 갈리는 것을
    잡으려면 따로 보면 안 된다) 창을 하나 더 연다.
    """
    from fastapi.testclient import TestClient

    from app.main import create_app

    with TestClient(create_app()) as c:
        c.post("/login", data={"phone": "01000000009", "password": DEMO_PASSWORD})
        yield c


# ── ① 꺼진 계정은 화면에도 라우터에도 못 닿는다 ─────────────────────────────

def test_a_new_account_starts_switched_off(db, users):
    """기본값은 **꺼짐**이다. 쓸 사람은 관리자가 정한다."""
    from app import deps

    assert not deps.may_auto_attach(users["u1"])
    assert deps.auto_attach_default_for("user") is False
    assert deps.auto_attach_default_for("admin") is False
    assert deps.auto_attach_default_for("consultant") is False


def test_the_folder_field_is_not_drawn_for_a_switched_off_account(logged_in):
    """★ 칸이 보이는 것 자체가 곧 기능이 열려 있다는 뜻이다.

    이 칸을 채우는 것이 자동 첨부를 켜는 일이라(`services/ir_attach.py`),
    그려 두고 눌러야 막힌 것을 알게 하면 안 된다 — 사이드바가 못 보는 메뉴를
    아예 지우는 것과 같은 자리다(`ui.can_see`).
    """
    assert THE_FOLDER_FIELD not in logged_in.get("/setup").text


def test_the_folder_field_is_drawn_once_it_is_switched_on(logged_in, db, users):
    _allow(db, users["u1"])
    assert THE_FOLDER_FIELD in logged_in.get("/setup").text


def test_the_url_does_not_work_either(logged_in, db, users):
    """★ 화면에서만 감추면 **주소로 그대로 부를 수 있다.**

    화면 목록과 라우터 목록이 갈려 막은 줄 알았던 것이 열려 있던 사고를 이
    저장소는 여러 번 겪었다. 둘이 같은 함수를 읽는지 여기서 본다.
    """
    r = logged_in.post("/setup/ir-root", data={"ir_root": MY_FOLDER},
                       follow_redirects=False)
    assert r.status_code == 403
    assert _device(db, users["u1"].id).ir_root is None, "막았는데 값이 들어갔다"


def test_the_saved_folder_is_not_read_when_it_is_off(db, users):
    """★ 켜져 있던 계정을 끄면 **남아 있는 폴더로 되살아나면 안 된다.**

    끄면서 값을 지우지 않기 때문에(다시 켰을 때 되돌아와야 한다) 그 값을 읽는
    자리가 하나라도 남아 있으면 끈 것이 아니다. 판정은 한 곳이다
    (`services/ir_attach.py: auto_attach_enabled`).
    """
    from app.services import ir_attach

    _device(db, users["u1"].id).ir_root = MY_FOLDER
    _allow(db, users["u1"])
    assert ir_attach.auto_attach_enabled(db, users["u1"])

    _allow(db, users["u1"], on=False)
    assert not ir_attach.auto_attach_enabled(db, users["u1"])


def test_being_switched_on_alone_is_not_enough(db, users):
    """켜 주기만 하고 폴더가 없으면 **아직 켜진 것이 아니다.**

    폴더를 모르면 발송기는 파일을 한 개도 못 찾는다. 그 상태를 켜진 것으로 치면
    **자료 없이 문구만 나간다** — 제일 나쁜 실패다.
    """
    from app.services import ir_attach

    _allow(db, users["u1"])
    assert not ir_attach.auto_attach_enabled(db, users["u1"])


def test_the_agent_is_not_handed_a_folder_it_must_not_use(client, db, users):
    """★ 발송기에도 안 내려간다.

    파일이 나가지는 않지만, 발송기는 이 값으로 켜질 때 `IR 자료 폴더: … —
    보낼 자료를 이 폴더에 넣으세요` 라고 적는다(`agent/main.py: preflight`).
    그대로 두면 그 창이 쓰지도 않을 폴더를 챙기라고 말한다.
    """
    _device(db, users["u1"].id).ir_root = MY_FOLDER
    db.commit()

    off = client.post("/api/agent/heartbeat", json={}, headers=auth(DEMO_TOKEN))
    assert off.json()["ir_root"] == ""

    _allow(db, users["u1"])
    on = client.post("/api/agent/heartbeat", json={}, headers=auth(DEMO_TOKEN))
    assert on.json()["ir_root"] == MY_FOLDER


# ── ② 껐다 켜면 폴더가 살아 있다 ────────────────────────────────────────────

def test_switching_off_keeps_the_folder(as_admin, db, users):
    """★ 끄는 것은 **안 읽는 것**이지 지우는 것이 아니다.

    그 경로는 그 PC 앞에 앉은 본인만 아는 값이라, 지우면 되살릴 사람이 없다.
    """
    _device(db, users["u1"].id).ir_root = MY_FOLDER
    _allow(db, users["u1"])

    as_admin.post(f"/team/members/{users['u1'].id}/auto-attach")
    db.expire_all()
    assert users["u1"].can_auto_attach_ir == 0
    assert _device(db, users["u1"].id).ir_root == MY_FOLDER, "폴더가 지워졌다"


def test_switching_it_back_on_brings_the_folder_back(as_admin, logged_in, db, users):
    """껐다 켜면 화면에 그 값이 그대로 있어야 한다 — 다시 칠 필요가 없다."""
    _device(db, users["u1"].id).ir_root = MY_FOLDER
    _allow(db, users["u1"])

    as_admin.post(f"/team/members/{users['u1'].id}/auto-attach")   # 끄고
    assert MY_FOLDER not in logged_in.get("/setup").text, "끈 사이에 보이면 안 된다"

    as_admin.post(f"/team/members/{users['u1'].id}/auto-attach")   # 다시 켠다
    assert MY_FOLDER in logged_in.get("/setup").text


def test_a_switched_off_account_is_not_shown_its_own_path(logged_in, db, users):
    """꺼진 계정 화면에는 경로 자체를 내보내지 않는다.

    그릴 자리가 없는 값을 컨텍스트에 태우면 언젠가 그 값을 쓰는 자리가 생긴다.
    """
    _device(db, users["u1"].id).ir_root = MY_FOLDER
    db.commit()
    assert MY_FOLDER not in logged_in.get("/setup").text


def test_the_person_who_had_a_folder_is_told_where_it_went(logged_in, db, users):
    """★ "왜 칸이 없지" 를 헤맬 사람은 **넣어 뒀던 사람**뿐이다.

    한 번도 켠 적 없는 계정에는 원래 없던 자리라 그리울 것이 없다. 넣어 뒀다가
    꺼진 사람만 자기가 친 경로가 사라진 것을 보고 값을 잃은 줄 안다 — 그 줄에만
    답한다(막힌 투자현황이 `관리자가 … 다시 켜 줄 수 있습니다` 라고 적는 것과
    같은 말이다).
    """
    never_had_one = logged_in.get("/setup").text
    assert "지워지지 않았습니다" not in never_had_one

    _device(db, users["u1"].id).ir_root = MY_FOLDER
    db.commit()
    had_one = logged_in.get("/setup").text
    assert "지워지지 않았습니다" in had_one
    assert "팀 현황" in had_one, "누가 되돌릴 수 있는지 적어야 한다"


# ── ③ 안내 문구가 갈린다 ───────────────────────────────────────────────────

def test_a_switched_off_account_is_not_sent_to_a_place_that_is_not_there(
        logged_in, db, users):
    """★ IR 진행 관리가 못 쓰는 사람을 `/setup` 으로 보내면 안 된다.

    예전에는 이 한 줄이 누구에게나 보였다. 그때는 가서 폴더를 넣으면 정말
    켜졌으니 맞는 말이었는데, 이제 그 자리는 켜 준 계정에만 있다.
    """
    assert GO_SET_THE_FOLDER not in logged_in.get("/ir").text

    _allow(db, users["u1"])
    assert GO_SET_THE_FOLDER in logged_in.get("/ir").text, \
        "켜 줬는데 폴더를 어디서 정하는지 알려주지 않는다"


def test_the_company_screen_says_the_same_thing(logged_in, db, users):
    """IR 기업 현황도 같은 값을 읽는다 — 두 화면이 갈리면 하나는 낡는다."""
    off = logged_in.get("/companies").text
    assert "화면에서 각자 정합니다" not in off
    # 파일 이름을 적는 법은 **누구에게나** 필요하다(손으로 붙이는 사람도 그
    # 이름으로 파일을 찾는다). 문단째 지우면 그것까지 사라진다.
    assert "파일 이름</b>을 적습니다" in off

    _allow(db, users["u1"])
    assert "화면에서 각자 정합니다" in logged_in.get("/companies").text


# ── ④ 관리자가 켜고 끈다 ───────────────────────────────────────────────────

def test_the_toggle_is_on_the_team_screen(as_admin, db, users):
    r = as_admin.get("/team")
    assert f"/team/members/{users['u1'].id}/auto-attach" in r.text
    assert "자료 자동첨부" in r.text


def test_the_table_reads_the_same_judgment_as_the_screen(as_admin, logged_in,
                                                         db, users):
    """★ 표에 켜졌다고 떠 있는데 그 사람 화면에는 칸이 없으면 안 된다.

    팀 현황의 `투자현황` 칸이 실제로 그렇게 갈린 적이 있다 — `막힘` 이라고
    떠 있는데 열려 있었다. 표시와 실제를 **매번 함께** 본다.
    """
    for expected in (True, False, True):
        _allow(db, users["u1"], on=expected)
        row = _row_of(as_admin.get("/team").text, users["u1"].id)
        assert ("켜짐" in row) is expected, "표가 실제와 다른 말을 한다"
        assert (THE_FOLDER_FIELD in logged_in.get("/setup").text) is expected


def test_only_an_admin_can_switch_it(logged_in, db, users):
    """팀원이 주소로 자기 것을 켜면, 이 칸을 둔 뜻이 없어진다."""
    r = logged_in.post(f"/team/members/{users['u1'].id}/auto-attach",
                       follow_redirects=False)
    assert r.status_code in (302, 303, 403)
    db.expire_all()
    assert users["u1"].can_auto_attach_ir == 0


def test_an_admin_can_switch_their_own(as_admin, db, admin):
    """★ 본인 것도 끄고 켠다 — **투자현황과 다른 판단**이다.

    투자현황은 본인 줄을 막았다. 관리자가 스스로를 잠그면 그 화면에 다시 들어갈
    길이 없어지기 때문이다. 여기는 꺼져도 잠기는 화면이 없고(팀 현황은 그대로
    열려 있다), 오히려 막으면 **이 기능을 쓸 사람이 관리자 본인일 때 자기 것을
    켤 수가 없다** — 기본값이 꺼짐이라 새로 깐 서버에서는 켜 줄 사람이 아예
    없어진다.
    """
    as_admin.post(f"/team/members/{admin.id}/auto-attach")
    db.expire_all()
    assert admin.can_auto_attach_ir == 1, "관리자가 자기 것을 못 켠다"

    as_admin.post(f"/team/members/{admin.id}/auto-attach")
    db.expire_all()
    assert admin.can_auto_attach_ir == 0
    assert as_admin.get("/team").status_code == 200, "끈 순간 갈 화면이 없어졌다"


def test_switching_it_on_says_what_is_left_to_do(as_admin, db, users):
    """켜 주기만 해서는 아무 일도 안 일어난다 — 본인이 폴더를 정해야 켜진다.

    이 한 줄이 없으면 관리자는 켜 줬다고 알리고, 정작 그 사람은 무엇을 더 해야
    하는지 모른 채 예전처럼 손으로 붙인다.
    """
    r = as_admin.post(f"/team/members/{users['u1'].id}/auto-attach",
                      follow_redirects=True)
    assert "자료 폴더를 정해야" in r.text


def test_switching_a_missing_account_is_not_a_crash(as_admin):
    assert as_admin.post("/team/members/99999/auto-attach").status_code == 404


def _row_of(html: str, member_id: int) -> str:
    """팀 현황 표에서 그 사람 줄만. 옆 사람의 상태를 읽고 통과하지 않게."""
    import re

    rows = re.findall(r"<tr>(.*?)</tr>", html, re.S)
    for row in rows:
        if f"/team/members/{member_id}/auto-attach" in row:
            return row
    raise AssertionError(f"{member_id} 줄이 표에 없다")
