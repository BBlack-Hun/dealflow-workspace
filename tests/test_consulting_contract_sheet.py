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


def test_첫_탭은_스타트업이다(db):
    from app.services.consulting_sheets import default_label, labels

    names = labels(db)
    assert names[0] == "스타트업"
    assert default_label(db) == "스타트업"
    assert "중요 스타트업" not in names


def test_새_줄의_기본_탭도_같이_바뀌었다(db, users):
    """모델 기본값이 옛 이름으로 남으면, 화면을 안 거친 줄만 유령 탭에 쌓인다."""
    from app.models import ConsultingColumn, ConsultingCompany
    from app.services.consulting_sheets import default_label

    row = _row(db, users["u1"].id, company_name="샘플기업")
    col = ConsultingColumn(user_id=users["u1"].id, label="8월 리마인드")
    db.add(col)
    db.commit()
    assert row.sheet == default_label(db)
    assert col.sheet == default_label(db)


def test_옛_이름의_시트를_다시_올려도_유령_탭이_안_생긴다(db):
    """사람이 들고 있는 xlsx 는 여전히 옛 이름이다. 그대로 받으면 같은 명단이
    두 탭으로 갈린다 — 가져오기가 이름을 옮겨 준다."""
    import sys

    sys.path.insert(0, "scripts")
    from import_consulting import SHEET_ALIAS

    from app.services.consulting_sheets import default_label

    assert SHEET_ALIAS["중요 스타트업"] == default_label(db)


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
    #
    # `계약서 수신여부` 는 `계약여부` **바로 오른쪽**이다. 계약을 맺은 것과
    # 계약서를 받은 것은 다른 사실이라 나란히 놓고 봐야 뜻이 갈린다.
    # `담당` 은 여러 사람의 표를 같이 보는 사람에게만 선다(이 검사의 `allowed`
    # 가 그렇다). 탭과 무관한 칸이라 계약 탭에도 같은 자리에 있다.
    assert heads == ["NO", "담당", "월", "계약월", "기업명", "계약여부",
                     "계약서 수신여부", "성공보수율", "계약금", ""], heads
    # 머리글과 데이터 칸이 **같은 순서로** 갈라져야 한다. 어긋나면 그 뒤가
    # 통째로 한 칸씩 밀린다.
    assert _fields(_open(allowed, CONTRACT)) == [
        "region", "meeting_at", "company_name", "management",
        "contract_received", "success_fee", "contract_fee"]


def test_다른_탭의_표는_한_칸도_안_바뀐다(allowed, db, users):
    """탭 하나를 고치다 **다른 탭의 표가 바뀌면** 안 된다.

    스타트업 탭에 `딜 소개문구` 가 선 것은 그 탭에 대고 따로 만든 칸이라
    여기서 세는 자리에 들어 있다(`tests/test_consulting_deal_pitch.py`).
    계약 탭의 칸이 새어 나온 것과는 다르다 — 아래 `계약서 수신여부` 검사가
    그쪽을 본다.
    """
    _row(db, users["u1"].id, company_name="샘플자", region="서울",
         ceo_name="김샘플", phone="010-0000-0000", email="a@example.com")
    body = _open(allowed, "스타트업")
    assert _heads(body) == ["NO", "담당", "지역", "미팅일", "기업명", "기업 관리",
                            "딜 소개문구", "대표자", "연락처", "이메일",
                            ""], _heads(body)
    assert _fields(body) == ["region", "meeting_at", "company_name",
                             "management", "deal_pitch",
                             "ceo_name", "phone", "email"]


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
    from app.services import consulting_status as status

    assert status.tag_value("무료", contract=True) == "무료"
    assert status.tag_value("유료", contract=True) == "유료"
    # 계약 탭에는 `관리 중`·`드랍` 이라는 갈래 자체가 없다 — 칩도 0곳이다.
    assert not status.is_managed("무료", contract=True)
    assert not status.is_dropped("무료", contract=True)
    # 다른 탭은 지금까지 그대로
    assert status.tag_value("관리 중") == "관리 중"
    assert status.tag_value("무료") == "기타 메모"

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
         success_fee="3%", contract_fee="무료", contract_received="O")
    assert CONTRACT_EXPORT_HEADERS == ["성공보수율", "계약금", "계약서 수신여부"]
    r = allowed.get("/api/export/consulting.xlsx")
    assert r.status_code == 200 and len(r.content) > 0


