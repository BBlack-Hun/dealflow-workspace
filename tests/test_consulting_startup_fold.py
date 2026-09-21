"""`스타트업 명단으로 보내기` 막대를 **접어 둔다** — 열어서 쓴다.

> "투자컨설턴트 메뉴의 리스트의 **이관메뉴는 닫음 처리**해주고
>  **열어서 기능 사용**할 수 있게!"

바로 앞 판(#219)에서 넣은 다건 보내기 묶음이다. 늘 펴져 있어 표 위가 그만큼
내려앉는데, 매일 쓰는 자리가 아니다 — 표를 읽고 칸을 고치는 것이 이 화면의
일이고 명단으로 보내는 것은 어쩌다 한 번이다.

## 이 파일이 지키는 것

  1. **기본은 닫힘** — `<details>` 에 `open` 이 안 붙는다.
  2. **접는 관용구를 새로 만들지 않았다** — `sheet-fold` 는 투자사 관리
     현황이 이미 쓰는 이름이고, 여닫이는 브라우저가 한다(JS 없음).
  3. 접어도 **DOM 에 그대로 있다** — 단추·명단 고르는 자리가 다 살아 있다.
  4. 접힌 채로도 **몇 개 골랐는지 보인다**(여는 줄에 적는다).
  5. 막대가 서는 조건은 **하나도 안 바뀌었다** — 탭·권한 판정 그대로.

**펼친 상태를 기억시키지 않는다.** 왜 안 해도 되는지는 아래
`test_고르는_동안_화면이_다시_안_그려진다` 가 근거를 붙들어 둔다.
"""
from __future__ import annotations

import pathlib
import re
import shutil
import subprocess

import pytest

from .conftest import DEMO_PASSWORD

ROOT = pathlib.Path(__file__).resolve().parent.parent
STARTUP = "스타트업"
HANDOVER = "경영본부 전달 기업"
HTML = ROOT / "app" / "templates" / "consulting.html"
JS = ROOT / "app" / "static" / "js"


MY_LIST = "스타트업 · 가담당"


@pytest.fixture()
def sheets(db, users):
    """보낼 수 있는 스타트업 명단 하나. `layout="startup"` 이 곧 **그 명단이
    스타트업 화면에 산다**는 뜻이다(`contact_columns.Layout.page`) —
    `test_consulting_to_startup.py` 와 같은 방식이다."""
    from app.models import SheetOwner

    users["u1"].can_view_consulting = 1
    db.add(SheetOwner(label=MY_LIST, user_id=users["u1"].id, layout="startup",
                      is_hidden=1))
    db.commit()


@pytest.fixture()
def sender(client, db, users, sheets):
    """이 막대를 볼 수 있는 사람 — 화면을 보고, 명단 하나를 맡고 있다."""
    from app.models import ConsultingCompany

    db.add(ConsultingCompany(user_id=users["u1"].id, sheet=STARTUP,
                             position=1, company_name="샘플가"))
    db.commit()
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    return client


def _open(client, sheet=STARTUP):
    from urllib.parse import quote

    return client.get(f"/consulting?sheet={quote(sheet)}").text


def _fold(html: str) -> str:
    """접는 상자 태그 한 줄."""
    m = re.search(r'<details[^>]*id="cs-startup-fold"[^>]*>', html)
    return m.group(0) if m else ""


# --- 1. 기본은 닫힘 -----------------------------------------------------------

def test_기본은_닫혀_있다(sender):
    """`<details>` 에 `open` 이 붙으면 펴진 채로 뜬다 — 요청의 반대다."""
    body = _open(sender)
    tag = _fold(body)
    assert tag, "접는 상자를 못 찾았습니다"
    assert " open" not in tag and "open>" not in tag, tag


def test_이_저장소의_접는_관용구를_그대로_쓴다(sender):
    """**새로 만들지 않는다.** 투자사 관리 현황이 표 위 543px 을 접을 때 쓴
    그 이름이고(`contacts.html` 의 `sheet-fold`), 여닫이는 브라우저가 한다 —
    여닫이 하나 때문에 JS 를 붙이면 그 파일이 안 실린 화면에서 죽는다
    (`_ref_new.html` 이 같은 말을 한다)."""
    tag = _fold(_open(sender))
    assert 'class="sheet-fold"' in tag, tag
    # 같은 이름을 쓰는 곳이 이미 있다 — 모양도 저기 CSS 하나에서 온다.
    css = (ROOT / "app" / "static" / "css" / "app.css").read_text(encoding="utf-8")
    assert ".sheet-fold > summary" in css
    contacts = (ROOT / "app" / "templates" / "contacts.html").read_text(encoding="utf-8")
    assert 'class="sheet-fold"' in contacts, \
        "이 이름을 쓰는 다른 화면이 없어졌습니다 — 관용구가 아니게 됩니다"
    # 여닫이에 JS 를 새로 붙이지 않았다.
    html = HTML.read_text(encoding="utf-8")
    assert "cs-startup-fold" not in html.replace('id="cs-startup-fold"', ""), \
        "여닫이를 스크립트로 여는 자리가 화면에 생겼습니다"


# --- 2. 접혀도 살아 있다 -------------------------------------------------------

def test_접힌_채로도_단추와_명단이_DOM_에_그대로_있다(sender):
    """`<details>` 는 **감출 뿐 지우지 않는다.** 지워 버리면 브라우저 찾기도
    검사도 그 자리를 못 본다."""
    body = _open(sender)
    for piece in ('id="cs-startup-bar"', 'id="cs-pick-all"',
                  'id="cs-startup-target"', 'id="cs-startup-send"',
                  MY_LIST):
        assert piece in body, piece
    # 체크 칸은 표 안이라 접어도 그대로 보인다 — 아래 개수 검사의 전제다.
    assert 'class="cs-pick"' in body


def test_고른_개수는_여는_줄에_적힌다(sender):
    """체크 칸은 **표 안**에 있어 접어도 보인다. 개수까지 몸통 안에 두면 줄을
    골라 놓고 아무것도 안 보이는 상태가 된다 — 접힌 채로도 읽혀야 한다.

    **적는 자리는 하나다**(`#cs-pick-count`). 같은 수를 두 곳에 적으면 한쪽이
    낡는다.
    """
    body = _open(sender)
    m = re.search(r"<summary>(.*?)</summary>", body, re.S)
    assert m, "여는 줄을 못 찾았습니다"
    assert 'id="cs-pick-count"' in m.group(1), m.group(1)
    assert body.count('id="cs-pick-count"') == 1, "개수를 두 곳에 적고 있습니다"
    # 여는 줄에 **무엇이 열리는지**도 적혀 있다 — 글자가 없으면 무엇을 누르는
    # 것인지 알 수 없다. 이름은 좌측 메뉴가 들고 있는 값이다(`ui.MENU`).
    from app.ui import menu_label

    assert menu_label("startup") in m.group(1)


# --- 3. 서는 조건은 그대로 -----------------------------------------------------

def test_막대가_서는_조건은_하나도_안_바뀌었다(sender, db, users):
    """접는 상자를 하나 끼운 것뿐이다. 조건이 같이 움직이면 다른 탭에 빈
    여는 줄이 서거나, 쓸 수 있는 탭에서 통째로 사라진다."""
    from app.models import ConsultingCompany

    db.add(ConsultingCompany(user_id=users["u1"].id, sheet=HANDOVER,
                             position=2, company_name="샘플나"))
    db.commit()
    assert _fold(_open(sender, STARTUP)), "쓸 수 있는 탭에서 사라졌습니다"
    other = _open(sender, HANDOVER)
    assert not _fold(other), "다른 탭에 섰습니다"
    assert "cs-startup-bar" not in other
    assert 'class="cs-pick"' not in other


def test_고를_명단이_없으면_여는_줄도_안_선다(client, db, users):
    """눌러도 아무 일이 없는 단추를 세우지 않는다 — 접는 상자가 생기면서
    **빈 여는 줄**이 남기 쉬운 자리다(몸통이 비어도 줄은 선다)."""
    from app.models import ConsultingCompany

    users["u1"].can_view_consulting = 1
    db.add(ConsultingCompany(user_id=users["u1"].id, sheet=STARTUP,
                             position=1, company_name="샘플가"))
    db.commit()
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    body = _open(client)
    assert not _fold(body)
    assert "cs-startup-bar" not in body


# --- 4. 펼친 상태를 기억해야 하나 ---------------------------------------------

def test_고르는_동안_화면이_다시_안_그려진다():
    """**기억시키지 않기로 한 근거다.**

    고르고 보내는 동안 화면이 다시 그려지면 펴 둔 것이 도로 닫혀 못 쓴다.
    그런 자리가 있는지 흐름을 따라가 봤다 — 없다.

      체크 누르기   `change` 로 개수만 고쳐 적는다(`consulting_to_startup.js`)
      검색 · 칩     줄을 `tr.hidden` 으로 감출 뿐이다(`consulting.js`)
      머리글 필터   주소만 `history.replaceState` 로 고친다(`filters.js`)
      칸 고치기     PATCH 뒤 그 칸만 고쳐 적는다

    화면을 다시 받는 자리는 **보내고 난 뒤**(`reload`/명단 화면으로 이동)와
    탭·담당을 바꾸는 **링크**뿐이다. 앞엣것은 일이 끝난 자리이고 뒤엣것은 고른
    체크가 어차피 풀리는 자리라, 펴진 채로 열리면 `0개 선택` 이라고 적힌 빈
    막대가 자리만 먹는다.

    주석은 낡는다. 이 검사가 "고르는 길에 새로고침이 끼어들지 않는다" 를
    붙들어 둔다 — 누가 거기에 `reload` 를 넣으면 여기서 깨지고, 그때는 펴 둔
    상태를 어딘가에 남기는 이야기를 다시 해야 한다.
    """
    pick = (JS / "consulting_to_startup.js").read_text(encoding="utf-8")
    # 체크를 다루는 자리(`refresh` · `change` · `pickAll`)에는 새로고침이 없다.
    head = pick.split('button.addEventListener("click"', 1)[0]
    for banned in ("location.reload", "location.href", "location.assign"):
        assert banned not in head, f"고르는 길에 새로고침이 끼었습니다: {banned}"

    table = (JS / "consulting.js").read_text(encoding="utf-8")
    # 칸을 고치는 길(`save`)도 그 칸만 고쳐 적는다.
    save = table.split("function save(", 1)[1].split("\n  }", 1)[0]
    for banned in ("location.reload", "location.href"):
        assert banned not in save, f"칸을 고칠 때 화면을 다시 받습니다: {banned}"

    filters = (JS / "filters.js").read_text(encoding="utf-8")
    assert "replaceState" in filters, "머리글 필터가 주소를 고치는 방식이 바뀌었습니다"
    for banned in ("location.reload", "location.assign", "location.href ="):
        assert banned not in filters, f"머리글 필터가 화면을 다시 받습니다: {banned}"


def test_처음_고르면_저절로_펴진다(sender):
    """닫아 두면 못 쓰는 자리가 하나 생긴다 — 체크 칸은 표 안에 있어 접어도
    보이는데, 접힌 채로는 [보내기] 단추에 닿을 길이 없다.

    동작 자체는 `tests/js/consulting_startup_fold_test.js` 가 실제로 돌려
    본다(손으로 접은 뒤에는 안 건드리는 것까지). 여기서는 화면이 그 장치에
    필요한 것을 실어 보내는지만 본다.
    """
    assert 'id="cs-startup-fold"' in _open(sender)
    js = (JS / "consulting_to_startup.js").read_text(encoding="utf-8")
    assert 'getElementById("cs-startup-fold")' in js
    assert "closedByHand" in js, "사람이 접어 둔 것을 도로 펴고 있습니다"


# --- 5. 화면 코드 -------------------------------------------------------------

def test_화면_코드를_그대로_돌려_본다():
    """`tests/js/consulting_startup_fold_test.js` 가
    consulting_to_startup.js 를 실제로 돌려, 접힌 막대를 고르고 보내는 데까지
    본다. 로컬에서는 `node tests/js/consulting_startup_fold_test.js` 로도 돈다."""
    node = shutil.which("node")
    if not node:
        pytest.skip("node 미설치 — 브라우저 로직 테스트 생략")
    js = ROOT / "tests" / "js" / "consulting_startup_fold_test.js"
    r = subprocess.run([node, str(js)], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr
