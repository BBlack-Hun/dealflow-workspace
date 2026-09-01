"""새 명단 만들기 — **같은 사람이 두 줄이 되지 않게.**

담당자가 새로 들어오면 그 사람의 시트를 명단(탭)으로 세워야 한다. 지금까지의
임포터는 **이미 있는 줄을 채우기만** 해서(`import_startup_sheet.py`) 새 명단을
못 만들었다. 만드는 길을 열면 곧바로 새 위험이 생긴다 — **채울 자리에 새로
만들어 같은 사람이 두 줄이 되는 것**이다.

두 줄이 되면 딜 소개가 두 번 나간다. 받는 쪽에서는 그게 우리 실수인지 알 수
없고, 나간 뒤에는 되돌릴 수가 없다. 그래서 여기서 막는 것은 다섯 가지다.

  1. 같은 파일을 두 번 넣어도 줄이 두 배가 되지 않는다  ← 가장 중요하다
  2. 이미 있는 번호는 새로 만들지 않고 **주인만 바뀐다**(이력이 그 줄에 있다)
  3. 번호가 없는 줄은 **기업명으로** 잇는다 — 그래도 두 번 넣으면 안 된다
  4. 시트 안에서 같은 번호가 둘이면 하나만 들어간다
  5. 명단·담당자는 **인자**다 — 코드에 박혀 있지 않다

이름·회사·번호는 전부 지어낸 값이다 — 저장소가 공개다.
"""
from __future__ import annotations

import csv
import re
from pathlib import Path

from datetime import date

import pytest

ROOT = Path(__file__).resolve().parent.parent

# 원본 시트가 그렇듯 이름에 괄호와 숫자가 붙는다. **코드가 이 이름을 알면 안 된다.**
LIST = "샘플 신규명단(7)"
OTHER = "샘플 다른명단(3)"
POOL = "샘플 투자사 풀"

# 시트 머리글. 앞 다섯 칸은 배치가 정한 고정 칸이고, 나머지는 **달마다 늘어나는
# 칸**으로 세워져야 한다. 번호 칸을 `No.` 로 적는 시트가 있어 그 모양으로 둔다.
HEAD = ["No.", "기업명", "성함", "연락처", "이메일",
        "8월 문자", "8월 TEL", "IR 자료 회신 여부",
        "메모 ( 통화내용 /  카톡내용  /  카톡답신내용)"]


def sheet_file(tmp_path: Path, rows, name="sheet.csv") -> str:
    """머리글 + 준 줄들로 시트 파일 하나."""
    path = tmp_path / name
    with path.open("w", encoding="utf-8", newline="") as fp:
        writer = csv.writer(fp)
        writer.writerow(HEAD)
        writer.writerows(rows)
    return str(path)


def row(no, firm, name, phone, memo="") -> list:
    return [no, firm, name, phone, f"{name}@example.com", "O", "X", "O", memo]


def rulings_file(tmp_path: Path, pairs) -> str:
    path = tmp_path / "rulings.csv"
    with path.open("w", encoding="utf-8", newline="") as fp:
        writer = csv.writer(fp)
        writer.writerow(["# 번호", "넣을 명단"])
        writer.writerows(pairs)
    return str(path)


def run(monkeypatch, path, sheet, owner, mode="create", *extra) -> int:
    """스크립트를 부르는 방식 그대로 부른다 — 인자까지가 이 도구의 규약이다."""
    import scripts.import_new_list as tool

    argv = ["import_new_list.py", path, "--sheet", sheet,
            "--owner", owner, "--mode", mode, *extra]
    monkeypatch.setattr("sys.argv", argv)
    return tool.main()


def rows_in(db, label: str) -> list:
    from app.models import VcContact
    from app.services import sheet_owner

    db.expire_all()
    return [c for c in db.query(VcContact).all()
            if label in sheet_owner.labels_of(c.source_sheet)]


@pytest.fixture()
def owners(db, users):
    """두 담당자의 계정 휴대폰번호. 스크립트는 이 번호로 담당을 찾는다."""
    return {"a": users["u1"].phone, "b": users["u2"].phone}


# ── 1. 두 번 넣어도 두 배가 되지 않는다 ─────────────────────────────────────

def test_같은_파일을_두_번_넣어도_줄이_두_배가_되지_않는다(
        tmp_path, db, owners, monkeypatch, capsys):
    """**이 파일에서 가장 중요한 검사다.**

    시트는 한 번에 다 맞는 일이 없다 — 빠진 줄을 채워 다시 올리고, 다음 달 칸이
    붙으면 또 올린다. 그때마다 줄이 두 배가 되면 딜 소개가 두 번 나가고, 이미
    나간 뒤에는 되돌릴 수 없다.

    두 번째 판은 **만들지 않고 채워야** 한다. 그래서 앱에서 고쳐 둔 값이
    시트의 빈 칸에 지워지지도 않는다.
    """
    path = sheet_file(tmp_path, [
        row("1", "샘플기업1", "김샘플", "010-7000-0001", "첫 통화 메모"),
        row("2", "샘플기업2", "이샘플", "010-7000-0002"),
        row("3", "샘플기업3", "박샘플", "010-7000-0003"),
    ])
    assert run(monkeypatch, path, LIST, owners["a"], "create", "--apply") == 0
    first = rows_in(db, LIST)
    assert len(first) == 3

    assert run(monkeypatch, path, LIST, owners["a"], "create", "--apply") == 0
    again = rows_in(db, LIST)
    assert len(again) == 3, (
        f"같은 파일을 두 번 넣었더니 {len(first)}줄이 {len(again)}줄이 됐습니다 "
        "— 같은 사람에게 딜 소개가 두 번 나갑니다")
    assert {c.id for c in first} == {c.id for c in again}, "줄이 새로 만들어졌습니다"

    # 세 번째 판을 미리 보면 **만들 줄이 0** 이어야 한다. 수가 0 이 아니면
    # 다음 `--apply` 에서 그만큼 두 줄이 된다.
    capsys.readouterr()
    out = _preview(monkeypatch, path, LIST, owners["a"], capsys)
    assert re.search(r"새로 만들 줄\s+0\b", out), out


def _preview(monkeypatch, path, sheet, owner, capsys, *extra) -> str:
    run(monkeypatch, path, sheet, owner, "create", *extra)
    return capsys.readouterr().out


def test_두_번째_판은_앱에서_고친_값을_지우지_않는다(
        tmp_path, db, owners, monkeypatch, capsys):
    """시트에서 비어 있는 칸이 앱의 값을 덮으면, 임포트 한 번에 통화 메모가 사라진다."""
    path = sheet_file(tmp_path, [row("1", "샘플기업1", "김샘플", "010-7000-0001")])
    run(monkeypatch, path, LIST, owners["a"], "create", "--apply")

    kept = rows_in(db, LIST)[0]
    kept.memo = "앱에서 적어 둔 통화 내용"
    db.commit()

    run(monkeypatch, path, LIST, owners["a"], "create", "--apply")
    db.expire_all()
    assert rows_in(db, LIST)[0].memo == "앱에서 적어 둔 통화 내용"


# ── 2. 이미 있는 번호는 주인만 바뀐다 ───────────────────────────────────────

def test_이미_있는_번호는_새로_만들지_않고_주인만_바뀐다(
        tmp_path, db, users, owners, monkeypatch, capsys):
    """그 줄에 **카톡방과 발송 이력**이 붙어 있다.

    새로 만들면 이력이 없는 빈 줄이 하나 더 생기고, 원래 줄은 옛 담당자에게
    남아 같은 사람에게 딜 소개가 두 번 나간다. 옮기는 것이지 베끼는 것이 아니다.
    """
    from app.models import SheetOwner, VcContact

    db.add(SheetOwner(label=OTHER, user_id=users["u1"].id))
    db.add(VcContact(user_id=users["u1"].id, source_sheet=OTHER,
                     name="최샘플", firm="샘플기업9", phone="010-7000-0009",
                     connect_stage="connected", channel_kakao=1,
                     kakao_room_name="샘플기업9 대표님 방", room_verified="verified"))
    db.commit()
    before = db.query(VcContact).count()

    path = sheet_file(tmp_path, [row("1", "샘플기업9(사명 변경)", "최샘플",
                                     "010-7000-0009")])
    run(monkeypatch, path, LIST, owners["b"], "create", "--apply")
    db.expire_all()

    assert db.query(VcContact).count() == before, "줄이 새로 만들어졌습니다"
    moved = rows_in(db, LIST)
    assert len(moved) == 1
    assert moved[0].user_id == users["u2"].id, "주인이 안 바뀌었습니다"
    assert moved[0].kakao_room_name == "샘플기업9 대표님 방", "카톡방 이력이 끊겼습니다"
    assert moved[0].room_verified == "verified"
    assert OTHER not in moved[0].source_sheet, (
        "옛 담당자의 명단에 그대로 남아 있습니다 — 딜 소개가 두 번 나갑니다")


def test_담당_없는_명단_라벨은_옮겨도_그대로_둔다(
        tmp_path, db, users, owners, monkeypatch):
    """투자사 풀은 **분류**지 담당이 아니다.

    거기서 빼면 "어디서 확보한 사람인가" 가 사라진다. 딜 소개가 두 번 나가는
    것은 **담당이 둘일 때**지 분류가 남아 있을 때가 아니다.
    """
    from app.models import SheetOwner, VcContact

    db.add(SheetOwner(label=POOL))          # 담당 없음 = 풀
    db.add(VcContact(user_id=users["u1"].id, source_sheet=POOL,
                     name="정샘플", firm="샘플기업8", phone="010-7000-0008"))
    db.commit()

    path = sheet_file(tmp_path, [row("1", "샘플기업8", "정샘플", "010-7000-0008")])
    run(monkeypatch, path, LIST, owners["b"], "create", "--apply")

    moved = rows_in(db, LIST)[0]
    assert POOL in moved.source_sheet, "풀에서까지 빼 버렸습니다"
    assert LIST in moved.source_sheet


# ── 3. 번호가 없는 줄 ───────────────────────────────────────────────────────
#
# 막는 것은 "번호가 없는 줄" 자체가 아니라 **겹침을 못 알아보는 것**이다. 이
# 배치의 시트는 기업이 주인공이라(`STARTUP_LAYOUT` 의 머리글이 `기업명`·`성함`)
# 기업명이 그 근거가 된다. 근거가 생겼으니 넣되, 근거를 잃는 자리는 그대로 막는다.