# --- 5. `계약서 수신여부` ----------------------------------------------------
#
# 계약을 맺은 것과 **계약서를 받은 것**은 다른 사실이다. 그 둘이 `계약여부`
# (`무료`/`유료`) 한 칸에 섞여 있어서, 계약은 했는데 서류가 아직 안 온 곳을
# 표에서 가려낼 방법이 없었다.

def test_계약서_수신여부는_고쳐지고_다시_읽힌다(allowed, db, users):
    """스키마·저장·되읽기·화면 넷 중 하나가 빠지면 **조용히** 안 저장된다.

    라우터의 `CompanyIn` 에 이름을 안 적으면 pydantic 이 모르는 칸을 그냥
    버린다 — 오류도 안 나고, 고친 사람은 저장된 줄 안다.
    """
    from app.models import ConsultingCompany

    row = _row(db, users["u1"].id, sheet=CONTRACT, position=1, company_name="샘플하")
    assert allowed.patch(f"/api/consulting/{row.id}",
                         json={"contract_received": "O"}).status_code == 200
    db.expire_all()
    assert db.get(ConsultingCompany, row.id).contract_received == "O"
    assert allowed.get(f"/api/consulting/{row.id}").json()["contract_received"] == "O"
    assert ('data-choices="O,X">O</td>' in _open(allowed, CONTRACT))


def test_아직_안_정한_줄은_빈칸으로_남는다(allowed, db, users):
    """**`O`/`X` 둘뿐이면 미정을 적을 자리가 없다.** 그래서 빈칸이 그 자리다.

    이미 들어 있던 줄을 `X` 로 채워 두면 앱이 "안 받았다"고 단정하는 것이 되고
    (아무도 확인한 적 없는 사실이다), 나중에 사람이 채울 때 **누가 확인한 X**
    인지 아무도 모른다. 비어 있어야 "아직 안 봤다" 가 눈에 보인다.

    빈칸인 줄을 찾는 길은 머리글 필터의 `(비어 있음)` 이다 — 그래서 행이 빈
    값이라도 그 칸을 **싣고** 있어야 한다(안 실으면 필터가 못 세운다).
    """
    from app.models import ConsultingCompany

    row = _row(db, users["u1"].id, sheet=CONTRACT, position=1, company_name="샘플거")
    assert db.get(ConsultingCompany, row.id).contract_received is None
    assert allowed.get(f"/api/consulting/{row.id}").json()["contract_received"] == ""
    assert 'data-f-received=""' in _open(allowed, CONTRACT)

    # 잘못 고른 것을 **빈칸으로 되돌릴 수 있어야** 한다.
    allowed.patch(f"/api/consulting/{row.id}", json={"contract_received": "X"})
    allowed.patch(f"/api/consulting/{row.id}", json={"contract_received": ""})
    db.expire_all()
    assert db.get(ConsultingCompany, row.id).contract_received == ""
    assert 'data-f-received=""' in _open(allowed, CONTRACT)


def test_계약서_수신여부_필터는_세_곳이_짝이_맞는다(allowed, db, users):
    """머리글 선언 · 행이 싣는 값 · 칸이 아는 필터 키 — 셋이 같아야 선다.

    하나만 어긋나도 화면은 멀쩡한데 필터만 **아무 말 없이** 거짓말한다
    (`tests/test_filter_columns.py` 가 전 화면을 훑는 부류다. 이 탭은 그 스윕이
    `?sheet=` 로 따로 열어야 보이는 자리라 여기서도 한 번 더 붙잡는다).
    """
    _row(db, users["u1"].id, sheet=CONTRACT, position=1,
         company_name="샘플너", management="유료", contract_received="O")
    body = _open(allowed, CONTRACT)
    assert 'data-filters="received:계약서 수신여부"' in body
    assert 'data-f-received="O"' in body
    assert 'data-field="contract_received" data-filter-key="received"' in body
    # 값은 **골라서** 넣는다. 손으로 적게 두면 `O`·`o`·`ㅇ`·`○` 로 갈려
    # 두 가지뿐인 칸에서 필터가 못 쓰게 된다.
    assert 'data-choices="O,X"' in body


def test_다른_탭은_이_칸을_아예_안_세운다(allowed, db, users):
    """계약서는 계약 줄에만 있는 개념이다.

    다른 두 탭의 같은 자리 칸은 `기업 관리` 라는 **자유 서술**이라 성격이
    아예 다르다. 빈 값이라도 늘 실어 두면 아무 머리글도 안 보는 죽은 속성이
    된다(`tests/test_filter_columns.py` 의 2번).
    """
    _row(db, users["u1"].id, company_name="샘플더", management="관리 중 : 미팅 완")
    body = _open(allowed, "스타트업")
    assert "계약서 수신여부" not in body
    assert "data-f-received" not in body
    assert "contract_received" not in body
    # 다른 탭의 표는 한 칸도 안 바뀐다.
    # 이 탭이 세우는 칸은 이것뿐이다. `딜 소개문구` 는 스타트업 탭에 대고 따로
    # 만든 칸이라 여기 들어 있다(`tests/test_consulting_deal_pitch.py`).
    assert _heads(body) == ["NO", "담당", "지역", "미팅일", "기업명", "기업 관리",
                            "딜 소개문구", "대표자", "연락처", "이메일",
                            ""], _heads(body)
    assert _fields(body) == ["region", "meeting_at", "company_name",
                             "management", "deal_pitch",
                             "ceo_name", "phone", "email"]


def test_칩과_KPI_는_이_칸을_안_본다():
    """판정은 `services/consulting_status.py` **한 곳**이다 — 늘리지 않는다.

    칩 넷은 `기업 관리` 한 갈래를 서로 안 겹치게 나눈 것이라 한 번에 하나만
    눌린다. 계약서 수신은 **다른 축**이라 거기 끼워 넣으면 둘을 같이 걸 수가
    없다 — 머리글 필터로 세워 두면 칩과 AND 로 묶인다(consulting.js 의 `extra`).

    KPI 도 마찬가지다. 위 숫자 넷은 탭을 가리지 않고 늘 서는데, 이 칸은 계약
    탭에만 있어서 다른 두 탭에서는 늘 0 이 된다 — 그 0 이 그 탭에 대한
    사실처럼 읽힌다.
    """
    import pathlib as _p

    src = _p.Path("app/services/consulting_status.py").read_text(encoding="utf-8")
    assert "contract_received" not in src, \
        "계약서 수신여부 판정이 갈래 판정 자리로 새어 들어왔습니다"
    tmpl = _p.Path("app/templates/consulting.html").read_text(encoding="utf-8")
    assert 'data-cs-filter="received"' not in tmpl, "칩은 `기업 관리` 한 갈래다"
    assert 'data-kpi="received"' not in tmpl, "KPI 는 탭을 가리지 않고 늘 선다"


def test_마이그레이션은_기존_줄에_값을_지어_넣지_않는다():
    """운영에는 이 탭에 이미 줄이 들어 있다. 그 줄들은 **빈칸으로 남는다.**

    `upgrade` 가 칸만 만들고 채우지 않는지, `downgrade` 로 되돌아가는지를
    본다 — 둘 중 하나만 있으면 되돌릴 수 없는 마이그레이션이 된다.
    """
    import importlib.util

    path = (pathlib.Path(__file__).resolve().parent.parent / "alembic" / "versions"
            / "0048_consulting_contract_received.py")
    spec = importlib.util.spec_from_file_location("m0047", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.down_revision == "0047_contract_received"
    src = path.read_text(encoding="utf-8")
    # 채우는 문장이 없어야 한다 — 있으면 그건 앱이 사실을 지어낸 것이다.
    assert "UPDATE" not in src.upper().split('"""')[-1], \
        "기존 줄에 값을 채우고 있습니다 — 아무도 확인한 적 없는 사실입니다"
    assert "def upgrade" in src and "def downgrade" in src
    assert "drop_column" in src, "되돌릴 수 없는 마이그레이션입니다"


def test_화면_코드를_그대로_돌려_본다():
    """서버만 고치면 반쪽이다 — 고른 값이 저장되고 필터에 걸리는 데까지 본다.

    `tests/js/consulting_contract_received_test.js` 가 consulting.js 를 실제로
    돌려, 칸을 눌러 `O`/`X`/`비움` 을 고르고 나간 요청과 행에 적힌 값을 본다.
    로컬에서는 `node tests/js/consulting_contract_received_test.js` 로도 돈다.
    """
    import shutil
    import subprocess

    node = shutil.which("node")
    if not node:
        pytest.skip("node 미설치 — 브라우저 로직 테스트 생략")
    js = (pathlib.Path(__file__).resolve().parent / "js"
          / "consulting_contract_received_test.js")
    r = subprocess.run([node, str(js)], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr
