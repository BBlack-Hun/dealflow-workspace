"""#25 — `Series A 이상 딜 소싱` 탭: `공유 심사역` 오른쪽에 `휴대폰` 칸.

요청: "공유 심사역 오른쪽에 핸드폰 컬럼. IR 기업현황이나 딜소싱 어느 쪽에 넣어도 자동 기입."
담당자: 번호는 **공유 심사역**의 번호다.

칸 이름은 `휴대폰` 이다 — 같은 번호(딜 소싱 줄 = 투자사 관리 현황 줄)를 두 화면이 그렇게
부른다(#63 "같은 칸은 같은 이름"). `핸드폰` 은 이 탭 `연락처`(대표 번호)의 옛 이름이라
쓰지 않는다(`tests/test_unify_column_labels.py` · `custom_columns` 의 옛 이름 → 새 이름).

  ① 머리글 `휴대폰` 이 `공유 심사역` 바로 오른쪽에 선다
  ② [이 분으로 확정]한 분이 없으면 빈칸이고 고칠 수 없다(칸도 안 열리고 서버도 막는다)
  ③ 확정한 분의 딜 소싱 줄 번호가 보이고, 고치면 그 줄에 저장돼 이어진 투자사 관리
     현황 줄도 따라 고쳐진다(`sourcing_sync.before_flush`)

이름 · 회사 · 번호는 전부 가상값이다(공개 저장소).
"""
from __future__ import annotations

import re

from .test_series_a_share_review import today, world  # noqa: F401 - 픽스처

PHONE = "010-0000-0002"


def _row(html: str, row_id: int) -> str:
    return re.search(rf'<tr data-id="{row_id}".*?</tr>', html, re.S).group(0)


def _phone_cell(html: str, row_id: int) -> str:
    return re.search(r'<td class="sa-sharer-phone[^"]*"[^>]*>[^<]*</td>',
                     _row(html, row_id)).group(0)


def test_the_column_sits_right_after_the_sharer(world, client):
    html = client.get("/companies?tab=series-a").text
    head = re.search(r'<table[^>]*id="sa-table".*?</thead>', html, re.S).group(0)
    heads = [re.sub(r"<[^>]+>", "", h).strip()
             for h in re.findall(r"<th\b[^>]*>(.*?)</th>", head, re.S)]
    at = heads.index("공유 심사역")
    assert heads[at + 1] == "휴대폰", heads


def test_without_a_confirmed_sharer_it_is_blank_and_locked(world, client, db):
    from app.models import SourcingContact

    own = world["c"]["own"]
    cell = _phone_cell(client.get("/companies?tab=series-a").text, own.id)
    assert 'class="sa-sharer-phone"' in cell and cell.endswith("></td>"), cell
    r = client.patch(f"/api/series-a-companies/{own.id}", json={"sharer_phone": PHONE})
    assert r.status_code == 400 and "이 분으로 확정" in r.json()["detail"]
    db.expire_all()
    assert all(p.phone is None for p in db.query(SourcingContact).all())


def test_it_shows_and_saves_the_confirmed_persons_number(world, client, db, users):
    from app.models import SourcingContact, VcContact

    own = world["c"]["own"]
    b = world["p"]["b"]
    vc = VcContact(user_id=users["u1"].id, source_sheet="내 명단", name=b.name,
                   firm=b.firm, phone="010-0000-0001")
    db.add(vc)
    db.flush()
    row = db.get(SourcingContact, b.id)
    row.vc_contact_id, row.phone = vc.id, "010-0000-0001"
    db.commit()
    client.put(f"/api/series-a-companies/{own.id}/sharer", json={"contact_id": b.id})

    cell = _phone_cell(client.get("/companies?tab=series-a").text, own.id)
    assert 'class="sa-sharer-phone cell"' in cell and ">010-0000-0001</td>" in cell, cell

    r = client.patch(f"/api/series-a-companies/{own.id}", json={"sharer_phone": f" {PHONE} "})
    assert r.status_code == 200, r.text
    assert r.json()["sharer_phone"] == PHONE
    assert r.json()["sharer"]["confirmed"]["phone"] == PHONE
    db.expire_all()
    assert db.get(SourcingContact, b.id).phone == PHONE
    assert db.get(VcContact, vc.id).phone == PHONE, "투자사 관리 현황이 안 따라왔다"
    # 딜 소싱에서 고쳐도 이 칸이 그 번호를 읽는다
    assert client.patch(f"/api/sourcing/{b.id}", json={"phone": "010-0000-0003"}).status_code == 200
    assert ">010-0000-0003</td>" in _phone_cell(client.get("/companies?tab=series-a").text, own.id)

    # 해제하면 빈칸으로 돌아가고 번호는 그 분 줄에 그대로 남는다
    r = client.put(f"/api/series-a-companies/{own.id}/sharer", json={"contact_id": None})
    assert r.json()["sharer"]["confirmed"] is None
    db.expire_all()
    assert db.get(SourcingContact, b.id).phone == "010-0000-0003"
