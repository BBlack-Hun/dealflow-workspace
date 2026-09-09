"""회차명 — **정규 발송만 주차를 단다.**

딜 소개는 `09/16 (9월 3주차)` 다. 주차가 곧 그 회차의 이름이라 뜻이 있다 —
사람들은 "첫째주 회차 / 셋째주 회차" 라고 부르고, 시트 머리글도 그렇다.

그런데 리마인드·미팅 요청도 같은 이름을 달았다. 그것들은 **회차에 매인 것이
아니다** — 딜 소개를 받은 사람이 답이 없어서, 미팅을 잡으려고 그때그때 보낸다.
발송 이력에 `09/16 (9월 3주차)` 가 여러 줄 남아, 무엇이 딜 소개고 무엇이
리마인드인지 이름만으로는 갈라지지 않았다.

그래서 정규 발송이 아니면 **주차를 빼고 무엇을 보내는지 적는다** —
`09/09 (리마인드)` · `09/09 (미팅 요청)`.

지키려는 경계.

1. 딜 소개는 **지금 그대로**다(주차).
2. 나머지는 주차 대신 **방식 이름**이고, 앞 날짜는 회차 기준일이 아니라 **오늘**이다.
3. 괄호 안 말은 **화면 탭 이름 그대로**다(`deals.MODE_TITLES`) — 여기서 짓지 않는다.
4. **이미 저장된 회차 이름은 안 바뀐다.** 바뀌는 것은 화면 기본값뿐이다
   (`test_cadence.test_saved_titles_are_not_renamed` 가 그것을 못박는다).
5. 화면에서 **탭을 바꾸면 회차명도 따라 바뀌고**, 사람이 고친 이름은 그대로 둔다
   (`tests/js/deals_batch_title_test.js`).

날짜는 전부 인자로 넣는다 — 오늘이 언제냐에 따라 통과했다 실패했다 하면 안 된다.
"""
from __future__ import annotations

import json
import re
from datetime import date

import pytest

from .conftest import DEMO_PASSWORD

# 9월 셋째 수요일 = 9/16 회차. 9/7~9/13 에는 회차일이 없어, 그 주에 화면을 열면
# 딜 소개 기본값은 **아직 오지 않은 9/16** 이 된다(회차 기준일). 정규가 아닌
# 방식이 그 날짜를 따라가는지 아닌지를 가르는 자리다.
CYCLE_DAY = date(2026, 9, 16)
OFF_WEEK = date(2026, 9, 10)     # 회차 주 밖 · 회차일 엿새 전


@pytest.fixture()
def logged(client, users):
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    return client


def _titles():
    from app.routers.deals import MODE_TITLES

    return MODE_TITLES


# ── 서비스 ──────────────────────────────────────────────────────────────────

def test_deal_keeps_its_week(db):
    """정규 발송은 **하나도 안 바뀐다** — 주차가 그 회차의 이름이다."""
    from app.services import cadence

    assert cadence.default_batch_title(None, OFF_WEEK) == "09/16 (9월 3주차)"
    # 회차일 뒤에는 오늘 날짜에 회차 주차. 예전 그대로다.
    assert cadence.default_batch_title(None, date(2026, 9, 17)) == "09/17 (9월 3주차)"


@pytest.mark.parametrize("label", ["리마인드", "미팅 요청", "IR 자료 전달"])
def test_other_modes_drop_the_week(db, label):
    """정규가 아니면 괄호 안이 **주차 대신 무엇을 보내는지**다."""
    from app.services import cadence

    title = cadence.default_batch_title(None, OFF_WEEK, label=label)
    assert title == f"09/10 ({label})"
    assert "주차" not in title


def test_other_modes_use_today_not_the_cycle_day(db):
    """앞 날짜는 **오늘**이다 — 회차 기준일이 아니다.

    회차 기준일을 쓰는 까닭은 괄호 안 주차가 그 회차를 가리키기 때문인데,
    주차를 빼고 나면 회차를 가리킬 것이 없다. 9/10 에 보내는 리마인드가
    `09/16 (리마인드)` 로 남으면 **보내지도 않은 엿새 뒤 날짜**가 적힌다.
    """
    from app.services import cadence

    assert cadence.cycle_anchor(None, OFF_WEEK) == CYCLE_DAY   # 아직 안 온 회차
    assert cadence.default_batch_title(None, OFF_WEEK).startswith("09/16")
    assert cadence.default_batch_title(None, OFF_WEEK,
                                       label="리마인드") == "09/10 (리마인드)"


def test_one_argument_call_is_unchanged(db):
    """`batch_title(day)` 는 손대지 않았다 — 저장된 이름이 그 길로 만들어졌다."""
    from app.services import cadence

    assert cadence.batch_title(date(2026, 8, 19)) == "08/19 (8월 3주차)"
    assert cadence.batch_title(date(2024, 2, 8)) == "02/08 (2월 2주차)"


def test_label_does_not_touch_saved_titles(db):
    """저장된 회차 이름을 만드는 함수는 **인자가 늘지 않았다.**

    바뀐 것은 새 회차를 만들 때 화면에 채워 주는 기본값뿐이다.
    (`test_cadence.test_saved_titles_are_not_renamed` 와 짝이다.)
    """
    import inspect

    from app.services import cadence

    assert list(inspect.signature(cadence.batch_title).parameters) == ["day", "cycle_day"]


# ── 괄호 안 말은 한 곳에서 온다 ─────────────────────────────────────────────

def test_labels_come_from_the_mode_titles(db):
    """새 말을 짓지 않는다 — 화면 탭 이름을 그대로 쓴다.

    두 군데 적으면 탭 이름만 고쳐지는 날 회차명이 낡은 말을 단 채 남는다.
    """
    from app.routers.deals import MODE_DEAL
    from app.services import cadence

    for mode, label in _titles().items():
        if mode == MODE_DEAL:
            continue
        assert cadence.default_batch_title(None, OFF_WEEK,
                                           label=label) == f"09/10 ({label})"


# ── 화면 ────────────────────────────────────────────────────────────────────

def _screen_titles(logged) -> dict:
    """화면이 실어 보낸 방식별 회차명(`data-titles`)."""
    body = logged.get("/deals").text
    m = re.search(r"data-titles='([^']*)'", body)
    assert m, "회차명 칸에 방식별 이름이 안 실렸다"
    return json.loads(m.group(1))


def test_screen_carries_a_title_for_every_mode(logged, db, monkeypatch):
    """탭이 일곱이면 이름도 일곱이다 — 하나라도 빠지면 그 탭만 낡은 이름을 단다."""
    from app import clock
    from app.routers.deals import MODE_DEAL

    monkeypatch.setattr(clock, "today", lambda: OFF_WEEK)
    titles = _screen_titles(logged)

    assert set(titles) == set(_titles())
    assert titles[MODE_DEAL] == "09/16 (9월 3주차)"
    for mode, label in _titles().items():
        if mode == MODE_DEAL:
            continue
        assert titles[mode] == f"09/10 ({label})", mode
        assert "주차" not in titles[mode], mode


def test_screen_input_starts_on_the_deal_title(logged, db, monkeypatch):
    """칸에 처음 채워지는 것은 딜 소개 이름이다 — 탭도 딜 소개로 서 있다."""
    from app import clock
    from app.routers.deals import MODE_DEAL

    monkeypatch.setattr(clock, "today", lambda: OFF_WEEK)
    body = logged.get("/deals").text
    m = re.search(r'id="batch-title" value="([^"]*)"', body)
    assert m, "회차명 칸이 없다"
    assert m.group(1) == _screen_titles(logged)[MODE_DEAL] == "09/16 (9월 3주차)"


# ── 브라우저 쪽 ─────────────────────────────────────────────────────────────
#
# 탭을 눌러 방식을 바꾸는 것도, 사람이 고친 이름을 알아보는 것도 브라우저에
# 있다. 그 규칙을 파이썬으로 다시 구현하면 두 벌이 되어 어긋나도 모르므로,
# deals.js 를 **그대로 실행**해 본다.

def test_화면이_방식을_바꾸면_회차명도_따라_바꾼다():
    """★ 탭을 바꾸면 그 방식 이름으로 · 사람이 고친 이름은 그대로.

    서버가 처음 채워 주는 것은 딜 소개 이름이라, 탭만 눌러 리마인드로 바꾸면
    **딜소개 이름을 단 채 리마인드가 나간다.**
    """
    import shutil
    import subprocess
    from pathlib import Path

    node = shutil.which("node")
    if node is None:
        pytest.skip("node 미설치 — 브라우저 로직 테스트 생략 "
                    "(호스트에서 `node tests/js/deals_batch_title_test.js`)")
    js = Path(__file__).resolve().parent / "js" / "deals_batch_title_test.js"
    result = subprocess.run([node, str(js)], capture_output=True,
                            text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
