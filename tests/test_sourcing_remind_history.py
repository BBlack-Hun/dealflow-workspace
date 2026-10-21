"""딜 소싱 표의 **월간 리마인드 이력** 칸 — 지난 석 달(#14).

여기서 못 박는 것.

  ① 달 칸은 이 달과 그 앞 두 달, 오래된 달이 왼쪽 — 해가 바뀌는 자리도
     (12월이면 10·11·12월, 1월이면 11·12·1월)
  ② 칸 자리는 `참여` 바로 뒤 — 머리글과 행이 같은 자리 · 같은 수. 고치지도
     거르지도 않는다(`.cell` · `data-field` · `data-filters` 가 없다)
  ③ 그 달 나간 리마인드가 `10/2 14:05 수동` 꼴로 그 달 칸에 — 자동화가 세운
     건(`automation_sends.item_id`)은 `자동`. 한 달에 여럿이면 보낸 차례대로
  ④ 보낸 것만 — 실패 · 대기 · 취소 · 보내는 중, 다른 글(처음 안내 · Series A
     딜 공유), 다른 잡 종류는 안 보인다. 시험 모드로 보낸 것도 안 보인다
  ⑤ 석 달보다 오래된 것은 안 보인다
  ⑥ 질의는 표 전체에 한 번(줄마다 묻지 않는다)
  ⑦ 중복 막기(`manual_sourcing_remind`)와 **같은 조건 한 벌**을 지난다 — 그
     함수가 하던 일은 그대로다
  ⑧ 보낸 것이 하나도 없어도, 명단이 비어 있어도 화면이 선다

이름 · 방은 전부 가상값이다(공개 저장소).
"""
from __future__ import annotations

import re
from datetime import date, datetime

import pytest
from sqlalchemy import event, select

from .conftest import DEMO_PASSWORD

SERIES_A = "시리즈 A 이상 딜 소싱 참여 심사역"
TODAY = date(2026, 10, 16)


@pytest.fixture()
def today(monkeypatch):
    from app import clock

    monkeypatch.setattr(clock, "today", lambda: TODAY)
    return TODAY


@pytest.fixture()
def people(db, users, today):
    from app.models import SourcingContact

    rows = {
        "a": SourcingContact(bucket=SERIES_A, position=0, name="홍길동", title="심사역",
                             firm="가나벤처스", kakao_room_name="홍길동 소싱방"),
        "b": SourcingContact(bucket=SERIES_A, position=1, name="김서연", title="팀장",
                             firm="마바벤처스", kakao_room_name="김서연 소싱방"),
    }
    db.add_all(rows.values())
    db.commit()
    return rows


@pytest.fixture()
def page(client, people):
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})

    def get(tab=SERIES_A):
        from urllib.parse import quote

        return client.get(f"/sourcing?tab={quote(tab)}").text

    return get


def _send(db, users, contact, sent_at, *, status="sent", kind="sourcing_intro",
          topic="sourcing_remind", auto=False, test=False):
    """발송 건 하나. `auto` 면 자동화가 세운 것처럼 `automation_sends` 가 가리킨다."""
    from app.models import AutomationSend, SendItem, SendJob

    job = SendJob(user_id=users["u1"].id, kind=kind, status="done", total=1,
                  sent=1 if status == "sent" else 0, topic=topic)
    db.add(job)
    db.flush()
    item = SendItem(job_id=job.id,
                    sourcing_contact_id=None if test else (contact.id if contact else None),
                    channel="kakao", room_name="소싱방", message="리마인드",
                    status=status, sent_at=sent_at)
    db.add(item)
    db.flush()
    if auto:
        db.add(AutomationSend(automation="sourcing_remind",
                              ref=f"remind:{item.id}:{(sent_at or '')[:7]}:2",
                              test=1 if test else 0, job_id=job.id, item_id=item.id,
                              sourcing_contact_id=None if test else contact.id))
    db.commit()
    return item


def _row(html, contact_id):
    body = html[html.index("<tbody>"):html.index("</tbody>")]
    m = re.search(r'<tr data-id="%d".*?</tr>' % contact_id, body, re.S)
    assert m, f"{contact_id} 줄이 없다"
    return m.group(0)


