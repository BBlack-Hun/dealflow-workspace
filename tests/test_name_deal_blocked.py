"""기업명에 붙은 `딜소개 불가` 꼬리표 — 계약여부 `딜소개 불가` 와 **똑같이** 막는다.

팀은 딜소개 불가를 계약여부 칸보다 **기업명 꼬리표**로 먼저 적는다
(`[딜소개 불가/폐업]` · `(딜소개 불가 / 2027년 3분기 부터 딜소개 가능)` · `딜 소개불가`).
계약여부가 유료 · 미계약 그대로여도 이름에 꼬리표가 있으면

  · 발송 화면(/deals)에 아예 안 뜨고, 주소로 찔러도 발송 목록 · 예약이 안 선다
  · 세운 뒤 꼬리표가 붙으면 나가는 순간(발송 시작 · 예약 풀림) 대기 건이 취소된다
  · 채널 TOP 자동화 · LLM 추천 자료 · IR 요청 후보 이름 · IR 아웃리치에서 빠진다

계약여부 값은 그대로 둔다(유료 계약 같은 사실이 사라진다). 꼬리표 없는 기업은 그대로다.
스타트업 월간 발송(계약 기업에 주는 보고)은 계약여부로 고르는 그대로다.

이름은 전부 지어낸 값이다(공개 저장소).
"""
from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select

from tests.conftest import DEMO_PASSWORD

GROUP = "샘플군"

#: 운영에서 본 꼬리표 모양들 — 띄어쓰기 · 괄호가 제각각이다.
TAGGED_NAMES = [
    "샘플가 [딜소개 불가]",
    "샘플나 (딜소개 불가 / 2027년 3분기 부터 딜소개 가능)",
    "샘플다 딜 소개불가",
    "샘플라 [딜 소개 불가/폐업]",
    "샘플마딜소개불가",
]


# ── 판정 하나 ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("name", TAGGED_NAMES)
def test_꼬리표는_띄어쓰기와_괄호에_상관없이_걸린다(name):
    from app.routers.companies import name_blocked

    assert name_blocked(name)


@pytest.mark.parametrize("name", ["샘플기업", "샘플 딜소개 가능", "샘플 소개 불가", "", None])
def test_꼬리표가_없으면_안_걸린다(name):
    from app.routers.companies import name_blocked

    assert not name_blocked(name)


def test_계약여부_또는_이름_어느_쪽이든_딜소개_불가다():
    from app.models import IrCompany
    from app.routers.companies import deal_blocked

    # 이름 꼬리표만 — 계약여부는 유료 · 미계약 · 빈칸 그대로.
    for contract in ("paid", "none", "no", None):
        assert deal_blocked(IrCompany(name="샘플가 [딜소개 불가]", contract_status=contract))
    # 계약여부만 — 값이든 화면 말이든.
    for contract in ("blocked", "딜소개 불가", "딜소개불가"):
        assert deal_blocked(IrCompany(name="샘플기업", contract_status=contract))
    # 둘 다 아니면 그대로.
    for contract in ("paid", "none", "free", None):
        assert not deal_blocked(IrCompany(name="샘플기업", contract_status=contract))


def test_SQL_조건이_파이썬_판정과_같다(db):
    """화면 목록(SQL)과 발송 길(파이썬)이 갈리면 화면에 없는 기업이 나가거나 그 반대다."""
    from app.models import IrCompany
    from app.routers.companies import deal_blocked, deal_blocked_clause

    rows = [IrCompany(name=n, contract_status=c)
            for n in TAGGED_NAMES + ["샘플기업", "샘플 딜소개 가능"]
            for c in ("paid", "none", "no", None, "blocked", "딜소개 불가", "free")]
    db.add_all(rows)
    db.commit()

    hit = set(db.execute(select(IrCompany.id).where(deal_blocked_clause())).scalars())
    miss = set(db.execute(select(IrCompany.id).where(~deal_blocked_clause())).scalars())
    assert hit == {r.id for r in rows if deal_blocked(r)}
    assert miss == {r.id for r in rows if not deal_blocked(r)}
    assert hit and miss and not hit & miss


# ── 기업 · 담당자 ────────────────────────────────────────────────────────────

def _company(name, **kw):
    from app.models import IrCompany

    base = dict(sector_major="AI", one_liner=f"{name} 한 줄 소개", funding_total="30억",
                is_top_deal=1, received_at="2026-10-01")
    base.update(kw)
    return IrCompany(name=name, **base)


@pytest.fixture()
def seed(client, db, users):
    """u1 로그인 + 꼬리표만 붙은 기업 셋(계약은 유료 · 미계약 · 빈칸) + 멀쩡한 기업 하나 +
    카톡방이 등록된 담당자 하나."""
    from app.models import VcContact

    rows = {
        "paid": _company("샘플가 [딜소개 불가]", contract_status="paid"),
        "none": _company("샘플나 (딜소개 불가 / 2027년 3분기 부터 딜소개 가능)",
                         contract_status="none"),
        "no": _company("샘플다 딜 소개불가", contract_status="no"),
        "ok": _company("샘플바", contract_status="paid"),
    }
    contact = VcContact(
        user_id=users["u1"].id, name="샘플담당", title="심사역", firm="샘플벤처스",
        group_name=GROUP, connect_stage="connected", status="active",
        kakao_room_name="샘플담당 심사역님 샘플벤처스", room_verified="verified",
        channel_kakao=1, source_sheet="샘플 명단",
    )
    db.add_all(list(rows.values()) + [contact])
    db.commit()
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    rows["contact"] = contact
    return rows


TAGGED = ("paid", "none", "no")


def test_꼬리표_기업도_소개_가능_판정은_그대로다(seed):
    """`introducible`(내용이 갖춰졌는가)은 뜻이 다르다 — 막는 판정은 따로 선다."""
    assert all(seed[k].introducible for k in TAGGED + ("ok",))


# ── 발송 화면 ────────────────────────────────────────────────────────────────

def test_발송_화면에_꼬리표_기업이_안_뜬다(client, seed):
    html = client.get("/deals").text
    assert f'class="company-cb" value="{seed["ok"].id}"' in html
    for key in TAGGED:
        assert f'class="company-cb" value="{seed[key].id}"' not in html, key
        assert seed[key].name not in html, key


@pytest.mark.parametrize("key", TAGGED)
def test_주소로_찔러도_미리보기_발송_예약이_막힌다(client, db, seed, key):
    from app.models import DealQueueItem, SendJob

    ids = [seed["ok"].id, seed[key].id]
    for path, body in (("/api/deals/preview", {"contact_ids": [seed["contact"].id]}),
                       ("/api/deals/send", {"contact_ids": [seed["contact"].id],
                                            "title": "샘플 회차"}),
                       ("/api/deals/queue", {"group_name": GROUP, "title": "샘플 회차"})):
        res = client.post(path, json={"company_ids": ids, **body})
        assert res.status_code == 400, (path, res.text)
        assert "딜소개 불가" in res.json()["detail"], path
    # IR 자료 전달도 같은 길이다.
    res = client.post("/api/deals/send", json={
        "mode": "ir", "company_ids": [seed[key].id],
        "contact_ids": [seed["contact"].id], "title": "샘플 회차"})
    assert res.status_code == 400 and "딜소개 불가" in res.json()["detail"]
    db.expire_all()
    assert not db.execute(select(SendJob)).scalars().all()
    assert not db.execute(select(DealQueueItem)).scalars().all()


def test_꼬리표_없는_기업은_그대로_나간다(client, seed):
    res = client.post("/api/deals/send", json={
        "company_ids": [seed["ok"].id], "contact_ids": [seed["contact"].id],
        "title": "샘플 회차"})
    assert res.status_code == 200, res.text


def test_예약_뒤에_꼬리표가_붙으면_시작이_막힌다(client, db, seed):
    from app.models import DealQueueItem, SendJob

    item_id = client.post("/api/deals/queue", json={
        "group_name": GROUP, "company_ids": [seed["ok"].id], "title": "샘플 회차",
    }).json()["item_id"]
    seed["ok"].name = "샘플바 [딜소개 불가]"
    db.commit()

    res = client.post(f"/api/deals/queue/{item_id}/start", json={})
    assert res.status_code == 400 and "딜소개 불가" in res.json()["detail"], res.text
    db.expire_all()
    assert db.get(DealQueueItem, item_id).status == "waiting"
    assert not db.execute(select(SendJob)).scalars().all()


def test_세운_뒤_꼬리표가_붙으면_나가는_순간_취소된다(client, db, seed):
    """대기 목록(`draft`)을 세운 뒤 이름에 꼬리표가 붙었다 — [발송 시작] 에서 다시 본다."""
    from app.models import SendItem, SendJob

    res = client.post("/api/deals/send", json={
        "company_ids": [seed["ok"].id], "contact_ids": [seed["contact"].id],
        "title": "샘플 회차", "draft": True})
    assert res.status_code == 200, res.text
    job_id = res.json()["job_id"]
    seed["ok"].name = "샘플바 (딜 소개 불가)"
    db.commit()

    res = client.post(f"/api/jobs/{job_id}/start")
    assert res.status_code == 200, res.text
    assert res.json()["requeued"] == 0
    db.expire_all()
    job = db.get(SendJob, job_id)
    assert job.status == "canceled"
    items = db.execute(select(SendItem).where(SendItem.job_id == job_id)).scalars().all()
    assert items and all(i.status == "canceled" for i in items)
    assert all("딜소개 불가" in (i.error or "") for i in items)


def test_꼬리표_없는_대기_목록은_그대로_시작된다(client, db, seed):
    from app.models import SendJob

    res = client.post("/api/deals/send", json={
        "company_ids": [seed["ok"].id], "contact_ids": [seed["contact"].id],
        "title": "샘플 회차", "draft": True})
    job_id = res.json()["job_id"]
    res = client.post(f"/api/jobs/{job_id}/start")
    assert res.status_code == 200 and res.json()["requeued"] == 1, res.text
    db.expire_all()
    assert db.get(SendJob, job_id).status == "queued"


# ── 자동 발송 · 추천 · 후보 이름 ─────────────────────────────────────────────

def test_채널_TOP_자동화가_꼬리표_기업을_고르지_않는다(db, seed):
    from app.services.automations import channel_top

    picked, _skipped = channel_top.pick(db, date(2026, 10, 14), 10, 90, test=False)
    assert [c.id for c in picked] == [seed["ok"].id]


def test_LLM_추천_자료에서_꼬리표_기업이_빠진다(db, seed):
    from app.services import llm_brief

    ids = {row["id"] for row in llm_brief.companies(db)}
    assert ids == {llm_brief.company_ref(seed["ok"].id)}


def test_IR_요청_후보_이름에서_꼬리표_기업이_빠진다(db, seed):
    from app.routers.ir import _company_names

    assert _company_names(db) == [seed["ok"].name]


def test_월간_발송_대상은_계약여부로_고른다(db, seed):
    """스타트업 월간 발송(A5)은 딜 소개가 아니라 **계약 기업에 주는 보고**다 — 이름 꼬리표로
    빼지 않는다(대상은 `ir_monthly.contracted` 한 곳, 폐업만 이름으로 뺀다)."""
    from app.services import ir_monthly

    ids = {c.id for c in ir_monthly.contracted(db)}
    assert {seed["paid"].id, seed["ok"].id} <= ids


# ── IR 아웃리치(안내 카톡) ───────────────────────────────────────────────────

def test_IR_아웃리치가_꼬리표_기업을_딜소개_불가로_뺀다(db, seed):
    from app.services import ir_outreach

    for key in TAGGED:
        company = seed[key]
        company.kakao_room_name = f"{company.name} 방"
        company.room_verified = "verified"
        assert ir_outreach.is_blocked(company), key
        assert ir_outreach.refusal(db, company) == "딜소개 불가", key
        # 방 찾기 · 확인에도 안 싣는다.
        company.room_verified = "unverified"
        assert ir_outreach.room_task(company) == "", key
    assert not ir_outreach.is_blocked(seed["ok"])
