"""투자컨설턴트 현황 — **보는 범위와 고치는 범위가 같은가.**

보는 쪽은 `scope()` 로 좁혀 있었다. 관리자만 전체를 보고 그 외에는 자기 것만이다
(컨설턴트가 여럿이면 남의 담당 기업이 보이고, 각자 올린 시트가 서로를 덮는다).
그런데 **고치는 쪽에는 검사가 아예 없었다.** `can_view_consulting` 이 켜진 팀원이
주소의 번호만 바꾸면 화면에 안 뜨는 남의 줄을 고치거나 지울 수 있었다.

이 방향이 더 위험하다. '보이는데 못 고치는' 것은 누른 사람이 그 자리에서 알지만,
'안 보이는데 고쳐지는' 것은 고친 사람도 당한 사람도 모른다.

그래서 여기서는 **화면과 조작을 따로 확인하지 않고 서로 대조한다** — 따로 보면
둘 다 '맞다'고 나오면서 서로 다를 수 있다(팀 현황의 `투자현황` 칸이 그랬다).
줄을 손으로 나열하지 않고 훑어서 견주는 이유도 같다. 나열해 두면 줄이 하나
늘 때 그 줄만 조용히 검사 밖으로 빠진다.

**상태 코드만 보지 않는다.** 404 를 주면서 값은 바꿔 두는 것이 가장 나쁜 실패라,
막혔다는 검사는 전부 **값을 되읽어** 확인한다.
"""
from __future__ import annotations

import json
import re

import pytest

from .conftest import DEMO_PASSWORD

# 훑기가 남기는 표시. 뜻이 있는 값이면 진짜 자료와 섞여 헷갈린다.
PROBE = "훑기표시"


# --- 무대 -------------------------------------------------------------------

@pytest.fixture()
def stage(db, users):
    """네 역할과 각자의 줄·열.

    `남` 도 이 화면을 볼 수 있는 사람으로 둔다 — 볼 권한이 없는 사람의 줄만
    가지고 검사하면 `require_access` 가 먼저 끊어 주는 바람에 소유 검사가
    없어도 통과한다(그래서 이 구멍이 오래 살아 있었다).
    """
    from app.models import ConsultingColumn, ConsultingCompany, User
    from app.services import auth as auth_svc

    pw = auth_svc.hash_password(DEMO_PASSWORD)
    member, other = users["u1"], users["u2"]
    member.can_view_consulting = 1
    other.can_view_consulting = 1
    consultant = User(name="컨설턴트시험", phone="01000000081", role="consultant",
                      password_hash=pw)
    admin = User(name="관리자시험", phone="01000000082", role="admin",
                 password_hash=pw)
    db.add_all([consultant, admin])
    db.commit()

    people = {"member": member, "other": other,
              "consultant": consultant, "admin": admin}

    rows, cols = {}, {}
    for key, who in people.items():
        rows[key] = ConsultingCompany(user_id=who.id, company_name=f"샘플기업-{key}",
                                      region=f"지역-{key}", position=1)
        cols[key] = ConsultingColumn(user_id=who.id, label=f"8월 리마인드-{key}",
                                     position=0)
        db.add_all([rows[key], cols[key]])
    # 주인이 없는 줄 — 관리자에게만 보인다(배정해야 할 것이 남았다는 뜻이다).
    rows["unassigned"] = ConsultingCompany(user_id=None, company_name="샘플기업-미배정",
                                           region="지역-미배정", position=1)
    db.add(rows["unassigned"])
    db.commit()
    # 열 id 를 키로 쓰는 기록도 심어 둔다 — 열을 지울 때 남의 기록까지
    # 지워지는지 보려면 값이 있어야 한다.
    for key, who in people.items():
        rows[key].notes = json.dumps({str(cols[key].id): f"통화 기록-{key}"},
                                     ensure_ascii=False)
    db.commit()

    return {"people": people, "rows": rows, "cols": cols}


@pytest.fixture()
def sign_in(db, users):
    """역할 이름 → 그 사람으로 로그인한 클라이언트.

    사람마다 클라이언트를 따로 만든다. 하나를 돌려 쓰면 나중 로그인이 앞
    세션을 덮어써 검사가 무의미해진다.
    """
    from fastapi.testclient import TestClient

    from app.main import create_app

    app = create_app()
    phones = {"member": "01000000001", "other": "01000000002",
              "consultant": "01000000081", "admin": "01000000082"}

    def _open(who: str):
        client = TestClient(app)
        r = client.post("/login", data={"phone": phones[who], "password": DEMO_PASSWORD},
                        follow_redirects=False)
        assert r.status_code == 303
        return client

    return _open


# --- 훑기 도구 ---------------------------------------------------------------

def _visible_rows(client) -> set:
    """화면에 실제로 떠 있는 줄 번호.

    표는 탭으로 나뉘고 월 열은 접혀 있다 — 탭을 다 돌고 `months=all` 로 펴서
    본다. 한 탭만 보고 '안 보인다'고 하면 다른 탭에 떠 있는 줄을 못 고친다고
    적어 두는 셈이다.
    """
    found = set()
    for sheet in _sheet_names(client):
        body = client.get(f"/consulting?months=all&sheet={sheet}").text
        found |= {int(m) for m in re.findall(r'<tr data-id="(\d+)"', body)}
    return found


def _sheet_names(client) -> list:
    """화면이 내놓는 탭 이름들.

    목록을 여기 적어 두지 않는다 — 이름은 화면에서 고치는 값이라, 적어 두면
    이름을 바꿨을 때 검사만 옛 탭을 훑고 새 탭에 뜬 줄을 못 본 채 통과한다.
    """
    from urllib.parse import unquote

    listing = client.get("/consulting").text
    names = [unquote(m) for m in
             re.findall(r'href="/consulting\?sheet=([^"&]+)"', listing)]
    return list(dict.fromkeys(names))


def _visible_columns(client) -> set:
    """화면에 떠 있는 월 열 번호(머리글의 [✕] 단추가 그 번호를 싣고 있다)."""
    found = set()
    for sheet in _sheet_names(client):
        body = client.get(f"/consulting?months=all&sheet={sheet}").text
        found |= {int(m) for m in
                  re.findall(r'/consulting/columns/(\d+)/delete', body)}
    return found


def _can_edit_row(client, db, row_id: int) -> bool:
    """이 줄을 실제로 고칠 수 있는가. **되읽어** 확인하고 원래대로 돌려 놓는다.

    상태 코드만 믿지 않는다 — 404 라고 답하면서 값은 바꿔 두는 것이 가장
    나쁜 실패다. 여기서 둘이 어긋나면 그 자리에서 터뜨린다.
    """
    from app.models import ConsultingCompany

    db.expire_all()
    before = db.get(ConsultingCompany, row_id).region
    r = client.patch(f"/api/consulting/{row_id}", json={"region": PROBE})
    db.expire_all()
    changed = db.get(ConsultingCompany, row_id).region == PROBE
    assert (r.status_code == 200) == changed, (
        f"{row_id}번: {r.status_code} 를 돌려주면서 값은 "
        f"{'바꿨다' if changed else '안 바꿨다'}")
    if changed:
        db.get(ConsultingCompany, row_id).region = before
        db.commit()
    return changed


def _can_rename_column(client, db, column_id: int) -> bool:
    """이 열 이름을 실제로 바꿀 수 있는가. 역시 되읽고 돌려 놓는다."""
    from app.models import ConsultingColumn

    db.expire_all()
    before = db.get(ConsultingColumn, column_id).label
    r = client.post(f"/consulting/columns/{column_id}/rename",
                    data={"label": PROBE}, follow_redirects=False)
    db.expire_all()
    changed = db.get(ConsultingColumn, column_id).label == PROBE
    assert (r.status_code == 303) == changed, (
        f"{column_id}번 열: {r.status_code} 를 돌려주면서 이름은 "
        f"{'바꿨다' if changed else '안 바꿨다'}")
    if changed:
        db.get(ConsultingColumn, column_id).label = before
        db.commit()
    return changed


# --- 보는 것과 고치는 것이 어긋나지 않는가 -------------------------------------

@pytest.mark.parametrize("who", ["member", "other", "consultant", "admin"])
def test_what_you_can_see_is_exactly_what_you_can_edit(stage, sign_in, db, who):
    """화면에 뜨는 줄은 전부 고쳐지고, 안 뜨는 줄은 하나도 안 고쳐진다.

    이 검사 하나가 이 파일의 뼈대다. 줄을 손으로 나열하면 다음에 줄이 하나
    늘 때 그 줄만 검사 밖으로 빠진다 — DB 에 있는 줄을 전부 훑어 화면과 견준다.
    """
    from app.models import ConsultingCompany

    client = sign_in(who)
    seen = _visible_rows(client)
    everything = {r.id for r in db.query(ConsultingCompany).all()}
    assert seen, f"{who}: 화면에 아무 줄도 없다 — 검사가 헛돈다"
    # 관리자만 전부 본다. 그 외에는 안 보이는 줄이 남아 있어야 검사가 뜻이 있다 —
    # 다 보이는 상태로 통과하면 '못 고친다'는 쪽을 한 번도 안 밟는다.
    assert bool(everything - seen) == (who != "admin"), (
        f"{who}: 보이는 줄 {sorted(seen)} / 전체 {sorted(everything)}")

    editable = {rid for rid in everything if _can_edit_row(client, db, rid)}
    assert editable == seen, (
        f"{who}: 보이는 줄 {sorted(seen)} 과 고쳐지는 줄 {sorted(editable)} 이 다르다")


@pytest.mark.parametrize("who", ["member", "other", "consultant", "admin"])
def test_the_same_holds_for_the_month_columns(stage, sign_in, db, who):
    """열도 사람마다 다르다 — 남의 달 이름을 바꾸면 그 사람 표의 머리글이 바뀐다."""
    from app.models import ConsultingColumn

    client = sign_in(who)
    seen = _visible_columns(client)
    everything = {c.id for c in db.query(ConsultingColumn).all()}
    assert seen, f"{who}: 화면에 아무 열도 없다 — 검사가 헛돈다"
    assert bool(everything - seen) == (who != "admin"), (
        f"{who}: 보이는 열 {sorted(seen)} / 전체 {sorted(everything)}")

    editable = {cid for cid in everything if _can_rename_column(client, db, cid)}
    assert editable == seen, (
        f"{who}: 보이는 열 {sorted(seen)} 과 고쳐지는 열 {sorted(editable)} 이 다르다")


# --- 남의 줄 ------------------------------------------------------------------

def test_someone_elses_row_cannot_be_edited(stage, sign_in, db):
    """404 이고, **값이 그대로**여야 한다."""
    from app.models import ConsultingCompany

    theirs = stage["rows"]["other"]
    before = theirs.region
    r = sign_in("member").patch(f"/api/consulting/{theirs.id}",
                                json={"region": "몰래", "company_name": "몰래"})
    assert r.status_code == 404
    db.expire_all()
    kept = db.get(ConsultingCompany, theirs.id)
    assert kept.region == before
    assert kept.company_name == "샘플기업-other"


def test_someone_elses_row_cannot_be_deleted(stage, sign_in, db):
    from app.models import ConsultingCompany

    theirs = stage["rows"]["other"]
    r = sign_in("member").delete(f"/api/consulting/{theirs.id}")
    assert r.status_code == 404
    db.expire_all()
    assert db.get(ConsultingCompany, theirs.id) is not None


def test_a_missing_row_and_someone_elses_row_answer_the_same(stage, sign_in):
    """남의 것은 '없는 것' 이다 — 갈라 답하면 번호를 훑어 남의 표 크기를 알 수 있다."""
    client = sign_in("member")
    theirs = client.patch(f"/api/consulting/{stage['rows']['other'].id}",
                          json={"region": "몰래"})
    missing = client.patch("/api/consulting/99999", json={"region": "몰래"})
    assert theirs.status_code == missing.status_code == 404
    assert theirs.json() == missing.json()


def test_an_unassigned_row_is_not_up_for_grabs(stage, sign_in, db):
    """주인 없는 줄은 관리자가 배정할 것이지, 먼저 본 사람이 갖는 것이 아니다."""
    from app.models import ConsultingCompany

    orphan = stage["rows"]["unassigned"]
    r = sign_in("member").patch(f"/api/consulting/{orphan.id}", json={"region": "내것"})
    assert r.status_code == 404
    db.expire_all()
    assert db.get(ConsultingCompany, orphan.id).region == "지역-미배정"


# --- 자기 줄은 그대로 고쳐진다 --------------------------------------------------

@pytest.mark.parametrize("who", ["member", "consultant"])
def test_my_own_row_is_still_editable(stage, sign_in, db, who):
    """막는 김에 자기 것까지 막으면 고친 것이 아니다.

    컨설턴트에게는 이 화면이 전부다 — 여기가 막히면 그 계정은 할 일이 없다.
    """
    from app.models import ConsultingCompany

    mine = stage["rows"][who]
    client = sign_in(who)
    assert client.patch(f"/api/consulting/{mine.id}",
                        json={"management": "관리 중 · 재통화"}).status_code == 200
    db.expire_all()
    assert db.get(ConsultingCompany, mine.id).management == "관리 중 · 재통화"


@pytest.mark.parametrize("who", ["member", "consultant"])
def test_my_own_row_can_still_be_deleted(stage, sign_in, db, who):
    from app.models import ConsultingCompany

    mine_id = stage["rows"][who].id
    assert sign_in(who).delete(f"/api/consulting/{mine_id}").status_code == 200
    # 지워진 줄은 **다시 물어서** 없음을 확인한다. 손에 들고 있던 것을 되읽으면
    # 이미 없는 줄을 새로 고치려다 터진다.
    db.expunge_all()
    assert db.get(ConsultingCompany, mine_id) is None


def test_admin_edits_and_deletes_every_row(stage, sign_in, db):
    """관리자는 보는 범위가 전체다 — 고치는 범위도 전체다."""
    from app.models import ConsultingCompany

    client = sign_in("admin")
    for rid in [r.id for r in db.query(ConsultingCompany).all()]:
        assert client.patch(f"/api/consulting/{rid}",
                            json={"region": "관리자수정"}).status_code == 200
    db.expire_all()
    assert {c.region for c in db.query(ConsultingCompany).all()} == {"관리자수정"}

    for rid in [r.id for r in db.query(ConsultingCompany).all()]:
        assert client.delete(f"/api/consulting/{rid}").status_code == 200
    db.expire_all()
    assert db.query(ConsultingCompany).count() == 0


# --- 월별 열 ------------------------------------------------------------------

def test_someone_elses_column_cannot_be_renamed(stage, sign_in, db):
    from app.models import ConsultingColumn

    theirs = stage["cols"]["other"]
    r = sign_in("member").post(f"/consulting/columns/{theirs.id}/rename",
                               data={"label": "몰래"}, follow_redirects=False)
    assert r.status_code == 404
    db.expire_all()
    assert db.get(ConsultingColumn, theirs.id).label == "8월 리마인드-other"


def test_someone_elses_column_cannot_be_deleted(stage, sign_in, db):
    """열을 지우면 그 달의 기록도 함께 사라진다 — 남의 달을 지우면 남의 기록이 사라진다."""
    from app.models import ConsultingColumn, ConsultingCompany

    theirs = stage["cols"]["other"]
    r = sign_in("member").post(f"/consulting/columns/{theirs.id}/delete",
                               follow_redirects=False)
    assert r.status_code == 404
    db.expire_all()
    assert db.get(ConsultingColumn, theirs.id) is not None
    kept = json.loads(db.get(ConsultingCompany, stage["rows"]["other"].id).notes)
    assert kept[str(theirs.id)] == "통화 기록-other"


def test_deleting_my_column_does_not_reach_into_someone_elses_rows(stage, sign_in, db):
    """자기 열을 지우는 것뿐인데 손이 남의 줄까지 닿으면 안 된다.

    예전에는 기록을 지우면서 표 전체를 훑었다. 열 번호가 겹치는 날 남의
    기록이 조용히 사라진다.
    """
    from app.models import ConsultingColumn, ConsultingCompany

    mine = stage["cols"]["member"]
    theirs_row = stage["rows"]["other"]
    # 남의 줄에 **내 열 번호로 된 기록**을 심어 둔다 — 훑는 범위가 넓으면 이것이 사라진다.
    theirs_row.notes = json.dumps({str(stage["cols"]["other"].id): "통화 기록-other",
                                   str(mine.id): "남의 줄에 남은 기록"},
                                  ensure_ascii=False)
    db.commit()

    mine_id, mine_row_id, theirs_row_id = mine.id, stage["rows"]["member"].id, theirs_row.id
    r = sign_in("member").post(f"/consulting/columns/{mine_id}/delete",
                               follow_redirects=False)
    assert r.status_code == 303
    db.expunge_all()
    assert db.get(ConsultingColumn, mine_id) is None                    # 내 열은 지워졌고
    assert str(mine_id) not in json.loads(
        db.get(ConsultingCompany, mine_row_id).notes)                   # 내 기록도 지워졌고
    kept = json.loads(db.get(ConsultingCompany, theirs_row_id).notes)
    assert kept[str(mine_id)] == "남의 줄에 남은 기록"                    # 남의 줄은 그대로다


