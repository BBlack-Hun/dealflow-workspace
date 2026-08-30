"""투자컨설턴트 — 이름(메뉴·탭)과 `월간 계약 업무현황표` 탭의 표.

여기서 막는 것은 넷이다.

  1. 메뉴·탭 이름이 **한 곳에서** 나오는가. 두 곳에 적으면 하나는 반드시 낡는다.
  2. 슬래시 한 줄을 칸으로 나누는 규칙이 **조각 수가 달라도** 무너지지 않는가.
  3. 마이그레이션이 들고 있는 규칙과 앱의 규칙이 **같은가.** 마이그레이션은
     돌아간 그때로 고정되어야 해서 일부러 베껴 두었다 — 베낀 것은 갈린다.
  4. 화면에서 뺀 칸(대표자·연락처·이메일)의 **값이 지워지지 않았는가.**

이름·기업명은 전부 지어낸 값이다 — 저장소가 공개다.
"""
from __future__ import annotations

import importlib.util
import pathlib

import pytest

from .conftest import DEMO_PASSWORD

CONTRACT = "월간 계약 업무현황표"


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


# --- 1. 이름 ----------------------------------------------------------------

def test_메뉴_이름은_투자컨설턴트다():
    """화면 제목도 이 목록에서 나온다 — 한 곳만 고치면 둘 다 바뀐다."""
    from app.ui import MENU, menu_label, screen_label

    item = next(m for m in MENU if m["key"] == "consult")
    assert item["label"] == "투자컨설턴트"
    assert menu_label("consult") == "투자컨설턴트"
    assert screen_label("/consulting") == "투자컨설턴트"


def test_첫_탭은_스타트업이다():
    from app.routers.consulting import DEFAULT_SHEET, SHEETS

    assert SHEETS[0] == "스타트업"
    assert DEFAULT_SHEET == "스타트업"
    assert "중요 스타트업" not in SHEETS


def test_새_줄의_기본_탭도_같이_바뀌었다(db, users):
    """모델 기본값이 옛 이름으로 남으면, 화면을 안 거친 줄만 유령 탭에 쌓인다."""
    from app.models import ConsultingColumn, ConsultingCompany
    from app.routers.consulting import DEFAULT_SHEET

    row = _row(db, users["u1"].id, company_name="샘플기업")
    col = ConsultingColumn(user_id=users["u1"].id, label="8월 리마인드")
    db.add(col)
    db.commit()
    assert row.sheet == DEFAULT_SHEET
    assert col.sheet == DEFAULT_SHEET


def test_옛_이름의_시트를_다시_올려도_유령_탭이_안_생긴다():
    """사람이 들고 있는 xlsx 는 여전히 옛 이름이다. 그대로 받으면 같은 명단이
    두 탭으로 갈린다 — 가져오기가 이름을 옮겨 준다."""
    import sys

    sys.path.insert(0, "scripts")
    from import_consulting import SHEET_ALIAS

    from app.routers.consulting import DEFAULT_SHEET

    assert SHEET_ALIAS["중요 스타트업"] == DEFAULT_SHEET


def test_옛_이름으로_넣으려_하면_거절한다(allowed):
    """`sheet_tabs` 가 줄의 이름을 그대로 탭으로 올린다 — 옛 이름을 받으면
    유령 탭이 다시 생긴다."""
    r = allowed.post("/api/consulting",
                     json={"company_name": "샘플기업Q", "sheet": "중요 스타트업"})
    assert r.status_code == 400


# --- 2. 슬래시 한 줄 나누기 --------------------------------------------------

# 시트가 스스로 적어 둔 순서: `기업명 / 계약금액 / 성공보수율 / 계약일`
CASES = [
    # 네 조각 — 시트에서 가장 흔한 모양
    ("샘플가/ 무료/ 3.5%/ 미정",
     {"company_name": "샘플가", "contract_fee": "무료",
      "success_fee": "3.5%", "meeting_at": "미정"}),
    ("샘플나/ 유료 90만/ 3프로 / 8",
     {"company_name": "샘플나", "contract_fee": "유료 90만",
      "success_fee": "3프로", "meeting_at": "8"}),
    # 세 조각 — 계약일이 아직 없다. **뒤 칸을 비운다**(앞에서 채우면 보수율
    # 칸에 계약일이 들어간다).
    ("샘플다/무료/4%",
     {"company_name": "샘플다", "contract_fee": "무료", "success_fee": "4%"}),
    # 두 조각
    ("샘플라/ 무료계약",
     {"company_name": "샘플라", "contract_fee": "무료계약"}),
    # 다섯 조각 — 남는 조각을 **마지막 칸에 이어 둔다**(버리지 않는다)
    ("샘플마/ 유료 90만/ 4%/ 8/ 재계약 예정",
     {"company_name": "샘플마", "contract_fee": "유료 90만",
      "success_fee": "4%", "meeting_at": "8 / 재계약 예정"}),
    # 슬래시가 없으면 나눌 것이 없다
    ("샘플바", {}),
    ("", {}),
]


@pytest.mark.parametrize("line,want", CASES)
def test_슬래시_줄을_칸으로_나눈다(line, want):
    from app.routers.consulting import split_contract_line

    assert split_contract_line(line) == want


def test_나눈_결과에_없는_칸은_비워_둔다():
    """`dict` 에 아예 안 담긴다 — `""` 로 담으면 이미 적혀 있던 값을 덮는다."""
    from app.routers.consulting import split_contract_line

    got = split_contract_line("샘플사/무료/4%")
    assert "meeting_at" not in got


# --- 3. 마이그레이션과 앱이 같은 규칙인가 ------------------------------------

def _migration():
    """마이그레이션 모듈을 파일에서 직접 불러온다(패키지가 아니다)."""
    path = (pathlib.Path(__file__).resolve().parent.parent
            / "alembic" / "versions" / "0040_contract_sheet_columns.py")
    spec = importlib.util.spec_from_file_location("m0040", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_마이그레이션이_베껴_둔_규칙이_앱과_같다():
    """마이그레이션은 **돌아간 그때의 규칙**으로 고정되어야 해서 앱 함수를
    부르지 않고 베껴 두었다. 베낀 것은 갈리므로 여기서 붙잡는다.
    """
    from app.routers import consulting

    mod = _migration()
    assert mod.PARTS == consulting.CONTRACT_PARTS
    for line, _want in CASES:
        assert mod.split_contract_line(line) == consulting.split_contract_line(line), line


# --- 4. 화면 --------------------------------------------------------------

def _open(client, sheet):
    from urllib.parse import quote

    return client.get(f"/consulting?sheet={quote(sheet)}").text


def _heads(html: str) -> list:
    """그려진 표의 머리글 이름들. **정적 글자가 아니라 그려진 화면**을 본다."""
    import re

    m = re.search(r"<thead>(.*?)</thead>", html, re.S)
    assert m, "표 머리글을 찾지 못했습니다"
    out = []
    for cell in re.findall(r"<th\b[^>]*>(.*?)</th>", m.group(1), re.S):
        # 월 열의 [✕](삭제 폼)은 이름이 아니다.
        cell = re.sub(r"<form\b.*?</form>", " ", cell, flags=re.S)
        out.append(" ".join(re.sub(r"<[^>]+>", " ", cell).split()))
    return out


def _fields(html: str) -> list:
    import re

    body = html.split("<tbody>", 1)[1]
    return re.findall(r'data-field="([^"]+)"', body)


def test_계약_탭의_머리글은_시트가_부르는_이름이다(allowed, db, users):
    _row(db, users["u1"].id, sheet=CONTRACT, position=1, region="6월",
         management="무료", company_name="샘플아", success_fee="3.5%",
         contract_fee="무료", meeting_at="미정")
    heads = _heads(_open(allowed, CONTRACT))
    # `계약월` — 시트 머리글은 `계약일` 이지만 칸에 든 값은 `미정` 과 `8` 이라
    # **달**이다. 이름이 `계약일` 이면 다음에 채우는 사람이 `2026-08-15` 같은
    # 날짜를 넣어, 같은 칸에 두 모양이 섞인다.
    assert heads == ["NO", "월", "계약월", "기업명", "계약여부",
                     "성공보수율", "계약금", ""], heads
    # 머리글과 데이터 칸이 **같은 순서로** 갈라져야 한다. 어긋나면 그 뒤가
    # 통째로 한 칸씩 밀린다.
    assert _fields(_open(allowed, CONTRACT)) == [
        "region", "meeting_at", "company_name", "management",
        "success_fee", "contract_fee"]


def test_다른_탭의_표는_한_칸도_안_바뀐다(allowed, db, users):
    """탭 하나를 고치다 **다른 탭의 표가 바뀌면** 안 된다."""
    _row(db, users["u1"].id, company_name="샘플자", region="서울",
         ceo_name="김샘플", phone="010-0000-0000", email="a@example.com")
    body = _open(allowed, "스타트업")
    assert _heads(body) == ["NO", "지역", "미팅일", "기업명", "기업 관리",
                            "대표자", "연락처", "이메일", ""], _heads(body)
    assert _fields(body) == ["region", "meeting_at", "company_name",
                             "management", "ceo_name", "phone", "email"]


def test_화면에서_뺀_칸의_값은_지워지지_않는다(allowed, db, users):
    """이 저장소는 이력을 함부로 지우지 않는다 — 화면에서만 뺀 것이다."""
    from app.models import ConsultingCompany

    row = _row(db, users["u1"].id, sheet=CONTRACT, position=1,
               company_name="샘플차", ceo_name="박샘플",
               phone="010-0000-0009", email="b@example.com")
    _open(allowed, CONTRACT)
    db.expire_all()
    kept = db.get(ConsultingCompany, row.id)
    assert (kept.ceo_name, kept.phone, kept.email) == \
        ("박샘플", "010-0000-0009", "b@example.com")
    # API 로도 그대로 읽힌다
    got = allowed.get(f"/api/consulting/{row.id}").json()
    assert got["ceo_name"] == "박샘플" and got["email"] == "b@example.com"


def test_성공보수율과_계약금은_고쳐지고_다시_읽힌다(allowed, db, users):
    """스키마·저장·되읽기·화면 넷 중 하나가 빠지면 **조용히** 안 저장된다."""
    from app.models import ConsultingCompany

    row = _row(db, users["u1"].id, sheet=CONTRACT, position=1, company_name="샘플카")
    r = allowed.patch(f"/api/consulting/{row.id}",
                      json={"success_fee": "4%", "contract_fee": "유료 90만"})
    assert r.status_code == 200
    db.expire_all()
    saved = db.get(ConsultingCompany, row.id)
    assert (saved.success_fee, saved.contract_fee) == ("4%", "유료 90만")

    got = allowed.get(f"/api/consulting/{row.id}").json()
    assert got["success_fee"] == "4%" and got["contract_fee"] == "유료 90만"
    body = _open(allowed, CONTRACT)
    assert '<td class="cell" data-field="success_fee">4%</td>' in body
    assert '<td class="cell" data-field="contract_fee">유료 90만</td>' in body


def test_계약여부_필터는_적힌_그대로_건다(allowed, db, users):
    """`무료`/`유료` 는 이미 추려진 값이다. `기업 관리` 규칙을 태우면 둘 다
    `기타 메모` 로 묶여 고를 것이 하나도 안 남는다."""
    from app.routers.consulting import management_tags

    assert management_tags("무료", contract=True) == "무료"
    assert management_tags("유료", contract=True) == "유료"
    # 다른 탭은 지금까지 그대로
    assert management_tags("관리 중") == "관리 중"
    assert management_tags("무료") == "기타 메모"

    _row(db, users["u1"].id, sheet=CONTRACT, position=1,
         company_name="샘플타", management="무료")
    body = _open(allowed, CONTRACT)
    assert 'data-f-mgmt="무료"' in body


def test_화면이_고친_값을_서버와_같은_규칙으로_다시_적는다():
    """서버만 고치면 반쪽이다 — 고친 직후와 새로고침 뒤가 달라진다."""
    js = pathlib.Path("app/static/js/consulting.js").read_text(encoding="utf-8")
    assert 'data-contract-sheet' in js, "화면이 계약 탭인지 안 읽습니다"
    html = pathlib.Path("app/templates/consulting.html").read_text(encoding="utf-8")
    assert 'data-contract-sheet="{{ 1 if is_contract_sheet else 0 }}"' in html


def test_엑셀에도_새_칸이_실린다(allowed, db, users):
    """화면에만 보이고 내려받으면 없는 칸을 만들지 않는다."""
    from app.routers.consulting import CONTRACT_EXPORT_HEADERS

    _row(db, users["u1"].id, sheet=CONTRACT, position=1, company_name="샘플파",
         success_fee="3%", contract_fee="무료")
    assert CONTRACT_EXPORT_HEADERS == ["성공보수율", "계약금"]
    r = allowed.get("/api/export/consulting.xlsx")
    assert r.status_code == 200 and len(r.content) > 0
