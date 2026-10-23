"""같은 기업 칸 따라 고치기 — IR 기업 현황 ↔ 투자컨설턴트 ↔ 스타트업 명단 (1단계).

10/22 요청: "같은 기업명을 쓰는 메뉴에서는 동기화가 되어 내용을 각 위치에서 수정해도
반영 될 수 있도록". 설계는 사용자가 승인한 결정 13개(10/22) 그대로다.

## 방식 — 각 표가 제 칸을 갖고, 고칠 때 이어진 줄을 따라 고친다

`sourcing_sync`(딜 소싱 ↔ 투자사 관리 현황)와 같은 방식이다. 읽는 곳(표 · 필터 · 엑셀
· 발송)을 하나도 안 고치고, **세션 flush 한 자리**에서 이어진 줄(`ir_company_id`)에
같은 값을 적는다 — 화면 PATCH · 시트 올리기 · 스크립트 어느 길로 고쳐도 지난다.
기준 값은 IR 기업 현황(`IrCompany`)이다.

## 잇는 칸(`FIELDS`)

    IR 기업 현황      투자컨설턴트                      스타트업 명단
    대표자명          대표자명 `ceo_name`               대표자명 `name`
    연락처            연락처 `phone`                    연락처 `phone`
    이메일            이메일 `email`                    이메일 `email`
    지역              지역 `region`                     —
    견적서 첨부 여부  견적서 첨부 여부(메타 탭만)        견적서 첨부 여부 `notes.quote_attached`
    카톡 연결 여부    카톡 연결 여부(메타 탭만)          카톡 연결 여부 `kakao_joined`
    ── 2단계(#59 · 10/23) ──
    계약여부          계약여부(메타 `contract_done` ·    계약여부 `notes.contract`
                      계약 탭 `management`)
    계약서 수신 여부  계약서 수신 여부(메타 · 계약 탭)   계약서 수신 여부 `notes.invoice_received`
    미팅제공일자      —                                 미팅제공일자 `notes.ir_meeting_offered_at`
    성공보수율        성공보수율(계약 탭만)              성공보수율 `notes.success_fee`(결정 10)

월간 계약 탭은 계약 칸(`CONTRACT_TAB`)만 잇는다 — 그 탭의 `region` 은 달 묶음 이름이다.
진행 기록(기업 관리 · 컨설팅 미팅일)은 잇지 않고 IR 화면에서 읽기만 한다(결정 3).

계약여부는 **화면마다 값 꼴이 다르다** — IR 은 열쇠(`paid`), 메타는 보기 둘
(`무료계약완료` · `유료계약완료` — 결정 4), 계약 탭은 `무료` · `유료`, 스타트업은 보기 넷.
읽을 때는 `contract_key` 로 열쇠로 맞추고(`norm`), 적을 때는 그 자리의 말로 바꾼다
(`_out` — 못 적는 상태면 안 적는다). 투자컨설턴트 칸에서는 무료 · 유료만 IR 로 간다.
IR 의 `미계약`(기본값)은 빈칸으로 본다.

**`딜소개 불가`(blocked)가 끼는 변경은 저절로 하지 않는다** — IR 이 그 값이 되면 그 기업이
딜 발송(`/deals`)에서 빠지고, 스타트업 줄이 그 값이면 스타트업 안내 발송에서 빠진다.
따라 고치기 · 잇는 순간 채우기 어느 쪽도 그 값을 적거나 지우지 않고, `값 다름` 에 세워
사람이 고른다(`resolve`). IR 화면에서 사람이 바꾸는 것은 그대로 된다.

## 규칙

1. **빈칸이 아닌 값으로 고친 칸만** 따라간다. 비운 칸은 다른 쪽을 지우지 않는다(결정 6
   — 수정창은 모든 칸을 보낸다).
2. 줄을 고치면 → IR → 그 IR 에 이어진 다른 줄 모두. IR 을 고치면 → 이어진 줄 모두.
   한 flush 에서 같은 칸을 IR 과 줄이 같이 고쳤으면 IR 값이 이긴다.
3. O/X 칸은 `O` · `X` 만 옮긴다. 자유 글(`10/1 초대함`)은 그 줄에 두고, 옮기지도
   덮지도 않는다 — 그 글이 그날의 기록이다. 계약서 수신 칸의 날짜 글(`9/25 계약서
   수신완료`)만은 IR 에 `O` 로 올리고 글은 그 줄에 둔다(결정 11).
4. **잇는 순간에는 빈칸만 채운다**(결정 2 · 5) — 양쪽에 다른 값이 있으면 덮지 않고
   `/ir-link` 의 `값 다름` 목록에 세운다(`differences`). 사람이 한쪽을 고르면
   (`resolve`) 그때부터 같아진다. 연락처 · 이메일은 둘 다 남길 수도 있다 — 한 칸에
   `IR 값, 줄 값`(앞이 정 · 메일은 정에만 간다, `keep_both` · 10/23 결정).
5. 시트 · 엑셀 다시 올리기는 이어진 줄의 빈칸만 채운다(결정 7 — `fill_only`).
6. 새 줄은 이름이 정확히 하나 맞으면 저절로 잇는다(`ir_link_auto` — 결정 2).
7. 수정 로그는 flush 자리라 `edit_log` 가 그대로 남긴다 — 컨설턴트가 고친 값이 IR
   공용 칸을 바꿀 수 있고(결정 13), 따라 고친 남의 줄은 `남의 것` 으로 남는다.

ORM 밖 대량 UPDATE(`update()` · `query().update()`)는 이 자리를 안 지난다 —
스크립트는 줄마다 ORM 으로 고친다(이 저장소의 관례).
"""
from __future__ import annotations

import json
import re
from contextlib import contextmanager
from typing import Dict, Iterable, List, Optional, Tuple, Union

from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import get_history

from .. import clock
from ..models import ConsultingCompany, ConsultingSheet, IrCompany, VcContact

Row = Union[ConsultingCompany, VcContact]

#: IR 칸 → (투자컨설턴트 칸, 스타트업 명단 칸). `note:` 는 `VcContact.notes` 의 열쇠.
FIELDS = {
    "contact_name": ("ceo_name", "name"),
    "contact_phone": ("phone", "phone"),
    "contact_email": ("email", "email"),
    "region": ("region", None),
    "quote_attached": ("contract_management", "note:quote_attached"),
    "kakao_joined": ("kakao_joined", "kakao_joined"),
    # 2단계(#59)
    "contract_status": ("contract_done", "note:contract"),
    "contract_received": ("contract_received", "note:invoice_received"),
    "meeting_offered_at": (None, "note:ir_meeting_offered_at"),
    "success_fee": (None, "note:success_fee"),
}
#: 월간 계약 탭이 받는 칸 — 그 탭은 표가 달라 계약여부가 `management`(`무료`/`유료`)다.
CONTRACT_TAB = {"contract_status": "management", "contract_received": "contract_received",
                "success_fee": "success_fee"}
#: 화면 이름 — 10/22 통일한 IR 기업 현황 낱말.
LABELS = {"contact_name": "대표자명", "contact_phone": "연락처", "contact_email": "이메일",
          "region": "지역", "quote_attached": "견적서 첨부 여부",
          "kakao_joined": "카톡 연결 여부", "contract_status": "계약여부",
          "contract_received": "계약서 수신 여부", "meeting_offered_at": "미팅제공일자",
          "success_fee": "성공보수율"}
#: `O` / `X` 만 옮기는 칸.
OX = ("quote_attached", "kakao_joined", "contract_received")
#: 투자컨설턴트에서 **메타(관리 스타트업) 탭에만** 서는 칸(계약 탭은 `CONTRACT_TAB`).
META_ONLY = ("quote_attached", "kakao_joined", "contract_status", "contract_received")
#: 시트 올리기가 덮지 않는 투자컨설턴트 칸(이어진 줄에서 — 결정 7). 올리기는 메타 탭에 든다.
CONSULTING_SLOTS = frozenset(c for c, _s in FIELDS.values() if c)

CONTRACT = "contract_status"
NONE, BLOCKED = "none", "blocked"
#: 투자컨설턴트가 IR 로 올릴 수 있는 계약 값 — 무료 · 유료계약완료 둘(결정 4). 그 밖의
#: 상태(검토중 · 미팅제공 · 딜소개 불가)는 투자컨설턴트 칸에서 IR 로 가지 않는다.
CONSULTANT_KEYS = ("free", "paid")
#: 월간 계약 탭 `계약여부` 의 두 마디 — `contract_key` 가 모르는 말이라 여기서만 잇는다.
TAB_WORDS = {"무료": "free", "유료": "paid"}
#: 스타트업 `계약여부` 에 적을 수 있는 상태 — 보기 넷(`contact_columns` 의 그 칸) +
#: 옛 값 `딜소개 불가`(사람이 `값 다름` 에서 고를 때만 적힌다).
STARTUP_KEYS = ("paid", "free", "review", NONE, BLOCKED)
#: 계약서 수신 칸의 날짜 글(`9/25 계약서 수신완료`) — IR 에는 `O` 로 올린다(결정 11).
DATED = re.compile(r"\d{1,4}\s*[/.\-]\s*\d{1,2}")

