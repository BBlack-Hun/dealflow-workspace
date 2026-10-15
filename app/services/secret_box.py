"""DB 에 넣는 비밀값을 **암호화해서** 둔다 — 지금은 딜 소싱 메일 확인의 POP3 비밀번호 하나.

## 왜 암호화하나

DB 파일은 여러 곳으로 간다 — 매일 백업(`/app/data/daily-*.db`), 옮길 때 뜨는
스냅숏(`scripts/db_snapshot.py`), 되돌리기 화면. 그 어느 사본이 새어도 회사 메일
비밀번호까지 같이 새면 안 된다. 그래서 열쇠는 **DB 밖**(서버 `.env`)에 두고,
DB 에는 그 열쇠로 잠근 글자(Fernet 토큰)만 남긴다.

## 열쇠는 어디서 오나

`.env` 의 비밀값에서 HKDF-SHA256 으로 뽑는다(값 그대로 쓰지 않는다 — 다른 쓰임과
갈라 두려고 `info` 를 붙인다).

  1. `DEALFLOW_SECRET_KEY` — 있으면 이것.
  2. 없으면 `DEALFLOW_AGENT_TOKEN` — **저장소 기본값이 아닐 때만.** 운영은 이 값이
     기본값이면 아예 뜨지 않으므로(`config.assert_ready`) 운영에는 늘 있다.
  3. 둘 다 없으면 **잠그지 않고 거절한다**(`NoSecret`). 평문으로 두는 길은 없다.

열쇠의 바탕값을 바꾸면 이미 넣어 둔 비밀번호는 풀리지 않는다(`CannotOpen`) —
화면이 "다시 입력하세요" 라고 말한다. 조용히 틀린 값으로 로그인하지 않는다.

## 무엇을 하지 않나

  · 풀어 낸 비밀번호를 로그 · 화면 · 응답에 싣지 않는다 — 부르는 쪽이 지킨다
    (`sourcing_mail.Settings.__repr__` 는 비밀번호를 뺀다).
  · 저장소 기본값(`agt_demo_token_sprint1`)으로는 잠그지 않는다 — 공개 저장소라
    아무나 아는 값이다.
"""
from __future__ import annotations

import base64
import os

from .. import config

ENV_SECRET = "DEALFLOW_SECRET_KEY"
ENV_AGENT_TOKEN = "DEALFLOW_AGENT_TOKEN"
#: HKDF 의 `info` — 이 열쇠를 다른 쓰임과 가른다. 바꾸면 넣어 둔 값이 안 풀린다.
_INFO = b"dealflow sourcing-mail password v1"


class NoSecret(RuntimeError):
    """잠글 열쇠의 바탕값이 서버에 없다."""


class CannotOpen(RuntimeError):
    """잠근 값을 풀 수 없다(열쇠가 바뀌었거나 값이 망가졌다)."""


NO_SECRET_TEXT = (f"서버에 비밀값({ENV_SECRET} 또는 기본값이 아닌 {ENV_AGENT_TOKEN})이 "
                  "없어 비밀번호를 저장하지 않았습니다. 서버 .env 에 넣은 뒤 다시 저장하세요")
CANNOT_OPEN_TEXT = "저장된 비밀번호를 풀 수 없습니다(서버 비밀값이 바뀜). 팀 현황에서 다시 입력하세요"


def _material() -> bytes:
    secret = os.environ.get(ENV_SECRET, "").strip()
    if secret:
        return secret.encode("utf-8")
    token = os.environ.get(ENV_AGENT_TOKEN, "").strip()
    if token and token != config.DEFAULT_AGENT_TOKEN:
        return token.encode("utf-8")
    raise NoSecret(NO_SECRET_TEXT)


def available() -> bool:
    try:
        _material()
    except NoSecret:
        return False
    return True


def _fernet():
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF

    key = HKDF(algorithm=hashes.SHA256(), length=32, salt=None,
               info=_INFO).derive(_material())
    return Fernet(base64.urlsafe_b64encode(key))


def seal(plain: str) -> str:
    """평문 → 잠근 글자. 열쇠가 없으면 `NoSecret`."""
    return _fernet().encrypt(plain.encode("utf-8")).decode("ascii")


def open_(sealed: str) -> str:
    """잠근 글자 → 평문. 못 풀면 `CannotOpen`(열쇠가 없으면 `NoSecret`)."""
    from cryptography.fernet import InvalidToken

    try:
        return _fernet().decrypt(sealed.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError, UnicodeError):
        raise CannotOpen(CANNOT_OPEN_TEXT) from None
