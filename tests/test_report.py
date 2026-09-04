"""주간·월간 업무 보고.

원본 시트는 미팅을 하고 나서 **사람이 다시 옮겨 적고** 있었다.

    6월 미팅 총 4개사
      6월 첫주   미팅 완료 2개사   결과 문의전화 완료
      6월 둘째주 미팅 완료 0개사

옮겨 적는 사이에 빠지는 건이 생긴다. 이제 기록에서 뽑는다.
시트에 "결과확인전화가 없으면 계약을 잊어버리는 경우가 발생할 수 있습니다" 라고
적혀 있었다 — **결과 문의를 했는지**가 이 보고의 핵심이다.
"""
from __future__ import annotations

from datetime import date
from html.parser import HTMLParser

import pytest

from .conftest import DEMO_PASSWORD


@pytest.fixture()
def logged(client, users):
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    return client


def _meeting(db, users, when, *, status="done", outcome="reviewing",
             followup_due=None, followup_done=0, user_key="u1", who="홍길동",
             company=""):
    """`who` 로 담당자를 나눈다.

    한 담당자에게 미팅이 두 건이면 **뒤엣것이 앞엣것을 대신한다** — 2차 미팅을
    잡았으면 1차에 결과를 물을 이유가 없다. 그 규칙과 무관한 것을 재려면
    담당자를 나눠야 한다.
    """
    from app.models import Meeting, VcContact

    contact = db.query(VcContact).filter_by(name=who).first()
    if contact is None:
        contact = VcContact(user_id=users["u1"].id, name=who, firm="가나벤처스")
        db.add(contact)
        db.flush()
    row = Meeting(user_id=users[user_key].id, contact_id=contact.id,
                  company_name=company or None,
                  scheduled_at=when.isoformat(), kind="first", status=status,
                  done_at=when.isoformat() if status == "done" else None,
                  outcome=outcome if status == "done" else None,
                  followup_due=(followup_due or when).isoformat(),
                  followup_done=followup_done)
    db.add(row)
    db.commit()
    return row


# --- 주차 계산 --------------------------------------------------------------

@pytest.mark.parametrize("day, week", [
    (date(2026, 6, 1), 1),
    (date(2026, 6, 10), 2),
    (date(2026, 6, 16), 3),
    (date(2026, 6, 25), 4),
    (date(2026, 6, 30), 5),
])
def test_week_of_month(day, week):
    from app.services.report import week_of_month

    assert week_of_month(day) == week


# --- 보고 -------------------------------------------------------------------

def test_monthly_groups_by_week(db, users):
    """시트와 같은 모양 — 월 합계 + 주차별."""
    from app.services import report

    _meeting(db, users, date(2026, 6, 10))
    _meeting(db, users, date(2026, 6, 16))
    _meeting(db, users, date(2026, 6, 25))
    _meeting(db, users, date(2026, 7, 1))     # 다른 달은 안 섞인다

    data = report.monthly(db, 2026, 6, users["u1"], today=date(2026, 7, 20))
    assert data["total"] == 3
    assert [w["week"] for w in data["weeks"]] == [2, 3, 4]
    assert all(w["done"] == 1 for w in data["weeks"])


def test_late_followup_is_counted(db, users):
    """열흘이 지났는데 결과를 안 물어본 건 — 이 보고가 잡아내야 할 것."""
    from app.services import report

    _meeting(db, users, date(2026, 6, 10), who="안물어본사람",
             followup_due=date(2026, 6, 20), followup_done=0)
    _meeting(db, users, date(2026, 6, 16), who="물어본사람",
             followup_due=date(2026, 6, 26), followup_done=1)

    data = report.monthly(db, 2026, 6, users["u1"], today=date(2026, 7, 1))
    assert data["followup_done"] == 1
    assert data["followup_late"] == 1


def test_future_followup_is_not_late(db, users):
    from app.services import report

    _meeting(db, users, date(2026, 6, 25), followup_due=date(2026, 7, 5))
    data = report.monthly(db, 2026, 6, users["u1"], today=date(2026, 7, 1))
    assert data["followup_late"] == 0


def test_outcomes_are_counted(db, users):
    from app.services import report

    _meeting(db, users, date(2026, 6, 10), outcome="investing")
    _meeting(db, users, date(2026, 6, 11), outcome="investing")
    _meeting(db, users, date(2026, 6, 12), outcome="pass")

    data = report.monthly(db, 2026, 6, users["u1"], today=date(2026, 7, 1))
    assert dict(data["outcomes"]) == {"투자 검토": 2, "거절": 1}


def test_ir_requests_are_counted_too(db, users):
    """미팅만으로는 그 달의 반응이 안 보인다."""
    from app.models import IrRequest, VcContact
    from app.services import report

    contact = VcContact(user_id=users["u1"].id, name="홍길동", firm="가나벤처스")
    db.add(contact)
    db.flush()
    db.add_all([
        IrRequest(user_id=users["u1"].id, contact_id=contact.id,
                  company_name="샘플애그", requested_at="2026-06-05",
                  status="delivered"),
        IrRequest(user_id=users["u1"].id, contact_id=contact.id,
                  company_name="샘플메디", requested_at="2026-06-20"),
    ])
    db.commit()

    data = report.monthly(db, 2026, 6, users["u1"], today=date(2026, 7, 1))
    assert data["ir_requested"] == 2
    assert data["ir_delivered"] == 1
    assert data["ir_open"] == 1


def test_my_report_excludes_teammates(db, users):
    from app.services import report

    _meeting(db, users, date(2026, 6, 10), user_key="u1")
    _meeting(db, users, date(2026, 6, 11), user_key="u2")

    mine = report.monthly(db, 2026, 6, users["u1"], today=date(2026, 7, 1))
    team = report.monthly(db, 2026, 6, None, today=date(2026, 7, 1))
    assert mine["total"] == 1
    assert team["total"] == 2


def test_page_opens(logged):
    r = logged.get("/report")
    assert r.status_code == 200
    assert "미팅 총" in r.text


def test_team_scope_is_admin_only(logged, db, users):
    """남의 미팅이 보이는 화면이다."""
    from app.services import report

    _meeting(db, users, date(2026, 6, 11), user_key="u2")
    body = logged.get("/report?month=2026-06&scope=team").text
    # 관리자가 아니면 scope=team 을 줘도 본인 것만 보인다
    assert "미팅 총 0개사" in body


# --- 미팅 표의 칸 ---------------------------------------------------------------
# 기업이 **담당자 칸 안에 태그로** 얹혀 있었다. 머리글이 없으니 그 글자가
# 무엇인지 알 방법이 없었고, 같은 화면 아래 '이 달의 반응' 표는 이미 기업을 제
# 칸으로 두고 있어 **한 화면이 같은 것을 두 가지로** 그리고 있었다.


