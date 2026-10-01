"""스타트업 대표 카톡방 **맞추기** — 방 제목을 어떻게 알아내고, 누가 고르나.

## 막혀 있던 것

계약을 마친 기업 수십 곳에 달마다 한 번 「IR 자료를 요청한 투자사 목록」을
보내야 하는데, `IrCompany.kakao_room_name` 이 든 곳이 **하나도 없었다**. 그래서
`/deals/startup-ir` 의 모든 줄이 `카톡방 이름 없음` 으로 떠서 고를 수 있는 것이
없었다. 채우는 길은 `IR 기업 현황` 의 [수정] 창을 **기업마다 한 번씩** 여는
것뿐이었다.

## 왜 규칙만으로는 안 되나  ★

투자사 담당자 쪽은 방 이름을 규칙으로 짓는다(`services/room_name.build_room_name`)
— `이름 직함 투자사 <고정 접미사>`. 스타트업 방은 그렇게 안 된다.

사용자가 든 실제 모양은 `대표자 대표 회사명 , 우리 팀원 직함` 인데,

  · **띄어쓰기가 제각각이다.** 같은 회사를 `회사 명` 으로 적은 방도 있고
    `회사명` 으로 적은 방도 있다. 발송기는 제목이 **글자까지** 같아야 방을
    찾으므로(`agent/sender/base.py` 의 "never guess"), 한 글자 틀린 이름은
    못 찾는 이름이다.
  · **꼬리의 우리 팀원을 채울 칸이 없다.** 그 자리에 쓸 만한 칸은
    `IrCompany.assignee_name` 하나인데, 그 칸은 **이관 이력 메모**다 —
    운영 56줄 중 41줄에 `A -> B` 꼴의 화살표·날짜·접두가 섞여 있다.
    거기서 사람 이름 하나를 뽑아내려면 짐작해야 한다.
  · **투자사 쪽 접미사를 붙여서도 안 된다.** `Deal 공유 … Asset` 은 투자사
    방에만 붙고 스타트업 방에는 없다(사용자 확인).

그래서 **규칙은 초안까지만** 짓고, 실제 제목은 **카톡에서 가져와 사람이
고른다.**

## 제목을 어디서 가져오나 — 이미 있는 길을 쓴다  ★★

발송기를 고치지 않는다. **방 확인 잡(`verify_room`)이 이미 카톡을 검색해 방
제목 목록을 서버로 올린다** — `agent/main.py: process_verify_job` 가
`sender.discover_rooms(query)` 로 찾은 제목들을 `candidates` 로 보고한다
(`agent/sender/kakao_mac.py: discover_rooms` — 방을 열지 않고 검색 결과 줄의
글자만 읽는다). 서버가 그 `candidates` 를 **받아 놓고 버리고 있었다.**

이 파일이 그 목록을 받아 두는 자리이고, 받는 칸은
`IrCompany.room_candidates` 다.

**그래서 발송기를 안 건드린다 — 판(`agent/version.py`)도 안 올리고, 팀원 PC 에
깔린 발송기를 다시 받게 하지도 않는다.** 새 잡 종류를 만들었다면 그 종류를
모르는 발송기가 잡을 집어가지 않아 큐에 그대로 서게 되고
(`app/version.py` 의 0.9.0 · 0.10.0 설명), 모두가 새로 받을 때까지 이 기능이
돌지 않는다. `routers/setup.py` 의 시험용 방 확인 자리에도 같은 말이 적혀
있다 — *"새 종류를 만들면 발송기를 갱신할 때까지 큐에 멈춘다."*

### 다만 후보가 **늘 오는 것은 아니다** — 화면이 그것을 말한다

`discover_rooms` 는 처음에 **macOS 발송기에만** 있었다. Windows 쪽은
발송기 **0.11.0** 에서 같은 자리가 채워졌다(`agent/sender/kakao_windows.py`).
새 잡 종류를 만든 것이 아니라 이미 있던 `verify_room` 갈래의 빈 자리를 채운
것이라 **큐에 서는 일은 없다** — 다만 **0.11.0 보다 낡은 Windows 발송기가 붙어
있으면 그 PC 에서는 여전히 후보가 0건**이다(그 자리가 비어 있다). 그리고 발송기
설정에 `room_marker` 가 들어 있으면 그 글자가 든 방만 남긴다 — 그것은 **투자사
방을 가려내려고** 둔 값이라(`agent/main.py: DEFAULT_CONFIG`, 기본값은 비어
있다), 켜져 있으면 스타트업 방이 전부 걸러진다.

**그래서 화면은 그대로 적어 둔다.** 후보가 0건이어도 이 화면은 그대로 쓸 수
있다 — 초안이 서고, 사람이 카톡에서 복사해 붙여 넣는다. 0건을 "카톡에 방이
없다" 로 읽으면 엉뚱한 데를 뒤지게 된다.

## 서버는 고르지 않는다  ★★

후보가 **하나뿐이어도** `kakao_room_name` 에 넣지 않는다. 회사명이 든 방이 꼭
그 회사 대표와의 방인 것은 아니다 — 그 회사 이름이 들어간 다른 방일 수 있고,
검색은 참여자 이름에도 걸린다. 짐작해서 넣으면 **엉뚱한 방으로 간다.**

투자사 담당자 쪽은 하나뿐인 결과를 자동으로 넣는다
(`routers/agent_api._apply_verify_result`). 그쪽은 **사람이 이미 적어 둔 방
이름을 대조하는 길**이라 사정이 다르다 — 찾은 제목이 적어 둔 것과 같은 방일
근거가 있다. 여기는 적어 둔 것이 아무것도 없는 상태에서 **처음 알아내는**
길이다. 근거가 없으니 사람이 고른다.
"""
from __future__ import annotations

import json
from typing import List, Optional

from sqlalchemy.orm import Session

from ..models import IrCompany
from .ir_monthly import contracted
from .room_name import normalize_space
from .sheet_import import normalize_company_name

#: 방 확인 결과가 쓸 수 있는 값. `VcContact.room_verified` 와 **같은 넷**이다
#: (`routers/agent_api.VERIFY_VERDICTS` + 아직 안 해 본 상태).
UNVERIFIED = "unverified"

#: 화면에 적는 말. 숫자만 보여 주면 무엇을 해야 하는지 알 수 없다
#: (`startup_send.NO_ROOM` 과 같은 결).
STATE_LABELS = {
    UNVERIFIED: "확인 안 됨",
    "verified": "확인됨",
    "ambiguous": "같은 이름이 여럿",
    "not_found": "카톡에서 못 찾음",
}

#: 초안에 붙는 직함. 사용자가 든 실제 방 이름이 `… 대표 …` 라 그대로 쓴다.
#: `services/room_name.looks_like_title` 의 어휘를 넓히지 않는다 — 그쪽은
#: 투자사 방 이름을 짓는 자리고, 넓히면 예전에 만든 방과 새로 만드는 방
#: 이름이 갈린다.
CEO_TITLE = "대표"


# ── 견주기 ──────────────────────────────────────────────────────────────────

def key(name: Optional[str]) -> str:
    """비교용 이름. `(주)`·띄어쓰기·대소문자 차이로 다른 회사가 되지 않게.

    `services/ir_monthly._key` · `services/deal_history._key` 가 쓰는 것과
    **같은 규칙**이다 — 세 곳이 다르게 맞추면 같은 기업이 화면마다 다른 줄에
    붙는다. 여기서 이 규칙이 하는 일은 하나다: 사용자가 짚어 준
    「**회사명이 무조건 들어가 있음**」을 띄어쓰기 차이에도 견딜 수 있게
    확인하는 것(`회사 명` ↔ `(주)회사명`).
    """
    return normalize_company_name(name or "").replace(" ", "").lower()


def has_company_name(room: Optional[str], company_name: Optional[str]) -> bool:
    """이 방 제목에 **그 회사 이름이 들어 있는가.**

    사용자가 짚어 준 매칭의 열쇠다 — 스타트업 방 제목에는 회사명이 무조건
    들어간다. 들어 있지 않은 후보도 **지우지 않는다**(화면에 남기고 표시만
    한다): 우리가 아는 회사명이 사용자가 카톡방을 만들 때 쓴 이름과 다를 수
    있고, 그때 지워 버리면 맞는 방이 화면에서 사라진다.

    `tells_people_apart`(투자사 쪽)와 같은 모양의 물음이지만 규칙이 다르다 —
    그쪽은 `room_name._key`(괄호·점까지 뗀다), 여기는 위 `key`(법인 표기를
    뗀다). 맞춰 둘 값보다 **각자 쓰는 자리에서 맞는 규칙**을 쓰는 값이 크다.
    """
    want = key(company_name)
    return bool(want) and want in key(room)


# ── 초안 ────────────────────────────────────────────────────────────────────

