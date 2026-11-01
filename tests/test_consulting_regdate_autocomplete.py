"""투자컨설턴트 — `등록일` 칸과 `기업명` IR 기업 후보(11/01 사용자 요청).

  1. `등록일` 은 `이메일` 바로 오른쪽(계약 탭은 `이메일` 이 없어 표시 칸 맨 뒤), 날짜만.
  2. IR 기업 후보 이름은 화면이 한 번에 싣는다(`ir_company_hint.js`) — 투자컨설턴트(역할)는 뺀다.
  3. 후보를 고르면 기업명이 그 이름 그대로 저장되고, 이름이 하나 맞는 IR 기업에 이어져
     **빈칸만** 채워진다(`company_sync` 의 자동 연결 · 채우기 규칙 그대로).

이름 · 번호는 전부 지어낸 것이다 — 저장소가 공개다.
"""
from __future__ import annotations

import json
import re
from urllib.parse import quote

import pytest

from .conftest import DEMO_PASSWORD


@pytest.fixture()
def allowed(client, db, users):
    users["u1"].can_view_consulting = 1
    db.commit()
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    return client


@pytest.fixture()
def sheets(db):
    from app.services import consulting_sheets as cs

    return {s.kind: s.label for s in cs.ensure(db)}


def _row(db, user_id, **kw):
    from app.models import ConsultingCompany

    row = ConsultingCompany(user_id=user_id, position=1, **kw)
    db.add(row)
    db.commit()
    return row


def _heads(html: str) -> list:
    head = re.search(r"<thead>(.*?)</thead>", html, re.S).group(1)
    return [re.sub(r"<[^>]+>", "", cell).strip()
            for attrs, cell in re.findall(r"<th\b([^>]*)>(.*?)</th>", head, re.S)
            if "ir-ro" not in attrs and "month-col" not in attrs]


# ── 1. 등록일 ───────────────────────────────────────────────────────────────

def test_등록일은_이메일_바로_오른쪽에_날짜만_선다(allowed, db, users, sheets):
    row = _row(db, users["u1"].id, sheet=sheets["startup"], company_name="샘플등록")
    row.created_at = "2026-10-05T14:30:12+09:00"
    db.commit()
    for kind in ("startup", "handover"):
        html = allowed.get("/consulting?sheet=" + quote(sheets[kind])).text
        heads = _heads(html)
        assert heads[heads.index("이메일") + 1] == "등록일", (kind, heads)
    html = allowed.get("/consulting?sheet=" + quote(sheets["startup"])).text
    assert '<td class="muted">2026-10-05</td>' in html
    assert "14:30" not in html.split("<tbody>", 1)[1]


def test_계약_탭은_이메일이_없어_표시_칸_맨_뒤에_선다(allowed, sheets):
    heads = _heads(allowed.get("/consulting?sheet=" + quote(sheets["contract"])).text)
    assert "이메일" not in heads
    assert heads[heads.index("계약금") + 1] == "등록일", heads


# ── 2. 후보 이름 ────────────────────────────────────────────────────────────

def test_IR_기업_후보_이름을_한_번에_싣는다(allowed, db):
    from app.models import IrCompany

    db.add_all([IrCompany(name="비에샘플"), IrCompany(name="비이샘플")])
    db.commit()
    html = allowed.get("/consulting").text
    carrier = re.search(r'id="opts-ir-company" hidden data-names=\'([^\']*)\'', html)
    assert carrier and json.loads(carrier.group(1)) == ["비에샘플", "비이샘플"]
    assert "js/ir_company_hint.js" in html
    # [기업 추가] 도 같은 후보를 받는 칸에 적는다(prompt 창에는 후보를 못 붙인다).
    assert 'id="cs-add-name"' in html


def test_투자컨설턴트에게는_IR_기업_목록을_안_싣는다(client, db):
    """IR 기업 현황이 닫힌 역할이다 — 이름 목록도 그 화면의 자료다."""
    from app.models import IrCompany, User
    from app.services import auth as auth_svc

    db.add_all([IrCompany(name="비에샘플"),
                User(name="컨설턴트샘플", phone="01000000093", role="consultant",
                     can_view_consulting=1,
                     password_hash=auth_svc.hash_password(DEMO_PASSWORD))])
    db.commit()
    client.post("/login", data={"phone": "01000000093", "password": DEMO_PASSWORD})
    html = client.get("/consulting").text
    assert "opts-ir-company" not in html
    assert "js/ir_company_hint.js" not in html


# ── 3. 고르면 잇고 빈칸만 채운다 ────────────────────────────────────────────

def test_고른_이름으로_고치면_IR에_잇고_빈칸만_채운다(allowed, db, users, sheets):
    from app.models import ConsultingCompany, IrCompany

    ir = IrCompany(name="비에샘플", contact_name="김샘플", contact_phone="010-0000-1111",
                   contact_email="ceo@example.com", region="서울")
    db.add(ir)
    db.commit()
    row = _row(db, users["u1"].id, sheet=sheets["startup"], company_name="비에",
               phone="010-0000-2222")
    assert row.ir_company_id is None          # `비에` 로는 안 이어진다

    r = allowed.patch(f"/api/consulting/{row.id}", json={"company_name": "비에샘플"})
    assert r.status_code == 200, r.text
    linked = r.json()["linked"]
    db.expire_all()
    row = db.get(ConsultingCompany, row.id)
    assert row.company_name == "비에샘플"
    assert (row.ir_company_id, row.ir_link_auto) == (ir.id, 1)
    # 빈칸만 채운다 — 연락처는 줄에 있던 값 그대로(다르면 `/ir-link` 의 `값 다름`).
    assert (row.ceo_name, row.email, row.region) == ("김샘플", "ceo@example.com", "서울")
    assert row.phone == "010-0000-2222"
    # 화면이 그 자리에서 적을 값.
    assert linked["ir_name"] == "비에샘플"
    assert linked["fields"]["ceo_name"] == "김샘플"
    assert linked["fields"]["phone"] == "010-0000-2222"


def test_이름이_둘_맞거나_사람이_고른_연결이면_안_바꾼다(allowed, db, users, sheets):
    from app.models import ConsultingCompany, IrCompany

    twin1, twin2, mine = (IrCompany(name="비티샘플"), IrCompany(name="(주)비티샘플"),
                          IrCompany(name="비이샘플"))
    db.add_all([twin1, twin2, mine])
    db.commit()
    loose = _row(db, users["u1"].id, sheet=sheets["startup"], company_name="임시")
    picked = _row(db, users["u1"].id, sheet=sheets["startup"], company_name="비이샘플")
    picked.ir_link_auto = 0                    # 사람이 `/ir-link` 에서 고른 연결
    db.commit()

    r = allowed.patch(f"/api/consulting/{loose.id}", json={"company_name": "비티샘플"})
    assert r.status_code == 200 and "linked" not in r.json()
    r = allowed.patch(f"/api/consulting/{picked.id}", json={"company_name": "비티샘플"})
    assert r.status_code == 200 and "linked" not in r.json()
    db.expire_all()
    assert db.get(ConsultingCompany, loose.id).ir_company_id is None
    assert db.get(ConsultingCompany, picked.id).ir_company_id == mine.id


def test_계약일_보수율만_고치면_다시_잇지_않는다(db, users, sheets):
    """`기업명 / 무료 / 3%` 의 뒤만 바뀐 것은 이름을 고친 것이 아니다(`_renamed`)."""
    from app.models import ConsultingCompany, IrCompany

    ir = IrCompany(name="비에샘플")
    db.add(ir)
    db.commit()
    row = _row(db, users["u1"].id, sheet=sheets["startup"], company_name="비에샘플 / 무료")
    assert row.ir_company_id == ir.id
    row.ir_company_id = None                   # 사람이 연결을 풀었다
    db.commit()
    row.company_name = "비에샘플 / 유료 / 3%"
    db.commit()
    db.expire_all()
    assert db.get(ConsultingCompany, row.id).ir_company_id is None


def test_화면_코드를_그대로_돌려_본다():
    """두 글자 · 고르기 · 채운 칸 적기 · [기업 추가] 칸은 `tests/js/consulting_company_hint_test.js`
    가 consulting.js 와 ir_company_hint.js 를 실제로 돌려 본다."""
    import shutil
    import subprocess
    from pathlib import Path

    node = shutil.which("node")
    if not node:
        pytest.skip("node 미설치 — 브라우저 로직 테스트 생략")
    js = Path(__file__).resolve().parent / "js" / "consulting_company_hint_test.js"
    r = subprocess.run([node, str(js)], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr
