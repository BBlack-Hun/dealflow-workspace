"""딜 소싱 [엑셀 내려받기] — 지금 탭의 보이는 줄 · 탭마다 한 장.

여기서 못 박는 것.

  ① 칸은 화면 표 그대로 — `참여` · 담당자 · 카톡방 · 메모 · 이 달 `딜 받음` ·
     투자사 관리 현황 연결 · 월간 리마인드 석 달 · 관리자가 붙인 추가 칸
  ② 지금 탭만, 화면이 실어 보낸 줄(`ids` — 검색 · 필터로 보이는 줄)만, 그 차례대로
  ③ `전체` 탭이면 `갈래` 칸이 선다 · [전체 탭]은 탭마다 한 장
  ④ 권한은 화면과 같다 — 팀원 누구나(팀 공용 명단), 투자컨설턴트는 막힌다

이름 · 회사 · 번호는 전부 가상값이다(공개 저장소).
"""
from __future__ import annotations

import io

import pytest

from .conftest import DEMO_PASSWORD

SYNC = "시리즈 A 이상 딜 소싱 참여 심사역"
CEO = "딜 소싱  참여 투자사 대표"


def _login(client, phone="01000000001"):
    client.post("/logout")
    client.post("/login", data={"phone": phone, "password": DEMO_PASSWORD})
    return client


def _book(resp):
    import openpyxl

    assert resp.status_code == 200, resp.text
    book = openpyxl.load_workbook(io.BytesIO(resp.content))
    return {ws.title: [list(r) for r in ws.iter_rows(values_only=True)]
            for ws in book.worksheets}


@pytest.fixture()
def board(client, db, users):
    """시리즈 A(이어진 줄 하나 · 안 이어진 줄 둘) · 대표 갈래(잇지 않음) 하나."""
    from app.models import SheetOwner, SourcingContact, VcContact

    db.add(SheetOwner(label="강민준 투자사", user_id=users["u1"].id, layout="investor"))
    vc = VcContact(user_id=users["u1"].id, name="홍길동", phone="010-1234-5678",
                   source_sheet="강민준 투자사")
    db.add(vc)
    db.flush()
    rows = {
        "hong": SourcingContact(bucket=SYNC, position=1, name="홍길동", phone="010-1234-5678",
                                vc_contact_id=vc.id, participation="참여",
                                assignee_name="강민준", memo="10월 통화",
                                kakao_room_name="홍길동 소싱방", requested_at="2026-10-01"),
        "kim": SourcingContact(bucket=SYNC, position=2, name="김서연", firm="가나벤처스",
                               participation="불참여", requested_at="2026-09-01"),
        "park": SourcingContact(bucket=SYNC, position=3, name="박도윤",
                                participation="참여", requested_at="2026-08-01"),
        "ceo": SourcingContact(bucket=CEO, position=1000, name="최대표", participation="참여"),
    }
    db.add_all(rows.values())
    db.commit()
    _login(client)
    return rows


def test_the_sheet_has_the_columns_the_table_shows(client, db, board):
    from app.routers.sourcing import COLUMNS

    sheet = _book(client.get("/api/sourcing/export.xlsx", params={"tab": SYNC}))
    [(title, rows)] = sheet.items()
    head = rows[0]
    for _field, label, _w, _f in COLUMNS:
        assert label in head, label
    assert "투자사 관리 현황" in head and any(h.endswith("월 딜 받음") for h in head)
    assert sum(1 for h in head if h.endswith("월 리마인드")) == 3
    # 화면처럼 — 이름 뒤에 딜 받음 · 연결, 참여 뒤에 리마인드 석 달
    i = head.index("이름")
    assert head[i + 2] == "투자사 관리 현황"
    assert head[head.index("참여") + 1].endswith("월 리마인드")
    assert "갈래" not in head                     # 한 탭 한 장 — 갈래는 탭 이름이다

    got = {r[i]: dict(zip(head, r)) for r in rows[1:]}
    assert set(got) == {"홍길동", "김서연", "박도윤"}     # 이 탭 줄만
    assert got["홍길동"]["투자사 관리 현황"] == "강민준 투자사 명단"
    assert got["김서연"]["투자사 관리 현황"] == "안 이어짐"
    assert (got["홍길동"]["참여"], got["김서연"]["참여"]) == ("참여", "불참여")
    assert (got["홍길동"]["담당자"], got["홍길동"]["메모"],
            got["홍길동"]["카톡방 이름"]) == ("강민준", "10월 통화", "홍길동 소싱방")
    assert got["홍길동"]["휴대폰"] == "010-1234-5678"     # 번호는 글자로


