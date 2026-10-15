"""딜 소싱 ↔ 투자사 관리 현황 — **한 사람을 한쪽에서 고치면 다른 쪽도 따라온다.**

같은 심사역이 두 표에 산다. 투자사 관리 현황(`vc_contacts` — 딜소개를 보내는
명단)과 딜 소싱(`sourcing_contacts` — 우리 딜을 같이 볼 사람). 지금까지는 두
메뉴에서 따로 적었다 — 투자사 관리 현황에서 "이 분 시리즈 A 딜 소싱 참여하신대"
를 듣고 딜 소싱 메뉴로 가서 이름 · 회사 · 번호를 다시 쳐 넣었다.

## 무엇을 잇나 — `시리즈 A 이상 딜 소싱 참여 심사역` 갈래 하나

잇는 것은 **그 갈래의 줄뿐**이다(`SYNC_BUCKET`). 사용자가 정했다 — "딜소싱
연동은 시리즈 A 이상 딜 소싱 참여 심사역 탭에만". M&A · 후속투자 같은 다른
갈래에 같은 분이 있어도 그 줄은 건드리지 않는다(옮기지도, 잇지도 않는다).

## 칸은 하나다 — 따로 저장하지 않는다

투자사 관리 현황의 `Series A 딜 소싱` 칸(O / X / 빈칸)은 **값이 없다.** 그
투자사 줄에 이어진 소싱 줄(`SourcingContact.vc_contact_id`)의
`participation` 을 읽어 그린다.

    이어진 줄 있음 · 참여    →  O
    이어진 줄 있음 · 불참여  →  X
    이어진 줄 없음           →  빈칸

그래서 딜 소싱 화면에서 `참여` 를 `불참여` 로 바꾸면 투자사 관리 현황의 그 칸이
그대로 X 가 된다 — 두 화면이 **같은 칸 하나**를 본다. O/X 를 투자사 쪽에
따로 적어 두는 길을 고르지 않은 이유가 그것이다: 두 벌을 맞추는 코드는 반드시
한쪽이 빠지고, 이 저장소가 반복해 당한 사고가 정확히 그 모양이다.

## 칸을 고치면 (`set_mark`)

    O  이어진 줄이 있으면 `참여` 로. 없으면 그 갈래에서 **같은 사람**을 찾아
       잇고(번호 → 이름+회사), 그래도 없으면 **새 줄을 만든다**.
    X  이어진 줄을 `불참여` 로. **지우지 않는다** — 리마인드 · `딜 받음` 이력이
       그 줄에 달려 있고, 다시 참여하시면 그대로 돌아온다.
    빈칸  이어진 줄이 없으면 그대로. 이어진 줄이 있으면 **막는다** — 빠지는
       것은 X 다(지우는 것은 딜 소싱 화면의 [삭제]).

## 딜 소싱에서 사람을 넣거나 번호를 고치면 (`auto_link`)

그 갈래 줄이고 아직 안 이어졌으면 **번호로** 투자사 관리 현황의 줄을 찾아
잇는다 — 번호가 딱 한 줄에만 맞을 때만. 그러면 투자사 쪽 칸이 곧바로 O 다.
이름으로는 저절로 잇지 않는다 — 같은 이름이 여럿이다(`sourcing_link` 머리말).

## 이어진 두 줄의 같은 칸 — **고치면 따라 고친다** (`before_flush`)

이름 · 직함 · 회사 · 휴대폰 · 메일(`SHARED_FIELDS`)은 두 표에 다 있다. 이어진
뒤에 한쪽에서 고치면 다른 쪽에도 같은 값을 적는다.

**왜 '쓸 때 따라 고친다' 인가 — '읽을 때 한쪽에서 가져온다' 가 아니라.**
소싱 줄의 이름 · 회사 · 메일을 읽는 곳이 많다 — 딜 소싱 제안 문구
(`routers/deals.py`), 메일 확인이 보낸 주소를 맞추는 곳(`sourcing_receipts.
addresses_of`), 딜 소싱 표 · 엑셀. 읽는 쪽을 다 고치면 하나는 반드시 빠지고,
빠진 곳만 옛 값을 쓴다. 쓰는 쪽은 **ORM 세션의 flush 한 자리**라(수정 로그
`edit_log` 가 같은 이유로 거기 서 있다) 화면 PATCH · 시트 가져오기 · 검사 어느
길로 고쳐도 빠뜨릴 수 없다. 그리고 투자사 줄이 지워져도 소싱 줄은 자기 값을
그대로 들고 남는다.

**이을 때 서로 다른 값은 덮지 않는다.** 잇는 순간에는 소싱 줄의 **빈 칸만**
투자사 줄 값으로 채운다(`link`). 이미 다르게 적힌 값(직함 · 회사 표기)은 둘 다
사람이 적은 것이라 어느 쪽이 맞는지 코드가 모른다 — 딜 소싱 화면의 연결 표시가
`다른 칸` 으로 알려 주고, 어느 쪽에서든 한 번 고치면 그때부터 같아진다.

**빈 값은 넘어가지 않는다.** 따라 고치는 것은 **빈칸이 아닌 값으로 고친 칸**
뿐이다(`_changed` · `_copy`). None · `""` · 공백은 모두 같은 '빈칸' 이라, 수정창이
비어 있던 칸(None)을 `""` 로 다시 적는 것은 고친 것이 아니다 — 수정창은 칸을
전부 보낸다(`contacts.js` 의 `readForm`). 그것을 고친 것으로 읽으면 메모 한 줄
저장에 이어진 소싱 줄의 메일 · 직함이 지워지고, 메일 확인(`sourcing_receipts.
addresses_of`)이 그분을 못 찾는다(PR #284 리뷰). 한쪽에서 일부러 비워도 다른
쪽은 그대로 둔다 — 비운 칸은 `다른 칸` 으로 보이고, 지우는 것은 각 표에서 한다.

## 잇지 않는 것 — 카톡방 · 담당 · 권한  ★

사용자가 짚었다 — "딜소싱에 있다는건 다른 사람 담당자라도 카톡방에 초대
되어있다는 뜻이므로, 투자사 관리 현황이랑은 다르게 생각해야함". 딜 소싱 줄은
**보내는 사람 카톡의 딜 소싱 방**에 있는 분이고, 투자사 줄을 누가 맡았는지와
따로 관리한다.

  · **카톡방** — 잇지도, 베끼지도, 이어받지도 않는다. 이 갈래 줄은 자기 방
    이름이 없으면 `방 없음` 이고(`sourcing_link.linked_rooms`), 딜 소싱 화면의
    [방 후보 찾기]로 보내는 사람 카톡에서 찾아 확정한다(`sourcing_rooms`).
  · **담당** — 따라 고치지 않는다. O 로 새 줄을 만들 때만 **O 를 넣은 사람**을
    담당으로 적는다(`create_row`) — 그 뒤로는 딜 소싱에서 따로 관리한다.
  · **권한** — 투자사 칸(O/X)은 그 투자사 줄을 고칠 수 있는 사람(담당 · 관리자
    — `routers/contacts._owned`)이다. 딜 소싱 쪽은 지금까지처럼 로그인한 누구나
    고친다(이어진 줄이어도 같다). 이어진 줄의 같은 칸을 딜 소싱에서 고치면 남의
    투자사 줄로도 넘어가는데, 그 일은 수정 로그에 `남의 것` 으로 남는다(`edit_log`).
"""
from __future__ import annotations

