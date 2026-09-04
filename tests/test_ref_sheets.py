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

# --- 고치기 -----------------------------------------------------------------
#
# 보기만 되던 자료다. 스크립트·성격 정리는 쓰면서 다듬는 것이라, 고치려고
# 구글 시트를 따로 열어야 하면 화면 안으로 들여온 뜻이 없다.

@pytest.fixture()
def table_sheet(seeded, db):
    import json

    from app.models import RefSheet

    row = RefSheet(position=10, kind="table", is_active=1, title="투자사 성격정리",
                   content_json=json.dumps({
                       "columns": ["명칭", "투자대상"],
                       "rows": [["VC", "초기"], ["PE", "성장"]],
                   }, ensure_ascii=False))
    db.add(row)
    db.commit()
    return row


def test_a_text_sheet_can_be_edited(seeded, db):
    import json

    row = _sheet(db, "카톡방 연결 순서")
    r = seeded.post(f"/ref-sheets/{row.id}/body",
                    data={"body": "전화 → 초대 → 확인 → 인사"},
                    follow_redirects=False)
    assert r.status_code == 303
    db.refresh(row)
    assert json.loads(row.content_json)["body"] == "전화 → 초대 → 확인 → 인사"


def test_editing_text_keeps_the_tab_open(seeded, db):
    row = _sheet(db, "카톡방 연결 순서")
    r = seeded.post(f"/ref-sheets/{row.id}/body",
                    data={"body": "고침", "sheet": "투자사 30명"},
                    follow_redirects=False)
    assert f"ref={row.id}" in r.headers["location"]


def test_a_table_cell_can_be_edited(seeded, db, table_sheet):
    import json

    r = seeded.patch(f"/api/ref-sheets/{table_sheet.id}/cell",
                     json={"row": 1, "col": 1, "value": "성장·후기"})
    assert r.status_code == 200
    db.refresh(table_sheet)
    rows = json.loads(table_sheet.content_json)["rows"]
    assert rows == [["VC", "초기"], ["PE", "성장·후기"]]


def test_a_cell_outside_the_table_is_refused(seeded, db, table_sheet):
    """없는 칸에 쓰면 자료가 조용히 늘어난다."""
    assert seeded.patch(f"/api/ref-sheets/{table_sheet.id}/cell",
                        json={"row": 9, "col": 0, "value": "x"}).status_code == 400
    assert seeded.patch(f"/api/ref-sheets/{table_sheet.id}/cell",
                        json={"row": 0, "col": 9, "value": "x"}).status_code == 400


def test_a_text_sheet_is_not_edited_as_a_table(seeded, db):
    row = _sheet(db, "카톡방 연결 순서")
    assert seeded.patch(f"/api/ref-sheets/{row.id}/cell",
                        json={"row": 0, "col": 0, "value": "x"}).status_code == 404


def test_each_cell_knows_its_own_row(seeded, table_sheet):
    """줄 번호를 안쪽 반복에서 가져오면 모든 칸이 같은 줄을 가리킨다."""
    body = seeded.get(f"/contacts?ref={table_sheet.id}").text
    panel = body[body.index('id="ref-table"'):]
    assert 'data-row="0" data-col="0"' in panel
    assert 'data-row="1" data-col="1"' in panel

# --- 머리글 고치기 -----------------------------------------------------------
#
# 표를 화면에서 세울 수 있게 되면서(`/ref-sheets/new`) 머리글이 `칸 1 · 칸 2 …`
# 로 선다. 표는 세울 수 있는데 그 칸을 뭐라 부르는지 정할 길이 없으면 이름 없는
# 표가 그대로 굳는다.
#
# 여기서 보는 것은 **칸 고치기와 같은 길을 지나는가**다 — 같은 화면, 같은 판정,
# 같은 되읽기. 다른 것은 자료에서 손대는 자리(`columns`)뿐이다.

def test_a_header_can_be_renamed(seeded, db, table_sheet):
    import json

    r = seeded.patch(f"/api/ref-sheets/{table_sheet.id}/column",
                     json={"col": 1, "value": "주로 보는 단계"})
    assert r.status_code == 200
    db.refresh(table_sheet)
    assert json.loads(table_sheet.content_json)["columns"] == ["명칭", "주로 보는 단계"]
    # 되읽기 — 저장은 됐는데 화면에 안 뜨면 고친 사람은 실패한 줄 안다.
    assert "주로 보는 단계" in seeded.get(f"/contacts?ref={table_sheet.id}").text


