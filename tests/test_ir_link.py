"""IR 기업 연결 — 스타트업 명단 줄 · 투자컨설턴트 줄을 IR 기업에 **사람이** 잇는다.

지키는 것(`services/ir_link.py` · `routers/ir_link.py` 머리말):

1. 후보 — 이름이 **통째로 같을 때만**(`deal_history._key`). 부분일치는 직접
   찾기에서만. 같은 이름의 IR 기업이 둘이면 `후보 여럿` 이다.
2. **이미 있던 줄은 저절로 잇지 않는다** — 화면을 열어도, 후보가 하나여도.
   (10/22 부터 **새로 생기는 줄**은 이름이 하나 맞으면 저절로 잇는다 —
   `tests/test_company_sync.py`. 그래서 아래 무대는 줄을 먼저 세우고 IR 기업을
   나중에 넣는다 — 기능이 생기기 전부터 있던 줄과 같은 모양이다.)
3. 누가 잇는가 — 그 줄이 사는 화면의 문 그대로(관리자 · 줄의 주인).
4. 일괄 연결은 **후보가 정확히 하나인 줄만**, 확인 화면에 보인 짝 그대로.
5. 잇고 푼 것은 수정 로그에 남는다 — 자기 줄이어도.
6. 판(0097)이 오르내린다.
7. 화면이 뜬다 — 연결 화면 · 수정창 표시 · 투자컨설턴트 `기업명` 칸 표시.

이름은 전부 지어낸 것이다 — 저장소가 공개다.
"""
from __future__ import annotations

import os
import re
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from .conftest import DEMO_PASSWORD

ROOT = Path(__file__).resolve().parent.parent

LIST_U1 = "샘플 스타트업 A"
LIST_U2 = "샘플 스타트업 B"
INVESTORS = "샘플 투자사 명단"


# ── 무대 ────────────────────────────────────────────────────────────────────

@pytest.fixture()
def people(db, users):
    from app.models import User
    from app.services import auth as auth_svc

    pw = auth_svc.hash_password(DEMO_PASSWORD)
    rows = [
        User(id=71, name="관리자시험", phone="01080000001", role="admin",
             can_view_consulting=1, password_hash=pw),
        User(id=73, name="컨설턴트시험", phone="01080000003", role="consultant",
             can_view_consulting=1, password_hash=pw),
    ]
    db.add_all(rows)
    # u1 은 투자컨설턴트 화면도 본다(관리자가 켜 준 팀원). u2 는 못 본다.
    users["u1"].can_view_consulting = 1
    db.commit()
    return {"admin": rows[0], "consultant": rows[1]}


@pytest.fixture()
def stage(db, users, people):
    from app.models import ConsultingCompany, IrCompany, SheetOwner, VcContact
    from app.services import contact_columns as cc

    u1, u2 = users["u1"], users["u2"]
    db.add_all([
        SheetOwner(label=LIST_U1, user_id=u1.id, layout=cc.STARTUP, is_hidden=1),
        SheetOwner(label=LIST_U2, user_id=u2.id, layout=cc.STARTUP, is_hidden=1),
        SheetOwner(label=INVESTORS, user_id=u1.id, layout=cc.INVESTOR, is_hidden=0),
    ])
    ir = {
        "ga": IrCompany(name="(주)가나다랩스", received_at="2026-09-01",
                        assignee_name="홍길동", contract_status="paid"),
        "ra": IrCompany(name="라마바"),
        # 비교용 이름이 같은 둘 — `사아자바이오`.
        "dup1": IrCompany(name="사아자 바이오"),
        "dup2": IrCompany(name="사아자바이오(주)"),
        "cha": IrCompany(name="차카타전자"),
        "long": IrCompany(name="가나라전자"),
        "en": IrCompany(name="Sample Labs"),
    }
    rows = {
        "exact": VcContact(user_id=u1.id, source_sheet=LIST_U1, name="홍길동",
                           firm="라마바"),
        "norm": VcContact(user_id=u1.id, source_sheet=LIST_U1, name="",
                          firm="가나다 랩스"),
        "dup": VcContact(user_id=u1.id, source_sheet=LIST_U1, name="",
                         firm="사아자바이오"),
        "none": VcContact(user_id=u1.id, source_sheet=LIST_U1, name="",
                          firm="파하테크"),
        "partial": VcContact(user_id=u1.id, source_sheet=LIST_U1, name="",
                             firm="가나"),
        "case": VcContact(user_id=u1.id, source_sheet=LIST_U1, name="",
                          firm="sample labs"),
        "hidden": VcContact(user_id=u1.id, source_sheet=LIST_U1, name="",
                            firm="차카타전자", is_hidden=1),
        "other": VcContact(user_id=u2.id, source_sheet=LIST_U2, name="",
                           firm="라마바"),
        # 투자사 명단 줄 — `firm` 이 투자사라 IR 기업에 잇는 줄이 아니다.
        "investor": VcContact(user_id=u1.id, source_sheet=INVESTORS,
                              name="투자담당", firm="라마바"),
    }
    db.add_all(rows.values())
    cons = {
        "mine": ConsultingCompany(user_id=u1.id, sheet="스타트업", position=1,
                                  company_name="가나다랩스 / 무료 / 3%"),
        "theirs": ConsultingCompany(user_id=u2.id, sheet="스타트업", position=2,
                                    company_name="라마바"),
    }
    db.add_all(cons.values())
    db.commit()
    # IR 기업은 **줄 다음에** 넣는다 — 새 줄 자동 연결(`company_sync`)이 안 걸린,
    # 예전부터 있던 줄이다.
    db.add_all(ir.values())
    db.commit()
    return {"ir": ir, "rows": rows, "cons": cons}


@pytest.fixture()
def portal(db, users, people):
    from fastapi.testclient import TestClient

    from app.main import create_app

    app = create_app()

    def sign_in(phone: str):
        client = TestClient(app)
        r = client.post("/login", data={"phone": phone, "password": DEMO_PASSWORD},
                        follow_redirects=False)
        assert r.status_code == 303
        return client

    return {"admin": sign_in("01080000001"), "consultant": sign_in("01080000003"),
            "u1": sign_in("01000000001"), "u2": sign_in("01000000002")}


def _fresh(db, row):
    db.expire_all()
    return db.get(type(row), row.id)


def _link(client, tab, row_id, company_id, **extra):
    return client.post("/ir-link/link", data={"tab": tab, "row_id": row_id,
                                              "company_id": company_id, **extra},
                       follow_redirects=False)


def _unlink(client, tab, row_id):
    return client.post("/ir-link/unlink", data={"tab": tab, "row_id": row_id},
                       follow_redirects=False)


# ── 1. 후보 ─────────────────────────────────────────────────────────────────

def test_후보는_같은_이름_하나_정규화_없음_여럿으로_갈린다(db, stage):
    from app.services import ir_link

    idx = ir_link.index(db)
    rows, ir = stage["rows"], stage["ir"]

    # 글자 그대로 같다.
    assert ir_link.state(idx, rows["exact"]) == ir_link.SINGLE
    assert ir_link.single_candidate(idx, rows["exact"]).id == ir["ra"].id
    # `(주)` · 띄어쓰기가 달라도 같다(`deal_history._key`).
    assert ir_link.state(idx, rows["norm"]) == ir_link.SINGLE
    assert ir_link.single_candidate(idx, rows["norm"]).id == ir["ga"].id
    # 대소문자도.
    assert ir_link.single_candidate(idx, rows["case"]).id == ir["en"].id
    # 같은 이름이 없다.
    assert ir_link.state(idx, rows["none"]) == ir_link.NONE
    assert idx.candidates(ir_link.row_name(rows["none"])) == []
    # 비교용 이름이 같은 IR 기업이 둘 — **하나로 세우지 않는다.**
    assert ir_link.state(idx, rows["dup"]) == ir_link.MULTI
    assert ir_link.single_candidate(idx, rows["dup"]) is None
    assert {c.id for c in idx.candidates("사아자바이오")} == {ir["dup1"].id, ir["dup2"].id}


def test_부분일치는_후보가_아니고_직접_찾기에서만_걸린다(db, stage):
    from app.services import ir_link

    idx = ir_link.index(db)
    partial = stage["rows"]["partial"]          # `가나`
    assert ir_link.state(idx, partial) == ir_link.NONE, \
        "`가나` 가 `가나다랩스` · `가나라전자` 의 후보로 서면 안 된다"
    found = {c.name for c in ir_link.search(idx, "가나")}
    assert {"(주)가나다랩스", "가나라전자"} <= found
    # 통째로 같은 것이 먼저 선다.
    assert ir_link.search(idx, "라마바")[0].name == "라마바"
    assert ir_link.search(idx, "") == []


