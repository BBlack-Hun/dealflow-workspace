"""스타트업DB 칸 → `딜 소개 문구` 자동 조합. **고를 때만 들어간다.**

시트를 쓰던 사람은 스타트업DB 탭에 값을 넣는데, 정작 딜소개에 쓰이는 것은 옆
탭의 한 칸이라 같은 내용을 두 번 적고 있었다. 이 검사는 그 조합이 **실데이터의
표기 그대로** 나오는지, 그리고 **칸의 기본이 사용자 정의 문구**인지를 지킨다.

기본이 무엇인지가 이 파일의 절반이다. 예전에는 조합값과 글자가 같은 줄
(`AUTO`)이 재료를 고칠 때마다 저절로 다시 쓰였고 칸을 비우면 조합값이 도로
들어왔다 — 칸의 기본이 자동이었다. 사용자가 그 기본을 뒤집었다("기본 값은
사용자 정의 문구 사용"). 그래서 이제 **저장하는 길은 이 칸을 건드리지 않고**,
자동 조합은 사람이 고르는 세 자리에서만 들어간다 — 창의 [자동 조합으로 바꾸기]
(→ [저장]), 표 위의 [전체 자동조합], `POST /api/companies/{id}/one-liner`.

기대값의 표기(`누적투자금액 N억` · `N억 투자유치중` · `Pre Value N억`)는 지어낸
것이 아니라 344행에서 가장 많이 쓰인 모양을 세어 뽑은 것이다 —
`app/services/one_liner.py` 의 머리말에 근거가 있다.

기업명·사람 이름은 **전부 지어낸 것**이다(공개 저장소).
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.one_liner import (
    apply_one_liner, compose_one_liner, one_liner_status, origin,
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
        # 금액 넷도 **적은 그대로**다(0074). 단위는 억.
        funding_total="11",
        raise_target="30",
        pre_value="200",
        competitiveness="TIPS 24년 선정",
    ))
    assert made == ("비전AI 기반 미세먼지·병충해 측정 솔루션 | 매출 13억 | "
                    "누적투자금액 11억 | 30억 투자유치중 | Pre Value 200억 | "
                    "TIPS 24년 선정")


def test_amounts_are_shown_in_eok_like_the_rest_of_the_screen():
    """적은 그대로가 화면·딜소개와 같은 단위(억)로 나온다."""
    made = compose_one_liner(make(business_desc="소재 제조",
                                  funding_total="5.6", raise_target="8.3",
                                  pre_value="150"))
    assert made == "소재 제조 | 누적투자금액 5.6억 | 8.3억 투자유치중 | Pre Value 150억"


def test_a_range_stays_a_range_in_the_line():
    """`5-10억 사이` 라고 적었으면 한줄 소개에도 구간이 남아야 한다.

    숫자 하나로 뭉개면 사람이 적은 뜻이 사라지고, 뭉갠 숫자가 그대로 투자사에게
    나간다. 구분자만 `~` 한 모양으로 선다.
    """
    made = compose_one_liner(make(business_desc="소재 제조",
                                  funding_total="5-10억 사이",
                                  raise_target="30~50억"))
    assert made == "소재 제조 | 누적투자금액 5~10억 | 30~50억 투자유치중"


def test_what_cannot_be_read_never_reaches_the_line():
    """`~`(모름)과 자유 문장은 **토막째 빠진다.**

    금액 칸이 글자가 되면서 사람은 아무 말이나 적을 수 있게 됐다. 그것이 그대로
    투자사에게 나가면 안 된다 — 빼면 값이 비었을 때와 똑같은 모양이 된다.
    """
    made = compose_one_liner(make(business_desc="소재 제조",
                                  funding_total="~",
                                  raise_target="투자 유치 협의중",
                                  pre_value="150"))
    assert made == "소재 제조 | Pre Value 150억"


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
    {"funding_total": "40"},
    {"raise_target": "5"},
    {"pre_value": "120"},
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
                                  revenue_2024="8.9억", funding_total="40",
                                  raise_target="10"))
    assert made == "시니어 문화여가 콘텐츠 공급 | 매출 8.9억 | 누적투자금액 40억 | 10억 투자유치중"


def test_nothing_filled_makes_nothing():
    assert compose_one_liner(make()) == ""


def test_zero_is_a_real_amount():
    """'0' 과 '아직 안 적음'은 다르다 — 0 을 빈 칸으로 삼키면 안 된다."""
    assert compose_one_liner(make(business_desc="초기 단계", funding_total="0")) == \
        "초기 단계 | 누적투자금액 0억"


def test_zero_and_unknown_are_different_facts():
    """`0`(없음)은 문구에 나가고, `~`(모름)은 안 나간다.

    둘을 한 칸으로 뭉개면 "아직 투자를 못 받았다"는 **아는 사실**이 "모른다"로
    바뀌어 사라진다. 투자사에게 보이는 뜻이 서로 다르다.
    """
    assert compose_one_liner(make(business_desc="초기 단계", funding_total="0")) == \
        "초기 단계 | 누적투자금액 0억"
    assert compose_one_liner(make(business_desc="초기 단계", funding_total="~")) == \
        "초기 단계"


# --- 사업분야에 이미 다 적혀 온 경우 ------------------------------------------

def test_does_not_repeat_what_the_business_desc_already_says():
    """시트를 쓰던 사람이 사업분야 한 칸에 재무까지 통째로 적어 온 경우.

    같은 항목을 또 붙이면 `매출 13억 … 매출 13억` 처럼 중복되고 숫자가 어긋난다.
    """
    made = compose_one_liner(make(
        business_desc="비전AI 측정 엔진 | 매출 13억 | 누적투자금액 11억 | Pre Value 200억",
        revenue_2024="9억", funding_total="5", pre_value="30",
        raise_target="30",
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


# --- 기본은 사용자 정의 문구 — 저장하는 길은 칸을 안 건드린다 ----------------
#
# `one_liner_status` 는 **읽기만 한다.** 여기서 칸이 한 글자라도 바뀌면 운영
# 293곳의 손글씨가 소리 없이 사라지는 길이 하나 생기는 것이다.

def test_status_never_writes_to_the_field():
    """재료가 다 찼어도 칸에 안 넣는다 — 만들어 보여 줄 뿐이다."""
    c = make(business_desc="소재 제조", funding_total="10")
    result = one_liner_status(c)
    assert c.one_liner is None, "저장 길에서 자동 조합이 칸에 들어갔다"
    assert result["applied"] is False
    # 조용히 넘어가지 않는다 — 만들어 둔 값을 함께 돌려줘야 화면이 물어볼 수 있다.
    assert result["suggestion"] == "소재 제조 | 누적투자금액 10억"
    assert result["origin"] == "empty"


def test_manual_line_is_never_replaced():
    """사람이 쓴 소개는 스타트업DB 를 고쳐도 그대로 남는다."""
    c = make(one_liner="사람이 다듬어 쓴 소개", business_desc="소재 제조",
             funding_total="10")
    result = one_liner_status(c)
    assert c.one_liner == "사람이 다듬어 쓴 소개"
    assert result["applied"] is False
    assert result["kept"] is True
    assert result["suggestion"] == "소재 제조 | 누적투자금액 10억"


def test_a_line_that_matches_the_auto_one_is_not_refreshed_either():
    """전에 조합값을 넣어 둔 줄도 **저절로는** 안 바뀐다 — 이게 뒤집힌 기본이다.

    예전 규칙에서는 이런 줄(`origin == auto`)이 재료를 고칠 때마다 따라왔다.
    그 자동 갱신이 곧 '기본이 자동' 이었다.
    """
    c = make(one_liner="소재 제조", business_desc="소재 제조", funding_total="10")
    result = one_liner_status(c)
    assert c.one_liner == "소재 제조", "재료를 고치자 칸이 저절로 다시 쓰였다"
    assert result["applied"] is False
    assert result["suggestion"] == "소재 제조 | 누적투자금액 10억"


def test_status_tells_the_screen_which_one_it_is():
    """화면이 `자동으로 만든 값` 과 `직접 쓰신 값` 을 갈라 말할 수 있어야 한다."""
    same = make(one_liner="소재 제조", business_desc="소재 제조")
    assert one_liner_status(same)["origin"] == "auto"
    mine = make(one_liner="사람이 다듬어 쓴 소개", business_desc="소재 제조")
    assert one_liner_status(mine)["origin"] == "manual"


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


def test_filling_the_startup_db_tab_only_offers_the_line(logged_in, db, company):
    """요청의 핵심 — 스타트업DB 를 채워도 칸은 그대로고, 만들 줄만 따라온다.

    **기본은 사용자 정의 문구다.** 채운 재료로 만들 수 있는 한 줄은 응답에
    실려 오고(화면이 [자동 조합으로 바꾸기] 로 권한다), 칸에 넣을지는 사람이
    누른다.
    """
    r = logged_in.patch(f"/api/companies/{company.id}",
                        json={"revenue_2024": "8.9억", "funding_total": "40",
                              "raise_target": "10", "pre_value": "120",
                              "competitiveness": "TIPS 선정"})
    assert r.status_code == 200, r.text
    made = ("산업용 센서 제조 | 매출 8.9억 | 누적투자금액 40억 | "
            "10억 투자유치중 | Pre Value 120억 | TIPS 선정")
    assert r.json()["one_liner_applied"] is False
    assert r.json()["one_liner_suggestion"] == made
    db.refresh(company)
    assert company.one_liner is None, "저장했더니 자동 조합이 칸에 들어갔다"

    # 그리고 **누르면** 들어간다 — 길이 막힌 것이 아니다.
    logged_in.post(f"/api/companies/{company.id}/one-liner")
    db.refresh(company)
    assert company.one_liner == made


def test_an_auto_looking_line_is_not_refreshed_by_a_source_edit(logged_in, db, company):
    """조합값이 들어 있던 줄도 재료를 고쳤다고 **저절로** 바뀌지 않는다.

    뒤집힌 기본이 바로 이것이다. 예전에는 이 줄이 따라 바뀌었다.
    """
    company.one_liner = "산업용 센서 제조"          # 그때의 조합값 그대로
    db.commit()

    logged_in.patch(f"/api/companies/{company.id}", json={"funding_total": "40"})
    db.refresh(company)
    assert company.one_liner == "산업용 센서 제조", "칸이 저절로 다시 쓰였다"


def test_hand_written_line_survives_a_startup_db_edit(logged_in, db, company):
    company.one_liner = "사람이 다듬어 쓴 소개"
    db.commit()

    r = logged_in.patch(f"/api/companies/{company.id}", json={"funding_total": "40"})
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


def test_creating_a_company_does_not_fill_the_line(logged_in, db):
    """새 기업도 마찬가지다 — 재료를 함께 적어 넣어도 칸은 사람이 쓴 것만 담는다."""
    from app.models import IrCompany

    r = logged_in.post("/api/companies",
                       json={"name": "샘플마바에듀", "business_desc": "교육 플랫폼",
                             "funding_total": "40"})
    assert r.status_code == 200, r.text
    assert r.json()["one_liner_applied"] is False
    assert r.json()["one_liner_suggestion"] == "교육 플랫폼 | 누적투자금액 40억"
    row = db.get(IrCompany, r.json()["id"])
    assert row.one_liner is None, "새 기업에 자동 조합이 저절로 들어갔다"


def test_a_line_typed_on_create_is_kept_as_is(logged_in, db):
    """적어 보낸 문구는 그대로 들어간다 — 그것이 기본값이다."""
    from app.models import IrCompany

    r = logged_in.post("/api/companies",
                       json={"name": "샘플바사푸드", "business_desc": "식자재 유통",
                             "funding_total": "40", "one_liner": "사람이 쓴 문구"})
    row = db.get(IrCompany, r.json()["id"])
    assert row.one_liner == "사람이 쓴 문구"


def test_preview_does_not_save(logged_in, db, company):
    company.one_liner = "사람이 다듬어 쓴 소개"
    company.funding_total = "40"
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
    company.funding_total = "40"
    db.commit()

    body = logged_in.post(f"/api/companies/{company.id}/one-liner").json()
    assert body["previous"] == "사람이 다듬어 쓴 소개", "무엇을 덮었는지 알려야 한다"
    db.refresh(company)
    assert company.one_liner == "산업용 센서 제조 | 누적투자금액 40억"


def test_clearing_the_line_leaves_it_empty(logged_in, db, company):
    """비워서 저장하면 **빈 채로** 둔다 — 비우는 것도 사람의 결정이다.

    예전에는 비워 보내는 것을 "자동 조합을 다시 넣어 달라" 는 뜻으로 받았다.
    그건 칸의 기본이 자동일 때의 규칙이라, 기본이 뒤집힌 지금은 비울 길이
    아예 없어지는 셈이었다.
    """
    company.one_liner = "사람이 다듬어 쓴 소개"
    company.funding_total = "40"
    db.commit()

    body = logged_in.patch(f"/api/companies/{company.id}",
                           json={"one_liner": ""}).json()
    db.refresh(company)
    assert company.one_liner is None, "비웠는데 자동 조합이 도로 들어왔다"
    # 비어 있어도 만들 수 있는 줄은 계속 권한다 — 되돌리는 길이 한 번 누르는 거리다.
    assert body["one_liner_suggestion"] == "산업용 센서 제조 | 누적투자금액 40억"


def test_typing_a_new_line_is_saved_as_typed(logged_in, db, company):
    """사람이 친 문장이 그대로 저장된다 — 재료를 같이 보내도 덮이지 않는다.

    [수정] 창은 **모든 칸을 한 번에** 보낸다. 그래서 이 저장 한 번에 재료 칸과
    문구 칸이 함께 실려 오는데, 그때 조합값이 이기면 방금 친 문장이 눈앞에서
    사라진다.
    """
    r = logged_in.patch(f"/api/companies/{company.id}",
                        json={"one_liner": "방금 손으로 적은 문장",
                              "business_desc": "산업용 센서 제조",
                              "funding_total": "40"})
    assert r.status_code == 200, r.text
    db.refresh(company)
    assert company.one_liner == "방금 손으로 적은 문장"


def test_table_rows_carry_the_preview(logged_in, db, company):
    """표를 보는 사람이 '지금 값 vs 자동 조합'을 나란히 볼 수 있어야 한다."""
    company.one_liner = "사람이 다듬어 쓴 소개"
    company.funding_total = "40"
    db.commit()

    row = next(r for r in logged_in.get("/api/companies").json()["rows"]
               if r["id"] == company.id)
    assert row["one_liner"] == "사람이 다듬어 쓴 소개"
    assert row["one_liner_suggestion"] == "산업용 센서 제조 | 누적투자금액 40억"
    assert row["one_liner_auto"] is False
