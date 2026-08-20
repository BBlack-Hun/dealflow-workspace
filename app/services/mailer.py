"""메일 발송 — 카톡으로 받지 않겠다는 투자사를 위한 두 번째 채널.

**카톡과 나가는 길이 다르다.** 카톡은 각자 PC의 발송 프로그램이 창을 눌러 보내지만,
메일은 서버가 SMTP 로 바로 보낸다. PC를 켜 둘 필요가 없고, 방 제목이 맞는지
확인할 일도 없다. 대신 메일 주소가 없으면 아무 것도 못 한다.

지금은 **자리만 잡아 둔 상태**다. 메일 서버 정보(SMTP)가 들어오면 `is_configured()`
가 참이 되고 발송 화면에서 메일 채널을 고를 수 있게 된다. 설정이 없으면
화면에서 아예 고를 수 없게 막는다 — 고를 수 있는데 나가지 않는 것이 제일 나쁘다.

설정은 환경변수로 준다(저장소에 올라가지 않게 `.env` 에 둔다):

    DEALFLOW_SMTP_HOST=smtp.example.com
    DEALFLOW_SMTP_PORT=587
    DEALFLOW_SMTP_USER=deal@example.com
    DEALFLOW_SMTP_PASSWORD=...
    DEALFLOW_SMTP_FROM=딜소싱팀 <deal@example.com>
    DEALFLOW_SMTP_TLS=1
"""
from __future__ import annotations

import os
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr
from typing import List, Optional


class MailerNotConfigured(RuntimeError):
    """메일 서버 정보가 없어 보낼 수 없다."""


@dataclass
class MailSettings:
    host: str = ""
    port: int = 587
    user: str = ""
    password: str = ""
    sender: str = ""
    use_tls: bool = True

    @property
    def configured(self) -> bool:
        # 보내는 주소는 서버 주소만큼 중요하다. 없으면 받는 쪽에서 스팸으로 걸린다.
        return bool(self.host and (self.sender or self.user))

    @property
    def from_address(self) -> str:
        return self.sender or self.user


def load_settings() -> MailSettings:
    def _int(name: str, default: int) -> int:
        try:
            return int(os.environ.get(name, "") or default)
        except ValueError:
            return default

    return MailSettings(
        host=os.environ.get("DEALFLOW_SMTP_HOST", "").strip(),
        port=_int("DEALFLOW_SMTP_PORT", 587),
        user=os.environ.get("DEALFLOW_SMTP_USER", "").strip(),
        password=os.environ.get("DEALFLOW_SMTP_PASSWORD", ""),
        sender=os.environ.get("DEALFLOW_SMTP_FROM", "").strip(),
        use_tls=os.environ.get("DEALFLOW_SMTP_TLS", "1") != "0",
    )


def is_configured() -> bool:
    return load_settings().configured


def status() -> dict:
    """화면에 보여줄 설정 상태. 비밀번호는 있는지 없는지만 알린다."""
    s = load_settings()
    missing = []
    if not s.host:
        missing.append("메일 서버 주소")
    if not s.from_address:
        missing.append("보내는 주소")
    if s.host and not s.password and s.user:
        missing.append("비밀번호")
    return {
        "configured": s.configured,
        "host": s.host,
        "port": s.port,
        "from_address": s.from_address,
        "has_password": bool(s.password),
        "use_tls": s.use_tls,
        "missing": missing,
    }


def send_mail(to: str, subject: str, body: str,
              settings: Optional[MailSettings] = None) -> None:
    """평문 메일 한 통. 실패하면 그대로 예외를 올린다(조용히 삼키면 안 된다)."""
    s = settings or load_settings()
    if not s.configured:
        raise MailerNotConfigured(
            "메일 서버 정보가 없습니다. 관리자에게 메일 발송 설정을 요청하세요."
        )
    if not (to or "").strip():
        raise ValueError("받는 사람 메일 주소가 없습니다")

    msg = EmailMessage()
    msg["To"] = to.strip()
    msg["From"] = _format_sender(s.from_address)
    msg["Subject"] = subject
    msg.set_content(body)

    with smtplib.SMTP(s.host, s.port, timeout=20) as smtp:
        if s.use_tls:
            smtp.starttls()
        if s.user:
            smtp.login(s.user, s.password)
        smtp.send_message(msg)


def _format_sender(value: str) -> str:
    """'이름 <주소>' 형태를 그대로 두고, 주소만 있으면 그대로 쓴다."""
    if "<" in value and ">" in value:
        return value
    return formataddr(("", value))


def missing_addresses(contacts: List) -> List[str]:
    """메일로 보낼 수 없는 담당자 이름. 발송 전에 알려줘야 한다."""
    return [c.name for c in contacts if not (getattr(c, "email", "") or "").strip()]
