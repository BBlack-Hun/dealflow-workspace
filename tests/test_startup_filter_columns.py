"""스타트업 표에 **분야 둘 · 기업구분 · IR Deck** 을 세우고 머리글 필터를 단다.

네 칸(`사업분야 대분류` · `소분류` · `기업구분` · `IR Deck 유무`)은 한동안
수정창에서만 보는 칸(`STARTUP_LAYOUT.extra`, `in_table=False`)이었다. 값은 들어
있는데 **이 값으로 거를 수가 없었다** — 머리글 필터는 자기 칸 머리글에만 서므로
(`contact_columns.header_filters`) 표에 안 선 칸은 필터를 질 자리가 없다.

이번 일은 그 넷을 표로 올리는 것뿐이고, 필터는 **저절로** 붙어야 한다(넷 다
`pick` 이라 `Column.filterable` 이 참이다). 그래서 여기서 재는 것도 "필터를
붙였나" 가 아니라 **판정 하나가 화면 끝까지 이어지는가**다:

1. **표에 선다** — 배치(`table_columns`)와 그려진 화면 둘 다에서.
2. **자리** — `기업명` 바로 뒤, 넷이 붙어서. IR 기업 현황 표가 이미 그
   차례이고(`NO`·`기업명`·`대분류`·`소분류`·`투자라운드`) 원본 시트도 그렇다.
   그 뒤의 차례(성함·연락처·이메일 → IR 미팅 제공일자 → ①② → 계약 세 칸 →
   수정한 날짜 → 월별)는 한 칸도 안 바뀐다.
3. **필터가 붙는다** — 머리글 선언(`data-filters`)과 행이 싣는 값(`data-f-*`)이
   **같은 목록 하나**에서 나와 짝이 맞는가. 보기를 안 적은 셋도 붙는가.
4. **폭** — 필터를 건 뒤의 머리글(`… (1) ▾`)이 한 줄에 들어가는가, 표 폭은
   칸 폭의 합 그대로인가.
5. **다른 자리에 부작용이 없다** — 수정창·엑셀에 칸이 **두 번** 서지 않고(한
   칸이 `head` 와 `extra` 에 같이 있으면 그렇게 된다), 저장 자리가 그대로이고,
   투자사 쪽 배치는 머리글도 필터도 안 바뀐다.

이름·회사·번호는 전부 지어낸 값이다 — 저장소가 공개다.
"""
from __future__ import annotations

import io as _io
import re
from urllib.parse import quote

import pytest

from .conftest import DEMO_PASSWORD
from .test_ui_layout import _text_px

LIST = "샘플 스타트업(9)"
OTHER = "샘플 투자사 20"
DEAL = "샘플 딜공유 20"

# 이번에 표로 올린 넷. **차례가 곧 요청의 절반**이라 여기 적는다.
COLUMNS = ["대분류", "소분류", "투자라운드", "IR 자료 유무"]
KEYS = ["sector_major", "sector_minor", "company_kind", "ir_deck"]
# 넷의 폭. 필터를 건 뒤의 머리글(`… (1) ▾`)에 몇 px 을 얹은 값이다 —
# 왜 그 값인지는 `contact_columns.STARTUP_LAYOUT` 의 그 자리 주석에 있다.
WIDTHS = [140, 100, 120, 130]

# 머리글 필터 단추는 고른 수가 붙어 `라벨 (1) ▾` 로 선다. 그 상태까지 잰다
# (`tests/test_startup_tab.py` 의 `머리글은_필터_단추까지_한_줄에_들어간다` 와 같은 자).
_FILTER_SUFFIX = " (1) ▾"
_PAD = 18          # td/th 좌우 여백
_BUTTON = 14       # 필터 단추의 테두리·여백


def _month() -> int:
    from app import clock

    return clock.today().month


def _url(sheet: str = LIST) -> str:
    from app.services import contact_columns as cc

    return f"/{cc.page_of(cc.STARTUP)}?sheet={quote(sheet)}"


def _thead_cells(html: str) -> list:
    m = re.search(r"<thead>(.*?)</thead>", html, re.S)
    assert m, "표 머리글을 찾지 못했습니다"
    return re.findall(r"<th\b([^>]*)>(.*?)</th>", m.group(1), re.S)


def _flat(cell_html: str) -> str:
    frag = re.sub(r'<div class="th-filters">\s*</div>', "", cell_html, flags=re.S)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", frag)).strip()


