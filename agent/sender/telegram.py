"""TelegramSender — 테스트용 실제 수신 채널.

목적: 카톡 발송(Windows 전용)을 붙이기 전에, **문구가 실제로 어떻게 도착하는지**를
운영자가 자기 폰으로 직접 확인하기 위한 센더. macOS/Docker에서도 동작한다.

Kakao 와 동일한 Sender 인터페이스를 구현하므로 잡 큐·재시도·이력 경로가 전부 같다.
즉 이 센더로 통과한 파이프라인은 KakaoDesktopSender 로 바꿔 끼우기만 하면 된다.

주의: 실제 투자사에게 가는 것이 아니라 **설정된 chat_id(운영자 본인)** 에게만 간다.
      방 이름(room_name)은 실제로 열지 않고 메시지 머리말에 표기만 한다.
"""
from __future__ import annotations

import json
import logging
import os
import random
import time
import urllib.parse
import urllib.request
from typing import Optional

from .base import SendResult, Sender

log = logging.getLogger("agent.telegram")

API = "https://api.telegram.org/bot{token}/sendMessage"


class TelegramSender(Sender):
    name = "telegram"

    def __init__(self, token: str, chat_id: str,
                 delay_min: float = 0.5, delay_max: float = 1.5,
                 prefix_room: bool = True):
        if not token or not chat_id:
            raise ValueError("TelegramSender 는 token 과 chat_id 가 모두 필요합니다.")
        self.token = token
        self.chat_id = str(chat_id)
        self.delay_min = delay_min
        self.delay_max = delay_max
        self.prefix_room = prefix_room

    def verify_room(self, room_name: str) -> str:
        # 텔레그램에는 카톡 방 개념이 없다. 빈 이름만 걸러낸다(오발송 방지 규칙 유지).
        return "verified" if room_name and room_name.strip() else "not_found"

    def send_text(self, room_name: str, text: str) -> SendResult:
        if not room_name or not room_name.strip():
            return SendResult(ok=False, error="room_name empty (telegram)")

        # 사람 유사 발송 간격 — 실제 카톡 발송과 동일한 리듬으로 테스트되도록.
        time.sleep(random.uniform(self.delay_min, self.delay_max))

        body = text
        if self.prefix_room:
            # 어느 담당자(카톡방)에게 갈 문구인지 테스트 중 식별하기 위한 머리말.
            body = f"[테스트 발송 → {room_name}]\n\n{text}"

        data = urllib.parse.urlencode({
            "chat_id": self.chat_id,
            "text": body,
            "disable_web_page_preview": "true",
        }).encode()

        try:
            req = urllib.request.Request(API.format(token=self.token), data=data)
            with urllib.request.urlopen(req, timeout=20) as resp:
                payload = json.loads(resp.read().decode())
            if not payload.get("ok"):
                return SendResult(ok=False, error=f"telegram: {payload.get('description')}")
            log.info("[telegram] SENT room=%r chars=%d", room_name, len(text))
            return SendResult(ok=True)
        except Exception as exc:  # 네트워크/토큰 오류 등
            log.exception("[telegram] send failed")
            return SendResult(ok=False, error=f"telegram: {exc}")


def create_from_env(cfg: dict) -> "TelegramSender":
    """config.yaml 의 telegram 섹션 + 환경변수에서 생성.

    토큰은 코드/설정파일에 박지 말고 환경변수(DEALFLOW_TELEGRAM_TOKEN)로 넣는 것을 권장.
    """
    tg = (cfg or {}).get("telegram", {}) or {}
    token = os.environ.get("DEALFLOW_TELEGRAM_TOKEN") or tg.get("token", "")
    chat_id = os.environ.get("DEALFLOW_TELEGRAM_CHAT_ID") or tg.get("chat_id", "")
    return TelegramSender(
        token=token,
        chat_id=chat_id,
        delay_min=float(tg.get("delay_min_sec", 0.5)),
        delay_max=float(tg.get("delay_max_sec", 1.5)),
        prefix_room=bool(tg.get("prefix_room", True)),
    )
