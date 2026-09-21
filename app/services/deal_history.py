"""기업별 소개 이력 — 이 기업을 **언제 · 누구에게 · 누가 · 몇 번** 보냈나.

매 회차 같은 기업을 또 보내면 받는 쪽에서는 이쪽이 지난번을 기억 못 한다고 읽는다.
그래서 기업을 고를 때 **최근에 보낸 것**이 눈에 띄어야 한다.

이력은 두 곳에 있다.
- `deal_batch_companies` — 이 시스템으로 보낸 회차
- `contact_activities` — 시트에서 옮겨 온 지난 발송 기록(문구 안에 기업명이 적혀 있다)
  그리고 사람이 손으로 적은 줄(`services/manual_send.py`, `source="manual"`)

시스템으로 보내기 시작한 것이 최근이라, 지금은 두 번째가 대부분이다.

## 왜 `한 수`로 줄이지 않는가

개발 자료로 재 보면 한 기업이 **보낸 날 6번 · 발송 180명**인데 날짜별로
`[113, 44, 20, 1, 1, 1]` 이다. 뒤의 `1` 셋은 투자사 **한 명**에게만 나간 것이라,
실제로는 단체 세 번 + 개별 세 번이다. 회차 수만 보이면 180명짜리와 103명짜리가
똑같이 `6회` 로 읽힌다. 그래서 **보낸 날 · 투자사 수 · 발송 건수 셋을 나란히**
내고, 날짜별로 펼쳐 그날 몇 명에게 갔는지까지 함께 낸다.

## 왜 이 파일 하나인가

이름을 맞추는 규칙(`_key`)도, 무엇을 `보냈다` 로 세는지도 여기 한 곳이다.
`llm_brief.sent_before` 가 이미 `_key` 를 부르고 있고, `/deals` 의
`최근에 소개함` 표시도 여기서 나온다. 규칙을 두 벌로 적으면 그 표시와
새 이력 수가 갈린다 — 이 저장소가 반복해서 데인 자리다.

그래서 **훑기는 `scan()` 한 번**이다. 화면이 묻는 것이 넷(마지막 날 · 보낸 날
수 · 투자사 수 · 발송 건수)이라 해서 질의를 넷으로 나누면, 그 넷이 조금씩
다른 것을 세기 시작한다.

## 투자사는 **수로만** 낸다

`contacts._owned` 는 남의 담당 투자사를 404 로 답한다 — 없는 것처럼 군다.
기업 화면이 그 명단을 읽는 우회로가 되면 안 되므로, 여기서 밖으로 나가는 것은
**사람 수**뿐이고 이름은 담지 않는다.
"""
from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (SEND_KINDS, ContactActivity, DealBatch, DealBatchCompany,
                      IrCompany, SendItem, SendJob, User, VcContact)
from .sheet_import import normalize_company_name

# 이 안에 보낸 기업은 '최근에 보냄'으로 표시한다.
# 월 2회 보내므로 두 회차(약 한 달) 안에 또 나가면 겹쳐 보인다.
RECENT_DAYS = 45

#: 시트에서 옮겨 온 지난 발송 기록의 갈래.
ACTIVITY_KIND = "deal_intro"

#: **실제로 나간 것**만 이력에 든다. `llm_brief.SENT_STATUS` 와 같은 값이고,
#: 같은 이유다 — `pending`·`failed`·`canceled` 를 "보냈다" 로 세면 안 나간
#: 기업이 이력에 든다. 잡 종류도 함께 본다(`models.SEND_KINDS`): 방 연결
#: 확인·시험 발송도 `sent` 로 남는데 그것은 투자사에게 보낸 것이 아니다.
SENT_STATUS = "sent"

#: 줄이 **어디서 왔나**. 화면에 그대로 뜨는 말이라 여기 한 곳에 둔다.
SHEET = "sheet"
APP = "app"
MANUAL = "manual"
SOURCE_LABELS = {SHEET: "시트", APP: "앱 발송", MANUAL: "손으로 적음"}

