"""문자 발송 — **우리 팀원에게만** 가는 알림 채널.

메일과 나가는 길이 같다. 카톡은 각자 PC 의 발송 프로그램이 창을 눌러 보내지만,
문자는 메일처럼 **서버가 바로** 보낸다. PC 를 켜 둘 필요도, 방 제목을 맞출
일도 없다 — 그래서 아침에 저절로 나가야 하는 알림에 쓸 수 있는 유일한 길이다.

**받는 사람은 우리 팀원뿐이다.** 투자사에게는 이 길로 보내지 않는다. 광고성
정보 규제(정보통신망법 제50조 — 사전 동의·야간 발송 제한·`(광고)` 표기)가
붙지 않는 이유가 그것이고, 넘어가면 안 되는 선도 그것이다. 번호를 밖에서
받지 않는 것으로 그 선을 지킨다(`followup_sms.py` 의 `recipients`).

설정은 환경변수로 준다(저장소에 올라가지 않게 `.env` 에 둔다):

    DEALFLOW_SMS_API_KEY=...
    DEALFLOW_SMS_API_SECRET=...
    DEALFLOW_SMS_FROM=0212345678     # 업체에 **등록해 둔** 발신번호

값이 하나라도 비면 `is_configured()` 가 거짓이고, 알림은 **조용히 아무것도 하지
않는다.** 메일이 지금 그렇다.

업체
----
지금 쓰는 곳은 **솔라피(SOLAPI)** 다. 업체에 매인 것은 이 파일 아래쪽
`업체에 매인 자리` 한 칸에 모아 두었다 — 주소·서명 방식·응답 읽는 법. 나중에
알리고 같은 데로 갈아타면 고칠 곳이 거기 하나다.

**갈아타기 틀은 만들지 않았다.** 지금 쓰는 곳이 하나뿐인데 업체마다 클래스를
두면, 쓰이지 않는 쪽은 아무도 돌려 보지 않아 처음 갈아타는 날 그대로 안 된다.

새 의존성을 넣지 않았다
-----------------------
솔라피 인증은 `HMAC-SHA256(date + salt, apiSecret)` 이다. 표준 라이브러리
`hmac`·`hashlib`·`secrets` 로 그대로 되고, 보내는 것은 JSON 한 덩이라
`urllib.request` 로 충분하다. 업체 SDK 를 넣으면 인증 방식이 바뀔 때 우리가
고칠 수 없는 코드가 하나 늘 뿐이다(에이전트의 텔레그램 센더도 같은 이유로
`urllib.request` 를 쓴다).

**이 앱이 바깥으로 HTTP 를 부르는 것은 이번이 처음이다.** 그래서 두 가지를
지킨다.

- **시간 제한**(`TIMEOUT_SEC`). 업체가 안 받으면 알림 실이 거기 매달린다.
- **실패를 조용히 삼키지 않는다.** 여기서는 예외를 그대로 올리고, 부르는 쪽이
  그 사유를 DB 에 남겨 화면에 띄운다(`sms_notices.error`).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from .. import clock


class SmsNotConfigured(RuntimeError):
    """문자 발송 설정이 없어 보낼 수 없다."""


class SmsSendFailed(RuntimeError):
    """업체가 받지 못했다. 사유는 사람이 볼 수 있게 문자열로 담는다."""


# 업체가 안 받을 때 여기서 매달리지 않게. 알림 실 하나가 통째로 멎는다.
# 문자는 늦게 가면 쓸모가 줄지만, 앱이 멈추는 것보다는 낫다.
TIMEOUT_SEC = 10

# 단문(SMS) 한 통에 들어가는 크기. **넘으면 장문(LMS) 으로 넘어가 값이 뛴다.**
# 한글은 EUC-KR 기준 2바이트라 45자쯤이 한계다(`byte_len` 참고).
SMS_MAX_BYTES = 90


@dataclass
class SmsSettings:
    api_key: str = ""
    api_secret: str = ""
    sender: str = ""          # 발신번호(숫자만)

    @property
    def configured(self) -> bool:
        """정말 보낼 수 있는 상태인가.

        발신번호는 열쇠만큼 중요하다 — 업체에 **등록해 둔 번호**가 아니면
        접수 단계에서 거부당한다. 셋 중 하나라도 비면 켜지지 않은 것으로 본다.
        고를 수 있는데 나가지 않는 상태를 만들지 않는다.
        """
        return bool(self.api_key and self.api_secret and self.sender)


def load_settings() -> SmsSettings:
    """부를 때마다 환경변수를 다시 읽는다(메일 설정과 같은 방식)."""
    return SmsSettings(
        api_key=os.environ.get("DEALFLOW_SMS_API_KEY", "").strip(),
        api_secret=os.environ.get("DEALFLOW_SMS_API_SECRET", "").strip(),
        sender=digits(os.environ.get("DEALFLOW_SMS_FROM", "")),
    )


def is_configured() -> bool:
    return load_settings().configured


def status() -> dict:
    """화면에 보여줄 설정 상태. **비밀값은 있는지 없는지만** 알린다."""
    s = load_settings()
    missing = []
    if not s.api_key:
        missing.append("API 키")
    if not s.api_secret:
        missing.append("API 시크릿")
    if not s.sender:
        missing.append("발신번호")
    return {
        "configured": s.configured,
        "vendor": VENDOR_LABEL,
        # 발신번호는 우리 회사 대표번호다(비밀값이 아니고, 틀리면 화면에서
        # 바로 알아야 하는 값이다). 열쇠 두 개는 있음/없음만.
        "sender": s.sender,
        "has_key": bool(s.api_key),
        "has_secret": bool(s.api_secret),
        "missing": missing,
    }


def digits(raw: Optional[str]) -> str:
    """번호에서 숫자만 남긴다.

    `auth.normalize_phone` 과 같은 규칙이다 — 이 앱은 **로그인 ID 가 곧
    휴대폰번호**라 `users.phone` 에 이미 숫자만 들어 있고, 사람이 `.env` 에
    적는 발신번호에는 하이픈이 섞인다. 양쪽을 같은 모양으로 만들어야
    "팀원 번호인가" 를 견줄 수 있다.
    """
    return re.sub(r"\D", "", raw or "")


def byte_len(text: str) -> int:
    """이 문구가 문자 몇 바이트인가 — **EUC-KR 기준**.

    통신사가 단문/장문을 가르는 자리가 이 바이트 수다(한글 2, 영문·숫자 1).
    파이썬 문자열 길이로 재면 한글 45자짜리를 45로 세어 "짧다" 고 판단하고,
    실제로는 90바이트라 장문으로 나가 값이 두 배 이상 뛴다.

    EUC-KR 이 모르는 글자(이모지 등)는 **2바이트로 친다** — 정확히는 통신사가
    이런 문구를 유니코드 장문으로 바꾸지만, 여기서는 '적어도 이만큼' 만
    알면 된다. 모자라게 세는 쪽이 위험하다.
    """
    total = 0
    for ch in text:
        try:
            total += len(ch.encode("euc-kr"))
        except UnicodeEncodeError:
            total += 2
    return total


def send(to: str, text: str, settings: Optional[SmsSettings] = None) -> str:
    """문자 한 통. 실패하면 예외를 올린다(조용히 삼키면 안 된다).

    돌려주는 것은 업체가 준 접수 번호다 — 나중에 업체 화면에서 되짚을 때 쓴다.

    **받는 사람이 팀원인지는 여기서 보지 않는다.** 그 판단은 번호를 고르는
    자리(`followup_sms.recipients`)에 있다. 두 군데에 적으면 한쪽이 낡는다.
    """
    s = settings or load_settings()
    if not s.configured:
        raise SmsNotConfigured(
            "문자 발송 설정이 없습니다. 관리자에게 문자 발송 설정을 요청하세요.")
    number = digits(to)
    if not number:
        raise ValueError("받는 사람 번호가 없습니다")
    if not text.strip():
        raise ValueError("보낼 문구가 없습니다")
    return _vendor_send(s, number, text)


def redact(text: str) -> str:
    """로그·DB 에 남기기 전에 **번호를 지운다.**

    업체가 돌려주는 실패 사유에 받는 번호가 그대로 섞여 오는 일이 있다
    (`01012345678 는 수신거부 번호입니다`). 그것을 그대로 적으면 로그와 DB 가
    번호를 흘리는 자리가 된다. 숫자 8자리 이상만 가린다 — 오류 코드(`2000`)나
    바이트 수까지 가리면 무엇이 잘못됐는지 읽을 수 없다.
    """
    return re.sub(r"\d{8,}", "***", text or "")


# ── 업체에 매인 자리 (SOLAPI) ────────────────────────────────────────────────
#
# 갈아탈 때 고칠 곳은 여기까지다. 위쪽은 어느 업체든 그대로 쓴다.
#
# 인증: `Authorization: HMAC-SHA256 apiKey=…, date=…, salt=…, signature=…`
#       signature = HMAC-SHA256(date + salt, apiSecret) 의 16진수
# 접수: POST /messages/v4/send  ·  {"message": {"to","from","text"}}
# 성공: HTTP 200 이고 statusCode 가 2 로 시작(2000 = 정상 접수)
#
# 문구 종류(SMS/LMS)는 **보내지 않는다.** 길이를 보고 업체가 정한다 — 여기서
# `SMS` 라고 박아 두면 90바이트를 넘긴 날 접수 자체가 거부된다.

VENDOR_LABEL = "솔라피(SOLAPI)"
API_URL = "https://api.solapi.com/messages/v4/send"


def _vendor_send(s: SmsSettings, number: str, text: str) -> str:
    body = json.dumps({"message": {
        "to": number, "from": s.sender, "text": text,
    }}).encode("utf-8")
    request = urllib.request.Request(
        API_URL, data=body, method="POST",
        headers={"Content-Type": "application/json",
                 "Authorization": _auth_header(s)})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SEC) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        # 4xx·5xx 는 몸통에 사유가 들어 있다. 읽지 않으면 `HTTP Error 400` 만
        # 남아서 무엇이 틀렸는지(키인지 발신번호인지) 알 수 없다.
        raise SmsSendFailed(redact(_http_error_detail(exc))) from exc
    except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
        # 그물이 끊겼거나 업체가 이상한 것을 돌려줬다. 앱은 멈추지 않는다 —
        # 부르는 쪽이 이 사유를 DB 에 남기고 화면이 그것을 보여 준다.
        raise SmsSendFailed(f"문자 업체에 연결하지 못했습니다: {redact(str(exc))}") from exc

    code = str(payload.get("statusCode") or "")
    if not code.startswith("2"):
        detail = payload.get("statusMessage") or payload.get("errorMessage") or code
        raise SmsSendFailed(redact(f"업체가 접수하지 않았습니다 ({code}): {detail}"))
    return str(payload.get("messageId") or "")


def _auth_header(s: SmsSettings, *, now: Optional[datetime] = None,
                 salt: Optional[str] = None) -> str:
    """서명 한 줄. `now`·`salt` 를 받는 것은 **검사에서 값을 고정하려고** 다.

    지금이 언제인지는 `app/clock.py` 하나에서만 읽는다(그 자리가 흩어져서 겪은
    일은 그쪽 머리말에 있다). 다만 업체에 적어 보내는 것은 **UTC** 다 — 우리
    시간대로 보내면 서명은 맞아도 `date` 가 허용 범위를 벗어났다고 거부당한다.
    `clock.now()` 는 오프셋이 붙은 값이라 그대로 옮길 수 있다.
    """
    stamp = (now or clock.now()).astimezone(
        timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    nonce = salt or secrets.token_hex(16)
    signature = hmac.new(s.api_secret.encode("utf-8"),
                         (stamp + nonce).encode("utf-8"),
                         hashlib.sha256).hexdigest()
    return (f"HMAC-SHA256 apiKey={s.api_key}, date={stamp}, "
            f"salt={nonce}, signature={signature}")


def _http_error_detail(exc: urllib.error.HTTPError) -> str:
    try:
        payload = json.loads(exc.read().decode("utf-8"))
    except Exception:  # noqa: BLE001 - 몸통이 JSON 이 아니면 상태 줄만 남긴다
        return f"문자 업체가 거부했습니다 (HTTP {exc.code})"
    detail = payload.get("errorMessage") or payload.get("message") or ""
    code = payload.get("errorCode") or exc.code
    return f"문자 업체가 거부했습니다 ({code}): {detail}".strip()