def _thead(html: str, ir: bool = True) -> list:
    # `ir=False` — 이어진 IR 기업의 읽기 전용 칸(#85 · `ir-ro`)은 이 명단의 칸이 아니라
    # 뺀다. 그 칸의 자리는 `tests/test_ir_readonly_cols.py` 가 지킨다.
    return [_flat(cell) for attrs, cell in _thead_cells(html) if ir or "ir-ro" not in attrs]


def _filters(html: str) -> dict:
    """머리글 이름 → 그 머리글이 선언한 `키:라벨` 들."""
    out = {}
    for attrs, cell in _thead_cells(html):
        m = re.search(r'data-filters="([^"]*)"', attrs)
        out[_flat(cell)] = m.group(1).split("|") if m else []
    return out


def _rows(html: str) -> list:
    """(행 여는 태그, 행 몸통) 짝."""
    return re.findall(r'(<tr class="data-row[^"]*"[^>]*>)(.*?)</tr>', html, re.S)


# ── 밑자리 ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def sheets(client, db, users):
    """스타트업 명단 하나(세 줄) + 투자사 명함 명단 하나.

    세 줄의 분야·구분 값을 **일부러 갈라 둔다** — 필터 목록에 값이 모이는지,
    보기를 안 적은 칸에서도 고를 거리가 생기는지를 보려면 줄마다 값이 달라야
    한다. 한 줄은 비워 둔다(아직 안 적은 기업이 흔하다).
    """
    from app.models import ContactColumn, SheetOwner, VcContact
    from app.services import contact_columns as cc

    u1 = users["u1"]
    db.add_all([
        SheetOwner(label=LIST, user_id=u1.id, layout=cc.STARTUP, is_hidden=0),
        SheetOwner(label=OTHER, user_id=u1.id, layout=cc.INVESTOR, is_hidden=0),
    ])
    for pos, what in enumerate(("리마인드 문자", "리마인드 TEL", "카톡 연결")):
        db.add(ContactColumn(sheet=LIST, label=f"{_month()}월 {what}", position=pos))
    values = [
        {"sector_major": "에듀테크", "sector_minor": "학습 플랫폼",
         "company_kind": "Seed", "ir_deck": "O"},
        {"sector_major": "헬스케어", "sector_minor": "디지털헬스",
         "company_kind": "Pre-A", "ir_deck": "X"},
        {},
    ]
    for i, notes in enumerate(values, start=1):
        db.add(VcContact(user_id=u1.id, source_sheet=LIST, name=f"김샘플{i}",
                         firm=f"샘플기업{i}", phone=f"0100000010{i}",
                         notes=cc.dump_notes(notes)))
    db.add(VcContact(user_id=u1.id, source_sheet=OTHER, name="박투자1",
                     firm="가나다벤처스", phone="01000000201"))
    db.commit()
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    return client


# ── 1. 표에 선다 ────────────────────────────────────────────────────────────

def test_네_칸이_배치의_표_칸에_든다(db):
    """화면이 아니라 **배치**가 정한다 — 표·필터·수정창·엑셀이 이 목록을 읽는다."""
    from app.services import contact_columns as cc

    columns = cc.table_columns(cc.STARTUP_LAYOUT, [])
    by_label = {c.label: c for c in columns}
    for label, key in zip(COLUMNS, KEYS):
        assert label in by_label, f"`{label}` 이 표 칸에 없습니다"
        column = by_label[label]
        assert column.key == key, f"`{label}` 의 저장 자리가 바뀌었습니다: {column.key}"
        assert column.source == "note", "notes 에 담던 값입니다 — 갈래가 바뀌었습니다"
        assert column.in_table is True


def test_네_칸이_그려진_표에_선다(sheets):
    """배치에만 있고 화면에 안 그려지면 아무 소용이 없다 — **그려서** 본다."""
    heads = _thead(sheets.get(_url()).text)
    missing = [label for label in COLUMNS if label not in heads]
    assert not missing, f"표 머리글에 없습니다: {missing}\n  화면 {heads}"


def test_머리글_수와_데이터_칸_수가_같다(sheets):
    """머리글만 네 개 늘고 칸이 안 늘면 **그 뒤가 전부 네 칸씩 밀린다.**"""
    html = sheets.get(_url()).text
    heads = len(_thead(html))
    rows = _rows(html)
    assert rows, "줄이 없어 잴 수가 없습니다"
    for _open, body in rows:
        assert len(re.findall(r"<td\b", body)) == heads


def test_값이_칸에_보이고_표에서_눌러_고칠_수_있다(sheets):
    """`data-note` — 표에서 고치면 `notes` 묶음으로 간다(`inline_edit.js`)."""
    html = sheets.get(_url()).text
    for key in KEYS:
        assert re.search(rf'data-field="{key}" data-note data-type="pick"', html), (
            f"`{key}` 칸이 눌러 고르는 칸으로 안 섰습니다")
    for value in ("에듀테크", "학습 플랫폼", "Seed", "헬스케어"):
        assert f">{value}</div>" in html, f"`{value}` 가 표 칸에 안 보입니다"


# ── 2. 자리 ─────────────────────────────────────────────────────────────────

def test_기업명_바로_뒤에_넷이_붙어_선다(sheets):
    """IR 기업 현황 표와 같은 차례 — 왼쪽 무리가 "이 기업이 무엇인가" 다."""
    heads = _thead(sheets.get(_url()).text)
    at = heads.index("기업명")
    assert heads[at + 1:at + 1 + len(COLUMNS)] == COLUMNS, (
        f"`기업명` 바로 뒤에 넷이 차례대로 붙어 있지 않습니다: {heads}")
    # 그다음은 한 사람에게 닿는 묶음이다 — 사이에 안 끼운다.
    assert heads[at + 1 + len(COLUMNS):at + 4 + len(COLUMNS)] == \
        ["대표자명", "연락처", "이메일"], heads


def test_뒤따르는_차례는_한_칸도_안_바뀐다(sheets, db):
    """넷을 앞에 끼웠다고 **그 뒤의 차례**가 흔들리면 안 된다.

    `이메일` 바로 뒤는 사용자가 `IR 미팅 제공일자` 로 못 박은 자리고, 그 뒤는
    일이 진행되는 차례(①② → 계약 세 칸)다. `수정한 날짜` 는 `head` 의 끝이라
    월별 묶음 바로 앞이다(`tests/test_startup_ir_meeting_date.py` ·
    `tests/test_startup_updated_at.py` 가 각자 그 자리를 지킨다 — 여기서는
    넷이 들어온 뒤에도 그 차례가 통째로 이어지는지만 본다).
    """
    from app.services import contact_columns as cc

    heads = _thead(sheets.get(_url()).text, ir=False)
    after = ["대표자명", "연락처", "이메일", "미팅제공일자",
             "투자유치 상태", "당사 협업 상태",
             "견적서 첨부 여부", "계약여부", "계약서 수신 여부", "수정한 날짜"]
    at = heads.index(after[0])
    assert heads[at:at + len(after)] == after, heads
    first_month = cc.month_label(cc.STARTUP_LAYOUT, f"{_month()}월 리마인드 문자")
    assert heads[at + len(after)] == first_month, heads


def test_고정_칸은_여전히_NO_와_기업명_둘이다(sheets):
    """가로로 밀어도 어느 기업 줄인지는 보여야 한다(`Layout.sticky`).

    셋째 칸(이제 `사업분야 대분류`)까지 고정하면 고정 폭이 300px 을 넘어 볼
    자리를 뺏는다 — 차례가 바뀐 자리라 한 번 더 잰다.
    """
    cells = _thead_cells(sheets.get(_url()).text)
    assert "stick stick-a" in cells[0][0], cells[0]
    assert "stick stick-b" in cells[1][0] and "기업명" in cells[1][1], cells[1]
    assert "stick" not in cells[2][0], f"셋째 칸이 고정됐습니다: {cells[2]}"


# ── 3. 필터가 붙는다 ────────────────────────────────────────────────────────

def test_네_칸_다_필터를_진다(db):
    """`filterable` 판정 하나에서 머리글 선언과 행이 싣는 목록이 **같이** 나온다."""
    from app.services import contact_columns as cc

    filters = cc.header_filters(cc.STARTUP_LAYOUT, [])
    carried = [c.key for c in cc.filter_columns(cc.STARTUP_LAYOUT, [])]
    for label, key in zip(COLUMNS, KEYS):
        assert filters.get(key) == f"{key}:{label}", (
            f"`{label}` 머리글에 필터 선언이 없습니다: {filters.get(key)}")
        assert key in carried, f"행이 `{key}` 값을 안 싣습니다"


