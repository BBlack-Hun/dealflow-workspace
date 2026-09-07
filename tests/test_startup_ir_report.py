"""이번 달 귀사 IR 자료를 요청한 투자사 — 문서와 그 화면.

여기서 막는 것은 여섯 가지다.

  1. **가리기** — 원래 이름이 어디에도 통째로 안 나오고, 별표 개수가 이름
     길이를 알려주지 않는다. 가리는 규칙은 **한 곳**에만 적혀 있다.
  2. 계약을 마친 기업만 문서를 받는다.
  3. 요청 기록 **두 곳**(이 앱에서 누른 것 · 시트에서 옮겨 온 것)이 합쳐진다.
  4. 못 맞춘 요청은 **세어지지 않되**, 몇 건인지는 화면에 뜬다.
  5. 달이 제대로 갈린다.
  6. 인쇄했을 때 화면 것(좌측 메뉴·단추)이 종이에 안 나간다.

이름·회사명은 **전부 지어낸 값**이다 — 저장소가 공개다. 가리는 일을 하면서
검사에 진짜 이름을 넣으면 앞뒤가 안 맞는다.

**날짜를 박지 않는다.** 달은 `clock` 에서 만든다 — 박아 두면 검사가 도는 달이
바뀔 때 저절로 깨진다.
"""
from __future__ import annotations

import json
import pathlib
import re

import pytest

from app.services import ir_mask

ROOT = pathlib.Path(__file__).resolve().parent.parent

# 전부 지어낸 이름이다.
FIRM_SHORT = "가나벤처스"          # 5자
FIRM_LONG = "마바사아자캐피탈파트너스"  # 12자 — 길이가 다른 짝
PERSON_SHORT = "홍길동"
PERSON_LONG = "남궁민수"            # 두 글자 성
COMPANY_A = "샘플에이"
COMPANY_B = "샘플비"
COMPANY_OFF = "샘플씨"             # 계약 안 한 기업


def _month(offset: int = 0) -> str:
    """이번 달(또는 몇 달 전) — `2026-09` 꼴. **박아 두지 않는다.**"""
    from app import clock

    today = clock.today()
    total = today.year * 12 + (today.month - 1) + offset
    return f"{total // 12:04d}-{total % 12 + 1:02d}"


def _day(month: str, day: int = 12) -> str:
    return f"{month}-{day:02d}"


# ── 밑자리 ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def seeded(db, users):
    """기업 셋(계약 둘·미계약 하나) + 투자사 둘 + 두 출처의 요청."""
    from app.models import ContactActivity, IrCompany, IrRequest, VcContact

    a = IrCompany(name=COMPANY_A, contract_status="paid")
    b = IrCompany(name=COMPANY_B, contract_status="free")
    off = IrCompany(name=COMPANY_OFF, contract_status="none")
    db.add_all([a, b, off])

    short = VcContact(user_id=1, name=PERSON_SHORT, firm=FIRM_SHORT)
    long_ = VcContact(user_id=1, name=PERSON_LONG, firm=FIRM_LONG)
    db.add_all([short, long_])
    db.flush()

    now = _month()
    # 출처 1 — 이 앱에서 누른 것(외래키가 있다).
    db.add(IrRequest(user_id=1, contact_id=short.id, company_id=a.id,
                     company_name=COMPANY_A, requested_at=_day(now, 3)))
    # 출처 2 — 시트에서 옮겨 온 것(이름 문자열뿐이다).
    db.add(ContactActivity(contact_id=long_.id, kind="ir_request",
                           content="IR 요청", happened_at=_day(now, 8),
                           company_names=json.dumps([COMPANY_A, COMPANY_B],
                                                    ensure_ascii=False)))
    db.commit()
    return {"a": a, "b": b, "off": off, "short": short, "long": long_,
            "month": now}


# ── 1. 가리기 ───────────────────────────────────────────────────────────────

