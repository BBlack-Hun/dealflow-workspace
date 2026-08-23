"""정적 파일 주소에 지문을 붙인다.

## 왜

CSS·JS 를 고쳐서 배포해도 브라우저는 갖고 있던 옛 파일을 계속 쓴다. 주소가
같으니 다시 받을 이유가 없기 때문이다. 실제로 숫자 칸 먹통을 고쳐 배포했는데
"아직 그대로" 라는 말을 들었다 — 서버는 고친 파일을 주고 있었고, 브라우저가
옛 것을 쓰고 있었다.

`Cache-Control: no-store` 로 매번 받게 할 수도 있지만, 그러면 화면을 열 때마다
CSS·JS 를 새로 받아 느려진다. 캐시는 두되 **파일이 바뀌면 주소가 바뀌게** 한다.

    /static/js/inline_edit.js?v=3f2a91c4

지문은 파일 내용에서 뽑는다. 배포 시각이나 버전 번호로 하면, 고쳤는데 버전을
안 올린 경우에 또 같은 일이 난다.

## 캐시는 얼마나

지문이 붙으므로 오래 잡아 둬도 안전하다 — 내용이 바뀌면 주소가 달라져
어차피 새로 받는다.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Dict

from . import config

# 파일 경로 → 지문. 한 번 읽고 기억한다(운영 중에는 파일이 바뀌지 않는다).
_CACHE: Dict[str, str] = {}


def fingerprint(rel_path: str) -> str:
    """`css/app.css` → 내용 해시 앞 8자. 파일이 없으면 빈 문자열."""
    if rel_path in _CACHE:
        return _CACHE[rel_path]

    path = Path(config.STATIC_DIR) / rel_path
    try:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()[:8]
    except OSError:
        digest = ""          # 없는 파일은 그냥 지문 없이 — 링크는 살려 둔다
    _CACHE[rel_path] = digest
    return digest


def asset(path: str) -> str:
    """템플릿에서 쓰는 함수. `asset('js/app.js')` → `/static/js/app.js?v=…`"""
    rel = path.lstrip("/")
    if rel.startswith("static/"):
        rel = rel[len("static/"):]
    mark = fingerprint(rel)
    return f"/static/{rel}" + (f"?v={mark}" if mark else "")


def reset() -> None:
    """기억해 둔 지문을 버린다. 테스트와 개발 중 다시 읽기용."""
    _CACHE.clear()
