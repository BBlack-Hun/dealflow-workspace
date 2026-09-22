"""미팅 요청 뒤 사흘 — **전화 요청** 단계.

미팅 요청 카톡을 보내고 답이 없으면 전화로 다시 청한다. 그 일은 앱 어디에도
안 잡혀 있어서 사람이 달력을 보며 챙기고 있었다 — 후속 캐던스를 만든 까닭과
같은 일이 한 단계 뒤에 그대로 남아 있었다.

여기서 지키려는 경계.

1. **흐름을 새로 만들지 않는다.** 이미 있는 단계 사다리에 한 칸을 더 단다
   (`cadence.STAGE_CALL`) — 날짜를 잡는 것도 멈추는 것도 그 한 곳을 지난다.
2. **★ 답이 온 상대에게는 안 뜬다.** IR 요청·미팅이 생기면 흐름이 멈춘다
   (`stop_on_reaction`·`sweep_reactions`). 새 단계도 그 규칙을 지나야 한다 —
   이 흐름에서 가장 나쁜 실패가 그것이다.
3. **[보내기] 가 아니라 [전화함].** 앱이 대신 걸 수 없다.
4. **업무 보고에도 잡힌다.** 사용자가 두 곳을 다 들었다.
"""
from __future__ import annotations

import re
from datetime import date, timedelta

import pytest

from .conftest import DEMO_PASSWORD


@pytest.fixture()
def logged(client, users):
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    return client


@pytest.fixture()
def waiting_call(db, users):
    """미팅 요청까지 나가고 **전화를 기다리는** 담당자 한 명.

    단계를 손으로 세워 두지 않는다 — `cadence` 를 그대로 태워서, 사다리가
    바뀌면 이 준비도 함께 깨지게 둔다.
    """
    from app.models import DealBatch, SendItem, SendJob, VcContact
    from app.services import cadence

    contact = VcContact(user_id=users["u1"].id, name="홍길동", title="심사역",
                        firm="가나벤처스", kakao_room_name="홍길동 심사역님",
                        room_verified="verified", channel_kakao=1)
    db.add(contact)
    db.flush()

    seq = None
    for stage, day in ((1, date(2026, 9, 2)), (2, date(2026, 9, 9)),
                       (3, date(2026, 9, 14))):
        when = day.isoformat() + "T09:00:00+09:00"
        batch = DealBatch(user_id=users["u1"].id, title=f"{stage}회차",
                          sent_date=day.isoformat())
        db.add(batch)
        db.flush()
        job = SendJob(user_id=users["u1"].id, kind="deal_intro",
                      batch_id=batch.id, status="done")
        db.add(job)
        db.flush()
        item = SendItem(job_id=job.id, contact_id=contact.id, stage=stage,
                        room_name="방", message="문구", status="sent",
                        sent_at=when)
        db.add(item)
        db.flush()
        seq = cadence.start_or_advance(db, item, job)
    db.commit()
    return {"contact": contact, "seq": seq}


# --- 1. 기존 흐름에 한 칸 ---------------------------------------------------------

def test_the_call_is_a_step_of_the_same_flow(waiting_call):
    """새 흐름이 아니라 **같은 사다리의 한 칸**이다."""
    from app.services import cadence

    seq = waiting_call["seq"]
    assert seq.status == "active"
    assert seq.stage == cadence.STAGE_MEETING
    assert seq.next_stage == cadence.STAGE_CALL
    # 미팅 요청을 보낸 날(9/14 월) + 사흘 = 9/17 목
    assert seq.next_due_date == "2026-09-17"

    # 주기는 코드가 아니라 DB 가 정한다 — 다른 단계와 같은 모양의 규칙이다.
    from app.db import SessionLocal

    with SessionLocal() as s:
        assert cadence.get_rule(s, "call")["kind"] == "offset_days"


def test_the_rule_is_on_the_cycle_panel(logged, db):
    """`발송 주기` 판에 전화 규칙이 서고, 관리자가 늘릴 수 있어야 한다.

    빠뜨리면 화면에 안 보이고 고칠 길도 없어, 코드에 박아 둔 것과 다를 바 없다.
    """
    from app.routers import followups
    from app.services import cadence

    keys = [r["key"] for r in followups._rule_views(db)]
    assert keys == list(cadence.DEFAULT_RULES), \
        "화면에 세우는 규칙과 기본 규칙이 갈렸다"

    body = logged.get("/ir").text
    rules = body[body.index("발송 주기"):body.index('id="closed"')
                 if 'id="closed"' in body else len(body)]
    # **기준이 딜소개가 아니다.** 전화는 미팅 요청을 보낸 날에서 센다 —
    # 화면이 코드와 다른 말을 하면 사람은 화면을 믿고 날짜를 잘못 짚는다.
    assert "미팅 요청 3일 뒤" in rules, rules[:800]
    assert "딜소개 3" not in rules
    # 폭이 없는 규칙을 `3~3일` 로 적으면 무엇이 흔들린다는 말로 읽힌다.
    assert "3~3" not in body


# --- 2. ★ 답이 온 상대에게는 안 뜬다 ------------------------------------------------

def test_an_ir_request_takes_the_call_off_the_list(waiting_call, logged, db):
    """**이 검사가 이 단계의 가장 중요한 경계다.**

    자료를 달라고 답한 사람에게 "미팅 가능하실지요" 를 다시 전화로 묻는 것은
    이쪽이 그 답을 못 봤다는 뜻이 된다.
    """
    contact = waiting_call["contact"]

    # 전화 구역에 서 있다가…
    assert str(contact.id) in _call_ids(logged.get("/ir").text)

    # IR 요청을 적으면 흐름이 멈춘다(`cadence.stop_on_reaction`).
    logged.post("/ir/requests", follow_redirects=False,
                data={"contact_id": contact.id, "company_name": "샘플애그"})
    db.expire_all()

    assert str(contact.id) not in _call_ids(logged.get("/ir").text), \
        "답이 온 상대에게 전화 요청이 떠 있다"
    seq = _seq(db, contact.id)
    assert seq.status == "responded"
    assert seq.next_stage is None and seq.next_due_date is None


def test_a_booked_meeting_takes_the_call_off_the_list(waiting_call, logged, db):
    """미팅이 잡혔으면 전화로 미팅을 청할 이유가 없다."""
    contact = waiting_call["contact"]

    logged.post("/ir/meetings", follow_redirects=False,
                data={"contact_id": contact.id, "scheduled_at": "2026-09-30"})
    db.expire_all()

    assert str(contact.id) not in _call_ids(logged.get("/ir").text)
    assert _seq(db, contact.id).status == "responded"


def test_a_late_reaction_is_swept_when_the_screen_opens(waiting_call, logged, db):
    """활동이 **시트 임포트로도** 들어온다 — 길목마다 훅을 달지 않고 훑는다.

    화면을 여는 길이 `sweep_reactions` 를 지나므로, 앱을 안 거치고 들어온
    반응도 전화 목록에서 빠진다.
    """
    from app.models import ContactActivity

    contact = waiting_call["contact"]
    db.add(ContactActivity(contact_id=contact.id, kind="ir_request",
                           happened_at="2026-09-15", content="시트에서 들어옴"))
    db.commit()

    assert str(contact.id) not in _call_ids(logged.get("/ir").text)
    db.expire_all()
    assert _seq(db, contact.id).status == "responded"


# --- 3. [보내기] 가 아니라 [전화함] -------------------------------------------------

def test_the_screen_has_a_tab_of_its_own(waiting_call, logged):
    """**갈래를 하나 더 세운다.** 점프바에 건수와 함께 선다.

    전화는 갈 발송 화면이 없어서 `오늘 보낼 리마인드` 묶음에 섞을 수 없다 —
    그 묶음의 머리에는 [보내기] 가 달려 있다.
    """
    body = logged.get("/ir").text

    at = body.index('class="jump-bar"')
    bar = body[at:body.index("</nav>", at)]
    assert 'href="#calls"' in bar, "점프바에 전화 요청 갈래가 없다"
    assert "전화 요청" in bar
    # 다른 갈래들처럼 건수를 단다 — 내려가 보지 않아도 몇 군데인지 보인다.
    assert re.search(r'href="#calls".*?<span[^>]*>1</span>', bar, re.S), \
        "전화 요청 갈래에 건수가 안 붙었다: " + bar

    assert 'id="calls"' in body, "전화 요청 구역이 없다"


def test_the_button_says_called_not_send(waiting_call, logged):
    """앱이 대신 걸 수 없다 — 할 수 있는 것은 **적는 일**뿐이다."""
    body = logged.get("/ir").text
    panel = body[body.index('id="calls"'):body.index('id="meetings"')]
    seq_id = waiting_call["seq"].id

    assert f'action="/followups/{seq_id}/called"' in panel
    assert ">전화함<" in panel
    # 보낼 문구가 없으니 발송 화면으로 가는 단추가 있으면 안 된다.
    assert "/deals?mode=" not in panel, \
        "전화 구역에 [보내기] 가 서 있다 — 보낼 것이 없다"
    assert "전화는 직접" in body, "앱이 거는 것으로 읽히면 안 된다"


def test_the_call_is_not_in_the_remind_groups(waiting_call, logged):
    """`오늘 보낼 리마인드` 묶음에 섞이지 않는다 — 한 줄이 두 곳에 서면 안 된다."""
    body = logged.get("/ir").text
    # `오늘 보낼 리마인드` 판 하나만 본다 — 아래 `발송 주기` 판에는 전화 규칙이
    # 서 있는 것이 맞다(고칠 자리다).
    at = body.index("오늘 보낼 리마인드")
    panel = body[at:body.index("</section>", at)]
    assert "전화 요청" not in panel, "전화가 리마인드 묶음에 섞여 있다"
    assert "홍길동" not in panel, "전화 기다리는 줄이 리마인드 묶음에 서 있다"


