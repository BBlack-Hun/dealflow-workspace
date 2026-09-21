"""스타트업 리마인드는 **석 달치**가 서고, 달이 넘어가면 새 달 칸이 저절로 생긴다.

사용자가 이렇게 적어 보냈다. 그대로 옮긴다.

  "스타트업도 3개월치 리마인드 메뉴가 나올 수 있고 다음달로 넘어가면 자동으로
   생성되게 해줘"

## 두 가지를 나눠 본다

**① 몇 달치를 보여 주는가** — 접기(`contact_columns.split_months`)가 정한다.
한동안 스타트업만 이번 달 하나였고 투자컨설턴트는 석 달이었다. 이제 달 수는
`services/monthly_columns.VISIBLE_MONTHS` **한 곳**이 정한다(두 표가 같은
숫자를 각자 적어 두면 한쪽만 고쳐지는 날 같은 화면에서 다른 달 수가 보인다 —
`tests/test_monthly_columns.py` 의 `test_두_표가_같은_달_수를_본다`).

**② 달이 넘어가면 새 칸이 생기는가** — 이 앱에는 예약 실행 장치가 없다.
그래서 "자동 생성" 은 **화면을 열 때 그 달 칸이 없으면 DB 에 만든다** 이다
(`services/monthly_columns.ensure_contact`). 그리는 순간에만 보이는 가짜 칸이
아니라 **줄이 실제로 생긴다** — 그래야 그 칸에 적은 메모가 갈 곳이 있다.
스타트업 명단은 배치가 심을 것을 정해 두어(`Layout.month_seed`) 달 칸이 하나도
없는 명단에도 선다.

## 접힌 달의 메모는 **지워지지 않는다**

접기는 표에 안 세우는 일일 뿐이다. 값은 `VcContact.notes` 에 그대로 있고,
`?months=all` 로 펴면 표에 다시 서며, 수정창은 접힌 달까지 **전부** 편다
(`contact_columns.panel_columns` 에 `routers/pages.py` 가 `all_months` 를 준다).
이것을 못 박아 두지 않으면 "안 보인다" 가 "지워졌다" 로 바뀌는 날이 온다.

이름·회사·번호는 전부 지어낸 값이다 — 저장소가 공개다.
"""
from __future__ import annotations

import re
from datetime import date
from urllib.parse import quote

import pytest

from .conftest import DEMO_PASSWORD

LIST = "샘플 스타트업(9)"

# 날짜를 **못 박는다.** 달이 넘어가는 것을 보려면 검사가 도는 날에 기대면 안
# 된다 — 9월 말에 돌리면 "다음 달" 이 실제로 와 버린다.
SEP = date(2026, 9, 8)
OCT = date(2026, 10, 1)         # 달이 막 넘어간 날

# 팀이 함께 쓰는 세 칸(`Layout.month_seed`). 한 달에 세 칸씩 붙는다.
WHAT = ("리마인드 문자", "리마인드 TEL", "카톡 연결")
SUFFIX = "(내용 기입)"          # 화면에만 붙는 꼬리말(`Layout.month_label_suffix`)

# 접힐 달(5월)에 적혀 있던 메모. **석 달 밖으로 밀려도 사라지면 안 된다.**
OLD_MEMO = "5/12 문자 발송\n5/14 통화 — 다음 달에 다시"
NEW_MEMO = "9/2 문자 발송\n9/5 부재중 — 다시 걸기로"

# 밑자리로 깔아 둘 달. 9월 기준으로 9·8·7 이 펴지고 6·5 가 접힌다.
SEEDED = (9, 8, 7, 6, 5)


# ── 밑자리 ──────────────────────────────────────────────────────────────────

def _labels(month: int) -> list:
    return [f"{month}월 {what}" for what in WHAT]


def _url(**q) -> str:
    from app.services import contact_columns as cc

    extra = "".join(f"&{k}={v}" for k, v in q.items())
    return f"/{cc.page_of(cc.STARTUP)}?sheet={quote(LIST)}{extra}"


