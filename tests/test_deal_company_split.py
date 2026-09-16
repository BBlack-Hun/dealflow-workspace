"""딜 소개 칸의 **기업 이름 쪼개기** — 규칙 하나 · 두 자리가 함께 쓴다.

시트를 읽어 넣는 쪽(`services/sheet_import`)과 이미 들어와 있는 줄을 다시
쪼개는 쪽(`scripts/resplit_deal_companies.py`)이 **같은 함수**
(`services/company_names.split`)를 부른다. 규칙이 두 벌이면 앞으로 들어오는
것과 이미 있는 것이 다르게 쪼개지므로, 아래 검사는 판정만 보지 않고 **두 자리가
그 판정을 실제로 지나는지**까지 본다.

값은 운영에서 센 **네 꼴**로 짠다(실제 칸 값 1,988줄 기준).

    `9/2 샘플가, 샘플나`            날짜가 맨 앞 (1,365줄)
    `[8/5] [핵심 딜 공유]`          **대괄호 씌운 날짜** (453줄) — 옛 규칙이 못 읽었다
    `샘플가, 샘플나`                 날짜 없는 줄 (165줄) — 앞 회차에서 이어진다
    `핵심 딜 8개사`                  개수만 적힌 회차

**가장 조심하는 것은 헛맞음이다.** 두 글자 이름은 긴 이름 한가운데에 우연히
박힌다. 그래서 이름을 찾는 길은 **구분자로 쪼갠 뒤 글자 그대로 맞추는 것**
하나뿐이고, 부분일치는 쓰지 않는다 — 아래 `헛맞음` 검사가 그것을 못 박는다.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

from app.services import company_names as cn

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "resplit_deal_companies.py"


# ── ① 회차 가르기 ───────────────────────────────────────────────────────────

def test_대괄호_씌운_날짜도_회차의_시작이다():
    """실제 칸 값 1,988줄 중 453줄이 이 꼴이다. 못 읽으면 앞 회차에 들러붙는다."""
    rounds = cn.rounds("7/29 샘플가, 샘플나\n[8/12] 샘플다, 샘플라")

    assert [(r.month, r.day) for r in rounds] == [(7, 29), (8, 12)]
    assert [cn.split(r.content).names for r in rounds] == [
        ["샘플가", "샘플나"], ["샘플다", "샘플라"]]


def test_날짜로_시작하지_않는_줄은_앞_회차에_이어_붙는다():
    """기업 목록이 다음 줄로 넘어가는 일이 잦다 — 그것은 새 회차가 아니다."""
    rounds = cn.rounds("[8/5] [핵심 딜 공유]\n샘플가, 샘플나, 샘플다")

    assert len(rounds) == 1
    assert cn.split(rounds[0].content).names == ["샘플가", "샘플나", "샘플다"]


def test_없는_날짜는_지어내지_않는다():
    assert cn.round_prefix("13/40 뭔가") is None


# ── ② 이름 쪼개기 ───────────────────────────────────────────────────────────

def test_한_덩어리로_뭉친_이름을_날짜에서_가른다():
    """이미 들어와 있는 줄의 모양이다 — 옛 규칙이 회차를 못 갈라 붙여 놓았다."""
    parsed = cn.split("샘플가 [8/12] 샘플나")

    assert parsed.names == ["샘플가", "샘플나"]
    assert parsed.dates == [(8, 12)]          # 날짜는 떼되 **버리지 않는다**


def test_꼬리말은_떼고_이름만_남긴다():
    assert cn.split("샘플가 전달").names == ["샘플가"]
    assert cn.split("카톡딜 공유/샘플가, 샘플나").names == ["샘플가", "샘플나"]
    assert cn.split("[핵심 딜 공유]").names == []
    assert cn.split("소개기업 없음").names == []


def test_이름_안의_띄어쓰기로는_쪼개지_않는다():
    """이름에 공백이 든 기업이 실목록 344곳 중 81곳이다. 거기서 자르면 안 된다."""
    assert cn.split("샘플 모빌리티, 샘플가").names == ["샘플 모빌리티", "샘플가"]


def test_법인_표기는_붙어_있는_그대로_남는다():
    """`(주)` 의 괄호는 구분자가 아니다. 저장은 원문 그대로 한다."""
    assert cn.split("1.(주)샘플가  2.샘플나").names == ["(주)샘플가", "샘플나"]
    assert cn.split("주식회사 샘플가, 샘플나").names == ["주식회사 샘플가", "샘플나"]


def test_개수만_적힌_회차는_개수를_남기고_이름을_지어내지_않는다():
    parsed = cn.split("핵심 딜 8개사")
    assert parsed.names == [] and parsed.count == 8


def test_개수_말에_붙어_버린_기업_이름을_살린다():
    """`핵심 딜 8개사 샘플가` — 옛 규칙은 이 조각을 통째로 버렸다."""
    assert cn.split("핵심 딜 8개사 샘플가, 샘플나").names == ["샘플가", "샘플나"]


def test_같은_이름이_두_번_적혀도_한_번만_센다():
    assert cn.split("샘플가, 샘플가, 샘플나").names == ["샘플가", "샘플나"]


def test_꼬리말_낱말이_기업_이름을_삼키지_않는다():
    """꼬리말은 **실제 기업 목록과 대조해서** 골랐다. 이름을 통째로 먹으면 안 된다."""
    for name in ("공유누리", "소개팅랩스", "딜라이트", "샘플기업", "전달체계",
                 "미팅박스", "카톡가나"):
        assert cn.split(name).names == [name], name


# ── ③ 헛맞음 ────────────────────────────────────────────────────────────────

def _key(name):
    from app.services.deal_history import _key as key

    return key(name)


def test_짧은_이름이_긴_이름_안에_박혀도_소개했다고_안_센다():
    """**이 저장소가 가장 조심하는 자리다.**

    두 글자 이름은 긴 이름 한가운데에 우연히 박힌다(`가나` ⊂ `가나다라전자`).
    부분일치로 찾으면 소개한 적 없는 기업이 소개한 것으로 잡힌다. 쪼갠 조각을
    **글자 그대로** 맞추므로 그런 일이 없어야 한다.
    """
    목록 = {_key(n) for n in ("가나", "다라", "가나다라전자")}

    쪼갠_것 = {_key(n) for n in cn.split("9/2 가나다라전자").names}

    assert 쪼갠_것 == {_key("가나다라전자")}
    assert _key("가나") not in 쪼갠_것      # 헛맞음 없음
    assert _key("다라") not in 쪼갠_것
    assert 쪼갠_것 <= 목록


def test_정말_적힌_짧은_이름은_잡는다():
    """헛맞음을 막느라 진짜 두 글자 이름까지 놓치면 안 된다."""
    names = {_key(n) for n in cn.split("9/2 가나, 가나다라전자").names}
    assert names == {_key("가나"), _key("가나다라전자")}


# ── ④ 시트를 읽어 넣는 쪽도 같은 규칙을 지난다 ──────────────────────────────

def test_임포트_파서가_같은_규칙으로_회차와_이름을_가른다():
    from app.services import sheet_import as si

    acts = si.parse_activity_cell("7/29(수) 샘플가, 샘플나\n[8/12] 샘플다",
                                  "2026-07", si.KIND_DEAL_INTRO, 2026)

    assert [(a.happened_at, a.companies) for a in acts] == [
        ("2026-07-29", ["샘플가", "샘플나"]),
        ("2026-08-12", ["샘플다"]),
    ]


# ── ⑤ 이미 들어와 있는 줄을 다시 쪼개는 스크립트 ────────────────────────────

GLUED = "7/29 샘플가, 샘플나\n[8/12] 샘플다, 샘플라"
TAIL = "8/19 샘플마 전달"


def _seed(db):
    """뭉친 줄 둘 + 이미 멀쩡한 줄 하나. 스크립트가 각각을 어떻게 가르는지 본다."""
    from app.models import ContactActivity, IrCompany, VcContact

    contact = VcContact(user_id=1, name="가", firm="가벤처스")
    db.add(contact)
    db.add_all([IrCompany(name=n) for n in
                ("샘플가", "샘플나", "샘플다", "샘플라", "샘플마", "가나")])
    db.flush()

    rows = [
        # ① 회차 둘이 한 줄에 뭉쳤다 — 옛 규칙이 `[8/12]` 를 날짜로 못 읽었다.
        ContactActivity(
            contact_id=contact.id, month="2026-07", kind="deal_intro",
            content="샘플가, 샘플나 [8/12] 샘플다, 샘플라",
            happened_at="2026-07-29", weekday="수", source="import",
            company_names=json.dumps(["샘플가", "샘플나 [8/12] 샘플다", "샘플라"],
                                     ensure_ascii=False),
            company_count=3, raw_text=GLUED),
        # ② 꼬리말이 붙어 이름이 안 맞던 줄. 날짜 칸도 비어 있다.
        ContactActivity(
            contact_id=contact.id, month="2026-08", kind="deal_intro",
            content="샘플마 전달", source="import",
            company_names=json.dumps(["샘플마 전달"], ensure_ascii=False),
            company_count=1, raw_text=TAIL),
        # ③ 이미 멀쩡한 줄 — 손대면 안 된다.
        ContactActivity(
            contact_id=contact.id, month="2026-08", kind="deal_intro",
            content="샘플가, 샘플나", happened_at="2026-08-26", weekday="수",
            source="import",
            company_names=json.dumps(["샘플가", "샘플나"], ensure_ascii=False),
            company_count=2, raw_text="8/26 샘플가, 샘플나"),
    ]
    db.add_all(rows)
    db.commit()
    return contact.id, [r.id for r in rows]


def _db_path() -> Path:
    import os

    return Path(os.environ["DATABASE_URL"][len("sqlite:///"):])


def _run(db_path: Path, *args) -> str:
    out = subprocess.run(
        [sys.executable, str(SCRIPT), "--db", str(db_path), *args],
        capture_output=True, text=True, cwd=str(ROOT), check=False)
    assert out.returncode == 0, out.stdout + out.stderr
    return out.stdout


def _dump(path: Path) -> list:
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        return con.execute(
            "SELECT * FROM contact_activities ORDER BY id").fetchall()
    finally:
        con.close()


def _sha(path: Path) -> str:
    """표 전체의 지문. **한 글자라도 달라지면 값이 달라진다.**"""
    return hashlib.sha256(
        json.dumps(_dump(path), ensure_ascii=False, default=str)
        .encode("utf-8")).hexdigest()


def _names(path: Path, row_id: int) -> list:
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        raw = con.execute("SELECT company_names FROM contact_activities "
                          "WHERE id = ?", (row_id,)).fetchone()
    finally:
        con.close()
    return json.loads(raw[0] or "[]") if raw else []


def test_미리보기가_기본이고_DB_에_한_글자도_안_쓴다(db, users):
    """`--apply` 를 안 주면 읽기 전용(`mode=ro`)으로 연다 — 쓸 길 자체가 없다."""
    _seed(db)
    path = _db_path()
    before = _sha(path)

    text = _run(path, "--dry-run")

    assert "미리보기" in text
    assert _sha(path) == before


def test_되돌릴_파일_없이는_바꾸지_않는다(db, users):
    _seed(db)
    out = subprocess.run(
        [sys.executable, str(SCRIPT), "--db", str(_db_path()), "--apply"],
        capture_output=True, text=True, cwd=str(ROOT), check=False)
    assert out.returncode == 2
    assert "--save-baseline" in out.stderr


def test_미리보기는_이름을_안_찍는다(db, users):
    """기업 이름은 실명이다. 기본은 **모양(개수·길이)**뿐이다."""
    _seed(db)
    quiet = _run(_db_path(), "--dry-run", "--limit", "0")
    assert "샘플다" not in quiet

    loud = _run(_db_path(), "--dry-run", "--limit", "0", "--show-values")
    assert "샘플다" in loud


def test_뭉친_이름을_쪼개고_회차가_둘이면_줄을_나눈다(db, users, tmp_path):
    contact_id, ids = _seed(db)
    path = _db_path()

    _run(path, "--apply", "--save-baseline", str(tmp_path / "deal.json"))

    # ① 앞 회차만 남고, 뒤 회차는 제 날짜를 단 **새 줄**로 옮겨 갔다.
    assert _names(path, ids[0]) == ["샘플가", "샘플나"]
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        fresh = con.execute(
            "SELECT happened_at, company_names FROM contact_activities "
            "WHERE id > ? ORDER BY id", (max(ids),)).fetchall()
    finally:
        con.close()
    assert [f[0] for f in fresh] == ["2026-08-12"]
    assert json.loads(fresh[0][1]) == ["샘플다", "샘플라"]

    # ② 꼬리말은 떨어지고, 비어 있던 날짜는 글에 남아 있던 조각으로 채워진다.
    assert _names(path, ids[1]) == ["샘플마"]
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        when = con.execute("SELECT happened_at, weekday FROM contact_activities"
                           " WHERE id = ?", (ids[1],)).fetchone()
    finally:
        con.close()
    assert when == ("2026-08-19", "수")

    # ③ 이미 멀쩡한 줄은 그대로다.
    assert _names(path, ids[2]) == ["샘플가", "샘플나"]


def test_되돌리면_한_글자도_안_달라진다(db, users, tmp_path):
    """`--restore` 는 고친 줄을 되살리고 **새로 만든 줄을 지운다.**"""
    _seed(db)
    path = _db_path()
    keep = tmp_path / "deal.json"
    before = _sha(path)

    _run(path, "--apply", "--save-baseline", str(keep))
    assert _sha(path) != before                      # 정말 바뀌었다

    _run(path, "--restore", str(keep), "--apply")
    assert _sha(path) == before                      # 지문까지 그대로


def test_두_번_돌려도_줄이_안_늘어난다(db, users, tmp_path):
    """임포트가 중복을 가리는 그 열쇠로 살펴본다 — 다시 돌려도 안전해야 한다."""
    _seed(db)
    path = _db_path()

    _run(path, "--apply", "--save-baseline", str(tmp_path / "1.json"))
    once = _sha(path)
    _run(path, "--apply", "--save-baseline", str(tmp_path / "2.json"))

    assert _sha(path) == once


def test_고친_뒤에는_소개_이력이_그_기업들을_찾아낸다(db, users, tmp_path):
    """이 작업의 성적표 — **못 맞춘 이름 수가 줄어야 한다.**

    `deal_history.scan()` 의 이력 표도, `llm_brief.sent_before` 도 같은
    `_key` 로 맞춘다. 그래서 한 곳만 봐도 둘이 함께 움직인다.
    """
    from app.services import deal_history

    contact_id, _ids = _seed(db)
    before = deal_history.scan(db)
    assert before.unmatched == 2          # `샘플나 [8/12] 샘플다` · `샘플마 전달`
    assert before.of("샘플다").days == 0   # 소개했는데 "소개한 적 없음" 이다
    db.rollback()                         # 읽던 자리를 놓는다(스크립트가 쓴다)

    _run(_db_path(), "--apply", "--save-baseline", str(tmp_path / "deal.json"))
    db.rollback()
    after = deal_history.scan(db)

    assert after.unmatched == 0
    assert after.of("샘플다").last_sent == "2026-08-12"
    assert after.of("샘플마").last_sent == "2026-08-19"

    # 딜 고르기가 보는 `이미 보낸 기업` 도 같은 값으로 늘어난다.
    from app.services import llm_brief

    _refs, _more, unmatched = llm_brief.sent_history(db, [contact_id])[contact_id]
    assert unmatched == 0
