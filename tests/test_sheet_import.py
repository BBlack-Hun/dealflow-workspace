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
    return si.read_csv(FIXTURES / "sheet_a_sample.csv")


def _rows_b():
    return si.read_csv(FIXTURES / "sheet_b_sample.csv")


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
    cols = si.detect_activity_columns(rows, header_idx=1, start_col=6, year=YEAR)
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


def test_activity_columns_extend_when_a_new_month_is_added():
    """9월 세트가 오른쪽에 추가돼도 코드 수정 없이 잡힌다 (시트가 계속 늘어나는 구조)."""
    rows = [list(r) for r in _rows_a()]
    rows[0] += ["9월", "", ""]
    rows[1] += ["1차 딜소개", "IR 자료 요청 기업", "미팅 요청"]
    cols = si.detect_activity_columns(rows, header_idx=1, start_col=6, year=YEAR)
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


def test_sheet_a_scopes_contacts_to_the_given_user(db, users):
    """시트 1개 = 사용자 1명. 같은 이름이어도 사용자별로 따로 쌓인다."""
    rows = _rows_a()
    si.apply_sheet_a(db, si.parse_sheet_a(rows, year=YEAR), user_id=1)
    si.apply_sheet_a(db, si.parse_sheet_a(rows, year=YEAR), user_id=2)
    assert db.query(VcContact).filter_by(user_id=1).count() == 5
    assert db.query(VcContact).filter_by(user_id=2).count() == 5


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


def test_dry_run_writes_nothing(db, users):
    si.apply_sheet_a(db, si.parse_sheet_a(_rows_a(), year=YEAR), user_id=1, dry_run=True)
    assert db.query(VcContact).count() == 0
    assert db.query(ContactActivity).count() == 0
