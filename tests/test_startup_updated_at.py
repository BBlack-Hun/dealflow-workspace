"""스타트업 표의 `수정한 날짜` 칸 — **앱이 적고, 사람은 못 고친다.**

사용자 요청은 한 줄이었다: "스타트업 메뉴의 **월별 리마인드 앞쪽으로 수정한
날짜 추가**해줘~". 그 한 줄이 실제로 지켜지려면 서로 다른 넷이 함께 참이어야
한다.

1. **자리** — 월별 리마인드 **앞쪽**이다. 월별 묶음은 `head` 와 `tail` 사이에
   통째로 서므로(`contact_columns.table_columns`) `head` 의 맨 끝이 곧 그
   자리다. 자리는 요청의 절반이라 여기서 못 박는다 — 칸이 하나 더 끼면
   밀린다.
2. **꼴** — 날짜와 **시·분**이 보인다. 저장값은 `2026-09-16T19:44:43+09:00` 이라
   그대로 내보이면 `T` 와 오프셋이 함께 나가고, 아무 생각 없이 `[:10]` 으로
   자르면 **시각이 통째로 사라진다**(이 저장소에는 `sent_at[:10]` 관용구가
   스무 곳 넘게 있다 — 다음 사람이 그것을 여기에도 쓸 수 있다).

   **초는 뺀다 — 처음에는 남겼었다.** 첫 요청이 '시분초까지' 여서 19자를
   그대로 보였는데, 두 화면에서 써 본 뒤 사용자가 다시 정했다("모든 수정한
   날짜에서 초는 빼줘"). 줄이는 자리가 `clock.stamp_text` 한 곳이라 이 화면은
   따라오기만 했다 — 여기서 고친 것은 폭뿐이다(150 → 130px).
3. **못 고친다** — 앱이 적는 값이다. 사람이 고칠 수 있으면 "언제 고쳤나" 가
   그 자리에서 거짓이 된다. 막는 자리가 셋이다: 표(눌러 고치기) · 수정창 ·
   서버 스키마. 화면만 막으면 주소로 직접 보내는 길이 늘 남는다.
4. **고치면 오른다** — 이 칸의 쓸모가 통째로 이것이다. `onupdate` 가 걸린
   칸이라 저절로 되지만, 저절로 되는 것일수록 조용히 깨진다.

**이주(migration)는 없다.** `VcContact` 는 `TimestampMixin` 을 쓰고 있어
`updated_at` 칸이 처음부터 있었다 — 없던 칸을 만드는 이야기가 아니라 이미
적히고 있던 값을 화면에 세우는 이야기다.

IR 기업 현황이 같은 칸을 먼저 세웠다(#200 · `tests/test_company_updated_at.py`).
거기서 정한 것들(자르는 자리 한 곳 · `%` 가 아니라 px · 한 줄로 · 한 번도 안
고친 줄은 옅게)을 그대로 따른다 — 같은 물음에 두 화면이 다르게 답하면 어느
쪽이 맞는지 알 수 없다.

이름·회사·번호는 전부 지어낸 값이다 — 저장소가 공개다.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from .conftest import DEMO_PASSWORD

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "app" / "templates" / "contacts.html"
SCRIPT = ROOT / "app" / "static" / "js" / "contacts.js"
CSS = ROOT / "app" / "static" / "css" / "app.css"

COLUMN = "수정한 날짜"
# 값(110px)에 맞춘 폭. 초를 빼면서 글자가 19자 → 16자가 되어 150 → 130px 이
# 됐다 — 아래 `test_폭은_값에_맞춘다`.
WIDTH_PX = 130

LIST = "샘플 스타트업(9)"

# 아주 옛 시각. 고쳤을 때 값이 실제로 **오르는지** 보려면 출발점이 지금과
# 뚜렷이 달라야 한다 — 같은 **분** 안에 두 번 고치면 분까지만 보이는 값은
# 안 변한다(초를 뺀 뒤로 그 창이 1초에서 1분으로 넓어졌다).
OLD = "2020-01-02T03:04:05+09:00"
OLD_TEXT = "2020-01-02 03:04"


def _month() -> int:
    from app import clock

    return clock.today().month


def _url() -> str:
    from urllib.parse import quote

    from app.services import contact_columns as cc

    return f"/{cc.page_of(cc.STARTUP)}?sheet={quote(LIST)}"


def _rewind(db, row, created: bool = True):
    """그 줄의 시각을 옛날로 되돌린다 — **SQL 로 직접** 적는다.

    앱의 시계(`clock.now`)를 미는 길은 쓰지 않는다. 시계 하나로 세션 만료까지
    함께 움직여서(`services/auth`), 로그인해 둔 시험 클라이언트가 그 자리에서
    쫓겨난다 — 시각을 보려다 로그인을 보게 된다. (#200 이 같은 이유로
    같은 길을 썼다.)

    ORM 으로 적으면 `onupdate` 가 그 자리에서 다시 '지금' 으로 덮어쓴다.
    """
    from sqlalchemy import text as sql

    cols = "updated_at = :t" + (", created_at = :t" if created else "")
    db.execute(sql(f"UPDATE vc_contacts SET {cols} WHERE id = :i"),
               {"t": OLD, "i": row.id})
    db.commit()
    db.expire_all()


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


# ── ① 자리 — 월별 리마인드 **앞쪽** ─────────────────────────────────────────

def test_월별_리마인드_바로_앞에_선다(sheets, db):
    """요청의 절반은 **자리**다.

    월별 묶음은 `head` 와 `tail` **사이**에 통째로 서므로, 그 앞이라는 말은
    곧 `head` 의 맨 끝이다. 사이에 끼우려 하면 달 칸 묶음을 쪼개야 하고,
    그러면 한 달의 기록이 표 두 군데로 갈린다.
    """
    from app.services import contact_columns as cc

    names = _thead(sheets.get(_url()).text)
    assert COLUMN in names, f"`{COLUMN}` 머리글이 없습니다: {names}"

    months = cc.month_columns(db, LIST)
    first = cc.month_label(cc.STARTUP_LAYOUT, months[0].label)
    assert names.index(COLUMN) + 1 == names.index(first), (
        f"`{COLUMN}` 은 월별 칸 **바로 앞**이어야 합니다 — 지금 차례: {names}")


def test_배치에서도_head_의_맨_끝이다():
    """화면이 아니라 **배치**가 자리를 정한다.

    화면에서만 맞춰 두면 엑셀·수정창처럼 같은 목록을 읽는 다른 자리가
    어긋난다(이 저장소가 표와 머리글을 한 목록에서 뽑는 이유다).
    """
    from app.services import contact_columns as cc

    last = cc.STARTUP_LAYOUT.head[-1]
    assert last.label == COLUMN, f"`head` 의 맨 끝이 아닙니다: {last.label}"
    assert last.key == "updated_at" and last.source == "stamp"
    assert last.in_table is True


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


def test_머리와_칸이_같은_수만큼_늘었다(sheets):
    """하나만 늘면 **그 뒤 칸이 전부 한 칸씩 밀린다.**

    달마다 칸이 세 개씩 늘어나는 표라 특히 잘 어긋난다.
    """
    html = sheets.get(_url()).text
    heads = len(_thead(html))
    body = re.search(r"<tbody>(.*?)</tbody>", html, re.S).group(1)
    first = re.search(r'<tr class="data-row.*?</tr>', body, re.S).group(0)
    cells = len(re.findall(r"<td\b", first))
    assert heads == cells, f"머리 {heads}개 · 칸 {cells}개 — 그 뒤가 한 칸씩 밀립니다"


# ── ② 꼴 — 시·분·초까지 ─────────────────────────────────────────────────────

def test_표에_실리는_값이_자르는_한_곳을_지난다(sheets, db, row):
    """`2026-09-16T19:44:43+09:00` → `2026-09-16 19:44`.

    줄이는 자리는 `app/clock.py` 의 `stamp_text` 한 곳이고 라우터가 거기를
    지난다. 화면에서 또 자르면 같은 값이 두 꼴로 보이고, 그중 하나만 고쳐지는
    날이 온다 — **초를 뺀 판이 그것을 실제로 확인한 판이었다.** 이 화면은
    아무 것도 안 고쳤는데도 함께 따라왔다.
    """
    from app.clock import stamp_text

    _rewind(db, row)
    html = sheets.get(_url()).text
    assert OLD_TEXT in html, "화면에 시각이 안 실렸습니다"
    assert OLD not in html, \
        "`T` 와 시간대 오프셋이 붙은 저장값이 화면에 그대로 나갔습니다"
    assert "03:04:05" not in html, "초가 화면에 남아 있습니다"
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}", stamp_text(OLD))


# ── ③ 못 고친다 — 표 · 수정창 · 서버 ────────────────────────────────────────

def test_눌러_고칠_수_없는_칸이다(sheets):
    """`inline_edit.js` 는 `.cell[data-field]` 를 찾는다 — **둘 다 없어야** 한다.

    하나만 빼도 지금은 안 열리지만, 나중에 누가 `cell` 만 붙이거나 `data-field`
    만 붙이면 그 순간 열린다. 둘 다 없는 것을 못 박아 둔다.
    """
    html = sheets.get(_url()).text
    tag = re.search(r'<td class="updated-at[^"]*"[^>]*>', html)
    assert tag, "`수정한 날짜` 칸을 못 찾았습니다"
    assert "data-field" not in tag.group(0), \
        "`data-field` 가 붙어 있으면 눌러서 고쳐집니다 — 앱이 적는 값입니다"
    assert not re.search(r'class="[^"]*\bcell\b', tag.group(0)), \
        "`cell` 이 붙어 있으면 눌러서 고쳐집니다 — 앱이 적는 값입니다"


def test_수정창에도_고치는_칸으로_안_선다(sheets, db):
    """창은 [저장] 한 번에 **폼의 모든 칸을 되보낸다**(`contacts.js`).

    `id="f-updated_at"` 을 세우는 순간 창이 이 값을 되보내게 되고, 그러면
    사람이 화면에서 고친 시각이 저장된다 — 값이 거짓이 된다.

    배치 쪽에서도 막는다 — 수정창은 `panel_columns` 하나에서 나온다.
    """
    from app.services import contact_columns as cc

    assert 'id="f-updated_at"' not in sheets.get(_url()).text, \
        "창에 고치는 칸으로 섰습니다"
    months = cc.month_columns(db, LIST)
    assert not [c for c in cc.panel_columns(cc.STARTUP_LAYOUT, months)
                if c.source == "stamp"], "수정창 목록에 들어 있습니다"


def test_엑셀에도_안_나간다(sheets, db):
    """엑셀은 **원본 시트와 나란히 놓고 대조하는 자리**다.

    시트에 없던 칸이라 거기 넣을 것이 아니다. 목록이 수정창과 같은 함수에서
    나오므로(`panel_columns`) 한 곳만 막으면 둘 다 막힌다.
    """
    import io
    from urllib.parse import quote

    from openpyxl import load_workbook

    res = sheets.get(f"/api/export/contacts.xlsx?sheet={quote(LIST)}")
    assert res.status_code == 200, res.text
    book = load_workbook(io.BytesIO(res.content))
    head = [c.value for c in next(book.active.iter_rows(max_row=1))]
    assert COLUMN not in head, f"엑셀에 끼어들었습니다: {head}"


def test_보내도_안_먹힌다(sheets, db, row):
    """스키마(`ContactIn`)에 없는 칸이라 PATCH 로 밀어 넣어도 저장되지 않는다.

    화면에서 막는 것만으로는 부족하다 — 주소로 직접 보내는 길이 늘 남는다.
    """
    _rewind(db, row)
    res = sheets.patch(f"/api/contacts/{row.id}",
                       json={"updated_at": "1999-01-01T00:00:00+09:00"})
    assert res.status_code == 200, res.text
    db.expire_all()
    assert not (row.updated_at or "").startswith("1999"), \
        "사람이 보낸 시각이 그대로 저장됐습니다"


def test_필터를_안_세운다(sheets, db):
    """값이 줄마다 다른 시각이라 목록으로 고를 것이 아니다.

    (안 쓰이는 필터 속성은 `tests/test_filter_columns.py` 가 따로 잡는다 —
     여기서는 **세우지 않기로 한 판단**을 못 박는다.)
    """
    from app.services import contact_columns as cc

    months = cc.month_columns(db, LIST)
    assert "updated_at" not in {c.key for c in
                                cc.filter_columns(cc.STARTUP_LAYOUT, months)}
    # **폭으로 찾지 않는다.** 150 → 130px 이 되면서 `투자유치 상태` 와 폭이
    # 같아졌고, 폭만 보고 찾던 정규식이 그 칸을 집어 와 엉뚱한 곳에서 터졌다
    # (그 칸에는 필터가 있다). 찾는 기준은 **이름**이어야 한다 — 폭은 언제든
    # 다른 칸과 겹칠 수 있는 값이다.
    html = sheets.get(_url()).text
    th = next((m.group(0) for m in re.finditer(r"<th\b[^>]*>(.*?)</th>", html, re.S)
               if COLUMN in re.sub(r"<[^>]+>", " ", m.group(1))), None)
    assert th, f"`{COLUMN}` 머리글을 못 찾았습니다"
    assert f"width:{WIDTH_PX}px" in th, f"폭이 {WIDTH_PX}px 이 아닙니다: {th}"
    assert "data-filters" not in th, "시각은 골라서 거를 값이 아닙니다"
    assert "data-f-updated_at=" not in html, "행이 죽은 값을 싣습니다"


# ── ④ 고치면 오른다 ─────────────────────────────────────────────────────────

def test_칸을_고치면_시각이_오른다(sheets, db, row):
    """`onupdate` 가 실제로 걸리는가. 이 칸의 쓸모가 통째로 이것이다."""
    from app import clock

    _rewind(db, row)
    assert OLD_TEXT in sheets.get(_url()).text

    res = sheets.patch(f"/api/contacts/{row.id}", json={"memo": "고침"})
    assert res.status_code == 200, res.text

    db.expire_all()
    after = clock.stamp_text(row.updated_at)
    assert after != OLD_TEXT, "칸을 고쳤는데 `수정한 날짜` 가 그대로입니다"
    assert after.startswith(clock.today().isoformat()), after
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}", after), after
    assert after in sheets.get(_url()).text


def test_그_명단에만_있는_칸을_고쳐도_오른다(sheets, db, row):
    """월별 메모는 `notes` 한 칸에 담긴다 — 그래도 줄을 고친 것이다.

    `notes` 는 JSON 글자 칸이라, 같은 글자를 다시 넣으면 SQLAlchemy 가 바뀐
    것으로 안 보고 `onupdate` 도 안 돈다. 다른 글자를 넣어 본다.
    """
    from app import clock
    from app.services import contact_columns as cc

    _rewind(db, row)
    key = cc.note_key(cc.month_columns(db, LIST)[0].id)
    res = sheets.patch(f"/api/contacts/{row.id}",
                       json={"notes": {key: "9/2 문자 발송\n9/5 부재중"}})
    assert res.status_code == 200, res.text
    db.expire_all()
    assert clock.stamp_text(row.updated_at) != OLD_TEXT, \
        "월별 메모를 고쳤는데 `수정한 날짜` 가 그대로입니다"


def test_고친_시각이_응답에_실려_온다(sheets, db, row):
    """표가 **새로고침 없이** 그 자리에서 고쳐 그린다(`contacts.js`).

    안 실으면 화면은 고치기 전 시각을 그대로 두게 되고, 방금 고친 사람 눈에는
    저장이 안 된 것처럼 보인다 — 그 물음에 답하라고 세운 칸이 그 물음을 만든다.
    """
    from app import clock

    _rewind(db, row)
    sent = sheets.patch(f"/api/contacts/{row.id}",
                        json={"memo": "고침"}).json().get("updated_at")
    assert sent and sent != OLD_TEXT, "응답에 고친 시각이 없습니다"
    db.expire_all()
    # **되읽기와 같아야 한다.** 화면이 이 값을 칸에 그대로 적으므로, 여기가
    # 어긋나면 새로고침하는 순간 칸의 글자가 바뀐다.
    assert clock.stamp_text(row.updated_at) == sent
    assert sent in sheets.get(_url()).text


def test_화면이_그_자리에서_고쳐_그린다():
    """응답 값을 **그대로** 적는다 — 브라우저 시계로 지어내지 않는다.

    지어내면 서버 시계와 다른 만큼 어긋나고, 새로고침하는 순간 다른 시각으로
    바뀐다. 옅은 글씨도 걷어내야 한다 — "만든 뒤로 고친 적이 없다" 는 표시인데
    방금 고쳤으니 더는 참이 아니다.
    """
    # **주석은 먼저 지운다.** 왜 그렇게 했는지를 주석에 적어 두는 파일이라,
    # 안 지우면 설명하려고 적은 글자(`new Date()`)를 코드로 세게 된다.
    text = re.sub(r"//[^\n]*", "", SCRIPT.read_text(encoding="utf-8"))
    block = re.search(r'getElementById\("contacts-table"\);(.*?)\}\)\(\);\s*$',
                      text, re.S)
    assert block and "updated_at" in block.group(1), \
        "표에서 눌러 고쳤을 때 시각을 되그리는 자리가 없습니다"
    body = block.group(1)
    assert "data.updated_at" in body, "응답이 준 값을 안 씁니다"
    assert "new Date(" not in body, "브라우저 시계로 시각을 지어냅니다"
    assert 'classList.remove("muted")' in body, "옅은 글씨가 안 걷힙니다"


# ── ⑤ 한 번도 안 고친 줄 ────────────────────────────────────────────────────

def test_한_번도_안_고친_줄은_그렇다고_말한다(sheets, db, row):
    """만든 시각이 그대로 들어 있다 — 아무 표시 없이 두면 '이때 고쳤다' 로 읽힌다.

    **값을 비우지는 않는다.** 빈 칸은 '못 읽었다' 로도 읽히고, 그러면 이 칸을
    믿을 수 없게 된다. 옅게 적고 짚으면 말해 준다(#200 과 같은 말·같은 결).
    """
    _rewind(db, row)
    html = sheets.get(_url()).text
    assert 'class="updated-at muted"' in html, "만든 그대로인 줄에 표시가 없습니다"
    assert "만든 뒤로 아직 고친 적이 없습니다" in html
    # 그래도 **시각은 보인다** — 표시는 값을 대신하는 것이 아니라 덧붙는 것이다.
    assert OLD_TEXT in html


def test_한_번_고치고_나면_그_표시가_없어진다(sheets, db, row):
    _rewind(db, row)
    sheets.patch(f"/api/contacts/{row.id}", json={"memo": "고침"})
    html = sheets.get(_url()).text
    assert 'class="updated-at muted"' not in html, \
        "고친 줄에 '아직 안 고쳤다' 표시가 남아 있습니다"
    assert "마지막으로 고친 시각" in html


# ── ⑥ 폭·모양 ──────────────────────────────────────────────────────────────

def test_폭은_값에_맞춘다():
    """이 표의 다른 칸들과 **자가 다르다.**

    옆 칸들은 *필터를 건 뒤의 머리글*에 맞춘다(값이 한두 글자인 고르는 칸들).
    이 칸은 값이 **언제나 16자**라 머리글(`수정한 날짜`)보다 훨씬 넓다 — 그래서
    값에 맞춘다. `%` 로 두지 않는 이유도 같다: 달 칸이 늘어 표가 넓어지는 날
    비율이 줄면 글자가 조용히 두 줄로 접힌다.

    **150 → 130px.** 초를 빼면서 값이 19자에서 16자가 됐다. 폭을 정하는 것이
    값이므로 값이 줄면 폭도 같이 줄어야 한다 — 안 줄이면 20px 이 빈자리로
    남는다. 아래 `19자 시절 폭` 검사가 그것을 못 박는다.
    """
    from app.services import contact_columns as cc

    from .test_ui_layout import _text_px

    column = cc.STARTUP_LAYOUT.head[-1]
    assert column.width == WIDTH_PX, column
    need = round(_text_px("2026-09-16 19:44") + 18)
    assert need <= column.width, f"값이 안 들어갑니다: {need}px 필요"
    assert round(_text_px(COLUMN) + 18) <= column.width
    # 넉넉하다고 그냥 두면 안 된다 — 빈자리도 폭이다. 150px 은 초까지 보이던
    # 19자 시절의 폭이다(`_text_px` 는 12px 머리글 자라 13px 본문 값을 조금
    # 좁게 셈한다 — 위 아래 한계로만 쓰고, 실측값은 docstring 에 적어 두었다).
    assert column.width < 150, (
        f"초를 뺐는데 폭이 19자 시절 그대로입니다: {column.width}px")


def test_한_줄로_고정한다():
    """`table-layout: fixed` 라 칸이 조금이라도 좁아지면 빈칸 자리에서 접힌다.

    접히면 그 줄만 키가 커져 표가 들쭉날쭉해지고, 아무 말도 안 해 준다.
    넘치게 두면 `overflow: hidden` 이 잘라 주어 "칸이 좁다" 가 눈에 보인다.
    """
    css = CSS.read_text(encoding="utf-8")
    assert re.search(r"\.startup-table td\.updated-at\s*\{[^}]*white-space:\s*nowrap",
                     css), "한 줄 고정 규칙이 없습니다"


def test_표_폭은_칸_폭의_합에서_나온다(sheets):
    """숫자를 CSS 에 박지 않는다 — 달마다 칸이 세 개씩 붙는 표다.

    박아 두면 그 숫자만 옛날 값으로 남아 머리글이 두 줄로 접힌다. 화면이
    칸 폭을 더해서 낸다(`contacts.html`).
    """
    from app.services import contact_columns as cc

    css = CSS.read_text(encoding="utf-8")
    assert not re.search(r"\.startup-table\s*\{[^}]*min-width", css), \
        "표 폭을 CSS 에 박아 두었습니다"

    html = sheets.get(_url()).text
    got = re.search(r'id="contacts-table"[^>]*style="min-width:(\d+)px', html, re.S)
    assert got, "표에 폭이 안 실렸습니다"
    layout = cc.STARTUP_LAYOUT
    assert int(got.group(1)) >= sum(c.width for c in layout.head if c.in_table)