def test_only_the_rows_the_screen_shows_in_its_order(client, board):
    """검색 · 필터는 화면에서 돈다 — 화면이 보이는 줄 번호를 보이는 차례로 싣는다."""
    ids = f"{board['park'].id},{board['hong'].id}"
    sheet = _book(client.get("/api/sourcing/export.xlsx", params={"tab": SYNC, "ids": ids}))
    [rows] = sheet.values()
    names = [r[rows[0].index("이름")] for r in rows[1:]]
    assert names == ["박도윤", "홍길동"]


def test_ids_from_another_tab_are_ignored(client, board):
    sheet = _book(client.get("/api/sourcing/export.xlsx",
                             params={"tab": SYNC, "ids": str(board["ceo"].id)}))
    [rows] = sheet.values()
    assert rows[1:] == []                        # 화면에 아무도 안 보이면 빈 표


def test_the_all_view_adds_a_bucket_column(client, board):
    sheet = _book(client.get("/api/sourcing/export.xlsx", params={"tab": "all"}))
    [(title, rows)] = sheet.items()
    assert title == "전체"
    assert rows[0][0] == "갈래"
    assert {r[0] for r in rows[1:]} == {SYNC, CEO}
    # 잇지 않는 갈래는 연결 칸이 빈칸 — `안 이어짐` 이 아니다
    ceo = next(dict(zip(rows[0], r)) for r in rows[1:] if r[0] == CEO)
    assert not ceo["투자사 관리 현황"]


def test_every_tab_gets_its_own_sheet(client, board):
    sheet = _book(client.get("/api/sourcing/export.xlsx", params={"every": 1}))
    assert len(sheet) == 2
    by_count = {title: len(rows) - 1 for title, rows in sheet.items()}
    assert sorted(by_count.values()) == [1, 3]
    assert all("갈래" not in rows[0] for rows in sheet.values())


def test_admin_columns_come_along(client, db, board):
    from app.models import CustomColumn, CustomColumnValue

    col = CustomColumn(target="sourcing", name="소싱 비고", kind="memo", position=1,
                       is_hidden=0, after_key="메모")
    db.add(col)
    db.flush()
    db.add(CustomColumnValue(column_id=col.id, row_table="sourcing_contacts",
                             row_id=board["hong"].id, value="다음 달 재연락"))
    db.commit()
    [rows] = _book(client.get("/api/sourcing/export.xlsx", params={"tab": SYNC})).values()
    head = rows[0]
    assert head[head.index("메모") + 1] == "소싱 비고"   # 화면처럼 고른 칸 뒤
    hong = next(dict(zip(head, r)) for r in rows[1:] if r[head.index("이름")] == "홍길동")
    assert hong["소싱 비고"] == "다음 달 재연락"


def test_a_teammate_gets_the_same_rows(client, board):
    """명단은 팀 공용이다 — 다른 팀원도 같은 줄을 받는다."""
    _login(client, "01000000002")
    [rows] = _book(client.get("/api/sourcing/export.xlsx", params={"tab": SYNC})).values()
    assert len(rows) == 4


def test_a_consultant_is_blocked(client, db, board):
    from app.models import User
    from app.services import auth as auth_svc

    db.add(User(id=93, name="컨설턴트시험", phone="01000000093", role="consultant",
                password_hash=auth_svc.hash_password(DEMO_PASSWORD)))
    db.commit()
    _login(client, "01000000093")
    assert client.get("/api/sourcing/export.xlsx", params={"tab": SYNC}).status_code == 403


def test_the_page_has_both_buttons(client, board):
    body = client.get("/sourcing").text
    assert 'data-testid="sourcing-export"' in body
    assert 'data-testid="sourcing-export-all"' in body
