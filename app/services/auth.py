"""ID/PW 인증 — 로그인 ID 는 휴대폰번호(숫자만), 비밀번호는 해시로만 저장.

설계 메모
- 외부 SMS 발송(OTP)을 쓰지 않기로 해서 의존성·비용이 없다.
- 비밀번호는 **PBKDF2-HMAC-SHA256**(표준 라이브러리)로 해시한다. bcrypt/argon2 를
  쓰려면 패키지가 필요한데, 사내 7명 규모에서 의존성을 늘리기보다 표준 라이브러리로
  충분한 강도를 확보하는 편이 배포가 단순하다.
- 세션 토큰은 DB 에 저장하고 쿠키에는 토큰만 넣는다. 쿠키를 위조해도 서버가
  소유자를 판단하므로 '쿠키에 user_id 를 담던' 개발용 전환과 근본적으로 다르다.
  DB 에는 토큰 자체가 아니라 **sha256 값만** 둔다(0123).
"""
from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import threading
import time
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from .. import clock, config
from ..models import Session as SessionRow
from ..models import User

# 해시 파라미터. 반복 횟수를 올리면 기존 해시와 호환되도록 문자열에 함께 저장한다.
_ALGO = "pbkdf2_sha256"
_ITERATIONS = 260_000
SESSION_COOKIE = "dealflow_session"
SESSION_DAYS = 14


# --- 휴대폰번호 -------------------------------------------------------------

def normalize_phone(raw: Optional[str]) -> str:
    """휴대폰번호를 숫자만 남긴다.

    사용자가 '010-1234-5678' 로 입력해도 로그인되게 하려면 저장·비교 양쪽에서
    같은 규칙으로 정규화해야 한다(하이픈 유무로 로그인 실패하는 일 방지).
    """
    return re.sub(r"\D", "", raw or "")


# --- 비밀번호 ---------------------------------------------------------------

def hash_password(password: str, *, salt: Optional[str] = None,
                  iterations: int = _ITERATIONS) -> str:
    salt = salt or secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"),
                             salt.encode("utf-8"), iterations)
    return f"{_ALGO}${iterations}${salt}${dk.hex()}"


def verify_password(password: str, stored: Optional[str]) -> bool:
    """타이밍 공격을 피하려 compare_digest 로 비교한다."""
    if not stored:
        return False
    try:
        algo, iterations, salt, digest = stored.split("$", 3)
    except ValueError:
        return False
    if algo != _ALGO:
        return False
    calc = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"),
                               salt.encode("utf-8"), int(iterations))
    return hmac.compare_digest(calc.hex(), digest)


# 없는 번호로 들어올 때 견줄 해시. 모듈을 불러올 때 **한 번만** 만들어 두고, 없는
# 번호도 있는 번호와 같은 일(견주기 한 번)만 하게 한다.
_DUMMY_HASH = hash_password(secrets.token_urlsafe(16))


def password_problem(password: str) -> Optional[str]:
    """받아들일 수 없는 비밀번호면 사유를 돌려준다(통과하면 None)."""
    if len(password) < 8:
        return "비밀번호는 8자 이상이어야 합니다."
    if password.isdigit():
        return "숫자만으로는 사용할 수 없습니다."
    return None


# --- 인증 -------------------------------------------------------------------

def authenticate(db: OrmSession, phone: str, password: str) -> Optional[User]:
    """휴대폰번호 + 비밀번호 검증. 실패 사유는 밖으로 구분해 알리지 않는다.

    '없는 번호'와 '틀린 비밀번호'를 구분해 주면 어떤 번호가 가입돼 있는지
    알려주는 셈이므로 둘 다 같은 실패로 처리한다.
    """
    user = db.execute(
        select(User).where(User.phone == normalize_phone(phone))
    ).scalars().first()
    if user is None or not user.is_active:
        # 사용자가 없어도 있는 번호와 **똑같이 한 번만** 견준다(응답 시간이 같게).
        verify_password(password, _DUMMY_HASH)
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


# --- 로그인 시도 제한 -------------------------------------------------------
#
# 번호별·IP별로 15분 안에 5번 틀리면 그 번호(그 IP)를 15분 잠근다. 잠긴 동안에는
# 비밀번호를 견주지 않는다(해시 계산을 아낀다). 없는 번호도 똑같이 센다.
# 맞게 들어오면 그 번호의 실패만 지운다 — IP 쪽은 시간이 지나야 풀린다.
# shortcut: 워커가 하나라 메모리에 둔다(다시 뜨면 풀린다) — 워커를 늘리면 DB 로 옮길 것.
LOGIN_MAX_FAILS = 5
LOGIN_LOCK_SECONDS = 15 * 60
_limit_lock = threading.Lock()
_fails: dict = {}    # 열쇠 → 최근 15분 안에 틀린 시각들
_locked: dict = {}   # 열쇠 → 잠금이 풀리는 시각


def _attempt_keys(phone: str, ip: str) -> tuple:
    return (f"phone:{normalize_phone(phone)}", f"ip:{ip or ''}")


def login_locked(phone: str, ip: str, now: Optional[float] = None) -> bool:
    """이 번호나 이 IP 가 지금 잠겨 있는가."""
    now = time.monotonic() if now is None else now
    with _limit_lock:
        return any(_locked.get(k, 0) > now for k in _attempt_keys(phone, ip))


def note_login_failure(phone: str, ip: str, now: Optional[float] = None) -> list:
    """틀린 것을 센다. 이번에 새로 잠긴 열쇠들을 돌려준다(로그에 남기라고)."""
    now = time.monotonic() if now is None else now
    newly = []
    with _limit_lock:
        for key in _attempt_keys(phone, ip):
            recent = [t for t in _fails.get(key, ()) if now - t < LOGIN_LOCK_SECONDS]
            recent.append(now)
            if len(recent) >= LOGIN_MAX_FAILS:
                _locked[key] = now + LOGIN_LOCK_SECONDS
                _fails.pop(key, None)
                newly.append(key)
            else:
                _fails[key] = recent
        if len(_fails) + len(_locked) > 1000:
            # 번호가 많이 쌓여도 표가 끝없이 자라지 않게 지난 것을 걷는다.
            for key in [k for k, ts in _fails.items() if now - ts[-1] >= LOGIN_LOCK_SECONDS]:
                del _fails[key]
            for key in [k for k, until in _locked.items() if until <= now]:
                del _locked[key]
    return newly


def note_login_success(phone: str) -> None:
    with _limit_lock:
        _fails.pop(_attempt_keys(phone, "")[0], None)


def reset_login_limits() -> None:
    """검사가 매번 빈 상태에서 시작하게(`tests/conftest.py`)."""
    with _limit_lock:
        _fails.clear()
        _locked.clear()


# --- 세션 -------------------------------------------------------------------

def _now() -> datetime:
    """지금(오프셋 붙은 값).

    만료 판정은 `fromisoformat(expires_at) <= _now()` 로 **순간**끼리 견준다.
    양쪽 다 오프셋이 있으므로 저장값이 UTC 표기든 한국시간 표기든 결과가 같다
    — 옛 값이 섞여 있어도 세션이 일찍 끊기거나 늘어나지 않는다.
    """
    return clock.now()


def _token_key(token: str) -> str:
    """DB 에 두는 세션 열쇠 — 쿠키의 토큰이 아니라 그 sha256 값이다.

    토큰은 32바이트 난수라 소금이나 느린 해시가 필요 없다. 0123 이 옛 줄을 같은
    값으로 바꿨다(그래서 이주해도 아무도 로그아웃되지 않는다).
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_session(db: OrmSession, user: User, user_agent: str = "") -> str:
    """새 세션. 돌려주는 것은 **쿠키에 넣을 토큰**이고, DB 에는 그 해시만 남는다."""
    token = secrets.token_urlsafe(32)
    row = SessionRow(
        token=_token_key(token),
        user_id=user.id,
        # 초까지만 적는다 — 다른 시각 칸과 길이를 맞춘다(문자열로 견주는 자리가 있다).
        expires_at=(_now() + timedelta(days=SESSION_DAYS)).isoformat(timespec="seconds"),
        user_agent=(user_agent or "")[:200],
    )
    user.last_login_at = clock.now_iso()
    db.add(row)
    db.commit()
    return token


def set_session_cookie(response, token: str) -> None:
    """로그인 쿠키를 굽는다. **여기 한 곳에서만 굽는다.**

    로그인(`routers/auth.py`)과 되돌리기 뒤 세션 잇기(`routers/dashboard.py`)가
    각자 `max_age`·`httponly`·`samesite` 를 적어 두면 하나는 반드시 낡는다 —
    이 저장소가 같은 부류로 여러 번 당했다. 유효기간은 `SESSION_DAYS` 하나에서
    나온다. 비밀번호를 바꾼 뒤 새로 굽는 자리도 이 함수다.

    운영(https)에서는 `Secure` 를 붙여 https 로만 오가게 한다. 로컬·테스트
    서버는 http 라 붙이지 않는다(붙이면 로그인이 안 된다).
    """
    response.set_cookie(
        SESSION_COOKIE, token,
        max_age=60 * 60 * 24 * SESSION_DAYS,
        httponly=True, samesite="lax", secure=config.IS_PRODUCTION,
    )


def user_for_token(db: OrmSession, token: Optional[str]) -> Optional[User]:
    if not token:
        return None
    row = db.execute(
        select(SessionRow).where(SessionRow.token == _token_key(token))
    ).scalars().first()
    if row is None:
        return None
    try:
        if datetime.fromisoformat(row.expires_at) <= _now():
            db.delete(row)
            db.commit()
            return None
    except ValueError:
        return None
    user = db.get(User, row.user_id)
    if user is None or not user.is_active:
        return None
    return user


def destroy_session(db: OrmSession, token: Optional[str]) -> None:
    if not token:
        return
    row = db.execute(
        select(SessionRow).where(SessionRow.token == _token_key(token))
    ).scalars().first()
    if row:
        db.delete(row)
        db.commit()


def destroy_all_sessions(db: OrmSession, user_id: int) -> int:
    """비밀번호 변경·퇴사 처리 시 그 사용자의 모든 세션을 끊는다."""
    rows = db.execute(select(SessionRow).where(SessionRow.user_id == user_id)).scalars().all()
    for r in rows:
        db.delete(r)
    db.commit()
    return len(rows)
