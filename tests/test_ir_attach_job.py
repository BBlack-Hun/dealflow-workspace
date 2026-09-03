"""자료 파일을 **발송기가 붙여 보낸다** — 잡에 싣는 자리부터 보내는 차례까지.

#110 이 발송기 쪽(파일 붙이기·관문)을 만들었지만 **잇지 않았다.** 화면에서
[자료 보내기] 를 눌러도 문구만 나갔다 — 잡에 파일명이 실리지 않았고, 발송기의
`send_file` 을 아무도 부르지 않았다. 여기서 그 두 자리를 지킨다.

## 누가 이 길을 타나

**자기 PC 의 자료 폴더를 정해 둔 계정만**(`agent_devices.ir_root`). 사람 이름을
코드에 적지 않는다 — 왜 그 칸으로 가르는지는 `app/services/ir_attach.py` 에
적어 두었다. 정하지 않은 계정은 **지금까지 그대로**: 문구만 나가고 안내창이
뜨고 사람이 PC 카톡에서 손으로 붙인다.

## 무엇을 지키나

1. 켠 계정의 잡에는 파일명이 **고른 차례대로** 실린다
2. 켜지 않은 계정의 잡에는 **안 실린다** (자료가 두 번 나가면 안 된다)
3. 파일명이 빈 기업이 있으면 **목록을 아예 안 만든다** — 자료 없이
   "보내드렸습니다" 만 나가는 것이 제일 나쁘다
4. 발송기는 **파일을 먼저, 문구를 마지막**으로 보낸다
5. 파일이 하나라도 실패하면 **문구를 보내지 않는다**
"""
from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

from .conftest import DEMO_PASSWORD

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

AGRI_FILE = "샘플애그_IR_2026.pdf"
MEDI_FILE = "샘플메디 IR deck.pdf"


# ── 화면에서 발송 목록까지 ──────────────────────────────────────────────────

@pytest.fixture()
def stage(client, db, users):
    """자료를 기다리는 투자사 한 명 + 자료가 있는 기업 둘."""
    from app.models import (IrCompany, MessageTemplate, SheetOwner, VcContact)

    db.add(SheetOwner(label="내 명단", user_id=users["u1"].id))
    contact = VcContact(user_id=users["u1"].id, name="홍길동", title="팀장",
                        firm="가나벤처스", source_sheet="내 명단",
                        channel_kakao=1, connect_stage="connected",
                        kakao_room_name="홍길동 팀장님")
    agri = IrCompany(name="샘플애그", ir_file_name=AGRI_FILE)
    medi = IrCompany(name="샘플메디", ir_file_name=MEDI_FILE)
    bare = IrCompany(name="샘플페이")            # 자료 파일명이 없다
    db.add_all([contact, agri, medi, bare,
                MessageTemplate(user_id=None, kind="ir_delivery", is_active=1,
                                body="{기업목록} IR deck 먼저 전달드리겠습니다.")])
    db.commit()

    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    return {"client": client, "db": db, "user": users["u1"], "contact": contact,
            "agri": agri, "medi": medi, "bare": bare}


def _turn_on(stage):
    """이 계정의 기기에 자료 폴더를 정해 둔다 — 자동 첨부를 켜는 유일한 스위치."""
    from app.models import AgentDevice

    device = stage["db"].query(AgentDevice).filter_by(
        user_id=stage["user"].id).one()
    device.ir_root = "/Users/somebody/IR자료"
    stage["db"].commit()
    return device


def _send(stage, company_ids, **extra):
    return stage["client"].post("/api/deals/send", json={
        "mode": "ir", "contact_ids": [stage["contact"].id],
        "company_ids": company_ids, **extra})


def _files_of(stage, job_id) -> list:
    from app.models import SendItem

    item = stage["db"].query(SendItem).filter_by(job_id=job_id).one()
    return json.loads(item.files_json) if item.files_json else []