def test_renaming_a_header_leaves_the_rows_alone(seeded, db, table_sheet):
    """자료는 그대로 두고 부르는 이름만 바꾼다 — 탭 이름 바꾸기와 같은 일이다.

    머리글을 고칠 때 그 열이 함께 비워지면 이름을 다듬을 때마다 적어 둔 것이
    날아간다.
    """
    import json

    seeded.patch(f"/api/ref-sheets/{table_sheet.id}/column",
                 json={"col": 0, "value": "이름"})
    db.refresh(table_sheet)
    assert json.loads(table_sheet.content_json)["rows"] == [["VC", "초기"], ["PE", "성장"]]


def test_an_empty_header_is_refused_out_loud(seeded, db, table_sheet):
    """빈 머리글은 표를 그리다 만 것처럼 보이고, 칸이 몇 개인지도 안 남는다.

    조용히 옛 이름으로 되돌리면 고친 사람은 저장된 줄 알고 넘어간다 — 화면이
    되돌리면서 왜 안 됐는지 말할 수 있게 **이유를 실어** 물린다.
    """
    import json

    r = seeded.patch(f"/api/ref-sheets/{table_sheet.id}/column",
                     json={"col": 0, "value": "   "})
    assert r.status_code == 400
    assert "머리글" in r.json()["detail"]
    db.refresh(table_sheet)
    assert json.loads(table_sheet.content_json)["columns"] == ["명칭", "투자대상"]


def test_a_header_outside_the_table_is_refused(seeded, db, table_sheet):
    """없는 머리글에 쓰면 자료가 조용히 늘어난다 — 칸 고치기와 같은 이유다."""
    assert seeded.patch(f"/api/ref-sheets/{table_sheet.id}/column",
                        json={"col": 9, "value": "x"}).status_code == 400
    assert seeded.patch(f"/api/ref-sheets/{table_sheet.id}/column",
                        json={"col": -1, "value": "x"}).status_code == 400


def test_two_headers_may_share_a_name(seeded, db, table_sheet):
    """탭 이름과 달리 머리글은 **자리**가 가리킨다 — 겹쳐도 갈린다.

    `1월`·`1월`, `비고`·`비고` 로 겹쳐 쓰는 표가 실제로 있다. 막으면 그렇게
    생긴 표는 머리글을 아예 못 고치는 표가 된다.
    """
    import json

    r = seeded.patch(f"/api/ref-sheets/{table_sheet.id}/column",
                     json={"col": 1, "value": "명칭"})
    assert r.status_code == 200
    db.refresh(table_sheet)
    assert json.loads(table_sheet.content_json)["columns"] == ["명칭", "명칭"]


def test_a_text_sheet_has_no_headers(seeded, db):
    """줄글에는 고칠 머리글이 없다 — 칸 고치기가 물리는 것과 같은 자리다."""
    row = _sheet(db, "카톡방 연결 순서")
    assert seeded.patch(f"/api/ref-sheets/{row.id}/column",
                        json={"col": 0, "value": "x"}).status_code == 404


def test_a_header_is_clicked_just_like_a_cell(seeded, table_sheet):
    """한 표 안에서 머리글과 칸을 고치는 법이 다르면 쓰는 사람이 헷갈린다.

    그래서 머리글도 **같은 `ref-cell`** 이다. 다른 것은 저장하는 자리를
    가리키는 표시(`ref-head`)와 줄 번호가 없다는 것뿐이다.
    """
    body = seeded.get(f"/contacts?ref={table_sheet.id}").text
    panel = body[body.index('id="ref-table"'):]
    head = panel[:panel.index("</thead>")]

    assert 'class="ref-cell ref-head" data-col="0"' in head
    assert 'data-col="1"' in head
    assert "data-row=" not in head          # 머리글에는 줄이 없다
    assert "머리글" in body                  # 눌러도 되는 자리라고 화면이 말한다


def test_a_table_made_on_screen_can_be_named(seeded, db):
    """`칸 1 · 칸 2 …` 로 세워 놓고 못 고치면 이름 없는 표가 그대로 굳는다."""
    import json

    _make(seeded, title="성격 메모", kind="table", cols="2", rows="2")
    row = _sheet(db, "성격 메모")
    assert json.loads(row.content_json)["columns"] == ["칸 1", "칸 2"]

    assert seeded.patch(f"/api/ref-sheets/{row.id}/column",
                        json={"col": 0, "value": "투자사"}).status_code == 200
    db.refresh(row)
    assert json.loads(row.content_json)["columns"] == ["투자사", "칸 2"]


