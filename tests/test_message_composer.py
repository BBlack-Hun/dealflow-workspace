"""Unit tests for the message composer (ROADMAP task 1.4)."""
from app.services import message_composer as mc
from app.services.message_composer import CompanyView, ContactView


# --- format_eok -------------------------------------------------------------
#
# 저장이 백만원 정수에서 **사람이 적은 글자(억)** 로 바뀌었다(0074). `format_eok`
# 은 이제 그 글자에서 **문구에 실을 수량**을 고르는 일을 하고, 고르는 판단은
# `services/amount.py` 한 곳에 있다.

def test_format_eok_passes_the_written_number_through():
    """옛 정수가 옮겨진 글자(`3090` → `"30.9"`)가 그대로 지나야 한다.

    **단위까지 붙어서 온다.** 틀에 `억` 을 적어 두면 `5천만원` 을 적은 순간
    `5천만원억` 이 된다 — 단위를 아는 곳은 `services/amount.py` 하나여야 한다.
    """
    assert mc.format_eok("30.9") == "30.9억"
    assert mc.format_eok("50") == "50억"
    assert mc.format_eok("200") == "200억"
    assert mc.format_eok("5.6") == "5.6억"


def test_format_eok_keeps_the_written_unit():
    """`5천만원` 이라고 적었으면 문구에도 `5천만원` 으로 나가야 한다.

    `0.5억` 으로 고쳐 내보내면 사람이 굳이 그렇게 적은 뜻이 사라지고, 투자사가
    실제로 쓰는 말도 아니다(사용자 요청이 정확히 이것이다).
    """
    assert mc.format_eok("5천만원") == "5천만원"
    assert mc.format_eok("4700만원") == "4700만원"
    assert mc.format_eok("5,000만원") == "5000만원"


def test_format_eok_keeps_a_range_a_range():
    """`5-10억 사이` 라고 적었으면 문구에도 구간이 남아야 한다.

    양쪽 단위가 같으면 단위를 **한 번만** 적는다(`5억~10억` 이 아니라 `5~10억`) —
    사람이 쓰는 모양이 그것이다. 섞여 있으면 각자의 단위가 그대로 남는다.
    """
    assert mc.format_eok("5-10억 사이") == "5~10억"
    assert mc.format_eok("5~10억") == "5~10억"
    assert mc.format_eok("5억~10억") == "5~10억"
    assert mc.format_eok("3천만원~1억") == "3천만원~1억"


def test_format_eok_none_returns_none():
    assert mc.format_eok(None) is None


def test_format_eok_drops_what_it_cannot_read():
    """`~`(모름)과 자유 문장은 **문구에 실리지 않는다.**

    사람이 아무 글자나 넣을 수 있게 된 이상, 못 읽는 것을 그대로 투자사에게
    보내는 쪽이 훨씬 나쁘다. 부르는 쪽은 `None` 을 보고 토막째 뺀다.
    """
    assert mc.format_eok("~") is None
    assert mc.format_eok("투자 유치 협의중") is None
    assert mc.format_eok("") is None


def test_the_number_rule_lives_in_exactly_one_place():
    """`format_eok` 은 **스스로 해석하지 않는다** — `amount.quantity` 를 부른다.

    이 파일에서 `억` 을 붙이는 자리가 넷이고 한줄소개에 셋이 더 있다. 그 일곱이
    각자 글자를 읽기 시작하면 같은 값이 문구마다 다르게 나가고, 갈린 숫자는
    겉보기에 멀쩡하다. 규칙을 옮기고 싶으면 `services/amount.py` 를 고쳐라 —
    이 검사는 그 자리를 바꾸면 깨지도록 되어 있다.
    """
    from app.services import amount

    for written in ("30.9", "5천만원", "5-10억 사이", "3천만원~1억", "0", "~",
                    "말도 안 되는 값"):
        assert mc.format_eok(written) == amount.phrase(written), written


# --- auto_company_summary --------------------------------------------------
#
# **적어 둔 글이 있으면 그것만 나간다.** 아래 조합 검사들은 그래서 전부
# `딜 소개 문구`(`one_liner`)가 **빈** 기업으로 서 있다 — 조합은 이제 그
# 갈래에서만 돈다. 예전 판에서는 같은 검사들이 `one_liner="선도거래"` 처럼
# 문구를 적어 둔 채로 `[분야] | 선도거래 | 매출 …` 을 견줬는데, 그 모양은
# 더 이상 만들어지지 않는다(그 줄이 바로 사용자가 고쳐 달라고 한 것이다).
# 검사가 재던 것(단위·`Pre Value 약 N억` 모양·빈 토막 생략)은 그대로 살아
# 있으니, 문구만 비우고 자리를 옮겼다.

def test_auto_summary_composes_the_materials_when_nothing_was_written():
    """`딜 소개 문구` 가 비면 — 그때만 — 재료로 한 줄을 만든다."""
    c = CompanyView(
        name="샘플애그", sector_major="애그테크",
        revenue_recent="30.9", funding_total="5.6", raise_target="20",
        pre_value="210", competitiveness="상급 유통사 12곳 계약",
    )
    summary = mc.auto_company_summary(c)
    # `Pre Value 약 210억원` 이 `Pre Value 약 210억` 이 됐다. 이 자리가 이 저장소에서
    # **유일하게 `원` 을 붙이던 곳**이었고, 실데이터에서 사람이 쓰는 모양은
    # `Pre Value 200억` 이다(세어 둔 것은 `services/one_liner.py`). 단위를
    # `services/amount.py` 한 곳으로 모으면서 그 예외를 없앤다 — 한줄소개와도
    # 이제 같은 모양이다.
    assert summary == (
        "[애그테크] | 매출 30.9억 | "
        "누적투자금액 5.6억 | 20억 투자유치중 | Pre Value 약 210억 | 상급 유통사 12곳 계약"
    )


def test_a_sub_eok_amount_keeps_its_unit_all_the_way_to_the_investor():
    """1억 미만을 `5천만원` 으로 적으면 **문구까지 그대로** 간다.

    틀이 `{}억` 이던 시절에는 이 값이 `5천만원억` 이 되거나, 억으로 뭉개져
    `0.5억` 으로 나갔다. 둘 다 사람이 적은 뜻이 아니다.

    (예전에는 `one_liner="선도거래"` 를 함께 두고 쟀다. 문구가 있으면 금액이
    아예 안 붙게 되었으므로 문구를 비운다 — 재는 것은 그대로 단위다.)
    """
    c = CompanyView(name="샘플애그", sector_major="애그테크",
                    funding_total="5천만원", raise_target="3천만원~1억",
                    pre_value="4700만원")
    assert mc.auto_company_summary(c) == (
        "[애그테크] | 누적투자금액 5천만원 | 3천만원~1억 투자유치중 | "
        "Pre Value 약 4700만원"
    )


def test_auto_summary_omits_empty_segments():
    """Empty values must drop the whole segment (no '매출 억').

    빈 칸 하나만 남기던 예전 검사는 `one_liner="한줄 소개"` 로 서 있었는데,
    이제 그 기업은 조합을 지나지 않아 **무엇이 생략되는지 재지 못한다.**
    그래서 문구를 비우고 금액 한 칸만 채워 둔다 — 찬 토막은 나오고 빈 토막은
    통째로 빠지는 것이 이 검사의 요점이다.
    """
    c = CompanyView(name="빈기업", sector_major="AI", funding_total="5")
    summary = mc.auto_company_summary(c)
    assert summary == "[AI] | 누적투자금액 5억"
    assert "매출" not in summary
    assert "Pre Value" not in summary
    assert "투자유치중" not in summary


def test_company_summary_prefers_manual_override():
    c = CompanyView(name="X", sector_major="AI", one_liner="auto",
                    summary="사람이 다듬은 요약문")
    assert mc.company_summary(c) == "사람이 다듬은 요약문"


def test_company_summary_falls_back_to_auto():
    """`summary` 가 비면 `auto_company_summary` 가 답한다.

    답이 `[AI] | auto` 에서 `auto` 로 바뀐 것이 이번 변경이다 — 적어 둔 글이
    있으면 분야도 안 붙는다.
    """
    c = CompanyView(name="X", sector_major="AI", one_liner="auto", summary="   ")
    assert mc.company_summary(c) == "auto"


