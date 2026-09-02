"""예약 큐 — **그룹마다 다른 딜소개를 미리 줄 세워 둔다.**

그룹마다 붙일 기업이 달라진다고 해서 생긴 자리다. 줄 하나가
**그룹 + 기업 묶음 + 문구**이고, 사람이 [시작] 을 누르면 그때 발송 목록이
만들어진다.

## 대상을 담지 않는다 — 이 파일이 지키는 것

예약 줄에는 **그룹 이름만** 있다. 받는 사람을 굳혀 두면 예약해 둔 사이에
카톡방을 나갔거나 `검토중단` 이 된 분께 그대로 나간다 — 되돌릴 수 없는 일이다.
그래서 화면에 적는 `대상 24명` 도, [시작] 이 실제로 보내는 사람도 **둘 다**
`targets()` 한 곳을 지난다. 두 벌로 적어 두면 수가 달라졌을 때 그것이 그사이
사람이 바뀐 탓인지 규칙이 어긋난 탓인지 알 수 없고, 그러면 아래 확인창이
하는 말이 통째로 거짓이 된다.

## 자동 발송은 없다

예약 시각이라는 칸을 두지 않았다. 이 앱에는 예약을 실행할 장치가 **일부러**
없다(크론도 워커도 없다). 줄만 세워 두고 누르는 것은 사람이다.
"""
from __future__ import annotations

from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import DealQueueCompany, DealQueueItem, IrCompany, SendJob, User, VcContact
from . import sheet_owner

# ── 예약 줄의 상태 ──────────────────────────────────────────────────────────
#
# **값과 한글 이름을 여기 둔다.** 판정이 여기 있는데 이름은 화면에 있으면,
# 이름이 바뀌는 날 화면과 서버가 서로 다른 말을 하게 된다 — 투자사 줄의
# `상태`(`sheet_owner.STATUS_LABELS`)를 같은 이유로 그렇게 두었다.
STATUS_WAITING = "waiting"
STATUS_STARTED = "started"
STATUS_CANCELED = "canceled"

#: `시작함` 이라고 적는다. `보냄` 이 아니다 — [시작] 은 발송 목록을 `queued` 로
#: 만들어 둘 뿐이고, 실제로 방에 들어가는 것은 각자 PC의 발송 프로그램이다.
#: 보냈다고 적어 두면 프로그램이 꺼져 있어 한 통도 안 나간 회차를 화면이
#: `보냄` 이라고 말한다. 어디까지 갔는지는 잡 화면이 이어서 말한다.
STATUS_LABELS = {
    STATUS_WAITING: "대기",
    STATUS_STARTED: "시작함",
    STATUS_CANCELED: "취소",
}

#: 그룹을 안 정해 둔 사람들의 예약 줄에 적는 말.
#:
#: **이 줄을 빼지 않는다.** 운영에서 그룹이 빈 분이 열일곱 명인데, 큐가 그룹
#: 있는 줄만 세우면 그분들은 이 화면을 통해서는 영영 아무것도 못 받는다.
#: 대신 그룹을 채우면 맞춤 기업을 붙일 수 있다는 것을 화면이 말한다.
#:
#: 같은 화면의 그룹 칩은 `sheet_owner.EMPTY_GROUP`(`(비어 있음)`)이라고 적는데,
#: **여기만 다른 말을 쓰는 것은 일부러다.** 칩은 `그룹` 이라는 이름표 밑에
#: 줄지어 서 있어서 `(비어 있음)` 이 "그룹이 비었다" 로 읽히지만, 예약 줄은
#: 홀로 서는 이름이라 거기서 `(비어 있음)` 은 무엇이 비었는지를 말해 주지
#: 않는다.
#:
#: 두 말이 어긋날 걱정은 없다 — **고르는 데 쓰는 값은 이 글자가 아니다.**
#: 양쪽 다 빈 문자열(`sheet_owner.group_of` 가 돌려주는 값)로 사람을 고르고,
#: 이 상수는 화면에 적기만 한다. 그 짝은 `tests/test_deal_queue.py` 가 지킨다.
EMPTY_GROUP_LABEL = "(그룹 없음)"


def group_label(group_name: str) -> str:
    """예약 줄의 그룹 이름. 빈 값이면 `(그룹 없음)`."""
    return (group_name or "").strip() or EMPTY_GROUP_LABEL


def targets(db: Session, user: User, group_name: str) -> List[VcContact]:
    """**지금 이 그룹에 보낼 수 있는 사람.** 화면의 수도 [시작] 도 여기를 지난다.

    `sheet_owner.recipients` 를 그대로 부른다 — 딜 제안 관리의 목록과 같은
    판정이어야 한다. 명단 밖·연결 전·`검토중단` 은 거기서 이미 빠지고,
    그래서 예약해 둔 사이에 상태가 바뀐 분은 **저절로** 빠진다.
    """
    return sheet_owner.in_group(sheet_owner.recipients(db, user), group_name)


def difference_note(shown: int, now: int, group_name: str) -> str:
    """미리보기 수와 지금 수가 **다를 때** 확인창이 할 말.

    조용히 다른 수로 보내면 안 된다. 그렇다고 수만 두 개 늘어놓으면 무엇이
    일어난 것인지 알 수 없으니, **왜 달라지는지**까지 한 줄로 적는다.

    문구를 서버에 두는 이유: 화면에도 같은 말을 적어 두면 두 벌이 되고, 둘이
    어긋나도 아무도 모른다. 확인창은 사람이 마지막으로 읽는 자리라 특히 그렇다.
    """
    moved = abs(now - shown)
    if now < shown:
        why = (f"{moved}명이 줄었습니다 — 그사이 카톡방을 나갔거나 "
               f"{sheet_owner.STATUS_LABELS[sheet_owner.STATUS_PAUSED]} 이 된 분은 빠집니다.")
    else:
        why = (f"{moved}명이 늘었습니다 — 그사이 연결이 끝났거나 "
               f"이 그룹에 들어온 분이 함께 나갑니다.")
    return (f"[{group_label(group_name)}] 예약을 걸어 둔 뒤 대상이 달라졌습니다.\n"
            f"화면에는 {shown}명 · 지금은 {now}명입니다 ({why})\n"
            f"지금 기준 {now}명에게 보냅니다. 진행할까요?")


def company_ids(item: DealQueueItem) -> List[int]:
    """예약에 붙여 둔 기업 — **적어 둔 순서 그대로.**

    순서가 곧 문구의 번호다(`1번 기업 …`). 뒤섞이면 받는 쪽이 기억하는 번호와
    어긋난다.
    """
    return [row.company_id for row in sorted(item.companies,
                                             key=lambda r: (r.position, r.company_id))]


def items_of(db: Session, user: User) -> List[DealQueueItem]:
    """이 사람의 예약 줄. **대기가 먼저**, 그 안에서는 만든 차례대로.

    할 일이 위에 있어야 한다 — 끝난 줄이 위로 올라오면 오늘 누를 것을 찾아
    아래로 내려가야 한다(`sheet_owner.blocked_stages` 가 할 일을 앞세우는 것과
    같은 이유).
    """
    rows = db.execute(
        select(DealQueueItem).where(DealQueueItem.user_id == user.id)
    ).scalars().all()
    order = {STATUS_WAITING: 0, STATUS_STARTED: 1, STATUS_CANCELED: 2}
    return sorted(rows, key=lambda r: (order.get(r.status, 9), r.id))


def rows(db: Session, user: User) -> List[dict]:
    """화면이 그리는 예약 줄들.

    `대상 N명` 은 **지금 세어 본 수**다. 저장해 둔 수가 아니다 — 저장하면
    화면이 어제의 수를 오늘의 수인 척 보여 준다. 다만 이 수는 화면을 그린
    순간의 것이라, 누를 때 또 달라질 수 있다: 그 차이는 [시작] 이 확인창으로
    말한다(`difference_note`).

    `(그룹 없음)` 줄도 **똑같이 선다.** 빼면 그룹이 빈 분들은 이 화면을 통해
    아무것도 못 받는다.
    """
    items = items_of(db, user)
    if not items:
        return []

    # 대상은 사람마다 한 번만 계산한다 — 줄마다 `recipients` 를 다시 부르면
    # 예약이 열 줄일 때 같은 질의를 열 번 돈다.
    people = sheet_owner.recipients(db, user)
    names = _company_names(db, items)
    # 같은 그룹에 대기 줄이 둘 이상이면 같은 분들께 두 번 나간다 — 막지는
    # 않지만(그룹마다 다른 기업을 다른 날 보내려고 만든 큐다) 말은 해 준다.
    waiting_per_group: dict = {}
    for it in items:
        if it.status == STATUS_WAITING:
            key = (it.group_name or "").strip()
            waiting_per_group[key] = waiting_per_group.get(key, 0) + 1

    out = []
    for it in items:
        group = (it.group_name or "").strip()
        out.append({
            "id": it.id,
            "group_name": group,
            "group_label": group_label(group),
            # 그룹을 안 정해 둔 줄인가 — 화면이 "그룹을 채우면 맞춤 기업을
            # 붙일 수 있다" 고 안내할 자리를 여기서 정한다.
            "no_group": not group,
            "title": it.title,
            "companies": [names.get(cid, f"#{cid}") for cid in company_ids(it)],
            "status": it.status,
            "status_label": STATUS_LABELS.get(it.status, it.status),
            "waiting": it.status == STATUS_WAITING,
            # 대기 줄만 지금 수를 센다. 이미 시작한 줄에 오늘의 수를 적으면
            # 그날 실제로 나간 수와 다른 수가 나란히 서서 어느 쪽이 그때의
            # 수인지 알 수 없다.
            "target_count": (len(sheet_owner.in_group(people, group))
                             if it.status == STATUS_WAITING else None),
            "job_id": it.job_id,
            # 시작한 줄이 **실제로 몇 명에게** 나갔는지. 잡이 들고 있는 수를
            # 읽는다 — 여기 또 적어 두면 두 벌이 되어 어긋난다.
            "sent_total": _job_total(db, it.job_id),
            "started_at": (it.started_at or "")[:16].replace("T", " "),
            # 같은 그룹에 대기 줄이 몇 개인지(자기 자신 포함).
            "same_group_waiting": (waiting_per_group.get(group, 0)
                                   if it.status == STATUS_WAITING else 0),
        })
    return out


def _company_names(db: Session, items: List[DealQueueItem]) -> dict:
    ids = {cid for it in items for cid in company_ids(it)}
    if not ids:
        return {}
    return {
        c.id: c.name
        for c in db.execute(
            select(IrCompany).where(IrCompany.id.in_(ids))
        ).scalars().all()
    }


def _job_total(db: Session, job_id: Optional[int]) -> Optional[int]:
    if not job_id:
        return None
    job = db.get(SendJob, job_id)
    return job.total if job else None


# ── 기업을 지울 때 ──────────────────────────────────────────────────────────
#
# 예약 줄은 기업을 **외래키로** 붙들고 있다. 그래서 기업 삭제는 셋 중 하나여야
# 하고, 어느 것인지가 사람에게 보여야 한다.
#
#   대기 중 예약   막는다. 아직 안 나간 계획이고, **취소하면 풀린다** — 할 일이
#                  분명하다. 조용히 예약에서 빼면 세 곳으로 예약해 둔 회차가
#                  말없이 두 곳이 되어 나간다.
#   시작한 예약    막는다. 다만 그때 회차(`DealBatch`)가 같은 기업으로 이미
#                  만들어져 있어서, 실제로는 회차 쪽 막이가 먼저 걸린다.
#   취소한 예약    **놓아 준다.** 접어 둔 계획이 기업을 인질로 잡으면, 지울
#                  길이 영영 없어진다(예약 줄을 지우는 단추는 없다). 가리키던
#                  기업이 사라진 뒤에는 그 줄이 보여 줄 참말도 남지 않는다.

def used_company_ids(db: Session) -> set:
    """**아직 살아 있는 예약**(대기·시작함)에 들어 있는 기업 번호들.

    기업 삭제를 막는 데 쓴다. 회차 이력이 붙은 기업을 막는 것
    (`routers/companies.py`)과는 **다른 말을 해야 한다** — 예약은 보낸 기록이
    아니라 계획이라, "이미 발송한 회차에 들어 있다" 고 하면 거짓말이다.

    막지 않고 그냥 지우면 예약 줄이 없는 기업을 가리킨 채 남아, [시작] 을
    누르는 순간 `기업 … 없음` 으로 죽는다. 그때는 왜 죽는지 화면에서 알 길이
    없다.
    """
    return {
        row.company_id
        for row in db.execute(
            select(DealQueueCompany)
            .join(DealQueueItem, DealQueueItem.id == DealQueueCompany.item_id)
            .where(DealQueueItem.status != STATUS_CANCELED)
        ).scalars().all()
    }


def release_company(db: Session, company_id: int) -> int:
    """**취소한** 예약이 붙들고 있던 기업을 놓아 준다. 지운 줄 수를 돌려준다.

    이것을 안 하면 접어 둔 계획 하나 때문에 기업이 영영 안 지워진다 — 그것도
    외래키가 막는 것이라, 화면에는 이유 없는 서버 오류로만 뜬다. 예약 줄
    자체는 남긴다: 무엇을 세워 뒀다가 접었는지가 화면에서 사라지면 안 나간
    이유를 나중에 찾을 수 없다.
    """
    rows = db.execute(
        select(DealQueueCompany)
        .join(DealQueueItem, DealQueueItem.id == DealQueueCompany.item_id)
        .where(DealQueueItem.status == STATUS_CANCELED,
               DealQueueCompany.company_id == company_id)
    ).scalars().all()
    for row in rows:
        db.delete(row)
    return len(rows)