def test_the_job_carries_the_file_names(stage):
    """켠 계정 — 발송기가 무엇을 붙일지 알아야 붙일 수 있다."""
    _turn_on(stage)

    r = _send(stage, [stage["agri"].id, stage["medi"].id])
    assert r.status_code == 200, r.text
    assert _files_of(stage, r.json()["job_id"]) == [AGRI_FILE, MEDI_FILE]


def test_the_file_order_follows_the_pick_order(stage):
    """문구가 기업을 짚는 차례이자 발송기가 파일을 보내는 차례다.

    여기서 다시 정렬하면 "1번 기업 …, 2번 기업 …" 과 올라온 파일의 차례가
    갈린다 — 받는 쪽은 어느 파일이 어느 기업인지 알 수 없게 된다.
    """
    _turn_on(stage)

    r = _send(stage, [stage["medi"].id, stage["agri"].id])
    assert _files_of(stage, r.json()["job_id"]) == [MEDI_FILE, AGRI_FILE]


def test_an_account_that_did_not_turn_it_on_sends_no_files(stage):
    """켜지 않은 계정은 **지금까지 그대로** — 문구만 나가고 사람이 붙인다.

    여기에 파일이 실리면 발송기도 붙이고 사람도 붙여 자료가 두 번 나간다.
    """
    r = _send(stage, [stage["agri"].id, stage["medi"].id])
    assert r.status_code == 200, r.text
    assert _files_of(stage, r.json()["job_id"]) == []


def test_one_persons_folder_does_not_turn_it_on_for_another(stage, db, users):
    """자료 폴더는 **그 PC 의 것**이다 — 남이 정했다고 내 발송이 달라지면 안 된다."""
    from app.models import AgentDevice

    other = db.query(AgentDevice).filter_by(user_id=users["u2"].id).one()
    other.ir_root = "/Users/other/IR자료"
    db.commit()

    r = _send(stage, [stage["agri"].id])
    assert _files_of(stage, r.json()["job_id"]) == []


def test_a_blank_folder_setting_does_not_count(stage):
    """공백만 넣어 둔 것은 정한 것이 아니다 — 발송기도 그 값으로는 못 찾는다."""
    device = _turn_on(stage)
    device.ir_root = "   "
    stage["db"].commit()

    r = _send(stage, [stage["agri"].id])
    assert _files_of(stage, r.json()["job_id"]) == []


# ── 파일명이 없으면 보내지 않는다 ───────────────────────────────────────────

def test_a_company_without_a_file_name_stops_the_send_list(stage):
    """자료 없이 "보내드리겠습니다" 만 나가는 것이 **제일 나쁘다.**

    목록을 만들어 두면 발송기가 그 건에서 실패하고, 실패한 건은 문구도 안 나가서
    그 사람만 아무것도 못 받는다 — 그것을 회차가 끝난 뒤에 알게 된다.
    """
    from app.models import SendJob

    _turn_on(stage)

    r = _send(stage, [stage["agri"].id, stage["bare"].id])
    assert r.status_code == 400, r.text
    assert "샘플페이" in r.json()["detail"]
    # 조용히 빼고 보내지 않는다 — 목록 자체가 안 생겨야 한다.
    assert stage["db"].query(SendJob).count() == 0


def test_a_missing_file_name_still_only_warns_when_it_is_off(stage):
    """켜지 않은 계정에서는 지금까지처럼 **경고만** 하고 보낼 수 있다.

    그쪽은 사람이 붙이는 길이라, 앱이 막으면 손으로 보낼 수 있던 것까지 못 보낸다.
    """
    r = _send(stage, [stage["agri"].id, stage["bare"].id])
    assert r.status_code == 200, r.text


def test_the_preview_warns_before_the_list_is_made(stage):
    """막히는 것을 [발송] 을 누른 뒤에 알면 늦다."""
    _turn_on(stage)

    r = stage["client"].post("/api/deals/preview", json={
        "mode": "ir", "contact_ids": [stage["contact"].id],
        "company_ids": [stage["agri"].id, stage["bare"].id]})
    warnings = r.json()["previews"][0]["warnings"]
    assert any("샘플페이" in w and "첨부할 IR 자료가 없는 기업" in w for w in warnings)


def test_email_never_carries_files(stage, db, monkeypatch):
    """파일은 **각자 PC** 에 있고 메일은 서버가 보낸다 — 서버에는 그 파일이 없다."""
    from app.services import mail_sender

    _turn_on(stage)
    stage["contact"].email = "hong@example.test"
    stage["contact"].channel_email = 1
    db.commit()

    for key, value in (("HOST", "smtp.example.test"), ("PORT", "465"),
                       ("USER", "deal@example.test"), ("FROM", "deal@example.test"),
                       ("PASSWORD", "secret")):
        monkeypatch.setenv(f"DEALFLOW_SMTP_{key}", value)
    monkeypatch.setattr(mail_sender, "send_job", lambda *a, **k: None)

    r = _send(stage, [stage["agri"].id], channel="email")
    assert r.status_code == 200, r.text
    assert _files_of(stage, r.json()["job_id"]) == []


# ── 화면이 같은 판단을 읽는가 ───────────────────────────────────────────────

def test_the_attach_notice_disappears_once_it_is_on(stage):
    """발송기가 붙이는데 "PC 에서 첨부하세요" 가 뜨면 자료가 두 번 나간다."""
    _turn_on(stage)

    html = stage["client"].get(
        f"/deals?attach=1&mode=ir&contacts={stage['contact'].id}").text
    assert "PC 에서 IR 자료를 첨부해주시기 바랍니다" not in html


def test_the_attach_notice_still_shows_when_it_is_off(stage):
    """켜지 않은 사람에게는 지금 동작 그대로다."""
    html = stage["client"].get(
        f"/deals?attach=1&mode=ir&contacts={stage['contact'].id}").text
    assert "PC 에서 IR 자료를 첨부해주시기 바랍니다" in html


def test_the_material_list_says_who_attaches(stage):
    """같은 목록이 두 가지 말을 한다 — 발송기가 붙이는가, 사람이 붙이는가."""
    off = stage["client"].get("/deals").text
    assert "PC 카톡에서 직접 첨부한 뒤" in off

    _turn_on(stage)
    on = stage["client"].get("/deals").text
    assert "발송 프로그램이 아래 파일을 먼저 보내고" in on


def test_the_request_screen_says_the_same_thing(stage):
    """`/ir` 과 `/deals` 가 **같은 판단**을 읽어야 한다.

    한쪽은 "손으로 붙이세요", 다른 쪽은 발송기가 붙이는 상태가 되면 자료가
    두 번 나간다.
    """
    off = stage["client"].get("/ir").text
    assert "PC 카톡에서 직접 첨부" in off

    _turn_on(stage)
    on = stage["client"].get("/ir").text
    assert "발송 프로그램이 붙여 보냅니다" in on
    assert "PC 카톡에서 직접 첨부" not in on


def test_the_preview_tells_the_screen_which_way_it_goes(stage):
    body = stage["client"].post("/api/deals/preview", json={
        "mode": "ir", "contact_ids": [stage["contact"].id],
        "company_ids": [stage["agri"].id]}).json()
    assert body["auto_attach"] is False

    _turn_on(stage)
    body = stage["client"].post("/api/deals/preview", json={
        "mode": "ir", "contact_ids": [stage["contact"].id],
        "company_ids": [stage["agri"].id]}).json()
    assert body["auto_attach"] is True


# ── 발송기가 받아 가는 자리 ─────────────────────────────────────────────────

def _poll(stage, token, **params):
    return stage["client"].get("/api/agent/poll", params=params,
                               headers={"Authorization": f"Bearer {token}"})


def test_the_agent_is_handed_the_file_names(stage, db, users):
    from app.models import AgentDevice

    _turn_on(stage)
    _send(stage, [stage["agri"].id, stage["medi"].id])
    token = db.query(AgentDevice).filter_by(user_id=users["u1"].id).one().token

    payload = _poll(stage, token, kinds="ir_delivery", files=1).json()
    assert payload["items"][0]["files"] == [AGRI_FILE, MEDI_FILE]


def test_an_agent_that_cannot_attach_is_not_handed_the_job(stage, db, users):
    """구버전 발송기는 이 칸을 **그냥 무시하고 문구만** 보낸다.

    그러면 "자료 전달드리겠습니다" 만 나가고 자료가 없다. `kinds` 와 같은
    방식으로 막는다 — 밝힌 발송기에게만 준다.
    """
    from app.models import AgentDevice, SendJob

    _turn_on(stage)
    _send(stage, [stage["agri"].id])
    token = db.query(AgentDevice).filter_by(user_id=users["u1"].id).one().token

    assert _poll(stage, token, kinds="ir_delivery").status_code == 204

    # 실패로 닫지 않는다 — 발송기를 갱신하면 그다음 폴링에 그대로 이어 나간다.
    db.expire_all()
    assert db.query(SendJob).one().status == "queued"
    assert _poll(stage, token, kinds="ir_delivery", files=1).status_code == 200


def test_a_job_without_files_still_goes_to_an_old_agent(stage, db, users):
    """파일이 없는 잡까지 막으면, 갱신 안 한 사람은 아무것도 못 보낸다."""
    from app.models import AgentDevice

    _send(stage, [stage["agri"].id])          # 자동 첨부를 켜지 않았다
    token = db.query(AgentDevice).filter_by(user_id=users["u1"].id).one().token

    payload = _poll(stage, token, kinds="ir_delivery").json()
    assert "files" not in payload["items"][0]


# ── 발송기 — 파일이 먼저, 문구가 마지막 ─────────────────────────────────────

@pytest.fixture()
def agent_main():
    return importlib.import_module("agent.main")


class FakeResult:
    def __init__(self, ok=True, error=None):
        self.ok = ok
        self.error = error
        self.screenshot_b64 = None


class FakeSender:
    """보낸 것을 **한 줄에 순서대로** 적어 두는 가짜 카톡.

    파일과 문구를 같은 목록에 적는다 — 무엇이 먼저 나갔는지가 이 파일의 핵심이라,
    따로 적어 두면 차례를 볼 수가 없다.
    """

    def __init__(self, files_fail=False):
        self.sent = []
        self.files_fail = files_fail

    def send_file(self, room, file_names):
        self.sent.append(("file", room, list(file_names)))
        if self.files_fail:
            return FakeResult(ok=False, error="이 PC 에 없습니다")
        return FakeResult(ok=True)

    def send_text(self, room, text):
        self.sent.append(("text", room, text))
        return FakeResult(ok=True)


NO_GAP = {"part_gap_sec": 0}
ITEM = {"room_name": "홍길동 팀장님", "message": "1번 기업 샘플애그 전달드리겠습니다."}


def test_files_go_before_the_message(agent_main):
    sender = FakeSender()
    result = agent_main.send_item(
        sender, {**ITEM, "files": [AGRI_FILE, MEDI_FILE]}, NO_GAP)

    assert result.ok
    assert [kind for kind, _room, _what in sender.sent] == ["file", "text"]
    assert sender.sent[0][2] == [AGRI_FILE, MEDI_FILE], "차례가 바뀌었다"
    assert sender.sent[1][2] == ITEM["message"]


def test_a_failed_file_stops_the_message(agent_main):
    """★ "자료 보내드렸습니다" 만 나가고 자료가 없는 것이 제일 나쁘다."""
    sender = FakeSender(files_fail=True)
    result = agent_main.send_item(sender, {**ITEM, "files": [AGRI_FILE]}, NO_GAP)

    assert not result.ok
    assert [kind for kind, _room, _what in sender.sent] == ["file"], \
        "파일이 실패했는데 문구가 나갔다"
    assert "문구도 보내지 않았습니다" in result.error, result.error
    assert "이 PC 에 없습니다" in result.error, "왜 막혔는지 원인이 남아야 한다"


def test_no_files_means_todays_behaviour(agent_main):
    """파일이 없으면 지금까지 그대로 — 문구만 나간다."""
    sender = FakeSender()
    result = agent_main.send_item(sender, ITEM, NO_GAP)

    assert result.ok
    assert [kind for kind, _room, _what in sender.sent] == ["text"]


def test_an_empty_file_list_does_not_open_the_attach_path(agent_main):
    """빈 목록으로 `send_file` 을 부르면 '보낼 파일이 없습니다' 로 실패한다 —
    보낼 것이 없는데 실패로 남으면 그 사람만 문구를 못 받는다."""
    sender = FakeSender()
    result = agent_main.send_item(sender, {**ITEM, "files": ["", "  "]}, NO_GAP)

    assert result.ok
    assert [kind for kind, _room, _what in sender.sent] == ["text"]


def test_the_agent_tells_the_server_it_can_attach(agent_main):
    """밝히지 않으면 서버가 파일이 실린 잡을 안 준다 — 두 곳이 같은 말을 써야 한다."""
    main = (ROOT / "agent" / "main.py").read_text(encoding="utf-8")
    assert '"files": 1' in main, "폴링에서 파일 처리 가능을 안 밝힌다"


def test_a_sender_that_cannot_attach_fails_loudly(agent_main):
    """되는 척하지 않는다 — 구현하지 않은 발송기는 분명히 실패한다.

    조용히 성공으로 넘어가면 자료가 안 나갔는데 나갔다고 기록된다.
    """
    from agent.sender.base import Sender

    result = agent_main.send_item(Sender(), {**ITEM, "files": [AGRI_FILE]}, NO_GAP)
    assert not result.ok
    assert "file_send_unsupported" in result.error


# ── 화면 로직 — [보낼 자료] 목록 ────────────────────────────────────────────
#
# 파일명을 링크로 걸면 눌러도 아무 일이 없다. 그것은 `deals.js` 를 **그대로
# 실행해야** 보이므로 브라우저 검사로 따로 둔다(`tests/js/deals_ir_files_test.js`).
# 로컬에서는 `node tests/js/deals_ir_files_test.js` 로도 돈다.

def test_the_material_list_shows_a_name_not_a_link():
    import shutil
    import subprocess

    node = shutil.which("node")
    if node is None:
        pytest.skip("node 미설치 — 브라우저 로직 테스트 생략 "
                    "(호스트에서 `node tests/js/deals_ir_files_test.js`)")
    js = Path(__file__).resolve().parent / "js" / "deals_ir_files_test.js"
    result = subprocess.run([node, str(js)], capture_output=True,
                            text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr


def test_the_picker_carries_the_file_name_to_the_screen():
    """화면 코드가 읽는 속성(`data-ir-file`)을 템플릿이 실제로 싣는가.

    한쪽만 고치면 목록이 늘 "첨부할 자료가 없습니다" 로 뜬다 — 값은 DB 에
    멀쩡히 들어 있는데.
    """
    root = Path(__file__).resolve().parents[1]
    html = (root / "app" / "templates" / "deals.html").read_text(encoding="utf-8")
    js = (root / "app" / "static" / "js" / "deals.js").read_text(encoding="utf-8")

    assert 'data-ir-file="{{ c.ir_file_name' in html
    assert 'getAttribute("data-ir-file")' in js
    assert "data-ir-url" not in html + js, "옛 속성이 남아 있다"
