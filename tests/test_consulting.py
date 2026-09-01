"""투자컨설턴트 현황.

이 표에는 대표자 연락처·이메일이 들어 있다. 팀 전체에 열어 둘 표가 아니라
**누가 볼 수 있는가**가 첫 번째 경계다.

원본이 구글시트라 값이 대부분 자유 문장이고(미팅일이 `9/16 PM2 (화상미팅)`),
월별 리마인드 열은 달마다 하나씩 늘어난다. 형식을 강제하거나 열을 테이블 컬럼으로
두면 원본을 옮길 수 없다 — 그 두 가지를 여기서 지킨다.
"""
from __future__ import annotations

import io
import json

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


def _xlsx(rows, title="스타트업") -> bytes:
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
    from app.ui import menu_label

    assert menu_label("consult") not in outsider.get("/deals").text


def test_menu_shows_the_tab_to_allowed_user(allowed):
    # 메뉴 이름은 `app/ui.py` 의 `MENU` 한 곳에서 나온다 — 여기 글자를 박아 두면
    # 이름을 고칠 때 검사만 옛 이름으로 남는다.
    from app.ui import menu_label

    assert menu_label("consult") in allowed.get("/deals").text


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


# --- [기업 추가] 는 **지금 보고 있는 탭**에 넣는다 ----------------------------
#
# 탭이 셋인데(`스타트업` · `경영본부 전달 기업` · `월간 계약 업무현황표`)
# 어느 탭에서 눌러도 첫 탭으로 들어갔다. 줄은 만들어졌지만 보고 있는 탭에는
# 없으니, 누른 사람 눈에는 **추가가 안 된 것처럼** 보인다.


def _tab_names(db) -> list:
    """지금 서 있는 탭 이름들. **목록을 여기 적어 두지 않는다** — 이름은 화면에서
    고치는 값이라(`ConsultingSheet.label`) 적어 두면 검사만 옛 이름을 본다."""
    from app.services.consulting_sheets import labels

    return labels(db)


def test_기업_추가는_지금_보고_있는_탭에_들어간다(allowed, db):
    from app.models import ConsultingCompany

    for i, sheet in enumerate(_tab_names(db)):
        name = f"샘플기업{i}"
        r = allowed.post("/api/consulting",
                         json={"company_name": name, "sheet": sheet})
        assert r.status_code == 200, r.text
        db.expire_all()
        added = db.query(ConsultingCompany).filter_by(company_name=name).one()
        assert added.sheet == sheet, f"{sheet} 탭에서 눌렀는데 {added.sheet} 로 들어갔다"


def test_없는_탭_이름은_받지_않는다(allowed):
    """오타 하나로 **없던 탭이 생기면** 그 줄은 아무도 다시 못 찾는다."""
    r = allowed.post("/api/consulting",
                     json={"company_name": "샘플기업X", "sheet": "스타트웁"})
    assert r.status_code == 400


def test_탭을_안_보내면_예전처럼_첫_탭이다(allowed, db):
    """옛 동작을 그대로 둔다 — 탭을 못 고른 화면에서도 추가는 되어야 한다."""
    from app.services.consulting_sheets import default_label
    from app.models import ConsultingCompany

    assert allowed.post("/api/consulting",
                        json={"company_name": "샘플기업Z"}).status_code == 200
    db.expire_all()
    assert db.query(ConsultingCompany).filter_by(
        company_name="샘플기업Z").one().sheet == default_label(db)


def test_추가한_줄이_그_탭_화면에_보인다(allowed, db):
    """DB 에만 들어가고 화면에 안 보이면 고친 것이 아니다."""
    names = _tab_names(db)
    assert allowed.post("/api/consulting",
                        json={"company_name": "샘플기업W", "sheet": names[1]}).status_code == 200
    assert "샘플기업W" in allowed.get(f"/consulting?sheet={names[1]}").text
    assert "샘플기업W" not in allowed.get(f"/consulting?sheet={names[0]}").text


