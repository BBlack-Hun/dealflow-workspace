"""시트의 `기타`·`대화내역 메모` 를 투자사 줄의 메모 칸으로 옮기기.

**가장 중요한 두 가지**를 여기서 못 박는다.

  1. **덮지 않는다 · 두 번 돌려도 안 늘어난다.** 이 스크립트는 사람이 앱에서
     적어 둔 글 위에 얹힌다. 덮으면 그 글이 사라지고, 멱등하지 않으면 시트가
     다시 올라올 때마다 같은 말이 한 벌씩 더 쌓인다.
  2. **애매하면 안 건드린다.** 시트 한 줄이 앱의 여러 줄에 맞거나 아무 줄에도
     안 맞으면 세기만 한다. 틀리게 붙이면 남의 선호가 엉뚱한 투자사에 들어가고,
     그 말을 다음 주 딜 고르기(`llm_brief`)가 그대로 믿는다.

시트에는 실명·투자사명이 들어 있어 **저장소에 넣지 않는다.** 여기 쓰는 워크북은
지어낸 값으로 코드가 만든다 — 원본과 **같은 모양**(머리글이 2행 · 6~27열이
달마다의 이력 · 맨 끝이 대화내역 메모)으로.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

TAB = "심사역 리스트(공통양식)"

# 원본과 같은 모양. 1행은 달 묶음(세 칸 병합이라 맨 왼쪽에만 값이 온다),
# 2행이 진짜 머리글, 값은 3행부터.
MONTH_ROW = ["", "", "", "", "", "9월", "", "", "8월", "", ""]
HEAD = ["", "그룹/투자분야/라운드사이즈", "이름", "투자사명", "기타",
        "딜소개", "IR 요청 (투자사 5 / IR 3)", "미팅 진행 여부",
        "딜소개", "IR 요청 (투자사 2 / IR 1)", "대화내역 메모"]

# 6~27열 자리. **여기 적힌 것이 결과에 나오면 안 된다** — 앱이 이미
# `ContactActivity` 로 갖고 있는 이력이다.
MONTHLY = ["9/2 샘플가, 샘플나", "9/5 샘플다 전달", "9/9 미팅 확정",
           "8/5 샘플라", "8/7 샘플마 전달"]


def sheet_row(name, firm, etc="", talk="") -> list:
    return ["A", "Seed / 20억", name, firm, etc, *MONTHLY, talk]


def book(tmp_path: Path, rows, name="pref.xlsx") -> Path:
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = TAB
    ws.append(MONTH_ROW)
    ws.append(HEAD)
    for row in rows:
        ws.append(row)
    path = tmp_path / name
    wb.save(path)
    wb.close()
    return path


def db_path() -> str:
    url = os.environ["DATABASE_URL"]
    return url[len("sqlite:///"):]


def contact(db, user_id, name, firm, **fields):
    from app.models import VcContact

    row = VcContact(user_id=user_id, name=name, firm=firm, **fields)
    db.add(row)
    db.commit()
    return row


def run(monkeypatch, xlsx, *extra) -> int:
    """스크립트를 부르는 방식 그대로 부른다 — 인자까지가 이 도구의 규약이다."""
    import scripts.import_pref_notes as tool

    monkeypatch.setattr("sys.argv", ["import_pref_notes.py",
                                     "--xlsx", str(xlsx), "--db", db_path(),
                                     *extra])
    return tool.main()


def apply(monkeypatch, xlsx, tmp_path, name="base.json", *extra) -> Path:
    """`--apply` 는 되돌리기 파일 없이는 안 돈다. 그래서 늘 함께 준다."""
    baseline = tmp_path / name
    assert run(monkeypatch, xlsx, "--apply",
               "--save-baseline", str(baseline), *extra) == 0
    return baseline


def refresh(db, row):
    db.expire_all()
    return db.get(type(row), row.id)


# ── 1. 정확히 한 줄에 맞는 줄만 붙는다 ──────────────────────────────────────

def test_두_칸이_각각_제_칸으로_간다(monkeypatch, db, users, tmp_path):
    """`기타` → `sourcing_note` · `대화내역 메모` → `memo`.

    **한 칸에 뭉치지 않는다.** 한쪽은 어떻게 이어져 있는가(딜소싱 경로)고 다른
    쪽은 무슨 말을 주고받았는가다. 합치면 되돌아볼 때 어느 글이 어느 시트 칸에서
    왔는지 가릴 수가 없다.
    """
    from app.services import pref_notes

    row = contact(db, users["u1"].id, "김샘플", "샘플투자")
    xlsx = book(tmp_path, [sheet_row("김샘플", "샘플투자",
                                     etc="8/11 딜소싱 네트워크 소개",
                                     talk="초기보다 성장단계를 보신다고 하심")])
    apply(monkeypatch, xlsx, tmp_path)

    got = refresh(db, row)
    assert got.sourcing_note == f"{pref_notes.MARK_ETC} 8/11 딜소싱 네트워크 소개"
    assert got.memo == f"{pref_notes.MARK_TALK} 초기보다 성장단계를 보신다고 하심"


def test_달마다의_이력은_안_가져온다(monkeypatch, db, users, tmp_path):
    """6~27열은 읽지 않는다 — 앱이 이미 `ContactActivity` 로 갖고 있다.

    가져오면 같은 이력이 메모에 한 벌 더 쌓이고, 그 메모를 `llm_brief` 가 읽어
    **이미 보낸 딜을 선호로 읽는다.**
    """
    row = contact(db, users["u1"].id, "김샘플", "샘플투자")
    xlsx = book(tmp_path, [sheet_row("김샘플", "샘플투자", etc="8/11 소개")])
    apply(monkeypatch, xlsx, tmp_path)

    got = refresh(db, row)
    blob = f"{got.sourcing_note or ''}\n{got.memo or ''}"
    for month in MONTHLY:
        assert month not in blob


# ── 2. 애매하면 안 건드린다 ────────────────────────────────────────────────

def test_여러_줄에_맞으면_한_줄도_안_건드린다(monkeypatch, db, users, tmp_path, capsys):
    """동명이인이 같은 투자사에 둘 있으면 **고르지 않는다.**

    여기서 하나를 고르면(id 가 작은 줄 · 먼저 만든 줄) 그 규칙이 코드 어디에도
    근거가 없는 채로 남의 선호를 옮겨 붙인다. 세어서 알리고 사람이 시트를 고친
    뒤 다시 돌리는 자리다.
    """
    a = contact(db, users["u1"].id, "김샘플", "샘플투자")
    b = contact(db, users["u1"].id, "김샘플", "샘플투자")
    xlsx = book(tmp_path, [sheet_row("김샘플", "샘플투자", etc="8/11 소개",
                                     talk="바이오만 보신다")])
    apply(monkeypatch, xlsx, tmp_path)

    for row in (a, b):
        got = refresh(db, row)
        assert got.sourcing_note is None
        assert got.memo is None
    assert "여러 줄에 맞음" in capsys.readouterr().out


def test_한_줄도_안_맞으면_건너뛴다(monkeypatch, db, users, tmp_path, capsys):
    """앱에 없는 사람이다. 줄을 **만들지 않는다** — 이 도구는 메모만 옮긴다."""
    from app.models import VcContact

    contact(db, users["u1"].id, "김샘플", "샘플투자")
    xlsx = book(tmp_path, [sheet_row("박샘플", "샘플캐피탈", etc="8/11 소개")])
    apply(monkeypatch, xlsx, tmp_path)

    db.expire_all()
    assert db.query(VcContact).count() == 1
    assert "한 줄도 안 맞음" in capsys.readouterr().out


def test_투자사명이_달라도_이름이_같으면_안_붙는다(monkeypatch, db, users, tmp_path):
    """열쇠는 **투자사명 + 이름**이다. 이름만으로 잇지 않는다.

    이 저장소는 같은 데서 이미 데였다 — 한 이름이 셋이라 남의 방으로 딜 소개가
    나갔다(`import_investor_list` 모듈 설명).
    """
    row = contact(db, users["u1"].id, "김샘플", "다른투자")
    xlsx = book(tmp_path, [sheet_row("김샘플", "샘플투자", etc="8/11 소개")])
    apply(monkeypatch, xlsx, tmp_path)

    assert refresh(db, row).sourcing_note is None


def test_법인_표기가_달라도_같은_투자사로_본다(monkeypatch, db, users, tmp_path):
    """`㈜샘플투자` 와 `샘플투자` 는 같은 곳이다 — 시트마다 넣고 빼는 법이 다르다."""
    row = contact(db, users["u1"].id, "김샘플", "㈜샘플투자")
    xlsx = book(tmp_path, [sheet_row("김샘플", "샘플투자", etc="8/11 소개")])
    apply(monkeypatch, xlsx, tmp_path)

    assert "8/11 소개" in refresh(db, row).sourcing_note


# ── 3. 덮지 않는다 · 두 번 돌려도 안 늘어난다 ──────────────────────────────

def test_이미_있는_글을_덮지_않고_뒤에_잇는다(monkeypatch, db, users, tmp_path):
    """앱에서 사람이 적어 둔 글이 **그대로 남아야** 한다."""
    written = "앱에서 적어 둔 글 — 지워지면 안 된다"
    row = contact(db, users["u1"].id, "김샘플", "샘플투자",
                  sourcing_note=written, memo=written)
    xlsx = book(tmp_path, [sheet_row("김샘플", "샘플투자", etc="8/11 소개",
                                     talk="바이오만 보신다")])
    apply(monkeypatch, xlsx, tmp_path)

    got = refresh(db, row)
    assert got.sourcing_note.startswith(written)
    assert got.sourcing_note.splitlines()[-1].endswith("8/11 소개")
    assert got.memo.startswith(written)
    assert got.memo.splitlines()[-1].endswith("바이오만 보신다")


def test_두_번_돌려도_안_늘어난다(monkeypatch, db, users, tmp_path):
    """**멱등.** 시트는 여러 번 올라오고 이 스크립트도 여러 번 돈다."""
    row = contact(db, users["u1"].id, "김샘플", "샘플투자", memo="먼저 적어 둔 글")
    xlsx = book(tmp_path, [sheet_row("김샘플", "샘플투자", etc="8/11 소개",
                                     talk="바이오만 보신다")])

    apply(monkeypatch, xlsx, tmp_path, "one.json")
    once = (refresh(db, row).sourcing_note, refresh(db, row).memo)
    apply(monkeypatch, xlsx, tmp_path, "two.json")
    assert (refresh(db, row).sourcing_note, refresh(db, row).memo) == once


def test_이미_같은_내용이_있으면_안_붙인다(monkeypatch, db, users, tmp_path, capsys):
    """표시 없이 **이미 그 말이 들어 있는** 줄. 다른 길로 먼저 들어온 값이다.

    (`import_investor_list` 는 `대화내역 메모` 를 `memo` 에 덮어쓴다 — 그
    스크립트가 먼저 돌았으면 여기 오는 값이 이미 그 칸에 있다.)
    """
    talk = "초기보다 성장단계를 보신다고 하심"
    row = contact(db, users["u1"].id, "김샘플", "샘플투자", memo=talk)
    xlsx = book(tmp_path, [sheet_row("김샘플", "샘플투자", talk=talk)])
    apply(monkeypatch, xlsx, tmp_path)

    assert refresh(db, row).memo == talk
    assert "이미 있음" in capsys.readouterr().out


# ── 4. 껍데기는 안 가져간다 ────────────────────────────────────────────────

@pytest.mark.parametrize("shell", ["-", ".", "없음", "해당없음", "N/A", "ㆍ", "   -  "])
def test_껍데기_값은_안_가져간다(monkeypatch, db, users, tmp_path, shell):
    """`-`·`.`·`없음` 은 **비워 두지 못해 적어 둔 글자**다. 옮기면 메모만 길어진다."""
    row = contact(db, users["u1"].id, "김샘플", "샘플투자")
    xlsx = book(tmp_path, [sheet_row("김샘플", "샘플투자", etc=shell, talk=shell)])
    apply(monkeypatch, xlsx, tmp_path)

    got = refresh(db, row)
    assert got.sourcing_note is None
    assert got.memo is None


def test_두_글자부터는_남긴다(monkeypatch, db, users, tmp_path):
    """실제 시트에 `거부` 처럼 두 자로 뜻이 서는 값이 있다 — 껍데기가 아니다."""
    row = contact(db, users["u1"].id, "김샘플", "샘플투자")
    xlsx = book(tmp_path, [sheet_row("김샘플", "샘플투자", etc="거부")])
    apply(monkeypatch, xlsx, tmp_path)

    assert refresh(db, row).sourcing_note.endswith("거부")


def test_빈_칸은_건너뛴다(monkeypatch, db, users, tmp_path):
    """빈 칸·공백만 있는 칸에는 표시만 남기지 않는다."""
    row = contact(db, users["u1"].id, "김샘플", "샘플투자")
    xlsx = book(tmp_path, [sheet_row("김샘플", "샘플투자", etc="", talk="   ")])
    apply(monkeypatch, xlsx, tmp_path)

    got = refresh(db, row)
    assert got.sourcing_note is None and got.memo is None


# ── 5. 미리보기가 기본 · 되돌릴 파일 없이는 안 쓴다 ────────────────────────

def test_기본은_미리보기라_DB_에_안_쓴다(monkeypatch, db, users, tmp_path):
    row = contact(db, users["u1"].id, "김샘플", "샘플투자")
    xlsx = book(tmp_path, [sheet_row("김샘플", "샘플투자", etc="8/11 소개")])

    assert run(monkeypatch, xlsx) == 0
    assert refresh(db, row).sourcing_note is None
    # `--dry-run` 을 적어도 같다. 적어 두고 돌린 명령이 "안 적었으니 저장됐나"
    # 로 읽히면 안 된다.
    assert run(monkeypatch, xlsx, "--dry-run") == 0
    assert refresh(db, row).sourcing_note is None


def test_되돌릴_파일_없이는_apply_를_거부한다(monkeypatch, db, users, tmp_path):
    row = contact(db, users["u1"].id, "김샘플", "샘플투자")
    xlsx = book(tmp_path, [sheet_row("김샘플", "샘플투자", etc="8/11 소개")])

    assert run(monkeypatch, xlsx, "--apply") == 2
    assert refresh(db, row).sourcing_note is None


def test_값은_기본으로_안_찍힌다(monkeypatch, db, users, tmp_path, capsys):
    """미리보기는 **id 와 길이**만 찍는다 — 실명·투자사명이 섞여 있다."""
    secret = "샘플바이오만 보신다고 하심"
    contact(db, users["u1"].id, "김샘플", "샘플투자")
    xlsx = book(tmp_path, [sheet_row("김샘플", "샘플투자", etc=secret)])

    run(monkeypatch, xlsx)
    assert secret not in capsys.readouterr().out
    run(monkeypatch, xlsx, "--show-values")
    assert secret in capsys.readouterr().out


# ── 6. 되돌리기 ────────────────────────────────────────────────────────────

def content_sha(path: str) -> str:
    """DB 안의 **내용**을 한 덩어리로 해싱한다.

    파일을 통째로 재면 값이 같아도 다른 해시가 나온다 — 줄이 커졌다 작아지면
    sqlite 가 쓰던 페이지를 비워 둔 채(free-list) 파일 길이를 안 줄인다.
    그래서 **되돌렸는지**를 재는 자를 둘로 나눈다: 이것은 값의 자,
    `file_sha()` 는 파일의 자다(둘 다 같아야 한다).
    """
    import sqlite3

    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        return hashlib.sha256(
            "\n".join(con.iterdump()).encode("utf-8")).hexdigest()
    finally:
        con.close()


# sqlite 파일 머리의 **살림 칸**. 값이 아니라 "몇 번 썼나 · 스키마가 몇 번째냐"
# 를 세는 자리라, 아무것도 안 바꾸는 쓰기 한 번에도 올라간다. 파일을 그대로
# 재면 값이 원래대로 돌아와도 이 세 자리 때문에 해시가 갈린다(실측으로 딱 이
# 3바이트만 달랐다). 가리고 잰다 — 가리는 것이 값이 아님을 여기 적어 둔다.
_BOOKKEEPING = ((24, 28),   # File change counter
                (40, 44),   # Schema cookie
                (92, 96))   # Version-valid-for number


def file_sha(path: str) -> str:
    """파일 그대로의 sha256 — **`VACUUM` 으로 자리를 다시 붙이고** 살림 칸은 가린다.

    `VACUUM` 이 필요한 이유: 줄이 커졌다 작아지면 sqlite 는 쓰던 페이지를 비워
    둔 채(free-list) 파일 길이를 안 줄인다. 값은 같은데 자리만 다른 상태다.
    """
    import sqlite3

    con = sqlite3.connect(path)
    try:
        con.isolation_level = None
        con.execute("VACUUM")
    finally:
        con.close()
    raw = bytearray(Path(path).read_bytes())
    for start, end in _BOOKKEEPING:
        raw[start:end] = bytes(end - start)
    return hashlib.sha256(bytes(raw)).hexdigest()


def test_되돌리면_값도_파일도_sha256_까지_원래대로(monkeypatch, db, users, tmp_path):
    """**한 글자도 안 달라져야 한다.** 이 도구는 남의 글 위에 얹히므로,
    되돌리기가 '거의' 되는 것으로는 아무도 `--apply` 를 누르지 못한다.

    값(`content_sha`)과 파일(`file_sha`) 둘 다 본다.
    """
    from app.db import engine

    from app.services import group_name

    for i in range(5):
        # 세 가지 처음 상태를 섞는다 — 빈 칸 · 사람이 적은 글 ·
        # **그룹 칸 정리가 옮겨 둔 글**(운영에서 이미 돌았다).
        memo = (None if i % 3 == 0 else "앱에서 적어 둔 글" if i % 3 == 1
                else f"{group_name.MOVED_MARK} Seed~Pre A 30억")
        contact(db, users["u1"].id, f"김샘플{i}", "샘플투자", memo=memo)
    xlsx = book(tmp_path, [sheet_row(f"김샘플{i}", "샘플투자",
                                     # 가리기까지 되돌리기 길에 태운다
                                     etc=f"8/1{i} 소개 · 강민준님 확인",
                                     talk=f"샘플{i} 분야를 보신다고 하심")
                           for i in range(5)])

    # 재기 전에 **열린 연결을 전부 닫는다** — 안 닫으면 WAL 에 남은 것이 본체에
    # 안 내려와 같은 상태인데도 다른 파일이 된다.
    db.commit()
    engine.dispose()
    path = db_path()
    before_content, before_file = content_sha(path), file_sha(path)

    baseline = apply(monkeypatch, xlsx, tmp_path)
    engine.dispose()
    assert content_sha(path) != before_content

    monkeypatch.setattr("sys.argv", ["import_pref_notes.py", "--db", path,
                                     "--restore", str(baseline), "--apply"])
    import scripts.import_pref_notes as tool
    assert tool.main() == 0
    engine.dispose()
    assert content_sha(path) == before_content
    assert file_sha(path) == before_file


def test_되돌리기도_apply_를_요구한다(monkeypatch, db, users, tmp_path):
    contact(db, users["u1"].id, "김샘플", "샘플투자")
    xlsx = book(tmp_path, [sheet_row("김샘플", "샘플투자", etc="8/11 소개")])
    baseline = apply(monkeypatch, xlsx, tmp_path)

    monkeypatch.setattr("sys.argv", ["import_pref_notes.py", "--db", db_path(),
                                     "--restore", str(baseline)])
    import scripts.import_pref_notes as tool
    assert tool.main() == 2


def test_기준_파일로_계획대로_바뀌었는지_맞춘다(monkeypatch, db, users, tmp_path):
    """`--baseline` 은 떠 둔 `after` 와 지금 DB 를 줄마다 맞춘다."""
    row = contact(db, users["u1"].id, "김샘플", "샘플투자")
    xlsx = book(tmp_path, [sheet_row("김샘플", "샘플투자", etc="8/11 소개")])
    baseline = apply(monkeypatch, xlsx, tmp_path)

    assert run(monkeypatch, xlsx, "--baseline", str(baseline)) == 0

    # 사람이 그 뒤에 그 칸을 고치면 **어긋남으로 잡힌다.**
    row = refresh(db, row)
    row.sourcing_note = "누가 다시 고친 글"
    db.commit()
    assert run(monkeypatch, xlsx, "--baseline", str(baseline)) == 1


def test_되돌리기_파일에는_전과_후가_다_들어_있다(monkeypatch, db, users, tmp_path):
    """`before` 가 있어야 되돌리고, `after` 가 있어야 맞춰 볼 수 있다."""
    from app.services import pref_notes

    contact(db, users["u1"].id, "김샘플", "샘플투자", memo="먼저 적어 둔 글")
    xlsx = book(tmp_path, [sheet_row("김샘플", "샘플투자", etc="8/11 소개",
                                     talk="바이오만 보신다")])
    baseline = apply(monkeypatch, xlsx, tmp_path)

    data = json.loads(baseline.read_text(encoding="utf-8"))
    assert len(data) == 1
    item = data[0]
    assert set(item["before"]) == set(pref_notes.FIELDS)
    assert item["before"]["memo"] == "먼저 적어 둔 글"
    assert item["after"]["memo"].startswith("먼저 적어 둔 글\n")


# ── 7. 판정 자체 ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("value,shell", [
    ("-", True), (".", True), ("..", True), ("없음", True), ("해당없음", True),
    ("N/A", True), ("ㆍ", True), ("  -  ", True), ("O", True), ("x", True),
    ("거부", False), ("휴직중이심", False), ("8/11 딜소싱 네트워크 소개", False),
])
def test_껍데기_판정(value, shell):
    from app.services import pref_notes

    assert pref_notes.is_shell(value) is shell


def test_빈_칸은_껍데기로_세지_않는다():
    """둘을 한 수로 뭉치면 **몇 줄을 걸렀는지** 셀 수가 없다."""
    from app.services import pref_notes

    assert pref_notes.is_empty("") and pref_notes.is_empty("   ")
    assert not pref_notes.is_shell("") and not pref_notes.is_shell("   ")


def test_표시_문구는_그룹_칸_정리와_같은_결이다():
    """`[그룹 칸에서 옮김]` 과 같은 자리·같은 모양. 어느 칸에서 왔는지가 다르다."""
    from app.services import group_name, pref_notes

    for mark in (pref_notes.MARK_ETC, pref_notes.MARK_TALK):
        assert mark.startswith("[") and mark.endswith("칸에서 옮김]")
    assert group_name.MOVED_MARK != pref_notes.MARK_ETC
    assert pref_notes.MARK_ETC != pref_notes.MARK_TALK


def test_옮기는_칸은_llm_brief_가_읽는_칸이다():
    """**이 검사가 이 기능의 이유다.** 옮겨 놓고 안 읽히면 한 일이 없다."""
    from app.services import llm_brief, pref_notes

    for field in pref_notes.FIELDS:
        assert field in llm_brief.INVESTOR_FIELDS


# ── 8. 우리 쪽 사람 이름을 가린다 ──────────────────────────────────────────
#
# **여섯째 꼴이다.** 옮기는 순간 생기는 문제라, 옮기는 검사 옆에 둔다.
#
# `llm_brief` 는 이것을 못 막는다 — 저쪽이 지우는 사람 이름은 그 줄 자신의
# 것뿐이다(`llm_brief._scrub`). 그리고 남의 이름까지 지우지 않기로 한 것은
# 거기 적힌 실측(세 글자 이름이 남의 문장 261곳에 우연히 맞았다) 때문이라,
# **여기서는 앞뒤를 보고 가린다.**

def owner(db, label, assignee):
    """명단 담당 팀원. 계정이 없어도 이름이 여기 남는다(`SheetOwner`)."""
    from app.models import SheetOwner

    row = SheetOwner(label=label, assignee_name=assignee)
    db.add(row)
    db.commit()
    return row


def test_세_자리에서_온_팀원_이름이_모두_가려진다(monkeypatch, db, users, tmp_path):
    """계정 · 명단 담당 · 담당자 칸 — `NAME_SOURCES` 셋이 다 쓰인다.

    한 자리만 보면 그 자리에 없는 팀원이 통째로 새어 나간다. 계정이 아직 없는
    팀원은 명단 담당에만 있고, 명단이 없는 팀원은 담당자 칸에만 있다.
    """
    from app.services import pref_notes

    owner(db, "샘플 명단", "박담당 팀장")          # sheet_owners.assignee_name
    contact(db, users["u2"].id, "정담당", "샘플파트너스",
            assignee_name="최담당")                # vc_contacts.assignee_name
    row = contact(db, users["u1"].id, "김샘플", "샘플투자")
    xlsx = book(tmp_path, [sheet_row(
        "김샘플", "샘플투자",
        # 강민준 = users 붙박이 계정 이름(`conftest.users`)
        etc="강민준님 카톡방 임시 관리\n이후 박담당님 연결\n최담당님 확인",
        talk="윤서아님께 전달 완료")])
    apply(monkeypatch, xlsx, tmp_path)

    got = refresh(db, row)
    for name in ("강민준", "박담당", "최담당", "윤서아"):
        assert name not in got.sourcing_note + got.memo
    # **지우지 않고 가린다** — 나머지 말은 살아 있어야 한다.
    assert pref_notes.TEAM_MASK in got.sourcing_note
    assert "카톡방 임시 관리" in got.sourcing_note
    assert "연결" in got.sourcing_note
    assert "전달 완료" in got.memo


@pytest.mark.parametrize("text,masked", [
    # 가린다 — 이름이 낱말을 열고, 뒤가 호칭이거나 한글이 아니다
    ("강민준님과 통화", True),
    ("강민준 / 9월 카톡방", True),
    ("이후 강민준 연결", True),
    ("민준부장 들어와 있음", True),          # 성을 뗀 이름 + 직함
    ("오후 5:15 민준 넵 확인했습니다", True),  # 대화 로그의 발화자 자리
    # **안 가린다 — 헛맞음이다**
    ("윤서아이디어 회의록 정리", False),      # 뒤가 한글이고 직함이 아니다
    ("계약서아카이브를 정리했다", False),      # 이름이 낱말 한가운데 박혔다
    ("강민준비물을 챙긴다", False),
    ("서아 담당으로 옮김", False),            # 성 뗀 이름인데 호칭이 안 붙었다
])
def test_헛맞음_앞뒤를_보고_가른다(db, users, text, masked):
    """**한글 이름은 두세 자라 보통 글자에 그냥 박힌다.**

    순진하게 부분문자열로 지우면 멀쩡한 문장이 뭉개진다 — `llm_brief` 가 실측
    261곳으로 재고 그만둔 그 방식이다. 여기서는 대는 이름이 팀원 몇 명뿐이라
    앞뒤를 볼 여유가 있다.
    """
    from app.services import pref_notes

    names = pref_notes.team_names(["강민준", "윤서아"])
    pattern = pref_notes.team_pattern(names)
    out, spots = pref_notes.mask_team(text, pattern)
    assert bool(spots) is masked
    assert (out != text) is masked


def test_발화자_자리는_시각을_남기고_이름만_가린다(db):
    """대화가 **언제** 오갔는지는 그 자체로 정보다 — `llm_brief._scrub` 도
    날짜는 안 지운다. 발화자만 바꾸고 시각은 그대로 둔다.
    """
    from app.services import pref_notes

    pattern = pref_notes.team_pattern(pref_notes.team_names(["강민준"]))
    out, spots = pref_notes.mask_team("오후 5:15 민준 넵 확인했습니다", pattern)
    assert spots == 1
    assert out == f"오후 5:15 {pref_notes.TEAM_MASK} 넵 확인했습니다"


def test_가리고_나니_남는_말이_없으면_안_옮긴다(monkeypatch, db, users, tmp_path,
                                              capsys):
    """이름 말고는 거의 없던 줄. 옮기면 메모에 표시만 쌓인다.

    **따로 센다** — `껍데기` 와 한 수로 뭉치면 가리기가 무엇을 지웠는지 안 보인다.
    """
    row = contact(db, users["u1"].id, "김샘플", "샘플투자")
    xlsx = book(tmp_path, [sheet_row("김샘플", "샘플투자", etc="강민준님")])
    apply(monkeypatch, xlsx, tmp_path)

    assert refresh(db, row).sourcing_note is None
    assert "가리니 빔" in capsys.readouterr().out


def test_앱이_모르는_이름은_못_가린다(monkeypatch, db, users, tmp_path, capsys):
    """**이 방법의 한계다.** 계정도 담당 표시도 없는 팀원은 못 거른다.

    사용자가 알고 고른 길이지만, 검사와 미리보기 둘 다에 적어 둔다 — 안 적으면
    "자동으로 다 걸러진다" 고 믿게 된다.
    """
    row = contact(db, users["u1"].id, "김샘플", "샘플투자")
    xlsx = book(tmp_path, [sheet_row("김샘플", "샘플투자",
                                     etc="없는분님 카톡방 임시 관리")])
    apply(monkeypatch, xlsx, tmp_path)

    assert "없는분" in refresh(db, row).sourcing_note
    out = capsys.readouterr().out
    assert "앱이 아는 이름만 가린다" in out and "못 거른다" in out


def test_이름_목록은_직함을_버리고_쪼갠다():
    """`담당자` 칸은 자유 글자다 — `김샘플 팀장` · `샘플가/샘플나`."""
    from app.services import pref_notes

    got = pref_notes.team_names(
        ["김샘플 팀장", "샘플가/샘플나", "팀장", "", None, "김샘플", "A", "너무긴이름입니다"])
    assert got == ("김샘플", "샘플가", "샘플나")


def test_미리보기와_저장이_같은_글을_쓴다(monkeypatch, db, users, tmp_path, capsys):
    """가리는 일은 `decide()` 안에서 **한 번만** 일어난다.

    미리보기가 따로 다시 가리면 본 것과 들어가는 것이 갈리고, 그러면 사람이
    확인할 자리가 없어진다.
    """
    row = contact(db, users["u1"].id, "김샘플", "샘플투자")
    xlsx = book(tmp_path, [sheet_row("김샘플", "샘플투자",
                                     etc="강민준님 카톡방 임시 관리")])
    assert run(monkeypatch, xlsx, "--show-values") == 0
    shown = capsys.readouterr().out
    apply(monkeypatch, xlsx, tmp_path)

    written = refresh(db, row).sourcing_note
    assert "[팀원]님 카톡방 임시 관리" in written
    # 미리보기가 **가리기 전/후를 나란히** 놓는다 — 확인할 유일한 길이다.
    assert "가리기 전" in shown and "가린  뒤" in shown
    assert "강민준님 카톡방 임시 관리" in shown       # 전
    assert "[팀원]님 카톡방 임시 관리" in shown       # 후


def test_가리기_전_글이_이미_있으면_가린_판을_또_안_붙인다(
        monkeypatch, db, users, tmp_path, capsys):
    """다른 임포터가 먼저 **덮어쓴** 판이 있는 경우.

    가린 판을 한 벌 더 붙이면 같은 말이 두 번 서고, 먼저 들어온 판에는 이름이
    그대로 남아 있어 가린 뜻도 안 산다. **덮지는 않되 몇 줄인지는 알린다.**
    """
    raw = "강민준님 카톡방 임시 관리"
    row = contact(db, users["u1"].id, "김샘플", "샘플투자", sourcing_note=raw)
    xlsx = book(tmp_path, [sheet_row("김샘플", "샘플투자", etc=raw)])
    apply(monkeypatch, xlsx, tmp_path)

    assert refresh(db, row).sourcing_note == raw
    assert "이미 그 칸에 들어 있는" in capsys.readouterr().out


def test_가린_뒤에도_두_번_돌리면_안_늘어난다(monkeypatch, db, users, tmp_path):
    """**멱등.** 가리기가 끼어도 두 번째 실행이 한 벌을 더 붙이면 안 된다."""
    row = contact(db, users["u1"].id, "김샘플", "샘플투자")
    xlsx = book(tmp_path, [sheet_row("김샘플", "샘플투자",
                                     etc="강민준님 카톡방 임시 관리",
                                     talk="오후 5:15 민준 확인했습니다")])
    apply(monkeypatch, xlsx, tmp_path, "one.json")
    once = (refresh(db, row).sourcing_note, refresh(db, row).memo)
    apply(monkeypatch, xlsx, tmp_path, "two.json")
    assert (refresh(db, row).sourcing_note, refresh(db, row).memo) == once


# ── 9. 그룹 칸 정리가 남긴 글과 같은 칸에 선다 ─────────────────────────────

def test_그룹_칸_정리가_memo_에_옮겨_둔_글과_부딪히지_않는다(
        monkeypatch, db, users, tmp_path):
    """**운영에서 이미 돌아간 정리다.** `clean_group_name` 이 그룹 칸의 문장을
    `[그룹 칸에서 옮김]` 표시와 함께 `memo` 뒤로 옮겨 두었다.

    그 뒤에 이 스크립트가 같은 칸에 붙는다 — 표시 두 종류가 한 칸에 선다.
    앞의 글이 **한 글자도 안 변해야** 하고, 순서도 지켜져야 한다.
    """
    from app.services import group_name, pref_notes

    moved = f"{group_name.MOVED_MARK} Seed~Pre A 30억 규모 위주"
    row = contact(db, users["u1"].id, "김샘플", "샘플투자", memo=moved)
    xlsx = book(tmp_path, [sheet_row("김샘플", "샘플투자",
                                     talk="바이오만 보신다고 하심")])
    apply(monkeypatch, xlsx, tmp_path)

    got = refresh(db, row).memo
    lines = got.splitlines()
    assert lines[0] == moved                       # 앞의 글은 그대로
    assert lines[-1].startswith(pref_notes.MARK_TALK)
    assert group_name.MOVED_MARK in got and pref_notes.MARK_TALK in got


def test_그룹_칸_정리가_옮긴_말과_같은_말이면_한_번만_선다(
        monkeypatch, db, users, tmp_path):
    """두 도구가 **같은 말**을 옮기는 경우. 겹침 판정을 같은 자로 하므로
    (`group_name.squash`) 뒤에 오는 쪽이 알아보고 안 붙인다.
    """
    from app.services import group_name

    same = "초기보다 성장단계 위주로 검토"
    row = contact(db, users["u1"].id, "김샘플", "샘플투자",
                  memo=f"{group_name.MOVED_MARK} {same}")
    xlsx = book(tmp_path, [sheet_row("김샘플", "샘플투자", talk=same)])
    apply(monkeypatch, xlsx, tmp_path)

    assert refresh(db, row).memo.count(same) == 1


def test_그룹_칸_정리가_이_스크립트가_붙인_글을_되밟지_않는다(db, users):
    """반대 방향도 본다 — 이 스크립트가 먼저 붙은 `memo` 에 `clean_group_name`
    이 나중에 도는 경우. 저쪽도 **이미 있는 말은 안 붙인다.**
    """
    from app.services import group_name, pref_notes

    memo = f"{pref_notes.MARK_TALK} 바이오만 보신다고 하심"
    first = group_name.decide("바이오만 보신다고 하심", memo=memo)
    assert first.memo is None or first.moved == ""
