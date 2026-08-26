"""구글시트 임포트 파서·업서트 테스트 (ROADMAP 2.1).

픽스처 CSV(tests/fixtures/*.csv)는 실제 시트 **구조**만 흉내낸 가상 데이터다
(헤더 2행 · 데이터 4행부터 · 월별 3열 세트 반복 · 이름+직함 합침).
"""
from sqlalchemy import select

from app.models import ContactActivity, IrCompany, User, VcContact
from app.services import sheet_import as si

from .conftest import FIXTURES

YEAR = 2026


def _rows_a():
    """딜소개 현황 시트(월별 3열 세트가 있는 메인 명단)."""
    return si.read_csv(FIXTURES / "sheet_a_sample.csv")


def _rows_a_list():
    """연결 명단 시트(컬럼 구성이 다른 두 번째 투자사 명단)."""
    return si.read_csv(FIXTURES / "sheet_a_list_sample.csv")


def _rows_b():
    return si.read_csv(FIXTURES / "sheet_b_sample.csv")


def _rows_b_startups():
    """스타트업 명단(기업 쪽 연락 담당자가 있는 기업 시트)."""
    return si.read_csv(FIXTURES / "sheet_b_startups_sample.csv")


# ── 헤더/컬럼 탐지 ──────────────────────────────────────────────────────────

def test_header_row_is_detected_not_hardcoded():
    """헤더는 2행(0-based 1). 인덱스를 박지 않고 탐지한다."""
    rows = _rows_a()
    assert si.detect_header_row(rows, ["그룹", "이름", "투자사"]) == 1


def test_header_detection_survives_inserted_rows():
    """시트 위에 행이 추가돼도 헤더를 따라간다 (사람이 계속 편집하는 문서라서)."""
    rows = [["메모"], [""]] + _rows_a()
    assert si.detect_header_row(rows, ["그룹", "이름", "투자사"]) == 3


def test_month_columns_are_scanned_repeatedly():
    """3열 세트가 8→7→6월로 반복된다. 월 라벨은 병합 셀이라 첫 칸에만 있다."""
    rows = _rows_a()
    cols = si.detect_activity_columns(rows, header_idx=1, year=YEAR, skip_cols=range(0, 7))
    assert [(c.month, c.kind) for c in cols] == [
        ("2026-08", si.KIND_DEAL_INTRO),
        ("2026-08", si.KIND_IR_REQUEST),
        ("2026-08", si.KIND_MEETING),
        ("2026-07", si.KIND_DEAL_INTRO),
        ("2026-07", si.KIND_IR_REQUEST),
        ("2026-07", si.KIND_MEETING),
        ("2026-06", si.KIND_DEAL_INTRO),
        ("2026-06", si.KIND_IR_REQUEST),
        ("2026-06", si.KIND_MEETING),
    ]


def test_the_year_moves_when_the_months_cross_january():
    """12월 옆 1월을 같은 해로 두면 그 달 회차가 1년 전 자리에 쌓인다.

    방향은 시트마다 다르다 — 명단 시트는 최신 달이 왼쪽이라 달이 줄고,
    새로 만든 표는 늘기도 한다.
    """
    def scan(labels):
        rows = [[""] * 3, ["NO", "이름", "투자사명"]]
        for label in labels:
            rows[0] += [label, "", ""]
            rows[1] += ["1차 딜소개", "IR 요청", "미팅"]
        cols = si.detect_activity_columns(rows, header_idx=1, year=YEAR,
                                          skip_cols=range(0, 3))
        # 3열 세트라 달마다 같은 값이 세 번 — 순서를 지켜 중복만 접는다
        seen = []
        for c in cols:
            if not seen or seen[-1] != c.month:
                seen.append(c.month)
        return seen

    # 오른쪽이 나중 (11월 → 12월 → 1월 → 2월)
    assert scan(["11월", "12월", "1월", "2월"]) == [
        "2026-11", "2026-12", "2027-01", "2027-02"]

    # 오른쪽이 이전 (2월 → 1월 → 12월 → 11월) — 실제 명단 시트의 방향
    assert scan(["2월", "1월", "12월", "11월"]) == [
        "2026-02", "2026-01", "2025-12", "2025-11"]


def test_a_month_that_merely_goes_backwards_does_not_move_the_year():
    """8→7→6월은 해가 바뀐 것이 아니다 — 경계에서만 옮긴다."""
    rows = _rows_a()
    cols = si.detect_activity_columns(rows, header_idx=1, year=YEAR, skip_cols=range(0, 7))
    assert {c.month[:4] for c in cols} == {"2026"}


def test_activity_columns_extend_when_a_new_month_is_added():
    """9월 세트가 오른쪽에 추가돼도 코드 수정 없이 잡힌다 (시트가 계속 늘어나는 구조)."""
    rows = [list(r) for r in _rows_a()]
    rows[0] += ["9월", "", ""]
    rows[1] += ["1차 딜소개", "IR 자료 요청 기업", "미팅 요청"]
    cols = si.detect_activity_columns(rows, header_idx=1, year=YEAR, skip_cols=range(0, 7))
    assert [(c.month, c.kind) for c in cols][-3:] == [
        ("2026-09", si.KIND_DEAL_INTRO),
        ("2026-09", si.KIND_IR_REQUEST),
        ("2026-09", si.KIND_MEETING),
    ]


# ── 셀 파싱 ─────────────────────────────────────────────────────────────────

def test_deal_intro_cell_splits_into_rounds():
    cell = "8/4(화) 핵심 딜 8개사\n\n8/13(목) 샘플애그, 샘플메디\n8/19(수) 샘플페이"
    acts = si.parse_activity_cell(cell, "2026-08", si.KIND_DEAL_INTRO, YEAR)
    assert [(a.happened_at, a.content) for a in acts] == [
        ("2026-08-04", "핵심 딜 8개사"),
        ("2026-08-13", "샘플애그, 샘플메디"),
        ("2026-08-19", "샘플페이"),
    ]


def test_continuation_line_joins_previous_round():
    """기업 목록이 다음 줄로 넘어가도 별도 회차로 쪼개지 않는다."""
    acts = si.parse_activity_cell("8/19(수) 샘플페이,\n샘플로지, 샘플에듀",
                                  "2026-08", si.KIND_DEAL_INTRO, YEAR)
    assert len(acts) == 1
    assert acts[0].content == "샘플페이, 샘플로지, 샘플에듀"


def test_numbered_company_list_is_split():
    """7월 형식: '1.(주)샘플가  2.샘플나  3.체인샘플' (구분자가 이중공백)."""
    acts = si.parse_activity_cell("7/9(목) 1.(주)샘플가  2.샘플나  3.체인샘플",
                                  "2026-07", si.KIND_DEAL_INTRO, YEAR)
    assert len(acts) == 1
    assert acts[0].companies == ["(주)샘플가", "샘플나", "체인샘플"]
    assert acts[0].company_count == 3
    assert acts[0].weekday == "목"
    assert acts[0].happened_at == "2026-07-09"


def test_comma_company_list_is_split():
    acts = si.parse_activity_cell("8/13(목) 샘플애그, 샘플메디", "2026-08",
                                  si.KIND_DEAL_INTRO, YEAR)
    assert acts[0].companies == ["샘플애그", "샘플메디"] and acts[0].company_count == 2


def test_count_only_round_keeps_number_without_inventing_names():
    """'핵심 딜 8개사' — 기업명이 없다. 없는 목록을 지어내지 않는다."""
    acts = si.parse_activity_cell("8/4(화) 핵심 딜 8개사", "2026-08",
                                  si.KIND_DEAL_INTRO, YEAR)
    assert acts[0].companies == [] and acts[0].company_count == 8


def test_raw_text_is_kept_for_traceability():
    """파싱이 틀렸을 때 원문을 볼 수 있어야 한다."""
    acts = si.parse_activity_cell("8/19(수) 샘플페이,\n샘플로지", "2026-08",
                                  si.KIND_DEAL_INTRO, YEAR)
    assert acts[0].raw_text == "8/19(수) 샘플페이,\n샘플로지"


def test_weekday_falls_back_to_the_date_when_not_written():
    acts = si.parse_activity_cell("8/13 샘플애그", "2026-08", si.KIND_DEAL_INTRO, YEAR)
    assert acts[0].weekday == "목"      # 2026-08-13 은 목요일


def test_year_follows_the_month_column_not_only_the_flag():
    """연말·연초가 섞인 시트: 컬럼의 월 라벨이 붙인 연도를 따른다."""
    acts = si.parse_activity_cell("1/8(목) 샘플애그", "2027-01", si.KIND_DEAL_INTRO, YEAR)
    assert acts[0].happened_at == "2027-01-08"


def test_week_of_month_matches_sheet_wording():
    """시트 헤더의 '첫째주 수요일 / 셋째주' 표기와 맞춘다."""
    assert si.week_of_month("2026-08-04") == 1
    assert si.week_of_month("2026-08-19") == 3


def test_company_name_normalization_for_matching():
    """법인 표기는 비교용으로만 떼고, 저장은 원문 그대로 한다."""
    assert si.normalize_company_name("(주)샘플가") == "샘플가"
    assert si.normalize_company_name("㈜샘플가") == "샘플가"
    assert si.normalize_company_name("주식회사 샘플가") == "샘플가"


def test_cell_without_date_keeps_raw_text():
    acts = si.parse_activity_cell("검토 중", "2026-07", si.KIND_MEETING, YEAR)
    assert len(acts) == 1 and acts[0].happened_at is None and acts[0].content == "검토 중"


def test_invalid_date_is_not_forced():
    """13/40 같은 값은 날짜로 만들지 않는다 (없는 날짜를 지어내지 않음)."""
    acts = si.parse_activity_cell("13/40 뭔가", None, si.KIND_MEETING, YEAR)
    assert acts[0].happened_at is None


def test_sector_tags_only_when_clearly_tags():
    assert si.split_sector_tags("AI, 헬스케어") == ["AI", "헬스케어"]
    # 자유 서술은 태그로 만들지 않는다 — 잘못된 태그는 발송 전 성향 경고를 오염시킨다.
    assert si.split_sector_tags("8/19 : 초기 기업보다는 성장단계 기업들 위주로 검토") == []
    assert si.split_sector_tags("라운드 30~100억") == []


def test_is_invited_variants():
    assert si.is_invited("완료") and si.is_invited("O") and si.is_invited("초대완료")
    assert not si.is_invited("") and not si.is_invited("미완")


# ── 시트 A 전체 ─────────────────────────────────────────────────────────────

def test_parse_sheet_a_rows_and_skips():
    parsed = si.parse_sheet_a(_rows_a(), year=YEAR)
    names = [c.name for c in parsed.contacts]
    assert names == ["홍길동", "김서연", "박준호", "이서준", "정민아"]

    reasons = {s.reason for s in parsed.skipped}
    assert "비정형 행(이름 아님)" in reasons   # temp_login 문자열 행
    assert "투자사명 없음" in reasons          # 방 이름을 만들 수 없는 행
    assert len(parsed.skipped) == 2            # 완전 빈 행은 잡음이라 리포트에 넣지 않는다


def test_name_and_title_are_split():
    parsed = si.parse_sheet_a(_rows_a(), year=YEAR)
    by_name = {c.name: c for c in parsed.contacts}
    assert by_name["홍길동"].title == "대표님"
    assert by_name["김서연"].title == "심사역"
    assert by_name["정민아"].title == "수석심사역"
    # 직함으로 확신할 수 없으면 통째로 이름 (잘못 분리하면 방 이름이 틀어진다)
    assert by_name["박준호"].title is None


def test_free_text_profile_goes_to_round_size_not_sectors():
    parsed = si.parse_sheet_a(_rows_a(), year=YEAR)
    by_name = {c.name: c for c in parsed.contacts}
    assert by_name["김서연"].profile_raw.startswith("8/19 :")
    assert by_name["김서연"].sectors == []
    assert by_name["박준호"].sectors == ["AI", "헬스케어"]


def test_apply_sheet_a_creates_contacts_activities_and_room_names(db, users):
    parsed = si.parse_sheet_a(_rows_a(), year=YEAR)
    report = si.apply_sheet_a(db, parsed, user_id=1)

    assert report.created == 5 and report.updated == 0
    hong = db.execute(select(VcContact).where(VcContact.name == "홍길동")).scalar_one()
    # 시트의 이름·직함·투자사만으로 방 이름을 자동 생성한다(126명 수기 입력 회피)
    assert hong.kakao_room_name == "홍길동 대표님 가나벤처스 Deal 공유 우리브이씨 Asset"
    assert hong.invited_status == "완료" and hong.channel_kakao == 1
    assert hong.user_id == 1

    acts = db.execute(
        select(ContactActivity).where(ContactActivity.contact_id == hong.id)
    ).scalars().all()
    # 8월: 딜소개 3회차 + IR 1 + 미팅 1, 7월 딜소개 1, 6월 딜소개 1 = 7건
    assert len(acts) == 7
    assert {a.month for a in acts} == {"2026-08", "2026-07", "2026-06"}
    assert {a.kind for a in acts} == {"deal_intro", "ir_request", "meeting"}
    assert all(a.source == "import" for a in acts)


def test_apply_sheet_a_is_idempotent(db, users):
    rows = _rows_a()
    si.apply_sheet_a(db, si.parse_sheet_a(rows, year=YEAR), user_id=1)
    before = db.query(ContactActivity).count()

    second = si.apply_sheet_a(db, si.parse_sheet_a(rows, year=YEAR), user_id=1)
    assert second.created == 0 and second.updated == 5
    assert second.activities_created == 0 and second.activities_existing == before
    assert db.query(VcContact).count() == 5
    assert db.query(ContactActivity).count() == before


def test_reimport_keeps_manually_fixed_room_name(db, users):
    """사용자가 실제 카톡 제목에 맞춰 고친 방 이름을 임포트가 되돌리면 안 된다.

    방 제목이 틀리면 그 담당자 발송이 통째로 skip 되므로 손대지 않는 쪽이 안전하다.
    """
    rows = _rows_a()
    si.apply_sheet_a(db, si.parse_sheet_a(rows, year=YEAR), user_id=1)
    hong = db.execute(select(VcContact).where(VcContact.name == "홍길동")).scalar_one()
    hong.kakao_room_name = "홍길동 대표님 가나벤처스 (수정됨)"
    db.commit()

    si.apply_sheet_a(db, si.parse_sheet_a(rows, year=YEAR), user_id=1)
    db.refresh(hong)
    assert hong.kakao_room_name == "홍길동 대표님 가나벤처스 (수정됨)"


def test_deal_rounds_are_stored_with_companies_and_weekday(db, users):
    """월별 딜소개 회차를 화면에서 조회할 수 있게 구조화해 저장한다."""
    si.apply_sheet_a(db, si.parse_sheet_a(_rows_a(), year=YEAR), user_id=1)
    hong = db.execute(select(VcContact).where(VcContact.name == "홍길동")).scalar_one()
    rounds = [a for a in db.execute(
        select(ContactActivity).where(ContactActivity.contact_id == hong.id,
                                      ContactActivity.kind == "deal_intro")
    ).scalars().all()]
    by_date = {a.happened_at: a for a in rounds}

    assert by_date["2026-08-04"].company_count == 8
    assert by_date["2026-08-04"].companies == []          # 개수만 적힌 회차
    assert by_date["2026-08-13"].companies == ["샘플애그", "샘플메디"]
    assert by_date["2026-08-13"].weekday == "목"
    assert by_date["2026-08-13"].raw_text.startswith("8/13(목)")


def test_owner_comes_from_the_sheet_column(db, users):
    """한 시트에 여러 팀원의 담당분이 섞여 있다 → 담당자 컬럼이 소유자를 정한다."""
    db.add(User(id=3, name="정훈", phone="01000000003"))
    db.add(User(id=4, name="김영희", phone="01000000004"))
    db.commit()

    report = si.apply_sheet_a(db, si.parse_sheet_a(_rows_a(), year=YEAR), user_id=1)
    owners = {c.name: c.user_id for c in db.query(VcContact).all()}
    assert owners["홍길동"] == 3       # 담당자 '정훈'
    assert owners["정민아"] == 4       # 담당자 '김영희'
    # 계정이 없는 담당자·빈 담당자는 **버리지 않고** 폴백으로 배정하고 리포트에 남긴다
    assert owners["박준호"] == 1 and owners["이서준"] == 1
    assert any("없는담당자" in n for n in report.notes)
    assert any("담당자 칸이 빈 행" in n for n in report.notes)


def test_owner_is_not_stolen_by_a_sheet_without_the_column(db, users):
    """담당자 칸이 없는 시트를 나중에 임포트해도 이미 정해진 담당을 뺏지 않는다."""
    db.add(User(id=3, name="정훈", phone="01000000003"))
    db.commit()
    si.apply_sheet_a(db, si.parse_sheet_a(_rows_a(), year=YEAR), user_id=1)

    rows = [list(r) for r in _rows_a()]
    for row in rows[1:]:
        if len(row) > 4:
            row[4] = ""      # 담당자 컬럼을 비운 시트
    si.apply_sheet_a(db, si.parse_sheet_a(rows, year=YEAR), user_id=2)

    hong = db.execute(select(VcContact).where(VcContact.name == "홍길동")).scalar_one()
    assert hong.user_id == 3


# ── 두 번째 명단 시트(컬럼 구성이 다름) ─────────────────────────────────────

def test_second_list_sheet_uses_the_same_parser():
    """컬럼이 달라도 헤더 이름으로 찾으므로 같은 파서가 읽는다."""
    parsed = si.parse_sheet_a(_rows_a_list(), year=YEAR)
    by_name = {c.name: c for c in parsed.contacts}
    assert set(by_name) == {"홍길동", "한지우", "서동현"}

    hong = by_name["홍길동"]
    assert hong.firm == "가나벤처스"          # '딜소싱 참여 투자사' 칸에 속지 않는다
    assert hong.owner_name == "정훈"
    assert hong.interest_level == "O" and hong.kakao_joined == "완료"
    assert hong.title == "대표"               # 직책 컬럼이 있으면 그쪽이 우선
    assert hong.sectors == ["애그테크", "커머스"]
    assert hong.round_size == "10~30억"
    assert hong.phone and hong.office_phone and hong.address
    assert parsed.activity_columns == []      # 이 시트엔 월별 컬럼이 없다


def test_same_person_across_sheets_is_merged_not_duplicated(db, users):
    """같은 사람이 여러 명단 시트에 나뉘어 있다 → (이름+투자사)로 병합한다."""
    si.apply_sheet_a(db, si.parse_sheet_a(_rows_a(), year=YEAR), user_id=1,
                     source_label="딜소개현황")
    before = db.query(VcContact).count()

    report = si.apply_sheet_a(db, si.parse_sheet_a(_rows_a_list(), year=YEAR), user_id=1,
                              source_label="연결명단")
    assert report.created == 2 and report.updated == 1        # 홍길동만 기존 행
    assert db.query(VcContact).count() == before + 2

    hong = db.execute(select(VcContact).where(VcContact.name == "홍길동")).scalar_one()
    assert hong.interest_level == "O"                         # 두 번째 시트에서 채워짐
    assert hong.title == "대표님"                              # 먼저 들어온 값은 지키고
    assert hong.source_sheet == "딜소개현황,연결명단"           # 어디서 왔는지 추적 가능


# ── 시트 B ──────────────────────────────────────────────────────────────────

def test_parse_sheet_b_maps_columns():
    parsed = si.parse_sheet_b(_rows_b(), year=YEAR)
    by_name = {c.name: c for c in parsed.companies}
    assert set(by_name) == {"샘플애그", "샘플메디", "샘플페이", "샘플로지"}

    ag = by_name["샘플애그"]
    assert ag.sector_major == "애그테크" and ag.sector_minor == "B2B 유통"
    assert ag.series == "SeriesA" and ag.contract_status == "yes"
    assert ag.contract_month == "2026-07" and ag.is_top_deal == 1
    assert ag.ir_drive_url == "https://drive.example.com/file/sample-ag"

    medi = by_name["샘플메디"]
    # deck '유' 인데 링크를 모르면 사실만 비고에 남기고 URL은 화면에서 수기 등록
    assert medi.ir_drive_url is None and "IR deck 보유" in medi.note
    assert medi.contract_status == "pending"

    pay = by_name["샘플페이"]
    assert pay.contract_status == "no" and pay.is_top_deal == 1

    assert [s.reason for s in parsed.skipped] == ["기업명 없음"]


def test_apply_sheet_b_upsert_and_owner_matching(db, users):
    db.add(User(id=3, name="정훈", phone="01000000003"))
    db.commit()

    parsed = si.parse_sheet_b(_rows_b(), year=YEAR)
    report = si.apply_sheet_b(db, parsed)
    assert report.created == 4

    ag = db.execute(select(IrCompany).where(IrCompany.name == "샘플애그")).scalar_one()
    assert ag.owner_user_id == 3
    # 계정이 없는 담당자는 비워두고 리포트에만 남긴다(엉뚱한 사람에게 붙이지 않는다)
    pay = db.execute(select(IrCompany).where(IrCompany.name == "샘플페이")).scalar_one()
    assert pay.owner_user_id is None
    assert any("없는담당자" in n for n in report.notes)

    again = si.apply_sheet_b(db, si.parse_sheet_b(_rows_b(), year=YEAR))
    assert again.created == 0 and again.updated == 4
    assert db.query(IrCompany).count() == 4


def test_startup_sheet_adds_company_side_contacts(db, users):
    """'스타트업' 명단은 기업 쪽 연락 담당자를 담고 있다(우리 팀 담당자와 다른 사람)."""
    si.apply_sheet_b(db, si.parse_sheet_b(_rows_b(), year=YEAR))
    si.apply_sheet_b(db, si.parse_sheet_b(_rows_b_startups(), year=YEAR))

    ag = db.execute(select(IrCompany).where(IrCompany.name == "샘플애그")).scalar_one()
    assert ag.contact_name == "구도현" and ag.contact_email == "sample-ag@example.com"
    # 앞 시트에서 온 정보는 유지된다(병합이지 덮어쓰기가 아니다)
    assert ag.sector_major == "애그테크"
    assert db.query(IrCompany).count() == 5     # 샘플에듀 1개만 새로 생김


def test_dry_run_writes_nothing(db, users):
    si.apply_sheet_a(db, si.parse_sheet_a(_rows_a(), year=YEAR), user_id=1, dry_run=True)
    assert db.query(VcContact).count() == 0
    assert db.query(ContactActivity).count() == 0

# --- 머리글이 다른 표가 아래로 이어 붙는 경우 --------------------------------
#
# 실제 시트(`투자사 98명`)가 그랬다. 머리글과 칸 구성이 다른 블록 61줄이
# 아래에 붙어 있었고, 그대로 읽어 **회사 칸에 주소가, 선호분야 칸에 휴대폰이**
# 들어간 가짜 담당자 58명이 만들어졌다.
#
# 칸을 짐작해서 맞추지 않는다 — 어긋난 줄은 이유를 적어 건너뛴다.
# 맞춰 넣으려다 틀리면 어느 칸이 틀렸는지도 알 수 없다.

def _shifted_sheet():
    return [
        ["NO", "이름", "담당자", "선호 투자분야", "휴대폰", "회사", "부서"],
        ["1", "홍길동", "김담당", "AI", "010-0000-0001", "가나벤처스", "투자1본부"],
        # 아래는 칸이 밀린 블록 — 이름 자리에 라벨, 회사 자리에 주소
        ["", "담당자2", "X", "010-0000-0002", "다라인베스트", "서울시 구로구 디지털로26길 38", ""],
        ["", "이서준", "김담당", "", "010-0000-0003",
         "서울특별시 영등포구 국제금융로8길 32", ""],
    ]


def test_a_label_in_the_name_column_is_not_a_person():
    parsed = si.parse_sheet_a(_shifted_sheet(), YEAR)
    assert [c.name for c in parsed.contacts] == ["홍길동"]
    reasons = {s.reason for s in parsed.skipped}
    assert "머리글과 칸이 어긋난 줄(이름 자리에 라벨)" in reasons


def test_an_address_in_the_firm_column_means_the_row_is_shifted():
    """이름이 멀쩡해도 나머지가 밀려 있을 수 있다."""
    parsed = si.parse_sheet_a(_shifted_sheet(), YEAR)
    assert "이서준" not in [c.name for c in parsed.contacts]
    assert "머리글과 칸이 어긋난 줄(회사 자리에 주소)" in {s.reason for s in parsed.skipped}


def test_a_real_firm_name_is_not_mistaken_for_an_address():
    """너무 넓게 잡으면 멀쩡한 투자사가 통째로 사라진다."""
    for firm in ["가나벤처스", "다라인베스트먼트", "마바캐피탈",
                 "TYCHE PARTNERS", "한국투자파트너스", "IBK기업은행"]:
        assert not si.looks_like_address(firm), firm
    for address in ["서울시 구로구 디지털로26길 38 지타워 10층",
                    "대전광역시 유성구 은구비남로 7번길 37 4층",
                    "경기도 성남시 분당구 판교로 255"]:
        assert si.looks_like_address(address), address

