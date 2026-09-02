"""투자컨설턴트 → `관리 스타트업` 탭의 `딜 소개문구` 칸.

투자사에 이 기업을 어떻게 소개할지 적어 두는 자리다. 지금까지는 바로 옆
`기업 관리` 에 같이 적혀 있었는데, 그 칸은 **지금 어떻게 되고 있는가**를 적고
그 값으로 칩·KPI 를 세는 자리라 성격이 다르다.

여기서 막는 것은 다섯이다.

  1. **조용히 안 저장되는 것.** 스키마·저장·되읽기·화면 넷 중 하나만 빠져도
     화면은 멀쩡하고 오류도 안 나는데 고친 글이 사라진다(라우터의 `CompanyIn`
     에 이름을 안 적으면 pydantic 이 모르는 칸을 그냥 버린다).
  2. **줄바꿈이 사라지는 것.** 메모처럼 쓰는 칸이라 문단이 들어온다.
  3. 필터·칩·KPI·갈래 판정에 **새어 들어가는 것**.
  4. 다른 두 탭에 칸이 **같이 서는 것**(값도 안 싣는다).
  5. 마이그레이션이 이미 들어 있는 줄에 값을 **지어 넣는 것**.

이름·기업명은 전부 지어낸 값이다 — 저장소가 공개다.
"""
from __future__ import annotations

import pathlib
import re

import pytest

from .conftest import DEMO_PASSWORD

STARTUP = "스타트업"
HANDOVER = "경영본부 전달 기업"
CONTRACT = "월간 계약 업무현황표"

# 실제로 들어올 법한 여러 줄 문구. **줄바꿈이 살아남는지**를 이 값으로 본다.
PITCH = "스마트팜 관제 SaaS.\n국내 3개 농장 파일럿 중.\n시리즈A 30억 목표."


@pytest.fixture()
def allowed(client, db, users):
    users["u1"].can_view_consulting = 1
    db.commit()
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    return client


def _row(db, user_id, **kw):
    from app.models import ConsultingCompany

    row = ConsultingCompany(user_id=user_id, **kw)
    db.add(row)
    db.commit()
    return row


def _open(client, sheet):
    from urllib.parse import quote

    return client.get(f"/consulting?sheet={quote(sheet)}").text


def _heads(html: str) -> list:
    """그려진 표의 머리글 이름들. **정적 글자가 아니라 그려진 화면**을 본다."""
    m = re.search(r"<thead>(.*?)</thead>", html, re.S)
    assert m, "표 머리글을 찾지 못했습니다"
    out = []
    for cell in re.findall(r"<th\b[^>]*>(.*?)</th>", m.group(1), re.S):
        cell = re.sub(r"<form\b.*?</form>", " ", cell, flags=re.S)   # 월 열의 [✕]
        out.append(" ".join(re.sub(r"<[^>]+>", " ", cell).split()))
    return out


# --- 1. 눌러 고치면 정말 저장되는가 ------------------------------------------

def test_딜_소개문구는_고쳐지고_다시_읽힌다(allowed, db, users):
    """스키마·저장·되읽기·화면 넷 중 하나가 빠지면 **조용히** 안 저장된다.

    라우터의 `CompanyIn` 에 이름을 안 적으면 pydantic 이 모르는 칸을 그냥
    버린다 — 오류도 안 나고, 고친 사람은 저장된 줄 안다. 이 저장소가 실제로
    당한 적이 있는 부류라 네 자리를 다 짚는다.
    """
    from app.models import ConsultingCompany

    row = _row(db, users["u1"].id, sheet=STARTUP, position=1, company_name="샘플가")
    assert allowed.patch(f"/api/consulting/{row.id}",
                         json={"deal_pitch": "스마트팜 관제 SaaS"}).status_code == 200
    db.expire_all()
    assert db.get(ConsultingCompany, row.id).deal_pitch == "스마트팜 관제 SaaS"
    assert allowed.get(f"/api/consulting/{row.id}").json()["deal_pitch"] \
        == "스마트팜 관제 SaaS"
    assert ('<td class="cell multi" data-field="deal_pitch">스마트팜 관제 SaaS</td>'
            in _open(allowed, STARTUP))


