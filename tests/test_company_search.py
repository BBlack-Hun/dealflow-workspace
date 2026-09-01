"""IR 기업 현황 · 스타트업DB 의 검색 — 기업명 말고 대표자·연락처·이메일로도 찾기.

표에는 대표자·연락처·이메일이 버젓이 보이는데 검색은 기업명·분야만 보고 있었다.
눈앞의 번호를 그대로 쳐도 아무 줄이 안 걸리니, 사람에게는 "검색이 고장났다" 로
보인다 — 무엇으로 찾을 수 있는지는 아무 데도 안 적혀 있으니 원인도 알 수 없다.

여기서 막는 것은 세 가지다.

  1. 줄에 실리는 검색 글자(`search_text`)에 그 칸들이 들어가는가
  2. 전화번호를 **어떤 모양으로 쳐도** 닿는가 — 원본에 `010-0000-5678` ·
     `01000001234` · `010 0000 4321` 이 섞여 있다. 줄에는 적은 그대로와 숫자만
     남긴 꼴을 함께 싣고, 친 글자 쪽을 숫자만 남기는 일은 companies.js 가 한다.
     양쪽이 다 있어야 어느 모양으로 쳐도 만난다.
  3. **탭이 둘인데 한쪽만 걸리는 일이 없는가.** 두 탭은 같은 레코드의 두 가지
     보기라 검색 글자도 한 곳에서 나와야 한다 — 두 벌로 두면 반드시 어긋나고,
     어긋난 쪽 탭에서는 조용히 안 걸린다.

브라우저 쪽 판단(친 글자를 숫자만 남기는 것 · 컬럼 필터와 AND)은 node 로
돌린다 — 맨 아래 래퍼가 그것이다.

이름·회사·번호·이메일은 전부 지어낸 값이다 — 저장소가 공개다.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "app" / "templates" / "companies.html"

# 지어낸 기업 하나. 번호는 **하이픈이 든 모양**으로 둔다 — 숫자만 남긴 꼴이
# 따로 실리는지 보려면 원본이 숫자만은 아니어야 한다.
NAME = "가나테크"
CONTACT = "김가나"
EMAIL = "ganatech@example.com"
PHONE = "010-0000-5678"
DIGITS = "01000005678"


@pytest.fixture()
def company(db):
    from app.models import IrCompany

    row = IrCompany(name=NAME, sector_major="AI", contract_status="none",
                    contact_name=CONTACT, contact_email=EMAIL, contact_phone=PHONE,
                    one_liner="농산물 선도거래")
    db.add(row)
    db.commit()
    return row


def _rows(html: str) -> dict:
    """표에 그려진 줄 → 그 줄이 들고 있는 검색 글자."""
    return {int(rid): text
            for rid, text in re.findall(r'<tr data-id="(\d+)" data-search="([^"]*)"', html)}


# ── ① 줄에 무엇이 실리는가 ──────────────────────────────────────────────────

def test_the_row_carries_the_contact_columns(db, company):
    """표에 보이는 칸으로는 찾아져야 한다."""
    from app.routers.companies import search_text

    text = search_text(company)
    for wanted in (NAME, CONTACT, EMAIL, PHONE):
        assert wanted.lower() in text, f"{wanted} 로는 검색이 안 된다"
    # 예전부터 되던 것도 그대로 남아 있어야 한다.
    assert "ai" in text and "농산물" in text, "분야·한줄 소개로 못 찾게 됐다"


def test_the_phone_is_carried_twice_so_any_shape_finds_it(db, company):
    """`01012345678` 로 쳤을 때 하이픈이 든 줄이 안 걸리면 사람은 없는 줄 안다.

    이 검사가 없으면 `search_text` 에서 숫자만 남긴 꼴을 빼도 아무 데서도 안
    터진다 — 화면에서 번호를 쳐 봐야 알게 된다.
    """
    from app.routers.companies import search_text

    text = search_text(company)
    assert PHONE.lower() in text, "적은 그대로가 없어 하이픈째 친 사람이 못 찾는다"
    assert DIGITS in text, "숫자만 남긴 꼴이 없어 숫자만 친 사람이 못 찾는다"
    # 뒷자리 네 개로 찾는 것이 실제로 가장 흔하다.
    assert DIGITS[-4:] in text


def test_a_plain_number_is_not_carried_twice(db):
    """이미 숫자뿐인 번호까지 두 번 실으면 줄만 길어진다(걸리는 것은 똑같다)."""
    from app.models import IrCompany
    from app.routers.companies import search_text

    plain = IrCompany(name="다라바이오", contact_phone="01000001234")
    db.add(plain)
    db.commit()

    assert search_text(plain).split().count("01000001234") == 1


def test_a_company_without_a_contact_still_has_a_search_text(db):
    """연락처가 비어 있어도 기업명으로는 찾아져야 한다 — 대부분의 줄이 그렇다."""
    from app.models import IrCompany
    from app.routers.companies import search_text

    bare = IrCompany(name="마바에너지")
    db.add(bare)
    db.commit()

    assert search_text(bare) == "마바에너지"


# ── ② 탭이 둘이다 ───────────────────────────────────────────────────────────

def test_both_tabs_search_on_the_same_thing(logged_in, company):
    """한쪽 탭만 고치면 다른 탭에서 **조용히** 안 걸린다.

    두 탭(IR 기업 현황 · 스타트업DB)은 같은 레코드의 두 가지 보기다. 검색 글자를
    탭마다 따로 만들면 반드시 어긋나는데, 어긋난 쪽은 아무 오류도 안 내고 그냥
    안 찾아진다 — 쓰는 사람은 그 탭에서만 검색이 안 된다는 것을 한참 뒤에 안다.
    """
    status = _rows(logged_in.get("/companies").text)
    startup = _rows(logged_in.get("/companies?tab=db").text)

    assert status and startup, "두 탭 중 한쪽에 줄이 안 그려졌다"
    assert status.keys() == startup.keys(), "탭마다 그려지는 기업이 다르다"
    assert status == startup, "탭마다 검색 글자가 다르다 — 한쪽에서만 걸린다"

    for tab, rows in (("IR 기업 현황", status), ("스타트업DB", startup)):
        text = rows[company.id]
        for wanted in (NAME.lower(), CONTACT, EMAIL, PHONE, DIGITS):
            assert wanted in text, f"{tab} 탭에서 {wanted} 로 검색이 안 된다"


# ── ③ 무엇으로 찾을 수 있는지 화면이 말해 주는가 ────────────────────────────

def test_the_search_box_says_what_it_searches():
    """자리표시 글자가 실제와 다르면, 되는 것도 안 되는 줄 알고 안 쳐 본다."""
    html = TEMPLATE.read_text(encoding="utf-8")
    box = re.search(r'<input type="search" id="co-search"(.*?)>', html, re.S)
    assert box, "검색칸을 못 찾았다"
    attrs = box.group(1)

    placeholder = re.search(r'placeholder="([^"]*)"', attrs)
    assert placeholder, "자리표시 글자가 없다"
    for word in ("기업명", "대표자", "연락처", "이메일"):
        assert word in placeholder.group(1), f"검색되는데 자리표시에 {word} 가 없다"

    # 자리표시에 다 못 적는 것(번호 모양·분야·소개)은 `title` 이 받는다.
    title = re.search(r'title="([^"]*)"', attrs)
    assert title and "뒷자리" in title.group(1), (
        "번호를 어떻게 쳐도 되는지 어디에도 안 적혀 있다")


# ── ④ 브라우저 쪽 판단 ──────────────────────────────────────────────────────

@pytest.mark.skipif(shutil.which("node") is None,
                    reason="node 미설치 — 브라우저 로직 테스트 생략")
def test_typing_a_phone_in_any_shape_finds_the_row():
    """친 글자를 숫자만 남겨 견주는가 · 컬럼 필터와 AND 로 묶이는가.

    판단이 브라우저에 있으므로 검사도 같은 언어로 둔다(tests/test_filters_js.py
    와 같은 방식). 파이썬으로 다시 구현하면 두 벌이 되고, 어긋나도 모른다.
    """
    script = ROOT / "tests" / "js" / "company_contact_search_test.js"
    out = subprocess.run([shutil.which("node"), str(script)],
                         capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stdout + out.stderr
