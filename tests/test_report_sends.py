"""업무 보고의 **발송** 부분 — 회차를 손으로 세지 않는다.

회차가 끝나면 카톡으로 이런 보고를 손으로 써서 보내고 있었다.

    딜소개 업무(핵심 딜 7개사)
    - 총 126명
    116개[8/27(목) 116개 완료]

    딜 소싱 2건(8/27(목)) 완료

그 `116개 완료` 가 틀린 값이었다. 그 회차는 대상 116명 중 **18건에서
중단**됐는데, 대상 수를 그대로 옮겨 적은 것이다. 손으로 세면 이렇게 된다.

여기 검사들이 못 박는 것은 하나다 — **안 나간 건은 완료가 아니다.**
"""
from __future__ import annotations

from datetime import date

import pytest

from .conftest import DEMO_PASSWORD


@pytest.fixture()
def logged(client, users):
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    return client


def _people(db, users, count, *, user_key="u1", sourcing=False):
    """받는 사람 `count` 명. 이름이 같으면 **같은 사람**이다.

    회차 둘의 대상이 겹치는 상황을 만들 수 있어야 한다 — 그래야 '총 N명' 이
    겹친 사람을 두 번 세는지 잴 수 있다.
    """
    from app.models import SourcingContact, VcContact

    out = []
    for i in range(count):
        name = f"{'소싱대상' if sourcing else '담당자'}{i}"
        if sourcing:
            row = db.query(SourcingContact).filter_by(name=name).first()
            if row is None:
                row = SourcingContact(bucket="시리즈A 이상", name=name)
        else:
            row = db.query(VcContact).filter_by(name=name).first()
            if row is None:
                row = VcContact(user_id=users[user_key].id, name=name,
                                firm="가나벤처스")
        db.add(row)
        out.append(row)
    db.flush()
    return out


def _round(db, users, *, title, when, kind="deal_intro", user_key="u1",
           sent=0, canceled=0, failed=0, pending=0, companies=0,
           deals="핵심딜", status="done", sent_date=True):
    """회차 하나. 발송 목록의 **건별 상태**까지 그대로 만든다.

    보고가 세는 것은 잡에 적힌 `sent` 칸이 아니라 실제 발송 건이라,
    건을 만들지 않으면 아무것도 재지 못한다.

    `deals` 가 같으면 **같은 기업**을 소개한 회차다 — 중단된 회차를 다시 돌리면
    같은 딜을 다시 보내게 되므로, 그 경우가 기본이다.
    """
    from app.models import (DealBatch, DealBatchCompany, IrCompany, SendItem,
                            SendJob)

    batch = DealBatch(user_id=users[user_key].id, title=title,
                      sent_date=when.isoformat() if sent_date else None)
    db.add(batch)
    db.flush()
    for pos in range(1, companies + 1):
        name = f"{deals}{pos}"
        company = db.query(IrCompany).filter_by(name=name).first()
        if company is None:
            company = IrCompany(name=name)
            db.add(company)
            db.flush()
        db.add(DealBatchCompany(batch_id=batch.id, company_id=company.id,
                                position=pos))

    total = sent + canceled + failed + pending
    job = SendJob(user_id=users[user_key].id, kind=kind, batch_id=batch.id,
                  status=status, total=total, sent=sent, failed=failed,
                  started_at=f"{when.isoformat()}T11:00:00+09:00")
    db.add(job)
    db.flush()

    who = _people(db, users, total, user_key=user_key,
                  sourcing=(kind == "sourcing_intro"))
    plan = (["sent"] * sent + ["canceled"] * canceled
            + ["failed"] * failed + ["pending"] * pending)
    for contact, item_status in zip(who, plan):
        db.add(SendItem(
            job_id=job.id,
            contact_id=None if kind == "sourcing_intro" else contact.id,
            sourcing_contact_id=contact.id if kind == "sourcing_intro" else None,
            room_name=f"{contact.name} 방", message="본문",
            status=item_status,
            sent_at=(f"{when.isoformat()}T11:20:00+09:00"
                     if item_status == "sent" else None),
        ))
    db.commit()
    return job


def _group(data, key):
    return next(g for g in data["sends"]["groups"] if g["key"] == key)


# --- 안 나간 건은 완료가 아니다 -------------------------------------------------