def draft(company: IrCompany) -> str:
    """규칙으로 지어 본 방 제목 **초안**. 지을 수 없으면 빈 글자.

    모양은 사용자가 든 실제 방 이름에서 왔다:

        {대표자} 대표 {회사명}

    꼬리의 `, 우리 팀원 직함` 은 **일부러 안 붙인다** — 채울 칸이
    `assignee_name` 하나뿐이고 그 칸에는 이관 이력이 들어 있다(머리말).
    없는 것을 지어 붙이면 초안이 **그럴듯해지고**, 그럴듯한 초안은 확인 없이
    저장된다. 모자란 초안은 모자란 채로 보이는 편이 낫다.

    회사명은 법인 표기를 뗀 것을 쓴다(`(주)회사명` → `회사명`) — 카톡방
    제목에 `(주)` 가 붙는 경우를 사용자가 든 예에서 보지 못했다.

    **이 값은 어디에도 저장되지 않는다.** 화면이 보여 주고, 사람이 그것으로
    하겠다고 눌렀을 때만 `kakao_room_name` 에 들어간다.
    """
    name = normalize_space(normalize_company_name(company.name or ""))
    if not name:
        return ""
    ceo = normalize_space(company.contact_name or "")
    if not ceo:
        # 대표 이름을 모르면 **회사명만** 내놓는다. 그래도 쓸모가 있다 —
        # 카톡에서 무엇으로 검색할지가 이 글자다.
        return name
    return f"{ceo} {CEO_TITLE} {name}"


def search_query(company: IrCompany) -> str:
    """카톡 검색창에 넣을 글자. **회사명 하나다.**

    사용자가 정한 길이 그대로다 — *"먼저 회사명으로 검색 후 리스트에서
    매칭되는 거 찾으면 될 듯"*. 대표자명을 섞지 않는다: 방 제목에 무조건 든
    것은 회사명이고(사용자 확인), 대표자명 표기가 방마다 다르면 섞은 검색어가
    오히려 결과를 0건으로 만든다.

    법인 표기를 뗀다 — 카톡 검색은 글자가 든 방을 찾으므로 `(주)` 가 붙은
    검색어는 그것이 든 방만 찾는다.
    """
    return normalize_space(normalize_company_name(company.name or ""))


def search_seed(company: IrCompany) -> str:
    """검색어로 아무것도 못 찾았을 때 **한 번 더 넣어 볼 더 짧은 글자.**

    발송기가 이미 그렇게 움직인다 — 검색어로 0건이면 `item["name"]` 으로 한
    번 더 찾는다(`agent/main.py: process_verify_job`). 그 자리에 **회사명의
    가장 긴 토막**을 넣는다.

    왜 짧은 쪽이 필요한가: 우리가 아는 이름이 `회사 명` 인데 방 제목은
    `회사명` 일 수 있다(사용자가 든 예가 그렇다). 띄어쓰기가 든 검색어는 그
    방을 못 찾지만 `회사` 는 찾는다. 넓게 찾은 뒤 **고르는 것은 사람**이라
    넓혀도 위험이 늘지 않는다.

    한 토막짜리 이름이면 검색어와 같은 글자가 되고, 그때 발송기는 두 번째
    검색을 건너뛴다(`name_only != query` 를 본다) — 헛걸음이 없다.
    """
    parts = [p for p in search_query(company).split(" ") if p]
    if not parts:
        return ""
    return max(parts, key=len)


# ── 후보 담아 두기 ──────────────────────────────────────────────────────────

def save_candidates(company: IrCompany, rooms, *, at: str,
                    query: str = "") -> None:
    """카톡에서 찾아낸 제목들을 담는다. **`kakao_room_name` 은 안 건드린다.**

    담는 모양은 `{"at": …, "query": …, "rooms": [...]}` 다. 언제·무엇으로
    찾은 것인지가 없으면 화면이 `후보 없음` 을 두 가지로 읽을 수 없다 —
    아직 안 찾아본 것과 찾았는데 없던 것은 해야 할 일이 정반대다.
    """
    clean: List[str] = []
    for room in rooms or []:
        text = normalize_space(str(room))
        if text and text not in clean:
            clean.append(text)
    company.room_candidates = json.dumps(
        {"at": at, "query": query, "rooms": clean}, ensure_ascii=False)


def candidates(company: IrCompany) -> dict:
    """담아 둔 후보. 한 번도 안 찾아봤으면 `{"at": "", "rooms": []}`.

    글자가 깨져 있어도 **터지지 않는다** — 이 값으로 열리는 것은 고르는
    화면이고, 거기서 500 이 나면 방 이름을 채울 길이 통째로 막힌다.
    """
    raw = (company.room_candidates or "").strip()
    if not raw:
        return {"at": "", "query": "", "rooms": []}
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return {"at": "", "query": "", "rooms": []}
    if not isinstance(data, dict):
        return {"at": "", "query": "", "rooms": []}
    rooms = [str(r) for r in (data.get("rooms") or []) if str(r).strip()]
    return {"at": str(data.get("at") or ""),
            "query": str(data.get("query") or ""),
            "rooms": rooms}


# ── 방 이름 적기 ────────────────────────────────────────────────────────────

