"""진행 단계 — 이 투자사와 지금 어디까지 왔는가.

딜소개는 한 번 보내고 끝이 아니라 **사다리**다.

    접촉 전 → 1차 딜소개 → IR 자료 요청 → IR 자료 전달 → 1차 미팅 → 2차 미팅 → 미팅 완료

지금까지 화면에는 "IR 있음 · 미팅 있음" 같은 태그만 있었다. 있다/없다만 알 수 있어서
*"IR 자료까지는 보냈는데 미팅으로 못 넘어간 곳"* 처럼 실제로 손이 필요한 구간을
골라낼 수가 없었다. 그게 이 모듈이 있는 이유다 — 사다리의 **가장 멀리 올라간 칸**을
투자사마다 하나씩 매겨서, 표에서 그 칸으로 걸러 볼 수 있게 한다.

## 근거를 여러 군데서 모으는 이유

시트에서 옮겨 온 과거 기록(`ContactActivity`)과 이 도구에서 만들어진 기록
(`SendItem` · `IrRequest` · `Meeting`)이 **같은 사다리의 서로 다른 구간**을 채운다.
과거 기록에는 'IR 요청이 왔다'까지만 남아 있고 그 뒤가 없다. 앞으로 쌓이는 기록에는
전달·미팅·결과가 다 남는다. 둘 중 하나만 보면 옮겨 오기 전 사람들은 전부
'접촉 전'으로 보인다.

## **앱으로 보낸 것**이 근거에 없었다

이 앱으로 딜소개를 보낸 담당자가 표에서 `접촉 전` 으로 남았다(메일도 같은 길이라
같았다). 근거가 위 셋뿐이라 **`SendItem`(이 앱이 실제로 보낸 건)을 아예 안 봤기**
때문이다. 지금까지 대부분 맞아 보인 것은 그 사람들에게 시트에서 옮겨 온 옛 기록이
같이 있어서지, 앱 발송을 세어서가 아니었다 — 옛 기록이 없는 사람(새로 넣는 사람은
전부 여기 든다)은 보내도 `접촉 전` 에 남았다.

무엇을 '보냈다' 로 세는지는 **이미 정해져 있다**: 실제로 나갔고(`SENT_STATUS`)
문구가 나가는 종류의 잡(`models.SEND_KINDS`)이어야 한다. 여기서 다시 적지 않고
그 값을 그대로 읽는다 — `llm_brief.sent_history` · `deal_history.scan` 과 같은
기준이다. 이 저장소가 `SEND_KINDS` 에서 이미 데인 자리다(세는 곳이 여럿이라 각자
걸러 두면 한 곳이 빠진다).

`pending`·`sending`·`failed`·`canceled` 는 **세지 않는다.** 안 나간 것을 보냈다고
세면 보낸 적 없는 사람이 `1차 딜소개` 로 서고, 그건 지금 버그의 반대 방향이라 더
나쁘다(안 보낸 사람이 명단에서 빠진다).

## 되돌아가지 않는다

거절당해도 단계는 내려가지 않는다. 단계는 *지금 상태*가 아니라 *어디까지 갔었나*이고,
거절은 `status`(활성/보류/거절) 쪽에서 따로 본다. 둘을 한 칸에 섞으면 "미팅까지 갔다가
거절된 곳"을 다시 찾을 수 없다 — 그게 제일 아까운 명단이다.
"""
from __future__ import annotations

from typing import Dict, Iterable, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (SEND_KINDS, ContactActivity, IrRequest, Meeting,
                      SendItem, SendJob)
#: 미팅 갈래의 **이름**은 여기서 정하지 않는다(`services/meeting_kind` 한 곳).
#: 그 갈래가 사다리의 **어느 칸**인지만 아래 `ACTIVITY_STAGE` 가 정한다 —
#: 사다리를 쥔 것은 이 모듈이다.
from . import meeting_kind as mk
#: 무엇을 '보냈다' 로 세는가 — **판정을 여기서 새로 적지 않는다.**
#: `deal_history` 가 이미 그 값을 들고 있고(`llm_brief.SENT_STATUS` 와 같은
#: 값·같은 이유), 그 두 곳과 이 곳이 세는 것이 갈리면 표의 단계와 이력이 서로
#: 다른 말을 한다.
from .deal_history import SENT_STATUS

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


