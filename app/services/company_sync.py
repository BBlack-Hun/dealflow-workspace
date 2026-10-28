"""같은 기업 칸 따라 고치기 — IR 기업 현황 ↔ 투자컨설턴트 ↔ 스타트업 명단 ↔ Series A.

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

    ── 3단계(10/26) — Series A 이상 딜 소싱(`SeriesACompany`)은 셋째 자리 ──
    대표자명 · 연락처 · 이메일   →  `ceo_name` · `ceo_phone` · `ceo_email`
    계약여부 · 계약서 수신 여부  →  같은 이름 칸(10/28 · 0125 — IR 과 같은 열쇠 · `O`/`X`)
    누적투자금액 · 투자유치희망금액 · Pre Value  →  같은 이름 칸(단위 억 글자)
    연도 매출  →  **해마다 짝이 바뀐다**(`_year_slot`). IR 은 올해 매출을 연도 칸이 아니라
                  `revenue_recent` 에 적는다(`revenue_years` 머리말). 그래서 Series A 의
                  올해 칸 ↔ IR `revenue_recent`, 지난 해 칸 ↔ IR 같은 해 칸이고, 앞으로 올
                  해 칸(26년의 `27년 매출`)은 잇지 않는다. 지난 해 칸으로 갈 때는 단위를
                  붙인다(`18.3` → `18.3억` — 연도 칸은 적힌 그대로 한줄 소개에 실린다).
    분야 · 투자라운드 · 딜소개 문구는 잇지 않는다 — Series A 는 시트 낱말 · 받은 날의 라운드
    · Series A 딜 공유용 문구라 IR 칸과 뜻이 갈린다(`models.SeriesACompany`).

월간 계약 탭은 계약 칸(`CONTRACT_TAB`)만 잇는다 — 그 탭의 `region` 은 달 묶음 이름이다.
진행 기록(기업 관리 · 컨설팅 미팅일)은 잇지 않고 IR 화면에서 읽기만 한다(결정 3).

계약여부는 **화면마다 값 꼴이 다르다** — IR 은 열쇠(`paid`), 메타는 보기 둘
(`무료계약완료` · `유료계약완료` — 결정 4), 계약 탭은 `무료` · `유료`, 스타트업은 보기 넷,
Series A 는 IR 과 같은 열쇠(`_out` 이 그대로 적는다).
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
   한 flush 에서 같은 칸을 IR 과 줄이 같이 고쳤으면 IR 값이 이긴다. 단 Series A 줄은
   빈칸 · IR 의 이전 값과 같던 칸만 따라간다 — 다른 값은 딜 소싱의 값이다(`_follows`).
3. O/X 칸은 `O` · `X` 만 옮긴다. 자유 글(`10/1 초대함`)은 그 줄에 두고, 옮기지도
   덮지도 않는다 — 그 글이 그날의 기록이다. 계약서 수신 칸의 날짜 글(`9/25 계약서
   수신완료`)만은 IR 에 `O` 로 올리고 글은 그 줄에 둔다(결정 11).
4. **잇는 순간에는 빈칸만 채운다**(결정 2 · 5) — 양쪽에 다른 값이 있으면 덮지 않고
   `/ir-link` 의 `값 다름` 목록에 세운다(`differences`). 사람이 한쪽을 고르면
   (`resolve`) 그때부터 같아진다. 연락처 · 이메일은 둘 다 남길 수도 있다 — 한 칸에
   `IR 값, 줄 값`(앞이 정 · 메일은 정에만 간다, `keep_both` · 10/23 결정).
5. 시트 · 엑셀 다시 올리기는 이어진 줄의 빈칸만 채운다(결정 7 — `fill_only`).
6. 새 줄은 이름이 정확히 하나 맞으면 저절로 잇는다(`ir_link_auto` — 결정 2).
   Series A 줄은 더 — **기업명을 고친 줄**(안 이었거나 저절로 이은 줄)도, **IR 에 기업이
   새로 생기거나 이름이 바뀌면** 그 이름의 안 이은 줄도 저절로 잇는다(10/26 사용자:
   "버튼을 눌러서 가져오는게 아니라 기업명을 넣었을때 자동으로"). 사람이 고른 연결은
   기업명을 고쳐도 그대로다. IR 쪽은 번호가 정해진 뒤라 `after_flush` 에서 잇고, 빈칸
   채우기는 커밋이 이어서 부르는 flush 가 한다. 스타트업 명단 줄도 **기업명을 고친 줄**은
   잇는다(#85 — `기업명` 칸 후보에서 IR 기업을 고르는 길).
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
from ..models import ConsultingCompany, ConsultingSheet, IrCompany, SeriesACompany, VcContact
from . import amount, revenue_years

Row = Union[ConsultingCompany, VcContact, SeriesACompany]
#: IR 기업에 이어지는 줄의 표.
MODELS = (ConsultingCompany, VcContact, SeriesACompany)

#: Series A 연도 매출 자리 — 짝이 해마다 바뀌어 `slot` 이 그해 칸으로 푼다(`_year_slot`).
YEAR = "year"

#: IR 칸 → (투자컨설턴트 칸, 스타트업 명단 칸, Series A 칸). `note:` 는 `VcContact.notes` 의 열쇠.
FIELDS = {
    "contact_name": ("ceo_name", "name", "ceo_name"),
    "contact_phone": ("phone", "phone", "ceo_phone"),
    "contact_email": ("email", "email", "ceo_email"),
    "region": ("region", None, None),
    "quote_attached": ("contract_management", "note:quote_attached", None),
    "kakao_joined": ("kakao_joined", "kakao_joined", None),
    # 2단계(#59)
    "contract_status": ("contract_done", "note:contract", "contract_status"),
    "contract_received": ("contract_received", "note:invoice_received", "contract_received"),
    "meeting_offered_at": (None, "note:ir_meeting_offered_at", None),
    "success_fee": (None, "note:success_fee", None),
    # 3단계(Series A)
    "funding_total": (None, None, "funding_total"),
    "raise_target": (None, None, "raise_target"),
    "pre_value": (None, None, "pre_value"),
    "revenue_recent": (None, None, YEAR),
    **{f: (None, None, YEAR) for f in revenue_years.FIELDS},
}
#: Series A 의 연도 매출 칸(0112 — 24~27년).
SERIES_A_YEARS = frozenset(c.key for c in SeriesACompany.__table__.columns
                           if re.fullmatch(r"revenue_\d{4}", c.key))
#: 월간 계약 탭이 받는 칸 — 그 탭은 표가 달라 계약여부가 `management`(`무료`/`유료`)다.
CONTRACT_TAB = {"contract_status": "management", "contract_received": "contract_received",
                "success_fee": "success_fee"}
#: 화면 이름 — 10/22 통일한 IR 기업 현황 낱말.
LABELS = {"contact_name": "대표자명", "contact_phone": "연락처", "contact_email": "이메일",
          "region": "지역", "quote_attached": "견적서 첨부 여부",
          "kakao_joined": "카톡 연결 여부", "contract_status": "계약여부",
          "contract_received": "계약서 수신 여부", "meeting_offered_at": "미팅제공일자",
          "success_fee": "성공보수율", "funding_total": "누적투자금액",
          "raise_target": "투자유치희망금액", "pre_value": "Pre Value"}
#: `O` / `X` 만 옮기는 칸.
OX = ("quote_attached", "kakao_joined", "contract_received")
#: 투자컨설턴트에서 **메타(관리 스타트업) 탭에만** 서는 칸(계약 탭은 `CONTRACT_TAB`).
META_ONLY = ("quote_attached", "kakao_joined", "contract_status", "contract_received")
#: 시트 올리기가 덮지 않는 투자컨설턴트 칸(이어진 줄에서 — 결정 7). 올리기는 메타 탭에 든다.
CONSULTING_SLOTS = frozenset(c for c, *_ in FIELDS.values() if c)

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
#: 금액에 단위가 적혀 있나(`8.2억` · `5천만원` · `1,224백만원`).
UNIT = re.compile(r"[억만천원]")

#: `session.info` 열쇠 — 켜져 있으면 따라 고칠 때 **빈칸만** 채운다(`fill_only`).
FILL_ONLY = "company_sync_fill_only"
#: `session.info` 열쇠 — 켜져 있으면 새 줄을 이름으로 잇지 않는다. 부르는 쪽이 이을
#: 기업을 따로 정해 줄 때(투자컨설턴트 → 스타트업 보내기)다 — 이름으로 먼저 다른 IR 에
#: 붙었다 옮기면 그 IR 의 빈칸이 엉뚱한 값으로 채워진다.
NO_AUTO_LINK = "company_sync_no_auto_link"
#: `session.info` 열쇠 — 이번 flush 에서 새로 생기거나 이름이 바뀐 IR 기업(`after_flush`).
NEW_NAMES = "company_sync_new_names"


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
    if field in revenue_years.FIELDS:
        # 연도 칸은 적힌 그대로 한줄 소개에 실린다 — Series A 의 `18.3`(단위 억)은 `18.3억`
        # 으로 맞춘다(`revenue_years.roll_over` 와 같은 규칙). 단위가 적힌 글은 그대로.
        return text if UNIT.search(text) else (amount.phrase(text) or text)
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
    elif field in revenue_years.FIELDS:
        return (norm(field, a) or "") == (norm(field, b) or "")   # `18.3` 과 `18.3억` 은 같다
    return _raw(a) == _raw(b)


def label(field: str) -> str:
    """화면 이름 — 연도 매출은 그해 글자(`25년 매출` · 올해 칸 `26년 매출`)."""
    if field == "revenue_recent":
        return revenue_years.recent_label()
    if field in revenue_years.FIELDS:
        return f"{field[-2:]}년 매출"
    return LABELS.get(field, field)


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


def _year_slot(field: str) -> Optional[str]:
    """IR 연도 매출 칸 `field` 를 받는 Series A 칸 — 올해(`revenue_years.this_year`) 기준.

    올해 칸 ↔ IR `revenue_recent`, 지난 해 칸 ↔ IR 같은 해 칸. 앞으로 올 해 칸은
    None — IR 에 받을 칸이 없다(그해가 오면 `revenue_recent` 와 잇는다).
    """
    year = revenue_years.this_year()
    if field == "revenue_recent":
        want = f"revenue_{year}"
    else:
        want = field if int(field[-4:]) < year else None
    return want if want in SERIES_A_YEARS else None


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
    if isinstance(row, SeriesACompany):
        where = FIELDS[field][2]
        return _year_slot(field) if where == YEAR else where
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


def _before(company: IrCompany, field: str) -> Optional[str]:
    """IR 칸의 이번 flush 전 값(옮길 꼴) — `_follows` 가 견준다."""
    deleted = get_history(company, field).deleted
    return norm(field, deleted[0] if deleted else None, field)


def _follows(other: Row, where: str, field: str, before) -> bool:
    """IR 을 따라 이 줄을 고쳐도 되나 — Series A 줄은 빈칸 · IR 의 이전 값과 같던 칸만.

    다른 값은 딜 소싱에서 따로 쓰는 값이라 덮지 않는다(10/26 사용자: "딜 소싱쪽에서
    별도로 사용된 값이 있는거라면 덮어쓰지 말아주면 됨"). 다른 표는 그대로 따라간다.
    """
    if not isinstance(other, SeriesACompany):
        return True
    current = _value(other, where, field)
    return not current or same(field, current, before)


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
            found = [r for model in MODELS
                     for r in session.execute(select(model).where(
                         model.ir_company_id == company_id)).scalars()]
        found += [o for o in list(session.new) + list(session.dirty)
                  if isinstance(o, MODELS)]
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
    """줄을 이름이 **정확히 하나** 맞는 IR 기업에 잇는다(결정 2 · `자동 연결`).

    후보가 여럿이거나 없으면 그대로 둔다 — `/ir-link` 에서 사람이 고른다(이미 저절로
    이어진 줄이면 그 연결도 그대로). 스타트업 명단 줄은 스타트업 화면의 명단에 올라
    있을 때만 — 투자사 줄의 `firm` 은 투자사다.
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
        found = idx.candidates(ir_link.row_name(row))
        if len(found) == 1 and found[0].id != row.ir_company_id:
            row.ir_company_id = found[0].id
            row.ir_link_auto = 1


def _renamed(obj) -> bool:
    """이번 flush 에서 이름이 **비교용 이름까지** 바뀌었나(띄어쓰기 · `(주)` 만 고친 것은 아니다).
    스타트업 명단 줄은 기업명이 `firm` 이다(`name` 은 대표 성함 — `ir_link.row_name`)."""
    from .deal_history import _key

    history = get_history(obj, "firm" if isinstance(obj, VcContact) else "name")
    if not history.added:
        return False
    before = history.deleted[0] if history.deleted else None
    return _key(history.added[0]) != _key(before)


def after_flush(session: Session) -> None:
    """IR 기업이 새로 생기거나 이름이 바뀌었다 → 그 이름이 **정확히 하나** 맞는, 아직 안
    이은 Series A 줄을 잇는다(머리말 규칙 6). `app/models.py` 가 `after_flush_postexec` 로
    건다 — 새 기업은 이제야 번호가 있다. 여기서 바꾼 줄은 커밋이 한 번 더 flush 하고
    (`Session.commit` 이 깨끗해질 때까지 flush 한다), 그 `before_flush` 가 빈칸을 채운다.
    """
    from .deal_history import _key

    companies = session.info.pop(NEW_NAMES, None)
    if not companies or session.info.get(NO_AUTO_LINK):
        return
    keys = {_key(c.name) for c in companies if c.id and c not in session.deleted} - {""}
    if not keys:
        return
    with session.no_autoflush:
        rows = [r for r in session.execute(select(SeriesACompany).where(
                    SeriesACompany.ir_company_id.is_(None))).scalars()
                if _key(r.name) in keys]
    if rows:
        _auto_link(session, rows)


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


def clear_same(session: Session, row: SeriesACompany) -> int:
    """연결을 풀기 전 — Series A 줄에서 **지금 IR 과 같은 칸**만 비운다. 비운 칸 수.

    10/26 사용자: "연결 해제를 할 경우에 연결된 정보도 지워지게". 어느 칸이 IR 에서 왔는지
    적어 둔 곳이 없어 IR 과 같은 값을 IR 에서 온 값으로 본다 — 다른 값은 딜 소싱의 값이라
    둔다(`_follows` 와 같은 결). IR 쪽은 안 건드린다(비우기는 따라가지 않는다 — `_changes`).
    """
    company = session.get(IrCompany, row.ir_company_id)
    if company is None:
        return 0
    cleared = 0
    for field, where in _places(row, {}).items():
        theirs, mine = _value(company, field, field), _raw(_get(row, where))
        if theirs and mine and same(field, mine, theirs):
            _set(row, where, None)
            cleared += 1
    return cleared


def before_flush(session: Session) -> None:
    """flush 직전 — 새 줄을 잇고, 이은 줄은 빈칸만 채우고, 고친 칸은 따라 고친다.

    `app/models.py` 가 세션 이벤트로 건다(모든 flush 가 지난다). 차례:
    ① 새 줄 자동 연결 → ② 바뀐 칸을 **먼저 다 읽어 둔다**(아래 ③이 적는 값이 '고친
    것' 으로 읽히지 않게) → ③ 이어진 줄은 빈칸만 채움 → ④ IR 을 고친 칸 → 이어진 줄
    → ⑤ 줄을 고친 칸 → IR · 다른 줄(④가 이미 적은 칸은 건너뛴다 — IR 이 이긴다).
    """
    rows = [o for o in list(session.new) + list(session.dirty)
            if isinstance(o, MODELS) and o not in session.deleted]
    companies = [o for o in session.dirty
                 if isinstance(o, IrCompany) and o not in session.deleted and o.id]
    # 새로 생기거나 이름이 바뀐 IR 기업 — 번호가 정해진 뒤 `after_flush` 가 줄을 잇는다.
    # flush 마다 새로 적는다(실패한 flush 의 목록이 다음 flush 로 넘어가지 않게).
    session.info[NEW_NAMES] = [o for o in session.new if isinstance(o, IrCompany)] + [
        c for c in companies if _renamed(c)]
    if not rows and not companies:
        return
    # 새 줄 · 기업명을 고친 Series A · 스타트업 명단 줄(안 이었거나 저절로 이은 줄 — 사람이
    # 고른 연결은 둔다). 스타트업 줄은 #85 — `기업명` 칸 후보에서 IR 기업을 고르면 잇는다
    # (투자사 줄은 `_auto_link` 가 거른다).
    fresh = [r for r in rows if (r in session.new and not r.ir_company_id) or (
        isinstance(r, (SeriesACompany, VcContact)) and r not in session.new
        and (not r.ir_company_id or r.ir_link_auto) and _renamed(r))]
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
            before = _before(company, field)
            for other in run.linked(company.id):
                if (w := slot(other, field, run.kinds)) and _follows(other, w, field, before):
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
            before = _value(company, field, field)   # 고치기 전에 잡아 둔다(`_follows`)
            # IR 에도 같은 규칙(`_put`) — 빈칸만 모드 · 같은 값 · O/X 칸의 자유 글은 그대로.
            if not _put(company, field, field, value, run.fill_only) \
                    and not same(field, getattr(company, field), value):
                continue
            wrote.add((company.id, field))
            for other in run.linked(company.id):
                # 같은 flush 에서 그 줄도 이 칸을 고쳤으면 제 손으로 고친 값을 둔다.
                if (other is not row and field not in touched.get(id(other), ())
                        and (w := slot(other, field, run.kinds))
                        and _follows(other, w, field, before)):
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
    return {w for _c, w, _a in FIELDS.values() if w and _raw(_get(row, w))}


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
            shown, mine_shown = theirs, mine
            if field == CONTRACT:
                shown = CONTRACT_LABELS.get(_key(theirs), theirs)
                mine_shown = CONTRACT_LABELS.get(mine, mine)   # Series A 줄은 열쇠(`paid`)를 적는다
            out.setdefault(row.id, []).append({
                "field": field, "label": label(field), "row": mine_shown, "ir": shown,
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
            raise ValueError(f"이 줄의 {label(field)} 값은 IR 로 옮길 수 없습니다")
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
    rows = [row] + [r for model in MODELS
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
