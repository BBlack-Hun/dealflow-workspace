"""투자컨설턴트 현황.

이 표에는 대표자 연락처·이메일이 들어 있다. 팀 전체에 열어 둘 표가 아니라
**누가 볼 수 있는가**가 첫 번째 경계다.

원본이 구글시트라 값이 대부분 자유 문장이고(미팅일이 `9/16 PM2 (화상미팅)`),
월별 리마인드 열은 달마다 하나씩 늘어난다. 형식을 강제하거나 열을 테이블 컬럼으로
두면 원본을 옮길 수 없다 — 그 두 가지를 여기서 지킨다.
"""
from __future__ import annotations

import io

import pytest

from .conftest import DEMO_PASSWORD

openpyxl = pytest.importorskip("openpyxl")

# 실제 시트와 같은 모양의 **가상** 데이터.
HEADER = ["NO", "지역", "미팅일(화상, 회의실)",
          "기업명 / 계약일 / 무료유료 / 계약금, 성과수수료 %",
          "기업 관리 [ 드랍 이유 상세하게 기입 / 관리중 / 백업팀으로 전환 ]",
          "8월 마지막주 리마인드 톡 or TEL",
          "7월 마지막주 리마인드 톡 or TEL",
          "대표자", "연락처", "이메일"]
SHEET_ROWS = [
    ["", "", "", "", "", "", "", "", "", ""],      # 시트 위쪽 빈 줄
    ["", "", "", "드랍", "", "", "", "", "", ""],  # 제목 비슷한 줄
    HEADER,
    ["3", "서울", "9/16 PM2 (화상미팅)", "샘플애그", "관리 중. 투자유치 시작 전",
     "카톡 완료 08.13", "", "홍길동", "010-0000-0001", "hong@example.com"],
    ["4", "대구", "2026.01.13", "샘플메디", "드랍 : 연락 두절",
     "", "7월 카톡 완료", "김서연", "010-0000-0002", "kim@example.com"],
    ["5", "", "", "", "", "", "", "", "", ""],     # 번호만 있는 빈 줄
]


def _xlsx(rows, title="중요 스타트업") -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = title
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


@pytest.fixture()
def allowed(client, db, users):
    """이 화면을 보도록 허용된 계정."""
    users["u1"].can_view_consulting = 1
    db.commit()
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    return client


@pytest.fixture()
def outsider(client, users):
    client.post("/login", data={"phone": "01000000002", "password": DEMO_PASSWORD})
    return client