import re
from typing import Dict, Iterable, List, Optional
from urllib.parse import quote

from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import get_history

from .. import clock
from ..models import SourcingContact, User, VcContact
from . import sheet_owner, sourcing_link

#: 투자사 관리 현황과 잇는 **하나뿐인** 갈래. 원본 시트의 탭 이름 그대로다
#: (운영 21줄 · 2026-10). 이 이름은 딜 소싱 화면에서 바꿀 수 없다
#: (`sourcing_buckets.rename`) — 바꾸면 이 글자와 갈려 잇기가 통째로 끊긴다.
SYNC_BUCKET = "시리즈 A 이상 딜 소싱 참여 심사역"

#: 투자사 관리 현황의 칸 이름. 어느 갈래와 이어지는지가 이름에 드러나야 한다 —
#: 그 표에는 원본 시트의 `딜소싱 참여 투자사`(자유 글 칸)가 이미 있다.
COLUMN_LABEL = "Series A 딜 소싱"

JOINED = "참여"
LEFT = "불참여"

MARK_JOINED = "O"
MARK_LEFT = "X"
MARKS = {JOINED: MARK_JOINED, LEFT: MARK_LEFT}

#: 두 표에 다 있는 칸 — 이어진 뒤에는 한쪽을 고치면 다른 쪽도 같이 고친다.
SHARED_FIELDS = ("name", "title", "firm", "phone", "email")
#: 화면에 부를 이름. 딜 소싱 표의 머리글과 같은 말이다.
SHARED_LABELS = {"name": "이름", "title": "직함", "firm": "회사",
                 "phone": "휴대폰", "email": "이메일"}

