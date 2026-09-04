"""스타트업DB 는 **재료**를, IR 기업 현황은 **조합 결과**를 보여 준다(0058).

## 왜 이 검사가 있나

0051 이 두 탭을 한 칸(`one_liner`)으로 합쳤더니, 그 칸에 든 것이 자동 조합의
**결과**라 스타트업DB 탭에도 조합 문구가 그대로 나왔다.

    사업 설명 | 매출 23년 2억, 24년 4억 | 누적투자금액 11억 | Pre Value 200억

스타트업DB 는 그 조각들을 **넣는 자리**다. 넣는 자리에 결과가 서 있으면 무엇을
고쳐야 그 줄이 바뀌는지 화면에서 알 수 없고, 매출·누적투자금액은 바로 옆 칸에
또 적혀 있어 같은 숫자가 한 줄에 두 번 보인다. 그래서 두 탭이 다른 칸을 본다.

    IR 기업 현황  머리글 `딜 소개 문구 회사개요`  → one_liner      (조합 결과)
    스타트업DB    머리글 `기업 한줄 소개`         → business_desc  (재료)

**칸을 새로 파지 않았다.** `business_desc` 는 0020 부터 있던 칸이고 조합의 첫
토막이 곧 그 값이다 — 0051 이 화면에서만 뗐을 뿐 지우지 않았다.

## 무엇을 못 박나

1. 스타트업DB 탭에 **조합 문구가 안 나온다** (매출·누적투자금액 토막이 없다)
2. IR 기업 현황 탭에는 **조합 문구가 그대로** 나온다
3. 두 머리글 이름, 그리고 [수정] 창이 부르는 이름
4. 갈라도 **아무 값이 안 지워진다** — 이주는 빈 칸만 채우고, 화면에서 재료를
   고쳐도 사람이 쓴 딜 소개 문구는 그대로다

값은 전부 가상값이다 — 저장소가 공개다.
"""
from __future__ import annotations

import os
import re
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "app" / "templates" / "companies.html"
PREVIOUS = "0057_send_item_files"
STAMP = "2026-09-04T09:00:00+09:00"

# 재료가 다 찬 기업 하나. 조합하면 아래 `COMPOSED` 가 나온다.
SOURCE = dict(business_desc="비전AI 기반 미세먼지 측정 솔루션",
              revenue_2023="2억", revenue_2024="4억",
              funding_total=1100, pre_value=20000)
COMPOSED = ("비전AI 기반 미세먼지 측정 솔루션 | 매출 23년 2억, 24년 4억"
            " | 누적투자금액 11억 | Pre Value 200억")


@pytest.fixture()
def composed(db):
    """조합 문구가 `one_liner` 에 들어 있는 기업 — 화면이 보게 될 그 상태."""
    from app.models import IrCompany
    from app.services.one_liner import compose_one_liner

    row = IrCompany(name="샘플가나헬스", **SOURCE)
    made = compose_one_liner(row)
    assert made == COMPOSED, made        # 조합 형식이 바뀌면 여기서 먼저 걸린다
    row.one_liner = made
    db.add(row)
    db.commit()
    return row


def _table(html: str, tab: str) -> str:
    """그 탭이 실제로 그린 표 한 덩이. `title` 속성까지 본다."""
    body = html.split('<table class="grid-table"', 1)[1]
    return body.split("</table>", 1)[0]


# --- ① 스타트업DB 탭에는 조합 문구가 없다 -------------------------------------

def test_스타트업DB_탭에는_조합_문구가_안_나온다(logged_in, composed):
    """넣는 자리에 결과가 서 있으면 무엇을 고쳐야 바뀌는지 알 수 없다."""
    table = _table(logged_in.get("/companies?tab=db").text, "db")

    assert "비전AI 기반 미세먼지 측정 솔루션" in table, "재료가 안 보인다"
    assert 'data-field="business_desc"' in table, "고칠 칸이 재료 칸이 아니다"
    for piece in ("매출 23년 2억", "누적투자금액 11억", "Pre Value 200억"):
        assert piece not in table.split('data-field="business_desc"', 1)[1] \
            .split("</td>", 1)[0], f"소개 칸에 조합 토막 `{piece}` 이 남아 있다"
    assert COMPOSED not in table, "조합 문구가 통째로 실려 있다"