# --- 적어 둔 글은 **한 글자도 안 바뀌고** 나간다 -----------------------------

def test_what_was_written_goes_out_untouched_even_with_every_number_filled():
    """이번 변경의 핵심. 재무 칸이 다 차 있어도 **아무것도 안 붙는다.**

    운영 실측이 이 모양이었다: 적은 글 186자가 나갈 때는 629자였다. 앞에
    `[분야]` 가 붙고 뒤에 `매출 …| 누적투자금액 …| N억 투자유치중 |
    Pre Value 약 …| 경쟁력` 이 443자 붙었다.

    **예전 판은 왜 못 막았나.** 덧붙일지 말지를 "적은 글에 그 낱말이 이미
    있는가" 로 봤는데, 아래 글에는 `매출`·`누적투자`·`투자유치`·`Pre Value`
    라는 **낱말이 하나도 없다** — 같은 사실을 사람 말로 적었을 뿐이다.
    그래서 검사를 다 통과하고 전부 다시 붙었다. 이 검사는 그 글을 그대로
    쓴다(낱말 검사로는 못 막는 글이라는 것이 요점이다).
    """
    written = ("반도체 후공정 검사 장비를 만듭니다. 작년에 19억을 팔았고 "
               "시리즈 A 까지 13억을 받았습니다. 올해 40억을 더 받으려 합니다.")
    c = CompanyView(
        name="샘플장비", sector_major="딥테크·제조", one_liner=written,
        revenue_recent="19.1", funding_total="13.38", raise_target="40",
        pre_value="200", competitiveness="특허 12건 · 대기업 3곳 납품(장문)",
    )
    said = mc.auto_company_summary(c)

    assert said == written, "적은 글이 한 글자도 안 바뀌어야 한다"
    assert len(said) == len(written), f"{len(written)}자가 {len(said)}자가 됐다"
    for leaked in ("[딥테크·제조]", "매출", "누적투자금액", "투자유치중",
                   "Pre Value", "19.1", "13.38", "200억", "특허 12건"):
        assert leaked not in said, f"{leaked} 이 덧붙었습니다"


def test_the_written_intro_is_what_actually_goes_out():
    """함수 하나가 아니라 **나가는 문구 전체**에서 확인한다.

    `auto_company_summary` 만 재면 사이에 낀 `company_summary`(수동 요약 우선)나
    `compose_message` 가 무엇을 더 붙였는지 놓친다 — 사용자가 본 것은 카톡에
    붙여 넣을 그 글 전체다.
    """
    written = "생산 공정을 스스로 바꾸는 로봇 셀을 만듭니다."
    c = CompanyView(name="샘플장비", sector_major="딥테크·제조", one_liner=written,
                    revenue_recent="19.1", funding_total="13.38",
                    raise_target="40", pre_value="200",
                    competitiveness="특허 12건")
    text = mc.compose_message("안녕하세요, {담당자명} {직함}", "핵심 딜 {개수}개사 공유드립니다.",
                              _contact(), [c], stage=mc.STAGE_DAY1).text
    assert f"[기업1] {written}" in text
    for leaked in ("[딥테크·제조]", "매출", "누적투자금액", "투자유치중",
                   "Pre Value", "특허 12건"):
        assert leaked not in text, f"{leaked} 이 덧붙었습니다"


def test_only_the_padding_around_the_written_intro_is_trimmed():
    """앞뒤 공백만 떼고, 안쪽 글자는 손대지 않는다.

    `|` 로 이어 적어 둔 글도 **그 모양 그대로** 나간다 — 구분자를 다시 맞추거나
    토막을 골라내는 자리는 여기에 없다(그 일은 [자동 조합] 쪽 일이다).
    """
    written = "설명 | 매출 13억 | 누적투자금액 11억"
    c = CompanyView(name="X", sector_major="AI", one_liner=f"  {written}\n")
    assert mc.auto_company_summary(c) == written


def test_a_company_can_be_introducible_with_no_written_intro():
    """**비었을 때 조합을 남겨 둔 이유.** 문구가 비어도 소개 대상에 설 수 있다.

    `IrCompany.introducible` 은 `사업분야 대분류 **또는** 딜 소개 문구` + 금액
    하나를 본다 — 문구 칸은 필수가 아니다. `/deals` 의 `내용 부족` 딱지도 그
    판정을 그대로 쓰고, 이유를 적는 `REQUIRED_FIELDS` 에는 이 칸이 아예 없다.
    즉 **문구가 비었다고 알려 주는 화면이 없다.**

    아무것도 안 내기로 했다면 이런 기업이 `[기업1] ` 한 줄로 카톡에 나간다.
    (개발 사본 344곳에서 문구가 빈 곳은 6곳이고 그 여섯은 금액이 없어 오늘은
    소개 대상이 아니다. 그중 한 곳은 분야가 이미 있어 **금액 한 칸만 채우면**
    아래와 똑같은 모양이 된다.)
    """
    from app.models import IrCompany

    row = IrCompany(name="샘플", sector_major="AI", funding_total="12",
                    summary_status="draft")
    assert row.one_liner is None
    assert row.introducible is True, "문구가 비어도 소개 대상에 선다"

    said = mc.auto_company_summary(CompanyView(
        name=row.name, sector_major=row.sector_major, one_liner=row.one_liner,
        funding_total=row.funding_total))
    assert said == "[AI] | 누적투자금액 12억"
    assert said.strip(), "빈 줄이 투자사에게 나가면 안 된다"


# --- render_template -------------------------------------------------------

def test_render_template_substitutes_known_vars():
    contact = ContactView(name="홍길동", title="대표님", firm="가나벤처스")
    out = mc.render_template("안녕하세요 {담당자명} {직함}님 ({투자사})", contact)
    # 시트의 직함에 이미 '님'이 포함돼 있으므로 '대표님님'이 되지 않아야 한다.
    assert out == "안녕하세요 홍길동 대표님 (가나벤처스)"


def test_render_template_no_duplicate_honorific_when_title_lacks_nim():
    # 직함에 '님'이 없으면 템플릿의 '님'이 정상적으로 붙는다.
    contact = ContactView(name="김서연", title="심사역", firm="자차벤처스")
    out = mc.render_template("{담당자명} {직함}님", contact)
    assert out == "김서연 심사역님"


def test_honorific_title_appends_nim_when_missing():
    """시트 직함이 뒤섞여 있다: '대표님'은 그대로, '심사역'·'파트너'는 '님'을 붙인다."""
    assert mc.honorific_title("심사역") == "심사역님"
    assert mc.honorific_title("파트너") == "파트너님"
    assert mc.honorific_title("대표님") == "대표님"
    assert mc.honorific_title("팀장님") == "팀장님"
    assert mc.honorific_title(None) == "님"


def test_template_without_nim_still_gets_honorific():
    """운영 템플릿 '{담당자명} {직함}' 에서도 모든 직함에 존칭이 붙어야 한다."""
    tpl = "안녕하세요, {담당자명} {직함}"
    assert mc.render_template(tpl, ContactView(name="박민수", title="심사역")) == "안녕하세요, 박민수 심사역님"
    assert mc.render_template(tpl, ContactView(name="박지훈", title="파트너")) == "안녕하세요, 박지훈 파트너님"
    assert mc.render_template(tpl, ContactView(name="홍길동", title="대표님")) == "안녕하세요, 홍길동 대표님"
    # 직함이 비어 있으면 이름에 '님'만 붙는다 (공백 없이)
    assert mc.render_template(tpl, ContactView(name="이수민", title=None)) == "안녕하세요, 이수민님"


def test_render_template_leaves_unknown_tokens():
    contact = ContactView(name="홍길동")
    out = mc.render_template("오타 {담당자님}", contact)
    assert "{담당자님}" in out


# --- pick_opening_kind -----------------------------------------------------

def test_pick_opening_first_contact():
    assert mc.pick_opening_kind(has_history=False) == "opening_first"


def test_pick_opening_re_contact():
    assert mc.pick_opening_kind(has_history=True) == "opening_re"


# --- compose_message -------------------------------------------------------

def _contact():
    return ContactView(name="홍길동", title="대표님", firm="가나벤처스")


def _companies():
    return [
        CompanyView(name="샘플애그", sector_major="애그테크", one_liner="선도거래", revenue_recent="30.9"),
        CompanyView(name="샘플메디", sector_major="헬스케어", one_liner="뇌영상 AI"),
        CompanyView(name="세번째", sector_major="핀테크", one_liner="결제"),
    ]


def test_compose_day1_structure():
    opening = "안녕하세요 {담당자명} {직함}님, 딜소개드립니다."
    closing = "관심 가시는 기업 있으시면 IR Deck 공유드리겠습니다."
    result = mc.compose_message(opening, closing, _contact(), _companies(), stage=mc.STAGE_DAY1)
    text = result.text
    assert text.startswith("안녕하세요 홍길동 대표님, 딜소개드립니다.")
    # 실제 운영 문구 형식: 번호는 "[기업1]", 안내문은 목록 '위'에 온다.
    #
    # 예전에는 `1) [애그테크] | 선도거래 | 매출 30.9억` 이었다. 세 기업 모두
    # `딜 소개 문구` 를 적어 두었으므로 이제 **적은 글만** 나간다 — 분야도
    # 재무도 붙지 않는다. `샘플애그` 의 매출 칸은 일부러 채워 둔 채 두었다:
    # 아래 `not in` 이 그 값이 다시 붙지 않는 것을 여기서도 못 박는다.
    assert "[기업1] 선도거래" in text
    assert "[기업2] 뇌영상 AI" in text
    assert "[기업3] 결제" in text
    assert "[애그테크]" not in text and "매출 30.9억" not in text
    assert text.index("관심 가시는 기업") < text.index("[기업1] ")
    assert text.rstrip().endswith("[기업3] 결제")
    # blank line separators between blocks
    assert "\n\n[기업1]" in text
    assert "\n\n[기업2]" in text


def test_compose_intro_company_count_token():
    """안내문의 {개수}가 선택 기업 수로 치환된다 ('핵심 딜 7개사')."""
    result = mc.compose_message(
        "안녕하세요, {담당자명}님\n우리브이씨 ASSET입니다.",
        "핵심 딜 {개수}개사 간단히 공유드립니다.\n관심 가시는 기업 있으시면 IR Deck 공유드리겠습니다.",
        _contact(), _companies(), stage=mc.STAGE_DAY1,
    )
    assert "핵심 딜 3개사 간단히 공유드립니다." in result.text


def test_compose_remind_omits_companies():
    result = mc.compose_message(
        "{담당자명}님 안녕하세요", "검토 중 궁금한 점 있으시면 말씀 주세요.",
        _contact(), _companies(), stage=mc.STAGE_REMIND,
    )
    assert "[1]" not in result.text
    assert "샘플애그" not in result.text
    assert "홍길동님 안녕하세요" in result.text


def test_compose_flags_too_long():
    big_company = CompanyView(name="Z", sector_major="AI", one_liner="가" * 4000)
    result = mc.compose_message("안녕", "끝", _contact(), [big_company], stage=mc.STAGE_DAY1)
    assert result.too_long is True
    assert result.char_count > mc.MESSAGE_WARN_CHARS
    assert any("초과" in w for w in result.warnings)


def test_compose_normal_length_not_flagged():
    result = mc.compose_message("안녕", "끝", _contact(), _companies(), stage=mc.STAGE_DAY1)
    assert result.too_long is False


# --- 직함이 어색하게 붙는 것 ------------------------------------------------
#
# 두 가지가 섞여 있었다. 원인이 다르니 고치는 자리도 다르다.
#   1) **이름 칸에 직함이 같이 적힌 줄** — 딜 소싱 명단이 그렇다. 직함을 또
#      붙여 '… 대리 심사역 심사역님' 이 나갔다.
#   2) **직함 칸에 여러 직함이 이어진 줄** — 명함에 겸직·자격을 함께 적어 둔다.
#      '팀장 / 수석심사역님' 은 인사말로 읽히지 않는다.
#
# 어느 쪽도 **저장된 값은 고치지 않는다.** 부를 때만 다듬는다.
# 이름은 전부 가상값이다(공개 저장소).

GREETING = "안녕하세요, {담당자명} {직함}"


def _greet(name, title=""):
    return mc.render_template(GREETING, mc.ContactView(name=name, title=title))


def test_name_that_already_carries_a_title_gets_only_one():
    """사용자가 실제로 받은 문구: '… 대리 심사역 심사역님'.

    딜 소싱은 직함 칸이 비면 갈래에서 '심사역' 을 끌어다 쓴다. 이름 칸에 이미
    직함이 적혀 있으면 그게 두 번이 된다.
    """
    assert _greet("최가온 대리 심사역", "심사역") == "안녕하세요, 최가온 대리 심사역님"
    assert _greet("박서준 수석심사역 팀장", "심사역") == "안녕하세요, 박서준 수석심사역 팀장님"
    assert _greet("강민재 대리", "심사역") == "안녕하세요, 강민재 대리님"
    assert _greet("김도윤 실장", "심사역") == "안녕하세요, 김도윤 실장님"
    # 빗금으로 이어 적은 것도 이름 칸에 온다.
    assert _greet("김하늘 이사/변호사", "심사역") == "안녕하세요, 김하늘 이사/변호사님"


def test_a_name_that_merely_looks_like_a_title_is_left_alone():
    """'김이사' 는 이름이다 — 직함으로 읽어 잘라 내면 사람 이름이 사라진다."""
    assert _greet("김이사", "심사역") == "안녕하세요, 김이사 심사역님"
    assert mc.name_carries_title("김이사") is False
    assert mc.name_carries_title("정다인") is False
    # 낱말이 떨어져 있을 때만 직함으로 본다.
    assert mc.name_carries_title("정다인 이사") is True


def test_several_titles_use_the_first_one():
    """겸직·자격을 함께 적은 칸은 **앞의 하나**로 부른다."""
    assert _greet("한지우", "팀장 / 수석심사역") == "안녕하세요, 한지우 팀장님"
    assert _greet("오세훈", "부장 / 본부장 / FRM") == "안녕하세요, 오세훈 부장님"
    assert _greet("이나래", "이사/공인회계사") == "안녕하세요, 이나래 이사님"
    assert mc.primary_title("팀장 / 수석심사역") == "팀장"
    assert mc.primary_title("책임심사역") == "책임심사역"
    assert mc.primary_title("") == ""


def test_the_stored_title_is_never_rewritten():
    """다듬는 것은 **문구뿐**이다 — 사람이 적어 둔 명함 값은 그대로 둔다."""
    who = mc.ContactView(name="한지우", title="팀장 / 수석심사역")
    mc.render_template(GREETING, who)
    assert who.title == "팀장 / 수석심사역"
    assert who.name == "한지우"


def test_ordinary_titles_are_unchanged():
    """멀쩡하던 것은 그대로여야 한다."""
    assert _greet("정다인", "심사역") == "안녕하세요, 정다인 심사역님"
    assert _greet("류시원", "책임심사역") == "안녕하세요, 류시원 책임심사역님"
    assert _greet("김선호", "대표님") == "안녕하세요, 김선호 대표님"
    # 직함이 아예 없으면 이름에 존칭만.
    assert _greet("정다인", "") == "안녕하세요, 정다인님"


def test_room_names_keep_their_own_vocabulary():
    """방 이름은 카톡 창 제목과 글자까지 같아야 한다 — 어휘를 넓히지 않았다.

    인사말에서만 인정하는 '대리' 로 방 이름이 갈리면, 이미 연결해 둔 방과
    어긋나 발송이 조용히 건너뛰어진다.
    """
    from app.services import room_name

    assert room_name.split_name_title("강민재 대리") == ("강민재 대리", None)
    assert room_name.looks_like_title("대리") is False
    assert room_name.looks_like_title("대리", ("대리",)) is True
    assert room_name.looks_like_title("이사") is True
