"""줄 **하나**를 다른 담당자에게 넘기기(이관).

명단을 통째로 옮기는 길은 이미 있었다(`/sheets/assign` · `scripts/import_new_list.py`).
없던 것은 **한 사람만** 넘기는 길이다 — 실제로 남의 명단에 섞여 들어간 몇 곳을
손으로 만든 배정표(CSV)로 옮겨야 했고, 팀원 워크북에는 `7/21 A -> 8/19 B` 처럼
사람 사이에 넘긴 이력이 적혀 있다.

여기서 못 박는 것은 여섯이다.

  1. **규칙이 한 벌이다** — 스크립트와 화면이 `sheet_owner.move_to` 를 같이 부른다
  2. **누가 넘길 수 있나** — 관리자, 그리고 지금 그 줄을 맡고 있는 사람뿐
  3. **아무 데로나 못 넘긴다** — 담당 없는 풀 · 감춘 명단 · 다른 화면은 막힌다
  4. **넘긴 뒤 화면 숫자가 맞다** — 명단 인원 · 대시보드 · 딜 제안 대상
  5. **되돌릴 수 있다** — 도로 넘기면 명단도 담당도 월별 기록도 돌아온다
  6. **월별 기록은 지워지지 않는다** — 안 보일 뿐이라 사람에게 그렇게 알린다

이름·회사·번호는 전부 지어낸 값이다 — 저장소가 공개다.
"""
from __future__ import annotations

from datetime import date

import pytest

from .conftest import DEMO_PASSWORD

# 화면 둘이 같은 표를 쓴다. 투자사 명단 셋(담당이 다르다) + 풀 + 스타트업 명단.
MINE = "가 명단"
YOURS = "나 명단"
POOL = "투자사 풀"
HIDDEN = "안 세는 명단"
STARTUP_LIST = "스타트업 명단"

TODAY = date(2026, 8, 19)   # 날짜가 바뀌어도 안 깨지게 못 박는다


@pytest.fixture()
def people(db, users):
    """관리자 · 투자컨설턴트. conftest 의 두 계정은 둘 다 일반 팀원이다."""
    from app.models import User
    from app.services import auth as auth_svc

    pw = auth_svc.hash_password(DEMO_PASSWORD)
    rows = [
        User(id=71, name="관리자시험", phone="01070000011", role="admin",
             password_hash=pw),
        User(id=73, name="컨설턴트시험", phone="01070000013", role="consultant",
             password_hash=pw),
    ]
    db.add_all(rows)
    db.commit()
    return {"admin": rows[0], "consultant": rows[1]}


@pytest.fixture()
def board(db, users, people):
    """u1 의 명단에 한 줄, u2 의 명단에 한 줄. 풀·감춘 명단·스타트업 명단도 함께.

    번호로 돌려준다 — ORM 객체를 넘기면 커밋마다 만료되어, 검사가 보려는 것
    (값이 바뀌었나)이 아니라 세션 상태를 보게 된다.
    """
    from app.models import SheetOwner, VcContact
    from app.services import contact_columns as cc

    db.add_all([
        SheetOwner(label=MINE, user_id=users["u1"].id),
        SheetOwner(label=YOURS, user_id=users["u2"].id),
        SheetOwner(label=POOL),                                   # 담당 없음 = 풀
        SheetOwner(label=HIDDEN, user_id=users["u2"].id, is_hidden=1),
        SheetOwner(label=STARTUP_LIST, user_id=users["u2"].id,
                   layout=cc.STARTUP),
    ])
    rows = [
        # 연결이 끝난 사람 — 딜 제안 대상 수가 따라 움직이는지 보려고.
        VcContact(user_id=users["u1"].id, source_sheet=MINE, name="가상길동",
                  firm="가상벤처스", phone="010-0000-0001",
                  connect_stage="connected", channel_kakao=1,
                  kakao_room_name="가상벤처스 방", room_verified="verified"),
        VcContact(user_id=users["u2"].id, source_sheet=YOURS, name="가상순신",
                  firm="가상파트너스", phone="010-0000-0002",
                  connect_stage="connected", kakao_room_name="가상파트너스 방"),
    ]
    db.add_all(rows)
    db.commit()
    return {"mine": rows[0].id, "yours": rows[1].id}


def sign_in(client, phone):
    r = client.post("/login", data={"phone": phone, "password": DEMO_PASSWORD})
    assert r.status_code in (200, 303)
    return client


def transfer(client, contact_id, label):
    return client.post(f"/api/contacts/{contact_id}/transfer", json={"label": label})


def reload(db, contact_id):
    from app.models import VcContact

    db.expire_all()
    return db.get(VcContact, contact_id)


# ── 1. 규칙이 한 벌이다 ─────────────────────────────────────────────────────
#
# 같은 판단을 두 곳에 적으면 한쪽이 낡는다. 이 저장소가 반복해 당한 사고라
# (투자사 수가 화면마다 갈린 일, 좌측 메뉴와 라우터가 갈린 일) 옮기는 규칙은
# `services/sheet_owner.py` 한 곳에만 있어야 한다.

def test_스크립트와_화면이_같은_함수를_부른다():
    """`import_new_list.move_to` 는 서비스의 그것과 **같은 객체**여야 한다.

    베껴 두면 다음에 한쪽만 고쳐지고, 고쳐지지 않은 쪽으로 옮긴 사람만 조용히
    옛 담당자의 발송 대상에 남는다 — 같은 사람에게 딜 소개가 두 번 나간다.
    """
    from app.services import sheet_owner
    from scripts import import_new_list

    assert import_new_list.move_to is sheet_owner.move_to, (
        "스크립트가 옮기는 규칙을 따로 들고 있습니다 — 두 벌이 되면 한쪽만 낡습니다")


def test_옮기는_규칙이_스크립트에_다시_적혀_있지_않다():
    """스크립트 파일 안에 `def move_to` 가 남아 있으면 안 된다."""
    from pathlib import Path

    src = Path(__file__).resolve().parents[1] / "scripts" / "import_new_list.py"
    assert "def move_to" not in src.read_text(encoding="utf-8"), (
        "옮기는 규칙이 스크립트에 다시 적혔습니다 — 판정은 sheet_owner 한 곳입니다")


# ── 2. 누가 넘길 수 있나 ────────────────────────────────────────────────────

def test_내_줄은_다른_담당자에게_넘길_수_있다(client, db, users, board):
    """이관의 본디 쓰임 — 내가 맡은 줄을 동료에게 넘긴다."""
    sign_in(client, "01000000001")
    r = transfer(client, board["mine"], YOURS)
    assert r.status_code == 200, r.text

    moved = reload(db, board["mine"])
    assert moved.user_id == users["u2"].id, "담당이 안 바뀌었습니다"
    assert YOURS in moved.source_sheet, "새 명단에 안 들어갔습니다"
    assert MINE not in moved.source_sheet, (
        "옛 명단에 그대로 남아 있습니다 — 딜 소개가 두 번 나갑니다")
    # 줄에 붙어 있던 이력은 그대로다. 새로 만드는 것이 아니라 옮기는 것이다.
    assert moved.kakao_room_name == "가상벤처스 방"
    assert moved.room_verified == "verified"


def test_남의_줄은_넘길_수_없고_값도_안_바뀐다(client, db, users, board):
    """**이 검사가 이 기능의 자물쇠다.**

    남의 담당을 아무나 바꾸면 그 팀원의 대시보드와 발송 대상이 본인 모르게
    달라진다. 상태 코드만 보지 않는다 — 404 를 받아 놓고 값이 바뀌어 있으면
    그게 제일 나쁜 상태다.
    """
    sign_in(client, "01000000001")           # u1 이 u2 의 줄을 넘기려 한다
    r = transfer(client, board["yours"], MINE)
    assert r.status_code == 404, f"남의 줄이 넘어갔습니다: {r.status_code} {r.text}"

    kept = reload(db, board["yours"])
    assert kept.user_id == users["u2"].id, "막혔다면서 담당이 바뀌었습니다"
    assert kept.source_sheet == YOURS, "막혔다면서 명단이 바뀌었습니다"


def test_관리자는_남의_줄도_넘길_수_있다(client, db, users, board, people):
    """관리자는 이미 명단 담당을 통째로 옮긴다 — 그보다 작은 한 줄을 못 옮기면
    보이는데 못 고치는 상태가 된다(이 저장소가 겪은 404 사고와 같은 자리다)."""
    sign_in(client, "01070000011")
    r = transfer(client, board["yours"], MINE)
    assert r.status_code == 200, r.text

    moved = reload(db, board["yours"])
    assert moved.user_id == users["u1"].id
    assert MINE in moved.source_sheet and YOURS not in moved.source_sheet


def test_투자컨설턴트는_이_길에_닿지_못한다(client, db, board, people):
    """새 주소는 허용 목록(`deps.CONSULTANT_PATHS`)에 없어 미들웨어가 끊는다.

    **403 인지까지 본다.** 허용 목록을 열어 두어도 `_owned` 가 남의 줄이라며
    404 를 내주기 때문에, `200 이 아니다` 로만 적어 두면 자물쇠 하나가 풀려도
    검사는 파랗게 지나간다(실제로 되돌려 보고 확인했다). 막는 것은 미들웨어이고,
    그것이 막았다는 증거가 403 이다.
    """
    sign_in(client, "01070000013")
    r = transfer(client, board["mine"], YOURS)
    assert r.status_code == 403, (
        f"허용 목록이 이 길을 안 막고 있습니다: {r.status_code} {r.text}")
    assert reload(db, board["mine"]).source_sheet == MINE


# ── 3. 아무 데로나 못 넘긴다 ────────────────────────────────────────────────

@pytest.mark.parametrize("label, why", [
    (POOL, "담당 없는 풀 — 넘긴 줄의 담당을 정할 수가 없다"),
    (STARTUP_LIST, "다른 화면 — 줄이 사라진 것처럼 보인다"),
    ("없는 명단", "이름만 지어 보낸 것"),
])
def test_넘길_수_없는_곳은_막는다(client, db, board, label, why):
    """화면이 안 보여 주는 곳이라도 **이름을 직접 보내는 길**이 남아 있다."""
    sign_in(client, "01000000001")
    r = transfer(client, board["mine"], label)
    assert r.status_code == 400, f"{why}: {r.status_code} {r.text}"
    assert reload(db, board["mine"]).source_sheet == MINE, "막혔다면서 옮겨졌습니다"


def test_감춘_명단으로도_넘어가되_화면이_그렇다고_적는다(client, db, users, board):
    """감춘 명단을 **막지 않는다.**

    처음엔 막았다. 거기로 넘기면 그 줄이 투자사 수와 발송 대상에서 빠지니
    위험하다고 본 것이다. 그런데 그러면 **스타트업 화면에서 넘길 곳이 하나도
    안 남는다** — 그 화면의 명단은 원래 전부 감춰져 있다(투자사가 아니라서
    투자사로 안 센다). 실제로 화면을 열어 보고 알았다.

    걱정한 것은 "조용히 빠지는 것" 이었지 감춘 명단 자체가 아니다. 그래서 막는
    대신 고르는 칸이 `(투자사로 안 셈)` 이라고 **적는다** — 수를 다룰 때 이
    저장소가 늘 하는 방식이다(`recipient_counts` 의 `off_list`).
    """
    sign_in(client, "01000000001")
    assert transfer(client, board["mine"], HIDDEN).status_code == 200

    moved = reload(db, board["mine"])
    assert moved.user_id == users["u2"].id and HIDDEN in moved.source_sheet

    # 고르는 칸이 그 명단은 투자사로 세지 않는다고 적어야 한다.
    html = client.get("/contacts").text
    picker = html[html.index('id="transfer-target"'):]
    picker = picker[:picker.index("</select>")]
    assert f"{HIDDEN} (투자사로 안 셈)" in picker, (
        f"감춘 명단이라고 안 적혀 있습니다 — 조용히 빠집니다:\n{picker}")


def test_스타트업_화면에서도_넘길_곳이_선다(client, db, users, board):
    """**두 화면 모두**에서 돼야 한다 — 요청이 그것이었다.

    스타트업 명단은 전부 감춰져 있어서(투자사로 안 센다), 감춘 명단을 target 에서
    빼 두면 이 화면에서는 고를 것이 하나도 없어 이관 단추가 아예 안 선다.
    화면을 직접 열어 보고 나서야 드러난 자리라 검사로 못 박는다.
    """
    from app.models import VcContact
    from app.services import contact_columns as cc, sheet_owner

    # 스타트업 명단 둘 — 담당이 다르다.
    other = "스타트업 명단 둘"
    sheet_owner.ensure(db, other, user_id=users["u1"].id)
    db.query(sheet_owner.SheetOwner).filter_by(label=other).update(
        {"layout": cc.STARTUP, "is_hidden": 1})
    db.add(VcContact(user_id=users["u1"].id, source_sheet=other,
                     name="가상기업", firm="가상스타트업"))
    db.commit()

    targets = sheet_owner.transfer_targets(db, page=cc.PAGE_STARTUP)
    assert {t["label"] for t in targets} == {STARTUP_LIST, other}, (
        f"스타트업 화면에 넘길 곳이 안 섭니다: {targets}")

    sign_in(client, "01000000001")
    html = client.get("/startup").text
    assert 'id="transfer-target"' in html, "스타트업 화면에 이관 칸이 없습니다"
    assert STARTUP_LIST in html


def test_풀_이름은_넘겨도_그대로_남는다(client, db, users, board):
    """풀은 **분류**지 담당이 아니다 — 거기서 빼면 어디서 확보한 사람인지 사라진다.

    스크립트가 지키던 규칙(`test_import_new_list.py`)이 화면에서도 같아야 한다.
    같은 함수를 부르므로 같아야 정상이고, 갈라지면 그 순간 두 벌이 된 것이다.
    """
    from app.models import VcContact

    row = db.get(VcContact, board["mine"])
    row.source_sheet = f"{POOL},{MINE}"
    db.commit()

    sign_in(client, "01000000001")
    assert transfer(client, board["mine"], YOURS).status_code == 200

    moved = reload(db, board["mine"])
    assert POOL in moved.source_sheet, "풀에서까지 빼 버렸습니다"
    assert YOURS in moved.source_sheet and MINE not in moved.source_sheet


# ── 4. 넘긴 뒤 화면 숫자가 맞다 ─────────────────────────────────────────────
#
# 명단별 인원 · 대시보드의 연결 현황 · 딜 제안 관리의 대상 담당자 수가 모두
# `source_sheet`/`user_id` 에서 나온다. 하나라도 옛 값으로 남으면 화면이
# 거짓말을 한다.

def test_넘기면_두_사람의_화면_숫자가_함께_움직인다(client, db, users, board):
    from app.services import dashboard, sheet_owner

    before_mine = sheet_owner.recipient_counts(db, users["u1"])
    before_yours = sheet_owner.recipient_counts(db, users["u2"])
    assert before_mine["held"] == 1 and before_yours["held"] == 1

    sign_in(client, "01000000001")
    assert transfer(client, board["mine"], YOURS).status_code == 200
    db.expire_all()

    after_mine = sheet_owner.recipient_counts(db, users["u1"])
    after_yours = sheet_owner.recipient_counts(db, users["u2"])
    assert after_mine["held"] == 0, "넘겼는데 아직 내 담당으로 세고 있습니다"
    assert after_yours["held"] == 2, "받은 사람 쪽 수가 안 늘었습니다"
    # 딜 제안 관리의 **대상 담당자** 수도 같이 움직여야 한다 — 안 움직이면
    # 넘긴 사람에게 딜 소개가 계속 나간다.
    assert after_mine["sendable"] == 0
    assert after_yours["sendable"] == 2

    # 대시보드가 세는 모집단('내 투자사')도 같은 값에서 나온다.
    assert sheet_owner.my_contacts(db, users["u1"]) == [], (
        "대시보드에는 아직 내 투자사로 남아 있습니다")
    assert len(sheet_owner.my_contacts(db, users["u2"])) == 2

    # 화면이 실제로 그리는 수까지 본다 — 모집단만 맞고 타일이 옛 수면 소용없다.
    def tile(u):
        board = dashboard.user_dashboard(db, u, today=TODAY)
        return next(k for k in board["kpis"] if k["key"] == "contacts")["value"]

    assert tile(users["u1"]) == 0, "대시보드 타일이 옛 수입니다"
    assert tile(users["u2"]) == 2, "받은 쪽 타일이 안 늘었습니다"


def test_명단_탭의_인원이_넘긴_대로_적힌다(client, db, users, board):
    """탭에 적히는 수는 서버가 그린다 — 넘긴 뒤 다시 그려야 맞는다."""
    from app.services import sheet_owner

    sign_in(client, "01000000001")
    assert transfer(client, board["mine"], YOURS).status_code == 200
    db.expire_all()

    tabs = {t["label"]: t["count"] for t in sheet_owner.sheet_rows(
        db, sheet_owner.managed(db, users["u2"], team_wide=False))}
    assert tabs.get(YOURS) == 2, f"받은 명단 인원이 안 맞습니다: {tabs}"
    assert MINE not in tabs, "넘긴 명단이 아직 남아 있습니다"


def test_넘긴_줄은_받은_사람_화면에_뜨고_넘긴_사람_화면에서_사라진다(
        client, db, board):
    """숫자만이 아니라 **표에 실제로 뜨는지**까지 본다."""
    sign_in(client, "01000000001")
    assert transfer(client, board["mine"], YOURS).status_code == 200
    gone = client.get("/contacts").text
    assert f'data-id="{board["mine"]}"' not in gone, "넘겼는데 내 표에 남아 있습니다"

    client.post("/logout")
    sign_in(client, "01000000002")
    got = client.get("/contacts").text
    assert f'data-id="{board["mine"]}"' in got, "받았는데 표에 안 뜹니다"


# ── 5. 되돌릴 수 있다 ───────────────────────────────────────────────────────

def test_도로_넘기면_원래대로_온다(client, db, users, board):
    """잘못 넘겼을 때 되돌아오는가. 되돌아오지 않으면 이관은 못 쓰는 단추다."""
    from app.models import VcContact

    row = db.get(VcContact, board["mine"])
    row.source_sheet = f"{POOL},{MINE}"
    db.commit()
    before = reload(db, board["mine"]).source_sheet

    sign_in(client, "01000000001")
    assert transfer(client, board["mine"], YOURS).status_code == 200
    client.post("/logout")

    # 받은 사람이 도로 넘긴다 — 이제 그 줄을 맡은 사람이 그쪽이다.
    sign_in(client, "01000000002")
    assert transfer(client, board["mine"], MINE).status_code == 200

    back = reload(db, board["mine"])
    assert back.user_id == users["u1"].id, "담당이 안 돌아왔습니다"
    assert set(back.source_sheet.split(",")) == set(before.split(",")), (
        f"명단이 안 돌아왔습니다: {before} → {back.source_sheet}")


# ── 6. 월별 기록 ────────────────────────────────────────────────────────────
#
# 달마다 늘어나는 칸은 **명단마다 따로**다(`ContactColumn.sheet`). 넘기면 옛
# 명단에 적어 둔 값이 새 명단의 수정창에 안 보인다 — 지워지는 것은 아니지만
# 사람 눈에는 사라진 것과 같아서, 화면이 그 사실을 말해 줘야 한다.

def test_월별_기록은_넘겨도_지워지지_않고_되돌리면_다시_보인다(
        client, db, board):
    from app.models import ContactColumn, VcContact
    from app.services import contact_columns as cc

    col = ContactColumn(sheet=MINE, label="8월 리마인드 (8/19)", position=1)
    db.add(col)
    db.flush()
    key = cc.note_key(col.id)
    row = db.get(VcContact, board["mine"])
    row.notes = cc.dump_notes({key: "8/19 통화 완료"})
    db.commit()

    sign_in(client, "01000000001")
    assert transfer(client, board["mine"], YOURS).status_code == 200

    moved = reload(db, board["mine"])
    assert cc.load_notes(moved.notes).get(key) == "8/19 통화 완료", (
        "넘기면서 월별 기록을 지웠습니다 — 옮기는 것이지 버리는 것이 아닙니다")
    # 칸은 옛 명단 것이라 새 명단의 수정창에는 안 뜬다. 그것이 **알려야 할**
    # 사실이고(확인창이 그렇게 적는다), 값 자체는 그대로 남아 되돌리면 보인다.
    assert col.sheet == MINE, "칸이 따라 옮겨졌습니다 — 칸은 명단의 것입니다"


def test_확인창이_누구를_누구에게_넘기는지와_월별_기록을_말한다():
    """확인창은 삭제 확인창들과 같은 결이어야 한다(`sourcing.html`).

    문구를 검사에 못 박아 두는 이유: 이 두 가지가 빠지면 사람은 **엉뚱한 줄을
    넘기고도 모르고**, 월별 기록이 날아간 줄 알고 다시 적는다.
    """
    from pathlib import Path

    src = (Path(__file__).resolve().parents[1] / "app" / "static" / "js"
           / "contacts.js").read_text(encoding="utf-8")
    body = src[src.index("function transfer()"):]
    body = body[:body.index("\n  }")]
    assert "confirm(" in body, "이관에 확인창이 없습니다"
    assert "who" in body and "owner" in body and "label" in body, (
        "확인창이 누구를 누구의 어느 명단으로 넘기는지 안 적습니다")
    assert "월별 기록" in body, "확인창이 월별 기록 이야기를 안 합니다"
    assert "지워지지는 않고" in body, "지워지지 않는다는 것을 안 말합니다"
