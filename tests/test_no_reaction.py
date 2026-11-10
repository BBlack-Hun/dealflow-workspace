"""딜 제안 관리 `반응 없음` 판정(#200) — `services/no_reaction`.

앱에서 받은 IR 요청 · 미팅 · 자료 전달 · `N월 IR 요청` 칸 글은 반응이고, 선호 ·
메모 칸에 값이 있는 것만으로는 반응이 아니다. 이름은 전부 가상이다(공개 저장소).
"""
from __future__ import annotations

import re
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


def test_리마인드_답옴과_달_없는_IR요청_칸도_반응이다(db, users):
    """`IR 요청 투자사` 표에 `답 옴` 으로 서 있는데 딜 제안 관리는 `반응 없음` 이라고
    했다(2026-11 운영: 반응 없음 361명 중 24명) — 리마인드 표의 [답 옴](카톡에서 답을
    받았습니다)과, IR 요청 · 미팅을 적어 앱이 멈춘 리마인드가 반응 원본에 없었다.

    시트 시절 칸 중 달이 안 붙은 `IR 요청` 칸도 IR 요청 기록이다(1명). 달은 업무 보고가
    전달 날짜를 읽을 때 필요할 뿐, 반응인지는 달과 상관없다. `IR 요청기업 미팅 안내전화`
    칸은 우리가 건 전화라 여전히 반응이 아니고, 사람이 손으로 멈춘 리마인드도 아니다.
    """
    from app.models import (ContactActivity, ContactColumn, SendSequence,
                            SheetOwner, VcContact)
    from app.routers.contacts import contact_rows
    from app.services import cadence, no_reaction

    u1 = users["u1"]
    db.add(SheetOwner(label="가 명단", user_id=u1.id))
    plain = ContactColumn(sheet="가 명단", label="IR 요청", position=1)
    call = ContactColumn(sheet="가 명단", label="미팅 요청 / IR 요청기업 미팅 안내전화 TEL",
                         position=2)
    db.add_all([plain, call])
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

    def sequence(c, status, reason):
        db.add(SendSequence(user_id=u1.id, contact_id=c.id, stage=2, status=status,
                            stopped_reason=reason))

    replied = person("답옴")
    sequence(replied, "responded", cadence.REPLIED_REASON)
    asked = person("요청멈춤")          # IR 요청을 적어 앱이 멈췄고, 그 요청 줄은 나중에 지워졌다
    sequence(asked, "responded", "IR 자료를 요청했습니다")
    stopped = person("손으로멈춤")
    sequence(stopped, "stopped", "사람이 중단")
    waiting = person("예약중")
    sequence(waiting, "active", None)
    old_col = person("달없는칸", notes=f'{{"c{plain.id}": "샘플가, 샘플나"}}')
    called = person("안내전화칸", notes=f'{{"c{call.id}": "통화함"}}')
    db.commit()

    got = no_reaction.ids(db, contact_rows(db, u1))
    assert got == {stopped.id, waiting.id, called.id}, (
        "리마인드 [답 옴] · 앱이 반응으로 멈춘 리마인드 · 달 없는 `IR 요청` 칸은 반응이고, "
        "손으로 멈춘 리마인드 · 미팅 안내전화 칸은 반응이 아니다")


def test_반응이_적히면_상태의_반응없음이_풀린다(db, users):
    """`상태` 칸의 `반응없음` 은 사람이 상세에서 고른 값이라 반응이 와도 그대로 남았다.
    IR 관리의 담당자 고르기가 그 값을 `[반응없음]` 꼬리표로 붙여, IR 요청을 여러 번 한
    분이 반응없음으로 보였다(2026-11-10 운영: 상태 반응없음 100명 중 23명).

    반응이 적히면 — 어느 길로 적든 — `반응없음` 이 `활발` 로 풀린다. 딜소개만 나간
    분은 그대로이고, `검토중단` 은 반응과 상관없는 사람의 결정이라 안 건드린다.
    """
    from app.models import ContactActivity, IrRequest, Meeting, SendSequence, VcContact
    from app.services import cadence, sheet_owner

    u1 = users["u1"]
    today = date.today().isoformat()
    quiet, held = sheet_owner.STATUS_NO_RESPONSE, sheet_owner.STATUS_PAUSED

    def person(name, status=quiet):
        c = VcContact(user_id=u1.id, name=name, firm="가나벤처스", status=status)
        db.add(c)
        db.flush()
        return c

    asked, met, sheet, sent, replied, intro = (
        person(n) for n in ("앱요청", "앱미팅", "시트요청", "자료전달", "답옴", "딜소개만"))
    paused = person("검토중단", status=held)
    seq = SendSequence(user_id=u1.id, contact_id=replied.id, stage=2, status="active")
    db.add(seq)
    db.commit()

    db.add(IrRequest(user_id=u1.id, contact_id=asked.id, company_name="샘플가",
                     requested_at=today))
    db.add(Meeting(user_id=u1.id, contact_id=met.id, scheduled_at=today))
    # 관계로만 이어 둔 줄(번호가 flush 뒤에 정해진다)도 놓치지 않는다.
    db.add(ContactActivity(contact=sheet, kind="ir_request", content="IR 요청",
                           happened_at=today))
    db.add(ContactActivity(contact_id=sent.id, kind="ir_delivery", content="전달",
                           happened_at=today))
    db.add(ContactActivity(contact_id=intro.id, kind="deal_intro", content="딜소개",
                           happened_at=today))
    db.add(IrRequest(user_id=u1.id, contact_id=paused.id, company_name="샘플가",
                     requested_at=today))
    cadence.stop(db, seq, cadence.REPLIED_REASON, status="responded")
    db.commit()
    db.expire_all()

    got = {c.name: c.status for c in db.query(VcContact).all()}
    active = sheet_owner.STATUS_ACTIVE
    assert got == {"앱요청": active, "앱미팅": active, "시트요청": active, "자료전달": active,
                   "답옴": active, "딜소개만": quiet, "검토중단": held}, got


def test_반응_없는_담당자만_단추에_수가_적힌다(logged_in, db, users):
    """[반응 없는 담당자만] 을 누르면 목록이 그분들만 남는다(#211 — 거르기는 `deals.js`,
    `tests/js/deals_noreact_filter_test.js`). 단추에는 처음부터 **목록에 선 사람 중**
    반응 없는 분 수가 적혀야 한다 — 판정은 이 파일이 지키는 `no_reaction` 그대로다."""
    from app.models import ContactActivity, IrRequest, SheetOwner, VcContact

    u1 = users["u1"]
    db.add(SheetOwner(label="가 명단", user_id=u1.id))
    today = date.today().isoformat()

    def person(name, stage="connected"):
        c = VcContact(user_id=u1.id, name=name, firm="가나벤처스", source_sheet="가 명단",
                      connect_stage=stage, kakao_room_name=f"{name} 방", channel_kakao=1)
        db.add(c)
        db.flush()
        db.add(ContactActivity(contact_id=c.id, kind="deal_intro", content="딜소개",
                               happened_at=today, month=today[:7]))
        return c

    person("무반응1")
    person("무반응2")
    person("연결전무반응", stage="in_progress")    # 목록에 안 서는 분 — 수에 안 든다
    asked = person("요청함")
    db.add(IrRequest(user_id=u1.id, contact_id=asked.id, company_name="샘플가",
                     requested_at=today))
    db.commit()

    html = logged_in.get("/deals").text
    button = re.search(r'<button[^>]*id="select-noreact"[^>]*>([^<]*)</button>', html)
    assert button, "[반응 없는 담당자만] 단추가 화면에 없다"
    assert button.group(1).strip() == "반응 없는 담당자만 · 2명", button.group(1)
    assert html.count('data-noreact="1"') == 2


def test_대시보드_반응_없는_분_수는_딜제안관리와_같고_눌러_넘어간다(logged_in, db, users):
    """대시보드 `내 투자사 선호` 는 IR 요청한 분의 순위라, 거기 한 번도 안 걸린 분이 곧
    반응 없는 분은 아니다 — 딜소개를 아직 안 받은 분과 미팅 · 답 옴처럼 IR 요청 말고 다른
    반응이 있는 분이 섞인다(2026-11-10 운영: 계정마다 5~41명). 그래서 대시보드는 제 집합을
    세지 않고 딜 제안 관리와 **같은 한 벌**(`no_reaction.listed`)의 수를 적고, 누르면
    [반응 없는 담당자만] 이 켜진 채 열린다(#213 — `?noreact=1`, `deals.js`)."""
    from app.models import ContactActivity, Meeting, SheetOwner, VcContact

    u1 = users["u1"]
    db.add(SheetOwner(label="가 명단", user_id=u1.id))
    today = date.today().isoformat()

    def person(name, intro=True):
        c = VcContact(user_id=u1.id, name=name, firm="가나벤처스", source_sheet="가 명단",
                      connect_stage="connected", kakao_room_name=f"{name} 방", channel_kakao=1)
        db.add(c)
        db.flush()
        if intro:
            db.add(ContactActivity(contact_id=c.id, kind="deal_intro", content="딜소개",
                                   happened_at=today, month=today[:7]))
        return c

    person("무반응1")
    person("무반응2")
    person("딜소개전", intro=False)                 # IR 요청 0건이지만 반응 없음이 아니다
    met = person("미팅만")                          # IR 요청 0건이지만 미팅이 있다
    db.add(Meeting(user_id=u1.id, contact_id=met.id, scheduled_at=today))
    db.commit()

    dash = logged_in.get("/dashboard").text
    link = re.search(r'<a[^>]*href="/deals\?noreact=1"[^>]*>.*?<b>(\d+)</b>', dash, re.S)
    assert link, "대시보드에 딜 제안 관리 [반응 없는 담당자만] 으로 넘어가는 연결이 없다"
    deals = logged_in.get("/deals").text
    button = re.search(r'id="select-noreact"[^>]*>반응 없는 담당자만 · (\d+)명<', deals)
    assert link.group(1) == button.group(1) == "2", (link.group(1), button.group(1))
    assert re.search(r'href="/deals\?noreact=1"', logged_in.get("/").text), (
        "첫 화면(`/`)도 같은 대시보드다 — 한쪽에만 연결이 서면 안 된다")
