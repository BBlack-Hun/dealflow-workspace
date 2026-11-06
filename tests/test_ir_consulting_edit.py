"""IR 기업 현황에서 `컨설팅 상태` · `컨설팅 미팅일` 을 고친다(#166).

값은 IR 줄이 아니라 **이어진 투자컨설턴트 줄**에 산다(결정 3 — `consulting_view`). 그래서

  · 칸은 그 줄의 저장 주소(`PATCH /api/consulting/{id}`)를 들고 서고, IR 에는 아무것도 안 담는다.
  · 누가 고치나는 그 화면의 판정 하나다(`consulting.may_edit_row`) — 자기 줄 · 관리자 ·
    관리자가 맡겨 준 사람의 줄. 못 고치는 줄은 예전처럼 읽기만 하는 칸으로 선다.
  · 수정 로그는 그 길이 남기는 그대로다 — 남의 줄을 고치면 전→후가 남는다.
  · 이어진 줄이 둘 이상이면 어느 줄을 고칠지 칸이 말해 주지 못해 읽기만 한다.

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


def test_이어진_줄이_없으면_고칠_값이_없다(logged_in, db, users, setup):
    html = logged_in.get("/companies").text
    status, meeting = _cells(html, setup["ir"].id)
    assert "data-save-url" not in status + meeting
    assert "이어진 투자컨설턴트 줄이 없습니다" in status


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
