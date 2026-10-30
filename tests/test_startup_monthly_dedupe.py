"""스타트업 월간 발송 — **같은 달에 이미 받은 기업에 모르고 다시 나가지 않는다.**

10/30 에 취소된 회차에서 9곳이 나간 뒤 같은 40곳으로 새 회차가 서서, 그 9곳에
같은 글이 20분 간격으로 다시 나갔다. 대기 목록도 나가는 순간도 "이 달에 이미 보낸
기업" 을 보지 않았다. 판정은 `startup_monthly.received` 하나다.

**막지는 않는다**(사용자 결정 — 잘못 보내고 지웠을 수도 있다).

1. 대기 목록 — 이미 보낸(sent) 기업은 `이번 달 보냄(날짜)` 로 **꺼진 채** 선다
   (비활성 아님, `data-sent-this-month`). 확인 값(`resend_ids`)이 있어야 들어간다.
   실패 · 취소만 있으면 켜진 채다.
2. 나가는 순간 — [발송 시작] · 예약 · 이어 보내기 · 재시도 · 취소분 재발송 모두
   **회차를 세운 뒤에 생긴** 같은 달 발송과 겹치는 건만 사유를 적어 취소한다.
   세울 때 이미 있던 발송은 사람이 확인하고 넣은 것이라 그대로 나간다.
3. 다른 달이면 상관없다. A5 는 제 확인 그대로이고 결과가 같다.

이름은 전부 지어낸 값이다 — 저장소가 공개다.
"""
from __future__ import annotations

import re
from datetime import timedelta
from urllib.parse import unquote

import pytest

from tests.test_startup_monthly_send import (  # noqa: F401 - 픽스처를 함께 쓴다
    _jobs, _login, _month, _poll, _turn_on, seeded)

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


def _later() -> str:
    """지금 세운 회차보다 **뒤**의 시각(같은 초면 뒤가 아니다)."""
    from app import clock

    return (clock.now() + timedelta(minutes=1)).isoformat(timespec="seconds")


def _past_job(db, company_id, month, *, status="sent", job_status="done", sent_at=None):
    """그 달치 회차 하나를 바로 심는다 — 회차명에 달이 적힌다(화면의 기본 이름).
    `sent_at` 이 없으면 그 달 1일 아침(어느 회차보다 **앞**)."""
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
                    sent_at=(sent_at or f"{month}-01T09:00:00+09:00")
                    if status == "sent" else None))
    db.commit()
    return job


def _draft(client, month, ids, resend=()):
    """[대기 목록 만들기] — 화면의 폼이 보내는 값 그대로(`resend_ids` 는 확인 창의 값)."""
    return client.post("/deals/startup-ir/send", follow_redirects=False, data={
        "month": month, "company_ids": list(ids), "resend_ids": list(resend),
        "title": f"검사 회차 ({month})"})


def _by_company(db, job):
    db.expire_all()
    return {i.ir_company_id: i for i in job.items}


def _box(page, company_id):
    """그 기업 줄의 체크칸 태그(속성까지)."""
    found = re.search(r'<input type="checkbox" name="company_ids" value="%d"[^>]*>'
                      % company_id, page)
    assert found, f"{company_id} 줄의 체크칸이 없다"
    return found.group(0)


# ── 1. 대기 목록 ─────────────────────────────────────────────────────────────

def test_이번_달_보낸_기업은_꺼진_채로_서고_전체_선택_표시를_단다(db, seeded, two, client):
    from app.services import startup_send

    ok, month = seeded["ok"].id, seeded["month"]
    _turn_on(db)
    _past_job(db, ok, month)

    page = _login(client).get("/deals/startup-ir").text
    sent = _box(page, ok)
    assert f'data-sent-this-month="{month[5:7]}/01"' in sent
    assert "checked" not in sent and "disabled" not in sent      # 꺼져 있되 막지 않는다
    assert f"이번 달 보냄({month[5:7]}/01)" in page
    assert re.search(r'name="resend_ids" value="%d" disabled' % ok, page)
    assert "checked" in _box(page, two.id)
    assert "data-sent-this-month" not in _box(page, two.id)
    assert "이미 보냄 <b>1곳</b>" in page
    assert "1곳 대기 목록 만들기" in page                         # 처음부터 켜진 수
    # A5 · 딜 제안 관리 링크가 읽는 대상은 그대로다(막지 않는다).
    assert set(startup_send.sendable_ids(db, month)) == {ok, two.id}


def test_확인_값이_없으면_빼고_있으면_넣는다(db, seeded, two, client):
    ok, month = seeded["ok"].id, seeded["month"]
    _turn_on(db)
    _past_job(db, ok, month)
    _login(client)

    _draft(client, month, [ok, two.id])                  # 전체 선택 · 오래된 탭
    assert [i.ir_company_id for i in _jobs(db)[-1].items] == [two.id]

    back = _draft(client, month, [ok])
    assert "이미 받은 기업만 골랐습니다" in unquote(back.headers["location"])

    _draft(client, month, [ok, two.id], resend=[ok])     # 묻는 창에서 [확인]
    assert [i.ir_company_id for i in _jobs(db)[-1].items] == [ok, two.id]


def test_실패나_취소만_있으면_켜진_채다(db, seeded, two, client):
    from app.services import startup_monthly

    ok, month = seeded["ok"].id, seeded["month"]
    _turn_on(db)
    _past_job(db, ok, month, status="failed", job_status="done_with_errors")
    _past_job(db, two.id, month, status="canceled", job_status="canceled")
    assert startup_monthly.received(db, month) == {}
    page = _login(client).get("/deals/startup-ir").text
    for cid in (ok, two.id):
        assert "checked" in _box(page, cid) and "data-sent-this-month" not in _box(page, cid)


def test_다른_달에_받은_것은_상관없다(db, seeded, client):
    ok, month = seeded["ok"].id, seeded["month"]
    _past_job(db, ok, _month(-1))
    _turn_on(db)
    page = _login(client).get("/deals/startup-ir").text
    assert "checked" in _box(page, ok)

    _draft(client, month, [ok])
    job = _jobs(db)[-1]
    _past_job(db, ok, _month(-1), sent_at=_later())       # 세운 뒤라도 다른 달
    assert client.post(f"/api/jobs/{job.id}/start").status_code == 200
    assert _by_company(db, job)[ok].status == "pending"
    assert job.status == "queued"


# ── 2. 나가는 순간 ───────────────────────────────────────────────────────────

def test_세운_뒤에_받은_기업은_옛_draft를_시작해도_건너뛴다(db, seeded, two, client):
    ok, month = seeded["ok"].id, seeded["month"]
    _turn_on(db)
    _draft(_login(client), month, [ok, two.id])
    [old] = _jobs(db)
    _past_job(db, ok, month, sent_at=_later())           # 그 뒤 다른 회차로 받았다

    assert client.post(f"/api/jobs/{old.id}/start").status_code == 200
    by = _by_company(db, old)
    assert by[ok].status == "canceled" and "세운 뒤" in by[ok].error
    assert by[two.id].status == "pending"
    claimed = _poll(client).json()
    assert [i["id"] for i in claimed["items"]] == [by[two.id].id]


def test_세우기_전에_받은_기업은_확인하고_넣었으니_그대로_나간다(db, seeded, client):
    ok, month = seeded["ok"].id, seeded["month"]
    _turn_on(db)
    _past_job(db, ok, month)                             # 이미 받은 뒤에
    _draft(_login(client), month, [ok], resend=[ok])     # 묻는 창에서 [확인]
    job = _jobs(db)[-1]

    assert client.post(f"/api/jobs/{job.id}/start").json()["requeued"] == 1
    assert _by_company(db, job)[ok].status == "pending"


def test_전부_세운_뒤에_받았으면_옛_draft는_닫힌다(db, seeded, client):
    ok, month = seeded["ok"].id, seeded["month"]
    _turn_on(db)
    _draft(_login(client), month, [ok])
    [old] = _jobs(db)
    _past_job(db, ok, month, sent_at=_later())

    answer = client.post(f"/api/jobs/{old.id}/start")
    assert answer.status_code == 200 and answer.json()["requeued"] == 0
    db.expire_all()
    assert old.status == "canceled"
    assert _poll(client).status_code == 204


def test_이어_보내기_재시도_취소분_재발송도_같다(db, seeded, two, client):
    ok, month = seeded["ok"].id, seeded["month"]
    _turn_on(db)
    _draft(_login(client), month, [ok, two.id])
    [job] = _jobs(db)
    by = _by_company(db, job)
    job.status = "paused"
    by[two.id].status = "failed"
    db.commit()
    _past_job(db, ok, month, sent_at=_later())
    _past_job(db, two.id, month, sent_at=_later())

    assert client.post(f"/api/jobs/{job.id}/resume").json()["requeued"] == 0
    assert "세운 뒤" in _by_company(db, job)[ok].error
    assert client.post(f"/api/jobs/{job.id}/retry").json()["requeued"] == 0
    by = _by_company(db, job)
    assert by[two.id].status == "canceled" and "세운 뒤" in by[two.id].error
    assert client.post(f"/api/jobs/{job.id}/resend-canceled").json()["requeued"] == 0
    assert {i.status for i in _by_company(db, job).values()} == {"canceled"}


def test_예약이_풀릴_때도_같다(db, seeded, two, client):
    from app import clock
    from app.services import scheduled_send

    ok, month = seeded["ok"].id, seeded["month"]
    _turn_on(db)
    _draft(_login(client), month, [ok, two.id])
    [job] = _jobs(db)
    # 보내는 시간(09~19시) 안의 시각 — `release` 는 넘겨준 `now` 로만 판단한다.
    at = scheduled_send._aware(clock.now()).replace(hour=11, minute=0, second=0,
                                                   microsecond=0)
    job.scheduled_at = at.isoformat(timespec="seconds")
    db.commit()
    _past_job(db, ok, month, sent_at=_later())

    assert scheduled_send.release(db, job, at + timedelta(minutes=1))
    by = _by_company(db, job)
    assert by[ok].status == "canceled" and by[two.id].status == "pending"
    assert job.status == "queued"


def test_다른_회차에서_나가는_중이면_빼고_draft는_안_센다(db, seeded, two, client):
    """둘 다 큐에 서면 둘 다 이 확인을 이미 지난 뒤라 둘 다 나간다 — 먼저 큐에 선
    회차의 대기도 받은 것으로 친다. 아직 안 누른 draft 는 안 센다."""
    ok, month = seeded["ok"].id, seeded["month"]
    _turn_on(db)
    _login(client)
    _draft(client, month, [ok])
    _draft(client, month, [ok, two.id])
    first, second = _jobs(db)

    client.post(f"/api/jobs/{first.id}/start")        # 둘째는 아직 draft
    assert _by_company(db, first)[ok].status == "pending"
    client.post(f"/api/jobs/{second.id}/start")       # 첫째가 큐에 서 있다
    by = _by_company(db, second)
    assert by[ok].status == "canceled" and f"#{first.id} 회차로 나가는 중" in by[ok].error
    assert by[two.id].status == "pending"


def test_한_회차에_같은_기업이_두_줄이면_앞_줄만(db, seeded, client):
    ok, month = seeded["ok"].id, seeded["month"]
    _turn_on(db)
    _draft(_login(client), month, [ok, ok])
    [job] = _jobs(db)
    client.post(f"/api/jobs/{job.id}/start")
    db.expire_all()
    assert [i.status for i in job.items] == ["pending", "canceled"]


# ── 3. A5 ────────────────────────────────────────────────────────────────────

def test_A5_회차는_그대로_나가고_나간_뒤엔_두_확인이_같은_회차를_본다(db, seeded):
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
    # A5 가 읽는 대상(`sendable_ids`)은 그대로다 — A5 는 제 확인으로 그 달을 건너뛴다.
    assert ok in startup_send.sendable_ids(db, month)
