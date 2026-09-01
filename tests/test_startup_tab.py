"""명단마다 다른 표 · 투자사로 세지 않는 명단 · 감춘 줄.

투자사 관리 현황에는 명단별 탭이 있는데, 그중 성격이 다른 명단이 섞여 있었다.
투자사 명함 칸(부서·직함·근무처 팩스·명함 등록일)을 그대로 쓰고 있어 대부분의
칸이 비었고, 그러면서 투자사 수에는 함께 세어져 있었다(전체 306명에 32명).

여기서 막는 것은 네 가지다.

  1. 명단이 정한 칸이 서는가 — 그리고 **다른 명단의 칸이 안 바뀌는가**
  2. 달마다 칸이 늘어나도 머리글 수 == 데이터 칸 수인가
  3. 감춘 명단·감춘 줄이 **세는 곳 전부**와 발송 대상에서 빠지는가
  4. 표에서 뺀 칸을 수정창에서 **실제로 저장하고 다시 읽을 수 있는가**

3번은 **화면을 손으로 적어 두지 않는다.** 세는 곳이 열대여섯 군데라, 목록을
적어 두면 화면이 하나 늘 때 넣는 것을 잊는 순간 그 화면만 아무 검사 없이
지나간다 — 숫자가 조용히 갈리는 부류라 아무도 눈치채지 못한다(예전에 투자사
관리 현황 117명 · 대시보드 123명으로 갈렸다). 그래서 앱에 등록된 화면 주소를
훑어 **전부** 연다.

이름·회사·번호는 전부 지어낸 값이다 — 저장소가 공개다.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from .conftest import DEMO_PASSWORD
from .test_ui_layout import _text_px

ROOT = Path(__file__).resolve().parent.parent

# 원본 시트가 그렇듯 이름에 괄호와 숫자가 붙는다. **코드가 이 이름을 알면 안 된다** —
# 아래 `test_명단_이름이_코드에_박혀_있지_않다` 가 그것을 지킨다.
LIST = "샘플 스타트업(9)"
OTHER = "샘플 투자사 20"

# 시트 머리글 그대로. 달마다 세 칸씩 늘어나는 부분은 따로 둔다.
# `계약여부` 는 **이메일 바로 뒤**다. 월별 칸 뒤에 두면 달이 쌓일수록 표
# 끝으로 밀려, 명단을 훑을 때 가로로 밀어야 닿는 자리가 된다.
HEAD = ["NO", "기업명", "성함", "연락처", "이메일", "계약여부"]

# **이번 달**로 만든다. 월별 칸은 이제 화면을 열 때 저절로 생기므로
# (`app/services/monthly_columns.py`), 지난달 이름으로 밑자리를 깔면 검사가
# 도는 달마다 화면이 달라진다 — 8월에는 8월 칸이 붙고 9월에는 9월 칸이 붙는다.
# 이번 달 칸이 이미 있으면 자동 생성은 아무것도 하지 않는다.
def _month(offset: int = 0) -> int:
    from app import clock

    return (clock.today().month - 1 + offset) % 12 + 1


MONTHS = [f"{_month()}월 리마인드 문자", f"{_month()}월 리마인드 TEL",
          f"{_month()}월 카톡 연결"]
TAIL = ["IR 자료 회신 여부",
        "메모 ( 통화내용 /  카톡내용  /  카톡답신내용)"]


def _same(text: str) -> str:
    """이름 대조는 **띄어쓰기를 눌러서** 한다.

    시트 머리글에는 칸 사이에 공백이 둘씩 들어간 자리가 있는데(`통화내용 /
    카톡내용`), HTML 은 이어진 공백을 한 칸으로 그린다 — 화면에서 읽히는 이름은
    같다. 원문은 원문대로 두고(시트와 나란히 놓고 복사할 수 있어야 한다),
    비교만 눌러서 한다.
    """
    return " ".join(text.split())


# ── 화면 읽기 ───────────────────────────────────────────────────────────────

def _thead(html: str) -> list:
    """그려진 표의 머리글 이름들. **정적 글자가 아니라 그려진 화면**을 본다."""
    m = re.search(r"<thead>(.*?)</thead>", html, re.S)
    assert m, "표 머리글을 찾지 못했습니다"
    return [_flat(cell) for _attrs, cell
            in re.findall(r"<th\b([^>]*)>(.*?)</th>", m.group(1), re.S)]


def _thead_cells(html: str) -> list:
    m = re.search(r"<thead>(.*?)</thead>", html, re.S)
    return re.findall(r"<th\b([^>]*)>(.*?)</th>", m.group(1), re.S)


def _rows(html: str) -> list:
    return re.findall(r'<tr class="data-row[^"]*"[^>]*>(.*?)</tr>', html, re.S)


def _flat(cell_html: str) -> str:
    frag = re.sub(r'<div class="th-filters">\s*</div>', "", cell_html, flags=re.S)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", frag)).strip()


def _layout_of(sheet: str) -> str:
    """이 명단이 쓰는 배치. 밑자리와 주소가 **같은 값**을 읽게 한다."""
    from app.services import contact_columns as cc

    return {LIST: cc.STARTUP, OTHER: cc.INVESTOR}[sheet]


def _home(sheet: str) -> str:
    """이 명단이 **사는 화면**.

    주소를 여기 적어 두지 않는다. 명단이 어느 화면에 서는지는 그 명단의
    배치가 정하는데(`Layout.page`), 검사만 옛 화면을 계속 보면 **새 화면이
    비어 있어도 통과한다** — 옮기다 만 상태를 그대로 넘긴다.
    """
    from app.services import contact_columns as cc

    return f"/{cc.page_of(_layout_of(sheet))}"


def _url(sheet: str, **q) -> str:
    from urllib.parse import quote

    extra = "".join(f"&{k}={v}" for k, v in q.items())
    return f"{_home(sheet)}?sheet={quote(sheet)}{extra}"


# ── 밑자리 ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def sheets(client, db, users):
    """성격이 다른 두 명단. 하나는 스타트업 배치, 하나는 지금까지의 투자사 표."""
    from app.models import ContactColumn, SheetOwner, VcContact
    from app.services import contact_columns as cc

    u1 = users["u1"]
    db.add_all([
        SheetOwner(label=LIST, user_id=u1.id, layout=_layout_of(LIST), is_hidden=1),
        SheetOwner(label=OTHER, user_id=u1.id, layout=_layout_of(OTHER), is_hidden=0),
    ])
    for pos, label in enumerate(MONTHS):
        db.add(ContactColumn(sheet=LIST, label=label, position=pos))
    db.flush()
    cols = {c.label: c for c in cc.month_columns(db, LIST)}

    # 스타트업 명단 3줄. 값은 시트처럼 자유 표기 그대로(`O`/`X`/빈칸).
    for i in range(1, 4):
        db.add(VcContact(
            user_id=u1.id, source_sheet=LIST, name=f"김샘플{i}",
            firm=f"샘플기업{i}", phone=f"0100000010{i}",
            email=f"sample{i}@example.com", memo=f"통화 메모 {i}",
            connect_stage="connected", channel_kakao=1,
            kakao_room_name=f"샘플기업{i} 대표님 방",
            notes=cc.dump_notes({
                "ir_reply": "O", "sector_major": "에듀테크",
                cc.note_key(cols[MONTHS[0]].id): "O",
            })))
    # 투자사 명단 2줄 — 이쪽 수가 흔들리면 안 된다.
    for i in range(1, 3):
        db.add(VcContact(
            user_id=u1.id, source_sheet=OTHER, name=f"박투자{i}",
            firm=f"샘플벤처스{i}", phone=f"0100000020{i}",
            connect_stage="connected", channel_kakao=1,
            kakao_room_name=f"박투자{i} 심사역 방"))
    db.commit()
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    return client


# ── 1. 명단이 정한 칸 ───────────────────────────────────────────────────────

def test_이_명단의_머리글은_원본_시트와_같다(sheets):
    """머리글 이름은 **시트 그대로**다.

    원본 시트를 쓰던 사람이 자기 칸을 찾을 수 있어야 한다. 한 글자라도 다르면
    시트와 나란히 놓고 대조할 때마다 "이게 그 칸인가" 를 멈춰서 확인해야 한다.
    """
    got = _thead(sheets.get(_url(LIST)).text)
    # 마지막 칸은 [수정] 단추 자리라 이름이 없다.
    want = [_same(t) for t in HEAD + MONTHS + TAIL]
    assert got[:-1] == want, (
        f"머리글이 시트와 다릅니다:\n  시트 {want}\n  화면 {got[:-1]}")


def test_다른_명단의_머리글은_한_칸도_안_바뀐다(sheets):
    """명단 하나에 칸을 붙이다가 **다른 명단의 표가 바뀌면** 안 된다.

    투자사 표는 시트에서 그대로 옮겨 온 것이고 매일 보는 화면이다.
    """
    got = _thead(sheets.get(_url(OTHER)).text)
    assert "이름" in got and "회사" in got and "명함 등록일" in got
    # 스타트업 명단에서만 쓰는 칸이 넘어오면 안 된다.
    for name in ("기업명", "성함", "IR 자료 회신 여부") + tuple(MONTHS):
        assert name not in got, f"투자사 표에 `{name}` 이 끼어들었습니다"


def test_머리글_수와_데이터_칸_수가_같다(sheets):
    """어긋나면 **그 뒤 칸이 전부 한 칸씩 밀린다.**

    이 저장소가 오래 지켜 온 규칙이다(tests/test_ui_layout.py). 달마다 칸이
    늘어나는 표라 특히 잘 어긋난다 — 머리글만 늘리고 데이터 칸을 안 늘리면
    이메일 자리에 메모가 찍힌다.
    """
    html = sheets.get(_url(LIST)).text
    heads = len(_thead(html))
    for i, row in enumerate(_rows(html)):
        cells = len(re.findall(r"<td\b", row))
        assert cells == heads, f"{i + 1}번째 줄: 머리글 {heads}칸 · 데이터 {cells}칸"


def test_칸을_하나_늘려도_머리글과_데이터_칸이_함께_늘어난다(sheets, db):
    """달이 바뀌면 칸이 옆에 붙는다. 한 달에 세 칸씩이다.

    고정 목록으로 짜 두면 매달 코드를 고치고 배포해야 한다. 화면에서 칸을
    세울 수 있어야 하고, 세운 칸이 **머리글과 데이터 양쪽에** 서야 한다.

    **같은 달** 이름으로 세운다. 접는 기준이 달이라, 다른 달 이름으로 세우면
    세우자마자 접혀서 머리글에 안 선다 — 이 검사가 보려는 것은 접기가 아니다.
    """
    label = f"{_month()}월 리마인드 카톡"
    before = len(_thead(sheets.get(_url(LIST)).text))
    sheets.post("/api/contacts/columns",
                data={"sheet": LIST, "label": label},
                follow_redirects=False)

    html = sheets.get(_url(LIST)).text
    heads = _thead(html)
    assert len(heads) == before + 1
    assert label in heads
    # 새 칸은 **맨 앞**이다 — 시트에서도 최근 달이 왼쪽이고, 지금 챙겨야 할
    # 달이 먼저 보여야 한다.
    assert heads.index(label) < heads.index(MONTHS[0])
    for row in _rows(html):
        assert len(re.findall(r"<td\b", row)) == len(heads)


def test_칸이_많아지면_접고_접었다는_것을_적는다(sheets, db):
    """그냥 안 보이면 **지워진 줄 안다.**

    한 해가 지나면 서른여섯 칸이 되어 가로로 밀어야 읽힌다. 접되, 몇 칸이
    접혔는지 적고 펼 수 있게 한다(투자컨설턴트 현황과 같은 방식).

    **자르는 기준은 달이다.** 칸 수로 자르면 한 달에 붙는 칸 수가 명단마다
    달라 달 중간이 잘린다 — `8월 리마인드 문자` 는 보이는데 `8월 카톡 연결` 은
    접혀 있는 표가 된다.
    """
    from app.services import contact_columns as cc

    from app.models import ContactColumn

    # 밑자리에 이번 달 세 칸(자리 0~2)이 있다. 지난 두 달을 **그 오른쪽에** 둔다 —
    # 시트도 최근 달이 왼쪽이다. (화면의 [칸 추가] 는 늘 맨 앞에 세우므로
    # 지난달을 그것으로 만들면 순서가 뒤집힌다.)
    pos = 3
    for back in (1, 2):
        for what in ("리마인드 문자", "리마인드 TEL", "카톡 연결"):
            db.add(ContactColumn(sheet=LIST, label=f"{_month(-back)}월 {what}",
                                 position=pos))
            pos += 1
    db.commit()
    html = sheets.get(_url(LIST)).text
    months = [h for h in _thead(html) if "리마인드" in h or "카톡 연결" in h]
    # 이번 달 세 칸만 편다 — 한 달의 칸은 **다 같이** 서거나 다 같이 접힌다.
    assert len(months) == 3, f"펴 둔 칸이 이번 달 세 칸이 아닙니다: {months}"
    assert all(f"{_month()}월" in h for h in months), months
    assert cc.VISIBLE_MONTHS == 1
    assert "펴기" in html, "접어 놓고 그 사실을 화면에 적지 않았습니다"

    everything = _thead(sheets.get(_url(LIST, months="all")).text)
    assert len([h for h in everything
                if "리마인드" in h or "카톡 연결" in h]) == 9


def test_머리글은_필터_단추까지_한_줄에_들어간다(sheets):
    """값을 고르면 라벨 뒤에 `(1) ▾` 가 붙어 24px 이 더 든다.

    안 재고 이름 길이로만 폭을 잡아 두면, 화면에서는 멀쩡하다가 **필터를 거는
    순간** 칸이 두 줄로 접혀 머리글 줄이 들쭉날쭉해진다.

    이 표의 머리글은 반복문으로 세워서 `tests/test_ui_layout.py` 의 정적 검사가
    건너뛴다 — 같은 자로 **그려진 화면**을 잰다.
    """
    html = sheets.get(_url(LIST)).text
    problems = []
    for attrs, cell in _thead_cells(html):
        px = re.search(r"width:\s*(\d+)px", attrs)
        if not px:
            continue
        filters = re.findall(r'data-filters="[^:"]*:([^"]*)"', attrs)
        # 필터가 하나뿐인 칸은 이름이 지워지고 단추가 그 자리에 선다.
        shown = ([(label + " (1) ▾", 14) for label in filters]
                 if filters else [(_flat(cell), 0)])
        for text, extra in shown:
            if not text:
                continue
            need = round(_text_px(text) + 18 + extra)
            if need > int(px.group(1)):
                problems.append(f"{text} ({px.group(1)}px → {need}px 필요)")
    assert not problems, ("머리글이 두 줄로 접힙니다. 칸 폭을 넓히세요:\n  "
                          + "\n  ".join(problems))


# ── 2. 표에서 뺀 칸 — 네 곳이 다 맞아야 한다 ────────────────────────────────

def test_표에서_뺀_칸도_수정창에_서고_저장되고_다시_읽힌다(sheets, db):
    """스키마 · 저장 · 되읽기 · 화면 **네 곳이 다 맞아야** 한 칸이 산다.

    하나만 빠져도 증상이 조용하다 — PATCH 는 200 을 주는데 아무것도 안 들어가거나,
    저장은 되는데 다시 열면 빈칸이다(예전에 `kakao_joined` 가 그랬다).

    **칸 이름을 여기 적어 두지 않는다.** 배치가 정한 것을 그대로 돌린다 —
    적어 두면 칸이 하나 늘 때 여기 넣는 것을 잊고, 그 칸만 검사 없이 지나간다.
    """
    from app.models import VcContact
    from app.services import contact_columns as cc

    layout = cc.layout_of(cc.STARTUP)
    months = cc.month_columns(db, LIST)
    keys = cc.note_keys(layout, months)
    assert keys, "이 배치에는 검사할 칸이 없습니다"

    html = sheets.get(_url(LIST)).text
    contact = db.query(VcContact).filter(VcContact.source_sheet == LIST).first()

    # (1) 화면 — 수정창에 그 칸이 **이름 그대로** 서 있는가
    labels = {c.key: c.label for c in cc.panel_columns(layout, months)}
    for key in keys:
        assert f'data-note="{key}"' in html, f"수정창에 `{labels[key]}` 칸이 없습니다"
        assert labels[key] in html, f"수정창의 `{key}` 칸에 시트 이름이 안 붙었습니다"

    # (2) 스키마 + (3) 저장 — 한 번에 보내서 실제로 들어가는가
    sent = {key: f"값{i}" for i, key in enumerate(keys)}
    res = sheets.patch(f"/api/contacts/{contact.id}", json={"notes": sent})
    assert res.status_code == 200, res.text

    # (4) 되읽기 — 다시 열었을 때 창을 채울 값이 오는가
    got = sheets.get(f"/api/contacts/{contact.id}").json()["contact"]["notes"]
    for key, value in sent.items():
        assert got.get(key) == value, f"`{labels[key]}` 가 되읽기에서 빠졌습니다"

    # 한 칸만 고쳐 보내도 **나머지 달의 기록이 살아 있어야** 한다.
    sheets.patch(f"/api/contacts/{contact.id}", json={"notes": {keys[0]: "바뀐값"}})
    got = sheets.get(f"/api/contacts/{contact.id}").json()["contact"]["notes"]
    assert got[keys[0]] == "바뀐값"
    for key in keys[1:]:
        assert got.get(key) == sent[key], f"한 칸을 고쳤더니 `{labels[key]}` 가 사라졌습니다"


def test_금액과_비율은_적힌_그대로_남는다(sheets, db):
    """`2.5%` 를 `0.025` 로, `900,000` 을 `900000` 으로 고쳐 쓰지 않는다.

    계약서에 적힌 말이라 앱이 다듬을 것이 아니다.
    """
    from app.models import VcContact

    contact = db.query(VcContact).filter(VcContact.source_sheet == LIST).first()
    raw = {"success_fee": "2.5%", "contract": "미계약", "company_kind": "Angel, Seed (누적투자금 0)"}
    sheets.patch(f"/api/contacts/{contact.id}", json={"notes": raw})
    got = sheets.get(f"/api/contacts/{contact.id}").json()["contact"]["notes"]
    for key, value in raw.items():
        assert got[key] == value


# ── 3. 감춘 명단 — 세는 곳을 전수로 훑는다 ──────────────────────────────────

def _screens(client) -> dict:
    """앱이 등록한 **HTML 화면 전부**. 손으로 적어 두지 않는다.

    화면이 하나 늘 때 목록에 넣는 것을 잊으면, 그 화면만 아무 검사도 없이
    지나간다 — 숫자가 조용히 갈리는 부류라 아무도 눈치채지 못한다.
    """
    from app.main import create_app

    out = {}
    for route in create_app().routes:
        path = getattr(route, "path", "")
        methods = getattr(route, "methods", set()) or set()
        if "GET" not in methods or "{" in path or path.startswith("/api"):
            continue
        if path in ("/health", "/login", "/logout", "/password"):
            continue
        res = client.get(path)
        if res.status_code == 200 and "<table" in res.text or res.status_code == 200:
            out[path] = res.text
    return out


def test_감춘_명단_사람은_어느_화면의_투자사_수에도_안_들어간다(sheets, db):
    """세는 곳이 열대여섯 군데다 — **한 곳만 고치면 화면마다 숫자가 달라진다.**

    실제로 투자사 관리 현황 117명 · 대시보드 123명으로 갈린 적이 있다.
    그래서 앱에 등록된 화면을 전부 열어 **그 사람들의 이름이 아예 안 보이는지**
    본다. 수를 화면마다 다르게 읽는 것보다 이 편이 새 화면까지 저절로 덮는다.

    그 명단 탭에서는 그대로 보여야 한다 — 감추기는 지우기가 아니다.
    """
    from app.models import VcContact

    hidden_names = {c.name for c in db.query(VcContact)
                    .filter(VcContact.source_sheet == LIST).all()}
    assert hidden_names

    # **자기 화면은 뺀다.** 이 명단이 사는 화면에서는 보여야 한다(감추기는
    # 지우기가 아니다). 어느 화면인지 여기 적지 않는다 — 명단의 배치가 정하는
    # 값을 그대로 읽으므로, 명단이 화면을 옮겨도 이 검사가 따라간다.
    home = _home(LIST)
    leaked = []
    for path, html in _screens(sheets).items():
        if path == home:
            continue
        for name in hidden_names:
            if name in html:
                leaked.append(f"{path} 에 `{name}` 이 보입니다")
    assert not leaked, ("투자사로 세지 않기로 한 명단이 다른 화면에 새고 있습니다 "
                        "— 그 화면의 수가 그만큼 부풀어 있습니다:\n  "
                        + "\n  ".join(leaked))

    # 자기 화면에서는 그대로 보인다 — 탭을 안 고르고 들어와도 보여야 한다.
    # (거기서도 안 보이면 옮기는 것이 아니라 잃어버린 것이다.)
    for url in (home, _url(LIST)):
        own = sheets.get(url).text
        for name in hidden_names:
            assert name in own, (
                f"{url} 에서 감춘 명단이 사라졌습니다 — 지우기가 아닙니다")

    # 그 화면이 **남의 명단까지 끌어오지는 않는다.** 투자사 줄이 섞이면 거기서
    # 고친 값이 어느 명단 것인지 알 수 없다.
    others = {c.name for c in db.query(VcContact)
              .filter(VcContact.source_sheet == OTHER).all()}
    home_html = sheets.get(home).text
    for name in others:
        assert name not in home_html, f"{home} 에 투자사 명단 `{name}` 이 섞였습니다"


def test_감춘_명단_사람은_발송_대상에_안_나온다(sheets, db):
    """안 보이는 사람에게 문구가 나가면 안 된다.

    목록에 안 뜨는 것만으로는 모자라다 — 오래된 탭에 남아 있던 체크박스로도
    id 는 들어오고, 그때는 되돌릴 수가 없다. **보내기 직전에도** 막는다.
    """
    from app.models import VcContact
    from app.routers.deals import _load_recipients

    rows = db.query(VcContact).filter(VcContact.source_sheet == LIST).all()
    ids = [c.id for c in rows]

    html = sheets.get("/deals").text
    for c in rows:
        assert c.name not in html, "감춘 명단이 발송 대상 목록에 떠 있습니다"

    from app.models import User

    picked = _load_recipients(db, db.get(User, 1), "kakao", ids)
    assert picked == [], "목록에는 없는데 보내기는 됩니다 — 오발송으로 이어집니다"


def test_감춘_명단에서_내_명단으로_퍼오지_못한다(sheets, db, users):
    """단추 한 번으로 방금 빼 둔 것이 되돌아오면 안 된다.

    담당이 없는 명단은 모두 '풀' 로 잡혀서 [내 명단으로 할당] 이 붙는다.
    투자사가 아닌 명단까지 그렇게 두면, 골라서 내 명단에 더하는 순간 그
    사람들이 투자사 수에 다시 들어오고 발송 대상에도 뜬다.

    화면에서 단추를 감추는 것만으로는 모자라다 — id 를 직접 보내는 길이 남는다.
    """
    from app.models import SheetOwner, VcContact

    db.add(SheetOwner(label="내 투자사 명단", user_id=users["u1"].id))
    db.commit()
    ids = [c.id for c in db.query(VcContact)
           .filter(VcContact.source_sheet == LIST).all()]

    res = sheets.post("/api/contacts/assign",
                      json={"contact_ids": ids, "label": "내 투자사 명단"})
    assert res.status_code == 400, "감춘 명단에서 퍼올 수 있습니다"
    db.expire_all()
    assert all(db.get(VcContact, i).source_sheet == LIST for i in ids)

    # 화면에도 그 단추가 없어야 한다 — 있는데 눌러서 실패하면 왜인지 알 수 없다.
    assert 'id="assign-bar"' not in sheets.get(_url(LIST)).text


def test_숨김을_되돌리면_원래대로_돌아온다(sheets, db, users):
    """감춰 놓고 켜는 자리까지 감추면 DB 를 직접 고쳐야 한다."""
    from app.models import SheetOwner, VcContact

    names = {c.name for c in db.query(VcContact)
             .filter(VcContact.source_sheet == LIST).all()}
    before = _count(sheets)

    # 관리자만 바꿀 수 있다 — 감추면 다른 팀원 화면의 숫자까지 함께 바뀐다.
    assert sheets.post("/api/contacts/sheets/hide", data={"label": LIST},
                       follow_redirects=False).status_code == 403
    users["u1"].role = "admin"
    db.commit()

    sheets.post("/api/contacts/sheets/hide", data={"label": LIST},
                follow_redirects=False)
    db.expire_all()
    assert db.query(SheetOwner).filter(SheetOwner.label == LIST).one().is_hidden == 0
    assert _count(sheets) == before + len(names), "숨김을 풀어도 수가 안 늘었습니다"
    # 숨김을 풀면 **발송 대상에도 돌아와야** 한다. 수만 돌아오고 목록이 그대로면
    # 화면에는 투자사로 잡히는데 보낼 수는 없는, 더 헷갈리는 상태가 된다.
    assert names <= set(_names(sheets.get("/deals").text)), (
        "수는 돌아왔는데 발송 대상 목록에는 없습니다")

    sheets.post("/api/contacts/sheets/hide", data={"label": LIST},
                follow_redirects=False)
    assert _count(sheets) == before, "다시 감췄는데 수가 안 줄었습니다"
    assert not (names & set(_names(sheets.get("/deals").text))), (
        "다시 감췄는데 발송 대상에 남아 있습니다")


def _count(client) -> int:
    """`전체` 탭에 적히는 투자사 수."""
    html = client.get("/contacts?sheet=all").text
    return int(re.search(r"data-filter-count>(\d+) /", html).group(1))


def _names(html: str) -> list:
    return re.findall(r'data-name="([^"]*)"', html)


# ── 4. 감춘 줄 ──────────────────────────────────────────────────────────────

def test_줄을_감추면_표와_발송_대상에서_함께_빠진다(sheets, db, users):
    """원본 시트가 17~32번 줄을 숨긴 채로 돌아다녔다.

    그래서 시트 이름은 `…(16)` 인데 실제 줄은 서른둘이었고, 열여섯 줄만 보고
    "없는 기업" 이라고 판단한 일이 있었다. 같은 조작을 앱에도 두되 **되돌리는
    길이 화면에 보여야** 한다.
    """
    from app.models import VcContact

    row = db.query(VcContact).filter(VcContact.source_sheet == OTHER).first()
    before_rows = len(_rows(sheets.get(_url(OTHER)).text))
    before_send = len(_names(sheets.get("/deals").text))

    assert sheets.patch(f"/api/contacts/{row.id}",
                        json={"is_hidden": 1}).status_code == 200

    html = sheets.get(_url(OTHER)).text
    assert len(_rows(html)) == before_rows - 1, "감췄는데 표에 그대로 있습니다"
    assert row.name not in html
    assert len(_names(sheets.get("/deals").text)) == before_send - 1, (
        "표에서 안 보이는 사람이 발송 대상에는 남아 있습니다")

    # **몇 줄을 감췄는지와 되돌리는 길이 화면에 보여야 한다.**
    assert "감춘 줄" in html, "감춘 줄이 있다는 것이 화면에 안 적혀 있습니다"
    assert "hidden=1" in html, "감춘 줄을 다시 볼 길이 화면에 없습니다"

    shown = sheets.get(_url(OTHER, hidden=1)).text
    assert row.name in shown, "되돌리는 길로 들어가도 안 보입니다"

    sheets.patch(f"/api/contacts/{row.id}", json={"is_hidden": 0})
    assert len(_rows(sheets.get(_url(OTHER)).text)) == before_rows


def test_감춘_줄은_투자사_수에서도_빠진다(sheets, db):
    """표에서 안 보이는 사람이 수에는 들어가 있으면, 세어 보고 찾을 수가 없다."""
    from app.models import VcContact

    row = db.query(VcContact).filter(VcContact.source_sheet == OTHER).first()
    before = _count(sheets)
    sheets.patch(f"/api/contacts/{row.id}", json={"is_hidden": 1})
    assert _count(sheets) == before - 1
    sheets.patch(f"/api/contacts/{row.id}", json={"is_hidden": 0})
    assert _count(sheets) == before


# ── 5. 이름을 코드가 알면 안 된다 ───────────────────────────────────────────

def test_명단_이름이_코드에_박혀_있지_않다():
    """`if 이름 == "…"` 를 심으면 다음 명단에서 또 심어야 한다.

    심는 것을 잊은 화면만 조용히 옛 동작을 하고, 화면은 멀쩡해 보인다.
    무엇을 감출지·어떤 표로 세울지는 **사람이 화면에서 정한 값**이 정한다.

    주석은 본다 — 주석에 예로 적는 것은 동작이 아니다. Jinja 주석(`{# … #}`)도
    그려지지 않으므로 뺀다.
    """
    # 원본 시트의 명단 이름들. 하나라도 소스에 박혀 있으면 안 된다.
    banned = ["스타트업(16)", "투자사 150", "투자사 98명", "투자사 30명",
              "전체 딜소개현황"]
    hits = []
    # **돌아가는 앱**(app/)과 명단을 다루는 스크립트를 본다. 이름 고치기
    # (`rename_sheets.py`)도 여기 든다 — 예전에는 옛 이름 → 새 이름 표를 그
    # 파일 안에 적어 두고 돌렸지만, 그 표는 한 번 돌리면 지난 일인데 파일에는
    # 남아서 다음 사람이 지우는 것을 잊으면 한 번 더 돈다. 지금은 부르는
    # 사람이 인자로 준다.
    targets = (list((ROOT / "app").rglob("*.py"))
               + list((ROOT / "app" / "static" / "js").glob("*.js"))
               + [ROOT / "scripts" / "import_startup_sheet.py",
                  ROOT / "scripts" / "import_new_list.py",
                  ROOT / "scripts" / "rename_sheets.py"])
    for path in targets:
        if "__pycache__" in str(path):
            continue
        body = _strip_comments(path.read_text(encoding="utf-8"))
        for name in banned:
            if name in body:
                hits.append(f"{path.relative_to(ROOT)} 에 `{name}`")
    for path in (ROOT / "app" / "templates").glob("*.html"):
        body = re.sub(r"\{#.*?#\}", "", path.read_text(encoding="utf-8"), flags=re.S)
        for name in banned:
            if name in body:
                hits.append(f"{path.relative_to(ROOT)} 에 `{name}`")
    assert not hits, ("명단 이름이 코드에 박혀 있습니다 — 다음 명단에서 또 "
                      "심어야 하고, 잊은 곳만 조용히 틀립니다:\n  " + "\n  ".join(hits))


def _strip_comments(src: str) -> str:
    """주석과 docstring 을 걷어낸 실제 코드.

    설명하려고 예로 적어 둔 이름까지 '박혀 있다'고 세면, 주석을 다는 것만으로
    검사가 깨진다 — 그러면 주석을 안 달게 된다.
    """
    src = re.sub(r'"""(?:.|\n)*?"""', "", src)
    src = re.sub(r"'''(?:.|\n)*?'''", "", src)
    src = re.sub(r"^\s*#.*$", "", src, flags=re.M)
    src = re.sub(r"//.*$", "", src, flags=re.M)
    return src


def test_투자사로_세는지는_한_곳에서만_판정한다():
    """판정을 두 벌로 적어 두면 화면마다 다른 수가 나온다.

    투자사 관리 현황 117명 · 대시보드 123명 사고가 그 부류였다. 세거나 보내는
    곳은 모두 `sheet_owner` 의 판정 하나를 지나야 한다.
    """
    import inspect

    from app.services import sheet_owner

    src = inspect.getsource(sheet_owner)
    assert "def is_investor" in src and "def investors" in src

    # 직접 담당자를 긁어 가는 곳은 그 판정을 지나야 한다.
    from app.routers import deals, pages
    from app.services import dashboard, sourcing_link

    # 담당자를 **직접 긁어 가는** 곳은 그 판정을 지나야 한다. `my_contacts` 를
    # 거치는 곳은 그 안에서 이미 걸러진다 — 놓치기 쉬운 것은 직접 긁는 쪽이다.
    for module in (pages, deals, dashboard, sourcing_link):
        body = inspect.getsource(module)
        if "select(VcContact)" not in body:
            continue
        assert "sheet_owner.investors" in body, (
            f"{module.__name__} 이 담당자를 직접 긁어 가면서 판정을 안 지납니다")


def test_딜소개를_보내는_명단인지도_한_곳에서만_판정한다():
    """**발송 대상의 모집단**도 같은 규칙이다.

    딜 제안 관리와 대시보드가 각자 모집단을 고르던 동안, 한쪽은 풀까지 세고
    한쪽은 안 세어서 같은 사람을 두고 다른 수가 나왔다. 그리고 판정을 명단
    **이름**으로 하면 이름에 붙은 인원(`…(125명)`)이 바뀌는 날 조용히 깨진다.
    """
    import inspect

    from app.services import sheet_owner

    src = inspect.getsource(sheet_owner)
    for fn in ("def is_deal_list", "def off_deal_labels", "def on_deal_list",
               "def deal_list_contacts"):
        assert fn in src, f"{fn} 가 sheet_owner 에 없습니다"

    # 발송 대상을 세는 곳은 모두 그 판정을 지난다 — 자기 질의를 따로 들지 않는다.
    #
    # **`연결 완료` 인지 견주는 것만** 본다. 어느 단계인지 나누는 비교
    # (`== STAGE_IN_PROGRESS`)는 그 단계별로 세라고 있는 것이라 괜찮다.
    # 여기서 막으려는 것은 "보낼 수 있는가" 를 두 번째로 적어 두는 일이다.
    from app.routers import pages
    from app.services import dashboard, readiness

    for module in (pages, dashboard, readiness):
        body = inspect.getsource(module)
        for said in ('== STAGE_CONNECTED', '== "connected"', "== 'connected'"):
            assert said not in body, (
                f"{module.__name__} 이 연결 완료를 직접 견줍니다({said}) — "
                "`sheet_owner.can_send_to` 를 지나야 합니다")