def _month_cells(row_html):
    """달(`2026-10`) → 그 칸의 줄들(`10/2 14:05 수동`)."""
    out = {}
    for key, inner in re.findall(
            r'<td class="remind-col"[^>]*data-month="([\d-]+)">(.*?)</td>', row_html, re.S):
        lines = re.findall(r'<div class="remind-sent">(.*?)</div>', inner, re.S)
        out[key] = [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", x)).strip() for x in lines]
    return out


# ── ① 달 칸 ─────────────────────────────────────────────────────────────────

def test_the_months_are_this_month_and_the_two_before_oldest_left():
    from app.services import sourcing_remind_log as log

    got = log.months(date(2026, 10, 16))
    assert [m.key for m in got] == ["2026-08", "2026-09", "2026-10"]
    assert [m.label for m in got] == ["8월 리마인드", "9월 리마인드", "10월 리마인드"]
    assert log.MONTHS == 3


def test_the_months_cross_the_year_boundary():
    from app.services import sourcing_remind_log as log

    dec = log.months(date(2026, 12, 5))
    assert [m.key for m in dec] == ["2026-10", "2026-11", "2026-12"]
    assert [m.label for m in dec] == ["10월 리마인드", "11월 리마인드", "12월 리마인드"]

    jan = log.months(date(2027, 1, 3))
    assert [m.key for m in jan] == ["2026-11", "2026-12", "2027-01"]
    # 머리글에는 해를 안 붙인다 — 석 달은 잇닿아 `12월` 이 둘일 수 없다.
    assert [m.label for m in jan] == ["11월 리마인드", "12월 리마인드", "1월 리마인드"]
    # 풍선말에는 해까지
    assert "2026년 12월" in jan[1].title and "2027년 1월" in jan[2].title


def test_a_send_across_the_year_boundary_lands_in_its_own_month(db, users, people):
    from app.services import sourcing_remind_log as log

    a = people["a"]
    _send(db, users, a, "2026-12-30T10:00:00+09:00")
    _send(db, users, a, "2027-01-02T09:30:00+09:00", auto=True)
    got = log.history(db, [a.id], log.months(date(2027, 1, 3)))
    assert {k: [(s.when, s.how) for s in v] for k, v in got[a.id].items()} == {
        "2026-12": [("12/30 10:00", "수동")],
        "2027-01": [("1/2 09:30", "자동")],
    }


# ── ② 칸 자리 — `참여` 바로 뒤, 머리글과 행이 같은 자리 ──────────────────────

def test_the_month_columns_sit_right_after_participation(page, people):
    html = page()
    head = html[html.index("<thead>"):html.index("</thead>")]
    ths = re.findall(r"<th[\s>].*?</th>", head, re.S)
    labels = [re.sub(r"<[^>]+>", "", x).strip() for x in ths]
    # 시리즈 A 탭은 맨 왼쪽에 고르는 칸(빈 머리글)이 선다
    assert labels[:8] == ["", "NO", "참여 요청일", "이름", "참여",
                          "8월 리마인드", "9월 리마인드", "10월 리마인드"], labels
    assert labels[8] == "담당자", labels

    # 읽기 전용 · 거르지 않는다 — 머리글 필터 선언이 없다
    months = [x for x in ths if 'data-testid="sourcing-remind-head"' in x]
    assert len(months) == 3
    assert all("data-filters" not in x for x in months)
    assert 'title="2026년 10월에 이 분께 월간 리마인드가 나간 시각' in months[2]

    row = _row(html, people["a"].id)
    tds = re.findall(r"<td[^>]*>", row)
    assert len(tds) == len(ths), "머리글과 칸 수가 어긋났다 — 표가 밀린다"
    at = [i for i, td in enumerate(tds) if 'data-field="participation"' in td][0]
    assert [re.search(r'data-month="([\d-]+)"', td).group(1)
            for td in tds[at + 1:at + 4]] == ["2026-08", "2026-09", "2026-10"]
    assert 'data-field="assignee_name"' in tds[at + 4]
    # 눌러 고치는 칸이 아니다 — inline_edit.js 는 `.cell[data-field]` 만 본다
    for td in tds[at + 1:at + 4]:
        assert "data-field" not in td and "cell" not in td.split('class="')[1].split('"')[0]


def test_the_table_grew_by_exactly_the_month_columns():
    """표 폭은 **든 만큼만** 올린다 — 안 올리면 폭을 안 준 `메모` 가 그 몫을 내어
    준다. 달 칸 폭을 고치면 `#sourcing-table` 의 최소 폭도 같이 고쳐야 한다."""
    from pathlib import Path

    from app.services.sourcing_remind_log import MONTHS

    root = Path(__file__).resolve().parent.parent / "app"
    css = (root / "static" / "css" / "app.css").read_text(encoding="utf-8")
    html = (root / "templates" / "sourcing.html").read_text(encoding="utf-8")
    wide = int(re.search(r"\.table-wrap\.wide \.grid-table \{ min-width: (\d+)px; \}",
                         css).group(1))
    own = int(re.search(r"#sourcing-table \{ min-width: (\d+)px; \}", css).group(1))
    col = int(re.search(r'<th class="remind-col" style="width:(\d+)px"', html).group(1))
    # #63 — `선호 투자분야` 120→134 · `라운드 사이즈(투자운영금액)` 134→204 도 든 만큼.
    widened = (134 - 120) + (204 - 134)
    assert own == wide + MONTHS * col + widened, (own, wide, col)


def test_the_router_decides_where_the_months_go():
    """머리글이 끼워 세우는 자리는 라우터 한 곳(`REMIND_AFTER`)이다."""
    from app.routers.sourcing import COLUMNS, REMIND_AFTER

    assert REMIND_AFTER == "participation"
    assert REMIND_AFTER in [f for f, _l, _w, _flt in COLUMNS]


# ── ③ 보낸 것 — 그 달 칸에, 시각과 자동 · 수동 ───────────────────────────────

def test_manual_and_auto_sends_show_in_their_month_with_a_marker(db, users, people, page):
    a, b = people["a"], people["b"]
    _send(db, users, a, "2026-10-02T14:05:00+09:00")                 # 사람이 보냄
    _send(db, users, a, "2026-09-09T11:00:20+09:00", auto=True)      # 자동화가 보냄
    _send(db, users, b, "2026-08-12T11:00:05+09:00", auto=True)

    html = page()
    assert _month_cells(_row(html, a.id)) == {
        "2026-08": [], "2026-09": ["9/9 11:00 자동"], "2026-10": ["10/2 14:05 수동"]}
    assert _month_cells(_row(html, b.id)) == {
        "2026-08": ["8/12 11:00 자동"], "2026-09": [], "2026-10": []}


def test_several_sends_in_a_month_are_listed_in_time_order(db, users, people, page):
    from app.services import sourcing_remind_log as log

    a = people["a"]
    # 넣는 차례(번호)와 보낸 차례를 엇갈리게 — 차례는 보낸 시각이다
    _send(db, users, a, "2026-10-21T11:00:00+09:00", auto=True)
    _send(db, users, a, "2026-10-03T16:40:00+09:00")
    _send(db, users, a, "2026-10-14T11:00:00+09:00", auto=True)

    assert _month_cells(_row(page(), a.id))["2026-10"] == [
        "10/3 16:40 수동", "10/14 11:00 자동", "10/21 11:00 자동"]
    got = log.history(db, [a.id], log.months(TODAY))
    assert [s.at for s in got[a.id]["2026-10"]] == [
        "2026-10-03T16:40:00+09:00", "2026-10-14T11:00:00+09:00",
        "2026-10-21T11:00:00+09:00"]


def test_a_real_automation_send_reads_as_auto(db, users, people):
    """A1 자동 리마인드가 **실제로** 세운 건 — `automation_sends.item_id` 로 `자동`."""
    from app.models import AutoSendSetting, SendItem
    from app.services import automation, automation_runner as runner
    from app.services import sourcing_remind_log as log

    users["u2"].role = "admin"
    db.add(AutoSendSetting(kind="startup_ir", enabled=1, user_id=users["u2"].id))
    db.commit()
    automation.save(db, automation.SOURCING_REMIND, enabled=True, user_id=None,
                    test_mode=False, test_room="자동화 시험방")
    result = runner.run_once(db, automation.SOURCING_REMIND,
                             datetime(2026, 10, 14, 9, 0).astimezone())
    assert result["status"] == "ready"
    items = db.execute(select(SendItem)).scalars().all()
    assert {i.sourcing_contact_id for i in items} == {people["a"].id, people["b"].id}
    for item in items:
        item.status, item.sent_at = "sent", "2026-10-14T11:00:20+09:00"
    db.commit()

    got = log.history(db, [people["a"].id, people["b"].id], log.months(TODAY))
    for who in ("a", "b"):
        assert [(s.when, s.how) for s in got[people[who].id]["2026-10"]] == [
            ("10/14 11:00", "자동")]


# ── ④ 보낸 것만 · 월간 리마인드만 · 실제 발송만 ─────────────────────────────

def test_only_sent_monthly_reminds_show(db, users, people, page):
    from app.services import sourcing_remind_log as log

    a = people["a"]
    when = "2026-10-05T10:00:00+09:00"
    for status in ("failed", "queued", "pending", "canceled", "sending"):
        _send(db, users, a, when, status=status)
    _send(db, users, a, None)                                   # sent 인데 시각이 없다
    _send(db, users, a, when, topic=None)                       # 처음 안내
    _send(db, users, a, when, topic="sourcing_deal_share")      # Series A 딜 공유
    _send(db, users, a, when, kind="deal_intro")                # 다른 잡 종류
    _send(db, users, a, when, kind="test_send", topic=None, auto=True, test=True)

    assert log.history(db, [a.id], log.months(TODAY)) == {}
    assert _month_cells(_row(page(), a.id)) == {
        "2026-08": [], "2026-09": [], "2026-10": []}


def test_test_mode_automation_sends_never_show(db, users, people):
    """시험 모드 회차는 받는 줄을 안 가리킨다(`automation.build_job`) — 시험방으로
    간 것이 그 분 이력에 서면 안 된다. 진짜 자동화를 시험 모드로 돌려 본다."""
    from app.models import AutoSendSetting, SendItem
    from app.services import automation, automation_runner as runner
    from app.services import sourcing_remind_log as log

    users["u2"].role = "admin"
    db.add(AutoSendSetting(kind="startup_ir", enabled=1, user_id=users["u2"].id))
    db.commit()
    automation.save(db, automation.SOURCING_REMIND, enabled=True, user_id=None,
                    test_mode=True, test_room="자동화 시험방")
    assert runner.run_once(db, automation.SOURCING_REMIND,
                           datetime(2026, 10, 14, 9, 0).astimezone())["status"] == "ready"
    items = db.execute(select(SendItem)).scalars().all()
    assert items and all(i.sourcing_contact_id is None for i in items)
    for item in items:
        item.status, item.sent_at = "sent", "2026-10-14T11:00:20+09:00"
    db.commit()

    assert log.history(db, [people["a"].id, people["b"].id], log.months(TODAY)) == {}


def test_only_the_asked_rows_come_back(db, users, people):
    """다른 갈래 · 지워진 줄의 리마인드는 그 줄 번호를 묻지 않았으면 안 온다."""
    from app.services import sourcing_remind_log as log

    _send(db, users, people["a"], "2026-10-02T14:05:00+09:00")
    _send(db, users, people["b"], "2026-10-02T14:06:00+09:00")
    got = log.history(db, [people["a"].id], log.months(TODAY))
    assert set(got) == {people["a"].id}
    assert log.history(db, [], log.months(TODAY)) == {}


# ── ⑤ 석 달보다 오래된 것 ─────────────────────────────────────────────────

def test_older_than_three_months_is_not_shown(db, users, people, page):
    from app.services import sourcing_remind_log as log

    a = people["a"]
    _send(db, users, a, "2026-07-31T23:59:00+09:00")
    _send(db, users, a, "2026-08-01T00:00:00+09:00", auto=True)
    got = log.history(db, [a.id], log.months(TODAY))
    assert list(got[a.id]) == ["2026-08"]
    assert _month_cells(_row(page(), a.id))["2026-08"] == ["8/1 00:00 자동"]
    assert "7/31" not in _row(page(), a.id)


# ── ⑥ 질의 수 ──────────────────────────────────────────────────────────────

def test_one_query_for_the_whole_table(db, users):
    from app.models import SourcingContact
    from app.services import sourcing_remind_log as log

    rows = []
    for n in range(40):
        row = SourcingContact(bucket=SERIES_A, position=n, name=f"심사역{n}")
        db.add(row)
        db.flush()
        rows.append(row)
    db.commit()
    for n, row in enumerate(rows):
        _send(db, users, row, f"2026-10-{(n % 20) + 1:02d}T11:00:00+09:00", auto=n % 2 == 0)
        _send(db, users, row, f"2026-09-{(n % 20) + 1:02d}T15:00:00+09:00")

    seen = []

    def count(*_args, **_kwargs):
        seen.append(1)

    shown = log.months(TODAY)
    event.listen(db.bind, "before_cursor_execute", count)
    try:
        got = log.history(db, [r.id for r in rows], shown)
    finally:
        event.remove(db.bind, "before_cursor_execute", count)

    assert len(got) == 40
    assert len(seen) == 1, f"40줄에 질의 {len(seen)}번 — 줄마다 묻고 있다"


# ── ⑦ 중복 막기와 같은 조건 한 벌 ─────────────────────────────────────────────

def test_dedup_and_the_table_read_the_same_condition(db, users, people):
    """`수동` 이 선 분은 그 달 자동이 빠지고, `자동` 만 선 분은 안 빠진다 —
    `manual_sourcing_remind` 가 하던 일 그대로다."""
    import inspect

    from app.services import automation_dedup, sourcing_remind_log as log

    a, b = people["a"], people["b"]
    _send(db, users, a, "2026-10-02T14:05:00+09:00")                # 수동
    _send(db, users, b, "2026-10-14T11:00:00+09:00", auto=True)     # 자동
    _send(db, users, b, "2026-10-03T09:00:00+09:00", status="failed")

    got = log.history(db, [a.id, b.id], log.months(TODAY))
    assert [s.how for s in got[a.id]["2026-10"]] == ["수동"]
    assert [s.how for s in got[b.id]["2026-10"]] == ["자동"]

    reason = automation_dedup.manual_sourcing_remind(db, a.id, "2026-10")
    assert reason.startswith(automation_dedup.PREFIX) and "10/2" in reason
    assert automation_dedup.manual_sourcing_remind(db, b.id, "2026-10") == ""
    assert automation_dedup.manual_sourcing_remind(db, a.id, "2026-09") == ""
    assert automation_dedup.manual_sourcing_remind(db, None, "2026-10") == ""

    # 두 곳이 같은 조건 · 같은 `자동` 판정을 지난다 — 한쪽만 고쳐지지 않게.
    for fn in (automation_dedup.manual_sourcing_remind, log.history):
        src = inspect.getsource(fn)
        assert "sourcing_remind_sent(" in src and "auto_items()" in src, fn.__name__


def test_the_shared_condition_spans_months_and_the_year_end(db, users, people):
    from app.models import SendItem, SendJob
    from app.services import automation_dedup

    a = people["a"]
    for when in ("2026-11-30T23:59:00+09:00", "2026-12-01T00:00:00+09:00",
                 "2026-12-31T23:59:00+09:00", "2027-01-01T00:00:00+09:00"):
        _send(db, users, a, when)

    def sent(first, last=None):
        return db.execute(
            select(SendItem.sent_at).join(SendJob, SendJob.id == SendItem.job_id)
            .where(*automation_dedup.sourcing_remind_sent(first, last))
            .order_by(SendItem.sent_at)).scalars().all()

    assert sent("2026-12") == ["2026-12-01T00:00:00+09:00", "2026-12-31T23:59:00+09:00"]
    assert sent("2026-11", "2027-01") == [
        "2026-11-30T23:59:00+09:00", "2026-12-01T00:00:00+09:00",
        "2026-12-31T23:59:00+09:00", "2027-01-01T00:00:00+09:00"]


# ── ⑧ 빈 화면 ──────────────────────────────────────────────────────────────

def test_the_page_renders_with_no_sends(page, people):
    html = page()
    assert html.count('data-testid="sourcing-remind-head"') == 3
    for who in ("a", "b"):
        assert _month_cells(_row(html, people[who].id)) == {
            "2026-08": [], "2026-09": [], "2026-10": []}


def test_the_page_renders_with_an_empty_list(client, users, today):
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    got = client.get("/sourcing")
    assert got.status_code == 200
    assert "아직 명단이 없습니다" in got.text
    assert "sourcing-remind-head" not in got.text


def test_the_all_tab_shows_history_too(db, users, people, page):
    from app.models import SourcingContact

    other = SourcingContact(bucket="M&A 찾는 투자사", position=1000, name="박다른",
                            firm="샘플애그")
    db.add(other)
    db.commit()
    _send(db, users, other, "2026-09-30T18:10:00+09:00")
    html = page("all")
    assert _month_cells(_row(html, other.id))["2026-09"] == ["9/30 18:10 수동"]