def test_회사명은_첫_글자만_남는다():
    assert ir_mask.mask_company(FIRM_SHORT).startswith(FIRM_SHORT[0])
    assert FIRM_SHORT not in ir_mask.mask_company(FIRM_SHORT)
    assert FIRM_SHORT[1:] not in ir_mask.mask_company(FIRM_SHORT)


def test_사람_이름은_성만_남는다():
    got = ir_mask.mask_person(PERSON_SHORT)
    assert got.startswith(PERSON_SHORT[0])
    assert PERSON_SHORT not in got
    assert PERSON_SHORT[1:] not in got


def test_별표_개수가_이름_길이를_알려주지_않는다():
    """길이가 다른 둘이 **같은 개수**의 별표를 단다.

    길이에 맞추면 길이가 샌다 — 실측으로 이름 242개 중 185개(76%)가 한 곳으로
    확정됐다. 고정하면 52개(22%)로 준다.
    """
    assert len(FIRM_SHORT) != len(FIRM_LONG), "길이가 같으면 검사가 뜻이 없다"
    a = ir_mask.mask_company(FIRM_SHORT).count("*")
    b = ir_mask.mask_company(FIRM_LONG).count("*")
    assert a == b, f"별표 개수가 길이를 따라간다: {a} vs {b}"

    c = ir_mask.mask_person(PERSON_SHORT).count("*")
    d = ir_mask.mask_person(PERSON_LONG).count("*")
    assert c == d, f"별표 개수가 길이를 따라간다: {c} vs {d}"


def test_가려진_값의_길이도_늘_같다():
    """개수뿐 아니라 **전체 길이**가 같아야 한다 — 길면 그것이 곧 힌트다."""
    lens = {len(ir_mask.mask_company(x)) for x in (FIRM_SHORT, FIRM_LONG)}
    lens |= {len(ir_mask.mask_person(x)) for x in (PERSON_SHORT, PERSON_LONG)}
    assert len(lens) == 1, f"가린 뒤 길이가 갈린다: {lens}"


def test_두_글자_성은_한_글자만_남긴다():
    """`남궁민수` → 성을 `남궁` 으로 보지 않는다.

    복성인지 아닌지는 사전 없이 못 가른다 — 틀리면 두 글자가 **새는 쪽으로**
    틀린다. 판별하지 않고 늘 한 글자만 남긴다.
    """
    got = ir_mask.mask_person(PERSON_LONG)
    assert got == PERSON_LONG[0] + ir_mask.STARS
    assert PERSON_LONG[:2] not in got, "두 글자 성이 그대로 남았다"


def test_영문_이름도_첫_글자_하나():
    assert ir_mask.mask_person("John Smith") == "J" + ir_mask.STARS
    assert ir_mask.mask_company("Acme Ventures") == "A" + ir_mask.STARS
    assert "Smith" not in ir_mask.mask_person("John Smith")


def test_빈_값은_별표만():
    for blank in ("", "   ", None):
        assert ir_mask.mask_company(blank) == ir_mask.BLANK
        assert ir_mask.mask_person(blank) == ir_mask.BLANK


def test_법인_표기는_떼고_첫_글자를_잡는다():
    """`(주)가나벤처스` 가 괄호로 시작하면 남긴 한 글자가 이름의 첫 글자가 아니다."""
    assert ir_mask.mask_company(f"(주){FIRM_SHORT}") == FIRM_SHORT[0] + ir_mask.STARS
    assert ir_mask.mask_company(f"{FIRM_SHORT}(주)") == FIRM_SHORT[0] + ir_mask.STARS