def test_번호가_없어도_기업명으로_들어간다(
        tmp_path, db, owners, monkeypatch, capsys):
    """시트가 번호를 안 적어 둔 줄이 있다(`전화` 칸에 `x` 만 적힌 줄).

    빼 버리면 그 기업이 통째로 사라진다 — 명단에도, 화면에도 없다. 넣되
    **무엇을 근거로 이었는지** 화면에 적어야 나중에 확인할 데가 있다.
    """
    path = sheet_file(tmp_path, [
        row("1", "샘플기업1", "김샘플", "010-7000-0001"),
        row("2", "번호없는샘플", "이샘플", "x"),
        row("3", "짧은번호샘플", "박샘플", "1234"),      # 내선번호 — 사람을 못 가른다
    ])
    run(monkeypatch, path, LIST, owners["a"], "create", "--apply")
    out = capsys.readouterr().out

    got = {c.firm for c in rows_in(db, LIST)}
    assert got == {"샘플기업1", "번호없는샘플", "짧은번호샘플"}, (
        f"번호 없는 줄이 빠졌습니다: {got}")
    assert "번호 없이 들어간 줄 2개" in out, out
    # **조용히 넣지 않는다.** 근거와 남는 위험 셋이 다 화면에 적혀야 한다.
    assert "기업명" in out, out
    for risk in ("앱의 다른 명단", "기업명이 바뀌어", "시트에** 번호를 채워"):
        assert risk in out, f"남는 위험을 안 적었습니다: {risk}\n{out}"


def test_번호_없이_들어간_줄도_두_번_넣으면_두_줄이_되지_않는다(
        tmp_path, db, owners, monkeypatch, capsys):
    """**이 변경의 핵심 위험이다.**

    번호가 없으면 다음 판에서 그 줄을 찾을 열쇠가 기업명뿐이다. 못 찾으면 또
    만들고, 그 순간 같은 기업이 두 줄이 된다. 시트마다 `(주)` 를 붙였다 뗐다
    하므로 **표기가 달라져도** 같은 줄로 걸려야 한다.
    """
    first = sheet_file(tmp_path, [
        row("1", "샘플기업1", "김샘플", "010-7000-0001"),
        row("2", "㈜번호없는샘플", "이샘플", "x"),
    ])
    assert run(monkeypatch, first, LIST, owners["a"], "create", "--apply") == 0
    before = {c.id for c in rows_in(db, LIST)}
    assert len(before) == 2

    # 다음 달 판에서는 법인 표기를 다르게 적었다. 같은 기업이다.
    second = sheet_file(tmp_path, [
        row("1", "샘플기업1", "김샘플", "010-7000-0001"),
        row("2", "(주) 번호없는샘플", "이샘플", "x"),
    ], "next.csv")
    assert run(monkeypatch, second, LIST, owners["a"], "create", "--apply") == 0
    again = rows_in(db, LIST)

    assert len(again) == 2, (
        f"번호 없는 줄을 두 번 넣었더니 {len(before)}줄이 {len(again)}줄이 "
        "됐습니다 — 같은 기업이 두 줄입니다")
    assert {c.id for c in again} == before, "줄이 새로 만들어졌습니다"

    # 세 번째 판을 미리 보면 **만들 줄이 0** 이어야 한다.
    capsys.readouterr()
    out = _preview(monkeypatch, second, LIST, owners["a"], capsys)
    assert re.search(r"새로 만들 줄\s+0\b", out), out


def test_번호는_앱에서_넣으면_다음_판이_번호로_잇는다(
        tmp_path, db, owners, monkeypatch, capsys):
    """번호 없이 들어간 줄에 **번호를 채우는 길**이 화면에 적힌 그대로여야 한다.

    이 대조는 기업명이 열쇠라, 시트에 번호를 채워 다시 넣으면 번호로는 그 줄을
    못 찾아 또 만든다. 막으려면 번호가 **있는** 줄도 기업명으로 한 번 더 찾아야
    하는데 그러면 지금 잘 도는 길의 동작이 바뀐다 — 그래서 코드로 막지 않고
    **길을 적는다.** 여기서 검사하는 것은 그 길이 실제로 통하는가다.
    """
    nophone = sheet_file(tmp_path, [row("1", "번호없는샘플", "김샘플", "x")])
    run(monkeypatch, nophone, LIST, owners["a"], "create", "--apply")
    out = capsys.readouterr().out
    assert "앱에서 그 줄을 열어" in out, f"번호를 채우는 길을 안 적었습니다:\n{out}"

    # 화면이 적은 대로 **앱에서** 번호를 넣는다.
    kept = rows_in(db, LIST)[0]
    kept.phone = "010-7000-0001"
    db.commit()

    # 다음 판에는 시트에도 번호가 적혀 있다. 그 줄로 이어져야 한다.
    phoned = sheet_file(tmp_path, [row("1", "번호없는샘플", "김샘플",
                                       "010-7000-0001")], "next.csv")
    run(monkeypatch, phoned, LIST, owners["a"], "create", "--apply")
    db.expire_all()

    got = rows_in(db, LIST)
    assert len(got) == 1, f"번호를 넣었는데 두 줄이 됐습니다: {len(got)}"
    assert got[0].id == kept.id, "줄이 새로 만들어졌습니다"


