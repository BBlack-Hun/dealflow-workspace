"""#23 — `Series A 이상 기업` 을 화면 어디서나 `Series A 이상 딜 소싱` 으로.

사용자 요청: "'Series A 이상기업' → 'Series A 이상 딜소싱' 으로 단어 변경."
탭 이름 하나만 바꾸면 그 탭을 가리키는 다른 말(딜 제안 관리의 고르개 안내 ·
못 찾았다는 경고 · 오류 문구 · 되돌리기 화면의 표 이름)이 옛 이름으로 남아,
같은 것을 두 이름으로 부르게 된다. 그래서 **사람 눈에 닿는 글자 전부**를 본다.

바꾸지 않는 것: 표(`series_a_companies`) · 모델 · 주소(`?tab=series-a`).
원본 구글 시트의 탭은 여전히 옛 이름이라, 가져오기를 설명하는 주석의
'시트 Series A 이상 기업' 은 그대로 둔다(코드 주석·문서 문자열은 화면에 안
나온다).
"""
from __future__ import annotations

import ast
import re
from pathlib import Path
from urllib.parse import quote

import pytest

from .conftest import DEMO_PASSWORD

ROOT = Path(__file__).resolve().parents[1]
OLD = "Series A 이상 기업"
NEW = "Series A 이상 딜 소싱"
SERIES_A = "시리즈 A 이상 딜 소싱 참여 심사역"
SHARE = "sourcing_deal_share"


@pytest.fixture()
def world(client, db, users):
    from app.models import SeriesACompany, SourcingContact

    person = SourcingContact(bucket=SERIES_A, position=0, name="가심사",
                             title="심사역", firm="가나벤처스",
                             kakao_room_name="가심사 소싱방")
    company = SeriesACompany(name="샘플바이오", received_at="2026-10-01",
                             series="Series A")
    db.add_all([person, company])
    db.commit()
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    return {"person": person, "company": company}


@pytest.mark.parametrize("path", ["/companies", "/companies?tab=db",
                                  "/companies?tab=series-a"])
def test_the_tab_is_called_by_the_new_name(world, client, path):
    html = client.get(path).text
    tabs = re.search(r'<nav class="sheet-tabs co-tabs">.*?</nav>', html, re.S).group(0)
    assert re.search(NEW + r' <span title="딜 소싱으로 받은 딜">1</span>', tabs), tabs
    # 주소는 그대로다 — 즐겨찾기·다른 화면의 링크가 안 끊긴다.
    assert 'href="/companies?tab=series-a"' in tabs
    assert OLD not in html


def test_the_deal_picker_says_the_new_name(world, client):
    """딜 제안 관리 › 딜 소싱 제안 › Series A 딜 공유의 기업 고르개."""
    html = client.get(f"/deals?mode=sourcing&topic={SHARE}").text
    picker = html[html.index('id="series-a-picker"'):]
    picker = picker[:picker.index('id="sa-filter-note"')]
    assert f"<b>{NEW}</b>(IR 기업 현황 › {NEW} 탭)에서 소개할 기업을" in picker
    assert f'aria-label="{NEW} 기업 검색"' in picker
    assert OLD not in html


def test_an_empty_picker_points_to_the_renamed_tab(client, db, users):
    from app.models import SourcingContact

    db.add(SourcingContact(bucket=SERIES_A, position=0, name="가심사", firm="가나벤처스"))
    db.commit()
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    html = client.get(f"/deals?mode=sourcing&topic={SHARE}").text
    assert (f'{NEW}에 받은 기업이 없습니다 — <a href="/companies?tab=series-a">'
            f"IR 기업 현황 › {NEW}</a> 탭에서 먼저 넣으세요.") in html
    assert OLD not in html


def test_the_sourcing_share_button_says_the_new_name(world, client):
    html = client.get(f"/sourcing?tab={quote(SERIES_A)}").text
    btn = re.search(r'<a [^>]*id="sourcing-share-btn"[^>]*>', html).group(0)
    assert f"거기서 {NEW} 기업을 고르고" in btn, btn
    assert OLD not in html


def test_error_messages_use_the_new_name(world, client):
    r = client.post("/api/deals/preview", json={
        "contact_ids": [world["person"].id], "mode": "sourcing", "topic": SHARE,
        "series_a_ids": []})
    assert r.status_code == 400
    assert r.json()["detail"].startswith(f"{NEW} 기업을 1~"), r.json()
    r = client.post("/api/deals/send", json={
        "contact_ids": [world["person"].id], "mode": "sourcing", "topic": SHARE,
        "series_a_ids": [99999]})
    assert r.status_code == 404
    assert r.json()["detail"] == f"{NEW} 기업 99999 없음", r.json()


def test_the_backup_screen_names_the_table_with_the_new_name():
    """되돌리기 화면은 표 이름을 사람 말로 보여 준다 — 화면의 탭과 같은 이름으로."""
    from app.services import backup

    assert backup.TABLE_LABELS["series_a_companies"] == f"{NEW}(받은 딜)"


def test_the_table_and_address_stay():
    """화면 이름만 바꾼다 — 표 이름이 바뀌면 이주가 필요하고 백업이 갈린다."""
    from app.models import SeriesACompany

    assert SeriesACompany.__tablename__ == "series_a_companies"


# ── 옛 이름이 화면 글자로 다시 들어오지 않는가 ─────────────────────────────────

def _py_strings(path: Path):
    """파이썬 파일의 **문서 문자열이 아닌** 글자 상수(화면·오류로 나가는 것들)."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docs = set()
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if isinstance(body, list) and body and isinstance(body[0], ast.Expr) \
                and isinstance(getattr(body[0], "value", None), ast.Constant):
            docs.add(id(body[0].value))
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) \
                and id(node) not in docs:
            yield node.value


def test_no_screen_text_keeps_the_old_name():
    bad = []
    for path in sorted((ROOT / "app").rglob("*.py")):
        for text in _py_strings(path):
            if OLD in text:
                bad.append(f"{path.relative_to(ROOT)}: {text[:60]}")
    for path in sorted((ROOT / "app" / "static" / "js").glob("*.js")):
        for line in path.read_text(encoding="utf-8").splitlines():
            code = line.split("//", 1)[0]
            if re.search(r'"[^"]*' + OLD + r'[^"]*"', code):
                bad.append(f"{path.relative_to(ROOT)}: {line.strip()[:60]}")
    for path in sorted((ROOT / "app" / "templates").glob("*.html")):
        text = re.sub(r"\{#.*?#\}", "", path.read_text(encoding="utf-8"), flags=re.S)
        if OLD in text:
            bad.append(f"{path.relative_to(ROOT)}")
    assert not bad, "화면 글자에 옛 이름이 남았다: " + " | ".join(bad)
