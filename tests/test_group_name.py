"""그룹 칸은 **정해 둔 갈래만** 담는다 — 판정 · 임포트 거르기 · 정리 스크립트.

세 자리가 **같은 함수 하나**(`app/services/group_name.decide`)를 부른다. 규칙이
두 군데 적히면 한쪽이 낡고, 그러면 여기서 정리해 둔 것을 다음 업로드가 통째로
되돌린다 — 이 저장소가 반복해서 데인 자리다. 그래서 아래 검사는 판정만 보지
않고, **시트를 읽어 넣는 쪽과 정리 스크립트가 그 판정을 실제로 지나는지**까지
본다.

갈래는 **두 줄기**다. 한 글자 여섯(`A`~`F`)과, 사용자가 그 뒤로 쓰기 시작한
**뜻이 있는 이름들**(`특정분야` · `Pre IPO` · `Series B 이상` … 50줄). 물었더니
"일부러 넣은 것이고 앞으로도 쓴다" 였다 — 그래서 이름도 갈래로 인정한다.

**바뀌지 않은 것이 이 파일의 절반이다**: 문장은 여전히 안 들어온다. 이름을
더한다고 `Seed~PreA 30억` 까지 통과시키면 158줄이 그대로 돌아온다.

값은 운영에 실제로 있던 **여섯 꼴**로 짠다:

    `A`                  이미 맞는 값(한 글자)
    `특정분야`            이미 맞는 값(이름) — 가장 많이 쓰는 이름이다
    `b그룹`               갈래인데 표기가 다르다
    `Seed~PreA 30억`      `round_size` 에 이미 있는 말
    `AI/바이오`            `sectors` 에 이미 있는 말
    `첫 미팅은 대면 선호`   여기에만 있는 말
"""
from __future__ import annotations

import json
import re
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from html import unescape

from app.services import group_name as gn

ROOT = Path(__file__).resolve().parent.parent

# 운영에 있던 다섯 꼴. 검사마다 다시 적지 않는다 — 한 곳에서 고치면 전부 따라온다.
ROUND = "Seed~Pre A | 30억"
SECTORS = "AI,바이오"
ONLY_HERE = "첫 미팅은 대면 선호"


# ── ① 판정 ──────────────────────────────────────────────────────────────────

def test_A부터_F까지는_그대로_통과한다():
    for one in gn.GROUPS:
        assert gn.decide(one).action == gn.KEEP
        assert gn.decide(one).group == one


def test_사용자가_쓰는_이름들도_그대로_통과한다():
    """**사용자가 일부러 넣은 값**이라 통과시켜야 한다 — 안 그러면 다음
    업로드·정리에서 메모로 쓸려 간다.

    처음엔 여덟이었고, 한 명단을 선호로 다시 묶으면서 다섯이 늘었다
    (`공통` · `딥테크·제조` · `ESG·푸드·애그테크` · `Seed~Pre-A` ·
    `Series A~B`). 수를 여기 적지 않는다 — 목록이 늘 때마다 검사 이름만
    낡는다. `services/pref_group` 이 내놓는 이름이 전부 여기 있는지는
    `tests/test_pref_group.py` 가 따로 못 박는다.
    """
    for name in gn.NAMED:
        assert gn.decide(name).action == gn.KEEP, name
        assert gn.decide(name).group == name, name
    # 받아들이는 값과 화면의 고정 보기는 **같은 목록 하나**에서 나온다.
    assert gn.KNOWN == gn.GROUPS + gn.NAMED
    assert gn.CHOICES == ",".join(gn.KNOWN)


def test_이름은_적어_둔_글자_그대로_돌려준다():
    """표기가 갈린 것은 **제 글자로 모은다.** 표에서 고른 값과 창에서 친 값이
    한 글자라도 다르면 딜 제안 관리에서 다른 그룹이 된다."""
    for raw, want in (("series b이상", "Series B 이상"), ("PRE IPO", "Pre IPO"),
                      ("Series  C이상", "Series C 이상"), ("m&a", "M&A"),
                      ("seed", "Seed"), ("tips", "TIPS")):
        decision = gn.decide(raw)
        assert decision.action == gn.FIX, raw
        assert decision.group == want, raw
    # 앞뒤 공백만 다른 것은 `decide` 가 먼저 다듬으므로 **고칠 것이 없다**.
    assert gn.decide(" 특정분야 ").action == gn.KEEP
    assert gn.decide(" 특정분야 ").group == "특정분야"


