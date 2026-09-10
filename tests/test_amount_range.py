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

# 옛 정수(백만원)가 어떤 글자로 옮겨지는가(0074).
#
# **위쪽 표는 화면 글자가 한 글자도 안 바뀌는 값들**이다 — 억으로 적어도 잃는
# 것이 없어서 옛 화면 글자(`format_eok(560)` = `"5.6"`)가 그대로 선다.
# 운영 자료 262칸 중 252칸이 이쪽이다.
LEGACY_SAME = [(0, "0"), (50, "0.5"), (100, "1"), (560, "5.6"),
               (1000, "10"), (3090, "30.9"), (15000, "150"), (21000, "210")]

# **아래쪽은 억으로 적으면 값을 잃는 값들.** 운영 자료에서 실제로 그랬던 10칸의
# 모양을 그대로 넣었다(숫자만 옮겼다 — 어느 기업 줄인지는 여기 없다).
#
# 짝은 `(백만원, 옮긴 글자, 예전에 화면에 뜨던 글자)` 다. 셋째 칸이 있는 것은
# **무엇이 달라지는지 눈으로 세기 위해서**다: 전부 반올림값 → 정확한 값이고,
# `1 → "0"` 은 `0`(= 없음)이라는 거짓말이 사라지는 자리다.
LEGACY_LOSSY = [
    (1, "100만원", "0"),        # ← 값이 통째로 사라지던 자리
    (6, "600만원", "0.1"),
    (13, "1300만원", "0.1"),
    (34, "3400만원", "0.3"),
    (47, "4700만원", "0.5"),
    (55, "5500만원", "0.6"),
    (68, "6800만원", "0.7"),
    (194, "1.94", "1.9"),
    (225, "2.25", "2.2"),
    (318, "3.18", "3.2"),
]

LEGACY = [(number, written) for number, written, _shown in LEGACY_LOSSY] + LEGACY_SAME


# ── ① 적은 그대로 ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("written, phrase, million", [
    # 억 — 이 칸의 기본 단위. 단위를 안 적으면 억이다.
    ("18.3", "18.3억", 1830),
    ("18.3억", "18.3억", 1830),
    ("약 5억", "5억", 500),
    ("1,200", "1200억", 120000),
    ("0", "0억", 0),
    # 1억 미만 — 사용자가 요청한 표기. **적은 단위가 그대로 남는다.**
    ("5천만원", "5천만원", 50),
    # `천만` 과 `천만원` 은 같은 단위다 — 문구에는 한 모양으로 선다
    #   (`누적투자금액 5천만` 은 말이 안 된다).
    ("5천만", "5천만원", 50),
    ("2억원", "2억", 200),
    ("4700만원", "4700만원", 47),
    ("5,000만원", "5000만원", 50),
    ("100만원", "100만원", 1),
    ("약 3천만원", "3천만원", 30),
    # 구간 — 양쪽 단위가 같으면 단위를 한 번만 적는다.
    ("5-10억 사이", "5~10억", 500),
    ("5~10억", "5~10억", 500),
    ("5억~10억", "5~10억", 500),
    ("5-10", "5~10억", 500),
    ("10-5", "5~10억", 500),          # 거꾸로 적어도 작은 쪽이 아래다
    ("3천만원~9천만원", "3~9천만원", 30),
    # 단위가 섞인 구간 — 각자의 단위가 그대로 남는다.
    ("3천만원~1억", "3천만원~1억", 30),
    ("1억~3억", "1~3억", 100),
])
def test_what_a_person_writes_keeps_its_meaning(written, phrase, million):
    assert amount.phrase(written) == phrase
    assert amount.million(written) == million


