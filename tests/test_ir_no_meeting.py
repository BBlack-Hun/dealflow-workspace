"""딜 진행 관리 › `IR 요청 후 미팅 없음` — 지금 기준으로 뽑는다.

못 박는 것.

1. 정의 — (심사역 한 사람, 기업) 한 쌍에 IR 요청이 있고 **완료·예정 미팅이 없다.**
   취소한 미팅은 없던 일 · 예정만 있으면 `미팅 예정` 쪽 · 완료면 빠진다.
   같은 기업이라도 다른 심사역은 따로 본다. 미팅은 **팀 누가 적었든** 센다.
   같은 분이 두 명단에 따로 있어도 한 사람이다. 기업은 번호가 한쪽에만 있어도 이름으로 맞춘다.
   `보내지 않음` 요청도 싣는다(상태에 적힌다).
2. 시트 이력 — `ir_request` 활동도 요청이고, 시트의 미팅 갈래(완료 · 확정 · 옛 값)와
   IR 요청 글의 `미팅완료` 도 미팅이다. `미팅 요청` · `미팅 진행하지 않겠다` 는 아니다.
3. 한 쌍에 요청이 여럿이면 한 줄 — 건수 · 첫/최근 요청일 · 전달 여부 · 경과일 · 출처.
4. 팀원은 제 것만, 관리자는 팀 전체가 기본(고르개) · 팀원 화면으로 보는 중이면 그 팀원.
5. 거르기(경과일 · 전달 여부 · 출처 · 보내지 않음 · 미팅 예정) — 화면과 엑셀이 같은 줄.
6. 딜 진행 관리 탭 줄에 선다.

이름·투자사명은 전부 지어낸 값이다(공개 저장소).
"""
from __future__ import annotations

import io
import json
import re
from datetime import date, timedelta

import pytest

from .conftest import DEMO_PASSWORD

TODAY = date(2026, 10, 21)


def _ago(days: int, today: date = TODAY) -> str:
    return (today - timedelta(days=days)).isoformat()


def _seed(db, users, today: date = TODAY):
    from app.models import ContactActivity, IrCompany, IrRequest, Meeting, VcContact

    u1, u2 = users["u1"].id, users["u2"].id
    kim = VcContact(user_id=u1, name="홍길동", title="심사역", firm="가나다벤처스")
    lee = VcContact(user_id=u1, name="이몽룡", title="이사", firm="라마바파트너스")
    park = VcContact(user_id=u2, name="성춘향", title="팀장", firm="사아자캐피탈")
    # 홍길동이 윤서아 명단에도 따로 있다 — 같은 분이다
    kim2 = VcContact(user_id=u2, name="홍 길동", title="심사역", firm="(주)가나다벤처스")
    agg = IrCompany(name="샘플애그")
    lab = IrCompany(name="테스트랩")
    farm = IrCompany(name="보기팜")
    db.add_all([kim, lee, park, kim2, agg, lab, farm])
    db.flush()

    def req(user, contact, company, name, days, status="open", delivered=None):
        db.add(IrRequest(user_id=user, contact_id=contact.id,
                         company_id=company.id if company else None,
                         company_name=name, requested_at=_ago(days, today),
                         status=status, delivered_at=delivered))

    def meet(user, contact, company, name, days, status):
        db.add(Meeting(user_id=user, contact_id=contact.id,
                       company_id=company.id if company else None,
                       company_name=name, scheduled_at=_ago(days, today), status=status))

    def act(contact, kind, days, content, names):
        db.add(ContactActivity(contact_id=contact.id, kind=kind, content=content,
                               happened_at=_ago(days, today),
                               company_names=json.dumps(names, ensure_ascii=False)))

    # 홍길동 × 샘플애그 — 요청 두 번(하나는 전달), 미팅은 취소뿐 → 남는다
    req(u1, kim, agg, "샘플애그", 40, "delivered", _ago(38, today))
    req(u1, kim, agg, "샘플애그", 10)
    meet(u1, kim, agg, "샘플애그", 5, "canceled")
    # 홍길동 × 테스트랩 — 미팅 예정 → `미팅 예정` 쪽
    req(u1, kim, lab, "테스트랩", 20, "delivered", _ago(19, today))
    meet(u1, kim, lab, "테스트랩", -3, "scheduled")
    # 홍길동 × 보기팜 — 미팅 완료가 **윤서아 명단의 홍길동**에 적혔다 → 빠진다
    req(u1, kim, farm, "보기팜", 12)
    meet(u2, kim2, farm, "보기팜", 1, "done")
    # 이몽룡 × 샘플애그 — 미팅 완료(다른 팀원이 적었다 · 번호 없이 이름만) → 빠진다
    req(u1, lee, agg, "샘플애그", 30, "delivered", _ago(29, today))
    meet(u2, lee, None, "(주)샘플애그", 2, "done")
    # 이몽룡 × 테스트랩 — 같은 기업을 홍길동은 미팅 예정이어도 이몽룡은 아니다 → 남는다
    req(u1, lee, lab, "테스트랩", 3)
    # 이몽룡 × 없는기업 — 우리 DB 에 없는 기업도 남는다
    req(u1, lee, None, "없는기업", 100)
    # 이몽룡 × 보류기업 — 보내지 않기로 한 요청도 싣는다(상태에 적힌다)
    req(u1, lee, None, "보류기업", 50, "dropped")
    # 성춘향(윤서아 담당) × 샘플애그 — 남의 줄
    req(u2, park, agg, "샘플애그", 15)

    # ── 시트 이력 ──
    # 이몽룡 × 시트기업A — 시트 요청뿐, 미팅은 `미팅 요청`(청했을 뿐) → 남는다
    act(lee, "ir_request", 60, "시트기업A IR 요청", ["시트기업A"])
    act(lee, "meeting_request", 55, "미팅 요청함", ["시트기업A"])
    # 이몽룡 × 시트기업B — 시트에 미팅 완료 → 빠진다
    act(lee, "ir_request", 70, "시트기업B", ["시트기업B"])
    act(lee, "meeting_done", 65, "미팅완료", ["시트기업B"])
    # 이몽룡 × 시트기업C — IR 요청 글에 `미팅완료` → 빠진다
    act(lee, "ir_request", 80, "시트기업C → 9/1 미팅완료", ["시트기업C"])
    # 이몽룡 × 시트기업D — `미팅 진행하지 않겠다` 는 만난 것이 아니다 → 남는다
    act(lee, "ir_request", 90, "시트기업D 검토 후 미팅 진행하지 않겠다고 함", ["시트기업D"])
    # 이몽룡 × 시트기업E — 옛 값 `meeting` 인데 취소 → 안 만났다 → 남는다
    act(lee, "ir_request", 75, "시트기업E", ["시트기업E"])
    act(lee, "meeting", 70, "미팅 취소", ["시트기업E"])
    # 이몽룡 × 시트기업F — 옛 값 `meeting`, 안 했다는 말 없음 → 만난 것 → 빠진다
    act(lee, "ir_request", 75, "시트기업F", ["시트기업F"])
    act(lee, "meeting", 70, "8/1", ["시트기업F"])
    # 이몽룡 × 테스트랩 — 시트에 미팅 확정 → 앱 요청이 `미팅 예정` 쪽으로 간다
    act(lee, "meeting_set", 2, "미팅확정", ["테스트랩"])
    # 기업 이름 없이 개수만 적힌 시트 요청 — 세기만 한다
    act(lee, "ir_request", 30, "핵심 딜 8개사", [])
    db.commit()


def _by_company(rows):
    return {(r["contact_name"], r["company"]): r for r in rows}


# --- 1·2·3. 정의 -----------------------------------------------------------

def test_definition_edge_cases(db, users):
    from app.services import ir_no_meeting

    _seed(db, users)
    rows, skipped = ir_no_meeting.rows(db, None, TODAY)
    got = _by_company(rows)

    assert set(got) == {
        ("홍길동", "샘플애그"),      # 취소한 미팅은 없던 일
        ("홍길동", "테스트랩"),      # 예정
        ("이몽룡", "테스트랩"),      # 같은 기업 · 다른 사람 — 시트 확정 → 예정
        ("이몽룡", "없는기업"),
        ("이몽룡", "보류기업"),      # 보내지 않음도 싣는다
        ("성춘향", "샘플애그"),
        ("이몽룡", "시트기업A"),     # 미팅 요청은 미팅이 아니다
        ("이몽룡", "시트기업D"),     # `미팅 진행하지 않겠다`
        ("이몽룡", "시트기업E"),     # 옛 값인데 취소
    }
    assert got[("홍길동", "테스트랩")]["scheduled_on"] == _ago(-3)
    assert got[("이몽룡", "테스트랩")]["scheduled"] is True
    assert got[("홍길동", "샘플애그")]["scheduled"] is False
    assert got[("이몽룡", "보류기업")]["status_label"] == "보내지 않음"
    assert skipped == 1


def test_one_row_per_pair_with_counts_and_dates(db, users):
    from app.services import ir_no_meeting

    _seed(db, users)
    got = _by_company(ir_no_meeting.rows(db, None, TODAY)[0])
    row = got[("홍길동", "샘플애그")]
    assert row["count"] == 2
    assert (row["first_at"], row["last_at"]) == (_ago(40), _ago(10))
    assert row["days"] == 10                       # 최근 요청에서 오늘까지
    assert row["state"] == "delivered" and row["delivered_at"] == _ago(38)
    assert row["firm"] == "가나다벤처스" and row["owners"] == "강민준"
    assert row["company_q"] == "샘플애그" and row["src"] == "app"

    other = got[("이몽룡", "없는기업")]
    assert other["company_q"] == "" and other["state"] == "open"
    sheet = got[("이몽룡", "시트기업A")]
    assert sheet["src"] == "sheet" and sheet["status_label"] == "시트 이력"
    assert sheet["owners"] == "강민준"            # 시트 이력의 담당은 명단 주인


def test_sorted_by_days_since_latest_request(db, users):
    from app.services import ir_no_meeting

    _seed(db, users)
    days = [r["days"] for r in ir_no_meeting.rows(db, None, TODAY)[0]]
    assert days == sorted(days, reverse=True)


# --- 3. 누가 무엇을 보나 ----------------------------------------------------

def _login(client, phone="01000000001"):
    client.post("/login", data={"phone": phone, "password": DEMO_PASSWORD})
    return client


def test_member_sees_only_their_own(client, db, users):
    _seed(db, users, date.today())
    c = _login(client)
    html = c.get("/ir/no-meeting").text
    assert "홍길동" in html and "성춘향" not in html
    html = c.get(f"/ir/no-meeting?member={users['u2'].id}").text   # 붙여 와도 제 것만
    assert "성춘향" not in html and "팀원 선택" not in html


def test_admin_sees_team_and_can_pick(client, db, users):
    _seed(db, users, date.today())
    users["u1"].role = "admin"
    db.commit()
    c = _login(client)
    html = c.get("/ir/no-meeting").text
    assert "홍길동" in html and "성춘향" in html and "팀원 선택" in html
    html = c.get(f"/ir/no-meeting?member={users['u2'].id}").text
    assert "성춘향" in html and "홍길동" not in html
    # 고른 팀원이 거르기 · 엑셀 주소에 이어 붙는다
    assert f"member={users['u2'].id}" in html.split("ir-no-meeting.xlsx", 1)[1][:120]


def test_view_as_defaults_to_the_viewed_member(client, db, users):
    from app.models import User
    from app.services import auth as auth_svc

    _seed(db, users, date.today())
    db.add(User(id=9, name="관리자", phone="01000000009", role="admin",
                password_hash=auth_svc.hash_password(DEMO_PASSWORD)))
    db.commit()
    _login(client, "01000000009")
    client.post("/account/view-as", data={"member_id": users["u2"].id, "next": "/"})
    html = client.get("/ir/no-meeting").text
    assert "성춘향" in html and "홍길동" not in html
    html = client.get("/ir/no-meeting?member=0").text                # [팀 전체]
    assert "성춘향" in html and "홍길동" in html


# --- 4. 거르기 · 엑셀 ---------------------------------------------------------

def _rows(html: str):
    body = html.split('id="irnm-table"', 1)[1].split("</table>", 1)[0]
    return re.findall(r"<tr data-pair>(.*?)</tr>", body, re.S)


def test_filters(client, db, users):
    _seed(db, users, date.today())
    c = _login(client)
    # 강민준 몫의 미팅 없음: 홍·샘플 · 이·없는 · 이·보류 · 이·시트A · 이·시트D · 이·시트E
    assert len(_rows(c.get("/ir/no-meeting").text)) == 6
    assert len(_rows(c.get("/ir/no-meeting?days=30").text)) == 5      # 홍·샘플(10일) 빠짐
    sent = _rows(c.get("/ir/no-meeting?sent=yes").text)
    assert len(sent) == 1 and "샘플애그" in sent[0]
    assert len(_rows(c.get("/ir/no-meeting?sent=no").text)) == 5
    assert len(_rows(c.get("/ir/no-meeting?src=app").text)) == 3
    assert len(_rows(c.get("/ir/no-meeting?src=sheet").text)) == 3
    rows = _rows(c.get("/ir/no-meeting?drop=hide").text)
    assert len(rows) == 5 and not any("보류기업" in r for r in rows)
    planned = c.get("/ir/no-meeting?view=scheduled").text
    rows = _rows(planned)
    assert len(rows) == 2 and all("테스트랩" in r for r in rows)
    assert _ago(-3, date.today()) in planned
    assert "기업 이름 없이 적힌 IR 요청 1건" in c.get("/ir/no-meeting").text


@pytest.mark.parametrize("q", ["days=abc", "days=-5", "sent=zzz", "view=zzz", "src=x",
                               "drop=x", "member=abc"])
def test_bad_query_does_not_500(client, db, users, q):
    _seed(db, users, date.today())
    res = _login(client).get(f"/ir/no-meeting?{q}")
    assert res.status_code in (200, 422)


def test_own_rows_link_to_deal_progress(client, db, users):
    _seed(db, users, date.today())
    html = _login(client).get("/ir/no-meeting").text
    row = next(r for r in _rows(html) if "없는기업" in r)
    assert 'href="/ir#requests"' in row                  # 열린 요청 — 보낼 자료 구역
    row = next(r for r in _rows(html) if "샘플애그" in r)
    assert 'href="/ir#delivered"' in row                 # 전달한 자료 구역
    assert 'href="/companies?q=' in row                  # 기업 → IR 기업 현황


def test_excel_matches_the_filtered_view(client, db, users):
    import openpyxl

    _seed(db, users, date.today())
    res = _login(client).get("/api/export/ir-no-meeting.xlsx?days=30&src=")
    assert res.status_code == 200
    ws = openpyxl.load_workbook(io.BytesIO(res.content)).active
    head = [c.value for c in ws[1]]
    assert head[:3] == ["기업명", "투자사", "심사역"] and "경과일" in head
    assert "미팅 예정일" not in head
    data = list(ws.iter_rows(min_row=2, values_only=True))
    assert [r[0] for r in data] == ["없는기업", "시트기업D", "시트기업E", "시트기업A", "보류기업"]
    assert head[-1] == "출처" and data[1][-1] == "시트 이력"

    res = _login(client).get("/api/export/ir-no-meeting.xlsx?view=scheduled")
    ws = openpyxl.load_workbook(io.BytesIO(res.content)).active
    assert [c.value for c in ws[1]][-1] == "미팅 예정일"
    assert [r[0] for r in ws.iter_rows(min_row=2, values_only=True)] == ["테스트랩", "테스트랩"]


# --- 5. 탭 ------------------------------------------------------------------

def test_tab_row(client, db, users):
    c = _login(client)
    for path in ("/ir", "/ir/calendar"):
        assert 'href="/ir/no-meeting"' in c.get(path).text
    html = c.get("/ir/no-meeting").text
    assert re.search(r'class="sheet-tab active" href="/ir/no-meeting">IR 요청 후 미팅 없음', html)
    assert not re.search(r'class="sheet-tab active" href="/ir">', html)
