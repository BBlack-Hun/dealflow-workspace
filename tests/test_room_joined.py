"""카톡방 `확인됨` ↔ `카톡방 참여여부` — 두 칸이 같은 말을 하는가.

사용자 요청: "카톡방 컬럼의 확인됨이랑 카톡방 참여여부랑 동기화 되게 해줘".
규칙은 `app/services/room_joined` 한 곳에 있다. 여기서는 그 규칙이 **적는 자리
마다** 실제로 지나가는지를 본다 — 방 확인 결과(PC 발송기) · 표에서 고치기 ·
수정창 · 시트 가져오기 · 정리 스크립트. 한 자리라도 규칙을 안 지나가면 두
칸은 그 자리에서 다시 갈린다.

이름·회사는 전부 지어낸 값이다 — 저장소가 공개다.
"""
from __future__ import annotations

import json
import re
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from app.models import SendItem, SendJob, VcContact
from app.services import room_joined, sheet_import as si

from .conftest import DEMO_TOKEN, auth

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "sync_room_joined.py"

FIRM = "가나다벤처스"


def _contact(db, *, joined=None, verified="unverified", stage="connected",
             room="홍길동 심사역 가나다벤처스 방", name="홍길동", firm=FIRM,
             hidden=0) -> VcContact:
    row = VcContact(user_id=1, name=name, title="심사역", firm=firm,
                    channel_kakao=1, kakao_room_name=room,
                    room_verified=verified, kakao_joined=joined,
                    connect_stage=stage, status="active", is_hidden=hidden)
    db.add(row)
    db.commit()
    return row


def _fresh(db, row_id: int) -> VcContact:
    db.expire_all()   # 서버가 같은 파일 DB 를 따로 고쳤다 — 다시 읽는다
    return db.get(VcContact, row_id)


# ── 참여여부 칸의 뜻 — 판정은 `sheet_import` 한 곳 ──────────────────────────

@pytest.mark.parametrize("value", ["O", "o", "○", "●", "○, DAY", "○, DAY, SUMMIT",
                                   "완료", " O "])
def test_참여_표시로_읽는다(value):
    assert si.joined_state(value) == si.JOINED_YES


@pytest.mark.parametrize("value", ["X", "x", "X, IRDAY", "참여안함", "방 나감"])
def test_안_참여로_읽는다(value):
    assert si.joined_state(value) == si.JOINED_NO


@pytest.mark.parametrize("value", [None, "", "   "])
def test_빈칸은_빈칸이다(value):
    assert si.joined_state(value) == si.JOINED_EMPTY


def test_다른_말은_뜻을_정하지_않는다():
    assert si.joined_state("확인 필요") == si.JOINED_OTHER


def test_행사_이름이_붙은_참여_표시도_시트에서_참여로_읽는다():
    """`○, DAY` 는 참여다 — 시트를 읽어 연결 단계를 정하는 쪽도 같은 판정을 탄다.

    예전에는 칸 전체를 보기 목록과 견줘서 이 줄이 참여로 안 읽혔다. 두 쪽이
    다른 값을 참여로 읽으면, 방 확인을 맞추는 쪽과 연결 단계가 서로 갈린다.
    """
    assert si.is_invited("○, DAY")
    assert si.connect_stage("○, DAY", "") == si.STAGE_CONNECTED
    # 안 참여 표시는 그대로 안 참여다.
    assert not si.is_invited("X, IRDAY")


# ── 규칙 1 · 4 — PC 발송기의 방 확인 결과 ───────────────────────────────────

def _verify(logged_in, db, contact: VcContact, verdict: str) -> None:
    """방 확인 잡 한 줄을 만들어 발송기가 결과를 보낸 것처럼 한다."""
    job = SendJob(user_id=1, kind="verify_room", status="running", total=1)
    db.add(job)
    db.flush()
    item = SendItem(job_id=job.id, contact_id=contact.id,
                    room_name=contact.kakao_room_name, message="", status="pending")
    db.add(item)
    db.commit()
    status = "sent" if verdict == "verified" else "failed"
    r = logged_in.post(f"/api/agent/items/{item.id}/result",
                       json={"status": status, "verify_result": verdict},
                       headers=auth(DEMO_TOKEN))
    assert r.status_code == 200, r.text