#: 휴대폰으로 인정할 최소 자릿수 — 방을 잇는 규칙과 **같은 값**이다.
MIN_DIGITS = sourcing_link.MIN_DIGITS


class SyncError(Exception):
    """잇지 못한 까닭. 화면에 그대로 띄운다(400)."""


# ── 값 읽기 ──────────────────────────────────────────────────────────────────

def participation_of(row) -> str:
    """`참여` | `불참여`. 비어 있거나 모르는 값은 `참여` 로 본다(칸의 기본값)."""
    return LEFT if (getattr(row, "participation", "") or "").strip() == LEFT else JOINED


def takes_part(row) -> bool:
    """딜 소싱 제안(처음 안내 · 월간 리마인드)을 받는 사람인가."""
    return participation_of(row) != LEFT


def normalize_participation(value: Optional[str]) -> str:
    """사람이 적은 값을 `참여`/`불참여` 로. 모르는 말은 막는다(조용히 버리지 않는다)."""
    text = (value or "").strip()
    if text in (JOINED, MARK_JOINED, "o", "○"):
        return JOINED
    if text in (LEFT, MARK_LEFT, "x", "×"):
        return LEFT
    raise SyncError(f"참여 칸에는 '{JOINED}' 나 '{LEFT}' 만 적습니다: {text or '(빈칸)'}")


def normalize_mark(value: Optional[str]) -> str:
    """투자사 관리 현황 칸에 적은 값 → `O` · `X` · 빈칸."""
    text = (value or "").strip()
    if not text:
        return ""
    if text in (MARK_JOINED, "o", "○", JOINED):
        return MARK_JOINED
    if text in (MARK_LEFT, "x", "×", LEFT):
        return MARK_LEFT
    raise SyncError(f"{COLUMN_LABEL} 칸에는 O(참여) 나 X(불참여) 만 적습니다: {text}")


def mark_of(row: Optional[SourcingContact]) -> str:
    """이어진 소싱 줄 → 투자사 관리 현황 칸 값."""
    return "" if row is None else MARKS[participation_of(row)]


def is_synced(row) -> bool:
    """이 소싱 줄이 투자사 관리 현황과 이어지는 갈래의 줄인가."""
    return (getattr(row, "bucket", "") or "") == SYNC_BUCKET


def digits(phone: Optional[str]) -> str:
    return sourcing_link.digits(phone)


def _key(text: Optional[str]) -> str:
    return re.sub(r"\s+", "", text or "").lower()


def _text(value) -> str:
    """None · `""` · 공백은 모두 `""` — 같은 '빈칸' 이다."""
    return (value or "").strip() if isinstance(value, str) or value is None else str(value)


def same_value(field: str, a, b) -> bool:
    """두 표의 같은 칸이 같은 값인가. 휴대폰은 **숫자만** 본다 —
    `010-1234-5678` 과 `01012345678` 은 같은 번호다(잇는 규칙도 숫자로 맞춘다)."""
    if field == "phone":
        return digits(_text(a)) == digits(_text(b))
    return _text(a) == _text(b)


def linked_rows(db: Session, contact_ids: Iterable[int]) -> Dict[int, SourcingContact]:
    """투자사 줄 번호 → 이어진 소싱 줄. **한 번에** 읽는다(표 한 장에 질의 하나)."""
    ids = [i for i in dict.fromkeys(contact_ids) if i]
    if not ids:
        return {}
    rows = db.execute(
        select(SourcingContact).where(SourcingContact.vc_contact_id.in_(ids),
                                      SourcingContact.bucket == SYNC_BUCKET)
    ).scalars().all()
    return {r.vc_contact_id: r for r in rows}


def marks_for(db: Session, contact_ids: Iterable[int]) -> Dict[int, str]:
    """투자사 줄 번호 → `O`/`X`. 이어진 줄이 없는 번호는 빠진다(= 빈칸)."""
    return {cid: mark_of(row) for cid, row in linked_rows(db, contact_ids).items()}


def linked_row(db: Session, contact: VcContact) -> Optional[SourcingContact]:
    return linked_rows(db, [contact.id]).get(contact.id)


def _sync_rows(db: Session) -> List[SourcingContact]:
    return list(db.execute(
        select(SourcingContact).where(SourcingContact.bucket == SYNC_BUCKET)
        .order_by(SourcingContact.id)
    ).scalars().all())


# ── 같은 사람 찾기 ──────────────────────────────────────────────────────────

def _phone_conflict(row: SourcingContact, phone: str) -> bool:
    """두 줄 다 번호가 있는데 다르다 — 이름 · 회사가 같아도 다른 사람이다."""
    other = digits(row.phone)
    return len(phone) >= MIN_DIGITS and len(other) >= MIN_DIGITS and other != phone


def find_row(db: Session, contact: VcContact) -> Optional[SourcingContact]:
    """이 투자사 줄과 **같은 사람**인 그 갈래의 소싱 줄 — 번호, 없으면 이름+회사.

    한 줄로 좁혀질 때만 돌려준다. 둘 이상이면 어느 줄인지 코드가 고르지 않고
    **막는다**(`SyncError`) — 하나를 골라 두면 반은 틀린다.

    찾은 줄이 이미 **다른 투자사 줄**과 이어져 있어도 막는다. 같은 분이 두
    팀원 명단에 한 줄씩 있는 경우인데(`sheet_import` 의 `따로 만들기`), 여기서
    새 줄을 또 만들면 그 분께 딜 소싱 제안이 두 번 나간다.
    """
    rows = _sync_rows(db)
    phone = digits(contact.phone)

    def pick(same: List[SourcingContact], how: str) -> Optional[SourcingContact]:
        mine = [r for r in same if r.vc_contact_id in (None, contact.id)]
        taken = [r for r in same if r.vc_contact_id not in (None, contact.id)]
        if taken and not mine:
            owner = db.get(VcContact, taken[0].vc_contact_id)
            who = sheet_owner.labels_of(owner.source_sheet)[0] if owner else "다른"
            raise SyncError(
                f"딜 소싱 › {SYNC_BUCKET} 의 '{taken[0].name}' 줄이 이미 투자사 관리 "
                f"현황의 다른 줄({who} 명단)과 이어져 있습니다 — 같은 분이면 그 줄에서 "
                "O/X 를 고치세요(한 분께 딜 소싱 제안이 두 번 나가지 않게 한 줄만 잇습니다).")
        if len(mine) > 1:
            raise SyncError(
                f"딜 소싱 › {SYNC_BUCKET} 에 {how}이 같은 줄이 {len(mine)}개라 어느 줄인지 "
                "정할 수 없습니다 — 딜 소싱 화면에서 겹친 줄을 먼저 정리해 주세요.")
        return mine[0] if mine else None

    if len(phone) >= MIN_DIGITS:
        found = pick([r for r in rows if digits(r.phone) == phone], "번호")
        if found is not None:
            return found
    name, firm = _key(contact.name), _key(contact.firm)
    if name and firm:
        return pick([r for r in rows if _key(r.name) == name and _key(r.firm) == firm
                     and not _phone_conflict(r, phone)], "이름 · 회사")
    return None


def other_buckets(db: Session, contact: VcContact) -> List[str]:
    """같은 번호가 **다른 갈래**에도 있는가 — 그 줄은 건드리지 않았다고 말해 준다."""
    phone = digits(contact.phone)
    if len(phone) < MIN_DIGITS:
        return []
    out: List[str] = []
    for bucket, raw in db.execute(
        select(SourcingContact.bucket, SourcingContact.phone)
        .where(SourcingContact.bucket != SYNC_BUCKET)
    ).all():
        if digits(raw) == phone and bucket not in out:
            out.append(bucket)
    return out


# ── 잇기 · 만들기 ───────────────────────────────────────────────────────────

