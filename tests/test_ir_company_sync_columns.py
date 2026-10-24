"""IR 기업 현황 새 칸 셋(0116) — 지역 · 견적서 첨부 여부 · 카톡 연결 여부.

투자컨설턴트 메타 탭에만 있던 **기업 사실**을 기준 표(IR 기업 현황)에도 세운다.
컨설팅 **진행 기록**(기업 관리 · 컨설팅 미팅일)은 IR 에 저장하지 않고 읽기만 한다
(결정 3 — `routers/companies.consulting_view`).
"""
from __future__ import annotations

import io
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def company(db):
    from app.models import IrCompany

    c = IrCompany(name="샘플지역랩")
    db.add(c)
    db.commit()
    return c


def _sheet(resp):
    from openpyxl import load_workbook

    ws = load_workbook(io.BytesIO(resp.content)).active
    grid = [list(r) for r in ws.values]
    return grid[0], grid[1:]


def test_이주는_0115_다음에_빈칸으로_붙는다():
    src = (ROOT / "alembic" / "versions" / "0116_ir_company_sync_columns.py").read_text("utf-8")
    assert 'down_revision = "0115_sourcing_tabs"' in src
    assert 'COLUMNS = ("region", "quote_attached", "kakao_joined")' in src
    assert "nullable=True" in src and "server_default" not in src


def test_수정_창과_표에서_고친다(logged_in, db, company):
    r = logged_in.patch(f"/api/companies/{company.id}",
                        json={"region": " 서울 ", "quote_attached": "o", "kakao_joined": "X"})
    assert r.status_code == 200, r.text
    # 소문자 `o` 는 대문자로 맞춰 돌려준다 — 화면이 그 값으로 칸을 되그린다.
    assert r.json()["quote_attached"] == "O" and r.json()["kakao_joined"] == "X"
    db.expire_all()
    assert (company.region, company.quote_attached, company.kakao_joined) == ("서울", "O", "X")
    row = logged_in.get(f"/api/companies/{company.id}").json()
    assert (row["region"], row["quote_attached"], row["kakao_joined"]) == ("서울", "O", "X")
    # 비우면 `아직 안 정함`(NULL)으로 돌아간다.
    logged_in.patch(f"/api/companies/{company.id}", json={"quote_attached": ""})
    db.expire_all()
    assert company.quote_attached is None


def test_O_X_칸에_모르는_말은_막는다(logged_in, company):
    r = logged_in.patch(f"/api/companies/{company.id}", json={"kakao_joined": "초대함"})
    assert r.status_code == 400
    assert "카톡 연결 여부" in r.json()["detail"]


def test_화면에_칸과_필터가_선다(logged_in, db, company):
    company.quote_attached, company.kakao_joined, company.region = "O", "X", "부산"
    db.commit()
    html = logged_in.get("/companies").text
    assert 'data-filters="quote:견적서 첨부 여부"' in html
    assert 'data-filters="joined:카톡 연결 여부"' in html
    assert 'data-f-quote="O"' in html and 'data-f-joined="X"' in html
    assert 'data-field="kakao_joined"' in html and 'id="f-kakao_joined"' in html
    # 견적서 → 미팅제공일자 → 계약여부 → 계약서 수신 여부 → 성공보수율(0119) → 카톡 연결 여부
    heads = [re.sub(r"<[^>]+>", "", h).strip() for h in re.findall(
        r"<th\b[^>]*>(.*?)</th>", re.search(r"<thead>(.*?)</thead>", html, re.S).group(1), re.S)]
    at = heads.index("견적서 첨부 여부")
    assert heads[at:at + 6] == ["견적서 첨부 여부", "미팅제공일자", "계약여부",
                                "계약서 수신 여부", "성공보수율", "카톡 연결 여부"], heads
    db_tab = logged_in.get("/companies?tab=db").text
    assert ">지역</th>" in db_tab and 'data-field="region">부산<' in db_tab
    assert 'id="f-region"' in db_tab


def test_엑셀_두_벌에_다_실린다(logged_in, db, company):
    company.quote_attached, company.kakao_joined, company.region = "O", "X", "부산"
    db.commit()
    head, rows = _sheet(logged_in.get("/api/export/companies.xlsx"))
    # 옛 IR 엑셀은 끝에 붙인다(결정 9) — 받아 쓰던 수식의 칸이 안 밀린다.
    assert head[-4:-1] == ["지역", "견적서 첨부 여부", "카톡 연결 여부"], head
    assert rows[0][-4:-1] == ["부산", "O", "X"]
    head, rows = _sheet(logged_in.get("/api/export/companies-view.xlsx"))
    assert rows[0][head.index("견적서 첨부 여부")] == "O"
    assert rows[0][head.index("카톡 연결 여부")] == "X"
    # 화면 그대로 엑셀은 필터도 같이 건다.
    head, rows = _sheet(logged_in.get("/api/export/companies-view.xlsx?joined=O"))
    assert rows == []


def test_컨설팅_진행_기록은_읽기만_한다(logged_in, db, users, company):
    from app.models import ConsultingCompany
    from app.services import consulting_sheets as cs

    sheets = cs.by_kind(db)
    db.add_all([
        ConsultingCompany(user_id=users["u1"].id, sheet=sheets[cs.STARTUP].label,
                          company_name="샘플지역랩", management="관리 중 : 미팅 완",
                          meeting_at="9/16 PM2", ir_company_id=company.id),
        # 계약 탭의 `meeting_at` 은 계약월이라 안 섞인다.
        ConsultingCompany(user_id=users["u1"].id, sheet=sheets[cs.CONTRACT].label,
                          company_name="샘플지역랩", management="무료",
                          meeting_at="8", ir_company_id=company.id),
    ])
    db.commit()
    # 투자컨설턴트 화면을 못 보는 사람에게는 칸이 안 선다.
    assert "컨설팅 상태" not in logged_in.get("/companies").text
    users["u1"].can_view_consulting = 1
    db.commit()
    html = logged_in.get("/companies").text
    assert ">컨설팅 상태</th>" in html and ">컨설팅 미팅일</th>" in html
    assert 'title="관리 중">관리 중<' in html
    assert 'title="9/16 PM2">9/16 PM2<' in html
    assert ">8<" not in html
    # IR 에는 저장하지 않는다 — 고칠 칸도 없다.
    from app.models import IrCompany

    assert not hasattr(IrCompany, "consulting_status")


# ── 0119 — 성공보수율(결정 10 · 기업 동기화 2단계) ──────────────────────────────

def test_성공보수율은_0118_다음_빈칸_칸이고_수정창_표_엑셀에_선다(logged_in, db, company):
    src = (ROOT / "alembic" / "versions" / "0119_ir_success_fee.py").read_text("utf-8")
    assert 'down_revision = "0118_series_a_ir_file"' in src
    assert "nullable=True" in src and "server_default" not in src
    r = logged_in.patch(f"/api/companies/{company.id}", json={"success_fee": " 3% "})
    assert r.status_code == 200, r.text
    db.expire_all()
    assert company.success_fee == "3%"
    assert logged_in.get(f"/api/companies/{company.id}").json()["success_fee"] == "3%"
    html = logged_in.get("/companies").text
    assert 'id="f-success_fee"' in html and 'data-field="success_fee"' in html
    head, rows = _sheet(logged_in.get("/api/export/companies.xlsx"))
    assert head[-1] == "성공보수율" and rows[0][-1] == "3%"       # 옛 엑셀은 끝에(결정 9)
    head, rows = _sheet(logged_in.get("/api/export/companies-view.xlsx"))
    assert rows[0][head.index("성공보수율")] == "3%"
