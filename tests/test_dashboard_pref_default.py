"""#26 — 대시보드 '내 투자사 선호' 의 기본 인원: 50 → 300.

사용자가 정했다(2026-10-16): 기본을 300 으로, 드롭다운은 그대로. **목록에
오르는 사람은 그대로다** — IR 자료를 달라고 한 투자사만 선다.

이름·회사는 전부 지어낸 값이다 — 저장소가 공개다.
"""
from __future__ import annotations

import json

import pytest

from .conftest import DEMO_PASSWORD

SHEET = "내 명단"
REQUESTERS = 60          # 옛 기본(50)을 넘는 수 — 기본에서 다 보여야 한다
QUIET = 5                # 요청이 없는 분 — 기본을 올려도 목록에 안 선다


@pytest.fixture()
def world(db, users):
    from app.models import ContactActivity, SheetOwner, VcContact

    db.add(SheetOwner(label=SHEET, user_id=users["u1"].id))
    db.flush()
    made = []
    for i in range(REQUESTERS + QUIET):
        row = VcContact(user_id=users["u1"].id, source_sheet=SHEET,
                        name=f"요청샘플{i:02d}", firm="가나벤처스", channel_kakao=1,
                        kakao_room_name=f"샘플방{i}", room_verified="verified")
        db.add(row)
        made.append(row)
    db.flush()
    for row in made[:REQUESTERS]:
        db.add(ContactActivity(contact_id=row.id, kind="ir_request",
                               content="요청", happened_at="2026-09-03",
                               company_names=json.dumps(["샘플애그"],
                                                        ensure_ascii=False)))
    db.commit()
    return made


def _login(client):
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    return client


def _rank_count(body: str) -> int:
    tail = body.split('id="req-rank-count"')[1]
    return int(tail.split("<b>")[1].split("</b>")[0])


def test_the_default_is_300(client, world):
    from app.services import dashboard as dash

    assert dash.TOP_DEFAULT == 300
    # 기본은 고를 수 있는 값 안이어야 드롭다운이 그 값을 골라 보인다.
    assert dash.TOP_DEFAULT in dash.TOP_CHOICES
    body = _login(client).get("/").text
    assert 'value="300" selected' in body, "기본으로 300 이 골라져 있지 않다"
    assert 'value="50" selected' not in body


@pytest.mark.parametrize("path", ["/", "/dashboard"])
def test_both_screens_show_everyone_who_asked_by_default(client, world, path):
    """옛 기본(50)이면 60곳 중 50곳만 섰다 — 이제 기본에서 다 선다."""
    body = _login(client).get(path).text
    assert _rank_count(body) == REQUESTERS


def test_the_api_default_follows(client, world):
    """목록만 다시 받는 길(드롭다운을 바꿀 때)도 같은 기본을 쓴다."""
    rows = _login(client).get("/api/dashboard/top-requesters").json()["rows"]
    assert len(rows) == REQUESTERS


def test_people_who_never_asked_still_do_not_appear(client, world):
    """기본을 올려도 모집단은 그대로 — IR 자료를 달라고 한 분만."""
    rows = _login(client).get("/api/dashboard/top-requesters").json()["rows"]
    names = {r["name"] for r in rows}
    for row in world[REQUESTERS:]:
        assert row.name not in names, f"요청이 없는 {row.name} 이 목록에 섰다"


def test_the_dropdown_still_picks_fewer(client, world):
    body = _login(client).get("/?top=50").text
    assert 'value="50" selected' in body
    assert _rank_count(body) == 50
    rows = client.get("/api/dashboard/top-requesters?top=10").json()["rows"]
    assert len(rows) == 10
