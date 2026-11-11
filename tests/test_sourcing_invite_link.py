"""딜 소싱 화면의 [검토 가능 심사역 참여 안내 (선택 N명)] 단추(11/11 요청).

시리즈 A 탭의 [참여 심사역 딜 발송 요청]과 같은 왼쪽 체크박스로 고르고, 체크한 분 중
**참여 안내를 받는 분**(`sourcing_sync.can_get_invite` — 제안 대기중 · 물어보는 중)만
딜 제안 관리 › 딜 소싱 제안의 [검토 가능 심사역 참여 안내]로 넘긴다. 보내기는 그 화면의
[미리보기] · [보내기] 그대로다 — 이 단추는 열고 골라 둘 뿐이다.

  ① 갈래 탭마다 · 전체 탭에도 선다. 처음에는 잠긴 채(주소 없이), 여는 주소는
     `topic=sourcing_intro`(딜 제안 관리의 그 칩 값)
  ② 줄마다 `data-invite` — 제안 대기중 · 물어보는 중만 `1`
  ③ `참여` 칸을 고치면 서버가 `invite_ok` 를 돌려준다(화면이 그 줄 값을 고친다)
  ④ 그 주소로 연 딜 제안 관리에 그분들 카드가 참여 안내 카드(`data-invite-only="1"`)로
     선다 — 미리 고르기는 `deals.js`(tests/js/deals_sourcing_invite_link_test.js)

단추 글자 · 뺀 수 · `일부 숨김` 은 tests/js/sourcing_invite_link_test.js.
이름 · 번호는 가상값이다(공개 저장소).
"""
from __future__ import annotations

import re
from urllib.parse import quote

from tests.test_sourcing_vc_sync import MNA, SYNC, board, sc  # noqa: F401 - 픽스처를 함께 쓴다

ASKING = "참여 의사를 물어보는 중"
OFFER = "딜 소싱 참여 제안 대기중"
CUSTOM = "11월 재연락"
BTN = re.compile(r'<a [^>]*id="sourcing-invite-btn"[^>]*>([^<]*)</a>')


def _rows(db):
    return {
        "offer": sc(db, name="대기심사", phone="010-2000-0001", kakao_room_name="대기 방",
                    participation=OFFER),
        "asking": sc(db, name="묻는심사", phone="010-2000-0002", kakao_room_name="묻는 방",
                     participation=ASKING),
        "joined": sc(db, name="참여심사", phone="010-2000-0003", kakao_room_name="참여 방"),
        "left": sc(db, name="빠진심사", phone="010-2000-0004", kakao_room_name="빠진 방",
                   participation="불참여"),
        "custom": sc(db, name="메모심사", phone="010-2000-0005", kakao_room_name="메모 방",
                     participation=CUSTOM),
        "mna": sc(db, name="엠앤심사", phone="010-2000-0006", kakao_room_name="엠앤 방",
                  bucket=MNA, participation=OFFER),
    }


def _tr(page, row_id):
    start = page.index(f'<tr data-id="{row_id}"')
    return page[start:page.index(">", start)]


def test_the_button_shows_on_every_tab_locked(board, db):
    _rows(db)
    for url in (f"/sourcing?tab={quote(SYNC)}", f"/sourcing?tab={quote(MNA)}", "/sourcing?tab=all"):
        page = board.get(url).text
        btn = BTN.search(page)
        assert btn, f"{url} 에 [검토 가능 심사역 참여 안내] 단추가 없다"
        assert btn.group(1) == "검토 가능 심사역 참여 안내 (선택 0명)"
        assert 'data-base="/deals?mode=sourcing&amp;topic=sourcing_intro"' in btn.group(0)
        # 처음에는 아무도 안 골랐다 — 잠긴 채, 주소 없이(보이는 줄 전부로 대신하지 않는다).
        assert 'aria-disabled="true"' in btn.group(0) and " href=" not in btn.group(0)
        assert 'data-testid="sourcing-invite-hint"' in page
    # 시리즈 A 단추는 지금처럼 그 갈래에만
    assert 'id="sourcing-share-btn"' in board.get(f"/sourcing?tab={quote(SYNC)}").text
    assert 'id="sourcing-share-btn"' not in board.get(f"/sourcing?tab={quote(MNA)}").text


def test_rows_carry_whether_they_get_the_invite(board, db):
    rows = _rows(db)
    page = board.get(f"/sourcing?tab={quote(SYNC)}").text
    for key, want in (("offer", "1"), ("asking", "1"), ("joined", "0"), ("left", "0"),
                      ("custom", "0")):
        assert f'data-invite="{want}"' in _tr(page, rows[key].id), key
    # 전체 탭에서도 같은 값 — 다른 갈래 줄도
    every = board.get("/sourcing?tab=all").text
    assert 'data-invite="1"' in _tr(every, rows["mna"].id)
    assert 'data-invite="0"' in _tr(every, rows["joined"].id)


def test_editing_participation_returns_invite_ok(board, db):
    rows = _rows(db)
    r = board.patch(f"/api/sourcing/{rows['joined'].id}", json={"participation": "물어보는 중"})
    assert r.status_code == 200, r.text
    assert (r.json()["participation"], r.json()["invite_ok"]) == (ASKING, True)
    r = board.patch(f"/api/sourcing/{rows['joined'].id}", json={"participation": "참여"})
    assert r.json()["invite_ok"] is False
    r = board.patch(f"/api/sourcing/{rows['joined'].id}", json={"participation": CUSTOM})
    assert r.json()["invite_ok"] is False


def test_the_deals_page_has_invite_cards_for_the_link(board, db):
    """단추가 여는 주소로 딜 제안 관리를 열면 넘긴 분들이 참여 안내 카드로 서 있다 —
    `deals.js` 가 `contacts` 로 그 카드를 켠다. 참여 안내 칩이 처음부터 켜져 있다."""
    rows = _rows(db)
    ids = ",".join(str(rows[k].id) for k in ("offer", "asking", "mna"))
    page = board.get(f"/deals?mode=sourcing&topic=sourcing_intro&contacts={ids}").text
    bar = page[page.index('id="sourcing-topic"'):]
    bar = bar[:bar.index("</div>")]
    assert re.search(r'class="chip active" data-value="sourcing_intro">검토 가능 심사역 참여 안내<', bar)
    listing = page[page.index('id="sourcing-list"'):]
    for key in ("offer", "asking", "mna"):
        at = listing.index(f'value="{rows[key].id}"')
        card = listing[listing.rfind("<label", 0, at):]
        assert 'data-invite-only="1"' in card[:card.index("</label>")], key
