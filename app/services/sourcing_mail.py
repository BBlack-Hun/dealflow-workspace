"""딜 소싱 — **메일로 온 딜을 저절로 `딜 받음`** (POP3, 머리글만 읽는다).

딜 소싱 참여자 대부분은 그 달 딜을 회사 메일함으로 보낸다. 받고도 아무도 딜 소싱
화면의 `딜 받음` 을 안 누르면, 누가 이 달 딜을 줬는지 화면이 모른다(곧 들어올
소싱 리마인드 자동화 #277 은 이 표시가 없는 사람에게만 보낸다 — 이미 보낸 분께
"이번 달 딜 부탁드립니다" 가 가는 일이 된다). 여기서 받은 편지함의 **머리글만**
읽어 보낸 주소가 소싱 명단에 있으면 그 달 `딜 받음` 을 세운다
(`sourcing_receipts.record_from_mail` — 주소는 `email` · `firm` 칸 둘 다에서).

## 어느 편지함을 읽나 — 팀 현황 판, 없으면 환경변수

  1. **팀 현황 › 딜 소싱 메일 확인** 판에서 관리자가 넣은 값(`SourcingMailSetting`).
     비밀번호는 암호화해서만 둔다(`services/secret_box.py`). 판에서 끌 수도 있다.
  2. 판이 비어 있으면 서버 환경변수(저장소에 올라가지 않게 `.env` 에 둔다):

         DEALFLOW_POP3_HOST=pop3.example.com
         DEALFLOW_POP3_PORT=995          # 비우면 995 — 처음부터 SSL(POP3S)
         DEALFLOW_POP3_USER=deal@example.com
         DEALFLOW_POP3_PASSWORD=...

둘 다 비면 **꺼짐**이다 — 딜 소싱 화면에 `메일 확인 꺼짐 (서버 설정 없음)` 이
서고 아무것도 하지 않는다. 회사 메일은 IMAP 이 닫혀 있고 POP3 over SSL(995)만
열려 있어 POP3 를 쓴다.

## 읽기만 한다 — `TOP n 0`

  · **RETR 을 부르지 않는다.** 본문을 받지 않는다(받을 까닭이 없고, 어떤 메일
    서비스는 RETR 한 메일을 "가져간 메일" 로 쳐서 다른 POP 손님에게 다시 안
    보여 준다). `TOP n 0` 은 머리글만 준다.
  · **DELE 를 부르지 않는다.** 편지함에서 아무것도 지우지 않는다.
  · 본문도 머리글 원문도 저장하지 않는다. 남기는 것은 보낸 주소가 명단에 있을
    때의 날짜 · 잘린 제목 · Message-ID 뿐이다.
  · 비밀번호는 로그에도 화면에도 나가지 않는다. 실패 사유는 정해 둔 말로만
    적는다(서버 응답 원문을 화면에 싣지 않는다).

## 어디까지 읽나

POP3 는 번호 차례(대개 도착 차례)로 준다. 가장 새 것부터 거꾸로 읽다가 **이 달
1일보다 오래된 메일이 30통 연달아**(`OLDER_RUN`) 나오면 멈춘다. 한 통이 아니라
30통인 까닭은 차례가 날짜와 꼭 같지 않아서다(보낸 쪽 시계가 틀렸거나 늦게
배달됐거나). 그래도 끝없이 읽지 않게 `MAX_SCAN` 통에서 끊는다.

**이 달 메일만 센다.** 지난달 말일 밤에 온 메일은 지난달 몫이다 — 이 달 표시를
세우지 않는다. 메일은 표시를 **세우기만** 하고 거두지 않는다. 사람이 누른
표시도 그대로다.

## 언제 도나

  · **매일 18:00** — 하루 한 번 장부를 맞춘다. 딜 소싱(리마인드)은 달에 한
    번이어도 딜 메일은 아무 날에나 오므로, 날마다 봐야 화면의 `딜 받음` 이 하루
    넘게 늦지 않는다. (처음에는 15일 · 말일에만 돌았다 — 그때 남은 `mid` · `end`
    줄은 지금도 그 이름으로 그린다.)
  · 딜 소싱 화면의 [지금 메일 확인](관리자).
  · **(나중) 소싱 리마인드 30분 전** — 리마인드 자동화(#277)가 들어오면 그쪽이
    `register_remind_source` 로 "그날 리마인드가 나갈 시각" 을 알려 주기만 하면
    된다. 그러면 그 시각 30분 전에 한 번 더 본다(`slots_on`). 그 확인이 실패해도
    리마인드는 그대로 나가야 한다(fail-open — 리마인드 글이 "이미 전달 주셨다면
    넘겨 주셔도 됩니다" 로 끝나고, 막으면 비밀번호가 바뀐 날부터 리마인드가
    조용히 멎는다). 실패는 오늘 할 일에 "리마인드는 그대로 나갑니다" 로 선다.

정해진 회차는 `(날, 회차)` 마다 한 번이다(`SourcingMailCheck.run_key` 유일 색인
— 자리를 먼저 잡고 돈다. 매일 회차의 열쇠는 `2026-10-15:daily`). 18시 회차는
서버가 그 시각에 멈춰 있었으면 그날 안에 늦게라도 돈다 — 읽기만 하는 일이라
늦어도 해가 없다. 하루를 통째로 놓쳐도 다음 날 회차가 이 달 1일부터 다시 읽어
메운다. 단 달이 바뀐 뒤에는 새 달 메일만 본다 — 말일 18시 뒤에 온 메일은
지난달 표시로 서지 않는다(새 달 표시도 세우지 않는다).

## 알림 — 알릴 일이 있을 때만

날마다 도는 확인이 날마다 "변화 없음" 을 올리면 아무도 안 읽게 된다. 그래서
정해진 회차가 끝나도 **새로 `딜 받음` 이 섰거나 실패했을 때만** 알린다
(`should_announce` · `today_items`):

  · 새로 선 분이 있다 → 관리자의 오늘 할 일에 `메일 확인 · 새로 딜 받음 N명`
    (오늘 · 어제 회차), 그리고 메일 설정(SMTP)이 있으면 자동 회차 알림과 같은
    곳(`send_guard.mail_admins`)으로 짧은 요약 한 통.
  · 실패 → 오늘 할 일에 고칠 때까지 사유 한 줄. 메일은 **새로 실패한 때만** —
    바로 앞 확인도 같은 사유로 실패했으면 날마다 다시 보내지 않는다(리마인드 전
    회차의 실패는 "리마인드는 그대로 나갑니다" 를 알려야 하므로 늘 보낸다).
  · 아무도 새로 안 섰다 → 어디에도 안 선다. 딜 소싱 화면 머리 줄의 `마지막`
    시각만 바뀐다.

서버에는 텔레그램 연동이 없어 텔레그램은 보내지 않는다.
"""
from __future__ import annotations

