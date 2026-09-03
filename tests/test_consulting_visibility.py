"""팀 현황이 투자컨설턴트에 대해 **사실대로** 그리는가.

두 가지가 어긋나 있었다.

1. `투자현황` 칸이 컨설턴트 줄에 `막힘` 이라고 떴는데 **실제로는 볼 수 있었다.**
   라우터는 역할까지 보고(`admin`·`consultant` 통과) 표는 `can_view_consulting`
   칸만 봤다 — 판정이 두 곳에 따로 적혀 있고 한쪽이 낡은 것이다. 이 저장소가
   반복해서 당한 사고다(메뉴 목록과 라우터 목록이 갈린 일, 투자사 수가 화면마다
   달랐던 일). 그래서 여기서는 **화면 표시와 실제 접근을 각각 확인하지 않고
   서로 대조한다** — 따로 보면 둘 다 '맞다'고 나오면서 서로 다를 수 있다.

   지금은 판정이 **칸 하나**다(`deps.may_view_consulting`) — 역할은 새 계정의
   기본값만 정한다. 그래서 이 대조가 여섯 갈래 전부에서 뜻을 갖는다.

2. 투자사·발송 칸이 `0` 과 `미연결` 로 떠서, 컨설턴트가 **아직 설정이 덜 된
   사람처럼** 읽혔다. 투자컨설턴트는 담당 투자사를 받지 않고 딜소개를 보내지
   않는다 — 원래 없는 것이다. 특히 `미연결` 은 이 앱에서 고쳐야 할 것을 뜻하는
   표시라(대시보드 경고도 같은 말을 쓴다) 고칠 것이 없는데 경고가 뜨면 진짜
   경고까지 무시하게 된다.
"""
from __future__ import annotations

import re

import pytest

from .conftest import DEMO_PASSWORD

# 역할 × `can_view_consulting` 켜짐/꺼짐 — 여섯 가지를 전부 돈다.
COMBOS = [(role, flag)
          for role in ("user", "consultant", "admin")
          for flag in (0, 1)]


@pytest.fixture()
def viewer(db, users):
    """표를 열어 볼 관리자. 검사 대상 계정은 이 사람이 아니다."""
    from app.models import User
    from app.services import auth as auth_svc

    # 계정을 만들 때의 기본값 그대로 — 관리자도 이제 이 칸으로 열린다.
    row = User(id=71, name="관리자시험", phone="01000000071", role="admin",
               can_view_consulting=1,
               password_hash=auth_svc.hash_password(DEMO_PASSWORD))
    db.add(row)
    db.commit()
    return row


@pytest.fixture()
def portal(db, users, viewer):
    from fastapi.testclient import TestClient

    from app.main import create_app

    app = create_app()

    def sign_in(phone: str):
        client = TestClient(app)
        r = client.post("/login", data={"phone": phone, "password": DEMO_PASSWORD},
                        follow_redirects=False)
        assert r.status_code == 303
        return client

    return {"app": app, "sign_in": sign_in, "admin": sign_in("01000000071")}


def _make(db, role: str, flag: int, phone: str, name: str = "검사대상"):
    from app.models import User
    from app.services import auth as auth_svc

    row = User(name=name, phone=phone, role=role, can_view_consulting=flag,
               password_hash=auth_svc.hash_password(DEMO_PASSWORD))
    db.add(row)
    db.commit()
    return row


def _row(html: str, name: str) -> str:
    """팀 현황 표에서 그 사람의 줄."""
    rows = [chunk for chunk in html.split("<tr") if f"<b>{name}</b>" in chunk]
    assert rows, f"{name} 줄이 표에 없다"
    return rows[0]


def _raw_cell(row: str, css_class: str) -> str:
    """칸 하나를 **태그째** — 확인 문구는 `onsubmit` 속성 안에 있다.

    줄 전체에서 찾으면 안 된다. 같은 줄의 [비밀번호 초기화]·[계정 정지]도
    `confirm(` 을 달고 있어서, 투자현황 칸에 아무것도 안 붙어 있는데 붙은
    것처럼 읽힌다.
    """
    found = re.search(rf'<td class="{css_class}".*?</td>', row, re.S)
    assert found, f"{css_class} 칸이 없다"
    return found.group(0)


