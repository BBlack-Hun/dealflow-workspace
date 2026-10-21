"""딜 소싱 갈래 이름 — **띄어쓰기만 다르면 같은 갈래다.**

갈래는 `sourcing_contacts.bucket` 에 적힌 글자(원본 시트의 탭 이름)다. 같은 탭이
띄어쓰기만 달리 적혀 들어온다 — `딜소싱` · `딜 소싱` · 두 칸 공백. 글자 그대로
견주면 딜 소싱 화면에 탭이 둘 서고, 투자사 관리 현황의 O 가 코드의 글자
(`sourcing_sync.SYNC_BUCKET`)로 새 갈래를 만든다. 견줄 때만 띄어쓰기를 모두
빼고(`sourcing_buckets.key`), **저장된 글자는 고치지 않는다.**

  ① 딜 소싱 화면 — 탭 하나, 그 탭에 모든 글자의 줄, 수도 합친 것.
     딜 제안 관리의 갈래 칩 · 카드도 한 갈래로.
  ② 투자사 관리 현황의 O — 저장된 글자의 줄에서 같은 분을 찾아 잇고, 없으면
     **저장된 글자로** 새 줄을 만든다.
  ③ [추가] · 시트 가져오기 — 저장된 글자를 그대로 쓴다.
  ④ 잇는 갈래 판정 · Series A 딜 공유 · 방 이어받기 · A1 갈래가 같은 갈래로 본다.
  ⑤ 문구 — 어느 글자의 줄이든 같은 문구를 찾는다. 심는 문구도 한 벌.
  ⑥ 이름 바꾸기 — 잇는 갈래(Series A · M&A · 구주·후속)는 어느 글자로도 못 바꾸고,
     다른 갈래는 글자 전부가 간다.

이름 · 회사 · 번호는 전부 가상값이다(공개 저장소).
"""
from __future__ import annotations

import re
from datetime import datetime

import pytest

from .conftest import DEMO_PASSWORD

SYNC = "시리즈 A 이상 딜 소싱 참여 심사역"     # 코드의 글자(`SYNC_BUCKET`)
TIGHT = "시리즈 A 이상 딜소싱 참여 심사역"       # 띄어쓰기 하나 빠짐(로컬 DB)
WIDE = "시리즈 A 이상  딜 소싱 참여 심사역"      # 두 칸 공백(운영 시트 탭처럼)
MNA = "M&A 찾는 투자사"
MNA_WIDE = "M&A  찾는 투자사"
# 투자사 관리 현황과 잇지 않는 갈래(이름을 바꿀 수 있다) — 운영 시트 탭처럼 두 칸 공백.
CEO = "딜 소싱 참여 투자사 대표"
CEO_WIDE = "딜 소싱  참여 투자사 대표"
SHEET = "가상 투자사 명단"

SERIES_A_NAMES = ("홍길동", "김서연", "가심사", "나심사", "다심사")


def _login(client, phone: str = "01000000001"):
    client.post("/logout")
    r = client.post("/login", data={"phone": phone, "password": DEMO_PASSWORD})
    assert r.status_code in (200, 303), r.text
    return client


def _sc(db, name, bucket, position, **kw):
    from app.models import SourcingContact

    kw.setdefault("firm", "가나벤처스")
    row = SourcingContact(bucket=bucket, position=position, name=name, **kw)
    db.add(row)
    db.commit()
    return row


def _stored(db):
    """저장된 갈래 글자 — 무엇을 해도 고쳐 쓰지 않는다."""
    from app.models import SourcingContact

    db.expire_all()
    return {b for (b,) in db.query(SourcingContact.bucket).distinct()}


@pytest.fixture()
def spread(db, users):
    """시리즈 A 갈래가 세 글자로 갈려 있다(시트에서 셋 · O 로 하나 · 두 칸 하나).
    M&A 갈래도 두 칸 공백 글자로 하나 더."""
    rows = {
        "hong": _sc(db, "홍길동", TIGHT, 0, phone="010-0000-0001"),
        "kim": _sc(db, "김서연", TIGHT, 1, phone="010-0000-0002"),
        "park": _sc(db, "가심사", TIGHT, 2, phone="010-0000-0003"),
        "lee": _sc(db, "나심사", SYNC, 3, phone="010-0000-0004"),
        "choi": _sc(db, "다심사", WIDE, 4, phone="010-0000-0005"),
        "mna": _sc(db, "박다른", MNA, 1000, phone="010-0000-0006", firm="마바벤처스"),
        "mna2": _sc(db, "라다른", MNA_WIDE, 1001, phone="010-0000-0007",
                    firm="마바벤처스"),
    }
    return rows