@pytest.mark.parametrize("before", [None, "", "X", "x"])
def test_확인됨이면_참여여부가_O_가_된다(logged_in, db, before):
    row = _contact(db, joined=before)
    _verify(logged_in, db, row, "verified")
    row = _fresh(db, row.id)
    assert row.room_verified == "verified"
    assert row.kakao_joined == "O"


@pytest.mark.parametrize("before", ["○", "●", "○, DAY", "완료", "확인 필요"])
def test_확인됨이어도_이미_적힌_참여_표시는_그대로다(logged_in, db, before):
    """`○, DAY` 를 `O` 로 갈면 시트에서 온 행사 표시가 사라진다."""
    row = _contact(db, joined=before)
    _verify(logged_in, db, row, "verified")
    row = _fresh(db, row.id)
    assert row.room_verified == "verified"
    assert row.kakao_joined == before


@pytest.mark.parametrize("verdict", ["not_found", "ambiguous"])
@pytest.mark.parametrize("before", [None, "O", "X"])
def test_못_찾았다고_참여여부를_건드리지_않는다(logged_in, db, verdict, before):
    """규칙 4 — Windows 검색이 못 찾는 일이 잦다. `X` 를 적으면 틀린 `X` 가 된다."""
    row = _contact(db, joined=before, verified="verified")
    _verify(logged_in, db, row, verdict)
    row = _fresh(db, row.id)
    assert row.room_verified == verdict
    assert row.kakao_joined == before


@pytest.mark.parametrize("stage", ["left_room", "declined"])
def test_나갔다고_적힌_줄은_확인돼도_확인됨을_달지_않는다(logged_in, db, stage):
    """방 제목은 그 사람이 나간 뒤에도 내 카톡에 남는다 — 방을 찾았다고 그
    사람이 방에 있는 것이 아니다. 규칙 2 가 바로 지울 상태를 만들지 않는다."""
    row = _contact(db, joined="X", stage=stage)
    _verify(logged_in, db, row, "verified")
    row = _fresh(db, row.id)
    assert row.kakao_joined == "X"
    assert row.room_verified == "unverified"
    assert row.connect_stage == stage


def test_동명이인이라_확인을_못_보낸_줄도_참여여부는_그대로다(logged_in, db):
    """[방 연결 확인] 이 보내기 전에 막는 줄(`복수 매칭`)도 같은 자리를 지난다."""
    first = _contact(db, joined="X", room="홍길동")
    second = _contact(db, joined="X", room="홍길동 님", firm="가나다벤처스2")
    logged_in.post("/api/contacts/verify-rooms", json={"contact_ids": [first.id, second.id]})
    for row_id in (first.id, second.id):
        row = _fresh(db, row_id)
        assert row.room_verified == "ambiguous"
        assert row.kakao_joined == "X"


# ── 규칙 2 · 3 · 5 — 사람이 표에서 고칠 때 ──────────────────────────────────

def test_참여여부를_X_로_바꾸면_확인됨이_풀리고_응답이_두_칸을_싣는다(logged_in, db):
    """표에서 칸 하나를 고치면 화면은 다시 받지 않는다 — 옆 `카톡방` 칸은
    응답이 알려 줘야 그 자리에서 바뀐다(`contacts.js` 의 `syncRoomCells`)."""
    row = _contact(db, joined="O", verified="verified")
    r = logged_in.patch(f"/api/contacts/{row.id}", json={"kakao_joined": "X"})
    assert r.status_code == 200
    body = r.json()
    assert body["room_verified"] == "unverified"
    assert body["kakao_joined"] == "X"
    assert body["send_state"] == "unverified"
    assert body["send_label"] == "미확인"
    assert _fresh(db, row.id).room_verified == "unverified"


