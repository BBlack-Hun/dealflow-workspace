"""수정창의 [저장]·[삭제] 는 **굴러가지 않는다**.

## 왜 이 검사가 있나

수정창의 단추 줄이 `.detail-body` **안**에 있었다. 그 자리는 칸이 세로로
쌓이는 자리고, **칸은 달마다 늘어난다** — 딜소개현황 명단은 한 달에 세 칸씩
붙는다(`1차 딜소개` · `IR 자료 요청 기업` · `미팅 요청/안내전화/미팅완료`,
`services/monthly_columns.py` 가 월 초에 저절로 세운다). 그래서 단추가 달마다
멀어졌다. 헤드리스 크롬으로 재 봤다(달 칸 열둘인 명단):

    /contacts   1440×900   창 속 2310px · 보이는 815px → [저장]까지 1495px
    /contacts    390×844   창 속 3392px · 보이는 719px → [저장]까지 2673px
    한 달 지나면(달 칸 열다섯)  2310px → 2589px  (달마다 +279px)

고침은 **바닥에 붙이기**다. 위로 올리지 않았다 — 올리면 되돌릴 수 없는
[삭제] 가 창을 여닫는 손길이 지나는 자리(`detail-head` 의 [닫기 ✕] 바로 밑)로
올라온다. 붙이면 자리를 늘 먹지만 재 보니 900px 중 58px · 844px 중 69px 이다.

**딜 기업 DB 가 이미 그 모양이었다**(`companies.html` 의 `.detail-foot`).
새 모양을 만든 것이 아니라 투자사 관리 현황을 거기 맞췄다 — 같은 자리를 두
모양으로 두면 반드시 한쪽이 낡는다(`static/js/panel_modal.js` 머리말).

## 여기서 보는 것

눌러 보는 일은 브라우저 쪽이 한다(`tests/js/panel_foot_tab_test.js` ·
`tests/js/detail_panel_modal_test.js`). 여기서는 **굴러가지 않게 하는 구조**를
지킨다: 단추가 굴리는 상자 바깥에 있는가 · 그 줄이 눌려 없어지지 않는가 ·
[삭제] 가 [저장] 옆에 안 붙는가 · 폰 폭에서 줄이 접히는가.
"""
from __future__ import annotations

import pathlib
import re
import shutil
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
CSS = ROOT / "app" / "static" / "css" / "app.css"
CONTACTS_HTML = ROOT / "app" / "templates" / "contacts.html"
COMPANIES_HTML = ROOT / "app" / "templates" / "companies.html"
FOOT_TEST = pathlib.Path(__file__).resolve().parent / "js" / "panel_foot_tab_test.js"

# 두 화면의 같은 자리. `(화면, [저장] id, [삭제] id)`
SCREENS = ((CONTACTS_HTML, "save-btn", "delete-btn"),
           (COMPANIES_HTML, "co-save", "co-delete"))


def _html(path: pathlib.Path) -> str:
    """Jinja 주석을 지운 화면. 안 지우면 주석 속 `<div>` 가 깊이 세기를 망친다."""
    return re.sub(r"\{#.*?#\}", "", path.read_text(encoding="utf-8"), flags=re.S)


def _css() -> str:
    """주석을 지운 CSS. 안 지우면 규칙 바로 위의 설명이 선택자에 딸려 온다."""
    return re.sub(r"/\*.*?\*/", "", CSS.read_text(encoding="utf-8"), flags=re.S)


def _rule(css: str, selector: str) -> str:
    for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", css):
        if m.group(1).strip() == selector:
            return m.group(2)
    raise AssertionError(f"CSS 에 `{selector}` 규칙이 없다")


def _blocks(html: str, opening: str):
    """`opening` 으로 시작하는 `<div>` 들의 `(시작, 끝)` 자리.

    여는 꺾쇠를 세어 짝을 맞춘다 — 클래스만 보고 다음 `</div>` 를 잡으면
    속에 든 `<div>` 하나에 범위가 통째로 어긋난다.
    """
    out = []
    for m in re.finditer(re.escape(opening), html):
        depth, i = 0, m.start()
        for t in re.finditer(r"<div\b|</div>", html[m.start():]):
            depth += 1 if t.group(0) == "<div" else -1
            if depth == 0:
                out.append((i, m.start() + t.end()))
                break
        else:
            raise AssertionError(f"`{opening}` 의 닫는 꺾쇠를 못 찾았다")
    return out


# ── 굴려야 닿는 자리에 있으면 안 된다 ───────────────────────────────────────


@pytest.mark.parametrize("path,save,delete", SCREENS, ids=lambda x: getattr(x, "name", x))
def test_저장과_삭제가_굴리는_상자_바깥에_있는가(path, save, delete):
    """`.detail-body` 가 굴리는 자리다. 단추가 그 안에 있으면 칸만큼 밀린다.

    달마다 칸이 세 개씩 붙으므로, 안에 두면 이 거리는 **해마다 3300px 씩 는다.**
    """
    html = _html(path)
    bodies = _blocks(html, '<div class="detail-body"')
    assert bodies, f"{path.name} 에 `.detail-body` 가 없다 — 굴리는 자리가 어디인지 모른다"
    feet = _blocks(html, '<div class="detail-foot"')
    assert len(feet) == 1, f"{path.name} 의 `.detail-foot` 이 {len(feet)}개다 — 바닥 줄은 하나다"

    for btn in (save, delete):
        at = html.find(f'id="{btn}"')
        assert at > 0, f"{path.name} 에 `#{btn}` 이 없다"
        for start, end in bodies:
            assert not (start < at < end), (
                f"{path.name}: `#{btn}` 이 `.detail-body` 안에 있다 ★ "
                "칸이 늘면 그만큼 아래로 밀린다 — 이 판이 고친 바로 그것이다"
            )
        start, end = feet[0]
        assert start < at < end, f"{path.name}: `#{btn}` 이 바닥 줄 안에 없다"


def test_삭제가_막힌_사유도_단추_옆에_남는가():
    """`#detail-msg` 는 **삭제가 왜 막혔는지** 적는 자리다(`contacts.js` 의 `remove`).

    굴러가는 본문 맨 밑에 두면, 바닥 줄의 [삭제] 를 누른 사람 눈에는 안 보인다 —
    확인창은 누르면 사라지므로 그 사유를 다시 읽을 데가 없어진다.
    """
    html = _html(CONTACTS_HTML)
    at = html.find('id="detail-msg"')
    assert at > 0, "`#detail-msg` 가 없다"
    start, end = _blocks(html, '<div class="detail-foot"')[0]
    assert start < at < end, (
        "`#detail-msg` 가 바닥 줄 밖에 있다 ★ 삭제가 막힌 사유를 누른 자리에서 못 읽는다"
    )


def test_바닥_줄이_눌려_사라지지_않는가():
    """`flex: 0 0 auto`. 안 적어 두면 내용이 아주 많은 창에서 이 줄만 납작해진다.

    창은 세로 flex 고 본문이 `flex:1` 이라 남는 자리를 본문이 먹는 것이 맞다.
    다만 바닥 줄이 **줄어들 수 있으면** 그 다툼에서 밀려 단추가 잘린다.
    """
    css = _css()
    panel = _rule(css, ".detail-panel")
    assert "flex-direction: column" in panel, "창이 세로 flex 가 아니면 바닥 줄이 안 붙는다"

    body = _rule(css, ".detail-body")
    assert "overflow-y: auto" in body, "본문이 굴리는 자리가 아니면 창 전체가 길어진다"
    assert "flex: 1" in body, "본문이 남는 자리를 안 먹으면 바닥 줄이 내용 바로 밑에 붙는다"

    foot = _rule(css, ".detail-foot")
    assert "flex: 0 0 auto" in foot, (
        "바닥 줄이 줄어들 수 있다 ★ 칸이 아주 많은 창에서 이 줄만 납작해져 단추가 잘린다"
    )


def test_폰_폭에서_단추가_밖으로_안_나가는가():
    """390px 에서 단추 넷이 한 줄에 다 안 들어가는 명단이 있다.

    `flex-wrap` 이 없으면 넘치는 단추가 창 밖으로 나가 **눌리지 않는다** —
    같은 일을 이 저장소가 `#165`·`#167` 에서 이미 겪었다.
    """
    foot = _rule(_css(), ".detail-foot")
    assert "flex-wrap: wrap" in foot, "바닥 줄이 안 접힌다 ★ 좁은 폭에서 단추가 창 밖으로 나간다"


def test_폰에서_창_밑동이_화면_아래로_안_내려가는가():
    """`100vh` 는 폰에서 **주소창을 숨겼을 때의 높이**다.

    단추가 본문 안에 있던 때는 굴리면 그만이라 티가 안 났다. 바닥에 붙인
    뒤로는 창 밑동이 곧 단추 자리라, 그만큼 내려가면 줄이 통째로 안 보인다.
    """
    panel = _rule(_css(), ".detail-panel")
    assert "height: 100dvh" in panel, "`100dvh` 가 없다 ★ 폰에서 바닥 줄이 화면 밖으로 내려간다"
    assert panel.index("height: 100vh") < panel.index("height: 100dvh"), (
        "`100vh` 가 뒤에 있다 — `dvh` 를 모르는 브라우저가 받을 값이 없다"
    )


# ── [삭제] 는 [저장] 옆에 안 선다 ──────────────────────────────────────────


@pytest.mark.parametrize("path,save,delete", SCREENS, ids=lambda x: getattr(x, "name", x))
def test_삭제가_저장_옆에_붙지_않는가(path, save, delete):
    """고친 값은 다시 고치면 되지만 **지운 줄은 화면 어디에도 안 남는다.**

    이 저장소가 같은 자리에서 쓰는 방법 그대로 넷을 겹친다
    (`_closed_followups.html` 의 [다시 켜기]·[지우기], `tests/test_closed_followup_delete.py`):
    사이를 벌리고 · 끊어 주고 · 색을 달리하고 · 확인창을 세운다.

    딜 기업 DB 는 이 둘이 **8px 떨어져 나란히** 서 있었다(재 봤다).
    """
    html = _html(path)
    start, end = _blocks(html, '<div class="detail-foot"')[0]
    foot = html[start:end]

    at_save, at_del = foot.find(f'id="{save}"'), foot.find(f'id="{delete}"')
    assert at_save >= 0 and at_del >= 0, f"{path.name}: 바닥 줄에 두 단추가 다 있어야 한다"
    assert at_save < at_del, f"{path.name}: [삭제] 가 [저장] 보다 앞에 있다"

    # 끊어 준다 — 사이에 다른 단추가 서든 아니든, 경계는 눈에 보여야 한다.
    sep = foot.find('class="sep"', at_save)
    assert 0 <= sep < at_del, (
        f"{path.name}: [저장] 과 [삭제] 사이가 안 끊겨 있다 ★ "
        "`<span class=\"sep\">` 을 바로 앞에 둔다"
    )
    # 색이 다르다 — 남은 셋 중 하나라도 빠지면 겹쳐 둔 뜻이 없다.
    assert re.search(r'class="danger-btn"[^>]*id="%s"' % re.escape(delete), foot) \
        or re.search(r'id="%s"[^>]*class="danger-btn"' % re.escape(delete), foot), \
        f"{path.name}: [삭제] 가 [저장] 과 같은 색이다"


def test_삭제를_줄의_반대쪽_끝으로_미는가():
    """벌리는 것은 CSS 가 한다 — 화면마다 단추 수가 달라(투자사 화면에만
    [이 방만 확인] 이 선다) 빈 칸을 손으로 넣으면 화면마다 달라진다."""
    css = _css()
    assert "margin-left: auto" in _rule(css, ".detail-foot .danger-btn"), (
        "[삭제] 를 줄의 반대쪽 끝으로 안 민다 ★ [저장] 바로 옆에 선다"
    )
    assert "margin-left: auto" in _rule(css, ".detail-foot .sep"), (
        "끊는 점이 [삭제] 를 따라가지 않는다 — 점만 줄 가운데 남는다"
    )
    assert "margin-left: 0" in _rule(css, ".detail-foot .sep + .danger-btn"), (
        "점과 [삭제] 가 둘 다 밀려 사이가 벌어진다 — 미는 일은 점 하나가 맡는다"
    )


# ── 브라우저 쪽 검사 ────────────────────────────────────────────────────────


@pytest.mark.skipif(shutil.which("node") is None, reason="node 미설치 — 브라우저 로직 테스트 생략")
def test_바닥_줄이_탭을_따라_숨는가():
    """활동 이력 탭에는 저장할 폼이 없다 — 거기서 [저장]·[삭제] 가 서 있으면
    무엇을 지우는 단추인지 알 수 없다.

    로컬에서는 `node tests/js/panel_foot_tab_test.js` 로도 돈다.
    """
    result = subprocess.run(
        [shutil.which("node"), str(FOOT_TEST)], capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
