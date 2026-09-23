"""스타트업 표의 `IR 미팅 제공일자` 칸 — **이메일 바로 오른쪽**.

사용자 요청은 한 줄이었다: "스타트업 메뉴의 **이메일 컬럼 오른쪽으로 IR 미팅
제공일자 컬럼** 넣어줘". 그 한 줄이 실제로 지켜지려면 서로 다른 넷이 함께
참이어야 한다.

1. **자리** — `이메일` 바로 오른쪽이다. 자리는 요청의 절반이라 여기서 못
   박는다. 뒤따르는 ①②(투자유치 상태 · 당사 협업 상태)와 계약 세 칸은 **일이
   진행되는 차례**로 묶여 있는데(`contact_columns.STARTUP_LAYOUT` 의 그 자리
   주석), 이 칸은 그 묶음 **앞**에 서므로 그 상대 차례를 흐트러뜨리지 않는다.
2. **월별 묶음을 안 민다** — 달 칸은 `head` 와 `tail` **사이**에 통째로 서고
   (`contact_columns.table_columns`), `head` 의 맨 끝은 `수정한 날짜` 그대로다.
   머리글 하나가 끼면 그 뒤가 전부 한 칸씩 밀리는 표라, 달 칸 묶음이 제자리에
   있는지를 따로 잰다.
3. **넷에 다 선다** — 표 · 수정창 · 엑셀, 그리고 저장·되읽기. 하나만 빠져도
   증상이 조용하다. 이 저장소가 반복해 당한 부류가 바로 그것이라
   (`contact_columns` 모듈 첫머리) 네 자리를 함께 잰다.
4. **날짜 칸인데 글자다** — `Column.kind` 에 날짜 갈래가 없다. 만들지 않는
   이유가 IR 기업 현황의 같은 이름 칸에 이미 적혀 있다(`companies.html` 의
   `미팅제공일자` · `수신일`): 달력 고르개로 두면 `9월 중`·`미정` 을 적을 수
   없고, **수정창은 모든 칸을 한 번에 보내므로** 날짜 칸이 못 읽는 글자는
   다른 칸을 고치려고 [저장]하는 것만으로 지워진다.

**이주(migration)는 없다.** 이 명단에만 있는 값이라 `VcContact.notes` 에 고정
키로 담는다 — 모델 칸을 만들지 않으니 판이 필요 없다.

이름·회사·번호는 전부 지어낸 값이다 — 저장소가 공개다.
"""
from __future__ import annotations

import io as _io
import re

import pytest

from .conftest import DEMO_PASSWORD

COLUMN = "IR 미팅 제공일자"
KEY = "ir_meeting_offered_at"
# 머리글(`IR 미팅 제공일자` · 12px 굵은 글씨)에 맞춘 폭. 값(`2026-09-15` ·
# 10자)보다 머리글이 넓은 칸이라 넓은 쪽이 정했다 — 아래 `test_폭은_머리글에_맞춘다`.
WIDTH_PX = 104
# 앞에 서는 칸. **이름을 여기 적어 두는 것이 요청 그 자체**다.
LEFT = "이메일"

LIST = "샘플 스타트업(9)"


def _month() -> int:
    from app import clock

    return clock.today().month


def _url() -> str:
    from urllib.parse import quote

    from app.services import contact_columns as cc

    return f"/{cc.page_of(cc.STARTUP)}?sheet={quote(LIST)}"


def _thead(html: str) -> list:
    m = re.search(r"<thead>(.*?)</thead>", html, re.S)
    assert m, "표 머리글을 찾지 못했습니다"
    out = []
    for _attrs, cell in re.findall(r"<th\b([^>]*)>(.*?)</th>", m.group(1), re.S):
        out.append(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", cell)).strip())
    return out


@pytest.fixture()
def sheets(client, db, users):
    from app.models import ContactColumn, SheetOwner, VcContact
    from app.services import contact_columns as cc

    u1 = users["u1"]
    db.add(SheetOwner(label=LIST, user_id=u1.id, layout=cc.STARTUP, is_hidden=0))
    for pos, what in enumerate(("리마인드 문자", "리마인드 TEL", "카톡 연결")):
        db.add(ContactColumn(sheet=LIST, label=f"{_month()}월 {what}", position=pos))
    db.add(VcContact(user_id=u1.id, source_sheet=LIST, name="김샘플1",
                     firm="샘플기업1", phone="01000000101"))
    db.commit()
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    return client


@pytest.fixture()
def row(db):
    from app.models import VcContact

    return db.query(VcContact).filter(VcContact.source_sheet == LIST).one()


# ── ① 자리 — `이메일` 바로 오른쪽 ───────────────────────────────────────────

def test_이메일_바로_오른쪽에_선다(sheets):
    """요청의 절반은 **자리**다. 그려진 화면에서 잰다."""
    names = _thead(sheets.get(_url()).text)
    assert COLUMN in names, f"`{COLUMN}` 머리글이 없습니다: {names}"
    assert names.index(LEFT) + 1 == names.index(COLUMN), (
        f"`{COLUMN}` 은 `{LEFT}` **바로 오른쪽**이어야 합니다 — 지금 차례: {names}")


def test_배치에서도_이메일_바로_뒤다():
    """화면이 아니라 **배치**가 자리를 정한다.

    화면에서만 맞춰 두면 엑셀·수정창처럼 같은 목록을 읽는 다른 자리가
    어긋난다(이 저장소가 표와 머리글을 한 목록에서 뽑는 이유다).
    """
    from app.services import contact_columns as cc

    labels = [c.label for c in cc.STARTUP_LAYOUT.head]
    assert labels.index(LEFT) + 1 == labels.index(COLUMN), (
        f"`head` 에서 `{LEFT}` 바로 뒤가 아닙니다: {labels}")


def test_일이_진행되는_차례_묶음을_안_흐트러뜨린다():
    """①② → 견적서 → 계약 → 계약서 수신 — 이 **상대 차례**가 요청보다 먼저 있다.

    담당 기업이 여든인 팀원이 적어 보낸 말이 정한 차례다. 새 칸은 그 묶음
    **앞**에 서므로 사이를 벌리지 않는다 — 가운데 끼면 "계약했나 → 그런데
    미팅은 언제 주나" 로 읽는 차례가 끊긴다.
    """
    from app.services import contact_columns as cc

    labels = [c.label for c in cc.STARTUP_LAYOUT.head]
    flow = ["투자유치 상태", "당사 협업 상태",
            "견적서 첨부여부", "계약여부", "계약서 수신여부"]
    at = [labels.index(x) for x in flow]
    assert at == list(range(at[0], at[0] + len(flow))), (
        f"흐름 묶음 사이에 다른 칸이 끼었습니다: {labels}")
    assert labels.index(COLUMN) < at[0], "새 칸이 흐름 묶음 뒤로 갔습니다"


# ── ② 월별 묶음 — 밀리지 않는다 ─────────────────────────────────────────────

def test_월별_묶음은_제자리다(sheets, db):
    """달 칸은 `수정한 날짜` 바로 뒤에 **통째로** 선다.

    머리글 하나가 끼면 그 뒤가 전부 한 칸씩 밀리는 표다. 칸을 늘렸다고
    한 달의 기록이 표 두 군데로 갈리거나 묶음이 뒤로 물러나면 안 된다.
    """
    from app.services import contact_columns as cc

    names = _thead(sheets.get(_url()).text)
    months = [cc.month_label(cc.STARTUP_LAYOUT, m.label)
              for m in cc.month_columns(db, LIST)]
    at = [names.index(m) for m in months]
    assert at == list(range(at[0], at[0] + len(months))), (
        f"달 칸 묶음이 쪼개졌습니다: {names}")
    assert names[at[0] - 1] == "수정한 날짜", (
        f"달 칸 묶음 바로 앞이 `수정한 날짜` 가 아닙니다: {names}")
    assert cc.STARTUP_LAYOUT.head[-1].label == "수정한 날짜", (
        "`head` 의 맨 끝이 밀렸습니다")


def test_머리와_칸이_같은_수만큼_늘었다(sheets):
    """하나만 늘면 **그 뒤 칸이 전부 한 칸씩 밀린다.**"""
    html = sheets.get(_url()).text
    heads = len(_thead(html))
    body = re.search(r"<tbody>(.*?)</tbody>", html, re.S).group(1)
    first = re.search(r'<tr class="data-row.*?</tr>', body, re.S).group(0)
    cells = len(re.findall(r"<td\b", first))
    assert heads == cells, f"머리 {heads}개 · 칸 {cells}개 — 그 뒤가 한 칸씩 밀립니다"


# ── ③ 넷에 다 선다 — 표 · 수정창 · 엑셀 · 저장 ──────────────────────────────

def test_표에서_눌러_고치고_저장하면_남는다(sheets, row, db):
    """표 · PATCH · 되읽기 — 셋이 다 맞아야 한 칸이 산다.

    하나만 빠져도 증상이 조용하다: PATCH 는 200 을 주는데 아무것도 안
    들어가거나, 저장은 되는데 다시 열면 빈칸이다.
    """
    html = sheets.get(_url()).text
    assert f'data-field="{KEY}"' in html, "표에서 눌러 고칠 수 있는 칸이 아닙니다"

    res = sheets.patch(f"/api/contacts/{row.id}", json={"notes": {KEY: "2026-09-15"}})
    assert res.status_code == 200, res.text

    db.expire_all()
    from app.services import contact_columns as cc

    assert cc.load_notes(db.get(type(row), row.id).notes).get(KEY) == "2026-09-15"
    assert "2026-09-15" in sheets.get(_url()).text, "저장한 값이 표에 안 보입니다"


def test_옆_칸을_고쳐도_안_지워진다(sheets, row, db):
    """수정창은 **칸을 한 번에** 보낸다. 날짜 칸이 아니라 글자 칸으로 둔 이유가
    이것이다 — 못 읽는 글자가 다른 칸을 고치는 것만으로 지워지면 안 된다.
    """
    sheets.patch(f"/api/contacts/{row.id}", json={"notes": {KEY: "9월 중"}})
    sheets.patch(f"/api/contacts/{row.id}", json={"notes": {"contract": "미계약"}})

    db.expire_all()
    from app.services import contact_columns as cc

    notes = cc.load_notes(db.get(type(row), row.id).notes)
    assert notes.get(KEY) == "9월 중", f"옆 칸을 고치자 값이 갈렸습니다: {notes}"


def test_수정창에도_선다(sheets):
    """표에서 보이는 칸이 창에 없으면 **긴 값을 고칠 자리가 없다.**"""
    html = sheets.get(_url()).text
    assert f'data-note="{KEY}"' in html, "수정창에 칸이 없습니다"
    assert COLUMN in html


def test_엑셀에도_따라온다(sheets, row):
    """파일은 시트와 나란히 놓고 대조하는 자리다 — 화면에 있는 칸이 빠지면
    받은 사람이 다른 표를 들고 대조하게 된다.
    """
    openpyxl = pytest.importorskip("openpyxl")

    sheets.patch(f"/api/contacts/{row.id}", json={"notes": {KEY: "2026-09-15"}})
    res = sheets.get("/api/export/contacts.xlsx", params={"sheet": LIST})
    assert res.status_code == 200, res.text
    ws = openpyxl.load_workbook(_io.BytesIO(res.content)).active
    rows = list(ws.iter_rows(values_only=True))
    assert COLUMN in rows[0], f"엑셀 머리글에 없습니다: {rows[0]}"
    assert rows[1][rows[0].index(COLUMN)] == "2026-09-15", "엑셀에 값이 안 담겼습니다"


# ── ④ 갈래와 폭 ─────────────────────────────────────────────────────────────

def test_날짜지만_글자_칸이다():
    """`Column.kind` 에 날짜 갈래가 없다 — 만들지 않는다.

    `pick` 도 아니다. 날짜는 줄마다 달라 고를 거리가 아니고, `pick` 으로 두면
    머리글에 필터가 붙어(`Column.filterable`) 줄 수만큼 항목이 생긴다.
    """
    from app.services import contact_columns as cc

    column = next(c for c in cc.STARTUP_LAYOUT.head if c.label == COLUMN)
    assert column.key == KEY and column.source == "note"
    assert column.kind == "text", "날짜 갈래를 새로 만들 자리가 아닙니다"
    assert not column.choices
    assert column.filterable is False, "줄마다 다른 값에 필터가 붙었습니다"
    assert column.in_table is True
    assert column.hint, "적는 꼴 안내가 없습니다 — 수정창 placeholder 로 건넨다"


def test_판이_필요_없다():
    """`notes` 에 담는다 — 모델 칸을 만들지 않으니 판(migration)이 없다."""
    from app.models import VcContact

    assert not hasattr(VcContact, KEY), (
        "모델 칸이 생겼습니다 — 이 칸은 `notes` 에 담기로 한 칸입니다")


def test_폭은_머리글에_맞춘다():
    """값(`2026-09-15`)보다 **머리글**이 넓은 칸이다.

    값에 맞추면 화면에서는 멀쩡하다가 머리글이 두 줄로 접힌다
    (`tests/test_startup_tab.py` 의 `머리글은_필터_단추까지_한_줄에_들어간다`
     가 그려진 화면에서 그것을 잰다).

    **`수정한 날짜`(130px)보다 좁다** — 저 칸은 `2026-09-23 14:30` 이 들어가고
    이 칸은 날짜만 들어간다. 같은 날짜 칸이라고 폭까지 맞추면 그 20px 이 값
    오른쪽의 빈자리로 남는다.
    """
    from app.services import contact_columns as cc
    from .test_ui_layout import _text_px

    column = next(c for c in cc.STARTUP_LAYOUT.head if c.label == COLUMN)
    assert column.width == WIDTH_PX
    assert column.width >= round(_text_px(COLUMN) + 18), "머리글이 두 줄로 접힙니다"
    stamp = next(c for c in cc.STARTUP_LAYOUT.head if c.label == "수정한 날짜")
    assert column.width < stamp.width, (
        "날짜만 들어가는 칸이 시각까지 들어가는 칸만큼 넓습니다")


# ── ⑤ 투자사 표에는 안 선다 ─────────────────────────────────────────────────

def test_투자사_표에는_안_선다(sheets, db, users):
    """같은 화면 코드(`contacts.html`)를 쓰는 표다. 요청은 스타트업 하나였다."""
    from urllib.parse import quote

    from app.models import SheetOwner, VcContact
    from app.services import contact_columns as cc

    other = "샘플 투자사 20"
    u1 = users["u1"]
    db.add(SheetOwner(label=other, user_id=u1.id, layout=cc.INVESTOR, is_hidden=0))
    db.add(VcContact(user_id=u1.id, source_sheet=other, name="박투자1",
                     firm="샘플벤처스1", phone="01000000201"))
    db.commit()

    html = sheets.get(f"/{cc.page_of(cc.INVESTOR)}?sheet={quote(other)}").text
    assert COLUMN not in _thead(html), "투자사 표에 칸이 끼어들었습니다"


# ── ⑥ 시트 임포터 — 달 칸으로 서면 안 된다 ──────────────────────────────────

def test_시트에_이_머리글이_와도_달_칸으로_안_선다():
    """남는 머리글은 전부 **달마다 늘어나는 칸**이 된다
    (`scripts/import_startup_sheet.parse`).

    달에 안 매이는 값이 달 칸 자리에 서면 펴 둘 달 자리를 하나 먹어 그 달의
    기록을 접어 버리고, 달이 바뀔 때마다 지난달로 밀려 내려간다. 화면에서
    적기 시작한 값이 시트를 한 번 올리는 것으로 그렇게 갈린다.
    """
    from scripts.import_startup_sheet import parse

    rows = [
        ["NO", "기업명", "성함", COLUMN, f"{_month()}월 리마인드 문자"],
        [1, "샘플기업1", "김샘플1", "2026-09-15", "문자 보냄"],
    ]
    out = parse(rows)
    assert COLUMN not in out["columns"], (
        f"이 머리글이 달 칸으로 섰습니다: {out['columns']}")
    assert out["items"][0]["notes"].get(KEY) == "2026-09-15"
