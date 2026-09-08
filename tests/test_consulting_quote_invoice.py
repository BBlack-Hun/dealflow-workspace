"""투자컨설턴트 → `관리 스타트업` 탭의 `견적서 첨부여부` · `계약관리` ·
`계산서 수신여부` — `기업 관리` **바로 뒤** 세 칸.

컨설턴트가 기업 하나를 붙들고 가는 흐름의 세 마디다(견적서 → 계약 → 계산서).
지금까지는 옆 `기업 관리` 에 한 문장으로 섞여 있었는데(`관리 중 : 미팅 완. ->
견적서 보내기 완료.`), 섞여 있으면 **아직 안 한 곳**을 골라낼 수가 없다 —
적힌 것은 검색으로 찾아지지만 안 적힌 것은 안 찾아진다.

여기서 막는 것은 여섯이다.

  1. **조용히 안 저장되는 것.** 스키마·저장·되읽기·화면 넷 중 하나만 빠져도
     화면은 멀쩡하고 오류도 안 나는데 고친 값이 사라진다(라우터의 `CompanyIn`
     에 이름을 안 적으면 pydantic 이 모르는 칸을 그냥 버린다).
  2. **자리가 밀리는 것.** 머리글 차례와 칸 차례가 어긋나면 그 뒤가 통째로
     밀린다. 빈 표 안내 줄의 `colspan` 도 같이 본다.
  3. 다른 탭에 칸이 **같이 서는 것**.
  4. 칩·KPI·갈래 판정에 **새어 들어가는 것**.
  5. 엑셀에서 **빠지는 것**, 그리고 이미 내려받아 둔 파일의 칸 자리가 밀리는 것.
  6. 이 셋이 **월별 리마인드 열로 딸려 들어가는 것**.

이름·기업명은 전부 지어낸 값이다 — 저장소가 공개다.
"""
from __future__ import annotations

import importlib.util
import pathlib
import re

import pytest

from .conftest import DEMO_PASSWORD

STARTUP = "스타트업"
HANDOVER = "경영본부 전달 기업"
CONTRACT = "월간 계약 업무현황표"

ROOT = pathlib.Path(__file__).resolve().parent.parent

# 세 칸을 한 자리에 적어 둔다. 검사마다 이름을 따로 적으면 하나를 고칠 때
# 나머지가 낡는다 — (화면 이름, 칸 이름, 필터 키) 다. `계약관리` 는 필터를
# 안 세운 칸이라 키가 없다.
NEW_COLUMNS = [
    ("견적서 첨부여부", "quote_attached", "quote"),
    ("계약관리", "contract_management", ""),
    ("계산서 수신여부", "invoice_received", "invoice"),
]


@pytest.fixture()
def allowed(client, db, users):
    users["u1"].can_view_consulting = 1
    db.commit()
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    return client


def _row(db, user_id, **kw):
    from app.models import ConsultingCompany

    row = ConsultingCompany(user_id=user_id, **kw)
    db.add(row)
    db.commit()
    return row


def _open(client, sheet):
    from urllib.parse import quote

    return client.get(f"/consulting?sheet={quote(sheet)}").text


def _heads(html: str) -> list:
    """그려진 표의 머리글 이름들. **정적 글자가 아니라 그려진 화면**을 본다."""
    m = re.search(r"<thead>(.*?)</thead>", html, re.S)
    assert m, "표 머리글을 찾지 못했습니다"
    out = []
    for cell in re.findall(r"<th\b[^>]*>(.*?)</th>", m.group(1), re.S):
        cell = re.sub(r"<form\b.*?</form>", " ", cell, flags=re.S)   # 월 열의 [✕]
        out.append(" ".join(re.sub(r"<[^>]+>", " ", cell).split()))
    return out


def _fields(html: str) -> list:
    return re.findall(r'data-field="([^"]+)"', html.split("<tbody>", 1)[1])


# --- 1. 눌러 고치면 정말 저장되는가 ------------------------------------------

