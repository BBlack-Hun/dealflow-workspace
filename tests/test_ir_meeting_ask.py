"""자료를 보내 놓고 **아무 말도 안 한 건**이 보이는가.

IR 자료를 전달하면 리마인드 시퀀스가 멈춘다(`cadence` 가 `responded` 로 닫는다
— 상대가 답을 했으니 맞는 동작이다). 그런데 그 뒤에 미팅 요청을 안 보내면
그 담당자는 `오늘 보낼 리마인드` 에도 `오늘 할 일` 에도 다시 안 뜬다.
**자료만 보내 놓고 아무 말 없이 끝나는 길**이 열려 있었다.

여기서 못박는 것.

1. 전달 후 7일이 안 지났으면 **안 뜬다**
2. 7일이 지났고 미팅 요청을 안 보냈으면 **뜬다**
3. **보냈으면 안 뜬다** — 근거는 `SendItem`(stage 3 · sent) 하나다
4. **손으로 보냈음 표시**를 하면 안 뜬다
5. 담당자 하나가 자료를 여러 건 받아도 **한 건으로 센다**
6. `7` 이라는 수는 **한 곳**에만 있다

날짜는 전부 인자로 넣는다 — 오늘이 언제냐에 따라 통과했다 실패했다 하면 안 된다.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from .conftest import DEMO_PASSWORD

#: 자료를 전달한 날. 모든 검사가 이 날을 기준으로 앞뒤를 잰다.
DELIVERED = date(2026, 6, 10)


@pytest.fixture()
def logged(client, users):
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    return client


def _contact(db, users, name, *, user_key="u1"):
    from app.models import SheetOwner, VcContact

    if db.query(SheetOwner).filter_by(label="내 명단").first() is None:
        db.add(SheetOwner(label="내 명단", user_id=users["u1"].id))
    row = VcContact(user_id=users[user_key].id, name=name, title="심사역",
                    firm="가나벤처스", source_sheet="내 명단",
                    channel_kakao=1, connect_stage="connected",
                    kakao_room_name=f"{name} 심사역님")
    db.add(row)
    db.commit()
    return row


def _delivered(db, users, contact, company, *, when=DELIVERED, user_key="u1"):
    """`company` 자료를 `when` 에 전달한 요청 한 줄."""
    from app.models import IrRequest

    row = IrRequest(user_id=users[user_key].id, contact_id=contact.id,
                    company_name=company, requested_at=when.isoformat(),
                    status="delivered", delivered_at=when.isoformat())
    db.add(row)
    db.commit()
    return row


def _meeting_send(db, users, contact, *, when, status="sent", stage=3):
    """미팅 요청 발송 한 건. **기본은 실제로 나간 것**(`sent`)."""
    from app.models import SendItem, SendJob

    job = SendJob(user_id=users["u1"].id, kind="deal_intro", status="done")
    db.add(job)
    db.flush()
    item = SendItem(job_id=job.id, contact_id=contact.id, stage=stage,
                    room_name=contact.kakao_room_name, message="미팅 가능하실지요",
                    status=status,
                    sent_at=(f"{when.isoformat()}T11:00:00+09:00"
                             if status == "sent" else None))
    db.add(item)
    db.commit()
    return item


def _state(db, users, today):
    """판정 한 곳을 그대로 부른다."""
    from app.models import IrRequest
    from app.services import pipeline

    rows = db.query(IrRequest).filter_by(user_id=users["u1"].id).all()
    return pipeline.meeting_ask_state(db, rows, today=today)


# --- 1) 아직 때가 안 됐다 ----------------------------------------------------

@pytest.mark.parametrize("days", [0, 1, 6])
def test_이레가_안_지났으면_안_뜬다(db, users, days):
    """전달한 바로 그날부터 6일째까지는 조용하다.

    자료를 보내자마자 재촉하면 그 숫자는 늘 켜져 있는 등이 되고,
    늘 켜져 있는 등은 아무도 안 본다.
    """
    contact = _contact(db, users, "가담당")
    _delivered(db, users, contact, "샘플애그")

    state = _state(db, users, DELIVERED + timedelta(days=days))
    assert state[contact.id]["overdue"] is False
    assert state[contact.id]["asked"] is False, "보낸 적이 없다"


# --- 2) 지났는데 아무 말이 없다 ----------------------------------------------

@pytest.mark.parametrize("days", [7, 8, 40])
def test_이레가_지났는데_안_보냈으면_뜬다(db, users, days):
    contact = _contact(db, users, "가담당")
    _delivered(db, users, contact, "샘플애그")

    state = _state(db, users, DELIVERED + timedelta(days=days))
    assert state[contact.id]["overdue"] is True
    assert state[contact.id]["due"] == (DELIVERED + timedelta(days=7)).isoformat()


def test_주말을_건너뛰지_않는다(db, users):
    """**달력 7일이다.**

    결과 문의(`MEETING_FOLLOWUP_DAYS`)는 `cadence.next_business_day` 를 지나
    주말을 건너뛰지만 여기는 안 건넌다 — 이건 나가는 발송의 날짜가 아니라
    "안 보낸 지 며칠 됐나" 를 세는 자다. 주말을 빼면 금요일에 보낸 자료가
    다음다음 주에야 지난 것이 되어, 열흘이 지나도록 말이 없는 건이 화면
    어디에도 안 뜬다.
    """
    from app.services import cadence

    saturday = date(2026, 6, 13)          # 토
    assert saturday.weekday() == 5, "전제"
    due = date(2026, 6, 20)               # 토 — 달력 7일
    assert due.weekday() == 5
    assert cadence.next_business_day(due) != due, "전제 — 영업일이면 월요일로 밀린다"

    contact = _contact(db, users, "가담당")
    _delivered(db, users, contact, "샘플애그", when=saturday)

    assert _state(db, users, due)[contact.id]["due"] == due.isoformat()
    assert _state(db, users, due)[contact.id]["overdue"] is True, \
        "주말이라고 월요일로 밀렸다"


# --- 3) 보냈으면 안 뜬다 — 근거는 `SendItem` 하나 ------------------------------

def test_미팅_요청을_보냈으면_안_뜬다(db, users):
    contact = _contact(db, users, "가담당")
    _delivered(db, users, contact, "샘플애그")
    _meeting_send(db, users, contact, when=DELIVERED + timedelta(days=2))

    state = _state(db, users, DELIVERED + timedelta(days=30))
    assert state[contact.id]["asked"] is True
    assert state[contact.id]["overdue"] is False
    assert state[contact.id]["asked_at"] == (DELIVERED + timedelta(days=2)).isoformat()


def test_전달보다_먼저_보낸_미팅_요청은_안_친다(db, users):
    """**전달 뒤에 한 말**만 센다.

    지난달에 미팅 요청을 한 번 보냈다고 이번에 보낸 자료가 소리 없이 묻히면
    안 된다 — 자료를 새로 보냈으면 그 뒤에 다시 말을 붙이는 것이 이 흐름이다.
    """
    contact = _contact(db, users, "가담당")
    _meeting_send(db, users, contact, when=DELIVERED - timedelta(days=20))
    _delivered(db, users, contact, "샘플애그")

    state = _state(db, users, DELIVERED + timedelta(days=10))
    assert state[contact.id]["asked"] is False
    assert state[contact.id]["overdue"] is True


def test_안_나간_발송은_보낸_것이_아니다(db, users):
    """★ 목록에 세워 두기만 한 건은 **한 통도 안 나간 것**이다.

    `IrRequest` 에 `meeting_asked_at` 같은 칸을 새로 두면 "화면은 보냄인데
    발송기가 꺼져 있어 실제로는 안 나간" 상태가 만들어진다. 이 저장소가
    반복해 겪은 사고라, 근거를 `send_items` 하나로 둔다.
    """
    contact = _contact(db, users, "가담당")
    _delivered(db, users, contact, "샘플애그")
    _meeting_send(db, users, contact, when=DELIVERED + timedelta(days=2),
                  status="pending")

    state = _state(db, users, DELIVERED + timedelta(days=10))
    assert state[contact.id]["asked"] is False
    assert state[contact.id]["overdue"] is True


def test_다른_단계_발송은_미팅_요청이_아니다(db, users):
    """리마인드(2단)를 보낸 것은 미팅을 청한 것이 아니다."""
    contact = _contact(db, users, "가담당")
    _delivered(db, users, contact, "샘플애그")
    _meeting_send(db, users, contact, when=DELIVERED + timedelta(days=2), stage=2)

    state = _state(db, users, DELIVERED + timedelta(days=10))
    assert state[contact.id]["overdue"] is True


# --- 4) 손으로 보냈음 표시 ---------------------------------------------------

def test_손으로_보냈음_표시를_하면_안_뜬다(db, users, logged):
    """카톡으로 사람이 직접 보낸 건은 앱이 모른다. 그대로 두면 거짓 경보다."""
    contact = _contact(db, users, "가담당")
    _delivered(db, users, contact, "샘플애그")
    assert _state(db, users, DELIVERED + timedelta(days=10))[contact.id]["overdue"]

    from app.services import pipeline

    pipeline.record_meeting_ask(db, contact.id,
                                when=DELIVERED + timedelta(days=3))
    db.commit()

    state = _state(db, users, DELIVERED + timedelta(days=10))
    assert state[contact.id]["asked"] is True
    assert state[contact.id]["overdue"] is False


def test_표시는_새_표도_새_칸도_안_쓴다(db, users):
    """`ContactActivity` 에 종류 하나를 더한 것뿐이라 이주가 없다.

    이력에서도 **제 이름으로** 떠야 한다(이름표는 `static/js/contacts.js`).
    """
    from app.models import ContactActivity
    from app.services import pipeline

    contact = _contact(db, users, "가담당")
    pipeline.record_meeting_ask(db, contact.id, when=DELIVERED)
    db.commit()

    row = db.query(ContactActivity).filter_by(contact_id=contact.id).one()
    assert row.kind == pipeline.MEETING_ASK_KIND
    assert row.source == "system"
    assert row.happened_at == DELIVERED.isoformat()
    assert row.month == DELIVERED.isoformat()[:7]
    assert row.content == pipeline.MEETING_ASK_BY_HAND


def test_두_번_눌러도_한_줄이다(db, users):
    from app.models import ContactActivity
    from app.services import pipeline

    contact = _contact(db, users, "가담당")
    assert pipeline.record_meeting_ask(db, contact.id, when=DELIVERED) is True
    db.commit()
    assert pipeline.record_meeting_ask(db, contact.id, when=DELIVERED) is False
    db.commit()

    assert db.query(ContactActivity).filter_by(contact_id=contact.id).count() == 1


def test_표시하는_길은_내_담당자만(db, users, logged):
    """남의 담당자에게는 못 적는다 — 다른 화면과 같은 좁힘이다."""
    mine = _contact(db, users, "가담당")
    theirs = _contact(db, users, "나담당", user_key="u2")

    assert logged.post(f"/ir/contacts/{mine.id}/meeting-asked",
                       follow_redirects=False).status_code == 303
    assert logged.post(f"/ir/contacts/{theirs.id}/meeting-asked",
                       follow_redirects=False).status_code == 404


def test_화면에서_누르면_표시된다(db, users, logged):
    """★ 실제로 눌러서 적히는가 — 함수만 맞고 길이 끊겨 있으면 뜻이 없다."""
    from app.models import ContactActivity

    contact = _contact(db, users, "가담당")
    _delivered(db, users, contact, "샘플애그")

    logged.post(f"/ir/contacts/{contact.id}/meeting-asked",
                follow_redirects=False)
    db.expire_all()
    assert db.query(ContactActivity).filter_by(
        contact_id=contact.id, kind="meeting_ask").count() == 1


# --- 5) 담당자 하나는 한 건 ---------------------------------------------------

def test_자료를_여러_건_받아도_한_건으로_센다(db, users):
    """★ 미팅 요청 카톡은 담당자당 **한 통**이다.

    미팅 요청 문구는 기업 목록을 쓰지 않는다(`deals.MODES_WITH_COMPANIES` 에
    미팅이 없다). 줄마다 세면 한 번 보낼 일이 세 건으로 보인다.
    """
    from app.services import report

    contact = _contact(db, users, "가담당")
    for name in ("샘플애그", "샘플메디", "샘플로지"):
        _delivered(db, users, contact, name)

    today = DELIVERED + timedelta(days=10)
    assert len(_state(db, users, today)) == 1

    data = report.monthly(db, DELIVERED.year, DELIVERED.month, users["u1"],
                          today=today)
    assert data["ir_delivered"] == 3, "자료 줄은 셋이다"
    assert data["ir_meeting_ask_missing"] == 1, "그래도 보낼 카톡은 한 통이다"
    assert data["ir_meeting_ask_overdue"] == 1


def test_한_통을_보내면_그_담당자의_줄이_모두_풀린다(db, users):
    contact = _contact(db, users, "가담당")
    for name in ("샘플애그", "샘플메디"):
        _delivered(db, users, contact, name)
    _meeting_send(db, users, contact, when=DELIVERED + timedelta(days=1))

    state = _state(db, users, DELIVERED + timedelta(days=10))
    assert state[contact.id]["asked"] is True


def test_마지막_전달일에_맞춘다(db, users):
    """자료를 새로 보냈으면 그 뒤에 다시 말을 붙인다.

    첫 전달일에 맞추면, 한 번 보낸 미팅 요청이 그 뒤의 모든 전달을 영영
    덮어 버린다 — 새로 보낸 자료가 소리 없이 묻힌다.
    """
    contact = _contact(db, users, "가담당")
    _delivered(db, users, contact, "샘플애그")
    _meeting_send(db, users, contact, when=DELIVERED + timedelta(days=1))
    later = DELIVERED + timedelta(days=30)
    _delivered(db, users, contact, "샘플메디", when=later)

    state = _state(db, users, later + timedelta(days=8))
    assert state[contact.id]["delivered_at"] == later.isoformat()
    assert state[contact.id]["asked"] is False
    assert state[contact.id]["overdue"] is True


def test_안_보낸_자료는_세지_않는다(db, users):
    """요청만 받고 아직 안 보낸 건은 이 숫자에 안 든다 — `아직 안 보냄` 이
    이미 세고 있고, 보내지도 않은 자료에 미팅을 청할 수는 없다."""
    from app.models import IrRequest

    contact = _contact(db, users, "가담당")
    db.add(IrRequest(user_id=users["u1"].id, contact_id=contact.id,
                     company_name="샘플애그",
                     requested_at=DELIVERED.isoformat(), status="open"))
    db.commit()

    assert _state(db, users, DELIVERED + timedelta(days=30)) == {}


# --- 6) 7 은 한 곳에만 -------------------------------------------------------

def test_이레는_한_곳에만_적혀_있다():
    """★ 같은 수를 여기저기 적으면 한 곳만 고쳐지고 화면과 코드가 갈린다.

    코드에 박힌 `7` 은 `pipeline.IR_MEETING_ASK_DAYS` 하나뿐이고,
    화면 안내문은 그 값을 읽어서 적는다.
    """
    import re
    from pathlib import Path

    from app.services import pipeline

    assert pipeline.IR_MEETING_ASK_DAYS == 7

    root = Path(pipeline.__file__).resolve().parents[1]
    watched = [root / "services" / "report.py",
               root / "routers" / "ir.py",
               root / "routers" / "data_io.py",
               root / "templates" / "ir.html",
               root / "templates" / "report.html"]
    for path in watched:
        text = path.read_text(encoding="utf-8")
        for line in text.splitlines():
            if "IR_MEETING_ASK_DAYS" in line or "meeting_ask_days" in line:
                continue
            assert not re.search(r"7\s*일\s*지남", line), \
                f"{path.name} 에 7 이 박혀 있다: {line.strip()}"


def test_화면_안내문이_그_값을_읽는다(db, users, logged):
    """안내문의 `7일` 은 상수에서 나온 것이어야 한다 — 값을 바꿔 보고 확인한다."""
    from app.services import pipeline

    contact = _contact(db, users, "가담당")
    _delivered(db, users, contact, "샘플애그",
               when=date.today() - timedelta(days=99))

    before = pipeline.IR_MEETING_ASK_DAYS
    try:
        pipeline.IR_MEETING_ASK_DAYS = 3
        body = logged.get("/ir").text
        assert "3일 지남" in body
        assert "7일 지남" not in body
    finally:
        pipeline.IR_MEETING_ASK_DAYS = before


# --- 보이는 자리 --------------------------------------------------------------

def test_전달한_자료_판에_뜬다(db, users, logged):
    """★ 실제로 화면에 뜨는가."""
    contact = _contact(db, users, "가담당")
    _delivered(db, users, contact, "샘플애그",
               when=date.today() - timedelta(days=30))

    body = logged.get("/ir").text
    assert "7일 지남" in body
    assert "미팅 요청 안 보냄 1명" in body
    assert f"/ir/contacts/{contact.id}/meeting-asked" in body


def test_보낸_줄에는_보냄과_날짜가_뜬다(db, users, logged):
    contact = _contact(db, users, "가담당")
    when = date.today() - timedelta(days=30)
    _delivered(db, users, contact, "샘플애그", when=when)
    _meeting_send(db, users, contact, when=when + timedelta(days=1))

    body = logged.get("/ir").text
    assert f"미팅 요청 보냄 · {(when + timedelta(days=1)).isoformat()}" in body
    assert "7일 지남" not in body
    # 이미 보낸 줄에는 표시할 단추가 없다 — 누를 일이 없는 단추는 소음이다.
    assert f"/ir/contacts/{contact.id}/meeting-asked" not in body


def test_업무_보고에_한_줄로_뜬다(db, users, logged):
    contact = _contact(db, users, "가담당")
    when = date.today().replace(day=1)
    _delivered(db, users, contact, "샘플애그", when=when)

    body = logged.get(f"/report?month={when.year}-{when.month:02d}").text
    assert "미팅 요청 안 보냄" in body


# --- 20 줄 잘림 ---------------------------------------------------------------

def test_지난_건은_스무_줄_밖으로_밀려도_보인다(db, users, logged):
    """★ 이 기능이 보여 주려는 것이 바로 **오래된 채로 말이 안 붙은 건**이다.

    `전달한 자료` 판은 최근 20줄만 그렸다. 오래된 것부터 밀려나가므로, 재촉할
    건은 정확히 잘려 나가는 쪽에 있다 — 그러면 세는 뜻이 없다.

    두 가지로 막는다. ① 지난 줄을 맨 위로 세운다 ② 지난 줄이 20보다 많으면
    그만큼 늘린다.
    """
    old = _contact(db, users, "가담당")
    _delivered(db, users, old, "샘플애그", when=date.today() - timedelta(days=60))

    # 그 뒤로 최근 건이 25줄 쌓였고 전부 미팅 요청까지 끝났다.
    fresh = _contact(db, users, "나담당")
    _delivered(db, users, fresh, "샘플메디", when=date.today())
    _meeting_send(db, users, fresh, when=date.today())
    for i in range(25):
        _delivered(db, users, fresh, f"샘플{i:02d}", when=date.today())

    body = logged.get("/ir").text
    assert "샘플애그" in body, "재촉할 건이 20줄 밖으로 밀려 사라졌다"
    assert "7일 지남" in body


def test_지난_줄이_스무_개를_넘어도_안_자른다(db, users, logged):
    contacts = [_contact(db, users, f"담당{i:02d}") for i in range(25)]
    for c in contacts:
        _delivered(db, users, c, f"샘플{c.id:02d}",
                   when=date.today() - timedelta(days=30))

    body = logged.get("/ir").text
    # 판 제목 옆 안내문에도 같은 말이 한 번 나오므로 **줄의 배지**만 센다.
    rows = body.count('class="status-when bad">7일 지남')
    assert rows == 25, rows
    assert "미팅 요청 안 보냄 25명" in body
