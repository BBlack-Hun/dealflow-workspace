"""스타트업 **안내 카톡** — 각자 맡은 스타트업에 문구 하나를 골라 보낸다.

## 무엇인가

팀원마다 좌측 [스타트업] 화면에 **자기가 맡은 스타트업 명단**이 있다(탭
하나가 한 사람 몫이다 — `sheet_owner.member_tabs`). 그 대표들에게 손으로
보내던 카톡이 셋 있었다.

  · 투자유치 진행 상황 문의 — IR 미팅을 드렸던 곳에 요즘 어떠신지
  · 견적서 공유 안내 — 견적서를 보낸 뒤 조율할 것이 있으면 말씀 달라고
  · 무료 투자유치(성과보수) 제안 — 계약금 없이 성과보수로 진행할 수 있다고

이것을 **딜소개처럼** 보낸다 — 받을 곳을 고르고 → 대기 목록(`draft`) →
진행 화면에서 [발송 시작] 또는 예약 → 그 사람 PC 의 발송 프로그램이 카톡으로
보낸다(공식 카카오 API 는 없다).

## 월간 발송과 무엇이 다른가

`services/startup_send.py`(스타트업 월간 발송)와 **다른 일이다.**

  · 받는 줄: 저쪽은 IR 기업 현황의 기업(`IrCompany`), 이쪽은 [스타트업] 명단의
    줄(`VcContact` — 기업명·성함·카톡방이 그 줄에 있다).
  · 보내는 사람: 저쪽은 설정이 고른 **한 계정**, 이쪽은 딜소개처럼 **각자**
    자기 줄에만 보낸다(관리자도 자기 줄만 — 딜 제안 관리와 같다).
  · 잡 종류: 저쪽 `startup_ir`, 이쪽 `startup_msg`(`models.STARTUP_MSG_KIND`
    — 왜 나누는지는 거기).

## 이 파일이 정하는 것

1. **어느 줄에 보낼 수 있는가**(`rows` · `refusal`) — 화면이 고를 수 있게
   하는 것과 목록을 만드는 자리가 막는 것이 **같은 함수**를 지난다.
2. **글을 어떻게 채우는가**(`render`) — 미리보기와 실제로 나가는 글이 같은
   함수를 지난다.
3. **이 문구를 언제 받았나**(`last_sent`) — `마지막 발송일` 과 `N일 안에 받은
   곳 빼기` 가 이것을 읽는다.

**발송 목록을 만드는 것은 여기가 아니다.** `routers/deals.create_send_list` 를
그대로 지난다(`MODE_STARTUP_MSG`) — 방 이름 확인 · 문구 스냅숏 · 예약 · `draft`
가 전부 그 함수 안에 있어서, 한 벌 더 적으면 그중 하나가 빠진 채로 대표
카톡방에 나간다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import timedelta
from typing import Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import clock
from ..models import STARTUP_MSG_KIND, SendItem, SendJob, User, VcContact
from . import (contact_columns, room_joined, room_match, sheet_owner,
               template_pick, twin_send)

#: 잡 종류(`SendJob.kind`). 같은 것을 가리키므로 글자도 같다.
KIND = STARTUP_MSG_KIND

#: 화면에 적는 이름.
LABEL = "스타트업 안내 카톡"

#: `이 문구를 N일 안에 받은 곳 빼기` 의 기본값. 화면에서 바꿀 수 있다
#: (0 이면 빼지 않는다).
DEFAULT_DAYS = 30

#: 문구 길이 상한 — 사람이 고친 문구를 받는 다른 자리와 같은 선이다
#: (`routers/deals._override_map`).
MAX_CHARS = 6000


# ── 문구 셋 ─────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Topic:
    """고를 수 있는 문구 하나.

    `key` 가 **세 가지를 한꺼번에** 가리킨다 — 문구틀의 종류
    (`message_templates.kind`), 회차에 남는 표시(`SendJob.topic`), 화면 주소의
    값(`?topic=`). 셋을 따로 두면 문구 화면에서 고친 것과 실제로 나가는 것,
    그리고 "언제 받았나" 가 서로 다른 문구를 가리키게 된다.
    """

    key: str
    label: str
    #: 문구틀이 하나도 없을 때 나가는 글이자, 새 서버에 처음 심는 팀 기본 문구
    #: (`scripts/bootstrap.py` 가 이 값을 읽는다 — 두 곳에 적지 않는다).
    default: str


# 사용자가 손으로 보내던 글 **그대로**다. `000` 자리만 채움말로 바꿨다.
# 띄어쓰기 한 칸까지 그대로 둔다(`ASSET  {보내는사람}` 의 두 칸도 원문이다).
TOPICS = (
    Topic("startup_msg_progress", "투자유치 진행 문의",
          "안녕하세요 {대표명} 대표님.\n"
          "IR 투자유치 관련 미팅 드렸던 컨텍브이씨 Asset 입니다.\n"
          "최근 투자사에서 신규 기업 검토 요청이 있어서\n"
          "대표님 회사 투자유치진행 상황이 어떠신지\n"
          "문의 연락드렸습니다."),
    Topic("startup_msg_quote", "견적서 공유 안내",
          "안녕하세요, 대표님.\n"
          "견적서를 카톡으로 공유 드렸습니다.\n"
          "\n"
          "조건이나 진행 방식 관련하여 조율이 필요하신 부분은 언제든 말씀해 주세요."),
    Topic("startup_msg_free", "무료 투자유치 제안",
          "안녕하세요 대표님.\n"
          "컨텍브이씨 ASSET  {보내는사람} 팀장입니다.\n"
          "\n"
          "저희는 매월 일부 기업을 선정해 계약금 없이 투자유치 완료 후 "
          "성과보수 방식으로 진행하고 있습니다.\n"
          "\n"
          "대표님 기업도 해당 방식으로 진행을 검토드릴 수 있어 연락드렸습니다.\n"
          "계약금이 있는 경우에는 성과보수율을 낮춰 진행할 수 있습니다.\n"
          "\n"
          "무료투자유치 조건 조율이 필요하시면 편하게 톡 주시면 검토 후 "
          "안내드리겠습니다."),
)
TOPIC_BY_KEY = {t.key: t for t in TOPICS}

#: 새 서버에 심는 팀 기본 문구 — `(종류, 본문)`. `scripts/bootstrap.py` 의
#: `TEAM_TEMPLATES` 가 이것을 그대로 덧붙인다.
TEAM_DEFAULTS = [(t.key, t.default) for t in TOPICS]


def topic_of(key: Optional[str]) -> Optional[Topic]:
    """고른 문구. 모르는 값이면 `None` — **짐작해서 다른 문구로 보내지 않는다.**"""
    return TOPIC_BY_KEY.get((key or "").strip())


def history_label(key: Optional[str]) -> str:
    """활동 이력에 적는 이름 — `안내 카톡 · 견적서 공유 안내`.

    모르는 문구(지운 문구 · 비어 있는 옛 줄)면 `안내 카톡` 만 적는다 — 지어내지
    않는다.
    """
    topic = topic_of(key)
    return f"안내 카톡 · {topic.label}" if topic else "안내 카톡"


def template_body(db: Session, user: User, topic: Topic) -> str:
    """이 사람이 이 문구에 쓸 글 — 고른 것 > 내 것 > 팀 것 > 코드의 기본.

    고르는 규칙은 `template_pick.pick` 한 곳이다(딜소개 문구와 같은 규칙).
    """
    picked = template_pick.pick(db, user.id, topic.key)
    return picked.body if picked else topic.default


# ── 채움말 ──────────────────────────────────────────────────────────────────

CEO = "{대표명}"
COMPANY = "{회사명}"
SENDER = "{보내는사람}"
#: 문구 화면이 적어 주는 안내 — 무엇이 어디서 채워지는지.
PLACEHOLDERS = [
    (CEO, "스타트업 명단의 성함 (비어 있으면 그 자리를 빼고 '대표님' 으로 읽힙니다)"),
    (COMPANY, "스타트업 명단의 기업명"),
    (SENDER, "보내는 사람의 계정 이름"),
]

# `홍길동 대표` · `홍길동 대표님` 처럼 성함 칸에 직함까지 적힌 줄이 있다.
# 그대로 넣으면 `홍길동 대표 대표님` 이 된다.
_CEO_SUFFIX = re.compile(r"\s*대표\s*님?\s*$")


def ceo_name(contact: VcContact) -> str:
    """`{대표명}` — 명단의 성함. 뒤에 붙은 `대표(님)` 은 뗀다(문구에 이미 있다)."""
    return _CEO_SUFFIX.sub("", (contact.name or "").strip()).strip()


def company_name(contact: VcContact) -> str:
    """`{회사명}` — 명단의 기업명(적힌 그대로)."""
    return (contact.firm or "").strip()


def sender_name(user: User) -> str:
    """`{보내는사람}` — 계정 이름. 이름이 없는 계정이면 빈 글자.

    이름이 빈 계정은 로그인 ID(휴대폰번호)가 이름 칸에 든다. 그것을 대표에게
    보내면 안 된다 — 판정은 탭 이름과 같은 자리다(`sheet_owner.real_name`).
    """
    return sheet_owner.real_name(user)


def _drop(text: str, token: str) -> str:
    """빈 채움말을 **옆의 빈칸 하나와 함께** 뺀다.

    `안녕하세요 {대표명} 대표님.` → `안녕하세요 대표님.` — 채움말만 지우면
    `안녕하세요  대표님.`(두 칸)이 된다. 문구 전체의 두 칸을 한 칸으로 줄이지는
    않는다: 원문에 일부러 띄운 두 칸이 있다(`ASSET  {보내는사람}`).
    """
    text = text.replace(token + " ", "")
    text = text.replace(" " + token, "")
    return text.replace(token, "")


def render(body: str, contact: VcContact, user: User) -> str:
    """이 줄에 나갈 글. **미리보기와 발송이 같은 이 함수를 지난다.**"""
    text = (body or "").strip()
    for token, value in ((CEO, ceo_name(contact)),
                         (COMPANY, company_name(contact)),
                         (SENDER, sender_name(user))):
        text = text.replace(token, value) if value else _drop(text, token)
    return text


# ── 누구에게 보낼 수 있는가 ─────────────────────────────────────────────────

def my_rows(db: Session, user: User) -> List[VcContact]:
    """내가 맡은 스타트업 줄 — **[스타트업] 화면 명단에 있는 내 줄**, 기업명 순.

    딜소개처럼 **본인 줄만**이다(`VcContact.user_id`). 관리자도 같다 — 회차는
    그 사람의 것으로 서고 그 사람 PC 의 발송기만 집어간다
    (`routers/agent_api.poll`). 남의 줄을 넣으면 남의 대표에게 내 카톡으로
    나간다.

    어느 명단이 [스타트업] 화면에 사는지는 이름이 아니라 배치가 정한다
    (`sheet_owner.page_labels`). 줄 단위로 감춘 줄은 뺀다 — 표에 없는 줄이
    발송 목록에만 있으면 안 된다.
    """
    labels = sheet_owner.page_labels(db, contact_columns.PAGE_STARTUP)
    rows = db.execute(
        select(VcContact).where(VcContact.user_id == user.id)
        .order_by(VcContact.firm, VcContact.id)
    ).scalars().all()
    return [c for c in rows
            if not c.is_hidden and sheet_owner.on_page(c, labels)]


def load(db: Session, user: User, ids: List[int]) -> List[VcContact]:
    """고른 id 중 **내 스타트업 줄인 것만**, 고른 순서대로."""
    by_id = {c.id: c for c in my_rows(db, user)}
    return [by_id[i] for i in ids if i in by_id]


def contract_of(contact: VcContact) -> str:
    """`계약여부` 칸(명단의 `notes["contract"]`) — 적힌 그대로."""
    return contact_columns.load_notes(contact.notes).get("contract", "").strip()


def is_blocked(contact: VcContact) -> bool:
    """`딜소개 불가` 로 적힌 줄. **언제나 뺀다.**

    말과 값을 맞추는 자리는 IR 기업 현황과 같은 함수다(`companies.contract_key`
    — `딜소개 불가` · `딜소개불가` · `blocked` 를 같은 것으로 본다).
    """
    from ..routers.companies import BLOCKED_CONTRACT, contract_key

    raw = contract_of(contact)
    return bool(raw) and contract_key(raw) == BLOCKED_CONTRACT


#: 방 이름이 빈 줄.
ROOM_MISSING = "missing"
#: 방 상태 → 화면 말. 확인 결과 넷은 스타트업 방 맞추기 화면과 **같은 말**이다.
ROOM_LABELS = {ROOM_MISSING: "카톡방 이름 없음", **room_match.STATE_LABELS}


def room_state(contact: VcContact) -> str:
    """보낼 방의 상태 — `missing` 이거나 방 확인 결과(`room_verified`) 넷 중 하나.

    ## 왜 `dashboard._room_state` 를 안 쓰나

    그 판정은 **채널 칸**(`channel_kakao`)을 먼저 본다. 스타트업 명단에는
    채널 칸이 없어서(표에도 수정창에도 없다 — `contact_columns.STARTUP_LAYOUT`)
    대부분 0 으로 들어 있고, 그 판정으로는 전부 `채널 불가` 가 된다. 여기서는
    방 이름과 확인 결과만 본다.
    """
    if not (contact.kakao_room_name or "").strip():
        return ROOM_MISSING
    return contact.room_verified or room_joined.UNVERIFIED


def room_ready(contact: VcContact) -> bool:
    """**카톡에서 확인된 방**인가 — 이 발송이 나갈 수 있는 방.

    딜소개(투자사)는 `확인 안 됨` 도 보낸다(`dashboard._SENDABLE_ROOM`). 여기는
    **확인된 방만** 보낸다. 스타트업 방 제목은 사람마다 제각각이고
    (`대표 대표님회사 , 팀원` — `room_match` 머리말), 대표 이름이 든 다른 방
    (투자사 방·단체방)이 같은 글자로 걸릴 수 있다. [방 연결 확인] 한 번이면
    `확인됨` 이 되고, 그 확인이 카톡 연결 여부도 `O` 로 맞춘다(`room_joined`).
    """
    return room_state(contact) == room_joined.VERIFIED


#: 못 보내는 갈래 — 화면이 줄을 어느 칸에 세울지가 이것으로 갈린다(`rows`).
EXCLUDED = "excluded"   # `딜소개 불가` · `검토중단` — 언제나 빠진다
NO_ROOM = "no_room"     # 방이 없거나 카톡에서 확인 전 — 고치면 보낼 수 있다


def _verdict(contact: VcContact):
    """`(갈래, 까닭)` — 보낼 수 있으면 `("", "")`. 판정은 여기 하나다."""
    if is_blocked(contact):
        return EXCLUDED, "딜소개 불가"
    if sheet_owner.is_paused(contact):
        return EXCLUDED, sheet_owner.paused_label()
    state = room_state(contact)
    if state != room_joined.VERIFIED:
        return NO_ROOM, ROOM_LABELS.get(state, state)
    return "", ""


def group_of(contact: VcContact) -> str:
    """못 보내는 갈래 — `excluded` · `no_room`, 보낼 수 있으면 빈 글자.

    [방 매칭](`services/startup_room_pick.py`)이 **어느 줄의 방을 찾을지**를
    이것으로 가른다 — 이 화면이 `방 확인 전` 으로 접어 두는 줄과 거기서 찾는
    줄이 같아야, 찾아서 확정한 줄이 곧바로 이 화면의 고를 수 있는 줄로 올라온다.
    """
    return _verdict(contact)[0]


def refusal(contact: VcContact) -> str:
    """이 줄에 **보내면 안 되는** 까닭. 보낼 수 있으면 빈 글자.

    화면이 고를 수 없게 하는 것과 목록을 만드는 자리가 막는 것이 이 함수
    하나를 지난다 — 둘이 갈리면 화면에서 못 고르는 줄이 주소로는 들어간다.
    (`N일 안에 받은 곳` 은 여기 없다 — 사람이 풀 수 있는 거르기다. `rows`.)
    """
    return _verdict(contact)[1]


def who(contact: VcContact) -> str:
    """화면·오류 문장에 적을 이름 — **기업명**(없으면 성함)."""
    return company_name(contact) or (contact.name or "").strip() or f"#{contact.id}"


# ── 이 문구를 언제 받았나 ───────────────────────────────────────────────────

#: 센다 — 나갔거나(`sent`), 나가는 중이거나(`sending`), 나갈 예정(`pending`).
#: 실패·취소는 안 받은 것이다(`twin_send.LIVE_ITEM` 과 같은 규칙).
LIVE_ITEM = ("pending", "sending", "sent")


def last_sent(db: Session, contacts: List[VcContact], topic: Topic) -> Dict[int, dict]:
    """`{contact_id: {"date": "YYYY-MM-DD", "pending_job": int, "by_twin": str}}`.

    **다른 팀원 명단의 같은 기업**도 센다(`twin_send.twins`) — 같은 대표가
    두 사람에게서 같은 문구를 받으면 안 된다. 그쪽에서 받은 것이면 `by_twin`
    에 그 팀원 이름이 든다.

    `date` 는 나간 것 중 가장 최근(나간 날 — 없으면 목록에 오른 날),
    `pending_job` 은 이 문구가 **아직 안 나간 채** 들어 있는 회차(대기·예약 ·
    보내는 중) 번호다. 없으면 0.
    """
    out: Dict[int, dict] = {}
    for contact in contacts:
        # 이 줄 + 다른 팀원 몫의 같은 줄(판정은 `twin_send.twins` 한 곳이다).
        owner_of = {contact.id: ""}
        for twin in twin_send.twins(db, contact):
            owner = db.get(User, twin.user_id)
            owner_of[twin.id] = getattr(owner, "name", "") or "다른 팀원"
        hits = db.execute(
            select(SendItem.contact_id, SendItem.status, SendItem.sent_at,
                   SendItem.created_at, SendItem.job_id)
            .join(SendJob, SendJob.id == SendItem.job_id)
            .where(SendJob.kind == KIND, SendJob.topic == topic.key,
                   SendJob.status != "canceled",
                   SendItem.contact_id.in_(list(owner_of)),
                   SendItem.status.in_(LIVE_ITEM))
        ).all()
        if not hits:
            continue
        sent = sorted(((h.sent_at or h.created_at or "")[:10], owner_of[h.contact_id])
                      for h in hits if h.status == "sent")
        latest, by = sent[-1] if sent else ("", "")
        waiting = [h for h in hits if h.status in ("pending", "sending")]
        out[contact.id] = {
            "date": latest,
            "pending_job": waiting[0].job_id if waiting else 0,
            "pending_by": owner_of[waiting[0].contact_id] if waiting else "",
            "by_twin": by,
        }
    return out


def recent_reason(info: Optional[dict], days: int) -> str:
    """`N일 안에 받은 곳 빼기` 에 걸리는 까닭. 안 걸리면 빈 글자.

    `days` 가 0 이면 아무것도 빼지 않는다(사람이 일부러 다시 보내는 자리).
    대기 중인 회차에 이미 들어 있으면 그것도 뺀다 — 둘 다 나가면 같은 문구를
    두 번 받는다.
    """
    if not info or days <= 0:
        return ""
    if info.get("pending_job"):
        # 회차 번호를 적는다 — 그 회차를 열어 보내거나 빼는 것이 할 일이다.
        by = f"{info['pending_by']} 님 " if info.get("pending_by") else ""
        return f"{by}아직 안 나간 회차 #{info['pending_job']} 에 이미 들어 있음"
    since = (clock.today() - timedelta(days=days - 1)).isoformat()
    if info.get("date") and info["date"] >= since:
        by = f"{info['by_twin']} 님 명단에서 " if info.get("by_twin") else ""
        return f"{by}{info['date']} 에 이 문구를 받음"
    return ""


def clamp_days(value) -> int:
    """화면이 보낸 `N일` — 숫자가 아니면 기본값, 음수는 0, 너무 크면 365."""
    try:
        days = int(value)
    except (TypeError, ValueError):
        return DEFAULT_DAYS
    return max(0, min(days, 365))


# ── 화면이 읽는 것 ──────────────────────────────────────────────────────────

def rows(db: Session, user: User, topic: Topic, days: int) -> dict:
    """[스타트업 안내 카톡] 화면의 표 — 내 스타트업 줄 전부를 **넷으로 가른다.**

      · `ready`    지금 고를 수 있는 줄
      · `recent`   이 문구를 N일 안에 받았거나 대기 중 — 표에 남기되 못 고른다
                   (N 을 0 으로 두면 고를 수 있다)
      · `no_room`  방이 없거나 확인 전 — 접힌 칸에 세우고 방 이름 · [방 연결
                   확인] 으로 이어 준다
      · `excluded` `딜소개 불가` · `검토중단` — 언제나 빠진다

    **조용히 빼지 않는다.** 못 고르는 줄도 어디엔가 서고 까닭이 적힌다 — 빠진
    줄이 안 보이면 "왜 이 기업이 없지" 를 화면에서 물을 수가 없다.
    """
    mine = my_rows(db, user)
    history = last_sent(db, mine, topic)
    out = []
    for c in mine:
        info = history.get(c.id)
        group, hard = _verdict(c)
        recent = "" if hard else recent_reason(info, days)
        state = room_state(c)
        if not group:
            group = "recent" if recent else "ready"
        out.append({
            "contact": c,
            "id": c.id,
            "firm": company_name(c),
            "name": (c.name or "").strip(),
            "contract": contract_of(c),
            "joined": (c.kakao_joined or "").strip(),
            "room": (c.kakao_room_name or "").strip(),
            "room_state": state,
            "room_label": ROOM_LABELS.get(state, state),
            "last_date": (info or {}).get("date", ""),
            "last_pending": (info or {}).get("pending_job", 0),
            "last_by": (info or {}).get("by_twin", ""),
            "reason": hard or recent,
            "group": group,
            "sendable": group == "ready",
            "sheets": sheet_owner.labels_of(c.source_sheet),
        })
    groups = {g: [r for r in out if r["group"] == g]
              for g in ("ready", "recent", NO_ROOM, EXCLUDED)}
    return {
        "rows": out,
        "table": groups["ready"] + groups["recent"],
        **{f"{g}_rows": v for g, v in groups.items()},
        "counts": {g: len(v) for g, v in groups.items()},
        "total": len(out),
        # 방 이름은 있는데 확인 전인 줄 — [방 연결 확인] 을 걸 수 있는 줄이다.
        "verify_ids": [r["id"] for r in groups[NO_ROOM] if r["room"]],
        # 계약여부 거르개에 세울 값 — **지금 이 표에 있는 값**에서 모은다.
        # 명단의 보기(`STARTUP_LAYOUT`)만 세우면 옛 값(`견적서전달` 등)이 든
        # 줄은 걸러 볼 수가 없다.
        "contracts": sorted({r["contract"] for r in out if r["group"] in ("ready", "recent")}),
    }

