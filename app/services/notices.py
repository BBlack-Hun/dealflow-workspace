"""공지 — **이번에 무엇이 바뀌었는지**를 팀이 지나는 자리에 한 번 띄운다.

무엇을 푸는가
-------------
화면을 고쳐 놓아도 **팀이 모르면 없는 것과 같다.** 지금까지는 고친 사람이
카톡방에 따로 적었고, 그 방을 안 보는 사람에게는 닿지 않았다. 닿아야 하는
자리는 그 사람이 **반드시 지나는 곳** — 로그인한 뒤 열리는 화면이다.

그래서 공지는 화면 하나에 사는 것이 아니라 **밑틀**(`base.html`)에 선다.
화면마다 심으면 새 화면이 하나 생겼을 때 그 화면만 조용히 아무 말이 없다 —
비밀번호 변경 알림(`ui.PASSWORD_CHANGED`)을 도착지가 아니라 밑틀에 둔 것과
같은 자리, 같은 이유다.

왜 `수정 로그` 를 띄우지 않는가
-------------------------------
이 저장소에는 **누가 무엇을 고쳤는지**가 이미 줄줄이 남는다(`EditLog`).
그것을 그대로 띄우는 길도 있었지만, 셋이 걸린다.

* **양.** 세션 이벤트가 flush 마다 남기므로 시트 한 번 올리면 수백 줄이다.
  그 표 자신의 설명이 `남기면 하루에 수백 줄이 쌓여 아무도 안 본다` 다
  (`services/edit_log.py`). 띄우면 더 안 본다.
* **누구의 것인가.** 거기 실린 것은 사람 이름·기업 이름이다. 전원의 화면에
  띄우면 공지가 아니라 **남의 근무 기록**이 된다 — 그 화면을 관리자만 보게
  해 둔 이유가 그것이다(`routers/dashboard.edit_log_page`).
* **사람의 말이 아니다.** `connect_stage: 연결 전 → 연결됨` 은 기계의 말이다.
  팀이 읽어야 하는 것은 `미팅 종류 칸이 생겼습니다` 이고, 그 번역은 사람이
  해야 한다.

그래서 **관리자가 손으로 적는다.** 적는 자리는 팀 현황(`/team`)이다.

한 번 본 것은 다시 안 뜬다
--------------------------
본 사람은 `notice_reads` 에 한 줄로 남고, 그 줄이 있으면 다시 안 뜬다.
**띄운 것만으로는 안 남는다** — [확인] 을 눌러야 남는다. 스쳐 지나간 것을
읽은 것으로 세면 그 공지는 아무도 안 읽은 채로 사라진다.

확인 단추는 **그때 화면에 실제로 떠 있던 번호만** 들고 간다(숨은 칸).
`지금 켜져 있는 것 전부를 읽음으로` 로 만들면, 화면을 열어 둔 사이에 관리자가
올린 공지가 **뜨지도 않고** 읽음이 된다.
"""
from __future__ import annotations

from typing import List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Notice, NoticeRead, User

#: 제목·본문 길이 상한. 화면이 감당할 수 있는 만큼만 받는다 — 밑틀에 서는
#: 판이라 여기가 길어지면 **모든 화면**이 그만큼 아래로 밀린다.
TITLE_MAX = 80
BODY_MAX = 2000

#: 관리자 화면의 공지 목록에 몇 개까지 보일까. 내린 것도 남겨 두므로
#: (`models.Notice` — 지우지 않는다) 목록에는 상한이 필요하다.
BOARD_LIMIT = 20


def _when(row: Notice) -> str:
    """`2026-09-21T14:00:00+09:00` → `2026-09-21 14:00`. 화면이 읽는 모양."""
    return (row.created_at or "")[:16].replace("T", " ")


def unread(db: Session, user: User) -> List[dict]:
    """이 사람이 **아직 확인하지 않은** 공지 — 올라온 차례대로.

    옛것이 위에 온다. 공지는 대개 "무엇이 바뀌었다" 의 연속이라, 밀린 것이
    둘이면 일어난 차례로 읽는 편이 말이 된다.
    """
    seen = select(NoticeRead.notice_id).where(NoticeRead.user_id == user.id)
    rows = db.execute(
        select(Notice, User.name)
        .join(User, User.id == Notice.author_user_id)
        .where(Notice.is_active == 1, Notice.id.notin_(seen))
        .order_by(Notice.id)
    ).all()
    return [{"id": row.id, "title": row.title, "body": row.body or "",
             "when": _when(row), "author": name}
            for row, name in rows]


def mark_seen(db: Session, user: User, ids: List[int]) -> int:
    """이 사람이 이 공지들을 확인했다고 적는다. 몇 줄이 새로 섰는지 돌려준다.

    **이미 있는 줄은 다시 넣지 않는다.** 유일 색인이 막아 주기는 하지만,
    막히는 것에 기대면 두 번 누른 사람에게 500 이 뜬다(뒤로가기 한 번이면
    일어나는 일이다).
    """
    if not ids:
        return 0
    live = set(db.execute(
        select(Notice.id).where(Notice.id.in_(ids), Notice.is_active == 1)
    ).scalars().all())
    already = set(db.execute(
        select(NoticeRead.notice_id)
        .where(NoticeRead.user_id == user.id, NoticeRead.notice_id.in_(live))
    ).scalars().all())
    added = 0
    for notice_id in sorted(live - already):
        db.add(NoticeRead(notice_id=notice_id, user_id=user.id))
        added += 1
    if added:
        db.commit()
    return added


def publish(db: Session, author: User, title: str, body: str) -> Optional[Notice]:
    """공지 한 장을 올린다. 제목이 비어 있으면 아무 일도 하지 않는다.

    제목이 없는 공지를 세우면 밑틀에 **빈 판**이 떠서 모든 화면이 아래로
    밀린다 — 올린 사람은 무엇이 잘못됐는지 알 길이 없다.
    """
    title = (title or "").strip()[:TITLE_MAX]
    if not title:
        return None
    row = Notice(title=title, body=(body or "").strip()[:BODY_MAX],
                 author_user_id=author.id, is_active=1)
    db.add(row)
    db.commit()
    return row


def turn_off(db: Session, notice_id: int) -> bool:
    """내린다 — 그 순간 아무에게도 안 뜬다. **줄은 지우지 않는다.**

    지우면 누가 무엇을 언제 알렸는지가 통째로 사라진다. 계정을 지우지 않고
    정지시키는 것과 같은 판단이다(`User.is_active`).
    """
    row = db.get(Notice, notice_id)
    if row is None or not row.is_active:
        return False
    row.is_active = 0
    db.commit()
    return True


def turn_on(db: Session, notice_id: int) -> bool:
    """내린 것을 다시 올린다.

    **이미 확인한 사람에게는 다시 안 뜬다** — `notice_reads` 줄이 그대로
    남아 있기 때문이다. 잘못 내린 것을 되돌리는 길이지, 같은 공지를 한 번 더
    읽히는 길이 아니다(그럴 때는 새로 적는 것이 맞다).
    """
    row = db.get(Notice, notice_id)
    if row is None or row.is_active:
        return False
    row.is_active = 1
    db.commit()
    return True


def board(db: Session) -> List[dict]:
    """관리자 화면의 공지 목록 — 최신 것이 위에.

    **몇 명이 확인했나**를 같이 센다. 올린 사람이 알고 싶은 것은 "떴나" 가
    아니라 "읽혔나" 이고, 그 숫자가 없으면 다시 알릴지 말지를 정할 수 없다.
    세는 모수는 **살아 있는 계정**이다 — 정지된 계정은 로그인하지 않으므로
    분모에 두면 영영 안 차는 숫자가 된다.
    """
    counts = dict(db.execute(
        select(NoticeRead.notice_id, func.count(NoticeRead.id))
        .group_by(NoticeRead.notice_id)
    ).all())
    people = db.execute(
        select(func.count(User.id)).where(User.is_active == 1)
    ).scalar() or 0
    rows = db.execute(
        select(Notice, User.name)
        .join(User, User.id == Notice.author_user_id)
        .order_by(Notice.id.desc())
        .limit(BOARD_LIMIT)
    ).all()
    return [{"id": row.id, "title": row.title, "body": row.body or "",
             "when": _when(row), "author": name,
             "active": bool(row.is_active),
             "seen": counts.get(row.id, 0), "people": people}
            for row, name in rows]
