"""예약 발송의 **화면 쪽**(JS)을 node 로 돌려 본다.

로직이 브라우저에 있으므로 검사도 같은 언어로 둔다(`tests/test_contacts_js.py`
와 같은 방식). node 가 없는 환경(운영 도커 이미지)에서는 건너뛴다 — 브라우저
자산 검사라 서버 실행에 필요한 의존성이 아니다. 로컬에서는
`node tests/js/progress_schedule_test.js` 로도 돈다.

**래퍼가 없으면 CI 가 영영 안 돈다** — node 검사만 더해 두면 아무도 부르지
않는다.

여기서 하나 더 본다: 가짜 화면 위의 검사는 **아이디를 바꿔도 통과한다.** 그래서
진짜로 그려지는 화면에 그 아이디들이 있는지는 파이썬이 따로 본다.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from .conftest import DEMO_PASSWORD

SCHEDULE_TEST = Path(__file__).resolve().parent / "js" / "progress_schedule_test.js"

#: `progress.js` 가 찾는 자리들. 하나라도 없으면 그 코드는 조용히 아무 일도
#: 하지 않고, 예약은 걸 수도 볼 수도 없게 된다.
IDS = ("schedule-box", "schedule-note", "schedule-at", "schedule-btn",
       "unschedule-btn", "schedule-hint", "standing-note")


@pytest.mark.skipif(shutil.which("node") is None,
                    reason="node 미설치 — 브라우저 로직 테스트 생략")
def test_예약_자리가_화면에서_실제로_도는가():
    """진짜 `progress.js` 를 가짜 화면 위에서 돌려 본다.

    무엇을 지키는지는 `tests/js/progress_schedule_test.js` 머리말에 있다 —
    걸어 둔 예약이 보이는가, 09~19 밖을 누르기 전에 막는가, 취소가 묻는가,
    서 있는 잡과 막힌 잡을 가리는가, 폴링이 고치던 값을 덮어쓰지 않는가.
    """
    result = subprocess.run([shutil.which("node"), str(SCHEDULE_TEST)],
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr


def test_진행_화면에_예약_자리가_그려지는가(client, db, users):
    """그려지는 HTML 에 그 아이디들이 정말 있는가.

    가짜 화면 위의 검사만으로는 못 잡는다 — 거기서는 아이디를 바꿔도 통과한다.
    """
    from app.models import SendJob

    job = SendJob(user_id=users["u1"].id, kind="deal_intro", status="draft",
                  total=0)
    db.add(job)
    db.commit()

    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    page = client.get(f"/jobs/{job.id}")

    assert page.status_code == 200
    for name in IDS:
        assert f'id="{name}"' in page.text, f"{name} 자리가 화면에 없다"


def test_발송_화면에_예약_시각_칸이_있는가(client, db, users):
    """딜 소개를 보내는 그 자리에 **언제 보낼지** 고르는 칸이 있는가.

    고를 수 있는 폭은 서버가 실어 준다 — 화면에 숫자를 박아 두면 막는 자리와
    안내하는 자리가 다른 말을 하는 날이 온다.
    """
    from app.services import scheduled_send

    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    page = client.get("/deals")

    assert page.status_code == 200
    assert 'id="send-at"' in page.text
    assert f'data-earliest="{scheduled_send.EARLIEST_HOUR}"' in page.text
    assert f'data-latest="{scheduled_send.LATEST_HOUR}"' in page.text
