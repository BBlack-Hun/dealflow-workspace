"""추적 중인 파일에 실제 휴대폰 번호·이메일이 들어가지 않게 막는다.

## 왜 이 검사가 있나

저장소가 **공개**다. 명단에서 한 줄 붙여 넣는 실수 하나로 남의 번호·주소가 기록에
영영 남는다. GitHub 의 비밀값 검사는 서비스 토큰 모양만 잡고 번호·주소는 못 잡는다.

## 무엇을 가짜로 보나

- 휴대폰: `010` 다음 자리가 0·1 로 시작하는 번호(010-0000-0001, 010-1234-5678 …).
  일반 휴대폰 번호는 이 대역을 쓰지 않는다. **새 가짜 번호는 이 모양으로 쓴다.**
  이 모양이 아닌 기존 가짜 번호는 `KNOWN_FAKE_PHONES` 에 적어 두었다 — 늘리지 않는다.
- 이메일: 예시용으로 예약된 이름만 — `example.com`·`example.net`·`example.org`(와 그
  아래), `.example`·`.test`·`.invalid`·`.localhost` 로 끝나는 주소.

`git ls-files` 가 보여 주는 파일만 본다(커밋될 것). 바이너리는 건너뛴다.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

PHONE = re.compile(rb"(?<![0-9])01[016789][-. ]?[0-9]{3,4}[-. ]?[0-9]{4}(?![0-9])")
EMAIL = re.compile(rb"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
EXAMPLE_DOMAIN = re.compile(
    r"(?:^|\.)example\.(?:com|net|org)$|\.(?:example|test|invalid|localhost)$")

# 이 검사가 생기기 전부터 시험·문서에 있던 가짜 번호(2026-10-27 기준 전부).
# 새로 늘리지 말고 010-0xxx·010-1xxx 모양을 쓴다.
KNOWN_FAKE_PHONES = frozenset("""
01020000001 01020000002 01020000003 01020000004 01020000005 01020000006
01020000007 01020000009 01022220001 01022220002 01022223333 01033334444
01044445555 01055555555 01055556666 01066667777 01070000001 01070000002
01070000003 01070000007 01070000008 01070000009 01070000011 01070000013
01070000044 01070000055 01070000077 01077770000 01077770001 01077770002
01077770003 01077770009 01077778888 01080000001 01080000003 01080000005
01090000000 01090000001 01090000002 01090000003 01099990000 01099998888
01099999999
""".split())


def _tracked_text_files():
    if shutil.which("git") is None:
        pytest.skip("git 이 없다")
    try:
        out = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT,
                             capture_output=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("git 저장소 안이 아니다")
    for raw in out.split(b"\0"):
        if not raw:
            continue
        name = raw.decode("utf-8", "surrogateescape")
        try:
            data = (ROOT / name).read_bytes()
        except OSError:
            continue  # 지운 채 아직 커밋하지 않은 파일
        if b"\0" in data[:8192]:
            continue  # 바이너리
        yield name, data


def _where(name: str, data: bytes, pos: int) -> str:
    line = data.count(b"\n", 0, pos) + 1
    return f"{name}:{line}"


def _is_fake_phone(digits: str) -> bool:
    return (digits.startswith("010") and digits[3] in "01") or digits in KNOWN_FAKE_PHONES


def test_no_real_phone_numbers_in_tracked_files():
    found = []
    for name, data in _tracked_text_files():
        for m in PHONE.finditer(data):
            digits = re.sub(rb"[^0-9]", b"", m.group()).decode()
            if not _is_fake_phone(digits):
                # 기록(CI 로그)에 번호를 다시 남기지 않는다 — 끝 네 자리만 보인다.
                found.append(f"{_where(name, data, m.start())}  …{digits[-4:]}")
    assert not found, (
        "실제 휴대폰 번호처럼 보이는 값이 있습니다. 가짜 번호는 010-0000-0001 처럼 "
        "010 다음 자리를 0·1 로 쓰세요:\n  " + "\n  ".join(found))


def test_no_real_email_addresses_in_tracked_files():
    found = []
    for name, data in _tracked_text_files():
        for m in EMAIL.finditer(data):
            domain = m.group().decode().rsplit("@", 1)[1].lower()
            if not EXAMPLE_DOMAIN.search(domain):
                found.append(f"{_where(name, data, m.start())}  …@{domain}")
    assert not found, (
        "예시용이 아닌 이메일 주소가 있습니다. hong@example.com 처럼 예약된 "
        "예시 도메인을 쓰세요:\n  " + "\n  ".join(found))


# 걸려야 하는 번호는 이어 붙여 만든다 — 그대로 적으면 이 파일이 위 검사에 걸린다.
@pytest.mark.parametrize("text, ok", [
    ("010-0000-0001", True), ("010-1234-5678", True), ("01099998888", True),
    ("010-2345-" + "6789", False), ("011-234-" + "5678", False),
])
def test_the_phone_rule(text, ok):
    digits = re.sub(r"[^0-9]", "", text)
    assert bool(PHONE.fullmatch(text.encode())) and _is_fake_phone(digits) == ok


@pytest.mark.parametrize("domain, ok", [
    ("example.com", True), ("corp.example.com", True), ("b.example", True),
    ("example.invalid", True), ("notexample.com", False), ("example.co.kr", False),
    ("gmail.com", False),
])
def test_the_email_rule(domain, ok):
    assert bool(EXAMPLE_DOMAIN.search(domain)) == ok
