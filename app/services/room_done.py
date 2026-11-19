"""방 찾기 · 확인 회차의 **줄마다 결과**와 **끝났을 때 한 번 띄우는 알림창** (11/13).

사용자(11/13): *"IR 기업 현황에서 방 찾기 확인을 했을 때 투자사 방 찾기처럼 별도의
체크하는 화면이 있었으면 좋겠음. 그리고 방 찾기 완료 시 alert"*.

진행 화면(`progress.js`)이 2초마다 묻는 자리(`routers/jobs.job_status`)에 싣는다.
**방 확인 회차(`verify_room`)에만** — 발송 회차에는 `None` 이라 화면이 아무것도 안
띄운다. 언제 띄우나(열어 둔 동안 진행 중 → 끝남으로 바뀔 때 한 번)는 화면이 정하고,
셈과 글은 여기서 만든다(예약 문장 · 안전장치 문장과 같은 나눔).

## 갈래 셋

  · **회사명으로 찾는 줄** — IR 기업 줄([카톡방 찾기·확인] · 월간 발송 맞추기)과
    스타트업 명단 줄([방 매칭]의 [카톡방 찾기·확인] — `ROOM_SEARCH_TOPIC`). 찾은 제목은
    후보로만 담기므로 진행 화면의 `확인됨`(건이 `sent`)은 「후보 하나를 찾았다」였다 —
    고르기 전인데 확인된 것처럼 읽혔다. 줄의 **지금** 상태로 다시 적는다:
    확인됨 · 찾음 · 여럿 · 못 찾음(`room_match.find_state` — 맞추기 화면과 같은 함수).
  · **딜 소싱 [방 후보 찾기]** — 그 화면의 알림과 같은 셈(`sourcing_rooms.search_summary`).
  · **투자사 [방 연결 확인]** — 진행 화면 숫자와 같은 말(확인됨 · 불일치).

## 확인 못 함 (0.11.16)

발송기가 그 PC 카톡의 **검색 결과를 못 읽은** 건(`services/room_unchecked.py`)은 어느
갈래든 `못 찾음` · `불일치` 가 아니라 **확인 못 함**으로 적고 따로 센다 — 방이 없다는
뜻이 아니고, 그 PC 카톡을 봐야 하는 건이다.
"""
from __future__ import annotations

from typing import Dict, Optional

from sqlalchemy.orm import Session

from ..models import ROOM_SEARCH_TOPIC, SendItem, SendJob
from . import room_match, room_unchecked, sourcing_rooms

#: 끝난 회차 — 화면이 따라가기를 멈추고 알림창을 띄운다.
ENDED = ("done", "done_with_errors", "canceled")
#: 발송기가 아직 안 본 건(`pending` · `sending`)은 결과가 없다.
_SEEN = ("sent", "failed")


def _row(job: SendJob, item: SendItem):
    """회사명으로 찾는 줄이면 그 줄 — IR 기업 줄 · 스타트업 명단 줄. 아니면 `None`."""
    if item.ir_company is not None:
        return item.ir_company
    if job.topic == ROOM_SEARCH_TOPIC and item.contact is not None:
        return item.contact
    return None


def _unchecked(item: SendItem) -> bool:
    """발송기가 검색 결과를 못 읽어 **확인을 못 한** 건인가."""
    return item.status == "failed" and room_unchecked.is_note(item.error)


def item_results(db: Session, job: SendJob) -> Dict[int, str]:
    """`{건 id: 결과 말}` — 진행 화면의 상태 칸이 `확인됨` · `불일치` 대신 적는 말.

    회사명으로 찾는 줄 중 발송기가 **본** 건만(대기 · 찾는 중 · 취소는 그대로 둔다).
    확인을 못 한 건(`room_unchecked`)은 어느 갈래든 `확인 못 함` 으로 적는다.
    """
    from ..routers.agent_api import VERIFY_KIND

    if job.kind != VERIFY_KIND:
        return {}
    known = None
    out: Dict[int, str] = {}
    for item in job.items:
        if _unchecked(item):
            out[item.id] = room_unchecked.LABEL
            continue
        row = _row(job, item)
        if row is None or item.status not in _SEEN:
            continue
        if known is None:
            known = room_match.investor_rooms(db)
        state = room_match.find_state(row, known)
        label = room_match.FIND_LABELS[state]
        if state == "many":
            shown, _ = room_match.drop_investor_rooms(
                room_match.candidates(row)["rooms"], room_match.company_name(row), known)
            label = f"{label}(후보 {len(shown)})"
        out[item.id] = label
    return out


def summary(db: Session, job: SendJob) -> Optional[dict]:
    """끝난 방 확인 회차의 알림 — `{"sentence": …, "pick": bool}`. 아니면 `None`.

    `pick` 은 고를 화면이 있는 갈래(회사명으로 찾는 줄)다 — 화면이 알림창 대신 묻는
    창(이동할까요)을 띄운다. 그 화면 주소는 진행 화면이 이미 그린 링크다
    (`progress.html` 의 `room-pick-link`).
    """
    from ..routers.agent_api import VERIFY_KIND

    if job is None or job.kind != VERIFY_KIND or job.status not in ENDED:
        return None
    stopped = job.status == "canceled"
    # 확인을 못 한 건은 `못 찾음` · `불일치` · `오류` 에서 빼고 따로 센다(모듈 머리말).
    unchecked = sum(1 for i in job.items if _unchecked(i))
    # 무엇을 볼지 한 줄 — 건마다의 사유 글과 같은 말이다.
    tail = ("\n확인 못 함: 보내는 PC 카톡이 채팅 탭에 있는지, 잠금모드가 아닌지 보고 다시 "
            "확인해 주세요") if unchecked else ""
    sourcing = sourcing_rooms.search_summary(db, job)
    if sourcing is not None:
        # 그 셈은 딜 소싱 줄만 센다 — 확인 못 함도 그 줄 것만 `오류` 에서 덜어 적는다.
        blind = sum(1 for i in job.items
                    if i.sourcing_contact_id is not None and _unchecked(i))
        errors = max(0, sourcing["failed"] - blind)
        parts = [f"확정 {sourcing['confirmed']}", f"후보 고르기 {sourcing['picks']}",
                 f"못 찾음 {sourcing['not_found']}"]
        if errors:
            parts.append(f"오류 {errors}")
        if blind:
            parts.append(f"확인 못 함 {blind}")
        head = "딜 소싱 방 찾기를 중단했습니다" if stopped else "딜 소싱 방 찾기가 끝났습니다"
        return {"sentence": f"{head} — {' · '.join(parts)}{tail}", "pick": False}

    companies = [(i, _row(job, i)) for i in job.items]
    companies = [(i, r) for i, r in companies if r is not None]
    canceled = sum(1 for i in job.items if i.status not in _SEEN)
    if companies:
        known = room_match.investor_rooms(db)
        got = {k: 0 for k in room_match.FIND_LABELS}
        for item, row in companies:
            if item.status in _SEEN and not _unchecked(item):
                got[room_match.find_state(row, known)] += 1
        parts = [f"찾음 {got['found']}", f"여럿 {got['many']}", f"못 찾음 {got['none']}"]
        if got["verified"]:
            parts.append(f"확인됨 {got['verified']}")
        head = "방 찾기를 중단했습니다" if stopped else "방 찾기가 끝났습니다"
        pick = True
    else:
        sent = sum(1 for i in job.items if i.status == "sent")
        failed = sum(1 for i in job.items if i.status == "failed")
        parts = [f"확인됨 {sent}", f"불일치 {failed - unchecked}"]
        head = "방 연결 확인을 중단했습니다" if stopped else "방 연결 확인이 끝났습니다"
        pick = False
    if unchecked:
        parts.append(f"확인 못 함 {unchecked}")
    if canceled:
        parts.append(f"취소 {canceled}")
    return {"sentence": f"{head} — {' · '.join(parts)}{tail}", "pick": pick}
