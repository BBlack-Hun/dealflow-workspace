"""내려받은 발송기 config.yaml 의 server_url — 운영 도메인이 있으면 https 로 굽는다.

운영은 Caddy 뒤라 접속 주소(`request.base_url`)가 http 로 잡힐 수 있다.
"""
from __future__ import annotations

import io
import zipfile


def _config(client) -> str:
    body = client.get("/download/agent?os_kind=windows").content
    with zipfile.ZipFile(io.BytesIO(body)) as zf:
        return zf.read("agent/config.yaml").decode("utf-8")


def test_domain_set_bakes_https_domain(logged_in, monkeypatch):
    monkeypatch.setenv("DEALFLOW_DOMAIN", "deal.example.org")
    assert 'server_url: "https://deal.example.org"' in _config(logged_in)


def test_no_domain_falls_back_to_the_visited_address(logged_in, monkeypatch):
    """로컬 테스트 서버(8889)는 도메인이 없다 — 접속한 주소 그대로."""
    monkeypatch.setenv("DEALFLOW_DOMAIN", "")
    assert 'server_url: "http://testserver"' in _config(logged_in)
