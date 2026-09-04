"""대시보드 집계 — 화면에 쓸 숫자를 한곳에서 만든다.

두 가지 화면이 있고 보는 목적이 다르다.

- **사용자 대시보드**: "다음 발송까지 내가 뭘 고쳐야 하나."
  방이 없는 담당자, 소개 문구가 없는 기업처럼 **막힌 것**을 먼저 보여준다.
  발송은 매월 첫째·셋째 수요일이라 그날까지 남은 날이 곧 마감이다.
- **관리자 대시보드**: "팀이 굴러가고 있나."
  팀원별 담당 규모·발송량·방 확인율을 나란히 놓아 어디가 막혔는지 본다.

집계는 SQL 한 번씩으로 끝낸다. 담당자 126명 · 활동 1,000여 건 규모라
파이썬에서 세도 되지만, 팀이 커지면 화면이 먼저 느려지는 자리다.
"""
from __future__ import annotations

from collections import Counter
from urllib.parse import quote
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import clock
from . import cadence, mailer, pipeline, sheet_owner
from .. import deps, version
from ..models import (
    SEND_KINDS,
    AgentDevice,
    IrRequest,
    Meeting,
    ContactActivity,
    DealBatch,
    IrCompany,
    SendItem,
    SendJob,
    User,
    VcContact,
)

# 반응을 '최근'으로 볼 기간. 내 투자사 화면과 같은 기준을 쓴다.
REACTION_WINDOW_DAYS = 60

# 발송 주기는 `schedule_rules` 가 정한다 — cadence.upcoming_send_dates 를 직접 쓴다.
# 예전엔 여기에 "매월 첫째·셋째 수요일" 이 박혀 있었는데, 주기는 운영하며 바뀐다.


# --- 공통 집계 --------------------------------------------------------------

# 방 확인 결과를 **명시적으로** 나눈다. 예전에는 모르는 값을 전부 '미확인'으로
# 떨어뜨렸는데, 그래서 '방 없음(not_found)' 으로 확인된 사람까지 발송 가능으로
# 세어졌다(투자사 관리 현황 117명 · 대시보드 123명으로 어긋난 원인).
_SENDABLE_ROOM = {"verified", "unverified"}
_ROOM_ALIAS = {
    "verified": "verified",
    "unverified": "unverified",
    "failed": "failed",
    "not_found": "failed",       # 방이 없다고 확인된 것 — 보낼 수 없다
    "ambiguous": "failed",       # 어느 방인지 모른다 — 보내면 안 된다
}


def _room_state(c: VcContact) -> str:
    """발송 준비 관점에서 본 방 상태."""
    if not c.channel_kakao:
        # 카톡 채널이 아니면 방 이름이 있어도 카톡 발송 대상이 아니다.
        return "email" if c.channel_email else "no_channel"
    if not (c.kakao_room_name or "").strip():
        return "missing"
    # 처음 보는 값은 '확인 안 됨'이 아니라 **보낼 수 없음**으로 본다.
    # 모르는 상태를 낙관적으로 해석하면 못 가는 곳에 갈 수 있다고 세게 된다.
    return _ROOM_ALIAS.get(c.room_verified or "", "failed")


# 세는 것만 보여주고 갈 곳이 없으면, 그 6명이 누구인지 알 수 없다.


# 값이 비어 있는 줄을 **거르는 값**. `filters.js` 가 값 없는 칸을 이 말로
# 세우므로(`EMPTY`), 링크도 같은 말로 걸어야 눌렀을 때 그 줄만 남는다.
# 여기에 다른 말을 적으면 눌러도 아무것도 안 걸러진 채 화면이 열린다 —
# 이 저장소가 두 번 당한 부류다(`connect=` · `room=`).
FILTER_EMPTY = "(비어 있음)"


def _values(key: str, values) -> str:
    """`키=값1,값2` — 한 칸 안에서는 **OR** 다(`filters.js` 규칙).

    값마다 따로 인코딩하고 나서 쉼표로 잇는다. 쉼표는 `filters.js` 가 값을
    나누는 글자라, 값 안에 쉼표가 들어 있으면(담당자 이름에 실제로 들어온다)
    거기서 갈라져 없는 값 둘이 된다 — `quote` 가 쉼표를 `%2C` 로 바꿔 주므로
    **먼저 인코딩하고 나중에 잇는** 순서를 지켜야 한다.
    """
    return f"{key}=" + ",".join(quote(v) for v in values)


def room_href(state: str, sheet: str = "all", stage: str = "") -> str:
    """이 방 상태의 사람만 남는 투자사 관리 현황 주소.

    **필터 값은 `ROOM_LABELS` 에서 꺼낸다.** 예전에는 여기에 `⚠ 미등록` 처럼
    말을 손으로 적어 두었는데, 그 말은 투자사 관리 현황이 쓰는 말도 아니었고
    `room` 이라는 키를 그 표가 **선언한 적조차 없었다** — `filters.js` 는
    선언되지 않은 키를 통째로 버리므로, 눌러도 274명이 그대로 떴다. 링크는
    살아 있고 화면도 열리니 아무도 눈치채지 못한다.

    지금은 표가 `카톡방` 칸을 세우고 `room:카톡방` 을 선언하며, 줄이 같은
    `ROOM_LABELS` 값을 `data-f-room` 으로 싣는다. 셋이 한 곳에서 나온다.

    `stage` 를 주면 연결 단계까지 함께 건다. 연결 진행 중인 명단 패널이
    **"연결은 끝났는데 방이 없는 사람"** 을 세기 때문이다 — 연결 전 사람도
    대개 방이 없어서, 그 조건을 안 걸면 패널이 말한 수보다 화면 줄이 많아진다.
    """
    return rooms_href([state], sheet, stage)


def rooms_href(states, sheet: str = "all", stage: str = "") -> str:
    """방 상태 **여럿**이 남는 주소. 한 칸 안에서는 OR 다.

    요약 줄의 `보낼 준비 완료 116명` 처럼 갈래를 묶어 세는 자리가 링크를 걸
    때 쓴다 — 갈래를 손으로 이어 붙이면 세는 곳과 가는 곳이 갈린다.
    """
    from .sheet_import import CONNECT_LABELS   # 순환 임포트라 함수 안에서

    href = (f"/contacts?sheet={quote(sheet)}&"
            + _values("room", [ROOM_LABELS[s][0] for s in states]))
    if stage:
        href += "&" + _values("connect", [CONNECT_LABELS[stage]])
    return href


