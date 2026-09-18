"""딜 진행 관리의 **고르는 두 칸** — 찾을 수 있는가, 그리고 안 깨지는가.

「요청 받았다고 적기」 폼에서 사람이 하는 일은 둘이다.

    ① 담당자를 고른다        — 고르는 칸에 133명이 들어 있다
    ② 요청받은 기업을 적는다  — 번호로도, 이름으로도 적는다

①은 이름을 알아도 목록을 훑어야 했고, ②는 344곳짜리 기업 DB 에 있는 이름을
사람이 한 글자씩 쳐야 했다.

**이 파일이 지키는 것은 "좁혀지는가" 가 아니라 그 옆의 것들이다.**

- 고르는 칸은 여전히 **번호**(`contact_id`)를 보낸다. 글자를 보내는 칸으로
  바뀌면 요청이 엉뚱한 담당자에게 적힐 길이 생긴다.
- **안 고르고 보낼 수 없다.** `required` 는 원래 아무 일도 안 하고 있었다 —
  첫 보기가 곧 어떤 사람이라, 폼을 열고 [기록] 만 눌러도 `회사 이름 순` 첫
  사람에게 요청이 적혔다.
- 후보 이름은 **서버가 한 번에** 싣는다(질의 하나). 타이핑마다 물으면 이름 한
  줄을 적는 동안 질의가 열 번 넘게 나간다.
- 딜소개 불가로 표시한 기업은 후보에 **안 뜬다** — 발송 화면이 목록에서 빼는
  그 기업이다(`routers/pages.py`).
- 담당자 고르기 한 벌을 **두 폼이 나눠 쓴다.** 두 곳에 같은 모양을 적어 두면
  한쪽에만 검색이 달린다.

화면이 실제로 어떻게 움직이는지(무엇으로 좁혀지는지 · 키보드로 고를 수
있는지 · 번호로 적는 길이 사는지)는 브라우저 검사가 본다 —
`tests/js/ir_contact_search_test.js` · `tests/js/ir_company_hint_test.js`.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from .conftest import DEMO_PASSWORD

ROOT = Path(__file__).resolve().parents[1]
IR_HTML = ROOT / "app" / "templates" / "ir.html"


@pytest.fixture()
def stage(client, db, users):
    """담당자 셋 + 기업 셋(그중 하나는 **딜소개 불가**)."""
    from app.models import IrCompany, SheetOwner, VcContact

    db.add(SheetOwner(label="내 명단", user_id=users["u1"].id))
    people = [
        VcContact(user_id=users["u1"].id, name="홍길동", title="심사역",
                  firm="가나벤처스", source_sheet="내 명단",
                  channel_kakao=1, connect_stage="connected"),
        VcContact(user_id=users["u1"].id, name="김철수", title="팀장",
                  firm="다라인베스트", source_sheet="내 명단",
                  channel_kakao=1, connect_stage="connected"),
        VcContact(user_id=users["u1"].id, name="이영희", title="대표",
                  firm="마바캐피탈", source_sheet="내 명단",
                  channel_kakao=1, connect_stage="connected"),
    ]
    companies = [
        IrCompany(name="샘플애그"),
        IrCompany(name="샘플메디"),
        # 더 이상 소개하면 안 되는 기업 — 후보에 뜨면 안 된다.
        IrCompany(name="샘플막힘", contract_status="blocked"),
    ]
    db.add_all(people + companies)
    db.commit()

    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    return {"client": client, "db": db, "user": users["u1"],
            "people": people, "companies": companies}


# ── ① 담당자 고르기 ─────────────────────────────────────────────────────────

def test_두_폼_모두_검색칸이_붙는다(stage):
    """요청 적기와 미팅 등록 **둘 다**. 한쪽만 붙는 것이 원래 문제다."""
    html = stage["client"].get("/ir").text

    picks = re.findall(r'data-contact-pick="([\w-]+)"', html)
    assert sorted(picks) == ["meeting-contact", "request-contact"], (
        f"검색칸이 두 폼에 다 안 붙었습니다: {picks}")

    # 검색칸이 가리키는 고르기가 **실제로 있어야** 한다 — 이름만 맞춰 두고
    # 칸이 없으면 화면은 멀쩡한데 검색만 조용히 아무 일도 안 한다.
    for pick_id in picks:
        assert f'<select id="{pick_id}" name="contact_id"' in html, (
            f"{pick_id} 를 가리키는 고르기가 없습니다")


def test_고르는_칸은_여전히_번호를_보낸다(stage):
    """`<input list=…>` 로 바꾸면 고른 값이 **글자**가 된다 — 안 바꿨는가."""
    html = stage["client"].get("/ir").text

    assert html.count('name="contact_id"') >= 2
    assert '<input list=' not in html, "담당자를 글자로 받는 칸이 생겼습니다"
    for person in stage["people"]:
        assert f'<option value="{person.id}"' in html, "번호가 보기에 안 실렸습니다"


def test_거르는_값이_이름과_투자사를_담는다(stage):
    """`data-search` — 딜 제안 관리의 담당자 카드와 같은 칸들이다."""
    html = stage["client"].get("/ir").text

    found = re.findall(r'data-search="([^"]*)"', html)
    joined = " / ".join(found)
    assert "홍길동" in joined and "가나벤처스" in joined, (
        "이름·투자사로 거를 수 없습니다")
    # 소문자로 싣는다 — 화면에서 대소문자를 가리지 않고 찾으려면 재료가
    # 소문자여야 한다(`deals.html` 과 같은 방식).
    assert all(v == v.lower() for v in found), "거르는 값이 소문자가 아닙니다"


def test_안_고르고는_보낼_수_없다(stage):
    """**빈 보기가 맨 앞**이다 — 그래야 `required` 가 실제로 막는다.

    이 칸은 원래도 `required` 였는데, 첫 보기가 곧 어떤 사람이라 아무것도 안
    고르고 [기록] 을 눌러도 그대로 넘어갔다. 그렇게 적힌 요청은 `회사 이름 순`
    첫 사람의 것이 된다 — 엉뚱한 투자사에게 자료를 보내게 되는 자리다.
    """
    from app.models import IrRequest

    html = stage["client"].get("/ir").text
    assert html.count('<option value="" selected>담당자를 고르세요</option>') == 2, (
        "빈 보기가 두 폼에 다 서 있지 않습니다 — required 가 아무 일도 안 합니다")

    # 화면만 막으면 값을 직접 보내는 길이 남는다 — 서버도 안 받는다.
    res = stage["client"].post("/ir/requests", follow_redirects=False,
                               data={"contact_id": "", "company_name": "샘플애그"})
    assert res.status_code == 422, "담당자 없이 보낸 요청이 받아들여졌습니다"
    assert stage["db"].query(IrRequest).count() == 0


def test_눌러서_넘어오면_그_사람이_골라져_있다(stage):
    """리마인드 구역에서 이름을 눌러 온 길. 빈 보기가 그것을 덮으면 안 된다."""
    who = stage["people"][0]
    html = stage["client"].get(f"/ir?contact={who.id}").text

    assert f'<option value="{who.id}" selected' in html
    assert '<option value="" selected>' not in html, (
        "골라 둔 사람이 있는데 빈 보기가 골라져 있습니다")


def test_담당자_고르기는_한_벌이다(stage):
    """두 폼이 **같은 매크로**를 쓴다 — 두 벌이면 한쪽만 고쳐진다."""
    src = IR_HTML.read_text(encoding="utf-8")

    assert src.count("{% macro contact_pick(") == 1, "고르기 한 벌이 아닙니다"
    assert src.count("{{ contact_pick(") == 2, (
        "두 폼이 그 한 벌을 안 씁니다 — 한쪽에만 검색이 달릴 자리입니다")
    # 매크로 밖에 **고르는 칸**이 또 있으면 그것이 두 벌이다.
    # ([자료 보내기] 폼의 숨은 칸은 고르는 칸이 아니다 — 이미 정해진 담당자를
    #  그대로 실어 보내는 자리라 검색이 붙을 곳이 아니다.)
    assert src.count('<select id="{{ pick_id }}" name="contact_id"') == 1
    assert src.count('<select name="contact_id"') == 0, (
        "담당자 고르기가 매크로 밖에도 적혀 있습니다")


# ── ② 기업명 후보 ───────────────────────────────────────────────────────────

def test_후보_이름을_서버가_한_번에_싣는다(stage):
    """화면이 그려질 때 한 번. 타이핑마다 묻지 않는다."""
    import json

    html = stage["client"].get("/ir").text
    found = re.search(r"<div id=\"opts-ir-company\" hidden data-names='([^']*)'",
                      html)
    assert found, "후보를 싣는 칸이 없습니다"
    names = json.loads(found.group(1))
    assert "샘플애그" in names and "샘플메디" in names


def test_딜소개_불가_기업은_후보에_없다(stage):
    """발송 화면이 목록에서 빼는 그 기업이다 — 고르는 자리라 이유가 같다."""
    import json

    html = stage["client"].get("/ir").text
    names = json.loads(
        re.search(r"data-names='([^']*)'", html).group(1))
    assert "샘플막힘" not in names, (
        "딜소개 불가 기업이 후보에 떴습니다 — 목록에 있는 것만으로 실수로 고릅니다")


def test_옛_말로_적힌_딜소개_불가도_빠진다(stage):
    """값이 `딜소개 불가` 라는 **말**로 적혀 있어도 걸러진다."""
    import json

    from app.models import IrCompany

    stage["db"].add(IrCompany(name="샘플옛말", contract_status="딜소개 불가"))
    stage["db"].commit()

    html = stage["client"].get("/ir").text
    names = json.loads(re.search(r"data-names='([^']*)'", html).group(1))
    assert "샘플옛말" not in names


def test_후보를_모으는_질의가_하나다(stage):
    """344곳짜리 표를 줄마다 읽으면 화면 한 번에 질의가 수백 번이 된다."""
    from sqlalchemy import event

    from app.db import engine
    from app.routers.ir import _company_names

    seen = []

    def watch(conn, cursor, statement, params, context, many):
        seen.append(statement)

    event.listen(engine, "before_cursor_execute", watch)
    try:
        names = _company_names(stage["db"])
    finally:
        event.remove(engine, "before_cursor_execute", watch)

    assert names, "후보가 비었습니다"
    assert len(seen) == 1, f"질의가 {len(seen)}번 나갔습니다: {seen}"
    # 줄 전체를 들고 오지 않는다 — 그리지도 않을 344줄이 화면에 실린다.
    assert "ir_companies.one_liner" not in seen[0], (
        "안 쓰는 칸까지 읽습니다")


def test_기업_칸은_여전히_여러_줄_칸이다(stage):
    """`<textarea>` 그대로다. `<input>` 으로 바뀌면 여러 개를 못 적는다."""
    html = stage["client"].get("/ir").text

    assert re.search(r'<textarea name="company_name" id="request-companies"[^>]*'
                     r'data-company-hint', html), (
        "요청받은 기업 칸이 여러 줄 칸이 아니거나 후보가 안 붙었습니다")


def test_번호로_적는_길이_그대로다(stage, db, users):
    """후보를 얹었다고 `2, 4` 가 깨지면 안 된다 — **서버는 후보를 모른다.**"""
    from app.models import (DealBatch, DealBatchCompany, IrRequest, SendItem,
                            SendJob)

    who = stage["people"][0]
    batch = DealBatch(user_id=users["u1"].id, title="8월 3주차",
                      sent_date="2026-08-19")
    db.add(batch)
    db.commit()
    for i, company in enumerate(stage["companies"][:2], start=1):
        db.add(DealBatchCompany(batch_id=batch.id, company_id=company.id,
                                position=i))
    job = SendJob(user_id=users["u1"].id, kind="deal_intro", batch_id=batch.id,
                  status="done")
    db.add(job)
    db.commit()
    db.add(SendItem(job_id=job.id, contact_id=who.id, status="sent",
                    room_name="홍길동 심사역님", message="…",
                    sent_at="2026-08-19T09:00:00+00:00"))
    db.commit()

    stage["client"].post("/ir/requests", follow_redirects=False,
                         data={"contact_id": who.id, "company_name": "2"})
    rows = db.query(IrRequest).all()
    assert [r.company_name for r in rows] == ["샘플메디"], (
        "번호로 적는 길이 깨졌습니다")


def test_자산이_화면에_실린다(stage):
    """스크립트가 안 실리면 검색칸은 아무 일도 안 하는 칸이 된다."""
    html = stage["client"].get("/ir").text

    assert "/static/js/ir_contact_search.js" in html
    assert "/static/js/ir_company_hint.js" in html
