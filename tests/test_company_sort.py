"""IR 기업 현황을 **머리글을 눌러 세운다** — 그 짝이 다 맞아 있는가.

사용자 요청은 「수정한 날짜 기준 정렬」이었고, 세울 범위는 **날짜·숫자 칸
전부**로 정해졌다. 이 탭에서 거기 드는 칸은 셋이다.

    `수정한 날짜`(`updated`) · `소개 횟수`(`sent`) · `미팅제공일자`(`meeting`)

세우는 일 자체는 브라우저가 하고(`app/static/js/table_sort.js` — 주간 업무·투자사
명단이 쓰던 그 부품 그대로다), 그 동작은 `tests/js/company_sort_test.js` 가 node
로 직접 돌려 본다. 여기서 보는 것은 **서버가 그려 주는 쪽**이다. 정렬 하나가
서려면 세 곳이 같은 것을 가리켜야 한다.

    <th data-sort="updated">수정한 날짜</th>   머리글이 무엇으로 세울지 선언한다
    <tr data-s-updated="…">                    줄이 세울 값을 싣는다
    <script src=".../table_sort.js">           그 선언을 읽는 부품이 화면에 온다

셋 중 하나만 빠져도 **화면은 멀쩡하다.** 머리글은 그대로 서 있고, 눌러도 아무
일이 없거나 아예 눌리지 않는다 — 이 저장소가 필터에서 두 번 당한 부류라
(`tests/test_filter_columns.py` 머리말) 같은 방식으로 막는다. 선언↔싣기의 짝
자체는 `tests/test_contacts_sort.py` 가 **모든 화면**을 훑어 지키고, 여기서는
이 표만의 판단들을 못 박는다.

  · 세울 값은 **화면 글자가 아니다.** `소개 횟수` 는 `6회 · 180건` 으로 그려지고
    `수정한 날짜` 는 `<td>` 안에 얹혀 있다.
  · 세우는 칸은 **필터가 없는 칸들**이다. 이 표의 머리글 폭은 전부 "필터를 건
    뒤의 머리글" 에 맞춘 최소값이라, 한 머리글에 단추가 둘 서면 두 줄로 접힌다.
  · `NO` 에는 **안 붙인다.** 이 표의 `NO` 는 시트 번호가 아니라 보이는 것 기준
    1,2,3… 이라(`companies.js` 의 `renumber`) 차례가 곧 번호다 — 그것으로 세우면
    아무 일도 안 일어난다.

값은 전부 가상값이다 — 저장소가 공개다.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "app" / "templates" / "companies.html"
SCRIPT = ROOT / "app" / "static" / "js" / "companies.js"

# 머리글 이름 → 세울 값의 이름(`data-sort` / `data-s-*`)
SORTED_COLUMNS = {
    "수정한 날짜": "updated",
    "소개 횟수": "sent",
    "미팅제공일자": "meeting",
}

# 일부러 안 세우는 칸들. **글자 칸**이라 가나다순의 쓸모가 적고, 거의 다 필터
# 단추가 이미 서 있어 꼬리표를 더하면 머리글이 두 줄로 접힌다.
UNSORTED_COLUMNS = ["NO", "기업명", "사업분야 대분류", "소분류", "기업구분",
                    "딜 소개 문구", "담당자", "계약여부", "계약서 수신 여부",
                    "홍보메일삭제", "핵심/TOP Deal", "IR 자료"]


def _tables() -> list:
    """이 화면의 `<table>` 들 — Jinja 주석은 먼저 지운다.

    주석에 `<th>` 나 `data-sort` 를 적어 두는 일이 잦은 파일이라, 안 지우면
    설명하려고 적은 글자를 마크업으로 세게 된다(tests/test_ui_layout.py 와
    같은 이유다).
    """
    text = re.sub(r"\{#.*?#\}", "", TEMPLATE.read_text(encoding="utf-8"), flags=re.S)
    return re.findall(r"<table\b.*?</table>", text, re.S)


def _status_tab_markup() -> str:
    """IR 기업 현황(기본) 탭의 표. 두 탭이 같은 id 를 쓰므로 **두 번째**다."""
    tables = _tables()
    assert len(tables) >= 2, "표가 둘보다 적습니다 — 화면 구조가 바뀌었습니다"
    markup = tables[1]
    assert "수정한 날짜" in markup, "두 번째 표가 IR 기업 현황 탭이 아닙니다"
    return markup


def _heads(markup: str) -> list:
    """머리글 하나하나 — `(속성들, 이름)`."""
    out = []
    for attrs, inner in re.findall(r"<th\b([^>]*)>(.*?)</th>", markup, re.S):
        name = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", inner)).strip()
        out.append((attrs, name))
    return out


# ── ① 어느 칸을 세우는가 ────────────────────────────────────────────────────

@pytest.mark.parametrize("column,key", sorted(SORTED_COLUMNS.items()))
def test_날짜_숫자_칸이_선언한다(column, key):
    """머리글이 무엇으로 세울지 선언하지 않으면 눌러도 단추조차 안 선다."""
    for attrs, name in _heads(_status_tab_markup()):
        if name == column:
            assert f'data-sort="{key}"' in attrs, (
                f"`{column}` 머리글에 `data-sort=\"{key}\"` 가 없습니다: {attrs}")
            return
    pytest.fail(f"`{column}` 머리글을 못 찾았습니다")


@pytest.mark.parametrize("column", UNSORTED_COLUMNS)
def test_글자_칸에는_안_붙인다(column):
    """가나다순은 이 표에서 쓸모가 적고, **머리글이 좁다.**

    이름으로 찾는 길은 이미 검색창이고 갈래로 좁히는 길은 이미 머리글 필터다.
    그런데 이 표의 칸 폭은 전부 "필터를 건 뒤의 머리글"(`계약여부 (1) ▾`)에
    맞춘 최소값이라(tests/test_ui_layout.py 가 그 자로 잰다), 거기에 정렬
    꼬리표(` ▲`)까지 더하면 `사업분야 대분류 (1) ▾ ▲` 가 되어 두 줄로 접힌다 —
    머리행이 접히면 표를 아래로 밀어내 첫 줄이 화면 밖으로 나간다.
    """
    for attrs, name in _heads(_status_tab_markup()):
        if name == column:
            assert "data-sort" not in attrs, (
                f"`{column}` 은 이번 범위(날짜·숫자)가 아닙니다: {attrs}")
            return
    pytest.fail(f"`{column}` 머리글을 못 찾았습니다")


def test_한_머리글에_단추가_둘_서지_않는다():
    """정렬을 붙인 셋은 **필터가 없는 칸들**이다.

    셋 다 값이 줄마다 다른 시각·수·날짜라 애초에 목록으로 고를 것이 아니어서
    필터를 안 세웠다. 덕분에 폭을 다시 잴 일이 없다 — 정렬 꼬리표만 더해진다.
    """
    both = [name for attrs, name in _heads(_status_tab_markup())
            if "data-sort=" in attrs and "data-filters=" in attrs]
    assert not both, (
        "한 머리글에 필터 단추와 정렬 단추가 함께 섰습니다: " + ", ".join(both))


def test_NO_에는_안_붙인다():
    """이 표의 `NO` 는 **보이는 것 기준 1,2,3…** 이다 — 차례가 곧 번호다.

    칸은 빈 채로 그려지고 `companies.js` 의 `renumber` 가 채운다. 값이 아니라
    지금 서 있는 차례 그 자체라, 그것으로 세우면 아무 일도 안 일어난다(세우고
    다시 매기면 또 1,2,3… 이다). 서버가 그려 준 차례로 돌아가는 길은 이미
    있다 — 같은 머리글을 세 번째 누르면 꺼진다.
    """
    markup = _status_tab_markup()
    body = re.search(r"<tbody>(.*?)</tbody>", markup, re.S).group(1)
    rowno = re.search(r'<td class="rowno[^"]*"[^>]*>(.*?)</td>', body, re.S)
    assert rowno, "`NO` 칸을 못 찾았습니다"
    assert not rowno.group(1).strip(), (
        "`NO` 칸에 값이 그려지고 있습니다 — 그렇다면 세울 수 있는 값입니다")
    assert "renumber" in SCRIPT.read_text(encoding="utf-8"), (
        "`NO` 를 다시 매기는 자리가 없어졌습니다")


# ── ② 세울 값 ───────────────────────────────────────────────────────────────

def test_줄이_세울_값을_싣는다():
    markup = _status_tab_markup()
    row = re.search(r"<tr\b[^>]*data-id=[^>]*>", markup, re.S).group(0)
    for column, key in sorted(SORTED_COLUMNS.items()):
        assert f"data-s-{key}=" in row, (
            f"`{column}` 을 선언만 하고 줄에 안 싣습니다 — "
            "머리글이 단추로 서기만 하고 아무 줄도 안 움직입니다")


def test_수정한_날짜는_화면에_뜨는_그_값을_싣는다(logged_in, db, users):
    """세울 값과 보이는 글자가 **같은 한 곳**(`clock.stamp_text`)에서 온다.

    `YYYY-MM-DD HH:MM:SS` 는 자릿수가 늘 같아 글자 차례가 곧 시각 차례다 —
    `8/7(금)` 처럼 바로잡을 것이 없다. 원본 저장값(`…T…+09:00`)을 따로 싣지
    않는 이유는 `companies.html` 의 그 `<tr>` 주석에 적어 두었다(오프셋은
    구분하는 것이 없고, 옛 값에는 `+00:00` 이 섞여 있다).
    """
    from app.models import IrCompany

    db.add(IrCompany(name="샘플가온헬스", owner_user_id=users["u1"].id))
    db.commit()
    html = logged_in.get("/companies").text

    row = re.search(r'<tr data-id="\d+"[^>]*>', html, re.S).group(0)
    value = re.search(r'data-s-updated="([^"]*)"', row).group(1)
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", value), (
        f"세울 값이 시분초까지의 그 꼴이 아닙니다: {value!r}")
    assert f'<td class="updated-at muted"' in html or 'class="updated-at' in html
    assert f">{value}</td>" in html, (
        "줄에 실은 세울 값과 칸에 그린 글자가 다릅니다 — 둘은 한 곳에서 와야 합니다")


def test_소개_횟수는_회차_수로_센다(logged_in, db, users):
    """화면은 `6회 · 180건` 이지만 세우는 것은 **앞의 수**다.

    칸 이름이 곧 그 수이고 화면에서도 굵게 서 있는 쪽이다. `건수` 로 세우면
    이름과 세우는 값이 달라져, `소개 횟수` 내림차순에서 `3회 · 200건` 이
    `9회 · 180건` 보다 위에 선다.

    **한 번도 안 나간 기업은 `0` 이다**(빈 값이 아니다). 화면의 `–` 는 '못
    읽었다' 가 아니라 영 회라는 뜻이고, 그래야 오름차순 맨 위에 "아직 한 번도
    안 나간 곳" 이 모인다 — 빈 값으로 실으면 그 줄들이 방향과 상관없이 늘 끝으로
    밀려 정작 찾고 싶을 때 찾을 수가 없다(`table_sort.js` 의 `order`).
    """
    from app.models import IrCompany

    db.add(IrCompany(name="샘플나루랩스", owner_user_id=users["u1"].id))
    db.commit()
    html = logged_in.get("/companies").text
    row = re.search(r'<tr data-id="\d+"[^>]*>', html, re.S).group(0)
    assert re.search(r'data-s-sent="0"', row), (
        f"한 번도 안 나간 줄의 세울 값이 `0` 이 아닙니다: {row}")


def test_소개_횟수의_세울_값은_늘_수다():
    """템플릿이 싣는 것이 `sent_rounds` 인가 — 글자가 섞이면 정렬이 글자순이 된다."""
    row = re.search(r"<tr\b[^>]*data-id=[^>]*>", _status_tab_markup(), re.S).group(0)
    assert 'data-s-sent="{{ r.sent_rounds }}"' in row, (
        "`소개 횟수` 의 세울 값이 회차 수(`sent_rounds`)가 아닙니다: " + row)


# ── ③ 미팅제공일자 — 날짜로 적힌 것만 ───────────────────────────────────────

@pytest.mark.parametrize("text,want", [
    ("2026-09-15", "2026-09-15"),
    ("2026-09-15 (확정)", "2026-09-15"),
    ("확정: 2026-09-15", "2026-09-15"),
    # 손으로 적는 칸이라 실제로 들어오는 말들. 날짜가 아니면 빈 값이다.
    ("9월 중", ""),
    ("10월 중", ""),
    ("미정", ""),
    ("", ""),
    (None, ""),
])
def test_미팅제공일자는_날짜로_적힌_것만_세운다(text, want):
    """글자 그대로 세우면 두 가지가 한꺼번에 어긋난다.

    · `10월 중` 이 `9월 중` 보다 **앞**에 선다(글자로는 `1` < `9`) —
      `table_sort.js` 머리글이 `8/7(금)` 을 들어 경고하는 바로 그것이다.
    · 내림차순에서 `미정` 이 **맨 위**로 올라온다(한글이 숫자보다 크다).
      가장 나중 날짜를 보려고 세웠는데 날짜 없는 줄부터 읽게 된다 —
      `sort_for_tab` 이 `수신일` 에서 겪은 그대로다.

    그래서 날짜가 안 보이는 글자는 빈 값이 되고, 빈 값은 `table_sort.js` 가
    방향과 상관없이 늘 끝에 둔다.
    """
    from app.routers.companies import meeting_sort_key

    assert meeting_sort_key(text) == want


def test_미팅제공일자의_세울_값은_서버가_추린다(logged_in, db, users):
    """추리는 규칙은 **서버 한 곳**이다(`meeting_sort_key`).

    화면에도 적으면 두 벌이 되어 한쪽만 고쳐지는 날이 온다.
    """
    from app.models import IrCompany

    db.add(IrCompany(name="샘플다온소재", owner_user_id=users["u1"].id,
                     meeting_offered_at="9월 중"))
    db.commit()
    html = logged_in.get("/companies").text
    row = re.search(r'<tr data-id="\d+"[^>]*>', html, re.S).group(0)
    assert 'data-s-meeting=""' in row, (
        f"날짜가 아닌 글자가 세울 값으로 그대로 실렸습니다: {row}")
    assert ">9월 중</td>" in html, "화면 글자까지 지워졌습니다 — 그것은 그대로여야 합니다"


def test_고친_뒤에도_세울_값이_따라온다(logged_in, db, users):
    """표에서 눌러 고치는 칸이라 **응답이 새 세울 값을 실어 줘야** 한다.

    브라우저는 날짜를 추리는 규칙을 모른다(알게 하면 규칙이 두 벌이 된다).
    안 실으면 고친 줄이 옛 날짜 자리에 그대로 선다 — `updated_at` 과 같은 짝이다.
    """
    from app.models import IrCompany

    row = IrCompany(name="샘플라온바이오", owner_user_id=users["u1"].id)
    db.add(row)
    db.commit()

    res = logged_in.patch(f"/api/companies/{row.id}",
                          json={"meeting_offered_at": "2026-10-01 오후"})
    assert res.status_code == 200, res.text
    assert res.json()["meeting_sort"] == "2026-10-01", res.json()
    assert res.json()["updated_at"], "고친 시각도 함께 와야 합니다"


# ── ④ 부품이 화면에 온다 ────────────────────────────────────────────────────

def test_정렬기가_companies_js_보다_먼저_실린다():
    """뒤에 오면 `window.DealflowSort` 가 아직 없어 **아무 일도 안 일어난다.**

    거는 자리가 `companies.js` 안인 이유는 그 파일 주석에 적어 두었다 —
    표를 세우는 일과 `NO` 를 다시 매기는 일이 한 짝이라서다.
    """
    text = TEMPLATE.read_text(encoding="utf-8")
    sorter = text.find("js/table_sort.js")
    screen = text.find("js/companies.js")
    assert sorter > 0, "`table_sort.js` 를 안 부릅니다 — 머리글이 눌리지 않습니다"
    assert sorter < screen, (
        "`table_sort.js` 가 `companies.js` 보다 뒤에 있습니다 — "
        "`window.DealflowSort` 가 아직 없어 정렬이 통째로 안 걸립니다")


def test_정렬을_NO_다시_매기기와_한_자리에_건다():
    """두 파일로 갈라 두면 다음 사람이 정렬만 옮기는 날 번호가 옛 자리에 남는다."""
    text = SCRIPT.read_text(encoding="utf-8")
    assert "DealflowSort.init" in text, "`companies.js` 가 정렬을 안 겁니다"
    assert re.search(r"DealflowSort\.init\(\{[^}]*onChange:\s*renumber", text, re.S), (
        "세우고 나서 `NO` 를 다시 매기지 않습니다 — 번호가 `3,5,1,4,2` 로 남습니다")


# ── ⑤ 옆 탭 ─────────────────────────────────────────────────────────────────

def test_스타트업DB_탭은_안_건드린다():
    """요청은 `IR 기업 현황` 탭 하나였다.

    (그 탭에도 날짜·숫자 칸이 많지만 — `수신일`·연도별 매출·금액 셋 — 이번
     범위가 아니다. 붙일지는 따로 정한다.)
    """
    db_tab = _tables()[0]
    assert "data-sort=" not in db_tab, "스타트업DB 탭에도 정렬이 들어갔습니다"
    assert "data-s-" not in db_tab, "스타트업DB 탭에도 세울 값이 들어갔습니다"


# ── ⑥ 브라우저 ──────────────────────────────────────────────────────────────

@pytest.mark.skipif(shutil.which("node") is None,
                    reason="node 미설치 — 브라우저 로직 테스트 생략")
def test_세우는_일은_브라우저에_있으니_거기서_잰다():
    """머리글을 눌렀을 때 실제로 어떤 차례가 서는지는 **파일을 그대로 돌려서** 본다.

    파이썬으로는 선언과 값이 있는지까지만 볼 수 있다. `10회` 가 `2회` 뒤에
    서는지, 날짜 아닌 글자가 늘 끝인지, 걸어 둔 필터가 안 풀리는지, 한 줄 고친
    뒤에도 차례가 남는지는 브라우저 코드를 돌려야 보인다
    (tests/js/company_sort_test.js). 로컬에서는
    `node tests/js/company_sort_test.js` 로도 돈다.
    """
    script = ROOT / "tests" / "js" / "company_sort_test.js"
    out = subprocess.run([shutil.which("node"), str(script)],
                         capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stdout + out.stderr