#: **앱 발송 한 건이 올려 주는 칸.** 잡 종류(`SendJob.kind`)마다 다르다.
#:
#: 무엇을 세는지(`SENT_STATUS` · `SEND_KINDS`)는 다른 곳에서 읽어 오지만, 그
#: 한 건이 사다리의 **어느 칸**을 뜻하는지는 사다리를 쥔 이 모듈이 정한다.
#:
#:   · `deal_intro`   — 딜소개가 나갔다. 사다리의 첫 칸 그대로다. 미팅 요청·
#:     리마인드도 같은 종류로 나가는데(`manual_send.AS_SEND` — `SendJob.kind`
#:     가 후속을 따로 적지 않는다), 그것들도 "딜소개를 보낸 뒤" 의 일이라
#:     `INTRO` 밑으로 내려가지 않는다.
#:   · `ir_delivery`  — IR 자료를 보냈다 = `IR_SENT`. `IrRequest.status ==
#:     "delivered"` 도 같은 칸을 올리지만 **두 번 세는 것이 아니다**: 단계는
#:     개수가 아니라 `higher()` 로 고른 가장 먼 칸 하나라, 같은 칸을 두 번
#:     올려도 값이 그대로다. 그리고 둘은 겹치지 않는 자리가 있다 — 요청 줄
#:     없이 딜 제안 관리에서 바로 보낸 건, 요청의 기업 이름이 회차와 안 맞아
#:     닫히지 않은 건(`pipeline.close_requests_for` 는 **이름이 맞는 `open`**
#:     요청만 닫는다)은 `IrRequest` 쪽에 아무 자국도 안 남는다. 그때 근거가
#:     되는 것은 실제로 나간 발송 건뿐이다.
#:   · `sourcing_intro` — **올리지 않는다.** 딜 소싱 명단으로 나간 것이라 받는
#:     줄이 `SendItem.sourcing_contact_id`(다른 표)에 있고, 이 모듈이 세는
#:     `contact_id`(투자사 담당자)는 비어 있다(`routers/deals.py` 가 셋 중
#:     하나만 채운다). 질의에 애초에 안 걸리지만, 번호만 같고 사람은 다른 줄이
#:     행여 섞여도 엉뚱한 사람의 단계가 오르지 않게 **여기서도 막아 둔다.**
#:
#: 값이 `None` 이면 "세지만 올리지는 않는다". `SEND_KINDS` 에 종류가 늘면 이
#: 표도 함께 늘어야 한다 — 빠뜨리면 검사가 잡는다(`tests/test_deal_stage.py`).
SENT_STAGE: Dict[str, Optional[str]] = {
    "deal_intro": INTRO,
    "ir_delivery": IR_SENT,
    "sourcing_intro": None,
}


#: **시트에서 옮겨 온 기록 한 줄이 올려 주는 칸**(`ContactActivity.kind`).
#:
#: 미팅이 넷으로 갈려 있다. 예전에는 `미팅` 글자만 있으면 전부 한 값이라
#: **미팅을 청하기만 한 줄도 `1차 미팅` 으로 섰다** — 고객사가 "그분들은
#: 실제로 미팅하신 상태가 아닙니다" 라고 짚은 것이 이 자리다.
#:
#:   · `meeting_request` — 청했을 뿐 **안 만났다**. 그래서 미팅 칸이 아니라
#:     `INTRO` 다. 이 앱이 미팅 요청 카톡을 보냈을 때 올리는 칸과 **같다**
#:     (위 `SENT_STAGE` 의 `deal_intro` 설명 — 미팅 요청·리마인드도 "딜소개를
#:     보낸 뒤" 의 일이라 `INTRO` 밑으로 안 내려간다). 같은 사실을 두 길로
#:     받았는데 칸이 다르면, 시트에서 온 사람과 앱에서 보낸 사람이 같은 일을
#:     하고도 다른 단계에 선다.
#:   · `meeting_set` — 날짜가 잡혔다. `Meeting` 줄의 `planned` 와 같은 뜻이라
#:     같은 칸(`MEET_1`)이다(`_from_meeting`).
#:   · `meeting_done` — 만났다. `Meeting.status == "done"` 과 같은 칸이다.
#:   · `meeting` — **아직 안 가른 옛 줄**(`services/meeting_kind` 참고).
#:     가르기 전까지 **지금 뜻 그대로** `MEET_1` 이다. 여기서 먼저 낮추면
#:     진짜로 미팅한 사람들이 스크립트를 돌리기도 전에 화면에서 빠진다.
ACTIVITY_STAGE: Dict[str, str] = {
    "deal_intro": INTRO,
    "ir_request": IR_ASKED,
    mk.REQUEST: INTRO,
    mk.SET: MEET_1,
    mk.DONE: MEET_DONE,
    mk.LEGACY: MEET_1,
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
        key = ACTIVITY_STAGE.get(kind)
        if key:
            raise_to(contact_id, key)

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

    # ③ 이 앱으로 **실제로 보낸 건**(카톡·메일 같은 길이다 — `SendItem.channel`
    #    만 다르고 여기까지 오는 줄은 하나다).
    #
    #    거르는 두 조건은 다른 곳에서 읽어 온 그대로다 — 실제로 나갔고
    #    (`SENT_STATUS`), 문구가 나가는 종류의 잡(`SEND_KINDS`). 시험 발송·방
    #    연결 확인·스타트업 월간 발송은 `SEND_KINDS` 밖이라 저절로 빠진다.
    #
    #    소싱 명단·스타트업으로 나간 줄은 `contact_id` 가 비어 있어
    #    (`models.SendItem` — 받는 줄은 셋 중 한 칸에만 담긴다) `in_(ids)` 에
    #    애초에 안 걸린다. 종류로도 한 번 더 가른다(`SENT_STAGE`).
    #
    #    질의는 **한 번**이다. 담당자 수와 무관하게 늘 한 번이라 300명 표에서도
    #    종류별 한 번씩(이제 넷)이다.
    for contact_id, kind in db.execute(
        select(SendItem.contact_id, SendJob.kind)
        .join(SendJob, SendJob.id == SendItem.job_id)
        .where(SendItem.contact_id.in_(ids),
               SendItem.status == SENT_STATUS,
               SendJob.kind.in_(SEND_KINDS))
    ).all():
        key = SENT_STAGE.get(kind)
        if key:
            raise_to(contact_id, key)

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
