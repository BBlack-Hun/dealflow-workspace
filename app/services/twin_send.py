"""같은 분께 **다른 팀원 몫으로** 같은 딜이 두 번 나가는 것을 막는다.

왜 생겼나
---------
투자사 관리 현황 업로드에 "다른 팀원에게 이미 있는 사람은 옮기지 않고 이
담당자 몫으로 따로 만들기" 를 붙였다(`sheet_import.apply_sheet_a`의
`keep_other_owner`). 그러면 같은 분(이름+투자사가 같다)이 두 팀원 명단에 한
줄씩 있게 된다.

발송은 **팀원마다 따로** 만든다 — 회차의 주인이 그 팀원이고(`SendJob.user_id`),
그 팀원 PC 의 발송기만 집어간다(`routers/agent_api.poll`). 그래서 한 회차 안에서
방 이름으로 겹침을 걸러도 소용이 없다 — 두 사람이 각자 자기 회차에 같은 분을
넣는다. 받는 분은 같은 기업 소개를 두 팀원에게서 두 번 받는다.

무엇을 보나
-----------
발송 목록을 만들 때 받는 분마다 **다른 팀원 몫의 같은 분**을 찾는다:

  · 이름과 투자사가 같다 (공백만 다른 것은 같은 것으로 본다), 또는
  · 카톡방 이름이 같다 (공백·대소문자 무시) — 메모 `duplicate-contact-assignments`
    가 "양쪽에 같은 방 이름이 붙는 순간 두 번 나간다" 고 적어 둔 그 경우다.

그 줄에 **최근 7일 안에** 같은 기업이 실린 딜소개가 나갔거나 나갈 예정이면
(대기·발송 중·보냄 — 실패·취소는 안 센다) 이번 목록에서 **뺀다.**

왜 막지 않고 빼나
-----------------
그룹 예약의 [시작] 도 같은 함수를 지난다(`routers/deals.start_queue_item`).
거기서 400 으로 멈추면 그 그룹은 한 사람 때문에 이번 주 내내 못 나간다 —
사람을 고를 길이 없는 화면이다. 대신 **조용히 빼지 않는다**: 미리보기가 그
분 경고에 이유를 싣고, 목록을 만든 응답이 뺀 분과 이유를 돌려준다. 고른
분이 전부 빠지면 그때는 400 이다(빈 회차를 만들지 않는다).

딜소개(`deal_intro`)만 본다. IR 자료 전달은 그 팀원이 받은 요청에 대한 답이라
담당한 쪽이 보내야 하고, 리마인드·미팅 문구는 기업이 실리지 않는다.
"""
from __future__ import annotations

import re
from datetime import timedelta
from typing import Dict, Iterable, List

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .. import clock
from ..models import DealBatchCompany, IrCompany, SendItem, SendJob, User, VcContact

#: 며칠 안에 나간 것을 같은 회차로 보나. 딜소개는 주 단위로 돈다.
WINDOW_DAYS = 7

#: 센다 — 나갔거나(`sent`), 나가는 중이거나(`sending`), 나갈 예정(`pending`).
LIVE_ITEM = ("pending", "sending", "sent")


def _key(text) -> str:
    return re.sub(r"\s+", "", str(text or "")).lower()


def twins(db: Session, contact: VcContact) -> List[VcContact]:
    """다른 팀원 몫의 **같은 분**.

    스타트업 안내 카톡도 이 판정을 읽는다(`services/startup_outreach.py`) —
    같은 스타트업이 두 팀원 명단에 한 줄씩 있으면, 한 사람이 보낸 문구를
    다른 사람이 또 보내지 않게. 무엇을 같은 분으로 보는지를 두 벌로 적지 않는다.
    """
    room = (contact.kakao_room_name or "").strip()
    conds = [VcContact.name == contact.name]
    if room:
        conds.append(VcContact.kakao_room_name == room)
    rows = db.execute(
        select(VcContact).where(VcContact.user_id != contact.user_id,
                                VcContact.id != contact.id, or_(*conds))
    ).scalars().all()
    name, firm, room_k = _key(contact.name), _key(contact.firm), _key(room)
    return [r for r in rows
            if (_key(r.name) == name and _key(r.firm) == firm)
            or (room_k and _key(r.kakao_room_name) == room_k)]


def blocked(db: Session, contacts: Iterable[VcContact],
            company_ids: Iterable[int]) -> Dict[int, str]:
    """`{contact_id: 이유}` — 이번 목록에서 뺄 분. 겹침이 없으면 빈 dict."""
    company_ids = list(company_ids)
    if not company_ids:
        return {}
    since = (clock.today() - timedelta(days=WINDOW_DAYS - 1)).isoformat()
    out: Dict[int, str] = {}
    for contact in contacts:
        twins_of = {t.id: t for t in twins(db, contact)}
        if not twins_of:
            continue
        hits = db.execute(
            select(SendItem.contact_id, SendItem.created_at,
                   DealBatchCompany.company_id)
            .join(SendJob, SendJob.id == SendItem.job_id)
            .join(DealBatchCompany, DealBatchCompany.batch_id == SendJob.batch_id)
            .where(SendItem.contact_id.in_(list(twins_of)),
                   SendJob.kind == "deal_intro",
                   SendJob.status != "canceled",
                   SendItem.status.in_(LIVE_ITEM),
                   SendItem.created_at >= since,
                   DealBatchCompany.company_id.in_(company_ids))
        ).all()
        if not hits:
            continue
        twin = twins_of[hits[0][0]]
        owner = db.get(User, twin.user_id)
        names = sorted({db.get(IrCompany, h[2]).name for h in hits
                        if db.get(IrCompany, h[2]) is not None})
        out[contact.id] = (
            f"같은 분이 {getattr(owner, 'name', '') or '다른 팀원'} 님 명단에도 있고, "
            f"{(hits[0][1] or '')[:10]} 에 같은 기업({', '.join(names)})을 "
            f"이미 보냈거나 보낼 예정입니다 — 두 번 나가지 않게 이번 목록에서 뺍니다")
    return out
