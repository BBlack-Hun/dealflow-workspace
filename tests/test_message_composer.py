"""Unit tests for the message composer (ROADMAP task 1.4)."""
from app.services import message_composer as mc
from app.services.message_composer import CompanyView, ContactView


# --- format_eok -----------------------------------------------------------

def test_format_eok_decimal():
    assert mc.format_eok(3090) == "30.9"   # 백만원 -> 억


def test_format_eok_whole_number_strips_decimal():
    assert mc.format_eok(5000) == "50"
    assert mc.format_eok(20000) == "200"


def test_format_eok_small_fraction():
    assert mc.format_eok(560) == "5.6"


def test_format_eok_none_returns_none():
    assert mc.format_eok(None) is None


# --- auto_company_summary --------------------------------------------------

def test_auto_summary_full():
    c = CompanyView(
        name="샘플애그", sector_major="애그테크",
        one_liner="B2B 농산물 선도거래 'Presell'",
        revenue_recent=3090, funding_total=560, raise_target=2000,
        pre_value=21000, competitiveness="상급 유통사 12곳 계약",
    )
    summary = mc.auto_company_summary(c)
    assert summary == (
        "[애그테크] | B2B 농산물 선도거래 'Presell' | 매출 30.9억 | "
        "누적투자금액 5.6억 | 20억 투자유치중 | Pre Value 약 210억원 | 상급 유통사 12곳 계약"
    )


def test_auto_summary_omits_empty_segments():
    """Empty values must drop the whole segment (no '매출 억')."""
    c = CompanyView(name="빈기업", sector_major="AI", one_liner="한줄 소개")
    summary = mc.auto_company_summary(c)
    assert summary == "[AI] | 한줄 소개"
    assert "매출" not in summary
    assert "억" not in summary
    assert "Pre Value" not in summary


def test_company_summary_prefers_manual_override():
    c = CompanyView(name="X", sector_major="AI", one_liner="auto",
                    summary="사람이 다듬은 요약문")
    assert mc.company_summary(c) == "사람이 다듬은 요약문"


def test_company_summary_falls_back_to_auto():
    c = CompanyView(name="X", sector_major="AI", one_liner="auto", summary="   ")
    assert mc.company_summary(c) == "[AI] | auto"


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
        CompanyView(name="샘플애그", sector_major="애그테크", one_liner="선도거래", revenue_recent=3090),
        CompanyView(name="샘플메디", sector_major="헬스케어", one_liner="뇌영상 AI"),
        CompanyView(name="세번째", sector_major="핀테크", one_liner="결제"),
    ]


def test_compose_day1_structure():
    opening = "안녕하세요 {담당자명} {직함}님, 딜소개드립니다."
    closing = "관심 가시는 기업 있으시면 IR Deck 공유드리겠습니다."
    result = mc.compose_message(opening, closing, _contact(), _companies(), stage=mc.STAGE_DAY1)
    text = result.text
    assert text.startswith("안녕하세요 홍길동 대표님, 딜소개드립니다.")
    # 실제 운영 문구 형식: 번호는 "1)", 안내문은 목록 '위'에 온다.
    assert "1) [애그테크] | 선도거래 | 매출 30.9억" in text
    assert "2) [헬스케어] | 뇌영상 AI" in text
    assert "3) [핀테크] | 결제" in text
    assert text.index("관심 가시는 기업") < text.index("1) ")
    assert text.rstrip().endswith("3) [핀테크] | 결제")
    # blank line separators between blocks
    assert "\n\n1)" in text
    assert "\n\n2)" in text


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
