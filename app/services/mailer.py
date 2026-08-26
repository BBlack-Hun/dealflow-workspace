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
    DEALFLOW_SMTP_TLS=1        # 587: 접속 후 STARTTLS 로 암호화
    DEALFLOW_SMTP_SSL=1        # 465: 처음부터 SSL 로 접속 (호스팅 메일이 대개 이쪽)

포트 465 는 **처음부터 SSL** 이라 STARTTLS 와 방식이 다르다. 465 인데 STARTTLS 로
붙으면 손도 못 대고 끊긴다. 그래서 포트가 465 면 SSL 을 기본으로 본다.
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


# 처음부터 SSL 로 접속하는 표준 포트. STARTTLS(587) 와 방식이 다르다.
SSL_PORT = 465


@dataclass
class MailSettings:
    host: str = ""
    port: int = 587
    user: str = ""
    password: str = ""
    sender: str = ""
    use_tls: bool = True       # 접속 후 STARTTLS
    use_ssl: bool = False      # 처음부터 SSL

    @property
    def configured(self) -> bool:
        """정말 보낼 수 있는 상태인가.

        보내는 주소는 서버 주소만큼 중요하다 — 없으면 받는 쪽에서 스팸으로 걸린다.
        계정이 있는데 비밀번호가 없으면 로그인에서 막힌다. 그런 상태로 화면에서
        이메일을 고를 수 있게 하면, 고를 수 있는데 나가지 않는 상태가 된다.
        """
        if not (self.host and (self.sender or self.user)):
            return False
        return bool(self.password) if self.user else True

    @property
    def from_address(self) -> str:
        return self.sender or self.user


def load_settings() -> MailSettings:
    def _int(name: str, default: int) -> int:
        try:
            return int(os.environ.get(name, "") or default)
        except ValueError:
            return default

    port = _int("DEALFLOW_SMTP_PORT", 587)
    raw_ssl = os.environ.get("DEALFLOW_SMTP_SSL", "").strip()
    # 465 는 처음부터 SSL 이다. 적어 두지 않았어도 포트로 알 수 있으므로
    # 기본값을 그렇게 잡는다 — 잘못 잡으면 손도 못 대고 끊긴다.
    use_ssl = (raw_ssl == "1") if raw_ssl else (port == SSL_PORT)
    return MailSettings(
        host=os.environ.get("DEALFLOW_SMTP_HOST", "").strip(),
        port=port,
        user=os.environ.get("DEALFLOW_SMTP_USER", "").strip(),
        password=os.environ.get("DEALFLOW_SMTP_PASSWORD", ""),
        sender=os.environ.get("DEALFLOW_SMTP_FROM", "").strip(),
        # SSL 로 붙으면 STARTTLS 는 쓰지 않는다(같이 켜면 서버가 거부한다).
        use_tls=(not use_ssl) and os.environ.get("DEALFLOW_SMTP_TLS", "1") != "0",
        use_ssl=use_ssl,
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
        "use_ssl": s.use_ssl,
        "security": "SSL" if s.use_ssl else ("STARTTLS" if s.use_tls else "없음"),
        "user": s.user,
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

    with _connect(s) as smtp:
        if s.user:
            smtp.login(s.user, s.password)
        smtp.send_message(msg)


def _connect(s: MailSettings):
    """SSL(465) 과 STARTTLS(587) 는 붙는 방식이 다르다."""
    if s.use_ssl:
        return smtplib.SMTP_SSL(s.host, s.port, timeout=20)
    smtp = smtplib.SMTP(s.host, s.port, timeout=20)
    if s.use_tls:
        smtp.starttls()
    return smtp


def send_test(to: str) -> dict:
    """설정이 맞는지 한 통 보내 본다.

    비밀번호가 틀렸는지, 포트를 잘못 잡았는지는 **실제로 보내 봐야** 안다.
    실패 사유를 그대로 돌려준다 — 화면에서 무엇을 고쳐야 하는지 알아야 한다.
    """
    from .. import clock

    stamp = clock.now().strftime("%Y-%m-%d %H:%M")
    try:
        send_mail(to,
                  "[CONTACTVC ASSET] 메일 발송 설정 확인",
                  f"메일 발송 설정이 정상입니다.\n보낸 시각: {stamp}\n\n"
                  "이 메일이 보이면 카톡으로 받지 않는 투자사에게 메일로 보낼 수 있습니다.")
    except MailerNotConfigured as exc:
        return {"ok": False, "detail": str(exc)}
    except smtplib.SMTPAuthenticationError:
        return {"ok": False,
                "detail": "로그인에 실패했습니다 — 계정 또는 비밀번호를 확인하세요."}
    except (smtplib.SMTPException, OSError) as exc:
        return {"ok": False,
                "detail": f"메일 서버에 연결하지 못했습니다: {exc}"}
    return {"ok": True, "detail": f"{to} 로 보냈습니다. 받은 편지함을 확인하세요."}


def _format_sender(value: str) -> str:
    """'이름 <주소>' 형태를 그대로 두고, 주소만 있으면 그대로 쓴다."""
    if "<" in value and ">" in value:
        return value
    return formataddr(("", value))


def missing_addresses(contacts: List) -> List[str]:
    """메일로 보낼 수 없는 담당자 이름. 발송 전에 알려줘야 한다."""
    return [c.name for c in contacts if not (getattr(c, "email", "") or "").strip()]
