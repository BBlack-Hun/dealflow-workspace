"""명단의 **표 배치만** 바꾸는 자리.

배치는 `SheetOwner.layout` 에 값으로 들어 있는데, 그 값을 정하는 자리가 임포터
뿐이었다 — 시트를 다시 올리지 않고는 "이 명단을 저 명단과 같은 모양으로 맞춰
달라" 를 할 수가 없었다.

여기서 막는 것은 셋이다.

  1. **미리보기가 먼저다** — 바꾸기 전에 달마다의 기록이 어디로 가는지 보인다
  2. **없는 명단은 만들지 않는다** — 오타로 생긴 설정은 아무 줄도 안 가리킨다
  3. **값은 안 건드린다** — 배치는 어디에 그릴지만 정한다

명단 이름은 전부 지어낸 값이다 — 저장소가 공개다.
"""
from __future__ import annotations

import pytest

LIST = "샘플 딜공유 명단(2)"
MONTHS = ["8월 딜소개", "7월 딜소개"]


def run(monkeypatch, *argv) -> int:
    import scripts.set_sheet_layout as tool

    monkeypatch.setattr("sys.argv", ["set_sheet_layout.py", *argv])
    return tool.main()


@pytest.fixture()
def sheet(db, users):
    """딜공유 배치로 서 있는 명단 + 달마다의 기록."""
    from app.models import ContactColumn, SheetOwner, VcContact
    from app.services import contact_columns as cc

    db.add(SheetOwner(label=LIST, user_id=users["u1"].id,
                      layout=cc.INVESTOR_MONTHLY, is_hidden=0))
    for pos, label in enumerate(MONTHS):
        db.add(ContactColumn(sheet=LIST, label=label, position=pos))
    db.flush()
    cols = {c.label: c for c in cc.month_columns(db, LIST)}
    for i in range(1, 3):
        db.add(VcContact(user_id=users["u1"].id, source_sheet=LIST,
                         name=f"김샘플{i}", firm=f"샘플투자{i}",
                         notes=cc.dump_notes(
                             {cc.note_key(cols[MONTHS[0]].id): f"8/5 샘플가{i}"})))
    db.commit()
    return LIST


def test_미리보기가_먼저다(monkeypatch, db, sheet, capsys):
    """`--apply` 없이는 한 명단도 안 바뀐다. 그리고 **달 칸이 어디로 가는지**가
    미리 보여야, 사라진 것이 아니라 자리를 옮긴 것임을 알 수 있다."""
    from app.models import SheetOwner
    from app.services import contact_columns as cc

    assert run(monkeypatch, "--sheet", sheet, "--layout", cc.INVESTOR) == 0
    out = capsys.readouterr().out
    db.expire_all()

    assert db.query(SheetOwner).filter(SheetOwner.label == sheet).one().layout \
        == cc.INVESTOR_MONTHLY, "미리보기인데 바뀌었습니다"
    assert "달 칸 2개" in out and "값이 든 칸 2개" in out
    assert "수정창" in out and "값은 지워지지 않습니다" in out
    assert "--apply" in out


def test_배치를_바꿔도_달마다의_기록은_그대로다(monkeypatch, db, sheet):
    """**배치는 어디에 그릴지만 정한다.** 값은 줄에, 칸은 따로 있다."""
    from app.models import ContactColumn, SheetOwner, VcContact
    from app.services import contact_columns as cc

    before = {c.id: c.notes for c in
              db.query(VcContact).filter(VcContact.source_sheet == sheet)}
    assert run(monkeypatch, "--sheet", sheet, "--layout", cc.INVESTOR,
               "--apply") == 0
    db.expire_all()

    assert db.query(SheetOwner).filter(SheetOwner.label == sheet).one().layout \
        == cc.INVESTOR
    assert db.query(ContactColumn).filter(ContactColumn.sheet == sheet).count() \
        == len(MONTHS), "칸이 지워졌습니다"
    assert {c.id: c.notes for c in
            db.query(VcContact).filter(VcContact.source_sheet == sheet)} == before


def test_없는_명단은_만들지_않고_멈춘다(monkeypatch, db, sheet, capsys):
    """오타 하나로 없던 명단이 생기면, 그 설정은 아무 줄도 가리키지 않은 채
    남고 정작 바꾸려던 명단은 그대로다."""
    from app.models import SheetOwner
    from app.services import contact_columns as cc

    assert run(monkeypatch, "--sheet", "없는 명단", "--layout", cc.INVESTOR,
               "--apply") == 1
    db.expire_all()
    assert db.query(SheetOwner).filter(SheetOwner.label == "없는 명단").count() == 0
    out = capsys.readouterr().out
    assert "없는 명단입니다" in out
    assert sheet in out, "지금 있는 명단을 안 보여 주면 무엇을 적어야 할지 모른다"


def test_명단_이름이_스크립트에_박혀_있지_않다():
    """저장소가 공개다. 그리고 이름이 박혀 있으면 다음 명단에서 또 박아야 한다."""
    import re
    from pathlib import Path

    src = (Path(__file__).resolve().parent.parent
           / "scripts" / "set_sheet_layout.py").read_text(encoding="utf-8")
    src = re.sub(r'"""(?:.|\n)*?"""', "", src)
    src = re.sub(r"^\s*#.*$", "", src, flags=re.M)

    assert not re.findall(r"\b01\d[-\s]?\d{3,4}[-\s]?\d{4}\b", src)
    for banned in (LIST, "딜공유현황", "심사역 리스트"):
        assert banned not in src, f"명단 이름 `{banned}` 이 코드에 박혀 있습니다"
