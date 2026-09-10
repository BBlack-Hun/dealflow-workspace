"""감춘 줄을 골라 **한꺼번에 지운다** — 투자사 관리 현황.

왜 이 검사가 있는가
-------------------
현황 시트를 새로 올리면 새 시트에 없는 줄이 남는다. 지우지 않고
`VcContact.is_hidden` 으로 감춘다 — 시트가 잘못 올라간 날 되돌릴 수 있어야
하기 때문이다. 한 번은 그렇게 80줄이 감겼고, **감춘 뒤에 정리하는 길이
없었다.** 그 길을 내면서 잠가야 하는 것이 여섯이다.

1. **평소 화면에는 감춘 줄도 지우는 단추도 없다.** 감춘 것이 기본으로 섞여
   나오면 감춘 뜻이 없다.
2. **고른 줄만 사라지고 안 고른 줄은 남는다.**
3. **권한 없는 계정은 못 지운다 — 서버가 막는다.** 화면만 감추면 번호를
   직접 보내는 길이 남는다.
4. **딸린 자료가 정한 대로 된다.** 활동 이력은 함께 사라지고, 발송 기록 ·
   IR 요청 · 미팅 · 후속 흐름이 걸린 줄은 **막힌다**(고아를 안 남긴다).
5. **삭제가 수정 로그에 남는다 — 줄마다 한 줄씩.** 80줄을 지웠는데 로그가
   비면 그것이 이 기능의 가장 큰 구멍이다.
6. **확인 없이는 안 지워진다.**
"""
from __future__ import annotations

from urllib.parse import quote

import pytest

from .conftest import DEMO_PASSWORD

SHEET = "투자사 시험 명단"


def _url(**q) -> str:
    extra = "".join(f"&{k}={v}" for k, v in q.items())
    return f"/contacts?sheet={quote(SHEET)}{extra}"


@pytest.fixture()
def rows(db, users):
    """한 명단 안에 감춘 줄 셋 · 보이는 줄 하나. 남의 담당도 하나 둔다.

    이름 · 회사는 전부 지어낸 것이다(공개 저장소).
    """
    from app.models import SheetOwner, VcContact
    from app.services import contact_columns as cc

    u1, u2 = users["u1"], users["u2"]
    db.add_all([
        SheetOwner(label=SHEET, user_id=u1.id, layout=cc.INVESTOR),
    ])
    made = {}
    for name, hidden, owner in (("가담당", 1, u1), ("나담당", 1, u1),
                                ("다담당", 1, u1), ("라담당", 0, u1),
                                ("마담당", 1, u2)):
        row = VcContact(user_id=owner.id, source_sheet=SHEET, name=name,
                        firm="가나벤처스", is_hidden=hidden,
                        connect_stage="connected", channel_kakao=1,
                        kakao_room_name=f"{name} 방")
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
    """u2 로 따로 로그인한 클라이언트 — 쿠키가 덮이지 않게 앱을 같이 쓴다."""
    from fastapi.testclient import TestClient

    from app.main import create_app

    c = TestClient(create_app())
    c.post("/login", data={"phone": "01000000002", "password": DEMO_PASSWORD})
    return c


def _names(db):
    from app.models import VcContact

    db.expire_all()
    return sorted(r.name for r in db.query(VcContact).all())


def _delete(client, ids, confirm=None):
    body = {"contact_ids": ids}
    if confirm is not None:
        body["confirm"] = confirm
    return client.post("/api/contacts/bulk-delete", json=body)


# ═══════════════════════════════════════════════════════════════════════════
# 1. 평소 화면에는 안 보인다
# ═══════════════════════════════════════════════════════════════════════════

def test_평소_화면에는_감춘_줄도_지우는_단추도_없다(team, rows):
    """감춘 것이 기본으로 섞여 나오면 감춘 뜻이 없다.

    지우는 단추도 마찬가지다. 늘 떠 있으면 '감춘 다음에 한 번 더 본다' 는
    걸음이 통째로 무의미해진다 — 그 두 걸음이 이 기능의 안전장치 전부다.
    """
    html = team.get(_url()).text

    assert "라담당" in html, "감추지 않은 줄이 안 보입니다 — 검사가 헛돕니다"
    for name in ("가담당", "나담당", "다담당"):
        assert name not in html, f"평소 화면에 감춘 줄({name})이 섞여 나옵니다"

    assert 'id="hidden-del-bar"' not in html, "평소 화면에 [선택 삭제] 가 서 있습니다"
    assert "hidden-del-cb" not in html, "평소 화면에 체크상자가 서 있습니다"


def test_함께_보기로_들어가야_체크상자가_선다(team, rows):
    """상자는 **감춘 줄에만** 선다.

    [함께 보기] 는 감춘 줄과 보이는 줄을 한 표에 섞는 자리다. 여기서 모든
    줄에 상자가 서면 [전체 선택] 한 번에 멀쩡한 줄이 딸려 들어간다.
    """
    html = team.get(_url(hidden=1)).text

    assert 'id="hidden-del-bar"' in html, "[함께 보기] 인데 [선택 삭제] 가 없습니다"
    assert 'id="pick-all-hidden"' in html, "전체 선택이 없습니다"

    # 줄마다 상자가 섰는지 — 감춘 셋만.
    got = {name for name in ("가담당", "나담당", "다담당", "라담당")
           if f'class="hidden-del-cb"' in _row_html(html, name)}
    assert got == {"가담당", "나담당", "다담당"}, (
        f"체크상자가 감춘 줄에만 서 있지 않습니다: {sorted(got)}")


def _row_html(html: str, name: str) -> str:
    """그 이름이 들어 있는 `<tr>` 한 덩어리."""
    at = html.index(name)
    start = html.rindex("<tr", 0, at)
    return html[start:html.index("</tr>", at)]


def test_스타트업_화면에는_붙지_않는다(client, db, users):
    """이 길은 **투자사 관리 현황 하나만** 쓴다.

    두 화면이 같은 틀(`contacts.html`)을 쓰므로, 조건을 안 걸면 다른 화면에도
    삭제가 저절로 따라 붙는다.
    """
    from app.models import SheetOwner, VcContact
    from app.services import contact_columns as cc

    label = "스타트업 시험 명단"
    db.add(SheetOwner(label=label, user_id=users["u1"].id, layout=cc.STARTUP))
    db.add(VcContact(user_id=users["u1"].id, source_sheet=label,
                     name="바기업", is_hidden=1))
    db.commit()
    client.post("/login", data={"phone": "01000000001",
                                "password": DEMO_PASSWORD})

    html = client.get(f"/startup?sheet={quote(label)}&hidden=1").text
    assert "바기업" in html, "[함께 보기] 로도 감춘 줄이 안 보입니다"
    assert 'id="hidden-del-bar"' not in html, (
        "투자사 관리 현황 말고 다른 화면에 삭제가 붙었습니다")


# ═══════════════════════════════════════════════════════════════════════════
# 2. 확인 없이는 안 지워진다
# ═══════════════════════════════════════════════════════════════════════════

def test_확인_없이_부르면_세어_보기만_하고_한_줄도_안_지운다(team, db, rows):
    """80줄이 한 번에 사라지는 일이다 — 서버가 다시 묻는다.

    확인을 화면(`confirm()` 창)에만 두면 번호를 직접 보내는 길로 아무 말 없이
    사라진다.
    """
    before = _names(db)
    r = _delete(team, [rows["가담당"].id, rows["나담당"].id])
    assert r.status_code == 200
    body = r.json()

    assert body["deleted"] == 0 and body["confirmed"] is False
    assert body["plan"]["total"] == 2 and body["plan"]["deletable"] == 2
    assert _names(db) == before, "확인 전인데 줄이 사라졌습니다"


def test_confirm_이_거짓이면_그것도_안_지운다(team, db, rows):
    """`confirm` 을 실어 보내되 거짓이면 세어 보기와 같다."""
    before = _names(db)
    assert _delete(team, [rows["가담당"].id], confirm=False).json()["deleted"] == 0
    assert _names(db) == before


# ═══════════════════════════════════════════════════════════════════════════
# 3. 고른 줄만 사라진다
# ═══════════════════════════════════════════════════════════════════════════

def test_고른_줄만_지워지고_안_고른_줄은_남는다(team, db, rows):
    r = _delete(team, [rows["가담당"].id, rows["다담당"].id], confirm=True)
    assert r.status_code == 200, r.text
    assert r.json()["deleted"] == 2

    assert _names(db) == ["나담당", "라담당", "마담당"], (
        "고르지 않은 줄까지 사라졌거나, 고른 줄이 남았습니다")


