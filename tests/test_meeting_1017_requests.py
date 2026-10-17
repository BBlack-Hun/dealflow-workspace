"""10/17 회의 요청 10건 (개선 과제 #35~#44) — 딜 진행 관리 · 업무 보고 · IR 기업 현황.

  #35  `전달함`              → `IR 자료 전달 완료`
  #36  `미팅 요청 보냄`       → `회의실 미팅 톡 요청 보냄 완료` / 안 보냄 → `… 미완료`
  #37  리마인드 뒤 답이 없으면 `답 없음 · 전화 필요` 표시 + 메모, 오늘 할 일에 뜬다
  #38  업무 보고 연간 보기를 월간 모양으로(열두 달 이어 붙이기)
  #39  `… 미완료` 뒤 일 수가 **상한 없이** 계속 센다
  #40  `요청받음`            → `IR 자료 요청 받음`
  #41  `미팅 잡기`            → `회의실 미팅 잡기`
  #42  `보냈음으로 표시`      → `IR 자료 검토 요청 보냄`
  #43  IR 기업 현황 탭 — 지금 화면(필터·검색·정렬) 그대로 엑셀
  #44  `답을 받았습니다` 사유 → `카톡에서 답을 받았습니다`

상태 코드·DB 값·주소는 그대로이고 **보이는 말만** 바뀐다는 것도 함께 본다.
사람·회사 이름은 전부 가짜다. 날짜는 오늘에서 재서 만든다 — 특정 날에만
깨지지 않게.
"""
from __future__ import annotations

import io
import re
from datetime import date, timedelta

import pytest

from .conftest import DEMO_PASSWORD


@pytest.fixture()
def logged(client, users):
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    return client


def _contact(db, users, name, *, firm="가나벤처스", user_key="u1"):
    from app.models import SheetOwner, VcContact

    label = f"{user_key} 명단"
    if db.query(SheetOwner).filter_by(label=label).first() is None:
        db.add(SheetOwner(label=label, user_id=users[user_key].id))
    row = VcContact(user_id=users[user_key].id, name=name, title="심사역",
                    firm=firm, source_sheet=label, channel_kakao=1,
                    connect_stage="connected", kakao_room_name=f"{name} 심사역님")
    db.add(row)
    db.commit()
    return row


def _delivered(db, users, contact, company, *, when, user_key="u1"):
    from app.models import IrRequest

    row = IrRequest(user_id=users[user_key].id, contact_id=contact.id,
                    company_name=company, requested_at=when.isoformat(),
                    status="delivered", delivered_at=when.isoformat())
    db.add(row)
    db.commit()
    return row


def _open_request(db, users, contact, company, *, when):
    from app.models import IrRequest

    row = IrRequest(user_id=users["u1"].id, contact_id=contact.id,
                    company_name=company, requested_at=when.isoformat(),
                    status="open")
    db.add(row)
    db.commit()
    return row


def _meeting_send(db, users, contact, *, when):
    """앱이 실제로 내보낸 미팅 요청 한 건(stage 3 · sent)."""
    from app.models import SendItem, SendJob

    job = SendJob(user_id=users["u1"].id, kind="deal_intro", status="done")
    db.add(job)
    db.flush()
    db.add(SendItem(job_id=job.id, contact_id=contact.id, stage=3,
                    room_name=contact.kakao_room_name, message="미팅 가능하실지요",
                    status="sent", sent_at=f"{when.isoformat()}T11:00:00+09:00"))
    db.commit()


def _sequence(db, users, contact, *, stage, next_stage, due, status="active",
              reason=None, user_key="u1"):
    """딜소개 후속 사다리 한 줄. `stage` 는 끝낸 마지막 단계."""
    from app.models import SendSequence

    sent = (date.today() - timedelta(days=10)).isoformat()
    seq = SendSequence(user_id=users[user_key].id, contact_id=contact.id,
                       stage=stage, status=status, day1_sent_at=sent,
                       last_sent_at=sent, next_stage=next_stage,
                       next_due_date=due.isoformat() if due else None,
                       stopped_reason=reason)
    db.add(seq)
    db.commit()
    return seq


def _admin(db):
    from app.models import User
    from app.services import auth as auth_svc

    admin = User(id=9, name="관리자", phone="01000000009", role="admin",
                 password_hash=auth_svc.hash_password(DEMO_PASSWORD))
    db.add(admin)
    db.commit()
    return admin


def _login(client, phone):
    client.cookies.clear()
    client.post("/login", data={"phone": phone, "password": DEMO_PASSWORD})
    return client


# ═══ 문구 (#35 · #36 · #40 · #41 · #42) ═══════════════════════════════════════

def test_보낼_자료_단추는_IR_자료_전달_완료다(db, users, logged):
    contact = _contact(db, users, "가담당")
    row = _open_request(db, users, contact, "샘플애그", when=date.today())

    body = logged.get("/ir").text
    assert ">IR 자료 전달 완료</button>" in body
    assert ">전달함</button>" not in body
    # 누르면 상태 **코드**는 그대로 `delivered` 다 — 바뀐 것은 말뿐이다.
    resp = logged.post(f"/ir/requests/{row.id}/deliver", follow_redirects=False)
    assert resp.status_code == 303
    db.expire_all()
    from app.models import IrRequest
    assert db.get(IrRequest, row.id).status == "delivered"


def test_안내문이_단추_이름_뒤에_조사를_틀리지_않는다(db, users, logged):
    """`전달함` 일 때 붙던 `을` 이 `IR 자료 전달 완료` 뒤에 남아 `완료'을` 이 됐다.

    단추 이름은 `pipeline.LABEL_DELIVERED` 한 곳에서 바뀔 수 있으므로 조사를
    이름에 맞추지 않고 `[단추 이름] 단추를` 로 적는다 — 이름이 또 바뀌어도 맞다.
    """
    contact = _contact(db, users, "가담당")
    _open_request(db, users, contact, "샘플애그", when=date.today())

    body = logged.get("/ir").text
    assert "완료'을" not in body and "완료'</b> 을" not in body
    assert "[IR 자료 전달 완료] 단추를 누를 필요가 없습니다" in body


def test_전달한_자료_표의_말이_바뀌었다(db, users, logged):
    contact = _contact(db, users, "가담당")
    _delivered(db, users, contact, "샘플애그", when=date.today() - timedelta(days=30))

    body = logged.get("/ir").text
    assert '<span class="status-badge">IR 자료 전달 완료</span>' in body
    assert ">회의실 미팅 잡기</button>" in body
    assert ">IR 자료 검토 요청 보냄</button>" in body
    for old in (">미팅 잡기</button>", ">보냈음으로 표시</button>", ">전달함</span>"):
        assert old not in body, old
    # 2차 미팅 잡기(미팅 후기 표)는 다른 단추라 그대로다 — 요청은 `미팅 잡기` 하나.
    assert "회의실 미팅 톡 요청 미완료 1명" in body


def test_IR_자료_검토_요청_보냄을_누르면_보냄_완료로_바뀐다(db, users, logged):
    contact = _contact(db, users, "가담당")
    _delivered(db, users, contact, "샘플애그", when=date.today() - timedelta(days=30))

    resp = logged.post(f"/ir/contacts/{contact.id}/meeting-asked",
                       follow_redirects=False)
    assert resp.status_code == 303
    body = logged.get("/ir").text
    assert f"회의실 미팅 톡 요청 보냄 완료 · {date.today().isoformat()}" in body
    assert ">IR 자료 검토 요청 보냄</button>" not in body, "이미 보낸 줄에 단추가 남았다"
    # 하는 일은 그대로 — 활동 이력에 `손으로 보냄` 한 줄(코드 `meeting_ask`).
    from app.models import ContactActivity
    from app.services import pipeline
    assert db.query(ContactActivity).filter_by(
        contact_id=contact.id, kind=pipeline.MEETING_ASK_KIND).count() == 1


def test_업무_보고의_IR_판도_같은_말이다(db, users, logged):
    when = date.today().replace(day=1)
    contact = _contact(db, users, "가담당")
    _delivered(db, users, contact, "샘플애그", when=when)
    _open_request(db, users, _contact(db, users, "나담당"), "샘플메디", when=when)

    body = re.sub(r"\s+", " ", logged.get(
        f"/report?month={when.year}-{when.month:02d}").text)
    assert "<span>IR 자료 요청 받음</span>" in body
    assert "<span>IR 자료 전달 완료</span>" in body
    assert "<span>회의실 미팅 톡 요청 미완료</span>" in body
    for old in ("<span>요청받음</span>", "<span>전달함</span>",
                "<span>미팅 요청 안 보냄</span>"):
        assert old not in body, old


def test_상태_코드는_그대로고_말만_바뀐다():
    from app.services import pipeline

    assert set(pipeline.REQUEST_STATUS) == {"open", "delivered", "dropped"}
    assert pipeline.REQUEST_STATUS["open"] == "IR 자료 요청 받음"
    assert pipeline.REQUEST_STATUS["delivered"] == "IR 자료 전달 완료"


def test_투자사_활동_이력은_같은_말을_두_번_하지_않는다(db, users):
    from app.routers.contacts import _pipeline_views

    contact = _contact(db, users, "가담당")
    _delivered(db, users, contact, "샘플애그", when=date.today())
    lines = [v["content"] for v in _pipeline_views(db, contact.id)]
    assert lines == ["IR 자료 전달 완료"], lines


# ═══ #39 — 일 수가 계속 센다 ══════════════════════════════════════════════════

@pytest.mark.parametrize("days", [0, 3, 7, 8, 45, 400])
def test_지난_날을_상한_없이_그대로_센다(db, users, days):
    """예전에는 7일이 지나면 `7일 지남` 이라는 고정된 말만 섰다(8일째든 400일째든)."""
    from app.models import IrRequest
    from app.services import pipeline

    contact = _contact(db, users, "가담당")
    today = date(2026, 10, 17)
    _delivered(db, users, contact, "샘플애그", when=today - timedelta(days=days))

    rows = db.query(IrRequest).all()
    st = pipeline.meeting_ask_state(db, rows, today=today)[contact.id]
    assert st["days"] == days
    text, level = pipeline.meeting_ask_note(st)
    assert text == f"회의실 미팅 톡 요청 미완료 · {days}일"
    assert level == ("bad" if days >= pipeline.IR_MEETING_ASK_DAYS else "warn")


def test_기한_전에도_일_수가_화면에_선다(db, users, logged):
    """예전에는 7일 전 줄에 아무 표시도 없었다 — 이제 처음부터 센다."""
    contact = _contact(db, users, "가담당")
    _delivered(db, users, contact, "샘플애그", when=date.today() - timedelta(days=3))

    body = logged.get("/ir").text
    assert 'class="status-when warn">회의실 미팅 톡 요청 미완료 · 3일' in body


def test_업무_보고_줄도_지난_날을_센다(db, users, logged):
    when = date.today().replace(day=1) - timedelta(days=45)
    contact = _contact(db, users, "가담당")
    _delivered(db, users, contact, "샘플애그", when=when)
    days = (date.today() - when).days

    body = logged.get(f"/report?month={when.year}-{when.month:02d}").text
    assert f"회의실 미팅 톡 요청 미완료 · {days}일" in body
    assert "까지</span>" not in body, "옛 `…까지` 글이 남았다"


# ═══ #44 — 답 옴 사유 ═════════════════════════════════════════════════════════

def test_답_옴은_새_말로_저장된다(db, users, logged):
    from app.models import SendSequence

    contact = _contact(db, users, "가담당")
    seq = _sequence(db, users, contact, stage=1, next_stage=2,
                    due=date.today())
    resp = logged.post(f"/followups/{seq.id}/responded", follow_redirects=False)
    assert resp.status_code == 303
    db.expire_all()
    assert db.get(SendSequence, seq.id).stopped_reason == "카톡에서 답을 받았습니다"


def test_옛_사유는_화면에서만_새_말로_보인다(db, users, logged):
    """DB 값은 그대로 두고(이주 없음) 보일 때만 바꾼다."""
    from app.models import SendSequence

    contact = _contact(db, users, "가담당")
    seq = _sequence(db, users, contact, stage=2, next_stage=None, due=None,
                    status="responded", reason="답을 받았습니다")

    body = logged.get("/ir").text
    assert "카톡에서 답을 받았습니다" in body
    assert re.search(r'muted">\s*답을 받았습니다', body) is None
    db.expire_all()
    assert db.get(SendSequence, seq.id).stopped_reason == "답을 받았습니다"


def test_다른_사유는_적힌_그대로다():
    from app.services import cadence

    assert cadence.reason_label("IR 자료를 요청했습니다") == "IR 자료를 요청했습니다"
    assert cadence.reason_label("답을 받았습니다") == "카톡에서 답을 받았습니다"
    assert cadence.reason_label(None) == ""


# ═══ #37 — 답 없음 · 전화 필요 ═════════════════════════════════════════════════

def _flag_form(contact_id):
    return f'action="/ir/contacts/{contact_id}/call-needed"'


def test_리마인드가_안_나간_줄에는_단추가_없다(db, users, logged):
    contact = _contact(db, users, "가담당")
    # 다음이 리마인드인 줄 — 딜소개만 나갔다.
    _sequence(db, users, contact, stage=1, next_stage=2, due=date.today())
    # 자료는 줬지만 회의실 미팅 톡 요청은 아직이다.
    _delivered(db, users, contact, "샘플애그", when=date.today() - timedelta(days=2))

    body = logged.get("/ir").text
    assert _flag_form(contact.id) not in body

    # 서버도 켜는 것을 막는다.
    resp = logged.post(f"/ir/contacts/{contact.id}/call-needed",
                       data={"on": "1", "back": "remind"}, follow_redirects=False)
    assert resp.status_code == 400


def test_리마인드가_나간_줄에_단추가_서고_켜면_누가_언제가_남는다(db, users, logged):
    from app.models import DealFollowup

    contact = _contact(db, users, "가담당")
    _sequence(db, users, contact, stage=2, next_stage=3, due=date.today())

    body = logged.get("/ir").text
    assert _flag_form(contact.id) in body

    resp = logged.post(f"/ir/contacts/{contact.id}/call-needed",
                       data={"on": "1", "back": "remind"}, follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"].endswith("#remind")

    row = db.query(DealFollowup).filter_by(contact_id=contact.id).one()
    assert row.call_needed == 1
    assert row.call_by == users["u1"].id
    assert row.call_at and row.call_at[:10] == date.today().isoformat()

    body = logged.get("/ir").text
    assert "📞 답 없음 · 전화 필요</span>" in body
    assert f"강민준 · {date.today().isoformat()}" in body, "누가 언제가 배지에 없다"
    # `전화 요청` 구역 맨 위 묶음에도 선다.
    group = body[body.index('data-testid="call-needed"'):]
    group = group[:group.index("</ul>")]
    assert "가담당" in group


def test_메모를_적고_지운다(db, users, logged):
    from app.models import DealFollowup

    contact = _contact(db, users, "가담당")
    _sequence(db, users, contact, stage=3, next_stage=4, due=date.today())

    logged.post(f"/ir/contacts/{contact.id}/call-memo",
                data={"memo": "오후에 다시 연락 주기로 함", "back": "calls"})
    row = db.query(DealFollowup).filter_by(contact_id=contact.id).one()
    assert row.memo == "오후에 다시 연락 주기로 함"
    assert row.memo_by == users["u1"].id and row.memo_at
    assert row.call_needed == 0, "메모만 적었는데 전화 필요가 켜졌다"
    assert "오후에 다시 연락 주기로 함" in logged.get("/ir").text

    logged.post(f"/ir/contacts/{contact.id}/call-memo",
                data={"memo": "  ", "back": "calls"})
    db.expire_all()
    assert db.query(DealFollowup).filter_by(contact_id=contact.id).one().memo is None


def test_끄면_오늘_할_일에서_빠진다(db, users, logged):
    from app.services import today as today_svc

    contact = _contact(db, users, "가담당", firm="다라파트너스")
    _sequence(db, users, contact, stage=2, next_stage=3, due=date.today())

    logged.post(f"/ir/contacts/{contact.id}/call-needed", data={"on": "1"})
    items = today_svc.build(db, users["u1"])["items"]
    call = [i for i in items if i["kind"] == "call"]
    assert len(call) == 1 and call[0]["count"] == 1
    assert "가담당(다라파트너스)" in call[0]["detail"]
    assert call[0]["href"] == "/ir#calls"
    assert "전화 필요" in logged.get("/todo").text

    logged.post(f"/ir/contacts/{contact.id}/call-needed", data={"on": "0"})
    items = today_svc.build(db, users["u1"])["items"]
    assert not [i for i in items if i["kind"] == "call"]


def test_남의_투자사는_고칠_수_없다(db, users, client):
    contact = _contact(db, users, "가담당")
    _sequence(db, users, contact, stage=2, next_stage=3, due=date.today())

    _login(client, "01000000002")          # 다른 팀원
    for path, data in ((f"/ir/contacts/{contact.id}/call-needed", {"on": "1"}),
                       (f"/ir/contacts/{contact.id}/call-memo", {"memo": "x"})):
        resp = client.post(path, data=data, follow_redirects=False)
        assert resp.status_code == 404, path


def test_관리자는_대신_켤_수_있고_담당자의_할_일에_뜬다(db, users, client):
    from app.services import call_flags

    _admin(db)
    contact = _contact(db, users, "가담당")
    _sequence(db, users, contact, stage=2, next_stage=3, due=date.today())

    _login(client, "01000000009")
    resp = client.post(f"/ir/contacts/{contact.id}/call-needed",
                       data={"on": "1"}, follow_redirects=False)
    assert resp.status_code == 303
    # 관리자의 할 일이 아니라 **맡은 팀원**의 할 일이다.
    assert [r["contact_id"] for r in call_flags.needed_for(db, users["u1"])] == [contact.id]
    assert call_flags.needed_for(db, db.get(type(users["u1"]), 9)) == []
    assert call_flags.views(db)[contact.id]["by"] == "관리자"


def test_줄을_가진_팀원도_고칠_수_있다(db, users, client):
    """투자사를 맡은 사람이 아니어도 그 사람의 리마인드 줄을 가진 팀원은 고친다."""
    contact = _contact(db, users, "가담당")      # u1 이 맡았다
    _sequence(db, users, contact, stage=2, next_stage=3, due=date.today(),
              user_key="u2")                     # 줄은 u2 의 것

    _login(client, "01000000002")
    resp = client.post(f"/ir/contacts/{contact.id}/call-needed",
                       data={"on": "1"}, follow_redirects=False)
    assert resp.status_code == 303


def test_회의실_미팅_톡_요청이_나간_자료_줄에도_선다(db, users, logged):
    contact = _contact(db, users, "가담당")
    when = date.today() - timedelta(days=20)
    _delivered(db, users, contact, "샘플애그", when=when)
    _meeting_send(db, users, contact, when=when + timedelta(days=7))

    body = logged.get("/ir").text
    section = body[body.index('id="delivered"'):]
    section = section[:section.index("</section>")]
    assert _flag_form(contact.id) in section
    assert 'name="back" value="delivered"' in section


def test_돌아갈_자리는_아는_구역만(db, users, logged):
    contact = _contact(db, users, "가담당")
    _sequence(db, users, contact, stage=2, next_stage=3, due=date.today())

    resp = logged.post(f"/ir/contacts/{contact.id}/call-needed",
                       data={"on": "1", "back": "//elsewhere.example"},
                       follow_redirects=False)
    assert resp.headers["location"].startswith("/ir?")
    assert resp.headers["location"].endswith("#calls")


def test_끄는_것은_리마인드_판정과_상관없이_된다(db, users, logged):
    """남은 표시를 치울 길은 늘 있어야 한다."""
    from app.models import DealFollowup

    contact = _contact(db, users, "가담당")
    db.add(DealFollowup(contact_id=contact.id, call_needed=1))
    db.commit()
    resp = logged.post(f"/ir/contacts/{contact.id}/call-needed",
                       data={"on": "0"}, follow_redirects=False)
    assert resp.status_code == 303
    db.expire_all()
    assert db.query(DealFollowup).filter_by(contact_id=contact.id).one().call_needed == 0


# ═══ #38 — 연간 업무 보고를 월간 모양으로 ═══════════════════════════════════════

def _a_meeting(db, users, when, who="가담당"):
    from app.models import Meeting

    contact = _contact(db, users, who)
    db.add(Meeting(user_id=users["u1"].id, contact_id=contact.id,
                   scheduled_at=when.isoformat(), status="done",
                   done_at=when.isoformat(), company_name="샘플애그"))
    db.commit()


def test_연간_보기는_열두_달을_월간_모양으로_이어_그린다(db, users, logged):
    _a_meeting(db, users, date(2026, 3, 10), who="삼월담당")
    _a_meeting(db, users, date(2026, 8, 12), who="팔월담당")

    body = logged.get("/report?span=year&year=2026").text
    ids = re.findall(r'<section class="year-month" id="m-(\d+)">', body)
    assert ids == [str(m) for m in range(1, 13)], ids

    def month(m):
        start = body.index(f'id="m-{m}"')
        end = body.index('<section class="year-month"', start + 1) if m < 12 \
            else body.index('id="year-total"')
        return body[start:end]

    # 일이 있던 달은 **월간과 같은 판들**이 선다 — 카드 · 발송 · 미팅 · IR · 반응.
    march = month(3)
    for piece in ('class="kpi-row slim"', "3월 발송", "3월 미팅 총 1개사",
                  "미팅 결과", "IR 자료 요청", "이 달의 반응", 'id="reactions-3"',
                  "삼월담당"):
        assert piece in march, piece
    assert "팔월담당" not in march
    # 아무것도 없던 달은 한 줄로 접힌다.
    assert "이 달에는 기록이 없습니다." in month(1)
    assert "kpi-row" not in month(1)
    # 달 머리에서 그 달 보고로 간다.
    assert "/report?month=2026-08" in month(8)


def test_연간_합계는_그대로_남는다(db, users, logged):
    _a_meeting(db, users, date(2026, 3, 10))
    _a_meeting(db, users, date(2026, 8, 12), who="나담당")

    body = logged.get("/report?span=year&year=2026").text
    # 맨 위 카드는 **한 해 합계**다(월간과 같은 다섯 칸).
    first_kpi = body[body.index("kpi-row"):body.index('id="m-1"')]
    assert re.search(r'kpi-label">잡은 미팅</span>\s*<span class="kpi-value">2<', first_kpi)
    # 맨 아래 연간 합계표(항목 × 달 + 합계).
    total = body[body.index('id="year-total"'):]
    assert "2026년 합계표" in total and "year-report" in total and ">합계<" in total


def test_연간_데이터가_달마다_월간과_같다(db, users):
    from app.services import report

    _a_meeting(db, users, date(2026, 5, 6))
    got = report.yearly(db, 2026, users["u1"], today=date(2026, 12, 31))
    assert [r["month"] for r in got["month_reports"]] == list(range(1, 13))
    for rep in got["month_reports"]:
        one = report.monthly(db, 2026, rep["month"], users["u1"],
                             today=date(2026, 12, 31))
        assert rep["total"] == one["total"]
        assert rep["empty"] == (rep["month"] != 5)


def test_월간_보기는_예전_주소를_지킨다(db, users, logged):
    """월간 몸통을 조각으로 떼어도 `#reactions` 주소는 그대로다."""
    when = date.today().replace(day=1)
    _a_meeting(db, users, when)
    body = logged.get(f"/report?month={when.year}-{when.month:02d}").text
    assert 'id="reactions"' in body
    assert 'class="year-month"' not in body


# ═══ #43 — IR 기업 현황 · 지금 화면 내려받기 ═══════════════════════════════════

def _companies(db, users):
    from app.models import IrCompany

    rows = [
        IrCompany(name="샘플가온헬스", sector_major="헬스케어", assignee_name="정담당",
                  received_at="2026-09-01", contact_phone="010-1234-5678",
                  ir_file_name="가온_IR.pdf"),
        IrCompany(name="샘플나루랩스", sector_major="AI", assignee_name="정담당",
                  received_at="2026-09-03"),
        IrCompany(name="샘플다온소재", sector_major="헬스케어", assignee_name="오담당",
                  received_at="2026-08-20"),
        IrCompany(name="Alpha샘플", sector_major="", assignee_name="오담당",
                  received_at="날짜 미정"),
        # 값 안에 쉼표가 있는 칸 — 화면은 `%2C` 로 실어 보낸다.
        IrCompany(name="샘플라온푸드", sector_major="식품,유통", assignee_name="정담당",
                  received_at="2026-07-01"),
    ]
    db.add_all(rows)
    db.commit()


def _sheet(resp):
    import openpyxl

    assert resp.status_code == 200, resp.text[:200]
    ws = openpyxl.load_workbook(io.BytesIO(resp.content)).active
    rows = [[c.value for c in r] for r in ws.iter_rows()]
    return rows[0], rows[1:]


def test_지금_화면_내려받기는_보이는_칸_그대로다(db, users, logged):
    from app.services import company_view

    _companies(db, users)
    head, rows = _sheet(logged.get("/api/export/companies-view.xlsx"))
    assert head == company_view.VIEW_HEADERS
    assert head[:3] == ["NO", "기업명", "수신일"]
    # 아무 조건 없으면 표의 기본 차례(수신일 최신순, 날짜 없는 곳은 끝).
    assert [r[1] for r in rows] == ["샘플나루랩스", "샘플가온헬스", "샘플다온소재",
                                    "샘플라온푸드", "Alpha샘플"]
    assert [r[0] for r in rows] == [1, 2, 3, 4, 5]
    # IR 자료 칸 — 있으면 파일명, 없으면 `없음`.
    by = {r[1]: r for r in rows}
    assert by["샘플가온헬스"][-1] == "가온_IR.pdf"
    assert by["샘플나루랩스"][-1] == "없음"


def test_머리글_필터가_서버에서_같게_걸린다(db, users, logged):
    _companies(db, users)
    # 칸끼리 AND, 한 칸 안에서는 OR — filters.js 의 matchRow.
    _, rows = _sheet(logged.get(
        "/api/export/companies-view.xlsx?sector=%ED%97%AC%EC%8A%A4%EC%BC%80%EC%96%B4"
        "&assignee=%EC%A0%95%EB%8B%B4%EB%8B%B9"))
    assert [r[1] for r in rows] == ["샘플가온헬스"]
    assert rows[0][0] == 1, "NO 는 보이는 차례로 다시 매긴다"

    _, rows = _sheet(logged.get(
        "/api/export/companies-view.xlsx?sector=AI,%ED%97%AC%EC%8A%A4%EC%BC%80%EC%96%B4"))
    assert {r[1] for r in rows} == {"샘플가온헬스", "샘플나루랩스", "샘플다온소재"}

    # 빈 값은 `(비어 있음)` 한 덩어리.
    _, rows = _sheet(logged.get(
        "/api/export/companies-view.xlsx?sector=(%EB%B9%84%EC%96%B4%20%EC%9E%88%EC%9D%8C)"))
    assert [r[1] for r in rows] == ["Alpha샘플"]

    # 값 안의 쉼표는 `%2C` — 쉼표로 가르기 **전에** 풀면 두 토막이 된다.
    _, rows = _sheet(logged.get(
        "/api/export/companies-view.xlsx?sector=%EC%8B%9D%ED%92%88%2C%EC%9C%A0%ED%86%B5"))
    assert [r[1] for r in rows] == ["샘플라온푸드"]

    # IR 자료 칸의 필터 값은 화면의 그 글자다.
    _, rows = _sheet(logged.get(
        "/api/export/companies-view.xlsx?ir=%E2%97%8F%20%EC%9E%88%EC%9D%8C"))
    assert [r[1] for r in rows] == ["샘플가온헬스"]


def test_검색과_정렬도_화면과_같다(db, users, logged):
    _companies(db, users)
    # 번호는 어느 모양으로 쳐도 — 뒷자리만으로도.
    _, rows = _sheet(logged.get("/api/export/companies-view.xlsx?q=5678"))
    assert [r[1] for r in rows] == ["샘플가온헬스"]
    _, rows = _sheet(logged.get("/api/export/companies-view.xlsx?q=%EB%82%98%EB%A3%A8"))
    assert [r[1] for r in rows] == ["샘플나루랩스"]

    # 이름순 — 한글 먼저(localeCompare('ko') 흉내), 거꾸로도.
    _, rows = _sheet(logged.get("/api/export/companies-view.xlsx?sort=name"))
    assert [r[1] for r in rows] == ["샘플가온헬스", "샘플나루랩스", "샘플다온소재",
                                    "샘플라온푸드", "Alpha샘플"]
    _, rows = _sheet(logged.get("/api/export/companies-view.xlsx?sort=-name"))
    assert [r[1] for r in rows][0] == "Alpha샘플"

    # 조건 셋을 함께.
    _, rows = _sheet(logged.get(
        "/api/export/companies-view.xlsx?assignee=%EC%A0%95%EB%8B%B4%EB%8B%B9"
        "&q=%EC%83%98%ED%94%8C&sort=-name"))
    assert [r[1] for r in rows] == ["샘플라온푸드", "샘플나루랩스", "샘플가온헬스"]


def test_전체_내려받기는_그대로_전부다(db, users, logged):
    _companies(db, users)
    _, rows = _sheet(logged.get(
        "/api/export/companies.xlsx?sector=AI"))   # 조건을 붙여도 전체다
    assert len(rows) == 5


def test_단추는_IR_기업_현황_탭에만(db, users, logged):
    body = logged.get("/companies").text
    assert 'id="co-export-view"' in body
    assert 'href="/api/export/companies.xlsx"' in body, "전체 내려받기는 그대로"
    assert 'id="co-export-view"' not in logged.get("/companies?tab=db").text


def test_정렬_규칙이_table_sort_와_같다():
    """빈 값은 방향과 상관없이 끝 · 같은 값은 처음 차례 · 숫자는 숫자로."""
    from app.services import company_view

    rows = [{"name": "가", "updated_at": "", "sent_rounds": 3, "meeting_sort": "2026-09-01"},
            {"name": "나", "updated_at": "", "sent_rounds": 10, "meeting_sort": ""},
            {"name": "다", "updated_at": "", "sent_rounds": 3, "meeting_sort": "2026-08-01"}]
    asc = [r["name"] for r in company_view.sort_rows(rows, "sent")]
    desc = [r["name"] for r in company_view.sort_rows(rows, "-sent")]
    assert asc == ["가", "다", "나"], "10 이 3 보다 앞에 오면 글자 차례로 센 것이다"
    assert desc == ["나", "가", "다"], "같은 값은 내림에서도 처음 차례 그대로"
    meet = [r["name"] for r in company_view.sort_rows(rows, "-meeting")]
    assert meet == ["가", "다", "나"], "빈 값은 내림에서도 끝"
    assert [r["name"] for r in company_view.sort_rows(rows, "모르는칸")] == ["가", "나", "다"]


@pytest.mark.skipif(__import__("shutil").which("node") is None,
                    reason="node 미설치 — 브라우저 로직 테스트 생략")
def test_단추가_누르는_순간의_조건을_싣는다():
    """필터·정렬은 주소 그대로, 검색창 글자는 `q=` 로(`companies.js`)."""
    import shutil
    import subprocess
    from pathlib import Path

    script = Path(__file__).resolve().parent / "js" / "company_export_view_test.js"
    out = subprocess.run([shutil.which("node"), str(script)],
                         capture_output=True, text=True)
    assert out.returncode == 0, out.stdout + out.stderr
