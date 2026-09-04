"""표에서 눌러 바로 고치기 — 한 칸만 보내도 저장되는가.

투자컨설턴트 현황에서만 쓰던 조작을 투자사 관리 현황 · IR 기업현황로 넓혔다.
칸 하나를 고칠 때 **다른 값까지 같이 보내야 한다면** 쓸 수 없는 기능이다.
실제로 처음엔 `name` 이 필수라 매출 한 칸을 고치는 데 422 가 났다.
"""
from __future__ import annotations

import pathlib

import pytest

from .conftest import DEMO_PASSWORD


@pytest.fixture()
def logged_in(client, db, users):
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    return client


@pytest.fixture()
def company(db):
    from app.models import IrCompany

    row = IrCompany(name="샘플애그", sector_major="애그테크",
                    one_liner="B2B 농산물 선도거래", revenue_recent=1200)
    db.add(row)
    db.commit()
    return row


@pytest.fixture()
def contact(db, users):
    from app.models import VcContact

    row = VcContact(user_id=users["u1"].id, name="홍길동", title="심사역",
                    firm="가나벤처스", memo="처음 메모")
    db.add(row)
    db.commit()
    return row


# --- IR 기업현황 -----------------------------------------------------------

def test_one_field_is_enough(logged_in, db, company):
    r = logged_in.patch(f"/api/companies/{company.id}",
                        json={"revenue_recent": 3400})
    assert r.status_code == 200, r.text
    db.refresh(company)
    assert company.revenue_recent == 3400
    assert company.name == "샘플애그", "이름을 안 보냈다고 지워지면 안 된다"


def test_zero_is_not_empty(logged_in, db, company):
    """'매출 0' 과 '아직 안 적음'은 다르다."""
    logged_in.patch(f"/api/companies/{company.id}", json={"revenue_recent": 0})
    db.refresh(company)
    assert company.revenue_recent == 0

    logged_in.patch(f"/api/companies/{company.id}", json={"revenue_recent": None})
    db.refresh(company)
    assert company.revenue_recent is None


def test_response_says_whether_it_became_introducible(logged_in, db, company):
    """한 칸을 채우면 '소개 가능'이 바뀔 수 있다. 새로고침해야 보이면 안 된다."""
    body = logged_in.patch(f"/api/companies/{company.id}",
                           json={"one_liner": "고침"}).json()
    assert body["introducible"] is False
    assert "없음" in body["blocked_reason"], "무엇이 모자란지 말해 줘야 채울 수 있다"

    for field, value in [("funding_total", 20), ("raise_target", 700),
                         ("pre_value", 3000), ("competitiveness", "특허 6건"),
                         ("ir_file_name", "샘플_IR.pdf"),
                         ("summary_status", "done")]:
        body = logged_in.patch(f"/api/companies/{company.id}",
                               json={field: value}).json()
    assert body["introducible"] is True, body["blocked_reason"]


def test_creating_still_needs_a_name(logged_in):
    assert logged_in.post("/api/companies", json={"sector_major": "AI"}).status_code == 400


# --- 투자사 관리 현황 ---------------------------------------------------------------

def test_memo_only(logged_in, db, contact):
    r = logged_in.patch(f"/api/contacts/{contact.id}", json={"memo": "고친 메모"})
    assert r.status_code == 200, r.text
    db.refresh(contact)
    assert contact.memo == "고친 메모"
    assert contact.name == "홍길동"


def test_changing_the_room_name_clears_the_check(logged_in, db, contact):
    """방 이름이 바뀌면 이전 확인 결과는 더 이상 근거가 아니다."""
    contact.kakao_room_name = "예전 방"
    contact.room_verified = "verified"
    db.commit()

    logged_in.patch(f"/api/contacts/{contact.id}",
                    json={"kakao_room_name": "새 방 이름"})
    db.refresh(contact)
    assert contact.kakao_room_name == "새 방 이름"
    assert contact.room_verified == "unverified"


def test_cannot_touch_someone_elses(client, db, users, contact):
    client.post("/login", data={"phone": "01000000002", "password": DEMO_PASSWORD})
    assert client.patch(f"/api/contacts/{contact.id}",
                        json={"memo": "남의 것"}).status_code == 404


# --- 화면에 붙어 있는가 ------------------------------------------------------

def test_tables_are_wired(logged_in, company, contact):
    companies = logged_in.get("/companies?tab=db").text
    assert 'data-inline-url="/api/companies"' in companies
    assert 'data-field="revenue_recent" data-type="number"' in companies
    assert "inline_edit.js" in companies

    contacts = logged_in.get("/contacts").text
    assert 'data-inline-url="/api/contacts"' in contacts
    # 메모는 담당자 시트에 없는 칸이라 표에서 뺐다 — [수정] 에서 본다.
    assert 'data-field="sectors"' in contacts
    assert "inline_edit.js" in contacts


def test_long_text_gets_the_floating_editor(logged_in, company, contact):
    """한줄소개는 320px 말줄임 칸이다. 그 안에서 한 줄 입력으로 문장을 쓰면
    앞뒤가 안 보여서 어디를 고치는지 모른 채 타이핑하게 된다."""
    companies = logged_in.get("/companies").text
    assert 'data-field="one_liner" data-type="long"' in companies

    contacts = logged_in.get("/contacts").text
    assert 'data-field="sectors" data-type="long"' in contacts

    js = (pathlib.Path("app/static/js/inline_edit.js")).read_text(encoding="utf-8")
    assert "startLong" in js
    # 표의 가로 스크롤에 잘리면 안 된다 — 화면 좌표로 띄운다
    assert "getBoundingClientRect" in js
    css = (pathlib.Path("app/static/css/app.css")).read_text(encoding="utf-8")
    assert ".cell-pop { position: fixed;" in css


# --- 좁은 칸을 읽고 고칠 수 있게 --------------------------------------------

def test_clamp_never_sits_on_a_td(logged_in, company):
    """`display:-webkit-box` 를 td 에 직접 걸면 그 칸이 테이블 레이아웃에서 빠져
    행이 통째로 어긋난다. 실제로 깨졌다 — 반드시 안쪽 div 에 건다."""
    import re

    html = logged_in.get("/companies").text
    assert not re.search(r'<td[^>]*class="[^"]*clamp2', html), "td 에 clamp 이 걸렸다"
    assert '<div class="cell clamp2"' in html

    rows = re.findall(r'<tr data-id="\d+".*?</tr>', html, re.S)
    heads = len(re.findall(r"<th[ >]", html.split("</thead>")[0]))
    for row in rows:
        assert len(re.findall(r"<td[ >]", row)) == heads, "머리와 셀 개수가 어긋난다"


def test_series_shows_the_name_but_keeps_the_whole_value(logged_in, db):
    """단계 값은 40자가 넘는다 — 괄호 안은 297행에 똑같이 반복되는 설명이다.
    표에는 이름만 보이되, 저장된 값은 그대로 지켜져야 한다."""
    from app.models import IrCompany
    from app.routers.companies import _short

    full = "Pre A, Bridge (누적투자금 5억미만, 년매출액 10억이상)"
    db.add(IrCompany(name="샘플메디", series=full))
    db.commit()
    assert _short(full) == "Pre A, Bridge"
    assert _short(None) == ""
    assert _short("Series A") == "Series A"          # 괄호가 없으면 그대로

    html = logged_in.get("/companies").text
    assert f'data-value="{full}"' in html            # 전체 값은 들고 있다
    assert ">Pre A, Bridge<" in html                 # 보이는 건 이름만
    assert 'data-f-series="Pre A, Bridge"' in html   # 필터 목록도 이름으로


def test_sector_and_series_use_the_pick_editor(logged_in, company):
    """값이 몇 개로 정해져 있는 칸이다. 새로 타이핑하면 '헬스케어' 와
    '헬스 케어' 가 갈라져 필터가 같은 뜻을 두 줄로 센다."""
    html = logged_in.get("/companies").text
    assert 'data-field="sector_major" data-type="pick"' in html
    assert 'data-field="series" data-type="pick"' in html

    js = pathlib.Path("app/static/js/inline_edit.js").read_text(encoding="utf-8")
    assert "startPick" in js
    # 목록은 표에 실제로 있는 값에서 모은다 — 서버 목록은 실제와 어긋난다
    assert "knownValues" in js
    assert "data-value" in js, "보이는 글자와 저장 값이 다른 칸을 다뤄야 한다"


# --- 갇히지 않는가 -----------------------------------------------------------

def test_the_editor_can_never_trap_the_table():
    """숫자 칸을 누르면 표 전체가 먹통이 된 적이 있다.

    `<input type="number">` 에서 `setSelectionRange()` 는 예외를 던진다
    (InvalidStateError — number 는 selection 을 지원하지 않는다). 그 줄이
    blur·Escape 를 붙이기 **전에** 있어서, 던지는 순간 빠져나갈 길이 하나도
    안 붙고 `editing` 이 그 칸에 물린 채 남았다. 결과는 입력 상자에서
    탈출 불가 + 다른 칸 클릭 무시.

    브라우저 없이 클릭을 재현할 수는 없으므로, **구조**를 못 박는다.
    """
    js = pathlib.Path("app/static/js/inline_edit.js").read_text(encoding="utf-8")

    # ① 빠져나갈 길을 먼저 붙인다
    blur_at = js.index('input.addEventListener("blur", finish)')
    focus_at = js.index("input.focus()")
    assert blur_at < focus_at, "focus/커서 이동보다 blur 핸들러가 먼저여야 한다"

    # ② 커서 이동은 되는 타입에서만 — 막는 목록이 아니라 되는 목록으로
    assert "var SELECTABLE = {" in js
    assert "putCaretAtEnd" in js
    assert "if (!multi && !SELECTABLE[input.type]) return;" in js

    # ③ 그래도 터지면 editing 을 놓아 준다
    assert "editing = null;" in js.split("} catch (err) {")[1][:200], \
        "여는 도중 예외가 나면 editing 을 풀어야 한다"


def test_number_cells_do_not_ask_for_a_caret(logged_in, company):
    """숫자 칸은 커서 위치를 건드리지 않는다 — 거기서 터졌다."""
    js = pathlib.Path("app/static/js/inline_edit.js").read_text(encoding="utf-8")
    selectable = js.split("var SELECTABLE = {")[1].split("};")[0]
    for kind in ("number", "date"):
        assert f"{kind}:" not in selectable, f"{kind} 는 selection 을 지원하지 않는다"


# --- 채워야 하는 값은 표에서 보여야 한다 ---------------------------------------

def test_required_fields_are_visible_in_the_table(logged_in, company):
    """`소개 가능` 조건인데 [수정] 을 눌러야만 보이는 칸이 있으면,
    채워졌는지 알 수 없어 결국 297개를 하나씩 열어 봐야 한다.

    Pre Value 가 그랬다. 조건을 새로 추가할 때도 같은 일이 나므로 여기서 잡는다.
    """
    from app.routers.companies import REQUIRED_FIELDS

    # 두 탭을 합쳐서 본다 — 사람은 탭을 오가며 채운다.
    html = (logged_in.get("/companies").text
            + logged_in.get("/companies?tab=db").text)

    # 표에 컬럼으로 나와 있는 것
    shown = {m for m in
             __import__("re").findall(r'data-field="([a-z_]+)"', html)}
    # 컬럼이 아니어도 되는 것 — 이유가 분명한 경우만 여기 적는다
    excused = {
        # 파일명은 값 대신 [있음]/[없음] 배지로 보여 준다 — 이름이 길어 표에
        # 늘어놓을 자리가 없다(짚어 보면 뜨고, 고치는 자리는 [수정] 창이다)
        "ir_file_name",
        # 문장이 길어 한 칸에 안 들어간다. 없으면 '소개 가능' 칸이 이름을 대 준다
        "competitiveness",
    }

    missing = [name for name, _label in REQUIRED_FIELDS
               if name not in shown and name not in excused]
    assert not missing, (
        "소개 가능 조건인데 표에서 안 보이는 칸: " + ", ".join(missing) +
        "\n컬럼으로 넣거나, 넣지 않는 이유를 excused 에 적으세요.")


def test_the_money_columns_can_all_be_typed_into(logged_in, company):
    html = logged_in.get("/companies?tab=db").text
    for field in ("revenue_recent", "funding_total", "raise_target", "pre_value"):
        assert f'data-field="{field}" data-type="number"' in html, field


# --- 금액 단위 ---------------------------------------------------------------
#
# DB 는 백만원으로 쌓여 있다. 표에 그대로 두면 `1,000` 이 10억이라 아무도
# 못 읽고, 딜소개 문구는 이미 억으로 나가서 표와 문구가 서로 다른 숫자를 보였다.

def test_money_columns_show_eok(logged_in, db):
    from app.models import IrCompany

    db.add(IrCompany(name="샘플로지", revenue_recent=1830,   # 18.3억
                     funding_total=1000,                     # 10억
                     pre_value=15000))                       # 150억
    db.commit()

    html = logged_in.get("/companies?tab=db").text
    assert ">18.3<" in html
    assert ">10<" in html
    assert ">150<" in html
    assert "1,830" not in html, "백만원이 그대로 보인다"
    # 숫자만 있으면 천만 원인지 천억인지 알 수 없다
    # 스타트업DB 탭의 금액 칸 — 연도별 매출은 적은 그대로(글자)라 단위를 안 붙인다
    assert html.count('class="th-unit">억<') == 0


def test_editing_in_eok_stores_baekman():
    """사람이 `18.3` 이라고 적으면 1830 으로 저장돼야 한다."""
    js = pathlib.Path("app/static/js/inline_edit.js").read_text(encoding="utf-8")
    assert 'unit === "eok" ? Math.round(n * 100) : n' in js, \
        "억 → 백만원 되돌림이 없다"
    assert 'data-unit' in js


def test_the_money_cells_are_marked_as_eok(logged_in, company):
    html = logged_in.get("/companies?tab=db").text
    for field in ("revenue_recent", "funding_total", "raise_target", "pre_value"):
        assert f'data-field="{field}" data-type="number" data-unit="eok"' in html, field


def test_the_version_is_at_the_top(logged_in):
    """맨 아래에 두면 스크롤해야 보여서, 정작 물어볼 때 아무도 못 찾는다."""
    from app import version

    html = logged_in.get("/companies").text
    assert "app-foot" not in html
    brand = html.index('class="brand"')
    menu = html.index('class="menu"')
    ver = html.index(f"v{version.VERSION}")
    assert brand < ver < menu, "버전이 상단 브랜드 옆에 있어야 한다"


def test_the_edit_modal_is_in_eok_too(logged_in, company):
    """표는 억인데 수정 창만 백만원이면 같은 값이 100배 차이로 보인다."""
    html = logged_in.get("/companies").text
    assert "단위: 억" in html
    assert "백만원" not in html
    # 18.3 같은 값을 넣을 수 있어야 한다
    for field in ("revenue_recent", "funding_total", "raise_target", "pre_value"):
        assert f'step="0.1" id="f-{field}"' in html, field

    js = pathlib.Path("app/static/js/companies.js").read_text(encoding="utf-8")
    assert "EOK_FIELDS" in js
    assert "Math.round(n * 100)" in js, "억 → 백만원 되돌림이 없다"


def test_the_excel_matches_the_screen(logged_in, db):
    """표와 엑셀을 나란히 놓고 보는 사람에게 100배 차이가 나면 안 된다."""
    import io

    import openpyxl

    from app.models import IrCompany

    db.add(IrCompany(name="샘플로지", revenue_recent=1830, pre_value=15000))
    db.commit()

    book = openpyxl.load_workbook(
        io.BytesIO(logged_in.get("/api/export/companies.xlsx").content))
    sheet = book.active
    head = [c.value for c in sheet[1]]
    assert "최근매출(억)" in head and "Pre Value(억)" in head

    col = {name: i for i, name in enumerate(head)}
    row = next(r for r in sheet.iter_rows(min_row=2, values_only=True)
               if r[0] == "샘플로지")
    assert row[col["최근매출(억)"]] == 18.3
    assert row[col["Pre Value(억)"]] == 150
    # 엑셀에서 계산할 수 있게 문자열이 아니라 숫자여야 한다
    assert isinstance(row[col["최근매출(억)"]], (int, float))


# --- 시트의 하단 탭 -----------------------------------------------------------

def test_two_tabs_match_the_sheet(logged_in, company):
    """시트를 쓰던 사람이 같은 자리에서 같은 것을 찾을 수 있어야 한다."""
    status = logged_in.get("/companies").text
    for col in ("사업분야 대분류", "소분류", "기업구분", "한줄 소개",
                "담당자", "계약여부", "핵심/TOP Deal"):
        assert col in status, f"IR 기업현황 탭에 '{col}' 이 없다"

    db_tab = logged_in.get("/companies?tab=db").text
    for col in ("대표자", "연락처", "이메일", "22년 매출", "25년 매출",
                "누적투자금액", "투자유치희망금액", "Pre Value",
                "특이사항 (장점)", "설립년도", "기보, 신보, 중진공"):
        assert col in db_tab, f"스타트업DB 탭에 '{col}' 이 없다"


def test_ir_column_stays_at_the_end_of_both(logged_in, company):
    """IR 자료는 요청이 왔을 때 바로 꺼내 쓰는 칸이다 — 어느 탭에서도 맨 끝."""
    import re

    for path in ("/companies", "/companies?tab=db"):
        head = logged_in.get(path).text.split("</thead>")[0]
        cols = [re.sub(r"<[^>]+>", "", m).strip()
                for m in re.findall(r"<th(?:\s[^>]*)?>(.*?)</th>", head, re.S)]
        assert cols[-1] == "", f"{path}: 마지막은 수정 버튼 칸이어야 한다"
        assert "IR 자료" in cols[-2], f"{path}: IR 자료가 맨 끝이 아니다 — {cols[-2]!r}"


def test_both_tabs_are_the_same_records(logged_in, db):
    """두 탭은 같은 기업의 두 가지 보기다. 한쪽에 넣으면 다른 쪽이 따라온다 —
    맞춰 주는 코드가 따로 있으면 반드시 어긋난다."""
    from app.models import IrCompany

    row = IrCompany(name="샘플로지", sector_major="물류")
    db.add(row)
    db.commit()

    logged_in.patch(f"/api/companies/{row.id}",
                    json={"contact_name": "홍길동", "sector_major": "물류테크"})

    # 스타트업DB 에서 넣은 대표자·사업분야가
    assert "홍길동" in logged_in.get("/companies?tab=db").text
    # IR 기업현황에도 그대로 보인다
    assert "물류테크" in logged_in.get("/companies").text


def test_yearly_revenue_is_kept_as_typed(logged_in, db):
    """원본에 `8.2억`·`1,224백만원`·`150억 ~ 200억` 이 섞여 있다.
    숫자로 바꾸면 100배가 틀어진 채 딜소개 문구에 실려 나간다."""
    from app.models import IrCompany

    row = IrCompany(name="샘플메디")
    db.add(row)
    db.commit()

    logged_in.patch(f"/api/companies/{row.id}", json={
        "revenue_2023": "1,224백만원", "revenue_2024": "8.2억",
        "revenue_2025": "150억 ~ 200억"})
    db.refresh(row)
    assert row.revenue_2023 == "1,224백만원"
    assert row.revenue_2025 == "150억 ~ 200억"

    html = logged_in.get("/companies?tab=db").text
    assert "1,224백만원" in html and "150억 ~ 200억" in html


def test_at_most_one_column_flexes(logged_in, company):
    """`table-layout: fixed` 에서 폭을 안 준 칸이 둘 이상이면 남는 자리를 나눠
    갖다가 **둘 다 짜부라진다.** 실제로 스타트업DB 의 사업분야 칸이 사라졌다.

    남는 자리를 먹는 칸은 표마다 하나여야 한다.
    """
    import re

    for path in ("/companies", "/companies?tab=db"):
        head = logged_in.get(path).text.split("</thead>")[0]
        flexible = []
        for attrs, label in re.findall(r"<th(\s[^>]*)?>(.*?)</th>", head, re.S):
            name = re.sub(r"<[^>]+>", "", label).strip()
            if not name:
                continue        # 수정 버튼 칸
            if not re.search(r"width:\s*\d+(px|%)", attrs or ""):
                flexible.append(name)
        assert len(flexible) <= 1, \
            f"{path}: 폭 없는 칸이 여럿 — {flexible} (서로 자리를 뺏다 사라진다)"


def test_the_wide_table_scrolls_instead_of_squeezing(logged_in, company):
    html = logged_in.get("/companies?tab=db").text
    assert "table-wrap wide" in html
    css = pathlib.Path("app/static/css/app.css").read_text(encoding="utf-8")
    import re

    # 가로만이 아니라 **세로도** 자른다 — 표가 페이지만큼 길어지면 가로
    # 스크롤바가 문서 맨 아래로 밀려서, 밀려면 끝까지 내려갔다 와야 한다.
    rule = re.search(r"\.table-wrap\.wide\s*\{([^}]*)\}", css)
    assert rule and re.search(r"overflow:\s*auto", rule.group(1))
    assert "max-height" in rule.group(1)
    assert "min-width: 2030px" in css
    # 세로로 밀 때 컬럼 이름이 사라지면 어느 칸인지 알 수 없다
    assert re.search(r"\.table-wrap\.wide thead th\s*\{[^}]*position:\s*sticky", css)


def test_top_deal_is_a_choice_not_a_switch(logged_in, db):
    """시트에 `핵심`(13) · `TOP`(11) · 둘 다(2) 가 들어 있다.
    켜짐/꺼짐 하나로는 어느 쪽인지 알 수 없다."""
    from app.models import IrCompany

    row = IrCompany(name="샘플로지")
    db.add(row)
    db.commit()

    logged_in.patch(f"/api/companies/{row.id}", json={"top_deal_kind": "TOP"})
    db.refresh(row)
    assert row.top_deal_kind == "TOP"
    # 골라 넣으면 '추천 딜' 도 함께 켜진다 — 따로 켜게 하면 한쪽만 켜 둔 채 잊는다
    assert row.is_top_deal == 1

    logged_in.patch(f"/api/companies/{row.id}", json={"top_deal_kind": ""})
    db.refresh(row)
    assert row.top_deal_kind is None and row.is_top_deal == 0

    html = logged_in.get("/companies").text
    assert 'data-field="top_deal_kind" data-type="pick"' in html


def test_contract_has_the_five_states(logged_in, company):
    """완료/진행중/없음 셋으로 뭉치면 '무료'와 '유료'가 같은 칸에 들어가고,
    '딜소개 불가'(더 이상 소개하면 안 되는 기업)가 '없음'에 섞여 사고가 난다."""
    from app.routers.companies import CONTRACT_LABELS, contract_key

    assert set(CONTRACT_LABELS.values()) == {
        "미계약", "무료계약완료", "유료계약완료", "계약검토중", "딜소개 불가"}
    # 예전 값도 그대로 읽힌다
    assert contract_key("yes") == "paid"
    assert contract_key("no") == "none"
    assert contract_key(None) == "none"

    html = logged_in.get("/companies").text
    assert "유료계약완료" in html and "딜소개 불가" in html


def test_top_deal_order_does_not_split_the_filter():
    """`핵심, TOP` 과 `TOP, 핵심` 은 같은 뜻인데 글자가 달라 필터가 두 줄로 셌다."""
    from app.routers.companies import top_deal_kind

    assert top_deal_kind("TOP, 핵심") == "핵심, TOP"
    assert top_deal_kind("핵심, TOP") == "핵심, TOP"
    assert top_deal_kind("핵심") == "핵심"
    assert top_deal_kind("TOP") == "TOP"
    assert top_deal_kind("") is None and top_deal_kind(None) is None
    # 모르는 말은 지우지 않는다 — 사람이 적은 것을 임의로 버리면 안 된다
    assert top_deal_kind("특별관리") == "특별관리"


def test_saving_either_order_lands_on_one(logged_in, db):
    from app.models import IrCompany

    row = IrCompany(name="샘플로지")
    db.add(row)
    db.commit()

    logged_in.patch(f"/api/companies/{row.id}", json={"top_deal_kind": "TOP, 핵심"})
    db.refresh(row)
    assert row.top_deal_kind == "핵심, TOP"


def test_no_filter_points_at_a_column_that_is_gone(logged_in, company):
    """`소개 가능` 컬럼을 뺐다. 그 값으로 보내는 링크·칩은 아무것도 못 거른다."""
    import re

    for path in ("/companies", "/companies?tab=db", "/"):
        body = logged_in.get(path).text
        assert "ready=" not in body, f"{path}: 없어진 컬럼으로 거르려 한다"

    # 칩이 거는 값은 실제로 표에 있는 값이어야 한다
    body = logged_in.get("/companies").text
    for preset in re.findall(r'data-preset="([^"]+)"', body):
        key = preset.split("=")[0]
        assert f'data-filters="{key}:' in body or f"|{key}:" in body, \
            f"'{key}' 필터가 표에 없다"


# --- 딜소개 불가 ---------------------------------------------------------------

def test_blocked_companies_never_reach_the_send_screen(logged_in, db):
    """`딜소개 불가` 는 "내용이 부족함" 과 다르다 — 그건 채우면 되지만
    이건 **보내면 안 되는 곳**이라, 목록에 있는 것만으로 실수로 고른다."""
    from app.models import IrCompany

    ok = IrCompany(name="보내도되는곳", sector_major="AI", contract_status="paid")
    blocked = IrCompany(name="보내면안되는곳", sector_major="AI",
                        contract_status="blocked")
    db.add_all([ok, blocked])
    db.commit()

    deals = logged_in.get("/deals").text
    assert "보내도되는곳" in deals
    assert "보내면안되는곳" not in deals, "불가 기업이 발송 화면에 떴다"


def test_blocked_companies_stay_visible_in_the_list(logged_in, db):
    """목록에서까지 지우면 '왜 없지' 가 된다 — 남기되 눈에 띄게 한다."""
    from app.models import IrCompany

    db.add(IrCompany(name="보내면안되는곳", sector_major="AI",
                     contract_status="blocked"))
    db.commit()

    html = logged_in.get("/companies").text
    assert "보내면안되는곳" in html
    assert "blocked-row" in html
    assert "딜소개 불가" in html


def test_old_contract_values_are_not_treated_as_blocked(logged_in, db):
    """예전 값(yes/pending/no)이 실수로 막히면 멀쩡한 기업이 사라진다."""
    from app.models import IrCompany
    from app.routers.companies import BLOCKED_CONTRACT, contract_key

    for old in ("yes", "pending", "no", "", None):
        assert contract_key(old) != BLOCKED_CONTRACT

    db.add(IrCompany(name="예전값기업", sector_major="AI", contract_status="yes"))
    db.commit()
    assert "예전값기업" in logged_in.get("/deals").text
