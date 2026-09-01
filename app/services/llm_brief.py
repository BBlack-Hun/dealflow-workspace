"""딜 소개 상대를 맞추는 데 쓸 자료 — **꺼내기만** 한다.

왜 꺼내기만 하는가
------------------
매주 "딜 소개할 기업 N곳" 을 고르는 일을 앱 밖 스크립트가 **낱말을 세어**
하고 있었다. `딥테크`·`AI`·`초기` 를 사전에 적어 두고 몇 번 나오는지 센다.
사전에 없는 말은 안 잡혀서 `콘텐츠`·`에듀테크`·`프롭테크` 를 손으로 계속
더해야 했고, **"규모가 좀 더 큰 곳 위주로"** 같은 문장은 아예 못 읽는다.
낱말 사전은 앞으로도 계속 모자랄 것이다 — 사람이 쓰는 말이 사전보다 넓다.

그래서 **맞추는 일은 LLM 에 맡기고 앱은 자료만 꺼낸다.** 여기에 점수·추천·
정렬을 넣으면 사전을 세던 때와 같은 자리로 돌아온다 — 앱이 먼저 걸러 낸
것은 LLM 이 볼 수조차 없기 때문이다. 이 파일에 판단이 없는 것이 요점이다.

왜 투자사는 번호로만 나가는가
-----------------------------
이 자료는 **앱 밖으로**(다른 LLM 서비스로) 나간다. 투자사 담당자의 이름·
투자사명·연락처·이메일·카톡방 이름은 맞추는 데 필요 없다 — 무엇을 좋아하고
어느 라운드를 보는지만 있으면 된다. 필요 없는 것을 내보내지 않는 것이
가장 확실한 보호다.

번호(`V-31`)는 **되찾을 수 있는 열쇠**다. LLM 이 `V-31` 로 답해 오면
`resolve()` 가 앱 안에서 다시 이름으로 바꾼다 — 그 길이 없으면 번호로
내보내는 순간 답을 못 쓴다.

**IR 기업은 이름을 넣는다.** 소개하려고 모아 둔 자료라 이름이 없으면 읽히지
않고, 어차피 딜소개 문구에 실려 투자사에게 그대로 나가는 이름이다.
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional
from urllib.parse import quote

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import clock
from ..models import IrCompany, User
from . import sheet_owner
# 방이 살아 있는지는 **대시보드가 세는 그 판정**을 그대로 쓴다. 여기에 다시
# 적으면 화면 숫자와 어긋난다 — 투자사 관리 현황 117명 · 대시보드 123명으로
# 갈렸던 사고가 판정을 두 벌로 적어 둔 탓이었다(`readiness.py` 도 같은 것을
# 읽는다). 밑줄로 시작하지만 이 저장소에서는 이미 공유되는 판정이다.
from .dashboard import _SENDABLE_ROOM, _room_state

# 번호 앞에 붙는 글자. 투자사와 기업이 섞여 오므로 무엇의 번호인지가 필요하다.
INVESTOR_PREFIX = "V"
COMPANY_PREFIX = "C"

# 저장은 백만원이다(`IrCompany` 참고). 화면은 억으로 보여주지만 여기서는
# **바꾸지 않고 단위만 밝힌다** — 두 표기를 같이 내보내면 언젠가 둘이
# 어긋나고, 어긋난 쪽을 읽은 답은 100배가 틀어진 채 돌아온다.
AMOUNT_UNIT = "백만원"

NOTE = ("투자사는 이름 없이 번호로만 나갑니다. 답하실 때 V-… · C-… 를 그대로 "
        "적어 주시면 앱에서 누구인지 다시 찾을 수 있습니다. "
        f"금액 단위는 {AMOUNT_UNIT} 입니다.")


def investor_ref(contact_id: int) -> str:
    return f"{INVESTOR_PREFIX}-{contact_id}"


def company_ref(company_id: int) -> str:
    return f"{COMPANY_PREFIX}-{company_id}"


# `V-031` · `v-31` · `C - 7` 을 모두 같은 번호로 읽는다.
#
# **자릿수를 채우지 않는다.** `V-031` 로 내보내면 번호가 1000 을 넘는 순간
# 같은 사람을 가리키는 표기가 둘이 된다(`V-031` 과 `V-1000` 은 폭이 다르다).
# 대신 **읽을 때 앞의 0 을 버려서** 어느 쪽으로 답해 와도 찾아 준다.
#
# **맨숫자(`31`)는 일부러 안 받는다.** 답에는 `30억` · `3곳` · `2026년` 처럼
# 번호가 아닌 숫자가 널려 있다. 그것까지 번호로 읽으면 엉뚱한 사람이 목록에
# 뜨고, 그 목록은 겉보기에 멀쩡하다 — 틀린 것을 알아채기 어려운 쪽이 나쁘다.
_REF = re.compile(rf"(?<![0-9A-Za-z])([{INVESTOR_PREFIX}{COMPANY_PREFIX}])"
                  r"\s*-\s*0*(\d+)", re.IGNORECASE)


def parse_refs(text: str) -> Dict[str, List[int]]:
    """붙여 넣은 글에서 번호만 골라낸다 — `{"investors": [...], "companies": [...]}`.

    사람은 LLM 의 답을 **통째로** 붙여 넣는다("V-031 님께 C-7, C-12 를 …").
    번호만 뽑아 달라고 하면 손으로 옮겨 적다 틀린다. 순서는 나온 순서대로
    두되 같은 번호는 한 번만 담는다 — 한 답 안에서 같은 사람이 여러 번
    거론되는 것은 흔한 일이고, 그때마다 줄이 늘면 읽기 어렵다.
    """
    found: Dict[str, List[int]] = {"investors": [], "companies": []}
    for prefix, digits in _REF.findall(text or ""):
        key = "investors" if prefix.upper() == INVESTOR_PREFIX else "companies"
        number = int(digits)
        if number and number not in found[key]:
            found[key].append(number)
    return found


# ── 내보내는 칸 ─────────────────────────────────────────────────────────────
#
# **여기 적힌 것만 나간다.** 모델의 칸을 통째로 훑어 내보내면 칸이 하나 늘
# 때마다 조용히 같이 나가고, 그중 하나가 이름이면 그게 곧 유출이다.
# `tests/test_llm_brief.py` 가 여기 없는 칸에 표식을 심어 두고 결과에 그
# 표식이 섞여 나오는지 본다 — 칸이 늘어도 검사가 먼저 걸린다.
INVESTOR_FIELDS = ("sectors", "round_size", "stages",
                   "sourcing_note", "memo", "tips_note", "interest_level")
COMPANY_FIELDS = ("name", "sector_major", "series", "one_liner", "summary",
                  "revenue_recent", "funding_total", "raise_target", "pre_value")


# ── 자유 문장에 섞여 든 이름·연락처 ────────────────────────────────────────
#
# 칸을 고르는 것만으로는 부족하다. **메모 안에 그대로 적혀 있는** 경우가 있다.
# 실데이터 274곳을 꺼내 훑어 보니 4곳의 메모에 자기 투자사명·연락처·이메일이
# 문장째 들어 있었고("○○벤처스 이사님", "010-… 로 연락 요망"), 전화번호 모양이
# 2곳, 이메일 모양이 1곳에 있었다. 칸만 막으면 이것이 그대로 나간다 — 번호로만
# 내보내는 뜻이 그 한 줄에서 사라진다.
#
# **그 줄 자신의 값만 지운다.** 남의 이름까지 전부 지우려면 300여 명의 값을
# 300여 줄에 다 대 봐야 하는데, 담당자 이름·직함은 두세 글자라 멀쩡한 문장이
# 통째로 뭉개진다(실제로 세 글자 담당자 이름이 남의 메모 261곳에 우연히
# 들어맞았다). 지켜야 하는 것은 **이 줄이 누구인지 알아볼 수 없는 것**이므로,
# 그 줄을 가리키는 값만 지우면 번호로 내보내는 뜻이 유지된다.
IDENTIFYING_FIELDS = ("kakao_room_name", "firm", "name", "email",
                      "phone", "office_phone", "office_fax")

# 지운 자리는 **비우지 않고 표시한다.** 그냥 빼면 "이사님과 통화" 처럼 문장이
# 멀쩡해 보여서, 뭔가 지워졌다는 것을 읽는 쪽도 사람도 알 수 없다.
MASK = "[가림]"

# 값이 어느 칸에도 없이 문장에만 있는 연락처. 누구 것이든 나가면 안 된다.
_PHONE = re.compile(r"0\d{1,2}[-.\s]?\d{3,4}[-.\s]?\d{4}")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")


def _scrub(text: str, row=None) -> str:
    """문장에서 그 줄을 알아볼 수 있는 것을 지운다.

    **날짜는 건드리지 않는다**(`8/19 : 초기 기업보다는…`). 언제 들은 요청인지가
    그 자체로 정보라 사람이 남겨 달라고 못 박은 자리다 — 여기서 지우는 것은
    이름·투자사명·연락처·이메일·카톡방 이름뿐이다.

    긴 값부터 지운다. 카톡방 이름이 대개 투자사명을 품고 있어서(`○○벤처스
    Deal 공유`), 짧은 쪽을 먼저 지우면 방 이름의 나머지가 남는다.
    """
    for value in sorted(
            {(getattr(row, f, None) or "").strip() for f in IDENTIFYING_FIELDS},
            key=len, reverse=True):
        # 한 글자짜리 값으로 지우기 시작하면 멀쩡한 문장이 통째로 뭉개진다.
        if len(value) >= 2:
            text = text.replace(value, MASK)
    text = _PHONE.sub(MASK, text)
    return _EMAIL.sub(MASK, text)


def _fill(row, fields, scrub_with=None) -> dict:
    """값이 있는 칸만 담는다.

    투자사 300여 명 중 소싱메모·팁스메모가 든 사람은 소수다. 빈 칸을 전부
    `null` 로 채우면 자료의 절반이 빈 칸 이름이 되어, 읽는 쪽이 실제 내용을
    그 사이에서 찾아야 한다. **날짜가 붙은 메모(`8/19 : 초기 기업보다는…`)는
    다듬지 않고 그대로 담는다** — 언제 들은 요청인지가 그 자체로 정보다.
    """
    out = {}
    for field in fields:
        value = getattr(row, field, None)
        if isinstance(value, str):
            value = _scrub(value.strip(), scrub_with)
        if value not in (None, "", 0):
            out[field] = value
    return out


def investors(db: Session, user: User) -> List[dict]:
    """맞추는 데 쓸 투자사 자료 — **이름 없이 번호로만**.

    누구를 담느냐는 **투자사 관리 현황이 세는 그 모집단**이다
    (`sheet_owner.managed`). 그 화면이 감춘 줄·투자사가 아닌 명단을 이미
    걸러 두었으므로, 여기서 따로 거르면 두 수가 갈린다.

    **자기 담당분이다**(관리자만 팀 전체). 추천은 전체를 보고 하는 일이라
    전부 내보내는 길도 있었지만, 딜 소개는 담당자별로 나간다 — 남의 담당
    투자사를 추천받아도 보낼 수가 없고, 번호를 되찾는 `resolve()` 도 같은
    모집단이라 누구인지조차 못 본다. 받는 사람이 **바로 쓸 수 있는 것**만
    나가는 편이 맞다. 팀 전체를 보고 고르는 것은 관리자의 일이고, 그 판정은
    담당자 줄을 고칠 수 있는가와 **같은 함수**를 읽는다.
    """
    from ..deps import may_manage_team_contacts   # deps → services 는 순환이 아니다

    rows = sheet_owner.managed(db, user,
                               team_wide=may_manage_team_contacts(user))
    out = []
    for c in rows:
        item = {"id": investor_ref(c.id)}
        item.update(_fill(c, INVESTOR_FIELDS, scrub_with=c))
        # 방이 살아 있어야 딜 소개가 나간다. 맞춰 놓고 보낼 길이 없으면
        # 그 추천은 쓸 수 없으므로 자료에 함께 담는다 — 거르지는 않는다
        # (막힌 사람을 골라 주면 그때 방부터 뚫으면 된다).
        item["room_open"] = _room_state(c) in _SENDABLE_ROOM
        out.append(item)
    return out


def companies(db: Session) -> List[dict]:
    """소개할 수 있는 IR 기업 자료 — 이름을 넣는다.

    기업은 **팀 공용**이다(`/companies` 화면도 담당으로 나누지 않는다).
    누구 담당이든 소개할 딜은 같은 목록에서 고른다.

    `딜소개 불가` 로 표시된 기업만 빠진다. 이것은 판단이 아니라 **보내면 안
    되는 곳**이고, 발송 화면이 이미 같은 이유로 목록에서 빼고 있다
    (`routers/pages.py` 의 `deals_page`) — 여기 남겨 두면 보낼 수 없는 곳을
    추천받는다. 판정은 그 화면이 쓰는 상수를 그대로 읽는다.

    내용이 모자란 기업은 **감추지 않고** `introducible` 로 표시만 한다.
    다시 계산하지 않고 `IrCompany.introducible` 을 그대로 읽는다 — 여기서
    조건을 새로 적으면 화면의 `내용 부족` 표시와 갈린다.

    이름은 나가야 하므로 가리지 않는다. 다만 한줄소개·요약에 **연락처가 문장째
    적혀 있는** 경우가 있어(투자사 쪽에서 실제로 나왔다) 전화·이메일 모양은
    여기서도 지운다 — `_scrub` 에 줄을 주지 않으면 그 둘만 걸린다.
    """
    from ..routers.companies import BLOCKED_CONTRACT, contract_key

    rows = db.execute(select(IrCompany).order_by(IrCompany.id)).scalars().all()
    out = []
    for c in rows:
        if contract_key(c.contract_status) == BLOCKED_CONTRACT:
            continue
        item = {"id": company_ref(c.id)}
        item.update(_fill(c, COMPANY_FIELDS))
        item["introducible"] = bool(c.introducible)
        out.append(item)
    return out


def brief(db: Session, user: User, *, now: Optional[str] = None) -> dict:
    """화면 단추와 API 가 **같이 부르는 함수**.

    둘을 따로 만들면 한쪽이 낡는다 — 이 저장소가 반복해 당한 사고다
    (좌측 메뉴 목록과 라우터 목록, 투자사 수 117명·123명). 화면의
    [자료 내려받기] 는 이 함수를 부르는 주소를 그대로 여는 링크다.
    """
    from ..deps import may_manage_team_contacts

    team_wide = may_manage_team_contacts(user)
    return {
        # 언제 꺼낸 자료인지. 메모에 날짜가 섞여 있어서(`8/19 : …`) 자료 자체가
        # 언제 것인지 없으면 그 날짜들을 어디에 견줘야 할지 알 수 없다.
        "generated_at": now or clock.now_iso(),
        "scope": "팀 전체" if team_wide else "본인 담당",
        "amount_unit": AMOUNT_UNIT,
        "note": NOTE,
        "investors": investors(db, user),
        "companies": companies(db),
    }


# ── 번호를 다시 이름으로 ────────────────────────────────────────────────────

def resolve(db: Session, user: User, text: str) -> dict:
    """LLM 이 답해 온 번호를 앱 안에서 이름으로 되돌린다.

    이 길이 없으면 번호로 내보내는 기능은 반쪽이다 — 답을 받아도 누구인지
    알 수 없다.

    **찾는 범위는 자료를 꺼낼 때와 같다.** 번호만 바꿔 넣어 남의 담당
    투자사를 알아내는 길이 되면 안 되고, 애초에 내보낸 적 없는 번호가 이름을
    돌려주면 그것도 유출이다. 그래서 `investors()` 와 같은 모집단
    (`sheet_owner.managed`)에서만 찾는다.

    못 찾은 번호는 **버리지 않고 그대로 돌려준다.** 조용히 빠지면 다섯을
    붙여 넣고 셋만 뜬 것을 눈치채지 못한다.
    """
    from ..deps import may_manage_team_contacts

    refs = parse_refs(text)

    contacts = {c.id: c for c in sheet_owner.managed(
        db, user, team_wide=may_manage_team_contacts(user))}
    found_investors = []
    for number in refs["investors"]:
        c = contacts.get(number)
        found_investors.append({
            "id": investor_ref(number),
            "found": c is not None,
            # 이름은 **앱 안에서만** 붙는다 — 내보내는 자료에는 없다.
            "name": c.name if c else "",
            "firm": (c.firm or "") if c else "",
            # 눌러서 바로 그 사람 상세를 연다. 목록만 띄우면 300명 중에서
            # 다시 찾아야 한다(대시보드의 '내 투자사 선호' 와 같은 주소다).
            "href": f"/contacts?contact={number}" if c else "",
        })

    ir_rows = {c.id: c for c in db.execute(select(IrCompany)).scalars().all()}
    found_companies = []
    for number in refs["companies"]:
        c = ir_rows.get(number)
        found_companies.append({
            "id": company_ref(number),
            "found": c is not None,
            "name": c.name if c else "",
            # IR 기업 현황에는 번호로 여는 길이 없고 검색만 있다 —
            # 이름으로 걸어 준다(`/companies?q=`).
            "href": f"/companies?q={quote(c.name)}" if c else "",
        })

    return {"investors": found_investors, "companies": found_companies}
