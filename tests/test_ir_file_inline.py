"""IR 기업 현황 `IR 자료` 칸을 **표에서 바로** 고친다(#151).

팀원 요청: "IR 기업현황 > IR 없음 → 있음으로 [수정] 으로 안 가고 바로 수정할 수 있게".
`Series A 이상 딜 소싱` 탭의 같은 칸(0118)과 같은 길이다 — 칸을 눌러 파일 이름을 적으면
`PATCH /api/companies/{id}` 의 `ir_file_name` 하나가 가고, 비우면 `없음` 이 된다.

못 박는 것.

1. **저장 · 비우기** — 응답에 다듬은 `ir_file_name` 과 `has_ir` 가 실린다(화면이 배지와
   필터 값을 이것으로 다시 그린다 · `companies.js`).
2. **파일 이름이 아니면 400** — Series A 탭과 같은 판정(`_looks_like_a_file_name`). 발송기가
   거부할 값을 넣는 자리에서 먼저 막는다.
3. **값이 바뀔 때만 거른다** — 운영에는 파일 이름 자리에 문장이 든 줄이 있다. [수정] 창은
   [저장] 한 번에 모든 칸을 보내므로, 늘 거르면 그 줄은 메모 하나도 못 고친다.
4. **수정 로그에 남는다** — IR 기업은 공용 자료라 누가 고쳐도 남는다(`edit_log.WATCHED`).
5. **화면** — 칸이 `.cell[data-field=ir_file_name]` 이고 배지는 칸 밖(`cell-hint`)이다.

기업 이름 · 파일 이름은 전부 지어낸 것이다(공개 저장소).
"""
from __future__ import annotations

import json
import re

import pytest

FILE = "샘플애그_IR_2026.pdf"
#: 운영에 있는 모양 — 파일 이름 자리에 사람이 적은 문장(`:` · `/` 가 든다). 지어낸 글이다.
ODD = ("자료는 대표님께 따로 받기로 함: 9/30 회신 예정 — 받으면 파일 이름으로 바꿀 것. "
       "예전 링크(https://example.invalid/old) 는 만료")


@pytest.fixture()
def co(db):
    from app.models import IrCompany

    row = IrCompany(name="샘플애그", sector_major="애그테크")
    db.add(row)
    db.commit()
    return row


def _patch(client, company_id, **body):
    return client.patch(f"/api/companies/{company_id}", json=body)


# ── 1. 저장 · 비우기 ──────────────────────────────────────────────────────────

def test_표에서_파일_이름을_적으면_있음이_된다(logged_in, db, co):
    res = _patch(logged_in, co.id, ir_file_name=f"  {FILE} ")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["ir_file_name"] == FILE, "앞뒤 빈칸을 뗀 값을 돌려줘야 칸과 DB 가 같다"
    assert body["has_ir"] is True
    db.refresh(co)
    assert co.ir_file_name == FILE
    assert logged_in.get(f"/api/companies/{co.id}").json()["has_ir"] is True


def test_비우면_없음으로_돌아간다(logged_in, db, co):
    co.ir_file_name = FILE
    db.commit()

    res = _patch(logged_in, co.id, ir_file_name="")
    assert res.status_code == 200, res.text
    assert (res.json()["ir_file_name"], res.json()["has_ir"]) == ("", False)
    db.refresh(co)
    assert co.ir_file_name is None, "빈 글자가 아니라 비운 값(None)으로 남아야 한다"


# ── 2. 파일 이름이 아니면 400 ─────────────────────────────────────────────────

@pytest.mark.parametrize("bad", ["/Users/someone/IR/a.pdf", "C:\\IR\\a.pdf",
                                 "https://drive.google.com/x", ".hidden.pdf", "폴더/파일.pdf"])
def test_경로나_주소는_받지_않는다(logged_in, db, co, bad):
    from app.routers.companies import NOT_A_FILE_NAME

    res = _patch(logged_in, co.id, ir_file_name=bad)
    assert res.status_code == 400, res.text
    assert res.json()["detail"] == NOT_A_FILE_NAME
    db.refresh(co)
    assert co.ir_file_name is None, "거절했는데 값이 들어갔다"


def test_Series_A_탭과_같은_말로_거절한다(client, db, users, logged_in):
    """두 탭이 같은 칸을 다른 말로 거절하면 사람은 규칙이 둘인 줄 안다."""
    from app.models import SeriesACompany
    from app.routers.companies import NOT_A_FILE_NAME

    row = SeriesACompany(name="샘플에이랩", received_at="2026-10-15")
    db.add(row)
    db.commit()
    res = logged_in.patch(f"/api/series-a-companies/{row.id}",
                          json={"ir_file_name": "https://drive.google.com/x"})
    assert res.status_code == 400 and res.json()["detail"] == NOT_A_FILE_NAME


def test_새로_만들_때도_같은_판정이다(logged_in, db):
    from app.models import IrCompany

    res = logged_in.post("/api/companies", json={"name": "샘플메디",
                                                 "ir_file_name": "https://x.invalid/a.pdf"})
    assert res.status_code == 400, res.text
    assert db.query(IrCompany).filter_by(name="샘플메디").count() == 0

    res = logged_in.post("/api/companies", json={"name": "샘플메디", "ir_file_name": FILE})
    assert res.status_code == 200, res.text


# ── 3. 값이 바뀔 때만 거른다 ──────────────────────────────────────────────────

def test_이상한_값이_든_줄도_다른_칸은_저장된다(logged_in, db, co):
    co.ir_file_name = ODD
    db.commit()

    # 표에서 다른 칸 하나.
    assert _patch(logged_in, co.id, note="메모 고침").status_code == 200
    # [수정] 창 — 모든 칸을 한 번에, IR 자료는 **적혀 있던 그대로** 실려 간다.
    res = _patch(logged_in, co.id, name="샘플애그", sector_major="애그테크",
                 ir_file_name=ODD, note="창에서 고침")
    assert res.status_code == 200, res.text
    db.refresh(co)
    assert (co.ir_file_name, co.note) == (ODD, "창에서 고침"), "있던 값을 지우거나 바꾸면 안 된다"

    # 그 칸을 **바꾸면** 그때는 거른다 — 다른 문장으로도, 고친 문장으로도.
    assert _patch(logged_in, co.id, ir_file_name=ODD + " 추가").status_code == 400
    # 파일 이름으로 바꾸거나 비우는 것은 된다.
    assert _patch(logged_in, co.id, ir_file_name=FILE).status_code == 200
    assert _patch(logged_in, co.id, ir_file_name="").status_code == 200


def test_일괄_붙여넣기는_전과_같다(logged_in, db, co):
    """일괄 입력은 줄마다 같은 판정으로 건너뛴다(`_apply_ir_files`) — 이 고침과 따로 돈다."""
    pasted = f"샘플애그\t{FILE}\n샘플애그\thttps://drive.google.com/x"
    res = logged_in.post("/companies/ir-files", data={"pasted": pasted},
                         follow_redirects=False)
    assert res.status_code == 303
    db.refresh(co)
    assert co.ir_file_name == FILE


# ── 4. 수정 로그 ──────────────────────────────────────────────────────────────

def test_수정_로그에_남는다(logged_in, db, users, co):
    from app.models import EditLog

    assert _patch(logged_in, co.id, ir_file_name=FILE).status_code == 200
    db.expire_all()
    logs = db.query(EditLog).filter_by(table_name="ir_companies", row_id=co.id).all()
    assert logs, "IR 자료를 바꿨는데 수정 로그에 안 남았다"
    log = logs[-1]
    assert log.actor_user_id == users["u1"].id
    assert "ir_file_name" in [c["field"] for c in json.loads(log.changes_json)]


# ── 5. 화면 ──────────────────────────────────────────────────────────────────

def _row(html: str, company_id: int) -> str:
    return re.search(rf'<tr data-id="{company_id}".*?</tr>', html, re.S).group(0)


@pytest.mark.parametrize("path", ["/companies", "/companies?tab=db"])
def test_칸을_눌러_고친다(logged_in, db, co, path):
    from app.models import IrCompany

    filled = IrCompany(name="샘플메디", ir_file_name=FILE)
    db.add(filled)
    db.commit()
    html = logged_in.get(path).text

    empty = _row(html, co.id)
    assert 'data-field="ir_file_name"' in empty, "IR 자료 칸을 표에서 고칠 수 없다"
    cell = re.search(r'<div class="([^"]*)" data-field="ir_file_name"', empty)
    assert cell and "cell" in cell.group(1).split(), "inline_edit.js 는 `.cell[data-field]` 를 찾는다"
    # 필터 값은 친 파일 이름이 아니라 `● 있음`/`⚠ 없음` — inline_edit.js 가 친 글자를 행에
    # 적지 않고(`data-filter-derived`) companies.js 가 응답으로 적는다.
    opening = re.search(r'<div [^>]*data-field="ir_file_name"[^>]*>', empty).group(0)
    assert 'data-filter-key="ir"' in opening and "data-filter-derived" in opening, opening
    # 배지는 칸 **밖**이고, 눌러도 칸이 열린다(`cell-hint`) — 빈 칸은 누를 자리가 배지뿐이다.
    assert re.search(r'class="room-badge warn cell-hint ir-badge"[^>]*>⚠ 없음<', empty)
    assert 'data-f-ir="⚠ 없음"' in empty

    full = _row(html, filled.id)
    assert re.search(r'class="room-badge ok cell-hint ir-badge"[^>]*>📎 있음<', full)
    assert re.search(rf'data-field="ir_file_name"[^>]*title="{re.escape(FILE)}">{re.escape(FILE)}</div>',
                     full), "칸 글자는 파일 이름 그대로여야 한다 — 열었을 때 고칠 값이 된다"
    assert 'data-f-ir="● 있음"' in full
