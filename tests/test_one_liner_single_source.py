"""`사업분야` 와 `기업 한줄 소개` 를 한 칸으로 — 정본은 `one_liner`(0051).

## 왜 이 검사가 있나

두 탭이 **같은 것을 다른 칸에 적고 있었다.** 스타트업DB 의 `사업분야`
(`business_desc`)와 IR 기업 현황의 `기업 한줄 소개`(`one_liner`)다. 이름이
다르니 다른 칸처럼 보이지만 둘 다 사업 설명이라, 한쪽을 고쳐도 다른 쪽은
그대로였다.

합치는 일은 **데이터를 옮기는 일**이라 되돌릴 수 없는 실수가 난다. 그래서
여기서 세 가지를 못 박는다.

  1. 옮기기는 **빈 곳만** 채운다 — 이미 적힌 소개를 덮으면 그게 제일 나쁘다
  2. 합치기 전 두 값이 **백업 칸에 그대로** 남는다 (특히 둘 다 있고 글자가
     서로 다른 곳 — 운영에서 97곳이다)
  3. `downgrade` 로 **원래대로 돌아온다**

운영과 같은 크기·같은 분포의 사본(321곳)으로 잰다. 몇 줄짜리 표본으로는
"덮어쓰기가 한 줄에서만 난다" 같은 고장이 안 잡힌다.
"""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PREVIOUS = "0050_deal_queue"
# **`head` 가 아니라 이 판까지만** 올린다. 이 파일이 재는 것은 0051 한 판이
# 자료에 무엇을 했는가인데, `head` 로 두면 뒤에 붙는 판들이 같은 칸을 만져도
# 그 결과가 0051 의 몫으로 읽힌다 — 실제로 0058 이 `business_desc` 를 채우자
# "0051 이 사업분야를 건드렸다" 는 거짓 실패가 났다.
REVISION = "0051_one_liner_single_source"

# 운영 321곳의 분포 그대로. 이 숫자가 곧 사람이 화면에서 보게 될 결과다.
BOTH_SAME = 138        # 둘 다 있고 글자까지 같음
BOTH_DIFFER = 97       # 둘 다 있는데 글자가 다름 ★ 백업이 지켜야 할 곳
DESC_ONLY = 23         # 사업분야만 — 한줄 소개로 옮긴다
ONE_LINER_ONLY = 58    # 한줄 소개만
NEITHER = 5            # 둘 다 빔
TOTAL = BOTH_SAME + BOTH_DIFFER + DESC_ONLY + ONE_LINER_ONLY + NEITHER

# 이름·내용은 전부 **가상값**이다. 이 저장소는 공개라 실데이터를 넣지 않는다.
FAKE = ["가나헬스", "나다물류", "다라소재", "라마핀테크", "마바에듀",
        "바사푸드", "사아로보", "아자바이오", "자차모빌", "차카에너지"]
# 시각은 못 박는다 — 오늘 날짜를 쓰면 내일 다른 것을 재는 검사가 된다.
STAMP = "2026-09-03T09:00:00+09:00"


def _alembic(db: Path, *args: str) -> subprocess.CompletedProcess:
    """따로 뜬 프로세스로 `alembic` 을 돌린다(tests/test_migrations.py 와 같은 방식).

    `alembic/env.py` 는 import 시점에 굳은 `app.config.DATABASE_URL` 을 읽는데,
    테스트 프로세스에서는 그것이 이미 conftest 의 테스트 DB 다.
    """
    env = {**os.environ,
           "DATABASE_URL": f"sqlite:///{db}",
           "DEALFLOW_DATA_DIR": str(db.parent)}
    return subprocess.run([sys.executable, "-m", "alembic", *args],
                          cwd=ROOT, env=env, capture_output=True, text=True)


def _read(db: Path, columns: str) -> list:
    con = sqlite3.connect(db)
    try:
        return con.execute(
            f"SELECT id, {columns} FROM ir_companies ORDER BY id").fetchall()
    finally:
        con.close()


def _columns(db: Path) -> set:
    con = sqlite3.connect(db)
    try:
        return {c[1] for c in con.execute("PRAGMA table_info(ir_companies)")}
    finally:
        con.close()


def _blank(value) -> bool:
    return not (value or "").strip()


def _seed() -> list:
    """운영과 같은 분포의 321곳. `(이름, 한줄소개, 사업분야)`.

    빈 칸은 `None` 과 `""` 를 **섞는다** — 운영에는 둘 다 있고, 한쪽만으로
    재면 "NULL 이던 칸에 빈 글자를 넣어 놓고 되돌렸다고 말하는" 고장을 놓친다.
    """
    out = []

    def add(one_liner, business_desc):
        n = len(out) + 1
        out.append((f"샘플{n:03d}{FAKE[n % len(FAKE)]}", one_liner, business_desc))

    for i in range(BOTH_SAME):
        same = f"{FAKE[i % 10]} 기반 솔루션 {i} | 매출 {i % 30 + 1}억"
        add(same, same)
    for i in range(BOTH_DIFFER):
        # 줄바꿈이 든 값을 일부러 섞는다 — 시트에서 온 글자가 그렇다.
        add(f"사람이 다듬어 쓴 소개 {i} | 누적투자금액 {i % 20 + 1}억",
            f"시트에 적혀 있던 사업 설명 {i}\n둘째 줄도 있다 | Pre Value {i % 50 + 10}억")
    for i in range(DESC_ONLY):
        add(None if i % 2 else "", f"사업분야에만 적혀 있던 설명 {i} | 매출 {i + 1}억")
    for i in range(ONE_LINER_ONLY):
        add(f"한줄 소개에만 적혀 있던 소개 {i}", None if i % 3 else "")
    for i in range(NEITHER):
        add(None if i % 2 else "", None if i % 2 else "")

    assert len(out) == TOTAL
    return out


@pytest.fixture(scope="module")
def cycle(tmp_path_factory) -> dict:
    """운영과 같은 크기의 사본을 만들어 **올렸다 내려 본다.**

    한 번만 돌리고 그때그때의 모습을 찍어 둔다 — 검사마다 321곳을 다시 심으면
    느리기만 하고, 무엇보다 **같은 한 번의 왕복**을 여러 각도로 봐야 앞뒤가
    맞는지 알 수 있다.
    """
    db = tmp_path_factory.mktemp("merge") / "replica.db"

    # 운영과 같은 출발선: 0050 까지 올린 스키마에서 `desc_backup` 을 뗀다.
    # 빈 DB 는 0001 의 `create_all()` 이 지금 모델 전체를 만들어 주므로 새 칸이
    # 이미 있는데, 운영 DB 에는 없다 — 떼어 내야 진짜 운영과 같은 길을 간다.
    up = _alembic(db, "upgrade", PREVIOUS)
    assert up.returncode == 0, up.stdout + up.stderr

    con = sqlite3.connect(db)
    if "desc_backup" in {c[1] for c in con.execute("PRAGMA table_info(ir_companies)")}:
        con.execute("ALTER TABLE ir_companies DROP COLUMN desc_backup")
    con.execute("DELETE FROM ir_companies")
    con.executemany(
        "INSERT INTO ir_companies (name, one_liner, business_desc, contract_status,"
        " summary_status, is_top_deal, created_at, updated_at)"
        " VALUES (?, ?, ?, 'none', 'draft', 0, ?, ?)",
        [(n, o, b, STAMP, STAMP) for n, o, b in _seed()])
    con.commit()
    con.close()

    before = _read(db, "one_liner, business_desc")

    upgraded = _alembic(db, "upgrade", REVISION)
    assert upgraded.returncode == 0, upgraded.stdout + upgraded.stderr
    after = _read(db, "one_liner, business_desc, desc_backup")
    after_columns = _columns(db)

    # 두 번 돌려도 아무 일도 안 일어나야 한다(중간에 끊겼다 다시 도는 길).
    again = _alembic(db, "upgrade", REVISION)
    assert again.returncode == 0, again.stdout + again.stderr
    twice = _read(db, "one_liner, business_desc, desc_backup")

    down = _alembic(db, "downgrade", PREVIOUS)
    assert down.returncode == 0, down.stdout + down.stderr
    restored = _read(db, "one_liner, business_desc")

    return {"before": before, "after": after, "twice": twice,
            "restored": restored, "after_columns": _columns(db) | after_columns,
            "down_columns": _columns(db),
            "up_log": upgraded.stdout, "down_log": down.stdout}


# --- 미리보기 ----------------------------------------------------------------

def test_바꾸기_전에_무엇이_몇_건인지_로그로_남긴다(cycle):
    """데이터를 옮기는 판이다. 끝난 뒤에는 원래 몇 건이었는지 되짚을 길이 없다."""
    log = cycle["up_log"]
    assert f"전체 {TOTAL}곳" in log, log
    assert f"둘 다 있음 {BOTH_SAME + BOTH_DIFFER}곳" in log, log
    assert f"같음 {BOTH_SAME} · 다름 {BOTH_DIFFER}" in log, log
    assert f"사업분야만 {DESC_ONLY}곳" in log, log
    assert f"한줄 소개만 {ONE_LINER_ONLY}곳" in log, log
    assert f"둘 다 빔 {NEITHER}곳" in log, log
    assert f"{DESC_ONLY}곳을 옮겼습니다" in log, log


# --- 옮기기 ------------------------------------------------------------------

def test_사업분야만_있던_곳에만_값이_들어간다(cycle):
    """그 곳들은 IR 화면에도 안 보이고 딜 소개 문구에도 안 실렸다."""
    after = {r[0]: r for r in cycle["after"]}
    moved = 0
    for cid, was_one_liner, was_desc in cycle["before"]:
        if _blank(was_one_liner) and not _blank(was_desc):
            assert after[cid][1] == was_desc, f"{cid}: 안 옮겨졌다"
            moved += 1
    assert moved == DESC_ONLY


def test_이미_적힌_한줄_소개는_한_글자도_안_덮인다(cycle):
    """제일 나쁜 고장이다 — 사람이 쓴 소개가 소리 없이 사라진다."""
    after = {r[0]: r for r in cycle["after"]}
    kept = 0
    for cid, was_one_liner, was_desc in cycle["before"]:
        if _blank(was_one_liner):
            continue
        assert after[cid][1] == was_one_liner, f"{cid}: 있던 한줄 소개가 덮였다"
        kept += 1
    assert kept == BOTH_SAME + BOTH_DIFFER + ONE_LINER_ONLY


def test_사업분야_칸_자체는_안_건드린다(cycle):
    """화면에서만 뗀다 — 칸을 지우면 백업과 원본이 같은 판에서 함께 사라진다."""
    after = {r[0]: r for r in cycle["after"]}
    for cid, _one_liner, was_desc in cycle["before"]:
        assert after[cid][2] == was_desc, f"{cid}: business_desc 가 바뀌었다"


# --- 백업 --------------------------------------------------------------------

def test_둘_다_있고_글자가_다른_97곳의_사업분야가_백업에_그대로_있다(cycle):
    """**하나라도 사라지면 안 된다.**

    합치고 나면 화면에는 `one_liner` 만 남는다. 그 97곳은 두 칸의 글자가 서로
    달라서, 백업이 없으면 `business_desc` 쪽에 적혀 있던 말이 아무 데서도
    안 보이게 된다.
    """
    after = {r[0]: r for r in cycle["after"]}
    alive = 0
    for cid, was_one_liner, was_desc in cycle["before"]:
        if _blank(was_one_liner) or _blank(was_desc):
            continue
        if was_one_liner.strip() == was_desc.strip():
            continue
        saved = json.loads(after[cid][3])
        assert saved["business_desc"] == was_desc, f"{cid}: 사업분야가 안 남았다"
        assert saved["one_liner"] == was_one_liner, f"{cid}: 한줄 소개가 안 남았다"
        alive += 1
    assert alive == BOTH_DIFFER, f"{alive}곳만 살아 있다 — {BOTH_DIFFER}곳이어야 한다"


def test_값이_있던_곳은_전부_백업이_생기고_둘_다_빈_곳은_안_생긴다(cycle):
    """`{}` 를 적어 두면 "백업이 있다" 는 줄과 구분이 안 된다."""
    after = {r[0]: r for r in cycle["after"]}
    with_backup = sum(1 for r in cycle["after"] if r[3])
    assert with_backup == TOTAL - NEITHER

    for cid, was_one_liner, was_desc in cycle["before"]:
        if _blank(was_one_liner) and _blank(was_desc):
            assert after[cid][3] is None, f"{cid}: 지킬 것이 없는데 백업이 생겼다"


def test_비어_있던_칸은_빈_글자가_아니라_null_로_남는다(cycle):
    """`""` 로 뭉개면 되돌릴 때 NULL 이던 칸에 빈 글자가 들어간다."""
    after = {r[0]: r for r in cycle["after"]}
    seen = 0
    for cid, was_one_liner, was_desc in cycle["before"]:
        if was_one_liner is not None or not after[cid][3]:
            continue
        assert json.loads(after[cid][3])["one_liner"] is None, f"{cid}"
        seen += 1
    assert seen, "NULL 이던 줄을 하나도 못 봤다 — 표본이 잘못됐다"


def test_두_번_돌려도_백업이_덮이지_않는다(cycle):
    """두 번째에는 `one_liner` 이 이미 채워진 뒤다. 다시 찍으면 "원래 비어
    있었다" 는 사실이 덮여, 되돌릴 근거가 그 순간 사라진다."""
    assert cycle["twice"] == cycle["after"]


