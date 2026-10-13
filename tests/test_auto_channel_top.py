"""A3 채널방 TOP·핵심 딜 — **매주 수요일, 방마다 같은 3곳, 몇 분씩 띄워.**

1. 매주 수요일 13:30 부터 방마다 회차가 따로 서고, 방 사이가 2~5분이다.
2. 모든 방에 같은 기업들 — 기업 덩어리는 딜 소개와 같은 모양, 앞뒤 줄만 방마다 다르다.
3. 고르는 차례: 채널로 한 번도 안 나간 기업 → 마지막 발송이 오래된 기업.
   90일 안에 나간 기업 · 딜소개 불가 · 내용 부족은 뺀다.
4. 3곳이 안 되면 있는 만큼, 0곳이면 그 주는 건너뛰고 오늘 할 일에 사유.
5. 채널 발송 기록은 실제로 나간 건만 센다.
6. 채널방 이름은 시험방으로 쓸 수 없다.
"""
from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import select

TEST_ROOM = "자동화 시험방"
ROOMS = ["투자 채널 하나", "투자 채널 둘", "투자 채널 셋"]
WED = datetime(2026, 10, 14, 9, 0)        # 2026 년 42주차 수요일


def _aware(when):
    return when.astimezone()


@pytest.fixture()
def deals(db, users):
    from app.models import AutoSendSetting, IrCompany

    users["u2"].role = "admin"
    db.add(AutoSendSetting(kind="startup_ir", enabled=1, user_id=users["u2"].id))

    def company(name, *, top=1, received="2026-10-01", **kw):
        row = IrCompany(name=name, is_top_deal=top, received_at=received,
                        sector_major="AI", one_liner=f"{name} 한 줄 소개",
                        funding_total="30억", **kw)
        db.add(row)
        db.flush()
        return row

    rows = {
        "new1": company("가나기업", received="2026-10-10"),
        "new2": company("다라기업", received="2026-10-05"),
        "old": company("마바기업"),
        "recent": company("사아기업"),
        "blocked": company("자차기업", contract_status="blocked"),
        "plain": company("카타기업", top=0),
    }
    db.commit()
    return rows


def _turn_on(db, *, test=False, rooms=ROOMS, **params):
    from app.services import automation, automation_runner as runner

    runner.save_params(db, automation.CHANNEL_TOP,
                       {"rooms": "\n".join(rooms), **params})
    return automation.save(db, automation.CHANNEL_TOP, enabled=True,
                           user_id=None, test_mode=test, test_room=TEST_ROOM)


def _run(db, now=WED):
    from app.services import automation, automation_runner as runner

    return runner.run_once(db, automation.CHANNEL_TOP, _aware(now))


def _jobs(db):
    from app.models import SendJob

    db.expire_all()
    return db.execute(select(SendJob).order_by(SendJob.id)).scalars().all()


def _history(db, company, when, test=0):
    """그 기업이 채널로 실제로 나간 기록 한 줄."""
    from app.models import AutomationSend, SendItem, SendJob

    job = SendJob(user_id=2, kind="deal_intro", status="done", total=1)
    db.add(job)
    db.flush()
    item = SendItem(job_id=job.id, room_name="투자 채널 하나", message="x",
                    status="sent", sent_at=f"{when}T13:30:00+09:00")
    db.add(item)
    db.flush()
    db.add(AutomationSend(automation="channel_top", ref=f"old:{company.id}:{when}",
                          test=test, job_id=job.id, item_id=item.id,
                          company_id=company.id))
    db.commit()


def test_one_job_per_room_minutes_apart_same_companies(db, users, deals):
    from app.services import scheduled_send

    _history(db, deals["old"], "2026-05-01")      # 90일 넘었다 — 다시 갈 수 있다
    _history(db, deals["recent"], "2026-09-30")   # 90일 안 — 뺀다
    _turn_on(db)
    result = _run(db)
    assert result["status"] == "ready", result
    jobs = [j for j in _jobs(db) if j.status == "draft"]
    assert len(jobs) == 3
    times = [scheduled_send.scheduled_at(j) for j in jobs]
    assert times[0].strftime("%H:%M") == "13:30"
    gaps = [(b - a).total_seconds() / 60 for a, b in zip(times, times[1:])]
    assert all(2 <= g <= 5 for g in gaps)
    assert [j.items[0].room_name for j in jobs] == ROOMS
    assert all(j.user_id == users["u2"].id for j in jobs)

    texts = [j.items[0].message for j in jobs]
    for text in texts:
        # 한 번도 안 나간 기업(수신일 최신순) → 오래된 기업. 90일 안 · 불가는 없다.
        assert text.index("가나기업") < text.index("다라기업") < text.index("마바기업")
        assert "사아기업" not in text and "자차기업" not in text and "카타기업" not in text
        assert "[기업1] " in text
    # 앞뒤 줄은 방마다 다르다.
    assert len({t.splitlines()[0] for t in texts}) > 1


def test_fewer_than_three_sends_what_there_is(db, users, deals):
    for key in ("new2", "old", "recent"):
        deals[key].is_top_deal = 0
    db.commit()
    _turn_on(db)
    _run(db)
    text = _jobs(db)[0].items[0].message
    assert "가나기업" in text and "[기업2]" not in text


def test_zero_skips_the_week_with_a_note(db, users, deals):
    from app.services import automation_runner as runner

    for row in deals.values():
        row.is_top_deal = 0
    db.commit()
    _turn_on(db)
    assert _run(db)["status"] == "empty"
    lines = runner.today_items(db, users["u2"], _aware(datetime(2026, 10, 14, 10, 0)))
    assert any("TOP·핵심 딜이 0곳" in line["detail"] for line in lines)


def test_only_wednesdays(db, users, deals):
    _turn_on(db)
    assert _run(db, datetime(2026, 10, 13, 9, 0))["status"] == "not_today"


def test_history_counts_only_sent_items(db, users, deals):
    from app.models import SendItem
    from app.services.automations import channel_top

    _turn_on(db)
    _run(db)
    assert channel_top.last_sent(db, False) == {}
    first = _jobs(db)[0]
    item = first.items[0]
    item.status = "sent"
    item.sent_at = "2026-10-14T13:30:20+09:00"
    db.commit()
    got = channel_top.last_sent(db, False)
    assert set(got) == {deals["new1"].id, deals["new2"].id, deals["old"].id}
    assert db.get(SendItem, item.id).status == "sent"


def test_next_week_rotates_to_others(db, users, deals):
    from app.models import IrCompany

    extra = IrCompany(name="하하기업", is_top_deal=1, received_at="2026-09-01",
                      sector_major="AI", one_liner="하하기업 한 줄", funding_total="10억")
    db.add(extra)
    db.commit()
    _turn_on(db)
    _run(db)
    for job in _jobs(db):
        for item in job.items:
            item.status = "sent"
            item.sent_at = "2026-10-14T13:40:00+09:00"
    db.commit()
    _run(db, datetime(2026, 10, 21, 9, 0))
    newest = _jobs(db)[-1].items[0].message
    assert "하하기업" in newest and "가나기업" not in newest


def test_test_mode_and_channel_rooms_are_not_test_rooms(db, users, deals):
    from app.services import automation

    _turn_on(db, test=True)
    _run(db)
    assert {j.items[0].room_name for j in _jobs(db)} == {TEST_ROOM}
    assert _jobs(db)[0].items[0].message.startswith("[시험] 원래 받을 방: 투자 채널 하나")
    assert "실제 상대" in automation.test_room_problem(db, "투자 채널 둘")


def test_empty_room_list_is_a_note(db, users, deals):
    _turn_on(db, rooms=[])
    result = _run(db)
    assert result["status"] == "empty"