def link(row: SourcingContact, contact: VcContact) -> None:
    """두 줄을 잇는다. 소싱 줄의 **빈 칸만** 투자사 줄 값으로 채운다.

    이미 적힌 값은 덮지 않는다 — 둘 다 사람이 적은 값이라 어느 쪽이 맞는지
    모른다(모듈 머리말). 투자사 줄은 **건드리지 않는다**: 잇는 일은 소싱 줄
    한 줄에만 적힌다.
    """
    row.vc_contact_id = contact.id
    for field in SHARED_FIELDS:
        theirs = _text(getattr(contact, field, None))
        if theirs and not _text(getattr(row, field, None)):
            setattr(row, field, theirs)


def assignee_for(db: Session, contact: VcContact, user: Optional[User]) -> str:
    """새 소싱 줄의 담당 — **O 를 넣은 사람**. 이름이 없으면 그 투자사 줄의 주인.

    투자사 줄의 주인을 그대로 옮기지 않는 까닭은 모듈 머리말(★)에 있다 — 딜
    소싱은 투자사 줄을 누가 맡았는지와 따로 관리한다. 넣은 사람이 그 분을 딜
    소싱 방에 둔 사람이라고 보는 것이 가장 덜 틀린다. 그 뒤로는 따라 고치지 않는다.
    """
    name = sheet_owner.real_name(user) if user is not None else ""
    if name:
        return name
    owner = db.get(User, contact.user_id) if contact.user_id else None
    return sheet_owner.real_name(owner) if owner is not None else ""


def create_row(db: Session, contact: VcContact, participation: str = JOINED,
               user: Optional[User] = None) -> SourcingContact:
    """그 갈래 맨 아래에 새 줄. 카톡방은 **비워 둔다** — 보내는 사람 카톡에서
    [방 후보 찾기]로 찾는다(모듈 머리말 ★)."""
    last = db.execute(
        select(func.max(SourcingContact.position))
        .where(SourcingContact.bucket == SYNC_BUCKET)
    ).scalar() or 0
    row = SourcingContact(
        bucket=SYNC_BUCKET, position=last + 1,
        name=_text(contact.name) or "(이름 없음)",
        title=_text(contact.title) or None,
        firm=_text(contact.firm) or None,
        phone=_text(contact.phone) or None,
        email=_text(contact.email) or None,
        assignee_name=assignee_for(db, contact, user) or None,
        # 참여하신 날 — 이 명단은 참여 요청일 최신순이라 방금 넣은 분이 맨 위다.
        requested_at=clock.today().isoformat(),
        room_verified="unverified",
        participation=participation,
        vc_contact_id=contact.id,
    )
    db.add(row)
    return row


def set_mark(db: Session, contact: VcContact, value: Optional[str],
             user: Optional[User] = None) -> dict:
    """투자사 관리 현황의 `Series A 딜 소싱` 칸을 고친다.

    돌려주는 것: `{"mark": 지금 칸 값, "message": 화면에 띄울 한 줄}`.
    `db.commit()` 은 부르는 쪽이 한다. 못 하는 까닭은 `SyncError`.
    """
    mark = normalize_mark(value)
    row = linked_row(db, contact)
    if not mark:
        if row is not None:
            raise SyncError(
                f"딜 소싱 › {SYNC_BUCKET} 에 이어진 분이라 비울 수 없습니다 — 빠지시면 "
                "X(불참여)로 두세요. 줄을 아예 빼려면 딜 소싱 화면에서 [삭제] 합니다.")
        return {"mark": "", "message": ""}

    want = JOINED if mark == MARK_JOINED else LEFT
    message = ""
    if row is None:
        if not sheet_owner.on_investor_list(contact, sheet_owner.hidden_labels(db)):
            raise SyncError("투자사 명단의 줄만 딜 소싱에 넣습니다 — 이 줄은 투자사로 "
                            "세지 않는 명단에 있습니다.")
        row = find_row(db, contact)
        if row is not None:
            link(row, contact)
            message = f"딜 소싱 › {SYNC_BUCKET} 에 있던 '{row.name}' 줄과 이었습니다."
        elif want == LEFT:
            raise SyncError(
                f"딜 소싱 › {SYNC_BUCKET} 에 없는 분이라 X 로 둘 줄이 없습니다 — "
                "빈칸이 '딜 소싱에 없음' 입니다.")
        else:
            row = create_row(db, contact, JOINED, user)
            message = (f"딜 소싱 › {SYNC_BUCKET} 에 새로 넣었습니다 — 카톡방은 딜 소싱 "
                       "화면의 [방 후보 찾기]로 보내는 분 카톡에서 찾아 확정하세요.")
            others = other_buckets(db, contact)
            if others:
                message += (f" 다른 갈래({', '.join(others)})에도 있는 분이라 그 줄은 "
                            "그대로 둡니다.")
    if participation_of(row) != want:
        row.participation = want
        if not message:
            message = f"딜 소싱에서 '{want}' 으로 바꿨습니다."
    return {"mark": mark, "message": message}


def auto_link(db: Session, row: SourcingContact) -> Optional[VcContact]:
    """딜 소싱 쪽에서 넣거나 번호를 고친 줄 — 투자사 관리 현황의 같은 분과 잇는다.

    **번호가 딱 한 줄에만 맞을 때만**이다. 투자사 쪽에 같은 번호가 둘이거나
    (두 팀원 명단에 한 줄씩), 이 갈래에 같은 번호가 또 있거나, 맞은 투자사 줄이
    이미 다른 소싱 줄과 이어져 있으면 잇지 않는다. 투자사로 세는 명단만 본다
    (`sheet_owner.investors` — 방을 잇는 `sourcing_link` 와 같은 모집단).
    이주(`0093_sourcing_vc_link`)가 처음 한 번 이은 규칙도 이것과 같다.
    """
    if not is_synced(row) or row.vc_contact_id:
        return None
    phone = digits(row.phone)
    if len(phone) < MIN_DIGITS:
        return None
    if any(digits(other.phone) == phone for other in _sync_rows(db)
           if other.id != row.id):
        return None
    contacts = [c for c in sheet_owner.investors(
        db, db.execute(select(VcContact)).scalars().all())
        if digits(c.phone) == phone]
    if len(contacts) != 1:
        return None
    contact = contacts[0]
    if linked_row(db, contact) is not None:
        return None
    link(row, contact)
    return contact


# ── 화면 ────────────────────────────────────────────────────────────────────

def badges(db: Session, rows: Iterable[SourcingContact]) -> Dict[int, dict]:
    """딜 소싱 표의 연결 표시 — `투자사 관리 현황: ○○ 명단`.

    `{소싱 줄 번호: {"sheet": 명단 이름, "href": 그 명단 주소, "diff": [다른 칸 이름]}}`.
    `diff` 는 **이을 때 이미 달랐던 칸**이다(모듈 머리말) — 어느 쪽에서든
    한 번 고치면 같아진다.
    """
    rows = [r for r in rows if r.vc_contact_id and is_synced(r)]
    if not rows:
        return {}
    contacts = {c.id: c for c in db.execute(
        select(VcContact).where(VcContact.id.in_({r.vc_contact_id for r in rows}))
    ).scalars().all()}
    hidden = sheet_owner.hidden_labels(db)
    out: Dict[int, dict] = {}
    for row in rows:
        contact = contacts.get(row.vc_contact_id)
        if contact is None:
            continue
        labels = sheet_owner.labels_of(contact.source_sheet)
        sheet = next((label for label in labels if label not in hidden), labels[0])
        out[row.id] = {
            "contact_id": contact.id,
            "sheet": sheet,
            "href": f"{sheet_owner.page_href(db, sheet)}?sheet={quote(sheet)}",
            "diff": [SHARED_LABELS[f] for f in SHARED_FIELDS
                     if not same_value(f, getattr(row, f, None),
                                       getattr(contact, f, None))],
        }
    return out


# ── 따라 고치기 · 끊기 — 세션 flush 한 자리 ─────────────────────────────────

def _changed(obj) -> List[str]:
    """이번 flush 에서 **빈칸 아닌 값으로 실제로 바뀐** 같은 칸.

    빠지는 것: 같은 값을 다시 적은 것, None ↔ `""` ↔ 공백처럼 빈칸끼리 바뀐 것
    (수정창이 빈 칸을 `""` 로 다시 적는다), 비운 것(빈 값은 넘어가지 않는다 —
    모듈 머리말).
    """
    out = []
    for field in SHARED_FIELDS:
        history = get_history(obj, field)
        if not history.added:
            continue
        after = _text(history.added[0])
        before = _text(history.deleted[0]) if history.deleted else ""
        if after and after != before:
            out.append(field)
    return out


def _copy(src, dst, field: str) -> bool:
    value = _text(getattr(src, field, None))
    if not value:
        # 빈 값은 다른 쪽을 지우지 않는다(모듈 머리말). 이름은 원래 비울 수 없다.
        return False
    if value == _text(getattr(dst, field, None)):
        return False
    setattr(dst, field, value)
    return True


def detach(session: Session, contact_ids: List[int]) -> None:
    """지워지는 투자사 줄을 가리키던 소싱 줄의 연결만 끊는다 — 줄은 남긴다.

    DB 에는 **먼저 바로 적는다**(Core UPDATE). 같은 flush 안에서 소싱 줄을
    고치고 투자사 줄을 지우면, 둘 사이에 관계(`relationship`)가 없어 어느 쪽이
    먼저 나갈지 SQLAlchemy 가 모른다 — 지우기가 먼저 나가면 외래키에 막힌다.
    여기서 먼저 적어 두면 차례를 탈 일이 없다.

    그다음 그 소싱 줄들을 세션에 올려 **ORM 으로도 같은 값**(None)을 적는다 —
    수정 로그(`edit_log`)는 flush 의 바뀐 줄만 읽으므로, 그래야 '끊김' 이
    `vc_contact_id: 번호 → 빈칸` 으로 남는다(PR #284 리뷰 — 잇기 · 만들기는
    남는데 끊기만 빠졌다). 이 ORM UPDATE 는 이미 NULL 인 칸에 NULL 을 다시
    적으므로 지우기보다 늦게 나가도 외래키에 걸리지 않는다. 이 훅은 수정 로그의
    `before_flush` 보다 먼저 걸린다(`models._sync_sourcing_links`).
    """
    ids = [i for i in contact_ids if i]
    if not ids:
        return
    with session.no_autoflush:
        rows = list(session.execute(
            select(SourcingContact).where(SourcingContact.vc_contact_id.in_(ids))
        ).scalars().all())
    # 세션에서 이번 flush 에 막 이어 둔 줄(아직 DB 에 안 적힌 값)도 함께.
    rows += [obj for obj in list(session.identity_map.values())
             if isinstance(obj, SourcingContact) and obj.vc_contact_id in ids
             and obj not in rows]
    table = SourcingContact.__table__
    session.execute(table.update().where(table.c.vc_contact_id.in_(ids))
                    .values(vc_contact_id=None))
    for obj in rows:
        if obj not in session.deleted:
            obj.vc_contact_id = None


def before_flush(session: Session) -> None:
    """flush 직전 — 지워지는 투자사 줄은 끊고, 이어진 두 줄의 같은 칸을 맞춘다.

    `app/models.py` 가 세션 이벤트로 건다(모든 flush 가 지난다).

    **한 칸을 두 쪽에서 동시에 고친 flush** 는 투자사 쪽 값이 이긴다 — 먼저
    투자사 → 소싱으로 옮기고, 이미 옮긴 칸은 거꾸로 옮기지 않는다. 화면에서는
    한 번에 한 쪽만 고치므로 생길 일이 거의 없지만, 순서가 정해져 있어야 같은
    입력에 늘 같은 결과가 나온다.
    """
    gone = [o.id for o in session.deleted if isinstance(o, VcContact) and o.id]
    if gone:
        detach(session, gone)

    dirty = list(session.dirty)
    contacts = {}
    for obj in dirty:
        if isinstance(obj, VcContact) and obj not in session.deleted and obj.id:
            changed = _changed(obj)
            if changed:
                contacts[obj.id] = (obj, changed)
    wrote = set()
    if contacts:
        with session.no_autoflush:
            linked = session.execute(
                select(SourcingContact).where(
                    SourcingContact.vc_contact_id.in_(list(contacts)),
                    SourcingContact.bucket == SYNC_BUCKET)
            ).scalars().all()
        for row in linked:
            if row in session.deleted:
                continue
            obj, changed = contacts[row.vc_contact_id]
            for field in changed:
                if _copy(obj, row, field):
                    wrote.add((id(row), field))

    for row in dirty:
        if (not isinstance(row, SourcingContact) or row in session.deleted
                or not row.vc_contact_id or not is_synced(row)):
            continue
        changed = [f for f in _changed(row) if (id(row), f) not in wrote]
        if not changed:
            continue
        with session.no_autoflush:
            contact = session.get(VcContact, row.vc_contact_id)
        if contact is None or contact in session.deleted:
            continue
        for field in changed:
            _copy(row, contact, field)
