"""참고 탭 — 투자사 관리 현황 옆에 붙는 스크립트·가이드 자료.

명단 탭과 성격이 다르다. 매번 구글 시트를 따로 열어 보던 자료를 화면 안으로
들여온 것이라, **쓰면서 추려 가는 것**이 전제다: 안 쓰는 탭은 감추고, 부르는
이름은 바꿀 수 있어야 한다. 이름이 원본 시트 탭 이름 그대로라 길다.
"""
from __future__ import annotations

import pytest

from .conftest import DEMO_PASSWORD


@pytest.fixture()
def seeded(client, db, users):
    from app.models import RefSheet

    db.add_all([
        RefSheet(position=5, kind="text", is_active=1,
                 title="40개사 스타트업 매월 1회 리마인드 카톡 가이드",
                 content_json='{"body": "달마다 한 번 안부를 묻는다."}'),
        RefSheet(position=11, kind="text", is_active=1,
                 title="카톡방 연결 순서",
                 content_json='{"body": "전화 → 초대 → 확인"}'),
        RefSheet(position=1, kind="text", is_active=1,
                 title="미팅완료 투자사 주간 월간 업무 보고",
                 content_json='{"body": "쓰지 않는 자료"}'),
    ])
    db.commit()
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    return client


def _sheet(db, title):
    from app.models import RefSheet

    return db.query(RefSheet).filter_by(title=title).first()


def test_active_tabs_show_up(seeded):
    body = seeded.get("/contacts").text
    assert "40개사 스타트업 매월 1회 리마인드 카톡 가이드" in body
    assert "카톡방 연결 순서" in body


def test_the_name_can_be_changed(seeded, db):
    """원본 시트 탭 이름 그대로라 길다 — 무엇을 여는 탭인지 한눈에 안 들어온다."""
    row = _sheet(db, "40개사 스타트업 매월 1회 리마인드 카톡 가이드")

    r = seeded.post(f"/ref-sheets/{row.id}/rename",
                    data={"title": "40개사 리마인드"}, follow_redirects=False)
    assert r.status_code == 303
    db.refresh(row)
    assert row.title == "40개사 리마인드"
    assert "40개사 리마인드" in seeded.get("/contacts").text


def test_renaming_keeps_the_content(seeded, db):
    """부르는 이름만 바꾼다 — 자료가 따라 바뀌면 이름을 못 바꾼다."""
    row = _sheet(db, "카톡방 연결 순서")
    seeded.post(f"/ref-sheets/{row.id}/rename", data={"title": "연결 순서"},
                follow_redirects=False)
    db.refresh(row)
    assert "전화 → 초대 → 확인" in row.content_json
    assert row.position == 11 and row.kind == "text"


def test_an_empty_name_is_refused(seeded, db):
    """이름 없는 탭은 누를 자리가 없어진다."""
    row = _sheet(db, "카톡방 연결 순서")
    seeded.post(f"/ref-sheets/{row.id}/rename", data={"title": "   "},
                follow_redirects=False)
    db.refresh(row)
    assert row.title == "카톡방 연결 순서"


def test_rename_comes_back_to_the_same_tab(seeded, db):
    """이름 하나 바꾸고 명단 맨 앞으로 튕기면 보던 자리를 다시 찾아야 한다."""
    row = _sheet(db, "카톡방 연결 순서")
    r = seeded.post(f"/ref-sheets/{row.id}/rename",
                    data={"title": "연결 순서", "sheet": "투자사 30명"},
                    follow_redirects=False)
    assert f"ref={row.id}" in r.headers["location"]
    assert "sheet=" in r.headers["location"]


def test_a_hidden_tab_disappears_but_survives(seeded, db):
    """안 쓰는 탭이 남아 있으면 자리만 차지한다. 그렇다고 지워 버리면 못 되살린다."""
    row = _sheet(db, "미팅완료 투자사 주간 월간 업무 보고")
    seeded.post(f"/ref-sheets/{row.id}/delete", follow_redirects=False)
    db.refresh(row)

    assert row.is_active == 0
    assert "쓰지 않는 자료" in row.content_json   # 자료는 남아 있다
    assert "미팅완료 투자사 주간 월간 업무 보고" not in seeded.get("/contacts").text


def test_the_rename_form_is_on_the_open_panel(seeded, db):
    """따로 화면을 열게 하면 이름 하나 바꾸려고 두 번 이동한다."""
    row = _sheet(db, "카톡방 연결 순서")
    body = seeded.get(f"/contacts?ref={row.id}").text
    assert f'action="/ref-sheets/{row.id}/rename"' in body
    assert 'name="title"' in body
