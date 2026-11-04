"""투자컨설턴트 — `기업명` 가로 고정(#153) · 계약 넷 `등록일` 오른쪽(#154) · `메모` 이름(#154).

11/04 팀원 요청:
  #153 "컬럼 기업명은 고정이 되고 우측으로 스크롤 가면서 볼수 있게"
  #154 "계약년월, 계약여부, 계약서수신여부, 성공보수률 등록일 컬럼 오른쪽에 쪼르륵 넣어
        주세요. 소개매모 -> 단어 메모로 변경"

지키는 것:
  1. 모든 탭에서 고르는 칸(있으면) · `NO` · `기업명` 이 IR 기업 현황과 같은 CSS 로 고정되고,
     `--stick-*` 자리가 앞 칸 폭의 합과 맞는다(어긋나면 글자가 겹친다).
  2. 메타 탭은 `등록일` 바로 오른쪽에 계약년월 → 계약여부 → 계약서 수신 여부 → 성공보수율.
     옮긴 두 칸은 옛 자리(`견적서 첨부 여부` 뒤)에 다시 안 선다. 다른 두 탭은 그대로다.
  3. 계약년월은 `YYYY-MM` 으로 맞춰 저장되고(못 읽으면 400), 맞춘 값이 응답에 실린다.
  4. 이어진 메타 줄의 성공보수율 · 계약년월은 IR 과 따라 고친다(경영본부 줄은 안 잇는다).
  5. `소개 메모` → `메모` — 화면 · 엑셀 · 추가 칸 자리 이름이 함께 바뀐다.

이름 · 번호는 전부 지어낸 것이다 — 저장소가 공개다.
"""
from __future__ import annotations

import io
import re
from urllib.parse import quote

import pytest

from .conftest import DEMO_PASSWORD

LIST = "샘플 스타트업 명단"
CONTRACT_FOUR = ["계약년월", "계약여부", "계약서 수신 여부", "성공보수율"]
CONTRACT_FIELDS = ["contract_ym", "contract_done", "contract_received", "success_fee"]


@pytest.fixture()
def tabs(db):
    from app.services import consulting_sheets as cs

    return {s.kind: s.label for s in cs.ensure(db)}


@pytest.fixture()
def member(client, db, users):
    users["u1"].can_view_consulting = 1
    db.commit()
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    return client


@pytest.fixture()
def admin_picking(client, db, users):
    """관리자 화면 — `담당자` 칸 + [스타트업 명단으로 보내기] 고르는 칸이 다 서는 자리."""
    from app.models import SheetOwner

    users["u1"].role = "admin"
    users["u1"].can_view_consulting = 1
    db.add(SheetOwner(label=LIST, user_id=users["u1"].id, layout="startup", is_hidden=1))
    db.commit()
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    return client


def _row(db, users, sheet, **kw):
    from app.models import ConsultingCompany

    row = ConsultingCompany(user_id=users["u1"].id, sheet=sheet, position=1, **kw)
    db.add(row)
    db.commit()
    return row


def _open(client, sheet):
    resp = client.get("/consulting?sheet=" + quote(sheet))
    assert resp.status_code == 200, resp.text
    return resp.text


def _head_cells(html):
    head = re.search(r"<thead>(.*?)</thead>", html, re.S).group(1)
    return [(attrs, " ".join(re.sub(r"<[^>]+>", " ", re.sub(r"<form\b.*?</form>", " ",
                                                             body, flags=re.S)).split()))
            for attrs, body in re.findall(r"<th\b([^>]*)>(.*?)</th>", head, re.S)]


def _heads(html):
    return [label for attrs, label in _head_cells(html)
            if "ir-ro" not in attrs and "month-col" not in attrs]


def _first_row(html):
    body = html.split("<tbody>", 1)[1]
    return re.search(r"<tr data-id=.*?</tr>", body, re.S).group(0)


def _fields(html):
    return re.findall(r'data-field="([^"]+)"', html.split("<tbody>", 1)[1])


# ── 1. 기업명 가로 고정(#153) ────────────────────────────────────────────────

def _check_sticky(html, lead):
    table = re.search(r'<table class="grid-table sheet-table" id="cs-table"[^>]*>', html).group(0)
    assert f"--stick-a:{lead}px; --stick-b:{lead + 44}px" in table, table
    cells = _head_cells(html)
    stuck = [(attrs, label) for attrs, label in cells if re.search(r'class="[^"]*\bstick\b', attrs)]
    want = (["stick-lead"] if lead else []) + ["stick-a", "stick-b"]
    assert [next(k for k in ("stick-lead", "stick-a", "stick-b") if k in a)
            for a, _l in stuck] == want, stuck
    assert stuck[-1][1] == "기업명" and stuck[-2][1] == "NO", stuck
    # `--stick-b` 셈과 머리글 폭이 같은 값에서 나온다(어긋나면 반 칸씩 겹친다).
    assert "width:44px" in stuck[-2][0], stuck[-2]
    if lead:
        assert f"width:{lead}px" in stuck[0][0], stuck[0]
    # 몸통도 같은 칸이 같은 표시를 단다 — 머리글만 고정되면 줄이 어긋나 밀린다.
    row = _first_row(html)
    tds = re.findall(r'<td class="([^"]*)"', row)
    body_stuck = [c for c in tds if re.search(r"\bstick\b", c)]
    assert len(body_stuck) == len(stuck), (body_stuck, stuck)
    assert "stick-b" in body_stuck[-1] and "strong" in body_stuck[-1], body_stuck
    assert re.search(r'<td class="cell strong stick stick-b" data-field="company_name"', row)


def test_세_탭_모두_NO와_기업명이_고정된다(member, db, users, tabs):
    for kind in ("startup", "handover", "contract"):
        _row(db, users, tabs[kind], company_name=f"샘플{kind}")
        _check_sticky(_open(member, tabs[kind]), lead=0)


def test_고르는_칸이_서면_그_폭만큼_자리가_밀린다(admin_picking, db, users, tabs):
    _row(db, users, tabs["startup"], company_name="샘플고정")
    html = _open(admin_picking, tabs["startup"])
    assert 'id="cs-startup-bar"' in html, "고르는 칸이 서는 무대가 아닙니다"
    assert ">담당자</th>" in html
    _check_sticky(html, lead=46)
    # `담당자` 는 `NO` 와 `기업명` 사이에 서지만 고정하지 않는다.
    owner = re.search(r'<th([^>]*)>담당자</th>', html).group(1)
    assert "stick" not in owner
    assert 'class="owner-cell muted"' in _first_row(html)


def test_고정_칸_CSS는_공용_규칙_그대로다():
    """새 규칙을 만들지 않았다 — `.table-wrap.wide` 의 `td.stick` · `.stick-*` 를 쓴다."""
    from pathlib import Path

    css = (Path(__file__).resolve().parents[1] / "app" / "static" / "css" / "app.css"
           ).read_text("utf-8")
    assert re.search(r"\.table-wrap\.wide td\.stick \{[^}]*position: sticky", css)
    html = (Path(__file__).resolve().parents[1] / "app" / "templates" / "consulting.html"
            ).read_text("utf-8")
    assert '<div class="table-wrap wide">' in html
    # 고정된 기업명도 저장 색을 받는다(고정 칸 바탕이 `td.cell.saving` 을 이긴다).
    for state in ("saving", "saved", "save-failed"):
        assert f"#cs-table td.stick.{state} {{" in css, state


# ── 2. 계약 넷은 `등록일` 오른쪽(#154) ──────────────────────────────────────

def test_메타_탭은_등록일_바로_오른쪽에_계약_넷이_선다(member, db, users, tabs):
    _row(db, users, tabs["startup"], company_name="샘플계약", contract_ym="2026-10",
         contract_done="유료계약완료", contract_received="O", success_fee="3%")
    html = _open(member, tabs["startup"])
    heads = _heads(html)
    at = heads.index("등록일")
    assert heads[at - 1] == "이메일"
    assert heads[at + 1:at + 5] == CONTRACT_FOUR, heads
    # 옛 자리에서는 빠졌다 — `견적서 첨부 여부` 바로 뒤는 `카톡 연결 여부`.
    assert heads.count("계약여부") == 1 and heads.count("계약서 수신 여부") == 1, heads
    assert heads[heads.index("견적서 첨부 여부") + 1] == "카톡 연결 여부", heads
    # 몸통 차례가 머리글과 같다 — `등록일`(편집 칸 아님) 바로 앞이 `email`.
    fields = _fields(html)
    at = fields.index("email")
    assert fields[at + 1:at + 5] == CONTRACT_FIELDS, fields
    assert fields.count("contract_done") == 1 and fields.count("contract_received") == 1
    row = _first_row(html)
    for text in ("2026-10", "유료계약완료", "3%"):
        assert f">{text}</td>" in row, text
    # 등록일 → 계약 넷 → 읽기 전용 IR 칸 차례.
    cells = _head_cells(html)
    labels = [label for _a, label in cells]
    first_ir = next(i for i, (a, _l) in enumerate(cells) if "ir-ro" in a)
    assert labels[first_ir - 1] == "성공보수율", labels


