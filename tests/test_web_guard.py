"""웹 방어 — 쓰기 요청의 출처 검사 · CSP · 운영의 API 문서.

세 가지 모두 `app/main.py` 의 미들웨어·앱 설정 한 곳에 있다.
"""
from __future__ import annotations

import re
from pathlib import Path

from .conftest import DEMO_TOKEN, auth

OTHER_SITE = "https://other.example"


def _new_contact(client, name, **headers):
    return client.post("/api/contacts", json={"name": name, "firm": "가나벤처스"},
                       headers=headers)


def _names(db):
    from app.models import VcContact

    db.expire_all()
    return {c.name for c in db.query(VcContact).all()}


# --- 쓰기 요청의 출처 ---------------------------------------------------------

def test_a_write_from_another_site_is_refused(logged_in, db):
    r = _new_contact(logged_in, "밖에서", Origin=OTHER_SITE)
    assert r.status_code == 403
    assert "밖에서" not in _names(db)


def test_a_referer_from_another_site_is_refused_too(logged_in, db):
    """`Origin` 이 없으면 `Referer` 를 본다."""
    r = _new_contact(logged_in, "밖에서", Referer=f"{OTHER_SITE}/page")
    assert r.status_code == 403
    assert "밖에서" not in _names(db)


def test_a_null_origin_is_refused(logged_in, db):
    """브라우저는 출처를 숨길 때 `null` 을 싣는다 — 이 사이트의 화면이 아니다."""
    assert _new_contact(logged_in, "밖에서", Origin="null").status_code == 403


def test_a_write_from_this_site_goes_through(logged_in, db):
    assert _new_contact(logged_in, "안에서",
                        Origin="http://testserver").status_code == 200
    assert _new_contact(logged_in, "안에서2",
                        Referer="http://testserver/contacts").status_code == 200
    assert {"안에서", "안에서2"} <= _names(db)


def test_without_origin_or_referer_it_goes_through(logged_in, db):
    """브라우저 밖 도구(검사 · 스크립트)는 그 머리글을 싣지 않는다."""
    assert _new_contact(logged_in, "도구에서").status_code == 200


def test_the_host_is_compared_not_a_fixed_domain(logged_in, db):
    """테스트 서버는 윈도우 PC 에서 IP·포트로 연다 — 그 주소 그대로 통과한다."""
    here = "192.168.0.5:8889"
    assert _new_contact(logged_in, "IP 로", Host=here,
                        Origin=f"http://{here}").status_code == 200
    assert _new_contact(logged_in, "다른 포트", Host=here,
                        Origin="http://192.168.0.5:9999").status_code == 403


def test_reads_are_not_checked(logged_in):
    assert logged_in.get("/contacts", headers={"Origin": OTHER_SITE}).status_code == 200


def test_the_agent_api_is_not_checked(client):
    """발송기 API 는 토큰으로 묻는다 — 출처를 보지 않는다."""
    r = client.post("/api/agent/heartbeat", json={},
                    headers={**auth(DEMO_TOKEN), "Origin": OTHER_SITE})
    assert r.status_code == 200


# --- CSP ----------------------------------------------------------------------

def test_every_response_carries_the_csp(logged_in):
    from app.main import CONTENT_SECURITY_POLICY

    for path in ("/contacts", "/login", "/static/css/app.css"):
        assert logged_in.get(path).headers["content-security-policy"] \
            == CONTENT_SECURITY_POLICY, path
    # 미들웨어가 바로 돌려주는 차단 응답에도 붙는다.
    blocked = _new_contact(logged_in, "밖에서", Origin=OTHER_SITE)
    assert blocked.headers["content-security-policy"] == CONTENT_SECURITY_POLICY


def test_the_csp_blocks_what_the_screens_do_not_use():
    from app.main import CONTENT_SECURITY_POLICY as csp

    for rule in ("default-src 'self'", "script-src 'self' 'unsafe-inline'",
                 "object-src 'none'", "base-uri 'none'",
                 "frame-ancestors 'none'", "form-action 'self'"):
        assert rule in csp, rule


def test_the_screens_load_nothing_from_outside():
    """CSP 가 바깥 자원을 막는다 — 화면이 바깥 것을 부르면 그 자리가 깨진다.

    바깥 스크립트·스타일·그림·틀·폼 주소가 생기면 `CONTENT_SECURITY_POLICY` 를
    먼저 고쳐야 한다. 그것을 잊지 않게 여기서 잡는다.
    """
    root = Path(__file__).resolve().parent.parent / "app"
    outside = re.compile(
        r"<(script|img|iframe|embed|object|source)\b[^>]*\bsrc=\"(https?:)?//"
        r"|<link\b[^>]*\bhref=\"(https?:)?//"
        r"|<form\b[^>]*\baction=\"(https?:)?//"
        r"|<(iframe|object|embed|base)\b"
        r"|@import|url\(\s*['\"]?(https?:)?//"
        r"|fetch\(\s*['\"`](https?:)?//", re.I)
    found = []
    for path in [*root.glob("templates/**/*.html"), *root.glob("static/**/*.js"),
                 *root.glob("static/**/*.css")]:
        for m in outside.finditer(path.read_text(encoding="utf-8")):
            found.append(f"{path.relative_to(root)}: {m.group(0)}")
    assert found == []


# --- 운영의 API 문서 ------------------------------------------------------------

def _paths(app):
    return {getattr(r, "path", "") for r in app.routes}


def test_api_docs_stay_open_locally(db):
    from app.main import create_app

    assert {"/docs", "/redoc", "/openapi.json"} <= _paths(create_app())


def test_api_docs_are_off_in_production(db, users, monkeypatch):
    from fastapi.testclient import TestClient

    from app import config
    from app.main import create_app

    monkeypatch.setattr(config, "IS_PRODUCTION", True)
    # 운영 설정 검사(기본 토큰 등)는 여기서 보는 것이 아니다.
    monkeypatch.setattr(config, "assert_ready", lambda: None)
    app = create_app()
    assert not {"/docs", "/redoc", "/openapi.json"} & _paths(app)
    with TestClient(app) as c:
        for path in ("/docs", "/redoc", "/openapi.json"):
            assert c.get(path, follow_redirects=False).status_code != 200, path
