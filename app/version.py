"""버전 — 서버와 발송 프로그램이 **같은 곳**을 본다.

## 왜 필요했나

발송 프로그램은 각자 PC 로 zip 을 받아 돌린다. 그래서 "지금 돌고 있는 게
어느 버전인가" 를 아무도 모른다. 실제로 함수 하나가 빠진 채 배포돼 사용자
PC 에서 `NameError` 로 터졌는데, 받은 쪽에서는 그게 낡은 것인지 고친 것인지
구분할 방법이 없었다. zip 에 코드 지문(sha256)을 넣어 두었지만, 지문으로는
**낡았는지** 를 판단할 수 없다 — 다르다는 것만 알 수 있다.

## 어떻게 쓰나

- 발송 프로그램이 폴링할 때마다 자기 버전을 알린다
- 서버는 그것을 저장하고, 자기보다 낡으면 화면에 드러낸다
- **막지는 않는다.** 회차 당일에 버전이 낡았다고 발송을 거부하면, 조금
  오래된 프로그램으로 보낼 수 있었던 것까지 못 보낸다. 크게 알리되 보낸다

## 올릴 때

발송 프로그램 쪽 동작이 바뀌면 **반드시** 올린다(문구를 나눠 보내는 방식이
바뀐 것 같은 경우). 서버만 바뀐 것은 잔 자리만 올린다.

    0.2.0  IR 자료 전달을 여러 통으로 나눠 보낸다 (발송 프로그램 필수 갱신)
    0.1.0  태그 없이 굴리던 시기
"""
from __future__ import annotations

VERSION = "0.2.0"

# 이 버전보다 낡은 발송 프로그램은 화면에서 '갱신 필요' 로 표시한다.
# 여기에 적힌 버전부터 링크를 여러 통으로 나눠 보낼 수 있다 — 그 아래는
# 한 통으로 보내므로 나가긴 하지만 카톡에서 미리보기 카드가 안 뜬다.
MIN_AGENT_VERSION = "0.2.0"


def as_tuple(value: str) -> tuple:
    """`"0.2.0"` → `(0, 2, 0)`. 비교하려고. 못 읽는 값은 (0,) 로 둔다 —
    모르는 버전은 낡은 것으로 보는 편이 안전하다."""
    parts = []
    for chunk in (value or "").split("."):
        digits = "".join(c for c in chunk if c.isdigit())
        if not digits:
            break
        parts.append(int(digits))
    return tuple(parts) or (0,)


def agent_is_old(reported: str | None) -> bool:
    """이 발송 프로그램이 갱신이 필요한가. 버전을 안 알리면 낡은 것으로 본다."""
    if not reported:
        return True
    return as_tuple(reported) < as_tuple(MIN_AGENT_VERSION)
