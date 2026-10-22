"""딜 소싱 제안 › Series A 딜 공유의 [후보 자동 채우기] — 체크할 기업과 그 차례.

사용자 요청(10/22): "자동채우기이지만 투자 유치금액 높은순으로 해줘~"

여기서 못 박는 것.

  ① 대상 — 딜 소개 문구(`deal_pitch`)가 있는 기업만(빈칸 · 띄어쓰기만은 뺀다)
  ② 차례 — 투자유치희망금액(`raise_target`) 높은 순. 범위는 **위쪽 값**(`amount.
     million_top`), 단위가 섞여도 같은 억으로 견준다
  ③ 금액이 비었거나(`~` · 못 읽는 글자 포함) 숫자가 아닌 곳은 **맨 뒤**
  ④ 같으면 덜 나간 순(받은 분 수), 그다음 받은 날 최신순(고르개 차례 — `sort_rows`)
  ⑤ 최대 10곳(고르개 한도) · 금액이 빈 후보 수를 함께 준다
  ⑥ 화면 — `/api/series-a-share/state` 가 그 차례를 싣고, 고르개에 단추 · 안내가 선다

차례가 곧 사람마다 앞에서 N개를 나눌 차례다(`series_a_share.plan`). 이름은 전부
가상값이다(공개 저장소).
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from .conftest import DEMO_PASSWORD

JS_DIR = Path(__file__).resolve().parent / "js"


def _row(cid, name, pitch, amount, received):
    return {"id": cid, "name": name, "deal_pitch": pitch, "raise_target": amount,
            "received_sort": received}


def test_highest_raise_first_blanks_last_then_fewer_shares_then_newest():
    from app.routers.series_a import sort_rows
    from app.services.series_a_share import autofill

    rows = sort_rows([
        _row(1, "가샘플", "문구", "50", "2026-10-01"),          # 50억 · 2명 받음
        _row(2, "나샘플", "문구", "30~80억", "2026-09-01"),     # 범위 — 위쪽 80억
        _row(3, "다샘플", "문구", "5천만원", "2026-08-01"),     # 0.5억
        _row(4, "라샘플", "문구", "", "2026-10-10"),           # 빈 금액
        _row(5, "마샘플", "문구", "~", "2026-10-12"),          # 모름 — 빈 것과 같다 · 1명 받음
        _row(6, "바샘플", "문구", "10억 이상", "2026-10-01"),   # 못 읽음 — 빈 것과 같다
        _row(7, "사샘플", "", "100", "2026-10-20"),            # 문구 없음 — 대상 아님
        _row(8, "아샘플", "  ", "200", "2026-10-20"),          # 띄어쓰기만 — 대상 아님
        _row(9, "자샘플", "문구", "50억", "2026-09-01"),        # 50억 동률 · 아무도 안 받음
        _row(10, "차샘플", "문구", "5,000만원", "2026-09-15"),  # 0.5억 동률 · 더 최근
        _row(11, "카샘플", "문구", None, "2026-07-03"),
        _row(12, "타샘플", "문구", None, "2026-07-02"),
        _row(13, "파샘플", "문구", None, "2026-07-01"),
    ])
    sent = {1: {101, 102}, 5: {101}}

    got = autofill(rows, sent)

    # 금액 높은 순(범위는 위쪽) → 동률은 덜 나간 순 → 받은 날 최신순 → 빈 금액은 뒤,
    # 그 안에서도 덜 나간 순 · 최신순. 11곳 중 10곳만 — 1명 받은 빈 금액(5)이 밀려난다.
    assert got["ids"] == [2, 9, 1, 10, 3, 4, 6, 11, 12, 13], got
    assert got["candidates"] == 11
    assert got["blank"] == 6, "빈 금액 · `~` · 못 읽는 글자를 다 센다"


def test_fewer_than_ten_takes_them_all():
    from app.services.series_a_share import autofill

    got = autofill([_row(1, "가샘플", "문구", "", "2026-10-01"),
                    _row(2, "나샘플", "문구", "3", "2026-09-01")], {})
    assert got == {"ids": [2, 1], "candidates": 2, "blank": 1}
    assert autofill([], {}) == {"ids": [], "candidates": 0, "blank": 0}


@pytest.fixture()
def world(client, db, users):
    from app.models import SeriesACompany

    rows = {
        "a": SeriesACompany(name="샘플알파", received_at="2026-10-01", deal_pitch="알파 문구",
                            raise_target="20"),
        "b": SeriesACompany(name="샘플베타", received_at="2026-10-05", deal_pitch="베타 문구"),
        "c": SeriesACompany(name="샘플감마", received_at="2026-09-01", deal_pitch="감마 문구",
                            raise_target="50-100억"),
        "d": SeriesACompany(name="샘플델타", received_at="2026-10-09", raise_target="500"),
    }
    db.add_all(rows.values())
    db.commit()
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    return rows


def test_the_state_carries_the_autofill_order(world, client):
    state = client.get("/api/series-a-share/state").json()
    w = world
    assert state["autofill"] == {"ids": [w["c"].id, w["a"].id, w["b"].id],
                                 "candidates": 3, "blank": 1}


def test_the_picker_has_the_button_and_the_hint(world, client):
    body = client.get("/deals").text
    picker = body[body.index('id="series-a-picker"'):]
    picker = picker[:picker.index('id="series-a-list"')]
    line = picker[picker.index('id="sa-autofill-line"'):]
    line = line[:line.index("</div>")]
    # Series A 딜 공유에만 서는 칸이다 — IR 자료 전달에서는 숨는다(`data-only`).
    assert 'data-only="share"' in picker[picker.rindex("<div", 0, picker.index('id="sa-autofill-line"')):]
    assert 'id="sa-autofill"' in line and "후보 자동 채우기" in line
    assert "투자유치 금액 높은 순으로 최대 10곳 — 금액이 빈 곳은 뒤로" in line
    assert 'id="sa-autofill-note"' in line


def test_the_screen_logic_runs_in_node():
    node = shutil.which("node")
    if node is None:
        pytest.skip("node 미설치 — `node tests/js/series_a_autofill_test.js`")
    result = subprocess.run([node, str(JS_DIR / "series_a_autofill_test.js")],
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