@pytest.mark.parametrize("stage", ["left_room", "declined"])
def test_방_나감으로_고르면_확인됨이_풀린다(logged_in, db, stage):
    row = _contact(db, joined="O", verified="verified")
    r = logged_in.patch(f"/api/contacts/{row.id}", json={"connect_stage": stage})
    assert r.status_code == 200
    assert r.json()["room_verified"] == "unverified"
    row = _fresh(db, row.id)
    assert row.room_verified == "unverified"
    # 참여여부까지 지어 적지는 않는다 — 사람이 고른 것은 단계뿐이다.
    assert row.kakao_joined == "O"


@pytest.mark.parametrize("state", ["unverified", "not_found", "ambiguous", "verified"])
def test_참여여부를_O_로_바꿔도_방_확인은_그대로다(logged_in, db, state):
    """규칙 3 — 방이 있다는 것은 PC 발송기만 확인할 수 있다."""
    row = _contact(db, joined="", verified=state)
    r = logged_in.patch(f"/api/contacts/{row.id}", json={"kakao_joined": "O"})
    assert r.json()["room_verified"] == state
    assert _fresh(db, row.id).room_verified == state


def test_X_로_바꿔도_방_없음은_미확인이_되지_않는다(logged_in, db):
    """`방 없음` 을 `미확인` 으로 바꾸면 **보낼 수 있는 갈래로 넘어간다**
    (`dashboard._SENDABLE_ROOM`). 푸는 것은 `확인됨` 뿐이다."""
    row = _contact(db, joined="O", verified="not_found")
    logged_in.patch(f"/api/contacts/{row.id}", json={"kakao_joined": "X"})
    assert _fresh(db, row.id).room_verified == "not_found"


def test_참여여부를_비워도_확인됨은_그대로다(logged_in, db):
    """규칙 5."""
    row = _contact(db, joined="O", verified="verified")
    logged_in.patch(f"/api/contacts/{row.id}", json={"kakao_joined": ""})
    row = _fresh(db, row.id)
    assert row.room_verified == "verified"
    assert row.kakao_joined == ""


def test_안_고친_X_는_확인됨을_풀지_않는다(logged_in, db):
    """이미 `확인됨` + `X` 로 어긋나 있던 줄. 수정창은 저장할 때 모든 칸을 함께
    보내므로 안 고친 `X` 도 매번 올라온다 — 메모 한 줄 고쳤다고 덩달아 풀리면
    무엇 때문에 풀렸는지 아무도 모른다. 그런 줄은 정리 스크립트가 세어 보인다."""
    row = _contact(db, joined="X", verified="verified")
    logged_in.patch(f"/api/contacts/{row.id}", json={"memo": "통화함", "kakao_joined": "X"})
    assert _fresh(db, row.id).room_verified == "verified"


def test_방_이름을_바꾸면_예전처럼_확인이_풀린다(logged_in, db):
    row = _contact(db, joined="O", verified="verified")
    logged_in.patch(f"/api/contacts/{row.id}",
                    json={"kakao_room_name": "홍길동 심사역 가나다벤처스 새 방"})
    row = _fresh(db, row.id)
    assert row.room_verified == "unverified"
    assert row.kakao_joined == "O"


def test_표가_그리는_카톡방_칸과_응답이_같은_말을_한다(logged_in, db):
    """표를 그릴 때와 칸 하나를 고친 뒤의 응답이 **같은 함수**를 쓴다
    (`routers/contacts._room_cell`). 둘이 따로 정하면 고친 직후의 칸과
    새로고침한 칸이 다른 말을 한다."""
    from app.models import User
    from app.routers.contacts import contact_rows

    row = _contact(db, joined="O", verified="verified")
    r = logged_in.patch(f"/api/contacts/{row.id}", json={"kakao_joined": "X"}).json()
    db.expire_all()
    shown = next(x for x in contact_rows(db, db.get(User, 1)) if x["id"] == row.id)
    assert (shown["send_state"], shown["send_label"], shown["send_class"]) == (
        r["send_state"], r["send_label"], r["send_class"])
    assert shown["kakao_joined"] == r["kakao_joined"] == "X"


