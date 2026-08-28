"""명단(시트) — 투자사 풀과 내 명단.

시트가 나뉘어 있던 방식을 그대로 옮긴다. 두 종류가 있다.

- **투자사 풀**: 확보해 둔 투자사 명단(150명·98명·30명 …). 분류 단위일 뿐
  누구의 담당도 아니다. 여기서 사람을 **할당**해 자기 명단을 만든다.
- **내 명단**: 풀에서 할당받아 내가 딜소개를 보내는 사람들.

대시보드의 '내 투자사'는 **내 명단**만 센다. 풀까지 세면 팀이 확보한 전체
인원이 내 담당처럼 보인다 — 실제로 한 사람의 대시보드에 333명이 잡혔다
(본인 담당은 126명).

한 사람이 풀과 내 명단에 함께 있으면(실제로 113명이 그렇다) **내 명단 쪽이
이긴다**. 그 사람에게 딜소개를 보내는 것은 내 명단 쪽 일이기 때문이다.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Set

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import SheetOwner, User, VcContact

# 시트에서 오지 않은 담당자
MANUAL_SHEET = "직접 추가"


def labels_of(value: Optional[str]) -> List[str]:
    """담당자 한 명이 속한 명단들. 임포트마다 시트 이름이 누적된다."""
    labels = [x.strip() for x in (value or "").split(",") if x.strip()]
    return labels or [MANUAL_SHEET]


# 명단 종류. 담당이 정해져 있으면 누군가의 명단, 아니면 아직 풀이다.
KIND_ASSIGNED = "assigned"
KIND_POOL = "pool"

KIND_LABELS = {KIND_ASSIGNED: "담당 명단", KIND_POOL: "투자사 풀"}


def kind_of(user_id: Optional[int]) -> str:
    return KIND_ASSIGNED if user_id else KIND_POOL


def owner_map(db: Session) -> Dict[str, Optional[int]]:
    """{명단 이름: 할당받은 계정 id 또는 None(풀)}."""
    return {
        row.label: row.user_id
        for row in db.execute(select(SheetOwner)).scalars().all()
    }


# ── 투자사로 세지 않는 명단 ─────────────────────────────────────────────────
#
# 명단이라고 다 투자사는 아니다. 스타트업 리마인드 명단처럼 **같은 표에 얹혀
# 있을 뿐 투자사가 아닌** 줄이 섞이면, 투자사 수가 부풀고(전체 306명에 32명이
# 함께 세어졌다) 딜소개 발송 대상 목록에도 같이 뜬다.
#
# **이름으로 거르지 않는다.** `if 이름 == "…"` 를 심으면 다음 명단에서 또
# 심어야 하고, 심는 것을 잊은 화면만 조용히 틀린 수를 보여 준다. 화면에서
# 사람이 켜고 끄는 값(`SheetOwner.is_hidden`)만 본다.
#
# 세는 곳이 열대여섯 군데다. 그래서 판정을 여기 한 번만 적고 모두가 부른다 —
# 예전에 투자사 관리 현황이 117명, 대시보드가 123명이던 사고가 판정을 두 벌로
# 적어 둔 탓이었다.

def hidden_labels(db: Session) -> Set[str]:
    """투자사로 세지 않기로 한 명단 이름들."""
    return {
        row.label
        for row in db.execute(select(SheetOwner)).scalars().all()
        if row.is_hidden
    }


def is_investor(contact: VcContact, hidden: Set[str]) -> bool:
    """이 사람을 투자사로 세는가.

    **감춘 명단에만 있을 때** 빠진다. 한 사람이 여러 명단에 겹쳐 있으면(실제로
    126명이 그렇다) 살아 있는 명단 쪽이 이긴다 — 감춘 명단에 이름이 한 번
    올랐다고 진짜 투자사가 사라지면 안 된다.

    줄 단위로 감춘 사람(`VcContact.is_hidden`)도 빠진다. 표에서 안 보이는
    사람이 수에는 들어가 있으면, 세어 보고 목록에서 찾을 수가 없다.
    """
    if contact.is_hidden:
        return False
    return any(label not in hidden for label in labels_of(contact.source_sheet))


def investors(db: Session, contacts: List[VcContact]) -> List[VcContact]:
    """투자사로 세는 사람만 남긴다. **세거나 보내는 곳은 모두 이것을 지난다.**"""
    hidden = hidden_labels(db)
    return [c for c in contacts if is_investor(c, hidden)]


def my_labels(db: Session, user: User) -> Set[str]:
    """내가 할당받은 명단들. 직접 추가한 담당자는 언제나 내 것이다."""
    mapping = owner_map(db)
    mine = {label for label, uid in mapping.items() if uid == user.id}
    mine.add(MANUAL_SHEET)
    return mine


def is_mine(contact: VcContact, mine: Set[str]) -> bool:
    return any(label in mine for label in labels_of(contact.source_sheet))


def my_contacts(db: Session, user: User) -> List[VcContact]:
    """내 명단에 있는 담당자만. 대시보드·후속의 '내 담당' 기준이다.

    풀에만 있는 사람은 아직 내 담당이 아니다 — 할당해야 내 것이 된다.
    투자사로 세지 않기로 한 명단(`is_investor`)은 여기서 빠진다 — 이 함수를
    지나는 화면이 열 곳이 넘어서, 각자 걸러 두면 한 곳만 다른 수가 나온다.
    """
    mine = my_labels(db, user)
    hidden = hidden_labels(db)
    rows = db.execute(
        select(VcContact).where(VcContact.user_id == user.id)
    ).scalars().all()
    return [c for c in rows if is_mine(c, mine) and is_investor(c, hidden)]


def ensure(db: Session, label: str, user_id: Optional[int] = None,
           assignee_name: Optional[str] = None) -> SheetOwner:
    """명단을 등록한다. 이미 있으면 할당을 **덮지 않는다**.

    시트를 다시 올렸다고 할당이 바뀌면, 명단을 한 번 올린 것만으로
    남의 담당이 넘어간다.
    """
    row = db.execute(
        select(SheetOwner).where(SheetOwner.label == label)
    ).scalars().first()
    if row is None:
        row = SheetOwner(label=label, user_id=user_id, assignee_name=assignee_name)
        db.add(row)
        db.flush()
    elif assignee_name and not row.assignee_name:
        row.assignee_name = assignee_name
    return row


def assign(db: Session, label: str, user_id: Optional[int]) -> SheetOwner:
    """명단을 팀원에게 할당한다(관리자). None 이면 다시 풀로 돌린다."""
    row = ensure(db, label)
    row.user_id = user_id
    db.flush()
    return row


def settings_map(db: Session) -> Dict[str, SheetOwner]:
    """{명단 이름: 그 명단의 설정 줄}. 배치·숨김을 한 번에 읽으려고."""
    return {row.label: row
            for row in db.execute(select(SheetOwner)).scalars().all()}


def layout_of(db: Session, label: str) -> str:
    """이 명단을 어떤 표로 보여 줄까. 정해 두지 않았으면 투자사 명함이다."""
    row = settings_map(db).get(label)
    return (row.layout if row and row.layout else "investor")


def sheet_rows(db: Session, contacts: List[VcContact]) -> List[dict]:
    """명단 목록 + 담당 + 인원. 화면의 탭과 관리 표에 함께 쓴다."""
    settings = settings_map(db)
    names = {
        u.id: u.name for u in db.execute(select(User)).scalars().all()
    }
    total: Dict[str, int] = {}
    connected: Dict[str, int] = {}
    # 줄 단위로 감춘 사람은 탭 건수에서도 빠져야 한다 — 탭에 32라고 적혀
    # 있는데 표에는 열여섯 줄이면 어느 쪽이 맞는지 알 수 없다.
    shown: Dict[str, int] = {}
    for c in contacts:
        for label in labels_of(c.source_sheet):
            total[label] = total.get(label, 0) + 1
            if not c.is_hidden:
                shown[label] = shown.get(label, 0) + 1
            if c.connect_stage == "connected":
                connected[label] = connected.get(label, 0) + 1

    out = []
    for label in sorted(total, key=lambda k: (-connected.get(k, 0), -total[k], k)):
        row = settings.get(label)
        uid = row.user_id if row else None
        out.append({
            "key": label,
            "label": label,
            "count": shown.get(label, 0),
            # 감춘 줄이 몇인지 탭에서 드러나야 한다. 안 드러나면 시트에서
            # 그랬듯 "없는 기업" 으로 읽힌다.
            "hidden_rows": total[label] - shown.get(label, 0),
            "connected": connected.get(label, 0),
            "owner_id": uid,
            "owner": names.get(uid, "") if uid else "",
            "kind": kind_of(uid),
            "kind_label": KIND_LABELS[kind_of(uid)],
            # 시트의 '담당자' 칸에 적힌 이름. 연결 작업을 한 사람이지 소유자가 아니다.
            "written_by": (row.assignee_name or "") if row else "",
            # 이 명단이 쓰는 표 배치와, 투자사로 세는지 여부.
            "layout": (row.layout if row and row.layout else "investor"),
            "is_hidden": bool(row.is_hidden) if row else False,
        })
    return out


def add_to_sheet(db: Session, contacts: List[VcContact], label: str,
                 user_id: int) -> int:
    """풀에 있는 담당자를 내 명단으로 **할당**한다.

    풀에서 빼지 않는다 — 풀은 확보해 둔 전체 명단이고, 거기서 뽑아 쓰는 것이지
    옮기는 것이 아니다. 그래서 출처에 내 명단 이름을 더한다.
    """
    moved = 0
    for contact in contacts:
        labels = labels_of(contact.source_sheet)
        if label in labels:
            continue
        if MANUAL_SHEET in labels:
            labels.remove(MANUAL_SHEET)
        contact.source_sheet = ",".join(labels + [label])
        contact.user_id = user_id
        moved += 1
    db.flush()
    return moved