def test_추가_단추가_지금_탭을_싣고_있다():
    """서버만 고치면 반쪽이다 — 화면이 탭을 안 실어 보내면 그대로다.

    값을 넘기는 방식은 딜 소싱의 `[○○에 추가]`(`data-bucket`)를 그대로 따른다.
    화면마다 다른 방식을 쓰면 다음 사람이 어느 쪽을 봐야 할지 모른다.
    """
    import pathlib as _p

    html = _p.Path("app/templates/consulting.html").read_text(encoding="utf-8")
    assert 'id="cs-add"' in html
    assert 'data-sheet="{{ selected_sheet }}"' in html, \
        "[기업 추가] 단추가 지금 보고 있는 탭을 안 싣고 있습니다"
    js = _p.Path("app/static/js/consulting.js").read_text(encoding="utf-8")
    assert 'getAttribute("data-sheet")' in js, "단추에 실어 둔 탭을 안 읽습니다"
    assert "body.sheet" in js, "탭을 서버로 안 보냅니다"


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

def _own(db, user_id, name="샘플기업", sheet=None):
    from app.models import ConsultingCompany
    from app.services.consulting_sheets import default_label

    # 첫 탭 이름을 여기 박아 두면 이름을 고칠 때 이 줄만 옛 탭에 남아,
    # 화면에는 안 보이는데 검사만 "있다" 고 우긴다.
    row = ConsultingCompany(user_id=user_id, company_name=name,
                            sheet=sheet or default_label(db))
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

def test_the_contract_sheet_is_a_tab_too(client, db, users):
    """머리글 있는 표가 아니라고 건너뛰면 화면에서 아예 볼 수 없다."""
    from app.models import ConsultingCompany
    from app.routers.consulting import is_contract

    assert "월간 계약 업무현황표" in _tab_names(db)
    # 이름이 아니라 **열쇠**로 계약 표를 고른다 — 이름을 고쳐도 표가 안 바뀐다.
    assert is_contract(db, "월간 계약 업무현황표")

    users["u1"].can_view_consulting = 1
    db.add(ConsultingCompany(user_id=users["u1"].id, sheet="월간 계약 업무현황표",
                             position=1, region="6월", management="무료",
                             company_name="샘플기업/ 무료/ 3.5%/ 미정"))
    db.commit()

    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    body = client.get("/consulting?sheet=%EC%9B%94%EA%B0%84%20%EA%B3%84%EC%95%BD%20%EC%97%85%EB%AC%B4%ED%98%84%ED%99%A9%ED%91%9C").text
    assert "샘플기업/ 무료/ 3.5%/ 미정" in body


def test_the_contract_sheet_reads_month_and_kind_from_the_line(tmp_path):
    """왼쪽 라벨은 병합 때문에 줄과 어긋나 있다 — 줄 안에 적힌 것을 믿는다."""
    import sys

    sys.path.insert(0, "scripts")
    from import_consulting import parse_contract_sheet

    wb = openpyxl.Workbook()
    ws = wb.active
    for row in [
        ["", ""],
        ["6월  (무료계약 2개사 / 유료계약 3개사)", ""],
        ["무료 계약", "기업명 / 계약금액 / 성공보수율 / 계약일"],
        ["유료 계약", "샘플가/ 무료/ 3.5%/ 미정"],      # 라벨은 '유료' 인데 줄은 '무료'
        ["", "샘플나/무료/4%/미정"],
        ["", ""],
        ["7월 ( 무료계약 3개사 )", ""],
        ["무료계약", "기업명 / 계약금액 / 성공보수율 / 계약일"],
        ["", "샘플다/ 유료 90만/ 3프로 / 미정"],
    ]:
        ws.append(row)

    got = parse_contract_sheet(ws)
    assert [(g["month"], g["kind"]) for g in got] == [
        ("6월", "무료"), ("6월", "무료"), ("7월", "유료")]
    # 머리글 줄은 값이 아니다
    assert all("기업명 /" not in g["line"] for g in got)



