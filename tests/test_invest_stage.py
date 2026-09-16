"""선호 투자단계(`stages`) — 판정 · 시트를 읽어 넣는 쪽 · 정리 스크립트.

세 자리가 **같은 함수 하나**(`app/services/invest_stage.decide`)를 부른다.
규칙이 두 군데 적히면 한쪽이 낡고, 그러면 여기서 정리해 둔 것을 다음 업로드가
통째로 되돌린다.

값은 운영 `round_size` 52줄에 실제로 있던 꼴로 짠다. 갈래는 넷이다:

    `Series C 이상 6/30`        확실한 단계 말 (+ 사다리 위로 열린다)
    `Seed~PreA`                 범위 — 사이를 채운다
    `IPO 부서라 Seed … 어려움`   낱말은 있는데 **뜻이 반대**다
    `초기 기업보다는 성장단계…`   어느 칸인지 알 수 없다

**이 파일이 가장 세게 보는 것은 ③이다** — 넣은 값이 `matcher.evaluate_company`
에 실제로 걸리는가. 안 걸리면 칸만 채우고 아무 일도 안 한 것이다.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pytest

from app.services import invest_stage as st
from app.services import matcher

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "fill_stages_from_round.py"

# 운영에 있던 네 꼴. 검사마다 다시 적지 않는다.
CLEAR = "Series C 이상 6/30"          # → SeriesC, Pre-IPO
RANGE = "Pre IPO, Seed~PreA(딥테크 초기기업 한정)"
NEGATED = "IPO 부서라 Seed 단계 검토 어려움 6/23"
# `docs/SHEET_FINDINGS.md §2` 가 이 칸의 실제 모양으로 적어 둔 바로 그 글이다.
VAGUE = "8/19 : 초기 기업보다는 성장단계 기업들 위주로 검토"


# ── ① 단계 말 알아보기 ──────────────────────────────────────────────────────
#
# **표기가 제각각이다.** 대소문자 · 띄어쓰기 · `-` · 한글/영문 · 범위. 아래
# 왼쪽은 전부 운영 `round_size` 에 실제로 있던 글이다(끝의 `6/30` 같은 날짜까지
# 그대로 — 그것이 붙어 있는 것이 실제 모양이다).

@pytest.mark.parametrize("raw,want", [
    # 그냥 한 칸
    ("Series C 6/18", ["SeriesC"]),
    ("Pre-seed 6/30", ["Pre-seed"]),
    ("Pre IPO 또는 상장사 메자닌 7/9", ["Pre-IPO"]),
    # 한글이 **바로 붙는다.** `\b` 로 막으면 이 줄을 통째로 놓친다
    # (한글도 낱말 글자라 경계가 서지 않는다).
    ("Seed단계 위주로 보심", ["Seed"]),
    ("pre-IPO단계 위주 6/23", ["Pre-IPO"]),
    # 쉼표로 여럿 — 사다리 차례로 줄 세워 돌려준다
    ("PreA, Series A, Seed 7/7", ["Seed", "Pre-A", "SeriesA"]),
    # 범위 `~` — 사이를 채운다
    ("Pre-seed ~ Pre-A 6/12", ["Pre-seed", "Seed", "Pre-A"]),
    # 뒤쪽이 **글자 하나**인 범위. 먼저 안 잡으면 `B` 가 홀로 남아 빠진다
    ("Series A~B, PreIPO 7/7", ["SeriesA", "SeriesB", "Pre-IPO"]),
    ("시리즈 B-C 단계나 PRE-IPO 단계 6/17", ["SeriesB", "SeriesC", "Pre-IPO"]),
    # `이상`·`이후` — 사다리 위로 연다
    ("Series C 이상 6/30", ["SeriesC", "Pre-IPO"]),
    ("시리즈 B 이후 6/23", ["SeriesB", "SeriesC", "Pre-IPO"]),
    # 끝에 매달린 `~` 도 열린 범위다
    ("Series C ~", ["SeriesC", "Pre-IPO"]),
    # 섞인 줄 — 금액·분야 설명이 함께 적혀 있어도 읽어낸다
    ("Series A 이상, 대략적인 투자규모는 20억원 내외 7/7",
     ["SeriesA", "SeriesB", "SeriesC", "Pre-IPO"]),
    ("5월말 기준 연내 상장 가능한 Pre IPO 중심으로 보신다고 하심", ["Pre-IPO"]),
])
def test_실제로_있던_표기를_전부_읽어낸다(raw, want):
    assert st.stages_of(raw) == want


def test_사다리_차례로_줄_세운다():
    """`matcher` 가 순서를 보지는 않는다. 그래도 고정해 둔다 — 같은 뜻이 줄마다
    다른 차례로 적히면 화면에서 두 사람을 나란히 놓고 볼 수가 없다."""
    assert st.stages_of("Pre-IPO, Seed, SeriesA") == ["Seed", "SeriesA", "Pre-IPO"]
    assert list(st.LADDER) == sorted(st.LADDER, key=st.LADDER.index)


def test_Pre_로_시작한다고_다_단계가_아니다():
    """운영에 `Pre Value 20-50억 사이` 줄이 있다. `Pre` 만 보고 잡으면 **금액을
    적은 줄이 Pre-A 선호로 둔갑한다.**"""
    assert st.stages_of("Pre Value 20-50억 사이") == []
    assert st.decide("Pre Value 20-50억 사이").action == st.NONE


@pytest.mark.parametrize("raw", [
    "50억 이상 6/24",
    "디지털 헬스분야 6/30",
    "AI 팹리스 벤처기업, 로봇, 드론",
    "PE 7/2",                       # 펀드 종류지 단계가 아니다
    "TIPS 미진행 기업이거나 TIPS 연계 가능성 있는 기업 위주로 소개",
])
def test_단계_말이_없는_줄은_안_건드린다(raw):
    assert st.decide(raw).action == st.NONE
    assert not st.decide(raw).changes


# ── ② 애매한 것 · 뜻이 뒤집힌 것 ────────────────────────────────────────────

@pytest.mark.parametrize("raw", [
    VAGUE,
    "후기 6/16",
    "후기 단계 7/7",
    # 아래 둘은 실제 줄의 **모양**만 옮겼다(긴 서술 + 금액이 섞인 꼴).
    # 이 저장소는 공개라 사람이 적은 문장을 그대로 싣지 않는다.
    "얼리스테이지 기업 위주로 투자를 진행. 30억 내외 밸류 검토 중 7/28",
    "초기 단계에 투자 집중. 기업가치 30 - 70억 정도를 comfort range 로 본다.",
])
def test_초기_후기_같은_말만_있으면_세기만_한다(raw):
    """`초기` 가 Seed 인지 Pre-A 인지 시트에 적혀 있지 않다. 틀리게 넣으면 딜
    고르기가 엉뚱한 단계로 걸러진다 — **비워 두는 쪽이 낫다.**"""
    decision = st.decide(raw)
    assert decision.action == st.VAGUE
    assert decision.stages is None
    assert not decision.changes


def test_뜻이_뒤집힌_줄은_낱말이_있어도_안_넣는다():
    """`IPO 부서라 Seed 단계 검토 어려움` 은 `Seed` 를 품고 있지만 뜻은 정반대다.

    그대로 베끼면 Seed 딜에 `단계 일치` 가 떠서, **안 보겠다고 적어 둔 사람에게
    그 딜이 권해진다.** 비어 있는 것보다 나쁘다.
    """
    decision = st.decide(NEGATED)
    assert decision.action == st.NEGATED
    assert decision.stages is None
    assert not decision.changes
    # 무엇을 보고 막았는지는 남긴다 — 미리보기가 그 낱말을 찍는다.
    assert "Seed" in decision.found


def test_뒤집힌_줄을_그냥_베꼈다면_어떻게_되는지():
    """위 검사가 막고 있는 것이 무엇인지 **눈에 보이게** 못 박는다."""
    naive = st.JOIN.join(st.stages_of(NEGATED))        # 뒤집힘을 안 본 값
    assert naive == "Seed"
    fit = matcher.evaluate_company(_C(stages=naive), _K(series="Seed"))
    assert fit.verdict == matcher.FIT                  # ← 이것이 틀린 결과다
    # 실제 판정은 이 값을 아예 안 만든다.
    assert st.decide(NEGATED).stages is None


def test_이미_값이_있으면_덮지_않는다():
    """사람이 손으로 골라 둔 값을 오래된 시트가 밀어내면 안 된다 — 옆 칸들과
    같은 규칙이다(`_fill_if_empty`)."""
    decision = st.decide(CLEAR, stages="Seed")
    assert decision.action == st.TAKEN
    assert not decision.changes


def test_빈_칸은_아무것도_하지_않는다():
    for empty in ("", "   ", None):
        assert st.decide(empty).action == st.EMPTY


def test_몇_번을_돌려도_같은_자리에_멈춘다():
    """시트는 여러 번 올라오고 정리 스크립트도 다시 돈다."""
    once = st.decide(CLEAR)
    assert once.changes
    twice = st.decide(CLEAR, stages=once.stages)
    assert twice.action == st.TAKEN


# ── ③ **넣은 값이 `matcher` 에 실제로 걸리는가** ────────────────────────────
#
# 이 판의 성패다. `matcher._split_csv` 는 `[,/|]` 로 쪼개고 `_norm` 은 공백·
# 하이픈을 지운다. 넣는 꼴이 그와 안 맞으면 칸만 채우고 판정에는 안 걸린다.

@dataclass
class _C:
    id: int = 1
    sectors: Optional[str] = None
    stages: Optional[str] = None
    round_size: Optional[str] = None


@dataclass
class _K:
    id: int = 10
    name: str = "샘플기업"
    sector_major: Optional[str] = None
    sector_minor: Optional[str] = None
    series: Optional[str] = None
    raise_target: Optional[str] = None


def test_넣는_꼴은_matcher_가_쪼개는_꼴이다():
    value = st.decide(CLEAR).stages
    assert value == "SeriesC, Pre-IPO"
    # 쪼갠 조각이 그대로 사다리의 낱말이어야 한다(빈 조각·붙은 조각이 없다).
    assert matcher._split_csv(value) == ["seriesc", "pre-ipo"]


@pytest.mark.parametrize("series,verdict", [
    ("SeriesC", matcher.FIT),
    ("Series C", matcher.FIT),      # 시트가 띄어 적어도 `_norm` 이 같게 본다
    ("Pre-IPO", matcher.FIT),       # `이상` 으로 열어 둔 칸
    ("Seed", matcher.MISMATCH),
    ("SeriesA", matcher.MISMATCH),
])
def test_Series_C_이상_이_기업의_시리즈와_실제로_맞붙는다(series, verdict):
    fit = matcher.evaluate_company(_C(stages=st.decide(CLEAR).stages),
                                   _K(series=series))
    assert fit.verdict == verdict
    assert any("단계" in r for r in fit.reasons), fit.reasons


def test_범위로_펴_넣은_값도_사이_칸에_걸린다():
    value = st.decide(RANGE).stages
    assert value == "Seed, Pre-A, Pre-IPO"
    for series in ("Seed", "Pre-A", "Pre-IPO"):
        assert matcher.evaluate_company(_C(stages=value),
                                        _K(series=series)).verdict == matcher.FIT
    assert matcher.evaluate_company(_C(stages=value),
                                    _K(series="SeriesB")).verdict == matcher.MISMATCH


def test_비어_있는_동안_단계_축이_통째로_죽어_있었다():
    """고치기 전 상태를 못 박는다 — `stages` 가 비면 `matcher` 는 그 축을 아예
    세지 않는다(`판단 불가`). 채워야 비로소 경고가 선다."""
    before = matcher.evaluate_company(_C(round_size=CLEAR), _K(series="Seed"))
    assert before.verdict == matcher.UNKNOWN
    after = matcher.evaluate_company(_C(round_size=CLEAR,
                                        stages=st.decide(CLEAR).stages),
                                     _K(series="Seed"))
    assert after.verdict == matcher.MISMATCH


def test_라운드_금액_읽기는_그대로_돈다():
    """**원문을 안 건드리는 갈래를 골랐다.** 단계 말이 섞여 있어도
    `parse_round_size_eok` 는 멀쩡히 돈다 — 빼서 얻을 것이 없다는 근거다."""
    raw = "Series A 이상, 대략적인 투자규모는 20억원 내외 7/7"
    assert matcher.parse_round_size_eok(raw) == (20, None)
    # 금액이 아예 없는 줄이 대부분이다(23줄 중 22줄). 빼도 `None` 그대로다.
    assert matcher.parse_round_size_eok(CLEAR) is None


# ── ④ 시트를 읽어 넣는 쪽 ───────────────────────────────────────────────────

def test_시트에는_아직_단계_칸이_없다():
    """**이 사실이 ㉮의 전부다.** 매핑을 붙여도 지금은 아무것도 안 들어온다.

    픽스처 두 장이 실 시트의 머리글을 그대로 옮겨 둔 것이라(`SHEET_FINDINGS`),
    여기서 못 찾으면 실 시트에도 없다. 시트에 칸이 생기는 날 이 검사가 먼저
    깨져서 알려 준다.
    """
    from app.services import sheet_import as si

    from .conftest import FIXTURES

    for name in ("sheet_a_sample.csv", "sheet_a_list_sample.csv"):
        rows = si.read_csv(FIXTURES / name)
        idx = si.detect_header_row(rows, ["이름", "투자사"]) or \
            si.detect_header_row(rows, ["NO", "회사"])
        header = rows[idx]
        assert si.first_column(header, ["투자", "단계"], ["선호", "단계"],
                               ["단계", "태그"]) is None, name
        # 대신 라운드 칸은 있다 — 단계 말이 섞여 들어오는 바로 그 칸이다.
        assert si.find_column(header, ["라운드"]) is not None or \
            si.find_column(header, ["라운드사이즈"]) is not None, name


def _sheet(round_size: str = "", stages_col: bool = False,
           stages: str = "") -> list:
    """가장 작은 시트 A. `stages_col` 이면 **시트에 없는** 단계 칸을 붙여 본다."""
    head = ["번호", "이름", "투자사명", "선호 투자분야", "라운드 사이즈"]
    row = ["1", "홍길동 대표님", "가나벤처스", "", round_size]
    if stages_col:
        head.append("선호 투자단계")
        row.append(stages)
    return [head, row]


def _apply(db, rows):
    from app.services import sheet_import as si

    parsed = si.parse_sheet_a(rows, year=2026)
    return si.apply_sheet_a(db, parsed, user_id=1, source_label="가상명단")


def _contact(db):
    from app.models import VcContact

    return db.query(VcContact).filter(VcContact.name == "홍길동").one()


def test_임포트가_라운드_칸에서_단계를_읽어_넣는다(db, users):
    report = _apply(db, _sheet(round_size=CLEAR))
    contact = _contact(db)
    assert contact.stages == "SeriesC, Pre-IPO"
    # **원문은 한 글자도 안 건드린다.**
    assert contact.round_size == CLEAR
    assert "넣음 1행" in report.as_text("가상")


def test_임포트는_뒤집힌_줄과_애매한_줄을_세어서_알린다(db, users):
    """조용히 비워 두면 사용자가 그 줄을 손으로 채울 기회를 못 얻는다."""
    rows = _sheet(round_size=NEGATED)
    rows.append(["2", "김철수 대표님", "다라벤처스", "", VAGUE])
    report = _apply(db, rows)
    text = report.as_text("가상")
    assert "애매해서 안 넣음 1행" in text
    assert "뜻이 뒤집혀 안 넣음 1행" in text
    assert _contact(db).stages is None


def test_단계_칸이_있는_시트는_그_칸을_원문_그대로_쓴다(db, users):
    """그 칸에 적은 것은 사람이 **단계를 적을 자리라고 알고** 적은 값이다.
    여기서 다시 읽어 고치면 근거 없이 뜻이 바뀐다."""
    _apply(db, _sheet(round_size=CLEAR, stages_col=True, stages="Seed, SeriesA"))
    assert _contact(db).stages == "Seed, SeriesA"


def test_단계를_안_건드린_시트는_리포트에_줄을_안_늘린다(db, users):
    report = _apply(db, _sheet(round_size="50억 이상 6/24"))
    assert _contact(db).stages is None
    assert "선호 투자단계를 라운드 사이즈 칸에서 읽었습니다" not in report.as_text("가상")


def test_임포트는_손으로_적어_둔_단계를_밀어내지_않는다(db, users):
    _apply(db, _sheet(round_size=CLEAR, stages_col=True, stages="Seed"))
    _apply(db, _sheet(round_size=CLEAR))
    assert _contact(db).stages == "Seed"


def test_넣은_값이_DB_를_지나_matcher_까지_간다(db, users):
    """**끝에서 끝까지.** 시트 → DB → `matcher` 가 실제로 경고를 낸다."""
    from app.models import IrCompany

    _apply(db, _sheet(round_size=CLEAR))
    company = IrCompany(name="샘플기업", series="Seed")
    db.add(company)
    db.commit()

    result = matcher.evaluate_contact(_contact(db), [company])
    assert result.mismatch_count == 1
    assert result.warnings


# ── ⑤ 정리 스크립트 ─────────────────────────────────────────────────────────

def _seed(db):
    """네 꼴을 한 줄씩. 스크립트가 각각을 어떻게 가르는지 본다."""
    from app.models import VcContact

    rows = [
        VcContact(user_id=1, name="가", firm="가벤처스", round_size=CLEAR),
        VcContact(user_id=1, name="나", firm="나벤처스", round_size=RANGE),
        VcContact(user_id=1, name="다", firm="다벤처스", round_size=NEGATED),
        VcContact(user_id=1, name="라", firm="라벤처스", round_size=VAGUE),
        VcContact(user_id=1, name="마", firm="마벤처스", round_size="50억 이상"),
        # 이미 손으로 채워 둔 줄 — 덮지 않는다.
        VcContact(user_id=1, name="바", firm="바벤처스", round_size=CLEAR,
                  stages="Seed"),
    ]
    db.add_all(rows)
    db.commit()
    return {r.name: r.id for r in rows}


def _run(db_path: Path, *args) -> str:
    out = subprocess.run(
        [sys.executable, str(SCRIPT), "--db", str(db_path), *args],
        capture_output=True, text=True, cwd=str(ROOT), check=False)
    assert out.returncode == 0, out.stdout + out.stderr
    return out.stdout


def _db_path() -> Path:
    import os

    return Path(os.environ["DATABASE_URL"][len("sqlite:///"):])


def _read(path: Path, row_id: int) -> tuple:
    con = sqlite3.connect(str(path))
    try:
        return con.execute(
            "SELECT stages, round_size FROM vc_contacts WHERE id = ?",
            (row_id,)).fetchone()
    finally:
        con.close()


def _fingerprint(path: Path) -> str:
    """이 표의 **모든 칸**을 한 글자도 빼지 않고 sha256 으로 접는다.

    파일 자체를 해싱하지 않는 이유: SQLite 파일은 같은 내용이라도 페이지 배치·
    빈자리 목록이 달라질 수 있어 바이트가 흔들린다. 여기서 보려는 것은 **자료가
    원래대로인가**지 파일 배치가 같은가가 아니다.
    """
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        cols = [r[1] for r in con.execute("PRAGMA table_info(vc_contacts)")]
        names = ", ".join(cols)
        rows = list(con.execute(
            f"SELECT {names} FROM vc_contacts ORDER BY id"))
    finally:
        con.close()
    blob = json.dumps([cols, rows], ensure_ascii=False, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def test_미리보기가_기본이고_DB_에_한_글자도_안_쓴다(db, users):
    """`--apply` 를 안 주면 읽기 전용(`mode=ro`)으로 연다 — 쓸 길 자체가 없다."""
    _seed(db)
    path = _db_path()
    before = _fingerprint(path)

    text = _run(path, "--dry-run")

    assert "미리보기" in text
    assert _fingerprint(path) == before


def _counted(text: str, label: str) -> int:
    """미리보기 표에서 그 줄이 센 수. **자릿수 맞춤에 기대지 않는다.**"""
    found = re.search(re.escape(label) + r"\)?\s+(\d+)", text)
    assert found, f"미리보기에 `{label}` 줄이 없다:\n{text}"
    return int(found.group(1))


def test_미리보기가_여섯_갈래를_갈라_센다(db, users):
    ids = _seed(db)
    text = _run(_db_path(), "--dry-run", "--limit", "0")

    assert _counted(text, "넣음") == 2          # 가 · 나
    assert _counted(text, "애매") == 1          # 라
    assert _counted(text, "뒤집힘") == 1        # 다
    assert _counted(text, "단계없음") == 1      # 마
    assert _counted(text, "이미있음") == 1      # 바
    # **안 건드린 줄을 따로 찍는다.** 이 수가 이 작업에서 가장 중요한 셈이다 —
    # 틀리게 넣으면 딜 고르기가 엉뚱한 단계로 걸러진다.
    assert "일부러 안 건드린** 줄: 2줄" in text
    assert str(ids["가"]) in text


def test_미리보기는_값을_안_찍는다(db, users):
    """이 칸에는 투자사 이야기가 섞여 있다. 기본은 **모양(길이)**뿐이다."""
    _seed(db)
    quiet = _run(_db_path(), "--dry-run", "--limit", "0")
    assert VAGUE not in quiet
    assert CLEAR not in quiet

    loud = _run(_db_path(), "--dry-run", "--limit", "0", "--show-values")
    assert CLEAR[:30] in loud


def test_되돌릴_파일_없이는_바꾸지_않는다(db, users):
    _seed(db)
    out = subprocess.run(
        [sys.executable, str(SCRIPT), "--db", str(_db_path()), "--apply"],
        capture_output=True, text=True, cwd=str(ROOT), check=False)
    assert out.returncode == 2
    assert "--save-baseline" in out.stderr


def test_확실한_줄만_넣고_라운드_원문은_안_건드린다(db, users, tmp_path):
    ids = _seed(db)
    path = _db_path()

    _run(path, "--apply", "--save-baseline", str(tmp_path / "before.json"))

    assert _read(path, ids["가"]) == ("SeriesC, Pre-IPO", CLEAR)
    assert _read(path, ids["나"]) == ("Seed, Pre-A, Pre-IPO", RANGE)
    assert _read(path, ids["다"]) == (None, NEGATED)        # 뒤집힘 — 안 건드림
    assert _read(path, ids["라"]) == (None, VAGUE)          # 애매 — 안 건드림
    assert _read(path, ids["마"]) == (None, "50억 이상")
    assert _read(path, ids["바"]) == ("Seed", CLEAR)        # 이미 있던 값 그대로


def test_넣은_뒤에_matcher_가_그_줄을_실제로_거른다(db, users, tmp_path):
    """**이 검사가 이 작업의 성패다.** 스크립트가 적은 글자를 그대로 다시 읽어
    `matcher` 에 물린다 — 꼴이 어긋나면 여기서 걸린다."""
    from app.models import IrCompany, VcContact

    ids = _seed(db)
    _run(_db_path(), "--apply", "--save-baseline", str(tmp_path / "b.json"))

    db.expire_all()
    contact = db.get(VcContact, ids["가"])
    assert matcher.evaluate_company(
        contact, IrCompany(name="샘플기업", series="SeriesC")).verdict == matcher.FIT
    assert matcher.evaluate_company(
        contact, IrCompany(name="샘플기업", series="Seed")).verdict == matcher.MISMATCH


def test_되돌리면_sha256_이_한_글자도_안_달라진다(db, users, tmp_path):
    ids = _seed(db)
    path = _db_path()
    keep = tmp_path / "before.json"
    before = _fingerprint(path)

    _run(path, "--apply", "--save-baseline", str(keep))
    assert _fingerprint(path) != before                     # 정말 바뀌었다
    assert _read(path, ids["가"])[0] == "SeriesC, Pre-IPO"

    _run(path, "--restore", str(keep), "--apply")
    assert _fingerprint(path) == before


def test_떠_둔_파일에는_넣는_줄만_전후로_들어간다(db, users, tmp_path):
    ids = _seed(db)
    keep = tmp_path / "before.json"
    _run(_db_path(), "--dry-run", "--save-baseline", str(keep))

    data = json.loads(keep.read_text(encoding="utf-8"))
    assert {item["id"] for item in data} == {ids["가"], ids["나"]}
    one = next(i for i in data if i["id"] == ids["가"])
    assert one["before"]["stages"] is None
    assert one["after"]["stages"] == "SeriesC, Pre-IPO"
    # 원문은 전·후가 같다 — 안 건드린다는 약속이 파일에도 남는다.
    assert one["before"]["round_size"] == one["after"]["round_size"] == CLEAR


def test_바꾼_뒤_기준과_맞추면_합격이_나온다(db, users, tmp_path):
    _seed(db)
    path = _db_path()
    keep = tmp_path / "before.json"

    _run(path, "--apply", "--save-baseline", str(keep))
    text = _run(path, "--baseline", str(keep))
    assert "어긋남 0줄" in text


def test_기준과_어긋나면_알려_준다(db, users, tmp_path):
    """맞춰 보기가 늘 합격이면 맞춰 본 것이 아니다."""
    ids = _seed(db)
    path = _db_path()
    keep = tmp_path / "before.json"
    _run(path, "--apply", "--save-baseline", str(keep))

    con = sqlite3.connect(str(path))
    con.execute("UPDATE vc_contacts SET stages = 'Seed' WHERE id = ?",
                (ids["가"],))
    con.commit()
    con.close()

    out = subprocess.run(
        [sys.executable, str(SCRIPT), "--db", str(path), "--baseline", str(keep)],
        capture_output=True, text=True, cwd=str(ROOT), check=False)
    assert out.returncode == 1
    assert "어긋남 1줄" in out.stdout


# ── ⑥ 명단 스크립트의 머리글 매핑 ───────────────────────────────────────────
#
# ㉮(앞으로 들어오는 길)는 지금 **아무 값도 안 옮긴다** — 시트에 단계 칸이 없기
# 때문이다(위 `test_시트에는_아직_단계_칸이_없다`). 그래도 걸어 두는 값이 있다:
# 시트에 칸이 생기는 날 코드를 고치지 않아도 들어온다. 대신 **걸어 두는 것 자체가
# 옆 칸을 밟지 않는지**는 지금 확인해야 한다.

def test_명단_스크립트가_단계_머리글을_잡는다():
    from scripts.import_investor_list import _columns_of

    header = ["이름", "투자사명", "선호 투자분야", "선호 투자단계", "라운드 사이즈"]
    where = _columns_of(header)
    assert header[where["stages"]] == "선호 투자단계"
    # **옆 칸을 뺏지 않는다.** `선호 투자단계` 안에 `선호 투자분야` 의 조각이
    # 있어서, 차례가 어긋나면 한 열이 두 칸 노릇을 한다.
    assert header[where["sectors"]] == "선호 투자분야"
    assert header[where["round_size"]] == "라운드 사이즈"


def test_명단_스크립트는_단계_칸이_없는_시트에서_아무것도_안_잡는다():
    """실제 시트가 지금 그렇다. 없는 칸을 억지로 잡으면 엉뚱한 열이 들어온다."""
    from scripts.import_investor_list import _columns_of

    where = _columns_of(["그룹/투자분야/라운드사이즈", "이름", "투자사명", "기타"])
    assert "stages" not in where


def test_명함_시트_스크립트도_한_열을_한_칸에만_준다():
    """`import_vc_sheets` 는 머리글을 **포함**으로 맞춘다. `선호 투자단계` 는
    `선호 투자` 에도 걸리므로, 잡힌 자리를 빼 두지 않으면 단계 값이 `sectors`
    로도 들어간다."""
    from scripts.import_vc_sheets import columns_of

    head = {"이름": 1, "선호 투자분야": 2, "선호 투자단계": 3, "라운드 사이즈": 4}
    where = columns_of(head)
    got = {field: col for col, field in where.values()}
    assert got["stages"] == 3
    assert got["sectors"] == 2
    assert got["round_size"] == 4
    # 한 열이 두 칸에 걸리지 않았다.
    assert len({col for col, _f in where.values()}) == len(where)
