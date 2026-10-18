"""업무 보고 › `매출예상리스트`(개선 과제 #46).

자동 칸은 값을 베껴 두지 않고 열 때마다 원본에서 읽는다(`services/forecast.py`).
여기서 못 박는 것:

1. 자동 칸이 원본에서 채워지고, 사람이 적은 값이 우선이다. 비우면 다시 자동,
   원본과 같은 값을 적으면 빈칸으로 둔다.
2. 같은 이름의 IR 기업이 여럿이면 후보를 띄우고 사람이 고른다. 기업명을 바꾸면
   연결을 풀고 다시 찾는다.
3. 심사역은 미팅(없으면 IR 요청) 상대 → 명단에 한 명뿐 → 후보 딱지 차례로 정한다.
4. 미팅은 같은 기업 + 같은 회사 상대만, 취소는 빼고, 가장 이른 날과 `외 N건`.
5. 남의 줄은 404, 관리자는 고칠 수 있다. 엑셀은 화면과 같은 범위 · 같은 칸.
6. IR 기업을 지우면 줄은 남고 연결만 끊긴다.

이름 · 회사 · 전화는 전부 지어낸 것이다(공개 저장소).
"""
from __future__ import annotations

import io

import pytest

from .conftest import DEMO_PASSWORD


@pytest.fixture()
def portal(db, users):
    from fastapi.testclient import TestClient

    from app.main import create_app
    from app.models import User
    from app.services import auth as auth_svc

    pw = auth_svc.hash_password(DEMO_PASSWORD)
    db.add_all([
        User(id=91, name="관리자시험", phone="01000000091", role="admin", password_hash=pw),
        User(id=92, name="컨설턴트시험", phone="01000000092", role="consultant",
             password_hash=pw),
    ])
    db.commit()
    app = create_app()

    def sign_in(phone):
        client = TestClient(app)
        client.post("/login", data={"phone": phone, "password": DEMO_PASSWORD})
        return client

    return {"u1": sign_in("01000000001"), "u2": sign_in("01000000002"),
            "admin": sign_in("01000000091"), "consultant": sign_in("01000000092")}


@pytest.fixture()
def company(db):
    from app.models import IrCompany

    row = IrCompany(name="샘플가나랩", contact_name="대표가", contact_phone="010-0000-1111",
                    pre_value="50", raise_target="10")
    db.add(row)
    db.commit()
    return row


def _vc(db, name, phone, firm="(주)가나벤처스", user_id=1):
    from app.models import VcContact

    row = VcContact(user_id=user_id, source_sheet="시험 명단", name=name, firm=firm,
                    phone=phone)
    db.add(row)
    db.commit()
    return row


def _meet(db, contact, company, day, kind="first", status="scheduled", user_id=1):
    from app.models import Meeting

    db.add(Meeting(user_id=user_id, contact_id=contact.id, company_id=company.id,
                   company_name=company.name, scheduled_at=day, kind=kind, status=status))
    db.commit()


def _add(client, name="샘플가나랩", firm="가나벤처스"):
    r = client.post("/api/forecast", json={"company_name": name, "firm": firm})
    assert r.status_code == 200, r.text
    return r.json()


def _cells(client, row_id, **body):
    r = client.patch(f"/api/forecast/{row_id}", json=body)
    assert r.status_code == 200, r.text
    return r.json()["cells"]


# --- 1. 자동 칸 · 우선순위 ----------------------------------------------------

def test_빈_칸은_원본에서_읽고_빨갛게_보인다(portal, db, company):
    _vc(db, "심사가", "010-0000-2222")
    row = _add(portal["u1"])
    cells = row["cells"]
    assert row["company"]["id"] == company.id, "후보가 하나면 바로 잇는다"
    assert cells["vc_name"] == {"text": "심사가", "value": "심사가", "auto": True}
    assert cells["vc_phone"]["text"] == "010-0000-2222"
    assert [cells[f]["text"] for f in ("ceo_name", "ceo_phone", "pre_value", "raise_target")] \
        == ["대표가", "010-0000-1111", "50", "10"]
    page = portal["u1"].get("/report/forecast").text
    assert 'class="cell fc-auto" data-field="ceo_name"' in page
    assert "비면 자동 — 스타트업DB — 대표자명" in page


def test_적은_값이_우선이고_비우면_자동_원본과_같으면_빈칸(portal, db, company):
    from app.models import RevenueForecast

    row = _add(portal["u1"])
    cells = _cells(portal["u1"], row["id"], ceo_name="다른대표")
    assert cells["ceo_name"] == {"text": "다른대표", "value": "다른대표", "auto": False}
    cells = _cells(portal["u1"], row["id"], ceo_name="")
    assert cells["ceo_name"]["auto"] and cells["ceo_name"]["text"] == "대표가"
    _cells(portal["u1"], row["id"], ceo_name="대표가")
    db.expire_all()
    assert db.get(RevenueForecast, row["id"]).ceo_name is None, "원본과 같으면 저장하지 않는다"


# --- 2. 기업 연결 ---------------------------------------------------------------

def test_같은_이름이_여럿이면_골라_잇고_이름을_바꾸면_다시_찾는다(portal, db, company):
    from app.models import IrCompany

    twin = IrCompany(name="샘플가나랩", contact_name="대표나")
    other = IrCompany(name="샘플다라소재", contact_name="대표다")
    db.add_all([twin, other])
    db.commit()
    row = _add(portal["u1"])
    assert row["company"] is None
    assert [c["id"] for c in row["company_candidates"]] == [company.id, twin.id]
    assert "이걸로" in portal["u1"].get("/report/forecast").text

    r = portal["u1"].post(f"/api/forecast/{row['id']}/company", json={"company_id": twin.id})
    assert r.json()["company"]["id"] == twin.id
    assert r.json()["cells"]["ceo_name"]["text"] == "대표나"

    cells = _cells(portal["u1"], row["id"], company_name="샘플다라소재")
    assert cells["ceo_name"]["text"] == "대표다", "이름을 바꾸면 풀고 다시 잇는다"
    _cells(portal["u1"], row["id"], company_name="샘플없는기업")
    assert "스타트업DB에 없음" in portal["u1"].get("/report/forecast").text


def test_자동완성_보기_같은_이름은_라운드_대표자로_가르고_투자사는_담당자_명단만(
        portal, db, company):
    from app.models import IrCompany

    db.add_all([IrCompany(name="샘플가나랩", series="Series A", contact_name="대표나"),
                IrCompany(name="샘플다라소재")])
    db.commit()
    _vc(db, "심사가", "010-0000-2222")
    _vc(db, "심사남", "010-0000-3333", firm="샘플남의벤처스", user_id=2)
    _add(portal["u1"])
    page = portal["u1"].get("/report/forecast").text
    assert 'list="fc-companies"' in page and 'data-list="fc-companies"' in page
    assert '<option value="샘플다라소재"></option>' in page, "이름이 하나면 이름만"
    assert '<option value="샘플가나랩" label="샘플가나랩 · 대표가">' in page
    assert '<option value="샘플가나랩" label="샘플가나랩 · Series A · 대표나">' in page
    assert 'data-list="fc-firms-1"' in page and '<option value="(주)가나벤처스">' in page
    assert "샘플남의벤처스" not in page, "남의 명단 회사명은 안 싣는다"

    # 스타트업 명단(투자사로 안 세는 명단) 줄은 후보에도, 심사역 자동 칸에도 안 뜬다.
    from app.models import SheetOwner, VcContact
    db.add_all([SheetOwner(label="시험 스타트업", user_id=1, layout="startup", is_hidden=1),
                VcContact(user_id=1, source_sheet="시험 스타트업", name="대표스",
                          firm="샘플스타트랩", phone="010-0000-5555")])
    db.commit()
    assert "샘플스타트랩" not in portal["u1"].get("/report/forecast").text
    assert _add(portal["u1"], firm="샘플스타트랩")["cells"]["vc_name"]["text"] == ""


# --- 3. 심사역 고르기 -------------------------------------------------------------

def test_심사역은_미팅_IR요청_명단_후보_차례로_정한다(portal, db, company):
    from app.models import IrRequest

    ga = _vc(db, "심사가", "010-0000-2222")
    na = _vc(db, "심사나", "010-0000-3333")
    _vc(db, "남의심사", "010-0000-4444", user_id=2)   # 남의 명단은 안 본다
    row = _add(portal["u1"])
    # 명단에 둘 — 정하지 않고 후보를 띄운다.
    assert row["cells"]["vc_name"]["text"] == ""
    assert [c["name"] for c in row["vc_candidates"]] == ["심사가", "심사나"]

    db.add(IrRequest(user_id=1, contact_id=ga.id, company_id=company.id,
                     company_name=company.name, requested_at="2026-10-01"))
    db.commit()
    assert _cells(portal["u1"], row["id"])["vc_name"]["text"] == "심사가", "IR 요청 상대"
    _meet(db, na, company, "2026-10-20")
    assert _cells(portal["u1"], row["id"])["vc_name"]["text"] == "심사나", "미팅이 먼저"

    # 사람이 고른 이름이면 전화번호는 그 사람 것.
    cells = _cells(portal["u1"], row["id"], vc_name="심사가")
    assert cells["vc_name"]["auto"] is False
    assert cells["vc_phone"] == {"text": "010-0000-2222", "value": "010-0000-2222",
                                 "auto": True}


# --- 4. 미팅 맞추기 --------------------------------------------------------------

def test_미팅은_같은_기업_같은_회사만_취소_빼고_외_N건(portal, db, company):
    from app.models import IrCompany, RevenueForecast

    ga = _vc(db, "심사가", "010-0000-2222")
    elsewhere = _vc(db, "심사라", "010-0000-5555", firm="라마파트너스")
    other_co = IrCompany(name="샘플다라소재")
    db.add(other_co)
    db.commit()
    _meet(db, ga, company, "2026-11-03")
    _meet(db, ga, company, "2026-11-10")
    _meet(db, ga, company, "2026-10-20", status="done")
    _meet(db, ga, company, "2026-10-28", kind="second", status="done")
    _meet(db, ga, company, "2026-10-01", status="canceled")
    _meet(db, elsewhere, company, "2026-10-05")
    _meet(db, ga, other_co, "2026-10-06")
    cells = _add(portal["u1"])["cells"]
    assert cells["meeting_plan"]["text"] == "2026-11-03 외 1건"
    assert "2026-10-20" not in cells["meeting_plan"]["text"], "완료된 미팅은 예정일에 안 잡힌다"
    assert cells["meeting1_done"]["text"] == "2026-10-20"
    assert cells["meeting2_done"]["text"] == "2026-10-28"

    row_id = db.query(RevenueForecast).one().id
    _cells(portal["u1"], row_id, meeting_plan="2026-11-03")
    db.expire_all()
    assert db.get(RevenueForecast, row_id).meeting_plan is None, "가장 이른 날과 같으면 빈칸"


# --- 5. 권한 · 엑셀 ---------------------------------------------------------------

def test_남의_줄은_404_관리자는_고치고_로그가_남는다(portal, db, company):
    from app.models import EditLog

    row = _add(portal["u1"])
    rid = row["id"]
    assert portal["u2"].patch(f"/api/forecast/{rid}", json={"ceo_share": "30%"}).status_code == 404
    assert portal["u2"].post(f"/api/forecast/{rid}/company",
                             json={"company_id": company.id}).status_code == 404
    assert portal["u2"].delete(f"/api/forecast/{rid}").status_code == 404
    assert f'data-id="{rid}"' not in portal["u2"].get("/report/forecast").text
    assert f'data-id="{rid}"' not in portal["admin"].get("/report/forecast").text
    assert f'data-id="{rid}"' in portal["admin"].get("/report/forecast?scope=team").text
    assert f'data-id="{rid}"' in portal["admin"].get("/report/forecast?member=1").text

    assert portal["admin"].patch(f"/api/forecast/{rid}",
                                 json={"ceo_share": "30%"}).status_code == 200
    assert db.query(EditLog).filter_by(table_name="revenue_forecasts").count() == 1
    assert portal["consultant"].get("/report/forecast", follow_redirects=False).status_code == 303
    assert portal["admin"].delete(f"/api/forecast/{rid}").status_code == 200


def test_엑셀은_화면과_같은_칸_같은_글자(portal, db, company):
    openpyxl = pytest.importorskip("openpyxl")
    from app.services import forecast as svc

    ga = _vc(db, "심사가", "010-0000-2222")
    _meet(db, ga, company, "2026-10-20")
    _meet(db, ga, company, "2026-11-03")
    _add(portal["u1"])
    _add(portal["u2"], name="샘플남의기업")
    r = portal["u1"].get("/api/export/forecast.xlsx")
    assert r.status_code == 200
    grid = [list(row) for row in openpyxl.load_workbook(io.BytesIO(r.content))
            .active.iter_rows(values_only=True)]
    assert grid[0] == [label for _f, label, _s in svc.COLUMNS]
    assert len(grid) == 2, "내 줄만"
    line = dict(zip(grid[0], grid[1]))
    assert line["기업명"] == "샘플가나랩" and line["심사역 성함"] == "심사가"
    assert line["투자사 미팅 예정일"] == "2026-10-20 외 1건"


# --- 6. 기업 삭제 ----------------------------------------------------------------

def test_IR_기업을_지우면_줄은_남고_연결만_끊긴다(portal, db, company):
    from app.models import RevenueForecast

    rid = _add(portal["u1"])["id"]
    plan = portal["admin"].get(f"/api/companies/{company.id}/delete-plan").json()
    assert plan["counts"]["forecasts"] == 1
    r = portal["admin"].post(f"/api/companies/{company.id}/force-delete",
                             json={"confirm_name": company.name})
    assert r.status_code == 200, r.text
    db.expire_all()
    row = db.get(RevenueForecast, rid)
    assert row is not None and row.ir_company_id is None
    assert portal["u1"].get("/report/forecast").status_code == 200