#: `session.info` 열쇠 — 켜져 있으면 따라 고칠 때 **빈칸만** 채운다(`fill_only`).
FILL_ONLY = "company_sync_fill_only"
#: `session.info` 열쇠 — 켜져 있으면 새 줄을 이름으로 잇지 않는다. 부르는 쪽이 이을
#: 기업을 따로 정해 줄 때(투자컨설턴트 → 스타트업 보내기)다 — 이름으로 먼저 다른 IR 에
#: 붙었다 옮기면 그 IR 의 빈칸이 엉뚱한 값으로 채워진다.
NO_AUTO_LINK = "company_sync_no_auto_link"


# ── 값 ─────────────────────────────────────────────────────────────────────

def _raw(value) -> str:
    return str(value or "").strip()


def _key(text: str) -> str:
    """계약 글 → IR 열쇠(`paid`). 빈칸은 `none`. 모르는 말은 그대로(`contract_key` 와 같다)."""
    from ..routers.companies import contract_key   # 순환 import 를 피해 늦게 부른다

    return contract_key(TAB_WORDS.get(text, text)) if text else NONE


def _known(key: str) -> bool:
    from ..routers.companies import CONTRACT_LABELS

    return key in CONTRACT_LABELS


def norm(field: str, value, where: Optional[str] = None) -> Optional[str]:
    """옮길 수 있는 값 — 빈칸 · O/X 칸의 자유 글 · 모르는 계약 말이면 None.

    계약여부는 IR 열쇠로 돌려준다. `where` 가 투자컨설턴트 계약 칸이면 무료 · 유료만(결정 4).
    """
    text = _raw(value)
    if not text:
        return None
    if field == CONTRACT:
        key = _key(text)
        if where in ("contract_done", "management") and key not in CONSULTANT_KEYS:
            return None
        return key if _known(key) else None
    if field in OX:
        upper = text.upper()
        if upper in ("O", "X"):
            return upper
        if field == "contract_received" and DATED.search(text) and "안" not in text:
            return "O"
        return None
    return text


def same(field: str, a, b) -> bool:
    """두 값이 같은 사실인가 — 연락처는 숫자만, O/X 는 대소문자 없이, 계약은 열쇠로 견준다."""
    if field == "contact_phone":
        return re.sub(r"\D", "", _raw(a)) == re.sub(r"\D", "", _raw(b))
    if field == CONTRACT:
        ka, kb = _key(_raw(a)), _key(_raw(b))
        if _known(ka) and _known(kb):
            return ka == kb
    elif field in OX:
        na, nb = norm(field, a), norm(field, b)
        if na and nb:
            return na == nb
        return _raw(a).upper() == _raw(b).upper()
    return _raw(a) == _raw(b)


def _kept(field: str, text: str, where: Optional[str] = None) -> bool:
    """저절로 덮지 않는 글 — 옮길 수 없는 값, 계약서 수신의 날짜 글(결정 11)."""
    return norm(field, text, where) is None or (
        field == "contract_received" and text.upper() not in ("O", "X"))


def _out(field: str, where: str, value: str) -> Optional[str]:
    """IR 값 `value` 를 이 자리에 적을 글 — 그 자리가 못 받는 상태면 None.

    계약여부만 자리마다 말이 다르다. 메타 칸은 보기 둘뿐이라 다른 상태는 빈칸
    (`아직 완료 아님` — 설계 4-4), 계약 탭은 `무료` / `유료` 만, 스타트업은 보기 넷.
    """
    if field != CONTRACT or where == CONTRACT:
        return value
    from ..routers.companies import CONTRACT_LABELS

    if where == "management":
        return {v: k for k, v in TAB_WORDS.items()}.get(value)
    if where == "contract_done":
        return CONTRACT_LABELS[value] if value in CONSULTANT_KEYS else ""
    return CONTRACT_LABELS[value] if value in STARTUP_KEYS else None


def _guarded(field: str, current: str, value: str) -> bool:
    """`딜소개 불가` 로 바뀌거나 그 값에서 풀리는 변경 — 저절로는 안 한다(머리말)."""
    return field == CONTRACT and BLOCKED in ((_key(current) if current else None), value)


#: [둘 다 남기기] 를 받는 칸 — 연락 수단이라 다른 값은 둘 다 둔다(10/23 결정).
#: 한 칸에 `정, 부` 로 잇는다. 앞(정)이 IR 값이고, 메일은 정에만 간다
#: (`mailer.primary_email`).
BOTH = ("contact_phone", "contact_email")
SEP = ", "


def pieces(value) -> List[str]:
    """한 칸에 적힌 값들 — `,` · `;` · 줄바꿈으로 나눈다(`/` 는 내선 번호에 쓰여 안 나눈다)."""
    return [p.strip() for p in re.split(r"[,;\n]", _raw(value)) if p.strip()]


def combine(field: str, values: Iterable) -> Tuple[str, int]:
    """값들을 차례대로 `, ` 로 잇는다(앞이 정). 같은 값은 한 번만 — 번호는 숫자만,
    메일은 대소문자 없이 견준다. `(이은 글, 꼴만 달라 하나로 접은 수)`."""
    out: List[str] = []
    seen: Dict[str, str] = {}
    folded = 0
    for piece in (p for v in values for p in pieces(v)):
        key = (re.sub(r"\D", "", piece) if field == "contact_phone" else piece.lower()) or piece
        if key in seen:
            folded += seen[key] != piece
            continue
        seen[key] = piece
        out.append(piece)
    return SEP.join(out), folded


# ── 줄의 칸 ────────────────────────────────────────────────────────────────

def sheet_kinds(session: Session) -> Dict[str, str]:
    """투자컨설턴트 탭 이름 → 종류. 탭 줄이 아직 없으면 처음 세울 이름으로 본다.

    `consulting_sheets.ensure` 를 안 부른다 — 그 함수는 줄을 세우고 커밋하는데, 여기는
    flush 한가운데다.
    """
    from . import consulting_sheets as cs

    with session.no_autoflush:
        found = {s.label: s.kind for s in session.execute(select(ConsultingSheet)).scalars()}
    return found or {label: kind for kind, label in cs.DEFAULTS}


def slot(row: Row, field: str, kinds: Dict[str, str]) -> Optional[str]:
    """이 줄에서 IR 칸 `field` 를 받는 자리. 안 잇는 칸이면 None."""
    if isinstance(row, ConsultingCompany):
        from . import consulting_sheets as cs

        kind = kinds.get(row.sheet or "", "")
        if kind == cs.CONTRACT:
            return CONTRACT_TAB.get(field)
        if field in META_ONLY and kind != cs.STARTUP:
            return None
        return FIELDS[field][0]
    return FIELDS[field][1]


def _value(obj, where: str, field: str) -> str:
    """그 자리에 적힌 글. IR 계약여부의 `미계약`(기본값)은 빈칸으로 본다."""
    text = _raw(_get(obj, where))
    return "" if field == CONTRACT == where and _key(text) == NONE else text


def _get(row, where: str):
    if where.startswith("note:"):
        from .contact_columns import load_notes

        return load_notes(row.notes).get(where[5:])
    return getattr(row, where, None)


def _set(row, where: str, value: str) -> None:
    if where.startswith("note:"):
        from .contact_columns import dump_notes, load_notes

        notes = load_notes(row.notes)
        notes[where[5:]] = value
        row.notes = dump_notes(notes)
    else:
        setattr(row, where, value)
    if isinstance(row, ConsultingCompany):
        # 따라 고친 칸도 `수정한 날짜` 를 찍는다 — 안 찍으면 값만 바뀌고 날짜는 옛것이다.
        try:
            stamps = json.loads(row.field_stamps or "{}")
        except ValueError:
            stamps = {}
        stamps = stamps if isinstance(stamps, dict) else {}
        stamps[where] = clock.now_iso()
        row.field_stamps = json.dumps(stamps, ensure_ascii=False)


def _put(target, where: str, field: str, value: str, fill_only: bool) -> bool:
    """`value`(IR 꼴) 를 적는다. 같으면 · (빈칸만 모드에서) 이미 값이 있으면 · 자유 글이
    적혀 있으면(규칙 3) · `딜소개 불가` 가 끼면(머리말) · 그 자리가 못 받는 상태면 그대로
    둔다. 적었으면 True."""
    current = _value(target, where, field)
    if same(field, current, value):
        return False      # 같은 사실(연락처는 숫자만)이면 꼴만 다른 값으로 다시 안 적는다
    if current and (fill_only or _kept(field, current, where)):
        return False
    if _guarded(field, current, value):
        return False      # 딜 발송 대상이 바뀌는 자리 — `값 다름` 에서 사람이 고른다
    out = _out(field, where, value)
    if out is None or out == _raw(_get(target, where)):
        return False
    _set(target, where, out)
    return True


# ── flush 한 자리 ──────────────────────────────────────────────────────────

def _changes(obj, places: Dict[str, str]) -> Dict[str, str]:
    """이번 flush 에서 **옮길 수 있는 값으로 바뀐** 칸 — `{IR 칸: 새 값}`."""
    out = {}
    for field, where in places.items():
        name = "notes" if where.startswith("note:") else where
        history = get_history(obj, name)
        if not history.added:
            continue
        after, before = history.added[0], history.deleted[0] if history.deleted else None
        if where.startswith("note:"):
            from .contact_columns import load_notes

            after = load_notes(after).get(where[5:])
            before = load_notes(before).get(where[5:])
        value = norm(field, after, where)
        # 계약의 `미계약` 은 IR 기본값(= 빈칸)이라 비우기처럼 안 따라간다(결정 6).
        if value and value != norm(field, before, where) and value != NONE:
            out[field] = value
    return out


def _places(row: Row, kinds: Dict[str, str]) -> Dict[str, str]:
    return {f: w for f in FIELDS if (w := slot(row, f, kinds))}


class _Flush:
    """flush 한 번 동안의 이어진 줄 찾기(같은 IR 을 여러 번 묻지 않게)."""

    def __init__(self, session: Session):
        self.session = session
        self.kinds = sheet_kinds(session)
        self.fill_only = bool(session.info.get(FILL_ONLY))
        self._linked: Dict[int, List[Row]] = {}

    def linked(self, company_id: int) -> List[Row]:
        """이 IR 기업에 **지금** 이어진 줄 — DB 와 세션의 새 · 고친 줄을 함께 본다."""
        if company_id in self._linked:
            return self._linked[company_id]
        session = self.session
        with session.no_autoflush:
            found = [r for model in (ConsultingCompany, VcContact)
                     for r in session.execute(select(model).where(
                         model.ir_company_id == company_id)).scalars()]
        found += [o for o in list(session.new) + list(session.dirty)
                  if isinstance(o, (ConsultingCompany, VcContact))]
        out, seen = [], set()
        for row in found:
            if (id(row) in seen or row in session.deleted
                    or row.ir_company_id != company_id):
                continue
            seen.add(id(row))
            out.append(row)
        self._linked[company_id] = out
        return out

    def company(self, company_id: int) -> Optional[IrCompany]:
        with self.session.no_autoflush:
            company = self.session.get(IrCompany, company_id)
        return None if company is None or company in self.session.deleted else company


def _auto_link(session: Session, rows: List[Row]) -> None:
    """새 줄을 이름이 **정확히 하나** 맞는 IR 기업에 잇는다(결정 2 · `자동 연결`).

    후보가 여럿이거나 없으면 그대로 둔다 — `/ir-link` 에서 사람이 고른다. 스타트업
    명단 줄은 스타트업 화면의 명단에 올라 있을 때만 — 투자사 줄의 `firm` 은 투자사다.
    """
    from . import ir_link, sheet_owner
    from .contact_columns import PAGE_STARTUP

    with session.no_autoflush:
        startup = (sheet_owner.page_labels(session, PAGE_STARTUP)
                   if any(isinstance(r, VcContact) for r in rows) else set())
        # 투자사 명단을 수백 줄 넣는 가져오기도 이 자리를 지난다 — 이을 줄이 없으면
        # IR 기업 표를 훑지 않는다.
        rows = [r for r in rows
                if not isinstance(r, VcContact) or sheet_owner.on_page(r, startup)]
        if not rows:
            return
        idx = ir_link.Index(session.execute(select(IrCompany)).scalars().all())
    for row in rows:
        company = ir_link.single_candidate(idx, row)
        if company is not None:
            row.ir_company_id = company.id
            row.ir_link_auto = 1