@pytest.mark.parametrize("field,value", [
    ("quote_attached", "O"),
    ("contract_management", "유료 계약 진행 중"),
    ("invoice_received", "X"),
])
def test_세_칸은_고쳐지고_다시_읽힌다(allowed, db, users, field, value):
    """스키마·저장·되읽기·화면 넷 중 하나가 빠지면 **조용히** 안 저장된다.

    라우터의 `CompanyIn` 에 이름을 안 적으면 pydantic 이 모르는 칸을 그냥
    버린다 — 오류도 안 나고, 고친 사람은 저장된 줄 안다. 이 저장소가 실제로
    당한 적이 있는 부류라 네 자리를 다 짚는다.
    """
    from app.models import ConsultingCompany

    row = _row(db, users["u1"].id, sheet=STARTUP, position=1, company_name="샘플가")
    assert allowed.patch(f"/api/consulting/{row.id}",
                         json={field: value}).status_code == 200
    db.expire_all()
    assert getattr(db.get(ConsultingCompany, row.id), field) == value
    assert allowed.get(f"/api/consulting/{row.id}").json()[field] == value
    assert f'data-field="{field}"' in _open(allowed, STARTUP)
    assert value in _open(allowed, STARTUP)


@pytest.mark.parametrize("field", ["quote_attached", "invoice_received"])
def test_빈칸으로_되돌릴_수_있다(allowed, db, users, field):
    """빈칸이 곧 **`아직 안 정함`** 이다.

    `O`/`X` 두 가지뿐이라 미정을 적을 자리가 따로 없다. 잘못 누른 것을
    되돌릴 길이 없으면 사람은 `X` 를 적어 두는데, 그러면 앱이 "안 했다" 고
    단정한 것이 되어 아무도 확인한 적 없는 사실이 표에 남는다.
    """
    from app.models import ConsultingCompany

    row = _row(db, users["u1"].id, sheet=STARTUP, position=1, company_name="샘플나")
    allowed.patch(f"/api/consulting/{row.id}", json={field: "O"})
    allowed.patch(f"/api/consulting/{row.id}", json={field: ""})
    db.expire_all()
    assert not getattr(db.get(ConsultingCompany, row.id), field)
    assert allowed.get(f"/api/consulting/{row.id}").json()[field] == ""


def test_계약관리는_줄바꿈이_살아남는다(allowed, db, users):
    """보기를 정해 두지 않은 **자유 글**이라 여러 줄이 들어온다.

    이름이 `~여부` 가 아니라 `~관리` 로 끝나는 것이 그 표시다 — 이 표에서
    `~관리` 로 끝나는 칸(`기업 관리`)은 이미 문단이 들어오는 자유 문장이다.
    `_assign` 은 앞뒤 공백만 뗀다.
    """
    from app.models import ConsultingCompany

    text = "무료계약 완료(9/2).\n유료 전환은 파일럿 뒤에 다시 이야기."
    row = _row(db, users["u1"].id, sheet=STARTUP, position=1, company_name="샘플다")
    allowed.patch(f"/api/consulting/{row.id}",
                  json={"contract_management": f"  {text}  "})
    db.expire_all()
    assert db.get(ConsultingCompany, row.id).contract_management == text
    cell = re.search(
        r'<td class="cell multi" data-field="contract_management">(.*?)</td>',
        _open(allowed, STARTUP), re.S)
    assert cell and cell.group(1) == text, repr(cell and cell.group(1))


def test_O_X_칸은_골라서_넣고_계약관리는_자유_글이다():
    """`O`·`o`·`ㅇ`·`○` 로 갈리면 두 가지뿐인 칸에서 필터가 못 쓰게 된다.

    계약 탭의 `계약서 수신여부` 가 같은 이유로 `data-choices="O,X"` 를 쓴다.
    반대로 `계약관리` 에 보기를 달면 **사람이 적을 자리가 없어진다** — 무엇을
    담을 칸인지 정해진 적이 없어서 자유 글로 두었다.

    긴 글 칸이 쓰는 표시는 `multi` 다. 다른 화면의 `data-type="long"` 은 공통
    편집기 `inline_edit.js` 의 것이라 이 표에 달면 아무 일도 안 일어난다.
    """
    html = (ROOT / "app" / "templates" / "consulting.html").read_text(encoding="utf-8")
    for field in ("quote_attached", "invoice_received"):
        m = re.search(r'data-field="' + field + r'"[^>]*data-choices="([^"]*)"', html)
        assert m and m.group(1) == "O,X", field
    assert '<td class="cell multi" data-field="contract_management">' in html
    assert 'data-field="contract_management" data-choices' not in html
    assert 'data-field="contract_management" data-type=' not in html


# --- 2. 자리 -----------------------------------------------------------------

