"""`그룹` 칸에 **넣을 수 있는 값** — 표 칸과 [수정] 창이 같은 목록을 쓰는가.

## 무엇을 막는 검사인가

그룹은 A~F 뿐이다(`services/group_name`). 그 판정 하나를 시트 임포트
(`sheet_import.apply_sheet_a`)와 정리 스크립트(`scripts/clean_group_name.py`)가
함께 읽는다 — A~F 로 안 읽히는 값은 다음 업로드에서 memo 로 옮겨지고 그룹 칸은
비워진다.

그런데 「투자사 현황 관리 → 전체 딜소개현황」의 표와 [수정] 창은 배치
(`contact_columns.Layout`)가 세우지 않는다. `contacts.html` 에 **손으로 적혀
있다** — 그래서 배치의 `Column("그룹", …, choices=group_name.CHOICES)` 를 안
지나고, 보기가 빠져도 반복문 검사에 안 걸린다. 실제로 둘 다 빠져 있었다:

    표 칸    `data-type="pick"` 인데 `data-choices` 가 없다
             → `pick` 창에 뜨는 것은 **다른 줄이 이미 쓰고 있는 값**뿐이다
               (`inline_edit.js` 의 `knownValues`)
    수정창   그냥 `<input type="text">` 였다 → 보기가 아예 없다

그래서 같은 칸인데 **어디서 고치느냐에 따라 값이 갈렸다** — `A` 옆에 `A그룹` ·
`a` 가 생긴다. 갈리면 그 사람은

    · 딜 제안 관리의 그룹 칩(`sheet_owner.group_rows` — 글자 그대로 센다)
    · 그룹 발송 대상(`deal_queue.targets` → `sheet_owner.in_group`)

둘 다에서 **다른 그룹**이 된다. 「투자사 관리 현황에서 그룹을 넣었는데 딜 소개
현황의 그룹 필터에 안 잡힌다」가 이 어긋남의 모습이다.

`관심도` 가 바로 앞 판(#197)에서 같은 이유로 `list=` 로 묶였다 — 이 파일은 그
규칙을 `그룹`·`카톡방 참여여부` 로 넓히고, **목록이 한 곳에서만 온다**는 것까지
잰다.

## 왜 `<select>` 가 아닌가

`list=` 는 `<input>` 을 묶지 않아 목록에 없는 말도 그대로 저장된다. 이 칸에는
사람이 자유롭게 적어 둔 옛 값이 들어 있어서, 묶는 순간 창을 여는 것만으로 그
값이 화면에서 사라진다(이 창의 다른 `list=` 칸과 같은 판단).
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.services import contact_columns, group_name

ROOT = Path(__file__).resolve().parent.parent
CONTACTS_HTML = ROOT / "app" / "templates" / "contacts.html"

#: 손으로 적은 [수정] 창을 감싼 조건. 배치가 세우는 창이 `if` 쪽이고,
#: 투자사 명함 배치의 창이 `else` 쪽에 **글자로 적혀 있다**.
_PANEL_IF = "{% if layout.key != 'investor' %}"


def _markup(text: str) -> str:
    """Jinja 주석(`{# … #}`)을 뺀 실제 마크업.

    이 파일이 더한 주석에도 `list=` · `data-choices` 라는 말이 그대로 들어
    있다. 지우지 않고 세면 "이미 묶여 있다" 고 잘못 읽는다.
    """
    return re.sub(r"\{#.*?#\}", "", text, flags=re.S)


@pytest.fixture(scope="module")
def panel() -> str:
    """손으로 적은 [수정] 창 부분(= `{% else %}` 쪽)의 마크업만.

    `if` 쪽 안에도 `{% if %}` 가 여럿이라 **가장 가까운 `{% else %}` 를 잡으면
    안 된다**(`tests/test_edit_panel_labels.py` 와 같은 자를 쓴다).
    """
    text = _markup(CONTACTS_HTML.read_text(encoding="utf-8"))
    at = text.index(_PANEL_IF) + len(_PANEL_IF)
    depth, start, end = 1, None, None
    for tag in re.finditer(r"\{%-?\s*(if|else|elif|endif)\b", text[at:]):
        word = tag.group(1)
        if word == "if":
            depth += 1
        elif word == "endif":
            depth -= 1
            if depth == 0:
                end = at + tag.start()
                break
        elif word == "else" and depth == 1:
            start = at + tag.end()
    assert start is not None and end is not None, "수정 창의 `else` 쪽을 못 찾았습니다"
    return text[start:end]


@pytest.fixture(scope="module")
def body() -> str:
    """투자사 표의 줄 마크업만(머리글 말고 `<tbody>`)."""
    text = _markup(CONTACTS_HTML.read_text(encoding="utf-8"))
    m = re.search(r'id="contacts-table".*?<tbody>(.*?)</tbody>', text, re.S)
    assert m, "투자사 표의 줄을 못 찾았습니다"
    return m.group(1)


def _cell(body: str, field: str) -> str:
    """표의 그 칸 한 덩어리(`<td …>` 또는 `<div …>` 의 여는 표)."""
    m = re.search(r'<(?:td|div)[^>]*data-field="%s"[^>]*>' % re.escape(field), body)
    assert m, f"표에 `{field}` 칸이 없습니다"
    return m.group(0)


def _field(panel: str, field_id: str) -> str:
    """수정창의 그 `<input …>` 한 덩어리."""
    m = re.search(r'<input[^>]*id="%s"[^>]*>' % re.escape(field_id), panel)
    assert m, f"수정창에 `{field_id}` 칸이 없습니다"
    return m.group(0)


def _datalist(panel: str, list_id: str) -> list:
    """그 `<datalist>` 가 세운 보기 값들, **적힌 차례 그대로**."""
    m = re.search(r'<datalist id="%s">(.*?)</datalist>' % re.escape(list_id),
                  panel, re.S)
    assert m, f"수정창에 `{list_id}` 목록이 없습니다"
    return re.findall(r'value="([^"]*)"', m.group(1))


# ── ① 표의 `그룹` 칸이 보기를 세운다 ─────────────────────────────────────────
def test_table_group_cell_has_choices(body):
    cell = _cell(body, "group_name")
    assert 'data-type="pick"' in cell, "그룹은 고르는 칸이어야 한다"
    assert "data-choices=" in cell, (
        "표의 `그룹` 칸에 보기가 없다 — `pick` 창에 뜨는 것은 다른 줄이 이미 쓰고 "
        "있는 값뿐이라, 아무도 안 채운 자리에서는 빈 칸에 그대로 타이핑하게 된다")
    # **필터 키는 그대로다.** 보기를 붙이는 일과 어느 `data-f-*` 를 같이 고치는
    # 일은 다른 물음이다(`inline_edit.js` 의 save).
    assert 'data-filter-key="group"' in cell


# ── ② 수정창의 `그룹` 이 같은 보기로 묶여 있다 ───────────────────────────────
def test_panel_group_is_bound_to_the_same_list(panel):
    field = _field(panel, "f-group_name")
    assert 'list="opts-panel-group_name"' in field, (
        "수정창의 `그룹` 이 자유 글자 칸이다 — 같은 칸을 표에서는 골라 넣고 "
        "창에서는 쳐 넣으면 `A` 와 `A그룹` 으로 갈린다")
    assert _datalist(panel, "opts-panel-group_name")


# ── ③ 목록이 **한 곳**에서만 온다 ────────────────────────────────────────────
#
# 이 파일의 핵심이다. 두 곳이 각자 보기를 들고 있으면 A~F 가 A~G 가 되는 날
# 한쪽만 고쳐지고, 고쳐진 쪽에서 넣은 값이 다른 쪽에서는 없는 값이 된다.
def test_group_choices_come_from_one_place(body, panel):
    cell = _cell(body, "group_name")
    assert 'data-choices="{{ group_choices }}"' in cell, (
        "표 칸이 보기를 **글자로** 들고 있다 — 서버가 넘긴 `group_choices` 하나를 써야 한다")
    assert "{% for v in group_choices.split(',') %}" in panel, (
        "수정창이 보기를 **글자로** 들고 있다 — 표 칸과 같은 값 하나를 써야 한다")
    # 화면 어디에도 A~F 를 손으로 적지 않았다.
    text = _markup(CONTACTS_HTML.read_text(encoding="utf-8"))
    assert group_name.CHOICES not in text, (
        f"`{group_name.CHOICES}` 가 화면에 그대로 적혀 있다 — "
        "판정은 `services/group_name` 한 곳에 둔다")


def test_group_choices_are_the_import_rule(db, logged_in, users):
    """그려진 화면의 보기가 **임포트가 통과시키는 값**과 같은가.

    줄이 있어야 표 칸이 그려진다 — 마크업만 읽으면 `{{ group_choices }}` 가
    실제로 무엇으로 치환되는지는 못 본다.
    """
    from app.models import VcContact

    db.add(VcContact(user_id=users["u1"].id, name="가나다", firm="테스트캐피탈",
                     status="active"))
    db.commit()

    html = logged_in.get("/contacts").text
    m = re.search(r'data-field="group_name"[^>]*data-choices="([^"]*)"', html)
    assert m, "그려진 표에 `그룹` 보기가 없다"
    shown = [v.strip() for v in m.group(1).split(",") if v.strip()]
    assert shown == list(group_name.GROUPS)
    # 수정창도 **같은 값**이다. 글자를 견주는 것이 요점이라 순서까지 본다.
    m = re.search(r'<datalist id="opts-panel-group_name">(.*?)</datalist>', html, re.S)
    assert m, "그려진 수정창에 `그룹` 목록이 없다"
    assert re.findall(r'value="([^"]*)"', m.group(1)) == list(group_name.GROUPS)
    # 그리고 그 보기는 **하나도 빠짐없이** 임포트를 지난다 — 화면에서 고른 값이
    # 다음 업로드에 지워지면 고른 것이 사라진 것과 같다.
    for value in shown:
        assert group_name.letter(value) == value


def test_investor_monthly_layout_uses_the_same_list():
    """배치가 세우는 표(투자사 딜공유)도 같은 목록을 쓴다 — 두 배치가 안 갈린다."""
    columns = {c.key: c for c in contact_columns.INVESTOR_MONTHLY_LAYOUT.head}
    assert columns["group_name"].choices == group_name.CHOICES


# ── ④ `카톡방 참여여부` — 표의 `O,X` 와 창의 보기가 같은 말인가 ──────────────
#
# 짝이 안 맞는 칸(`data-field="kakao_joined"` ↔ 필터 키 `joined`)이라, 표와 창이
# 갈리면 `O`·`o`·`완료` 가 한 칸에 섞인다 — 이 저장소가 이미 데인 자리다.
def test_panel_kakao_joined_matches_the_table(body, panel):
    cell = _cell(body, "kakao_joined")
    m = re.search(r'data-choices="([^"]*)"', cell)
    assert m, "표의 `카톡방 참여여부` 칸에 보기가 없다"
    table_choices = [v.strip() for v in m.group(1).split(",") if v.strip()]

    field = _field(panel, "f-kakao_joined")
    assert 'list="opts-panel-kakao_joined"' in field, (
        "수정창의 `카톡방 참여여부` 가 자유 글자 칸이다 — 표에서는 `O`/`X` 를 "
        "골라 넣는데 창에서는 아무 말이나 쳐 넣게 된다")
    assert _datalist(panel, "opts-panel-kakao_joined") == table_choices, (
        "표 칸과 수정창의 보기가 다른 말이다")


# ── ⑤ 안 건드린 것 ───────────────────────────────────────────────────────────
def test_nothing_is_locked_down(panel):
    """`<select>` 로 묶지 않았다 — 목록에 없는 옛 값이 그대로 살아 있어야 한다."""
    for field_id in ("f-group_name", "f-kakao_joined"):
        assert _field(panel, field_id).startswith("<input")
    # `연결 상태`·`상태` 는 원래 `<select>` 다(고를 값이 앱의 판정 그 자체다).
    assert '<select id="f-connect_stage">' in panel
    assert '<select id="f-status">' in panel
