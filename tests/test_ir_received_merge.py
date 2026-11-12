"""i239(11/12 팀원 요청) — `IR 자료` · `IR 자료 수신` 두 칸을 `IR 자료 수신` **한 칸**으로.

"IR 기업 현황 과 Series A 이상 딜 소개 > 컬럼 IR 자료, IR 자료수신 컬럼 -> IR 자료 수신
컬럼으로 통일 하나로 합처 주세요 내용도 합처 주세요".

두 칸은 값의 성질이 다르다.

  · `IR 자료` — 보낼 파일 이름(`ir_file_name`). 발송기가 자료 폴더 + 이 이름으로 파일을
    붙인다 — 글을 섞으면 첨부가 깨진다(`agent/sender/base.py` 의 `check_ir_file_name`).
  · `IR 자료 수신` — 관리자가 붙인 추가 메모 칸(받은 기록 글 · 구글 드라이브 수신 확인이
    적는 칸 — `gdrive_ir.COLUMN`).

그래서 **값은 제자리에 두고 칸 하나 안에 둘 다 그린다**(`custom_columns.absorb`). 못 박는 것:

1. 두 탭 모두 머리글은 `IR 자료 수신` 하나 — 추가 칸이 따로 서지 않는다.
2. 한 칸 안에 파일 이름(위)과 받은 기록(아래)이 **둘 다** 선다 — 어느 값도 안 사라진다.
3. 적는 길은 그대로다 — 파일 이름은 그 표의 PATCH, 받은 기록은 추가 칸 값 길.
4. 숨긴 칸은 안 보이고, 이름을 바꾼 칸은 따로 선다(관리자 뜻).
5. 화면 엑셀은 한 칸(파일 아래 기록), 전체 엑셀은 옛 차례 그대로(`IR 자료 파일명` + 끝의 추가 칸).
6. 옛 이름(`IR 자료`) 뒤에 골라 둔 추가 칸은 새 칸 뒤에 선다.

기업 이름 · 파일 이름은 전부 지어낸 것이다(공개 저장소).
"""
from __future__ import annotations

import io
import re

import pytest

FILE = "샘플가온_IR_2026.pdf"
MEMO = "2026/11/04 수신완료"


@pytest.fixture()
def stage(db, users):
    """IR 기업 셋(파일+기록 · 기록만 · 둘 다 없음) · Series A 둘(기록만 · IR 에도 있는 기업)."""
    from app.models import CustomColumnValue, IrCompany, SeriesACompany
    from app.services import custom_columns

    both = IrCompany(name="샘플가온", ir_file_name=FILE, received_at="2026-11-04")
    memo_only = IrCompany(name="샘플나래", received_at="2026-11-03")
    bare = IrCompany(name="샘플다온", received_at="2026-11-02")
    sa = SeriesACompany(name="샘플라온", received_at="2026-11-01")
    twin = SeriesACompany(name="샘플가온", received_at="2026-10-30")   # IR 에도 있음
    db.add_all([both, memo_only, bare, sa, twin])
    col = custom_columns.add(db, "companies", "IR 자료 수신", "memo", users["u1"].id)
    db.flush()
    # 운영과 같은 자리 — 관리자가 옛 `IR 자료` 뒤에 붙였다.
    col.after_key = "IR 자료"
    db.add_all([
        CustomColumnValue(column_id=col.id, row_table="ir_companies", row_id=both.id,
                          value=MEMO),
        CustomColumnValue(column_id=col.id, row_table="ir_companies", row_id=memo_only.id,
                          value="2026/11/03 메일 수신"),
        CustomColumnValue(column_id=col.id, row_table="series_a_companies", row_id=sa.id,
                          value="2026/11/01 수신완료"),
        CustomColumnValue(column_id=col.id, row_table="series_a_companies", row_id=twin.id,
                          value="2026/10/30 수신"),
    ])
    db.commit()
    return {"both": both, "memo_only": memo_only, "bare": bare, "sa": sa, "twin": twin,
            "col": col, "db": db}


def _heads(html: str, table_id: str) -> list:
    head = re.search(rf'id="{table_id}".*?</thead>', html, re.S).group(0)
    return [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", h)).strip()
            for h in re.findall(r"<th\b[^>]*>(.*?)</th>", head, re.S)]


