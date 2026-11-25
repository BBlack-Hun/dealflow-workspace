"""메일로 나가는 IR 자료 전달에 **자료 파일이 붙는다** (0.11.17).

메일은 서버가 보내는데 자료 파일은 각자 PC 의 자료 폴더에만 있다. 그래서

1. 파일이 실린 메일 건은 **파일이 올라올 때까지 대기**한다(까닭이 그 줄에 선다).
2. 발송기는 박동에 `mail_files` 를 밝혀야 올릴 건을 받는다 — 낡은 판 · 남의 발송기 ·
   자동 첨부가 꺼진 계정 · 자료 폴더가 없는 PC 에는 주지 않는다.
3. 올리는 문은 좁다 — 토큰 · 그 발송기에 내준 건 · 그 건에 적힌 파일 차례만.
   이름을 받지 않으니 경로가 될 글자가 없고, 흘려 받으며 크기를 센다.
4. 다 올라오면 예약 실이 이어 보내고(시간 · 상한은 그대로), 끝난 건의 파일은 지운다.
5. 상한을 넘으면 그 건은 **실패**다(사유가 선다).
6. 발송기 쪽: 폴더에서 찾아 올리고, 없거나 크면 올리지 않고 실패로 알린다.
"""
from __future__ import annotations

import importlib
import json
import sys
from datetime import datetime
from pathlib import Path

import pytest

from .conftest import DEMO_TOKEN, OTHER_TOKEN, auth

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

FILES = ["샘플애그_IR_2026.pdf", "샘플메디 IR deck.pptx"]
PDF = b"%PDF-1.4 sample agri deck"
PPT = b"PK sample medi deck"


@pytest.fixture()
def data_dir(tmp_path, monkeypatch):
    from app import config

    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    return tmp_path


@pytest.fixture()
def mail_on(monkeypatch):
    for key, value in (("HOST", "smtp.example.com"), ("PORT", "465"),
                       ("USER", "deal@example.com"), ("FROM", "deal@example.com"),
                       ("PASSWORD", "secret")):
        monkeypatch.setenv(f"DEALFLOW_SMTP_{key}", value)


@pytest.fixture()
def outbox(monkeypatch):
    """가짜 SMTP — 나간 메일을 통째로 적어 둔다. 받는 크기(`SIZE`)는 검사가 정한다."""
    from app.services import mail_sender, mailer

    class Outbox(list):
        smtp = None             # 가짜 SMTP 틀 — 검사가 받는 크기 · 실패를 끼운다
        timeouts = None         # 붙을 때마다 넘긴 대기 시간(안 넘겼으면 None)

    sent = Outbox()

    class FakeSMTP:
        esmtp_features: dict = {}

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def ehlo_or_helo_if_needed(self):
            pass

        def login(self, *a):
            pass

        def send_message(self, msg):
            sent.append(msg)

    sent.timeouts = []

    def connect(s, timeout=None):
        sent.timeouts.append(timeout)
        return FakeSMTP()

    monkeypatch.setattr(mailer, "_connect", connect)
    # 이어 보내기 실을 그 자리에서 돌린다.
    monkeypatch.setattr(mail_sender, "_dispatch", lambda func, *args: func(*args))
    monkeypatch.setattr(mail_sender, "GAP_SEC", 0)
    sent.smtp = FakeSMTP
    return sent


@pytest.fixture()
def stage(client, db, users, data_dir, mail_on):
    """자동 첨부를 켠 u1(자료 폴더까지) + 파일 둘이 실린 대기 메일 건 하나."""
    from app.models import AgentDevice, SendItem, SendJob, VcContact

    users["u1"].can_auto_attach_ir = 1
    db.query(AgentDevice).filter_by(user_id=1).one().ir_root = "/Users/somebody/IR자료"
    contact = VcContact(user_id=1, name="홍길동", firm="가나벤처스",
                        email="hong@example.com")
    job = SendJob(user_id=1, kind="ir_delivery", status="queued", total=1)
    db.add_all([contact, job])
    db.flush()
    item = SendItem(job_id=job.id, contact_id=contact.id, channel="email",
                    room_name="hong@example.com", subject="IR 자료 전달드립니다",
                    message="[기업1] 샘플애그 자료 전달드립니다.",
                    files_json=json.dumps(FILES, ensure_ascii=False), status="pending")
    db.add(item)
    db.commit()
    return {"client": client, "job_id": job.id, "item_id": item.id,
            "dir": data_dir / "mail_attachments" / str(item.id)}


def _item(db, stage):
    from app.models import SendItem

    db.expire_all()
    return db.get(SendItem, stage["item_id"])


def _job(db, stage):
    from app.models import SendJob

    db.expire_all()
    return db.get(SendJob, stage["job_id"])


def _beat(client, token=DEMO_TOKEN, **body):
    return client.post("/api/agent/heartbeat", json=body, headers=auth(token)).json()


def _upload(stage, index, content, token=DEMO_TOKEN, item_id=None):
    return stage["client"].post(
        f"/api/agent/items/{item_id or stage['item_id']}/mail-files/{index}",
        content=content, headers=auth(token))


# ── 1. 파일이 올라올 때까지 대기 ─────────────────────────────────────────────

def test_mail_waits_until_the_files_arrive(db, stage, outbox):
    from app.services import mail_attach, mail_sender

    mail_sender._run(db, stage["job_id"], gap_sec=0)

    assert outbox == [], "자료 파일 없이 메일이 나갔다"
    item = _item(db, stage)
    assert item.status == "pending", "실패로 닫으면 사람이 다시 만들어야 한다"
    assert item.error == mail_attach.WAIT
    assert "발송 프로그램" in item.error, "무엇을 해야 나가는지 진행 화면에 서야 한다"
    assert _job(db, stage).status == "queued"
    # 파일이 없는 동안은 예약 실이 깨어나도 띄울 것이 없다.
    assert mail_sender.resume_waiting(db) == []


def test_a_mail_without_files_is_not_held_back(db, stage, outbox):
    """딜 소개 같은 여느 메일은 지금까지 그대로 바로 나간다."""
    from app.services import mail_sender

    _item(db, stage).files_json = None
    db.commit()
    mail_sender._run(db, stage["job_id"], gap_sec=0)

    assert len(outbox) == 1 and not list(outbox[0].iter_attachments())
    assert _item(db, stage).status == "sent"


# ── 2. 누구에게 올릴 건을 주나 ───────────────────────────────────────────────

def test_the_agent_is_offered_the_waiting_item(db, stage):
    from app.services import mail_attach

    got = _beat(stage["client"], mail_files=True)

    assert got["mail_uploads"] == [{"id": stage["item_id"], "files": FILES}]
    assert got["mail_max_bytes"] == mail_attach.DEFAULT_MAX_MB * 1024 * 1024


def test_an_old_agent_is_offered_nothing(db, stage):
    """`mail_files` 를 안 밝히는 낡은 판 — 판 번호로 가리지 않는다. 그 건은 대기로 남는다."""
    got = _beat(stage["client"], agent_version="99.0.0")

    assert "mail_uploads" not in got
    assert _item(db, stage).status == "pending"


@pytest.mark.parametrize("spoil", ["other_device", "switched_off", "no_folder",
                                   "draft_job", "kakao_item", "done_item"])
def test_nothing_is_offered_or_accepted_outside_the_gate(db, stage, spoil):
    """내주는 자리와 받는 자리가 **같은 판정**이다(`agent_api._may_upload`)."""
    from app.models import AgentDevice, User

    token = DEMO_TOKEN
    if spoil == "other_device":
        # 남의 발송기 — 제 계정은 켜져 있고 폴더도 있지만 이 건은 u1 것이다.
        db.query(AgentDevice).filter_by(user_id=2).one().ir_root = "/Users/else/IR"
        db.get(User, 2).can_auto_attach_ir = 1
        token = OTHER_TOKEN
    elif spoil == "switched_off":
        db.get(User, 1).can_auto_attach_ir = 0
    elif spoil == "no_folder":
        db.query(AgentDevice).filter_by(user_id=1).one().ir_root = ""
    elif spoil == "draft_job":
        _job(db, stage).status = "draft"
    elif spoil == "kakao_item":
        _item(db, stage).channel = "kakao"
    elif spoil == "done_item":
        _item(db, stage).status = "canceled"
    db.commit()

    assert _beat(stage["client"], token=token, mail_files=True)["mail_uploads"] == []
    r = _upload(stage, 0, PDF, token=token)
    assert r.status_code == 404, r.text
    assert not stage["dir"].exists(), "받지 않을 파일을 디스크에 적었다"


def test_an_account_served_by_this_agent_is_offered_too(db, stage):
    """`○○ 발송기로` 맡긴 계정의 메일 건 — 그 발송기가 제 폴더에서 올린다."""
    from app.models import User

    job = _job(db, stage)                   # (`_job` 은 안 적힌 변경을 버린다 — 먼저 집는다)
    u2 = db.get(User, 2)
    u2.send_via_user_id = 1
    u2.can_auto_attach_ir = 1
    job.user_id = 2
    db.commit()

    assert [u["id"] for u in _beat(stage["client"], mail_files=True)["mail_uploads"]] \
        == [stage["item_id"]]
    assert _upload(stage, 0, PDF).status_code == 200


# ── 3. 올리는 문 ─────────────────────────────────────────────────────────────

def test_upload_needs_the_device_token(stage):
    r = stage["client"].post(f"/api/agent/items/{stage['item_id']}/mail-files/0",
                             content=PDF)
    assert r.status_code == 401
    r = _upload(stage, 0, PDF, token="agt_wrong_token")
    assert r.status_code == 401
    assert not stage["dir"].exists()


@pytest.mark.parametrize("index", ["2", "-1", "99", "..%2F..%2Fdealflow.db", "0.part",
                                   "%2e%2e"])
def test_only_the_files_listed_on_the_item_are_accepted(stage, data_dir, index):
    """이름이 아니라 **몇 번째 파일인가**만 받는다 — 경로가 될 글자가 들어올 자리가 없다."""
    before = sorted(p.name for p in data_dir.rglob("*"))

    r = _upload(stage, index, PDF)

    assert r.status_code in (404, 422), r.text
    assert sorted(p.name for p in data_dir.rglob("*")) == before, "문 밖에 무언가 적혔다"


def test_an_unknown_item_answers_like_someone_elses(stage):
    assert _upload(stage, 0, PDF, item_id=987654).status_code == 404


def test_files_are_kept_under_server_made_names(db, stage):
    """적어 둔 이름(한글 · 공백)은 디스크에 안 쓴다 — 차례 번호가 곧 이름이다."""
    assert _upload(stage, 0, PDF).json() == {"ok": True, "size": len(PDF)}
    assert _upload(stage, 1, PPT).status_code == 200

    assert sorted(p.name for p in stage["dir"].iterdir()) == ["0", "1"]
    assert (stage["dir"] / "0").read_bytes() == PDF
    assert (stage["dir"] / "1").read_bytes() == PPT


def test_uploading_the_same_file_again_replaces_it(db, stage):
    _upload(stage, 0, b"first try")
    assert _upload(stage, 0, PDF).status_code == 200

    assert (stage["dir"] / "0").read_bytes() == PDF
    assert sorted(p.name for p in stage["dir"].iterdir()) == ["0"]


def test_nothing_more_is_taken_once_all_files_are_in(db, stage):
    """다 올라온 건은 메일 쪽이 읽는 중일 수 있다 — 바꿔 놓지 않는다."""
    _upload(stage, 0, PDF)
    _upload(stage, 1, PPT)

    assert _upload(stage, 0, b"late").status_code == 404
    assert (stage["dir"] / "0").read_bytes() == PDF
    assert _beat(stage["client"], mail_files=True)["mail_uploads"] == []


def test_an_empty_body_is_refused_and_the_item_keeps_waiting(db, stage):
    r = _upload(stage, 0, b"")

    assert r.status_code == 400
    assert _item(db, stage).status == "pending"
    assert not (stage["dir"] / "0").exists()


def test_uploaded_files_are_not_served_back(stage):
    _upload(stage, 0, PDF)

    for url in (f"/api/agent/items/{stage['item_id']}/mail-files/0",
                f"/mail_attachments/{stage['item_id']}/0",
                f"/static/mail_attachments/{stage['item_id']}/0"):
        r = stage["client"].get(url, headers=auth(DEMO_TOKEN), follow_redirects=False)
        assert r.status_code != 200 or PDF not in r.content, url


# ── 4. 다 올라오면 붙여 보내고 지운다 ────────────────────────────────────────

def test_the_mail_goes_out_with_the_files_once_they_arrive(db, stage, outbox, monkeypatch):
    from app.services import mail_sender, pipeline

    closed = []
    monkeypatch.setattr(pipeline, "close_requests_for",
                        lambda db, job, contact_id: closed.append(contact_id))
    mail_sender._run(db, stage["job_id"], gap_sec=0)         # 대기로 선다
    _upload(stage, 0, PDF)
    assert mail_sender.resume_waiting(db) == [], "파일 하나만 온 건을 보내려 했다"
    _upload(stage, 1, PPT)

    assert mail_sender.resume_waiting(db) == [stage["job_id"]]

    assert len(outbox) == 1
    msg = outbox[0]
    assert msg["To"] == "hong@example.com"
    assert msg["Subject"] == "IR 자료 전달드립니다"
    assert "자료 전달드립니다" in msg.get_body(preferencelist=("plain",)).get_content()
    parts = list(msg.iter_attachments())
    assert [p.get_filename() for p in parts] == FILES, "한글 파일 이름이 깨졌다"
    assert [p.get_content() for p in parts] == [PDF, PPT]
    assert parts[0].get_content_type() == "application/pdf"
    assert parts[1].get_content_type().endswith("presentation")
    # 실제로 나가는 글자에는 RFC 2231 로 실린다 — 받는 쪽이 다시 읽어도 같은 이름.
    from email import message_from_bytes, policy
    again = message_from_bytes(msg.as_bytes(), policy=policy.default)
    assert [p.get_filename() for p in again.iter_attachments()] == FILES

    item = _item(db, stage)
    assert (item.status, item.error) == ("sent", None)
    assert _job(db, stage).status == "done"
    assert not stage["dir"].exists(), "보낸 뒤에도 자료 파일을 들고 있다"
    assert closed == [item.contact_id], "자료가 나갔는데 그 요청이 `전달함` 으로 안 닫혔다"
    assert mail_sender.resume_waiting(db) == [], "한 번 나간 메일이 또 나가려 한다"
    assert len(outbox) == 1


def test_a_mail_with_files_waits_longer_for_the_server(db, stage, outbox):
    """수십 MB 를 받고 답하는 데 20초를 넘길 수 있다 — 그때 끊으면 나간 메일이 실패로
    적혀 재시도에 한 번 더 나간다. 붙은 것이 없는 메일은 지금까지와 똑같이 붙는다."""
    from app.services import mail_sender, mailer

    _upload(stage, 0, PDF)
    _upload(stage, 1, PPT)
    mail_sender._run(db, stage["job_id"], gap_sec=0)
    assert outbox.timeouts == [mailer.ATTACH_TIMEOUT_SEC]
    assert mailer.ATTACH_TIMEOUT_SEC >= 120

    mailer.send_mail("hong@example.com", "제목", "본문", settings=mailer.load_settings())
    assert outbox.timeouts[-1] is None, "붙은 것이 없는 메일의 붙는 길이 바뀌었다"


def test_the_plain_smtp_timeout_is_unchanged(mail_on, monkeypatch):
    import smtplib

    from app.services import mailer

    seen = []
    monkeypatch.setattr(smtplib, "SMTP_SSL",
                        lambda host, port, timeout, context: seen.append(timeout))
    mailer._connect(mailer.load_settings())
    mailer._connect(mailer.load_settings(), mailer.ATTACH_TIMEOUT_SEC)

    assert seen == [20, 180]


def test_a_company_blocked_while_waiting_is_not_mailed(db, stage, outbox):
    """파일을 기다리는 사이 실린 기업이 `딜소개 불가` 가 됐다 — 카톡이 내주기 직전에
    보는 것과 같은 판정(`jobs._drop_blocked_companies`)으로 그 건을 취소한다."""
    from app.models import DealBatch, DealBatchCompany, IrCompany
    from app.services import mail_sender

    company = IrCompany(name="샘플애그", ir_file_name=FILES[0])
    batch = DealBatch(user_id=1, title="IR 자료 전달", sent_date="2099-03-12",
                      cycle_type="adhoc")
    db.add_all([company, batch])
    db.flush()
    db.add(DealBatchCompany(batch_id=batch.id, company_id=company.id, position=1))
    job = _job(db, stage)
    job.batch_id = batch.id
    db.commit()
    mail_sender._run(db, stage["job_id"], gap_sec=0)
    assert _item(db, stage).status == "pending", "막히지 않은 기업의 건을 취소했다"
    _upload(stage, 0, PDF)
    _upload(stage, 1, PPT)

    company = db.get(IrCompany, company.id)
    company.name = "샘플애그 [딜소개 불가]"
    db.commit()
    assert mail_sender.resume_waiting(db) == [stage["job_id"]]

    assert outbox == [], "딜소개 불가 기업의 자료가 메일로 나갔다"
    item = _item(db, stage)
    assert item.status == "canceled" and "딜소개 불가" in item.error
    assert _job(db, stage).status == "canceled"
    assert not stage["dir"].exists()


def test_a_file_name_typed_in_split_jamo_goes_out_composed(db, stage, outbox):
    """맥에서 복사해 적은 이름(NFD)은 윈도우 메일함에서 자모가 흩어져 보인다."""
    import unicodedata

    from app.services import mail_sender

    item = _item(db, stage)
    item.files_json = json.dumps([unicodedata.normalize("NFD", FILES[0])],
                                 ensure_ascii=False)
    db.commit()
    _upload(stage, 0, PDF)
    mail_sender._run(db, stage["job_id"], gap_sec=0)

    assert [p.get_filename() for p in outbox[0].iter_attachments()] == [FILES[0]]


@pytest.mark.send_window
def test_files_arriving_at_night_wait_for_the_window(db, stage, outbox, monkeypatch):
    """보내는 시간(09~19시)은 그대로다 — 밤에 올라온 파일은 아침에 나간다."""
    from app import clock
    from app.services import mail_sender

    monkeypatch.delenv("DEALFLOW_TEST_SERVER_NO_SEND_WINDOW", raising=False)
    now = {"t": datetime(2099, 3, 12, 22, 0).astimezone()}
    monkeypatch.setattr(clock, "now", lambda: now["t"])
    mail_sender._run(db, stage["job_id"], gap_sec=0)
    assert _item(db, stage).error == mail_sender.mail_attach.WAIT, \
        "파일을 기다리는 건에 `시간이 되면 나갑니다` 가 섰다"
    _upload(stage, 0, PDF)
    _upload(stage, 1, PPT)

    assert mail_sender.resume_waiting(db, now["t"]) == []
    mail_sender._run(db, stage["job_id"], gap_sec=0)
    assert outbox == []
    assert _item(db, stage).error == mail_sender.HELD_WINDOW
    assert stage["dir"].exists(), "기다리는 건의 파일을 지웠다"

    now["t"] = datetime(2099, 3, 13, 9, 0).astimezone()
    assert mail_sender.resume_waiting(db, now["t"]) == [stage["job_id"]]
    assert len(outbox) == 1 and _item(db, stage).status == "sent"


def test_a_failed_mail_also_lets_go_of_the_files(db, stage, outbox):
    """실패도 끝난 건이다. [실패 재시도] 를 누르면 다시 대기 → 다시 올라온다."""
    import smtplib

    from app.services import mail_attach, mail_sender

    def refuse(self, msg):
        raise smtplib.SMTPRecipientsRefused({"hong@example.com": (550, b"no such user")})

    outbox.smtp.send_message = refuse
    _upload(stage, 0, PDF)
    _upload(stage, 1, PPT)
    mail_sender._run(db, stage["job_id"], gap_sec=0)

    item = _item(db, stage)
    assert item.status == "failed" and "주소" in item.error
    assert not stage["dir"].exists()

    job = _job(db, stage)
    item = _item(db, stage)
    item.status, item.error, job.status = "pending", None, "queued"    # [실패 재시도]
    db.commit()
    mail_sender._run(db, stage["job_id"], gap_sec=0)
    assert _item(db, stage).error == mail_attach.WAIT
    assert [u["id"] for u in _beat(stage["client"], mail_files=True)["mail_uploads"]] \
        == [stage["item_id"]]