#: 보낸 사람을 **추정으로 적었다**는 표시.
#:
#: `contact_activities` 줄에는 **누가 보냈는지가 없다.** 시트에서 옮겨 온 줄은
#: 시트에 그 칸이 없었고, 사람이 손으로 적은 줄(`manual_send.record`)도 담당자
#: 번호만 남긴다 — 적은 사람을 담아 두는 칸이 그 표에 없다. 그래서 낼 수 있는
#: 답은 `contact_id → VcContact.user_id`, 즉 "그 투자사를 **지금** 담당하는
#: 팀원" 뿐이고, 담당이 이관되면 과거 발송이 통째로 새 담당자 앞으로 옮겨
#: 붙는다. 그 사실이 화면에 드러나야 한다.
#:
#: 앱으로 보낸 회차만 `SendJob.user_id` 로 **실제로 누른 사람**이 남는다.
GUESS_MARK = "(담당)"


def _key(name: Optional[str]) -> str:
    """비교용 이름. (주)·띄어쓰기 차이로 다른 기업이 되지 않게 맞춘다."""
    return normalize_company_name(name or "").replace(" ", "").lower()


@dataclass
class Sender:
    """한 회차에서 **이 기업을 보낸 팀원** 한 명.

    `guessed` 가 참이면 이름이 **추정**이다 — 줄에 보낸 사람이 안 적혀 있어서
    그 투자사를 지금 담당하는 팀원을 대신 적었다. 담당이 이관되면 과거 발송이
    통째로 새 담당자 앞으로 옮겨 붙는다. 화면은 이 값으로 `(담당)` 을 붙인다.
    """

    name: str
    count: int
    guessed: bool

    @property
    def label(self) -> str:
        return f"{GUESS_MARK} {self.name}" if self.guessed else self.name


@dataclass
class Round:
    """**하루치 한 줄** — 그날 이 기업이 몇 명에게, 누구 손으로 나갔나."""

    day: str                      # YYYY-MM-DD (없으면 빈 글자)
    source: str                   # SHEET · APP · MANUAL
    #: 시트에 적힌 요일. **계산하지 않는다** — 연도 추정이 틀리면 계산값이
    #: 어긋나므로 사용자가 쓴 값을 그대로 보존해 표시에 쓴다(모델 주석).
    #: 앱 회차에는 그 값이 없어 빈 글자다.
    weekday: str = ""
    #: 그날 이 기업이 나간 **사람 수**. 이름은 담지 않는다(머리글 참고).
    investors: int = 0
    senders: List[Sender] = field(default_factory=list)
    batch_title: str = ""         # 앱 회차만. 시트 줄은 빈 글자다.

    @property
    def source_label(self) -> str:
        return SOURCE_LABELS.get(self.source, self.source)


@dataclass
class CompanyHistory:
    """한 기업의 이력 전부. **한 수로 줄이지 않는다**(머리글 참고)."""

    rounds: List[Round] = field(default_factory=list)   # 최근 날짜부터
    #: 서로 다른 **사람** 수. 같은 사람에게 세 번 갔으면 하나로 센다.
    investors: int = 0
    #: 발송 건수 — 회차마다의 사람 수를 그대로 더한 값이다.
    sends: int = 0
    last_sent: str = ""

    @property
    def days(self) -> int:
        """보낸 날 수."""
        return len(self.rounds)


@dataclass
class CountOnly:
    """**개수만 적혀 기업을 알 수 없는 회차.**

    시트에 `핵심 딜 8개사` 처럼 적힌 줄이 있다(`ContactActivity.company_count`).
    기업 이름이 없으니 기업 줄에서 출발하는 이 집계에는 **한 줄도 안 잡힌다** —
    그 회차는 어느 기업 화면에도 안 보인다. 조용히 빠지면 합계가 왜 안 맞는지
    물을 자리가 없으므로 몇 개인지 세어 화면에 내놓는다.
    """

    rounds: int = 0               # 서로 다른 날 수
    rows: int = 0                 # 줄 수(= 받은 사람 수)
    days: List[str] = field(default_factory=list)


@dataclass
class Scan:
    """한 번의 훑기 결과. 화면이 묻는 것은 전부 여기서 나온다."""

    companies: Dict[str, CompanyHistory] = field(default_factory=dict)
    count_only: CountOnly = field(default_factory=CountOnly)
    #: 이력에는 있는데 지금 기업 목록에 **없는 이름**이 몇 곳인가.
    #: 이름은 담지 않는다 — `llm_brief.sent_before_unmatched` 와 같은 방식이다.
    unmatched: int = 0

    def of(self, name: Optional[str]) -> CompanyHistory:
        """이 기업의 이력. 없으면 **빈 이력**을 돌려준다(None 이 아니다).

        빈 이력을 돌려주는 것이 요점이다 — 부르는 쪽이 `if hist` 를 적기
        시작하면 "안 보냈다" 와 "이름이 안 맞았다" 가 같은 빈칸이 된다.
        """
        return self.companies.get(_key(name), CompanyHistory())

    def last_sent_map(self) -> Dict[str, str]:
        """{정규화한 기업명: 마지막으로 소개한 날(YYYY-MM-DD)}."""
        return {key: hist.last_sent
                for key, hist in self.companies.items() if hist.last_sent}


