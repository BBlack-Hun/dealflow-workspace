"""진행 단계 — 어디까지 갔는지가 맞게 매겨지는가.

"IR 있음 / 미팅 있음" 태그로는 *IR 자료까지 보냈는데 미팅으로 못 넘어간 곳*을
골라낼 수 없었다. 단계를 매기는 규칙이 어긋나면 그 명단이 통째로 틀어지므로
사다리의 각 칸을 하나씩 못 박는다.
"""
from __future__ import annotations

from datetime import date

import pytest

from app.services import deal_stage

from .conftest import DEMO_PASSWORD


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


def test_nothing_yet(db, contact):
    assert stage_of(db, contact) == deal_stage.NONE


def test_imported_history_counts(db, contact):
    """시트에서 옮겨 온 기록만 있어도 단계가 매겨져야 한다.

    이걸 놓치면 옮겨 오기 전 담당자 300여 명이 전부 '접촉 전'으로 보인다.
    """
    from app.models import ContactActivity

    db.add(ContactActivity(contact_id=contact.id, kind="deal_intro",
                           happened_at="2025-06-04", content="7개사"))
    db.commit()
    assert stage_of(db, contact) == deal_stage.INTRO

    db.add(ContactActivity(contact_id=contact.id, kind="ir_request",
                           happened_at="2025-06-10", content="샘플애그"))
    db.commit()
    assert stage_of(db, contact) == deal_stage.IR_ASKED


def test_request_then_delivery(db, contact):
    from app.models import IrRequest

    request = IrRequest(user_id=contact.user_id, contact_id=contact.id,
                        company_name="샘플애그", status="open",
                        requested_at=date.today().isoformat())
    db.add(request)
    db.commit()
    assert stage_of(db, contact) == deal_stage.IR_ASKED

    request.status = "delivered"
    db.commit()
    assert stage_of(db, contact) == deal_stage.IR_SENT


def test_meetings_climb(db, contact):
    from app.models import Meeting

    first = Meeting(user_id=contact.user_id, contact_id=contact.id,
                    kind="first", status="planned",
                    scheduled_at=date.today().isoformat())
    db.add(first)
    db.commit()
    assert stage_of(db, contact) == deal_stage.MEET_1

    second = Meeting(user_id=contact.user_id, contact_id=contact.id,
                     kind="second", status="planned",
                     scheduled_at=date.today().isoformat())
    db.add(second)
    db.commit()
    assert stage_of(db, contact) == deal_stage.MEET_2

    second.status = "done"
    db.commit()
    assert stage_of(db, contact) == deal_stage.MEET_DONE


def test_it_never_goes_back_down(db, contact):
    """거절당해도 '미팅까지 갔던 곳'은 그대로다.

    단계는 *지금 상태*가 아니라 *어디까지 갔나*다. 거절을 단계로 덮어쓰면
    미팅까지 갔다가 거절된 명단 — 제일 아까운 명단 — 을 다시 못 찾는다.
    """
    from app.models import ContactActivity, Meeting

    db.add_all([
        Meeting(user_id=contact.user_id, contact_id=contact.id, kind="first",
                status="done", outcome="pass",
                scheduled_at=date.today().isoformat()),
        # 나중에 딜소개를 한 번 더 보냈다고 단계가 내려가면 안 된다
        ContactActivity(contact_id=contact.id, kind="deal_intro",
                        happened_at="2025-08-06", content="7개사"),
    ])
    contact.status = "declined"
    db.commit()
    assert stage_of(db, contact) == deal_stage.MEET_DONE


def test_one_query_per_kind_not_per_contact(db, users):
    """300명 표에서 행마다 묻지 않는지. 느려지면 표가 못 쓰게 된다."""
    from sqlalchemy import event

    from app.models import ContactActivity, VcContact

    ids = []
    for i in range(50):
        row = VcContact(user_id=users["u1"].id, name=f"담당{i}")
        db.add(row)
        db.flush()
        db.add(ContactActivity(contact_id=row.id, kind="deal_intro",
                               happened_at="2025-06-04", content="7개사"))
        # 앱 발송도 근거다. 그 근거를 더하면서 **행마다 묻기 시작하면** 300명
        # 표에서 질의가 다시 폭발한다 — 그래서 여기에도 함께 심는다.
        _item(db, _job(db, row), row.id)
        ids.append(row.id)
    db.commit()

    seen = []

    def count(*_args, **_kwargs):
        seen.append(1)

    event.listen(db.bind, "before_cursor_execute", count)
    try:
        result = deal_stage.of_many(db, ids)
    finally:
        event.remove(db.bind, "before_cursor_execute", count)

    assert len(result) == 50
    assert all(v == deal_stage.INTRO for v in result.values())
    assert len(seen) <= 5, f"담당자 50명에 질의 {len(seen)}번 — 행마다 묻고 있다"


def test_funnel_keeps_empty_steps():
    """0명인 칸을 지우면 어디서 끊겼는지가 안 보인다."""
    rows = deal_stage.funnel({1: deal_stage.INTRO, 2: deal_stage.INTRO,
                              3: deal_stage.MEET_DONE})
    assert [r["key"] for r in rows] == deal_stage.LADDER
    counts = {r["label"]: r["count"] for r in rows}
    assert counts["1차 딜소개"] == 2
    assert counts["IR 자료 전달"] == 0
    assert counts["미팅 완료"] == 1


def test_table_shows_the_stage_and_can_filter_on_it(client, db, contact):
    from app.models import ContactActivity

    db.add(ContactActivity(contact_id=contact.id, kind="ir_request",
                           happened_at="2025-06-10", content="샘플애그"))
    db.commit()

    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    body = client.get("/contacts").text

    assert 'data-f-dealstage="IR 자료 요청"' in body      # 행에 값이 붙는다
    assert "dealstage:진행 단계" in body                  # 컬럼 필터가 열린다
    assert "funnel-step" in body                          # 눌러서 거를 수 있다


# ── 이 앱으로 보낸 것도 근거다 ───────────────────────────────────────────────
#
# 딜소개를 앱으로 보냈는데 표에서 `접촉 전` 으로 남았다(메일도 같았다). 근거가
# `ContactActivity` · `IrRequest` · `Meeting` 셋뿐이라 **실제로 나간 발송 건**을
# 아예 안 봤기 때문이다. 지금까지 대부분 맞아 보인 것은 시트에서 옮겨 온 옛
# 기록이 같이 있어서지 앱 발송을 세어서가 아니었다 — 옛 기록이 없는 사람(앞으로
# 새로 넣는 사람은 전부 여기 든다)은 보내도 `접촉 전` 에 남았다.

def _job(db, contact, kind: str = "deal_intro"):
    from app.models import SendJob

    job = SendJob(user_id=contact.user_id, kind=kind, status="done")
    db.add(job)
    db.flush()
    return job


def _item(db, job, contact_id, status: str = "sent", channel: str = "kakao"):
    from app.models import SendItem

    row = SendItem(job_id=job.id, contact_id=contact_id, channel=channel,
                   room_name="가나벤처스 홍길동", message="…",
                   status=status,
                   sent_at=("2025-09-01T10:00:00+09:00"
                            if status == "sent" else None))
    db.add(row)
    db.flush()
    return row


def test_an_app_send_alone_raises_the_stage(db, contact):
    """**시트 기록이 하나도 없어도** 앱으로 보냈으면 `1차 딜소개` 다.

    운영에서 앱으로만 보낸 담당자 13명이 `접촉 전` 에 서 있었다. 앞으로 넣는
    사람에게는 옛 기록이 아예 없으므로 전부 이 자리에 걸린다.
    """
    assert stage_of(db, contact) == deal_stage.NONE      # 아직 아무 근거도 없다

    _item(db, _job(db, contact), contact.id)
    db.commit()

    assert stage_of(db, contact) == deal_stage.INTRO


def test_mail_counts_the_same_as_kakao(db, contact):
    """메일도 같은 길이다 — 다른 것은 `channel` 뿐이다."""
    _item(db, _job(db, contact), contact.id, channel="email")
    db.commit()

    assert stage_of(db, contact) == deal_stage.INTRO


@pytest.mark.parametrize("status", ["pending", "sending", "failed", "canceled"])
def test_what_never_went_out_does_not_count(db, contact, status):
    """**안 나간 것을 보냈다고 세면 안 된다.**

    운영에는 `failed` 235 · `canceled` 156 · `pending` 15 건이 있다. 그것을
    세면 보낸 적 없는 사람이 `1차 딜소개` 로 서고, 그건 이 버그의 반대 방향이라
    더 나쁘다 — 정작 보내야 할 사람이 명단에서 빠진다.
    """
    _item(db, _job(db, contact), contact.id, status=status)
    db.commit()

    assert stage_of(db, contact) == deal_stage.NONE


def test_ir_delivery_send_raises_to_ir_sent_without_a_request_row(db, contact):
    """자료를 보냈으면 `IR 자료 전달` 이다 — 요청 줄이 없어도.

    `IrRequest.status == "delivered"` 도 같은 칸을 올리지만 둘이 겹치지 않는
    자리가 있다: 딜 제안 관리에서 요청 줄 없이 바로 보낸 건은 `IrRequest` 에
    아무 자국도 안 남는다(`pipeline.close_requests_for` 는 **이름이 맞는
    `open`** 요청만 닫는다). 그때 근거가 되는 것은 나간 발송 건뿐이다.
    """
    _item(db, _job(db, contact, kind="ir_delivery"), contact.id)
    db.commit()

    assert stage_of(db, contact) == deal_stage.IR_SENT


def test_counting_it_twice_changes_nothing(db, contact):
    """같은 사건이 두 곳에 남아도 단계는 하나다 — 개수가 아니라 **가장 먼 칸**."""
    from app.models import IrRequest

    db.add(IrRequest(user_id=contact.user_id, contact_id=contact.id,
                     company_name="샘플애그", status="delivered",
                     requested_at=date.today().isoformat(),
                     delivered_at=date.today().isoformat()))
    _item(db, _job(db, contact, kind="ir_delivery"), contact.id)
    db.commit()

    assert stage_of(db, contact) == deal_stage.IR_SENT


def test_a_send_never_pulls_the_stage_back_down(db, contact):
    """미팅까지 간 곳에 딜소개를 한 번 더 보내도 내려가지 않는다."""
    from app.models import Meeting

    db.add(Meeting(user_id=contact.user_id, contact_id=contact.id,
                   kind="first", status="done",
                   scheduled_at=date.today().isoformat()))
    _item(db, _job(db, contact), contact.id)
    db.commit()

    assert stage_of(db, contact) == deal_stage.MEET_DONE


def test_kinds_outside_send_kinds_do_not_count(db, contact):
    """방 연결 확인·시험 발송·스타트업 월간 발송은 투자사에게 보낸 것이 아니다.

    셋 다 끝나면 `status="sent"` 로 남는다 — 종류로 거르지 않으면 방 확인만
    눌러도 단계가 오른다(`models.SEND_KINDS` 주석의 그 자리다).
    """
    from app.models import STARTUP_SEND_KIND, TEST_SEND_KIND

    for kind in ("verify_room", TEST_SEND_KIND, STARTUP_SEND_KIND):
        _item(db, _job(db, contact, kind=kind), contact.id)
    db.commit()

    assert stage_of(db, contact) == deal_stage.NONE


def test_a_sourcing_send_does_not_raise_the_investor_with_that_number(db, contact):
    """소싱 명단으로 나간 줄이 **번호가 같은 투자사**의 단계를 올리면 안 된다.

    받는 줄은 세 표에 나뉘고 `SendItem` 은 셋 중 한 칸만 채운다
    (`contact_id` · `sourcing_contact_id` · `ir_company_id`). 이 모듈이 세는
    것은 `contact_id` 뿐인데, 표가 다르니 번호는 얼마든지 겹친다.
    """
    from app.models import SourcingContact

    db.add(SourcingContact(id=contact.id, bucket="시리즈 A 이상",
                           name="다른사람", firm="다른벤처스"))
    db.flush()
    job = _job(db, contact, kind="sourcing_intro")
    item = _item(db, job, None)
    item.sourcing_contact_id = contact.id
    db.commit()

    assert stage_of(db, contact) == deal_stage.NONE


def test_every_send_kind_says_which_rung_it_means():
    """`SEND_KINDS` 에 종류가 늘면 **어느 칸인지 정하고 지나가야 한다.**

    빠뜨리면 조용히 안 세어진다 — 이 저장소가 `SEND_KINDS` 에서 이미 데인
    모양 그대로다(세는 곳이 여럿이라 각자 걸러 두면 한 곳이 빠진다).
    """
    from app.models import SEND_KINDS

    assert set(deal_stage.SENT_STAGE) == set(SEND_KINDS)


def test_the_funnel_and_the_table_filter_agree_after_an_app_send(client, db, contact):
    """깔때기와 표 필터가 **같은 값**을 쓰는지 — 앱 발송 뒤에도.

    깔때기는 표에 실린 `deal_stage` 를 그대로 세고(`routers/pages.py`), 표 필터는
    같은 줄의 한글 이름으로 거른다. 둘이 갈리면 `1차 딜소개` 를 눌렀는데 아무도
    안 나오는 화면이 된다.
    """
    _item(db, _job(db, contact), contact.id)
    db.commit()

    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    body = client.get("/contacts").text

    assert 'data-f-dealstage="1차 딜소개"' in body          # 표의 줄
    assert '<b>1</b><span>1차 딜소개</span>' in body        # 깔때기의 수
    assert '<b>0</b><span>접촉 전</span>' in body           # 더는 여기 없다
