"""투자사 연결 파이프라인.

지금까지 시스템에는 **카톡방까지 연결이 끝난** 담당자만 있었다. 실제 운영에서는
그 앞에 '전화 → 카톡 초대 → 연결'이라는 긴 과정이 있고, 그건 시트에만 있었다.

여기서 지키려는 경계.

1. **연결 전 담당자에게 방 이름을 지어 주지 않는다.** 지어 주면 발송 대상처럼
   보이는데 실제로는 보낼 방이 없다.
2. **단계를 뒤로 내리지 않는다.** 이미 방이 붙어 발송까지 한 담당자를 오래된
   명단 시트 하나 때문에 '미착수'로 되돌리면 발송 대상에서 빠진다.
3. **발송 대상은 연결이 끝난 사람만.**
4. **관리자는 팀 전체를 본다.** 직접 보내지는 않지만 누가 무엇을 맡았는지 알아야 한다.
"""
from __future__ import annotations

import io

import pytest

from .conftest import DEMO_PASSWORD

openpyxl = pytest.importorskip("openpyxl")

# 명단 시트(150/98/30명)와 같은 머리글. 투자사를 '회사' 로 적는다.
ROSTER_HEADER = ["NO", "이름", "담당자", "관심도 (월말기준)", "카톡방 참여여부",
                 "메모 ( 통화내용 / 카톡내용 / 카톡답신 )", "딜소싱 참여 투자사",
                 "선호 투자분야", "라운드 사이즈(투자운영금액)", "휴대폰",
                 "회사", "부서", "직함", "전자 메일 주소"]


def _xlsx(rows, title="명단") -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = title
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _row(no, name, kakao="", memo="", firm="가나벤처스", dept="", email=""):
    return [no, name, "", "", kakao, memo, "", "", "", "010-0000-0000",
            firm, dept, "심사역", email]


@pytest.fixture()
def logged(client, users):
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    return client


def _import(client, rows, **form):
    return client.post(
        "/api/import/contacts",
        files={"file": ("명단.xlsx", _xlsx([ROSTER_HEADER] + rows),
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        data={"dry_run": "false", **form},
    )


# --- 단계 판정 --------------------------------------------------------------

@pytest.mark.parametrize("kakao, memo, invited, expected", [
    ("O", "", "", "connected"),
    ("", "", "완료", "connected"),                      # 딜소개현황 시트는 초대완료여부를 쓴다
    ("X", "딜소싱 네트워크 전화 - 참여안하심 7/9", "", "declined"),
    ("X", "관련업무 안함", "", "declined"),
    ("X", "기존에 연결된 적 없음, 신규연결 진행 7/16", "", "in_progress"),
    ("X", "딜소싱 네트워크 전화 - 부재중 7/9 -> 카톡 공유 완료", "", "in_progress"),
    ("", "", "", "not_started"),
    ("X", "", "", "not_started"),
])
def test_stage_is_read_from_the_sheet(kakao, memo, invited, expected):
    from app.services.sheet_import import connect_stage

    assert connect_stage(kakao, memo, invited=invited) == expected


def test_existing_room_always_means_connected():
    from app.services.sheet_import import connect_stage

    assert connect_stage("X", "참여안하심", has_room=True) == "connected"


# --- 임포트 ----------------------------------------------------------------

def test_company_column_is_recognised(logged, db):
    """명단 시트는 투자사를 '회사' 로 적는다."""
    from app.models import VcContact

    _import(logged, [_row(1, "홍길동", kakao="O", firm="가나벤처스",
                          dept="투자본부", email="hong@example.com")])
    db.expire_all()
    row = db.query(VcContact).filter_by(name="홍길동").first()
    assert row is not None
    assert row.firm == "가나벤처스"
    assert row.department == "투자본부"
    assert row.email == "hong@example.com"
    assert row.channel_email == 1        # 메일 주소가 있으면 메일로도 보낼 수 있다


def test_unconnected_contact_gets_no_room_name(logged, db):
    """방 이름을 지어 주면 발송 대상처럼 보이는데 보낼 방이 없다."""
    from app.models import VcContact

    _import(logged, [
        _row(1, "연결됨", kakao="O"),
        _row(2, "진행중", kakao="X", memo="신규연결 진행", firm="마바벤처스"),
        _row(3, "미착수", firm="사아파트너스"),
    ])
    db.expire_all()
    rows = {c.name: c for c in db.query(VcContact).all()}
    assert rows["연결됨"].kakao_room_name
    assert not rows["진행중"].kakao_room_name
    assert not rows["미착수"].kakao_room_name


def test_stage_never_goes_backwards(logged, db):
    """이미 발송까지 한 담당자를 오래된 명단 때문에 '미착수'로 되돌리면 안 된다."""
    from app.models import VcContact

    _import(logged, [_row(1, "홍길동", kakao="O")])
    db.expire_all()
    before = db.query(VcContact).filter_by(name="홍길동").first()
    room_before = before.kakao_room_name
    assert before.connect_stage == "connected"

    # 같은 사람이 '미연결' 로 적힌 오래된 명단을 나중에 올린다
    _import(logged, [_row(1, "홍길동", kakao="X")])
    db.expire_all()
    after = db.query(VcContact).filter_by(name="홍길동").first()
    assert after.connect_stage == "connected"
    assert after.kakao_room_name == room_before


def test_unlabelled_name_column_is_reported(logged, db):
    """머리글이 빈 이름 칸을 짐작으로 쓰면 안 되고, 썼으면 알려야 한다."""
    from app.models import VcContact

    header = list(ROSTER_HEADER)
    header[1] = ""                       # 명단 시트 하나는 B1 이 비어 있다
    r = logged.post(
        "/api/import/contacts",
        files={"file": ("명단.xlsx",
                        _xlsx([header, _row(1, "홍길동", kakao="O")]),
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        data={"dry_run": "false"},
    )
    assert r.status_code == 200, r.text
    assert any("이름" in note for note in r.json()["notes"])
    db.expire_all()
    assert db.query(VcContact).filter_by(name="홍길동").first() is not None


# --- 발송 대상 --------------------------------------------------------------

def test_send_targets_are_connected_only(logged, db):
    """연결 전 명단이 발송 화면에 섞이면 보낼 방도 없는 사람에게 체크하게 된다."""
    _import(logged, [
        _row(1, "연결됨", kakao="O"),
        _row(2, "진행중", kakao="X", memo="신규연결 진행", firm="마바벤처스"),
    ])
    body = logged.get("/deals").text
    assert "연결됨" in body
    assert "진행중" not in body


# --- 관리자 시야 ------------------------------------------------------------

def test_admin_sees_the_whole_team(client, db, users):
    """관리자는 직접 보내지 않지만 누가 무엇을 맡았는지 알아야 한다."""
    from app.models import VcContact

    db.add_all([
        VcContact(user_id=users["u1"].id, name="내담당", firm="가나벤처스",
                  connect_stage="connected"),
        VcContact(user_id=users["u2"].id, name="남담당", firm="마바벤처스",
                  connect_stage="connected"),
    ])
    users["u2"].role = "admin"
    db.commit()

    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    mine = client.get("/contacts").text
    assert "내담당" in mine and "남담당" not in mine

    client.post("/login", data={"phone": "01000000002", "password": DEMO_PASSWORD})
    admin = client.get("/contacts").text
    assert "내담당" in admin and "남담당" in admin
    assert "담당 팀원" in admin


def test_admin_cannot_send_to_someone_elses_contact(client, db, users):
    """보는 것과 보내는 것은 다르다 — 남의 담당에 실수로 나가면 안 된다."""
    from app.models import IrCompany, VcContact

    company = IrCompany(name="샘플애그", one_liner="소개", revenue_recent=10)
    other = VcContact(user_id=users["u1"].id, name="남담당", firm="가나벤처스",
                      kakao_room_name="남담당 방", connect_stage="connected")
    db.add_all([company, other])
    users["u2"].role = "admin"
    db.commit()

    client.post("/login", data={"phone": "01000000002", "password": DEMO_PASSWORD})
    assert "남담당" not in client.get("/deals").text          # 발송 목록에는 없고
    r = client.post("/api/deals/send", json={                 # 직접 불러도 막힌다
        "company_ids": [company.id], "contact_ids": [other.id],
    })
    assert r.status_code == 404


# --- 명단(시트) 탭 ----------------------------------------------------------
#
# 시트가 나뉘어 있던 데는 이유가 있다. 한 표에 다 쏟으면 시트를 쓰던 사람이
# 자기 명단을 못 찾는다 — 원본 시트와 같은 이름으로 탭을 나눈다.

def test_tabs_use_the_original_sheet_names(logged, db):
    _import(logged, [_row(1, "가나사람", kakao="O")], sheet="")
    logged.post(
        "/api/import/contacts",
        files={"file": ("150명.xlsx", _xlsx([ROSTER_HEADER, _row(2, "신규사람", firm="마바벤처스")]),
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        data={"dry_run": "false"},
    )
    body = logged.get("/contacts").text
    assert "명단.xlsx" in body or "150명.xlsx" in body


def test_tab_filters_to_that_sheet(logged, db):
    from app.models import VcContact

    _import(logged, [_row(1, "가나사람", kakao="O")])
    db.expire_all()
    # 두 번째 명단에만 있는 사람
    row = VcContact(user_id=1, name="딴명단사람", firm="마바벤처스",
                    source_sheet="다른명단", connect_stage="not_started")
    db.add(row)
    db.commit()

    everything = logged.get("/contacts").text
    assert "가나사람" in everything and "딴명단사람" in everything

    only = logged.get("/contacts?sheet=다른명단").text
    assert "딴명단사람" in only
    assert "가나사람" not in only


def test_unknown_tab_falls_back_to_everything(logged, db):
    """탭이 사라져도 빈 화면이 뜨지 않는다."""
    _import(logged, [_row(1, "가나사람", kakao="O")])
    assert "가나사람" in logged.get("/contacts?sheet=없는명단").text


def test_contact_in_two_sheets_shows_in_both(logged, db):
    """한 사람이 여러 명단에 겹쳐 있다 — 한쪽에서만 보이면 안 된다."""
    from app.models import VcContact

    db.add(VcContact(user_id=1, name="겹친사람", firm="가나벤처스",
                     source_sheet="명단A,명단B", connect_stage="connected"))
    db.commit()
    assert "겹친사람" in logged.get("/contacts?sheet=명단A").text
    assert "겹친사람" in logged.get("/contacts?sheet=명단B").text


def test_manually_added_contacts_get_their_own_tab(logged, db):
    """시트에서 오지 않은 담당자도 어딘가에는 있어야 한다."""
    from app.models import VcContact

    db.add(VcContact(user_id=1, name="직접넣은사람", firm="가나벤처스",
                     connect_stage="not_started"))
    db.commit()
    body = logged.get("/contacts").text
    assert "직접 추가" in body
    assert "직접넣은사람" in logged.get("/contacts?sheet=직접 추가").text


# --- 명단 담당 --------------------------------------------------------------
#
# 담당은 사람이 아니라 **명단(시트) 단위**로 정해진다.
# "내 이름으로 된 탭만 내 담당 투자사" — 시트를 나눠 쓰던 방식 그대로다.

def test_import_does_not_steal_an_existing_sheet(logged, db, users):
    """남의 명단을 한 번 올린 것만으로 담당이 넘어오면 안 된다."""
    from app.models import SheetOwner
    from app.services import sheet_owner

    db.add(SheetOwner(label="남의 명단", user_id=users["u2"].id))
    db.commit()

    logged.post(
        "/api/import/contacts",
        files={"file": ("남의 명단.xlsx", _xlsx([ROSTER_HEADER, _row(1, "홍길동", kakao="O")]),
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        data={"dry_run": "false", "sheet": ""},
    )
    db.expire_all()
    assert sheet_owner.owner_map(db)["남의 명단"] == users["u2"].id


def test_only_admin_can_reassign_a_sheet(logged, db, users):
    from app.models import SheetOwner

    db.add(SheetOwner(label="명단A", user_id=None))
    db.commit()
    r = logged.post("/api/contacts/sheets/assign",
                    data={"label": "명단A", "user_id": str(users["u1"].id)})
    assert r.status_code == 403


def test_admin_reassigns_a_sheet(client, db, users):
    from app.models import SheetOwner
    from app.services import sheet_owner

    db.add(SheetOwner(label="명단A", user_id=None))
    users["u2"].role = "admin"
    db.commit()

    client.post("/login", data={"phone": "01000000002", "password": DEMO_PASSWORD})
    r = client.post("/api/contacts/sheets/assign",
                    data={"label": "명단A", "user_id": str(users["u1"].id)},
                    follow_redirects=False)
    assert r.status_code == 303
    db.expire_all()
    assert sheet_owner.owner_map(db)["명단A"] == users["u1"].id