def test_그려진_머리글에_필터가_서고_행이_값을_싣는다(sheets):
    """선언만 하고 안 실으면 늘 빈 목록, 싣기만 하면 죽은 속성이다.

    값은 **보이는 그대로** 실린다 — 비어 있는 줄은 빈 값(필터의 `(비어 있음)`)이다.
    """
    html = sheets.get(_url()).text
    got = _filters(html)
    for label, key in zip(COLUMNS, KEYS):
        assert got.get(label) == [f"{key}:{label}"], (
            f"`{label}` 머리글의 필터가 다릅니다: {got.get(label)}")

    rows = [opening for opening, _body in _rows(html)]
    assert len(rows) == 3, rows
    carried = [dict(re.findall(r'data-f-([\w-]+)="([^"]*)"', r)) for r in rows]
    majors = sorted(c.get("sector_major", "?") for c in carried)
    assert majors == ["", "에듀테크", "헬스케어"], majors
    decks = sorted(c.get("ir_deck", "?") for c in carried)
    assert decks == ["", "O", "X"], decks
    for c in carried:
        for key in KEYS:
            assert key in c, f"행이 `data-f-{key}` 를 안 실었습니다: {c}"


def test_보기를_안_적은_셋도_필터가_붙는다():
    """판정은 `choices` 가 아니라 **고르는 칸이냐**다(`Column.filterable`).

    분야 둘·기업구분은 보기를 코드에 적지 않는다 — 갈래를 한 벌 더 적으면
    사람이 쌓아 온 값과 어긋난다. 그 셋에서 필터가 조용히 빠지면 이번 일의
    절반이 사라진다.
    """
    from app.services import contact_columns as cc

    by_key = {c.key: c for c in cc.STARTUP_LAYOUT.head}
    for key in ("sector_major", "sector_minor", "company_kind"):
        column = by_key[key]
        assert column.kind == "pick" and not column.choices, column
        assert column.filterable, f"`{column.label}` 에 필터가 안 붙습니다"
    deck = by_key["ir_deck"]
    assert deck.choices == "O,X", "IR Deck 유무는 O/X 둘 중에서 고른다"


def test_보기를_안_적은_칸은_표에서_다른_줄의_값을_보기로_띄운다(sheets):
    """표 칸에 `data-choices` 가 없으면 `startPick` 이 **다른 줄이 쓰고 있는 값**을
    모아 띄운다(`inline_edit.js` 의 `knownValues`). 그 값이 칸 글자로 실려 있어야
    모을 것이 있다 — 칸 안에 값이 안 그려지면 보기가 늘 빈 목록이다.
    """
    html = sheets.get(_url()).text
    for key in ("sector_major", "sector_minor", "company_kind"):
        cells = re.findall(rf'data-field="{key}"[^>]*>([^<]*)</div>', html)
        assert len(cells) == 3, f"`{key}` 칸이 줄마다 안 섰습니다: {cells}"
        assert len({c for c in cells if c}) == 2, (
            f"`{key}` 칸에 줄마다의 값이 안 그려졌습니다: {cells}")
        tag = re.search(rf'<div[^>]*data-field="{key}"[^>]*>', html).group(0)
        assert "data-choices" not in tag, (
            f"`{key}` 에 보기를 적었습니다 — 데이터에서 모으기로 한 칸입니다")
    deck = re.search(r'<div[^>]*data-field="ir_deck"[^>]*>', html).group(0)
    assert 'data-choices="O,X"' in deck, deck


def test_필터에_걸린_값을_표에서_고치면_행이_새_값을_싣는다(sheets, db):
    """저장 → 다시 그리기 → 필터 목록. 한 바퀴가 이어져야 고친 값으로 걸린다."""
    from app.models import VcContact

    row = (db.query(VcContact)
           .filter(VcContact.source_sheet == LIST, VcContact.name == "김샘플3")
           .one())
    res = sheets.patch(f"/api/contacts/{row.id}",
                       json={"notes": {"sector_major": "핀테크", "ir_deck": "O"}})
    assert res.status_code == 200, res.text

    html = sheets.get(_url()).text
    opening = next(o for o, _b in _rows(html) if f'data-id="{row.id}"' in o)
    assert 'data-f-sector_major="핀테크"' in opening, opening
    assert 'data-f-ir_deck="O"' in opening, opening


# ── 4. 폭 ───────────────────────────────────────────────────────────────────

def test_폭은_필터를_건_뒤의_머리글이_한_줄에_들어가는_선이다():
    """값을 고르면 라벨 뒤에 `(1) ▾` 가 붙는다 — 그 상태까지 한 줄이어야 한다.

    이름 길이로만 잡으면 화면에서는 멀쩡하다가 **필터를 거는 순간** 머리글이
    두 줄로 접힌다. 이번에 올리는 칸이 바로 필터를 걸려고 올리는 칸이다.
    """
    from app.services import contact_columns as cc

    by_label = {c.label: c for c in cc.STARTUP_LAYOUT.head}
    for label, want in zip(COLUMNS, WIDTHS):
        column = by_label[label]
        need = round(_text_px(label + _FILTER_SUFFIX) + _PAD + _BUTTON)
        assert column.width >= need, (
            f"`{label}` {column.width}px — 필터를 걸면 {need}px 가 필요합니다")
        assert column.width == want, (
            f"`{label}` 폭이 {column.width}px 입니다(정한 값 {want}px) — 바꿨다면 "
            "`STARTUP_LAYOUT` 의 그 자리 주석의 표도 같이 고치세요")


def test_표_폭은_칸_폭의_합_그대로다(sheets, db):
    """`min-width` 는 **적어 둔 칸 폭의 합**이다 — 넷이 늘면 그만큼 저절로 는다.

    CSS 에 숫자를 박아 두면 그 숫자만 옛날 값으로 남아 머리글이 두 줄로
    접힌다(`contacts.html` 의 `table_columns|sum(attribute='width')`).
    """
    from app.services import contact_columns as cc

    # 이번 달 세 칸뿐이라 접히는 달도 숨긴 칸도 없다 — 화면에 선 칸 그대로다.
    columns = cc.table_columns(cc.STARTUP_LAYOUT, cc.month_columns(db, LIST))
    html = sheets.get(_url()).text
    got = re.search(r'id="contacts-table"[^>]*min-width:(\d+)px', html, re.S)
    assert got, "표 폭을 찾지 못했습니다"
    assert int(got.group(1)) == sum(c.width for c in columns) + 44
    assert sum(c.width for c in columns if c.label in COLUMNS) == sum(WIDTHS)


# ── 5. 다른 자리에 부작용이 없다 ────────────────────────────────────────────

def test_수정창과_엑셀에_칸이_한_번씩만_선다(db):
    """`head` 로 올리면서 `extra` 에 그대로 두면 **같은 칸이 두 번** 선다.

    수정창에 같은 `data-note` 입력이 둘 생기면 저장할 때 한쪽 값이 다른 쪽을
    덮고, 엑셀에는 같은 열이 둘 나온다 — 둘 다 화면은 멀쩡해 보인다.
    """
    from app.services import contact_columns as cc

    keys = [c.key for c in cc.panel_columns(cc.STARTUP_LAYOUT, [])]
    dup = sorted({k for k in keys if keys.count(k) > 1})
    assert not dup, f"수정창 칸이 겹칩니다: {dup}"
    extra = [c.key for c in cc.STARTUP_LAYOUT.extra]
    for key in KEYS:
        assert key in keys, f"수정창에서 `{key}` 가 빠졌습니다"
        assert key not in extra, f"`{key}` 가 아직 `extra` 에도 있습니다"
    assert cc.note_keys(cc.STARTUP_LAYOUT, []).count("sector_major") == 1


def test_수정창에_한_번씩_서고_저장하면_되읽힌다(sheets, db):
    """창에 같은 입력이 둘이면 `contacts.js` 가 어느 쪽을 실을지 모른다."""
    from app.models import VcContact

    html = sheets.get(_url()).text
    for label, key in zip(COLUMNS, KEYS):
        assert html.count(f'data-note="{key}"') == 1, (
            f"수정창에 `{label}` 입력이 한 개가 아닙니다")

    row = db.query(VcContact).filter(VcContact.source_sheet == LIST).first()
    sent = {"sector_major": "모빌리티", "sector_minor": "물류",
            "company_kind": "Series A", "ir_deck": "X"}
    res = sheets.patch(f"/api/contacts/{row.id}", json={"notes": sent})
    assert res.status_code == 200, res.text
    got = sheets.get(f"/api/contacts/{row.id}").json()["contact"]["notes"]
    for key, value in sent.items():
        assert got.get(key) == value, f"`{key}` 가 되읽기에서 다릅니다: {got}"


def test_엑셀에는_화면과_같은_차례로_한_번씩_나온다(sheets):
    """파일도 같은 목록(`panel_columns`)에서 나온다 — 칸이 빠지거나 겹치면 안 된다."""
    openpyxl = pytest.importorskip("openpyxl")

    res = sheets.get("/api/export/contacts.xlsx", params={"sheet": LIST})
    assert res.status_code == 200, res.text
    ws = openpyxl.load_workbook(_io.BytesIO(res.content)).active
    rows = list(ws.iter_rows(values_only=True))
    head = [str(c or "") for c in rows[0]]
    for label in COLUMNS:
        assert head.count(label) == 1, f"엑셀에 `{label}` 이 {head.count(label)}번 나옵니다"
    at = head.index("기업명")
    assert head[at + 1:at + 1 + len(COLUMNS)] == COLUMNS, head
    by_firm = {r[head.index("기업명")]: r for r in rows[1:]}
    assert by_firm["샘플기업1"][head.index("대분류")] == "에듀테크"


def test_시트_임포터는_같은_저장_자리로_읽어_넣는다():
    """시트에서 읽어 넣은 값이 **이 칸들에 그대로** 보여야 한다.

    임포터가 다른 키에 넣으면 시트를 올린 뒤에도 표의 네 칸은 비어 있다.
    `IR Deck` 은 시트 쪽 옛 철자(`IR dack`)로 찾는다 — 화면 이름만 고쳤다.
    """
    from scripts.import_startup_sheet import NOTES

    # 튜플이면 첫 낱말이 원본 시트 머리글이다(그다음은 10/22 화면 이름).
    by_key = {key: (label[0] if isinstance(label, tuple) else label) for label, key in NOTES}
    assert by_key.get("sector_major") == "사업분야 대분류"
    assert by_key.get("sector_minor") == "소분류"
    assert by_key.get("company_kind") == "기업구분"
    assert by_key.get("ir_deck") == "IR dack"


def test_투자사_배치는_머리글도_필터도_안_바뀐다(sheets, db, users):
    """같은 화면 코드(`contacts.html`)를 쓰는 표들이다. 요청은 스타트업 하나였다."""
    from app.models import ContactColumn, SheetOwner, VcContact
    from app.services import contact_columns as cc

    # 투자사 명함 표 — 머리글이 템플릿에 적혀 있는 표. `소분류` 는 이 표의 것이 따로
    # 선다(투자사가 실제로 투자한 소분류 · 회사 단위 — `investor_firms`). 스타트업의
    # `sector_minor` 가 아니라 자기 필터 키(`sub_sector`)여야 한다.
    page = sheets.get(f"/{cc.page_of(cc.INVESTOR)}?sheet={quote(OTHER)}").text
    heads = _thead(page)
    for label in COLUMNS:
        if label == "소분류":
            assert _filters(page)[label] == ["sub_sector:소분류"]
            continue
        assert label not in heads, f"투자사 표에 `{label}` 이 끼어들었습니다"

    # 투자사 딜공유 — 같은 반복문으로 그리는 표. 필터는 `그룹` 하나 그대로다.
    db.add(SheetOwner(label=DEAL, user_id=users["u1"].id, layout=cc.INVESTOR_MONTHLY))
    db.add(ContactColumn(sheet=DEAL, position=0, label=f"{_month()}월 딜소개"))
    db.add(VcContact(user_id=users["u1"].id, source_sheet=DEAL, name="박투자2",
                     firm="가나다벤처스"))
    db.commit()
    html = sheets.get(f"/{cc.page_of(cc.INVESTOR_MONTHLY)}?sheet={quote(DEAL)}").text
    heads = _thead(html)
    for label in COLUMNS:
        assert label not in heads, f"딜공유 표에 `{label}` 이 끼어들었습니다"
    assert cc.header_filters(cc.INVESTOR_MONTHLY_LAYOUT, []) == {
        "group_name": "group_name:그룹"}
    assert cc.header_filters(cc.INVESTOR_LAYOUT, []) == {}
