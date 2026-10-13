"""딜 소싱 메일 확인 — **받은 편지함의 머리글만 읽어 `딜 받음` 을 저절로.**

가짜 POP3(`poplib.POP3_SSL` 을 바꿔 끼운다)로 본다. 진짜 편지함에는 붙지 않는다.

1. 머리글 읽기 — 인코딩된 제목(UTF-8 · ks_c_5601-1987 · Q) · 날것 8비트 ·
   엉뚱한 Date 꼴 · Date 를 못 읽으면 Received.
2. 주소는 `email` 칸과 `firm` 칸 둘 다에서 — 명단에 있는 주소만.
3. **이 달 메일만** 세운다. 사람이 누른 표시는 그대로, 메일은 거두지 않는다.
4. 같은 메일(Message-ID)로는 한 번만 — 사람이 거둔 표시를 같은 메일이 다시
   세우지 않는다. 새 메일은 다시 세운다.
5. `RETR` · `DELE` 를 부르지 않는다. `TOP n 0` 만.
6. 오래된 메일이 30통 연달아 나오면 멈춘다(차례가 조금 섞여도 계속 본다).
7. 설정이 없으면 꺼짐 — 아무것도 안 한다.
8. 로그인 거부 · 연결 실패 — 사유가 화면과 관리자 오늘 할 일에, 비밀번호는 어디에도.
9. 회차 — 15일 · 말일(2월 포함) 18:00, 소싱 리마인드 30분 전. (날, 회차)마다 한 번.
10. 리마인드 전 확인이 메일로 보낸 사람을 빼고, 실패하면 리마인드는 그대로 나간다.
11. [지금 메일 확인] 은 관리자만.
"""
from __future__ import annotations

import logging
import poplib
from datetime import date, datetime, timedelta, timezone
from email.header import Header as MimeHeader
from email.utils import format_datetime

import pytest
from sqlalchemy import select

from tests.conftest import DEMO_PASSWORD

GROUP = "시리즈 A 이상 딜 소싱 참여 심사역"
HOST = "pop3.example.com"
USER = "deal@example.com"
SECRET = "not-a-real-password-123"


def _aware(when: datetime) -> datetime:
    return when.astimezone()


# ── 가짜 편지함 ──────────────────────────────────────────────────────────────

class FakeBox:
    """POP3 서버 하나. 메일은 오래된 것부터(1번이 가장 오래된 것)."""

    def __init__(self):
        self.mails = []
        self.bad_login = False
        self.refuse = False
        self.connections = []

    def add(self, sender, when, subject="10월 딜 공유", mid=None, extra=()):
        lines = [f"From: {sender}".encode("utf-8")]
        if when is not None:
            stamp = when if isinstance(when, str) else format_datetime(_aware(when))
            lines.append(f"Date: {stamp}".encode("utf-8"))
        if isinstance(subject, bytes):
            lines.append(b"Subject: " + subject)
        elif subject:
            lines.append(b"Subject: " + MimeHeader(subject, "utf-8").encode().encode("ascii"))
        if mid is not False:
            lines.append(f"Message-ID: {mid or f'<m{len(self.mails) + 1}@example.com>'}"
                         .encode("ascii"))
        lines.extend(extra)
        lines.append(b"")
        self.mails.append(lines)

    def factory(self):
        box = self

        class FakePop3:
            def __init__(self, host, port=995, timeout=None, **kw):
                if box.refuse:
                    raise ConnectionRefusedError(111, "Connection refused")
                self.host, self.port, self.timeout = host, port, timeout
                self.calls = []
                box.connections.append(self)

            def user(self, name):
                self.calls.append(("user", name))
                return b"+OK"

            def pass_(self, password):
                self.calls.append(("pass_",))
                if box.bad_login:
                    raise poplib.error_proto(b"-ERR [AUTH] Authentication failed")
                return b"+OK"

            def stat(self):
                self.calls.append(("stat",))
                return len(box.mails), 1000

            def top(self, which, howmuch):
                self.calls.append(("top", which, howmuch))
                return b"+OK", list(box.mails[which - 1]), 100

            def retr(self, *args):
                raise AssertionError("RETR 를 부르면 안 된다")

            def dele(self, *args):
                raise AssertionError("DELE 를 부르면 안 된다")

            def quit(self):
                self.calls.append(("quit",))
                return b"+OK"

            def close(self):
                self.calls.append(("close",))

        return FakePop3


