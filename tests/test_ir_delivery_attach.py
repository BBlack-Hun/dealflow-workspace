"""IR 자료 전달 — 자료는 **사람이 PC 카톡에서 첨부한다**.

지금까지는 구글 드라이브 링크를 문구에 실어 보냈다. 기업 하나당 한 통씩
링크를 먼저 던지고 설명이 마지막이었다.

    1번 (주)샘플애그
    https://drive.google.com/file/d/…       ← 이 통들이 없어졌다

    홍길동 팀장님 안녕하세요.
    1번 기업 (주)샘플애그 IR deck 먼저 전달드리겠습니다.

그 방식을 폐기했다. 링크는 더 이상 문구에 실리지 않고, 앱은 **안내 문구만**
보낸다. 자료 파일은 사람이 PC 카카오톡에서 직접 첨부한다.

이 파일이 지키는 것은 셋이다.
- 링크가 **정말로 안 나간다**(옛 문구에 남은 `{자료링크}` 토큰까지 포함해서).
- 그래도 **어느 기업 자료인지는 문구에 남는다** — 번호와 이름.
- [자료 보내기] 를 누른 것이 **활동 이력에 남고**, 눌렀다는 이유만으로
  요청이 '전달함' 으로 닫히지는 않는다.

여기 사람들은 **자동 첨부를 켜지 않은 계정**이다(자기 PC 의 자료 폴더를 정하지
않았다). 그래서 지금까지의 동작 그대로다 — 문구만 나가고 안내창이 뜬다.
켠 계정이 어떻게 달라지는지는 `tests/test_ir_attach_job.py` 가 지킨다.
"""
from __future__ import annotations

import pathlib
import re

import pytest

from app.services import message_composer as mc

from .conftest import DEMO_PASSWORD

#: 자료 칸에 들어가는 값 — **파일명**이다(0056). 예전에는 드라이브 링크였다.
FILE = "샘플애그_IR.pdf"
#: 폐기한 옛 값. 이것이 문구에 실리지 않는지가 이 파일의 첫 번째 검사다.
LINK = "https://drive.google.com/file/d/agri/view"
NOTICE = "PC 에서 IR 자료를 첨부해주시기 바랍니다"


def _notice_body(stage) -> str:
    """안내창 본문만."""
    html = stage["client"].get("/deals?mode=ir&attach=1").text
    body = re.search(r'<p class="guard-body">(.*?)</p>', html, re.S)
    assert body, "안내창 본문을 찾지 못했습니다"
    return re.sub(r"<[^>]+>", "", body.group(1))


def _css_without_comments() -> str:
    """주석을 걷어낸 CSS — **브라우저처럼** 안 닫힌 주석은 끝까지 삼킨다.

    글자만 찾으면 `/*` 하나가 안 닫혀 아래 규칙이 통째로 죽은 날에도 검사가
    통과한다(실제로 그랬다). 브라우저가 버리는 것을 여기서도 버려야 한다.
    """
    css = pathlib.Path("app/static/css/app.css").read_text(encoding="utf-8")
    out, i = [], 0
    while True:
        start = css.find("/*", i)
        if start < 0:
            out.append(css[i:])
            break
        out.append(css[i:start])
        end = css.find("*/", start + 2)
        if end < 0:
            break                       # 안 닫힌 주석 — 여기서부터 없는 것이다
        i = end + 2
    return "".join(out)


@pytest.fixture()
def stage(client, db, users):
    from app.models import (DealBatch, DealBatchCompany, IrCompany, IrRequest,
                            MessageTemplate, SendItem, SendJob, SheetOwner,
                            VcContact)

    db.add(SheetOwner(label="내 명단", user_id=users["u1"].id))
    contact = VcContact(user_id=users["u1"].id, name="홍길동", title="팀장",
                        firm="가나벤처스", source_sheet="내 명단",
                        channel_kakao=1, connect_stage="connected",
                        kakao_room_name="홍길동 팀장님")
    agri = IrCompany(name="샘플애그", ir_file_name=FILE)
    medi = IrCompany(name="샘플메디")            # 자료 없음
    batch = DealBatch(user_id=users["u1"].id, title="8월 3주차",
                      sent_date="2026-08-19")
    db.add_all([contact, agri, medi, batch,
                # 인사는 인사말이 맡는다 — 여기에 또 넣으면 두 번 나간다
                MessageTemplate(user_id=None, kind="ir_delivery", is_active=1,
                                body="{기업목록} IR deck 먼저 전달드리겠습니다.")])
    db.commit()

    db.add_all([DealBatchCompany(batch_id=batch.id, company_id=agri.id, position=1),
                DealBatchCompany(batch_id=batch.id, company_id=medi.id, position=2)])
    job = SendJob(user_id=users["u1"].id, kind="deal_intro", batch_id=batch.id,
                  status="done")
    db.add(job)
    db.commit()
    # `stage` 는 빼먹으면 안 된다 — 기업 목록에 번호를 붙여 내보낸 발송인지를
    # 그 칸으로 가린다(`services/deal_numbers.for_contact`). 딜 소개는 늘 1 이다.
    db.add(SendItem(job_id=job.id, contact_id=contact.id, status="sent",
                    stage=mc.STAGE_DAY1,
                    room_name="홍길동 팀장님", message="…"))
    # 투자사가 "1번, 2번 주세요" 라고 답한 상태 — [자료 보내기] 가 눌리는 자리.
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
    return {"client": client, "contact": contact, "agri": agri, "medi": medi}


def _preview(stage, company_ids) -> dict:
    r = stage["client"].post("/api/deals/preview", json={
        "mode": "ir", "contact_ids": [stage["contact"].id],
        "company_ids": company_ids})
    assert r.status_code == 200, r.text
    return r.json()["previews"][0]


# --- 링크는 나가지 않는다 -----------------------------------------------------

def test_the_link_is_not_in_the_message(stage):
    """폐기한 것은 **보내는 방식**이다 — 링크가 문구에 실리지 않는다."""
    body = _preview(stage, [stage["agri"].id])["message"]
    assert LINK not in body, "구글 드라이브 링크 방식은 폐기했다"
    assert "drive.google.com" not in body
    # 파일명도 문구에 적지 않는다. 받는 쪽에 필요한 것은 **번호와 기업 이름**
    # 이고(투자사는 번호로 기억한다), 파일명은 보내는 쪽 사정이다.
    assert FILE not in body


def test_the_company_is_still_pointed_at_by_number(stage):
    """자료는 안 실려도 **어느 기업 자료인지**는 남아야 한다.

    투자사는 지난 회차의 번호로 기억하고 답한다("2번 주세요").
    """
    body = _preview(stage, [stage["agri"].id])["message"]
    assert "1번 기업 샘플애그" in body


def test_it_goes_as_one_message(stage):
    """링크를 한 통씩 먼저 던지던 것이 없어졌으니 나눌 것도 없다."""
    preview = _preview(stage, [stage["agri"].id, stage["medi"].id])
    assert preview["parts"] == []
    assert "1번 기업 샘플애그" in preview["message"]
    assert "2번 기업 샘플메디" in preview["message"]


def test_an_old_template_token_does_not_leak(db, stage):
    """손으로 고쳐 둔 문구에 `{자료링크}` 가 남아 있어도 **글자 그대로 나가면 안 된다**.

    모르는 `{…}` 는 그대로 두는 것이 치환 규칙이라(오타를 눈에 띄게 하려고),
    치환 목록에서 빼 버리면 토큰이 투자사 카톡방에 그대로 나간다.
    """
    from app.models import MessageTemplate

    row = db.query(MessageTemplate).filter_by(kind="ir_delivery").one()
    row.body = "{기업목록} IR deck 전달드립니다.\n\n{자료링크}"
    db.commit()

    body = _preview(stage, [stage["agri"].id])["message"]
    assert "{자료링크}" not in body
    assert LINK not in body


def test_composer_no_longer_fills_the_token():
    contact = mc.ContactView(name="홍길동", title="팀장", firm="가나벤처스")
    out = mc.compose_message("{담당자명} {직함} 안녕하세요.", "{자료링크}", contact,
                             stage=mc.STAGE_REMIND)
    assert "{자료링크}" not in out.text


def test_the_send_stores_no_parts(stage, db):
    """한 통이면 순서를 저장할 것이 없다."""
    from app.models import SendItem

    r = stage["client"].post("/api/deals/send", json={
        "mode": "ir", "contact_ids": [stage["contact"].id],
        "company_ids": [stage["agri"].id, stage["medi"].id]})
    assert r.status_code == 200, r.text

    item = db.query(SendItem).filter_by(job_id=r.json()["job_id"]).one()
    assert item.parts_json is None
    assert LINK not in item.message


def test_the_agent_gets_one_message(stage, db):
    from app.models import AgentDevice

    stage["client"].post("/api/deals/send", json={
        "mode": "ir", "contact_ids": [stage["contact"].id],
        "company_ids": [stage["agri"].id]})
    device = db.query(AgentDevice).filter_by(
        user_id=stage["contact"].user_id).first()

    payload = stage["client"].get(
        "/api/agent/poll",
        headers={"Authorization": f"Bearer {device.token}"}).json()
    item = payload["items"][0]
    assert item.get("parts") in (None, [])
    assert LINK not in item["message"]


# --- 자료가 없으면 첨부할 것이 없다 --------------------------------------------

def test_a_company_without_material_is_still_warned(stage):
    """파일명이 비어 있으면 붙일 것을 못 찾는다 — 보내기 전에 알려야 한다."""
    preview = _preview(stage, [stage["agri"].id, stage["medi"].id])
    assert any("샘플메디" in w and "첨부할 IR 자료가 없는 기업" in w
               for w in preview["warnings"])


def test_the_attachment_list_carries_the_file_name(stage):
    """화면의 [보낼 자료] 목록은 남는다 — 담기는 값이 **파일명**으로 바뀌었을 뿐.

    링크가 아니라서 열 수는 없다. 그래도 이름이 있어야 그 파일을 PC 에서 찾아
    붙일 수 있다.
    """
    preview = _preview(stage, [stage["agri"].id])
    assert preview["attachments"][0]["file"] == FILE
    assert preview["attachments"][0]["name"] == "샘플애그"


def test_a_plain_account_gets_no_files_in_the_job(stage, db):
    """자동 첨부를 켜지 않은 계정은 **지금까지 그대로** — 문구만 나간다.

    파일이 잡에 실리면 발송기가 붙여 보내고, 사람도 손으로 붙인다 —
    같은 자료가 두 번 나간다.
    """
    from app.models import SendItem

    r = stage["client"].post("/api/deals/send", json={
        "mode": "ir", "contact_ids": [stage["contact"].id],
        "company_ids": [stage["agri"].id]})
    assert r.status_code == 200, r.text
    item = db.query(SendItem).filter_by(job_id=r.json()["job_id"]).one()
    assert item.files_json is None


# --- [자료 보내기] — 활동 이력과 안내창 ----------------------------------------
#
# **이력은 보낸 때 남는다** — 누른 때가 아니다. [자료 보내기] 는 이제 화면을
# 옮기지 않고 그 자리에서 창을 여는 단추라(`static/js/ir_send.js`), 열어서
# 문구만 확인하고 닫는 것이 자연스러운 동작이다. 누른 때 적으면 보내지도 않은
# 건이 '자료 보냄' 으로 남는다. 왜 발송 목록을 만드는 자리로 옮겼는지는
# `app/services/ir_attach.py` 의 `record_delivery` 옆에 적어 두었다.

def _press_deliver(stage, follow=False):
    """스크립트가 죽었을 때의 길 — 폼이 그대로 서버로 온다."""
    return stage["client"].post(
        "/ir/deliver-guide",
        data={"contact_id": stage["contact"].id,
              "company_ids": f"{stage['agri'].id},{stage['medi'].id}"},
        follow_redirects=follow)


def _send_ir(stage):
    return stage["client"].post("/api/deals/send", json={
        "mode": "ir", "contact_ids": [stage["contact"].id],
        "company_ids": [stage["agri"].id, stage["medi"].id]})


def _history(db, stage):
    from app.models import ContactActivity

    return db.query(ContactActivity).filter_by(
        contact_id=stage["contact"].id, kind="ir_delivery").all()


def test_sending_leaves_a_line_in_the_history(stage, db):
    """자료를 앱이 안 보내므로, 여기 안 적으면 손으로 한 일이 아무 데도 안 남는다."""
    assert _send_ir(stage).status_code == 200

    rows = _history(db, stage)
    assert len(rows) == 1
    assert "PC 에서 직접 첨부" in rows[0].content
    assert rows[0].source == "system"
    assert sorted(rows[0].companies) == ["샘플메디", "샘플애그"]


def test_pressing_it_leaves_nothing_until_it_is_sent(stage, db):
    """누르기만 한 것은 **아직 아무것도 아니다.**

    창을 열어 문구만 보고 닫는 일이 흔한데, 그것까지 '자료 보냄' 으로 남으면
    이력을 훑어도 무엇이 실제로 나갔는지 알 수 없다.
    """
    _press_deliver(stage)

    assert _history(db, stage) == []


def test_sending_twice_does_not_pile_up(stage, db):
    """두 번 보냈다고 같은 줄이 두 번 쌓이면 이력이 아니라 소음이다.

    실패해서 다시 보내는 것은 흔한 일이다 — 같은 날 같은 묶음이면 한 줄이다.
    """
    _send_ir(stage)
    _send_ir(stage)

    assert len(_history(db, stage)) == 1


def test_the_deal_screen_leaves_the_same_line(stage, db):
    """딜 제안 관리에서 바로 보내도 **같은 줄이 남는다.**

    예전에는 IR 관리의 단추가 제 손으로 적어서, 그 화면을 거치지 않고 보낸
    건은 이력에 아무 줄도 없었다 — 같은 일을 두 화면이 다르게 기록했다.
    """
    r = stage["client"].post("/api/deals/send", json={
        "mode": "ir", "contact_ids": [stage["contact"].id],
        "company_ids": [stage["agri"].id]})
    assert r.status_code == 200, r.text

    rows = _history(db, stage)
    assert len(rows) == 1
    assert rows[0].companies == ["샘플애그"]


def test_a_deal_intro_leaves_no_ir_line(stage, db):
    """딜 소개는 자료 전달이 아니다 — 그 줄이 붙으면 안 보낸 자료가 남는다."""
    stage["client"].post("/api/deals/send", json={
        "contact_ids": [stage["contact"].id], "company_ids": [stage["agri"].id]})

    assert _history(db, stage) == []


def test_sending_does_not_close_the_request(stage, db):
    """발송 목록을 만든 것만으로는 닫지 않는다.

    아직 나가지 않았다. 여기서 닫으면 발송이 실패해도 '보낼 자료' 에서 사라진다 —
    닫는 것은 발송기가 실제로 보내고 난 뒤다(`pipeline.close_requests_for`).
    """
    from app.models import IrRequest

    _send_ir(stage)

    rows = db.query(IrRequest).filter_by(contact_id=stage["contact"].id).all()
    assert [r.status for r in rows] == ["open", "open"]


def test_the_fallback_lands_on_the_send_screen_with_everything_picked(stage):
    """스크립트가 안 실렸을 때의 길 — 예전 그대로 발송 화면으로 간다."""
    r = _press_deliver(stage)
    assert r.status_code == 303
    where = r.headers["location"]
    assert where.startswith("/deals?")
    assert "mode=ir" in where
    assert f"contacts={stage['contact'].id}" in where
    assert f"companies={stage['agri'].id},{stage['medi'].id}" in where
    assert "attach=1" in where


def test_the_send_screen_says_to_attach_on_the_pc(stage):
    import re

    html = _press_deliver(stage, follow=True).text
    assert NOTICE in html
    # 닫는 길은 **평범한 링크**다 — 스크립트 예외 하나로 발송 화면이 통째로
    # 가려지면 안 된다(`admin_only.html` 과 같은 조심). 닫으면 안내창만 빠지고
    # 골라 둔 담당자·기업은 그대로다.
    close = re.search(r'guard-go" href="([^"]+)"', html)
    assert close, "안내창을 닫을 링크가 없다"
    assert close.group(1).startswith("/deals?")
    assert "attach" not in close.group(1)
    assert "mode=ir" in close.group(1)
    assert f"contacts={stage['contact'].id}" in close.group(1)


def test_the_notice_is_not_shown_on_a_plain_visit(stage):
    """평소에 발송 화면을 열 때는 안내창이 뜨지 않는다."""
    html = stage["client"].get("/deals").text
    assert NOTICE not in html


def test_the_notice_needs_something_to_point_at(stage):
    """`mode=ir` 없이 `attach=1` 만 있으면 **안내창을 띄우지 않는다**.

    안내창은 `[보낼 자료]` 칸을 가리키는데 그 칸은 IR 자료 전달 방식에서만
    켜진다(`deals.js` 의 `renderIrLinks`). 방식이 안 실린 주소에서는 화면에
    없는 칸을 가리키는 안내가 되어, 자료를 어디서 받는지 찾다가 그냥 [발송]
    을 누르게 된다 — 안내창이 막으려던 바로 그 일이다.

    정상 경로로는 안 생긴다(`/ir/deliver-guide` 가 둘을 늘 함께 붙인다).
    주소를 손보거나 즐겨찾기로 다시 열 때 생긴다.
    """
    assert NOTICE not in stage["client"].get("/deals?attach=1").text


def test_the_notice_is_shown_when_the_mode_came_along(stage):
    """둘이 함께 실려 오는 정상 경로에서는 그대로 뜬다."""
    assert NOTICE in stage["client"].get("/deals?mode=ir&attach=1").text


def test_the_notice_does_not_say_which_way_to_look(stage):
    """가리킬 때 **방향을 말하지 않는다.**

    `[보낼 자료]` 칸은 넓은 화면에서 오른쪽 미리보기 안에 있고, 좁은
    화면(900px 이하)에서 칸이 세로로 쌓일 때만 아래다 — '아래' 든 '오른쪽'
    이든 한쪽 폭에서는 틀린 말이 되어, 그 말대로 본 사람은 없는 자리를 본다.
    """
    body = _notice_body(stage)
    assert "보낼 자료" in body, "가리키는 칸 이름은 남아 있어야 한다"
    for way in ("아래", "위쪽", "오른쪽", "왼쪽", "우측", "좌측", "하단", "상단"):
        assert way not in body, f"화면 폭에 따라 틀려지는 말입니다: {way}"


def test_the_sidebar_dims_with_the_backdrop():
    """뒷막이 뜨면 **좌측 메뉴도 눈에 띄게 어두워져야 한다.**

    뒷막은 사이드바까지 덮어 메뉴를 정말로 막는다. 그런데 뒷막색이 사이드바
    바탕색(#10151d)과 같아서 사이드바 위에서는 아무 일도 일어나지 않았다 —
    본문만 흐려지고 메뉴는 멀쩡해 보이니 눌러 보고 나서야 막힌 줄 안다.

    **주석을 걷어낸 뒤** 찾는다. 전에 CSS 주석이 안 닫혀 규칙이 통째로 죽은
    적이 있는데, 글자만 찾으면 그때도 이 검사는 통과한다.
    """
    css = _css_without_comments()
    rule = re.search(r"\.layout:has\(\.guard-backdrop\)\s+\.sidebar\s*\{([^}]*)\}", css)
    assert rule, "뒷막이 떴을 때 사이드바를 어둡게 하는 규칙이 없습니다"
    assert "brightness(" in rule.group(1), (
        "어두운 색을 덧칠하는 방식으로는 이미 어두운 사이드바를 어둡게 할 수 없습니다")


def test_the_backdrop_itself_is_not_made_heavier():
    """본문 쪽은 지금보다 과해지지 않는다 — 뒷막에 `backdrop-filter` 를 걸면
    사이드바와 함께 본문도 더 어두워진다."""
    css = _css_without_comments()
    rule = re.search(r"\.guard-backdrop\s*\{([^}]*)\}", css)
    assert rule, "뒷막 규칙이 사라졌거나 주석 안에 갇혔습니다"
    assert "rgba(16,21,29,.28)" in rule.group(1)
    assert "backdrop-filter" not in rule.group(1)


def test_another_persons_contact_is_refused(client, db, users, stage):
    """남의 담당자로 이력을 남길 수 없다."""
    client.post("/login", data={"phone": "01000000002", "password": DEMO_PASSWORD})
    r = client.post("/ir/deliver-guide",
                    data={"contact_id": stage["contact"].id, "company_ids": ""})
    assert r.status_code == 404


# --- 인사말 --------------------------------------------------------------------

def test_the_greeting_appears_exactly_once(stage):
    """인사말은 모든 방식에서 기본으로 붙는다. 자료 전달 문구가 자체적으로
    인사로 시작하면 **두 번** 나가므로, 그 문구는 본문만 담는다."""
    body = _preview(stage, [stage["agri"].id])["message"]
    assert body.count("안녕하세요") == 1, body


def test_the_greeting_is_on_by_default_except_when_asking(stage):
    """빼는 것은 선호 분야를 되물을 때뿐이다 — 그건 이미 대화가 오간 방에
    한 줄만 덧붙이는 것이라 다시 인사하면 어색하다."""
    js = pathlib.Path("app/static/js/deals.js").read_text(encoding="utf-8")
    assert 'greet.checked = (mode !== "ask")' in js


def test_it_can_still_be_turned_off(stage):
    """켜고 끄는 것은 사람이 정한다 — 기본값만 정해 둔 것이다."""
    r = stage["client"].post("/api/deals/preview", json={
        "mode": "ir", "contact_ids": [stage["contact"].id],
        "company_ids": [stage["agri"].id], "include_opening": False})
    assert "안녕하세요" not in r.json()["previews"][0]["message"]


def test_deal_intro_still_greets(stage):
    """딜소개는 처음 여는 말이 필요하다."""
    r = stage["client"].post("/api/deals/preview", json={
        "contact_ids": [stage["contact"].id], "company_ids": [stage["agri"].id]})
    assert "안녕하세요" in r.json()["previews"][0]["message"]


def test_deal_intro_never_carried_links(stage):
    """딜소개에는 애초에 링크를 붙이지 않았다 — 그대로다."""
    r = stage["client"].post("/api/deals/preview", json={
        "contact_ids": [stage["contact"].id],
        "company_ids": [stage["agri"].id]})
    assert LINK not in r.json()["previews"][0]["message"]
