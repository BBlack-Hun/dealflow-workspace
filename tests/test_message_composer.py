"""Unit tests for the message composer (ROADMAP task 1.4)."""
from app.services import message_composer as mc
from app.services.message_composer import CompanyView, ContactView


# --- format_eok -------------------------------------------------------------
#
# 저장이 백만원 정수에서 **사람이 적은 글자(억)** 로 바뀌었다(0074). `format_eok`
# 은 이제 그 글자에서 **문구에 실을 수량**을 고르는 일을 하고, 고르는 판단은
# `services/amount.py` 한 곳에 있다.

def test_format_eok_passes_the_written_number_through():
    """옛 정수가 옮겨진 글자(`3090` → `"30.9"`)가 그대로 지나야 한다."""
    assert mc.format_eok("30.9") == "30.9"
    assert mc.format_eok("50") == "50"
    assert mc.format_eok("200") == "200"
    assert mc.format_eok("5.6") == "5.6"


def test_format_eok_keeps_a_range_a_range():
    """`5-10억 사이` 라고 적었으면 문구에도 구간이 남아야 한다."""
    assert mc.format_eok("5-10억 사이") == "5~10"
    assert mc.format_eok("5~10억") == "5~10"


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

    for written in ("30.9", "5-10억 사이", "0", "~", "말도 안 되는 값"):
        assert mc.format_eok(written) == amount.quantity(written), written


# --- auto_company_summary --------------------------------------------------

def test_auto_summary_full():
    c = CompanyView(
        name="샘플애그", sector_major="애그테크",
        one_liner="B2B 농산물 선도거래 'Presell'",
        revenue_recent="30.9", funding_total="5.6", raise_target="20",
        pre_value="210", competitiveness="상급 유통사 12곳 계약",
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
