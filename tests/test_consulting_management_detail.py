"""`기업 관리` 에서 갈라져 나온 **`기업 내용`** — 칸과 **옮기는 스크립트** 둘 다.

> "투자 컨설턴트 메뉴의 리스트에서 **기업관리 컬럼의 내용을 분리해서 기업 내용
>  컬럼을 신설**하고 그쪽으로 옮겨줘"

## 무엇을 "분리" 로 읽었나

원본 머리글이 `기업 관리 [ 드랍 이유 상세하게 기입 / 관리중 / 백업팀으로 전환 ]`
이다 — 한 칸에 **상태**와 **그 이유를 상세하게 적은 글**을 같이 적으라고 했고,
값이 `상태 : 상세` 꼴로 적혀 있다. 상태는 남고 상세가 옮겨 간다.

## 이 파일이 지키는 것

  1. 칸이 정말 저장되고 다시 읽힌다 · 자리는 `기업 관리` 바로 오른쪽이다.
  2. **갈래 판정이 이 칸을 안 본다** — 갈라낸 보람이 거기 있다.
  3. 검색에는 실린다 — 갈라내기 전에는 걸리던 글이다.
  4. 계약 탭에는 안 선다.
  5. **이주는 값을 한 줄도 안 옮긴다** — 옮기는 것은 사람이 돌리는 스크립트다.
  6. 스크립트가 **구분자가 있는 줄만** 나누고, 갈래가 바뀌면 **멈추고**,
     되돌리면 **원래대로 돌아온다**.
  7. 내렸다 올려도 표가 같다.

이름·기업명·내용은 전부 지어낸 값이다 — 저장소가 공개다.
"""
from __future__ import annotations

import json
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

LABEL = "기업 내용"
FIELD = "management_detail"
REVISION = "0080_consulting_management_detail"
SCRIPT = ROOT / "scripts" / "split_consulting_management.py"


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
    m = re.search(r"<thead>(.*?)</thead>", html, re.S)
    assert m, "표 머리글을 찾지 못했습니다"
    out = []
    for cell in re.findall(r"<th\b[^>]*>(.*?)</th>", m.group(1), re.S):
        cell = re.sub(r"<form\b.*?</form>", " ", cell, flags=re.S)
        out.append(" ".join(re.sub(r"<[^>]+>", " ", cell).split()))
    return out


def _fields(html: str) -> list:
    return re.findall(r'data-field="([^"]+)"', html.split("<tbody>", 1)[1])


# --- 1. 칸 -------------------------------------------------------------------

def test_고쳐지고_다시_읽힌다(allowed, db, users):
    from app.models import ConsultingCompany

    row = _row(db, users["u1"].id, sheet=STARTUP, position=1, company_name="샘플가")
    text = "몇 차례 확인했으나 일정이 밀렸다\n다음 달에 다시 본다"
    assert allowed.patch(f"/api/consulting/{row.id}",
                         json={FIELD: text}).status_code == 200
    db.expire_all()
    # **줄바꿈이 살아 있다** — 긴 글 칸이라 `deal_pitch` 와 같다.
    assert getattr(db.get(ConsultingCompany, row.id), FIELD) == text
    assert allowed.get(f"/api/consulting/{row.id}").json()[FIELD] == text


def test_기업_관리_바로_오른쪽에_선다(allowed, db, users):
    """사용자가 부른 자리 그대로다. 머리글 차례와 칸 차례가 어긋나면 그 뒤가
    통째로 밀린다."""
    from app.routers import consulting

    _row(db, users["u1"].id, sheet=STARTUP, position=1, company_name="샘플나")
    heads = _heads(_open(allowed, STARTUP))
    assert heads[heads.index("기업 관리") + 1] == LABEL, heads
    fields = _fields(_open(allowed, STARTUP))
    assert fields[fields.index("management") + 1] == FIELD, fields
    labels = [label for label, _f in consulting.FIXED_COLUMNS]
    at = labels.index("기업 관리 [ 드랍 이유 상세하게 기입 / 관리중 / 백업팀으로 전환 ]")
    assert consulting.FIXED_COLUMNS[at + 1] == (LABEL, FIELD)


