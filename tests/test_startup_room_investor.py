"""스타트업 대표 카톡방 후보에 **투자사 방이 섞이지 않는가** (0.11.3).

## 실제로 난 일

회사명이 두 글자인 기업을 검색하자 카톡 맨 위에 **투자사 방**이 떴다 —
`<두 글자>인베스트먼트 <이름> 이사님 <다른 투자사> Asset deal 공유` 꼴이다.
회사명이 그 제목 안에 글자로 들어 있어 Windows 발송기의 맨 위 방 열기
(0.11.2)가 그것을 후보로 올렸고, 서버도 그대로 담았다. 사람이 그것을 누르면
그 기업의 월간 IR 메일이 **투자사 방으로 간다.**

## 이 파일이 지키는 것

    ① 서버가 담을 때 투자사 방을 뺀다 — 담당자 명단의 방 이름 · 투자사 이름 ·
       표식(인베스트먼트·벤처스 …). **발송기 판과 상관없이** 막는다
    ② 이미 담겨 있는 투자사 방도 맞추기 화면에 서지 않는다(데이터는 그대로)
    ③ 대표와의 방(`<대표>대표님<회사명> , <팀원>`)은 남는다. 회사명 자체에
       표식이 든 기업(`…파트너스`)의 방도 남는다
    ④ 서버와 발송기의 표식 목록이 **같다**
    ⑤ 발송기는 기업 줄의 맨 위 방 열기에서 투자사 방을 버린다 — 담당자 쪽
       확인에서는 안 버린다(찾는 방이 곧 투자사 방이다)
    ⑥ Windows 검색칸을 **비우고** 붙인다 — 카톡이 직전 검색어를 남겨 두어
       회사명이 이어 붙었다(실기)

이름·회사명은 **전부 지어낸 값**이다 — 저장소가 공개다.
"""
from __future__ import annotations

import pytest

from agent.sender import kakao_windows as kw
from tests.test_startup_room_match import (_jobs, _login, _report, _rows,
                                           _search, _turn_on)
from tests.test_win_discover_rooms import FakeAgentClient, FakeKakao, FakeWin, NO_WAIT
from tests.test_win_room_open_top import CHAT, PID, OpenWin

SHORT = "(주)가나"                     # 두 글자 회사
SHORT_QUERY = "가나"
INVESTOR_ROOM = "가나인베스트먼트 홍길동 이사님 다라마브이씨 Asset deal 공유"
STARTUP_ROOM = "김철수대표님가나 , 이영희 매니저"
PARTNERS = "바사파트너스"                 # 회사명에 표식이 든 스타트업
PARTNERS_ROOM = "박민수 대표 바사파트너스 , 이영희 매니저"


@pytest.fixture()
def short(db, users):
    from app.models import IrCompany

    company = IrCompany(name=SHORT, contract_status="paid", contact_name="김철수")
    partners = IrCompany(name=PARTNERS, contract_status="paid")
    db.add_all([company, partners])
    db.commit()
    return {"short": company, "partners": partners}


def _item_of(db, company_id):
    job = _jobs(db)[-1]
    return next(i for i in job.items if i.ir_company_id == company_id)


# ── ① 담을 때 뺀다 ─────────────────────────────────────────────────────────

def test_투자사_표식이_든_방은_후보로_담지_않는다(db, short, client):
    from app.services import room_match

    _turn_on(db)
    me = _login(client)
    _search(me)
    item = _item_of(db, short["short"].id)

    _report(me, item.id, verdict="ambiguous",
            candidates=[INVESTOR_ROOM, STARTUP_ROOM])
    db.expire_all()

    found = room_match.candidates(short["short"])
    assert found["rooms"] == [STARTUP_ROOM]
    assert found["dropped"] == 1


def test_하나뿐인_결과가_투자사_방이면_확인됨이_아니다(db, short, client):
    """발송기가 맨 위 방 하나를 `verified` 로 올려도, 그것이 투자사 방이면
    찾은 것이 없는 것과 같다 — 실패 목록에 사유와 함께 남는다."""
    from app.services import room_match

    _turn_on(db)
    me = _login(client)
    _search(me)
    item = _item_of(db, short["short"].id)

    _report(me, item.id, verdict="verified", found_room=INVESTOR_ROOM,
            candidates=[INVESTOR_ROOM])
    db.expire_all()

    assert room_match.candidates(short["short"])["rooms"] == []
    assert item.status == "failed"
    assert "투자사 방" in (item.error or "")
    assert short["short"].kakao_room_name is None


def test_담당자_명단에_있는_방_이름과_투자사_이름으로도_뺀다(db, short):
    from app.models import VcContact
    from app.services import room_match

    db.add_all([
        VcContact(user_id=1, name="홍길동", firm="다라마브이씨",
                  kakao_room_name="홍길동 이사 아무개 공유방"),
        VcContact(user_id=1, name="고길동", firm="가나"),   # 두 글자 투자사 — 안 쓴다
    ])
    db.commit()
    known = room_match.investor_rooms(db)

    kept, dropped = room_match.drop_investor_rooms(
        ["홍길동  이사 아무개 공유방",            # 명단의 방 이름(공백만 다르다)
         "가나 다라마브이씨 미팅방",               # 아는 투자사 이름
         STARTUP_ROOM],
        SHORT, known)
    assert kept == [STARTUP_ROOM], "두 글자 투자사 이름으로 대표 방까지 빼면 안 된다"
    assert len(dropped) == 2


def test_회사명에_든_글자로는_빼지_않는다(db, short):
    """회사 이름이 `바사파트너스` 면 그 회사의 진짜 방에도 `파트너스` 가 든다.
    투자사 이름이 회사명 안에 들어 있을 때도 같다."""
    from app.models import VcContact
    from app.services import room_match

    db.add(VcContact(user_id=1, name="홍길동", firm="바사파트너스"))
    db.commit()
    known = room_match.investor_rooms(db)
    assert room_match.investor_reason(PARTNERS_ROOM, PARTNERS, known) == ""
    # 다른 표식은 그대로 본다.
    assert room_match.investor_reason(
        "바사파트너스 홍길동 이사님 Asset deal 공유", PARTNERS, known)


def test_폴링이_기업_줄에_표시를_붙인다(db, short, client):
    """발송기가 기업 줄인지 알아야 맨 위 방 열기에서 투자사 방을 버린다."""
    from tests.test_startup_room_match import AGENT_KINDS
    from tests.conftest import DEMO_TOKEN

    _turn_on(db)
    me = _login(client)
    _search(me)
    got = me.get("/api/agent/poll", params={"kinds": AGENT_KINDS},
                 headers={"Authorization": f"Bearer {DEMO_TOKEN}"}).json()
    targets = {i.get("target") for i in got["items"]}
    assert targets == {"company"}


# ── ② 이미 담긴 것도 화면에 안 선다 ─────────────────────────────────────────

def test_이미_담긴_투자사_방은_화면에서_감춘다(db, short, client):
    """운영에 0.11.2 때 담긴 투자사 방이 남아 있다 — 데이터를 고치지 않고
    화면에서 감춘다. 감췄다는 것은 적는다."""
    from app.services import room_match
    from app.deps import now_iso

    room_match.save_candidates(short["short"], [INVESTOR_ROOM, STARTUP_ROOM],
                               at=now_iso(), query=SHORT_QUERY)
    db.commit()
    _turn_on(db)
    me = _login(client)
    body = _rows(me).text

    assert STARTUP_ROOM in body
    assert INVESTOR_ROOM not in body
    assert "투자사 방 1개는 후보에서 뺐습니다" in body

    row = next(r for r in room_match.rows(db)["rows"]
               if r["company"].id == short["short"].id)
    assert [c["room"] for c in row["candidates"]] == [STARTUP_ROOM]


# ── ④ 두 벌이 같다 ─────────────────────────────────────────────────────────

def test_서버와_발송기의_투자사_표식이_같다():
    from app.services import room_match

    assert tuple(room_match.INVESTOR_ROOM_MARKERS) == tuple(kw.INVESTOR_ROOM_MARKERS)


# ── ⑤ 발송기의 맨 위 방 열기 ───────────────────────────────────────────────

def _unreadable_short():
    return FakeKakao({SHORT_QUERY: [INVESTOR_ROOM]}, no_list=True)


def test_기업_줄이면_맨_위_투자사_방을_버린다():
    sender = OpenWin(_unreadable_short(), opens={CHAT: (INVESTOR_ROOM, PID)})
    assert sender.discover_rooms(SHORT_QUERY, company=True) == []


def test_담당자_줄이면_맨_위_방을_그대로_올린다():
    sender = OpenWin(_unreadable_short(), opens={CHAT: (INVESTOR_ROOM, PID)})
    assert sender.discover_rooms(SHORT_QUERY) == [INVESTOR_ROOM]


def test_기업_줄의_대표_방은_그대로_올린다():
    kakao = FakeKakao({SHORT_QUERY: [STARTUP_ROOM]}, no_list=True)
    sender = OpenWin(kakao, opens={CHAT: (STARTUP_ROOM, PID)})
    assert sender.discover_rooms(SHORT_QUERY, company=True) == [STARTUP_ROOM]


def test_잡의_기업_표시가_발송기까지_간다():
    import agent.main as agent_main

    sender = OpenWin(_unreadable_short(), opens={CHAT: (INVESTOR_ROOM, PID)})
    client = FakeAgentClient()
    job = {"job_id": 9, "kind": "verify_room",
           "items": [{"id": 1, "room_name": "", "query": SHORT_QUERY,
                      "name": SHORT_QUERY, "target": "company"}]}
    agent_main.process_verify_job(client, sender, job, dict(NO_WAIT))
    assert client.items[0]["candidates"] is None
    assert client.items[0]["status"] == "failed"


def test_looks_like_investor_room():
    assert kw.looks_like_investor_room(INVESTOR_ROOM, SHORT_QUERY)
    assert not kw.looks_like_investor_room(STARTUP_ROOM, SHORT_QUERY)
    assert not kw.looks_like_investor_room(PARTNERS_ROOM, PARTNERS)
    assert kw.looks_like_investor_room("가나 홍길동 ASSET DEAL", SHORT_QUERY)


# ── ⑥ 검색칸을 비우고 붙인다 ───────────────────────────────────────────────

class StickyKakao(FakeKakao):
    """검색칸에 **직전 검색어가 남는** 카톡(실기). 붙이면 이어 붙는다."""

    def __init__(self, index, *, leftover="", stubborn=0, **kw_):
        super().__init__(index, **kw_)
        self.text = leftover
        self.stubborn = stubborn      # 처음 몇 번은 지우기가 안 먹는다


class StickyWin(FakeWin):
    def _search_titles(self, win, query, conf, keep_open=False):
        original = self._pyautogui.hotkey
        state = {"all": False}

        def hotkey(*keys):
            original(*keys)
            if keys == ("ctrl", "a"):
                state["all"] = True
            elif keys == ("backspace",) and state["all"]:
                state["all"] = False
                if win.stubborn:
                    win.stubborn -= 1
                else:
                    win.text = ""
            elif keys == tuple(conf.get("paste_hotkey") or ["ctrl", "v"]):
                win.text = win.text + self._pyperclip.text

        self._pyautogui.hotkey = hotkey
        try:
            return kw.KakaoDesktopSender._search_titles(
                self, win, query, conf, keep_open=keep_open)
        finally:
            self._pyautogui.hotkey = original


ROOM_A = "홍길동 대표 라마바 , 김영희 매니저"


def test_검색칸을_비운_뒤에_붙인다():
    kakao = StickyKakao({"라마바": [ROOM_A]}, leftover="가나다")
    sender = StickyWin(kakao)
    assert sender.discover_rooms("라마바") == [ROOM_A]
    keys = sender._pyautogui.keys
    f = keys.index(("ctrl", "f"))
    v = keys.index(("ctrl", "v"))
    assert keys[f + 1:v] == [("ctrl", "a"), ("backspace",)], keys


def test_비우기를_끄면_이어_붙은_글자로는_검색하지_않는다():
    """끄면(`clear_keys: []`) 실기 그대로 `가나다라마바` 가 된다 — 그때도 남의
    글자로 검색한 결과를 후보로 올리지 않는다."""
    kakao = StickyKakao({"라마바": [ROOM_A], "가나다라마바": [ROOM_A]},
                        leftover="가나다")
    sender = StickyWin(kakao)
    sender.sel = dict(sender.sel)
    sender.sel["room_search"] = dict(sender.sel.get("room_search") or {},
                                     clear_keys=[], open_top_fallback=False)
    assert sender.discover_rooms("라마바") == []
    assert sender._last_search_state == "typed_mismatch"


def test_한_번_안_지워지면_한_번_더_비우고_붙인다():
    kakao = StickyKakao({"라마바": [ROOM_A]}, leftover="가나다", stubborn=1)
    sender = StickyWin(kakao)
    assert sender.discover_rooms("라마바") == [ROOM_A]
    assert sender._pyautogui.keys.count(("ctrl", "v")) == 2


def test_두_번_다_안_지워지면_접는다():
    kakao = StickyKakao({"라마바": [ROOM_A]}, leftover="가나다", stubborn=5)
    sender = StickyWin(kakao)
    sender.sel = dict(sender.sel)
    sender.sel["room_search"] = dict(sender.sel.get("room_search") or {},
                                     open_top_fallback=False)
    assert sender.discover_rooms("라마바") == []
    assert sender._pyautogui.keys.count(("ctrl", "v")) == 2


def test_재시도_전에_포커스를_못_잡으면_키를_더_누르지_않는다():
    kakao = StickyKakao({"라마바": [ROOM_A]}, leftover="가나다", stubborn=5)
    sender = StickyWin(kakao)
    calls = {"n": 0}

    def focus(win, expect_title=None):
        calls["n"] += 1
        return calls["n"] == 1        # 처음(검색 전)만 잡힌다

    sender._focus_verified = focus
    assert sender.discover_rooms("라마바") == []
    assert sender._pyautogui.keys.count(("ctrl", "v")) == 1


def test_clear_keys_는_selectors_에_있다():
    from tests.test_win_discover_rooms import SELECTORS

    assert SELECTORS["room_search"]["clear_keys"] == [["ctrl", "a"], ["backspace"]]
    assert kw.clear_chords({"clear_keys": ["esc", ["ctrl", "a"]]}) == [
        ("esc",), ("ctrl", "a")]
    assert kw.clear_chords({"clear_keys": []}) == []
