"""마지막 일 — 단계를 건드리지 않고 **지금 무슨 일이 있었는지**를 말하는 칸.

## 무엇을 막는 검사인가

고객사의 말이 출발점이다.

    "격주로 딜 소개를 하다보니 딜소개에 있다가 IR 자료 요청에 있다가
     헷갈립니다. 8월에 IR 자료 요청하셨고 9월에 두 번 딜 소개가 나갔는데
     진행단계가 IR 자료 요청으로 되어 있어요."

고치는 길이 둘이었다.

  ① 단계를 '가장 최근 일' 로 바꾼다 — **고르지 않았다.** 운영에서 재 보니
     138명이 내려가고 오르는 사람은 0명, 미팅 흔적이 있는 22명 중 15명이
     미팅 칸에서 빠진다. `deal_stage` 가 사다리를 쥔 까닭(38~42줄)이 바로
     그것이다: *"미팅까지 갔다가 거절된 곳을 다시 찾을 수 없다."*
  ② 단계는 그대로 두고 **칸을 하나 세운다** — 이쪽이다.

그래서 이 PR 이 지켜야 하는 것은 하나다: **단계가 한 칸도 안 바뀐다.**
아래 첫 묶음이 그것을 못 박는다. 같은 자료를 두 값이 다르게 읽어야 하고
(단계는 안 움직이고 마지막 일만 움직인다), 사다리 자체도 그대로여야 한다.
"""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import pytest

from app.services import cadence, deal_stage, last_activity

from .conftest import DEMO_PASSWORD

ROOT = Path(__file__).resolve().parent.parent
CONTACTS_HTML = ROOT / "app" / "templates" / "contacts.html"
APP_CSS = ROOT / "app" / "static" / "css" / "app.css"
DEAL_STAGE_PY = ROOT / "app" / "services" / "deal_stage.py"


@pytest.fixture()
def contact(db, users):
    from app.models import SheetOwner, VcContact

    db.add(SheetOwner(label="내 명단", user_id=users["u1"].id))
    row = VcContact(user_id=users["u1"].id, name="홍길동", title="심사역",
                    firm="가나벤처스", source_sheet="내 명단", channel_kakao=1)
    db.add(row)
    db.commit()
    return row


def stage_of(db, contact) -> str:
    return deal_stage.of_many(db, [contact.id])[contact.id]


def last_of(db, contact):
    return last_activity.of_many(db, [contact.id]).get(contact.id)


def _the_complaint(db, contact):
    """고객사가 짚은 그 줄 — 8월에 IR 요청, 9월에 딜소개 두 번."""
    from app.models import ContactActivity

    db.add_all([
        ContactActivity(contact_id=contact.id, kind="ir_request",
                        happened_at="2026-08-19", content="샘플애그"),
        ContactActivity(contact_id=contact.id, kind="deal_intro",
                        happened_at="2026-09-02", content="7개사"),
        ContactActivity(contact_id=contact.id, kind="deal_intro",
                        happened_at="2026-09-16", content="5개사"),
    ])
    db.commit()


# ── ① 단계는 한 칸도 안 바뀐다 ─────────────────────────────────────────────

def test_단계는_그대로고_마지막_일만_움직인다(db, contact):
    """같은 줄을 두 값이 **다르게** 읽는다 — 그게 칸을 따로 세운 이유다."""
    _the_complaint(db, contact)

    # 단계는 사다리의 꼭대기 그대로다. 딜소개가 뒤에 나갔다고 내려가지 않는다.
    assert stage_of(db, contact) == deal_stage.IR_ASKED
    # 마지막 일은 그 뒤에 나간 9월 3주차 딜소개다 — 고객사가 쓴 바로 그 말.
    act = last_of(db, contact)
    assert act.day == "2026-09-16"
    assert act.text == "09/16 (9월 3주차) 딜소개"


def test_마지막_일을_세워도_단계는_어느_줄에서도_안_바뀐다(db, contact):
    """사다리의 칸마다 **단계는 그대로**인지 하나씩 본다.

    이 PR 이 단계를 한 칸이라도 움직였다면 여기가 빨개진다.
    """
    from app.models import ContactActivity, IrRequest, Meeting

    steps = []

    db.add(ContactActivity(contact_id=contact.id, kind="deal_intro",
                           happened_at="2026-08-19", content="7개사"))
    db.commit()
    steps.append((stage_of(db, contact), deal_stage.INTRO))

    db.add(IrRequest(user_id=contact.user_id, contact_id=contact.id,
                     company_name="샘플애그", status="open",
                     requested_at="2026-08-26"))
    db.commit()
    steps.append((stage_of(db, contact), deal_stage.IR_ASKED))

    db.add(Meeting(user_id=contact.user_id, contact_id=contact.id, kind="first",
                   status="done", scheduled_at="2026-09-01", done_at="2026-09-01"))
    db.commit()
    steps.append((stage_of(db, contact), deal_stage.MEET_DONE))

    # **미팅 완료 뒤에 딜소개가 또 나가도** 단계는 내려가지 않는다.
    db.add(ContactActivity(contact_id=contact.id, kind="deal_intro",
                           happened_at="2026-09-16", content="5개사"))
    db.commit()
    steps.append((stage_of(db, contact), deal_stage.MEET_DONE))

    assert [got for got, _ in steps] == [want for _, want in steps]
    # 그런데 마지막 일은 그 딜소개다 — 두 값이 서로 다른 질문에 답한다.
    assert last_of(db, contact).label == "딜소개"


def test_사다리와_되돌아가지_않는다는_근거는_그대로다():
    """`deal_stage` 의 사다리·`raise_to` 는 이 PR 이 건드리지 않는다.

    칸을 하나 세우면서 "이왕이면 단계도" 로 번지는 것이 이 자리의 사고다.
    사다리 순서와 그 근거가 적힌 문장을 함께 못 박아 둔다 — 문장이 지워지면
    다음 사람이 왜 안 내려가는지를 모른 채 내리게 된다.
    """
    assert deal_stage.LADDER == [
        deal_stage.NONE, deal_stage.INTRO, deal_stage.IR_ASKED,
        deal_stage.IR_SENT, deal_stage.MEET_1, deal_stage.MEET_2,
        deal_stage.MEET_DONE,
    ]
    # 올리기만 한다.
    assert deal_stage.higher(deal_stage.MEET_DONE, deal_stage.INTRO) == deal_stage.MEET_DONE
    assert deal_stage.higher(deal_stage.INTRO, deal_stage.MEET_DONE) == deal_stage.MEET_DONE

    src = DEAL_STAGE_PY.read_text(encoding="utf-8")
    assert "거절당해도 단계는 내려가지 않는다" in src
    assert "미팅까지 갔다가" in src


def test_대시보드의_단계_링크가_그대로_동작한다(client, db, contact):
    """`/contacts?dealstage=…` 는 대시보드에서 눌러 들어오는 길이다.

    칸을 하나 끼워 넣으면서 머리글의 필터 선언을 밀어 버리면, `filters.js` 가
    그 쿼리를 **아무 말 없이** 통째로 버린다 — 눌러도 전원이 그대로 나온다.
    """
    _the_complaint(db, contact)
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    body = client.get("/contacts").text

    assert "dealstage:진행 단계" in body                 # 머리글이 선언한다
    assert 'data-f-dealstage="IR 자료 요청"' in body     # 줄이 값을 싣는다
    assert "connect:연결 상태" in body                   # 같은 칸의 둘째 필터도


# ── ② 무엇을 '일' 로 세는가 ────────────────────────────────────────────────

def test_딜소개만이_아니라_IR과_미팅까지_본다(db, contact):
    """칸 이름이 `마지막 일` 이다 — 딜소개만 보면 IR 을 요청한 그 다음 날에도
    지난달 딜소개를 보여 준다. 화면이 낡은 값을 말하는 것, 지금 고치는 그 버그다.
    """
    from app.models import ContactActivity, IrRequest, Meeting

    db.add(ContactActivity(contact_id=contact.id, kind="deal_intro",
                           happened_at="2026-09-02", content="7개사"))
    db.commit()
    assert last_of(db, contact).label == "딜소개"

    request = IrRequest(user_id=contact.user_id, contact_id=contact.id,
                        company_name="샘플애그", status="open",
                        requested_at="2026-09-04")
    db.add(request)
    db.commit()
    assert last_of(db, contact).text == "09/04 (9월 1주차) IR 자료 요청"

    request.status = "delivered"
    request.delivered_at = "2026-09-07"
    db.commit()
    assert last_of(db, contact).text == "09/07 (9월 1주차) IR 자료 전달"

    meeting = Meeting(user_id=contact.user_id, contact_id=contact.id,
                      kind="first", status="planned", scheduled_at="2026-09-18")
    db.add(meeting)
    db.commit()
    assert last_of(db, contact).text == "09/18 (9월 3주차) 미팅 확정"

    meeting.status = "done"
    meeting.done_at = "2026-09-18"
    db.commit()
    assert last_of(db, contact).text == "09/18 (9월 3주차) 미팅 완료"