def test_기업_관리_바로_뒤에_차례대로_선다(allowed, db, users):
    """사용자가 부른 자리 그대로다 — `기업 관리` **다음**, 견적서 → 계약 →
    계산서 차례.

    칸 순서가 머리글과 어긋나면 그 뒤가 통째로 밀린다. `딜 소개문구` 는 이
    셋보다 뒤로 물러난다 — 세 마디가 일이 나아가는 차례라 `기업 관리` 에
    붙어 있어야 읽힌다.
    """
    _row(db, users["u1"].id, sheet=STARTUP, position=1, company_name="샘플라",
         management="관리 중", quote_attached="O",
         contract_management="무료계약 완료", invoice_received="X")
    body = _open(allowed, STARTUP)
    heads = _heads(body)
    at = heads.index("기업 관리")
    assert heads[at + 1:at + 5] == ["견적서 첨부여부", "계약관리",
                                    "계산서 수신여부", "딜 소개문구"], heads
    fields = _fields(body)
    at = fields.index("management")
    assert fields[at + 1:at + 5] == ["quote_attached", "contract_management",
                                     "invoice_received", "deal_pitch"], fields


def test_머리글_수와_몸통_칸_수가_같다(allowed, db, users):
    """어긋나면 표가 통째로 한 칸씩 밀리는데, 화면에서는 그냥 값이 이상해
    보일 뿐이라 원인을 못 찾는다."""
    _row(db, users["u1"].id, sheet=STARTUP, position=1, company_name="샘플마")
    body = _open(allowed, STARTUP)
    head = len(_heads(body))
    row = re.search(r"<tbody>(.*?)</tr>", body, re.S)
    assert row
    assert len(re.findall(r"<td\b", row.group(1))) == head


def test_빈_표_안내_줄이_표_전체를_덮는다(allowed, db, users):
    """`colspan` 이 모자라면 안내 문구 오른쪽에 빈 칸이 남아 표가 깨져 보인다.

    이 화면은 아직 기업을 안 받은 컨설턴트에게 **이 안내가 전부**라, 그 줄이
    깨져 보이면 계정이 잘못된 줄 안다.
    """
    body = _open(allowed, STARTUP)
    head = len(_heads(body))
    m = re.search(r'colspan="(\d+)"', body)
    assert m, "빈 표 안내 줄을 못 찾았습니다"
    assert int(m.group(1)) == head, (m.group(1), head)


# --- 3. 다른 탭 ---------------------------------------------------------------

def test_다른_두_탭에는_칸이_안_선다(allowed, db, users):
    """세 마디는 **아직 관리 중인 기업**에 대고 쓰는 말이다.

    `경영본부 전달 기업` 은 이미 넘긴 곳이고 `월간 계약 업무현황표` 는 표
    자체가 다르다(그쪽에는 `계약서 수신여부` 가 이미 서 있다 — 계약 줄의
    서류 이야기라 같은 칸이 아니다).

    **`not is_contract_sheet` 로 가르면 여기서 걸린다** — 계약 탭이 아닌 탭은
    `경영본부 전달 기업` 말고도 사람이 시트를 올려 만든 탭까지 여럿이다.
    """
    _row(db, users["u1"].id, sheet=HANDOVER, position=1, company_name="샘플바")
    _row(db, users["u1"].id, sheet=CONTRACT, position=1, company_name="샘플사",
         management="유료")
    _row(db, users["u1"].id, sheet="사람이 올려 만든 탭", position=1,
         company_name="샘플아")
    for sheet in (HANDOVER, CONTRACT, "사람이 올려 만든 탭"):
        body = _open(allowed, sheet)
        for label, field, _key in NEW_COLUMNS:
            assert label not in body, (sheet, label)
            assert field not in body, (sheet, field)


def test_다른_탭에_값이_남아_있어도_그_탭_화면에는_안_나온다(allowed, db, users):
    """화면에서 뺀 것이지 값을 지운 것이 아니다 — 이 저장소는 이력을 함부로
    지우지 않는다(`CONTRACT_TAIL` 이 대표자·연락처를 남겨 둔 것과 같다)."""
    from app.models import ConsultingCompany

    row = _row(db, users["u1"].id, sheet=HANDOVER, position=1,
               company_name="샘플자", contract_management="옮겨 오기 전에 적어 둔 말")
    body = _open(allowed, HANDOVER)
    assert "옮겨 오기 전에 적어 둔 말" not in body
    db.expire_all()
    assert db.get(ConsultingCompany, row.id).contract_management \
        == "옮겨 오기 전에 적어 둔 말"


