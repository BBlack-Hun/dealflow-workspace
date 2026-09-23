"""시트와 **다른 칸** — 보여 주기 · 골라서 덮기 · 한 판에 로그 한 줄.

고객사가 말했다 — *"제가 드리는 내용이 왜 그대로 엑셀이 반영이 안 되나."*
사실이었다. 넣는 길 둘이 **빈 칸만 채우는데** 그 사실이 어디에도 안 떴다.

이 검사가 지키는 것은 다섯이다.

1. **기본이 안 바뀐다.** 아무 것도 고르지 않고 돌리면 지금까지처럼 빈 칸만
   채운다. 기본을 덮기로 바꾸면 이 스크립트를 쓰던 다른 일이 조용히 망가진다
   — 그래서 이 검사가 맨 앞에 있다.
2. **다른 칸이 보인다.** 몇 칸이 · 어느 줄의 어느 칸이 · 지금 값과 시트 값이
   나란히.
3. **덮는 길이 있고, 아무 칸에나 닿지는 않는다.** 메모·이름·투자사명·카톡방
   이름은 어느 말로도 안 덮인다.
4. **되돌릴 수 있다.** `--save-baseline` 없이는 덮지 못하고, `--restore` 가
   그 파일로 원상 복구한다.
5. **한 판이 로그 한 줄로 남는다.** 줄마다 남기면 1,360줄이 되어 아무도 안
   본다(`services/edit_log` 머리글).

이름·회사·번호는 전부 지어낸 값이다 — 저장소가 공개다.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from .test_import_investor_list import (LIST, book, card_row, deal_row,
                                        fill_book, owners, rows_in, run,  # noqa: F401
                                        run_book, standing)  # noqa: F401


# ═══════════════════════════════════════════════════════════════════════════
# 0. 갈래 — 어느 칸이 덮일 수 있나 (판정은 한 곳이다)
# ═══════════════════════════════════════════════════════════════════════════

def test_모르는_칸은_안_덮는_쪽이_기본이다():
    """허용 목록이다. 막을 칸을 적는 방식이면 칸이 하나 늘 때 조용히 덮인다."""
    from app.services import import_diff as svc

    assert svc.group_of("note:c7") == svc.MONTHS
    assert svc.group_of("phone") == svc.CARD
    assert svc.group_of("note:etc") == svc.CARD
    for held in ("memo", "name", "firm", "kakao_room_name", "connect_stage",
                 "user_id", "source_sheet", "아직없는칸"):
        assert svc.group_of(held) == svc.HELD, f"{held} 이 덮을 수 있는 칸입니다"


def test_사람이_쥐는_칸은_골라도_안_덮인다():
    """미리보기에 뜨는 말을 그대로 베끼는 자리라, 섞여 들어와도 막혀야 한다."""
    from app.services import import_diff as svc

    memo = svc.Diff(row_id=7, key="memo", label="메모", before="가", after="나")
    month = svc.Diff(row_id=7, key="note:c3", label="8월", before="가", after="나")

    assert svc.parse_picks("7:memo").wants(memo) is False
    assert svc.parse_picks("all").wants(memo) is False
    assert svc.parse_picks("all").wants(month) is True
    assert svc.parse_picks("months").wants(month) is True
    assert svc.parse_picks("7:note:c3").wants(month) is True
    assert svc.parse_picks("").wants(month) is False, "빈 말이 덮었습니다"


def test_다름은_양쪽에_값이_있을_때만이다():
    """빈 칸은 다름이 아니라 **채울 자리**이고, 시트의 빈 칸은 `모름` 이다."""
    from app.services import import_diff as svc

    out = svc.compare(1,
                      {"a": "앱값", "b": "", "c": "같다", "d": "앱값"},
                      {"a": "시트값", "b": "시트값", "c": "같다", "d": ""})
    assert [d.key for d in out] == ["a"]
    assert (out[0].before, out[0].after) == ("앱값", "시트값")
    assert out[0].token == "1:a"


def test_값을_보여_줄지는_수정_로그와_같은_자로_가른다():
    """같은 물음에 두 곳이 다른 답을 하면, 로그에서 막은 값이 여기로 샌다.

    `as_rows` 의 값은 HTTP 응답으로 나가 브라우저에 남는다 — 한 겹 더 조심할
    자리이지 다른 자를 쓸 자리가 아니다.
    """
    from app.services import edit_log, import_diff as svc

    rows = {x["key"]: x for x in svc.as_rows([
        svc.Diff(row_id=3, key="memo", label="메모", before="가나다",
                 after="라마바사"),
        svc.Diff(row_id=3, key="phone", label="연락처", before="010-0000-0000",
                 after="010-0000-0001"),
        svc.Diff(row_id=3, key="kakao_room_name", label="카톡방 이름",
                 before="가상 방", after="다른 방"),
    ])}
    assert "before" not in rows["memo"] and rows["memo"]["before_len"] == 3
    assert rows["phone"]["before"] == "010-0000-0000", "덮을 칸을 못 보면 못 고른다"
    # 오발송에 가장 가까운 칸이라 로그도 값을 남긴다 — 여기서도 보여야 한다.
    assert "kakao_room_name" in edit_log.VALUE_FIELDS
    assert rows["kakao_room_name"]["before"] == "가상 방"
    assert svc.shows_value("아직없는칸") is False, "모르는 칸의 값이 샜습니다"


# ═══════════════════════════════════════════════════════════════════════════
# 1. 기본이 안 바뀐다 — **이 파일에서 가장 중요한 검사**
# ═══════════════════════════════════════════════════════════════════════════

def test_아무_말도_안_주면_지금까지처럼_빈_칸만_채운다(
        monkeypatch, db, owners, standing, capsys):
    """기본을 덮기로 바꾸면 이 스크립트를 쓰던 다른 일이 조용히 망가진다."""
    kept = [c for c in rows_in(db, LIST) if c.name == "김샘플"][0]
    kept.title = "손으로 고친 직함"
    kept.memo = "손으로 적은 메모"
    db.commit()

    assert fill_book(monkeypatch, standing, LIST, owners["a"], "--apply") == 0
    db.expire_all()
    after = [c for c in rows_in(db, LIST) if c.name == "김샘플"][0]
    assert after.title == "손으로 고친 직함", "기본값이 덮었습니다"
    assert after.memo == "손으로 적은 메모", "기본값이 메모를 덮었습니다"
    assert after.phone == "010-7000-0001", "빈 칸을 안 채웠습니다"
    assert "덮은 칸 0개" in capsys.readouterr().out


def test_만들기의_기본_동작도_그대로다(monkeypatch, db, owners, sample_book):
    """만들기는 예전부터 시트 값으로 덮는다 — 그 규칙을 건드리지 않았다."""
    run_book(monkeypatch, sample_book, LIST, owners["a"], "--apply")
    row = [c for c in rows_in(db, LIST) if c.name == "김샘플"][0]
    row.title = "손으로 고친 직함"
    db.commit()

    run_book(monkeypatch, sample_book, LIST, owners["a"], "--apply")
    db.expire_all()
    assert [c for c in rows_in(db, LIST) if c.name == "김샘플"][0].title == "이사"


@pytest.fixture()
def sample_book(tmp_path):
    return book(tmp_path,
                cards=[card_row("김샘플", "010-7000-0001", "샘플투자")],
                deals=[deal_row("김샘플", "샘플투자", "8/5 샘플가")],
                name="sample.xlsx")


# ═══════════════════════════════════════════════════════════════════════════
# 2. 다른 칸이 보인다
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture()
def diverged(monkeypatch, db, owners, standing, tmp_path):
    """**시트가 고쳐져 온 판.** 이미 선 명단의 달 칸·직함·메모와 다 다르다.

    고객이 실제로 한 일이 이것이다 — 값을 고쳐 다시 보냈는데 화면이 그대로였다.
    """
    path = book(tmp_path,
                cards=[card_row("김샘플", "010-7000-0001", "샘플투자")],
                deals=[deal_row("김샘플", "샘플투자", "8/5 샘플가/샘플나/샘플다",
                                memo="시트가 적은 기타")],
                name="fixed.xlsx")
    row = [c for c in rows_in(db, LIST) if c.name == "김샘플"][0]
    row.title = "손으로 고친 직함"
    row.memo = "손으로 적은 메모"
    db.commit()
    return path


def test_미리보기가_다른_칸을_줄과_칸까지_보여_준다(
        monkeypatch, db, owners, diverged, capsys):
    """**지금 값과 시트 값이 나란히** 보여야 사람이 판단할 수 있다."""
    fill_book(monkeypatch, diverged, LIST, owners["a"])
    out = capsys.readouterr().out

    row = [c for c in rows_in(db, LIST) if c.name == "김샘플"][0]
    assert "시트와 다른 칸" in out and "안 덮습니다" in out
    assert re.search(rf"{row.id}:note:c\d+", out), "어느 줄의 어느 칸인지 없습니다"
    assert "8/5 샘플가/샘플나/샘플다" in out, "시트 값이 안 보입니다"
    assert "8/5 샘플가/샘플나" in out, "지금 값이 안 보입니다"
    assert "--overwrite months" in out, "덮는 길을 안 알려 줍니다"


def test_메모는_다르다고만_하고_값을_안_찍는다(monkeypatch, db, owners, diverged,
                                              capsys):
    """이 칸에는 사람 이야기가 섞여 있다 — 길이만 보이면 화면에서 열어 본다."""
    fill_book(monkeypatch, diverged, LIST, owners["a"])
    out = capsys.readouterr().out
    assert "손으로 적은 메모" not in out
    assert "안 덮습니다" in out


def test_만들기_미리보기는_무엇이_덮이는지_보여_준다(
        monkeypatch, db, owners, sample_book, capsys):
    """만들기는 덮는 것이 맞지만, **무엇이 덮이는지 모르고** 덮는 것은 아니다.

    만들기가 조용히 덮던 자리가 실제로 있었다 — 운영에서 그룹 칸을 손으로
    정리해 둔 121줄이 같은 시트를 한 번 더 넣으면 옛 문장으로 되돌아간다.
    """
    run_book(monkeypatch, sample_book, LIST, owners["a"], "--apply")
    row = [c for c in rows_in(db, LIST) if c.name == "김샘플"][0]
    row.title = "손으로 고친 직함"
    db.commit()

    run_book(monkeypatch, sample_book, LIST, owners["a"])
    out = capsys.readouterr().out
    assert "덮습니다" in out and "시트와 다른 칸" in out
    assert f"{row.id}:title" in out, "어느 줄의 어느 칸인지 없습니다"


# ═══════════════════════════════════════════════════════════════════════════
# 3. 덮는 길 — 전부 · 고른 것만
# ═══════════════════════════════════════════════════════════════════════════

def test_월별_칸만_덮으면_명함과_메모는_그대로다(
        monkeypatch, db, owners, diverged, tmp_path, capsys):
    from app.services import contact_columns as cc

    base = tmp_path / "base.json"
    assert fill_book(monkeypatch, diverged, LIST, owners["a"],
                     "--overwrite", "months",
                     "--save-baseline", str(base), "--apply") == 0
    db.expire_all()
    row = [c for c in rows_in(db, LIST) if c.name == "김샘플"][0]
    values = cc.load_notes(row.notes)
    assert "8/5 샘플가/샘플나/샘플다" in values.values(), "월별 칸을 안 덮었습니다"
    assert row.title == "손으로 고친 직함", "월별만 덮으랬는데 직함이 덮였습니다"
    assert row.memo == "손으로 적은 메모", "메모가 덮였습니다"
    assert "덮은 칸 1개" in capsys.readouterr().out


def test_고른_칸만_덮는다(monkeypatch, db, owners, diverged, tmp_path, capsys):
    """미리보기가 찍어 준 말을 그대로 베껴 넘긴다."""
    fill_book(monkeypatch, diverged, LIST, owners["a"])
    token = re.search(r"(\d+:note:c\d+)", capsys.readouterr().out).group(1)

    base = tmp_path / "base.json"
    assert fill_book(monkeypatch, diverged, LIST, owners["a"],
                     "--overwrite", token,
                     "--save-baseline", str(base), "--apply") == 0
    assert json.loads(base.read_text(encoding="utf-8"))[0]["key"] == \
        token.split(":", 1)[1]


def test_되돌릴_파일_없이는_못_덮는다(monkeypatch, db, owners, diverged, capsys):
    """되돌릴 파일 없이 덮으면 되돌릴 길이 없다 — `clean_group_name` 과 같다."""
    assert fill_book(monkeypatch, diverged, LIST, owners["a"],
                     "--overwrite", "all", "--apply") == 2
    db.expire_all()
    assert [c for c in rows_in(db, LIST) if c.name == "김샘플"][0].title == \
        "손으로 고친 직함"


def test_만들기에서는_덮으라는_말을_안_받는다(monkeypatch, db, owners, diverged):
    """만들기는 이미 시트 값으로 덮는다 — 또 덮으라면 무엇이 무엇을 덮었는지
    아무도 모른다."""
    assert run(monkeypatch, diverged, LIST, owners["a"], "--mode", "create",
               "--tab", "딜공유탭", "--overwrite", "months") == 2


def test_고를_칸이_많으면_파일로_준다(monkeypatch, db, owners, diverged,
                                       tmp_path, capsys):
    """칸이 백을 넘으면 명령줄에 늘어놓을 수가 없다 — 목록을 파일에 모아 둔다."""
    fill_book(monkeypatch, diverged, LIST, owners["a"])
    token = re.search(r"(\d+:note:c\d+)", capsys.readouterr().out).group(1)
    picks = tmp_path / "picks.txt"
    picks.write_text(token + "\n", encoding="utf-8")

    base = tmp_path / "base.json"
    assert fill_book(monkeypatch, diverged, LIST, owners["a"],
                     "--overwrite", "@" + str(picks),
                     "--save-baseline", str(base), "--apply") == 0
    assert "덮은 칸 1개" in capsys.readouterr().out


def test_모르는_말은_멈춘다(monkeypatch, db, owners, diverged):
    assert fill_book(monkeypatch, diverged, LIST, owners["a"],
                     "--overwrite", "몽땅") == 2


# ═══════════════════════════════════════════════════════════════════════════
# 4. 되돌리기
# ═══════════════════════════════════════════════════════════════════════════

def test_덮은_것을_그대로_되돌린다(monkeypatch, db, owners, diverged, tmp_path):
    from app.services import contact_columns as cc

    row = [c for c in rows_in(db, LIST) if c.name == "김샘플"][0]
    before = dict(cc.load_notes(row.notes))

    base = tmp_path / "base.json"
    fill_book(monkeypatch, diverged, LIST, owners["a"], "--overwrite", "all",
              "--save-baseline", str(base), "--apply")
    db.expire_all()
    # **덮은 칸만** 본다. 같은 판이 빈 칸도 채우는데(그것이 기본 동작이다)
    # 되돌리기는 덮은 것만 되돌린다 — 채운 것까지 되돌리면 이 명령이 "판
    # 전체를 없던 일로" 만드는 다른 도구가 된다.
    keys = {item["key"][5:] for item in json.loads(base.read_text(encoding="utf-8"))
            if item["key"].startswith("note:")}
    assert keys, "월별 칸을 안 덮었습니다"
    after = cc.load_notes(
        [c for c in rows_in(db, LIST) if c.name == "김샘플"][0].notes)
    assert any(after[k] != before[k] for k in keys)

    assert run(monkeypatch, str(diverged), LIST, owners["a"], "--mode", "fill",
               "--restore", str(base), "--apply") == 0
    db.expire_all()
    back = cc.load_notes(
        [c for c in rows_in(db, LIST) if c.name == "김샘플"][0].notes)
    assert all(back[k] == before[k] for k in keys), "되돌아가지 않았습니다"


def test_되돌리기도_apply_를_요구한다(monkeypatch, db, owners, diverged, tmp_path):
    base = tmp_path / "base.json"
    base.write_text("[]", encoding="utf-8")
    assert run(monkeypatch, str(diverged), LIST, owners["a"], "--mode", "fill",
               "--restore", str(base)) == 2


# ═══════════════════════════════════════════════════════════════════════════
# 5. 한 판에 수정 로그 한 줄
# ═══════════════════════════════════════════════════════════════════════════

def _import_logs(db):
    from app.models import EditLog

    db.expire_all()
    return [x for x in db.query(EditLog).order_by(EditLog.id).all()
            if x.action == "import"]


def test_스크립트_한_판이_로그_한_줄로_남는다(monkeypatch, db, owners, diverged,
                                             tmp_path):
    """**줄마다 남기면 1,360줄이 되어 아무도 안 본다.**"""
    was = len(_import_logs(db))     # `standing` 이 이미 한 판을 넣어 두었다
    base = tmp_path / "base.json"
    fill_book(monkeypatch, diverged, LIST, owners["a"], "--overwrite", "months",
              "--save-baseline", str(base), "--apply")

    logs = _import_logs(db)
    assert len(logs) == was + 1, f"한 판에 {len(logs) - was}줄이 남았습니다"
    log = logs[-1]
    assert log.row_label == LIST and log.table_name == "sheet_owners"
    fields = {c["field"]: c.get("after")
              for c in json.loads(log.changes_json)}
    assert "fixed.xlsx" in fields["import_source"], "어느 시트인지 없습니다"
    assert "fill" in fields["import_mode"]
    assert fields["import_overwritten"] == 1
    assert fields["import_rows"] >= 1


def test_미리보기는_로그를_안_남긴다(monkeypatch, db, owners, diverged):
    """DB 에 닿지 않은 일을 로그가 일어난 일로 적으면 안 된다."""
    was = len(_import_logs(db))
    fill_book(monkeypatch, diverged, LIST, owners["a"])
    assert len(_import_logs(db)) == was, "미리보기가 로그를 남겼습니다"


def test_로그_화면이_한_판을_그린다(portal_admin, db, owners, monkeypatch,
                                    diverged, tmp_path):
    """`/team/edit-log` 에 보여야 앱 안에서 되짚을 수 있다."""
    base = tmp_path / "base.json"
    fill_book(monkeypatch, diverged, LIST, owners["a"], "--overwrite", "months",
              "--save-baseline", str(base), "--apply")

    body = portal_admin.get("/team/edit-log").text
    assert "시트 한 판" in body and LIST in body
    assert "덮어씀" in body


@pytest.fixture()
def portal_admin(db, users):
    from fastapi.testclient import TestClient

    from app.main import create_app
    from app.models import User
    from app.services import auth as auth_svc

    from .conftest import DEMO_PASSWORD

    db.add(User(id=91, name="관리자시험", phone="01090000001", role="admin",
                password_hash=auth_svc.hash_password(DEMO_PASSWORD)))
    db.commit()
    client = TestClient(create_app())
    r = client.post("/login", data={"phone": "01090000001",
                                    "password": DEMO_PASSWORD},
                    follow_redirects=False)
    assert r.status_code == 303
    return client


# ═══════════════════════════════════════════════════════════════════════════
# 6. 화면 업로드 — 보여만 주고, 덮지 않고, 한 줄 남긴다
# ═══════════════════════════════════════════════════════════════════════════

UPLOAD_HEAD = ["담당자", "이름", "투자사명", "직책", "연락처", "메모",
               "8월 1차 딜소개"]


def _upload_rows(title: str, memo: str, deal: str) -> list:
    return [["", "", "", "", "", "", ""],
            UPLOAD_HEAD,
            ["", "박샘플 대표님", "샘플캐피탈", title, "010-7000-0003", memo, deal]]


def _apply(db, rows, user_id, label="업로드시험", dry_run=False):
    from datetime import date

    from app.services import sheet_import as si

    parsed = si.parse_sheet_a(rows, date.today().year)
    return si.apply_sheet_a(db, parsed, user_id=user_id, dry_run=dry_run,
                            source_label=label)


def test_업로드는_다른_칸을_세지만_덮지는_않는다(db, users):
    """이 길은 팀원 누구나 파일 하나로 도는 길이라 덮는 단추를 달지 않았다."""
    _apply(db, _upload_rows("이사", "처음 메모", "8/5 샘플가"), users["u1"].id)

    report = _apply(db, _upload_rows("상무", "고친 메모", "8/5 샘플가"),
                    users["u1"].id)
    keys = {d.key for d in report.diffs}
    assert "title" in keys and "memo" in keys, f"다름을 못 셌습니다: {keys}"

    from app.models import VcContact
    db.expire_all()
    row = db.query(VcContact).filter(VcContact.name == "박샘플").first()
    assert row.title == "이사", "화면 업로드가 값을 덮었습니다"
    assert "시트 값과 **다른 칸" in report.as_text("업로드")


def test_업로드_한_판도_로그_한_줄이다(db, users):
    _apply(db, _upload_rows("이사", "처음 메모", "8/5 샘플가"), users["u1"].id)
    logs = _import_logs(db)
    assert len(logs) == 1
    fields = {c["field"]: c.get("after") for c in json.loads(logs[0].changes_json)}
    assert fields["import_mode"] == "업로드"
    assert fields["import_created"] == 1


def test_업로드_미리보기는_로그를_안_남긴다(db, users):
    _apply(db, _upload_rows("이사", "처음 메모", "8/5 샘플가"), users["u1"].id,
           dry_run=True)
    assert _import_logs(db) == []


def test_시트에서_없어진_활동_줄은_세기만_한다(db, users):
    """**지우지 않는다.** 이 표에는 손으로 적은 줄과 발송이 만든 줄이 함께 산다."""
    from app.models import ContactActivity

    _apply(db, _upload_rows("이사", "메모", "8/5 샘플가"), users["u1"].id)
    before = db.query(ContactActivity).count()

    report = _apply(db, _upload_rows("이사", "메모", "8/12 샘플나"), users["u1"].id)
    db.expire_all()
    assert report.activities_stale == 1, "없어진 줄을 못 셌습니다"
    assert db.query(ContactActivity).count() == before + 1, "줄이 지워졌습니다"
    assert "지우지 않습니다" in report.as_text("업로드")


def test_다른_경로로_들어온_활동_줄은_아예_안_센다(db, users):
    """손으로 적은 줄은 이 시트가 만든 것이 아니라 견줄 상대가 아니다."""
    from app.models import ContactActivity, VcContact

    _apply(db, _upload_rows("이사", "메모", "8/5 샘플가"), users["u1"].id)
    row = db.query(VcContact).filter(VcContact.name == "박샘플").first()
    db.add(ContactActivity(contact_id=row.id, month="2026-08",
                           kind="deal_intro", content="손으로 적은 회차",
                           source="manual"))
    db.commit()

    report = _apply(db, _upload_rows("이사", "메모", "8/5 샘플가"), users["u1"].id)
    assert report.activities_stale == 0, "손으로 적은 줄을 없어진 것으로 셌습니다"
