"""딜 소싱으로 나간 발송이 **이어진 투자사 줄**의 이력에도 보인다(10/29 제보).

딜 소싱 발송은 받는 줄이 딜 소싱 명단(`send_items.sourcing_contact_id`)이라 투자사
활동 이력 · 받은 기업 기록(`deal_history`) · IR 요청 기록의 [지난 회차에서 고르기]가
못 읽었다. 잇기(`SourcingContact.vc_contact_id`)만 따라간다 — 이름으로 짐작하지 않는다.
이름 · 회사는 가상의 값이다.
"""
from __future__ import annotations

from datetime import date

import pytest

from app.models import (DealBatch, DealBatchCompany, IrCompany, SendItem, SendJob,
                        SeriesACompany, SeriesAShare, SourcingContact, VcContact)
from app.services import deal_history, sourcing_msg
from app.services.sourcing_sync import SYNC_BUCKET


@pytest.fixture()
def world(db, users):
    """u1 의 투자사 줄 하나 + 이어진 소싱 줄 둘(갈래 둘) + 이름만 같은 안 이어진 소싱 줄."""
    vc = VcContact(user_id=1, name="가심사", firm="가나벤처스", kakao_room_name="방")
    db.add(vc)
    db.flush()
    series = SourcingContact(bucket=SYNC_BUCKET, name="가심사", firm="가나벤처스",
                             kakao_room_name="소싱방", vc_contact_id=vc.id)
    mna = SourcingContact(bucket="M&A 찾는 투자사", name="가심사", firm="가나벤처스",
                          kakao_room_name="소싱방2", vc_contact_id=vc.id)
    stranger = SourcingContact(bucket=SYNC_BUCKET, name="가심사", firm="다른벤처스",
                               kakao_room_name="남의방")
    ir = IrCompany(name="샘플에이", ir_file_name="a.pdf")
    db.add_all([series, mna, stranger, ir])
    db.flush()
    linked_a = SeriesACompany(name="샘플에이", ir_company_id=ir.id)
    only_a = SeriesACompany(name="샘플비")
    db.add_all([linked_a, only_a])
    db.commit()
    return {"vc": vc, "series": series, "mna": mna, "stranger": stranger,
            "ir": ir, "linked_a": linked_a, "only_a": only_a}


def _send(db, user_id, day, topic, rows, status="sent", shares=()):
    """딜 소싱 회차 하나 — `rows` 마다 한 건, `shares` 는 그 건마다 실린 기업(차례대로)."""
    batch = DealBatch(user_id=user_id, title=f"{day[5:]} 회차", sent_date=day)
    db.add(batch)
    db.flush()
    job = SendJob(user_id=user_id, kind=sourcing_msg.KIND, topic=topic, status="done",
                  batch_id=batch.id, total=len(rows))
    db.add(job)
    db.flush()
    items = []
    for row in rows:
        item = SendItem(job_id=job.id, sourcing_contact_id=row.id, room_name="소싱방",
                        message="본문", status=status, error="방 없음" if status == "failed" else None,
                        sent_at=f"{day}T10:00:00")
        db.add(item)
        db.flush()
        for no, company in enumerate(shares, start=1):
            db.add(SeriesAShare(series_a_company_id=company.id, sourcing_contact_id=row.id,
                                send_item_id=item.id, position=no, user_id=user_id))
        items.append(item)
    db.commit()
    return batch, items


# ── ① 활동 이력 ─────────────────────────────────────────────────────────────

def test_timeline_shows_linked_sourcing_sends_with_source_and_sender(logged_in, db, world):
    w = world
    # 다른 팀원(u2)이 보낸 Series A 딜 공유 — 기업이 문구 차례대로 붙는다.
    _send(db, 2, "2026-10-22", sourcing_msg.SHARE_KIND, [w["series"]],
          shares=[w["only_a"], w["linked_a"]])
    _send(db, 1, "2026-10-15", sourcing_msg.REMIND_KIND, [w["mna"]], status="failed")
    _send(db, 1, "2026-08-27", None, [w["series"]])
    # 이름만 같은 안 이어진 줄로 나간 것 · 방 확인 잡은 안 붙는다.
    _send(db, 1, "2026-10-23", sourcing_msg.SHARE_KIND, [w["stranger"]], shares=[w["only_a"]])
    room = SendJob(user_id=1, kind="verify_room", status="done", total=1)
    db.add(room)
    db.flush()
    db.add(SendItem(job_id=room.id, sourcing_contact_id=w["series"].id, room_name="소싱방",
                    message="", status="sent", sent_at="2026-10-24T10:00:00"))
    db.commit()

    timeline = logged_in.get(f"/api/contacts/{w['vc'].id}").json()["timeline"]
    rows = {t["kind"]: t for t in timeline if t["kind"].startswith("sourcing")}
    assert set(rows) == {"sourcing_intro", "sourcing_remind", "sourcing_deal_share"}
    assert len([t for t in timeline if t["kind"].startswith("sourcing")]) == 3

    share = rows["sourcing_deal_share"]
    assert [c["name"] for c in share["companies"]] == ["샘플비", "샘플에이"]
    assert share["sender"] == "윤서아" and share["state"] == ""
    assert share["date"] == "2026-10-22"

    remind = rows["sourcing_remind"]
    assert remind["state"] == "실패"
    assert remind["content"] == "딜 소싱(월간 리마인드) 실패 — 방 없음"
    assert rows["sourcing_intro"]["content"] == "딜 소싱(참여 안내)"
    assert rows["sourcing_intro"]["companies"] == []