def test_시트_안에_같은_기업명이_둘이면_번호_없는_줄은_안_들어간다(
        tmp_path, db, owners, monkeypatch, capsys):
    """열쇠가 기업명뿐인데 그 이름이 둘이면 **어느 줄인지 가릴 길이 없다.**

    넣어 두면 다음 판이 못 알아보고 또 만든다. `by_phone` 이 겹친 번호를 아예
    빼는 것과 같은 이유다 — 하나를 골라 두면 반은 틀린다.
    """
    path = sheet_file(tmp_path, [
        row("1", "겹치는샘플", "김샘플", "x"),
        row("2", "겹치는샘플", "이샘플", "x"),
        row("3", "샘플기업3", "박샘플", "010-7000-0003"),
    ])
    run(monkeypatch, path, LIST, owners["a"], "create", "--apply")

    got = {c.firm for c in rows_in(db, LIST)}
    assert got == {"샘플기업3"}, f"가릴 수 없는 줄이 들어갔습니다: {got}"
    assert "같은 기업명이 여럿" in capsys.readouterr().out


def test_기업명이_빈_줄은_여전히_안_들어간다(
        tmp_path, db, owners, monkeypatch, capsys):
    """번호도 기업명도 없으면 **대조할 것이 아무것도 없다.**

    법인 표기만 적힌 칸도 마찬가지다 — 열쇠로 만들면 빈 글자가 된다.
    """
    path = sheet_file(tmp_path, [
        row("1", "㈜", "김샘플", "x"),
        row("2", "샘플기업2", "이샘플", "010-7000-0002"),
    ])
    run(monkeypatch, path, LIST, owners["a"], "create", "--apply")

    assert {c.firm for c in rows_in(db, LIST)} == {"샘플기업2"}
    assert "번호도 기업명도 없어" in capsys.readouterr().out


def test_기업명_대조는_이_명단_안까지만_한다(
        tmp_path, db, users, owners, monkeypatch):
    """앱 전체를 기업명으로 뒤지지 않는다.

    투자사 명단은 **사람이 주인공**이라 한 투자사에 심사역이 여럿이다. 앱 전체를
    이렇게 뒤지면 그 여럿이 한 줄로 뭉개지고, 남의 명단에서 사람이 빠진다.
    범위가 이 명단 하나면 틀려도 남의 명단에는 닿지 않는다.
    """
    from app.models import SheetOwner, VcContact

    db.add(SheetOwner(label=OTHER, user_id=users["u1"].id))
    db.add(VcContact(user_id=users["u1"].id, source_sheet=OTHER,
                     name="최샘플", firm="같은이름샘플", phone="010-7000-0009",
                     kakao_room_name="같은이름샘플 대표님 방"))
    db.commit()

    path = sheet_file(tmp_path, [row("1", "같은이름샘플", "이샘플", "x")])
    run(monkeypatch, path, LIST, owners["b"], "create", "--apply")
    db.expire_all()

    stayed = rows_in(db, OTHER)
    assert len(stayed) == 1, "남의 명단에서 줄을 가져왔습니다"
    assert stayed[0].kakao_room_name == "같은이름샘플 대표님 방"
    assert stayed[0].user_id == users["u1"].id, "남의 담당이 넘어갔습니다"
    assert [c.firm for c in rows_in(db, LIST)] == ["같은이름샘플"]


def test_이_명단에_같은_기업명이_두_줄이면_얹지_않는다(
        tmp_path, db, users, owners, monkeypatch, capsys):
    """앱 쪽에서 이미 갈라져 있으면 **어느 줄에 얹을지 알 수 없다.**

    하나를 골라 두면 반은 틀리고, 틀리면 남의 이력에 남의 값이 덮인다 —
    되돌릴 수 없는 쪽이다.
    """
    from app.models import SheetOwner, VcContact

    db.add(SheetOwner(label=LIST, user_id=users["u1"].id))
    db.add_all([
        VcContact(user_id=users["u1"].id, source_sheet=LIST,
                  name="김샘플", firm="갈라진샘플", memo="먼저 적어 둔 통화"),
        VcContact(user_id=users["u1"].id, source_sheet=LIST,
                  name="이샘플", firm="갈라진샘플"),
    ])
    db.commit()

    path = sheet_file(tmp_path, [row("1", "갈라진샘플", "박샘플", "x", "새 메모")])
    run(monkeypatch, path, LIST, owners["a"], "create", "--apply")
    db.expire_all()

    got = rows_in(db, LIST)
    assert len(got) == 2, f"가릴 수 없는데 줄을 만들었습니다: {len(got)}"
    assert {c.memo for c in got} == {"먼저 적어 둔 통화", None}, (
        "어느 줄인지 모르는 채로 값을 덮었습니다")
    assert "같은 기업명이 두 줄" in capsys.readouterr().out


def test_번호로_집은_줄을_번호_없는_줄이_다시_집지_않는다(
        tmp_path, db, users, owners, monkeypatch, capsys):
    """시트의 두 줄이 앱의 **한 줄**을 가리키면 겹쳐 얹힌다.

    시트에서 기업명을 새로 적은 줄과 옛 이름 줄이 같이 남아 있을 때 생긴다 —
    번호 있는 줄은 그 줄을 번호로 집고, 옛 이름 줄은 같은 줄을 기업명으로 집는다.
    둘 다 얹으면 나중 것이 앞 것을 덮은 것인지조차 알 수 없다.
    """
    from app.models import SheetOwner, VcContact

    db.add(SheetOwner(label=LIST, user_id=users["u1"].id))
    db.add(VcContact(user_id=users["u1"].id, source_sheet=LIST,
                     name="김샘플", firm="옛이름샘플", phone="010-7000-0001"))
    db.commit()

    # 1번 줄이 그 줄을 번호로 집으면서 이름을 바꾼다. 2번 줄은 옛 이름 그대로다.
    path = sheet_file(tmp_path, [
        row("1", "새이름샘플", "김샘플", "010-7000-0001"),
        row("2", "옛이름샘플", "김샘플", "x"),
    ])
    run(monkeypatch, path, LIST, owners["a"], "create", "--apply")
    db.expire_all()

    got = rows_in(db, LIST)
    assert len(got) == 1, f"겹쳐 얹거나 새로 만들었습니다: {len(got)}"
    assert got[0].firm == "새이름샘플", "번호로 집은 값이 아닙니다"
    assert "번호로 집었다" in capsys.readouterr().out


def test_기업명으로_잇는지는_명단_이름이_아니라_배치가_정한다():
    """**사람이 주인공인 명단에서 기업명으로 맞추면 안 된다.**

    한 투자사에 심사역이 여럿이라, 투자사명으로 맞추면 그 여럿이 한 줄로
    뭉개진다. 그래서 임포터는 명단 이름이 아니라 **배치**에 묻는다 — 이름으로
    가르면 다음 명단에서 또 적어야 하고, 안 적은 곳만 조용히 옛 동작을 한다
    (`SheetOwner.layout` 주석).

    판정은 머리글 순서에서 읽는다. 어느 쪽이 앞에 서느냐가 곧 누가 주인공인가다.
    """
    from app.services import contact_columns as cc

    from scripts.import_new_list import LAYOUT

    assert cc.firm_leads(cc.STARTUP), "기업명이 앞에 서는 배치인데 아니라고 합니다"
    assert not cc.firm_leads(cc.INVESTOR_MONTHLY), (
        "사람이 주인공인 명단을 기업명으로 잇습니다 — 심사역 여럿이 한 줄로 뭉개집니다")
    # 머리글을 화면에 적어 둔 배치는 여기서 읽을 것이 없다. **모를 때는 안 잇는다.**
    assert not cc.firm_leads(cc.INVESTOR)
    assert not cc.firm_leads(None) and not cc.firm_leads("없는배치")

    # 임포터가 세우는 배치가 곧 그 근거다 — 두 자리가 갈리면 안 된다.
    assert cc.firm_leads(LAYOUT)


def test_채우기_모드는_번호_없는_줄도_만들지_않는다(
        tmp_path, db, owners, monkeypatch, capsys):
    """기업명으로 **잇는** 것과 **만드는** 것은 다르다.

    채우기는 이미 서 있는 명단에 값을 얹는 일이다. 없는 줄을 기업명만 보고
    만들기 시작하면 채우기가 만들기의 조용한 판이 된다.
    """
    path = sheet_file(tmp_path, [row("1", "번호없는샘플", "김샘플", "x")])
    run(monkeypatch, path, LIST, owners["a"], "fill", "--apply")

    assert rows_in(db, LIST) == []
    assert "앱에 없는 사람" in capsys.readouterr().out


# ── 4. 시트 안에서 같은 번호가 둘 ───────────────────────────────────────────

def test_시트_안에서_같은_번호가_둘이면_하나만_들어간다(
        tmp_path, db, owners, monkeypatch, capsys):
    """사람이 쓰는 문서라 같은 줄이 두 번 적힌다. 표기가 달라도 같은 사람이다."""
    path = sheet_file(tmp_path, [
        row("1", "샘플기업1", "김샘플", "010-7000-0001"),
        row("2", "샘플기업1(중복)", "김샘플", "01070000001"),   # 하이픈만 다르다
    ])
    run(monkeypatch, path, LIST, owners["a"], "create", "--apply")

    got = rows_in(db, LIST)
    assert len(got) == 1, f"같은 번호가 {len(got)}줄 들어갔습니다"
    assert "시트 안에서 같은 번호가 두 번" in capsys.readouterr().out


# ── 5. 명단·담당자는 인자다 ─────────────────────────────────────────────────

def test_명단과_담당자를_인자로_받는다(tmp_path, db, users, owners, monkeypatch):
    """같은 파일을 다른 명단·다른 담당으로 넣을 수 있어야 한다.

    코드에 박아 두면 다음 명단에서 또 박아야 하고, 박는 것을 잊은 곳만 조용히
    옛 동작을 한다.
    """
    a = sheet_file(tmp_path, [row("1", "샘플기업1", "김샘플", "010-7000-0001")],
                   "a.csv")
    b = sheet_file(tmp_path, [row("1", "샘플기업2", "이샘플", "010-7000-0002")],
                   "b.csv")
    run(monkeypatch, a, LIST, owners["a"], "create", "--apply")
    run(monkeypatch, b, OTHER, owners["b"], "create", "--apply")

    assert [c.user_id for c in rows_in(db, LIST)] == [users["u1"].id]
    assert [c.user_id for c in rows_in(db, OTHER)] == [users["u2"].id]


