"""설치 화면(`/setup`)과 계정 화면의 글자 — 무엇이 보이고 무엇이 가려지는가.

연결키 · 로그인 아이디는 화면 공유·캡처 한 번이면 나간다. 가리되, 그 값을 쓰는
길(설치 파일 내려받기 · [복사])은 그대로 돌아야 한다.
"""
from __future__ import annotations

import io
import re
import zipfile

from .conftest import DEMO_TOKEN


def test_setup_has_its_own_title(logged_in):
    """제품 이름이 화면 제목이면 탭에 `CONTACTVC ASSET · CONTACTVC ASSET` 이 선다."""
    html = logged_in.get("/setup").text
    assert '<h1 class="page-title">발송 프로그램 설치</h1>' in html
    assert "<title>발송 프로그램 설치 · CONTACTVC ASSET</title>" in html


def test_the_token_is_masked_but_the_copy_button_holds_it(logged_in):
    html = logged_in.get("/setup").text
    masked = re.search(r'<code class="token"[^>]*>([^<]*)</code>', html).group(1)
    assert DEMO_TOKEN not in masked
    assert masked.endswith(DEMO_TOKEN[-4:]), "끝 네 자리로 어느 키인지는 알아본다"
    # 값은 [복사] 단추만 든다 — 화면 글자로는 한 번도 서지 않는다.
    assert f'data-token="{DEMO_TOKEN}"' in html
    assert html.count(DEMO_TOKEN) == 1


def test_the_download_still_carries_the_token(logged_in):
    """가린 것은 화면뿐이다 — 설치 파일은 서버가 키를 다시 읽어 넣는다."""
    body = logged_in.get("/download/agent?os_kind=windows").content
    with zipfile.ZipFile(io.BytesIO(body)) as zf:
        config = zf.read("agent/config.yaml").decode("utf-8")
    assert f'token: "{DEMO_TOKEN}"' in config


def test_setup_guide_does_not_show_login_id(logged_in, users):
    html = logged_in.get("/setup").text
    who = re.search(r'<p class="whoami">(.*?)</p>', html, re.S).group(1)
    assert users["u1"].name in who
    assert users["u1"].phone not in who


def test_install_step_is_numbered_once(logged_in):
    """Windows · macOS 는 둘 중 하나라 한 단계(②) 안에 선다 — 번호가 겹치지 않는다."""
    html = logged_in.get("/setup").text
    assert html.count("② 설치하고 켜기") == 1
    assert "<h3>Windows</h3>" in html and "<h3>macOS</h3>" in html


def test_send_pace_warning_points_the_right_way(logged_in):
    """간격은 줄이면, 상한은 늘리면 빨라진다."""
    html = logged_in.get("/setup").text
    assert "발송 간격을 줄이거나 상한을 늘리지 마세요" in html
    assert "간격·상한을 임의로 줄이지" not in html


def test_password_rule_sits_under_the_new_password_field(logged_in):
    html = logged_in.get("/account/password").text
    new_field = html.index('id="new"')
    rule = html.index('id="pw-rule"')
    confirm = html.index('id="conf"')
    assert new_field < rule < confirm, "규칙은 적기 전에 — 새 비밀번호 칸 바로 밑"
    assert 'aria-describedby="pw-rule"' in html


def test_rename_shows_current_name_apart(logged_in, users):
    html = logged_in.get("/account/name").text
    assert f'<p data-testid="name-now">현재 이름: <b>{users["u1"].name}</b></p>' in html
