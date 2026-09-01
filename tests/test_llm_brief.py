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
import shutil
import subprocess
from pathlib import Path

import pytest
from sqlalchemy import String, Text

from .conftest import DEMO_PASSWORD

# 날짜가 바뀌어도 안 깨지게 못 박는다.
FIXED_NOW = "2026-09-01T09:00:00+09:00"

# 내보내도 되는 투자사 칸. **이 목록은 검사가 직접 들고 있다**(위 설명 참고).
CONTACT_COLUMNS_ALLOWED_OUT = {
    "sectors", "round_size", "stages",
    "sourcing_note", "memo", "tips_note", "interest_level",
}
# IR 기업은 소개하려고 모은 자료라 **이름이 나간다** — 그것 말고는 마찬가지다.
# 특히 기업 쪽 연락 담당자(`contact_name`·`contact_phone`·`contact_email`)는
# 나가면 안 된다.
COMPANY_COLUMNS_ALLOWED_OUT = {
    "name", "sector_major", "series", "one_liner", "summary",
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


def _company(db, **kw):
    from app.models import IrCompany

    values = dict(name="가상바이오", sector_major="바이오", series="Series A",
                  one_liner="세포 배양 장비", revenue_recent=1830)
    values.update(kw)
    row = IrCompany(**values)
    db.add(row)
    db.commit()
    return row


def _brief(db, user):
    from app.services import llm_brief

    return llm_brief.brief(db, user, now=FIXED_NOW)


# ── 무엇이 나가는가 ─────────────────────────────────────────────────────────

def test_an_investor_goes_out_as_a_number_and_their_preferences(db, users):
    """맞추는 데 필요한 것만 — 번호 · 선호분야 · 라운드 · 단계 · 메모 · 관심도."""
    row = _contact(db, users["u1"].id, sectors="AI,헬스케어",
                   round_size="건당 30억~100억", stages="Seed,SeriesA",
                   sourcing_note="전화완료", memo="후속 검토 중",
                   tips_note="팁스 운영사", interest_level="높음")

    got = _brief(db, users["u1"])["investors"]
    assert got == [{
        "id": f"V-{row.id}",
        "sectors": "AI,헬스케어",
        "round_size": "건당 30억~100억",
        "stages": "Seed,SeriesA",
        "sourcing_note": "전화완료",
        "memo": "후속 검토 중",
        "tips_note": "팁스 운영사",
        "interest_level": "높음",
        "room_open": True,
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
    assert got == {"id": f"V-{row.id}", "sectors": "AI", "room_open": True}


def test_whether_the_room_is_open_is_the_dashboards_own_judgement(db, users):
    """방 상태는 **대시보드가 세는 그 판정**이다 — 여기서 다시 정하지 않는다.

    두 벌로 적어 두면 화면 숫자와 어긋난다(투자사 관리 현황 117명 · 대시보드
    123명으로 갈렸던 그 사고다). 그래서 판정을 옮겨 적지 않고, 같은 함수가
    말하는 것과 결과가 같은지를 본다 — 갈래가 하나 늘어도 같이 움직인다.
    """
    from app.services.dashboard import _SENDABLE_ROOM, _room_state

    rows = [
        _contact(db, users["u1"].id, room_verified="verified"),
        _contact(db, users["u1"].id, room_verified="unverified"),
        _contact(db, users["u1"].id, room_verified="not_found"),
        _contact(db, users["u1"].id, kakao_room_name=""),        # 방 미등록
        _contact(db, users["u1"].id, channel_kakao=0, channel_email=1),
    ]
    got = {item["id"]: item["room_open"] for item in _brief(db, users["u1"])["investors"]}

    for row in rows:
        assert got[f"V-{row.id}"] == (_room_state(row) in _SENDABLE_ROOM), row.id
    # 다 같은 답이 나오면 검사가 아무것도 안 본 것이다.
    assert set(got.values()) == {True, False}


def test_a_company_goes_out_with_its_name_and_its_own_introducible_flag(db, users):
    """`IrCompany.introducible` 을 **다시 계산하지 않고** 그대로 읽는다."""
    ok = _company(db, name="가상바이오", raise_target=3000, pre_value=12000)
    thin = _company(db, name="가상로보틱스", sector_major="", one_liner="",
                    revenue_recent=None)

    got = {c["id"]: c for c in _brief(db, users["u1"])["companies"]}
    assert got[f"C-{ok.id}"]["name"] == "가상바이오"
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


def test_the_amount_unit_is_declared_once_and_numbers_are_left_alone(db, users):
    """저장은 백만원이다. 바꾸지 않고 단위만 밝힌다 — 두 표기를 같이 내보내면
    언젠가 둘이 어긋나고, 어긋난 쪽을 읽은 답은 100배가 틀어진다."""
    _company(db, revenue_recent=1830, funding_total=500,
             raise_target=3000, pre_value=12000)

    out = _brief(db, users["u1"])
    assert out["amount_unit"] == "백만원"
    got = out["companies"][0]
    assert (got["revenue_recent"], got["funding_total"],
            got["raise_target"], got["pre_value"]) == (1830, 500, 3000, 12000)


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



def _mark_every_other_column(model, row, allowed):
    """내보내면 안 되는 글자 칸마다 그 칸 이름이 든 표식을 심는다.

    **모델의 칸을 훑는다** — 손으로 적은 목록은 칸이 하나 늘 때 낡는다.
    표식에 칸 이름을 넣어 두어서, 걸렸을 때 어느 칸이 샜는지 바로 나온다.
    """
    marks = {}
    for column in model.__table__.columns:
        if column.name in allowed or not isinstance(column.type, (String, Text)):
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

    row = _contact(db, users["u1"].id, sectors="AI")
    marks = _mark_every_other_column(VcContact, row, CONTACT_COLUMNS_ALLOWED_OUT)
    db.commit()

    out = _brief(db, users["u1"])
    assert len(out["investors"]) == 1, "줄이 아예 안 나가면 검사가 아무것도 못 본다"

    dumped = json.dumps(out, ensure_ascii=False)
    leaked = sorted(name for name, mark in marks.items() if mark in dumped)
    assert not leaked, "투자사 자료에 이 칸이 새어 나갔습니다: " + ", ".join(leaked)
    # 표식을 심을 칸이 없으면 위 검사는 언제나 통과한다 — 그것도 잡는다.
    for must in ("name", "firm", "phone", "email", "kakao_room_name"):
        assert must in marks, f"{must} 칸에 표식을 못 심었습니다"


def test_no_company_side_contact_column_leaks_out_even_if_someone_adds_one(db, users):
    """기업은 이름이 나간다 — 그 대신 **기업 쪽 연락처**가 새면 안 된다."""
    from app.models import IrCompany

    row = _company(db, revenue_recent=1830)
    marks = _mark_every_other_column(IrCompany, row, COMPANY_COLUMNS_ALLOWED_OUT)
    # 이름은 나가야 하므로 표식 뒤에 다시 가상 이름을 넣는다.
    row.name = "가상바이오"
    db.commit()

    out = _brief(db, users["u1"])
    assert len(out["companies"]) == 1

    dumped = json.dumps(out, ensure_ascii=False)
    leaked = sorted(name for name, mark in marks.items() if mark in dumped)
    assert not leaked, "기업 자료에 이 칸이 새어 나갔습니다: " + ", ".join(leaked)
    for must in ("contact_name", "contact_phone", "contact_email"):
        assert must in marks, f"{must} 칸에 표식을 못 심었습니다"


def test_the_keys_that_go_out_are_exactly_these(db, users):
    """칸이 조용히 하나 붙는 것을 모양으로도 못 박는다.

    위 표식 검사는 **값**이 새는 것을 잡고, 이것은 **칸**이 느는 것을 잡는다.
    값이 우연히 안 겹치는 칸(숫자·참거짓)이 붙어도 여기서 걸린다.
    """
    _contact(db, users["u1"].id, sectors="AI", round_size="30억", stages="Seed",
             sourcing_note="메모", memo="메모", tips_note="메모", interest_level="높음")
    _company(db, summary="요약", funding_total=500, raise_target=3000, pre_value=12000)

    out = _brief(db, users["u1"])
    assert set(out) == {"generated_at", "scope", "amount_unit", "note",
                        "investors", "companies"}
    assert set(out["investors"][0]) == {
        "id", "sectors", "round_size", "stages",
        "sourcing_note", "memo", "tips_note", "interest_level", "room_open"}
    assert set(out["companies"][0]) == {
        "id", "name", "sector_major", "series", "one_liner", "summary",
        "revenue_recent", "funding_total", "raise_target", "pre_value",
        "introducible"}


def test_the_answer_that_actually_leaves_the_server_has_no_names_in_it(db, users,
                                                                       logged_in):
    """서비스가 아니라 **주소가 실제로 돌려주는 것**을 본다.

    라우터가 뒤에 무엇을 덧붙였을 수도 있다 — 나가는 바이트를 직접 훑는다.
    """
    _contact(db, users["u1"].id, name="홍길동", firm="가나벤처스",
             phone="010-0000-0001", email="hong@example.invalid",
             kakao_room_name="가나벤처스 Deal 공유", title="심사역",
             group_name="가나그룹", assignee_name="김담당", sectors="AI")

    body = logged_in.get("/api/llm-brief.json").text
    for secret in ("홍길동", "가나벤처스", "010-0000-0001", "hong@example.invalid",
                   "가나벤처스 Deal 공유", "심사역", "가나그룹", "김담당"):
        assert secret not in body, f"내보낸 자료에 `{secret}` 이 들어 있습니다"


# ── 누가 받는가 ─────────────────────────────────────────────────────────────

def test_a_member_gets_only_the_contacts_they_manage(db, users):
    """딜 소개는 담당자별로 나간다 — 남의 담당을 추천받아도 보낼 수가 없다."""
    mine = _contact(db, users["u1"].id, sectors="AI")
    theirs = _contact(db, users["u2"].id, sectors="바이오")

    ids = [c["id"] for c in _brief(db, users["u1"])["investors"]]
    assert ids == [f"V-{mine.id}"]
    assert f"V-{theirs.id}" not in ids
    assert _brief(db, users["u1"])["scope"] == "본인 담당"


def test_an_admin_gets_the_whole_team(db, users, people):
    """관리자는 이미 팀 전체를 보고 담당까지 옮긴다 — 판정도 그 함수를 읽는다."""
    mine = _contact(db, users["u1"].id, sectors="AI")
    theirs = _contact(db, users["u2"].id, sectors="바이오")

    out = _brief(db, people["admin"])
    assert {c["id"] for c in out["investors"]} == {f"V-{mine.id}", f"V-{theirs.id}"}
    assert out["scope"] == "팀 전체"


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

    got = _resolve(db, users["u1"], "1번 투자사에게 30억 규모로 3곳을 2026년에")
    assert got == {"investors": [], "companies": []}


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


def test_an_admin_resolves_across_the_team(db, users, people):
    """관리자에게는 팀 전체가 나가므로 되돌리는 범위도 같아야 한다."""
    theirs = _contact(db, users["u2"].id, name="홍길동")

    got = _resolve(db, people["admin"], f"V-{theirs.id}")
    assert got["investors"][0]["name"] == "홍길동"


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
