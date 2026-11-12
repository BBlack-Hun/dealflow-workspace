"""i231 · i234 — 계약 칸들을 `기업명` 바로 오른쪽으로(IR 기업 현황 · Series A 이상 딜 소싱).

팀원 요청:
  · i231 "IR 기업현황 > 기업명 오른쪽으로 4개 컬럼 자리 이동시켜주세요 견적서 첨부, 계약여부,
    계약서 수신여부, 성공보수율"
  · i234 "Series A 이상 딜소싱 탭에서 > 기업명 컬럼 오른쪽으로 > 계약년월, 계약여부,
    계약서수신 여부 컬럼 기업명 오른쪽으로 컬럼 이동해주세요"

칸 이름 · 값 · 저장 길 · 필터 열쇠는 그대로이고 **자리만** 옮긴다. 나머지 칸의 차례도
그대로다(옮긴 칸이 빠진 자리의 앞뒤가 이어 붙는다). 머리글과 줄의 칸이 같은 차례인지,
화면 그대로 엑셀 · 추가 칸 기준점도 따라오는지 본다. 이름 · 값은 지어낸 것이다(공개 저장소).
"""
from __future__ import annotations

import io
import re

import pytest

from tests.test_company_tab_order import _head_names

IR_MOVED = ["견적서 첨부 여부", "계약여부", "계약서 수신 여부", "성공보수율"]
IR_FIELDS = ["quote_attached", "contract_status", "contract_received", "success_fee"]
SA_MOVED = ["계약년월", "계약여부", "계약서 수신 여부"]
SA_FIELDS = ["contract_ym", "contract_status", "contract_received"]


def _sa_heads(html: str) -> list:
    thead = re.search(r'id="sa-table".*?</thead>', html, re.S).group(0)
    return [re.sub(r"<[^>]+>", "", t).strip()
            for t in re.findall(r"<th\b[^>]*>(.*?)</th>", thead, re.S)]


def _first_row(html: str) -> str:
    return re.search(r"<tr data-id=.*?</tr>", html.split("<tbody>", 1)[1], re.S).group(0)


def _td_fields(row: str) -> list:
    """줄의 칸마다 그 칸 안의 첫 `data-field`(없으면 칸의 class) — 차례 그대로."""
    out = []
    for td in re.findall(r"<td\b.*?</td>", row, re.S):
        field = re.search(r'data-field="([^"]+)"', td)
        out.append(field.group(1) if field else re.search(r'<td\b[^>]*>', td).group(0))
    return out


@pytest.fixture()
def world(db):
    from app.models import IrCompany, SeriesACompany

    db.add(IrCompany(name="샘플가온", received_at="2026-09-01", assignee_name="가담당",
                     quote_attached="O", contract_status="paid", contract_received="X",
                     success_fee="3%", contract_ym="2026-10"))
    db.add(SeriesACompany(name="샘플나래", received_at="2026-09-02", assignee_name="나담당",
                          contract_ym="2026-11", contract_status="free",
                          contract_received="O"))
    db.commit()


def test_ir_tab_four_contract_columns_right_of_name(logged_in, world):
    html = logged_in.get("/companies").text
    names = _head_names(html)
    at = names.index("기업명") + 1
    assert names[at:at + 4] == IR_MOVED, names
    # 옮긴 칸 다음은 예전 `기업명` 다음 칸(`수신일`)이다.
    assert names[at + 4] == "수신일", names
    for name in IR_MOVED:
        assert names.count(name) == 1, (name, names)
    # 빠진 자리의 앞뒤는 이어 붙는다 — 나머지 차례는 그대로.
    seam = names.index("미팅제공일자")
    assert names[seam - 1:seam + 3] == ["담당별 소개", "미팅제공일자", "계약년월",
                                       "카톡 연결 여부"], names

    fields = _td_fields(_first_row(html))
    i = fields.index("name") + 1
    assert fields[i:i + 4] == IR_FIELDS, fields
    assert fields[i + 4] == "received_at", fields
    j = fields.index("meeting_offered_at")
    assert fields[j:j + 3] == ["meeting_offered_at", "contract_ym", "kakao_joined"], fields
    # 머리 수와 줄의 칸 수가 같아야 뒤 칸이 안 밀린다.
    assert len(fields) == len(names), (len(fields), len(names))


def test_ir_tab_moved_cells_keep_values_and_filters(logged_in, world):
    row = _first_row(logged_in.get("/companies").text)
    assert re.search(r'data-field="quote_attached"[^>]*data-filter-key="quote"[^>]*>O<', row)
    assert re.search(r'data-field="contract_status"[^>]*data-filter-key="contract"', row)
    assert ">유료계약완료</td>" in row
    assert re.search(r'data-field="contract_received"[^>]*data-filter-key="received"', row)
    assert re.search(r'data-field="success_fee">3%</td>', row)


def test_series_a_tab_three_contract_columns_right_of_name(logged_in, world):
    html = logged_in.get("/companies?tab=series-a").text
    heads = _sa_heads(html)
    at = heads.index("기업명") + 1
    assert heads[at:at + 3] == SA_MOVED, heads
    # 옮긴 칸 다음은 예전 `기업명` 다음 칸(`메모`)이다 — 그 뒤 차례도 그대로.
    assert heads[at + 3:at + 7] == ["메모", "수정한 팀원", "담당자", "수정한 날짜"], heads
    for name in SA_MOVED:
        assert heads.count(name) == 1, (name, heads)
    # 빠진 자리(`이메일` 뒤)는 `대분류` 로 이어진다.
    assert heads[heads.index("이메일") + 1] == "대분류", heads

    fields = _td_fields(_first_row(html))
    i = fields.index("name") + 1
    assert fields[i:i + 3] == SA_FIELDS, fields
    assert fields[i + 3] == "memo", fields
    assert fields[fields.index("ceo_email") + 1] == "sector_major", fields
    assert len(fields) == len(heads), (len(fields), len(heads))


def test_view_export_follows_screen_and_full_export_keeps_fixed_head(logged_in, u1_admin, world):
    import openpyxl

    from app.routers.data_io import COMPANY_HEADERS

    resp = logged_in.get("/api/export/companies-view.xlsx")
    assert resp.status_code == 200
    ws = openpyxl.load_workbook(io.BytesIO(resp.content)).active
    head, row = [[c.value for c in r] for r in ws.iter_rows(max_row=2)]
    at = head.index("기업명") + 1
    assert head[at:at + 5] == IR_MOVED + ["수신일"], head
    assert row[at:at + 4] == ["O", "유료계약완료", "X", "3%"], row

    # 전체 파일은 앞쪽 고정 머리글(받아 쓰는 수식이 머리글로 찾는다)을 그대로 둔다.
    resp = logged_in.get("/api/export/companies.xlsx")
    assert resp.status_code == 200
    ws = openpyxl.load_workbook(io.BytesIO(resp.content)).active
    full = [c.value for c in next(ws.iter_rows(max_row=1))]
    assert full[:len(COMPANY_HEADERS)] == COMPANY_HEADERS, full


def test_custom_column_anchors_follow():
    from app.services import custom_columns

    groups = custom_columns.anchor_groups("companies")
    ir = list(groups["IR 기업 현황"])
    at = ir.index("기업명") + 1
    # 성공보수율은 원래 이 목록(추가 칸을 둘 자리)에 없다 — 있는 셋만 같은 차례.
    assert ir[at:at + 4] == ["견적서 첨부 여부", "계약여부", "계약서 수신 여부", "수신일"], ir
    sa = list(groups["Series A 이상 딜 소싱"])
    at = sa.index("기업명") + 1
    assert sa[at:at + 4] == SA_MOVED + ["메모"], sa
    assert sa[sa.index("이메일") + 1] == "대분류", sa
