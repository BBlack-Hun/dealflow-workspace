"""`딜 소개 문구` 의 **기본은 사용자 정의 문구**다(사용자 요청).

## 왜 이 검사가 있나

이 칸은 한동안 **자동 조합이 기본**이었다. 조합값과 글자가 같은 줄(`AUTO`)은
스타트업DB 를 고칠 때마다 저절로 다시 쓰였고, 칸을 비워서 저장하면 조합값이
도로 들어왔다. 사용자가 그 기본을 뒤집었다 — "기본 값은 사용자 정의 문구
사용".

뒤집는 일은 **글자를 덮어쓰는 규칙을 손대는 일**이라 조용히 잘못되면 되돌릴 수
없다. 운영 344곳 중 **293곳에 사람이 쓴 문구**가 들어 있다. 그래서 한 줄짜리
표본이 아니라 **같은 크기·같은 분포의 사본**으로 잰다: 한 줄에서만 나는 고장은
한 줄짜리 표본으로는 안 잡힌다.

## 무엇을 못 박나

1. 재료를 전부 고쳐 저장해도 **293곳이 한 글자도 안 바뀐다**
2. 조합값과 같아서 예전에 '자동' 으로 읽히던 줄도 **저절로는 안 바뀐다**
3. 비워서 저장하면 **빈 채로** 남는다(비우는 것도 사람의 결정이다)
4. 그래도 **고르면 들어간다** — 자동 조합을 없앤 것이 아니다

기업명·문구는 전부 가상값이다 — 저장소가 공개다.
"""
from __future__ import annotations

import pytest

from .conftest import DEMO_PASSWORD

# 운영 344곳의 분포 그대로.
MANUAL = 293       # 사람이 쓴 문구가 들어 있는 곳 ★ 이 검사가 지키는 곳
AUTO_LIKE = 6      # 조합값과 글자까지 같은 곳(예전 규칙에서 저절로 따라오던 줄)
EMPTY = 45         # 아직 비어 있는 곳
TOTAL = MANUAL + AUTO_LIKE + EMPTY

FAKE = ["가나헬스", "나다물류", "다라소재", "라마핀테크", "마바에듀",
        "바사푸드", "사아로보", "아자바이오", "자차모빌", "차카에너지"]


@pytest.fixture()
def logged_in(client, users):
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    return client


@pytest.fixture()
def replica(db):
    """운영과 같은 크기의 사본. `{id: 심어 둔 문구}` 와 함께 돌려준다."""
    from app.models import IrCompany

    rows = {}
    for i in range(TOTAL):
        name = f"샘플{i:03d}{FAKE[i % len(FAKE)]}"
        desc = f"{FAKE[i % len(FAKE)]} 기반 솔루션 {i}"
        if i < MANUAL:
            # 빈 칸은 `None` 과 `""` 를 섞는다 — 운영에 둘 다 있다.
            line = f"사람이 다듬어 쓴 소개 {i} | 매출 {i % 30 + 1}억"
        elif i < MANUAL + AUTO_LIKE:
            line = desc                     # 재료 하나뿐이라 조합값이 곧 이 글자다
        else:
            line = None if i % 2 else ""
        row = IrCompany(name=name, business_desc=desc, one_liner=line,
                        revenue_2024=f"{i % 9 + 1}억")
        db.add(row)
        rows[name] = row
    db.commit()
    return {row.id: row.one_liner for row in rows.values()}


def _values(db) -> dict:
    from app.models import IrCompany

    return {row.id: row.one_liner
            for row in db.query(IrCompany).order_by(IrCompany.id).all()}


def test_재료를_다_고쳐도_사람이_쓴_293곳이_그대로다(logged_in, db, replica):
    """제일 나쁜 고장이다 — 344줄을 훑는 동안 손글씨가 소리 없이 사라진다."""
    before = dict(replica)
    assert sum(1 for v in before.values() if v and "사람이 다듬어" in v) == MANUAL

    # 조합에 쓰이는 칸을 **전부** 건드린다. 한 칸만 고쳐도 예전 규칙에서는
    # 조합이 다시 돌았다.
    for cid in before:
        r = logged_in.patch(f"/api/companies/{cid}",
                            json={"revenue_2025": "20억", "funding_total": "40",
                                  "raise_target": "10", "pre_value": "120",
                                  "competitiveness": "TIPS 선정"})
        assert r.status_code == 200, r.text

    db.expire_all()
    after = _values(db)
    changed = {cid: (before[cid], after[cid])
               for cid in before if (before[cid] or "") != (after[cid] or "")}
    assert not changed, f"{len(changed)}곳이 저절로 바뀌었습니다: {list(changed)[:3]}"


def test_조합값과_같던_줄도_저절로는_안_바뀐다(logged_in, db, replica):
    """예전에는 이 줄들이 `AUTO` 로 읽혀 재료를 고칠 때마다 따라왔다."""
    from app.models import IrCompany

    auto_like = [cid for cid, line in replica.items()
                 if line and "사람이 다듬어" not in line]
    assert len(auto_like) == AUTO_LIKE, len(auto_like)

    for cid in auto_like:
        logged_in.patch(f"/api/companies/{cid}", json={"funding_total": "40"})

    db.expire_all()
    for cid in auto_like:
        assert db.get(IrCompany, cid).one_liner == replica[cid], \
            "고른 적 없는데 칸이 다시 쓰였다"


def test_비워서_저장하면_빈_채로_남는다(logged_in, db, replica):
    """예전에는 비워 보내는 것이 '자동 조합을 다시 넣어 달라' 는 뜻이었다."""
    from app.models import IrCompany

    cid = next(cid for cid, line in replica.items()
               if line and "사람이 다듬어" in line)
    logged_in.patch(f"/api/companies/{cid}", json={"one_liner": ""})
    db.expire_all()
    assert not (db.get(IrCompany, cid).one_liner or ""), "비웠는데 조합값이 들어왔다"


def test_빈_칸도_저절로_채워지지_않는다(logged_in, db, replica):
    """비어 있다는 이유로 채우면 그것도 '기본이 자동' 이다."""
    from app.models import IrCompany

    blanks = [cid for cid, line in replica.items() if not (line or "").strip()]
    assert len(blanks) == EMPTY, len(blanks)

    for cid in blanks:
        logged_in.patch(f"/api/companies/{cid}", json={"funding_total": "40"})

    db.expire_all()
    still = [cid for cid in blanks if (db.get(IrCompany, cid).one_liner or "").strip()]
    assert not still, f"{len(still)}곳이 저절로 채워졌습니다"


def test_고르면_들어간다(logged_in, db, replica):
    """자동 조합을 **없앤 것이 아니다** — 기본을 뒤집었을 뿐이다."""
    from app.models import IrCompany

    cid = next(cid for cid, line in replica.items()
               if line and "사람이 다듬어" in line)
    body = logged_in.get(f"/api/companies/{cid}/one-liner").json()
    assert body["origin"] == "manual"
    assert body["suggestion"], "만들 수 있는 줄을 안 알려 준다"

    logged_in.post(f"/api/companies/{cid}/one-liner")
    db.expire_all()
    assert db.get(IrCompany, cid).one_liner == body["suggestion"]


def test_화면이_기본을_말해_준다(logged_in, replica):
    """`딜 소개 문구` 머리글과, 자동 조합을 부르는 단추가 한 화면에 있어야 한다."""
    html = logged_in.get("/companies").text
    assert ">딜 소개 문구</th>" in html, "머리글 이름이 바뀌었습니다"
    assert "자동 조합으로 바꾸기" in html, "자동 조합을 부르는 단추가 없습니다"
    assert 'id="one-liner-preview"' in html, "무엇으로 바뀌는지 보여 줄 자리가 없습니다"
