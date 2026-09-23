"""IR 기업 현황 · 스타트업DB 의 **칸 이름 넷을 바꿨다** (2026-09, 사용자 요청).

        사업분야 대분류  → 대분류      (`sector_major`)
        기업구분        → 투자라운드   (`series`)
        대표자          → 대표자명     (`contact_name`)
        기보, 신보, 중진공 → 정책자금   (`guarantee`)

**DB 칸 이름은 하나도 안 바뀌었다.** 보이는 이름만 바뀐 일이라 판(migration)도
없다. 그래서 이 검사가 보는 것은 전부 **화면에 서는 글자**와, 그 글자가
바뀌었을 때 **같이 깨지는 자리들**이다.

## 이 판에서 제일 위험했던 것 — 시트 가져오기

가져오기는 **고객사 시트의 머리글**로 칸을 찾는다. 그 시트는 여전히 옛
이름이라, 화면을 따라 가져오기까지 새 이름으로 바꾸면 **다음 업로드에서 그
열을 못 찾는다** — 오류가 나는 것이 아니라 값이 조용히 안 들어간다. 그래서
가져오는 두 자리는 옛 이름과 새 이름을 **함께** 받고, 아래 ③ 이 그것을 실제
시트를 만들어 확인한다.

## 이름을 안 바꾼 곳 셋 — 여기 적어 두는 것이 전부다

  · **엑셀 내려받기 머리글**(`routers/data_io.py`) — 받아 쓰던 수식이 머리글로
    칸을 찾는다. 이 목록은 애초에 화면 이름을 따라가지 않는다(`분야(대)` ·
    `경쟁력` 은 화면에서 그렇게 불린 적이 없다).
  · **투자컨설턴트 화면의 `대표자`**(`ConsultingCompany.ceo_name`) — 다른 표의
    다른 칸이다. 이번 요청은 IR 기업 현황 · 스타트업DB 두 탭이었다.
  · **스타트업 명단의 `사업분야 대분류`·`기업구분`**
    (`services/contact_columns.py` 의 `STARTUP_LAYOUT`) — `VcContact.notes` 쪽
    칸이라 여기와 남남이다.

셋 다 "아직 안 고친 자리" 가 아니라 **일부러 둔 자리**다. 이 검사가 그 사실을
붙들어, 다음 사람이 "여기만 안 바꿨네" 하고 마저 바꾸지 않게 한다.

값은 전부 지어낸 것이다 — 저장소가 공개다.
"""
from __future__ import annotations

import io
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parent.parent

# (모델 칸, 옛 이름, 새 이름). **여기 적어 두는 것이 이 검사의 전부다** —
# 앱에서 가져오면 앱이 바뀔 때 검사도 같이 바뀌어 아무것도 못 막는다.
RENAMES = [
    ("sector_major", "사업분야 대분류", "대분류"),
    ("series", "기업구분", "투자라운드"),
    ("contact_name", "대표자", "대표자명"),
    ("guarantee", "기보, 신보, 중진공", "정책자금"),
]

# 필터 **열쇠**. 이름이 아니라 이것이 주소(`?sector=…`)와
# 줄 속성(`data-f-sector`)을 짓는다 — 이름을 바꿔도 여기는 그대로여야 한다.
FILTER_KEYS = {"sector_major": "sector", "series": "series"}


@pytest.fixture()
def company(db):
    from app.models import IrCompany

    row = IrCompany(name="샘플애그", sector_major="애그테크", sector_minor="B2B 유통",
                    series="Pre A, Bridge (누적투자금 5억미만)", contact_name="김가나",
                    guarantee="기보 3억, 신보 2억", one_liner="B2B 농산물 선도거래",
                    revenue_recent="12")
    db.add(row)
    db.commit()
    return row


def _heads(html: str, marker: str) -> list:
    """그 표의 머리글 이름들. `marker` 가 들어 있는 `<thead>` 를 고른다."""
    for m in re.finditer(r"<thead>(.*?)</thead>", html, re.S):
        names = [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", c)).strip()
                 for _a, c in re.findall(r"<th\b([^>]*)>(.*?)</th>", m.group(1), re.S)]
        if marker in names:
            return names
    raise AssertionError(f"`{marker}` 가 있는 표를 못 찾았습니다")


# ── ① 화면에 새 이름이 선다 ─────────────────────────────────────────────────

def test_표_머리글이_새_이름이다(logged_in, company):
    """IR 기업 현황 탭에 둘, 스타트업DB 탭에 둘."""
    status = _heads(logged_in.get("/companies").text, "딜 소개 문구")
    assert "대분류" in status and "투자라운드" in status, status
    assert "소분류" in status, "짝이 되는 칸이 사라졌습니다"

    db_tab = _heads(logged_in.get("/companies?tab=db").text, "수신일")
    assert "대표자명" in db_tab and "정책자금" in db_tab, db_tab


