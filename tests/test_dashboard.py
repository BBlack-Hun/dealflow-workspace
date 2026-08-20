"""대시보드 · 팀 현황 · 딜 기업 DB.

여기서 지키려는 것.

1. **발송일 계산이 맞아야 한다.** 대시보드 맨 위의 'D-n' 이 곧 마감이라
   하루라도 틀리면 회차를 놓친다. 매월 첫째·셋째 수요일이 기준이다.
2. **팀 현황은 관리자만 본다.** 남의 담당 투자사가 그대로 보이는 화면이다.
3. **소개 불가 사유가 사람 말로 나와야 한다.** '왜 목록에 안 뜨는지' 모르면
   기업 DB 화면이 있으나 마나다.
4. **발송한 회차에 들어간 기업은 지울 수 없다.** 이력이 깨진다.
"""
from __future__ import annotations

from datetime import date

import pytest

from .conftest import DEMO_PASSWORD


@pytest.fixture()
def logged(client, users):
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    return client


@pytest.fixture()
def admin_client(client, db, users):
    users["u2"].role = "admin"
    db.commit()
    client.post("/login", data={"phone": "01000000002", "password": DEMO_PASSWORD})
    return client


# --- 발송 주기 --------------------------------------------------------------

@pytest.mark.parametrize("today, expected", [
    # 2026-09-01(화) 기준 → 첫째 수요일 9/2, 셋째 수요일 9/16
    (date(2026, 9, 1), [date(2026, 9, 2), date(2026, 9, 16), date(2026, 10, 7)]),
    # 발송일 당일은 '오늘'로 잡혀야 한다 (지나간 것으로 밀면 그날 발송을 놓친다)
    (date(2026, 9, 2), [date(2026, 9, 2), date(2026, 9, 16), date(2026, 10, 7)]),
    # 셋째 수요일 다음 날 → 다음 달로 넘어간다
    (date(2026, 9, 17), [date(2026, 10, 7), date(2026, 10, 21), date(2026, 11, 4)]),
    # 연말 → 해를 넘겨도 이어진다
    (date(2026, 12, 20), [date(2027, 1, 6), date(2027, 1, 20), date(2027, 2, 3)]),
])
def test_upcoming_send_dates(today, expected):
    from app.services.dashboard import upcoming_send_dates

    assert upcoming_send_dates(today) == expected


def test_send_dates_are_always_wednesday():
    from app.services.dashboard import upcoming_send_dates

    for d in upcoming_send_dates(date(2026, 8, 20), count=12):
        assert d.weekday() == 2, f"{d} 는 수요일이 아니다"


# --- 사용자 대시보드 --------------------------------------------------------

def test_dashboard_is_the_home_page(logged):
    """좌측 위 dealflow 를 누르면 오는 곳 = '/' = 대시보드."""
    r = logged.get("/")
    assert r.status_code == 200
    assert "다음 딜소개" in r.text


def test_dashboard_lists_what_blocks_sending(logged, db, users):
    """방이 없는 담당자는 '먼저 손봐야 할 것'에 뜬다."""
    from app.models import VcContact
    from app.services.dashboard import user_dashboard

    db.add(VcContact(user_id=users["u1"].id, name="홍길동", firm="가나벤처스",
                     channel_kakao=1))
    db.commit()
    data = user_dashboard(db, users["u1"])
    labels = [b["label"] for b in data["blockers"]]
    assert any("카톡방이 등록되지 않은" in x for x in labels)


def test_dashboard_counts_only_successful_sends(logged, db, users):
    """'이번 달 발송'은 시도가 아니라 성공 건수다."""
    from app.models import SendItem, SendJob, VcContact
    from app.services.dashboard import user_dashboard

    contact = VcContact(user_id=users["u1"].id, name="홍길동", firm="가나벤처스")
    job = SendJob(user_id=users["u1"].id, kind="deal_intro", status="done")
    db.add_all([contact, job])
    db.flush()
    stamp = date.today().isoformat() + "T09:00:00"
    db.add_all([
        SendItem(job_id=job.id, contact_id=contact.id, room_name="방", message="a",
                 status="sent", sent_at=stamp),
        SendItem(job_id=job.id, contact_id=contact.id, room_name="방", message="b",
                 status="failed", sent_at=stamp),
    ])
    db.commit()

    kpi = {k["key"]: k["value"] for k in user_dashboard(db, users["u1"])["kpis"]}
    assert kpi["sent"] == 1


# --- 팀 현황 ----------------------------------------------------------------

def test_team_page_is_admin_only(logged):
    assert logged.get("/team").status_code == 403


def test_team_page_opens_for_admin(admin_client):
    r = admin_client.get("/team")
    assert r.status_code == 200
    assert "팀원별 현황" in r.text


def test_admin_can_create_member(admin_client, db):
    from app.models import AgentDevice, User

    r = admin_client.post("/team/members",
                          data={"name": "새사람", "phone": "010-5555-6666", "role": "user"},
                          follow_redirects=False)
    assert r.status_code == 303
    db.expire_all()
    member = db.query(User).filter_by(phone="01055556666").first()
    assert member is not None
    assert member.must_change_password == 1
    # 연결키는 계정마다 따로 — 한 키를 두 PC에 넣으면 발송이 어디로 갈지 모른다
    device = db.query(AgentDevice).filter_by(user_id=member.id).first()
    assert device is not None and device.token


def test_member_creation_rejects_duplicate_phone(admin_client, db):
    from app.models import User

    before = db.query(User).count()
    admin_client.post("/team/members",
                      data={"name": "중복", "phone": "01000000001", "role": "user"},
                      follow_redirects=False)
    db.expire_all()
    assert db.query(User).count() == before


def test_non_admin_cannot_create_member(logged, db):
    from app.models import User

    before = db.query(User).count()
    assert logged.post("/team/members",
                       data={"name": "몰래", "phone": "01077778888"}).status_code == 403
    db.expire_all()
    assert db.query(User).count() == before


def test_deactivate_keeps_the_record(admin_client, db, users):
    """퇴사 처리는 삭제가 아니다 — 담당 투자사와 이력이 주인을 잃으면 안 된다."""
    from app.models import User

    admin_client.post(f"/team/members/{users['u1'].id}/deactivate", follow_redirects=False)
    db.expire_all()
    left = db.get(User, users["u1"].id)
    assert left is not None
    assert left.is_active == 0


# --- 딜 기업 DB -------------------------------------------------------------

def test_companies_page_opens(logged):
    r = logged.get("/companies")
    assert r.status_code == 200
    assert "스타트업 관리" in r.text


def testblocked_reason_is_plain_korean(logged, db):
    """소개가 안 되는 이유를 사람 말로 알려준다."""
    from app.models import IrCompany
    from app.routers.companies import blocked_reason

    only_name = IrCompany(name="이름만", summary_status="draft")
    db.add(only_name)
    db.commit()
    reason = blocked_reason(only_name)
    assert "분야" in reason and "숫자" in reason

    held = IrCompany(name="보류기업", one_liner="설명", revenue_recent=10,
                     summary_status="insufficient")
    db.add(held)
    db.commit()
    assert blocked_reason(held) == "보류로 표시됨"


def test_editing_makes_a_company_introducible(logged, db):
    from app.models import IrCompany

    company = IrCompany(name="채울기업", summary_status="draft")
    db.add(company)
    db.commit()
    assert not company.introducible

    r = logged.patch(f"/api/companies/{company.id}",
                     json={"name": "채울기업", "one_liner": "B2B 정산 자동화",
                           "revenue_recent": 500})
    assert r.status_code == 200
    assert r.json()["introducible"] is True


def test_company_used_in_a_batch_cannot_be_deleted(logged, db, users):
    """이미 보낸 회차에 들어간 기업은 지우지 않는다(이력이 깨진다)."""
    from app.models import DealBatch, DealBatchCompany, IrCompany

    company = IrCompany(name="발송된기업", one_liner="소개", revenue_recent=100)
    batch = DealBatch(user_id=users["u1"].id, title="9월 1회차")
    db.add_all([company, batch])
    db.flush()
    db.add(DealBatchCompany(batch_id=batch.id, company_id=company.id, position=1))
    db.commit()

    r = logged.delete(f"/api/companies/{company.id}")
    assert r.status_code == 400
    assert "보류" in r.json()["detail"]      # 대신 무엇을 하면 되는지 알려준다


def test_unused_company_can_be_deleted(logged, db):
    from app.models import IrCompany

    company = IrCompany(name="지울기업")
    db.add(company)
    db.commit()
    company_id = company.id          # 지운 뒤 company.id 를 읽으면 세션이 행을 다시 찾는다
    assert logged.delete(f"/api/companies/{company_id}").status_code == 200
    db.expire_all()
    assert db.get(IrCompany, company_id) is None


# --- 화면에서 개발 용어가 보이지 않아야 한다 --------------------------------

DEV_WORDS = ["Sprint", "스프린트", "dry_run", "user_id", "None", "Traceback"]


@pytest.mark.parametrize("path", ["/", "/deals", "/contacts", "/companies",
                                  "/templates", "/setup", "/todo"])
def test_pages_have_no_developer_jargon(logged, path):
    """쓰는 사람에게 아무 뜻이 없는 말은 화면에 두지 않는다."""
    body = logged.get(path).text
    for word in DEV_WORDS:
        assert word not in body, f"{path} 에 '{word}' 가 보입니다"


# --- 좌측 메뉴 이름과 화면 제목 ---------------------------------------------

@pytest.mark.parametrize("path, key", [
    ("/deals", "deal"), ("/contacts", "vc"), ("/companies", "su"),
    ("/templates", "templates"), ("/setup", "setup"),
])
def test_page_title_matches_menu_label(logged, path, key):
    """메뉴 이름만 바꾸고 화면 제목을 두면 둘이 어긋난다 — 한 곳에서 가져온다."""
    from app.ui import menu_label

    body = logged.get(path).text
    assert f"<h1>{menu_label(key)}</h1>" in body or \
        f'<h1 class="page-title">{menu_label(key)}</h1>' in body


def test_mail_channel_is_off_until_configured(logged):
    """메일 서버 정보가 없으면 아예 고를 수 없어야 한다.

    고를 수 있는데 나가지 않는 것이 제일 나쁘다.
    """
    body = logged.get("/deals").text
    assert 'value="email"' in body
    assert "disabled" in body
    assert "메일 발송은 아직 켜지지 않았습니다" in body


def test_companies_table_shows_ir_link_state(logged, db):
    """자료 링크 유무가 곧 'IR 요청이 오면 바로 보낼 수 있는가' 다."""
    from app.models import IrCompany

    db.add_all([
        IrCompany(name="자료있음", one_liner="소개", revenue_recent=10,
                  ir_drive_url="https://drive.google.com/file/d/x/view"),
        IrCompany(name="자료없음", one_liner="소개", revenue_recent=10),
    ])
    db.commit()
    body = logged.get("/companies").text
    assert 'data-f-ir="● 있음"' in body
    assert 'data-f-ir="⚠ 없음"' in body
