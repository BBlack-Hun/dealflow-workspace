"""딜 소싱 — **메일로 온 딜을 저절로 `딜 받음`** (POP3, 머리글만 읽는다).

딜 소싱 참여자 대부분은 그 달 딜을 회사 메일함으로 보낸다. 소싱 리마인드(A1)는
`딜 받음` 이 아닌 사람에게만 나가므로, 메일을 받고도 아무도 안 누르면 이미
보낸 사람에게 "이번 달 딜 부탁드립니다" 가 간다. 여기서 받은 편지함의
**머리글만** 읽어 보낸 주소가 소싱 명단에 있으면 그 달 `딜 받음` 을 세운다
(`sourcing_receipts.record_from_mail` — 주소는 `email` · `firm` 칸 둘 다에서).

설정은 환경변수로 준다(저장소에 올라가지 않게 `.env` 에 둔다):

    DEALFLOW_POP3_HOST=pop3.example.com
    DEALFLOW_POP3_PORT=995          # 비우면 995 — 처음부터 SSL(POP3S)
    DEALFLOW_POP3_USER=deal@example.com
    DEALFLOW_POP3_PASSWORD=...

호스트 · 계정 · 비밀번호 중 하나라도 비면 **꺼짐**이다 — 딜 소싱 화면에
`메일 확인 꺼짐 (서버 설정 없음)` 이 서고, 실도 뜨지 않고, 아무것도 하지 않는다.
회사 메일은 IMAP 이 닫혀 있고 POP3 over SSL(995)만 열려 있어 POP3 를 쓴다.

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

  · 매달 **15일 · 말일 18:00** — 보름마다 한 번 장부를 맞춘다.
  · **소싱 리마인드가 나가는 날, 그 시각 30분 전**(기본 11:00 → 10:30) — 아침
    (08시)에 선 리마인드 회차는 풀리는 순간 `딜 받음` 인 사람을 뺀다
    (`sourcing_remind.still_ok`). 그 전에 편지함을 한 번 보면 메일로 이미 보낸
    사람에게는 안 나간다. 리마인드가 꺼져 있으면 이 회차도 없다. 시각은 자동화
    판에서 고친 리마인드 시각을 따라간다.
  · 딜 소싱 화면의 [지금 메일 확인](관리자).

정해진 회차는 `(날, 회차)` 마다 한 번이다(`SourcingMailCheck.run_key` 유일 색인
— 자리를 먼저 잡고 돈다. `automation_runner._claim` 과 같은 방식). 18시 회차는
서버가 그 시각에 멈춰 있었으면 그날 안에 늦게라도 돈다 — 읽기만 하는 일이라
늦어도 해가 없다. 리마인드 전 회차는 리마인드 시각이 지나면 쓸모가 없어
건너뛴다.

## 리마인드 전 확인이 실패하면 — **리마인드는 그대로 나간다**

막지 않는다(fail-open). 까닭:
  · 리마인드 글 자체가 "이미 전달 주셨다면 이 메시지는 넘겨 주셔도 됩니다" 로
    끝난다 — 이미 보낸 사람이 한 통 더 받아도 사과할 일은 아니다.
  · 막으면 메일 비밀번호를 바꾼 날부터 리마인드가 **조용히** 멎는다. 한 달 치
    딜을 못 받는 쪽이 한 통 더 가는 쪽보다 훨씬 비싸다.
  · 사람이 누른 `딜 받음` 과 앞 회차(15일 등)에 메일로 선 표시는 그대로 빠진다
    — 놓치는 것은 그 사이에 온 메일뿐이다.
대신 오늘 할 일(관리자)과 딜 소싱 화면에 `메일 확인 실패: …` 가 서고, 리마인드
전 회차였으면 "리마인드는 그대로 나갑니다" 를 함께 적는다.

## 알림

정해진 회차가 끝나면 관리자의 오늘 할 일에 한 줄(`today_items`), 그리고 메일
설정(SMTP)이 있으면 자동 회차 알림과 같은 곳(`send_guard.mail_admins`)으로 짧은
요약 한 통. 서버에는 텔레그램 연동이 없어 텔레그램은 보내지 않는다.
"""
from __future__ import annotations

