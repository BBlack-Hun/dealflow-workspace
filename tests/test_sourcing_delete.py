"""딜 소싱 명단에서 사람 빼기.

넣는 길만 있고 빼는 길이 없었다 — 전화로 급히 적다가 이름을 잘못 넣어도
시트를 통째로 다시 올리는 것 말고는 방법이 없었다.

여기서 못 박는 것은 셋이다.
  1. **딸린 것** — 이 사람에게 보낸 발송 이력이 있으면 지우지 않는다.
     발송 이력은 "누구에게 언제 보냈나" 의 근거라 명단 한 줄보다 무겁다.
     (계정 삭제가 `AgentDevice` 때문에 막혔던 것과 같은 자리다)
  2. **닿을 수 있는 사람** — 로그인한 팀원만. 명단은 팀 공용이라 주인 칸이
     없고(`sourcing_contacts` 에 `user_id` 가 없다), 그래서 여기서 볼 수 있는
     경계는 로그인 여부와 역할뿐이다.
  3. **지운 뒤 화면** — 목록에서 빠지고 갈래별 인원 수가 맞아야 한다.

이름·회사는 모두 가상이다 — 저장소가 공개다.
"""
from __future__ import annotations

import pytest

from .conftest import DEMO_PASSWORD

BUCKET_A = "시리즈 A 이상"
BUCKET_B = "M&A 찾는 투자사"


@pytest.fixture()
def rows(db, users):
    """갈래 둘에 걸친 시험용 명단.

    같은 사람이 여러 갈래에 들어가는 것이 이 표의 성격이다 — 한쪽을 지울 때
    다른 쪽이 같이 사라지면 안 되므로 그 모양을 그대로 만들어 둔다.
    """
    from app.models import SourcingContact

    made = [
        SourcingContact(bucket=BUCKET_A, position=0, name="가나다",
                        title="심사역", firm="가나벤처스"),
        SourcingContact(bucket=BUCKET_A, position=1, name="라마바",
                        title="팀장", firm="다라인베스트"),
        # 같은 사람의 다른 갈래 줄
        SourcingContact(bucket=BUCKET_B, position=0, name="가나다",
                        title="심사역", firm="가나벤처스"),
    ]
    db.add_all(made)
    db.commit()
    return {"a1": made[0], "a2": made[1], "b1": made[2]}


@pytest.fixture()
def signed_in(client, rows):
    """일반 팀원(u1) 으로 로그인한 클라이언트."""
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    return client


def _still_there(db, row_id: int) -> bool:
    """이 줄이 명단에 남아 있는가.

    세션은 `expire_on_commit=False` 라 한 번 읽은 객체를 그대로 들고 있다 —
    다른 세션(앱)이 지운 뒤에도 살아 있는 것처럼 보인다. 매번 DB 에 다시 묻는다.
    """
    from app.models import SourcingContact

    db.expunge_all()
    return db.get(SourcingContact, row_id) is not None


def _fresh_client(phone: str = ""):
    """따로 로그인한 클라이언트.

    한 클라이언트로 로그인을 갈아타면 쿠키가 덮여 어느 사람으로 부른 것인지
    알 수 없게 된다(tests/test_consultant_access.py 와 같은 이유).
    `phone` 이 비면 **로그인하지 않은** 손님이다.
    """
    from fastapi.testclient import TestClient

    from app.main import create_app

    c = TestClient(create_app())
    if phone:
        r = c.post("/login", data={"phone": phone, "password": DEMO_PASSWORD},
                   follow_redirects=False)
        assert r.status_code == 303
    return c


# --- 지워진다 ---------------------------------------------------------------

def test_a_row_can_be_deleted(signed_in, db, rows):
    """잘못 넣은 사람을 뺄 길이 있어야 한다 — 여태 없었다."""
    row_id = rows["a2"].id
    r = signed_in.delete(f"/api/sourcing/{row_id}")
    assert r.status_code == 200, r.text
    assert r.json() == {"deleted": row_id}
    assert not _still_there(db, row_id)


def test_the_deleted_person_leaves_the_list(signed_in, rows):
    """지웠는데 화면에 남아 있으면 지운 줄 모르고 또 누른다."""
    assert "라마바" in signed_in.get(f"/sourcing?tab={BUCKET_A}").text
    signed_in.delete(f"/api/sourcing/{rows['a2'].id}")
    assert "라마바" not in signed_in.get(f"/sourcing?tab={BUCKET_A}").text


def test_the_bucket_count_follows(signed_in, db, rows):
    """탭의 갈래별 인원 수가 실제 줄 수와 어긋나면 어디에 사람이 있는지 못 믿는다."""
    from app.routers.sourcing import buckets

    signed_in.delete(f"/api/sourcing/{rows['a2'].id}")

    body = signed_in.get(f"/sourcing?tab={BUCKET_A}").text
    # 갈래는 2명 → 1명, 전체는 3명 → 2명
    assert f"{BUCKET_A} <span>1</span>" in body
    assert "전체 <span>2</span>" in body
    assert {b["key"]: b["count"] for b in buckets(db)} == {BUCKET_A: 1, BUCKET_B: 1}


def test_only_that_bucket_loses_the_row(signed_in, db, rows):
    """같은 사람이 여러 갈래에 들어간다 — 한쪽을 빼려고 눌렀는데 다른 쪽까지
    사라지면, 시리즈 A 에서만 빼려던 사람이 M&A 에서도 없어진다."""
    from app.models import SourcingContact

    signed_in.delete(f"/api/sourcing/{rows['a1'].id}")

    left = db.query(SourcingContact).filter_by(name="가나다").all()
    assert [r.bucket for r in left] == [BUCKET_B]


def test_the_delete_button_is_on_the_screen(signed_in):
    """경로만 있고 화면에 단추가 없으면 쓰는 사람에게는 없는 기능이다."""
    body = signed_in.get(f"/sourcing?tab={BUCKET_A}").text
    assert "js-sourcing-del" in body
    assert "/api/sourcing/" in body          # 화면 스크립트가 실제로 부른다


def test_the_confirm_names_who_is_being_deleted(signed_in):
    """되돌릴 수 없는 일이다 — 한 줄 밀려 눌러도 이름을 보고 알아채야 한다."""
    body = signed_in.get(f"/sourcing?tab={BUCKET_A}").text
    assert "confirm(" in body
    assert "되돌릴 수 없습니다" in body
    assert 'data-field="name"' in body       # 확인창에 넣을 이름을 여기서 읽는다


# --- 딸린 것: 발송 이력 -------------------------------------------------------

def _send_to(client, db, row, room="시험용_소싱방"):
    """이 사람에게 딜 소싱 제안을 한 번 보낸 상태를 만든다.

    손으로 `SendItem` 을 만들지 않고 실제 발송 경로를 지난다 — 이력이 어떤
    모양으로 남는지는 그 경로만 안다.
    """
    row.kakao_room_name = room
    db.commit()
    r = client.post("/api/deals/send",
                    json={"contact_ids": [row.id], "mode": "sourcing"})
    assert r.status_code == 200, r.text
    return r.json()


def test_a_person_with_send_history_is_not_deleted(signed_in, db, rows):
    """발송 이력은 "누구에게 언제 보냈나" 의 근거다 — 명단 한 줄보다 무겁다.

    그냥 지우면 운영 DB 는 외래키가 없어 조용히 넘어가고(alembic 0029 가
    `sourcing_contact_id` 를 그냥 Integer 로 붙였다) 발송 건이 없는 번호를
    가리킨 채 남는다. 테스트 DB 는 모델대로 외래키가 서 있어 같은 코드가
    IntegrityError 로 터진다. 어느 쪽도 답이 아니라 **막는다.**
    """
    who = rows["a1"]
    _send_to(signed_in, db, who)

    r = signed_in.delete(f"/api/sourcing/{who.id}")
    assert r.status_code == 400
    # 왜 안 되는지와 무엇을 하면 되는지가 같이 나와야 한다.
    detail = r.json()["detail"]
    assert "삭제할 수 없습니다" in detail
    assert "카톡방 이름" in detail
    assert _still_there(db, who.id)


def test_the_send_history_itself_survives_the_refusal(signed_in, db, rows):
    """막았는데 이력이 반쯤 지워져 있으면 막은 뜻이 없다."""
    from app.models import SendItem

    who = rows["a1"]
    _send_to(signed_in, db, who)
    signed_in.delete(f"/api/sourcing/{who.id}")

    item = db.query(SendItem).filter_by(sourcing_contact_id=who.id).one()
    assert item.recipient_name == "가나다"     # 이력이 가리키는 사람이 그대로다


def test_someone_elses_history_does_not_block_this_row(signed_in, db, rows):
    """옆 사람의 이력까지 세면, 한 번이라도 보낸 갈래는 통째로 못 지우게 된다."""
    _send_to(signed_in, db, rows["a1"])

    r = signed_in.delete(f"/api/sourcing/{rows['a2'].id}")
    assert r.status_code == 200, r.text
    assert not _still_there(db, rows["a2"].id)


def test_a_contact_send_does_not_block_a_sourcing_row(signed_in, db, rows, users):
    """발송 건은 투자사 담당자 또는 소싱 명단 **둘 중 하나**를 가리킨다.

    번호만 보고 세면 같은 번호의 투자사 담당자에게 보낸 이력이 엉뚱한 소싱
    줄을 붙잡는다 — 지울 수 있는 줄이 이유 없이 안 지워진다.
    """
    from app.models import SendItem, SendJob, VcContact

    contact = VcContact(user_id=users["u1"].id, name="사아자", firm="마바인베스트")
    db.add(contact)
    db.flush()
    job = SendJob(user_id=users["u1"].id, kind="deal_intro", status="queued",
                  total=1, sent=0, failed=0)
    db.add(job)
    db.flush()
    db.add(SendItem(job_id=job.id, contact_id=contact.id, sourcing_contact_id=None,
                    room_name="시험용_투자사방", message="본문", status="pending"))
    db.commit()

    r = signed_in.delete(f"/api/sourcing/{rows['a1'].id}")
    assert r.status_code == 200, r.text
    assert not _still_there(db, rows["a1"].id)


# --- 닿을 수 있는 사람 --------------------------------------------------------

def test_a_signed_out_visitor_cannot_delete(db, rows):
    """로그인 화면으로 보내면 스크립트는 성공한 줄 안다 — API 는 401 이다."""
    r = _fresh_client().delete(f"/api/sourcing/{rows['a1'].id}", follow_redirects=False)
    assert r.status_code == 401
    assert _still_there(db, rows["a1"].id)


def test_a_consultant_cannot_delete(db, rows):
    """투자컨설턴트는 자기 화면 하나만 쓴다 — 남의 명단에 닿으면 안 된다.

    이 표에는 주인 칸(`user_id`)이 없어 "내 명단 / 남의 명단" 이 나뉘지 않는다.
    소싱 명단은 IR 기업현황과 같은 **팀 공용**이라 명단 자체가 하나다
    (tests/test_data_scope.py 가 무엇이 공용이고 무엇이 내 것인지 못 박는다).
    그래서 여기서 지킬 수 있는 경계는 역할이고, 그 판정은 `app/main.py`
    미들웨어 한 곳에서만 한다.
    """
    from app.models import User
    from app.services import auth as auth_svc

    db.add(User(id=93, name="컨설턴트시험", phone="01000000093", role="consultant",
                password_hash=auth_svc.hash_password(DEMO_PASSWORD)))
    db.commit()

    r = _fresh_client("01000000093").delete(f"/api/sourcing/{rows['a1'].id}")
    assert r.status_code == 403
    assert "투자컨설턴트" in r.text
    assert _still_there(db, rows["a1"].id)


def test_a_teammate_can_delete_because_the_list_is_shared(db, rows):
    """명단이 팀 공용이라는 사실을 여기서 못 박는다.

    주인 칸이 생기는 날 이 검사가 깨진다 — 그때 삭제도 주인 검사를 해야
    한다는 신호다. 지금 조용히 열려 있는 것과, 그렇게 정한 것은 다르다.
    """
    r = _fresh_client("01000000002").delete(f"/api/sourcing/{rows['a1'].id}")
    assert r.status_code == 200, r.text
    assert not _still_there(db, rows["a1"].id)


# --- 없는 줄 -----------------------------------------------------------------

def test_a_missing_id_is_404(signed_in):
    """이미 지운 줄을 한 번 더 누르면(두 창을 열어 두면 생긴다) 500 이 아니라 404."""
    r = signed_in.delete("/api/sourcing/999999")
    assert r.status_code == 404
    assert "찾을 수 없습니다" in r.json()["detail"]


def test_deleting_twice_is_not_a_crash(signed_in, rows):
    assert signed_in.delete(f"/api/sourcing/{rows['a1'].id}").status_code == 200
    assert signed_in.delete(f"/api/sourcing/{rows['a1'].id}").status_code == 404


# --- 표가 밀리지 않는다 --------------------------------------------------------

def test_the_delete_button_did_not_add_a_column(signed_in):
    """단추를 칸으로 세우면 머리글과 칸 수가 어긋나 표가 한 칸씩 밀린다.

    (카톡방 이름 칸이 실제로 그렇게 빠졌었다 — tests/test_sourcing.py 참고)
    단추는 이름 칸 **안**에 들어간다.
    """
    import re

    from app.routers.sourcing import COLUMNS

    body = signed_in.get(f"/sourcing?tab={BUCKET_A}").text
    head = body[body.index("<thead>"):body.index("</thead>")]
    first_row = body[body.index("<tbody>"):body.index("</tbody>")]
    first_row = first_row[:first_row.index("</tr>")]

    assert len(re.findall(r"<th[\s>]", head)) == len(COLUMNS) + 1
    assert len(re.findall(r"<td[\s>]", first_row)) == len(COLUMNS) + 1
    assert "js-sourcing-del" in first_row
