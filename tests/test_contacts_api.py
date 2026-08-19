"""내 투자사 화면·API + 방 연결 확인 (ROADMAP 2.2/2.3/2.5)."""
from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.models import ContactActivity, SendItem, SendJob, VcContact

from .conftest import DEMO_TOKEN, OTHER_TOKEN, auth


@pytest.fixture()
def contacts(db, users):
    """user1 담당자 3명 (방 이름 있음/없음, 확인 상태 혼재) + user2 담당자 1명."""
    rows = [
        VcContact(user_id=1, name="홍길동", title="대표님", firm="가나벤처스", group_name="A그룹",
                  channel_kakao=1, channel_email=1, stages="Seed,SeriesA", sectors="AI,SaaS",
                  kakao_room_name="홍길동 대표님 가나벤처스 Deal 공유 우리브이씨 Asset",
                  room_verified="verified", status="active", memo="AI 인프라 선호"),
        VcContact(user_id=1, name="김서연", title="심사역", firm="마바벤처스", group_name="B그룹",
                  channel_kakao=1, stages="SeriesB", sectors="헬스케어",
                  kakao_room_name="김서연 심사역님 마바벤처스 Deal 공유 우리브이씨 Asset",
                  room_verified="unverified", status="no_response"),
        VcContact(user_id=1, name="박준호", firm="사아파트너스",
                  channel_email=1, status="paused"),   # 카톡방 이름 없음
        VcContact(user_id=2, name="최유진", title="팀장님", firm="자차인베스트",
                  channel_kakao=1, kakao_room_name="최유진 팀장님 자차인베스트", status="active"),
    ]
    db.add_all(rows)
    db.commit()
    return rows


# ── 표(SSR) ────────────────────────────────────────────────────────────────

def test_contacts_page_renders_seven_columns_without_scroll_hacks(client, contacts):
    r = client.get("/contacts")
    assert r.status_code == 200
    html = r.text
    # 7컬럼 폭 합계 100% (FEATURE_SPEC §3) — 가로 스크롤 0 의 근거
    widths = ["16%", "8%", "16%", "12%", "12%", "10%", "26%"]
    for w in widths:
        assert f"width:{w}" in html
    assert sum(int(w.rstrip("%")) for w in widths) == 100
    assert "table-layout" not in html  # 폭 제어는 CSS(.grid-table)에 있고 인라인 해킹이 없다


def test_page_shows_only_my_contacts(client, contacts):
    html = client.get("/contacts").text
    assert "홍길동" in html and "김서연" in html
    assert "최유진" not in html  # user2 담당자는 보이지 않는다 (RBAC)


def test_rows_carry_filter_attributes(client, contacts):
    """필터 컴포넌트는 행의 data-f-* 만 읽는다 — 다중 값은 '|' 로 나뉜다."""
    html = client.get("/contacts").text
    assert 'data-f-stage="Seed|SeriesA"' in html
    assert 'data-f-sector="AI|SaaS"' in html
    assert 'data-f-channel="카톡|메일"' in html
    assert 'data-f-status="활발"' in html
    assert 'data-f-room="● 확인됨"' in html
    assert 'data-f-room="○ 미확인"' in html
    assert 'data-f-room="⚠ 미등록"' in html   # 방 이름이 없는 담당자
    # 필터 대상 컬럼 헤더에 드롭다운이 붙는다
    assert 'data-filters="stage:단계|sector:섹터"' in html


def test_recent_deal_and_reaction_are_aggregated_not_stored(client, db, contacts):
    """'최근 딜소개'와 '반응'은 수기 입력이 아니라 이력에서 집계한다."""
    hong = db.execute(select(VcContact).where(VcContact.name == "홍길동")).scalar_one()
    today = date.today()
    db.add_all([
        ContactActivity(contact_id=hong.id, month=today.strftime("%Y-%m"), kind="deal_intro",
                        content="샘플애그, 샘플메디", happened_at=today.isoformat(), source="import"),
        ContactActivity(contact_id=hong.id, kind="ir_request", content="샘플애그 IR 요청",
                        happened_at=(today - timedelta(days=10)).isoformat(), source="import"),
        # 90일 밖 미팅은 '반응(90일)' 에 들어가지 않는다
        ContactActivity(contact_id=hong.id, kind="meeting", content="미팅 요청",
                        happened_at=(today - timedelta(days=200)).isoformat(), source="import"),
    ])
    db.commit()

    from app.routers.contacts import contact_rows
    from app.models import User

    rows = {r["name"]: r for r in contact_rows(db, db.get(User, 1))}
    hong_row = rows["홍길동"]
    assert hong_row["last_deal"] == today.isoformat()
    assert hong_row["recency"] == "7일 내"
    assert hong_row["ir_recent"] == 1 and hong_row["meet_recent"] == 0
    assert hong_row["meet_total"] == 1          # 누적에는 남는다
    assert hong_row["reaction_tags"] == ["IR 있음"]
    assert rows["박준호"]["reaction_tags"] == ["반응 없음"]
    assert rows["박준호"]["last_deal_label"] == "-"


def test_send_history_counts_as_recent_deal(client, db, contacts):
    """서비스에서 실제로 보낸 건도 '최근 딜소개'에 반영된다."""
    from app.models import User
    from app.routers.contacts import contact_rows

    hong = db.execute(select(VcContact).where(VcContact.name == "홍길동")).scalar_one()
    job = SendJob(user_id=1, kind="deal_intro", status="done", total=1)
    db.add(job)
    db.flush()
    db.add(SendItem(job_id=job.id, contact_id=hong.id, room_name=hong.kakao_room_name,
                    message="본문", status="sent", sent_at="2026-08-19T10:00:00"))
    db.commit()

    rows = {r["name"]: r for r in contact_rows(db, db.get(User, 1))}
    assert rows["홍길동"]["last_deal"] == "2026-08-19"


# ── CRUD / RBAC ────────────────────────────────────────────────────────────

def test_create_contact_autogenerates_room_name(client, contacts):
    r = client.post("/api/contacts", json={"name": "정민아", "title": "수석심사역",
                                           "firm": "자차인베스트", "channel_kakao": 1})
    assert r.status_code == 200
    assert r.json()["kakao_room_name"] == "정민아 수석심사역님 자차인베스트 Deal 공유 우리브이씨 Asset"


def test_detail_returns_timeline_of_import_and_system(client, db, contacts):
    hong = db.execute(select(VcContact).where(VcContact.name == "홍길동")).scalar_one()
    db.add(ContactActivity(contact_id=hong.id, month="2026-08", kind="deal_intro",
                           content="샘플애그", happened_at="2026-08-13", source="import"))
    job = SendJob(user_id=1, kind="deal_intro", status="done", total=1)
    db.add(job)
    db.flush()
    db.add(SendItem(job_id=job.id, contact_id=hong.id, room_name="방", message="본문",
                    status="sent", sent_at="2026-08-19T10:00:00"))
    db.commit()

    body = client.get(f"/api/contacts/{hong.id}").json()
    sources = [t["source"] for t in body["timeline"]]
    assert "import" in sources and "system" in sources


def test_timeline_shows_round_structure_for_viewing(client, db, contacts):
    """'월별로 특정 주·요일에 보낸 딜 리스트'를 화면에서 확인할 수 있어야 한다."""
    from app.models import IrCompany

    db.add(IrCompany(name="샘플애그", summary_status="draft"))
    hong = db.execute(select(VcContact).where(VcContact.name == "홍길동")).scalar_one()
    db.add(ContactActivity(
        contact_id=hong.id, month="2026-08", kind="deal_intro",
        content="샘플애그, 미등록기업", happened_at="2026-08-19", weekday="수",
        company_names='["샘플애그", "미등록기업"]', company_count=2,
        raw_text="8/19(수) 샘플애그, 미등록기업", source="import",
    ))
    db.commit()

    body = client.get(f"/api/contacts/{hong.id}").json()
    entry = next(t for t in body["timeline"] if t["date"] == "2026-08-19")
    assert entry["month"] == "2026-08" and entry["weekday"] == "수"
    assert entry["week"] == 3                      # 셋째 주 (운영 리듬과 대조 가능)
    assert entry["company_count"] == 2
    # 딜 기업 DB에 있는 기업만 표시가 다르되, 없는 기업도 원문 그대로 보인다
    assert entry["companies"] == [
        {"name": "샘플애그", "known": True},
        {"name": "미등록기업", "known": False},
    ]


def test_recent_deal_column_shows_count_and_weekday(client, db, contacts):
    from app.models import User
    from app.routers.contacts import contact_rows

    hong = db.execute(select(VcContact).where(VcContact.name == "홍길동")).scalar_one()
    db.add(ContactActivity(
        contact_id=hong.id, month="2026-08", kind="deal_intro", content="샘플애그, 샘플메디",
        happened_at="2026-08-19", weekday="수", company_names='["샘플애그", "샘플메디"]',
        company_count=2, source="import",
    ))
    db.commit()

    row = {r["name"]: r for r in contact_rows(db, db.get(User, 1))}["홍길동"]
    assert row["last_deal_label"] == "08.19(수)"
    assert row["last_deal_note"] == "2개사 · 샘플애그, 샘플메디"


def test_editing_room_name_resets_verification(client, db, contacts):
    """방 이름이 바뀌면 이전 '확인됨'은 근거가 아니다 → 미확인으로 되돌린다."""
    hong = db.execute(select(VcContact).where(VcContact.name == "홍길동")).scalar_one()
    r = client.patch(f"/api/contacts/{hong.id}",
                     json={"name": "홍길동", "kakao_room_name": "다른 방 이름"})
    assert r.status_code == 200 and r.json()["room_verified"] == "unverified"
    db.refresh(hong)
    assert hong.room_verified == "unverified"


def test_delete_removes_activities(client, db, contacts):
    hong = db.execute(select(VcContact).where(VcContact.name == "홍길동")).scalar_one()
    db.add(ContactActivity(contact_id=hong.id, kind="memo", content="메모", source="import"))
    db.commit()
    assert client.delete(f"/api/contacts/{hong.id}").status_code == 200
    assert db.query(ContactActivity).filter_by(contact_id=hong.id).count() == 0


def test_other_users_contact_is_not_reachable(client, db, contacts):
    other = db.execute(select(VcContact).where(VcContact.name == "최유진")).scalar_one()
    assert client.get(f"/api/contacts/{other.id}").status_code == 404
    assert client.patch(f"/api/contacts/{other.id}", json={"name": "x"}).status_code == 404
    assert client.delete(f"/api/contacts/{other.id}").status_code == 404


# ── 방 연결 확인 (2.5) ──────────────────────────────────────────────────────

def test_verify_rooms_queues_job_and_skips_contacts_without_room(client, db, contacts):
    r = client.post("/api/contacts/verify-rooms", json={})
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 2 and body["skipped"] == ["박준호"]

    job = db.get(SendJob, body["job_id"])
    assert job.kind == "verify_room" and job.status == "queued" and job.user_id == 1
    # 확인 잡에는 보낼 문구가 없다 (구버전 에이전트가 발송으로 오해해도 보낼 게 없다)
    assert all(i.message == "" for i in job.items)
    assert {i.room_name for i in job.items} == {
        "홍길동 대표님 가나벤처스 Deal 공유 우리브이씨 Asset",
        "김서연 심사역님 마바벤처스 Deal 공유 우리브이씨 Asset",
    }


def test_verify_rooms_rejects_when_nothing_to_check(client, db, contacts):
    park = db.execute(select(VcContact).where(VcContact.name == "박준호")).scalar_one()
    r = client.post("/api/contacts/verify-rooms", json={"contact_ids": [park.id]})
    assert r.status_code == 400


def test_verify_rooms_cannot_target_other_users_contacts(client, db, contacts):
    other = db.execute(select(VcContact).where(VcContact.name == "최유진")).scalar_one()
    r = client.post("/api/contacts/verify-rooms", json={"contact_ids": [other.id]})
    assert r.status_code == 400  # 내 것 중에 대상이 없다


def test_old_agent_never_receives_verify_jobs(client, contacts):
    """구버전 에이전트(kinds 미지정)는 확인 잡을 받지 않는다 — 발송으로 오해하면 사고다."""
    client.post("/api/contacts/verify-rooms", json={})
    assert client.get("/api/agent/poll", headers=auth(DEMO_TOKEN)).status_code == 204

    r = client.get("/api/agent/poll?kinds=deal_intro,ir_delivery,verify_room",
                   headers=auth(DEMO_TOKEN))
    assert r.status_code == 200 and r.json()["kind"] == "verify_room"


def test_verify_job_is_isolated_per_user(client, contacts):
    """사용자 1명 = 에이전트 1대. 남의 잡은 다른 토큰으로 절대 나가지 않는다."""
    client.post("/api/contacts/verify-rooms", json={})
    other = client.get("/api/agent/poll?kinds=deal_intro,verify_room", headers=auth(OTHER_TOKEN))
    assert other.status_code == 204


def test_verify_result_updates_room_badge(client, db, contacts):
    job_id = client.post("/api/contacts/verify-rooms", json={}).json()["job_id"]
    claimed = client.get("/api/agent/poll?kinds=verify_room", headers=auth(DEMO_TOKEN)).json()
    items = {i["room_name"]: i["id"] for i in claimed["items"]}

    hong_item = items["홍길동 대표님 가나벤처스 Deal 공유 우리브이씨 Asset"]
    kim_item = items["김서연 심사역님 마바벤처스 Deal 공유 우리브이씨 Asset"]
    client.post(f"/api/agent/items/{hong_item}/result",
                json={"status": "sent", "verify_result": "verified"}, headers=auth(DEMO_TOKEN))
    client.post(f"/api/agent/items/{kim_item}/result",
                json={"status": "failed", "verify_result": "ambiguous"}, headers=auth(DEMO_TOKEN))

    hong = db.execute(select(VcContact).where(VcContact.name == "홍길동")).scalar_one()
    kim = db.execute(select(VcContact).where(VcContact.name == "김서연")).scalar_one()
    db.refresh(hong); db.refresh(kim)
    assert hong.room_verified == "verified"
    assert kim.room_verified == "ambiguous"

    # 화면에서는 성공/실패로 읽힌다: 고쳐야 할 방이 실패 목록에 남는다
    status = client.get(f"/api/jobs/{job_id}").json()
    by_id = {i["id"]: i for i in status["items"]}
    assert by_id[hong_item]["status"] == "sent"
    assert by_id[kim_item]["status"] == "failed"
    assert "여러 개" in by_id[kim_item]["error"]


def test_verify_without_verdict_never_marks_verified(client, db, contacts):
    """판정이 없으면 '확인됨'으로 올리지 않는다 (모르면 미확인이 안전하다)."""
    client.post("/api/contacts/verify-rooms", json={})
    claimed = client.get("/api/agent/poll?kinds=verify_room", headers=auth(DEMO_TOKEN)).json()
    item_id = claimed["items"][0]["id"]
    client.post(f"/api/agent/items/{item_id}/result",
                json={"status": "sent"}, headers=auth(DEMO_TOKEN))

    db.expire_all()  # 서버가 같은 파일 DB를 따로 수정했으므로 캐시를 비우고 다시 읽는다
    item = db.get(SendItem, item_id)
    assert item.status == "failed"
    assert db.get(VcContact, item.contact_id).room_verified == "not_found"


def test_send_job_flow_is_untouched(client, db, contacts):
    """기존 발송 잡 흐름은 그대로 — 확인 기능이 끼어들지 않는다."""
    job = SendJob(user_id=1, kind="deal_intro", status="queued", total=1)
    db.add(job)
    db.flush()
    hong = db.execute(select(VcContact).where(VcContact.name == "홍길동")).scalar_one()
    db.add(SendItem(job_id=job.id, contact_id=hong.id, room_name=hong.kakao_room_name,
                    message="딜소개 본문", status="pending"))
    db.commit()

    claimed = client.get("/api/agent/poll", headers=auth(DEMO_TOKEN)).json()
    assert claimed["kind"] == "deal_intro"
    item_id = claimed["items"][0]["id"]
    client.post(f"/api/agent/items/{item_id}/result", json={"status": "sent"},
                headers=auth(DEMO_TOKEN))

    item = db.get(SendItem, item_id)
    db.refresh(item)
    assert item.status == "sent" and item.sent_at
    # 발송 결과가 담당자 방 확인 상태를 건드리지 않는다
    db.refresh(hong)
    assert hong.room_verified == "verified"
