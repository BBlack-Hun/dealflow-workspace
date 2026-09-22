"""미팅 후기의 투자사명 → 후기를 묻는 카톡 발송으로.

미팅이 끝나고 열흘쯤 지나면 결과를 묻는다. 물어볼 사람은 딜 진행 관리의
`미팅 후기` 표에 이미 줄로 서 있는데, **그 줄에서 갈 길이 없었다** — 화면을
옮겨 담당자를 목록에서 다시 찾아 골라야 했고, 그러다 엉뚱한 곳에 나간다.

못 박는 것은 넷이다.

1. **투자사명이 그 길로 이어진다** — `/deals?mode=review&contacts=…`.
2. **문구를 새로 짓지 않는다.** `meeting_review` 를 짓는 자리는 이미 있다
   (`routers/deals.MODE_TEMPLATE_KIND[MODE_REVIEW]`).
3. **원래 가던 곳을 빼앗지 않는다.** 이 칸은 링크가 아니었고, 옆의
   [2차 미팅 잡기] 도 그대로다.
4. **누르는 것으로는 아무것도 안 나간다.** 발송 앞에는 사람이 선다.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from datetime import date
from pathlib import Path

import pytest

from .conftest import DEMO_PASSWORD

ROOT = Path(__file__).resolve().parents[1]
REVIEW_JS_TEST = ROOT / "tests" / "js" / "ir_review_link_test.js"


@pytest.fixture()
def finished_meeting(client, db, users):
    """끝난 미팅 한 건 — 후기를 물어볼 자리."""
    from app.models import Meeting, VcContact

    contact = VcContact(user_id=users["u1"].id, name="홍길동", title="심사역",
                        firm="가나벤처스")
    db.add(contact)
    db.flush()
    db.add(Meeting(user_id=users["u1"].id, contact_id=contact.id,
                   company_name="샘플애그", kind="first",
                   scheduled_at="2026-08-24", status="done", outcome="review",
                   followup_due="2026-09-03"))
    db.commit()
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    return {"client": client, "contact": contact}


def _reviews_panel(html: str) -> str:
    """`미팅 후기` 판만 잘라 본다 — 위 [전달한 자료] 표에도 이름 링크가 있다."""
    at = html.index('id="reviews"')
    return html[at:]


# --- 1. 투자사명이 그 길로 이어진다 ----------------------------------------------

def test_the_firm_name_opens_the_review_kakao(finished_meeting):
    contact = finished_meeting["contact"]
    panel = _reviews_panel(finished_meeting["client"].get("/ir").text)

    assert f"/deals?mode=review&contacts={contact.id}" in panel, \
        "미팅 후기 표의 투자사명이 후기 카톡으로 안 이어진다"
    # 이름 줄 전체가 링크다 — 투자사명만 눌리게 하면 투자사명이 빈 줄에서는
    # 누를 곳이 없어진다(위 [전달한 자료] 의 이름과 같은 방식).
    link = re.search(
        r'<a class="req-link"\s+href="/deals\?mode=review&contacts=\d+"'
        r'[^>]*>(.*?)</a>', panel, re.S)
    assert link is not None, "이름 링크를 못 찾았다"
    assert "홍길동" in link.group(1) and "가나벤처스" in link.group(1)
    # 무엇이 일어날지 미리 말한다 — 카톡이 나가는 길이다.
    assert "미팅 후기" in panel and "카톡" in panel


def test_it_is_the_same_road_as_the_delivered_table(finished_meeting, db, users):
    """위 [전달한 자료] 의 이름이 여는 길과 **같은 주소**이고 방식만 다르다.

    길을 새로 내면 한쪽만 고쳐지는 날 두 이름이 다른 화면으로 간다.
    """
    from app.models import IrRequest

    # 위 표가 비어 있으면 견줄 것이 없다 — 전달한 자료 한 줄을 세운다.
    db.add(IrRequest(user_id=users["u1"].id,
                     contact_id=finished_meeting["contact"].id,
                     company_name="샘플애그", requested_at="2026-08-22",
                     status="delivered"))
    db.commit()

    html = finished_meeting["client"].get("/ir").text
    modes = set(re.findall(r'href="/deals\?mode=(\w+)&contacts=', html))
    assert {"meeting", "review"} <= modes, \
        f"두 표가 같은 주소를 쓰지 않는다: {modes}"


# --- 2. 문구를 새로 짓지 않는다 --------------------------------------------------

def test_the_wording_is_the_one_that_already_exists():
    """`meeting_review` 를 짓는 자리는 이미 있다 — 거기로 잇기만 한다."""
    from app.routers.deals import (FOLLOW_UP_MODES, MODE_REVIEW,
                                   MODE_TEMPLATE_KIND, MODES_WITH_COMPANIES)

    assert MODE_TEMPLATE_KIND[MODE_REVIEW] == "meeting_review"
    assert FOLLOW_UP_MODES[MODE_REVIEW][0] == "meeting_review"
    # 기업 목록 없이 문구만 나간다 — 이미 목록을 본 사람에게 다시 밀어 넣지 않는다.
    assert MODE_REVIEW not in MODES_WITH_COMPANIES

    # 화면에 그 탭이 실제로 서 있어야 링크가 갈 곳이 있다.
    html = (ROOT / "app" / "templates" / "deals.html").read_text(encoding="utf-8")
    assert 'data-mode="review"' in html


# --- 3. 원래 가던 곳을 안 빼앗는다 ------------------------------------------------

def test_the_second_meeting_button_is_still_there(finished_meeting):
    """옆의 [2차 미팅 잡기] 는 그대로다 — 흐름은 일직선이 아니다."""
    panel = _reviews_panel(finished_meeting["client"].get("/ir").text)
    assert "js-book-meeting" in panel and "2차 미팅" in panel


def test_a_canceled_meeting_gets_no_review_link(client, db, users):
    """**취소된 미팅에는 안 건다.** 있지도 않았던 미팅의 후기를 물을 수는 없다.

    옆 [2차 미팅 잡기] 가 취소 건을 빼는 것과 같은 까닭이다. 그때는 지금까지처럼
    글자로 둔다 — 이름이 사라지면 어느 줄인지 알 수 없다.
    """
    from app.models import Meeting, VcContact

    contact = VcContact(user_id=users["u1"].id, name="취소담당",
                        title="심사역", firm="다라벤처스")
    db.add(contact)
    db.flush()
    db.add(Meeting(user_id=users["u1"].id, contact_id=contact.id,
                   kind="first", scheduled_at="2026-08-24", status="canceled"))
    db.commit()
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})

    panel = _reviews_panel(client.get("/ir").text)
    assert "취소담당" in panel, "이름은 그대로 보여야 한다"
    assert f"/deals?mode=review&contacts={contact.id}" not in panel, \
        "취소된 미팅에 후기 요청 길이 걸렸다"


# --- 4. 확인 없이는 안 나간다 ----------------------------------------------------

def test_opening_the_link_sends_nothing(finished_meeting, db):
    """**누르자마자 나가면 안 된다.** 발송 앞에는 사람이 선다."""
    from app.models import SendJob

    before = db.query(SendJob).count()
    contact = finished_meeting["contact"]
    page = finished_meeting["client"].get(
        f"/deals?mode=review&contacts={contact.id}")

    assert page.status_code == 200
    assert db.query(SendJob).count() == before, \
        "화면을 여는 것만으로 발송 건이 생겼다"
    # 넘어간 화면에는 보내기 전에 보는 자리가 있다
    assert "미팅 후기" in page.text


def test_the_browser_side_reads_that_address():
    """주소가 맞아도 `deals.js` 가 안 읽으면 빈 화면이 열린다 — 눌러 봐야 안다.

    로컬에서는 `node tests/js/ir_review_link_test.js` 로도 돈다.
    """
    node = shutil.which("node")
    if node is None:
        pytest.skip("node 미설치 — 브라우저 로직 테스트 생략 "
                    "(호스트에서 `node tests/js/ir_review_link_test.js`)")
    result = subprocess.run([node, str(REVIEW_JS_TEST)], capture_output=True,
                            text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