def test_a_scheduled_call_is_not_listed_twice(db, users, logged):
    """아직 날이 안 온 전화는 `예약된 리마인드` 표에 서지 않는다.

    그 표는 **보낼 것**을 세우는 자리다. 안 가르면 한 줄이 두 표에 나란히 서서
    두 건으로 읽힌다.
    """
    from app.models import DealBatch, SendItem, SendJob, VcContact
    from app.services import cadence

    contact = VcContact(user_id=users["u1"].id, name="마바사", title="심사역",
                        firm="마바벤처스")
    db.add(contact)
    db.flush()
    seq = None
    for stage, day in ((1, date.today() - timedelta(days=20)),
                       (2, date.today() - timedelta(days=10)),
                       (3, date.today())):        # 오늘 보냈으니 전화는 사흘 뒤
        b = DealBatch(user_id=users["u1"].id, title="회차",
                      sent_date=day.isoformat())
        db.add(b)
        db.flush()
        j = SendJob(user_id=users["u1"].id, kind="deal_intro", batch_id=b.id,
                    status="done")
        db.add(j)
        db.flush()
        it = SendItem(job_id=j.id, contact_id=contact.id, stage=stage,
                      room_name="방", message="문구", status="sent",
                      sent_at=day.isoformat() + "T09:00:00+09:00")
        db.add(it)
        db.flush()
        seq = cadence.start_or_advance(db, it, j)
    db.commit()
    assert seq.next_stage == cadence.STAGE_CALL and seq.next_due_date > \
        date.today().isoformat()

    body = logged.get("/ir").text
    at = body.index("예약된 리마인드")
    table = body[at:body.index("</section>", at)]
    assert "마바사" not in table, "전화가 `예약된 리마인드` 표에도 서 있다"

    # 제 구역에는 `예정` 으로 선다
    calls = body[body.index('id="calls"'):body.index('id="meetings"')]
    assert "마바사" in calls and "예정" in calls


def test_pressing_called_closes_the_row(waiting_call, logged, db):
    """걸고 나서 그 줄에서 바로 끝낸다 — 「체크 가능한」 이 뜻하는 것."""
    from app.services import cadence

    seq_id = waiting_call["seq"].id
    contact = waiting_call["contact"]

    logged.post(f"/followups/{seq_id}/called", follow_redirects=False)
    db.expire_all()

    seq = _seq(db, contact.id)
    assert seq.status == "done", "전화까지 한 건은 `완료` 다"
    assert seq.stage == cadence.STAGE_CALL
    assert seq.next_due_date is None
    assert str(contact.id) not in _call_ids(logged.get("/ir").text)


def test_called_is_not_the_same_as_stopped(waiting_call, logged, db):
    """`전화함` 과 `중단` 은 뜻이 다르다.

    하나는 **할 일을 끝낸** 것이고 하나는 **도중에 그만둔** 것이다. 같은 값으로
    적으면 나중에 둘이 한 덩어리가 되어, 이 단계를 둔 뜻이 사라진다.
    """
    logged.post(f"/followups/{waiting_call['seq'].id}/called",
                follow_redirects=False)
    db.expire_all()
    assert _seq(db, waiting_call["contact"].id).status == "done"

    # 견주기: 중단은 `stopped` 다
    assert _seq(db, waiting_call["contact"].id).status != "stopped"


def test_someone_elses_row_cannot_be_marked(waiting_call, client, users, db):
    """판정은 `답 옴`·`중단` 과 **같은 것**이다(`_owned`) — 새로 짓지 않는다."""
    client.post("/login", data={"phone": "01000000002",
                                "password": DEMO_PASSWORD})
    got = client.post(f"/followups/{waiting_call['seq'].id}/called",
                      follow_redirects=False)
    assert got.status_code == 404
    db.expire_all()
    assert _seq(db, waiting_call["contact"].id).status == "active"


# --- 4. 업무 보고에도 잡힌다 --------------------------------------------------------

def test_the_report_counts_the_call(waiting_call, db, users):
    """사용자가 두 곳을 다 들었다 — 딜 진행 관리에만 두면 보고를 보며 일하는
    사람에게는 이 일이 아예 안 보인다."""
    from app.services import report

    data = report.monthly(db, 2026, 9, users["u1"], today=date(2026, 9, 18))
    assert data["call_open"] == 1
    assert data["call_overdue"] == 1, "9/17 이 걸 날인데 9/18 에 보고 있다"
    assert data["call_done"] == 0
    # 화면이 "사흘" 이라고 말할 때 쓰는 값은 서버가 낸다.
    assert data["call_days"] == 3

    bucket = next(b for b in data["buckets"] if b["key"] == "meeting_call")
    assert bucket["label"] == "미팅 요청 후 전화 투자사"
    assert [r["name"] for r in bucket["rows"]] == ["홍길동"]
    assert bucket["rows"][0]["date"] == "2026-09-17"
    assert "지금 거세요" in bucket["rows"][0]["note"]


def test_the_report_tells_the_two_calls_apart(waiting_call, db, users):
    """**미팅이 끝난 뒤 거는 전화와 다르다.**

    보고에 이미 `IR 미팅완료 리마인드 TEL 투자사` 가 있다 — 그쪽은 미팅이 끝나고
    열흘 뒤 결과를 묻는 것이고, 이쪽은 미팅을 청해 놓고 답이 없을 때 거는 것이다.
    한 화면에 나란히 서므로 이름이 그 둘을 갈라야 한다.
    """
    from app.services import report

    data = report.monthly(db, 2026, 9, users["u1"], today=date(2026, 9, 18))
    labels = [b["label"] for b in data["buckets"]]
    assert "미팅 요청 후 전화 투자사" in labels
    assert "IR 미팅완료 리마인드 TEL 투자사" in labels
    assert len(set(labels)) == len(labels), "갈래 이름이 겹친다"


def test_the_report_screen_shows_it(waiting_call, logged):
    body = logged.get("/report?month=2026-09").text
    # 판 안의 차례가 곧 흐름이다 — 바로 윗줄 `미팅 요청 안 보냄` 과 같은 결.
    assert "전화 요청 안 함" in body
    assert "미팅 요청 후 전화 투자사" in body
    assert "홍길동" in body
    # 걸고 나서 어디서 적는지 알려 준다
    assert "/ir#calls" in body


def test_the_excel_carries_it_without_being_told(waiting_call, logged):
    """엑셀은 갈래를 **화면에서 그대로 받는다** — 여기 손댈 것이 없어야 맞다."""
    import io as _io

    openpyxl = pytest.importorskip("openpyxl")
    got = logged.get("/api/export/report.xlsx?month=2026-09")
    assert got.status_code == 200
    wb = openpyxl.load_workbook(_io.BytesIO(got.content))
    flat = [str(c) for row in wb["2026-09 반응"].iter_rows(values_only=True)
            for c in row if c is not None]
    assert any("미팅 요청 후 전화 투자사" in c for c in flat), \
        "파일에 갈래가 안 실렸다"
    assert "홍길동" in flat


def test_a_finished_call_shows_in_the_month_it_was_made(waiting_call, logged,
                                                        db, users):
    """건 것도 그 달에 남는다 — `전화함 N명` 이 그 수다."""
    from app.services import report

    logged.post(f"/followups/{waiting_call['seq'].id}/called",
                follow_redirects=False)
    db.expire_all()
    seq = _seq(db, waiting_call["contact"].id)
    # 건 날을 그 달로 못박는다(오늘이 언제든 검사가 같은 답을 내야 한다).
    seq.last_sent_at = "2026-09-18T11:00:00+09:00"
    db.commit()

    data = report.monthly(db, 2026, 9, users["u1"], today=date(2026, 9, 30))
    assert data["call_done"] == 1
    assert data["call_open"] == 0

    bucket = next(b for b in data["buckets"] if b["key"] == "meeting_call")
    assert bucket["rows"][0]["note"] == "전화함 · 2026-09-18"

    # 다른 달에는 안 선다
    other = report.monthly(db, 2026, 10, users["u1"], today=date(2026, 10, 31))
    assert other["call_done"] == 0


def test_the_report_does_not_count_the_call_twice(waiting_call, db, users):
    """**같은 셈을 두 곳에 적지 않는다.** 갈래 줄과 숫자가 한 벌에서 나온다."""
    from app.services import report

    data = report.monthly(db, 2026, 9, users["u1"], today=date(2026, 9, 18))
    bucket = next(b for b in data["buckets"] if b["key"] == "meeting_call")
    assert len(bucket["rows"]) == data["call_open"] + data["call_done"]


# --- 거들이 ------------------------------------------------------------------------

def _seq(db, contact_id):
    from sqlalchemy import select

    from app.models import SendSequence

    return db.execute(
        select(SendSequence).where(SendSequence.contact_id == contact_id)
        .order_by(SendSequence.id.desc())
    ).scalars().first()


def _call_ids(html: str) -> set:
    """전화 요청 구역에 서 있는 담당자 번호들."""
    if 'id="calls"' not in html:
        return set()
    panel = html[html.index('id="calls"'):html.index('id="meetings"')]
    return set(re.findall(r'/ir\?contact=(\d+)', panel))
