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
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..models import User, WeeklyRoutine, WeeklyRoutineRun, WeeklyTask

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


def parse_nth_weeks(value: Optional[str]) -> List[int]:
    """`"1,3"` → `[1, 3]`. 그 달의 몇째 주에 도는가.

    **`ScheduleRule.nth_weeks` 와 같은 모양이다**(회차일이 "매월 첫째·셋째
    수요일"). 같은 뜻에 다른 모양을 하나 더 만들 이유가 없다.

    **비어 있으면 빈 목록이고, 그 뜻은 '매주'다.** 이 칸이 생기기 전의 규칙이
    전부 그 상태라, 여기서 기본값을 지어내면 매주 나가던 일이 말없이 격주가
    된다.

    1~5 밖의 값은 버린다 — 한 달은 1~7일부터 29~31일까지 다섯 토막이다
    (`week_of_month`).
    """
    out = []
    for part in (value or "").split(","):
        part = part.strip()
        if part.isdigit() and 1 <= int(part) <= 5:
            out.append(int(part))
    return sorted(set(out))


def nth_label(value: Optional[str]) -> str:
    weeks = parse_nth_weeks(value)
    return "·".join(str(n) for n in weeks) + "주차" if weeks else "매주"


def week_of_month(day: date) -> int:
    """그 날이 그 달의 몇째 주인가. **1~7일이 1주차.**

    **규칙은 저장소에 하나뿐이다**(`sheet_import.week_of_month`) — 시트 머리글의
    "첫째주 수요일" 표기이자 회차일이 세는 방식이다. 여기서 따로 세면 같은 날이
    화면마다 3주차·4주차로 갈린다. 실제로 갈린 적이 있어 `report.py` 도 이렇게
    그 하나를 부른다.
    """
    from .sheet_import import week_of_month as by_day

    return by_day(day.isoformat()) or 1


def routine_due(start: date, routine: WeeklyRoutine) -> Optional[date]:
    """그 주에 이 반복 업무가 놓일 날. **그 주에 돌지 않으면 None.**

    요일이 정해지지 않은 규칙은 그 주 월요일에 한 번 놓는다.

    주차는 **놓일 날**로 본다. 그 줄이 실제로 서는 날이 그 날이고, 사람이 표에서
    보는 날짜도 그것이다. 이러면 `1,3` 은 "매월 첫째·셋째 <그 요일>" 과 정확히
    같은 뜻이 된다 — 그 달 n번째 <요일>은 늘 n주차에 든다(회차일이 쓰는 셈법과
    같다, `services/cadence.py`). 달이 걸친 주도 저절로 풀린다: 8/31(월)~9/6 주의
    월요일은 8월의 5주차이므로 `1,3` 규칙은 그 주를 건너뛰고, 9/7(월)부터 다시
    1주차로 선다.
    """
    days = parse_weekdays(routine.weekdays)
    due = start + timedelta(days=days[0]) if days else start
    weeks = parse_nth_weeks(routine.nth_weeks)
    if weeks and week_of_month(due) not in weeks:
        return None
    return due


# --- 반복 업무 --------------------------------------------------------------

def active_routines(db: Session, user: User) -> List[WeeklyRoutine]:
    """아직 도는 반복 업무. **화면도 이 목록을 그린다.**

    예전에는 화면(`todo_page`)이 제 손으로 `user_id` 만 걸러 뽑고, 매주 채우는
    쪽(`fill_week`)만 `is_active` 를 봤다. 지금은 지우기가 이 칸을 내리므로,
    목록이 둘이면 **지운 규칙이 표에는 그대로 서 있고 새 항목만 안 생기는**
    상태가 된다. 판정은 여기 하나뿐이어야 한다.
    """
    return list(db.execute(
        select(WeeklyRoutine).where(WeeklyRoutine.user_id == user.id,
                                    WeeklyRoutine.is_active == 1)
        .order_by(WeeklyRoutine.id)
    ).scalars().all())


def ensure_routines(db: Session, user: User) -> int:
    """처음 쓰는 사람에게 기본 반복 업무를 넣어 준다(한 번만).

    **'한 번만' 은 지운 것까지 세어서 판정한다.** 화면을 열 때마다 부르는
    자리라(`todo_page`), 기준이 "지금 규칙이 하나도 없는가" 이면 우리 팀이
    하지 않는 기본 규칙을 지운 사람에게 다음 새로고침 때 그대로 되살아난다 —
    실제로 넷을 다 지우고 화면을 다시 열면 넷이 새 번호로 다시 서 있었다.
    지우기는 `is_active=0` 으로 남으므로(`delete_routine`) 그 흔적이 여기서
    "이미 넣어 준 적 있다"는 표시가 된다.
    """
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


def delete_routine(db: Session, routine: WeeklyRoutine) -> None:
    """반복 업무 규칙을 내린다 — 다음 주부터 새 항목이 생기지 않는다.

    **줄을 지우지 않고 `is_active` 를 내린다.** 두 가지가 여기 걸려 있었다.

    1) `weekly_tasks.routine_id` 가 이 표를 가리키는 외래키이고 SQLite 는
       `PRAGMA foreign_keys=ON` 으로 돈다(`app/db.py`). 딸린 항목이 하나라도
       있으면 삭제가 `FOREIGN KEY constraint failed` 로 튕겼고 화면에는 500 만
       떴다. 반복 업무를 만들면 `/todo` 로 돌아오면서 `fill_week` 가 곧바로 그
       주 항목을 하나 만들기 때문에, **만들자마자 지르는 [삭제]도 반드시**
       500 이었다.
    2) 줄이 통째로 사라지면 `ensure_routines` 가 "이 사람은 처음 쓰는구나" 로
       읽고 기본 규칙 넷을 다시 넣었다 — 지운 것이 새로고침 한 번에 되살아났다.

    내려 두면 둘 다 풀린다. 이미 만들어진 항목은 자기를 만든 규칙을 계속
    가리킨 채 그대로 남고(지우기 창이 약속하는 그대로), 화면의 표는
    `active_routines` 가 그리므로 그 줄만 사라진다.

    **이미 만들어진 항목은 그대로 둔다.** 규칙을 내리면서 그 줄까지 걷어가는
    길도 있었지만, 그 줄에는 이미 사람이 손댄 것이 얹혀 있다 — 상태를 `완료`
    로 바꿔 놓았거나 메모를 적어 두었을 수 있고, 그것은 그 주에 실제로 한
    일의 기록이다. 규칙 하나를 내렸다고 지난 기록을 말없이 걷어가는 것이 더
    나쁘다. 남은 줄이 필요 없으면 **주간 업무 표에서 지우면 되고, 이제 그
    지우기가 붙든다**(`fill_week` 머리말). 사람이 요청한 것도 그것이었다 —
    "주간업무쪽에서는 지울 수 있게".
    """
    routine.is_active = 0
    db.commit()


def _claim(db: Session, user: User, start: date, routine: WeeklyRoutine) -> bool:
    """이 주 이 규칙 몫을 내가 맡는다. 이미 맡은 요청이 있으면 False.

    유일 색인이 판정한다 — 세어 보고 넣으면 동시에 들어온 두 요청이 둘 다
    "없네" 를 보고 둘 다 넣는다. 저장점(SAVEPOINT) 안에서 넣는 것은, 실패했을
    때 **부르는 쪽이 하던 일까지 되돌리지 않기** 위해서다
    (`services/monthly_columns.py` 의 `_claim` 과 같은 방식).
    """
    try:
        with db.begin_nested():
            db.add(WeeklyRoutineRun(user_id=user.id,
                                    week_start=start.isoformat(),
                                    routine_id=routine.id))
    except IntegrityError:
        return False
    return True


def fill_week(db: Session, user: User, start: date,
              today: Optional[date] = None) -> int:
    """그 주에 아직 안 만든 반복 업무를 만들어 넣는다.

    화면을 열 때 부른다 — 스케줄러 없이도 그 주를 열면 채워진다.

    **줄이 아니라 만들었다는 사실을 본다**(`WeeklyRoutineRun`)
    ------------------------------------------------------------
    예전에는 "이 규칙 줄이 이번 주에 있나" 를 **지금 남아 있는
    `WeeklyTask.routine_id`** 로 봤다. 그래서 사람이 그 줄을 지우면 자취까지
    사라져 없는 것이 되고, `/todo` 로 돌아온 그 화면이 곧바로 "없으니 만들자"
    를 다시 돌렸다 — **지운 줄이 그 자리에 다시 서 있었다.** 지운 사람 눈에는
    지워지지 않는 줄이다.

    `MonthlyColumnRun`(0041) 이 같은 문제를 같은 방식으로 풀어 두었다. 지워도
    남는 표시를 보므로 되살아나지 않고, 유일 색인 덕에 화면 두 개를 같은 순간에
    열어도 한 주에 두 줄로 앉지 않는다.

    **이미 끝난 주는 채우지 않는다.** 예전에는 [← 지난 주] 를 누르기만 해도
    그 주에 반복 업무가 새로 생겼다. 하지도 않았고 시킨 적도 없는 일이 날짜가
    지난 채로 나타나서 그 자리에서 '지남' 이 되고, 이번 주 화면에는
    "지난 주에 못 끝낸 일이 5건 있습니다" 라는 안내까지 떴다 — 지난 주를
    한 번 들여다본 것이 없던 일을 만들어 낸 것이다. 지난 주 화면은 **그때
    실제로 적혀 있던 것**만 보여야 한다.
    """
    today = today or date.today()
    if start < week_start(today):
        return 0
    routines = active_routines(db, user)
    if not routines:
        return 0

    already = set(db.execute(
        select(WeeklyRoutineRun.routine_id).where(
            WeeklyRoutineRun.user_id == user.id,
            WeeklyRoutineRun.week_start == start.isoformat())
    ).scalars().all())

    made = 0
    for routine in routines:
        if routine.id in already:
            continue
        due = routine_due(start, routine)
        if due is None:
            # 주차가 맞지 않는 주다(격주 규칙의 2·4주차). **표시를 남기지
            # 않는다** — 만든 적이 없으니 적을 사실이 없고, 다음에 열 때 같은
            # 답이 다시 나온다.
            continue
        if not _claim(db, user, start, routine):
            continue        # 다른 요청이 먼저 맡았다
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
            # 상태로 정렬할 때 쓰는 값. **글자순이 아니다** — `완료`·`예정`·
            # `진행중` 을 가나다로 세우면 다 한 일이 맨 위에 온다. 아래에서
            # 줄을 세우는 차례와 **같은 `STATUS_ORDER`** 를 화면에도 그대로
            # 넘긴다(화면이 제 손으로 다시 매기면 두 벌이 되어 어긋난다).
            "status_order": STATUS_ORDER.get(row.status, 9),
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

    **이번 주에 이미 같은 규칙의 줄이 서 있으면 빼고 센다.** 반복 업무는
    이번 주에 제 손으로 다시 생기는데(`fill_week`), 지난 주 것까지 끌어오면
    같은 규칙이 한 주에 두 줄로 앉는다 — [이번 주로 가져오기] 를 한 번 누르면
    반복 업무가 전부 두 벌이 됐다. 규칙이 내려간 뒤라 이번 주에 다시 생기지
    않는 줄은 그대로 가져온다(빠뜨리면 갈 곳이 없다).

    안내 문구의 건수와 실제로 옮겨지는 수가 **같은 함수**에서 나온다 — 둘로
    나누면 "3건 있습니다" 를 눌렀는데 하나만 옮겨지는 자리가 된다.
    """
    last = (start - timedelta(days=7)).isoformat()
    rows = db.execute(
        select(WeeklyTask).where(WeeklyTask.user_id == user.id,
                                 WeeklyTask.week_start == last,
                                 WeeklyTask.status != "done")
    ).scalars().all()
    here = set(db.execute(
        select(WeeklyTask.routine_id).where(
            WeeklyTask.user_id == user.id,
            WeeklyTask.week_start == start.isoformat(),
            WeeklyTask.routine_id.isnot(None))
    ).scalars().all())
    return [{"id": r.id, "category": r.category or "", "title": r.title,
             "status_label": STATUS_LABELS.get(r.status, r.status)}
            for r in rows if r.routine_id not in here]


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
