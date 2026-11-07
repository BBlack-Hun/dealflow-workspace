"""IR 기업 현황에서 `컨설팅 상태` · `컨설팅 미팅일` 을 고친다(#166).

값은 IR 줄이 아니라 **이어진 투자컨설턴트 줄**에 산다(결정 3 — `consulting_view`). 그래서

  · 칸은 그 줄의 저장 주소(`PATCH /api/consulting/{id}`)를 들고 서고, IR 에는 아무것도 안 담는다.
  · 누가 고치나는 그 화면의 판정 하나다(`consulting.may_edit_row`) — 자기 줄 · 관리자 ·
    관리자가 맡겨 준 사람의 줄. 못 고치는 줄은 예전처럼 읽기만 하는 칸으로 선다.
  · 수정 로그는 그 길이 남기는 그대로다 — 남의 줄을 고치면 전→후가 남는다.
  · 이어진 줄이 둘 이상이면 어느 줄을 고칠지 칸이 말해 주지 못해 읽기만 한다.
  · 이어진 줄이 **없으면**(11/07 — "데이터가 들어가야지만 수정이 가능") 빈 칸도 열리고, 처음
    적는 순간 그 기업에 이어진 줄이 첫 탭에 선다 — 주인은 누른 사람, 수정 로그에 남는다
    (`routers/companies.save_consulting`). 값은 여전히 컨설턴트 줄 한 곳이다.

값은 전부 지어낸 것이다 — 저장소가 공개다.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def setup(db, users):
    from app.models import IrCompany
    from app.services import consulting_sheets as cs

    users["u1"].can_view_consulting = 1
    users["u2"].can_view_consulting = 1
    ir = IrCompany(name="샘플상태랩")
    db.add(ir)
    db.commit()
    return {"ir": ir, "sheets": cs.by_kind(db), "cs": cs}


def _link(db, setup, owner_id, **kw):
    from app.models import ConsultingCompany

    row = ConsultingCompany(user_id=owner_id, sheet=setup["sheets"][setup["cs"].STARTUP].label,
                            company_name="샘플상태랩", ir_company_id=setup["ir"].id, **kw)
    db.add(row)
    db.commit()
    return row


def _cells(html: str, ir_id: int) -> list:
    """IR 줄 하나의 `컨설팅 상태` · `컨설팅 미팅일` 칸(td 통째)."""
    row = re.search(rf'<tr data-id="{ir_id}".*?</tr>', html, re.S).group(0)
    tds = re.findall(r"<td\b[^>]*>.*?</td>", row, re.S)
    # `메모` 칸 바로 앞 두 칸이다(`companies.html`).
    at = next(i for i, td in enumerate(tds) if 'data-field="note"' in td)
    return tds[at - 2:at]


def test_meeting_day_는_날짜뿐인_값만_날짜_입력의_꼴로():
    from app.routers.companies import meeting_day

    assert meeting_day("2025.09.16") == "2025-09-16"
    assert meeting_day("2025. 9. 6.") == "2025-09-06"
    assert meeting_day("2025-09-16") == "2025-09-16"
    # 시각 · 말이 붙은 값은 그대로 — 날짜 입력에 넣으면 그 글자가 지워진다.
    assert meeting_day("9/16 PM2 (화상)") == "9/16 PM2 (화상)"
    assert meeting_day("2025. 09. 16 PM2") == "2025. 09. 16 PM2"
    assert meeting_day("2025.02.30") == "2025.02.30"        # 없는 날
    assert meeting_day(None) == ""


def test_자기_줄이_이어진_기업은_칸이_그_줄의_저장_주소를_들고_선다(logged_in, db, users, setup):
    row = _link(db, setup, users["u1"].id, management="관리 중 : 미팅 완",
                meeting_at="2025.09.16")
    html = logged_in.get("/companies").text
    status, meeting = _cells(html, setup["ir"].id)
    assert f'data-save-url="/api/consulting/{row.id}"' in status
    assert 'data-field="management"' in status and 'data-type="pick"' in status
    # 보기는 시트가 정해 둔 세 마디뿐이다(다른 줄의 글은 보기로 안 선다).
    assert 'data-choices="관리 중,드랍,백업팀 전환"' in status and "data-fixed-choices" in status
    assert "data-pick-head" in status
    # 칸에는 갈래, 편집창은 적힌 글 그대로에서 시작한다.
    assert 'data-value="관리 중 : 미팅 완"' in status and ">관리 중</td>" in status
    assert f'data-save-url="/api/consulting/{row.id}"' in meeting
    assert 'data-type="date"' in meeting and 'data-value="2025-09-16"' in meeting
    assert ">2025.09.16</td>" in meeting, "저장된 글자는 그대로 보인다"


def test_고친_값은_컨설턴트_줄에만_담기고_IR_줄은_그대로다(logged_in, db, users, setup):
    from app.models import ConsultingCompany, IrCompany

    row = _link(db, setup, users["u1"].id, management="관리 중 : 미팅 완",
                meeting_at="9/16 PM2")
    before = db.get(IrCompany, setup["ir"].id).updated_at
    r = logged_in.patch(f"/api/consulting/{row.id}", json={"management": "드랍 : 미팅 완"})
    assert r.status_code == 200, r.text
    # 화면이 칸을 다시 그릴 갈래 — 서버 한 곳(`consulting_status`)이 센다.
    assert r.json()["management_tag"] == "드랍"
    assert r.json()["values"] == {"management": "드랍 : 미팅 완"}
    r = logged_in.patch(f"/api/consulting/{row.id}", json={"meeting_at": "2025-10-01"})
    assert r.status_code == 200, r.text
    assert "management_tag" not in r.json(), "기업 관리를 안 고쳤는데 갈래가 실렸다"

    db.expire_all()
    got = db.get(ConsultingCompany, row.id)
    assert (got.management, got.meeting_at) == ("드랍 : 미팅 완", "2025-10-01")
    stamps = json.loads(got.field_stamps or "{}")
    assert {"management", "meeting_at"} <= set(stamps), "그 줄의 칸 날짜가 안 찍혔다"
    assert db.get(IrCompany, setup["ir"].id).updated_at == before, "IR 줄이 같이 고쳐졌다"
    status, meeting = _cells(logged_in.get("/companies").text, setup["ir"].id)
    assert ">드랍</td>" in status and ">2025-10-01</td>" in meeting


def test_남의_줄은_못_고치고_읽기만_한다(logged_in, db, users, setup):
    row = _link(db, setup, users["u2"].id, management="관리 중", meeting_at="2025.09.16")
    status, meeting = _cells(logged_in.get("/companies").text, setup["ir"].id)
    assert "data-save-url" not in status + meeting
    assert 'class="muted"' in status and ">관리 중</td>" in status
    assert "고칠 수 있는 계정만" in status
    # 저장 길도 그 화면의 판정 그대로 막는다(없는 번호와 같은 404).
    r = logged_in.patch(f"/api/consulting/{row.id}", json={"management": "드랍"})
    assert r.status_code == 404


def test_맡겨_준_사람의_줄은_고친다_그리고_수정_로그가_남는다(logged_in, db, users, setup):
    from app.models import ConsultingRowGrant, EditLog

    row = _link(db, setup, users["u2"].id, management="관리 중 : 미팅 완",
                meeting_at="2025.09.16")
    db.add(ConsultingRowGrant(user_id=users["u2"].id, editor_user_id=users["u1"].id))
    db.commit()
    status, _ = _cells(logged_in.get("/companies").text, setup["ir"].id)
    assert f'data-save-url="/api/consulting/{row.id}"' in status

    assert logged_in.patch(f"/api/consulting/{row.id}",
                           json={"management": "백업팀 전환 : 미팅 완"}).status_code == 200
    assert logged_in.patch(f"/api/consulting/{row.id}",
                           json={"meeting_at": "2025-10-01"}).status_code == 200
    logs = [x for x in db.query(EditLog).all()
            if x.table_name == "consulting_companies" and x.row_id == row.id]
    changes = [c for x in logs for c in json.loads(x.changes_json)]
    by_field = {c["field"]: c for c in changes}
    assert set(by_field) >= {"management", "meeting_at"}, changes
    # 전→후가 그대로 남는다 — 미팅일도 `바뀜` 이 아니라 값이다.
    dumped = json.dumps(changes, ensure_ascii=False)
    assert "관리 중 : 미팅 완" in dumped and "백업팀 전환 : 미팅 완" in dumped
    assert "2025.09.16" in dumped and "2025-10-01" in dumped
    assert all(x.actor_user_id == users["u1"].id for x in logs)
    assert all(x.target_user_id == users["u2"].id for x in logs)


def test_관리자는_누구_줄이든_고친다(logged_in, db, users, setup, u1_admin):
    row = _link(db, setup, users["u2"].id, management="", meeting_at="")
    status, meeting = _cells(logged_in.get("/companies").text, setup["ir"].id)
    assert f'data-save-url="/api/consulting/{row.id}"' in status
    assert 'title="눌러서 고릅니다"' in status and 'data-value=""' in meeting


def test_이어진_줄이_둘이면_읽기만_한다(logged_in, db, users, setup):
    _link(db, setup, users["u1"].id, management="관리 중", meeting_at="2025.09.16")
    _link(db, setup, users["u1"].id, management="드랍", meeting_at="2025.10.01")
    status, meeting = _cells(logged_in.get("/companies").text, setup["ir"].id)
    assert "data-save-url" not in status + meeting
    assert ">관리 중 · 드랍</td>" in status
    assert "2개에 이어져 있어" in status


def test_계약_탭_줄은_안_보이고_안_센다(logged_in, db, users, setup):
    """계약 탭의 같은 칸은 `계약여부` · `계약월` 이라 다른 물음이다 — 이어진 줄 수에도 안 든다."""
    from app.models import ConsultingCompany

    row = _link(db, setup, users["u1"].id, management="관리 중", meeting_at="2025.09.16")
    db.add(ConsultingCompany(user_id=users["u1"].id,
                             sheet=setup["sheets"][setup["cs"].CONTRACT].label,
                             company_name="샘플상태랩", management="무료", meeting_at="8",
                             ir_company_id=setup["ir"].id))
    db.commit()
    status, _ = _cells(logged_in.get("/companies").text, setup["ir"].id)
    assert f'data-save-url="/api/consulting/{row.id}"' in status


def test_이어진_줄이_있고_값이_비어도_칸이_열린다(logged_in, db, users, setup):
    """값이 빈 칸이라 못 고치는 것이 아니다 — 자기 줄이면 빈 칸도 그 줄의 저장 주소를 든다."""
    row = _link(db, setup, users["u1"].id, management="", meeting_at="")
    status, meeting = _cells(logged_in.get("/companies").text, setup["ir"].id)
    assert f'data-save-url="/api/consulting/{row.id}"' in status
    assert f'data-save-url="/api/consulting/{row.id}"' in meeting
    assert 'class="cell"' in status and 'class="cell"' in meeting
    assert status.endswith("></td>") and meeting.endswith("></td>")


def test_이어진_줄이_없는_기업은_빈_칸이_IR_쪽_주소를_들고_선다(logged_in, db, users, setup):
    html = logged_in.get("/companies").text
    status, meeting = _cells(html, setup["ir"].id)
    url = f'data-save-url="/api/companies/{setup["ir"].id}/consulting"'
    assert url in status and url in meeting
    assert 'class="cell"' in status and 'data-type="pick"' in status and 'data-value=""' in status
    assert 'class="cell"' in meeting and 'data-type="date"' in meeting and 'data-value=""' in meeting
    # 짚으면 어디에 줄이 생기는지 말한다 — 첫 탭(시트의 `메타`) 이름 그대로.
    first = setup["sheets"][setup["cs"].STARTUP].label
    assert f"「{first}」 탭에 이 기업 줄이 생기고" in status


def test_빈_칸에_처음_적으면_그_기업에_이어진_줄이_첫_탭에_선다(logged_in, db, users, setup):
    from app.models import ConsultingCompany, EditLog, IrCompany

    ir = db.get(IrCompany, setup["ir"].id)
    ir.region = "샘플시"
    db.commit()
    before = db.get(IrCompany, setup["ir"].id).updated_at
    url = f"/api/companies/{setup['ir'].id}/consulting"

    r = logged_in.patch(url, json={"management": "드랍"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["created"] is True and body["management_tag"] == "드랍"
    assert body["values"] == {"management": "드랍"}

    db.expire_all()
    rows = db.query(ConsultingCompany).all()
    assert len(rows) == 1, "줄이 안 섰거나 둘이 섰다"
    row = rows[0]
    assert row.id == body["id"]
    assert row.user_id == users["u1"].id, "주인은 누른 사람이다([기업 추가] 와 같다)"
    assert row.sheet == setup["sheets"][setup["cs"].STARTUP].label, "첫 탭에 서야 한다"
    assert row.ir_company_id == setup["ir"].id and not row.ir_link_auto
    assert row.company_name == "샘플상태랩" and row.management == "드랍"
    assert row.position == 1
    assert "management" in json.loads(row.field_stamps or "{}"), "칸 날짜가 안 찍혔다"
    # 이은 순간 잇는 칸의 빈칸은 IR 값으로 채워진다 — 다른 이어진 줄과 같다(`company_sync`).
    assert row.region == "샘플시"
    # IR 줄에는 아무것도 안 담는다.
    assert db.get(IrCompany, setup["ir"].id).updated_at == before, "IR 줄이 같이 고쳐졌다"

    # 자기 줄이라도 세운 일은 수정 로그에 남는다(`edit_log.always`). 새 줄의 로그는 번호
    # (`row_id`)가 아직 안 실리는 길이라(기존 동작) 기업 이름과 이은 IR 번호로 짚는다.
    logs = [x for x in db.query(EditLog).all() if x.table_name == "consulting_companies"]
    assert [(x.action, x.scope, x.actor_user_id, x.row_label) for x in logs] == [
        ("create", "mine", users["u1"].id, "샘플상태랩")], logs
    changes = {c["field"]: c.get("after") for c in json.loads(logs[0].changes_json)}
    assert changes.get("ir_company_id") == setup["ir"].id, changes
    assert changes.get("sheet") == row.sheet and changes.get("management") == "드랍", changes

    # 옆 칸을 이어서 적으면(화면이 아직 IR 쪽 주소를 들고 있어도) **같은 줄**에 담긴다.
    r = logged_in.patch(url, json={"meeting_at": "2026-12-01"})
    assert r.status_code == 200, r.text
    assert "created" not in r.json()
    db.expire_all()
    assert db.query(ConsultingCompany).count() == 1, "옆 칸을 적었더니 줄이 또 섰다"
    assert db.get(ConsultingCompany, row.id).meeting_at == "2026-12-01"

    # 다시 그리면 그 줄의 저장 길을 들고 선다.
    status, meeting = _cells(logged_in.get("/companies").text, setup["ir"].id)
    assert f'data-save-url="/api/consulting/{row.id}"' in status and ">드랍</td>" in status
    assert f'data-save-url="/api/consulting/{row.id}"' in meeting and ">2026-12-01</td>" in meeting


def test_빈_값으로는_줄을_세우지_않는다(logged_in, db, users, setup):
    from app.models import ConsultingCompany

    r = logged_in.patch(f"/api/companies/{setup['ir'].id}/consulting", json={"meeting_at": "  "})
    assert r.status_code == 200, r.text
    assert r.json()["id"] is None
    assert db.query(ConsultingCompany).count() == 0
    assert logged_in.patch(f"/api/companies/{setup['ir'].id}/consulting",
                           json={}).status_code == 400


def test_계약_탭에만_이어진_기업은_첫_탭에_새로_선다(logged_in, db, users, setup):
    """계약 탭 줄은 진행 기록이 아니다(다른 물음) — 그 줄을 건드리지 않고 첫 탭에 새로 선다."""
    from app.models import ConsultingCompany

    contract = ConsultingCompany(user_id=users["u2"].id,
                                 sheet=setup["sheets"][setup["cs"].CONTRACT].label,
                                 company_name="샘플상태랩", management="무료", meeting_at="8",
                                 ir_company_id=setup["ir"].id)
    db.add(contract)
    db.commit()
    status, _ = _cells(logged_in.get("/companies").text, setup["ir"].id)
    assert f'data-save-url="/api/companies/{setup["ir"].id}/consulting"' in status
    r = logged_in.patch(f"/api/companies/{setup['ir'].id}/consulting",
                        json={"management": "관리 중"})
    assert r.status_code == 200 and r.json()["created"] is True, r.text
    db.expire_all()
    got = db.get(ConsultingCompany, contract.id)
    assert (got.management, got.meeting_at) == ("무료", "8"), "계약 탭 줄이 고쳐졌다"
    assert db.query(ConsultingCompany).count() == 2


def test_IR_쪽_주소도_이어진_줄이_있으면_그_줄의_판정_그대로다(logged_in, db, users, setup):
    """창을 연 뒤 남이 줄을 이었으면 새로 안 세우고 그 줄의 저장 길로 간다 — 남의 줄은 404."""
    from app.models import ConsultingCompany

    row = _link(db, setup, users["u2"].id, management="관리 중")
    r = logged_in.patch(f"/api/companies/{setup['ir'].id}/consulting", json={"management": "드랍"})
    assert r.status_code == 404
    db.expire_all()
    assert db.query(ConsultingCompany).count() == 1
    assert db.get(ConsultingCompany, row.id).management == "관리 중"

    # 둘이면 어느 줄인지 몰라 막는다.
    _link(db, setup, users["u1"].id, management="드랍")
    r = logged_in.patch(f"/api/companies/{setup['ir'].id}/consulting", json={"management": "드랍"})
    assert r.status_code == 409 and "2개에 이어져" in r.json()["detail"]


def test_투자현황을_못_보는_계정은_IR_쪽_주소로도_못_세운다(logged_in, db, users, setup):
    from app.models import ConsultingCompany

    users["u1"].can_view_consulting = 0
    db.commit()
    r = logged_in.patch(f"/api/companies/{setup['ir'].id}/consulting", json={"management": "드랍"})
    assert r.status_code == 403
    assert db.query(ConsultingCompany).count() == 0
    assert logged_in.patch("/api/companies/99999/consulting",
                           json={"management": "드랍"}).status_code in (403, 404)


@pytest.mark.skipif(shutil.which("node") is None,
                    reason="node 미설치 — 브라우저 로직 테스트 생략")
def test_표에서_고르고_저장하는_브라우저_동작():
    """칸 → 저장 주소 · 보기 세 마디 · 머리만 바꾸기 · 안 고치면 그대로 · 저장 뒤 갈래로 다시 그리기.

    `tests/js/company_consulting_edit_test.js` 를 node 로 돌린다.
    """
    script = ROOT / "tests" / "js" / "company_consulting_edit_test.js"
    out = subprocess.run([shutil.which("node"), str(script)],
                         capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stdout + out.stderr