def test_수정창도_같은_이름이다(logged_in, company):
    """표와 창이 갈리면 같은 칸인지 이름으로 판별이 안 된다.

    자리 순서로 짝을 대조하는 일은 tests/test_ui_layout.py 가 전 화면에 걸쳐
    한다. 여기서는 **이번에 바꾼 넷**을 못 박아, 한쪽만 바뀐 채로 통과하지
    않게 한다.
    """
    html = logged_in.get("/companies").text
    for _field, _old, new in RENAMES:
        assert f"<span>{new}</span>" in html, f"[수정] 창에 `{new}` 가 없습니다"


def test_옛_이름은_화면에서_사라졌다(logged_in, company):
    """**그려진 화면**에서 본다 — 템플릿 글자가 아니다.

    바꾼 자리마다 `예전 이름 …` 이라고 주석을 남겨 두었기 때문이다(시트·수식·
    문서가 아직 옛 이름을 쓰고 있어서 적어 둬야 한다). Jinja 주석은 그려질 때
    사라지므로, 화면을 보면 주석에 걸리지 않는다.
    """
    for path in ("/companies", "/companies?tab=db"):
        html = logged_in.get(path).text
        for _field, old, _new in RENAMES:
            assert f"<span>{old}</span>" not in html, f"{path}: 창에 옛 이름 `{old}`"
            assert f">{old}<" not in html, f"{path}: 표에 옛 이름 `{old}`"


def test_이름이_바뀌어도_필터_열쇠는_그대로다(logged_in, db, company):
    """★ 이름은 단추 글자일 뿐이고, **주소를 짓는 것은 열쇠다**(filters.js).

    열쇠가 같이 바뀌면 걸어 둔 필터 주소(`?sector=…`)와 줄 속성
    (`data-f-sector`)이 갈려, 걸어 둔 필터가 말없이 풀린다. 「사업분야 없음」
    단추도 같은 열쇠를 부른다(`data-preset="sector=…"`).

    그 단추는 **대분류가 빈 기업이 있을 때만** 선다(`counts.no_sector`) —
    그래서 빈 줄을 하나 더 넣고 본다.
    """
    from app.models import IrCompany

    db.add(IrCompany(name="샘플메디", one_liner="의료 영상 판독"))
    db.commit()

    html = logged_in.get("/companies").text
    for field, key in FILTER_KEYS.items():
        new = next(n for f, _o, n in RENAMES if f == field)
        assert f'data-filters="{key}:{new}"' in html, f"`{key}` 열쇠가 바뀌었습니다"
        assert f'data-f-{key}=' in html, f"줄에 `data-f-{key}` 가 없습니다"
    assert 'data-preset="sector=' in html, "「사업분야 없음」 단추의 열쇠가 바뀌었습니다"


# ── ② 값은 그대로 오간다 (이름만 바뀐 일이다) ───────────────────────────────

def test_저장도_되읽기도_그대로다(logged_in, db, company):
    """DB 칸 이름은 안 바뀌었다 — PATCH 열쇠도 그대로여야 한다."""
    body = {"series": "Series A", "sector_major": "헬스케어",
            "contact_name": "이다라", "guarantee": "중진공 5억"}
    assert logged_in.patch(f"/api/companies/{company.id}", json=body).status_code == 200

    db.expire_all()
    from app.models import IrCompany
    again = db.get(IrCompany, company.id)
    assert (again.series, again.sector_major) == ("Series A", "헬스케어")
    assert (again.contact_name, again.guarantee) == ("이다라", "중진공 5억")


# ── ③ ★ 시트 가져오기는 **옛 머리글을 계속 읽는다** ─────────────────────────

# 고객사 시트의 머리글. **옛 이름 그대로다** — 이것이 이 검사의 요점이다.
OLD_SHEET_HEAD = ["NO", "기업명", "사업분야 대분류", "소분류", "기업구분",
                  "한줄 소개", "담당자", "IR deck유무", "계약여부",
                  "계약 월 기입", "핵심/TOP Deal", "투자유치상태", "비고"]
# 고객사가 언젠가 시트 머리글까지 화면에 맞춰 고쳤을 때.
NEW_SHEET_HEAD = [h.replace("사업분야 대분류", "대분류").replace("기업구분", "투자라운드")
                  for h in OLD_SHEET_HEAD]


@pytest.mark.parametrize("head, where", [(OLD_SHEET_HEAD, "옛"), (NEW_SHEET_HEAD, "새")])
def test_시트B_파서가_두_머리글을_다_읽는다(head, where):
    """`services/sheet_import.py` 의 `parse_sheet_b`.

    옛 머리글이 안 읽히면 **다음 업로드에서 분야·라운드가 통째로 빈다.**
    오류가 안 나서 아무도 모른다 — 그래서 여기서 잡는다.
    """
    from app.services import sheet_import

    rows = [head, ["1", "샘플애그", "애그테크", "B2B 유통", "Pre A, Bridge",
                   "B2B 농산물 선도거래", "", "", "", "", "", "", ""]]
    parsed = sheet_import.parse_sheet_b(rows, 2026)
    got = parsed.companies[0]
    assert got.sector_major == "애그테크", f"{where} 머리글: 대분류를 못 읽었습니다"
    assert got.series == "Pre A, Bridge", f"{where} 머리글: 투자라운드를 못 읽었습니다"


@pytest.mark.parametrize("swap, where", [
    ({}, "옛"),
    ({"기업구분": "투자라운드", "기보, 신보, 중진공": "정책자금",
      "사업분야 대분류": "대분류", "대표자": "대표자명"}, "새"),
])
def test_스크립트가_두_머리글을_다_읽는다(swap, where):
    """`scripts/import_company_sheets.py` — 실제 워크북을 만들어 넣어 본다.

    이쪽은 `label in name` 으로 찾는다. `대표자` 는 `대표자명` 을 **포함으로**
    잡고 `대분류` 는 `사업분야 대분류` 를 잡지만, `기업구분`↔`투자라운드` 와
    `기보`↔`정책자금` 은 글자가 하나도 안 겹쳐서 둘을 나란히 적어야 한다.
    """
    import openpyxl

    from app.models import IrCompany
    from scripts import import_company_sheets as imp

    book = openpyxl.Workbook()
    ws = book.active
    head = ["기업명", "사업분야 대분류", "소분류", "기업구분", "대표자",
            "기보, 신보, 중진공"]
    ws.append([swap.get(h, h) for h in head])
    ws.append(["샘플애그", "애그테크", "B2B 유통", "Pre A, Bridge",
               "김가나", "기보 3억"])

    row = IrCompany(name="샘플애그")
    by_name = {imp.norm("샘플애그"): row}
    columns = imp.STATUS_COLUMNS + imp.COLUMNS
    imp.load(ws, columns, by_name, SimpleNamespace(overwrite=True))

    assert row.sector_major == "애그테크", f"{where} 머리글: 대분류"
    assert row.series == "Pre A, Bridge", f"{where} 머리글: 투자라운드"
    assert row.contact_name == "김가나", f"{where} 머리글: 대표자명"
    assert row.guarantee == "기보 3억", f"{where} 머리글: 정책자금"


def test_가져오기_목록에서_옛_이름을_지우면_안_된다():
    """옛 이름이 목록에서 사라지면 위 검사가 잡는다 — 여기서는 **까닭이 적혀
    있는지**를 본다. 까닭이 없으면 다음 사람이 "화면이랑 다르네" 하고 지운다.
    """
    src = (ROOT / "scripts" / "import_company_sheets.py").read_text("utf-8")
    assert "시트 머리글" in src and "옛 이름을 지우지 마라" in src, \
        "가져오기 목록에 옛 머리글을 왜 남겨 두는지 안 적혀 있습니다"

    svc = (ROOT / "app" / "services" / "sheet_import.py").read_text("utf-8")
    assert "옛 시트 머리글을 계속 읽는다" in svc, \
        "`parse_sheet_b` 에 옛 머리글을 왜 남겨 두는지 안 적혀 있습니다"


# ── ④ 일부러 **안 바꾼** 세 곳 ──────────────────────────────────────────────

def test_엑셀_머리글은_그대로다(logged_in, db, company):
    """★ '아직 안 바꾼 자리' 가 아니다.

    받아 쓰던 수식이 머리글로 칸을 찾는다. 그리고 이 목록은 애초에 화면 이름을
    따라가지 않는다 — `분야(대)`·`경쟁력` 은 화면에서 그렇게 불린 적이 없다.
    """
    import openpyxl

    book = openpyxl.load_workbook(
        io.BytesIO(logged_in.get("/api/export/companies.xlsx").content))
    head = [c.value for c in book.active[1]]
    assert "기업구분" in head, "★ 엑셀 머리글을 바꾸면 받아 쓰던 수식이 깨진다"
    assert "투자라운드" not in head
    assert "분야(대)" in head and "분야(소)" in head, "이 목록은 화면 이름을 안 따른다"

    src = (ROOT / "app" / "routers" / "data_io.py").read_text("utf-8")
    assert "수식이 머리글로 칸을 찾는다" in src, "왜 안 바꿨는지 안 적혀 있습니다"


def test_투자컨설턴트의_대표자는_그대로다():
    """다른 표의 다른 칸(`ConsultingCompany.ceo_name`)이다."""
    from app.routers import consulting

    labels = [label for label, _field in consulting.MANAGEMENT_COLUMNS] \
        if hasattr(consulting, "MANAGEMENT_COLUMNS") else []
    src = (ROOT / "app" / "routers" / "consulting.py").read_text("utf-8")
    assert '("대표자", "ceo_name")' in src, \
        "투자컨설턴트의 `대표자` 까지 바꿨습니다 — 다른 표의 다른 칸입니다"
    assert "대표자명" not in src or labels is not None


def test_스타트업_명단의_칸_이름은_그대로다():
    """`VcContact.notes` 쪽 칸이라 여기와 남남이다."""
    from app.services import contact_columns as cc

    names = [c.label for c in
             list(cc.STARTUP_LAYOUT.head) + list(cc.STARTUP_LAYOUT.tail)
             + list(cc.STARTUP_LAYOUT.extra)]
    assert "사업분야 대분류" in names and "기업구분" in names, \
        "스타트업 명단까지 바꿨습니다 — 그 탭은 다른 표를 봅니다"
