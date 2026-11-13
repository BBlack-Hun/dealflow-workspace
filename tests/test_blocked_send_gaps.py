"""`딜소개 불가`(계약여부 · 기업명 꼬리표)를 **나가는 모든 문**에서 다시 본다 — #530 의 후속.

#530 은 세운 뒤 막힌 기업을 [발송 시작] · 예약 풀림 · 재시도에서 다시 봤다
(`jobs._drop_blocked_companies`). 그 뒤에 남은 빈틈 셋이다 — 계약 `blocked` 도 똑같이
새던 자리다.

1. **딜 소개 · IR 자료 전달 · 스타트업 월간 발송만 본다.** 다른 종류의 회차는 그대로
   나간다. 스타트업 월간 발송(A5 · 손 발송)은 처음엔 막지 않았는데, 사용자 결정
   (2026-11-13 — 딜소개 불가면 월간 보고도 막는다, 유료여도)으로 **그 기업의 건만**
   취소한다(건 하나가 기업 하나). 일부 나간 딜 소개 회차를 이어 보내면 **나간 건은
   그대로**, 대기 건만 취소된다. 예약이 풀릴 때 전부 빠졌으면 "예약 발송 — N명" 이라고
   말하지 않는다.
2. **발송기가 회차를 받아 갈 때 다시 본다**(`agent_api.poll`). 19시 이후 · PC 꺼짐 ·
   하루 한도(`_settle` 이 다시 큐에 세운다)로 `queued` 인 채 밤을 넘긴 회차가 그사이 막힌
   기업을 싣고 다음 날 그대로 나가지 않는다.
3. **채널 TOP 자동화**는 아침에 고르고 13:30 에 풀린다 — 풀릴 때 다시 본다(`still_ok`).

이름은 전부 지어낸 값이다(공개 저장소). 시각은 실제 오늘과 상관없는 날로 못박는다.
"""
from __future__ import annotations

import logging
from datetime import datetime

import pytest
from sqlalchemy import select

from tests.conftest import DEMO_PASSWORD, DEMO_TOKEN, auth

#: 발송 프로그램이 밝히는 종류(`agent/main.py: SUPPORTED_KINDS`) — 모르는 종류는 안
#: 내주므로, 빠지면 "안 나간다" 를 틀린 이유로 통과한다.
KINDS = "deal_intro,ir_delivery,sourcing_intro,verify_room,test_send,startup_ir,startup_msg"

#: 2099-03-12 는 목요일이다. 실제 오늘이 언제든 이 날이 '지금' 일 수 없다.
DAY = (2099, 3, 12)
AT = "2099-03-12T14:00"


def _at(hour, minute=0, day=DAY):
    return datetime(*day, hour, minute).astimezone()


def _freeze(monkeypatch, when):
    from app import clock

    monkeypatch.setattr(clock, "now", lambda: when)


def _poll(client, token=DEMO_TOKEN):
    return client.get("/api/agent/poll", params={"kinds": KINDS, "cap": 60, "files": 1},
                      headers=auth(token))


def _report_all(client, data, token=DEMO_TOKEN):
    """받은 건을 전부 `sent` 로 보고하고 회분을 끝냈다고 알린다 — 발송기가 하는 그대로."""
    for item in data["items"]:
        client.post(f"/api/agent/items/{item['id']}/result",
                    json={"status": "sent"}, headers=auth(token))
    return client.post(f"/api/agent/jobs/{data['job_id']}/status",
                       json={"status": "done"}, headers=auth(token))


def _fresh(db, job_id):
    from app.models import SendJob

    db.expire_all()
    return db.get(SendJob, job_id)


def _block(db, company, how):
    """세운 뒤에 막힌다 — 이름 꼬리표든 계약여부든."""
    if how == "name":
        company.name = f"{company.name} [딜소개 불가]"
    else:
        company.contract_status = "blocked"
    db.commit()


def _all_canceled_for_block(items):
    return items and all(i.status == "canceled" and "딜소개 불가" in (i.error or "")
                         for i in items)


# ── 딜 소개 · IR 자료 전달 ────────────────────────────────────────────────────

@pytest.fixture()
def seed(client, db, users):
    """u1 로그인 + 멀쩡한 유료 기업 하나 + 카톡방이 등록된 담당자 셋."""
    from app.models import IrCompany, VcContact

    company = IrCompany(name="샘플하나", contract_status="paid", sector_major="AI",
                        one_liner="샘플하나 한 줄 소개", funding_total="30억",
                        received_at="2026-10-01", ir_file_name="샘플하나_IR.pdf")
    people = [VcContact(user_id=users["u1"].id, name=f"샘플{n}", title="심사역",
                        firm=f"샘플{n}벤처스", group_name="샘플군",
                        connect_stage="connected", status="active",
                        kakao_room_name=f"샘플{n} 심사역님 샘플{n}벤처스",
                        room_verified="verified", channel_kakao=1,
                        source_sheet="샘플 명단")
              for n in ("가", "나", "다")]
    db.add_all([company, *people])
    db.commit()
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    return {"company": company, "contact_ids": [p.id for p in people]}


def _send(client, seed, **over):
    body = {"company_ids": [seed["company"].id], "contact_ids": seed["contact_ids"],
            "title": "샘플 회차", **over}
    res = client.post("/api/deals/send", json=body)
    assert res.status_code == 200, res.text
    return res.json()["job_id"]


# 2. 발송기가 받아 갈 때 ─────────────────────────────────────────────────────

@pytest.mark.parametrize("how", ["name", "contract"])
@pytest.mark.parametrize("mode", ["deal", "ir"])
def test_큐에_선_회차는_발송기에_내주기_직전에_다시_본다(client, db, seed, mode, how):
    """19시 이후 · PC 꺼짐으로 `queued` 인 채 밤을 넘긴 회차 — 그사이 막혔으면 안 내준다."""
    job_id = _send(client, seed, mode=mode)
    assert _fresh(db, job_id).status == "queued"
    _block(db, seed["company"], how)

    assert _poll(client).status_code == 204
    job = _fresh(db, job_id)
    assert job.status == "canceled" and job.finished_at
    assert _all_canceled_for_block(job.items)
    # 닫힌 회차는 다시 집히지 않는다.
    assert _poll(client).status_code == 204


def test_막히지_않은_회차는_그대로_내준다(client, db, seed):
    job_id = _send(client, seed)
    got = _poll(client)
    assert got.status_code == 200 and got.json()["job_id"] == job_id
    assert len(got.json()["items"]) == 3


def test_하루_한도로_다시_큐에_선_회차도_다음_날_내주기_직전에_다시_본다(
        client, db, users, seed, monkeypatch):
    """한도에 걸려 앞 한 명만 나가고 `_settle` 이 다시 큐에 세웠다 — 밤사이 기업이 막혔다.

    다음 날 받아 가는 순간 남은 대기 건은 취소되고, **이미 나간 건은 그대로**다.
    """
    _freeze(monkeypatch, _at(10, 0))
    users["u1"].daily_send_cap = 1
    db.commit()
    # 시계를 옮겼으니 다시 들어간다(세션 시각이 그 시계를 따른다).
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    job_id = _send(client, seed)

    first = _poll(client).json()
    assert len(first["items"]) == 1
    settled = _report_all(client, first)
    assert settled.json()["status"] == "queued" and settled.json()["pending"] == 2

    _block(db, seed["company"], "name")
    _freeze(monkeypatch, _at(10, 0, day=(2099, 3, 13)))
    assert _poll(client).status_code == 204

    job = _fresh(db, job_id)
    sent_id = first["items"][0]["id"]
    assert [i.status for i in job.items if i.id == sent_id] == ["sent"]
    assert _all_canceled_for_block([i for i in job.items if i.id != sent_id])
    assert job.status == "canceled"
    assert job.sent == 1


# 1. 다시 살리는 길 · 예약 풀림 ──────────────────────────────────────────────

def test_일부_나간_딜소개를_이어_보내도_나간_건은_그대로_대기_건만_취소된다(client, db, seed):
    from app.clock import now_iso

    job_id = _send(client, seed)
    job = _fresh(db, job_id)
    sent, failed, waiting = job.items
    sent.status, sent.sent_at = "sent", now_iso()
    failed.status, failed.error = "failed", "방을 찾지 못했습니다"
    job.status = "paused"
    db.commit()
    _block(db, seed["company"], "name")

    # [이어 보내기] — 대기 건만 되살리는 자리.
    res = client.post(f"/api/jobs/{job_id}/resume")
    assert res.status_code == 200 and res.json()["requeued"] == 0, res.text
    job = _fresh(db, job_id)
    by = {i.id: i for i in job.items}
    assert by[sent.id].status == "sent"
    assert by[failed.id].status == "failed"
    assert _all_canceled_for_block([by[waiting.id]])
    assert job.status != "queued"

    # [실패 재시도] — 실패 건이 대기로 돌았다가 같은 자리에서 빠진다.
    res = client.post(f"/api/jobs/{job_id}/retry")
    assert res.status_code == 200 and res.json()["requeued"] == 0, res.text
    job = _fresh(db, job_id)
    by = {i.id: i for i in job.items}
    assert by[sent.id].status == "sent" and by[sent.id].sent_at
    assert _all_canceled_for_block([by[failed.id], by[waiting.id]])
    assert job.status != "queued"
    assert _poll(client).status_code == 204


@pytest.mark.parametrize("how", ["name", "contract"])
def test_예약이_풀릴_때_막혔으면_안_나가고_보냈다고_하지도_않는다(client, db, seed, caplog, how):
    from app.services import scheduled_send

    job_id = _send(client, seed, scheduled_at=AT)
    _block(db, seed["company"], how)

    with caplog.at_level(logging.INFO, logger="app.services.scheduled_send"):
        result = scheduled_send.run_once(db, now=datetime(2099, 3, 12, 14, 0))
    assert result == {"released": [], "count": 0}
    assert "예약 발송 — 회차" not in caplog.text
    assert "보낼 건이 남지 않아" in caplog.text

    job = _fresh(db, job_id)
    assert job.status == "canceled" and job.released_at
    assert _all_canceled_for_block(job.items)
    assert _poll(client).status_code == 204


def test_예약이_풀리면_실제로_올린_수를_말한다(client, db, seed, caplog):
    from app.services import scheduled_send

    job_id = _send(client, seed, scheduled_at=AT)
    with caplog.at_level(logging.INFO, logger="app.services.scheduled_send"):
        result = scheduled_send.run_once(db, now=datetime(2099, 3, 12, 14, 0))
    assert result["released"] == [job_id]
    assert f"예약 발송 — 회차 {job_id}, 3명" in caplog.text
    assert _fresh(db, job_id).status == "queued"


# 1. 다른 종류의 회차는 그대로 ────────────────────────────────────────────────

