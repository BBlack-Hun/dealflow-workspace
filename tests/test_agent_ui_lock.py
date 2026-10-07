"""한 PC 에서 발송기 둘이 **동시에** 카톡을 만지지 않는가 (0.11.5).

같은 컴퓨터 이름으로 계정이 다른 발송기 둘이 함께 폴링하고 있었다. 서버에서는
다른 기기라 잡을 각자 집어가지만 화면의 카카오톡은 하나다. 잡을 집기 **전에**
PC 잠금을 잡고, 못 잡으면 폴링하지 않는다(잡은 서버 큐에 그대로 선다).
"""
from __future__ import annotations

import subprocess
import sys

from agent import main as agent_main


class Client:
    def __init__(self, job=None):
        self.job = job
        self.polls = 0

    def poll(self):
        self.polls += 1
        return self.job


def test_잠금은_한_번에_하나만(tmp_path):
    path = tmp_path / "ui.lock"
    a, b = agent_main.UiLock(path), agent_main.UiLock(path)
    assert a.acquire()
    assert not b.acquire()
    a.release()
    assert b.acquire()
    b.release()


def test_다른_프로세스가_쥐고_있으면_못_잡는다(tmp_path):
    path = tmp_path / "ui.lock"
    holder = subprocess.Popen(
        [sys.executable, "-c",
         "import sys,time; from agent.main import UiLock; l=UiLock(sys.argv[1]); "
         "assert l.acquire(); print('held', flush=True); time.sleep(30)", str(path)],
        stdout=subprocess.PIPE, text=True)
    try:
        assert holder.stdout.readline().strip() == "held"
        assert not agent_main.UiLock(path).acquire()
    finally:
        holder.kill()
        holder.wait()
    # 쥔 프로세스가 죽으면 OS 가 풀어 준다 — 남아서 막히지 않는다.
    lock = agent_main.UiLock(path)
    assert lock.acquire()
    lock.release()


def test_다른_발송기가_보내는_중이면_폴링하지_않는다(tmp_path, monkeypatch):
    path = tmp_path / "ui.lock"
    other = agent_main.UiLock(path)
    assert other.acquire()
    client = Client(job={"job_id": 1, "items": []})
    called = []
    monkeypatch.setattr(agent_main, "process_job", lambda *a: called.append(a))
    out = agent_main.poll_and_process(client, None, {}, agent_main.UiLock(path))
    assert out == "busy"
    assert client.polls == 0          # 잡을 집지 않는다 — 서버 큐에 그대로
    assert called == []
    other.release()


def test_잡을_처리하고_나면_잠금을_푼다(tmp_path, monkeypatch):
    path = tmp_path / "ui.lock"
    monkeypatch.setattr(agent_main, "process_job", lambda *a: None)
    mine = agent_main.UiLock(path)
    assert agent_main.poll_and_process(Client(job={"job_id": 1}), None, {}, mine) == "done"
    assert agent_main.poll_and_process(Client(job=None), None, {}, mine) == "idle"
    other = agent_main.UiLock(path)
    assert other.acquire()
    other.release()


def test_처리_중_터져도_잠금을_푼다(tmp_path, monkeypatch):
    path = tmp_path / "ui.lock"

    def boom(*a):
        raise RuntimeError("터졌다")

    monkeypatch.setattr(agent_main, "process_job", boom)
    mine = agent_main.UiLock(path)
    try:
        agent_main.poll_and_process(Client(job={"job_id": 1}), None, {}, mine)
    except RuntimeError:
        pass
    other = agent_main.UiLock(path)
    assert other.acquire()
    other.release()


def test_잠금_파일을_못_열면_예전처럼_돈다(tmp_path):
    lock = agent_main.UiLock(tmp_path / "없는_폴더" / "ui.lock")
    assert lock.acquire()
    lock.release()