def test_detached_row_takes_its_history_with_it(logged_in, db, world):
    """잇기를 끊으면 그 줄로 나간 것은 이 투자사 이력에서 빠진다 — 링크만 기준이다."""
    w = world
    _send(db, 1, "2026-10-22", sourcing_msg.SHARE_KIND, [w["series"]], shares=[w["only_a"]])
    w["series"].vc_contact_id = None
    db.commit()
    timeline = logged_in.get(f"/api/contacts/{w['vc'].id}").json()["timeline"]
    assert not [t for t in timeline if t["kind"].startswith("sourcing")]


# ── ② 받은 기업 기록 ────────────────────────────────────────────────────────

def test_sent_share_to_linked_row_counts_as_received(db, world):
    w = world
    batch, _ = _send(db, 2, "2026-10-22", sourcing_msg.SHARE_KIND, [w["series"]],
                     shares=[w["only_a"], w["linked_a"]])
    # 안 나간 건 · 안 이어진 줄 · 기업 없는 글은 안 센다.
    _send(db, 1, "2026-10-25", sourcing_msg.SHARE_KIND, [w["series"]], status="failed",
          shares=[w["only_a"]])
    _send(db, 1, "2026-10-26", sourcing_msg.SHARE_KIND, [w["stranger"]], shares=[w["only_a"]])
    _send(db, 1, "2026-10-27", sourcing_msg.REMIND_KIND, [w["series"], w["mna"]])

    sent = deal_history.scan(db)
    got = sorted((r.key, r.day, r.contact_id, r.source, r.user_id) for r in sent.receipts)
    assert got == sorted([
        (deal_history._key("샘플비"), "2026-10-22", w["vc"].id, deal_history.SOURCING, 2),
        (deal_history._key("샘플에이"), "2026-10-22", w["vc"].id, deal_history.SOURCING, 2),
    ])
    hist = sent.of("샘플비")
    assert hist.last_sent == "2026-10-22" and hist.investors == 1 and hist.days == 1
    assert hist.rounds[0].source_label == "딜 소싱"
    assert hist.rounds[0].batch_title == batch.title
    assert [s.label for s in hist.rounds[0].senders] == ["윤서아"]


def test_deal_intro_and_share_of_one_company_are_two_rounds(db, world):
    """같은 기업을 딜 소개와 딜 소싱으로 따로 받으면 회차 둘(`N회`) · 마지막 날은 늦은 쪽(45일)."""
    w = world
    batch = DealBatch(user_id=1, title="딜 소개", sent_date="2026-09-01")
    db.add(batch)
    db.flush()
    db.add(DealBatchCompany(batch_id=batch.id, company_id=w["ir"].id, position=1))
    job = SendJob(user_id=1, kind="deal_intro", status="done", batch_id=batch.id, total=1)
    db.add(job)
    db.flush()
    db.add(SendItem(job_id=job.id, contact_id=w["vc"].id, room_name="방", message="본문",
                    status="sent", sent_at="2026-09-01T10:00:00"))
    db.commit()
    _send(db, 2, "2026-10-22", sourcing_msg.SHARE_KIND, [w["series"]], shares=[w["linked_a"]])

    info = deal_history.annotate([w["ir"]], deal_history.scan(db), today=date(2026, 10, 29),
                                 mine={w["vc"].id})[w["ir"].id]
    assert info["rounds"] == 2
    assert info["investors"] == 1 and info["sends"] == 2
    assert info["last_sent"] == "2026-10-22" and info["recent"] is True
    assert info["my_got"] == 1 and info["my_last"] == "2026-10-22"


# ── ③ IR 요청 기록의 [지난 회차에서 고르기] ────────────────────────────────

def test_ir_last_batch_carries_the_last_sourcing_share(logged_in, db, world):
    w = world
    _send(db, 2, "2026-10-15", sourcing_msg.SHARE_KIND, [w["series"]], shares=[w["only_a"]])
    _send(db, 2, "2026-10-22", sourcing_msg.SHARE_KIND, [w["series"]],
          shares=[w["only_a"], w["linked_a"]])
    _send(db, 1, "2026-10-28", sourcing_msg.SHARE_KIND, [w["series"]], status="failed",
          shares=[w["only_a"]])
    _send(db, 1, "2026-10-29", sourcing_msg.SHARE_KIND, [w["stranger"]], shares=[w["only_a"]])

    body = logged_in.get(f"/api/ir/last-batch/{w['vc'].id}").json()
    assert body["items"] == []                       # 딜 소개 번호는 그대로(없다)
    src = body["sourcing"]
    assert src["title"] == "딜 소싱(Series A 딜 공유)" and src["sent_date"] == "2026-10-22"
    assert [(i["label"], i["name"], i["has_file"]) for i in src["items"]] == [
        ("[기업1]", "샘플비", False), ("[기업2]", "샘플에이", True)]


def test_ir_last_batch_without_linked_share_is_empty(logged_in, db, world):
    body = logged_in.get(f"/api/ir/last-batch/{world['vc'].id}").json()
    assert body["sourcing"]["items"] == []