@pytest.mark.parametrize("kind,dropped", [
    ("deal_intro", True), ("ir_delivery", True),
    ("startup_ir", False), ("startup_msg", False), ("sourcing_intro", False),
    ("test_send", False), ("verify_room", False),
])
def test_실린_기업으로_막는_것은_딜소개와_IR_전달뿐이다(db, users, kind, dropped):
    """회차 **묶음**에 막힌 기업 줄이 있어도 **딜 소개 · IR 자료 전달**만 취소한다.
    스타트업 월간 발송은 묶음이 아니라 건의 기업(`ir_company_id`)을 본다 — 아래
    `test_꼬리표_붙은_유료_기업의_월간_발송은_나가기_전에_빠진다`."""
    from app.models import DealBatch, DealBatchCompany, IrCompany, SendItem, SendJob
    from app.routers.jobs import _drop_blocked_companies

    company = IrCompany(name="샘플둘 [딜소개 불가]", contract_status="paid")
    batch = DealBatch(user_id=1, title="샘플 회차", sent_date="2099-03-12",
                      cycle_type="adhoc")
    db.add_all([company, batch])
    db.flush()
    db.add(DealBatchCompany(batch_id=batch.id, company_id=company.id, position=1))
    job = SendJob(user_id=1, kind=kind, batch_id=batch.id, status="draft", total=1)
    db.add(job)
    db.flush()
    db.add(SendItem(job_id=job.id, room_name="샘플 방", message="-", status="pending"))
    db.commit()

    _drop_blocked_companies(db, job)
    assert job.items[0].status == ("canceled" if dropped else "pending")


@pytest.fixture()
def monthly(client, db, users):
    """스타트업 월간 발송(A5)을 보낼 수 있는 유료 기업 하나 — 그 달 IR 요청이 있다."""
    from app import clock
    from app.models import IrCompany, IrRequest, VcContact
    from app.services import startup_send

    company = IrCompany(name="샘플셋", contract_status="paid",
                        kakao_room_name="샘플셋 대표님")
    contact = VcContact(user_id=1, name="샘플라", firm="샘플라벤처스")
    db.add_all([company, contact])
    db.flush()
    month = clock.today().strftime("%Y-%m")
    db.add(IrRequest(user_id=1, contact_id=contact.id, company_id=company.id,
                     company_name=company.name, requested_at=f"{month}-03"))
    db.commit()
    startup_send.save(db, enabled=True, user_id=1)
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    return {"company": company, "month": month}


def test_꼬리표_붙은_유료_기업의_월간_발송은_나가기_전에_빠진다(client, db, monthly):
    """딜소개 불가면 월간 보고도 막는다(사용자 결정 2026-11-13 — 유료 계약이어도).
    회차를 세운 뒤 이름에 꼬리표가 붙으면 [발송 시작] 에서 그 건이 까닭과 함께 빠진다."""
    from app.models import SendJob

    made = client.post("/deals/startup-ir/send", follow_redirects=False, data={
        "month": monthly["month"], "company_ids": [monthly["company"].id],
        "title": "샘플 월간"})
    assert made.status_code == 303, made.text
    job = db.execute(select(SendJob)).scalars().one()
    assert job.kind == "startup_ir" and job.status == "draft"
    _block(db, monthly["company"], "name")

    res = client.post(f"/api/jobs/{job.id}/start")
    assert res.status_code == 200 and res.json()["requeued"] == 0, res.text
    job = _fresh(db, job.id)
    assert job.status == "canceled"
    assert _all_canceled_for_block(job.items)
    assert _poll(client).status_code == 204


def test_발송기가_받아_갈_때_막힌_기업의_월간_건만_빼고_남긴다(client, db, monthly):
    """큐에 선 월간 회차가 받아 가기 전에 한 기업이 막히면 **그 건만** 취소되고(커밋된다)
    나머지 기업 건은 그대로 내준다 — 건 하나가 기업 하나라 회차를 통째로 닫지 않는다."""
    from app.models import IrCompany, IrRequest, SendJob, VcContact

    other = IrCompany(name="샘플넷째", contract_status="free",
                      kakao_room_name="샘플넷째 대표님")
    contact = VcContact(user_id=1, name="샘플마", firm="샘플마파트너스")
    db.add_all([other, contact])
    db.flush()
    db.add(IrRequest(user_id=1, contact_id=contact.id, company_id=other.id,
                     company_name=other.name, requested_at=f"{monthly['month']}-04"))
    db.commit()
    made = client.post("/deals/startup-ir/send", follow_redirects=False, data={
        "month": monthly["month"], "company_ids": [monthly["company"].id, other.id],
        "title": "샘플 월간"})
    assert made.status_code == 303, made.text
    job = db.execute(select(SendJob)).scalars().one()
    assert client.post(f"/api/jobs/{job.id}/start").json()["requeued"] == 2
    _block(db, monthly["company"], "name")

    got = _poll(client)
    assert got.status_code == 200 and got.json()["job_id"] == job.id
    assert [i["room_name"] for i in got.json()["items"]] == ["샘플넷째 대표님"]
    job = _fresh(db, job.id)
    by_company = {i.ir_company_id: i for i in job.items}
    assert by_company[monthly["company"].id].status == "canceled"
    assert "딜소개 불가" in by_company[monthly["company"].id].error
    assert by_company[other.id].status == "pending"