# ── ① 탭 하나 ───────────────────────────────────────────────────────────────

def test_the_key_drops_every_space():
    """공백을 한 칸으로 줄이는 것만으로는 `딜소싱` 과 `딜 소싱` 이 같아지지 않는다."""
    from app.services import sourcing_buckets

    assert sourcing_buckets.key(TIGHT) == sourcing_buckets.key(SYNC) \
        == sourcing_buckets.key(WIDE) == sourcing_buckets.key(f" {SYNC}\t")
    assert sourcing_buckets.same(MNA, MNA_WIDE)
    assert not sourcing_buckets.same(SYNC, MNA)
    assert not sourcing_buckets.same("시리즈 a 이상 딜 소싱 참여 심사역", SYNC)  # 글자는 그대로


def test_one_tab_holds_every_spelling(db, users, spread):
    """탭은 갈래마다 하나 — 이름은 줄이 가장 많은 글자, 수는 합친 것."""
    from app.routers.sourcing import buckets

    tabs = buckets(db)
    assert [(t["label"], t["count"]) for t in tabs] == [(TIGHT, 5), (MNA, 2)]
    assert sorted(tabs[0]["variants"]) == sorted([TIGHT, SYNC, WIDE])


def test_the_tab_shows_every_spelling_whichever_spelling_opens_it(client, db, users,
                                                                  spread):
    """어느 글자로 열어도 같은 탭 — 그 탭에 세 글자의 줄이 다 보인다."""
    _login(client)
    for tab in (TIGHT, SYNC, WIDE):
        html = client.get("/sourcing", params={"tab": tab}).text
        assert html.count('class="sheet-tab ') == 3, tab     # 두 갈래 + 전체
        for name in SERIES_A_NAMES:
            assert name in html, (tab, name)
        assert "박다른" not in html and "라다른" not in html
        # [추가] 는 저장된 글자로 · `방 없음` 은 그 탭의 방 없는 줄 다섯 명
        assert f'data-bucket="{TIGHT}"' in html
        assert len(re.findall(r'<tr data-id="\d+" data-no-room', html)) == 5
    # [방 후보 찾기]는 고른 다섯을 어느 글자의 줄이든 다 찾는다 — 다른 갈래 줄은 빠진다
    from app.models import SendJob

    ids = [spread[k].id for k in ("hong", "kim", "park", "lee", "choi", "mna")]
    client.post("/sourcing/rooms/search",
                data={"tab": WIDE, "ids": ",".join(map(str, ids))})
    assert db.query(SendJob).one().total == 5
    html = client.get("/sourcing", params={"tab": MNA_WIDE}).text
    assert "박다른" in html and "라다른" in html
    assert _stored(db) == {TIGHT, SYNC, WIDE, MNA, MNA_WIDE}


def test_the_deal_page_shows_one_bucket(client, db, users, spread):
    """딜 제안 관리 › 딜 소싱 제안 — 갈래 칩 하나 · 카드도 같은 갈래 이름.

    카드의 `data-bucket` 이 저장된 글자 그대로면 칩을 눌렀을 때 다른 글자의
    분이 빠지고, Series A 딜 공유는 그 분을 고를 수 없다(`deals.js` 가 글자로 견준다).
    """
    _login(client)
    html = client.get("/deals").text
    assert f'data-value="{TIGHT}"' in html
    assert f'data-value="{SYNC}"' not in html and f'data-value="{WIDE}"' not in html
    assert html.count(f'data-bucket="{TIGHT}"') == 5 + 1       # 카드 다섯 + 공유 칩
    assert f'data-bucket="{SYNC}"' not in html
    assert f'data-bucket="{WIDE}"' not in html


# ── ② 투자사 관리 현황의 O ─────────────────────────────────────────────────