def test_청하기만_한_미팅을_만났다고_적지_않는다(db, contact):
    """고객사가 짚었던 그 거짓말이 이 칸에서 다시 나면 안 된다.

    사다리는 `미팅 요청` 을 `1차 딜소개` 칸으로 친다(청했을 뿐 안 만났으므로).
    그건 *어디까지 갔나*의 답으로는 맞지만 *마지막으로 무엇을 했나*의 답으로는
    틀리다 — 그날 있었던 일은 미팅 요청이지 딜소개가 아니다.
    """
    from app.models import ContactActivity
    from app.services import meeting_kind as mk

    db.add(ContactActivity(contact_id=contact.id, kind=mk.REQUEST,
                           happened_at="2026-09-10", content="미팅 요청"))
    db.commit()

    assert stage_of(db, contact) == deal_stage.INTRO        # 사다리는 그대로
    assert last_of(db, contact).label == "미팅 요청"        # 칸은 있었던 일 그대로


def test_안_나간_발송은_세지_않는다(db, contact):
    """`pending`·`failed` 를 세면 **보낸 적 없는 사람**에게 날짜가 붙는다.

    거르는 값은 `deal_stage` 와 같은 곳에서 읽는다(`SENT_STATUS`·`SEND_KINDS`).
    """
    from app.models import SendItem, SendJob

    job = SendJob(user_id=contact.user_id, kind="deal_intro", status="done")
    db.add(job)
    db.flush()
    db.add(SendItem(job_id=job.id, contact_id=contact.id, channel="kakao",
                    room_name="가나벤처스 홍길동", message="…", status="failed"))
    db.commit()
    assert last_of(db, contact) is None

    db.add(SendItem(job_id=job.id, contact_id=contact.id, channel="kakao",
                    room_name="가나벤처스 홍길동", message="…", status="sent",
                    sent_at="2026-09-16T11:00:00+09:00"))
    db.commit()
    assert last_of(db, contact).text == "09/16 (9월 3주차) 딜소개"


def test_근거가_하나_늘면_이_칸도_같이_안다():
    """`deal_stage` 는 아는데 이 모듈이 모르는 근거가 있으면 안 된다.

    있으면 단계는 오르는데 `마지막 일` 칸만 낡은 값에 머무는 줄이 생긴다 —
    이 저장소가 `SEND_KINDS` 에서 이미 데인 모양 그대로다.
    """
    assert last_activity.missing_kinds() == []


def test_한_번에_묻는다(db, users):
    """행마다 물으면 800명 표에서 질의가 수천 번 나간다."""
    from sqlalchemy import event

    from app.models import ContactActivity, SheetOwner, VcContact

    db.add(SheetOwner(label="큰 명단", user_id=users["u1"].id))
    ids = []
    for i in range(50):
        row = VcContact(user_id=users["u1"].id, name=f"담당{i}", firm=f"투자사{i}",
                        source_sheet="큰 명단", channel_kakao=1)
        db.add(row)
        db.flush()
        db.add(ContactActivity(contact_id=row.id, kind="deal_intro",
                               happened_at="2026-09-16", content="7개사"))
        ids.append(row.id)
    db.commit()

    seen = []

    def count(*_args, **_kwargs):
        seen.append(1)

    event.listen(db.bind, "before_cursor_execute", count)
    try:
        got = last_activity.of_many(db, ids)
    finally:
        event.remove(db.bind, "before_cursor_execute", count)

    assert len(got) == 50
    assert len(seen) <= 5, f"담당자 50명에 질의 {len(seen)}번 — 행마다 묻고 있다"


# ── ③ 주차 이름은 저장소에 하나뿐인 규칙에서 나온다 ────────────────────────

def test_주차_이름은_회차명과_한_글자도_다르지_않다():
    """`09/16 (9월 3주차)` 는 회차명이다 — 업무보고·발송 이력이 쓰는 그 말.

    만드는 곳이 둘이 되면 같은 날이 화면마다 3주차·4주차로 갈린다.
    여기서 새로 세지 않고 `cadence.batch_title` 을 그대로 부르는지 본다.
    """
    from app.services import sheet_import, weekly

    for day in ("2026-09-01", "2026-09-07", "2026-09-08", "2026-09-16",
                "2026-08-26", "2026-12-31"):
        act = last_activity.LastActivity(day=day, kind=last_activity.DEAL)
        assert act.title == cadence.batch_title(date.fromisoformat(day))

    # 1~7일이 1주차. 주차를 세는 규칙 자체도 저장소에 하나뿐이다.
    assert last_activity.LastActivity(day="2026-09-07", kind=last_activity.DEAL).title \
        == "09/07 (9월 1주차)"
    assert last_activity.LastActivity(day="2026-09-08", kind=last_activity.DEAL).title \
        == "09/08 (9월 2주차)"
    assert sheet_import.week_of_month("2026-09-16") == 3
    assert weekly.week_of_month(date(2026, 9, 16)) == 3


def test_부르는_말을_여기서_새로_짓지_않는다():
    """`딜소개`·`IR 자료 요청`·`미팅 완료` 는 이미 쓰고 있는 말이다.

    여기 또 적으면 말이 바뀌는 날 이 칸만 옛말을 단 채 남는다.
    """
    from app.services import meeting_kind as mk

    assert last_activity.LABELS[last_activity.DEAL] \
        == cadence.STAGE_LABELS[cadence.STAGE_DAY1]
    assert last_activity.LABELS[last_activity.IR_ASKED] \
        == deal_stage.LABELS[deal_stage.IR_ASKED]
    assert last_activity.LABELS[last_activity.IR_SENT] \
        == deal_stage.LABELS[deal_stage.IR_SENT]
    assert last_activity.LABELS[last_activity.MEET_DONE] == mk.LABELS[mk.DONE]


# ── ④ 화면과 엑셀 ──────────────────────────────────────────────────────────

def test_표에_칸이_서고_값이_찬다(client, db, contact):
    _the_complaint(db, contact)
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    body = client.get("/contacts").text

    assert ">마지막 일</th>" in body
    assert "09/16 (9월 3주차) 딜소개" in body
    # 회차 내용은 말풍선에서 본다 — 칸에 넣으면 IR·미팅 줄의 폭만 비운다.
    assert 'title="09/16 (9월 3주차) 딜소개 · 5개사"' in body


def test_일이_없는_줄은_빈_칸이_아니라_대시다(client, db, contact):
    """빈 칸은 "아직 아무 일도 없었다" 로도 "못 읽었다" 로도 읽힌다."""
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    body = client.get("/contacts").text
    assert '<span class="muted">—</span>' in body


def test_칸은_진행_단계_바로_옆에_선다():
    """헷갈린다고 한 것이 이 두 값이다 — 나란히 서야 견줄 수 있다."""
    html = re.sub(r"\{#.*?#\}", "", CONTACTS_HTML.read_text(encoding="utf-8"), flags=re.S)
    head = re.search(r'id="contacts-table".*?<thead>(.*?)</thead>', html, re.S).group(1)
    names = re.findall(r"<th[^>]*>(?:<[^>]+>)*([^<]*)", head)
    names = [n.strip() for n in names]
    assert "마지막 일" in names
    assert names[names.index("진행 단계") + 1] == "마지막 일"


def test_표_폭은_칸_폭_합을_담는다():
    """`table-layout: fixed` 는 표가 합보다 좁으면 칸을 비율대로 눌러 버린다.

    그러면 머리글이 한 줄 더 접힌다 — 칸을 늘리고 min-width 를 안 올린 날
    이 저장소가 겪은 자리다(app.css 의 그 주석).
    """
    html = re.sub(r"\{#.*?#\}", "", CONTACTS_HTML.read_text(encoding="utf-8"), flags=re.S)
    head = re.search(r'id="contacts-table".*?<thead>(.*?)</thead>', html, re.S).group(1)
    total = sum(int(w) for w in re.findall(r"width:(\d+)px", head))
    css = APP_CSS.read_text(encoding="utf-8")
    got = int(re.search(r"#contacts-table \{ min-width: (\d+)px", css).group(1))
    assert got >= total, (
        f"#contacts-table min-width {got}px 가 칸 폭 합 {total}px 보다 좁다 — "
        "칸이 비율대로 눌려 머리글이 접힌다")


def test_엑셀에도_같은_줄이_나간다(client, db, contact):
    """화면과 엑셀이 **같은 값**을 쓴다. 두 곳에 적으면 한쪽만 고쳐진다.

    `마지막 딜소개`·`회차 메모` 와 겹치지 않는다 — 저쪽은 딜소개만 보고
    이쪽은 그 뒤에 온 IR·미팅까지 본다.
    """
    from app.routers import data_io

    assert "마지막 일" in data_io.CONTACT_HEADERS
    assert "마지막 딜소개" in data_io.CONTACT_HEADERS      # 둘 다 남는다

    _the_complaint(db, contact)
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    from app.routers.contacts import contact_rows
    from app.models import User

    user = db.get(User, contact.user_id)
    row = contact_rows(db, user)[0]
    line = data_io._contact_row(row)
    assert len(line) == len(data_io.CONTACT_HEADERS), "머리글과 값이 한 칸씩 밀린다"
    assert line[data_io.CONTACT_HEADERS.index("마지막 일")] == "09/16 (9월 3주차) 딜소개"
    assert line[data_io.CONTACT_HEADERS.index("마지막 딜소개")] == "2026-09-16"
