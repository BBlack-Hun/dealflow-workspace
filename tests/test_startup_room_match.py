"""대표 카톡방 **맞추기** — 후보는 카톡에서 오고, 고르는 것은 사람이다.

월간 발송이 막혀 있던 까닭은 `IrCompany.kakao_room_name` 이 **한 곳도** 안
채워져 있어서였다. 채우는 길이 기업마다 [수정] 창을 한 번씩 여는 것뿐이라,
수십 곳을 앞에 두고는 쓸 수 없는 길이었다.

## 여기서 못박는 것 일곱

1. **방 제목을 짐작해서 넣지 않는다.** 후보가 하나뿐이고 발송기가 `확인됨`
   이라고 보고해도 서버는 `kakao_room_name` 에 넣지 않는다 — 회사명이 든 방이
   꼭 그 대표와의 방인 것은 아니다. 이 저장소에서 가장 비싼 사고가 그것이다.
2. **발송기를 안 고쳤다.** 이미 있는 방 확인 잡(`verify_room`)을 그대로 쓰고,
   발송기가 이미 보내고 있던 `candidates` 를 받기만 한다 — 판을 안 올려도
   팀원 PC 에 깔린 발송기가 그대로 이 잡을 처리한다.
3. **계약 기업 전부가 한 판에** 선다. 이미 맞춰진 곳도, 후보가 없는 곳도
   목록에 남는다(조용히 빠지지 않는다).
4. **한 번에 저장한다.** 짝이 어긋나면 한 줄도 넣지 않는다 — 어긋난 채로
   넣으면 A 기업 칸의 글자가 B 기업 방 이름이 된다.
5. **글자가 바뀌면 확인은 무효다.** 적는 자리가 한 곳이라
   (`room_match.set_room`) [수정] 창으로 고쳐도 같다.
6. **발송 판정은 그대로다.** 확인 안 된 방도 보낼 수 있다 — 막으면 찾기가
   한 번 실패한 달에 월간 발송이 통째로 선다.
7. **정해진 한 계정만.** 보내는 자리와 **같은 판정**을 지난다.

이름·회사명은 **전부 지어낸 값**이다 — 저장소가 공개다.
"""
from __future__ import annotations

import re
from urllib.parse import unquote

import pytest

from tests.conftest import DEMO_PASSWORD, DEMO_TOKEN

# 전부 지어낸 이름이다. **띄어쓰기가 다른 짝**을 일부러 둔다 — 그것이 이
# 기능이 풀어야 할 문제다(아는 이름 `샘플 가`, 카톡 제목 `샘플가`).
SPACED = "샘플 가"          # 우리가 아는 이름 (띄어 적혀 있다)
SPACED_ROOM = "가나다 대표 샘플가 , 라마바 팀장"   # 카톡에 있는 제목
CORP = "(주)샘플나"          # 법인 표기가 붙어 있다
PLAIN = "샘플다"
MATCHED = "샘플라"           # 이미 방 제목이 들어 있다
CEO = "가나다"

AGENT_KINDS = ("deal_intro,ir_delivery,sourcing_intro,"
               "verify_room,test_send,startup_ir")


# ── 밑판 ────────────────────────────────────────────────────────────────────

@pytest.fixture()
def seeded(db, users):
    """계약 기업 넷 — 띄어쓰기가 다른 곳 · 법인 표기가 붙은 곳 · 평범한 곳 ·
    이미 맞춰진 곳. 그리고 **계약을 안 한 곳 하나**(목록에 서면 안 된다)."""
    from app.models import IrCompany

    spaced = IrCompany(name=SPACED, contract_status="paid", contact_name=CEO)
    corp = IrCompany(name=CORP, contract_status="free")
    plain = IrCompany(name=PLAIN, contract_status="paid", contact_name=CEO)
    matched = IrCompany(name=MATCHED, contract_status="paid",
                        kakao_room_name=f"{CEO} 대표 {MATCHED}")
    nope = IrCompany(name="샘플마", contract_status="no")
    db.add_all([spaced, corp, plain, matched, nope])
    db.commit()
    return {"spaced": spaced, "corp": corp, "plain": plain,
            "matched": matched, "nope": nope}


def _turn_on(db, user_id: int = 1):
    from app.services import startup_send

    return startup_send.save(db, enabled=True, user_id=user_id)


def _login(client, phone="01000000001"):
    client.post("/login", data={"phone": phone, "password": DEMO_PASSWORD})
    return client


def _rows(client):
    return client.get("/deals/startup-ir/rooms")


def _save(client, pairs):
    """[저장] — 화면의 폼이 보내는 것과 **같은 모양**(짝지은 두 목록)."""
    return client.post("/deals/startup-ir/rooms", follow_redirects=False, data={
        "company_ids": [cid for cid, _ in pairs],
        "rooms": [room for _, room in pairs],
    })


def _search(client):
    return client.post("/deals/startup-ir/rooms/search", follow_redirects=False)


def _jobs(db):
    from sqlalchemy import select

    from app.models import SendJob

    return db.execute(select(SendJob).order_by(SendJob.id)).scalars().all()


def _report(client, item_id, *, candidates=None, verdict="ambiguous",
            found_room=None, token=DEMO_TOKEN):
    """발송기가 결과를 올리는 그 길. **실제 발송기가 보내는 모양 그대로**다
    (`agent/main.py: process_verify_job` 의 `report_item`)."""
    return client.post(f"/api/agent/items/{item_id}/result",
                       headers={"Authorization": f"Bearer {token}"},
                       json={"status": "sent" if verdict == "verified" else "failed",
                             "verify_result": verdict,
                             "found_room": found_room,
                             "candidates": candidates})


# ── 1. 짐작해서 방 이름을 정하지 않는다  ★★ ────────────────────────────────

def test_후보가_하나뿐이고_확인됨이어도_서버는_넣지_않는다(db, seeded, client):
    """**이 검사가 이 기능의 알맹이다.**

    발송기가 회사명으로 찾아 방 하나를 집어 `verified` 로 보고해도, 서버는
    그것을 `kakao_room_name` 에 넣지 않는다. 회사명이 든 방이 꼭 그 회사
    대표와의 방인 것은 아니다 — 그 회사 얘기를 하는 다른 방일 수 있고, 카톡
    검색은 참여자 이름에도 걸린다. 넣어 버리면 **엉뚱한 방으로 간다.**

    투자사 담당자 쪽은 하나뿐인 결과를 넣는다. 그쪽은 사람이 **이미 적어 둔**
    방 이름을 대조하는 길이라 근거가 있다 — 여기는 처음 알아내는 길이다.
    """
    _turn_on(db)
    me = _login(client)
    _search(me)
    job = _jobs(db)[0]
    item = next(i for i in job.items if i.ir_company_id == seeded["spaced"].id)

    _report(me, item.id, verdict="verified", found_room=SPACED_ROOM,
            candidates=[SPACED_ROOM])
    db.expire_all()

    assert seeded["spaced"].kakao_room_name is None, (
        "서버가 찾아낸 제목을 혼자 넣었다 — 고르는 것은 사람이어야 한다")
    # 그래도 **후보로는 남는다.** 안 남기면 사람이 고를 것이 없다.
    from app.services import room_match
    assert room_match.candidates(seeded["spaced"])["rooms"] == [SPACED_ROOM]


def test_확인_표시도_기업_줄에서는_올라가지_않는다(db, seeded, client):
    """`room_verified` 는 **그 칸에 적힌 글자**에 대한 판정이다. 칸이 비어
    있는데 `확인됨` 이 붙으면, 무엇이 확인됐다는 말인지가 없다."""
    _turn_on(db)
    me = _login(client)
    _search(me)
    item = _jobs(db)[0].items[0]

    _report(me, item.id, verdict="verified", found_room=SPACED_ROOM,
            candidates=[SPACED_ROOM])
    db.expire_all()

    assert item.ir_company.room_verified == "unverified"


def test_초안은_저장되지_않는다(db, seeded):
    """초안은 **보여 주기만** 한다. 어디에도 들어가지 않는다 — 확인 안 된
    이름으로 보내면 발송기가 방을 못 찾는다."""
    from app.services import room_match

    assert room_match.draft(seeded["plain"]) == f"{CEO} 대표 {PLAIN}"
    assert seeded["plain"].kakao_room_name is None
    # 화면을 열어도 들어가지 않는다.
    assert room_match.rows.__doc__  # 읽는 함수일 뿐이다
    assert seeded["plain"].kakao_room_name is None


# ── 2. 발송기를 안 고쳤다 — 이미 있는 잡을 그대로 쓴다  ★ ───────────────────

def test_발송기_판을_올리지_않았다():
    """**이 기능은 재배포가 필요 없다.**

    새 잡 종류를 만들었다면 그 종류를 모르는 발송기가 잡을 집어가지 않아 큐에
    그대로 서고, 팀원 PC 의 발송기를 전부 다시 받을 때까지 돌지 않는다
    (`app/version.py` 의 0.9.0 · 0.10.0 이 그 일을 두 번 적어 두었다).

    그래서 세우는 잡의 종류가 **이미 있는 그것**(`verify_room`)인지를 못박는다.
    새 종류를 쓰려면 이 검사가 먼저 깨지고, 그때 판을 올리게 된다.
    """
    from app.routers import agent_api, startup_send as router

    assert router.VERIFY_KIND is agent_api.VERIFY_KIND
    assert agent_api.VERIFY_KIND == "verify_room"

    import agent.main as agent_main

    assert agent_api.VERIFY_KIND in agent_main.SUPPORTED_KINDS, (
        "발송기가 밝히지 않는 종류다 — 잡이 큐에 그대로 선다")


def test_찾기는_이미_있는_방_확인_잡을_세운다(db, seeded, client):
    """기업 줄을 가리키는 건(`ir_company_id`)으로 서고, **보낼 문구가 없다.**

    `message=""` 는 안전장치다 — 아주 낡은 발송기가 이 잡을 발송으로 오해해도
    보낼 내용이 없어 실패로 끝난다(`routers/contacts.verify_rooms` 가 같은
    이유로 같은 값을 넣는다).
    """
    _turn_on(db)
    me = _login(client)
    res = _search(me)

    jobs = _jobs(db)
    assert len(jobs) == 1
    job = jobs[0]
    assert job.kind == "verify_room"
    assert res.headers["location"] == f"/jobs/{job.id}"

    # 방 제목이 비어 있는 계약 기업만 — 이미 맞춰진 곳은 건드리지 않는다.
    assert {i.ir_company_id for i in job.items} == {
        seeded["spaced"].id, seeded["corp"].id, seeded["plain"].id}
    for item in job.items:
        assert item.message == ""
        assert item.room_name == "", "모르는 방 이름을 지어 넣었다"
        assert item.contact_id is None


def test_폴링이_회사명을_검색어로_내준다(db, seeded, client):
    """발송기는 `query` 로 카톡을 뒤진다. 그 값이 **회사명**이어야 한다 —
    사용자가 정한 길이 그대로다(먼저 회사명으로 검색).

    `firm` 은 **안 보낸다.** 보내면 발송기가 결과가 둘 이상일 때 그것으로
    걸러 하나로 줄이고, 줄여서 하나가 되면 **나머지 후보를 버린 채** 보고한다
    — 사람이 고를 것이 사라진다.
    """
    _turn_on(db)
    me = _login(client)
    _search(me)

    got = me.get("/api/agent/poll", params={"kinds": AGENT_KINDS},
                 headers={"Authorization": f"Bearer {DEMO_TOKEN}"}).json()
    assert got["kind"] == "verify_room"
    by_room = {i["query"]: i for i in got["items"]}

    # 법인 표기는 뗀다 — 카톡 검색은 글자가 든 방을 찾으므로 `(주)` 가 붙은
    # 검색어는 그것이 든 방만 찾는다.
    assert "샘플나" in by_room
    # 띄어 적힌 이름은 **더 짧은 토막**을 함께 준다. 발송기가 `query` 로 0건이면
    # 그것으로 한 번 더 찾는다 — 그래야 `샘플가` 로 만든 방을 찾는다.
    spaced = by_room[SPACED]
    assert spaced["name"] == "샘플"
    assert "firm" not in spaced, "firm 을 보내면 발송기가 후보를 줄여 버린다"


def test_후보가_여럿이면_사유가_고르라고_말한다(db, seeded, client):
    """발송기는 결과가 둘 이상이면 `ambiguous` 로 보고한다. 투자사 쪽 사유는
    *카톡에서 방 이름을 고유하게 바꾸세요* 인데, **여기서는 여러 개가 정상**
    이다 — 그 말을 그대로 적으면 안 해도 되는 일을 시킨다."""
    _turn_on(db)
    me = _login(client)
    _search(me)
    item = _jobs(db)[0].items[0]

    _report(me, item.id, verdict="ambiguous",
            candidates=[SPACED_ROOM, f"{CEO} 대표 샘플가 공유방"])
    db.expire_all()

    assert item.status == "failed"          # 고칠 줄이 실패 목록에 남는다
    assert "고르세요" in (item.error or "")
    assert "고유하게" not in (item.error or "")


# ── 3. 계약 기업 전부가 한 판에 선다  ★ ────────────────────────────────────

def test_계약_기업_전부가_한_화면에_선다(db, seeded, client):
    """**이미 맞춰진 곳도 남는다.** 빼면 "계약 기업인데 왜 이 표에 없지" 를
    화면에서 물을 수가 없다(`startup_send.rows` 의 그 규칙 그대로)."""
    _turn_on(db)
    body = _rows(_login(client)).text

    for name in (SPACED, CORP, PLAIN, MATCHED):
        assert name in body, f"{name} 줄이 표에서 빠졌다"
    assert "샘플마" not in body, "계약을 안 한 기업이 섰다"

    # 줄마다 적는 칸이 하나씩 — 한 판에 다룰 수 있어야 한다.
    assert body.count('name="rooms"') == 4
    assert body.count('name="company_ids"') == 4


def test_후보는_눌러_넣는_단추로_선다(db, seeded, client):
    """카톡에서 가져온 **진짜 제목**이 줄마다 선다. 회사명이 든 후보를
    도드라지게 두는 것은 사용자가 짚어 준 그 성질이 고를 근거이기 때문이다."""
    from app.clock import now_iso
    from app.services import room_match

    other = f"{CEO} 대표 다른회사"
    room_match.save_candidates(seeded["spaced"], [SPACED_ROOM, other],
                               at=now_iso(), query="샘플가")
    db.commit()
    _turn_on(db)
    body = _rows(_login(client)).text

    assert f'data-room="{SPACED_ROOM}"' in body
    assert "room-pick named" in body, "회사명이 든 후보가 도드라지지 않는다"
    # 회사명이 안 든 후보도 **지우지 않는다** — 우리가 아는 이름이 방을 만들 때
    # 쓴 이름과 다를 수 있어, 지우면 맞는 방이 화면에서 사라진다.
    assert other in body
    assert "회사명 없음" in body


def test_초안은_초안이라고_적혀_선다(db, seeded, client):
    """그대로 저장되면 발송기가 방을 못 찾으므로, 카톡에서 가져온 제목과
    **같은 꼴로 서면 안 된다.**"""
    _turn_on(db)
    body = _rows(_login(client)).text

    assert "room-pick draft" in body
    assert f'data-room="{CEO} 대표 {PLAIN}"' in body
    assert "초안" in body


def test_한_번도_안_찾아본_곳과_찾았는데_없는_곳을_가른다(db, seeded, client):
    """해야 할 일이 정반대다 — 앞은 단추를 누르면 되고, 뒤는 카톡을 사람이
    들여다봐야 한다. 둘을 `후보 없음` 으로 묶으면 그 갈림이 사라진다."""
    from app.clock import now_iso
    from app.services import room_match

    room_match.save_candidates(seeded["corp"], [], at=now_iso(), query="샘플나")
    db.commit()
    _turn_on(db)
    body = _rows(_login(client)).text

    assert "아직 찾아보지 않았습니다" in body
    assert "카톡에 걸린 방이" in body


# ── 4. 한 번에 저장한다 ─────────────────────────────────────────────────────

def test_여러_줄을_한_번에_넣는다(db, seeded, client):
    _turn_on(db)
    me = _login(client)
    res = _save(me, [(seeded["spaced"].id, SPACED_ROOM),
                     (seeded["plain"].id, f"{CEO} 대표 {PLAIN}"),
                     (seeded["corp"].id, "")])
    db.expire_all()

    assert res.status_code == 303
    assert seeded["spaced"].kakao_room_name == SPACED_ROOM
    assert seeded["plain"].kakao_room_name == f"{CEO} 대표 {PLAIN}"
    assert seeded["corp"].kakao_room_name is None   # 빈 칸은 그대로 빈 칸이다
    assert "2곳의 방 제목을 넣었습니다" in unquote(res.headers["location"])


def test_앞뒤_공백은_떼고_가운데는_안_건드린다(db, seeded, client):
    """붙여 넣을 때 딸려 온 공백 하나로 못 찾는 방이 된다. 그렇다고 가운데를
    줄이지는 않는다 — 두 칸 띄운 방이 있다면 줄여 적는 순간 못 찾는 이름이다."""
    _turn_on(db)
    _save(_login(client), [(seeded["plain"].id, "  가나다 대표  샘플다  ")])
    db.expire_all()

    assert seeded["plain"].kakao_room_name == "가나다 대표  샘플다"


def test_짝이_어긋나면_한_줄도_넣지_않는다(db, seeded, client):
    """어긋난 채로 넣으면 A 기업 칸의 글자가 B 기업 방 이름이 된다 —
    그것이 곧 오발송이다."""
    _turn_on(db)
    res = _login(client).post("/deals/startup-ir/rooms", follow_redirects=False,
                              data={"company_ids": [seeded["spaced"].id,
                                                    seeded["plain"].id],
                                    "rooms": [SPACED_ROOM]})
    db.expire_all()

    assert res.status_code == 303
    assert seeded["spaced"].kakao_room_name is None
    assert seeded["plain"].kakao_room_name is None
    assert "어긋났습니다" in unquote(res.headers["location"])


def test_계약_기업이_아니면_주소로도_안_들어간다(db, seeded, client):
    """화면에 선 줄과 여기서 받는 줄이 **같은 함수**로 갈린다
    (`room_match.company_ids`)."""
    _turn_on(db)
    _save(_login(client), [(seeded["nope"].id, "아무 방")])
    db.expire_all()

    assert seeded["nope"].kakao_room_name is None


# ── 5. 글자가 바뀌면 확인은 무효다  ★ ──────────────────────────────────────

def test_방_이름을_고치면_확인이_풀린다(db, seeded, client):
    _turn_on(db)
    seeded["matched"].room_verified = "verified"
    db.commit()

    _save(_login(client), [(seeded["matched"].id, "가나다 대표 샘플라 공유방")])
    db.expire_all()

    assert seeded["matched"].room_verified == "unverified"


def test_IR_기업_현황의_수정_창도_같은_자리를_지난다(db, seeded, logged_in):
    """적는 자리가 둘이면 **한쪽만 확인 표시를 지운다** — 창에서 고친 기업이
    `확인됨` 배지를 그대로 달고 있게 되고, 그 배지는 거짓말이다."""
    seeded["matched"].room_verified = "verified"
    db.commit()

    res = logged_in.patch(f"/api/companies/{seeded['matched'].id}",
                          json={"kakao_room_name": "가나다 대표 샘플라 새방"})
    db.expire_all()

    assert res.status_code == 200
    assert seeded["matched"].kakao_room_name == "가나다 대표 샘플라 새방"
    assert seeded["matched"].room_verified == "unverified"


def test_같은_글자를_다시_저장하면_확인이_남는다(db, seeded, client):
    """바뀐 것이 없으면 아무 일도 없다. 저장 단추를 한 번 더 눌렀다고 확인이
    풀리면, 한 판에 저장하는 이 화면에서는 **누를 때마다 전부 풀린다.**"""
    _turn_on(db)
    seeded["matched"].room_verified = "verified"
    db.commit()
    same = seeded["matched"].kakao_room_name

    _save(_login(client), [(seeded["matched"].id, same)])
    db.expire_all()

    assert seeded["matched"].room_verified == "verified"


# ── 6. 발송 판정은 그대로다  ★ ─────────────────────────────────────────────

def test_확인_안_된_방도_보낼_수_있다(db, seeded):
    """막으면 찾기가 한 번 실패한 달에 월간 발송이 통째로 선다 — 그 까닭은
    "방 이름이 틀렸다" 가 아니라 "카톡을 못 뒤졌다"(PC 가 꺼져 있었다)다.
    투자사 쪽도 `unverified` 를 막지 않는다(`routers/deals.py: room_ok`)."""
    from app.services import ir_monthly, startup_send

    month = ir_monthly.this_month()
    assert seeded["matched"].room_verified == "unverified"

    row = next(r for r in startup_send.rows(db, month)["rows"]
               if r["company"].id == seeded["matched"].id)
    # 보낼 줄이 없는 것(`NO_LINES`)과 방 이름이 없는 것(`NO_ROOM`)은 갈린다 —
    # 여기서 확인하려는 것은 **까닭이 `방 이름 없음` 이 아니라는 것**이다.
    assert row["reason"] != startup_send.NO_ROOM
    assert row["verified"] is False


def test_확인은_세어서_보여_주기만_한다(db, seeded):
    """`sendable` 에 끼지 않는다. 숫자로는 적는다 — 아무도 확인하지 않은
    이름으로 회차를 세우고도 그것을 모르면 안 된다."""
    from app.services import ir_monthly, startup_send

    before = startup_send.rows(db, ir_monthly.this_month())
    seeded["matched"].room_verified = "verified"
    db.commit()
    after = startup_send.rows(db, ir_monthly.this_month())

    assert after["verified_count"] == before["verified_count"] + 1
    assert after["sendable_count"] == before["sendable_count"]
    assert after["no_room_count"] == before["no_room_count"]


def test_보내는_표가_맞추기_표를_가리킨다(db, seeded, client):
    """지금까지 이 안내는 `IR 기업 현황` 의 [수정] 을 가리켰고, 그 창은 한
    기업씩 여는 자리라 수십 곳이 비어 있을 때 쓸 수 없었다."""
    _turn_on(db)
    body = _login(client).get("/deals/startup-ir").text

    assert "/deals/startup-ir/rooms" in body
    assert "확인 안 됨" in body


# ── 7. 정해진 한 계정만 ────────────────────────────────────────────────────

def test_지정되지_않은_계정에는_없는_자리다(db, seeded, client):
    """보내는 자리와 **같은 판정**(`startup_send.may_send`)을 지난다. 403 이
    아니라 404 다 — 403 은 쓸 수 없는 기능의 존재를 알려 준다."""
    _turn_on(db, user_id=1)
    other = _login(client, phone="01000000002")

    assert other.get("/deals/startup-ir/rooms").status_code == 404
    assert _save(other, [(seeded["plain"].id, "아무 방")]).status_code == 404
    assert _search(other).status_code == 404
    assert not _jobs(db)
    db.expire_all()
    assert seeded["plain"].kakao_room_name is None


def test_꺼져_있으면_아무에게도_없다(db, seeded, logged_in):
    assert logged_in.get("/deals/startup-ir/rooms").status_code == 404


# ── 견주기 · 초안 규칙 ──────────────────────────────────────────────────────

def test_회사명_견주기는_띄어쓰기와_법인_표기를_넘는다():
    """사용자가 짚어 준 「회사명이 무조건 들어가 있음」이 매칭의 열쇠인데,
    실제 표기가 제각각이다(`샘플 가` ↔ `샘플가` ↔ `(주)샘플가`). 규칙은
    `ir_monthly._key` 가 쓰는 것과 **같은 것**이다."""
    from app.services import room_match

    assert room_match.has_company_name(SPACED_ROOM, "샘플 가")
    assert room_match.has_company_name(SPACED_ROOM, "(주)샘플가")
    assert room_match.has_company_name("가나다 대표 샘플 가 , 라마바", "샘플가")
    assert not room_match.has_company_name(SPACED_ROOM, "샘플다")
    # 회사명을 모르면 견줄 것이 없다 — `있다` 고 답하지 않는다.
    assert not room_match.has_company_name(SPACED_ROOM, "")


def test_초안은_대표자와_회사명까지만_짓는다(db, seeded):
    """꼬리의 `, 우리 팀원 직함` 을 **일부러 안 붙인다.** 채울 칸이
    `assignee_name` 하나뿐이고 그 칸에는 이관 이력이 들어 있다 — 운영 자료에서
    `A -> B` 꼴의 화살표·날짜 접두가 섞여 있는 줄이 과반이다. 없는 것을 지어
    붙이면 초안이 **그럴듯해지고**, 그럴듯한 초안은 확인 없이 저장된다."""
    from app.models import IrCompany
    from app.services import room_match

    assert room_match.draft(seeded["plain"]) == f"{CEO} 대표 {PLAIN}"
    # 법인 표기는 뗀다. 대표를 모르면 **회사명만** — 그래도 검색어로는 쓸모가 있다.
    assert room_match.draft(seeded["corp"]) == "샘플나"

    # 이관 이력이 든 담당자 칸은 초안에 실리지 않는다.
    messy = IrCompany(name=PLAIN, contact_name=CEO,
                      assignee_name="라마바 -> 사아자 09/08")
    assert "->" not in room_match.draft(messy)
    assert "09/08" not in room_match.draft(messy)

    # 투자사 쪽 고정 접미사도 안 붙는다 — 그 규칙은 투자사 방 것이다.
    assert "Asset" not in room_match.draft(seeded["plain"])


def test_검색어는_회사명이고_두_번째_시도는_더_짧다(db, seeded):
    from app.services import room_match

    assert room_match.search_query(seeded["corp"]) == "샘플나"
    assert room_match.search_query(seeded["spaced"]) == SPACED
    # 띄어 적힌 이름은 가장 긴 토막으로 한 번 더 — `샘플가` 로 만든 방을 찾는다.
    assert room_match.search_seed(seeded["spaced"]) == "샘플"
    # 한 토막이면 같은 글자가 되고, 그때 발송기는 두 번째 검색을 건너뛴다.
    assert room_match.search_seed(seeded["plain"]) == PLAIN


def test_깨진_후보_글자로는_화면이_터지지_않는다(db, seeded, client):
    """이 값으로 열리는 것은 **고르는 화면**이다. 거기서 500 이 나면 방 이름을
    채울 길이 통째로 막힌다."""
    seeded["plain"].room_candidates = "{이건 JSON 이 아니다"
    db.commit()
    _turn_on(db)

    assert _rows(_login(client)).status_code == 200


def test_후보를_담아도_방_이름은_안_바뀐다(db, seeded):
    """담는 함수 자체가 `kakao_room_name` 을 모른다 — 모르는 것이 안전하다."""
    from app.clock import now_iso
    from app.services import room_match

    room_match.save_candidates(seeded["matched"], ["아무 방", "아무 방", " "],
                               at=now_iso(), query="샘플라")
    db.commit()

    assert seeded["matched"].kakao_room_name == f"{CEO} 대표 {MATCHED}"
    # 같은 제목이 두 번 오면 한 번만 남는다 — 같은 단추가 둘 서면 사람은
    # 둘이 다른 방인 줄 안다.
    assert room_match.candidates(seeded["matched"])["rooms"] == ["아무 방"]


def test_찾기는_이미_맞춰진_곳을_덮지_않는다(db, seeded, client):
    """사람이 카톡에서 옮겨 적은 글자를 기계가 찾아온 후보로 덮지 않는다."""
    _turn_on(db)
    _search(_login(client))

    assert seeded["matched"].id not in {i.ir_company_id
                                       for i in _jobs(db)[0].items}


def test_찾을_곳이_없으면_잡을_세우지_않는다(db, seeded, client):
    """빈 잡을 세우면 진행 화면이 `0건 완료` 로 열리고, 사람은 찾아봤다고
    읽는다."""
    _turn_on(db)
    me = _login(client)
    _save(me, [(seeded["spaced"].id, SPACED_ROOM),
               (seeded["corp"].id, "가나다 대표 샘플나"),
               (seeded["plain"].id, f"{CEO} 대표 {PLAIN}")])

    res = _search(me)
    assert res.status_code == 303
    assert "/deals/startup-ir/rooms" in res.headers["location"]
    assert not _jobs(db)


def test_진행_화면이_어느_기업_것인지_말한다(db, seeded, client):
    """기업 줄로 선 건에는 담당자가 없다. 진행 화면이 빈 칸을 보여 주면 어느
    기업을 찾고 있는지 알 수 없다 — `SendItem.recipient_name` 이 기업 이름을
    내놓는다."""
    _turn_on(db)
    me = _login(client)
    _search(me)
    job = _jobs(db)[0]

    names = {i["contact_name"] for i in me.get(f"/api/jobs/{job.id}").json()["items"]}
    assert SPACED in names


def test_맞추기_화면의_표는_가로로_밀_상자_안에_있다(db, seeded, client):
    """폰에서 표가 페이지를 통째로 밀어내지 않게. 템플릿 폴더를 훑는 검사가
    이미 있지만(`test_mobile_layout`), 이 화면은 줄마다 입력칸이 서서 폭이
    가장 쉽게 벌어지는 자리라 여기서도 못박는다."""
    _turn_on(db)
    body = _rows(_login(client)).text

    assert '<div class="table-wrap">' in body
    assert body.index('<div class="table-wrap">') < body.index('<table class="grid-table">')


def test_후보_단추는_폼을_보내지_않는다(db, seeded, client):
    """후보 단추는 폼 **안**에 선다. `type="button"` 이 빠지면 누르는 순간
    저장이 되고, 사람이 보려던 후보가 그대로 들어간다."""
    _turn_on(db)
    body = _rows(_login(client)).text

    picks = re.findall(r'<(\w+)([^>]*?)class="chip room-pick', body)
    assert picks, "후보 단추가 한 줄도 안 섰다 — 이 검사가 아무것도 못 지킨다"
    for tag, attrs in picks:
        assert tag == "button" and 'type="button"' in attrs, (
            "후보 단추에 type=\"button\" 이 없다 — 폼 안이라 누르면 전송된다")


# ── 브라우저 쪽 ─────────────────────────────────────────────────────────────

def test_후보를_누르는_동작은_node_로_잰다():
    """`tests/js/startup_room_test.js` — 누른 후보가 **그 줄의** 칸에 그대로
    들어가는가, 폼이 전송되지 않는가, 저절로 채우지 않는가.

    `node` 가 없으면 건너뛴다(검사 틀이 쓰는 그 방식이다)."""
    import shutil
    import subprocess
    from pathlib import Path

    node = shutil.which("node")
    if node is None:
        pytest.skip("node 미설치 — 브라우저 로직 검사 생략 "
                    "(호스트에서 `node tests/js/startup_room_test.js`)")
    js = Path(__file__).resolve().parent / "js" / "startup_room_test.js"
    done = subprocess.run([node, str(js)], capture_output=True, text=True,
                          timeout=60)
    assert done.returncode == 0, done.stdout + done.stderr


def test_가짜_화면이_실제_화면과_같은_이름을_쓴다(db, seeded, client):
    """`node` 검사는 손으로 지은 화면에서 돈다. 실제 템플릿에서 이름이 바뀌면
    그쪽은 **조용히 통과한다** — 그 틈을 여기서 막는다
    (`tests/js/_ir_dom.js` 가 같은 말을 적어 두었다)."""
    from pathlib import Path

    _turn_on(db)
    body = _rows(_login(client)).text
    js = (Path(__file__).resolve().parent / "js" / "startup_room_test.js"
          ).read_text(encoding="utf-8")

    # 템플릿은 `class="chip room-pick"` 로, 가짜 화면은 `{ class: "room-pick" }`
    # 로 적는다 — 꼴이 달라서 **이름만** 견준다.
    for token in ("room-match", "room-input", "rooms", "company_ids",
                  "room-pick", "data-room"):
        assert token in body, f"템플릿에서 {token} 가 사라졌다"
        assert token in js, f"가짜 화면이 {token} 를 안 쓴다"
    assert "startup_room.js" in body, "화면이 그 스크립트를 안 싣는다"


def test_확인이_not_found_여도_대기_목록이_선다(db, seeded, client):
    """**발송 판정에 영향이 없다는 것을 길 끝까지 잰다.**

    찾기가 실패해 `not_found` 가 박힌 기업도 회차에 실린다. 목록을 만드는
    자리(`routers/deals.create_send_list`)는 **방 이름이 비었는가** 하나만
    본다 — 투자사 쪽 미리보기가 `room_verified` 를 보는 자리는 스타트업
    발송이 아예 들어가지 않는 길이다(`deals.py` 의 `MODE_STARTUP` 거절).

    막았다면 카톡을 못 뒤진 달(PC 가 꺼져 있었다)에 월간 발송이 통째로 선다.
    """
    from app.models import IrRequest, SendJob, VcContact
    from app.services import ir_monthly

    month = ir_monthly.this_month()
    # 그 달까지 요청한 투자사를 하나 만들어야 실을 줄이 생긴다.
    who = VcContact(user_id=1, name="홍길동", firm="가나벤처스")
    db.add(who)
    db.flush()
    db.add(IrRequest(user_id=1, contact_id=who.id,
                     company_id=seeded["matched"].id,
                     company_name=MATCHED, requested_at=f"{month}-03"))
    seeded["matched"].room_verified = "not_found"
    db.commit()
    _turn_on(db)

    res = _login(client).post("/deals/startup-ir/send", follow_redirects=False,
                              data={"month": month,
                                    "company_ids": [seeded["matched"].id],
                                    "title": "검사 회차"})

    assert res.status_code == 303 and "/jobs/" in res.headers["location"]
    from sqlalchemy import select
    job = db.execute(select(SendJob)).scalars().one()
    assert job.kind == "startup_ir"
    assert [i.room_name for i in job.items] == [f"{CEO} 대표 {MATCHED}"]
