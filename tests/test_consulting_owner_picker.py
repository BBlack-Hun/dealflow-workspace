"""투자컨설턴트 현황 — **탭이 아니라 사람을 고르는 자리.**

이 화면은 원래 투자컨설턴트 한 사람의 **개인 표**다(줄마다 담당이 붙어 있다).
그 개인 표들을 모아 팀이 보는 자리이기도 해서, 무엇을 보고 있는지는 탭이 아니라
**사람**으로 갈린다. 탭 셋(스타트업 → 경영본부 전달 → 계약)은 팀이 함께 쓰는
업무 단계라 사람마다 나눌 것이 아니다(`models.ConsultingSheet`).

여기서 지키는 것 넷:

1. 이름은 **줄에 붙어 있는 담당**에서 나온다. 계정 목록으로 세우면 아직 기업을
   안 받은 사람이 `0` 으로 서서, 고를 것이 없는 이름만 늘어난다.
2. **숫자는 눌렀을 때 나올 수와 같다.** 탭을 가리지 않고 세면 탭에는 32 라고
   적혀 있는데 이름 옆에는 55 가 붙는다.
3. **KPI 도 칩도 표도 고른 사람 것이다.** 위 숫자만 전체로 남아 있으면 어느
   쪽이 맞는지 화면 어디에도 안 나온다.
4. **빈 표는 왜 비었는지 말한다.** 그냥 빈 표는 고장으로 읽힌다 — 특히
   컨설턴트에게는 이 화면이 전부라(`deps.CONSULTANT_PATHS`) 계정이 잘못된 줄 안다.

이름은 전부 가상값이다. 이 저장소는 공개라 실명이 들어가면 안 된다.
"""
from __future__ import annotations

import re

import pytest

from .conftest import DEMO_PASSWORD

STARTUP = "스타트업"
HANDOVER = "경영본부 전달 기업"


@pytest.fixture()
def stage(db, users):
    """두 컨설턴트와, 시트를 통째로 들고 있는 팀원 하나.

    지금 운영이 그 모양이다 — 55줄이 전부 팀원 한 사람 앞으로 되어 있고
    컨설턴트 계정에는 줄이 0개다. 나누는 것은 사용자가 나중에 정한다.
    """
    from app.models import ConsultingCompany, User
    from app.services import auth as auth_svc

    pw = auth_svc.hash_password(DEMO_PASSWORD)
    member = users["u1"]                 # 팀원 — 관리자가 이 화면을 켜 줬다
    member.can_view_consulting = 1
    first = User(name="컨설갑", phone="01000000101", role="consultant",
                 password_hash=pw)
    second = User(name="컨설을", phone="01000000102", role="consultant",
                  password_hash=pw)
    # 계정만 있고 줄이 하나도 없는 컨설턴트 — 고르는 자리에 서면 안 된다.
    idle = User(name="컨설병", phone="01000000103", role="consultant",
                password_hash=pw)
    admin = User(name="관리갑", phone="01000000104", role="admin",
                 password_hash=pw)
    db.add_all([first, second, idle, admin])
    db.commit()

    rows = []
    for who, sheet, name in [
        (member, STARTUP, "샘플가"), (member, STARTUP, "샘플나"),
        (member, HANDOVER, "샘플다"),
        (first, STARTUP, "샘플라"),
        (second, HANDOVER, "샘플마"),
    ]:
        row = ConsultingCompany(user_id=who.id, sheet=sheet, company_name=name,
                                management="관리 중", position=1)
        db.add(row)
        rows.append(row)
    orphan = ConsultingCompany(user_id=None, sheet=STARTUP,
                               company_name="샘플바", management="드랍", position=9)
    db.add(orphan)
    db.commit()
    return {"member": member, "first": first, "second": second,
            "idle": idle, "admin": admin, "orphan": orphan}


@pytest.fixture()
def sign_in(db, users):
    from fastapi.testclient import TestClient

    from app.main import create_app

    app = create_app()
    phones = {"member": "01000000001", "first": "01000000101",
              "second": "01000000102", "idle": "01000000103",
              "admin": "01000000104"}

    def _open(who: str):
        client = TestClient(app)
        r = client.post("/login", data={"phone": phones[who],
                                        "password": DEMO_PASSWORD},
                        follow_redirects=False)
        assert r.status_code == 303
        return client

    return _open


def _picker(html: str) -> list:
    """고르는 자리에 선 이름들 — `(이름, 숫자)`. 없으면 빈 목록."""
    block = re.search(r'<div class="filter-line owner-line">(.*?)</div>', html, re.S)
    if not block:
        return []
    out = []
    for chip in re.findall(r"<a[^>]*>(.*?)</a>", block.group(1), re.S):
        text = " ".join(re.sub(r"<[^>]+>", " ", chip).split())
        m = re.match(r"(.*?)\s*(\d+)$", text)
        out.append((m.group(1).strip(), int(m.group(2))) if m else (text, None))
    return out


def _kpi(html: str, key: str) -> int:
    m = re.search(rf'data-kpi="{key}"[^>]*>(\d+)<', html)
    assert m, f"{key} KPI 를 찾지 못했습니다"
    return int(m.group(1))


def _rows(html: str) -> list:
    body = html.split("<tbody>", 1)[1]
    return re.findall(r'data-field="company_name"[^>]*>([^<]*)<', body)


# --- 1. 이름은 줄에서 나온다 ---------------------------------------------------

def test_the_picker_lists_only_people_who_actually_hold_rows(stage, sign_in):
    """계정 목록으로 세우면 **줄이 없는 이름**이 고르는 자리에 선다.

    `컨설병` 은 계정만 있고 담당 기업이 하나도 없다 — 눌러도 빈 표가 나온다.
    """
    names = [name for name, _n in _picker(sign_in("member").get("/consulting").text)]
    assert "컨설병" not in names, names
    for who in ("강민준", "컨설갑", "컨설을"):
        assert who in " ".join(names), names


def test_a_row_with_no_owner_gets_its_own_name(stage, sign_in):
    """주인 없는 줄은 `아직 배정 안 됨` 이라는 **다른 뜻**이다 — 사람과 안 섞는다."""
    names = [name for name, _n in _picker(sign_in("member").get("/consulting").text)]
    assert "담당 미배정" in names, names


def test_an_owner_who_is_not_a_consultant_is_marked_as_such(stage, sign_in):
    """이 화면은 컨설턴트별 표다 — 이름만 있으면 세 번째 컨설턴트로 읽힌다.

    지금 운영의 모든 줄이 팀원 한 사람 앞으로 되어 있다. 그 이름을 `미배정`
    으로 묶으면 화면이 거짓말을 한다(그 줄에는 실제로 주인이 있고 그 사람만
    고칠 수 있다). 이름은 그대로 두고 **역할을 옆에 적는다.**
    """
    picker = _picker(sign_in("member").get("/consulting").text)
    flat = {name for name, _n in picker}
    assert "강민준 팀원" in flat, picker
    # 컨설턴트에게는 안 붙는다 — 같은 말을 두 번 하는 것뿐이다.
    assert "컨설갑" in flat, picker


def test_the_picker_is_not_shown_to_someone_who_only_sees_their_own(stage, sign_in):
    """고를 것이 하나뿐인 자리를 세우면 눌러도 아무 일이 없는 단추가 된다."""
    assert _picker(sign_in("first").get("/consulting").text) == []


# --- 2. 숫자는 눌렀을 때 나올 수와 같다 -----------------------------------------

def test_the_number_next_to_a_name_is_what_you_get_when_you_click_it(stage, sign_in):
    """탭을 가리지 않고 세면 탭에는 2, 이름 옆에는 3 이 붙는다."""
    client = sign_in("member")
    body = client.get("/consulting").text            # 첫 탭(스타트업)
    counts = dict(_picker(body))
    assert counts["강민준 팀원"] == 2, counts
    assert counts["컨설갑"] == 1, counts
    assert counts["컨설을"] == 0, counts            # 이 탭에는 줄이 없다

    # 실제로 눌러 본다 — 적힌 수와 나오는 줄 수가 같아야 한다.
    for name, uid in [("강민준 팀원", stage["member"].id),
                      ("컨설갑", stage["first"].id),
                      ("컨설을", stage["second"].id)]:
        picked = client.get(f"/consulting?sheet={STARTUP}&owner={uid}").text
        assert len(_rows(picked)) == counts[name], name


def test_someone_with_no_rows_in_this_tab_stays_on_the_list(stage, sign_in):
    """이 탭에 줄이 없다고 이름을 빼면 그 사람 표로 건너갈 길이 사라진다."""
    body = sign_in("member").get(f"/consulting?sheet={STARTUP}").text
    assert "컨설을" in [name for name, _n in _picker(body)]


def test_the_order_does_not_change_between_tabs(stage, sign_in):
    """탭을 옮겼는데 이름 순서가 바뀌면 같은 자리를 눌렀다가 다른 사람이 열린다."""
    client = sign_in("member")
    first = [name for name, _n in _picker(client.get(f"/consulting?sheet={STARTUP}").text)]
    second = [name for name, _n in _picker(client.get(f"/consulting?sheet={HANDOVER}").text)]
    assert first == second, (first, second)


# --- 3. 고른 사람을 KPI·칩·표가 따라간다 ----------------------------------------

def test_the_numbers_follow_the_person_you_picked(stage, sign_in):
    """위 숫자만 전체로 남아 있으면 어느 쪽이 맞는지 화면에 안 나온다."""
    client = sign_in("member")
    everyone = client.get(f"/consulting?sheet={STARTUP}").text
    # 스타트업 탭: 팀원 2 + 컨설갑 1 + 주인 없는 줄 1 = 4
    assert _kpi(everyone, "total") == 4
    assert _kpi(everyone, "managed") == 3
    assert _kpi(everyone, "dropped") == 1

    only_first = client.get(
        f"/consulting?sheet={STARTUP}&owner={stage['first'].id}").text
    assert _kpi(only_first, "total") == 1
    assert _kpi(only_first, "managed") == 1
    assert _kpi(only_first, "dropped") == 0
    assert _rows(only_first) == ["샘플라"]


def test_the_tab_counts_follow_the_person_too(stage, sign_in):
    """탭 건수만 전체로 남으면, 탭에는 4 인데 표에는 1줄이 뜬다."""
    body = sign_in("member").get(
        f"/consulting?sheet={STARTUP}&owner={stage['first'].id}").text
    tabs = dict(re.findall(r'sheet-tab[^>]*>([^<]*?)\s*<span>(\d+)</span>', body))
    assert tabs[STARTUP] == "1", tabs
    assert tabs[HANDOVER] == "0", tabs


def test_the_unassigned_chip_actually_narrows_to_unassigned_rows(stage, sign_in):
    """`담당 미배정` 을 눌렀는데 전체가 나오면 그 칩은 거짓말이다.

    `owner=0` 은 **안 고른 상태**라, 미배정을 0 으로 두면 눌러도 전체가 나오고
    `전체` 칩까지 같이 눌린 것처럼 보인다.
    """
    from app.routers.consulting import UNASSIGNED

    body = sign_in("member").get(
        f"/consulting?sheet={STARTUP}&owner={UNASSIGNED}").text
    assert _rows(body) == ["샘플바"]
    assert _kpi(body, "total") == 1


def test_a_person_who_is_not_on_the_list_falls_back_to_everyone(stage, sign_in):
    """없는 번호가 실려 오면 표는 비고 아무 칩도 안 눌린 채로 남는다."""
    body = sign_in("member").get(f"/consulting?sheet={STARTUP}&owner=99999").text
    assert _kpi(body, "total") == 4
    assert "내용이 없습니다" not in body


def test_a_consultant_cannot_look_at_someone_else_by_url(stage, sign_in):
    """고르는 자리가 안 뜬다고 주소까지 막힌 것은 아니다."""
    body = sign_in("first").get(
        f"/consulting?sheet={STARTUP}&owner={stage['member'].id}").text
    assert _rows(body) == ["샘플라"]          # 무엇을 넣든 자기 줄만이다


# --- 4. 담당 칸 ---------------------------------------------------------------

def test_each_row_says_whose_it_is(stage, sign_in):
    """줄만 보고 누구 것인지 알 수 없으면 고른 사람을 바꿀 때마다 위를 다시 본다."""
    body = sign_in("member").get(f"/consulting?sheet={STARTUP}").text
    owners = re.findall(r'<td class="owner-cell muted"[^>]*>([^<]*)</td>', body)
    assert owners == ["강민준", "강민준", "컨설갑", "미배정"], owners
    # 왜 안 눌리는지도 그 칸에 적혀 있다 — 내 줄에는 안 붙는다.
    marks = re.findall(r'<td class="owner-cell muted"([^>]*)>', body)
    assert [bool("볼 수만 있습니다" in m) for m in marks] == [False, False, True, True], marks


def test_the_owner_column_is_not_shown_to_someone_who_only_sees_their_own(stage, sign_in):
    """같은 이름이 줄마다 반복되는 칸은 자리만 먹는다."""
    body = sign_in("first").get("/consulting").text
    assert "owner-cell" not in body


# --- 5. 빈 표는 왜 비었는지 말한다 ----------------------------------------------

def test_a_consultant_with_nothing_assigned_is_told_why(stage, sign_in):
    """그냥 빈 표는 고장으로 읽힌다 — 이 계정에는 이 화면이 전부다."""
    body = sign_in("idle").get("/consulting").text
    assert "아직 배정된 기업이 없습니다" in body
    assert "관리자가 담당 기업을 배정하면 여기에 표시됩니다" in body
    # 스스로 넣을 길도 함께 알려 준다 — 기다리는 것 말고 할 일이 있다.
    assert "[기업 추가]" in body


def test_picking_a_person_with_nothing_in_this_tab_says_so(stage, sign_in):
    """탭을 바꾸거나 다른 사람을 고를 일이지, 시트를 올릴 일이 아니다."""
    body = sign_in("member").get(
        f"/consulting?sheet={STARTUP}&owner={stage['second'].id}").text
    assert "컨설을" in body
    assert "이 탭에서 맡은 기업이 없습니다" in body
    assert "아직 배정된 기업이 없습니다" not in body


def test_the_read_only_rule_is_written_where_the_rows_are(stage, sign_in):
    """눌러도 아무 일이 없는 칸이 있으면 왜 안 되는지 적혀 있어야 한다."""
    body = sign_in("member").get(f"/consulting?sheet={STARTUP}").text
    assert "다른 담당자의 줄은 볼 수만 있습니다" in body
    # 남의 줄이 하나도 없으면 그 안내도 없다 — 안 걸리는 규칙을 적어 두면 잡음이다.
    mine_only = sign_in("member").get(
        f"/consulting?sheet={STARTUP}&owner={stage['member'].id}").text
    assert "다른 담당자의 줄은 볼 수만 있습니다" not in mine_only