def _linked_now(row: Row) -> bool:
    """이번 flush 에서 (새로) 이어졌는가."""
    history = get_history(row, "ir_company_id")
    return bool(history.added and history.added[0]
                and history.added[0] != (history.deleted[0] if history.deleted else None))


def _fill(run: "_Flush", row: Row, fields: Optional[Iterable[str]] = None) -> int:
    """이 줄과 그 IR 의 **양쪽 빈칸만** 채운다 — 다른 값은 그대로 둔다. 적은 칸 수."""
    company = run.company(row.ir_company_id)
    if company is None:
        return 0
    wrote = 0
    for field, where in _places(row, run.kinds).items():
        if fields is not None and field not in fields:
            continue
        mine = norm(field, _get(row, where), where)
        theirs = norm(field, _value(company, field, field), field)
        if mine and not _value(company, field, field):
            if _put(company, field, field, mine, fill_only=True):
                wrote += 1
                for other in run.linked(company.id):
                    if other is not row and (w := slot(other, field, run.kinds)):
                        wrote += _put(other, w, field, mine, fill_only=True)
        elif theirs and not _value(row, where, field):
            wrote += _put(row, where, field, theirs, fill_only=True)
    return wrote


def fill_blanks(session: Session, rows: Iterable[Row],
                fields: Optional[Iterable[str]] = None) -> int:
    """**이미 이어진 줄**을 잇는 순간처럼 맞춘다 — 양쪽 빈칸만(결정 5).

    2단계 칸(계약 · 미팅 · 보수율)은 줄을 이은 뒤에 생겨 잇는 순간 채우기를 못 지났다.
    `scripts/company_sync_fill.py` 가 부른다. 적은 칸 수를 돌려준다(커밋은 부르는 쪽).
    """
    run = _Flush(session)
    fields = set(fields) if fields is not None else None
    with session.no_autoflush:
        return sum(_fill(run, r, fields) for r in rows if r.ir_company_id)


def before_flush(session: Session) -> None:
    """flush 직전 — 새 줄을 잇고, 이은 줄은 빈칸만 채우고, 고친 칸은 따라 고친다.

    `app/models.py` 가 세션 이벤트로 건다(모든 flush 가 지난다). 차례:
    ① 새 줄 자동 연결 → ② 바뀐 칸을 **먼저 다 읽어 둔다**(아래 ③이 적는 값이 '고친
    것' 으로 읽히지 않게) → ③ 이어진 줄은 빈칸만 채움 → ④ IR 을 고친 칸 → 이어진 줄
    → ⑤ 줄을 고친 칸 → IR · 다른 줄(④가 이미 적은 칸은 건너뛴다 — IR 이 이긴다).
    """
    rows = [o for o in list(session.new) + list(session.dirty)
            if isinstance(o, (ConsultingCompany, VcContact)) and o not in session.deleted]
    companies = [o for o in session.dirty
                 if isinstance(o, IrCompany) and o not in session.deleted and o.id]
    if not rows and not companies:
        return
    fresh = [r for r in rows if r in session.new and not r.ir_company_id]
    if fresh and not session.info.get(NO_AUTO_LINK):
        _auto_link(session, fresh)
    rows = [r for r in rows if r.ir_company_id]
    if not rows and not companies:
        return

    run = _Flush(session)
    joined = [r for r in rows if _linked_now(r)]
    edited = [(r, _changes(r, _places(r, run.kinds))) for r in rows if r not in joined]
    ir_edits = [(c, _changes(c, {f: f for f in FIELDS})) for c in companies]

    # ③ 잇는 순간 — 양쪽 빈칸만 채운다. 다른 값은 그대로(`differences` 가 보인다).
    for row in joined:
        _fill(run, row)

    # ④ IR 을 고쳤다 → 이어진 줄 모두.
    wrote = set()
    for company, changed in ir_edits:
        for field, value in changed.items():
            wrote.add((company.id, field))
            for other in run.linked(company.id):
                if (w := slot(other, field, run.kinds)):
                    _put(other, w, field, value, run.fill_only)

    # ⑤ 줄을 고쳤다 → IR → 그 IR 에 이어진 다른 줄.
    touched = {id(r): set(ch) for r, ch in edited}
    for row, changed in edited:
        company = run.company(row.ir_company_id) if changed else None
        if company is None:
            continue
        for field, value in changed.items():
            if (company.id, field) in wrote:
                continue
            # IR 에도 같은 규칙(`_put`) — 빈칸만 모드 · 같은 값 · O/X 칸의 자유 글은 그대로.
            if not _put(company, field, field, value, run.fill_only) \
                    and not same(field, getattr(company, field), value):
                continue
            wrote.add((company.id, field))
            for other in run.linked(company.id):
                # 같은 flush 에서 그 줄도 이 칸을 고쳤으면 제 손으로 고친 값을 둔다.
                if (other is not row and field not in touched.get(id(other), ())
                        and (w := slot(other, field, run.kinds))):
                    _put(other, w, field, value, run.fill_only)


@contextmanager
def fill_only(session: Session):
    """이 안에서는 따라 고칠 때 **빈칸만** 채운다 — 시트 · 엑셀 다시 올리기(결정 7)."""
    before = session.info.get(FILL_ONLY)
    session.info[FILL_ONLY] = True
    try:
        yield
    finally:
        if before is None:
            session.info.pop(FILL_ONLY, None)
        else:
            session.info[FILL_ONLY] = before


def sheet_keeps(row: ConsultingCompany, where: str) -> bool:
    """시트 올리기가 이 칸을 **덮지 않아야** 하는가 — 이어진 줄의 잇는 칸에 값이 있으면."""
    return bool(row.ir_company_id and where in CONSULTING_SLOTS and _raw(getattr(row, where, None)))


def startup_keeps(row: VcContact) -> set:
    """시트 올리기가 덮지 않을 스타트업 줄의 자리(`name` · `note:quote_attached` …)."""
    if not row.ir_company_id:
        return set()
    return {w for _c, w in FIELDS.values() if w and _raw(_get(row, w))}


# ── 값 다름 목록 · 고르기 ───────────────────────────────────────────────────

def differences(db: Session, rows: Iterable[Row]) -> Dict[int, List[dict]]:
    """이어진 줄마다 **IR 과 값이 다른 칸** — `{줄 번호: [{field, label, row, ir, movable,
    both, blocked}]}`.

    둘 다 값이 있는데 다를 때만 센다(한쪽이 비면 잇는 순간 채워진다). 하나 더 —
    줄이 `딜소개 불가` 인데 IR 이 비었으면(미계약) 저절로 안 채우므로(머리말) 여기 선다.
    `movable` 이 False 면 그 줄 값을 IR 로 올릴 수 없다(자유 글 · 투자컨설턴트의 다른 계약
    상태). `blocked` 면 고르는 쪽에 따라 딜 발송 대상이 바뀐다.
    """
    from ..routers.companies import CONTRACT_LABELS

    rows = [r for r in rows if r.ir_company_id]
    if not rows:
        return {}
    kinds = sheet_kinds(db)
    companies = {c.id: c for c in db.execute(select(IrCompany).where(
        IrCompany.id.in_({r.ir_company_id for r in rows}))).scalars()}
    out: Dict[int, List[dict]] = {}
    for row in rows:
        company = companies.get(row.ir_company_id)
        if company is None:
            continue
        for field, where in _places(row, kinds).items():
            mine, theirs = _value(row, where, field), _value(company, field, field)
            stuck = bool(mine) and not theirs and _guarded(field, theirs, _key(mine))
            if not stuck and not (mine and theirs and not same(field, mine, theirs)):
                continue
            shown = theirs
            if field == CONTRACT:
                shown = CONTRACT_LABELS.get(_key(theirs), theirs)
            out.setdefault(row.id, []).append({
                "field": field, "label": LABELS[field], "row": mine, "ir": shown,
                "movable": norm(field, mine, where) is not None, "both": field in BOTH,
                "blocked": _guarded(field, mine, _key(theirs))})
    return out


def resolve(db: Session, row: Row, field: str, pick: str) -> None:
    """`값 다름` 한 칸을 사람이 고른다 — `ir`(IR 값으로 이 줄을) · `row`(이 줄 값으로 IR 을)
    · `both`(연락처 · 이메일만 — 둘 다 남긴다, `keep_both`).

    적기만 한다. 나머지 이어진 줄은 flush 가 따라 고친다(규칙 2). 커밋은 부르는 쪽.
    """
    company = db.get(IrCompany, row.ir_company_id) if row.ir_company_id else None
    where = slot(row, field, sheet_kinds(db)) if field in FIELDS else None
    if company is None or where is None:
        raise ValueError("이어진 IR 기업이나 맞출 칸이 없습니다")
    if pick == "both":
        keep_both(db, row, field)
    elif pick == "ir" and field == CONTRACT:
        # IR 의 빈칸은 `미계약` 이다. 이 줄이 못 받는 상태면 비운다(`아직 완료 아님`).
        _set(row, where, _out(field, where, _key(_value(company, field, field))) or "")
    elif pick == "ir":
        value = _raw(getattr(company, field))
        if not value:
            raise ValueError("IR 쪽 값이 비어 있습니다")
        _set(row, where, value)
    elif pick == "row":
        value = norm(field, _get(row, where), where)
        if value is None:
            raise ValueError(f"이 줄의 {LABELS[field]} 값은 IR 로 옮길 수 없습니다")
        setattr(company, field, value)
    else:
        raise ValueError("고르는 쪽이 올바르지 않습니다")


def keep_both(db: Session, row: Row, field: str, skip_odd: bool = False) -> Dict[str, int]:
    """연락처 · 이메일 `값 다름` 을 **둘 다 남긴다** — `IR 값, 이 줄 값`(앞이 정).

    · 꼴만 다른 같은 번호 · 대소문자만 다른 같은 메일은 하나로 접는다(`combine`).
    · 연락처 칸에 적힌 메일 주소는 이메일 칸 뒤로 옮겨 잇는다 — 투자컨설턴트
      `경영본부 전달 기업` 탭이 연락처 칸에 메일을 적어 두었다.
    · 이 IR 에 이어진 **다른 줄의 값도 뒤에** 잇고 그 줄들까지 같은 값을 적는다 —
      IR 을 고치면 flush 가 그 줄들을 덮으므로(규칙 2) 안 이으면 그 값이 사라진다.

    `odd` 는 모양이 이상한 값 수 — 연락처에 숫자가 없는 글, 이메일에 `@` 가 없는 글.
    `skip_odd` 면 그런 값이 하나라도 있을 때 아무것도 안 적는다(일괄 스크립트 — 사람이
    `/ir-link` 에서 고르게 남긴다). 적기만 한다(커밋은 부르는 쪽 — 수정 로그는 flush 가).
    돌려주는 것: `{"moved": 옮긴 메일 수, "folded": 꼴만 달라 접은 수, "odd": …}`.
    """
    company = db.get(IrCompany, row.ir_company_id) if row.ir_company_id else None
    kinds = sheet_kinds(db)
    if field not in BOTH or company is None or slot(row, field, kinds) is None:
        raise ValueError("둘 다 남기기는 이어진 줄의 연락처 · 이메일 칸만 됩니다")
    rows = [row] + [r for model in (ConsultingCompany, VcContact)
                    for r in db.execute(select(model).where(
                        model.ir_company_id == company.id).order_by(model.id)).scalars()
                    if r is not row]

    def values(f: str) -> List[str]:
        """IR 이 앞, 이 줄, 다른 이어진 줄 차례의 낱값."""
        found = [getattr(company, f)] + [_get(r, w) for r in rows if (w := slot(r, f, kinds))]
        return [p for v in found for p in pieces(v)]

    new: Dict[str, str] = {}
    phones: List[str] = []
    emails: List[str] = []
    moved: List[str] = []
    folded = 0
    if field == "contact_phone":
        phones = values(field)
        moved = [p for p in phones if "@" in p]
        phones = [p for p in phones if "@" not in p]
        new[field], folded = combine(field, phones)
    if field == "contact_email" or moved:
        emails = values("contact_email") + moved
        new["contact_email"], n = combine("contact_email", emails)
        folded += n
    odd = (sum(1 for p in phones if not re.search(r"\d", p))
           + sum(1 for p in emails if "@" not in p))
    if skip_odd and odd:
        return {"moved": 0, "folded": 0, "odd": odd}
    # 글자 그대로 견준다 — `same` 은 숫자만 보므로 연락처 칸의 메일(숫자 없음)을 못 비운다.
    for f, text in new.items():
        if _raw(getattr(company, f)) != text:
            setattr(company, f, text)
        for r in rows:
            w = slot(r, f, kinds)
            if w and _raw(_get(r, w)) != text:
                _set(r, w, text)
    return {"moved": len(moved), "folded": folded, "odd": odd}
