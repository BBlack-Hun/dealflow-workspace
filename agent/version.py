"""발송 프로그램 버전.

`app/version.py` 와 **같은 값**이어야 한다. 각자 PC 로 zip 을 받아 돌리는
구조라 서버가 "지금 붙어 있는 게 어느 버전인가" 를 알아야 낡은 것을 짚어 줄
수 있다.

두 파일로 나뉜 이유는 zip 에 `app/` 이 들어가지 않기 때문이다 — 발송
프로그램은 서버 코드를 모른다. 값이 어긋나면 테스트가 잡는다
(`tests/test_version.py`).
"""
from __future__ import annotations

VERSION = "0.7.0"
