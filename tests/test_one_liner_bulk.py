"""[전체 자동조합] — 미리보기 → 골라서 적용 → 되돌리기.

## 왜 이 검사가 있나

사용자 요청은 "기업 하나하나씩 눌러서 자동조합을 눌러야 하는 구조인데 전체에
대해서 자동조합이 되게끔" 이었다. 그런데 이건 **빈 칸을 채우는 일이 아니라
이미 적힌 문장을 갈아엎는 일**이다 — 운영과 같은 사본 344곳에서 45곳만 빈
칸이고 181곳은 사람이 쓴 값을 덮는 쪽이다. 덮는 쪽이 늘 나은 것도 아니라서
(원본의 오타를 그대로 들고 오거나, 손으로 덧붙여 둔 매출이 빠지는 예가 있다)
**미리 보고 골라서** 적용하고, **되돌릴 수 있어야** 한다.

여기서 못 박는 것은 넷이다.

  1. 미리보기와 적용이 **같은 판단**(`one_liner.bulk_rows`)을 지난다 —
     "미리보기엔 A 인데 눌렀더니 B" 가 안 나온다
  2. 고른 것만 바뀐다
  3. 되돌리면 **바꾸기 전 값 그대로** 돌아오고, 그 뒤에 손으로 고친 줄은
     되돌리기가 건드리지 않는다
  4. 적용한 줄은 **AUTO 가 되어** 그다음부터 스타트업DB 를 고치면 따라온다
     — 사용자가 "동기화가 안 된다" 고 한 것의 진짜 해결이 이것이다

기업명은 **전부 지어낸 것**이다(공개 저장소).
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from app.models import IrCompany, OneLinerBackup

from .conftest import DEMO_PASSWORD

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture()
def people(db, users):
    """관리자 한 명. conftest 의 두 계정은 둘 다 일반 팀원이다."""
    from app.models import User
    from app.services import auth as auth_svc

    row = User(id=93, name="관리자시험", phone="01000000093", role="admin",
               password_hash=auth_svc.hash_password(DEMO_PASSWORD))
    db.add(row)
    db.commit()
    return row


@pytest.fixture()
def portal(db, users, people):
    """역할별로 따로 로그인한 클라이언트(test_company_status_and_delete 와 같은 방식)."""
    from fastapi.testclient import TestClient

    from app.main import create_app

    app = create_app()

    def sign_in(phone: str):
        client = TestClient(app)
        client.post("/login", data={"phone": phone, "password": DEMO_PASSWORD})
        return client

    return {"admin": sign_in("01000000093"), "member": sign_in("01000000001")}


@pytest.fixture()
def rows(db):
    """네 갈래를 **한 벌씩** 심는다 — 목록에 서는 둘과 안 서는 둘.

    운영의 분포를 그대로 옮기지 않고 갈래만 심는 이유는, 여기서 재는 것이
    '몇 곳인가' 가 아니라 '어느 갈래가 목록에 서는가' 이기 때문이다.
    """
    made = {
        # ① 사람이 쓴 값이 있다 → 덮는 쪽. 목록에 선다.
        "manual": IrCompany(name="가나테크", business_desc="산업용 센서 제조",
                            revenue_2024="8.9억", one_liner="사람이 다듬어 쓴 소개"),
        # ② 비어 있다 → 채우는 쪽. 목록에 선다.
        "empty": IrCompany(name="나다물류", business_desc="물류 최적화",
                           revenue_2024="4억", one_liner=None),
        # ③ 이미 조합값과 글자까지 같다 → 눌러도 아무 일이 안 난다. 안 선다.
        "same": IrCompany(name="다라소재", business_desc="소재 제조",
                          one_liner="소재 제조"),
        # ④ 조합할 재료가 없다 → 만들 것이 없다. 안 선다.
        #    여기서 빈 줄을 만들어 멀쩡한 소개를 지우면 제일 나쁘다.
        "bare": IrCompany(name="라마핀테크", one_liner="사람이 쓴 소개뿐"),
    }
    db.add_all(list(made.values()))
    db.commit()
    return made


def _preview(client):
    r = client.get("/api/one-liner/bulk")
    assert r.status_code == 200, r.text
    return r.json()


# --- ① 목록에 무엇이 서는가 ---------------------------------------------------

def test_바뀔_곳만_목록에_선다(portal, rows):
    body = _preview(portal["admin"])
    got = {r["id"] for r in body["rows"]}
    assert got == {rows["manual"].id, rows["empty"].id}, (
        "이미 같은 곳이나 재료가 없는 곳이 목록에 서면, 고를 것이 없는 줄을 "
        "고르게 만든다")

    counts = body["counts"]
    assert counts["changes"] == 2
    assert counts["filled"] == 1        # 덮는 쪽
    assert counts["empty"] == 1         # 채우는 쪽
    assert counts["unchanged"] == 1
    assert counts["no_source"] == 1
    assert counts["total"] == 4, "왜 4곳인데 2줄뿐인지 화면이 말할 수 있어야 한다"


def test_지금_값과_조합값을_나란히_준다(portal, rows):
    """사람이 고르려면 **무엇이 무엇으로** 바뀌는지 둘 다 보여야 한다."""
    row = next(r for r in _preview(portal["admin"])["rows"]
               if r["id"] == rows["manual"].id)
    assert row["current"] == "사람이 다듬어 쓴 소개"
    assert row["suggestion"] == "산업용 센서 제조 | 매출 8.9억"
    assert row["filled"] is True
    assert row["name"] == "가나테크"


def test_미리보기는_저장하지_않는다(portal, db, rows):
    _preview(portal["admin"])
    db.refresh(rows["manual"])
    assert rows["manual"].one_liner == "사람이 다듬어 쓴 소개"


# --- ② 고른 것만 바뀐다 -------------------------------------------------------

def test_고른_곳만_바뀐다(portal, db, rows):
    r = portal["admin"].post("/api/one-liner/bulk",
                             json={"company_ids": [rows["empty"].id]})
    assert r.status_code == 200, r.text
    assert r.json()["applied"] == 1

    db.refresh(rows["empty"]); db.refresh(rows["manual"])
    assert rows["empty"].one_liner == "물류 최적화 | 매출 4억"
    assert rows["manual"].one_liner == "사람이 다듬어 쓴 소개", "안 고른 줄이 바뀌었다"


def test_아무것도_안_고르면_거절한다(portal):
    r = portal["admin"].post("/api/one-liner/bulk", json={"company_ids": []})
    assert r.status_code == 400


def test_미리보기와_적용이_같은_판단을_지난다(portal, db, rows):
    """**목록에 서지 않는 줄은 id 를 직접 보내도 안 바뀐다.**

    화면이 보여준 목록과 서버가 바꾸는 목록이 두 벌이면 "미리보기엔 A 인데
    눌렀더니 B" 가 된다. 적용은 목록을 **다시 만들어** 그 안에 있는 id 에만
    적용하므로, 재료가 없는 줄(④)은 보내도 걸러진다.
    """
    r = portal["admin"].post("/api/one-liner/bulk",
                             json={"company_ids": [rows["bare"].id]})
    assert r.status_code == 409, "목록에 없던 id 가 그대로 먹히면 안 된다"
    db.refresh(rows["bare"])
    assert rows["bare"].one_liner == "사람이 쓴 소개뿐", "재료가 없는데 덮였다"


def test_미리보기를_띄워_둔_사이에_값이_바뀌면_그_줄은_건너뛴다(portal, db, rows):
    """미리보기가 낡았을 수 있다 — 화면이 보여주지 못한 문장을 저장하지 않는다."""
    # 그 사이 누군가 손으로 소개를 조합값과 똑같이 맞춰 두었다 → 바꿀 것이 없다.
    rows["empty"].one_liner = "물류 최적화 | 매출 4억"
    db.commit()

    r = portal["admin"].post(
        "/api/one-liner/bulk",
        json={"company_ids": [rows["empty"].id, rows["manual"].id]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["applied"] == 1 and body["skipped"] == 1


# --- ③ 되돌리기 ---------------------------------------------------------------

def test_되돌리면_바꾸기_전_값_그대로_온다(portal, db, rows):
    ids = [rows["manual"].id, rows["empty"].id]
    portal["admin"].post("/api/one-liner/bulk", json={"company_ids": ids})
    db.refresh(rows["manual"]); db.refresh(rows["empty"])
    assert rows["manual"].one_liner == "산업용 센서 제조 | 매출 8.9억"

    r = portal["admin"].post("/api/one-liner/bulk/undo")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["restored"] == 2 and body["kept"] == 0

    db.refresh(rows["manual"]); db.refresh(rows["empty"])
    assert rows["manual"].one_liner == "사람이 다듬어 쓴 소개"
    # 비어 있던 줄은 **다시 비운다.** `''` 로 되돌리면 '비어 있었다' 가 사라진다.
    assert rows["empty"].one_liner is None


def test_되돌리기가_그_뒤에_손으로_고친_줄은_안_덮는다(portal, db, rows):
    """제일 나쁜 고장이다 — 되돌리기가 방금 쓴 문장을 지운다."""
    portal["admin"].post("/api/one-liner/bulk",
                         json={"company_ids": [rows["manual"].id]})
    rows["manual"].one_liner = "적용 뒤에 사람이 다시 쓴 소개"
    db.commit()

    body = portal["admin"].post("/api/one-liner/bulk/undo").json()
    assert body["restored"] == 0 and body["kept"] == 1, "지켰다는 사실을 알려야 한다"
    db.refresh(rows["manual"])
    assert rows["manual"].one_liner == "적용 뒤에 사람이 다시 쓴 소개"


def test_되돌린_묶음은_두_번_되돌아가지_않는다(portal, db, rows):
    portal["admin"].post("/api/one-liner/bulk",
                         json={"company_ids": [rows["manual"].id]})
    portal["admin"].post("/api/one-liner/bulk/undo")
    r = portal["admin"].post("/api/one-liner/bulk/undo")
    assert r.status_code == 404
    assert db.query(OneLinerBackup).count() == 0


def test_되돌리기는_직전_묶음만_되돌린다(portal, db, rows):
    """두 번 눌렀으면 **나중 것**만 돌아온다 — 다른 때 바꾼 줄까지 끌고 오면
    사람은 무엇이 돌아온 것인지 알 수 없다."""
    portal["admin"].post("/api/one-liner/bulk",
                         json={"company_ids": [rows["manual"].id]})
    portal["admin"].post("/api/one-liner/bulk",
                         json={"company_ids": [rows["empty"].id]})

    body = portal["admin"].post("/api/one-liner/bulk/undo").json()
    assert body["restored"] == 1
    db.refresh(rows["manual"]); db.refresh(rows["empty"])
    assert rows["empty"].one_liner is None, "나중 묶음이 돌아와야 한다"
    assert rows["manual"].one_liner == "산업용 센서 제조 | 매출 8.9억", \
        "먼저 묶음까지 돌아왔다"


def test_되돌릴_것이_있는지_화면이_안다(portal, rows):
    assert _preview(portal["admin"])["undo"]["count"] == 0
    portal["admin"].post("/api/one-liner/bulk",
                         json={"company_ids": [rows["manual"].id]})
    assert _preview(portal["admin"])["undo"]["count"] == 1


# --- ④ 적용한 줄은 그 뒤로 저절로 따라온다 -----------------------------------

def test_적용한_줄은_AUTO_가_되어_스타트업DB_를_고치면_따라온다(portal, db, rows):
    """사용자가 "동기화가 안 된다" 고 한 것의 **진짜 해결**이 이것이다.

    스타트업DB 를 고치면 자동 조합은 원래 따라온다 — 다만 **자동으로 만든
    값이었을 때만** 그렇다. 사람이 쓴 값은 일부러 안 덮기 때문에(`origin`),
    한 번 일괄 적용으로 정리해 두면 그 줄들이 AUTO 가 되어 그다음부터는 저절로
    따라온다. 새 동기화 장치를 만들 필요가 없다.
    """
    admin = portal["admin"]
    cid = rows["manual"].id

    # 적용 전 — 사람이 쓴 값이라 스타트업DB 를 고쳐도 안 따라온다.
    admin.patch(f"/api/companies/{cid}", json={"revenue_2024": "10억"})
    db.refresh(rows["manual"])
    assert rows["manual"].one_liner == "사람이 다듬어 쓴 소개"

    admin.post("/api/one-liner/bulk", json={"company_ids": [cid]})
    db.refresh(rows["manual"])
    assert rows["manual"].one_liner == "산업용 센서 제조 | 매출 10억"

    # 적용 후 — 이제 따라온다.
    admin.patch(f"/api/companies/{cid}", json={"revenue_2025": "20억"})
    db.refresh(rows["manual"])
    assert rows["manual"].one_liner == "산업용 센서 제조 | 매출 24년 10억, 25년 20억", \
        "일괄 적용 뒤에도 안 따라오면 사용자가 겪던 문제가 그대로다"


# --- ⑤ 누가 쓸 수 있나 --------------------------------------------------------

@pytest.mark.parametrize("method,path", [
    ("get", "/api/one-liner/bulk"),
    ("post", "/api/one-liner/bulk"),
    ("post", "/api/one-liner/bulk/undo"),
])
def test_팀원은_전체_자동조합을_쓸_수_없다(portal, rows, method, path):
    """한 번에 수백 줄을 바꾸는 일이라 **관리자만**이다.

    한 곳씩 누르는 [자동 조합으로 바꾸기] 는 그대로 누구나 쓴다 — 아래에서
    같이 지킨다.
    """
    call = getattr(portal["member"], method)
    r = call(path, json={"company_ids": [rows["manual"].id]}) if method == "post" else call(path)
    assert r.status_code == 403, "화면만 감추면 주소를 직접 치는 길이 남는다"


def test_한_곳씩_누르는_자동조합은_팀원도_그대로_쓴다(portal, db, rows):
    """일괄만 막는다 — 그 줄을 보고 있는 사람이 그 줄 하나를 바꾸는 것은 그대로다."""
    r = portal["member"].post(f"/api/companies/{rows['manual'].id}/one-liner")
    assert r.status_code == 200, r.text
    db.refresh(rows["manual"])
    assert rows["manual"].one_liner == "산업용 센서 제조 | 매출 8.9억"


def test_팀원_화면에는_단추가_아예_없다(portal):
    """라우터가 막는 것과 **같은 판정**을 화면이 읽는지."""
    member = portal["member"].get("/companies").text
    admin = portal["admin"].get("/companies").text
    assert 'id="ol-bulk-btn"' not in member
    assert 'id="ol-bulk-btn"' in admin


# --- ⑥ 브라우저 쪽 ------------------------------------------------------------

@pytest.mark.skipif(shutil.which("node") is None,
                    reason="node 미설치 — 브라우저 로직 테스트 생략")
def test_고르기와_되칠하기는_브라우저에_있으니_거기서_잰다():
    """전체 선택 · 고른 수 · 적용 뒤 표 되칠하기는 파이썬으로 잴 수 없는 자리다."""
    script = ROOT / "tests" / "js" / "one_liner_bulk_test.js"
    out = subprocess.run([shutil.which("node"), str(script)],
                         capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stdout + out.stderr
