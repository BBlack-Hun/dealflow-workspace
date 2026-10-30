"""스타트업 월간 발송 — **같은 달에 이미 받은 기업에게 다시 나가지 않는다.**

10/30 에 취소된 회차에서 9곳이 나간 뒤 같은 40곳으로 새 회차가 서서, 그 9곳에
같은 글이 20분 간격으로 다시 나갔다. 대기 목록도 나가는 순간도 "이 달에 이미 보낸
기업" 을 빼지 않았다. 판정은 `startup_monthly.received` 하나다.

1. 대기 목록 — 이미 보낸(sent) 기업은 고를 수 없다. 실패 · 취소만 있으면 고른다.
2. 나가는 순간 — [발송 시작] · 예약 · 이어 보내기 · 재시도 · 취소분 재발송 모두
   그 기업의 대기 건을 사유를 적어 취소한다(옛 draft 를 눌러도 안 나간다).
3. 다른 달이면 막지 않는다. A5 는 제 확인 그대로이고 결과가 같다.

이름은 전부 지어낸 값이다 — 저장소가 공개다.
"""
from __future__ import annotations

from datetime import timedelta
from urllib.parse import unquote

import pytest

from tests.test_startup_monthly_send import (  # noqa: F401 - 픽스처를 함께 쓴다
    _jobs, _login, _make_draft, _month, _poll, _turn_on, seeded)

COMPANY_TWO = "샘플디"


@pytest.fixture()
def two(db, seeded):
    """보낼 수 있는 계약 기업 하나 더."""
    from app.models import IrCompany, IrRequest, VcContact

    company = IrCompany(name=COMPANY_TWO, contract_status="paid",
                        kakao_room_name=f"{COMPANY_TWO} 대표님")
    contact = VcContact(user_id=1, name="김철수", firm="마바파트너스")
    db.add_all([company, contact])
    db.flush()
    db.add(IrRequest(user_id=1, contact_id=contact.id, company_id=company.id,
                     company_name=COMPANY_TWO, requested_at=f"{seeded['month']}-04"))
    db.commit()
    return company


def _past_job(db, company_id, month, *, status="sent", job_status="done"):
    """그 달치 회차 하나를 바로 심는다 — 회차명에 달이 적힌다(화면의 기본 이름)."""
    from app.models import DealBatch, SendItem, SendJob

    batch = DealBatch(user_id=1, title=f"10/30 (스타트업 월간 발송 {month})")
    db.add(batch)
    db.flush()
    job = SendJob(user_id=1, kind="startup_ir", batch_id=batch.id,
                  status=job_status, total=1)
    db.add(job)
    db.flush()
    db.add(SendItem(job_id=job.id, ir_company_id=company_id, room_name="방",
                    message="글", status=status,
                    sent_at=f"{month}-15T15:11:00+09:00" if status == "sent" else None))
    db.commit()
    return job


def _by_company(db, job):
    db.expire_all()
    return {i.ir_company_id: i for i in job.items}


# ── 1. 대기 목록 ─────────────────────────────────────────────────────────────

def test_이번_달_보낸_기업은_목록에서_빠진다(db, seeded, two, client):
    from app.services import startup_send

    ok, month = seeded["ok"].id, seeded["month"]
    _turn_on(db)
    _past_job(db, ok, month)

    page = _login(client).get("/deals/startup-ir").text
    assert f"이번 달 보냄({month[5:7]}/15)" in page
    assert "이미 보냄 <b>1곳</b>" in page
    assert startup_send.sendable_ids(db, month) == [two.id]
    # 주소로 밀어 넣어도 — 화면의 폼도, 곧장 `queued` 로 세우는 길도 막힌다.
    back = _make_draft(client, seeded, ids=[ok, two.id])
    assert "보낼 수 없는 기업이 섞였습니다" in unquote(back.headers["location"])
    direct = client.post("/api/deals/send", json={
        "contact_ids": [ok], "mode": "startup", "month": month})
    assert direct.status_code == 400 and "이미 받은" in direct.json()["detail"]
    assert len(_jobs(db)) == 1


def test_실패나_취소만_있으면_다시_고를_수_있다(db, seeded, two):
    from app.services import startup_send

    ok, month = seeded["ok"].id, seeded["month"]
    _past_job(db, ok, month, status="failed", job_status="done_with_errors")
    _past_job(db, two.id, month, status="canceled", job_status="canceled")
    assert set(startup_send.sendable_ids(db, month)) == {ok, two.id}


def test_다른_달에_받은_것은_막지_않는다(db, seeded, two, client):
    from app.services import startup_send

    ok, month = seeded["ok"].id, seeded["month"]
    _past_job(db, ok, _month(-1))
    assert ok in startup_send.sendable_ids(db, month)

    _turn_on(db)
    _make_draft(_login(client), seeded, ids=[ok])
    job = _jobs(db)[-1]
    assert client.post(f"/api/jobs/{job.id}/start").status_code == 200
    assert _by_company(db, job)[ok].status == "pending"
    assert job.status == "queued"


# ── 2. 나가는 순간 ───────────────────────────────────────────────────────────