# ── 3. 채널 TOP 자동화 ────────────────────────────────────────────────────────

ROOMS = ["샘플 채널 하나", "샘플 채널 둘"]
WED = datetime(2026, 10, 14, 9, 0)        # 2026 년 42주차 수요일


@pytest.fixture()
def top_deals(db, users):
    from app.models import AutoSendSetting, IrCompany

    users["u2"].role = "admin"
    db.add(AutoSendSetting(kind="startup_ir", enabled=1, user_id=users["u2"].id))
    rows = {key: IrCompany(name=name, is_top_deal=1, received_at=received,
                           contract_status="paid", sector_major="AI",
                           one_liner=f"{name} 한 줄 소개", funding_total="30억")
            for key, name, received in (("first", "샘플넷", "2026-10-10"),
                                        ("second", "샘플다섯", "2026-10-05"))}
    db.add_all(rows.values())
    db.commit()
    return rows


def _top_jobs(db):
    from app.models import SendJob

    db.expire_all()
    return db.execute(select(SendJob).order_by(SendJob.id)).scalars().all()


@pytest.mark.parametrize("how", ["name", "contract", None])
def test_채널_TOP_은_풀릴_때_다시_보고_막힌_기업이_실린_회차를_뺀다(db, users, top_deals, how):
    """아침 9시에 고른 뒤 13:30 전에 막혔다 — 그 방의 한 통이 통째로 빠지고 까닭이 남는다.

    한 통에 여러 곳이 실려 한 곳만 뺄 수 없다. 막히지 않았으면 그대로 풀린다.
    """
    from app.services import automation, scheduled_send
    from app.services import automation_runner as runner

    runner.save_params(db, automation.CHANNEL_TOP, {"rooms": "\n".join(ROOMS)})
    automation.save(db, automation.CHANNEL_TOP, enabled=True, user_id=None,
                    test_mode=False, test_room="샘플 시험방")
    assert runner.run_once(db, automation.CHANNEL_TOP, WED.astimezone())["status"] == "ready"
    jobs = [j for j in _top_jobs(db) if j.status == "draft"]
    assert len(jobs) == 2
    assert all("샘플넷" in j.items[0].message for j in jobs)
    if how:
        _block(db, top_deals["first"], how)

    first = jobs[0]
    released = scheduled_send.run_once(db, now=scheduled_send.scheduled_at(first))
    first = _fresh(db, first.id)
    if how is None:
        assert released["released"] == [first.id]
        assert first.status == "queued"
        return
    assert released["released"] == []
    assert first.status == "canceled"
    item = first.items[0]
    assert item.status == "canceled"
    assert "샘플넷" in item.error and "딜소개 불가" in item.error, item.error


def test_채널_TOP_기록에_기업이_없으면_막지_않는다(db):
    """기업 줄이 없는 기록(옛 줄 · 기업이 지워짐)은 이 판정으로 빼지 않는다."""
    from app.models import AutomationSend
    from app.services.automations import channel_top

    assert channel_top.still_ok(db, AutomationSend(automation="channel_top",
                                                   ref="week:1:방")) == ""
    assert channel_top.still_ok(db, AutomationSend(automation="channel_top",
                                                   ref="week:1:방:999",
                                                   company_id=999)) == ""
