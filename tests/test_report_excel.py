"""업무 보고 → 엑셀 리포트.

업무 보고 화면(`/report`)을 **카톡 업무보고 대신** 쓴다. 화면에는 발송 기록이
나오는데 내려받기에는 안 들어가서, 파일을 받아도 결국 화면을 보며 손으로 옮겨
적어야 했다 — 그 옮겨 적기가 이 보고가 없애려던 일이다.

여기 검사들이 못 박는 것은 넷이다.

1. **화면 맨 위의 발송 패널이 엑셀에 들어간다.**
2. **중단된 회차를 완료로 세지 않는다.** 116명이 대상이었고 18건에서 멈춘
   회차를 `116개 완료` 로 적던 것이 이 보고를 만든 이유다. 화면에서 고친 그
   규칙이 파일에서 되살아나면 안 된다.
3. **화면 숫자 == 엑셀 숫자.** 두 곳에서 따로 세면 반드시 갈라진다.
4. **발송이 없는 달에도 깨지지 않는다.** 보고는 조용한 달에도 열린다.
"""
from __future__ import annotations

import io
import re
from datetime import date, timedelta

import pytest

from .conftest import DEMO_PASSWORD
# 회차 만들기는 발송 보고 검사와 **같은 것을 쓴다.** 회차의 모양(잡 · 발송 건 ·
# 회차일)이 바뀌면 두 검사가 함께 움직여야 하는데, 여기 따로 한 벌 적어 두면
# 한쪽만 옛 모양으로 남아 아무 말 없이 다른 것을 재게 된다.
from .test_report_sends import _round

openpyxl = pytest.importorskip("openpyxl")


@pytest.fixture()
def logged(client, users):
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    return client


def _book(response):
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith(
        "application/vnd.openxmlformats"), "엑셀로 와야 한다"
    return openpyxl.load_workbook(io.BytesIO(response.content))


def _grid(ws):
    """시트를 문자열 2차원 배열로. 좌표를 손으로 세지 않기 위해서다."""
    return [["" if c is None else c for c in row]
            for row in ws.iter_rows(values_only=True)]


def _find(grid, text):
    """그 글자로 **시작하는** 첫 줄. 없으면 None."""
    for row in grid:
        if row and str(row[0]).startswith(text):
            return row
    return None


def _row_with(grid, value):
    """그 값이 들어 있는 첫 줄 — 회차명처럼 첫 칸이 아닌 것을 찾을 때."""
    for row in grid:
        if value in [str(c) for c in row]:
            return row
    return None


def _download(client, month="2026-08", **params):
    query = "&".join([f"month={month}"] + [f"{k}={v}" for k, v in params.items()])
    return client.get(f"/api/export/report.xlsx?{query}")


# --- 1. 발송 패널이 들어간다 -----------------------------------------------------

def test_the_send_panel_is_in_the_file(logged, db, users):
    """화면 맨 위의 발송 패널 — 회차명·날짜(요일)·개사·대상·완료가 그대로."""
    _round(db, users, title="8/26 (8월 4주차)", when=date(2026, 8, 27),
           sent=97, companies=7)
    _round(db, users, title="09/02 (9월 1주차)", when=date(2026, 8, 27),
           kind="sourcing_intro", sent=2)

    wb = _book(_download(logged))
    assert wb.sheetnames == ["2026-08 발송", "2026-08 미팅", "2026-08 반응"], \
        "화면 순서대로 — 파일을 열면 첫 장이 화면 맨 위여야 한다"

    grid = _grid(wb["2026-08 발송"])
    flat = [str(c) for row in grid for c in row]
    assert "8월 발송  ·  딜 소개 · 딜 소싱" in flat
    for title in ("8/26 (8월 4주차)", "09/02 (9월 1주차)"):
        assert title in flat, f"{title} 회차가 파일에 없습니다"
    assert "8/27(목)" in flat, "날짜에 요일이 붙어야 한다 — 회차는 요일로 기억된다"

    row = _row_with(grid, "8/26 (8월 4주차)")
    # 날짜 | 회차명 | 딜 소개 | 대상 | 완료 | 안 나감 | …
    assert list(row[:6]) == ["8/27(목)", "8/26 (8월 4주차)", 7, 97, 97, 0]
    # 딜 소개 · 딜 소싱은 성격이 다른 일이라 사용자도 나눠 적었다
    assert _find(grid, "딜 소개   97건 완료") is not None
    assert _find(grid, "딜 소싱   2건 완료") is not None


def test_the_file_carries_the_whole_screen(logged, db, users):
    """발송만이 아니라 미팅·반응까지 — 화면을 보며 옮겨 적지 않게."""
    from app.models import IrRequest, Meeting, VcContact

    contact = VcContact(user_id=users["u1"].id, name="담당자하나",
                        title="심사역", firm="가나벤처스")
    db.add(contact)
    db.flush()
    # 결과 문의 날짜는 **오늘에서 잡는다.** 날짜를 박아 두었더니 그날이 오는
    # 순간(2026-09-03) `_call_state` 가 `예정` 대신 `오늘` 을 내놓아 검사가
    # 깨졌다 — 코드는 그대로인데 달력만 넘어간 것이다. 여기서 보려는 것은
    # "결과 문의를 언제 걸어야 하는지가 파일에 적히는가" 이지 특정 날짜가
    # 아니다.
    due = (date.today() + timedelta(days=7)).isoformat()
    db.add(Meeting(user_id=users["u1"].id, contact_id=contact.id,
                   company_name="샘플기업", kind="first",
                   scheduled_at="2026-08-24", status="done", outcome="review",
                   followup_due=due, note="긍정적"))
    db.add(IrRequest(user_id=users["u1"].id, contact_id=contact.id,
                     company_name="샘플기업", requested_at="2026-08-22",
                     status="delivered"))
    db.commit()

    wb = _book(_download(logged))
    meet = [str(c) for row in _grid(wb["2026-08 미팅"]) for c in row]
    assert "담당자하나" in meet and "가나벤처스" in meet and "샘플기업" in meet
    assert "긍정적" in meet, "딜 진행 관리에서 적은 후기를 그대로 가져온다"
    assert f"{due} 예정" in meet, "결과 문의를 언제 걸어야 하는지"

    react = [str(c) for row in _grid(wb["2026-08 반응"]) for c in row]
    assert "IR 요청 투자사   1건" in react
    assert "IR 미팅완료 리마인드 TEL 투자사   1건" in react


def test_the_screen_and_the_file_show_the_same_buckets(logged, db, users):
    """**화면의 갈래 == 파일의 갈래.**

    `이 달의 반응` 장은 화면이 쓰는 `buckets` 를 그대로 받아 적는다. 한쪽에서만
    갈래를 빼면 받은 파일에 화면에는 없는 표가 서 있게 되고, 그러면 어느 쪽을
    옮겨 적어야 할지 알 수 없다 — `IR 요청받은 기업`(= `IR 요청 투자사` 를
    기업명 순으로 다시 늘어놓은 것) 을 지울 때 실제로 갈릴 수 있던 자리다.
    """
    from app.models import IrRequest, Meeting, VcContact

    contact = VcContact(user_id=users["u1"].id, name="담당자하나",
                        title="심사역", firm="가나벤처스")
    db.add(contact)
    db.flush()
    db.add(Meeting(user_id=users["u1"].id, contact_id=contact.id,
                   company_name="샘플기업", kind="first",
                   scheduled_at="2026-08-24", status="done", outcome="review",
                   followup_due="2026-09-03"))
    db.add(IrRequest(user_id=users["u1"].id, contact_id=contact.id,
                     company_name="샘플기업", requested_at="2026-08-22",
                     status="delivered"))
    db.commit()

    # 화면 — `이 달의 반응` 칸의 갈래 이름. 위쪽 발송 패널도 같은 `bucket-head`
    # 를 쓰므로 그 칸부터 잘라 본다.
    panel = logged.get("/report?month=2026-08").text.split("이 달의 반응", 1)[-1]
    on_screen = [x.strip() for x in
                 re.findall(r'class="bucket-head">([^<]+)', panel)]
    assert on_screen, "화면에서 갈래를 못 찾았다 — 선택자가 바뀌었나"

    # 파일 — 갈래 머리는 `이름   N건` 한 줄이다(`_ReportSheet.group`).
    grid = _grid(_book(_download(logged))["2026-08 반응"])
    in_file = [m.group(1) for m in
               (re.match(r"^(.+?)\s{3}\d+건$", str(row[0])) for row in grid if row)
               if m]

    assert on_screen == in_file, "화면과 파일의 갈래가 다르다"
    assert "IR 요청받은 기업" not in on_screen, \
        "`IR 요청 투자사` 와 줄도 내용도 같은 갈래다 — 한 표로 족하다"


# --- 2. 중단된 회차는 완료가 아니다 ---------------------------------------------

def test_a_stopped_round_is_not_counted_as_done(logged, db, users):
    """**이 검사가 이 파일의 이유다.**

    대상 116명, 18건에서 중단. 손으로 쓴 보고는 `116개 완료` 였다.
    화면에서 고친 규칙이 엑셀에서 되살아나면 안 된다.
    """
    _round(db, users, title="08/27 (8월 4주차)", when=date(2026, 8, 27),
           sent=18, canceled=98, status="canceled")

    grid = _grid(_book(_download(logged))["2026-08 발송"])
    row = _find(grid, "8/27(목)")
    assert row is not None, "회차 줄이 없습니다"
    assert row[3] == 116, "대상은 116명이었다"
    assert row[4] == 18, "완료는 18건 — 116 이 아니다"
    assert row[5] == 98, "안 나간 98건이 드러나야 한다"
    assert row[6] == "중단 98건", "왜 안 나갔는지"
    assert row[7] == "중단됨", "'완료' 로 읽히면 안 된다"

    flat = [str(c) for r in grid for c in r]
    assert any("98건이 안 나갔습니다(회차 1개)" in c for c in flat), \
        "파일도 화면처럼 이것을 **먼저** 말해야 한다"
    # 116 이 완료 자리에 서 있으면 안 된다 — 요약 줄도 마찬가지다
    assert _find(grid, "보낸 건수") is not None
    kpi = _grid(_book(_download(logged))["2026-08 발송"])
    labels = _find(kpi, "보낸 건수")
    values = kpi[kpi.index(labels) + 1]
    assert values[0] == 18, "요약의 '보낸 건수' 도 실제로 나간 건이다"
    assert values[2] == 98, "'안 나감' 이 요약에 서 있어야 한다"


def test_the_stopped_round_is_marked_in_red(logged, db, users):
    """숫자만 맞으면 안 된다 — 눈에 띄어야 완료로 잘못 읽지 않는다."""
    _round(db, users, title="멀쩡한 회차", when=date(2026, 8, 5), sent=10)
    _round(db, users, title="멈춘 회차", when=date(2026, 8, 6),
           sent=18, canceled=98, status="canceled")

    ws = _book(_download(logged))["2026-08 발송"]
    fills = {}
    for row in ws.iter_rows():
        if row[1].value in ("멀쩡한 회차", "멈춘 회차"):
            fills[row[1].value] = (row[1].fill.fgColor.rgb or "")[-6:]
    assert fills["멈춘 회차"] == "FDECEC", "중단된 회차는 바탕이 붉어야 한다"
    assert fills["멀쩡한 회차"] != "FDECEC", "다 나간 회차는 조용해야 한다"


# --- 3. 화면 숫자 == 엑셀 숫자 ---------------------------------------------------

def test_the_numbers_match_the_screen(logged, db, users):
    """두 곳에서 따로 세면 반드시 갈라진다. 화면이 읽는 값과 대조한다."""
    from app.services import report

    _round(db, users, title="8/26 (8월 4주차)", when=date(2026, 8, 27),
           sent=97, companies=7)
    _round(db, users, title="08/27 (8월 4주차)", when=date(2026, 8, 27),
           sent=18, canceled=98, companies=7, status="canceled")
    _round(db, users, title="소싱 회차", when=date(2026, 8, 27),
           kind="sourcing_intro", sent=2)

    seen = report.monthly(db, 2026, 8, users["u1"], today=date.today())
    grid = _grid(_book(_download(logged))["2026-08 발송"])

    labels = _find(grid, "보낸 건수")
    values = grid[grid.index(labels) + 1]
    assert list(values[:9]) == [
        seen["sends"]["sent"], seen["sends"]["rounds"], seen["sends"]["left"],
        seen["total"], seen["done"], seen["followup_done"],
        seen["followup_open"], seen["ir_requested"], seen["ir_delivered"],
    ], "요약 줄이 화면 KPI 와 같아야 한다"

    deal = next(g for g in seen["sends"]["groups"] if g["key"] == "deal_intro")
    total = _find(grid, "합계")
    assert (total[3], total[4], total[5]) == (deal["target"], deal["sent"],
                                              deal["left"])
    assert total[4] == 115, "97 + 18 — 대상 213 도 116 도 아니다"
    # 개사는 더하면 안 된다 — 같은 딜을 다시 돌린 회차라 7 + 7 = 14 가 아니다.
    assert total[2] == "", "딜 소개 칸은 합계에서 비운다"
    assert deal["companies"] == 7
    assert _find(grid, f"딜 소개   {deal['sent']}건 완료") is not None
    assert any("딜 소개 7개사" in str(c) for row in grid for c in row)

    # 그리고 그려진 화면과도 같은 말을 해야 한다 — dict 만 대조하면 화면이
    # 그 값을 다른 자리에 그려도 이 검사는 통과한다.
    body = logged.get("/report?month=2026-08").text
    assert "<b>98건</b>이 안 나갔습니다(회차 1개)" in body
    for row in deal["rows"]:
        assert f'class="num">{row["sent"]}</td>' in body, \
            f"{row['title']} 의 완료 {row['sent']}건이 화면에 없습니다"


def test_the_scope_is_the_same_as_the_page(client, db, users):
    """같은 주소면 화면과 파일이 같은 범위여야 한다 — 관리자만 팀 전체를 본다."""
    from app.models import User
    from app.services import auth as auth_svc

    db.add(User(name="관리자시험", phone="01000000009", role="admin",
                password_hash=auth_svc.hash_password(DEMO_PASSWORD)))
    db.commit()
    _round(db, users, title="남의 회차", when=date(2026, 8, 6), sent=4,
           user_key="u2")

    # 팀원은 scope=team 을 붙여도 자기 것만
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    flat = [str(c) for row in _grid(_book(_download(client, scope="team"))["2026-08 발송"])
            for c in row]
    assert "남의 회차" not in flat
    assert any("이 달에는 나간 회차가 없습니다" in c for c in flat)

    # 관리자는 팀 전체를 보고, 누가 보냈는지도 나온다
    client.post("/login", data={"phone": "01000000009", "password": DEMO_PASSWORD})
    grid = _grid(_book(_download(client, scope="team"))["2026-08 발송"])
    flat = [str(c) for row in grid for c in row]
    assert "남의 회차" in flat
    assert users["u2"].name in flat, "팀 전체로 볼 때는 팀원 칸이 선다"
    # 팀원 한 사람만 고르면 그 사람 것만
    flat = [str(c) for row in _grid(
        _book(_download(client, member=users["u1"].id))["2026-08 발송"]) for c in row]
    assert "남의 회차" not in flat


def test_login_is_required(client):
    assert client.get("/api/export/report.xlsx", follow_redirects=False
                      ).status_code in (302, 303, 401, 403)


# --- 4. 이름은 `딜 소개` 다 -------------------------------------------------------

def test_the_column_is_called_deal_intro(logged, db, users):
    """`핵심 딜` 은 IR 기업현황의 `핵심/TOP Deal`(기업 등급)에도 쓰이던 말이라
    같은 말이 두 가지를 가리켰다. 여기 숫자는 **그 회차에 소개한 기업 수**다.
    화면과 파일이 같은 말을 써야 한다."""
    _round(db, users, title="8/26 (8월 4주차)", when=date(2026, 8, 27),
           sent=97, companies=7)

    grid = _grid(_book(_download(logged))["2026-08 발송"])
    flat = [str(c) for row in grid for c in row]
    assert "딜 소개" in flat, "표 머리글이 `딜 소개` 여야 한다"
    assert "핵심 딜" not in flat
    assert any("딜 소개 7개사" in c for c in flat)

    body = logged.get("/report?month=2026-08").text
    assert "핵심 딜" not in body, "화면에도 옛 이름이 남으면 안 된다"
    assert "딜 소개 7개사" in body


def test_top_deal_grade_keeps_its_own_name(logged, db):
    """이름 바꾸기가 **다른 뜻**까지 건드리면 안 된다.

    IR 기업현황의 `핵심/TOP Deal` 은 기업 하나에 붙는 등급(`top_deal_kind`)이고,
    발송 보고의 `딜 소개` 는 그 회차에 소개한 기업 수다. 서로 다른 것이다.
    """
    from app.models import IrCompany

    db.add(IrCompany(name="샘플기업", top_deal_kind="핵심", is_top_deal=1))
    db.commit()
    assert "핵심/TOP Deal" in logged.get("/companies").text


def test_the_meeting_company_column_is_named_the_same_everywhere(logged, db, users):
    """미팅의 기업 칸은 **화면에서도 파일에서도 `기업`** 이다.

    화면의 미팅 표는 기업을 담당자 칸 안에 태그로 얹고 있었다(머리글이 없었다).
    제 칸으로 빼면서 이름을 새로 지으면, 같은 것을 화면은 `기업명` · 파일은
    `기업` 으로 불러 또 갈린다 — 이미 `기업` 이라 부르던 곳(같은 화면의 '이 달의
    반응' 표 · 엑셀 미팅/반응 시트 · IR 화면)에 맞춘다.
    """
    from app.models import Meeting, VcContact

    contact = VcContact(user_id=users["u1"].id, name="담당자하나",
                        title="심사역", firm="가나벤처스")
    db.add(contact)
    db.flush()
    db.add(Meeting(user_id=users["u1"].id, contact_id=contact.id,
                   company_name="가나테크", kind="first",
                   scheduled_at="2026-08-24", status="done", outcome="review"))
    db.commit()

    grid = _grid(_book(_download(logged))["2026-08 미팅"])
    at = next((i for i, row in enumerate(grid)
               if "기업" in [str(c) for c in row]), None)
    assert at is not None, "엑셀 미팅 시트에 `기업` 머리글이 있어야 한다"
    head = [str(c) for c in grid[at]]
    assert "기업명" not in head, "화면과 다른 이름을 쓰면 안 된다"
    # 차례도 화면과 같다 — 담당자 · 투자사 다음이 기업이고, 그다음이 구분이다.
    assert head.index("기업") == head.index("투자사") + 1
    assert head.index("기업") < head.index("구분")
    # 값이 **그 칸에** 실린다 — 머리글만 세워 두고 값을 옆 칸에 넣으면
    # 파일을 열어 보기 전까지 아무도 모른다.
    assert str(grid[at + 1][head.index("기업")]) == "가나테크"

    screen = logged.get("/report?month=2026-08").text
    assert "기업명" not in screen, "화면 머리글도 `기업` 이다"


# --- 5. 조용한 달에도 열린다 -----------------------------------------------------

def test_a_month_with_no_sends_still_opens(logged, db, users):
    """보고는 아무 일도 없던 달에도 열린다 — 거기서 깨지면 아무도 안 쓴다."""
    wb = _book(_download(logged, month="2026-02"))
    assert wb.sheetnames == ["2026-02 발송", "2026-02 미팅", "2026-02 반응"]

    flat = [str(c) for row in _grid(wb["2026-02 발송"]) for c in row]
    assert any("이 달에는 나간 회차가 없습니다" in c for c in flat)
    labels = _find(_grid(wb["2026-02 발송"]), "보낸 건수")
    values = _grid(wb["2026-02 발송"])[
        _grid(wb["2026-02 발송"]).index(labels) + 1]
    assert list(values[:3]) == [0, 0, 0], "빈 달은 0 이지 빈칸이 아니다"

    meet = [str(c) for row in _grid(wb["2026-02 미팅"]) for c in row]
    assert any("이 달에는 기록된 미팅이 없습니다" in c for c in meet)
    react = [str(c) for row in _grid(wb["2026-02 반응"]) for c in row]
    # 빈 달이라고 갈래가 사라지면 안 된다 — `없습니다.` 라고 서 있어야 그 달에
    # 아무것도 없었다는 사실이 남는다. (넷인 이유는 `_buckets` 주석 참고)
    assert react.count("없습니다.") == 4, "네 갈래가 다 서 있어야 한다"


def test_a_broken_month_falls_back_to_today(logged, db, users):
    """주소를 손으로 고쳐 오는 일이 있다 — 화면과 **같은 규칙**으로 이 달을 연다."""
    today = date.today()
    wb = _book(logged.get("/api/export/report.xlsx?month=엉터리"))
    assert wb.sheetnames[0] == f"{today.year}-{today.month:02d} 발송"


# --- 리포트로 뽑을 수 있는가 -----------------------------------------------------

def test_it_is_laid_out_as_a_report(logged, db, users):
    """숫자만 맞으면 표지 없는 표 뭉치다. 뽑아서 읽을 수 있어야 한다."""
    from app.services import spreadsheet as sp

    _round(db, users, title="8/26 (8월 4주차)", when=date(2026, 8, 27), sent=97)
    wb = _book(_download(logged))
    ws = wb["2026-08 발송"]

    assert wb.properties.keywords == sp.EXPORT_MARK, \
        "되올리기 방지 표식 — 보고 파일을 업로드 칸에 넣으면 이력이 뻥튀기된다"
    assert ws["A1"].value == "2026년 8월 업무 보고"
    assert ws["A1"].font.bold and ws["A1"].font.size >= 14
    assert "뽑음" in str(ws["A2"].value), "언제·누구 것을 뽑았는지가 있어야 한다"

    head = next(row for row in ws.iter_rows() if row[0].value == "날짜")
    assert head[0].font.bold
    assert (head[0].fill.fgColor.rgb or "")[-6:] == "EEF2F7", "머리글 서식"
    assert head[0].border.bottom.style == "thin"

    assert ws.column_dimensions["B"].width >= 30, "회차명이 잘리면 못 읽는다"
    # 요약 머리글은 좁은 칸에서 두 줄로 접힌다(`진행한 미팅`) — 줄 높이를 22 로
    # 고정해 두면 아랫줄이 잘려 무엇을 센 숫자인지 모르는 표가 된다.
    kpi = next(row for row in ws.iter_rows() if row[0].value == "보낸 건수")
    assert ws.row_dimensions[kpi[0].row].height >= 30, "접힌 머리글이 잘린다"
    assert kpi[4].value == "진행한 미팅" and kpi[4].alignment.wrap_text
    assert ws.sheet_view.showGridLines is False, "표에 테두리를 직접 그린다"
    # 인쇄 설정 — '리포트로 뽑을 수 있게' 가 요청이었다
    assert ws.page_setup.orientation == "landscape"
    assert ws.page_setup.fitToWidth == 1, "가로로 잘려 나가면 안 된다"
    assert ws.page_setup.fitToHeight == 0, "세로는 몇 장이 되든 그대로"


def test_the_filename_says_which_month(logged, db, users):
    """받아 둔 파일이 여럿이면 어느 달 것인지 이름으로 알아야 한다."""
    got = _download(logged, month="2026-08")
    assert "%EC%97%85%EB%AC%B4%EB%B3%B4%EA%B3%A0_2026-08.xlsx" in \
        got.headers["content-disposition"], "업무보고_2026-08.xlsx"
