"""미팅을 **청한 것**과 **실제로 만난 것**이 갈려 있는가.

한 칸(`kind='meeting'`)에 뭉쳐 있을 때 고객사가 짚었다 — "그 심사역들은 실제로
미팅하신 상태가 아닙니다". 청하기만 한 줄이 화면에서 `1차 미팅` 으로 서고
엑셀의 `미팅(누적)` 에도 세어졌기 때문이다.

여기서 못 박는 것이 넷이다.

    ① 머리글이 제각각이어도 갈래가 갈린다 (`services/meeting_kind`)
    ② 판정이 **한 곳**이다 — 시트를 읽어 넣는 쪽과 이미 들어온 줄을 가르는
       스크립트가 같은 함수를 지난다
    ③ 사다리에서 요청은 미팅 칸이 아니다 (`services/deal_stage`)
    ④ 화면과 엑셀이 **같은 함수**를 쓰므로 한 곳만 고치면 둘 다 따라온다

이름·투자사명은 **전부 지어낸 값**이다(공개 저장소).
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.services import deal_stage
from app.services import meeting_kind as mk
from app.services import sheet_import as si


# ── ① 머리글 ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("header, want", [
    # 실제 시트에 서 있던 머리글들.
    ("3~5월 미팅 요청", mk.REQUEST),
    ("미팅 요청 / IR 요청기업 미팅 안내전화 TEL", mk.REQUEST),
    ("IR 요청기업 미팅 안내전화", mk.REQUEST),
    ("미팅완료 투자사", mk.DONE),
    # **전화를 건 것은 만난 것이 아니다.**
    ("9월 미팅 안내전화", mk.REQUEST),
    # 묻는 칸이다 — 답은 칸 안에 있다. 머리글로는 못 정한다.
    ("6~9월 미팅 진행 여부", None),
    # 두 갈래를 함께 이고 있다 — 역시 칸 안이 정한다.
    ("미팅확정/미팅완료", None),
    # 달마다 저절로 서는 칸의 이름이 이 모양이다
    # (`templates/contacts.html` · `services/monthly_columns`).
    ("9월 미팅 요청/안내전화/미팅완료", None),
    # 아무 말도 없는 머리글.
    ("8월 미팅", None),
])
def test_headers_split_into_kinds(header, want):
    assert mk.of_header(header) == want


@pytest.mark.parametrize("content, want", [
    ("8/20 미팅완료", mk.DONE),
    ("9/3 미팅 확정", mk.SET),
    ("미팅 요청함", mk.REQUEST),
    # 요청을 **완료**한 것이지 만난 것이 아니다. `완료` 글자에 낚이면 안 된다.
    ("미팅 요청 완료", mk.REQUEST),
    # 뒤에 적힌 사실이 앞의 계획을 덮는다.
    ("미팅 요청 → 8/20 미팅완료", mk.DONE),
    # 안 했다는 말이 섞이면 **못 정한 것**으로 둔다.
    ("미팅 미진행", None),
    ("미팅 취소", None),
    # 미팅 이야기가 아예 없는 잡담.
    ("검토 중", None),
    ("O", None),
])
def test_contents_split_into_kinds(content, want):
    assert mk.of_content(content) == want


def test_a_cell_without_meeting_words_is_left_alone():
    """`미팅` 글자조차 없는 줄은 스크립트가 손대지 않는다 — 추측이 되기 때문."""
    assert mk.mentions_meeting("8/20 미팅완료") is True
    assert mk.mentions_meeting("검토 중") is False


# ── ② 판정이 한 곳인가 ───────────────────────────────────────────────────────

def test_the_importer_keeps_no_words_of_its_own():
    """시트를 읽어 넣는 쪽은 `미팅` 글자가 있는지만 본다.

    갈래를 가르는 말이 여기 다시 적히면, 앞으로 들어오는 줄과 이미 들어와
    있는 줄을 가르는 스크립트가 **서로 다르게** 갈린다. 이 저장소가 되풀이해
    덴 자리다(`services/company_names` 가 같은 까닭으로 한 곳이 되었다).
    """
    assert dict(si._KIND_KEYWORDS)[si.KIND_MEETING] == ("미팅",)


def test_the_monthly_column_name_goes_to_the_same_judge():
    """달마다 서는 칸(`ContactColumn.kind`)의 글자도 **같은 함수**가 읽는다.

    그 칸에는 머리글 뒷말이 그대로 들어 있다(`services/monthly_columns.kind_of`).
    구분이 거기 이미 보존돼 있었는데 활동 이력 쪽이 뭉갠 것이 이번 버그다 —
    같은 글자를 두 곳이 각자 읽지 않게 판정을 하나로 둔다.
    """
    from app.services import monthly_columns

    assert mk.of_header(monthly_columns.kind_of("3월 미팅 요청")) == mk.REQUEST
    assert mk.of_header(monthly_columns.kind_of("8월 미팅완료 투자사")) == mk.DONE
    # 한 칸에 두 갈래가 적힌 이름은 머리글로 못 정한다 — 칸 안이 정한다.
    assert mk.of_header(
        monthly_columns.kind_of("9월 미팅 요청/안내전화/미팅완료")) is None


def test_the_importer_asks_the_one_module(monkeypatch):
    """머리글도 칸 안의 글도 **`meeting_kind` 를 지나서** 갈린다."""
    calls = []
    real_header, real_content = mk.of_header, mk.of_content

    def spy(name, real):
        def inner(text):
            calls.append(name)
            return real(text)
        return inner

    monkeypatch.setattr(mk, "of_header", spy("머리글", real_header))
    monkeypatch.setattr(mk, "of_content", spy("내용", real_content))

    assert si.detect_kind("9월 미팅 요청", "9월 미팅 요청") == si.KIND_MEETING_REQUEST
    si.parse_activity_cell("8/20 미팅완료", "2026-09", si.KIND_MEETING, 2026,
                           head="9월 미팅")
    assert calls == ["머리글", "내용"]


def test_column_kind_comes_from_the_header_not_the_first_row():
    """첫 담당자의 값 하나가 **칸 전체**의 갈래를 바꾸면 안 된다.

    헤더 문맥은 헤더 아래 1행까지 이어 붙인다(병합된 달 라벨을 따라가려고).
    그 1행은 보통 첫 담당자의 값이라, 거기 적힌 `8/20 미팅완료` 가 갈래를
    정해 버리면 나머지 담당자의 줄까지 통째로 '완료' 가 된다.
    """
    rows = [
        ["", "", "", "9월", "", ""],
        ["NO", "이름", "투자사명", "1차 딜소개", "IR 요청", "미팅 요청"],
        ["1", "가상담당", "가상투자", "9/2 가상기업", "", "8/20 미팅완료"],
    ]
    cols = si.detect_activity_columns(rows, header_idx=1, year=2026,
                                      skip_cols=range(0, 3))
    assert [c.kind for c in cols] == [
        si.KIND_DEAL_INTRO, si.KIND_IR_REQUEST, si.KIND_MEETING_REQUEST]

    # 그래도 **그 칸의 값**은 만난 줄이다 — 칸마다 내용이 한 번 더 본다.
    acts = si.parse_activity_cell("8/20 미팅완료", "2026-09",
                                  si.KIND_MEETING_REQUEST, 2026,
                                  head="9월 미팅 요청")
    assert [a.kind for a in acts] == [si.KIND_MEETING_DONE]


def test_an_ambiguous_header_lets_each_cell_decide():
    """`미팅확정/미팅완료` 한 칸에 두 갈래가 섞여 있다 — 줄마다 가른다."""
    head = "미팅확정/미팅완료"
    assert si.detect_kind(head, head) == si.KIND_MEETING     # 머리글로는 못 정한다

    for text, want in (("9/3 미팅확정", si.KIND_MEETING_SET),
                       ("8/20 미팅완료", si.KIND_MEETING_DONE),
                       ("검토 중", si.KIND_MEETING)):
        acts = si.parse_activity_cell(text, "2026-09", si.KIND_MEETING, 2026,
                                      head=head)
        assert [a.kind for a in acts] == [want], text


# ── ③ 사다리 ────────────────────────────────────────────────────────────────

@pytest.fixture()
def contact(db, users):
    from app.models import SheetOwner, VcContact

    db.add(SheetOwner(label="가상 명단", user_id=users["u1"].id))
    row = VcContact(user_id=users["u1"].id, name="가상담당", title="심사역",
                    firm="가상투자", source_sheet="가상 명단", channel_kakao=1)
    db.add(row)
    db.commit()
    return row


def _stage(db, contact, kind, content="미팅"):
    from app.models import ContactActivity

    db.query(ContactActivity).delete()
    db.add(ContactActivity(contact_id=contact.id, kind=kind, content=content,
                           happened_at=date.today().isoformat()))
    db.commit()
    return deal_stage.of_many(db, [contact.id])[contact.id]


def test_a_meeting_request_is_not_a_meeting(db, contact):
    """**청한 것은 미팅 칸이 아니다.** 고객사가 짚은 바로 그 줄이다.

    `INTRO` 인 까닭: 이 앱이 미팅 요청 카톡을 보냈을 때 올리는 칸과 같다
    (`deal_stage.SENT_STAGE` — 미팅 요청·리마인드도 딜소개를 보낸 뒤의 일이라
    `INTRO` 밑으로 안 내려간다). 같은 사실을 시트로 받았다고 다른 칸에 세우면
    두 사람이 같은 일을 하고도 다른 단계에 선다.
    """
    assert _stage(db, contact, mk.REQUEST) == deal_stage.INTRO


def test_a_confirmed_meeting_stands_where_a_planned_meeting_stands(db, contact):
    """`미팅확정` = 날짜는 잡혔다. 이 앱의 `Meeting(planned)` 과 같은 칸이다."""
    assert _stage(db, contact, mk.SET) == deal_stage.MEET_1


def test_a_finished_meeting_stands_where_a_done_meeting_stands(db, contact):
    """`미팅완료` = 만났다. `Meeting.status == 'done'` 과 같은 칸이다."""
    assert _stage(db, contact, mk.DONE) == deal_stage.MEET_DONE


def test_an_unsplit_row_keeps_todays_meaning(db, contact):
    """아직 안 가른 옛 줄은 **지금 뜻 그대로**다.

    여기서 먼저 낮추면, 스크립트를 돌리기도 전에 **진짜로 미팅한 사람들이**
    화면에서 빠진다. 그건 지금 버그의 반대 방향이라 더 나쁘다.
    """
    assert _stage(db, contact, mk.LEGACY) == deal_stage.MEET_1


def test_every_meeting_kind_has_a_rung():
    """갈래가 늘면 사다리도 같이 늘어야 한다 — 빠지면 그 줄이 조용히 안 읽힌다."""
    for kind in mk.ALL:
        assert kind in deal_stage.ACTIVITY_STAGE, kind


# ── ④ 화면과 엑셀 ───────────────────────────────────────────────────────────

def _rows(db, contact):
    from app.models import User
    from app.routers.contacts import contact_rows

    return {r["id"]: r for r in contact_rows(db, db.get(User, contact.user_id))}


def test_only_a_finished_meeting_is_counted(db, contact):
    """`미팅(최근)`·`미팅(누적)` 은 **만난 줄만** 센다."""
    from app.models import ContactActivity

    today = date.today()
    db.add_all([
        ContactActivity(contact_id=contact.id, kind=mk.REQUEST,
                        content="미팅 요청", happened_at=today.isoformat()),
        ContactActivity(contact_id=contact.id, kind=mk.SET,
                        content="9/3 미팅확정", happened_at=today.isoformat()),
        ContactActivity(contact_id=contact.id, kind=mk.DONE,
                        content="8/20 미팅완료",
                        happened_at=(today - timedelta(days=5)).isoformat()),
    ])
    db.commit()

    row = _rows(db, contact)[contact.id]
    assert row["meet_total"] == 1, "청한 줄·잡은 줄은 미팅으로 세지 않는다"
    assert row["meet_recent"] == 1
    assert row["reaction_tags"] == ["미팅 있음"]
    # 청하기만 한 담당자는 미팅 칸에 서지 않는다.
    assert row["deal_stage"] == deal_stage.MEET_DONE


def test_people_who_really_met_stay_meeting(db, contact):
    """**고치다가 진짜로 미팅한 사람이 빠지면 더 나쁘다.**

    완료·확정으로 갈린 줄, 그리고 아직 안 가른 옛 줄 — 셋 다 미팅으로 남는다.
    """
    from app.models import ContactActivity

    for kind, counted in ((mk.DONE, 1), (mk.LEGACY, 1), (mk.SET, 0),
                          (mk.REQUEST, 0)):
        db.query(ContactActivity).delete()
        db.add(ContactActivity(contact_id=contact.id, kind=kind,
                               content="미팅", happened_at=date.today().isoformat()))
        db.commit()
        assert _rows(db, contact)[contact.id]["meet_total"] == counted, kind


def test_the_screen_and_the_excel_read_one_function():
    """표와 엑셀이 **같은 줄**을 쓴다 — 한 곳만 고치면 둘 다 따라온다.

    엑셀 한 줄을 짓는 `_contact_row` 는 `contact_rows()` 가 만든 그 dict 를
    그대로 받아 칸을 꺼낸다. 세는 자리가 둘이 아니라는 것을 못 박는다.
    """
    from app.routers.data_io import _contact_row

    counted = {"meet_recent": 3, "meet_total": 7}
    fake = dict(counted, owner="", assignee="", connect_label="", group_name="",
                name="", title="", firm="", department="", channel_kakao=0,
                channel_email=0, room_name="", room_label="",
                invited_status="", interest_level="", round_size="",
                stages=[], sectors=[], phone="", email="", office_phone="",
                office_fax="", address="", card_registered_at="",
                last_deal="", last_deal_note="", ir_recent=1, ir_total=2,
                status_label="", memo="")
    line = _contact_row(fake)
    assert line.count(3) == 1 and line.count(7) == 1, \
        "엑셀이 미팅 수를 따로 세면 표와 갈린다"


# ── ⑤ 건드리면 안 되는 이웃들 ────────────────────────────────────────────────

def test_the_work_report_does_not_read_these_rows():
    """업무보고(`/report`)는 **`Meeting` 표**를 읽는다 — 이 갈래와 무관하다.

    이 표(`contact_activities`)를 아예 안 들여다보므로 갈래가 늘어도 보고의
    숫자는 한 칸도 안 움직인다. 확인만 하고 건드리지 않았다.
    """
    from app.services import report

    assert not hasattr(report, "ContactActivity"), \
        "업무보고가 활동 이력을 읽기 시작했다 — 미팅 갈래를 여기서도 봐야 한다"


def test_the_call_stage_still_sees_a_meeting_request_as_a_reaction(db, contact):
    """`STAGE_CALL`(미팅 요청 사흘 뒤 전화)과 부딪치지 않는다.

    전화 단계는 `SendSequence` 의 값이라 이 표와 칸이 다르다. 둘이 만나는
    자리는 **반응이 있었는가** 하나뿐인데(`cadence.has_reaction_since`), 거기서는
    청한 것도 반응이다 — 갈래가 넷으로 늘어도 답이 그대로여야 한다.
    """
    from app.models import ContactActivity
    from app.services import cadence

    since = date.today() - timedelta(days=3)
    assert cadence.has_reaction_since(db, contact.id, since.isoformat()) is False

    for kind in mk.ALL:
        db.query(ContactActivity).delete()
        db.add(ContactActivity(contact_id=contact.id, kind=kind, content="미팅",
                               happened_at=date.today().isoformat()))
        db.commit()
        assert cadence.has_reaction_since(
            db, contact.id, since.isoformat()) is True, kind

    # 전화 단계 자체는 이 표를 쓰지 않는다 — 값도 뜻도 그대로다.
    assert cadence.STAGE_LABELS[cadence.STAGE_CALL] == "전화 요청"
