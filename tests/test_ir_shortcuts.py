"""딜소개 → 자료 요청으로 이어지는 길이 끊기지 않는가.

투자사가 "2, 4 주세요" 라고 답했을 때, 사람이 하는 일은 세 가지다.
그 셋이 각각 막혀 있었다.

    ① 후속 화면에서 그 사람을 보고 → IR 요청 화면으로 옮겨 담당자를 다시 고른다
    ② 번호가 어느 기업인지 지난 카톡을 뒤진다
    ③ 회차명을 손으로 적는다
"""
from __future__ import annotations

from datetime import date

import pytest

from .conftest import DEMO_PASSWORD


@pytest.fixture()
def sent_batch(client, db, users):
    """담당자 1명에게 기업 3개를 보낸 상태."""
    from app.models import (DealBatch, DealBatchCompany, IrCompany, SendItem,
                            SendJob, SheetOwner, VcContact)

    db.add(SheetOwner(label="내 명단", user_id=users["u1"].id))
    contact = VcContact(user_id=users["u1"].id, name="홍길동", title="심사역",
                        firm="가나벤처스", source_sheet="내 명단",
                        channel_kakao=1, connect_stage="connected",
                        kakao_room_name="홍길동 심사역님")
    companies = [IrCompany(name=n) for n in ("샘플애그", "샘플메디", "샘플로지")]
    batch = DealBatch(user_id=users["u1"].id, title="8월 3주차",
                      sent_date="2026-08-19")
    db.add_all([contact, batch] + companies)
    db.commit()

    for i, company in enumerate(companies, start=1):
        db.add(DealBatchCompany(batch_id=batch.id, company_id=company.id,
                                position=i))
    job = SendJob(user_id=users["u1"].id, kind="deal_intro", batch_id=batch.id,
                  status="done")
    db.add(job)
    db.commit()
    db.add(SendItem(job_id=job.id, contact_id=contact.id, status="sent",
                    room_name="홍길동 심사역님", message="…",
                    sent_at="2026-08-19T09:00:00+00:00"))
    db.commit()

    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    return {"client": client, "contact": contact, "companies": companies}


# --- ② 번호로 적기 -----------------------------------------------------------

def test_numbers_become_companies(sent_batch, db):
    """"2, 4" 를 이름으로 읽으면 `2` 라는 기업의 요청이 만들어진다."""
    from app.models import IrRequest

    sent_batch["client"].post("/ir/requests", follow_redirects=False, data={
        "contact_id": sent_batch["contact"].id, "company_name": "2, 3"})

    rows = db.query(IrRequest).order_by(IrRequest.id).all()
    assert [r.company_name for r in rows] == ["샘플메디", "샘플로지"]
    assert all(r.company_id is not None for r in rows), "기업까지 이어져야 한다"


def test_numbers_and_names_can_mix(sent_batch, db):
    from app.models import IrRequest

    sent_batch["client"].post("/ir/requests", follow_redirects=False, data={
        "contact_id": sent_batch["contact"].id,
        "company_name": "1, 샘플로지"})
    assert {r.company_name for r in db.query(IrRequest).all()} == {"샘플애그", "샘플로지"}


def test_the_same_company_twice_is_one_request(sent_batch, db):
    """번호로도 이름으로도 적었다 — 요청이 두 개 생기면 두 번 보낸다."""
    from app.models import IrRequest

    sent_batch["client"].post("/ir/requests", follow_redirects=False, data={
        "contact_id": sent_batch["contact"].id,
        "company_name": "1, 샘플애그"})
    assert db.query(IrRequest).count() == 1


def test_a_number_that_was_never_sent_is_not_silently_kept(sent_batch, db):
    """없는 번호를 이름으로 남기면 `9` 라는 기업이 생긴다."""
    from app.models import IrRequest

    r = sent_batch["client"].post("/ir/requests", follow_redirects=False, data={
        "contact_id": sent_batch["contact"].id, "company_name": "1, 9"})

    assert db.query(IrRequest).count() == 1
    assert "9" in r.headers["location"], "건너뛴 번호를 알려 줘야 한다"


def test_only_numbers_and_none_of_them_valid(sent_batch, db):
    from app.models import IrRequest

    sent_batch["client"].post("/ir/requests", follow_redirects=False, data={
        "contact_id": sent_batch["contact"].id, "company_name": "8, 9"})
    assert db.query(IrRequest).count() == 0


# --- ① 후속에서 바로 넘어가기 -------------------------------------------------

def test_followup_names_link_to_the_request_form(sent_batch, db):
    from app.models import SendSequence

    db.add(SendSequence(user_id=sent_batch["contact"].user_id,
                        contact_id=sent_batch["contact"].id, stage=1,
                        next_stage=2, status="active",
                        next_due_date=(date.today()).isoformat()))
    db.commit()

    body = sent_batch["client"].get("/followups").text
    assert f'/ir?contact={sent_batch["contact"].id}' in body


def test_arriving_with_a_contact_opens_the_form_ready(sent_batch):
    contact_id = sent_batch["contact"].id
    body = sent_batch["client"].get(f"/ir?contact={contact_id}").text
    assert f'value="{contact_id}" selected' in body
    assert '<div class="member-form" id="new-request" >' in body or \
           'id="new-request" >' in body, "폼이 열린 채로 떠야 한다"


# --- ③ 회차명 · 주차 -----------------------------------------------------------

def test_batch_title_is_filled_in(sent_batch):
    import re

    body = sent_batch["client"].get("/deals").text
    m = re.search(r'id="batch-title" value="([^"]*)"', body)
    assert m, "회차명 칸이 없다"
    assert re.fullmatch(r"\d{2}/\d{2} \(\d+월 \d주차\)", m.group(1)), m.group(1)


def test_every_screen_counts_weeks_the_same_way():
    """같은 날이 화면마다 3주차·4주차로 갈리면 안 된다 — 실제로 갈렸다."""
    from app.services import cadence, report, sheet_import

    for iso in ("2026-08-04", "2026-08-13", "2026-08-19", "2026-08-26"):
        day = date.fromisoformat(iso)
        week = sheet_import.week_of_month(iso)
        assert report.week_of_month(day) == week, iso
        assert cadence.batch_title(day) == \
            f"{day.month:02d}/{day.day:02d} ({day.month}월 {week}주차)", iso


# --- 발송 이력에 기업명 --------------------------------------------------------

def test_send_history_shows_companies_not_the_room_name(sent_batch, db):
    """`딜소개 발송 성공 · 홍길동 심사역님` 이라 기업 자리에 사람 이름이 찍혔다.
    이력을 훑는 목적은 '언제 어떤 기업을 보냈나' 다."""
    body = sent_batch["client"].get(
        f"/api/contacts/{sent_batch['contact'].id}").json()
    rows = [t for t in body["timeline"] if t["source"] == "system"]
    assert rows, "발송 이력이 없다"

    row = rows[0]
    assert [c["name"] for c in row["companies"]] == ["샘플애그", "샘플메디", "샘플로지"]
    assert row["company_count"] == 3
    assert "홍길동" not in row["content"]
    assert row["week"] == 3 and row["weekday"] == "수"


# --- ④ 전달한 자료 → 미팅 요청 --------------------------------------------
#
# 자료를 보낸 다음에 하는 말은 "미팅 가능하실지요" 다. 그런데 그 말을 보내려면
# 딜 제안 관리로 옮겨 `미팅 요청` 탭을 누르고, 방금 자료를 보낸 그 담당자를
# 목록에서 **다시 찾아** 골라야 했다 — 이미 화면에 떠 있는 이름이다.
#
# 새 길을 내는 것이 아니라 [자료 보내기] 가 쓰던 그 주소에 방식만 바꿔 단다.


@pytest.fixture()
def delivered(sent_batch, db):
    """자료를 전달한 요청 한 건 — `전달한 자료` 표에 서는 줄."""
    from app.models import IrRequest

    row = IrRequest(user_id=sent_batch["contact"].user_id,
                    contact_id=sent_batch["contact"].id,
                    company_id=sent_batch["companies"][0].id,
                    company_name="샘플애그", requested_at="2026-08-20",
                    status="delivered", delivered_at="2026-08-21")
    db.add(row)
    db.commit()
    return sent_batch


def test_the_firm_links_to_the_meeting_request(delivered):
    """투자사명을 누르면 **미팅 요청 방식**의 발송 화면으로 간다."""
    from app.routers.deals import MODE_MEETING

    body = delivered["client"].get("/ir").text
    assert f'/deals?mode={MODE_MEETING}&contacts={delivered["contact"].id}' in body


def test_the_meeting_mode_is_a_real_tab(delivered):
    """`mode=meeting` 이 발송 화면에 **없는 탭**이면 링크는 딜 소개로 열린다.

    화면 코드가 `.mode-tab[data-mode=…]` 를 못 찾으면 방식을 안 바꾼다 —
    담당자만 골라진 채 딜 소개 문구가 준비된다.
    """
    from app.routers.deals import FOLLOW_UP_MODES, MODE_MEETING, MODE_TITLES

    assert MODE_MEETING in FOLLOW_UP_MODES
    assert MODE_TITLES[MODE_MEETING] == "미팅 요청"
    assert f'data-mode="{MODE_MEETING}"' in delivered["client"].get("/deals").text


def test_no_companies_ride_along(delivered):
    """기업은 안 싣는다 — 미팅 요청 문구가 기업 목록을 안 쓴다."""
    import re

    from app.routers.deals import MODE_MEETING, MODES_WITH_COMPANIES

    assert MODE_MEETING not in MODES_WITH_COMPANIES
    body = delivered["client"].get("/ir").text
    links = re.findall(r'/deals\?mode=meeting[^"\']*', body)
    assert links, "미팅 요청 링크가 없다"
    assert not any("companies=" in href for href in links), links


def test_someone_elses_contact_never_reaches_the_send_list(sent_batch, db, client):
    """넘어간 곳에서 **남의 담당자는 여전히 못 고른다.**

    주소에 번호를 실어 보내는 길이라 "링크를 만들면 고를 수 있게 되나" 를
    확인해 둔다 — 발송 화면의 목록은 서버가 그린다. 없으면 없는 것이다.
    """
    from .conftest import DEMO_PASSWORD

    client.post("/login", data={"phone": "01000000002",
                                "password": DEMO_PASSWORD})
    body = client.get("/deals").text
    assert f'class="contact-cb" value="{sent_batch["contact"].id}"' not in body
    assert "홍길동" not in body
