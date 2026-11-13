"""딜 제안 관리 › 반응 없는 담당자 → 엑셀(i246 — 전화 리마인드용).

요청: "반응 없는 담당분 → 성함, 전화번호, 회사명 엑셀로 다운받을 수 있게".
받는 사람은 [반응 없는 담당자만] 단추가 세는 그분들 그대로다(`no_reaction.judged`) —
손으로 뺀 분 · 반응 있는 분 · 딜소개 전 · 감춘 줄 · 세지 않는 명단 · 남의 담당은 빠진다.

이름 · 번호는 전부 지어낸 것이다 — 저장소가 공개다.
"""
from __future__ import annotations

import io
import re
from datetime import date
from urllib.parse import unquote

import openpyxl
import pytest

from .conftest import DEMO_PASSWORD

SHEET = "가 명단"
HIDDEN_SHEET = "세지 않는 명단"
URL = "/api/export/no-reaction.xlsx"


@pytest.fixture()
def people(db, users):
    from app.models import ContactActivity, IrRequest, SheetOwner, VcContact

    u1, u2 = users["u1"], users["u2"]
    db.add_all([SheetOwner(label=SHEET, user_id=u1.id),
                SheetOwner(label=HIDDEN_SHEET, user_id=u1.id, is_hidden=1),
                SheetOwner(label="나 명단", user_id=u2.id)])
    today = date.today().isoformat()

    def person(name, owner=u1, sheet=SHEET, intro=True, **kw):
        c = VcContact(user_id=owner.id, name=name, firm=f"{name}벤처스", source_sheet=sheet,
                      connect_stage="connected", kakao_room_name=f"{name} 방",
                      channel_kakao=1, **kw)
        db.add(c)
        db.flush()
        if intro:
            db.add(ContactActivity(contact_id=c.id, kind="deal_intro", content="딜소개",
                                   happened_at=today, month=today[:7]))
        return c

    made = {
        "무반응": person("무반응", title="심사역", phone="010-0000-0101",
                       office_phone="02-000-0101", group_name="1군"),
        "회사번호": person("회사번호", office_phone="02-000-0102", group_name="2군"),
        "번호없음": person("번호없음", group_name="2군"),
        "뺀분": person("뺀분", phone="010-0000-0103",
                     no_reaction_cleared_at="2026-11-11T10:00:00+09:00"),
        "요청함": person("요청함", phone="010-0000-0104"),
        "딜소개전": person("딜소개전", phone="010-0000-0105", intro=False),
        "감춘줄": person("감춘줄", phone="010-0000-0106", is_hidden=1),
        "세지않음": person("세지않음", phone="010-0000-0107", sheet=HIDDEN_SHEET),
        "남의담당": person("남의담당", owner=u2, sheet="나 명단", phone="010-0000-0108"),
    }
    db.add(IrRequest(user_id=u1.id, contact_id=made["요청함"].id, company_name="샘플가",
                     requested_at=today))
    db.commit()
    return made


def _login(client, phone):
    client.post("/login", data={"phone": phone, "password": DEMO_PASSWORD})


def _sheet(resp):
    assert resp.status_code == 200, resp.text
    ws = openpyxl.load_workbook(io.BytesIO(resp.content)).active
    return [[("" if v is None else v) for v in row] for row in ws.iter_rows(values_only=True)]


def test_반응_없는_분만_성함_전화번호_회사명으로_나간다(logged_in, db, users, people):
    from app.services import no_reaction

    resp = logged_in.get(URL)
    rows = _sheet(resp)
    assert rows[0] == ["성함", "직함", "회사명", "전화번호", "번호 종류",
                       "마지막 딜소개", "회차 메모", "담당 팀원"]
    today = date.today().isoformat()
    body = {r[0]: r for r in rows[1:]}
    # 화면 단추가 세는 그분들 그대로 — 손으로 뺀 분 · 반응 · 딜소개 전 · 감춘 줄 ·
    # 세지 않는 명단 · 남의 담당은 없다.
    assert set(body) == {"무반응", "회사번호", "번호없음"}
    assert {people[n].id for n in body} == no_reaction.listed(db, users["u1"])
    # 휴대폰이 먼저 — 회사 번호가 함께 있어도 휴대폰이다. 앞자리 0 이 글자로 남는다.
    assert body["무반응"][:5] == ["무반응", "심사역", "무반응벤처스", "010-0000-0101", "휴대폰"]
    # 휴대폰이 없으면 회사 번호, 그것도 없으면 빈 칸.
    assert body["회사번호"][3:5] == ["02-000-0102", "회사"]
    assert body["번호없음"][3:5] == ["", ""]
    assert body["무반응"][5] == today and body["무반응"][7] == users["u1"].name
    # 차례는 화면 카드와 같다(그룹 → 이름).
    assert [r[0] for r in rows[1:]] == ["무반응", "번호없음", "회사번호"]
    name = unquote(resp.headers["content-disposition"])
    assert f"반응 없는 담당자_{today}.xlsx" in name


def test_딜제안관리에_엑셀_단추가_서고_반응_없는_분이_없으면_안_선다(client, db, users, people):
    from app.models import IrRequest

    _login(client, "01000000001")
    assert re.search(r'<a class="linkbtn" id="noreact-export" href="/api/export/no-reaction.xlsx"'
                     r' download\s+title="반응 없는 담당자 3명', client.get("/deals").text)

    _login(client, "01000000002")
    assert 'id="noreact-export"' in client.get("/deals").text
    # u2 의 한 분이 IR 을 요청하면 반응 없는 분이 없다 — 빈 파일을 내밀지 않는다.
    db.add(IrRequest(user_id=users["u2"].id, contact_id=people["남의담당"].id,
                     company_name="샘플나", requested_at=date.today().isoformat()))
    db.commit()
    assert 'id="noreact-export"' not in client.get("/deals").text


def test_남의_담당은_받을_수_없다(client, people):
    _login(client, "01000000002")
    rows = _sheet(client.get(URL))
    assert [r[0] for r in rows[1:]] == ["남의담당"]


def test_로그인_안_하면_못_받는다(client, people):
    resp = client.get(URL, follow_redirects=False)
    assert resp.status_code in (302, 303, 401)