def test_a_stopped_round_is_not_counted_as_done(db, users):
    """**이 검사가 이 파일의 이유다.**

    대상 116명, 18건에서 중단. 손으로 쓴 보고는 `116개 완료` 였다.
    """
    from app.services import report

    _round(db, users, title="08/27 (8월 4주차)", when=date(2026, 8, 27),
           sent=18, canceled=98, status="canceled")

    data = report.monthly(db, 2026, 8, users["u1"], today=date(2026, 8, 31))
    row = _group(data, "deal_intro")["rows"][0]

    assert row["target"] == 116, "대상은 116명이었다"
    assert row["sent"] == 18, "실제로 나간 것은 18건 — 116 이 아니다"
    assert row["left"] == 98, "안 나간 98건이 드러나야 한다"
    assert data["sends"]["sent"] == 18
    assert data["sends"]["left"] == 98
    assert data["sends"]["short"] == 1, "끝까지 못 간 회차가 있다고 말해야 한다"
    # 화면에서 파란 '완료' 배지와 섞이면 안 된다.
    assert row["status_label"] == "중단됨"
    assert row["level"] == "bad"
    assert row["left_label"] == "중단 98건"


def test_failed_items_are_not_done_either(db, users):
    """실패도 안 나간 것이다 — '완료(실패 있음)' 을 완료 건수로 세면 안 된다."""
    from app.services import report

    _round(db, users, title="8월 1주차", when=date(2026, 8, 5),
           sent=10, failed=3, status="done_with_errors")

    row = _group(report.monthly(db, 2026, 8, users["u1"],
                                today=date(2026, 8, 31)), "deal_intro")["rows"][0]
    assert (row["target"], row["sent"], row["left"]) == (13, 10, 3)
    assert row["failed"] == 3
    assert row["level"] == "warn"
    # 왜 안 나갔는지가 남아야 다시 돌릴 것인지 판단할 수 있다
    assert row["left_label"] == "실패 3건"


def test_a_finished_round_has_nothing_left(db, users):
    """다 나간 회차는 조용해야 한다 — 늘 경고가 뜨면 아무도 안 본다."""
    from app.services import report

    _round(db, users, title="8/26 (8월 4주차)", when=date(2026, 8, 27), sent=97)

    data = report.monthly(db, 2026, 8, users["u1"], today=date(2026, 8, 31))
    assert data["sends"]["left"] == 0
    assert data["sends"]["short"] == 0
    assert _group(data, "deal_intro")["rows"][0]["level"] == ""


# --- 한 날에 회차가 여럿일 때 ---------------------------------------------------

def test_two_rounds_on_one_day_stay_apart(db, users):
    """합치면 중단된 회차가 묻힌다 — 손으로 쓴 보고가 실제로 그랬다."""
    from app.services import report

    _round(db, users, title="8/26 (8월 4주차)", when=date(2026, 8, 27),
           sent=97, companies=7)
    _round(db, users, title="08/27 (8월 4주차)", when=date(2026, 8, 27),
           sent=18, canceled=98, companies=7, status="canceled")

    deal = _group(report.monthly(db, 2026, 8, users["u1"],
                                 today=date(2026, 8, 31)), "deal_intro")
    assert len(deal["rows"]) == 2, "같은 날이어도 회차마다 한 줄이다"
    assert {r["day"] for r in deal["rows"]} == {"8/27(목)"}
    assert sorted(r["sent"] for r in deal["rows"]) == [18, 97]
    assert deal["sent"] == 115, "두 회차를 합쳐 115건 — 213 도 116 도 아니다"
    assert deal["companies"] == 7, "같은 딜을 다시 돌린 것이라 14개사가 아니다"


def test_people_are_counted_once_even_across_rounds(db, users):
    """'총 N명' 은 사람 수다. 같은 사람에게 두 회차를 보냈어도 한 명이다."""
    from app.services import report

    _round(db, users, title="첫 회차", when=date(2026, 8, 27), sent=97)
    _round(db, users, title="둘째 회차", when=date(2026, 8, 27),
           sent=18, canceled=98, status="canceled")

    deal = _group(report.monthly(db, 2026, 8, users["u1"],
                                 today=date(2026, 8, 31)), "deal_intro")
    assert deal["target"] == 213, "발송 건으로는 213건이 잡혔지만"
    assert deal["contacts"] == 116, "사람으로는 116명 — 97명은 겹친다"


# --- 달 경계 -------------------------------------------------------------------

def test_only_this_months_rounds(db, users):
    from app.services import report

    _round(db, users, title="7월 말", when=date(2026, 7, 31), sent=5)
    _round(db, users, title="8월 초", when=date(2026, 8, 1), sent=7)
    _round(db, users, title="9월 초", when=date(2026, 9, 1), sent=9)

    data = report.monthly(db, 2026, 8, users["u1"], today=date(2026, 9, 30))
    assert data["sends"]["rounds"] == 1
    assert data["sends"]["sent"] == 7
    assert _group(data, "deal_intro")["rows"][0]["title"] == "8월 초"


def test_a_round_without_a_date_falls_back_to_when_it_started(db, users):
    """회차일이 비어도 발송을 시작한 날은 있다 — 그 달에서 사라지면 안 된다."""
    from app.services import report

    _round(db, users, title="회차일 없음", when=date(2026, 8, 12), sent=4,
           sent_date=False)

    data = report.monthly(db, 2026, 8, users["u1"], today=date(2026, 8, 31))
    assert data["sends"]["sent"] == 4
    assert _group(data, "deal_intro")["rows"][0]["day"] == "8/12(수)"


# --- 팀 전체 / 본인 -------------------------------------------------------------

def test_my_report_excludes_teammates(db, users):
    from app.services import report

    _round(db, users, title="내 회차", when=date(2026, 8, 5), sent=3,
           user_key="u1")
    _round(db, users, title="남의 회차", when=date(2026, 8, 6), sent=4,
           user_key="u2")

    mine = report.monthly(db, 2026, 8, users["u1"], today=date(2026, 8, 31))
    team = report.monthly(db, 2026, 8, None, today=date(2026, 8, 31))
    assert (mine["sends"]["rounds"], mine["sends"]["sent"]) == (1, 3)
    assert (team["sends"]["rounds"], team["sends"]["sent"]) == (2, 7)


def test_team_scope_is_admin_only(logged, db, users):
    """남의 회차가 보이는 화면이다 — 관리자가 아니면 scope=team 도 본인 것."""
    _round(db, users, title="남의 회차", when=date(2026, 8, 6), sent=4,
           user_key="u2")

    body = logged.get("/report?month=2026-08&scope=team").text
    assert "남의 회차" not in body
    assert "이 달에는 나간 회차가 없습니다" in body


def test_an_admin_sees_the_whole_team(client, db, users):
    from app.models import User
    from app.services import auth as auth_svc

    db.add(User(name="관리자", phone="01000000009", role="admin",
                password_hash=auth_svc.hash_password(DEMO_PASSWORD)))
    db.commit()
    _round(db, users, title="남의 회차", when=date(2026, 8, 6), sent=4,
           user_key="u2")

    client.post("/login", data={"phone": "01000000009", "password": DEMO_PASSWORD})
    body = client.get("/report?month=2026-08&scope=team").text
    assert "남의 회차" in body
    # 팀 전체로 볼 때는 누가 보냈는지가 나와야 한다
    assert users["u2"].name in body


# --- 핵심 딜 · 딜 소싱 ----------------------------------------------------------

def test_the_top_deal_company_count(db, users):
    """사용자가 `핵심 딜 7개사` 라고 적던 값."""
    from app.services import report

    _round(db, users, title="8/26 (8월 4주차)", when=date(2026, 8, 27),
           sent=97, companies=7)

    deal = _group(report.monthly(db, 2026, 8, users["u1"],
                                 today=date(2026, 8, 31)), "deal_intro")
    assert deal["rows"][0]["companies"] == 7
    assert len(deal["rows"][0]["company_names"]) == 7
    assert deal["companies"] == 7, "그 달에 소개한 기업 수"

    # 다른 딜을 실은 회차가 하나 더 돌면 그 달에 소개한 기업이 늘어난다
    _round(db, users, title="8/12 (8월 2주차)", when=date(2026, 8, 12),
           sent=90, companies=3, deals="다른딜")
    deal = _group(report.monthly(db, 2026, 8, users["u1"],
                                 today=date(2026, 8, 31)), "deal_intro")
    assert deal["companies"] == 10


def test_sourcing_is_reported_apart_from_deal_intro(db, users):
    """성격이 다른 일이라 사용자도 나눠 적었다."""
    from app.services import report

    _round(db, users, title="8/26 (8월 4주차)", when=date(2026, 8, 27), sent=97)
    _round(db, users, title="09/02 (9월 1주차)", when=date(2026, 8, 27),
           kind="sourcing_intro", sent=2)

    data = report.monthly(db, 2026, 8, users["u1"], today=date(2026, 8, 31))
    assert _group(data, "deal_intro")["sent"] == 97
    sourcing = _group(data, "sourcing_intro")
    assert sourcing["sent"] == 2
    assert sourcing["rows"][0]["day"] == "8/27(목)"
    assert data["sends"]["sent"] == 99


# --- 발송이 아닌 것은 세지 않는다 -------------------------------------------------

def test_room_checks_are_not_sends(db, users):
    """방 연결 확인은 아무것도 보내지 않는다.

    끝난 건이 `sent` 로 남아서, 방 확인만 돌린 날 발송 116건으로 찍힌 적이 있다.
    """
    from app.services import report

    _round(db, users, title="방 연결 확인", when=date(2026, 8, 26),
           kind="verify_room", sent=116, failed=7,
           status="done_with_errors")

    data = report.monthly(db, 2026, 8, users["u1"], today=date(2026, 8, 31))
    assert data["sends"]["rounds"] == 0
    assert data["sends"]["sent"] == 0


def test_ir_delivery_is_not_counted_twice(db, users):
    """IR 자료 전달은 아래 'IR 자료 요청' 칸이 이미 센다."""
    from app.services import report

    _round(db, users, title="IR 자료 전달", when=date(2026, 8, 10),
           kind="ir_delivery", sent=1)

    data = report.monthly(db, 2026, 8, users["u1"], today=date(2026, 8, 31))
    assert data["sends"]["rounds"] == 0


# --- 발송이 없는 달 -------------------------------------------------------------

def test_a_month_without_sends_does_not_break(db, users):
    from app.services import report

    data = report.monthly(db, 2026, 5, users["u1"], today=date(2026, 8, 31))
    assert data["sends"]["rounds"] == 0
    assert data["sends"]["sent"] == 0
    assert data["sends"]["left"] == 0
    # 종류 칸은 늘 자리를 지킨다 — 빈 달에도 무엇을 세는 화면인지 보여야 한다
    assert [g["key"] for g in data["sends"]["groups"]] == ["deal_intro",
                                                           "sourcing_intro"]


def test_the_page_opens_for_an_empty_month(logged):
    body = logged.get("/report?month=2026-05").text
    assert "5월 발송" in body
    assert "이 달에는 나간 회차가 없습니다" in body


# --- 화면 ----------------------------------------------------------------------

def test_the_page_shows_the_round_as_the_report_reads(logged, db, users):
    """화면만 보고 보고가 끝나야 한다 — 회차명·날짜(요일)·개사·대상·완료."""
    _round(db, users, title="8/26 (8월 4주차)", when=date(2026, 8, 27),
           sent=97, companies=7)
    _round(db, users, title="08/27 (8월 4주차)", when=date(2026, 8, 27),
           sent=18, canceled=98, companies=7, status="canceled")
    _round(db, users, title="09/02 (9월 1주차)", when=date(2026, 8, 27),
           kind="sourcing_intro", sent=2)

    body = logged.get("/report?month=2026-08").text

    assert "8월 발송" in body
    for title in ("8/26 (8월 4주차)", "08/27 (8월 4주차)", "09/02 (9월 1주차)"):
        assert title in body, f"{title} 회차가 화면에 없습니다"
    assert "8/27(목)" in body, "날짜에 요일이 붙어야 한다"
    assert "중단됨" in body, "중단된 회차가 '완료' 로 보이면 안 된다"
    assert "핵심 딜 7개사" in body
    # 안 나간 건을 화면이 **먼저** 말한다
    assert "<b>98건</b>이 안 나갔습니다(회차 1개)" in body
    # 두 회차의 대상·완료가 각각 서 있다
    for number in ("97", "116", "18"):
        assert f'class="num">{number}</td>' in body, f"{number} 이 표에 없습니다"


# --- 연간 ----------------------------------------------------------------------

def test_yearly_sums_the_sends(db, users):
    """월간에만 두면 연말에 열두 달을 열어 손으로 더하게 된다."""
    from app.services import report

    _round(db, users, title="3월 회차", when=date(2026, 3, 11), sent=40)
    _round(db, users, title="8월 회차", when=date(2026, 8, 27),
           sent=18, canceled=98, status="canceled")

    got = report.yearly(db, 2026, users["u1"], today=date(2026, 12, 31))
    assert got["totals"]["send_rounds"] == 2
    assert got["totals"]["send_sent"] == 58, "40 + 18 — 대상 수가 아니다"
    assert got["totals"]["send_left"] == 98

    # 달별 값이 월간 보고와 같아야 한다 — 두 곳에서 따로 세면 반드시 갈라진다
    for m in got["months"]:
        one = report.monthly(db, 2026, m["month"], users["u1"],
                             today=date(2026, 12, 31))
        assert m["send_sent"] == one["sends"]["sent"], f"{m['label']} 이 월간과 다르다"
        assert m["send_left"] == one["sends"]["left"], f"{m['label']} 이 월간과 다르다"


def test_yearly_page_shows_the_sends(logged, db, users):
    _round(db, users, title="8월 회차", when=date(2026, 8, 27),
           sent=18, canceled=98, status="canceled")

    body = logged.get("/report?span=year&year=2026").text
    assert "발송 회차" in body and "보낸 건수" in body and "안 나감" in body
