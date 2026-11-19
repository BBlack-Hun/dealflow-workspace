"""방 확인을 **못 한** 건의 말 — `못 찾음` 과 가른다 (0.11.16).

## 왜 있나

발송기는 카톡 검색 결과를 못 읽으면 `not_found` 를 올린다(모르는 것을 `verified` 로
올리지 않는다). 그런데 화면에는 그것이 **방이 없다**와 같은 말로 섰다 — 운영의 윈도우
PC 한 대에서 16명 방 찾기가 전부 `이 방을 찾지 못했습니다` 로 끝났는데, 실제로는
검색 결과를 한 줄도 못 읽었고 맨 위 방도 한 번도 안 열렸다(카톡이 채팅 탭이 아니었거나
잠금모드였을 수 있다). 사람은 방이 없다고 읽었고, 그 PC 에서 무엇을 봐야 하는지는
어디에도 없었다.

0.11.16 발송기는 **검색이 하나도 안 읽힌 건**에 그 까닭(`verify_reason`)을 함께 올린다
(`agent/sender/kakao_windows.py: blind_reason`). 여기서 그 까닭을 사람이 읽는 말로 바꾼다.

## 지키는 것

  · **판정은 그대로다.** 까닭이 와도 건은 `not_found` 로 받는다 — 무엇도 확인 완료로
    올리지 않고, 확인 표시를 거두는 자리(`sender_rooms.apply_result` 의 끝 ·
    `room_joined.set_verdict`)도 예전과 같다. 바뀌는 것은 **사유 글과 상태 말**이다.
  · **까닭 없이 온 결과는 예전 문구 그대로다** — 0.11.15 까지의 발송기 · 맥 발송기.
  · 찾은 제목이 하나라도 있거나 발송기 오류(`error`)가 실려 왔으면 쓰지 않는다 —
    그쪽 말이 먼저다.
  · 모르는 까닭 값은 `unreadable` 의 말로 받는다(나중 판의 발송기가 새 값을 보내도
    `확인 못 함` 으로 선다).

## 한계 — 사람이 읽는 말에 담았다

검색 결과 줄을 UIA 로 못 읽는 PC 에서는 **방이 정말 없을 때**도 똑같이 보인다(줄을 못
읽고, 열리는 방도 없다). 그래서 발송기는 **그 회차에서 검색이 한 번이라도 읽힌 뒤**의
건에는 까닭을 싣지 않고(= 예전의 `못 찾음`), 말에도 "카톡방이 없다는 뜻은 아닙니다 ·
그래도 같으면 카톡방 이름을 봐 주세요" 를 적는다.
"""
from __future__ import annotations

#: 사유 글의 머리 — 이 글자로 시작하면 **확인을 못 한** 건이다(`is_note`).
PREFIX = "확인 못 함 — "
#: 상태 칸에 서는 짧은 말(진행 화면 · 보내는 계정 방 제목 판 · 딜 소싱 화면).
LABEL = "확인 못 함"

MESSAGES = {
    # 검색 결과 줄도 못 읽고 맨 위 방도 안 열렸다 — 까닭은 모른다.
    "unreadable": (
        PREFIX + "보내는 PC 카톡에서 검색 결과를 읽지 못했습니다(카톡방이 없다는 뜻은 "
        "아닙니다). 그 PC 카톡이 채팅 탭에 있는지, 잠금모드가 아닌지 보고 다시 확인해 "
        "주세요. 그래도 같으면 카톡방 이름이 카톡에 뜨는 제목과 같은지 봐 주세요"),
    # 메인 창이 다른 탭으로 **확인됐다**(`selectors.yaml: chat_tab` 을 채운 PC 에서만).
    "not_chat_tab": (
        PREFIX + "보내는 PC 카톡이 채팅 탭이 아닌 것으로 보입니다. 채팅 탭으로 바꾼 뒤 "
        "다시 확인해 주세요"),
    "locked": (
        PREFIX + "보내는 PC 카톡이 잠금모드로 보입니다. 잠금을 풀고 다시 확인해 주세요"),
    "no_focus": (
        PREFIX + "보내는 PC 에서 카톡 창을 앞으로 가져오지 못했습니다. 카톡 창을 열어 "
        "두고 다른 창이 가리지 않게 한 뒤 다시 확인해 주세요"),
}


def note(body) -> str:
    """발송기가 **확인을 못 했다**고 올린 결과면 그 말, 아니면 빈 글자.

    `body` 는 건 결과(`agent_api.ItemResult`)다. 판정이 `not_found` 이고 찾은 제목도
    발송기 오류도 없을 때만 답한다.
    """
    reason = getattr(body, "verify_reason", None)
    if not isinstance(reason, str) or not reason.strip():
        return ""
    if getattr(body, "verify_result", None) != "not_found":
        return ""
    if (getattr(body, "error", None) or "").strip():
        return ""
    if (getattr(body, "found_room", None) or "").strip():
        return ""
    if any(str(c).strip() for c in (getattr(body, "candidates", None) or [])):
        return ""
    return MESSAGES.get(reason.strip(), MESSAGES["unreadable"])


def is_note(text) -> bool:
    """그 사유 글이 **확인 못 함**인가 — 진행 화면 · 끝난 알림의 셈이 본다."""
    return isinstance(text, str) and text.startswith(PREFIX)
