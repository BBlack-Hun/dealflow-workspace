"""카톡방 `확인됨`(`room_verified`) ↔ `카톡방 참여여부`(`kakao_joined`) — **한 자리.**

투자사 관리 현황의 두 칸이 서로 다른 말을 하고 있었다. `카톡방` 칸은 `확인됨`
인데 바로 옆 `카톡방 참여여부` 는 비어 있거나 `X` 인 줄이 있었다. 두 값을 적는
자리는 여럿인데(방 확인 결과 · 표에서 고치기 · 수정창 · 시트 가져오기 ·
명단 스크립트) 서로를 몰랐기 때문이다. 사용자 요청: "카톡방 컬럼의 확인됨이랑
카톡방 참여여부랑 동기화 되게 해줘".

**맞추는 규칙은 이 파일에만 있다.** 적는 자리마다 규칙을 옮겨 적으면 하나만
고쳐지는 날 두 칸이 다시 갈린다 — 이 저장소가 반복해 당한 부류다. 그래서
`room_verified` 를 적는 자리는 전부 여기를 지나고(`set_verdict` ·
`after_edit`), 그것을 검사가 지킨다(`tests/test_room_joined.py` 의 쓰는 자리
목록).

## 규칙

1. 방 확인이 `확인됨` 으로 끝나면 참여여부를 `O` 로 적는다 — 비어 있거나
   `X`(안 참여) 일 때만. 이미 참여 표시(`O`·`○`·`●`·`○, DAY` …)가 있으면 그
   글자를 그대로 둔다. 사람이 적은 다른 말도 그대로 둔다.
2. 사람이 참여여부를 `X` 로 바꾸거나, 연결 단계가 `방 나감`·`참여 안 함` 으로
   바뀌면 `확인됨` 을 푼다(`unverified`). 그 사람은 방에 없다.
3. 사람이 `O` 로 바꿔도 방 확인은 그대로다. 방이 있다는 것은 PC 발송기만
   확인할 수 있다. `방 없음`·`복수 매칭` 도 그대로 둔다.
4. 방 확인이 `방 없음`·`복수 매칭` 으로 끝나면 참여여부는 건드리지 않는다.
   Windows 검색이 못 찾는 일이 잦아서, 거기서 `X` 를 적으면 틀린 `X` 가 된다.
5. 사람이 참여여부를 비우면 방 확인은 그대로다.

## 규칙 2 에서 따라 나오는 것 하나

연결 단계가 `방 나감`·`참여 안 함` 인 줄은 방 확인이 `확인됨` 으로 끝나도
`확인됨` 을 달지 않고, 참여여부도 `O` 로 바꾸지 않는다. 사람이 나갔다고 적어
둔 줄이다. 방 제목은 그 사람이 나간 뒤에도 내 카톡에 남아 있어서, 방을 찾은
것만으로는 그 사람이 방에 있다는 근거가 안 된다. 여기서 `확인됨` 을 달면 규칙
2 가 바로 지우는 상태를 만드는 셈이다. 다시 들어오신 분이면 사람이 단계를
`연결 완료` 로 고친 뒤 다시 확인하면 된다.

## 무엇을 보내는가는 이 파일이 안 정한다

`확인됨` 을 풀어도(`unverified`) 보낼 수 있는 갈래는 그대로다 — 둘 다
`dashboard._SENDABLE_ROOM` 안이다. 보낼지 말지는 연결 단계(`connect_stage`)가
정하고(`sheet_owner.is_connected`), 그 값은 사람이 고른다. 여기서는 두 칸이
같은 말을 하게 할 뿐이다.

## 무엇을 바꿨는지 따로 적지 않는다

여기서 바꾼 값은 같은 저장 안에서 일어나므로 수정 로그가 함께 남긴다
(`services/edit_log` 가 flush 때 바뀐 칸을 모은다 — 두 칸 다 값을 남기는 칸이다).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

# **판정은 시트 쪽 한 곳**이다 — 참여로 읽는 표시(`O`·`○`·`○, DAY` …)와 연결
# 단계 이름. 시트를 읽어 연결 단계를 정하는 쪽과 같은 판정을 읽어야 둘이 안
# 갈린다. (`sheet_import` 는 이 파일을 함수 안에서 부른다 — 순환을 피한다.)
from .sheet_import import (CONNECT_DONE, JOINED_EMPTY, JOINED_NO,
                           joined_state)

VERIFIED = "verified"
UNVERIFIED = "unverified"
NOT_FOUND = "not_found"
AMBIGUOUS = "ambiguous"

#: `room_verified` 가 가질 수 있는 넷(`models.VcContact.room_verified`).
VERDICTS = (VERIFIED, UNVERIFIED, NOT_FOUND, AMBIGUOUS)

#: 규칙 1 이 적는 글자. 표의 보기(`data-choices="O,X"`)와 같은 글자다.
JOINED_MARK = "O"


def joined_after_verified(joined: Optional[str], stage: Optional[str]) -> Optional[str]:
    """방이 `확인됨` 으로 끝났을 때 참여여부에 **새로 적을 값**. 그대로면 `None`.

    규칙 1 의 판정이다. 살아 있는 길(`set_verdict`)과 이미 쌓인 줄을 채우는
    스크립트(`scripts/sync_room_joined.py`)가 **같은 이 함수**를 부른다 —
    둘이 따로 정하면 스크립트가 채운 줄과 앞으로 채워질 줄이 다른 규칙을 탄다.
    """
    if (stage or "") in CONNECT_DONE:
        return None
    if joined_state(joined) in (JOINED_EMPTY, JOINED_NO):
        return JOINED_MARK
    return None


def set_verdict(contact, verdict: str) -> None:
    """방 확인 결과를 담당자 줄에 적는 **단 하나의 자리** (규칙 1·4).

    PC 발송기의 확인 결과(`routers/agent_api._apply_verify_result`), 동명이인
    이라 확인을 못 보낸 줄(`routers/contacts.verify_rooms`), 리허설 준비
    스크립트가 모두 여기로 온다.
    """
    if verdict not in VERDICTS:
        raise ValueError(f"모르는 방 확인 값입니다: {verdict}")
    contact.room_verified = verdict
    if verdict != VERIFIED:
        # 규칙 4 — 못 찾았다는 것은 그 사람이 방에 없다는 뜻이 아니다.
        return
    if (contact.connect_stage or "") in CONNECT_DONE:
        # 규칙 2 에서 따라 나오는 것 — 나갔다고 적힌 줄에 `확인됨` 을 달지 않는다.
        contact.room_verified = UNVERIFIED
        return
    joined = joined_after_verified(contact.kakao_joined, contact.connect_stage)
    if joined is not None:
        contact.kakao_joined = joined


@dataclass(frozen=True)
class Before:
    """고치기 **전** 의 세 값. 무엇이 *바뀌었는지* 를 보려면 전이 있어야 한다."""

    room_name: str
    joined: str
    stage: str


def before(contact) -> Before:
    """고치기 전에 떠 둔다 — `after_edit` 의 짝이다."""
    return Before(room_name=contact.kakao_room_name or "",
                  joined=contact.kakao_joined or "",
                  stage=contact.connect_stage or "")


def after_edit(contact, was: Before) -> None:
    """사람(또는 시트)이 줄을 고친 **뒤** — 방 이름 · 규칙 2·3·5.

    **바뀐 것만 본다.** 지금 값이 `X` 인 것만으로 풀면, 이미 `확인됨` + `X`
    로 어긋나 있던 줄이 메모 한 줄 고칠 때 덩달아 풀린다 — 무엇 때문에 풀렸는지
    아무도 모른다. 그런 줄은 정리 스크립트가 세어 보여 주고 사람이 정한다
    (`scripts/sync_room_joined.py`). 수정창은 저장할 때 모든 칸을 함께 보내므로
    이것이 더욱 필요하다 — 안 고친 `X` 도 매번 올라온다.
    """
    if (contact.kakao_room_name or "") != was.room_name:
        # 방 이름이 바뀌면 이전 확인 결과는 다른 방 이야기다.
        contact.room_verified = UNVERIFIED
        return
    if contact.room_verified != VERIFIED:
        # 규칙 3 — `방 없음`·`복수 매칭` 은 방 이름을 고치라는 경고라 그대로 둔다.
        # (`미확인` 으로 바꾸면 보낼 수 있는 갈래로 넘어간다.)
        return
    left = (joined_state(contact.kakao_joined) == JOINED_NO
            and joined_state(was.joined) != JOINED_NO)
    quit_ = ((contact.connect_stage or "") in CONNECT_DONE
             and was.stage not in CONNECT_DONE)
    if left or quit_:
        contact.room_verified = UNVERIFIED
