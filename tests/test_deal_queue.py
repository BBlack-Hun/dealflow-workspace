"""예약 큐 — **대상을 담지 않고, 누를 때 다시 센다.**

이 파일이 지키려는 것은 하나다. 예약 줄에는 **그룹 이름만** 있고 받는 사람이
없어야 한다. 굳혀 두면 예약해 둔 사이에 카톡방을 나갔거나 `검토중단` 이 된
분께 그대로 나간다 — 실투자사 카톡방이고, 되돌릴 수가 없다.

그래서 여기서는 **예약해 둔 뒤 명단을 실제로 흔들어 본다**: 한 분은 방을
나가게 하고, 한 분은 `검토중단` 으로 세우고, 한 분은 새로 연결시킨다. 그러고도
줄에 적히는 수와 [시작] 이 실제로 만든 발송 목록이 **그때의 명단**이면 통과다.

함께 못박는 것들.

  · **미리보기 수와 실제 수가 다를 때 화면이 무슨 말을 하는가.** 조용히 다른
    수로 보내면 몇 명에게 나갔는지 아무도 모른다.
  · **`(그룹 없음)` 줄도 선다.** 운영에 그룹이 빈 분이 열일곱 명인데, 큐가
    그분들을 빼면 이 화면을 통해서는 영영 아무것도 못 받는다.
  · **예약이 `DealBatch` 를 세는 곳에 안 걸린다.** 표를 나눈 이유가 그것이라,
    나눔이 풀리면 안 보낸 기업이 `최근에 소개함` 으로 찍힌다.

이름·회사명은 전부 가상이다(공개 저장소).
"""
from __future__ import annotations

import pytest

from .conftest import DEMO_PASSWORD

GROUP_A = "1군"
GROUP_B = "2군"


@pytest.fixture()
def seed(client, db, users):
    """u1 로 로그인 + 기업 둘 + 그룹이 갈리는 담당자들.

    `1군` 넷은 전부 연결이 끝나 있고, 그룹을 안 정해 둔 분이 둘, `2군` 에는
    아직 연결 전인 분 하나. 명단 설정(`SheetOwner`) 줄을 만들지 않는다 —
    설정이 없는 이름은 딜 소개 명단으로 친다(`sheet_owner.is_deal_list`).
    """
    from app.models import IrCompany, VcContact

    companies = [
        IrCompany(name="가나애그", sector_major="애그테크", series="Seed",
                  one_liner="B2B 농산물 선도거래", summary="요약문",
                  summary_status="done", revenue_recent=12),
        IrCompany(name="다라헬스", sector_major="헬스케어", series="Pre-A",
                  one_liner="비대면 진료 보조", summary="요약문",
                  summary_status="done", revenue_recent=8),
    ]

    def contact(name, group, stage="connected", status="active"):
        return VcContact(
            user_id=users["u1"].id, name=name, title="심사역", firm="마바벤처스",
            group_name=group or None, connect_stage=stage, status=status,
            kakao_room_name=f"{name} 방", room_verified="verified",
            channel_kakao=1, source_sheet="가 명단",
        )

    people = [
        contact("가담당", GROUP_A),
        contact("나담당", GROUP_A),
        contact("다담당", GROUP_A),
        contact("라담당", GROUP_A),
        contact("마담당", ""),          # 그룹을 안 정해 둔 분
        contact("바담당", ""),
        contact("사담당", GROUP_B, stage="in_progress"),   # 아직 연결 전
    ]
    db.add_all(companies + people)
    db.commit()
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    return {
        "company_ids": [c.id for c in companies],
        "ids": {p.name: p.id for p in people},
    }


def _reserve(client, seed, group=GROUP_A, companies=None):
    r = client.post("/api/deals/queue", json={
        "group_name": group,
        "company_ids": companies or seed["company_ids"],
        "title": "08/26 (8월 4주차)",
    })
    assert r.status_code == 200, r.text
    return r.json()


def _rows(db, users):
    from app.services import deal_queue

    db.expire_all()
    return deal_queue.rows(db, users["u1"])


def _move(db, contact_id, **fields):
    """예약해 둔 뒤 명단이 흔들리는 상황을 만든다."""
    from app.models import VcContact

    row = db.get(VcContact, contact_id)
    for k, v in fields.items():
        setattr(row, k, v)
    db.commit()


# ── ① 예약에는 대상이 없다 ─────────────────────────────────────────────────

def test_예약_줄에는_받는_사람_칸이_없다(db):
    """칸이 있으면 언젠가 채워진다. 애초에 담을 자리를 두지 않는다."""
    from app.models import DealQueueItem

    names = set(DealQueueItem.__table__.columns.keys())
    # 대상을 가리킬 만한 이름이 하나도 없어야 한다.
    assert not (names & {"contact_id", "contact_ids", "recipients",
                         "target_ids", "targets", "total"}), names
    # 그룹 이름 하나로 대상을 정한다.
    assert "group_name" in names


def test_예약_시각_칸을_두지_않는다(db):
    """이 앱에는 예약을 실행할 장치가 **일부러** 없다(크론도 워커도 없다).

    시각 칸을 두면 화면은 약속을 하는데 지킬 사람이 없다 — 적어 두고 안
    나간 것을 나간 줄 알게 되는 것이 제일 나쁘다.
    """
    from app.models import DealQueueItem

    names = set(DealQueueItem.__table__.columns.keys())
    assert not (names & {"scheduled_at", "run_at", "due_at", "send_at",
                         "scheduled_for"}), names


# ── ② ★ 예약 뒤 대상이 바뀌면, 그때의 명단으로 나간다 ──────────────────────

def test_예약한_뒤_명단이_바뀌면_줄의_수가_따라_움직인다(client, db, users, seed):
    """줄에 적히는 `대상 N명` 은 **저장된 수가 아니라 지금 센 수**다.

    저장하면 화면이 어제의 수를 오늘의 수인 척 보여 준다. 예약을 걸어 둔 뒤에
    명단을 흔들어, 예약 줄을 한 번도 건드리지 않았는데 수가 따라 움직이는지 본다.
    """
    _reserve(client, seed)
    assert [r["target_count"] for r in _rows(db, users)] == [4]

    # 한 분은 방을 나가고, 한 분은 검토중단이 되었다.
    _move(db, seed["ids"]["가담당"], connect_stage="left_room")
    _move(db, seed["ids"]["나담당"], status="paused")
    assert [r["target_count"] for r in _rows(db, users)] == [2]

    # 아직 연결 전이던 분이 `1군` 으로 들어오며 연결이 끝났다 — 늘기도 한다.
    _move(db, seed["ids"]["사담당"], group_name=GROUP_A, connect_stage="connected")
    assert [r["target_count"] for r in _rows(db, users)] == [3]


def test_시작하면_예약할_때가_아니라_지금_명단으로_나간다(client, db, users, seed):
    """★ 이 파일의 핵심.

    예약할 때 넷이었고, 그사이 둘이 빠졌다. 그러면 **둘에게만** 나가야 하고,
    빠진 두 분은 발송 목록에 이름조차 없어야 한다.
    """
    from app.models import SendItem, SendJob
    from sqlalchemy import select

    item = _reserve(client, seed)
    assert item["target_count"] == 4

    _move(db, seed["ids"]["가담당"], connect_stage="left_room")   # 방을 나갔다
    _move(db, seed["ids"]["나담당"], status="paused")             # 검토중단

    # 화면에 적혀 있던 수(4)를 그대로 들고 눌렀다 — 서버가 먼저 되묻는다.
    r = client.post(f"/api/deals/queue/{item['item_id']}/start", json={"shown": 4})
    assert r.status_code == 200, r.text
    assert r.json()["needs_confirm"] is True
    assert r.json()["now"] == 2
    # 되묻는 동안에는 **아무것도 만들어지지 않았다.**
    db.expire_all()
    assert db.execute(select(SendJob)).scalars().all() == []

    r = client.post(f"/api/deals/queue/{item['item_id']}/start",
                    json={"shown": 4, "confirmed": True})
    assert r.status_code == 200, r.text
    assert r.json()["total"] == 2

    db.expire_all()
    job = db.execute(select(SendJob)).scalars().one()
    assert job.status == "queued"       # 발송 경로는 그대로 — 에이전트가 집어 간다
    went = {
        i.contact_id for i in
        db.execute(select(SendItem).where(SendItem.job_id == job.id)).scalars().all()
    }
    assert went == {seed["ids"]["다담당"], seed["ids"]["라담당"]}
    assert seed["ids"]["가담당"] not in went     # 방을 나간 분
    assert seed["ids"]["나담당"] not in went     # 검토중단


def test_수가_그대로면_되묻지_않는다(client, db, seed):
    """달라졌을 때만 묻는다. 늘 물으면 사람이 확인창을 읽지 않게 된다."""
    item = _reserve(client, seed)
    r = client.post(f"/api/deals/queue/{item['item_id']}/start", json={"shown": 4})
    assert r.status_code == 200, r.text
    assert r.json().get("ok") is True
    assert r.json()["total"] == 4


# ── ③ 다를 때 화면이 하는 말 ───────────────────────────────────────────────

def test_줄었을_때_확인창이_그_차이를_말한다(client, seed):
    """수만 두 개 늘어놓으면 무엇이 일어난 것인지 알 수 없다 — **왜** 까지 적는다."""
    from app.services import deal_queue, sheet_owner

    note = deal_queue.difference_note(24, 21, GROUP_A)
    assert "화면에는 24명 · 지금은 21명입니다" in note
    assert "3명이 줄었습니다" in note
    # 상태 이름을 손으로 적지 않는다 — 이름이 바뀌면 이 검사가 먼저 깨져야 한다.
    assert sheet_owner.STATUS_LABELS[sheet_owner.STATUS_PAUSED] in note
    assert "지금 기준 21명에게 보냅니다" in note


def test_늘었을_때도_같은_자리에서_말한다(client, seed):
    """줄어든 것만 말하면, 늘어난 회차는 조용히 더 많은 사람에게 나간다."""
    from app.services import deal_queue

    note = deal_queue.difference_note(21, 24, GROUP_A)
    assert "화면에는 21명 · 지금은 24명입니다" in note
    assert "3명이 늘었습니다" in note
    assert "지금 기준 24명에게 보냅니다" in note


def test_확인창_문구는_서버가_만든_것을_그대로_돌려준다(client, db, seed):
    """화면이 같은 말을 다시 지어내면 두 벌이 되고, 어긋나도 아무도 모른다."""
    from app.services import deal_queue

    item = _reserve(client, seed)
    _move(db, seed["ids"]["가담당"], status="paused")
    r = client.post(f"/api/deals/queue/{item['item_id']}/start", json={"shown": 4})
    assert r.json()["message"] == deal_queue.difference_note(4, 3, GROUP_A)


# ── ④ 보낼 사람이 없거나, 이미 누른 줄 ─────────────────────────────────────

def test_지금_보낼_사람이_없으면_막는다(client, db, seed):
    """0명짜리 발송 목록을 만들어 두면, 나간 줄 알고 다음 일로 넘어간다."""
    item = _reserve(client, seed)
    for name in ("가담당", "나담당", "다담당", "라담당"):
        _move(db, seed["ids"][name], status="paused")
    r = client.post(f"/api/deals/queue/{item['item_id']}/start",
                    json={"shown": 4, "confirmed": True})
    assert r.status_code == 400
    assert "보낼 수 있는" in r.json()["detail"]


def test_같은_예약을_두_번_시작하지_못한다(client, seed):
    """창을 두 개 열어 두면 실제로 두 번 누르게 된다 — 두 번 나가면 되돌릴 수 없다."""
    item = _reserve(client, seed)
    assert client.post(f"/api/deals/queue/{item['item_id']}/start",
                       json={"shown": 4}).status_code == 200
    r = client.post(f"/api/deals/queue/{item['item_id']}/start",
                    json={"shown": 4, "confirmed": True})
    assert r.status_code == 400
    assert "시작함" in r.json()["detail"]


def test_취소한_예약은_시작되지_않는다(client, seed):
    item = _reserve(client, seed)
    assert client.post(f"/api/deals/queue/{item['item_id']}/cancel").status_code == 200
    r = client.post(f"/api/deals/queue/{item['item_id']}/start", json={"shown": 4})
    assert r.status_code == 400


def test_취소해도_줄은_남는다(client, db, users, seed):
    """지우면 무엇을 세워 뒀다가 접었는지가 사라져, 안 나간 이유를 못 찾는다."""
    from app.services import deal_queue

    item = _reserve(client, seed)
    client.post(f"/api/deals/queue/{item['item_id']}/cancel")
    rows = _rows(db, users)
    assert len(rows) == 1
    assert rows[0]["status"] == deal_queue.STATUS_CANCELED
    assert rows[0]["status_label"] == "취소"
    # 끝난 줄에는 오늘의 수를 적지 않는다 — 그때의 수와 나란히 서면 어느 쪽이
    # 그날의 수인지 알 수 없다.
    assert rows[0]["target_count"] is None


def test_남의_예약은_보이지도_눌리지도_않는다(client, db, users, seed):
    """번호만 바꿔 가며 남이 무엇을 예약해 두었는지 알아낼 수 있으면 안 된다."""
    from app.models import DealQueueItem

    theirs = DealQueueItem(user_id=users["u2"].id, group_name=GROUP_A,
                           title="남의 예약")
    db.add(theirs)
    db.commit()
    assert client.post(f"/api/deals/queue/{theirs.id}/start",
                       json={"shown": 1}).status_code == 404
    assert client.post(f"/api/deals/queue/{theirs.id}/cancel").status_code == 404
    assert [r["id"] for r in _rows(db, users)] == []


# ── ⑤ `(그룹 없음)` 도 한 줄로 선다 ────────────────────────────────────────

def test_그룹_없음_줄도_똑같이_서고_보낸다(client, db, users, seed):
    """빼면 그룹이 빈 분들은 이 화면을 통해 영영 아무것도 못 받는다."""
    from app.services import deal_queue

    item = _reserve(client, seed, group="")
    row = _rows(db, users)[0]
    assert row["group_label"] == deal_queue.EMPTY_GROUP_LABEL
    assert row["no_group"] is True
    assert row["target_count"] == 2          # 마담당 · 바담당

    r = client.post(f"/api/deals/queue/{item['item_id']}/start", json={"shown": 2})
    assert r.status_code == 200, r.text
    assert r.json()["total"] == 2


def test_그룹_없음_줄은_그룹을_채우라고_알려_준다(client, seed):
    """빼지 않는 대신, **그룹을 채우면 맞춤 기업을 붙일 수 있다**는 것이 보여야 한다."""
    _reserve(client, seed, group="")
    html = client.get("/deals").text
    assert "그룹을 안 정해 두신 분들입니다" in html
    assert "그룹마다 다른 기업을 붙일 수 있습니다" in html


def test_큐의_빈_그룹과_표_필터의_빈_그룹은_같은_사람을_고른다(db, users, seed):
    """말은 다르다(`(그룹 없음)` · `(비어 있음)`). **고르는 값이 같아야** 한다.

    두 화면이 같은 조건으로 고른 사람이 달라지면, 필터로 열일곱 명을 보고
    예약한 줄이 다른 사람에게 나간다. 고르는 값은 양쪽 다 빈 문자열이라
    글자와는 상관이 없다 — 그 사실을 여기서 못박는다.
    """
    from app.services import deal_queue, sheet_owner

    people = sheet_owner.recipients(db, users["u1"])
    by_queue = {c.id for c in deal_queue.targets(db, users["u1"], "")}
    # 표 필터가 `(비어 있음)` 으로 고르는 것 = 그룹 값이 빈 사람(`filters.js`).
    by_filter = {c.id for c in people if not sheet_owner.group_of(c)}
    assert by_queue == by_filter
    assert deal_queue.EMPTY_GROUP_LABEL != sheet_owner.EMPTY_GROUP  # 말은 다르다


# ── ⑥ 예약이 회차 이력을 오염시키지 않는다 ────────────────────────────────

def test_예약은_회차로_세어지지_않는다(client, db, users, seed):
    """`DealBatch` 에 칸 하나를 더하지 않은 이유. 나눔이 풀리면 여기가 깨진다.

    `deal_history.last_sent_map` 은 `deal_batches` 를 **조건 없이 통째로** 훑는다
    (WHERE 가 아예 없다). 예약 줄이 그 표에 섞이면 아직 안 보낸 기업이
    `최근에 소개함` 으로 찍혀, 발송 화면의 기업 목록에서 밀려난다.
    """
    from app.models import DealBatch
    from app.services import deal_history
    from sqlalchemy import select

    _reserve(client, seed)
    db.expire_all()
    assert db.execute(select(DealBatch)).scalars().all() == []
    assert deal_history.last_sent_map(db) == {}


def test_예약에_든_기업은_삭제가_막히되_회차와_다른_말을_한다(client, db, users, seed):
    """예약은 기록이 아니라 계획이다 — "이미 발송한 회차에 들어 있다" 는 거짓말이다.

    그렇다고 그냥 지우면 예약이 없는 기업을 가리킨 채 남아, [시작] 을 누르는
    순간 `기업 … 없음` 으로 죽는다. 그때는 왜 죽는지 화면에서 알 길이 없다.
    """
    from app.models import User

    _reserve(client, seed, companies=[seed["company_ids"][0]])
    admin = db.get(User, users["u1"].id)
    admin.role = "admin"
    db.commit()

    r = client.delete(f"/api/companies/{seed['company_ids'][0]}")
    assert r.status_code == 400, r.text
    detail = r.json()["detail"]
    assert "예약" in detail
    assert "발송한 회차" not in detail        # 보냈다고 말하면 안 된다
    # 예약에 없는 기업은 그대로 지워진다.
    assert client.delete(f"/api/companies/{seed['company_ids'][1]}").status_code == 200


def test_취소한_예약은_기업_삭제를_막지_않는다(client, db, users, seed):
    """접어 둔 계획이 기업을 인질로 잡고 있으면 안 된다."""
    from app.models import User

    item = _reserve(client, seed, companies=[seed["company_ids"][0]])
    client.post(f"/api/deals/queue/{item['item_id']}/cancel")
    admin = db.get(User, users["u1"].id)
    admin.role = "admin"
    db.commit()
    assert client.delete(f"/api/companies/{seed['company_ids'][0]}").status_code == 200


# ── ⑦ 화면이 실제로 그리는가 ───────────────────────────────────────────────

def test_화면이_예약_줄을_지금_수와_함께_그린다(client, db, seed):
    """`data-count` 가 **화면이 지금 말하고 있는 수**다.

    [시작] 은 이 값을 서버로 함께 보내고, 서버가 그때 다시 센 수와 다르면
    확인창을 띄운다. 속성 이름이 어긋나면 화면은 멀쩡한데 되묻는 일이 통째로
    사라진다 — 조용히 다른 수로 나간다.
    """
    _reserve(client, seed)
    html = client.get("/deals").text
    assert 'id="queue-list"' in html
    assert 'class="queue-row' in html
    assert 'data-count="4"' in html
    assert "queue-start" in html
    assert "queue-cancel" in html
    assert f'>{GROUP_A}<' in html or GROUP_A in html


def test_같은_그룹에_예약이_둘이면_두_번_나간다고_말한다(client, db, seed):
    """막지는 않는다 — 그룹마다 다른 기업을 다른 날 보내려고 만든 큐다.

    막으면 이 기능의 쓰임 자체를 막는 것이 된다. 대신 **같은 분들께 두 번
    나간다**는 것은 화면이 말해야 한다.
    """
    _reserve(client, seed)
    _reserve(client, seed, companies=[seed["company_ids"][1]])
    html = client.get("/deals").text
    assert "대기 중인 예약이" in html
    assert "2번 나갑니다" in html


def test_시작한_줄은_그날_나간_수와_진행_링크를_남긴다(client, db, users, seed):
    """보낸 뒤 그 줄이 무엇이 되었는지 화면에서 읽혀야 한다."""
    item = _reserve(client, seed)
    r = client.post(f"/api/deals/queue/{item['item_id']}/start", json={"shown": 4})
    job_id = r.json()["job_id"]

    row = _rows(db, users)[0]
    assert row["status_label"] == "시작함"
    assert row["sent_total"] == 4
    assert row["job_id"] == job_id
    html = client.get("/deals").text
    assert f'href="/jobs/{job_id}"' in html


# ── ⑧ 브라우저 쪽 ──────────────────────────────────────────────────────────
#
# 확인창을 띄우는 것도, 화면에 적혀 있던 수를 함께 보내는 것도 브라우저에
# 있다. 그 규칙을 파이썬으로 다시 구현하면 두 벌이 되어 어긋나도 모르므로,
# deals.js 를 **그대로 실행**해 본다(`tests/js/deals_queue_test.js`).

def test_시작_단추가_화면의_수를_함께_보내고_서버의_말을_그대로_띄운다():
    """★ 화면이 `data-count` 를 안 보내면 서버는 달라진 것을 알 방법이 없다.

    그러면 되묻는 일이 통째로 사라지고, 조용히 다른 수로 나간다 — 몇 명에게
    나갔는지 아무도 모르는 채로 되돌릴 수 없는 일이 끝나 있다. 확인창의 말도
    **서버가 만든 것을 그대로** 띄워야 한다: 화면이 다시 지어내면 두 벌이 되고,
    사람이 마지막으로 읽는 자리라 어긋나도 아무도 모른다.
    """
    import shutil
    import subprocess
    from pathlib import Path

    node = shutil.which("node")
    if node is None:
        pytest.skip("node 미설치 — 브라우저 로직 테스트 생략 "
                    "(호스트에서 `node tests/js/deals_queue_test.js`)")
    js = Path(__file__).resolve().parent / "js" / "deals_queue_test.js"
    result = subprocess.run([node, str(js)], capture_output=True,
                            text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
