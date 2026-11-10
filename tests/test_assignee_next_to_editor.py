"""#209 — `담당자` 칸이 `수정한 팀원` 바로 오른쪽에 선다(IR 기업 현황 · Series A 이상 딜 소싱).

11/10 팀원 요청: "IR 기업현황 , A 이상 딜 소싱 > 수정한 팀원 오른쪽으로 담당자 컬럼 이동".
칸 · 필터 열쇠 · 고치는 길은 그대로이고 자리만 옮긴다. 화면 그대로 엑셀 · 추가 칸 기준점도
같은 차례다(머리글과 칸이 갈리면 값이 옆 머리글 밑에 선다). 이름은 지어낸 값이다(공개 저장소).
"""
from __future__ import annotations

import io
import re

import pytest

from tests.test_company_tab_order import _head_names


def _sa_heads(html: str) -> list:
    thead = re.search(r'id="sa-table".*?</thead>', html, re.S).group(0)
    return [re.sub(r"<[^>]+>", "", t).strip()
            for t in re.findall(r"<th\b[^>]*>(.*?)</th>", thead, re.S)]


def _tds(row: str) -> list:
    """줄의 `<td>` 여는 꼬리표들 — 차례 그대로."""
    return re.findall(r"<td\b[^>]*>", row)


@pytest.fixture()
def world(db):
    from app.models import IrCompany, SeriesACompany

    db.add(IrCompany(name="샘플가온", received_at="2026-09-01", assignee_name="가담당"))
    db.add(SeriesACompany(name="샘플나래", received_at="2026-09-02", assignee_name="나담당"))
    db.commit()


def test_ir_tab_assignee_right_of_editor(logged_in, world):
    html = logged_in.get("/companies").text
    names = _head_names(html)
    at = names.index("수정한 팀원")
    assert names[at + 1].startswith("담당자"), names
    assert names.count("담당자") == 1, names
    row = re.search(r"<tr data-id=.*?</tr>", html.split("<tbody>", 1)[1], re.S).group(0)
    tds = _tds(row)
    i = next(n for n, t in enumerate(tds) if 'class="updated-by' in t)
    assert 'data-field="assignee_name"' in tds[i + 1], tds[i:i + 2]


def test_series_a_tab_assignee_right_of_editor(logged_in, world):
    html = logged_in.get("/companies?tab=series-a").text
    heads = _sa_heads(html)
    at = heads.index("수정한 팀원")
    assert heads[at + 1] == "담당자" and heads[at + 2] == "수정한 날짜", heads
    row = re.search(r"<tr data-id=.*?</tr>", html, re.S).group(0)
    tds = _tds(row)
    i = next(n for n, t in enumerate(tds) if 'class="updated-by' in t)
    assert 'data-field="assignee_name"' in tds[i + 1], tds[i:i + 2]
    assert len(tds) == len(heads), (len(tds), len(heads))


def test_view_export_and_anchors_follow(logged_in, u1_admin, world):
    import openpyxl

    from app.services import custom_columns

    resp = logged_in.get("/api/export/companies-view.xlsx")
    assert resp.status_code == 200
    ws = openpyxl.load_workbook(io.BytesIO(resp.content)).active
    head, row = [[c.value for c in r] for r in ws.iter_rows(max_row=2)]
    at = head.index("수정한 팀원")
    assert head[at + 1] == "담당자" and row[at + 1] == "가담당", (head, row)
    groups = custom_columns.anchor_groups("companies")
    for tab in ("IR 기업 현황", "Series A 이상 딜 소싱"):
        names = list(groups[tab])
        assert names[names.index("수정한 팀원") + 1] == "담당자", (tab, names)
