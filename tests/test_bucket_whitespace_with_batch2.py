"""갈래 이름 띄어쓰기(`fix/sourcing-bucket-whitespace`) × 2차 묶음(#305 · #306) — 접합.

두 쪽이 따로 main 에 서 있어 각자의 PR 에서는 못 맞춘 자리다. 함께 들어가면:

  ① [모든 팀원에게 적용](#306) — 딜 소싱 갈래 자리는 띄어쓰기만 달라도 한 자리다.
     다른 글자로 골라 둔 선택 · 개인 문구도 덮고, 되돌릴 버퍼도 그 자리에서 찾는다.
     갈래 이름을 바꾸면 버퍼도 묶인 글자 전부를 따라간다.
  ② 시트 다시 가져오기(#305) — 사람이 확정한 잇기를 묶인 글자의 줄 전부에서 기억한다.

이름 · 회사 · 번호는 전부 가상값이다(공개 저장소).
"""
from __future__ import annotations

from tests.test_sourcing_link_confirm import (  # noqa: F401 - 픽스처를 함께 쓴다
    _reimport, confirm)
from tests.test_sourcing_vc_sync import (  # noqa: F401
    board, sc, sync_rows, vc)
from tests.test_template_apply_all import people, portal  # noqa: F401

SYNC = "시리즈 A 이상 딜 소싱 참여 심사역"
TIGHT = "시리즈 A 이상 딜소싱 참여 심사역"
CEO = "딜 소싱 참여 투자사 대표"
CEO_WIDE = "딜 소싱  참여 투자사 대표"


def test_apply_all_covers_the_whitespace_variant(db, people):
    from app.models import MessageTemplate, TemplateChoice
    from app.services import template_apply, template_pick

    team = MessageTemplate(user_id=None, kind="sourcing_intro", name=TIGHT,
                           body="팀 문구", is_active=1)
    mine = MessageTemplate(user_id=people["u1"].id, kind="sourcing_intro", name=SYNC,
                           body="내 문구", is_active=1)
    db.add_all([team, mine])
    db.commit()
    db.add(TemplateChoice(user_id=people["u1"].id, kind="sourcing_intro", variant=SYNC,
                          template_id=mine.id))
    db.commit()

    plan, backup = template_apply.apply(db, team, people["admin"])
    db.commit()
    assert [p.id for p in plan.turn_off] == [mine.id]
    assert {"user_id": people["u1"].id, "template_id": mine.id} in plan.previous
    assert template_pick.pick(db, people["u1"].id, "sourcing_intro", SYNC).id == team.id
    assert db.query(TemplateChoice).filter_by(user_id=people["u1"].id,
                                              kind="sourcing_intro").count() == 1
    assert template_apply.latest(db, "sourcing_intro", SYNC).id == backup.id


def test_renaming_carries_backups_of_every_variant(db, people):
    from app.models import MessageTemplate, SourcingContact, TemplateApplyBackup
    from app.services import sourcing_buckets

    # 잇지 않는 갈래로 본다 — M&A 는 투자사 관리 현황과 이어져 이름을 못 바꾼다.
    db.add(SourcingContact(bucket=CEO_WIDE, position=1, name="홍길동"))
    team = MessageTemplate(user_id=None, kind="sourcing_intro", name=CEO_WIDE,
                           body="팀 문구", is_active=1)
    db.add(team)
    db.commit()
    db.add(TemplateApplyBackup(user_id=people["admin"].id, kind="sourcing_intro",
                               variant=CEO_WIDE, template_id=team.id,
                               previous_json="[]", turned_off_json="[]"))
    db.commit()
    sourcing_buckets.rename(db, CEO, "투자사 대표")
    db.commit()
    assert db.query(TemplateApplyBackup).one().variant == "투자사 대표"


def test_reimport_keeps_a_confirmed_link_on_a_whitespace_variant(board, db, users, tmp_path,
                                                                 monkeypatch):
    confirmed = vc(db, users, name="김서연", phone="010-1234-5678")   # 번호만 같다
    row = sc(db, bucket=TIGHT)                                          # 홍길동, `딜소싱`
    assert confirm(board, row.id, confirmed.id).status_code == 200

    _reimport(tmp_path, monkeypatch, [("2026/05/21", "홍길동", "010-1234-5678", "")])
    db.expire_all()
    from app.models import SourcingContact

    [again] = db.query(SourcingContact).all()
    assert again.bucket == TIGHT                       # 저장돼 있던 글자로 다시 넣는다
    assert again.vc_contact_id == confirmed.id
