"""#31 A7 이 물은 미팅 — 사람 쪽 알림은 **'자동 문의함 M/D' + 답 적는 칸**만.

사용자 결정(2026-10-17, "추천대로"):

4. A7 이 물은 미팅(`automation_sends` 의 `meeting:<미팅>` · `meeting30:<미팅>`, 실제
   모드 · 나간 것)은 사람 쪽 결과 문의 자리에서 **'물어보세요' 가 아니라 '자동
   문의함 M/D'** 로 서고 답 적는 칸만 남는다 — `/ir` 결과 문의 · 오늘 할 일 ·
   결과 문의 문자(그 미팅은 빠진다) · 발송 화면의 미팅 후기 탭. `followup_done`
   은 켜지 않는다 — 답은 사람이 적는다.
5. 전환하는 날 밀린 결과 문의는 저절로 안 나간다 — 오늘 할 일에 수 한 줄
   (`자동화 전환 전 밀린 결과 문의 N건 — 손으로 확인`).

이름·회사명은 전부 지어낸 값이다(공개 저장소).
"""
from __future__ import annotations

import pytest
from sqlalchemy import select

from tests.conftest import DEMO_PASSWORD

LONG_PAST = "2020-01-06"          # 결과를 물을 날이 오래전에 지났다
SENT_AT = "2026-10-14T14:00:30+09:00"
TEST_ROOM = "자동화 시험방"


@pytest.fixture()
def world(db, users):
    from app.models import Meeting, VcContact

    def contact(owner, name, firm):
        row = VcContact(user_id=owner.id, name=name, firm=firm, title="심사역",
                        kakao_room_name=f"{name} {firm} Deal 공유",
                        connect_stage="connected", source_sheet="내 명단")
        db.add(row)
        db.flush()
        return row

    def meeting(owner, who, done=LONG_PAST):
        row = Meeting(user_id=owner.id, contact_id=who.id, scheduled_at=done,
                      status="done", done_at=done, followup_due=done,
                      followup_done=0, outcome="reviewing")
        db.add(row)
        db.flush()
        return row

    people = {"asked": contact(users["u1"], "홍길동", "가나벤처스"),
              "manual": contact(users["u1"], "김서연", "마바벤처스")}
    meetings = {k: meeting(users["u1"], v) for k, v in people.items()}
    db.commit()
    return {"people": people, "meetings": meetings}


def _asked(db, meeting, *, sent_at=SENT_AT, status="sent", test=0, head="meeting"):
    """A7 이 이 미팅에 한 통을 실었다(나갔다) — 러너가 남기는 그 모양 그대로."""
    from app.models import AutomationSend, DealBatch, SendItem, SendJob

    batch = DealBatch(user_id=2, title="미팅 후 검토결과 문의 자동", sent_date=SENT_AT[:10])
    db.add(batch)
    db.flush()
    job = SendJob(user_id=2, kind="deal_intro", batch_id=batch.id, status="done",
                  total=1, sent=1, failed=0)
    db.add(job)
    db.flush()
    item = SendItem(job_id=job.id, contact_id=meeting.contact_id, channel="kakao",
                    room_name="방", message="미팅 후기", status=status,
                    sent_at=sent_at if status == "sent" else None)
    db.add(item)
    db.flush()
    db.add(AutomationSend(automation="meeting_review", ref=f"{head}:{meeting.id}",
                          test=test, job_id=job.id, item_id=item.id,
                          contact_id=meeting.contact_id, room="방"))
    db.commit()
    return item


# ── 무엇을 '물었다' 로 보나 ─────────────────────────────────────────────────

def test_a_sent_real_ask_moves_the_meeting_off_the_ask_list(db, users, world):
    from app.services import pipeline

    _asked(db, world["meetings"]["asked"])
    items = pipeline.today_items(db, users["u1"])
    assert [m["id"] for m in items["due_followups"]] == [world["meetings"]["manual"].id]
    [asked] = items["asked_followups"]
    assert asked["id"] == world["meetings"]["asked"].id
    assert asked["auto_asked"] is True and asked["auto_asked_on"] == "10/14"
    # 결과는 사람이 적는다 — 묻는 것만으로 '문의함' 이 켜지지 않는다.
    db.refresh(world["meetings"]["asked"])
    assert world["meetings"]["asked"].followup_done == 0


