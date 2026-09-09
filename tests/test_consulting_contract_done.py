"""투자컨설턴트 → `관리 스타트업` 탭의 `계약관리` · `계약완료여부` ·
`계약서 수신완료여부` — `기업 관리` **바로 뒤** 세 칸.

컨설턴트가 기업 하나를 붙들고 가는 흐름의 세 마디다(어떻게 되고 있나 →
끝났나 → 서류는 왔나). 지금까지는 옆 `기업 관리` 에 한 문장으로 섞여 있었는데
(`관리 중 : 미팅 완. -> 계약서 보내기 완료.`), 섞여 있으면 **아직 안 한 곳**을
골라낼 수가 없다 — 적힌 것은 검색으로 찾아지지만 안 적힌 것은 안 찾아진다.

## `계약서 수신완료여부` 는 **새 칸이 아니다**

계약 탭의 `계약서 수신여부`(0048 의 `contract_received`)와 같은 칸이다. 묻는
사실이 하나뿐이라 — 계약서가 왔는가 — 칸을 새로 만들지 않았다. 뜻이 같은데
칸을 둘로 두면 같은 기업의 같은 사실이 두 군데에 갈려 어느 쪽이 맞는지 알 수
없게 된다. 탭마다 이름이 다른 것은 이 표가 이미 하는 일이다(같은 `region` 이
한 탭에서는 `지역`, 다른 탭에서는 `월` 이다).

## `견적서 첨부여부` · `계산서 수신여부` 는 **없어졌다**

0065 가 세웠던 칸인데 사용자가 다시 부른 자리에 없다. 값이 한 줄도 없어서
지웠다(0068). 화면·엑셀·시트 올리기 어디에도 남아 있으면 안 된다 — 남으면
아무도 안 채우는 칸이 표를 넓히고, 엑셀에서는 늘 비어 있는 열이 된다.

여기서 막는 것은 일곱이다.

  1. **조용히 안 저장되는 것.** 스키마·저장·되읽기·화면 넷 중 하나만 빠져도
     화면은 멀쩡하고 오류도 안 나는데 고친 값이 사라진다(라우터의 `CompanyIn`
     에 이름을 안 적으면 pydantic 이 모르는 칸을 그냥 버린다).
  2. **자리가 밀리는 것.** 머리글 차례와 칸 차례가 어긋나면 그 뒤가 통째로
     밀린다. 빈 표 안내 줄의 `colspan` 도 같이 본다.
  3. 다른 탭에 칸이 **같이 서는 것**.
  4. 칩·KPI·갈래 판정에 **새어 들어가는 것**.
  5. 엑셀에서 **빠지는 것**, 지운 둘이 **남아 있는 것**, 그리고 같은 값이
     **두 칸에** 실리는 것.
  6. 세 칸이 **월별 리마인드 열로 딸려 들어가는 것**.
  7. 보기 글자가 **두 곳에 따로 적히는 것** — IR 기업 현황과 갈린다.

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

# 이 탭에 새로 세운 세 칸을 한 자리에 적어 둔다. 검사마다 이름을 따로 적으면
# 하나를 고칠 때 나머지가 낡는다 — (화면 이름, 칸 이름, 필터 키) 다.
# `계약관리` 는 필터를 안 세운 칸이라 키가 없다.
COLUMNS = [
    ("계약관리", "contract_management", ""),
    ("계약완료여부", "contract_done", "done"),
    ("계약서 수신완료여부", "contract_received", "received"),
]

# 0065 가 세웠다가 이번에 지운 칸들. 화면·엑셀·시트 올리기·모델·DB 어디에도
# 남아 있으면 안 된다.
GONE = [("견적서 첨부여부", "quote_attached"),
        ("계산서 수신여부", "invoice_received")]


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
    ("contract_management", "유료 전환 논의 중"),
    ("contract_done", "무료계약완료"),
    ("contract_received", "O"),
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


@pytest.mark.parametrize("field", ["contract_done", "contract_received"])
def test_빈칸으로_되돌릴_수_있다(allowed, db, users, field):
    """빈칸이 곧 **`아직 안 정함`** 이다.

    보기가 둘뿐이라 미정을 적을 자리가 따로 없다. 잘못 누른 것을 되돌릴 길이
    없으면 사람은 아무 값이나 적어 두는데, 그러면 앱이 아무도 확인한 적 없는
    사실을 표에 남긴다. **아직 계약을 안 정한 기업이 실제로 있다.**
    """
    from app.models import ConsultingCompany

    row = _row(db, users["u1"].id, sheet=STARTUP, position=1, company_name="샘플나")
    allowed.patch(f"/api/consulting/{row.id}", json={field: "무료계약완료"})
    allowed.patch(f"/api/consulting/{row.id}", json={field: ""})
    db.expire_all()
    assert not getattr(db.get(ConsultingCompany, row.id), field)
    assert allowed.get(f"/api/consulting/{row.id}").json()[field] == ""
    # 빈칸인 줄을 찾는 길은 머리글 필터의 `(비어 있음)` 이다 — 그래서 행이
    # 빈 값이라도 그 칸을 **싣고** 있어야 한다.
    body = _open(allowed, STARTUP)
    key = dict((f, k) for _label, f, k in COLUMNS)[field]
    assert f'data-f-{key}=""' in body


def test_계약관리는_줄바꿈이_살아남는다(allowed, db, users):
    """보기를 정해 두지 않은 **자유 글**이라 여러 줄이 들어온다.

    이름이 `~여부` 가 아니라 `~관리` 로 끝나는 것이 그 표시다 — 이 표에서
    `~관리` 로 끝나는 칸(`기업 관리`)은 이미 문단이 들어오는 자유 문장이다.
    `_assign` 은 앞뒤 공백만 뗀다.
    """
    from app.models import ConsultingCompany

    text = "무료로 시작(9/2).\n유료 전환은 파일럿 뒤에 다시 이야기."
    row = _row(db, users["u1"].id, sheet=STARTUP, position=1, company_name="샘플다")
    allowed.patch(f"/api/consulting/{row.id}",
                  json={"contract_management": f"  {text}  "})
    db.expire_all()
    assert db.get(ConsultingCompany, row.id).contract_management == text
    cell = re.search(
        r'<td class="cell multi" data-field="contract_management">(.*?)</td>',
        _open(allowed, STARTUP), re.S)
    assert cell and cell.group(1) == text, repr(cell and cell.group(1))


def test_고르는_두_칸은_골라서_넣고_계약관리는_자유_글이다(allowed, db, users):
    """같은 뜻이 여러 글자로 갈리면 두세 가지뿐인 칸에서 필터가 못 쓰게 된다.

    반대로 `계약관리` 에 보기를 달면 **사람이 적을 자리가 없어진다** — 무엇을
    담을 칸인지 정해진 적이 없어서 자유 글로 두었다(0065).

    긴 글 칸이 쓰는 표시는 `multi` 다. 다른 화면의 `data-type="long"` 은 공통
    편집기 `inline_edit.js` 의 것이라 이 표에 달면 아무 일도 안 일어난다.
    """
    from app.routers.consulting import CONTRACT_DONE_CHOICES

    _row(db, users["u1"].id, sheet=STARTUP, position=1, company_name="샘플라")
    body = _open(allowed, STARTUP)
    m = re.search(r'data-field="contract_done"[^>]*data-choices="([^"]*)"', body)
    assert m and m.group(1) == ",".join(CONTRACT_DONE_CHOICES), body[:0] or m
    m = re.search(r'data-field="contract_received"[^>]*data-choices="([^"]*)"', body)
    assert m and m.group(1) == "O,X"
    html = (ROOT / "app" / "templates" / "consulting.html").read_text(encoding="utf-8")
    assert '<td class="cell multi" data-field="contract_management">' in html
    assert 'data-field="contract_management" data-choices' not in html
    assert 'data-field="contract_management" data-type=' not in html


# --- 2. 보기 값은 어디서 오는가 ----------------------------------------------

def test_보기는_IR_기업_현황이_계약을_부르는_그_말이다():
    """같은 것을 두 화면에서 **다른 말로** 부르면 어느 쪽이 맞는지 알 수 없다.

    `무료계약완료`·`유료계약완료` 는 IR 기업 현황이 계약 상태를 부르는 말이고
    (`routers/companies.py` 의 `CONTRACT_LABELS`), 그 말을 여기에 다시 적어
    두면 한쪽을 고치는 날 두 화면이 갈린다. 그래서 **말은 저기서 가져온다.**

    담기는 칸까지 하나로 하지는 못한다 — 저쪽은 `ir_companies` 의 기업 줄,
    이쪽은 `consulting_companies` 의 컨설턴트 줄이고 둘을 잇는 열쇠가 없다
    (기업명이 같다는 보장도 없다). 가져올 수 있는 것은 말뿐이다.
    """
    from app.routers.companies import CONTRACT_LABELS
    from app.routers.consulting import CONTRACT_DONE_CHOICES

    assert CONTRACT_DONE_CHOICES == (CONTRACT_LABELS["free"],
                                     CONTRACT_LABELS["paid"])
    # 글자를 다시 적어 두지 않았는가 — 화면도 라우터가 넘긴 값을 그린다.
    tmpl = (ROOT / "app" / "templates"
            / "consulting.html").read_text(encoding="utf-8")
    assert 'data-choices="{{ contract_done_choices }}"' in tmpl
    for label in CONTRACT_DONE_CHOICES:
        assert label not in tmpl, f"보기 글자({label})가 화면에 또 적혀 있습니다"


def test_계약검토중과_미계약은_이_칸에_안_선다():
    """이름이 `계약완료여부` 인 칸이다.

    `계약검토중`·`미계약` 은 **아직 계약이 안 끝난 상태**라 여기 세우면 이름과
    값이 어긋난다. 그 상태는 빈칸(아직 안 정함)과 옆 `계약관리` 자유 글이 받는다.
    `딜소개 불가` 는 계약 상태가 아니라 발송 금지 표시라 더욱 아니다.
    """
    from app.routers.consulting import CONTRACT_DONE_CHOICES

    assert len(CONTRACT_DONE_CHOICES) == 2
    for word in ("계약검토중", "미계약", "딜소개 불가"):
        assert word not in CONTRACT_DONE_CHOICES


# --- 3. 자리 -----------------------------------------------------------------

def test_기업_관리_바로_뒤에_차례대로_선다(allowed, db, users):
    """사용자가 부른 자리 그대로다 — `기업 관리` **다음**, 계약관리 →
    계약완료여부 → 계약서 수신완료여부 차례.

    칸 순서가 머리글과 어긋나면 그 뒤가 통째로 밀린다. `딜 소개문구` 는 이
    셋보다 뒤다 — 세 마디가 일이 나아가는 차례라 `기업 관리` 에 붙어 있어야
    읽힌다.
    """
    _row(db, users["u1"].id, sheet=STARTUP, position=1, company_name="샘플마",
         management="관리 중", contract_management="무료로 시작",
         contract_done="무료계약완료", contract_received="O")
    body = _open(allowed, STARTUP)
    heads = _heads(body)
    at = heads.index("기업 관리")
    assert heads[at + 1:at + 5] == [label for label, _f, _k in COLUMNS] \
        + ["딜 소개문구"], heads
    fields = _fields(body)
    at = fields.index("management")
    assert fields[at + 1:at + 5] == [field for _l, field, _k in COLUMNS] \
        + ["deal_pitch"], fields


def test_머리글_수와_몸통_칸_수가_같다(allowed, db, users):
    """어긋나면 표가 통째로 한 칸씩 밀리는데, 화면에서는 그냥 값이 이상해
    보일 뿐이라 원인을 못 찾는다."""
    _row(db, users["u1"].id, sheet=STARTUP, position=1, company_name="샘플바")
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


# --- 4. 다른 탭 ---------------------------------------------------------------

def test_다른_두_탭에는_이_묶음이_안_선다(allowed, db, users):
    """세 마디는 **아직 관리 중인 기업**에 대고 쓰는 말이다.

    `경영본부 전달 기업` 은 이미 넘긴 곳이고 `월간 계약 업무현황표` 는 표
    자체가 다르다.

    **`not is_contract_sheet` 로 가르면 여기서 걸린다** — 계약 탭이 아닌 탭은
    `경영본부 전달 기업` 말고도 사람이 시트를 올려 만든 탭까지 여럿이다.

    계약 탭의 `계약서 수신여부` 는 예외다. 그 칸(`contract_received`)은 원래
    거기 서 있었고 이번에 스타트업 탭에도 **같은 칸으로** 섰다 — 그래서 이
    검사는 `계약완료여부` 와 `계약관리` 만 본다.
    """
    _row(db, users["u1"].id, sheet=HANDOVER, position=1, company_name="샘플사")
    _row(db, users["u1"].id, sheet=CONTRACT, position=1, company_name="샘플아",
         management="유료")
    _row(db, users["u1"].id, sheet="사람이 올려 만든 탭", position=1,
         company_name="샘플자")
    for sheet in (HANDOVER, CONTRACT, "사람이 올려 만든 탭"):
        body = _open(allowed, sheet)
        for label, field, _key in COLUMNS:
            if field == "contract_received":
                continue
            assert label not in body, (sheet, label)
            assert field not in body, (sheet, field)
    # `경영본부 전달 기업` 과 사람이 만든 탭에는 `계약서 수신완료여부` 도
    # 안 선다 — 빈 값이라도 실으면 아무 머리글도 안 보는 죽은 속성이 된다.
    for sheet in (HANDOVER, "사람이 올려 만든 탭"):
        body = _open(allowed, sheet)
        assert "contract_received" not in body, sheet
        assert "data-f-received" not in body, sheet


def test_계약서_수신여부는_두_탭에서_한_칸이다(allowed, db, users):
    """이름은 탭이 정하고 **담기는 칸은 하나**다.

    뜻이 같은데 칸을 둘로 두면 같은 기업의 같은 사실이 두 군데에 갈려 어느
    쪽이 맞는지 알 수 없게 된다 — 이 저장소가 되풀이해 겪은 유형이다. 같은
    `region` 이 한 탭에서는 `지역`, 다른 탭에서는 `월` 인 것과 같은 방식이다.
    """
    from app.routers import consulting

    startup = dict((f, label) for label, f in consulting.STARTUP_COLUMNS)
    contract = dict((f, label) for label, f in consulting.CONTRACT_COLUMNS)
    assert startup["contract_received"] == "계약서 수신완료여부"
    assert contract["contract_received"] == "계약서 수신여부"
    # 모델에 같은 뜻의 칸이 하나 더 생기지 않았는가.
    from app.models import ConsultingCompany

    names = set(ConsultingCompany.__table__.c.keys())
    for word in ("contract_receipt", "contract_received_done",
                 "contract_doc_received"):
        assert word not in names, f"같은 뜻의 칸이 두 벌입니다: {word}"


def test_다른_탭에_값이_남아_있어도_그_탭_화면에는_안_나온다(allowed, db, users):
    """화면에서 뺀 것이지 값을 지운 것이 아니다 — 이 저장소는 이력을 함부로
    지우지 않는다(`CONTRACT_TAIL` 이 대표자·연락처를 남겨 둔 것과 같다)."""
    from app.models import ConsultingCompany

    row = _row(db, users["u1"].id, sheet=HANDOVER, position=1,
               company_name="샘플차", contract_management="옮겨 오기 전에 적어 둔 말")
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
        (label, field) for label, field, _key in COLUMNS
    ] + [("딜 소개문구", "deal_pitch")]
    assert consulting.layout_of(db, "경영본부 전달 기업") == (
        consulting.FIXED_COLUMNS, consulting.TAIL_COLUMNS)


# --- 5. 필터 · 검색 · 판정 ----------------------------------------------------

def test_고르는_두_칸에는_필터를_세우고_계약관리에는_안_세운다(allowed, db, users):
    """보기가 정해진 칸은 고를 것이 모이고, 무엇보다 **빈칸(아직 안 정함)을
    고를 수 있어야** 한다 — filters.js 가 빈 값을 `(비어 있음)` 으로 세워
    주므로, 채워 넣어야 할 줄을 찾는 길이 그것뿐이다.

    `계약관리` 는 자유 글이라 줄마다 달라 고를 것이 모이지 않는다. 세우지
    않았으므로 **행에도 값을 안 싣는다** — 실으면 아무 머리글도 안 보는 죽은
    속성이 된다(`tests/test_filter_columns.py` 의 2번이 잡는다).
    """
    _row(db, users["u1"].id, sheet=STARTUP, position=1, company_name="샘플카",
         contract_management="유료 전환 논의 중", contract_done="유료계약완료",
         contract_received="X")
    body = _open(allowed, STARTUP)
    assert 'data-filters="done:계약완료여부"' in body
    assert 'data-filters="received:계약서 수신완료여부"' in body
    assert 'data-f-done="유료계약완료"' in body
    assert 'data-f-received="X"' in body
    assert 'data-field="contract_done" data-filter-key="done"' in body
    assert 'data-field="contract_received" data-filter-key="received"' in body
    assert 'data-filters="contract_management' not in body
    assert "data-f-contract" not in body
    assert 'data-field="contract_management" data-filter-key' not in body


def test_검색에는_넣는다(allowed, db, users):
    """서버가 안 넣으면 **새로고침 전후로 검색 결과가 달라진다** — 화면에서
    칸을 고치면 `refreshRowFlags` 가 `td.cell` 을 전부 이어 붙여 다시 적으므로
    그때는 걸리는데, 새로고침하면 서버가 그린 값으로 돌아가 안 걸린다."""
    _row(db, users["u1"].id, sheet=STARTUP, position=1, company_name="샘플타",
         contract_management="유료 전환 논의 중", contract_done="유료계약완료")
    row = re.search(r'<tr [^>]*data-search="([^"]*)"', _open(allowed, STARTUP))
    assert row, "줄에서 data-search 를 못 찾았습니다"
    assert "유료 전환 논의 중" in row.group(1), row.group(1)
    assert "유료계약완료" in row.group(1), row.group(1)


def test_칩과_KPI_와_갈래_판정은_이_칸들을_안_본다():
    """판정은 `services/consulting_status.py` **한 곳**이다 — 늘리지 않는다.

    칩 넷은 `기업 관리` 한 갈래를 서로 안 겹치게 나눈 것이라 한 번에 하나만
    눌린다. 이 셋은 **다른 축**이라 거기 끼면 둘을 같이 걸 수가 없다.
    KPI 도 마찬가지다 — 위 숫자 넷은 탭을 가리지 않고 늘 서는데, 이 칸들은 한
    탭에만 있어서 다른 탭에서는 늘 0 이 되고 그 0 이 사실처럼 읽힌다.

    무엇보다 `계약관리` 는 자유 글이라 `관리` 라는 낱말이 늘 들어 있고
    `계약완료여부` 에는 `계약` 이 늘 들어 있다 — 갈래 판정이 이 칸들을 보는
    순간 그 탭의 모든 줄이 `관리 중` 이 된다.
    """
    src = (ROOT / "app" / "services"
           / "consulting_status.py").read_text(encoding="utf-8")
    tmpl = (ROOT / "app" / "templates"
            / "consulting.html").read_text(encoding="utf-8")
    for _label, field, key in COLUMNS:
        assert field not in src, f"{field} 가 갈래 판정 자리로 새어 들어왔습니다"
        assert f'data-cs-filter="{field}"' not in tmpl, "칩은 `기업 관리` 한 갈래다"
        assert f'data-kpi="{field}"' not in tmpl, "KPI 는 탭을 가리지 않고 늘 선다"
        if key:
            assert f'data-cs-filter="{key}"' not in tmpl


# --- 6. 엑셀 ------------------------------------------------------------------

def test_엑셀에도_실리고_이미_받아_둔_파일의_자리는_안_밀린다(allowed, db, users):
    """화면에 보이는데 내려받으면 없는 칸을 만들지 않는다 — 없다는 사실 자체를
    아무도 눈치채지 못한 채 그 파일이 보고서로 돌아다닌다.

    자리는 **맨 뒤**다. 화면 차례대로 `기업 관리` 옆에 끼우면 그 뒤 월 열이
    통째로 밀려, 지난번에 내려받아 둔 파일과 나란히 놓고 볼 수가 없다.

    `계약서 수신완료여부` 는 **여기 없다.** 계약 탭과 같은 칸이라
    `계약서 수신여부` 로 이미 실린다 — 또 세우면 같은 값이 두 칸에 나오고,
    그 파일을 여는 사람은 둘이 다른 사실인 줄 안다.
    """
    from app.routers.consulting import (CONTRACT_EXPORT_HEADERS,
                                        STARTUP_EXPORT_HEADERS)

    assert STARTUP_EXPORT_HEADERS == ["딜 소개문구", "계약관리", "계약완료여부"]
    assert "계약서 수신여부" in CONTRACT_EXPORT_HEADERS

    _row(db, users["u1"].id, sheet=STARTUP, position=1, company_name="샘플파",
         contract_management="무료로 시작", contract_done="무료계약완료",
         contract_received="O")
    r = allowed.get("/api/export/consulting.xlsx")
    assert r.status_code == 200 and len(r.content) > 0

    import io

    from openpyxl import load_workbook

    ws = load_workbook(io.BytesIO(r.content)).active
    grid = list(ws.values)
    head = list(grid[0])
    # 머리글 수와 줄의 칸 수가 같은가 — 하나라도 빠지면 그 뒤가 통째로 밀린다.
    body = list(grid[1])
    assert len(body) == len(head)
    for label in ("계약관리", "계약완료여부", "계약서 수신여부"):
        assert head.count(label) == 1, (label, head)
    # 지운 두 칸은 엑셀에도 없다.
    for label, _field in GONE:
        assert label not in head, label
    for value in ("무료로 시작", "무료계약완료"):
        assert body.count(value) == 1, (value, body)
    # 계약서 수신 여부는 **한 칸에** 실린다.
    assert body[head.index("계약서 수신여부")] == "O"
    assert body.count("O") == 1, body


# --- 7. 월별 열 · 시트 올리기 --------------------------------------------------

def test_월별_열_자동_생성에_안_낀다(allowed, db, users):
    """이 표에는 달마다 한 칸씩 늘어나는 열이 있다(`ConsultingColumn`).

    세 칸은 그 열이 아니라 **줄의 칸**(`consulting_companies` 의 컬럼)이라
    본으로 잡힐 자리가 아예 없다. 화면을 열어도 이름을 딴 월 열이 생기지
    않는지 본다 — 생기면 같은 이름이 표에 두 번 서고, 그 뒤로 달마다 하나씩
    늘어난다.
    """
    from app.models import ConsultingColumn

    _row(db, users["u1"].id, sheet=STARTUP, position=1, company_name="샘플하")
    db.add(ConsultingColumn(sheet=STARTUP,
                            label="8월 마지막주 리마인드 톡 or TEL", position=0))
    db.commit()
    _open(allowed, STARTUP)
    labels = [c.label for c in db.query(ConsultingColumn).all()]
    for label, _field, _key in COLUMNS:
        assert label not in labels, (label, labels)


def test_시트를_올릴_때_월별_열로_딸려_들어가지_않는다(allowed, db, users):
    """원본 시트에도 이 세 칸이 있을 수 있다.

    `parse_rows` 가 못 알아본 열은 **전부 월별 리마인드 열**이 된다. 여기서
    안 받으면 같은 이름이 표에 두 번 서고(전용 칸은 빈 채로) 값은 엉뚱한
    쪽에 담긴다.
    """
    from app.routers.consulting import apply_rows, parse_rows

    rows = [
        ["NO", "지역", "미팅일", "기업명", "기업 관리", "계약 관리",
         "계약완료여부", "계약서 수신완료여부", "8월 마지막주 리마인드 톡"],
        ["1", "서울", "9/16", "샘플거", "관리 중", "무료로 시작", "무료계약완료",
         "O", "통화함"],
    ]
    parsed = parse_rows(rows)
    assert parsed["columns"] == ["8월 마지막주 리마인드 톡"], parsed["columns"]
    item = parsed["companies"][0]
    assert item["contract_management"] == "무료로 시작"
    assert item["contract_done"] == "무료계약완료"
    assert item["contract_received"] == "O"

    apply_rows(db, parsed, users["u1"])
    from app.models import ConsultingCompany

    saved = db.query(ConsultingCompany).filter_by(company_name="샘플거").one()
    assert (saved.contract_management, saved.contract_done,
            saved.contract_received) == ("무료로 시작", "무료계약완료", "O")


def test_한_열을_두_칸이_집어_가지_않는다(allowed, db, users):
    """머리글 셋이 서로의 낱말을 품고 있다.

    `계약서 수신완료여부` 안에는 `계약` 도 `완료` 도 들어 있어서, 토막만으로
    가르면 `계약완료여부` 자리가 그 열을 채간다 — 그러면 같은 값이 두 칸에
    담기고 정작 제 칸은 빈 채로 남는다. 시트에 한쪽 칸만 있을 때가 그렇다.
    """
    from app.routers.consulting import parse_rows

    rows = [["NO", "기업명", "계약서 수신완료여부"], ["1", "샘플너", "O"]]
    item = parse_rows(rows)["companies"][0]
    assert item["contract_received"] == "O"
    assert item.get("contract_done") is None, item


def test_이름이_비슷한_월_열은_안_채간다(allowed, db, users):
    """`계약 관리`·`계약 완료` 같은 말은 **월별 리마인드 열 이름에도** 들어간다.

    그 열을 세 칸 중 하나가 채가면 그 달 기록이 갈 곳을 잃은 채 조용히
    사라진다 — `parse_rows` 는 여기서 집어 간 열을 빼고 월 열을 세기 때문이다.
    달이 적힌 이름은 월 열이라는 뜻이니 건너뛴다.
    """
    from app.routers.consulting import parse_rows

    rows = [
        ["NO", "기업명", "9월 계약 완료 확인 톡", "10월 계약 관리 확인"],
        ["1", "샘플더", "톡 발송", "통화 완"],
    ]
    parsed = parse_rows(rows)
    assert parsed["columns"] == ["9월 계약 완료 확인 톡",
                                 "10월 계약 관리 확인"], parsed["columns"]
    item = parsed["companies"][0]
    assert item.get("contract_done") is None
    assert item.get("contract_management") is None
    assert item["notes"] == {"9월 계약 완료 확인 톡": "톡 발송",
                             "10월 계약 관리 확인": "통화 완"}


# --- 8. 지운 두 칸 ------------------------------------------------------------

def test_지운_두_칸은_어디에도_안_남는다(allowed, db, users):
    """0065 가 세웠던 칸인데 사용자가 다시 부른 자리에 없다.

    화면·엑셀·시트 올리기·모델 중 한 곳이라도 남으면 아무도 안 채우는 칸이
    표를 넓히고, 엑셀에서는 늘 비어 있는 열이 된다.
    """
    from app.models import ConsultingCompany
    from app.routers import consulting

    _row(db, users["u1"].id, sheet=STARTUP, position=1, company_name="샘플러")
    body = _open(allowed, STARTUP)
    names = set(ConsultingCompany.__table__.c.keys())
    layout = [f for _label, f in consulting.STARTUP_COLUMNS]
    for label, field in GONE:
        assert label not in body, label
        assert field not in body, field
        assert field not in names, f"모델에 {field} 가 남아 있습니다"
        assert field not in layout, field
        assert label not in consulting.STARTUP_EXPORT_HEADERS
        assert label not in consulting.CONTRACT_EXPORT_HEADERS
    src = (ROOT / "app" / "routers" / "consulting.py").read_text(encoding="utf-8")
    js = (ROOT / "app" / "static" / "js"
          / "consulting.js").read_text(encoding="utf-8")
    for _label, field in GONE:
        assert field not in src, field
        assert field not in js, field
    # 시트에 그 이름의 열이 남아 있으면 **월별 리마인드 열**로 들어간다 —
    # 전용 칸이 없어졌으니 그것이 맞는 자리다(기록이 사라지지 않는다).
    parsed = consulting.parse_rows(
        [["NO", "기업명", "견적서 첨부여부"], ["1", "샘플머", "O"]])
    assert parsed["columns"] == ["견적서 첨부여부"], parsed["columns"]
    assert parsed["companies"][0]["notes"] == {"견적서 첨부여부": "O"}


# --- 9. 마이그레이션 ----------------------------------------------------------

def _module(name: str):
    path = ROOT / "alembic" / "versions" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name.replace("/", "_"), path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod, path


def test_마이그레이션은_기존_줄에_값을_지어_넣지_않는다():
    """운영에는 이 탭에 이미 줄이 들어 있다. 그 줄들은 **빈칸으로 남는다.**

    둘 중 하나로 채우면 앱이 "무료로 계약했다" 고 **단정**하는 것이 되는데,
    그건 아무도 확인한 적 없는 사실이다(0047 · 0048 · 0049 · 0065 가 같은
    이유로 backfill 을 안 했다).
    """
    mod, path = _module("0068_consulting_contract_done")
    assert mod.down_revision == "0067_consulting_columns_per_sheet"
    assert [name for name, _kind in mod.ADDED] == ["contract_done"]
    assert [name for name, _kind in mod.DROPPED] == ["quote_attached",
                                                     "invoice_received"]
    src = path.read_text(encoding="utf-8")
    body = src.split('"""')[-1]
    assert "UPDATE" not in body.upper(), \
        "기존 줄에 값을 채우고 있습니다 — 아무도 확인한 적 없는 사실입니다"
    assert "def upgrade" in src and "def downgrade" in src


def test_내려가면_지운_두_칸이_돌아온다():
    """되돌릴 수 없는 마이그레이션을 만들지 않는다.

    `downgrade` 가 `contract_done` 을 지우고 두 칸을 도로 세운다 — **값은 안
    돌아온다.** 지울 때 두 칸이 비어 있어서 돌아올 값이 없다.
    """
    import sqlalchemy as sa

    mod, _path = _module("0068_consulting_contract_done")
    # 되돌릴 때 **같은 자료형으로** 세워야 한다 — 0065 가 적어 둔 것과 같은가.
    old, _ = _module("0065_consulting_quote_contract_invoice")
    was = dict(old.COLUMNS)
    for name, kind in mod.DROPPED:
        assert isinstance(kind, type(was[name])), name
    assert isinstance(dict(mod.ADDED)["contract_done"], sa.String)


def test_모델과_마이그레이션이_같은_자료형을_말한다():
    """한쪽만 고치면 새로 만든 DB 와 마이그레이션을 태운 DB 가 갈린다.

    (`tests/test_migrations.py` 가 빈 DB 를 끝까지 올려 모델과 칸 단위로
    대조한다 — 이 검사는 그보다 앞에서, 자료형까지 짚는다.)
    """
    import sqlalchemy as sa

    from app.models import ConsultingCompany

    mod, _path = _module("0068_consulting_contract_done")
    column = ConsultingCompany.__table__.c["contract_done"]
    assert isinstance(column.type, sa.String)
    assert isinstance(dict(mod.ADDED)["contract_done"], sa.String)
    assert column.nullable, "빈칸이 곧 `아직 안 정함` 이라 NULL 이 서야 한다"
    # `계약서 수신완료여부` 는 새 칸이 아니다 — 이주가 필요 없다. 여기서 또
    # 만들면 0048 이 세운 칸과 두 벌이 된다(같은 뜻의 칸이 둘).
    touched = {name for name, _kind in mod.ADDED + mod.DROPPED}
    assert "contract_received" not in touched, \
        "이미 있는 칸을 또 만들고 있습니다(0048 의 `contract_received`)"


def test_화면_코드를_그대로_돌려_본다():
    """서버만 고치면 반쪽이다 — 고른 값이 저장되고 필터에 걸리는 데까지 본다.

    `tests/js/consulting_contract_done_test.js` 가 consulting.js 를 실제로
    돌려, 칸을 눌러 보기와 `비움` 을 고르고 나간 요청과 행에 적힌 값을 본다.
    로컬에서는 `node tests/js/consulting_contract_done_test.js` 로도 돈다.
    """
    import shutil
    import subprocess

    node = shutil.which("node")
    if not node:
        pytest.skip("node 미설치 — 브라우저 로직 테스트 생략")
    js = ROOT / "tests" / "js" / "consulting_contract_done_test.js"
    r = subprocess.run([node, str(js)], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr
