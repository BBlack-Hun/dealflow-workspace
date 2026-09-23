"""맞추기용 자료 꺼내기 — **이름이 새지 않는가**가 이 검사의 절반이다.

이 자료는 앱 밖(다른 LLM 서비스)으로 나간다. 그래서 투자사는 번호로만 나가고
이름·투자사명·연락처·이메일·카톡방 이름은 한 글자도 실리면 안 된다.

제일 큰 위험은 **칸이 하나 늘 때 조용히 새는 것**이다. 오늘 맞게 짜 두어도
다음 사람이 `VcContact` 에 칸을 더하고 내보내기에 얹으면 그걸로 끝이다.
그래서 아래 `CONTACT_COLUMNS_ALLOWED_OUT` 은 **이 검사가 직접 들고 있다** —
서비스의 `INVESTOR_FIELDS` 를 가져다 쓰면 칸을 더하는 순간 '내보내도 되는
것' 의 목록도 같이 넓어져서 검사가 아무것도 못 막는다. 여기 적어 두면
모델에 칸이 늘 때 그 칸에 표식이 심기고, 결과에 표식이 섞여 나오면 그 자리에서
걸린다. 정말로 내보내야 하는 칸이라면 이 목록을 손대야 하고, 손대는 순간
사람이 한 번 보게 된다.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from html import escape
from pathlib import Path

import pytest
from sqlalchemy import String, Text

from .conftest import DEMO_PASSWORD

# 날짜가 바뀌어도 안 깨지게 못 박는다.
FIXED_NOW = "2026-09-01T09:00:00+09:00"

# 내보내도 되는 투자사 칸. **이 목록은 검사가 직접 들고 있다**(위 설명 참고).
CONTACT_COLUMNS_ALLOWED_OUT = {
    # `group_name` 은 **일부러** 나간다 — 사람이 손으로 묶어 둔 갈래이고, 딜
    # 소개를 실제로 보낼 때 대상을 묶는 값이다(`deal_queue.targets`). 나머지
    # 칸이 시트에서 딸려 온 자유 문장인 것과 다르고, 그 셋이 비어 있는 줄에도
    # 이 값은 적혀 있는 경우가 많다. 이름이 아니라 갈래라 나가도 된다.
    "group_name",
    "sectors", "round_size", "stages",
    "sourcing_note", "memo", "tips_note", "interest_level",
}
# 기업도 **이름이 나가지 않는다.** 맞추는 데 쓰이는 것은 분야·단계·요약·규모이고,
# 이름은 답으로 돌아온 `C-7` 을 앱 안에서 되돌려 얻는다. `name` 이 여기 없는 것이
# 이 검사의 요점이다 — 다시 넣으려면 이 줄을 손대야 하고, 손대는 순간 사람이 본다.
COMPANY_COLUMNS_ALLOWED_OUT = {
    "sector_major", "series", "one_liner", "summary",
}


@pytest.fixture()
def people(db, users):
    """관리자 · 투자컨설턴트. conftest 의 두 계정은 둘 다 일반 팀원이다."""
    from app.models import User
    from app.services import auth as auth_svc

    pw = auth_svc.hash_password(DEMO_PASSWORD)
    rows = [
        User(id=71, name="관리자시험", phone="01000000071", role="admin",
             password_hash=pw),
        User(id=72, name="컨설턴트시험", phone="01000000072", role="consultant",
             password_hash=pw),
    ]
    db.add_all(rows)
    db.commit()
    return {"admin": rows[0], "consultant": rows[1]}


def _contact(db, user_id: int, **kw):
    """가상의 투자사 담당자. 저장소가 공개라 실제 이름·번호를 두지 않는다."""
    from app.models import VcContact

    values = dict(user_id=user_id, name="홍길동", firm="가나벤처스",
                  phone="010-0000-0001", email="hong@example.invalid",
                  kakao_room_name="가나벤처스 Deal 공유", channel_kakao=1,
                  room_verified="verified", connect_stage="connected")
    values.update(kw)
    row = VcContact(**values)
    db.add(row)
    db.commit()
    return row


def _sheet(db, label: str, *, user_id=None, hidden=False):
    """명단(시트) 한 줄. **담당은 계정이 아니라 이 표가 정한다**(`SheetOwner`).

    `user_id` 가 비어 있으면 아직 누구의 것도 아닌 **투자사 풀**이다.
    """
    from app.models import SheetOwner

    row = SheetOwner(label=label, user_id=user_id, is_hidden=1 if hidden else 0)
    db.add(row)
    db.commit()
    return row


def _company(db, **kw):
    from app.models import IrCompany

    values = dict(name="가상바이오", sector_major="바이오", series="Series A",
                  one_liner="세포 배양 장비", revenue_recent="18.3")
    values.update(kw)
    row = IrCompany(**values)
    db.add(row)
    db.commit()
    return row


def _sent(db, contact, companies, *, status="sent", kind="deal_intro"):
    """이 담당자에게 이 기업들을 **한 회차로 보냈다** 고 적어 둔다.

    `status` 를 바꾸면 만들다 만 것·실패·취소를 흉내 낼 수 있다.
    """
    from app.models import DealBatch, DealBatchCompany, SendItem, SendJob

    batch = DealBatch(user_id=contact.user_id, title="가상 회차")
    db.add(batch)
    db.flush()
    for position, company in enumerate(companies, start=1):
        db.add(DealBatchCompany(batch_id=batch.id, company_id=company.id,
                                position=position))
    job = SendJob(user_id=contact.user_id, kind=kind, batch_id=batch.id,
                  status="done")
    db.add(job)
    db.flush()
    db.add(SendItem(job_id=job.id, contact_id=contact.id, room_name="가상 방",
                    message="가상 문구", status=status))
    db.commit()
    return batch


def _sheet_sent(db, contact, names, *, when="2026-08-13"):
    """시트에서 옮겨 온 지난 발송 기록 — 거기에는 **기업 이름**이 적혀 있다."""
    from app.models import ContactActivity

    db.add(ContactActivity(contact_id=contact.id, kind="deal_intro",
                           content="딜소개", happened_at=when,
                           company_names=json.dumps(names, ensure_ascii=False)))
    db.commit()


def _brief(db, user):
    from app.services import llm_brief

    return llm_brief.brief(db, user, now=FIXED_NOW)


# ── 무엇이 나가는가 ─────────────────────────────────────────────────────────

def test_an_investor_goes_out_as_a_number_and_their_preferences(db, users):
    """맞추는 데 필요한 것만 — 번호 · 선호분야 · 라운드 · 단계 · 메모 · 관심도."""
    row = _contact(db, users["u1"].id, group_name="Pre IPO",
                   sectors="AI,헬스케어",
                   round_size="건당 30억~100억", stages="Seed,SeriesA",
                   sourcing_note="전화완료", memo="후속 검토 중",
                   tips_note="팁스 운영사", interest_level="높음")

    got = _brief(db, users["u1"])["investors"]
    assert got == [{
        "id": f"V-{row.id}",
        # 사람이 손으로 묶어 둔 갈래. **적힌 글자 그대로** 나간다 — 앱이
        # 거르는 값과 한 글자라도 다르면 답을 받고도 보낼 수가 없다.
        "group_name": "Pre IPO",
        "sectors": "AI,헬스케어",
        "round_size": "건당 30억~100억",
        "stages": "Seed,SeriesA",
        "sourcing_note": "전화완료",
        "memo": "후속 검토 중",
        "tips_note": "팁스 운영사",
        "interest_level": "높음",
        # 이미 보낸 기업. 보낸 적이 없어도 칸은 남는다 — 칸이 없는 것과
        # '보낸 적 없다' 를 읽는 쪽이 구별할 길이 없다.
        "sent_before": [],
    }]


def test_a_memo_keeps_its_date_exactly_as_written(db, users):
    """`8/19 : 초기 기업보다는…` 의 날짜를 지우거나 다듬지 않는다.

    언제 들은 요청인지가 그 자체로 정보다 — 지난달 이야기와 이번 주 이야기는
    무게가 다르다. 사람이 "날짜는 남겨주고 이대로" 라고 못 박은 자리다.
    """
    written = "8/19 : 초기 기업보다는 규모가 좀 더 큰 곳 위주로"
    _contact(db, users["u1"].id, sourcing_note=written)

    assert _brief(db, users["u1"])["investors"][0]["sourcing_note"] == written


def test_an_empty_field_is_left_out_rather_than_sent_as_null(db, users):
    """빈 칸을 전부 `null` 로 채우면 자료의 절반이 빈 칸 이름이 된다."""
    row = _contact(db, users["u1"].id, sectors="AI", memo="   ")

    got = _brief(db, users["u1"])["investors"][0]
    assert got == {"id": f"V-{row.id}", "sectors": "AI", "sent_before": []}


def test_only_a_room_that_was_actually_checked_goes_into_the_data(db, users):
    """**보낼 수 없는 곳은 담지 않는다** — 맞춰 놓고 보낼 길이 없으면 못 쓴다.

    677곳을 내보내고 실제로 보낼 수 있는 곳은 114곳이던 자리다. 방이 없거나
    확인되지 않은 곳까지 담으면 추천의 대부분이 처음부터 쓸 수 없는 것으로
    돌아온다.
    """
    verified = _contact(db, users["u1"].id, room_verified="verified")
    for kw in ({"room_verified": "unverified"},
               {"room_verified": "not_found"},
               {"room_verified": "ambiguous"},
               {"kakao_room_name": ""},                       # 방 미등록
               {"channel_kakao": 0, "channel_email": 1}):     # 메일 채널
        _contact(db, users["u1"].id, **kw)

    ids = [item["id"] for item in _brief(db, users["u1"])["investors"]]
    assert ids == [f"V-{verified.id}"]


def test_the_filter_is_the_one_the_screens_already_use(db, users):
    """거르는 판정을 **여기서 다시 짓지 않는다** — 화면이 쓰는 그 함수를 부른다.

    두 벌로 적어 두면 화면 숫자와 자료 수가 어긋난다(투자사 관리 현황 117명 ·
    대시보드 123명으로 갈렸던 그 사고다). 그래서 판정을 옮겨 적지 않고, 같은
    함수가 말하는 것과 담긴 줄이 같은지를 본다 — 갈래가 하나 늘거나 `not_found`
    가 어느 쪽으로 가는지가 바뀌어도 둘이 같이 움직인다.

    **둘이 갈리면 여기가 깨진다.** `room_confirmed` 가 참인데 안 담기거나,
    거짓인데 담기면 그 자리에서 걸린다.
    """
    from app.services.dashboard import room_confirmed

    rows = [
        _contact(db, users["u1"].id, room_verified="verified"),
        _contact(db, users["u1"].id, room_verified="unverified"),
        _contact(db, users["u1"].id, room_verified="not_found"),
        _contact(db, users["u1"].id, room_verified="ambiguous"),
        _contact(db, users["u1"].id, room_verified=""),          # 처음 보는 값
        _contact(db, users["u1"].id, kakao_room_name=""),        # 방 미등록
        _contact(db, users["u1"].id, channel_kakao=0, channel_email=1),
    ]
    ids = {item["id"] for item in _brief(db, users["u1"])["investors"]}

    for row in rows:
        assert (f"V-{row.id}" in ids) == room_confirmed(row), row.id
    # 다 같은 답이 나오면 검사가 아무것도 안 본 것이다.
    assert 0 < len(ids) < len(rows)


def test_the_room_state_column_is_gone_because_every_row_now_has_one(db, users):
    """늘 같은 값인 칸은 읽는 쪽을 헷갈리게만 한다.

    방이 막힌 사람을 담고 칸으로 알리던 자리다. 이제 담지 않으므로 칸도 없다 —
    남겨 두면 "거짓인 줄도 있나" 를 읽는 쪽이 계속 따져 보게 된다.
    """
    _contact(db, users["u1"].id)

    assert "room_open" not in _brief(db, users["u1"])["investors"][0]


def test_a_company_goes_out_as_a_number_not_a_name(db, users):
    """기업도 **번호로만** 나간다 — 이름은 답을 되돌릴 때 앱 안에서 붙는다.

    맞추는 데 쓰이는 것은 분야·단계·요약·규모다. 이름은 그 일에 쓰이지 않고,
    앱 밖으로 나가는 자료에서 필요 없는 것을 빼는 것이 가장 확실한 보호다.
    """
    ok = _company(db, name="가상바이오", raise_target="30", pre_value="120")

    got = {c["id"]: c for c in _brief(db, users["u1"])["companies"]}
    assert "name" not in got[f"C-{ok.id}"]
    assert "가상바이오" not in json.dumps(got, ensure_ascii=False)
    # 맞추는 데 쓰는 것은 그대로 남는다.
    assert got[f"C-{ok.id}"]["sector_major"] == "바이오"


def test_a_company_that_names_itself_in_its_own_summary_is_masked(db, users):
    """이름 칸을 빼도 **문장 안에 자기 이름이 남는** 줄이 있다.

    개발 자료 344곳 중 5곳이 그랬다. 투자사 쪽에서 이미 겪은 것과 같은 일이라
    **같은 `_scrub`** 을 지나게 한다 — 두 벌로 만들면 한쪽이 낡는다.
    """
    from app.services.llm_brief import MASK

    _company(db, name="가상바이오", one_liner="가상바이오는 세포 배양 장비를 만든다",
             summary="가상바이오 창업자 김대표", contact_name="김대표",
             contact_phone="010-0000-0002", assignee_name="박담당",
             kakao_room_name="가상바이오 대표님")

    got = _brief(db, users["u1"])["companies"][0]
    dumped = json.dumps(got, ensure_ascii=False)
    for secret in ("가상바이오", "김대표", "010-0000-0002", "박담당"):
        assert secret not in dumped, secret
    # 지운 자리는 비우지 않고 표시한다.
    assert MASK in got["one_liner"]
    assert "세포 배양 장비를 만든다" in got["one_liner"]


def test_a_thin_company_is_flagged_rather_than_hidden(db, users):
    """`IrCompany.introducible` 을 **다시 계산하지 않고** 그대로 읽는다."""
    ok = _company(db, name="가상바이오", raise_target="30", pre_value="120")
    thin = _company(db, name="가상로보틱스", sector_major="", one_liner="",
                    revenue_recent=None)

    got = {c["id"]: c for c in _brief(db, users["u1"])["companies"]}
    assert got[f"C-{ok.id}"]["introducible"] is ok.introducible is True
    # 내용이 모자란 기업도 **감추지 않는다** — 채우면 되는 것이라 보여야 한다.
    assert got[f"C-{thin.id}"]["introducible"] is thin.introducible is False


def test_a_company_marked_do_not_introduce_is_left_out(db, users):
    """`딜소개 불가` 는 판단이 아니라 **보내면 안 되는 곳**이다.

    발송 화면이 이미 같은 이유로 목록에서 뺀다(`routers/pages.py`). 여기 남기면
    보낼 수 없는 곳을 추천받는다 — 판정은 그 화면이 쓰는 상수를 그대로 읽는다.
    """
    from app.routers.companies import BLOCKED_CONTRACT

    live = _company(db, name="가상바이오")
    blocked = _company(db, name="가상소재", contract_status=BLOCKED_CONTRACT)

    ids = [c["id"] for c in _brief(db, users["u1"])["companies"]]
    assert ids == [f"C-{live.id}"]
    assert f"C-{blocked.id}" not in ids


def test_the_amount_unit_is_declared_once_and_the_bands_use_it(db, users):
    """저장은 백만원이다. 바꾸지 않고 단위만 밝힌다 — 두 표기를 같이 내보내면
    언젠가 둘이 어긋나고, 어긋난 쪽을 읽은 답은 100배가 틀어진다.

    **구간 표기도 같은 단위다.** 억으로 고쳐 적으면 한 자료 안에 두 단위가
    섞인다.
    """
    from app.services.llm_brief import (AMOUNT_EDGES, ZERO_BAND, amount_band,
                                        amount_bands)

    # 저장은 **사람이 적은 글자(억)** 다(0074). 자료로 나갈 때 `amount.million`
    # 이 백만원으로 옮기고, 그 숫자가 구간이 된다 — 아래 기대값의 정수와 같은 값이다.
    _company(db, revenue_recent="18.3", funding_total="5",
             raise_target="30", pre_value="120")

    out = _brief(db, users["u1"])
    assert out["amount_unit"] == "백만원"
    got = out["companies"][0]
    # 값 자체를 여기 또 적지 않는다 — 경계는 `AMOUNT_EDGES` 한 곳에서 온다.
    assert (got["revenue_recent"], got["funding_total"],
            got["raise_target"], got["pre_value"]) == (
        amount_band(1830), amount_band(500),
        amount_band(3000), amount_band(12000))
    # 구간 표에 쓰인 숫자는 **경계 그 자체**여야 한다. 억으로 고쳐 적으면
    # (`10000+` → `100+`) 여기서 걸린다 — 한 자료에 두 단위가 섞이는 순간이다.
    for band in amount_bands():
        if band == ZERO_BAND:
            continue
        for number in re.findall(r"\d+", band):
            assert int(number) in AMOUNT_EDGES, f"{band} 이 다른 눈금입니다"


# ── 금액이 구간으로 나가는가 ────────────────────────────────────────────────
#
# **이름을 뺐어도 숫자가 이름 노릇을 한다.** 실제 자료로 재 보니 나가는 317곳
# 중 분야+단계+수치 조합이 그 기업 하나만 가리키는 곳이 123곳이었고, 수치가
# 있는 114곳만 보면 112곳이 유일했다. 아래 검사들이 잠그는 것은 그 구멍이다.

#: 구간으로 나가야 하는 칸에 심는 **표식 값**. 경계와 겹치지 않는 숫자다 —
#: `1000` 을 심으면 구간 이름 `1000~5000` 안에 그 숫자가 들어 있어서, 값이
#: 새어 나갔는지 구간 이름을 본 것인지 구별할 수 없다.
#: **적는 글자와 그것이 뜻하는 백만원 정수를 함께 둔다**(0074). 나가면 안 되는
#: 것은 둘 다다 — 구간으로 바꿔 내보내면서 사람이 적은 글자(`18.37`)를 어딘가에
#: 그대로 실어 보내면, 이름을 뺀 뜻이 그 글자에서 그대로 풀린다.
AMOUNT_MARKS = {"revenue_recent": "18.37", "funding_total": "42.93",
                "raise_target": "74.11", "pre_value": "265.43"}
AMOUNT_MARK_MILLIONS = {"revenue_recent": 1837, "funding_total": 4293,
                        "raise_target": 7411, "pre_value": 26543}


def test_no_exact_amount_appears_anywhere_in_the_data(db, users):
    """**칸 이름이 아니라 값을 본다.** 표식 숫자를 심고 결과 전체를 훑는다.

    칸만 확인하면 다른 자리(요약 문장·이력·설명문)로 같은 숫자가 함께 나가는
    것을 못 잡는다 — 이름에 대해 이미 같은 방식으로 잠가 두었다.
    """
    _company(db, **AMOUNT_MARKS)

    dumped = json.dumps(_brief(db, users["u1"]), ensure_ascii=False)
    for field, value in AMOUNT_MARKS.items():
        assert str(value) not in dumped, f"{field} 에 적힌 글자가 나갔습니다"
    for field, value in AMOUNT_MARK_MILLIONS.items():
        assert str(value) not in dumped, f"{field} 의 정확한 값이 나갔습니다"
    # 검사가 헛돌지 않았는지 — 그 기업이 실제로 실려 있어야 한다.
    assert '"revenue_recent"' in dumped


def test_the_answer_that_actually_leaves_the_server_has_no_exact_amount(
        db, users, logged_in):
    """서비스가 아니라 **주소가 실제로 돌려주는 바이트**를 훑는다."""
    _company(db, **AMOUNT_MARKS)

    body = logged_in.get("/api/llm-brief.json").text
    for field, value in AMOUNT_MARKS.items():
        assert str(value) not in body, f"{field} 에 적힌 글자가 나갔습니다"
    for field, value in AMOUNT_MARK_MILLIONS.items():
        assert str(value) not in body, f"{field} 의 정확한 값이 나갔습니다"


def test_a_missing_amount_and_a_zero_are_different_facts(db, users):
    """없는 것을 맨 아래 구간에 넣으면 **없다는 사실이 사라진다.**

    "아직 매출이 없다" 와 "얼마인지 모른다" 는 다른 사실이고, 투자사에게
    보이는 뜻도 다르다.
    """
    from app.services.llm_brief import ZERO_BAND

    zero = _company(db, revenue_recent="0", funding_total="0",
                    raise_target="30", pre_value=None)
    unknown = _company(db, revenue_recent=None, raise_target="30")

    rows = {c["id"]: c for c in _brief(db, users["u1"])["companies"]}
    got_zero, got_unknown = rows[f"C-{zero.id}"], rows[f"C-{unknown.id}"]

    assert got_zero["revenue_recent"] == ZERO_BAND
    assert got_zero["funding_total"] == ZERO_BAND
    # 모르는 값은 **칸이 아예 없다** — `0` 으로도 `~1000` 으로도 채우지 않는다.
    assert "pre_value" not in got_zero
    assert "revenue_recent" not in got_unknown
    assert "funding_total" not in got_unknown


def test_a_value_sitting_exactly_on_a_boundary_goes_up(db, users):
    """경계값이 어느 쪽으로 가는지 못 박는다 — **앞 숫자 포함, 뒤 숫자 미포함.**

    정해 두지 않으면 같은 값이 사람마다 다른 구간으로 읽히고, 그 어긋남은
    자료만 봐서는 안 보인다.
    """
    from app.services.llm_brief import AMOUNT_EDGES, ZERO_BAND, amount_band

    first = AMOUNT_EDGES[0]
    assert amount_band(first - 1) == f"~{first}"
    assert amount_band(first) != f"~{first}", "경계값이 아래 구간에 남았습니다"
    for low, high in zip(AMOUNT_EDGES, AMOUNT_EDGES[1:]):
        assert amount_band(low) == f"{low}~{high}"
        assert amount_band(high - 1) == f"{low}~{high}"
    last = AMOUNT_EDGES[-1]
    assert amount_band(last) == f"{last}+"
    # 0 은 어느 구간에도 안 들어간다.
    assert amount_band(0) == ZERO_BAND
    assert amount_band(None) is None


def test_the_band_edges_are_written_in_exactly_one_place(db, users):
    """경계를 화면·자료·검사가 각자 들고 있으면 반드시 갈린다.

    값을 바꿔 보고 **나가는 자료와 읽는 법 설명이 둘 다** 따라오는지 본다
    (`PICK_COUNT` 와 같은 방식이다).
    """
    from app.services import llm_brief

    _company(db, revenue_recent="18.3")   # = 1830 백만원
    # 검사가 경계를 또 적지 않는다 — 지금 값이 무엇이든 따라오는지만 본다.
    original = llm_brief.AMOUNT_EDGES
    was = llm_brief.amount_band(1830)

    before = _brief(db, users["u1"])
    assert before["companies"][0]["revenue_recent"] == was
    assert was in before["note"]

    llm_brief.AMOUNT_EDGES = (2000,)
    try:
        after = _brief(db, users["u1"])
    finally:
        llm_brief.AMOUNT_EDGES = original

    assert after["companies"][0]["revenue_recent"] == "~2000"
    assert "~2000" in after["note"], "읽는 법 설명이 옛 경계를 들고 있습니다"
    assert was not in json.dumps(after, ensure_ascii=False), \
        "경계를 고쳤는데 옛 구간이 어딘가에 그대로 남아 있습니다"


def test_the_screen_does_not_write_the_edges_down_again(logged_in):
    """화면은 **구간으로 나간다는 사실만** 말한다 — 숫자는 자료가 들고 있다.

    구간 표를 화면에도 적어 두면 경계를 고치는 날 그 문장만 옛말이 되고,
    사람은 화면을 믿는다. `PICK_COUNT` · 시킬 말과 같은 자리다.
    """
    from app.services.llm_brief import ZERO_BAND, amount_bands

    assert "구간" in logged_in.get("/deals").text, \
        "금액이 구간으로 나간다는 것을 화면이 말하지 않습니다"

    root = Path(__file__).resolve().parent.parent
    for path in ("app/templates/deals.html", "app/static/js/llm_brief.js"):
        src = (root / path).read_text(encoding="utf-8")
        for band in amount_bands():
            if band == ZERO_BAND:      # `0` 은 어디에나 있는 글자다
                continue
            assert band not in src, f"{path} 가 구간 표를 따로 들고 있습니다"


def test_the_data_says_how_to_read_a_band(db, users):
    """구간 표만 던져 두면 읽는 쪽이 앞 숫자를 값으로 읽는다."""
    from app.services.llm_brief import AMOUNT_FIELDS, AMOUNT_UNIT, amount_bands

    got = _brief(db, users["u1"])["note"]
    assert AMOUNT_UNIT in got
    for field in AMOUNT_FIELDS:
        assert field in got, field
    for band in amount_bands():
        assert band in got, band
    assert "구간" in got and "포함" in got


# ── 매출이 계약 기준선을 넘는가 ─────────────────────────────────────────────
#
# 사용자 요구는 "유료계약·무료계약은 년매출 5억 이상 기업으로" 다. 그런데 금액이
# 구간으로 나가면서(#156) 기준선이 맨 아래 구간 안에 통째로 묻혔다 — LLM 이
# 자료만 보고는 판단할 수가 없다. 아래 검사들이 잠그는 것은 그 구멍이고,
# **정확한 금액은 여전히 안 나간다**는 것까지 함께 잠근다.

#: 투자라운드 칸이 실제로 적어 두는 모양(2026-09 까지 이름은 `기업구분`). 매출 기준이 **누적투자금 조건과 한 줄에**
#: 있어서, `5억미만` 만 찾으면 누적투자금 쪽을 매출로 읽는다.
SEED_SERIES = "Angel, Seed (누적투자금 0, 년매출액 3억미만)"
PRE_A_SERIES = "Pre A, Bridge (누적투자금 5억미만, 년매출액 10억이상)"


def _over(db, users, **kw):
    """기업 하나를 그 조건으로 만들고 **나가는 자료에서** 판정을 읽어 온다.

    함수를 직접 부르지 않고 자료를 거치는 것이 요점이다 — 판정이 맞아도
    자료에 안 실리면 LLM 은 못 본다.
    """
    row = _company(db, **kw)
    got = {c["id"]: c for c in _brief(db, users["u1"])["companies"]}
    return got[f"C-{row.id}"]["revenue_over"]


def test_every_company_says_whether_it_clears_the_contract_line(db, users):
    """칸이 **늘 있다.** 없으면 `모름` 과 `아니오` 를 구별할 자리가 사라진다."""
    from app.services.llm_brief import OVER_NO, OVER_UNKNOWN, OVER_YES

    _company(db, series=None, revenue_recent=None)
    for row in _brief(db, users["u1"])["companies"]:
        assert row["revenue_over"] in (OVER_YES, OVER_NO, OVER_UNKNOWN)


def test_the_line_is_read_from_both_the_series_column_and_the_recent_number(db,
                                                                           users):
    """같은 사실이 두 칸에 적혀 있다 — **하나라도 넘으면 `예`.**"""
    from app.services.llm_brief import OVER_NO, OVER_YES

    # 투자라운드만으로 넘는다(최근매출은 비어 있다).
    assert _over(db, users, series=PRE_A_SERIES, revenue_recent=None) == OVER_YES
    # 최근매출만으로 넘는다(투자라운드에는 매출 기준이 없다).
    assert _over(db, users, series="Series A", revenue_recent="7") == OVER_YES
    # 둘이 어긋나면 넘는 쪽이 이긴다 — 넘는다는 근거가 한 곳에라도 있으면 된다.
    assert _over(db, users, series=SEED_SERIES, revenue_recent="7") == OVER_YES
    # 둘 다 못 넘는다.
    assert _over(db, users, series=SEED_SERIES, revenue_recent="1") == OVER_NO


def test_unknown_is_never_folded_into_no(db, users):
    """**`모름` 은 `아니오` 가 아니다** — 못 넘는다는 뜻이 아니라 알 수 없다는 뜻.

    두 칸이 다 비어 있는 줄이 많다. 그것을 `아니오` 로 적으면 "매출이 안 되는
    곳" 이라는 **없는 사실**이 생기고, 읽는 쪽은 그 기업을 통째로 뺀다.
    """
    from app.services.llm_brief import OVER_UNKNOWN

    # 아무 근거도 없다.
    assert _over(db, users, series=None, revenue_recent=None) == OVER_UNKNOWN
    # `~` 는 '적었는데 모른다' 다 — 빈 칸과 같이 다뤄진다(`services/amount.py`).
    assert _over(db, users, series="Series A", revenue_recent="~") == OVER_UNKNOWN
    # 기준선을 **걸치는** 구간. 아래만 보고 `아니오` 라 적으면 모르는 것을
    # 뭉개는 것이 된다 — 실제로 넘을 수도 있다.
    assert _over(db, users, series=None, revenue_recent="3~10억") == OVER_UNKNOWN
    # 투자라운드이 걸치는 조건을 적어 둔 경우도 같다.
    assert _over(db, users, series="Series X (년매출액 10억미만)",
                 revenue_recent=None) == OVER_UNKNOWN


def test_a_zero_revenue_is_a_known_fact_not_an_unknown(db, users):
    """`0` 은 **아는 사실**이다 — 기준선을 못 넘는 것이 확실하다.

    `0`(없음)과 `~`(모름)을 가른 자리가 이 자료에 이미 있다(`ZERO_BAND`).
    같은 가름이 여기서도 서야 한다.
    """
    from app.services.llm_brief import OVER_NO

    assert _over(db, users, series=None, revenue_recent="0") == OVER_NO


def test_the_contract_line_is_written_in_exactly_one_place(db, users):
    """기준선을 코드·설명문·시킬 말이 각자 들고 있으면 반드시 갈린다.

    값을 바꿔 보고 **나가는 판정과 읽는 법 설명이 둘 다** 따라오는지 본다
    (`AMOUNT_EDGES` · `PICK_COUNT` 와 같은 방식이다).
    """
    from app.services import llm_brief

    what = _company(db, series=None, revenue_recent="7")   # = 700 백만원

    original = llm_brief.REVENUE_GATE
    unit = llm_brief.AMOUNT_UNIT
    before = _brief(db, users["u1"])
    got = {c["id"]: c for c in before["companies"]}[f"C-{what.id}"]
    assert got["revenue_over"] == llm_brief.OVER_YES
    # **단위까지 붙여 본다.** `500` 만 찾으면 구간 이름(`5000~10000`) 안의 글자에
    # 걸려 검사가 헛돈다.
    assert f"{original}{unit}" in before["note"], "읽는 법 설명에 기준선이 없습니다"

    # 구간 경계(`AMOUNT_EDGES`)와 겹치지 않는 값으로 옮긴다 — 겹치면 판정이
    # 따라온 것인지 구간이 따라온 것인지 구별할 수 없다.
    llm_brief.REVENUE_GATE = 777
    try:
        after = _brief(db, users["u1"])
    finally:
        llm_brief.REVENUE_GATE = original

    got = {c["id"]: c for c in after["companies"]}[f"C-{what.id}"]
    assert got["revenue_over"] == llm_brief.OVER_NO, \
        "기준선을 올렸는데 판정이 따라오지 않았습니다"
    assert f"777{unit}" in after["note"], "읽는 법 설명이 옛 기준선을 들고 있습니다"
    assert f"{original}{unit}" not in after["note"]


def test_the_line_is_decided_in_the_service_and_nowhere_else(db, users):
    """판정이 두 벌로 적히는 것을 막는다 — **`revenue_over()` 한 곳**이다.

    화면도 스크립트도 매출 기준을 스스로 세지 않는다. 기준선 숫자를 화면에
    적어 두면 고치는 날 그 문장만 옛말이 되고, 사람은 화면을 믿는다.
    """
    from app.services.llm_brief import REVENUE_GATE

    root = Path(__file__).resolve().parent.parent
    for path in ("app/templates/deals.html", "app/static/js/llm_brief.js"):
        src = (root / path).read_text(encoding="utf-8")
        assert str(REVENUE_GATE) not in src, f"{path} 가 기준선을 따로 들고 있습니다"


def test_the_line_never_carries_the_exact_amount_with_it(db, users):
    """`예`/`아니오` 는 **넘는가 아닌가**뿐이다 — 숫자가 딸려 나가면 안 된다.

    #156 이 막은 구멍(이름을 빼도 숫자로 특정된다)이 이 칸으로 다시 열리는
    것을 잠근다.
    """
    _company(db, series=PRE_A_SERIES, **AMOUNT_MARKS)

    dumped = json.dumps(_brief(db, users["u1"]), ensure_ascii=False)
    for field, value in AMOUNT_MARKS.items():
        assert str(value) not in dumped, f"{field} 에 적힌 글자가 나갔습니다"
    for field, value in AMOUNT_MARK_MILLIONS.items():
        assert str(value) not in dumped, f"{field} 의 정확한 값이 나갔습니다"
    assert '"revenue_over"' in dumped


# ── 이름이 새는가 ───────────────────────────────────────────────────────────
#
# 칸을 고르는 것만으로는 부족하다 — **메모 안에 이름이 문장째 적혀 있는** 줄이
# 실제로 있었다. 아래 두 갈래를 다 본다: 칸이 새는가, 문장이 새는가.

def test_a_memo_that_names_the_investor_is_masked(db, users):
    """자기 투자사명·이름·연락처가 자기 메모에 적혀 있으면 지운다.

    칸으로는 안 나가는데 문장 안에 그대로 있는 경우다. 실데이터를 꺼내 훑어
    보니 274곳 중 4곳이 그랬다 — 칸만 막으면 번호로 내보내는 뜻이 그 줄에서
    사라진다.
    """
    from app.services.llm_brief import MASK

    _contact(db, users["u1"].id, name="홍길동", firm="가나벤처스",
             phone="010-0000-0001", email="hong@example.invalid",
             kakao_room_name="가나벤처스 Deal 공유",
             memo="가나벤처스 홍길동 이사님 · 010-0000-0001 · hong@example.invalid",
             sourcing_note="가나벤처스 Deal 공유 방으로 초대함")

    got = _brief(db, users["u1"])["investors"][0]
    for secret in ("홍길동", "가나벤처스", "010-0000-0001", "hong@example.invalid",
                   "가나벤처스 Deal 공유"):
        assert secret not in json.dumps(got, ensure_ascii=False), secret
    # 지운 자리는 **비우지 않고 표시한다** — 그냥 빼면 문장이 멀쩡해 보여서
    # 뭔가 지워졌다는 것을 아무도 모른다.
    assert MASK in got["memo"]
    assert "이사님" in got["memo"], "지울 것만 지우고 문장은 남긴다"


def test_masking_does_not_touch_the_date_in_a_memo(db, users):
    """가리는 것은 이름·연락처뿐이다 — 날짜는 그대로 둔다."""
    _contact(db, users["u1"].id, firm="가나벤처스",
             sourcing_note="8/19 : 가나벤처스는 초기보다 규모가 큰 곳 위주로")

    got = _brief(db, users["u1"])["investors"][0]["sourcing_note"]
    assert got.startswith("8/19 : ")
    assert "초기보다 규모가 큰 곳 위주로" in got
    assert "가나벤처스" not in got


def test_a_phone_or_email_shape_is_masked_whoever_it_belongs_to(db, users):
    """값이 어느 칸에도 없이 문장에만 있는 연락처도 나가면 안 된다."""
    from app.services.llm_brief import MASK

    _contact(db, users["u1"].id, firm="가나벤처스",
             memo="비서분 02-000-0000 · 다른분 010-9999-8888 · x@example.invalid")
    _company(db, summary="문의는 031-000-0000 또는 ir@example.invalid 로")

    out = _brief(db, users["u1"])
    memo = out["investors"][0]["memo"]
    for shape in ("02-000-0000", "010-9999-8888", "x@example.invalid"):
        assert shape not in memo, shape
    assert memo.count(MASK) == 3

    summary = out["companies"][0]["summary"]
    assert "031-000-0000" not in summary and "ir@example.invalid" not in summary
    assert "문의는" in summary


def test_a_one_letter_value_never_blanks_a_whole_sentence(db, users):
    """한 글자짜리 값으로 지우기 시작하면 멀쩡한 문장이 통째로 뭉개진다."""
    _contact(db, users["u1"].id, name="김", firm="가나벤처스",
             memo="김치 관련 기업을 찾는다")

    got = _brief(db, users["u1"])["investors"][0]["memo"]
    assert got == "김치 관련 기업을 찾는다"



def test_another_rows_company_name_written_in_a_memo_is_masked(db, users):
    """**남의 상호는 지운다.**

    기업을 번호로만 내보내기로 해 놓고 그 이름이 옆줄 메모로 나가면, 규칙이
    지켜지는 줄과 안 지켜지는 줄이 섞인 채로 나간다 — 그런 보호는 없는 것과
    같다. 실데이터에서 실제로 나온 모양이다(투자사 메모 12곳 · 남의 소개
    문장 1곳).
    """
    from app.services.llm_brief import MASK

    _company(db, name="가상바이오테크")
    _contact(db, users["u1"].id, firm="가나벤처스",
             memo="가상바이오테크 소개드렸습니다")

    got = _brief(db, users["u1"])["investors"][0]["memo"]
    assert "가상바이오테크" not in got
    assert got == f"{MASK} 소개드렸습니다"


def test_another_investors_firm_written_in_a_memo_is_masked(db, users):
    """남의 투자사명도 마찬가지다 — 실데이터에서 3곳 나왔다."""
    _contact(db, users["u1"].id, firm="가나벤처스", memo="마바벤처스와 공동검토")
    _contact(db, users["u1"].id, firm="마바벤처스", sectors="바이오")

    memos = [i.get("memo", "") for i in _brief(db, users["u1"])["investors"]]
    assert not any("마바벤처스" in m for m in memos)


def test_a_short_org_name_does_not_blank_other_peoples_sentences(db, users):
    """짧은 값으로 남의 문장까지 지우면 멀쩡한 글이 뭉개진다.

    `카카오` 를 지우면 `카카오톡` 이야기가 `[가림]톡` 이 된다. 그래서 남의
    상호는 **일정 길이 이상**만 지운다(`CROSS_MIN_LEN`).
    """
    from app.services.llm_brief import CROSS_MIN_LEN

    short = "가나" * 1
    assert len(short) < CROSS_MIN_LEN, "이 검사는 짧은 상호를 전제로 한다"
    _company(db, name=short)
    _contact(db, users["u1"].id, firm="마바벤처스", memo="가나다라 분야를 본다")

    assert _brief(db, users["u1"])["investors"][0]["memo"] == "가나다라 분야를 본다"


def test_someone_elses_person_name_is_left_alone_on_purpose(db, users):
    """사람 이름은 남의 것까지 지우지 않는다 — 두세 글자라 우연히 들어맞는다.

    실제로 세 글자 담당자 이름이 남의 메모 261곳에 들어맞았다. 지켜야 하는
    것은 **그 줄이 누구인지 알아볼 수 없는 것**이라, 그 줄 자신의 값만 지운다.
    """
    _contact(db, users["u1"].id, name="김치", firm="마바벤처스",
             memo="김치 관련 기업을 찾는다")
    _contact(db, users["u1"].id, name="홍길동", firm="사아파트너스",
             memo="김치 관련 기업을 찾는다")

    memos = [i.get("memo", "") for i in _brief(db, users["u1"])["investors"]]
    # 자기 이름이 든 줄은 가려지고, 남의 줄은 문장이 살아 있다.
    assert "김치 관련 기업을 찾는다" in memos


# 표식을 심으면 그 줄이 **자료에서 통째로 빠지는** 칸. 자료가 담는 사람이
# `내 명단 · 방 확인됨` 으로 좁아진 뒤로, 여기에 아무 글자나 넣으면
# `_room_state` 가 '보낼 수 없음' 으로, `is_mine` 이 '남의 명단' 으로 읽어 줄이
# 사라진다 — 줄이 없으면 표식 검사는 언제나 통과한다. 그래서 이 칸들은 표식
# 대신 **저장값이 자료에 안 나오는지**를 따로 지킨다(아래 검사).
GATE_COLUMNS = {"room_verified", "source_sheet"}


def _mark_every_other_column(model, row, allowed, gate=()):
    """내보내면 안 되는 글자 칸마다 그 칸 이름이 든 표식을 심는다.

    **모델의 칸을 훑는다** — 손으로 적은 목록은 칸이 하나 늘 때 낡는다.
    표식에 칸 이름을 넣어 두어서, 걸렸을 때 어느 칸이 샜는지 바로 나온다.

    `gate` 는 줄이 자료에 담기는지를 **결정하는** 칸이다(`GATE_COLUMNS`).
    """
    marks = {}
    for column in model.__table__.columns:
        if (column.name in allowed or column.name in gate
                or not isinstance(column.type, (String, Text))):
            continue
        mark = f"표식-{column.name}-표식"
        marks[column.name] = mark
        setattr(row, column.name, mark)
    return marks


def test_no_investor_column_leaks_out_even_if_someone_adds_one(db, users):
    """**칸이 늘어도 걸리는 검사.**

    내보내도 되는 칸 말고는 전부 표식을 심고, 나간 자료에 표식이 하나라도
    섞였는지 본다. 다음 사람이 `VcContact` 에 칸을 더해 내보내기에 얹으면
    그 칸에도 표식이 심기므로 여기서 먼저 걸린다.
    """
    from app.models import VcContact

    # 표식을 못 심는 칸도 **값이 들어 있어야** 아래 검사가 무엇인가를 본다.
    _sheet(db, "내 딜소개현황", user_id=users["u1"].id)
    row = _contact(db, users["u1"].id, sectors="AI",
                   source_sheet="내 딜소개현황")
    marks = _mark_every_other_column(VcContact, row, CONTACT_COLUMNS_ALLOWED_OUT,
                                     gate=GATE_COLUMNS)
    db.commit()

    out = _brief(db, users["u1"])
    assert len(out["investors"]) == 1, "줄이 아예 안 나가면 검사가 아무것도 못 본다"

    dumped = json.dumps(out, ensure_ascii=False)
    leaked = sorted(name for name, mark in marks.items() if mark in dumped)
    assert not leaked, "투자사 자료에 이 칸이 새어 나갔습니다: " + ", ".join(leaked)
    # 표식을 심을 칸이 없으면 위 검사는 언제나 통과한다 — 그것도 잡는다.
    for must in ("name", "firm", "phone", "email", "kakao_room_name"):
        assert must in marks, f"{must} 칸에 표식을 못 심었습니다"
    # 표식을 못 심는 칸(줄이 담기는지를 결정하는 칸)은 **저장값 그대로** 본다.
    for column in GATE_COLUMNS:
        value = getattr(row, column)
        assert value and value not in dumped, f"{column} 칸이 새어 나갔습니다"


def test_no_company_side_contact_column_leaks_out_even_if_someone_adds_one(db, users):
    """기업은 이름이 나간다 — 그 대신 **기업 쪽 연락처**가 새면 안 된다."""
    from app.models import IrCompany

    row = _company(db, revenue_recent="18.3")
    marks = _mark_every_other_column(IrCompany, row, COMPANY_COLUMNS_ALLOWED_OUT)
    db.commit()

    out = _brief(db, users["u1"])
    assert len(out["companies"]) == 1

    dumped = json.dumps(out, ensure_ascii=False)
    leaked = sorted(name for name, mark in marks.items() if mark in dumped)
    assert not leaked, "기업 자료에 이 칸이 새어 나갔습니다: " + ", ".join(leaked)
    # **이름 칸도 표식 대상이다** — 여기 없으면 위 검사가 이름을 안 본 것이다.
    for must in ("name", "contact_name", "contact_phone", "contact_email",
                 "kakao_room_name", "assignee_name"):
        assert must in marks, f"{must} 칸에 표식을 못 심었습니다"


def test_the_keys_that_go_out_are_exactly_these(db, users):
    """칸이 조용히 하나 붙는 것을 모양으로도 못 박는다.

    위 표식 검사는 **값**이 새는 것을 잡고, 이것은 **칸**이 느는 것을 잡는다.
    값이 우연히 안 겹치는 칸(숫자·참거짓)이 붙어도 여기서 걸린다.
    """
    from app.services import llm_brief

    who = _contact(db, users["u1"].id, group_name="A", sectors="AI",
                   round_size="30억",
                   stages="Seed", sourcing_note="메모", memo="메모",
                   tips_note="메모", interest_level="높음")
    what = _company(db, summary="요약", funding_total="5", raise_target="30",
                    pre_value="120")
    _sent(db, who, [what])
    _sheet_sent(db, who, ["이제는없는기업"])

    out = _brief(db, users["u1"])
    # `sector_names` 는 **분야 이름뿐**이다 — 수요를 세는 쪽이 쓸 눈금이고,
    # 세는 일은 앱이 하지 않는다(`llm_brief.sector_names` 설명 참고).
    assert set(out) == {"generated_at", "scope", "amount_unit", "note",
                        "prompt", "investors", "companies", "sector_names",
                        # 그룹 갈래·인원. 이름은 한 곳에서만 짓는다.
                        llm_brief.GROUPS_KEY}
    assert set(out["investors"][0]) == {
        "id", "group_name", "sectors", "round_size", "stages",
        "sourcing_note", "memo", "tips_note", "interest_level",
        "sent_before", "sent_before_unmatched"}
    # **`name` 이 없다** — 기업도 번호로만 나간다.
    # `revenue_over` 는 정확한 금액이 아니라 **넘는가 아닌가** 한 칸이다.
    assert set(out["companies"][0]) == {
        "id", "sector_major", "series", "one_liner", "summary",
        "revenue_recent", "funding_total", "raise_target", "pre_value",
        "introducible", "revenue_over"}


def test_the_answer_that_actually_leaves_the_server_has_no_names_in_it(db, users,
                                                                       logged_in):
    """서비스가 아니라 **주소가 실제로 돌려주는 것**을 본다.

    라우터가 뒤에 무엇을 덧붙였을 수도 있다 — 나가는 바이트를 직접 훑는다.
    """
    who = _contact(db, users["u1"].id, name="홍길동", firm="가나벤처스",
                   phone="010-0000-0001", email="hong@example.invalid",
                   kakao_room_name="가나벤처스 Deal 공유", title="심사역",
                   group_name="Series B 이상", assignee_name="김담당",
                   sectors="AI")
    # 기업 이름도 **한 글자도** 나가면 안 된다. 이미 보낸 회차가 있어도
    # 이력에는 번호만 실린다.
    what = _company(db, name="가상바이오", contact_name="김대표",
                    contact_email="ceo@example.invalid",
                    one_liner="가상바이오의 세포 배양 장비")
    _sent(db, who, [what])

    body = logged_in.get("/api/llm-brief.json").text
    for secret in ("홍길동", "가나벤처스", "010-0000-0001", "hong@example.invalid",
                   "가나벤처스 Deal 공유", "심사역", "김담당",
                   "가상바이오", "김대표", "ceo@example.invalid"):
        assert secret not in body, f"내보낸 자료에 `{secret}` 이 들어 있습니다"
    # 검사가 헛돌지 않았는지 — 그 기업이 실제로 이력에 실렸어야 한다.
    assert f'"C-{what.id}"' in body
    # **그룹은 가리지 않는다.** 위 목록에서 빠진 것이 실수가 아니라는 것을
    # 여기서 못 박는다 — 사람 이름이 아니라 갈래이고, 이 이름으로 답이 돌아와야
    # 앱에서 그 갈래에 그대로 보낼 수 있다.
    assert "Series B 이상" in body


# ── 누가 받는가 ─────────────────────────────────────────────────────────────

def test_a_member_gets_only_the_contacts_they_manage(db, users):
    """딜 소개는 담당자별로 나간다 — 남의 담당을 추천받아도 보낼 수가 없다."""
    mine = _contact(db, users["u1"].id, sectors="AI")
    theirs = _contact(db, users["u2"].id, sectors="바이오")

    ids = [c["id"] for c in _brief(db, users["u1"])["investors"]]
    assert ids == [f"V-{mine.id}"]
    assert f"V-{theirs.id}" not in ids
    assert "내 명단" in _brief(db, users["u1"])["scope"]


def test_an_admin_gets_only_their_own_contacts_too(db, users, people):
    """**관리자도 자기 담당분만** 담는다 — 팀 전체를 담지 않는다.

    관리자 계정에서 꺼내면 팀 전체 677곳이 담기던 자리다. 딜 소개는 담당자별로
    나가므로 남의 담당 투자사를 추천받아도 **보낼 수가 없고**, 번호를 되찾는
    `resolve()` 도 같은 모집단이라 누구인지조차 못 본다. 팀 전체를 보고 고르는
    것은 투자사 관리 현황에서 할 일이다.
    """
    mine = _contact(db, people["admin"].id, sectors="AI")
    theirs = _contact(db, users["u2"].id, sectors="바이오")

    out = _brief(db, people["admin"])
    assert {c["id"] for c in out["investors"]} == {f"V-{mine.id}"}
    assert f"V-{theirs.id}" not in json.dumps(out, ensure_ascii=False)
    assert "내 명단" in out["scope"]


# ── 담당은 계정이 아니라 명단이다 ───────────────────────────────────────────
#
# 사용자가 정정한 자리다 — "`전체 딜소개현황-○○○` 이게 내꺼임.. 그 외의것은 내
# 담당이 아님." 계정만 보고 좁혔을 때는 실제 자료에서 수가 **우연히 같았다**:
# 계정 기준 265곳 중 방 확인됨이 114곳이고, 자기 명단(118곳) 중 방 확인됨도
# 114곳이었다. 나머지 명단(투자사 풀)에 방 확인된 줄이 하나도 없었을 뿐이라,
# 그 명단에서 방이 하나라도 확인되는 순간 담당이 아닌 줄이 자료에 섞인다.

def test_a_row_on_someone_elses_sheet_is_not_mine_even_on_my_account(db, users):
    """**같은 계정이 들고 있어도** 내 명단이 아니면 안 담긴다.

    투자사 풀은 분류 단위일 뿐 누구의 담당도 아니다 — 거기 사람에게 딜 소개를
    추천받아도 보낼 수가 없다. 방이 확인돼 있어도 마찬가지다(방만 보고 담으면
    바로 이 줄이 섞인다).
    """
    _sheet(db, "내 딜소개현황", user_id=users["u1"].id)
    _sheet(db, "투자사 풀")                     # 아직 누구의 것도 아니다
    _sheet(db, "남의 딜소개현황", user_id=users["u2"].id)

    mine = _contact(db, users["u1"].id, source_sheet="내 딜소개현황")
    pool = _contact(db, users["u1"].id, source_sheet="투자사 풀")
    theirs = _contact(db, users["u1"].id, source_sheet="남의 딜소개현황")

    ids = [c["id"] for c in _brief(db, users["u1"])["investors"]]
    assert ids == [f"V-{mine.id}"]
    assert f"V-{pool.id}" not in ids and f"V-{theirs.id}" not in ids


def test_a_row_on_several_sheets_counts_if_one_of_them_is_mine(db, users):
    """`source_sheet` 는 **쉼표로 이어 붙는다** — 부분 일치로 봐야 한다.

    임포트할 때마다 명단 이름이 누적되므로 한 줄이 여러 명단에 속한다. 내
    명단이 하나라도 있으면 내 담당이고, 통째로 견주면 그 줄이 통째로 빠진다.
    """
    _sheet(db, "내 딜소개현황", user_id=users["u1"].id)
    _sheet(db, "투자사 150")

    both = _contact(db, users["u1"].id,
                    source_sheet="내 딜소개현황,투자사 150")
    pool_only = _contact(db, users["u1"].id, source_sheet="투자사 150")

    ids = [c["id"] for c in _brief(db, users["u1"])["investors"]]
    assert ids == [f"V-{both.id}"], "여러 명단에 걸친 줄이 빠졌습니다"
    assert f"V-{pool_only.id}" not in ids


def test_a_row_that_only_lives_on_a_hidden_sheet_is_left_out(db, users):
    """감춘 명단은 투자사로 세지 않는다 — 자료에도 들어가면 안 된다.

    감춤은 지우기가 아니라 **투자사로 안 세는** 표시라, 한 줄이 살아 있는
    명단에도 함께 올라 있으면 그쪽이 이긴다(`sheet_owner.is_investor`).
    """
    _sheet(db, "내 딜소개현황", user_id=users["u1"].id)
    _sheet(db, "스타트업 명단", user_id=users["u1"].id, hidden=True)

    kept = _contact(db, users["u1"].id, source_sheet="내 딜소개현황")
    both = _contact(db, users["u1"].id,
                    source_sheet="내 딜소개현황,스타트업 명단")
    hidden_only = _contact(db, users["u1"].id, source_sheet="스타트업 명단")

    ids = {c["id"] for c in _brief(db, users["u1"])["investors"]}
    assert ids == {f"V-{kept.id}", f"V-{both.id}"}
    assert f"V-{hidden_only.id}" not in ids


def test_the_sheet_gate_is_the_one_the_dashboard_already_uses(db, users):
    """모집단을 **여기서 다시 짓지 않는다** — '내 담당' 을 세는 그 함수를 부른다.

    대시보드·후속이 쓰는 `sheet_owner.my_contacts` 와 담긴 줄이 갈리면 여기가
    깨진다. 명단 판정이 하나 늘어도(감춘 줄·직접 추가 …) 자료가 같이 움직인다.
    """
    from app.services import sheet_owner
    from app.services.dashboard import room_confirmed

    _sheet(db, "내 딜소개현황", user_id=users["u1"].id)
    _sheet(db, "투자사 150")
    _sheet(db, "스타트업 명단", user_id=users["u1"].id, hidden=True)

    for sheet in ("내 딜소개현황", "투자사 150", "스타트업 명단",
                  "내 딜소개현황,투자사 150", ""):
        for room in ("verified", "unverified", "not_found"):
            _contact(db, users["u1"].id, source_sheet=sheet, room_verified=room)

    ids = {c["id"] for c in _brief(db, users["u1"])["investors"]}
    want = {f"V-{c.id}" for c in sheet_owner.my_contacts(db, users["u1"])
            if room_confirmed(c)}
    assert ids == want
    # 다 담기거나 다 빠지면 검사가 아무것도 안 본 것이다.
    assert 0 < len(ids) < 15


# ── 몇 곳이 담기는지 말하는가 ───────────────────────────────────────────────
#
# 677 과 114 가 갈렸는데 화면도 자료도 아무 말을 안 해서, 사람은 답을 받고 나서야
# 대부분 못 보내는 곳인 것을 알았다. 수가 갈렸다는 사실 자체를 모르는 것이 제일
# 나쁘다.

def test_the_data_says_how_many_went_in_and_why(db, users):
    """자료를 열면 **몇 곳인지·왜 그 수인지** 읽을 수 있어야 한다."""
    kept = _contact(db, users["u1"].id)
    _contact(db, users["u1"].id, room_verified="not_found")
    _contact(db, users["u1"].id, kakao_room_name="")

    out = _brief(db, users["u1"])
    # 담긴 수와 **견주는 수**가 둘 다 적힌다 — 하나만 적으면 왜 줄었는지 모른다.
    # 견주는 수도 같은 모집단(내 명단)이라, 빠진 수는 오직 방 때문이다.
    assert out["scope"] == "내 명단의 투자사 3곳 중 카톡방 확인됨 1곳"
    assert len(out["investors"]) == 1 and out["investors"][0]["id"] == f"V-{kept.id}"
    # 무엇이 빠졌는지도 자료 안에 적혀 있어야 한다 — 담기지 않은 투자사가
    # 있다는 것을 모르면 "왜 이 투자사가 없지" 를 알 길이 없다.
    assert "확인됨" in out["note"] and "내 명단" in out["note"]


def test_the_count_in_the_data_is_the_number_of_rows_in_it(db, users):
    """적힌 수와 실제 줄 수가 갈리면 적어 둔 뜻이 사라진다."""
    from app.services import llm_brief

    for kw in ({}, {}, {"room_verified": "unverified"}, {"kakao_room_name": ""}):
        _contact(db, users["u1"].id, **kw)

    out = _brief(db, users["u1"])
    picked = llm_brief.scope(db, users["u1"])
    assert picked["count"] == len(out["investors"]) == 2
    assert str(picked["count"]) + "곳" in out["scope"]


def test_the_screen_says_the_same_number_as_the_data(logged_in, db, users):
    """화면과 자료가 **같은 문장**을 읽는다 — 각자 적으면 반드시 갈린다."""
    from app.services import llm_brief

    _contact(db, users["u1"].id)
    _contact(db, users["u1"].id, room_verified="not_found")

    html = logged_in.get("/deals").text
    picked = llm_brief.scope(db, users["u1"])
    assert picked["text"] in html, "화면이 몇 곳이 담기는지 말하지 않습니다"
    assert picked["text"] == _brief(db, users["u1"])["scope"]
    # 눌러 가면 **담긴 그 사람들**만 남아야 한다 — 세는 곳과 가는 곳이 다르면
    # 화면에 적힌 수를 확인할 길이 없다.
    # HTML 에서는 `&` 가 `&amp;` 로 새겨진다 — 새긴 뒤의 글자로 견준다.
    assert escape(picked["href"]) in html


def test_an_empty_data_set_says_so_instead_of_going_out_silently(logged_in, db,
                                                                 users):
    """방이 확인된 곳이 하나도 없으면 **자료도 화면도 그렇게 말한다.**

    빈 자료를 그대로 붙여 넣으면 LLM 은 아무것도 못 고르고, 사람은 시킨 말이
    잘못된 줄 안다 — 무엇을 하면 되는지까지 적어 둔다.
    """
    from app.services import llm_brief

    _contact(db, users["u1"].id, room_verified="not_found")

    out = _brief(db, users["u1"])
    assert out["investors"] == []
    assert "담을 투자사가 없습니다" in out["scope"]
    assert "방 연결 확인" in out["scope"], "무엇을 하면 되는지 말하지 않습니다"

    picked = llm_brief.scope(db, users["u1"])
    assert picked["empty"] is True
    assert picked["text"] in logged_in.get("/deals").text


def test_an_empty_sheet_and_an_unchecked_room_are_different_things(db, users):
    """할 말이 다르다 — 방을 확인하라고만 하면 명단이 빈 사람은 헤맨다."""
    from app.services import llm_brief

    _sheet(db, "투자사 풀")
    _contact(db, users["u1"].id, source_sheet="투자사 풀")   # 내 명단이 아니다

    picked = llm_brief.scope(db, users["u1"])
    assert picked["held"] == 0 and picked["empty"] is True
    assert "내 명단에 올라 있는 투자사가 없습니다" in picked["text"]
    assert "방 연결 확인" not in picked["text"], "없는 단추를 찾아 헤매게 됩니다"


def test_a_consultant_cannot_reach_either_address(db, users, people):
    """투자컨설턴트는 딜 소개를 보내지도, 담당 투자사를 갖지도 않는다.

    투자사의 선호·메모가 통째로 나가는 자료를 그 계정에 줄 이유가 없다.
    **따로 막지 않는다** — `deps.CONSULTANT_PATHS` 가 허용 목록이라 여기 적지
    않은 새 주소는 기본으로 막힌다. 그래서 이 검사는 **그 목록에 이 주소가
    없다는 사실**을 지킨다. 목록에 얹으면 여기가 빨개진다.
    """
    from fastapi.testclient import TestClient

    from app import deps
    from app.main import create_app

    assert not deps.consultant_may_open("/api/llm-brief.json")
    assert not deps.consultant_may_open("/api/llm-brief/resolve")

    client = TestClient(create_app())
    client.post("/login", data={"phone": "01000000072", "password": DEMO_PASSWORD})
    assert client.get("/api/llm-brief.json").status_code == 403
    assert client.post("/api/llm-brief/resolve",
                       json={"text": "V-1"}).status_code == 403


def test_a_visitor_who_is_not_logged_in_gets_nothing(client):
    assert client.get("/api/llm-brief.json").status_code == 401
    assert client.post("/api/llm-brief/resolve", json={"text": "V-1"}).status_code == 401


# ── 이미 보낸 기업 ──────────────────────────────────────────────────────────
#
# 맞추는 쪽이 제일 먼저 하는 일이 **이미 보낸 것을 빼는 것**이다. 이 자료가
# 틀리면 두 가지로 틀린다 — 안 보낸 것을 보냈다고 하면 멀쩡한 후보가 빠지고,
# 보낸 것을 빠뜨리면 지난달에 보낸 기업을 또 고른다.

def test_the_history_lists_what_was_already_sent_by_number(db, users):
    """이름을 또 적지 않는다 — **자료에 이미 있는 번호**로 가리킨다."""
    who = _contact(db, users["u1"].id, sectors="AI")
    first = _company(db, name="가상바이오")
    second = _company(db, name="가상로보틱스")
    _sent(db, who, [first, second])

    got = _brief(db, users["u1"])["investors"][0]
    assert sorted(got["sent_before"]) == sorted([f"C-{first.id}", f"C-{second.id}"])
    assert "sent_before_more" not in got


def test_an_investor_with_no_history_still_carries_an_empty_list(db, users):
    """칸이 없는 것과 '보낸 적 없다' 를 읽는 쪽이 구별할 길이 없다."""
    _contact(db, users["u1"].id, sectors="AI")
    _company(db)

    assert _brief(db, users["u1"])["investors"][0]["sent_before"] == []


def test_only_what_actually_went_out_counts_as_sent(db, users):
    """만들다 만 것·가는 중·실패·취소는 **보낸 것이 아니다.**

    안 나간 기업을 이력에 넣으면 LLM 이 멀쩡한 후보를 빼 버리고, 빠진 이유가
    자료 어디에도 안 보인다.
    """
    who = _contact(db, users["u1"].id, sectors="AI")
    sent = _company(db, name="가상바이오")
    _sent(db, who, [sent])
    for status in ("pending", "sending", "failed", "canceled"):
        _sent(db, who, [_company(db, name=f"가상{status}")], status=status)

    got = _brief(db, users["u1"])["investors"][0]["sent_before"]
    assert got == [f"C-{sent.id}"], "실제로 나간 것만 이력에 들어야 한다"


def test_a_send_that_never_reaches_an_investor_is_not_history(db, users):
    """시험 발송·스타트업 월간 발송도 `sent` 로 남는다 — 그러나 투자사에게
    보낸 것이 아니다. 세는 자리마다 따로 거르면 한 곳이 빠지므로
    `models.SEND_KINDS` 한 곳을 읽는다.
    """
    from app.models import SEND_KINDS, STARTUP_SEND_KIND, TEST_SEND_KIND

    who = _contact(db, users["u1"].id, sectors="AI")
    real = _company(db, name="가상바이오")
    _sent(db, who, [real], kind="deal_intro")
    for kind in (TEST_SEND_KIND, STARTUP_SEND_KIND, "verify_room"):
        assert kind not in SEND_KINDS, kind
        _sent(db, who, [_company(db, name=f"가상{kind}")], kind=kind)

    assert _brief(db, users["u1"])["investors"][0]["sent_before"] == [f"C-{real.id}"]


def test_a_company_no_longer_on_the_list_is_still_named_in_the_history(db, users):
    """옛 회차의 기업이 지금 목록에 없어도 **말없이 빠뜨리지 않는다.**

    조용히 빼면 LLM 이 '안 보낸 기업' 으로 읽고 다시 고른다. 번호만 실리므로
    목록에 없는 번호가 무엇인지는 자료의 `note` 가 말해 준다.
    """
    from app.routers.companies import BLOCKED_CONTRACT

    who = _contact(db, users["u1"].id, sectors="AI")
    gone = _company(db, name="가상소재", contract_status=BLOCKED_CONTRACT)
    _sent(db, who, [gone])

    out = _brief(db, users["u1"])
    assert f"C-{gone.id}" not in [c["id"] for c in out["companies"]]
    assert out["investors"][0]["sent_before"] == [f"C-{gone.id}"]
    assert "sent_before" in out["note"] and "이미 보낸" in out["note"]


def test_the_same_company_sent_twice_is_listed_once(db, users):
    who = _contact(db, users["u1"].id, sectors="AI")
    once = _company(db, name="가상바이오")
    _sent(db, who, [once])
    _sent(db, who, [once])

    assert _brief(db, users["u1"])["investors"][0]["sent_before"] == [f"C-{once.id}"]


def test_a_long_history_is_cut_and_says_so_in_the_data(db, users, monkeypatch):
    """조용히 자르면 읽는 쪽이 그게 전부인 줄 안다 — 자른 개수를 밝힌다."""
    from app.services import llm_brief

    monkeypatch.setattr(llm_brief, "HISTORY_LIMIT", 3)
    who = _contact(db, users["u1"].id, sectors="AI")
    for _ in range(5):
        _sent(db, who, [_company(db)])

    got = llm_brief.brief(db, users["u1"], now=FIXED_NOW)["investors"][0]
    assert len(got["sent_before"]) == 3
    assert got["sent_before_more"] == 2


def test_someone_elses_history_does_not_come_along(db, users):
    """이력도 자료와 **같은 모집단**이다 — 남의 담당은 줄 자체가 없다."""
    mine = _contact(db, users["u1"].id, sectors="AI")
    theirs = _contact(db, users["u2"].id, sectors="바이오")
    what = _company(db)
    _sent(db, theirs, [what])

    got = _brief(db, users["u1"])["investors"]
    assert [i["id"] for i in got] == [f"V-{mine.id}"]
    assert got[0]["sent_before"] == []


def test_the_history_carries_numbers_and_nothing_else(db, users):
    """**칸이 늘어도 이력으로는 새지 않는다.**

    담당자 줄과 기업 줄 양쪽에 표식을 심고, 이력이 실린 자료를 통째로 훑는다.
    회차 제목·문구 같은 자유 문장을 나중에 이력에 얹으면 여기서 걸린다.
    """
    from app.models import IrCompany, VcContact

    who = _contact(db, users["u1"].id, sectors="AI")
    what = _company(db, revenue_recent="18.3")
    _sent(db, who, [what])

    marks = _mark_every_other_column(VcContact, who, CONTACT_COLUMNS_ALLOWED_OUT,
                                     gate=GATE_COLUMNS)
    marks.update(_mark_every_other_column(IrCompany, what,
                                          COMPANY_COLUMNS_ALLOWED_OUT))
    db.commit()

    out = _brief(db, users["u1"])
    assert out["investors"][0]["sent_before"] == [f"C-{what.id}"], \
        "이력이 비면 이 검사는 아무것도 못 본다"
    dumped = json.dumps(out, ensure_ascii=False)
    leaked = sorted(name for name, mark in marks.items() if mark in dumped)
    assert not leaked, "자료에 이 칸이 새어 나갔습니다: " + ", ".join(leaked)


def test_the_history_also_reads_what_the_sheet_brought_over(db, users):
    """이력은 **두 곳**에 있다 — 이 시스템으로 보낸 회차와 시트에서 옮겨 온 기록.

    시스템으로 보내기 시작한 것이 최근이라 지난 것은 거의 다 시트 쪽에 있다.
    한쪽만 세면 대부분의 투자사가 "보낸 적 없음" 으로 나가고, 그건 사실이
    아니다(개발 자료로 274명 중 시스템 발송만으로는 5명, 둘을 합치면 125명).
    """
    who = _contact(db, users["u1"].id, sectors="AI")
    by_system = _company(db, name="가상바이오")
    by_sheet = _company(db, name="가상로보틱스")
    _sent(db, who, [by_system])
    _sheet_sent(db, who, ["가상로보틱스"])

    got = _brief(db, users["u1"])["investors"][0]["sent_before"]
    assert sorted(got) == sorted([f"C-{by_system.id}", f"C-{by_sheet.id}"])


def test_a_sheet_name_is_matched_the_same_way_the_rest_of_the_app_matches(db,
                                                                         users):
    """`(주)`·띄어쓰기 차이로 다른 기업이 되면 안 된다 — 규칙은 한 곳이다."""
    who = _contact(db, users["u1"].id, sectors="AI")
    what = _company(db, name="가상바이오")
    _sheet_sent(db, who, ["(주)가상바이오"])

    assert _brief(db, users["u1"])["investors"][0]["sent_before"] == [f"C-{what.id}"]


def test_a_name_that_cannot_be_matched_is_counted_not_dropped_and_not_named(db,
                                                                           users):
    """못 이은 이름을 조용히 버리면 읽는 쪽이 목록을 전부인 줄 안다.

    그렇다고 이름을 내보낼 수도 없다 — **몇 곳인지만** 밝힌다.
    """
    who = _contact(db, users["u1"].id, sectors="AI")
    known = _company(db, name="가상바이오")
    _sheet_sent(db, who, ["가상바이오", "이제는없는기업", "또없는기업"])

    out = _brief(db, users["u1"])
    got = out["investors"][0]
    assert got["sent_before"] == [f"C-{known.id}"]
    assert got["sent_before_unmatched"] == 2
    dumped = json.dumps(out, ensure_ascii=False)
    for gone in ("이제는없는기업", "또없는기업"):
        assert gone not in dumped, gone
    assert "sent_before_unmatched" in out["note"]


def test_nothing_unmatched_means_no_extra_key(db, users):
    who = _contact(db, users["u1"].id, sectors="AI")
    _sheet_sent(db, who, ["가상바이오"])
    _company(db, name="가상바이오")

    assert "sent_before_unmatched" not in _brief(db, users["u1"])["investors"][0]


def test_only_deal_intro_records_count_as_history(db, users):
    """`ir_request`·`meeting` 은 기업을 소개한 기록이 아니다."""
    who = _contact(db, users["u1"].id, sectors="AI")
    _company(db, name="가상바이오")
    from app.models import ContactActivity

    db.add(ContactActivity(contact_id=who.id, kind="ir_request", content="자료요청",
                           happened_at="2026-08-13",
                           company_names=json.dumps(["가상바이오"],
                                                    ensure_ascii=False)))
    db.commit()

    assert _brief(db, users["u1"])["investors"][0]["sent_before"] == []


# ── 그룹 ────────────────────────────────────────────────────────────────────
#
# 그룹은 **사람이 손으로 묶어 둔 갈래**이고, 딜 소개를 실제로 보낼 때 대상을
# 묶는 값이다(`deal_queue.targets` → `sheet_owner.in_group`). 그래서 자료에
# 실리는 것도, 답이 그 이름으로 돌아오는 것도 뜻이 있다.


def test_the_group_goes_out_with_each_investor(db, users):
    """그룹은 **분야·단계·규모가 비어 있는 자리를 메운다.**

    실측한 한 명단 117줄에서 `sectors` 21 · `round_size` 41 · `stages` 18 인데
    `group_name` 은 71이었다. 셋 다 빈 줄에도 그룹은 적혀 있는 경우가 많고,
    그때 그 줄에 대해 아는 것은 그룹뿐이다 — 안 실으면 그 사람은 자료 안에서
    아무 말도 안 하는 줄이 된다.
    """
    row = _contact(db, users["u1"].id, group_name="Series C 이상")

    got = _brief(db, users["u1"])["investors"][0]
    assert got["group_name"] == "Series C 이상"


def test_the_group_goes_out_exactly_as_written(db, users):
    """**모아 부르지 않는다** — `E그룹` 을 `E` 로 고치면 답을 받고도 못 보낸다.

    앱이 그룹으로 사람을 고르는 자(`sheet_owner.group_of`)는 앞뒤 공백만 뗀다.
    자료가 다른 글자로 나가면 LLM 이 그 이름으로 답해 와도 그 갈래로 묶인
    사람이 앱에는 없다.
    """
    from app.services import sheet_owner

    row = _contact(db, users["u1"].id, group_name="E그룹")

    got = _brief(db, users["u1"])["investors"][0]
    assert got["group_name"] == "E그룹"
    assert got["group_name"] == sheet_owner.group_of(row)


def test_an_investor_with_no_group_simply_has_no_group_column(db, users):
    """빈 그룹을 `정보 없음` 으로 지어 적지 않는다 — 다른 빈 칸과 같은 규칙이다.

    대신 **몇 명이 그런지는 갈래 표가 적는다**(아래 검사) — 조용히 사라지면
    읽는 쪽이 인원 합이 안 맞는 것을 알 길이 없다.
    """
    _contact(db, users["u1"].id, sectors="AI")

    assert "group_name" not in _brief(db, users["u1"])["investors"][0]


def test_the_data_carries_the_groups_and_how_many_are_in_each(db, users):
    """자리를 나누는 비례는 **인원**이다. 세는 일을 읽는 쪽에 떠넘기지 않는다.

    114줄을 세게 하면 틀리고, **틀린 비례로 나눈 답은 겉보기에 멀쩡하다.**
    """
    from app.services import llm_brief

    _contact(db, users["u1"].id, group_name="A")
    _contact(db, users["u1"].id, group_name="A")
    _contact(db, users["u1"].id, group_name="Pre IPO")

    got = _brief(db, users["u1"])[llm_brief.GROUPS_KEY]
    assert got == [
        {"name": "A", "count": 2, llm_brief.SENDABLE_KEY: 2},
        {"name": "Pre IPO", "count": 1, llm_brief.SENDABLE_KEY: 1}]


def test_the_ungrouped_are_counted_too_so_the_numbers_add_up(db, users):
    """안 묶인 사람도 갈래 표에 적는다 — 빼면 인원 합이 투자사 수와 안 맞는다.

    부르는 말은 **화면의 칩이 쓰는 그 말**이어야 한다(`sheet_owner.EMPTY_GROUP`).
    자료가 다른 말로 적으면 답을 보고 화면에서 그 갈래를 찾을 수 없다.
    """
    from app.services import llm_brief, sheet_owner

    _contact(db, users["u1"].id, group_name="A")
    _contact(db, users["u1"].id)
    _contact(db, users["u1"].id, group_name="   ")

    out = _brief(db, users["u1"])
    rows = out[llm_brief.GROUPS_KEY]
    assert rows[-1] == {"name": sheet_owner.EMPTY_GROUP, "count": 2,
                        llm_brief.SENDABLE_KEY: 2}
    assert sum(g["count"] for g in rows) == len(out["investors"])


def test_the_group_count_is_the_one_the_deal_screen_uses(db, users):
    """세는 자를 **여기서 다시 짓지 않는다** — 화면·발송이 쓰는 그 함수다.

    두 벌로 세면 자료의 인원과 딜 제안 관리의 그룹 칩이 갈리고, 갈린 수로 나눈
    자리는 보낼 때 안 맞는다(투자사 수가 117명·123명으로 갈렸던 그 사고다).
    """
    from app.services import llm_brief, sheet_owner

    _contact(db, users["u1"].id, group_name="A")
    _contact(db, users["u1"].id, group_name="B")
    _contact(db, users["u1"].id)

    rows = llm_brief.investor_rows(db, users["u1"])
    assert [(g["name"], g["count"])
            for g in _brief(db, users["u1"])[llm_brief.GROUPS_KEY]] == [
        (g["label"], g["count"]) for g in sheet_owner.group_rows(rows)]


def test_the_groups_only_count_who_is_actually_in_the_data(db, users):
    """**담기지 않은 사람 몫으로 자리를 나누면 그 자리는 아무에게도 안 간다.**

    방이 확인되지 않은 줄은 자료에 안 담긴다(`investor_rows`). 갈래 표도 같은
    모집단이어야 한다.
    """
    from app.services import llm_brief

    _contact(db, users["u1"].id, group_name="A")
    _contact(db, users["u1"].id, group_name="A", room_verified="unverified")

    out = _brief(db, users["u1"])
    assert out[llm_brief.GROUPS_KEY] == [
        {"name": "A", "count": 1, llm_brief.SENDABLE_KEY: 1}]
    assert len(out["investors"]) == 1


def test_the_note_says_how_to_read_a_group(db, users):
    """읽는 법이 없으면 그룹은 그냥 한 칸으로 보이고 그대로 지나간다."""
    from app.services import llm_brief

    got = _brief(db, users["u1"])["note"]
    assert "group_name" in got
    assert llm_brief.GROUPS_KEY in got
    # 안 묶인 사람을 부르는 말이 화면과 같아야 한다.
    assert llm_brief.sheet_owner.EMPTY_GROUP in got
    # 모아 부르지 말라는 못 — 이게 빠지면 `E그룹` 이 `E` 로 돌아온다.
    assert "그대로" in got


def test_the_prompt_picks_per_group_because_sending_is_per_group(db, users):
    """**발송 단위가 곧 고르는 단위다.**

    사용자가 그룹별로 따로 발송하기로 정했다. 그러면 한 벌을 먼저 정하고 "이 중
    어느 것이 이 갈래에 맞는지" 를 덧붙이게 하는 것은 손해다 — 그 갈래에 딱
    맞는데 한 벌에 못 든 기업은 보일 기회조차 없다.
    """
    from app.services import llm_brief

    got = _brief(db, users["u1"])["prompt"]
    assert "group_name" in got
    assert llm_brief.GROUPS_KEY in got
    # 갈래마다 한 벌 — 전원에게 보낼 한 벌이 아니다.
    assert "갈래마다" in got
    # 뜻을 지어내지 말라는 못 — `A` 를 무슨 뜻으로 읽고 고르면 그 답은
    # 겉보기에 멀쩡하다.
    assert "지어내지" in got


def test_the_groups_key_is_written_in_exactly_one_place(db, users):
    """칸 이름을 세 곳(읽는 법·시킬 말·자료)에 손으로 적으면 두 곳이 낡는다."""
    from app.services import llm_brief

    llm_brief.GROUPS_KEY = "갈래표시험"
    try:
        out = _brief(db, users["u1"])
        assert "갈래표시험" in out
        assert "갈래표시험" in out["note"]
        assert "갈래표시험" in out["prompt"]
    finally:
        llm_brief.GROUPS_KEY = "groups"


# ── 보낼 수 있는 갈래인가 ──────────────────────────────────────────────────
#
# 딜 소개를 멈춰 둔 분(`검토중단`)만 모인 갈래가 실제로 있다. 그 갈래에 기업을
# 뽑으면 **뽑은 것이 갈 데가 없다.** 갈래 이름으로 거르지 않고 **보낼 수 있는
# 인원이 0인지**로 가른다 — 이름은 사람이 바꾸고, 바뀌면 그 문장만 옛말이 된다.


def test_a_group_nobody_can_be_sent_to_says_so_with_a_zero(db, users):
    """`count` 는 그대로 두고 `SENDABLE_KEY` 만 0이 된다.

    **줄을 지우지 않는다.** 앱이 갈래를 통째로 감추면 사람은 그 갈래가 왜 없는지
    알 길이 없다 — 세어서 밝히고, 건너뛸지는 시킬 말이 정한다.
    """
    from app.services import llm_brief, sheet_owner

    _contact(db, users["u1"].id, group_name="보류시험",
             status=sheet_owner.STATUS_PAUSED)
    _contact(db, users["u1"].id, group_name="보류시험",
             status=sheet_owner.STATUS_PAUSED)
    _contact(db, users["u1"].id, group_name="살아있음시험")

    out = _brief(db, users["u1"])
    got = {g["name"]: g for g in out[llm_brief.GROUPS_KEY]}
    assert got["보류시험"]["count"] == 2
    assert got["보류시험"][llm_brief.SENDABLE_KEY] == 0
    assert got["살아있음시험"][llm_brief.SENDABLE_KEY] == 1
    # 멈춰 둔 분도 **자료에는 그대로 담긴다** — 적어 둔 분야·단계는 여전히
    # 사실이고, 한 갈래에 섞여 있는 경우가 있다.
    assert len(out["investors"]) == 3


def test_a_paused_person_only_drops_out_of_the_sendable_count(db, users):
    """한 갈래에 멈춘 분과 안 멈춘 분이 **섞여 있는** 경우가 실제로 있다.

    그 갈래는 건너뛰면 안 된다 — 보낼 분이 남아 있다.
    """
    from app.services import llm_brief, sheet_owner

    _contact(db, users["u1"].id, group_name="섞임시험")
    _contact(db, users["u1"].id, group_name="섞임시험",
             status=sheet_owner.STATUS_PAUSED)

    got = _brief(db, users["u1"])[llm_brief.GROUPS_KEY][0]
    assert got == {"name": "섞임시험", "count": 2, llm_brief.SENDABLE_KEY: 1}


def test_the_sendable_count_is_the_one_the_send_screen_uses(db, users):
    """판정을 **여기서 새로 적지 않는다** — 딜 제안 관리가 대상을 고르는 그것이다.

    `can_send_to` 는 문이 둘이다(연결이 끝났는가 · 멈춰 두지 않았는가). 여기에
    `status != paused` 라고 다시 적으면 문이 하나 늘 때 이 줄만 낡는다.
    """
    from app.services import llm_brief, sheet_owner

    _contact(db, users["u1"].id, group_name="A")
    _contact(db, users["u1"].id, group_name="A",
             status=sheet_owner.STATUS_PAUSED)
    _contact(db, users["u1"].id, group_name="B")

    rows = llm_brief.investor_rows(db, users["u1"])
    want = {}
    for c in rows:
        if sheet_owner.can_send_to(c):
            want[sheet_owner.group_of(c)] = want.get(sheet_owner.group_of(c), 0) + 1
    assert {g["name"]: g[llm_brief.SENDABLE_KEY]
            for g in llm_brief.groups(db, users["u1"])} == want


def test_the_note_says_what_the_sendable_count_means(db, users):
    """이 말이 없으면 읽는 쪽이 `count` 만 보고 멈춰 둔 갈래에도 기업을 뽑는다."""
    from app.services import llm_brief, sheet_owner

    got = _brief(db, users["u1"])["note"]
    assert llm_brief.SENDABLE_KEY in got
    # 부르는 말은 화면이 그 상태를 부르는 말과 같아야 한다.
    assert sheet_owner.STATUS_LABELS[sheet_owner.STATUS_PAUSED] in got


def test_the_prompt_skips_a_group_by_the_number_not_by_its_name(db, users):
    """**갈래 이름을 시킬 말에 적어 두지 않는다.**

    "`딜 소개 보류` 갈래를 빼라" 고 이름으로 적으면, 사람이 그 이름을 바꾸는 날
    이 문장만 옛말이 되고 같은 뜻의 다른 이름이 생기면 안 걸린다.
    """
    from app.services import llm_brief

    got = _brief(db, users["u1"])["prompt"]
    assert llm_brief.SENDABLE_KEY in got and "건너뛰" in got
    assert "보류" not in got


def test_the_sendable_key_is_written_in_exactly_one_place(db, users):
    """칸 이름을 읽는 법·시킬 말·자료 셋에 손으로 적으면 두 곳이 낡는다."""
    from app.services import llm_brief

    llm_brief.SENDABLE_KEY = "보낼수있는인원시험"
    try:
        out = _brief(db, users["u1"])
        assert "보낼수있는인원시험" in out["note"]
        assert "보낼수있는인원시험" in out["prompt"]
        _contact(db, users["u1"].id, group_name="A")
        assert "보낼수있는인원시험" in _brief(db, users["u1"])[
            llm_brief.GROUPS_KEY][0]
    finally:
        llm_brief.SENDABLE_KEY = "sendable"


# ── 많아야 여덟, 맞는 것만 ─────────────────────────────────────────────────
#
# 사용자가 정한 것이다 — "기업이 8개가 안 되는 경우라면 보낼 수 있는 기업만이라도
# 리스트업해서 보낼 수 있음." 수를 채우려고 안 맞는 곳을 끼워 넣으면 받는 분이
# 다음부터 안 본다.


def test_the_prompt_says_the_number_is_a_ceiling_not_a_quota(db, users):
    """**"8곳을 고르라" 가 아니라 "많아야 8곳, 맞는 것만" 이어야 한다.**"""
    from app.services.llm_brief import PICK_COUNT

    got = _brief(db, users["u1"])["prompt"]
    assert f"많아야 기업 {PICK_COUNT}곳" in got
    assert f"{PICK_COUNT}곳은 채워야 하는 수가 아니라" in got
    assert "끼워 넣지 마세요" in got


def test_the_prompt_says_what_to_answer_when_nothing_fits(db, users):
    """0곳이어도 된다 — 다만 **줄은 남겨야** 빠뜨린 것과 구별된다."""
    from app.services.llm_brief import EMPTY_PICK_ANSWER

    got = _brief(db, users["u1"])["prompt"]
    assert EMPTY_PICK_ANSWER in got
    assert "억지로 만들지" in got
    assert "0곳" in got


def test_the_prompt_lets_one_company_land_in_several_groups(db, users):
    """겹침을 막으면 **어느 갈래를 먼저 채우느냐로 답이 달라진다.**

    나중 갈래는 남은 것 중에서 고르느라 더 안 맞는 곳을 받는다. 한 사람은 한
    갈래에만 속하므로(`sheet_owner.group_of` 가 한 값이다) 같은 기업을 두 번
    받는 일도 없다.
    """
    got = _brief(db, users["u1"])["prompt"]
    assert "겹쳐 나와도 됩니다" in got


def test_the_answer_example_carries_the_group_and_how_many(db, users):
    """답이 **어느 갈래의 몫인지**를 싣고 와야 사람이 그대로 발송으로 옮긴다.

    개수까지 적게 하는 것은 갈래마다 수가 다른 것이 정상이기 때문이다 —
    그 수가 보여야 "왜 이 갈래만 2곳이지" 를 바로 짚는다.
    """
    from app.services.llm_brief import ANSWER_EXAMPLE, COMPANY_PREFIX

    assert ":" in ANSWER_EXAMPLE
    assert "곳" in ANSWER_EXAMPLE
    assert f"{COMPANY_PREFIX}-" in ANSWER_EXAMPLE
    assert ANSWER_EXAMPLE in _brief(db, users["u1"])["prompt"]


# ── 갈래별로 온 답을 가른다 ────────────────────────────────────────────────
#
# 답도 갈래마다 한 줄씩 온다. 번호만 훑어 한 덩어리로 돌려주면 사람이 그것을
# 다시 갈래로 갈라야 하고, 갈래가 아홉이면 아홉 번이다.


def _picks(text, names):
    from app.services import llm_brief

    return llm_brief.parse_group_refs(text, names)


def test_an_answer_written_per_group_is_split_per_group():
    assert _picks("공통 (2곳): C-7, C-12\nSeed (1곳): C-30",
                  ["공통", "Seed"]) == [
        {"name": "공통", "companies": [7, 12]},
        {"name": "Seed", "companies": [30]}]


def test_a_bulleted_or_bolded_group_line_is_still_a_group_line():
    """사람이 붙여 넣는 답은 목록 모양으로 오는 일이 흔하다."""
    for written in ("- 공통: C-7", "* **공통**: C-7", "1. 공통 (1곳): C-7",
                    "## 공통：C-7"):
        assert _picks(written, ["공통"]) == [
            {"name": "공통", "companies": [7]}], written


def test_the_longest_group_name_wins():
    """`Series C` 가 먼저 걸리면 `Series C 이상` 은 영영 안 잡힌다."""
    got = _picks("Series C 이상: C-7", ["Series C", "Series C 이상"])
    assert got == [{"name": "Series C 이상", "companies": [7]}]


def test_a_one_letter_group_does_not_swallow_an_ordinary_line():
    """한 글자 갈래(`A`·`B`·`E`)가 실제로 있다 — `AI 분야:` 를 잡으면 안 된다."""
    assert _picks("AI 분야: C-7", ["A"]) == []


def test_a_heading_that_is_not_a_group_is_not_invented():
    """답에 적힌 소제목(`후보`·`제외`)을 갈래로 읽으면 화면에 없는 갈래가 뜬다."""
    assert _picks("후보: C-7", ["공통"]) == []


def test_numbers_before_the_first_group_line_belong_to_no_group():
    """첫머리 요약에 섞인 번호를 첫 갈래에 붙이면, 그 갈래가 고르지도 않은
    기업을 받는다."""
    got = _picks("모두 12곳을 골랐습니다(C-9 제외).\n공통: C-7", ["공통"])
    assert got == [{"name": "공통", "companies": [7]}]


def test_the_same_company_may_appear_in_two_groups():
    """겹쳐도 된다고 시킨 것이 시킬 말이다 — 읽는 쪽이 지우면 안 된다."""
    got = _picks("공통: C-7\n딥테크: C-7", ["공통", "딥테크"])
    assert got == [{"name": "공통", "companies": [7]},
                   {"name": "딥테크", "companies": [7]}]


def test_the_same_group_written_twice_is_one_group():
    got = _picks("공통: C-7\n공통: C-7, C-12", ["공통"])
    assert got == [{"name": "공통", "companies": [7, 12]}]


def test_a_group_with_nothing_that_fits_keeps_its_line(db, users):
    """0곳도 **줄이 남아야** 빠뜨린 것과 구별된다."""
    from app.services.llm_brief import EMPTY_PICK_ANSWER

    got = _picks(f"공통: C-7\nSeed (0곳): {EMPTY_PICK_ANSWER}",
                 ["공통", "Seed"])
    assert got == [{"name": "공통", "companies": [7]},
                   {"name": "Seed", "companies": []}]


def test_an_investor_number_on_a_group_line_is_not_a_pick():
    """갈래가 고른 것은 **기업**이다. 투자사 번호가 섞여 와도 그 자리에 안 든다."""
    got = _picks("공통: V-31 님 몫으로 C-7", ["공통"])
    assert got == [{"name": "공통", "companies": [7]}]


def test_the_lines_under_a_group_line_belong_to_that_group():
    """고른 까닭을 아래 줄에 적는 일이 흔하다 — 그 줄의 번호도 그 갈래 것이다."""
    got = _picks("공통 (2곳):\n  - C-7 매출이 기준을 넘습니다\n  - C-12\n"
                 "Seed (1곳): C-30", ["공통", "Seed"])
    assert got == [{"name": "공통", "companies": [7, 12]},
                   {"name": "Seed", "companies": [30]}]


def test_the_group_names_come_from_the_data_not_from_the_answer(db, users):
    """되돌릴 때 쓰는 갈래 이름은 **자료에 실어 보낸 그 이름들**이다."""
    from app.services import llm_brief

    _contact(db, users["u1"].id, group_name="E그룹")
    what = _company(db, name="가상바이오")

    got = llm_brief.resolve(db, users["u1"],
                            f"E그룹 (1곳): C-{what.id}\n후보: C-{what.id}")
    assert [g["name"] for g in got[llm_brief.GROUPS_KEY]] == ["E그룹"]


def test_the_resolved_answer_says_which_group_each_company_is_for(db, users):
    """이 길이 없으면 사람이 아홉 갈래를 손으로 다시 갈라야 한다."""
    from app.services import llm_brief

    _contact(db, users["u1"].id, group_name="공통")
    _contact(db, users["u1"].id, group_name="Seed")
    one = _company(db, name="가상바이오")
    two = _company(db, name="가상소재")

    got = llm_brief.resolve(
        db, users["u1"],
        f"공통 (2곳): C-{one.id}, C-{two.id}\nSeed (1곳): C-{one.id}")
    assert got[llm_brief.GROUPS_KEY] == [
        {"name": "공통", "companies": [
            {"id": f"C-{one.id}", "found": True, "name": "가상바이오",
             "href": f"/companies?q=%EA%B0%80%EC%83%81%EB%B0%94%EC%9D%B4%EC%98%A4"},
            {"id": f"C-{two.id}", "found": True, "name": "가상소재",
             "href": got["companies"][1]["href"]}]},
        {"name": "Seed", "companies": [
            {"id": f"C-{one.id}", "found": True, "name": "가상바이오",
             "href": got["companies"][0]["href"]}]}]
    # 전체 목록은 **그대로 남는다** — 갈래 머리가 없는 답도 읽혀야 한다.
    assert [c["id"] for c in got["companies"]] == [f"C-{one.id}", f"C-{two.id}"]


def test_an_answer_without_group_lines_still_resolves(db, users):
    """갈래 머리가 없는 답(옛 모양)도 그대로 읽혀야 한다."""
    from app.services import llm_brief

    _contact(db, users["u1"].id, group_name="공통")
    what = _company(db, name="가상바이오")

    got = llm_brief.resolve(db, users["u1"], f"C-{what.id} 를 추천합니다")
    assert got[llm_brief.GROUPS_KEY] == []
    assert got["companies"][0]["name"] == "가상바이오"


def test_a_number_in_a_group_line_that_is_not_in_the_data_is_still_shown(db,
                                                                        users):
    """조용히 빠지면 다섯을 넣고 셋만 뜬 것을 눈치채지 못한다 — 갈래 안도 같다."""
    from app.services import llm_brief

    _contact(db, users["u1"].id, group_name="공통")

    got = llm_brief.resolve(db, users["u1"], "공통 (1곳): C-9999")
    assert got[llm_brief.GROUPS_KEY] == [
        {"name": "공통", "companies": [
            {"id": "C-9999", "found": False, "name": "", "href": ""}]}]


# ── 시킬 말 ────────────────────────────────────────────────────────────────

def test_the_prompt_says_to_exclude_what_was_sent_and_to_answer_in_numbers(db,
                                                                          users):
    """사용자가 청한 세 가지가 다 들어 있어야 한다 —
    이미 보낸 것 빼기 · 성향 보기 · 몇 곳을 고를지, 그리고 **번호로 답하기.**
    """
    from app.services.llm_brief import ANSWER_EXAMPLE, PICK_COUNT

    got = _brief(db, users["u1"])["prompt"]
    assert "sent_before" in got and "빼" in got
    for preference in ("sectors", "stages", "round_size", "memo"):
        assert preference in got, preference
    assert f"{PICK_COUNT}곳" in got
    # 번호로 답해 달라는 요구가 없으면 [번호 → 이름 찾기] 가 못 읽는다.
    assert "번호로" in got
    assert ANSWER_EXAMPLE in got


def test_the_number_to_pick_is_written_in_exactly_one_place(db, users):
    """`8` 을 여기저기 적어 두면 한 곳만 고쳐진다 — 값을 바꿔 보고 따라오는지 본다."""
    from app.services import llm_brief

    before = llm_brief.prompt()
    assert "8곳" in before

    llm_brief.PICK_COUNT = 5
    try:
        after = llm_brief.prompt()
    finally:
        llm_brief.PICK_COUNT = 8
    assert "5곳" in after and "8곳" not in after


def test_the_prompt_is_not_per_investor_and_not_one_set_for_everyone(db, users):
    """**시킬 말이 실제 운영과 같은 것을 시켜야 한다.**

    이 자리가 두 번 틀렸다. ① "투자사마다 기업 8곳" — 114곳이면 912 짝이고
    그중 아무것도 쓰이지 않았다. ② "이번 주 8개사를 전원에게" — 그때는 맞았지만
    사용자가 **그룹별로 따로 발송**하기로 전제를 바꿨다. 둘 다 남아 있으면 안
    된다 — 남으면 다음 사람이 읽고 되돌린다.
    """
    from app.services.llm_brief import PICK_COUNT

    got = _brief(db, users["u1"])["prompt"]
    assert f"투자사마다 기업 {PICK_COUNT}곳" not in got
    assert f"{PICK_COUNT}곳 한 벌" not in got
    assert "전원에게 보낼" not in got


def test_the_prompt_reads_the_free_text_of_the_group_members(db, users):
    """갈래가 무엇을 원하는지는 **속한 분들이 적어 둔 말**에서 나온다.

    갈래 이름만 읽으라고 하면 `A`·`B` 처럼 글자뿐인 갈래에서 아무것도 못 읽는다.
    """
    got = _brief(db, users["u1"])["prompt"]
    # 무엇을 읽고 세는지가 적혀 있어야 한다.
    for field in ("sectors", "stages", "round_size", "memo"):
        assert field in got, field
    # 한 갈래 안에서도 많이 청한 쪽에 자리를 더 준다.
    assert "많이 청한" in got


def test_the_prompt_makes_the_counting_use_the_names_that_are_in_the_data(db,
                                                                         users):
    """**세는 이름이 기업 값과 같아야 한다** — 다르면 수요가 통째로 사라진다.

    사람이 손으로 해 보다 실제로 당한 자리다: `AI`·`로보틱스` 로 셌는데 기업
    값은 `AI·SaaS·데이터` 였고 `로보틱스` 라는 분야는 아예 없어서(로봇은
    `딥테크·제조` 에 든다) 그 수요가 한 곳도 안 걸렸다.
    """
    got = _brief(db, users["u1"])["prompt"]
    assert "sector_names" in got
    assert "없는 이름" in got or "거기 없는" in got


def test_the_data_carries_the_sector_names_so_the_counting_can_land(db, users):
    """세라고 시키려면 **셀 눈금이 자료 안에** 있어야 한다.

    앱이 하는 일은 여기까지다 — 이름을 꺼내는 것은 자료를 꺼내는 일이고,
    세는 것은 판단이라 LLM 이 한다(`services/llm_brief.py` 머리말).
    """
    _company(db, sector_major="딥테크·제조")
    _company(db, sector_major="AI·SaaS·데이터")
    _company(db, sector_major="딥테크·제조")
    _company(db, sector_major=None)

    got = _brief(db, users["u1"])["sector_names"]
    assert got == ["AI·SaaS·데이터", "딥테크·제조"]
    # **이름만이다.** 개수·순위가 붙으면 앱이 먼저 추린 것이 되고, 앱이 추린
    # 것은 LLM 이 볼 수조차 없다.
    assert all(isinstance(v, str) for v in got)


def test_a_sector_that_is_not_in_the_data_is_not_in_the_name_list(db, users):
    """목록과 줄이 갈리면 **자료에 없는 분야로 수요를 세게 된다.**

    `딜소개 불가` 로 빠진 기업의 분야가 목록에만 남으면, 그 분야로 나눈 자리를
    채울 기업이 자료 안에 하나도 없다.
    """
    from app.routers.companies import BLOCKED_CONTRACT

    _company(db, sector_major="딥테크·제조")
    _company(db, sector_major="보낼수없는분야", contract_status=BLOCKED_CONTRACT)

    out = _brief(db, users["u1"])
    assert out["sector_names"] == ["딥테크·제조"]
    # 자료에 실린 줄에서 꺼낸 것이라 둘이 갈릴 수 없다.
    assert set(out["sector_names"]) == {c["sector_major"]
                                        for c in out["companies"]
                                        if c.get("sector_major")}


def test_the_prompt_prefers_the_revenue_line_without_dropping_early_companies(
        db, users):
    """사용자 요구는 **고르는 말**이지 거르는 말이 아니다.

    "5억 미만은 무조건 빼라" 로 적으면 초기 기업을 찾는 투자사의 수요가 통째로
    죽는다 — `stages` 에 `Seed`·`Pre-seed` 가 적힌 곳이 실제로 있고, 그
    사람들에게 보낼 것이 자료에서 사라진다.
    """
    from app.services.llm_brief import OVER_NO, OVER_UNKNOWN, OVER_YES

    got = _brief(db, users["u1"])["prompt"]
    assert "revenue_over" in got and OVER_YES in got
    # 무조건 빼라는 말이 **아니라는 것**이 적혀 있어야 한다.
    assert OVER_NO in got and OVER_UNKNOWN in got
    assert "아닙니다" in got
    assert "Seed" in got


def test_the_prompt_is_built_in_the_service_and_nowhere_else(logged_in):
    """화면과 API 가 각자 문장을 들고 있으면 반드시 갈린다.

    화면이 부르는 자료 안에 시킬 말이 실려 있고, 템플릿·스크립트에는 그 문장이
    없어야 한다 — 스크립트는 받은 것을 앞에 붙이기만 한다.
    """
    from app.services import llm_brief

    sentence = llm_brief.prompt().splitlines()[0]
    assert sentence and sentence in logged_in.get("/api/llm-brief.json").text

    for path in (Path("app/templates/deals.html"),
                 Path("app/static/js/llm_brief.js")):
        src = (Path(__file__).resolve().parent.parent / path).read_text(
            encoding="utf-8")
        assert sentence not in src, f"{path} 가 시킬 말을 따로 들고 있습니다"
    # 스크립트는 서버가 보낸 것을 읽기만 한다.
    js = (Path(__file__).resolve().parent.parent
          / "app" / "static" / "js" / "llm_brief.js").read_text(encoding="utf-8")
    assert "data.prompt" in js


def test_the_answer_example_is_the_same_as_the_paste_box_placeholder(logged_in):
    """사람이 보는 예시와 LLM 이 받은 지시가 다르면, 못 읽는 모양으로 답이 온다."""
    from app.services.llm_brief import ANSWER_EXAMPLE

    assert ANSWER_EXAMPLE in logged_in.get("/deals").text


# ── 번호를 다시 이름으로 ────────────────────────────────────────────────────

def _resolve(db, user, text):
    from app.services import llm_brief

    return llm_brief.resolve(db, user, text)


def test_a_pasted_answer_says_who_the_numbers_are(db, users):
    """이 길이 없으면 번호로 내보내는 기능은 반쪽이다."""
    who = _contact(db, users["u1"].id, name="홍길동", firm="가나벤처스")
    what = _company(db, name="가상바이오")

    got = _resolve(db, users["u1"],
                   f"V-{who.id} 님께는 C-{what.id} 를 소개하시면 좋겠습니다.")
    assert got["investors"] == [{
        "id": f"V-{who.id}", "found": True, "name": "홍길동",
        "firm": "가나벤처스", "href": f"/contacts?contact={who.id}"}]
    assert got["companies"][0]["name"] == "가상바이오"
    assert got["companies"][0]["href"].startswith("/companies?q=")


def test_padding_spacing_and_case_do_not_matter(db, users):
    """LLM 이 `V-031` 로 답해 와도 찾아야 한다 — 내보낼 때는 자릿수를 안 채운다."""
    who = _contact(db, users["u1"].id)
    assert who.id == 1, "이 검사는 한 자리 번호를 전제로 한다"

    for written in ("V-1", "V-001", "v-1", "V - 1", "투자사 V-0001 추천"):
        got = _resolve(db, users["u1"], written)
        assert [i["id"] for i in got["investors"]] == ["V-1"], written


def test_a_bare_number_is_not_read_as_a_reference(db, users):
    """답에는 `30억`·`3곳`·`2026년` 이 널려 있다.

    그것까지 번호로 읽으면 엉뚱한 사람이 목록에 뜨고, 그 목록은 겉보기에
    멀쩡하다 — 틀린 것을 알아채기 어려운 쪽이 나쁘다.
    """
    _contact(db, users["u1"].id)
    _company(db)

    from app.services import llm_brief

    got = _resolve(db, users["u1"], "1번 투자사에게 30억 규모로 3곳을 2026년에")
    assert got == {"investors": [], "companies": [],
                   llm_brief.GROUPS_KEY: []}


def test_the_same_number_twice_is_listed_once(db, users):
    who = _contact(db, users["u1"].id)
    got = _resolve(db, users["u1"], f"V-{who.id} · 다시 V-{who.id}")
    assert [i["id"] for i in got["investors"]] == [f"V-{who.id}"]


def test_someone_elses_contact_does_not_get_a_name(db, users):
    """번호만 바꿔 넣어 남의 담당을 알아내는 길이 되면 안 된다.

    애초에 내보낸 적 없는 번호가 이름을 돌려주면 그것도 유출이다 — 찾는
    범위를 자료를 꺼낼 때와 같게 둔 이유다.
    """
    theirs = _contact(db, users["u2"].id, name="홍길동", firm="가나벤처스")

    got = _resolve(db, users["u1"], f"V-{theirs.id}")
    assert got["investors"] == [{"id": f"V-{theirs.id}", "found": False,
                                 "name": "", "firm": "", "href": ""}]
    assert "홍길동" not in json.dumps(got, ensure_ascii=False)


def test_a_number_that_is_not_found_is_reported_not_dropped(db, users):
    """조용히 빠지면 다섯을 붙여 넣고 셋만 뜬 것을 눈치채지 못한다."""
    who = _contact(db, users["u1"].id)

    got = _resolve(db, users["u1"], f"V-{who.id} 와 V-9999")
    assert [(i["id"], i["found"]) for i in got["investors"]] == [
        (f"V-{who.id}", True), ("V-9999", False)]


def test_an_admin_does_not_resolve_across_the_team_either(db, users, people):
    """관리자에게도 자기 담당분만 나가므로 되돌리는 범위도 같다."""
    theirs = _contact(db, users["u2"].id, name="홍길동")

    got = _resolve(db, people["admin"], f"V-{theirs.id}")
    assert got["investors"][0]["found"] is False
    assert "홍길동" not in json.dumps(got, ensure_ascii=False)


def test_the_data_and_the_lookup_share_one_population(db, users, people):
    """**자료에 담긴 번호는 반드시 되찾아지고, 안 담긴 번호는 되찾히면 안 된다.**

    둘이 갈리는 방향이 둘 다 사고다 — 안 담긴 번호가 이름을 돌려주면 번호만
    바꿔 넣어 남의 담당·방이 막힌 곳을 알아내는 길이 되고, 담긴 번호가 안
    찾아지면 답을 받아도 쓸 수가 없다. 그래서 같은 함수 하나를 부른다.

    **모집단이 둘로 갈리면 여기가 깨진다.**
    """
    _sheet(db, "투자사 풀")

    rows = [
        _contact(db, users["u1"].id),                              # 담긴다
        _contact(db, users["u1"].id, room_verified="not_found"),   # 방이 막혔다
        _contact(db, users["u1"].id, kakao_room_name=""),          # 방 미등록
        _contact(db, users["u1"].id, source_sheet="투자사 풀"),      # 내 명단이 아니다
        _contact(db, users["u2"].id),                              # 남의 계정
        _contact(db, people["admin"].id),                          # 관리자 계정
    ]
    in_data = {c["id"] for c in _brief(db, users["u1"])["investors"]}
    got = _resolve(db, users["u1"],
                   " ".join(f"V-{row.id}" for row in rows))
    found = {item["id"] for item in got["investors"] if item["found"]}

    assert found == in_data
    # 다 담기거나 다 빠지면 검사가 아무것도 안 본 것이다.
    assert 0 < len(in_data) < len(rows)


# ── 화면 단추와 API 가 갈리지 않는가 ────────────────────────────────────────

JS = Path(__file__).resolve().parent.parent / "app" / "static" / "js" / "llm_brief.js"
JS_TEST = Path(__file__).resolve().parent / "js" / "llm_brief_test.js"


def _registered_paths():
    from app.main import create_app

    return {getattr(route, "path", "") for route in create_app().routes}


def test_the_screen_button_is_the_api_address_itself(logged_in):
    """단추가 부르는 곳과 API 가 **같은 주소**여야 한다.

    화면용 경로를 따로 두면 한쪽이 낡는다 — 이 저장소가 반복해 당한 사고다
    (좌측 메뉴 목록과 라우터 목록이 갈려 컨설턴트에게 다 열려 있던 일).
    링크에 적힌 주소가 실제로 앱에 등록된 라우트인지까지 본다: 주소를 고치면
    한쪽만 고쳐진 채로는 이 검사를 지날 수 없다.
    """
    body = logged_in.get("/deals").text
    assert 'href="/api/llm-brief.json"' in body
    assert "/api/llm-brief.json" in _registered_paths()
    # 화면에서 자료를 그리는 스크립트도 같이 실려야 한다.
    assert "js/llm_brief.js" in body


def test_the_browser_script_calls_only_registered_addresses(logged_in):
    """스크립트가 부르는 주소도 앱에 있는 것이어야 한다.

    브라우저 쪽은 주소가 틀려도 화면이 조용히 비어 있을 뿐이라 눈에 안 띈다.
    """
    src = JS.read_text(encoding="utf-8")
    paths = _registered_paths()
    assert "/api/llm-brief/resolve" in src
    assert "/api/llm-brief/resolve" in paths
    # 자료를 꺼내는 주소는 **내려받기 링크에서 읽어 온다** — 스크립트가 주소를
    # 또 적어 두면 링크만 고쳐졌을 때 둘이 갈린다.
    assert 'download && download.getAttribute("href")' in src


@pytest.mark.skipif(shutil.which("node") is None,
                    reason="node 미설치 — 브라우저 로직 테스트 생략 "
                           "(호스트에서 `node tests/js/llm_brief_test.js`)")
def test_the_panel_really_fetches_and_resolves():
    """화면 로직은 브라우저에 있으므로 검사도 같은 언어로 둔다.

    `<script>` 태그가 그려지는지만 보는 검사로는 [화면에서 보기] 가 엉뚱한
    주소를 부르거나 결과를 안 그리는 것을 못 잡는다.
    """
    result = subprocess.run([shutil.which("node"), str(JS_TEST)],
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