def _thead(html: str) -> list:
    """그려진 표의 머리글 이름들."""
    m = re.search(r"<thead>(.*?)</thead>", html, re.S)
    assert m, "표 머리글을 찾지 못했습니다"
    out = []
    for _attrs, cell in re.findall(r"<th\b([^>]*)>(.*?)</th>", m.group(1), re.S):
        frag = re.sub(r'<div class="th-filters">\s*</div>', "", cell, flags=re.S)
        out.append(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", frag)).strip())
    return out


def _month_heads(heads: list) -> list:
    """머리글 중 **달마다 늘어나는 칸**만. 이름 앞의 `N월` 로 가른다.

    뒷말로 고르면 안 된다 — 붙박이 칸에도 같은 말이 선다(`카톡 연결 여부`).
    """
    return [h for h in heads if re.match(r"\d+월\s", h)]


def _months_in(heads: list) -> list:
    """머리글에 선 달 숫자. **선 차례 그대로**(중복은 턴다)."""
    out = []
    for h in _month_heads(heads):
        month = int(h.split("월")[0])
        if month not in out:
            out.append(month)
    return out


def _cols(db):
    """이 명단의 월별 칸 — `{이름: 줄}`. **읽기만** 한다(`create=False`).

    읽는 김에 만들어 버리면 밑자리를 깔다가 달 칸이 딸려 생긴다.
    """
    from sqlalchemy import select

    from app.models import ContactColumn

    rows = db.execute(
        select(ContactColumn).where(ContactColumn.sheet == LIST)
        .order_by(ContactColumn.position, ContactColumn.id)).scalars().all()
    return {c.label: c for c in rows}


@pytest.fixture()
def clock_at(monkeypatch):
    """시계를 못 박는 손잡이. 앱이 '지금' 을 읽는 자리는 하나다(`app/clock.py`).

    그 하나를 바꾸면 칸을 **세우는 쪽**(`monthly_columns`)과 **접는 쪽**
    (`contact_columns.split_months`)이 같은 날을 본다 — 두 쪽이 다른 날을 보면
    갓 선 칸이 선 그날 접힌다.
    """
    from app import clock

    def _set(day: date):
        monkeypatch.setattr(clock, "today", lambda: day)
        return day

    return _set


@pytest.fixture()
def startup(client, db, users, clock_at):
    """스타트업 명단 하나 — 다섯 달치 칸과, 접힐 달에 적힌 메모 한 줄."""
    from app.models import ContactColumn, SheetOwner, VcContact
    from app.services import contact_columns as cc

    clock_at(SEP)
    u1 = users["u1"]
    db.add(SheetOwner(label=LIST, user_id=u1.id, layout=cc.STARTUP, is_hidden=0))
    # 최근 달이 왼쪽이다 — 시트가 그렇고, [칸 추가] 도 늘 맨 앞에 세운다.
    pos = 0
    for month in SEEDED:
        for label in _labels(month):
            db.add(ContactColumn(sheet=LIST, label=label, position=pos))
            pos += 1
    db.flush()
    cols = _cols(db)

    db.add(VcContact(
        user_id=u1.id, source_sheet=LIST, name="김샘플1", firm="샘플기업1",
        phone="01000000101", email="sample1@example.com",
        notes=cc.dump_notes({
            cc.note_key(cols["9월 리마인드 문자"].id): NEW_MEMO,
            cc.note_key(cols["5월 리마인드 문자"].id): OLD_MEMO,
        })))
    db.commit()
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    return client


# ── ① 석 달치가 선다 ────────────────────────────────────────────────────────

def test_석_달치_리마인드_칸이_표에_선다(startup, db):
    """사용자 요청 그대로 — "3개월치 리마인드 메뉴가 나올 수 있고"."""
    from app.services import monthly_columns as mc

    heads = _thead(startup.get(_url()).text)
    assert _months_in(heads) == [9, 8, 7], (
        f"석 달치가 아닙니다: {_month_heads(heads)}")
    # 한 달의 칸은 **다 같이** 선다 — 칸 수로 자르면 달 중간이 잘린다.
    assert len(_month_heads(heads)) == 3 * mc.VISIBLE_MONTHS


def test_석_달치도_전부_메모_칸이다(startup, db):
    """o/x 가 아니다. **세 달치가 다** 2~3줄 적는 칸이어야 한다.

    새로 펴 준 두 달만 고르는 칸으로 서면, 그 달에 적어 둔 글이 한 번
    고치는 순간 한 글자로 덮인다(`Layout.month_kind` 주석이 든 그 사고다).
    """
    from app.services import contact_columns as cc

    body = startup.get(_url()).text
    for month in (9, 8, 7):
        for label in _labels(month):
            key = cc.note_key(_cols(db)[label].id)
            cell = re.search(r'<div class="cell[^>]*\bdata-field="'
                             + re.escape(key) + r'"[^>]*>', body)
            assert cell, f"{label} 이 표에 메모 칸으로 안 섰습니다"
            attrs = cell.group(0)
            assert 'data-type="long"' in attrs, \
                f"{label} 이 메모 칸이 아닙니다: {attrs}"
            assert "clamp2" in attrs, \
                f"{label} 이 두 줄 접는 칸이 아닙니다: {attrs}"
            assert "data-choices" not in attrs, \
                f"{label} 에 고를 거리가 붙었습니다 — 메모 칸이 아닙니다"


def test_수정한_날짜는_월별_묶음_바로_앞에_남는다(startup, db):
    """칸이 셋으로 늘어도 **그 자리는 안 밀린다.**

    월별 칸은 `head` 와 `tail` **사이**에 한 덩어리로 선다
    (`contact_columns.table_columns`). `수정한 날짜` 는 `head` 의 맨 끝이라,
    달이 몇 개가 서든 바로 뒤가 월별 묶음의 첫 칸이다. 이 자리를 잃으면
    "이 기록이 최근 것인가" 를 묻는 칸이 달 칸들 너머로 밀려난다.
    """
    heads = _thead(startup.get(_url()).text)
    at = heads.index("수정한 날짜")
    assert _month_heads(heads) == heads[at + 1:at + 1 + 9], (
        f"`수정한 날짜` 뒤가 월별 묶음이 아닙니다: {heads[at:at + 10]}")


# ── ② 달이 넘어가면 저절로 생긴다 ───────────────────────────────────────────

def test_달이_넘어가면_새_달_칸이_저절로_생긴다(startup, db, clock_at):
    """2026-09 → 2026-10. **예약 실행 장치가 없다** — 알아채는 자리는 요청뿐이다.

    그리는 순간에만 보이는 가짜 칸이 아니라 **DB 에 줄이 생긴다.** 그래야
    그 달에 적은 메모가 갈 곳이 있다(`notes` 의 열쇠가 열 id 다).
    """
    from app.services import monthly_columns as mc

    assert "10월 리마인드 문자" not in _cols(db), "밑자리에 이미 10월이 있습니다"

    clock_at(OCT)
    heads = _thead(startup.get(_url()).text)

    db.expire_all()
    made = _cols(db)
    for label in _labels(10):
        assert label in made, f"달이 넘어갔는데 칸이 안 생겼습니다: {label}"
    # 이름은 **직전 달 칸을 본떠** 짓는다(`monthly_columns.relabel`) — 꼬리말은
    # 화면에서만 붙으므로 저장된 이름에는 없다.
    for label in _labels(10):
        assert SUFFIX not in label

    # 표에는 새 달을 포함한 석 달이 선다. 7월은 이제 접힌다.
    assert _months_in(heads) == [10, 9, 8], _month_heads(heads)
    assert mc.VISIBLE_MONTHS == 3


def test_두_번_열어도_그_달_칸은_하나다(startup, db, clock_at):
    """같은 달이 두 칸이면 그 달 기록이 두 군데로 갈린다. 되돌릴 방법이 없다.

    세어 보고 넣는 방식으로는 못 막는다 — 막는 것은 `MonthlyColumnRun` 이다.
    """
    clock_at(OCT)
    startup.get(_url())
    startup.get(_url())
    db.expire_all()
    made = [label for label in _cols(db) if label.startswith("10월 ")]
    assert sorted(made) == sorted(_labels(10)), f"10월 칸이 겹쳤습니다: {made}"


def test_달이_두_번_넘어가도_따라간다(startup, db, clock_at):
    """10월에 선 칸을 본떠 11월이 선다 — 본이 되는 것은 **직전 달**이다."""
    clock_at(OCT)
    startup.get(_url())
    clock_at(date(2026, 11, 2))
    heads = _thead(startup.get(_url()).text)

    db.expire_all()
    for label in _labels(11):
        assert label in _cols(db), f"두 번째 달 넘김에서 빠졌습니다: {label}"
    assert _months_in(heads) == [11, 10, 9], _month_heads(heads)


# ── ③ 석 달 밖의 메모는 **안 사라진다** ─────────────────────────────────────

def test_접힌_달의_메모는_지워지지_않는다(startup, db):
    """접기는 **표에 안 세우는 일**이지 지우는 일이 아니다.

    화면을 여러 번 열어도(달이 넘어가 칸이 새로 서는 순간을 포함해서) 값은
    `VcContact.notes` 에 그대로 있어야 한다.
    """
    from app.models import VcContact
    from app.services import contact_columns as cc

    key = cc.note_key(_cols(db)["5월 리마인드 문자"].id)
    heads = _thead(startup.get(_url()).text)
    assert 5 not in _months_in(heads), "5월이 접히지 않았습니다 — 밑자리가 틀렸습니다"

    db.expire_all()
    row = db.query(VcContact).filter(VcContact.source_sheet == LIST).one()
    assert cc.load_notes(row.notes).get(key) == OLD_MEMO, \
        "접힌 달의 메모가 사라졌습니다"


def test_접힌_달의_메모는_수정창에서_그대로_보인다(startup, db):
    """표에서 접혀도 **적을 자리는 남아 있어야 한다.**

    수정창은 접힌 달까지 전부 편다(`panel_columns` 는 `all_months` 를 받는다).
    여기서도 빠지면 값은 DB 에 있는데 화면 어디에서도 볼 수 없는 칸이 된다 —
    사람은 지워진 줄 안다.
    """
    from app.services import contact_columns as cc

    key = cc.note_key(_cols(db)["5월 리마인드 문자"].id)
    body = startup.get(_url()).text
    assert f'data-note="{key}"' in body, \
        "접힌 달 칸이 수정창에 안 섰습니다 — 적을 자리가 없습니다"
    # 머리글은 **화면 이름**(꼬리말 포함)으로 선다 — 접혔다고 이름이 달라지지 않는다.
    assert f"5월 리마인드 문자{SUFFIX}" in body


def test_펴면_접힌_달이_표에_다시_선다(startup, db):
    """`?months=all` — 접었다는 것을 적고 **펴는 길을 남긴다.**

    그냥 안 보이면 지워진 줄 안다.
    """
    body = startup.get(_url()).text
    assert "펴기" in body, "접어 놓고 그 사실을 화면에 안 적었습니다"

    heads = _thead(startup.get(_url(months="all")).text)
    assert _months_in(heads) == list(SEEDED), _month_heads(heads)


def test_달이_넘어가도_접힌_달의_메모는_그대로다(startup, db, clock_at):
    """새 달 칸이 서면서 한 달이 더 접힌다. **접히는 것뿐이어야 한다.**"""
    from app.models import VcContact
    from app.services import contact_columns as cc

    keys = {label: cc.note_key(_cols(db)[label].id)
            for label in ("9월 리마인드 문자", "5월 리마인드 문자")}
    clock_at(OCT)
    heads = _thead(startup.get(_url()).text)
    assert 7 not in _months_in(heads), "달이 넘어갔는데 7월이 안 접혔습니다"

    db.expire_all()
    notes = cc.load_notes(
        db.query(VcContact).filter(VcContact.source_sheet == LIST).one().notes)
    assert notes.get(keys["9월 리마인드 문자"]) == NEW_MEMO
    assert notes.get(keys["5월 리마인드 문자"]) == OLD_MEMO
    # 다 펴면 다섯 달이 그대로 있다 — 지워진 칸이 없다.
    everything = _thead(startup.get(_url(months="all")).text)
    assert _months_in(everything) == [10] + list(SEEDED), _month_heads(everything)