def set_room(company: IrCompany, value: Optional[str]) -> bool:
    """`kakao_room_name` 을 적는 **한 자리.** 바뀌었으면 True.

    `IR 기업 현황` 의 [수정] 창도(`routers/companies._assign`) 맞추기 화면도
    이 함수를 지난다. 두 곳에 따로 적으면 **한쪽만 확인 표시를 지운다** —
    창에서 방 이름을 고친 기업이 `확인됨` 배지를 그대로 달고 있게 되고, 그
    배지는 거짓말이다.

    ## 글자가 바뀌면 확인은 무효다  ★

    `room_verified` 를 `unverified` 로 되돌린다. 투자사 담당자 쪽이 같은
    규칙이다(`routers/contacts.py` 의 방 이름 PATCH) — 확인은 **그때 그
    글자**에 대한 것이라, 글자를 고치면 확인한 적이 없는 것이다.

    **앞뒤 공백만 뗀다.** 가운데 공백을 줄이지 않는다 — 방 제목은 카톡에
    보이는 글자 그대로여야 하고(`startup_send.room_of`), 두 칸 띄운 방이
    있다면 줄여 적는 순간 못 찾는 이름이 된다.
    """
    new = (value or "").strip() or None
    if new == company.kakao_room_name:
        return False
    company.kakao_room_name = new
    company.room_verified = UNVERIFIED
    return True


# ── 화면이 읽는 것 ──────────────────────────────────────────────────────────

def rows(db: Session) -> dict:
    """맞추기 화면이 읽는 것 — **계약 기업 전부, 한 판에.**

    ## 달을 안 받는다

    `startup_send.rows` 는 달을 받는다(그 달에 실을 줄이 있는가를 세므로).
    방 제목은 달과 상관이 없다 — 한 번 맞춰 두면 다음 달에도 그 방이다.
    달을 받으면 "9월 화면에서 맞춘 방이 10월에도 맞춰져 있나" 를 사람이
    의심하게 된다.

    ## 대상은 `startup_send` 와 **같은 기업 집합**이다

    `ir_monthly.contracted` 하나를 지난다 — 보낼 수 있는 곳과 맞출 수 있는
    곳이 갈리면, 맞춰 놓고도 못 보내는 기업이나 못 맞추는데 보내야 하는
    기업이 생긴다.

    ## 못 보내는 줄을 **빼지 않는다**

    `startup_send.rows` 의 그 규칙 그대로다. 후보가 없는 기업도, 방 이름이
    이미 든 기업도 전부 남는다 — 빼면 "왜 이 기업이 목록에 없지" 를 화면에서
    물을 수가 없다. 대신 줄마다 **무엇이 모자란지**를 적는다.
    """
    out = []
    for company in contracted(db):
        found = candidates(company)
        room = (company.kakao_room_name or "").strip()
        picks = [{"room": r, "has_name": has_company_name(r, company.name)}
                 for r in found["rooms"]]
        out.append({
            "company": company,
            "room": room,
            "state": company.room_verified or UNVERIFIED,
            "state_label": STATE_LABELS.get(
                company.room_verified or UNVERIFIED, company.room_verified or ""),
            # 초안은 **초안이라고** 보여야 한다. 후보와 나란히 두면 카톡에서
            # 가져온 진짜 제목과 우리가 지어 본 글자가 한 줄에 섞인다.
            "draft": draft(company),
            "query": search_query(company),
            "candidates": picks,
            "searched_at": found["at"],
            # 담아 둔 후보 중 **그 회사 이름이 든 것**이 몇 개인가. 화면이
            # 이 수로 `볼 만한 후보` 와 `회사명이 안 든 후보` 를 갈라 적는다.
            "named_count": sum(1 for p in picks if p["has_name"]),
        })
    return {
        "rows": out,
        "total": len(out),
        "with_room": sum(1 for r in out if r["room"]),
        "no_room": sum(1 for r in out if not r["room"]),
        "verified": sum(1 for r in out if r["state"] == "verified"),
        # 한 번도 안 찾아본 곳. **찾았는데 0건인 곳과 가른다** — 앞은 단추를
        # 누르면 되고, 뒤는 카톡을 사람이 들여다봐야 한다.
        "never_searched": sum(1 for r in out if not r["searched_at"]),
        "with_candidates": sum(1 for r in out if r["candidates"]),
    }


def company_ids(db: Session) -> List[int]:
    """맞출 수 있는 기업 id. **막는 자리가 읽는 것도 이것이다** — 화면이 거른
    것과 라우터가 거른 것이 갈리면 화면에 없는 줄이 주소로는 들어간다
    (`startup_send.sendable_ids` 와 같은 짝)."""
    return [c.id for c in contracted(db)]