# ── 훑기 ────────────────────────────────────────────────────────────────────

class _Bucket:
    """모으는 중인 한 줄. 자리 하나 = (기업, 출처, 날짜 또는 회차)."""

    __slots__ = ("day", "source", "weekdays", "contacts", "senders", "title")

    def __init__(self, day: str, source: str) -> None:
        self.day = day
        self.source = source
        self.weekdays: Counter = Counter()
        self.contacts: set = set()
        self.senders: Counter = Counter()      # (이름, 추정인가) → 건수
        self.title = ""

    def round(self) -> Round:
        senders = [Sender(name=name, count=n, guessed=guessed)
                   for (name, guessed), n in
                   sorted(self.senders.items(), key=lambda kv: (-kv[1], kv[0]))]
        weekday = self.weekdays.most_common(1)[0][0] if self.weekdays else ""
        return Round(day=self.day, source=self.source, weekday=weekday,
                     investors=len(self.contacts), senders=senders,
                     batch_title=self.title)


def scan(db: Session) -> Scan:
    """이력을 **한 번에** 훑는다 — 날짜·투자사 수·팀원·출처를 함께 만든다.

    세는 기준은 `llm_brief.sent_history` 와 같아야 한다(둘 다 "이미 보낸 것"을
    세는 자리다): 앱 발송은 **실제로 나갔고**(`SENT_STATUS`) **문구가 나가는
    종류의 잡**(`SEND_KINDS`)인 것만 든다.
    """
    out = Scan()
    acc: Dict[str, Dict[Tuple, _Bucket]] = {}

    def bucket(key: str, at: Tuple, day: str, source: str) -> _Bucket:
        spots = acc.setdefault(key, {})
        if at not in spots:
            spots[at] = _Bucket(day, source)
        return spots[at]

    # 우리 팀 이름. 담당자 줄의 `user_id` 와 잡의 `user_id` 가 이것을 가리킨다.
    names = {u.id: (u.name or "").strip() for u in
             db.execute(select(User)).scalars().all()}
    # **그 투자사를 지금 담당하는 팀원.** 시트에서 온 옛 줄이 낼 수 있는 유일한
    # 답이다 — 줄 자체에는 누가 보냈는지가 안 적혀 있다.
    owner_of = {c.id: c.user_id for c in
                db.execute(select(VcContact)).scalars().all()}

    known = set()
    for company in db.execute(select(IrCompany)).scalars().all():
        known.add(_key(company.name))
    known.discard("")

    # ① 시트에서 옮겨 온 지난 발송 기록 + 손으로 적은 줄
    #
    # 되돌린 줄은 여기 안 온다 — 거르는 자리가 한 곳이라(`models`) 이 질의도
    # 저절로 지난다.
    seen_names = set()
    count_only_days: Counter = Counter()
    for act in db.execute(
        select(ContactActivity).where(ContactActivity.kind == ACTIVITY_KIND)
    ).scalars().all():
        try:
            row_names = json.loads(act.company_names or "[]")
        except (TypeError, ValueError):
            row_names = []
        if not row_names:
            # 개수만 적힌 회차. 기업을 알 수 없어 기업 줄에는 못 실린다.
            if act.company_count:
                count_only_days[(act.happened_at or "")[:10]] += 1
            continue
        day = (act.happened_at or "")[:10]
        source = MANUAL if act.source == MANUAL else SHEET
        who = names.get(owner_of.get(act.contact_id) or 0, "")
        for name in row_names:
            key = _key(name)
            if not key:
                continue
            seen_names.add(key)
            spot = bucket(key, (source, day), day, source)
            spot.contacts.add(act.contact_id)
            if act.weekday:
                spot.weekdays[act.weekday] += 1
            if who:
                # **추정이다** — 줄에 보낸 사람이 없어 담당을 대신 적는다.
                spot.senders[(who, True)] += 1

    out.count_only = CountOnly(rounds=len(count_only_days),
                               rows=sum(count_only_days.values()),
                               days=sorted((d for d in count_only_days if d),
                                           reverse=True))
    out.unmatched = len(seen_names - known)

    # ② 이 시스템으로 보낸 회차 — 자리는 **회차 하나**다(날짜가 아니다).
    #
    # 한 회차가 이틀에 걸쳐 나가도 사람이 세는 것은 그 회차 하나다. 날짜는
    # 회차가 적어 둔 발송일을 그대로 쓴다 — `마지막으로 소개한 날` 이 예전부터
    # 그 값이었고, 여기서 `SendItem.sent_at` 으로 갈아타면 그 표시가 하루씩
    # 어긋난다.
    for _link, batch, company in db.execute(
        select(DealBatchCompany, DealBatch, IrCompany)
        .join(DealBatch, DealBatch.id == DealBatchCompany.batch_id)
        .join(IrCompany, IrCompany.id == DealBatchCompany.company_id)
    ).all():
        key = _key(company.name)
        if not key:
            continue
        day = (batch.sent_date or "")[:10]
        spot = bucket(key, (APP, batch.id), day, APP)
        spot.title = batch.title or ""

    # 회차에 실제로 나간 건. **한 회차가 잡 여럿으로 나뉘어 나가기도 한다**
    # (그룹마다 한 잡) — 그래서 회차로 묶어 사람을 센다.
    sent_by_batch: Dict[int, set] = {}
    job_users: Dict[int, Counter] = {}
    for batch_id, user_id, contact_id in db.execute(
        select(SendJob.batch_id, SendJob.user_id, SendItem.contact_id)
        .join(SendItem, SendItem.job_id == SendJob.id)
        .where(SendItem.status == SENT_STATUS,
               SendJob.kind.in_(SEND_KINDS),
               SendJob.batch_id.isnot(None))
    ).all():
        sent_by_batch.setdefault(batch_id, set()).add(contact_id)
        # 앱 발송은 **실제로 누가 눌렀는지**가 남는다 — 추정이 아니다.
        job_users.setdefault(batch_id, Counter())[user_id] += 1

    for spots in acc.values():
        for at, spot in spots.items():
            if spot.source != APP:
                continue
            batch_id = at[1]
            spot.contacts |= sent_by_batch.get(batch_id, set())
            for user_id, n in (job_users.get(batch_id) or Counter()).items():
                who = names.get(user_id, "")
                if who:
                    spot.senders[(who, False)] += n

    for key, spots in acc.items():
        rounds = sorted((spot.round() for spot in spots.values()),
                        key=lambda r: (r.day, r.source), reverse=True)
        everyone: set = set()
        for spot in spots.values():
            everyone |= spot.contacts
        days = [r.day for r in rounds if r.day]
        out.companies[key] = CompanyHistory(
            rounds=rounds,
            investors=len(everyone),
            sends=sum(r.investors for r in rounds),
            last_sent=max(days) if days else "")
    return out