def test_가리는_규칙은_한_곳에만_적혀_있다():
    """별표를 만드는 자리가 둘이면 한쪽이 낡고, **낡은 쪽이 이름을 내보낸다.**

    앱 코드에서 별표를 짓는 곳은 `services/ir_mask.py` 하나여야 한다.
    (`services/sms.py` 는 전화번호를 가린다 — 사람·회사 이름과 다른 일이다.)
    """
    allowed = {"app/services/ir_mask.py", "app/services/sms.py"}
    # 별표를 **짓는** 모양만 본다: `"***"` 같은 글자 뭉치와 `"*" * n` 같은 반복.
    # (설명글의 `**굵게**` 는 별표를 짓는 것이 아니다.)
    makes_stars = re.compile(r"""(["'])\*{2,}\1|["']\*["']\s*\*""")
    bad = [path.relative_to(ROOT).as_posix()
           for path in (ROOT / "app").rglob("*.py")
           if path.relative_to(ROOT).as_posix() not in allowed
           and makes_stars.search(path.read_text(encoding="utf-8"))]
    assert not bad, f"별표를 짓는 자리가 더 있다: {bad}"


# ── 2. 문서 화면 ────────────────────────────────────────────────────────────

def test_문서에_투자사_원래_이름이_한_글자도_통째로_안_나온다(logged_in, seeded):
    """담당자까지 켜고 본다 — 켠 상태가 가장 많이 새는 상태다."""
    r = logged_in.get(f"/startup/ir-report/{seeded['a'].id}"
                      f"?month={seeded['month']}&who=1")
    assert r.status_code == 200
    html = r.text
    for name in (FIRM_SHORT, FIRM_LONG, PERSON_SHORT, PERSON_LONG):
        assert name not in html, f"원래 이름이 그대로 나왔다: {name}"
    # 가린 값은 떠 있어야 한다 — 아무것도 안 나오면 가린 것이 아니라 빈 것이다.
    assert ir_mask.mask_company(FIRM_SHORT) in html
    assert ir_mask.mask_person(PERSON_LONG) in html


def test_담당자_이름은_기본으로_안_실린다(logged_in, seeded):
    """새는 자리를 하나 줄인다 — 필요할 때만 켠다(`who=1`)."""
    r = logged_in.get(f"/startup/ir-report/{seeded['a'].id}?month={seeded['month']}")
    assert r.status_code == 200
    assert ir_mask.mask_person(PERSON_SHORT) not in r.text
    assert ir_mask.mask_company(FIRM_SHORT) in r.text, "투자사는 실려야 한다"


def test_목록에도_투자사_이름이_안_나온다(logged_in, seeded):
    r = logged_in.get(f"/startup/ir-report?month={seeded['month']}")
    assert r.status_code == 200
    for name in (FIRM_SHORT, FIRM_LONG, PERSON_SHORT, PERSON_LONG):
        assert name not in r.text, f"목록 화면이 이름을 내보냈다: {name}"


# ── 3. 계약을 마친 기업만 ───────────────────────────────────────────────────

def test_계약_기업만_목록에_선다(logged_in, seeded):
    r = logged_in.get(f"/startup/ir-report?month={seeded['month']}")
    assert COMPANY_A in r.text and COMPANY_B in r.text
    assert COMPANY_OFF not in r.text, "미계약 기업이 목록에 있다"


def test_계약_안_한_기업은_문서가_안_열린다(logged_in, seeded):
    r = logged_in.get(f"/startup/ir-report/{seeded['off'].id}"
                      f"?month={seeded['month']}")
    assert r.status_code == 404


def test_없는_기업도_404(logged_in, seeded):
    assert logged_in.get("/startup/ir-report/999999").status_code == 404


# ── 4. 두 출처가 합쳐진다 ───────────────────────────────────────────────────

def test_두_출처가_한_문서에_같이_실린다(db, seeded):
    """이 앱에서 누른 것(외래키)과 시트에서 옮겨 온 것(이름 문자열)."""
    from app.services import ir_monthly

    got = ir_monthly.report(db, seeded["a"].id, seeded["month"])
    assert got["count"] == 2, "한쪽 출처만 세었다"
    assert {r.source for r in got["requesters"]} == {"app", "sheet"}


def test_한쪽_출처밖에_없는_달도_빈칸이_되지_않는다(db, seeded):
    """`샘플비` 는 시트 쪽에만 있다 — 앱 기록만 보면 통째로 빈다."""
    from app.services import ir_monthly

    got = ir_monthly.report(db, seeded["b"].id, seeded["month"])
    assert got["count"] == 1
    assert got["requesters"][0].source == "sheet"


def test_같은_투자사가_두_출처에_다_있으면_한_번만_센다(db, seeded):
    """옮겨 온 뒤 앱에서도 누른 건. 두 줄이면 `2곳` 이라고 적히지만 실제로는 한 곳이다."""
    import json as _json

    from app.models import ContactActivity
    from app.services import ir_monthly

    db.add(ContactActivity(contact_id=seeded["short"].id, kind="ir_request",
                           content="IR 요청", happened_at=_day(seeded["month"], 3),
                           company_names=_json.dumps([COMPANY_A], ensure_ascii=False)))
    db.commit()
    got = ir_monthly.report(db, seeded["a"].id, seeded["month"])
    assert got["count"] == 2, f"같은 곳을 두 번 셌다: {got['count']}"


def test_법인_표기가_달라도_같은_기업으로_붙는다(db, seeded):
    """시트 원문은 `(주)샘플에이` 처럼 적혀 온다."""
    import json as _json

    from app.models import ContactActivity, VcContact
    from app.services import ir_monthly

    other = VcContact(user_id=1, name="김서연", firm="바사벤처스")
    db.add(other)
    db.flush()
    db.add(ContactActivity(contact_id=other.id, kind="ir_request",
                           content="IR 요청", happened_at=_day(seeded["month"], 9),
                           company_names=_json.dumps([f"(주){COMPANY_A}"],
                                                     ensure_ascii=False)))
    db.commit()
    assert ir_monthly.report(db, seeded["a"].id, seeded["month"])["count"] == 3


# ── 5. 못 맞춘 것은 세지 않되, 몇 건인지 드러난다 ───────────────────────────

def test_못_맞춘_요청은_세어지지_않는다(db, seeded):
    import json as _json

    from app.models import ContactActivity
    from app.services import ir_monthly

    db.add(ContactActivity(contact_id=seeded["short"].id, kind="ir_request",
                           content="IR 요청", happened_at=_day(seeded["month"], 11),
                           company_names=_json.dumps(["우리목록에없는이름"],
                                                     ensure_ascii=False)))
    db.commit()
    got = ir_monthly.monthly_requests(db, seeded["month"])
    total = sum(len(v) for v in got.by_company.values())
    assert total == 3, "못 맞춘 것이 어느 기업에 붙었다"
    assert got.skipped_count == 1


def test_개수만_적힌_요청은_적힌_개수만큼_빠진다(db, seeded):
    """`핵심 딜 8개사` — 몇 건인지는 알지만 어느 기업 몫인지 모른다."""
    from app.models import ContactActivity
    from app.services import ir_monthly

    db.add(ContactActivity(contact_id=seeded["short"].id, kind="ir_request",
                           content="핵심 딜 8개사", happened_at=_day(seeded["month"], 14),
                           company_names=None, company_count=8))
    db.commit()
    got = ir_monthly.monthly_requests(db, seeded["month"])
    assert got.skipped_count == 8
    assert sum(len(v) for v in got.by_company.values()) == 3, "개수만 적힌 것이 세어졌다"


def test_못_맞춘_건수가_화면에_뜬다(logged_in, db, seeded):
    """조용히 빠지면 `0곳` 이 진짜 0곳인지 못 맞춰서 0곳인지 알 수 없다."""
    import json as _json

    from app.models import ContactActivity

    db.add(ContactActivity(contact_id=seeded["short"].id, kind="ir_request",
                           content="IR 요청", happened_at=_day(seeded["month"], 11),
                           company_names=_json.dumps(["우리목록에없는이름"],
                                                     ensure_ascii=False)))
    db.commit()
    r = logged_in.get(f"/startup/ir-report?month={seeded['month']}")
    assert "1건" in r.text, "빠진 건수가 화면에 없다"


