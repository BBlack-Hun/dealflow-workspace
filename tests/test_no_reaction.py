"""딜 제안 관리 `반응 없음` 판정(#200) — `services/no_reaction`.

앱에서 받은 IR 요청 · 미팅 · 자료 전달 · `N월 IR 요청` 칸 글은 반응이고, 선호 ·
메모 칸에 값이 있는 것만으로는 반응이 아니다. 이름은 전부 가상이다(공개 저장소).
"""
from __future__ import annotations

from datetime import date


def test_앱_반응과_IR요청_칸은_반응이고_선호칸은_아니다(db, users):
    from app.models import (ContactActivity, ContactColumn, IrRequest, Meeting,
                            SheetOwner, VcContact)
    from app.routers.contacts import contact_rows
    from app.services import no_reaction

    u1 = users["u1"]
    db.add(SheetOwner(label="가 명단", user_id=u1.id))
    col = ContactColumn(sheet="가 명단", label="11월 IR 요청", position=1)
    db.add(col)
    db.flush()
    today = date.today().isoformat()

    def person(name, **kw):
        c = VcContact(user_id=u1.id, name=name, firm="가나벤처스",
                      source_sheet="가 명단", **kw)
        db.add(c)
        db.flush()
        db.add(ContactActivity(contact_id=c.id, kind="deal_intro", content="딜소개",
                               happened_at=today, month=today[:7]))
        return c

    quiet = person("무반응")
    prefs = person("선호만", sectors="AI", memo="시드 선호", interest_level="낮음")
    asked = person("앱요청")
    db.add(IrRequest(user_id=u1.id, contact_id=asked.id, company_name="샘플가",
                     requested_at=today))
    met = person("앱미팅")
    db.add(Meeting(user_id=u1.id, contact_id=met.id, scheduled_at=today))
    sent = person("자료전달")
    db.add(ContactActivity(contact_id=sent.id, kind="ir_delivery", content="전달",
                           happened_at=today))
    undone = person("전달취소")
    db.add(ContactActivity(contact_id=undone.id, kind="ir_delivery", content="전달",
                           happened_at=today, undone_at=today))
    noted = person("칸기록", notes=f'{{"c{col.id}": "[요청] 샘플가"}}')
    db.add(VcContact(user_id=u1.id, name="미발송", firm="가나벤처스", source_sheet="가 명단"))
    db.commit()

    got = no_reaction.ids(db, contact_rows(db, u1))
    assert got == {quiet.id, prefs.id, undone.id}, (
        "앱 IR 요청 · 미팅 · 자료 전달 · IR 요청 칸 글이 있으면 반응이고, "
        "선호 · 메모 칸 값만으로는 반응이 아니다")