def _import(client, rows=None, **form):
    return client.post(
        "/consulting/import",
        files={"file": ("현황.xlsx", _xlsx(rows or SHEET_ROWS),
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        data=form, follow_redirects=False,
    )


# --- 누가 볼 수 있는가 ------------------------------------------------------

def test_page_is_closed_by_default(outsider):
    """허용되지 않은 계정은 볼 수 없다 — 대표자 연락처가 들어 있는 표다."""
    assert outsider.get("/consulting").status_code == 403


def test_allowed_user_can_open(allowed):
    assert allowed.get("/consulting").status_code == 200


def test_admin_can_open_without_the_flag(client, db, users):
    users["u2"].role = "admin"
    db.commit()
    client.post("/login", data={"phone": "01000000002", "password": DEMO_PASSWORD})
    assert client.get("/consulting").status_code == 200


def test_menu_hides_the_tab_from_others(outsider):
    assert "투자컨설턴트 현황" not in outsider.get("/deals").text


def test_menu_shows_the_tab_to_allowed_user(allowed):
    assert "투자컨설턴트 현황" in allowed.get("/deals").text


def test_api_is_closed_too(allowed, db):
    """화면만 막고 API 를 열어 두면 막은 것이 아니다.

    (fixture 의 client 는 하나뿐이라 계정을 바꿔 다시 로그인한다 —
     두 fixture 를 함께 받으면 나중 로그인이 앞 세션을 덮어써 검사가 무의미해진다)
    """
    from app.models import ConsultingCompany

    _import(allowed)
    db.expire_all()
    row_id = db.query(ConsultingCompany).first().id

    allowed.post("/login", data={"phone": "01000000002", "password": DEMO_PASSWORD})
    assert allowed.get(f"/api/consulting/{row_id}").status_code == 403
    assert allowed.patch(f"/api/consulting/{row_id}", json={"region": "몰래"}).status_code == 403
    assert allowed.get("/api/export/consulting.xlsx").status_code == 403


# --- 시트 읽기 --------------------------------------------------------------

def test_header_is_found_by_content_not_position(allowed, db):
    """머리행 위에 빈 줄·제목이 있어도 찾아낸다(사람이 줄을 넣다 뺐다 한다)."""
    from app.models import ConsultingColumn, ConsultingCompany

    _import(allowed)
    db.expire_all()
    names = {c.company_name for c in db.query(ConsultingCompany).all()}
    assert names == {"샘플애그", "샘플메디"}
    # 고정 열이 아닌 나머지는 월별 리마인드 열로 이름 그대로 들어온다
    labels = {c.label for c in db.query(ConsultingColumn).all()}
    assert labels == {"8월 마지막주 리마인드 톡 or TEL", "7월 마지막주 리마인드 톡 or TEL"}


def test_rows_without_a_company_name_are_skipped(allowed, db):
    """번호만 있고 기업명이 없는 줄은 빈 칸이다 — 유령 행을 만들지 않는다."""
    from app.models import ConsultingCompany

    _import(allowed)
    db.expire_all()
    assert db.query(ConsultingCompany).count() == 2


def test_free_text_values_survive(allowed, db):
    """미팅일이 '9/16 PM2 (화상미팅)' 이어도 그대로 들어와야 한다."""
    from app.models import ConsultingCompany

    _import(allowed)
    db.expire_all()
    row = db.query(ConsultingCompany).filter_by(company_name="샘플애그").first()
    assert row.meeting_at == "9/16 PM2 (화상미팅)"
    assert row.region == "서울"
    assert row.email == "hong@example.com"


def test_reimport_updates_instead_of_duplicating(allowed, db):
    from app.models import ConsultingCompany

    _import(allowed)
    _import(allowed)
    db.expire_all()
    assert db.query(ConsultingCompany).count() == 2


# --- 고치기 -----------------------------------------------------------------

def test_cell_edit_saves(allowed, db):
    from app.models import ConsultingCompany

    _import(allowed)
    db.expire_all()
    row = db.query(ConsultingCompany).first()
    r = allowed.patch(f"/api/consulting/{row.id}", json={"management": "관리 중 · 재통화"})
    assert r.status_code == 200
    db.expire_all()
    assert db.get(ConsultingCompany, row.id).management == "관리 중 · 재통화"


def test_note_edit_keeps_other_months(allowed, db):
    """한 달을 고쳤다고 다른 달 기록이 사라지면 안 된다."""
    import json

    from app.models import ConsultingColumn, ConsultingCompany

    _import(allowed)
    db.expire_all()
    row = db.query(ConsultingCompany).filter_by(company_name="샘플메디").first()
    july = db.query(ConsultingColumn).filter_by(
        label="7월 마지막주 리마인드 톡 or TEL").first()
    august = db.query(ConsultingColumn).filter_by(
        label="8월 마지막주 리마인드 톡 or TEL").first()

    allowed.patch(f"/api/consulting/{row.id}",
                  json={"notes": {str(august.id): "8월 통화 완료"}})
    db.expire_all()
    notes = json.loads(db.get(ConsultingCompany, row.id).notes)
    assert notes[str(august.id)] == "8월 통화 완료"
    assert notes[str(july.id)] == "7월 카톡 완료"      # 원래 있던 달은 그대로


def test_new_month_column_goes_first(allowed, db):
    """새 달은 맨 앞에 온다 — 지금 챙겨야 할 달이 먼저 보여야 한다."""
    from app.models import ConsultingColumn

    _import(allowed)
    allowed.post("/consulting/columns", data={"label": "9월 마지막주 리마인드"},
                 follow_redirects=False)
    db.expire_all()
    cols = db.query(ConsultingColumn).order_by(ConsultingColumn.position).all()
    assert cols[0].label == "9월 마지막주 리마인드"


def test_deleting_a_column_removes_its_notes(allowed, db):
    import json

    from app.models import ConsultingColumn, ConsultingCompany

    _import(allowed)
    db.expire_all()
    august = db.query(ConsultingColumn).filter_by(
        label="8월 마지막주 리마인드 톡 or TEL").first()
    august_id = august.id

    allowed.post(f"/consulting/columns/{august_id}/delete", follow_redirects=False)
    db.expire_all()
    for company in db.query(ConsultingCompany).all():
        assert str(august_id) not in json.loads(company.notes or "{}")


def test_new_row_gets_the_next_number(allowed, db):
    """새 줄의 NO 를 사람이 매번 세지 않아도 된다."""
    from app.models import ConsultingCompany

    _import(allowed)
    r = allowed.post("/api/consulting", json={"company_name": "샘플페이"})
    assert r.status_code == 200
    db.expire_all()
    added = db.query(ConsultingCompany).filter_by(company_name="샘플페이").first()
    assert added.position == 5          # 시트의 마지막 번호가 4였다


def test_row_without_a_name_is_rejected(allowed):
    assert allowed.post("/api/consulting", json={"company_name": "  "}).status_code == 400


# --- 권한 부여 · 회수 -------------------------------------------------------
#
# 대표자 연락처가 들어 있는 표라, 누가 볼 수 있는지를 관리자가 쥐고 있어야 한다.

def test_admin_grants_and_revokes(client, db, users):
    from app.models import User

    users["u2"].role = "admin"
    db.commit()
    client.post("/login", data={"phone": "01000000002", "password": DEMO_PASSWORD})

    client.post(f"/team/members/{users['u1'].id}/consulting", follow_redirects=False)
    db.expire_all()
    assert db.get(User, users["u1"].id).can_view_consulting == 1

    client.post(f"/team/members/{users['u1'].id}/consulting", follow_redirects=False)
    db.expire_all()
    assert db.get(User, users["u1"].id).can_view_consulting == 0


def test_revoking_closes_the_page_at_once(client, db, users):
    """회수하면 그 자리에서 막혀야 한다 — 다음 로그인까지 기다리면 안 된다."""
    users["u1"].can_view_consulting = 1
    users["u2"].role = "admin"
    db.commit()

    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    assert client.get("/consulting").status_code == 200

    client.post("/login", data={"phone": "01000000002", "password": DEMO_PASSWORD})
    client.post(f"/team/members/{users['u1'].id}/consulting", follow_redirects=False)

    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    assert client.get("/consulting").status_code == 403


def test_only_admin_can_change_it(client, db, users):
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    r = client.post(f"/team/members/{users['u2'].id}/consulting")
    assert r.status_code == 403


# --- 투자컨설턴트 전용 계정 -----------------------------------------------------

def test_consultant_sees_only_their_screen(client, db, users):
    """딜소개를 하지 않는 사람이라 발송·투자사 명단을 보여줄 이유가 없다 —
    볼 수 있으면 실수로 건드린다."""
    from app.ui import visible_menu

    users["u1"].role = "consultant"
    db.commit()

    keys = [m["key"] for m in visible_menu(users["u1"])]
    assert keys == ["consult"], keys


def test_consultant_can_open_the_page_without_the_extra_flag(client, db, users):
    """계정 자체가 그 화면 전용이다 — 따로 켜 줄 필요가 없다."""
    users["u1"].role = "consultant"
    users["u1"].can_view_consulting = 0
    db.commit()

    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    assert client.get("/consulting").status_code == 200


def test_consultant_lands_on_their_screen(client, db, users):
    """대시보드를 볼 이유가 없다."""
    users["u1"].role = "consultant"
    db.commit()

    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/consulting"


# --- 월 컬럼 접기 ---------------------------------------------------------------

def test_only_recent_months_are_shown(client, db, users):
    """달마다 한 칸씩 늘어나는 표라, 한 해 뒤에는 열두 칸이 되어 가로로
    밀어야 읽힌다. 실제로 챙기는 것은 최근 몇 달뿐이다."""
    from app.models import ConsultingColumn
    from app.routers.consulting import VISIBLE_MONTHS, _split_columns

    cols = [ConsultingColumn(label=f"{m}월 리마인드", position=i)
            for i, m in enumerate(range(12, 0, -1))]
    shown, hidden = _split_columns(cols)
    assert len(shown) == VISIBLE_MONTHS
    assert len(hidden) == 12 - VISIBLE_MONTHS
    # 최근 것이 남는다
    assert shown[0].label == "12월 리마인드"

    # 일부러 다 보겠다고 하면 접지 않는다
    all_shown, none_hidden = _split_columns(cols, show_all=True)
    assert len(all_shown) == 12 and none_hidden == []


def test_the_user_is_told_that_months_are_folded(client, db, users):
    """그냥 안 보이면 지워진 줄 안다."""
    from app.models import ConsultingColumn

    # 표에는 주인이 있다 — 남의 열이 내 표에 섞이면 안 된다
    for i, m in enumerate(range(12, 0, -1)):
        db.add(ConsultingColumn(label=f"{m}월 리마인드", position=i,
                                user_id=users["u1"].id))
    db.commit()

    users["u1"].can_view_consulting = 1
    db.commit()
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})

    body = client.get("/consulting").text
    assert "접어 두었습니다" in body
    assert "지워진 것이 아닙니다" in body
    # 펴는 링크는 지금 보고 있는 시트를 유지한다 — 펴면서 다른 탭으로
    # 튕기면 찾던 표를 다시 찾아야 한다.
    assert "months=all" in body
    assert "/consulting?sheet=" in body

    # 펴면 다 보인다
    opened = client.get("/consulting?months=all").text
    assert "1월 리마인드" in opened

# --- 사람별로 나뉘는가 ------------------------------------------------------

def _own(db, user_id, name="샘플기업", sheet="중요 스타트업"):
    from app.models import ConsultingCompany

    row = ConsultingCompany(user_id=user_id, company_name=name, sheet=sheet)
    db.add(row)
    db.commit()
    return row


def test_i_only_see_my_own_table(client, db, users):
    """컨설턴트가 여럿이면 남의 담당 기업까지 보인다."""
    users["u1"].can_view_consulting = 1
    users["u2"].can_view_consulting = 1
    db.commit()
    _own(db, users["u1"].id, "내기업")
    _own(db, users["u2"].id, "남의기업")

    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    body = client.get("/consulting").text
    assert "내기업" in body
    assert "남의기업" not in body


def test_admin_sees_everyone(client, db, users):
    """관리자는 누가 무엇을 맡고 있는지 알아야 한다."""
    users["u2"].role = "admin"
    db.commit()
    _own(db, users["u1"].id, "내기업")
    _own(db, users["u2"].id, "남의기업")

    client.post("/login", data={"phone": "01000000002", "password": DEMO_PASSWORD})
    body = client.get("/consulting").text
    assert "내기업" in body and "남의기업" in body
    assert "담당" in body          # 사람별로 갈라 보는 줄


def test_admin_can_narrow_to_one_person(client, db, users):
    users["u2"].role = "admin"
    db.commit()
    _own(db, users["u1"].id, "내기업")
    _own(db, users["u2"].id, "남의기업")

    client.post("/login", data={"phone": "01000000002", "password": DEMO_PASSWORD})
    body = client.get(f"/consulting?owner={users['u1'].id}").text
    assert "내기업" in body
    assert "남의기업" not in body


def test_a_row_cannot_be_opened_by_id_from_another_table(client, db, users):
    """화면만 막고 API 를 열어 두면 막은 것이 아니다."""
    users["u1"].can_view_consulting = 1
    db.commit()
    theirs = _own(db, users["u2"].id, "남의기업")

    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    assert client.get(f"/api/consulting/{theirs.id}").status_code == 404


def test_a_reupload_does_not_wipe_someone_elses_table(client, db, users):
    """예전에는 전체를 지워서, 한 사람이 다시 올리면 남의 표까지 사라졌다."""
    from app.models import ConsultingCompany

    users["u1"].can_view_consulting = 1
    db.commit()
    _own(db, users["u2"].id, "남의기업")

    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    _import(client, replace="1")
    db.expire_all()

    kept = db.query(ConsultingCompany).filter_by(user_id=users["u2"].id).count()
    assert kept == 1, "남의 표가 지워졌다"


def test_an_upload_belongs_to_whoever_uploaded_it(client, db, users):
    from app.models import ConsultingCompany

    users["u1"].can_view_consulting = 1
    db.commit()
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    _import(client)
    db.expire_all()

    owners = {c.user_id for c in db.query(ConsultingCompany).all()}
    assert owners == {users["u1"].id}

