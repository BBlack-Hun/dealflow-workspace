"""스타트업DB 칸 → `기업 한줄 소개` 자동 조합.

시트를 쓰던 사람은 스타트업DB 탭에 값을 넣는데, 정작 딜소개에 쓰이는 것은 옆
탭의 `한줄 소개` 한 칸이라 같은 내용을 두 번 적고 있었다. 이 검사는 그 조합이
**실데이터의 표기 그대로** 나오는지, 그리고 **사람이 쓴 소개를 지우지 않는지**를
지킨다.

기대값의 표기(`누적투자금액 N억` · `N억 투자유치중` · `Pre Value N억`)는 지어낸
것이 아니라 344행에서 가장 많이 쓰인 모양을 세어 뽑은 것이다 —
`app/services/one_liner.py` 의 머리말에 근거가 있다.

기업명·사람 이름은 **전부 지어낸 것**이다(공개 저장소).
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.one_liner import (
    apply_one_liner, compose_one_liner, origin, sync_one_liner,
)

from .conftest import DEMO_PASSWORD


def make(**kw):
    """조합에 쓰이는 칸만 가진 가짜 기업. 안 준 칸은 비어 있다."""
    fields = dict(business_desc=None, revenue_2022=None, revenue_2023=None,
                  revenue_2024=None, revenue_2025=None, funding_total=None,
                  raise_target=None, pre_value=None, competitiveness=None,
                  one_liner=None)
    fields.update(kw)
    return SimpleNamespace(**fields)


# --- 형식 --------------------------------------------------------------------

def test_full_line_follows_the_sheet_notation():
    """모든 칸이 찼을 때. 사용자가 준 예시와 같은 모양이어야 한다."""
    made = compose_one_liner(make(
        business_desc="비전AI 기반 미세먼지·병충해 측정 솔루션",
        revenue_2025="13억",
        funding_total=1100,   # 백만원 → 11억
        raise_target=3000,    # → 30억
        pre_value=20000,      # → 200억
        competitiveness="TIPS 24년 선정",
    ))
    assert made == ("비전AI 기반 미세먼지·병충해 측정 솔루션 | 매출 13억 | "
                    "누적투자금액 11억 | 30억 투자유치중 | Pre Value 200억 | "
                    "TIPS 24년 선정")


def test_amounts_are_shown_in_eok_like_the_rest_of_the_screen():
    """백만원 정수는 화면·딜소개와 같은 단위(억)로 나온다. 소수 한 자리까지."""
    made = compose_one_liner(make(business_desc="소재 제조",
                                  funding_total=560, raise_target=830,
                                  pre_value=15000))
    assert made == "소재 제조 | 누적투자금액 5.6억 | 8.3억 투자유치중 | Pre Value 150억"


def test_every_written_year_is_listed():
    """적힌 해가 여럿이면 **다 나온다.** 사용자 신고가 바로 이것이다.

    모양(`매출 23년 A, 24년 B, 25년 C`)은 지어낸 것이 아니라 실데이터에 그대로
    있는 줄에서 가져왔다 — `매출 23년 2억, 24년 4억, 25년 11억` 이 글자까지
    이 모양이고, 쉼표만 뺀 같은 모양이 하나 더 있다.
    """
    made = compose_one_liner(make(business_desc="물류 최적화",
                                  revenue_2023="2억", revenue_2024="4억",
                                  revenue_2025="11억"))
    assert made == "물류 최적화 | 매출 23년 2억, 24년 4억, 25년 11억"


def test_2022_is_a_source_year_again():
    """22년도 재료다.

    한동안 일부러 빼 두었던 해다("소개 문구에 22년 매출을 적은 예가 시트에
    하나도 없다"). 그 근거가 지금은 성립하지 않는다 — 운영 사본에 22년 값이
    136곳(금액 92곳) 쌓였고, 사용자가 22·23년도 나오게 해 달라고 요청했다.
    """
    made = compose_one_liner(make(business_desc="소재 제조",
                                  revenue_2022="2.6억", revenue_2023="2.8억",
                                  revenue_2024="1.6억"))
    assert made == "소재 제조 | 매출 22년 2.6억, 23년 2.8억, 24년 1.6억"


def test_oldest_year_comes_first():
    """차례는 **오래된 해부터**다. 뒤집히면 추세를 거꾸로 읽는다."""
    made = compose_one_liner(make(revenue_2025="11억", revenue_2022="1억"))
    assert made == "매출 22년 1억, 25년 11억"


def test_a_single_year_carries_no_year_label():
    """한 해뿐이면 연도를 안 붙인다 — `매출 13억`.

    사람이 쓴 `매출 …` 짧은 토막 139개에는 연도가 없고, 연도를 적은 17개는
    하나같이 연도를 **앞에** 둔다(`25년 매출 13억`). 한 해짜리에 연도를 붙이면
    139개 쪽과 어긋나고, `25년 매출 13억` 으로 뒤집으면 여러 해일 때의 모양과
    갈린다.
    """
    assert compose_one_liner(make(revenue_2024="13억")) == "매출 13억"
    assert compose_one_liner(make(revenue_2022="13억")) == "매출 13억"


def test_years_without_an_amount_drop_out_of_the_list():
    """가운데 해가 메모면 **그 해만** 빠진다 — 자리를 비워 두지 않는다."""
    made = compose_one_liner(make(revenue_2022="4억", revenue_2023="확인안됨",
                                  revenue_2024="9억"))
    assert made == "매출 22년 4억, 24년 9억"

    # 그렇게 걸러 한 해만 남으면 연도가 다시 빠진다.
    made = compose_one_liner(make(revenue_2022="확인안됨", revenue_2023="검색안됨",
                                  revenue_2024="9억"))
    assert made == "매출 9억"


def test_a_note_that_carries_year_numbers_is_still_a_note():
    """`23, 24, 25 매출액 없음` 의 23·24·25 는 금액이 아니라 **연도**다.

    숫자가 들어 있어서 '숫자가 한 자라도 있는가' 규칙만으로는 통과해
    `매출 23, 24, 25 매출액 없음` 이 되어 나간다. 운영 사본의 매출 칸 값 639개
    중 `없음` 이 든 것은 4개뿐이고 넷 다 이런 메모다.
    """
    for note in ("23, 24, 25 매출액 없음", "2025년 설립, 해당없음",
                 "2026년 6월 22일 설립된 신설법인으로, 과거 매출 실적은 없음"):
        assert compose_one_liner(make(business_desc="소재", revenue_2024=note)) == "소재"


# --- 금액은 글자다 ------------------------------------------------------------

@pytest.mark.parametrize("written", [
    "1,224백만원",      # 백만원 단위로 적힌 줄
    "8.2억",
    "150억 ~ 200억",    # 범위
    "8,247만 9,485원",  # 원 단위 그대로
    "4월 기준 3억",     # 말이 섞인 금액
    "1.5억 목표",
    "10억 이상",
])
def test_written_revenue_is_copied_verbatim(written):
    """연도별 매출은 **적힌 그대로** 옮긴다.

    원본 한 칸에 억·백만원·원·범위가 섞여 있다. 숫자로 바꾸려면 단위를 판별해야
    하고, 잘못 읽으면 100배가 틀어진 채 딜소개 문구에 실려 나간다.
    """
    made = compose_one_liner(make(business_desc="소재", revenue_2024=written))
    assert made == f"소재 | 매출 {written}"


@pytest.mark.parametrize("note", ["확인안됨", "검색안됨", "최근데이터 확인X", "매출액 없음"])
def test_not_a_number_notes_are_not_shown_as_revenue(note):
    """매출 칸에 든 '아직 못 찾았다'는 메모는 금액이 아니다.

    실데이터에 `확인안됨`(40곳)·`검색안됨`(36곳)·`최근데이터 확인X`(55곳)이 들어
    있다. 그대로 옮기면 `매출 확인안됨` 이 되어 안 쓴 것만 못하다.
    가르는 기준은 **숫자가 한 자라도 있는가** 하나다.
    """
    assert compose_one_liner(make(business_desc="소재", revenue_2024=note)) == "소재"


# --- 일부만 찼을 때(실데이터의 대부분) ----------------------------------------

@pytest.mark.parametrize("only", [
    {"business_desc": "헬스케어 기기 제조"},
    {"revenue_2024": "8.9억"},
    {"funding_total": 4000},
    {"raise_target": 500},
    {"pre_value": 12000},
    {"competitiveness": "특허 17건"},
])
def test_missing_items_leave_no_empty_slot(only):
    """빈 칸은 **토막째** 빠진다 — `| |` 도, 앞뒤에 붙은 `|` 도 남지 않는다.

    실데이터는 대부분 일부만 차 있다(누적투자금액은 344곳 중 42곳뿐이다).
    자리를 비워 두면 소개가 `… | | …` 로 도배된다.
    """
    made = compose_one_liner(make(**only))
    assert made, "칸 하나만 차 있어도 한 줄은 나와야 한다"
    assert "| |" not in made
    assert not made.startswith("|") and not made.endswith("|")
    assert "  " not in made


def test_partial_row_keeps_the_order():
    """가운데가 비어도 남은 토막의 **순서**는 그대로다."""
    made = compose_one_liner(make(business_desc="시니어 문화여가 콘텐츠 공급",
                                  revenue_2024="8.9억", funding_total=4000,
                                  raise_target=1000))
    assert made == "시니어 문화여가 콘텐츠 공급 | 매출 8.9억 | 누적투자금액 40억 | 10억 투자유치중"


def test_nothing_filled_makes_nothing():
    assert compose_one_liner(make()) == ""


def test_zero_is_a_real_amount():
    """'0' 과 '아직 안 적음'은 다르다 — 0 을 빈 칸으로 삼키면 안 된다."""
    assert compose_one_liner(make(business_desc="초기 단계", funding_total=0)) == \
        "초기 단계 | 누적투자금액 0억"


# --- 사업분야에 이미 다 적혀 온 경우 ------------------------------------------

def test_does_not_repeat_what_the_business_desc_already_says():
    """시트를 쓰던 사람이 사업분야 한 칸에 재무까지 통째로 적어 온 경우.

    같은 항목을 또 붙이면 `매출 13억 … 매출 13억` 처럼 중복되고 숫자가 어긋난다.
    """
    made = compose_one_liner(make(
        business_desc="비전AI 측정 엔진 | 매출 13억 | 누적투자금액 11억 | Pre Value 200억",
        revenue_2024="9억", funding_total=500, pre_value=3000,
        raise_target=3000,
    ))
    # 이미 말한 매출·누적투자·Pre Value 는 다시 안 붙고, 없던 투자유치만 붙는다.
    assert made == ("비전AI 측정 엔진 | 매출 13억 | 누적투자금액 11억 | "
                    "Pre Value 200억 | 30억 투자유치중")


def test_typoed_separators_become_one_shape():
    """`|` 를 치려다 같은 자리의 `I`·`l`·`ㅣ` 를 친 흔적이 실데이터에 남아 있다."""
    made = compose_one_liner(make(
        business_desc="측정 엔진 | 매출 13억 I 누적투자금액 11억 l Pre value 200억ㅣTIPS 선정"))
    assert made == "측정 엔진 | 매출 13억 | 누적투자금액 11억 | Pre value 200억 | TIPS 선정"


def test_dash_placeholder_is_dropped():
    """시트에서 '해당 없음'을 `-` 하나로 적어 둔 칸. 그대로 두면 빈 칸이 보인다."""
    made = compose_one_liner(make(business_desc="광 다이오드 칩 | - | 투자유치 진행중 | -"))
    assert made == "광 다이오드 칩 | 투자유치 진행중"


# --- 손으로 쓴 소개을 지키는 규칙 ---------------------------------------------

def test_manual_line_is_never_silently_replaced():
    """사람이 쓴 소개는 스타트업DB 를 고쳐도 그대로 남는다."""
    c = make(one_liner="사람이 다듬어 쓴 소개", business_desc="소재 제조",
             funding_total=1000)
    result = sync_one_liner(c, previous_auto="예전 자동 조합 값")
    assert c.one_liner == "사람이 다듬어 쓴 소개"
    assert result["applied"] is False
    assert result["kept"] is True
    # 조용히 넘어가지 않는다 — 만들어 둔 값을 함께 돌려줘야 화면이 물어볼 수 있다.
    assert result["suggestion"] == "소재 제조 | 누적투자금액 10억"


def test_empty_line_is_filled():
    c = make(business_desc="소재 제조", funding_total=1000)
    result = sync_one_liner(c, previous_auto=None)
    assert c.one_liner == "소재 제조 | 누적투자금액 10억"
    assert result["applied"] is True


def test_previously_auto_line_is_refreshed():
    """전에 이 코드가 만든 값이면 갱신한다 — 지울 손글씨가 없다."""
    before = "소재 제조"
    c = make(one_liner=before, business_desc="소재 제조", funding_total=1000)
    result = sync_one_liner(c, previous_auto=before)
    assert c.one_liner == "소재 제조 | 누적투자금액 10억"
    assert result["applied"] is True


def test_empty_source_never_wipes_an_existing_line():
    """스타트업DB 가 비었다는 이유로 멀쩡한 소개를 지우지 않는다."""
    c = make(one_liner="사람이 쓴 소개")
    result = sync_one_liner(c, previous_auto=None)
    assert c.one_liner == "사람이 쓴 소개"
    assert result["applied"] is False


def test_typing_into_the_line_wins_in_the_same_request():
    """방금 손으로 적은 문장을 같은 요청 안에서 자동 조합으로 덮으면 안 된다."""
    c = make(one_liner="방금 손으로 적은 문장", business_desc="소재 제조")
    sync_one_liner(c, previous_auto=None, manual_edit=True)
    assert c.one_liner == "방금 손으로 적은 문장"


def test_origin_tells_hand_written_from_generated():
    assert origin("", None) == "empty"
    assert origin("소재 제조", "소재 제조") == "auto"
    assert origin("사람이 다듬어 쓴 소개", "소재 제조") == "manual"


def test_apply_overwrites_on_purpose():
    """사람이 '자동 조합을 쓰겠다'고 고른 경우에만 손글씨를 덮는다."""
    c = make(one_liner="사람이 쓴 소개", business_desc="소재 제조")
    assert apply_one_liner(c) == "소재 제조"
    assert c.one_liner == "소재 제조"


def test_apply_does_not_blank_out_when_there_is_nothing_to_compose():
    c = make(one_liner="사람이 쓴 소개")
    apply_one_liner(c)
    assert c.one_liner == "사람이 쓴 소개"


# --- 화면/API ----------------------------------------------------------------

@pytest.fixture()
def logged_in(client, db, users):
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    return client


@pytest.fixture()
def company(db):
    from app.models import IrCompany

    row = IrCompany(name="가나테크", business_desc="산업용 센서 제조")
    db.add(row)
    db.commit()
    return row


def test_filling_the_startup_db_tab_updates_the_line(logged_in, db, company):
    """요청의 핵심 — 스타트업DB 칸을 채우면 한줄 소개가 실제로 바뀐다."""
    r = logged_in.patch(f"/api/companies/{company.id}",
                        json={"revenue_2024": "8.9억", "funding_total": 4000,
                              "raise_target": 1000, "pre_value": 12000,
                              "competitiveness": "TIPS 선정"})
    assert r.status_code == 200, r.text
    assert r.json()["one_liner_applied"] is True
    db.refresh(company)
    assert company.one_liner == ("산업용 센서 제조 | 매출 8.9억 | 누적투자금액 40억 | "
                                 "10억 투자유치중 | Pre Value 120억 | TIPS 선정")


def test_hand_written_line_survives_a_startup_db_edit(logged_in, db, company):
    company.one_liner = "사람이 다듬어 쓴 소개"
    db.commit()

    r = logged_in.patch(f"/api/companies/{company.id}", json={"funding_total": 4000})
    assert r.status_code == 200, r.text
    body = r.json()
    db.refresh(company)
    assert company.one_liner == "사람이 다듬어 쓴 소개", "손으로 쓴 소개가 사라졌다"
    assert body["one_liner_applied"] is False
    assert body["one_liner_kept_manual"] is True, "지켰다는 사실을 알려야 한다"
    assert "누적투자금액 40억" in body["one_liner_suggestion"]


def test_unrelated_edit_does_not_touch_the_line(logged_in, db, company):
    """계약여부처럼 상관없는 칸을 고쳤는데 소개가 바뀌면 이유를 알 수 없다."""
    logged_in.patch(f"/api/companies/{company.id}", json={"contract_status": "paid"})
    db.refresh(company)
    assert company.one_liner is None


def test_preview_does_not_save(logged_in, db, company):
    company.one_liner = "사람이 다듬어 쓴 소개"
    company.funding_total = 4000
    db.commit()

    body = logged_in.get(f"/api/companies/{company.id}/one-liner").json()
    assert body["origin"] == "manual"
    assert body["current"] == "사람이 다듬어 쓴 소개"
    assert body["suggestion"] == "산업용 센서 제조 | 누적투자금액 40억"
    assert body["differs"] is True
    db.refresh(company)
    assert company.one_liner == "사람이 다듬어 쓴 소개", "미리보기가 저장하면 안 된다"


def test_choosing_the_auto_line_replaces_the_manual_one(logged_in, db, company):
    """자동 조합을 쓸지 손으로 쓴 것을 지킬지는 **언제나 사람이 고른다**."""
    company.one_liner = "사람이 다듬어 쓴 소개"
    company.funding_total = 4000
    db.commit()

    body = logged_in.post(f"/api/companies/{company.id}/one-liner").json()
    assert body["previous"] == "사람이 다듬어 쓴 소개", "무엇을 덮었는지 알려야 한다"
    db.refresh(company)
    assert company.one_liner == "산업용 센서 제조 | 누적투자금액 40억"


def test_clearing_the_line_brings_the_auto_one_back(logged_in, db, company):
    """소개를 비워 보내면 '자동 조합을 다시 넣어 달라'는 뜻으로 받는다."""
    company.one_liner = "사람이 다듬어 쓴 소개"
    company.funding_total = 4000
    db.commit()

    logged_in.patch(f"/api/companies/{company.id}", json={"one_liner": ""})
    db.refresh(company)
    assert company.one_liner == "산업용 센서 제조 | 누적투자금액 40억"


def test_table_rows_carry_the_preview(logged_in, db, company):
    """표를 보는 사람이 '지금 값 vs 자동 조합'을 나란히 볼 수 있어야 한다."""
    company.one_liner = "사람이 다듬어 쓴 소개"
    company.funding_total = 4000
    db.commit()

    row = next(r for r in logged_in.get("/api/companies").json()["rows"]
               if r["id"] == company.id)
    assert row["one_liner"] == "사람이 다듬어 쓴 소개"
    assert row["one_liner_suggestion"] == "산업용 센서 제조 | 누적투자금액 40억"
    assert row["one_liner_auto"] is False