def test_이름이_여러_기업에_걸리면_고르지_않는다(db, seeded):
    """아무거나 고르면 남의 기업 문서에 남의 투자사가 실린다."""
    import json as _json

    from app.models import ContactActivity, IrCompany
    from app.services import ir_monthly

    # 시트에 적힌 `샘플에이비씨` 는 `샘플에이`·`샘플에이비` 둘 다에 걸린다.
    db.add(IrCompany(name=COMPANY_A + "비", contract_status="paid"))
    db.add(ContactActivity(contact_id=seeded["short"].id, kind="ir_request",
                           content="IR 요청", happened_at=_day(seeded["month"], 15),
                           company_names=_json.dumps([COMPANY_A + "비씨"],
                                                     ensure_ascii=False)))
    db.commit()
    got = ir_monthly.monthly_requests(db, seeded["month"])
    assert got.skipped_count == 1
    assert any("걸림" in s.label for s in got.skipped)


# ── 6. 달 가르기 ────────────────────────────────────────────────────────────

def test_지난달_요청은_이번_달_문서에_안_실린다(db, seeded):
    import json as _json

    from app.models import ContactActivity
    from app.services import ir_monthly

    db.add(ContactActivity(contact_id=seeded["short"].id, kind="ir_request",
                           content="IR 요청", happened_at=_day(_month(-1), 20),
                           company_names=_json.dumps([COMPANY_A], ensure_ascii=False)))
    db.commit()
    assert ir_monthly.report(db, seeded["a"].id, seeded["month"])["count"] == 2
    assert ir_monthly.report(db, seeded["a"].id, _month(-1))["count"] == 1


def test_날짜가_없으면_시트가_적어_둔_달을_쓴다(db, seeded):
    """시트에는 날짜 없이 달만 적힌 회차가 있다 — 버리면 그 달이 통째로 빈다."""
    import json as _json

    from app.models import ContactActivity
    from app.services import ir_monthly

    last = _month(-1)
    db.add(ContactActivity(contact_id=seeded["long"].id, kind="ir_request",
                           content="IR 요청", month=last, happened_at=None,
                           company_names=_json.dumps([COMPANY_A], ensure_ascii=False)))
    db.commit()
    assert ir_monthly.report(db, seeded["a"].id, last)["count"] == 1


def test_고를_수_있는_달은_기록에서_나온다(db, seeded):
    from app.services import ir_monthly

    got = ir_monthly.month_options(db)
    assert got == sorted(got, reverse=True), "최근 달이 위에 와야 한다"
    assert seeded["month"] in got
    assert ir_monthly.this_month() in got, "이번 달은 기록이 없어도 고를 수 있어야 한다"


# ── 7. 요청 0곳 · 1곳 ──────────────────────────────────────────────────────

def test_요청이_0곳인_기업도_목록에는_남는다(logged_in, db, seeded):
    """빼 버리면 **진짜 0곳**과 **못 맞춰서 0곳**이 똑같이 사라진다 —
    그 둘은 해야 할 일이 정반대다."""
    from app.services import ir_monthly

    got = ir_monthly.overview(db, _month(-2))
    names = {r["company"].name for r in got["rows"]}
    assert {COMPANY_A, COMPANY_B} <= names
    assert all(r["count"] == 0 and not r["sendable"] for r in got["rows"])

    r = logged_in.get(f"/startup/ir-report?month={_month(-2)}")
    assert COMPANY_A in r.text
    assert "요청 없음" in r.text, "0곳인 기업이 무엇으로 보이는지 화면에 없다"


def test_요청이_0곳이면_문서를_만들지_않는다(logged_in, db, seeded):
    """화면은 열리되 **보낼 것이 아니라고** 말한다. 빈 문서를 그대로 보내면
    받는 대표는 우리가 아무것도 안 한 줄로 읽는다."""
    from app.services import ir_monthly

    got = ir_monthly.report(db, seeded["a"].id, _month(-2))
    assert got["empty"] and got["count"] == 0

    r = logged_in.get(f"/startup/ir-report/{seeded['a'].id}?month={_month(-2)}")
    assert r.status_code == 200
    assert "보낼 문서가 아닙니다" in r.text


def test_한_곳뿐이면_가릴_상대가_없다고_알린다(logged_in, db, seeded):
    """87% 가 이 경우다 — 그냥 만들되, 만드는 사람이 알고 만들어야 한다."""
    from app.services import ir_monthly

    got = ir_monthly.overview(db, seeded["month"])
    row = next(r for r in got["rows"] if r["company"].name == COMPANY_B)
    assert row["alone"] and row["sendable"]

    r = logged_in.get(f"/startup/ir-report?month={seeded['month']}")
    assert "가릴 상대 없음" in r.text


# ── 8. 인쇄했을 때 ──────────────────────────────────────────────────────────

CSS = ROOT / "app" / "static" / "css" / "app.css"


def _print_block() -> str:
    css = CSS.read_text(encoding="utf-8")
    m = re.search(r"@media\s+print\s*\{", css)
    assert m, "인쇄용 규칙(@media print)이 없다"
    i = m.start()
    depth, out = 0, []
    for ch in css[i:]:
        out.append(ch)
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                break
    # 설명글은 떼고 본다 — 붙어 있으면 셀렉터에 딸려 들어간다.
    return re.sub(r"/\*.*?\*/", "", "".join(out), flags=re.S)


def test_인쇄하면_화면_것이_종이에_안_나간다():
    """좌측 메뉴·단추가 찍혀 나가면 문서가 아니라 화면을 복사한 것으로 읽힌다."""
    block = _print_block()
    hidden = re.findall(r"([^{}]+)\{[^{}]*display\s*:\s*none[^{}]*\}", block)
    selectors = {s.strip() for line in hidden for s in line.split(",")}
    for must in (".sidebar", ".no-print", ".toolbar"):
        assert must in selectors, f"인쇄에서 {must} 를 안 지운다"


def test_인쇄하면_문서가_종이_전체를_쓴다():
    """사이드바가 빠져도 `.layout` 이 flex 인 채면 오른쪽에 빈 기둥이 남는다."""
    block = _print_block()
    assert re.search(r"\.layout\s*\{[^{}]*display\s*:\s*block", block)
    assert re.search(r"\.content\s*\{[^{}]*padding\s*:\s*0", block)


def test_표_한_줄이_쪽을_넘기며_잘리지_않는다():
    """잘린 줄은 다음 쪽에서 날짜만 남아 무엇의 날짜인지 알 수 없게 된다."""
    block = _print_block()
    assert "page-break-inside: avoid" in block or "break-inside: avoid" in block
    assert "table-header-group" in block, "쪽을 넘기면 머리글이 사라진다"


def test_문서_화면이_인쇄에서_지울_것에_표시를_달고_있다(logged_in, seeded):
    """CSS 만 있고 화면에 표시가 없으면 아무것도 안 지워진다."""
    r = logged_in.get(f"/startup/ir-report/{seeded['a'].id}?month={seeded['month']}")
    assert "no-print" in r.text


# ── 9. 문 ──────────────────────────────────────────────────────────────────

def test_스타트업_화면에서_문서로_가는_길이_있다(logged_in, seeded):
    r = logged_in.get("/startup")
    assert "/startup/ir-report" in r.text, "문서로 가는 길이 화면에 없다"


def test_투자사_화면에는_그_길이_없다(logged_in, seeded):
    """이 문서는 스타트업 한 곳 단위다 — 투자사 화면의 일이 아니다."""
    r = logged_in.get("/contacts")
    assert "/startup/ir-report" not in r.text
