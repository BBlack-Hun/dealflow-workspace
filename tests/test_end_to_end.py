"""통합 시나리오 — 딜소개 한 회차가 끝까지 흐르는지.

각 화면은 따로 테스트하지만, **이어지는 지점**에서 깨진 적이 여러 번 있다.
잡 종류를 안 남겨 후속이 안 멈췄고, 이름이 어긋나 요청이 안 닫혔다.
그래서 한 회차를 처음부터 끝까지 한 번에 흘려 본다.

    딜소개 발송 → 성공 보고 → 리마인드 예약
      → IR 요청 옴 → 후속 자동 중단
      → 자료 전달 발송 → 요청 자동 닫힘
      → 미팅 등록 → 완료 → 열흘 뒤 결과 문의 예약
      → 오늘 할 일에 그대로 뜬다
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from .conftest import DEMO_PASSWORD


@pytest.fixture()
def stage(client, db, users):
    """보낼 수 있는 상태 하나. 담당자 1명 · 기업 2개."""
    from app.models import (AgentDevice, IrCompany, MessageTemplate,
                            ScheduleRule, SheetOwner, VcContact)

    db.add_all([
        SheetOwner(label="내 명단", user_id=users["u1"].id),
        VcContact(user_id=users["u1"].id, name="홍길동", title="심사역",
                  firm="가나벤처스", source_sheet="내 명단", channel_kakao=1,
                  kakao_room_name="홍길동 심사역님 가나벤처스",
                  room_verified="verified", connect_stage="connected"),
        IrCompany(name="샘플애그", one_liner="B2B 농산물 선도거래",
                  revenue_recent=12, sector_major="애그테크",
                  ir_file_name="샘플애그_IR.pdf"),
        IrCompany(name="샘플메디", one_liner="뇌영상 분석 AI",
                  revenue_recent=4, sector_major="헬스케어",
                  ir_file_name="샘플메디_IR.pdf"),
        MessageTemplate(user_id=None, kind="opening_first",
                        body="안녕하세요, {담당자명} {직함}\n우리브이씨입니다.", is_active=1),
        MessageTemplate(user_id=None, kind="closing_day1",
                        body="핵심 딜 {개수}개사 공유드립니다.", is_active=1),
        MessageTemplate(user_id=None, kind="closing_remind",
                        body="지난번 공유드린 기업들 검토 중이신가요?", is_active=1),
        MessageTemplate(user_id=None, kind="ir_delivery",
                        body="{담당자명} {직함} 안녕하세요.\n{기업목록} IR deck 전달드립니다.",
                        is_active=1),
        ScheduleRule(key="deal_cycle", label="딜소개 회차", kind="monthly_weekday",
                     weekday=2, nth_weeks="1,3", skip_weekend=1),
        ScheduleRule(key="remind", label="리마인드", kind="offset_days",
                     offset_min_days=6, offset_max_days=7, skip_weekend=1),
        ScheduleRule(key="meeting", label="미팅 요청", kind="offset_days",
                     offset_min_days=11, offset_max_days=14, skip_weekend=1),
    ])
    db.commit()

    device = db.query(AgentDevice).filter_by(user_id=users["u1"].id).first()
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    contact = db.query(VcContact).filter_by(name="홍길동").first()
    return {
        "client": client,
        "user": users["u1"],
        "contact_id": contact.id,
        "agri": db.query(IrCompany).filter_by(name="샘플애그").first().id,
        "medi": db.query(IrCompany).filter_by(name="샘플메디").first().id,
        "token": device.token,
    }


def _send(stage, **body) -> int:
    r = stage["client"].post("/api/deals/send", json=body)
    assert r.status_code == 200, r.text
    return r.json()["job_id"]


def _agent_reports_sent(stage, db, job_id) -> None:
    """에이전트가 발송 성공을 보고한 것처럼."""
    from app.models import SendItem

    for item in db.query(SendItem).filter_by(job_id=job_id).all():
        r = stage["client"].post(
            f"/api/agent/items/{item.id}/result",
            headers={"Authorization": f"Bearer {stage['token']}"},
            json={"status": "sent"})
        assert r.status_code == 200, r.text
    db.expire_all()


def test_one_cycle_flows_end_to_end(stage, db):
    from app.models import IrRequest, Meeting, SendItem, SendJob, SendSequence
    from app.services import pipeline

    client = stage["client"]

    # ── ① 딜소개 발송 ────────────────────────────────────────
    job_id = _send(stage, company_ids=[stage["agri"], stage["medi"]],
                   contact_ids=[stage["contact_id"]], title="8월 회차")
    item = db.query(SendItem).filter_by(job_id=job_id).first()
    assert "1)" in item.message and "2)" in item.message   # 기업 목록이 붙는다
    assert "안녕하세요" in item.message                     # 인사말도

    # 아직 성공 보고 전 — 후속이 잡히면 안 된다
    assert db.query(SendSequence).count() == 0

    # ── ② 성공 보고 → 리마인드 예약 ──────────────────────────
    _agent_reports_sent(stage, db, job_id)
    seq = db.query(SendSequence).one()
    assert seq.status == "active"
    assert seq.next_stage == 2
    gap = (date.fromisoformat(seq.next_due_date) - date.today()).days
    assert 6 <= gap <= 9                                   # 6~7일 + 주말 보정

    # 후속 화면에 예약으로 뜬다
    assert "홍길동" in client.get("/followups").text

    # ── ③ IR 요청이 옴 → 후속 자동 중단 ─────────────────────
    client.post("/ir/requests", follow_redirects=False, data={
        "contact_id": stage["contact_id"], "company_name": "샘플애그"})
    db.expire_all()
    seq = db.query(SendSequence).one()
    assert seq.status == "responded", "답이 왔는데 리마인드가 살아 있다"
    assert seq.next_due_date is None

    request_row = db.query(IrRequest).one()
    assert request_row.status == "open"
    assert request_row.company_id == stage["agri"]         # 이름으로 기업을 찾았다

    # ── ④ 자료 전달 → 요청 자동 닫힘 ────────────────────────
    ir_job = _send(stage, company_ids=[stage["agri"]],
                   contact_ids=[stage["contact_id"]], mode="ir")
    assert db.get(SendJob, ir_job).kind == "ir_delivery"

    ir_item = db.query(SendItem).filter_by(job_id=ir_job).first()
    assert "1번 기업 샘플애그" in ir_item.message           # 지난 회차 번호로 짚는다
    assert "1)" not in ir_item.message                     # 목록은 다시 붙이지 않는다

    _agent_reports_sent(stage, db, ir_job)
    assert db.query(IrRequest).one().status == "delivered"

    # ── ⑤ 미팅 등록 → 완료 → 열흘 뒤 결과 문의 ──────────────
    client.post("/ir/meetings", follow_redirects=False, data={
        "contact_id": stage["contact_id"],
        "scheduled_at": date.today().isoformat(), "kind": "first"})
    db.expire_all()
    meeting = db.query(Meeting).one()

    client.post(f"/ir/meetings/{meeting.id}/done", follow_redirects=False,
                data={"outcome": "reviewing"})
    db.expire_all()
    meeting = db.query(Meeting).one()
    assert meeting.status == "done"
    assert meeting.followup_due == pipeline.followup_date(date.today()).isoformat()

    # ── ⑥ 오늘 할 일에 그대로 뜬다 ──────────────────────────
    meeting.followup_due = date.today().isoformat()        # 열흘 뒤가 됐다고 치고
    db.commit()
    body = client.get("/todo").text
    assert "미팅 결과 문의" in body


def test_failed_send_schedules_nothing(stage, db):
    """실패한 건까지 후속이 잡히면, 받은 적 없는 사람에게 '지난번 공유드린'이 나간다."""
    from app.models import SendItem, SendSequence

    job_id = _send(stage, company_ids=[stage["agri"]],
                   contact_ids=[stage["contact_id"]])
    item = db.query(SendItem).filter_by(job_id=job_id).first()
    stage["client"].post(
        f"/api/agent/items/{item.id}/result",
        headers={"Authorization": f"Bearer {stage['token']}"},
        json={"status": "failed", "error": "room_not_found"})
    db.expire_all()
    assert db.query(SendSequence).count() == 0


def test_follow_up_send_advances_the_sequence(stage, db):
    """리마인드를 보내면 다음은 미팅 요청이 잡힌다."""
    from app.models import SendSequence

    _agent_reports_sent(stage, db, _send(
        stage, company_ids=[stage["agri"]], contact_ids=[stage["contact_id"]]))

    remind_job = _send(stage, company_ids=[], contact_ids=[stage["contact_id"]],
                       mode="remind")
    _agent_reports_sent(stage, db, remind_job)

    seq = db.query(SendSequence).one()
    assert seq.stage == 2
    assert seq.next_stage == 3
    gap = (date.fromisoformat(seq.next_due_date) - date.today()).days
    assert 11 <= gap <= 16


def test_test_room_redirects_every_send(stage, db, monkeypatch):
    """테스트 모드에서는 실제 담당자 방으로 나가면 안 된다."""
    from app import config
    from app.models import SendItem
    from app.routers import deals

    monkeypatch.setattr(config, "TEST_ROOM", "나와의 채팅")
    monkeypatch.setattr(deals.config, "TEST_ROOM", "나와의 채팅")

    job_id = _send(stage, company_ids=[stage["agri"]],
                   contact_ids=[stage["contact_id"]])
    item = db.query(SendItem).filter_by(job_id=job_id).first()
    assert item.room_name == "나와의 채팅"
    assert "테스트 발송" in item.message           # 원래 누구에게 갈 문구였는지 남는다
    assert "홍길동 심사역님 가나벤처스" in item.message


def test_every_screen_opens(stage):
    """한 화면이라도 죽으면 회차 당일에 손을 못 쓴다."""
    client = stage["client"]
    for path in ("/", "/todo", "/readiness", "/deals", "/followups", "/ir",
                 "/contacts", "/companies", "/templates", "/setup"):
        assert client.get(path).status_code == 200, path
