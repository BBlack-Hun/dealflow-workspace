"""딜 제안 관리의 **대상 담당자** — 누가 목록에 오르고, 무엇이 걸러지는가.

세 가지가 어긋나면 실제 투자사 카톡방으로 문구가 나간다. 되돌릴 수가 없다.

1. **수가 화면마다 다르다.** 투자사 관리 현황과 딜 제안 관리가 각자 질의를 들고
   있어서 같은 사람을 두고 두 수가 나왔다 — 이 저장소가 반복해 당한 부류다
   (투자사 117명·123명, 좌측 메뉴와 라우터 목록, 컨설턴트 `막힘` 오표시).
   여기서는 **손으로 숫자를 적지 않는다.** 두 화면을 각각 세어 대조한다 —
   기대값을 적어 두면 판정이 갈려도 그 숫자만 고치면 지나간다.
2. **그룹 필터가 조용히 죽는다.** 선언한 값과 줄이 싣는 값과 화면에 보이는 값이
   짝이 아니면 필터는 멀쩡해 보이면서 아무 것도 안 거른다.
3. **[전체선택]·[전체해제]가 안 보이는 사람까지 켜고 끈다.** ← 여기가 제일
   위험하다. 조작 자체는 브라우저에 있으므로 `tests/js/deals_select_all_test.js`
   가 deals.js 를 그대로 실행해 본다. 이 파일은 그 검사가 **헛돌지 않게**
   화면이 같은 아이디·속성을 실제로 그리는지 지킨다.
4. **무엇으로 골랐는지가 요약 줄에서 사라진다.** 여러 그룹에 걸쳐 고르고 나면
   `곽○○ … 외 119명` 만 남아 어느 그룹이 발송에 들었는지 알 수 없었다 —
   `tests/js/deals_group_summary_test.js` 가 그 줄을 본다.

같은 화면(딜 진행 관리)의 것도 여기서 함께 본다 — 미팅 후기의 기업명과 시각,
그리고 예약된 후속의 이름 검색. 앞의 둘은 **없으면 빈칸**이고, 검색은
투자사 관리 현황·딜 소싱과 **같은 방식**(`data-search` + `filters.js`)이다.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from datetime import date, timedelta
from pathlib import Path

import pytest

from .conftest import DEMO_PASSWORD

ROOT = Path(__file__).resolve().parent.parent
JS_TEST = ROOT / "tests" / "js" / "deals_select_all_test.js"
GROUP_SUMMARY_JS_TEST = ROOT / "tests" / "js" / "deals_group_summary_test.js"
SEARCH_JS_TEST = ROOT / "tests" / "js" / "upcoming_search_test.js"
TEMPLATES = ROOT / "app" / "templates"


# ── 시험용 명단 ─────────────────────────────────────────────────────────────
#
# 실제로 갈리는 경우를 전부 넣는다: 연결 단계 **다섯 가지**(`CONNECT_LABELS` 의
# 모든 단계) · 감춘 명단 · 감춘 줄 · 남의 담당 · 그룹 있는 사람과 없는 사람 ·
# 풀에 있으면서 연결도 아직인 사람. 이름은 전부 가상이다(공개 저장소).

MY_SHEET = "가 명단"
HIDDEN_SHEET = "세지 않는 명단"
POOL_SHEET = "확보해 둔 풀"


@pytest.fixture()
def mixed(db, users):
    from app.models import SheetOwner, VcContact

    db.add_all([
        SheetOwner(label=MY_SHEET, user_id=users["u1"].id),
        SheetOwner(label=HIDDEN_SHEET, user_id=users["u1"].id, is_hidden=1),
        # 담당 없는 **투자사 풀**. 여기 사람은 연결이 끝나 있어도 딜 소개
        # 명단에 올린 적이 없다 — 실데이터에서 이런 17명이 발송 목록에 떴다.
        SheetOwner(label=POOL_SHEET, user_id=None),
    ])

    def contact(name, stage, group="", sheet=MY_SHEET, hidden=0, owner="u1"):
        return VcContact(user_id=users[owner].id, name=name, firm="가나벤처스",
                         group_name=group or None, source_sheet=sheet,
                         connect_stage=stage, is_hidden=hidden,
                         kakao_room_name=f"{name} 방", channel_kakao=1)

    rows = [
        contact("가담당", "connected", "1군"),
        contact("나담당", "connected", "1군"),
        contact("다담당", "connected", "2군"),
        contact("라담당", "connected"),            # 그룹을 안 정해 둔 사람
        contact("마담당", "in_progress", "1군"),   # 아직 연결 전
        contact("바담당", "not_started", "2군"),
        contact("사담당", "declined"),
        # 방에 들어왔다가 **나간** 사람. `참여 안 함` 과 뜻이 다르다(다시 부를 수
        # 있는지가 갈린다). 단계가 `연결 완료` 하나로 갈리는 것이 아니라는 것을
        # 검사가 알아야, 단계가 늘 때 화면이 조용히 한 갈래를 빠뜨리지 않는다.
        contact("하담당", "left_room"),
        contact("아담당", "connected", "1군", hidden=1),          # 감춘 줄
        contact("자담당", "connected", "2군", sheet=HIDDEN_SHEET),  # 감춘 명단에만
        contact("차담당", "connected", "1군", owner="u2"),          # 남의 담당
        # ★ 내가 들고 있고 연결도 끝났지만 **딜 소개 명단이 아닌** 사람.
        contact("카담당", "connected", "1군", sheet=POOL_SHEET),
        contact("타담당", "connected", "2군", sheet=POOL_SHEET),
        # ★ 풀에 있으면서 **연결도 아직**인 사람. `이 단계만 보기` 링크가 딜 소개
        # 명단으로 좁혀지지 않으면 이 사람까지 딸려 나온다 — 화면은 `미착수
        # 1명` 이라 적고 눌러 가면 2줄이 뜬다(대시보드가 당한 그 어긋남).
        contact("거담당", "not_started", sheet=POOL_SHEET),
        # 풀에도 있고 내 명단에도 있는 사람 — **명단 쪽이 이긴다.**
        contact("파담당", "connected", "1군", sheet=f"{POOL_SHEET},{MY_SHEET}"),
    ]
    db.add_all(rows)
    db.commit()
    return {r.name: r for r in rows}


# ── 1) 두 화면이 같은 판정을 지난다 ─────────────────────────────────────────

def test_딜_제안_관리의_대상은_투자사_관리_현황이_세는_사람_안에서만_나온다(db, users, mixed):
    """목록에 없는 사람에게 체크가 걸리면 그대로 발송이 나간다.

    **양쪽을 각각 세어 대조한다.** 기대 숫자를 적어 두면, 두 화면이 다시
    갈려도 그 숫자만 고치면 지나가 버린다.
    """
    from app.routers.contacts import contact_rows
    from app.services import sheet_owner

    u1 = users["u1"]
    on_deals = {c.id for c in sheet_owner.recipients(db, u1)}
    on_contacts = {r["id"] for r in contact_rows(db, u1)}

    assert on_deals, "시험용 명단이 비었다 — 검사가 헛돈다"
    assert on_deals <= on_contacts, (
        "투자사 관리 현황이 세지 않는 사람이 발송 대상에 올랐다: "
        f"{sorted(on_deals - on_contacts)}")


def test_두_화면의_차이는_명단과_연결_두_가지뿐이다(db, users, mixed):
    """다른 것이 섞이면 **왜 수가 다른지** 화면이 하는 말이 거짓이 된다.

    화면은 "딜소개 명단 N명 중 연결이 끝난 M명 · 명단 밖 K명" 이라고 적는다.
    그 말이 맞으려면 두 목록의 차이가 정확히 **명단**과 **연결** 둘이어야 한다.
    """
    from app.models import VcContact
    from app.routers.contacts import contact_rows
    from app.services import sheet_owner

    u1 = users["u1"]
    off = sheet_owner.off_deal_labels(db)
    on_deals = {c.id for c in sheet_owner.recipients(db, u1)}
    sendable_on_contacts = {
        r["id"] for r in contact_rows(db, u1)
        if sheet_owner.on_deal_list(db.get(VcContact, r["id"]), off)
        and sheet_owner.can_send_to(db.get(VcContact, r["id"]))
    }
    assert on_deals == sendable_on_contacts


# ── 1-2) ★ 발송 대상의 기준은 `딜소개 명단` 이다 ────────────────────────────
#
# 여기가 이번에 바로잡은 자리다. 예전 기준은 "내가 들고 있는 줄 중 연결이
# 끝난 사람" 이었고, 그래서 **딜 소개 명단에 올린 적 없는 풀 사람**이 목록에
# 떴다(실데이터 142명 중 17명). 발송은 되돌릴 수 없다.

def test_명단_밖_사람은_연결이_끝나_있어도_안_뜬다(logged_in, db, users, mixed):
    """풀에 있는 사람은 딜 소개를 보내기로 한 적이 없다."""
    from app.services import sheet_owner

    names = {c.name for c in sheet_owner.recipients(db, users["u1"])}
    assert "카담당" not in names and "타담당" not in names, (
        "딜소개 명단 밖(투자사 풀) 사람이 발송 대상에 올랐다")
    # 화면에도 없어야 한다 — 목록에 있으면 체크가 걸리고 그대로 나간다.
    html = logged_in.get("/deals").text
    for gone in ("카담당", "타담당"):
        assert f'data-name="{gone}"' not in html, f"{gone} 이 발송 목록에 떠 있다"


def test_풀에도_있는_사람은_명단_쪽이_이긴다(db, users, mixed):
    """한 사람이 풀과 딜소개 명단에 겹쳐 있다(실제로 113명이 그렇다).

    풀에 이름이 있다는 이유로 명단에 올린 사람이 빠지면, 원래 받아야 할
    사람이 회차에서 통째로 빠진다.
    """
    from app.services import sheet_owner

    names = {c.name for c in sheet_owner.recipients(db, users["u1"])}
    assert "파담당" in names


def test_명단_판정은_이름이_아니라_표시로_한다(db, users, mixed):
    """**명단 이름을 코드에 적지 않는다.**

    지금 이름은 `전체 딜소개현황(125명)` 처럼 괄호 안 인원이 붙어 있고 그 수는
    사람이 늘 때마다 바뀐다 — 이름으로 맞추면 조용히 깨진다. 여기서는 이름을
    그대로 둔 채 **표시만 뒤집어** 판정이 따라오는지 본다.
    """
    from app.models import SheetOwner
    from app.services import sheet_owner
    from sqlalchemy import select

    u1 = users["u1"]
    before = {c.name for c in sheet_owner.recipients(db, u1)}
    assert "가담당" in before and "카담당" not in before

    rows = {r.label: r for r in db.execute(select(SheetOwner)).scalars().all()}
    rows[MY_SHEET].is_deal_list = 0      # 이름은 그대로, 표시만 끈다
    rows[POOL_SHEET].is_deal_list = 1
    db.commit()

    after = {c.name for c in sheet_owner.recipients(db, u1)}
    assert "가담당" not in after, "표시를 껐는데 여전히 발송 대상이다"
    assert "카담당" in after, "표시를 켰는데 발송 대상이 되지 않았다"


def test_관리자가_화면에서_켜고_끌_수_있다(logged_in, client, db, users, mixed):
    """표시는 **화면에서 사람이 정한다** — 코드나 DB 를 손대야 하면 값으로 둔
    보람이 없다. 그리고 **관리자만** 바꾼다: 켜고 끄는 순간 그 명단을 맡은
    팀원의 발송 대상이 통째로 바뀌고, 그건 실제 카톡방으로 나가는 일이다.
    """
    from app.models import SheetOwner
    from app.services import sheet_owner
    from sqlalchemy import select

    def names():
        return {c.name for c in sheet_owner.recipients(db, users["u1"])}

    # 팀원은 못 바꾼다.
    assert logged_in.post("/api/contacts/sheets/deal-list",
                          data={"label": POOL_SHEET},
                          follow_redirects=False).status_code == 403
    users["u1"].role = "admin"
    db.commit()

    assert "카담당" not in names()
    logged_in.post("/api/contacts/sheets/deal-list", data={"label": POOL_SHEET},
                   follow_redirects=False)
    db.expire_all()
    assert "카담당" in names(), "켰는데 발송 대상에 안 들어왔다"
    logged_in.post("/api/contacts/sheets/deal-list", data={"label": POOL_SHEET},
                   follow_redirects=False)
    db.expire_all()
    assert "카담당" not in names(), "껐는데 발송 대상에 남아 있다"

    # 감춘 명단은 켤 수 없다 — 투자사에게 보낼 문구가 스타트업에게 나간다.
    resp = logged_in.post("/api/contacts/sheets/deal-list",
                          data={"label": HIDDEN_SHEET}, follow_redirects=False)
    assert resp.status_code == 400
    db.expire_all()
    row = db.execute(select(SheetOwner)
                     .where(SheetOwner.label == HIDDEN_SHEET)).scalars().one()
    assert not sheet_owner.is_deal_list(row)


def test_화면에_지금_상태와_되돌릴_단추가_함께_있다(logged_in, db, users, mixed):
    """감춰 놓고 켜는 자리까지 감추면 DB 를 직접 고쳐야 한다(명단 숨김과 같은 규칙)."""
    users["u1"].role = "admin"
    db.commit()

    html = logged_in.get("/contacts?sheet=" + MY_SHEET).text
    assert "딜소개를 보내는 명단" in html, "지금 상태를 화면이 말하지 않는다"
    assert "딜소개 명단에서 빼기" in html, "되돌릴 단추가 없다"

    pool = logged_in.get("/contacts?sheet=" + POOL_SHEET).text
    assert "딜소개 발송 대상이 아닙니다" in pool
    assert "딜소개 명단으로 표시" in pool, "켜는 단추가 없다"


def test_명단에_있어도_방이_없으면_못_보낸다(db, users, mixed):
    """기준이 `연결됨` 에서 `이 명단` 으로 바뀐 것이지, 연결 조건이 사라진 것이
    아니다. 명단에 있어도 카톡방이 없으면 보낼 길이 없다."""
    from app.services import sheet_owner

    names = {c.name for c in sheet_owner.recipients(db, users["u1"])}
    # 같은 명단인데 연결 단계가 아직인 사람들 — 명단 안이지만 대상은 아니다.
    for waiting in ("마담당", "바담당", "사담당", "하담당"):
        assert waiting not in names, f"{waiting} 은 연결 전인데 발송 대상이다"
    assert {"가담당", "나담당"} <= names


# ── 1-3) ★ 빠진 사람이 **누구인지** 화면이 말한다 ───────────────────────────
#
# 여기가 이번에 채운 자리다. 화면은 "명단 141명 중 122명" 이라고 수는 적었지만,
# 빠진 19명은 목록에 아예 없어서 **누구인지 알 길이 없었다.** 카톡방을 아무리
# 확인해도 그 수는 안 움직인다 — 방 확인(`room_verified`)과 연결 단계
# (`connect_stage`)는 따로 관리되는 값이기 때문이다. 실제로 "방은 확인됐는데
# 왜 대상이 아니냐" 는 물음이 여기서 나왔다.
#
# 그렇다고 목록에 섞어 넣으면 안 된다. 고를 수 있게 되는 순간 **보낼 방도 없는
# 사람에게 문구가 나간다.** 그래서 보이되 못 고르게 한다.

def _blocked_block(html: str) -> str:
    """화면에서 `연결이 안 끝나 빠진 사람` 칸만 잘라 낸다."""
    start = html.find('id="blocked-contacts"')
    assert start != -1, "빠진 사람을 보여 주는 칸이 화면에 없다"
    end = html.find("</details>", start)
    assert end != -1
    return html[start:end]


def test_빠진_사람을_이름까지_화면이_보여준다(logged_in, db, users, mixed):
    """수만 적고 이름을 안 적으면, 누가 빠졌는지 몰라 손을 쓸 수가 없다.

    **기대 숫자를 적지 않는다.** 서비스가 세는 사람과 화면이 세우는 이름을
    맞대 본다 — 숫자를 적어 두면 판정이 갈려도 그 숫자만 고치면 지나간다.
    """
    from app.services import sheet_owner

    html = logged_in.get("/deals").text
    block = _blocked_block(html)

    counts = sheet_owner.recipient_counts(db, users["u1"])
    blocked = [c for c in sheet_owner.deal_list_contacts(db, users["u1"])
               if not sheet_owner.can_send_to(c)]
    assert blocked, "시험용 명단에 연결 전 사람이 없다 — 검사가 헛돈다"
    assert counts["blocked"] == len(blocked)

    # ① 빠진 사람이 **한 명도 빠짐없이** 이름으로 선다. 앞의 몇 명만 세우고
    #    나머지를 접으면, 화면에 안 뜨는 사람이 또 생긴다 — 그게 고치려던 문제다.
    for c in blocked:
        assert c.name in block, (
            f"{c.name} 은 명단에 있는데 발송 대상도 아니고 화면 어디에도 없다")
        # 이름은 장식이 아니라 갈 곳이다 — 눌러서 그 사람 줄을 열 수 있어야 한다.
        assert f"/contacts?contact={c.id}" in block, f"{c.name} 을 열 곳이 없다"

    # ② 접힌 줄만 봐도 몇 명이 **어느 단계에서** 빠졌는지 보인다 — 열지 않아도
    #    무슨 일인지는 알아야 한다.
    summary = block[:block.find("</summary>")]
    assert f"<b>{counts['blocked']}명</b>" in summary
    for s in counts["blocked_by_stage"]:
        assert f"{s['label']} {s['count']}명" in summary, (
            f"접힌 줄이 `{s['label']}` 을 말하지 않는다 — 열어 봐야만 알 수 있다")


def test_빠진_사람은_보이기만_하고_고를_수는_없다(logged_in, db, users, mixed):
    """★ 여기가 제일 위험하다.

    연결이 안 끝난 사람을 고를 수 있게 되면 **보낼 방도 없는 사람에게 문구가
    나간다** — 되돌릴 수가 없다. 막는 것은 두 겹이다.

      ① 화면이 그 자리에 **입력칸을 아예 안 그린다** ← 여기서 본다
      ② deals.js 가 고르는 상자를 `#contact-list` 안으로 좁혀 둔다
         (`tests/js/deals_select_all_test.js` 가 deals.js 를 그대로 돌려 본다)
    """
    from app.services import sheet_owner

    html = logged_in.get("/deals").text
    block = _blocked_block(html)

    assert "<input" not in block, (
        "빠진 사람 줄에 입력칸이 생겼다 — 체크가 걸리면 그대로 발송이 나간다")
    assert "contact-cb" not in block, "발송 대상 체크박스가 빠진 사람 줄에 들어갔다"
    # `data-name` 은 발송이 사람을 집어 가는 표식이다(deals.js). 이 줄에는 없어야 한다.
    assert "data-name=" not in block

    # 고르는 목록은 **정확히 발송 대상만**이다. 빠진 사람이 그 상자 안으로
    # 새어 들어가면 위 검사가 다 통과해도 소용이 없다.
    picker = html[html.find('id="contact-list"'):html.find('id="blocked-contacts"')]
    for c in sheet_owner.deal_list_contacts(db, users["u1"]):
        if not sheet_owner.can_send_to(c):
            assert f'data-name="{c.name}"' not in picker, (
                f"{c.name} 은 연결 전인데 고르는 목록에 들어가 있다")


def test_단계는_다섯이고_뜻이_두_갈래다(db, users, mixed):
    """`연결 완료` 하나만 있는 것이 아니다 — 단계가 늘어도 갈래가 안 새야 한다.

    `방 나감` 은 `참여 안 함` 과 뜻이 다르고(다시 부를 수 있는지가 갈린다),
    둘 다 **기다려도 대상이 되지 않는** 쪽이다. 그 차이를 안 적으면 방만 다시
    확인하면 될 줄 알고 안 움직이는 수를 계속 들여다보게 된다.
    """
    from app.services import sheet_owner
    from app.services.sheet_import import (CONNECT_DONE, CONNECT_LABELS,
                                           CONNECT_OPEN, STAGE_CONNECTED)

    # 단계를 세는 곳이 여기 하나뿐이어야 한다 — 화면이 따로 세면 갈린다.
    assert set(CONNECT_LABELS) == {STAGE_CONNECTED, *CONNECT_OPEN, *CONNECT_DONE}, (
        "단계가 늘었는데 갈래(할 일 · 끝난 줄)에 안 들어갔다")

    rows = sheet_owner.deal_list_contacts(db, users["u1"])
    stages = sheet_owner.blocked_stages(db, rows)

    # `연결 완료` 는 여기 오지 않는다 — 그 사람들이 곧 발송 대상이다.
    assert STAGE_CONNECTED not in {s["key"] for s in stages}
    # 이름을 지어내지 않고 임포트가 정한 것을 그대로 읽는다.
    for s in stages:
        assert s["label"] == CONNECT_LABELS[s["key"]]
        assert s["done"] is (s["key"] in CONNECT_DONE)
        assert s["count"] == len(s["people"])
    # 수와 이름이 한 곳에서 나온다 — 갈라지면 어느 쪽이 맞는지 알 수 없다.
    assert sum(s["count"] for s in stages) == len(
        [c for c in rows if not sheet_owner.can_send_to(c)])
    # 할 일이 먼저다(대시보드가 `CONNECT_OPEN` → `CONNECT_DONE` 순으로 세우는
    # 것과 같은 이유). 끝난 줄이 위에 서면 손댈 곳이 뒤로 밀린다.
    assert [s["done"] for s in stages] == sorted(s["done"] for s in stages)


def test_이_단계만_보기가_화면이_센_바로_그_사람에게_간다(logged_in, db, users, mixed):
    """**세는 곳과 가는 곳의 모집단이 같아야 한다.**

    이 칸이 세는 것은 딜 소개 명단이다. 링크를 `전체` 탭으로 보내면 화면은
    `미착수 4명` 이라고 적어 놓고 눌러 가면 맡은 사람 전체의 미착수 84줄이
    뜬다 — 대시보드가 똑같이 당했던 자리다(패널 0명 → 화면 44줄).

    **수가 아니라 이름을 대조한다.** 수만 맞추면 `4명 중 4명` 이 서로 다른
    4명이어도 지나간다.
    """
    from app.services import sheet_owner

    from .test_dashboard_connect import _rows_left   # 거르는 규칙을 두 벌 적지 않는다

    stages = sheet_owner.recipient_counts(db, users["u1"])["blocked_by_stage"]
    assert stages, "시험용 명단에 연결 전 사람이 없다 — 검사가 헛돈다"
    for s in stages:
        page = logged_in.get(s["href"])
        assert page.status_code == 200, f"[{s['label']}] 링크가 열리지 않는다"
        left = _rows_left(page.text, s["href"].partition("?")[2])
        assert sorted(left) == sorted(p["name"] for p in s["people"]), (
            f"[{s['label']} {s['count']}명] 이 가리키는 곳에는 {sorted(left)} 가 "
            f"남는다 — 화면이 센 사람과 다르다")


def test_모르는_단계가_들어와도_사람이_사라지지_않는다(db, users, mixed):
    """단계가 하나 느는 날, 이름 짝이 없다고 그 사람들만 조용히 빠지면 안 된다 —
    빠진 사람을 보이게 하려고 만든 자리다."""
    from app.models import VcContact
    from app.services import sheet_owner

    row = db.query(VcContact).filter_by(name="바담당").one()
    row.connect_stage = "아직_없는_단계"
    db.commit()

    stages = sheet_owner.blocked_stages(
        db,
        sheet_owner.deal_list_contacts(db, users["u1"]))
    hit = [s for s in stages if s["key"] == "아직_없는_단계"]
    assert hit, "모르는 단계에 걸린 사람이 통째로 사라졌다"
    assert [p["name"] for p in hit[0]["people"]] == ["바담당"]
    # 끝난 줄로 치지 않는다 — 할 일로 남겨 두는 쪽이 안전하다.
    assert hit[0]["done"] is False


def test_화면이_단계_이름을_손으로_적지_않는다(db, users, mixed):
    """같은 말을 두 곳에 적으면 한쪽이 반드시 낡는다.

    투자사 관리 현황의 고르는 칸은 `sheet_import.CONNECT_LABELS` 를 쓴다. 화면이
    `연결 완료` 를 손으로 적어 두면 그 말이 바뀌는 날 두 화면이 서로 다른 말을
    하고, 쓰는 사람은 없는 단계를 찾아 헤맨다.
    """
    from app.services.sheet_import import CONNECT_LABELS

    # 주석은 뺀다 — 왜 그렇게 했는지 적는 자리라 단계 이름이 나올 수 있다.
    body = re.sub(r"\{#.*?#\}", "", (TEMPLATES / "deals.html").read_text("utf-8"),
                  flags=re.S)
    for label in CONNECT_LABELS.values():
        assert label not in body, (
            f"화면이 단계 이름 `{label}` 을 손으로 적어 두었다 — "
            "`recipient_counts` 가 실어 주는 값을 쓰라")


def test_명단_기본값은_담당_지정을_따른다(db, users):
    """표시를 안 해 둔 명단이 **조용히 빠지면** 회차가 통째로 잘못 나간다.

    그래서 `is_deal_list` 가 비어 있으면 할당 여부를 따른다 — 이 앱이 원래
    쓰던 정의 그대로다("내 명단 = 할당받아 내가 딜소개를 보내는 사람들").
    """
    from app.models import SheetOwner
    from app.services import sheet_owner

    assigned = SheetOwner(label="새로 받은 명단", user_id=users["u1"].id)
    pool = SheetOwner(label="새 풀", user_id=None)
    hidden = SheetOwner(label="안 세는 명단", user_id=users["u1"].id, is_hidden=1)
    assert sheet_owner.is_deal_list(assigned) is True
    assert sheet_owner.is_deal_list(pool) is False
    assert sheet_owner.is_deal_list(hidden) is False
    # 설정 줄이 아예 없는 이름(손으로 넣은 담당자)은 뺄 근거가 없다.
    assert sheet_owner.is_deal_list(None) is True


def test_화면에_찍히는_수가_서로_어긋나지_않는다(logged_in, db, users, mixed):
    """서비스가 맞아도 **화면이 딴 수를 적으면** 쓰는 사람에게는 그게 진실이다."""
    from app.routers.contacts import contact_rows
    from app.services import sheet_owner

    deals = logged_in.get("/deals").text
    contacts = logged_in.get("/contacts?sheet=all").text

    # 딜 제안 관리: 목록에 그려진 카드 수 = 발송 대상
    cards = len(re.findall(r'class="pick-card"[^>]*data-group=', deals))
    assert cards == len(sheet_owner.recipients(db, users["u1"]))

    # 딜 제안 관리가 적은 "딜소개 명단 … N명 중 … M명"
    said = re.search(r"딜소개 명단.*?<b>(\d+)</b>명 중\s*"
                     r"카톡방 연결이 끝난 <b>(\d+)</b>명", deals, re.S)
    assert said, "무엇을 기준으로 세는지 화면이 말하지 않는다"
    listed_said, sendable_said = int(said.group(1)), int(said.group(2))
    assert sendable_said == cards
    counts = sheet_owner.recipient_counts(db, users["u1"])
    assert listed_said == counts["managed"]

    # 어느 명단 기준인지 **이름으로** 적어야 기준이 또 어긋났을 때 먼저 보인다.
    assert MY_SHEET in deals

    # **명단 밖 인원을 화면이 말한다.** 줄어든 몫이 안 적히면, 명단을 새로 받아
    # 표시하는 것을 잊었을 때 그 사람들이 조용히 빠진다.
    off = re.search(r"맡고 있는 (\d+)명 중\s*<b>(\d+)</b>명은 <b>딜소개 명단 밖</b>",
                    deals, re.S)
    assert off, "명단 밖 인원을 화면이 말하지 않는다"
    held_said, off_said = int(off.group(1)), int(off.group(2))
    assert held_said - off_said == listed_said

    # 투자사 관리 현황의 `전체` 탭에 적힌 수와 같아야 한다(맡고 있는 사람 전체).
    total = re.search(r'href="/contacts\?sheet=all"[^>]*>\s*전체 <span>(\d+)</span>',
                      contacts)
    assert total, "투자사 관리 현황의 전체 수를 못 찾았다"
    assert int(total.group(1)) == held_said == len(contact_rows(db, users["u1"]))


def test_관리자는_팀_전체를_보지만_보내는_것은_본인_담당분뿐이고_화면이_그렇게_말한다(
        client, db, users, mixed):
    """수가 다른 것 자체보다 **왜 다른지 화면이 말하지 않는 것**이 문제였다."""
    from app.models import User
    from app.services import auth as auth_svc

    admin = User(id=9, name="관리자", phone="01099998888", role="admin",
                 password_hash=auth_svc.hash_password(DEMO_PASSWORD))
    db.add(admin)
    db.commit()
    client.post("/login", data={"phone": "01099998888", "password": DEMO_PASSWORD})

    deals = client.get("/deals").text
    assert "발송 대상은 본인 담당분뿐입니다" in deals, (
        "관리자 화면에 팀 전체가 뜨는데 발송 목록만 조용히 비어 있다 — "
        "설정이 덜 된 것처럼 읽힌다")


# ── 2) 그룹 필터 ────────────────────────────────────────────────────────────

def test_그룹_필터가_실제로_줄을_거른다(logged_in, db, users, mixed):
    """선언(칩) · 줄이 싣는 값(`data-group`) · 화면에 보이는 값이 짝이어야 한다.

    셋 중 하나만 어긋나도 화면은 멀쩡해 보이는데 필터만 아무 말 없이 거짓말을
    한다(표 쪽에서는 `tests/test_filter_columns.py` 가 같은 짝을 지킨다).
    """
    from app.services import sheet_owner

    html = logged_in.get("/deals").text
    people = sheet_owner.recipients(db, users["u1"])

    # 줄이 값을 싣는다 — 대상 한 사람마다 정확히 한 줄.
    carried = re.findall(r'class="pick-card" data-group="([^"]*)"', html)
    assert sorted(carried) == sorted(sheet_owner.group_of(c) for c in people)

    # 칩이 그 값을 선언한다 — 값마다 하나씩, 인원까지.
    bar = re.search(r'<div class="filter-line" id="group-filter"(.*?)</div>',
                    html, re.S)
    assert bar, "그룹 필터 줄이 없다"
    declared = {value: int(count) for value, _label, count in
                re.findall(r'data-value="([^"]*)">\s*([^<]*?)\s*<b>(\d+)</b>',
                           bar.group(1))}
    counted = {(g["name"] or g["label"]): g["count"]
               for g in sheet_owner.group_rows(people)}
    assert declared.pop("", None) == len(people), "[전체] 칩의 인원이 대상 수와 다르다"
    assert declared == counted, (
        "필터가 선언한 그룹·인원이 실제 대상과 다르다 — 골라도 엉뚱한 사람이 남는다")

    # 화면에 **보이는** 값이 있어야 한다. 칸이 없는데 필터만 걸면 무엇으로
    # 걸러졌는지 확인할 수가 없다.
    for c in people:
        if sheet_owner.group_of(c):
            assert f'<span class="tag soft">그룹 {c.group_name}</span>' in html


def test_그룹을_안_정해_둔_사람은_투자사_관리_현황과_같은_말로_묶인다():
    """`(비어 있음)` 이라는 말이 두 화면에서 달라지면 같은 조건인지 알 수 없다.

    표 필터(`filters.js`)가 그 말의 주인이다 — 서버는 그 글자를 그대로 실어
    보낸다(`sheet_owner.EMPTY_GROUP`). 한쪽만 고쳐지는 날이 오면 여기서 걸린다.
    """
    from app.services import sheet_owner

    js = (ROOT / "app" / "static" / "js" / "filters.js").read_text(encoding="utf-8")
    said = re.search(r'var EMPTY = "([^"]+)";', js)
    assert said, "filters.js 에서 EMPTY 를 못 찾았다"
    assert sheet_owner.EMPTY_GROUP == said.group(1)


def test_두_화면이_같은_사람에게_같은_그룹_값을_싣는다(logged_in, db, users, mixed):
    """딜 제안 관리에서 `1군` 으로 고른 사람과 투자사 관리 현황에서 고른 사람이
    달라지면, 어느 쪽을 믿을지 알 수 없다."""
    deals = logged_in.get("/deals").text
    contacts = logged_in.get("/contacts?sheet=all").text

    for name, row in mixed.items():
        if row.user_id != users["u1"].id or row.is_hidden:
            continue
        if row.connect_stage != "connected":
            continue
        on_deals = re.search(
            r'data-group="([^"]*)"[^>]*>\s*<input[^>]*data-name="' + name + '"',
            deals, re.S)
        if on_deals is None:      # 감춘 명단에만 있는 사람은 아예 안 뜬다
            continue
        on_contacts = re.search(
            r'data-name="' + name + r'"[^>]*\n?\s*data-f-group="([^"]*)"', contacts)
        assert on_contacts, f"{name} 이 투자사 관리 현황에 없다"
        assert on_deals.group(1) == on_contacts.group(1)


# ── 3) ★ [전체선택]·[전체해제]가 훑는 범위 ──────────────────────────────────

def test_화면이_전체선택_검사가_기대하는_모양을_실제로_그린다(logged_in, mixed):
    """브라우저 검사는 가짜 DOM 위에서 돈다 — **그 모양이 화면과 어긋나면 헛돈다.**

    아이디나 속성 이름을 하나 바꾼 순간, 브라우저 검사는 여전히 통과하는데
    실제 화면에서는 필터도 전체선택도 안 걸리는 상태가 된다. 그 짝을 여기서 건다.
    """
    html = logged_in.get("/deals").text
    for needed in ('id="select-all-contacts"', 'id="clear-all-contacts"',
                   'id="contact-list"',
                   'id="group-filter"', 'id="contact-filters"',
                   'class="contact-cb"', 'class="pick-card" data-group=',
                   'id="contact-filter-note"', 'id="contact-summary"',
                   'id="bucket-mix-note"', 'data-empty='):
        assert needed in html, f"화면에 {needed} 가 없다 — 브라우저 검사가 헛돈다"


def test_전체선택_옆에_전체해제가_있다(logged_in, mixed):
    """단추가 하나뿐이라 **푸는 길이 없었다.**

    [전체선택]은 지금 걸러진 범위만 되돌린다 — 그 좁힘이 이 화면의 안전장치라
    넓힐 수 없다(그룹으로 추려 놓고 누른 조작이 다른 그룹을 건드리면 그대로
    남의 카톡방으로 문구가 나간다). 그래서 조건 밖에서 고른 사람에게는 손이
    닿지 않았고, 필터를 되돌리거나 새로고침하는 수밖에 없었다.

    범위가 다른 일이라 단추도 따로 세운다. 여기서는 **그 단추가 화면에 있고,
    풀 것이 없을 때는 잠겨 있는지**만 본다 — 무엇을 푸는지는 브라우저 쪽
    검사가 deals.js 를 그대로 돌려 본다.
    """
    html = logged_in.get("/deals").text
    at = html.find('id="clear-all-contacts"')
    assert at > 0, "[전체해제] 단추가 화면에 없다"
    assert "disabled" in html[at:at + 220], (
        "아무도 안 골랐는데 [전체해제]가 눌린다 — 눌러도 아무 일이 없는 단추다")
    # 찾던 자리에 있어야 한다. [전체선택] 옆이 아니면 없는 것과 같다.
    assert 0 < html.find('id="select-all-contacts"') < at, (
        "[전체해제]가 [전체선택] 옆에 없다 — 없다고 한 그 자리에 세워야 한다")


def test_전체선택은_안_보이는_사람에게_걸리면_안_된다():
    """규칙을 옮겨 적으면 두 벌이 되어 어긋나도 모른다 — deals.js 를 그대로 돌린다.

    가장 위험한 자리다. 그룹으로 추려 놓고 [전체선택]을 눌렀는데 다른 그룹까지
    켜지면, 그대로 **실제 투자사 방으로 문구가 나간다.**

    함정은 **이미 고른 사람**이다. 이 화면은 고른 사람을 조건 밖에서도 계속
    보여 준다(몇 명 골랐는지 알아야 하므로) — `보인다 = 조건에 맞다` 로 읽으면
    아까 고른 사람들이 딸려 온다.
    """
    node = shutil.which("node")
    if node is None:
        pytest.skip("node 미설치 — 브라우저 로직 테스트 생략 "
                    "(호스트에서 `node tests/js/deals_select_all_test.js`)")
    result = subprocess.run([node, str(JS_TEST)], capture_output=True,
                            text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr


def test_고른_그룹_이름이_요약_줄에서_사라지면_안_된다():
    """여러 그룹에 걸쳐 고르고 나면 **무엇으로 골랐는지가 화면에서 사라졌다.**

    그룹 칩은 한 번에 하나만 켜지는데 고르기는 그 위에 쌓인다 — 1군을 고르고
    2군으로 옮겨 [전체선택]을 누르면 발송 대상에 두 그룹이 함께 있는데, 요약
    줄은 `곽○○ … 외 119명` 이라고만 적었다. 칩은 지금 걸린 조건 하나만 말하지
    이미 담아 둔 것을 말해 주지 않는다.

    그룹 이름은 **하나도 줄이지 않는다** — 이름은 여럿 중 하나지만 그룹은
    `무엇으로 골랐는가` 라서, 하나가 가려지면 그 그룹이 통째로 발송에 들어간
    사실이 안 보인다.
    """
    node = shutil.which("node")
    if node is None:
        pytest.skip("node 미설치 — 브라우저 로직 테스트 생략 "
                    "(호스트에서 `node tests/js/deals_group_summary_test.js`)")
    result = subprocess.run([node, str(GROUP_SUMMARY_JS_TEST)],
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr


# ── 4) 미팅 후기에 기업명 ───────────────────────────────────────────────────

@pytest.fixture()
def meetings(db, users):
    """끝난 미팅 둘 — 기업을 적어 둔 것과 안 적어 둔 것."""
    from app.models import Meeting, VcContact

    contact = VcContact(user_id=users["u1"].id, name="홍길동", title="심사역",
                        firm="가나벤처스", connect_stage="connected")
    db.add(contact)
    db.flush()
    done = date.today() - timedelta(days=20)
    rows = [
        Meeting(user_id=users["u1"].id, contact_id=contact.id,
                company_name="샘플애그", scheduled_at=done.isoformat(),
                scheduled_time="14:30", status="done", done_at=done.isoformat(),
                followup_due=(done + timedelta(days=10)).isoformat()),
        # 기업도 시각도 안 적어 둔 미팅. **비어 있는 것이 정확하다.**
        Meeting(user_id=users["u1"].id, contact_id=contact.id,
                scheduled_at=done.isoformat(), status="done",
                done_at=done.isoformat()),
    ]
    db.add_all(rows)
    db.commit()
    return {"contact": contact, "with_company": rows[0], "bare": rows[1]}


def test_미팅_후기에_어느_기업_미팅이었는지_나온다(logged_in, meetings):
    """결과만 적혀 있고 무엇에 대한 미팅인지 없으면, 다음 회차에 이 투자사를
    어떻게 대할지 정할 근거가 안 된다."""
    html = logged_in.get("/ir").text
    review = html.split('id="reviews"', 1)
    assert len(review) == 2, "미팅 후기 구역이 없다"
    assert "<th style=\"width:120px\">기업</th>" in review[1], \
        "미팅 후기 표에 기업 칸이 없다"
    assert "샘플애그" in review[1]


def test_기업을_안_적어_둔_미팅에는_기업명을_지어내지_않는다(logged_in, db, meetings):
    """담당자가 맡은 기업이나 지난 회차에서 골라 채우면 그럴듯하지만, 후기를
    읽는 사람은 그것을 "이 미팅은 그 기업 건" 으로 읽는다. 모르면 빈칸이다."""
    from app.services import pipeline
    from app.models import User

    rows = {m["id"]: m for m in
            pipeline.meeting_rows(db, db.get(User, 1))}
    assert rows[meetings["bare"].id]["company_name"] == ""

    html = logged_in.get("/ir").text
    # 빈 미팅 줄에 아무 기업 이름도 새로 생기지 않는다.
    assert html.count("샘플애그") >= 1
    assert '<td class="ellipsis" title="">' in html, \
        "기업을 안 적어 둔 미팅 줄이 빈칸이 아니다"


# ── 5) 미팅 시각 ────────────────────────────────────────────────────────────
#
# **날짜 칸에 붙이지 않는다.** `scheduled_at` 을 날짜 문자열로 견주는 곳이
# 여럿이라(업무 보고의 월간 집계 · 오늘 미팅), `T14:00` 이 붙으면 그 달
# 마지막 날의 미팅이 통째로 빠지고 오늘 미팅이 하나도 안 잡힌다.

def test_시각을_적으면_저장되고_되읽힌다(logged_in, db, users, meetings):
    from app.models import Meeting
    from sqlalchemy import select

    resp = logged_in.post("/ir/meetings", data={
        "contact_id": meetings["contact"].id,
        "scheduled_at": date.today().isoformat(),
        "scheduled_time": "09:05",
        "kind": "first", "company_name": "샘플애그",
    }, follow_redirects=False)
    assert resp.status_code == 303
    db.expire_all()
    row = db.execute(select(Meeting).where(Meeting.scheduled_time == "09:05")
                     ).scalars().first()
    assert row is not None, "시각이 저장되지 않았다"
    assert "09:05" in logged_in.get("/ir").text


def test_시각을_안_적어도_미팅을_잡을_수_있다(logged_in, db, meetings):
    """날짜만 아는 단계가 실제로 있다 — 필수로 만들면 그 단계를 기록할 수 없다."""
    from app.models import Meeting
    from sqlalchemy import select

    before = len(db.execute(select(Meeting)).scalars().all())
    logged_in.post("/ir/meetings", data={
        "contact_id": meetings["contact"].id,
        "scheduled_at": date.today().isoformat(),
        "scheduled_time": "", "kind": "first",
    }, follow_redirects=False)
    db.expire_all()
    rows = db.execute(select(Meeting)).scalars().all()
    assert len(rows) == before + 1
    assert rows[-1].scheduled_time is None, "안 적은 시각을 지어냈다"


def test_읽을_수_없는_시각은_지어내지_않고_버린다():
    from app.services import pipeline

    assert pipeline.clean_time("14:30") == "14:30"
    assert pipeline.clean_time("14:30:00") == "14:30"    # 브라우저가 초까지 보낼 때
    assert pipeline.clean_time("") is None
    assert pipeline.clean_time("오후 두시") is None       # 00:00 으로 채우지 않는다
    assert pipeline.clean_time("25:00") is None


def test_시각이_없는_기존_미팅도_그대로_보인다(logged_in, db, meetings):
    """이미 들어 있는 기록은 시각을 모른다. 그 줄이 깨지거나 자정으로 채워지면 안 된다."""
    from app.services import pipeline
    from app.models import User

    rows = {m["id"]: m for m in pipeline.meeting_rows(db, db.get(User, 1))}
    bare = rows[meetings["bare"].id]
    assert bare["scheduled_time"] == ""
    assert bare["when_label"] == meetings["bare"].scheduled_at
    assert logged_in.get("/ir").status_code == 200


def test_시각이_붙어도_월간_집계가_같은_달로_잡힌다(db, users, meetings):
    """업무 보고는 `scheduled_at` 을 **날짜 문자열로** 견준다
    (`scheduled_at <= 월말`). 시각이 그 칸에 붙으면 그 달 마지막 날의 미팅이
    통째로 빠진다 — 그래서 칸을 나눴다. 그 결정이 지켜지는지 본다."""
    from app.models import Meeting
    from app.services import report
    from sqlalchemy import select

    last_day = date(2026, 8, 31)
    db.add(Meeting(user_id=users["u1"].id,
                   contact_id=meetings["contact"].id,
                   company_name="샘플애그", scheduled_at=last_day.isoformat(),
                   scheduled_time="23:59", status="done",
                   done_at=last_day.isoformat()))
    db.commit()

    # 날짜 칸에는 시각이 섞여 있으면 안 된다.
    for row in db.execute(select(Meeting)).scalars().all():
        assert len(row.scheduled_at) == 10, \
            f"날짜 칸에 시각이 섞였다: {row.scheduled_at!r}"

    # 집계가 세는 수 == 그 달에 실제로 있는 미팅 수. 날짜 칸에 `T23:59` 가
    # 붙는 순간 `'2026-08-31T23:59' <= '2026-08-31'` 이 거짓이 되어 이 줄이
    # 통째로 빠진다 — 그때 여기서 걸린다.
    have = [m for m in db.execute(select(Meeting)).scalars().all()
            if m.user_id == users["u1"].id and (m.scheduled_at or "")[:7] == "2026-08"]
    assert have, "시험용 미팅이 그 달에 없다 — 검사가 헛돈다"
    data = report.monthly(db, 2026, 8, user=users["u1"])
    assert data["total"] == len(have), \
        "그 달 마지막 날의 미팅이 월간 집계에서 빠졌다"


def test_후속_챙김_날짜는_시각을_안_탄다():
    """미팅 며칠 뒤 결과를 묻는 것은 **날짜 단위 일**이다 — 오후 미팅만 하루
    밀리는 식으로 갈리면 안 된다."""
    from app.services import pipeline

    day = date(2026, 8, 24)
    assert pipeline.followup_date(day) == pipeline.followup_date(day)
    # 시각은 인자에 들어가지도 않는다 — 날짜 하나만 받는다.
    import inspect
    assert list(inspect.signature(pipeline.followup_date).parameters) == ["done_on"]


def test_미팅_시각_마이그레이션은_두_번_돌려도_죽지_않는다():
    """스탬프가 어긋난 DB 로 컨테이너가 뜨면 `duplicate column name` 으로 죽고,
    다시 뜨고, 또 죽는 크래시 루프가 된다 — 실데이터가 든 DB 라 손댈 수도 없다."""
    import sqlalchemy as sa

    path = ROOT / "alembic" / "versions" / "0038_meeting_time.py"
    src = path.read_text(encoding="utf-8")
    assert "_has_column" in src and "if not _has_column" in src, \
        "있으면 건너뛰는 자리가 없다 — 두 번째 실행에서 죽는다"

    # 실제로 두 번 돌려 본다(임시 DB).
    engine = sa.create_engine("sqlite://")
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "CREATE TABLE meetings (id INTEGER PRIMARY KEY, scheduled_at TEXT)")

    import types
    from alembic.operations import Operations
    from alembic.runtime.migration import MigrationContext

    mod = types.ModuleType("m0038")
    exec(compile(src, str(path), "exec"), mod.__dict__)
    with engine.connect() as conn:
        # 마이그레이션 안의 `op` 는 모듈 전역에서 찾는다 — 이 연결에 묶인
        # 것으로 갈아 끼우면 진짜 파일이 그대로 돈다.
        mod.op = Operations(MigrationContext.configure(conn))
        mod.upgrade()
        mod.upgrade()      # ← 두 번째. 여기서 죽으면 크래시 루프다.
        cols = {c["name"] for c in sa.inspect(conn).get_columns("meetings")}
    assert "scheduled_time" in cols


# ── 6) 예약된 후속에서 이름 검색 ────────────────────────────────────────────

def test_예약된_후속_패널은_두_화면이_같은_파일을_쓴다():
    """한 벌씩 들고 있으면 한쪽에만 검색칸이 달린다.

    이 저장소가 반복해 당한 부류다 — 좌측 메뉴 목록과 라우터 목록이 갈려
    컨설턴트에게 다 열려 있던 일, 투자사 수가 화면마다 달랐던 일.
    """
    shared = TEMPLATES / "_upcoming_followups.html"
    assert shared.exists(), "예약된 후속 패널을 함께 쓰는 파일이 없다"
    for name in ("ir.html", "followups.html"):
        page = (TEMPLATES / name).read_text(encoding="utf-8")
        assert '{% include "_upcoming_followups.html" %}' in page, (
            f"{name} 이 예약된 후속을 따로 그리고 있다 — 한쪽만 고쳐진다")
        assert "예약된 후속 <span" not in page, (
            f"{name} 에 옛 패널이 남아 있다 — 두 벌이 된다")


def test_검색칸이_이_앱의_방식_그대로다():
    """툴바 안에 두어야 크기가 `--ctl-h` 한 값에서 나온다. 줄은 `data-search` 를
    싣고, 거는 것은 공용 필터(`filters.js`)다 — 새로 만들지 않는다."""
    shared = (TEMPLATES / "_upcoming_followups.html").read_text(encoding="utf-8")
    toolbar = re.search(r'<div class="toolbar">(.*?)</div>\s*</div>', shared, re.S)
    assert toolbar and 'type="search"' in toolbar.group(1), \
        "검색칸이 툴바 밖에 있다 — 이 줄만 브라우저 기본 입력칸으로 따로 논다"
    assert 'data-search=' in shared, "줄이 검색할 값을 싣지 않는다"
    assert "DealflowFilters" in shared, "공용 필터를 안 쓰고 새로 만들었다"


def test_두_화면_모두에서_검색칸이_그려진다(logged_in, db, users):
    """`/followups` 는 지금 `/ir#remind` 로 보내는 옛 주소다 — 따라가서 본다."""
    from app.models import DealBatch, SendSequence, VcContact

    contact = VcContact(user_id=users["u1"].id, name="가담당", firm="가나벤처스",
                        connect_stage="connected")
    batch = DealBatch(user_id=users["u1"].id, title="시험 회차")
    db.add_all([contact, batch])
    db.flush()
    db.add(SendSequence(user_id=users["u1"].id, contact_id=contact.id,
                        batch_id=batch.id, stage=1, next_stage=2,
                        next_due_date=(date.today() + timedelta(days=5)).isoformat(),
                        status="active"))
    db.commit()

    for url in ("/ir", "/followups"):
        html = logged_in.get(url, follow_redirects=True).text
        assert 'id="upcoming-search"' in html, f"{url} 에 검색칸이 없다"
        assert 'id="upcoming-table"' in html
        # 줄이 이름·회사·다음 단계를 싣는다 — 화면에 보이는 것만.
        row = re.search(r'<tr class="data-row"\s*\n?\s*data-search="([^"]*)"', html)
        assert row, f"{url} 의 줄이 검색할 값을 안 싣는다"
        assert "가담당" in row.group(1) and "가나벤처스" in row.group(1)


def test_친_글자로_실제로_줄이_걸러진다():
    """규칙을 옮겨 적으면 두 벌이 된다 — `filters.js` 와 화면이 거는 자리를
    **그대로 실행**해 본다. 검색어를 지웠을 때 줄이 돌아오는지도 함께 본다
    (검색과 다른 조건이 번갈아 `tr.hidden` 을 덮어쓴 적이 있다)."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("node 미설치 — 브라우저 로직 테스트 생략 "
                    "(호스트에서 `node tests/js/upcoming_search_test.js`)")
    result = subprocess.run([node, str(SEARCH_JS_TEST)], capture_output=True,
                            text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
