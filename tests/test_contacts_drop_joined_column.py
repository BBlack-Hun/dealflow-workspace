"""투자사 관리 현황 표에서 `카톡방 참여여부` 칸을 뺐다 — **표에서만.**

요청 원문: "투자사 관리 현황 메뉴에서 "카톡방 참여 여부" 컬럼 없애줘".

## 뺀 것 (그 화면의 표 하나)

  · 머리글 `카톡방 참여여부` 와 그 머리글 필터(`joined`)
  · 줄마다의 그 칸(`data-field="kakao_joined"`)과 행이 싣던 거를 값(`data-f-joined`)

## 그대로 둔 것

  · 값 자체(`VcContact.kakao_joined`) — 시트 업로드 · 엑셀 · 방 확인과 맞추는 규칙
    (`services/room_joined`) · 수정 이력이 계속 읽고 적는다. 이주는 없다.
  · **수정창의 `카톡방 참여여부`** — 표에서 칸이 빠졌으니 손으로 고치는 자리가
    여기 하나다. 빠지면 틀린 값을 고칠 길이 없다.
  · 투자컨설턴트 화면 · IR 기업 현황의 `카톡 연결 여부` 와 그 필터(`joined`) —
    같은 키를 쓰지만 **다른 표**다.

## 저장해 둔 `?joined=…` 주소

머리글 필터의 상태는 **주소에만** 실린다(`filters.js` — 저장소 · 저장된 보기가
없다). 선언이 없는 키는 읽을 때 건너뛰므로(`tests/js/filters_test.js` 의 `필터와
무관한 쿼리는 무시한다`) 그 주소로 들어와도 **보이지 않는 필터가 걸리지 않고**
전체가 뜬다. 서버도 그 키를 읽지 않는다 — 아래 마지막 검사가 본다.

이름·회사는 전부 지어낸 값이다 — 저장소가 공개다.
"""
from __future__ import annotations

import re
from urllib.parse import quote

import pytest

from .conftest import DEMO_PASSWORD

LABEL = "카톡방 참여여부"


@pytest.fixture()
def row(db, users):
    """참여여부가 `O` 인 투자사 한 줄 — 값이 있어야 "칸이 없다" 가 뜻이 있다."""
    from app.models import VcContact

    contact = VcContact(user_id=users["u1"].id, name="가나다", firm="테스트캐피탈",
                        status="active", kakao_joined="O")
    db.add(contact)
    db.commit()
    return contact


def _table(html: str) -> str:
    at = html.index('id="contacts-table"')
    return html[at:html.index("</table>", at)]


def _filter_keys(table: str) -> set:
    keys = set()
    for spec in re.findall(r'data-filters="([^"]*)"', table):
        keys |= {part.split(":", 1)[0] for part in spec.split("|") if part}
    return keys


def test_투자사_표에_카톡방_참여여부_칸과_필터가_없다(logged_in, row):
    table = _table(logged_in.get("/contacts").text)
    assert 'data-name="가나다"' in table, "밑자리 줄이 안 그려졌습니다 — 빈 표를 잰 것입니다"

    head = table[table.index("<thead"):table.index("</thead>")]
    names = [" ".join(re.sub(r"<[^>]+>", " ", th).split())
             for th in re.findall(r"<th\b[^>]*>(.*?)</th>", head, re.S)]
    assert LABEL not in names, names
    assert "joined" not in _filter_keys(table), "머리글 필터 `joined` 가 남아 있습니다"

    # 칸도, 행이 싣던 거를 값도 함께 빠져야 한다 — 값만 남으면 아무 머리글도
    # 안 보는 죽은 속성이고, 칸만 남으면 머리글과 한 칸씩 밀린다.
    assert 'data-field="kakao_joined"' not in table
    assert 'data-filter-key="joined"' not in table
    assert "data-f-joined" not in table

    # 옆 칸들은 그대로다 — `관심도` 바로 뒤가 `메모` 다.
    assert names[names.index("관심도") + 1] == "메모", names
    body_row = table[table.index('data-name="가나다"'):]
    body_row = body_row[:body_row.index("</tr>")]
    assert len(re.findall(r"<td\b", body_row)) == len(names), (
        "머리글 칸 수와 줄의 칸 수가 다릅니다 — 한쪽만 뺀 것입니다")


def test_수정창의_카톡방_참여여부는_그대로_서고_저장된다(logged_in, db, row):
    """표에서 뺐으니 **손으로 고치는 자리는 수정창 하나**다."""
    from app.models import VcContact

    html = logged_in.get("/contacts").text
    field = re.search(r'<label class="field"><span>([^<]*)</span>\s*'
                      r'<input[^>]*id="f-kakao_joined"[^>]*>', html)
    assert field, "수정창에서 `카톡방 참여여부` 칸이 사라졌습니다"
    assert field.group(1) == LABEL
    options = re.search(r'<datalist id="opts-panel-kakao_joined">(.*?)</datalist>',
                        html, re.S)
    assert options and re.findall(r'value="([^"]*)"', options.group(1)) == ["O", "X"]

    # 창의 [저장] 이 가는 길 그대로(`contacts.js` 의 `FIELDS` → `PATCH`).
    assert logged_in.patch(f"/api/contacts/{row.id}",
                           json={"kakao_joined": "X"}).status_code == 200
    db.expire_all()
    assert db.get(VcContact, row.id).kakao_joined == "X"
    assert logged_in.get(f"/api/contacts/{row.id}").json()["contact"]["kakao_joined"] == "X"


def test_저장해_둔_joined_주소로_들어와도_전체가_뜬다(logged_in, row):
    """`?joined=X` 인데 이 줄은 `O` 다 — 그래도 줄이 그려지고, 그 키를 선언한
    머리글이 없어 화면(`filters.js`)도 거르지 않는다."""
    table = _table(logged_in.get("/contacts?joined=X").text)
    assert 'data-name="가나다"' in table
    assert "joined" not in _filter_keys(table)


def test_투자컨설턴트_화면의_카톡_연결_여부_필터는_그대로다(client, db, users):
    """같은 키(`joined`)를 쓰는 **다른 표**다 — 이 판이 건드리면 안 된다."""
    from app.models import ConsultingCompany

    users["u1"].can_view_consulting = 1
    db.add(ConsultingCompany(user_id=users["u1"].id, sheet="스타트업", position=1,
                             company_name="샘플가", kakao_joined="O"))
    db.commit()
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})

    body = client.get(f"/consulting?sheet={quote('스타트업')}").text
    assert 'data-filters="joined:카톡 연결 여부"' in body
    assert 'data-f-joined="O"' in body
    assert 'data-filter-key="joined"' in body
