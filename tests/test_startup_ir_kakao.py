"""IR 자료 요청 투자사 — **카톡으로 나가는 글**.

옆의 문서(#131)와 짓는 자리가 다르므로 막을 것도 겹치지 않는다. 여기서 막는
것은 일곱이다.

  1. **가리기** — 원래 투자사명이 글 어디에도, 화면 어디에도 통째로 안 나온다.
     (문서에서 한 번 막았다고 여기서 안 막으면, 새는 자리가 하나 더 생긴 것뿐이다.)
  2. **누적** — `7월 말까지` 는 7월 한 달이 아니다. 지난 달 것이 들어오고,
     그 뒤 달 것은 안 들어온다.
  3. 계약을 마친 기업만.
  4. 요청이 0곳이면 **글을 짓지 않는다**(#131 과 같은 결).
  5. 날짜 꼴이 `5/22` — 앞에 0 이 없다.
  6. 기업이 여럿일 때 머리말과 줄이 갈린다.
  7. 길어지면 여러 통으로 나뉘고, 인사말은 **첫 통에만** 붙는다.

이름·회사명은 **전부 지어낸 값**이다 — 저장소가 공개다.
**날짜를 박지 않는다** — 달은 `clock` 에서 만든다.
"""
from __future__ import annotations

import json
import pathlib

import pytest

from app.services import ir_kakao, ir_mask

ROOT = pathlib.Path(__file__).resolve().parent.parent

# 전부 지어낸 이름이다.
FIRM_SHORT = "가나벤처스"
FIRM_LONG = "마바사아자캐피탈파트너스"
FIRM_OLD = "다라인베스트먼트"
PERSON = "홍길동"
COMPANY_A = "샘플에이"
COMPANY_B = "샘플비"
COMPANY_OFF = "샘플씨"          # 계약 안 한 기업


def _month(offset: int = 0) -> str:
    from app import clock

    today = clock.today()
    total = today.year * 12 + (today.month - 1) + offset
    return f"{total // 12:04d}-{total % 12 + 1:02d}"


def _day(month: str, day: int) -> str:
    return f"{month}-{day:02d}"


@pytest.fixture()
def seeded(db, users):
    """계약 기업 둘 + 미계약 하나. 요청은 **이번 달과 지난 달**에 걸쳐 있다."""
    from app.models import ContactActivity, IrCompany, IrRequest, VcContact

    a = IrCompany(name=COMPANY_A, contract_status="paid")
    b = IrCompany(name=COMPANY_B, contract_status="free")
    off = IrCompany(name=COMPANY_OFF, contract_status="none")
    db.add_all([a, b, off])

    short = VcContact(user_id=1, name=PERSON, firm=FIRM_SHORT)
    long_ = VcContact(user_id=1, name=PERSON, firm=FIRM_LONG)
    old = VcContact(user_id=1, name=PERSON, firm=FIRM_OLD)
    db.add_all([short, long_, old])
    db.flush()

    now, last = _month(), _month(-1)
    # 이번 달 — 이 앱에서 누른 것(외래키가 있다).
    db.add(IrRequest(user_id=1, contact_id=short.id, company_id=a.id,
                     company_name=COMPANY_A, requested_at=_day(now, 3)))
    # 이번 달 — 시트에서 옮겨 온 것(이름 문자열뿐이다). 기업 둘에 걸친다.
    db.add(ContactActivity(contact_id=long_.id, kind="ir_request",
                           content="IR 요청", happened_at=_day(now, 8),
                           company_names=json.dumps([COMPANY_A, COMPANY_B],
                                                    ensure_ascii=False)))
    # **지난 달** — 누적에만 들어온다.
    db.add(ContactActivity(contact_id=old.id, kind="ir_request",
                           content="IR 요청", happened_at=_day(last, 22),
                           company_names=json.dumps([COMPANY_A],
                                                    ensure_ascii=False)))
    db.commit()
    return {"a": a, "b": b, "off": off, "month": now, "last": last}


def _msg(db, seeded, company="a", month=None):
    return ir_kakao.for_company(db, seeded[company].id, month or seeded["month"])


# ── 1. 가리기 ───────────────────────────────────────────────────────────────

def test_문구에_투자사_원래_이름이_통째로_안_나온다(db, seeded):
    """이 검사 하나가 이 일에서 제일 중요하다."""
    got = _msg(db, seeded)
    for name in (FIRM_SHORT, FIRM_LONG, FIRM_OLD):
        assert name not in got.text, f"원래 이름이 그대로 실렸다: {name}"
    # 가린 값은 있어야 한다 — 아무것도 없으면 가린 것이 아니라 빈 것이다.
    assert ir_mask.mask_company(FIRM_SHORT) in got.text


def test_투자사_이름의_뒷부분도_안_나온다(db, seeded):
    """첫 글자만 남는다 — 두 글자째부터가 어디에도 없어야 한다."""
    got = _msg(db, seeded)
    for name in (FIRM_SHORT, FIRM_LONG, FIRM_OLD):
        assert name[1:] not in got.text, f"이름 뒷부분이 샜다: {name[1:]}"


def test_담당자_이름은_아예_안_실린다(db, seeded):
    """실물에 투자사만 적혀 있다. 사람 이름은 새는 자리를 하나 더 만든다."""
    got = _msg(db, seeded)
    assert PERSON not in got.text
    assert ir_mask.mask_person(PERSON) not in got.text


def test_화면에도_원래_이름이_안_나온다(logged_in, db, seeded):
    r = logged_in.get(f"/startup/ir-kakao/{seeded['a'].id}?month={seeded['month']}")
    assert r.status_code == 200
    for name in (FIRM_SHORT, FIRM_LONG, FIRM_OLD, PERSON):
        assert name not in r.text, f"화면이 이름을 내보냈다: {name}"
    assert ir_mask.mask_company(FIRM_LONG) in r.text


def test_가리기를_이_파일이_직접_하지_않는다():
    """별표를 짓는 자리는 `ir_mask` 하나다 — 여기서 또 지으면 낡는 쪽이 생긴다."""
    src = (ROOT / "app" / "services" / "ir_kakao.py").read_text(encoding="utf-8")
    assert "mask_company(" not in src and "mask_person(" not in src, \
        "카톡 문구가 제 손으로 가리고 있다 — 이미 가려진 값을 받아야 한다"


# ── 2. 누적 ─────────────────────────────────────────────────────────────────

def test_지난_달_요청이_이번_달_문구에_들어온다(db, seeded):
    """`7월 말까지` 는 7월 한 달이 아니다 — 한 달치만 실으면 지난 달에 물어본
    곳이 목록에서 사라진다."""
    got = _msg(db, seeded)
    assert len(got.lines) == 3, f"누적이 아니다: {[l.text for l in got.lines]}"
    assert ir_mask.mask_company(FIRM_OLD) in got.text, "지난 달 것이 빠졌다"


def test_문서는_한_달치_그대로다(db, seeded):
    """누적을 넣느라 옆의 문서까지 바뀌면 #131 이 조용히 달라진다."""
    from app.services import ir_monthly

    doc = ir_monthly.report(db, seeded["a"].id, seeded["month"])
    assert doc["count"] == 2, "문서가 누적이 되어 버렸다"


def test_그_달_뒤의_요청은_안_들어온다(db, seeded):
    """`말까지` 다 — 지난 달로 문구를 뽑으면 이번 달 것이 빠져야 한다."""
    got = _msg(db, seeded, month=seeded["last"])
    assert len(got.lines) == 1
    assert ir_mask.mask_company(FIRM_SHORT) not in got.text


def test_같은_투자사가_두_달에_걸쳐도_한_줄이다(db, seeded):
    """누적에서 두 줄이 되면 `몇 곳이 요청했는가` 가 틀어진다.
    남는 것은 **먼저 온 날**이다."""
    from app.models import ContactActivity, VcContact
    from app.services import ir_monthly

    old = db.query(VcContact).filter_by(firm=FIRM_OLD).one()
    db.add(ContactActivity(contact_id=old.id, kind="ir_request",
                           content="IR 요청", happened_at=_day(seeded["month"], 25),
                           company_names=json.dumps([COMPANY_A],
                                                    ensure_ascii=False)))
    db.commit()
    got = _msg(db, seeded)
    assert len(got.lines) == 3, f"같은 곳이 두 줄이 됐다: {[l.text for l in got.lines]}"
    masked = ir_mask.mask_company(FIRM_OLD)
    assert got.text.count(masked) == 1
    # 먼저 온 날이 남는다 — 지난 달 22일.
    assert ir_kakao.day_label(_day(seeded["last"], 22)) in got.text
    assert ir_monthly.monthly_requests(db, seeded["month"]).of(seeded["a"].id)


# ── 3. 계약을 마친 기업만 ───────────────────────────────────────────────────

def test_계약_안_한_기업은_문구를_안_만든다(db, seeded):
    """계약검토중·미계약 기업에 투자사 반응을 보내면 그것이 곧 영업 자료가 된다."""
    from app.models import ContactActivity, VcContact

    other = db.query(VcContact).filter_by(firm=FIRM_SHORT).one()
    db.add(ContactActivity(contact_id=other.id, kind="ir_request",
                           content="IR 요청", happened_at=_day(seeded["month"], 5),
                           company_names=json.dumps([COMPANY_OFF],
                                                    ensure_ascii=False)))
    db.commit()
    assert ir_kakao.for_company(db, seeded["off"].id, seeded["month"]) is None


def test_계약_안_한_기업은_화면도_404(logged_in, seeded):
    r = logged_in.get(f"/startup/ir-kakao/{seeded['off'].id}"
                      f"?month={seeded['month']}")
    assert r.status_code == 404


def test_없는_기업도_404(logged_in, seeded):
    assert logged_in.get("/startup/ir-kakao/999999").status_code == 404


# ── 4. 0곳이면 안 만든다 ────────────────────────────────────────────────────

def test_요청이_0곳이면_문구를_짓지_않는다(db, seeded):
    """빈 목록을 보내면 받는 대표는 우리가 아무것도 안 한 줄로 읽는다."""
    assert _msg(db, seeded, month=_month(-6)) is None


def test_0곳인_달은_화면도_404(logged_in, seeded):
    r = logged_in.get(f"/startup/ir-kakao/{seeded['a'].id}?month={_month(-6)}")
    assert r.status_code == 404
    assert "보낼 문구가 없습니다" in r.text


def test_목록에서_누적_0곳이면_문구_링크가_안_선다(logged_in, db, seeded):
    r = logged_in.get(f"/startup/ir-report?month={_month(-6)}")
    assert r.status_code == 200
    assert f"/startup/ir-kakao/{seeded['a'].id}" not in r.text


def test_이_달_0곳이어도_누적이_있으면_문구는_나간다(logged_in, db, seeded):
    """문서는 없고 **문구만** 있는 줄. 이 달 수로 막으면 실물과 다른 글이 된다.

    다음 달에는 아직 아무 요청도 없다 — 그래도 `말까지` 는 지금까지 쌓인 것을
    다 싣는다.
    """
    from app.services import ir_monthly

    nxt = _month(1)
    got = ir_monthly.overview(db, nxt)
    row = next(r for r in got["rows"] if r["company"].name == COMPANY_A)
    assert row["count"] == 0 and not row["sendable"], "그 달에 요청이 있다"
    assert row["msg_sendable"] and row["total_count"] == 3, "누적이 안 잡혔다"
    assert got["sendable_count"] == 0 and got["msg_sendable_count"] == 2

    r = logged_in.get(f"/startup/ir-report?month={nxt}")
    assert f"/startup/ir-kakao/{seeded['a'].id}" in r.text
    assert f"/startup/ir-report/{seeded['a'].id}" not in r.text


# ── 5. 실물의 모양 ──────────────────────────────────────────────────────────

def test_날짜는_앞에_0_없이_찍힌다(db, seeded):
    """실물이 `5/22` 다. `05/22` 도 `5/2` 도 아니다."""
    assert ir_kakao.day_label("2026-05-22") == "5/22"
    assert ir_kakao.day_label("2026-11-02") == "11/2"
    got = _msg(db, seeded)
    assert f"{ir_kakao.day_label(_day(seeded['last'], 22))} " in got.text


def test_날짜를_모르면_지어내지_않는다():
    """달만 적힌 기록에 `5/1` 을 넣으면 대표는 그날 온 줄로 읽는다."""
    assert ir_kakao.day_label("2026-05") == ""
    assert ir_kakao.day_label("") == ""


def test_달은_7월_꼴이다():
    assert ir_kakao.month_label("2026-07") == "7월"
    assert ir_kakao.month_label("2026-11") == "11월"
    assert ir_kakao.month_label("아무거나") == ""


def test_머리말_세_줄이_실물_그대로다(db, seeded):
    got = _msg(db, seeded)
    head = got.text.splitlines()
    assert head[0] == "안녕하세요 대표님"
    assert head[1].startswith(f"{ir_kakao.month_label(seeded['month'])} 말까지 ")
    assert head[1].endswith(COMPANY_A)
    assert head[2] == ir_kakao.LEAD
    assert head[3] == "", "머리말과 목록 사이에 빈 줄이 없다"


def test_줄은_날짜_기업_투자사_차례다(db, seeded):
    got = _msg(db, seeded)
    line = got.lines[0]
    assert line.text == f"{line.date} {line.company} {line.firm}"
    assert line.company == COMPANY_A


def test_줄이_날짜_순으로_선다(db, seeded):
    got = _msg(db, seeded)
    assert got.lines[0].date == ir_kakao.day_label(_day(seeded["last"], 22))


# ── 6. 기업이 여럿일 때 ─────────────────────────────────────────────────────

def test_기업이_여럿이면_머리말에_다_적힌다(db, seeded):
    """실물이 `(주)가 , (주)나` 다."""
    got = ir_kakao.compose(db, [seeded["a"], seeded["b"]], seeded["month"])
    assert got is not None
    assert f"{COMPANY_A}{ir_kakao.COMPANY_SEP}{COMPANY_B}" in got.text


def test_줄마다_어느_기업_몫인지_적힌다(db, seeded):
    """섞인 목록에서 기업이 안 적히면 대표는 남의 회사 요청까지 제 것으로 읽는다."""
    got = ir_kakao.compose(db, [seeded["a"], seeded["b"]], seeded["month"])
    assert {ln.company for ln in got.lines} == {COMPANY_A, COMPANY_B}
    for ln in got.lines:
        assert ln.company in ln.text


def test_화면은_기업을_묶지_않는다(logged_in, db, seeded):
    """한 대표가 여러 기업을 갖는지 앱이 알 길이 없다(까닭은 routers/startup.py).
    엉뚱한 대표에게 남의 회사 목록이 가는 것이 이 일의 유일한 되돌릴 수 없는
    사고라, 화면은 **기업 하나씩** 부른다."""
    r = logged_in.get(f"/startup/ir-kakao/{seeded['a'].id}?month={seeded['month']}")
    assert r.status_code == 200
    assert COMPANY_B not in r.text, "남의 기업이 이 대표의 문구에 실렸다"


# ── 7. 길어지면 나눈다 ──────────────────────────────────────────────────────

def test_짧으면_한_통이다(db, seeded):
    got = _msg(db, seeded)
    assert got.parts == [], "한 통인데 나눌 순서를 들고 있다"
    assert got.part_count == 1


def test_길면_여러_통으로_나뉜다():
    """누적이라 계약이 오래된 기업은 줄이 계속 는다."""
    lines = [f"5/{n % 28 + 1} 샘플기업 가***" for n in range(400)]
    parts = ir_kakao.pack("머리말", lines)
    assert len(parts) > 1
    assert all(len(p) <= ir_kakao.LIMIT for p in parts), "한 통이 한계를 넘었다"


def test_인사말은_첫_통에만_붙는다():
    """통마다 붙으면 같은 인사가 서너 번 온다."""
    lines = [f"5/{n % 28 + 1} 샘플기업 가***" for n in range(400)]
    parts = ir_kakao.pack("머리말", lines)
    assert parts[0].startswith("머리말")
    assert all("머리말" not in p for p in parts[1:])


def test_나눠도_줄이_하나도_안_빠진다():
    lines = [f"5/{n % 28 + 1} 샘플기업{n} 가***" for n in range(400)]
    parts = ir_kakao.pack("머리말", lines)
    joined = "\n".join(parts)
    assert all(ln in joined for ln in lines)


def test_나눌_자리는_글자_수로_정한다():
    """줄 수로 정하면 기업명 길이에 따라 어떤 통은 넘친다."""
    short = ir_kakao.pack("머리말", ["5/1 가 나***"] * 300)
    long_ = ir_kakao.pack("머리말", ["5/1 아주아주긴기업이름주식회사 나***"] * 300)
    assert len(long_) > len(short), "줄 수만 보고 잘랐다"


# ── 8. 화면 ─────────────────────────────────────────────────────────────────

def test_복사_단추가_공용_한_벌을_쓴다(logged_in, seeded):
    """클립보드 코드가 화면마다 갈리면 되돌림·안내 글자가 조금씩 달라진다."""
    r = logged_in.get(f"/startup/ir-kakao/{seeded['a'].id}?month={seeded['month']}")
    assert "문구 복사" in r.text
    assert "js/ir_attach_list.js" in r.text, "공용 한 벌이 안 실렸다"

    js = (ROOT / "app" / "static" / "js" / "startup_ir_kakao.js").read_text(
        encoding="utf-8")
    assert "IrAttach.copyText" in js
    assert "navigator.clipboard" not in js, "복사를 제 손으로 또 짰다"
    assert "execCommand(" not in js, "복사를 제 손으로 또 짰다"


def test_문구_전문이_화면에_그대로_있다(logged_in, db, seeded):
    """보이는 것과 복사되는 것이 같아야 한다."""
    r = logged_in.get(f"/startup/ir-kakao/{seeded['a'].id}?month={seeded['month']}")
    got = _msg(db, seeded)
    assert "안녕하세요 대표님" in r.text
    for line in got.lines:
        assert line.text in r.text


def test_못_맞춘_건수가_이_화면에도_뜬다(logged_in, db, seeded):
    """목록으로 돌아가지 않는 사람도 알아야 한다 — `0곳` 이 진짜 0곳인지
    못 맞춰서 0곳인지 구분할 수 없다."""
    from app.models import ContactActivity, VcContact

    other = db.query(VcContact).filter_by(firm=FIRM_SHORT).one()
    db.add(ContactActivity(contact_id=other.id, kind="ir_request",
                           content="IR 요청", happened_at=_day(seeded["month"], 11),
                           company_names=json.dumps(["우리목록에없는이름"],
                                                    ensure_ascii=False)))
    db.commit()
    r = logged_in.get(f"/startup/ir-kakao/{seeded['a'].id}?month={seeded['month']}")
    assert "1건" in r.text, "빠진 건수가 이 화면에 없다"


def test_날짜_없는_줄이_있으면_화면이_알린다(logged_in, db, seeded):
    from app.models import ContactActivity, VcContact

    # **다른 투자사**여야 한다 — 같은 투자사면 날짜가 있는 쪽과 한 줄로 묶여
    # 날짜 없는 줄 자체가 안 생긴다(그것이 맞는 동작이다).
    nameless = VcContact(user_id=1, name=PERSON, firm="차카타파트너스")
    db.add(nameless)
    db.flush()
    db.add(ContactActivity(contact_id=nameless.id, kind="ir_request",
                           content="IR 요청", month=seeded["last"], happened_at=None,
                           company_names=json.dumps([COMPANY_A],
                                                    ensure_ascii=False)))
    db.commit()
    got = _msg(db, seeded)
    assert got.undated >= 1
    # 날짜를 모르는 줄은 맨 뒤다 — 사이에 끼면 앞뒤 날짜 사이에 온 것처럼 읽힌다.
    assert got.lines[-1].date == ""

    r = logged_in.get(f"/startup/ir-kakao/{seeded['a'].id}?month={seeded['month']}")
    assert "날짜 없이" in r.text


def test_목록_화면에서_문구로_가는_길이_있다(logged_in, seeded):
    r = logged_in.get(f"/startup/ir-report?month={seeded['month']}")
    assert f"/startup/ir-kakao/{seeded['a'].id}" in r.text


def test_보내기_단추는_없다(logged_in, seeded):
    """스타트업 카톡방이 아직 자료에 없다. 보내는 시늉을 내는 단추를 세우면
    눌러 놓고 나간 줄 아는 사람이 생긴다."""
    r = logged_in.get(f"/startup/ir-kakao/{seeded['a'].id}?month={seeded['month']}")
    body = r.text.split('{}'.format("<main"))[-1]
    assert "primary-btn" not in body, "보내는 단추가 서 있다"
    assert "<form" not in body, "보내는 길이 열려 있다"


def test_문서_화면은_그대로_있다(logged_in, seeded):
    """Windows 파일 첨부 시험에 쓰인다 — 지우지 않는다."""
    r = logged_in.get(f"/startup/ir-report/{seeded['a'].id}?month={seeded['month']}")
    assert r.status_code == 200
    assert "인쇄 / PDF 로 저장" in r.text


def test_브라우저에서_실제로_복사가_된다():
    """★ 복사 규칙은 브라우저에 있으므로 검사도 브라우저에서 돈다
    (`tests/js/startup_ir_kakao_copy_test.js` — 화면 코드를 **그대로 실행**한다).
    여기서는 CI 가 그것을 잊지 않도록 감싼다."""
    import shutil
    import subprocess

    node = shutil.which("node")
    if node is None:
        pytest.skip("node 미설치 — 브라우저 로직 테스트 생략 "
                    "(호스트에서 `node tests/js/startup_ir_kakao_copy_test.js`)")
    js = ROOT / "tests" / "js" / "startup_ir_kakao_copy_test.js"
    got = subprocess.run([node, str(js)], capture_output=True, text=True,
                         timeout=60)
    assert got.returncode == 0, got.stdout + got.stderr