@pytest.mark.parametrize("written", [
    # `5천` — `5천만원` 인지 `5천원` 인지 글자만으로 못 가른다. 짐작해 읽으면
    # 그 짐작이 그대로 투자사에게 나간다.
    "5천",
    # `백만원` 은 옛 저장 단위다. 여기서 다시 받으면 "이 칸은 백만원이었지" 하는
    # 기억과 섞인다 — 시트에서 오는 값은 가져오기가 억으로 옮겨 담는다.
    "1,224백만원",
    "5백만원",
    # 한쪽만 열린 구간. 문구 자리에 넣을 모양이 없다.
    "10억 이상",
    "1억 미만",
    # 그냥 말
    "투자 유치 협의중",
    "5천만원쯤 될 듯",
])
def test_what_is_deliberately_not_accepted(written):
    """**받는 것과 안 받는 것을 여기 못 박는다.**

    안 받는 값도 저장은 된다 — 사람이 적은 것을 지우지 않는다. 다만 숫자로 읽지
    않고, 문구에서 빠지고, 표에 `⚠ 문구에서 빠짐` 딱지가 붙는다.
    """
    assert amount.state(written) == amount.UNREADABLE, written
    assert amount.phrase(written) is None
    assert amount.million(written) is None


def test_a_bare_number_is_always_eok():
    """단위를 안 적으면 **언제나 억**이다 — 규칙이 둘이 되면 안 된다.

    맨숫자를 원으로도 읽기 시작하면 `18.3` 과 `50000000` 이 같은 칸 안에서 서로
    다른 단위가 된다. 이 칸은 예전부터 억이었고(입력창이 억이었다) 그대로 둔다.
    """
    assert amount.million("0.5") == 50
    assert amount.million("5") == 500


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


# ── ③ 옛 정수 값을 한 줄도 잃지 않는다 ──────────────────────────────────────

def test_no_old_row_is_ever_lost():
    """**옛 정수 → 글자 → 다시 정수가 원래 값이어야 한다.** 0~300억 전 구간.

    처음에는 옛 화면 계산 그대로(소수 한 자리) 옮겼다. 화면 글자는 한 글자도 안
    바뀌지만 **저장값이 조금 달라진다** — 운영 자료 262칸 중 10칸이 그랬고,
    `raise_target 1(백만원)` 은 `"0"`(= 없음)이 되어 **값이 통째로 사라졌다.**

    반올림이 아니라 다른 사실로 바뀌는 것이라, 화면 글자를 지키자고 값을 잃을
    수는 없다. 이 검사가 그 자리를 잠근다.

    **한 검사 안에서 훑는다.** 값마다 검사를 세우면 시험 목록 3만 줄이 이것
    하나로 덮여, 정작 무엇이 깨졌는지 안 보인다. 대신 어긋난 값을 세어 보여준다.
    """
    lost = [(baekman, amount.from_million(baekman))
            for baekman in range(0, 30001)
            if amount.million(amount.from_million(baekman)) != baekman]
    assert not lost, f"{len(lost)}개가 되읽으면 달라집니다 (앞 5개: {lost[:5]})"


@pytest.mark.parametrize("baekman, written", LEGACY_SAME)
def test_rows_that_lose_nothing_keep_the_screen_letters(baekman, written):
    """잃을 것이 없으면 **옛 화면 글자 그대로**다.

    `format_eok` · `companies.eok` · `data_io._eok` 셋 다 백만원을 100 으로 나눠
    소수 한 자리에서 끊고 있었다. 그 계산이 값을 안 잃는 줄에서는 그대로 쓰인다 —
    운영 자료 262칸 중 252칸이 이쪽이라, 표를 열어도 달라진 데가 없다.
    """
    assert amount.from_million(baekman) == written


@pytest.mark.parametrize("baekman, written, used_to_show", LEGACY_LOSSY)
def test_rows_that_would_lose_get_a_notation_that_does_not(baekman, written,
                                                            used_to_show):
    """잃는 줄만 표기가 바뀐다 — **그리고 그 10칸이 전부다.**

    1억 미만은 만원으로(`47 → "4700만원"`). `0.47억` 이라고 적어 두면 사람이 매번
    억을 만원으로 되돌려 읽어야 하고, 문구에 `누적투자금액 0.47억` 이 나간다 —
    투자사가 쓰는 말이 아니다. 1억 이상은 억을 끊지 않는다(`318 → "3.18"`) —
    억 단위에서 소수 둘째 자리는 그대로 읽히고 `31800만원` 이 오히려 어렵다.
    """
    assert amount.from_million(baekman) == written
    assert amount.million(written) == baekman
    # 바뀌기 **전에** 화면에 뜨던 글자. 값이 커지거나 작아지는 칸은 없다.
    assert written != used_to_show
    assert amount.million(used_to_show) != baekman, \
        "이 줄은 잃지 않는다 — LEGACY_SAME 으로 옮기세요"


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


def test_the_migration_moves_old_rows_without_losing_a_single_one(tmp_path):
    """진짜로 판을 오르내려 본다.

    빈 DB 는 `0001_initial` 이 **지금 모델**로 만들어 이미 글자 칸이다. 그래서
    옛 DB 를 흉내 내려면 먼저 **0074 를 되돌려** 칸을 정수로 만든다 — 이 한
    번으로 되돌리기까지 함께 확인된다.
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
        for index, (baekman, _written) in enumerate(LEGACY):
            _insert_legacy(con, index, baekman)
        con.commit()
    finally:
        con.close()

    alembic("upgrade", "head")

    con = sqlite3.connect(db)
    try:
        got = dict(con.execute(
            "SELECT id, funding_total FROM ir_companies WHERE id >= 900").fetchall())
        for index, (_baekman, written) in enumerate(LEGACY):
            assert got[900 + index] == written, index

        # 사람이 새로 적은 구간을 한 줄 섞어 두고 되돌려 본다.
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
        # **이 판이 옮긴 줄은 한 줄도 안 잃고 원래 정수로 돌아온다.**
        for index, (baekman, _written) in list(enumerate(LEGACY))[1:]:
            assert got[900 + index] == baekman, index
    finally:
        con.close()


def test_the_excel_still_holds_a_number_for_old_values(logged_in, db):
    """엑셀에서 계산할 수 있게 **숫자로** 둔다 — 옛 값은 예전과 같은 숫자다.

    `5천만원` 처럼 억이 아닌 단위로 적힌 값도 **억으로 옮겨** 숫자로 나간다.
    머리글이 `(억)` 이라, 그 열에만 만원이 섞이면 합계를 내는 사람이 100배를
    헛짚는다.
    """
    from app.models import IrCompany

    db.add(IrCompany(name="샘플옛값", revenue_recent="18.3", pre_value="150",
                     funding_total="4700만원"))
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
    assert row[col["누적투자(억)"]] == 0.47


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

    for written in ("5-10억 사이", "5천만원"):
        number = amount.million(written)       # 구간이면 아래
        assert message_composer.format_eok(written) == amount.phrase(written)
        assert llm_brief.amount_band(written) == llm_brief.amount_band(number)

    assert one_liner._eok_segment("5-10억 사이", "누적투자금액 {}") == "누적투자금액 5~10억"
    assert one_liner._eok_segment("5천만원", "누적투자금액 {}") == "누적투자금액 5천만원"


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
    ("8.2억", "8.2억"),
    ("150억 ~ 200억", "150~200억"),   # 구간이 **구간인 채로** 들어온다
    ("2억원~5억", "2~5억"),
    ("3천만원", "3천만원"),            # 억 미만은 만원인 채로 남는다
    ("1,224백만원", "12.24"),         # 앱이 안 받는 단위 → 예전 길로 읽어 억으로
    # 앱 문법 밖이라 예전 길로 간다 — 작은 쪽을 억으로 옮겨 담는다.
    ("10억 이상", "10"),
    ("미정", None),
    ("2020", None),                   # 단위 없는 맨숫자는 연도일 수 있다
])
def test_the_sheet_import_goes_through_the_same_rule(cell, stored):
    from app.services.sheet_import import _company_amount

    assert _company_amount(cell) == stored