class _Tables(HTMLParser):
    """그린 화면에서 표마다 (머리글 · 행별 칸) 을 모은다.

    머리글 수와 몸통 칸 수가 어긋나는 표는 **그린 뒤**에만 잡힌다 —
    `{% if team_wide %}` 로 칸이 늘고 주는 표라, 템플릿 글자를 세면 두 경우 중
    어느 쪽도 실제로 재지 못한다.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[dict] = []
        self._table: dict | None = None
        self._section = ""
        self._cell: list | None = None

    def handle_starttag(self, tag, attrs) -> None:
        if tag == "table":
            self._table = {"head": [], "rows": []}
            self.tables.append(self._table)
            self._section = ""
        elif self._table is None:
            return
        elif tag in ("thead", "tbody"):
            self._section = tag
        elif tag == "tr" and self._section == "tbody":
            self._table["rows"].append([])
        elif tag == "th" and self._section == "thead":
            self._cell = []
            self._table["head"].append(self._cell)
        elif tag == "td" and self._section == "tbody" and self._table["rows"]:
            self._cell = []
            self._table["rows"][-1].append(self._cell)

    def handle_endtag(self, tag) -> None:
        if tag in ("th", "td"):
            self._cell = None
        elif tag == "table":
            self._table = None

    def handle_data(self, data) -> None:
        if self._cell is not None:
            self._cell.append(data)


def _meeting_table(body):
    """'{달}월 미팅 총 N개사' 패널의 첫 주차 표 → (머리글, 행들).

    주차마다 표가 하나씩이라 첫 표를 본다. 찾는 기준은 머리글 첫 두 칸이다 —
    화면에는 표가 여럿 있고, 그중 이것만 `담당자 / 투자사` 로 시작한다.
    """
    def text(cell):
        return " ".join("".join(cell).split())

    reader = _Tables()
    reader.feed(body)
    seen = [([text(c) for c in t["head"]],
             [[text(c) for c in r] for r in t["rows"]])
            for t in reader.tables]
    found = [t for t in seen if t[0][:2] == ["날짜", "담당자 / 투자사"]]
    assert found, f"미팅 표를 못 찾았다 — 화면의 표들: {[t[0] for t in seen]}"
    return found[0]


def test_the_meeting_table_has_a_company_column(logged, db, users):
    """기업에 **머리글이 붙는다.** 태그로 얹혀 있을 때는 그 글자가 투자사인지
    기업인지 담당자의 무엇인지 화면만 봐서는 알 수 없었다."""
    _meeting(db, users, date(2026, 6, 10), company="가나테크")

    head, rows = _meeting_table(logged.get("/report?month=2026-06").text)
    assert "기업" in head, f"기업 칸이 없다: {head}"
    assert rows[0][head.index("기업")] == "가나테크"


def test_the_meeting_columns_follow_the_reaction_table(logged, db, users):
    """같은 화면의 '이 달의 반응' 표·엑셀 미팅 시트와 **차례가 같다** —
    날짜 · 담당자 · 투자사 · 기업 · 구분. 한 화면에서 두 표가 같은 것을
    다른 자리에 그리면 읽는 사람이 매번 다시 찾아야 한다."""
    _meeting(db, users, date(2026, 6, 10), company="가나테크")

    head, _ = _meeting_table(logged.get("/report?month=2026-06").text)
    assert head.index("기업") == head.index("담당자 / 투자사") + 1
    assert head.index("기업") < head.index("구분")


@pytest.mark.parametrize("scope, wide", [("", False), ("team", True)])
def test_the_meeting_header_and_body_have_the_same_cells(client, db, users,
                                                         scope, wide):
    """`{% if team_wide %}` 로 칸이 늘고 주는 표다. 머리글에만 칸을 더하고
    몸통을 잊으면 **한 경우에서만** 줄이 밀린다 — 두 경우를 다 센다."""
    users["u1"].role = "admin"
    db.commit()
    client.post("/login", data={"phone": "01000000001",
                                "password": DEMO_PASSWORD})
    _meeting(db, users, date(2026, 6, 10), company="가나테크")

    head, rows = _meeting_table(
        client.get(f"/report?month=2026-06&scope={scope}").text)
    assert ("팀원" in head) is wide, f"scope={scope!r} 인데 머리글이 {head}"
    assert rows, "미팅 한 건은 나와야 한다"
    for row in rows:
        assert len(row) == len(head), (
            f"머리글 {len(head)}칸 / 몸통 {len(row)}칸 — {head} vs {row}")


def test_a_meeting_with_no_company_leaves_the_cell_empty(logged, db, users):
    """기업을 적어 두지 않은 미팅이 있다. 없는 것을 `-` 로 **지어내지 않는다** —
    옆의 '이 달의 반응' 표도 엑셀도 그냥 비워 둔다. 칸 자체는 있어야 뒤 칸이
    한 자리씩 밀리지 않는다."""
    _meeting(db, users, date(2026, 6, 10))      # 기업을 안 적었다

    head, rows = _meeting_table(logged.get("/report?month=2026-06").text)
    assert rows[0][head.index("기업")] == ""
    assert len(rows[0]) == len(head), "빈 칸이어도 칸은 서 있어야 한다"


# --- 결과를 물어볼 필요가 없는 경우 --------------------------------------------

def test_a_rejected_meeting_needs_no_followup(db, users):
    """거절당한 곳에 "그 뒤 어떻게 되셨나요" 를 묻는 것은 실례다 —
    이미 답을 받았으므로 물어볼 것이 남아 있지 않다."""
    from app.services import report

    _meeting(db, users, date(2026, 6, 10), who="거절함", outcome="pass",
             followup_due=date(2026, 6, 20), followup_done=0)

    data = report.monthly(db, 2026, 6, users["u1"], today=date(2026, 7, 1))
    assert data["followup_open"] == 0
    assert data["followup_late"] == 0


def test_a_held_meeting_still_needs_one(db, users):
    """보류는 다시 살아날 수 있어 물어볼 값어치가 있다."""
    from app.services import report

    _meeting(db, users, date(2026, 6, 10), who="보류함", outcome="hold",
             followup_due=date(2026, 6, 20), followup_done=0)

    assert report.monthly(db, 2026, 6, users["u1"],
                          today=date(2026, 7, 1))["followup_open"] == 1


def test_booking_the_next_meeting_closes_the_previous_one(db, users):
    """2차 미팅을 잡았다는 것은 이미 이어졌다는 뜻이다 — 1차에 결과를
    물을 이유가 없다."""
    from app.services import report

    _meeting(db, users, date(2026, 6, 10), who="이어진사람",
             followup_due=date(2026, 6, 20), followup_done=0)
    _meeting(db, users, date(2026, 6, 24), who="이어진사람",
             followup_due=date(2026, 7, 4), followup_done=0)

    data = report.monthly(db, 2026, 6, users["u1"], today=date(2026, 7, 1))
    # 뒤엣것 하나만 남는다
    assert data["followup_open"] == 1


def test_completing_a_rejected_meeting_schedules_nothing(db, users):
    """거절로 끝났으면 물어볼 날 자체를 잡지 않는다."""
    from app.models import Meeting, VcContact
    from app.services import pipeline

    contact = VcContact(user_id=users["u1"].id, name="홍길동", firm="가나벤처스")
    db.add(contact)
    db.commit()
    meeting = Meeting(user_id=users["u1"].id, contact_id=contact.id,
                      kind="first", status="planned",
                      scheduled_at=date(2026, 6, 10).isoformat())
    db.add(meeting)
    db.commit()

    pipeline.complete_meeting(db, meeting, outcome="pass", when=date(2026, 6, 10))
    db.commit()
    assert meeting.followup_due is None

    pipeline.complete_meeting(db, meeting, outcome="reviewing", when=date(2026, 6, 10))
    db.commit()
    assert meeting.followup_due is not None


def test_asking_early_can_be_recorded(client, db, users):
    """물어보고 나면 그 자리에서 적을 수 있어야 한다.

    예전엔 **날짜가 지난 건**에만 [문의 완료] 가 떠서, 미리 물어봤으면
    적을 곳이 없었다 — 기록을 못 하니 계속 "안 물어봄" 으로 남는다.
    """
    from app.models import Meeting
    from app.services import report

    _meeting(db, users, date(2026, 6, 10), who="미리물어봄",
             followup_due=date(2026, 12, 31), followup_done=0)
    meeting = db.query(Meeting).filter_by(followup_done=0).first()

    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    # 날짜가 한참 남았어도 버튼이 있다
    assert "물어봤음" in client.get("/ir").text

    r = client.post(f"/ir/meetings/{meeting.id}/followup",
                    data={"outcome": "investing"}, follow_redirects=False)
    assert r.status_code == 303
    db.expire_all()

    data = report.monthly(db, 2026, 6, users["u1"], today=date(2026, 7, 1))
    assert data["followup_done"] == 1
    assert data["followup_open"] == 0
    # 결과도 함께 갱신된다
    assert db.get(Meeting, meeting.id).outcome == "investing"


def test_call_list_says_when_to_call(db, users):
    """`예정` 만으로는 오늘 걸 곳인지 알 수 없다."""
    from app.services import report

    _meeting(db, users, date(2026, 6, 1), who="지난사람",
             followup_due=date(2026, 6, 11), followup_done=0)
    _meeting(db, users, date(2026, 6, 12), who="오늘사람",
             followup_due=date(2026, 7, 1), followup_done=0)

    data = report.monthly(db, 2026, 6, users["u1"], today=date(2026, 7, 1))
    call = next(b for b in data["buckets"] if b["key"] == "call")
    notes = {r["name"]: r["note"] for r in call["rows"]}
    assert "지금 거세요" in notes["지난사람"]
    assert notes["오늘사람"] == "오늘"


def test_the_call_list_skips_what_needs_no_call(db, users):
    from app.services import report

    _meeting(db, users, date(2026, 6, 10), who="거절함", outcome="pass",
             followup_due=date(2026, 6, 20), followup_done=0)

    data = report.monthly(db, 2026, 6, users["u1"], today=date(2026, 7, 1))
    call = next(b for b in data["buckets"] if b["key"] == "call")
    assert call["rows"] == []


# --- 연간 요약 -----------------------------------------------------------------

def test_yearly_sums_the_months(db, users):
    """"올해 몇 건이나 했나" 를 보려고 열두 달을 하나씩 눌러 보고 있었다.

    각 달의 요약을 그대로 쓴다 — 두 곳에서 따로 세면 반드시 갈라진다.
    """
    from app.services import report

    _meeting(db, users, date(2026, 3, 10), who="삼월사람")
    _meeting(db, users, date(2026, 8, 12), who="팔월사람")

    got = report.yearly(db, 2026, users["u1"], today=date(2026, 12, 31))
    assert len(got["months"]) == 12, "빈 달도 자리를 지켜야 흐름이 보인다"
    assert got["totals"]["total"] == 2

    # 달별 값이 월간 보고와 같아야 한다
    for m in got["months"]:
        one = report.monthly(db, 2026, m["month"], users["u1"],
                             today=date(2026, 12, 31))
        assert m["total"] == one["total"], f"{m['label']} 이 월간과 다르다"


def test_yearly_page_opens_and_links_back_to_months(client, db, users):
    _meeting(db, users, date(2026, 8, 12), who="팔월사람")

    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    body = client.get("/report?span=year&year=2026").text
    assert "2026년 · 달별" in body
    # 달을 누르면 그 달 보고로 간다
    assert "/report?month=2026-08" in body


def test_the_picker_is_a_dropdown_not_buttons(client, db, users):
    """단추로 늘어놓으면 두 해치가 스무 개가 넘어 줄바꿈되고, 정작 찾는
    달이 어디 있는지 안 보인다."""
    import re

    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    body = client.get("/report").text

    picker = body[body.index("report-picker"):body.index("kpi-row")]
    assert "<select" in picker
    # 달 단추가 줄줄이 늘어서 있으면 안 된다
    assert len(re.findall(r'class="chip[^"]*"[^>]*>\d+년 \d+월', picker)) == 0
    # 월간·연간은 남긴다 — 두 개뿐이라 눈에 보이는 편이 낫다
    assert ">월간<" in picker and ">연간<" in picker
