"""ID/PW 인증 — 로그인 ID 는 휴대폰번호(숫자만), 비밀번호는 해시로만 저장.

설계 메모
- 외부 SMS 발송(OTP)을 쓰지 않기로 해서 의존성·비용이 없다.
- 비밀번호는 **PBKDF2-HMAC-SHA256**(표준 라이브러리)로 해시한다. bcrypt/argon2 를
  쓰려면 패키지가 필요한데, 사내 7명 규모에서 의존성을 늘리기보다 표준 라이브러리로
  충분한 강도를 확보하는 편이 배포가 단순하다.
- 세션 토큰은 DB 에 저장하고 쿠키에는 토큰만 넣는다. 쿠키를 위조해도 서버가
  소유자를 판단하므로 '쿠키에 user_id 를 담던' 개발용 전환과 근본적으로 다르다.
"""
from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from .. import clock
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
        # 사용자가 없어도 해시 계산을 한 번 수행해 응답 시간 차이를 줄인다.
        verify_password(password, hash_password("dummy"))
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


# --- 세션 -------------------------------------------------------------------

def _now() -> datetime:
    """지금(오프셋 붙은 값).

    만료 판정은 `fromisoformat(expires_at) <= _now()` 로 **순간**끼리 견준다.
    양쪽 다 오프셋이 있으므로 저장값이 UTC 표기든 한국시간 표기든 결과가 같다
    — 옛 값이 섞여 있어도 세션이 일찍 끊기거나 늘어나지 않는다.
    """
    return clock.now()


def create_session(db: OrmSession, user: User, user_agent: str = "") -> str:
    token = secrets.token_urlsafe(32)
    row = SessionRow(
        token=token,
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
    나온다.
    """
    response.set_cookie(
        SESSION_COOKIE, token,
        max_age=60 * 60 * 24 * SESSION_DAYS,
        httponly=True, samesite="lax",
    )


def user_for_token(db: OrmSession, token: Optional[str]) -> Optional[User]:
    if not token:
        return None
    row = db.execute(select(SessionRow).where(SessionRow.token == token)).scalars().first()
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
    row = db.execute(select(SessionRow).where(SessionRow.token == token)).scalars().first()
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