def test_Seed_는_라운드_칸과_겹쳐_보여도_안_지운다():
    """`Seed` 는 갈래이면서 `round_size` 에도 흔히 든 말이다. 겹침을 먼저 보면
    사용자가 고른 갈래가 **소리 없이 비워진다** — 차례(② 가 ③ 보다 앞)가 그것을
    막는다. 이 검사는 그 차례를 지킨다."""
    decision = gn.decide("Seed", round_size="Seed~Pre A | 30억", sectors="")
    assert decision.action == gn.KEEP
    assert decision.group == "Seed"


def test_b그룹도_소문자_a도_한_글자로_읽는다():
    """골라서 거르는 칸이라, 갈래로 안 맞으면 필터에서 따로 떨어져 나온다."""
    for raw, want in (("b그룹", "B"), ("a", "A"), ("C 그룹", "C"),
                      (" f그룹 ", "F"), ("그룹 D", "D")):
        decision = gn.decide(raw)
        assert decision.action == gn.FIX, raw
        assert decision.group == want, raw


def test_G_는_그룹이_아니다():
    """한 글자는 여섯뿐이다. 일곱 번째 글자를 통과시키면 고르는 칸이 아니게 된다."""
    assert gn.decide("G").action == gn.MOVE
    assert gn.letter("G") is None
    assert gn.canonical("G") is None


def test_이름을_더했다고_문장까지_들어오지는_않는다():
    """이 파일의 절반이 이것이다. 전에 158줄이 문장이었고 그중 64줄이 메모로
    갔다 — 갈래를 넓혔다고 그 문장들이 다시 그룹 칸에 앉으면 안 된다."""
    for sentence in ("Seed~PreA 30억", "Series B 이상 선호하고 바이오만 봄",
                     "AI/바이오 선호", "첫 미팅은 대면 선호", "TIPS 운영사 투자금 1-10억"):
        assert gn.canonical(sentence) is None, sentence
        assert gn.decide(sentence, round_size="", sectors="").action == gn.MOVE, sentence


def test_라운드_칸에_이미_있는_말은_메모로_옮기지_않고_비운다():
    """옮기면 같은 말이 **세 군데**가 된다 — 그룹 · 라운드 · 메모."""
    decision = gn.decide(ROUND, round_size=ROUND, sectors="", memo="")
    assert decision.action == gn.DROP
    assert decision.group is None
    assert decision.memo is None          # 메모는 건드리지 않는다


def test_겹침은_띄어쓰기와_구분_기호를_지우고_본다():
    """같은 말이 `Seed~Pre A | 30억` 과 `Seed~PreA/30억` 로 갈려 적혀 있다."""
    assert gn.overlaps("Seed~PreA/30억", "Seed~Pre A | 30억")
    assert gn.overlaps("AI · 바이오", "AI,바이오")
    # 한쪽이 다른 쪽에 들어가기만 해도 같은 말로 본다(길이가 다를 수 있다).
    assert gn.overlaps("AI", "AI,바이오,핀테크")


def test_빈_칸은_어느_말과도_안_겹친다():
    """빈 글자는 어느 글에나 들어간다. 안 막으면 `round_size` 가 빈 줄의 그룹
    값이 통째로 "겹친다" 로 판정돼 소리 없이 사라진다."""
    assert not gn.overlaps(ONLY_HERE, "")
    assert not gn.overlaps(ONLY_HERE, None)
    assert not gn.overlaps("", ONLY_HERE)
    assert gn.decide(ONLY_HERE, round_size="", sectors="").action == gn.MOVE


def test_선호_투자분야와_겹치는_말도_비운다():
    assert gn.decide(SECTORS, round_size="", sectors=SECTORS).action == gn.DROP


def test_아무_데도_없는_말은_메모_뒤로_옮기고_출처를_적는다():
    decision = gn.decide(ONLY_HERE, round_size=ROUND, sectors=SECTORS,
                         memo="8/20 통화")
    assert decision.action == gn.MOVE
    assert decision.group is None
    assert decision.memo == f"8/20 통화\n{gn.MOVED_MARK} {ONLY_HERE}"
    assert decision.moved == ONLY_HERE


def test_메모가_비어_있으면_줄바꿈_없이_넣는다():
    decision = gn.decide(ONLY_HERE, memo=None)
    assert decision.memo == f"{gn.MOVED_MARK} {ONLY_HERE}"


def test_같은_말이_메모에_이미_있으면_두_번_붙이지_않는다():
    """시트는 여러 번 올라오고 정리 스크립트도 다시 돈다. 돌 때마다 쌓이면
    메모를 읽을 수가 없다 — **몇 번을 돌려도 같은 자리에 멈춰야** 한다."""
    once = gn.decide(ONLY_HERE, memo="").memo
    twice = gn.decide(ONLY_HERE, memo=once)
    assert twice.action == gn.MOVE
    assert twice.memo is None             # 붙일 것이 없다 = 메모 그대로
    assert twice.moved == ""


def test_빈_그룹_칸은_아무것도_하지_않는다():
    for empty in ("", "   ", None):
        decision = gn.decide(empty)
        assert decision.action == gn.EMPTY
        assert not decision.changes


# ── ② 칸 정의 ───────────────────────────────────────────────────────────────

def test_그룹_칸은_정해_둔_갈래를_고르는_칸이고_필터가_붙는다():
    """이름을 `그룹` 으로 줄인 것이 이 판의 핵심이다. 옛 이름
    (`그룹/투자분야/라운드사이즈`)이 세 가지를 한 칸에 적으라고 시켰다."""
    from app.services import contact_columns as cc

    column = next(c for c in cc.INVESTOR_MONTHLY_LAYOUT.head
                  if c.key == "group_name")
    assert column.label == "그룹"
    assert column.kind == "pick"
    # **글자를 여기 다시 적지 않는다.** 배치가 목록을 따로 들면, 화면에서 고른
    # 값이 임포트에서는 없는 값이 되는 날이 온다.
    assert column.choices == gn.CHOICES
    assert column.choices.startswith("A,B,C,D,E,F,")   # 한 글자가 먼저다
    for name in gn.NAMED:
        assert name in column.choices.split(","), name
    # `filterable` 은 `kind == "pick"` 이다 — 고르는 칸이니 필터가 붙는 것이 맞다.
    assert column.filterable
    # 표에 서는 것은 지금까지 그대로다(이 판에서 건드리지 않았다).
    assert column.in_table


def test_그룹_머리글은_필터_단추까지_한_줄에_들어간다():
    """폭은 값(한 글자)이 아니라 **필터를 건 뒤의 머리글**에 맞춘다 —
    `견적서 첨부여부`·`계약여부` 가 같은 자를 쓴다. 값 길이로 잡으면 화면에서는
    멀쩡하다가 필터를 거는 순간 머리글이 두 줄로 접힌다.
    """
    from app.services import contact_columns as cc

    from .test_ui_layout import _text_px

    column = next(c for c in cc.INVESTOR_MONTHLY_LAYOUT.head
                  if c.key == "group_name")
    need = round(_text_px(f"{column.label} (1) ▾") + 18 + 14)
    assert column.width >= need, f"머리글이 두 줄로 접힌다: {need}px 필요"
    # 옛 폭(156px)은 옛 **이름**에 맞춘 값이었다. 한 글자 값에 그대로 두면
    # 달마다 칸이 늘어나는 이 표에서 68px 을 헛되이 먹는다.
    assert column.width < 156


# ── ③ 시트를 읽어 넣는 쪽 ───────────────────────────────────────────────────

def _sheet(group: str, round_size: str = "", sectors: str = "",
           memo: str = "") -> list:
    """다섯 꼴을 한 줄씩 넣을 수 있는 가장 작은 시트 A.

    머리글은 `tests/fixtures/sheet_a_sample.csv` 와 같은 결로 적는다 — 그룹 ·
    투자분야 · 라운드가 **각자 칸을 가진** 모양이다. 셋이 한 머리글에 붙은
    시트에서는 임포터가 그 한 칸을 라운드 칸으로도 읽어(`combined`) 같은 글이
    이미 `round_size` 에 들어간다 — 그것은 아래 `라운드 칸에 이미 있는 말`
    검사가 보는 그 상황이다.
    """
    return [
        ["번호", "그룹", "이름", "투자사명", "담당자",
         "선호 투자분야", "라운드 사이즈", "메모"],
        ["1", group, "홍길동 대표님", "가나벤처스", "", sectors, round_size, memo],
    ]


def _apply(db, rows):
    from app.services import sheet_import as si

    parsed = si.parse_sheet_a(rows, year=2026)
    return si.apply_sheet_a(db, parsed, user_id=1, source_label="가상명단")


def _contact(db):
    from app.models import VcContact

    return db.query(VcContact).filter(VcContact.name == "홍길동").one()


def test_임포트는_b그룹을_B_로_고쳐_넣는다(db, users):
    """시트 머리글은 아직 `그룹/투자분야/라운드사이즈` 다. 화면 이름만 바꾸면
    다음 업로드에 문장이 그대로 또 들어온다."""
    report = _apply(db, _sheet("b그룹"))
    assert _contact(db).group_name == "B"
    assert "A~F 로 고침 1행" in report.as_text("가상")


def test_임포트는_그룹_칸의_문장을_메모로_옮기고_그룹을_비운다(db, users):
    report = _apply(db, _sheet(ONLY_HERE, memo="8/20 통화"))
    contact = _contact(db)
    assert contact.group_name is None
    assert contact.memo == f"8/20 통화\n{gn.MOVED_MARK} {ONLY_HERE}"
    # **몇 줄을 옮겼는지 결과에 적는다.** 조용히 옮기면 사용자가 자기가 적은
    # 글이 어디로 갔는지 못 찾는다.
    text = report.as_text("가상")
    assert "메모 뒤로 옮김 1행" in text
    assert gn.MOVED_MARK in text


def test_임포트는_라운드_칸에_이미_있는_말을_그룹에_안_넣는다(db, users):
    report = _apply(db, _sheet(ROUND, round_size=ROUND))
    contact = _contact(db)
    assert contact.group_name is None
    # 메모에도 안 붙인다 — 같은 말이 세 군데가 되면 안 된다.
    assert gn.MOVED_MARK not in (contact.memo or "")
    assert "안 넣음 1행" in report.as_text("가상")


def test_임포트는_선호_투자분야와_겹치는_말도_안_넣는다(db, users):
    _apply(db, _sheet(SECTORS, sectors=SECTORS))
    assert _contact(db).group_name is None


def test_같은_시트를_두_번_넣어도_메모가_두_번_적히지_않는다(db, users):
    """시트는 여러 번 올라온다. 올릴 때마다 같은 문장이 쌓이면 대화내역 메모가
    읽을 수 없게 된다(그 칸은 원래도 가장 긴 칸이다)."""
    _apply(db, _sheet(ONLY_HERE))
    _apply(db, _sheet(ONLY_HERE))
    assert _contact(db).memo.count(gn.MOVED_MARK) == 1


def test_그룹_칸을_안_건드린_시트는_리포트에_줄을_안_늘린다(db, users):
    """A~F 만 든 시트에는 알릴 것이 없다. 0만 늘어놓으면 정작 봐야 할 줄이 묻힌다."""
    report = _apply(db, _sheet("A"))
    assert _contact(db).group_name == "A"
    assert "그룹 칸은 A~F 만 담습니다" not in report.as_text("가상")


def test_임포트는_손으로_골라_둔_그룹을_밀어내지_않는다(db, users):
    """옆 칸들과 같은 규칙이다(`_fill_if_empty`) — 오래된 시트 한 장이 사람이
    고쳐 둔 값을 되돌리면 안 된다."""
    _apply(db, _sheet("C"))
    _apply(db, _sheet("d그룹"))
    assert _contact(db).group_name == "C"


