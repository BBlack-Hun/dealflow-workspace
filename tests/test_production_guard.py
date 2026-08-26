"""운영으로 뜰 때 기본값이 그대로면 막는다.

저장소가 **공개**라, 코드에 적힌 기본 토큰·비밀번호는 이미 아무나 아는 값이다.
로컬에서는 편의를 위해 그 기본값을 쓰지만 인터넷에 올리는 순간 구멍이 된다.

"운영에서는 바꿔 쓸 것" 이라는 주석은 지켜지지 않는다 — 시작을 막는다.
"""
from __future__ import annotations

import importlib

import pytest


def _config(monkeypatch, **env):
    """환경변수를 바꿔 config 를 다시 읽는다."""
    from app import config as cfg

    for key in ("DEALFLOW_ENV", "DEALFLOW_AGENT_TOKEN",
                "DEALFLOW_INITIAL_PASSWORD", "DEALFLOW_SEED_DEMO"):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return importlib.reload(cfg)


@pytest.fixture(autouse=True)
def _restore():
    """다른 테스트가 쓰는 전역 설정을 원래대로 돌려놓는다."""
    yield
    from app import config as cfg

    importlib.reload(cfg)


def test_local_runs_with_the_defaults(monkeypatch):
    """로컬에서까지 막으면 개발할 때마다 값을 채워야 한다."""
    cfg = _config(monkeypatch)
    assert not cfg.IS_PRODUCTION
    cfg.assert_ready()          # 아무 일도 없어야 한다


def test_production_refuses_the_repo_default_token(monkeypatch):
    """이 토큰을 아는 사람은 발송 대기열에서 보낼 문구 전문을 가져간다."""
    cfg = _config(monkeypatch, DEALFLOW_ENV="production",
                  DEALFLOW_INITIAL_PASSWORD="바꾼비밀번호")
    with pytest.raises(RuntimeError) as err:
        cfg.assert_ready()
    assert "DEALFLOW_AGENT_TOKEN" in str(err.value)


def test_production_refuses_the_repo_default_password(monkeypatch):
    cfg = _config(monkeypatch, DEALFLOW_ENV="production",
                  DEALFLOW_AGENT_TOKEN="agt_real_secret")
    with pytest.raises(RuntimeError) as err:
        cfg.assert_ready()
    assert "DEALFLOW_INITIAL_PASSWORD" in str(err.value)


def test_production_refuses_demo_seed(monkeypatch):
    """실데이터 위에 가상 기업이 섞이면 어느 것이 진짜인지 알 수 없다."""
    cfg = _config(monkeypatch, DEALFLOW_ENV="production",
                  DEALFLOW_AGENT_TOKEN="agt_real_secret",
                  DEALFLOW_INITIAL_PASSWORD="바꾼비밀번호",
                  DEALFLOW_SEED_DEMO="1")
    with pytest.raises(RuntimeError) as err:
        cfg.assert_ready()
    assert "SEED_DEMO" in str(err.value)


def test_production_starts_when_everything_is_set(monkeypatch):
    cfg = _config(monkeypatch, DEALFLOW_ENV="production",
                  DEALFLOW_AGENT_TOKEN="agt_real_secret",
                  DEALFLOW_INITIAL_PASSWORD="바꾼비밀번호")
    assert cfg.IS_PRODUCTION
    cfg.assert_ready()


def test_all_problems_are_listed_at_once(monkeypatch):
    """하나 고치고 다시 떠서 또 막히면, 몇 번을 반복해야 하는지 모른다."""
    cfg = _config(monkeypatch, DEALFLOW_ENV="production",
                  DEALFLOW_SEED_DEMO="1")
    problems = cfg.production_problems()
    assert len(problems) == 3
