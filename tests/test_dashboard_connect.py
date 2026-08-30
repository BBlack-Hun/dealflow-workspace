"""대시보드 · 연결 진행 중인 명단 — **어느 명단을 세고, 누구인지 보이는가**.

모집단은 **딜 제안 관리와 같은 명단**이다(`sheet_owner.deal_list_contacts`).
한때 이 패널이 안 뜬다고 모집단을 '내가 들고 있는 줄 전체' 로 넓혀 두었는데,
그러면 딜 소개 명단에 올린 적도 없는 풀 사람의 연결 상태가 내 할 일로 뜬다 —
**숫자를 만들려고 모집단을 넓히지 않는다.** 여기서 지키려는 것은 다섯이다.

1. **기준이 딜소개 명단이다.** 그 명단 밖 사람은 연결 중이어도 안 센다.
2. **이름이 나온다.** 앞에서 몇 명은 대시보드에서 바로 읽히고, 이름을 누르면
   그 사람 상세로 간다.
3. **패널이 말한 수 == 눌러 간 화면의 줄 수.** 기대값을 손으로 적지 않고 양쪽을
   세어 대조한다 — 손으로 적으면 모집단이 어긋나도 테스트만 통과한다.
   (예전 사고: 패널은 '내 배정 명단' 을 세고 링크는 `sheet=all` 로 보냈다.
    패널 0명 → 화면 44줄. 반대로 `connect` 필터를 아무도 선언하지 않아
    `?connect=` 가 통째로 버려지던 시절엔 눌러도 306명이 그대로 나왔다.
    `room=` 필터가 같은 상태로 오래 살아 있었다.)
4. **전원 연결 완료여도 패널이 사라지지 않는다.** 실데이터의 딜소개 명단
   125명은 전부 연결 완료다 — 그때 패널을 감추면 사용자가 보려던 화면이
   바로 그 순간 사라진다. 0 이면 0 이라고 말하고, 아직 방이 없어 **못 받는
   사람**을 갈래별로 이어서 보여 준다.
5. **팀원은 자기 것만 본다.** 대시보드는 자기 화면이다.

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

#: 값이 비어 있는 줄을 세우는 말. `filters.js` 의 `EMPTY` 와 같은 글자여야 한다 —
#: 대시보드의 `연결 담당: 미지정` 이 이 값으로 걸린다.
EMPTY = "(비어 있음)"


def _cell_values(raw: str) -> list[str]:
    """한 칸의 값들. **비어 있으면 `(비어 있음)` 한 개다**(`filters.js` 규칙).

    이걸 빼놓으면 `assignee=(비어 있음)` 같은 링크가 여기서만 0줄로 보인다 —
    브라우저에서는 멀쩡히 걸리는데 검사만 거짓말한다.
    """
    parts = [x.strip() for x in (raw or "").split("|") if x.strip()]
    return parts or [EMPTY]


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
        if all(any(v in _cell_values(values.get(key, "")) for v in vals)
               for key, vals in wanted.items()):
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


DEAL_SHEET = "내 딜소개 명단"
POOL_SHEET = "확보해 둔 풀"


@pytest.fixture()
def waiting(db, users):
    """딜소개 명단 안에서 연결이 아직 안 끝난 사람들.

    **딜소개 명단에 둔다.** 이 패널이 세는 것은 "딜 소개를 보내기로 한 명단의
    연결 현황" 이다 — 풀에 있는 사람의 연결은 아직 내 회차의 일이 아니다.
    풀 명단도 함께 두어, 그쪽 사람이 섞이지 않는지 같이 본다.
    """
    from app.models import SheetOwner, VcContact

    db.add_all([
        SheetOwner(label=DEAL_SHEET, user_id=users["u1"].id),
        SheetOwner(label=POOL_SHEET, user_id=None, assignee_name="연결담당"),
    ])
    db.add_all([
        VcContact(user_id=users["u1"].id, name=f"가나{i}", firm="가나벤처스",
                  source_sheet=DEAL_SHEET, connect_stage="in_progress",
                  assignee_name="연결담당")
        for i in range(7)
    ] + [
        VcContact(user_id=users["u1"].id, name=f"다라{i}", firm="다라인베스트",
                  source_sheet=DEAL_SHEET, connect_stage="not_started")
        for i in range(3)
    ] + [
        VcContact(user_id=users["u1"].id, name="마바", firm="마바파트너스",
                  source_sheet=DEAL_SHEET, connect_stage="declined"),
        # 연결이 끝나고 방까지 있는 사람 — 이 패널의 '연결 남음' 에는 안 든다.
        VcContact(user_id=users["u1"].id, name="사아", firm="사아캐피탈",
                  source_sheet=DEAL_SHEET, connect_stage="connected",
                  channel_kakao=1, room_verified="verified",
                  kakao_room_name="사아 방"),
        # **딜소개 명단 밖**에서 연결 중인 사람. 이 패널이 세면 안 된다.
        VcContact(user_id=users["u1"].id, name="풀사람", firm="자차인베스트",
                  source_sheet=POOL_SHEET, connect_stage="in_progress",
                  assignee_name="연결담당"),
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
    from app.services.sheet_import import CONNECT_OPEN

    panel = _panel(logged.get("/").text)
    tiles = _tiles(panel)
    # 칸 수를 손으로 적지 않는다 — **아직 손이 필요한 단계**만 칸이 된다.
    # 끝난 단계(참여 안 함 · 방 나감)는 아래 별도 검사가 본다.
    assert len(tiles) == len(CONNECT_OPEN), [t["label"] for t in tiles]

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


# ── 3. 전원 연결이 끝났을 때 (= 실데이터의 지금 상태) ──────────────────────
#
# 딜소개 명단 125명이 전부 연결 완료다. 예전 화면은 그때 패널을 통째로
# 감췄는데, **사용자가 보려던 것이 바로 그 상태**였다("누가 아직 못 받는지").

ROOM_TILE = re.compile(
    r'<a class="name-lead [^"]*" href="([^"]+)">([^<]+?) (\d+)명</a>')


@pytest.fixture()
def all_connected(db, users):
    """전원 연결 완료 · 방 상태만 갈리는 딜소개 명단.

    실데이터와 같은 모양이다(확인됨 116 · 채널 없음 6 · 메일 2 · 실패 1).
    """
    from app.models import SheetOwner, VcContact

    db.add(SheetOwner(label=DEAL_SHEET, user_id=users["u1"].id))

    def one(name, **kw):
        return VcContact(user_id=users["u1"].id, name=name, firm="가나벤처스",
                         source_sheet=DEAL_SHEET, connect_stage="connected", **kw)

    db.add_all(
        [one(f"준비{i}", channel_kakao=1, room_verified="verified",
             kakao_room_name=f"준비{i} 방") for i in range(4)]
        + [one(f"방없음{i}", channel_kakao=1) for i in range(3)]
        + [one("메일만", channel_email=1)]
    )
    db.commit()
    return db


def test_전원_연결이_끝나도_패널이_사라지지_않는다(logged, all_connected):
    """0 이면 0 이라고 말한다 — 침묵하면 고장으로 읽힌다."""
    body = logged.get("/").text
    panel = _panel(body)
    assert panel, "전원 연결 완료라고 패널이 통째로 사라졌다"
    assert "전원 연결이 끝났습니다" in panel
    # 세 칸은 그대로 0 이다. **숫자를 만들려고 모집단을 넓히지 않는다.**
    assert all(t["count"] == 0 for t in _tiles(panel)), _tiles(panel)


def test_아직_못_받는_사람을_갈래별로_이름까지_보여_준다(logged, all_connected):
    """딜 소개는 카톡방으로 나간다 — 연결이 끝났다고 보낼 수 있는 것이 아니다."""
    panel = _panel(logged.get("/").text)
    tiles = {label: (html_mod.unescape(href), int(n))
             for href, label, n in ROOM_TILE.findall(panel)}
    assert tiles, "방이 없어 못 받는 사람을 화면이 말하지 않는다"

    from app.services.dashboard import ROOM_LABELS

    assert tiles[ROOM_LABELS["missing"][0]][1] == 3
    assert tiles[ROOM_LABELS["email"][0]][1] == 1
    # 준비된 사람은 여기 뜨면 안 된다 — 손댈 것이 없는 사람이다.
    assert "준비0" not in panel
    assert "방없음0" in panel, "누구인지 이름으로 보여야 한다"


def test_방_상태_타일도_말한_수와_눌러_간_화면의_줄_수가_같다(logged, all_connected):
    """`room=` 은 오래 **어디에도 선언되지 않은 키**였다 — 눌러도 274명이
    그대로 떴다. 여기서 양쪽을 세어 대조한다."""
    panel = _panel(logged.get("/").text)
    for raw_href, label, count in ROOM_TILE.findall(panel):
        href = html_mod.unescape(raw_href)
        page = logged.get(href)
        assert page.status_code == 200, f"{label} 링크가 열리지 않는다"
        left = _rows_left(page.text, href.partition("?")[2])
        assert len(left) == int(count), (
            f"[{label}] 패널은 {count}명이라 했는데 {href} 에는 {len(left)}줄이 남는다")


def test_모두_준비되면_손댈_것이_없다고_말한다(logged, db, users):
    """방까지 다 있으면 갈래 줄도 없다 — 빈 자리 대신 그렇다고 적는다."""
    from app.models import SheetOwner, VcContact

    db.add(SheetOwner(label=DEAL_SHEET, user_id=users["u1"].id))
    db.add_all([
        VcContact(user_id=users["u1"].id, name=f"준비{i}", firm="가나벤처스",
                  source_sheet=DEAL_SHEET, connect_stage="connected",
                  channel_kakao=1, room_verified="verified",
                  kakao_room_name=f"준비{i} 방")
        for i in range(3)
    ])
    db.commit()

    panel = _panel(logged.get("/").text)
    assert "전원 연결이 끝났습니다" in panel and "모두 보낼 수 있습니다" in panel
    assert not ROOM_TILE.findall(panel)


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

def test_딜소개_명단_밖은_연결_중이어도_세지_않는다(logged, db, users, waiting):
    """★ 이번에 바로잡은 자리.

    한때 이 패널이 안 뜬다고 모집단을 '내가 들고 있는 줄 전체' 로 넓혀 두었다.
    그러면 **딜 소개 명단에 올린 적도 없는 풀 사람**의 연결 상태가 내 할 일로
    뜬다 — 숫자를 만들려고 모집단을 넓히지 않는다.
    """
    from app.services.dashboard import user_dashboard
    from app.services import sheet_owner

    data = user_dashboard(db, users["u1"])
    # 딜소개 명단 안에서 연결 중인 사람은 7명. 풀의 `풀사람` 은 여기 없다.
    assert data["pipeline"]["in_progress"] == 7
    assert data["pipeline"]["listed"] == len(
        sheet_owner.deal_list_contacts(db, users["u1"]))
    assert "풀사람" not in _panel(logged.get("/").text), (
        "딜소개 명단 밖 사람이 패널에 떠 있다")


def test_패널이_세는_모집단은_발송_대상과_같은_명단이다(db, users, waiting):
    """두 화면이 각자 모집단을 고르면 또 갈린다 — 판정은 `sheet_owner` 한 곳이다."""
    from app.services import sheet_owner
    from app.services.dashboard import user_dashboard

    listed = sheet_owner.deal_list_contacts(db, users["u1"])
    counts = sheet_owner.recipient_counts(db, users["u1"])
    pipeline = user_dashboard(db, users["u1"])["pipeline"]

    assert pipeline["listed"] == len(listed) == counts["managed"]
    # 연결이 남은 사람 + 보낼 수 있는 사람 + 방이 없어 못 보내는 사람 = 명단 전체
    assert pipeline["total"] + pipeline["ready"] + pipeline["stuck"] == len(listed)
    assert pipeline["ready"] + pipeline["stuck"] == counts["sendable"]


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


# ── 6. 패널이 낸 **모든** 링크를 훑어 따라간다 ─────────────────────────────
#
# 위 검사들은 볼 링크를 손으로 적어 둔다(타일 · 방 상태 줄). 링크가 하나
# 늘어나면 그 링크만 아무 검사도 없이 지나간다 — 눌러도 아무것도 안 걸러지는
# 부류라, 빠졌다는 사실 자체를 아무도 눈치채지 못한다. 이 저장소가 두 번 당한
# 자리다(`connect=` · `room=` 이 어디에도 선언되지 않은 채 오래 살아 있었다).
#
# 그래서 **패널이 실제로 내놓은 `<a href="/contacts?…">` 를 전부 긁어** 하나씩
# 따라가고, 링크 글자가 말한 수와 간 화면의 줄 수를 대조한다.

PANEL_LINK = re.compile(r'<a\b[^>]*href="(/contacts\?[^"]+)"[^>]*>(.*?)</a>', re.S)


def _panel_links(panel: str) -> list[tuple[str, str]]:
    """(주소, 링크에 적힌 글자) — 주소는 엔티티를 풀어서."""
    out = []
    for href, inner in PANEL_LINK.findall(panel):
        text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", inner)).strip()
        out.append((html_mod.unescape(href), text))
    return out


def test_패널이_낸_모든_링크가_실제로_거른다(logged, waiting):
    """**손으로 나열하지 않는다.** 패널이 낸 링크를 훑어 각각 따라가 대조한다.

    링크가 하나 늘어도 저절로 걸린다. 지키는 것은 셋이다.

      ① 필터 키를 투자사 관리 현황이 **선언**했는가 — `filters.js` 는 선언
         안 된 키를 통째로 버린다. 버려도 화면은 멀쩡히 열려서 아무도 모른다.
      ② 그 주소가 실제로 **열리는가**.
      ③ 링크 글자가 수를 말하면 **간 화면의 줄 수와 같은가**.
    """
    panel = _panel(logged.get("/").text)
    links = _panel_links(panel)
    # 링크가 통째로 사라지면 이 검사가 조용히 0건이 된다 — 그쪽이 더 나쁘다.
    assert len(links) >= 8, f"패널의 링크가 너무 적다: {links}"

    declared = _declared_filter_keys()
    counted = 0
    for href, text in links:
        query = href.partition("?")[2]
        keys = {pair.split("=")[0] for pair in query.split("&") if pair}
        unknown = keys - declared - SERVED
        assert not unknown, (
            f"[{text}] 이 모르는 키({sorted(unknown)})로 걸려 있다 — 눌러도 "
            f"아무것도 안 걸러진다. 아는 키: {sorted(declared)}")

        page = logged.get(href)
        assert page.status_code == 200, f"[{text}] 링크가 열리지 않는다"

        # 사람 상세를 여는 링크는 목록을 거르는 링크가 아니다.
        if "contact=" in query:
            assert "window.DEALFLOW_OPEN_CONTACT = " in page.text
            continue
        # `나머지 2명 보기` 가 말하는 수는 **안 보여 준 수**지 간 화면의 줄
        # 수가 아니다(7명 중 5명을 세우고 남은 2명).
        if "나머지" in text:
            continue
        # 거르는 키가 하나도 없는 링크(`?sheet=…` 만)는 좁히겠다고 말한 적이
        # 없다 — 명단으로 건너가는 길이다. 게다가 명단 이름에 수가 들어 있는
        # 일이 흔해서(`전체 딜소개현황(125명)`) 그 수를 줄 수로 읽으면 안 된다.
        if not (keys - SERVED):
            continue
        said = re.search(r"(\d+)", text)
        if not said:
            continue
        left = _rows_left(page.text, query)
        assert len(left) == int(said.group(1)), (
            f"[{text}] 는 {said.group(1)}명이라 했는데 {href} 에는 "
            f"{len(left)}줄이 남는다")
        counted += 1
    assert counted >= 6, f"수를 대조한 링크가 너무 적다({counted}) — {links}"


def test_숫자를_말하는_링크는_저마다_다른_곳으로_간다(logged, waiting):
    """같은 곳으로 두 번 가는 링크는 군더더기다.

    요약 줄의 숫자에 링크를 걸 때 판단한 규칙이다 — 아래 갈래 줄이 이미
    가는 곳에 합계까지 걸면, 같은 사람에게 가는 길이 하나 더 생길 뿐이다.
    """
    links = _panel_links(_panel(logged.get("/").text))
    targets = [href for href, text in links
               if "contact=" not in href and re.search(r"\d", text)
               and "나머지" not in text]
    assert len(targets) == len(set(targets)), (
        f"같은 주소로 두 번 갑니다: {sorted(targets)}")


# ── 7. 끝난 상태는 대시보드에서 빠지고, 투자사 관리 현황에는 남는다 ────────


@pytest.fixture()
def finished(db, users):
    """딜소개 명단 안에 **끝난 줄**이 섞여 있는 상태.

    카톡방을 나가신 분이 실제로 있다 — 방 이름을 지우면 코드가 말없이
    `진행 중` 으로 되돌려서 대시보드에 `지금 연결 중` 으로 계속 떴다.
    """
    from app.models import SheetOwner, VcContact

    db.add(SheetOwner(label=DEAL_SHEET, user_id=users["u1"].id))
    db.add_all([
        VcContact(user_id=users["u1"].id, name="가나0", firm="가나벤처스",
                  source_sheet=DEAL_SHEET, connect_stage="in_progress"),
        VcContact(user_id=users["u1"].id, name="나감이", firm="다라인베스트",
                  source_sheet=DEAL_SHEET, connect_stage="left_room"),
        VcContact(user_id=users["u1"].id, name="안함이", firm="마바파트너스",
                  source_sheet=DEAL_SHEET, connect_stage="declined"),
    ])
    db.commit()
    return db


def test_끝난_상태는_대시보드_칸에서_빠진다(logged, finished):
    """대시보드는 **할 일이 남은 것**을 띄우는 자리다."""
    from app.services.sheet_import import CONNECT_DONE, CONNECT_LABELS

    tiles = {t["label"] for t in _tiles(_panel(logged.get("/").text))}
    for key in CONNECT_DONE:
        assert CONNECT_LABELS[key] not in tiles, (
            f"{CONNECT_LABELS[key]} 이 아직 할 일 칸에 서 있다: {tiles}")


def test_뺐다고_수까지_지우지_않는다(logged, finished):
    """몇 명인지조차 안 보이면 **없어진 줄 알고** 다시 세러 들어간다."""
    from app.services.sheet_import import CONNECT_LABELS, STAGE_LEFT_ROOM

    panel = _panel(logged.get("/").text)
    assert f"{CONNECT_LABELS[STAGE_LEFT_ROOM]} 1명" in panel, panel
    assert "더 진행하지 않기로 한 명단" in panel


def test_끝난_줄은_투자사_관리_현황에는_그대로_남는다(logged, finished):
    """대시보드에서 뺀 것이지 명단에서 지운 것이 아니다."""
    from app.services.sheet_import import CONNECT_LABELS, STAGE_LEFT_ROOM

    body = logged.get("/contacts?sheet=all").text
    assert "나감이" in body and "안함이" in body
    # 눌러서 그 명단만 볼 수도 있어야 한다 — 행이 그 값을 싣고 있는가.
    assert f'data-f-connect="{CONNECT_LABELS[STAGE_LEFT_ROOM]}"' in body


def test_방을_나가신_분은_지금_연결_중에_안_뜬다(logged, finished):
    """이 건의 뿌리 — 나가신 분이 `지금 연결 중` 으로 잡히면 안 된다."""
    panel = _panel(logged.get("/").text)
    names = {n for _, n in NAME_LINK.findall(panel)}
    assert "나감이" not in names, "방을 나가신 분이 아직 연결 중으로 뜬다"
    assert "가나0" in names


def test_연결_남음은_끝난_줄을_안_센다(logged, finished, db, users):
    """`연결 남음` 에 참여 안 함·방 나감이 섞이면 할 일이 아닌 것을 할 일로 센다."""
    from app.services.dashboard import user_dashboard

    pipeline = user_dashboard(db, users["u1"])["pipeline"]
    assert pipeline["open"] == 1          # 진행 중 1명뿐
    assert pipeline["total"] == 3         # 못 보내는 사람은 셋 (셈은 그대로)
