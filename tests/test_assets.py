"""고친 CSS·JS 가 브라우저에 실제로 닿는가.

숫자 칸 먹통을 고쳐 배포했는데 "아직 그대로" 라는 말을 들었다. 서버는 고친
파일을 주고 있었고, **브라우저가 옛 것을 쓰고 있었다.** 주소가 같으니 다시
받을 이유가 없었던 것이다.

고친 것이 안 보이는 쪽이, 조금 느린 것보다 훨씬 나쁘다.
"""
from __future__ import annotations

import re

import pytest

from app import assets

from .conftest import DEMO_PASSWORD


@pytest.fixture(autouse=True)
def _fresh():
    assets.reset()
    yield
    assets.reset()


def test_static_urls_carry_a_fingerprint(client, db, users):
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})

    for path in ("/", "/companies", "/contacts", "/deals", "/todo", "/ir"):
        body = client.get(path).text
        bare = re.findall(r'(?:src|href)="(/static/[^"?]+)"', body)
        assert not bare, f"{path}: 지문 없는 정적 주소 {bare}"

        marked = re.findall(r'(?:src|href)="/static/[^"]+\?v=([a-f0-9]{8})"', body)
        assert marked, f"{path}: 정적 파일을 하나도 안 부른다"


def test_the_login_page_too(client):
    """로그인 화면은 base.html 을 안 거칠 수 있다 — 거기만 캐시에 물리면
    고친 CSS 가 로그인에서만 옛 것이 된다."""
    body = client.get("/login").text
    assert not re.findall(r'(?:src|href)="(/static/[^"?]+)"', body)


def test_the_fingerprint_follows_the_contents(tmp_path, monkeypatch):
    """배포 시각이나 버전 번호로 하면, 고쳤는데 안 올린 경우에 또 물린다."""
    from app import config

    static = tmp_path / "static"
    (static / "js").mkdir(parents=True)
    target = static / "js" / "x.js"
    target.write_text("hello", encoding="utf-8")
    monkeypatch.setattr(config, "STATIC_DIR", static)
    monkeypatch.setattr(assets.config, "STATIC_DIR", static)

    first = assets.asset("js/x.js")
    assert re.fullmatch(r"/static/js/x\.js\?v=[a-f0-9]{8}", first), first

    target.write_text("hello world", encoding="utf-8")
    assets.reset()
    assert assets.asset("js/x.js") != first, "내용이 바뀌었는데 주소가 그대로다"


def test_a_missing_file_still_gets_a_usable_link(tmp_path, monkeypatch):
    from app import config

    monkeypatch.setattr(config, "STATIC_DIR", tmp_path)
    monkeypatch.setattr(assets.config, "STATIC_DIR", tmp_path)
    assert assets.asset("js/없는파일.js") == "/static/js/없는파일.js"


def test_fingerprinted_files_are_cached_hard(client):
    """지문이 붙으면 내용이 바뀔 때 주소가 달라지므로 오래 잡아 둬도 안전하다."""
    marked = client.get("/static/css/app.css?v=deadbeef")
    assert "immutable" in marked.headers.get("cache-control", "")

    bare = client.get("/static/css/app.css")
    assert bare.headers.get("cache-control") == "no-cache", \
        "지문 없이 부른 주소까지 오래 캐시하면 고친 것이 안 보인다"


def test_pages_are_never_cached(client, db, users):
    """화면은 캐시하면 안 된다 — 고친 숫자가 예전 값으로 보인다."""
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    assert "no-store" in client.get("/").headers.get("cache-control", "")
