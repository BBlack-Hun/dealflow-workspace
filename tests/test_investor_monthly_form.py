"""**딜공유 명단을 투자사 명함 표로 맞추면서, 달마다의 기록을 잃지 않는가.**

담당자마다 쓰던 딜공유 시트는 `투자사 딜공유` 배치(월별 칸이 표에 서는 표)로
들어왔는데, 다른 명단들과 모양이 달라 나란히 보기가 어려웠다. 그래서 그 명단을
**투자사 명함 표**로 맞춘다.

그 순간 위험한 것이 하나 있다. 명함 표에는 월별 칸이 없다 — 표가 `contacts.html`
에 그대로 적혀 있고, 시트 컬럼 열여덟 개에 열다섯 칸을 더 붙이면 맞추라고 한 그
모양이 아니게 된다. 그런데 달마다의 딜공유 기록이 **그 명단의 핵심 내용**이라,
화면에서 사라지면 명단을 열었을 때 이름과 투자사명만 남는다. 지워지지 않았는데
사람은 지워진 줄 안다.

여기서 막는 것은 다섯 가지다.

  1. 맞춘 명단의 표가 **기준 명단의 표와 한 칸도 다르지 않은가**
  2. 달마다의 기록이 **수정창에 그대로 서고, 고치고, 다시 읽히는가**
  3. 채우기가 **줄을 만들지 않는가** (만들면 같은 사람이 두 줄이 된다)
  4. 두 번 돌려도 **줄도 칸도 늘지 않는가**
  5. 못 찾은 값이 **빈칸으로 남는가** (지어내지 않는다)

이름·회사·번호는 전부 지어낸 값이다 — 저장소가 공개다.
"""
from __future__ import annotations

import re

import pytest

from .conftest import DEMO_PASSWORD

# 원본 시트가 그렇듯 이름에 괄호와 숫자가 붙는다. **코드가 이 이름을 알면 안 된다.**
DEAL = "샘플 딜공유 명단(4)"
CARD = "샘플 명함 명단(2)"

# 시트 머리글 그대로. 한 달에 세 칸씩 붙는다.
MONTHS = ["8월 딜소개 8/5 8/12", "8월 IR 요청", "7월 딜소개"]


def _url(sheet: str, **q) -> str:
    from urllib.parse import quote

    extra = "".join(f"&{k}={v}" for k, v in q.items())
    return f"/contacts?sheet={quote(sheet)}{extra}"


def _thead(html: str) -> list:
    """그려진 표의 머리글. **정적 글자가 아니라 그려진 화면**을 본다."""
    m = re.search(r"<thead>(.*?)</thead>", html, re.S)
    assert m, "표 머리글을 찾지 못했습니다"
    return [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", cell)).strip()
            for _attrs, cell in re.findall(r"<th\b([^>]*)>(.*?)</th>", m.group(1), re.S)]


def _rows(html: str) -> list:
    return re.findall(r'<tr class="data-row[^"]*"[^>]*>(.*?)</tr>', html, re.S)


def _panel_notes(html: str) -> dict:
    """수정창의 `그 명단에만 있는 칸` — `{키: 라벨}`."""
    out = {}
    for block in re.findall(r'<label class="field[^"]*">(.*?)</label>', html, re.S):
        key = re.search(r'data-note="([^"]+)"', block)
        name = re.search(r"<span[^>]*>(.*?)</span>", block, re.S)
        if key and name:
            out[key.group(1)] = re.sub(r"\s+", " ", name.group(1)).strip()
    return out


@pytest.fixture()
def sheets(client, db, users):
    """딜공유 명단(달 칸 있음) + 명함 명단(달 칸 없음).

    **둘 다 투자사 명함 배치**로 세운다 — 이 파일이 보는 것이 그 상태다.
    달 칸이 있느냐 없느냐는 명단이 정하는 것이지 배치가 정하는 것이 아니다.
    """
    from app.models import ContactColumn, SheetOwner, VcContact
    from app.services import contact_columns as cc

    u1 = users["u1"]
    db.add_all([
        SheetOwner(label=DEAL, user_id=u1.id, layout=cc.INVESTOR, is_hidden=0),
        SheetOwner(label=CARD, user_id=u1.id, layout=cc.INVESTOR, is_hidden=0),
    ])
    for pos, label in enumerate(MONTHS):
        db.add(ContactColumn(sheet=DEAL, label=label, position=pos))
    db.flush()
    cols = {c.label: c for c in cc.month_columns(db, DEAL)}

    for i in range(1, 5):
        db.add(VcContact(
            user_id=u1.id, source_sheet=DEAL, name=f"김샘플{i}",
            firm=f"샘플투자{i}", connect_stage="connected", channel_kakao=1,
            notes=cc.dump_notes({cc.note_key(cols[MONTHS[0]].id): f"8/5 샘플가{i}",
                                 cc.note_key(cols[MONTHS[2]].id): f"7/1 샘플나{i}"})))
    for i in range(1, 3):
        db.add(VcContact(user_id=u1.id, source_sheet=CARD, name=f"박샘플{i}",
                         firm=f"샘플벤처스{i}", phone=f"0100000030{i}"))
    db.commit()
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    return client


# ── 1. 표가 기준 명단과 같은가 ──────────────────────────────────────────────

def test_달_칸이_있어도_표는_명함_명단과_한_칸도_다르지_않다(sheets):
    """**맞추라고 한 것이 이 모양이다.**

    달 칸을 표에 붙이면 값은 보이지만 그 순간 다른 표가 된다 — 나란히 놓고
    대조하려고 맞춘 것인데 맞춘 쪽만 열다섯 칸이 더 길어진다.
    """
    deal = _thead(sheets.get(_url(DEAL)).text)
    card = _thead(sheets.get(_url(CARD)).text)
    assert deal == card, (
        "달 칸이 있는 명단의 표가 명함 명단과 다릅니다:\n"
        f"  명함 {card}\n  딜공유 {deal}")
    for label in MONTHS:
        assert label not in deal, f"표에 달 칸 `{label}` 이 끼어들었습니다"


def test_머리글_수와_데이터_칸_수가_같다(sheets):
    """어긋나면 **그 뒤 칸이 전부 한 칸씩 밀린다** — 이 저장소가 오래 지켜 온 규칙."""
    for label in (DEAL, CARD):
        html = sheets.get(_url(label)).text
        heads = len(_thead(html))
        for i, row in enumerate(_rows(html)):
            cells = len(re.findall(r"<td\b", row))
            assert cells == heads, (
                f"{label} {i + 1}번째 줄: 머리글 {heads}칸 · 데이터 {cells}칸")


# ── 2. 달마다의 기록이 살아 있는가 ──────────────────────────────────────────

def test_표에서_뺀_달_칸이_수정창에_시트_이름_그대로_선다(sheets, db):
    """**여기가 그 값을 보는 유일한 자리다.** 빼면 화면에서 통째로 사라진다.

    칸 이름을 검사에 적어 두지 않는다 — 배치가 정한 것을 그대로 돌린다.
    """
    from app.services import contact_columns as cc

    layout = cc.layout_of(cc.INVESTOR)
    months = cc.month_columns(db, DEAL)
    keys = cc.note_keys(layout, months)
    assert keys, "이 배치에는 검사할 칸이 없습니다"

    notes = _panel_notes(sheets.get(_url(DEAL)).text)
    for column in cc.panel_columns(layout, months):
        assert notes.get(column.key) == column.label, (
            f"수정창에 `{column.label}` 칸이 없거나 이름이 다릅니다: {notes}")


def test_달_칸은_수정창에서_접지_않고_전부_편다(sheets, db):
    """표에서는 가로로 밀려 이번 달만 펴지만(`split_months`), 수정창은 세로로
    쌓이는 자리라 접을 이유가 없다. 접으면 지난달 기록을 볼 길이 없다."""
    from app.services import contact_columns as cc

    html = sheets.get(_url(DEAL)).text
    labels = set(_panel_notes(html).values())
    for column in cc.month_columns(db, DEAL):
        assert column.label in labels, f"`{column.label}` 이 수정창에서 접혔습니다"


def test_달_칸을_고쳐도_다른_달_기록이_사라지지_않는다(sheets, db):
    """스키마 · 저장 · 되읽기 · 화면 **네 곳이 다 맞아야** 한 칸이 산다."""
    from app.models import VcContact
    from app.services import contact_columns as cc

    keys = [cc.note_key(c.id) for c in cc.month_columns(db, DEAL)]
    who = db.query(VcContact).filter(VcContact.source_sheet == DEAL).first()
    before = cc.load_notes(who.notes)
    assert before, "밑자리에 달마다의 기록이 없습니다"

    res = sheets.patch(f"/api/contacts/{who.id}", json={"notes": {keys[1]: "8/6 샘플다"}})
    assert res.status_code == 200, res.text
    got = sheets.get(f"/api/contacts/{who.id}").json()["contact"]["notes"]
    assert got[keys[1]] == "8/6 샘플다"
    for key, value in before.items():
        assert got.get(key) == value, f"한 칸을 고쳤더니 `{key}` 가 사라졌습니다"


def test_달_칸을_고치고_지우는_도구줄이_그대로_있다(sheets):
    """표에 안 서는 배치라고 칸 관리까지 사라지면, 값은 보이는데 칸 이름을
    고치거나 지울 자리가 아예 없어진다."""
    html = sheets.get(_url(DEAL)).text
    assert "month-cols" in html, "달 칸 도구줄이 사라졌습니다"
    assert "/api/contacts/columns" in html, "[칸 추가] 가 사라졌습니다"

    # 달 칸이 없는 명단에는 나오지 않는다 — 없는 것을 관리하는 도구줄이다.
    assert "month-cols" not in sheets.get(_url(CARD)).text, (
        "달 칸이 없는 명함 명단에까지 도구줄이 붙었습니다")


def test_배치를_바꿔도_달마다의_기록은_한_칸도_안_사라진다(sheets, db):
    """**배치는 어디에 그릴지만 정한다.** 값은 줄의 `notes` 에, 칸은 따로 있다."""
    from app.models import SheetOwner, VcContact
    from app.services import contact_columns as cc

    def month_cells() -> dict:
        db.expire_all()
        keys = {cc.note_key(c.id) for c in cc.month_columns(db, DEAL)}
        return {c.id: {k: v for k, v in cc.load_notes(c.notes).items() if k in keys}
                for c in db.query(VcContact).filter(VcContact.source_sheet == DEAL)}

    before = month_cells()
    assert sum(len(v) for v in before.values()) == 8

    row = db.query(SheetOwner).filter(SheetOwner.label == DEAL).one()
    row.layout = cc.INVESTOR_MONTHLY
    db.commit()
    sheets.get(_url(DEAL))
    row.layout = cc.INVESTOR
    db.commit()
    sheets.get(_url(DEAL))

    assert month_cells() == before, "배치를 오가는 사이 달마다의 기록이 달라졌습니다"


def test_달_칸이_없는_명단에는_달_칸이_생기지_않는다(sheets, db):
    """명함만 있는 명단(기준 명단)을 여는 것만으로 칸이 서면 **기준이 흔들린다.**

    달 칸을 세우는 것은 원본 시트이지 달력이 아니다. 본뜰 칸이 없으면 아무것도
    만들지 않는다(`services/monthly_columns.py` 의 `plan`).
    """
    from app.models import ContactColumn

    sheets.get(_url(CARD))
    db.expire_all()
    assert db.query(ContactColumn).filter(ContactColumn.sheet == CARD).count() == 0
