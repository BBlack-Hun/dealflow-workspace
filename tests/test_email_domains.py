"""메일 칸의 **도메인 후보** — 무엇을 세고, 어디를 자르고, 어디서 모으나.

화면 쪽 동작(치면 뜨는가 · 고르면 `@` 앞이 그대로인가 · 고르기 전에 저장되지
않는가)은 `tests/js/email_domain_hint_test.js` 가 본다. 여기서는 서버 쪽
셋을 잰다.

  1. 무엇을 후보로 세고 무엇을 버리나(`services/email_domains.py`).
  2. 자르는 선이 **두 번 이상**인가 — 한 번만 쓰인 도메인이 새 나가면
     목록이 수백 줄이 되고, 뜨는 후보가 전부 남의 도메인이 된다.
  3. 두 화면이 그 목록을 **같은 이름의 칸 하나**로 싣고, 네 자리(화면 둘 ×
     수정창·표)가 모두 그 하나를 보는가.

값은 전부 가상값이다 — 저장소가 공개다.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from app.services import contact_columns
from app.services.email_domains import MIN_COUNT, domain_of, domain_options

ROOT = Path(__file__).resolve().parent.parent
COMPANIES = (ROOT / "app" / "templates" / "companies.html").read_text(encoding="utf-8")
CONTACTS = (ROOT / "app" / "templates" / "contacts.html").read_text(encoding="utf-8")
JS_DIR = ROOT / "app" / "static" / "js"

CARRIER = "opts-email-domain"


# ── 1. 무엇을 후보로 세나 ───────────────────────────────────────────────

def test_두_번_이상_쓰인_도메인만_후보가_된다():
    """한 번만 쓰인 도메인은 **그 줄 하나의 도메인**이다.

    재 보니 IR 기업 대표 메일은 주소 247개에 도메인 190가지였다. 다 띄우면
    고를 수가 없고, 뜨는 후보가 전부 남의 회사 도메인이다 — 눌리면 그 줄에
    엉뚱한 도메인이 조용히 들어앉는다. 아껴 주는 타자는 없고 잃을 것만 있다.
    """
    rows = [
        "a@example.com", "b@example.com", "c@example.com",
        "d@example.net", "e@example.net",
        "f@only-once.example",            # 한 번뿐 — 후보가 되면 안 된다
    ]
    assert domain_options(rows) == ["example.com", "example.net"]
    assert MIN_COUNT == 2


def test_많이_쓰인_것부터_선다():
    """`@` 만 치고 멈춘 손이 첫 줄에서 끝나야 한다 — 훑게 하면 치는 편이 빠르다."""
    rows = ["a@second.example", "b@second.example",
            "c@first.example", "d@first.example", "e@first.example"]
    assert domain_options(rows) == ["first.example", "second.example"]


def test_같은_수면_글자_차례다():
    """차례가 실행할 때마다 달라지면 손이 기억한 자리가 매번 어긋난다."""
    rows = ["a@b.example", "b@b.example", "c@a.example", "d@a.example"]
    assert domain_options(rows) == ["a.example", "b.example"]


def test_한_칸에_주소가_여럿이어도_따로_센다():
    """시트에서 옮겨 온 칸에는 주소가 둘 적힌 줄이 있다.

    통째로 보면 마지막 하나만 세어져서, 실제로 두 번 쓰인 도메인이 한 번으로
    밀려 후보에서 조용히 빠진다.
    """
    rows = ["a@example.com / b@example.net", "c@example.net", "d@example.com"]
    assert domain_options(rows) == ["example.com", "example.net"]


def test_도메인_같지_않은_값은_버린다():
    """후보는 **눌리면 그대로 저장되는 값**이라 확신할 수 있는 것만 센다."""
    assert domain_of("hong@example.com") == "example.com"
    assert domain_of("  HONG@Example.COM  ") == "example.com"     # 다듬고 낮춘다
    assert domain_of("hong@example.com.") == "example.com"        # 끝의 점
    assert domain_of("hong@") == ""                               # 치다 만 값
    assert domain_of("hong@사내메일") == ""                        # 한글 메모
    assert domain_of("hong@nodot") == ""                          # 점이 없다
    assert domain_of("전화로만") == ""
    assert domain_of("") == ""
    assert domain_of(None) == ""


def test_메일이_하나도_없으면_빈_목록이다():
    """화면은 그때 후보를 아예 안 띄우고 보통 글자 칸으로 둔다."""
    assert domain_options([]) == []
    assert domain_options(["", None, "전화로만 연락"]) == []


# ── 2. 두 화면이 같은 하나를 본다 ───────────────────────────────────────

def test_도메인을_싣는_칸이_화면마다_하나씩이다():
    """두 벌이 되는 날 같은 화면 안에서 후보가 갈린다."""
    for name, html in (("companies.html", COMPANIES), ("contacts.html", CONTACTS)):
        assert html.count(f'id="{CARRIER}"') == 1, f"{name} 에 후보 칸이 하나가 아니다"
        assert f"data-domains='{{{{ email_domains|tojson }}}}'" in html, name


def test_도메인_목록을_읽는_자리가_한_곳이다():
    """화면 코드 중 그 칸을 읽는 파일은 공통 부품 하나여야 한다.

    표에서 고치는 길이 제 나름대로 목록을 모으기 시작하면, 수정창과 표가 서로
    다른 후보를 띄운다 — 사람이 어느 쪽으로 들어왔느냐에 따라 화면이 달라진다.
    """
    readers = sorted(p.name for p in JS_DIR.glob("*.js")
                     if CARRIER in p.read_text(encoding="utf-8"))
    assert readers == ["email_hint.js"]


def test_후보_부품이_inline_edit_보다_먼저_실린다():
    """표 칸이 그 부품을 쓴다 — 늦게 실리면 표 쪽만 조용히 후보가 안 뜬다."""
    for name, html in (("companies.html", COMPANIES), ("contacts.html", CONTACTS)):
        hint = html.index("js/email_hint.js")
        inline = html.index("js/inline_edit.js")
        assert hint < inline, f"{name} 에서 후보 부품이 늦게 실린다"


def test_네_자리가_모두_후보를_받는다():
    """화면 둘 × (수정창 · 표에서 눌러 고치기). **한쪽만 되면 안 된다.**"""
    # ① IR 기업 현황(스타트업DB) — 표 / 수정창
    assert re.search(r'data-field="contact_email" data-type="email"', COMPANIES)
    assert re.search(r'id="f-contact_email" data-email-hint', COMPANIES)

    # ② 투자사 관리 현황 — 표 / 수정창
    assert re.search(r'data-field="email" data-type="email"', CONTACTS)
    assert re.search(r'id="f-email" data-email-hint', CONTACTS)

    # ③ 스타트업 — 표도 수정창도 **배치가 정한다**(`contact_columns`).
    #    화면에 칸 이름을 적어 두면 배치가 하나 늘 때 또 적어야 한다.
    assert '{% if c.kind == \'email\' %}data-email-hint{% endif %}' in CONTACTS


def test_배치가_메일_칸을_메일_칸으로_안다():
    """`kind="email"` 이 빠지면 그 명단만 조용히 후보 없는 칸이 된다."""
    startup = contact_columns.STARTUP_LAYOUT
    email = [c for c in startup.head + startup.tail + startup.extra if c.key == "email"]
    assert email and email[0].kind == "email", "스타트업 배치의 메일 칸이 글자 칸이다"

    monthly = contact_columns.INVESTOR_MONTHLY_LAYOUT
    email = [c for c in monthly.head + monthly.tail + monthly.extra if c.key == "email"]
    assert email and email[0].kind == "email", "투자사 월별 배치의 메일 칸이 글자 칸이다"


def test_메일_칸에는_머리글_필터가_안_붙는다():
    """후보를 띄우는 칸이 되었다고 필터까지 붙으면 줄 수만큼 항목이 생긴다.

    `filterable` 은 `pick` 만 본다 — 그 판정이 `kind` 를 넓게 보기 시작하면
    자유롭게 적는 칸에 고를 것 없는 필터가 달린다.
    """
    startup = contact_columns.STARTUP_LAYOUT
    email = [c for c in startup.head if c.key == "email"][0]
    assert email.filterable is False


# ── 3. 실제로 그려지는가 ────────────────────────────────────────────────

def _domains_in(html: str) -> list:
    found = re.search(r"id=\"opts-email-domain\"[^>]*data-domains='([^']*)'", html)
    assert found, "후보 칸이 안 그려졌다"
    # Jinja 의 `tojson` 은 `'`·`<`·`>`·`&` 를 `\u0027` 꼴로 escape 한다 —
    # 작은따옴표 속성 안에 그대로 실어도 안전하고, JSON 으로는 그대로 읽힌다.
    return json.loads(found.group(1))


def test_기업_화면이_지금_그리는_줄에서_후보를_뽑는다(logged_in, db):
    """재료가 `rows` 라 **표에 보이는 것과 후보가 갈릴 자리가 없다.**"""
    from app.models import IrCompany

    db.add_all([
        IrCompany(name="가나테크", contact_email="a@example.com"),
        IrCompany(name="다라랩", contact_email="b@example.com"),
        IrCompany(name="마바에이아이", contact_email="c@only-once.example"),
    ])
    db.commit()

    html = logged_in.get("/companies?tab=db").text
    assert _domains_in(html) == ["example.com"]


def test_투자사_화면도_같은_함수를_지난다(logged_in, db, users):
    from app.models import VcContact

    db.add_all([
        VcContact(user_id=users["u1"].id, name="김가나", email="a@example.net"),
        VcContact(user_id=users["u1"].id, name="이다라", email="b@example.net"),
        VcContact(user_id=users["u1"].id, name="박마바", email="c@only-once.example"),
    ])
    db.commit()

    html = logged_in.get("/contacts").text
    assert _domains_in(html) == ["example.net"]


def test_메일이_하나도_없어도_화면이_안_깨진다(logged_in, db):
    """빈 목록이면 그 칸은 그냥 보통 글자 칸이다 — 화면이 뜨기는 해야 한다."""
    for path in ("/companies?tab=db", "/contacts", "/startup"):
        res = logged_in.get(path)
        assert res.status_code == 200, path
        assert _domains_in(res.text) == []