def test_감추지_않은_줄은_지울_수_없다(team, db, rows):
    """감추기가 곧 '지워도 되는지 한 번 더 보는 자리' 다.

    화면에서는 보이는 줄에 상자를 안 세우지만, **화면만 감추면 번호를 직접
    보내는 길이 남는다.**
    """
    before = _names(db)
    r = _delete(team, [rows["가담당"].id, rows["라담당"].id], confirm=True)
    assert r.status_code == 400, r.text
    assert "감춘 줄" in r.json()["detail"]
    assert _names(db) == before, "한 줄이라도 지워졌습니다 — 전부 아니면 전무여야 합니다"


def test_아무것도_안_고르면_거절한다(team, db, rows):
    before = _names(db)
    assert _delete(team, [], confirm=True).status_code == 400
    assert _names(db) == before


# ═══════════════════════════════════════════════════════════════════════════
# 4. 누가 지울 수 있나
# ═══════════════════════════════════════════════════════════════════════════

def test_남의_담당은_못_지운다(other, db, rows):
    """판정은 한 줄 고치기와 **같은 것**이다(`_owned`).

    남의 담당자는 '없는 것' 으로 답한다 — 있는지 없는지도 흘리지 않는다.
    """
    before = _names(db)
    r = other.post("/api/contacts/bulk-delete",
                   json={"contact_ids": [rows["가담당"].id], "confirm": True})
    assert r.status_code == 404, r.text
    assert _names(db) == before


def test_내_것에_남의_것을_한_줄_섞으면_한_줄도_안_지워진다(team, db, rows):
    """부분 삭제는 없다. 고른 것과 사라진 것이 다르면 되돌릴 것을 고를 수 없다."""
    before = _names(db)
    r = _delete(team, [rows["가담당"].id, rows["마담당"].id], confirm=True)
    assert r.status_code == 404
    assert _names(db) == before


def test_관리자는_팀_전체의_감춘_줄을_지운다(client, db, users, rows):
    """보는 쪽과 지우는 쪽이 **같은 판정**이어야 한다.

    관리자 화면에는 팀 전체가 뜬다(`deps.may_manage_team_contacts`). 여기서만
    따로 좁히면 화면에 뜬 줄을 눌러도 404 가 나는, 이 저장소가 반복해서 당한
    어긋남이 또 난다.
    """
    from app.models import User
    from app.services import auth as auth_svc

    db.add(User(id=91, name="관리자시험", phone="01090000001", role="admin",
                password_hash=auth_svc.hash_password(DEMO_PASSWORD)))
    db.commit()
    client.post("/login", data={"phone": "01090000001",
                                "password": DEMO_PASSWORD})

    r = client.post("/api/contacts/bulk-delete",
                    json={"contact_ids": [rows["마담당"].id], "confirm": True})
    assert r.status_code == 200, r.text
    assert "마담당" not in _names(db)


# ═══════════════════════════════════════════════════════════════════════════
# 5. 딸린 자료
# ═══════════════════════════════════════════════════════════════════════════

def test_활동_이력은_함께_사라진다(team, db, rows):
    """시트의 월별 칸을 줄로 편 것이라 그 담당자 줄 밖에서는 뜻이 없다.

    한 줄 지우기가 이미 그렇게 한다 — 여기서 달리 하면 같은 일이 두 가지로
    굴러가고, 남은 활동 줄은 아무 데도 안 뜨는 고아가 된다.
    """
    from app.models import ContactActivity

    cid = rows["가담당"].id
    db.add_all([ContactActivity(contact_id=cid, month="2026-08",
                                kind="deal_intro", content="1회차"),
                ContactActivity(contact_id=cid, month="2026-08",
                                kind="ir_request", content="가나기업")])
    db.commit()

    plan = _delete(team, [cid]).json()["plan"]
    assert plan["activities"] == 2, "함께 사라지는 것을 세어 보여 주지 않습니다"

    assert _delete(team, [cid], confirm=True).status_code == 200
    db.expire_all()
    assert db.query(ContactActivity).filter(
        ContactActivity.contact_id == cid).count() == 0, "고아 활동 이력이 남았습니다"


@pytest.mark.parametrize("key,label", [
    ("sends", "발송 기록"),
    ("ir_requests", "IR 요청"),
    ("meetings", "미팅"),
    ("sequences", "후속 발송"),
])
def test_이력이_걸린_줄은_막힌다(team, db, rows, key, label):
    """지우지 않는다 — **팀의 이력**이라서다.

    주간·월간 보고가 그 줄들을 세어 실적을 낸다. 담당자 한 줄을 정리하려다
    지난달 보고 숫자가 조용히 바뀌면 나중에 어느 쪽이 맞는지 알 수 없다.
    그렇다고 가리키는 줄만 지우면 고아가 된다. 그래서 막고, 무엇이 걸렸는지
    세어서 보여 준다 — 막힌 줄은 감춘 채로 두면 되고 그 상태가 안전하다.
    """
    from app.models import (IrRequest, Meeting, SendItem, SendJob,
                            SendSequence)

    cid = rows["가담당"].id
    if key == "sends":
        job = SendJob(user_id=1, kind="deal_intro", status="done")
        db.add(job)
        db.flush()
        db.add(SendItem(job_id=job.id, contact_id=cid, room_name="가담당 방",
                        message="", status="sent"))
    elif key == "ir_requests":
        db.add(IrRequest(user_id=1, contact_id=cid, company_name="가나기업",
                         requested_at="2026-08-13"))
    elif key == "meetings":
        db.add(Meeting(user_id=1, contact_id=cid, company_name="가나기업",
                       scheduled_at="2026-08-20"))
    else:
        db.add(SendSequence(user_id=1, contact_id=cid, stage=1))
    db.commit()

    # ① 세어 보기 — 무엇이 걸렸는지 이름과 이유를 함께 준다.
    plan = _delete(team, [cid, rows["나담당"].id]).json()["plan"]
    assert plan[key] == 1, f"{label} 을(를) 세지 않습니다"
    assert plan["deletable"] == 1
    assert [b["name"] for b in plan["blocked"]] == ["가담당"]
    assert label in plan["blocked"][0]["why"], (
        f"왜 막혔는지 말해 주지 않습니다: {plan['blocked'][0]['why']}")

    # ② 그대로 밀어붙이면 **한 줄도** 안 지워진다.
    before = _names(db)
    r = _delete(team, [cid, rows["나담당"].id], confirm=True)
    assert r.status_code == 409, r.text
    assert _names(db) == before, (
        "막힌 줄을 뺀 나머지가 지워졌습니다 — 고른 것과 사라진 것이 달라집니다")

    # ③ 걸린 줄을 빼면 나머지는 지워진다.
    assert _delete(team, [rows["나담당"].id], confirm=True).status_code == 200
    db.expire_all()
    assert "가담당" in _names(db) and "나담당" not in _names(db)


def test_담당자_줄을_가리키는_표는_전부_어느_쪽인지_정해져_있다(db):
    """**표를 통째로 훑는다** — 담당자 줄을 가리키는 표가 하나 늘면 걸린다.

    정하지 않은 표는 둘 중 하나가 된다. 조용히 고아로 남거나(그 화면이 깨진다),
    아무도 모르게 함께 사라지거나(팀의 이력이 날아간다). 어느 쪽도 나중에
    알아채기 어렵다 — 만든 사람이 여기서 한 번 고르게 한다.

    `tests/test_edit_log.py` 가 표를 훑어 `WATCHED`/`UNWATCHED` 중 하나를
    고르게 하는 그 방식이다.
    """
    import app.models  # noqa: F401  (Base.metadata 에 모델 등록)
    from app.db import Base
    from app.routers import contacts as router

    decided = {m for _k, m, _l in
               router.CASCADING_LINKS + router.BLOCKING_LINKS}
    missing = []
    for mapper in Base.registry.mappers:
        model = mapper.class_
        if model in decided:
            continue
        for column in mapper.local_table.columns:
            for fk in column.foreign_keys:
                if fk.column.table.name == "vc_contacts":
                    missing.append(f"{model.__tablename__}.{column.key}")

    assert not missing, (
        "담당자 줄을 가리키는데 지울 때 어떻게 할지 정해 두지 않은 표가 "
        "있습니다. app/routers/contacts.py 의 CASCADING_LINKS(함께 지운다) 나 "
        "BLOCKING_LINKS(걸려 있으면 막는다) 중 하나에 적어 주세요:\n"
        + "\n".join(sorted(set(missing))))


def test_막힌_줄의_이력은_그대로_있다(team, db, rows):
    """막았으면 정말 손대지 않아야 한다 — 세어 보기가 이력을 건드리면 안 된다."""
    from app.models import Meeting

    cid = rows["가담당"].id
    db.add(Meeting(user_id=1, contact_id=cid, company_name="가나기업",
                   scheduled_at="2026-08-20"))
    db.commit()

    _delete(team, [cid])
    _delete(team, [cid], confirm=True)
    db.expire_all()
    assert db.query(Meeting).filter(Meeting.contact_id == cid).count() == 1


# ═══════════════════════════════════════════════════════════════════════════
# 6. 수정 로그
# ═══════════════════════════════════════════════════════════════════════════

def _logs(db):
    from app.models import EditLog

    db.expire_all()
    return db.query(EditLog).order_by(EditLog.id).all()


def test_지운_것은_줄마다_한_줄씩_수정_로그에_남는다(team, db, rows):
    """**80줄을 지웠는데 로그가 비면 그것이 이 기능의 가장 큰 구멍이다.**

    한 건으로 뭉치지 않는 것은 #157 의 판단 그대로다 — 되돌릴 것을 고르려면
    "몇 시에 누가 몇 줄" 이 아니라 **어느 줄이 사라졌는지**가 필요하다.

    지우는 사람 본인의 담당분이어도 남는다. 자기 것이라고 빼면, 이 길로 지운
    80줄은 대개 본인 담당이라 로그가 통째로 빈다.
    """
    ids = [rows["가담당"].id, rows["나담당"].id, rows["다담당"].id]
    assert _delete(team, ids, confirm=True).status_code == 200

    logs = [g for g in _logs(db) if g.table_name == "vc_contacts"]
    assert len(logs) == 3, f"줄마다 남지 않았습니다: {len(logs)}건"
    assert {g.row_label for g in logs} == {"가담당", "나담당", "다담당"}
    assert {g.action for g in logs} == {"delete"}
    assert {g.scope for g in logs} == {"mine"}, (
        "자기 담당분을 지웠더니 안 남았거나 범위가 다릅니다")
    assert {g.path for g in logs} == {"/api/contacts/bulk-delete"}
    assert {g.actor_user_id for g in logs} == {1}


def test_세어_보기만_한_것은_로그에_안_남는다(team, db, rows):
    """아무 것도 안 지운 부름이 로그를 채우면 정작 지운 줄이 묻힌다."""
    _delete(team, [rows["가담당"].id])
    assert [g for g in _logs(db) if g.table_name == "vc_contacts"] == []


def test_남의_담당을_지우면_남의_것으로_남는다(client, db, users, rows):
    """관리자가 팀원의 줄을 지운 것이다 — 누구 것이었는지가 로그에 있어야 한다."""
    from app.models import User
    from app.services import auth as auth_svc

    db.add(User(id=92, name="관리자시험", phone="01090000002", role="admin",
                password_hash=auth_svc.hash_password(DEMO_PASSWORD)))
    db.commit()
    client.post("/login", data={"phone": "01090000002",
                                "password": DEMO_PASSWORD})
    client.post("/api/contacts/bulk-delete",
                json={"contact_ids": [rows["마담당"].id], "confirm": True})

    logs = [g for g in _logs(db) if g.table_name == "vc_contacts"]
    assert len(logs) == 1
    assert logs[0].scope == "others" and logs[0].target_user_id == 2


def test_수정_로그_화면이_그_줄을_보여_준다(team, db, users, rows):
    """로그에 남기만 하고 화면이 `공용` 이라고 적으면 읽는 사람이 오독한다.

    지운 사람은 팀원(자기 담당분)이고 로그를 보는 사람은 관리자다 — 실제로
    이 화면을 여는 상황이 그것이다.
    """
    from fastapi.testclient import TestClient

    from app.main import create_app
    from app.models import User
    from app.services import auth as auth_svc

    assert _delete(team, [rows["가담당"].id], confirm=True).status_code == 200

    db.add(User(id=93, name="관리자시험", phone="01090000003", role="admin",
                password_hash=auth_svc.hash_password(DEMO_PASSWORD)))
    db.commit()
    admin = TestClient(create_app())
    admin.post("/login", data={"phone": "01090000003",
                               "password": DEMO_PASSWORD})

    html = admin.get("/team/edit-log?scope=mine").text
    assert "가담당" in html, "지운 줄이 수정 로그 화면에 안 뜹니다"
    assert "삭제" in html
    assert "공용" not in _row_html(html, "가담당"), (
        "자기 담당 줄을 지운 것이 `공용` 으로 적혀 있습니다")
