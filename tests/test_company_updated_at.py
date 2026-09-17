"""IR 기업 현황 표의 `수정한 날짜` 칸 — **앱이 적고, 사람은 못 고친다.**

사용자 요청은 한 줄이었다: "「기업구분」 컬럼 뒤쪽으로 수정한 날짜, 시분초까지".
그 한 줄이 실제로 지켜지려면 서로 다른 네 가지가 동시에 참이어야 한다.

1. **자리** — `기업구분` 바로 뒤다. 자리는 요청의 절반이라 여기서 못 박는다
   (칸을 하나 더 끼워 넣다가 순서가 밀리면 요청과 달라진다).
2. **꼴** — 시·분·초가 다 보인다. 저장값은 `2026-09-16T16:31:40+09:00` 라
   그대로 내보이면 `T` 와 오프셋이 함께 나가고, 아무 생각 없이 `[:10]` 으로
   자르면 **초는커녕 시각이 통째로 사라진다**(이 저장소에는 `sent_at[:10]`
   관용구가 스무 곳 넘게 있다 — 다음 사람이 그것을 여기에도 쓸 수 있다).
3. **못 고친다** — 앱이 적는 값이다. 사람이 고칠 수 있으면 "언제 고쳤나" 가
   그 자리에서 거짓이 된다. 표에서 눌러 고치는 길은 `.cell[data-field]` 둘이
   함께 있을 때만 열리므로(`static/js/inline_edit.js`), **둘 다 없어야** 한다.
4. **고치면 오른다** — 이 칸의 쓸모가 통째로 이것이다. `onupdate` 가 걸린
   칸이라 저절로 되지만, 저절로 되는 것일수록 조용히 깨진다(누가 `updated_at`
   을 손으로 적어 넣는 코드를 하나 두면 그날로 끝난다).

**이주(migration)는 없다.** `IrCompany` 는 `TimestampMixin` 을 쓰고 있어
`updated_at` 칸이 처음부터 있었다 — 이 판은 없던 칸을 만드는 이야기가 아니라
이미 적히고 있던 값을 화면에 세우는 이야기다.

값은 전부 가상값이다 — 저장소가 공개다.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "app" / "templates" / "companies.html"
SCRIPT = ROOT / "app" / "static" / "js" / "companies.js"
CSS = ROOT / "app" / "static" / "css" / "app.css"

COLUMN = "수정한 날짜"
WIDTH_PX = 150          # 값(130px)에 맞춘 폭 — 아래 `test_폭은_값에_맞춘다` 참고


# 아주 옛 시각. 고쳤을 때 값이 실제로 **오르는지** 보려면 출발점이 지금과
# 뚜렷이 달라야 한다 — 같은 초 안에 두 번 고치면 초까지만 적는 값은 안 변한다.
OLD = "2020-01-02T03:04:05+09:00"
OLD_TEXT = "2020-01-02 03:04:05"


def _rewind(db, company, created: bool = True):
    """그 줄의 시각을 옛날로 되돌린다 — **SQL 로 직접** 적는다.

    앱의 시계(`clock.now`)를 미는 길은 쓰지 않는다. 시계 하나로 세션 만료까지
    함께 움직여서(`services/auth`), 로그인해 둔 시험 클라이언트가 그 자리에서
    쫓겨난다 — 시각을 보려다 로그인을 보게 된다.

    ORM 으로 적으면 `onupdate` 가 그 자리에서 다시 '지금' 으로 덮어쓴다.
    """
    from sqlalchemy import text as sql

    cols = "updated_at = :t" + (", created_at = :t" if created else "")
    db.execute(sql(f"UPDATE ir_companies SET {cols} WHERE id = :i"),
               {"t": OLD, "i": company.id})
    db.commit()


@pytest.fixture()
def company(db):
    from app.models import IrCompany

    row = IrCompany(name="샘플가나헬스")
    db.add(row)
    db.commit()
    return row


def _tables() -> list:
    """이 화면의 `<table>` 들 — 여는 태그부터 닫는 태그까지, 나온 차례대로.

    Jinja 주석(`{# … #}`)은 먼저 지운다. 주석에 `<th>` 나 `data-field` 를 적어
    두는 일이 잦은 파일이라, 안 지우면 설명하려고 적은 글자를 마크업으로 세게
    된다(tests/test_ui_layout.py 와 같은 이유다).

    **탭을 `{% else %}` 로 가르지 않는다.** 그 글자는 표 안의 `{% for %}` 에도
    있어서(줄이 하나도 없을 때 까는 안내줄), 그것으로 자르면 엉뚱한 자리에서
    끊긴다. 표는 표로 찾는 편이 안 헷갈린다.
    """
    text = re.sub(r"\{#.*?#\}", "", TEMPLATE.read_text(encoding="utf-8"), flags=re.S)
    return re.findall(r"<table\b.*?</table>", text, re.S)


def _status_tab_markup() -> str:
    """IR 기업 현황(기본) 탭의 표. 두 탭이 같은 id 를 쓰므로 **두 번째**다.

    앞 표는 스타트업DB 탭이고(`{% if co_tab == 'db' %}` 쪽), 뒤 표가 남는 탭이다.
    셋째 표는 [수정] 창의 `소개 이력` 이라 여기 안 든다.
    """
    tables = _tables()
    assert len(tables) >= 2, "표가 둘보다 적습니다 — 화면 구조가 바뀌었습니다"
    markup = tables[1]
    assert COLUMN in markup, "두 번째 표가 IR 기업 현황 탭이 아닙니다"
    return markup


# ── ① 자리 ──────────────────────────────────────────────────────────────────

def test_기업구분_바로_뒤에_선다():
    """요청의 절반은 **자리**다 — `기업구분` 다음 칸이어야 한다."""
    heads = re.findall(r"<th\b[^>]*>(.*?)</th>", _status_tab_markup(), re.S)
    names = [re.sub(r"<[^>]+>", " ", h).strip() for h in heads]
    names = [re.sub(r"\s+", " ", n) for n in names]

    assert COLUMN in names, f"`{COLUMN}` 머리글이 없습니다: {names}"
    assert "기업구분" in names, f"`기업구분` 머리글이 없습니다: {names}"
    assert names.index(COLUMN) == names.index("기업구분") + 1, (
        f"`{COLUMN}` 은 `기업구분` **바로 뒤**여야 합니다 — 지금 차례: {names}")


def test_스타트업DB_탭은_안_건드린다():
    """같은 화면의 옆 탭이다. 요청은 `IR 기업 현황` 탭 하나였다."""
    db_tab = _tables()[0]
    assert COLUMN not in db_tab, "스타트업DB 탭에도 칸이 들어갔습니다"
    assert "updated-at" not in db_tab, "스타트업DB 탭에도 칸이 들어갔습니다"


def test_머리와_칸이_같은_수만큼_늘었다():
    """하나만 늘면 **그 뒤 칸이 전부 한 칸씩 밀린다.**

    줄이 하나도 없을 때 까는 안내줄(`colspan`)도 같이 센다 — 거기만 안 고치면
    기업이 0곳인 화면에서 표가 어긋난다.
    """
    markup = _status_tab_markup()
    heads = len(re.findall(r"<th\b", markup))
    body = re.search(r"<tbody>(.*?)</tbody>", markup, re.S).group(1)
    first_row = re.search(r"<tr\b[^>]*data-id=.*?</tr>", body, re.S).group(0)
    cells = len(re.findall(r"<td\b", first_row))
    assert heads == cells, f"머리 {heads}개 · 칸 {cells}개 — 그 뒤가 한 칸씩 밀립니다"

    colspan = re.search(r'<td colspan="(\d+)"', body)
    assert colspan and int(colspan.group(1)) == heads, (
        f"빈 표 안내줄의 colspan 이 {colspan and colspan.group(1)} 입니다 — {heads} 여야 합니다")


# ── ② 꼴 — 시·분·초까지 ─────────────────────────────────────────────────────

def test_시분초까지_보인다():
    """`2026-09-16T16:31:40+09:00` → `2026-09-16 16:31:40`."""
    from app.clock import now_iso, stamp_text

    assert stamp_text("2026-09-16T16:31:40+09:00") == "2026-09-16 16:31:40"
    # 지금 적히는 값도 같은 자리에서 끊긴다 — 저장 꼴이 바뀌면 여기서 잡힌다.
    text = stamp_text(now_iso())
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", text), text


def test_초를_자르지_않는다():
    """분까지만 보이면 **연달아 고친 두 줄을 구분하지 못한다.**

    이 저장소에는 `[:16]`(분까지)·`[:10]`(날짜까지)로 자르는 관용구가 여럿
    있어서, 그것을 여기에 옮겨 쓰기 쉽다. 요청은 '시분초까지' 였다.
    """
    from app.clock import stamp_text

    assert stamp_text("2026-09-16T16:31:40+09:00").endswith(":40")


def test_마이크로초가_붙은_옛_값도_같은_자리에서_끊긴다():
    """`now_iso` 는 초까지만 적지만, 그 전에 적힌 값까지 책임진다."""
    from app.clock import stamp_text

    assert stamp_text("2026-08-01T09:00:00.123456+00:00") == "2026-08-01 09:00:00"


def test_빈_값은_빈_글자다():
    """없는 시각을 지어내지 않는다 — 화면은 빈 칸을 그린다."""
    from app.clock import stamp_text

    assert stamp_text(None) == ""
    assert stamp_text("") == ""


def test_표에_실리는_값이_그_꼴이다(logged_in, company):
    from app.clock import stamp_text

    html = logged_in.get("/companies").text
    assert stamp_text(company.updated_at) in html
    # 저장 꼴이 그대로 새어 나가면 안 된다.
    assert company.updated_at not in html, \
        "`T` 와 시간대 오프셋이 붙은 저장값이 화면에 그대로 나갔습니다"


# ── ③ 못 고친다 ─────────────────────────────────────────────────────────────

def test_눌러_고칠_수_없는_칸이다():
    """`inline_edit.js` 는 `.cell[data-field]` 를 찾는다 — **둘 다 없어야** 한다.

    하나만 빼도 지금은 안 열리지만, 나중에 누가 `cell` 만 붙이거나 `data-field`
    만 붙이면 그 순간 열린다. 둘 다 없는 것을 못 박아 둔다.
    """
    markup = _status_tab_markup()
    cell = re.search(r'<td class="updated-at[^"]*"[^>]*>', markup)
    assert cell, "`수정한 날짜` 칸을 못 찾았습니다"
    tag = cell.group(0)
    assert "data-field" not in tag, \
        "`data-field` 가 붙어 있으면 눌러서 고쳐집니다 — 앱이 적는 값입니다"
    assert not re.search(r'class="[^"]*\bcell\b', tag), \
        "`cell` 이 붙어 있으면 눌러서 고쳐집니다 — 앱이 적는 값입니다"


def test_수정_창에도_고치는_칸으로_안_둔다():
    """창은 [저장] 한 번에 **모든 칸을 되보낸다**(`collect`).

    `id="f-updated_at"` 을 세우는 순간 창이 이 값을 되보내게 되고, 그러면
    사람이 화면에서 고친 시각이 저장된다 — 값이 거짓이 된다.
    """
    text = TEMPLATE.read_text(encoding="utf-8")
    assert 'id="f-updated_at"' not in text, "창에 고치는 칸으로 섰습니다"

    listed = re.search(r"var FIELDS = \[(.*?)\];", SCRIPT.read_text(encoding="utf-8"), re.S)
    assert listed, "companies.js 에서 FIELDS 를 못 찾았습니다"
    assert "updated_at" not in listed.group(1), \
        "창의 저장 목록(FIELDS)에 들어 있습니다 — [저장]이 이 값을 되보냅니다"


def test_보내도_안_먹힌다(logged_in, company):
    """스키마에 없는 칸이라 PATCH 로 밀어 넣어도 저장되지 않는다.

    화면에서 막는 것만으로는 부족하다 — 주소로 직접 보내는 길이 늘 남는다.
    """
    before = company.updated_at
    r = logged_in.patch(f"/api/companies/{company.id}",
                        json={"updated_at": "1999-01-01T00:00:00+09:00"})
    assert r.status_code == 200, r.text
    row = logged_in.get(f"/api/companies/{company.id}").json()
    assert not row["updated_at"].startswith("1999"), \
        "사람이 보낸 시각이 그대로 저장됐습니다"
    # 아무 칸도 안 고친 요청이라 시각도 그대로다.
    assert row["updated_at"][:10] == (before or "")[:10]


def test_필터를_안_세운다():
    """값이 줄마다 다른 시각이라 목록으로 고를 것이 아니다.

    (안 쓰이는 필터 속성은 tests/test_filter_columns.py 가 따로 잡는다 —
     여기서는 **세우지 않기로 한 판단**을 못 박는다.)
    """
    markup = _status_tab_markup()
    head = re.search(r'<th style="width:%dpx"[^>]*>\s*%s' % (WIDTH_PX, COLUMN),
                     markup)
    assert head, f"`{COLUMN}` 머리글을 못 찾았습니다"
    block = markup[head.start():head.end() + 80]
    assert "data-filters" not in block, "시각은 골라서 거를 값이 아닙니다"


# ── ④ 고치면 오른다 ─────────────────────────────────────────────────────────

def test_칸을_고치면_시각이_오른다(logged_in, db, company):
    """`onupdate` 가 실제로 걸리는가. 이 칸의 쓸모가 통째로 이것이다."""
    from app import clock

    _rewind(db, company)
    assert logged_in.get(f"/api/companies/{company.id}").json()["updated_at"] == OLD_TEXT

    r = logged_in.patch(f"/api/companies/{company.id}", json={"series": "Seed"})
    assert r.status_code == 200, r.text

    after = logged_in.get(f"/api/companies/{company.id}").json()["updated_at"]
    assert after != OLD_TEXT, "칸을 고쳤는데 `수정한 날짜` 가 그대로입니다"
    assert after.startswith(clock.today().isoformat()), after
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", after), after


def test_고친_시각이_응답에_실려_온다(logged_in, db, company):
    """표가 **새로고침 없이** 그 자리에서 고쳐 그린다(companies.js).

    안 실으면 화면은 고치기 전 시각을 그대로 두게 되고, 방금 고친 사람 눈에는
    저장이 안 된 것처럼 보인다 — 그 물음에 답하라고 세운 칸이 그 물음을 만든다.
    """
    _rewind(db, company)
    r = logged_in.patch(f"/api/companies/{company.id}", json={"series": "Seed"})
    assert r.status_code == 200, r.text
    sent = r.json().get("updated_at")
    assert sent and sent != OLD_TEXT, f"응답에 고친 시각이 없습니다: {r.text}"
    # **되읽기와 같아야 한다.** 화면이 이 값을 칸에 그대로 적으므로, 여기가
    # 어긋나면 새로고침하는 순간 칸의 글자가 바뀐다.
    assert logged_in.get(f"/api/companies/{company.id}").json()["updated_at"] == sent


def test_표를_다시_그려도_같은_값이다(logged_in, db, company):
    """응답이 준 값과 새로고침한 표의 값이 같아야 한다(화면이 지어낸 값이 아니다)."""
    _rewind(db, company)
    sent = logged_in.patch(f"/api/companies/{company.id}",
                           json={"series": "Seed"}).json()["updated_at"]
    assert sent in logged_in.get("/companies").text


def test_아무_것도_안_고친_저장은_시각을_안_올린다(logged_in, db, company):
    """열어 보기만 한 것은 고친 것이 아니다.

    이 칸이 '열어 본 시각' 까지 세기 시작하면, 값이 늘 최근이라 아무 말도
    못 하게 된다.
    """
    _rewind(db, company)
    r = logged_in.patch(f"/api/companies/{company.id}", json={})
    assert r.status_code == 200, r.text
    assert logged_in.get(f"/api/companies/{company.id}").json()["updated_at"] == OLD_TEXT


# ── ⑤ 한 번도 안 고친 줄 ────────────────────────────────────────────────────

def test_한_번도_안_고친_줄은_그렇다고_말한다(logged_in, company):
    """만든 시각이 그대로 들어 있다 — 아무 표시 없이 두면 '이때 고쳤다' 로 읽힌다.

    **값을 비우지는 않는다.** 빈 칸은 '못 읽었다' 로도 읽히고, 그러면 이 칸을
    믿을 수 없게 된다. 옅게 적고 짚으면 말해 준다.
    """
    row = logged_in.get(f"/api/companies/{company.id}").json()
    assert row["updated_never"] is True

    html = logged_in.get("/companies").text
    assert 'class="updated-at muted"' in html, "만든 그대로인 줄에 표시가 없습니다"
    assert "만든 뒤로 아직 고친 적이 없습니다" in html
    # 그래도 **시각은 보인다** — 표시는 값을 대신하는 것이 아니라 덧붙는 것이다.
    assert row["updated_at"] in html


def test_한_번_고치고_나면_그_표시가_없어진다(logged_in, db, company):
    _rewind(db, company)
    logged_in.patch(f"/api/companies/{company.id}", json={"series": "Seed"})

    row = logged_in.get(f"/api/companies/{company.id}").json()
    assert row["updated_never"] is False
    html = logged_in.get("/companies").text
    assert 'class="updated-at muted"' not in html, \
        "고친 줄인데 '고친 적 없음' 표시가 남아 있습니다"
    assert "마지막으로 고친 시각" in html


# ── ⑥ 폭 ────────────────────────────────────────────────────────────────────

def test_폭은_값에_맞춘다():
    """이 칸은 **머리글보다 값이 넓다** — 이름에 맞추면 글자가 접힌다.

    헤드리스 크롬으로 실측: 값 `2026-09-16 16:31:40` 이 13px 본문 글꼴에서
    130px, 머리글 `수정한 날짜` 가 12px 에서 55px. td 좌우 여백이 18px 이므로
    값 쪽이 148px 을 요구한다.

    `%` 가 아니라 `px` 인 이유는 companies.html 의 그 칸 주석에 적어 두었다 —
    값이 19자로 고정이라 표가 넓어져도 더 보여 줄 것이 없고, `%` 로 두면
    표 폭이 바뀌는 날 글자가 조용히 두 줄로 접힌다.
    """
    markup = _status_tab_markup()
    m = re.search(r'<th style="width:(\d+)(px|%)"[^>]*>\s*' + COLUMN, markup)
    assert m, f"`{COLUMN}` 머리글의 폭을 못 찾았습니다"
    assert m.group(2) == "px", "이 칸의 폭은 글자가 정한다 — `%` 가 아니다"
    assert int(m.group(1)) >= 148, f"값 130px + td 여백 18px 이 안 들어갑니다: {m.group(1)}px"
    assert int(m.group(1)) == WIDTH_PX


def test_접히지_않게_한_줄로_세운다():
    """`table-layout: fixed` 라, 칸이 조금만 좁아져도 빈칸 자리에서 접힌다."""
    css = CSS.read_text(encoding="utf-8")
    assert re.search(r"#co-table td\.updated-at\s*\{[^}]*white-space:\s*nowrap", css), \
        "`#co-table td.updated-at` 에 `white-space: nowrap` 이 없습니다"


def test_표_min_width_도_함께_올렸다():
    """안 올리면 폭을 안 준 `딜 소개 문구` 가 새 칸 폭을 통째로 내어 준다.

    이 표에서 제일 많이 읽는 칸이라 깎을 자리가 아니다 — `계약서 수신 여부` ·
    `소개 횟수` 를 세울 때 세운 규칙 그대로다(app.css 의 그 자리 주석).
    """
    css = CSS.read_text(encoding="utf-8")
    m = re.search(r"#co-table \{[^}]*min-width:\s*(\d+)px", css)
    assert m, "`#co-table` 의 min-width 를 못 찾았습니다"
    assert int(m.group(1)) >= 2386 + WIDTH_PX, (
        f"`{COLUMN}` {WIDTH_PX}px 이 들었는데 표 폭은 {m.group(1)}px 그대로입니다")


def test_오른쪽으로_미는_칸이_아니다():
    """이 표의 다른 날짜 칸(`미팅제공일자`)과 같은 자리에서 시작해야 한다.

    `num` 은 자릿수를 맞춰 읽는 **수**에 붙는다(`소개 횟수`·매출). 시각은
    자릿수가 늘 같아서 맞출 것이 없고, 혼자 오른쪽에 붙으면 세로로 훑을 때
    옆의 날짜 칸과 눈이 어긋난다.
    """
    markup = _status_tab_markup()
    head = re.search(r"<th([^>]*)>\s*" + COLUMN, markup)
    cell = re.search(r'<td class="updated-at[^"]*"', markup)
    assert head and cell
    assert "num" not in head.group(1), "머리글이 오른쪽 정렬입니다"
    assert "num" not in cell.group(0), "칸이 오른쪽 정렬입니다"
