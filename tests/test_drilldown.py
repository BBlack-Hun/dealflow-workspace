"""숫자를 누르면 뜨는 상세 목록(#175 · #177 · #178 · #179 · #182) — `services/drilldown.py`.

지키는 것은 하나다: **화면 숫자와 목록이 같은 조건이다.** 목록의 묶음 수(`NO`)가
누른 숫자와 같아야 한다 — 반응 다섯 칸 · 달별 · 연간 · 업무 보고 미팅 카드 넷 모두.
"""
from __future__ import annotations

import json
from datetime import date

import pytest

from .conftest import DEMO_PASSWORD


@pytest.fixture()
def data(db, users):
    from app.models import (ContactActivity, IrCompany, IrRequest, Meeting, SheetOwner,
                            VcContact)

    db.add_all([SheetOwner(label="내 명단", user_id=users["u1"].id),
                SheetOwner(label="남의 명단", user_id=users["u2"].id)])
    a = VcContact(user_id=users["u1"].id, name="심사역가", firm="가나벤처스",
                  phone="010-0000-1111", address="서울 어딘가 1", source_sheet="내 명단")
    b = VcContact(user_id=users["u1"].id, name="심사역나", firm="다라인베스트",
                  source_sheet="내 명단")
    other = VcContact(user_id=users["u2"].id, name="남의심사역", firm="마바파트너스",
                      source_sheet="남의 명단")
    co = IrCompany(name="샘플애그", contact_name="대표가", contact_phone="010-0000-2222",
                   pre_value="120", revenue_2025="3억", revenue_recent="5", revenue_2027="9",
                   funding_total="20", raise_target="30")
    db.add_all([a, b, other, co])
    db.commit()
    db.add_all([
        # 시트 이력 — 한 투자사가 기업 둘을 요청(투자사 1곳 · 기업 2개)
        ContactActivity(contact_id=a.id, kind="ir_request", content="요청",
                        happened_at="2026-09-03",
                        company_names=json.dumps(["샘플애그", "샘플메디"], ensure_ascii=False)),
        # 날짜가 비고 달만 적힌 줄
        ContactActivity(contact_id=b.id, kind="ir_request", content="요청",
                        happened_at=None, month="2026-08",
                        company_names=json.dumps(["샘플애그"], ensure_ascii=False)),
        ContactActivity(contact_id=b.id, kind="meeting_set", content="미팅 확정",
                        happened_at="2026-08-20"),
        ContactActivity(contact_id=other.id, kind="ir_request", content="요청",
                        happened_at="2026-09-04",
                        company_names=json.dumps(["샘플페이"], ensure_ascii=False)),
        # 앱 기록
        IrRequest(user_id=users["u1"].id, contact_id=a.id, company_id=co.id,
                  company_name="샘플애그", status="open", requested_at="2026-09-10"),
        Meeting(user_id=users["u1"].id, contact_id=a.id, company_id=co.id,
                company_name="샘플애그", kind="first", status="done", outcome="hold",
                scheduled_at="2026-09-15", scheduled_time="14:00"),
        Meeting(user_id=users["u1"].id, contact_id=b.id, company_name="샘플애그",
                kind="first", status="done", followup_done=1, scheduled_at="2026-08-21"),
        Meeting(user_id=users["u1"].id, contact_id=b.id, company_name="샘플메디",
                kind="first", status="canceled", scheduled_at="2026-09-01"),
        Meeting(user_id=users["u2"].id, contact_id=other.id, company_name="샘플페이",
                kind="first", status="done", scheduled_at="2026-09-05"),
    ])
    db.commit()
    return {"a": a, "b": b, "other": other}


def _login(client, phone="01000000001"):
    client.post("/login", data={"phone": phone, "password": DEMO_PASSWORD})
    return client


@pytest.mark.parametrize("period", [{}, {"month": "2026-09"}, {"month": "2026-08"},
                                    {"year": "2026"}])
def test_reaction_list_has_as_many_groups_as_the_number(db, users, data, period):
    from app.services import dashboard, drilldown

    ids = dashboard.reaction_ids(db, users["u1"])
    want = dashboard._reaction_summary(db, ids, period.get("month", ""),
                                       int(period.get("year", 0)))
    for key in dashboard.REACTION_KEYS:
        if want[key] is None:          # 달로 못 가르는 칸 — 목록도 없다
            with pytest.raises(LookupError):
                drilldown.build(db, users["u1"], key, **period)
            continue
        got = drilldown.build(db, users["u1"], key, **period)
        assert got["count"] == want[key], (key, period)
        assert max([r["no"] or 0 for r in got["rows"]] or [0]) == want[key], key


def test_meeting_card_lists_match_the_report_cards(db, users, data):
    from app.services import drilldown, report

    month = report.monthly(db, 2026, 9, users["u1"])
    year = report.yearly(db, 2026, users["u1"])
    for key, _label in report.MEETING_CARDS:
        assert drilldown.build(db, users["u1"], key, month="2026-09")["count"] == month[key]
        got = drilldown.build(db, users["u1"], key, year="2026")
        assert got["count"] == year["totals"][key], key
        assert len(got["rows"]) == got["count"], "미팅 카드는 한 건이 한 줄"


def test_meeting_card_lists_call_the_first_column_meeting_date(client, db, users, data):
    """미팅 카드 넷의 첫 칸은 미팅 날(`scheduled_at`)이라 `미팅 일자`(11/11 사용자 요청) —
    반응 목록의 첫 칸은 반응이 일어난 날이라 `날짜` 그대로다. `미팅 일시` 칸은 그대로 둔다."""
    from app.models import Meeting
    from app.services import dashboard, drilldown, report

    for key, _label in report.MEETING_CARDS:
        got = drilldown.build(db, users["u1"], key, month="2026-09")
        assert got["headers"][0] == "미팅 일자", key
        assert "날짜" not in got["headers"] and "미팅 일시" in got["headers"], key
        by_id = {m.id: m.scheduled_at for m in db.query(Meeting)}
        days = {r["cells"][0] for r in got["rows"]}
        assert days <= set(by_id.values()), (key, days)
    for key in dashboard.REACTION_KEYS:
        assert drilldown.build(db, users["u1"], key)["headers"][0] == "날짜", key
    page = _login(client).get("/reactions/list?key=done&month=2026-09").text
    assert "<th>미팅 일자</th>" in page and "<th>날짜</th>" not in page


def test_columns_read_the_source_rows(db, users, data):
    """값은 투자사 명단 · IR 기업 현황 · 미팅 기록에서 그대로 읽는다(베껴 두지 않는다)."""
    from app.services import drilldown, pipeline

    got = drilldown.build(db, users["u1"], "meeting_done")
    heads = got["headers"]
    for h in ("심사역 이름", "투자사명", "연락처", "회사주소", "스타트업명", "기업 담당자",
              "기업 담당자 연락처", "Pre Value", "누적투자금액", "투자유치희망금액",
              "미팅 일시", "미팅 결과", "24년 매출", "25년 매출", "26년 매출", "27년 예상매출"):
        assert h in heads, h
    assert "23년 매출" not in heads, "연도 매출은 24~27년(27년 예상) 넷"
    row = next(dict(zip(heads, r["cells"])) for r in got["rows"]
               if r["cells"][heads.index("심사역 이름")] == "심사역가")
    assert row["투자사명"] == "가나벤처스"
    assert row["연락처"] == "010-0000-1111"
    assert row["회사주소"] == "서울 어딘가 1"
    assert row["기업 담당자"] == "대표가"
    assert row["기업 담당자 연락처"] == "010-0000-2222"
    assert row["Pre Value"] == "120억"
    assert row["26년 매출"] == "5억"
    assert row["25년 매출"] == "3억"
    assert row["27년 예상매출"] == "9억"
    assert row["미팅 일시"] == "2026-09-15 14:00"
    # 결과 글자는 `pipeline.OUTCOMES` 를 읽는다 — 결과 칸 말을 바꿔도(#176 · #183) 따라간다.
    assert row["미팅 결과"] == pipeline.OUTCOMES["hold"]


def test_a_request_row_carries_the_latest_meeting(db, users, data):
    """IR 요청 줄에는 같은 심사역 × 기업의 가장 최근 미팅을 붙인다(취소는 뺀다)."""
    from app.services import drilldown

    got = drilldown.build(db, users["u1"], "ir_contacts", month="2026-09")
    heads = got["headers"]
    rows = [dict(zip(heads, r["cells"])) for r in got["rows"]]
    agg = [r for r in rows if r["스타트업명"] == "샘플애그" and r["심사역 이름"] == "심사역가"]
    assert agg and all(r["미팅 일시"] == "2026-09-15 14:00" for r in agg)
    medi = [r for r in rows if r["스타트업명"] == "샘플메디"]
    assert medi and medi[0]["미팅 일시"] == "", "취소된 미팅은 붙이지 않는다"


def test_admin_dashboard_sums_the_team(client, db, users, data):
    """#175 — 관리자 대시보드의 반응은 팀원 것을 모두 합친 수다. 팀원은 그대로 본인 것."""
    from app.services import dashboard

    from app.models import Meeting

    db.query(Meeting).filter_by(contact_id=data["other"].id).update({"outcome": "pass"})
    db.commit()
    mine_all = dashboard.user_dashboard(db, users["u1"])
    mine = mine_all["reactions"]
    users["u2"].role = "admin"
    db.commit()
    team = dashboard.user_dashboard(db, users["u2"])
    assert team["reaction_team"] is True
    assert team["reactions"]["ir_contacts"] == mine["ir_contacts"] + 1
    assert team["reactions"]["meeting_done"] == mine["meeting_done"] + 1
    # 옆 `미팅 결과` 칸(#183)도 같은 팀 합계 — 범위가 옆 칸과 갈리면 안 된다.
    def results(d):
        return {r["key"]: r["count"] for r in d["meeting_results"]}

    assert results(mine_all) == {"pass": 0, "hold": 1, "investing": 0}
    assert results(team) == {"pass": 1, "hold": 1, "investing": 0}, "내 보류 + 남의 의사 없음"

    body = _login(client, "01000000002").get("/").text
    assert 'href="/reactions/list?key=ir_contacts&amp;scope=team"' in body
    page = client.get("/reactions/list?key=ir_contacts&scope=team").text
    assert "남의심사역" in page and "심사역가" in page


def test_member_cannot_widen_the_scope(client, db, users, data):
    body = _login(client).get("/reactions/list?key=ir_contacts&scope=team").text
    assert "심사역가" in body
    assert "남의심사역" not in body, "팀원은 scope=team 을 줘도 본인 것만"
    assert client.get(f"/reactions/list?key=ir_contacts&member={users['u2'].id}").text.count(
        "남의심사역") == 0


def test_monthly_numbers_and_report_cards_link_to_the_list(client, db, users, data):
    """#179 달별 숫자 · #177 업무 보고 미팅 카드 · #182 연간 반응 칸이 같은 목록을 연다."""
    from app.models import ContactActivity

    db.add(ContactActivity(contact_id=data["a"].id, kind="ir_request", content="요청",
                           happened_at=date.today().isoformat()))
    db.commit()
    _login(client)
    dash = client.get("/").text
    this_month = f"{date.today():%Y-%m}"
    assert f'href="/reactions/list?key=ir_contacts&month={this_month}"' in dash
    report = client.get("/report?month=2026-09").text
    for key in ("total", "done", "followup_done", "followup_open"):
        assert f'/reactions/list?key={key}&month=2026-09' in report, key
    yearly = client.get("/report?span=year&year=2026").text
    assert "2026년 반응" in yearly
    for key in ("ir_contacts", "meeting_contacts", "requested_companies", "meeting_done",
                "meeting_call"):
        assert f'href="/reactions/list?key={key}&amp;year=2026"' in yearly, key
    page = client.get("/reactions/list?key=meeting_done&year=2026")
    assert page.status_code == 200 and "심사역가" in page.text


def test_year_meeting_results_match_the_meeting_done_list(client, db, users, data):
    """#182 연간 반응 칸의 `미팅 결과`(결과별 건수 · #183)는 `IR 미팅완료 투자사` 상세 목록과
    같은 조건이다 — 결과별 수 = 그 목록의 `미팅 결과` 칸이 그 결과인 줄 수(모집단 · 해 같음)."""
    from collections import Counter

    from app.services import drilldown, pipeline

    for year in (2026, 2025):
        got = drilldown.build(db, users["u1"], "meeting_done", year=str(year))
        col = got["headers"].index("미팅 결과")
        listed = Counter(r["cells"][col] for r in got["rows"])
        results = drilldown.year_results(db, users["u1"], year)
        assert [(r["label"], r["count"]) for r in results] == [
            (label, listed.get(label, 0)) for label in pipeline.OUTCOME_CHOICES.values()], year
    assert {r["key"]: r["count"] for r in drilldown.year_results(db, users["u1"], 2026)} == {
        "pass": 0, "hold": 1, "investing": 0}

    yearly = _login(client).get("/report?span=year&year=2026").text
    panel = yearly.split("2026년 반응", 1)[1].split("</section>", 1)[0]
    assert "meeting-results" in panel, "연간 반응 칸에도 미팅 결과가 선다"
    assert f"<b>1</b>{pipeline.OUTCOME_CHOICES['hold']}" in panel


def test_list_has_one_number_column(client, db, users, data):
    """번호 칸은 묶음 번호(`NO`) 하나 — CSS 자동 줄 번호(#100)는 이 표에서 뺀다."""
    from .test_row_numbers import _opt_out

    page = _login(client).get("/reactions/list?key=ir_contacts").text
    table = page.split('id="reaction-list"', 1)[1].split("</thead>", 1)[0]
    assert table.count(">NO</th>") == 1
    assert "#reaction-list" in _opt_out(), "자동 번호가 같이 서서 번호 칸이 둘이 된다"


def test_unknown_key_or_unsplittable_month_is_404(client, db, users, data):
    _login(client)
    assert client.get("/reactions/list?key=nope").status_code == 404
    assert client.get("/reactions/list?key=meeting_call&month=2026-09").status_code == 404
    assert client.get("/reactions/list?key=ir_contacts&month=2026-13").status_code == 404


# ── i241 — 시트 이력 글 · 꼬리표 붙은 이름에서도 기업 칸을 채운다 ──────────────

def _rows(db, user, key="requested_companies"):
    from app.services import drilldown

    got = drilldown.build(db, user, key)
    return got, [dict(zip(got["headers"], r["cells"])) for r in got["rows"]]


def _ask(db, contact, *names):
    from app.models import ContactActivity

    db.add(ContactActivity(contact_id=contact.id, kind="ir_request", content="요청",
                           happened_at="2026-07-02",
                           company_names=json.dumps(list(names), ensure_ascii=False)))
    db.commit()


def test_sheet_text_and_tagged_names_still_find_the_company(db, users, data):
    """`1.샘플애그 요청 -> 8/4(화) 전달 완료` · `샘플넷 IR 전달` 처럼 적힌 시트 이력, IR 쪽
    이름에 `[딜소개 불가/…]` · `(영문)` 꼬리표가 붙은 기업도 IR 칸을 읽는다. 숫자는 그대로."""
    from app.models import IrCompany
    from app.services import dashboard

    db.add_all([IrCompany(name="샘플넷 [딜소개 불가/폐업위기]", contact_name="대표나",
                          contact_phone="010-0000-3333", pre_value="50"),
                IrCompany(name="샘플캣(Samplecat)", contact_name="대표다")])
    db.commit()
    before = dashboard._reaction_summary(db, dashboard.reaction_ids(db, users["u1"]))
    _ask(db, data["a"], "1.샘플애그 요청 -> 8/4(화) 전달 완료", "샘플넷 IR 전달",
         "샘플캣 전달 완료")
    got, rows = _rows(db, users["u1"])
    by = {r["스타트업명"]: r for r in rows}
    assert by["1.샘플애그 요청 -> 8/4(화) 전달 완료"]["기업 담당자"] == "대표가"
    assert by["샘플넷 IR 전달"]["기업 담당자 연락처"] == "010-0000-3333"
    assert by["샘플넷 IR 전달"]["Pre Value"] == "50억"
    assert by["샘플캣 전달 완료"]["기업 담당자"] == "대표다"
    # 묶음(숫자)은 적힌 글 그대로 센 것 — 기업을 찾았다고 묶음이 합쳐지지 않는다.
    assert got["count"] == before["requested_companies"] + 3


def test_two_companies_or_a_partial_name_stay_empty(db, users, data):
    """기업이 둘 걸리면 어느 것인지 모르므로 비운다. 부분일치(`샘플애그리`)는 안 한다."""
    from app.models import IrCompany

    db.add(IrCompany(name="샘플넷", contact_name="대표나"))
    db.commit()
    _ask(db, data["a"], "샘플애그 샘플넷 전달", "샘플애그리 전달")
    _got, rows = _rows(db, users["u1"])
    by = {r["스타트업명"]: r for r in rows}
    assert by["샘플애그 샘플넷 전달"]["기업 담당자"] == ""
    assert by["샘플애그리 전달"]["기업 담당자"] == ""


def test_empty_address_reads_a_colleague_at_the_same_firm(db, users, data):
    """회사주소가 빈 심사역 줄은 같은 투자사 다른 심사역 줄의 주소를 보인다(가장 많이 적힌 것)."""
    from app.models import VcContact

    db.add_all([VcContact(user_id=users["u2"].id, name=f"동료{i}", firm="(주)다라인베스트",
                          address=addr, source_sheet="남의 명단")
                for i, addr in enumerate(["서울 본사 3", "서울 본사 3", "부산 지점 9"])])
    db.commit()
    _got, rows = _rows(db, users["u1"], "ir_contacts")
    b = [r for r in rows if r["심사역 이름"] == "심사역나"]
    assert b and all(r["회사주소"] == "서울 본사 3" for r in b)
    a = [r for r in rows if r["심사역 이름"] == "심사역가"]
    assert a and all(r["회사주소"] == "서울 어딘가 1" for r in a), "제 주소가 있으면 그대로"


# ── i242 — 관리자 대시보드의 카톡방 연결 상태 · 내 투자사 선호도 팀 전체 합계 ──

# i252 — 이 칸의 이름. 옛 이름은 '내 투자사 선호'.
REQUESTERS_TITLE = "IR 자료를 많이 요청하신 심사역 순"


def test_member_dashboard_names_the_requesters_panel(client, db, users, data):
    body = _login(client).get("/").text
    head = body.split(REQUESTERS_TITLE, 1)[1].split("</h2>", 1)[0]
    assert "팀 전체 합계" not in head
    assert "내 투자사 선호" not in body, "옛 이름(i252 에서 바꿈)이 남아 있다"


def test_admin_rooms_and_requesters_sum_the_team(client, db, users, data):
    from app.services import dashboard

    mine = dashboard.user_dashboard(db, users["u1"])
    users["u2"].role = "admin"
    db.commit()
    team = dashboard.user_dashboard(db, users["u2"])

    def total(d):
        return sum(r["count"] for r in d["rooms"])

    assert (total(mine), total(team)) == (2, 3), "내 명단 2명 + 남의 명단 1명"
    # 남의 줄은 딜 제안 관리(본인 담당분만)로 체크해 보낼 수 없다 — 투자사 관리 현황 전체 탭.
    assert all(r["href"].startswith("/contacts?sheet=all&") for r in team["rooms"])
    names = {r["name"] for r in team["top_requesters"]}
    assert names == {"심사역가", "심사역나", "남의심사역"}
    assert "남의심사역" not in {r["name"] for r in mine["top_requesters"]}

    _login(client, "01000000002")
    body = client.get("/").text
    rooms = body.split("카톡방 연결 상태", 1)[1].split("</h2>", 1)[0]
    pref = body.split(REQUESTERS_TITLE, 1)[1].split("</h2>", 1)[0]
    assert "팀 전체 합계" in rooms and "팀 전체 합계" in pref
    assert "내 투자사 선호" not in body, "옛 이름(i252 에서 바꿈)이 남아 있다"
    # 몇 명까지 볼지 바꿔도(새로고침 없이 부르는 API) 같은 모집단이다.
    api = client.get("/api/dashboard/top-requesters?top=10").json()["rows"]
    assert {r["name"] for r in api} == names


def test_view_as_dashboard_is_the_members_own(client, db, users, data):
    """관리자가 팀원 화면으로 보면 반응 · 카톡방 · 선호 모두 **그 팀원 것**이다 — 팀 합계는
    관리자 본인 화면에서만(역할만 관리자인 보기용 사본이 팀 합계를 그리던 것을 막는다)."""
    from app.models import User
    from app.services import auth as auth_svc

    db.add(User(id=9, name="관리자", phone="01000000009", role="admin",
                password_hash=auth_svc.hash_password(DEMO_PASSWORD)))
    db.commit()
    _login(client, "01000000009")
    assert 'key=ir_contacts&amp;scope=team"' in client.get("/").text
    client.post("/account/view-as", data={"member_id": users["u1"].id, "next": "/"},
                follow_redirects=False)
    body = client.get("/").text
    assert "팀 전체 합계" not in body
    assert REQUESTERS_TITLE in body and "내 투자사 선호" not in body
    assert 'href="/reactions/list?key=ir_contacts"' in body
    api = client.get("/api/dashboard/top-requesters?top=10").json()["rows"]
    assert {r["name"] for r in api} == {"심사역가", "심사역나"}