def test_긴_글_칸이다(allowed, db, users):
    """옆 `기업 관리`·`딜 소개문구` 와 같은 표시(`multi`)를 쓴다 — 누르면
    textarea 가 열려 엔터로 줄을 나눌 수 있다. 이 표만의 표시라 다른 화면의
    `data-type="long"` 을 달면 아무 일도 안 일어난다."""
    _row(db, users["u1"].id, sheet=STARTUP, position=1, company_name="샘플다")
    body = _open(allowed, STARTUP)
    assert f'class="cell multi" data-field="{FIELD}"' in body


def test_필터를_안_세우고_죽은_속성도_안_싣는다(allowed, db, users):
    """값이 자유 문장이라 줄마다 다르다 — 고를 것이 모이지 않는다
    (`딜 소개문구`·`미팅일` 과 같은 이유). 필터를 안 세웠으니 행에도 값을
    실으면 안 된다: 아무 머리글도 안 보는 죽은 속성이 된다
    (`tests/test_filter_columns.py` 의 2번)."""
    _row(db, users["u1"].id, sheet=STARTUP, position=1, company_name="샘플라",
         management_detail="상세한 사정")
    body = _open(allowed, STARTUP)
    assert "detail:" not in body
    assert "data-f-detail" not in body
    assert f'data-field="{FIELD}"' in body
    assert 'data-filters="mgmt:기업 관리"' in body       # 왼쪽 칸의 필터는 그대로


# --- 2. 갈래 판정은 이 칸을 안 본다 -------------------------------------------

def test_칩과_KPI_는_이_칸을_안_본다(allowed, db, users):
    """**갈라낸 보람이 여기 있다.** 상세 글에 `드랍` 이라는 낱말이 우연히 들어
    있어도 그 줄은 드랍으로 안 걸려야 한다 — 섞여 있을 때 실제로 그랬다."""
    _row(db, users["u1"].id, sheet=STARTUP, position=1, company_name="샘플마",
         management="관리 중",
         management_detail="드랍 이야기가 나왔지만 백업팀으로 넘기지 않기로 했다")
    body = _open(allowed, STARTUP)
    m = re.search(r'data-f-mgmt="([^"]*)"', body)
    assert m and m.group(1) == "관리 중", m and m.group(1)
    assert re.search(r'data-kpi="dropped">0<', body), "드랍 KPI 가 0이어야 한다"


def test_브라우저_쪽_규칙도_이_칸을_안_본다():
    """칸을 눌러 고친 직후를 다시 세는 것은 브라우저다(`refreshRowFlags`).
    거기서 이 칸을 보면 서버와 갈려, 고친 직후와 새로고침 뒤에 같은 줄이
    서로 다른 갈래로 걸린다."""
    js = (ROOT / "app" / "static" / "js" / "consulting.js").read_text(encoding="utf-8")
    assert FIELD not in js, "브라우저가 이 칸을 갈래 판정에 끌어들였습니다"


# --- 3. 검색 · 탭 -------------------------------------------------------------

def test_검색에는_넣는다(allowed, db, users):
    """갈라내기 전에는 `기업 관리` 에 들어 있어 검색에 걸리던 글이다. 여기서
    빼면 옮긴 뒤에 "찾던 기업이 검색에 안 나온다" 가 된다."""
    _row(db, users["u1"].id, sheet=STARTUP, position=1, company_name="샘플바",
         management_detail="회생신청 때문에 멈춤")
    m = re.search(r'data-search="([^"]*)"', _open(allowed, STARTUP))
    assert m and "회생신청" in m.group(1)


def test_계약_탭에는_안_선다(allowed, db, users):
    """저 탭의 `management` 는 `계약여부`(`무료`/`유료`)라는 **다른 물음**이라
    갈라낼 상세가 없다."""
    _row(db, users["u1"].id, sheet=CONTRACT, position=1, company_name="샘플사",
         management="무료", management_detail="옮긴 적 없는 글")
    body = _open(allowed, CONTRACT)
    assert LABEL not in _heads(body)
    assert FIELD not in _fields(body)
    assert "옮긴 적 없는 글" not in body


def test_경영본부_탭에는_선다(allowed, db, users):
    """`기업 관리` 와 **같은 묶음**(`FIXED_COLUMNS`)이다 — 두 탭이 같이 쓴다.
    실제로 그 탭의 줄에도 `관리 중 : …` 꼴 값이 들어 있다."""
    _row(db, users["u1"].id, sheet=HANDOVER, position=1, company_name="샘플아")
    assert LABEL in _heads(_open(allowed, HANDOVER))


@pytest.mark.parametrize("sheet", [STARTUP, HANDOVER, CONTRACT])
def test_머리글_수와_칸_수와_colspan_이_맞는다(allowed, db, users, sheet):
    body = _open(allowed, sheet)
    head = len(_heads(body))
    m = re.search(r'colspan="(\d+)"', body)
    assert m and int(m.group(1)) == head, (sheet, m and m.group(1), head)
    _row(db, users["u1"].id, sheet=sheet, position=1, company_name="샘플자")
    body = _open(allowed, sheet)
    first = re.search(r"<tbody>(.*?)</tr>", body, re.S)
    assert first
    assert len(re.findall(r"<td\b", first.group(1))) == len(_heads(body))


def test_엑셀에도_실리고_이미_받아_둔_파일의_자리는_안_밀린다(allowed, db, users):
    from app.routers import consulting
    from app.services import spreadsheet as sp

    _row(db, users["u1"].id, sheet=STARTUP, position=1, company_name="샘플차",
         management_detail="상세 사정")
    res = allowed.get("/api/export/consulting.xlsx")
    rows = sp.read_rows("x.xlsx", res.content, None)
    head = [str(c or "").strip() for c in rows[0]]
    assert head[-1] == LABEL, head
    assert head.count(LABEL) == 1, head
    assert consulting.FIXED_EXTRA_EXPORT[-1] == (LABEL, FIELD)
    mine = next(r for r in rows[1:] if "샘플차" in " ".join(str(c or "") for c in r))
    assert len(mine) == len(head)
    assert mine[head.index(LABEL)] == "상세 사정"


def test_시트를_올릴_때_월별_열로_딸려_들어가지_않는다():
    from app.routers.consulting import parse_rows

    parsed = parse_rows([
        ["NO", "기업명", "기업 관리 [ 드랍 이유 상세하게 기입 ]", LABEL, "9월 리마인드"],
        ["1", "샘플카", "드랍", "연락이 닿지 않음", "부재중"],
    ])
    assert LABEL not in parsed["columns"], parsed["columns"]
    assert parsed["companies"][0]["management"] == "드랍"
    assert parsed["companies"][0][FIELD] == "연락이 닿지 않음"


# --- 4. 이주는 값을 안 옮긴다 -------------------------------------------------

def test_이주는_값을_한_줄도_안_옮긴다():
    """`alembic upgrade` 는 컨테이너가 뜨면서 저절로 도는 자리다
    (`RUN_MIGRATIONS=1`). 거기서 운영 자료를 바꾸면 아무도 보고 있지 않을 때
    바뀌고 결과가 틀려도 알아챌 사람이 없다."""
    src = (ROOT / "alembic" / "versions" / f"{REVISION}.py").read_text(encoding="utf-8")
    for word in ("UPDATE", "update(", "execute("):
        assert word not in src, f"이주가 값을 건드립니다: {word}"
    assert "scripts/split_consulting_management.py" in src, \
        "옮기는 길이 어디인지 이주 머리글에 적혀 있어야 한다"


def test_내렸다_올리면_표가_같다(tmp_path):
    if shutil.which("alembic") is None and not (ROOT / "alembic.ini").exists():
        pytest.skip("alembic 이 없습니다")
    import os

    db_path = tmp_path / "t.db"
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{db_path}"}

    def run(*args):
        return subprocess.run([sys.executable, "-m", "alembic", *args],
                              cwd=ROOT, env=env, capture_output=True, text=True)

    assert run("upgrade", "head").returncode == 0
    con = sqlite3.connect(db_path)
    sql = con.execute(
        "select sql from sqlite_master where name='consulting_companies'").fetchone()[0]
    con.close()
    assert FIELD in sql
    down = run("downgrade", "0079_consulting_meeting_kind")
    assert down.returncode == 0, down.stdout + down.stderr
    con = sqlite3.connect(db_path)
    sql = con.execute(
        "select sql from sqlite_master where name='consulting_companies'").fetchone()[0]
    con.close()
    assert FIELD not in sql, "내렸는데 칸이 남아 있다"
    assert run("upgrade", "head").returncode == 0
    con = sqlite3.connect(db_path)
    sql = con.execute(
        "select sql from sqlite_master where name='consulting_companies'").fetchone()[0]
    con.close()
    assert FIELD in sql


# --- 5. 옮기는 스크립트 -------------------------------------------------------

def _plan(db):
    """스크립트의 계산만 떼어 부른다 — DB 를 안 건드린다."""
    import importlib.util as _u

    from app.services import consulting_sheets as cs

    spec = _u.spec_from_file_location("split_mgmt", SCRIPT)
    mod = _u.module_from_spec(spec)
    spec.loader.exec_module(mod)
    labels = {s.label for s in cs.ensure(db) if s.kind == cs.CONTRACT}
    return mod, mod._plan(db, labels), labels


@pytest.mark.parametrize("before,head,tail", [
    ("드랍 : 연락이 닿지 않았다", "드랍", "연락이 닿지 않았다"),
    ("관리 중 : 미팅 완료", "관리 중", "미팅 완료"),
    ("드랍：전각 구분자도 본다", "드랍", "전각 구분자도 본다"),
])
def test_구분자가_있는_줄만_나눈다(db, users, before, head, tail):
    from app.models import ConsultingCompany

    row = _row(db, users["u1"].id, sheet=STARTUP, position=1,
               company_name="샘플타", management=before)
    mod, plan, labels = _plan(db)
    assert [m["id"] for m in plan["move"]] == [row.id]
    assert plan["move"][0]["head"] == head
    assert plan["move"][0]["tail"] == tail
    mod._apply(db, plan, _tmp_backup())
    db.expire_all()
    got = db.get(ConsultingCompany, row.id)
    assert got.management == head
    assert got.management_detail == tail


_BACKUPS = []


def _tmp_backup():
    import tempfile

    p = pathlib.Path(tempfile.mkdtemp()) / "backup.json"
    _BACKUPS.append(p)
    return p


@pytest.mark.parametrize("value", [
    "관리 중",                       # 상태만 — 나눌 것이 없다
    "백업팀으로 전환 예정이고 아직 정리 중",   # 구분자가 없다
    "드랍 :",                        # 뒤가 비었다
    ": 앞이 비었다",                  # 앞이 비었다
])
def test_구분자가_없거나_한쪽이_비면_손대지_않는다(db, users, value):
    """어디까지가 상태인지 **아무도 정한 적이 없다.** 빈칸에서 갈라 넣으면
    앱이 쓴 적 없는 경계를 지어내는 것이 된다."""
    from app.models import ConsultingCompany

    row = _row(db, users["u1"].id, sheet=STARTUP, position=1,
               company_name="샘플파", management=value)
    _mod, plan, _labels = _plan(db)
    assert plan["move"] == []
    assert plan["keep"] == 1
    assert db.get(ConsultingCompany, row.id).management == value


def test_계약_탭의_줄은_건너뛴다(db, users):
    """저 칸은 `계약여부`(`무료`/`유료`)라는 다른 물음이다."""
    _row(db, users["u1"].id, sheet=CONTRACT, position=1, company_name="샘플하",
         management="유료 : 90만")
    _mod, plan, _labels = _plan(db)
    assert plan["move"] == []
    assert plan["skipped"] == 1