def test_adding_a_month_column_does_not_shuffle_someone_elses(stage, sign_in, db):
    """새 열은 맨 앞에 오면서 나머지를 한 칸씩 민다 — 그 손도 자기 표 안이어야 한다."""
    from app.models import ConsultingColumn

    before = stage["cols"]["other"].position
    assert sign_in("member").post("/consulting/columns",
                                  data={"label": "9월 리마인드"},
                                  follow_redirects=False).status_code == 303
    db.expire_all()
    assert db.get(ConsultingColumn, stage["cols"]["other"].id).position == before


# --- 읽는 쪽도 같은 범위인가 -----------------------------------------------------

def test_a_row_cannot_be_read_by_id_from_another_table(stage, sign_in):
    """고치는 길만 막고 읽는 길을 열어 두면 대표자 연락처가 그대로 샌다."""
    client = sign_in("member")
    assert client.get(f"/api/consulting/{stage['rows']['other'].id}").status_code == 404
    assert client.get(f"/api/consulting/{stage['rows']['unassigned'].id}").status_code == 404
    assert client.get(f"/api/consulting/{stage['rows']['member'].id}").status_code == 200


def test_the_export_carries_only_what_the_screen_shows(stage, sign_in, db):
    """엑셀은 화면을 그대로 내려받는 것이다 — 여기서 새면 화면을 막은 뜻이 없다."""
    import io

    openpyxl = pytest.importorskip("openpyxl")

    client = sign_in("member")
    r = client.get("/api/export/consulting.xlsx")
    assert r.status_code == 200
    sheet = openpyxl.load_workbook(io.BytesIO(r.content)).active
    body = "\n".join(str(c) for row in sheet.iter_rows(values_only=True) for c in row)

    assert "샘플기업-member" in body
    for key in ("other", "consultant", "admin", "미배정"):
        assert f"샘플기업-{key}" not in body, f"{key} 의 줄이 엑셀에 섞였다"
    # 열 머리글도 마찬가지다 — 남의 달 이름이 내 파일에 뜨면 그 자체가 정보다.
    assert "8월 리마인드-other" not in body


def test_the_admin_export_carries_everything(stage, sign_in):
    """관리자는 보는 것이 전체이므로 내려받는 것도 전체다."""
    import io

    openpyxl = pytest.importorskip("openpyxl")

    r = sign_in("admin").get("/api/export/consulting.xlsx")
    sheet = openpyxl.load_workbook(io.BytesIO(r.content)).active
    body = "\n".join(str(c) for row in sheet.iter_rows(values_only=True) for c in row)
    for key in ("member", "other", "consultant", "admin", "미배정"):
        assert f"샘플기업-{key}" in body


def test_an_import_never_touches_someone_elses_table(stage, sign_in, db):
    """시트를 통째로 갈아끼우는 길이라 범위가 어긋나면 한 번에 남의 표가 사라진다."""
    import io

    openpyxl = pytest.importorskip("openpyxl")
    from app.models import ConsultingCompany

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["NO", "지역", "기업명 / 계약일", "8월 리마인드-member"])
    ws.append(["1", "서울", "샘플기업-올림", "카톡 완료"])
    buf = io.BytesIO()
    wb.save(buf)

    r = sign_in("member").post(
        "/consulting/import",
        files={"file": ("현황.xlsx", buf.getvalue(),
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        data={"replace": "1"}, follow_redirects=False)
    assert r.status_code == 303
    db.expire_all()
    survivors = {c.company_name for c in db.query(ConsultingCompany).all()}
    for key in ("other", "consultant", "admin", "미배정"):
        assert f"샘플기업-{key}" in survivors, f"{key} 의 줄이 남의 업로드에 지워졌다"
    assert "샘플기업-올림" in survivors
    assert "샘플기업-member" not in survivors      # 내 것만 갈아끼운다
