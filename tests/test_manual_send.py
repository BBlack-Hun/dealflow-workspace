"""손으로 보낸 것을 적는다 — 딜 제안 관리의 [손으로 보냈다면].

왜 이 검사가 있는가
-------------------
팀원 중에 프로그램으로 카톡을 보내지 않고 **손으로** 보내는 사람이 있다.
그 사람이 한 일은 앱 어디에도 안 남아서, 업무 보고의 `딜 소개 총 N명` 도
진행 단계도 비어 있고 **리마인드가 아예 안 섰다.**

잠가야 하는 것이 여덟이다.

1. **업무 보고·대시보드의 발송 수에 합쳐진다** — 그리고 세는 자리가 한 곳이다
   (`manual_send.counted`). 자리마다 따로 세면 한 곳이 반드시 빠진다.
2. **오늘 날짜면 리마인드가 서고, 지난 날짜면 안 선다.** 2주치를 몰아 적었을
   때 `밀린 리마인드 80건` 이 뜨면 오늘 할 일이 묻힌다.
3. **딜 소개는 기업이 적힌다** — 안 적히면 다음 회차에 LLM 이 같은 기업을 또
   추천한다. 이름 없이 **개수만** 적는 길도 열려 있다(`핵심 딜 8개사`).
4. **묶음째 되돌릴 수 있고, 되돌린 줄은 읽는 자리 어디에서도 안 읽힌다.**
5. **남의 담당 줄이 섞이면 한 줄도 안 적힌다.**
6. **같은 날 같은 묶음을 두 번 적어도 두 번 안 들어간다.**
7. **`source="manual"` 인 줄만 수정 로그에 남는다** — 가져오기·발송이 만든
   줄까지 남기면 하루 수천 줄이 쌓여 아무도 안 본다.
8. 확인 없이 부르면 **세기만** 한다.

이름·회사는 전부 지어낸 것이다(공개 저장소).
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.services import manual_send

from .conftest import DEMO_PASSWORD

SHEET = "투자사 시험 명단"
TODAY = date.today().isoformat()
LONG_AGO = (date.today() - timedelta(days=14)).isoformat()


@pytest.fixture()
def rows(db, users):
    """u1 담당 셋 · u2 담당 하나. 기업 둘."""
    from app.models import IrCompany, SheetOwner, VcContact
    from app.services import contact_columns as cc

    u1, u2 = users["u1"], users["u2"]
    db.add(SheetOwner(label=SHEET, user_id=u1.id, layout=cc.INVESTOR))
    made = {}
    for name, owner in (("가담당", u1), ("나담당", u1), ("다담당", u1),
                        ("라담당", u2)):
        row = VcContact(user_id=owner.id, source_sheet=SHEET, name=name,
                        firm="가나벤처스", connect_stage="connected",
                        channel_kakao=1, kakao_room_name=f"{name} 방")
        db.add(row)
        made[name] = row
    for cname in ("샘플애그", "샘플메디"):
        db.add(IrCompany(name=cname, one_liner="한 줄", sector_major="아무분야",
                         series="시드"))
    db.commit()
    made["companies"] = db.query(IrCompany).order_by(IrCompany.id).all()
    return made


@pytest.fixture()
def me(client, db, users, rows):
    client.post("/login", data={"phone": "01000000001",
                                "password": DEMO_PASSWORD})
    return client


def _post(client, ids, *, kind=manual_send.DEAL_INTRO, day=TODAY,
          companies=None, count=None, confirm=True):
    return client.post("/api/deals/manual-sends", json={
        "contact_ids": ids, "kind": kind, "day": day,
        "company_ids": companies or [], "company_count": count,
        "confirm": confirm})


def _acts(db, contact_id=None):
    from app.models import ContactActivity

    q = db.query(ContactActivity)
    if contact_id:
        q = q.filter(ContactActivity.contact_id == contact_id)
    return q.all()


# ── ① 합쳐 센다 ─────────────────────────────────────────────────────────────

def test_manual_rows_join_the_report_and_the_dashboard(db, me, rows, users):
    """손으로 적은 것이 **업무 보고의 `딜 소개 총 N명`** 과 대시보드에 함께 선다.

    이것이 안 되면 손으로 보내는 사람의 보고가 영영 0 이다.
    """
    from app.services import dashboard, report

    ids = [rows["가담당"].id, rows["나담당"].id, rows["다담당"].id]
    got = _post(me, ids, companies=[c.id for c in rows["companies"]])
    assert got.status_code == 200, got.text
    assert got.json()["added"] == 3

    today = date.today()
    data = report.monthly(db, today.year, today.month, users["u1"])
    deal = next(g for g in data["sends"]["groups"] if g["key"] == "deal_intro")
    assert deal["contacts"] == 3, "업무 보고가 손으로 적은 3명을 안 세고 있다"
    assert deal["sent"] == 3
    # 합쳤어도 **되짚을 수 있어야 한다** — 손으로 적은 줄임이 회차명에 있다.
    manual_rows = [r for r in deal["rows"] if r.get("manual")]
    assert len(manual_rows) == 1
    assert manual_send.BY_HAND in manual_rows[0]["title"]
    # 볼 회차가 없다(발송기를 지나지 않았다) — 화면이 [보기] 칸을 비운다.
    assert manual_rows[0]["job_id"] == 0
    # 그 회차에 실은 기업도 그대로 선다.
    assert deal["companies"] == 2

    view = dashboard.user_dashboard(db, users["u1"])
    sent = next(k for k in view["kpis"] if k["key"] == "sent")
    assert sent["value"] == 3, "대시보드 이번 주 발송에 안 합쳐졌다"
    assert "손으로 적음 3" in sent["sub"], "합친 수를 되짚을 말이 없다"


def test_the_team_view_counts_them_too(db, me, rows, users):
    """팀 현황의 `이번 달 발송`도 같은 함수를 읽는다 — 화면마다 수가 갈리면 안 된다."""
    from app.services import dashboard

    _post(me, [rows["가담당"].id, rows["나담당"].id])
    team = dashboard.admin_dashboard(db)
    mine = next(r for r in team["members"] if r["id"] == users["u1"].id)
    assert mine["sent_month"] == 2
    assert mine["sent_month_manual"] == 2


def test_counting_lives_in_one_place(db, me, rows):
    """★ **세는 자리가 한 곳인지**를 못 박는다.

    세 화면이 각자 `source == "manual"` 을 거르고 있으면 한 곳이 반드시
    빠진다(이 저장소가 `SEND_KINDS` 에서 이미 그렇게 데였다). 그래서 세 화면이
    읽는 함수를 **비워 보고**, 셋이 다 같이 0 이 되는지를 본다.
    """
    from app.services import dashboard, report

    _post(me, [rows["가담당"].id, rows["나담당"].id])
    from app.models import User

    real = manual_send.counted
    manual_send.counted = lambda *a, **k: []
    try:
        today = date.today()
        data = report.monthly(db, today.year, today.month, None)
        deal = next(g for g in data["sends"]["groups"]
                    if g["key"] == "deal_intro")
        assert deal["contacts"] == 0, "업무 보고가 그 함수를 안 읽고 따로 세고 있다"
        view = dashboard.user_dashboard(db, db.get(User, 1))
        assert next(k for k in view["kpis"] if k["key"] == "sent")["value"] == 0, \
            "대시보드가 그 함수를 안 읽고 따로 세고 있다"
        team = dashboard.admin_dashboard(db)
        assert all(r["sent_month"] == 0 for r in team["members"]), \
            "팀 현황이 그 함수를 안 읽고 따로 세고 있다"
    finally:
        manual_send.counted = real


# ── ② 오늘 것만 리마인드 ────────────────────────────────────────────────────

def test_today_sets_a_reminder(db, me, rows):
    from app.models import SendSequence

    _post(me, [rows["가담당"].id], day=TODAY)
    seq = db.query(SendSequence).filter(
        SendSequence.contact_id == rows["가담당"].id).one()
    assert seq.status == "active"
    assert seq.next_due_date, "다음 리마인드 날짜가 안 잡혔다"


def test_a_past_day_only_records(db, me, rows):
    """2주 전 80명을 몰아 적어도 **밀린 리마인드가 쏟아지지 않는다.**"""
    from app.models import SendSequence

    got = _post(me, [rows["가담당"].id], day=LONG_AGO)
    assert got.json()["reminded"] == 0
    assert db.query(SendSequence).count() == 0
    # 기록은 남는다 — 빠지는 것은 후속 예약뿐이다.
    assert len(_acts(db, rows["가담당"].id)) == 1


def test_the_screen_is_told_before_it_happens(me):
    """화면이 **미리** 말한다 — 적고 나서 알면 이미 늦다."""
    page = me.get("/deals")
    assert manual_send.REMIND_NOTE in page.text
    # 글자를 화면에 박아 두지 않았는지 — 가르는 함수와 같은 곳에서 온다.
    assert manual_send.sets_reminder(TODAY) is True
    assert manual_send.sets_reminder(LONG_AGO) is False


def test_the_future_is_refused(me, rows):
    """앞날로는 못 적는다 — 아직 안 한 일을 보고가 세면 안 된다."""
    later = (date.today() + timedelta(days=3)).isoformat()
    assert _post(me, [rows["가담당"].id], day=later).status_code == 400
    assert _post(me, [rows["가담당"].id], day="언젠가").status_code == 400


# ── ③ 기업 ──────────────────────────────────────────────────────────────────

def test_deal_intro_writes_the_companies(db, me, rows):
    """기업이 안 적히면 **다음 회차에 LLM 이 같은 기업을 또 추천한다.**"""
    from app.services import deal_history

    names = [c.name for c in rows["companies"]]
    _post(me, [rows["가담당"].id], companies=[c.id for c in rows["companies"]])
    act = _acts(db, rows["가담당"].id)[0]
    assert act.companies == names
    assert act.company_count == 2
    # `이미 보낸 기업` 이 이 이름으로 만들어진다.
    assert set(deal_history.last_sent_map(db)) >= {
        deal_history._key(n) for n in names}


def test_a_count_only_round_is_allowed(db, me, rows):
    """`핵심 딜 8개사` 처럼 **개수만** 적힌 회차가 시트에 실제로 있다."""
    _post(me, [rows["가담당"].id], count=8)
    act = _acts(db, rows["가담당"].id)[0]
    assert act.companies == []
    assert act.company_count == 8
    # 화면이 그렇게 보여 준다 — `8개사`.
    from app.routers.contacts import _round_label

    assert "8개사" in _round_label(act)


def test_meeting_ask_carries_no_companies(db, me, rows):
    """미팅 요청은 기업을 안 적는다 — 나가는 카톡이 담당자당 한 통이다."""
    _post(me, [rows["가담당"].id], kind=manual_send.MEETING_ASK,
          companies=[c.id for c in rows["companies"]])
    act = _acts(db, rows["가담당"].id)[0]
    assert act.companies == []
    assert act.company_count is None


def test_a_manual_meeting_ask_is_seen_as_asked(db, me, rows):
    """#162·#180 의 미팅 요청 판정이 손으로 적은 것도 읽는가."""
    from app.services import pipeline

    _post(me, [rows["가담당"].id], kind=manual_send.MEETING_ASK)
    acts = _acts(db, rows["가담당"].id)
    assert acts[0].kind == pipeline.MEETING_ASK_KIND