def test_이미_상세가_들어_있는_줄은_안_덮는다(db, users):
    """사람이 손으로 적어 둔 글을 지우면 안 된다."""
    _row(db, users["u1"].id, sheet=STARTUP, position=1, company_name="샘플거",
         management="드랍 : 옮길 글", management_detail="이미 적어 둔 글")
    _mod, plan, _labels = _plan(db)
    assert plan["move"] == []
    assert plan["skipped"] == 1


def test_갈래가_바뀌면_멈춘다(db, users):
    """나누고 나서 `관리 중` 이던 줄이 `기타 메모` 로 떨어지면 위 KPI 와 칩
    수가 **조용히** 달라진다. 그런 줄이 있으면 사람이 먼저 봐야 한다."""
    from app.services import consulting_status as status

    _row(db, users["u1"].id, sheet=STARTUP, position=1, company_name="샘플너",
         management="아직 정리 안 됨 : 관리 중이라고 적으려던 것")
    _mod, plan, _labels = _plan(db)
    assert plan["tag_change"], "갈래가 바뀌는데 못 잡았습니다"
    row_id, before, after = plan["tag_change"][0]
    assert status.MANAGED in before and status.MANAGED not in after


def test_옮겼다가_되돌리면_원래대로_돌아온다(db, users):
    """`alembic downgrade` 로는 안 돌아온다 — 칸을 지우는 일이라 옮겨 둔 글이
    같이 사라진다. 되돌리는 길은 이 스크립트 안에 있다."""
    from app.models import ConsultingCompany

    before = "드랍 : 몇 차례 확인했으나 진행이 어렵다"
    row = _row(db, users["u1"].id, sheet=STARTUP, position=1,
               company_name="샘플더", management=before)
    mod, plan, labels = _plan(db)
    backup = _tmp_backup()
    mod._apply(db, plan, backup)
    db.expire_all()
    assert db.get(ConsultingCompany, row.id).management == "드랍"

    mod._revert(db, labels)
    db.expire_all()
    got = db.get(ConsultingCompany, row.id)
    assert got.management == before, got.management
    assert not got.management_detail


def test_백업_파일에서_글자_그대로_되돌린다(db, users):
    """구분자 앞뒤 공백이 시트마다 다를 수 있다(`드랍:…` 처럼 붙여 적은 줄).
    그런 줄은 다시 붙이는 것으로 원본이 안 되므로 **옮기기 전 값을 통째로**
    담아 둔다."""
    from app.models import ConsultingCompany

    before = "드랍:공백 없이 적은 줄"
    row = _row(db, users["u1"].id, sheet=STARTUP, position=1,
               company_name="샘플러", management=before)
    mod, plan, _labels = _plan(db)
    assert plan["lossy"] == 1, "되붙일 때 글자가 달라지는 줄을 못 셌습니다"
    backup = _tmp_backup()
    mod._apply(db, plan, backup)
    saved = json.loads(backup.read_text(encoding="utf-8"))
    assert saved["rows"] == [{"id": row.id, "management": before}]
    assert saved["revision"] == REVISION

    mod._revert_from(db, backup)
    db.expire_all()
    got = db.get(ConsultingCompany, row.id)
    assert got.management == before
    assert not got.management_detail


def test_미리보기가_기본이다():
    """`--apply` 없이 돌리면 아무 것도 안 바뀐다. 운영 자료를 건드리는
    도구라, 기본값이 조용히 쓰는 쪽이면 안 된다
    (`scripts/import_consulting.py` 가 같은 규칙이다)."""
    src = SCRIPT.read_text(encoding="utf-8")
    assert '"--apply", action="store_true"' in src
    assert "if not args.apply:" in src
    assert '"--revert"' in src and '"--revert-from"' in src
    # 백업을 **쓰기 전에** 낸다 — 되돌릴 근거 없이 바꾸지 않는다.
    body = src.split("def _apply(", 1)[1]
    assert body.index("backup.write_text") < body.index("db.commit()")