def _cell(row: str, css_class: str) -> str:
    """줄에서 칸 하나의 글자만 (표시를 태그와 함께 견주면 모양만 바꿔도 깨진다)."""
    found = re.search(rf'<td class="{css_class}".*?</td>', row, re.S)
    assert found, f"{css_class} 칸이 없다"
    return " ".join(re.sub(r"<[^>]+>", " ", found.group(0)).split())


# --- 표시와 실제가 같은가 ------------------------------------------------------

@pytest.mark.parametrize("role,flag", COMBOS)
def test_the_screen_and_the_real_permission_agree(portal, db, role, flag):
    """`볼 수 있음` 이라고 적힌 사람은 실제로 열리고, `막힘` 인 사람은 막힌다.

    표시와 실제를 **대조**한다 — 이 버그가 정확히 그 둘이 갈려서 났다.
    """
    made = _make(db, role, flag, "01000000072")
    shown = _cell(_row(portal["admin"].get("/team").text, made.name), "consulting-cell")
    assert shown in ("볼 수 있음", "막힘"), shown

    opened = portal["sign_in"]("01000000072").get("/consulting", follow_redirects=False)
    assert (shown == "볼 수 있음") == (opened.status_code == 200), (
        f"{role}(flag={flag}): 표는 `{shown}` 인데 실제로는 "
        f"{opened.status_code} 다")


# --- 누구든 끄고 켠다 ---------------------------------------------------------
#
# 예전에는 **역할이 곧 권한**이라 관리자·투자컨설턴트는 개별로 막을 수 없었다
# (그 줄에는 단추 대신 상태만 떴다). 사용자가 원한 것은 그냥 "보여줬다 말았다"
# 하는 것이라, 이제 칸 하나로 누구든 끄고 켠다.

@pytest.mark.parametrize("role", ["user", "consultant", "admin"])
def test_every_role_can_be_switched_off_and_back_on(portal, db, role):
    """켠 뒤 열리고, 끈 뒤 막힌다 — **역할과 상관없이.**

    화면에 적힌 것과 실제 접근을 매번 함께 본다. 둘 중 하나만 보면 '껐다고
    적혀 있는데 계속 열려 있는' 그 어긋남을 못 잡는다.
    """
    made = _make(db, role, 1, "01000000074")
    door = portal["sign_in"]("01000000074")
    admin = portal["admin"]

    def shown():
        return _cell(_row(admin.get("/team").text, made.name), "consulting-cell")

    assert shown() == "볼 수 있음"
    assert door.get("/consulting").status_code == 200

    assert admin.post(f"/team/members/{made.id}/consulting",
                      follow_redirects=False).status_code == 303
    db.refresh(made)
    assert made.can_view_consulting == 0
    assert shown() == "막힘"
    assert door.get("/consulting").status_code == 403

    admin.post(f"/team/members/{made.id}/consulting", follow_redirects=False)
    db.refresh(made)
    assert made.can_view_consulting == 1
    assert shown() == "볼 수 있음"
    assert door.get("/consulting").status_code == 200


@pytest.mark.parametrize("role", ["user", "consultant", "admin"])
def test_the_toggle_is_offered_on_every_row_but_your_own(portal, db, role):
    """단추가 없는 줄은 **본인**뿐이다."""
    made = _make(db, role, 1, "01000000075")
    row = _row(portal["admin"].get("/team").text, made.name)
    assert f"/team/members/{made.id}/consulting" in row


def test_you_cannot_switch_off_your_own(portal, db, viewer):
    """스스로를 잠그면 이 화면에 다시 들어올 수 없다 — 권한 칸과 같은 이유다.

    화면에서 단추를 감추는 것만으로는 부족하다. 주소로 직접 부를 수 있어서,
    **라우터가 같이 막아야** 잠기지 않는다.
    """
    admin = portal["admin"]
    row = _row(admin.get("/team").text, viewer.name)
    assert f"/team/members/{viewer.id}/consulting" not in row, "본인 줄에 단추가 있다"
    assert "본인 ·" in _cell(row, "consulting-cell")

    r = admin.post(f"/team/members/{viewer.id}/consulting", follow_redirects=False)
    assert r.status_code == 303
    db.refresh(viewer)
    assert viewer.can_view_consulting == 1, "본인 것이 꺼졌다"
    assert admin.get("/consulting").status_code == 200


def test_switching_off_a_consultant_warns_first(portal, db):
    """투자컨설턴트를 끄면 **볼 화면이 하나도 안 남는다** — 누르기 전에 알린다.

    막는 것 자체는 막지 않는다. 모르고 끄는 것을 막는 자리다(비밀번호 초기화·
    계정 정지가 확인을 받는 것과 같다).
    """
    made = _make(db, "consultant", 1, "01000000076")
    cell = _raw_cell(_row(portal["admin"].get("/team").text, made.name),
                     "consulting-cell")
    assert "confirm(" in cell and "다른 화면이 없어" in cell

    # 팀원 줄에는 붙지 않는다 — 다른 화면이 얼마든지 남아 있다.
    plain = _make(db, "user", 1, "01000000077", name="팀원대상")
    assert "confirm(" not in _raw_cell(
        _row(portal["admin"].get("/team").text, plain.name), "consulting-cell")


def test_a_switched_off_consultant_gets_a_notice_not_an_empty_screen(portal, db):
    """끈 계정이 어디로 가는가 — 빈 화면도, 날것의 오류도 아니어야 한다."""
    made = _make(db, "consultant", 1, "01000000078")
    portal["admin"].post(f"/team/members/{made.id}/consulting", follow_redirects=False)
    db.refresh(made)

    door = portal["sign_in"]("01000000078")
    # 첫 화면(`deps.home_for`)이 곧 막힌 그 화면이다 — 되돌려 보내면 맴돈다.
    landing = door.get("/", follow_redirects=False)
    assert landing.status_code == 303 and landing.headers["location"] == "/consulting"

    blocked = door.get("/consulting")
    assert blocked.status_code == 403
    assert "guard-modal" in blocked.text
    assert "다른 화면이 없어" in blocked.text
    # 메뉴가 남아 있으면 눌러야 막힌 것을 안다 — 화면이 거짓말을 한다.
    assert 'href="/consulting"' not in blocked.text


# --- 없는 것을 0 으로 그리지 않는다 -------------------------------------------

def test_the_deal_columns_are_blank_for_a_consultant(portal, db):
    """`0` 과 `미연결` 로 그리면 설정이 덜 된 사람처럼 읽힌다."""
    made = _make(db, "consultant", 0, "01000000077")
    row = _row(portal["admin"].get("/team").text, made.name)
    assert "미연결" not in row
    assert "미발급" not in row
    # 숫자를 지어내지 않는다 — 비울 뿐이다.
    assert row.count("—") == 6           # 담당 투자사 · 발송 준비 · 발송 · IR · 미팅 · 발송 프로그램


def test_a_team_member_still_sees_their_numbers(portal, db, users):
    """비우는 것은 컨설턴트뿐이다 — 팀원의 0 은 고쳐야 할 것이라 그대로 보인다."""
    row = _row(portal["admin"].get("/team").text, users["u1"].name)
    assert "미연결" in row
    assert "—" not in row


def test_a_consultant_is_not_in_the_agent_warning(db, users, viewer):
    """고칠 것이 없는데 경고가 뜨면 진짜 경고를 무시하게 된다."""
    from app.services.dashboard import admin_dashboard

    made = _make(db, "consultant", 0, "01000000078")
    warnings = {w["label"]: w["detail"] for w in admin_dashboard(db)["warnings"]}

    assert "발송 프로그램 미연결" in warnings          # 팀원은 그대로 잡힌다
    assert users["u1"].name in warnings["발송 프로그램 미연결"]
    assert made.name not in warnings["발송 프로그램 미연결"]
    assert made.name not in warnings.get("담당 투자사가 없는 계정", "")
