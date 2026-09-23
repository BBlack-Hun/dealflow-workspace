"""마지막 일 — 이 투자사와 **가장 최근에 있었던 일 한 가지**.

## 왜 칸을 하나 더 세우나

`services/deal_stage` 의 진행 단계는 사다리의 **꼭대기**다. 어디까지 갔었나를
말하므로 내려가지 않는다(그 까닭은 그 모듈의 `되돌아가지 않는다` 절에 있고,
이 모듈은 **그 값을 한 칸도 건드리지 않는다**).

그런데 화면에서 그 하나만 보이니 이런 자리가 생겼다 — 8월에 IR 자료를
요청받고, 9월에 딜소개가 두 번 더 나간 담당자가 표에서는 계속 `IR 자료 요청`
으로 서 있다. 고객사의 말 그대로다:

    "딜소개에 있다가 IR 자료 요청에 있다가 헷갈립니다.
     … 9월 1주차 딜소개 혹은 9월 3주차 딜소개로 상태가 변경되어야 할 것 같습니다."

단계를 '가장 최근 일'로 바꾸면 그 헷갈림은 풀리지만 **미팅까지 갔다가 조용해진
명단이 통째로 사라진다**(운영 실측: 138명이 내려가고 오르는 사람은 0명,
미팅 흔적이 있는 22명 중 15명이 미팅 칸에서 빠진다). 그래서 사다리는 그대로
두고, **지금 무슨 일이 있었는지**를 말하는 칸을 따로 세운다. 둘은 서로 다른
질문에 답한다 — 어디까지 갔나(단계) · 마지막으로 무엇을 했나(이 칸).

## 세는 자리는 여기 한 곳이다

화면 표(`routers/contacts.contact_rows`)와 엑셀(`routers/data_io._contact_row`)
이 **같은 줄 하나**를 쓴다. 근거가 넷(시트 이력 · IR 요청 · 미팅 · 앱 발송)이라
두 곳에 나눠 적으면 한쪽만 고쳐지는 날 화면과 파일이 다른 날짜를 말한다.

## 무엇을 '일' 로 세는가

`deal_stage` 가 이미 근거 넷을 알고 있다. **그 표를 그대로 읽는다** —
`ACTIVITY_STAGE`(시트 이력의 갈래) · `SENT_STAGE`(앱 발송의 잡 종류). 여기서
갈래를 다시 적으면 근거가 하나 늘 때 단계는 오르는데 이 칸은 낡은 채로 남는다
(`tests/test_last_activity.py` 가 두 표의 키가 갈리면 빨개진다).

다만 **말은 사다리 칸 이름이 아니다.** 사다리는 `미팅 요청` 을 `1차 딜소개`
칸으로 친다(청했을 뿐 안 만났으므로 — `deal_stage.ACTIVITY_STAGE` 주석). 그건
'어디까지 갔나' 의 답으로는 맞지만 '마지막으로 무엇을 했나' 의 답으로는 틀리다
— 그날 있었던 일은 미팅 요청이지 딜소개가 아니다. 그래서 갈래는 그 일 그대로
두고, 부르는 말도 **그 일을 이미 부르고 있는 곳**에서 가져온다
(`meeting_kind.LABELS` · `deal_stage.LABELS` · `cadence.STAGE_LABELS`).

## 주차 이름은 새로 세지 않는다

`09/16 (9월 3주차)` 는 회차명이다 — 업무보고·발송 이력이 쓰는 그 말이고,
만드는 곳은 `cadence.batch_title` 하나뿐이다(주차 규칙은 그 아래
`sheet_import.week_of_month` 한 곳, **1~7일이 1주차**). 여기서 다시 세면 같은
날이 화면마다 3주차·4주차로 갈린다 — `services/weekly` 와 `services/report` 가
같은 까닭으로 그 하나를 부른다.

**저장된 회차명(`DealBatch.title`)을 쓰지 않는 이유.** 그쪽이 더 정확해 보이지만
셋이 걸린다. ① 값이 있는 줄이 소수다 — 운영에서 마지막 일이 있는 504명 중
497명은 시트에서 옮겨 온 이력이라 회차 행 자체가 없다. 섞어 쓰면 같은 날짜가
줄마다 두 꼴로 보인다. ② 정규 발송이 아닌 회차는 주차 대신 무엇을 보내는지가
들어간다(`09/10 (미팅 요청)` · `09/18 (IR 자료 전달)` — `cadence.
default_batch_title` 의 `label`). ③ 회차명의 날짜와 **실제로 나간 날**이 어긋난
줄이 운영에 있다(회차명은 `09/16 (9월 3주차)` 인데 9/3·9/9 에 나간 22건).
이 칸이 말하는 것은 *그 일이 있었던 날*이라, 그 자리에 다른 날짜를 적으면
지금 고치는 바로 그 버그 — 화면이 낡은 값을 보여주는 것 — 를 다시 만든다.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Dict, Iterable, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import SEND_KINDS, ContactActivity, IrRequest, Meeting, SendItem, SendJob
from . import cadence, deal_stage
from . import meeting_kind as mk
from .deal_history import SENT_STATUS

# ── 갈래 ────────────────────────────────────────────────────────────────────
#
# 사다리 칸이 아니라 **그날 있었던 일** 그대로다(모듈 설명 참고).
DEAL = "deal"
IR_ASKED = "ir_asked"
IR_SENT = "ir_sent"
MEET_REQUEST = mk.REQUEST
MEET_SET = mk.SET
MEET_DONE = mk.DONE
MEET_LEGACY = mk.LEGACY

#: 부르는 말. **여기서 짓지 않는다** — 이 일들을 이미 부르고 있는 곳에서 읽는다.
#: 말이 바뀌면 그 한 곳만 고치면 되고, 표·엑셀·다른 화면이 같이 따라간다.
LABELS: Dict[str, str] = {
    DEAL: cadence.STAGE_LABELS[cadence.STAGE_DAY1],          # 딜소개
    IR_ASKED: deal_stage.LABELS[deal_stage.IR_ASKED],        # IR 자료 요청
    IR_SENT: deal_stage.LABELS[deal_stage.IR_SENT],          # IR 자료 전달
    MEET_REQUEST: mk.LABELS[mk.REQUEST],                     # 미팅 요청
    MEET_SET: mk.LABELS[mk.SET],                             # 미팅 확정
    MEET_DONE: mk.LABELS[mk.DONE],                           # 미팅 완료
    MEET_LEGACY: mk.LABELS[mk.LEGACY],                       # 미팅(안 가름)
}

#: **같은 날에 두 가지 일이 있었을 때** 무엇을 적을지. 멀리 간 쪽이다.
#:
#: 사다리가 아니다 — 보여 줄 것을 하나 고르는 순서일 뿐이고, 여기서 무엇을
#: 고르든 `deal_stage` 의 단계는 움직이지 않는다. 그래도 순서를 못 박아 두는
#: 것은, 안 그러면 같은 자료에서 화면을 두 번 그릴 때 다른 말이 나올 수 있어서다.
ORDER: Tuple[str, ...] = (DEAL, MEET_REQUEST, IR_ASKED, IR_SENT,
                          MEET_LEGACY, MEET_SET, MEET_DONE)
_RANK: Dict[str, int] = {key: i for i, key in enumerate(ORDER)}

#: 시트에서 옮겨 온 이력 한 줄(`ContactActivity.kind`) → 갈래.
#:
#: **키는 `deal_stage.ACTIVITY_STAGE` 와 같아야 한다.** 근거가 하나 늘 때
#: 단계만 오르고 이 칸은 낡은 채 남는 것을 막는다(검사가 두 표를 대조한다).
ACTIVITY_KIND: Dict[str, str] = {
    "deal_intro": DEAL,
    "ir_request": IR_ASKED,
    mk.REQUEST: MEET_REQUEST,
    mk.SET: MEET_SET,
    mk.DONE: MEET_DONE,
    mk.LEGACY: MEET_LEGACY,
    # `ir_delivery` 는 사다리 표에 없다 — [자료 보내기]를 누르면 `IrRequest.
    # delivered_at` 이 같은 사실을 들고 있어서 단계는 그쪽으로 오른다. 여기서는
    # 날짜가 필요하므로 이 줄도 읽는다(요청 줄 없이 보낸 건은 이쪽에만 남는다).
    "ir_delivery": IR_SENT,
}

#: 앱이 실제로 보낸 건(`SendJob.kind`) → 갈래.
#: 키는 `deal_stage.SENT_STAGE` 와 같다. 값이 `None` 이면 세지 않는다.
SENT_KIND: Dict[str, Optional[str]] = {
    "deal_intro": DEAL,
    "ir_delivery": IR_SENT,
    "sourcing_intro": None,
}


@dataclass(frozen=True)
class LastActivity:
    """그 담당자에게 **마지막으로** 있었던 일 하나."""

    day: str                     # YYYY-MM-DD
    kind: str

    @property
    def label(self) -> str:
        """`딜소개` · `IR 자료 요청` — 무엇을 했나."""
        return LABELS.get(self.kind, "")

    @property
    def title(self) -> str:
        """`09/16 (9월 3주차)` — 회차명. **만드는 곳은 `cadence` 하나다.**"""
        return cadence.batch_title(date.fromisoformat(self.day))

    @property
    def text(self) -> str:
        """`09/16 (9월 3주차) 딜소개` — 한 줄로 적을 때.

        고객사가 쓰는 말이 `9월 3주차 딜소개` 다. 날짜가 앞에 오는 것은
        회차명의 규칙이고(`cadence.batch_title`), 이 칸도 결국 "언제" 를
        찾는 자리라 그대로 둔다.
        """
        return f"{self.title} {self.label}".strip()


def _day(value: Optional[str]) -> Optional[str]:
    return value[:10] if value else None


def _activity_day(act: ContactActivity) -> Optional[str]:
    """활동의 대표 날짜. 날짜가 없으면 그 달 1일로 근사한다.

    `routers/contacts._activity_date` 와 같은 근사다 — 같은 줄을 두 곳에서
    읽으므로 다르게 근사하면 `마지막 딜소개` 칸과 이 칸이 다른 날을 말한다.
    """
    if act.happened_at:
        return act.happened_at[:10]
    if act.month:
        return f"{act.month[:7]}-01"
    return None


def of_many(db: Session, contact_ids: Iterable[int]) -> Dict[int, LastActivity]:
    """담당자별 마지막 일. **한 번에** 구한다(값이 없는 사람은 키가 없다).

    행마다 물으면 800명 표에서 질의가 수천 번 나간다. `deal_stage.of_many` 와
    같은 이유·같은 모양으로 종류마다 한 번씩만 훑는다.
    """
    ids = [int(i) for i in contact_ids]
    if not ids:
        return {}

    out: Dict[int, LastActivity] = {}

    def mark(contact_id: Optional[int], day: Optional[str], kind: Optional[str]) -> None:
        if contact_id is None or not day or not kind:
            return
        have = out.get(contact_id)
        if have is None or (day, _RANK.get(kind, 0)) > (have.day, _RANK.get(have.kind, 0)):
            out[contact_id] = LastActivity(day=day, kind=kind)

    # ① 시트에서 옮겨 온 과거 기록
    for act in db.execute(
        select(ContactActivity).where(ContactActivity.contact_id.in_(ids))
    ).scalars().all():
        mark(act.contact_id, _activity_day(act), ACTIVITY_KIND.get(act.kind))

    # ② 이 도구에서 쌓인 기록 — 요청받은 날과 보낸 날이 **따로** 있다.
    for contact_id, requested_at, delivered_at in db.execute(
        select(IrRequest.contact_id, IrRequest.requested_at, IrRequest.delivered_at)
        .where(IrRequest.contact_id.in_(ids))
    ).all():
        mark(contact_id, _day(requested_at), IR_ASKED)
        mark(contact_id, _day(delivered_at), IR_SENT)

    # 미팅도 잡힌 날과 만난 날이 따로다. **만난 줄만 `미팅 완료`** 다 —
    # 청하거나 잡아 둔 것을 만났다고 적으면, 고객사가 짚었던 그 거짓말이
    # 이 칸에서 다시 난다(`services/meeting_kind`).
    for contact_id, scheduled_at, done_at, status in db.execute(
        select(Meeting.contact_id, Meeting.scheduled_at, Meeting.done_at, Meeting.status)
        .where(Meeting.contact_id.in_(ids))
    ).all():
        mark(contact_id, _day(scheduled_at),
             MEET_DONE if status == "done" else MEET_SET)
        mark(contact_id, _day(done_at), MEET_DONE)

    # ③ 이 앱으로 **실제로 보낸 건**. 거르는 두 조건은 `deal_stage` 와 같은
    #    값을 같은 곳에서 읽는다 — 실제로 나갔고(`SENT_STATUS`), 문구가 나가는
    #    종류의 잡(`SEND_KINDS`). 한쪽만 세면 단계와 이 칸이 다른 말을 한다.
    for contact_id, kind, sent_at in db.execute(
        select(SendItem.contact_id, SendJob.kind, SendItem.sent_at)
        .join(SendJob, SendJob.id == SendItem.job_id)
        .where(SendItem.contact_id.in_(ids),
               SendItem.status == SENT_STATUS,
               SendJob.kind.in_(SEND_KINDS))
    ).all():
        mark(contact_id, _day(sent_at), SENT_KIND.get(kind))

    return out


def missing_kinds() -> List[str]:
    """`deal_stage` 는 아는데 이 모듈이 모르는 근거. **있으면 안 된다.**

    검사가 부른다(`tests/test_last_activity.py`). 여기 뭔가 담기면 단계는
    오르는데 `마지막 일` 칸만 낡은 값에 머무는 줄이 생긴다는 뜻이다.
    """
    gaps = [k for k in deal_stage.ACTIVITY_STAGE if k not in ACTIVITY_KIND]
    gaps += [k for k in deal_stage.SENT_STAGE if k not in SENT_KIND]
    return gaps