@pytest.mark.parametrize("kw", [{"status": "pending"}, {"status": "canceled"},
                                {"status": "failed"}, {"test": 1}])
def test_an_ask_that_did_not_reach_the_investor_does_not_count(db, users, world, kw):
    """아직 안 나갔거나 · [중단] · 실패 · 시험방으로 간 한 통은 '물었다' 가 아니다."""
    from app.services import pipeline

    _asked(db, world["meetings"]["asked"], **kw)
    items = pipeline.today_items(db, users["u1"])
    assert world["meetings"]["asked"].id in {m["id"] for m in items["due_followups"]}
    assert items["asked_followups"] == []


def test_the_thirty_day_decision_ask_counts_too_and_the_latest_date_shows(db, users, world):
    from app.services import pipeline

    _asked(db, world["meetings"]["asked"], sent_at="2026-09-16T14:00:10+09:00")
    _asked(db, world["meetings"]["asked"], head="meeting30")
    [asked] = pipeline.today_items(db, users["u1"])["asked_followups"]
    assert asked["auto_asked_on"] == "10/14"


# ── 결과 문의 문자 ─────────────────────────────────────────────────────────

def test_the_reminder_sms_skips_an_auto_asked_meeting(db, users, world):
    from app.services import followup_sms

    _asked(db, world["meetings"]["asked"])
    [(user, rows)] = followup_sms.recipients(db)
    assert user.id == users["u1"].id
    assert [r["id"] for r in rows] == [world["meetings"]["manual"].id]
    _asked(db, world["meetings"]["manual"])
    assert followup_sms.recipients(db) == []


# ── /ir ────────────────────────────────────────────────────────────────────

def _page(client):
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    return client.get("/ir").text


def test_ir_shows_auto_asked_with_an_answer_field_only(db, users, world, client):
    _asked(db, world["meetings"]["asked"])
    page = _page(client)
    group = page.split('data-testid="asked-followups"', 1)[1].split("</ul>", 1)[0]
    assert "홍길동" in group and "자동 문의함 10/14" in group
    assert 'name="note"' in group and "답 적기" in group
    assert "문의 완료" not in group and "물어" not in group
    ask = page.split("결과를 물어볼 때가 됐습니다", 1)[1].split("</ul>", 1)[0]
    assert "김서연" in ask and "홍길동" not in ask
    # 아래 미팅 표의 결과 문의 칸도 '지남' 대신 자동 문의함.
    table = page.split('id="review-table"', 1)[1]
    row = table.split("홍길동", 1)[1].split("</tr>", 1)[0]
    assert "자동 문의함 10/14" in row and "지남" not in row and "답 적기" in row


def test_writing_the_answer_closes_it(db, users, world, client):
    from app.services import pipeline

    _asked(db, world["meetings"]["asked"])
    _page(client)
    client.post(f"/ir/meetings/{world['meetings']['asked'].id}/followup",
                data={"outcome": "investing", "note": "다음 주 내부 검토"})
    db.expire_all()
    items = pipeline.today_items(db, users["u1"])
    assert items["asked_followups"] == []
    assert world["meetings"]["asked"].followup_done == 1


# ── 오늘 할 일 ─────────────────────────────────────────────────────────────

def test_today_says_auto_asked_instead_of_ask(db, users, world):
    from app.services import today

    _asked(db, world["meetings"]["asked"])
    items = today.build(db, users["u1"])["items"]
    ask = [i for i in items if i["title"] == "미팅 결과 문의"]
    assert ask and ask[0]["count"] == 1 and "홍길동" not in ask[0]["detail"]
    [answer] = [i for i in items if "자동 문의" in i["title"]]
    assert "홍길동" in answer["detail"] and "10/14" in answer["detail"]
    assert answer["count"] == 1 and answer["href"].startswith("/ir")


# ── 발송 화면 미팅 후기 탭 ──────────────────────────────────────────────────