def test_머리글과_몸통_칸_수와_빈_표_안내가_맞다(admin_picking, db, users, tabs):
    html = _open(admin_picking, tabs["startup"])
    total = len(_head_cells(html))
    m = re.search(r'colspan="(\d+)"', html)
    assert m and int(m.group(1)) == total, (m and m.group(1), total)
    _row(db, users, tabs["startup"], company_name="샘플칸수")
    html = _open(admin_picking, tabs["startup"])
    assert len(re.findall(r"<td\b", _first_row(html))) == total


def test_다른_두_탭은_그대로다(member, db, users, tabs):
    _row(db, users, tabs["handover"], company_name="샘플경영", success_fee="2%",
         contract_ym="2026-01")
    html = _open(member, tabs["handover"])
    heads = _heads(html)
    for label in ("계약년월", "성공보수율", "계약서 수신 여부"):
        assert label not in heads, label
    assert "contract_ym" not in html and 'data-field="success_fee"' not in html
    # 계약 탭은 원래 `기업명` 오른쪽에 계약 칸이 모여 있다 — 차례 그대로, `계약년월` 은 없다.
    _row(db, users, tabs["contract"], company_name="샘플계약탭")
    heads = _heads(_open(member, tabs["contract"]))
    at = heads.index("기업명")
    assert heads[at + 1:at + 7] == ["계약월", "계약여부", "계약서 수신 여부", "성공보수율",
                                    "계약금", "등록일"], heads
    assert "계약년월" not in heads


# ── 3. 저장 ──────────────────────────────────────────────────────────────────

def test_계약년월은_YYYY_MM으로_맞춰_저장되고_응답에_실린다(member, db, users, tabs):
    from app.models import ConsultingCompany

    row = _row(db, users, tabs["startup"], company_name="샘플년월")
    r = member.patch(f"/api/consulting/{row.id}", json={"contract_ym": "2026.3"})
    assert r.status_code == 200, r.text
    assert r.json()["values"] == {"contract_ym": "2026-03"}
    db.expire_all()
    assert db.get(ConsultingCompany, row.id).contract_ym == "2026-03"

    r = member.patch(f"/api/consulting/{row.id}", json={"contract_ym": "다음 달"})
    assert r.status_code == 400 and "YYYY-MM" in r.json()["detail"]
    db.expire_all()
    assert db.get(ConsultingCompany, row.id).contract_ym == "2026-03"

    r = member.patch(f"/api/consulting/{row.id}", json={"contract_ym": ""})
    assert r.status_code == 200 and r.json()["values"] == {"contract_ym": ""}
    db.expire_all()
    assert not db.get(ConsultingCompany, row.id).contract_ym


def test_성공보수율은_메타_줄에서도_고쳐지고_검색에_든다(member, db, users, tabs):
    row = _row(db, users, tabs["startup"], company_name="샘플보수")
    r = member.patch(f"/api/consulting/{row.id}",
                     json={"success_fee": " 3.5% ", "contract_ym": "2026-11"})
    assert r.status_code == 200, r.text
    assert r.json()["values"] == {"success_fee": "3.5%", "contract_ym": "2026-11"}
    html = _open(member, tabs["startup"])
    assert '<td class="cell" data-field="success_fee">3.5%</td>' in html
    tr = re.search(r'<tr data-id="%d"[^>]*>' % row.id, html, re.S).group(0)
    search = re.search(r'data-search="([^"]*)"', tr).group(1)
    assert "3.5%" in search and "2026-11" in search


# ── 4. IR 과 따라 고치기 ─────────────────────────────────────────────────────

def test_이어진_메타_줄의_성공보수율_계약년월은_IR과_따라_고친다(member, db, users, tabs):
    from app.models import IrCompany

    ir = IrCompany(name="샘플잇기")
    db.add(ir)
    db.commit()
    meta = _row(db, users, tabs["startup"], company_name="샘플잇기")
    hand = _row(db, users, tabs["handover"], company_name="샘플잇기")
    db.expire_all()
    meta, hand, ir = (db.get(type(x), x.id) for x in (meta, hand, ir))
    assert meta.ir_company_id == ir.id and hand.ir_company_id == ir.id

    r = member.patch(f"/api/consulting/{meta.id}",
                     json={"success_fee": "3%", "contract_ym": "2026-10"})
    assert r.status_code == 200, r.text
    db.expire_all()
    ir, hand = db.get(IrCompany, ir.id), db.get(type(hand), hand.id)
    assert (ir.success_fee, ir.contract_ym) == ("3%", "2026-10")
    # 경영본부 줄에는 이 칸이 안 선다 — 따라 적지 않는다.
    assert (hand.success_fee, hand.contract_ym) == (None, None)

    member.post("/logout")
    users["u1"].role = "admin"
    db.commit()
    member.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    r = member.patch(f"/api/companies/{ir.id}", json={"success_fee": "4%",
                                                       "contract_ym": "2026-12"})
    assert r.status_code == 200, r.text
    db.expire_all()
    meta = db.get(type(meta), meta.id)
    assert (meta.success_fee, meta.contract_ym) == ("4%", "2026-12")


