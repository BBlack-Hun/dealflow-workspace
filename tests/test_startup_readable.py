"""표를 **읽히게** 만든 규칙들 — 첫 열 고정 · 위쪽 접기 · 줄 높이.

담당 기업이 여든인 팀원이 이렇게 적어 보냈다. 그대로 옮긴다.

  "첫 행(타이틀 행)은 고정인데 왜 좌우 스크롤이 되면 스타트업 이름은 고정이 또
   아닌 건지, 일관된 UX 규칙이 없는 것 같습니다."

  "실제 화면에서 스타트업 리스트가 가장 중요한 정보라고 생각되는데, 리스트는
   4줄밖에 스크롤이 안 되고, 리스트 외의 항목이 더 많은 열을 차지합니다."

여기서 막는 것은 넷이다.

  1. 첫 열이 가로 스크롤에 고정되는가 — **머리행과 겹치는 모서리까지**
  2. **두 화면이 같은 규칙**인가(투자사 관리 현황 · 스타트업)
  3. 접어 둔 것을 **펼 수 있는가** — 그리고 접힌 채로도 있다는 것이 보이는가
  4. 줄 높이를 줄인 규칙이 그대로 있는가

전부 **글자를 정적으로** 읽는다. 브라우저를 띄우지 않는 검사라 "정말 그렇게
보이는가" 까지는 못 본다 — 실제 자리·높이는 헤드리스 크롬으로 재서 확인했고,
여기서는 그 규칙이 **조용히 빠지지 않게** 잠근다(이 저장소가 반복해 당한 것이
규칙이 사라져도 화면이 멀쩡해 보이는 부류다).

이름·회사·번호는 전부 지어낸 값이다 — 저장소가 공개다.
"""
from __future__ import annotations

import re
from pathlib import Path

from .test_startup_tab import LIST, OTHER, _thead_cells, _url, sheets  # noqa: F401

ROOT = Path(__file__).resolve().parent.parent
CSS = (ROOT / "app" / "static" / "css" / "app.css").read_text(encoding="utf-8")
HTML = (ROOT / "app" / "templates" / "contacts.html").read_text(encoding="utf-8")


def _z(pattern: str) -> int:
    """그 규칙이 정한 `z-index`. 못 찾으면 검사를 세운다."""
    m = re.search(pattern, CSS, re.S)
    assert m, f"app.css 에서 규칙을 못 찾았습니다: {pattern}"
    return int(m.group(1))


# ── 1. 첫 열 고정 ───────────────────────────────────────────────────────────

def test_머리행과_첫_열이_둘_다_고정이다():
    """하나만 고정하면 **다른 축으로 밀 때 그 칸이 흘러간다.**

    머리행 고정은 오래전부터 있었고(`thead th { top: 0 }`) 첫 열이 없었다.
    표가 화면보다 1,900px 넘게 넓어서, 오른쪽 끝의 이번 달 칸을 보는 동안
    어느 기업 줄인지 알 수가 없었다.
    """
    assert re.search(r"\.table-wrap\.wide thead th \{[^}]*position: sticky", CSS), \
        "머리행 세로 고정이 사라졌습니다"
    assert re.search(r"\.table-wrap\.wide thead th \{[^}]*top: 0", CSS), \
        "머리행 세로 고정이 사라졌습니다"
    assert re.search(r"\.table-wrap\.wide td\.stick \{[^}]*position: sticky", CSS), \
        "첫 열 가로 고정이 사라졌습니다"
    # 왼쪽 자리는 **화면이 더해 넘긴 값**을 읽는다 — CSS 에 px 을 박으면
    # 칸 폭을 고칠 때 두 군데를 맞춰야 하고, 한쪽만 고쳐지면 반 칸씩 어긋난다.
    for name in ("--stick-a", "--stick-b"):
        assert f"var({name}" in CSS, f"{name} 를 안 읽습니다"
        assert name in HTML, f"화면이 {name} 를 안 넘깁니다"


def test_겹치는_모서리가_둘_다_위에_선다():
    """왼쪽 위 칸은 **머리행이기도 하고 첫 열이기도 하다.**

    쌓는 차례가 어긋나면 글자가 겹쳐 보인다:

        머리행의 고정 칸 > 머리행 > 몸통의 고정 칸 > 보통 칸

    몸통의 고정 칸이 머리행보다 위면 세로로 밀 때 기업명이 머리글을 덮고,
    보통 칸보다 아래면 가로로 밀 때 남의 값이 기업명을 덮는다. 둘 다 겪었다.
    """
    body_stick = _z(r"\.table-wrap\.wide td\.stick \{[^}]*z-index: (\d+)")
    head = _z(r"\.table-wrap\.wide thead th \{[^}]*z-index: (\d+)")
    corner = _z(r"\.table-wrap\.wide th\.stick \{[^}]*z-index: (\d+)")
    assert 0 < body_stick < head < corner, (
        f"쌓는 차례가 어긋납니다: 몸통 고정 {body_stick} · 머리행 {head} · "
        f"모서리 {corner}")


def test_고정된_칸은_바탕이_비치지_않는다():
    """고정 칸은 다른 칸 **위에** 그려진다 — 바탕이 없으면 밑이 비친다."""
    assert re.search(r"\.table-wrap\.wide td\.stick \{[^}]*background:", CSS), \
        "고정된 몸통 칸에 바탕색이 없습니다"
    # 줄에 걸린 색(마우스 올림·감춘 줄)도 고정 칸까지 이어져야 한다 —
    # 끊기면 그 줄이 두 줄처럼 보인다.
    assert "tr:hover > td.stick" in CSS, "마우스 올린 줄의 색이 고정 칸에서 끊깁니다"
    assert "tr.row-hidden > td.stick" in CSS, "감춘 줄 무늬가 고정 칸에서 끊깁니다"


def test_표의_왼쪽_테두리는_세우지_않는다():
    """`border-collapse: collapse` 의 왼쪽 1px 이 **이음매로 드러난다.**

    그 1px 은 표에 붙어 함께 밀려 가는데 고정된 칸의 바탕은 그 뒤에서 시작해서,
    가로로 밀면 한 줄 틈으로 밑을 지나가는 글자가 비쳤다. 헤드리스 크롬으로
    네 가지를 재 봤고 테두리를 안 세우는 것만 통했다.
    """
    assert re.search(r"\.table-wrap\.wide \.grid-table \{[^}]*border-left: 0", CSS), \
        "표의 왼쪽 테두리를 다시 세웠습니다 — 고정 칸 옆에 1px 이음매가 생깁니다"


def test_스타트업_표의_첫_두_칸이_고정된다(sheets):  # noqa: F811
    """`NO` 와 `기업명`. 번호만 고정하면 어느 기업인지 여전히 모른다."""
    cells = _thead_cells(sheets.get(_url(LIST)).text)
    assert "stick stick-a" in cells[0][0], cells[0]
    assert "stick stick-b" in cells[1][0], cells[1]
    assert "기업명" in cells[1][1], cells[1]


def test_투자사_표도_같은_규칙이다(sheets):  # noqa: F811
    """**같은 화면 파일·같은 감싸개**를 쓰는 표다.

    한쪽만 고정하면 화면을 옮길 때마다 규칙이 바뀐다 — "일관된 UX 규칙이
    없다" 는 그 불만이 그대로 남는다.
    """
    cells = _thead_cells(sheets.get(_url(OTHER)).text)
    assert "stick stick-a" in cells[0][0], cells[0]
    assert "stick stick-b" in cells[1][0], cells[1]
    assert "이름" in cells[1][1], cells[1]


def test_머리글과_칸에_같은_수의_고정_표시가_붙는다(sheets):  # noqa: F811
    """한쪽만 붙으면 **머리글은 멈춰 서고 칸은 따라 흘러간다.**

    이름 위에 남의 값이 겹쳐 보이는데, 머리글만 보면 멀쩡해서 눈치채기 어렵다.
    """
    for sheet in (LIST, OTHER):
        body = sheets.get(_url(sheet)).text
        head = re.search(r"<thead>(.*?)</thead>", body, re.S).group(1)
        rows = re.findall(r'<tr class="data-row.*?</tr>', body, re.S)
        assert rows, f"{sheet}: 줄이 하나도 없어 검사할 수 없습니다"
        want = len(re.findall(r'class="[^"]*\bstick\b', head))
        assert want >= 2, f"{sheet}: 머리글에 고정 칸이 없습니다"
        for row in rows:
            got = len(re.findall(r'class="[^"]*\bstick\b', row))
            assert got == want, (
                f"{sheet}: 머리글 {want}칸 · 줄 {got}칸 — 짝이 안 맞습니다")


def test_폰에서는_가로_고정만_풀고_머리행은_남긴다():
    """고정 폭 214px 은 폰(표에 362px)에서 **볼 자리를 뺏는다.**

    `position` 을 건드리면 머리행 세로 고정까지 같이 풀린다 — 가로 자리만 푼다.
    """
    m = re.search(r"@media \(max-width: 720px\) \{(.*?)\n\}", CSS, re.S)
    assert m, "폰 규칙 묶음을 못 찾았습니다"
    phone = m.group(1)
    assert re.search(r"\.table-wrap\.wide td\.stick \{[^}]*position: static", phone), \
        "폰에서 첫 열 고정을 안 풉니다"
    assert "th.stick { position" not in phone, \
        "폰에서 머리글 칸의 position 을 건드리면 머리행 세로 고정까지 풀립니다"
    assert re.search(r"\.stick-b \{[^}]*left: auto", phone), \
        "폰에서 고정 칸의 가로 자리를 안 풉니다"


# ── 2. 접은 것을 펼 수 있는가 ───────────────────────────────────────────────

FOLDED = [
    "이름 저장",          # 명단 이름 바꾸기
    "칸 추가",            # 달 칸 세우기
    "칸 숨기기",
    "칸 삭제",
]


def test_표_위의_설정은_접혀_있고_눌러서_펼_수_있다(sheets):  # noqa: F811
    """`<details>` 다 — **지우는 것이 아니라 접는 것**이다.

    접힌 것도 DOM 에 그대로 있어서 브라우저 찾기·검사가 다 본다. 자바스크립트
    없이 브라우저가 여닫으므로, 스크립트가 막힌 화면에서도 열린다.
    """
    body = sheets.get(_url(LIST)).text
    m = re.search(r'<details class="sheet-fold">(.*?)</details>', body, re.S)
    assert m, "표 위 설정을 담은 접는 상자가 없습니다"
    assert "<summary>" in m.group(1), "펼 수 있는 여는 줄(summary)이 없습니다"
    # 기본은 **접힌 채**다. 펴진 채로 서면 접은 뜻이 없다.
    assert "<details class=\"sheet-fold\" open" not in body, \
        "접는 상자가 펴진 채로 섭니다 — 표에 돌려준 자리가 없습니다"
    for name in FOLDED:
        assert name in m.group(1), f"[{name}] 이 접는 상자 안에 없습니다"


def test_접힌_채로도_무엇이_들어_있는지_보인다(sheets):  # noqa: F811
    """숨긴 칸이 있는 것을 모르면 "왜 그 칸이 없지" 를 DB 에서 찾게 된다."""
    body = sheets.get(_url(LIST)).text
    summary = re.search(r"<summary>(.*?)</summary>", body, re.S).group(1)
    assert "명단" in summary and "칸" in summary, summary
    assert "달 칸" in summary, f"달 칸이 몇 개인지 접힌 줄에 안 적혀 있습니다: {summary}"


def test_지난_칸_펴기는_접지_않는다(sheets):  # noqa: F811
    """이것은 설정이 아니라 **지금 표가 무엇을 보여 주는가**다.

    지난달 칸이 접혀 있다는 것을 모르면 그 달 기록이 지워진 줄 안다
    (`services/contact_columns.split_months` 주석이 든 그 사고다).
    """
    # 지난달 칸을 하나 세워 둔다 — 안 그러면 이 줄이 뜰 일이 없다.
    from app.models import ContactColumn
    from app.db import SessionLocal

    db = SessionLocal()
    db.add(ContactColumn(sheet=LIST, label="1월 리마인드 문자", position=99))
    db.commit()
    db.close()

    body = sheets.get(_url(LIST)).text
    fold = re.search(r'<details class="sheet-fold">.*?</details>', body, re.S)
    assert "months=all" in body, "지난 칸을 펴는 길이 화면에 없습니다"
    assert "months=all" not in fold.group(0), \
        "지난 칸 펴기가 접는 상자 안에 들어갔습니다 — 접혀 있는 줄 모르게 됩니다"


# ── 3. 줄 높이 ──────────────────────────────────────────────────────────────

def test_넓은_표는_줄을_얇게_한다():
    """글자 크기(13px)는 사용자가 정한 값이라 **되돌리지 않는다.**

    대신 글자가 아닌 것을 줄인다 — 위아래 여백과 두 줄 접는 칸의 줄 간격.
    """
    pad = re.search(r"\.table-wrap\.wide \.grid-table td \{[^}]*padding: (\d+)px", CSS)
    assert pad, "넓은 표의 칸 여백 규칙이 사라졌습니다"
    assert int(pad.group(1)) <= 4, f"칸 여백이 다시 늘었습니다({pad.group(1)}px)"
    lh = re.search(r"\.table-wrap\.wide \.grid-table \.clamp2 \{[^}]*line-height: ([\d.]+)",
                   CSS)
    assert lh, "두 줄 접는 칸의 줄 간격 규칙이 사라졌습니다"
    assert float(lh.group(1)) <= 1.4, f"줄 간격이 다시 늘었습니다({lh.group(1)})"
    # 글자 크기는 13px 한 값 그대로여야 한다(#174 에서 사용자가 정했다).
    assert re.search(r"\.grid-table td \{[^}]*font-size: 13px", CSS), \
        "표 글자 크기가 13px 이 아닙니다 — 줄 높이를 글자로 줄이면 안 됩니다"


def test_촘촘히_보기는_긴_글도_한_줄로_접는다():
    """여백만 줄이던 토글이라 눌러도 줄 수가 거의 안 늘었다.

    줄 높이를 정하는 것은 **두 줄짜리 메모 칸**이라, 그것을 안 접으면
    여백을 아무리 줄여도 줄 수가 그대로다.
    """
    assert re.search(r"\.grid-table\.dense \.clamp2 \{[^}]*line-clamp: 1", CSS), \
        "촘촘히 보기가 긴 글을 한 줄로 안 접습니다"
    # 넓은 표에서도 촘촘히가 이겨야 한다 — 셈이 같으면 안 걸린다.
    assert ".table-wrap.wide .grid-table.dense td" in CSS, \
        "넓은 표에서 촘촘히 보기의 여백이 안 걸립니다"


def test_고르는_칸은_한_줄로_선다(sheets):  # noqa: F811
    """보기에 칸 폭을 넘는 말이 있다(`현재 투자유치 계획 없음`).

    그냥 두면 그 한 칸 때문에 **줄 전체가 두 줄 높이**가 된다. 값 전체는
    `title` 로 그 자리에서 읽히고, 눌러 고칠 때는 보기 목록이 뜬다.
    """
    body = sheets.get(_url(LIST)).text
    row = re.search(r'<tr class="data-row.*?</tr>', body, re.S).group(0)
    picks = re.findall(r'<div class="cell([^"]*)"[^>]*data-type="pick"', row, re.S)
    # **찾은 것이 없으면 이 검사는 아무것도 안 본 것이다.** 화면 글자가 바뀌어
    # 정규식이 빗나가면 조용히 통과하는 부류라, 먼저 개수를 못 박는다.
    assert len(picks) >= 6, f"고르는 칸을 못 찾았습니다({len(picks)}개)"
    for cell in picks:
        assert "ellipsis" in cell, f"고르는 칸이 두 줄로 접힙니다: {cell}"
    # 긴 글 칸은 그대로 두 줄이다 — 값이 통째로 안 보이면 안 되는 칸이다.
    assert "clamp2" in row, "긴 글 칸의 두 줄 접기가 사라졌습니다"
