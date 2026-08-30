"""IR 기업현황 — 계약여부가 실제로 걸리는가 · 삭제는 관리자만인가.

세 가지 증상이 **한 뿌리**에서 나왔다.

1. `계약여부` 를 `딜소개 불가` 로 바꿔도 딜 제안 관리에서 안 빠졌다.
2. `계약여부` 가 표에서 고쳐지지 않았다(고친 것처럼 보였다가 되돌아왔다).
3. IR 자료 링크를 고치고 [저장]하면 `저장 요청 오류` 가 났다.

뿌리는 **화면에 보이는 말과 저장하는 값이 서로 다른 것**이었다.

    표는 `딜소개 불가` 를 보여 주고 → 눌러 고치면 그 글자가 그대로 저장되고
    → 되읽을 때 어느 상태에도 안 맞아 `미계약` 으로 돌아오고
    → 발송 화면은 `blocked` 를 찾으므로 그 기업이 그대로 남았다.

3번은 같은 어긋남의 반대 방향이다. 예전 값(`no`)이 되읽기에 그대로 실려
나가는데 수정 패널의 <select> 에는 그런 option 이 없어, 고른 것 없는 상태로
[저장]하면 빈 값이 날아가고 **NOT NULL 인 칸이라 저장 전체가 500** 이 났다.
344개 중 244개가 그랬다 — IR 링크만의 문제가 아니라 그 패널로는 아무것도
저장할 수 없는 기업이 그만큼이었다.

그래서 이 파일은 **스키마 · 저장 목록 · 되읽기 응답 · 화면** 네 곳이 다
맞는지를 함께 본다. 한 곳만 보는 검사는 이 부류를 못 잡는다.
"""
from __future__ import annotations

import re

import pytest

from .conftest import DEMO_PASSWORD


@pytest.fixture()
def people(db, users):
    """관리자 · 컨설턴트. conftest 의 두 계정은 둘 다 일반 팀원이다."""
    from app.models import User
    from app.services import auth as auth_svc

    pw = auth_svc.hash_password(DEMO_PASSWORD)
    rows = [
        User(id=91, name="관리자시험", phone="01000000091", role="admin", password_hash=pw),
        User(id=92, name="컨설턴트시험", phone="01000000092", role="consultant",
             password_hash=pw),
    ]
    db.add_all(rows)
    db.commit()
    return {"admin": rows[0], "consultant": rows[1]}


@pytest.fixture()
def portal(db, users, people):
    """앱 하나 + 역할별로 따로 로그인한 클라이언트.

    한 클라이언트로 로그인을 갈아타면 쿠키가 덮여서 어느 사람으로 부른
    것인지 알 수 없게 된다(tests/test_admin_guard.py 와 같은 방식).
    """
    from fastapi.testclient import TestClient

    from app.main import create_app

    app = create_app()

    def sign_in(phone: str):
        client = TestClient(app)
        client.post("/login", data={"phone": phone, "password": DEMO_PASSWORD})
        return client

    return {
        "admin": sign_in("01000000091"),
        "member": sign_in("01000000001"),      # conftest 의 u1 — 일반 팀원
        "consultant": sign_in("01000000092"),
    }


@pytest.fixture()
def company(db):
    from app.models import IrCompany

    row = IrCompany(name="샘플에이", sector_major="AI", contract_status="none")
    db.add(row)
    db.commit()
    return row


def _still_there(db, company_id) -> bool:
    """정말 남아 있는가.

    `db.get` 만으로는 세션이 들고 있던 것을 그대로 돌려줘서, 지워졌는데도
    있는 것처럼 보인다 — 지웠는지 확인하는 검사가 조용히 통과한다.
    """
    from app.models import IrCompany

    db.expire_all()
    return db.get(IrCompany, company_id) is not None


# ── ① 화면에 보이는 말로 고쳐도 저장된다 ────────────────────────────────────

def test_the_word_on_screen_is_what_gets_saved(logged_in, db, company):
    """표에서 `계약여부` 를 눌러 고치면 **보이는 글자**가 그대로 온다.

    inline_edit.js 는 칸에 보이는 것을 보낸다 — 값(`blocked`)을 알 길이 없다.
    받는 쪽이 말과 값을 같은 것으로 보지 않으면, PATCH 는 200 인데 아무것도
    안 고쳐진다.
    """
    r = logged_in.patch(f"/api/companies/{company.id}",
                        json={"contract_status": "딜소개 불가"})
    assert r.status_code == 200
    db.expire_all()
    db.refresh(company)
    assert company.contract_status == "blocked", "화면에 보이는 말이 값으로 안 바뀌었다"


def test_spacing_does_not_decide_whether_a_company_is_blocked(logged_in, db, company):
    """`딜소개불가` 와 `딜소개 불가` 는 같은 말이다. 한 글자 차이로 안 걸리면
    막아 둔 줄 알았던 기업이 그대로 나간다."""
    logged_in.patch(f"/api/companies/{company.id}",
                    json={"contract_status": "딜소개불가"})
    db.expire_all()
    db.refresh(company)
    assert company.contract_status == "blocked"


def test_an_unknown_word_is_refused_not_swallowed(logged_in, db, company):
    """모르는 말을 그대로 넣어 두면 되읽을 때 `미계약` 으로 보인다 —
    **고친 적 없는 것처럼** 되고, 왜 안 걸리는지 알 방법이 없다."""
    r = logged_in.patch(f"/api/companies/{company.id}",
                        json={"contract_status": "계약함"})
    assert r.status_code == 400
    # 무엇을 고를 수 있는지 알려 준다 — 막기만 하면 다시 찍어 볼 수밖에 없다
    assert "딜소개 불가" in r.json()["detail"]
    db.expire_all()
    db.refresh(company)
    assert company.contract_status == "none", "막았다면서 값은 바뀌어 있다"


# ── ② 되읽기 — 고친 것이 화면으로 돌아온다 ──────────────────────────────────

def test_the_save_response_carries_the_word_back(logged_in, company):
    """응답이 값만 주면 화면은 방금 누른 글자를 그대로 둘 수밖에 없다.
    그러면 새로고침 때 다른 말이 나온다 — 저장된 것을 못 믿게 된다."""
    body = logged_in.patch(f"/api/companies/{company.id}",
                           json={"contract_status": "딜소개 불가"}).json()
    assert body["contract_status"] == "blocked"
    assert body["contract_label"] == "딜소개 불가"
    assert body["blocked"] is True


def test_reading_it_back_shows_what_was_saved(logged_in, company):
    row = logged_in.patch(f"/api/companies/{company.id}",
                          json={"contract_status": "딜소개 불가"}) and \
        logged_in.get(f"/api/companies/{company.id}").json()
    assert row["contract_label"] == "딜소개 불가"
    assert row["blocked"] is True
    html = logged_in.get("/companies").text
    assert 'data-f-contract="딜소개 불가"' in html, "표의 필터 값이 안 따라왔다"
    assert "blocked-row" in html, "그 줄에 표시가 안 붙었다"


def test_every_one_of_the_five_survives_a_round_trip(logged_in, db, company):
    """다섯 가지 **전부**가 고쳐지고 되읽혀야 한다. 하나만 확인하면
    나머지 넷 중 하나가 조용히 어긋나 있어도 통과한다."""
    from app.routers.companies import CONTRACT_LABELS

    for key, label in CONTRACT_LABELS.items():
        logged_in.patch(f"/api/companies/{company.id}", json={"contract_status": label})
        row = logged_in.get(f"/api/companies/{company.id}").json()
        assert row["contract_status"] == key, f"{label} 이 {key} 로 안 갔다"
        assert row["contract_label"] == label


# ── ③ 화면 네 곳이 서로 맞는가 ──────────────────────────────────────────────

def test_the_table_offers_all_five_even_when_none_is_in_use(logged_in, company):
    """편집창은 지금 표에 실린 값만 모아 보여 준다(inline_edit.js 의
    `knownValues`). `딜소개 불가` 인 기업이 하나도 없으면 그 말을 고를 길이
    사라져, 똑같이 받아 적어야 했다 — 그래서 다섯 가지를 늘 세워 둔다."""
    from app.routers.companies import CONTRACT_LABELS

    html = logged_in.get("/companies").text
    choices = re.search(r'data-field="contract_status"[^>]*data-choices="([^"]+)"', html)
    assert choices, "계약여부 칸에 고를 값이 세워져 있지 않다"
    assert set(v.strip() for v in choices.group(1).split(",")) == set(CONTRACT_LABELS.values())


def test_the_panel_select_can_show_every_value_the_api_returns(logged_in, db):
    """되읽기가 주는 값에 **같은 option 이 반드시 있어야 한다.**

    없으면 select 는 고른 것 없는 상태가 되고, 사람은 계약여부를 건드린 적도
    없는데 그대로 [저장]하면 빈 값이 날아간다. 이 칸은 NOT NULL 이라 저장이
    통째로 500 이 났다 — 화면에는 `저장 요청 오류` 만 떴다.
    """
    from app.models import IrCompany

    html = logged_in.get("/companies").text
    select = re.search(r'<select id="f-contract_status">(.*?)</select>', html, re.S)
    assert select, "수정 패널에 계약여부 <select> 가 없다"
    options = set(re.findall(r'value="([^"]*)"', select.group(1)))

    # 예전 값들도 되읽기를 거치면 반드시 option 안에 들어와야 한다.
    for old in ("no", "yes", "pending", "", None, "blocked"):
        row = IrCompany(name=f"예전값{old!r}", contract_status=old)
        db.add(row)
        db.commit()
        got = logged_in.get(f"/api/companies/{row.id}").json()["contract_status"]
        assert got in options, f"{old!r} 이 {got!r} 로 나와 화면 option 에 없다"


# ── ④ 수정 패널이 실제로 보내는 모양 그대로 ─────────────────────────────────
#
# API 를 칸 하나만 불러 보는 검사는 이 부류를 **못 잡는다.** 패널은 [저장] 한
# 번에 열여섯 칸을 통째로 보낸다 — 터진 것은 IR 링크가 아니라 같이 실려 간
# 계약여부였는데, 사람에게는 마지막에 만진 칸이 문제로 보인다.

# app/static/js/companies.js 의 FIELDS 와 같은 목록.
PANEL_FIELDS = ["name", "sector_major", "sector_minor", "series", "one_liner",
                "revenue_recent", "funding_total", "raise_target", "pre_value",
                "competitiveness", "funding_status", "ir_drive_url",
                "contract_status", "contract_month", "summary_status", "note"]


def test_the_panel_sends_the_same_fields_the_script_does():
    """목록이 갈리면 이 파일의 검사만 통과하고 화면은 그대로 터진다."""
    from pathlib import Path

    js = Path("app/static/js/companies.js").read_text(encoding="utf-8")
    listed = re.search(r"var FIELDS = \[(.*?)\];", js, re.S)
    assert listed, "companies.js 에서 저장 목록을 찾지 못했다"
    assert re.findall(r'"([a-z_0-9]+)"', listed.group(1)) == PANEL_FIELDS


# 억으로 보여 주고 숫자로 보내는 칸(companies.js 의 EOK_FIELDS).
# 나머지는 전부 글자로 간다 — 빈 칸은 빈 글자다(`input.value.trim()`).
PANEL_NUMBER_FIELDS = ["revenue_recent", "funding_total", "raise_target", "pre_value"]


def _panel_save(client, company_id, **over):
    """수정 패널이 [저장] 때 보내는 몸통 그대로 PATCH 한다.

    **패널을 한 번 열었다 저장하는 흐름 그대로**여야 한다 — 되읽기로 칸을
    채우고(fill), 그 열여섯 칸을 통째로 보낸다(collect). 칸 하나만 실어
    보내는 검사는 이 부류의 사고를 못 잡는다.
    """
    row = client.get(f"/api/companies/{company_id}").json()
    body = {}
    for f in PANEL_FIELDS:
        value = row.get(f)
        if f in PANEL_NUMBER_FIELDS:
            body[f] = value                     # 빈 칸은 null
        else:
            body[f] = "" if value is None else str(value)
    body["is_top_deal"] = bool(row.get("is_top_deal"))
    body.update(over)
    return client.patch(f"/api/companies/{company_id}", json=body)


def test_saving_an_ir_link_from_the_panel_works_for_old_rows(logged_in, db):
    """`저장 요청 오류` 의 재현. 예전 값(`no`)을 가진 기업 — 344개 중 244개."""
    from app.models import IrCompany

    row = IrCompany(name="샘플비", contract_status="no")
    db.add(row)
    db.commit()

    link = "https://drive.example.com/file/d/sample/view"
    r = _panel_save(logged_in, row.id, ir_drive_url=link)
    assert r.status_code == 200, f"패널 저장이 {r.status_code} 로 실패했다"
    # **되읽어서** 확인한다 — 저장은 됐는데 안 돌아오는 사고가 이 저장소에 여러 번 있었다.
    assert logged_in.get(f"/api/companies/{row.id}").json()["ir_drive_url"] == link
    assert 'href="' + link + '"' in logged_in.get("/companies").text, "표에 링크가 안 걸렸다"
    assert 'href="' + link + '"' in logged_in.get("/companies?tab=db").text, \
        "스타트업DB 탭에 링크가 안 걸렸다"


def test_the_panel_never_empties_a_column_that_cannot_be_empty(logged_in, company):
    """계약여부를 빈 값으로 보내도 저장이 통째로 죽으면 안 된다."""
    r = _panel_save(logged_in, company.id, contract_status="")
    assert r.status_code == 200
    assert logged_in.get(f"/api/companies/{company.id}").json()["contract_status"] == "none"


def test_editing_the_ir_link_twice_keeps_the_second_one(logged_in, company):
    """한 번 되는 것과 계속 되는 것은 다르다."""
    first = "https://drive.example.com/file/d/one/view"
    second = "https://drive.example.com/file/d/two/view"
    _panel_save(logged_in, company.id, ir_drive_url=first)
    _panel_save(logged_in, company.id, ir_drive_url=second)
    assert logged_in.get(f"/api/companies/{company.id}").json()["ir_drive_url"] == second


# ── ⑤ 딜소개 불가 — 발송 화면 목록에서 실제로 빠진다 ────────────────────────

def _pickable_company_ids(html: str):
    """딜 제안 관리에서 **체크할 수 있는** 기업 번호.

    이름이 안 보이는 것만으로는 부족하다 — 화면에서 감췄어도 체크박스가
    남아 있으면 그대로 골라진다(감춘 사람이 체크박스로는 골라지던 사고가
    이 저장소에 있었다).
    """
    return set(re.findall(r'<input type="checkbox" class="company-cb" value="(\d+)"', html))


def test_marking_it_blocked_takes_it_out_of_the_send_list(logged_in, db, company):
    """상태만 보지 않는다 — **고를 수 있는 목록**에서 사라져야 한다."""
    assert str(company.id) in _pickable_company_ids(logged_in.get("/deals").text)

    logged_in.patch(f"/api/companies/{company.id}",
                    json={"contract_status": "딜소개 불가"})

    html = logged_in.get("/deals").text
    assert str(company.id) not in _pickable_company_ids(html), \
        "딜소개 불가로 바꿨는데 아직 고를 수 있다"
    assert "샘플에이" not in html


def test_it_comes_back_when_the_block_is_lifted(logged_in, db, company):
    """되돌릴 수 있어야 한다 — 한 번 막으면 영영 못 보내는 것은 아니다."""
    logged_in.patch(f"/api/companies/{company.id}", json={"contract_status": "딜소개 불가"})
    logged_in.patch(f"/api/companies/{company.id}", json={"contract_status": "미계약"})
    assert str(company.id) in _pickable_company_ids(logged_in.get("/deals").text)


def test_it_stays_on_the_company_screen_where_it_can_be_undone(logged_in, company):
    """목록에서까지 지우면 '왜 없지' 가 된다 — 남기되 눈에 띄게 한다."""
    logged_in.patch(f"/api/companies/{company.id}", json={"contract_status": "딜소개 불가"})
    html = logged_in.get("/companies").text
    assert "샘플에이" in html and "blocked-row" in html


def test_being_thin_is_not_the_same_as_being_blocked(logged_in, db, company):
    """`보류`(내용 부족)는 발송 화면에서 **뒤로 밀릴 뿐 그대로 뜬다.**
    목록에서 실제로 빠지는 것은 `딜소개 불가` 하나뿐이라, 삭제를 막을 때
    안내가 '보류' 를 가리키면 틀린 길을 알려 주는 셈이다."""
    logged_in.patch(f"/api/companies/{company.id}", json={"summary_status": "insufficient"})
    assert str(company.id) in _pickable_company_ids(logged_in.get("/deals").text)


# ── ⑥ 삭제 — 관리자만 ───────────────────────────────────────────────────────

def test_only_an_admin_can_delete(portal, db, company):
    """팀원·컨설턴트는 막히고, **대상이 실제로 남아 있어야** 한다.
    상태 코드만 보면 403 을 주고도 지워 버리는 경우를 못 잡는다."""
    for role in ("member", "consultant"):
        r = portal[role].delete(f"/api/companies/{company.id}")
        assert r.status_code == 403, f"{role} 이 {r.status_code} 를 받았다"
        assert _still_there(db, company.id), f"{role} 을 막았다는데 지워졌다"

    assert portal["admin"].delete(f"/api/companies/{company.id}").status_code == 200
    assert not _still_there(db, company.id)


def test_the_button_is_only_drawn_for_an_admin(portal):
    """눌러도 안 되는 단추가 보이면 고장으로 읽힌다.
    **보이는 사람과 지울 수 있는 사람이 같아야 한다** — 판정이 갈리면
    보이는데 막히거나, 안 보이는데 주소로는 되는 상태가 된다."""
    assert 'id="co-delete"' in portal["admin"].get("/companies").text
    assert 'id="co-delete"' not in portal["member"].get("/companies").text


def test_the_confirm_names_what_it_deletes(portal):
    """되돌릴 수 없는 일이라 **무엇을 지우는지** 확인창에 나와야 한다
    (투자컨설턴트 현황이 같은 어휘로 묻는다)."""
    from pathlib import Path

    js = Path("app/static/js/companies.js").read_text(encoding="utf-8")
    confirm = re.search(r"confirm\((.*?)\)\) return;", js, re.S)
    assert confirm, "삭제 확인창을 찾지 못했다"
    assert "currentName" in confirm.group(1), "확인창이 이름을 대지 않는다"
    assert "되돌릴 수 없습니다" in confirm.group(1)
    # 지우는 것 말고 **다른 길**도 알려 준다
    assert "딜소개 불가" in confirm.group(1)


def test_a_missing_company_does_not_leak_to_a_non_admin(portal, db):
    """권한을 먼저 본다 — 없는 번호에 404 를 주면 번호만 바꿔 가며
    어느 기업이 있는지 알아낼 수 있다."""
    assert portal["member"].delete("/api/companies/999999").status_code == 403
    assert portal["admin"].delete("/api/companies/999999").status_code == 404


# ── ⑦ 딜소개 이력이 붙은 기업 ───────────────────────────────────────────────

def test_a_company_that_was_already_sent_is_never_deleted(portal, db, company):
    """**관리자여도 지우지 않는다.**

    회차는 "그날 누구에게 무엇을 보냈는가" 의 기록이다. 기업을 지우면 그
    회차가 무엇을 보낸 회차였는지 알 수 없게 되고, 업무 보고가 그 줄을 읽는다.
    지우는 대신 `딜소개 불가` 로 두면 발송 목록에서 빠진다 — 이력은 남는다.
    """
    from app.models import DealBatch, DealBatchCompany

    batch = DealBatch(user_id=1, title="시험 회차")
    db.add(batch)
    db.commit()
    db.add(DealBatchCompany(batch_id=batch.id, company_id=company.id, position=1))
    db.commit()

    r = portal["admin"].delete(f"/api/companies/{company.id}")
    assert r.status_code == 400
    assert _still_there(db, company.id)

    detail = r.json()["detail"]
    assert "샘플에이" in detail, "무엇을 못 지웠는지 이름이 없다"
    # 예전 안내는 '보류' 를 가리켰는데 그것으로는 발송 목록에서 안 빠진다
    assert "딜소개 불가" in detail and "보류" not in detail


def test_the_way_out_that_the_message_points_at_actually_works(portal, db, company):
    """안내가 가리킨 길이 실제로 되는지까지 본다 — 틀린 길을 알려 주면
    지우지도 못하고 빼지도 못한 채 남는다."""
    from app.models import DealBatch, DealBatchCompany

    batch = DealBatch(user_id=1, title="시험 회차")
    db.add(batch)
    db.commit()
    db.add(DealBatchCompany(batch_id=batch.id, company_id=company.id, position=1))
    db.commit()

    portal["admin"].patch(f"/api/companies/{company.id}",
                          json={"contract_status": "딜소개 불가"})
    assert str(company.id) not in _pickable_company_ids(portal["admin"].get("/deals").text)
    assert _still_there(db, company.id), "빼기만 해야 하는데 사라졌다"


# ── ⑧ `홍보메일삭제` — 이름을 칸에 든 값에 맞춘다 ───────────────────────────

def test_the_promo_mail_column_is_named_after_what_it_holds(logged_in, db):
    """`날짜 기입` 은 무엇을 적는 칸인지 말해 주지 않았다.

    실제 값 43줄 중 42줄이 홍보 메일을 지웠다는 기록이고(`삭제 완료` 28 ·
    `7월 삭제필요 -> 삭제 완료` 8 · `민진 8/13 삭제` 5 …) 날짜만 든 줄은
    하나도 없다 — 이름이 값보다 좁고 또 틀렸다.

    **이미 적힌 것은 지우지 않는다** — 지난 정리 기록이라 지우면 무엇을 언제
    처리했는지 되짚을 길이 없다. 이름만 바뀌고 값은 그대로다.
    """
    from app.models import IrCompany

    row = IrCompany(name="샘플시", contract_month="삭제 완료")
    db.add(row)
    db.commit()

    html = logged_in.get("/companies").text
    assert "날짜 기입" not in html, "옛 이름이 남아 있다"
    assert ">홍보메일삭제<" in html
    # 표 머리글과 수정 패널의 안내가 **같아야** 한다(한쪽만 고치면 다시 갈린다)
    hint = 'title="계약기업 · 거부메일 주소를 홍보 메일 목록에서 지웠는지"'
    assert html.count(hint) == 2
    # 없는 모양을 예로 들면 그 모양으로 적게 된다 — 이 칸에 날짜는 한 줄도 없다.
    assert 'id="f-contract_month" placeholder="삭제 완료"' in html
    # 적혀 있던 것은 그대로 보인다
    assert "삭제 완료" in html
    assert logged_in.get(f"/api/companies/{row.id}").json()["contract_month"] == "삭제 완료"
