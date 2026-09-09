"""투자사 관리 현황을 **이름으로 세운다** — 그 짝이 다 맞아 있는가.

사용자 원문: "투자사 관리현황의 딜 소개 탭의 이름 기준으로 정렬이 필요함."

세우는 일 자체는 브라우저가 하고(`app/static/js/table_sort.js` — 주간 업무가
쓰던 그 부품 그대로다), 그 동작은 `tests/js/contacts_sort_test.js` 가 node 로
직접 돌려 본다. 여기서 보는 것은 **서버가 그려 주는 쪽**이다. 정렬 하나가
서려면 세 곳이 같은 것을 가리켜야 한다.

    <th data-sort="name">이름</th>      머리글이 무엇으로 세울지 선언한다
    <tr data-s-name="…">                 줄이 세울 값을 싣는다
    <script src=".../table_sort.js">     그 선언을 읽는 부품이 화면에 온다

셋 중 하나만 빠져도 **화면은 멀쩡하다.** 머리글은 그대로 서 있고, 눌러도
아무 일이 없거나 아예 눌리지 않는다 — 이 저장소가 필터에서 두 번 당한 부류라
(`tests/test_filter_columns.py` 머리말) 같은 방식으로 막는다.

값은 화면 글자가 아니라 줄에 적어 둔 것을 본다. 이름 칸은 `<b>` 안에 들어
있고 인라인 수정까지 붙어 있어, 화면 글자로 세우면 태그가 하나 늘 때마다
정렬이 조용히 어긋난다.
"""
from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path

from .conftest import DEMO_PASSWORD

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / "app" / "templates"

SHEET = "투자사 30"


def _seed(db, users):
    """이름 칸이 채워진 줄과 **빈 줄**을 함께 둔다.

    빈 이름이 어디로 가는지가 이 화면의 판단 중 하나다(늘 끝). 값이 있는 줄만
    두면 그 줄에 `data-s-name` 이 붙는지 아무도 안 본다.

    이름·회사는 모두 가상이다 — 저장소가 공개다.
    """
    from app.models import VcContact

    u1 = users["u1"]
    db.add_all([
        VcContact(user_id=u1.id, name="이서준", title="심사역",
                  firm="가나벤처스", source_sheet=SHEET),
        VcContact(user_id=u1.id, name="김하늘", title="팀장",
                  firm="다라캐피탈", source_sheet=SHEET),
        # 이름이 비어 있는 줄. 시트에서 회사만 적혀 온 줄이 실제로 있다.
        VcContact(user_id=u1.id, name="", title="",
                  firm="마바인베스트", source_sheet=SHEET),
    ])
    db.commit()


def _page(client, db, users) -> str:
    _seed(db, users)
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    res = client.get("/contacts", params={"sheet": SHEET})
    assert res.status_code == 200, res.status_code
    return res.text


class _Rows(HTMLParser):
    """그려진 표에서 머리글의 `data-sort` 와 줄의 `data-s-*` 를 모은다."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.declared: dict[str, str] = {}      # {키: 머리글 이름}
        self.rows: list[dict] = []
        self._th = ""
        self._label = ""

    def handle_starttag(self, tag: str, attrs) -> None:
        a = dict(attrs)
        if tag == "th" and a.get("data-sort"):
            self._th = a["data-sort"]
            self._label = ""
        elif tag == "tr" and "data-row" in (a.get("class") or ""):
            self.rows.append({k[len("data-s-"):]: v or ""
                              for k, v in a.items() if k.startswith("data-s-")})

    def handle_data(self, data: str) -> None:
        if self._th:
            self._label += data

    def handle_endtag(self, tag: str) -> None:
        if tag == "th" and self._th:
            self.declared[self._th] = self._label.strip()
            self._th = ""


def _read(html: str) -> _Rows:
    parser = _Rows()
    parser.feed(html)
    return parser


def test_이름_머리글이_세울_칸이라고_선언한다(client, db, users):
    """선언이 없으면 머리글은 그냥 글자다 — 눌러도 아무 일이 없다."""
    read = _read(_page(client, db, users))
    assert read.declared.get("name") == "이름", (
        "이름 머리글에 `data-sort=\"name\"` 이 없습니다 — "
        f"지금 선언된 칸: {read.declared}")


def test_줄마다_세울_이름을_싣는다(client, db, users):
    """선언만 하고 안 실으면 머리글만 단추가 되고 아무 줄도 안 움직인다.

    빈 이름인 줄에도 **속성 자체는 있어야 한다.** 없으면 그 줄은 세우는 대상에서
    통째로 빠져(`table_sort.js` 가 `tr[data-s-name]` 으로 고른다) 정렬할 때마다
    제자리에 남는다 — 목록 한가운데에 박힌 줄이 된다.
    """
    read = _read(_page(client, db, users))
    assert len(read.rows) == 3, read.rows
    assert all("name" in r for r in read.rows), (
        "`data-s-name` 이 없는 줄이 있습니다 — 그 줄은 정렬에서 빠집니다: "
        f"{read.rows}")
    assert sorted(r["name"] for r in read.rows) == ["", "김하늘", "이서준"], read.rows


def test_세우는_부품이_화면에_온다(client, db, users):
    """`table_sort.js` 가 안 실리면 선언도 값도 아무도 안 읽는다."""
    html = _page(client, db, users)
    assert re.search(r'src="/static/js/table_sort\.js\?v=[a-f0-9]{8}"', html), (
        "table_sort.js 가 이 화면에 실리지 않습니다")
    # 부품이 **contacts.js 보다 먼저** 와야 한다 — 표를 세우고 NO 를 다시 매기는
    # 일이 contacts.js 안에 있어서, 뒤에 오면 `window.DealflowSort` 가 아직 없다.
    assert html.index("js/table_sort.js") < html.index("js/contacts.js"), (
        "table_sort.js 가 contacts.js 뒤에 실립니다 — 정렬이 걸리지 않습니다")


def test_사람이_눌러_볼_수_있다고_적혀_있다(client, db, users):
    """칸이 스무 개 넘는 표다. 어디를 누르면 세워지는지 화면에 한 줄 없으면
    아무도 머리글을 눌러 보지 않는다."""
    assert "머리글을 눌러 정렬" in _page(client, db, users)


def test_선언한_칸은_반드시_값을_싣는다():
    """**모든 화면**을 훑는다 — 정렬을 붙이는 다음 표까지 같이 지킨다.

    필터가 겪은 것과 같은 어긋남이다(`tests/test_filter_columns.py`).

      · 선언만 하고 안 싣는다  → 머리글만 단추가 되고 아무 줄도 안 움직인다
      · 싣기만 하고 선언이 없다 → 아무도 안 보는 죽은 속성

    반복문으로 머리글을 세우는 표는 값이 실행 때 정해져서 정적으로는 못 읽는다 —
    `{{`·`{%` 가 든 선언은 건너뛴다(다른 화면 검사들과 같은 규칙).
    """
    problems = []
    for path in sorted(TEMPLATES.glob("*.html")):
        text = path.read_text(encoding="utf-8")
        declared = {k for k in re.findall(r'data-sort="([^"{}%]+)"', text)}
        carried = {k for k in re.findall(r'data-s-([\w-]+)=', text)}
        for key in sorted(declared - carried):
            problems.append(f"{path.name}: `{key}` 를 선언만 하고 줄에 안 싣습니다")
        for key in sorted(carried - declared):
            problems.append(f"{path.name}: `{key}` 를 싣기만 하고 머리글이 선언하지 않습니다")
    assert not problems, "\n  ".join([""] + problems)