def last_sent_map(db: Session) -> Dict[str, str]:
    """{정규화한 기업명: 마지막으로 소개한 날(YYYY-MM-DD)}.

    **`scan()` 에서 그대로 나온다.** 날짜만 필요한 자리를 위한 짧은 답이고,
    규칙을 따로 들고 있지 않다 — 들고 있으면 `최근에 소개함` 표시와 이력 표가
    갈린다.
    """
    return scan(db).last_sent_map()


def annotate(companies: List[IrCompany], sent: Scan,
             today: Optional[date] = None) -> Dict[int, dict]:
    """{기업 id: {last_sent, days_ago, recent, rounds, investors, sends}}.

    `rounds` 는 **보낸 날 수**다. 발송 건수(`sends`)와 나란히 둔다 — 회차 수만
    보이면 180명짜리와 103명짜리가 똑같이 `6회` 로 읽힌다(머리글 참고).
    """
    today = today or date.today()
    out: Dict[int, dict] = {}
    for company in companies:
        hist = sent.of(company.name)
        when = hist.last_sent
        days = None
        if when:
            try:
                days = (today - date.fromisoformat(when)).days
            except ValueError:
                days = None
        out[company.id] = {
            "last_sent": when,
            "days_ago": days,
            "recent": days is not None and 0 <= days <= RECENT_DAYS,
            "rounds": hist.days,
            "investors": hist.investors,
            "sends": hist.sends,
        }
    return out
