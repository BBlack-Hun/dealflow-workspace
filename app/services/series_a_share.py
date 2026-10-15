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
저절로 안 센다.

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
분의 이름을 직함 · 존칭 · 띄어쓰기를 떼고 견주고(`person_keys`), **회사가 양쪽에
다 있으면 회사도 같아야 한다**(`firm_key` — `deal_history._key` 와 같은 손).
한쪽 회사가 비었으면 이름만으로 본다. 이름은 같은데 회사가 다르면 동명이인이다 —
본인으로 보지 않는다.

이름 · 회사 · 기업은 전부 화면에서 오는 값이다 — 여기에 적힌 실명은 없다(공개 저장소).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (SendItem, SendJob, SeriesACompany, SeriesAShare,
                      SourcingContact, User)
from . import deal_history, deal_numbers, room_name, sourcing_msg
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


_BULLET = re.compile(r"^\s*(?:[-•·*▶▪◦]|\d+[.)])\s*")
_SENTENCE = re.compile(r"^(.+?[.!?。])(?=\s|$)")


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
    typed = re.sub(r"\n\s*\n+", "\n", (row.deal_pitch or "").strip())
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
    body = (template_body or "").strip()
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
    text = result.text.replace(_SLOT, companies_text or SAMPLE_SLOT)
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
    """`(기업, 사람)` — **살아 있는 발송 건**에 실린 것만(머리말 `기록`)."""
    stmt = (select(SeriesAShare.series_a_company_id, SeriesAShare.sourcing_contact_id)
            .join(SendItem, SendItem.id == SeriesAShare.send_item_id)
            .join(SendJob, SendJob.id == SendItem.job_id)
            .where(SendItem.status.in_(LIVE_ITEM), SendJob.status != "canceled"))
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
# `홍길동 이사님` · `홍길동이사` · `홍길동 이사(가나벤처스)` 처럼 온다. 딜 소싱 명단의
# 이름 칸에도 직함이 섞여 있다(`message_composer.name_carries_title`). 그래서 양쪽
# 모두 같은 손으로 직함 · 존칭 · 괄호 · 띄어쓰기를 떼고 견준다.

#: 이름 **뒤에 붙어 온** 직함 — 띄어 쓴 낱말은 `room_name.looks_like_title` 이
#: 가리고(방 이름 어휘 + 아래 낱말), 붙여 쓴 것은 이 목록의 꼬리를 뗀다.
#: 방 이름 어휘를 넓히지 않으려고(`room_name.looks_like_title` 머리말) 여기서만 더한다.
_EXTRA_TITLES = mc._GREETING_TITLE_WORDS + ("대표이사", "씨")
_GLUED_TITLES = tuple(sorted(set(room_name._TITLE_WORDS + _EXTRA_TITLES),
                             key=len, reverse=True))
#: 한 칸에 여럿이 적힌 경우(`가 이사, 나 팀장`)를 사람마다 가른다. `/` 는 가르지
#: 않는다 — `이사/변호사` 처럼 한 사람의 겸직을 잇는 데 쓴다.
_PEOPLE_SPLIT = re.compile(r"[,;&\n·ㆍ]|\s및\s")
_BRACKETS = re.compile(r"\([^)]*\)|\[[^\]]*\]|（[^）]*）")


def _is_title(token: str) -> bool:
    head = token.split("/")[0].strip()
    if not head.rstrip("님"):
        return True                    # `님` 하나만 떨어져 있다
    return room_name.looks_like_title(head, _EXTRA_TITLES)


def person_key(raw: Optional[str]) -> str:
    """사람 한 명의 견줄 이름 — 직함 · 존칭 · 괄호 · 띄어쓰기를 뗀다. 못 짓으면 빈 글자.

    `홍길동 이사님` · `홍길동이사` · `홍길동 (가나벤처스)` → `홍길동`. 붙여 쓴 직함은
    **두 글자 이상 남을 때만** 뗀다 — `김이사` 를 `김` 으로 자르면 아무나와 맞는다.
    """
    text = room_name.normalize_space(_BRACKETS.sub(" ", raw or ""))
    if not text:
        return ""
    tokens = text.split(" ")
    while len(tokens) > 1 and _is_title(tokens[-1]):
        tokens.pop()
    key = "".join(tokens).rstrip("님")
    # `홍길동상무이사` 처럼 둘이 붙어 오기도 한다 — 더 뗄 것이 없을 때까지.
    while True:
        hit = next((t for t in _GLUED_TITLES
                    if key.endswith(t) and len(key) - len(t) >= 2), None)
        if hit is None:
            break
        key = key[:-len(hit)]
    return key.lower()


def person_keys(raw: Optional[str]) -> Set[str]:
    """`공유 심사역` 칸의 사람들 — 한 칸에 둘이 적혀 있으면 둘 다."""
    keys = {person_key(part) for part in _PEOPLE_SPLIT.split(raw or "")}
    # 직함만 떨어져 남은 조각(`… , 이사`)은 사람이 아니다.
    return {k for k in keys if k and not _is_title(k)}


def firm_key(raw: Optional[str]) -> str:
    """견줄 회사 이름 — `(주)` · 띄어쓰기 · 대소문자(`deal_history._key` 와 같은 손)."""
    return deal_history._key(raw)


def is_own(row: SeriesACompany, contact) -> bool:
    """이 기업은 **이 분이 공유해 준 딜**인가.

    이름(`person_keys` ↔ 받는 분 이름)이 같아야 하고, **회사가 양쪽에 다 있으면**
    회사도 같아야 한다. 한쪽 회사가 비었으면(대개 줄의 `회사` 칸이 비었다) 이름만으로
    본다 — 견줄 것이 없을 뿐 어긋난 것은 아니다. 이름이 같아도 회사가 다르면
    동명이인으로 보고 **본인으로 보지 않는다.**
    """
    who = person_key(getattr(contact, "name", ""))
    if not who or who not in person_keys(row.shared_by):
        return False
    row_firm = firm_key(row.source_firm)
    their_firm = firm_key(getattr(contact, "firm", ""))
    if not row_firm or not their_firm:
        return True
    return row_firm == their_firm


def own_by_company(db: Session, rows: Sequence[SeriesACompany]) -> Dict[int, List[int]]:
    """기업 → **그 딜을 공유해 준** 이 갈래 심사역 번호들. 고르개의 `본인 공유 N명 제외`.

    갈래의 줄 전부(불참여도)를 본다 — 화면이 지금 고른 받는 분과 견준다.
    """
    people = db.execute(select(SourcingContact).where(
        SourcingContact.bucket == BUCKET)).scalars().all()
    out: Dict[int, List[int]] = {}
    for row in rows:
        if not person_keys(row.shared_by):
            continue
        ids = sorted(p.id for p in people if is_own(row, p))
        if ids:
            out[row.id] = ids
    return out


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