def _row(html: str, row_id: int) -> str:
    return re.search(rf'<tr data-id="{row_id}".*?</tr>', html, re.S).group(0)


def _recv_td(row: str) -> str:
    """줄에서 `IR 자료 수신` 칸 — 받은 기록 칸(`ir-recv-memo`)을 품은 td."""
    tds = re.findall(r"<td\b.*?</td>", row, re.S)
    hit = [td for td in tds if "ir-recv-memo" in td]
    assert len(hit) == 1, f"받은 기록이 선 칸이 {len(hit)}개다"
    return hit[0]


# ── 1 · 2 · 3. 두 탭 — 머리글 하나 · 한 칸에 둘 다 ──────────────────────────────

def test_IR_기업_현황은_한_칸에_파일과_받은_기록이_선다(logged_in, stage):
    html = logged_in.get("/companies").text
    heads = _heads(html, "co-table")
    assert heads.count("IR 자료 수신") == 1, heads
    assert "IR 자료" not in heads, heads

    td = _recv_td(_row(html, stage["both"].id))
    # 파일 이름 — 그 표의 PATCH 로 고치는 칸 그대로(배지 · 필터 값도 그대로).
    assert 'data-field="ir_file_name"' in td and FILE in td and "📎 있음" in td
    # 받은 기록 — 추가 칸 값 길 그대로(`inline_edit.js` 의 `data-custom`).
    col = stage["col"]
    assert f'data-custom="{col.id}"' in td and 'data-custom-rows="ir_companies"' in td
    assert f">{MEMO}</div>" in td
    # 파일 묶음이 먼저(위), 받은 기록이 다음(아래).
    assert td.index("ir_file_name") < td.index("ir-recv-memo")

    td = _recv_td(_row(html, stage["memo_only"].id))
    assert "⚠ 없음" in td and ">2026/11/03 메일 수신</div>" in td
    # 빈 칸도 누를 자리는 선다(받은 기록 칸이 빈 채로).
    td = _recv_td(_row(html, stage["bare"].id))
    assert re.search(r'ir-recv-memo"[^>]*></div>', td)


def test_Series_A_탭도_한_칸에_파일과_받은_기록이_선다(logged_in, stage):
    html = logged_in.get("/companies?tab=series-a").text
    heads = _heads(html, "sa-table")
    assert heads.count("IR 자료 수신") == 1, heads
    assert "IR 자료" not in heads, heads

    td = _recv_td(_row(html, stage["sa"].id))
    assert 'data-field="ir_file_name"' in td
    assert 'data-custom-rows="series_a_companies"' in td and ">2026/11/01 수신완료</div>" in td

    # IR 기업 현황에도 있는 기업 — 파일은 IR 쪽 것을 보여만 주고, 이 줄의 받은 기록은 적는다.
    td = _recv_td(_row(html, stage["twin"].id))
    assert 'data-field="ir_file_name"' not in td and f"📎 {FILE}" in td
    assert ">2026/10/30 수신</div>" in td and f'data-custom="{stage["col"].id}"' in td


def test_받은_기록은_추가_칸_길로_적힌다(logged_in, stage):
    """칸 안의 받은 기록을 고치면 추가 칸 값이 바뀌고 파일 이름은 그대로다."""
    from app.models import CustomColumnValue, IrCompany

    col, row = stage["col"], stage["bare"]
    res = logged_in.put(f"/api/custom-values/ir_companies/{row.id}",
                        json={"column_id": col.id, "value": " 2026/11/12 수신완료 "})
    assert res.status_code == 200, res.text
    db = stage["db"]
    db.expire_all()
    cell = db.query(CustomColumnValue).filter_by(column_id=col.id, row_table="ir_companies",
                                                 row_id=row.id).one()
    assert cell.value == "2026/11/12 수신완료"
    assert db.get(IrCompany, row.id).ir_file_name is None
    # 화면에 그 칸 안에 선다 · 검색에도 걸린다(보이는 메모 칸 — #152).
    html = logged_in.get("/companies").text
    tr = _row(html, row.id)
    assert ">2026/11/12 수신완료</div>" in _recv_td(tr)
    assert "2026/11/12 수신완료" in re.search(r'data-search="([^"]*)"', tr).group(1)


# ── 4. 숨김 · 이름 바꾼 칸 ────────────────────────────────────────────────────

def test_숨긴_칸은_안_보인다(logged_in, stage):
    stage["col"].is_hidden = 1
    stage["db"].commit()
    html = logged_in.get("/companies").text
    body = html.split("<tbody>", 1)[1].split("</tbody>", 1)[0]
    assert "ir-recv-memo" not in body and MEMO not in body
    assert _heads(html, "co-table").count("IR 자료 수신") == 1


def test_이름을_바꾼_칸은_따로_선다(logged_in, stage):
    from app.services import custom_columns

    custom_columns.rename(stage["db"], stage["col"], "수신 메모")
    stage["db"].commit()
    html = logged_in.get("/companies").text
    heads = _heads(html, "co-table")
    assert heads.count("IR 자료 수신") == 1 and "수신 메모" in heads
    assert "ir-recv-memo" not in html.split("<tbody>", 1)[1]


def test_OX_칸은_빼내지_않는다():
    from app.models import CustomColumn
    from app.services import custom_columns

    memo = CustomColumn(id=1, target="companies", name="IR 자료 수신", kind="memo")
    ox = CustomColumn(id=2, target="companies", name="IR 자료 수신", kind="ox")
    other = CustomColumn(id=3, target="startup", name="IR 자료 수신", kind="memo")
    assert custom_columns.is_merged(memo)
    assert not custom_columns.is_merged(ox) and not custom_columns.is_merged(other)

    v = {"custom_target": "companies", "custom_cols": [ox, memo],
         "custom_vals": {7: {1: "기록", 2: "O"}, 8: {2: "X"}}}
    col, vals = custom_columns.absorb(v)
    assert col is memo and vals == {7: "기록"} and v["custom_cols"] == [ox]


# ── 5. 엑셀 ──────────────────────────────────────────────────────────────────

def _sheet(resp):
    import openpyxl

    assert resp.status_code == 200, resp.text
    ws = openpyxl.load_workbook(io.BytesIO(resp.content)).active
    rows = [[c.value for c in r] for r in ws.iter_rows()]
    return rows[0], {r[rows[0].index("기업명")]: r for r in rows[1:]}


def test_화면_엑셀은_한_칸에_파일_아래_기록(logged_in, u1_admin, stage):
    head, by = _sheet(logged_in.get("/api/export/companies-view.xlsx"))
    assert head.count("IR 자료 수신") == 1 and "IR 자료" not in head
    at = head.index("IR 자료 수신")
    assert by["샘플가온"][at] == f"{FILE}\n{MEMO}"
    assert by["샘플나래"][at] == "2026/11/03 메일 수신"
    assert by["샘플다온"][at] == "없음"


def test_전체_엑셀은_옛_차례_그대로(logged_in, u1_admin, stage):
    """받아 쓰던 수식이 머리글로 칸을 찾는다 — 파일 이름 칸 이름 · 자리는 그대로이고,
    받은 기록은 지금처럼 추가 칸으로 끝에 붙는다(값이 빠지지 않는다)."""
    head, by = _sheet(logged_in.get("/api/export/companies.xlsx"))
    assert by["샘플가온"][head.index("IR 자료 파일명")] == FILE
    assert head.count("IR 자료 수신") == 1
    assert by["샘플가온"][head.index("IR 자료 수신")] == MEMO


# ── 6. 옛 이름 뒤에 골라 둔 칸 ──────────────────────────────────────────────

def test_옛_IR_자료_뒤에_골라_둔_칸은_새_칸_뒤에_선다():
    from app.models import CustomColumn
    from app.services import custom_columns

    col = CustomColumn(target="companies", name="TIPS", kind="ox", after_key="IR 자료")
    assert custom_columns.anchor_of(col) == "IR 자료 수신"
    for tab, labels in custom_columns.anchor_groups("companies").items():
        assert "IR 자료 수신" in labels and "IR 자료" not in labels, tab


def test_컬럼_관리에_합친_칸이라고_알린다(client, users, db, stage):
    from tests.conftest import DEMO_PASSWORD

    users["u1"].role = "admin"
    db.commit()
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    html = client.get("/columns?target=companies").text
    assert "칸 안, 파일 이름 아래에 보입니다" in html
