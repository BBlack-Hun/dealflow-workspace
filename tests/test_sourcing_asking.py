"""딜 소싱 `참여 의사를 물어보는 중` — **갈래에는 넣되, 동의 전에는 딜이 안 나간다.**

사용자 요청: Series A 이상을 원하는 투자사는 `Series A 딜 소싱` 에 O 를 넣고, 참여
칸에는 `참여 의사를 물어보는 중` 과 사람이 적는 문구를 둘 수 있게.

예전 판정은 "불참여가 아니면 받는다" 였다. 그대로 값을 하나 들이면 그 값이 `참여`
와 똑같이 딜을 받는다 — 아직 동의하지 않은 분께 Series A 딜 공유 · 월간 리마인드가
나간다. 여기서 못 박는 것(`services/sourcing_sync.py` 머리말).

  ① 받는 것은 **정확히 `참여`** 뿐 — 불참여 · 물어보는 중 · 사람이 적은 문구는 안 받는다.
     O/X 칸은 `불참여` 만 X, 나머지는 O(갈래에 있음).
  ② 값 검사 — 세 값은 같은 뜻의 말을 맞춰 적고, 그 밖의 글은 그대로(40자 · 제어문자 금지).
  ③ O — 새 줄은 `딜 소싱 참여 제안 대기중`, `불참여` 였던 줄도 `제안 대기중`(다시
     묻는다), 참여 · 제안 대기중 · 물어보는 중 · 문구는 덮지 않는다. 새 줄의 담당은 넘길 수 있다(스크립트용).
  ④ 발송 — 딜 제안 관리 목록 · 참여 안내 · 월간 리마인드 · Series A 딜 공유 · 메일
     채널 · A1 소싱 리마인드(collect · still_ok)가 모두 같은 판정으로 뺀다.
  ⑤ 화면 — 딜 소싱 칸은 주황 딱지 · 보기 세 값 · 직접 적기. 딜 제안 관리에 뺀 수.
  ⑥ [방 후보 찾기] · 메일 주소 채우기는 물어보는 중인 분도 한다(발송이 아니다).
  ⑦ 시트를 다시 가져와도 `참여` 가 아닌 값은 되살린다(기본값 `참여` 로 돌아가지 않게).
  ⑧ 한꺼번에 넣는 스크립트(`scripts/apply_sourcing_marks.py`) — 미리보기는 DB 에 안 쓴다.

이름 · 회사 · 번호는 전부 가상값이다(공개 저장소).
"""
from __future__ import annotations

from datetime import datetime

import pytest

from tests.test_auto_sourcing_remind import (  # noqa: F401 - 픽스처를 함께 쓴다
    WEEK2, _aware, _items, _run, _turn_on, people)
from tests.test_series_a_deal_share import (  # noqa: F401 - 픽스처를 함께 쓴다
    SHARE, _ids, _send, today, world)
from tests.test_sourcing_link_confirm import _reimport
from tests.test_sourcing_vc_sync import (  # noqa: F401 - 픽스처를 함께 쓴다
    SHEET, SYNC, board, column, mail_on, mark, sc, sync_rows, vc)

ASKING = "참여 의사를 물어보는 중"
OFFER = "딜 소싱 참여 제안 대기중"     # O 로 새 줄이 생길 때의 기본값
CUSTOM = "11월 재연락"


class _Row:
    def __init__(self, participation):
        self.participation = participation


# ── ① 받는 것은 정확히 `참여` 뿐 ────────────────────────────────────────────

@pytest.mark.parametrize("value, takes, kind, mark_", [
    ("참여", True, "joined", "O"),
    ("  참여 ", True, "joined", "O"),
    (None, True, "joined", "O"),           # 빈 칸은 칸의 기본값(`참여`)
    ("불참여", False, "left", "X"),
    (ASKING, False, "pending", "O"),
    (OFFER, False, "pending", "O"),
    (CUSTOM, False, "pending", "O"),
])
def test_only_exact_joined_takes_part(value, takes, kind, mark_):
    from app.services import sourcing_sync

    row = _Row(value)
    assert sourcing_sync.takes_part(row) is takes
    assert sourcing_sync.kind_of(row) == kind
    assert sourcing_sync.mark_of(row) == mark_
    assert sourcing_sync.is_left(row) is (kind == "left")


# ── ② 값 검사 ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize("raw, saved", [
    ("참여", "참여"), ("O", "참여"), ("o", "참여"), ("○", "참여"),
    ("불참여", "불참여"), ("X", "불참여"), ("×", "불참여"),
    (ASKING, ASKING), ("물어보는 중", ASKING), ("물어보는중", ASKING),
    ("참여의사를 물어보는 중", ASKING),
    (OFFER, OFFER), ("제안 대기", OFFER), ("제안대기중", OFFER), ("참여 제안 대기중", OFFER),
    ("  " + CUSTOM + "  ", CUSTOM),           # 앞뒤 공백만 뗀다
    ("가" * 40, "가" * 40),                   # 40자까지
])
def test_participation_words(raw, saved):
    from app.services import sourcing_sync

    assert sourcing_sync.normalize_participation(raw) == saved


@pytest.mark.parametrize("raw", ["", "   ", None, "가" * 41, "다음 달\n연락", "보류\t중",
                                 "끝\x7f"])
def test_participation_refuses_blank_long_and_control(raw):
    from app.services import sourcing_sync

    with pytest.raises(sourcing_sync.SyncError):
        sourcing_sync.normalize_participation(raw)


def test_a_custom_phrase_is_saved_on_the_sourcing_screen(board, db, users):
    """딜 소싱 표에서 문구를 직접 적는다 — 그대로 저장되고 칸 갈래는 `pending`.
    투자사 관리 현황 칸은 O(갈래에 있음)."""
    contact = vc(db, users)
    row = sc(db, vc_contact_id=contact.id)

    r = board.patch(f"/api/sourcing/{row.id}", json={"participation": " " + CUSTOM})
    assert r.status_code == 200, r.text
    assert (r.json()["participation"], r.json()["participation_kind"]) == (CUSTOM, "pending")
    assert column(board, contact.id) == "O"

    r = board.patch(f"/api/sourcing/{row.id}", json={"participation": "물어보는 중"})
    assert (r.json()["participation"], r.json()["participation_kind"]) == (ASKING, "pending")

    r = board.patch(f"/api/sourcing/{row.id}", json={"participation": "o"})
    assert (r.json()["participation"], r.json()["participation_kind"]) == ("참여", "joined")


def test_adding_on_the_sourcing_screen_takes_a_custom_phrase(board, db, users):
    """[추가] 로 넣을 때도 같은 검사 — 안 적으면 예전처럼 `참여`(전화로 승낙받은 분)."""
    from app.models import SourcingContact

    r = board.post("/api/sourcing", params={"bucket": SYNC},
                   json={"name": "새심사", "participation": CUSTOM})
    assert r.status_code == 200, r.text
    assert db.get(SourcingContact, r.json()["id"]).participation == CUSTOM
    r = board.post("/api/sourcing", params={"bucket": SYNC}, json={"name": "새심사둘"})
    assert db.get(SourcingContact, r.json()["id"]).participation == "참여"
    r = board.post("/api/sourcing", params={"bucket": SYNC},
                   json={"name": "새심사셋", "participation": "줄\n바꿈"})
    assert r.status_code == 400


# ── ③ O 의 규칙 ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("before", ["참여", OFFER, ASKING, CUSTOM])
def test_O_does_not_overwrite_joined_asking_or_custom(board, db, users, before):
    contact = vc(db, users)
    sc(db, vc_contact_id=contact.id, participation=before)

    r = mark(board, contact.id, "O")
    assert r.status_code == 200, r.text
    [row] = sync_rows(db)
    assert row.participation == before
    assert column(board, contact.id) == "O"


def test_O_on_a_left_row_asks_again_and_X_leaves(board, db, users):
    contact = vc(db, users)
    sc(db, vc_contact_id=contact.id, participation="불참여")
    assert column(board, contact.id) == "X"

    assert mark(board, contact.id, "O").status_code == 200
    [row] = sync_rows(db)
    assert row.participation == OFFER
    assert column(board, contact.id) == "O"

    assert mark(board, contact.id, "X").status_code == 200
    [row] = sync_rows(db)
    assert row.participation == "불참여"


def test_set_mark_takes_an_assignee_and_a_participation_for_new_rows(db, users):
    """스크립트용 — 새 줄의 담당 · 참여를 넘긴다. 이어지기만 하는 줄의 담당은 그대로."""
    from app.models import SheetOwner
    from app.services import sourcing_sync

    db.add(SheetOwner(label=SHEET, user_id=users["u1"].id, layout="investor"))
    db.commit()
    fresh = vc(db, users)
    got = sourcing_sync.set_mark(db, fresh, "O", None, assignee=" 담당가 ",
                                 participation="참여")
    db.commit()
    assert got["action"] == sourcing_sync.ACT_CREATED
    [row] = sync_rows(db)
    assert (row.assignee_name, row.participation) == ("담당가", "참여")

    # 기본값 — 담당은 O 를 넣은 사람(없으면 투자사 줄 주인), 참여는 제안 대기중
    other = vc(db, users, name="이영희", phone="010-3333-4444")
    got = sourcing_sync.set_mark(db, other, "O", None)
    db.commit()
    assert got["participation"] == OFFER
    assert sync_rows(db)[-1].assignee_name == users["u1"].name

    # 같은 사람이 이미 갈래에 있으면 잇기만 — 담당은 넘겨도 안 바뀐다
    third = vc(db, users, name="박민수", phone="010-5555-6666")
    sc(db, name="박민수", phone="010-5555-6666", assignee_name="원래담당")
    got = sourcing_sync.set_mark(db, third, "O", None, assignee="담당가")
    db.commit()
    assert got["action"] == sourcing_sync.ACT_LINKED
    linked = [r for r in sync_rows(db) if r.vc_contact_id == third.id]
    assert [(r.assignee_name, r.participation) for r in linked] == [("원래담당", "참여")]


# ── ④ 발송 — 모든 길이 같은 판정 ────────────────────────────────────────────

def _four(db):
    return {
        "joined": sc(db, name="참여심사", phone="010-1000-0001", kakao_room_name="참여 방"),
        "asking": sc(db, name="묻는심사", phone="010-1000-0002", kakao_room_name="묻는 방",
                     participation=ASKING),
        "custom": sc(db, name="메모심사", phone="010-1000-0003", kakao_room_name="메모 방",
                     participation=CUSTOM),
        "left": sc(db, name="빠진심사", phone="010-1000-0004", kakao_room_name="빠진 방",
                   participation="불참여"),
    }


def test_pending_people_are_not_offered_and_not_sent(board, db, users):
    rows = _four(db)

    deals = board.get("/deals").text
    listing = deals[deals.index('id="sourcing-list"'):]
    assert f'value="{rows["joined"].id}"' in listing
    for key in ("asking", "custom", "left"):
        assert f'value="{rows[key].id}"' not in listing, key
    # 뺀 수를 목록 위에 적는다 — 확인 전과 불참여를 나눠서
    held = deals[deals.index('id="sourcing-held"'):]
    held = held[:held.index("</p>")]
    assert "참여 확인 전(제안 대기·물어보는 중 등) <b>2</b>명" in held
    assert "불참여 <b>1</b>명" in held

    for topic in ("sourcing_intro", "sourcing_remind"):
        r = board.post("/api/deals/send", json={"contact_ids": [rows["asking"].id],
                                                "mode": "sourcing", "topic": topic})
        assert r.status_code == 400, r.text
        assert f"참여 확인 전({ASKING})" in r.json()["detail"]

        ids = [rows[k].id for k in ("joined", "asking", "custom", "left")]
        r = board.post("/api/deals/send", json={"contact_ids": ids,
                                                "mode": "sourcing", "topic": topic})
        assert r.status_code == 200, r.text
        assert r.json()["total"] == 1
        reasons = {s["name"]: s["reason"] for s in r.json()["skipped"]}
        assert f"참여 확인 전({CUSTOM})" in reasons["메모심사"]
        assert "참여 확인 전" in reasons["묻는심사"]
        assert "딜 소싱 불참여" in reasons["빠진심사"]

    preview = board.post("/api/deals/preview", json={
        "contact_ids": [rows["asking"].id], "mode": "sourcing"}).json()
    assert any("참여 확인 전" in w for w in preview["previews"][0]["warnings"])


def test_offer_pending_people_are_not_offered_and_not_sent(board, db, users):
    """O 로 막 넣은 분(`딜 소싱 참여 제안 대기중`) — 목록에도 없고 보내도 빠진다."""
    joined = sc(db, name="참여심사", phone="010-1000-0001", kakao_room_name="참여 방")
    offer = sc(db, name="대기심사", phone="010-1000-0006", kakao_room_name="대기 방",
               participation=OFFER)

    deals = board.get("/deals").text
    listing = deals[deals.index('id="sourcing-list"'):]
    assert f'value="{offer.id}"' not in listing
    for topic in ("sourcing_intro", "sourcing_remind"):
        r = board.post("/api/deals/send", json={"contact_ids": [joined.id, offer.id],
                                                "mode": "sourcing", "topic": topic})
        assert r.status_code == 200, r.text
        assert r.json()["total"] == 1
        reasons = {s["name"]: s["reason"] for s in r.json()["skipped"]}
        assert f"참여 확인 전({OFFER})" in reasons["대기심사"]


def test_state_marks_pending_people_out_with_their_own_label(board, db, users):
    rows = _four(db)
    state = {r["id"]: r for r in board.get("/api/sourcing/state").json()["rows"]}
    assert (state[rows["joined"].id]["out"], state[rows["joined"].id]["out_label"]) == (False, "")
    assert state[rows["asking"].id]["out"] is True
    assert state[rows["asking"].id]["out_label"] == f"참여 확인 전 · {ASKING}"
    assert state[rows["custom"].id]["out_label"] == f"참여 확인 전 · {CUSTOM}"
    assert state[rows["left"].id]["out_label"] == "딜 소싱 불참여"


def test_the_mail_channel_skips_pending_people_too(board, db, users, mail_on, monkeypatch):
    from app.services import mail_sender

    monkeypatch.setattr(mail_sender, "send_job", lambda *a, **k: None)
    asking = sc(db, email="ask@example.com", participation=ASKING)
    r = board.post("/api/deals/send", json={"contact_ids": [asking.id],
                                            "mode": "sourcing", "channel": "email"})
    assert r.status_code == 400
    assert "참여 확인 전" in r.json()["detail"]


def test_series_a_share_skips_pending_people(world, client, db):
    from app.models import SourcingContact

    db.get(SourcingContact, world["p"]["b"].id).participation = ASKING
    db.commit()
    r = _send(client, _ids(world, "a", "b"), _ids(world, "bio", kind="c"))
    assert r.status_code == 200, r.text
    assert r.json()["total"] == 1
    reasons = {s["name"]: s["reason"] for s in r.json()["skipped"]}
    assert "참여 확인 전" in reasons["나심사"]


def test_A1_remind_skips_pending_people(db, users, people):
    people["a"].participation = ASKING
    people["b"].participation = CUSTOM
    db.commit()
    _turn_on(db)
    result = _run(db, WEEK2)
    assert _items(db) == []
    assert any(ASKING in s for s in result["skipped"])
    assert any(CUSTOM in s for s in result["skipped"])


def test_A1_drops_someone_who_became_pending_before_release(db, users, people):
    from app.models import SourcingContact
    from app.services import scheduled_send

    _turn_on(db)
    _run(db, WEEK2)
    assert len(_items(db)) == 2
    db.get(SourcingContact, people["a"].id).participation = ASKING
    db.commit()
    scheduled_send.run_once(db, _aware(datetime(2026, 10, 14, 11, 0, 20)))
    status = {i.sourcing_contact_id: i.status for i in _items(db)}
    assert status[people["a"].id] == "canceled"
    assert status[people["b"].id] != "canceled"


def test_A1_still_ok_names_the_value(db, users, people):
    from app.models import AutomationSend
    from app.services.automations import sourcing_remind

    people["a"].participation = CUSTOM
    db.commit()
    rec = AutomationSend(ref=f"remind:{people['a'].id}:2026-10:2")
    assert sourcing_remind.still_ok(db, rec) == CUSTOM


# ── ⑤ 화면 ──────────────────────────────────────────────────────────────────

def test_the_sourcing_cell_shows_pending_differently(board, db, users):
    rows = _four(db)
    body = board.get(f"/sourcing?tab={SYNC}").text

    def cell(row):
        tr = body[body.index(f'<tr data-id="{row.id}"'):]
        tr = tr[:tr.index("</tr>")]
        at = tr.index('data-field="participation"')
        return tr, tr[tr.rfind("<td", 0, at):tr.index("</td>", at)]

    tr, td = cell(rows["asking"])
    assert 'data-part-kind="pending"' in tr
    assert "part-pending" in td and ASKING in td
    assert f'data-choices="참여,불참여,{OFFER},{ASKING}"' in td
    tr, td = cell(rows["custom"])
    assert 'data-part-kind="pending"' in tr and "part-pending" in td
    tr, td = cell(rows["left"])
    assert 'data-part-kind="left"' in tr and "muted" in td and "part-pending" not in td
    tr, td = cell(rows["joined"])
    assert 'data-part-kind="joined"' in tr and "part-pending" not in td


def test_the_pending_badge_has_a_style():
    from pathlib import Path

    css = Path("app/static/css/app.css").read_text(encoding="utf-8")
    assert "#sourcing-table td.part-pending" in css


# ── ⑥ 준비는 물어보는 중인 분도 한다 ────────────────────────────────────────

def test_room_search_and_address_count_include_pending_people(board, db, users):
    from app.services import sourcing_receipts, sourcing_rooms

    asking = sc(db, name="묻는심사", phone="010-1000-0002", participation=ASKING)
    custom = sc(db, name="메모심사", phone="010-1000-0003", participation=CUSTOM)
    left = sc(db, name="빠진심사", phone="010-1000-0004", participation="불참여")
    found = [r.id for r in sourcing_rooms.needs_room(db, [asking, custom, left])]
    assert found == [asking.id, custom.id]
    assert sourcing_receipts.without_address(db) == 2


# ── ⑦ 시트를 다시 가져와도 되살린다 ─────────────────────────────────────────

def test_reimport_keeps_participation_that_is_not_joined(board, db, users, tmp_path,
                                                         monkeypatch):
    sc(db, name="묻는심사", phone="010-1000-0002", participation=ASKING)
    sc(db, name="메모심사", phone="010-1000-0003", participation=CUSTOM)
    sc(db, name="빠진심사", phone="010-1000-0004", participation="불참여")
    sc(db, name="참여심사", phone="010-1000-0001")

    _reimport(tmp_path, monkeypatch, [
        ("2026-10-01", "묻는심사", "010-1000-0002", "가나벤처스"),
        ("2026-10-01", "메모심사", "010-1000-0003", "가나벤처스"),
        ("2026-10-01", "빠진심사", "010-1000-0004", "가나벤처스"),
        ("2026-10-01", "참여심사", "010-1000-0001", "가나벤처스"),
        ("2026-10-01", "새로온심사", "010-1000-0005", "가나벤처스"),
    ])
    got = {r.name: r.participation for r in sync_rows(db)}
    assert got == {"묻는심사": ASKING, "메모심사": CUSTOM, "빠진심사": "불참여",
                   "참여심사": "참여", "새로온심사": "참여"}


# ── ⑧ 한꺼번에 넣는 스크립트 ────────────────────────────────────────────────

@pytest.fixture()
def marks_world(db, users):
    """투자사 줄 다섯 — 새로 들어갈 분 · 이미 이어진 분 · 불참여로 이어진 분 ·
    번호만 같은 줄이 있는 분(막힘) · 감춘 줄."""
    from app.models import SheetOwner

    db.add(SheetOwner(label=SHEET, user_id=users["u1"].id, layout="investor"))
    db.commit()
    w = {
        "new": vc(db, users, name="새로심사", phone="010-2000-0001"),
        "joined": vc(db, users, name="참여심사", phone="010-2000-0002"),
        "left": vc(db, users, name="빠진심사", phone="010-2000-0003"),
        "phone_only": vc(db, users, name="번호심사", phone="010-2000-0004"),
        "hidden": vc(db, users, name="감춘심사", phone="010-2000-0005", is_hidden=1),
    }
    sc(db, name="참여심사", phone="010-2000-0002", vc_contact_id=w["joined"].id,
       assignee_name="원래담당")
    sc(db, name="빠진심사", phone="010-2000-0003", vc_contact_id=w["left"].id,
       participation="불참여")
    sc(db, name="다른이름", phone="010-2000-0004")          # 번호만 같다 → 막힘
    return w


def _ids_file(tmp_path, w, extra=()):
    path = tmp_path / "ids.txt"
    lines = ["# 시험 목록", *(str(w[k].id) for k in w), *extra]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_the_script_previews_without_writing(db, users, marks_world, tmp_path, capsys):
    from scripts import apply_sourcing_marks

    before = [(r.id, r.participation, r.vc_contact_id) for r in sync_rows(db)]
    path = _ids_file(tmp_path, marks_world, extra=["999999", str(marks_world["new"].id)])
    assert apply_sourcing_marks.main(["--ids-file", str(path), "--assignee", "담당가"]) == 0
    out = capsys.readouterr().out
    assert "미리보기" in out
    assert "새 줄 1 · 기존 줄과 이음 0 · 참여만 바꿈 0 · 그대로(이미 갈래에 있음) 1 · " \
           "막힘 1 · 건너뜀 3 (모두 6)" in out
    # 이름은 찍지 않는다(막힌 까닭도 `--show-reasons` 일 때만)
    for name in ("새로심사", "다른이름", "번호심사"):
        assert name not in out
    assert [(r.id, r.participation, r.vc_contact_id) for r in sync_rows(db)] == before


def test_the_script_applies_through_set_mark(db, users, marks_world, tmp_path, capsys):
    from scripts import apply_sourcing_marks

    path = _ids_file(tmp_path, marks_world)
    assert apply_sourcing_marks.main(["--ids-file", str(path), "--assignee", "담당가",
                                      "--apply", "--show-reasons"]) == 0
    out = capsys.readouterr().out
    assert "저장했습니다" in out and "이 분으로 확정" in out
    rows = {r.vc_contact_id: r for r in sync_rows(db) if r.vc_contact_id}
    new = rows[marks_world["new"].id]
    assert (new.participation, new.assignee_name) == (OFFER, "담당가")
    # 이미 이어진 분은 그대로 — 담당도 참여도
    joined = rows[marks_world["joined"].id]
    assert (joined.participation, joined.assignee_name) == ("참여", "원래담당")
    # 불참여(X)는 건드리지 않는다
    assert rows[marks_world["left"].id].participation == "불참여"
    assert marks_world["phone_only"].id not in rows
    assert marks_world["hidden"].id not in rows


def test_the_script_can_ask_again_and_refuses_bad_values(db, users, marks_world, tmp_path,
                                                         capsys):
    from scripts import apply_sourcing_marks

    path = tmp_path / "one.txt"
    path.write_text(f"{marks_world['left'].id}\n", encoding="utf-8")
    assert apply_sourcing_marks.main(["--ids-file", str(path), "--revive-left",
                                      "--apply"]) == 0
    rows = {r.vc_contact_id: r for r in sync_rows(db) if r.vc_contact_id}
    assert rows[marks_world["left"].id].participation == OFFER

    assert apply_sourcing_marks.main(["--ids-file", str(path),
                                      "--participation", "줄\n바꿈"]) == 2
    bad = tmp_path / "bad.txt"
    bad.write_text("12a\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        apply_sourcing_marks.main(["--ids-file", str(bad)])