@pytest.fixture()
def board(client, db, users):
    from app.models import SheetOwner

    db.add(SheetOwner(label=SHEET, user_id=users["u1"].id, layout="investor"))
    db.commit()
    return _login(client)


def _vc(db, users, name, phone, **kw):
    from app.models import VcContact

    row = VcContact(user_id=users["u1"].id, name=name, firm="가나벤처스", title="심사역",
                    phone=phone, source_sheet=SHEET, room_verified="verified",
                    connect_stage="connected", channel_kakao=1, **kw)
    db.add(row)
    db.commit()
    return row


def _mark(client, contact_id, value):
    r = client.patch(f"/api/contacts/{contact_id}", json={"sourcing_join": value})
    assert r.status_code == 200, r.text
    return r.json()


def test_O_makes_the_new_row_under_the_stored_spelling(board, db, users):
    """그 갈래에 없는 분이면 새 줄 — **저장된 글자**로, 그 갈래 맨 아래에.

    고치기 전에는 코드의 글자(`딜 소싱`)로 만들어 딜 소싱 화면에 탭이 둘 섰다.
    """
    from app.models import SourcingContact

    _sc(db, "홍길동", TIGHT, 7, phone="010-0000-0001")
    contact = _vc(db, users, "김서연", "010-0000-0002")

    out = _mark(board, contact.id, "O")
    assert out["sourcing_join"] == "O"
    assert "새로 넣었습니다" in out["sourcing_msg"]
    row = db.query(SourcingContact).filter_by(vc_contact_id=contact.id).one()
    assert (row.bucket, row.position) == (TIGHT, 8)
    assert _stored(db) == {TIGHT}


def test_O_finds_the_same_person_under_another_spelling(board, db, users):
    """같은 분이 다른 글자의 줄에 있으면 **그 줄과 잇는다** — 새로 만들지 않는다."""
    from app.models import SourcingContact

    existing = _sc(db, "홍길동", WIDE, 0, phone="010-0000-0001")
    contact = _vc(db, users, "홍길동", "010-0000-0001")

    out = _mark(board, contact.id, "O")
    assert "이었습니다" in out["sourcing_msg"]
    db.expire_all()
    assert db.get(SourcingContact, existing.id).vc_contact_id == contact.id
    assert db.query(SourcingContact).count() == 1

    # 이어진 줄을 읽는 쪽(칸 · X)도 그 글자의 줄을 본다
    assert _mark(board, contact.id, "X")["sourcing_join"] == "X"
    db.expire_all()
    assert db.get(SourcingContact, existing.id).participation == "불참여"
    assert _stored(db) == {WIDE}


def test_an_edit_on_either_side_follows_on_a_spelling_variant(board, db, users):
    """이어진 두 줄의 같은 칸(`before_flush`)도 그 글자의 줄을 따라 고친다."""
    from app.models import SourcingContact

    row = _sc(db, "홍길동", TIGHT, 0, phone="010-0000-0001")
    contact = _vc(db, users, "홍길동", "010-0000-0001")
    _mark(board, contact.id, "O")

    r = board.patch(f"/api/contacts/{contact.id}", json={"title": "이사"})
    assert r.status_code == 200, r.text
    db.expire_all()
    assert db.get(SourcingContact, row.id).title == "이사"


# ── ③ 새 줄 · 시트 가져오기 ────────────────────────────────────────────────

def test_add_row_reuses_the_stored_spelling(client, db, users, spread):
    """[추가] 는 화면이 보낸 글자가 아니라 **그 갈래가 쓰는 글자**로 적는다 —
    자리도 세 글자 줄을 다 본 맨 아래."""
    from app.models import SourcingContact

    _login(client)
    r = client.post("/api/sourcing", params={"bucket": SYNC}, json={"name": "새심사"})
    assert r.status_code == 200, r.text
    assert r.json()["bucket"] == TIGHT
    row = db.get(SourcingContact, r.json()["id"])
    assert (row.bucket, row.position) == (TIGHT, 5)
    assert _stored(db) == {TIGHT, SYNC, WIDE, MNA, MNA_WIDE}


def test_the_sheet_import_replaces_every_spelling(db, users, spread, tmp_path,
                                                  monkeypatch):
    """시트를 다시 올리면 그 갈래의 **모든 글자** 줄을 갈아 끼우고, 저장된 글자를 쓴다."""
    import sys

    import openpyxl

    from app.models import SourcingContact
    from scripts import import_sourcing

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = SYNC                       # 시트 탭은 코드의 글자
    ws.append(["이름", "휴대폰", "회사"])
    ws.append(["시트심사", "010-0000-0011", "가나벤처스"])
    path = tmp_path / "sourcing.xlsx"
    wb.save(path)

    monkeypatch.setattr(sys, "argv", ["import_sourcing.py", str(path), "--apply"])
    import_sourcing.main()

    db.expire_all()
    rows = db.query(SourcingContact).filter(
        SourcingContact.bucket.in_([TIGHT, SYNC, WIDE])).all()
    assert [(r.bucket, r.name) for r in rows] == [(TIGHT, "시트심사")]
    assert _stored(db) == {TIGHT, MNA, MNA_WIDE}


# ── ④ 잇는 갈래 · Series A 딜 공유 · 방 · A1 ────────────────────────────────

def test_every_spelling_is_the_synced_bucket(db, users, spread):
    from app.services import series_a_share, sourcing_sync

    from app.models import SourcingContact

    for key in ("hong", "lee", "choi"):
        assert sourcing_sync.is_synced(spread[key]), key
        assert series_a_share.is_share_bucket(spread[key].bucket), key
    # M&A 도 투자사 관리 현황과 잇는 갈래다(2026-10-21 — 갈래 셋) — 어느 글자로든.
    # Series A 딜 공유는 그대로 시리즈 A 에만.
    for key in ("mna", "mna2"):
        assert sourcing_sync.is_synced(spread[key]), key
        assert sourcing_sync.branch_of(spread[key]) == MNA
    assert not series_a_share.is_share_bucket(MNA)
    assert not sourcing_sync.is_synced(SourcingContact(bucket=CEO_WIDE))


def test_series_a_share_sees_every_spelling(client, db, users, spread):
    """공유 심사역 짐작 · [이 분으로 확정] 이 다른 글자의 줄도 그 갈래로 본다."""
    from app.models import SeriesACompany
    from app.services import series_a_share

    company = SeriesACompany(name="샘플애그", received_at="2026-10-01",
                             shared_by="다심사 이사", source_firm="가나벤처스")
    db.add(company)
    db.commit()
    assert series_a_share.own_by_company(db, [company]) == {
        company.id: [spread["choi"].id]}

    _login(client)
    r = client.put(f"/api/series-a-companies/{company.id}/sharer",
                   json={"contact_id": spread["hong"].id})
    assert r.status_code == 200, r.text
    r = client.put(f"/api/series-a-companies/{company.id}/sharer",
                   json={"contact_id": spread["mna"].id})
    assert r.status_code == 400


def test_no_room_borrowing_for_any_spelling(db, users, spread):
    """시리즈 A 갈래는 투자사 방을 이어받지 않는다 — 어느 글자의 줄이어도."""
    from app.models import SheetOwner
    from app.services import sourcing_link

    db.add(SheetOwner(label=SHEET, user_id=users["u1"].id, layout="investor"))
    _vc(db, users, "다심사", "010-0000-0005", kakao_room_name="다심사 딜소개 방")
    _vc(db, users, "박다른", "010-0000-0006", kakao_room_name="박다른 딜소개 방")

    linked = sourcing_link.linked_rooms(db, list(spread.values()))
    assert spread["choi"].id not in linked
    assert linked[spread["mna"].id]["room"] == "박다른 딜소개 방"


def test_a1_groups_reach_every_spelling(db, users, spread):
    """A1 의 갈래(기본값 · 저장한 이름)는 띄어쓰기만 다른 글자의 줄도 데려간다."""
    from sqlalchemy import select

    from app.models import AutoSendSetting, SendItem
    from app.services import automation, automation_runner as runner

    users["u2"].role = "admin"
    db.add(AutoSendSetting(kind="startup_ir", enabled=1, user_id=users["u2"].id))
    for row in spread.values():
        row.kakao_room_name = f"{row.name} 소싱방"
    db.commit()
    automation.save(db, automation.SOURCING_REMIND, enabled=True, user_id=None,
                    test_mode=False, test_room="자동화 시험방")

    def run(when):
        runner.run_once(db, automation.SOURCING_REMIND, when.astimezone())
        db.expire_all()
        return {i.sourcing_contact_id
                for i in db.execute(select(SendItem)).scalars().all()}

    series_a = {spread[k].id for k in ("hong", "kim", "park", "lee", "choi")}
    assert run(datetime(2026, 10, 14, 9, 0)) == series_a          # 기본 갈래
    runner.save_params(db, automation.SOURCING_REMIND,
                       {"groups": "M&A   찾는 투자사", "weeks": "2,3",
                        "weekday": "수", "time": "11:00"})
    assert run(datetime(2026, 10, 21, 9, 0)) - series_a == {
        spread["mna"].id, spread["mna2"].id}


# ── ⑤ 문구 ──────────────────────────────────────────────────────────────────

def _tpl(db, kind, name, body, user_id=None):
    from app.models import MessageTemplate

    row = MessageTemplate(user_id=user_id, kind=kind, name=name, body=body, is_active=1)
    db.add(row)
    db.commit()
    return row


def test_every_spelling_finds_the_same_template(db, users, spread):
    from app.services import series_a_share, sourcing_msg

    user = users["u1"]
    _tpl(db, sourcing_msg.KIND, TIGHT, "시리즈 A 처음 안내")
    _tpl(db, series_a_share.KIND, SYNC, "공유 {기업 목록}")
    for bucket in (TIGHT, SYNC, WIDE):
        assert sourcing_msg.body_for(db, user, bucket) == "시리즈 A 처음 안내", bucket
        assert series_a_share.body_for(db, user, bucket) == "공유 {기업 목록}", bucket


def test_a_choice_is_one_per_bucket(client, db, users, spread):
    """팀 문구가 두 글자에 하나씩이면 한 갈래에 둘이다 — 고른 것이 어느 글자의
    줄에나 나가고, 다시 고르면 **그 선택을 갈아 끼운다**(둘이 쌓이지 않는다)."""
    from app.models import TemplateChoice
    from app.routers import templates_crud
    from app.services import sourcing_msg, template_pick

    user = users["u1"]
    kind = sourcing_msg.REMIND_KIND
    tight = _tpl(db, kind, TIGHT, "띄어쓰기 없는 글자 문구")
    sync = _tpl(db, kind, SYNC, "코드 글자 문구")
    # 한 자리에 팀 문구가 둘 — 고르기 전에는 아무것도 안 집는다(뼈대가 나간다)
    assert template_pick.pick(db, user.id, kind, WIDE) is None
    assert templates_crud._slots(kind, [tight, sync]) == [TIGHT]

    template_pick.set_choice(db, user.id, kind, sync.id, variant=SYNC)
    db.commit()
    for bucket in (TIGHT, SYNC, WIDE):
        assert template_pick.chosen_id(db, user.id, kind, bucket) == sync.id
    template_pick.set_choice(db, user.id, kind, tight.id, variant=TIGHT)
    db.commit()
    assert db.query(TemplateChoice).filter_by(kind=kind).count() == 1
    assert sourcing_msg.remind_body_for(db, user, WIDE) == "띄어쓰기 없는 글자 문구"
    # 문구 화면을 열 때 치우는 것(`prune`)이 이 선택을 죽은 것으로 보지 않는다
    _login(client)
    assert client.get("/templates").status_code == 200
    db.expire_all()
    assert template_pick.chosen_id(db, user.id, kind, SYNC) == tight.id


def test_seeding_plants_one_template_per_bucket(db, users, spread):
    """문구를 심는 것(`bootstrap`)도 갈래 하나에 한 벌 — 둘 심으면 위처럼 아무것도
    안 집혀 운영자가 고친 글 대신 뼈대가 나간다."""
    from app.models import MessageTemplate
    from app.services import series_a_share, sourcing_msg
    from scripts.bootstrap import seed_series_a_share, seed_sourcing_remind

    # 시리즈 A 하나 · M&A 하나(M&A 말로 쓴 글 — `sourcing_msg.remind_mna_body`)
    assert seed_sourcing_remind(db) == 2
    db.commit()
    assert seed_sourcing_remind(db) == 0
    names = {t.name for t in db.query(MessageTemplate).filter_by(kind=sourcing_msg.REMIND_KIND)}
    assert names == {TIGHT, MNA}

    _tpl(db, series_a_share.KIND, WIDE, "운영자가 고친 공유 글 {기업 목록}")
    assert seed_series_a_share(db) == 0


# ── ⑥ 이름 바꾸기 ──────────────────────────────────────────────────────────

def test_the_synced_bucket_cannot_be_renamed_under_any_spelling(db, users, spread):
    from app.services import sourcing_buckets

    for before in (TIGHT, SYNC, WIDE, MNA, MNA_WIDE):     # 잇는 갈래는 셋 다 못 바꾼다
        with pytest.raises(sourcing_buckets.RenameError):
            sourcing_buckets.rename(db, before, "새 갈래")
    assert _stored(db) == {TIGHT, SYNC, WIDE, MNA, MNA_WIDE}


def test_renaming_takes_every_spelling(db, users, spread):
    """탭 하나를 바꾸면 그 탭의 줄 · 문구가 **모든 글자에서** 함께 간다 —
    하나만 옮기면 남은 글자가 옛 이름의 유령 탭이 된다."""
    from app.models import MessageTemplate, SourcingContact
    from app.services import sourcing_buckets, sourcing_msg

    _sc(db, "박대표", CEO, 2000, phone="010-0000-0008")
    _sc(db, "라대표", CEO_WIDE, 2001, phone="010-0000-0009")
    _tpl(db, sourcing_msg.KIND, CEO_WIDE, "대표 문구")
    after = "딜 소싱 참여 투자사 대표 (2026)"
    assert sourcing_buckets.rename(db, CEO, after) == 2
    db.commit()
    assert {r.name for r in db.query(SourcingContact).filter_by(bucket=after)} == {
        "박대표", "라대표"}
    assert db.query(MessageTemplate).filter_by(name=after).count() == 1


def test_renaming_to_a_spacing_variant_keeps_one_choice(db, users, spread):
    """탭 이름의 두 칸 공백만 한 칸으로 고친다 — 그 갈래의 두 글자에 골라 둔 것이 하나씩
    있으면 읽히던 것(먼저 것) 하나만 남긴다. 옮기는 UPDATE 가 지우는 DELETE 보다 먼저
    나가면 (사람 · 종류 · 갈래) 유일 조건(`uq_template_choice_slot`)에 걸려 터졌다."""
    from app.models import TemplateChoice
    from app.services import sourcing_buckets, sourcing_msg

    user = users["u1"]
    kind = sourcing_msg.KIND
    _sc(db, "박대표", CEO, 2000, phone="010-0000-0008")
    _sc(db, "라대표", CEO_WIDE, 2001, phone="010-0000-0009")
    wide = _tpl(db, kind, CEO_WIDE, "두 칸 글자 문구")
    tight = _tpl(db, kind, CEO, "한 칸 글자 문구")
    db.add(TemplateChoice(user_id=user.id, kind=kind, variant=CEO_WIDE,
                          template_id=wide.id))
    db.commit()
    db.add(TemplateChoice(user_id=user.id, kind=kind, variant=CEO, template_id=tight.id))
    db.commit()

    assert sourcing_buckets.rename(db, CEO_WIDE, CEO) == 2
    db.commit()
    [choice] = db.query(TemplateChoice).filter_by(kind=kind).all()
    assert (choice.variant, choice.template_id) == (CEO, wide.id)
    assert _stored(db) == {TIGHT, SYNC, WIDE, MNA, MNA_WIDE, CEO}


def test_cannot_rename_onto_a_spelling_variant_of_another_bucket(db, users, spread):
    """띄어쓰기만 다른 이름은 이미 쓰는 이름이다 — 두 갈래가 한 덩어리가 된다."""
    from app.services import sourcing_buckets

    with pytest.raises(sourcing_buckets.RenameError):
        sourcing_buckets.rename(db, MNA, "시리즈A이상딜소싱참여심사역")
