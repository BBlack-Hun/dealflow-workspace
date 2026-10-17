"""IR 기업 현황 정리 — 목록대로 맞추기 · 빈 대분류 제안 · 고른 것만 반영 · 백업 한 번.

기업 이름 · 소개는 전부 지어낸 것이다 — 저장소가 공개다.
"""
from __future__ import annotations

import pytest

from tests.conftest import DEMO_PASSWORD


@pytest.fixture()
def seeded(db):
    from app.services import taxonomy as tx

    tx.ensure_seed(db)
    return db


def _company(db, name, major, minor, one_liner=None):
    from app.models import IrCompany

    row = IrCompany(name=name, sector_major=major, sector_minor=minor,
                    one_liner=one_liner)
    db.add(row)
    db.commit()
    return row


def _rows(db):
    from app.services import ir_sector_cleanup as c

    return {r.name: r for r in c.plan(db).rows}


# ── 1. 규칙 ─────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("major, minor, want_major, want_minor", [
    # 오탈자 · 옛 이름
    ("헬스케어·바이오", "신약개", "헬스케어·바이오", "신약개발"),
    ("콘텐츠·엔터테인먼트", "비추얼휴먼, 게임", "콘텐츠·엔터테인먼트", "버추얼휴먼, 게임"),
    ("프롭테크·스마트시티", "건물 빌딩 관리", "프롭테크·스마트시티", "건물관리 SaaS"),
    ("뷰티", None, "커머스·라이프스타일", ""),
    ("물류", "라스트마일", "모빌리티·물류", "라스트마일"),
    # 대분류 옮김 — 소분류가 목록에서 다른 대분류 아래
    ("AI·SaaS·데이터", "첨단소재", "딥테크·제조", "첨단소재"),
    ("헬스케어·바이오", "뷰티테크", "커머스·라이프스타일", "뷰티테크"),
    ("커머스·라이프스타일", "버추얼휴먼", "콘텐츠·엔터테인먼트", "버추얼휴먼"),
    ("모빌리티·물류", "배터리", "딥테크·제조", "배터리"),
    # 철자 · 구분 기호 · 목록대로 나눔
    ("AI SaaS 데이터", "생성형AI / AI SaaS", "AI·SaaS·데이터", "생성형AI, AI SaaS"),
    ("딥테크·제조", "광학·센서", "딥테크·제조", "광학, 센서"),
    ("커머스·라이프스타일", "여행/레저", "커머스·라이프스타일", "여행, 레저"),
    # 빈 대분류인데 소분류가 목록에 있다 — 규칙대로 채운다
    (None, "DID·인증", "핀테크·블록체인", "DID·인증"),
])
def test_정리_규칙(seeded, major, minor, want_major, want_minor):
    from app.services import ir_sector_cleanup as c

    _company(seeded, "가상기업", major, minor)
    row = _rows(seeded)["가상기업"]
    assert (row.new_major, row.new_minor) == (want_major, want_minor)
    assert row.kind == c.KIND_FIX
    assert row.reasons, "까닭이 비었다 — 미리보기가 왜 바뀌는지 말해야 한다"


def test_소분류가_두_대분류에_걸치면_지금_대분류를_지킨다(seeded):
    _company(seeded, "가상기업", "모빌리티·물류", "EV충전, 배터리")
    assert "가상기업" not in _rows(seeded), "괜히 옮겼다"


def test_목록대로인_기업은_안_뜬다(seeded):
    _company(seeded, "가상기업", "딥테크·제조", "로봇, 반도체")
    _company(seeded, "가상기업2", None, None, one_liner=None)
    assert _rows(seeded) == {}


def test_시험용_대분류는_정리_대상으로만_띄운다(seeded):
    from app.services import ir_sector_cleanup as c

    _company(seeded, "가상시험", "테스트", "테스트1")
    result = c.plan(seeded)
    assert not result.rows
    assert [f["name"] for f in result.flagged] == ["가상시험"]


def test_목록에_없는_말은_그대로_두고_따로_센다(seeded):
    from app.services import ir_sector_cleanup as c

    _company(seeded, "가상기업", "가상대분류", "가상소분류")
    result = c.plan(seeded)
    assert not result.rows
    assert result.unknown_majors == {"가상대분류": 1}
    assert result.unknown_minors == {"가상소분류": 1}


def test_설명_글로_찬_소분류는_쉼표도_안_고친다(seeded):
    _company(seeded, "가상기업", None, "온라인 , 오프라인 교육")
    row = _rows(seeded)["가상기업"]
    assert row.new_minor == "온라인 , 오프라인 교육"
    assert row.new_major == "에듀테크·HR테크"       # 소분류 글의 `교육`


# ── 2. 빈 대분류 제안 ───────────────────────────────────────────────────────

def test_빈_대분류에는_한_줄_소개로_제안을_붙이고_미리_고르지_않는다(seeded):
    from app.services import ir_sector_cleanup as c

    _company(seeded, "가상팜", None, None,
             one_liner="스마트팜 기반 친환경 작물 재배 | 매출 3억")
    row = _rows(seeded)["가상팜"]
    assert row.kind == c.KIND_SUGGEST
    assert row.new_major == "ESG·푸드·애그테크"
    assert row.as_dict()["checked"] is False, "제안을 미리 골라 두었다"
    assert any("한 줄 소개" in r for r in row.reasons)


def test_자리채움_글에는_제안하지_않는다(seeded):
    from app.services import ir_sector_cleanup as c

    _company(seeded, "가상기업", None, None, one_liner="회사정보 검색안됨")
    result = c.plan(seeded)
    assert not result.rows
    assert [n["name"] for n in result.no_suggestion] == ["가상기업"]


# ── 3. 반영 ─────────────────────────────────────────────────────────────────

def test_고른_것만_반영하고_원래_값은_한_번만_남는다(seeded):
    from app.services import ir_sector_cleanup as c

    a = _company(seeded, "가상A", "AI·SaaS·데이터", "첨단소재")
    b = _company(seeded, "가상B", "헬스케어·바이오", "신약개")
    result = c.apply(seeded, [{"id": a.id}])
    assert result["applied"] == 1
    seeded.refresh(a)
    seeded.refresh(b)
    assert (a.sector_major, a.sector_minor) == ("딥테크·제조", "첨단소재")
    assert (a.sector_major_raw, a.sector_minor_raw) == ("AI·SaaS·데이터", None)
    assert b.sector_minor == "신약개", "안 고른 기업이 바뀌었다"

    # 다시 돌려도 백업은 그대로다 — 손으로 되돌린 뒤 다시 정리해 본다.
    a.sector_major = "AI·SaaS·데이터"
    seeded.commit()
    c.apply(seeded, [{"id": a.id}])
    seeded.refresh(a)
    assert a.sector_major_raw == "AI·SaaS·데이터"


def test_빈_대분류를_채우면_빈_백업이_남는다(seeded):
    from app.services import ir_sector_cleanup as c

    a = _company(seeded, "가상A", None, "DID·인증")
    c.apply(seeded, [{"id": a.id}])
    seeded.refresh(a)
    assert a.sector_major == "핀테크·블록체인"
    assert a.sector_major_raw == "", "비어 있었다는 것을 남겨야 다음 판이 덮지 않는다"


def test_제안_줄은_관리자가_고른_대분류로_넣는다(seeded):
    from app.services import ir_sector_cleanup as c
    from app.services import taxonomy as tx

    a = _company(seeded, "가상팜", None, None, one_liner="스마트팜 운영사")
    with pytest.raises(tx.TaxonomyError):
        c.apply(seeded, [{"id": a.id, "major": "목록에 없는 대분류"}])
    c.apply(seeded, [{"id": a.id, "major": "모빌리티·물류"}])
    seeded.refresh(a)
    assert a.sector_major == "모빌리티·물류"


def test_규칙_줄은_화면이_보낸_대분류를_안_믿는다(seeded):
    from app.services import ir_sector_cleanup as c

    a = _company(seeded, "가상A", "AI·SaaS·데이터", "첨단소재")
    c.apply(seeded, [{"id": a.id, "major": "핀테크·블록체인"}])
    seeded.refresh(a)
    assert a.sector_major == "딥테크·제조"


def test_그_사이_바뀌어_계획에서_빠진_기업은_건너뛴다(seeded):
    from app.services import ir_sector_cleanup as c
    from app.services import taxonomy as tx

    a = _company(seeded, "가상A", "딥테크·제조", "로봇")         # 바꿀 것 없음
    with pytest.raises(tx.TaxonomyError):
        c.apply(seeded, [{"id": a.id}])


# ── 4. 화면 · 권한 ─────────────────────────────────────────────────────────

def test_미리보기와_반영_길(client, db, users):
    users["u2"].role = "admin"
    db.commit()
    client.post("/login", data={"phone": "01000000002", "password": DEMO_PASSWORD})
    from app.services import taxonomy as tx

    tx.ensure_seed(db)
    a = _company(db, "가상A", "모빌리티·물류", "배터리")
    preview = client.get("/api/taxonomy/ir-cleanup").json()
    assert preview["counts"]["fix"] == 1
    assert preview["rows"][0]["new_major"] == "딥테크·제조"
    assert "딥테크·제조" in preview["majors"]
    db.expire_all()
    assert db.get(type(a), a.id).sector_major == "모빌리티·물류", "미리보기가 썼다"

    done = client.post("/api/taxonomy/ir-cleanup", json={"items": [{"id": a.id}]})
    assert done.status_code == 200, done.text
    assert done.json()["applied"] == 1
    assert done.json()["counts"]["fix"] == 0      # 다시 센 미리보기가 같이 온다
    db.expire_all()
    assert db.get(type(a), a.id).sector_major == "딥테크·제조"