def test_the_review_tab_preview_warns_it_was_auto_asked(db, users, world, client):
    _asked(db, world["meetings"]["asked"])
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    ids = [world["people"]["asked"].id, world["people"]["manual"].id]
    answer = client.post("/api/deals/preview", json={"contact_ids": ids,
                                                      "company_ids": [], "mode": "review"})
    assert answer.status_code == 200, answer.text
    by = {p["contact_id"]: p["warnings"] for p in answer.json()["previews"]}
    assert any("자동 문의함 10/14" in w for w in by[world["people"]["asked"].id])
    assert not any("자동 문의함" in w for w in by[world["people"]["manual"].id])


# ── 5. 전환 전 밀린 결과 문의 ───────────────────────────────────────────────

def _a7_real(db, users, *, test=False):
    from app.models import AutoSendSetting
    from app.services import automation

    db.add(AutoSendSetting(kind="startup_ir", enabled=1, user_id=users["u2"].id))
    db.commit()
    return automation.save(db, automation.MEETING_REVIEW, enabled=True, user_id=None,
                           test_mode=test, test_room=TEST_ROOM)


def _first_run(db, day="2026-10-14"):
    from app.models import AutoSendRun

    db.add(AutoSendRun(kind="auto:meeting_review", ref_id=int(day.replace("-", "")),
                       user_id=2, day=day, status="empty"))
    db.commit()


def _admin(db):
    from app.models import User
    from app.services import auth as auth_svc

    row = User(id=9, name="관리자", phone="01000000009", role="admin",
               password_hash=auth_svc.hash_password(DEMO_PASSWORD))
    db.add(row)
    db.commit()
    return row


def _backlog_lines(db, user):
    from app.services import today

    return [i for i in today.build(db, user)["items"] if "밀린 결과 문의" in i["title"]]


def test_the_switch_over_backlog_is_one_count_line(db, users, world):
    from app.models import Meeting

    _a7_real(db, users)
    _first_run(db)
    # A7 이 켜진 뒤 물을 차례가 온 미팅(완료 10/12 → 10/14) — 밀린 것이 아니다.
    recent = Meeting(user_id=1, contact_id=world["people"]["manual"].id,
                     scheduled_at="2026-10-12", status="done", done_at="2026-10-12",
                     followup_due="2026-10-15", followup_done=0, outcome="reviewing")
    db.add(recent)
    db.delete(world["meetings"]["manual"])
    db.commit()
    admin = _admin(db)
    [line] = _backlog_lines(db, admin)
    assert line["title"] == "자동화 전환 전 밀린 결과 문의 1건 — 손으로 확인"
    assert line["count"] == 1 and users["u1"].name in line["detail"]
    # 보내는 계정(u2)에게도, 담당 팀원(u1)에게는 안 선다 — 그 사람에게는 '미팅 결과 문의' 가 선다.
    assert len(_backlog_lines(db, users["u2"])) == 1
    assert _backlog_lines(db, users["u1"]) == []


def test_an_auto_asked_meeting_is_not_backlog(db, users, world):
    _a7_real(db, users)
    _first_run(db)
    _asked(db, world["meetings"]["asked"])
    [line] = _backlog_lines(db, _admin(db))
    assert line["count"] == 1          # 손으로 볼 것은 김서연 한 건


@pytest.mark.parametrize("case", ["off", "test", "never_ran"])
def test_no_backlog_line_before_a7_really_runs(db, users, world, case):
    from app.services import automation

    _a7_real(db, users, test=(case == "test"))
    if case == "off":
        automation.turn_off(db, automation.MEETING_REVIEW)
    if case != "never_ran":
        _first_run(db)
    assert _backlog_lines(db, _admin(db)) == []


def test_the_backlog_is_never_sent_automatically(db, users, world):
    """A7 은 사흘 넘게 지난 미팅을 줍지 않는다 — 켜는 날 밀린 것이 한꺼번에 나가지 않는다."""
    from datetime import datetime

    from app.models import AutomationSend
    from app.services import automation, automation_runner as runner

    _a7_real(db, users)
    result = runner.run_once(db, automation.MEETING_REVIEW,
                             datetime(2026, 10, 19, 9, 0).astimezone())
    assert result["status"] == "empty"
    assert db.execute(select(AutomationSend)).scalars().all() == []
