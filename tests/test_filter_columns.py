"""표 컬럼 필터가 **그 칸이 보여 주는 값**을 보고 있는가.

필터 하나가 서 있으려면 세 곳이 같은 것을 가리켜야 한다.

    <th data-filters="키:라벨">              머리글이 무엇으로 거를지 선언한다
    <tr data-f-키="값">                      행이 그 값을 싣는다
    <td data-field / data-filter-key>        그 칸이 화면에 보여 주는 값

셋 중 하나만 어긋나도 화면은 멀쩡해 보이는데 필터만 **아무 말 없이** 거짓말을
한다. 실제로 라운드 사이즈 필터가 선호 단계(값이 0개인 다른 칸)를 보고 있어서,
표에는 52줄에 라운드가 적혀 있는데 필터를 열면 늘 빈 목록이었다. 눈으로는
찾을 수 없는 부류라 전 화면을 훑는다.

같은 뿌리에서 나오는 네 가지를 각각 막는다.
  1. 선언만 하고 안 싣는다        → 필터를 열어도 늘 빈 목록
  2. 싣기만 하고 선언이 없다      → 아무도 안 보는 죽은 속성
  3. 선언이 옆 칸의 값을 가리킨다 → 라벨과 다른 것으로 걸러진다 (이번 버그)
  4. 칸이 자기 필터 키를 모른다   → 고쳐 저장해도 필터는 옛 목록 그대로
"""
from __future__ import annotations

import inspect
import re
import shutil
import subprocess
from html.parser import HTMLParser
from pathlib import Path

import pytest

from .conftest import DEMO_PASSWORD

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / "app" / "templates"
JS_DIR = ROOT / "app" / "static" / "js"


# ── 표 읽기 ────────────────────────────────────────────────────────────────
# 머리글을 Jinja 반복문으로 세우는 표(딜 소싱)가 있어 **그린 뒤**에 읽는다.
# 템플릿 글자만 정규식으로 훑으면 그런 표는 통째로 빠진다.

class _TableReader(HTMLParser):
    """표마다 (머리글이 선언한 키 · 행이 싣는 키 · 칸별 필터 키) 를 모은다."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[dict] = []
        self._table: dict | None = None
        self._section = ""
        self._head_done = False
        self._in_row = False
        self._row_done = False

    def handle_starttag(self, tag: str, attrs) -> None:
        a = dict(attrs)
        if tag == "table":
            self._table = {"name": a.get("id") or a.get("class") or "이름 없는 표",
                           "cols": [], "row": set(), "cells": []}
            self.tables.append(self._table)
            self._section = ""
            self._head_done = self._in_row = self._row_done = False
            return
        if self._table is None:
            return
        if tag in ("thead", "tbody"):
            self._section = tag
        elif tag == "th" and self._section == "thead" and not self._head_done:
            self._table["cols"].append(_declared(a.get("data-filters", "")))
        elif tag == "tr":
            if self._section == "thead":
                if self._table["cols"]:
                    self._head_done = True      # 머리글이 두 줄이면 첫 줄만 본다
            elif self._section == "tbody" and not self._row_done:
                keys = {k[len("data-f-"):] for k in a if k.startswith("data-f-")}
                if keys:                        # 값이 없는 안내 행은 건너뛴다
                    self._table["row"] = keys
                    self._table["cells"] = []
                    self._in_row = True
        elif self._in_row:
            if tag == "td":
                self._table["cells"].append(None)
            # 고칠 수 있는 칸은 td 자신일 수도, 그 안의 div 일 수도 있다.
            if "data-field" in a and self._table["cells"] \
                    and self._table["cells"][-1] is None:
                self._table["cells"][-1] = (a.get("data-filter-key")
                                            or a["data-field"])

    def handle_endtag(self, tag: str) -> None:
        if tag == "tr" and self._in_row:
            self._in_row = False
            self._row_done = True               # 한 행만 봐도 짝은 다 드러난다
        elif tag == "thead":
            self._head_done = True
            self._section = ""
        elif tag == "table":
            self._table = None


def _declared(spec: str) -> list[tuple[str, str]]:
    """`"a:라벨A|b:라벨B"` → `[("a", "라벨A"), ("b", "라벨B")]`."""
    out = []
    for part in spec.split("|"):
        if ":" in part:
            key, label = part.split(":", 1)
            out.append((key.strip(), label.strip()))
    return out


def _filter_tables(html: str) -> list[dict]:
    """필터와 상관있는 표만. (안내 문구용 표까지 볼 이유는 없다)"""
    reader = _TableReader()
    reader.feed(html)
    return [t for t in reader.tables
            if any(t["cols"]) or t["row"]]


@pytest.fixture()
def screens(client, db, users):
    """필터가 붙은 네 화면을 **실제로 그려서** 돌려준다.

    이름·번호는 모두 가상이다 — 저장소가 공개다.
    """
    from app.models import IrCompany, SourcingContact, VcContact

    u1 = users["u1"]
    db.add_all([
        VcContact(user_id=u1.id, name="홍길동", title="심사역", firm="가나벤처스",
                  group_name="1군", round_size="10~30억", sectors="AI,헬스케어",
                  interest_level="높음", kakao_joined="O", channel_kakao=1,
                  connect_stage="in_progress", source_sheet="투자사 30",
                  department="투자1본부", phone="01000000009"),
        VcContact(user_id=u1.id, name="김철수", title="팀장", firm="다라인베스트",
                  connect_stage="not_started", source_sheet="투자사 30"),
        IrCompany(name="샘플애그", sector_major="애그테크", sector_minor="스마트팜",
                  series="Seed", contract_status="free", is_top_deal=1,
                  one_liner="스마트팜 관제", ir_drive_url="https://example.com/ir"),
        SourcingContact(bucket="시리즈 A 이상", position=0, name="박영희",
                        title="심사역", firm="마바캐피탈", assignee_name="강민준",
                        sectors="AI", round_size="10~30억"),
    ])
    db.commit()
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    return {
        "투자사 관리 현황": client.get("/contacts?sheet=all").text,
        "IR 기업현황": client.get("/companies").text,
        "스타트업DB": client.get("/companies?tab=db").text,
        "딜 소싱": client.get("/sourcing").text,
    }


def _each_table(screens: dict):
    for page, html in screens.items():
        for table in _filter_tables(html):
            yield page, table


# ── 1. 선언 → 행 ───────────────────────────────────────────────────────────

def test_선언만_하고_값을_안_실으면_필터_칩이_아예_안_뜬다(screens):
    """머리글이 `data-filters="키:…"` 로 선언한 키는 행이 반드시 실어야 한다.

    행에 `data-f-키` 가 없으면 필터는 모든 행을 "(비어 있음)" 으로 읽는다 —
    고를 값이 하나도 없는 빈 목록이 뜨고, 왜 비었는지는 화면 어디에도 안 나온다.
    """
    missing = []
    for page, table in _each_table(screens):
        for keys in table["cols"]:
            for key, label in keys:
                if key not in table["row"]:
                    missing.append(
                        f"{page} · [{label}] 필터는 data-f-{key} 를 보는데 "
                        f"행이 싣는 것은 {sorted(table['row'])}")
    assert not missing, (
        "선언한 키를 행이 싣지 않습니다 — 그 필터는 열어도 늘 빈 목록입니다.\n  "
        + "\n  ".join(missing))


# ── 2. 행 → 선언 ───────────────────────────────────────────────────────────

def test_싣기만_하고_선언이_없는_값은_아무도_안_보는_죽은_속성이다(screens):
    """행이 실은 `data-f-*` 를 아무 머리글도 선언하지 않으면 걸 곳이 없다.

    해롭지는 않지만, 있는 줄 알고 다른 화면에서 `?키=값` 으로 링크를 걸면
    그 쿼리가 조용히 버려진다(대시보드의 `연결 진행 중인 명단` 이 그랬다).
    """
    orphans = []
    for page, table in _each_table(screens):
        declared = {k for keys in table["cols"] for k, _ in keys}
        for key in sorted(table["row"] - declared):
            orphans.append(f"{page} · data-f-{key} 를 선언한 머리글이 없다")
    assert not orphans, (
        "행만 값을 싣고 있습니다 — 거는 곳이 없으면 지우거나, 칸을 세우고 "
        "머리글에 선언하세요.\n  " + "\n  ".join(orphans))


# ── 3. 선언 ↔ 그 칸이 보여 주는 필드 (이번 버그) ─────────────────────────────

def test_필터는_옆_칸이_아니라_그_칸이_보여_주는_값을_본다(screens):
    """같은 자리의 `<th>` 와 `<td>` 가 다른 필드를 가리키면 안 된다.

    라운드 사이즈 머리글이 `stage`(선호 단계)를 선언해 두었다. 칸에는 라운드가
    52줄 적혀 있는데 선호 단계는 0줄이라, 표에는 보이는 값이 필터에는 없었다.
    라벨·칸·필터가 셋 다 같은 것을 가리켜야 필터가 사람이 본 것을 거른다.
    """
    crossed = []
    for page, table in _each_table(screens):
        for i, keys in enumerate(table["cols"]):
            if not keys or i >= len(table["cells"]):
                continue
            cell_key = table["cells"][i]
            if cell_key is None:
                continue        # 고칠 수 없는 칸(뱃지·링크)은 대조할 필드가 없다
            if cell_key not in {k for k, _ in keys}:
                labels = " · ".join(f"{k}({lb})" for k, lb in keys)
                crossed.append(
                    f"{page} · {i + 1}번째 칸: 머리글은 {labels} 로 거르는데 "
                    f"칸이 보여 주는 값은 {cell_key} 다")
    assert not crossed, (
        "필터가 그 칸이 아닌 다른 필드를 보고 있습니다 — 라벨은 맞는데 결과가 "
        "다른, 눈으로는 못 찾는 부류입니다.\n  " + "\n  ".join(crossed))


# ── 4. 칸 → 행 (고친 값이 필터에 나오는 한 바퀴) ────────────────────────────

def test_칸이_자기_필터_키를_모르면_고쳐도_필터는_옛_목록_그대로다(screens):
    """고칠 수 있는 칸은 행의 어느 `data-f-*` 를 같이 고칠지 알아야 한다.

    `inline_edit.js` 는 저장 뒤 `data-filter-key || data-field` 이름으로 행을
    고친다. 칸 이름(DB 컬럼)과 필터 키가 다른데 `data-filter-key` 가 없으면
    그 이름의 속성이 행에 없어 아무 일도 일어나지 않는다 —
    **관심도를 채워 넣어도 필터는 계속 비어 있었다.**
    """
    deaf = []
    for page, table in _each_table(screens):
        for i, keys in enumerate(table["cols"]):
            if not keys or i >= len(table["cells"]):
                continue
            cell_key = table["cells"][i]
            if cell_key is None:
                continue
            if cell_key not in table["row"]:
                deaf.append(f"{page} · {i + 1}번째 칸이 고치려는 data-f-{cell_key} "
                            f"가 행에 없다")
    assert not deaf, (
        "칸을 고쳐도 행 값이 안 바뀝니다 — 칸에 data-filter-key 를 주거나 "
        "행이 그 이름으로 값을 싣게 하세요.\n  " + "\n  ".join(deaf))


# ── 5. 다른 화면에서 걸어 오는 링크 ────────────────────────────────────────

def _query_keys(text: str, path: str) -> set:
    """`href="/contacts?sheet=all&connect=…"` 에서 쿼리 **이름**만 추린다."""
    keys = set()
    for query in re.findall(re.escape(path) + r"\?([^\"'\s>]*)", text):
        for pair in query.split("&"):
            name = pair.split("=")[0].strip()
            if name and name.isidentifier():
                keys.add(name)
    return keys


def test_다른_화면이_거는_필터_링크는_그_표가_아는_키여야_한다(screens):
    """`/contacts?connect=진행 중` 처럼 눌러 오는 링크는 선언된 키여야 한다.

    `filters.js` 는 **선언된 키가 아닌 쿼리는 버린다.** 그래서 대시보드의
    `연결 진행 중인 명단` 을 눌러도 306명이 그대로 나왔다 — 링크는 살아 있고
    화면도 열리니 아무도 눈치채지 못한다.
    """
    from app.routers import pages

    contacts = _filter_tables(screens["투자사 관리 현황"])
    declared = {k for t in contacts for keys in t["cols"] for k, _ in keys}
    # 서버가 직접 읽는 값(명단 탭·참고 자료·바로 열 담당자)은 필터가 아니다.
    served = set(inspect.signature(pages.contacts_page).parameters)

    linked = set()
    for path in sorted(TEMPLATES.glob("*.html")) + sorted(JS_DIR.glob("*.js")):
        linked |= _query_keys(path.read_text(encoding="utf-8"), "/contacts")
    # 빠른 필터 칩(프리셋)도 같은 쿼리 문법을 쓴다.
    for preset in re.findall(r'data-preset="([^"]*)"',
                             screens["투자사 관리 현황"]):
        linked |= {p.split("=")[0] for p in preset.split("&") if p}

    dangling = sorted(k for k in linked - served - declared if k)
    assert not dangling, (
        "투자사 관리 현황이 모르는 키로 링크가 걸려 있습니다 — 눌러도 아무것도 "
        f"안 걸러집니다: {dangling}\n"
        f"(그 표가 아는 키: {sorted(declared)})")


# ── 6. 고친 값 → 필터 목록 (브라우저 쪽 한 바퀴) ────────────────────────────

@pytest.mark.skipif(shutil.which("node") is None,
                    reason="node 미설치 — 브라우저 로직 테스트 생략")
def test_저장에서_필터_목록까지_한_바퀴가_이어져_있다():
    """저장 → 행에 적기 → 다시 읽기 → 목록에 등장, 네 고리가 다 이어져야 한다.

    한 고리만 끊겨도 증상은 똑같다 — 값은 화면에 보이는데 필터에는 없다.
    딜 소싱은 `inline-saved` 를 듣는 화면이 없어 refresh 가 영영 안 불렸고,
    투자사 관리 현황은 칸이 자기 필터 키를 몰라 행이 안 바뀌었다.
    """
    script = Path(__file__).resolve().parent / "js" / "filter_loop_test.js"
    out = subprocess.run([shutil.which("node"), str(script)],
                         capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stdout + out.stderr