@pytest.fixture()
def box(monkeypatch):
    from app.services import sourcing_mail

    fake = FakeBox()
    monkeypatch.setattr(sourcing_mail.poplib, "POP3_SSL", fake.factory())
    return fake


@pytest.fixture()
def configured(monkeypatch):
    monkeypatch.setenv("DEALFLOW_POP3_HOST", HOST)
    monkeypatch.setenv("DEALFLOW_POP3_PORT", "")
    monkeypatch.setenv("DEALFLOW_POP3_USER", USER)
    monkeypatch.setenv("DEALFLOW_POP3_PASSWORD", SECRET)


@pytest.fixture()
def mailed(monkeypatch):
    """관리자 요약 메일을 잡아 둔다(보내지 않는다)."""
    from app.services import send_guard

    sent = []
    monkeypatch.setattr(send_guard, "mail_admins",
                        lambda subject, body: sent.append((subject, body)))
    return sent


@pytest.fixture()
def people(db, users):
    from app.models import SourcingContact

    users["u2"].role = "admin"

    def person(name, bucket=GROUP, **kw):
        row = SourcingContact(bucket=bucket, name=name, **kw)
        db.add(row)
        db.flush()
        return row

    rows = {
        "hong": person("홍길동", firm="가나다벤처스", email="Hong@Example.com",
                       kakao_room_name="홍길동 방"),
        # 주소가 회사 칸에 들어가 있는 줄 — 시트에서 옮길 때 칸이 밀렸다.
        "kim": person("김철수", firm="kim@corp.example.com", kakao_room_name="김철수 방"),
        "none": person("이주소없음", firm="라마바파트너스", kakao_room_name="이주소없음 방"),
        # 같은 사람이 다른 갈래에도 한 줄 더.
        "hong2": person("홍길동", bucket="M&A 찾는 투자사", firm="가나다벤처스",
                        email="hong@example.com"),
    }
    db.commit()
    return rows


def _check(db, when):
    from app.services import sourcing_mail

    row = sourcing_mail._new_row(sourcing_mail.SLOT_MANUAL, _aware(when))
    db.add(row)
    db.commit()
    return sourcing_mail.run_check(db, row)


def _receipts(db, month="2026-10"):
    from app.services import sourcing_receipts

    db.expire_all()
    return sourcing_receipts.receipts(db, month)


# ── 1. 머리글 ────────────────────────────────────────────────────────────────

KST = timezone(timedelta(hours=9))
UTC = timezone.utc


# 시간대가 적힌 값은 그 **순간**으로 견준다(검사 기계의 시간대와 무관하게 — CI 는
# UTC 다). 시간대가 없는 값만 이 프로세스 시간대로 읽는다.
@pytest.mark.parametrize("raw, want", [
    ("Thu, 15 Oct 2026 18:00:00 +0900", datetime(2026, 10, 15, 18, 0, tzinfo=KST)),
    ("Thu, 15 Oct 2026 18:00:00 +0900 (KST)", datetime(2026, 10, 15, 18, 0, tzinfo=KST)),
    ("15 Oct 2026 09:00:00 GMT", datetime(2026, 10, 15, 9, 0, tzinfo=UTC)),   # 요일 없음 · GMT
    ("Thu, 1 Oct 2026 00:30 +0900", datetime(2026, 10, 1, 0, 30, tzinfo=KST)),  # 초 없음
    ("Wed, 30 Sep 2026 16:30:00 +0000", datetime(2026, 9, 30, 16, 30, tzinfo=UTC)),
    ("Wed, 30 Sep 2026 16:30:00 -0000", datetime(2026, 9, 30, 16, 30, tzinfo=UTC)),  # -0000 도 UTC
    ("thu, 15 oct 26 18:00:00 +0900", datetime(2026, 10, 15, 18, 0, tzinfo=KST)),  # 소문자 · 두 자리 해
    ("2026-10-15T18:00:00+09:00", datetime(2026, 10, 15, 18, 0, tzinfo=KST)),       # ISO
    ("2026-10-15 18:00:00", datetime(2026, 10, 15, 18, 0)),     # 시간대 없음 → 이 프로세스
    ("2026. 10. 15. 오후 6:00", datetime(2026, 10, 15, 18, 0)),  # 한글
    ("2026년 10월 15일 오전 9:05", datetime(2026, 10, 15, 9, 5)),
])
def test_odd_date_formats(raw, want):
    from app.services import sourcing_mail

    got = sourcing_mail.parse_date(raw)
    assert got is not None and got == _aware(want)
    # 늘 이 프로세스 시간대로 돌려준다 — 달을 가를 때 화면과 같은 날짜로 읽힌다.
    assert got.utcoffset() == datetime.now().astimezone().utcoffset()


def test_month_is_read_in_the_process_timezone():
    """UTC 9/30 16:30 은 한국 시간으로 10/1 01:30 — 이 프로세스가 한국이면 10월 몫."""
    from app.services import sourcing_mail, sourcing_receipts

    got = sourcing_mail.parse_date("Wed, 30 Sep 2026 16:30:00 +0000")
    local = datetime(2026, 9, 30, 16, 30, tzinfo=UTC).astimezone()
    assert sourcing_receipts.month_of(got.date()) == f"{local.year:04d}-{local.month:02d}"


@pytest.mark.parametrize("raw", ["", "unknown", "Mon, 99 Foo 2026", "1970-01-01 00:00:00"])
def test_unreadable_dates_are_none(raw):
    from app.services import sourcing_mail

    assert sourcing_mail.parse_date(raw) is None


def test_encoded_subjects_and_senders():
    from app.services import sourcing_mail

    korean = "=?ks_c_5601-1987?B?" + __import__("base64").b64encode(
        "10월 딜 공유드립니다 똠".encode("cp949")).decode() + "?="
    lines = [
        b"Received: from mx.example.com by pop3.example.com; Thu, 15 Oct 2026 18:00:01 +0900",
        b"From: =?UTF-8?B?" + __import__("base64").b64encode("홍길동".encode()) + b"?=",
        b"  <Hong@Example.COM>",
        b"Subject: " + korean.encode("ascii"),
        b" =?UTF-8?Q?_=EB=94=9C_=EC=B2=A8=EB=B6=80?=",
        b"Date: not a date",
        b"Message-ID: <abc@example.com>",
        b"",
        b"this line is body and must not be read",
    ]
    header = sourcing_mail.parse_header(3, lines)
    assert header.sender == "hong@example.com"
    assert header.subject == "10월 딜 공유드립니다 똠 딜 첨부"
    # Date 를 못 읽으면 우리 서버가 받은 시각(Received)
    assert header.when == datetime(2026, 10, 15, 18, 0, 1, tzinfo=KST)
    assert header.message_id == "<abc@example.com>"

    raw8 = sourcing_mail.parse_header(4, [
        "From: 김철수 <kim@corp.example.com>".encode("utf-8"),
        "Subject: 날것 제목 cp949".encode("cp949"),
        b"Date: Thu, 15 Oct 2026 18:00:00 +0900",
    ])
    assert (raw8.sender, raw8.subject) == ("kim@corp.example.com", "날것 제목 cp949")
    # Message-ID 가 없으면 주소 · 시각 · 제목으로 같은 메일을 알아본다.
    again = sourcing_mail.parse_header(9, [
        "From: 김철수 <kim@corp.example.com>".encode("utf-8"),
        "Subject: 날것 제목 cp949".encode("cp949"),
        b"Date: Thu, 15 Oct 2026 18:00:00 +0900",
    ])
    assert raw8.message_id.startswith("<no-id-") and raw8.message_id == again.message_id


def test_long_subject_is_cut():
    from app.services import sourcing_mail

    header = sourcing_mail.parse_header(1, [
        b"From: a@example.com",
        b"Subject: " + MimeHeader("가" * 400, "utf-8").encode().encode("ascii"),
    ])
    assert len(header.subject) == sourcing_mail.SUBJECT_MAX


# ── 2. 주소 ──────────────────────────────────────────────────────────────────

