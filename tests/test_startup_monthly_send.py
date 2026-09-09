"""스타트업 월간 발송 — **정해진 한 계정만, 그리고 누르기 전에는 안 나간다.**

달마다 한 번, 그 달 말까지 「IR 자료를 요청한 투자사 목록」(가려서)을 그 기업
대표 카톡방으로 보낸다. 지금까지는 스타트업 화면이 글을 지어 주면 사람이
[문구 복사] 로 퍼 날랐다 — 보내는 자리가 딜 제안 관리로 왔다.

## 여기서 못박는 것 다섯

1. **지정된 계정이 아니면 메뉴도 경로도 막힌다.** 안 보이는 것만으로는 부족하다 —
   주소로 곧장 찔러도 없는 자리여야 한다.
2. **설정이 켜져 있어도 사람이 [발송 시작] 을 누르기 전에는 발송기 폴링이
   아무것도 못 가져간다.** 잘못 담긴 것을 나가기 전에 볼 수 있는 자리가 그
   한 번이다.
3. **방 이름이 빈 기업은 조용히 빠지지 않고 화면에 드러난다.** 매달 같은 기업만
   소리 없이 빠지면 아무도 그 사실을 모른다.
4. **글을 짓는 자리는 `ir_kakao` 하나다.** 화면이 보여 준 글과 대표가 받는 글이
   글자 하나까지 같아야 한다.
5. **가리기는 `ir_mask` 를 지난다.** 원래 투자사명이 나가는 글 어디에도 없다.

## 진짜로는 한 통도 안 나간다

이 검사는 **발송 목록까지만** 만든다. 실제로 카톡을 보내는 것은 각 PC 의 발송
프로그램이고, 검사는 그것을 띄우지 않는다.

이름·회사명은 **전부 지어낸 값**이다 — 저장소가 공개다.
**날짜를 박지 않는다** — 달은 `clock` 에서 만든다.
"""
from __future__ import annotations

import json

import pytest

from tests.conftest import DEMO_PASSWORD, DEMO_TOKEN, OTHER_TOKEN

# 전부 지어낸 이름이다.
FIRM = "가나벤처스"
FIRM_OLD = "다라인베스트먼트"
PERSON = "홍길동"
COMPANY_OK = "샘플에이"        # 방 이름이 있고 실을 줄도 있다
COMPANY_NOROOM = "샘플비"      # **방 이름이 없다** — 이 줄이 이 검사의 알맹이다
COMPANY_EMPTY = "샘플씨"       # 방은 있는데 그 달까지 요청이 한 곳도 없다

ROOM_OK = f"{COMPANY_OK} 대표님"
ROOM_EMPTY = f"{COMPANY_EMPTY} 대표님"

#: 발송 프로그램이 폴링할 때 밝히는 종류. `agent/main.py: SUPPORTED_KINDS` 와
#: 같아야 한다 — 여기 없으면 서버가 잡을 안 내주고, 그러면 이 검사는 "안
#: 나간다" 를 **틀린 이유로** 통과한다.
AGENT_KINDS = "deal_intro,ir_delivery,sourcing_intro,verify_room,test_send,startup_ir"


def _month(offset: int = 0) -> str:
    from app import clock

    today = clock.today()
    total = today.year * 12 + (today.month - 1) + offset
    return f"{total // 12:04d}-{total % 12 + 1:02d}"


def _day(month: str, day: int) -> str:
    return f"{month}-{day:02d}"


@pytest.fixture()
def seeded(db, users):
    """계약 기업 셋 — 보낼 수 있는 곳 하나, 방 없는 곳 하나, 요청 없는 곳 하나."""
    from app.models import ContactActivity, IrCompany, IrRequest, VcContact

    ok = IrCompany(name=COMPANY_OK, contract_status="paid",
                   kakao_room_name=ROOM_OK)
    # **방 이름을 비운 채로 둔다.** 이것이 지금까지 발송을 막고 있던 그 빈칸이다.
    noroom = IrCompany(name=COMPANY_NOROOM, contract_status="free")
    empty = IrCompany(name=COMPANY_EMPTY, contract_status="free",
                      kakao_room_name=ROOM_EMPTY)
    db.add_all([ok, noroom, empty])

    now_contact = VcContact(user_id=1, name=PERSON, firm=FIRM)
    old_contact = VcContact(user_id=1, name=PERSON, firm=FIRM_OLD)
    db.add_all([now_contact, old_contact])
    db.flush()

    now, last = _month(), _month(-1)
    # 이번 달 — 이 앱에서 누른 것(외래키가 있다).
    db.add(IrRequest(user_id=1, contact_id=now_contact.id, company_id=ok.id,
                     company_name=COMPANY_OK, requested_at=_day(now, 3)))
    # **지난 달** — 누적이라 이번 달 글에 함께 실린다.
    db.add(ContactActivity(contact_id=old_contact.id, kind="ir_request",
                           content="IR 요청", happened_at=_day(last, 22),
                           company_names=json.dumps([COMPANY_OK, COMPANY_NOROOM],
                                                    ensure_ascii=False)))
    db.commit()
    return {"ok": ok, "noroom": noroom, "empty": empty, "month": now}


def _turn_on(db, user_id: int = 1):
    """그 계정에만 이 메뉴를 연다. **이름을 코드에 적지 않는다** — 설정값이다."""
    from app.services import startup_send

    return startup_send.save(db, enabled=True, user_id=user_id)


def _login(client, phone="01000000001"):
    client.post("/login", data={"phone": phone, "password": DEMO_PASSWORD})
    return client


def _make_draft(client, seeded, ids=None, month=None):
    """[대기 목록 만들기] — 화면의 폼이 보내는 것과 같은 값이다."""
    return client.post("/deals/startup-ir/send", follow_redirects=False, data={
        "month": month or seeded["month"],
        "company_ids": ids if ids is not None else [seeded["ok"].id],
        "title": "검사 회차",
    })


def _poll(client, token=DEMO_TOKEN):
    """발송 프로그램이 지금 집어갈 것이 있는지 물어본다. 없으면 204 다."""
    return client.get("/api/agent/poll", params={"kinds": AGENT_KINDS},
                      headers={"Authorization": f"Bearer {token}"})


def _jobs(db):
    from sqlalchemy import select

    from app.models import SendJob

    return db.execute(select(SendJob).order_by(SendJob.id)).scalars().all()


# ── 1. 지정된 계정이 아니면 메뉴도 경로도 막힌다  ★ ─────────────────────────

def test_꺼져_있으면_아무에게도_안_보인다(db, seeded, logged_in):
    """설정 줄이 아예 없는 것이 **기본이자 꺼짐**이다. 메일·문자와 같다."""
    assert "/deals/startup-ir" not in logged_in.get("/deals").text
    assert logged_in.get("/deals/startup-ir").status_code == 404


def test_지정된_계정에만_메뉴가_보인다(db, seeded, client):
    _turn_on(db, user_id=1)

    mine = _login(client).get("/deals")
    assert "/deals/startup-ir" in mine.text
    assert client.get("/deals/startup-ir").status_code == 200


def test_다른_팀원에게는_메뉴도_경로도_없다(db, seeded, client):
    """**안 보이는 것만으로는 부족하다.** 주소로 곧장 찔러도 없는 자리여야 한다.

    403 이 아니라 404 다 — 403 은 "그런 자리가 있는데 너는 안 된다" 라서
    이 계정으로 쓸 수 없는 기능의 존재를 알려 준다.
    """
    _turn_on(db, user_id=1)
    other = _login(client, phone="01000000002")

    assert "/deals/startup-ir" not in other.get("/deals").text
    assert other.get("/deals/startup-ir").status_code == 404
    # 보내는 자리도 같은 판정을 지난다.
    assert _make_draft(other, seeded).status_code == 404
    # 발송 목록을 만드는 API 를 직접 찔러도 마찬가지다.
    assert other.post("/api/deals/send", json={
        "contact_ids": [seeded["ok"].id], "mode": "startup",
        "month": seeded["month"], "draft": True,
    }).status_code == 404
    assert not _jobs(db)


def test_관리자도_예외가_아니다(db, users, seeded, client):
    """권한의 높낮이가 아니라 **어느 PC 의 카톡에서 나가는가**이기 때문이다.

    관리자를 통과시키면 그 사람 것으로 회차가 서고, 그 계정에 붙은 발송기가
    없으면 **아무도 집어가지 않는 회차**가 된다.
    """
    users["u2"].role = "admin"
    db.commit()
    _turn_on(db, user_id=1)

    boss = _login(client, phone="01000000002")
    assert boss.get("/deals/startup-ir").status_code == 404


def test_계정을_바꾸면_따라_옮겨간다(db, seeded, client):
    """실명을 코드에 적지 않았으므로, 담당이 바뀌어도 배포가 필요 없다."""
    _turn_on(db, user_id=2)

    assert _login(client).get("/deals/startup-ir").status_code == 404
    client.post("/logout")
    assert _login(client, phone="01000000002").get(
        "/deals/startup-ir").status_code == 200


# ── 2. 누르기 전에는 한 통도 안 나간다  ★ ───────────────────────────────────

def test_대기_목록만_서고_발송기는_집어가지_못한다(db, seeded, client):
    """이 검사가 이 기능의 알맹이다.

    회차는 `draft` 로 서고, 발송 프로그램은 `queued` 인 회차만 집어간다
    (`routers/agent_api.py: poll`).
    """
    _turn_on(db, user_id=1)
    made = _make_draft(_login(client), seeded)

    assert made.status_code == 303
    job = _jobs(db)[0]
    assert job.status == "draft"
    assert made.headers["location"] == f"/jobs/{job.id}"
    # 발송기가 물어봐도 줄 것이 없다.
    assert _poll(client).status_code == 204
    assert {i.status for i in job.items} == {"pending"}


def test_누르면_그때_나간다(db, seeded, client):
    _turn_on(db, user_id=1)
    _make_draft(_login(client), seeded)
    job = _jobs(db)[0]

    assert client.post(f"/api/jobs/{job.id}/start").status_code == 200
    db.expire_all()
    assert _jobs(db)[0].status == "queued"

    claimed = _poll(client)
    assert claimed.status_code == 200
    assert claimed.json()["job_id"] == job.id
    assert claimed.json()["kind"] == "startup_ir"


def test_남의_기기는_집어가지_못한다(db, seeded, client):
    """회차는 **그 계정 것**으로 서고, 그 계정의 기기 토큰으로만 내려간다."""
    _turn_on(db, user_id=1)
    _make_draft(_login(client), seeded)
    client.post(f"/api/jobs/{_jobs(db)[0].id}/start")

    assert _poll(client, token=OTHER_TOKEN).status_code == 204


def test_누르기_전에_몇_곳_어느_방인지_보인다(db, seeded, client):
    """발송은 되돌릴 수 없으므로 **누른 뒤에 숫자를 아는 것은 늦다.**"""
    _turn_on(db, user_id=1)
    body = _login(client).get("/deals/startup-ir").text

    assert ROOM_OK in body, "어느 방으로 가는지가 화면에 없다"
    assert "1곳 대기 목록 만들기" in body, "몇 곳인지가 단추에 없다"


# ── 3. 방 이름이 빈 기업은 조용히 빠지지 않는다  ★ ──────────────────────────

def test_방_이름이_없는_기업이_화면에_드러난다(db, seeded, client):
    """빼 버리면 계약 기업인데 왜 안 보이는지 물을 자리가 없어진다."""
    from app.services import startup_send

    _turn_on(db, user_id=1)
    body = _login(client).get("/deals/startup-ir").text

    assert COMPANY_NOROOM in body, "방 없는 기업이 목록에서 사라졌다"
    assert startup_send.NO_ROOM in body, "왜 못 보내는지가 안 적혀 있다"
    # 고를 수는 없다 — 체크박스가 서지 않는다.
    assert f'name="company_ids" value="{seeded["noroom"].id}"' not in body


def test_방_이름이_없으면_주소로_밀어_넣어도_안_된다(db, seeded, client):
    """화면이 거른 것과 라우터가 거르는 것이 갈리면, 화면에서 못 고르는 줄이
    주소로는 들어간다."""
    _turn_on(db, user_id=1)
    back = _make_draft(_login(client), seeded,
                       ids=[seeded["ok"].id, seeded["noroom"].id])

    assert back.status_code == 303
    assert "/deals/startup-ir" in back.headers["location"]
    # **한 곳도 안 섰다.** 나머지만 조용히 보내면 몇 곳에 나갔는지 아무도 모른다.
    assert not _jobs(db)


def test_방_이름을_채우면_그_기업도_보낼_수_있다(db, seeded, client):
    """빈 칸은 '보내지 말라' 가 아니라 **아직 안 적었다**는 뜻이다."""
    seeded["noroom"].kakao_room_name = f"{COMPANY_NOROOM} 대표님"
    db.commit()
    _turn_on(db, user_id=1)

    body = _login(client).get("/deals/startup-ir").text
    assert f'name="company_ids" value="{seeded["noroom"].id}"' in body
    assert _make_draft(client, seeded,
                       ids=[seeded["ok"].id, seeded["noroom"].id]).status_code == 303
    assert _jobs(db)[0].total == 2


def test_그_달에_요청이_없는_기업도_목록에_남는다(db, seeded, client):
    """방은 멀쩡한데 실을 줄이 없는 것은 **다른 사실**이다 — 까닭이 갈려야
    무엇을 해야 할지 알 수 있다. 빈 목록을 보내면 대표는 우리가 아무것도 안 한
    줄로 읽는다."""
    from app.services import startup_send

    _turn_on(db, user_id=1)
    body = _login(client).get("/deals/startup-ir").text

    assert COMPANY_EMPTY in body
    assert startup_send.NO_LINES in body
    assert f'name="company_ids" value="{seeded["empty"].id}"' not in body


def test_방_칸을_기업_현황에서_채운다(db, seeded, logged_in):
    """**채우는 자리가 있어야 한다.** 칸만 만들고 넣을 자리가 없으면 그 기업은
    영영 못 보낸다."""
    company_id = seeded["noroom"].id
    room = f"{COMPANY_NOROOM} 대표님"

    assert "f-kakao_room_name" in logged_in.get("/companies").text
    assert logged_in.patch(f"/api/companies/{company_id}",
                           json={"kakao_room_name": f"  {room}  "}).status_code == 200
    db.expire_all()
    # 앞뒤 공백은 떨어진다 — 발송기는 제목이 **글자까지** 같아야 방을 찾는다.
    assert db.get(type(seeded["noroom"]), company_id).kakao_room_name == room
    assert logged_in.get(f"/api/companies/{company_id}").json()[
        "kakao_room_name"] == room


# ── 4. 글을 짓는 자리는 `ir_kakao` 하나다  ★ ────────────────────────────────

def test_나가는_글이_화면이_보여_준_글과_같다(db, seeded, client):
    """두 벌로 지으면 사람이 보고 고른 글과 대표가 받는 글이 갈리고, 그 차이는
    나간 뒤에야 드러난다."""
    from app.services import ir_kakao

    _turn_on(db, user_id=1)
    user = _login(client)
    _make_draft(user, seeded)

    item = _jobs(db)[0].items[0]
    from app.models import User

    composed = ir_kakao.for_company(db, db.get(User, 1), seeded["ok"].id,
                                    seeded["month"])
    assert item.message == composed.text
    assert item.room_name == ROOM_OK


def test_발송이_제_손으로_글을_짓지_않는다():
    """`routers/deals.py` 안에 이 글의 문장이 한 조각도 없어야 한다."""
    import pathlib

    from app.services import ir_kakao

    root = pathlib.Path(__file__).resolve().parent.parent
    src = (root / "app" / "routers" / "deals.py").read_text(encoding="utf-8")
    for piece in (ir_kakao.HELLO, ir_kakao.LEAD, ir_kakao.COMPANIES_TOKEN):
        assert piece not in src, f"발송 자리가 글을 짓고 있다: {piece}"
    assert "ir_kakao.for_company" in src, "짓는 자리를 지나지 않는다"


def test_받는_줄은_기업이다(db, seeded, client):
    """투자사도 소싱 명단도 아니다 — 셋 중 하나만 찬다."""
    _turn_on(db, user_id=1)
    _make_draft(_login(client), seeded)

    item = _jobs(db)[0].items[0]
    assert item.ir_company_id == seeded["ok"].id
    assert item.contact_id is None and item.sourcing_contact_id is None
    # 진행 화면이 부르는 이름도 기업 이름이다.
    assert item.recipient_name == COMPANY_OK


def test_딜소개_실적에_섞이지_않는다(db, seeded, client):
    """받는 쪽이 투자사가 아니다. 섞이면 팀원의 딜소개 실적이 부푼다."""
    from app.models import SEND_KINDS

    _turn_on(db, user_id=1)
    _make_draft(_login(client), seeded)

    assert _jobs(db)[0].kind not in SEND_KINDS


def test_미리보기로는_들어갈_수_없다(db, seeded, client):
    """딜소개 미리보기 길로 들여보내면 기업 id 를 투자사 담당자 id 로 알고
    **실제로 나갈 글과 아무 상관 없는** 문구를 지어 내놓는다."""
    _turn_on(db, user_id=1)
    answer = _login(client).post("/api/deals/preview", json={
        "contact_ids": [seeded["ok"].id], "mode": "startup"})

    assert answer.status_code == 400


# ── 5. 가리기는 `ir_mask` 를 지난다  ★ ──────────────────────────────────────

def test_나가는_글에_투자사_원래_이름이_없다(db, seeded, client):
    """가리기는 안 하는 것보다 어설프게 하는 쪽이 나쁘다."""
    from app.services import ir_mask

    _turn_on(db, user_id=1)
    _make_draft(_login(client), seeded)
    message = _jobs(db)[0].items[0].message

    for firm in (FIRM, FIRM_OLD):
        assert firm not in message, f"원래 이름이 그대로 나간다: {firm}"
        assert firm[1:] not in message, "뒷부분이 새고 있다"
        assert ir_mask.mask_company(firm) in message
    # 담당자 이름은 아예 안 실린다.
    assert PERSON not in message


def test_가리기를_발송_자리가_직접_하지_않는다():
    """별표를 만드는 자리는 `ir_mask` 하나다 — 두 곳에 적히면 한쪽이 낡고,
    **낡은 쪽이 이름을 그대로 내보낸다.**"""
    import pathlib

    from app.services import ir_mask

    root = pathlib.Path(__file__).resolve().parent.parent
    for name in ("app/routers/deals.py", "app/routers/startup_send.py",
                 "app/services/startup_send.py"):
        src = (root / name).read_text(encoding="utf-8")
        assert ir_mask.STARS not in src, f"{name} 이 별표를 직접 만든다"


# ── 달을 짐작하지 않는다 ────────────────────────────────────────────────────

def test_달이_없으면_이번_달로_대신_보내지_않는다(db, seeded, client):
    """글에 `7월 말까지` 라고 적혀 나가는 자리라, 짐작이 틀리면 그 거짓말이
    그대로 대표에게 간다."""
    _turn_on(db, user_id=1)
    back = _make_draft(_login(client), seeded, month="이상한값")

    assert back.status_code == 303
    assert not _jobs(db)


def test_고른_달이_그대로_실린다(db, seeded, client):
    """화면에서 지난 달을 보고 눌렀는데 이번 달치가 나가면 안 된다."""
    from app.services import ir_kakao
    from app.models import User

    _turn_on(db, user_id=1)
    last = _month(-1)
    _make_draft(_login(client), seeded, month=last)

    composed = ir_kakao.for_company(db, db.get(User, 1), seeded["ok"].id, last)
    assert _jobs(db)[0].items[0].message == composed.text
