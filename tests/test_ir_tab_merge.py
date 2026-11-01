"""#105 · #106 — `IR 기업 현황` 과 `스타트업DB` 탭을 **하나로** 합친다.

두 탭은 같은 표(`ir_companies`)의 두 가지 보기였다. 사용자 요청:
  · 탭을 `IR 기업 현황` 하나로 — 칸은 **하나도 빼지 않고** 모두(겹치는 칸은 한 번).
  · `기업 한줄 소개` 바로 오른쪽에 `딜 소개 문구`.
  · `수신일` 바로 오른쪽에 `수정한 날짜` · `수정한 팀원`.
옛 주소(`/companies?tab=db`)는 합친 탭으로 온다. 이름 · 값은 지어낸 것이다(공개 저장소).
"""
from __future__ import annotations

import io
import re

import pytest

from tests.conftest import DEMO_PASSWORD
from tests.test_company_tab_order import _head_names

# 합치기 전 `스타트업DB` 탭의 머리글(왼쪽부터). 가운데 매출 · 금액 칸은 해마다 이름이
# 바뀌어 `revenue_years.columns()` 가 끼운다(`_old_db`).
OLD_DB_BEFORE_YEARS = ["기업명", "수신일", "대표자명", "연락처", "이메일", "기업 한줄 소개"]
OLD_DB_AFTER_YEARS = ["특이사항 (장점)", "설립년도", "지역", "정책자금", "IR 자료"]


def _old_db() -> list:
    from app.services import revenue_years

    return (OLD_DB_BEFORE_YEARS + [label for _f, label in revenue_years.columns()]
            + OLD_DB_AFTER_YEARS)


@pytest.fixture()
def logged(client, users, db):
    from app.models import CustomColumn, IrCompany

    row = IrCompany(name="샘플가온헬스", received_at="2026-09-01", business_desc="샘플 소개",
                    one_liner="샘플 딜 소개", competitiveness="샘플 장점",
                    founded_year="2020", region="샘플시", guarantee="샘플 보증 1억")
    db.add(row)
    # 관리자가 붙인 칸 — 하나는 옛 스타트업DB 에만 있던 칸 뒤에 자리를 골랐다.
    db.add(CustomColumn(target="companies", name="TIPS", kind="ox", position=1))
    db.add(CustomColumn(target="companies", name="샘플 메모칸", kind="memo", position=2,
                        after_key="정책자금"))
    db.commit()
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    return client


def test_탭_줄에_스타트업DB_탭이_없다(logged):
    nav = re.search(r'<nav class="sheet-tabs co-tabs">(.*?)</nav>',
                    logged.get("/companies").text, re.S).group(1)
    assert "tab=db" not in nav and "스타트업DB" not in nav, nav
    assert "IR 기업 현황" in nav


def test_옛_스타트업DB_주소는_합친_탭을_그린다(logged):
    old = logged.get("/companies?tab=db")
    assert old.status_code == 200
    assert _head_names(old.text) == _head_names(logged.get("/companies").text)
    active = re.search(r'class="sheet-tab active"[^>]*>(.*?)</a>', old.text, re.S).group(1)
    assert "IR 기업 현황" in active, active


def test_옛_스타트업DB_칸이_하나도_빠지지_않고_한_번씩_선다(logged):
    names = _head_names(logged.get("/companies").text)
    missing = [n for n in _old_db() if n not in names]
    assert not missing, f"합친 탭에 빠진 칸: {missing}"
    named = [n for n in names if n]
    dup = sorted({n for n in named if named.count(n) > 1})
    assert not dup, f"두 번 선 칸: {dup}"
    assert "TIPS" in names and "샘플 메모칸" in names, "관리자가 붙인 칸이 빠졌습니다"


def test_수신일_오른쪽에_수정한_날짜와_팀원(logged):
    names = _head_names(logged.get("/companies").text)
    at = names.index("수신일") + 1
    assert names[at:at + 2] == ["수정한 날짜", "수정한 팀원"], names


def test_기업_한줄_소개_오른쪽에_딜_소개_문구(logged):
    names = _head_names(logged.get("/companies").text)
    assert names[names.index("기업 한줄 소개") + 1] == "딜 소개 문구", names


def test_옛_스타트업DB_칸은_눌러_고칠_수_있게_값과_함께_선다(logged):
    html = logged.get("/companies").text
    body = html.split("<tbody>", 1)[1]
    for field, value in (("competitiveness", "샘플 장점"), ("founded_year", "2020"),
                         ("region", "샘플시"), ("guarantee", "샘플 보증 1억")):
        assert re.search(rf'class="cell[^"]*" data-field="{field}"[^>]*>{value}<', body), field
    # 머리 수와 첫 줄 칸 수가 같아야 뒤 칸이 안 밀린다.
    head = html.split("<thead>", 1)[1].split("</thead>", 1)[0]
    first = re.search(r"<tr data-id=.*?</tr>", body, re.S).group(0)
    assert len(re.findall(r"<th\b", head)) == len(re.findall(r"<td\b", first))


def test_자리_고르기는_합친_탭_하나다():
    from app.services import custom_columns

    groups = custom_columns.anchor_groups("companies")
    assert "스타트업DB" not in groups
    assert set(_old_db()) <= set(groups["IR 기업 현황"])


def test_지금_화면_내려받기는_합친_탭의_칸_그대로다(logged):
    import openpyxl

    html = logged.get("/companies").text
    screen = [n for n in _head_names(html)
              if n and n not in ("TIPS", "샘플 메모칸", "컨설팅 상태", "컨설팅 미팅일")]
    resp = logged.get("/api/export/companies-view.xlsx")
    assert resp.status_code == 200
    ws = openpyxl.load_workbook(io.BytesIO(resp.content)).active
    head, row = [[c.value for c in r] for r in ws.iter_rows(max_row=2)]
    # 화면의 `소개 횟수` 한 칸이 파일에서는 둘(회 · 명)이다. 추가 칸은 고른 자리에 낀다.
    assert [h for h in head if h not in ("소개 발송(명)", "TIPS", "샘플 메모칸")] == screen
    by = dict(zip(head, row))
    # 숫자로만 된 글자(`2020`)는 파일에서 수가 된다(`spreadsheet.write_xlsx`).
    assert (by["특이사항 (장점)"], str(by["설립년도"]), by["지역"], by["정책자금"]) == (
        "샘플 장점", "2020", "샘플시", "샘플 보증 1억")
    assert head.index("샘플 메모칸") == head.index("정책자금") + 1
