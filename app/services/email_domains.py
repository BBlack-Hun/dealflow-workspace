"""메일 칸에 띄울 **도메인 후보를 고르는 한 곳**.

## 왜 도메인만인가

주소 자체는 후보가 못 된다. 이 저장소가 이미 재 보고 적어 둔 대로
(`templates/companies.html` 의 `이메일` 칸 주석) 채워져 있는 주소는 줄마다
다르다 — 목록에 뜨는 모든 후보가 **남의 주소**라, 눌리면 그 줄에 남의
연락처가 조용히 들어앉는다.

`@` 뒤는 다르다. 재 본 값:

    IR 기업 대표 메일   주소 247개 · 도메인 190가지
                       두 번 이상 쓰인 도메인 7가지에 주소 64개 (상위 35·17·4·2…)
    투자사 명단 메일    주소 753개 · 도메인 503가지
                       두 번 이상 쓰인 도메인 97가지에 주소 347개 (상위 40·31·13·8…)

투자사 쪽은 **절반 가까이**(347/753) 겹치는 도메인이다. 그래서 도메인만 띄운다.

## 어디를 자르나 — `두 번 이상`

190가지·503가지를 다 띄우면 고를 수가 없다. 자르는 선은 **두 번 이상 쓰인
도메인**이다.

`상위 N개` 로 안 자르는 이유: 꼬리가 길다(40·31·13·8… 로 완만하게 내려간다).
어디를 잘라도 근거가 없는 임의의 선이 되고, 명단이 늘면 그 선은 또 어긋난다.

`두 번 이상` 은 **뜻이 있는 선**이다 — 적어도 두 사람이 같은 도메인을 쓰고
있다는 말이고, 그것이 곧 "다음 사람도 그 도메인일 수 있다" 는 근거다. 한 번만
쓰인 도메인은 그 줄 하나의 도메인이라, 후보로 세워 봐야 위의 "남의 주소" 와
같은 거래가 된다 — 아껴 주는 타자는 없고 잘못 눌릴 일만 있다.

자른 사실은 **사람에게 말해 준다**(화면 쪽 `static/js/email_hint.js` 의 안내
줄). 안 말해 주면 자기 도메인이 안 뜨는 사람이 고장으로 여겨 목록을 뒤진다 —
그냥 쳐서 저장되는 칸인데도.

한 번에 **보이는** 개수를 더 줄이는 것은 화면 쪽 일이라 여기서 안 한다
(97가지가 한 번에 서면 역시 고를 수 없다 — 그쪽 주석 참고).

## 세는 자리가 여기 하나인 이유

이 목록을 만드는 코드는 이 파일뿐이고, 화면 둘(`companies.html` ·
`contacts.html`)이 그린 **같은 이름의 칸 하나**(`#opts-email-domain`)를 통해
받아 간다. 재료는 그 화면이 지금 그리고 있는 줄들(`rows`)이라, 표에 보이는 것과
후보가 갈릴 자리가 없다.
"""
from __future__ import annotations

import re
from collections import Counter
from typing import Iterable, List

# 몇 번 이상 쓰인 도메인을 후보로 세우나. 위 주석의 근거를 참고.
MIN_COUNT = 2

# 도메인에 허용하는 글자. 시트에서 옮겨 온 값이라 한글 설명·괄호·줄바꿈이
# 섞여 들어온 칸이 있다 — 그런 것이 후보 목록에 서면 눌리는 순간 저장된다.
_DOMAIN = re.compile(r"^[a-z0-9]([a-z0-9.-]*[a-z0-9])?$")

# 한 칸에 주소가 여럿 적힌 줄이 있다(`a@example.com / b@example.net`).
# 통째로 보면 마지막 하나만 세어져서, 실제로 두 번 쓰인 도메인이 한 번으로
# 밀려 후보에서 빠진다.
_SPLIT = re.compile(r"[,;/\s]+")


def domain_of(raw: str) -> str:
    """주소 한 개에서 `@` 뒤를 떼어 낸다. 도메인 같지 않으면 빈 글자.

    점이 없는 것은 버린다(`hong@` 를 치다 만 값 · 한글 메모가 섞인 칸).
    후보 목록은 **눌리면 그대로 저장되는 값**이라, 확신할 수 있는 것만 세운다.
    """
    text = str(raw or "").strip().lower()
    at = text.rfind("@")
    if at < 0:
        return ""
    domain = text[at + 1:].strip().strip(".")
    if "." not in domain or not _DOMAIN.match(domain):
        return ""
    return domain


def domain_options(emails: Iterable[str], *, min_count: int = MIN_COUNT) -> List[str]:
    """지금 화면에 있는 주소들에서 **띄울 도메인**을 골라 차례대로 돌려준다.

    차례는 많이 쓰인 것부터다(같은 수면 글자 차례). 사람이 칠 확률이 높은
    것이 위에 서야 `@` 만 치고 멈췄을 때 첫 줄에서 끝난다.

    주소가 하나도 없으면 빈 목록이다 — 화면은 그때 후보를 아예 안 띄우고
    보통 글자 칸으로 둔다(빈 상자가 뜨면 그게 무슨 뜻인지 매번 다시 읽어야 한다).
    """
    counts: Counter = Counter()
    for raw in emails:
        for token in _SPLIT.split(str(raw or "")):
            domain = domain_of(token)
            if domain:
                counts[domain] += 1
    picked = [(name, n) for name, n in counts.items() if n >= min_count]
    picked.sort(key=lambda item: (-item[1], item[0]))
    return [name for name, _n in picked]
