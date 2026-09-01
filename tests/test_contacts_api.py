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

def test_contacts_columns_fit_without_horizontal_scroll(logged_in, contacts):
    """시트 컬럼 18개를 그대로 세우면 화면보다 넓다 — 그것 자체는 맞다.

    대신 **표 안에서만** 가로로 밀려야 한다. 페이지가 통째로 밀리면 좌측
    메뉴까지 따라 움직여 어디를 보고 있는지 잃는다.
    """
    import pathlib
    import re

    html = logged_in.get("/contacts").text
    head = html.split("</thead>")[0]
    head = head[head.index('id="contacts-table"'):]

    fixed, flexible = 0, 0
    for attrs, label in re.findall(r"<th(\s[^>]*)?>(.*?)</th>", head, re.S):
        if not re.sub(r"<[^>]+>", "", label).strip():
            continue
        px = re.search(r"width:\s*(\d+)px", attrs or "")
        if px:
            fixed += int(px.group(1))
        else:
            flexible += 1

    # 폭 없는 칸이 여럿이면 서로 자리를 뺏어 칸 너비가 들쭉날쭉해진다.
    assert flexible == 0, f"폭 없는 칸이 {flexible}개 — 서로 자리를 뺏는다"
    # 표가 제 감싸개 안에서 밀려야 한다(페이지가 통째로 밀리면 안 된다).
    assert 'class="table-wrap wide"' in html
    css = pathlib.Path("app/static/css/app.css").read_text(encoding="utf-8")
    assert "#contacts-table { min-width:" in css
    # 세로도 자른다 — 그래야 가로 스크롤바가 표 바로 아래 붙는다.
    rule = re.search(r"\.table-wrap\.wide\s*\{([^}]*)\}", css)
    assert rule, ".table-wrap.wide 규칙이 없습니다"
    assert re.search(r"overflow:\s*auto", rule.group(1))
    assert "max-height" in rule.group(1), (
        "높이를 안 자르면 가로 스크롤바가 문서 맨 아래로 밀린다")
    # 폭 제어는 th 에서 한다. 옛 colgroup 이 남아 있으면 그쪽이 이겨 버린다.
    assert "<colgroup" not in html


def test_page_shows_only_my_contacts(logged_in, contacts):
    html = logged_in.get("/contacts").text
    assert "홍길동" in html and "김서연" in html
    assert "최유진" not in html  # user2 담당자는 보이지 않는다 (RBAC)


def test_rows_carry_filter_attributes(logged_in, contacts):
    """필터 컴포넌트는 행의 data-f-* 만 읽는다 — 다중 값은 '|' 로 나뉜다.

    행이 싣는 값은 **그 칸이 화면에 보여 주는 것**이어야 한다. 라운드 사이즈
    칸의 필터가 `stages`(선호 단계)를 보고 있어서, 표에는 라운드가 52줄 적혀
    있는데 필터를 열면 늘 빈 목록이었다 — `stages` 는 값이 0줄이다.
    선호 단계는 표에 칸이 없어(상세 패널에서만 고친다) 필터에서 뺐다.

    방 연결(`data-f-room`)도 한동안 걷어내 두었는데, 대시보드가 `방 미등록
    6명` 을 눌러 `/contacts?room=…` 으로 들어오면서 **칸부터 세우고** 다시
    실었다. 값·말은 `dashboard.ROOM_LABELS` 한 곳에서 온다 — 세는 곳과 거는
    곳이 갈래를 따로 적으면 눌러 온 화면의 줄 수가 패널의 수와 어긋난다.
    짝이 어긋나는지는 tests/test_filter_columns.py 가 전 화면에서 훑는다.
    """
    html = logged_in.get("/contacts").text
    assert 'data-f-sector="AI|SaaS"' in html
    # 라운드 사이즈 칸이 보여 주는 그 값으로 거른다
    assert 'data-f-round=' in html
    assert 'data-f-stage=' not in html, "표에 칸이 없는 값으로 거르려 한다"
    # 방 상태는 칸(`카톡방`)과 머리글 선언이 함께 서 있다.
    assert 'data-filters="room:카톡방"' in html
    assert 'data-f-room=' in html, "칸을 세워 두고 행이 값을 안 싣는다"
    # 채널·상태는 시트에 없는 칸이라 컬럼과 함께 뺐다.
    assert 'data-f-dealstage=' in html      # 그 자리에 진행 단계가 있다
    # 필터 대상 컬럼 헤더에 드롭다운이 붙는다
    assert 'data-filters="sector:선호 투자분야"' in html
    # 컬럼 이름은 원본 시트를 그대로 따른다
    assert 'data-filters="round:라운드 사이즈(투자운영금액)"' in html


def test_recent_deal_and_reaction_are_aggregated_not_stored(logged_in, db, contacts):
    """'최근 딜소개'와 '반응'은 수기 입력이 아니라 이력에서 집계한다."""
    hong = db.execute(select(VcContact).where(VcContact.name == "홍길동")).scalar_one()
    today = date.today()
    db.add_all([
        ContactActivity(contact_id=hong.id, month=today.strftime("%Y-%m"), kind="deal_intro",
                        content="샘플애그, 샘플메디", happened_at=today.isoformat(), source="import"),
        ContactActivity(contact_id=hong.id, kind="ir_request", content="샘플애그 IR 요청",
                        happened_at=(today - timedelta(days=10)).isoformat(), source="import"),
        # 오래된 미팅. '최근'에는 안 잡히지만 **반응 태그에는 남는다** —
        # 반응은 한 번 오면 없어지는 것이 아니다.
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
    # 반응 태그는 **기간을 자르지 않는다**. 예전엔 최근 N일만 봐서 N+1일째에
    # 태그가 조용히 사라졌고, 대시보드에서 눌러 온 목록과 수가 어긋났다.
    assert hong_row["reaction_tags"] == ["IR 있음", "미팅 있음"]
    assert rows["박준호"]["reaction_tags"] == ["반응 없음"]
    assert rows["박준호"]["last_deal_label"] == "-"


def test_send_history_counts_as_recent_deal(logged_in, db, contacts):
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

def test_create_contact_autogenerates_room_name(logged_in, contacts):
    r = logged_in.post("/api/contacts", json={"name": "정민아", "title": "수석심사역",
                                           "firm": "자차인베스트", "channel_kakao": 1})
    assert r.status_code == 200
    assert r.json()["kakao_room_name"] == "정민아 수석심사역님 자차인베스트 Deal 공유 우리브이씨 Asset"


def test_detail_returns_timeline_of_import_and_system(logged_in, db, contacts):
    hong = db.execute(select(VcContact).where(VcContact.name == "홍길동")).scalar_one()
    db.add(ContactActivity(contact_id=hong.id, month="2026-08", kind="deal_intro",
                           content="샘플애그", happened_at="2026-08-13", source="import"))
    job = SendJob(user_id=1, kind="deal_intro", status="done", total=1)
    db.add(job)
    db.flush()
    db.add(SendItem(job_id=job.id, contact_id=hong.id, room_name="방", message="본문",
                    status="sent", sent_at="2026-08-19T10:00:00"))
    db.commit()

    body = logged_in.get(f"/api/contacts/{hong.id}").json()
    sources = [t["source"] for t in body["timeline"]]
    assert "import" in sources and "system" in sources


def test_timeline_shows_round_structure_for_viewing(logged_in, db, contacts):
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

    body = logged_in.get(f"/api/contacts/{hong.id}").json()
    entry = next(t for t in body["timeline"] if t["date"] == "2026-08-19")
    assert entry["month"] == "2026-08" and entry["weekday"] == "수"
    assert entry["week"] == 3                      # 셋째 주 (운영 리듬과 대조 가능)
    assert entry["company_count"] == 2
    # 딜 기업 DB에 있는 기업만 표시가 다르되, 없는 기업도 원문 그대로 보인다
    assert entry["companies"] == [
        {"name": "샘플애그", "known": True},
        {"name": "미등록기업", "known": False},
    ]


def test_recent_deal_column_shows_count_and_weekday(logged_in, db, contacts):
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


def test_editing_room_name_resets_verification(logged_in, db, contacts):
    """방 이름이 바뀌면 이전 '확인됨'은 근거가 아니다 → 미확인으로 되돌린다."""
    hong = db.execute(select(VcContact).where(VcContact.name == "홍길동")).scalar_one()
    r = logged_in.patch(f"/api/contacts/{hong.id}",
                     json={"name": "홍길동", "kakao_room_name": "다른 방 이름"})
    assert r.status_code == 200 and r.json()["room_verified"] == "unverified"
    db.refresh(hong)
    assert hong.room_verified == "unverified"


def test_delete_removes_activities(logged_in, db, contacts):
    hong = db.execute(select(VcContact).where(VcContact.name == "홍길동")).scalar_one()
    db.add(ContactActivity(contact_id=hong.id, kind="memo", content="메모", source="import"))
    db.commit()
    assert logged_in.delete(f"/api/contacts/{hong.id}").status_code == 200
    assert db.query(ContactActivity).filter_by(contact_id=hong.id).count() == 0


def test_other_users_contact_is_not_reachable(logged_in, db, contacts):
    other = db.execute(select(VcContact).where(VcContact.name == "최유진")).scalar_one()
    assert logged_in.get(f"/api/contacts/{other.id}").status_code == 404
    assert logged_in.patch(f"/api/contacts/{other.id}", json={"name": "x"}).status_code == 404
    assert logged_in.delete(f"/api/contacts/{other.id}").status_code == 404


# ── 방 연결 확인 (2.5) ──────────────────────────────────────────────────────

def test_verify_rooms_queues_job_and_skips_contacts_without_room(logged_in, db, contacts):
    r = logged_in.post("/api/contacts/verify-rooms", json={})
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


def test_verify_rooms_rejects_when_nothing_to_check(logged_in, db, contacts):
    park = db.execute(select(VcContact).where(VcContact.name == "박준호")).scalar_one()
    r = logged_in.post("/api/contacts/verify-rooms", json={"contact_ids": [park.id]})
    assert r.status_code == 400


def test_verify_rooms_cannot_target_other_users_contacts(logged_in, db, contacts):
    other = db.execute(select(VcContact).where(VcContact.name == "최유진")).scalar_one()
    r = logged_in.post("/api/contacts/verify-rooms", json={"contact_ids": [other.id]})
    assert r.status_code == 400  # 내 것 중에 대상이 없다


def test_old_agent_never_receives_verify_jobs(logged_in, contacts):
    """구버전 에이전트(kinds 미지정)는 확인 잡을 받지 않는다 — 발송으로 오해하면 사고다."""
    logged_in.post("/api/contacts/verify-rooms", json={})
    assert logged_in.get("/api/agent/poll", headers=auth(DEMO_TOKEN)).status_code == 204

    r = logged_in.get("/api/agent/poll?kinds=deal_intro,ir_delivery,verify_room",
                   headers=auth(DEMO_TOKEN))
    assert r.status_code == 200 and r.json()["kind"] == "verify_room"


def test_verify_job_is_isolated_per_user(logged_in, contacts):
    """사용자 1명 = 에이전트 1대. 남의 잡은 다른 토큰으로 절대 나가지 않는다."""
    logged_in.post("/api/contacts/verify-rooms", json={})
    other = logged_in.get("/api/agent/poll?kinds=deal_intro,verify_room", headers=auth(OTHER_TOKEN))
    assert other.status_code == 204


def test_verify_result_updates_room_badge(logged_in, db, contacts):
    job_id = logged_in.post("/api/contacts/verify-rooms", json={}).json()["job_id"]
    claimed = logged_in.get("/api/agent/poll?kinds=verify_room", headers=auth(DEMO_TOKEN)).json()
    items = {i["room_name"]: i["id"] for i in claimed["items"]}

    hong_item = items["홍길동 대표님 가나벤처스 Deal 공유 우리브이씨 Asset"]
    kim_item = items["김서연 심사역님 마바벤처스 Deal 공유 우리브이씨 Asset"]
    logged_in.post(f"/api/agent/items/{hong_item}/result",
                json={"status": "sent", "verify_result": "verified"}, headers=auth(DEMO_TOKEN))
    logged_in.post(f"/api/agent/items/{kim_item}/result",
                json={"status": "failed", "verify_result": "ambiguous"}, headers=auth(DEMO_TOKEN))

    hong = db.execute(select(VcContact).where(VcContact.name == "홍길동")).scalar_one()
    kim = db.execute(select(VcContact).where(VcContact.name == "김서연")).scalar_one()
    db.refresh(hong); db.refresh(kim)
    assert hong.room_verified == "verified"
    assert kim.room_verified == "ambiguous"

    # 화면에서는 성공/실패로 읽힌다: 고쳐야 할 방이 실패 목록에 남는다
    status = logged_in.get(f"/api/jobs/{job_id}").json()
    by_id = {i["id"]: i for i in status["items"]}
    assert by_id[hong_item]["status"] == "sent"
    assert by_id[kim_item]["status"] == "failed"
    assert "여러 개" in by_id[kim_item]["error"]


def test_verify_without_verdict_never_marks_verified(logged_in, db, contacts):
    """판정이 없으면 '확인됨'으로 올리지 않는다 (모르면 미확인이 안전하다)."""
    logged_in.post("/api/contacts/verify-rooms", json={})
    claimed = logged_in.get("/api/agent/poll?kinds=verify_room", headers=auth(DEMO_TOKEN)).json()
    item_id = claimed["items"][0]["id"]
    logged_in.post(f"/api/agent/items/{item_id}/result",
                json={"status": "sent"}, headers=auth(DEMO_TOKEN))

    db.expire_all()  # 서버가 같은 파일 DB를 따로 수정했으므로 캐시를 비우고 다시 읽는다
    item = db.get(SendItem, item_id)
    assert item.status == "failed"
    assert db.get(VcContact, item.contact_id).room_verified == "not_found"


def test_send_job_flow_is_untouched(logged_in, db, contacts):
    """기존 발송 잡 흐름은 그대로 — 확인 기능이 끼어들지 않는다."""
    job = SendJob(user_id=1, kind="deal_intro", status="queued", total=1)
    db.add(job)
    db.flush()
    hong = db.execute(select(VcContact).where(VcContact.name == "홍길동")).scalar_one()
    db.add(SendItem(job_id=job.id, contact_id=hong.id, room_name=hong.kakao_room_name,
                    message="딜소개 본문", status="pending"))
    db.commit()

    claimed = logged_in.get("/api/agent/poll", headers=auth(DEMO_TOKEN)).json()
    assert claimed["kind"] == "deal_intro"
    item_id = claimed["items"][0]["id"]
    logged_in.post(f"/api/agent/items/{item_id}/result", json={"status": "sent"},
                headers=auth(DEMO_TOKEN))

    item = db.get(SendItem, item_id)
    db.refresh(item)
    assert item.status == "sent" and item.sent_at
    # 발송 결과가 담당자 방 확인 상태를 건드리지 않는다
    db.refresh(hong)
    assert hong.room_verified == "verified"


# --- 활동 이력에 IR 요청·미팅이 들어간다 ----------------------------------------

def test_timeline_includes_meetings_and_requests(logged_in, db, contacts):
    """미팅을 잡고 완료 처리까지 해도 활동 이력에는 아무것도 안 남았다 —
    화면에서 한 일이 기록에 없는 것처럼 보였다."""
    from datetime import date

    from app.models import IrRequest, Meeting, VcContact

    hong = db.execute(select(VcContact).where(VcContact.name == "홍길동")).scalar_one()
    today = date.today().isoformat()
    db.add_all([
        IrRequest(user_id=hong.user_id, contact_id=hong.id, company_name="샘플애그",
                  status="delivered", requested_at=today),
        Meeting(user_id=hong.user_id, contact_id=hong.id, kind="first",
                status="done", outcome="reviewing", scheduled_at=today),
    ])
    db.commit()

    timeline = logged_in.get(f"/api/contacts/{hong.id}").json()["timeline"]
    kinds = [t["kind"] for t in timeline]
    assert "meeting" in kinds, "미팅이 활동 이력에 없다"
    assert "ir_request" in kinds, "IR 요청이 활동 이력에 없다"

    meeting = next(t for t in timeline if t["kind"] == "meeting")
    assert "1차 미팅" in meeting["content"]
    assert "검토 중" in meeting["content"]


def test_timeline_is_newest_first(logged_in, db, contacts):
    """출처별로 뭉쳐 두면 8월 미팅이 6월 기록 아래에 묻힌다."""
    from datetime import date

    from app.models import ContactActivity, Meeting, VcContact

    hong = db.execute(select(VcContact).where(VcContact.name == "홍길동")).scalar_one()
    db.add_all([
        ContactActivity(contact_id=hong.id, kind="deal_intro",
                        happened_at="2026-06-10", content="옛날 회차"),
        Meeting(user_id=hong.user_id, contact_id=hong.id, kind="first",
                status="planned", scheduled_at=date.today().isoformat()),
    ])
    db.commit()

    dates = [t["date"] for t in
             logged_in.get(f"/api/contacts/{hong.id}").json()["timeline"] if t["date"]]
    assert dates == sorted(dates, reverse=True), dates


# --- 시트 값이 화면 어디에서든 보여야 한다 --------------------------------------

def test_email_never_lands_in_the_address_field(db, users):
    """`전자 메일 주소` 에도 '주소' 가 들어 있다 — 빼지 않으면 이메일이
    주소 칸에 들어간다. 실제로 259건이 그랬다."""
    from app.services.sheet_import import find_column

    header = ["이름", "휴대폰", "전자 메일 주소", "근무처 전화", "근무지 주소 번지"]
    addr = find_column(header, ["주소"], exclude=["메일", "이메일", "전자"])
    assert header[addr] == "근무지 주소 번지"


def test_detail_panel_carries_every_sheet_field(logged_in, db, contacts):
    """표에 다 넣으면 20칸이 되어 정작 매일 보는 칸이 눌린다 — 가끔 찾는
    값은 상세에서 본다. **볼 곳이 아예 없으면 안 된다.**"""
    from app.models import VcContact

    hong = db.execute(select(VcContact).where(VcContact.name == "홍길동")).scalar_one()
    hong.address = "서울시 강남구 테헤란로 1"
    hong.office_phone = "02-1234-5678"
    hong.office_fax = "02-1234-5679"
    hong.card_registered_at = "2026-01-15"
    hong.interest_level = "높음"
    db.commit()

    got = logged_in.get(f"/api/contacts/{hong.id}").json()["contact"]
    for field in ("address", "office_phone", "office_fax",
                  "card_registered_at", "interest_level", "assignee_name"):
        assert field in got, f"상세에 {field} 가 없다"
    assert got["address"] == "서울시 강남구 테헤란로 1"

    # 화면에도 입력 칸이 있어야 고칠 수 있다
    html = logged_in.get("/contacts").text
    for field in ("address", "office_phone", "office_fax",
                  "card_registered_at", "interest_level"):
        assert f'id="f-{field}"' in html, f"화면에 {field} 칸이 없다"


def test_those_fields_can_be_edited(logged_in, db, contacts):
    from app.models import VcContact

    hong = db.execute(select(VcContact).where(VcContact.name == "홍길동")).scalar_one()
    r = logged_in.patch(f"/api/contacts/{hong.id}",
                        json={"address": "부산시 해운대구 센텀로 9"})
    assert r.status_code == 200
    db.refresh(hong)
    assert hong.address == "부산시 해운대구 센텀로 9"

# --- 명단(시트) 이름 바꾸기 --------------------------------------------------
#
# 참고 탭은 이름을 바꿀 수 있는데 명단 탭은 못 바꿨다. 원본 시트에서 이름을
# 다듬으면 앱만 옛 이름으로 남는다.

def _named(db, users, name, sheet):
    from app.models import VcContact

    row = VcContact(user_id=users["u1"].id, name=name, firm="가나벤처스",
                    source_sheet=sheet, connect_stage="connected")
    db.add(row)
    db.commit()
    return row


def test_a_list_sheet_can_be_renamed(logged_in, db, users):
    row = _named(db, users, "박준호", "옛 이름")
    r = logged_in.post("/api/contacts/sheets/rename",
                       data={"old": "옛 이름", "new": "새 이름"},
                       follow_redirects=False)
    assert r.status_code == 303
    db.refresh(row)
    assert row.source_sheet == "새 이름"


def test_renaming_does_not_smudge_the_other_lists(logged_in, db, users):
    """한 사람이 여러 명단에 겹친다 — 통째로 바꾸면 다른 명단까지 뭉개진다."""
    both = _named(db, users, "이서준", "옛 이름,다른 명단")
    logged_in.post("/api/contacts/sheets/rename",
                   data={"old": "옛 이름", "new": "새 이름"}, follow_redirects=False)
    db.refresh(both)
    assert both.source_sheet == "새 이름,다른 명단"


def test_an_empty_new_name_is_refused(logged_in, db, users):
    """이름 없는 탭은 누를 자리가 없어진다."""
    row = _named(db, users, "정민아", "옛 이름")
    logged_in.post("/api/contacts/sheets/rename",
                   data={"old": "옛 이름", "new": "   "}, follow_redirects=False)
    db.refresh(row)
    assert row.source_sheet == "옛 이름"


def test_the_owner_mapping_follows_the_rename(logged_in, db, users):
    """담당은 명단 이름으로 붙어 있다 — 이름만 바꾸면 담당이 끊긴다."""
    from app.models import SheetOwner

    _named(db, users, "홍길동2", "옛 이름")
    db.add(SheetOwner(label="옛 이름", user_id=users["u1"].id))
    db.commit()

    logged_in.post("/api/contacts/sheets/rename",
                   data={"old": "옛 이름", "new": "새 이름"}, follow_redirects=False)
    db.expire_all()
    labels = {o.label for o in db.query(SheetOwner).all()}
    assert "새 이름" in labels and "옛 이름" not in labels


def test_달_칸과_달_표시도_이름을_따라온다(logged_in, db, users):
    """이름은 설정 줄에만 있는 것이 아니다.

    `ContactColumn.sheet` 와 `MonthlyColumnRun.scope` 도 이름을 **문자열로**
    담고 있다. 안 따라가면 그 명단의 달 칸이 통째로 사라진 것처럼 보이고
    (값은 남았는데 칸이 없어 화면이 못 그린다), 사람이 일부러 지운 이번 달
    칸이 다음 요청에서 되살아난다.
    """
    from app.models import ContactColumn, MonthlyColumnRun, SheetOwner

    _named(db, users, "한지우", "옛 이름")
    db.add(SheetOwner(label="옛 이름", user_id=users["u1"].id))
    db.add(ContactColumn(sheet="옛 이름", label="8월 딜소개", position=0))
    db.add(MonthlyColumnRun(target="contact", scope="옛 이름", month="2026-08",
                            labels="[]"))
    db.commit()

    logged_in.post("/api/contacts/sheets/rename",
                   data={"old": "옛 이름", "new": "새 이름"}, follow_redirects=False)
    db.expire_all()
    assert [c.sheet for c in db.query(ContactColumn).all()] == ["새 이름"], (
        "달 칸이 옛 이름에 남았습니다 — 그 명단 탭에서 칸이 사라집니다")
    assert [r.scope for r in db.query(MonthlyColumnRun).all()] == ["새 이름"]


def test_이미_쓰고_있는_이름으로는_못_바꾼다(logged_in, db, users):
    """두 명단이 같은 이름이면 **서로를 덮는다.**

    이름이 곧 열쇠라(`source_sheet` 가 이름을 담는다) 섞이고 나면 어느 줄이
    원래 어느 명단 것이었는지 되돌릴 근거가 없다. 담당도 배치도 딜소개 표시도
    한 벌만 남는다.
    """
    from app.models import SheetOwner

    mine = _named(db, users, "서지안", "내 명단")
    other = _named(db, users, "노하은", "남의 명단")
    db.add(SheetOwner(label="내 명단", user_id=users["u1"].id))
    db.add(SheetOwner(label="남의 명단", user_id=users["u2"].id))
    db.commit()

    r = logged_in.post("/api/contacts/sheets/rename",
                       data={"old": "내 명단", "new": "남의 명단"},
                       follow_redirects=False)
    assert r.status_code == 303
    db.expire_all()
    assert mine.source_sheet == "내 명단", "두 명단이 한 탭으로 섞였습니다"
    assert other.source_sheet == "남의 명단"
    assert {o.label for o in db.query(SheetOwner).all()} == {"내 명단", "남의 명단"}
    # **왜 안 됐는지 화면이 말해야 한다** — 조용히 돌아가면 저장된 줄 안다.
    assert "msg=" in r.headers["location"]


def test_쉼표가_든_이름은_받지_않는다(logged_in, db, users):
    """`source_sheet` 는 쉼표로 이어 붙인 목록이다(한 사람이 여러 명단에 겹친다).

    이름에 쉼표가 들어가면 줄은 그대로인데 탭만 둘로 갈라져 읽힌다.
    """
    row = _named(db, users, "임도윤", "옛 이름")
    logged_in.post("/api/contacts/sheets/rename",
                   data={"old": "옛 이름", "new": "앞, 뒤"}, follow_redirects=False)
    db.refresh(row)
    assert row.source_sheet == "옛 이름"

# --- 화면에서 고친 값이 실제로 저장되는가 --------------------------------------
#
# 스키마(`ContactIn`)에 칸을 더해 놓고 `_assign` 의 저장 목록에 안 넣으면,
# 요청은 **200 으로 끝나는데 값은 그대로**다. 화면에서는 저장된 것처럼 보이고
# 새로고침해야 안 들어간 것을 안다 — `tips_note` 가 실제로 그랬다.

def test_every_editable_field_is_actually_saved():
    """스키마에 있는데 저장 목록에서 빠지면 조용히 안 들어간다."""
    import pathlib
    import re

    src = pathlib.Path("app/routers/contacts.py").read_text(encoding="utf-8")
    schema = re.search(r"class ContactIn\(BaseModel\):(.*?)\n\nclass ", src, re.S)
    assert schema, "ContactIn 을 찾지 못했습니다"
    fields = set(re.findall(r"^\s{4}(\w+):", schema.group(1), re.M))

    assign = re.search(r"def _assign.*?for field in \((.*?)\):", src, re.S)
    assert assign, "_assign 의 저장 목록을 찾지 못했습니다"
    listed = set(re.findall(r'"(\w+)"', assign.group(1)))

    # 목록 밖에서 따로 다루는 칸들. **손으로 적어 두지 않는다** — 그렇게 두면
    # 따로 다루는 칸이 하나 늘 때마다 여기도 고쳐야 하고, 고치는 김에 정작
    # 빠뜨린 칸까지 같이 적어 넣게 된다. 라우터가 `body.칸` 으로 실제로 읽는
    # 것을 세면, "스키마에만 있고 아무도 안 읽는 칸" 이라는 진짜 버그만 남는다.
    handled = listed | set(re.findall(r"body\.(\w+)", src))
    missing = sorted(fields - handled)
    assert not missing, f"고쳐도 저장되지 않는 칸: {missing}"


def test_the_sheet_only_columns_can_be_edited(logged_in, db, users):
    """시트에만 있던 칸도 화면에서 고쳐야 한다 — 안 되면 시트를 다시 올려야 한다."""
    from app.models import VcContact

    row = VcContact(user_id=users["u1"].id, name="홍길동", firm="가나벤처스")
    db.add(row)
    db.commit()

    r = logged_in.patch(f"/api/contacts/{row.id}", json={
        "tips_note": "O", "kakao_joined": "O", "sourcing_note": "참여 의사 있음"})
    assert r.status_code == 200
    db.refresh(row)
    assert row.tips_note == "O"
    assert row.kakao_joined == "O"
    assert row.sourcing_note == "참여 의사 있음"

def test_the_detail_panel_can_read_and_write_every_table_column():
    """표에 있는 칸은 [수정] 창에서도 적을 수 있어야 한다.

    한 칸이 화면에 뜨려면 **네 곳**이 맞아야 한다: 창의 입력칸(`id="f-…"`) ·
    JS 의 `FIELDS` · 저장 스키마(`ContactIn`+`_assign`) · 조회 응답(`get_contact`).
    한 곳만 빠져도 조용히 어긋난다 — `TIPS 운영사` 는 창에 칸이 없었고,
    칸을 그린 뒤에도 조회에서 안 돌려줘 **저장은 되는데 다시 열면 비어** 있었다.
    """
    import pathlib
    import re

    html = pathlib.Path("app/templates/contacts.html").read_text(encoding="utf-8")
    js = pathlib.Path("app/static/js/contacts.js").read_text(encoding="utf-8")
    py = pathlib.Path("app/routers/contacts.py").read_text(encoding="utf-8")

    row = re.search(r'id="contacts-table".*?<tbody>(.*?)</tr>', html, re.S)
    table = set(re.findall(r'data-field="([a-z_]+)"', row.group(1)))

    panel = set(re.findall(r'id="f-([a-z_]+)"', html))
    fields = set(re.findall(r'"([a-z_]+)"',
                            re.search(r"var FIELDS = \[(.*?)\];", js, re.S).group(1)))
    detail = set(re.findall(r'"([a-z_]+)": contact\.', py))
    saved = set(re.findall(r'"([a-z_]+)"',
                           re.search(r"def _assign.*?for field in \((.*?)\):", py, re.S).group(1)))
    saved |= {"name"}

    assert not table - panel, f"창에 칸이 없다: {sorted(table - panel)}"
    assert not table - fields, f"JS 목록에 없어 안 채워진다: {sorted(table - fields)}"
    assert not table - detail, f"조회가 안 돌려줘 다시 열면 빈다: {sorted(table - detail)}"
    assert not table - saved, f"저장되지 않는다: {sorted(table - saved)}"


def test_an_empty_cell_is_still_clickable():
    """빈 칸을 눌러도 입력창이 안 뜨고 [수정] 창이 열렸다.

    `.clamp2` 는 `-webkit-box` 라 내용이 없으면 높이가 0 이 된다 — 누를 자리가
    없어 클릭이 뒤의 행으로 흘러간다. `TIPS 운영사` 는 306행 중 303행이 빈칸이라
    사실상 늘 그랬다.
    """
    import pathlib
    import re

    css = pathlib.Path("app/static/css/app.css").read_text(encoding="utf-8")
    rule = re.search(r"\.cell\[data-field\]\s*\{([^}]*)\}", css)
    assert rule, ".cell[data-field] 규칙이 없습니다"
    assert re.search(r"min-height:\s*[\d.]+", rule.group(1)), (
        "빈 칸에 높이를 주지 않으면 누를 자리가 없다")

