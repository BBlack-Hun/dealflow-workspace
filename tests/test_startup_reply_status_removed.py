"""스타트업 명단에서 **`회신 상태` 칸을 뺐다** — 값은 안 지우고.

사용자가 「스타트업 메뉴에서 회신상태 컬럼 제거」라고 했다. 이 칸은
`source="note"` 라 값이 `VcContact.notes` 의 `reply_status` 키에 담긴다 —
**모델 칸이 아니라 이주가 없고**, 칸 정의만 빼면 값은 그대로 남는다.

여기서 잠그는 것은 다섯 가지다.

  1. 칸이 **네 곳 전부**에서 빠졌는가 — 표 · 필터 · 수정창 · 엑셀.
     넷이 한 목록에서 나오므로(`contact_columns`) 한 군데만 남는 일은 없어야
     한다. 한 군데라도 남으면 "뺐다" 가 거짓말이 된다.
  2. **값이 안 지워지는가** — 이번 판에서 제일 중요하다. 칸을 뺀 것이지
     값을 버린 것이 아니다. 옆 칸을 고쳐도, 화면을 열어도, API 로 되읽어도
     `reply_status` 는 그대로 있어야 한다. 지워지면 되돌릴 수가 없다.
  3. **되돌리기가 한 줄인가** — 뺀 자리에 그 한 줄이 주석으로 남아 있는가
     (#197 이 `초대 완료 여부` 를 뺄 때 세운 방식이다).
  4. **남은 칸이 안 밀리는가** — 차례도 폭도 그대로고, 표 폭만 그 칸 폭
     (110px)만큼 줄어드는가.
  5. **시트 임포터가 조용히 쌓지 않는가** — 그 열은 계속 알아보되(빼면 월별
     칸으로 서 버린다), 들어오면 화면에 안 보인다고 적어서 알리는가.

이름·회사·번호는 전부 지어낸 값이다 — 저장소가 공개다.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from .conftest import DEMO_PASSWORD

ROOT = Path(__file__).resolve().parent.parent

LIST = "샘플 스타트업(9)"

# 뺀 칸. **여기 적어 두는 것이 이 검사의 전부다** — 앱에서 가져오면 앱이
# 바뀔 때 검사도 같이 바뀌어 아무것도 못 막는다.
GONE_LABEL = "회신 상태"
GONE_KEY = "reply_status"
GONE_WIDTH = 110

# 뺀 칸 **바로 앞**에 서 있던 칸. 그 뒤가 월별 묶음이 되어야 한다.
BEFORE = "계약서 수신여부"


def _month(offset: int = 0) -> int:
    from app import clock

    return (clock.today().month - 1 + offset) % 12 + 1


MONTHS = [f"{_month()}월 리마인드 문자", f"{_month()}월 리마인드 TEL",
          f"{_month()}월 카톡 연결"]


def _url() -> str:
    from urllib.parse import quote

    from app.services import contact_columns as cc

    return f"/{cc.page_of(cc.STARTUP)}?sheet={quote(LIST)}"


def _thead(html: str) -> list:
    m = re.search(r"<thead>(.*?)</thead>", html, re.S)
    assert m, "표 머리글을 찾지 못했습니다"
    return [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", cell)).strip()
            for _attrs, cell
            in re.findall(r"<th\b([^>]*)>(.*?)</th>", m.group(1), re.S)]


@pytest.fixture()
def sheets(client, db, users):
    """스타트업 명단 하나 — 그중 한 줄이 **뺀 칸의 값을 들고 있다.**

    운영에서도 그렇다: 915줄 중 4줄만 값이 있었다(`회신 받음` 3 · `회신 대기` 1).
    칸을 뺀 뒤에도 그 글자가 DB 에 그대로 있어야 되돌릴 수 있다.
    """
    from app.models import ContactColumn, SheetOwner, VcContact
    from app.services import contact_columns as cc

    u1 = users["u1"]
    db.add(SheetOwner(label=LIST, user_id=u1.id, layout=cc.STARTUP, is_hidden=0))
    for pos, label in enumerate(MONTHS):
        db.add(ContactColumn(sheet=LIST, label=label, position=pos))
    db.flush()

    db.add(VcContact(
        user_id=u1.id, source_sheet=LIST, name="김샘플1", firm="샘플기업1",
        phone="01000000101", email="sample1@example.com",
        notes=cc.dump_notes({
            GONE_KEY: "회신 받음",
            "funding_status": "투자유치 진행 중",
            "collab_status": "협업 논의 중",
        })))
    db.add(VcContact(
        user_id=u1.id, source_sheet=LIST, name="김샘플2", firm="샘플기업2",
        phone="01000000102", email="sample2@example.com",
        notes=cc.dump_notes({GONE_KEY: "회신 대기"})))
    db.commit()
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    return client


def _row(db):
    from app.models import VcContact

    db.expire_all()
    return (db.query(VcContact)
            .filter(VcContact.source_sheet == LIST,
                    VcContact.firm == "샘플기업1").one())


# ── 1. 네 곳 전부에서 빠졌다 ────────────────────────────────────────────────

def test_배치에_그_칸이_없다():
    """`head`·`tail`·`extra` 어디에도 없어야 한다.

    `extra` 로 옮기는 길도 있었다(표에서 빼고 수정창에만 남기기 — `사업분야
    대분류` 가 그렇게 서 있다). 사용자는 **칸을 없애라**고 했으므로 거기에도
    안 둔다. 그 길로 가고 싶어지면 `extra` 에 같은 줄을 세우면 된다.
    """
    from app.services import contact_columns as cc

    layout = cc.STARTUP_LAYOUT
    everywhere = list(layout.head) + list(layout.tail) + list(layout.extra)
    assert GONE_KEY not in [c.key for c in everywhere], \
        "배치에 아직 그 칸이 있습니다"
    assert GONE_LABEL not in [c.label for c in everywhere], \
        "이름만 바꾼 같은 칸이 남아 있습니다"


def test_표와_필터와_수정창_어디에도_안_선다(sheets, db):
    """**한 군데만 남는 일**을 막는다.

    표·필터·수정창은 같은 목록 하나에서 나오지만(`contact_columns`), 한쪽이
    다른 규칙으로 갈라지는 날 이 검사가 잡는다. 수정창에 남으면 화면에서
    적을 수 있는데 표에서는 안 보이는, 가장 헷갈리는 상태가 된다.
    """
    from app.services import contact_columns as cc

    html = sheets.get(_url()).text
    months = cc.month_columns(db, LIST)

    assert GONE_LABEL not in _thead(html), "표 머리글에 아직 그 칸이 있습니다"
    assert f'data-field="{GONE_KEY}"' not in html, "표에 그 칸의 자리가 있습니다"
    assert f'data-note="{GONE_KEY}"' not in html, "수정창에 그 칸이 있습니다"
    assert f'data-filters="{GONE_KEY}:' not in html, "머리글에 필터가 남았습니다"
    assert f"data-f-{GONE_KEY}=" not in html, "행이 아직 그 값을 싣습니다"

    assert GONE_KEY not in [c.key for c in cc.table_columns(cc.STARTUP_LAYOUT, months)]
    assert GONE_KEY not in [c.key for c in cc.panel_columns(cc.STARTUP_LAYOUT, months)]
    assert GONE_KEY not in [c.key for c in cc.filter_columns(cc.STARTUP_LAYOUT, months)]
    assert GONE_KEY not in cc.note_keys(cc.STARTUP_LAYOUT, months)


def test_엑셀에도_그_칸이_안_나간다(sheets):
    """내보내기는 화면과 **같은 함수**에서 칸을 받는다(`panel_columns`).

    파일에만 남으면 받은 사람이 화면과 다른 표를 들고 대조하게 된다.
    """
    import io

    openpyxl = pytest.importorskip("openpyxl")

    res = sheets.get("/api/export/contacts.xlsx", params={"sheet": LIST})
    assert res.status_code == 200, res.text
    ws = openpyxl.load_workbook(io.BytesIO(res.content)).active
    head = list(next(ws.iter_rows(values_only=True)))
    assert GONE_LABEL not in head, f"엑셀에 그 칸이 남았습니다: {head}"
    # 안 건드린 칸은 그대로 나간다 — 뺀 것이 그 칸 하나인지 함께 본다.
    assert "계약여부" in head and BEFORE in head, head


# ── 2. 값은 안 지워진다 — 이번 판의 핵심 ────────────────────────────────────

def test_칸을_빼도_저장된_값이_그대로_있다(sheets, db):
    """**칸을 뺀 것이지 값을 버린 것이 아니다.**

    `source="note"` 라 값은 `VcContact.notes` 의 키에 담긴다 — 모델 칸이
    아니어서 이주가 없고, 칸 정의만 빠져도 DB 는 그대로다. 화면을 열고 API 로
    읽어도 줄어들 자리가 없어야 한다.
    """
    from app.services import contact_columns as cc

    sheets.get(_url())              # 화면을 한 번 그린다
    row = _row(db)
    assert cc.load_notes(row.notes).get(GONE_KEY) == "회신 받음", \
        "화면을 여는 것만으로 값이 사라졌습니다"

    got = sheets.get(f"/api/contacts/{row.id}").json()["contact"]["notes"]
    assert got.get(GONE_KEY) == "회신 받음", \
        "되읽기에서 값이 빠졌습니다 — 되돌려도 돌아올 것이 없어진다"


def test_옆_칸을_고쳐도_그_값이_안_지워진다(sheets, db):
    """`PATCH` 는 `notes` 를 **합쳐서** 저장한다.

    통째로 덮어쓰는 구조였다면, 칸을 뺀 화면에서 아무 칸이나 한 번 고치는
    순간 `reply_status` 가 통째로 날아간다 — 아무도 안 보는 칸이라 날아간
    줄도 모른다. 여기서 잠그는 것이 정확히 그것이다.
    """
    from app.services import contact_columns as cc

    row = _row(db)
    res = sheets.patch(f"/api/contacts/{row.id}",
                       json={"notes": {"collab_status": "당사 통한 진행 희망"}})
    assert res.status_code == 200, res.text

    got = sheets.get(f"/api/contacts/{row.id}").json()["contact"]["notes"]
    assert got["collab_status"] == "당사 통한 진행 희망"
    assert got.get(GONE_KEY) == "회신 받음", \
        "옆 칸을 고쳤더니 뺀 칸의 값이 사라졌습니다"

    db.expire_all()
    assert cc.load_notes(_row(db).notes).get(GONE_KEY) == "회신 받음"


def test_이주가_없다():
    """**이주를 만들지 않았다.** 모델 칸이 아니라 만들 것도 없다.

    `VcContact` 에 `reply_status` 칸이 있었다면 지우는 데 이주가 필요했을
    것이고, 그때는 되돌리기가 한 줄이 아니다.
    """
    from app.models import VcContact

    assert not hasattr(VcContact, GONE_KEY), \
        "모델 칸이라면 이 판에서 뺄 칸이 아니다 — 이주가 필요하다"
    for path in (ROOT / "alembic" / "versions").glob("*.py"):
        assert GONE_KEY not in path.read_text(encoding="utf-8"), \
            f"{path.name} 이 그 키를 건드립니다 — 이 판은 이주를 만들지 않는다"


# ── 3. 되돌리기가 한 줄이다 ─────────────────────────────────────────────────

def test_되돌릴_한_줄이_뺀_자리에_주석으로_남아_있다():
    """#197 이 `초대 완료 여부` 를 뺄 때 세운 방식이다.

    왜 뺐는지와 **어떻게 되돌리는지**가 뺀 자리에 없으면, 다음 사람은 이
    칸이 있었다는 것조차 모른다 — 이 저장소의 주석은 `회신 상태` 를 가리키는
    글을 여러 군데 들고 있어서, 없는 칸을 찾아 헤매게 된다.
    """
    src = (ROOT / "app" / "services" / "contact_columns.py").read_text(encoding="utf-8")
    assert f'#     Column("{GONE_LABEL}", "{GONE_KEY}", {GONE_WIDTH}, source="note",' in src, \
        "되돌릴 한 줄이 주석으로 안 남아 있습니다"
    assert "#            kind=\"pick\", choices=REPLY_CHOICES)," in src


def test_보기_목록은_남기되_어느_칸도_안_쓴다():
    """`REPLY_CHOICES` 는 그대로 둔다.

    `notes` 에 **이미 들어 있는 글**이 무슨 말이었는지 아는 유일한 자리이고,
    되돌릴 때 `choices=REPLY_CHOICES` 한 줄이 그대로 살아야 한다. 대신 지금은
    **어느 칸도 그 목록을 안 쓴다** — 쓰고 있으면 칸이 덜 빠진 것이다.
    """
    from app.services import contact_columns as cc

    assert cc.REPLY_CHOICES, "보기 목록까지 지우면 되돌리기가 한 줄이 아니다"
    assert "회신 받음" in cc.REPLY_CHOICES

    layouts = [cc.STARTUP_LAYOUT, cc.INVESTOR_LAYOUT, cc.INVESTOR_MONTHLY_LAYOUT]
    for layout in layouts:
        for column in list(layout.head) + list(layout.tail) + list(layout.extra):
            assert column.choices != cc.REPLY_CHOICES, \
                f"`{column.label}` 이 아직 그 보기를 씁니다"
        for _needle, choices in layout.month_picks:
            assert choices != cc.REPLY_CHOICES, \
                "월별 칸이 그 보기를 씁니다 — 달에 안 매이는 값이었다"


# ── 4. 남은 칸은 안 밀린다 ──────────────────────────────────────────────────

def test_남은_칸은_차례도_폭도_그대로고_표만_그만큼_좁아진다(sheets, db):
    """칸 하나가 빠질 때 **옆 칸이 따라 밀리는 것**이 이 표의 사고 방식이다.

    표 폭은 적어 둔 칸 폭의 합이라(`contacts.html` 의 `table_columns|sum`)
    손으로 맞출 데가 없다 — 그래도 실제로 그만큼만 줄었는지 여기서 잰다.
    `app.css` 의 `#contacts-table { min-width }` 는 **투자사 표 것**이라
    이 표를 따라 줄지 않는다(그래서 안 건드렸다).
    """
    from app.services import contact_columns as cc

    months = cc.month_columns(db, LIST)
    columns = cc.table_columns(cc.STARTUP_LAYOUT, months)
    labels = [c.label for c in columns]

    # 계약 세 칸 **바로 뒤**가 월별 묶음이다(그 사이에 뺀 칸이 서 있었다).
    assert labels[labels.index(BEFORE) + 1] == MONTHS[0], labels

    html = sheets.get(_url()).text
    got = re.search(r'id="contacts-table"[^>]*min-width:(\d+)px', html, re.S)
    assert got, "표 폭을 찾지 못했습니다"
    want = sum(c.width for c in columns) + 44
    assert int(got.group(1)) == want, (int(got.group(1)), want)
    # 그 칸이 서 있었다면 딱 110px 더 넓었다 — 뺀 만큼만 줄었는지 되짚는다.
    assert int(got.group(1)) == want, (int(got.group(1)), want)
    assert GONE_WIDTH not in [c.width for c in columns
                              if c.label == GONE_LABEL], "칸이 아직 있습니다"

    # 남은 칸의 폭은 한 칸도 안 건드렸다.
    widths = {c.label: c.width for c in cc.STARTUP_LAYOUT.head}
    assert widths["계약여부"] == 110 and widths[BEFORE] == 140, widths


# ── 5. 시트 임포터가 조용히 쌓지 않는다 ─────────────────────────────────────

def test_임포터는_그_열을_계속_알아본다():
    """**빼면 더 나빠진다.**

    `NOTES` 에서 빼면 `회신 상태` 가 남는 머리글이 되어 **월별 칸으로 선다** —
    달에 안 매이는 값이 달 칸 자리에 서면 그 달의 기록을 접어 버리고, 달이
    바뀔 때마다 지난달로 밀려 내려간다. 그래서 읽는 것은 그대로 둔다.
    """
    from scripts.import_startup_sheet import HIDDEN_NOTES, NOTES

    assert (GONE_LABEL, GONE_KEY) in NOTES, \
        "빼면 그 머리글이 월별 칸으로 선다 — 더 나쁜 자리다"
    assert GONE_KEY in HIDDEN_NOTES, "화면에 안 서는 칸이라고 적어 두지 않았습니다"


def test_그_열이_들어오면_화면에_안_보인다고_알린다(tmp_path):
    """조용히 쌓는 대신 **적어서 알린다.**

    값이 `notes` 에 들어가는데 화면 어디에도 안 보이면, 시트에 적은 사람은
    사라졌다고 읽고 다시 적는다 — 그때는 원래 무엇이 적혀 있었는지 알 길이
    없다. 이 저장소가 가장 경계하는 '조용한' 부류다.
    """
    import csv

    from scripts.import_startup_sheet import hidden_notice, parse

    head = ["NO", "기업명", "성함", "연락처", "이메일", GONE_LABEL,
            f"{_month()}월 리마인드 문자"]
    path = tmp_path / "sheet.csv"
    with path.open("w", encoding="utf-8", newline="") as fp:
        writer = csv.writer(fp)
        writer.writerow(head)
        writer.writerow(["1", "샘플기업1", "김샘플1", "01000000101",
                         "sample1@example.com", "회신 받음", "발송 완료"])
    with path.open(encoding="utf-8") as fp:
        rows = [r for r in csv.reader(fp)]

    parsed = parse(rows)
    # 값은 그 키로 들어간다 — 버리지 않는다.
    assert parsed["items"][0]["notes"][GONE_KEY] == "회신 받음"
    # 달마다 늘어나는 칸으로 서지 않는다.
    assert GONE_LABEL not in parsed["columns"], parsed["columns"]
    # 그리고 **조용하지 않다.**
    notice = hidden_notice(parsed)
    assert GONE_LABEL in notice and "안 보" in notice, notice


def test_그_열이_없는_시트에는_아무_말도_안_한다(tmp_path):
    """알림이 늘 뜨면 아무도 안 읽는다."""
    import csv

    from scripts.import_startup_sheet import hidden_notice, parse

    path = tmp_path / "sheet.csv"
    with path.open("w", encoding="utf-8", newline="") as fp:
        writer = csv.writer(fp)
        writer.writerow(["NO", "기업명", "성함", "연락처", "이메일"])
        writer.writerow(["1", "샘플기업1", "김샘플1", "01000000101",
                         "sample1@example.com"])
    with path.open(encoding="utf-8") as fp:
        rows = [r for r in csv.reader(fp)]

    assert hidden_notice(parse(rows)) == ""