def test_an_imported_table_can_be_named_too(seeded, db, table_sheet):
    """가져온 표도 같이 고쳐진다.

    `table_sheet` 는 가져오기가 만드는 모양 그대로다(원본 시트 첫 줄이 머리글).
    자료는 그대로 두고 부르는 이름만 바꾸는 것이라, 이 화면이 탭 이름에 대해
    이미 하고 있는 일과 같다 — 가져왔다는 이유로 막을 자리가 아니다.
    """
    import json

    assert table_sheet.kind == "table"
    r = seeded.patch(f"/api/ref-sheets/{table_sheet.id}/column",
                     json={"col": 0, "value": "투자사 이름"})
    assert r.status_code == 200
    db.refresh(table_sheet)
    data = json.loads(table_sheet.content_json)
    assert data["columns"] == ["투자사 이름", "투자대상"]
    assert data["rows"] == [["VC", "초기"], ["PE", "성장"]]


def _table_on(db, page, title="표 자료"):
    import json

    from app.models import RefSheet

    row = RefSheet(position=20, kind="table", is_active=1, page=page, title=title,
                   content_json=json.dumps({"columns": ["칸 1", "칸 2"],
                                            "rows": [["", ""]]},
                                           ensure_ascii=False))
    db.add(row)
    db.commit()
    return row


@pytest.mark.parametrize("page", ["contacts", "consulting", "startup"])
def test_every_screen_that_shows_the_panel_can_edit_headers(seeded, db, users, page):
    """패널을 쓰는 화면 **셋 모두**에서 눌러 고쳐진다.

    화면마다 스크립트를 따로 걸어 두는 곳이라, 한 화면에만 붙이면 나머지는
    "눌러서 고칩니다" 라고 적어 놓고 아무 일도 안 하는 화면이 된다.
    """
    import json

    users["u1"].can_view_consulting = 1
    db.commit()
    row = _table_on(db, page)

    body = seeded.get(f"/{page}?ref={row.id}").text
    assert 'class="ref-cell ref-head"' in body, f"/{page} 에 머리글이 안 서 있다"
    assert "js/ref_edit.js" in body, f"/{page} 에서 눌러도 아무 일이 없다"

    assert seeded.patch(f"/api/ref-sheets/{row.id}/column",
                        json={"col": 1, "value": "메모"}).status_code == 200
    db.refresh(row)
    assert json.loads(row.content_json)["columns"] == ["칸 1", "메모"]
    assert "메모" in seeded.get(f"/{page}?ref={row.id}").text


# --- 어느 화면에 붙는가 ------------------------------------------------------
#
# 참고 탭은 투자사 관리 현황에만 붙었다. 투자컨설턴트 현황에도 스크립트가
# 있는데(미팅 진행 프로세스 · 견적서 발송 톡 …) 붙일 자리가 없었다.

def _consult_sheet(db, title="IRDAY 진행 스크립트"):
    import json

    from app.models import RefSheet

    row = RefSheet(position=1, kind="text", is_active=1, page="consulting",
                   title=title,
                   content_json=json.dumps({"body": "1) 인사 2) 소개"},
                                           ensure_ascii=False))
    db.add(row)
    db.commit()
    return row


def test_consulting_scripts_show_on_the_consulting_page(seeded, db, users):
    users["u1"].can_view_consulting = 1
    db.commit()
    row = _consult_sheet(db)
    body = seeded.get("/consulting").text
    assert "IRDAY 진행 스크립트" in body
    assert f"ref={row.id}" in body


def test_the_two_pages_do_not_mix(seeded, db, users):
    """투자사 스크립트가 투자컨설턴트 탭에 섞이면 어느 화면 것인지 모른다."""
    users["u1"].can_view_consulting = 1
    db.commit()
    _consult_sheet(db)

    consulting = seeded.get("/consulting").text
    assert "카톡방 연결 순서" not in consulting      # 투자사 쪽 자료

    contacts = seeded.get("/contacts").text
    assert "IRDAY 진행 스크립트" not in contacts     # 컨설턴트 쪽 자료


def test_a_consulting_script_can_be_renamed_and_edited(seeded, db, users):
    import json

    users["u1"].can_view_consulting = 1
    db.commit()
    row = _consult_sheet(db)

    seeded.post(f"/ref-sheets/{row.id}/rename", data={"title": "IR DAY 스크립트"},
                follow_redirects=False)
    seeded.post(f"/ref-sheets/{row.id}/body", data={"body": "1) 인사 2) 소개 3) 마무리"},
                follow_redirects=False)
    db.refresh(row)
    assert row.title == "IR DAY 스크립트"
    assert json.loads(row.content_json)["body"].endswith("마무리")


