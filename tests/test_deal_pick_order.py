"""딜 소개 — **고른 차례가 곧 문구의 번호다.**

문구는 `1) …` `2) …` 로 나가고 투자사는 그 번호로 기억해서 "2번 자료 주세요"
라고 답한다. 그래서 어느 기업이 몇 번인지가 이 화면의 알맹이다.

화면이 고른 차례를 안 들고 있어서 **목록에 그려진 차례**로 나가던 일을 고쳤다
(`tests/js/deals_pick_order_test.js`). 여기서는 그 차례가 서버를 지나는 동안
**어디서도 다시 정렬되지 않는지**를 끝까지 따라간다. 고친 자리는 화면이지만,
서버가 조용히 다시 세우면 화면만 고쳐 봐야 소용이 없다.

따라가는 길은 셋이고 전부 **거꾸로 고른 경우**로 본다(차례대로 고르면 목록
차례와 같아서 뒤섞여도 안 걸린다).

  · 미리보기 문구의 `1) 2) 3)`
  · 실제 발송 — `DealBatchCompany.position` 과 저장된 문구
  · 예약 큐 — `DealQueueCompany.position`, 그리고 [시작] 이 만든 회차

이름·회사명은 전부 가상이다(공개 저장소).
"""
from __future__ import annotations

import re

import pytest

from .conftest import DEMO_PASSWORD

GROUP = "1군"


@pytest.fixture()
def seed(client, db, users):
    """u1 로 로그인 + 소개 가능한 기업 셋 + 카톡방이 등록된 담당자 하나.

    기업 셋을 **목록에 그려지는 차례**(가 → 나 → 다)로 넣어 둔다. 검사는 이
    차례를 일부러 거꾸로 뒤집어 고른다.
    """
    from app.models import IrCompany, VcContact

    companies = [
        # 요약문에 **이름이 들어 있어야** 번호가 어느 기업 것인지 가릴 수 있다
        # (운영 요약문도 기업명으로 시작한다).
        IrCompany(name="가나애그", sector_major="애그테크", series="Seed",
                  one_liner="B2B 농산물 선도거래",
                  summary="가나애그 [애그테크] B2B 농산물 선도거래",
                  summary_status="done", revenue_recent=12),
        IrCompany(name="다라헬스", sector_major="헬스케어", series="Pre-A",
                  one_liner="비대면 진료 보조",
                  summary="다라헬스 [헬스케어] 비대면 진료 보조",
                  summary_status="done", revenue_recent=8),
        IrCompany(name="마바로보", sector_major="로보틱스", series="Seed",
                  one_liner="물류 상하차 로봇",
                  summary="마바로보 [로보틱스] 물류 상하차 로봇",
                  summary_status="done", revenue_recent=5),
    ]
    contact = VcContact(
        user_id=users["u1"].id, name="가담당", title="심사역", firm="사아벤처스",
        group_name=GROUP, connect_stage="connected", status="active",
        kakao_room_name="가담당 심사역님 사아벤처스", room_verified="verified",
        channel_kakao=1, source_sheet="가 명단",
    )
    db.add_all(companies + [contact])
    db.commit()
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    return {
        "ids": {c.name: c.id for c in companies},
        "listed": [c.id for c in companies],      # 목록에 그려지는 차례
        "contact_id": contact.id,
    }


def _reversed_pick(seed):
    """거꾸로 고른 차례 — 다 → 가 → 나. 목록 차례와 다르다."""
    ids = seed["ids"]
    return [ids["마바로보"], ids["가나애그"], ids["다라헬스"]]


def _numbered_names(text: str) -> list:
    """문구에서 `1) [분야] 이름 …` 의 **번호 붙은 차례**만 뽑는다."""
    return [line.split(")", 1)[1].strip()
            for line in text.splitlines()
            if re.match(r"^\d+\)\s", line)]


def _first(names: list) -> list:
    """줄에서 기업 이름만 — 한줄소개가 뒤에 붙어 있어 앞머리로 가른다."""
    out = []
    for line in names:
        for name in ("가나애그", "다라헬스", "마바로보"):
            if name in line:
                out.append(name)
                break
    return out


# ── 미리보기 ────────────────────────────────────────────────────────────────

def test_preview_numbers_follow_the_pick_order(client, seed):
    """`1) 2) 3)` 은 **받은 차례**대로 붙는다 — 목록 차례로 다시 세우지 않는다."""
    r = client.post("/api/deals/preview", json={
        "company_ids": _reversed_pick(seed),
        "contact_ids": [seed["contact_id"]],
    })
    assert r.status_code == 200, r.text
    text = r.json()["previews"][0]["message"]

    assert _first(_numbered_names(text)) == ["마바로보", "가나애그", "다라헬스"], text


# ── 실제 발송 ───────────────────────────────────────────────────────────────

def test_send_writes_positions_in_the_pick_order(client, db, seed):
    """`DealBatchCompany.position` 이 고른 차례 그대로다.

    이 번호는 **다음 회차까지 남는다** — 자료를 보낼 때 `deal_positions` 가
    이것을 읽어 "2번 기업 …" 이라고 짚어 준다. 여기서 어긋나면 투자사가 기억한
    번호와 다른 기업 이야기가 나간다.
    """
    from sqlalchemy import select

    from app.models import DealBatchCompany

    picked = _reversed_pick(seed)
    r = client.post("/api/deals/send", json={
        "company_ids": picked,
        "contact_ids": [seed["contact_id"]],
        "title": "가상 회차",
    })
    assert r.status_code == 200, r.text

    db.expire_all()
    rows = db.execute(
        select(DealBatchCompany).order_by(DealBatchCompany.position)
    ).scalars().all()
    assert [row.company_id for row in rows] == picked
    assert [row.position for row in rows] == [1, 2, 3]


def test_sent_message_numbers_match_the_pick_order(client, db, seed):
    """**실제로 나갈 문구**(스냅샷)의 번호도 같은 차례다.

    미리보기만 맞고 발송이 다르면 제일 나쁘다 — 사람이 눈으로 확인한 것과
    다른 것이 실투자사 카톡방으로 나가고, 되돌릴 수가 없다.
    """
    from sqlalchemy import select

    from app.models import SendItem

    r = client.post("/api/deals/send", json={
        "company_ids": _reversed_pick(seed),
        "contact_ids": [seed["contact_id"]],
        "title": "가상 회차",
    })
    assert r.status_code == 200, r.text

    db.expire_all()
    message = db.execute(select(SendItem)).scalars().first().message
    assert _first(_numbered_names(message)) == ["마바로보", "가나애그", "다라헬스"], message


# ── 예약 큐 ─────────────────────────────────────────────────────────────────

def test_queue_keeps_the_pick_order(client, db, seed):
    """예약에 담긴 차례가 고른 차례다 — 걸어 둔 뒤에도 그대로 읽힌다."""
    from app.models import DealQueueItem
    from app.services import deal_queue

    picked = _reversed_pick(seed)
    r = client.post("/api/deals/queue", json={
        "group_name": GROUP, "company_ids": picked, "title": "가상 회차",
    })
    assert r.status_code == 200, r.text

    db.expire_all()
    item = db.get(DealQueueItem, r.json()["item_id"])
    assert deal_queue.company_ids(item) == picked


def test_queue_start_sends_in_the_pick_order(client, db, seed):
    """[시작] 이 만든 회차의 번호도 예약할 때 화면에 보이던 차례다.

    예약은 걸어 두고 나중에 누른다. 그 사이에 차례가 뒤집히면 무엇이 몇 번으로
    나갔는지 아무도 모른 채 되돌릴 수 없는 일이 끝나 있다.
    """
    from sqlalchemy import select

    from app.models import DealBatchCompany, SendItem

    picked = _reversed_pick(seed)
    item_id = client.post("/api/deals/queue", json={
        "group_name": GROUP, "company_ids": picked, "title": "가상 회차",
    }).json()["item_id"]

    r = client.post(f"/api/deals/queue/{item_id}/start", json={})
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True, r.text

    db.expire_all()
    rows = db.execute(
        select(DealBatchCompany).order_by(DealBatchCompany.position)
    ).scalars().all()
    assert [row.company_id for row in rows] == picked

    message = db.execute(select(SendItem)).scalars().first().message
    assert _first(_numbered_names(message)) == ["마바로보", "가나애그", "다라헬스"], message


# ── 브라우저 쪽 ─────────────────────────────────────────────────────────────
#
# **고친 자리는 여기다.** 고른 차례를 들고 있는 것도, 카드에 번호를 붙이는 것도
# 브라우저에 있다. 그 규칙을 파이썬으로 다시 구현하면 두 벌이 되어 어긋나도
# 모르므로, deals.js 를 **그대로 실행**해 본다
# (`tests/js/deals_pick_order_test.js`).

def test_화면이_고른_차례를_들고_미리보기_발송_예약에_그대로_싣는다():
    """★ 거꾸로 골라도(3 → 1 → 2) 고른 차례로 나가는가.

    차례대로 고르면 목록 차례와 같아서 뒤섞여도 아무것도 안 잡힌다. 그래서
    저쪽 검사는 전부 거꾸로 고른다. 카드에 번호가 뜨는지, 체크를 풀면 뒤
    번호가 당겨지는지, 그 차례가 미리보기·발송·예약 셋 다에 같이 실리는지를
    한자리에서 본다.
    """
    import shutil
    import subprocess
    from pathlib import Path

    node = shutil.which("node")
    if node is None:
        pytest.skip("node 미설치 — 브라우저 로직 테스트 생략 "
                    "(호스트에서 `node tests/js/deals_pick_order_test.js`)")
    js = Path(__file__).resolve().parent / "js" / "deals_pick_order_test.js"
    result = subprocess.run([node, str(js)], capture_output=True,
                            text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
