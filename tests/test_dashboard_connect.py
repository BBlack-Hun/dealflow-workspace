"""대시보드 · 연결 진행 중인 명단 — **누구인지 보이는가**.

이 패널은 오래 숫자만 보여 주었다. `진행 중 44` 는 알겠는데 그 44명이 누구인지
알 수 없었고, 눌러 간 화면에는 다른 수가 떴다. 여기서 지키려는 것은 넷이다.

1. **이름이 나온다.** 앞에서 몇 명은 대시보드에서 바로 읽히고, 이름을 누르면
   그 사람 상세로 간다.
2. **패널이 말한 수 == 눌러 간 화면의 줄 수.** 기대값을 손으로 적지 않고 양쪽을
   세어 대조한다 — 손으로 적으면 모집단이 어긋나도 테스트만 통과한다.
   (예전 사고: 패널은 '내 배정 명단' 을 세고 링크는 `sheet=all` 로 보냈다.
    패널 0명 → 화면 44줄. 반대로 `connect` 필터를 아무도 선언하지 않아
    `?connect=` 가 통째로 버려지던 시절엔 눌러도 306명이 그대로 나왔다.)
3. **아무도 없을 때 안 깨진다.** 진행 중이 0인데 이름 자리만 비어 있으면
   고장으로 읽힌다 — 다음 동작을 적는다.
4. **팀원은 자기 것만 본다.** 대시보드는 자기 화면이다.

실명·회사명을 쓰지 않는다(공개 저장소). 가상 이름만 쓴다.
"""
from __future__ import annotations

import html as html_mod
import re
from pathlib import Path
from urllib.parse import unquote_plus

import pytest

from .conftest import DEMO_PASSWORD

CONTACTS_HTML = Path(__file__).resolve().parents[1] / "app" / "templates" / "contacts.html"


# ── 화면에서 읽어 오는 것들 ────────────────────────────────────────────────
#
# 브라우저가 하는 일을 그대로 흉내 낸다. 서버는 줄을 전부 그려 보내고
# `filters.js` 가 `?키=값` 에 맞는 줄만 남긴다 — 그래서 '화면의 줄 수' 는
# **필터를 적용한 뒤** 남는 줄이다. 여기서 그 계산을 한다.

PANEL = re.compile(r'<section class="panel pipeline-strip">(.*?)</section>', re.S)
TILE = re.compile(
    r'<a class="react[^"]*" href="([^"]+)">\s*<b>(\d+)</b><span>([^<]+)</span>', re.S)
ROW = re.compile(r'<tr class="data-row"[^>]*>')
NAME_LINK = re.compile(r'<a class="req-link" href="([^"]+)"[^>]*>\s*<b>([^<]+)</b>', re.S)

#: 서버가 직접 읽는 값. 필터가 아니라 화면을 고르는 값이라 줄을 거르지 않는다.
SERVED = {"sheet", "ref", "contact", "months", "hidden", "msg"}


def _panel(html: str) -> str:
    found = PANEL.search(html)
    return found.group(1) if found else ""


def _tiles(panel: str) -> list[dict]:
    """패널의 단계 타일 — {라벨: 몇 명, 어디로}.

    주소는 **엔티티를 풀어서** 돌려준다. 템플릿이 내놓는 것은 `&amp;` 이고
    브라우저는 그걸 `&` 로 읽는다 — 안 풀면 `amp;connect` 라는 없는 키가 된다.
    """
    return [{"href": html_mod.unescape(href), "count": int(count), "label": label}
            for href, count, label in TILE.findall(panel)]


def _rows_left(html: str, query: str) -> list[str]:
    """그 주소로 갔을 때 **화면에 남는 줄** — 이름으로 돌려준다.

    수만 맞추면 "44명 중 44명" 이 서로 다른 44명이어도 통과한다. 이 패널이
    답하려는 것은 '누구인가' 라 이름까지 대조해야 한다.

    거르는 규칙은 `filters.js` 와 같다 — 컬럼 간 AND, 한 컬럼 안에서는 OR,
    다중 값 셀은 `|` 로 나눈다. 선언되지 않은 키는 브라우저가 버리므로
    여기서도 버린다(그래서 링크가 조용히 안 걸리면 수가 어긋나 걸린다).
    """
    wanted: dict[str, list[str]] = {}
    for pair in query.split("&"):
        if not pair or "=" not in pair:
            continue
        key, raw = pair.split("=", 1)
        if key in SERVED:
            continue
        wanted.setdefault(key, []).extend(
            v for v in (unquote_plus(x) for x in raw.split(",")) if v)

    left = []
    for row in ROW.findall(html):
        values = dict(re.findall(r'data-f-([a-z]+)="([^"]*)"', row))
        if all(any(v in [x.strip() for x in values.get(key, "").split("|")]
                   for v in vals) for key, vals in wanted.items()):
            left.append(re.search(r'data-name="([^"]*)"', row).group(1))
    return left


def _declared_filter_keys() -> set[str]:
    """투자사 관리 현황이 머리글에 선언한 필터 키."""
    keys = set()
    for spec in re.findall(r'data-filters="([^"]*)"', CONTACTS_HTML.read_text("utf-8")):
        for one in spec.split("|"):
            if ":" in one and not one.startswith("{{"):
                keys.add(one.split(":", 1)[0].strip())
    return keys


@pytest.fixture()
def waiting(db, users):
    """연결이 아직 안 끝난 명단.

    **풀 명단에 둔다.** 연결 작업은 명단을 배정받기 전에 하는 일이라 실제
    데이터도 그렇다(로컬 실데이터에서 배정 명단 125명은 전부 연결 완료였고,
    연결 중인 132명은 전부 풀에 있었다). 배정 명단만 세던 동안 이 패널은
    사람이 있는데도 화면에 아예 뜨지 않았다.
    """
    from app.models import SheetOwner, VcContact

    # 배정 명단도 하나 둔다. 투자사 관리 현황은 아무 것도 안 고르면 **배정
    # 명단 탭**을 먼저 여는데, 연결 중인 사람은 거기 없다 — 링크에서
    # `sheet=all` 이 빠지면 패널은 7명이라 하고 화면은 0줄이 된다.
    db.add_all([
        SheetOwner(label="내 명단", user_id=users["u1"].id),
        SheetOwner(label="연결 명단", user_id=None, assignee_name="연결담당"),
    ])
    db.add_all([
        VcContact(user_id=users["u1"].id, name=f"가나{i}", firm="가나벤처스",
                  source_sheet="연결 명단", connect_stage="in_progress",
                  assignee_name="연결담당")
        for i in range(7)
    ] + [
        VcContact(user_id=users["u1"].id, name=f"다라{i}", firm="다라인베스트",
                  source_sheet="연결 명단", connect_stage="not_started")
        for i in range(3)
    ] + [
        VcContact(user_id=users["u1"].id, name="마바", firm="마바파트너스",
                  source_sheet="연결 명단", connect_stage="declined"),
        # 연결이 끝난 사람은 이 패널이 세지 않는다 — 딜소개 대상이다.
        VcContact(user_id=users["u1"].id, name="사아", firm="사아캐피탈",
                  source_sheet="내 명단", connect_stage="connected",
                  kakao_room_name="사아 방"),
    ])
    db.commit()
    return db


@pytest.fixture()
def logged(client, users):
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    return client


# ── 1. 이름이 나온다 ───────────────────────────────────────────────────────

def test_패널이_누구인지_이름으로_보여_준다(logged, waiting):
    """세는 것만 보여주고 갈 곳이 없으면, 그 44명이 누구인지 알 수 없다."""
    panel = _panel(logged.get("/").text)
    assert panel, "연결 진행 중인 명단 패널이 없다"

    names = NAME_LINK.findall(panel)
    assert names, "이름이 한 명도 없다 — 숫자만 있으면 누구인지 알 수 없다"
    # 진행 중인 사람만 이름으로 세운다(지금 전화·초대가 걸린 사람).
    assert {n for _, n in names} <= {f"가나{i}" for i in range(7)}
    assert "사아" not in panel, "연결이 끝난 사람이 섞였다"


def test_이름을_누르면_그_사람_상세가_열린다(logged, waiting, db):
    """이름은 장식이 아니라 갈 곳이다 — `?contact=` 가 그 줄을 연다."""
    from app.models import VcContact

    raw_href, name = NAME_LINK.findall(_panel(logged.get("/").text))[0]
    href = html_mod.unescape(raw_href)
    contact = db.query(VcContact).filter_by(name=name).one()
    assert f"contact={contact.id}" in href

    page = logged.get(href)
    assert page.status_code == 200
    # 화면이 그 사람을 열도록 서버가 값을 넘겼는가.
    assert f"window.DEALFLOW_OPEN_CONTACT = {contact.id};" in page.text


def test_명단을_통째로_쏟지_않고_나머지는_눌러서_본다(logged, waiting):
    """대시보드는 한눈에 보는 화면이다 — '오늘 보낼 후속'과 같은 다섯 명."""
    from app.services.dashboard import PIPELINE_NAMES

    panel = _panel(logged.get("/").text)
    names = NAME_LINK.findall(panel)
    assert len(names) == PIPELINE_NAMES < 7
    assert f"나머지 {7 - PIPELINE_NAMES}명 보기" in panel


# ── 2. 패널이 말한 수 == 눌러 간 화면의 줄 수 ──────────────────────────────

def test_패널이_말한_수와_눌러_간_화면의_줄_수가_같다(logged, waiting):
    """**양쪽을 세어 대조한다.** 기대값을 손으로 적으면 모집단이 어긋나도 통과한다."""
    panel = _panel(logged.get("/").text)
    tiles = _tiles(panel)
    assert len(tiles) == 3, "진행 중 · 미착수 · 참여 안 함 세 칸이어야 한다"

    panel_names = {n for _, n in NAME_LINK.findall(panel)}
    for tile in tiles:
        query = tile["href"].partition("?")[2]
        page = logged.get(tile["href"])
        assert page.status_code == 200, f'{tile["label"]} 링크가 열리지 않는다'
        left = _rows_left(page.text, query)
        assert len(left) == tile["count"], (
            f'[{tile["label"]}] 패널은 {tile["count"]}명이라 했는데 '
            f"{tile['href']} 에는 {len(left)}줄이 남는다")
        assert tile["count"], f'{tile["label"]} 이 0명이면 대조가 의미 없다'
        if tile["label"] == "진행 중":
            # 수만 같고 다른 사람이면 소용이 없다 — 패널에 세운 이름이
            # 그 화면에 실제로 있어야 한다.
            assert panel_names <= set(left), (
                f"패널에 세운 이름이 화면에 없다: {sorted(panel_names - set(left))}")


def test_나머지_보기도_같은_목록으로_간다(logged, waiting):
    """'나머지 39명 보기' 가 진행 중 타일과 다른 곳으로 가면 안 된다."""
    panel = _panel(logged.get("/").text)
    in_progress = next(t for t in _tiles(panel) if t["label"] == "진행 중")
    more = re.search(r'<a class="linkbtn" href="([^"]+)">나머지', panel)
    assert more and html_mod.unescape(more.group(1)) == in_progress["href"]


def test_링크의_필터_키는_그_표가_선언한_키여야_한다(logged, waiting):
    """`filters.js` 는 **선언 안 된 키를 버린다.**

    버려도 화면은 멀쩡히 열려서 아무도 눈치채지 못한다 — 예전에 `connect` 가
    어디에도 선언되지 않아 눌러도 306명이 그대로 나왔다.
    """
    declared = _declared_filter_keys()
    for tile in _tiles(_panel(logged.get("/").text)):
        query = tile["href"].partition("?")[2]
        for pair in query.split("&"):
            key = pair.split("=")[0]
            assert key in declared | SERVED, (
                f"투자사 관리 현황이 모르는 키({key})로 링크가 걸려 있다 — "
                f"눌러도 아무것도 안 걸러진다. 아는 키: {sorted(declared)}")


def test_라벨은_임포트가_정한_말을_그대로_쓴다(logged, waiting):
    """타일 글자와 필터 값이 갈리면 눌렀을 때 0줄이 된다."""
    from app.services.sheet_import import CONNECT_LABELS

    for tile in _tiles(_panel(logged.get("/").text)):
        assert tile["label"] in CONNECT_LABELS.values()
        assert f"connect={tile['label'].replace(' ', '%20')}" in unquote_plus(
            tile["href"]).replace(" ", "%20")


# ── 3. 아무도 없을 때 ──────────────────────────────────────────────────────

def test_연결할_사람이_없으면_패널을_아예_띄우지_않는다(logged, db, users):
    """전원 연결 완료면 이 패널이 할 말이 없다 — 0 세 칸을 띄우지 않는다."""
    from app.models import VcContact

    db.add(VcContact(user_id=users["u1"].id, name="사아", firm="사아캐피탈",
                     kakao_room_name="사아 방", connect_stage="connected"))
    db.commit()

    body = logged.get("/").text
    assert body.count("연결 진행 중인 명단") == 0
    assert _tiles(_panel(body)) == []


def test_담당자가_아예_없어도_대시보드가_열린다(logged):
    page = logged.get("/")
    assert page.status_code == 200
    assert _panel(page.text) == ""


def test_진행_중이_없으면_다음_동작을_적는다(logged, db, users):
    """이름 자리만 비어 있으면 고장으로 읽힌다 — 미착수에서 고르라고 말한다."""
    from app.models import VcContact

    db.add_all([VcContact(user_id=users["u1"].id, name=f"다라{i}",
                          firm="다라인베스트", connect_stage="not_started")
                for i in range(3)])
    db.commit()

    panel = _panel(logged.get("/").text)
    assert panel and not NAME_LINK.findall(panel)
    assert "미착수 3명" in panel
    # 수와 링크는 그대로 맞아야 한다.
    tile = next(t for t in _tiles(panel) if t["label"] == "미착수")
    assert tile["count"] == 3


def test_참여_안_함만_남아도_깨지지_않는다(logged, db, users):
    from app.models import VcContact

    db.add(VcContact(user_id=users["u1"].id, name="마바", firm="마바파트너스",
                     connect_stage="declined"))
    db.commit()

    panel = _panel(logged.get("/").text)
    assert panel, "참여 안 함만 남았다고 패널이 사라지면 안 된다"
    assert "미착수 0명" not in panel


# ── 4. 자기 것만 본다 ──────────────────────────────────────────────────────

def test_팀원은_자기_담당만_센다(logged, db, users):
    """대시보드는 자기 화면이다. 남의 담당이 섞이면 내 일이 아닌 것을 챙긴다."""
    from app.models import VcContact
    from app.services.dashboard import user_dashboard

    db.add_all([
        VcContact(user_id=users["u1"].id, name="가나0", firm="가나벤처스",
                  connect_stage="in_progress"),
        VcContact(user_id=users["u2"].id, name="남의사람", firm="사아캐피탈",
                  connect_stage="in_progress"),
    ])
    db.commit()

    panel = _panel(logged.get("/").text)
    assert "가나0" in panel
    assert "남의사람" not in panel
    assert user_dashboard(db, users["u1"])["pipeline"]["in_progress"] == 1
    assert user_dashboard(db, users["u2"])["pipeline"]["in_progress"] == 1


def test_관리자도_자기_담당만_센다(client, db, users):
    """관리자는 투자사 관리 현황에서 팀 전체를 보지만, 대시보드는 자기 것이다."""
    from app.models import VcContact
    from app.services.dashboard import user_dashboard

    users["u2"].role = "admin"
    db.add(VcContact(user_id=users["u1"].id, name="가나0", firm="가나벤처스",
                     connect_stage="in_progress"))
    db.commit()

    client.post("/login", data={"phone": "01000000002", "password": DEMO_PASSWORD})
    assert user_dashboard(db, users["u2"])["pipeline"]["total"] == 0
    assert _panel(client.get("/").text) == ""


# ── 5. 모집단 (이 패널이 세는 사람) ────────────────────────────────────────

def test_배정_전_풀_명단도_센다(logged, db, users):
    """연결 작업은 **배정받기 전** 풀에서 한다.

    배정된 명단만 세면 이 패널은 사실상 늘 비어 있다 — 로컬 실데이터에서도
    배정 명단 125명은 전부 '연결 완료' 였고, 연결 중인 132명은 풀에 있었다.
    """
    from app.models import SheetOwner, VcContact
    from app.services.dashboard import user_dashboard

    db.add_all([
        SheetOwner(label="내 명단", user_id=users["u1"].id),
        SheetOwner(label="풀 명단", user_id=None),
        VcContact(user_id=users["u1"].id, name="가나0", firm="가나벤처스",
                  source_sheet="풀 명단", connect_stage="in_progress"),
    ])
    db.commit()

    data = user_dashboard(db, users["u1"])
    assert data["pipeline"]["in_progress"] == 1
    # 배정 명단만 세는 '내 담당 투자사' 는 그대로 0이다 — 두 수는 원래 다르다.
    assert {k["key"]: k["value"] for k in data["kpis"]}["contacts"] == 0
    assert "가나0" in _panel(logged.get("/").text)


def test_투자사로_세지_않는_명단은_빠진다(logged, db, users):
    """감춘 명단(스타트업 리마인드 등)은 투자사가 아니다 — 목록 화면도 뺀다."""
    from app.models import SheetOwner, VcContact
    from app.services.dashboard import user_dashboard

    db.add_all([
        SheetOwner(label="감춘 명단", user_id=None, is_hidden=1),
        VcContact(user_id=users["u1"].id, name="가나0", firm="가나벤처스",
                  source_sheet="감춘 명단", connect_stage="in_progress"),
    ])
    db.commit()

    assert user_dashboard(db, users["u1"])["pipeline"]["total"] == 0
    assert _panel(logged.get("/").text) == ""