def test_줄바꿈이_살아남는다(allowed, db, users):
    """메모처럼 쓰는 칸이라 문단이 들어온다.

    `_assign` 은 앞뒤 공백만 뗀다 — 가운데 줄바꿈까지 지우면 문단이 한 줄로
    뭉개져 무엇이 어디서 끝나는지 알 수 없게 된다. 화면에서도 그대로 보여야
    하므로(`td.cell { white-space: pre-wrap }`) 그린 HTML 에 줄바꿈이 살아
    있는지까지 본다.
    """
    from app.models import ConsultingCompany

    row = _row(db, users["u1"].id, sheet=STARTUP, position=1, company_name="샘플나")
    # 앞뒤 공백은 떼고, 가운데 줄바꿈은 남긴다.
    allowed.patch(f"/api/consulting/{row.id}", json={"deal_pitch": f"  {PITCH}  "})
    db.expire_all()
    saved = db.get(ConsultingCompany, row.id).deal_pitch
    assert saved == PITCH, repr(saved)
    assert saved.count("\n") == 2

    body = _open(allowed, STARTUP)
    cell = re.search(r'<td class="cell multi" data-field="deal_pitch">(.*?)</td>',
                     body, re.S)
    assert cell and cell.group(1) == PITCH, repr(cell and cell.group(1))
    # 화면이 줄바꿈을 접지 않고 그대로 그리는가 — 이 칸이 기대는 규칙이다.
    css = pathlib.Path("app/static/css/app.css").read_text(encoding="utf-8")
    assert re.search(r"td\.cell\s*\{[^}]*white-space:\s*pre-wrap", css), \
        "줄바꿈이 화면에서 한 줄로 뭉개집니다"


def test_긴_글_칸은_이_표가_쓰는_표시를_단다():
    """`multi` 여야 누를 때 textarea 가 열린다 — 한 줄짜리 입력이면 엔터가
    저장이 되어 **줄을 나눌 수가 없다.**

    다른 화면의 긴 글 칸은 `data-type="long"` 인데, 그것은 공통 편집기
    `inline_edit.js` 의 표시다. 이 표는 그 편집기를 안 쓰므로(자기 `startEdit`
    이 따로 있다) 그 표시를 달면 아무 일도 일어나지 않는다 — 바로 위
    `기업 관리` 와 같은 `multi` 를 쓴다.
    """
    html = pathlib.Path("app/templates/consulting.html").read_text(encoding="utf-8")
    assert '<td class="cell multi" data-field="deal_pitch">' in html
    assert 'data-field="deal_pitch" data-type=' not in html
    js = pathlib.Path("app/static/js/consulting.js").read_text(encoding="utf-8")
    assert 'classList.contains("multi")' in js, \
        "이 표의 편집기가 여러 줄 칸을 알아보는 자리가 사라졌습니다"


# --- 2. 필터·검색·엑셀 -------------------------------------------------------

def test_필터에는_안_세운다(allowed, db, users):
    """값이 자유 문장이라 **고를 것이 모이지 않는다.**

    32줄이면 32가지가 서서 목록이 그냥 자료를 한 번 더 적은 것이 된다 —
    같은 표의 `미팅일`(`9/16 PM2 (화상미팅)`)을 안 거는 것과 같은 이유고,
    투자사 딜공유 칸도 "값이 130가지라 필터로도 고를 것이 없다"고 적혀 있다
    (`services/contact_columns.py`).

    세우지 않았으므로 **행에도 값을 안 싣는다.** 실어 두면 아무 머리글도 안
    보는 죽은 속성이 된다(`tests/test_filter_columns.py` 의 2번이 잡는다).
    """
    _row(db, users["u1"].id, sheet=STARTUP, position=1, company_name="샘플다",
         management="관리 중", deal_pitch="스마트팜 관제 SaaS")
    body = _open(allowed, STARTUP)
    assert "deal_pitch" in body, "칸 자체가 안 섰습니다 — 아래 단정이 무의미해집니다"
    assert 'data-filters="deal_pitch' not in body
    assert "data-f-deal" not in body
    assert 'data-field="deal_pitch" data-filter-key' not in body


def test_검색에는_넣는다(allowed, db, users):
    """문구로 찾는 것이 이 칸을 둔 이유에 가깝다.

    툴바의 `기업 · 대표자 · 내용 검색` 은 줄의 `data-search` 를 본다. 서버가
    거기 안 넣으면 **새로고침 전후로 검색 결과가 달라진다** — 화면에서 칸을
    고치면 `refreshRowFlags` 가 `td.cell` 을 전부 이어 붙여 다시 적으므로
    그때는 걸리는데, 새로고침하면 서버가 그린 값으로 돌아가 안 걸린다.
    """
    _row(db, users["u1"].id, sheet=STARTUP, position=1, company_name="샘플라",
         deal_pitch="스마트팜 관제 SaaS")
    body = _open(allowed, STARTUP)
    row = re.search(r'<tr data-id="\d+" data-search="([^"]*)"', body)
    assert row, "줄에서 data-search 를 못 찾았습니다"
    assert "스마트팜 관제 saas" in row.group(1), row.group(1)


def test_엑셀에도_실린다(allowed, db, users):
    """화면에 보이는데 내려받으면 없는 칸을 만들지 않는다.

    없다는 사실 자체를 아무도 눈치채지 못한 채 그 파일이 보고서로 돌아다닌다.
    바로 옆 `기업 관리` 도 같은 성격의 긴 글인데 이미 실려 있다.

    자리는 **맨 뒤**다 — 화면 순서대로 끼우면 그 뒤 월 열이 통째로 한 칸씩
    밀려 지난번에 내려받아 둔 파일과 나란히 놓고 볼 수가 없다.
    """
    from app.routers.consulting import (CONTRACT_EXPORT_HEADERS,
                                        STARTUP_EXPORT_HEADERS)

    _row(db, users["u1"].id, sheet=STARTUP, position=1, company_name="샘플마",
         deal_pitch=PITCH)
    assert STARTUP_EXPORT_HEADERS == ["딜 소개문구"]
    # 계약 탭 칸들 뒤에 붙는다 — 이미 내려받아 둔 파일의 칸 자리가 안 밀린다.
    src = pathlib.Path("app/routers/consulting.py").read_text(encoding="utf-8")
    assert "CONTRACT_EXPORT_HEADERS\n               + STARTUP_EXPORT_HEADERS" in src
    assert CONTRACT_EXPORT_HEADERS[-1] == "계약서 수신여부"

    r = allowed.get("/api/export/consulting.xlsx")
    assert r.status_code == 200 and len(r.content) > 0


# --- 3. 다른 탭 ---------------------------------------------------------------

def test_다른_두_탭에는_칸도_값도_안_선다(allowed, db, users):
    """소개 문구는 **아직 관리 중인 기업**에 대고 쓰는 말이다.

    `경영본부 전달 기업` 은 이미 넘긴 곳이고 `월간 계약 업무현황표` 는 표
    자체가 다르다. 값을 늘 실으면 아무 머리글도 안 보는 죽은 속성이 된다
    (`tests/test_filter_columns.py` 의 2번).

    **`not is_contract_sheet` 로 가르면 여기서 걸린다** — 계약 탭이 아닌 탭은
    `경영본부 전달 기업` 말고도 사람이 시트를 올려 만든 탭까지 여럿이다.
    """
    _row(db, users["u1"].id, sheet=HANDOVER, position=1, company_name="샘플바")
    _row(db, users["u1"].id, sheet=CONTRACT, position=1, company_name="샘플사",
         management="유료")
    for sheet in (HANDOVER, CONTRACT):
        body = _open(allowed, sheet)
        assert "딜 소개문구" not in body, sheet
        assert "deal_pitch" not in body, sheet
    # 경영본부 탭의 표는 이 PR 전과 글자 그대로 같다.
    assert _heads(_open(allowed, HANDOVER)) == [
        "NO", "지역", "미팅일", "기업명", "기업 관리",
        "대표자", "연락처", "이메일", ""]


def test_스타트업_탭에서만_기업_관리_바로_오른쪽에_선다(allowed, db, users):
    """사용자가 부른 자리 그대로다 — `기업 관리` **바로 오른쪽**.

    칸 순서가 머리글과 어긋나면 그 뒤가 통째로 한 칸씩 밀린다.
    """
    _row(db, users["u1"].id, sheet=STARTUP, position=1, company_name="샘플아",
         management="관리 중", deal_pitch="스마트팜 관제 SaaS")
    body = _open(allowed, STARTUP)
    heads = _heads(body)
    assert heads.index("딜 소개문구") == heads.index("기업 관리") + 1, heads
    fields = re.findall(r'data-field="([^"]+)"', body.split("<tbody>", 1)[1])
    assert fields.index("deal_pitch") == fields.index("management") + 1, fields


def test_다른_탭에_값이_남아_있어도_그_탭_화면에는_안_나온다(allowed, db, users):
    """화면에서 뺀 것이지 값을 지운 것이 아니다 — 이 저장소는 이력을 함부로
    지우지 않는다(`CONTRACT_TAIL` 이 대표자·연락처를 남겨 둔 것과 같다).

    탭을 옮긴 줄이 있을 수 있어서 값이 남는 일 자체는 막지 않는다. 다만 그
    탭의 화면에는 칸이 없으므로 글이 새어 나오지도 않아야 한다.
    """
    from app.models import ConsultingCompany

    row = _row(db, users["u1"].id, sheet=HANDOVER, position=1,
               company_name="샘플자", deal_pitch="옮겨 오기 전에 적어 둔 문구")
    body = _open(allowed, HANDOVER)
    assert "옮겨 오기 전에 적어 둔 문구" not in body
    db.expire_all()
    assert db.get(ConsultingCompany, row.id).deal_pitch == "옮겨 오기 전에 적어 둔 문구"


# --- 4. 판정 자리에 새어 들어가지 않는가 --------------------------------------

def test_칩과_KPI_와_갈래_판정은_이_칸을_안_본다():
    """판정은 `services/consulting_status.py` **한 곳**이다 — 늘리지 않는다.

    이 칸이 거기 끼면 소개 문구에 우연히 든 `관리` 한 낱말로 그 줄이 `관리 중`
    으로 걸린다. 칩 넷은 `기업 관리` 한 갈래를 서로 안 겹치게 나눈 것이고,
    KPI 넷은 탭을 가리지 않고 늘 서는 숫자다 — 이 칸은 한 탭에만 있어서
    다른 탭에서는 늘 0 이 되는데 그 0 이 그 탭에 대한 사실처럼 읽힌다.
    """
    src = pathlib.Path("app/services/consulting_status.py").read_text(encoding="utf-8")
    assert "deal_pitch" not in src, \
        "소개 문구가 갈래 판정 자리로 새어 들어왔습니다"
    tmpl = pathlib.Path("app/templates/consulting.html").read_text(encoding="utf-8")
    assert 'data-cs-filter="deal_pitch"' not in tmpl, "칩은 `기업 관리` 한 갈래다"
    assert 'data-kpi="deal_pitch"' not in tmpl, "KPI 는 탭을 가리지 않고 늘 선다"


def test_표_모양은_이름이_아니라_열쇠로_짝짓는다(db):
    """탭 이름을 고쳐도 `딜 소개문구` 칸이 사라지면 안 된다.

    이름으로 짝지어 두면 이름을 고칠 수 있게 만든 것이 곧 함정이 된다 —
    화면은 멀쩡하고 칸만 조용히 사라진다(`services/consulting_sheets.py`).
    """
    from app.routers import consulting
    from app.services import consulting_sheets as cs

    assert consulting.SHEET_LAYOUTS[cs.STARTUP] == (
        consulting.STARTUP_COLUMNS, consulting.TAIL_COLUMNS)
    assert consulting.STARTUP_COLUMNS[-1] == ("딜 소개문구", "deal_pitch")
    # 경영본부 탭과 사람이 만든 탭은 지금까지의 묶음 그대로다.
    assert cs.HANDOVER not in consulting.SHEET_LAYOUTS
    assert consulting.layout_of(db, "경영본부 전달 기업") == (
        consulting.FIXED_COLUMNS, consulting.TAIL_COLUMNS)
    assert consulting.layout_of(db, "사람이 올려 만든 탭") == (
        consulting.FIXED_COLUMNS, consulting.TAIL_COLUMNS)


# --- 5. 마이그레이션 ---------------------------------------------------------

def test_마이그레이션은_기존_줄에_값을_지어_넣지_않는다():
    """운영에는 이 탭에 이미 줄이 들어 있다. 그 줄들은 **빈칸으로 남는다.**

    옆 `기업 관리` 에 섞여 있던 문장을 옮겨 오고 싶어지는 자리인데, 그러면
    앱이 **어디까지가 소개 문구인지 지어내는 것**이 된다 — 그 경계는 아무도
    정한 적이 없고, 잘못 나눈 뒤에는 원래 한 줄이 어땠는지 남지 않는다.

    `upgrade` 가 칸만 만들고 채우지 않는지, `downgrade` 로 되돌아가는지를
    본다 — 둘 중 하나만 있으면 되돌릴 수 없는 마이그레이션이 된다.
    """
    import importlib.util

    path = (pathlib.Path(__file__).resolve().parent.parent / "alembic" / "versions"
            / "0049_consulting_deal_pitch.py")
    spec = importlib.util.spec_from_file_location("m0049", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.down_revision == "0048_consulting_contract_received"
    assert mod.COLUMN == "deal_pitch"
    src = path.read_text(encoding="utf-8")
    # 채우는 문장이 없어야 한다 — 있으면 그건 앱이 사실을 지어낸 것이다.
    body = src.split('"""')[-1]
    assert "UPDATE" not in body.upper(), \
        "기존 줄에 값을 채우고 있습니다 — 아무도 확인한 적 없는 사실입니다"
    assert "def upgrade" in src and "def downgrade" in src
    assert "drop_column" in src, "되돌릴 수 없는 마이그레이션입니다"
    # 메모처럼 쓰는 칸이라 `Text` 다 — `management`·`notes` 와 같다.
    assert "sa.Text()" in src, "긴 글 칸인데 길이 제한이 있는 자료형입니다"


def test_모델과_마이그레이션이_같은_자료형을_말한다():
    """한쪽만 고치면 새로 만든 DB 와 마이그레이션을 태운 DB 가 갈린다."""
    from sqlalchemy import Text

    from app.models import ConsultingCompany

    column = ConsultingCompany.__table__.c.deal_pitch
    assert isinstance(column.type, Text)
    assert column.nullable, "빈칸이 곧 `아직 안 적음` 이라 NULL 이 서야 한다"
