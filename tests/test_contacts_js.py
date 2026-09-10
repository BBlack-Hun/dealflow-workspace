"""내 투자사 화면(JS)을 node 로 돌려 본다.

로직이 브라우저에 있으므로 테스트도 같은 언어로 둔다(tests/test_filters_js.py 와 같은 방식).
node 가 없는 환경(운영 도커 이미지)에서는 건너뛴다 — 브라우저 자산 테스트라
서버 실행에 필요한 의존성이 아니다. 로컬에서는 `node tests/js/contacts_open_test.js` 로도 돈다.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

OPEN_TEST = Path(__file__).resolve().parent / "js" / "contacts_open_test.js"
TRANSFER_TEST = Path(__file__).resolve().parent / "js" / "contact_transfer_test.js"
SORT_TEST = Path(__file__).resolve().parent / "js" / "contacts_sort_test.js"
DELETE_TEST = Path(__file__).resolve().parent / "js" / "hidden_delete_test.js"


@pytest.mark.skipif(shutil.which("node") is None, reason="node 미설치 — 브라우저 로직 테스트 생략")
def test_dashboard_link_actually_opens_the_detail_panel():
    """대시보드에서 눌러 와도 상세가 안 열린다 — 함수가 다른 IIFE 안에 갇혀 있다.

    '내 투자사 선호'에서 사람을 누르면 /contacts?contact=<id> 로 온다. 화면은
    window.DEALFLOW_OPEN_CONTACT 에 번호를 적어 두고 contacts.js 가 그것을 보고
    상세를 여는데, 그 몇 줄이 상세 패널과 **다른 IIFE** 에 떨어져 있어서
    loadContact 이라는 이름이 닿지 않았다. ReferenceError 로 죽고 목록만 남는다 —
    오류는 콘솔에만 있어 눈에 안 띈다.

    `<script>` 태그가 그려지는지만 보는 검사(test_dashboard.py)로는 못 잡는다.
    그래서 여기서는 가짜 DOM 위에 contacts.js 를 **실제로 실행**해서, 번호를 주면
    /api/contacts/<id> 를 부르고 패널이 정말 열리는지까지 본다.
    """
    node = shutil.which("node")
    result = subprocess.run(
        [node, str(OPEN_TEST)], capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.skipif(shutil.which("node") is None, reason="node 미설치 — 브라우저 로직 테스트 생략")
def test_transfer_confirm_names_who_goes_where():
    """이관 확인창이 **누구를 누구에게** 넘기는지, 월별 기록이 어찌 되는지 말하는가.

    이관은 되돌리기 번거로운 조작이라 사람이 마지막에 보는 것이 그 한 줄이다.
    이름이 빠지면 엉뚱한 줄을 넘겨도 모르고, 월별 기록 이야기가 빠지면 기록이
    날아간 줄 알고 다시 적는다(달마다 늘어나는 칸은 명단마다 따로라 옛 기록이
    새 명단의 수정창에 안 뜬다 — 지워지는 것은 아니다).

    취소를 눌렀을 때 한 건도 안 나가는지까지 본다. 확인창을 띄워 놓고 이미
    보내 버리면 확인창은 장식일 뿐이다.
    """
    node = shutil.which("node")
    result = subprocess.run(
        [node, str(TRANSFER_TEST)], capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.skipif(shutil.which("node") is None, reason="node 미설치 — 브라우저 로직 테스트 생략")
def test_이름_머리글을_눌러_정렬하고_NO_를_다시_매기는가():
    """투자사 관리 현황을 **이름으로 세운다** — 그리고 세운 뒤에 `NO` 를 다시 매긴다.

    세우는 일 자체는 주간 업무가 쓰던 부품이 한다(`table_sort.js`) — 화면마다
    정렬기를 새로 만들면 "빈 값은 어디로 가나" 같은 판단이 두 벌이 되어 한쪽만
    낡는다. 그래서 여기서 보는 것은 **그 부품이 이 표에 물렸는가**와, 이 화면에만
    있는 두 가지다.

    · `NO` 는 보이는 것 기준 1,2,3… 이라 **차례가 곧 번호**다. 줄을 세우고 번호를
      안 다시 매기면 정렬한 표의 번호가 `3,5,1,4,2` 로 남아 목록을 셀 수가 없다.
    · 검색·필터를 걸어 둔 채로 머리글을 눌렀을 때 감춰 둔 줄이 되살아나면,
      세우는 순간 걸어 둔 조건이 풀린다.

    로컬에서는 `node tests/js/contacts_sort_test.js` 로도 돈다.
    """
    result = subprocess.run(
        [shutil.which("node"), str(SORT_TEST)], capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.skipif(shutil.which("node") is None, reason="node 미설치 — 브라우저 로직 테스트 생략")
def test_감춘_줄을_골라_지우는_길이_실수를_막는가():
    """감춘 줄 [선택 삭제] — **되돌릴 수 없는 조작**이라 화면 쪽 잠금을 잰다.

    서버 쪽(누가 지울 수 있나 · 무엇이 막히나 · 로그에 남나)은
    `tests/test_contacts_bulk_delete.py` 가 본다. 여기서만 잴 수 있는 것이 넷이다.

    · [전체 선택]이 **검색·필터로 감춰 둔 줄까지** 켜면, 사람이 못 보는 줄이
      그대로 사라진다(딜 제안 관리의 [전체선택]이 같은 함정을 안고 있었다).
    · 확인창에서 [취소]를 눌렀는데 이미 나가 버리면 확인창은 장식이다.
    · 확인 전에 서버에 묻는 부름이 `confirm: true` 로 나가면 세어 보기가 곧
      삭제가 된다.
    · 못 지우는 줄이 섞여 있을 때 체크를 풀고 멈추는가 — 그대로 나머지를
      지우면 고른 것과 사라진 것이 달라진다.

    로컬에서는 `node tests/js/hidden_delete_test.js` 로도 돈다.
    """
    result = subprocess.run(
        [shutil.which("node"), str(DELETE_TEST)], capture_output=True, text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