# ── ④ 되돌리기 ──────────────────────────────────────────────────────────────

def test_a_batch_is_undone_as_one(db, me, rows):
    ids = [rows["가담당"].id, rows["나담당"].id, rows["다담당"].id]
    key = _post(me, ids).json()["batch_key"]

    plan = me.post(f"/api/deals/manual-sends/{key}/undo", json={"confirm": False})
    assert plan.json()["plan"]["rows"] == 3
    assert plan.json()["undone"] == 0, "확인 전인데 되돌아갔다"

    got = me.post(f"/api/deals/manual-sends/{key}/undo", json={"confirm": True})
    assert got.json()["undone"] == 3


#: 되돌린 줄을 **계속 읽으면 안 되는** 자리들. 한 곳이라도 읽으면 되돌린 뜻이
#: 없다 — 그래서 거르는 자리를 한 곳에 두었다(`models._hide_undone_activities`).
def test_an_undone_row_is_read_nowhere(db, me, rows, users):
    from app.services import (cadence, dashboard, deal_history, deal_stage,
                              ir_monthly, llm_brief, pipeline, report)

    contact = rows["가담당"]
    key = _post(me, [contact.id],
                companies=[c.id for c in rows["companies"]]).json()["batch_key"]
    assert deal_stage.of_many(db, [contact.id])[contact.id] == deal_stage.INTRO

    me.post(f"/api/deals/manual-sends/{key}/undo", json={"confirm": True})
    db.expire_all()

    # 1. 진행 단계
    assert deal_stage.of_many(db, [contact.id])[contact.id] == deal_stage.NONE
    # 2. 기업별 최근 발송
    assert deal_history.last_sent_map(db) == {}
    # 3. LLM `sent_before`
    assert llm_brief.sent_history(db, [contact.id])[contact.id][0] == []
    # 4. 투자사 목록의 `마지막 딜소개`
    from app.routers.contacts import contact_rows

    row = next(r for r in contact_rows(db, users["u1"])
               if r["id"] == contact.id)
    assert row["last_deal"] is None
    # 5. 담당자 이력 타임라인
    detail = me.get(f"/api/contacts/{contact.id}").json()
    assert not [t for t in detail["timeline"]
                if t.get("source") == "manual"]
    # 6. 업무 보고
    today = date.today()
    data = report.monthly(db, today.year, today.month, users["u1"])
    deal = next(g for g in data["sends"]["groups"] if g["key"] == "deal_intro")
    assert deal["contacts"] == 0
    # 7. 대시보드
    view = dashboard.user_dashboard(db, users["u1"])
    assert next(k for k in view["kpis"] if k["key"] == "sent")["value"] == 0
    # 8. 대시보드 반응 · 팀 현황
    assert dashboard._recent_activity_counts(db, [contact.id], "1900-01-01") == {}
    # 9. 합쳐 세는 자리
    assert manual_send.counted(db, send_kinds=("deal_intro",)) == []

    # ── 남은 읽는 자리 셋은 다른 갈래를 읽는다 ─────────────────────────────
    #
    # 리마인드 **멈추기** · IR 월간 · 대시보드 반응은 `ir_request`·`meeting`
    # 을 본다. 손으로 적는 길은 그 갈래를 만들지 않으므로(반응은 이쪽이 보낸
    # 것이 아니다) 되돌린 줄을 직접 세워 본다 — 거르는 자리가 한 곳이라면
    # 이 셋도 함께 빠져야 한다.
    from app.models import ContactActivity

    db.add(ContactActivity(contact_id=contact.id, kind="ir_request",
                           content="숨긴 요청", company_names='["샘플애그"]',
                           happened_at=TODAY, month=TODAY[:7],
                           undone_at="2026-01-01T00:00:00+09:00"))
    db.commit()
    assert cadence.has_reaction_since(db, contact.id, "1900-01-01") is False
    assert pipeline.meeting_ask_state(db, []) == {}
    assert ir_monthly.monthly_requests(
        db, today.strftime("%Y-%m")).by_company == {}
    assert dashboard._recent_activity_counts(db, [contact.id], "1900-01-01") == {}


def test_an_undone_batch_stays_in_the_list(db, me, rows):
    """되돌린 판이 목록에서 사라지면 **되돌렸는지 안 적었는지**를 알 수 없다."""
    key = _post(me, [rows["가담당"].id]).json()["batch_key"]
    me.post(f"/api/deals/manual-sends/{key}/undo", json={"confirm": True})

    listed = me.get("/api/deals/manual-sends").json()["batches"]
    got = next(b for b in listed if b["batch_key"] == key)
    assert got["is_undone"] is True
    assert got["rows"] == 1


def test_undo_does_not_delete(db, me, rows):
    """지우지 않는다 — 무엇이 있었는지 물을 자리가 남아야 한다."""
    key = _post(me, [rows["가담당"].id]).json()["batch_key"]
    me.post(f"/api/deals/manual-sends/{key}/undo", json={"confirm": True})
    from app.models import ContactActivity, including_undone

    with including_undone(db):
        kept = db.query(ContactActivity).all()
    assert len(kept) == 1 and kept[0].undone_at


def test_someone_elses_batch_cannot_be_undone(db, client, rows, users):
    """되돌리는 것도 적는 것과 같은 무게다 — 판정은 같은 `_owned` 다."""
    client.post("/login", data={"phone": "01000000001",
                                "password": DEMO_PASSWORD})
    key = _post(client, [rows["가담당"].id]).json()["batch_key"]
    client.post("/login", data={"phone": "01000000002",
                                "password": DEMO_PASSWORD})
    got = client.post(f"/api/deals/manual-sends/{key}/undo",
                      json={"confirm": True})
    assert got.status_code == 404
    from app.models import ContactActivity

    assert db.query(ContactActivity).filter(
        ContactActivity.undone_at.isnot(None)).count() == 0


# ── ⑤ 남의 줄이 섞이면 한 줄도 안 적힌다 ────────────────────────────────────

def test_one_foreign_row_stops_the_whole_batch(db, me, rows):
    got = _post(me, [rows["가담당"].id, rows["라담당"].id])
    assert got.status_code == 404
    assert _acts(db) == [], "남의 줄이 섞였는데 일부가 적혔다"


def test_nothing_is_written_without_confirm(db, me, rows):
    got = _post(me, [rows["가담당"].id, rows["나담당"].id], confirm=False)
    assert got.json()["plan"]["adding"] == 2
    assert got.json()["added"] == 0
    assert _acts(db) == [], "확인 전인데 적혔다"


# ── ⑥ 두 번 적어도 한 줄 ────────────────────────────────────────────────────

def test_the_same_batch_twice_lands_once(db, me, rows):
    ids = [rows["가담당"].id, rows["나담당"].id]
    company_ids = [c.id for c in rows["companies"]]
    _post(me, ids, companies=company_ids)
    again = _post(me, ids + [rows["다담당"].id], companies=company_ids)
    body = again.json()
    assert body["added"] == 1
    assert body["duplicated"] == 2
    assert "이미 있었음" in body["note"]
    assert len(_acts(db)) == 3


def test_a_different_count_is_not_a_duplicate(db, me, rows):
    """같은 날 `8개사` 와 `5개사` 는 다른 회차다 — 뒤엣것이 묻히면 안 된다."""
    _post(me, [rows["가담당"].id], count=8)
    _post(me, [rows["가담당"].id], count=5)
    assert len(_acts(db, rows["가담당"].id)) == 2


def test_the_shared_rule_is_the_one_the_app_already_used(db, rows):
    """★ 중복 판정이 한 곳인가 — `ir_attach` · `pipeline` 이 같은 함수를 지난다."""
    from app.services import ir_attach, pipeline

    contact = rows["가담당"]
    calls = []
    real = manual_send.existing

    def spy(*a, **k):
        calls.append(a[2])
        return real(*a, **k)

    manual_send.existing = spy
    try:
        ir_attach.record_delivery(db, contact.id, ["샘플애그"])
        pipeline.record_meeting_ask(db, contact.id)
    finally:
        manual_send.existing = real
    assert calls == ["ir_delivery", pipeline.MEETING_ASK_KIND]


# ── ⑦ 수정 로그 ─────────────────────────────────────────────────────────────

def _logs(db, table="contact_activities"):
    from app.models import EditLog

    return db.query(EditLog).filter(EditLog.table_name == table).all()


def test_manual_rows_are_logged(db, me, rows):
    """묶음 입력은 **남의 담당자 줄에도 닿는다** — 되돌릴 근거가 여기 말고 없다."""
    _post(me, [rows["가담당"].id, rows["나담당"].id])
    got = _logs(db)
    assert len(got) == 2, "손으로 적은 줄이 수정 로그에 안 남았다"
    assert all(x.action == "create" for x in got)
    # 되돌린 것도 남아야 한다 — 그것도 사람이 한 일이다.
    key = _post(me, [rows["다담당"].id]).json()["batch_key"]
    before = len(_logs(db))
    me.post(f"/api/deals/manual-sends/{key}/undo", json={"confirm": True})
    assert len(_logs(db)) > before


def test_imports_and_sends_are_not_logged(db, me, rows):
    """가져오기·발송이 만든 줄까지 남기면 **하루 수천 줄**이 쌓여 아무도 안 본다."""
    from app.services import ir_attach

    before = len(_logs(db))
    # 앱이 적는 길(`source="system"`).
    got = me.post(f"/ir/contacts/{rows['가담당'].id}/meeting-asked")
    assert got.status_code in (200, 303, 307)
    assert len(_logs(db)) == before, "발송이 만든 줄이 로그에 남았다"

    ir_attach.record_delivery(db, rows["가담당"].id, ["샘플애그"])
    db.commit()
    assert len(_logs(db)) == before


def test_the_table_is_no_longer_unwatched(db):
    """`UNWATCHED` 의 설명이 거짓이 되지 않았는지 — 표를 옮겼는지 본다."""
    from app.services import edit_log

    assert "contact_activities" not in edit_log.UNWATCHED
    watch = edit_log.WATCHED["contact_activities"]
    assert watch.only == ("source", "manual")


# ── 거르는 자리가 한 곳인가 ─────────────────────────────────────────────────

@pytest.mark.parametrize("shape", ["entity", "column", "aggregate", "join"])
def test_every_query_shape_is_filtered(db, users, rows, shape):
    """★ 되돌린 줄이 **어떤 모양의 조회에서도** 안 읽히는가.

    이 표를 읽는 자리는 줄 단위 조회보다 **칸만 고르는 조회와 셈**이 훨씬
    많다(`select(ContactActivity.kind, func.count())`). 거르는 자리 한 곳이
    그 모양들까지 덮지 못하면, 덮이지 않은 자리에서 되돌린 줄이 계속 읽힌다.
    """
    from sqlalchemy import func, select

    from app.models import ContactActivity, VcContact

    contact = rows["가담당"]
    db.add(ContactActivity(contact_id=contact.id, kind="deal_intro",
                           content="숨긴 줄", happened_at=TODAY,
                           undone_at="2026-01-01T00:00:00+09:00"))
    db.add(ContactActivity(contact_id=contact.id, kind="deal_intro",
                           content="보이는 줄", happened_at=TODAY))
    db.commit()

    if shape == "entity":
        got = [a.content for a in db.execute(
            select(ContactActivity)).scalars().all()]
    elif shape == "column":
        got = list(db.execute(select(ContactActivity.content)).scalars().all())
    elif shape == "aggregate":
        got = ["보이는 줄"] * db.execute(
            select(func.count()).select_from(ContactActivity)).scalar()
    else:
        got = [c for c, _n in db.execute(
            select(ContactActivity.content, VcContact.name)
            .join(VcContact, VcContact.id == ContactActivity.contact_id)).all()]
    assert got == ["보이는 줄"], f"{shape} 조회가 되돌린 줄을 읽었다"


# ── 브라우저 쪽 ─────────────────────────────────────────────────────────────
#
# 고른 것을 서버로 싣는 일도, 확인창이 무엇을 묻는지도 브라우저에 있다. 그
# 규칙을 파이썬으로 다시 구현하면 두 벌이 되어 어긋나도 모르므로,
# `manual_send.js` 를 **그대로 실행**해 본다.

def test_the_browser_side_asks_twice_and_carries_the_pick():
    """★ 확인 전에는 안 적는가 · 고른 기업과 사람이 그대로 실리는가.

    node 가 없는 환경(운영 도커 이미지)에서는 건너뛴다 — 브라우저 자산
    검사라 서버 실행에 필요한 의존성이 아니다.
    """
    import shutil
    import subprocess
    from pathlib import Path

    node = shutil.which("node")
    if node is None:
        pytest.skip("node 미설치 — 브라우저 로직 테스트 생략 "
                    "(호스트에서 `node tests/js/manual_send_test.js`)")
    js = Path(__file__).resolve().parent / "js" / "manual_send_test.js"
    result = subprocess.run([node, str(js)], capture_output=True,
                            text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr


def test_the_screen_really_draws_what_the_browser_test_assumes(me):
    """가짜 화면(`tests/js/_deals_dom.js`)이 **실제 화면과 같은 칸**을 세우는가.

    브라우저 검사는 지어낸 화면 위에서 돈다 — 그 화면이 진짜와 어긋나면
    검사는 통과하는데 실제로는 아무 것도 안 붙는다. 그래서 아이디는 여기서
    한 번 대조한다(`tests/test_deals_recipients.py` 가 하는 일과 같다).
    """
    page = me.get("/deals").text
    for anchor in ('id="manual-send"', 'id="manual-kind"', 'id="manual-day"',
                   'id="manual-count"', 'id="manual-count-wrap"',
                   'id="manual-btn"', 'id="manual-note"', 'id="manual-state"',
                   'id="manual-batches"', 'id="manual-batch-list"',
                   'js/manual_send.js'):
        assert anchor in page, f"화면에 {anchor} 가 없다"
    # 갈래·오늘 날짜는 **서버가 실어 준다** — 화면에 박아 두면 두 벌이 된다.
    assert f'data-today="{TODAY}"' in page
    for key in manual_send.KIND_LABELS:
        assert f'value="{key}"' in page