def test_addresses_come_from_email_and_firm_columns(db, people):
    from app.services import sourcing_receipts

    book = sourcing_receipts.address_book(db)
    assert book["hong@example.com"] == [people["hong"].id, people["hong2"].id]
    assert book["kim@corp.example.com"] == [people["kim"].id]
    assert sourcing_receipts.without_address(db) == 1
    assert sourcing_receipts.addresses_in(
        "A <x@example.com>, mailto:Z@Mail.Example.org; 전각＠예시 y＠example.net.") == [
        "x@example.com", "z@mail.example.org", "y@example.net"]


# ── 3·4. 이 달만 · 한 번만 ───────────────────────────────────────────────────

def test_only_this_month_from_listed_addresses_is_marked(db, people, box, configured):
    from app.services import sourcing_mail, sourcing_receipts

    sourcing_receipts.mark(db, people["kim"].id, "2026-10", user_id=1)   # 손으로 누름
    db.commit()
    box.add("홍길동 <hong@example.com>", datetime(2026, 9, 30, 23, 30), "9월 딜")   # 지난달
    box.add("모르는사람 <stranger@example.com>", datetime(2026, 10, 2, 9, 0))
    box.add("홍길동 <HONG@example.com>", datetime(2026, 10, 3, 9, 0), "10월 딜 공유드립니다")
    box.add("홍길동 <hong@example.com>", datetime(2026, 10, 9, 9, 0), "10월 딜 두 번째")
    box.add("김철수 <kim@corp.example.com>", datetime(2026, 10, 10, 9, 0))
    box.add("이주소없음 <none@example.com>", datetime(2026, 11, 1, 9, 0))         # 다음 달(시계 틀림)

    row = _check(db, datetime(2026, 10, 15, 18, 0))
    assert row.status == sourcing_mail.STATUS_OK
    got = _receipts(db)
    assert set(got) == {people["hong"].id, people["hong2"].id, people["kim"].id}
    hong = got[people["hong"].id]
    # 그 달 **첫** 메일로 선다.
    assert (hong.source, hong.mail_at[:16], hong.mail_subject) == (
        "mail", "2026-10-03T09:00", "10월 딜 공유드립니다")
    assert hong.mail_message_id == "<m3@example.com>"
    # 손으로 누른 표시는 그대로 — 메일이 덮지 않는다.
    assert (got[people["kim"].id].source, got[people["kim"].id].mail_at) == ("manual", None)
    assert _receipts(db, "2026-09") == {}
    assert (row.scanned, row.matched, row.marked) == (6, 3, 2)
    assert "홍길동(가나다벤처스)" in row.detail


def test_same_message_marks_once_and_a_human_unmark_wins(db, people, box, configured):
    from app.services import sourcing_receipts

    box.add("hong@example.com", datetime(2026, 10, 3, 9, 0), mid="<deal-1@example.com>")
    # 같은 메일이 두 번 배달됐다(같은 Message-ID).
    box.add("hong@example.com", datetime(2026, 10, 3, 9, 0), mid="<deal-1@example.com>")
    first = _check(db, datetime(2026, 10, 15, 18, 0))
    assert first.marked == 2                       # 홍길동의 두 줄(두 갈래)
    again = _check(db, datetime(2026, 10, 31, 18, 0))
    assert again.marked == 0 and again.matched == 2

    # 사람이 거둔다(딜이 아닌 메일이었다) → 같은 메일로는 다시 안 선다.
    sourcing_receipts.unmark(db, people["hong"].id, "2026-10")
    db.commit()
    _check(db, datetime(2026, 10, 31, 18, 5))
    assert people["hong"].id not in _receipts(db)

    # 새 메일이 오면 다시 선다.
    box.add("hong@example.com", datetime(2026, 10, 20, 9, 0), mid="<deal-2@example.com>")
    _check(db, datetime(2026, 10, 31, 18, 10))
    assert _receipts(db)[people["hong"].id].mail_message_id == "<deal-2@example.com>"


def test_mail_never_unmarks(db, people, box, configured):
    from app.services import sourcing_receipts

    sourcing_receipts.mark(db, people["hong"].id, "2026-10", user_id=1)
    db.commit()
    _check(db, datetime(2026, 10, 15, 18, 0))          # 빈 편지함
    assert _receipts(db)[people["hong"].id].source == "manual"


