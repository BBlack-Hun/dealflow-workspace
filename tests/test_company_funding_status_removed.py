"""IR 기업 현황에서 **`투자 현황` 칸을 뺐다** — 값은 안 지우고.

사용자가 그려 준 구조 맨 아래에 `투자현황 -> 삭제` 라고 적혀 있었다. 그런데
이 칸은 `ir_companies.funding_status` 라는 **모델 칸**이고 운영 281줄에 값이
들어 있다 — 판(migration)으로 떨구면 그 값이 사라진다.

그래서 **칸은 화면에서만 뺐고 값은 DB 에 그대로 둔다.** 이 저장소가 `회신
상태` 를 뺄 때 세운 방식 그대로다(tests/test_startup_reply_status_removed.py).

## 지우기 전에 옮긴 것

이 칸에만 있고 다른 칸(`one_liner`·`business_desc`)에는 없던 글 **19줄**을
`메모`(`note`)로 먼저 옮겼다(운영 자료에서 한 일 — 새로 채움 17 · 기존 메모
뒤에 붙임 2). 나머지 **258줄**은 `기업 한줄 소개`·`딜 소개 문구` 와 글자까지
같은 사본이라 화면에 읽을 곳이 그대로 남아 있다. 그래서 칸을 빼도 **읽을 수
없게 되는 글이 없다.**

## 여기서 잠그는 것

  1. 칸이 **적는 자리 전부**에서 빠졌는가 — [수정] 창 · 표 둘 · 저장 목록
     (`FIELDS`) · 응답 · 저장 길(PATCH). 한 군데라도 남으면 "뺐다" 가
     거짓말이 된다.
  2. **값이 안 지워지는가** — 이 판에서 제일 중요하다. 칸을 뺀 것이지 값을
     버린 것이 아니다. [수정] 창은 **모든 칸을 한 번에** 보내므로, 옆 칸
     하나 고치고 [저장]하는 것만으로 지워지면 되돌릴 수가 없다.
  3. **엑셀에는 남아 있는가 — 일부러다.** 남겨 둔 281줄을 읽을 수 있는
     자리가 거기뿐이다. 여기를 "아직 안 뺀 자리" 로 읽고 마저 빼면, 남겨 둔
     값은 DB 를 직접 여는 것 말고 읽을 길이 없어진다.
  4. **시트 가져오기가 덮지 않는가** — 그 길은 `_set_if_value` 라 덮어쓴다.
     시트를 한 번 올리는 것만으로 남겨 둔 값이 갈아치워지면, 아무도 안 보는
     칸이라 덮인 줄도 모른다.
  5. **되돌리는 길이 적혀 있는가** — 뺀 자리에 왜 뺐는지와 값이 DB 에 남아
     있다는 것이 주석으로 남아 있는가.

## 옆의 같은 이름과 헷갈리지 말 것

`funding_status` 라는 이름은 이 저장소에 **둘**이다.

  · `IrCompany.funding_status`      ← 이 검사가 빼는 칸
  · `VcContact.notes["funding_status"]` — 스타트업 명단의 `투자유치 상태`
    (`services/contact_columns.py` 의 `STARTUP_LAYOUT`). **다른 칸이고 그대로
    둔다.** 그쪽을 잠그는 검사는 tests/test_startup_status_choices.py 다.

또 `투자현황` 이라는 **말**은 투자컨설턴트 메뉴 권한(`can_view_consulting`)을
가리키기도 한다 — 그것도 남남이다.

값은 전부 지어낸 것이다 — 저장소가 공개다.
"""
from __future__ import annotations

import io
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "app" / "templates" / "companies.html"
SCRIPT = ROOT / "app" / "static" / "js" / "companies.js"

# 뺀 칸. **여기 적어 두는 것이 이 검사의 전부다** — 앱에서 가져오면 앱이
# 바뀔 때 검사도 같이 바뀌어 아무것도 못 막는다.
GONE_FIELD = "funding_status"
GONE_LABEL = "투자 현황"

# 엑셀에는 **남는다**. 머리글은 화면 이름과 달리 띄어쓰기가 없다(예전부터
# 그랬고, 이 파일을 받아 쓰던 수식이 머리글로 칸을 찾는다).
EXCEL_HEADER = "투자현황"

# 지어낸 값. 실제로 그 칸에 적혀 있던 모양(진행 라운드 메모)을 흉내 낸다.
KEPT = "Series B 라운드 오픈 — 샘플 메모"


@pytest.fixture()
def company(db):
    """`투자 현황` 에 값이 든 기업 한 곳.

    운영에서도 그렇다: 326줄 중 281줄에 값이 있었다. 칸을 뺀 뒤에도 그 글자가
    DB 에 그대로 있어야 되돌릴 수 있다.
    """
    from app.models import IrCompany

    row = IrCompany(name="샘플애그", sector_major="애그테크",
                    one_liner="B2B 농산물 선도거래", revenue_recent="12",
                    funding_status=KEPT)
    db.add(row)
    db.commit()
    return row


def _reload(db, company):
    db.expire_all()
    from app.models import IrCompany

    return db.get(IrCompany, company.id)


# ── 1. 적는 자리 전부에서 빠졌다 ────────────────────────────────────────────

def test_수정창에_그_칸이_없다(logged_in, company):
    """이름표도 입력 칸도 없어야 한다 — **그려진 화면**에서 본다.

    템플릿 글자가 아니라 응답 HTML 을 본다. 뺀 자리에 남긴 주석이 `투자 현황`
    이라는 말을 쓰고 있어서(왜 뺐는지 적어야 하니까), 템플릿 글자로 재면 그
    주석 때문에 영영 통과하지 못한다. Jinja 주석은 그려질 때 사라진다.
    """
    for path in ("/companies", "/companies?tab=db"):
        html = logged_in.get(path).text
        assert f'id="f-{GONE_FIELD}"' not in html, f"{path}: 입력 칸이 남아 있다"
        assert f"<span>{GONE_LABEL}</span>" not in html, f"{path}: 이름표가 남아 있다"


def test_두_표_어디에도_그_칸이_없다(logged_in, company):
    """눌러 고치는 칸(`data-field`)으로도 서 있으면 안 된다."""
    for path in ("/companies", "/companies?tab=db"):
        html = logged_in.get(path).text
        assert f'data-field="{GONE_FIELD}"' not in html, f"{path}: 표에 남아 있다"


def test_저장_목록에서도_빠졌다():
    """`companies.js` 의 `FIELDS`.

    창과 이 목록이 갈리면 **아무 표시 없이 저장이 안 된다**(이 저장소가 겪은
    사고다). 지금은 양쪽에서 함께 빠져 있어야 맞다 — 둘을 맞대는 검사는
    tests/js/company_edit_fields_test.js 가 따로 한다.
    """
    listed = re.search(r"var FIELDS = \[(.*?)\];", SCRIPT.read_text("utf-8"), re.S)
    assert listed, "companies.js 에서 FIELDS 를 못 찾았습니다"
    names = re.findall(r'"([a-z_0-9]+)"', listed.group(1))
    assert GONE_FIELD not in names, "FIELDS 에 아직 그 칸이 있습니다"


def test_응답에도_그_칸이_안_실린다(logged_in, company):
    """표 · 목록 API · [수정] 창이 **한 벌**(`company_rows`)에서 나온다.

    한 곳에 남겨 두면 화면에 없는 칸이 세 응답에 계속 실려 나간다.
    """
    rows = logged_in.get("/api/companies").json()["rows"]
    assert GONE_FIELD not in rows[0], "목록 응답에 남아 있습니다"

    one = logged_in.get(f"/api/companies/{company.id}").json()
    assert GONE_FIELD not in one, "[수정] 창 응답에 남아 있습니다"


# ── 2. ★ 값이 안 지워진다 ───────────────────────────────────────────────────

def test_옆_칸을_고쳐도_값이_그대로다(logged_in, db, company):
    """★ 이 판에서 제일 중요한 줄.

    [수정] 창은 표와 달리 **모든 칸을 한 번에** 보낸다. 창이 안 보내는 칸을
    서버가 '빈 값으로 하라'로 읽으면, 다른 칸 하나 고치려고 누른 [저장]이
    281줄의 값을 지운다.
    """
    body = {"name": "샘플애그", "sector_major": "애그테크",
            "one_liner": "바뀐 한 줄", "note": "바뀐 메모"}
    assert logged_in.patch(f"/api/companies/{company.id}", json=body).status_code == 200

    again = _reload(db, company)
    assert again.one_liner == "바뀐 한 줄", "옆 칸은 고쳐져야 한다"
    assert again.funding_status == KEPT, "★ 뺀 칸의 값이 지워졌습니다"


def test_화면을_열어_보는_것만으로는_아무_일도_없다(logged_in, db, company):
    for path in ("/companies", "/companies?tab=db"):
        logged_in.get(path)
    logged_in.get(f"/api/companies/{company.id}")
    assert _reload(db, company).funding_status == KEPT


# ── 3. 저장 길(PATCH)로도 못 쓴다 ───────────────────────────────────────────

def test_PATCH_로_보내도_안_써진다(logged_in, db, company):
    """화면에서 없앴는데 API 로는 여전히 쓸 수 있으면 반쪽이다.

    보이지도 고치지도 못하는 값이 계속 쌓일 자리를 남겨 두지 않는다.
    """
    logged_in.patch(f"/api/companies/{company.id}",
                    json={GONE_FIELD: "새로 써 넣으려는 값"})
    assert _reload(db, company).funding_status == KEPT, "PATCH 로 써졌습니다"


