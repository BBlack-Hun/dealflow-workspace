"""한 줄 지우기가 **왜 안 되는지 말한다** — 투자사 관리 현황의 [삭제].

무엇이 잘못돼 있었나
--------------------
수정창에서 [삭제] 를 눌러도 줄이 안 지워지는데, 왜 안 되는지 아무 말이 없었다.
`delete_contact` 는 활동 이력만 지우고 `db.delete()` 를 던졌는데, 담당자 줄을
가리키는 표는 **다섯**이고 외래키가 켜져 있다(`PRAGMA foreign_keys = 1`).
발송 기록 · 후속 발송 · IR 요청 · 미팅 중 하나라도 걸려 있으면 거기서 막혀
500 이 나거나 조용히 실패했다. 화면 쪽은 응답을 보지도 않고 새로 그렸으므로
**지워진 줄 알았다가 그 줄이 그대로 있는 것을 나중에 발견하는** 상태였다.

여기서 잠그는 것
----------------
1. 아무 것도 안 걸린 줄은 **그대로 지워진다** — 되던 것이 안 깨진다.
2. 걸린 줄은 **409 와 사유**가 온다. 상태 번호는 여러 줄 지우기와 같다.
3. 사유에 **무엇이 몇 건인지**와 **다음에 뭘 하면 되는지**가 들어 있다.
4. 활동 이력만 있는 줄은 지워지고, 그 이력도 함께 사라진다(고아를 안 남긴다).
5. 남의 담당은 여전히 404 — 권한 판정은 `_owned` 그대로다.
6. 지운 것은 **수정 로그에 남는다**(자기 담당분이어도).
7. **판정이 한 곳이다** — 한 줄 지우기와 여러 줄 지우기가 같은 함수를 읽는다.

7번이 이 파일의 핵심이다. 같은 판단을 두 곳에 적으면 표가 하나 늘었을 때
한쪽만 고쳐지고, 그러면 같은 줄이 한 길에서는 지워지고 다른 길에서는 막힌다.

이름 · 회사는 전부 지어낸 것이다(공개 저장소).
"""
from __future__ import annotations

import pytest

from .conftest import DEMO_PASSWORD

SHEET = "투자사 시험 명단"


@pytest.fixture()
def rows(db, users):
    """내 담당 둘 · 남의 담당 하나. 감추기와 상관없이 한 줄 지우기는 된다."""
    from app.models import SheetOwner, VcContact
    from app.services import contact_columns as cc

    u1, u2 = users["u1"], users["u2"]
    db.add(SheetOwner(label=SHEET, user_id=u1.id, layout=cc.INVESTOR))
    made = {}
    for name, owner in (("가담당", u1), ("나담당", u1), ("마담당", u2)):
        row = VcContact(user_id=owner.id, source_sheet=SHEET, name=name,
                        firm="가나벤처스", connect_stage="connected",
                        channel_kakao=1, kakao_room_name=f"{name} 방")
        db.add(row)
        made[name] = row
    db.commit()
    return made


@pytest.fixture()
def team(client, db, users, rows):
    """u1 으로 로그인한 클라이언트."""
    client.post("/login", data={"phone": "01000000001",
                                "password": DEMO_PASSWORD})
    return client


@pytest.fixture()
def other(db, users, rows):
    """u2 로 따로 로그인한 클라이언트 — 쿠키가 덮이지 않게 앱을 따로 세운다."""
    from fastapi.testclient import TestClient

    from app.main import create_app

    c = TestClient(create_app())
    c.post("/login", data={"phone": "01000000002", "password": DEMO_PASSWORD})
    return c


def _names(db):
    from app.models import VcContact

    db.expire_all()
    return sorted(r.name for r in db.query(VcContact).all())


def _link(db, kind, cid, n=1):
    """그 줄에 이력을 `n` 건 건다. 갈래 이름은 `BLOCKING_LINKS` 의 키와 같다."""
    from app.models import IrRequest, Meeting, SendItem, SendJob, SendSequence

    for i in range(n):
        if kind == "sends":
            job = SendJob(user_id=1, kind="deal_intro", status="done")
            db.add(job)
            db.flush()
            db.add(SendItem(job_id=job.id, contact_id=cid, room_name="가담당 방",
                            message="", status="sent"))
        elif kind == "ir_requests":
            db.add(IrRequest(user_id=1, contact_id=cid, company_name="가나기업",
                             requested_at="2026-08-13"))
        elif kind == "meetings":
            db.add(Meeting(user_id=1, contact_id=cid, company_name="가나기업",
                           scheduled_at=f"2026-08-{20 + i:02d}"))
        elif kind == "sequences":
            db.add(SendSequence(user_id=1, contact_id=cid, stage=i + 1))
        else:  # pragma: no cover - 시험이 오타 난 것
            raise AssertionError(kind)
    db.commit()


# ═══════════════════════════════════════════════════════════════════════════
# 1. 안 걸린 줄은 그대로 지워진다
# ═══════════════════════════════════════════════════════════════════════════

def test_아무것도_안_걸린_줄은_그대로_지워진다(team, db, rows):
    """지금 되던 것이 안 깨진다 — 막는 판정을 태우면서 흔히 여기가 상한다."""
    r = team.delete(f"/api/contacts/{rows['가담당'].id}")
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True
    assert _names(db) == ["나담당", "마담당"], "고르지 않은 줄까지 사라졌습니다"


def test_활동_이력만_있는_줄은_지워지고_이력도_함께_사라진다(team, db, rows):
    """활동 이력은 시트의 월별 칸을 줄로 편 것이라 그 줄 밖에서는 뜻이 없다.

    여러 줄 지우기와 **같은 목록**(`CASCADING_LINKS`)을 읽으므로 두 길이
    저절로 같이 움직인다.
    """
    from app.models import ContactActivity

    cid = rows["가담당"].id
    db.add_all([ContactActivity(contact_id=cid, month="2026-08",
                                kind="deal_intro", content="1회차"),
                ContactActivity(contact_id=cid, month="2026-08",
                                kind="ir_request", content="가나기업")])
    db.commit()

    assert team.delete(f"/api/contacts/{cid}").status_code == 200
    db.expire_all()
    assert "가담당" not in _names(db)
    assert db.query(ContactActivity).filter(
        ContactActivity.contact_id == cid).count() == 0, "고아 활동 이력이 남았습니다"


# ═══════════════════════════════════════════════════════════════════════════
# 2. 걸린 줄은 409 와 **사유**
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("kind,label", [
    ("sends", "발송 기록"),
    ("ir_requests", "IR 요청"),
    ("meetings", "미팅"),
    ("sequences", "후속 발송"),
])
def test_이력이_걸리면_409_와_사유가_온다(team, db, rows, kind, label):
    """넷 다 막아야 한다. 하나라도 빠지면 그 표만 외래키에 걸려 500 이 난다.

    상태 번호는 여러 줄 지우기와 **같은 409** 다 — 같은 이유로 막는데 번호가
    다르면 화면이 길마다 다르게 받아야 하고, 한쪽은 반드시 안 맞춰진다.
    """
    cid = rows["가담당"].id
    _link(db, kind, cid)

    r = team.delete(f"/api/contacts/{cid}")
    assert r.status_code == 409, f"막지 못했습니다({r.status_code}): {r.text}"
    assert label in r.json()["detail"], (
        f"왜 막혔는지 말해 주지 않습니다: {r.json()['detail']}")
    assert _names(db) == ["가담당", "나담당", "마담당"], "막았는데 줄이 사라졌습니다"


def test_사유에_무엇이_몇_건인지_들어_있다(team, db, rows):
    """**건수가 없으면 "그냥 안 되는구나" 로 끝난다.**

    한 건짜리 미팅 하나 때문인지, 손댈 수 없는 이력 뭉치인지에 따라 사람이
    할 일이 다르다.
    """
    cid = rows["가담당"].id
    _link(db, "sends", cid, n=12)
    _link(db, "meetings", cid, n=1)

    detail = team.delete(f"/api/contacts/{cid}").json()["detail"]
    assert "발송 기록 12건" in detail, f"몇 건인지 안 적혔습니다: {detail}"
    assert "미팅 1건" in detail, f"몇 건인지 안 적혔습니다: {detail}"


def test_막혔을_때_다음에_뭘_하면_되는지_알려_준다(team, db, rows):
    """막기만 하고 길을 안 알려 주면 사람이 **막다른 길에 선다.**

    감추면 표에서 빠지고 딜 소개 발송 대상에서도 빠지므로 실무에서는 지운 것과
    같고, 보고가 세는 이력은 그대로 남는다.
    """
    cid = rows["가담당"].id
    _link(db, "meetings", cid)

    detail = team.delete(f"/api/contacts/{cid}").json()["detail"]
    assert "감추기" in detail, f"다음 걸음을 안 알려 줍니다: {detail}"
    assert "발송" in detail, f"감추면 발송 대상에서도 빠진다는 말이 없습니다: {detail}"


def test_막힌_줄의_이력은_손대지_않는다(team, db, rows):
    """막았으면 정말 아무 것도 안 건드려야 한다.

    활동 이력을 먼저 지우고 나서 막으면, 막힌 줄에서 월별 기록만 사라진다 —
    되돌릴 수도 없고 아무도 알아채지 못한다.
    """
    from app.models import ContactActivity, Meeting

    cid = rows["가담당"].id
    db.add(ContactActivity(contact_id=cid, month="2026-08",
                           kind="deal_intro", content="1회차"))
    db.commit()
    _link(db, "meetings", cid)

    assert team.delete(f"/api/contacts/{cid}").status_code == 409
    db.expire_all()
    assert db.query(ContactActivity).filter(
        ContactActivity.contact_id == cid).count() == 1, "막았는데 활동 이력이 사라졌습니다"
    assert db.query(Meeting).filter(Meeting.contact_id == cid).count() == 1


# ═══════════════════════════════════════════════════════════════════════════
# 3. 누가 지울 수 있나 — `_owned` 그대로
# ═══════════════════════════════════════════════════════════════════════════

def test_남의_담당_줄은_여전히_404(other, db, rows):
    """있는지 없는지도 흘리지 않는다. 판정은 한 줄 고치기와 같은 `_owned` 다."""
    r = other.delete(f"/api/contacts/{rows['가담당'].id}")
    assert r.status_code == 404, r.text
    assert _names(db) == ["가담당", "나담당", "마담당"]


def test_없는_번호도_404(team, rows):
    assert team.delete("/api/contacts/999999").status_code == 404


def test_권한을_이력_판정보다_먼저_본다(other, db, rows):
    """남의 줄이면 **무엇이 걸렸는지도 알려 주지 않는다.**

    409 로 "발송 기록 3건" 이라고 답하면, 남의 담당자에게 발송이 몇 건 나갔는지
    번호만 바꿔 가며 읽어 낼 수 있다.
    """
    _link(db, "sends", rows["가담당"].id, n=3)
    r = other.delete(f"/api/contacts/{rows['가담당'].id}")
    assert r.status_code == 404, f"남의 줄의 이력 건수를 흘렸습니다: {r.text}"
    assert "발송" not in r.text


# ═══════════════════════════════════════════════════════════════════════════
# 4. 수정 로그
# ═══════════════════════════════════════════════════════════════════════════

def test_지운_것이_수정_로그에_남는다(team, db, rows):
    """지운 줄은 화면 어디에도 없다 — 무엇이 있었는지 물을 자리가 여기뿐이다.

    자기 담당분이어도 남는다(`edit_log.SCOPE_MINE`). 이 길로 지우는 것은 대개
    본인 담당이라, 자기 것이라고 빼면 로그가 통째로 빈다.
    """
    from app.models import EditLog

    assert team.delete(f"/api/contacts/{rows['가담당'].id}").status_code == 200

    db.expire_all()
    logs = [g for g in db.query(EditLog).order_by(EditLog.id).all()
            if g.table_name == "vc_contacts"]
    assert len(logs) == 1, f"한 줄 지우기가 로그에 안 남았습니다: {len(logs)}건"
    assert logs[0].action == "delete"
    assert logs[0].row_label == "가담당"
    assert logs[0].scope == "mine", "자기 담당분을 지웠더니 안 남거나 범위가 다릅니다"
    assert logs[0].actor_user_id == 1


def test_막혀서_못_지운_것은_로그에_안_남는다(team, db, rows):
    """아무 것도 안 지운 부름이 로그를 채우면 정작 지운 줄이 묻힌다."""
    from app.models import EditLog

    _link(db, "meetings", rows["가담당"].id)
    assert team.delete(f"/api/contacts/{rows['가담당'].id}").status_code == 409

    db.expire_all()
    assert [g for g in db.query(EditLog).all()
            if g.table_name == "vc_contacts"] == []


# ═══════════════════════════════════════════════════════════════════════════
# 5. **판정은 한 곳** — 두 길이 갈리면 여기서 깨진다
# ═══════════════════════════════════════════════════════════════════════════

def test_두_길이_같은_판정_함수를_읽는다(team, db, rows, monkeypatch):
    """한 줄 지우기와 여러 줄 지우기가 **둘 다** `_blocking_reasons` 를 지난다.

    한쪽이 자기 판정을 따로 적으면 여기서 걸린다. 가짜 판정을 끼워 넣고 두
    길을 다 눌러 본다 — 그 판정이 안 먹는 길이 있으면 그 길은 다른 자리를
    읽고 있다는 뜻이다.
    """
    from app.routers import contacts as router

    calls = []
    real = router._blocking_reasons

    def spy(db_, ids, linked=None):
        calls.append(sorted(ids))
        # 무엇이 걸렸는지까지 **판정이 정한다** — 부르는 쪽이 다시 세면 안 된다.
        return {i: [("가짜 이력", 7)] for i in ids}

    monkeypatch.setattr(router, "_blocking_reasons", spy)
    assert real is not spy

    cid = rows["가담당"].id
    one = team.delete(f"/api/contacts/{cid}")
    assert one.status_code == 409, (
        f"한 줄 지우기가 판정을 안 지납니다({one.status_code}) — 자기 판정을 "
        f"따로 적고 있습니다: {one.text}")
    assert "가짜 이력 7건" in one.json()["detail"], (
        f"판정이 준 사유를 안 씁니다: {one.json()['detail']}")

    rows["가담당"].is_hidden = 1
    db.commit()
    many = team.post("/api/contacts/bulk-delete",
                     json={"contact_ids": [cid], "confirm": True})
    assert many.status_code == 409, (
        f"여러 줄 지우기가 판정을 안 지납니다({many.status_code}): {many.text}")

    assert calls == [[cid], [cid]], (
        f"두 길이 판정을 한 번씩 지나지 않았습니다: {calls}")
    assert _names(db) == ["가담당", "나담당", "마담당"]


def test_막는_목록에_표를_하나_더하면_두_길_다_막힌다(team, db, rows, monkeypatch):
    """**목록 하나만 고쳐도 두 길이 같이 움직인다.**

    표가 새로 생겨 `BLOCKING_LINKS` 에 한 줄이 늘었을 때가 실제로 이 코드가
    바뀌는 순간이다. 한쪽이 표 이름을 손으로 적어 두었으면 그 길만 안 따라
    오고, 그러면 같은 줄이 한 길에서는 막히고 다른 길에서는 지워진다.

    (활동 이력을 잠시 막는 쪽으로 옮겨 잰다 — 목록이 바뀌었다는 것 말고는
    아무 것도 안 바꾼다.)
    """
    from app.models import ContactActivity
    from app.routers import contacts as router

    for name in ("가담당", "나담당"):
        db.add(ContactActivity(contact_id=rows[name].id, month="2026-08",
                               kind="deal_intro", content="1회차"))
    rows["나담당"].is_hidden = 1
    db.commit()

    # 안 걸린 것으로 치던 표를 **막는 쪽으로** 옮긴다.
    monkeypatch.setattr(router, "CASCADING_LINKS", ())
    monkeypatch.setattr(
        router, "BLOCKING_LINKS",
        router.BLOCKING_LINKS + (("activities", ContactActivity, "활동 이력"),))

    one = team.delete(f"/api/contacts/{rows['가담당'].id}")
    assert one.status_code == 409, (
        f"목록에 더한 표를 한 줄 지우기가 안 봅니다({one.status_code}) — 자기 "
        f"판정을 따로 적고 있습니다: {one.text}")
    assert "활동 이력 1건" in one.json()["detail"]

    many = team.post("/api/contacts/bulk-delete",
                     json={"contact_ids": [rows["나담당"].id], "confirm": True})
    assert many.status_code == 409, (
        f"목록에 더한 표를 여러 줄 지우기가 안 봅니다({many.status_code}): {many.text}")

    assert _names(db) == ["가담당", "나담당", "마담당"]


def test_판정_함수를_부르는_자리가_둘뿐이다(team, rows):
    """`_blocking_reasons` 를 부르는 자리가 **딱 그 둘**인지 글자로도 본다.

    세 번째 자리가 생기면 사유 문장과 상태 번호가 또 갈린다. 위의 두 검사는
    지금 있는 두 길이 같은 자리를 읽는지만 보므로, 새로 생기는 길은 여기서
    걸린다.
    """
    import re
    from pathlib import Path

    src = Path(__file__).resolve().parents[1] / "app" / "routers" / "contacts.py"
    text = src.read_text(encoding="utf-8")
    # 정의 한 줄 + 부르는 두 자리 = 셋.
    hits = re.findall(r"_blocking_reasons\(", text)
    assert len(hits) == 3, (
        f"`_blocking_reasons` 를 부르는 자리가 둘이 아닙니다({len(hits) - 1}곳) — "
        "판정이 흩어지면 사유 문장과 상태 번호가 갈립니다")
