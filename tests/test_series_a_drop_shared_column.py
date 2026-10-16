"""#24(일부) — `Series A 이상 딜 소싱` 탭에서 `공유한 심사역` 칸을 뺀다.

사용자: "공유심사역 컬럼이 있고, 공유한 심사역 컬럼이 있는데 같은 의미임,
공유한 심사역 컬럼 없애줘".

빼는 것은 **표의 칸과 그 설명**뿐이다. 공유 기록(`series_a_shares`)과 Series A
딜 공유의 동작은 그대로이고, 받은 분 수는 줄에 그대로 실린다(`data-shared` —
[삭제] 확인창이 "공유 기록도 함께 지워진다" 고 말할 때 읽는다).

값은 전부 지어낸 것이다 — 저장소가 공개다.
"""
from __future__ import annotations

import re

import pytest


@pytest.fixture()
def companies(db):
    from app.models import SeriesACompany

    db.add_all([
        SeriesACompany(name="샘플애그", received_at="2026-07-01",
                       deal_type="딜 소싱 네트워크", shared_by="가심사",
                       source_firm="가나벤처스", series="Series A"),
        SeriesACompany(name="샘플메디", received_at="2026-08-25",
                       shared_by="나심사", source_firm="다라인베스트"),
    ])
    db.commit()


def _table(html: str) -> str:
    return re.search(r'<table[^>]*id="sa-table".*?</table>', html, re.S).group(0)


def _heads(table: str):
    head = re.search(r"<thead>.*?</thead>", table, re.S).group(0)
    return [re.sub(r"<[^>]+>", "", h).strip()
            for h in re.findall(r"<th\b[^>]*>(.*?)</th>", head, re.S)]


def test_the_column_is_gone(logged_in, companies):
    table = _table(logged_in.get("/companies?tab=series-a").text)
    heads = _heads(table)
    assert "공유한 심사역" not in heads, heads
    # 이 딜을 **우리에게** 넘겨 준 분 칸은 그대로다 — 남는 쪽이다.
    assert "공유 심사역" in heads
    assert heads[:3] == ["NO", "기업명", "수신 일자"], heads
    assert 'class="sa-shared"' not in table and 'data-testid="sa-shared"' not in table


def test_every_row_still_lines_up_with_the_header(logged_in, companies):
    """칸 하나를 빼면서 머리글과 줄의 칸 수가 갈리면 값이 옆 칸 머리글 밑에 선다."""
    table = _table(logged_in.get("/companies?tab=series-a").text)
    heads = _heads(table)
    rows = re.findall(r"<tr data-id=.*?</tr>", table, re.S)
    assert len(rows) == 2
    for row in rows:
        tds = re.findall(r"<td\b", row)
        assert len(tds) == len(heads), (len(tds), len(heads))


def test_the_empty_table_spans_every_column(logged_in, db):
    table = _table(logged_in.get("/companies?tab=series-a").text)
    span = re.search(r'<td colspan="(\d+)" class="muted">아직 받은 딜이 없습니다', table)
    assert span, table[-600:]
    assert int(span.group(1)) == len(_heads(table))


def test_the_footnote_no_longer_explains_it(logged_in, companies):
    html = logged_in.get("/companies?tab=series-a").text
    hint = html[html.index("</table>"):]
    hint = hint[:hint.index("</p>")]
    assert "공유한 심사역" not in hint
    # 남는 칸(`공유 심사역`)의 설명은 그대로다.
    assert "공유 심사역</b> 아래 후보" in hint


def test_rows_still_carry_how_many_received_it(logged_in, companies):
    """[삭제] 확인창이 읽는 수는 남는다 — 칸만 뺐다."""
    html = logged_in.get("/companies?tab=series-a").text
    rows = re.findall(r"<tr data-id=.*?>", html, re.S)
    assert rows and all('data-shared="0"' in r for r in rows), rows