def test_숫자는_제_칸에_그대로_있다(logged_in, composed):
    """조합을 뺐다고 숫자가 사라지는 것은 아니다 — 원래 제 칸이 따로 있다."""
    table = _table(logged_in.get("/companies?tab=db").text, "db")
    for field, shown in (("revenue_2023", "2억"), ("revenue_2024", "4억"),
                         ("funding_total", "11"), ("pre_value", "200")):
        cell = table.split(f'data-field="{field}"', 1)[1].split("</td>", 1)[0]
        assert shown in cell, f"{field} 칸에 {shown} 이 없다"


# --- ② IR 기업 현황 탭에는 그대로 나온다 --------------------------------------

def test_IR_기업_현황_탭에는_조합_문구가_그대로_나온다(logged_in, composed):
    """딜 소개 문구에 그대로 나가는 줄이다 — 여기서까지 빠지면 쓸 곳이 없다."""
    table = _table(logged_in.get("/companies").text, "status")
    assert COMPOSED in table, "조합 문구가 IR 기업 현황에서 사라졌다"
    assert 'data-field="one_liner"' in table


# --- ③ 이름 ------------------------------------------------------------------

def _headers(html: str) -> list:
    head = html.split("</thead>", 1)[0]
    return [re.sub(r"<[^>]+>", "", cell).strip()
            for _attrs, cell in re.findall(r"<th\b([^>]*)>(.*?)</th>", head, re.S)]


def test_머리글은_탭마다_다른_이름이다(logged_in, composed):
    """같은 이름이면 어느 쪽이 조합 결과인지 화면에서 가를 수 없다."""
    status = _headers(logged_in.get("/companies").text)
    assert "딜 소개 문구 회사개요" in status, status
    assert "기업 한줄 소개" not in status, "IR 기업 현황에 옛 이름이 남아 있다"

    db_tab = _headers(logged_in.get("/companies?tab=db").text)
    assert "기업 한줄 소개" in db_tab, db_tab
    assert "딜 소개 문구 회사개요" not in db_tab, "재료 칸이 결과 이름을 쓰고 있다"


def test_수정_창도_같은_두_이름으로_부른다():
    """창이 다르게 부르면 같은 칸인지 알 수 없다(짝 대조는 test_ui_layout.py)."""
    text = TEMPLATE.read_text(encoding="utf-8")
    for field, label in (("one_liner", "딜 소개 문구 회사개요"),
                         ("business_desc", "기업 한줄 소개")):
        block = re.search(r"<span>([^<]*)</span>\s*\n?\s*<textarea id=\"f-%s\"" % field,
                          text)
        assert block, f"f-{field} 라벨을 못 찾았습니다"
        assert block.group(1).strip() == label, \
            f"f-{field}: 창이 '{block.group(1).strip()}' 이라 부릅니다 — '{label}' 이어야 합니다"


# --- ④ 아무 값도 안 지워진다 ---------------------------------------------------

def test_재료를_고쳐도_사람이_쓴_딜_소개_문구는_그대로다(logged_in, db):
    """제일 나쁜 고장이다 — 손으로 다듬어 둔 문구가 소리 없이 사라진다."""
    from app.models import IrCompany

    row = IrCompany(name="샘플다라소재", business_desc="소재 제조",
                    one_liner="사람이 다듬어 쓴 딜 소개 문구")
    db.add(row)
    db.commit()

    logged_in.patch(f"/api/companies/{row.id}",
                    json={"business_desc": "고급 소재 제조"})
    got = logged_in.get(f"/api/companies/{row.id}").json()
    assert got["one_liner"] == "사람이 다듬어 쓴 딜 소개 문구", got["one_liner"]
    assert got["business_desc"] == "고급 소재 제조"


def test_스타트업DB_에서_친_글자로_검색이_된다(logged_in, composed):
    """보이는 칸으로는 찾아져야 한다 — 검색은 탭을 가리지 않는다."""
    row = logged_in.get("/companies?tab=db").text
    line = row.split('data-search="', 1)[1].split('"', 1)[0]
    assert "비전ai 기반 미세먼지 측정 솔루션" in line, line


# --- ⑤ 이주 — 빈 칸만 채운다 ---------------------------------------------------

def _alembic(db: Path, *args: str) -> subprocess.CompletedProcess:
    """따로 뜬 프로세스로 `alembic` 을 돌린다(tests/test_migrations.py 와 같은 방식)."""
    env = {**os.environ,
           "DATABASE_URL": f"sqlite:///{db}",
           "DEALFLOW_DATA_DIR": str(db.parent)}
    return subprocess.run([sys.executable, "-m", "alembic", *args],
                          cwd=ROOT, env=env, capture_output=True, text=True)


# `(id, 한줄소개, 재료, 0051 백업)` — 이주가 갈라 봐야 하는 네 가지 줄.
SEED = [
    # 재료가 비었다 → 옮긴다. 그 글자는 0051 이후 사람이 그 탭에서 친 것이다.
    (1, "사람이 스타트업DB 탭에 친 소개", None,
     '{"one_liner": "사람이 스타트업DB 탭에 친 소개", "business_desc": null}'),
    # 재료가 이미 있다 → 손대지 않는다(덮어쓰면 그게 제일 나쁘다).
    (2, "비전AI 측정 엔진 | 매출 13억", "비전AI 측정 엔진",
     '{"one_liner": "비전AI 측정 엔진 | 매출 13억", "business_desc": "비전AI 측정 엔진"}'),
    # 재료 없이 조합된 줄 → 옮기면 매출이 '설명' 이 된다. 건너뛴다.
    (3, "매출 13억 | 누적투자금액 11억", "", '{"one_liner": null, "business_desc": null}'),
    # 둘 다 비었다 → 옮길 것이 없다.
    (4, None, None, None),
]


@pytest.fixture(scope="module")
def migrated(tmp_path_factory) -> dict:
    """0057 까지 올린 DB 에 위 네 줄을 심고 **올렸다 내렸다 다시 올려 본다.**

    한 번의 왕복을 여러 각도로 봐야 앞뒤가 맞는지 알 수 있다
    (tests/test_one_liner_single_source.py 의 `cycle` 과 같은 방식).
    """
    db = tmp_path_factory.mktemp("split") / "dealflow.db"
    up = _alembic(db, "upgrade", PREVIOUS)
    assert up.returncode == 0, up.stdout + up.stderr

    con = sqlite3.connect(db)
    con.execute("DELETE FROM ir_companies")
    for cid, one_liner, desc, backup in SEED:
        con.execute(
            "INSERT INTO ir_companies (id, name, one_liner, business_desc,"
            " desc_backup, contract_status, summary_status, is_top_deal,"
            " created_at, updated_at) VALUES (?, ?, ?, ?, ?, 'none', 'draft', 0, ?, ?)",
            (cid, f"샘플{cid:03d}가나헬스", one_liner, desc, backup, STAMP, STAMP))
    con.commit()
    con.close()

    def read():
        con = sqlite3.connect(db)
        try:
            return {r[0]: (r[1], r[2]) for r in con.execute(
                "SELECT id, business_desc, one_liner FROM ir_companies").fetchall()}
        finally:
            con.close()

    before = read()
    up = _alembic(db, "upgrade", "head")
    assert up.returncode == 0, up.stdout + up.stderr
    after = read()

    down = _alembic(db, "downgrade", PREVIOUS)
    assert down.returncode == 0, down.stdout + down.stderr
    restored = read()

    # 끊겼다 다시 도는 길 — 같은 자리로 돌아와야 한다.
    again = _alembic(db, "upgrade", "head")
    assert again.returncode == 0, again.stdout + again.stderr

    return {"before": before, "after": after, "restored": restored,
            "twice": read(), "log": up.stdout, "down_log": down.stdout}


def _desc(state: dict) -> dict:
    return {cid: value[0] for cid, value in state.items()}


def test_재료가_빈_줄만_채운다(migrated):
    """옮기는 것은 한 줄뿐 — 나머지 셋은 이유가 저마다 다르다."""
    after = _desc(migrated["after"])
    assert after[1] == "사람이 스타트업DB 탭에 친 소개", "빈 재료 칸을 안 채웠다"
    assert after[2] == "비전AI 측정 엔진", "이미 있던 재료를 덮었다"
    assert not (after[3] or "").strip(), "재료 없이 조합된 줄을 옮겼다"
    assert after[4] is None
    assert "1곳을 옮겼습니다" in migrated["log"], migrated["log"]
    assert "건너뜁니다" in migrated["log"], migrated["log"]


def test_딜_소개_문구는_한_글자도_안_바뀐다(migrated):
    """이 판은 `one_liner` 을 읽기만 한다 — 옮기는 것이 아니라 **베끼는** 것이다."""
    was = {cid: value[1] for cid, value in migrated["before"].items()}
    for state in ("after", "restored", "twice"):
        now = {cid: value[1] for cid, value in migrated[state].items()}
        assert now == was, f"{state}: 딜 소개 문구가 바뀌었다"


def test_되돌렸다_다시_올려도_같은_자리다(migrated):
    """중간에 끊겼다 다시 도는 길에서도 같은 결과여야 한다."""
    assert _desc(migrated["twice"]) == _desc(migrated["after"])


def test_되돌리면_채운_줄만_다시_빈다(migrated):
    """이미 차 있던 재료까지 비우면 그게 제일 나쁘다."""
    down = _desc(migrated["restored"])
    assert down[1] is None, "이 판이 채운 줄이 안 비워졌다"
    assert down[2] == "비전AI 측정 엔진", "원래 있던 재료가 지워졌다"
    assert "1곳을 되돌렸습니다" in migrated["down_log"], migrated["down_log"]


def test_되돌린_뒤에_사람이_고쳐_쓴_줄은_안_건드린다(tmp_path):
    """되돌리기가 손글씨를 지우면 안 된다 — 0051 의 downgrade 와 같은 규칙이다."""
    db = tmp_path / "edited.db"
    assert _alembic(db, "upgrade", PREVIOUS).returncode == 0

    con = sqlite3.connect(db)
    con.execute("DELETE FROM ir_companies")
    con.execute(
        "INSERT INTO ir_companies (id, name, one_liner, business_desc,"
        " desc_backup, contract_status, summary_status, is_top_deal,"
        " created_at, updated_at) VALUES (1, '샘플가나헬스', ?, NULL, ?,"
        " 'none', 'draft', 0, ?, ?)",
        ("사람이 스타트업DB 탭에 친 소개",
         '{"one_liner": "사람이 스타트업DB 탭에 친 소개", "business_desc": null}',
         STAMP, STAMP))
    con.commit()
    con.close()

    assert _alembic(db, "upgrade", "head").returncode == 0

    con = sqlite3.connect(db)
    con.execute("UPDATE ir_companies SET business_desc = '사람이 다시 쓴 재료' WHERE id = 1")
    con.commit()
    con.close()

    down = _alembic(db, "downgrade", PREVIOUS)
    assert down.returncode == 0, down.stdout + down.stderr
    con = sqlite3.connect(db)
    try:
        got = con.execute("SELECT business_desc FROM ir_companies").fetchone()[0]
    finally:
        con.close()
    assert got == "사람이 다시 쓴 재료", "되돌리기가 그 뒤에 쓴 손글씨를 지웠다"
    assert "그대로 둡니다" in down.stdout, down.stdout
