"""수정창(우측 슬라이드 상세 패널)은 **모달**이다 — 뒷막 · Escape · 미저장 확인.

## 왜 이 검사가 있나

투자사 관리 현황(`/contacts` · `/startup`)의 수정창은 뒷막 없이 표 위에 얹혀
있었다. 그래서 두 가지가 함께 났다.

**겹친다.** 창은 `z-index:40`, 칸 위에 뜨는 편집창(`.cell-pop`)은 `z-index:60`
이라 팝오버가 늘 창 위에 그려졌다. 자리잡기상 팝오버의 오른쪽 끝이 화면 끝
28px 앞이라 420px 짜리 창과 최대 392px 이 겹쳤다 — 본문을 밀어 주는 규칙은
CSS 에 없다.

**써 놓은 값이 조용히 사라진다.** 같은 칸 열한 개를 창과 표가 서로 다른 시점에
저장한다. 표는 칸 하나를 누르는 즉시 PATCH 하고, 창은 [저장] 때 폼 전체를
보낸다. 창을 열어 둔 채 표에서 고치고 [저장]을 누르면 옛 값으로 되돌아갔다.

고침은 **뒷막**이다. 창이 열려 있는 동안 표를 덮으면 칸을 누를 수 없어 팝오버가
뜰 일 자체가 없어진다 — 겹침이 원인에서 사라지고, 두 자리가 같은 칸을 다투는
일도 없어진다.

## 여기서 보는 것

눌러 보는 일은 브라우저 쪽 검사가 한다(tests/js/detail_panel_modal_test.js ·
tests/js/cell_pop_close_test.js). 여기서는 **그것이 화면에 닿는 길**을 지킨다:
화면이 뒷막을 그리는지, 부품이 두 화면에 실리는지, 그리고 뒷막이 CSS 에서
정말 표를 덮고 창 아래에 서는지.
"""
from __future__ import annotations

import pathlib
import re
import shutil
import subprocess

import pytest

CSS = pathlib.Path("app/static/css/app.css")
CONTACTS_HTML = pathlib.Path("app/templates/contacts.html")
COMPANIES_HTML = pathlib.Path("app/templates/companies.html")

JS_DIR = pathlib.Path(__file__).resolve().parent / "js"
MODAL_TEST = JS_DIR / "detail_panel_modal_test.js"
CELL_POP_TEST = JS_DIR / "cell_pop_close_test.js"


def _css() -> str:
    """주석을 지운 CSS. 안 지우면 규칙 바로 위의 설명이 선택자에 딸려 온다."""
    return re.sub(r"/\*.*?\*/", "", CSS.read_text(encoding="utf-8"), flags=re.S)


def _rule(css: str, selector: str) -> str:
    """`선택자 { … }` 한 덩어리의 본체. 선택자가 정확히 그것인 규칙만 본다."""
    for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", css):
        if m.group(1).strip() == selector:
            return m.group(2)
    raise AssertionError(f"CSS 에 `{selector}` 규칙이 없다")


def _z(css: str, selector: str) -> int:
    hit = re.search(r"z-index:\s*(-?\d+)", _rule(css, selector))
    assert hit, f"`{selector}` 에 z-index 가 없다"
    return int(hit.group(1))


# ── 브라우저 쪽 검사 ────────────────────────────────────────────────────────
#
# 로직이 브라우저에 있으므로 검사도 같은 언어로 둔다(tests/test_contacts_js.py 와
# 같은 방식). node 가 없는 환경(운영 도커 이미지)에서는 건너뛴다 — 브라우저 자산
# 검사라 서버를 띄우는 데 필요한 의존성이 아니다.


@pytest.mark.skipif(shutil.which("node") is None, reason="node 미설치 — 브라우저 로직 테스트 생략")
def test_수정창이_모달로_서고_적던_값을_확인_없이_버리지_않는가():
    """창이 열리면 뒷막이 서고, 고친 폼은 확인 없이 사라지지 않는다.

    닫는 길이 셋이다(뒷막 · Escape · [닫기 ✕]). 확인이 그중 하나에만 걸려
    있으면 나머지 둘로 값이 샌다. 표의 다른 줄을 누르는 길도 폼을 통째로
    갈아 끼우므로 같은 확인을 거쳐야 한다.

    딜 기업 DB 도 **같은 부품**을 쓴다 — 거기 있던 '뒷막을 누르면 적던 값이
    그대로 사라진다' 는 결함이 함께 고쳐졌는지도 여기서 본다.

    로컬에서는 `node tests/js/detail_panel_modal_test.js` 로도 돈다.
    """
    result = subprocess.run(
        [shutil.which("node"), str(MODAL_TEST)], capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.skipif(shutil.which("node") is None, reason="node 미설치 — 브라우저 로직 테스트 생략")
def test_칸_편집창은_바깥을_눌렀을_때만_닫히는가():
    """창의 여백·보기 목록을 눌러도 창이 저장되며 닫히면 안 된다.

    닫는 자리가 입력칸의 `blur` 하나였다. 그래서 창 안이라도 초점이 빠지기만
    하면 닫혔다 — 고를 것을 보려고 목록(`.cell-pop-choices`, 132px 에서 스크롤)을
    내리다 창이 사라졌다.

    안내 딱지(`.cell-hint`)는 **바깥**으로 정했다. 그것은 창의 일부가 아니라
    다른 칸의 손잡이라 누르면 지금 창이 끝나고 그 칸이 열려야 한다 — 빈 칸은
    글자가 없어 누를 자리가 그 딱지뿐이다.

    로컬에서는 `node tests/js/cell_pop_close_test.js` 로도 돈다.
    """
    result = subprocess.run(
        [shutil.which("node"), str(CELL_POP_TEST)], capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr


# ── 화면에 닿는 길 ──────────────────────────────────────────────────────────


def test_수정창_앞에_뒷막이_그려지는가():
    """화면이 뒷막을 안 그리면 부품이 세울 것이 없다 — 예전 그대로다."""
    html = CONTACTS_HTML.read_text(encoding="utf-8")
    hit = re.search(r'<div class="([^"]*)" id="detail-backdrop" hidden>', html)
    assert hit, "contacts.html 에 `#detail-backdrop` 이 없다 ★ 뒷막 없이 창만 뜬다"
    assert "panel-backdrop" in hit.group(1).split(), (
        "뒷막이 딜 기업 DB 와 같은 `.panel-backdrop` 이 아니다 — 뒷막 모양이 두 벌이 된다"
    )
    assert html.index('id="detail-backdrop"') < html.index('id="detail-panel"'), (
        "뒷막이 창보다 뒤에 그려진다 — 쌓임 차례가 z-index 와 어긋나 보기 어려워진다"
    )


def test_여닫는_부품이_두_화면에_같이_실리는가():
    """부품이 화면 스크립트보다 **먼저** 와야 한다 — 뒤면 `window.PanelModal` 이 없다."""
    for html_path, own in ((CONTACTS_HTML, "js/contacts.js"), (COMPANIES_HTML, "js/companies.js")):
        html = html_path.read_text(encoding="utf-8")
        assert "js/panel_modal.js" in html, (
            f"{html_path.name} 이 여닫는 공통 부품을 안 부른다 ★ 창이 통째로 안 붙는다"
        )
        assert html.index("js/panel_modal.js") < html.index(own), (
            f"{html_path.name}: 부품이 {own} 보다 뒤에 온다 — 부를 때 아직 없다"
        )


def test_두_화면이_같은_부품_하나만_쓰는가():
    """여닫는 판단이 화면마다 한 벌씩 생기면 반드시 한쪽이 낡는다.

    이 저장소가 되풀이한 사고다 — 딜 기업 DB 에는 뒷막이 있었고 투자사 관리
    현황에는 없었으며, 있던 쪽은 뒷막을 누르면 값을 그냥 버렸다.
    """
    modal = pathlib.Path("app/static/js/panel_modal.js")
    assert modal.exists(), "여닫는 공통 부품 파일이 없다"
    for name in ("contacts.js", "companies.js"):
        src = pathlib.Path("app/static/js") / name
        code = re.sub(r"//[^\n]*", "", src.read_text(encoding="utf-8"))
        assert "PanelModal.init(" in code, f"{name} 이 공통 부품을 안 쓴다"
        assert '"Escape"' not in code, (
            f"{name} 이 Escape 를 직접 듣는다 ★ 닫는 판단이 두 벌이다"
        )


def test_뒷막이_표를_덮고_창_아래에_서는가():
    """층위가 이 고침의 전부다.

    · 뒷막이 창보다 위면 창의 칸을 못 누른다.
    · 뒷막이 표·필터 패널보다 아래면 표의 칸을 그대로 누를 수 있어, 막으려던
      팝오버가 다시 창 위에 겹친다.
    """
    css = _css()
    backdrop = _rule(css, ".panel-backdrop")
    assert "position: fixed" in backdrop, "뒷막이 고정이 아니면 표를 따라 스크롤된다"
    assert "inset: 0" in backdrop, "뒷막이 화면 전체를 안 덮으면 옆으로 새어 칸이 눌린다"

    z_backdrop = _z(css, ".panel-backdrop")
    z_panel = _z(css, ".detail-panel")
    assert z_backdrop < z_panel, "뒷막이 창을 덮는다 — 창의 칸을 못 누른다"

    # 뒷막 밑에 깔려야 하는 것들. 표 머리글(sticky)과 컬럼 필터 패널이 그것이다.
    for selector in (".table-wrap.wide thead th", ".filter-panel"):
        assert _z(css, selector) < z_backdrop, (
            f"`{selector}` 이 뒷막 위로 올라온다 — 창이 열려 있어도 눌린다"
        )


def test_팝오버는_z_index_로는_못_이긴다는_것을_적어_둔다():
    """`.cell-pop` 은 창보다 위다 — **그래서** 뒷막이 필요하다.

    다음 사람이 "z-index 만 손보면 되겠네" 하고 뒷막을 떼는 것을 여기서 막는다.
    팝오버를 창 밑으로 내리면 이번에는 표에서 칸을 고칠 때 그 창이 상세 패널
    뒤로 숨는다 — 어느 쪽으로 정해도 층위만으로는 안 풀린다.
    """
    css = _css()
    assert _z(css, ".cell-pop") > _z(css, ".detail-panel"), (
        "팝오버가 창 아래로 내려갔다 — 표에서 칸을 고칠 때 편집창이 창 뒤로 숨는다"
    )