def test_보내도_400_이_되지는_않는다(logged_in, company):
    """**막지는 않는다** — 모르는 칸은 조용히 버린다.

    창이 모든 칸을 한 번에 보내므로, 낡은 화면이 남아 있는 잠깐 동안 그 창이
    보내는 값은 *방금 읽은 그 값* 이다. 버리나 넣으나 결과가 같은 한 번인데,
    400 을 내면 그 무해한 한 번이 "저장 실패" 가 된다.

    (`contract_status` 는 반대로 막는다 — 거기는 모르는 값이 들어가면 줄의
     뜻이 바뀌어 발송 목록이 달라진다. 버려도 되는 값이 아니다.)
    """
    r = logged_in.patch(f"/api/companies/{company.id}",
                        json={"name": "샘플애그", GONE_FIELD: "아무 값"})
    assert r.status_code == 200, r.text


# ── 4. 검색으로도 안 걸린다 ─────────────────────────────────────────────────

def test_안_보이는_글자로_줄이_걸리지_않는다(logged_in, db, company):
    """화면 어디에도 안 보이는 글자로 줄이 걸리면 왜 걸렸는지 알 수 없다.

    잃는 것도 없다 — 값 281줄 중 258줄은 `기업 한줄 소개`·`딜 소개 문구` 와
    글자까지 같은 사본이라 그 두 칸으로 그대로 걸리고, 나머지 19줄은
    `메모`(`note`)로 옮겨 두었다.
    """
    rows = logged_in.get("/api/companies").json()["rows"]
    hay = rows[0]["search"]
    assert "라운드 오픈" not in hay, "안 보이는 칸의 글자가 검색에 실려 있습니다"
    assert "b2b" in hay, "보이는 칸은 그대로 걸려야 한다"


# ── 5. ★ 엑셀에는 남아 있다 — 일부러 ────────────────────────────────────────

def test_엑셀에는_남긴다(logged_in, db, company):
    """★ **이 줄은 '아직 안 뺀 자리' 가 아니다.**

    값 281줄을 DB 에 그대로 두기로 한 이상, 그것을 읽을 수 있는 자리가 하나는
    있어야 한다 — 그 자리가 여기뿐이다. 엑셀은 적는 자리가 아니라 내려받아
    대조하는 자리라서, 화면에서 뺀 것과 어긋나지도 않는다.

    이 칸을 정말 버리기로 하면 **여기가 마지막 자리**다. 여기서 빼는 순간
    남겨 둔 값은 DB 를 직접 여는 것 말고는 읽을 길이 없어진다.
    """
    import openpyxl

    book = openpyxl.load_workbook(
        io.BytesIO(logged_in.get("/api/export/companies.xlsx").content))
    sheet = book.active
    head = [c.value for c in sheet[1]]
    assert EXCEL_HEADER in head, "★ 엑셀에서도 빠지면 남겨 둔 값을 읽을 데가 없다"

    col = {name: i for i, name in enumerate(head)}
    row = next(r for r in sheet.iter_rows(min_row=2, values_only=True)
               if r[0] == "샘플애그")
    assert row[col[EXCEL_HEADER]] == KEPT


# ── 6. 시트 가져오기가 덮지 않는다 ──────────────────────────────────────────

def test_시트를_올려도_그_칸을_덮지_않는다(db, company):
    """그 길은 `_set_if_value` 라 **덮어쓴다**.

    시트를 한 번 올리는 것만으로, 화면에서 뺀 뒤에도 읽을 수 있게 남겨 둔
    281줄이 시트 값으로 갈아치워진다. 아무도 안 보는 칸이라 덮인 줄도 모른다.
    """
    from app.services import sheet_import

    parsed = sheet_import.ParsedCompany(row_no=2, name="샘플애그",
                                        funding_status="시트가 들고 온 값")
    sheet_import.apply_sheet_b(db, sheet_import.SheetBParse(companies=[parsed]))
    db.commit()

    assert _reload(db, company).funding_status == KEPT, \
        "시트 가져오기가 뺀 칸을 덮었습니다"


# ── 7. 되돌리는 길이 적혀 있다 ──────────────────────────────────────────────

def test_왜_뺐는지와_값이_남아_있다는_것이_적혀_있다():
    """안 적으면 다음 사람이 "칸이 없어졌는데 값이 있네" 하고 헤맨다.

    적는 자리는 **뺀 그 자리**다 — 칸을 찾다가 없어서 템플릿을 여는 사람이
    가장 먼저 닿는 곳이라, 딴 데 적어 두면 못 읽는다.
    """
    text = TEMPLATE.read_text("utf-8")
    assert GONE_LABEL in text, "뺀 자리에 그 칸 이름이 안 적혀 있습니다"
    for word in (GONE_FIELD, "DB", "메모", "엑셀"):
        assert word in text, f"뺀 이유 주석에 `{word}` 가 없습니다"


def test_엑셀에_남긴_이유도_그_자리에_적혀_있다():
    """다음 사람이 "여기만 안 뺐네" 하고 마저 빼지 않게."""
    text = (ROOT / "app" / "routers" / "data_io.py").read_text("utf-8")
    assert "일부러 남겼다" in text, "엑셀에 남긴 것이 뜻한 바라고 안 적혀 있습니다"