import calendar
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
from typing import Dict, List, Optional, Sequence, Tuple

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import clock
from ..db import SessionLocal
from ..models import SourcingContact, SourcingMailCheck, User
from . import sourcing_receipts

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
#: 15일 · 말일 회차의 시각.
CHECK_TIME = "18:00"
#: 리마인드 몇 분 전에 보나.
PRE_REMIND_LEAD_MIN = 30
#: 실이 깨어나는 간격 — 자동화 실(`automation_runner`)과 같다.
CHECK_INTERVAL_SEC = 5 * 60
#: `running` 으로 이보다 오래 서 있는 줄은 죽은 것으로 본다(서버가 그 사이 멈췄다).
STALE_MIN = 15

SLOT_MID = "mid"
SLOT_END = "end"
SLOT_PRE = "pre_remind"
SLOT_MANUAL = "manual"
SLOT_LABELS = {
    SLOT_MID: "15일 회차",
    SLOT_END: "말일 회차",
    SLOT_PRE: "리마인드 전 회차",
    SLOT_MANUAL: "지금 메일 확인",
}

STATUS_RUNNING = "running"
STATUS_OK = "ok"
STATUS_FAILED = "failed"

OFF_TEXT = "메일 확인 꺼짐 (서버 설정 없음)"
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

    @property
    def configured(self) -> bool:
        return bool(self.host and self.user and self.password)


def load_settings() -> Settings:
    raw_port = os.environ.get(ENV_PORT, "").strip()
    try:
        port = int(raw_port) if raw_port else DEFAULT_PORT
    except ValueError:
        port = DEFAULT_PORT
    return Settings(host=os.environ.get(ENV_HOST, "").strip(), port=port,
                    user=os.environ.get(ENV_USER, "").strip(),
                    password=os.environ.get(ENV_PASSWORD, ""))


def is_configured() -> bool:
    return load_settings().configured


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
    settings = settings or load_settings()
    if not settings.configured:
        return _finish(db, row, STATUS_FAILED, error=OFF_TEXT)
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


def last_day(day: date) -> int:
    return calendar.monthrange(day.year, day.month)[1]


def _remind_source(db: Session):
    """소싱 리마인드의 (설정 줄, 틀) — 꺼져 있으면 `None`."""
    from . import automation, automation_runner as runner

    row = automation.load(db, automation.SOURCING_REMIND)
    if not automation.is_on(row):
        return None
    runner._load_all()
    spec = runner.REGISTRY.get(automation.SOURCING_REMIND)
    return (row, spec) if spec is not None else None


def remind_at(db: Session, day: date, source=False) -> Optional[datetime]:
    """그날 소싱 리마인드가 나갈 시각 — 켜져 있고 그날이 회차일 때만."""
    source = _remind_source(db) if source is False else source
    if source is None:
        return None
    row, spec = source
    plan = spec.plan(db, row, day)
    return _aware(plan.at) if plan is not None else None


def slots_on(db: Session, day: date, source=False) -> List[Slot]:
    """그날의 정해진 회차들(시각 차례)."""
    out: List[Slot] = []
    evening = _at(day, CHECK_TIME)
    if day.day == 15:
        out.append(Slot(SLOT_MID, evening))
    if day.day == last_day(day):
        out.append(Slot(SLOT_END, evening))
    remind = remind_at(db, day, source)
    if remind is not None:
        out.append(Slot(SLOT_PRE, remind - timedelta(minutes=PRE_REMIND_LEAD_MIN),
                        until=remind))
    return sorted(out, key=lambda s: s.at)


def due(db: Session, now: datetime) -> List[Slot]:
    now = _aware(now)
    return [s for s in slots_on(db, now.date())
            if s.at <= now and (s.until is None or now < s.until)]


def next_slot(db: Session, now: datetime, days: int = 45) -> Optional[Slot]:
    now = _aware(now)
    source = _remind_source(db)
    for offset in range(days):
        for slot in slots_on(db, now.date() + timedelta(days=offset), source):
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
    """때가 된 회차를 돈다. 설정이 없으면 아무것도 안 한다."""
    if not is_configured():
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


# ── [지금 메일 확인] ─────────────────────────────────────────────────────────

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
    if not is_configured():
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


def _latest(db: Session, *statuses: str) -> Optional[SourcingMailCheck]:
    return db.execute(
        select(SourcingMailCheck).where(SourcingMailCheck.status.in_(statuses))
        .order_by(SourcingMailCheck.id.desc())
    ).scalars().first()


def page_status(db: Session, now: Optional[datetime] = None) -> dict:
    """딜 소싱 머리 줄 — `메일 확인: 마지막 10/15 18:00 · 이번 달 메일로 받은 분 N명 ·
    메일 주소 없는 분 M명` 과 실패 · 도는 중 · 다음 회차."""
    if not is_configured():
        return {"on": False, "off_text": OFF_TEXT}
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


def _summary_line(db: Session, row: SourcingMailCheck) -> str:
    total = sourcing_receipts.mail_count(db, row.month)
    fresh = f"새로 딜 받음 {row.marked}명" + (f" — {row.detail}" if row.detail else "")
    return f"{fresh} · 이번 달 메일로 받은 분 {total}명 · 읽은 메일 {row.scanned}통"


def today_items(db: Session, user: User, now: Optional[datetime] = None) -> List[dict]:
    """관리자의 오늘 할 일 — 정해진 회차의 결과(오늘 · 어제), 그리고 **마지막 확인이
    실패했으면** 고칠 때까지 그 사유 한 줄.

    18시 회차의 결과가 다음 날 아침 화면에도 보이도록 어제 것까지 싣는다.
    """
    if user.role != "admin" or not is_configured():
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
        select(SourcingMailCheck).where(SourcingMailCheck.day.in_(days),
                                        SourcingMailCheck.status == STATUS_OK,
                                        SourcingMailCheck.slot != SLOT_MANUAL)
        .order_by(SourcingMailCheck.id)
    ).scalars().all()
    for row in rows:
        out.append({"level": "info",
                    "title": f"메일 확인 · {stamp(row.started_at)} ({SLOT_LABELS.get(row.slot, '')})",
                    "detail": _summary_line(db, row), "href": "/sourcing?tab=all",
                    "count": row.marked or None})
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
    else:
        subject = f"[딜플로우] 딜 소싱 메일 확인 — 새로 딜 받음 {row.marked}명"
        lines = [f"{when} 메일 확인 결과", _summary_line(db, row)]
    lines.append("화면: /sourcing?tab=all")
    return subject, "\n".join(lines)


def announce(db: Session, row: SourcingMailCheck) -> None:
    """정해진 회차가 끝났다 — 메일 설정이 있으면 관리자에게 요약 한 통.

    오늘 할 일은 따로 적지 않는다 — 이 표를 그대로 읽는다(`today_items`).
    """
    if row.slot == SLOT_MANUAL:
        return
    from . import send_guard

    subject, body = summary(db, row)
    send_guard.mail_admins(subject, body)


# ── 실 ──────────────────────────────────────────────────────────────────────

def start_scheduler() -> None:
    """웹 프로세스 안에서 5분마다 깨어나 때가 된 회차를 본다.

    설정이 없으면 실 자체를 띄우지 않는다 — 문자 알림(`followup_sms`)과 같다.
    설정은 컨테이너를 다시 만들 때 읽히므로, 켜는 날에는 어차피 다시 뜬다.
    """
    global _SCHEDULER
    if not is_configured():
        log.info("메일 확인 설정이 없어 실을 띄우지 않습니다 (%s 등)", ENV_HOST)
        return
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