def test_existing_sheets_stayed_on_the_contacts_page(seeded, db):
    """옮기면서 기존 자료가 사라지면 안 된다."""
    row = _sheet(db, "카톡방 연결 순서")
    assert row.page == "contacts"



# --- 만들기 -----------------------------------------------------------------
#
# 참고 자료는 **구글 시트에서 가져와야만** 생겼다. 이름을 바꾸고, 칸을 고치고,
# 지우는 길은 전부 화면에 있는데 첫 자료를 세울 자리만 없어서, 쓰다가 하나가 더
# 필요해지면 스크립트를 돌릴 사람을 찾아야 했다.
#
# **모양은 새로 만들지 않는다.** 표와 글 둘 다 이미 도는 길이라, 여기서 보는
# 것은 만든 자료가 **가져온 자료와 똑같이 굴러가는가**다 — 만들어 놓고 못 고치면
# 만든 뜻이 없다.

def _make(client, page="contacts", **kw):
    data = {"page": page, "title": "새 자료", "kind": "table"}
    data.update(kw)
    return client.post("/ref-sheets/new", data=data, follow_redirects=False)


def test_a_blank_table_is_made_with_the_size_you_asked_for(seeded, db):
    """빈 표가 몇 칸·몇 줄인지 정해야 그릴 수 있다."""
    import json

    r = _make(seeded, title="투자사 성격 메모", kind="table", cols="2", rows="3")
    assert r.status_code == 303
    row = _sheet(db, "투자사 성격 메모")
    data = json.loads(row.content_json)
    assert row.kind == "table" and row.page == "contacts" and row.is_active == 1
    assert len(data["columns"]) == 2
    assert data["rows"] == [["", ""], ["", ""], ["", ""]]


def test_a_new_table_can_actually_be_edited(seeded, db):
    """만들어 놓고 못 고치면 만든 뜻이 없다 — 가져온 표와 같은 길을 지난다."""
    import json

    _make(seeded, title="빈 표", kind="table", cols="2", rows="2")
    row = _sheet(db, "빈 표")

    assert seeded.patch(f"/api/ref-sheets/{row.id}/cell",
                        json={"row": 1, "col": 0, "value": "적었다"}).status_code == 200
    db.refresh(row)
    # 줄을 곱해서 만들면 모든 줄이 같은 리스트 하나를 가리켜, 칸 하나를 고치면
    # 그 열이 통째로 바뀐다.
    assert json.loads(row.content_json)["rows"] == [["", ""], ["적었다", ""]]


def test_a_blank_text_sheet_can_be_made_and_written(seeded, db):
    import json

    r = _make(seeded, title="응대 스크립트", kind="text")
    assert r.status_code == 303
    row = _sheet(db, "응대 스크립트")
    assert row.kind == "text"
    assert json.loads(row.content_json)["body"] == ""

    seeded.post(f"/ref-sheets/{row.id}/body", data={"body": "1) 인사"},
                follow_redirects=False)
    db.refresh(row)
    assert json.loads(row.content_json)["body"] == "1) 인사"


def test_the_new_tab_opens_right_away(seeded, db):
    """만들어 놓고 어디 있는지 찾게 하지 않는다."""
    r = _make(seeded, title="바로 열리나", kind="text", sheet="투자사 30명")
    row = _sheet(db, "바로 열리나")
    assert r.headers["location"].startswith("/contacts?")
    assert f"ref={row.id}" in r.headers["location"]
    assert "sheet=" in r.headers["location"]
    assert "바로 열리나" in seeded.get(f"/contacts?ref={row.id}").text


def test_a_new_tab_goes_to_the_end_of_the_row(seeded, db):
    """가져온 자료 사이에 끼어들면 방금 만든 것을 눈으로 찾아야 한다."""
    _make(seeded, title="맨 뒤", kind="text")
    row = _sheet(db, "맨 뒤")
    assert row.position > 11        # seeded 의 가장 뒤가 11


def test_a_nameless_tab_is_refused_out_loud(seeded, db):
    """이름 없는 탭은 누를 자리가 없어진다. 조용히 되돌아가면 또 누른다."""
    from app.models import RefSheet

    before = db.query(RefSheet).count()
    r = _make(seeded, title="   ", kind="text")
    assert r.status_code == 303
    assert "msg=" in r.headers["location"]
    assert db.query(RefSheet).count() == before


def test_a_name_already_in_use_is_refused(seeded, db):
    """같은 이름이 둘이면 탭 줄에서 갈리지 않는다 — 둘 다 `📄 같은이름`이다."""
    from app.models import RefSheet

    r = _make(seeded, title="카톡방 연결 순서", kind="text")
    assert "msg=" in r.headers["location"]
    assert db.query(RefSheet).filter_by(title="카톡방 연결 순서").count() == 1


def test_a_name_freed_by_deleting_can_be_used_again(seeded, db):
    """지운 자료는 탭에 안 서니 헷갈릴 자리도 없다."""
    row = _sheet(db, "카톡방 연결 순서")
    seeded.post(f"/ref-sheets/{row.id}/delete", follow_redirects=False)

    r = _make(seeded, title="카톡방 연결 순서", kind="text")
    assert "msg=" not in r.headers["location"]
    assert "ref=" in r.headers["location"]


def test_an_unknown_screen_is_refused(seeded, db):
    """어느 화면에도 안 뜨는 자료가 조용히 쌓이면 만든 사람은 사라진 줄 안다."""
    from app.models import RefSheet

    assert _make(seeded, page="없는화면", title="유령").status_code == 404
    assert db.query(RefSheet).filter_by(title="유령").count() == 0


def test_a_silly_size_does_not_get_through(seeded, db):
    """0칸짜리 표는 만들자마자 고칠 칸이 없고, 5000칸짜리는 화면을 덮는다."""
    import json

    _make(seeded, title="이상한 크기", kind="table", cols="0", rows="9999")
    data = json.loads(_sheet(db, "이상한 크기").content_json)
    assert len(data["columns"]) >= 1
    assert 1 <= len(data["rows"]) <= 60


def test_an_empty_size_box_falls_back_instead_of_erroring(seeded, db):
    """칸을 비운 채 눌렀다고 422 화면으로 튕기면 무엇이 잘못됐는지 모른다."""
    import json

    r = _make(seeded, title="빈 칸 수", kind="table", cols="", rows="")
    assert r.status_code == 303
    data = json.loads(_sheet(db, "빈 칸 수").content_json)
    assert len(data["columns"]) >= 1 and len(data["rows"]) >= 1


def test_the_make_button_sits_after_the_last_reference_tab(seeded):
    """브라우저 새 탭 `+` 처럼 참고 자료 무리의 **끝**에 붙는다.

    명단 탭 쪽이나 구분선 앞에 서면 무엇을 더하는 단추인지 자리가 말해 주지
    않는다 — 참고 자료 옆에 있어야 참고 자료를 더한다고 읽힌다.
    """
    body = seeded.get("/contacts").text
    # 좌측 메뉴도 `<nav>` 라 앞쪽에 있다 — 탭 줄이 시작한 **뒤**에서 끝을 찾는다.
    head = body.index('class="sheet-tabs"')
    nav = body[head:body.index("</nav>", head)]

    assert 'action="/ref-sheets/new"' in nav          # 탭 줄 안이다
    assert nav.index("tab-divider") < nav.index("ref-new")   # 구분선 뒤
    # 📄 는 참고 자료 탭에만 붙는다 — 그 **마지막** 것보다 뒤에 서야 한다.
    assert nav.rindex("📄") < nav.index("ref-new-btn")
    # 글자 하나짜리 단추라 **가리키는 말**이 없으면 무엇인지 알 수 없다.
    assert "참고자료 추가" in nav


def test_the_make_button_is_there_before_any_sheet_exists(client, db, users):
    """자료가 하나도 없는 화면에 만들 자리가 없으면 첫 자료를 세울 길이 없다."""
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    body = client.get("/contacts").text
    assert 'action="/ref-sheets/new"' in body


def test_the_make_button_is_on_the_consulting_screen_too(seeded, db, users):
    """지우고 이름 바꾸는 길이 열린 화면이면 세우는 길도 열려 있어야 한다."""
    users["u1"].can_view_consulting = 1
    db.commit()
    body = seeded.get("/consulting").text
    assert 'action="/ref-sheets/new"' in body
    assert 'value="consulting"' in body


def test_a_sheet_made_on_consulting_stays_there(seeded, db, users):
    """만든 자료가 남의 화면에 섞이면 어느 화면 것인지 모른다."""
    users["u1"].can_view_consulting = 1
    db.commit()
    _make(seeded, page="consulting", title="IR 진행 스크립트", kind="text")

    assert "IR 진행 스크립트" in seeded.get("/consulting").text
    assert "IR 진행 스크립트" not in seeded.get("/contacts").text
