"""Quartz(pyobjc)가 없어도 에이전트가 죽지 않는지 확인.

실기에서 Python 3.9 + pyobjc 12.0 조합이 소스 빌드로 넘어가 설치에 실패했고,
그 실패가 requests 설치까지 롤백시켜 에이전트가 아예 뜨지 않았다.
Quartz 는 '채팅방을 검색해서 새로 여는' 경로에만 쓰이므로,
없으면 그 기능만 비활성화되고 발송 경로는 살아 있어야 한다.
"""
import builtins
import sys

import pytest

from agent.sender import kakao_mac


@pytest.fixture
def no_quartz(monkeypatch):
    """import Quartz 가 실패하는 상황을 흉내낸다."""
    monkeypatch.delitem(sys.modules, "Quartz", raising=False)
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "Quartz":
            raise ImportError("No module named 'Quartz'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)


def test_quartz_available_false_when_missing(no_quartz):
    assert kakao_mac.quartz_available() is False


def test_double_click_raises_actionable_error(no_quartz):
    """크래시가 아니라, 무엇을 하면 되는지 알려주는 예외여야 한다."""
    with pytest.raises(kakao_mac.QuartzUnavailable) as exc:
        kakao_mac._double_click(10, 10)
    msg = str(exc.value)
    assert "채팅방 창을 미리 열어두면" in msg   # 대안 안내
    assert "Quartz" in msg


def test_module_imports_without_quartz(no_quartz):
    """모듈 임포트 자체는 Quartz 와 무관해야 한다(지연 임포트)."""
    import importlib

    mod = importlib.reload(kakao_mac)
    assert hasattr(mod, "KakaoMacSender")


def test_quartz_unavailable_is_runtime_error():
    """호출부가 광범위한 except 로 삼키지 않도록 명시적 예외 타입을 쓴다."""
    assert issubclass(kakao_mac.QuartzUnavailable, RuntimeError)