# --- KPI 와 칩 ---------------------------------------------------------------
#
# 화면 위 숫자와 칩은 **할 일을 고르는 자리**다. 다 한 수를 보여 주면 봐도 할
# 일이 안 나오고, 칩이 안 걸리면 34줄을 눈으로 훑게 된다.


def _consulting_ctx(db, users, columns, rows_notes):
    """열과 줄을 깔고 화면을 연다. (본문, 열 id 목록)"""
    from app.models import ConsultingColumn, ConsultingCompany
    from app.services.consulting_sheets import default_label

    cols = []
    for pos, label in enumerate(columns):
        col = ConsultingColumn(user_id=users["u1"].id, sheet=default_label(db),
                               label=label, position=pos)
        db.add(col)
        cols.append(col)
    db.flush()
    for i, notes in enumerate(rows_notes):
        db.add(ConsultingCompany(
            user_id=users["u1"].id, sheet=default_label(db), position=i + 1,
            company_name=f"샘플기업{i}",
            notes=json.dumps({str(cols[k].id): v for k, v in notes.items()},
                             ensure_ascii=False)))
    db.commit()
    return cols


def _mgmt_ctx(db, users, managements, notes=None):
    """`기업 관리` 칸만 다른 줄들을 깐다. (실제 시트와 같은 모양의 **가상** 값)

    `notes` 를 주면 월별 리마인드 칸도 같이 깐다(줄 순서대로). `연락 기록 없음`
    은 두 칸을 **같이** 보므로, 한쪽만 깔아서는 그 칩을 검사할 수 없다.
    """
    from app.models import ConsultingColumn, ConsultingCompany
    from app.services.consulting_sheets import default_label

    col = None
    if notes is not None:
        col = ConsultingColumn(user_id=users["u1"].id, sheet=default_label(db),
                               label="8월 리마인드", position=0)
        db.add(col)
        db.flush()
    for i, text in enumerate(managements):
        note = (notes or [])[i] if notes is not None else ""
        db.add(ConsultingCompany(
            user_id=users["u1"].id, sheet=default_label(db), position=i + 1,
            company_name=f"샘플기업{i}", management=text,
            notes=json.dumps({str(col.id): note}, ensure_ascii=False) if col else None))
    db.commit()


def test_KPI_는_지난달_빈칸을_센다(allowed, db, users):
    """다 한 수는 봐도 할 일이 안 나온다 — **아직 안 한 곳**을 센다.

    기준은 지난달이다. 진행 중인 달을 세면 월 초에는 전부 미완료라 늘 전체
    건수가 뜬다(그 열은 이제 월 초에 저절로 생긴다).
    """
    from app.routers.consulting import _prev_month

    prev = _prev_month()
    this = prev % 12 + 1
    # 세 줄 중 하나만 지난달 기록이 있다 → 미완료 2
    _consulting_ctx(db, users,
                    [f"{this}월 마지막주 리마인드 톡 or TEL",
                     f"{prev}월 마지막주 리마인드 톡 or TEL"],
                    [{1: "카톡 완료"}, {0: "이번달만 했다"}, {}])

    body = allowed.get("/consulting").text
    assert f"{prev}월 마지막주 리마인드톡 미완료 기업" in body
    assert "이전달 연락 기록 있음" not in body, "옛 이름이 남아 있습니다"
    # 값은 KPI 카드 안에서 읽는다 — 다른 숫자와 섞이지 않게.
    card = body.split(f"{prev}월 마지막주 리마인드톡 미완료 기업")[1]
    assert ">2<" in card.split("</div>")[0]


def test_지난달_열이_없으면_전부_미완료로_세지_않는다(allowed, db, users):
    """빈칸을 그냥 세면 "열이 없다" 가 "전부 미완료" 로 둔갑한다."""
    from app.routers.consulting import _prev_month

    this = _prev_month() % 12 + 1
    _consulting_ctx(db, users, [f"{this}월 리마인드"], [{}, {}, {}])
    body = allowed.get("/consulting").text
    assert "지난달 열이 없습니다" in body
    card = body.split("미완료 기업")[1]
    assert ">0<" in card.split("</div>")[0]


def test_연락_기록_없음_칩이_보는_값(allowed, db, users):
    """칩은 줄의 `data-contacted` 를 본다 — 기록이 하나도 없는 줄만 걸려야 한다."""
    import re

    from app.routers.consulting import _prev_month

    prev = _prev_month()
    this = prev % 12 + 1
    _consulting_ctx(db, users, [f"{this}월 리마인드", f"{prev}월 리마인드"],
                    [{0: "8월 통화"}, {1: "7월 통화"}, {}])
    body = allowed.get("/consulting").text
    flags = re.findall(r'data-contacted="(\d)"', body)
    assert flags == ["1", "1", "0"], flags
    assert 'data-cs-filter="nocontact"' in body and ">연락 기록 없음<" in body


def test_기업_관리에_값이_있으면_연락_기록_없음이_아니다(allowed, db, users):
    """`연락 기록 없음` 은 **아무것도 안 적힌 줄**이다.

    예전에는 월별 리마인드 칸만 봤다. 그래서 `기업 관리` 에
    `관리 중 : 미팅 완. -> 견적서 보내기 완료.` 라고 적어 둔 줄이, 리마인드
    칸이 비었다는 이유로 `관리 중` 과 `연락 기록 없음` 에 **동시에** 떴다.
    화면에서는 세 칩이 나란히 붙어 한 갈래로 읽히는데 실제로는 두 갈래를 섞어
    놓은 것이라, 관리 중인 기업이 "연락 기록 없음" 에 뜨는 것이 틀려 보인다.

    두 칸을 **같이** 본다 — `기업 관리` 가 비어 있고 그리고 리마인드도 다 빔.
    """
    from app.services import consulting_status as status

    # 적어 둔 것이 있으면 — 리마인드가 비어 있어도 — `연락 기록 없음` 이 아니다.
    assert not status.no_contact("관리 중 : 미팅 완. -> 견적서 보내기 완료.", [])
    assert not status.no_contact("드랍 : 연락 두절", [])
    # 셋 중 어느 마디도 아닌 자유 서술도 마찬가지다. 적어 둔 것은 적어 둔 것이다.
    assert not status.no_contact("제안서 검토 후 진행 안 하기로 함", [])
    # 둘 다 비어 있을 때만 걸린다.
    assert status.no_contact("", [])
    assert status.no_contact("   ", ["", "  "])
    # 리마인드에 기록이 있으면 `기업 관리` 가 비어 있어도 아니다.
    assert not status.no_contact("", ["8월 통화 완료"])


def test_기업_관리에_값이_있는_줄은_반드시_칩에_걸린다(allowed, db, users):
    """자유 서술이라 값의 종류가 무한하다 — 그래도 **떨어지는 줄은 없어야** 한다.

    시트 머리글이 정해 둔 마디(`관리 중`·`드랍`·`백업팀 전환`)에 안 맞는 값이
    실제로 있다(`제안서 검토 후 진행 안 하기로 함`). 값마다 칩을
    세우면 칩이 끝없이 늘어나므로, 두 마디에 안 걸리는 나머지를 `그 외` 하나로
    받는다. 값별로 고르는 일은 머리글 `기업 관리 ▾` 가 이미 한다.
    """
    from app.services import consulting_status as status

    for text in ("제안서 검토 후 진행 안 하기로 함",
                 "내후년에 라운드 돌 예정",
                 "판단 보류",
                 "백업팀으로 전환"):
        assert (status.is_managed(text) or status.is_dropped(text)
                or status.is_other(text)), f"{text!r} 이 어느 칩에도 안 걸립니다"
    # `그 외` 는 관리 중·드랍과 겹치지 않는다 — 겹치면 같은 줄이 두 칩에 뜬다.
    assert not status.is_other("관리 중")
    assert not status.is_other("백업팀으로 전환 · 논의 중임. 드랍")
    # 안 적은 줄은 `그 외` 가 아니다. 그 줄은 `연락 기록 없음` 이 받는다.
    assert not status.is_other("")
    assert not status.is_other("   ")


def test_칩_넷이_한_줄도_흘리지_않는다(allowed, db, users):
    """칩으로 거른 줄을 다 합치면 표 전체가 되어야 한다 — 값이 적힌 줄에 한해.

    실데이터에서 34줄 중 12줄이 `관리 중`·`드랍` 어디에도 안 걸렸다. 그 가운데
    값이 적힌 3줄은 이제 `그 외` 가, 아무것도 안 적힌 줄은 `연락 기록 없음` 이
    받는다. 나머지(리마인드만 적힌 줄)는 머리글 `기업 관리 ▾ → (비어 있음)` 이다.
    """
    import re

    from app.services import consulting_status as status

    managements = [
        "관리 중",
        "드랍 : 연락 두절",
        "백업팀으로 전환 · 논의 중임. 드랍",
        "제안서 검토 후 진행 안 하기로 함",   # 자유 서술
        "백업팀으로 전환",                                # 마디는 맞지만 칩은 없다
        "",                                               # 둘 다 빔
        "",                                               # 리마인드만 있는 줄
    ]
    notes = ["", "", "", "", "", "", "8월 통화 완료"]
    _mgmt_ctx(db, users, managements, notes)
    body = allowed.get("/consulting").text

    picked = {"managed": 0, "dropped": 0, "other": 0, "nocontact": 0}
    unmatched = []
    for text, note in zip(managements, notes):
        hit = False
        for key, ok in (("managed", status.is_managed(text)),
                        ("dropped", status.is_dropped(text)),
                        ("other", status.is_other(text)),
                        ("nocontact", status.no_contact(text, [note]))):
            if ok:
                picked[key] += 1
                hit = True
        if not hit:
            unmatched.append(text)

    assert picked == {"managed": 1, "dropped": 2, "other": 2, "nocontact": 1}, picked
    # 값이 적힌 줄은 하나도 안 흘린다. 안 적은 줄만 남는다(머리글이 받는다).
    assert unmatched == [""], unmatched

    # 화면에도 그 칩이 서 있어야 한다.
    assert 'data-cs-filter="other"' in body and ">그 외<" in body
    assert 'data-cs-filter="nocontact"' in body and ">연락 기록 없음<" in body
    # 머리글 필터가 값별로 고르는 일은 그대로다 — 칩과 어긋나면 안 된다.
    tags = re.findall(r'data-f-mgmt="([^"]*)"', body)
    assert tags == ["관리 중", "드랍", "드랍|백업팀 전환", "기타 메모",
                    "백업팀 전환", "", ""], tags


def test_접어_둔_달의_기록도_기록이다(allowed, db, users):
    """칸을 고치면 consulting.js 가 `data-contacted` 를 다시 적는데, 그때 JS 가
    볼 수 있는 것은 **펴 둔 달의 칸뿐**이다. 접힌 달에만 기록이 있는 줄이
    고치는 순간 `기록 없음` 으로 뒤집혔다(실데이터 34줄 중 12줄이 그 상태였다).
    """
    import pathlib as _p
    import re

    from app.routers.consulting import VISIBLE_MONTHS

    labels = [f"{m}월 리마인드" for m in range(12, 12 - VISIBLE_MONTHS - 1, -1)]
    cols = _consulting_ctx(db, users, labels, [{len(labels) - 1: "접힌 달 기록"}])
    body = allowed.get("/consulting").text

    # 마지막 열은 접혀 있다
    assert "접어 두었습니다" in body
    assert f'data-note="{cols[-1].id}"' not in body
    assert re.search(r'data-contacted="1"', body)
    assert 'data-contacted-folded="1"' in body, \
        "접힌 달의 기록을 화면이 안 싣고 있습니다"

    js = _p.Path("app/static/js/consulting.js").read_text(encoding="utf-8")
    assert 'data-contacted-folded' in js, \
        "화면이 실어 준 사실을 JS 가 안 읽습니다 — 고치는 순간 뒤집힙니다"


def test_공백만_있는_리마인드_칸은_기록이_아니다(allowed, db, users):
    """`" "` 한 칸을 기록으로 세면 그 줄은 **아무 칸이나 고치는 순간 뒤집힌다.**

    서버는 값이 비어 있지 않은지만 봤고(젠자의 `select`), 브라우저는 앞뒤 공백을
    떼고 봤다(`trim`). 원본 시트에서 올라온 값은 다듬어지지 않으므로
    (`/consulting/import` 는 칸을 적힌 그대로 넣는다) 공백만 있는 칸이 실제로
    생긴다. 그런 줄은 `연락 기록 있음` 으로 그려졌다가, 칸을 한 번 고치면
    `연락 기록 없음` 으로 넘어갔다 — 화면에 안 보이는 차이라 이유를 알 수 없다.
    """
    import re

    from app.routers.consulting import _prev_month

    prev = _prev_month()
    this = prev % 12 + 1
    _consulting_ctx(db, users, [f"{this}월 리마인드", f"{prev}월 리마인드"],
                    [{0: "   "}, {0: "8월 통화"}])
    body = allowed.get("/consulting").text
    assert re.findall(r'data-contacted="(\d)"', body) == ["0", "1"], \
        "공백만 있는 칸을 기록으로 셌습니다 — 브라우저는 안 그렇게 봅니다"


def test_KPI_와_칩은_같은_줄을_센다(allowed, db, users):
    """위 숫자와 칩으로 거른 줄 수가 다르면 어느 쪽을 믿을지 알 수 없다.

    한 줄에 두 마디가 같이 오는 일이 잦다(`백업팀으로 전환 … 드랍`). 그 줄은
    드랍이라고 적혀 있으니 `드랍` 에 잡혀야 하고, KPI 도 같이 세야 한다.
    """
    import re

    _mgmt_ctx(db, users, [
        "관리 중",
        "관리중 : 견적서 보내기 완료",
        "드랍 : ir 진행 계약 완료 -> 기업 회생 신청",
        "백업팀으로 전환 · 논의 중임. 드랍",
        "내년부터 투자 라운드 돌 예정",       # 적혀 있지만 셋 중 어느 것도 아니다
        "",                                    # 아직 안 적은 줄
    ])
    body = allowed.get("/consulting").text
    tags = re.findall(r'data-f-mgmt="([^"]*)"', body)
    assert tags == ["관리 중", "관리 중", "드랍", "드랍|백업팀 전환", "기타 메모", ""]

    def card(label):
        return int(re.search(r">(\d+)<",
                             body.split(f">{label}</span>")[1]).group(1))

    assert card("관리 중") == sum(1 for t in tags if "관리 중" in t.split("|"))
    assert card("드랍") == sum(1 for t in tags if "드랍" in t.split("|"))
    assert card("전체") == len(tags)


def test_KPI_숫자에_브라우저가_다시_셀_표식이_있다(allowed, db, users):
    """칸을 고치면 칩은 따라오는데 위 숫자만 옛것으로 남아 있었다.

    다시 세는 것은 브라우저다(`consulting.js` 의 `syncKpi`). 어느 숫자가 무엇을
    세는 자리인지 표에 적혀 있지 않으면 브라우저가 고쳐 쓸 자리를 못 찾는다.
    """
    _mgmt_ctx(db, users, ["관리 중", "드랍 : 연락 두절"])
    body = allowed.get("/consulting").text
    for key in ("total", "managed", "dropped"):
        assert f'data-kpi="{key}"' in body, \
            f"`{key}` 숫자에 표식이 없습니다 — 고쳐도 위 숫자는 그대로입니다"


