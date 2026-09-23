"""이미 들어온 미팅 이력을 다시 가르는 스크립트.

못 박는 것이 넷이다.

    ① **기본이 미리보기**다 — DB 를 읽기 전용으로 열고 한 줄도 안 바꾼다
    ② 갈래별로 **몇 줄이 어디로 가는지** 숫자가 나온다
    ③ **애매한 줄은 안 옮긴다** — 세어서 보여 주기만 한다
    ④ 되돌리면 값이 한 글자도 안 달라진다

내용은 **전부 지어낸 값**이다(공개 저장소).
"""
from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
from pathlib import Path

import pytest

from app.services import meeting_kind as mk

ROOT = Path(__file__).resolve().parent.parent


def _script():
    """`scripts/` 는 꾸러미가 아니라 파일로 읽는다(다른 스크립트 검사와 같다)."""
    path = ROOT / "scripts" / "resplit_meeting_kind.py"
    spec = importlib.util.spec_from_file_location("resplit_meeting_kind", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


#: 운영에서 본 모양 그대로의 **가짜** 줄들. (갈래, 내용) — 이름은 안 쓴다.
ROWS = [
    (mk.REQUEST, "8/5 미팅 요청"),
    (mk.REQUEST, "미팅 요청 드림"),
    (mk.REQUEST, "IR 요청기업 미팅 안내전화"),
    (mk.SET, "9/3 미팅확정"),
    (mk.DONE, "8/20 미팅완료"),
    (mk.DONE, "미팅 진행"),
    # 미팅 말이 아예 없다 — 옮기지 않는다.
    (None, "검토 중"),
    (None, "O"),
    # 미팅 말은 있는데 못 가른다 — 옮기지 않는다.
    (None, "미팅 취소"),
    (None, "미팅 미진행"),
]


@pytest.fixture()
def sample(tmp_path):
    """`contact_activities` 만 있는 작은 자료. 스크립트는 sqlite3 로 직접 연다."""
    path = tmp_path / "sample.db"
    con = sqlite3.connect(path)
    con.execute("""
        CREATE TABLE contact_activities (
            id INTEGER PRIMARY KEY, contact_id INTEGER, month TEXT, kind TEXT,
            content TEXT, happened_at TEXT, source TEXT, created_at TEXT,
            updated_at TEXT, weekday TEXT, company_names TEXT,
            company_count INTEGER, raw_text TEXT, batch_key TEXT,
            undone_at TEXT)
    """)
    for idx, (_want, content) in enumerate(ROWS, start=1):
        con.execute(
            "INSERT INTO contact_activities (id, contact_id, month, kind, "
            "content, source) VALUES (?, ?, ?, 'meeting', ?, 'import')",
            (idx, idx, "2026-08", content))
    # 이미 가른 줄과 되돌린 줄은 **후보가 아니다.**
    con.execute("INSERT INTO contact_activities (id, contact_id, kind, content,"
                " source) VALUES (99, 99, ?, '8/20 미팅완료', 'import')",
                (mk.DONE,))
    con.execute("INSERT INTO contact_activities (id, contact_id, kind, content,"
                " source, undone_at) VALUES (98, 98, 'meeting', "
                "'8/20 미팅완료', 'import', '2026-09-01')")
    con.commit()
    con.close()
    return path


def test_the_plan_sorts_every_row(sample):
    mod = _script()
    con = mod.open_db(sample, write=False)
    try:
        rows = mod.plan(con)
    finally:
        con.close()

    got = {item["id"]: item["kind"] for item in rows}
    assert got == {idx: want for idx, (want, _c) in enumerate(ROWS, start=1)}
    # 이미 가른 줄·되돌린 줄은 계획에 없다.
    assert 99 not in got and 98 not in got


def test_the_counts_say_where_each_group_goes(sample):
    mod = _script()
    con = mod.open_db(sample, write=False)
    try:
        counts = mod.summarize(mod.plan(con))
    finally:
        con.close()

    assert counts[mk.REQUEST] == 3
    assert counts[mk.SET] == 1
    assert counts[mk.DONE] == 2
    assert counts[mod.NO_WORD] == 2, "미팅 말이 없는 줄은 따로 센다"
    assert counts[mod.UNSURE] == 2, "못 가른 줄도 따로 센다"


def test_people_counts_keep_the_ones_who_really_met(sample):
    """**진짜로 미팅한 사람이 빠지면 더 나쁘다** — 스크립트가 그 수를 먼저 찍는다."""
    mod = _script()
    con = mod.open_db(sample, write=False)
    try:
        people = mod.people_counts(con, mod.plan(con))
    finally:
        con.close()

    # 전: `meeting` 10명 + 이미 가른 완료 1명 = 11명이 미팅으로 서 있었다.
    assert people["before"] == 11
    # 후: 완료 2 + 이미 가른 완료 1 + 안 옮긴 4 = 7명.
    assert people["after"] == 7
    assert people["kept"] == 7 and people["dropped"] == 4
    assert people["done"] == 3, "만난 사람은 한 명도 안 빠진다"
    assert people["asked"] == 3


def test_preview_writes_nothing(sample):
    """**기본이 미리보기다.** 읽기 전용으로 열어 쓸 길 자체를 막는다."""
    mod = _script()
    before = _kinds(sample)

    assert mod.main.__module__  # 스크립트가 import 만으로 아무 일도 안 한다
    sys.argv = ["resplit_meeting_kind.py", "--db", str(sample)]
    assert mod.main() == 0
    assert _kinds(sample) == before

    con = mod.open_db(sample, write=False)
    try:
        with pytest.raises(sqlite3.OperationalError):
            con.execute("UPDATE contact_activities SET kind = 'x'")
    finally:
        con.close()


def test_apply_needs_a_way_back(sample, tmp_path, capsys):
    """되돌릴 파일 없이 바꾸지 않는다."""
    mod = _script()
    sys.argv = ["resplit_meeting_kind.py", "--db", str(sample), "--apply"]
    assert mod.main() == 2
    assert _kinds(sample)[1] == "meeting"


def test_apply_then_restore_changes_nothing(sample, tmp_path):
    mod = _script()
    baseline = tmp_path / "meet.json"
    before = _kinds(sample)

    sys.argv = ["resplit_meeting_kind.py", "--db", str(sample), "--apply",
                "--save-baseline", str(baseline)]
    assert mod.main() == 0

    after = _kinds(sample)
    assert after[1] == mk.REQUEST and after[4] == mk.SET and after[5] == mk.DONE
    # 안 옮기는 줄은 그대로다 — 손대면 추측이 된다.
    assert after[7] == "meeting" and after[9] == "meeting"

    # 계획대로 바뀌었는지 스스로 맞춰 본다.
    sys.argv = ["resplit_meeting_kind.py", "--db", str(sample),
                "--baseline", str(baseline)]
    assert mod.main() == 0

    # 두 번 돌려도 더 움직이지 않는다.
    sys.argv = ["resplit_meeting_kind.py", "--db", str(sample), "--apply",
                "--save-baseline", str(tmp_path / "again.json")]
    assert mod.main() == 0
    assert _kinds(sample) == after

    sys.argv = ["resplit_meeting_kind.py", "--db", str(sample), "--apply",
                "--restore", str(baseline)]
    assert mod.main() == 0
    assert _kinds(sample) == before, "되돌리면 한 글자도 안 달라진다"


def test_the_baseline_carries_both_sides(sample, tmp_path):
    mod = _script()
    baseline = tmp_path / "meet.json"
    sys.argv = ["resplit_meeting_kind.py", "--db", str(sample), "--apply",
                "--save-baseline", str(baseline)]
    mod.main()
    data = json.loads(baseline.read_text(encoding="utf-8"))
    assert len(data) == 6, "옮기는 줄만 떠 둔다"
    assert all(d["before"]["kind"] == "meeting" for d in data)
    assert {d["after"]["kind"] for d in data} == {mk.REQUEST, mk.SET, mk.DONE}


def test_values_are_hidden_unless_asked(sample, capsys):
    """미리보기는 **모양(길이)** 만 찍는다 — 내용에 실명이 섞여 있다."""
    mod = _script()
    sys.argv = ["resplit_meeting_kind.py", "--db", str(sample)]
    mod.main()
    out = capsys.readouterr().out
    assert "8/20 미팅완료" not in out and "자" in out

    sys.argv = ["resplit_meeting_kind.py", "--db", str(sample), "--show-values"]
    mod.main()
    assert "8/20 미팅완료" in capsys.readouterr().out


def _kinds(path: Path) -> dict:
    con = sqlite3.connect(path)
    try:
        return dict(con.execute("SELECT id, kind FROM contact_activities"))
    finally:
        con.close()
