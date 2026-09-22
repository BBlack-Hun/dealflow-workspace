"""시험방은 **`/setup` 의 시험 단추만** 쓴다 — 일반 발송은 제 갈 곳으로.

## 무엇이 잘못돼 있었나

`config.TEST_ROOM` 에 값이 있으면 `routers/deals.py: create_send_list` 가
**여기를 지나는 모든 발송**의 방 이름을 그 한 방으로 바꿔 치웠다. 딜 소개도
IR 전달도 미팅 요청도 리마인드도 소싱도 스타트업 월간도 전부.

그 장치의 전제는 "운영에는 시험방이 없다" 였다. 전제가 깨지는 날 —
시험 한 번 하려고 운영 `.env` 에 방 제목을 넣어 둔 날 — **딜 소개가
투자사 대신 그 방으로 갔다.** 투자사는 아무것도 못 받았고 화면에는 '보냄'
으로 찍혔으니, 며칠 뒤 "연락이 없네" 로나 알게 된다.

## 무엇으로 갈랐나

**잡 종류**다(`models.TEST_SEND_KIND`). 시험 발송은 만드는 자리부터 다르고
(`routers/setup.py: _queue_test_job`), 그 자리만 시험방을 읽는다. 일반 발송을
만드는 `create_send_list` 는 시험방을 **아예 읽지 않는다.**

## 이 검사가 못박는 것

1. **갈래마다 한 줄씩** — 시험방이 켜져 있어도 딜 소개·IR 전달·미팅 요청·
   리마인드·선호 분야 묻기·미팅 후기·소싱·스타트업 월간이 **각자의 방**으로
   간다. 한 갈래만 확인하면 나머지 일곱이 조용히 샌다.
2. **문구에 손대지 않는다** — `[테스트 발송 → …]` 머리말도, 메일 제목의
   `[테스트]` 접두도 붙지 않는다. 붙으면 그대로 투자사가 읽는다.
3. **반대 방향** — `/setup` 의 시험 발송이 진짜 투자사에게 가지 않는다.
   이쪽이 훨씬 나쁘다: 지어낸 보기 자료가 실제 담당자 방에 꽂힌다.
4. **되살아나지 못하게** — `create_send_list` 가 있는 파일에서 시험방을
   읽는 자리가 다시 생기면 여기서 걸린다.

이름·회사명·방 제목은 **전부 지어낸 값**이다 — 저장소가 공개다.
"""
from __future__ import annotations

import json

import pytest

from .conftest import DEMO_PASSWORD

#: 검사용 시험방 제목. 실제 값은 `.env` 로 들어오고 저장소에는 올리지 않는다.
TEST_ROOM = "나와의 채팅"

#: 실제 담당자의 방. **이 값이 나와야 한다** — 시험방이 아니라.
ROOM = "홍길동 심사역님 가나벤처스"
SOURCING_ROOM = "김철수 소싱방"
STARTUP_ROOM = "샘플애그 대표님"

#: 시험방으로 돌릴 때 붙던 머리말. 이제 어느 갈래에도 없어야 한다.
OLD_BANNER = "테스트 발송"


@pytest.fixture()
def test_room_on(monkeypatch):
    """시험방 ON — **운영이 지금 이 상태다.** 여기서부터가 이 검사의 전제다.

    `config` 하나만 바꾼다. 예전에는 `deals.config` 도 따로 바꿔야 했는데,
    그쪽이 시험방을 안 읽게 됐으므로 바꿀 자리 자체가 없다.
    """
    from app import config

    monkeypatch.setattr(config, "TEST_ROOM", TEST_ROOM)
    return TEST_ROOM


@pytest.fixture()
def stage(client, db, users, monkeypatch):
    """보낼 수 있는 상태 하나 — 카톡 담당자·메일 담당자·소싱 명단·계약 기업."""
    from app.models import (ContactActivity, IrCompany, IrRequest,
                            MessageTemplate, SheetOwner, SourcingContact,
                            VcContact)
    from app.services import mail_sender, startup_send

    # 메일은 서버가 바로 보낸다 — 검사에서 실제로 나가지 않게 막는다.
    monkeypatch.setattr(mail_sender, "send_job", lambda *a, **k: None)

    u1 = users["u1"]
    db.add_all([
        SheetOwner(label="내 명단", user_id=u1.id),
        MessageTemplate(user_id=None, kind="opening_first",
                        body="안녕하세요, {담당자명} {직함}", is_active=1),
        MessageTemplate(user_id=None, kind="closing_day1",
                        body="핵심 딜 {개수}개사 공유드립니다.", is_active=1),
        IrCompany(name="샘플애그", one_liner="B2B 농산물 선도거래",
                  revenue_recent=12, sector_major="애그테크",
                  contract_status="paid", kakao_room_name=STARTUP_ROOM),
    ])
    contact = VcContact(
        user_id=u1.id, name="홍길동", title="심사역", firm="가나벤처스",
        source_sheet="내 명단", channel_kakao=1, kakao_room_name=ROOM,
        room_verified="verified", connect_stage="connected")
    mailed = VcContact(
        user_id=u1.id, name="메일받는분", title="심사역", firm="다라캐피탈",
        source_sheet="내 명단", channel_kakao=0, channel_email=1,
        email="deal@example.com", connect_stage="connected")
    sourcing = SourcingContact(bucket="딜 소싱  개인참여 심사역", position=1,
                               name="김철수", title="심사역", firm="마바벤처스",
                               kakao_room_name=SOURCING_ROOM)
    db.add_all([contact, mailed, sourcing])
    db.flush()

    # 스타트업 월간 발송이 실을 줄 하나 — 이 달에 자료를 요청한 투자사.
    company = db.query(IrCompany).filter_by(name="샘플애그").one()
    db.add(IrRequest(user_id=u1.id, contact_id=contact.id, company_id=company.id,
                     company_name=company.name, requested_at=_day(_month(), 3)))
    db.add(ContactActivity(contact_id=contact.id, kind="ir_request",
                           content="IR 요청", happened_at=_day(_month(), 3),
                           company_names=json.dumps(["샘플애그"],
                                                    ensure_ascii=False)))
    # 스타트업 월간 발송은 **정해진 계정만** 쓴다 — 켜 두지 않으면 404 다.
    startup_send.save(db, enabled=True, user_id=u1.id)
    db.commit()

    client.post("/login", data={"phone": "01000000001",
                                "password": DEMO_PASSWORD})
    return {
        "client": client,
        "user": u1,
        "contact_id": contact.id,
        "mailed_id": mailed.id,
        "sourcing_id": sourcing.id,
        "company_id": company.id,
        "month": _month(),
    }


def _month() -> str:
    from app import clock

    today = clock.today()
    return f"{today.year:04d}-{today.month:02d}"


def _day(month: str, day: int) -> str:
    return f"{month}-{day:02d}"


def _send(stage, **body):
    r = stage["client"].post("/api/deals/send", json=body)
    assert r.status_code == 200, r.text
    return r.json()["job_id"]


def _items(db, job_id):
    from app.models import SendItem

    return db.query(SendItem).filter_by(job_id=job_id).order_by(SendItem.id).all()


def _sole(db, job_id):
    items = _items(db, job_id)
    assert len(items) == 1, f"건이 {len(items)}개다"
    return items[0]


# ══════════════════════════════════════════════════════════════════════════
#  ① 갈래마다 — 시험방이 켜져 있어도 **제 갈 곳으로** 간다
# ══════════════════════════════════════════════════════════════════════════
#
# 한 갈래만 보면 나머지가 조용히 샌다. 실제로 시험방 치환은 갈래를 가리지
# 않았으므로, 푸는 쪽도 갈래를 가리지 않고 확인해야 한다.

#: 담당자 한 명에게 보내는 여덟 갈래 중 **기업이 필요 없는** 것들.
#: (`deal` · `ir` 는 기업을 고르므로 따로 본다. `sourcing` · `startup` 은
#:  받는 표가 달라 또 따로 본다.)
CONTACT_MODES = ["remind", "meeting", "ask", "review"]


@pytest.mark.parametrize("mode", CONTACT_MODES)
def test_후속_문구가_담당자_방으로_간다(stage, db, test_room_on, mode):
    """리마인드·미팅 요청·선호 분야 묻기·미팅 후기 — 넷 다 담당자 방이다."""
    job_id = _send(stage, contact_ids=[stage["contact_id"]], mode=mode)

    item = _sole(db, job_id)
    assert item.room_name == ROOM, f"'{mode}' 가 시험방으로 샜다"
    assert item.room_name != TEST_ROOM
    assert OLD_BANNER not in item.message, f"'{mode}' 문구에 시험 머리말이 붙었다"


def test_딜_소개가_담당자_방으로_간다(stage, db, test_room_on):
    """★ 이 한 줄이 이번 사고 그 자체다 — 딜 소개가 투자사에게 가야 한다."""
    job_id = _send(stage, contact_ids=[stage["contact_id"]],
                   company_ids=[stage["company_id"]], title="검사 회차")

    item = _sole(db, job_id)
    assert item.room_name == ROOM
    assert OLD_BANNER not in item.message
    # 문구는 시험방이 꺼져 있을 때와 **글자 하나까지 같아야 한다.**
    assert item.message.startswith("안녕하세요, 홍길동 심사역")


def test_IR_자료_전달이_담당자_방으로_간다(stage, db, test_room_on):
    job_id = _send(stage, contact_ids=[stage["contact_id"]],
                   company_ids=[stage["company_id"]], mode="ir")

    item = _sole(db, job_id)
    assert item.room_name == ROOM
    assert OLD_BANNER not in item.message


def test_소싱_제안이_소싱_명단의_방으로_간다(stage, db, test_room_on):
    """소싱은 받는 표가 다르다(`SourcingContact`) — 그래서 따로 본다."""
    job_id = _send(stage, contact_ids=[stage["sourcing_id"]], mode="sourcing")

    item = _sole(db, job_id)
    assert item.room_name == SOURCING_ROOM
    assert item.sourcing_contact_id == stage["sourcing_id"]
    assert OLD_BANNER not in item.message


def test_스타트업_월간_발송이_대표_방으로_간다(stage, db, test_room_on):
    """받는 쪽이 투자사가 아니라 **기업 대표**다 — 여기도 시험방이 아니다.

    이 갈래는 담당자 줄에 직함도 투자사도 없다(`IrCompany`). 예전 치환 코드가
    바로 그 자리에서 터졌던 적이 있어, 갈래로 가른 지금도 한 번 더 본다.
    """
    job_id = _send(stage, contact_ids=[stage["company_id"]], mode="startup",
                   month=stage["month"])

    item = _sole(db, job_id)
    assert item.room_name == STARTUP_ROOM
    assert item.ir_company_id == stage["company_id"]
    assert OLD_BANNER not in item.message


def test_나눠_보내는_통에도_머리말이_안_붙는다(stage, db, test_room_on):
    """글이 여러 통으로 나뉘면 첫 통에만 머리말을 얹던 자리가 있었다.

    통이 하나든 여럿이든 이제 얹을 것이 없다 — `parts_json` 을 통째로 본다.
    """
    job_id = _send(stage, contact_ids=[stage["company_id"]], mode="startup",
                   month=stage["month"])

    item = _sole(db, job_id)
    parts = json.loads(item.parts_json) if item.parts_json else [item.message]
    assert parts, "나눠 보낼 차례가 비었다"
    assert not any(OLD_BANNER in part for part in parts)


def test_시험방을_꺼도_결과가_같다(stage, db):
    """★ 시험방이 결과를 바꾸지 않는다는 것이 이 변경의 전부다.

    켠 채로 보낸 것과 끈 채로 보낸 것이 **방도 문구도 같아야** 한다. 앞의
    검사들은 "시험방이 아니다" 만 보므로, 값이 문구를 슬쩍 바꾸는 경우를
    못 잡는다.
    """
    from app import config

    off = _sole(db, _send(stage, contact_ids=[stage["contact_id"]],
                          company_ids=[stage["company_id"]], title="검사 회차"))
    room_off, message_off = off.room_name, off.message

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(config, "TEST_ROOM", TEST_ROOM)
        on = _sole(db, _send(stage, contact_ids=[stage["contact_id"]],
                             company_ids=[stage["company_id"]],
                             title="검사 회차"))
        assert on.room_name == room_off
        assert on.message == message_off


# ══════════════════════════════════════════════════════════════════════════
#  ② 메일 — 제목에 `[테스트]` 가 붙지 않는다
# ══════════════════════════════════════════════════════════════════════════
#
# 메일은 주소가 곧 대상이라 방을 모을 수가 없었다. 그래서 "카톡만 시험방으로
# 가고 메일은 진짜로 간다" 는 차이를 제목으로나마 알리자고 `[테스트]` 를
# 붙였다. 이제 카톡도 제 갈 곳으로 가므로 알릴 차이가 없다 — 남겨 두면
# **투자사 메일함 제목 줄에 `[테스트]` 가 그대로 꽂힌다.**

@pytest.fixture()
def mail_on(monkeypatch):
    monkeypatch.setenv("DEALFLOW_SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("DEALFLOW_SMTP_PORT", "465")
    monkeypatch.setenv("DEALFLOW_SMTP_USER", "deal@example.com")
    monkeypatch.setenv("DEALFLOW_SMTP_FROM", "deal@example.com")
    monkeypatch.setenv("DEALFLOW_SMTP_PASSWORD", "secret")


def test_메일_제목에_테스트_접두가_안_붙는다(stage, db, mail_on, test_room_on):
    job_id = _send(stage, contact_ids=[stage["mailed_id"]],
                   company_ids=[stage["company_id"]], channel="email",
                   subject="9월 딜 소개")

    item = _sole(db, job_id)
    assert item.subject == "9월 딜 소개", "제목에 시험 표시가 남았다"
    assert "[테스트]" not in item.subject
    assert item.room_name == "deal@example.com"


def test_메일_제목의_치환은_그대로다(stage, db, mail_on, test_room_on):
    """접두만 뗐지 치환을 건드린 것이 아니다 — 함께 지워지지 않았는지 본다."""
    job_id = _send(stage, contact_ids=[stage["mailed_id"]],
                   company_ids=[stage["company_id"]], channel="email",
                   subject="{투자사} 딜 소개")

    assert _sole(db, job_id).subject == "다라캐피탈 딜 소개"


# ══════════════════════════════════════════════════════════════════════════
#  ③ ★ 반대 방향 — 시험 발송이 **진짜 투자사에게 가면 훨씬 나쁘다**
# ══════════════════════════════════════════════════════════════════════════
#
# 일반 발송이 시험방으로 새면 아무도 못 받는다. 시험 발송이 실방으로 새면
# 투자사가 `[보기 자료] … 보기기업` 을 읽는다 — 되돌릴 수가 없다.

def test_시험_발송은_시험방으로만_간다(logged_in, db, test_room_on, users):
    """`/setup` 의 시험 단추가 만든 잡. 방 이름을 사람이 고를 수 없다."""
    from app.models import TEST_SEND_KIND

    users["u1"].can_auto_attach_ir = 1
    db.commit()

    r = logged_in.post("/setup/test/attach", data={"file_name": "회사소개서.pdf"},
                       follow_redirects=False)
    assert r.status_code in (302, 303), r.status_code
    job_id = int(r.headers["location"].rsplit("/", 1)[1])

    from app.models import SendJob
    job = db.get(SendJob, job_id)
    assert job.kind == TEST_SEND_KIND
    item = _sole(db, job_id)
    assert item.room_name == TEST_ROOM, "시험 발송이 시험방 밖으로 나갔다"


def test_방_이름을_밀어_넣어도_시험방으로만_간다(logged_in, db, test_room_on, users):
    """옆칸(방 이름 시험)의 값을 이쪽으로 실어 보내는 시도가 자연스럽다."""
    users["u1"].can_auto_attach_ir = 1
    db.commit()

    r = logged_in.post("/setup/test/attach",
                       data={"file_name": "회사소개서.pdf", "room_name": ROOM},
                       follow_redirects=False)
    job_id = int(r.headers["location"].rsplit("/", 1)[1])
    assert _sole(db, job_id).room_name == TEST_ROOM


def test_시험_잡을_세우는_자리가_방_이름을_다시_본다(db, users, test_room_on):
    """★ 부르는 쪽 넷 중 하나가 언젠가 다른 방을 넘긴다 — 그때 터져야 한다.

    조용히 고쳐서 보내면 부르는 쪽의 실수가 묻히고, 그 실수는 다음 갈래에서
    다시 나온다. 막을 자리가 없을 수도 있는 다음번을 위해 여기서 세운다.
    """
    from app.models import SendJob, TEST_SEND_KIND
    from app.routers import setup as setup_router

    with pytest.raises(RuntimeError):
        setup_router._queue_test_job(db, users["u1"], TEST_SEND_KIND,
                                     ROOM, "문구", [])
    db.rollback()
    assert db.query(SendJob).count() == 0, "막았는데 잡이 남았다"


def test_방_이름_시험은_이_막이에_걸리지_않는다(logged_in, db, test_room_on):
    """방 이름 시험은 **아무것도 보내지 않는다**(`verify_room`).

    그쪽은 사람이 적은 방 제목을 그대로 들고 가야 검색이 되는지 볼 수 있다 —
    시험방으로 바꿔 버리면 시험 자체가 성립하지 않는다. 막이가 잡 종류를
    보고 서는 까닭이 그것이다.
    """
    r = logged_in.post("/setup/test/room", data={"room_name": "아무개 방"},
                       follow_redirects=False)
    assert r.status_code in (302, 303), r.text
    job_id = int(r.headers["location"].rsplit("/", 1)[1])
    assert _sole(db, job_id).room_name == "아무개 방"


# ══════════════════════════════════════════════════════════════════════════
#  ④ 되살아나지 못하게
# ══════════════════════════════════════════════════════════════════════════

def test_일반_발송_파일은_시험방을_읽지_않는다():
    """★ 치환이 되살아나면 여기서 걸린다.

    위 검사들은 **지금 만들어지는 건**을 본다. 누군가 "시험 모드면 …" 한 줄을
    다시 넣되 검사가 안 지나는 갈래에만 넣으면 전부 통과한다 — 실제로 그
    장치는 여덟 갈래를 한 자리에서 가로채고 있었다. 그래서 자리 자체를 본다.

    주석은 센다. 왜 읽지 않는지가 그 파일에 적혀 있어야 하고, 적힌 줄까지
    금지하면 다음 사람이 까닭을 모른 채 되돌린다.
    """
    import inspect

    from app.routers import deals

    source = inspect.getsource(deals)
    code = "\n".join(line for line in source.splitlines()
                     if not line.lstrip().startswith("#"))
    assert "TEST_ROOM" not in code, (
        "일반 발송 길에 시험방을 읽는 자리가 다시 생겼다 — "
        "시험방으로 가는 것은 `/setup` 의 시험 발송뿐이다")


def test_시험_종류는_발송_실적에_안_섞인다():
    """가르는 값이 커진 만큼, 그 값이 집계에 새지 않는지 다시 본다."""
    from app.models import SEND_KINDS, STARTUP_SEND_KIND, TEST_SEND_KIND

    assert TEST_SEND_KIND not in SEND_KINDS
    assert STARTUP_SEND_KIND not in SEND_KINDS
    assert TEST_SEND_KIND != STARTUP_SEND_KIND


# ══════════════════════════════════════════════════════════════════════════
#  ⑤ 화면이 무엇을 말하나
# ══════════════════════════════════════════════════════════════════════════
#
# 띠가 옛말을 하면 사람은 나간 것을 안 나간 줄로 읽는다 — 그 반대도.

def test_모든_화면이_시험방을_알린다(stage, test_room_on):
    """`/setup` 에만 적혀 있으면 발송을 누르는 사람은 모른 채 누른다."""
    for path in ("/deals", "/followups", "/ir", "/contacts", "/setup"):
        html = stage["client"].get(path).text
        assert TEST_ROOM in html, f"{path} 에 시험방 표시가 없다"
        assert "시험방이 켜져 있습니다" in html, path


def test_띠가_일반_발송은_제_갈_곳으로_간다고_적는다(stage, test_room_on):
    """★ 예전 띠는 '모든 발송이 그 방으로만' 이라고 적었다 — 지금은 거짓말이다."""
    html = stage["client"].get("/deals").text

    assert "각 담당자 방으로 그대로 나갑니다" in html
    assert "모든 발송이" not in html


def test_시험방이_꺼져_있으면_띠도_없다(stage):
    html = stage["client"].get("/deals").text
    assert "시험방이 켜져 있습니다" not in html