def test_leftovers_are_swept(db, stage, data_dir):
    """[중단]된 건 · 사라진 건의 폴더는 예약 실이 치운다. 모르는 이름은 안 건드린다."""
    from app.services import mail_sender

    _upload(stage, 0, PDF)
    base = data_dir / "mail_attachments"
    (base / "999999").mkdir()                    # 없는 건
    (base / "999999" / "0").write_bytes(b"x")
    (base / "keep-me").mkdir()                   # 건 번호가 아닌 이름
    mail_sender.resume_waiting(db)
    assert stage["dir"].exists(), "대기 중인 건의 파일을 지웠다"
    assert not (base / "999999").exists()
    assert (base / "keep-me").exists()

    stage["client"].post("/login", data={"phone": "01000000001",
                                         "password": "dealflow123"})
    assert stage["client"].post(f"/api/jobs/{stage['job_id']}/cancel").status_code == 200
    mail_sender.resume_waiting(db)
    assert not stage["dir"].exists(), "[중단]한 건의 파일이 남았다"


def test_a_waiting_items_files_are_never_swept_for_being_old(db, stage):
    """기다리는 건은 며칠이고 설 수 있다 — 묵었다고 지우면 다 올라온 자료가 사라진다.
    묵어서 지우는 것은 보내다 굳은 건(`sending`)과 받다 만 조각뿐이다."""
    import os
    import time

    from app.services import mail_attach

    _upload(stage, 0, PDF)
    half = stage["dir"] / "1.abc123.part"                 # 받다 끊긴 조각
    half.write_bytes(b"half")
    old = time.time() - (mail_attach.STALE_DAYS + 1) * 86400
    for path in (half, stage["dir"]):
        os.utime(path, (old, old))

    _item(db, stage)                # 세션에 줄을 올려 둔다 — 치우기는 그래도 새로 읽는다
    mail_attach.sweep(db)
    assert (stage["dir"] / "0").read_bytes() == PDF, "기다리는 건의 파일을 지웠다"
    assert not half.exists(), "받다 만 조각이 남았다"

    item = _item(db, stage)
    item.status = "sending"
    db.commit()
    os.utime(stage["dir"], None)
    mail_attach.sweep(db)
    assert stage["dir"].exists(), "지금 보내는 중인 건의 파일을 지웠다"
    os.utime(stage["dir"], (old, old))
    mail_attach.sweep(db)
    assert not stage["dir"].exists(), "보내다 굳은 건의 파일이 끝없이 남는다"


# ── 5. 용량 ──────────────────────────────────────────────────────────────────

def test_over_the_limit_fails_the_item_with_a_reason(db, stage, monkeypatch):
    """서버가 흘려 받으며 센다 — 발송기의 미리 재기는 편의일 뿐이다."""
    monkeypatch.setenv("DEALFLOW_MAIL_ATTACH_MAX_MB", "0.001")        # 1048 바이트

    assert _upload(stage, 0, b"a" * 600).status_code == 200
    r = _upload(stage, 1, b"b" * 600)                                 # 합계가 넘는다

    assert r.status_code == 413
    item = _item(db, stage)
    assert item.status == "failed"
    assert "첨부 용량 초과" in item.error
    job = _job(db, stage)
    assert (job.status, job.failed) == ("done_with_errors", 1)
    assert not stage["dir"].exists()


def test_an_endless_body_is_cut_at_the_limit(data_dir, monkeypatch):
    """본문을 다 받고 재지 않는다 — 상한을 넘는 조각에서 멈추고 받던 것을 지운다."""
    import asyncio

    from app.services import mail_attach

    monkeypatch.setenv("DEALFLOW_MAIL_ATTACH_MAX_MB", "0.001")
    taken = []

    async def endless():
        while True:
            taken.append(1)
            yield b"x" * 512

    with pytest.raises(mail_attach.TooBig):
        asyncio.run(mail_attach.save(5, 0, endless()))

    assert len(taken) == 3, "상한(1048 바이트)을 넘고도 계속 읽었다"
    assert list((data_dir / "mail_attachments" / "5").iterdir()) == []


def _interleaved(*bodies, check=None):
    """조각을 번갈아 내주는 본문들 — 두 올리기가 겹쳐 도는 모양을 만든다."""
    import asyncio

    def body(data):
        async def chunks():
            for at in range(0, len(data), 100):
                yield data[at:at + 100]
                if check:
                    check()
                await asyncio.sleep(0)          # 다른 올리기에게 차례를 넘긴다
        return chunks()

    return [body(data) for data in bodies]


def test_two_uploads_of_the_same_file_do_not_corrupt_each_other(data_dir):
    """같은 토큰의 발송기 창 둘이 같은 파일을 함께 올려도 — 조각이 요청마다 따로라
    제자리에 서는 것은 늘 **온전한 한 벌**이다. 섞인 파일이 "다 올라왔다" 가 되면
    깨진 자료가 메일로 나간다."""
    import asyncio

    from app.services import mail_attach

    one, two = b"A" * 950, b"B" * 1400
    final = data_dir / "mail_attachments" / "5" / "0"
    seen = []

    def check():
        if final.exists():
            seen.append(final.read_bytes())

    async def both():
        a, b = _interleaved(one, two, check=check)
        return await asyncio.gather(mail_attach.save(5, 0, a), mail_attach.save(5, 0, b))

    assert asyncio.run(both()) == [len(one), len(two)]

    assert seen, "겹쳐 도는 동안 제자리를 한 번도 못 봤다 — 검사가 겹치지 않았다"
    assert set(seen) <= {one, two}, "받다 만 · 섞인 파일이 제자리에 섰다"
    assert final.read_bytes() == two, "나중에 끝난 올리기가 통째로 남아야 한다"
    assert [p.name for p in final.parent.iterdir()] == ["0"], "조각이 남았다"


def test_parallel_uploads_cannot_pass_the_limit_together(data_dir, monkeypatch):
    """둘 다 시작할 때는 상한 안이다 — 옮기기 직전에 합계를 다시 봐야 함께 못 넘는다."""
    import asyncio

    from app.services import mail_attach

    monkeypatch.setenv("DEALFLOW_MAIL_ATTACH_MAX_MB", "0.001")        # 1048 바이트

    async def both():
        a, b = _interleaved(b"a" * 600, b"b" * 600)
        return await asyncio.gather(mail_attach.save(5, 0, a), mail_attach.save(5, 1, b),
                                    return_exceptions=True)

    done = asyncio.run(both())

    assert sum(isinstance(r, mail_attach.TooBig) for r in done) == 1, done
    assert mail_attach.total(5) == 600
    assert [p.name for p in (data_dir / "mail_attachments" / "5").iterdir()] in (["0"], ["1"])


def test_the_second_parallel_upload_over_the_limit_fails_the_item(db, stage, monkeypatch):
    """서버 길로 — 둘째가 거절되고(413) 그 건은 실패로 닫힌다. 메일은 안 나간다."""
    monkeypatch.setenv("DEALFLOW_MAIL_ATTACH_MAX_MB", "0.001")
    from app.services import mail_attach

    real = mail_attach.save

    async def save_with_a_rival(item_id, index, chunks):
        # 이 올리기가 도는 사이 다른 창이 나머지 파일을 먼저 끝낸다.
        folder = stage["dir"]
        folder.mkdir(parents=True, exist_ok=True)

        async def racing():
            async for chunk in chunks:
                yield chunk
            (folder / "0").write_bytes(b"a" * 600)

        return await real(item_id, index, racing())

    monkeypatch.setattr(mail_attach, "save", save_with_a_rival)
    r = _upload(stage, 1, b"b" * 600)

    assert r.status_code == 413
    item = _item(db, stage)
    assert item.status == "failed" and "첨부 용량 초과" in item.error
    assert not stage["dir"].exists()


def test_a_mail_over_the_limit_is_never_sent(db, stage, outbox, monkeypatch):
    """보내기 직전에도 한 번 더 본다 — 어떤 길로든 상한을 넘은 건은 실패다."""
    from app.services import mail_sender

    _upload(stage, 0, b"a" * 600)
    _upload(stage, 1, b"b" * 600)
    monkeypatch.setenv("DEALFLOW_MAIL_ATTACH_MAX_MB", "0.001")
    mail_sender._run(db, stage["job_id"], gap_sec=0)

    assert outbox == []
    item = _item(db, stage)
    assert item.status == "failed" and "첨부 용량 초과" in item.error
    assert _job(db, stage).status == "done_with_errors"
    assert not stage["dir"].exists()


def test_cancel_during_an_over_limit_upload_stays_canceled(db, stage, monkeypatch):
    """올라오는 동안 [중단]된 건을 `실패` 로 덮어쓰지 않는다 — 회차도 `중단` 그대로."""
    from app.db import SessionLocal
    from app.models import SendItem, SendJob
    from app.services import mail_attach

    async def canceled_meanwhile(item_id, index, chunks):
        other = SessionLocal()                  # 화면의 [중단] — 다른 요청이다
        try:
            other.get(SendItem, item_id).status = "canceled"
            other.get(SendJob, stage["job_id"]).status = "canceled"
            other.commit()
        finally:
            other.close()
        raise mail_attach.TooBig(mail_attach.too_big_note())

    monkeypatch.setattr(mail_attach, "save", canceled_meanwhile)
    r = _upload(stage, 0, PDF)

    assert r.status_code == 413
    item = _item(db, stage)
    assert (item.status, item.error) == ("canceled", None)
    job = _job(db, stage)
    assert (job.status, job.failed) == ("canceled", 0)


def test_the_limit_comes_from_the_environment(monkeypatch):
    from app.services import mail_attach

    assert mail_attach.max_bytes() == 18 * 1024 * 1024
    monkeypatch.setenv("DEALFLOW_MAIL_ATTACH_MAX_MB", "5")
    assert mail_attach.max_bytes() == 5 * 1024 * 1024
    for bad in ("많이", "0", "-3"):
        monkeypatch.setenv("DEALFLOW_MAIL_ATTACH_MAX_MB", bad)
        assert mail_attach.max_bytes() == 18 * 1024 * 1024


def test_a_mail_bigger_than_the_smtp_server_takes_is_not_tried(db, stage, outbox):
    """메일 서버가 EHLO 에서 받는 크기(`SIZE`)를 밝혔으면 넘는 메일은 보내 보지 않는다."""
    from app.services import mail_sender

    outbox.smtp.esmtp_features = {"size": "40"}
    _upload(stage, 0, PDF)
    _upload(stage, 1, PPT)
    mail_sender._run(db, stage["job_id"], gap_sec=0)

    assert outbox == []
    item = _item(db, stage)
    assert item.status == "failed" and "첨부 용량 초과" in item.error
    assert not stage["dir"].exists()


# ── 발송기가 못 올리겠다고 알리면 ────────────────────────────────────────────

def test_the_agent_reporting_a_missing_file_fails_the_item(db, stage):
    _upload(stage, 0, PDF)
    why = "자료 파일을 올리지 못해 메일을 보내지 않았습니다 — 이 PC 에 파일이 없습니다"

    r = stage["client"].post(f"/api/agent/items/{stage['item_id']}/result",
                             json={"status": "failed", "error": why},
                             headers=auth(DEMO_TOKEN))

    assert r.status_code == 200
    item = _item(db, stage)
    assert (item.status, item.error) == ("failed", why)
    assert _job(db, stage).status == "done_with_errors", "회차가 큐에 선 채로 남았다"
    assert not stage["dir"].exists()


@pytest.mark.parametrize("case", ["no_files", "all_files_in"])
def test_the_agent_can_only_fail_a_mail_that_still_waits_for_files(db, stage, case):
    """그 문은 "붙일 파일을 못 올렸다" 를 위한 것이다 — 파일이 없는 여느 메일, 다 올라와
    곧 나갈 메일을 발송기가 실패로 닫을 수는 없다."""
    if case == "no_files":
        _item(db, stage).files_json = None
        db.commit()
    else:
        _upload(stage, 0, PDF)
        _upload(stage, 1, PPT)

    r = stage["client"].post(f"/api/agent/items/{stage['item_id']}/result",
                             json={"status": "failed", "error": "그냥"},
                             headers=auth(DEMO_TOKEN))

    assert r.status_code == 409
    item = _item(db, stage)
    assert (item.status, item.error) == ("pending", None)
    assert _job(db, stage).status == "queued"


def test_the_agent_cannot_mark_a_mail_as_sent(db, stage):
    """메일은 서버가 보낸다 — 발송기의 '보냄' 을 받아 적으면 안 나간 메일이 보낸 것이 된다."""
    r = stage["client"].post(f"/api/agent/items/{stage['item_id']}/result",
                             json={"status": "sent"}, headers=auth(DEMO_TOKEN))

    assert r.status_code == 409
    assert _item(db, stage).status == "pending"


# ── 6. 발송기 쪽 ─────────────────────────────────────────────────────────────

@pytest.fixture()
def agent_main():
    return importlib.import_module("agent.main")


class FakeClient:
    """올린 것 · 실패로 알린 것을 적어 두는 가짜 서버 통로."""

    def __init__(self, status=200):
        self.uploads, self.failed, self.status = [], [], status

    def upload_mail_file(self, item_id, index, path):
        self.uploads.append((item_id, index, Path(path).read_bytes()))
        return type("R", (), {"status_code": self.status, "text": "refused"})()

    def report_item(self, item_id, status, error=None, **more):
        self.failed.append((item_id, status, error))


@pytest.fixture()
def ir_folder(tmp_path):
    folder = tmp_path / "IR자료"
    folder.mkdir()
    (folder / FILES[0]).write_bytes(PDF)
    (folder / FILES[1]).write_bytes(PPT)
    (tmp_path / "secret.txt").write_text("폴더 밖")
    return folder


def _payload(folder, files=FILES, limit=18 * 1024 * 1024):
    return {"ir_root": str(folder), "mail_max_bytes": limit,
            "mail_uploads": [{"id": 7, "files": list(files)}]}


def test_agent_uploads_each_file_in_order(agent_main, ir_folder):
    client = FakeClient()

    assert agent_main.upload_mail_files(client, _payload(ir_folder)) == 1

    assert client.uploads == [(7, 0, PDF), (7, 1, PPT)]
    assert client.failed == []


def test_agent_reports_a_missing_file_and_uploads_nothing(agent_main, ir_folder):
    """하나라도 없으면 **한 개도 올리지 않는다** — 반쪽 자료로 메일이 나가면 안 된다."""
    client = FakeClient()

    done = agent_main.upload_mail_files(
        client, _payload(ir_folder, [FILES[0], "없는파일.pdf"]))

    assert done == 0 and client.uploads == []
    (item_id, status, error), = client.failed
    assert (item_id, status) == (7, "failed")
    assert "메일을 보내지 않았습니다" in error and "없는파일.pdf" in error


def test_agent_fails_early_when_the_files_are_too_large(agent_main, ir_folder):
    client = FakeClient()

    agent_main.upload_mail_files(client, _payload(ir_folder, limit=10))

    assert client.uploads == [], "넘을 줄 알면서 올렸다"
    assert "첨부 용량 초과" in client.failed[0][2]


@pytest.mark.parametrize("name", ["../secret.txt", "/etc/hosts", ".hidden", ""])
def test_agent_keeps_the_same_bolts_as_the_kakao_attach(agent_main, ir_folder, name):
    """파일을 찾는 규칙은 카톡 첨부와 한 벌이다(`resolve_ir_file`) — 폴더 밖은 안 나간다."""
    client = FakeClient()

    agent_main.upload_mail_files(client, _payload(ir_folder, [name]))

    assert client.uploads == []
    assert client.failed and client.failed[0][1] == "failed"


def test_agent_without_a_folder_fails_the_item_clearly(agent_main, ir_folder):
    client = FakeClient()

    agent_main.upload_mail_files(client, {**_payload(ir_folder), "ir_root": ""})

    assert client.uploads == []
    assert "IR 자료 폴더가 정해지지 않았습니다" in client.failed[0][2]


def test_agent_moves_on_when_the_server_refuses(agent_main, ir_folder):
    """그 사이 [중단]됐다 등 — 실패로 알리지 않고(서버가 이미 안다) 다음 건으로."""
    client = FakeClient(status=404)
    payload = _payload(ir_folder)
    payload["mail_uploads"].append({"id": 8, "files": [FILES[1]]})

    assert agent_main.upload_mail_files(client, payload) == 0
    assert [(i, n) for i, n, _ in client.uploads] == [(7, 0), (8, 0)]
    assert client.failed == []


def _two_items(folder):
    payload = _payload(folder, [FILES[0]])
    payload["mail_uploads"].append({"id": 8, "files": [FILES[1]]})
    return payload


def test_agent_network_trouble_on_one_item_does_not_stop_the_next(agent_main, ir_folder):
    """통신이 끊긴 건은 실패로 알리지 않는다(다음 박동에 다시) — 뒤의 건은 그대로 올린다.
    맨 앞 건이 늘 탈이 나도 뒤의 건이 굶지 않는다."""
    import requests

    class Flaky(FakeClient):
        def upload_mail_file(self, item_id, index, path):
            if item_id == 7:
                raise requests.ConnectionError("connection reset")
            return super().upload_mail_file(item_id, index, path)

    client = Flaky()

    assert agent_main.upload_mail_files(client, _two_items(ir_folder)) == 1
    assert client.uploads == [(8, 0, PPT)]
    assert client.failed == [], "통신 문제를 그 건의 실패로 닫았다"


def test_agent_reports_a_file_it_cannot_open(agent_main, ir_folder):
    """Windows 에서 다른 프로그램이 잠가 둔 파일 — 그 건만 까닭과 함께 실패, 다음 건은 간다."""
    class Locked(FakeClient):
        def upload_mail_file(self, item_id, index, path):
            if item_id == 7:
                raise PermissionError(13, "Permission denied", str(path))
            return super().upload_mail_file(item_id, index, path)

    client = Locked()

    assert agent_main.upload_mail_files(client, _two_items(ir_folder)) == 1
    assert client.uploads == [(8, 0, PPT)]
    (item_id, status, error), = client.failed
    assert (item_id, status) == (7, "failed")
    assert "메일을 보내지 않았습니다" in error and "파일을 읽지 못했습니다" in error
    assert FILES[0] in error


def test_agent_upload_trouble_never_reaches_the_main_loop(agent_main, ir_folder):
    """무슨 탈이 나도 던지지 않는다 — 여기서 새면 카톡 발송 고리가 그 바퀴를 건너뛴다."""
    import requests

    class Broken(FakeClient):
        def upload_mail_file(self, item_id, index, path):
            raise RuntimeError("뜻밖의 탈")

        def report_item(self, item_id, status, error=None, **more):
            raise requests.Timeout("실패 보고도 못 닿는다")

    payload = _two_items(ir_folder)
    payload["mail_uploads"] += ["엉뚱한 값", {"id": 9}, {"id": 10, "files": ["없는파일.pdf"]}]
    payload["mail_max_bytes"] = "많이"

    assert agent_main.upload_mail_files(Broken(), payload) == 0
    assert agent_main.upload_mail_files(FakeClient(), {"mail_uploads": "목록이 아님"}) == 0


def test_agent_ignores_a_reply_without_uploads(agent_main):
    """낡은 서버 · 못 읽은 응답 — 아무 일도 없다."""
    client = FakeClient()

    assert agent_main.upload_mail_files(client, None) == 0
    assert agent_main.upload_mail_files(client, {"ok": True, "ir_root": ""}) == 0
    assert client.uploads == [] and client.failed == []


def test_agent_says_it_can_upload_on_the_heartbeat(agent_main):
    client = agent_main.AgentClient({"server_url": "http://server.example", "token": "t"})
    seen = {}
    client.session = type("S", (), {"post": lambda self, url, **kw: seen.update(kw)})()

    client.heartbeat()

    assert seen["json"]["mail_files"] is True


def test_agent_to_server_end_to_end(agent_main, db, stage, outbox, ir_folder):
    """진짜 발송기 코드가 진짜 서버 길을 지난다 — 박동 → 올리기 → 메일."""
    from app.services import mail_sender

    web = stage["client"]

    class Bridge:
        """`requests.Session` 자리에 검사용 서버를 끼운다."""

        def post(self, url, json=None, data=None, headers=None, timeout=None):
            path = url.replace("http://server.example", "")
            headers = {**auth(DEMO_TOKEN), **(headers or {})}
            if data is not None:
                return web.post(path, content=data.read(), headers=headers)
            return web.post(path, json=json, headers=headers)

    client = agent_main.AgentClient({"server_url": "http://server.example",
                                     "token": DEMO_TOKEN})
    client.session = Bridge()
    mail_sender._run(db, stage["job_id"], gap_sec=0)

    reply = client.heartbeat().json()
    reply["ir_root"] = str(ir_folder)          # 서버에 적힌 경로는 이 PC 에 없다
    assert agent_main.upload_mail_files(client, reply) == 1
    assert mail_sender.resume_waiting(db) == [stage["job_id"]]

    assert [p.get_content() for p in outbox[0].iter_attachments()] == [PDF, PPT]
    assert _item(db, stage).status == "sent"
