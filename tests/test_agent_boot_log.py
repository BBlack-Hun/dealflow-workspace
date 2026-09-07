"""켤 때 화면에 무엇이 적히는가.

## 왜 이 파일이 있나

새 발송기를 받아 켰는데 서버에는 여전히 **옛 판(0.7.0)** 으로 올라와 있었다.
켠 사람은 새것을 켰다고 믿고 있었고, 화면 어디에도 판 번호가 없어 그 믿음을
확인할 길이 없었다. 판 번호는 서버에만 알리고(`heartbeat`) 정작 짚어야 할
사람 앞에는 안 적었던 것이다.

같은 날, 자료가 실린 잡이 안 내려오는 이유를 알아내려고 **서버 DB 를 뒤졌다** —
이 발송기가 "파일을 붙일 줄 안다" 고 밝혔는지가 화면에 없었기 때문이다.

그래서 켤 때 이만큼은 적는다: 판 번호 · 어느 발송기인지 · 파일 첨부를 할 줄
아는지 · 붙을 서버. 그리고 **토큰은 적지 않는다.**

여기서 보는 것은 문구의 예쁨이 아니라 **그 값이 정말 화면에 나오는가** 이다.
그래서 돌려받은 줄이 아니라 로그로 나간 것(`caplog`)을 견준다.
"""
from __future__ import annotations

import logging
import pathlib

import pytest

from agent import main as agent_main
from agent.version import VERSION as AGENT_VERSION

TOKEN = "agt_이건_절대_찍히면_안_되는_값"
SERVER = "https://dealflow.example.org"


def attached(sender="kakao_windows", *, files=False, cap=60):
    """발송기가 붙은 뒤의 `AgentClient`. 서버에 밝히는 값을 그대로 들고 있다."""
    c = agent_main.AgentClient({"server_url": SERVER + "/", "token": TOKEN,
                                "job_cap": cap})
    c.hostname = "테스트PC"
    c.sender_name = sender
    c.sender_can_send_files = files
    return c


@pytest.fixture()
def logged(caplog):
    """`log_startup` 이 **실제로 로그에 내보낸** 글자."""
    def run(*args, **kwargs):
        caplog.clear()
        with caplog.at_level(logging.INFO, logger="agent"):
            agent_main.log_startup(attached(*args, **kwargs))
        return caplog.text
    return run


# ══════════════════════════════════════════════════════════════════════════
#  판 번호 — 이것 하나 때문에 만들었다
# ══════════════════════════════════════════════════════════════════════════

def test_the_version_is_printed_when_it_starts(logged):
    """★ 켠 사람이 **어느 판을 켰는지** 화면에서 바로 본다."""
    assert f"v{AGENT_VERSION}" in logged(), "판 번호가 안 찍힌다"


def test_the_printed_version_is_the_agents_own(logged):
    """서버 쪽 값이 아니라 **이 발송기가 들고 있는 값**이어야 한다.

    두 파일이 갈리는 것은 `tests/test_version.py` 가 따로 잡는다. 여기서
    보는 것은 '찍히는 값이 그 파일에서 온다' 는 것이다.
    """
    from app import version as server_version

    text = logged()
    assert f"v{AGENT_VERSION}" in text
    assert AGENT_VERSION == server_version.VERSION, "두 판 번호가 갈렸다"


def test_the_version_is_printed_before_the_sender_is_built():
    """발송기를 세우다 터져도 **어느 판이 터졌는지**는 남아야 한다.

    함수 하나가 빠진 채 배포돼 사용자 PC 에서 터진 적이 있는데, 받은 쪽은
    그것이 낡은 것인지 고친 것인지 몰랐다. 그래서 요약 줄과 별개로 한 줄을
    `build_sender` **앞에** 둔다.
    """
    src = pathlib.Path("agent/main.py").read_text(encoding="utf-8")
    boot = src[src.index("def main("):]
    assert boot.index("VERSION") < boot.index("build_sender(cfg)"), (
        "판 번호가 build_sender 뒤에서만 찍힌다 — 세우다 터지면 안 남는다")


def test_the_summary_actually_runs_when_it_starts():
    """요약을 만들어 놓고 부르지 않으면 아무 데도 안 찍힌다.

    `quartz_available()` 이 있는데 아무도 안 불러서 몇 달을 놓친 적이 있다.
    """
    src = pathlib.Path("agent/main.py").read_text(encoding="utf-8")
    assert "log_startup(client)" in src[src.index("def main("):]


# ══════════════════════════════════════════════════════════════════════════
#  ★ 토큰은 적지 않는다
# ══════════════════════════════════════════════════════════════════════════

def test_the_token_is_never_printed(logged):
    """이 로그는 파일로 남고, 그 꼬리가 진단 스냅샷에 실려 서버로 올라간다.
    사람이 화면을 찍어 붙이기도 한다. 토큰이 섞이면 되돌릴 수 없다."""
    for sender, files in [("kakao_windows", False), ("kakao_mac", True),
                          ("mock", False), ("telegram", False)]:
        text = logged(sender, files=files)
        assert TOKEN not in text, f"{sender}: 토큰이 찍혔다"
        assert "Bearer" not in text
        assert "agt_" not in text


def test_the_token_is_not_hiding_in_the_server_address(logged):
    """주소는 적지만 그 주소에 열쇠가 붙어 나가면 안 된다."""
    text = logged()
    assert SERVER in text
    assert "token" not in text.lower()


# ══════════════════════════════════════════════════════════════════════════
#  어느 발송기인가 — 실제로 카톡으로 나가는가
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("sender", ["kakao_windows", "kakao_mac", "mock", "telegram"])
def test_it_says_which_sender_is_attached(logged, sender):
    assert sender in logged(sender)


def test_a_pretend_sender_says_so(logged):
    """★ mock 인 줄 모르고 회차를 돌리면 아무 데도 안 나간다 — 이름만으로는
    그것이 안 드러난다."""
    text = logged("mock")
    assert "아무것도 나가지 않습니다" in text


def test_a_real_sender_says_so(logged):
    assert "실제 카카오톡" in logged("kakao_windows")
    assert "실제 카카오톡" in logged("kakao_mac")


def test_an_unknown_sender_is_not_dressed_up_as_real(logged):
    """모르는 발송기를 '실제로 나간다' 고 적으면 그 줄이 거짓말이 된다."""
    text = logged("무언가새로운것")
    assert "실제 카카오톡" not in text
    assert "모릅니다" in text


# ══════════════════════════════════════════════════════════════════════════
#  파일 첨부 — 자료 잡이 왜 안 내려오는지 화면에서 보이게
# ══════════════════════════════════════════════════════════════════════════

def test_a_sender_that_can_attach_files_says_so(logged):
    text = logged("kakao_mac", files=True)
    assert "파일 첨부 켜짐" in text
    assert "실린 잡도 받습니다" in text


def test_a_sender_that_cannot_says_the_jobs_will_not_come(logged):
    """★ 이것을 몰라서 서버 DB 를 뒤졌다. '꺼짐' 만으로는 부족하다 —
    **그래서 무슨 일이 벌어지는지**(잡이 안 온다) 까지 적는다."""
    text = logged("kakao_mac", files=False)
    assert "파일 첨부 꺼짐" in text
    assert "실린 잡은 오지 않습니다" in text


def test_the_two_senders_do_not_read_the_same(logged):
    assert logged("kakao_mac", files=True) != logged("kakao_mac", files=False)


def test_windows_is_told_where_the_switch_is(logged):
    """켜는 손잡이를 못 찾아서 서버 DB 를 뒤진 것이라, 그 이름을 같이 적는다."""
    from agent.sender.kakao_windows import FILE_SEND_ENV

    assert FILE_SEND_ENV in logged("kakao_windows", files=False)


def test_the_switch_is_not_mentioned_where_it_does_nothing(logged):
    """맥·mock 에서 Windows 손잡이를 알려 주면 엉뚱한 데를 뒤지게 된다."""
    from agent.sender.kakao_windows import FILE_SEND_ENV

    assert FILE_SEND_ENV not in logged("kakao_mac", files=False)
    assert FILE_SEND_ENV not in logged("mock", files=False)
    assert FILE_SEND_ENV not in logged("kakao_windows", files=True)


# ══════════════════════════════════════════════════════════════════════════
#  붙을 자리 · 서버에 밝히는 값
# ══════════════════════════════════════════════════════════════════════════

def test_it_says_which_server_it_will_talk_to(logged):
    assert SERVER in logged()


def test_it_says_which_jobs_it_will_take(logged):
    """잡이 큐에 멈춰 있는 이유가 여기 있을 수 있다 — 서버가 만든 종류를
    이 발송기가 안 받으면 그대로 남는다(실제로 소싱 제안이 그랬다)."""
    text = logged()
    for kind in agent_main.SUPPORTED_KINDS:
        assert kind in text


def test_it_says_how_many_it_takes_at_once(logged):
    assert "97건" in logged(cap=97)


def test_what_is_printed_is_what_the_server_is_told():
    """★ 화면에 적힌 것과 서버가 받는 것이 갈리면 이 줄들이 쓸모없어진다.

    폴링에 실어 보내는 값(`kinds`·`files`·`cap`)을 그대로 적는지 본다.
    """
    c = attached("kakao_mac", files=True, cap=42)
    lines = "\n".join(agent_main.log_startup(c))

    sent = {}

    class FakeResponse:
        status_code = 204

    def fake_get(url, params=None, timeout=None):
        sent.update(params or {})
        return FakeResponse()

    c.session.get = fake_get
    c.poll()

    assert str(sent["cap"]) in lines
    assert sent["files"] == 1 and "파일 첨부 켜짐" in lines
    for kind in sent["kinds"].split(","):
        assert kind in lines


# ══════════════════════════════════════════════════════════════════════════
#  시험 모드 — 서버가 알려주지 않는 것은 지어내지 않는다
# ══════════════════════════════════════════════════════════════════════════

def test_the_agent_is_not_told_whether_the_server_is_in_test_mode():
    """시험 모드(`DEALFLOW_TEST_ROOM`)는 **서버만 안다.**

    발송기에 내려오는 통로가 없다 — 박동 응답에 실리는 것은 IR 자료 폴더 자리
    하나뿐이다. 그래서 켤 때 그것을 적지 않는다. 모르는 것을 아는 척 적으면
    그 줄이 곧 거짓말이 된다.

    이 검사는 **통로가 생기면 깨진다.** 그때는 켜는 줄에도 같이 적어야 한다.
    """
    import inspect

    from app.routers import agent_api

    body = inspect.getsource(agent_api.heartbeat)
    assert "test_room" not in body and "TEST_ROOM" not in body, (
        "서버가 시험 모드를 알려주기 시작했다 — 켤 때 적는 줄에도 넣어야 한다")