def test_옛_draft를_시작하면_이미_받은_기업은_건너뛴다(db, seeded, two, client):
    ok, month = seeded["ok"].id, seeded["month"]
    _turn_on(db)
    _make_draft(_login(client), seeded, ids=[ok, two.id])
    [old] = _jobs(db)
    _past_job(db, ok, month)            # 그 뒤 다른 회차로 받았다

    assert client.post(f"/api/jobs/{old.id}/start").status_code == 200
    by = _by_company(db, old)
    assert by[ok].status == "canceled" and "이미 받은" in by[ok].error
    assert by[two.id].status == "pending"
    claimed = _poll(client).json()
    assert [i["id"] for i in claimed["items"]] == [by[two.id].id]


def test_전부_받았으면_옛_draft는_닫힌다(db, seeded, client):
    ok, month = seeded["ok"].id, seeded["month"]
    _turn_on(db)
    _make_draft(_login(client), seeded, ids=[ok])
    [old] = _jobs(db)
    _past_job(db, ok, month)

    answer = client.post(f"/api/jobs/{old.id}/start")
    assert answer.status_code == 200 and answer.json()["requeued"] == 0
    db.expire_all()
    assert old.status == "canceled"
    assert _poll(client).status_code == 204


def test_이어_보내기_재시도_취소분_재발송도_같다(db, seeded, two, client):
    ok, month = seeded["ok"].id, seeded["month"]
    _turn_on(db)
    _make_draft(_login(client), seeded, ids=[ok, two.id])
    [job] = _jobs(db)
    by = _by_company(db, job)
    job.status = "paused"
    by[two.id].status = "failed"
    db.commit()
    _past_job(db, ok, month)
    _past_job(db, two.id, month)

    assert client.post(f"/api/jobs/{job.id}/resume").json()["requeued"] == 0
    assert "이미 받은" in _by_company(db, job)[ok].error
    assert client.post(f"/api/jobs/{job.id}/retry").json()["requeued"] == 0
    by = _by_company(db, job)
    assert by[two.id].status == "canceled" and "이미 받은" in by[two.id].error
    assert client.post(f"/api/jobs/{job.id}/resend-canceled").json()["requeued"] == 0
    assert {i.status for i in _by_company(db, job).values()} == {"canceled"}


def test_예약이_풀릴_때도_같다(db, seeded, two, client):
    from app import clock
    from app.services import scheduled_send

    ok, month = seeded["ok"].id, seeded["month"]
    _turn_on(db)
    _make_draft(_login(client), seeded, ids=[ok, two.id])
    [job] = _jobs(db)
    at = scheduled_send._aware(clock.now()).replace(hour=11, minute=0, second=0,
                                                   microsecond=0)
    job.scheduled_at = at.isoformat(timespec="seconds")
    db.commit()
    _past_job(db, ok, month)

    assert scheduled_send.release(db, job, at + timedelta(minutes=1))
    by = _by_company(db, job)
    assert by[ok].status == "canceled" and by[two.id].status == "pending"
    assert job.status == "queued"


def test_다른_회차에서_나가는_중이면_빼고_draft는_안_센다(db, seeded, two, client):
    """둘 다 큐에 서면 둘 다 이 확인을 이미 지난 뒤라 둘 다 나간다 — 먼저 큐에 선
    회차의 대기도 받은 것으로 친다. 아직 안 누른 draft 는 안 센다."""
    ok = seeded["ok"].id
    _turn_on(db)
    _login(client)
    _make_draft(client, seeded, ids=[ok])
    _make_draft(client, seeded, ids=[ok, two.id])
    first, second = _jobs(db)

    client.post(f"/api/jobs/{first.id}/start")        # 둘째는 아직 draft
    assert _by_company(db, first)[ok].status == "pending"
    client.post(f"/api/jobs/{second.id}/start")       # 첫째가 큐에 서 있다
    by = _by_company(db, second)
    assert by[ok].status == "canceled" and f"#{first.id} 회차로 나가는 중" in by[ok].error
    assert by[two.id].status == "pending"


def test_한_회차에_같은_기업이_두_줄이면_앞_줄만(db, seeded, client):
    ok = seeded["ok"].id
    _turn_on(db)
    _make_draft(_login(client), seeded, ids=[ok, ok])
    [job] = _jobs(db)
    client.post(f"/api/jobs/{job.id}/start")
    db.expire_all()
    assert [i.status for i in job.items] == ["pending", "canceled"]


# ── 3. A5 ────────────────────────────────────────────────────────────────────

def test_A5_회차는_그대로_나가고_나간_뒤엔_두_확인이_같은_답(db, seeded):
    from app.services import scheduled_send, startup_monthly, startup_send
    from tests.test_auto_startup_monthly import _on, _run

    ok, month = seeded["ok"].id, seeded["month"]
    _turn_on(db)
    _on(db)
    assert _run(db)["status"] == "ready"
    [job] = _jobs(db)
    # 아무도 안 받은 달 — 새 확인이 A5 회차를 건드리지 않는다.
    assert scheduled_send.release(db, job, scheduled_send.scheduled_at(job)
                                  + timedelta(minutes=1))
    db.expire_all()
    assert job.status == "queued" and [i.status for i in job.items] == ["pending"]

    job.items[0].status = "sent"
    job.items[0].sent_at = f"{month}-20T11:00:00+09:00"
    db.commit()
    # A5 의 회차 단위 확인(기존)과 기업 단위 확인(새)이 같은 달 · 같은 회차를 본다.
    assert startup_monthly.month_job(db, month).id == job.id
    assert startup_monthly.received(db, month)[ok].job_id == job.id
    assert ok not in startup_send.sendable_ids(db, month)