# ── 5·6. 읽기만 · 어디까지 ───────────────────────────────────────────────────

def test_only_top_with_zero_lines_never_retr_or_dele(db, people, box, configured):
    for day in range(1, 6):
        box.add("hong@example.com", datetime(2026, 10, day, 9, 0))
    _check(db, datetime(2026, 10, 15, 18, 0))
    (conn,) = box.connections
    assert (conn.host, conn.port, conn.timeout) == (HOST, 995, 30)
    names = {call[0] for call in conn.calls}
    assert names <= {"user", "pass_", "stat", "top", "quit"}
    tops = [call for call in conn.calls if call[0] == "top"]
    assert [c[1] for c in tops] == [5, 4, 3, 2, 1]        # 새 것부터
    assert all(c[2] == 0 for c in tops)                    # 머리글만
    assert conn.calls[-1] == ("quit",)


def test_stops_after_thirty_older_in_a_row(db, people, box, configured):
    from app.services import sourcing_mail

    for index in range(100):                                 # 지난달 메일 100통
        box.add("old@example.com", datetime(2026, 8, 1) + timedelta(hours=index))
    box.add("hong@example.com", datetime(2026, 10, 2, 9, 0))
    box.add("old@example.com", datetime(2026, 9, 29, 9, 0))   # 차례가 섞인 한 통
    box.add("kim@corp.example.com", datetime(2026, 10, 5, 9, 0))
    row = _check(db, datetime(2026, 10, 15, 18, 0))
    assert row.scanned == 3 + sourcing_mail.OLDER_RUN
    assert set(_receipts(db)) == {people["hong"].id, people["hong2"].id, people["kim"].id}


# ── 7. 꺼짐 ──────────────────────────────────────────────────────────────────

def _login(client, phone):
    client.post("/login", data={"phone": phone, "password": DEMO_PASSWORD})


def test_missing_config_does_nothing(client, db, people, box):
    from app.models import SourcingMailCheck
    from app.services import sourcing_mail

    assert not sourcing_mail.is_configured()
    assert sourcing_mail.tick(db, _aware(datetime(2026, 10, 15, 18, 5))) == []
    assert sourcing_mail.start_manual(db, _admin(db)) is None
    _login(client, "01000000002")                           # 관리자
    page = client.get(f"/sourcing?tab={GROUP}").text
    assert "메일 확인 꺼짐 (서버 설정 없음)" in page
    answer = client.post("/sourcing/mail-check", data={"tab": GROUP},
                         follow_redirects=False)
    assert answer.status_code == 303
    assert box.connections == []
    assert db.execute(select(SourcingMailCheck)).scalars().all() == []
    assert sourcing_mail.today_items(db, _admin(db)) == []


def _admin(db):
    from app.models import User

    return db.get(User, 2)


def test_port_defaults_to_995_and_password_is_not_in_repr(configured, monkeypatch):
    from app.services import sourcing_mail

    settings = sourcing_mail.load_settings()
    assert (settings.host, settings.port, settings.user) == (HOST, 995, USER)
    assert SECRET not in repr(settings)
    monkeypatch.setenv("DEALFLOW_POP3_PORT", "1995")
    assert sourcing_mail.load_settings().port == 1995


# ── 8. 실패 ──────────────────────────────────────────────────────────────────

def test_login_refused_is_recorded_and_shown(client, db, people, box, configured, caplog):
    from app.services import sourcing_mail, today

    box.bad_login = True
    with caplog.at_level(logging.DEBUG):
        row = _check(db, datetime(2026, 10, 15, 18, 0))
    assert row.status == sourcing_mail.STATUS_FAILED
    assert row.error == "로그인 거부 (POP3 사용 허용 여부·비밀번호 확인)"
    assert SECRET not in caplog.text
    assert _receipts(db) == {}

    _login(client, "01000000002")
    page = client.get(f"/sourcing?tab={GROUP}").text
    assert "메일 확인 실패: 로그인 거부 (POP3 사용 허용 여부·비밀번호 확인)" in page
    assert SECRET not in page
    titles = [i["title"] for i in today.build(db, _admin(db))["items"]]
    assert "메일 확인 실패: 로그인 거부 (POP3 사용 허용 여부·비밀번호 확인)" in titles
    # 팀원(관리자 아님)의 오늘 할 일에는 서지 않는다.
    from app.models import User
    member = db.get(User, 1)
    assert not [i for i in today.build(db, member)["items"] if "메일 확인" in i["title"]]


def test_connection_refused(db, people, box, configured):
    from app.services import sourcing_mail

    box.refuse = True
    row = _check(db, datetime(2026, 10, 15, 18, 0))
    assert (row.status, row.error) == (sourcing_mail.STATUS_FAILED, sourcing_mail.ERR_CONNECT)


# ── 9. 회차 ──────────────────────────────────────────────────────────────────

def _remind_on(db, time="11:00"):
    """소싱 리마인드를 켠다 — 보내는 계정은 스타트업 월간 발송을 보내는 계정(u2)."""
    from app.models import AutoSendSetting
    from app.services import automation, automation_runner as runner

    if not db.execute(select(AutoSendSetting)).scalars().first():
        db.add(AutoSendSetting(kind="startup_ir", enabled=1, user_id=2))
        db.commit()
    runner.save_params(db, automation.SOURCING_REMIND,
                       {"groups": GROUP, "weeks": "2,3", "weekday": "수", "time": time})
    automation.save(db, automation.SOURCING_REMIND, enabled=True, user_id=None,
                    test_mode=False, test_room="")


def _slots(db, day):
    from app.services import sourcing_mail

    return [(s.key, s.at.strftime("%H:%M"), s.until and s.until.strftime("%H:%M"))
            for s in sourcing_mail.slots_on(db, day)]


def test_slots_mid_and_last_day_including_february(db, users):
    assert _slots(db, date(2026, 10, 15)) == [("mid", "18:00", None)]
    assert _slots(db, date(2026, 10, 31)) == [("end", "18:00", None)]
    assert _slots(db, date(2026, 10, 30)) == []
    assert _slots(db, date(2026, 2, 15)) == [("mid", "18:00", None)]
    assert _slots(db, date(2026, 2, 28)) == [("end", "18:00", None)]       # 평년
    assert _slots(db, date(2028, 2, 28)) == []                              # 윤년은 29일
    assert _slots(db, date(2028, 2, 29)) == [("end", "18:00", None)]
    assert _slots(db, date(2026, 4, 30)) == [("end", "18:00", None)]
    # 소싱 리마인드가 꺼져 있으면 리마인드 전 회차는 없다(10/14 는 2주차 수요일).
    assert _slots(db, date(2026, 10, 14)) == []


def test_pre_remind_slot_follows_the_reminder_time(db, users):
    from app.services import sourcing_mail

    users["u2"].role = "admin"
    db.commit()
    _remind_on(db)
    assert _slots(db, date(2026, 10, 14)) == [("pre_remind", "10:30", "11:00")]
    assert _slots(db, date(2026, 10, 21)) == [("pre_remind", "10:30", "11:00")]
    assert _slots(db, date(2026, 10, 7)) == []                     # 1주차
    _remind_on(db, time="14:00")
    assert _slots(db, date(2026, 10, 14)) == [("pre_remind", "13:30", "14:00")]

    def due(h, m):
        return [s.key for s in sourcing_mail.due(db, _aware(datetime(2026, 10, 14, h, m)))]

    assert due(13, 29) == [] and due(13, 31) == ["pre_remind"]
    assert due(14, 0) == []                                         # 리마인드가 나간 뒤
    nxt = sourcing_mail.next_slot(db, _aware(datetime(2026, 10, 14, 15, 0)))
    assert (nxt.key, nxt.at.date()) == ("mid", date(2026, 10, 15))


def test_tick_runs_each_slot_once(db, people, box, configured, mailed):
    from app.models import SourcingMailCheck
    from app.services import sourcing_mail

    box.add("hong@example.com", datetime(2026, 10, 3, 9, 0))
    assert sourcing_mail.tick(db, _aware(datetime(2026, 10, 15, 17, 59))) == []
    done = sourcing_mail.tick(db, _aware(datetime(2026, 10, 15, 18, 3)))
    assert [r.run_key for r in done] == ["2026-10-15:mid"]
    assert sourcing_mail.tick(db, _aware(datetime(2026, 10, 15, 18, 8))) == []
    assert sourcing_mail.tick(db, _aware(datetime(2026, 10, 15, 23, 0))) == []
    assert len(box.connections) == 1
    assert len(db.execute(select(SourcingMailCheck)).scalars().all()) == 1
    # 요약 메일 한 통(설정이 있으면 관리자에게).
    assert len(mailed) == 1 and "새로 딜 받음 2명" in mailed[0][0]


# ── 10. 리마인드 전 확인 ─────────────────────────────────────────────────────

def _remind_items(db):
    from app.models import SendItem

    db.expire_all()
    return {i.sourcing_contact_id: i.status
            for i in db.execute(select(SendItem)).scalars().all()}


def test_pre_remind_check_drops_people_who_already_mailed(db, people, box, configured,
                                                          mailed):
    from app.services import automation, automation_runner as runner
    from app.services import scheduled_send, sourcing_mail

    _remind_on(db)
    runner.run_once(db, automation.SOURCING_REMIND, _aware(datetime(2026, 10, 14, 9, 0)))
    assert set(_remind_items(db)) == {people["hong"].id, people["kim"].id,
                                      people["none"].id}
    box.add("홍길동 <hong@example.com>", datetime(2026, 10, 13, 20, 0))
    done = sourcing_mail.tick(db, _aware(datetime(2026, 10, 14, 10, 31)))
    assert [r.slot for r in done] == ["pre_remind"]
    scheduled_send.run_once(db, _aware(datetime(2026, 10, 14, 11, 0, 20)))
    assert _remind_items(db) == {people["hong"].id: "canceled",
                                 people["kim"].id: "pending",
                                 people["none"].id: "pending"}


def test_pre_remind_check_failure_still_sends_and_says_so(db, people, box, configured,
                                                          mailed):
    from app.services import automation, automation_runner as runner
    from app.services import scheduled_send, sourcing_mail

    _remind_on(db)
    runner.run_once(db, automation.SOURCING_REMIND, _aware(datetime(2026, 10, 14, 9, 0)))
    box.add("hong@example.com", datetime(2026, 10, 13, 20, 0))
    box.bad_login = True
    (row,) = sourcing_mail.tick(db, _aware(datetime(2026, 10, 14, 10, 31)))
    assert row.status == sourcing_mail.STATUS_FAILED
    scheduled_send.run_once(db, _aware(datetime(2026, 10, 14, 11, 0, 20)))
    assert set(_remind_items(db).values()) == {"pending"}            # 그대로 나간다
    items = sourcing_mail.today_items(db, _admin(db), _aware(datetime(2026, 10, 14, 11, 5)))
    assert items[0]["level"] == "urgent"
    assert "리마인드는 그대로 나갑니다" in items[0]["detail"]
    assert "실패" in mailed[0][0] and "리마인드는 그대로 나갑니다" in mailed[0][1]


def test_scheduled_result_stands_in_admin_today_until_next_day(db, people, box,
                                                               configured, mailed):
    from app.services import sourcing_mail

    box.add("hong@example.com", datetime(2026, 10, 3, 9, 0))
    sourcing_mail.tick(db, _aware(datetime(2026, 10, 15, 18, 3)))
    for when in (datetime(2026, 10, 15, 18, 30), datetime(2026, 10, 16, 9, 0)):
        (item,) = sourcing_mail.today_items(db, _admin(db), _aware(when))
        assert item["title"] == "메일 확인 · 10/15 18:03 (15일 회차)"
        assert "새로 딜 받음 2명" in item["detail"]
        assert "이번 달 메일로 받은 분 2명" in item["detail"]
    assert sourcing_mail.today_items(db, _admin(db),
                                     _aware(datetime(2026, 10, 17, 9, 0))) == []
    from app.models import User
    assert sourcing_mail.today_items(db, db.get(User, 1),
                                     _aware(datetime(2026, 10, 15, 18, 30))) == []


# ── 11. [지금 메일 확인] ─────────────────────────────────────────────────────

def test_check_now_is_admin_only(client, db, people, box, configured, monkeypatch):
    from app import clock
    from app.models import SourcingMailCheck
    from app.services import sourcing_mail

    monkeypatch.setattr(sourcing_mail, "_spawn", sourcing_mail._run_by_id)
    now = clock.now()
    # 이 달 1일 0시 1초 — 언제 돌려도 이 달 메일이다(월말 자정 무렵에도).
    box.add("홍길동 <hong@example.com>",
            now.replace(day=1, hour=0, minute=0, second=1, microsecond=0), "이번 달 딜")

    _login(client, "01000000001")                            # 팀원
    answer = client.post("/sourcing/mail-check", data={"tab": GROUP},
                         follow_redirects=False)
    assert answer.status_code == 403
    assert db.execute(select(SourcingMailCheck)).scalars().all() == []
    assert box.connections == []
    assert "지금 메일 확인" not in client.get(f"/sourcing?tab={GROUP}").text

    client.post("/logout")
    _login(client, "01000000002")                            # 관리자
    answer = client.post("/sourcing/mail-check", data={"tab": GROUP},
                         follow_redirects=False)
    assert answer.status_code == 303
    db.expire_all()
    (row,) = db.execute(select(SourcingMailCheck)).scalars().all()
    assert (row.slot, row.status, row.user_id, row.marked) == ("manual", "ok", 2, 2)
    page = client.get(f"/sourcing?tab={GROUP}").text
    assert "지금 메일 확인" in page
    assert f"메일 확인: 마지막 {sourcing_mail.stamp(row.started_at)}" in page
    assert "이번 달 메일로 받은 분 <b>2명</b>" in page
    assert "메일 주소 없는 분 1명" in page
    label = f"{now.month}월 딜 받음 ✓"
    assert label in page
    assert f"(메일 {now.month}/1)" in page


def test_check_now_refuses_while_one_is_running(db, people, box, configured, monkeypatch):
    from app import clock
    from app.services import sourcing_mail

    started = []
    monkeypatch.setattr(sourcing_mail, "_spawn", started.append)
    admin = _admin(db)
    admin.role = "admin"
    first = sourcing_mail.start_manual(db, admin)
    assert first is not None and started == [first.id]
    assert sourcing_mail.start_manual(db, admin) is None
    assert sourcing_mail.page_status(db, clock.now())["running"] is True
    # 서버가 그 사이 멈춰 `running` 으로 남은 줄은 오래되면 막지 않는다.
    later = clock.now() + timedelta(minutes=sourcing_mail.STALE_MIN + 1)
    assert sourcing_mail.running(db, later) is None


def test_manual_mark_shows_as_direct(client, db, people):
    from app.services import sourcing_receipts

    month = sourcing_receipts.month_of()
    sourcing_receipts.mark(db, people["hong"].id, month, user_id=1)
    db.commit()
    _login(client, "01000000001")
    page = client.get(f"/sourcing?tab={GROUP}").text
    assert f"{int(month[5:])}월 딜 받음 ✓" in page and "(직접)" in page


def test_deleting_a_row_takes_its_seen_mail(client, db, people, box, configured):
    from app.models import SourcingMailSeen

    box.add("hong@example.com", datetime(2026, 10, 3, 9, 0))
    _check(db, datetime(2026, 10, 15, 18, 0))
    _login(client, "01000000001")
    assert client.delete(f"/api/sourcing/{people['hong2'].id}").status_code == 200
    db.expire_all()
    seen = db.execute(select(SourcingMailSeen)).scalars().all()
    assert [s.sourcing_contact_id for s in seen] == [people["hong"].id]


def test_reminder_panel_says_whether_mail_is_checked(db, users, monkeypatch):
    from app.services import automation
    from app.services.automations import sourcing_remind

    row = automation.load(db, automation.SOURCING_REMIND)
    assert "메일 확인 꺼짐" in sourcing_remind.describe(db, row)
    monkeypatch.setenv("DEALFLOW_POP3_HOST", HOST)
    monkeypatch.setenv("DEALFLOW_POP3_USER", USER)
    monkeypatch.setenv("DEALFLOW_POP3_PASSWORD", SECRET)
    assert "10:30" in sourcing_remind.describe(db, row)
