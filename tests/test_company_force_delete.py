"""IR 기업 현황 · 스타트업DB — **기업 강제 삭제**.

왜 이 검사가 있는가
-------------------
이 저장소는 지금까지 **지우지 않고 감춰** 왔다(`VcContact.is_hidden` ·
`ContactColumn.is_hidden` — "지우는 것이 아니라 세지 않는 것"). 사용자는 그것을
알고 **강제 삭제**를 요청했고, 근거로 일일 백업을 들었다. 자료가 정말로
없어지는 길이라, 잠가야 하는 것이 일곱이다.

1. **관리자만.** 한 번 누르면 팀 전체의 기록이 움직인다.
2. **기업명을 글자 그대로 적기 전에는 안 지워진다 — 서버가 본다.**
   화면에만 두면 주소를 직접 두드리는 길이 남는다.
3. **무엇이 몇 건 움직이는지 먼저 세어 준다**(`delete-plan` 은 아무 것도
   안 지운다).
4. **딸린 것이 정한 대로 된다.** 이름을 제 줄에 들고 있는 표(`발송 이력` ·
   `IR 요청` · `미팅`)는 **연결만 끊고**, 기업 번호가 줄의 열쇠인 표
   (`회차` · `예약` · `되돌리기 버퍼`)는 **줄째 지운다.**
5. **지운 뒤에 화면이 안 깨진다.** 이력이 붙은 기업도, 아무것도 없는 기업도.
6. **수정 로그에 남는다** — 누가 언제 무엇을, 그리고 **함께 움직인 것이
   몇 건인지**까지.
7. **평범한 [삭제] 는 여전히 막는다.** 막을 때 500 이 아니라 이유를 말한다.

이름·기업명은 전부 지어낸 것이다(공개 저장소).
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from .conftest import DEMO_PASSWORD

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture()
def people(db, users):
    """관리자 하나. conftest 의 두 계정은 둘 다 일반 팀원이다."""
    from app.models import User
    from app.services import auth as auth_svc

    row = User(id=91, name="관리자시험", phone="01000000091", role="admin",
               password_hash=auth_svc.hash_password(DEMO_PASSWORD))
    db.add(row)
    db.commit()
    return row


@pytest.fixture()
def portal(db, users, people):
    """역할별로 **따로** 로그인한 클라이언트(한 클라이언트로 갈아타면 쿠키가 덮인다)."""
    from fastapi.testclient import TestClient

    from app.main import create_app

    app = create_app()

    def sign_in(phone: str):
        client = TestClient(app)
        client.post("/login", data={"phone": phone, "password": DEMO_PASSWORD})
        return client

    return {"admin": sign_in("01000000091"), "member": sign_in("01000000001")}


@pytest.fixture()
def plain(db):
    """아무 것도 안 붙은 기업."""
    from app.models import IrCompany

    row = IrCompany(name="샘플다라소재", sector_major="소재", series="Seed")
    db.add(row)
    db.commit()
    return row


@pytest.fixture()
def linked(db, users, plain):
    """**이력이 붙은** 기업 — 여섯 표에 하나씩.

    돌려주는 것은 `(기업, 붙은 것들)`. 무엇이 몇 건인지는 검사가 직접 센다.
    """
    from app.models import (DealBatch, DealBatchCompany, DealQueueCompany,
                            DealQueueItem, IrCompany, IrRequest, Meeting,
                            OneLinerBackup, SendItem, SendJob, VcContact)

    u1 = users["u1"]
    company = IrCompany(name="샘플마바에너지", sector_major="에너지", one_liner="한 줄")
    db.add(company)
    db.commit()

    contact = VcContact(user_id=u1.id, source_sheet="시험 명단", name="가담당",
                        firm="가나벤처스", kakao_room_name="가담당 방")
    batch = DealBatch(user_id=u1.id, title="시험 회차")
    db.add_all([contact, batch])
    db.commit()

    job = SendJob(user_id=u1.id, kind="deal_intro", batch_id=batch.id, total=1)
    db.add(job)
    db.commit()

    queue = DealQueueItem(user_id=u1.id, group_name="", title="시험 예약",
                          status="waiting")
    db.add(queue)
    db.commit()

    made = [
        SendItem(job_id=job.id, ir_company_id=company.id, room_name="샘플마바 대표방",
                 message="월간 보고", status="sent"),
        IrRequest(user_id=u1.id, contact_id=contact.id, company_id=company.id,
                  company_name="샘플마바에너지", requested_at="2026-08-01"),
        Meeting(user_id=u1.id, contact_id=contact.id, company_id=company.id,
                company_name="샘플마바에너지", scheduled_at="2026-08-10"),
        DealBatchCompany(batch_id=batch.id, company_id=company.id, position=1),
        DealQueueCompany(item_id=queue.id, company_id=company.id, position=1),
        OneLinerBackup(batch=1, company_id=company.id, previous="옛 소개",
                       applied="새 소개"),
    ]
    db.add_all(made)
    db.commit()
    return company


def _plan(client, company_id: int):
    return client.get(f"/api/companies/{company_id}/delete-plan")


def _force(client, company_id: int, name: str):
    return client.post(f"/api/companies/{company_id}/force-delete",
                       json={"confirm_name": name})


def _alive(db, company_id: int) -> bool:
    from app.models import IrCompany

    db.expire_all()
    return db.get(IrCompany, company_id) is not None


# ── ① 관리자만 ──────────────────────────────────────────────────────────────

def test_팀원은_세어_볼_수도_강제로_지울_수도_없다(portal, db, plain):
    """**단추가 보이는 사람과 지울 수 있는 사람이 같아야 한다.**

    화면은 `can_delete`(→ `deps.admin_only`)로 가리는데, 라우터가 제 판정을
    새로 지으면 안 보이는데 주소로는 되는 상태가 된다.
    """
    assert _plan(portal["member"], plain.id).status_code == 403
    assert _force(portal["member"], plain.id, plain.name).status_code == 403
    assert _alive(db, plain.id)


def test_없는_번호는_권한을_먼저_본다(portal, db):
    """권한 없는 사람에게 404 를 주면 번호만 바꿔 가며 어느 기업이 있는지
    알아낼 수 있다 — 평범한 [삭제] 와 같은 차례다."""
    assert _plan(portal["member"], 999999).status_code == 403
    assert _force(portal["member"], 999999, "무엇이든").status_code == 403
    assert _plan(portal["admin"], 999999).status_code == 404
    assert _force(portal["admin"], 999999, "무엇이든").status_code == 404


# ── ② 이름을 손으로 적어야 지워진다 — **서버가 본다** ───────────────────────

@pytest.mark.parametrize("typed", ["", "샘플마바", "샘플마바에너지주식회사", "다른이름"])
def test_기업명이_다르면_한_줄도_안_지워진다(portal, db, linked, typed):
    """확인창의 [확인] 은 손이 미끄러지면 그대로 눌린다. 이름은 그 기업을
    보고 있지 않으면 적을 수가 없다.

    **화면이 아니라 서버가 본다** — 주소를 직접 두드리는 길이 남으면 안 된다.
    """
    r = _force(portal["admin"], linked.id, typed)
    assert r.status_code == 400
    assert "기업명" in r.json()["detail"]
    assert _alive(db, linked.id)


def test_앞뒤_공백은_봐_준다(portal, db, plain):
    """화면에서 긁어 붙이면 공백이 딸려 온다 — 그것 때문에 막으면 사람은
    무엇이 틀렸는지 눈으로 찾을 수 없다(공백은 안 보인다)."""
    assert _force(portal["admin"], plain.id, f"  {plain.name} ").status_code == 200


# ── ③ 먼저 세어 본다 — `delete-plan` 은 아무 것도 안 지운다 ─────────────────

def test_세어_보기는_한_줄도_건드리지_않는다(portal, db, linked):
    from app.models import IrRequest, Meeting, SendItem

    before = [db.query(m).count() for m in (SendItem, IrRequest, Meeting)]
    r = _plan(portal["admin"], linked.id)
    assert r.status_code == 200
    assert _alive(db, linked.id)
    db.expire_all()
    assert [db.query(m).count() for m in (SendItem, IrRequest, Meeting)] == before


def test_무엇이_몇_건인지_숫자로_말한다(portal, linked):
    """`발송 이력 · 미팅` 처럼 갈래 이름만 늘어놓으면 사람은 손댈 수 없는
    이력 뭉치인지 한 건짜리인지 판단할 수가 없다."""
    plan = _plan(portal["admin"], linked.id).json()
    assert plan["counts"] == {"sends": 1, "ir_requests": 1, "meetings": 1,
                              "batches": 1, "queued": 1, "backups": 1}
    assert plan["detached"] == 3 and plan["removed"] == 2
    # 아직 안 나간 예약에 들어 있다 — 세 곳짜리 회차가 말없이 두 곳이 된다.
    assert plan["live_queue"] == 1
    assert plan["name"] == "샘플마바에너지"
    assert plan["blocks"], "평범한 [삭제] 가 막힐 이유가 있어야 한다"


def test_아무것도_안_붙은_기업은_막을_이유가_없다(portal, plain):
    plan = _plan(portal["admin"], plain.id).json()
    assert plan["blocks"] == []
    assert plan["detached"] == 0 and plan["removed"] == 0


def test_이름으로만_붙는_시트_이력도_세어_준다(portal, db, users, plain):
    """외래키가 없어 지워지지도 끊기지도 않지만, 기업 줄이 없어지면 그 이름이
    **이력에만 있고 기업 목록에 없는 이름** 쪽으로 옮겨 앉는다
    (`services/deal_history.py` 의 `unmatched`). 화면이 말 안 하면 IR 기업
    현황 아래의 그 수가 왜 늘었는지 물을 자리가 없다."""
    import json

    from app.models import ContactActivity, VcContact

    contact = VcContact(user_id=users["u1"].id, source_sheet="시험 명단",
                        name="나담당", firm="다라벤처스")
    db.add(contact)
    db.commit()
    db.add(ContactActivity(contact_id=contact.id, kind="deal_intro",
                           content="딜 소개", happened_at="2026-07-01",
                           company_names=json.dumps(["샘플다라소재"],
                                                    ensure_ascii=False)))
    db.commit()

    assert _plan(portal["admin"], plain.id).json()["by_name"] == 1


# ── ④ 딸린 것이 정한 대로 된다 ─────────────────────────────────────────────

def test_이름을_들고_있는_줄은_남고_연결만_끊긴다(portal, db, linked):
    """**세 갈래 중 이것을 골랐다.**

    `발송 이력` · `IR 요청` · `미팅` 은 "우리가 이 기업으로 몇 번 움직였나" 의
    근거다. 줄째 지우면 지난 주간·월간 보고의 수가 **소급해서** 바뀌고,
    `send_items` 는 `SendJob.total` 과 짝이라 진행 화면이 영영 안 맞는 회차가
    된다. 셋 다 제 줄에 이름·방 제목을 들고 있으므로, 연결만 끊어도 무엇에
    대한 줄인지가 남는다.
    """
    from app.models import IrRequest, Meeting, SendItem

    assert _force(portal["admin"], linked.id, linked.name).status_code == 200
    db.expire_all()

    send = db.query(SendItem).one()
    assert send.ir_company_id is None
    assert send.room_name == "샘플마바 대표방", "누구에게 보냈는지가 사라졌다"

    req = db.query(IrRequest).one()
    assert req.company_id is None
    assert req.company_name == "샘플마바에너지", "요청받은 기업 이름이 사라졌다"

    meet = db.query(Meeting).one()
    assert meet.company_id is None
    assert meet.company_name == "샘플마바에너지", "미팅 기업 이름이 사라졌다"


def test_기업_번호가_열쇠인_줄은_줄째_지워진다(portal, db, linked):
    """`deal_batch_companies` · `deal_queue_companies` 는 기업 번호가 복합
    기본키라 비울 수가 없고, `one_liner_backups` 는 NOT NULL 이다. 남겨 두면
    없는 기업을 가리킨 채로 남아 INNER JOIN 에서 조용히 빠지거나(회차 목록)
    [시작] 을 누르는 순간 `기업 … 없음` 으로 죽는다(예약)."""
    from app.models import DealBatch, DealBatchCompany, DealQueueCompany, \
        DealQueueItem, OneLinerBackup

    assert _force(portal["admin"], linked.id, linked.name).status_code == 200
    db.expire_all()
    assert db.query(DealBatchCompany).count() == 0
    assert db.query(DealQueueCompany).count() == 0
    assert db.query(OneLinerBackup).count() == 0
    # 회차와 예약 **줄 자체**는 남는다 — 무엇을 세워 뒀는지가 사라지면 안 된다.
    assert db.query(DealBatch).count() == 1
    assert db.query(DealQueueItem).count() == 1


def test_기업_줄을_가리키는_표는_전부_어느_쪽인지_정해져_있다(db):
    """**표를 통째로 훑는다** — 기업 줄을 가리키는 표가 하나 늘면 걸린다.

    정하지 않은 표는 둘 중 하나가 된다. 조용히 고아로 남거나(그 화면이
    깨지거나 숫자가 줄거나), 아무도 모르게 함께 사라지거나. 어느 쪽도 나중에
    알아채기 어렵다 — 만든 사람이 여기서 한 번 고르게 한다
    (`tests/test_contacts_bulk_delete.py` 가 담당자 줄에 대해 하는 그 방식).
    """
    import app.models  # noqa: F401  (Base.metadata 에 모델 등록)
    from app.db import Base
    from app.routers import companies as router

    decided = {(model_name, field)
               for _k, model_name, field, _l, _m in router.COMPANY_LINKS}
    missing = []
    for mapper in Base.registry.mappers:
        model = mapper.class_
        for column in mapper.local_table.columns:
            for fk in column.foreign_keys:
                if fk.column.table.name != "ir_companies":
                    continue
                if (model.__name__, column.key) in decided:
                    continue
                missing.append(f"{model.__tablename__}.{column.key}")

    assert not missing, (
        "기업 줄을 가리키는데 지울 때 어떻게 할지 정해 두지 않은 표가 "
        "있습니다. app/routers/companies.py 의 COMPANY_LINKS 에 "
        "DETACH(연결만 끊는다) · CASCADE(줄째 지운다) · SWEEP(묻지 않고 "
        "치운다) 중 하나로 적어 주세요:\n" + "\n".join(sorted(set(missing))))


# ── ⑤ 지운 뒤에 화면이 안 깨진다 ───────────────────────────────────────────

SCREENS = ["/companies", "/companies?tab=db", "/dashboard", "/deals",
           "/report", "/ir", "/followups", "/startup/ir-report", "/contacts"]


@pytest.mark.parametrize("path", SCREENS)
def test_이력이_붙은_기업을_지워도_화면이_뜬다(portal, db, linked, path):
    """**이쪽이 요점이다.** 딸린 줄이 여섯 표에 있는 기업을 지운다."""
    assert _force(portal["admin"], linked.id, linked.name).status_code == 200
    r = portal["admin"].get(path)
    assert r.status_code == 200, f"{path} 가 {r.status_code} 로 떴다"


@pytest.mark.parametrize("path", SCREENS)
def test_아무것도_없는_기업을_지워도_화면이_뜬다(portal, db, plain, path):
    assert _force(portal["admin"], plain.id, plain.name).status_code == 200
    assert portal["admin"].get(path).status_code == 200


def test_예약_시작과_회차_이력도_안_죽는다(portal, db, linked):
    """예약 줄이 없는 기업을 가리킨 채 남으면 [시작] 이 `기업 … 없음` 으로
    죽는다. 회차 쪽은 INNER JOIN 이라 안 죽는 대신 숫자가 준다 — 둘 다
    실제로 불러 본다."""
    from app.services import deal_history, report

    assert _force(portal["admin"], linked.id, linked.name).status_code == 200
    db.expire_all()
    # 기업 이력 훑기 — `/companies` 와 `/deals` 가 이 한 번을 함께 쓴다.
    scan = deal_history.scan(db)
    assert scan.of("샘플마바에너지").rounds == []
    # 업무 보고 — 지워진 기업이 실렸던 회차 줄을 읽는다.
    assert portal["admin"].get("/report").status_code == 200
    assert report is not None


# ── ⑥ 수정 로그 ────────────────────────────────────────────────────────────

def test_지운_것이_수정_로그에_남는다(portal, db, linked):
    """지운 줄은 화면 어디에도 없다 — 무엇이 있었는지 물을 자리가 여기밖에
    없다. **함께 움직인 것이 몇 건인지**까지 남아야 한다: 그 수는 기업 줄
    어디에도 안 적혀 있어, 나중에 물을 자리가 로그 말고 없다."""
    from app.models import EditLog

    assert _force(portal["admin"], linked.id, linked.name).status_code == 200
    db.expire_all()

    rows = db.query(EditLog).filter(EditLog.table_name == "ir_companies").all()
    assert len(rows) == 1, "기업을 지웠는데 로그가 한 줄도 없다"
    row = rows[0]
    assert row.action == "delete"
    assert row.actor_user_id == 91, "누가 지웠는지가 없다"
    assert row.row_label == "샘플마바에너지", "무엇을 지웠는지 이름이 없다"
    # **강제로 지운 길이라는 것**이 주소에 남는다 — 평범한 [삭제] 와 갈린다.
    assert "force-delete" in row.path
    assert row.at, "언제 지웠는지가 없다"

    changes = row.changes_json
    # 주요 값 — 이름·분야·계약 상태가 그대로 남는다.
    assert "샘플마바에너지" in changes and "에너지" in changes
    # 함께 움직인 것.
    assert "force_delete" in changes
    assert "발송 이력 1건 연결 끊음" in changes
    assert "발송 회차에 실린 줄 1건 지움" in changes


def test_수정_로그_화면이_함께_움직인_것을_그려_준다(portal, db, linked):
    """로그에 담기만 하고 화면이 못 그리면 없는 것과 같다.

    그 화면은 `삭제` 줄에서 **`before` 만** 보여 준다(`edit_log.html` — 지운
    줄에 `→ (빈 값)` 을 붙여 봐야 읽는 눈만 잡아먹는다). 담는 자리를 잘못
    고르면 `함께 움직인 것 (빈 값)` 으로 뜬다.
    """
    assert _force(portal["admin"], linked.id, linked.name).status_code == 200
    html = portal["admin"].get("/team/edit-log").text
    assert "함께 움직인 것" in html
    assert "발송 이력 1건 연결 끊음" in html
    assert "샘플마바에너지" in html


def test_아무것도_안_붙은_기업도_로그에_남는다(portal, db, plain):
    from app.models import EditLog

    assert _force(portal["admin"], plain.id, plain.name).status_code == 200
    db.expire_all()
    row = db.query(EditLog).filter(EditLog.table_name == "ir_companies").one()
    assert row.row_label == "샘플다라소재"
    assert "딸린 줄 없음" in row.changes_json


# ── ⑦ 평범한 [삭제] 는 여전히 막는다 — 500 이 아니라 이유를 말한다 ─────────

def test_IR_요청이_붙은_기업은_평범한_삭제에서_500_이_아니라_막힌다(
        portal, db, users, plain):
    """예전에는 `ir_requests` · `meetings` · `send_items` 를 아무도 안 봐서,
    아래 `db.delete()` 가 외래키에 걸려 **이유 없는 500** 이 났다. 화면에는
    `삭제 실패` 만 떠서 왜 안 지워지는지 알 길이 없었다."""
    from app.models import IrRequest, VcContact

    contact = VcContact(user_id=users["u1"].id, source_sheet="시험 명단",
                        name="다담당", firm="마바벤처스")
    db.add(contact)
    db.commit()
    db.add(IrRequest(user_id=users["u1"].id, contact_id=contact.id,
                     company_id=plain.id, company_name="샘플다라소재",
                     requested_at="2026-08-01"))
    db.commit()

    r = portal["admin"].delete(f"/api/companies/{plain.id}")
    assert r.status_code == 400, f"500 이 아니라 이유를 말해야 한다({r.status_code})"
    detail = r.json()["detail"]
    assert "IR 요청 1건" in detail, "무엇이 몇 건 걸렸는지 말하지 않는다"
    assert "강제 삭제" in detail, "다음에 뭘 하면 되는지 알려 주지 않는다"
    assert _alive(db, plain.id)

    # 그리고 **강제 삭제로는 지워진다.**
    assert _force(portal["admin"], plain.id, plain.name).status_code == 200
    assert not _alive(db, plain.id)


def test_되돌리기_버퍼_하나_때문에_기업이_영영_안_지워지면_안_된다(
        portal, db, plain):
    """`one_liner_backups` 는 [전체 자동조합] 이 남겨 둔 임시 버퍼다. 한 번
    누르면 고른 기업 전부에 한 줄씩 쌓이고, 되돌리기를 누르기 전에는 안
    지워진다 — 그것 때문에 평범한 [삭제] 가 막히면 안 된다."""
    from app.models import OneLinerBackup

    db.add(OneLinerBackup(batch=1, company_id=plain.id, previous="옛", applied="새"))
    db.commit()

    assert portal["admin"].delete(f"/api/companies/{plain.id}").status_code == 200
    db.expire_all()
    assert db.query(OneLinerBackup).count() == 0


# ── ⑧ 화면이 되돌리는 길을 정확히 적는가 ───────────────────────────────────

def test_화면이_두_탭과_백업_되돌리기를_적는다(portal):
    """사용자는 `어차피 백업하고 있으니 복구 가능` 이라 했는데, 백업 되돌리기는
    **DB 전체를 그 시점으로 되돌리는 일**이다 — 그사이의 다른 작업도 같이
    사라진다. 그 사실을 화면이 적지 않으면 사람은 되돌릴 수 있다고 믿고 누른다.
    """
    html = portal["admin"].get("/companies").text
    assert 'id="co-force"' in html, "강제 삭제 상자가 없다"
    assert 'id="co-force-name"' in html, "기업명을 적는 칸이 없다"
    # 두 탭에서 함께 사라진다.
    assert "스타트업DB" in html and "두 탭" in html
    # 되돌리는 길과 그 한계.
    assert "/team/restore" in html
    assert "DB 전체를 그날로 되돌리는 일" in html
    assert "/team/edit-log" in html, "수정 로그로 가는 길이 없다"


def test_팀원_화면에는_강제_삭제_상자가_아예_없다(portal):
    """눌러도 안 되는 단추가 보이면 고장으로 읽힌다 — [삭제] 와 같은 판정."""
    html = portal["member"].get("/companies").text
    assert 'id="co-force"' not in html
    assert 'id="co-delete"' not in html


@pytest.mark.skipif(shutil.which("node") is None,
                    reason="node 미설치 — 브라우저 로직 테스트 생략")
def test_잘못_누르기_어려운지는_브라우저에_있으니_거기서_잰다():
    """이름을 다 적기 전에는 단추가 안 열리는가 · 다른 기업으로 넘어가면
    상자가 접히는가 · 딸린 것이 없으면 강제 상자가 아예 안 뜨는가.
    파이썬으로는 잴 수 없는 자리다."""
    script = ROOT / "tests" / "js" / "company_force_delete_test.js"
    out = subprocess.run([shutil.which("node"), str(script)],
                         capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stdout + out.stderr