def test_명단_이름과_연락처가_스크립트에_박혀_있지_않다():
    """실제 명단 이름이나 사람 번호가 소스에 남으면 안 된다.

    저장소가 공개다. 그리고 이름이 박혀 있으면 다음 명단에서 또 박아야 한다.
    주석은 본다 — 주석에 예로 적는 것은 동작이 아니다.
    """
    src = (ROOT / "scripts" / "import_new_list.py").read_text(encoding="utf-8")
    src = re.sub(r'"""(?:.|\n)*?"""', "", src)
    src = re.sub(r"^\s*#.*$", "", src, flags=re.M)

    phones = re.findall(r"\b01\d[-\s]?\d{3,4}[-\s]?\d{4}\b", src)
    assert not phones, f"연락처가 코드에 박혀 있습니다: {phones}"
    for banned in (LIST, OTHER, "스타트업"):
        assert banned not in src, f"명단 이름 `{banned}` 이 코드에 박혀 있습니다"


# ── 만들기와 채우기를 부르는 사람이 고른다 ──────────────────────────────────

def test_모드를_고르지_않으면_아무것도_하지_않는다(tmp_path, db, owners, monkeypatch):
    """기본값을 두지 않는다.

    위험한 쪽(만들기)이 기본값이면 채울 자리에 두 줄이 생기고, 안전한 쪽이
    기본값이면 "왜 아무것도 안 들어갔지" 를 매번 겪는다. **둘 다 적게 한다.**
    """
    import scripts.import_new_list as tool

    path = sheet_file(tmp_path, [row("1", "샘플기업1", "김샘플", "010-7000-0001")])
    monkeypatch.setattr("sys.argv", ["import_new_list.py", path,
                                     "--sheet", LIST, "--owner", owners["a"],
                                     "--apply"])
    with pytest.raises(SystemExit):
        tool.main()
    assert rows_in(db, LIST) == []


def test_채우기_모드는_없는_사람을_만들지_않는다(
        tmp_path, db, owners, monkeypatch, capsys):
    """`import_startup_sheet.py` 가 지켜 온 규칙이다 — 못 맞춘 줄은 **적어서 알린다.**"""
    path = sheet_file(tmp_path, [row("1", "샘플기업1", "김샘플", "010-7000-0001")])
    run(monkeypatch, path, LIST, owners["a"], "fill", "--apply")

    assert rows_in(db, LIST) == []
    assert "앱에 없는 사람" in capsys.readouterr().out


def test_미리보기가_먼저다(tmp_path, db, owners, monkeypatch, capsys):
    """`--apply` 없이는 한 줄도 안 들어간다. 넣기 전에 무엇이 들어갈지 읽는다."""
    path = sheet_file(tmp_path, [row("1", "샘플기업1", "김샘플", "010-7000-0001")])
    run(monkeypatch, path, LIST, owners["a"], "create")

    assert rows_in(db, LIST) == []
    out = capsys.readouterr().out
    assert "새로 만들 줄" in out and "--apply" in out


# ── 배정표 ──────────────────────────────────────────────────────────────────

def test_다른_명단으로_배정된_사람은_안_들어간다(
        tmp_path, db, owners, monkeypatch, capsys):
    """겹치는 사람을 양쪽에 넣으면 **두 계정에 들어가 딜 소개가 두 번 나간다.**

    누가 맡을지는 사람이 정하는 일이라 파일로 받는다 — 코드에 적으면 다음
    배정에서 또 코드를 고쳐야 하고, 공개 저장소에 실명과 번호가 남는다.
    """
    path = sheet_file(tmp_path, [
        row("1", "샘플기업1", "김샘플", "010-7000-0001"),
        row("2", "샘플기업2", "이샘플", "010-7000-0002"),
    ])
    rules = rulings_file(tmp_path, [["010-7000-0002", OTHER]])
    run(monkeypatch, path, LIST, owners["a"], "create", "--apply",
        "--rulings", rules)

    assert {c.firm for c in rows_in(db, LIST)} == {"샘플기업1"}
    assert "다른 명단으로 배정됨" in capsys.readouterr().out


def test_배정표가_이_명단으로_정하면_시트에_없어도_주인이_바뀐다(
        tmp_path, db, users, owners, monkeypatch):
    """넘겨받는 사람의 시트에는 그 줄이 **아직 없는 것이 보통이다.**

    시트는 자료일 뿐이고 배정을 정한 것은 사람이라, 시트에 안 적혔다고 배정이
    없던 일이 되면 안 된다. 이때도 새로 만들지 않고 옮긴다 — 그 줄에 이력이 있다.
    """
    from app.models import SheetOwner, VcContact

    db.add(SheetOwner(label=OTHER, user_id=users["u1"].id))
    db.add(VcContact(user_id=users["u1"].id, source_sheet=OTHER,
                     name="한샘플", firm="샘플기업7", phone="010-7000-0007",
                     connect_stage="connected", kakao_room_name="샘플기업7 대표님 방"))
    db.commit()
    before = db.query(VcContact).count()

    path = sheet_file(tmp_path, [row("1", "샘플기업1", "김샘플", "010-7000-0001")])
    rules = rulings_file(tmp_path, [["010-7000-0007", LIST]])
    run(monkeypatch, path, LIST, owners["b"], "create", "--apply",
        "--rulings", rules)
    db.expire_all()

    assert db.query(VcContact).count() == before + 1, "옮길 줄을 새로 만들었습니다"
    moved = {c.firm: c for c in rows_in(db, LIST)}
    assert set(moved) == {"샘플기업1", "샘플기업7"}
    assert moved["샘플기업7"].kakao_room_name == "샘플기업7 대표님 방"
    assert moved["샘플기업7"].user_id == users["u2"].id


# ── 명단 설정 ───────────────────────────────────────────────────────────────

def test_새_명단은_스타트업_배치로_서고_투자사로_세지_않는다(
        tmp_path, db, owners, monkeypatch):
    """스타트업은 투자사가 아니다.

    투자사로 세면 투자사 수가 부풀고, 딜소개 발송 대상과 소싱 방 잇기에도 함께
    떠서 **스타트업 대표의 방으로 "이 딜 어떠세요" 가 나간다.**
    """
    from app.models import SheetOwner
    from app.services import contact_columns as cc

    path = sheet_file(tmp_path, [row("1", "샘플기업1", "김샘플", "010-7000-0001")])
    run(monkeypatch, path, LIST, owners["a"], "create", "--apply")
    db.expire_all()

    settings = db.query(SheetOwner).filter(SheetOwner.label == LIST).one()
    assert settings.layout == cc.STARTUP
    assert settings.is_hidden == 1


def test_숨김을_풀어_둔_명단을_다시_올려도_되돌아가지_않는다(
        tmp_path, db, owners, monkeypatch):
    """화면에서 사람이 정한 값을 임포트 한 번이 되돌리면 안 된다."""
    from app.models import SheetOwner

    path = sheet_file(tmp_path, [row("1", "샘플기업1", "김샘플", "010-7000-0001")])
    run(monkeypatch, path, LIST, owners["a"], "create", "--apply")
    db.expire_all()
    db.query(SheetOwner).filter(SheetOwner.label == LIST).one().is_hidden = 0
    db.commit()

    run(monkeypatch, path, LIST, owners["a"], "create", "--apply")
    db.expire_all()
    assert db.query(SheetOwner).filter(SheetOwner.label == LIST).one().is_hidden == 0


def test_남는_머리글은_달마다_늘어나는_칸으로_선다(
        tmp_path, db, owners, monkeypatch):
    """고정 칸으로 알아본 것 말고 **남는 머리글 전부**가 칸이 된다.

    목록을 손으로 적어 두면 9월 시트를 올렸을 때 그 칸이 조용히 버려진다.
    번호 칸(`No.`)은 칸이 아니다 — 칸으로 세면 표 맨 앞에 번호 열이 하나 더 생긴다.
    """
    from app.services import contact_columns as cc

    path = sheet_file(tmp_path, [row("1", "샘플기업1", "김샘플", "010-7000-0001")])
    run(monkeypatch, path, LIST, owners["a"], "create", "--apply")
    db.expire_all()

    labels = [c.label for c in cc.month_columns(db, LIST, today=date(2026, 8, 15))]
    assert labels == ["8월 문자", "8월 TEL"], labels

    # 다시 올려도 칸이 두 벌이 되지 않는다.
    run(monkeypatch, path, LIST, owners["a"], "create", "--apply")
    db.expire_all()
    assert [c.label for c in cc.month_columns(db, LIST, today=date(2026, 8, 15))] == labels


# 담당자 워크북의 머리글. 위 `HEAD` 와 두 가지가 다르다 — 원본 명단 번호가 한 칸
# 더 있고, **우리 팀 안에서 넘긴 이력**(`담당자`)이 기업 정보 사이에 끼어 있다.
WORKBOOK_HEAD = ["No", "원본NO", "기업명", "사업분야 대분류", "소분류", "담당자",
                 "카톡방 연결여부", "리마인드 카톡(월1회-수or목or금)", "전화", "비고"]


def test_원본번호와_담당_이력은_달마다_늘어나는_칸이_아니다(
        tmp_path, db, owners, monkeypatch):
    """남는 머리글이 전부 달 칸이 되는 규칙에 **두 칸은 걸리면 안 된다.**

    걸리면 두 가지가 한꺼번에 나빠진다.

      · 이 배치의 달 칸은 `O`/`X` 고르기다(`STARTUP_LAYOUT.month_kind`).
        `7/21 김담당 -> 8/19 이담당` 이 거기 서면 **한 번 고치는 순간 넘긴
        이력이 한 글자로 덮인다.** 되돌릴 데가 없다 — 시트에만 있던 글이다.
      · 시트에서 이 둘이 그 달의 기록보다 **앞에** 적혀 있다. `VISIBLE_MONTHS`
        가 1이라 맨 앞 칸만 펴지므로, 정작 카톡 연결 기록이 접히고 표에는
        원본 번호가 선다.

    그리고 `담당자` 는 **스타트업 쪽 담당자가 아니다.** `성함` 으로 보내면 기업의
    연락 상대 자리에 우리 팀원 이름이 앉는다.
    """
    from app.services import contact_columns as cc

    path = tmp_path / "workbook.csv"
    with path.open("w", encoding="utf-8", newline="") as fp:
        writer = csv.writer(fp)
        writer.writerow(WORKBOOK_HEAD)
        writer.writerow(["1", "150", "샘플기업1", "커머스", "D2C",
                         "7/21 김담당 -> 8/19 이담당", "7/24 o", "",
                         "010-7000-0001", "전화가 와서 카톡으로 안내"])
    run(monkeypatch, str(path), LIST, owners["a"], "create",
        "--map", "전화=phone", "--map", "비고=memo", "--apply")
    db.expire_all()

    months = cc.month_columns(db, LIST, today=date(2026, 8, 15))
    labels = [c.label for c in months]
    assert labels == ["카톡방 연결여부", "리마인드 카톡(월1회-수or목or금)"], (
        f"원본NO·담당자를 달마다 늘어나는 칸으로 세웠습니다: {labels}")

    kept = rows_in(db, LIST)[0]
    notes = cc.load_notes(kept.notes)
    assert notes.get("origin_no") == "150"
    assert notes.get("owner_history") == "7/21 김담당 -> 8/19 이담당"
    assert not kept.name, f"담당 이력이 성함으로 갔습니다: {kept.name!r}"
    # 그 달의 기록은 달 칸 그대로 남는다 — 옮긴 것은 위의 두 칸뿐이다.
    assert notes.get(cc.note_key(months[0].id)) == "7/24 o"
    assert kept.phone == "010-7000-0001"
    assert kept.memo == "전화가 와서 카톡으로 안내"

    # 표에 서는 것은 **그 달의 기록**이어야 한다.
    visible, _folded = cc.split_months(months)
    assert [c.label for c in visible] == ["카톡방 연결여부"]


# ── 시트를 읽는 규칙은 두 임포터가 나눠 쓴다 ────────────────────────────────

def test_번호_칸을_어떻게_적어도_알아본다():
    """`NO` · `no` · `No.` 가 다 돌아다닌다.

    글자 그대로 맞추면 마침표 하나 때문에 번호 칸을 못 알아보고, 그 칸이
    **달마다 늘어나는 칸**으로 잘못 서서 표 맨 앞에 번호 열이 하나 더 생긴다.
    """
    from scripts.import_startup_sheet import parse

    for spelling in ("NO", "no", "No.", " No "):
        rows = [[spelling, "기업명", "성함", "연락처", "8월 문자"],
                ["1", "샘플기업1", "김샘플", "010-7000-0001", "O"]]
        got = parse(rows)
        assert got["items"], f"`{spelling}` 머리글을 못 읽었습니다"
        assert got["columns"] == ["8월 문자"], (
            f"`{spelling}` 을 달마다 늘어나는 칸으로 잘못 세웠습니다: {got['columns']}")


def test_표의_줄을_보는_눈은_임포터마다_다르다():
    """채우기 임포터의 판정은 **바뀌지 않았다.**

    저쪽은 표 아래에 운영 가이드가 줄글로 붙은 시트를 읽어야 해서 `> 0` 인 줄만
    표로 본다. 이쪽은 `0` 을 '다른 담당자에게 넘김' 표시로 쓰는 시트를 읽어야
    해서 `0` 도 줄로 센다. 한쪽 규칙을 다른 쪽에 밀어 넣으면 둘 중 하나가 깨진다.
    """
    from scripts.import_new_list import is_table_row
    from scripts.import_startup_sheet import has_row_no, parse

    rows = [["No.", "기업명", "성함", "연락처"],
            ["0", "넘긴기업", "김샘플", "010-7000-0001"],
            ["1", "샘플기업1", "이샘플", "010-7000-0002"],
            ["표 아래 안내", "연락은 이렇게 하세요", "", ""]]

    assert not has_row_no("0") and is_table_row("0")
    assert not has_row_no("표 아래 안내") and not is_table_row("표 아래 안내")

    assert [i["fields"]["firm"] for i in parse(rows)["items"]] == ["샘플기업1"]
    assert [i["fields"]["firm"] for i in parse(rows, is_row=is_table_row)["items"]] \
        == ["넘긴기업", "샘플기업1"]


def test_담당자_계정이_없으면_만들지_않고_멈춘다(tmp_path, db, users, monkeypatch,
                                    capsys):
    """번호를 한 자 잘못 적었을 때 **유령 계정**이 생기고 거기에 사람들이 붙는다.

    계정 만들기는 `scripts/add_user.py` 의 일이다.
    """
    from app.models import User

    path = sheet_file(tmp_path, [row("1", "샘플기업1", "김샘플", "010-7000-0001")])
    assert run(monkeypatch, path, LIST, "010-9999-0000", "create", "--apply") == 1

    assert db.query(User).count() == len(users)
    assert rows_in(db, LIST) == []
    assert "add_user.py" in capsys.readouterr().out