def test_관리_드랍_판정은_한_곳에서만_한다():
    """같은 판단을 세 곳에 적어 두면 한쪽이 낡는다.

    `기업 관리` 칸이 어느 갈래인가를 (1) 라우터의 KPI, (2) 화면의 줄 표시,
    (3) 머리글 필터용 태그가 **각자** 정하고 있었다. 규칙은 한 곳에만 둔다
    (`services/consulting_status.py`) — `deps.may_view_consulting` ·
    `services/sheet_owner.py` 와 같은 자리다.
    """
    import pathlib as _p
    import re

    from app.services import consulting_status as status

    assert status.tag_value("드랍 : 연락 두절") == "드랍"
    assert status.is_dropped("드랍 : 연락 두절") and not status.is_managed("드랍 : 연락 두절")

    # 주석은 옛 모양을 **적어 두는** 자리라 여기서 세면 안 된다. 판정하는
    # **코드**가 남아 있는지만 본다.
    tmpl = re.sub(r"\{#.*?#\}", "",
                  _p.Path("app/templates/consulting.html").read_text(encoding="utf-8"),
                  flags=re.S)
    for word in ("'관리' in", "'드랍' in"):
        assert word not in tmpl, \
            f"화면이 갈래를 다시 정하고 있습니다({word}) — 규칙이 두 벌입니다"

    router = re.sub(r"#[^\n]*", "",
                    _p.Path("app/routers/consulting.py").read_text(encoding="utf-8"))
    for word in ('"관리" in', '"드랍" in'):
        assert word not in router, \
            f"라우터가 갈래를 다시 정하고 있습니다({word}) — 규칙이 두 벌입니다"


@pytest.mark.skipif(__import__("shutil").which("node") is None,
                    reason="node 미설치 — 브라우저 로직 테스트 생략")
def test_화면_코드를_그대로_돌려_본다():
    """규칙을 파이썬으로 옮겨 적으면 두 벌이 되어 어긋나도 모른다.

    `tests/js/consulting_contacted_test.js` 가 consulting.js 를 **실제로 돌려**
    칸을 눌러 고치는 데까지 흉내 낸다. 로컬에서는 `node` 로도 돈다.
    """
    import pathlib as _p
    import shutil
    import subprocess

    js = _p.Path(__file__).resolve().parent / "js" / "consulting_contacted_test.js"
    r = subprocess.run([shutil.which("node"), str(js)],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr


@pytest.mark.skipif(__import__("shutil").which("node") is None,
                    reason="node 미설치 — 브라우저 로직 테스트 생략")
def test_칩이_잡는_줄을_그대로_돌려_본다():
    """칩 넷이 각각 어느 줄을 잡는지 — 규칙은 브라우저에도 한 벌 있다.

    `tests/js/consulting_chips_test.js` 가 consulting.js 를 실제로 돌려, `기업
    관리` 에 값이 있는 줄이 `연락 기록 없음` 에 뜨지 않는지 · 자유 서술 줄이
    `그 외` 에 걸리는지 · 칸을 고치면 그 자리에서 갈래가 바뀌는지를 본다.
    """
    import pathlib as _p
    import shutil
    import subprocess

    js = _p.Path(__file__).resolve().parent / "js" / "consulting_chips_test.js"
    r = subprocess.run([shutil.which("node"), str(js)],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr


@pytest.mark.skipif(__import__("shutil").which("node") is None,
                    reason="node 미설치 — 브라우저 로직 테스트 생략")
def test_고친_값을_KPI_가_따라오는지_그대로_돌려_본다():
    """칩만 따라오고 위 숫자가 옛것이면 사용자는 어느 쪽을 믿을지 알 수 없다.

    `tests/js/consulting_kpi_test.js` 가 consulting.js 를 실제로 돌려 칸을 고치고,
    KPI 가 따라오는지 · 거른 결과가 아니라 표 전체를 세는지까지 본다.
    """
    import pathlib as _p
    import shutil
    import subprocess

    js = _p.Path(__file__).resolve().parent / "js" / "consulting_kpi_test.js"
    r = subprocess.run([shutil.which("node"), str(js)],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr
