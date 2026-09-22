"""투자컨설턴트 리스트의 `미팅종류` — `미팅일` 바로 오른쪽이라는 것까지 못 박는다.

> "투자컨설턴트 메뉴에서 리스트 탭에서 **미팅날짜 컬럼 옆에 미팅종류 컬럼
>  신설**하고 **화상미팅, 회의실 미팅** 선택할 수 있게 해줘"

## 이 파일이 지키는 것

  1. 눌러 고치면 **정말 저장되고 다시 읽힌다** — 이 저장소는 칸을 고쳐도
     조용히 안 저장되는 사고를 여러 번 겪었다(라우터의 `CompanyIn` 에 이름을
     안 적으면 pydantic 이 그냥 버린다).
  2. **자리**가 사용자가 부른 그대로(`미팅일` 바로 오른쪽)고, 머리글 차례와
     칸 차례가 안 어긋난다.
  3. 보기 둘 + **빈칸**. 글자는 한 곳(`MEETING_KIND_CHOICES`)에서만 나온다.
  4. 계약 탭에는 **안 선다** — 저 탭의 `meeting_at` 은 `계약월` 이라는 다른
     물음을 받고 있다.
  5. 필터 셋(머리글 선언 · 행이 싣는 값 · 칸이 아는 키)이 같은 것을 가리키고,
     검색에도 실린다.
  6. 엑셀·시트 올리기가 이 칸을 다룬다.
  7. 이주가 기존 줄에 값을 **지어 넣지 않고**, 내렸다 올려도 표가 같다.
  8. `Meeting.meet_mode` 와 **다른 칸**이다 — 값이 오가지 않는다.

이름·기업명은 전부 지어낸 값이다 — 저장소가 공개다.
"""
from __future__ import annotations

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

LABEL = "미팅종류"
FIELD = "meeting_kind"
KEY = "meetkind"                    # 머리글이 선언하는 필터 키
REVISION = "0079_consulting_meeting_kind"
#: 이 판 **바로 앞** 판. `downgrade -1` 로 적으면 "이 판이 맨 끝이다" 라는
#: 뜻이 되어, 다음 판이 하나 붙는 날 조용히 **남의 판**을 내린다 — 옆의 같은
#: 부류 검사가 이미 이름으로 적고 있다(`test_consulting_kakao_joined.py`
#: 의 `BEFORE`). 이 판이 `0078_notices`(#223) 뒤로 옮겨 서면서 실제로 그
#: 자리가 됐다.
BEFORE = "0078_notices"


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

@pytest.mark.parametrize("value", ["화상미팅", "회의실 미팅"])
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
    남긴다 — 자리를 아직 안 잡은 미팅이 실제로 있다.
    """
    from app.models import ConsultingCompany

    row = _row(db, users["u1"].id, sheet=STARTUP, position=1, company_name="샘플나")
    allowed.patch(f"/api/consulting/{row.id}", json={FIELD: "화상미팅"})
    allowed.patch(f"/api/consulting/{row.id}", json={FIELD: ""})
    db.expire_all()
    assert not getattr(db.get(ConsultingCompany, row.id), FIELD)
    assert allowed.get(f"/api/consulting/{row.id}").json()[FIELD] == ""
    # 빈칸인 줄을 찾는 길은 머리글 필터의 `(비어 있음)` 이라, 행이 빈 값이라도
    # 그 칸을 **싣고** 있어야 한다.
    assert f'data-f-{KEY}=""' in _open(allowed, STARTUP)


def test_기본값이_안_붙는다(db, users):
    """새 줄도 빈칸으로 시작한다 — 둘 중 하나로 채우면 앱이 아무도 확인한 적
    없는 사실을 단정하는 것이 된다."""
    from app.models import ConsultingCompany

    row = _row(db, users["u1"].id, sheet=STARTUP, position=1, company_name="샘플다")
    assert getattr(db.get(ConsultingCompany, row.id), FIELD) is None


# --- 2. 고르는 칸 -------------------------------------------------------------

def test_옆_칸과_같은_방식으로_골라_넣는다(allowed, db, users):
    """**새 방식을 만들지 않는다.** 이 표에서 값이 몇 가지로 정해진 칸은 전부
    `data-choices` 하나를 쓴다(consulting.js 의 `addChoices`) —
    `계약완료여부`·`카톡 연결 여부` 가 그 길이다.

    긴 글 표시(`multi`)가 붙으면 누를 때 textarea 가 열려 고르는 칸에
    줄바꿈이 들어간다(`견적서 첨부 여부` 가 겪은 자리다).
    """
    from app.routers import consulting

    _row(db, users["u1"].id, sheet=STARTUP, position=1, company_name="샘플라")
    body = _open(allowed, STARTUP)
    m = re.search(rf'data-field="{FIELD}"[^>]*data-choices="([^"]*)"', body)
    assert m, "고르는 칸이 아닙니다 — data-choices 가 없습니다"
    assert m.group(1) == "화상미팅,회의실 미팅", m.group(1)
    assert m.group(1) == ",".join(consulting.MEETING_KIND_CHOICES)
    html = (ROOT / "app" / "templates" / "consulting.html").read_text(encoding="utf-8")
    assert f'class="cell multi" data-field="{FIELD}"' not in html, \
        "고르는 칸에 긴 글 표시(multi)가 남아 있습니다 — textarea 가 열립니다"


def test_보기_글자는_한_곳에만_적혀_있다():
    """화면에 글자를 적어 두면 말을 고치는 날 한쪽만 남는다 —
    `계약완료여부` 가 같은 이유로 `contract_done_choices` 를 받는다."""
    html = (ROOT / "app" / "templates" / "consulting.html").read_text(encoding="utf-8")
    # 주석은 설명하는 자리라 센다 — `data-choices` 에 박힌 글자만 막는다.
    assert 'data-choices="화상미팅' not in html, \
        "보기 글자가 화면에 박혀 있습니다 — MEETING_KIND_CHOICES 를 쓰세요"
    js = (ROOT / "app" / "static" / "js" / "consulting.js").read_text(encoding="utf-8")
    assert "화상미팅" not in js, "보기 글자가 브라우저 쪽에도 적혀 있습니다"


# --- 3. 자리 -----------------------------------------------------------------

def test_미팅일_바로_오른쪽에_선다(allowed, db, users):
    """사용자가 부른 자리 그대로다 — "미팅날짜 컬럼 옆에".

    머리글 차례와 칸 차례가 어긋나면 그 뒤가 통째로 밀린다 — 화면에서는 그냥
    값이 이상해 보일 뿐이라 원인을 못 찾는다.
    """
    from app.routers import consulting

    _row(db, users["u1"].id, sheet=STARTUP, position=1, company_name="샘플마",
         meeting_at="9/16 PM2", meeting_kind="화상미팅")
    heads = _heads(_open(allowed, STARTUP))
    at = heads.index("미팅일")
    assert heads[at + 1] == LABEL, heads
    fields = _fields(_open(allowed, STARTUP))
    at = fields.index("meeting_at")
    assert fields[at + 1] == FIELD, fields
    # 칸 묶음 쪽도 같은 차례다 — 화면만 고치고 묶음을 안 고치면 탭 하나가
    # 다른 차례로 그려진다.
    labels = [label for label, _f in consulting.FIXED_COLUMNS]
    at = labels.index("미팅일(화상, 회의실)")
    assert labels[at + 1] == LABEL, labels
    assert consulting.FIXED_COLUMNS[at + 1] == (LABEL, FIELD)


@pytest.mark.parametrize("sheet", [STARTUP, HANDOVER])
def test_머리글_수와_몸통_칸_수가_같다(allowed, db, users, sheet):
    _row(db, users["u1"].id, sheet=sheet, position=1, company_name="샘플바")
    body = _open(allowed, sheet)
    head = len(_heads(body))
    row = re.search(r"<tbody>(.*?)</tr>", body, re.S)
    assert row
    assert len(re.findall(r"<td\b", row.group(1))) == head


@pytest.mark.parametrize("sheet", [STARTUP, HANDOVER, CONTRACT])
def test_빈_표_안내_줄이_표_전체를_덮는다(allowed, sheet):
    """칸이 하나 늘면 `colspan` 도 같이 늘어야 한다 — 모자라면 안내 문구
    오른쪽에 빈 칸이 남아 표가 깨져 보인다. **탭 셋을 다 본다** — 이 칸은
    계약 탭에만 안 서므로 한 탭만 재면 나머지가 조용히 어긋난다."""
    body = _open(allowed, sheet)
    head = len(_heads(body))
    m = re.search(r'colspan="(\d+)"', body)
    assert m, "빈 표 안내 줄을 못 찾았습니다"
    assert int(m.group(1)) == head, (sheet, m.group(1), head)


# --- 4. 계약 탭 ---------------------------------------------------------------

def test_계약_탭에는_안_선다(allowed, db, users):
    """저 탭의 `meeting_at` 은 `계약월` 이라는 **다른 물음**이다(값이 `미정`·`8`).
    옆에 미팅 방식을 세우면 영영 안 채워지는 칸이 하나 는다."""
    _row(db, users["u1"].id, sheet=CONTRACT, position=1, company_name="샘플사")
    heads = _heads(_open(allowed, CONTRACT))
    assert LABEL not in heads, heads
    assert "계약월" in heads, heads
    assert FIELD not in _fields(_open(allowed, CONTRACT))


def test_경영본부_탭에는_선다(allowed, db, users):
    """`기업 관리` · `미팅일` 과 **같은 묶음**(`FIXED_COLUMNS`)이다 — 두 탭이
    그 묶음을 같이 쓴다. `관리 스타트업` 에만 세우는 칸들과 다르다."""
    _row(db, users["u1"].id, sheet=HANDOVER, position=1, company_name="샘플아")
    assert LABEL in _heads(_open(allowed, HANDOVER))


def test_계약_탭에_값이_남아_있어도_그_탭_화면에는_안_나온다(allowed, db, users):
    """탭을 옮긴 줄에는 값이 남아 있을 수 있다 — 이 저장소는 이력을 안 지운다.
    화면에 없는 글자로 줄이 걸리면 왜 걸렸는지 알 수가 없다."""
    _row(db, users["u1"].id, sheet=CONTRACT, position=1, company_name="샘플자",
         meeting_kind="화상미팅")
    body = _open(allowed, CONTRACT)
    assert f"data-f-{KEY}" not in body, "계약 탭에 죽은 속성이 실렸습니다"
    assert "화상미팅" not in body


# --- 5. 필터 · 검색 -----------------------------------------------------------

def test_필터를_세우고_행에도_값을_싣는다(allowed, db, users):
    """머리글 선언 · 행이 싣는 값 · 칸이 아는 키 **셋이 같은 것**을 가리켜야
    한다. 하나만 어긋나도 필터가 아무 말 없이 거짓말을 한다
    (`tests/test_filter_columns.py` 가 전 화면에 대고 같은 것을 본다)."""
    _row(db, users["u1"].id, sheet=STARTUP, position=1, company_name="샘플차",
         meeting_kind="회의실 미팅")
    body = _open(allowed, STARTUP)
    assert f'data-filters="{KEY}:{LABEL}"' in body
    assert f'data-f-{KEY}="회의실 미팅"' in body
    assert re.search(rf'data-field="{FIELD}"[^>]*data-filter-key="{KEY}"', body)


def test_검색에는_넣는다(allowed, db, users):
    """툴바의 검색이 보는 값(`data-search`)에 실린다 — 화면에서 고치면
    브라우저가 `td.cell` 을 전부 이어 붙여 이 값을 다시 적으므로
    (`consulting.js` 의 `refreshRowFlags`), 서버가 안 넣으면 고치기 전후로
    검색 결과가 달라진다."""
    _row(db, users["u1"].id, sheet=STARTUP, position=1, company_name="샘플카",
         meeting_kind="화상미팅")
    m = re.search(r'data-search="([^"]*)"', _open(allowed, STARTUP))
    assert m and "화상미팅" in m.group(1)


def test_칸이_안_서는_탭에서는_검색에도_안_넣는다(allowed, db, users):
    _row(db, users["u1"].id, sheet=CONTRACT, position=1, company_name="샘플타",
         meeting_kind="화상미팅")
    m = re.search(r'data-search="([^"]*)"', _open(allowed, CONTRACT))
    assert m and "화상미팅" not in m.group(1)


def test_칩과_KPI_와_갈래_판정은_이_칸을_안_본다():
    """칩·KPI 는 `기업 관리` 한 갈래만 본다. 이 칸이 판정에 끼면 미팅을 화상으로
    한 것이 `관리 중`·`드랍` 수를 바꾼다."""
    from app.services import consulting_status as status

    for value in ("화상미팅", "회의실 미팅"):
        assert status.tags(value) == [status.OTHER]
        assert not status.is_managed(value)
        assert not status.is_dropped(value)


# --- 6. 엑셀 · 시트 올리기 ----------------------------------------------------

def test_엑셀에도_실리고_이미_받아_둔_파일의_자리는_안_밀린다(allowed, db, users):
    """화면에 보이는 칸이 내려받은 파일에만 없으면, 없다는 사실 자체를 아무도
    눈치채지 못한 채 그 파일이 보고서로 돌아다닌다.

    자리는 **맨 뒤**다 — 화면 차례(`미팅일` 뒤)대로 끼우면 그 뒤 월 열이
    통째로 한 칸씩 밀려 지난번 파일과 나란히 놓고 볼 수가 없다.
    """
    from app.routers import consulting
    from app.services import spreadsheet as sp

    _row(db, users["u1"].id, sheet=STARTUP, position=1, company_name="샘플파",
         meeting_kind="화상미팅")
    res = allowed.get("/api/export/consulting.xlsx")
    assert res.status_code == 200
    rows = sp.read_rows("x.xlsx", res.content, None)
    head = [str(c or "").strip() for c in rows[0]]
    # **뒤에 붙는 묶음 안**에 있다. 그 묶음이 자랄 수 있으므로 `맨 뒤` 로
    # 못 박지 않는다 — 지키는 것은 **앞자리를 하나도 안 밀었다**는 것이다.
    tail = [label for label, _f in consulting.FIXED_EXTRA_EXPORT]
    assert head[-len(tail):] == tail, head
    assert (LABEL, FIELD) in consulting.FIXED_EXTRA_EXPORT
    # **머리글에 두 번 서지 않는다.** `CONSULTING_EXPORT_HEADERS` 가
    # `FIXED_COLUMNS` 에서 뽑으므로, 빼 두지 않으면 같은 칸이 앞뒤 두 자리에
    # 선다 — 그러면 값을 손으로 세우는 줄과 칸 수가 어긋나 **그 뒤 값이 통째로
    # 한 칸씩 밀린다**(기업명 자리에 지역이 찍힌다). 실제로 그렇게 났다.
    assert head.count(LABEL) == 1, head
    # 그 앞자리들은 **하나도 안 밀렸다.**
    assert head[-len(tail) - 1] == "카톡 연결 여부", head
    mine = next(r for r in rows[1:] if "샘플파" in " ".join(str(c or "") for c in r))
    # 머리글 수와 값 수가 같아야 한 칸도 안 밀린다.
    assert len(mine) == len(head), (len(mine), len(head))
    assert mine[head.index(LABEL)] == "화상미팅"
    assert mine[head.index("기업명 / 계약일 / 무료유료 / 계약금, 성과수수료 %")] == "샘플파"


def test_시트를_올릴_때_월별_열로_딸려_들어가지_않는다(db, users):
    """원본 시트에도 이 열이 있을 수 있다. 안 받으면 `parse_rows` 가 못 알아본
    열을 전부 월 열로 삼아, 같은 이름이 표에 두 번 서고(전용 칸은 빈 채로) 값은
    엉뚱한 쪽에 담긴다."""
    from app.routers.consulting import parse_rows

    parsed = parse_rows([
        ["NO", "지역", "미팅일(화상, 회의실)", LABEL, "기업명", "9월 리마인드"],
        ["1", "서울", "9/16 PM2", "회의실 미팅", "샘플하", "통화함"],
    ])
    assert LABEL not in parsed["columns"], parsed["columns"]
    assert parsed["companies"][0][FIELD] == "회의실 미팅"
    assert parsed["companies"][0]["meeting_at"] == "9/16 PM2"
    assert parsed["companies"][0]["notes"] == {"9월 리마인드": "통화함"}


def test_달이_적힌_미팅_열은_안_채간다():
    """`9월 미팅 종류` 같은 이름은 월별 리마인드 열이다 — `fixed` 가 달이 적힌
    이름을 건너뛴다. 채가면 그 달 기록이 갈 곳을 잃고 조용히 사라진다."""
    from app.routers.consulting import parse_rows

    parsed = parse_rows([
        ["NO", "기업명", "9월 미팅 종류"],
        ["1", "샘플거", "화상으로 했음"],
    ])
    assert parsed["columns"] == ["9월 미팅 종류"]
    assert parsed["companies"][0].get(FIELD) is None


# --- 7. 이주 -----------------------------------------------------------------

def test_마이그레이션은_기존_줄에_값을_지어_넣지_않는다():
    """`미팅일` 칸의 `(화상미팅)` 을 읽어다 채우면, 아무 것도 안 적힌 줄
    (더 많다)에 무엇을 넣어도 추측이다. 빈칸이 `아직 안 정함` 이다."""
    src = (ROOT / "alembic" / "versions" / f"{REVISION}.py").read_text(encoding="utf-8")
    for word in ("UPDATE", "update(", "execute("):
        assert word not in src, f"이주가 값을 건드립니다: {word}"


def test_모델과_마이그레이션이_같은_자료형을_말한다():
    import sqlalchemy as sa

    from app.models import ConsultingCompany

    import importlib.util as _u

    spec = _u.spec_from_file_location(REVISION,
                                      ROOT / "alembic" / "versions" / f"{REVISION}.py")
    mod = _u.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert [n for n, _k in mod.ADDED] == [FIELD]
    assert isinstance(mod.ADDED[0][1], sa.String)
    col = ConsultingCompany.__table__.columns[FIELD]
    assert isinstance(col.type, sa.String) and col.nullable


def test_내렸다_올리면_표가_같다(tmp_path):
    """이 저장소는 운영에 올리기 전에 `downgrade` → `upgrade` 를 실제로 돌려
    표가 같은지 본다. 되돌리면 이 칸의 값은 안 돌아온다 — 여기서 처음 생긴
    값이라 옮겨 둘 자리가 없다."""
    if shutil.which("alembic") is None:
        pytest.skip("alembic 명령이 없습니다")
    db_path = tmp_path / "t.db"
    env = {"DATABASE_URL": f"sqlite:///{db_path}"}
    import os

    env = {**os.environ, **env}

    def run(*args):
        return subprocess.run([sys.executable, "-m", "alembic", *args],
                              cwd=ROOT, env=env, capture_output=True, text=True)

    def columns(path):
        con = sqlite3.connect(path)
        try:
            sql = con.execute("select sql from sqlite_master "
                              "where name='consulting_companies'").fetchone()[0]
        finally:
            con.close()
        return {line.strip().split()[0].strip('"')
                for line in sql.split("(", 1)[1].split(",") if line.strip()}

    # **`head` 가 아니라 이 판까지만** 올린다. `head` 로 올리면 뒤에 쌓인 남의
    # 판까지 같이 올라가, 아래 `옆 칸을 안 건드렸나` 대조가 그 판들 때문에
    # 깨진다(`test_consulting_kakao_joined.py` 가 같은 이유로 그렇게 한다).
    assert run("upgrade", REVISION).returncode == 0
    before = columns(db_path)
    assert FIELD in before

    assert run("downgrade", BEFORE).returncode == 0
    assert FIELD not in columns(db_path), \
        "내렸는데 칸이 남아 있다 — `downgrade` 가 제 일을 안 했다"
    assert columns(db_path) == before - {FIELD}, "내리면서 옆 칸까지 건드렸다"

    assert run("upgrade", REVISION).returncode == 0
    assert columns(db_path) == before, "내렸다 올렸더니 표가 달라졌다"


# --- 8. `Meeting.meet_mode` 와 다른 칸 ----------------------------------------

def test_IR_미팅의_대면_화상과_다른_칸이다(allowed, db, users):
    """저쪽은 `meetings` 의 미팅 줄에 `in_person`/`video` 라는 **열쇠**를 담고,
    화면에 보일 때만 `대면`/`화상` 으로 옮긴다(`services/pipeline.py`).
    이쪽은 `consulting_companies` 의 컨설턴트 줄이고 **보이는 말이 곧 값**이다.

    두 표를 잇는 열쇠가 없어(둘 다 `users` 만 가리킨다) 값을 끌어올 수도 없다.
    """
    from app.models import ConsultingCompany, Meeting
    from app.services import pipeline

    assert set(pipeline.MEETING_MODES) == {"in_person", "video"}
    assert set(pipeline.MEETING_MODES.values()) == {"대면", "화상"}
    # 이 표가 쓰는 말은 시트의 말이다 — 저 말과 한 글자도 안 겹친다.
    from app.routers import consulting

    assert set(consulting.MEETING_KIND_CHOICES) == {"화상미팅", "회의실 미팅"}
    assert not set(consulting.MEETING_KIND_CHOICES) & set(pipeline.MEETING_MODES.values())
    # 두 표를 잇는 외래키가 없다.
    for table in (ConsultingCompany.__table__, Meeting.__table__):
        targets = {fk.column.table.name for fk in table.foreign_keys}
        assert "meetings" not in targets or table is Meeting.__table__
    assert "consulting_companies" not in {
        fk.column.table.name for fk in Meeting.__table__.foreign_keys}
