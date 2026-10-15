"""Series A 딜 공유 — **받은 딜을 시리즈 A 딜 소싱 네트워크 심사역께 소개한다.**

딜 제안 관리 › 딜 소싱 제안 탭의 [보낼 문구 › Series A 딜 공유]가 이 글을 짓는다.
받는 사람은 딜 소싱 명단의 `시리즈 A 이상 딜 소싱 참여 심사역` 갈래
(`sourcing_sync.SYNC_BUCKET`)에서 `참여` 인 분이고, 소개하는 기업은 IR 기업 현황
메뉴의 `Series A 이상 기업` 탭(`series_a_companies`)의 줄이다.

## 보내는 길은 새로 만들지 않는다

처음 안내 · 월간 리마인드와 **같은 탭 · 같은 길**이다 — 받는 명단 · 미리보기 ·
발송 목록(draft) · [발송 시작] · 예약 · 발송 상한(send_guard) · 방 규칙(시리즈 A
갈래는 자기 딜 소싱 방만, 투자사 방을 이어받지 않는다)이 그대로다. 잡 종류도
`sourcing_intro` 그대로이고(발송 프로그램이 아는 종류), 무슨 글이었는지는
`SendJob.topic = 'sourcing_deal_share'` 가 담는다. 여기는 **글**과 **기록**만 맡는다.

## 글 — 인사말 + 문구 + 기업 덩어리

인사말은 처음 안내와 같은 손이다(`routers/deals._compose_for_contact` — 첫 연락
인사말, 빈 직함은 갈래 호칭). 문구는 갈래마다 하나(`template_pick.
NAME_IS_A_BUCKET`)이고, 고르는 차례도 같다: 갈래 문구 > 갈래 없는 문구 > 코드
뼈대(`default_body`). 문구 속 `{기업 목록}` 자리에 고른 기업이 **기업마다 한
덩어리**로 들어간다(`block`). 자리가 없으면 첫 문단 뒤에 넣는다(`slot`).

기업 덩어리는 딜 소개와 같은 번호 모양(`[기업1]` — `deal_numbers.label`)으로
시작한다. 심사역이 "기업2 IR 부탁드립니다" 로 답하는 그 글자다.

## 기록 — 누가 무엇을 받았나

발송 목록을 만들 때 발송 건마다 `(기업, 사람)` 을 적는다(`record` →
`models.SeriesAShare`). **받았는지는 그 발송 건의 상태가 정한다** — 대기 · 보내는
중 · 보냄만 센다(`LIVE_ITEM`, `twin_send` 와 같은 규칙). 회차를 [중단]하면
저절로 안 센다. **아직 내보내지 않은(draft) 회차**의 대기 건은 만든 지 7일
안에만 센다(`DRAFT_WINDOW_DAYS`) — 예약 시각을 놓쳐 서 있거나 버려진 목록이
그 분을 영영 '받은 분' 으로 막지 않게(`_live_pairs`).

사람이 미리보기에서 **고친 글**로 보내면 기록은 그 글에 실제로 든 기업만이다
(`companies_in` — `[기업N] 기업명` 줄). 고른 기업과 고친 글이 갈려도 나간 글과
기록이 같다.

이미 받은 기업은 기본으로 **그 분 문구에서 뺀다** — 고른 기업을 모두 받은 분은
이번 목록에서 빠진다(조용히 빼지 않는다: 미리보기 경고 · 발송 응답의 `skipped`).
화면의 [이미 이 기업들을 받은 분 제외]를 끄면(`include_shared`) 그대로 다 보낸다.

## 사람마다 몇 곳 — 본인이 공유한 딜은 빼고 앞에서부터 N개

딜 소싱 네트워크로 받은 딜은 **그 딜을 넘겨 준 심사역 본인**도 이 갈래에 있다.
자기가 준 딜을 되받으면 결례라, 그 분께는 **늘** 뺀다(켜고 끄는 칸이 없다 —
`is_own`). 그리고 한 사람에게는 **사람당 N개**(기본 2 — `PER_PERSON_DEFAULT`)만
간다. 그래서 화면에서 기업을 3~4개 고르면 사람마다 ① 본인이 공유한 기업 ②
이미 받은 기업(제외를 켰을 때)을 빼고 **고른 차례 앞에서부터 N개**가 나간다
(`plan`). 모자라면 남은 만큼(1개도 간다), 하나도 안 남으면 그 분은 빠진다
(`NOTHING_LEFT_NOTE`). 기록(`record`)은 **실제로 나간 기업만** 적는다.

본인인지는 `공유 심사역`(`홍길동 이사` 처럼 직함까지 적힌 자유 글자)과 받는
분의 이름을 직함 · 존칭 · 회사 이름 · 띄어쓰기를 떼고 견주고(`person_keys`),
**회사가 양쪽에 다 있으면 회사도 같아야 한다**(`firm_canon` — 한영 · 약칭 표기를
맞춘 뒤 같거나 한쪽이 다른 쪽의 앞부분). 한쪽 회사가 비었으면 이름만으로 본다.
이름은 같은데 회사가 분명히 다르면 동명이인이다 — 본인으로 보지 않는다.

짐작이 틀리는 줄은 탭의 `공유 심사역` 칸에서 사람이 딜 소싱 명단의 그 분으로
**확정**한다(`SeriesACompany.shared_by_contact_id`). 확정한 줄은 짐작하지 않고 그
번호만 본다.

이름 · 회사 · 기업은 전부 화면에서 오는 값이다 — 여기에 적힌 실명은 없다(공개 저장소).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from sqlalchemy import or_, select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import set_committed_value

from .. import clock
from ..models import (SendItem, SendJob, SeriesACompany, SeriesAShare,
                      SourcingContact, User)
from . import deal_history, deal_numbers, room_name, sourcing_msg, twin_send
from . import message_composer as mc
from .sourcing_sync import SYNC_BUCKET

#: 문구 종류 — 딜 소싱 제안 탭의 [보낼 문구]가 고르는 셋째 글. 갈래마다 하나다
#: (`template_pick.NAME_IS_A_BUCKET`).
KIND = sourcing_msg.SHARE_KIND

#: 화면 · 회차명(`09/09 (Series A 딜 공유)`) · 문구 화면이 함께 부르는 이름.
LABEL = "Series A 딜 공유"

#: 이 글을 받는 **하나뿐인** 갈래 — 투자사 관리 현황과 이어진 그 갈래다.
#: 이름을 바꿀 수 없는 갈래라(`sourcing_buckets.rename`) 글자로 견준다.
BUCKET = SYNC_BUCKET

#: 문구 속 기업 자리. 딜 소개 · 자료 전달의 `{기업목록}`(붙여 쓴 것)도 같은
#: 자리로 받는다 — 그 말에 익은 운영자가 붙여 써도 기업이 빠지지 않게.
LIST_TOKEN = "{기업 목록}"
_TOKENS = (LIST_TOKEN, "{기업목록}")

#: 딜소개 문구가 빈 기업은 `상세 내용` 의 첫 문장을 쓴다 — 이 길이까지.
PITCH_MAX = 120

#: 받은 것으로 세는 발송 건 상태 — 나갔거나 · 나가는 중이거나 · 나갈 예정.
#: (`services/twin_send.LIVE_ITEM` 과 같은 규칙: 실패 · 취소는 안 센다)
LIVE_ITEM = ("pending", "sending", "sent")

#: **아직 내보내지 않은(draft) 회차**의 대기 건을 받은 것으로 세는 날 수 — 오늘을
#: 넣어 이만큼(`twin_send.WINDOW_DAYS` 와 같은 폭).
#:
#: 목록을 만들어 두고 [발송 시작] · 예약 시각을 기다리는 동안 또 목록을 만들면
#: 같은 기업이 두 번 나간다 — 그래서 막 만든 draft 는 센다. 그런데 예약 시각을
#: 놓쳐 draft 로 돌아갔거나(`scheduled_send.expire_missed`) 아무도 안 누른 채 버려진
#: 목록까지 기한 없이 세면, 그 분은 **한 번도 못 받았는데** 다음 공유에서 계속
#: 빠진다. 일주일이 지나도 서 있는 draft 는 버려진 것으로 본다. 나중에 누가 그
#: 회차를 내보내면(`queued`) 그때부터 다시 센다 — 상태를 따라가는 규칙 그대로다.
DRAFT_WINDOW_DAYS = twin_send.WINDOW_DAYS

#: 기업을 아직 안 골랐을 때(기본 문구 미리보기 · 문구 화면) 기업 자리에 서는 말.
#: 가짜 기업을 지어 넣지 않는다 — 진짜로 나갈 기업처럼 읽힌다.
SAMPLE_SLOT = "(고른 기업이 이 자리에 기업마다 한 덩어리씩 들어갑니다)"

#: 받는 분이 이 갈래가 아닐 때 — 미리보기 경고 · 발송에서 뺀 이유.
NOT_BUCKET_NOTE = f"{LABEL}는 '{BUCKET}' 갈래에만 보냅니다 — 뺐습니다"
#: 본인이 공유한 기업 · 이미 받은 기업을 빼고 나니 **보낼 기업이 하나도 없는** 분 —
#: 미리보기 경고 · 발송에서 뺀 이유(`skipped`).
NOTHING_LEFT_NOTE = "보낼 기업 없음 (본인 공유/이미 받음)"

#: 사람당 보낼 기업 수 — 기본 · 범위. **화면 기본값과 같아야 한다**
#: (`deals.html` 의 `#sa-per-person`). 위 끝은 한 번에 고를 수 있는 기업 수와 같다.
PER_PERSON_DEFAULT = 2
PER_PERSON_MIN = 1
PER_PERSON_MAX = mc.MAX_COMPANIES_PER_SEND

#: 기업을 그 분 문구에서 뺀 까닭 — 미리보기의 `뺀 기업` 줄에 그대로 선다.
OWN_REASON = "본인이 공유한 딜"
GOT_REASON = "이미 받음"

#: 받는 분이 실제로 있는데 보낼 기업이 없을 때 기업 자리에 서는 말(미리보기만 —
#: 그 분은 발송 목록에서 빠진다). 기본 문구의 `SAMPLE_SLOT` 이 서면 무엇이 나갈지
#: 아직 모르는 글처럼 읽힌다.
NOTHING_SLOT = f"({NOTHING_LEFT_NOTE} — 이 분은 이번 목록에서 빠집니다)"

# 글을 다 짓고 나서 기업 덩어리를 끼우는 표시. 인사말 · 문구가 지나는 치환
# (`message_composer.render_template` — `{직함}` · 존칭 다듬기)을 **기업 글은
# 안 지나게** 하려는 것이다: 상세 내용에 `○○ 님` 같은 글이 있으면 존칭
# 다듬기가 그 띄어쓰기를 지운다.
_SLOT = "⟦SERIES_A_COMPANIES⟧"


# ── 글 ──────────────────────────────────────────────────────────────────────

def default_body() -> str:
    """문구틀이 없을 때 나가는 글 — **글자까지 bootstrap 이 심는 문구와 같다.**

    메일 주소 · 실명은 없다(공개 저장소). 운영에서 고치려면 문구 화면의
    `딜 소싱 제안 — Series A 딜 공유` 구간에서 고친다.
    """
    return "\n".join([
        "Series A 이상 딜 네트워크를 통해 공유드릴 딜이 있어 연락드립니다.",
        "",
        LIST_TOKEN,
        "",
        "관심 있는 기업이 있으시면 편하게 말씀 부탁드립니다.",
        "IR Deck 전달과 기업 담당자 연결 도와드리겠습니다.",
        "",
        "감사합니다.",
    ])


def body_for(db: Session, user: User, bucket: str) -> str:
    """이 갈래에 쓸 문구틀(`{기업 목록}` 이 든 채) — 갈래 문구 > 갈래 없는 문구 > 뼈대.

    고르는 차례는 처음 안내 · 월간 리마인드와 같은 손(`sourcing_msg._picked`)이다.
    """
    return sourcing_msg._picked(db, user, KIND, bucket) or default_body()


def is_share_bucket(bucket: Optional[str]) -> bool:
    return (bucket or "") == BUCKET


def short_series(value: Optional[str]) -> str:
    """`Series A (누적투자금 10억이상, …)` → `Series A` — 표의 `투자라운드` 와 같은 손."""
    from ..routers.series_a import short_series as _short   # noqa: PLC0415

    return _short(value)


#: 머리 글머리표 — `-` · `•` · `1.` · `2)`. 번호 꼴은 **뒤에 띄어쓰기가 올 때만**
#: 글머리표다 — `3.5억 …` 의 `3.` 을 떼면 `5억` 이 나간다.
_BULLET = re.compile(r"^\s*(?:[-•·*▶▪◦]|\d+[.)](?=\s))\s*")
_SENTENCE = re.compile(r"^(.+?[.!?。])(?=\s|$)")


def _lf(text: Optional[str]) -> str:
    """줄바꿈을 `\n` 하나로 — 문구 화면에서 저장한 글은 `\r\n` 으로 올 수 있다.

    `\r\n` 이 남으면 빈 줄(`\n\n`)로 문단을 찾는 자리(`slot`)가 문단을 못 찾아 기업
    덩어리가 맨 끝에 붙고, 카톡에도 `\r` 이 그대로 실린다.
    """
    return (text or "").replace("\r\n", "\n").replace("\r", "\n")


def _flat(text: Optional[str]) -> str:
    """여러 줄 글을 **한 줄**로. 머리 글머리표(`-` · `•` · `1.`)는 뗀다.

    문장으로 끝난 줄은 띄어쓰기로, 아닌 줄(항목 나열)은 ` · ` 로 잇는다 —
    줄바꿈을 그냥 지우면 `스마트팜 관제후속 라운드` 처럼 붙어 버린다.
    """
    lines = [_BULLET.sub("", ln).strip() for ln in (text or "").splitlines()]
    lines = [re.sub(r"\s+", " ", ln) for ln in lines if ln]
    out = ""
    for ln in lines:
        if not out:
            out = ln
        elif re.search(r"[.!?。]$", out):
            out += " " + ln
        else:
            out += " · " + ln
    return out


def pitch_of(row: SeriesACompany) -> str:
    """기업 덩어리의 `소개` — **딜소개 문구가 있으면 그것, 없으면 상세 내용 첫 문장.**

    딜소개 문구는 사람이 이 자리에 쓰려고 적은 글이라 **적힌 그대로** 간다
    (앞뒤 공백 · 빈 줄 겹침만 다듬는다 — 딜 소개의 `딜 소개 문구` 와 같은 결).
    상세 내용은 천 자가 넘는 여러 줄 글이 있어 그대로 실으면 카톡 한 통이
    넘친다 — 한 줄로 펴고(`_flat`) 첫 문장, 그것도 길면 `PITCH_MAX` 자에서 끊는다.
    """
    typed = re.sub(r"\n\s*\n+", "\n", _lf(row.deal_pitch).strip())
    if typed:
        return typed
    flat = _flat(row.detail)
    if not flat:
        return ""
    found = _SENTENCE.match(flat)
    first = found.group(1) if found else flat
    if len(first) <= PITCH_MAX:
        return first
    cut = first[:PITCH_MAX]
    space = cut.rfind(" ")
    if space >= PITCH_MAX * 2 // 3:
        cut = cut[:space]
    return cut.rstrip(" ,·") + "…"


def block(no: int, row: SeriesACompany) -> str:
    """기업 한 덩어리 — `[기업N] 기업명` · 분야 · 투자라운드 · 소개. 빈 칸은 그 줄째 뺀다."""
    lines = [f"{deal_numbers.label(no)} {(row.name or '').strip()}"]
    field = " / ".join(p.strip() for p in (row.sector_major, row.sector_minor)
                       if (p or "").strip())
    if field:
        lines.append(f" · 분야: {field}")
    rnd = short_series(row.series)
    if rnd:
        lines.append(f" · 투자라운드: {rnd}")
    pitch = pitch_of(row)
    if pitch:
        lines.append(f" · 소개: {pitch}")
    return "\n".join(lines)


def blocks(rows: Sequence[SeriesACompany]) -> str:
    """고른 차례 그대로 번호를 붙인 덩어리들(빈 줄로 띄운다)."""
    return "\n\n".join(block(no, row) for no, row in deal_numbers.numbered(list(rows)))


def slot(template_body: str) -> str:
    """문구틀의 `{기업 목록}` 을 끼울 표시로. **자리가 없으면 첫 문단 뒤에** 둔다.

    자리가 여럿이면 첫 자리에만 넣고 나머지는 지운다 — 같은 목록이 두 번 나가면
    결례다. 문구가 한 문단뿐이면 그 뒤에 붙인다.
    """
    body = _lf(template_body).strip()
    hits = [(body.find(t), t) for t in _TOKENS if t in body]
    if hits:
        _at, token = min(hits)
        body = body.replace(token, _SLOT, 1)
        for t in _TOKENS:
            body = body.replace(t, "")
        return body
    parts = re.split(r"\n[ \t]*\n", body, maxsplit=1)
    if len(parts) == 2:
        return f"{parts[0].rstrip()}\n\n{_SLOT}\n\n{parts[1].lstrip()}"
    return f"{body}\n\n{_SLOT}" if body else _SLOT


def fill(result: mc.ComposeResult, companies_text: str) -> mc.ComposeResult:
    """지은 글의 표시 자리에 기업 덩어리를 넣고, 글자 수 · 길이 경고를 다시 센다."""
    text = _lf(result.text).replace(_SLOT, _lf(companies_text) or SAMPLE_SLOT)
    text = re.sub(r"\n{3,}", "\n\n", text).strip() + "\n"
    count = len(text)
    too_long = count > mc.MESSAGE_WARN_CHARS
    # 길이 경고는 composer 가 표시 자리로 센 것이라 버리고 다시 단다(같은 말로).
    warnings = [w for w in result.warnings if not w.startswith("메시지가 ")]
    if too_long:
        warnings.append(
            f"메시지가 {count}자로 {mc.MESSAGE_WARN_CHARS}자를 초과했습니다 "
            "(카톡 장문 붙여넣기 안정성 주의).")
    return mc.ComposeResult(text=text, char_count=count, too_long=too_long,
                            warnings=warnings, parts=list(result.parts))


# ── 고른 기업 ───────────────────────────────────────────────────────────────

class MissingCompany(LookupError):
    """없는 기업 번호. 화면에 그대로 띄운다(404)."""


def load(db: Session, ids: Iterable[int]) -> List[SeriesACompany]:
    """고른 차례 그대로. 같은 번호는 한 번만, 없는 번호는 **말하고 멈춘다.**"""
    out: List[SeriesACompany] = []
    seen: Set[int] = set()
    for raw in ids or []:
        cid = int(raw)
        if cid in seen:
            continue
        seen.add(cid)
        row = db.get(SeriesACompany, cid)
        if row is None:
            raise MissingCompany(f"Series A 이상 기업 {cid} 없음")
        out.append(row)
    return out


# ── 기록 ────────────────────────────────────────────────────────────────────

def _live_pairs(db: Session, company_ids: Optional[Iterable[int]] = None,
                contact_ids: Optional[Iterable[int]] = None) -> Set[Tuple[int, int]]:
    """`(기업, 사람)` — **살아 있는 발송 건**에 실린 것만(머리말 `기록`).

    draft 회차의 건은 만든 지 `DRAFT_WINDOW_DAYS` 안의 것만 센다(그 상수 설명).
    """
    since = (clock.today() - timedelta(days=DRAFT_WINDOW_DAYS - 1)).isoformat()
    stmt = (select(SeriesAShare.series_a_company_id, SeriesAShare.sourcing_contact_id)
            .join(SendItem, SendItem.id == SeriesAShare.send_item_id)
            .join(SendJob, SendJob.id == SendItem.job_id)
            .where(SendItem.status.in_(LIVE_ITEM), SendJob.status != "canceled",
                   or_(SendJob.status != "draft", SendItem.created_at >= since)))
    if company_ids is not None:
        stmt = stmt.where(SeriesAShare.series_a_company_id.in_(list(company_ids)))
    if contact_ids is not None:
        stmt = stmt.where(SeriesAShare.sourcing_contact_id.in_(list(contact_ids)))
    return {(c, p) for c, p in db.execute(stmt).all()}


def contacts_by_company(db: Session) -> Dict[int, Set[int]]:
    """기업 → 그 기업을 받은 심사역들. 고르개의 `이미 받은 분` · 탭의 `공유한 심사역`."""
    out: Dict[int, Set[int]] = {}
    for company_id, contact_id in _live_pairs(db):
        out.setdefault(company_id, set()).add(contact_id)
    return out


def companies_by_contact(db: Session,
                         contact_ids: Optional[Iterable[int]] = None,
                         company_ids: Optional[Iterable[int]] = None
                         ) -> Dict[int, Set[int]]:
    """심사역 → 받은 기업들. 발송에서 이미 받은 기업을 빼는 자리 · 딜 소싱 줄의 `N건`."""
    out: Dict[int, Set[int]] = {}
    for company_id, contact_id in _live_pairs(db, company_ids, contact_ids):
        out.setdefault(contact_id, set()).add(company_id)
    return out


def shared_people(db: Session) -> Dict[int, List[str]]:
    """기업 → 받은 심사역 `이름(회사)` — 탭의 `공유한 심사역` 칸 풍선말."""
    by_company = contacts_by_company(db)
    ids = {cid for people in by_company.values() for cid in people}
    if not ids:
        return {}
    rows = {r.id: r for r in db.execute(
        select(SourcingContact).where(SourcingContact.id.in_(ids))).scalars()}
    out: Dict[int, List[str]] = {}
    for company_id, people in by_company.items():
        names = []
        for cid in people:
            row = rows.get(cid)
            if row is None:
                continue
            firm = (row.firm or "").strip()
            names.append(f"{row.name}({firm})" if firm else row.name)
        out[company_id] = sorted(names)
    return out


def shared_companies(db: Session, contact_ids: Iterable[int]) -> Dict[int, List[str]]:
    """심사역 → 받은 기업 이름들(가나다순) — 딜 소싱 줄의 `Series A 딜 공유 N건` 과 풍선말."""
    by_contact = companies_by_contact(db, contact_ids=list(contact_ids))
    ids = {cid for got in by_contact.values() for cid in got}
    if not ids:
        return {}
    names = {r.id: (r.name or "").strip() for r in db.execute(
        select(SeriesACompany).where(SeriesACompany.id.in_(ids))).scalars()}
    return {contact_id: sorted(names[c] for c in got if c in names)
            for contact_id, got in by_contact.items()}


def _names(rows: Sequence[SeriesACompany]) -> str:
    return ", ".join((c.name or "").strip() for c in rows)


def partial_note(old: Sequence[SeriesACompany]) -> str:
    """일부를 이미 받은 분 — 미리보기 경고."""
    return f"이미 받은 기업 {len(old)}곳은 이 분 문구에서 뺐습니다: {_names(old)}"


def own_note(own: Sequence[SeriesACompany]) -> str:
    """본인이 공유한 기업이 고른 것에 든 분 — 미리보기 경고."""
    return f"{OWN_REASON} {len(own)}곳은 이 분 문구에서 뺐습니다: {_names(own)}"


def resend_note(old: Sequence[SeriesACompany]) -> str:
    """제외를 끄고 이미 받은 기업을 다시 보내는 분 — 미리보기 경고."""
    return f"이미 받은 기업 {len(old)}곳도 다시 보냅니다: {_names(old)}"


def per_person_hint(per_person: int = PER_PERSON_DEFAULT) -> str:
    """고르개 옆 안내 — 몇 개를 고르면 사람마다 몇 개가 가는지.

    고를 개수는 `N ~ 2N`(10개 한도)로 권한다 — 본인 공유 · 이미 받은 기업을 빼고도
    대개 N개가 남는 폭이다. **화면도 같은 식으로 고쳐 쓴다**(`deals.js` 의
    `perPersonHint`) — 칸을 바꾸면 이 글도 따라 바뀐다.
    """
    top = min(per_person * 2, PER_PERSON_MAX)
    span = f"{per_person}~{top}" if top > per_person else f"{per_person}"
    return (f"기업을 {span}개 고르면 사람마다 본인 공유·이미 받은 기업을 빼고 "
            f"앞에서부터 {per_person}개씩 나갑니다.")


def over_reason(per_person: int) -> str:
    """앞의 N개가 다 차서 이 분께는 이번에 안 가는 기업 — `뺀 기업` 줄의 까닭."""
    return f"사람당 {per_person}개 — 이번엔 안 보냄"


def short_note(per_person: int, sent: int) -> str:
    """남은 기업이 N개보다 적어 그만큼만 가는 분 — 미리보기 경고(그래도 보낸다)."""
    return f"사람당 {per_person}개 중 {sent}개만 나갑니다 — 본인 공유 · 이미 받은 기업을 빼니 모자랍니다"


# ── 본인이 공유한 딜 ────────────────────────────────────────────────────────
#
# `공유 심사역` 칸은 사람이 시트에 손으로 적은 글자다 — `홍길동 이사` ·
# `홍길동 이사님` · `홍길동이사` · `홍길동 이사(가나벤처스)` 뿐 아니라
# `가나벤처스 홍길동 이사`(회사명 이름 직함) · `이사 홍길동`(직함 이름) ·
# `홍길동 CEO`(영문 직함) · `홍길동 대표 겸 파트너`(겸직) · `홍길동 이사/김철수 팀장`
# (여럿)으로도 온다. 딜 소싱 명단의 이름 칸에도 직함이 섞여 있다
# (`message_composer.name_carries_title`). 그래서 양쪽 모두 같은 손으로 직함 ·
# 존칭 · 괄호 · 회사 이름 · 띄어쓰기를 떼고 견준다.
#
# 짐작이 틀리는 줄은 사람이 탭에서 확정한다(`SeriesACompany.shared_by_contact_id`) —
# 확정한 줄은 여기 짐작을 지나지 않는다(`is_own`).

#: 이름 **앞뒤에 붙어 온** 한글 직함 — 띄어 쓴 낱말은 `room_name.looks_like_title` 이
#: 가리고(방 이름 어휘 + 아래 낱말), 붙여 쓴 것은 이 목록의 꼬리를 뗀다.
#: 방 이름 어휘를 넓히지 않으려고(`room_name.looks_like_title` 머리말) 여기서만 더한다.
_EXTRA_TITLES = mc._GREETING_TITLE_WORDS + (
    "대표이사", "씨", "공동대표", "대표파트너", "매니징파트너", "제너럴파트너",
    "벤처파트너", "투자심사역", "그룹장", "디렉터", "프린시펄", "어소시에이트",
    "애널리스트", "상무이사", "전무이사")
_GLUED_TITLES = tuple(sorted(set(room_name._TITLE_WORDS + _EXTRA_TITLES),
                             key=len, reverse=True))
#: 영문 직함 — 소문자로, 띄어 쓴 **낱말 하나하나**로 견준다(`Managing Director` 는
#: 두 낱말 다 이 목록에 있다). `Partners` 는 직함이 아니라 회사 꼬리다(`_FIRM_TAILS`).
_EN_TITLES = frozenset((
    "ceo", "cfo", "cto", "coo", "cio", "cso", "cmo", "cpo",
    "vp", "svp", "evp", "avp", "md", "gp", "partner", "managing", "general",
    "director", "principal", "associate", "analyst", "manager", "head",
    "president", "vice", "senior", "junior", "chief", "officer", "executive",
    "founder", "co-founder", "cofounder", "chairman", "lead", "investor",
    "mr", "ms", "mrs", "dr"))
#: 붙여 쓴 영문 직함(`홍길동CEO`) — 두 글자 이상인 것만, 긴 것부터.
_GLUED_EN = tuple(sorted((t for t in _EN_TITLES if len(t) >= 2), key=len, reverse=True))
_HANGUL = re.compile(r"[가-힣]")
#: 겸직을 잇는 말 — `대표 겸 파트너` · `대표겸파트너`.
_JOIN = "겸"
#: 한 칸에 여럿이 적힌 경우(`가 이사, 나 팀장` · `가 이사/나 팀장`)를 사람마다 가른다.
#: `/` 로도 가른다 — 한 사람의 겸직(`이사/변호사`)은 갈라도 뒤 조각이 직함뿐이라
#: 사람으로 안 센다(`person_keys`).
_PEOPLE_SPLIT = re.compile(r"[,，;&\n·ㆍ/、+]|\s및\s|\sand\s", re.I)
_BRACKETS = re.compile(r"\([^)]*\)|\[[^\]]*\]|（[^）]*）")

#: 회사 이름의 한영 · 다른 표기를 한 가지로(`firm_canon`). 긴 것부터 바꾼다 —
#: `investments` 를 `invest` 보다 먼저.
_FIRM_WORDS = (
    ("assetmanagement", "자산운용"),
    ("investments", "인베스트"), ("investment", "인베스트"), ("인베스트먼트", "인베스트"),
    ("invest", "인베스트"),
    ("partners", "파트너스"), ("파트너즈", "파트너스"),
    ("자산운용사", "자산운용"), ("자산운영", "자산운용"),
    ("ventures", "벤처스"), ("venture", "벤처"), ("벤쳐", "벤처"),
    ("capital", "캐피탈"), ("캐피털", "캐피탈"),
)
#: 회사 이름의 꼬리(맞춘 뒤의 글자). 이것으로 끝나는 낱말은 사람 이름이 아니라
#: 회사 이름이다 — `가나벤처스 홍길동 이사` 의 `가나벤처스`.
#:
#: 가리기의 꼬리말 목록(`ir_mask.FIRM_SUFFIXES` — 투자사 이름에서 **드러낼** 꼬리)과
#: 하는 일이 다르다. 그쪽은 가린 뒤에도 보일 말만 담고(`벤처스` · `캐피탈` 은 일부러
#: 뺐다), 여기는 공유 심사역 칸에서 **회사 낱말을 알아보는** 말을 담는다.
_FIRM_TAILS = ("벤처스", "벤처캐피탈", "벤처투자", "인베스트", "파트너스", "캐피탈",
                  "자산운용", "투자", "홀딩스", "증권", "액셀러레이터", "엑셀러레이터")


def firm_key(raw: Optional[str]) -> str:
    """견줄 회사 이름 — `(주)` · 띄어쓰기 · 대소문자(`deal_history._key` 와 같은 손)."""
    return deal_history._key(raw)


def firm_canon(raw: Optional[str]) -> str:
    """`firm_key` 에 **한영 · 다른 표기**까지 맞춘 것.

    `가나 Investment` · `가나인베스트먼트` → `가나인베스트`, `가나 Partners` →
    `가나파트너스`, `가나AM` · `가나 Asset Management` → `가나자산운용`.
    `AM` 은 한글 바로 뒤에 붙었을 때만 자산운용으로 읽는다(영문 이름 속 `am` 을
    바꾸지 않게).
    """
    key = firm_key(raw)
    for src, dst in _FIRM_WORDS:
        key = key.replace(src, dst)
    if key.endswith("am") and len(key) > 2 and _HANGUL.match(key[-3]):
        key = key[:-2] + "자산운용"
    return key


def _firms_agree(a: str, b: str) -> bool:
    """맞춘 회사 이름 둘(`firm_canon`)이 같은 회사인가 — 같거나, **한쪽이 다른 쪽의
    앞부분**이다(`가나` ↔ `가나벤처스` 같은 약칭). 앞부분은 두 글자 이상이어야 한다.

    꼬리만 다른 같은 머리(`가나벤처스` ↔ `가나캐피탈`)는 다른 회사로 본다 — 같은
    이름의 다른 분일 수 있다. 같은 분이면 사람이 탭에서 확정한다.
    """
    if a == b:
        return True
    short, long_ = sorted((a, b), key=len)
    return len(short) >= 2 and long_.startswith(short)


def _firms_match(a: str, b: str) -> bool:
    """한쪽이 비었으면 견줄 것이 없을 뿐 어긋난 것이 아니다(머리말)."""
    return not a or not b or _firms_agree(a, b)


def _one_title(word: str) -> bool:
    w = word.strip()
    if not w.rstrip("님"):
        return True                    # `님` 하나만 떨어져 있다
    if room_name.looks_like_title(w, _EXTRA_TITLES):
        return True
    return w.rstrip("님").lower().rstrip(".") in _EN_TITLES


def _is_title(token: str) -> bool:
    """이 낱말이 직함인가 — `이사` · `이사님` · `CEO` · `이사/변호사` · `대표겸파트너` · `겸`."""
    head = token.split("/")[0].strip()
    if head == _JOIN or _one_title(head):
        return True
    pieces = head.split(_JOIN)
    return len(pieces) > 1 and all(p and _one_title(p) for p in pieces)


def _firm_suffix_only(token: str) -> bool:
    """회사 꼬리만 떨어져 있다 — `가나 Ventures` 의 `Ventures`."""
    return firm_canon(token) in _FIRM_TAILS


def _is_firm_word(token: str, firm: str) -> bool:
    """이 낱말이 회사 이름인가 — 회사 꼬리로 끝나거나(`가나벤처스`), 그 줄의 회사와
    맞는다(`가나` ↔ 줄의 회사 `가나벤처스`). `firm` 은 맞춘 회사 이름(`firm_canon`)."""
    canon = firm_canon(token)
    if len(canon) < 2:
        return False
    if firm and _firms_agree(canon, firm):
        return True
    return any(canon.endswith(sfx) for sfx in _FIRM_TAILS)


def _merge_firm_tails(tokens: List[str]) -> List[str]:
    """`가나 Ventures 홍길동` → `가나Ventures 홍길동` — 회사 꼬리를 앞 낱말에 붙인다.

    붙이고 나서 사람 이름으로 남는 낱말이 없으면(`홍길동 Partners`) 붙이지 않는다 —
    이름을 회사로 삼켜 버린다.
    """
    out: List[str] = []
    for tok in tokens:
        if out and _firm_suffix_only(tok) and not _is_title(out[-1]):
            out[-1] = out[-1] + tok
        else:
            out.append(tok)
    return out if len(out) > 1 else tokens


def _strip_glued(key: str) -> str:
    """붙여 쓴 직함을 꼬리부터 뗀다 — `홍길동상무이사` · `홍길동대표겸파트너` · `홍길동CEO`.

    **두 글자 이상 남을 때만** 뗀다 — `김이사` 를 `김` 으로 자르면 아무나와 맞는다.
    영문 직함은 한글 바로 뒤에 붙었을 때만 뗀다(영문 이름을 자르지 않게).
    """
    while True:
        hit = next((t for t in _GLUED_TITLES
                    if key.endswith(t) and len(key) - len(t) >= 2), None)
        if hit is None:
            low = key.lower()
            hit = next((t for t in _GLUED_EN
                        if low.endswith(t) and len(key) - len(t) >= 2
                        and _HANGUL.match(key[-len(t) - 1])), None)
        if hit is None:
            return key
        key = key[:-len(hit)]
        # `…대표겸` — 앞이 직함으로 끝나면 `겸` 도 직함을 잇는 말이다
        if key.endswith(_JOIN) and any(key[:-1].endswith(t) for t in _GLUED_TITLES):
            key = key[:-1]


def person_key(raw: Optional[str], firm: Optional[str] = None) -> str:
    """사람 한 명의 견줄 이름 — 직함 · 존칭 · 괄호 · 회사 이름 · 띄어쓰기를 뗀다.
    못 지으면 빈 글자.

    `홍길동 이사님` · `홍길동이사` · `홍길동 (가나벤처스)` · `가나벤처스 홍길동 이사` ·
    `이사 홍길동` · `홍길동 CEO` · `홍길동 대표 겸 파트너` → `홍길동`. `firm` 을 주면
    (그 줄의 회사) 회사 꼬리가 없는 약칭(`가나 홍길동`)도 회사로 보고 뗀다.

    앞뒤 낱말은 **사람 이름이 하나 남을 때까지만** 뗀다.
    """
    text = room_name.normalize_space(_BRACKETS.sub(" ", raw or ""))
    if not text:
        return ""
    canon = firm_canon(firm)
    tokens = _merge_firm_tails(text.split(" "))

    def junk(tok: str) -> bool:
        return _is_title(tok) or _is_firm_word(tok, canon)

    while len(tokens) > 1 and junk(tokens[-1]):
        tokens.pop()
    while len(tokens) > 1 and junk(tokens[0]):
        tokens.pop(0)
    key = _strip_glued("".join(tokens).rstrip("님"))
    return key.lower()


def person_keys(raw: Optional[str], firm: Optional[str] = None) -> Set[str]:
    """`공유 심사역` 칸의 사람들 — 한 칸에 여럿이 적혀 있으면 모두."""
    keys = {person_key(part, firm) for part in _PEOPLE_SPLIT.split(raw or "")}
    # 직함만 떨어져 남은 조각(`… , 이사` · `이사/변호사` 의 `변호사`)은 사람이 아니다.
    return {k for k in keys if k and not _is_title(k)}


def _row_sig(row: SeriesACompany) -> Tuple[Set[str], str]:
    """줄 쪽 견줄 것 — (공유 심사역 이름들, 맞춘 회사 이름)."""
    return person_keys(row.shared_by, row.source_firm), firm_canon(row.source_firm)


def _contact_sig(contact) -> Tuple[str, str]:
    """받는 분 쪽 견줄 것 — (이름, 맞춘 회사 이름)."""
    return (person_key(getattr(contact, "name", "")),
            firm_canon(getattr(contact, "firm", "")))


def _confirmed(row) -> Optional[int]:
    return getattr(row, "shared_by_contact_id", None)


def is_own(row: SeriesACompany, contact) -> bool:
    """이 기업은 **이 분이 공유해 준 딜**인가.

    사람이 확정한 줄(`shared_by_contact_id`)은 **그 번호만** 본다. 아니면 이름
    (`person_keys` ↔ 받는 분 이름)이 같아야 하고, **회사가 양쪽에 다 있으면** 회사도
    맞아야 한다(`firm_canon` · `_firms_agree`). 한쪽 회사가 비었으면(대개 줄의 `회사`
    칸이 비었다) 이름만으로 본다 — 견줄 것이 없을 뿐 어긋난 것은 아니다. 이름이
    같아도 회사가 분명히 다르면 동명이인으로 보고 **본인으로 보지 않는다.**
    """
    confirmed = _confirmed(row)
    if confirmed is not None:
        return getattr(contact, "id", None) == confirmed
    keys, firm = _row_sig(row)
    who, their = _contact_sig(contact)
    return bool(who) and who in keys and _firms_match(firm, their)


def _bucket_people(db: Session) -> List[SourcingContact]:
    return db.execute(select(SourcingContact).where(
        SourcingContact.bucket == BUCKET)).scalars().all()


def _name_index(people: Iterable) -> Dict[str, List[Tuple[object, str]]]:
    """이름 → [(사람, 맞춘 회사)] — 사람마다 **한 번만** 이름을 푼다."""
    out: Dict[str, List[Tuple[object, str]]] = {}
    for p in people:
        who, firm = _contact_sig(p)
        if who:
            out.setdefault(who, []).append((p, firm))
    return out


def own_by_company(db: Session, rows: Sequence[SeriesACompany]) -> Dict[int, List[int]]:
    """기업 → **그 딜을 공유해 준** 이 갈래 심사역 번호들. 고르개의 `본인 공유 N명 제외`.

    갈래의 줄 전부(불참여도)를 본다 — 화면이 지금 고른 받는 분과 견준다. 사람 이름은
    한 번씩만 풀어 이름으로 찾는다(`_name_index`) — (기업 × 사람)마다 이름을 다시
    풀면 줄이 늘수록 /deals 가 느려진다. 결과는 `is_own` 과 같다.
    """
    people = _bucket_people(db)
    index = _name_index(people)
    ids_in_bucket = {p.id for p in people}
    out: Dict[int, List[int]] = {}
    for row in rows:
        confirmed = _confirmed(row)
        if confirmed is not None:
            if confirmed in ids_in_bucket:
                out[row.id] = [confirmed]
            continue
        keys, firm = _row_sig(row)
        ids = sorted({p.id for key in keys for p, their in index.get(key, ())
                      if _firms_match(firm, their)})
        if ids:
            out[row.id] = ids
    return out


def _person_label(p) -> str:
    """`홍길동 이사 (가나벤처스)` — 탭의 `공유 심사역` 칸 아래 후보 · 확정 줄."""
    who = " ".join(x for x in ((p.name or "").strip(), (p.title or "").strip()) if x)
    firm = (p.firm or "").strip()
    return f"{who} ({firm})" if firm else who


def sharer_views(db: Session, rows: Sequence[SeriesACompany]) -> Dict[int, dict]:
    """줄 → `공유 심사역` 칸 아래에 띄울 것 — 확정한 분 · 이름이 같은 후보들.

    `candidates[].auto` 는 지금 짐작(`is_own`)이 이 분을 본인으로 보는가 — 이름과
    회사가 다 맞는다. 이름만 같고 회사가 다르면 거짓이다(그래도 후보로 띄운다 —
    이직했거나 회사 표기가 크게 다를 수 있다).
    """
    people = _bucket_people(db)
    index = _name_index(people)
    by_id = {p.id: p for p in people}
    out: Dict[int, dict] = {}
    for row in rows:
        confirmed = None
        cid = _confirmed(row)
        if cid is not None:
            p = by_id.get(cid) or db.get(SourcingContact, cid)
            confirmed = {"id": cid, "label": _person_label(p) if p else f"#{cid}"}
        keys, firm = _row_sig(row)
        seen: Set[int] = set()
        cands = []
        for key in sorted(keys):
            for p, their in index.get(key, ()):
                if p.id in seen:
                    continue
                seen.add(p.id)
                cands.append({"id": p.id, "label": _person_label(p),
                              "auto": _firms_match(firm, their)})
        cands.sort(key=lambda c: (not c["auto"], c["label"]))
        out[row.id] = {"confirmed": confirmed, "candidates": cands}
    return out


def sharer_view(db: Session, row: SeriesACompany) -> dict:
    return sharer_views(db, [row])[row.id]


def forget_sharers(session: Session, contact_ids: List[int]) -> None:
    """지워지는 딜 소싱 줄을 **확정한 공유 심사역**으로 가리키던 칸을 비운다.

    `models._forget_series_a_sharers` 가 flush 직전에 부른다. ORM 으로 고치지 않고
    바로 적는다 — 같은 flush 안에서 줄을 고치고 소싱 줄을 지우면 어느 쪽이 먼저
    나갈지 SQLAlchemy 가 몰라 외래키에 막힐 수 있다(`sourcing_sync.detach` 와 같은
    까닭). 세션에 올라와 있는 줄은 값만 맞춘다.
    """
    ids = [i for i in contact_ids if i]
    if not ids:
        return
    table = SeriesACompany.__table__
    session.execute(table.update().where(table.c.shared_by_contact_id.in_(ids))
                    .values(shared_by_contact_id=None))
    for obj in list(session.identity_map.values()):
        if isinstance(obj, SeriesACompany) and obj.shared_by_contact_id in ids:
            set_committed_value(obj, "shared_by_contact_id", None)


# ── 사람마다 무엇을 보내나 ───────────────────────────────────────────────────

@dataclass
class Plan:
    """한 분께 나갈 기업 · 뺀 기업(까닭과 함께) — 고른 차례 그대로."""

    send: List[SeriesACompany] = field(default_factory=list)
    #: (기업, 까닭) — `OWN_REASON` · `GOT_REASON` · `over_reason(N)`.
    dropped: List[Tuple[SeriesACompany, str]] = field(default_factory=list)
    #: 이미 받았는데 제외를 꺼서 다시 가는 기업(`send` 의 일부).
    resent: List[SeriesACompany] = field(default_factory=list)

    def dropped_for(self, reason: str) -> List[SeriesACompany]:
        return [c for c, why in self.dropped if why == reason]


def plan(contact, companies: Sequence[SeriesACompany], got: Dict[int, Set[int]],
         per_person: int, include_shared: bool = False) -> Plan:
    """**이 분께 나갈 기업** — 고른 차례에서 ① 본인이 공유한 기업(늘) ② 이미 받은
    기업(제외를 켰을 때)을 빼고 앞에서부터 `per_person` 개.

    미리보기와 발송 목록 만들기가 **이 함수 하나**를 지난다 — 둘이 따로 고르면
    미리보기에서 본 기업과 나가는 기업이 갈린다.
    """
    have = got.get(contact.id, set())
    out = Plan()
    for company in companies:
        if is_own(company, contact):
            out.dropped.append((company, OWN_REASON))
        elif company.id in have and not include_shared:
            out.dropped.append((company, GOT_REASON))
        elif len(out.send) >= per_person:
            out.dropped.append((company, over_reason(per_person)))
        else:
            out.send.append(company)
            if company.id in have:
                out.resent.append(company)
    return out


def plan_notes(p: Plan, per_person: int) -> List[str]:
    """미리보기 경고 — 무엇을 왜 뺐는지. 조용히 빼지 않는다."""
    notes = []
    own = p.dropped_for(OWN_REASON)
    if own:
        notes.append(own_note(own))
    got = p.dropped_for(GOT_REASON)
    if got:
        notes.append(partial_note(got))
    if p.resent:
        notes.append(resend_note(p.resent))
    if not p.send:
        notes.append(NOTHING_LEFT_NOTE + " — 이번 목록에서 뺐습니다")
    elif len(p.send) < per_person and (own or got):
        notes.append(short_note(per_person, len(p.send)))
    return notes


def plan_view(p: Plan) -> dict:
    """미리보기 응답에 싣는 모양 — 화면이 `보내는 기업` · `뺀 기업` 줄을 그린다."""
    return {
        "send": [{"id": c.id, "name": (c.name or "").strip(),
                  "label": deal_numbers.label(no)}
                 for no, c in deal_numbers.numbered(list(p.send))],
        "dropped": [{"id": c.id, "name": (c.name or "").strip(), "reason": why}
                    for c, why in p.dropped],
    }


#: 기업 덩어리의 첫 줄 — `[기업2] 샘플바이오`(`block`). 번호 꼴은 `deal_numbers.
#: parse_label` 이 읽는 그 모양이다(사람이 띄어 써도 받는다).
_HEADER = re.compile(r"^[ \t]*(\[[^\]\n]*\])[ \t]*(\S[^\n]*?)[ \t]*$", re.M)


def _name_key(name: Optional[str]) -> str:
    return re.sub(r"\s+", " ", (name or "").strip())


def companies_in(text: Optional[str],
                 candidates: Sequence[SeriesACompany]) -> List[SeriesACompany]:
    """나간 글에 **실제로 든** 기업 — `[기업N] 기업명` 줄로 찾는다(글에 나온 차례).

    사람이 미리보기에서 고친 글(`overrides`)로 보낼 때 기록이 이것을 따른다. 고친
    글은 그 시점의 고른 기업으로 지어진 것이라, 기업을 바꾼 뒤 예전에 고친 글이
    되살아나 나가면 지금 고른 기업(`plan`)과 글이 갈린다 — 그대로 적으면 글에 없는
    기업을 '받음' 으로 적어 그 분은 그 기업을 영영 못 받는다. 덩어리를 지웠으면
    그 기업은 안 적는다. 견주는 것은 `candidates`(이번에 고른 기업)의 이름이다.
    """
    by_name: Dict[str, SeriesACompany] = {}
    for c in candidates:
        by_name.setdefault(_name_key(c.name), c)
    out: List[SeriesACompany] = []
    seen: Set[int] = set()
    for m in _HEADER.finditer(_lf(text)):
        if deal_numbers.parse_label(m.group(1)) is None:
            continue
        hit = by_name.get(_name_key(m.group(2)))
        if hit is not None and hit.id not in seen:
            seen.add(hit.id)
            out.append(hit)
    return out


def record(db: Session, item: SendItem, contact_id: int,
           companies: Sequence[SeriesACompany], user: Optional[User]) -> None:
    """이 발송 건에 실린 기업을 적는다. `item` 은 flush 되어 번호가 있어야 한다."""
    for no, company in deal_numbers.numbered(list(companies)):
        db.add(SeriesAShare(series_a_company_id=company.id,
                            sourcing_contact_id=contact_id,
                            send_item_id=item.id, position=no,
                            user_id=user.id if user is not None else None))


def delete_for_company(db: Session, company_id: int) -> int:
    """`Series A 이상 기업` 줄을 지울 때 그 기업의 공유 기록도 — 가리킬 곳 없는 줄을 남기지 않는다.

    나간 문구 자체는 발송 건(`send_items.message`)에 그대로 남는다.
    """
    return db.query(SeriesAShare).filter(
        SeriesAShare.series_a_company_id == company_id).delete(
        synchronize_session=False)