# ── ④ 정리 스크립트 ─────────────────────────────────────────────────────────

SCRIPT = ROOT / "scripts" / "clean_group_name.py"


def _seed(db):
    """여섯 꼴을 한 줄씩. 스크립트가 각각을 어떻게 가르는지 본다."""
    from app.models import VcContact

    rows = [
        VcContact(user_id=1, name="가", firm="가벤처스", group_name="A"),
        # 사용자가 일부러 넣은 이름. **스크립트가 건드리면 안 되는 줄**이다.
        VcContact(user_id=1, name="사", firm="사벤처스", group_name="특정분야"),
        VcContact(user_id=1, name="나", firm="나벤처스", group_name="b그룹"),
        VcContact(user_id=1, name="다", firm="다벤처스", group_name=ROUND,
                  round_size=ROUND),
        VcContact(user_id=1, name="라", firm="라벤처스", group_name=SECTORS,
                  sectors=SECTORS),
        VcContact(user_id=1, name="마", firm="마벤처스", group_name=ONLY_HERE,
                  memo="8/20 통화"),
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
            "SELECT group_name, memo FROM vc_contacts WHERE id = ?",
            (row_id,)).fetchone()
    finally:
        con.close()


def test_미리보기가_기본이고_DB_에_한_글자도_안_쓴다(db, users, tmp_path):
    """`--apply` 를 안 주면 읽기 전용(`mode=ro`)으로 연다 — 쓸 길 자체가 없다."""
    ids = _seed(db)
    path = _db_path()
    before = {name: _read(path, row_id) for name, row_id in ids.items()}

    text = _run(path, "--dry-run")

    assert "미리보기" in text
    for name, row_id in ids.items():
        assert _read(path, row_id) == before[name], name


def _counted(text: str, label: str) -> int:
    """미리보기 표에서 그 줄이 센 수. **자릿수 맞춤에 기대지 않는다** —
    칸 폭을 손보면 검사가 깨지는데, 이 검사가 보는 것은 폭이 아니라 셈이다."""
    found = re.search(re.escape(label) + r"\)?\s+(\d+)", text)
    assert found, f"미리보기에 `{label}` 줄이 없다:\n{text}"
    return int(found.group(1))


def test_미리보기가_다섯_꼴을_갈라_센다(db, users):
    ids = _seed(db)
    text = _run(_db_path(), "--dry-run", "--limit", "0")

    assert _counted(text, "그대로 (정해 둔 갈래") == 2      # `A` 와 `특정분야`
    assert _counted(text, "고침   (표기만 다름") == 1
    assert _counted(text, "라운드 사이즈와 겹침") == 1
    assert _counted(text, "선호 투자분야와 겹침") == 1
    assert _counted(text, "둘 다 겹침") == 0
    assert _counted(text, "옮김   (아무 데도 안 겹침") == 1
    # 바뀌는 줄은 id 로 가리킨다.
    assert str(ids["나"]) in text


def test_정리_스크립트는_사용자가_넣은_이름을_안_건드린다(db, users, tmp_path):
    """운영에서 50줄이 이름 갈래를 쓴다. 스크립트를 다시 돌릴 일이 생겼을 때
    그 값을 메모로 쓸어 가면, 사용자가 일부러 넣은 것이 사라진다.

    `--apply` 까지 돌려서 본다 — 미리보기만 보면 "세는 자리는 맞는데 쓰는
    자리가 다른" 경우를 못 잡는다.
    """
    from app.models import VcContact

    ids = {}
    for i, name in enumerate(gn.NAMED):
        row = VcContact(user_id=1, name=f"이름{i}", firm=f"{i}벤처스",
                        group_name=name, memo="8/20 통화")
        db.add(row)
        db.flush()
        ids[name] = row.id
    db.commit()
    path = _db_path()

    # `--apply` 는 되돌릴 파일을 반드시 받는다(스크립트가 정한 규칙).
    _run(path, "--apply", "--save-baseline", str(tmp_path / "group.json"))

    for name, row_id in ids.items():
        group, memo = _read(path, row_id)
        assert group == name, name          # 그대로 있다
        assert memo == "8/20 통화", name     # 메모에 옮겨 붙지도 않았다
        assert gn.MOVED_MARK not in (memo or ""), name


def test_미리보기는_값을_안_찍는다(db, users):
    """이 칸에는 투자사·사람 이야기가 섞여 있다. 기본은 **모양(길이)**뿐이다."""
    _seed(db)
    quiet = _run(_db_path(), "--dry-run", "--limit", "0")
    assert ONLY_HERE not in quiet
    assert ROUND not in quiet

    loud = _run(_db_path(), "--dry-run", "--limit", "0", "--show-values")
    assert ONLY_HERE in loud


def test_되돌릴_파일_없이는_바꾸지_않는다(db, users):
    """되돌릴 길 없이 526줄을 건드리게 두지 않는다."""
    _seed(db)
    out = subprocess.run(
        [sys.executable, str(SCRIPT), "--db", str(_db_path()), "--apply"],
        capture_output=True, text=True, cwd=str(ROOT), check=False)
    assert out.returncode == 2
    assert "--save-baseline" in out.stderr


def test_고치고_비우고_옮긴다(db, users, tmp_path):
    ids = _seed(db)
    path = _db_path()
    keep = tmp_path / "before.json"

    _run(path, "--apply", "--save-baseline", str(keep))

    assert _read(path, ids["가"]) == ("A", None)            # 그대로
    assert _read(path, ids["나"])[0] == "B"                 # 고침
    assert _read(path, ids["다"]) == (None, None)           # 지움 (라운드와 겹침)
    assert _read(path, ids["라"]) == (None, None)           # 지움 (분야와 겹침)
    assert _read(path, ids["마"]) == (
        None, f"8/20 통화\n{gn.MOVED_MARK} {ONLY_HERE}")     # 옮김


def test_떠_둔_파일로_원래대로_되돌린다(db, users, tmp_path):
    """바꾸기 전 `(id, group_name, memo)` 를 통째로 적어 두고, 그 파일로 돌아온다."""
    ids = _seed(db)
    path = _db_path()
    keep = tmp_path / "before.json"
    before = {name: _read(path, row_id) for name, row_id in ids.items()}

    _run(path, "--apply", "--save-baseline", str(keep))
    assert _read(path, ids["마"]) != before["마"]           # 정말 바뀌었다

    _run(path, "--restore", str(keep), "--apply")
    for name, row_id in ids.items():
        assert _read(path, row_id) == before[name], name


def test_떠_둔_파일에는_바뀌는_줄만_전후로_들어간다(db, users, tmp_path):
    ids = _seed(db)
    keep = tmp_path / "before.json"
    _run(_db_path(), "--dry-run", "--save-baseline", str(keep))

    data = json.loads(keep.read_text(encoding="utf-8"))
    assert {item["id"] for item in data} == {
        ids["나"], ids["다"], ids["라"], ids["마"]}        # `가` 는 안 바뀐다
    moved = next(i for i in data if i["id"] == ids["마"])
    assert moved["before"]["memo"] == "8/20 통화"
    assert gn.MOVED_MARK in moved["after"]["memo"]


def test_바꾼_뒤_기준과_맞추면_합격이_나온다(db, users, tmp_path):
    """계획대로 바뀌었는지를 **줄마다** 맞춘다 — `check_month_backfill` 과 같은 결."""
    _seed(db)
    path = _db_path()
    keep = tmp_path / "before.json"

    _run(path, "--apply", "--save-baseline", str(keep))
    text = _run(path, "--baseline", str(keep))
    assert "어긋남 0줄" in text


def test_두_번_돌려도_메모가_두_번_적히지_않는다(db, users, tmp_path):
    """정리는 한 번만 도는 일이 아니다 — 운영에서는 미리보기·적용·확인을 오간다."""
    ids = _seed(db)
    path = _db_path()
    _run(path, "--apply", "--save-baseline", str(tmp_path / "a.json"))
    _run(path, "--apply", "--save-baseline", str(tmp_path / "b.json"))
    assert _read(path, ids["마"])[1].count(gn.MOVED_MARK) == 1


# ── ⑤ 그려진 화면 ───────────────────────────────────────────────────────────
#
# 칸 정의만 보고 끝내면 **머리글에 필터가 서는지, 칸을 눌렀을 때 A~F 가
# 뜨는지**는 아무도 안 본다. 배치와 화면이 갈리는 자리가 정확히 거기다
# (`data-choices` 가 담당자 칸에만 붙어 있었다).

DEAL = "샘플 딜공유 명단(9)"


@pytest.fixture()
def monthly_sheet(client, db, users):
    """`투자사 딜공유` 배치로 세운 명단. 이름·회사는 전부 지어낸 값이다."""
    from app.models import SheetOwner, VcContact
    from app.services import contact_columns as cc

    from .conftest import DEMO_PASSWORD

    u1 = users["u1"]
    db.add(SheetOwner(label=DEAL, user_id=u1.id, layout=cc.INVESTOR_MONTHLY,
                      is_hidden=0))
    db.add_all([
        VcContact(user_id=u1.id, source_sheet=DEAL, name="김샘플1",
                  firm="샘플투자1", group_name="A"),
        VcContact(user_id=u1.id, source_sheet=DEAL, name="김샘플2",
                  firm="샘플투자2", group_name="C"),
    ])
    db.commit()
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    return client


def _cells(html: str, field: str) -> list:
    return re.findall(r'<td[^>]*\bdata-field="' + field + r'"[^>]*>', html) \
        + re.findall(r'<div[^>]*\bdata-field="' + field + r'"[^>]*>', html)


def test_표_머리글이_그룹_이고_필터가_붙는다(monthly_sheet):
    from urllib.parse import quote

    html = monthly_sheet.get(f"/contacts?sheet={quote(DEAL)}").text
    head = re.search(r"<thead>(.*?)</thead>", html, re.S).group(1)
    found = re.search(r'<th[^>]*data-filters="group_name:([^"]*)"[^>]*>', head)
    assert found, f"그룹 머리글에 필터가 없습니다:\n{head}"
    assert found.group(1) == "그룹"
    assert "그룹/투자분야/라운드사이즈" not in html, "옛 이름이 화면에 남아 있습니다"


def test_표의_그룹_칸을_누르면_정해_둔_갈래가_뜬다(monthly_sheet):
    """수정창에는 `list=` 로 이미 붙어 있었다. 표만 빈 글자 칸이면 **어디서
    고치느냐에 따라** `A` 와 `a그룹` 으로 갈린다 — 방금 정리한 그것이다."""
    from urllib.parse import quote

    html = monthly_sheet.get(f"/contacts?sheet={quote(DEAL)}").text
    cells = _cells(html, "group_name")
    assert cells, "표에 그룹 칸이 없습니다"
    for cell in cells:
        assert 'data-type="pick"' in cell, cell
        # **`M&A` 는 화면에서 `M&amp;A` 로 적힌다** — 브라우저가 읽을 때 다시
        # `M&A` 가 되므로 값은 같다. 검사도 같은 자로 읽는다.
        m = re.search(r'data-choices="([^"]*)"', cell)
        assert m, cell
        assert unescape(m.group(1)) == gn.CHOICES, cell


def test_수정창의_그룹_칸에도_같은_갈래가_붙는다(monthly_sheet):
    from urllib.parse import quote

    html = monthly_sheet.get(f"/contacts?sheet={quote(DEAL)}").text
    assert 'id="f-group_name" ' in html or 'id="f-group_name"\n' in html
    picks = re.search(r'<datalist id="opts-panel-group_name">(.*?)</datalist>',
                      html, re.S)
    assert picks, "수정창에 그룹 보기 목록이 없습니다"
    # 한 글자 여섯 **과 이름들**이 함께 뜬다 — 사용자가 둘 다 쓴다.
    assert [unescape(v) for v in re.findall(r'value="([^"]*)"', picks.group(1))] \
        == list(gn.KNOWN)