# --- 되돌리기 ----------------------------------------------------------------

def test_되돌리면_원래대로_돌아온다(cycle):
    """`NULL` 이던 칸은 `NULL` 로, 빈 글자이던 칸은 빈 글자로."""
    assert cycle["restored"] == cycle["before"]
    assert f"{DESC_ONLY}곳을 되돌렸습니다" in cycle["down_log"], cycle["down_log"]


def test_되돌리면_백업_칸도_사라진다(cycle):
    assert "desc_backup" in cycle["after_columns"]
    assert "desc_backup" not in cycle["down_columns"]


# --- 되돌린 뒤에 사람이 손댄 줄 -----------------------------------------------

def test_옮긴_뒤에_사람이_고쳐_쓴_줄은_되돌리기가_안_건드린다(tmp_path):
    """되돌리기가 손글씨를 지우면 안 된다.

    올린 뒤에 그 소개를 사람이 다시 쓸 수 있다. 백업만 보고 무턱대고 되돌리면
    그 문장이 사라진다 — 지금 값이 **이 판이 써 넣은 값 그대로일 때만** 되돌린다.
    """
    db = tmp_path / "edited.db"
    up = _alembic(db, "upgrade", PREVIOUS)
    assert up.returncode == 0, up.stdout + up.stderr

    con = sqlite3.connect(db)
    if "desc_backup" in {c[1] for c in con.execute("PRAGMA table_info(ir_companies)")}:
        con.execute("ALTER TABLE ir_companies DROP COLUMN desc_backup")
    con.execute("DELETE FROM ir_companies")
    con.execute(
        "INSERT INTO ir_companies (id, name, one_liner, business_desc,"
        " contract_status, summary_status, is_top_deal, created_at, updated_at)"
        " VALUES (1, '샘플가나헬스', NULL, '사업분야에만 적혀 있던 설명',"
        " 'none', 'draft', 0, ?, ?)", (STAMP, STAMP))
    con.commit()
    con.close()

    assert _alembic(db, "upgrade", "head").returncode == 0
    assert _read(db, "one_liner")[0][1] == "사업분야에만 적혀 있던 설명"

    # 올린 뒤에 사람이 다시 썼다.
    con = sqlite3.connect(db)
    con.execute("UPDATE ir_companies SET one_liner = '사람이 다시 쓴 소개' WHERE id = 1")
    con.commit()
    con.close()

    down = _alembic(db, "downgrade", PREVIOUS)
    assert down.returncode == 0, down.stdout + down.stderr
    assert _read(db, "one_liner")[0][1] == "사람이 다시 쓴 소개", \
        "되돌리기가 그 뒤에 쓴 손글씨를 지웠다"
    assert "그대로 둡니다" in down.stdout, down.stdout


# --- 화면 --------------------------------------------------------------------

@pytest.fixture()
def merged(db):
    """합치기가 끝난 기업 하나 — 백업까지 들어 있다."""
    from app.models import IrCompany

    row = IrCompany(
        name="샘플가나헬스",
        one_liner="사람이 다듬어 쓴 소개",
        business_desc="시트에 적혀 있던 사업 설명",
        desc_backup=json.dumps({"one_liner": "사람이 다듬어 쓴 소개",
                                "business_desc": "시트에 적혀 있던 사업 설명"},
                               ensure_ascii=False))
    db.add(row)
    db.commit()
    return row


def test_두_탭은_이제_서로_다른_칸을_보여_준다(logged_in, merged):
    """0051 은 두 탭을 한 칸으로 묶었고, **0058 이 다시 갈랐다.**

    갈랐다고 0051 이 되돌려진 것은 아니다 — 0051 이 없앤 것은 *같은 뜻을 담은
    두 칸*이었고, 지금 갈라진 둘은 **재료와 그 조합 결과**라 뜻이 다르다.
    (조합이 두 탭에서 어떻게 보이는지는 tests/test_one_liner_tab_split.py 가 잰다.)
    """
    ir = logged_in.get("/companies").text
    assert 'data-field="one_liner"' in ir, "IR 기업 현황은 조합 결과를 보여 준다"
    assert "사람이 다듬어 쓴 소개" in ir

    db_tab = logged_in.get("/companies?tab=db").text
    assert 'data-field="business_desc"' in db_tab, "스타트업DB 는 재료를 보여 준다"
    assert "시트에 적혀 있던 사업 설명" in db_tab


def test_재료를_고치면_조합_결과가_따라온다(logged_in, db):
    """0051 이 지키려던 것 — "고쳤는데 저쪽이 그대로" 가 없어야 한다.

    칸이 갈라졌어도 **맞춰 주는 코드는 여전히 없다.** 스타트업DB 에서 재료를
    고치면 조합이 다시 만들어져 IR 기업 현황이 따라온다(one_liner.sync).
    """
    from app.models import IrCompany

    row = IrCompany(name="샘플나다물류", business_desc="물류 최적화 SaaS",
                    one_liner="물류 최적화 SaaS")      # 조합값 그대로 = AUTO
    db.add(row)
    db.commit()

    logged_in.patch(f"/api/companies/{row.id}",
                    json={"business_desc": "스타트업DB 에서 고친 소개"})
    assert "스타트업DB 에서 고친 소개" in logged_in.get("/companies?tab=db").text
    assert "스타트업DB 에서 고친 소개" in logged_in.get("/companies").text, \
        "재료를 고쳤는데 딜 소개 문구가 따라오지 않았다"


def test_스타트업DB_에는_이제_사업분야_머리글이_없다(logged_in, merged):
    """이름만 다른 같은 칸이 둘 다 보이면 어느 쪽이 정본인지 다시 알 수 없다.

    `business_desc` 가 이 탭으로 돌아온 뒤에도(0058) 머리글은 `기업 한줄 소개`
    다 — `사업분야` 로 되돌리면 옆 탭의 `사업분야 대분류` 와 같은 말이 된다.
    """
    import re

    head = logged_in.get("/companies?tab=db").text.split("</thead>")[0]
    names = [re.sub(r"<[^>]+>", "", m).strip()
             for _a, m in re.findall(r"<th\b([^>]*)>(.*?)</th>", head, re.S)]
    assert "사업분야" not in names, names
    assert "기업 한줄 소개" in names, names


def test_합치기_전_값은_표가_아니라_수정창에서만_본다(logged_in, merged):
    """표는 이미 화면보다 넓다. 이 값은 매일 보는 값이 아니라 한 번 열어 보는 기록이다."""
    row = logged_in.get(f"/api/companies/{merged.id}").json()
    labels = [line["label"] for line in row["desc_backup"]]
    assert labels == ["사업분야 (스타트업DB)", "기업 한줄 소개 (IR 기업 현황)"], labels
    assert row["desc_backup"][0]["value"] == "시트에 적혀 있던 사업 설명"

    # 표에는 안 실린다 — 실으면 321줄이 통째로 두 배가 된다.
    assert "합치기 전 값" in logged_in.get("/companies?tab=db").text  # 수정창 라벨
    body = logged_in.get("/companies?tab=db").text.split("</table>")[0]
    assert "backup-line" not in body


def test_백업이_없는_기업에서는_상자가_통째로_숨는다(logged_in, db):
    """빈 상자가 늘 떠 있으면 그게 무슨 뜻인지 매번 다시 읽어야 한다."""
    from app.models import IrCompany

    row = IrCompany(name="샘플나다물류", one_liner="소개만 있는 기업")
    db.add(row)
    db.commit()
    assert logged_in.get(f"/api/companies/{row.id}").json()["desc_backup"] == []


def test_깨진_백업이_화면을_죽이지_않는다(logged_in, db):
    """되살려 보려고 연 화면이 그것 때문에 안 열리면 백업을 둔 뜻이 없다."""
    from app.models import IrCompany

    row = IrCompany(name="샘플다라소재", one_liner="소개", desc_backup="{깨진 값")
    db.add(row)
    db.commit()
    assert logged_in.get(f"/api/companies/{row.id}").json()["desc_backup"] == []
    assert logged_in.get("/companies?tab=db").status_code == 200


# --- 브라우저 ----------------------------------------------------------------

@pytest.mark.skipif(shutil.which("node") is None,
                    reason="node 미설치 — 브라우저 로직 테스트 생략")
def test_수정창의_합치기_전_값은_브라우저에_있으니_거기서_잰다():
    """읽기 전용인가 · 다시 열어도 줄이 쌓이지 않는가 · 없으면 숨는가.

    `companies.js` 를 **그대로 돌려서** 본다 — 규칙을 옮겨 적으면 두 벌이 되어
    어긋나도 모른다(tests/js/company_desc_backup_test.js).
    로컬에서는 `node tests/js/company_desc_backup_test.js` 로도 돈다.
    """
    script = ROOT / "tests" / "js" / "company_desc_backup_test.js"
    out = subprocess.run([shutil.which("node"), str(script)],
                         capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stdout + out.stderr
