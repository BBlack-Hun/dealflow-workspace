"""`관리 스타트업` 탭의 `카톡 연결 여부` — 세 번째 자리라는 것까지 못 박는다.

사용자가 이 탭에 부른 칸이다. 자리는 `계약서 수신완료여부` 바로 뒤,
`딜 소개문구` 앞이다(처음에는 `IR 자료 회신여부` 앞이라고 불렀는데 이 탭에는
그런 칸이 없어, 없는 칸을 새로 세우는 대신 자리를 다시 물어 정했다).

## 이 파일이 지키는 것

  1. 눌러 고치면 **정말 저장되고 다시 읽힌다** — 이 저장소는 칸을 고쳐도
     조용히 안 저장되는 사고를 여러 번 겪었다(라우터의 `CompanyIn` 에 이름을
     안 적으면 pydantic 이 그냥 버린다).
  2. **자리**가 사용자가 정한 그대로고, 머리글 차례와 칸 차례가 안 어긋난다.
  3. 다른 탭에는 **안 선다.**
  4. 필터 셋(머리글 선언 · 행이 싣는 값 · 칸이 아는 키)이 같은 것을 가리키고,
     검색에도 실린다.
  5. 엑셀·시트 올리기가 이 칸을 다룬다.
  6. 이주가 기존 줄에 값을 **지어 넣지 않고**, 내렸다 올려도 표가 같다.
  7. **같은 물음을 적는 자리가 셋**이고 값이 서로 안 오간다 — 합치려면 기업
     목록부터 이어야 한다. `tests/test_contract_received_xref.py` 가 계약서
     수신 쪽에 대고 하는 일을 카톡 연결 쪽에 대고 한다.

이름·기업명은 전부 지어낸 값이다 — 저장소가 공개다.
"""
from __future__ import annotations

import importlib.util
import os
import pathlib
import re
import shutil
import sqlite3
import subprocess
import sys

import pytest

from .conftest import DEMO_PASSWORD

STARTUP = "스타트업"
HANDOVER = "경영본부 전달 기업"
CONTRACT = "월간 계약 업무현황표"

ROOT = pathlib.Path(__file__).resolve().parent.parent

LABEL = "카톡 연결 여부"
FIELD = "kakao_joined"
KEY = "joined"                      # 머리글이 선언하는 필터 키
REVISION = "0077_consulting_kakao_joined"


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

@pytest.mark.parametrize("value", ["O", "X"])
def test_고쳐지고_다시_읽힌다(allowed, db, users, value):
    """스키마·저장·되읽기·화면 넷 중 하나가 빠지면 **조용히** 안 저장된다."""
    from app.models import ConsultingCompany

    row = _row(db, users["u1"].id, sheet=STARTUP, position=1, company_name="샘플가")
    assert allowed.patch(f"/api/consulting/{row.id}",
                         json={FIELD: value}).status_code == 200
    db.expire_all()
    assert getattr(db.get(ConsultingCompany, row.id), FIELD) == value
    assert allowed.get(f"/api/consulting/{row.id}").json()[FIELD] == value
    body = _open(allowed, STARTUP)
    assert f'data-field="{FIELD}"' in body
    assert f'data-f-{KEY}="{value}"' in body


def test_빈칸으로_되돌릴_수_있다(allowed, db, users):
    """빈칸이 곧 **`아직 안 정함`** 이다.

    보기가 둘뿐이라 미정을 적을 자리가 따로 없다. 되돌릴 길이 없으면 사람은
    아무 값이나 적어 두는데, 그러면 앱이 아무도 확인한 적 없는 사실을 표에
    남긴다 — 카톡방은 아직 얘기도 안 꺼낸 기업이 실제로 있다.
    """
    from app.models import ConsultingCompany

    row = _row(db, users["u1"].id, sheet=STARTUP, position=1, company_name="샘플나")
    allowed.patch(f"/api/consulting/{row.id}", json={FIELD: "O"})
    allowed.patch(f"/api/consulting/{row.id}", json={FIELD: ""})
    db.expire_all()
    assert not getattr(db.get(ConsultingCompany, row.id), FIELD)
    assert allowed.get(f"/api/consulting/{row.id}").json()[FIELD] == ""
    # 빈칸인 줄을 찾는 길은 머리글 필터의 `(비어 있음)` 이라, 행이 빈 값이라도
    # 그 칸을 **싣고** 있어야 한다.
    assert f'data-f-{KEY}=""' in _open(allowed, STARTUP)


def test_기본값이_안_붙는다(db, users):
    """새 줄도 빈칸으로 시작한다 — `X` 로 시작하면 앱이 "확인했는데 연결이
    안 됐다" 고 단정하는 것이 된다."""
    from app.models import ConsultingCompany

    row = _row(db, users["u1"].id, sheet=STARTUP, position=1, company_name="샘플다")
    assert getattr(db.get(ConsultingCompany, row.id), FIELD) is None


def test_옆_칸과_같은_방식으로_골라_넣는다(allowed, db, users):
    """`O`/`X` 두 가지뿐인 칸이다. **새 방식을 만들지 않고** 바로 위
    `계약서 수신완료여부` 가 쓰는 길을 그대로 쓴다 — 이 표의 편집기가 보는
    `data-choices`(consulting.js 의 `addChoices`) 하나다.

    긴 글 표시(`multi`)가 붙으면 누를 때 textarea 가 열려 두 글자만 서야 할
    칸에 줄바꿈이 들어간다.
    """
    _row(db, users["u1"].id, sheet=STARTUP, position=1, company_name="샘플라")
    body = _open(allowed, STARTUP)
    m = re.search(rf'data-field="{FIELD}"[^>]*data-choices="([^"]*)"', body)
    assert m and m.group(1) == "O,X", m and m.group(1)
    html = (ROOT / "app" / "templates" / "consulting.html").read_text(encoding="utf-8")
    assert f'class="cell multi" data-field="{FIELD}"' not in html, \
        "고르는 칸에 긴 글 표시(multi)가 남아 있습니다 — textarea 가 열립니다"


# --- 2. 자리 -----------------------------------------------------------------

def test_딜_소개문구_다음에_맨_뒤로_선다(allowed, db, users):
    """사용자가 정한 자리 그대로다 — `딜 소개문구` **다음**, 묶음의 맨 뒤다.

    한 번 `계약서 수신완료여부` 뒤로 세웠다가 사용자가 고쳐 정했다. 계약 세
    마디의 흐름에 끼는 칸이 아니라 그 뒤에 따로 붙는 칸이다.

    머리글 차례와 칸 차례가 어긋나면 그 뒤가 통째로 밀린다 — 화면에서는 그냥
    값이 이상해 보일 뿐이라 원인을 못 찾는다.
    """
    from app.routers import consulting

    _row(db, users["u1"].id, sheet=STARTUP, position=1, company_name="샘플마",
         management="관리 중", contract_received="O", kakao_joined="O")
    heads = _heads(_open(allowed, STARTUP))
    at = heads.index("계약서 수신완료여부")
    assert heads[at + 1:at + 3] == ["딜 소개문구", LABEL], heads
    fields = _fields(_open(allowed, STARTUP))
    at = fields.index("contract_received")
    assert fields[at + 1:at + 3] == ["deal_pitch", FIELD], fields
    # 칸 묶음 쪽도 같은 차례다 — 화면만 고치고 묶음을 안 고치면 탭 하나가
    # 다른 차례로 그려진다.
    labels = [label for label, _f in consulting.STARTUP_COLUMNS]
    at = labels.index("계약서 수신완료여부")
    assert labels[at + 1:at + 3] == ["딜 소개문구", LABEL], labels
    assert consulting.STARTUP_COLUMNS[at + 2] == (LABEL, FIELD)
    # 묶음의 **맨 뒤** 칸이다 — 뒤에 무엇이 붙으면 이 검사가 먼저 깨진다.
    assert consulting.STARTUP_COLUMNS[-1] == (LABEL, FIELD)


def test_머리글_수와_몸통_칸_수가_같다(allowed, db, users):
    _row(db, users["u1"].id, sheet=STARTUP, position=1, company_name="샘플바")
    body = _open(allowed, STARTUP)
    head = len(_heads(body))
    row = re.search(r"<tbody>(.*?)</tr>", body, re.S)
    assert row
    assert len(re.findall(r"<td\b", row.group(1))) == head


def test_빈_표_안내_줄이_표_전체를_덮는다(allowed, db, users):
    """칸이 하나 늘면 `colspan` 도 같이 늘어야 한다 — 모자라면 안내 문구
    오른쪽에 빈 칸이 남아 표가 깨져 보인다."""
    body = _open(allowed, STARTUP)
    head = len(_heads(body))
    m = re.search(r'colspan="(\d+)"', body)
    assert m, "빈 표 안내 줄을 못 찾았습니다"
    assert int(m.group(1)) == head, (m.group(1), head)


# --- 3. 다른 탭 ---------------------------------------------------------------

def test_다른_탭에는_안_선다(allowed, db, users):
    """`관리 스타트업` 탭에만 부른 칸이다.

    **`not is_contract_sheet` 로 가르면 여기서 걸린다** — 계약 탭이 아닌 탭은
    `경영본부 전달 기업` 말고도 사람이 시트를 올려 만든 탭까지 여럿이고, 그
    탭들에는 값이 영영 안 들어간다.
    """
    _row(db, users["u1"].id, sheet=HANDOVER, position=1, company_name="샘플사")
    _row(db, users["u1"].id, sheet=CONTRACT, position=1, company_name="샘플아",
         management="유료")
    _row(db, users["u1"].id, sheet="사람이 올려 만든 탭", position=1,
         company_name="샘플자")
    for sheet in (HANDOVER, CONTRACT, "사람이 올려 만든 탭"):
        body = _open(allowed, sheet)
        assert LABEL not in body, sheet
        assert FIELD not in body, sheet
        # 빈 값이라도 실으면 아무 머리글도 안 보는 죽은 속성이 된다
        # (`tests/test_filter_columns.py` 의 2번).
        assert f"data-f-{KEY}" not in body, sheet


def test_다른_탭에_값이_남아_있어도_그_탭_화면에는_안_나온다(allowed, db, users):
    """화면에서 안 세우는 것이지 값을 지우는 것이 아니다 — 이 저장소는 이력을
    함부로 지우지 않는다(탭을 옮긴 줄에는 값이 남아 있을 수 있다)."""
    from app.models import ConsultingCompany

    row = _row(db, users["u1"].id, sheet=HANDOVER, position=1,
               company_name="샘플차", kakao_joined="O")
    assert f"data-f-{KEY}" not in _open(allowed, HANDOVER)
    db.expire_all()
    assert db.get(ConsultingCompany, row.id).kakao_joined == "O"


def test_표_모양은_이름이_아니라_열쇠로_짝짓는다(db):
    """탭 이름을 고쳐도 이 칸이 사라지면 안 된다."""
    from app.routers import consulting
    from app.services import consulting_sheets as cs

    assert consulting.SHEET_LAYOUTS[cs.STARTUP] == (
        consulting.STARTUP_COLUMNS, consulting.TAIL_COLUMNS)
    assert (LABEL, FIELD) in consulting.STARTUP_COLUMNS
    assert (LABEL, FIELD) not in consulting.FIXED_COLUMNS
    assert (LABEL, FIELD) not in consulting.CONTRACT_COLUMNS


# --- 4. 필터 · 검색 · 판정 ----------------------------------------------------

def test_필터를_세우고_행에도_값을_싣는다(allowed, db, users):
    """머리글이 선언한 키 · 행이 싣는 값 · 칸이 아는 키, 셋이 같은 것을
    가리켜야 한다(`tests/test_filter_columns.py` 의 부류).

    `data-filter-key` 가 없으면 여기서 고쳐도 행 값이 그대로라 **채워 넣어도
    필터는 옛 목록 그대로**다.
    """
    _row(db, users["u1"].id, sheet=STARTUP, position=1, company_name="샘플카",
         kakao_joined="X")
    body = _open(allowed, STARTUP)
    assert f'data-filters="{KEY}:{LABEL}"' in body
    assert f'data-field="{FIELD}" data-filter-key="{KEY}"' in body
    assert f'data-f-{KEY}="X"' in body
    # 칸 이름을 필터 키로 그대로 쓰면 안 된다 — 머리글이 선언한 것은 `joined` 다.
    assert f'data-filters="{FIELD}' not in body
    assert f"data-f-{FIELD}" not in body


def test_검색에는_넣는다(allowed, db, users):
    """서버가 안 넣으면 **새로고침 전후로 검색 결과가 달라진다** — 화면에서
    고치면 `refreshRowFlags` 가 `td.cell` 을 이어 붙여 다시 적으므로 그때는
    걸리는데, 새로고침하면 서버가 그린 값으로 돌아가 안 걸린다."""
    _row(db, users["u1"].id, sheet=STARTUP, position=1, company_name="샘플타",
         kakao_joined="O")
    row = re.search(r'<tr [^>]*data-search="([^"]*)"', _open(allowed, STARTUP))
    assert row and "o" in row.group(1), row and row.group(1)


def test_칸이_안_서는_탭에서는_검색에도_안_넣는다(allowed, db, users):
    """화면 어디에도 없는 글자로 줄이 걸리면 왜 걸렸는지 알 수가 없다.

    게다가 그 탭에서 아무 칸이나 고치는 순간 브라우저가 보이는 칸만 이어 붙여
    이 값을 다시 적으므로, 고치기 전후로 검색 결과가 달라진다.
    """
    _row(db, users["u1"].id, sheet=HANDOVER, position=1, company_name="샘플파",
         kakao_joined="한글자국")
    row = re.search(r'<tr [^>]*data-search="([^"]*)"', _open(allowed, HANDOVER))
    assert row and "한글자국" not in row.group(1), row and row.group(1)


def test_칩과_KPI_와_갈래_판정은_이_칸을_안_본다():
    """판정은 `services/consulting_status.py` **한 곳**이다 — 늘리지 않는다.

    칩 넷은 `기업 관리` 한 갈래를 서로 안 겹치게 나눈 것이라 한 번에 하나만
    눌리는데, 이 칸은 다른 축이라 거기 끼면 둘을 같이 걸 수가 없다. KPI 도
    탭을 가리지 않고 늘 서는데 이 칸은 한 탭에만 있어, 다른 탭에서는 늘 0 이
    되고 그 0 이 사실처럼 읽힌다.
    """
    src = (ROOT / "app" / "services"
           / "consulting_status.py").read_text(encoding="utf-8")
    tmpl = (ROOT / "app" / "templates"
            / "consulting.html").read_text(encoding="utf-8")
    assert FIELD not in src, "갈래 판정 자리로 새어 들어왔습니다"
    assert f'data-cs-filter="{FIELD}"' not in tmpl
    assert f'data-cs-filter="{KEY}"' not in tmpl
    assert f'data-kpi="{FIELD}"' not in tmpl


# --- 5. 엑셀 · 시트 올리기 ----------------------------------------------------

def test_엑셀에도_실리고_이미_받아_둔_파일의_자리는_안_밀린다(allowed, db, users):
    """화면에 보이는데 내려받으면 없는 칸을 만들지 않는다 — 없다는 사실 자체를
    아무도 눈치채지 못한 채 그 파일이 보고서로 돌아다닌다.

    자리는 **맨 뒤**다. 화면 차례대로 끼우면 그 뒤 월 열이 통째로 한 칸씩
    밀려, 지난번에 내려받아 둔 파일과 나란히 놓고 볼 수가 없다.
    """
    import io

    from openpyxl import load_workbook

    from app.routers.consulting import STARTUP_EXPORT_HEADERS

    assert STARTUP_EXPORT_HEADERS[-1] == LABEL, STARTUP_EXPORT_HEADERS

    _row(db, users["u1"].id, sheet=STARTUP, position=1, company_name="샘플하",
         contract_received="O", kakao_joined="X")
    r = allowed.get("/api/export/consulting.xlsx")
    assert r.status_code == 200
    ws = load_workbook(io.BytesIO(r.content)).active
    grid = list(ws.values)
    head, body = list(grid[0]), list(grid[1])
    assert len(body) == len(head), "머리글 수와 줄의 칸 수가 다릅니다"
    assert head.count(LABEL) == 1, head
    # 같은 값이 두 칸에 나오지 않는가 — 그 파일을 여는 사람은 둘이 다른
    # 사실인 줄 안다(`계약서 수신여부` 와 보기가 같은 `O`/`X` 라 특히 그렇다).
    assert body[head.index(LABEL)] == "X"
    assert body[head.index("계약서 수신여부")] == "O"


def test_시트를_올릴_때_월별_열로_딸려_들어가지_않는다(db, users):
    """원본 시트에도 이 칸이 있을 수 있다.

    `parse_rows` 가 못 알아본 열은 **전부 월별 리마인드 열**이 된다. 여기서
    안 받으면 같은 이름이 표에 두 번 서고(전용 칸은 빈 채로) 값은 엉뚱한
    쪽에 담긴다.
    """
    from app.models import ConsultingCompany
    from app.routers.consulting import apply_rows, parse_rows

    rows = [
        ["NO", "기업명", "계약서 수신완료여부", "카톡 연결 여부",
         "8월 마지막주 리마인드 톡"],
        ["1", "샘플거", "O", "X", "통화함"],
    ]
    parsed = parse_rows(rows)
    assert parsed["columns"] == ["8월 마지막주 리마인드 톡"], parsed["columns"]
    item = parsed["companies"][0]
    assert item[FIELD] == "X"
    assert item["contract_received"] == "O"

    apply_rows(db, parsed, users["u1"])
    saved = db.query(ConsultingCompany).filter_by(company_name="샘플거").one()
    assert (saved.kakao_joined, saved.contract_received) == ("X", "O")


def test_달이_적힌_카톡_열은_안_채간다(db):
    """`스타트업` 명단은 카톡 연결을 **달마다 하나씩** 적는다(`9월 카톡 연결`).

    그런 열까지 이 칸이 집어 가면 그 달 기록이 갈 곳을 잃은 채 조용히
    사라지고(집어 간 열은 월 열에서 빠진다), 달이 여럿이면 어느 달 값이
    남았는지도 알 수 없게 된다. 달이 적힌 이름은 월 열이라는 뜻이다.
    """
    from app.routers.consulting import parse_rows

    parsed = parse_rows([["NO", "기업명", "9월 카톡 연결", "10월 카톡 연결"],
                         ["1", "샘플너", "연결 완료", "기존 연결방 이용"]])
    assert parsed["columns"] == ["9월 카톡 연결", "10월 카톡 연결"], parsed["columns"]
    item = parsed["companies"][0]
    assert item.get(FIELD) is None, item
    assert item["notes"] == {"9월 카톡 연결": "연결 완료",
                             "10월 카톡 연결": "기존 연결방 이용"}


# --- 6. 수정 로그 -------------------------------------------------------------

def test_이_칸을_고치면_수정_로그에_남는다(allowed, db, users):
    """남의 줄을 고친 일은 남아야 한다 — 이 표는 팀원이 서로의 줄을 고칠 수
    있고(`ConsultingRowGrant`), 잘못 바뀐 값을 되돌리려면 앞뒤 값이 남아
    있어야 한다.

    `services/edit_log.py` 의 허용 목록은 **칸 이름**으로 되어 있어서, 이름을
    `VcContact.kakao_joined` 와 같게 둔 덕에 이 칸이 목록에 이미 들어 있다 —
    새 칸을 만들면서 그 목록에 손대는 일을 잊어도 값이 조용히 빠지지 않는다.
    """
    from app.models import ConsultingRowGrant, EditLog
    from app.services import edit_log as svc

    assert FIELD in svc.VALUE_FIELDS, \
        "허용 목록에 없으면 `바뀜` 만 남고 무엇이 어떻게 바뀌었는지가 빠진다"

    # u2 의 줄을 u1 이 고칠 수 있게 해 둔다 — 자기 것만 고친 것은 안 남는다.
    db.add(ConsultingRowGrant(user_id=users["u2"].id,
                              editor_user_id=users["u1"].id))
    db.commit()
    row = _row(db, users["u2"].id, sheet=STARTUP, position=1, company_name="샘플더")
    assert allowed.patch(f"/api/consulting/{row.id}",
                         json={FIELD: "O"}).status_code == 200

    logs = [x for x in db.query(EditLog).all()
            if x.table_name == "consulting_companies" and x.row_id == row.id]
    assert logs, "남의 줄을 고쳤는데 로그가 없습니다"
    assert any(FIELD in (x.changes_json or "") and "O" in (x.changes_json or "")
               for x in logs), [x.changes_json for x in logs]


# --- 7. 마이그레이션 ----------------------------------------------------------

def _module(name: str):
    path = ROOT / "alembic" / "versions" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name.replace("/", "_"), path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod, path


def test_마이그레이션은_기존_줄에_값을_지어_넣지_않는다():
    """운영에는 이 탭에 이미 줄이 들어 있다. 그 줄들은 **빈칸으로 남는다.**

    `X` 로 채우면 앱이 "확인했는데 연결이 안 됐다" 고 단정하는 것이 되고,
    `vc_contacts.kakao_joined` 에서 읽어다 채우는 길도 없다 — 두 표를 잇는
    열쇠가 없다(아래 9번).
    """
    mod, path = _module(REVISION)
    assert mod.down_revision == "0076_manual_send_log"
    assert [name for name, _kind in mod.ADDED] == [FIELD]
    body = path.read_text(encoding="utf-8").split('"""')[-1]
    assert "UPDATE" not in body.upper(), \
        "기존 줄에 값을 채우고 있습니다 — 아무도 확인한 적 없는 사실입니다"
    assert "def upgrade" in body and "def downgrade" in body
    assert "drop_column" in body, "되돌릴 수 없는 마이그레이션입니다"


def test_모델과_마이그레이션이_같은_자료형을_말한다():
    """한쪽만 고치면 새로 만든 DB 와 마이그레이션을 태운 DB 가 갈린다."""
    import sqlalchemy as sa

    from app.models import ConsultingCompany

    mod, _path = _module(REVISION)
    column = ConsultingCompany.__table__.c[FIELD]
    assert isinstance(column.type, sa.String)
    assert isinstance(dict(mod.ADDED)[FIELD], sa.String)
    assert column.nullable, "빈칸이 곧 `아직 안 정함` 이라 NULL 이 서야 한다"


def _alembic(db: pathlib.Path, *args: str) -> subprocess.CompletedProcess:
    """컨테이너가 하는 것과 같은 방식으로 따로 뜬 프로세스에서 돌린다
    (`tests/test_migrations.py` 의 `_alembic` 과 같다)."""
    env = {**os.environ,
           "DATABASE_URL": f"sqlite:///{db}",
           "DEALFLOW_DATA_DIR": str(db.parent)}
    return subprocess.run([sys.executable, "-m", "alembic", *args],
                          cwd=ROOT, env=env, capture_output=True, text=True)


def _columns(db: pathlib.Path, table: str) -> set:
    con = sqlite3.connect(db)
    try:
        return {c[1] for c in con.execute(f'PRAGMA table_info("{table}")')}
    finally:
        con.close()


@pytest.mark.skipif(shutil.which(sys.executable) is None, reason="python 없음")
def test_내렸다_올리면_표가_같다(tmp_path):
    """**운영에 올리기 전에 실제로 내렸다 올려 본다.**

    이 판만 한 칸 내리고(`downgrade -1`) 다시 올려, 칸이 사라졌다가 돌아오고
    나머지 표가 한 칸도 안 달라지는지 본다. 여기 적어 둔 값은 안 돌아온다 —
    이 칸에서 처음 생긴 값이라 옮겨 둘 자리가 없다.

    (`tests/test_migrations.py` 는 `base` 까지 내렸다 올린다. 이 검사는 이 판
    하나를 짚는다 — 전체 되돌리기가 멎으면 어느 판 때문인지 안 보인다.)
    """
    db = tmp_path / "kakao.db"
    up = _alembic(db, "upgrade", "head")
    assert up.returncode == 0, up.stdout + up.stderr
    before = _columns(db, "consulting_companies")
    assert FIELD in before

    down = _alembic(db, "downgrade", "-1")
    assert down.returncode == 0, down.stdout + down.stderr
    assert FIELD not in _columns(db, "consulting_companies"), \
        "내렸는데 칸이 남아 있다 — `downgrade` 가 제 일을 안 했다"
    assert _columns(db, "consulting_companies") == before - {FIELD}, \
        "내리면서 옆 칸까지 건드렸다"

    again = _alembic(db, "upgrade", "head")
    assert again.returncode == 0, again.stdout + again.stderr
    assert _columns(db, "consulting_companies") == before, \
        "내렸다 올렸더니 표가 달라졌다"


# --- 8. 같은 물음을 적는 자리가 셋이다 ----------------------------------------

def test_이_칸은_VcContact_의_같은_이름과_다른_칸이다():
    """**이름이 같아도 다른 표의 다른 칸**이다 — 한쪽에 `O` 를 넣어도 다른
    쪽은 계속 비어 있다.

    이름을 일부러 같게 두었다. 묻는 사실이 같은 칸에 같은 이름을 쓰는 것은
    이 저장소의 방식이고(`IrCompany.contract_received` 와
    `ConsultingCompany.contract_received` 가 그렇게 서 있다), 이름을 달리
    지으면 같은 물음이라는 사실이 코드에서 사라진다.

    **그래서 더더욱, 하나로 이어져 있다고 읽으면 안 된다.** 한 화면만 보고
    `카톡 연결이 된 곳이 몇 곳` 을 세는 일을 여기서 막는다.
    """
    from app.models import ConsultingCompany, VcContact

    consulting = ConsultingCompany.__table__.c[FIELD]
    contact = VcContact.__table__.c[FIELD]
    assert consulting.table.name == "consulting_companies"
    assert contact.table.name == "vc_contacts"
    assert consulting is not contact
    # 둘 다 빈칸이 `아직 안 정함` 이다.
    assert consulting.nullable and contact.nullable


def test_두_표를_잇는_길이_없다():
    """**합치려면 칸이 아니라 기업 목록부터 이어야 한다**는 근거다.

    두 표 사이에 외래키가 없고(둘 다 `users` 만 가리킨다) 기업 이름에 유일성도
    없다 — `VcContact` 는 사람 줄이라 한 기업에 여러 줄이 실리고,
    `ConsultingCompany` 는 시트 줄이라 탭마다 한 줄씩 는다. 이어 주는 것이
    없는 채로 값을 끌어오면 같은 이름의 **다른 기업 줄**에서 값이 넘어온다.

    이 길이 생기는 날 이 검사가 깨지고, 그때
    `models.ConsultingCompany.kakao_joined` 의 주석을 다시 쓰게 된다.
    """
    from app.models import ConsultingCompany, VcContact

    pairs = {(VcContact, "vc_contacts"), (ConsultingCompany, "consulting_companies")}
    names = {name for _model, name in pairs}
    for model, own in pairs:
        pointed = {fk.column.table.name for fk in model.__table__.foreign_keys}
        assert not (pointed & (names - {own})), \
            f"{own} 이 {pointed & names} 를 가리키게 되었다 — 두 자리를 잇는 " \
            "길이 생긴 것이라면 `ConsultingCompany.kakao_joined` 주석을 다시 써라"
    assert not ConsultingCompany.__table__.c["company_name"].unique
    assert "sheet" in ConsultingCompany.__table__.c
    assert not VcContact.__table__.c["firm"].unique


def test_월별_카톡_칸은_여전히_명단_쪽에_있다():
    """세 번째 자리 — `스타트업` 명단이 **달마다** 세우는 `N월 카톡 연결`.

    보기부터 다르다(여덟 가지). 이 칸(`O`/`X`)과 같은 것으로 읽고 한쪽을
    지우면 그 달 기록이 통째로 사라진다.

    (`services/contact_columns.py` 는 다른 작업이 만지고 있는 파일이라 여기서
     **읽기만** 한다.)
    """
    from app.services import contact_columns as cc

    assert "카톡 연결" in cc.STARTUP_LAYOUT.month_seed
    assert len(cc.KAKAO_CHOICES.split(",")) > 2, \
        "월별 칸의 보기가 `O`/`X` 로 줄었다면 두 자리가 합쳐진 것이다"


def test_설명은_한_곳에만_적혀_있다():
    """주석은 낡는다 — 같은 설명이 두 벌이면 한 벌은 반드시 낡는다.

    어디에 무엇이 있고 왜 안 이었는지는 `ConsultingCompany.kakao_joined` 한
    곳에 적고, `VcContact.kakao_joined` 는 거기를 가리키기만 한다.
    """
    src = (ROOT / "app" / "models.py").read_text(encoding="utf-8")
    assert "ConsultingCompany.kakao_joined" in src, \
        "`VcContact` 쪽에서 설명이 있는 자리를 가리키지 않고 있습니다"


# --- 9. 화면 코드 -------------------------------------------------------------

def test_화면_코드를_그대로_돌려_본다():
    """서버만 고치면 반쪽이다 — 고른 값이 저장되고 필터에 걸리는 데까지 본다.

    `tests/js/consulting_kakao_joined_test.js` 가 consulting.js 를 실제로
    돌려, 칸을 눌러 `O`/`X`/`비움` 을 고르고 나간 요청과 행에 적힌 값을 본다.
    로컬에서는 `node tests/js/consulting_kakao_joined_test.js` 로도 돈다.
    """
    node = shutil.which("node")
    if not node:
        pytest.skip("node 미설치 — 브라우저 로직 테스트 생략")
    js = ROOT / "tests" / "js" / "consulting_kakao_joined_test.js"
    r = subprocess.run([node, str(js)], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr
