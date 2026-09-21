"""IR 자료 요청 투자사 — **카톡으로 나가는 글**.

옆의 문서(#131)와 짓는 자리가 다르므로 막을 것도 겹치지 않는다. 여기서 막는
것은 일곱이다.

  1. **가리기** — 원래 투자사명도 **원래 심사역 이름**도 글 어디에도, 화면
     어디에도 통째로 안 나온다. 투자사만 **꼬리말**(`…파트너스`)이 남는다 —
     사용자가 정한 것이고, 여럿이 함께 쓰는 말이라 한 곳을 집어내지 못한다. 줄에 심사역이 실리게 된 뒤로 여기서 막을 것이
     하나 늘었다 — 가려진 값만 줄에 담긴다(`ir_kakao.Line`).
     (문서에서 한 번 막았다고 여기서 안 막으면, 새는 자리가 하나 더 생긴 것뿐이다.)
  2. **누적** — `7월 말까지` 는 7월 한 달이 아니다. 지난 달 것이 들어오고,
     그 뒤 달 것은 안 들어온다.
  3. 계약을 마친 기업만.
  4. 요청이 0곳이면 **글을 짓지 않는다**(#131 과 같은 결).
  5. 날짜 꼴이 `05/22` — **두 자리**다. 그리고 **모르는 자리는 지어내지 않고
     통째로 뺀다**(날짜도, 직함도).
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
# 같은 투자사에 심사역이 둘일 때를 보려고 **이름을 따로** 하나 더 둔다.
PERSON_2 = "강감찬"
# 직함은 가리지 않는다 — 이름이 아니라서 가릴 것이 없다(`ir_monthly.Requester`).
# 셋째는 **일부러 비운다**: 명단에 직함이 안 적힌 심사역이 실제로 있다.
TITLE_SHORT = "심사역"
TITLE_LONG = "이사"
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

    short = VcContact(user_id=1, name=PERSON, firm=FIRM_SHORT, title=TITLE_SHORT)
    long_ = VcContact(user_id=1, name=PERSON, firm=FIRM_LONG, title=TITLE_LONG)
    # **직함이 비어 있는 심사역.** 명단에 안 적힌 분이 실제로 있어서, 줄이 그때
    # 어떻게 끝나는지가 이 자료로 검사된다.
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


def _msg(db, seeded, company="a", month=None, user=None):
    return ir_kakao.for_company(db, user, seeded[company].id,
                                month or seeded["month"])


# ── 1. 가리기 ───────────────────────────────────────────────────────────────

def test_문구에_투자사_원래_이름이_통째로_안_나온다(db, seeded):
    """이 검사 하나가 이 일에서 제일 중요하다."""
    got = _msg(db, seeded)
    for name in (FIRM_SHORT, FIRM_LONG, FIRM_OLD):
        assert name not in got.text, f"원래 이름이 그대로 실렸다: {name}"
    # 가린 값은 있어야 한다 — 아무것도 없으면 가린 것이 아니라 빈 것이다.
    # **투자사는 `mask_firm`** 이다(꼬리말은 남는다 — `ir_mask` 참고).
    assert ir_mask.mask_firm(FIRM_SHORT) in got.text


def test_투자사_이름의_뒷부분도_안_나온다(db, seeded):
    """**바뀐 검사다.** 이제 드러나는 것이 하나 있다 — **꼬리말**이다.

    사용자가 `파트너스` · `인베스트먼트` · `자산운용` 은 보이게 하라고 정했다.
    그래서 검사는 "뒷부분이 통째로 안 나온다" 로 좁힌다: 꼬리말을 뺀 나머지는
    여전히 한 글자도 나오면 안 된다. 얼마나 덜 가려지는지는 `ir_mask` 에 재어
    적어 두었다.
    """
    got = _msg(db, seeded)
    for name in (FIRM_SHORT, FIRM_LONG, FIRM_OLD):
        assert name[1:] not in got.text, f"이름 뒷부분이 샜다: {name[1:]}"
        suffix = ir_mask.firm_suffix(name)
        body = name[1:-len(suffix)] if suffix else name[1:]
        for size in range(2, len(body) + 1):
            for start in range(0, len(body) - size + 1):
                assert body[start:start + size] not in got.text, \
                    f"꼬리말이 아닌 자리가 샜다: {body[start:start + size]}"


def test_심사역_원래_이름이_통째로_안_나온다(db, seeded):
    """**바뀐 검사다.** 예전에는 사람 이름이 줄에 아예 안 실렸다(투자사만 적었다).

    사용자가 줄에 `심사역 성함`·`직책`을 더해 달라고 정했다 — 대표가 어느
    투자사인지만 알고 누가 물어봤는지를 모르면 다음 연락을 준비할 수 없어서다.
    그래서 **안 싣는다**는 규칙은 없어졌지만, 막는 것은 오히려 늘었다:
    실리는 것은 **가려진 값뿐**이고 원래 이름은 글에도 자료구조에도 없다.
    """
    got = _msg(db, seeded)
    assert PERSON not in got.text, "원래 심사역 이름이 그대로 실렸다"
    # 가린 값은 있어야 한다 — 없으면 가린 것이 아니라 빈 것이다.
    assert ir_mask.mask_person(PERSON) in got.text


def test_심사역_이름의_뒷부분도_안_나온다(db, seeded):
    """첫 글자만 남는다 — 두 글자째부터가 어디에도 없어야 한다(투자사와 같다)."""
    got = _msg(db, seeded)
    assert PERSON[1:] not in got.text, f"이름 뒷부분이 샜다: {PERSON[1:]}"


def test_원래_이름은_자료구조에도_안_담긴다(db, seeded):
    """글자만 보는 것으로는 모자라다 — 화면이 `line.person` 을 그리는 날
    자료구조에 원래 이름이 들어 있으면 그대로 새기 때문이다.

    `Line` 이 들고 있는 것은 **가려진 값**이어야 한다(`ir_kakao.Line` 의 규칙).
    """
    got = _msg(db, seeded)
    for line in got.lines:
        assert PERSON not in line.person, "줄이 원래 이름을 들고 있다"
        assert line.person == ir_mask.mask_person(PERSON)
        for name in (FIRM_SHORT, FIRM_LONG, FIRM_OLD):
            assert name not in line.firm
    # 재료 쪽도 같다 — 여기서 새면 문서 화면도 같이 샌다.
    from app.services import ir_monthly

    for row in ir_monthly.monthly_requests(db, seeded["month"],
                                           cumulative=True).of(seeded["a"].id):
        assert PERSON not in row.person


def test_화면에도_원래_이름이_안_나온다(logged_in, db, seeded):
    r = logged_in.get(f"/startup/ir-kakao/{seeded['a'].id}?month={seeded['month']}")
    assert r.status_code == 200
    for name in (FIRM_SHORT, FIRM_LONG, FIRM_OLD, PERSON):
        assert name not in r.text, f"화면이 이름을 내보냈다: {name}"
    assert ir_mask.mask_firm(FIRM_LONG) in r.text
    # 심사역도 **가린 채로** 화면에 있어야 한다 — 없으면 화면과 나가는 글이
    # 다른 것이고, 통째로 있으면 새는 것이다.
    assert ir_mask.mask_person(PERSON) in r.text


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
    assert ir_mask.mask_firm(FIRM_OLD) in got.text, "지난 달 것이 빠졌다"


def test_문서는_한_달치_그대로다(db, seeded):
    """누적을 넣느라 옆의 문서까지 바뀌면 #131 이 조용히 달라진다."""
    from app.services import ir_monthly

    doc = ir_monthly.report(db, seeded["a"].id, seeded["month"])
    assert doc["count"] == 2, "문서가 누적이 되어 버렸다"


def test_그_달_뒤의_요청은_안_들어온다(db, seeded):
    """`말까지` 다 — 지난 달로 문구를 뽑으면 이번 달 것이 빠져야 한다."""
    got = _msg(db, seeded, month=seeded["last"])
    assert len(got.lines) == 1
    assert ir_mask.mask_firm(FIRM_SHORT) not in got.text


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
    masked = ir_mask.mask_firm(FIRM_OLD)
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
    assert ir_kakao.for_company(db, None, seeded["off"].id, seeded["month"]) is None


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

def test_날짜는_두_자리로_찍힌다(db, seeded):
    """**바뀐 검사다.** 예전에는 `5/22` 였다(실물이 그랬다).

    사용자가 **줄이 가지런히 서게** 두 자리로 바꿔 달라고 정했다. 날짜 자리의
    글자 수가 줄마다 다르면 그 뒷자리가 줄마다 다른 데서 시작한다.
    """
    assert ir_kakao.day_label("2026-05-22") == "05/22"
    assert ir_kakao.day_label("2026-11-02") == "11/02"
    # 모든 날짜 자리가 **같은 글자 수**다 — 그것이 이 변경의 전부다.
    assert len({len(ir_kakao.day_label(f"2026-{m:02d}-{d:02d}"))
                for m, d in ((1, 1), (5, 22), (11, 2), (12, 31))}) == 1
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


def test_글이_보고서_모양이다(db, seeded):
    """**바뀐 검사다.** 예전에는 머리말 세 줄이 실물 그대로였다
    (`안녕하세요 대표님` / `{달} 말까지 {기업들}` / 맺음말).

    사용자가 모양 몇 개를 보고 **보고서 느낌**을 골랐다 — 제목 두 줄, 요약 한
    줄, 목록을 감싸는 구분선, 그리고 **목록 아래로 내려간 맺음말**이다.
    """
    got = _msg(db, seeded)
    lines = got.text.splitlines()
    assert lines[0] == "[01. 월간 IR 진행 현황]"
    assert lines[1].endswith(ir_kakao.ym_label(seeded["month"]))
    assert lines[2] == ""
    assert lines[3] == ir_kakao.HELLO
    assert lines[4].startswith(COMPANY_A)
    assert lines[5] == ""
    assert lines[6].startswith(ir_kakao.SUMMARY_MARK), "요약 줄이 없다"
    assert lines[7] == ir_kakao.RULE, "목록 위 구분선이 없다"
    # 목록 → 구분선 → 맺음말.
    assert lines[8] == got.lines[0].text
    assert lines[-2] == ir_kakao.RULE, "목록 아래 구분선이 없다"
    assert lines[-1] == ir_kakao.DEFAULT_TAIL


def test_맺음말은_목록_아래에_온다(db, seeded):
    """사용자가 고른 모양이다 — 예전에는 머리말 셋째 줄이었다."""
    got = _msg(db, seeded)
    assert got.text.index(got.tail) > got.text.index(got.lines[-1].text)


def test_요약이_목록과_셈이_맞는다(db, seeded):
    """`12곳` 이라고 적힌 글에 줄이 15개면 대표는 셈이 안 맞는다고 읽는다.

    줄은 **사람마다** 하나씩 선다(`ir_monthly`). 그래서 곳과 명이 갈릴 때는
    둘 다 적는다.
    """
    from app.services import ir_monthly

    got = _msg(db, seeded)
    tally = ir_monthly.monthly_requests(
        db, seeded["month"], cumulative=True).tally_of(seeded["a"].id)
    assert tally.people == len(got.lines), "명이 줄 수와 다르다"
    assert got.summary.startswith(f"{ir_kakao.SUMMARY_MARK} 누적 ")
    assert ir_kakao.count_label(tally.firms, tally.people) in got.summary
    # 신규는 **그 달에 처음** 물어본 것이다 — 지난 달 것은 안 센다.
    assert f"{ir_kakao.month_label(seeded['month'])} 신규 " in got.summary
    assert tally.new_people == 2 and tally.people == 3, "신규가 누적과 같다"


def test_요약_숫자는_문구틀이_아니라_코드가_짓는다():
    """사람이 손으로 적은 숫자는 목록과 갈린다 — 갈린 채로 대표에게 간다."""
    from scripts import bootstrap

    for kind, body in bootstrap.TEAM_TEMPLATES:
        if kind.startswith("startup_sms"):
            assert "누적" not in body and ir_kakao.SUMMARY_MARK not in body


def test_시드_문구가_코드에_적힌_것과_같다():
    """둘이 갈리면 **문구틀을 지운 사람만** 다른 글을 받는다."""
    from scripts import bootstrap

    seeds = dict(bootstrap.TEAM_TEMPLATES)
    assert seeds[ir_kakao.KIND] == ir_kakao.DEFAULT_HEAD
    assert seeds[ir_kakao.TAIL_KIND] == ir_kakao.DEFAULT_TAIL


def test_줄은_날짜_기업_투자사_심사역_직함_차례다(db, seeded):
    """**바뀐 검사다.** 예전 차례는 `날짜 · 기업 · 투자사` 셋이었다.

    사용자가 적어 준 모양이 `{{일자}} {{회사명}} {{마스킹한 투자사}}
    {{마스킹한 심사역 성함}} {{직책}}` 이라 뒤에 둘이 붙었다. 차례를 여기에
    박아 두는 까닭은, 순서가 바뀌면 대표가 **투자사와 사람을 맞바꿔** 읽기
    때문이다 — 둘 다 `X***` 꼴이라 글만 보고는 가려낼 수가 없다.
    """
    got = _msg(db, seeded)
    line = next(ln for ln in got.lines if ln.title)
    # **바뀐 줄이다.** ① 기업이 하나인 글에서는 기업 자리가 빈다(그 이름은
    # 머리말에 있다). ② 자리 사이가 **두 칸**이다 — 사용자가 고른 모양이고,
    # 자리가 자리로 보여야 훑어 읽힌다. 직함만 이름에 한 칸으로 붙는다.
    assert line.text == (f"{line.date}  {line.firm}  "
                         f"{line.person} {line.title}")
    assert line.company == "", "기업이 하나인데 줄에 기업명이 또 적혔다"


def test_직함이_빈_심사역은_이름에서_줄이_끝난다(db, seeded):
    """**직함을 지어내지 않는다.**

    `담당` 같은 기본말을 넣으면 줄은 가지런해지지만, 그 말은 **우리가 만든
    것**이고 대표는 명단에 그렇게 적힌 줄로 읽는다. 날짜를 모를 때 그 자리를
    비우는 것과 같은 규칙이다 — 모르는 것은 적지 않는다.

    개발 자료 실측(2026-09): IR 을 요청한 심사역은 전부 직함이 적혀 있었고,
    명단 전체로는 **다섯에 하나쯤**이 비어 있다. 지금 안 보인다고 없는 길이
    아니라, 빈 직함은 언제든 목록에 들어온다.
    """
    got = _msg(db, seeded)
    # **바뀐 줄이다.** 투자사는 `mask_firm` 으로 가린다 — 꼬리말
    # (`…인베스트먼트`)이 남으므로 `mask_company` 로는 줄을 못 찾는다.
    bare = next(ln for ln in got.lines if ln.firm == ir_mask.mask_firm(FIRM_OLD))
    assert bare.title == ""
    assert bare.text == f"{bare.date}  {bare.firm}  {bare.person}"
    assert not bare.text.endswith(" "), "빈 직함 자리가 공백으로 남았다"
    # 자리 사이는 두 칸이다(사용자가 고른 모양) — 빈 자리가 남아 **세 칸**이
    # 벌어지면 그것이 고장이다.
    assert "   " not in bare.text, "빈 자리가 공백으로 남았다"
    assert "담당" not in got.text, "없는 직함을 지어냈다"


def test_직함은_명단에_적힌_그대로다(db, seeded):
    """가리지도, 다듬지도 않는다. `이사` 와 `이사님` 이 명단에 섞여 있는데
    여기서 하나로 맞추면 앱이 보여 주는 말과 대표가 받는 말이 갈린다."""
    got = _msg(db, seeded)
    assert f" {TITLE_SHORT}" in got.text and f" {TITLE_LONG}" in got.text
    assert ir_mask.mask_person(TITLE_SHORT) not in got.text, "직함을 가렸다"


def test_같은_투자사의_두_심사역이_서로_다른_줄로_보인다(db, seeded):
    """묶는 자리는 투자사가 아니라 **사람**이다(`ir_monthly`).

    예전에는 두 줄의 글자가 똑같았다(`5/3 샘플에이 가***` 두 번) — 대표가 보기에
    같은 줄이 두 번 적힌 고장이었다. 심사역이 붙은 지금은 두 줄이 갈린다.
    """
    from app.models import IrRequest, VcContact

    mate = VcContact(user_id=1, name=PERSON_2, firm=FIRM_SHORT, title=TITLE_LONG)
    db.add(mate)
    db.flush()
    db.add(IrRequest(user_id=1, contact_id=mate.id, company_id=seeded["a"].id,
                     company_name=COMPANY_A,
                     requested_at=_day(seeded["month"], 3)))
    db.commit()

    got = _msg(db, seeded)
    same = [ln for ln in got.lines if ln.firm == ir_mask.mask_firm(FIRM_SHORT)]
    assert len(same) == 2, "한 투자사의 두 심사역이 한 줄로 묶였다"
    assert len({ln.text for ln in same}) == 2, "두 줄의 글자가 똑같다"
    assert PERSON_2 not in got.text, "새 심사역의 원래 이름이 샜다"


def test_같은_심사역이_여러_번_요청해도_한_줄이다(db, seeded):
    """이름이 붙어도 묶는 규칙은 그대로다 — 한 사람이 두 번 물어봤다고 두 줄이
    되면 대표는 두 사람이 물어본 줄로 읽는다."""
    from app.models import IrRequest, VcContact

    short = db.query(VcContact).filter_by(firm=FIRM_SHORT).one()
    db.add(IrRequest(user_id=1, contact_id=short.id, company_id=seeded["a"].id,
                     company_name=COMPANY_A,
                     requested_at=_day(seeded["month"], 27)))
    db.commit()

    got = _msg(db, seeded)
    same = [ln for ln in got.lines if ln.firm == ir_mask.mask_firm(FIRM_SHORT)]
    assert len(same) == 1, f"한 사람이 두 줄이 됐다: {[l.text for l in same]}"
    # 남는 것은 **먼저 온 날**이다.
    assert same[0].date == ir_kakao.day_label(_day(seeded["month"], 3))


def test_이름_직함이_붙어_글이_길어진다(db, seeded):
    """줄마다 글자가 늘면 한 통이던 글이 두 통이 될 수 있다(`pack`).
    늘어난다는 사실 자체를 박아 둔다 — 통 수는 글자 수로 정해진다."""
    got = _msg(db, seeded)
    bare = sum(len(f"{ln.date} {ln.company} {ln.firm}".strip())
               for ln in got.lines)
    assert sum(len(ln.text) for ln in got.lines) > bare


def test_줄이_날짜_순으로_선다(db, seeded):
    got = _msg(db, seeded)
    assert got.lines[0].date == ir_kakao.day_label(_day(seeded["last"], 22))


# ── 6. 기업이 여럿일 때 ─────────────────────────────────────────────────────

def test_기업이_여럿이면_머리말에_다_적힌다(db, seeded):
    """실물이 `(주)가 , (주)나` 다."""
    got = ir_kakao.compose(db, None, [seeded["a"], seeded["b"]], seeded["month"])
    assert got is not None
    assert f"{COMPANY_A}{ir_kakao.COMPANY_SEP}{COMPANY_B}" in got.text


def test_줄마다_어느_기업_몫인지_적힌다(db, seeded):
    """섞인 목록에서 기업이 안 적히면 대표는 남의 회사 요청까지 제 것으로 읽는다."""
    got = ir_kakao.compose(db, None, [seeded["a"], seeded["b"]], seeded["month"])
    assert {ln.company for ln in got.lines} == {COMPANY_A, COMPANY_B}
    for ln in got.lines:
        assert ln.company in ln.text


def test_기업이_여럿이면_같은_투자사를_두_번_세지_않는다(db, seeded):
    """한 투자사가 두 기업에 물어봤으면 그것은 **한 곳**이다 — 기업별로 세어
    더하면 `곳` 이 부풀고, 부푼 수가 그대로 대표에게 간다."""
    from app.services import ir_monthly

    data = ir_monthly.monthly_requests(db, seeded["month"], cumulative=True)
    a, b = seeded["a"].id, seeded["b"].id
    both = data.tally_of(a, b)
    assert both.people == len(data.of(a)) + len(data.of(b)), "명이 줄 수와 다르다"
    assert both.firms < data.tally_of(a).firms + data.tally_of(b).firms, \
        "두 기업에 물어본 한 곳이 두 곳으로 세어졌다"

    got = ir_kakao.compose(db, None, [seeded["a"], seeded["b"]], seeded["month"])
    assert ir_kakao.count_label(both.firms, both.people) in got.summary


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


# ── 7-2. 맺음말 · 옛 문구틀  ★ ──────────────────────────────────────────────
#
# 맺음말이 **목록 아래**로 내려갔다(사용자가 고른 보고서 모양). 문구틀에
# `{목록}` 같은 자리를 내주지 않고 **문구를 둘로 나눠서** 그렇게 했다 —
# 목록을 어디에 놓을지는 여전히 코드만 안다(`services/ir_kakao.py` 머리말).


def _template(db, kind, body, user_id=None):
    from app.models import MessageTemplate

    db.add(MessageTemplate(user_id=user_id, kind=kind, name="시험", body=body,
                           is_active=1))
    db.commit()


def test_맺음말_문구를_고치면_글이_바뀐다(db, seeded, users):
    _template(db, ir_kakao.TAIL_KIND, "맺음말을 팀이 고쳤습니다.")
    got = _msg(db, seeded, user=users["u1"])
    assert got.text.endswith("맺음말을 팀이 고쳤습니다.")
    assert got.tail_from_template


def test_문구틀에_목록_자리를_내주지_않았다(db, seeded, users):
    """`{목록}` 을 주면 같은 문구에 **안 가려진** 자리도 쓸 수 있게 된다 —
    가리는 일이 문구를 고치는 사람 손으로 넘어간다. 맺음말을 목록 아래로
    내리면서도 그 선은 넘지 않았다(문구를 **둘로 나눴다**).
    """
    _template(db, ir_kakao.KIND, f"{ir_kakao.HELLO}\n{{목록}}")
    got = _msg(db, seeded, user=users["u1"])
    head = got.text.split(ir_kakao.RULE)[0]
    for line in got.lines:
        assert line.text not in head, "문구틀 자리에 목록이 들어갔다"
        assert got.text.count(line.text) == 1, "목록이 두 번 적혔다"

    from app.routers import templates_crud

    # 화면이 안내하는 자리에도 없다 — 안내에 뜨면 사람이 쓴다.
    assert "{목록}" not in str(templates_crud.VARIABLES)


def test_옛_문구틀의_맺음말이_목록_아래로_내려간다(db, seeded, users):
    """운영 DB 의 `startup_sms` 에는 맺음말이 **머리말 셋째 줄**로 들어 있다.
    그대로 두면 같은 말이 목록 위에 한 번, 아래에 또 한 번 적힌다."""
    old_body = "\n".join([ir_kakao.HELLO,
                          f"{ir_kakao.MONTH_TOKEN} 말까지 "
                          f"{ir_kakao.COMPANIES_TOKEN}",
                          ir_kakao.LEAD])
    _template(db, ir_kakao.KIND, old_body)
    got = _msg(db, seeded, user=users["u1"])
    assert got.text.count(ir_kakao.LEAD) == 1, "맺음말이 두 번 적혔다"
    assert got.text.endswith(ir_kakao.LEAD), "맺음말이 목록 아래로 안 내려갔다"
    assert not got.tail_from_template, "내려온 줄인데 문구틀에서 온 것으로 적혔다"


def test_팀이_고쳐_쓴_문장은_안_옮긴다(db, seeded, users):
    """저장소가 시드로 내보냈던 문장과 **글자까지 같을 때만** 옮긴다.
    남의 문장을 짐작해서 옮기기 시작하면 무엇이 나갈지 아무도 모른다."""
    mine = "우리 팀이 고쳐 쓴 맺음말입니다."
    _template(db, ir_kakao.KIND, f"{ir_kakao.HELLO}\n{mine}")
    got = _msg(db, seeded, user=users["u1"])
    assert got.text.splitlines()[1] == mine, "고쳐 쓴 문장을 코드가 옮겼다"


def test_맺음말은_마지막_통에_붙고_잘리지_않는다():
    """맺음말은 목록 아래에 오는 문장이라 첫 통에 붙으면 글이 거기서 끝난
    것처럼 읽힌다. 그리고 **잘리면 안 된다** — 잘린 자리가 마지막 문장이다."""
    lines = [f"05/{n % 28 + 1}  가***  홍*** 심사역" for n in range(400)]
    tail = "맺음말 한 줄입니다."
    parts = ir_kakao.pack("머리말", lines, tail)
    assert len(parts) > 1
    assert parts[-1].endswith(tail)
    assert all(tail not in p for p in parts[:-1]), "맺음말이 가운데 통에 붙었다"
    assert all(len(p) <= ir_kakao.LIMIT for p in parts), "한 통이 한계를 넘었다"


def test_자리가_없으면_맺음말만_한_통으로_간다():
    """넘치는 채로 붙이면 카톡에서 뒤가 잘려 나간다."""
    tail = "맺음말은 길다"
    parts = ir_kakao.pack("머리말", ["가" * 10] * 3, tail, limit=40)
    assert parts[-1] == tail, "자리가 없는데 우겨 넣었다"
    assert all(len(p) <= 40 for p in parts)


def test_구분선이_목록을_감싼다(db, seeded):
    got = _msg(db, seeded)
    body = got.text.split(ir_kakao.RULE)
    assert len(body) == 3, "구분선이 둘이 아니다"
    for line in got.lines:
        assert line.text in body[1], "줄이 구분선 밖으로 나갔다"


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