import email.utils
import hashlib
import logging
import os
import poplib
import re
import ssl
import threading
import time as _time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from email.header import decode_header
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import clock
from ..db import SessionLocal
from ..models import SourcingContact, SourcingMailCheck, SourcingMailSetting, User
from . import secret_box, sourcing_receipts

log = logging.getLogger(__name__)

ENV_HOST = "DEALFLOW_POP3_HOST"
ENV_PORT = "DEALFLOW_POP3_PORT"
ENV_USER = "DEALFLOW_POP3_USER"
ENV_PASSWORD = "DEALFLOW_POP3_PASSWORD"

#: POP3 over SSL 의 표준 포트. 회사 메일은 이것만 열려 있다.
DEFAULT_PORT = 995
#: 접속 · 명령 하나를 기다리는 초.
TIMEOUT_SEC = 30
#: 이 달 1일보다 오래된 메일이 **연달아** 몇 통이면 멈추나(머리말 `어디까지`).
OLDER_RUN = 30
#: 한 번에 머리글을 읽는 최대 통수 — 큰 편지함에서 끝없이 돌지 않게.
MAX_SCAN = 3000
#: 남기는 제목 길이.
SUBJECT_MAX = 120
#: 매일 회차의 시각(이 프로세스 시간대 — 서버는 `TZ=Asia/Seoul` 이라 한국 시간).
CHECK_TIME = "18:00"
#: 리마인드 몇 분 전에 보나.
PRE_REMIND_LEAD_MIN = 30
#: 실이 깨어나는 간격(5분) — 하루 한 번 서는 일이라 촘촘할 까닭이 없다.
CHECK_INTERVAL_SEC = 5 * 60
#: `running` 으로 이보다 오래 서 있는 줄은 죽은 것으로 본다(서버가 그 사이 멈췄다).
STALE_MIN = 15

#: 매일 `CHECK_TIME` 회차.
SLOT_DAILY = "daily"
#: 처음에는 15일 · 말일에만 돌았다 — 이제 서지 않지만, 그때 남은 줄을 그리려고 둔다.
SLOT_MID = "mid"
SLOT_END = "end"
SLOT_PRE = "pre_remind"
SLOT_MANUAL = "manual"
#: 팀 현황의 [연결 시험] — 편지함을 훑지 않는다(로그인 · STAT 만).
SLOT_TEST = "test"
SLOT_LABELS = {
    SLOT_DAILY: "매일 회차",
    SLOT_MID: "15일 회차",
    SLOT_END: "말일 회차",
    SLOT_PRE: "리마인드 전 회차",
    SLOT_MANUAL: "지금 메일 확인",
    SLOT_TEST: "연결 시험",
}
#: 사람이 누르지 않고 저절로 돈 회차 — 오늘 할 일 · 요약 메일이 보는 것(지난
#: 15일 · 말일 줄 포함).
SCHEDULED_SLOTS = (SLOT_DAILY, SLOT_PRE, SLOT_MID, SLOT_END)

STATUS_RUNNING = "running"
STATUS_OK = "ok"
STATUS_FAILED = "failed"

OFF_TEXT = "메일 확인 꺼짐 (서버 설정 없음)"
OFF_BY_PANEL = "메일 확인 꺼짐 (팀 현황에서 꺼 둠)"
ERR_LOGIN = "로그인 거부 (POP3 사용 허용 여부·비밀번호 확인)"
ERR_CONNECT = "연결 안 됨 (호스트·포트 확인)"
ERR_TLS = "보안 연결 실패 (포트 995 · SSL 확인)"
ERR_DROPPED = "연결이 중간에 끊김 (잠시 뒤 다시 확인)"
ERR_TOP = "머리글을 읽지 못함 (서버가 TOP 명령을 지원하는지 확인)"
ERR_BOX = "편지함을 열지 못함 (POP3 사용 허용 여부 확인)"
ERR_BUSY = "다른 메일 확인과 겹침 (잠시 뒤 다시 확인)"
ERR_UNKNOWN = "알 수 없는 오류 (서버 기록 확인)"

_LOCK = threading.Lock()
_SCHEDULER: Optional[threading.Thread] = None


# ── 설정 ────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Settings:
    host: str = ""
    port: int = DEFAULT_PORT
    user: str = ""
    #: `repr` 에서 뺀다 — 설정을 통째로 로그에 찍는 날에도 새지 않게.
    password: str = field(default="", repr=False)
    #: 어디서 왔나 — `panel`(팀 현황) | `env`(서버 환경변수) | ``(없음).
    source: str = ""
    #: 판에서 켜 두었나(환경변수는 늘 켜짐).
    enabled: bool = True
    #: 값은 있는데 쓸 수 없는 까닭(저장된 비밀번호를 못 풂 등). 사람이 읽는 말.
    problem: str = ""

    @property
    def configured(self) -> bool:
        return bool(self.host and self.user and self.password)

    @property
    def active(self) -> bool:
        """정말 돌릴 상태인가 — 값이 다 있고, 켜져 있고, 문제가 없다."""
        return self.configured and self.enabled and not self.problem

    @property
    def off_text(self) -> str:
        if self.problem:
            return f"메일 확인 꺼짐 ({self.problem})"
        if self.configured and not self.enabled:
            return OFF_BY_PANEL
        return OFF_TEXT


def setting_row(db: Session) -> Optional[SourcingMailSetting]:
    return db.execute(
        select(SourcingMailSetting).order_by(SourcingMailSetting.id)
    ).scalars().first()


def _panel_in_use(row: Optional[SourcingMailSetting]) -> bool:
    return bool(row is not None and (row.host or row.username or row.password_enc))


def env_settings() -> Settings:
    raw_port = os.environ.get(ENV_PORT, "").strip()
    try:
        port = int(raw_port) if raw_port else DEFAULT_PORT
    except ValueError:
        port = DEFAULT_PORT
    host = os.environ.get(ENV_HOST, "").strip()
    user = os.environ.get(ENV_USER, "").strip()
    password = os.environ.get(ENV_PASSWORD, "")
    return Settings(host=host, port=port, user=user, password=password,
                    source="env" if (host or user or password) else "")


def load_settings(db: Session) -> Settings:
    """지금 쓸 편지함 — **팀 현황 판이 먼저**, 판이 비어 있으면 환경변수."""
    row = setting_row(db)
    if not _panel_in_use(row):
        return env_settings()
    password, problem = "", ""
    if row.password_enc:
        try:
            password = secret_box.open_(row.password_enc)
        except (secret_box.CannotOpen, secret_box.NoSecret):
            problem = "저장된 비밀번호를 풀 수 없음, 팀 현황에서 다시 입력"
    return Settings(host=(row.host or "").strip(), port=row.port or DEFAULT_PORT,
                    user=(row.username or "").strip(), password=password,
                    source="panel", enabled=bool(row.enabled), problem=problem)


def is_configured(db: Session) -> bool:
    """돌릴 상태인가(값이 다 있고 켜져 있다)."""
    return load_settings(db).active


_HOST = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9\-]{0,61}[A-Za-z0-9])?"
                   r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9\-]{0,61}[A-Za-z0-9])?)*$")


def save_settings(db: Session, *, host: str, port, username: str, password: str,
                  enabled: bool) -> SourcingMailSetting:
    """팀 현황 판의 [저장]. **못 받을 값이면 `ValueError`**(까닭이 화면에 간다).

    비밀번호 칸이 비어 있으면 **있던 비밀번호를 그대로 둔다**(화면은 비밀번호를
    되돌려 그리지 않으므로, 빈칸은 '안 바꿈' 이다). 새 비밀번호는 잠가서만
    담는다 — 잠글 열쇠가 서버에 없으면 `secret_box.NoSecret` 으로 거절한다(평문을
    두는 길은 없다). 커밋까지 한다.
    """
    host = (host or "").strip()
    username = (username or "").strip()
    if host and not _HOST.match(host):
        raise ValueError("서버 이름은 pop3.example.com 처럼 주소만 넣으세요(https:// · 포트 없이)")
    try:
        port_no = int(str(port).strip() or DEFAULT_PORT)
    except ValueError:
        raise ValueError("포트는 숫자로 넣으세요(보통 995)") from None
    if not 1 <= port_no <= 65535:
        raise ValueError("포트는 1~65535 사이로 넣으세요(보통 995)")
    if len(username) > 200:
        raise ValueError("계정이 너무 깁니다")
    if password and len(password) > 500:
        raise ValueError("비밀번호가 너무 깁니다")
    sealed = secret_box.seal(password) if password else None   # NoSecret 이면 여기서 멎는다
    row = setting_row(db)
    if row is None:
        row = SourcingMailSetting()
        db.add(row)
    row.host = host or None
    row.port = port_no
    row.username = username or None
    if sealed is not None:
        row.password_enc = sealed
    row.enabled = 1 if enabled else 0
    db.commit()
    return row


def clear_settings(db: Session) -> None:
    """판을 비운다 — 그 뒤로는 환경변수(`DEALFLOW_POP3_*`)를 쓴다. 커밋까지 한다."""
    row = setting_row(db)
    if row is not None:
        db.delete(row)
        db.commit()


# ── 머리글 읽기 ──────────────────────────────────────────────────────────────

@dataclass
class Header:
    """메일 한 통의 머리글 중 쓰는 것만."""

    number: int
    #: 보낸 주소(소문자). 못 읽으면 빈 글자.
    sender: str
    #: 보낸 날(이 프로세스 시간대). 못 읽으면 `None`.
    when: Optional[datetime]
    subject: str
    message_id: str


# 한국 메일이 붙이는 문자셋 이름들. 실제 글자는 거의 늘 cp949(euc-kr 의 확장)라
# euc-kr 로 풀면 '똠' 같은 글자에서 깨진다.
_KOREAN_CHARSETS = {"ks_c_5601-1987", "ks_c_5601", "ksc5601", "ks-c-5601-1987",
                    "euc-kr", "euc_kr", "euckr", "cp949", "uhc", "x-windows-949",
                    "windows-949", "korean"}


def _codec(charset: Optional[str]) -> str:
    name = (charset or "").strip().strip('"').lower()
    if name in _KOREAN_CHARSETS or name.replace("_", "-") in _KOREAN_CHARSETS:
        return "cp949"
    return name


def _text(raw: bytes, charset: Optional[str] = None) -> str:
    """바이트를 글자로. 적힌 문자셋 → utf-8 → cp949 → 깨진 글자는 `?`."""
    tries = ([_codec(charset)] if charset else []) + ["utf-8", "cp949"]
    for codec in tries:
        try:
            return raw.decode(codec)
        except (LookupError, UnicodeDecodeError):
            continue
    return raw.decode("utf-8", "replace")


def decode_value(raw: bytes) -> str:
    """머리글 값 하나를 사람이 읽는 글자로.

    `=?UTF-8?B?…?=` · `=?ks_c_5601-1987?B?…?=` 같은 인코딩 단어(RFC 2047)와,
    인코딩 없이 날것으로 실린 8비트 글자 둘 다 푼다. 못 풀면 날 글자 그대로.
    """
    text = _text(raw)
    if "=?" not in text:
        return " ".join(text.split())
    try:
        parts = decode_header(text)
    except Exception:  # noqa: BLE001 - 망가진 인코딩 단어 하나로 확인이 멎으면 안 된다
        return " ".join(text.split())
    out = []
    for part, charset in parts:
        if isinstance(part, str):
            out.append(part)
        elif charset is None:
            # 인코딩 단어 사이의 날 글자 — `decode_header` 가 raw-unicode-escape 로 싸 둔다.
            out.append(part.decode("raw-unicode-escape", "replace"))
        else:
            out.append(_text(part, charset))
    return " ".join("".join(out).split())


def raw_headers(lines: Sequence[bytes]) -> Dict[str, List[bytes]]:
    """`TOP n 0` 이 준 줄들 → 머리글 이름(소문자) → 값들(접힌 줄은 편다)."""
    out: Dict[str, List[bytes]] = {}
    last: Optional[str] = None
    for line in lines:
        if isinstance(line, str):
            line = line.encode("utf-8", "surrogateescape")
        line = line.rstrip(b"\r\n")
        if not line.strip():
            if out:
                break           # 머리글이 끝났다(본문은 `TOP n 0` 이라 오지 않는다)
            continue
        if line[:1] in (b" ", b"\t"):
            if last is not None:
                out[last][-1] = out[last][-1] + b" " + line.strip()
            continue
        name, sep, value = line.partition(b":")
        if not sep:
            last = None
            continue
        last = name.strip().lower().decode("ascii", "replace")
        out.setdefault(last, []).append(value.strip())
    return out


_ISO = re.compile(r"(\d{4})-(\d{1,2})-(\d{1,2})[T ](\d{1,2}):(\d{2})(?::(\d{2}))?")
# `2026. 10. 15. 오후 6:00` · `2026년 10월 15일 18:00` — 손으로 짠 메일 프로그램.
_KOREAN = re.compile(
    r"(\d{4})\s*[.\-/년]\s*(\d{1,2})\s*[.\-/월]\s*(\d{1,2})\s*[.일]?\s*"
    r"(?:(오전|오후|AM|PM|am|pm)\s*)?(?:(\d{1,2}):(\d{2})(?::(\d{2}))?)?")


def _local(value: datetime) -> Optional[datetime]:
    """이 프로세스 시간대로. 시간대가 없는 값은 이 프로세스 시간대(한국)로 본다."""
    if value.year < 1990 or value.year > 2100:
        return None
    try:
        return value.astimezone()
    except (OverflowError, OSError, ValueError):
        return None


def parse_date(raw: Optional[str]) -> Optional[datetime]:
    """`Date:` 값 → 시각(이 프로세스 시간대). 못 읽으면 `None`.

    표준(RFC 5322) 꼴이 대부분이지만 실제로는 섞여 온다 — 요일이 없거나, 초가
    없거나, 끝에 `(KST)` 같은 주석이 붙거나, `GMT`/`UT`/`-0000` 이거나, ISO
    꼴(`2026-10-15T18:00:00+09:00`)이거나, 한글(`2026. 10. 15. 오후 6:00`)이다.
    """
    text = " ".join((raw or "").split())
    if not text:
        return None
    cleaned = re.sub(r"\([^)]*\)", " ", text).strip()
    for candidate in dict.fromkeys((text, cleaned)):
        try:
            parsed = email.utils.parsedate_to_datetime(candidate)
        except (TypeError, ValueError, IndexError, OverflowError):
            parsed = None
        if parsed is not None:
            if parsed.tzinfo is None:
                # `-0000` — RFC 5322 에서 'UTC 인데 보낸 곳 시간대는 모름' 이다.
                parsed = parsed.replace(tzinfo=timezone.utc)
            return _local(parsed)
    try:
        return _local(datetime.fromisoformat(cleaned.replace("Z", "+00:00")))
    except ValueError:
        pass
    found = _ISO.search(cleaned)
    if found:
        y, mo, d, h, mi, s = (int(v or 0) for v in found.groups())
        try:
            return _local(datetime(y, mo, d, h, mi, s))
        except ValueError:
            return None
    found = _KOREAN.search(cleaned)
    if found:
        y, mo, d = (int(v) for v in found.groups()[:3])
        ampm, h, mi, s = found.group(4), found.group(5), found.group(6), found.group(7)
        hour = int(h or 0)
        if ampm in ("오후", "PM", "pm") and hour < 12:
            hour += 12
        if ampm in ("오전", "AM", "am") and hour == 12:
            hour = 0
        try:
            return _local(datetime(y, mo, d, hour, int(mi or 0), int(s or 0)))
        except ValueError:
            return None
    return None


def _sender(values: List[bytes]) -> str:
    for raw in values:
        text = _text(raw)
        for _name, address in email.utils.getaddresses([text]):
            if "@" in (address or ""):
                found = sourcing_receipts.addresses_in(address)
                if found:
                    return found[0]
        found = sourcing_receipts.addresses_in(text)
        if found:
            return found[0]
    return ""


def _received_at(values: List[bytes]) -> Optional[datetime]:
    """`Received:` 의 `; <날짜>` — `Date:` 를 못 읽을 때 우리 서버가 받은 시각."""
    for raw in values:
        text = _text(raw)
        if ";" in text:
            when = parse_date(text.rsplit(";", 1)[1])
            if when is not None:
                return when
    return None


def parse_header(number: int, lines: Sequence[bytes]) -> Header:
    heads = raw_headers(lines)
    sender = _sender(heads.get("from") or heads.get("sender") or [])
    when = None
    for raw in heads.get("date", []):
        when = parse_date(_text(raw))
        if when is not None:
            break
    if when is None:
        when = _received_at(heads.get("received", []))
    subject = decode_value(heads["subject"][0]) if heads.get("subject") else ""
    message_id = (_text(heads["message-id"][0]).strip()
                  if heads.get("message-id") else "")
    if not message_id:
        # Message-ID 가 없는 메일 — 보낸 주소 · 시각 · 제목으로 같은 메일을 알아본다.
        basis = f"{sender}|{when.isoformat() if when else ''}|{subject}"
        message_id = "<no-id-" + hashlib.sha1(basis.encode("utf-8")).hexdigest() + ">"
    return Header(number=number, sender=sender, when=when,
                  subject=subject[:SUBJECT_MAX], message_id=message_id[:300])


# ── 편지함 ───────────────────────────────────────────────────────────────────

class CheckError(Exception):
    """사람에게 보일 실패 사유. 서버 응답 원문 · 비밀번호를 담지 않는다."""


def _redact(value, settings: Settings) -> str:
    """로그에 실을 서버 응답 — 혹시 비밀번호가 섞여 있으면 `[비밀번호]` 로 바꾼다.

    (사람 · 회사 이름을 가리는 별표 규칙은 `ir_mask` 한 곳이다 — 여기는 다른 일이라
    별표를 쓰지 않는다.)
    """
    text = str(value)
    if settings.password:
        text = text.replace(settings.password, "[비밀번호]")
    return text[:200]


def _connect(settings: Settings):
    try:
        return poplib.POP3_SSL(settings.host, settings.port, timeout=TIMEOUT_SEC)
    except ssl.SSLError as exc:
        log.warning("메일 확인 — 보안 연결 실패 (%s:%s): %s", settings.host,
                    settings.port, type(exc).__name__)
        raise CheckError(ERR_TLS) from None
    except (OSError, poplib.error_proto) as exc:
        log.warning("메일 확인 — 연결 실패 (%s:%s): %s", settings.host,
                    settings.port, _redact(exc, settings))
        raise CheckError(ERR_CONNECT) from None


