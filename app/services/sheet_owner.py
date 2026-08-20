"""명단(시트)별 담당 — 누가 어느 명단을 맡는가.

담당은 사람이 아니라 **명단 단위**로 정해진다. 시트를 나눠 쓰던 방식이 그랬고,
쓰는 사람의 머릿속도 그렇다("내 이름으로 된 탭만 내 담당 투자사").

이걸 두지 않으면 시트를 올린 사람에게 팀 전체가 붙는다 — 실제로 한 사람의
대시보드에 333명이 '내 담당'으로 잡혔다(본인 담당은 126명).

한 사람이 여러 명단에 겹쳐 있으면(실제로 113명이 그렇다) **내 명단에 있으면
내 담당**이다. 그 사람에게 딜소개를 보내는 것은 내 명단 쪽 일이기 때문이다.
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


def owner_map(db: Session) -> Dict[str, Optional[int]]:
    """{명단 이름: 담당 계정 id 또는 None}."""
    return {
        row.label: row.user_id
        for row in db.execute(select(SheetOwner)).scalars().all()
    }


def my_labels(db: Session, user: User) -> Set[str]:
    """내가 담당인 명단들. 직접 추가한 담당자는 언제나 내 것이다."""
    mapping = owner_map(db)
    mine = {label for label, uid in mapping.items() if uid == user.id}
    mine.add(MANUAL_SHEET)
    return mine


def is_mine(contact: VcContact, mine: Set[str]) -> bool:
    return any(label in mine for label in labels_of(contact.source_sheet))


def my_contacts(db: Session, user: User) -> List[VcContact]:
    """내 명단에 있는 담당자만. 대시보드·후속의 '내 담당' 기준이다."""
    mine = my_labels(db, user)
    rows = db.execute(
        select(VcContact).where(VcContact.user_id == user.id)
    ).scalars().all()
    return [c for c in rows if is_mine(c, mine)]


def ensure(db: Session, label: str, user_id: Optional[int] = None,
           assignee_name: Optional[str] = None) -> SheetOwner:
    """명단을 등록한다. 이미 있으면 담당을 **덮지 않는다**.

    시트를 다시 올렸다고 담당이 바뀌면, 남의 명단을 한 번 올린 것만으로
    담당이 넘어간다.
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
    """담당을 바꾼다(관리자). None 이면 담당 없음으로 둔다."""
    row = ensure(db, label)
    row.user_id = user_id
    db.flush()
    return row


def sheet_rows(db: Session, contacts: List[VcContact]) -> List[dict]:
    """명단 목록 + 담당 + 인원. 화면의 탭과 관리 표에 함께 쓴다."""
    mapping = owner_map(db)
    names = {
        u.id: u.name for u in db.execute(select(User)).scalars().all()
    }
    written = {
        row.label: (row.assignee_name or "")
        for row in db.execute(select(SheetOwner)).scalars().all()
    }
    total: Dict[str, int] = {}
    connected: Dict[str, int] = {}
    for c in contacts:
        for label in labels_of(c.source_sheet):
            total[label] = total.get(label, 0) + 1
            if c.connect_stage == "connected":
                connected[label] = connected.get(label, 0) + 1

    out = []
    for label in sorted(total, key=lambda k: (-connected.get(k, 0), -total[k], k)):
        uid = mapping.get(label)
        out.append({
            "key": label,
            "label": label,
            "count": total[label],
            "connected": connected.get(label, 0),
            "owner_id": uid,
            "owner": names.get(uid, "") if uid else "",
            # 시트에 적힌 담당자 이름 — 계정이 없어도 누구 것인지 알 수 있게
            "written_by": written.get(label, ""),
        })
    return out
