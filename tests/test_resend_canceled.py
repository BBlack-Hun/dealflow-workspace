"""취소분 재발송 — [중단] 으로 남은 사람에게만 다시 보낸다.

발송 도중 [중단]을 누르면 아직 안 나간 사람이 `canceled` 로 남는다. 남은 사람에게
다시 보내는 길이 없어서, 발송 목록을 처음부터 다시 만들며 **이미 받은 사람을 손으로
골라내야** 했다. 한 명만 실수해도 같은 사람에게 두 번 나간다.

여기서 지키려는 것.

1. **이미 나간 사람(`sent`)은 절대 다시 대기로 가지 않는다.** 발송은 되돌릴 수 없다.
   이 파일에서 가장 중요한 검사다.
2. 되살리는 것은 **취소 건뿐**이다. 실패 건은 [실패 재시도] 가 따로 맡는다.
3. **채널마다 제 길로 간다.** 카톡 건은 발송 프로그램이 집어가고, 메일 건은 서버가
   직접 보낸다. 한쪽만 되돌리면 나머지가 영원히 대기로 남는다.
4. 되살릴 것이 없으면 400 — 아무 일도 안 일어났는데 성공으로 보이면 안 된다.
"""
from __future__ import annotations

import pytest

from .conftest import DEMO_PASSWORD, DEMO_TOKEN


@pytest.fixture()
def logged(client, users):
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    return client


def _job(db, user_id: int, items: list[dict], status: str = "canceled"):
    """`items` = [{"status": …, "channel": …}, …] 순서대로 만든 회차.

    받는 사람 정보는 이 검사와 무관하므로 방 이름만 번호로 채운다(공개 저장소라
    실제 상호·주소를 넣지 않는다).
    """
    from app.models import SendItem, SendJob

    job = SendJob(user_id=user_id, kind="deal_intro", status=status,
                  total=len(items), finished_at="2026-08-19T10:00:00")
    db.add(job)
    db.flush()
    rows = []
    for index, spec in enumerate(items, start=1):
        channel = spec.get("channel", "kakao")
        row = SendItem(
            job_id=job.id,
            channel=channel,
            room_name=(f"받는사람{index}@example.com" if channel == "email"
                       else f"받는사람{index} 심사역님"),
            subject="딜 소개" if channel == "email" else None,
            message="문구",
            status=spec["status"],
            sent_at="2026-08-19T10:00:00" if spec["status"] == "sent" else None,
        )
        db.add(row)
        rows.append(row)
    db.commit()
    return job, rows


def _statuses(db, job_id: int) -> list[str]:
    from sqlalchemy import select

    from app.models import SendItem

    db.expire_all()
    return list(db.execute(
        select(SendItem.status).where(SendItem.job_id == job_id)
        .order_by(SendItem.id)
    ).scalars())


# --- 무엇이 되살아나는가 ----------------------------------------------------

def test_only_canceled_items_go_back_to_pending(logged, db, users):
    """취소된 건만 대기로 돌아간다."""
    job, _ = _job(db, users["u1"].id, [
        {"status": "sent"}, {"status": "canceled"}, {"status": "canceled"},
    ])

    r = logged.post(f"/api/jobs/{job.id}/resend-canceled")

    assert r.status_code == 200, r.text
    assert r.json()["requeued"] == 2
    assert _statuses(db, job.id) == ["sent", "pending", "pending"]


def test_sent_items_are_never_requeued(logged, db, users):
    """**이미 나간 사람에게 두 번 보내면 안 된다.** 이 기능에서 가장 위험한 부분이다.

    취소 건 하나 사이에 성공 건을 끼워 둔다 — 잘못 훑으면 함께 딸려 들어간다.
    """
    job, rows = _job(db, users["u1"].id, [
        {"status": "sent"}, {"status": "canceled"}, {"status": "sent"},
        {"status": "canceled"}, {"status": "sent"},
    ])
    sent_ids = [row.id for row in rows if row.status == "sent"]

    r = logged.post(f"/api/jobs/{job.id}/resend-canceled")
    assert r.status_code == 200, r.text

    assert _statuses(db, job.id) == ["sent", "pending", "sent", "pending", "sent"]
    assert r.json()["requeued"] == 2, "성공 건까지 세었습니다"

    # 발송 시각도 그대로여야 한다 — 지워지면 "언제 보냈나" 가 끊긴다.
    from app.models import SendItem
    for item_id in sent_ids:
        item = db.get(SendItem, item_id)
        assert item.status == "sent"
        assert item.sent_at == "2026-08-19T10:00:00"


def test_failed_items_are_left_to_the_retry_button(logged, db, users):
    """실패 건은 [실패 재시도] 가 맡는다.

    취소분만 보내려던 사람이 사유도 못 본 실패 건까지 내보내게 되면 그것도
    예상 밖의 발송이다.
    """
    job, _ = _job(db, users["u1"].id, [
        {"status": "failed"}, {"status": "canceled"},
    ])

    r = logged.post(f"/api/jobs/{job.id}/resend-canceled")

    assert r.status_code == 200, r.text
    assert _statuses(db, job.id) == ["failed", "pending"]


def test_nothing_canceled_is_a_400(logged, db, users):
    """되살릴 것이 없는데 성공으로 보이면, 눌렀는데 아무 일도 안 난 줄 모른다."""
    job, _ = _job(db, users["u1"].id, [
        {"status": "sent"}, {"status": "failed"},
    ], status="done_with_errors")

    r = logged.post(f"/api/jobs/{job.id}/resend-canceled")

    assert r.status_code == 400
    assert "취소" in r.json()["detail"]
    assert _statuses(db, job.id) == ["sent", "failed"], "막았는데 상태가 바뀌었습니다"


def test_other_users_job_is_not_reachable(logged, db, users):
    """남의 회차를 되살리면 그 사람 이름으로 문구가 나간다."""
    job, _ = _job(db, users["u2"].id, [{"status": "canceled"}])

    r = logged.post(f"/api/jobs/{job.id}/resend-canceled")

    assert r.status_code == 404
    assert _statuses(db, job.id) == ["canceled"]


# --- 채널마다 제 길로 -------------------------------------------------------

def test_kakao_items_are_handed_back_to_the_agent(logged, client, db, users):
    """카톡 건은 발송 프로그램이 다시 집어가야 한다.

    잡이 `queued` 로 돌아가지 않으면 선점(`WHERE status='queued'`)에 걸리지 않아
    대기인 채로 영영 멈춘다.
    """
    from agent.main import SUPPORTED_KINDS

    job, _ = _job(db, users["u1"].id, [
        {"status": "sent"}, {"status": "canceled"},
    ])

    assert logged.post(f"/api/jobs/{job.id}/resend-canceled").json()["status"] == "queued"

    picked = client.get("/api/agent/poll",
                        params={"kinds": ",".join(SUPPORTED_KINDS)},
                        headers={"Authorization": f"Bearer {DEMO_TOKEN}"})
    assert picked.status_code == 200, "되살린 잡을 발송 프로그램이 집어가지 못했습니다"
    body = picked.json()
    assert body["job_id"] == job.id
    # 이미 나간 사람은 목록에 없어야 한다 — 있으면 두 번 나간다.
    assert [i["room_name"] for i in body["items"]] == ["받는사람2 심사역님"]


def test_mail_items_are_sent_by_the_server(logged, db, users, monkeypatch):
    """메일 건은 서버가 직접 보낸다 — 발송 프로그램은 메일 방을 찾지 못한다."""
    calls = []
    monkeypatch.setattr("app.routers.jobs.mail_sender.send_job",
                        lambda job_id: calls.append(job_id))

    job, _ = _job(db, users["u1"].id, [
        {"status": "sent", "channel": "email"},
        {"status": "canceled", "channel": "email"},
    ])

    assert logged.post(f"/api/jobs/{job.id}/resend-canceled").status_code == 200
    assert calls == [job.id], "메일 건을 되살렸는데 서버가 보내지 않았습니다"


def test_mail_and_kakao_in_one_job_both_move(logged, client, db, users, monkeypatch):
    """한 회차에 두 채널이 섞여 있으면 **둘 다** 제 길로 가야 한다.

    한쪽만 되돌리면 나머지가 영원히 대기로 남는다.
    """
    from agent.main import SUPPORTED_KINDS

    calls = []
    monkeypatch.setattr("app.routers.jobs.mail_sender.send_job",
                        lambda job_id: calls.append(job_id))

    job, _ = _job(db, users["u1"].id, [
        {"status": "canceled", "channel": "kakao"},
        {"status": "canceled", "channel": "email"},
    ])

    assert logged.post(f"/api/jobs/{job.id}/resend-canceled").json()["requeued"] == 2
    assert calls == [job.id], "메일 건이 서버 발송으로 넘어가지 않았습니다"

    picked = client.get("/api/agent/poll",
                        params={"kinds": ",".join(SUPPORTED_KINDS)},
                        headers={"Authorization": f"Bearer {DEMO_TOKEN}"})
    assert picked.status_code == 200
    # 메일 건이 카톡 목록에 섞이면 발송 프로그램이 방을 찾다가 실패한다.
    assert [i["room_name"] for i in picked.json()["items"]] == ["받는사람1 심사역님"]


def test_kakao_only_job_does_not_wake_the_mail_sender(logged, db, users, monkeypatch):
    """카톡만 있는 회차에서 메일 발송을 깨우면 헛돈다."""
    calls = []
    monkeypatch.setattr("app.routers.jobs.mail_sender.send_job",
                        lambda job_id: calls.append(job_id))

    job, _ = _job(db, users["u1"].id, [{"status": "canceled"}])

    assert logged.post(f"/api/jobs/{job.id}/resend-canceled").status_code == 200
    assert calls == []


# --- 되살린 회차가 원래 회차인가 --------------------------------------------

def test_resend_revives_the_same_job_instead_of_making_a_new_one(logged, db, users):
    """새 회차를 만들면 회차 번호·종류를 옮겨 담아야 하고, 하나라도 빠지면
    받은 사람인데 "보낸 적 없음" 으로 보인다. 같은 줄을 되살리면 옮길 것이 없다."""
    from sqlalchemy import func, select

    from app.models import SendItem, SendJob

    job, rows = _job(db, users["u1"].id, [
        {"status": "sent"}, {"status": "canceled"},
    ])
    before_ids = [row.id for row in rows]

    logged.post(f"/api/jobs/{job.id}/resend-canceled")
    db.expire_all()

    assert db.execute(select(func.count()).select_from(SendJob)).scalar() == 1
    assert list(db.execute(
        select(SendItem.id).order_by(SendItem.id)).scalars()) == before_ids
    # 끝난 시각은 지워야 한다 — 남아 있으면 아직 도는 회차가 끝난 것으로 보인다.
    assert db.get(SendJob, job.id).finished_at is None


# --- 화면에 붙어 있는가 -----------------------------------------------------

def test_progress_screen_has_the_button(logged, db, users):
    """회차 상세에 버튼이 있어야 누를 수 있다."""
    job, _ = _job(db, users["u1"].id, [{"status": "canceled"}])

    html = logged.get(f"/jobs/{job.id}").text
    assert 'id="resend-canceled-btn"' in html
    assert "hidden" in html.split('id="resend-canceled-btn"')[1].split(">")[0], (
        "취소 건이 없을 때도 보이면 안 된다 — 처음엔 감춰 두고 JS 가 켠다")


def test_button_is_hidden_until_there_is_something_to_resend():
    """취소된 건이 없으면 버튼이 보이지 않아야 하고, 보일 때는 **인원수**가 적혀야 한다.

    발송은 되돌릴 수 없어서 누르기 전에 몇 명인지 알아야 한다.
    """
    from pathlib import Path

    js = (Path(__file__).resolve().parent.parent
          / "app" / "static" / "js" / "progress.js").read_text(encoding="utf-8")

    assert "resend-canceled-btn" in js, "버튼을 켜고 끄는 코드가 없습니다"
    assert "counts.canceled" in js, "취소 건수를 보지 않고 버튼을 켜고 있습니다"
    assert "명)" in js, "버튼에 인원수가 적히지 않습니다"
    assert "confirm(" in js, "되돌릴 수 없는 발송인데 한 번 더 묻지 않습니다"


def test_readonly_admin_view_has_no_resend_button(client, db, users):
    """관리자가 남의 회차를 볼 때는 조작 버튼이 없다(서버도 404 로 막지만,
    누를 수 있게 보이는 것 자체가 사고의 입구다)."""
    from app.models import User
    from app.services import auth as auth_svc

    admin = User(name="관리자", phone="01000000009", role="admin",
                 password_hash=auth_svc.hash_password(DEMO_PASSWORD))
    db.add(admin)
    db.commit()
    job, _ = _job(db, users["u1"].id, [{"status": "canceled"}])

    client.post("/login", data={"phone": "01000000009", "password": DEMO_PASSWORD})
    html = client.get(f"/jobs/{job.id}").text

    assert "조회만 가능합니다" in html
    assert 'id="resend-canceled-btn"' not in html
