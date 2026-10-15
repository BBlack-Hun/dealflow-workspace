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

이름 · 회사 · 기업은 전부 화면에서 오는 값이다 — 여기에 적힌 실명은 없다(공개 저장소).
"""
from __future__ import annotations

import re
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (SendItem, SendJob, SeriesACompany, SeriesAShare,
                      SourcingContact, User)
from . import deal_numbers, sourcing_msg
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
#: 고른 기업을 이미 다 받은 분 — 미리보기 경고 · 발송에서 뺀 이유.
ALL_SHARED_NOTE = "고른 기업을 모두 이미 받은 분입니다 — 이번 목록에서 뺐습니다"

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


def split(contact_id: int, companies: Sequence[SeriesACompany],
          got: Dict[int, Set[int]]) -> Tuple[List[SeriesACompany], List[SeriesACompany]]:
    """(아직 안 받은 기업, 이미 받은 기업) — 고른 차례는 그대로."""
    have = got.get(contact_id, set())
    fresh = [c for c in companies if c.id not in have]
    old = [c for c in companies if c.id in have]
    return fresh, old


def partial_note(old: Sequence[SeriesACompany]) -> str:
    """일부를 이미 받은 분 — 미리보기 경고."""
    names = ", ".join((c.name or "").strip() for c in old)
    return f"이미 받은 기업 {len(old)}곳은 이 분 문구에서 뺐습니다: {names}"


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