def fetch_headers(settings: Settings, since: datetime, *, older_run: int = OLDER_RUN,
                  max_scan: int = MAX_SCAN) -> Tuple[List[Header], int]:
    """편지함의 머리글을 새 것부터 — `since` 보다 오래된 메일이 `older_run` 통
    연달아 나오면 멈춘다. (머리글들, 읽은 통수).

    부르는 명령은 `USER` · `PASS` · `STAT` · `TOP n 0` · `QUIT` 뿐이다.
    """
    conn = _connect(settings)
    try:
        try:
            conn.user(settings.user)
            conn.pass_(settings.password)
        except poplib.error_proto as exc:
            log.warning("메일 확인 — 로그인 거부 (%s): %s", settings.user,
                        _redact(exc, settings))
            raise CheckError(ERR_LOGIN) from None
        except OSError as exc:
            log.warning("메일 확인 — 로그인 중 연결 끊김: %s", _redact(exc, settings))
            raise CheckError(ERR_DROPPED) from None
        try:
            count, _size = conn.stat()
        except poplib.error_proto as exc:
            log.warning("메일 확인 — STAT 실패: %s", _redact(exc, settings))
            raise CheckError(ERR_BOX) from None
        except OSError:
            raise CheckError(ERR_DROPPED) from None

        headers: List[Header] = []
        scanned = older = failures = 0
        for number in range(int(count), 0, -1):
            if scanned >= max_scan:
                log.warning("메일 확인 — %s통에서 끊습니다(더 오래된 메일은 안 봅니다)",
                            max_scan)
                break
            try:
                _resp, lines, _octets = conn.top(number, 0)
            except poplib.error_proto as exc:
                # 한 통이 그사이 지워졌을 수 있다. 첫 몇 통이 전부 안 되면 TOP 이 없는 서버다.
                failures += 1
                log.info("메일 확인 — %s번 머리글을 못 읽었습니다: %s", number,
                         _redact(exc, settings))
                if not scanned and failures >= 3:
                    raise CheckError(ERR_TOP) from None
                continue
            except OSError:
                raise CheckError(ERR_DROPPED) from None
            scanned += 1
            header = parse_header(number, lines)
            headers.append(header)
            if header.when is None:
                continue
            if header.when < since:
                older += 1
                if older >= older_run:
                    break
            else:
                older = 0
        if failures and not scanned:
            raise CheckError(ERR_TOP)
        return headers, scanned
    finally:
        try:
            conn.quit()     # DELE 를 하지 않았으므로 QUIT 은 아무것도 지우지 않는다
        except Exception:  # noqa: BLE001 - 끊는 자리의 실패는 결과를 바꾸지 않는다
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass


# ── 한 회 ────────────────────────────────────────────────────────────────────

def month_start(month: str) -> datetime:
    """`YYYY-MM` 의 1일 0시(이 프로세스 시간대)."""
    return datetime(int(month[:4]), int(month[5:7]), 1).astimezone()


def _who(row: SourcingContact) -> str:
    return f"{row.name}({row.firm})" if row.firm and "@" not in row.firm else row.name


def run_check(db: Session, row: SourcingMailCheck,
              settings: Optional[Settings] = None) -> SourcingMailCheck:
    """편지함을 한 번 훑어 `row` 를 채운다(이미 `running` 으로 서 있는 줄)."""
    settings = settings or load_settings(db)
    if not settings.active:
        return _finish(db, row, STATUS_FAILED, error=settings.off_text)
    try:
        headers, scanned = fetch_headers(settings, month_start(row.month))
    except CheckError as exc:
        row.scanned = 0
        return _finish(db, row, STATUS_FAILED, error=str(exc))
    except Exception as exc:  # noqa: BLE001 - 실이 죽으면 다음 회차가 조용히 멎는다
        log.error("메일 확인 — 예기치 못한 실패: %s", _redact(exc, settings))
        return _finish(db, row, STATUS_FAILED, error=ERR_UNKNOWN)

    book = sourcing_receipts.address_book(db)
    ours = [h for h in headers
            if h.sender and h.when is not None and h.sender in book
            and sourcing_receipts.month_of(h.when.date()) == row.month]
    # 이른 메일부터 — `메일 10/3` 은 그 달 **첫** 메일이다.
    ours.sort(key=lambda h: h.when)
    fresh: List[int] = []
    try:
        for header in ours:
            fresh += sourcing_receipts.record_from_mail(
                db, header.sender, header.when.date(), subject=header.subject,
                message_id=header.message_id,
                mail_at=header.when.isoformat(timespec="seconds"), book=book)
        db.flush()
    except IntegrityError:
        db.rollback()
        row = db.get(SourcingMailCheck, row.id) or row
        return _finish(db, row, STATUS_FAILED, error=ERR_BUSY)
    names = []
    for cid in fresh:
        person = db.get(SourcingContact, cid)
        if person is not None and _who(person) not in names:
            names.append(_who(person))
    row.scanned = scanned
    row.matched = len(ours)
    row.marked = len(fresh)
    row.detail = ", ".join(names)[:1000] or None
    log.info("메일 확인 — %s통 읽음, 명단에서 온 이 달 메일 %s통, 새로 딜 받음 %s줄",
             scanned, len(ours), len(fresh))
    return _finish(db, row, STATUS_OK)


def _finish(db: Session, row: SourcingMailCheck, status: str, *,
            error: str = "") -> SourcingMailCheck:
    row.status = status
    row.error = error or None
    row.finished_at = clock.now_iso()
    db.commit()
    return row


def _new_row(slot: str, now: datetime, *, run_key: Optional[str] = None,
             user_id: Optional[int] = None) -> SourcingMailCheck:
    return SourcingMailCheck(
        run_key=run_key, slot=slot, day=now.date().isoformat(),
        month=sourcing_receipts.month_of(now.date()), status=STATUS_RUNNING,
        started_at=now.isoformat(timespec="seconds"), user_id=user_id)


# ── 정해진 회차 ──────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Slot:
    key: str
    #: 이 시각부터 돈다.
    at: datetime
    #: 이 시각 전까지만(리마인드 전 회차 — 리마인드가 나간 뒤에는 쓸모가 없다).
    until: Optional[datetime] = None


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.astimezone()


def _at(day: date, hhmm: str) -> datetime:
    hour, minute = (int(part) for part in hhmm.split(":"))
    return datetime(day.year, day.month, day.day, hour, minute).astimezone()


#: **리마인드 전 회차의 고리.** `(db, 날) → 그날 소싱 리마인드가 나갈 시각 | None`.
#: 지금은 비어 있다 — 소싱 리마인드 자동화(#277)가 들어오면 그 모듈이 읽힐 때
#: `register_remind_source(...)` 한 줄로 단다. 그러면 그 시각 `PRE_REMIND_LEAD_MIN`
#: 분 전에 `pre_remind` 회차가 선다(실패해도 리마인드는 막지 않는다 — 머리말).
REMIND_SOURCES: List[Callable[[Session, date], Optional[datetime]]] = []


def register_remind_source(func: Callable[[Session, date], Optional[datetime]]):
    """리마인드 시각을 알려 줄 곳을 단다(같은 것을 두 번 달지 않는다)."""
    if func not in REMIND_SOURCES:
        REMIND_SOURCES.append(func)
    return func


def remind_times(db: Session, day: date) -> List[datetime]:
    out = []
    for source in list(REMIND_SOURCES):
        try:
            when = source(db, day)
        except Exception:  # noqa: BLE001 - 고리 하나 때문에 매일 회차가 멎으면 안 된다
            log.exception("메일 확인 — 리마인드 시각을 못 읽었습니다")
            continue
        if when is not None:
            out.append(_aware(when))
    return out


def slots_on(db: Session, day: date) -> List[Slot]:
    """그날의 정해진 회차들(시각 차례) — **날마다** `CHECK_TIME` 한 번, 그리고
    리마인드가 나가는 날이면 그 `PRE_REMIND_LEAD_MIN` 분 전에 한 번 더."""
    out: List[Slot] = [Slot(SLOT_DAILY, _at(day, CHECK_TIME))]
    for remind in remind_times(db, day):
        out.append(Slot(SLOT_PRE, remind - timedelta(minutes=PRE_REMIND_LEAD_MIN),
                        until=remind))
    return sorted(out, key=lambda s: s.at)


def due(db: Session, now: datetime) -> List[Slot]:
    now = _aware(now)
    return [s for s in slots_on(db, now.date())
            if s.at <= now and (s.until is None or now < s.until)]


def next_slot(db: Session, now: datetime, days: int = 2) -> Optional[Slot]:
    """다음 회차 — 매일 회차가 있어 늦어도 내일 안에 하나 선다."""
    now = _aware(now)
    for offset in range(days):
        for slot in slots_on(db, now.date() + timedelta(days=offset)):
            if slot.at > now:
                return slot
    return None


def run_key(slot: str, day: date) -> str:
    return f"{day.isoformat()}:{slot}"


def _claim(db: Session, slot: str, now: datetime) -> Optional[SourcingMailCheck]:
    """이 회차 자리를 잡는다. 이미 돈(도는) 회차면 `None`."""
    row = _new_row(slot, now, run_key=run_key(slot, now.date()))
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return None
    return row


def tick(db: Session, now: Optional[datetime] = None) -> List[SourcingMailCheck]:
    """때가 된 회차를 돈다. 설정이 없거나 꺼져 있으면 아무것도 안 한다."""
    if not is_configured(db):
        return []
    now = _aware(now or clock.now())
    slots = due(db, now)
    if not slots:
        return []
    if not _LOCK.acquire(blocking=False):
        return []           # [지금 메일 확인] 이 돌고 있다 — 다음에 깨어날 때 다시
    done = []
    try:
        for slot in slots:
            row = _claim(db, slot.key, now)
            if row is None:
                continue
            run_check(db, row)
            announce(db, row)
            done.append(row)
    finally:
        _LOCK.release()
    return done


# ── [지금 메일 확인] · [연결 시험] ───────────────────────────────────────────

def running(db: Session, now: Optional[datetime] = None) -> Optional[SourcingMailCheck]:
    """지금 도는 회(오래된 `running` 은 죽은 것으로 보고 뺀다)."""
    now = _aware(now or clock.now())
    since = (now - timedelta(minutes=STALE_MIN)).isoformat(timespec="seconds")
    return db.execute(
        select(SourcingMailCheck).where(SourcingMailCheck.status == STATUS_RUNNING,
                                        SourcingMailCheck.started_at >= since)
        .order_by(SourcingMailCheck.id.desc())
    ).scalars().first()


def start_manual(db: Session, user: User,
                 now: Optional[datetime] = None) -> Optional[SourcingMailCheck]:
    """관리자가 누른 확인 — 줄을 세우고 따로 띄운 실에서 돈다. 이미 돌고 있으면 `None`."""
    if not is_configured(db):
        return None
    now = _aware(now or clock.now())
    if _LOCK.locked() or running(db, now) is not None:
        return None
    row = _new_row(SLOT_MANUAL, now, user_id=user.id)
    db.add(row)
    db.commit()
    _spawn(row.id)
    return row


def _run_by_id(check_id: int) -> None:
    db = SessionLocal()
    try:
        with _LOCK:
            row = db.get(SourcingMailCheck, check_id)
            if row is not None and row.status == STATUS_RUNNING:
                run_check(db, row)
    except Exception:  # noqa: BLE001
        log.exception("메일 확인 — 실이 넘어졌습니다")
    finally:
        db.close()


def _spawn(check_id: int) -> None:
    """요청을 붙잡지 않게 따로 띄운 실에서. 검사는 이 함수를 바꿔 끼워 그 자리에서 돌린다."""
    threading.Thread(target=_run_by_id, args=(check_id,), daemon=True,
                     name="sourcing-mail").start()


def probe(settings: Settings) -> int:
    """로그인 → `STAT` → `QUIT`. 편지함의 메일 수. 실패면 `CheckError`."""
    conn = _connect(settings)
    try:
        try:
            conn.user(settings.user)
            conn.pass_(settings.password)
        except poplib.error_proto as exc:
            log.warning("메일 확인 — 연결 시험 로그인 거부 (%s): %s", settings.user,
                        _redact(exc, settings))
            raise CheckError(ERR_LOGIN) from None
        except OSError:
            raise CheckError(ERR_DROPPED) from None
        try:
            count, _size = conn.stat()
        except poplib.error_proto:
            raise CheckError(ERR_BOX) from None
        except OSError:
            raise CheckError(ERR_DROPPED) from None
        return int(count)
    finally:
        try:
            conn.quit()
        except Exception:  # noqa: BLE001
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass


def check_connection(db: Session, user: Optional[User] = None,
                    now: Optional[datetime] = None) -> SourcingMailCheck:
    """팀 현황의 [연결 시험] — 지금 설정으로 로그인 · STAT · 로그아웃만. 결과를 한 줄로 남긴다.

    편지함을 훑지 않는다(`딜 받음` 을 세우지 않는다). 결과 문장은
    `로그인 성공 · 메일 N통` 이거나 실패 사유 — 비밀번호는 어디에도 없다.
    """
    now = _aware(now or clock.now())
    settings = load_settings(db)
    row = _new_row(SLOT_TEST, now, user_id=user.id if user else None)
    db.add(row)
    db.commit()
    if not settings.configured or settings.problem:
        return _finish(db, row, STATUS_FAILED,
                       error=settings.problem or "서버 · 계정 · 비밀번호를 모두 넣으세요")
    try:
        count = probe(settings)
    except CheckError as exc:
        return _finish(db, row, STATUS_FAILED, error=str(exc))
    except Exception as exc:  # noqa: BLE001
        log.error("메일 확인 — 연결 시험 중 예기치 못한 실패: %s", _redact(exc, settings))
        return _finish(db, row, STATUS_FAILED, error=ERR_UNKNOWN)
    row.scanned = count
    row.detail = f"로그인 성공 · 메일 {count}통"
    return _finish(db, row, STATUS_OK)


def connection_text(row: Optional[SourcingMailCheck]) -> str:
    """[연결 시험] 결과 한 줄."""
    if row is None:
        return ""
    if row.status == STATUS_OK:
        return row.detail or "로그인 성공"
    return f"연결 실패: {row.error}"


# ── 화면 · 오늘 할 일 · 알림 ─────────────────────────────────────────────────

def stamp(value: Optional[str]) -> str:
    """`2026-10-15T18:00:12+09:00` → `10/15 18:00`."""
    if not value or len(value) < 16:
        return ""
    return f"{int(value[5:7])}/{int(value[8:10])} {value[11:16]}"


def day_stamp(value: Optional[str]) -> str:
    """`2026-10-15T…` → `10/15`."""
    if not value or len(value) < 10:
        return ""
    return f"{int(value[5:7])}/{int(value[8:10])}"


def _latest(db: Session, *statuses: str, slots: Optional[Sequence[str]] = None
            ) -> Optional[SourcingMailCheck]:
    """마지막 회 — [연결 시험] 은 편지함을 훑은 회가 아니라 기본으로 뺀다."""
    query = select(SourcingMailCheck).where(SourcingMailCheck.status.in_(statuses))
    if slots is None:
        query = query.where(SourcingMailCheck.slot != SLOT_TEST)
    else:
        query = query.where(SourcingMailCheck.slot.in_(list(slots)))
    return db.execute(query.order_by(SourcingMailCheck.id.desc())).scalars().first()


def page_status(db: Session, now: Optional[datetime] = None) -> dict:
    """딜 소싱 머리 줄 — `메일 확인: 마지막 10/15 18:00 · 이번 달 메일로 받은 분 N명 ·
    메일 주소 없는 분 M명` 과 실패 · 도는 중 · 다음 회차."""
    settings = load_settings(db)
    if not settings.active:
        return {"on": False, "off_text": settings.off_text}
    now = _aware(now or clock.now())
    month = sourcing_receipts.month_of(now.date())
    last_ok = _latest(db, STATUS_OK)
    latest = _latest(db, STATUS_OK, STATUS_FAILED)
    nxt = next_slot(db, now)
    failed = latest if latest is not None and latest.status == STATUS_FAILED else None
    return {
        "on": True,
        "last_label": stamp(last_ok.started_at) if last_ok else "",
        "mail_count": sourcing_receipts.mail_count(db, month),
        "no_address": sourcing_receipts.without_address(db),
        "failed": (f"메일 확인 실패: {failed.error}" if failed else ""),
        "failed_label": stamp(failed.started_at) if failed else "",
        "running": running(db, now) is not None,
        "next_label": (f"{stamp(nxt.at.isoformat())} ({SLOT_LABELS[nxt.key]})"
                       if nxt else ""),
    }


def panel(db: Session) -> dict:
    """팀 현황의 `딜 소싱 메일 확인` 판. **비밀번호는 싣지 않는다** — 있는지만."""
    row = setting_row(db)
    settings = load_settings(db)
    env = env_settings()
    tested = _latest(db, STATUS_OK, STATUS_FAILED, slots=[SLOT_TEST])
    return {
        "host": (row.host or "") if row else "",
        "port": (row.port or DEFAULT_PORT) if row else DEFAULT_PORT,
        "username": (row.username or "") if row else "",
        "has_password": bool(row and row.password_enc),
        "enabled": bool(row.enabled) if row else True,
        "in_use": settings.source,
        "env_configured": env.configured,
        "active": settings.active,
        "off_text": "" if settings.active else settings.off_text,
        "can_seal": secret_box.available(),
        "no_secret_text": secret_box.NO_SECRET_TEXT,
        "test_text": connection_text(tested),
        "test_ok": bool(tested and tested.status == STATUS_OK),
        "test_label": stamp(tested.started_at) if tested else "",
        "status": page_status(db) if settings.active else None,
    }


def _summary_line(db: Session, row: SourcingMailCheck) -> str:
    total = sourcing_receipts.mail_count(db, row.month)
    fresh = f"새로 딜 받음 {row.marked}명" + (f" — {row.detail}" if row.detail else "")
    return f"{fresh} · 이번 달 메일로 받은 분 {total}명 · 읽은 메일 {row.scanned}통"


def today_items(db: Session, user: User, now: Optional[datetime] = None) -> List[dict]:
    """관리자의 오늘 할 일 — **알릴 일이 있을 때만**(머리말 `알림`).

      · 마지막 확인이 실패했으면 고칠 때까지 그 사유 한 줄(날마다 실패해도 한 줄).
      · 정해진 회차가 새로 `딜 받음` 을 세웠으면 `메일 확인 · 새로 딜 받음 N명`
        — 18시 회차의 결과가 다음 날 아침 화면에도 보이도록 오늘 · 어제 회차.
      · 아무도 새로 안 선 회차는 싣지 않는다 — 매일 도는 확인이 매일 한 줄씩
        쌓이면 아무도 안 읽는다.
    """
    if user.role != "admin" or not is_configured(db):
        return []
    now = _aware(now or clock.now())
    days = {now.date().isoformat(), (now.date() - timedelta(days=1)).isoformat()}
    out: List[dict] = []
    latest = _latest(db, STATUS_OK, STATUS_FAILED)
    if latest is not None and latest.status == STATUS_FAILED:
        detail = f"{stamp(latest.started_at)} {SLOT_LABELS.get(latest.slot, '')}"
        if latest.slot == SLOT_PRE and latest.day == now.date().isoformat():
            detail += " — 소싱 리마인드는 그대로 나갑니다(메일로 이미 보낸 분께도 갈 수 있습니다)"
        else:
            detail += " — 고친 뒤 딜 소싱 화면의 [지금 메일 확인] 으로 다시 보세요"
        out.append({"level": "urgent", "title": f"메일 확인 실패: {latest.error}",
                    "detail": detail, "href": "/sourcing?tab=all", "count": None})
    rows = db.execute(
        select(SourcingMailCheck).where(
            SourcingMailCheck.day.in_(days),
            SourcingMailCheck.status == STATUS_OK,
            SourcingMailCheck.marked > 0,
            SourcingMailCheck.slot.in_(SCHEDULED_SLOTS))
        .order_by(SourcingMailCheck.id)
    ).scalars().all()
    for row in rows:
        total = sourcing_receipts.mail_count(db, row.month)
        detail = (f"{stamp(row.started_at)} ({SLOT_LABELS.get(row.slot, '')})"
                  + (f" — {row.detail}" if row.detail else "")
                  + f" · 이번 달 메일로 받은 분 {total}명 · 읽은 메일 {row.scanned}통")
        out.append({"level": "info", "title": f"메일 확인 · 새로 딜 받음 {row.marked}명",
                    "detail": detail, "href": "/sourcing?tab=all", "count": row.marked})
    return out


def summary(db: Session, row: SourcingMailCheck) -> Tuple[str, str]:
    """정해진 회차가 끝난 뒤 관리자에게 가는 짧은 메일 (제목, 본문)."""
    when = f"{stamp(row.started_at)} {SLOT_LABELS.get(row.slot, '')}".strip()
    if row.status == STATUS_FAILED:
        subject = f"[딜플로우] 딜 소싱 메일 확인 실패 — {row.error}"
        lines = [f"{when} 메일 확인이 실패했습니다: {row.error}"]
        if row.slot == SLOT_PRE:
            lines.append("소싱 리마인드는 그대로 나갑니다 — 메일로 이미 보낸 분께도 갈 수 있습니다.")
        lines.append("고친 뒤 딜 소싱 화면의 [지금 메일 확인] 으로 다시 보세요.")
        if row.slot != SLOT_PRE:
            lines.append("같은 사유로 날마다 실패해도 이 메일은 다시 보내지 않습니다"
                         " — 오늘 할 일에는 고칠 때까지 남습니다.")
    else:
        subject = f"[딜플로우] 딜 소싱 메일 확인 — 새로 딜 받음 {row.marked}명"
        lines = [f"{when} 메일 확인 결과", _summary_line(db, row)]
    lines.append("화면: /sourcing?tab=all")
    return subject, "\n".join(lines)


def _previous(db: Session, row: SourcingMailCheck) -> Optional[SourcingMailCheck]:
    """`row` 바로 앞의 끝난 확인 — [연결 시험] · 도는 중인 줄은 뺀다."""
    return db.execute(
        select(SourcingMailCheck).where(
            SourcingMailCheck.id < row.id,
            SourcingMailCheck.slot != SLOT_TEST,
            SourcingMailCheck.status.in_([STATUS_OK, STATUS_FAILED]))
        .order_by(SourcingMailCheck.id.desc())
    ).scalars().first()


def should_announce(db: Session, row: SourcingMailCheck) -> bool:
    """이 회차의 결과를 관리자에게 메일로 알릴 일인가(머리말 `알림`).

    정해진 회차만. 성공이면 새로 `딜 받음` 이 섰을 때만, 실패면 **새로 실패한
    때만**(바로 앞 확인이 같은 사유로 실패했으면 안 보낸다 — 비밀번호가 바뀐 채
    두면 날마다 같은 메일이 간다). 리마인드 전 회차의 실패는 늘 보낸다.
    """
    if row.slot not in SCHEDULED_SLOTS:
        return False
    if row.status == STATUS_OK:
        return bool(row.marked)
    if row.status != STATUS_FAILED:
        return False
    if row.slot == SLOT_PRE:
        return True
    before = _previous(db, row)
    return not (before is not None and before.status == STATUS_FAILED
                and before.error == row.error)


def announce(db: Session, row: SourcingMailCheck) -> None:
    """정해진 회차가 끝났다 — 알릴 일이면(`should_announce`) 메일 설정이 있을 때
    관리자에게 요약 한 통.

    오늘 할 일은 따로 적지 않는다 — 이 표를 그대로 읽는다(`today_items`).
    """
    if not should_announce(db, row):
        return
    from . import send_guard

    subject, body = summary(db, row)
    send_guard.mail_admins(subject, body)


# ── 실 ──────────────────────────────────────────────────────────────────────

def start_scheduler() -> None:
    """웹 프로세스 안에서 5분마다 깨어나 때가 된 회차를 본다.

    **설정이 없어도 실은 띄운다** — 편지함은 팀 현황 판에서 언제든 넣을 수 있어,
    넣은 뒤 컨테이너를 다시 띄워야 돈다면 넣어 두고 잊는 날이 온다. 설정이
    없으면 깨어나도 곧바로 돌아온다(`tick`).
    """
    global _SCHEDULER
    if _SCHEDULER is not None and _SCHEDULER.is_alive():
        return

    def loop() -> None:
        while True:
            _time.sleep(CHECK_INTERVAL_SEC)
            db = SessionLocal()
            try:
                tick(db)
            except Exception:  # noqa: BLE001
                log.exception("메일 확인 회차를 살피다 실패했습니다")
            finally:
                db.close()

    _SCHEDULER = threading.Thread(target=loop, daemon=True, name="sourcing-mail-tick")
    _SCHEDULER.start()