def test_표_모양은_이름이_아니라_열쇠로_짝짓는다(db):
    """탭 이름을 고쳐도 세 칸이 사라지면 안 된다.

    이름으로 짝지어 두면 이름을 고칠 수 있게 만든 것이 곧 함정이 된다 —
    화면은 멀쩡하고 칸만 조용히 사라진다.
    """
    from app.routers import consulting
    from app.services import consulting_sheets as cs

    assert consulting.SHEET_LAYOUTS[cs.STARTUP] == (
        consulting.STARTUP_COLUMNS, consulting.TAIL_COLUMNS)
    assert consulting.STARTUP_COLUMNS[len(consulting.FIXED_COLUMNS):] == [
        ("견적서 첨부여부", "quote_attached"),
        ("계약관리", "contract_management"),
        ("계산서 수신여부", "invoice_received"),
        ("딜 소개문구", "deal_pitch"),
    ]
    assert consulting.layout_of(db, "경영본부 전달 기업") == (
        consulting.FIXED_COLUMNS, consulting.TAIL_COLUMNS)


# --- 4. 필터 · 검색 · 판정 ----------------------------------------------------

def test_두_O_X_칸에는_필터를_세우고_계약관리에는_안_세운다(allowed, db, users):
    """`O`/`X` 는 고를 것이 모이고, 무엇보다 **빈칸(아직 안 정함)을 고를 수
    있어야** 한다 — filters.js 가 빈 값을 `(비어 있음)` 으로 세워 주므로,
    채워 넣어야 할 줄을 찾는 길이 그것뿐이다.

    `계약관리` 는 자유 글이라 줄마다 달라 고를 것이 모이지 않는다. 세우지
    않았으므로 **행에도 값을 안 싣는다** — 실으면 아무 머리글도 안 보는 죽은
    속성이 된다(`tests/test_filter_columns.py` 의 2번이 잡는다).
    """
    _row(db, users["u1"].id, sheet=STARTUP, position=1, company_name="샘플차",
         quote_attached="O", contract_management="유료계약 완료",
         invoice_received="X")
    body = _open(allowed, STARTUP)
    assert 'data-filters="quote:견적서 첨부여부"' in body
    assert 'data-filters="invoice:계산서 수신여부"' in body
    assert 'data-f-quote="O"' in body
    assert 'data-f-invoice="X"' in body
    assert 'data-filters="contract_management' not in body
    assert "data-f-contract" not in body
    assert 'data-field="contract_management" data-filter-key' not in body


def test_검색에는_넣는다(allowed, db, users):
    """서버가 안 넣으면 **새로고침 전후로 검색 결과가 달라진다** — 화면에서
    칸을 고치면 `refreshRowFlags` 가 `td.cell` 을 전부 이어 붙여 다시 적으므로
    그때는 걸리는데, 새로고침하면 서버가 그린 값으로 돌아가 안 걸린다."""
    _row(db, users["u1"].id, sheet=STARTUP, position=1, company_name="샘플카",
         contract_management="유료계약 완료")
    row = re.search(r'<tr [^>]*data-search="([^"]*)"', _open(allowed, STARTUP))
    assert row, "줄에서 data-search 를 못 찾았습니다"
    assert "유료계약 완료" in row.group(1), row.group(1)


def test_칩과_KPI_와_갈래_판정은_이_칸들을_안_본다():
    """판정은 `services/consulting_status.py` **한 곳**이다 — 늘리지 않는다.

    칩 넷은 `기업 관리` 한 갈래를 서로 안 겹치게 나눈 것이라 한 번에 하나만
    눌린다. 이 셋은 **다른 축**이라 거기 끼면 둘을 같이 걸 수가 없다.
    KPI 도 마찬가지다 — 위 숫자 넷은 탭을 가리지 않고 늘 서는데, 이 칸들은 한
    탭에만 있어서 다른 탭에서는 늘 0 이 되고 그 0 이 사실처럼 읽힌다.

    무엇보다 `계약관리` 는 자유 글이라 `관리` 라는 낱말이 늘 들어 있다 —
    갈래 판정이 이 칸을 보는 순간 그 탭의 모든 줄이 `관리 중` 이 된다.
    """
    src = (ROOT / "app" / "services" / "consulting_status.py").read_text(encoding="utf-8")
    tmpl = (ROOT / "app" / "templates" / "consulting.html").read_text(encoding="utf-8")
    for _label, field, key in NEW_COLUMNS:
        assert field not in src, f"{field} 가 갈래 판정 자리로 새어 들어왔습니다"
        assert f'data-cs-filter="{field}"' not in tmpl, "칩은 `기업 관리` 한 갈래다"
        assert f'data-kpi="{field}"' not in tmpl, "KPI 는 탭을 가리지 않고 늘 선다"
        if key:
            assert f'data-cs-filter="{key}"' not in tmpl


# --- 5. 엑셀 ------------------------------------------------------------------

def test_엑셀에도_실리고_이미_받아_둔_파일의_자리는_안_밀린다(allowed, db, users):
    """화면에 보이는데 내려받으면 없는 칸을 만들지 않는다 — 없다는 사실 자체를
    아무도 눈치채지 못한 채 그 파일이 보고서로 돌아다닌다.

    자리는 **맨 뒤**다. 화면 차례대로 `기업 관리` 옆에 끼우면 그 뒤 월 열이
    통째로 세 칸씩 밀려, 지난번에 내려받아 둔 파일과 나란히 놓고 볼 수가 없다.
    """
    from app.routers.consulting import STARTUP_EXPORT_HEADERS

    assert STARTUP_EXPORT_HEADERS == ["딜 소개문구", "견적서 첨부여부",
                                      "계약관리", "계산서 수신여부"]
    _row(db, users["u1"].id, sheet=STARTUP, position=1, company_name="샘플타",
         quote_attached="O", contract_management="무료계약 완료",
         invoice_received="X")
    r = allowed.get("/api/export/consulting.xlsx")
    assert r.status_code == 200 and len(r.content) > 0

    # 머리글 수와 줄의 칸 수가 같은가 — 하나라도 빠지면 그 뒤가 통째로 밀린다.
    import io

    from openpyxl import load_workbook

    ws = load_workbook(io.BytesIO(r.content)).active
    grid = list(ws.values)
    head = [c for c in grid[0]]
    for label, _field, _key in NEW_COLUMNS:
        assert label in head, label
    body = grid[1]
    assert len(body) == len(head)
    for value in ("O", "무료계약 완료", "X"):
        assert value in body, (value, body)


# --- 6. 월별 열 ---------------------------------------------------------------

def test_월별_열_자동_생성에_안_낀다(allowed, db, users):
    """이 표에는 달마다 한 칸씩 늘어나는 열이 있다(`ConsultingColumn`).

    새 세 칸은 그 열이 아니라 **줄의 칸**(`consulting_companies` 의 컬럼)이라
    본으로 잡힐 자리가 아예 없다. 화면을 열어도 이름을 딴 월 열이 생기지
    않는지 본다 — 생기면 같은 이름이 표에 두 번 서고, 그 뒤로 달마다 하나씩
    늘어난다.
    """
    from app.models import ConsultingColumn

    _row(db, users["u1"].id, sheet=STARTUP, position=1, company_name="샘플파")
    db.add(ConsultingColumn(user_id=users["u1"].id, sheet=STARTUP,
                            label="8월 마지막주 리마인드 톡 or TEL", position=0))
    db.commit()
    _open(allowed, STARTUP)
    labels = [c.label for c in db.query(ConsultingColumn).all()]
    for label, _field, _key in NEW_COLUMNS:
        assert label not in labels, (label, labels)


def test_시트를_올릴_때_월별_열로_딸려_들어가지_않는다(allowed, db, users):
    """원본 시트에도 이 세 칸이 있을 수 있다.

    `parse_rows` 가 못 알아본 열은 **전부 월별 리마인드 열**이 된다. 여기서
    안 받으면 같은 이름이 표에 두 번 서고(전용 칸은 빈 채로) 값은 엉뚱한
    쪽에 담긴다.
    """
    from app.routers.consulting import apply_rows, parse_rows

    rows = [
        ["NO", "지역", "미팅일", "기업명", "기업 관리", "견적서 첨부여부",
         "계약 관리", "계산서 수신여부", "8월 마지막주 리마인드 톡"],
        ["1", "서울", "9/16", "샘플하", "관리 중", "O", "무료계약 완료", "X",
         "통화함"],
    ]
    parsed = parse_rows(rows)
    assert parsed["columns"] == ["8월 마지막주 리마인드 톡"], parsed["columns"]
    item = parsed["companies"][0]
    assert item["quote_attached"] == "O"
    assert item["contract_management"] == "무료계약 완료"
    assert item["invoice_received"] == "X"

    apply_rows(db, parsed, users["u1"])
    from app.models import ConsultingCompany

    saved = db.query(ConsultingCompany).filter_by(company_name="샘플하").one()
    assert (saved.quote_attached, saved.contract_management,
            saved.invoice_received) == ("O", "무료계약 완료", "X")