def _room_href(state: str, ids: List[int], sheet: str = "all") -> Optional[str]:
    """이 상태의 사람들이 있는 곳.

    보낼 수 있는 방(확인됨·미확인)은 **딜 제안 관리로, 체크된 채로** 보낸다 —
    거기서 바로 다음 회차를 만드는 것이 다음 동작이라, 목록만 보여 주면 같은
    사람을 손으로 다시 골라야 한다.

    보낼 수 없는 쪽(방 없음·미등록·채널)은 고쳐야 할 것이라 투자사 목록으로
    보낸다.
    """
    if state in _SENDABLE_ROOM:
        return "/deals?contacts=" + ",".join(str(i) for i in ids) if ids else None
    return room_href(state, sheet)


# '내 투자사 선호' 를 몇 명까지 볼지. 50명이 기본이다 — 10명만 보면 그 아래에
# 누가 있는지 몰라서 매번 눌러 늘려야 했다.
# **화면(`/`)과 대시보드(`/dashboard`) 두 곳이 같은 값을 써야 한다** —
# 예전에는 각자 10 을 박아 두어 한쪽만 고쳐졌다.
TOP_CHOICES = [10, 30, 50, 100]
TOP_DEFAULT = 50


def clamp_top(top: int) -> int:
    return min(max(top, 5), max(TOP_CHOICES))


ROOM_LABELS = {
    "verified": ("확인됨", "ok"),
    "unverified": ("미확인", "warn"),
    "failed": ("방 없음 · 실패", "bad"),
    "missing": ("방 미등록", "bad"),
    "email": ("메일 채널", "muted"),
    # '미지정' 은 아직 안 정한 것처럼 읽혀서, 채우면 보낼 수 있는 줄로 오해된다.
    # 카톡도 메일도 아닌 사람이라 **보낼 길이 없는** 줄이다.
    "no_channel": ("채널 불가 투자사", "muted"),
}


def _recent_activity_counts(db: Session, contact_ids: List[int],
                            cutoff: str) -> Dict[str, int]:
    """최근 N일 안의 활동을 종류별로 센다(투자사 목록의 '반응' 태그용)."""
    if not contact_ids:
        return {}
    rows = db.execute(
        select(ContactActivity.kind, func.count())
        .where(ContactActivity.contact_id.in_(contact_ids),
               func.coalesce(ContactActivity.happened_at, "") >= cutoff)
        .group_by(ContactActivity.kind)
    ).all()
    return {kind: n for kind, n in rows}


def top_requesters(db: Session, contact_ids: List[int], limit: int = 10) -> List[dict]:
    """**IR 자료를 많이 달라고 한 투자사** 순.

    선호 단계·분야 분포는 '우리 명단이 어떤 성격인가' 는 알려 주지만 다음
    회차에 누구를 먼저 챙길지는 말해 주지 않았다. 자료를 달라고 한 횟수가
    관심의 크기이므로, 그 순서가 곧 우선순위다.

    시트에서 옮겨 온 기록(`ContactActivity`)과 이 도구에서 쌓인 기록
    (`IrRequest`)을 **함께** 센다 — 한쪽만 보면 옮겨 오기 전 이력이 통째로
    빠진다.
    """
    if not contact_ids:
        return []

    counts: Dict[int, int] = {}
    companies: Dict[int, set] = {}

    for contact_id, names in db.execute(
        select(ContactActivity.contact_id, ContactActivity.company_names)
        .where(ContactActivity.contact_id.in_(contact_ids),
               ContactActivity.kind == "ir_request")
    ).all():
        got = _company_names(names)
        counts[contact_id] = counts.get(contact_id, 0) + max(len(got), 1)
        companies.setdefault(contact_id, set()).update(got)

    for contact_id, company_name in db.execute(
        select(IrRequest.contact_id, IrRequest.company_name)
        .where(IrRequest.contact_id.in_(contact_ids))
    ).all():
        counts[contact_id] = counts.get(contact_id, 0) + 1
        if company_name:
            companies.setdefault(contact_id, set()).add(company_name.strip())

    if not counts:
        return []

    rows = db.execute(
        select(VcContact).where(VcContact.id.in_(list(counts)))
    ).scalars().all()
    by_id = {c.id: c for c in rows}

    out = []
    for contact_id, count in sorted(counts.items(), key=lambda kv: -kv[1])[:limit]:
        contact = by_id.get(contact_id)
        if contact is None:
            continue
        out.append({
            "id": contact_id,
            "name": contact.name,
            "title": contact.title or "",
            "firm": contact.firm or "",
            "count": count,
            "companies": sorted(companies.get(contact_id, set()))[:4],
        })
    return out


def _reaction_summary(db: Session, contact_ids: List[int]) -> dict:
    """반응 요약 — **기간을 자르지 않는다**.

    예전엔 '최근 60일'이었는데, 61일째가 되면 숫자가 갑자기 줄어드는 것을
    화면만 보고는 알 수 없었다. 반응은 한 번 오면 없어지는 것이 아니므로
    전체 기간으로 센다.

    세는 단위도 나눈다. IR 요청·미팅은 **투자사(담당자) 몇 곳**이 반응했는지가
    궁금하고(같은 곳이 세 번 요청해도 한 곳이다), 요청받은 **기업 수**는
    따로 봐야 한다.
    """
    if not contact_ids:
        return {"ir_contacts": 0, "meeting_contacts": 0, "requested_companies": 0,
                "meeting_done": 0, "meeting_call": 0}

    rows = db.execute(
        select(ContactActivity.kind, ContactActivity.contact_id,
               ContactActivity.company_names)
        .where(ContactActivity.contact_id.in_(contact_ids),
               ContactActivity.kind.in_(("ir_request", "meeting")))
    ).all()

    ir_contacts, meeting_contacts, companies = set(), set(), set()
    for kind, contact_id, names in rows:
        if kind == "ir_request":
            ir_contacts.add(contact_id)
            for name in _company_names(names):
                companies.add(name)
        else:
            meeting_contacts.add(contact_id)

    # 이 시스템으로 받은 요청도 함께 센다(시트 이력만 보면 최근 것이 빠진다).
    for contact_id, company_name in db.execute(
        select(IrRequest.contact_id, IrRequest.company_name)
        .where(IrRequest.contact_id.in_(contact_ids))
    ).all():
        ir_contacts.add(contact_id)
        if company_name:
            companies.add(company_name.strip())
    # 미팅은 '요청' 과 '완료' 를 나눠 센다. 끝난 미팅은 다음 할 일이 다르다 —
    # 열흘 뒤 결과를 물어봐야 하고, 그걸 놓치면 계약을 통째로 잊는다.
    done_contacts, call_contacts = set(), set()
    for meeting in db.execute(
        select(Meeting).where(Meeting.contact_id.in_(contact_ids))
    ).scalars().all():
        meeting_contacts.add(meeting.contact_id)
        if meeting.status == "done":
            done_contacts.add(meeting.contact_id)
            # 결과 문의를 아직 안 한 곳 — 전화할 대상이다.
            if not meeting.followup_done:
                call_contacts.add(meeting.contact_id)

    return {
        "meeting_done": len(done_contacts),
        "meeting_call": len(call_contacts),
        "ir_contacts": len(ir_contacts),
        "meeting_contacts": len(meeting_contacts),
        "requested_companies": len(companies),
    }


def _company_names(raw: Optional[str]) -> List[str]:
    import json

    try:
        return [str(n).strip() for n in json.loads(raw or "[]") if str(n).strip()]
    except (TypeError, ValueError):
        return []


def _split_csv(value: Optional[str]) -> List[str]:
    return [v.strip() for v in (value or "").split(",") if v.strip()]


def _distribution(values: List[str], top: int = 6) -> List[dict]:
    """막대그래프용 분포. 합계 대비 비율까지 계산해 템플릿을 단순하게 둔다."""
    counted = Counter(values)
    total = sum(counted.values()) or 1
    rows = [{"label": label, "count": n, "percent": round(n * 100 / total)}
            for label, n in counted.most_common(top)]
    return rows


# --- 사용자 대시보드 --------------------------------------------------------

def user_dashboard(db: Session, user: User, today: Optional[date] = None,
                   top_n: int = 10) -> dict:
    """`top_n` — '내 투자사 선호'에 몇 명까지 세울지. 화면에서 고른다(10~20)."""
    today = today or date.today()
    cutoff = (today - timedelta(days=REACTION_WINDOW_DAYS)).isoformat()

    # 담당은 **명단(시트) 단위**로 정해진다 — "내 이름으로 된 탭만 내 담당".
    # 이렇게 하지 않으면 시트를 올린 사람에게 팀 전체가 붙는다.
    contacts = sheet_owner.my_contacts(db, user)
    ids = [c.id for c in contacts]

    # 발송 준비를 말하는 숫자는 전부 **딜 소개를 보내기로 한 명단**에서 나온다.
    #
    # 한때 이 패널의 모집단을 내가 들고 있는 줄 전체(`managed` 274명)로 넓혀
    # 두었다. 배정 명단 125명이 전부 연결 완료라 패널이 안 뜨는 것을 보고 넓힌
    # 것인데, **그게 틀렸다** — 숫자를 만들려고 모집단을 넓히면 딜 소개 명단에
    # 올린 적도 없는 풀 사람의 연결 상태가 내 할 일로 뜬다. 기준은 딜 제안
    # 관리와 **같은 명단**이어야 한다(`sheet_owner.deal_list_contacts`).
    #
    # 0 이 정답이면 0 으로 둔다. 대신 화면이 **다 끝났다고 말하고**, 그 명단에서
    # 아직 못 받는 사람(방이 없는 쪽)을 이어서 보여 준다 — `_pipeline_view`.
    sending = sheet_owner.deal_list_contacts(db, user)
    # **연결이 안 끝난 사람**이다(`can_send_to` 가 아니라 `is_connected`).
    # 이 패널은 연결이라는 일 자체를 세는 자리라, 딜 소개를 멈춰 둔 사람까지
    # `아직 연결 안 됨` 으로 세면 안 된다 — 게다가 이 패널의 수는 눌러 가는
    # 목록(`?connect=…`)의 줄 수와 맞아야 하는데, 표에 `상태` 로 거르는 칸이
    # 없어서 여기서 빼면 화면이 센 수와 눌러 간 줄 수가 갈린다. 멈춰 둔 사람은
    # 아래 `on_hold` 가 이름까지 따로 말한다.
    waiting = [c for c in sending if not sheet_owner.is_connected(c)]
    # 눌러 갈 곳도 같은 명단이어야 한다. 세는 곳과 가는 곳이 다르면 "9명" 을
    # 눌렀는데 다른 수가 나온다.
    sheet_scope = deal_sheet_scope(db, sending)

    rooms = Counter(_room_state(c) for c in sending)
    # 상태별로 **누구인지**까지 들고 있어야 눌러서 갈 곳을 만들 수 있다.
    room_ids: Dict[str, List[int]] = {}
    for c in sending:
        room_ids.setdefault(_room_state(c), []).append(c.id)
    sendable = sum(rooms[state] for state in _SENDABLE_ROOM)

    companies = db.execute(select(IrCompany)).scalars().all()
    introducible = [c for c in companies if c.introducible]

    acts = _recent_activity_counts(db, ids, cutoff)

    # 발송 = **성공한** 건수. '보냈다'는 시도가 아니라 도착을 뜻해야 한다.
    #
    # 한 달 단위로 세면 월초에는 늘 0 에 가깝고 월말에만 커진다 — 이번 주에
    # 얼마나 나갔는지는 알 수 없다. 회차가 격주(첫째·셋째 수요일)라 **주간**이
    # 실제 일하는 단위다.
    week_start = today - timedelta(days=today.weekday())
    sent_rows = db.execute(
        select(SendItem.contact_id)
        .join(SendJob, SendJob.id == SendItem.job_id)
        .where(SendJob.user_id == user.id, SendItem.status == "sent",
               # 방 연결 확인은 아무것도 보내지 않는다 — 발송으로 세면 안 된다.
               SendJob.kind.in_(SEND_KINDS),
               func.coalesce(SendItem.sent_at, "") >= week_start.isoformat())
    ).scalars().all()
    sent_this_week = len(sent_rows)
    # 누르면 그 사람들이 **체크된 채로** 발송 화면이 열린다. 숫자만 보고
    # 누구에게 갔는지 모르면 다음에 누구를 챙길지 정할 수 없다.
    # (소싱 발송은 contact_id 가 비어 있다 — 투자사 목록에서 고를 수 없다)
    sent_ids = sorted({c for c in sent_rows if c})

    # 막힌 것 — 발송 전에 손봐야 할 목록
    #
    # 갈 곳은 `room_href` 하나가 만든다. 예전에는 여기에 `⚠ 미등록` 같은 말을
    # 손으로 적어 두었는데 표가 아는 값이 아니어서, 눌러도 아무것도 안 걸러진
    # 채 화면만 열렸다.
    blockers = []
    if rooms["missing"]:
        blockers.append({
            "count": rooms["missing"], "label": "카톡방이 없는 투자사",
            "hint": "이 투자사에게는 아무 것도 나가지 않습니다 — 방을 찾아 연결하세요",
            # 눌렀을 때 그 투자사만 보여야 한다. 전체 목록을 열어 주면
            # 어느 줄이 문제인지 다시 찾아야 한다.
            "href": room_href("missing", sheet_scope), "level": "bad",
        })
    if rooms["failed"]:
        blockers.append({
            "count": rooms["failed"], "label": "카톡방을 못 찾은 투자사",
            "hint": "실제 방이 없거나 제목이 다릅니다 — 이 투자사에게는 나가지 않습니다",
            "href": room_href("failed", sheet_scope), "level": "bad",
        })
    if rooms["unverified"]:
        blockers.append({
            "count": rooms["unverified"], "label": "카톡방 확인이 안 된 투자사",
            "hint": "제목이 실제와 다르면 그때 가서 빠집니다 — [방 연결 확인]을 돌리세요",
            "href": room_href("unverified", sheet_scope), "level": "warn",
        })
    not_introducible = len(companies) - len(introducible)
    if not_introducible:
        blockers.append({
            "count": not_introducible, "label": "발송 목록에 안 뜨는 기업",
            "hint": "한줄소개 또는 숫자(매출·투자금)가 비어 소개 문구를 만들 수 없습니다",
            # 표에서 '소개 가능' 컬럼을 뺐으므로 그 필터로 보내면 갈 곳이 없다.
            # 채워야 하는 값이 있는 스타트업DB 탭으로 보낸다.
            "href": "/companies?tab=db", "level": "warn",
        })

    device = db.execute(
        select(AgentDevice).where(AgentDevice.user_id == user.id)
    ).scalars().first()
    if device is None or not device.last_poll_at:
        blockers.append({
            "count": 1, "label": "발송 프로그램이 꺼져 있음",
            "hint": "내 PC에 설치하고 켜 두어야 카톡으로 나갑니다 — 지금은 한 건도 안 나갑니다",
            "href": "/setup", "level": "bad",
        })

    # 오늘 보낼 리마인드 — 딜소개 회차보다 먼저 챙겨야 할 때가 많다.
    cadence.sweep_reactions(db, user.id)
    due_rows = cadence.sequence_rows(db, user.id, today)
    due_today = [r for r in due_rows if r["status"] == "active" and r["due"]
                 and r["due"] <= today.isoformat()]

    upcoming = cadence.upcoming_send_dates(db, today)
    next_send = upcoming[0]

    return {
        "kpis": [
            # 이름만 보고 무엇을 세는지 알 수 있어야 한다.
            # '카톡 발송 가능'·'소개 가능 기업'은 무엇이 가능하다는 건지 모호했다.
            {"key": "contacts", "label": "내 담당 투자사", "value": len(contacts),
             "sub": "내 명단에 있는 사람", "href": "/contacts"},
            # 누르면 이번 주에 **실제로 도착한 사람**이 나온다 — 숫자만 보고
            # 누구에게 갔는지 모르면 다음에 누구를 챙길지 정할 수 없다.
            {"key": "sent", "label": "이번 주 보낸 건수", "value": sent_this_week,
             "sub": f"{week_start.strftime('%m/%d')}부터 · 도착 성공",
             "href": ("/deals?contacts=" + ",".join(str(i) for i in sent_ids)
                      if sent_ids else "/deals")},
        ],
        "next_send": next_send,
        "days_left": (next_send - today).days,
        "upcoming": upcoming,
        "rooms": [
            {"state": s, "label": ROOM_LABELS[s][0], "level": ROOM_LABELS[s][1],
             "count": rooms.get(s, 0),
             "percent": round(rooms.get(s, 0) * 100 / (len(sending) or 1)),
             "href": _room_href(s, room_ids.get(s, []), sheet_scope)}
            for s in ("verified", "unverified", "failed", "missing",
                      "email", "no_channel")
            if rooms.get(s, 0)
        ],
        "blockers": blockers,
        # 연결 작업은 발송과 다른 일이라 따로 보여준다.
        "pipeline": _pipeline_view(sending, waiting, sheet_scope),
        "pipeline_items": pipeline.today_items(db, user, today),
        "followups": {
            "due": len(due_today),
            "overdue": sum(1 for r in due_today if r["overdue"]),
            "rows": due_today[:5],
        },
        # 화면에는 안 띄우지만 값은 남긴다 — 발송 대상 판정이 이 기준을 쓰고,
        # 대시보드와 투자사 목록의 수가 어긋난 적이 있어 테스트가 지키고 있다.
        "sendable": sendable,
        "reactions": _reaction_summary(db, ids),
        "stages": _distribution([s for c in contacts for s in _split_csv(c.stages)]),
        "sectors": _distribution([s for c in contacts for s in _split_csv(c.sectors)]),
        # 다음 회차에 누구를 먼저 챙길지 — 자료를 달라고 한 횟수가 관심의 크기다.
        "top_requesters": top_requesters(db, ids, limit=top_n),
        "recent_batches": recent_batches(db, user_id=user.id),
    }


# 패널에 이름을 몇 명까지 세울지. '오늘 보낼 리마인드'(5명)와 같은 수다 —
# 대시보드는 한눈에 보는 화면이라 명단을 통째로 쏟으면 나머지가 안 보인다.
# 나머지는 눌러서 본다(그래서 `more` 와 링크를 함께 내놓는다).
PIPELINE_NAMES = 5

# 눌러 갈 곳은 **이 패널이 세는 딜 소개 명단 탭**이다.
#
# 세는 곳과 가는 곳이 같아야 한다. 예전에 패널은 '내 배정 명단' 을 세고 링크는
# `전체` 탭으로 보내서, 패널 0명 → 화면 44줄이 났다. 그다음에는 반대로 모집단을
# `전체` 로 넓혀 수를 맞췄는데, 그건 **딜 소개 명단에 없는 사람을 내 할 일로
# 세우는** 일이라 사용자가 바로잡았다.
#
# 그래서 모집단은 딜 소개 명단이고, 링크도 그 명단 탭으로 간다.
# 명단이 둘 이상이면 한 탭에 담기지 않으므로 `전체` 탭으로 보낸다 — 그때는
# 수가 한 겹 넓어지지만, 없는 탭으로 보내 0줄을 띄우는 것보다 낫다.
_ALL_SHEETS = "all"


def deal_sheet_scope(db: Session, rows: List[VcContact]) -> str:
    """이 사람들을 한 화면에 담는 명단 탭 이름. 여럿이면 `전체` 탭."""
    names = sheet_owner.deal_list_names(db, rows)
    return names[0] if len(names) == 1 else _ALL_SHEETS


def _sheet_href(sheet: str) -> str:
    return f"/contacts?sheet={quote(sheet)}"


def connect_href(stage: str, sheet: str = _ALL_SHEETS) -> str:
    """이 단계의 사람들만 남는 목록 주소.

    **필터 키(`connect`)와 값(연결 상태 라벨)을 손으로 적지 않는다.** 값은
    임포트가 정한 라벨(`CONNECT_LABELS`)을 그대로 쓰고, 키는 투자사 관리 현황이
    머리글에 선언한 것과 같아야 한다(`contacts.html` 의 `connect:연결 상태`,
    행의 `data-f-connect`). 셋 중 하나만 어긋나도 **눌러도 아무것도 안 걸러진
    채** 화면이 열려서, 아무도 눈치채지 못한다 — 이 저장소가 한 번 당한 자리다.

    바로 그 이유로 **모듈 밖에서도 부른다**(`room_href` 와 같은 자리다).
    딜 제안 관리도 "미착수 19명" 옆에 갈 곳을 걸어야 하는데, 거기서 주소를
    다시 조립하면 벌이 둘이 되어 한쪽이 낡는다 — `sheet_owner.blocked_stages`.
    """
    return _connect_any_href([stage], sheet)


def _connect_any_href(stages, sheet: str = _ALL_SHEETS, assignee=None) -> str:
    """단계 **여럿**(과 연결 담당)으로 거른 목록 주소.

    한 칸 안에서는 OR, 칸끼리는 AND 다(`filters.js`). 그래서
    `connect=진행 중,미착수 & assignee=…` 은 "그 담당의 아직 남은 사람" 이다.

    `assignee` 는 연결 담당이다. 안 정해진 사람은 빈 값이라 필터에서
    `(비어 있음)` 으로 서므로, 대시보드의 `미지정` 도 그 말로 건다.
    """
    from .sheet_import import CONNECT_LABELS   # 순환 임포트 방지: 함수 안에서

    href = (f"{_sheet_href(sheet)}&"
            + _values("connect", [CONNECT_LABELS[s] for s in stages]))
    if assignee is not None:
        href += "&" + _values("assignee", [assignee or FILTER_EMPTY])
    return href


def _people(rows: List[VcContact], sheet: str) -> List[dict]:
    """패널에 이름으로 세울 사람들(앞에서 `PIPELINE_NAMES` 명).

    이름을 누르면 그 사람 상세가 열린다(`?contact=` 는 화면이 직접 읽는 값이라
    필터와 부딪히지 않는다).
    """
    return [{"id": c.id, "name": c.name, "firm": c.firm or "",
             "href": f"{_sheet_href(sheet)}&contact={c.id}"}
            for c in rows[:PIPELINE_NAMES]]


def _pipeline_view(rows: List[VcContact], waiting: List[VcContact],
                   sheet: str = _ALL_SHEETS) -> dict:
    """딜 소개 명단의 **연결 현황**. 누구인지까지 보여준다.

    `rows` 는 그 명단 전체이고 `waiting` 은 그중 아직 연결이 안 끝난 사람이다.

    세는 것만 보여주고 갈 곳이 없으면, 그 44명이 누구인지 알 수 없다. 그래서
    ① 진행 중인 사람 이름을 앞에서 몇 명 세우고, ② 나머지는 목록으로 보내고,
    ③ 이름 하나하나가 그 사람의 상세로 간다.

    이름을 세우는 것은 **진행 중**뿐이다. 지금 전화·초대가 걸려 있는 사람이라
    다음 동작이 붙어 있고, 미착수 80명까지 이름으로 늘어놓으면 대시보드가
    명단 화면이 된다(그건 투자사 관리 현황이 할 일이다).

    ── 전원 연결이 끝났을 때 ────────────────────────────────────────────────
    실데이터의 딜 소개 명단 125명은 **전부 연결 완료**다. 그래서 연결 단계만
    보면 세 칸이 다 0이고, 예전 화면은 그때 패널을 통째로 감췄다 — 사용자가
    보려던 것("누가 아직 못 받는지")이 바로 그때 사라진다.

    **0 이면 0 이라고 말한다.** 숫자를 만들려고 모집단을 넓히지 않는다. 대신
    그다음 문을 보여 준다 — 딜 소개는 카톡방으로 나가는데 그 125명 중 9명은
    아직 방이 없다(채널 없음 6 · 메일 2 · 실패 1). 지금 실제로 손이 필요한
    것은 그쪽이다.

    갈래는 **`_room_state` 가 이미 정해 둔 것을 그대로 쓴다.** 여기에 다시
    적으면 대시보드의 방 요약과 이 패널이 서로 다른 갈래를 세게 된다.
    """
    from .sheet_import import (CONNECT_DONE, CONNECT_OPEN, STAGE_CONNECTED,
                               STAGE_IN_PROGRESS, STAGE_NOT_STARTED,
                               CONNECT_LABELS)

    counted = Counter(c.connect_stage for c in waiting)
    # **아직 손이 필요한 사람만** 이 패널의 일이다(`CONNECT_OPEN`).
    # `참여 안 함`·`방 나감` 은 더 진행하지 않기로 끝난 줄이라 챙길 것이 없다 —
    # 대시보드는 **할 일이 남은 것**을 띄우는 자리다. 방을 나가신 분이 계속
    # `지금 연결 중` 으로 떠 있던 것이 이 패널이 오래 당해 온 자리다.
    still_open = [c for c in waiting if c.connect_stage in CONNECT_OPEN]
    owners = Counter((c.assignee_name or "").strip() for c in still_open)
    working = [c for c in waiting if c.connect_stage == STAGE_IN_PROGRESS]

    # 화면은 단계 이름·라벨·주소·강조를 짝지어 두지 않는다 — 그렇게 두면 벌이
    # 둘이 되어 하나는 반드시 낡는다(라벨만 고치고 링크는 옛 값으로 남는 식).
    stages = [
        {"key": key, "label": CONNECT_LABELS[key], "count": counted.get(key, 0),
         "href": connect_href(key, sheet),
         # 지금 사람이 붙어 움직이는 것은 '진행 중' 하나뿐이라 거기만 눈에 띈다.
         "level": "ok" if key == STAGE_IN_PROGRESS else ""}
        for key in CONNECT_OPEN
    ]
    # 끝난 단계는 칸에서 빼되 **몇 명인지는 남긴다.** 수까지 사라지면 없어진
    # 줄 알고 다시 세러 들어간다 — 뺀 것과 없어진 것은 다르다. 0명인 갈래는
    # 적지 않는다(할 일이 아닌 것을 0으로 나열하면 칸만 늘어난다).
    done = [
        {"key": key, "label": CONNECT_LABELS[key], "count": counted.get(key, 0),
         "href": connect_href(key, sheet)}
        for key in CONNECT_DONE if counted.get(key, 0)
    ]

    # 연결은 끝났는데 **방이 없어 못 받는 사람.** 갈래별로 누구인지까지.
    #
    # 갈 곳에도 `연결 완료` 를 함께 건다. 연결 전 사람도 대개 방이 없어서,
    # 그 조건을 빼면 패널이 말한 수보다 화면 줄이 많아진다 — 이 패널이 오래
    # 당해 온 부류가 바로 "세는 곳과 가는 곳의 모집단이 다른" 것이다.
    stuck = [c for c in rows
             if sheet_owner.is_connected(c) and _room_state(c) not in _SENDABLE_ROOM]
    # 연결은 끝났는데 딜 소개를 멈춰 둔 사람 — 아래 `on_hold` 참고. 누구인지는
    # 발송 대상 판정과 같은 곳에서 온다.
    on_hold = sheet_owner.paused_rows(rows)
    by_room = Counter(_room_state(c) for c in stuck)
    rooms = [
        {"state": s, "label": ROOM_LABELS[s][0], "level": ROOM_LABELS[s][1],
         "count": by_room[s], "href": room_href(s, sheet, STAGE_CONNECTED),
         "people": _people([c for c in stuck if _room_state(c) == s], sheet),
         "more": max(by_room[s] - PIPELINE_NAMES, 0)}
        for s in ("missing", "failed", "unverified", "email", "no_channel")
        if by_room.get(s)
    ]

    return {
        # 이 패널이 말하는 모집단 = 딜 소개 명단. 화면이 "명단 125명" 이라고
        # 적을 수 있어야 기준이 또 어긋났을 때 쓰는 사람이 먼저 알아챈다.
        "listed": len(rows),
        # 어느 명단 기준인지 화면이 적을 수 있게. 명단이 둘 이상이면 `all` 이라
        # 이름 대신 빈 값으로 두고, 화면은 그냥 `딜소개 명단` 이라고만 적는다.
        "sheet": "" if sheet == _ALL_SHEETS else sheet,
        # 아직 못 보내는 사람 **전부**(끝난 줄까지). 화면이 아니라
        # `명단 = 준비 + 못 보냄 + 남음` 이라는 셈이 여기에 걸려 있다.
        "total": len(waiting),
        # 그중 **아직 손이 필요한** 사람. 화면의 `연결 남음` 은 이쪽이다 —
        # 참여 안 함·방 나감을 여기 섞으면 할 일이 아닌 것을 할 일로 센다.
        "open": len(still_open),
        "in_progress": counted.get(STAGE_IN_PROGRESS, 0),
        "not_started": counted.get(STAGE_NOT_STARTED, 0),
        "stages": stages,
        # 더 진행하지 않기로 끝난 줄 — 칸에서는 뺐지만 수와 갈 곳은 남긴다.
        "done": done,
        "people": _people(working, sheet),
        # 화면이 `총 - 보여준 수` 를 다시 계산하지 않게 여기서 준다.
        "more": max(len(working) - PIPELINE_NAMES, 0),
        "in_progress_href": connect_href(STAGE_IN_PROGRESS, sheet),
        # 요약 줄의 `연결 남음` 이 가는 곳 — 아직 손이 필요한 사람 전부.
        # 칸 두 개(진행 중·미착수)가 각각 절반씩 가리키는 자리라, 합쳐 놓은
        # 이 주소는 **다른 어느 링크도 가지 않는 곳**이다.
        "open_href": _connect_any_href(CONNECT_OPEN, sheet),
        # 요약 줄의 `보낼 준비 완료` — 연결이 끝났고 방까지 있는 사람.
        # 이쪽도 패널의 다른 링크가 가지 않는 곳이다.
        "ready_href": rooms_href(sorted(_SENDABLE_ROOM), sheet, STAGE_CONNECTED),
        # 진행 중이 하나도 없을 때 화면이 가리키는 다음 자리. 라벨을 화면에
        # 다시 적지 않도록 단계 하나를 통째로 넘긴다.
        "next_stage": next(s for s in stages if s["key"] == STAGE_NOT_STARTED),
        "list_href": _sheet_href(sheet),
        # 연결은 끝났지만 아직 못 받는 사람 — 갈래 · 이름 · 갈 곳.
        "rooms": rooms,
        "stuck": len(stuck),
        "ready": len(rows) - len(waiting) - len(stuck),
        # ── 연결은 끝났는데 **딜 소개를 멈춰 둔** 사람 ──────────────────────
        #
        # 이 명단에 있고 연결도 끝났지만 딜 제안 관리의 대상은 아니다
        # (`sheet_owner.can_send_to`). 그 차이를 안 적으면 대시보드가
        # `보낼 준비 완료 5명` 이라 해 놓고 발송 화면에는 4명이 뜬다 — 수가
        # 다른 것보다 **왜 다른지 화면이 말하지 않는 것**이 이 저장소가
        # 반복해 당한 문제다.
        #
        # **위 수에서 빼지는 않는다.** 위 갈래는 전부 눌러 가는 목록이 있고
        # 그 줄 수와 맞아야 하는데, 투자사 관리 현황 표에는 `상태` 로 거르는
        # 칸이 없다. 빼면 화면이 센 수와 눌러 간 줄 수가 갈린다 — 그래서
        # 겹친다는 것을 화면이 말하고, 이름으로 누구인지까지 보여 준다.
        "on_hold": len(on_hold),
        # 한글 이름을 여기서 지어내지 않는다 — 투자사 관리 현황의 고르는 칸과
        # 딜 제안 관리의 안내가 쓰는 그 말을 그대로 읽는다.
        "on_hold_label": sheet_owner.paused_label(),
        "on_hold_people": _people(on_hold, sheet),
        "on_hold_more": max(len(on_hold) - PIPELINE_NAMES, 0),
        # 연결 담당별로 **아직 남은** 사람. 갈 곳은 `그 담당 × 아직 남은 단계`
        # 라 화면의 수와 눌러 간 줄 수가 맞는다. 담당이 안 정해진 사람은
        # 값이 비어 있어서 `(비어 있음)` 으로 걸러진다 — 화면에는 `미지정`
        # 이라고 적지만 **거는 값은 필터가 쓰는 말**이어야 한다.
        "owners": [{"name": name or "미지정", "count": n,
                    "href": _connect_any_href(CONNECT_OPEN, sheet, assignee=name)}
                   for name, n in owners.most_common(4)],
    }


def recent_batches(db: Session, user_id: Optional[int] = None, limit: int = 5) -> List[dict]:
    """최근 발송 회차. 관리자 화면에서는 user_id 없이 팀 전체를 본다.

    **딜소개만 세면 안 된다.** IR 자료 전달·리마인드도 나간 것이고, 관리자가
    보려는 것은 "무엇이 나갔나" 다 — 종류로 걸러 놓으면 보낸 사람은 보냈는데
    관리자 화면에는 없는 상태가 된다(방 확인은 발송이 아니라 제외).
    """
    stmt = select(SendJob).where(SendJob.kind != "verify_room")
    if user_id is not None:
        stmt = stmt.where(SendJob.user_id == user_id)
    jobs = db.execute(stmt.order_by(SendJob.id.desc()).limit(limit)).scalars().all()
    if not jobs:
        return []

    batches = {
        b.id: b for b in db.execute(
            select(DealBatch).where(
                DealBatch.id.in_([j.batch_id for j in jobs if j.batch_id] or [0]))
        ).scalars().all()
    }
    owners = {
        u.id: u for u in db.execute(
            select(User).where(User.id.in_([j.user_id for j in jobs]))
        ).scalars().all()
    }
    kind_labels = {"deal_intro": "딜소개", "ir_delivery": "IR 자료 전달"}
    out = []
    for job in jobs:
        batch = batches.get(job.batch_id)
        owner = owners.get(job.user_id)
        out.append({
            "job_id": job.id,
            "title": batch.title if batch else "딜소개 회차",
            "kind": kind_labels.get(job.kind, job.kind),
            "date": (batch.sent_date if batch else None) or (job.started_at or "")[:10],
            "owner": owner.name if owner else "",
            "status": job.status,
            "total": job.total, "sent": job.sent, "failed": job.failed,
        })
    return out


# --- 관리자 대시보드 --------------------------------------------------------

def admin_dashboard(db: Session, today: Optional[date] = None) -> dict:
    today = today or date.today()
    cutoff = (today - timedelta(days=REACTION_WINDOW_DAYS)).isoformat()
    month_prefix = today.strftime("%Y-%m")

    users = db.execute(select(User).order_by(User.id)).scalars().all()
    # 팀 현황의 `전체 투자사` · 팀원별 담당 수 · 발송 가능 비율이 전부 여기서
    # 나온다. 투자사로 세지 않는 명단(스타트업 리마인드 등)과 감춘 줄을 여기서
    # 빼지 않으면, 사용자 대시보드는 걸러 세고 팀 현황만 안 걸러 세어 **화면마다
    # 수가 달라진다** — 예전에 117명 · 123명으로 갈렸던 그 부류다.
    contacts = sheet_owner.investors(
        db, db.execute(select(VcContact)).scalars().all())
    by_user: Dict[int, List[VcContact]] = {}
    for c in contacts:
        by_user.setdefault(c.user_id, []).append(c)

    devices = {
        d.user_id: d for d in db.execute(select(AgentDevice)).scalars().all()
    }

    # 이번 달 사용자별 성공 발송 수
    sent_rows = db.execute(
        select(SendJob.user_id, func.count())
        .select_from(SendItem).join(SendJob, SendJob.id == SendItem.job_id)
        .where(SendItem.status == "sent", SendJob.kind.in_(SEND_KINDS),
               func.coalesce(SendItem.sent_at, "").startswith(month_prefix))
        .group_by(SendJob.user_id)
    ).all()
    sent_by_user = {uid: n for uid, n in sent_rows}

    rows = []
    for u in users:
        mine = by_user.get(u.id, [])
        states = Counter(_room_state(c) for c in mine)
        ready = sum(states[state] for state in _SENDABLE_ROOM)
        acts = _recent_activity_counts(db, [c.id for c in mine], cutoff)
        device = devices.get(u.id)
        rows.append({
            "id": u.id,
            "name": u.name or "-",
            "phone": u.phone,
            "role": u.role,
            "contacts": len(mine),
            "ready": ready,
            "ready_percent": round(ready * 100 / (len(mine) or 1)),
            "missing": states["missing"] + states["failed"],
            "sent_month": sent_by_user.get(u.id, 0),
            "ir": acts.get("ir_request", 0),
            "meeting": acts.get("meeting", 0),
            "agent": _agent_label(device),
            "agent_ok": bool(device and device.last_poll_at),
            "agent_version": (device.agent_version if device else "") or "",
            "agent_old": bool(device and device.last_poll_at
                              and version.agent_is_old(device.agent_version)),
            "password_pending": bool(u.must_change_password),
            # 화면은 판정하지 않고 읽기만 한다. 예전에는 여기서 조건을 따로
            # 적어(`can_view_consulting or admin`) 라우터가 보는 조건과 갈렸고,
            # 컨설턴트 줄이 `막힘` 으로 떴는데 실제로는 열려 있었다.
            "consulting": deps.may_view_consulting(u),
            # 이 계정을 끄면 **볼 화면이 하나도 안 남는가.** 표가 누르기 전에
            # 확인 문구로 알려 준다 — 투자컨설턴트에게는 이 화면이 전부다.
            # (끌 수 있는 줄인지는 표가 본다: 본인 줄만 못 끈다.)
            "consulting_only_screen": deps.consulting_is_only_screen(u),
            # 자료 자동 첨부를 **쓸 수 있는 계정인가.** 화면은 판정하지 않고
            # 이 값을 읽는다 — `/setup` 의 자료 폴더 칸과 저장 라우터가 보는
            # 것과 **같은 함수**다(`deps.may_auto_attach`). 표에는 켜졌다고
            # 떠 있는데 그 사람 화면에는 칸이 없는, 그 어긋남을 막는다.
            "auto_attach": deps.may_auto_attach(u),
            # 딜소개를 보내지 않는 계정(투자컨설턴트)은 담당 투자사·발송 칸이
            # **원래 비어 있다.** 0 으로 그리면 설정이 덜 된 사람처럼 읽힌다.
            "sends_deals": deps.sends_deals(u),
            "last_login": (u.last_login_at or "")[:10],
        })

    companies = db.execute(select(IrCompany)).scalars().all()
    introducible = [c for c in companies if c.introducible]

    unassigned = len([c for c in contacts
                      if c.user_id not in {u.id for u in users}])

    return {
        "kpis": [
            {"key": "users", "label": "팀원", "value": len(users), "sub": "명", "href": "/team"},
            {"key": "contacts", "label": "전체 투자사", "value": len(contacts),
             "sub": "명", "href": "/contacts"},
            {"key": "companies", "label": "소개 가능 기업", "value": len(introducible),
             "sub": f"등록 {len(companies)}개 중", "href": "/companies"},
            {"key": "sent", "label": "이번 달 발송", "value": sum(sent_by_user.values()),
             "sub": "건 성공", "href": "/team"},
        ],
        "members": rows,
        "next_send": cadence.upcoming_send_dates(db, today)[0],
        "upcoming": cadence.upcoming_send_dates(db, today),
        "companies": {
            "total": len(companies),
            "introducible": len(introducible),
            "blocked": len(companies) - len(introducible),
            "top_deal": len([c for c in companies if c.is_top_deal]),
            "contracted": len([c for c in companies if c.contract_status == "yes"]),
        },
        "sectors": _distribution([c.sector_major for c in companies if c.sector_major], top=8),
        "mail": mailer.status(),
        "warnings": _admin_warnings(rows, unassigned),
        "recent_batches": recent_batches(db, limit=8),
    }


def _agent_label(device: Optional[AgentDevice]) -> str:
    if device is None:
        return "미발급"
    if not device.last_poll_at:
        return "미연결"
    if version.agent_is_old(device.agent_version):
        # 낡은 채로 돌면 조용히 다르게 동작한다 — 링크가 한 통으로 나가는 것처럼.
        # 연결됐다는 표시만 보고 넘어가지 않게 여기서 드러낸다.
        return f"갱신 필요 (v{device.agent_version or '?'})"
    try:
        ts = datetime.fromisoformat(device.last_poll_at)
        # 경과시간은 **순간**끼리 뺀다 — 저장값의 오프셋이 무엇이든 결과가 같다.
        mins = (clock.now() - ts).total_seconds() / 60
    except ValueError:
        return "확인 불가"
    if mins < 2:
        return f"연결됨 · {device.hostname or '이름 없음'}"
    if mins < 60:
        return f"{int(mins)}분 전"
    return f"{int(mins // 60)}시간 전"


def _admin_warnings(rows: List[dict], unassigned: int) -> List[dict]:
    """팀 단위로 손봐야 할 것. 사람 이름을 세워 누가 막혔는지 바로 보이게 한다.

    **딜소개를 보내는 계정만 센다.** 투자컨설턴트는 담당 투자사도 발송 프로그램도
    원래 없어서, 같이 세면 `발송 프로그램 미연결` 에 늘 이름이 올라간다 — 고칠
    것이 없는데 뜨는 경고가 섞이면 진짜 경고까지 무시하게 된다. 비밀번호처럼
    계정이면 누구나 해당되는 것은 그대로 전부 본다.
    """
    out = []
    senders = [r for r in rows if r.get("sends_deals", True)]
    old = [f'{r["name"]}(v{r["agent_version"] or "?"})'
           for r in senders if r.get("agent_old")]
    if old:
        out.append({"level": "warn", "label": "발송 프로그램이 낡았습니다",
                    "detail": ", ".join(old),
                    # 이 문구는 올릴 때마다 같이 고친다. 예전 이유(IR 링크가
                    # 여러 통으로 나간다)가 그대로 남아 있어, 낡은 에이전트가
                    # 왜 위험한지 잘못 알리고 있었다.
                    "hint": f"v{version.MIN_AGENT_VERSION} 부터 [중단]을 누르면 "
                            f"발송이 실제로 멈춥니다 — 그 PC에서 다시 받아 주세요"})
    no_agent = [r["name"] for r in senders if not r["agent_ok"]]
    if no_agent:
        out.append({"level": "bad", "label": "발송 프로그램 미연결",
                    "detail": ", ".join(no_agent),
                    "hint": "그 PC에서 [발송 프로그램 설치]를 해야 발송이 나갑니다"})
    pending = [r["name"] for r in rows if r["password_pending"]]
    if pending:
        out.append({"level": "warn", "label": "초기 비밀번호를 아직 안 바꾼 계정",
                    "detail": ", ".join(pending),
                    "hint": "첫 로그인 시 변경 화면으로 유도됩니다"})
    blocked = [f"{r['name']}({r['missing']}명)" for r in senders if r["missing"]]
    if blocked:
        out.append({"level": "warn", "label": "카톡방이 없거나 연결 실패한 담당자",
                    "detail": ", ".join(blocked),
                    "hint": "그 담당자에게는 발송이 나가지 않습니다"})
    empty = [r["name"] for r in senders if r["contacts"] == 0 and r["role"] != "admin"]
    if empty:
        out.append({"level": "muted", "label": "담당 투자사가 없는 계정",
                    "detail": ", ".join(empty),
                    "hint": "현황 시트를 업로드하면 채워집니다"})
    if unassigned:
        out.append({"level": "bad", "label": "주인이 없는 담당자",
                    "detail": f"{unassigned}명",
                    "hint": "계정이 지워졌는데 담당자가 남아 있습니다"})
    return out
