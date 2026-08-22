"""주간 업무 — 시트의 체크리스트를 그대로 옮긴다.

원본은 이런 표였다.

    8월
    항목 │ 세부업무                        │ 일시  │ 상태
         │ 홍보 메일 발송 - 60개            │ 8/7  │ 완료
         │ 미팅 조율 중 ○○○ 과장님          │      │ 진행중

    * 이메일 발송 — 매주 화요일, 목요일
    * 딜 소개 + 리마인드 카톡 — 매주 화요일 오전 11시

목록은 사람이 손으로 적는다. 그러니 **고칠 수 있어야** 한다 — 자동으로만 채우면
실제로 한 일과 어긋난다.

아래 규칙은 글로만 적혀 있어서, 사람이 읽고 매주 옮겨 적다 빠지는 주가 생겼다.
그 규칙을 담아 두고 **요일이 오면 그 주 목록에 저절로** 넣는다.

시스템이 이미 아는 일(후속 발송·IR 요청·회차 준비)은 여기 넣지 않는다.
같은 것을 두 곳에 적으면 반드시 어긋난다 — 화면에서 따로 보여준다.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import User, WeeklyRoutine, WeeklyTask

STATUS_LABELS = {"todo": "예정", "doing": "진행중", "done": "완료"}
STATUS_ORDER = {"doing": 0, "todo": 1, "done": 2}
WEEKDAYS = ["월", "화", "수", "목", "금", "토", "일"]

# 처음 쓰는 사람에게 넣어 주는 반복 업무. 시트 아래에 글로 적혀 있던 규칙들이다.
# 회사마다 다르므로 화면에서 고치고 지울 수 있다.
DEFAULT_ROUTINES = [
    ("메일", "홍보 메일 발송 · 발송내역 공유", "1,3"),
    ("메일", "이메일 관리 — 불필요한 메일 삭제, 거부 메일 정리", "1,3"),
    ("딜소개", "딜 소개 + 리마인드 카톡", "1"),
    ("IR", "IR Deck 자료 확인 및 업데이트", "0,2"),
]


def week_start(day: Optional[date] = None) -> date:
    """그 주 월요일. 주간 업무의 기준이다."""
    day = day or date.today()
    return day - timedelta(days=day.weekday())


def week_label(start: date) -> str:
    end = start + timedelta(days=6)
    if start.month == end.month:
        return f"{start.month}월 {start.day}~{end.day}일"
    return f"{start.month}/{start.day}~{end.month}/{end.day}"


def parse_weekdays(value: Optional[str]) -> List[int]:
    out = []
    for part in (value or "").split(","):
        part = part.strip()
        if part.isdigit() and 0 <= int(part) <= 6:
            out.append(int(part))
    return sorted(set(out))


def weekday_label(value: Optional[str]) -> str:
    days = parse_weekdays(value)
    return " · ".join(f"{WEEKDAYS[d]}" for d in days) if days else "요일 없음"


# --- 반복 업무 --------------------------------------------------------------

def ensure_routines(db: Session, user: User) -> int:
    """처음 쓰는 사람에게 기본 반복 업무를 넣어 준다(한 번만)."""
    exists = db.execute(
        select(WeeklyRoutine.id).where(WeeklyRoutine.user_id == user.id).limit(1)
    ).first()
    if exists:
        return 0
    for category, title, weekdays in DEFAULT_ROUTINES:
        db.add(WeeklyRoutine(user_id=user.id, category=category,
                             title=title, weekdays=weekdays))
    db.commit()
    return len(DEFAULT_ROUTINES)


def fill_week(db: Session, user: User, start: date) -> int:
    """그 주에 아직 없는 반복 업무를 만들어 넣는다.

    화면을 열 때 부른다 — 스케줄러 없이도 그 주를 열면 채워진다.
    같은 규칙으로 두 번 만들지 않는다(`routine_id` 로 확인).
    """
    routines = db.execute(
        select(WeeklyRoutine).where(WeeklyRoutine.user_id == user.id,
                                    WeeklyRoutine.is_active == 1)
    ).scalars().all()
    if not routines:
        return 0

    already = {
        row.routine_id for row in db.execute(
            select(WeeklyTask).where(WeeklyTask.user_id == user.id,
                                     WeeklyTask.week_start == start.isoformat(),
                                     WeeklyTask.routine_id.isnot(None))
        ).scalars().all()
    }

    made = 0
    for routine in routines:
        if routine.id in already:
            continue
        days = parse_weekdays(routine.weekdays)
        # 요일이 정해지지 않은 규칙은 그 주 월요일에 한 번 놓는다.
        due = start + timedelta(days=days[0]) if days else start
        db.add(WeeklyTask(
            user_id=user.id, week_start=start.isoformat(),
            category=routine.category, title=routine.title,
            due_date=due.isoformat(), routine_id=routine.id,
            position=100 + made,
        ))
        made += 1
    if made:
        db.commit()
    return made


# --- 조회 -------------------------------------------------------------------

def task_rows(db: Session, user: User, start: date,
              today: Optional[date] = None) -> List[dict]:
    today = today or date.today()
    rows = db.execute(
        select(WeeklyTask).where(WeeklyTask.user_id == user.id,
                                 WeeklyTask.week_start == start.isoformat())
    ).scalars().all()

    out = []
    for row in rows:
        due = _as_date(row.due_date)
        out.append({
            "id": row.id,
            "category": row.category or "",
            "title": row.title,
            "due_date": row.due_date or "",
            "due_label": f"{due.month}/{due.day}({WEEKDAYS[due.weekday()]})" if due else "",
            "status": row.status,
            "status_label": STATUS_LABELS.get(row.status, row.status),
            "note": row.note or "",
            "routine": row.routine_id is not None,
            # 날짜가 지났는데 아직 안 끝난 것
            "overdue": bool(due and due < today and row.status != "done"),
            "position": row.position,
        })
    out.sort(key=lambda r: (STATUS_ORDER.get(r["status"], 9),
                            r["due_date"] or "9999", r["position"], r["id"]))
    return out


def carry_over_candidates(db: Session, user: User, start: date) -> List[dict]:
    """지난 주에 못 끝낸 것. 이번 주로 가져올 수 있게 보여준다.

    그냥 두면 지난 주 화면에 묻혀 잊힌다.
    """
    last = (start - timedelta(days=7)).isoformat()
    rows = db.execute(
        select(WeeklyTask).where(WeeklyTask.user_id == user.id,
                                 WeeklyTask.week_start == last,
                                 WeeklyTask.status != "done")
    ).scalars().all()
    return [{"id": r.id, "category": r.category or "", "title": r.title,
             "status_label": STATUS_LABELS.get(r.status, r.status)} for r in rows]


def carry_over(db: Session, user: User, start: date) -> int:
    """지난 주 미완료를 이번 주로 옮긴다. 이력을 남기려 복사가 아니라 이동이다."""
    rows = carry_over_candidates(db, user, start)
    if not rows:
        return 0
    ids = [r["id"] for r in rows]
    for task in db.execute(
        select(WeeklyTask).where(WeeklyTask.id.in_(ids))
    ).scalars().all():
        task.week_start = start.isoformat()
        # 지난 주 날짜를 그대로 두면 계속 '지남'으로 보인다.
        task.due_date = None
    db.commit()
    return len(ids)


def summary(rows: List[dict]) -> dict:
    return {
        "total": len(rows),
        "done": sum(1 for r in rows if r["status"] == "done"),
        "doing": sum(1 for r in rows if r["status"] == "doing"),
        "todo": sum(1 for r in rows if r["status"] == "todo"),
        "overdue": sum(1 for r in rows if r["overdue"]),
    }


def _as_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None
