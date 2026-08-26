"""딜 소싱 — 우리 딜을 같이 볼 사람 명단.

투자사 관리 현황(딜소개를 **보내는** 명단)과는 성격이 다르다. 여기는
무엇을 찾는지(시리즈 A 이상 · 개인 참여 · M&A · 후속투자)로 갈래가 나뉘고,
같은 사람이 여러 갈래에 들어갈 수 있다.
"""
from __future__ import annotations

import pytest

from .conftest import DEMO_PASSWORD


@pytest.fixture()
def seeded(client, db, users):
    from app.models import SourcingContact

    db.add_all([
        SourcingContact(bucket="시리즈 A 이상", position=0, name="홍길동",
                        title="심사역", firm="가나벤처스",
                        sectors="AI", round_size="10~30억"),
        SourcingContact(bucket="시리즈 A 이상", position=1, name="김철수",
                        title="팀장", firm="다라인베스트"),
        # 같은 사람이 다른 갈래에도 들어간다
        SourcingContact(bucket="M&A 찾는 투자사", position=1000, name="홍길동",
                        title="심사역", firm="가나벤처스"),
    ])
    db.commit()
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    return client


def test_the_menu_and_page_exist(seeded):
    body = seeded.get("/sourcing").text
    assert "딜 소싱" in body


def test_tabs_are_the_buckets_with_counts(seeded):
    body = seeded.get("/sourcing").text
    assert "시리즈 A 이상" in body
    assert "M&amp;A 찾는 투자사" in body or "M&A 찾는 투자사" in body
    # 어디에 사람이 있는지 알아야 한다
    assert ">2<" in body


def test_first_bucket_opens_by_default(seeded):
    """전체를 먼저 보여주면 갈래가 나뉜 뜻이 사라진다."""
    body = seeded.get("/sourcing").text
    assert "홍길동" in body and "김철수" in body


def test_the_same_person_can_be_in_two_buckets(seeded, db):
    from app.models import SourcingContact

    rows = db.query(SourcingContact).filter_by(name="홍길동").all()
    assert len(rows) == 2
    assert {r.bucket for r in rows} == {"시리즈 A 이상", "M&A 찾는 투자사"}


def test_rows_are_editable_in_place(seeded, db):
    from app.models import SourcingContact

    row = db.query(SourcingContact).filter_by(name="김철수").first()
    r = seeded.patch(f"/api/sourcing/{row.id}", json={"memo": "10월 통화 예정"})
    assert r.status_code == 200
    db.refresh(row)
    assert row.memo == "10월 통화 예정"


def test_the_name_cannot_be_emptied(seeded, db):
    """누구인지 모르는 줄이 남으면 안 된다."""
    from app.models import SourcingContact

    row = db.query(SourcingContact).filter_by(name="김철수").first()
    seeded.patch(f"/api/sourcing/{row.id}", json={"name": "  "})
    db.refresh(row)
    assert row.name == "김철수"


def test_every_column_has_a_cell(seeded):
    """머리글은 `columns` 를 돌지만 칸은 손으로 적혀 있다.

    컬럼을 늘리면서 칸을 안 만들면 머리글만 생기고 표가 한 칸씩 밀린다 —
    카톡방 이름 칸이 실제로 그렇게 빠졌었다.
    """
    import re

    from app.routers.sourcing import COLUMNS

    body = seeded.get("/sourcing").text
    head = body[body.index("<thead>"):body.index("</thead>")]
    first_row = body[body.index("<tbody>"):body.index("</tbody>")]
    first_row = first_row[:first_row.index("</tr>")]

    # 머리글 = # + 컬럼 수  (`<thead>` 자체가 걸리지 않게 경계를 본다)
    assert len(re.findall(r"<th[\s>]", head)) == len(COLUMNS) + 1
    assert len(re.findall(r"<td[\s>]", first_row)) == len(COLUMNS) + 1

    # 모든 컬럼이 눌러서 고칠 수 있어야 한다
    fields = set(re.findall(r'data-field="(\w+)"', first_row))
    assert fields == {f for f, _label, _w in COLUMNS}, fields


def test_the_room_name_is_editable(seeded, db):
    """여기서 방 이름을 못 넣으면 딜 소싱 제안을 아예 보낼 수 없다."""
    from app.models import SourcingContact

    row = db.query(SourcingContact).filter_by(name="김철수").first()
    r = seeded.patch(f"/api/sourcing/{row.id}",
                     json={"kakao_room_name": "김철수_소싱방"})
    assert r.status_code == 200
    db.refresh(row)
    assert row.kakao_room_name == "김철수_소싱방"


def test_changing_the_room_name_clears_the_check(seeded, db):
    """예전 확인은 다른 방 이야기다."""
    from app.models import SourcingContact

    row = db.query(SourcingContact).filter_by(name="김철수").first()
    row.kakao_room_name = "예전방"
    row.room_verified = "verified"
    db.commit()

    seeded.patch(f"/api/sourcing/{row.id}", json={"kakao_room_name": "새로운방"})
    db.refresh(row)
    assert row.room_verified == "unverified"


# --- 보내기 ----------------------------------------------------------------

def test_the_send_tab_is_open(seeded):
    body = seeded.get("/deals").text
    assert 'data-mode="sourcing"' in body
    assert "disabled" not in body[body.index('data-mode="sourcing"'):][:200]


def test_the_sourcing_list_is_its_own_picker(seeded):
    """투자사 명단과 한 표에 섞으면 딜소개를 보내면서 소싱 명단을 같이 고른다.

    그 둘은 받는 문구가 전혀 다르다.
    """
    body = seeded.get("/deals").text
    assert 'id="sourcing-list"' in body
    picker = body[body.index('id="sourcing-list"'):]
    assert "홍길동" in picker and "김철수" in picker
    # 갈래가 곧 문구다 — 무엇이 나갈지 고르는 자리에서 보여야 한다
    assert "시리즈 A 이상" in picker


def _filter_bar(body: str, bar_id: str) -> str:
    chunk = body[body.index('id="%s"' % bar_id):]
    return chunk[:chunk.index("</div>")]


def test_buckets_are_a_filter_not_a_search_term(seeded):
    """갈래 이름을 검색창에 쳐서 찾게 하면 갈래가 몇 개인지도 모른 채 골라야 한다."""
    bar = _filter_bar(seeded.get("/deals").text, "bucket-filter")

    assert 'data-value=""' in bar and "전체" in bar
    assert 'data-value="시리즈 A 이상"' in bar
    assert 'data-value="M&amp;A 찾는 투자사"' in bar
    # 어디에 사람이 있는지 알아야 어느 갈래부터 볼지 정한다
    assert "<b>2</b>" in bar


def test_assignee_is_a_filter_too(seeded, db):
    """39명을 통째로 훑는 것과 내 담당만 보는 것은 다른 일이다."""
    from app.models import SourcingContact

    for name, who in (("홍길동", "이영희"), ("김철수", "최민수")):
        db.query(SourcingContact).filter_by(name=name).update({"assignee_name": who})
    db.commit()

    body = seeded.get("/deals").text
    bar = _filter_bar(body, "assignee-filter")
    assert 'data-value="이영희"' in bar
    assert 'data-value="최민수"' in bar
    # 카드에 담당이 없으면 눌러서 거를 수가 없다
    picker = body[body.index('id="sourcing-list"'):]
    assert 'data-assignee="이영희"' in picker


def test_each_card_carries_its_bucket(seeded):
    """카드에 갈래가 없으면 눌러서 거를 수가 없다."""
    body = seeded.get("/deals").text
    picker = body[body.index('id="sourcing-list"'):]
    assert 'data-bucket="시리즈 A 이상"' in picker
    assert 'data-bucket="M&amp;A 찾는 투자사"' in picker


def test_the_sheets_summary_tail_is_not_a_name(seeded):
    """`이영희 (총 4명)` 을 그대로 두면 같은 사람이 둘로 갈린다."""
    from scripts.import_sourcing import assignee

    assert assignee("이영희 (총 4명)") == "이영희"
    assert assignee("최민수 (총 7명)") == "최민수"
    assert assignee("정하늘") == "정하늘"


def test_preview_uses_the_bucket_script(seeded, db):
    """갈래마다 호칭·개수가 다르다. 틀리면 문구 자체가 결례가 된다."""
    from app.models import SourcingContact

    boss = SourcingContact(bucket="딜 소싱  참여 투자사 대표", position=5,
                           name="이대표", title="대표", firm="마바캐피탈")
    db.add(boss)
    db.commit()
    analyst = db.query(SourcingContact).filter_by(name="김철수").first()

    r = seeded.post("/api/deals/preview",
                    json={"contact_ids": [boss.id, analyst.id], "mode": "sourcing"})
    assert r.status_code == 200
    by_name = {p["name"]: p["message"] for p in r.json()["previews"]}

    # 투자사 대표는 팀 전체가 본 딜을 쥐고 있어 5개사
    assert "5개사" in by_name["이대표"]
    assert "2개사" not in by_name["이대표"]

    # 개인 자격 심사역은 자기가 본 것만이라 2개사
    assert "2개사" in by_name["김철수"]
    # 시리즈 A 이상 갈래는 찾는 범위를 문구에 적는다
    assert "프리 IPO" in by_name["김철수"]
    assert "M&A , 후속투자" not in by_name["김철수"]


def test_a_missing_title_falls_back_to_the_bucket(seeded, db):
    """직함이 빈 줄이 있다. 그대로 두면 '안녕하세요, 홍길동' 으로 나간다."""
    from app.models import SourcingContact

    db.add(SourcingContact(bucket="딜 소싱  개인참여 심사역", position=7,
                           name="박무명", title=None, firm="사아벤처스"))
    db.commit()
    who = db.query(SourcingContact).filter_by(name="박무명").first()

    r = seeded.post("/api/deals/preview",
                    json={"contact_ids": [who.id], "mode": "sourcing"})
    assert "박무명 심사역님" in r.json()["previews"][0]["message"]


def test_preview_does_not_attach_companies(seeded, db):
    """소싱은 우리 딜을 보여 주는 게 아니라 **당신이 뺀 딜을 달라**는 초대다."""
    from app.models import IrCompany, SourcingContact

    db.add(IrCompany(name="샘플컴퍼니", one_liner="한 줄", sector_major="AI"))
    db.commit()
    company = db.query(IrCompany).filter_by(name="샘플컴퍼니").first()
    who = db.query(SourcingContact).filter_by(name="김철수").first()

    r = seeded.post("/api/deals/preview",
                    json={"contact_ids": [who.id], "company_ids": [company.id],
                          "mode": "sourcing"})
    assert r.status_code == 200
    assert "샘플컴퍼니" not in r.json()["previews"][0]["message"]


def test_send_records_against_the_sourcing_table(seeded, db):
    """투자사 담당자 표의 같은 번호를 가리키면 엉뚱한 사람에게 간 것으로 남는다."""
    from app.models import SendItem, SourcingContact

    who = db.query(SourcingContact).filter_by(name="김철수").first()
    who.kakao_room_name = "김철수_소싱방"
    db.commit()

    r = seeded.post("/api/deals/send",
                    json={"contact_ids": [who.id], "mode": "sourcing"})
    assert r.status_code == 200, r.text

    item = db.query(SendItem).filter_by(job_id=r.json()["job_id"]).one()
    assert item.contact_id is None
    assert item.sourcing_contact_id == who.id
    assert item.room_name == "김철수_소싱방"
    assert item.recipient_name == "김철수"


def test_send_blocks_when_there_is_no_room(seeded, db):
    """방 이름이 없으면 보낼 길이 없다 — 목록을 만들기 전에 막는다."""
    from app.models import SourcingContact

    who = db.query(SourcingContact).filter_by(name="홍길동").first()
    r = seeded.post("/api/deals/send",
                    json={"contact_ids": [who.id], "mode": "sourcing"})
    assert r.status_code == 400
    assert "카톡방" in r.json()["detail"]


def test_sourcing_sends_do_not_start_the_follow_up_ladder(seeded, db):
    """딜을 봐 달라는 초대에 '검토 중이신가요' 를 이어 보낼 것이 없다."""
    from app.models import SendItem, SendSequence, SourcingContact
    from app.services import cadence

    who = db.query(SourcingContact).filter_by(name="김철수").first()
    who.kakao_room_name = "김철수_소싱방"
    db.commit()
    job_id = seeded.post("/api/deals/send",
                         json={"contact_ids": [who.id], "mode": "sourcing"}).json()["job_id"]

    item = db.query(SendItem).filter_by(job_id=job_id).one()
    item.status = "sent"
    db.commit()
    assert cadence.start_or_advance(db, item, item.job) is None
    assert db.query(SendSequence).count() == 0


def test_the_importer_replaces_a_bucket_wholesale(db, users):
    """맞춰 넣으면 시트에서 지운 사람이 앱에 남는다."""
    import pathlib

    src = pathlib.Path("scripts/import_sourcing.py").read_text(encoding="utf-8")
    assert "delete(SourcingContact).where(SourcingContact.bucket == bucket)" in src

# --- 투자사 명단에서 방 이어받기 ---------------------------------------------
#
# 같은 사람이 두 표에 있다. 투자사 관리 현황에서 이미 카톡방까지 연결해 둔
# 사람이면 딜 소싱에서 방 이름을 다시 적을 이유가 없다 — 손으로 옮겨 적으면
# 한 글자만 달라도 발송이 통째로 skip 된다.

def _vc(db, users, name, phone, room, firm="가나벤처스"):
    from app.models import VcContact

    row = VcContact(user_id=users["u1"].id, name=name, firm=firm, phone=phone,
                    kakao_room_name=room, room_verified="verified",
                    connect_stage="connected", channel_kakao=1)
    db.add(row)
    db.commit()
    return row


def _sc(db, name, phone, bucket="시리즈 A 이상", room=None):
    from app.models import SourcingContact

    row = SourcingContact(bucket=bucket, position=90, name=name, phone=phone,
                          kakao_room_name=room)
    db.add(row)
    db.commit()
    return row


def test_the_room_comes_from_the_contact_list(seeded, db, users):
    from app.services import sourcing_link

    _vc(db, users, "박세준", "010-1111-2222", "박세준 이사님 가나벤처스 Deal 공유")
    who = _sc(db, "박세준", "010-1111-2222")

    linked = sourcing_link.linked_rooms(db, [who])
    assert linked[who.id]["room"] == "박세준 이사님 가나벤처스 Deal 공유"


def test_a_room_written_here_wins(seeded, db, users):
    """사람이 적은 것이 우선이다 — 이어받기가 덮으면 고칠 수가 없다."""
    from app.services import sourcing_link

    _vc(db, users, "박세준", "010-1111-2222", "투자사쪽 방")
    who = _sc(db, "박세준", "010-1111-2222", room="소싱쪽 방")

    assert who.id not in sourcing_link.linked_rooms(db, [who])
    assert sourcing_link.room_for(who, {}) == "소싱쪽 방"


def test_names_are_never_used_to_link(seeded, db, users):
    """같은 이름이 여럿 있다 — 이름으로 이으면 남의 방으로 나간다."""
    from app.services import sourcing_link

    _vc(db, users, "김형준", "010-3333-4444", "김형준 이사님 가나벤처스 Deal 공유")
    who = _sc(db, "김형준", "")          # 번호가 없다
    assert sourcing_link.linked_rooms(db, [who]) == {}


def test_a_shared_phone_links_to_nobody(seeded, db, users):
    """같은 번호가 둘이면 어느 쪽 방인지 알 수 없다 — 하나를 고르면 반은 틀린다."""
    from app.services import sourcing_link

    _vc(db, users, "홍길동", "010-5555-6666", "홍길동 방", firm="가나벤처스")
    _vc(db, users, "김서연", "010-5555-6666", "김서연 방", firm="다라인베스트")
    who = _sc(db, "홍길동", "010-5555-6666")
    assert sourcing_link.linked_rooms(db, [who]) == {}


def test_a_short_number_does_not_link(seeded, db, users):
    """내선번호끼리 우연히 맞아 엉뚱한 사람과 이어지면 안 된다."""
    from app.services import sourcing_link

    _vc(db, users, "홍길동", "1234", "홍길동 방")
    who = _sc(db, "박세준", "1234")
    assert sourcing_link.linked_rooms(db, [who]) == {}


def test_sending_uses_the_linked_room(seeded, db, users):
    from app.models import SendItem

    _vc(db, users, "박세준", "010-1111-2222", "박세준 이사님 가나벤처스 Deal 공유")
    who = _sc(db, "박세준", "010-1111-2222")

    r = seeded.post("/api/deals/send",
                    json={"contact_ids": [who.id], "mode": "sourcing"})
    assert r.status_code == 200, r.text
    item = db.query(SendItem).filter_by(job_id=r.json()["job_id"]).one()
    assert item.room_name == "박세준 이사님 가나벤처스 Deal 공유"
    assert item.sourcing_contact_id == who.id


def test_the_preview_says_where_the_room_came_from(seeded, db, users):
    """화면에는 '방 미등록' 인데 실제로는 나가면, 어디로 갈지 모른 채 누른다."""
    _vc(db, users, "박세준", "010-1111-2222", "박세준 이사님 가나벤처스 Deal 공유")
    who = _sc(db, "박세준", "010-1111-2222")

    r = seeded.post("/api/deals/preview",
                    json={"contact_ids": [who.id], "mode": "sourcing"})
    p = r.json()["previews"][0]
    assert p["room_name"] == "박세준 이사님 가나벤처스 Deal 공유"
    assert p["room_from"] == "투자사 명단"
    assert not p["room_warning"]

def test_the_default_preview_works_without_anyone_picked(seeded, db, users):
    """담당자를 고르기 전 기본 문구 미리보기가 터졌다.

    가상의 대상에는 휴대폰이 없는데, 방 이어받기가 그 번호를 읽으려다 멎었다.
    화면을 열자마자 나는 오류라 발송을 시작할 수조차 없었다.
    """
    _vc(db, users, "박세준", "010-1111-2222", "박세준 이사님 가나벤처스 Deal 공유")

    r = seeded.post("/api/deals/preview", json={"contact_ids": [], "mode": "sourcing"})
    assert r.status_code == 200, r.text
    p = r.json()["previews"][0]
    assert p["sample"] is True
    assert p["name"] == "○○○"          # 진짜 사람 이름이 아니어야 한다
    assert not p["room_warning"]        # 가상의 사람에게 방을 물을 것이 없다


def test_every_mode_previews_without_anyone_picked(seeded, db, users):
    """한 방식만 고쳐 두면 다른 방식에서 같은 자리가 다시 터진다."""
    for mode in ("deal", "ir", "remind", "meeting", "review", "ask", "sourcing"):
        r = seeded.post("/api/deals/preview", json={"contact_ids": [], "mode": mode})
        assert r.status_code == 200, f"{mode}: {r.text}"
        assert r.json()["previews"], mode

