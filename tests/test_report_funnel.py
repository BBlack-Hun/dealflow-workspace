"""업무 보고 맨 위의 진행 단계 깔때기.

수는 투자사 관리 현황의 깔때기와 **같은 것**(`deal_stage.funnel`)이어야 한다 —
두 화면이 다른 수를 내면 어느 쪽을 믿을지 모른다. 막대는 그 수를 '그 단계까지
온 사람' 으로 더한 것(`deal_stage.reach`)이라, %가 바로 앞 단계 대비 전환율이다.
"""
from __future__ import annotations

import re

import pytest

from app.services import deal_stage, sheet_owner

from .conftest import DEMO_PASSWORD


# --- 더하기 ------------------------------------------------------------------

def _counts(*numbers):
    """사다리 차례대로 칸마다 몇 명인지 → `funnel()` 과 같은 모양."""
    stages, cid = {}, 0
    for key, n in zip(deal_stage.LADDER, numbers):
        for _ in range(n):
            cid += 1
            stages[cid] = key
    return deal_stage.funnel(stages)


def test_reach_counts_everyone_who_got_that_far():
    rows = deal_stage.reach(_counts(2, 3, 0, 1, 0, 0, 1))

    # 칸마다 '여기 이상 간 사람' — 뒤 칸들의 합
    assert [r["reached"] for r in rows] == [7, 5, 2, 2, 1, 1, 1]
    # `funnel()` 의 수(지금 이 칸)는 그대로 남는다
    assert [r["count"] for r in rows] == [2, 3, 0, 1, 0, 0, 1]
    assert [r["key"] for r in rows] == deal_stage.LADDER
    # 바로 앞 칸 대비 % — 첫 칸은 비교할 앞이 없다
    assert [r["rate"] for r in rows] == [None, 71, 40, 100, 50, 100, 100]
    assert [r["lost"] for r in rows] == [0, 2, 3, 0, 1, 0, 0]
    # 강조는 가장 많이 빠진 칸 **하나**
    assert [r["worst"] for r in rows] == [False, False, True, False, False, False, False]
    # 폭은 첫 칸(전체) 대비
    assert rows[0]["width"] == 100 and rows[1]["width"] == pytest.approx(71.4)


def test_reach_with_nobody_keeps_every_step_and_divides_by_nothing():
    rows = deal_stage.reach(deal_stage.funnel({}))

    assert len(rows) == len(deal_stage.LADDER)
    assert all(r["reached"] == 0 and r["width"] == 0 and r["rate"] is None
               and not r["worst"] for r in rows)


def test_a_step_after_an_empty_one_has_no_rate():
    """앞 칸이 0 이면 나눌 수가 없다 — 0% 로 적으면 '다 빠졌다' 로 읽힌다."""
    rows = deal_stage.reach(_counts(3, 0, 0, 0, 0, 0, 0))
    assert rows[1]["rate"] == 0          # 3명 중 0명 — 진짜 0%
    assert rows[2]["rate"] is None       # 0명 중 — 비율이 없다


# --- 화면 --------------------------------------------------------------------

def _contact(db, user, name, *kinds, delivered=False):
    """`kinds` 는 시트에서 옮겨 온 기록의 종류(`ContactActivity.kind`)."""
    from app.models import ContactActivity, IrRequest, VcContact

    row = VcContact(user_id=user.id, name=name, firm="가나벤처스",
                    source_sheet=f"명단{user.id}")
    db.add(row)
    db.flush()
    for kind in kinds:
        db.add(ContactActivity(contact_id=row.id, kind=kind,
                               happened_at="2026-06-01", content="기록"))
    if delivered:
        db.add(IrRequest(user_id=user.id, contact_id=row.id, company_name="샘플테크",
                         status="delivered", requested_at="2026-06-02"))
    db.commit()
    return row


@pytest.fixture()
def people(db, users):
    """u1 은 다섯 명, u2 는 두 명 — 범위에 따라 수가 달라야 한다."""
    u1, u2 = users["u1"], users["u2"]
    _contact(db, u1, "가")                                   # 접촉 전
    _contact(db, u1, "나", "deal_intro")                     # 딜소개
    _contact(db, u1, "다", "deal_intro")
    _contact(db, u1, "라", "deal_intro", "ir_request")       # IR 자료 요청
    _contact(db, u1, "마", "deal_intro", delivered=True)     # IR 자료 전달
    _contact(db, u2, "바", "deal_intro")
    _contact(db, u2, "사", "meeting_done")                   # 미팅 완료
    return users


def _login(client, phone="01000000001"):
    client.post("/login", data={"phone": phone, "password": DEMO_PASSWORD})


def _section(body):
    start = body.index('class="panel stage-funnel"')
    return body[start:body.index("</section>", start)]


def _bars(body):
    """그린 깔때기 → 줄마다 (이름, 온 사람, 지금 이 칸, 폭)."""
    out = []
    for chunk in _section(body).split('<div class="stage-bar')[2:]:
        label = re.search(r'stage-bar-label">([^<]*)<', chunk).group(1)
        reached = int(re.search(r"<b>(\d+)</b>명", chunk).group(1))
        here = re.search(r"(?:지금 여기|접촉 전) (\d+)명", chunk)
        width = float(re.search(r'style="width:([\d.]+)%"', chunk).group(1))
        out.append((label, reached, int(here.group(1)) if here else reached, width))
    return out


def _expected(db, user, *, team_wide=False):
    ids = [c.id for c in sheet_owner.managed(db, user, team_wide=team_wide)]
    return deal_stage.reach(deal_stage.funnel(deal_stage.of_many(db, ids)))


def test_the_report_opens_with_the_same_numbers_as_deal_stage(client, db, people):
    _login(client)
    body = client.get("/report?month=2026-06").text

    # 맨 위 — 월간 카드보다 먼저 선다
    assert body.index("stage-funnel") < body.index("kpi-row slim")
    want = _expected(db, people["u1"])
    got = _bars(body)
    assert len(got) == len(deal_stage.LADDER) == len(want)
    assert [g[0] for g in got] == ["전체"] + [r["label"] for r in want[1:]]
    assert [g[1] for g in got] == [r["reached"] for r in want] == [5, 4, 2, 1, 0, 0, 0]
    # 지금 이 칸에 선 사람 = 투자사 관리 현황 깔때기의 수
    assert [g[2] for g in got] == [r["count"] for r in want] == [1, 2, 1, 1, 0, 0, 0]
    assert [g[3] for g in got] == [r["width"] for r in want]
    # 0 인 칸도 줄째 남는다
    assert sum(1 for g in got if g[1] == 0) == 3
    # 무엇을 센 것인지 제목이 말한다
    assert "내 담당" in _section(body) and "투자사 5명, 지금 기준" in _section(body)


def test_the_biggest_drop_is_the_only_highlight(client, db, people):
    _login(client)
    part = _section(client.get("/report?month=2026-06").text)
    # 딜소개 4 → IR 자료 요청 2 (2명), IR 2 → 1, 전체 5 → 4 … 가장 많이 빠진 곳은 하나
    assert part.count('stage-bar worst') == 1
    assert "가장 많이 빠짐 2명" in part
    assert "50%" in part                     # IR 자료 요청 = 딜소개 4명 중 2명


def test_it_is_readable_without_seeing_the_bars(client, db, people):
    _login(client)
    part = _section(client.get("/report?month=2026-06").text)
    label = re.search(r'role="img"\s+aria-label="([^"]*)"', part).group(1)
    for step in deal_stage.LADDER[1:]:
        assert deal_stage.LABELS[step] in label
    assert "전체 5명(접촉 전 1명)" in label and "앞 단계의 50%" in label


def test_the_scope_follows_the_report(client, db, people):
    """내 것 / 팀 전체 / 팀원 한 사람 — 보고가 쓰는 범위 그대로."""
    users = people
    users["u1"].role = "admin"
    db.commit()
    _login(client)

    mine = _bars(client.get("/report?month=2026-06").text)
    team = client.get("/report?month=2026-06&scope=team").text
    other = client.get(f"/report?month=2026-06&member={users['u2'].id}").text

    assert mine[0][1] == 5
    assert _bars(team)[0][1] == 7 and "팀 전체" in _section(team)
    assert [g[1] for g in _bars(team)] == [
        r["reached"] for r in _expected(db, users["u1"], team_wide=True)]
    assert [g[1] for g in _bars(other)] == [
        r["reached"] for r in _expected(db, users["u2"])] == [2, 2, 1, 1, 1, 1, 1]
    assert "윤서아 님 담당" in _section(other)


def test_a_member_cannot_widen_it_to_the_team(client, db, people):
    _login(client)
    body = client.get("/report?month=2026-06&scope=team").text
    assert _bars(body)[0][1] == 5 and "팀 전체" not in _section(body)


def test_yearly_view_shows_it_once_at_the_top(client, db, people):
    _login(client)
    body = client.get("/report?span=year&year=2026").text

    assert body.count('class="panel stage-funnel"') == 1
    assert body.index("stage-funnel") < body.index('id="m-1"')
    assert [g[1] for g in _bars(body)] == [5, 4, 2, 1, 0, 0, 0]
    # 고른 달과 상관없는 수다 — 다른 달을 골라도 같다
    assert _bars(client.get("/report?month=2025-01").text) == _bars(body)


def test_nobody_assigned_still_draws_every_step(client, db, users):
    _login(client)
    got = _bars(client.get("/report").text)
    assert len(got) == len(deal_stage.LADDER)
    assert all(g[1] == 0 and g[3] == 0 for g in got)
