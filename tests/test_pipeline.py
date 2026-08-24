"""IR 요청 · 미팅 — 딜소개 뒤에 오는 일.

받은 요청을 놓치면 그 회차에서 가장 뜨거운 반응을 흘려보낸다.
여기서 지키려는 것.

1. **답이 왔으면 리마인드를 멈춘다.** IR 요청이 왔는데 "지난번 공유드린 기업들
   검토 중…"이 또 나가면 상대는 이쪽이 자기 답을 못 봤다고 생각한다.
2. **미팅이 끝나면 열흘 뒤 결과를 물을 날이 잡힌다.** 사람이 기억하지 않아도 되게.
3. **남의 요청·미팅은 건드릴 수 없다.**
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from .conftest import DEMO_PASSWORD


@pytest.fixture()
def logged(client, users):
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    return client


@pytest.fixture()
def seed(db, users):
    from app.models import IrCompany, SheetOwner, VcContact

    db.add_all([
        SheetOwner(label="내 명단", user_id=users["u1"].id),
        VcContact(user_id=users["u1"].id, name="홍길동", title="심사역",
                  firm="가나벤처스", source_sheet="내 명단",
                  connect_stage="connected", kakao_room_name="홍길동 방"),
        IrCompany(name="샘플애그", one_liner="B2B 농산물", revenue_recent=12,
                  ir_drive_url="https://drive.google.com/file/d/x/view"),
    ])
    db.commit()
    return {
        "contact_id": db.query(VcContact).filter_by(name="홍길동").first().id,
        "user_id": users["u1"].id,
    }


# --- IR 요청 ----------------------------------------------------------------

def test_request_matches_a_known_company(logged, db, seed):
    from app.models import IrCompany, IrRequest

    logged.post("/ir/requests", follow_redirects=False, data={
        "contact_id": seed["contact_id"], "company_name": "샘플애그"})
    db.expire_all()
    row = db.query(IrRequest).first()
    assert row.company_id == db.query(IrCompany).filter_by(name="샘플애그").first().id
    assert row.status == "open"


def test_request_keeps_unknown_company_names(logged, db, seed):
    """우리 DB 에 없는 기업이라고 요청을 버리면 요청을 놓친다."""
    from app.models import IrRequest

    logged.post("/ir/requests", follow_redirects=False, data={
        "contact_id": seed["contact_id"], "company_name": "처음보는기업"})
    db.expire_all()
    row = db.query(IrRequest).first()
    assert row.company_id is None
    assert row.company_name == "처음보는기업"


def test_multiple_companies_in_one_go(logged, db, seed):
    """한 번에 여러 기업 자료를 요청받는다 — 줄바꿈으로 적는다."""
    from app.models import IrRequest

    logged.post("/ir/requests", follow_redirects=False, data={
        "contact_id": seed["contact_id"],
        "company_name": "샘플애그\n샘플메디\n샘플페이"})
    db.expire_all()
    assert db.query(IrRequest).count() == 3


def test_request_stops_the_reminder(logged, db, seed):
    """답이 왔는데 리마인드가 또 나가면 안 된다."""
    from app.models import SendSequence

    db.add(SendSequence(user_id=seed["user_id"], contact_id=seed["contact_id"],
                        stage=1, status="active", next_stage=2,
                        next_due_date=(date.today() + timedelta(days=3)).isoformat(),
                        day1_sent_at=date.today().isoformat()))
    db.commit()

    logged.post("/ir/requests", follow_redirects=False, data={
        "contact_id": seed["contact_id"], "company_name": "샘플애그"})
    db.expire_all()
    seq = db.query(SendSequence).first()
    assert seq.status == "responded"
    assert seq.next_due_date is None


def test_deliver_marks_the_date(logged, db, seed):
    from app.models import IrRequest

    logged.post("/ir/requests", follow_redirects=False, data={
        "contact_id": seed["contact_id"], "company_name": "샘플애그"})
    db.expire_all()
    row = db.query(IrRequest).first()
    logged.post(f"/ir/requests/{row.id}/deliver", follow_redirects=False)
    db.expire_all()
    row = db.get(IrRequest, row.id)
    assert row.status == "delivered"
    assert row.delivered_at == date.today().isoformat()


def test_waiting_three_days_is_overdue(db, users, seed):
    """사흘 넘게 못 보낸 요청은 눈에 띄어야 한다."""
    from app.models import IrRequest
    from app.services import pipeline

    db.add(IrRequest(user_id=seed["user_id"], contact_id=seed["contact_id"],
                     company_name="샘플애그",
                     requested_at=(date.today() - timedelta(days=4)).isoformat()))
    db.commit()
    rows = pipeline.request_rows(db, users["u1"])
    assert rows[0]["waited"] == 4
    assert rows[0]["overdue"] is True


def test_same_day_request_is_not_overdue(db, users, seed):
    from app.models import IrRequest
    from app.services import pipeline

    db.add(IrRequest(user_id=seed["user_id"], contact_id=seed["contact_id"],
                     company_name="샘플애그", requested_at=date.today().isoformat()))
    db.commit()
    assert pipeline.request_rows(db, users["u1"])[0]["overdue"] is False


def test_cannot_touch_another_users_request(client, db, users, seed):
    from app.models import IrRequest

    db.add(IrRequest(user_id=users["u1"].id, contact_id=seed["contact_id"],
                     company_name="샘플애그", requested_at=date.today().isoformat()))
    db.commit()
    row_id = db.query(IrRequest).first().id

    client.post("/login", data={"phone": "01000000002", "password": DEMO_PASSWORD})
    assert client.post(f"/ir/requests/{row_id}/deliver").status_code == 404


# --- 미팅 ------------------------------------------------------------------

def test_meeting_completion_schedules_the_followup(logged, db, seed):
    """미팅이 끝나면 열흘 뒤 결과를 물어야 한다 — 사람이 기억하지 않아도 되게."""
    from app.models import Meeting
    from app.services import pipeline

    logged.post("/ir/meetings", follow_redirects=False, data={
        "contact_id": seed["contact_id"],
        "scheduled_at": date.today().isoformat(), "kind": "first"})
    db.expire_all()
    meeting = db.query(Meeting).first()
    assert meeting.followup_due is None

    logged.post(f"/ir/meetings/{meeting.id}/done", follow_redirects=False,
                data={"outcome": "reviewing"})
    db.expire_all()
    meeting = db.get(Meeting, meeting.id)
    assert meeting.status == "done"
    assert meeting.outcome == "reviewing"
    expected = pipeline.followup_date(date.today()).isoformat()
    assert meeting.followup_due == expected


def test_followup_never_lands_on_a_weekend(db):
    from app.services import pipeline

    for offset in range(14):
        day = pipeline.followup_date(date(2026, 8, 1) + timedelta(days=offset))
        assert day.weekday() < 5


def test_meeting_stops_the_reminder(logged, db, seed):
    from app.models import SendSequence

    db.add(SendSequence(user_id=seed["user_id"], contact_id=seed["contact_id"],
                        stage=1, status="active", next_stage=2,
                        next_due_date=(date.today() + timedelta(days=3)).isoformat(),
                        day1_sent_at=date.today().isoformat()))
    db.commit()

    logged.post("/ir/meetings", follow_redirects=False, data={
        "contact_id": seed["contact_id"], "scheduled_at": date.today().isoformat()})
    db.expire_all()
    assert db.query(SendSequence).first().status == "responded"


def test_canceled_meeting_has_no_followup(logged, db, seed):
    from app.models import Meeting

    logged.post("/ir/meetings", follow_redirects=False, data={
        "contact_id": seed["contact_id"], "scheduled_at": date.today().isoformat()})
    db.expire_all()
    meeting = db.query(Meeting).first()
    logged.post(f"/ir/meetings/{meeting.id}/done", follow_redirects=False, data={})
    logged.post(f"/ir/meetings/{meeting.id}/cancel", follow_redirects=False)
    db.expire_all()
    assert db.get(Meeting, meeting.id).followup_due is None


def test_bad_meeting_date_is_rejected(logged, db, seed):
    from app.models import Meeting

    logged.post("/ir/meetings", follow_redirects=False, data={
        "contact_id": seed["contact_id"], "scheduled_at": "내일"})
    db.expire_all()
    assert db.query(Meeting).count() == 0


def test_page_opens(logged, seed):
    r = logged.get("/ir")
    assert r.status_code == 200
    assert "보낼 자료" in r.text


# --- 딜 제안 관리와 이어지기 -------------------------------------------------
#
# 보내고 나서 다시 화면으로 돌아와 '전달함'을 누르게 하면, 바쁠 때 그 한 번을
# 빼먹는다. 그러면 이미 보낸 요청이 계속 '보낼 자료'에 남는다.

def _report_sent(client, db, job_id):
    """에이전트가 발송 성공을 보고한 것처럼."""
    from app.models import AgentDevice, SendItem

    token = db.query(AgentDevice).filter_by(user_id=1).first().token
    item = db.query(SendItem).filter_by(job_id=job_id).first()
    return client.post(f"/api/agent/items/{item.id}/result",
                       headers={"Authorization": f"Bearer {token}"},
                       json={"status": "sent"})


def test_ir_send_closes_the_request(logged, db, seed):
    """자료를 보내면 그 요청이 자동으로 닫힌다."""
    from app.models import IrCompany, IrRequest

    logged.post("/ir/requests", follow_redirects=False, data={
        "contact_id": seed["contact_id"], "company_name": "샘플애그"})
    db.expire_all()
    company = db.query(IrCompany).filter_by(name="샘플애그").first()

    r = logged.post("/api/deals/send", json={
        "company_ids": [company.id], "contact_ids": [seed["contact_id"]],
        "mode": "ir"})
    assert r.status_code == 200, r.text
    _report_sent(logged, db, r.json()["job_id"])

    db.expire_all()
    assert db.query(IrRequest).first().status == "delivered"


def test_ir_send_uses_its_own_job_kind(logged, db, seed):
    """IR 자료 전달은 딜소개와 다른 일이다 — 종류가 남아야 후속도 멈춘다."""
    from app.models import IrCompany, SendJob

    company = db.query(IrCompany).filter_by(name="샘플애그").first()
    r = logged.post("/api/deals/send", json={
        "company_ids": [company.id], "contact_ids": [seed["contact_id"]],
        "mode": "ir"})
    db.expire_all()
    assert db.get(SendJob, r.json()["job_id"]).kind == "ir_delivery"


def test_only_the_sent_companies_are_closed(logged, db, seed):
    """같은 담당자의 다른 기업 요청까지 닫으면 안 보낸 것을 보냈다고 적는 셈이다."""
    from app.models import IrCompany, IrRequest

    db.add(IrCompany(name="샘플메디", one_liner="뇌영상", revenue_recent=5))
    db.commit()
    logged.post("/ir/requests", follow_redirects=False, data={
        "contact_id": seed["contact_id"], "company_name": "샘플애그\n샘플메디"})
    db.expire_all()

    agri = db.query(IrCompany).filter_by(name="샘플애그").first()
    r = logged.post("/api/deals/send", json={
        "company_ids": [agri.id], "contact_ids": [seed["contact_id"]], "mode": "ir"})
    _report_sent(logged, db, r.json()["job_id"])

    db.expire_all()
    rows = {x.company_name: x.status for x in db.query(IrRequest).all()}
    assert rows["샘플애그"] == "delivered"
    assert rows["샘플메디"] == "open"


def test_deal_send_does_not_close_requests(logged, db, seed):
    """딜소개(목록 발송)는 자료를 보낸 것이 아니다."""
    from app.models import IrCompany, IrRequest

    logged.post("/ir/requests", follow_redirects=False, data={
        "contact_id": seed["contact_id"], "company_name": "샘플애그"})
    db.expire_all()
    company = db.query(IrCompany).filter_by(name="샘플애그").first()

    r = logged.post("/api/deals/send", json={
        "company_ids": [company.id], "contact_ids": [seed["contact_id"]]})
    _report_sent(logged, db, r.json()["job_id"])

    db.expire_all()
    assert db.query(IrRequest).first().status == "open"


def test_ir_screen_groups_by_contact(logged, db, seed):
    """한 담당자가 여러 기업을 요청하면 한 번에 보낼 수 있어야 한다."""
    from app.models import IrCompany

    db.add(IrCompany(name="샘플메디", one_liner="뇌영상", revenue_recent=5))
    db.commit()
    logged.post("/ir/requests", follow_redirects=False, data={
        "contact_id": seed["contact_id"], "company_name": "샘플애그\n샘플메디"})

    body = logged.get("/ir").text
    assert "<b>2</b>개 기업" in body
    # 담당자와 기업이 함께 넘어가야 딜 제안 관리에서 다시 고르지 않는다
    import re
    link = re.search(r'/deals\?mode=ir&contacts=(\d+)&companies=([\d,]+)', body)
    assert link is not None, "자료 보내기 링크에 기업이 실려 있지 않다"
    assert len(link.group(2).split(",")) == 2


# --- 딜 진행 관리 (후속 + IR·미팅 통합) -------------------------------------
#
# 둘 다 '보낸 뒤에 챙기는 일'인데 메뉴가 갈라져 있어서 매일 두 군데를 열어야 했다.

def test_menu_has_one_entry_not_two(client, db, users):
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    body = client.get("/").text
    assert "딜 진행 관리" in body
    assert "후속 관리" not in body
    assert "IR·미팅 관리" not in body


def test_everything_lives_on_one_page(client, db, users):
    """넷 다 한 페이지의 구역이다. 예전에는 탭처럼 생겼는데 둘만 페이지를
    바꾸고 둘은 스크롤이라, 누를 때마다 무슨 일이 일어날지 알 수 없었다."""
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})

    body = client.get("/ir").text
    assert "jump-bar" in body
    for section in ('id="requests"', 'id="remind"', 'id="meetings"', 'id="reviews"'):
        assert section in body, f"{section} 구역이 없다"
    for label in ("IR 자료 요청", "리마인드", "미팅", "미팅 후기"):
        assert label in body, f"{label} 이동 링크가 없다"

    # 옛 주소는 살려 둔다 — 즐겨찾기와 화면 안 링크가 여럿 걸려 있다
    moved = client.get("/followups", follow_redirects=False)
    assert moved.status_code in (302, 307)
    assert moved.headers["location"] == "/ir#remind"


def test_tab_counts_come_from_one_place(client, db, users):
    """두 화면이 각자 세면 반드시 어긋난다 — 실제로 6명 어긋난 적이 있다."""
    from datetime import date

    from app.services import flow

    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    expected = flow.counts(db, users["u1"], date.today())

    for path in ("/followups", "/ir"):
        assert client.get(path).status_code == 200, path
    assert set(expected) == {"due", "upcoming", "ir_open", "ir_overdue",
                             "meeting_todo", "meeting_open",
                             "review_due", "review_open"}


def test_the_jump_bar_follows_the_working_order(client, db, users):
    """순서가 곧 일하는 순서여야 다음에 뭘 눌러야 할지 헤매지 않는다.

        딜 소개 → IR 자료 요청 → (반응 없음) 리마인드
               → (반응 있음) 미팅 → 미팅 후기
    """
    import re

    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    body = client.get("/ir").text
    block = body[body.index("jump-bar"):]
    hrefs = re.findall(r'href="(#\w+)"', block[:1400])
    assert hrefs[:4] == ["#requests", "#remind", "#meetings", "#reviews"], hrefs


def test_review_count_excludes_already_asked(db, users):
    """이미 결과를 물어본 곳까지 세면 전화할 곳이 몇 군데인지 알 수 없다."""
    from datetime import date

    from app.models import Meeting, VcContact
    from app.services import flow

    c1 = VcContact(user_id=users["u1"].id, name="물어봄", firm="가나벤처스")
    c2 = VcContact(user_id=users["u1"].id, name="아직", firm="다라인베스트")
    db.add_all([c1, c2])
    db.commit()
    today = date.today().isoformat()
    db.add_all([
        Meeting(user_id=users["u1"].id, contact_id=c1.id, kind="first",
                status="done", followup_done=1, scheduled_at=today),
        Meeting(user_id=users["u1"].id, contact_id=c2.id, kind="first",
                status="done", scheduled_at=today),
    ])
    db.commit()

    counts = flow.counts(db, users["u1"], date.today())
    assert counts["review_open"] == 1, "이미 물어본 곳이 섞였다"


def test_delivered_materials_offer_to_book_a_meeting(client, db, users):
    """미팅은 **자료를 보낸 그 건**에서 이어진다. 담당자·기업을 처음부터 다시
    고르게 하면 이미 아는 정보를 또 타이핑하게 되고, 그러다 다른 담당자를
    골라 엉뚱한 곳에 미팅이 잡힌다."""
    from datetime import date

    from app.models import IrRequest, VcContact

    contact = VcContact(user_id=users["u1"].id, name="홍길동", title="심사역",
                        firm="가나벤처스")
    db.add(contact)
    db.commit()
    db.add(IrRequest(user_id=users["u1"].id, contact_id=contact.id,
                     company_name="샘플애그", status="delivered",
                     requested_at=date.today().isoformat()))
    db.commit()

    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    body = client.get("/ir").text

    assert "js-book-meeting" in body, "전달한 자료에서 미팅을 잡을 방법이 없다"
    assert f'data-contact="{contact.id}"' in body
    assert 'data-company="샘플애그"' in body


def test_a_reviewing_meeting_can_loop_back_to_a_second_one(client, db, users):
    """흐름은 일직선이 아니다 — 검토 중이면 2차 미팅으로 돌아간다.
    여기서 바로 잡지 못하면 위로 올라가 담당자를 다시 골라야 하고,
    그러다 엉뚱한 곳에 미팅이 잡힌다."""
    from datetime import date

    from app.models import Meeting, VcContact

    contact = VcContact(user_id=users["u1"].id, name="홍길동", firm="가나벤처스")
    db.add(contact)
    db.commit()
    db.add(Meeting(user_id=users["u1"].id, contact_id=contact.id, kind="first",
                   status="done", outcome="reviewing", company_name="샘플애그",
                   scheduled_at=date.today().isoformat()))
    db.commit()

    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    body = client.get("/ir").text
    assert "2차 미팅 잡기" in body
    assert 'data-kind="second"' in body


def test_a_rejected_meeting_does_not_suggest_another(client, db, users):
    """이미 거절·보류로 끝난 건에 다음 미팅을 권하면 안 된다."""
    from datetime import date

    from app.models import Meeting, VcContact

    contact = VcContact(user_id=users["u1"].id, name="거절함", firm="다라인베스트")
    db.add(contact)
    db.commit()
    db.add(Meeting(user_id=users["u1"].id, contact_id=contact.id, kind="first",
                   status="done", outcome="pass",
                   scheduled_at=date.today().isoformat()))
    db.commit()

    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    body = client.get("/ir").text
    row = body[body.index("거절함"):body.index("거절함") + 600]
    assert "미팅 잡기" not in row
