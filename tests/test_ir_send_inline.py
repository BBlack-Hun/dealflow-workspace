"""[자료 보내기] 는 **그 자리에서 끝난다** — 딜 제안 관리로 넘어가지 않는다.

예전에는 IR 진행 관리(`/ir`)에서 [자료 보내기] 를 누르면 딜 제안 관리
(`/deals`)로 화면이 통째로 옮겨 갔다. 옮겨 간 화면에서 할 일은 이미 정해져
있었는데도(이 담당자 · 이 기업들 · 지금 보낸다) 기업 고르기·담당자 고르기·예약
큐가 다 붙은 넓은 화면을 다시 읽어야 했고, 돌아올 길도 스스로 찾아야 했다.

지금은 그 자리에서 창이 열려 **번호·파일명·나갈 문구**를 보여 주고 거기서
보낸다. 이 파일이 지키는 것은 넷이다.

- 화면이 **안 넘어간다** — 다만 스크립트가 죽었을 때의 길은 남아 있다.
- 창이 그리는 값은 **전부 서버가 준 것**이다 — 화면이 세거나 짓지 않는다.
  (그래서 딜 제안 관리의 목록과 갈릴 수가 없다.)
- 자료를 **누가 붙이는지**를 두 화면이 같은 말로 한다.
- 이력은 **보낸 때** 남는다 — 누른 때가 아니다.

창이 실제로 어떻게 움직이는지(폼을 막는지·서버에 무엇을 묻는지·막혔을 때
무슨 말이 뜨는지)는 브라우저 검사가 본다 — `tests/js/ir_send_test.js`.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

from .conftest import DEMO_PASSWORD
from .test_ir_delivery_attach import _css_without_comments

ROOT = Path(__file__).resolve().parents[1]
JS_DIR = ROOT / "app" / "static" / "js"

#: 자동 첨부를 켠 계정 · 켜지 않은 계정이 [보낼 자료] 칸에서 보는 말.
#: **두 화면이 같은 글자를 쓴다** — 한쪽만 고치면 여기서는 손으로 붙이라는데
#: 저기서는 발송기가 붙여 자료가 두 번 나간다.
BY_SENDER = "발송 프로그램이 아래 차례대로 파일을 보내고"
BY_HAND = "아래 차례대로 PC 카톡에 직접 첨부한 뒤"


@pytest.fixture()
def stage(client, db, users):
    """자료를 기다리는 투자사 한 명 + 자료가 있는 기업 둘 + 열린 요청 둘."""
    from app.models import (IrCompany, IrRequest, MessageTemplate, SheetOwner,
                            VcContact)

    db.add(SheetOwner(label="내 명단", user_id=users["u1"].id))
    contact = VcContact(user_id=users["u1"].id, name="홍길동", title="팀장",
                        firm="가나벤처스", source_sheet="내 명단",
                        channel_kakao=1, connect_stage="connected",
                        kakao_room_name="홍길동 팀장님")
    agri = IrCompany(name="샘플애그", ir_file_name="샘플애그_IR.pdf")
    medi = IrCompany(name="샘플메디", ir_file_name="샘플메디_IR.pdf")
    db.add_all([contact, agri, medi,
                MessageTemplate(user_id=None, kind="ir_delivery", is_active=1,
                                body="{기업목록} IR deck 먼저 전달드리겠습니다.")])
    db.commit()
    db.add_all([
        IrRequest(user_id=users["u1"].id, contact_id=contact.id,
                  company_id=agri.id, company_name="샘플애그",
                  requested_at="2026-08-20"),
        IrRequest(user_id=users["u1"].id, contact_id=contact.id,
                  company_id=medi.id, company_name="샘플메디",
                  requested_at="2026-08-20"),
    ])
    db.commit()

    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    return {"client": client, "db": db, "user": users["u1"], "contact": contact,
            "agri": agri, "medi": medi}


def _turn_on(stage):
    """자료 폴더를 정해 둔다 — 자동 첨부를 켜는 유일한 스위치(`ir_attach`)."""
    from app.models import AgentDevice

    device = stage["db"].query(AgentDevice).filter_by(
        user_id=stage["user"].id).one()
    device.ir_root = "/Users/somebody/IR자료"
    stage["db"].commit()


def _ir(stage) -> str:
    return stage["client"].get("/ir").text


# --- 그 자리에서 연다 ----------------------------------------------------------

def test_the_screen_carries_every_place_the_script_fills(stage):
    """창의 자리를 **서버가 그린다** — 스크립트는 채우기만 한다.

    브라우저 검사는 가짜 화면 위에서 도는데(`tests/js/_ir_dom.js`), 실제 화면에서
    아이디 하나가 바뀌어도 그 가짜 화면 위에서는 그대로 통과한다. 그래서 가짜가
    세운 아이디가 **정말로 그려지는지**를 여기서 맞대 본다.
    """
    fake = (ROOT / "tests" / "js" / "_ir_dom.js").read_text(encoding="utf-8")
    html = _ir(stage)

    ids = sorted(set(re.findall(r'id: "([\w-]+)"', fake)))
    assert ids, "가짜 화면이 아이디를 하나도 안 세운다 — 검사가 헛돈다"
    missing = [i for i in ids if f'id="{i}"' not in html]
    assert not missing, f"화면에 없는 자리를 검사가 세우고 있다: {missing}"


def test_the_button_still_works_without_script(stage):
    """스크립트가 안 실리거나 예외가 나면 **예전 길로 간다.**

    창을 여는 것이 링크였다면 스크립트 예외 하나에 [자료 보내기] 가 아무 일도
    안 하는 단추가 된다. 폼으로 두면 그때는 폼대로 서버에 닿는다.
    """
    html = _ir(stage)

    assert 'class="deliver-form" method="post" action="/ir/deliver-guide"' in html
    # 창이 확인창에서 누구에게 보내는지 말하려면 이름이 필요하다.
    assert f'data-name="{stage["contact"].name}"' in html


def test_the_screen_loads_the_shared_list_before_its_own_script(stage):
    """[보낼 자료] 목록은 **딜 제안 관리와 같은 한 벌**이고, 먼저 실려야 한다."""
    html = _ir(stage)

    shared = html.find("js/ir_attach_list.js")
    mine = html.find("js/ir_send.js")
    assert shared > 0, "공용 한 벌을 안 싣는다 — 목록을 그릴 것이 없다"
    assert mine > 0, "그 자리에서 여는 스크립트를 안 싣는다"
    assert shared < mine, "공용 한 벌이 뒤에 실리면 창이 그것을 못 찾는다"


def test_the_screen_no_longer_promises_to_move(stage):
    """안내가 옛말을 달고 있으면, 안 넘어가는 화면을 두고 넘어간다고 말한다."""
    html = _ir(stage)
    hint = html[html.index("<b>[자료 보내기]</b>"):][:400]

    assert "이 화면에서" in hint
    assert "딜 제안 관리가 열리고" not in hint


# --- 새로 만든 것이 없다 --------------------------------------------------------

def test_the_window_asks_the_server_instead_of_composing(stage):
    """번호도 문구도 **서버가 준 것만** 쓴다.

    화면이 제 손으로 목록을 세우면 목록은 `1, 2`, 문구는 `1번, 3번` 이 되어 어느
    쪽이 맞는지 알 수 없다 — 이 저장소에서 실제로 났던 사고다.
    """
    js = (JS_DIR / "ir_send.js").read_text(encoding="utf-8")

    assert "/api/deals/preview" in js, "미리보기를 서버에 안 묻는다"
    assert "/api/deals/send" in js, "발송 길을 새로 팠다"
    assert "IrAttach.renderList" in js, "목록을 제 손으로 그린다"
    assert "IrAttach.copyText" in js, "복사를 제 손으로 한다"
    # 목록을 훑어 무엇을 짓는 코드가 여기 있으면 안 된다 — 그리는 자리는 한 벌뿐이다.
    assert ".attachments" not in js, "자료 목록을 여기서 다시 훑고 있다"


def test_only_one_place_draws_the_list():
    """목록을 그리는 코드가 **한 벌뿐인가.**

    딜 제안 관리도 이 한 벌을 부른다 — 베껴 두면 번호를 적는 규칙이 두 벌이 되어
    고칠 때 한쪽만 고쳐진다.
    """
    shared = (JS_DIR / "ir_attach_list.js").read_text(encoding="utf-8")
    deals = (JS_DIR / "deals.js").read_text(encoding="utf-8")
    mine = (JS_DIR / "ir_send.js").read_text(encoding="utf-8")

    assert '"ir-no"' in shared or "ir-no" in shared, "공용 한 벌이 목록을 안 그린다"
    for name, js in (("deals.js", deals), ("ir_send.js", mine)):
        assert "IrAttach.renderList" in js, f"{name} 이 공용 한 벌을 안 쓴다"
        assert "번호 없음" not in js, f"{name} 에 목록 그리는 코드가 또 있다"


# --- 갈래 둘 — 자료를 누가 붙이는가 ---------------------------------------------

def test_both_screens_say_the_same_thing_when_attaching_by_hand(stage):
    html = _ir(stage)
    deals = stage["client"].get("/deals").text

    assert BY_HAND in html, "IR 진행 관리의 창이 누가 붙이는지 말하지 않는다"
    assert BY_HAND in deals
    assert BY_SENDER not in html


def test_the_sender_attaching_account_goes_to_the_deal_screen(stage):
    """**자료 폴더를 등록한 계정은 예전처럼 넘어간다** — 사용자가 그렇게 정했다.

    가리는 방법이 **자리를 안 그리는 것**이라, 창도 스크립트도 실리지 않는다.
    그러면 `ir_send.js` 가 가로챌 것이 없어 폼이 폼대로 `/ir/deliver-guide` 로
    가고, 딜 제안 관리가 열린다(그 길은 아래 fallback 검사가 지킨다).
    """
    _turn_on(stage)
    html = _ir(stage)

    assert 'id="ir-send-modal"' not in html, "넘어갈 계정에 그 자리 창이 떠 있다"
    assert "js/ir_send.js" not in html, "쓰지도 않을 스크립트를 싣는다"
    # 창이 없으니 그 안의 [보낼 자료] 칸도 없다 — 이 화면에서 볼 것이 아니다.
    assert BY_HAND not in html
    assert BY_SENDER not in html
    # 안내가 옛말을 달고 있으면 안 넘어간다고 말하는 화면이 넘어간다.
    hint = html[html.index("<b>[자료 보내기]</b>"):][:400]
    assert "딜 제안 관리가 열립니다" in hint
    assert "이 화면에서" not in hint


def test_the_deal_screen_still_tells_that_account_who_attaches(stage):
    """넘어간 화면에서는 자료를 발송기가 붙인다고 말해야 한다 — 거기가 그 말을 할 자리다."""
    _turn_on(stage)

    assert BY_SENDER in stage["client"].get("/deals").text


def test_the_deal_screen_does_not_contradict_itself_about_who_attaches(stage):
    """넘어간 화면이 **한 화면 안에서 두 말**을 하면 안 된다.

    [보낼 자료] 머리말은 `발송 프로그램이 … 파일을 보내고` 인데 바로 아래
    발송 요약줄은 `자료는 PC 카톡에서 직접 첨부하고` 라는 붙박이 글자였다.
    그 말대로 하면 **같은 자료가 두 번 나간다** — 발송기도 붙이고 사람도 붙인다.

    화면이 다시 판단하지 않게, 서버가 칸에 적어 준 값 하나를 읽는다.
    """
    js = (JS_DIR / "deals.js").read_text(encoding="utf-8")
    _turn_on(stage)
    html = stage["client"].get("/deals").text

    assert 'data-auto="1"' in html, "서버가 자료를 누가 붙이는지 칸에 안 적는다"
    assert 'getAttribute("data-auto")' in js, "화면이 그 값을 안 읽는다"
    # 붙박이 글자가 남아 있으면 켠 계정에서도 그것이 뜬다.
    assert "자료는 PC 카톡에서 직접 첨부하고, 여기서는 문구만 보냅니다" in js
    assert "자료 파일은 발송 프로그램이 붙여 보냅니다" in js


def test_the_deal_screen_says_hand_attaching_for_a_plain_account(stage):
    assert 'data-auto="0"' in stage["client"].get("/deals").text


def test_only_one_place_decides_which_way(stage):
    """창·스크립트·안내가 **같은 값 하나**를 읽는가.

    셋이 따로 판단하면 창은 떴는데 스크립트가 없거나(단추가 죽는다), 안내만
    옛말인 화면이 생긴다. 판단은 `services/ir_attach.py: auto_attach_enabled`
    한 곳이고 화면은 그것을 `ir_auto_attach` 로 받는다.
    """
    html = (ROOT / "app" / "templates" / "ir.html").read_text(encoding="utf-8")

    # 갈리는 자리는 셋이고 **읽는 값은 하나**다: 창 · 스크립트 · 안내.
    assert html.count("{% if not ir_auto_attach %}") == 2, (
        "창과 스크립트가 같은 조건으로 갈리지 않는다")
    assert html.count("{% if ir_auto_attach %}") == 1, (
        "안내가 다른 조건으로 갈린다 — 넘어가는 화면이 안 넘어간다고 말한다")


def test_the_history_says_who_attached_the_files(stage):
    """자료를 발송기가 붙인 건과 사람이 붙인 건은 **나중에 다른 일**이다."""
    from app.models import ContactActivity

    _turn_on(stage)
    r = stage["client"].post("/api/deals/send", json={
        "mode": "ir", "contact_ids": [stage["contact"].id],
        "company_ids": [stage["agri"].id]})
    assert r.status_code == 200, r.text

    row = stage["db"].query(ContactActivity).filter_by(
        contact_id=stage["contact"].id, kind="ir_delivery").one()
    assert "발송 프로그램이 첨부" in row.content
    assert "PC 에서 직접 첨부" not in row.content


# --- 남의 것은 못 건드린다 -------------------------------------------------------

def test_another_persons_contact_cannot_be_sent_for(client, db, users, stage):
    """남의 담당자로는 발송도, 이력도 안 된다."""
    from app.models import ContactActivity

    client.post("/login", data={"phone": "01000000002", "password": DEMO_PASSWORD})
    r = client.post("/api/deals/send", json={
        "mode": "ir", "contact_ids": [stage["contact"].id],
        "company_ids": [stage["agri"].id]})

    assert r.status_code == 404
    assert db.query(ContactActivity).filter_by(
        contact_id=stage["contact"].id, kind="ir_delivery").count() == 0


def test_a_company_the_contact_did_not_ask_for_is_dropped_on_the_fallback(stage):
    """스크립트 없는 길에서도 **요청한 기업만** 넘어간다.

    주소에 남의 기업 번호를 섞어 넣어도 발송 화면에는 이 담당자가 실제로
    요청한 것만 골라져 있어야 한다.
    """
    from app.models import IrCompany

    other = IrCompany(name="딴기업", ir_file_name="딴기업.pdf")
    stage["db"].add(other)
    stage["db"].commit()

    r = stage["client"].post(
        "/ir/deliver-guide",
        data={"contact_id": stage["contact"].id,
              "company_ids": f"{stage['agri'].id},{other.id}"},
        follow_redirects=False)
    where = r.headers["location"]

    assert f"companies={stage['agri'].id}&" in where + "&", where
    assert str(other.id) not in where.split("companies=")[1].split("&")[0]


# --- 화면 ----------------------------------------------------------------------

def test_the_window_rule_is_not_swallowed_by_a_comment():
    """창을 세우는 규칙이 **살아 있는가.**

    전에 CSS 주석이 안 닫혀 아래 규칙이 통째로 죽은 적이 있는데, 글자만 찾으면
    그때도 검사는 통과한다. 브라우저가 버리는 것을 여기서도 버리고 찾는다.
    """
    css = _css_without_comments()
    rule = re.search(r"\.send-modal\s*\{([^}]*)\}", css)

    assert rule, "창 규칙이 사라졌거나 주석 안에 갇혔습니다"
    body = rule.group(1)
    assert "position: fixed" in body, "떠 있지 않으면 뒤 화면과 섞인다"
    assert "z-index: 40" in body, "뒷막(39) 위에 서야 한다"


# --- 창의 설명 글귀 ---------------------------------------------------------------
#
# 사용자가 창의 설명 글귀를 **한 줄만** 두고 지워 달라고 했다. 지운 것은 설명뿐
# 이고 **일하는 부분과 알림은 그대로**다 — 일하는 부분을 지우면 그 자리에서
# 보낼 수가 없어져 이 창을 만든 뜻이 사라지고, 알림을 지우면 사람이 모르고 보낸다.

#: 창에 남는 단 한 줄.
THE_ONE_LINE = "보낼 자료 — 아래 차례대로 PC 카톡에 직접 첨부한 뒤 이 문구를 보내세요."


def _modal(stage) -> str:
    """그려진 화면에서 **창 부분만** 잘라 낸다.

    페이지 전체에서 찾으면 창 밖의 글(요청 표 아래 안내 등)까지 걸려, 지웠는지
    아닌지를 엉뚱한 자리로 판단한다. 창은 본문의 마지막이라 그 뒤는 스크립트다.
    """
    html = _ir(stage)
    start = html.index('id="ir-send-modal"')
    end = html.index("<script", start)
    return html[start:end]


def test_the_window_keeps_only_the_one_line(stage):
    modal = _modal(stage)

    assert THE_ONE_LINE in modal, "남겨야 할 한 줄이 사라졌다"
    for gone in ("님에게", "개 기업 자료를 보냅니다",
                 "담당자를 바꾸면 번호도 바뀝니다",
                 "실제로 나갈 문구", "고치시려면"):
        assert gone not in modal, f"지웠어야 할 설명이 남아 있다: {gone}"


def test_the_window_keeps_everything_that_does_the_work(stage):
    """지우다가 일하는 자리를 지우면 그 자리에서 보낼 수가 없다."""
    modal = _modal(stage)

    for keep in ('id="ir-links"', 'id="ir-send-message"', 'id="ir-send-copy"',
                 'id="ir-send-go"', 'id="ir-send-close"', 'id="ir-send-open-deals"'):
        assert keep in modal, f"일하는 자리가 사라졌다: {keep}"


def test_the_window_keeps_the_warnings(stage):
    """경고는 설명이 아니라 **알림**이다 — 지우면 사람이 모르고 보낸다."""
    modal = _modal(stage)

    # 어디로 나가는지 · 막힌 사유.
    assert 'id="ir-send-state"' in modal
    assert 'id="ir-send-warnings"' in modal


def test_the_deal_screen_keeps_the_number_note(stage):
    """번호 설명 줄은 **딜 제안 관리에는 남는다.**

    거기서는 탭을 옮기며 담당자를 바꾸므로 "담당자를 바꾸면 번호도 바뀝니다"
    가 실제로 필요한 말이다. IR 창은 담당자 하나만 다뤄 애초에 안 닿는 말이었다.
    """
    assert 'id="ir-no-note"' in stage["client"].get("/deals").text


# --- 패널 이름 ------------------------------------------------------------------

def test_the_closed_followup_panel_is_called_by_its_new_name(stage):
    """사용자가 부르기로 한 이름 — `끝난 후속` → `IR 요청 투자사`."""
    html = _ir(stage)

    assert "IR 요청 투자사" in html
    assert "끝난 후속" not in html


def test_both_copies_of_that_panel_carry_the_same_name():
    """같은 표가 두 파일에 있다 — 한쪽만 고치면 이름이 갈린다.

    `followups.html` 은 지금 **아무 라우트도 안 그린다**(`/followups` 는
    `/ir#remind` 로 넘긴다). 그래도 함께 고친다 — 되살아나는 날 같은 표가
    다른 이름을 달고 나오는 것을 막는 값이, 한 줄 고치는 값보다 크다.
    """
    for name in ("ir.html", "followups.html"):
        page = (ROOT / "app" / "templates" / name).read_text(encoding="utf-8")
        assert '<h2 class="panel-title">IR 요청 투자사' in page, name
        assert "아직 끝난 후속이 없습니다" not in page, name


# --- 시연 자료 --------------------------------------------------------------------
#
# [보낼 자료] 목록은 사람이 **기업과 파일의 짝을 눈으로 맞춰 보는** 자리다.
# 그러려면 시연 자료 자체의 짝이 맞아야 한다 — 실제로 `샘플페이` 가
# `샘플로지_IR.pdf` 를 달고 있어서, 멀쩡한 화면이 "기업과 파일이 어긋난다" 로
# 읽혔다(`scripts/bootstrap.py`).
#
# **이름 규칙을 붙들어 매지는 않는다.** `{기업명}_IR.pdf` 를 강요하면 시연
# 자료를 손볼 때마다 검사가 걸리적거린다. 보는 것은 **짝이 맞는가** 하나다 —
# 제 이름을 달고 있는가, 남의 이름을 달고 있지는 않은가.

def test_the_demo_material_belongs_to_the_company_that_carries_it():
    from scripts.bootstrap import DEMO_COMPANIES

    named = [(c["name"], c.get("ir_file_name") or "") for c in DEMO_COMPANIES]
    assert named, "시연 기업이 하나도 없다 — 검사가 헛돈다"

    for name, ir_file in named:
        if not ir_file:
            continue        # 자료를 안 붙인 기업은 이 검사의 대상이 아니다
        assert name in ir_file, (
            f"scripts/bootstrap.py — '{name}' 의 자료 파일명에 제 이름이 없다"
            f"({ir_file}). 화면에서 짝을 눈으로 맞출 수 없다")
        others = [n for n, _ in named if n != name and n in ir_file]
        assert not others, (
            f"scripts/bootstrap.py — '{name}' 이 '{others[0]}' 의 자료를 달고 있다"
            f"({ir_file}). 화면이 고장난 것으로 읽힌다")


# --- 브라우저 검사 -----------------------------------------------------------------
#
# 폼을 막는지·서버에 무엇을 묻는지·막혔을 때 무슨 말이 뜨는지는 `ir_send.js` 를
# **그대로 실행해야** 보인다. node 가 없는 환경(운영 도커 이미지)에서는 건너뛴다 —
# 브라우저 자산 검사라 서버 실행에 필요한 의존성이 아니다.

def test_the_window_opens_in_place_and_sends_through_the_existing_path():
    node = shutil.which("node")
    if node is None:
        pytest.skip("node 미설치 — 브라우저 로직 테스트 생략 "
                    "(호스트에서 `node tests/js/ir_send_test.js`)")
    js = Path(__file__).resolve().parent / "js" / "ir_send_test.js"
    result = subprocess.run([node, str(js)], capture_output=True,
                            text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
