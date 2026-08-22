"""진행 단계 — 이 투자사와 지금 어디까지 왔는가.

딜소개는 한 번 보내고 끝이 아니라 **사다리**다.

    접촉 전 → 1차 딜소개 → IR 자료 요청 → IR 자료 전달 → 1차 미팅 → 2차 미팅 → 미팅 완료

지금까지 화면에는 "IR 있음 · 미팅 있음" 같은 태그만 있었다. 있다/없다만 알 수 있어서
*"IR 자료까지는 보냈는데 미팅으로 못 넘어간 곳"* 처럼 실제로 손이 필요한 구간을
골라낼 수가 없었다. 그게 이 모듈이 있는 이유다 — 사다리의 **가장 멀리 올라간 칸**을
투자사마다 하나씩 매겨서, 표에서 그 칸으로 걸러 볼 수 있게 한다.

## 근거를 두 군데서 모으는 이유

시트에서 옮겨 온 과거 기록(`ContactActivity`)과 이 도구에서 만들어진 기록
(`IrRequest` · `Meeting`)이 **같은 사다리의 서로 다른 구간**을 채운다. 과거 기록에는
'IR 요청이 왔다'까지만 남아 있고 그 뒤가 없다. 앞으로 쌓이는 기록에는 전달·미팅·결과가
다 남는다. 둘 중 하나만 보면 옮겨 오기 전 사람들은 전부 '접촉 전'으로 보인다.

## 되돌아가지 않는다

거절당해도 단계는 내려가지 않는다. 단계는 *지금 상태*가 아니라 *어디까지 갔었나*이고,
거절은 `status`(활성/보류/거절) 쪽에서 따로 본다. 둘을 한 칸에 섞으면 "미팅까지 갔다가
거절된 곳"을 다시 찾을 수 없다 — 그게 제일 아까운 명단이다.
"""
from __future__ import annotations

from typing import Dict, Iterable, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import ContactActivity, IrRequest, Meeting

# 사다리. 왼쪽이 낮고 오른쪽이 높다 — 순서가 곧 의미다.
NONE = "none"
INTRO = "intro"
IR_ASKED = "ir_asked"
IR_SENT = "ir_sent"
MEET_1 = "meet_1"
MEET_2 = "meet_2"
MEET_DONE = "meet_done"

LADDER: List[str] = [NONE, INTRO, IR_ASKED, IR_SENT, MEET_1, MEET_2, MEET_DONE]
RANK: Dict[str, int] = {key: i for i, key in enumerate(LADDER)}

LABELS: Dict[str, str] = {
    NONE: "접촉 전",
    INTRO: "1차 딜소개",
    IR_ASKED: "IR 자료 요청",
    IR_SENT: "IR 자료 전달",
    MEET_1: "1차 미팅",
    MEET_2: "2차 미팅",
    MEET_DONE: "미팅 완료",
}

# 화면 뱃지 색. 올라갈수록 진해진다 — 표를 훑을 때 색만으로 구간이 보여야 한다.
CLASSES: Dict[str, str] = {
    NONE: "muted",
    INTRO: "soft",
    IR_ASKED: "warn",
    IR_SENT: "warn",
    MEET_1: "good",
    MEET_2: "good",
    MEET_DONE: "done",
}


def label(key: str) -> str:
    return LABELS.get(key, LABELS[NONE])


def higher(a: str, b: str) -> str:
    """둘 중 더 멀리 간 쪽."""
    return a if RANK.get(a, 0) >= RANK.get(b, 0) else b


def _from_meeting(meeting: Meeting) -> str:
    if meeting.status == "done":
        return MEET_DONE
    return MEET_2 if meeting.kind == "second" else MEET_1


def of_many(db: Session, contact_ids: Iterable[int]) -> Dict[int, str]:
    """담당자별 진행 단계. **한 번에** 구한다.

    행마다 따로 물으면 300명 표에서 질의가 1,200번 나간다. 표를 그릴 때마다
    그러면 화면이 눈에 띄게 느려지므로 종류별로 한 번씩만 훑는다.
    """
    ids = [int(i) for i in contact_ids]
    if not ids:
        return {}

    out: Dict[int, str] = {cid: NONE for cid in ids}

    def raise_to(contact_id: Optional[int], key: str) -> None:
        if contact_id in out:
            out[contact_id] = higher(out[contact_id], key)

    # ① 시트에서 옮겨 온 과거 기록
    activities = db.execute(
        select(ContactActivity.contact_id, ContactActivity.kind)
        .where(ContactActivity.contact_id.in_(ids))
    ).all()
    for contact_id, kind in activities:
        if kind == "deal_intro":
            raise_to(contact_id, INTRO)
        elif kind == "ir_request":
            raise_to(contact_id, IR_ASKED)
        elif kind == "meeting":
            raise_to(contact_id, MEET_1)

    # ② 이 도구에서 쌓인 기록
    for contact_id, status in db.execute(
        select(IrRequest.contact_id, IrRequest.status)
        .where(IrRequest.contact_id.in_(ids))
    ).all():
        raise_to(contact_id, IR_SENT if status == "delivered" else IR_ASKED)

    for meeting in db.execute(
        select(Meeting).where(Meeting.contact_id.in_(ids))
    ).scalars().all():
        raise_to(meeting.contact_id, _from_meeting(meeting))

    return out


def funnel(stages: Dict[int, str]) -> List[dict]:
    """단계별 몇 명인가. 사다리 순서 그대로, 0명인 칸도 남긴다.

    빈 칸을 지우면 어디서 끊겼는지가 안 보인다 — 0이 답인 칸이 가장 중요하다.
    """
    counts: Dict[str, int] = {key: 0 for key in LADDER}
    for key in stages.values():
        counts[key] = counts.get(key, 0) + 1
    return [{"key": key, "label": LABELS[key], "count": counts[key],
             "cls": CLASSES[key]} for key in LADDER]
