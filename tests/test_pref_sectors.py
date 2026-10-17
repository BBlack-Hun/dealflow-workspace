"""투자사 선호분야 재분류(#30) — 키워드 분류 · 메모 분리 · 못 맞춘 조각 · 반영.

사람 · 회사 이름은 전부 지어낸 것이다 — 저장소가 공개다. 선호분야 글은 실제 값의
**모양**만 본떠 새로 적었다.
"""
from __future__ import annotations

import pytest

from tests.conftest import DEMO_PASSWORD


@pytest.fixture()
def resolver(db):
    from app.services import taxonomy as tx

    tx.ensure_seed(db)
    return tx.Resolver.load(db)


def _classify(value, resolver):
    from app.services import pref_sectors as ps

    return ps.classify(value, resolver)


# ── 1. 키워드 분류 ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("value, tokens", [
    ("로봇", ["로봇"]),
    ("딥테크", ["딥테크·제조"]),
    ("반도체, 소부장", ["반도체", "딥테크·제조"]),
    ("SaaS, AI 관련 기업", ["AI·SaaS·데이터"]),
    ("화장품 브랜드사", ["뷰티테크", "커머스·라이프스타일"]),
    ("바이오 (헬스케어/바이오소재 포함)", ["헬스케어·바이오", "바이오소재"]),
    ("이차전지, 방산", ["배터리", "국방기술"]),
    ("디지털 헬스", ["디지털헬스케어"]),                 # 띄어쓰기 무시
    ("의료기기", ["의료기기"]),                           # 긴 말이 `의료` 를 덮는다
    ("피지컬AI", ["로봇"]),                               # `AI` 가 따로 안 걸린다
    ("ESG,푸드,애그테크", ["ESG·푸드·애그테크"]),        # 줄 전체가 목록 이름 하나
    ("AI SaaS 데이터", ["AI·SaaS·데이터"]),
])
def test_목록의_말로_바꾼다(resolver, value, tokens):
    result = _classify(value, resolver)
    assert result.tokens == tokens
    assert result.after == ", ".join(tokens)
    assert result.moved == []


@pytest.mark.parametrize("value", [
    "핀테크·블록체인, 로봇",          # 고르는 창에서 대분류를 고르면 이렇게 적힌다
    "블록체인, DID·인증",
    "핀테크·블록체인, 공급망금융(SCF)",
    "ESG·푸드·애그테크, 콘텐츠·엔터테인먼트",
    "프롭테크·스마트시티, AI SaaS",
])
def test_목록대로_적힌_값은_다시_돌려도_그대로다(resolver, value):
    """가르는 글자(`·` `()`)가 든 이름을 반쪽으로 쪼개면 `블록체인` 이 소분류로
    따로 붙거나 `DID` · `인증` 두 조각이 된다 — 목록대로 적힌 값을 망친다."""
    result = _classify(value, resolver)
    assert result.after == value
    assert not result.changes and result.unmatched == []


def test_이름_안의_가운뎃점은_날짜와_함께_있어도_안_쪼갠다(resolver):
    result = _classify("핀테크·블록체인 6/17", resolver)
    assert result.tokens == ["핀테크·블록체인"]
    assert result.moved == ["핀테크·블록체인 6/17"]


@pytest.mark.parametrize("value", ["PAID 고객", "VISIT 기록", "Pre IPO"])
def test_라틴_낱말은_다른_낱말_안에서_안_걸린다(resolver, value):
    result = _classify(value, resolver)
    assert "AI·SaaS·데이터" not in result.tokens
    assert "IP" not in result.tokens


# ── 2. 메모로 옮기는 것 ─────────────────────────────────────────────────────

@pytest.mark.parametrize("value", [
    "B",                        # 그룹 표시
    "b그룹",
    "Seed Pre A",               # 단계 말
    "Pre IPO",
    "Series C ~",
    "방 나가셨음",               # 카톡방 기록
    "보통딜",
    "6/17",                     # 날짜만
    "Pre-Value 150-300억 선호",  # 금액
])
def test_분야가_아닌_글은_메모로_옮기고_칸은_빈다(resolver, value):
    result = _classify(value, resolver)
    assert result.tokens == []
    assert result.after == ""
    assert result.moved == [value]
    assert result.changes


def test_날짜가_붙은_줄은_분야를_뽑고_그_줄을_통째로_메모로(resolver):
    result = _classify("로봇, AI, 소부장 7/7", resolver)
    assert result.tokens == ["로봇", "AI·SaaS·데이터", "딥테크·제조"]
    assert result.moved == ["로봇, AI, 소부장 7/7"], "날짜만 떼어 옮기면 무슨 날짜인지 모른다"


def test_뒤집는_말이_있는_줄은_분야를_뽑지_않는다(resolver):
    result = _classify("바이오 제외", resolver)
    assert result.tokens == [] and result.moved == ["바이오 제외"]
    result = _classify("로봇\nAI 솔루션은 투자하지 않음", resolver)
    assert result.tokens == ["로봇"]
    assert result.moved == ["AI 솔루션은 투자하지 않음"]


def test_여러_줄은_줄마다_본다(resolver):
    value = "6/17 \n반도체나 소부장 위주\n\n매출 100억 이상"
    result = _classify(value, resolver)
    assert result.tokens == ["반도체", "딥테크·제조"]
    # 분야 말뿐인 줄(`위주` 는 뜻을 더하지 않는 말)은 칸에만 남고 메모로 안 간다.
    assert result.moved == ["6/17", "매출 100억 이상"]


def test_메모_줄과_함께_있는_모르는_줄은_같이_옮긴다(resolver):
    result = _classify("바이오마커 기반 제약 기업\nex. 가상바이오텍", resolver)
    assert "ex. 가상바이오텍" in result.moved
    assert "가상바이오텍" not in result.after


# ── 3. 못 맞춘 조각 ─────────────────────────────────────────────────────────

def test_모르는_말_하나뿐이면_칸에_남기고_못_맞춘_조각으로_띄운다(resolver):
    result = _classify("스포츠", resolver)
    assert result.after == "스포츠"
    assert result.unmatched == ["스포츠"]
    assert not result.changes, "그대로인 줄은 바뀌는 줄로 세면 안 된다"


def test_분야_목록_안의_모르는_말은_칸에_남는다(resolver):
    result = _classify("섬유/반도체/AI", resolver)
    assert result.after == "반도체, AI·SaaS·데이터, 섬유"
    assert result.unmatched == ["섬유"]


# ── 4. 메모 붙이기 ──────────────────────────────────────────────────────────

def test_메모_뒤에_표시를_달아_붙이고_두_번_붙이지_않는다():
    from app.services import pref_sectors as ps

    memo = ps.append_memo("통화 완료", ["Seed Pre A"])
    assert memo == "통화 완료\n[선호분야 칸에서 옮김] Seed Pre A"
    assert ps.append_memo(memo, ["Seed Pre A"]) == memo
    assert ps.append_memo(None, ["B"]) == "[선호분야 칸에서 옮김] B"


def test_옮긴_단계_말도_그룹_판정이_읽는다():
    """재분류로 메모에 간 `Pre IPO` 가 그룹 판정(`pref_group`)에서 사라지면 안 된다."""
    from types import SimpleNamespace

    from app.services import pref_group as pg

    row = SimpleNamespace(sectors=None, round_size=None, stages=None,
                          memo="통화 완료\n[선호분야 칸에서 옮김] Pre IPO")
    assert pg.decide(row).group == pg.LATE


# ── 5. 반영 ─────────────────────────────────────────────────────────────────

def _contact(db, users, name, sectors, **kw):
    from app.models import VcContact

    row = VcContact(user_id=users["u1"].id, name=name, firm="가상벤처스",
                    sectors=sectors, **kw)
    db.add(row)
    db.commit()
    return row


def test_반영하면_백업이_한_번_남고_메모가_붙고_라운드는_그대로다(db, users):
    from app.services import pref_sectors as ps
    from app.services import taxonomy as tx

    tx.ensure_seed(db)
    a = _contact(db, users, "가나다", "로봇, AI 6/17", memo="통화 완료",
                 round_size="Seed 10억")
    b = _contact(db, users, "라마바", "B")
    empty = _contact(db, users, "사아자", "")
    none = _contact(db, users, "차카타", None)

    result = ps.apply(db)
    assert result["applied"] == 2 and result["moved"] == 2
    for row in (a, b, empty, none):
        db.refresh(row)
    assert a.sectors == "로봇, AI·SaaS·데이터"
    assert a.sectors_raw == "로봇, AI 6/17"
    assert a.memo == "통화 완료\n[선호분야 칸에서 옮김] 로봇, AI 6/17"
    assert a.round_size == "Seed 10억", "라운드 사이즈는 건드리지 않는다(③ 대기)"
    assert b.sectors is None and b.sectors_raw == "B"
    assert b.memo == "[선호분야 칸에서 옮김] B"
    assert empty.sectors == "" and empty.sectors_raw is None, "빈 칸을 건드렸다"
    assert none.sectors is None and none.sectors_raw is None

    # 다시 돌리면 바꿀 것이 없고, 백업도 메모도 그대로다.
    again = ps.preview(db)
    assert again["counts"]["changes"] == 0
    ps.apply(db)
    db.refresh(a)
    assert a.sectors_raw == "로봇, AI 6/17"
    assert a.memo.count("[선호분야 칸에서 옮김]") == 1


def test_고른_투자사만_반영한다(db, users):
    from app.services import pref_sectors as ps
    from app.services import taxonomy as tx

    tx.ensure_seed(db)
    a = _contact(db, users, "가나다", "딥테크")
    b = _contact(db, users, "라마바", "B")
    ps.apply(db, [a.id])
    db.refresh(a)
    db.refresh(b)
    assert a.sectors == "딥테크·제조"
    assert b.sectors == "B"
    with pytest.raises(tx.TaxonomyError):
        ps.apply(db, [a.id])            # 이미 반영돼 계획에 없다


def test_이어진_딜_소싱_줄도_같은_칸이라_따라간다(db, users):
    """`선호 투자분야` 와 딜 소싱의 `투자분야` 는 같은 칸이다(`sourcing_sync`)."""
    from app.models import SourcingContact
    from app.services import pref_sectors as ps
    from app.services import sourcing_sync, taxonomy as tx

    tx.ensure_seed(db)
    a = _contact(db, users, "가나다", "딥테크")
    linked = SourcingContact(bucket=sourcing_sync.SYNC_BUCKET, name="가나다",
                             vc_contact_id=a.id, sectors="딥테크")
    db.add(linked)
    db.commit()
    ps.apply(db)
    db.refresh(linked)
    assert linked.sectors == "딥테크·제조"


def test_미리보기는_사람마다_전_후_메모_못_맞춘_조각을_준다(client, db, users):
    users["u2"].role = "admin"
    db.commit()
    client.post("/login", data={"phone": "01000000002", "password": DEMO_PASSWORD})
    _contact(db, users, "가나다", "로봇, 스포츠\n6/17 통화")
    data = client.get("/api/taxonomy/pref-sectors").json()
    row = data["rows"][0]
    assert row["before"] == "로봇, 스포츠\n6/17 통화"
    assert row["after"] == "로봇, 스포츠"
    assert row["moved"] == ["6/17 통화"]
    assert row["unmatched"] == ["스포츠"]
    assert row["owner"] == users["u1"].name
    done = client.post("/api/taxonomy/pref-sectors", json={"all": True}).json()
    assert done["applied"] == 1 and done["counts"]["changes"] == 0
