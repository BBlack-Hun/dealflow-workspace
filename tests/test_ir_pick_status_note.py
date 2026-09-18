"""딜 진행 관리의 담당자 고르기 — **왜 이 사람이 목록에 있는지 적는가.**

「요청 받았다고 적기」·「미팅 잡기」의 고르기는 `sheet_owner.my_contacts` 다 —
**맡은 사람 전부**. 발송 대상(`recipients`)은 여기서 문을 둘 더 지나므로,
아래 세 갈래는 딜 제안 관리에서는 사라지는데 이 고르기에는 그대로 남는다.

    `검토중단`                      `is_paused`
    `참여 안 함` · `방 나감` 등     `is_connected`
    딜소개 명단에서 내린 사람        `on_deal_list`

쓰는 사람에게는 이것이 **"지운 사람이 아직 나온다"** 로 보였다. 그렇다고
빼면 안 된다 — 이 화면은 *보내는* 곳이 아니라 **이미 일어난 일을 적는** 곳이라,
방을 나간 분이 메일로 요청한 일을 적을 길이 사라진다. 그래서 빼는 대신
**상태를 함께 적는다.**

**이 파일이 지키는 것.**

- `활발` + `연결 완료` + `명단 안` 에는 **아무것도 안 붙는다.** 대부분이
  그래서, 다 붙으면 꼬리표가 눈에 안 들어오는 소음이 된다.
- 한글 이름을 **화면이 지어내지 않는다** — `sheet_owner.STATUS_LABELS` ·
  `sheet_import.CONNECT_LABELS` 에서 온다. 지어내면 화면마다 다른 말이 선다.
- 꼬리표가 붙은 사람은 **그 말로도 찾아진다**(`data-search`). `방 나감` 을
  쳐서 그 사람들만 볼 수 있어야 꼬리표가 쓸모가 있다.
- 꼬리표 유무가 **발송 판정과 어긋나지 않는다** — 목록에 있는데 딜 제안
  관리에서 빠지는 사람은 **반드시** 꼬리표가 있다.
- 한 벌짜리 매크로라 **두 폼이 같이 붙는다.**

화면이 실제로 어떻게 좁혀지는지는 `tests/js/ir_contact_search_test.js` 가 본다.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from .conftest import DEMO_PASSWORD

ROOT = Path(__file__).resolve().parents[1]
IR_HTML = ROOT / "app" / "templates" / "ir.html"


@pytest.fixture()
def stage(client, db, users):
    """다섯 갈래를 한 화면에 세운다 — 이름·투자사는 전부 지어낸 것이다."""
    from app.models import SheetOwner, VcContact

    db.add_all([
        SheetOwner(label="내 명단", user_id=users["u1"].id),
        # 딜소개 명단에서 **내린** 명단. 사람의 상태가 아니라 명단의 상태다.
        SheetOwner(label="내린 명단", user_id=users["u1"].id, is_deal_list=False),
    ])

    def who(name, sheet="내 명단", status="active", stage="connected"):
        return VcContact(user_id=users["u1"].id, name=name, title="심사역",
                         firm=f"{name}벤처스", source_sheet=sheet,
                         channel_kakao=1, status=status, connect_stage=stage)

    people = {
        # 아무것도 안 붙는 사람 — 대부분이 이쪽이다.
        "plain": who("가담당"),
        "left": who("나담당", stage="left_room"),
        "declined": who("다담당", stage="declined"),
        "paused": who("라담당", status="paused"),
        "off_list": who("마담당", sheet="내린 명단"),
        # 두 갈래에 걸린 사람.
        "both": who("바담당", status="paused", stage="left_room"),
        # 아직 연결 중인 사람도 발송 대상이 아니다 — 여기도 적힌다.
        "working": who("사담당", stage="in_progress"),
    }
    db.add_all(list(people.values()))
    db.commit()

    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    return {"client": client, "db": db, "user": users["u1"], "people": people}


def options(html: str) -> dict:
    """번호 → (보이는 글자, 거르는 값). 「요청 받았다고 적기」 폼 기준."""
    out = {}
    for m in re.finditer(
            r'<option value="(\d+)"[^>]*data-search="([^"]*)">([^<]*)</option>',
            html):
        out.setdefault(int(m.group(1)), (m.group(3), m.group(2)))
    return out


# ── ① 안 붙는 자리 ──────────────────────────────────────────────────────────

def test_활발_연결완료에는_아무것도_안_붙는다(stage):
    """**대부분이 이쪽이다.** 다 붙이면 꼬리표가 소음이 된다.

    개발 자료 125명이 전부 여기 해당하고, 운영에서 걸린 것도 133명 중
    1명뿐이었다 — 꼬리표는 드물어야 눈에 띈다.
    """
    html = stage["client"].get("/ir").text
    shown = options(html)[stage["people"]["plain"].id][0]

    assert "[" not in shown, f"안 붙어야 할 줄에 꼬리표가 붙었습니다: {shown}"
    assert shown.strip() == "가담당 심사역 · 가담당벤처스"


def test_상태가_비어_있어도_안_붙는다(stage):
    """값을 정한 적 없는 옛 줄은 **멈춘 것이 아니다**(`is_paused` 와 같은 뜻).

    빈 값에 `[-]` 같은 것이 붙으면, 손댈 것이 없는 줄에 손댈 것이 있는
    것처럼 보인다.
    """
    from app.models import VcContact

    row = stage["db"].get(VcContact, stage["people"]["plain"].id)
    row.status = ""
    stage["db"].commit()

    shown = options(stage["client"].get("/ir").text)[row.id][0]
    assert "[" not in shown, f"빈 상태에 꼬리표가 붙었습니다: {shown}"


# ── ② 붙는 자리 ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("key,label_of", [
    ("left", lambda: _connect("left_room")),
    ("declined", lambda: _connect("declined")),
    ("working", lambda: _connect("in_progress")),
    ("paused", lambda: _status("paused")),
])
def test_빠지는_사람에게는_상태가_붙는다(stage, key, label_of):
    """딜 제안 관리에서 사라지는 그 갈래들 — 여기서는 **이유가 적힌다.**"""
    shown = options(stage["client"].get("/ir").text)[stage["people"][key].id][0]

    assert f"[{label_of()}]" in shown, (
        f"{key} 줄에 상태가 없습니다: {shown} ★ 왜 목록에 있는지 알 수 없습니다")


def test_명단에서_내린_사람은_명단_밖이라고_적는다(stage):
    """**사람의 상태가 아니라 명단의 상태**다 — 그래도 같은 자리에 적는다.

    쓰는 사람이 이 줄에서 묻는 것은 "왜 저쪽에서는 안 보이나" 하나다. 이것만
    빼면 명단에서 내린 사람만 아무 표시 없이 섞여, 고쳐야 할 곳이 사람인지
    명단인지 알 수 없다. 대신 **말을 갈라 둔다** — `검토중단`(사람)과
    `명단 밖`(명단)은 읽는 순간 어디를 손대야 하는지가 다르다.
    """
    from app.services import sheet_owner

    shown = options(stage["client"].get("/ir").text)[
        stage["people"]["off_list"].id][0]

    assert f"[{sheet_owner.OFF_LIST_LABEL}]" in shown, (
        f"명단에서 내린 사람이 그냥 서 있습니다: {shown}")


def test_두_갈래에_걸리면_둘_다_적는다(stage):
    """하나만 적으면 **고쳤는데 그대로**가 된다.

    `검토중단` 만 보이는 줄에서 상태를 풀어 준 사람은, 그 사람이 딜 제안
    관리에 뜰 것이라고 믿는다. 남은 이유(`방 나감`)가 화면에 없으면 그 믿음을
    고칠 길이 없다. 차례는 **상태 → 연결 → 명단**이다.
    """
    shown = options(stage["client"].get("/ir").text)[
        stage["people"]["both"].id][0]

    assert f"[{_status('paused')} · {_connect('left_room')}]" in shown, (
        f"걸린 갈래가 다 안 적혔습니다: {shown}")


# ── ③ 말은 한 곳에서 온다 ──────────────────────────────────────────────────

def test_한글_이름을_화면이_지어내지_않는다():
    """`sheet_owner.STATUS_LABELS` · `sheet_import.CONNECT_LABELS` 뿐이다.

    화면에 `방 나감` 을 손으로 적어 두면, 임포트가 그 말을 바꾸는 날 이
    화면만 옛말로 남는다 — 이 저장소가 반복해 당한 부류다.
    """
    from app.services import sheet_owner
    from app.services.sheet_import import CONNECT_LABELS

    src = IR_HTML.read_text(encoding="utf-8")
    # 주석은 뜻을 적는 자리라 말이 나온다 — 그려지는 부분만 본다.
    drawn = re.sub(r"\{#.*?#\}", "", src, flags=re.S)

    words = (set(CONNECT_LABELS.values())
             | set(sheet_owner.STATUS_LABELS.values())
             | {sheet_owner.OFF_LIST_LABEL})
    found = sorted(w for w in words if w in drawn)
    assert not found, (
        f"화면이 상태 이름을 직접 적고 있습니다: {found} ★ 서버(`pick_notes`)가 "
        f"주는 말만 그려야 합니다")


def test_판정이_서버에_있다():
    """템플릿이 `status` · `connect_stage` 값을 직접 보지 않는다.

    `활발 + 연결 완료면 안 붙인다`는 판정은 곧 발송 판정(`can_send_to`)이다.
    화면에 한 벌 더 적어 두면 문이 하나 늘 때 한쪽만 고쳐진다.
    """
    src = IR_HTML.read_text(encoding="utf-8")
    drawn = re.sub(r"\{#.*?#\}", "", src, flags=re.S)

    for raw in ("c.connect_stage", "c.status", "'connected'", '"connected"',
                "'active'", "'paused'"):
        assert raw not in drawn, (
            f"화면이 {raw} 를 직접 봅니다 ★ 판정이 두 벌이 됩니다")


# ── ④ 검색이 상태로도 걸린다 ───────────────────────────────────────────────

def test_상태로도_찾아진다(stage):
    """`방 나감` 을 쳐서 **그 사람들만** 볼 수 있어야 쓸모가 있다."""
    found = options(stage["client"].get("/ir").text)
    word = _connect("left_room").lower()

    hit = {cid for cid, (_, search) in found.items() if word in search}
    assert hit == {stage["people"]["left"].id, stage["people"]["both"].id}, (
        "상태로 좁혀지지 않거나 엉뚱한 사람이 걸립니다")


def test_보이는_말과_거르는_말이_같다(stage):
    """보이는 대로 쳤는데 아무도 안 나오면, 그 꼬리표는 없는 것과 같다."""
    for shown, search in options(stage["client"].get("/ir").text).values():
        tag = re.search(r"\[([^\]]+)\]", shown)
        if not tag:
            continue
        for word in tag.group(1).split(" · "):
            assert word.lower() in search, (
                f"화면에는 `{word}` 인데 그 말로 걸러지지 않습니다: {search}")


def test_거르는_값은_여전히_소문자다(stage):
    """`deals.html` 과 같은 방식 — 재료가 소문자라야 대소문자를 안 가린다."""
    html = stage["client"].get("/ir").text
    found = re.findall(r'data-search="([^"]*)"', html)
    assert found and all(v == v.lower() for v in found)


# ── ⑤ 어긋나지 않는다 ──────────────────────────────────────────────────────

def test_빠지는_사람은_빠짐없이_꼬리표를_단다(stage):
    """**딜 제안 관리에서 빠지는 사람은 반드시 꼬리표가 있다.**

    이 대응이 깨지면 꼬리표가 거짓말을 한다 — 아무 표시 없는 줄을 골랐는데
    그 사람은 발송 목록에 없는 사람인 자리다. 갈래를 하나 더 만드는 날
    (문이 셋이 되는 날) 여기서 걸린다.

    거꾸로는 성립하지 않는다 — `반응없음` 은 붙지만 발송 대상이다
    (바로 아래 검사).
    """
    from app.services import sheet_owner

    db, user = stage["db"], stage["user"]
    rows = sheet_owner.my_contacts(db, user)
    notes = sheet_owner.pick_notes(db, rows)
    sendable = {c.id for c in sheet_owner.recipients(db, user)}

    for c in rows:
        if c.id not in sendable:
            assert notes.get(c.id), (
                "발송 대상이 아닌데 아무 표시가 없습니다 ★ 왜 저쪽에서 안 "
                "보이는지 알 길이 없습니다")


def test_반응없음도_적는다(stage):
    """`반응없음` 은 발송 대상에서 **안 빠진다**. 그래도 적는다.

    꼬리표가 "왜 딜 제안 관리에서 빠졌나" 만 적는 표라면 이 사람에게는 붙지
    않아야 한다. 하지만 이 자리는 **지금 어떤 상태인지**를 적는 자리다 —
    상태 사전(`STATUS_LABELS`) 중 하나만 화면에서 빠지면, 표시가 없는 줄이
    `활발` 인지 `반응없음` 인지 알 수 없다. 안 붙는 것은 `활발` 하나다.

    붙는 줄이 늘어 소음이 되면 그때는 **여기(`pick_note`) 한 곳**을 고치면
    된다 — 화면 두 곳이 아니다.
    """
    from app.models import VcContact
    from app.services import sheet_owner

    row = stage["db"].get(VcContact, stage["people"]["plain"].id)
    row.status = sheet_owner.STATUS_NO_RESPONSE
    stage["db"].commit()

    shown = options(stage["client"].get("/ir").text)[row.id][0]
    assert f"[{_status(sheet_owner.STATUS_NO_RESPONSE)}]" in shown, shown
    # 그래도 보낼 수 있는 사람이다 — 꼬리표가 발송 판정을 바꾸지 않는다.
    assert row.id in {c.id for c in sheet_owner.recipients(
        stage["db"], stage["user"])}, "꼬리표가 발송 대상을 흔들었습니다"


def test_두_폼에_같이_붙는다(stage):
    """매크로 한 벌이라 한쪽만 붙을 수 없다 — 그래도 못 박아 둔다."""
    html = stage["client"].get("/ir").text
    who = stage["people"]["left"].id

    lines = re.findall(rf'<option value="{who}"[^>]*>([^<]*)</option>', html)
    assert len(lines) == 2, f"두 폼에 다 안 섰습니다: {lines}"
    assert all("[" in line for line in lines), (
        f"한쪽 폼에만 꼬리표가 붙었습니다: {lines}")


def test_명단_설정을_한_번만_읽는다(stage):
    """사람마다 물으면 125줄짜리 화면에서 질의가 125번 나간다."""
    from sqlalchemy import event

    from app.db import engine
    from app.services import sheet_owner

    rows = sheet_owner.my_contacts(stage["db"], stage["user"])
    seen = []

    def watch(conn, cursor, statement, params, context, many):
        seen.append(statement)

    event.listen(engine, "before_cursor_execute", watch)
    try:
        notes = sheet_owner.pick_notes(stage["db"], rows)
    finally:
        event.remove(engine, "before_cursor_execute", watch)

    assert notes, "꼬리표가 하나도 안 나왔습니다 — 검사가 아무것도 안 봅니다"
    assert len(seen) <= 1, f"질의가 {len(seen)}번 나갔습니다: {seen}"


# ── 거들개 ──────────────────────────────────────────────────────────────────

def _connect(stage_key: str) -> str:
    from app.services.sheet_import import CONNECT_LABELS

    return CONNECT_LABELS[stage_key]


def _status(key: str) -> str:
    from app.services import sheet_owner

    return sheet_owner.STATUS_LABELS[key]
