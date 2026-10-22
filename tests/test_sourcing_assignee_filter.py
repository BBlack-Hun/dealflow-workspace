"""딜 소싱 [담당] 필터 — **지금 맡은 사람**으로 거르고, 고치면 곧바로 따라온다.

딜 소싱 명단의 `담당자` 칸에는 넘긴 이력이 쌓인다(`가 > 10/13 나` · `가 > 나 > 다`
· `백업팀 > 나`). 그 글자를 통째로 필터 값으로 쓰면 넘겨받은 사람의 칩에 그
줄이 안 잡히고 이력 글자가 칩 하나로 따로 섰다 — 딜 소싱 메뉴에서 담당을
바꿔도 딜 제안 관리의 [담당] 필터는 그대로인 것처럼 보였다.

여기서 못 박는 것.
  ① 지금 맡은 사람을 읽는 규칙은 하나(`pipeline.current_assignee`)이고 두 화면이
     그것을 지난다(`routers/sourcing.assignee_of`)
  ② 딜 제안 관리의 칩 · 카드, 딜 소싱 메뉴의 필터 값이 같은 사람을 말한다
  ③ 딜 소싱 메뉴에서 고치면(PATCH) 그 응답 · 상태 API · 다음 화면이 곧바로 새 값

이름은 전부 가상값이다(공개 저장소). 운영의 이력 모양만 그대로 옮겼다.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

from .conftest import DEMO_PASSWORD

BUCKET = "시리즈 A 이상"


@pytest.mark.parametrize("written, now", [
    ("가 > 10/13 나", "나"),          # 넘긴 날짜가 붙은 이력
    ("가 >10/13 나", "나"),           # 화살표 뒤 공백이 없다
    ("가 > 나 > 다", "다"),           # 두 번 넘겼다
    ("백업팀 > 가", "가"),            # 팀에서 사람으로
    ("백업팀 확인 > 나", "나"),       # 앞 토막이 두 낱말
    ("가담당 > 10/13 나담당", "나담당"),
    ("나", "나"),                     # 이력이 없다
    ("", ""),
])
def test_the_current_assignee_is_the_last_hand(written, now):
    from app.models import SourcingContact
    from app.routers.sourcing import assignee_of
    from app.services.pipeline import current_assignee

    assert current_assignee(written) == now
    # 소싱 화면들은 **같은 함수**를 지난다 — 따로 자르면 화면마다 다른 담당이 선다.
    assert assignee_of(SourcingContact(bucket=BUCKET, name="x", assignee_name=written)) == now


def test_one_rule_for_both_screens():
    """규칙을 두 벌로 두지 않는다 — 소싱 쪽은 `pipeline.current_assignee` 를 부른다."""
    import inspect

    from app.routers import sourcing

    assert "current_assignee(" in inspect.getsource(sourcing.assignee_of)


@pytest.fixture()
def roster(client, db, users):
    from app.models import SourcingContact

    rows = {
        "handed": SourcingContact(bucket=BUCKET, position=0, name="홍길동",
                                  assignee_name="가담당 > 10/13 나담당"),
        "twice": SourcingContact(bucket=BUCKET, position=1, name="김철수",
                                 assignee_name="가담당 > 다담당 > 나담당"),
        "plain": SourcingContact(bucket=BUCKET, position=2, name="박영희",
                                 assignee_name="가담당"),
    }
    db.add_all(rows.values())
    db.commit()
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    return rows


def _chips(body: str) -> dict:
    bar = body[body.index('id="assignee-filter"'):]
    bar = bar[:bar.index("</div>")]
    return {name: int(n) for name, n in
            re.findall(r'data-value="([^"]+)" data-count="(\d+)"', bar)}


def _deal_cards(body: str) -> dict:
    picker = body[body.index('id="sourcing-list"'):]
    return {int(i): who for who, i in re.findall(
        r'data-assignee="([^"]*)"[\s\S]*?class="contact-cb" value="(\d+)"', picker)}


def _sourcing_rows(body: str) -> dict:
    return {int(i): who for i, who in re.findall(
        r'<tr data-id="(\d+)"[^>]*?data-f-assignee_name="([^"]*)"', body)}


def test_deals_page_counts_who_holds_it_now(roster, client):
    body = client.get("/deals").text
    assert _chips(body) == {"나담당": 2, "가담당": 1}
    # 이력 글자가 칩 하나로 따로 서지 않는다
    assert "10/13" not in body[body.index('id="assignee-filter"'):][:2000]
    cards = _deal_cards(body)
    assert cards[roster["handed"].id] == "나담당"
    assert cards[roster["twice"].id] == "나담당"
    assert cards[roster["plain"].id] == "가담당"


def test_both_screens_agree(roster, client):
    deals = _deal_cards(client.get("/deals").text)
    sourcing = _sourcing_rows(client.get(f"/sourcing?tab={BUCKET}").text)
    assert sourcing == {i: deals[i] for i in sourcing}
    assert set(sourcing) == {r.id for r in roster.values()}
    # 칸에는 적힌 글자 그대로 — 이력은 그 칸에서 관리한다
    body = client.get(f"/sourcing?tab={BUCKET}").text
    assert "가담당 &gt; 10/13 나담당" in body


def test_an_edit_shows_up_at_once(roster, client, db):
    row = roster["plain"]
    r = client.patch(f"/api/sourcing/{row.id}",
                     json={"assignee_name": "가담당 > 10/14 라담당"})
    assert r.status_code == 200
    # 딜 소싱 화면은 이 값으로 행의 필터 값을 고친다(`sourcing.html`)
    assert r.json()["assignee"] == "라담당"
    db.refresh(row)
    assert row.assignee_name == "가담당 > 10/14 라담당"       # 적힌 글자는 그대로

    # 열어 둔 딜 제안 관리가 다시 읽는 자리
    state = client.get("/api/sourcing/state").json()
    assert {x["name"]: x["count"] for x in state["assignees"]} == {"나담당": 2, "라담당": 1}
    assert {x["id"]: x["assignee"] for x in state["rows"]}[row.id] == "라담당"

    # 새로 여는 두 화면
    body = client.get("/deals").text
    assert _chips(body) == {"나담당": 2, "라담당": 1}
    assert _deal_cards(body)[row.id] == "라담당"
    assert _sourcing_rows(client.get(f"/sourcing?tab={BUCKET}").text)[row.id] == "라담당"


def test_state_carries_this_months_receipts(roster, client, db):
    from app.services import sourcing_receipts

    month = sourcing_receipts.month_of()
    sourcing_receipts.mark(db, roster["twice"].id, month)
    db.commit()
    state = client.get("/api/sourcing/state").json()
    assert state["month"] == month
    assert state["month_label"] == f"{int(month[5:])}월"
    got = {x["id"]: x["received"] for x in state["rows"]}
    assert got == {roster["handed"].id: False, roster["twice"].id: True,
                   roster["plain"].id: False}


def test_chip_counts_follow_the_picked_message():
    """[담당] 칩 숫자 = **지금 고른 문구에서 뜨는 카드 수**(`deals.js` 의 `syncAssigneeCounts`).
    서버는 어느 글이든 받는 분을 다 세어 보내 리마인드에서 칩 55 · 카드 13장이었다."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("node 미설치 — 브라우저 로직 테스트 생략 "
                    "(호스트에서 `node tests/js/sourcing_assignee_counts_test.js`)")
    script = Path(__file__).resolve().parent / "js" / "sourcing_assignee_counts_test.js"
    result = subprocess.run([node, str(script)], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