def test_투자컨설턴트_줄은_기업명만_꺼내_견준다(db, stage):
    from app.services import ir_link

    idx = ir_link.index(db)
    mine = stage["cons"]["mine"]
    assert ir_link.row_name(mine) == "가나다랩스"     # `/ 무료 / 3%` 를 뗐다
    assert ir_link.single_candidate(idx, mine).id == stage["ir"]["ga"].id


def test_중복_이름_묶음을_센다(db, stage):
    from app.services import ir_link

    groups = ir_link.index(db).duplicate_keys()
    assert list(groups) == ["사아자바이오"]


# ── 2. 저절로 잇지 않는다 ───────────────────────────────────────────────────

def test_화면을_열어도_아무것도_안_이어진다(db, stage, portal):
    from app.models import ConsultingCompany, VcContact

    for who in ("u1", "admin"):
        for tab in ("startup", "consulting"):
            assert portal[who].get(f"/ir-link?tab={tab}").status_code == 200
        assert portal[who].get("/ir-link/bulk?tab=startup").status_code == 200
    db.expire_all()
    assert all(c.ir_company_id is None for c in db.query(VcContact).all())
    assert all(c.ir_company_id is None for c in db.query(ConsultingCompany).all())


def test_company_for_는_이은_것만_돌려준다(db, stage):
    from app.services import ir_link

    row, ra = stage["rows"]["exact"], stage["ir"]["ra"]
    # 후보가 하나여도 사람이 잇기 전에는 None 이다.
    assert ir_link.company_for(row) is None
    assert ir_link.link(db, row, ra) is True
    db.commit()
    assert ir_link.company_for(row).id == ra.id          # 세션을 안 넘겨도
    assert ir_link.company_for(row, db).id == ra.id
    assert ir_link.link(db, row, ra) is False            # 같은 곳이면 바뀐 것 없음
    assert ir_link.unlink(db, row) is True
    db.commit()
    assert ir_link.company_for(row) is None
    assert ir_link.unlink(db, row) is False


# ── 3. 누가 잇는가 ──────────────────────────────────────────────────────────

def test_자기_스타트업_줄은_잇고_푼다(db, stage, portal):
    row, ra = stage["rows"]["exact"], stage["ir"]["ra"]
    r = _link(portal["u1"], "startup", row.id, ra.id)
    assert r.status_code == 303, r.text
    assert r.headers["location"].endswith(f"#row-{row.id}")
    assert _fresh(db, row).ir_company_id == ra.id

    r = _unlink(portal["u1"], "startup", row.id)
    assert r.status_code == 303, r.text
    assert _fresh(db, row).ir_company_id is None


def test_남의_스타트업_줄은_못_잇는다_관리자는_된다(db, stage, portal):
    row, ra = stage["rows"]["exact"], stage["ir"]["ra"]      # u1 의 줄
    assert _link(portal["u2"], "startup", row.id, ra.id).status_code == 404
    assert _fresh(db, row).ir_company_id is None

    assert _link(portal["admin"], "startup", row.id, ra.id).status_code == 303
    assert _fresh(db, row).ir_company_id == ra.id
    # 푸는 것도 같은 문이다.
    assert _unlink(portal["u2"], "startup", row.id).status_code == 404
    assert _fresh(db, row).ir_company_id == ra.id


def test_투자사_명단_줄은_잇는_줄이_아니다(db, stage, portal):
    row, ra = stage["rows"]["investor"], stage["ir"]["ra"]
    assert _link(portal["u1"], "startup", row.id, ra.id).status_code == 404
    assert _fresh(db, row).ir_company_id is None


def test_없는_IR_기업이나_탭은_거절한다(db, stage, portal):
    row = stage["rows"]["exact"]
    assert _link(portal["u1"], "startup", row.id, 99999).status_code == 404
    assert _link(portal["u1"], "nope", row.id, stage["ir"]["ra"].id).status_code == 400
    assert _fresh(db, row).ir_company_id is None


def test_투자컨설턴트_줄은_고칠_수_있는_줄만(db, stage, portal):
    mine, theirs = stage["cons"]["mine"], stage["cons"]["theirs"]
    ga, ra = stage["ir"]["ga"], stage["ir"]["ra"]
    # 화면을 볼 수 있는 팀원 — 자기 줄은 되고 남의 줄은 안 된다(보이기만 한다).
    assert _link(portal["u1"], "consulting", mine.id, ga.id).status_code == 303
    assert _fresh(db, mine).ir_company_id == ga.id
    assert _link(portal["u1"], "consulting", theirs.id, ra.id).status_code == 404
    # 그 화면이 꺼진 팀원은 자기 줄이어도 못 닿는다.
    r = _link(portal["u2"], "consulting", theirs.id, ra.id)
    assert r.status_code in (403, 404), r.status_code
    assert _fresh(db, theirs).ir_company_id is None
    # 관리자는 된다.
    assert _link(portal["admin"], "consulting", theirs.id, ra.id).status_code == 303
    assert _fresh(db, theirs).ir_company_id == ra.id


def test_투자컨설턴트_역할은_이_화면에_못_들어온다(db, stage, portal):
    client = portal["consultant"]
    page = client.get("/ir-link", follow_redirects=False)
    assert page.status_code != 200 or "IR 기업 연결" not in page.text
    r = _link(client, "startup", stage["rows"]["exact"].id, stage["ir"]["ra"].id)
    assert r.status_code in (302, 303, 403)
    assert _fresh(db, stage["rows"]["exact"]).ir_company_id is None


def test_한_IR_기업에_여러_줄이_이어져도_되고_그_수를_보인다(db, stage, portal):
    from app.services import ir_link

    ra = stage["ir"]["ra"]
    assert _link(portal["u1"], "startup", stage["rows"]["exact"].id, ra.id).status_code == 303
    assert _link(portal["u2"], "startup", stage["rows"]["other"].id, ra.id).status_code == 303
    assert ir_link.link_counts(db)[ra.id] == 2
    html = portal["u1"].get("/ir-link?tab=startup&show=linked").text
    assert "이 기업에 이어진 줄 2개" in html


# ── 4. 일괄 연결 ────────────────────────────────────────────────────────────

def _tokens(html: str) -> list:
    return re.findall(r'name="pair" value="(\d+:\d+)"', html)


def test_일괄_연결은_후보가_하나인_내_줄만_세운다(db, stage, portal):
    rows, ir = stage["rows"], stage["ir"]
    html = portal["u1"].get("/ir-link/bulk?tab=startup").text
    want = {f"{rows['exact'].id}:{ir['ra'].id}", f"{rows['norm'].id}:{ir['ga'].id}",
            f"{rows['case'].id}:{ir['en'].id}"}
    assert set(_tokens(html)) == want, "후보 여럿·없음·감춘 줄·남의 줄이 섞였다"
    assert 'data-testid="ir-link-bulk-count"' in html
    assert f'<span id="ir-link-bulk-n">{len(want)}</span>줄' in html


def test_일괄_연결은_보인_짝_그대로만_잇는다(db, stage, portal):
    rows, ir = stage["rows"], stage["ir"]
    good = [f"{rows['exact'].id}:{ir['ra'].id}", f"{rows['norm'].id}:{ir['ga'].id}"]
    forged = [
        f"{rows['dup'].id}:{ir['dup1'].id}",      # 후보가 여럿인 줄
        f"{rows['none'].id}:{ir['cha'].id}",      # 후보가 없는 줄
        f"{rows['other'].id}:{ir['ra'].id}",      # 남의 줄
        f"{rows['case'].id}:{ir['ra'].id}",       # 다른 기업으로 바꿔 친 짝
        f"{rows['hidden'].id}:{ir['cha'].id}",    # 감춘 줄
        "엉터리",
    ]
    r = portal["u1"].post("/ir-link/bulk", data={"tab": "startup", "pair": good + forged},
                          follow_redirects=False)
    assert r.status_code == 303, r.text
    assert "msg=" in r.headers["location"]
    assert _fresh(db, rows["exact"]).ir_company_id == ir["ra"].id
    assert _fresh(db, rows["norm"]).ir_company_id == ir["ga"].id
    for key in ("dup", "none", "other", "case", "hidden", "investor", "partial"):
        assert _fresh(db, rows[key]).ir_company_id is None, key


def test_이미_이은_줄은_일괄_연결에_다시_안_선다(db, stage, portal):
    rows, ir = stage["rows"], stage["ir"]
    # 사람이 다른 기업으로 이어 둔 줄 — 후보가 하나여도 덮지 않는다.
    assert _link(portal["u1"], "startup", rows["exact"].id, ir["cha"].id).status_code == 303
    html = portal["u1"].get("/ir-link/bulk?tab=startup").text
    assert not any(t.startswith(f"{rows['exact'].id}:") for t in _tokens(html))
    portal["u1"].post("/ir-link/bulk",
                      data={"tab": "startup", "pair": [f"{rows['exact'].id}:{ir['ra'].id}"]},
                      follow_redirects=False)
    assert _fresh(db, rows["exact"]).ir_company_id == ir["cha"].id


def test_관리자의_일괄_연결은_팀_전체_줄을_받는다(db, stage, portal):
    rows, ir = stage["rows"], stage["ir"]
    tokens = _tokens(portal["admin"].get("/ir-link/bulk?tab=startup").text)
    assert f"{rows['other'].id}:{ir['ra'].id}" in tokens
    r = portal["admin"].post("/ir-link/bulk", data={"tab": "startup", "pair": tokens},
                             follow_redirects=False)
    assert r.status_code == 303
    assert _fresh(db, rows["other"]).ir_company_id == ir["ra"].id
    assert _fresh(db, rows["dup"]).ir_company_id is None


def test_투자컨설턴트_탭도_일괄로_잇는다(db, stage, portal):
    cons, ir = stage["cons"], stage["ir"]
    tokens = _tokens(portal["u1"].get("/ir-link/bulk?tab=consulting").text)
    assert tokens == [f"{cons['mine'].id}:{ir['ga'].id}"], "남의 줄이 섞였다"
    portal["u1"].post("/ir-link/bulk", data={"tab": "consulting", "pair": tokens},
                      follow_redirects=False)
    assert _fresh(db, cons["mine"]).ir_company_id == ir["ga"].id
    assert _fresh(db, cons["theirs"]).ir_company_id is None


# ── 5. 수정 로그 ────────────────────────────────────────────────────────────

def _logs(db):
    from app.models import EditLog

    db.expire_all()
    return [x for x in db.query(EditLog).order_by(EditLog.id).all()
            if '"ir_company_id"' in (x.changes_json or "")]


def test_자기_줄을_이어도_로그에_남는다(db, stage, portal):
    import json

    from app.services import edit_log

    row, ra = stage["rows"]["exact"], stage["ir"]["ra"]
    _link(portal["u1"], "startup", row.id, ra.id)
    _unlink(portal["u1"], "startup", row.id)
    logs = _logs(db)
    assert len(logs) == 2, "잇고 푼 것이 한 줄씩 남아야 한다"
    first = logs[0]
    assert first.table_name == "vc_contacts" and first.row_id == row.id
    assert first.scope == edit_log.SCOPE_MINE
    assert first.path == "/ir-link/link"
    change = next(c for c in json.loads(first.changes_json)
                  if c["field"] == "ir_company_id")
    assert change["before"] is None and change["after"] == ra.id

    # 로그 화면은 번호가 아니라 기업 이름을 보인다.
    shown = edit_log.recent(db)
    # 잇는 순간 IR 의 빈칸도 채워(`company_sync`) 같은 주소의 IR 줄 로그가 함께 선다 —
    # 그중 연결 칸을 가진 줄을 본다.
    item = next(c for x in shown if x["path"] == "/ir-link/link"
                for c in x["changes"] if c["label"] == "IR 기업 연결")
    assert item["after"] == "라마바"
    assert item["before"] == "(빈 값)"


def test_남의_줄을_이으면_남의_것으로_남는다(db, stage, portal):
    from app.services import edit_log

    row, ra = stage["rows"]["exact"], stage["ir"]["ra"]
    _link(portal["admin"], "startup", row.id, ra.id)
    log = _logs(db)[-1]
    assert log.scope == edit_log.SCOPE_OTHERS
    assert log.target_user_id == row.user_id


def test_일괄_연결은_줄마다_남는다(db, stage, portal):
    tokens = _tokens(portal["u1"].get("/ir-link/bulk?tab=startup").text)
    portal["u1"].post("/ir-link/bulk", data={"tab": "startup", "pair": tokens},
                      follow_redirects=False)
    assert len(_logs(db)) == len(tokens)


def test_자기_줄의_다른_칸은_여전히_안_남는다(db, stage, portal):
    """`ALWAYS_FIELDS` 가 문을 넓힌 것은 그 칸 하나다."""
    from app.models import EditLog

    row = stage["rows"]["exact"]
    before = db.query(EditLog).count()
    r = portal["u1"].patch(f"/api/contacts/{row.id}", json={"memo": "고친 메모"})
    assert r.status_code == 200, r.text
    db.expire_all()
    assert db.query(EditLog).count() == before


# ── 6. IR 기업을 지울 때 ────────────────────────────────────────────────────

def test_이어진_IR_기업은_평범한_삭제가_막고_강제_삭제는_연결만_끊는다(db, stage, portal):
    row, ra = stage["rows"]["exact"], stage["ir"]["ra"]
    _link(portal["u1"], "startup", row.id, ra.id)
    _link(portal["admin"], "consulting", stage["cons"]["theirs"].id, ra.id)

    plan = portal["admin"].get(f"/api/companies/{ra.id}/delete-plan").json()
    assert plan["counts"]["startup_links"] == 1
    assert plan["counts"]["consulting_links"] == 1

    r = portal["admin"].delete(f"/api/companies/{ra.id}")
    assert r.status_code == 400
    assert "스타트업 명단 연결 1건" in r.text

    r = portal["admin"].post(f"/api/companies/{ra.id}/force-delete",
                             json={"confirm_name": "라마바"})
    assert r.status_code == 200, r.text
    got = _fresh(db, row)
    assert got is not None and got.ir_company_id is None, "줄은 남고 연결만 끊긴다"
    assert _fresh(db, stage["cons"]["theirs"]).ir_company_id is None


# ── 7. 판(0097)이 오르내린다 ────────────────────────────────────────────────

REVISION = "0097_ir_company_link"
PARENT = "0096_activity_sequence_trace"


def _alembic(db_path: Path, *args: str) -> subprocess.CompletedProcess:
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{db_path}",
           "DEALFLOW_DATA_DIR": str(db_path.parent)}
    return subprocess.run([sys.executable, "-m", "alembic", *args],
                          cwd=ROOT, env=env, capture_output=True, text=True)


def _table_sql(db_path: Path, table: str) -> str:
    con = sqlite3.connect(db_path)
    try:
        return con.execute("select sql from sqlite_master where name=?",
                           (table,)).fetchone()[0]
    finally:
        con.close()


def test_판이_오르내리고_외래키가_붙는다(tmp_path):
    if shutil.which("alembic") is None and not (ROOT / "alembic.ini").exists():
        pytest.skip("alembic 이 없습니다")
    db_path = tmp_path / "t.db"
    up = _alembic(db_path, "upgrade", "head")
    assert up.returncode == 0, up.stdout + up.stderr
    for table in ("vc_contacts", "consulting_companies"):
        assert "ir_company_id" in _table_sql(db_path, table)

    down = _alembic(db_path, "downgrade", PARENT)
    assert down.returncode == 0, down.stdout + down.stderr
    for table in ("vc_contacts", "consulting_companies"):
        assert "ir_company_id" not in _table_sql(db_path, table), "내렸는데 칸이 남았다"

    # 이번에는 **이 판의 ALTER 로** 붙는다(빈 DB 길은 0001 이 붙였다).
    up = _alembic(db_path, "upgrade", "head")
    assert up.returncode == 0, up.stdout + up.stderr
    for table in ("vc_contacts", "consulting_companies"):
        sql = _table_sql(db_path, table)
        assert re.search(r"ir_company_id INTEGER REFERENCES ir_companies", sql), sql


def test_판은_값을_채우지_않는다():
    """저절로 잇지 않는다 — 판에서도."""
    src = (ROOT / "alembic" / "versions" / f"{REVISION}.py").read_text(encoding="utf-8")
    assert "UPDATE" not in src.upper().replace("UPGRADE", "")
    assert "INSERT" not in src.upper()


# ── 8. 화면 ─────────────────────────────────────────────────────────────────

def test_연결_화면이_숫자와_후보를_보인다(db, stage, portal):
    rows, ir = stage["rows"], stage["ir"]
    html = portal["u1"].get("/ir-link?tab=startup").text
    assert "IR 기업 연결" in html
    m = re.search(r'data-testid="ir-link-summary">(.*?)</p>', html, re.S)
    summary = re.sub(r"<[^>]+>|\s+", "", m.group(1))
    # 내 줄(감춘 줄 뺌): exact · norm · case = 하나, dup = 여럿, none · partial = 없음.
    assert "6줄" in summary
    assert "연결됨0" in summary and "후보하나3" in summary
    assert "후보여럿1" in summary and "후보없음2" in summary
    # 후보의 고르는 칸 — 수신일 · 담당자 · 계약.
    assert "2026-09-01" in html and "홍길동" in html and "유료계약완료" in html
    assert html.count('class="linkbtn ir-link-btn"') >= 4
    # 남의 줄 · 감춘 줄 · 투자사 줄은 안 선다.
    for key in ("other", "hidden", "investor"):
        assert f'id="row-{rows[key].id}"' not in html, key
    assert "일괄 연결 (3줄)" in html
    # 같은 이름 IR 기업 묶음이 있다는 것을 알린다.
    assert "같은 이름 여럿" in html


def test_거르기_칩(db, stage, portal):
    rows, ir = stage["rows"], stage["ir"]
    _link(portal["u1"], "startup", rows["exact"].id, ir["ra"].id)
    client = portal["u1"]

    def ids(show):
        html = client.get(f"/ir-link?tab=startup&show={show}").text
        return {int(x) for x in re.findall(r'id="row-(\d+)"', html)}

    assert ids("linked") == {rows["exact"].id}
    assert ids("cand") == {rows["norm"].id, rows["case"].id, rows["dup"].id}
    assert ids("none") == {rows["none"].id, rows["partial"].id}
    html = client.get("/ir-link?tab=startup&show=linked").text
    assert "연결 해제" in html


def test_줄_하나를_펴고_직접_찾는다(db, stage, portal):
    row = stage["rows"]["partial"]
    html = portal["u1"].get(f"/ir-link?tab=startup&row={row.id}&q=가나").text
    assert 'id="ir-link-results"' in html
    assert "(주)가나다랩스" in html and "가나라전자" in html
    # 감춘 줄도 펴서 잇는다(수정창에서 넘어온다).
    hidden = stage["rows"]["hidden"]
    html = portal["u1"].get(f"/ir-link?tab=startup&row={hidden.id}").text
    assert f'id="row-{hidden.id}"' in html and "차카타전자" in html
    # 남의 줄은 펴지지 않는다.
    other = stage["rows"]["other"]
    html = portal["u1"].get(f"/ir-link?tab=startup&row={other.id}").text
    assert "찾을 수 없습니다" in html and f'id="row-{other.id}"' not in html


def test_투자컨설턴트_탭은_볼_수_있는_사람에게만(db, stage, portal):
    cons = stage["cons"]
    html = portal["u1"].get("/ir-link?tab=consulting").text
    assert f'id="row-{cons["mine"].id}"' in html
    assert f'id="row-{cons["theirs"].id}"' not in html     # 볼 수만 있는 남의 줄
    assert "가나다랩스" in html
    # 그 화면이 꺼진 팀원에게는 탭이 없고 스타트업 탭으로 연다.
    html = portal["u2"].get("/ir-link?tab=consulting").text
    assert "?tab=consulting" not in html
    assert f'id="row-{stage["rows"]["other"].id}"' in html


def test_IR_기업_현황_탭과_스타트업_툴바에_서고_좌측_메뉴에는_없다(db, stage, portal, people):
    """좌측 메뉴가 아니라 IR 기업 현황의 넷째 탭 · 스타트업 툴바에 선다 —
    볼 사람은 라우터와 같다(투자컨설턴트 역할만 빼고)."""
    from app import ui

    assert all(m["href"] != "/ir-link" for m in ui.MENU)
    tab = re.compile(r'class="sheet-tab\s*(active)?"\s+href="/ir-link"')
    menu = re.compile(r'class="menu-item[^"]*"\s+href="/ir-link"')
    for who in ("u1", "u2", "admin"):
        html = portal[who].get("/companies").text
        nav = re.search(r'<nav class="sheet-tabs co-tabs">.*?</nav>', html, re.S).group(0)
        m = tab.search(nav)
        assert m and not m.group(1), who
        assert 'id="ir-link-link" href="/ir-link?tab=startup"' in portal[who].get("/startup").text, who
        assert not menu.search(html), who
    # 이 화면에서는 그 탭에 불이 들어오고, 좌측 메뉴는 IR 기업 현황이 켜진다.
    html = portal["u1"].get("/ir-link").text
    nav = re.search(r'<nav class="sheet-tabs co-tabs">.*?</nav>', html, re.S).group(0)
    assert tab.search(nav).group(1) == "active"
    assert nav.count('class="sheet-tab active"') == 1
    assert re.search(r'class="menu-item\s*active"\s+href="/companies"', html)
    assert not menu.search(html)
    # 투자컨설턴트(역할)에게는 어디에도 없다 — 판정은 메뉴의 것(`can_see`) 그대로다.
    assert not ui.can_see(people["consultant"], {"href": "/ir-link"})
    assert ui.can_see(people["admin"], {"href": "/ir-link"})
    for path in ("/consulting", "/companies", "/startup", "/ir-link"):
        assert 'href="/ir-link' not in portal["consultant"].get(path).text, path


def test_수정창이_연결_표시를_받는다(db, stage, portal):
    row, ra = stage["rows"]["exact"], stage["ir"]["ra"]
    got = portal["u1"].get(f"/api/contacts/{row.id}").json()["ir_link"]
    assert got["linked"] is False and got["candidates"] == 1
    assert got["link_href"] == f"/ir-link?tab=startup&row={row.id}"
    _link(portal["u1"], "startup", row.id, ra.id)
    got = portal["u1"].get(f"/api/contacts/{row.id}").json()["ir_link"]
    assert got["linked"] is True and got["name"] == "라마바"
    assert got["company_href"].startswith("/companies?q=")


def test_스타트업_화면에만_연결_자리가_선다(db, stage, portal):
    startup = portal["u1"].get(f"/startup?sheet={LIST_U1}").text
    assert 'id="ir-link-link"' in startup and 'id="ir-link-badge"' in startup
    assert "js/ir_link_badge.js" in startup
    investors = portal["u1"].get(f"/contacts?sheet={INVESTORS}").text
    assert 'id="ir-link-badge"' not in investors and "ir_link_badge.js" not in investors


def test_투자컨설턴트_기업명_칸에_표시가_선다(db, stage, portal):
    cons, ga = stage["cons"], stage["ir"]["ga"]
    _link(portal["u1"], "consulting", cons["mine"].id, ga.id)
    html = portal["admin"].get("/consulting").text
    # 값은 `.cell-main` 안 — 편집기가 그것만 읽는다(표시 글자가 기업명에 안 섞인다).
    assert re.search(r'data-field="company_name"><div class="cell-main">가나다랩스 / 무료 / 3%</div>'
                     r'<div class="ir-link-sub muted">IR 기업: <a href="/companies\?q=[^"]+">'
                     r'\(주\)가나다랩스</a> \(연결됨\)</div>', html), "연결 표시가 없다"
    assert f'/ir-link?tab=consulting&amp;row={cons["theirs"].id}' in html \
        or f'/ir-link?tab=consulting&row={cons["theirs"].id}' in html
    # 볼 수만 있는 남의 줄에는 [연결하기] 가 안 선다(눌러도 그 화면에 없다).
    seen = portal["u1"].get("/consulting").text
    assert f'row={cons["theirs"].id}' not in seen
    assert "ir-link-sub" in seen
    # 투자컨설턴트(역할)에게는 갈 데가 없는 링크라 안 세운다.
    mine = portal["consultant"].get("/consulting").text
    assert "ir-link-sub" not in mine


def test_브라우저_쪽은_node_로_잰다():
    node = shutil.which("node")
    if node is None:
        pytest.skip("node 미설치 — 호스트에서 `node tests/js/ir_link_test.js`")
    js = Path(__file__).resolve().parent / "js" / "ir_link_test.js"
    done = subprocess.run([node, str(js)], capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stdout + done.stderr
