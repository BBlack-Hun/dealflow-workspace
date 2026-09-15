"""칸 이름에만 있던 **달·종류**를 값으로 올리는가 — 그리고 **값을 안 건드리는가**.

0075 가 하는 일이다. 달마다 칸이 느는 두 표(`contact_columns` ·
`consulting_columns`)에서 어느 달·무슨 종류인지가 지금까지 **이름 안에만**
있었다(`9월 리마인드 문자`). 이름에는 해가 없어서, 12월 칸과 1월 칸이 나란히
서면 어느 해 것인지 이름으로는 가릴 수가 없다.

여기서 막는 것이 넷이다.

  1. 달을 읽는 **세 단계**가 그대로 도는가 — 세운 기록 → 만든 날에서 거꾸로
     세기 → 못 읽으면 비워 두기. 순서가 뒤집히면 짐작이 기록을 덮는다.
  2. 달을 못 읽는 칸을 **손대지 않는가.** `카톡방 연결여부` 처럼 애초에 월별
     칸이 아닌 것들이다 — 지어내면 없던 달이 생긴다.
  3. `notes` 가 **한 글자도 안 바뀌는가.** 0075 는 값을 옮기지 않는 설계라
     `UPDATE` 만 한다. 열쇠를 다시 적는 이전은 한 줄만 어긋나도 그 줄의 기록이
     화면에서 통째로 사라진다(0039·0067 이 그 유형이다).
  4. **되돌렸다 올리면 같은 자료인가.** 값을 안 옮겼으니 같아야 한다.

이름에서 뒷말을 읽는 규칙은 새로 만들지 않는다 — 앱이 **새 달 칸 이름을 지을
때 남겨 두는 그 부분**이다(`services/monthly_columns.relabel`). 그래서 안쪽
공백도 줄지 않는다(`마지막주 리마인드 카톡  or  TEL` 은 시트에 그대로 있는 글자).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest

from app.services.monthly_columns import kind_of, month_key_of, months_back

ROOT = Path(__file__).resolve().parent.parent
PREV = "0074_company_amounts_as_text"      # 0075 의 부모
NOW = "2026-09-08T10:13:11+09:00"


# ── ① 달 읽기 — 세 단계 ─────────────────────────────────────────────────────

def test_세운_기록이_있으면_그_달로_확정한다():
    """1단계. 앱이 칸을 세우며 적어 둔 줄이라 짐작이 아니다.

    **이름의 달보다 이 기록이 앞선다** — 해를 아는 것은 이쪽뿐이다.
    """
    assert month_key_of("9월 리마인드 문자", date(2026, 9, 8),
                        {"9월 리마인드 문자": ["2026-09"]}) == "2026-09"


def test_기록이_없으면_만든_날에서_거꾸로_센다():
    """2단계. 시트에서 실려 온 옛 칸에는 세운 기록이 없다.

    8월 28일에 선 `7월` 칸은 한 달 전이므로 그해 7월이다.
    """
    assert month_key_of("7월 리마인드 문자 (7/28)", date(2026, 8, 28)) == "2026-07"
    assert month_key_of("8월 마지막주 리마인드 톡 or TEL",
                        date(2026, 8, 26)) == "2026-08"


def test_해가_바뀌는_자리에서는_지난해로_물린다():
    """거꾸로 세기라 12월 다음이 1월인 것을 그대로 안다.

    1월에 서 있는 `12월` 칸은 한 달 전 — **지난해** 12월이다. `max(달)` 로
    골랐으면 여기서 올해 12월이 되어, 아직 오지 않은 달이 칸에 적힌다.
    """
    assert month_key_of("12월 리마인드", date(2026, 1, 3)) == "2025-12"
    assert month_key_of("11월 리마인드", date(2026, 2, 20)) == "2025-11"
    assert months_back(1, 12) == 1
    assert months_back(9, 9) == 0


def test_달을_못_읽으면_비워_둔다():
    """3단계. 애초에 월별 칸이 아닌 것들 — 지어내지 않는다.

    `리마인드 카톡(월1회-수or목or금)` 은 `월` 앞에 숫자가 없어 달이 아니다.
    """
    assert month_key_of("카톡방 연결여부", date(2026, 9, 1)) is None
    assert month_key_of("리마인드 카톡(월1회-수or목or금)", date(2026, 9, 1)) is None
    assert month_key_of("13월 리마인드", date(2026, 9, 1)) is None


def test_같은_이름이_두_달로_적혀_있으면_기록을_안_믿는다():
    """해가 바뀌어 `9월` 이 두 번 선 표. 기록만으로는 어느 쪽인지 못 고른다.

    그럴 때는 1단계를 건너뛰고 **만든 날**로 간다 — 고르는 근거가 없는데
    아무거나 집으면 절반이 틀린 해가 된다.
    """
    runs = {"9월 리마인드 문자": ["2025-09", "2026-09"]}
    assert month_key_of("9월 리마인드 문자", date(2026, 9, 8), runs) == "2026-09"


def test_기록에_없는_이름은_만든_날로_넘어간다():
    """같은 표의 기록이 있어도 **그 이름**이 없으면 1단계는 답하지 않는다."""
    runs = {"9월 리마인드 문자": ["2026-09"]}
    assert month_key_of("7월 리마인드 TEL", date(2026, 8, 28), runs) == "2026-07"


# ── ② 종류(뒷말) 읽기 ───────────────────────────────────────────────────────

@pytest.mark.parametrize("label,want", [
    ("7월 리마인드 문자 (7/28)", "리마인드 문자"),
    ("8월 딜소개 8/5 8/12 8/19", "딜소개"),
    ("6월 마지막주 리마인드 카톡  or  TEL", "마지막주 리마인드 카톡  or  TEL"),
    ("9월 카톡 연결", "카톡 연결"),
])
def test_이름에서_달과_보낸날을_떼면_종류다(label, want):
    assert kind_of(label) == want


def test_안쪽_공백을_줄이지_않는다():
    """시트에 두 칸짜리 공백이 그대로 들어 있는 칸이 있다.

    고르면 시트와 글자가 달라져 나란히 놓고 대조할 수가 없다 — 앱이 새 달 칸
    이름을 지을 때도 그대로 두는 그것이다(`relabel`).
    """
    kind = kind_of("6월 마지막주 리마인드 카톡  or  TEL")
    assert "카톡  or  TEL" in kind
    assert "  " in kind


def test_달과_숫자가_다른_토막은_날짜가_아니다():
    """`8월 성공보수 1/2 조건` 의 `1/2` 는 날짜가 아니라 조건이다.

    아무 `M/D` 나 떼면 시트에 있던 글자를 지운다 — `relabel` 이 달이 맞을 때만
    떼는 이유이고, 뒷말을 읽을 때도 같은 손질을 쓴다.
    """
    assert kind_of("8월 성공보수 1/2 조건") == "성공보수 1/2 조건"


# ── ③ 이주 — 값을 안 건드리는가 ─────────────────────────────────────────────

def _alembic(db: Path, *args: str) -> subprocess.CompletedProcess:
    """`tests/test_migrations.py` 와 같은 방식 — 따로 뜬 프로세스로 돌린다.

    `alembic/env.py` 는 import 시점에 굳은 `app.config.DATABASE_URL` 을 읽는데,
    검사 프로세스에서는 그것이 이미 conftest 의 검사 DB 다.
    """
    env = {**os.environ,
           "DATABASE_URL": f"sqlite:///{db}",
           "DEALFLOW_DATA_DIR": str(db.parent)}
    return subprocess.run([sys.executable, "-m", "alembic", *args],
                          cwd=ROOT, env=env, capture_output=True, text=True)


# 운영에서 실측한 모양을 본뜬 가상 자료.
#
#   · 세운 기록이 있는 칸(9월 셋)          → 1단계
#   · 기록이 없는 옛 칸(7월 셋 · 6~8월)    → 2단계
#   · 달이 없는 칸 둘                      → 3단계(그대로 둔다)
CONTACT_SHEET = "샘플 스타트업(9)"
OLD_SHEET = "샘플 명단"
CONSULT_SHEET = "샘플 탭"

CONTACT_COLUMNS = [
    # (id, 명단, 이름, 만든 날)
    (1, OLD_SHEET, "7월 리마인드 문자 (7/28)", "2026-08-28T13:48:06+09:00"),
    (2, OLD_SHEET, "7월 리마인드 TEL", "2026-08-28T13:48:06+09:00"),
    (3, OLD_SHEET, "카톡방 연결여부", "2026-09-01T11:11:41+09:00"),
    (4, OLD_SHEET, "리마인드 카톡(월1회-수or목or금)", "2026-09-01T11:11:41+09:00"),
    (5, CONTACT_SHEET, "9월 리마인드 문자", "2026-09-01T12:37:08+09:00"),
    (6, CONTACT_SHEET, "9월 카톡 연결", "2026-09-01T12:37:08+09:00"),
]
CONSULTING_COLUMNS = [
    (1, CONSULT_SHEET, "6월 마지막주 리마인드 카톡  or  TEL",
     "2026-08-26T12:21:40+09:00"),
    (2, CONSULT_SHEET, "9월 마지막주 리마인드 카톡  or  TEL",
     "2026-09-01T17:34:06+09:00"),
]
RUNS = [
    ("contact", CONTACT_SHEET, "2026-09",
     ["9월 리마인드 문자", "9월 카톡 연결"]),
    ("consulting", CONSULT_SHEET, "2026-09",
     ["9월 마지막주 리마인드 카톡  or  TEL"]),
]

WANT_CONTACT = {
    1: ("2026-07", "리마인드 문자"),      # 2단계 — 만든 날에서 한 달 물림
    2: ("2026-07", "리마인드 TEL"),
    3: (None, None),                      # 3단계 — 달 칸이 아니다
    4: (None, None),
    5: ("2026-09", "리마인드 문자"),      # 1단계 — 세운 기록
    6: ("2026-09", "카톡 연결"),
}
WANT_CONSULTING = {
    1: ("2026-06", "마지막주 리마인드 카톡  or  TEL"),   # 2단계 — 두 달 물림
    2: ("2026-09", "마지막주 리마인드 카톡  or  TEL"),   # 1단계
}


def _seed(db: Path) -> None:
    """이전 **전**의 자료. 줄마다의 `notes` 에 그 칸의 기록을 적어 둔다."""
    con = sqlite3.connect(db)
    try:
        con.execute(
            "INSERT INTO users (id, name, role, weekly_goal_sends, is_active, "
            "must_change_password, can_view_consulting, can_auto_attach_ir, "
            "created_at, updated_at) VALUES (1, '샘플', 'admin', 0, 1, 0, 1, 0, ?, ?)",
            (NOW, NOW))
        for col_id, sheet, label, created in CONTACT_COLUMNS:
            con.execute(
                "INSERT INTO contact_columns (id, sheet, label, position, "
                "is_hidden, created_at, updated_at) VALUES (?,?,?,?,0,?,?)",
                (col_id, sheet, label, col_id, created, created))
        for col_id, sheet, label, created in CONSULTING_COLUMNS:
            con.execute(
                "INSERT INTO consulting_columns (id, sheet, label, position, "
                "created_at, updated_at) VALUES (?,?,?,?,?,?)",
                (col_id, sheet, label, col_id, created, created))
        for target, scope, month, labels in RUNS:
            con.execute(
                "INSERT INTO monthly_column_runs (target, scope, month, labels, "
                "created_at, updated_at) VALUES (?,?,?,?,?,?)",
                (target, scope, month,
                 json.dumps(labels, ensure_ascii=False), NOW, NOW))
        # 열쇠 모양이 표마다 다르다 — 투자사 쪽은 `c12`, 투자컨설턴트 쪽은 `12`.
        con.execute(
            "INSERT INTO vc_contacts (id, user_id, name, channel_kakao, "
            "channel_email, room_verified, status, connect_stage, is_hidden, "
            "notes, created_at, updated_at) "
            "VALUES (1, 1, '샘플 담당자', 1, 0, 'unverified', 'active', "
            "'not_started', 0, ?, ?, ?)",
            (json.dumps({"c1": "완료", "c3": "O", "c5": ""},
                        ensure_ascii=False), NOW, NOW))
        con.execute(
            "INSERT INTO consulting_companies (id, sheet, notes, created_at, "
            "updated_at) VALUES (1, ?, ?, ?, ?)",
            (CONSULT_SHEET,
             json.dumps({"1": "통화함", "2": ""}, ensure_ascii=False), NOW, NOW))
        con.commit()
    finally:
        con.close()


def _fingerprint(db: Path) -> dict:
    """`scripts/check_month_backfill.py` 의 ②와 **같은 셈** — 열쇠 집합의 해시.

    값이 아니라 **열쇠**를 센다. 0075 가 건드릴 수 있었던 것이 열쇠다.
    """
    con = sqlite3.connect(db)
    try:
        out = {}
        for table in ("vc_contacts", "consulting_companies"):
            digest = hashlib.sha256()
            for row_id, notes in con.execute(
                    f"SELECT id, notes FROM {table} ORDER BY id"):
                keys = sorted(json.loads(notes or "{}").keys())
                digest.update(f"{row_id}:{','.join(keys)}\n".encode("utf-8"))
            out[table] = digest.hexdigest()
        return out
    finally:
        con.close()


def _rows(db: Path) -> dict:
    con = sqlite3.connect(db)
    try:
        return {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                for t in ("contact_columns", "consulting_columns",
                          "vc_contacts", "consulting_companies")}
    finally:
        con.close()


def _month_kind(db: Path, table: str) -> dict:
    con = sqlite3.connect(db)
    try:
        return {r[0]: (r[1], r[2]) for r in con.execute(
            f"SELECT id, month, kind FROM {table}")}
    finally:
        con.close()


def _notes(db: Path) -> dict:
    con = sqlite3.connect(db)
    try:
        return {("vc", r[0]): r[1] for r in con.execute(
            "SELECT id, notes FROM vc_contacts ORDER BY id")}
    finally:
        con.close()


@pytest.fixture(scope="module")
def migrated(tmp_path_factory) -> Path:
    """0074 까지 올려 자료를 넣고, 0075 를 올린 DB. 아래 검사들이 나눠 쓴다."""
    db = tmp_path_factory.mktemp("backfill") / "m.db"
    down = _alembic(db, "upgrade", PREV)
    assert down.returncode == 0, down.stdout + down.stderr
    _seed(db)
    up = _alembic(db, "upgrade", "head")
    assert up.returncode == 0, up.stdout + up.stderr
    return db


def test_명단_칸의_달과_종류가_세_단계대로_채워진다(migrated):
    assert _month_kind(migrated, "contact_columns") == WANT_CONTACT


def test_컨설턴트_칸도_같은_규칙으로_채워진다(migrated):
    assert _month_kind(migrated, "consulting_columns") == WANT_CONSULTING


def test_달을_못_읽는_칸은_손대지_않는다(migrated):
    """`NULL` 로 남는다. 그 칸에 적혀 있던 값(`c3`)도 그대로다."""
    got = _month_kind(migrated, "contact_columns")
    assert got[3] == (None, None)
    assert got[4] == (None, None)
    assert json.loads(_notes(migrated)[("vc", 1)])["c3"] == "O"


def test_안쪽_공백이_그대로_실린다(migrated):
    """시트에 있는 두 칸짜리 공백이 값으로도 그대로 올라와야 한다."""
    _, kind = _month_kind(migrated, "consulting_columns")[1]
    assert kind == "마지막주 리마인드 카톡  or  TEL"


def test_notes_가_한_글자도_안_바뀐다(tmp_path):
    """이전 전후로 열쇠 집합 해시가 **반드시 같다**.

    0075 는 값을 옮기지 않는 설계라 여기에 단정을 걸 수 있다. 달라지면 이전이
    `notes` 를 건드린 것이고, 그것은 고장이다.
    """
    db = tmp_path / "notes.db"
    assert _alembic(db, "upgrade", PREV).returncode == 0
    _seed(db)
    before, before_rows, before_notes = _fingerprint(db), _rows(db), _notes(db)

    up = _alembic(db, "upgrade", "head")
    assert up.returncode == 0, up.stdout + up.stderr

    assert _fingerprint(db) == before
    assert _rows(db) == before_rows          # 넣지도 지우지도 않는다
    assert _notes(db) == before_notes        # 글자까지 그대로다


def test_되돌렸다_올리면_같은_자료다(tmp_path):
    """값을 안 옮겼으니 내렸다 올린 DB 는 이전 전과 같아야 한다.

    내려간 자리에서는 칸 둘이 사라지고, 다시 올리면 같은 값으로 채워진다 —
    백필이 **자료를 보고** 답을 내기 때문이다(한 번 쓰고 잊는 계산이 아니다).
    """
    db = tmp_path / "roundtrip.db"
    assert _alembic(db, "upgrade", PREV).returncode == 0
    _seed(db)
    before, before_rows, before_notes = _fingerprint(db), _rows(db), _notes(db)

    assert _alembic(db, "upgrade", "head").returncode == 0
    filled = _month_kind(db, "contact_columns")

    down = _alembic(db, "downgrade", PREV)
    assert down.returncode == 0, down.stdout + down.stderr
    con = sqlite3.connect(db)
    try:
        cols = {r[1] for r in con.execute("PRAGMA table_info(contact_columns)")}
    finally:
        con.close()
    assert "month" not in cols and "kind" not in cols
    assert _fingerprint(db) == before
    assert _rows(db) == before_rows
    assert _notes(db) == before_notes

    again = _alembic(db, "upgrade", "head")
    assert again.returncode == 0, again.stdout + again.stderr
    assert _month_kind(db, "contact_columns") == filled
    assert _fingerprint(db) == before
    assert _rows(db) == before_rows


def test_두_번_올려도_아무_일도_안_일어난다(tmp_path):
    """운영은 배포할 때마다 `upgrade head` 를 한 번 더 한다."""
    db = tmp_path / "twice.db"
    assert _alembic(db, "upgrade", PREV).returncode == 0
    _seed(db)
    assert _alembic(db, "upgrade", "head").returncode == 0
    once = _month_kind(db, "contact_columns"), _fingerprint(db), _rows(db)

    again = _alembic(db, "upgrade", "head")
    assert again.returncode == 0, again.stdout + again.stderr
    assert "Running upgrade" not in again.stdout + again.stderr
    assert (_month_kind(db, "contact_columns"), _fingerprint(db),
            _rows(db)) == once


def test_이주에는_INSERT_도_DELETE_도_없다():
    """설계가 그렇다 — 읽고 `UPDATE` 만 한다. 글자로 못 박는다.

    이 판이 값을 옮기기 시작하면 ②(열쇠 해시가 같다)의 단정이 곧바로 거짓이
    된다. 나중에 한 줄이 끼어드는 것을 여기서 막는다.
    """
    text = (ROOT / "alembic" / "versions" /
            "0075_column_month_kind.py").read_text(encoding="utf-8")
    body = text.split('"""', 2)[2]          # 모듈 설명은 뺀다
    for word in ("INSERT ", "DELETE "):
        assert word not in body.upper(), f"0075 에 {word.strip()} 이 들어왔다"


def test_판의_머리가_하나다():
    """두 사람이 같은 판을 부모로 삼으면 알렘빅이 `Multiple head revisions` 로 멎는다.

    이 저장소에서 번호가 겹쳐 CI 가 터진 적이 있다.
    (`tests/test_migrations.py` 도 같은 것을 본다 — 새 판을 더하는 이 자리에서
    한 번 더 본다.)

    **머리의 이름은 못 박지 않는다.** `0075` 라고 적어 두었더니 그 위에 판을
    하나 얹는 순간 이 검사가 빨개졌다 — 묻는 것은 "머리가 하나인가" 이지
    "머리가 0075 인가" 가 아니다. 대신 0075 가 **사슬 안에 있는지**를 본다:
    누군가 이 판을 사슬에서 떼어 내면 그건 진짜로 잡아야 할 일이다.
    """
    revisions, parents = set(), set()
    for path in (ROOT / "alembic" / "versions").glob("0*.py"):
        text = path.read_text(encoding="utf-8")
        revisions |= set(re.findall(r'^revision = "([^"]+)"', text, re.M))
        parents |= set(re.findall(r'^down_revision = "([^"]+)"', text, re.M))
    heads = revisions - parents
    assert len(heads) == 1, f"머리가 하나여야 한다 — 지금: {sorted(heads)}"
    assert "0075_column_month_kind" in revisions