def test_따라_고치는_자리는_메타_탭만이다(db, users, tabs):
    from app.services import company_sync

    kinds = company_sync.sheet_kinds(db)
    meta = _row(db, users, tabs["startup"], company_name="샘플자리1")
    hand = _row(db, users, tabs["handover"], company_name="샘플자리2")
    con = _row(db, users, tabs["contract"], company_name="샘플자리3")
    assert company_sync.slot(meta, "success_fee", kinds) == "success_fee"
    assert company_sync.slot(meta, "contract_ym", kinds) == "contract_ym"
    assert company_sync.slot(hand, "success_fee", kinds) is None
    assert company_sync.slot(hand, "contract_ym", kinds) is None
    # 계약 탭은 성공보수율만(그 탭의 `계약월` 은 `meeting_at` 글이라 안 잇는다).
    assert company_sync.slot(con, "success_fee", kinds) == "success_fee"
    assert company_sync.slot(con, "contract_ym", kinds) is None


# ── 5. `소개 메모` → `메모` ──────────────────────────────────────────────────

def test_소개_메모는_메모로_불린다(member, db, users, tabs):
    from app.routers import consulting

    _row(db, users, tabs["startup"], company_name="샘플메모", deal_pitch="메모 글")
    html = _open(member, tabs["startup"])
    heads = _heads(html)
    assert "메모" in heads and "소개 메모" not in html
    assert heads[heads.index("기업 내용") + 1] == "메모", heads
    assert dict((f, label) for label, f in consulting.STARTUP_COLUMNS)["deal_pitch"] == "메모"
    assert consulting.STARTUP_EXPORT_HEADERS[0] == "메모"


def test_엑셀은_메모_이름과_맨_끝_계약년월을_싣는다(member, db, users, tabs):
    from openpyxl import load_workbook

    _row(db, users, tabs["startup"], company_name="샘플엑셀", deal_pitch="메모 글",
         contract_ym="2026-09")
    resp = member.get("/api/export/consulting.xlsx")
    assert resp.status_code == 200
    ws = load_workbook(io.BytesIO(resp.content)).active
    head = [c.value for c in ws[1]]
    assert "소개 메모" not in head and "메모" in head
    assert head[-1] == "계약년월", head
    row = [c.value for c in ws[2]]
    assert row[head.index("메모")] == "메모 글"
    assert row[-1] == "2026-09"


def test_추가_칸_자리_이름도_따라간다():
    from types import SimpleNamespace

    from app.services import custom_columns as svc

    labels = svc.anchor_groups("consulting")["스타트업"]
    assert "메모" in labels and "소개 메모" not in labels
    for label in CONTRACT_FOUR:
        assert label in labels, label
    # 옛 이름(`소개 메모` · 그 전 `딜 소개문구`) 뒤에 골라 둔 칸은 `메모` 뒤에 선다.
    for old in ("소개 메모", "딜 소개문구"):
        assert svc.anchor_of(SimpleNamespace(target="consulting", after_key=old)) == "메모"


def test_표는_서버가_맞춘_계약년월로_칸을_다시_적는다():
    """`tests/js/consulting_contract_ym_test.js` 가 consulting.js 를 실제로 돌린다 —
    `2026.3` 을 치면 응답의 `values`(`2026-03`)로 칸이 바뀌는지, 막히면 옛 값으로 돌아가는지.
    로컬에서는 `node tests/js/consulting_contract_ym_test.js` 로도 돈다.
    """
    import shutil
    import subprocess
    from pathlib import Path

    node = shutil.which("node")
    if not node:
        pytest.skip("node 미설치 — 브라우저 로직 테스트 생략")
    js = Path(__file__).resolve().parent / "js" / "consulting_contract_ym_test.js"
    r = subprocess.run([node, str(js)], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr
