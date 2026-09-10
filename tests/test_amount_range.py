"""금액을 **구간·`~` 로도 적을 수 있다** — 그리고 숫자로 쓰는 곳이 다 살아 있다.

사용자 요청은 한 줄이었다: "누적 투자금액에 `~` 이나 `5-10억 사이` 이러한 표현을
입력해야 하는데 지금은 숫자만 입력 가능함". 그 한 줄을 지키면서 **깨뜨리면 안 되는
것이 여섯**이라, 여기서 한 자리에 모아 잠근다.

  1. 적은 그대로 저장되고 화면·문구에 뜻이 남는다
  2. `~`(모름)과 `0`(없음)이 다르게 다뤄진다
  3. 옛 정수 값이 전과 똑같이 보인다 (문구 · 화면 · 엑셀)
  4. 숫자를 뽑는 규칙이 **한 곳**이다
  5. LLM 자료의 구간화가 계속 돌고 정확한 수치가 안 나간다
  6. 못 읽는 값이 문구에 그대로 실려 나가지 않는다

`services/amount.py` 그 자체를 보는 검사와, 그것을 읽는 여섯 자리를 보는 검사가
섞여 있다. 섞어 둔 것은 일부러다 — 규칙을 고치는 사람이 **누가 그 규칙을 읽는지**
를 같은 파일에서 보게 된다.
"""
from __future__ import annotations

import io
import sqlite3
import subprocess
import sys
from pathlib import Path

import openpyxl
import pytest

from app.services import amount

ROOT = Path(__file__).resolve().parent.parent

# 옛 자료가 어떤 글자로 옮겨지는가(0074). **여기 적힌 오른쪽이 곧 예전에 화면에
# 뜨던 글자**다 — `format_eok(560)` 이 `"5.6"` 이었다.
LEGACY = [(560, "5.6"), (3090, "30.9"), (1000, "10"), (21000, "210"),
          (0, "0"), (1224, "12.2"), (15000, "150")]


# ── ① 적은 그대로 ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("written, quantity, million", [
    ("5-10억 사이", "5~10", 500),
    ("5~10억", "5~10", 500),
    ("5억~10억", "5~10", 500),
    ("5-10", "5~10", 500),
    ("10-5", "5~10", 500),          # 거꾸로 적어도 작은 쪽이 아래다
    ("18.3", "18.3", 1830),
    ("18.3억", "18.3", 1830),
    ("약 5억", "5", 500),
    ("1,200", "1200", 120000),
    ("0", "0", 0),
])
def test_what_a_person_writes_keeps_its_meaning(written, quantity, million):
    assert amount.quantity(written) == quantity
    assert amount.million(written) == million


def test_a_range_reaches_the_deal_message(logged_in, db):
    """요청의 핵심 — `5-10억 사이` 가 딜소개 문구까지 **구간인 채로** 간다."""
    from app.models import IrCompany
    from app.services.message_composer import CompanyView, auto_company_summary

    row = IrCompany(name="샘플구간", sector_major="애그테크", one_liner="선도거래",
                    funding_total="5-10억 사이")
    db.add(row)
    db.commit()

    # 저장은 적은 그대로
    assert row.funding_total == "5-10억 사이"
    # 표도 적은 그대로 — 무엇을 고쳐야 문구가 바뀌는지 보여야 한다
    assert "5-10억 사이" in logged_in.get("/companies?tab=db").text
    # 문구에는 한 모양으로 선다
    said = auto_company_summary(CompanyView(
        name=row.name, sector_major=row.sector_major, one_liner=row.one_liner,
        funding_total=row.funding_total))
    assert "누적투자금액 5~10억" in said


def test_a_range_makes_a_company_introducible(db):
    """구간을 적었으면 **소개 대상이 된다.**

    예전에는 숫자가 하나도 없으면 소개 목록에서 빠졌다. 구간을 못 세면 정확한
    금액을 모르는 기업은 영영 소개가 안 된다 — 요청이 막혀 있던 자리다.
    """
    from app.models import IrCompany

    row = IrCompany(name="샘플구간", sector_major="애그테크",
                    funding_total="5-10억 사이", summary_status="draft")
    db.add(row)
    db.commit()
    assert row.introducible is True


# ── ② `~`(모름)과 `0`(없음) ──────────────────────────────────────────────────

def test_unknown_and_zero_are_different_facts(db):
    """`0` 은 아는 사실이고 `~` 는 모른다는 표시다.

    뭉개면 "아직 투자를 못 받았다" 가 "모른다" 로 바뀌어 사라진다 — 투자사에게
    보이는 뜻이 서로 다르다.
    """
    from app.models import IrCompany
    from app.services.llm_brief import ZERO_BAND, amount_band
    from app.services.message_composer import CompanyView, auto_company_summary

    def said(value):
        return auto_company_summary(CompanyView(
            name="x", sector_major="AI", funding_total=value))

    # 문구: 0 은 나가고, ~ 는 안 나간다
    assert "누적투자금액 0억" in said("0")
    assert "누적투자금액" not in said("~")

    # LLM 자료: 0 은 `0` 표로 실리고, ~ 는 아예 안 실린다(= 빈 칸과 같다)
    assert amount_band("0") == ZERO_BAND
    assert amount_band("~") is None
    assert amount_band("") is None

    # 소개 가능 판정: **둘 다 안 센다.** 0 을 안 세는 것은 예전 그대로다.
    for value in ("0", "~"):
        row = IrCompany(name=f"샘플{value}", sector_major="AI",
                        funding_total=value, summary_status="draft")
        db.add(row)
        db.commit()
        assert row.introducible is False, value
        assert amount.is_countable(value) is False, value


def test_unknown_is_still_visible_on_the_screen(logged_in, db):
    """`~` 는 빈 칸과 **눈으로 구별된다** — 하나는 '아직 안 봤다', 하나는 '모른다'."""
    from app.models import IrCompany

    db.add(IrCompany(name="샘플모름", funding_total="~"))
    db.commit()
    assert ">~<" in logged_in.get("/companies?tab=db").text


# ── ③ 옛 정수 값이 전과 똑같이 보인다 ────────────────────────────────────────

@pytest.mark.parametrize("baekman, shown", LEGACY)
def test_old_integers_become_exactly_what_the_screen_used_to_show(baekman, shown):
    """옮기는 규칙이 **예전 화면 계산과 같은 것**이어야 한다.

    `format_eok` · `companies.eok` · `data_io._eok` 셋 다 백만원을 100 으로
    나눠 소수 한 자리에서 끊고 있었다. `from_million` 이 그 계산 그대로다.
    """
    assert amount.from_million(baekman) == shown


def _insert_legacy(con, index: int, baekman: int) -> None:
    """옛 DB 에 있던 줄 하나. **NOT NULL 칸은 스키마를 보고 채운다** —

    여기 칸 이름을 손으로 적어 두면 표에 NOT NULL 칸이 하나 늘 때마다 이 검사가
    엉뚱한 자리에서 깨진다.
    """
    filled = {"id": 900 + index, "name": f"옛기업{index}", "funding_total": baekman}
    for _cid, name, kind, notnull, default, _pk in con.execute(
            'PRAGMA table_info("ir_companies")'):
        if name in filled or not notnull or default is not None:
            continue
        filled[name] = 0 if kind.upper().startswith("INT") else ""
    con.execute(
        "INSERT INTO ir_companies ({}) VALUES ({})".format(
            ", ".join(filled), ", ".join("?" * len(filled))),
        tuple(filled.values()))


def test_the_migration_moves_old_rows_without_changing_what_is_shown(tmp_path):
    """진짜로 판을 오르내려 본다.

    빈 DB 는 `0001_initial` 이 **지금 모델**로 만들어 이미 글자 칸이다. 그래서
    옛 DB 를 흉내 내려면 먼저 **0074 를 되돌려** 칸을 정수로 만든다 — 이 한
    번으로 되돌리기까지 함께 확인된다.

    옮긴 뒤의 글자가 **화면에 뜨던 글자와 같아야** 한다(`LEGACY` 의 오른쪽).
    """
    import os

    db = tmp_path / "legacy.db"
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{db}",
           "DEALFLOW_DATA_DIR": str(tmp_path)}

    def alembic(*args):
        done = subprocess.run([sys.executable, "-m", "alembic", *args],
                              cwd=ROOT, env=env, capture_output=True, text=True)
        assert done.returncode == 0, done.stdout + done.stderr

    alembic("upgrade", "head")
    alembic("downgrade", "0073_consulting_row_grant")   # 칸이 정수로 돌아간다

    con = sqlite3.connect(db)
    try:
        kinds = {r[1]: r[2] for r in con.execute('PRAGMA table_info("ir_companies")')}
        assert kinds["funding_total"].upper().startswith("INT"), \
            "되돌리기가 칸을 정수로 되돌리지 않았다"
        for index, (baekman, _shown) in enumerate(LEGACY):
            _insert_legacy(con, index, baekman)
        con.commit()
    finally:
        con.close()

    alembic("upgrade", "head")

    con = sqlite3.connect(db)
    try:
        got = dict(con.execute(
            "SELECT id, funding_total FROM ir_companies WHERE id >= 900").fetchall())
        for index, (_baekman, shown) in enumerate(LEGACY):
            assert got[900 + index] == shown, index

        # 구간을 하나 적어 두고 되돌려 본다.
        con.execute("UPDATE ir_companies SET funding_total = '5-10억 사이' WHERE id = 900")
        con.commit()
    finally:
        con.close()

    alembic("downgrade", "0073_consulting_row_grant")

    con = sqlite3.connect(db)
    try:
        got = dict(con.execute(
            "SELECT id, funding_total FROM ir_companies WHERE id >= 900").fetchall())
        assert got[900] is None, \
            "구간은 정수 칸에 담을 자리가 없다 — 하한으로 눌러 담으면 틀린 단정이 남는다"
        for index, (_baekman, shown) in list(enumerate(LEGACY))[1:]:
            # 옮겼다 되돌리면 **적혀 있던 글자가 뜻하는 정수**로 돌아온다.
            # 소수 한 자리에서 끊이며 잃은 만큼(최대 5백만원)은 돌아오지 않는다 —
            # 그 자리는 화면·문구·엑셀이 이미 끊어 보여주던 자리다.
            assert got[900 + index] == amount.million(shown), index
    finally:
        con.close()


def test_the_excel_still_holds_a_number_for_old_values(logged_in, db):
    """엑셀에서 계산할 수 있게 **숫자로** 둔다 — 옛 값은 예전과 같은 숫자다."""
    from app.models import IrCompany

    db.add(IrCompany(name="샘플옛값", revenue_recent="18.3", pre_value="150"))
    db.commit()

    book = openpyxl.load_workbook(
        io.BytesIO(logged_in.get("/api/export/companies.xlsx").content))
    sheet = book.active
    head = [c.value for c in sheet[1]]
    col = {name: i for i, name in enumerate(head)}
    row = next(r for r in sheet.iter_rows(min_row=2, values_only=True)
               if r[0] == "샘플옛값")
    assert row[col["최근매출(억)"]] == 18.3
    assert isinstance(row[col["최근매출(억)"]], (int, float))
    assert row[col["Pre Value(억)"]] == 150


# ── ④ 숫자를 뽑는 규칙이 한 곳 ───────────────────────────────────────────────

#: 금액 글자에서 숫자를 뽑아 쓰는 자리. **여섯이 각자 해석하면 문구·LLM·엑셀
#: 숫자가 갈린다** — 갈린 숫자는 겉보기에 멀쩡해서 알아채기까지 오래 걸린다.
READERS = [
    "app/services/message_composer.py",
    "app/services/one_liner.py",
    "app/models.py",
    "app/services/llm_brief.py",
    "app/routers/data_io.py",
    "app/services/matcher.py",
    "app/routers/companies.py",
    "app/deps.py",
    # 화면도 마찬가지다. 예전에는 여기서 억↔백만원을 곱하고 나눴고, 그 자리
    # 때문에 `5-10억 사이` 를 아예 넣을 수 없었다.
    "app/static/js/companies.js",
    "app/static/js/inline_edit.js",
]

#: 금액을 스스로 해석하려 드는 흔적. 예전에 **여섯 자리에 흩어져 있던 계산**이다.
FORBIDDEN = ("/ 100.0", "/ 100)", "* 100)", "value_baekman", 'unit === "eok"')


def test_only_one_place_reads_a_number_out_of_the_text():
    """읽는 쪽 어디에도 **자기만의 환산**이 없어야 한다.

    이 검사가 잠그는 것은 "누가 고쳤을 때 무엇이 갈리는가" 다. 둘로 갈리면
    깨진다 — 어느 파일이든 100 으로 곱하거나 나누기 시작하면 여기서 걸린다.
    """
    for name in READERS:
        text = (ROOT / name).read_text(encoding="utf-8")
        code = "\n".join(line for line in text.splitlines()
                         if not line.lstrip().startswith(("#", "//")))
        for mark in FORBIDDEN:
            assert mark not in code, f"{name} 이 금액을 스스로 환산하고 있습니다: {mark}"


def test_the_sheet_import_does_not_write_the_field_by_hand():
    """시트 가져오기는 `services/sheet_import.py` 만 예외다 — **자기 환산이 있다.**

    거기 있는 `parse_money_to_million` 은 이 칸을 읽는 규칙이 아니라 **시트의
    자유 서술을 읽는 규칙**이다(`1,224백만원` · `3천만`). 단위가 제각각인 칸을
    읽는 일이라 여기 있는 것이 맞다.

    지켜야 하는 것은 **그 결과가 칸에 곧장 들어가지 않는 것**이다 — 반드시
    `_company_amount` 를 지나 `services/amount.py` 의 글자가 되어야 한다.
    """
    text = (ROOT / "app/services/sheet_import.py").read_text(encoding="utf-8")
    assign = text.split("def apply_company_financials", 1)[1]
    assert "_company_amount(" in assign
    assert "parse_money_to_million(" not in assign, \
        "시트 값이 `_company_amount` 를 건너뛰고 칸에 곧장 들어갑니다"


def test_every_reader_agrees_on_the_number():
    """같은 값을 여섯 자리가 **같은 숫자로** 읽는가.

    표기를 하나 정해 두고 문구 · 한줄소개 · 구간 · 엑셀 · 매칭이 서로 어긋나지
    않는지 본다. 규칙이 두 곳으로 갈리는 날 여기가 먼저 깨진다.
    """
    from app.services import llm_brief, message_composer, one_liner

    written = "5-10억 사이"
    number = amount.million(written)          # 500 백만원 (구간이면 아래)

    assert message_composer.format_eok(written) == amount.quantity(written)
    assert one_liner._eok_segment(written, "누적투자금액 {}억") == "누적투자금액 5~10억"
    assert llm_brief.amount_band(written) == llm_brief.amount_band(number)


# ── ⑤ LLM 자료 — 구간화가 계속 돌고 정확한 수치가 안 나간다 ──────────────────
#
# `tests/test_llm_brief.py` 가 #155·#156 검사를 통째로 들고 있다. 여기서는
# **글자가 된 뒤에도** 그 길이 살아 있는지만 한 번 더 짚는다.

def test_the_written_text_never_leaves_the_server(db, users, logged_in):
    """구간으로 바꿔 내보내면서 **사람이 적은 글자를 흘리면** 뜻이 없다.

    이름을 뺀 까닭이 숫자에서 그대로 풀린다(`llm_brief.amount_band` 참고).
    적은 글자(`42.93`)든 그것이 뜻하는 백만원(`4293`)이든 나가면 안 된다.
    """
    from app.models import IrCompany

    db.add(IrCompany(name="샘플엘엘엠", sector_major="AI", one_liner="소개",
                     funding_total="42.93", raise_target="5-10억 사이"))
    db.commit()

    body = logged_in.get("/api/llm-brief.json").text
    for leaked in ("42.93", "4293", "5-10억 사이", "5~10억"):
        assert leaked not in body, f"{leaked} 이 그대로 나갔습니다"


# ── ⑥ 못 읽는 값이 문구에 실려 나가지 않는다 ─────────────────────────────────

@pytest.mark.parametrize("written", [
    "투자 유치 협의중", "10억 이상", "확인 후 알려드리겠습니다", "??!!", "~",
])
def test_what_cannot_be_read_never_reaches_an_investor(written):
    """사람이 아무 글자나 넣을 수 있게 된 이상, **못 읽는 것은 뺀다.**

    빼면 그 항목만 없는 문구가 되고, 그것은 값이 비었을 때와 똑같은 모양이라
    읽는 사람이 이상하게 보지 않는다. 그대로 실어 보내는 쪽이 훨씬 나쁘다.
    """
    from app.services.message_composer import CompanyView, auto_company_summary
    from app.services.one_liner import compose_one_liner
    from types import SimpleNamespace

    said = auto_company_summary(CompanyView(
        name="x", sector_major="AI", one_liner="소개",
        revenue_recent=written, funding_total=written,
        raise_target=written, pre_value=written))
    assert said == "[AI] | 소개", said
    assert written not in said

    made = compose_one_liner(SimpleNamespace(
        business_desc="소재 제조", revenue_2022=None, revenue_2023=None,
        revenue_2024=None, revenue_2025=None, funding_total=written,
        raise_target=written, pre_value=written, competitiveness=None,
        one_liner=None))
    assert made == "소재 제조", made


def test_the_screen_says_which_values_will_be_dropped(logged_in, db):
    """조용히 빠지면 사람은 적어 뒀는데 왜 안 나오는지 알 길이 없다.

    `~`(모름)에는 딱지를 안 붙인다 — 그것은 실수가 아니라 일부러 적은 표시라,
    문구에서 빠지는 것이 적은 사람의 뜻 그대로다.
    """
    from app.models import IrCompany

    db.add(IrCompany(name="샘플못읽음", funding_total="투자 유치 협의중"))
    db.add(IrCompany(name="샘플모름2", funding_total="~"))
    db.commit()

    html = logged_in.get("/companies?tab=db").text
    unreadable = html.split("샘플못읽음", 1)[1].split("</tr>", 1)[0]
    unknown = html.split("샘플모름2", 1)[1].split("</tr>", 1)[0]
    assert "문구에서 빠짐" in unreadable
    assert "문구에서 빠짐" not in unknown


# ── 시트에서 읽어 넣는 자리도 같은 규칙을 지난다 ─────────────────────────────

@pytest.mark.parametrize("cell, stored", [
    ("8.2억", "8.2"),
    ("150억 ~ 200억", "150~200"),     # 구간이 **구간인 채로** 들어온다
    ("2억원~5억", "2~5"),
    ("1,224백만원", "12.2"),          # 단위가 억이 아니면 예전 길로 읽는다
    ("10억 이상", "10"),              # 앱 문법 밖 → 예전 길(작은 쪽)
    ("미정", None),
    ("2020", None),                   # 단위 없는 맨숫자는 연도일 수 있다
])
def test_the_sheet_import_goes_through_the_same_rule(cell, stored):
    from app.services.sheet_import import _company_amount

    assert _company_amount(cell) == stored