def test_이름이_비슷한_월_열은_안_채간다(allowed, db, users):
    """`견적서`·`계약 관리` 같은 말은 **월별 리마인드 열 이름에도** 들어간다.

    그 열을 세 칸 중 하나가 채가면 그 달 기록이 갈 곳을 잃은 채 조용히
    사라진다 — `parse_rows` 는 여기서 집어 간 열을 빼고 월 열을 세기 때문이다.
    달이 적힌 이름은 월 열이라는 뜻이니 건너뛴다.
    """
    from app.routers.consulting import parse_rows

    rows = [
        ["NO", "기업명", "9월 견적서 리마인드 톡", "10월 계약 관리 확인"],
        ["1", "샘플거", "톡 발송", "통화 완"],
    ]
    parsed = parse_rows(rows)
    assert parsed["columns"] == ["9월 견적서 리마인드 톡",
                                 "10월 계약 관리 확인"], parsed["columns"]
    item = parsed["companies"][0]
    assert item.get("quote_attached") is None
    assert item.get("contract_management") is None
    assert item["notes"] == {"9월 견적서 리마인드 톡": "톡 발송",
                             "10월 계약 관리 확인": "통화 완"}


# --- 7. 마이그레이션 ----------------------------------------------------------

def test_마이그레이션은_기존_줄에_값을_지어_넣지_않는다():
    """운영에는 이 탭에 이미 줄이 들어 있다. 그 줄들은 **빈칸으로 남는다.**

    전부 `X` 로 채우면 앱이 "안 했다" 고 **단정**하는 것이 되는데, 그건 아무도
    확인한 적 없는 사실이다(0047 · 0048 · 0049 가 같은 이유로 backfill 을 안
    했다).
    """
    path = ROOT / "alembic" / "versions" / "0065_consulting_quote_contract_invoice.py"
    spec = importlib.util.spec_from_file_location("m0065", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.down_revision == "0064_contact_column_hidden"
    assert [name for name, _kind in mod.COLUMNS] == [
        "quote_attached", "contract_management", "invoice_received"]
    src = path.read_text(encoding="utf-8")
    body = src.split('"""')[-1]
    assert "UPDATE" not in body.upper(), \
        "기존 줄에 값을 채우고 있습니다 — 아무도 확인한 적 없는 사실입니다"
    assert "def upgrade" in src and "def downgrade" in src
    assert "drop_column" in src, "되돌릴 수 없는 마이그레이션입니다"


def test_모델과_마이그레이션이_같은_자료형을_말한다():
    """한쪽만 고치면 새로 만든 DB 와 마이그레이션을 태운 DB 가 갈린다.

    `계약관리` 만 `Text` 다 — 보기를 안 정한 자유 글이라 문단이 들어온다.
    """
    import sqlalchemy as sa

    from app.models import ConsultingCompany

    path = ROOT / "alembic" / "versions" / "0065_consulting_quote_contract_invoice.py"
    spec = importlib.util.spec_from_file_location("m0065b", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    kinds = dict(mod.COLUMNS)
    for name, kind in (("quote_attached", sa.String),
                       ("contract_management", sa.Text),
                       ("invoice_received", sa.String)):
        column = ConsultingCompany.__table__.c[name]
        assert isinstance(column.type, kind), name
        assert isinstance(kinds[name], kind), name
        assert column.nullable, "빈칸이 곧 `아직 안 정함` 이라 NULL 이 서야 한다"


def test_화면_코드를_그대로_돌려_본다():
    """서버만 고치면 반쪽이다 — 고른 값이 저장되고 필터에 걸리는 데까지 본다.

    `tests/js/consulting_quote_invoice_test.js` 가 consulting.js 를 실제로
    돌려, 칸을 눌러 `O`/`X`/`비움` 을 고르고 나간 요청과 행에 적힌 값을 본다.
    로컬에서는 `node tests/js/consulting_quote_invoice_test.js` 로도 돈다.
    """
    import shutil
    import subprocess

    node = shutil.which("node")
    if not node:
        pytest.skip("node 미설치 — 브라우저 로직 테스트 생략")
    js = ROOT / "tests" / "js" / "consulting_quote_invoice_test.js"
    r = subprocess.run([node, str(js)], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr
