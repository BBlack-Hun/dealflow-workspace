"""#181 — 투자사 관리 현황의 **명단 탭 차례**를 명단에 붙은 수(`SheetOwner.position`)로 정한다.

  1. 수가 있는 명단이 먼저, 작은 수부터. 수가 없는 명단은 지금까지의 차례
     (연결 완료 → 인원 → 이름)로 그 뒤에 선다 — 수를 안 넣으면 화면이 그대로다.
  2. 관리자의 `전체` 표도 줄을 **탭 차례대로** 묶는다. 같은 명단 안은 `그룹 → 이름` 그대로.

이름·회사는 전부 지어낸 값이다(공개 저장소).
"""
from __future__ import annotations

import re

import pytest

from .conftest import DEMO_PASSWORD

A, B, C = "샘플 명단 가", "샘플 명단 나", "샘플 명단 다"


@pytest.fixture()
def world(db, users):
    from app.models import SheetOwner, VcContact
    from app.services import contact_columns as cc

    u1, u2 = users["u1"], users["u2"]
    u1.role = "admin"
    for label, owner in ((A, u2), (B, u1), (C, u2)):
        db.add(SheetOwner(label=label, user_id=owner.id, layout=cc.INVESTOR, is_hidden=0))
    # 연결 완료 수: 가 3 · 다 2 · 나 1 → 수가 없으면 이 차례다.
    for label, owner, names in ((A, u2, ["가1", "가2", "가3"]),
                                (B, u1, ["나1"]),
                                (C, u2, ["다1", "다2"])):
        for n in names:
            db.add(VcContact(user_id=owner.id, source_sheet=label, name=n,
                             firm="샘플벤처스", connect_stage="connected"))
    db.commit()
    return users


def _tabs(db):
    from app.models import VcContact
    from app.services import contact_columns as cc
    from app.services import sheet_owner

    contacts = db.query(VcContact).all()
    return [t["key"] for t in sheet_owner.sheet_rows(db, contacts, page=cc.PAGE_CONTACTS)]


def _set(db, **pos):
    from app.models import SheetOwner

    for row in db.query(SheetOwner).all():
        row.position = pos.get(row.label)
    db.commit()


def test_수가_없으면_지금까지의_차례다(db, world):
    assert _tabs(db) == [A, C, B]


def test_수가_있는_명단이_먼저_작은_수부터(db, world):
    _set(db, **{B: 1, C: 2})
    assert _tabs(db) == [B, C, A], "수가 없는 명단은 수가 있는 명단 뒤에 선다"
    _set(db, **{A: 3, B: 2, C: 1})
    assert _tabs(db) == [C, B, A]


def test_관리자의_전체_표도_탭_차례로_줄을_묶는다(client, db, world):
    _set(db, **{B: 1, C: 2, A: 3})
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    html = client.get("/contacts?sheet=all").text
    tabs = [t for t in re.findall(r'href="/contacts\?sheet=([^"&]+)"', html) if t != "all"]
    from urllib.parse import unquote

    assert [unquote(t) for t in tabs][:3] == [B, C, A]
    names = re.findall(r'data-s-name="([^"]+)"', html)
    assert names == ["나1", "다1", "다2", "가1", "가2", "가3"], names