# ── 시트 가져오기도 같은 규칙을 지난다 ──────────────────────────────────────

def _sheet(joined: str) -> si.SheetAParse:
    return si.SheetAParse(contacts=[si.ParsedContact(
        row_no=4, name="홍길동", title="심사역", firm=FIRM, kakao_joined=joined)])


def test_시트가_참여여부를_X_로_바꾸면_확인됨이_풀린다(db, users):
    row = _contact(db, joined="O", verified="verified")
    si.apply_sheet_a(db, _sheet("X"), user_id=1)
    db.commit()
    row = _fresh(db, row.id)
    assert row.kakao_joined == "X"
    assert row.room_verified == "unverified"


def test_시트가_같은_값을_다시_올려도_확인됨은_그대로다(db, users):
    row = _contact(db, joined="O", verified="verified")
    si.apply_sheet_a(db, _sheet("○"), user_id=1)
    db.commit()
    assert _fresh(db, row.id).room_verified == "verified"


# ── `room_verified` 를 적는 자리는 한 곳이다 ─────────────────────────────────

#: `.room_verified = …` 를 적어도 되는 파일. **담당자 줄(`VcContact`)이 아닌 표**
#: 이거나 규칙이 사는 자리다.
ALLOWED_WRITERS = {
    "app/services/room_joined.py": "규칙이 사는 자리",
    "app/services/room_match.py": "스타트업 기업(`IrCompany`)의 방 — 다른 표다",
    "app/routers/sourcing.py": "딜 소싱 명단(`SourcingContact`) — 다른 표다",
}


def test_담당자_방_확인_값은_room_joined_만_적는다():
    """같은 판단을 두 곳에 적으면 한쪽이 낡는다 — 이 저장소가 반복해 당한 부류다.

    새 자리에서 `contact.room_verified = …` 를 적으면 여기서 걸린다. 그 자리는
    `room_joined.set_verdict` 나 `after_edit` 를 불러야 참여여부가 함께 맞는다.
    """
    pattern = re.compile(r"\.room_verified\s*=(?!=)")
    found = []
    for base in ("app", "scripts"):
        for path in sorted((ROOT / base).rglob("*.py")):
            rel = path.relative_to(ROOT).as_posix()
            if rel in ALLOWED_WRITERS:
                continue
            for no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if line.lstrip().startswith("#"):
                    continue
                if pattern.search(line):
                    found.append(f"{rel}:{no}: {line.strip()}")
    assert not found, "room_joined 를 거치지 않고 방 확인 값을 적는다:\n" + "\n".join(found)


def test_잘못된_방_확인_값은_받지_않는다(db, users):
    row = _contact(db)
    with pytest.raises(ValueError):
        room_joined.set_verdict(row, "확인됨")


# ── 정리 스크립트 — 이미 쌓인 줄 ────────────────────────────────────────────

def _db_path() -> Path:
    import os

    return Path(os.environ["DATABASE_URL"][len("sqlite:///"):])


def _run(*args) -> str:
    out = subprocess.run(
        [sys.executable, str(SCRIPT), "--db", str(_db_path()), *args],
        capture_output=True, text=True, cwd=str(ROOT), check=False)
    assert out.returncode == 0, out.stdout + out.stderr
    return out.stdout


def _joined(row_id: int):
    con = sqlite3.connect(str(_db_path()))
    try:
        return con.execute("SELECT kakao_joined FROM vc_contacts WHERE id = ?",
                           (row_id,)).fetchone()[0]
    finally:
        con.close()


def _counted(text: str, label: str) -> int:
    found = re.search(re.escape(label) + r"[^\d]*?(\d+)줄", text)
    assert found, f"미리보기에 `{label}` 줄이 없다:\n{text}"
    return int(found.group(1))


def _seed(db) -> dict:
    """갈래마다 한 줄씩 — 스크립트가 각각을 어떻게 가르는지 본다."""
    rows = {
        "빈칸": _contact(db, joined=None, verified="verified", firm="가나다벤처스1"),
        "감춘_빈칸": _contact(db, joined="", verified="verified", firm="가나다벤처스2",
                          hidden=1),
        "X": _contact(db, joined="X", verified="verified", firm="가나다벤처스3"),
        "나감_X": _contact(db, joined="X", verified="verified", stage="left_room",
                         firm="가나다벤처스4"),
        "나감_빈칸": _contact(db, joined=None, verified="verified", stage="left_room",
                          firm="가나다벤처스5"),
        "O": _contact(db, joined="○, DAY", verified="verified", firm="가나다벤처스6"),
        "다른말": _contact(db, joined="확인 필요", verified="verified", firm="가나다벤처스7"),
        # `확인됨` 이 아닌 줄 — 규칙 3 그대로라 건드리지 않는다.
        "미확인_O": _contact(db, joined="O", verified="unverified", firm="가나다벤처스8"),
        "미확인_빈칸": _contact(db, joined=None, verified="unverified", firm="가나다벤처스9"),
    }
    return {k: v.id for k, v in rows.items()}


def test_미리보기가_기본이고_DB_에_한_글자도_안_쓴다(db, users):
    ids = _seed(db)
    before = {k: _joined(v) for k, v in ids.items()}
    text = _run()
    assert "미리보기" in text and "읽기 전용" in text
    assert {k: _joined(v) for k, v in ids.items()} == before


def test_미리보기가_갈래를_센다(db, users):
    ids = _seed(db)
    text = _run("--ids")
    assert _counted(text, "`확인됨` 인 줄") == 7
    assert _counted(text, "채움 (빈칸 → O)") == 2
    assert _counted(text, "어긋남 (확인됨 + X)") == 2       # 나감 단계의 X 도 여기 센다
    assert _counted(text, "나간 단계 + 빈칸") == 1
    assert _counted(text, "그대로 (이미 참여 표시)") == 1
    assert _counted(text, "다른 말") == 1
    # 이름은 찍지 않는다 — 번호만.
    assert "홍길동" not in text
    assert str(ids["X"]) in text


def test_적용하면_빈칸만_O_로_채우고_되돌릴_수_있다(db, users, tmp_path):
    ids = _seed(db)
    baseline = tmp_path / "room_joined.json"

    _run("--apply", "--save-baseline", str(baseline))

    assert _joined(ids["빈칸"]) == "O"
    assert _joined(ids["감춘_빈칸"]) == "O"
    # 세기만 하는 갈래는 그대로다.
    assert _joined(ids["X"]) == "X"
    assert _joined(ids["나감_X"]) == "X"
    assert _joined(ids["나감_빈칸"]) is None
    assert _joined(ids["O"]) == "○, DAY"
    assert _joined(ids["다른말"]) == "확인 필요"
    assert _joined(ids["미확인_O"]) == "O"
    assert _joined(ids["미확인_빈칸"]) is None
    # 되돌리기 파일에는 번호와 전 값만 — 이름이 없다.
    saved = json.loads(baseline.read_text(encoding="utf-8"))
    assert sorted(item["id"] for item in saved) == sorted([ids["빈칸"], ids["감춘_빈칸"]])
    assert "홍길동" not in baseline.read_text(encoding="utf-8")

    # 두 번 돌리면 채울 것이 없다.
    assert _counted(_run(), "`확인됨` 인 줄") == 7
    assert "채움" not in _run()

    _run("--restore", str(baseline), "--apply")
    assert _joined(ids["빈칸"]) is None
    assert _joined(ids["감춘_빈칸"]) == ""


def test_적용에는_되돌릴_파일이_있어야_한다(db, users):
    _seed(db)
    out = subprocess.run(
        [sys.executable, str(SCRIPT), "--db", str(_db_path()), "--apply"],
        capture_output=True, text=True, cwd=str(ROOT), check=False)
    assert out.returncode == 2
    assert "--save-baseline" in out.stderr


def test_스크립트와_살아_있는_길이_같은_판정을_탄다(db, users):
    """스크립트가 채우는 줄 = 방 확인이 지금 `확인됨` 으로 끝났다면 `O` 가 적혔을 줄."""
    import scripts.sync_room_joined as tool

    for joined, stage in [(None, "connected"), ("", "in_progress"), ("X", "connected"),
                          (None, "left_room"), ("○", "connected"), ("메모", "connected")]:
        live = room_joined.joined_after_verified(joined, stage)
        assert (tool.classify(joined, stage) == tool.FILL) == (
            live is not None and si.joined_state(joined) == si.JOINED_EMPTY), (joined, stage)


# ── 좌측 [스타트업] 화면 — **같은 표, 같은 규칙** ───────────────────────────
#
# 사용자 요청: "그 스타트업 메뉴에도 카톡 동기화 하는거 추가하자".
#
# 그 화면의 줄은 투자사 관리 현황과 **같은 표**(`VcContact`)이고, 그 화면의
# `카톡 연결 여부` 칸이 곧 `kakao_joined` 다(`contact_columns.STARTUP_LAYOUT`).
# 고치는 길도 같다(`PATCH /api/contacts/{id}` · 같은 `contacts.js`). 그래서
# 규칙을 한 벌 더 만들지 않는다 — 대신 **그 화면의 줄에서도** 규칙이 실제로
# 지나가는지를 여기서 본다. 언젠가 스타트업 화면이 제 길을 따로 파면 여기서 걸린다.

STARTUP_LIST = "샘플 스타트업(9)"


@pytest.fixture()
def startup_row(db, users):
    from app.models import SheetOwner
    from app.services import contact_columns as cc

    db.add(SheetOwner(label=STARTUP_LIST, user_id=1, layout=cc.STARTUP, is_hidden=1))
    db.commit()
    row = _contact(db, joined="O", verified="verified", firm="가나다벤처스")
    row.source_sheet = STARTUP_LIST
    db.commit()
    return row


def test_스타트업_화면의_카톡_연결_여부가_참여여부_그_칸이다(logged_in, db, startup_row):
    """두 화면이 같은 칸을 고친다는 전제가 깨지면 이 검사들이 엉뚱한 칸을 본다."""
    from urllib.parse import quote

    from app.services import contact_columns as cc

    col = next(c for c in cc.STARTUP_LAYOUT.tail if c.label == "카톡 연결 여부")
    assert (col.key, col.source) == ("kakao_joined", "field")
    html = logged_in.get(f"/{cc.page_of(cc.STARTUP)}?sheet={quote(STARTUP_LIST)}").text
    assert 'data-inline-url="/api/contacts"' in html
    assert 'data-field="kakao_joined"' in html


def test_스타트업_줄도_X_로_바꾸면_확인됨이_풀린다(logged_in, db, startup_row):
    r = logged_in.patch(f"/api/contacts/{startup_row.id}", json={"kakao_joined": "X"})
    assert r.status_code == 200
    assert r.json()["room_verified"] == "unverified"
    assert r.json()["kakao_joined"] == "X"
    assert _fresh(db, startup_row.id).room_verified == "unverified"


def test_스타트업_줄도_확인됨이면_연결_여부가_O_가_된다(logged_in, db, startup_row):
    startup_row.kakao_joined = None
    startup_row.room_verified = "unverified"
    db.commit()
    _verify(logged_in, db, startup_row, "verified")
    row = _fresh(db, startup_row.id)
    assert (row.room_verified, row.kakao_joined) == ("verified", "O")


def test_정리_스크립트가_스타트업_화면을_따로_센다(db, startup_row):
    """좌측 [스타트업] 화면의 줄도 같이 채우되, 요약은 화면별로 갈라 찍는다."""
    startup_row.kakao_joined = None
    db.commit()
    _contact(db, joined=None, verified="verified", firm="가나다벤처스2")
    text = _run()
    assert "`확인됨` 인 줄 2줄  (투자사 관리 현황 1 · 스타트업 1)" in text
    assert "화면: 투자사 관리 현황 1 · 스타트업 1" in text
    assert re.search(r"스타트업\s+전체 1 · 확인됨 1 · 참여 표시 0 · X 0 · 빈칸 1", text), text
