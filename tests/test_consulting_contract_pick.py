"""투자컨설턴트 `월간 계약 업무현황표` 탭의 `계약여부`(`management`) — 고르는 칸.

자유 글이라 같은 뜻이 여러 꼴로 갈려 `/ir-link` 에 `값 다름` 으로 섰다. 보기는 그 탭이
쓰던 둘(`무료` · `유료` — 따라 고치기의 `TAB_WORDS`) + 빈칸이다.

  1. 화면이 보기를 세운다.
  2. 보기 밖 옛 값(자유 글)은 **지우지 않고 그대로 보인다.**
  3. 보기 값은 저장되고 IR 로 따라간다(`딜소개 불가` 안전장치도 그대로).
  4. 보기 밖 **새** 글자는 서버가 막는다 — 그 줄의 옛 값을 다시 보내는 것은 받는다.
  5. 다른 칸을 고쳐도 옛 값이 남는다.

이름 · 기업명은 전부 지어낸 값이다 — 저장소가 공개다.
"""
from __future__ import annotations

import re
from urllib.parse import quote

import pytest

from .conftest import DEMO_PASSWORD

CONTRACT = "월간 계약 업무현황표"
STARTUP = "스타트업"


@pytest.fixture()
def allowed(client, db, users):
    from app.services import consulting_sheets as cs

    users["u1"].can_view_consulting = 1
    db.commit()
    cs.ensure(db)
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    return client


def _row(db, users, sheet=CONTRACT, **kw):
    from app.models import ConsultingCompany

    row = ConsultingCompany(user_id=users["u1"].id, sheet=sheet, position=1, **kw)
    db.add(row)
    db.commit()
    return row


def _fresh(db, *rows):
    db.expire_all()
    return [db.get(type(r), r.id) for r in rows]


def _cell(allowed) -> str:
    body = allowed.get(f"/consulting?sheet={quote(CONTRACT)}").text
    m = re.search(r'<td class="cell" data-field="management"[^>]*>[^<]*</td>', body)
    assert m, "계약 탭에 계약여부 칸이 없습니다"
    return m.group(0)


def test_계약여부는_보기_둘을_세운다(allowed, db, users):
    from app.routers.consulting import CONTRACT_DONE_CHOICES, CONTRACT_TAB_CHOICES

    _row(db, users, company_name="샘플고름")
    assert CONTRACT_TAB_CHOICES == ("무료", "유료")
    # 메타 탭의 보기는 그대로다.
    assert CONTRACT_DONE_CHOICES == ("무료계약완료", "유료계약완료")
    assert 'data-choices="무료,유료"' in _cell(allowed)


@pytest.mark.parametrize("old", ["유료 90만", "구두로 유료 합의(메모)"])
def test_보기_밖_옛_값은_그대로_보인다(allowed, db, users, old):
    _row(db, users, company_name="샘플옛값", management=old)
    assert _cell(allowed).endswith(f">{old}</td>")


def test_보기_값은_저장되고_IR로_따라간다(allowed, db, users):
    from app.models import IrCompany

    ir = IrCompany(name="샘플계약사")
    db.add(ir)
    db.commit()
    con = _row(db, users, company_name="샘플계약사")
    meta = _row(db, users, sheet=STARTUP, company_name="샘플계약사")
    con, meta = _fresh(db, con, meta)
    assert con.ir_company_id == meta.ir_company_id == ir.id

    r = allowed.patch(f"/api/consulting/{con.id}", json={"management": "유료"})
    assert r.status_code == 200, r.text
    ir, con, meta = _fresh(db, ir, con, meta)
    assert (con.management, ir.contract_status, meta.contract_done) == \
        ("유료", "paid", "유료계약완료")

    # IR 에서 바꾸면 계약 탭에는 그 탭의 보기 말로 적힌다.
    allowed.patch(f"/api/companies/{ir.id}", json={"contract_status": "무료계약완료"})
    assert _fresh(db, con)[0].management == "무료"

    # `딜소개 불가` 인 IR 은 줄을 골라도 저절로 안 풀린다(`_guarded`).
    ir = _fresh(db, ir)[0]
    ir.contract_status = "blocked"
    db.commit()
    r = allowed.patch(f"/api/consulting/{con.id}", json={"management": "유료"})
    assert r.status_code == 200, r.text
    ir, con = _fresh(db, ir, con)
    assert con.management == "유료" and ir.contract_status == "blocked"


def test_보기_밖_새_글자는_막는다(allowed, db, users):
    con = _row(db, users, company_name="샘플막음")
    for text in ("무료계약완료", "유료 (구두)", "딜소개 불가"):
        r = allowed.patch(f"/api/consulting/{con.id}", json={"management": text})
        assert r.status_code == 400, (text, r.text)
        assert "무료 · 유료" in r.json()["detail"]
    assert not _fresh(db, con)[0].management
    # 새 줄도 같다.
    r = allowed.post("/api/consulting", json={"sheet": CONTRACT, "company_name": "샘플새줄",
                                              "management": "무료 예정"})
    assert r.status_code == 400, r.text
    r = allowed.post("/api/consulting", json={"sheet": CONTRACT, "company_name": "샘플새줄",
                                              "management": "무료"})
    assert r.status_code == 200, r.text
    # 빈칸(아직 안 정함)은 받는다.
    r = allowed.patch(f"/api/consulting/{con.id}", json={"management": ""})
    assert r.status_code == 200, r.text
    # 다른 탭의 `management` 는 `기업 관리` 자유 글이다 — 막지 않는다.
    meta = _row(db, users, sheet=STARTUP, company_name="샘플관리")
    r = allowed.patch(f"/api/consulting/{meta.id}", json={"management": "관리 중 : 미팅 완"})
    assert r.status_code == 200, r.text


def test_다른_칸을_고쳐도_옛_값이_남는다(allowed, db, users):
    con = _row(db, users, company_name="샘플남김", management="유료 90만")
    r = allowed.patch(f"/api/consulting/{con.id}", json={"success_fee": "3%"})
    assert r.status_code == 200, r.text
    # 그 줄의 옛 값을 그대로 다시 보내는 것도 받는다(수정창이 모든 칸을 보낼 때).
    r = allowed.patch(f"/api/consulting/{con.id}",
                      json={"management": " 유료 90만 ", "contract_fee": "90만"})
    assert r.status_code == 200, r.text
    con = _fresh(db, con)[0]
    assert (con.management, con.success_fee, con.contract_fee) == ("유료 90만", "3%", "90만")
    # 옛 값에서 다른 보기 밖 글자로는 못 바꾼다 — 보기로 다시 고르면 된다.
    assert allowed.patch(f"/api/consulting/{con.id}",
                         json={"management": "유료 100만"}).status_code == 400
    assert allowed.patch(f"/api/consulting/{con.id}",
                         json={"management": "유료"}).status_code == 200
    assert _fresh(db, con)[0].management == "유료"
