"""딜 제안 관리의 `반응 없음` — 판정이 적힌 한 곳.

딜소개를 받았는데 아무 반응이 없는 담당자다. 화면의 `반응 없음` 딱지와
[반응 없는 담당자만] 단추가 이 판정을 읽는다(`routers/pages.deals_page`).
이들에게는 목록을 또 밀어 넣기보다 무엇을 보고 싶은지 되묻는 편이 답이 온다.

## 무엇을 반응으로 보나 (#200)

예전에는 시트에서 옮겨 온 활동 줄의 IR 요청 · 만난 미팅만 봤다. 앱이 생긴 뒤의
반응은 다른 표와 칸에 쌓여서, IR 을 요청하고 자료까지 받은 분이 `반응 없음` 으로
골라졌다(2026-11 운영: 반응 없음 315명 중 42명).

- 대시보드 반응 칸이 세는 줄 — 시트 IR 요청 · 미팅 네 갈래(청한 것 포함) · 앱 IR
  요청 · 앱 미팅(`dashboard.reaction_hits`). 두 화면이 같은 줄을 반응으로 본다.
- IR 자료 전달 기록 · [답 옴] — 자료를 보냈거나 답이 왔으면 이미 이어진 것이다.
- 리마인드가 `답 옴` 으로 멈춘 사람 — 리마인드 표의 [답 옴](카톡에서 답을 받았습니다)
  이나, IR 요청 · 미팅 · 자료 전달을 적어 앱이 멈춘 것(`cadence.stop_on_reaction`).
  `IR 요청 투자사` 표에 `답 옴` 으로 서 있는데 여기서 `반응 없음` 이라고 했다
  (2026-11-10 운영: 반응 없음 361명 중 24명 — 그중 둘은 IR 요청을 적었다가 그 줄을
  나중에 지운 분이다). 사람이 손으로 멈춘 것(`중단`)은 답이 왔다는 뜻이 아니라 안 본다.
- 명단의 `IR 요청` 칸에 사람이 적은 글 — 업무 보고가 `전달` 을 읽는 그 칸이고, 시트
  시절의 달 없는 `IR 요청` 칸까지 본다(`memo_delivered.is_ir_request_column` — 달은
  업무 보고가 날짜를 읽을 때만 필요하다).

**선호 · 메모 칸은 반응으로 안 본다.** 반응 없음 315명 모두 어딘가에 값이 있다 —
카톡방 참여(자동) · 월별 딜소개 칸(우리가 보낸 기록) · 관심도 `낮음` · TIPS
운영사(조사 값)가 그렇고, `연락 시작 / 반응` 칸 38명 중 21명은 그 칸에 `반응 없음`
이라고 적혀 있다. 값이 있다는 것만으로는 답이 왔는지 알 수 없다.

**그룹 칸은 건드리지 않는다.** 그룹은 그분이 받을 딜을 고르는 선호 갈래라
(`group_name`), 반응으로 덮어쓰면 다음 리스트업에서 그분의 딜이 엇나간다. 반응이
생긴 분은 이 판정에서 빠지는 것으로 [반응 없는 담당자만] 에서 저절로 빠진다.

## `상태` 칸의 `반응없음` 은 반응이 적히면 풀린다 (11/10)

`상태`(`VcContact.status = no_response`)는 사람이 상세에서 고르는 값이라 이 판정과
따로 논다 — 반응이 와도 그대로 남았다. IR 관리의 담당자 고르기가 그 값을
`[반응없음]` 꼬리표로 붙여서(`sheet_owner.pick_note`), IR 요청을 여러 번 한 분을
적을 때마다 반응없음으로 보였다(2026-11-10 운영: 상태 반응없음 100명 중 23명이 IR
요청 기록이 있다 — 모두 시트 시절 기록이고, 딜 제안 관리의 이 판정은 그분들을 이미
반응 있음으로 본다).

반응이 생긴 뒤에도 남은 `반응없음` 은 낡은 값이라 **반응이 적히는 순간 `활발` 로
푼다**(`before_flush`). 어느 길로 적든(IR 관리 · 리마인드 [답 옴] · 자료 전달 기록 ·
시트 가져오기) 빠지지 않게 세션의 flush 한 곳에서 건다(`models._clear_no_response`).
푸는 것은 `반응없음` 하나다 — `검토중단` 은 딜 소개를 멈춰 둔 사람의 결정이라
(`sheet_owner.is_paused`) 반응과 상관없다. 이미 낡아 있는 값은 새 반응이 와야
풀리므로, 그 몫은 운영 데이터를 한 번 고쳐야 한다(코드가 하지 않는다).
"""
from __future__ import annotations

from typing import List, Set

from sqlalchemy import inspect, select
from sqlalchemy.orm import Session

from ..models import (ContactActivity, ContactColumn, IrRequest, Meeting, SendSequence,
                      VcContact)
from . import contact_columns, dashboard, memo_delivered
from . import meeting_kind as mk
from .automations.meeting_request import REPLY_KIND
from .manual_send import IR_DELIVERY
from .sheet_owner import STATUS_ACTIVE, STATUS_NO_RESPONSE

#: 우리 쪽이 적은 기록이지만 **반응이 있었다는 뜻**인 활동 — 자료를 보냈다 · 답이 왔다.
FOLLOWED = (IR_DELIVERY, REPLY_KIND)

#: 리마인드가 답을 받아 멈춘 상태(`cadence.STATUS_LABELS` 의 `답 옴`).
RESPONDED = "responded"

#: 반응인 활동 갈래 — `reacted_ids` 가 읽는 것과 같다(대시보드가 세는 시트 IR 요청 ·
#: 미팅 네 갈래 + `FOLLOWED`).
REACTION_KINDS = ("ir_request",) + mk.ALL + FOLLOWED


def reacted_ids(db: Session, contact_ids: List[int]) -> Set[int]:
    """이 사람들 중 반응이 한 번이라도 있었던 사람. 기간을 자르지 않는다 —
    반응은 한 번 오면 없어지는 것이 아니다(`contacts._reaction_tags` 와 같은 이유)."""
    if not contact_ids:
        return set()
    hits = dashboard.reaction_hits(db, contact_ids)
    got = {h.contact_id for key in ("ir_contacts", "meeting_contacts") for h in hits[key]}
    # 되돌린 줄은 세션이 이미 뺀다(`models._hide_undone_activities`).
    got.update(db.execute(
        select(ContactActivity.contact_id).where(
            ContactActivity.contact_id.in_(contact_ids),
            ContactActivity.kind.in_(FOLLOWED))).scalars())
    got.update(db.execute(
        select(SendSequence.contact_id).where(
            SendSequence.contact_id.in_(contact_ids),
            SendSequence.status == RESPONDED)).scalars())
    return got


def ids(db: Session, rows: List[dict]) -> Set[int]:
    """`contacts.contact_rows` 의 줄 중 **딜소개를 받고 반응이 없는** 사람 번호."""
    sent = [r for r in rows if r["last_deal"]]
    if not sent:
        return set()
    reacted = reacted_ids(db, [r["id"] for r in sent])
    keys = [contact_columns.note_key(c.id)
            for c in db.execute(select(ContactColumn)).scalars().all()
            if memo_delivered.is_ir_request_column(c)]
    return {r["id"] for r in sent if r["id"] not in reacted
            and not any(r["notes"].get(k, "").strip() for k in keys)}


def _reacted_in(session) -> Set[int]:
    """이번 flush 에 **새로 적히는 반응**의 담당자 번호 — `reacted_ids` 가 읽는 원본 그대로."""
    out: Set[int] = set()
    for obj in session.new:
        if isinstance(obj, (IrRequest, Meeting)):
            out.add(obj.contact_id)
        elif isinstance(obj, ContactActivity) and obj.kind in REACTION_KINDS:
            # 관계로만 이어 둔 줄은 번호가 flush 뒤에 정해진다.
            out.add(obj.contact_id or getattr(obj.contact, "id", None))
    for obj in list(session.new) + list(session.dirty):
        if (isinstance(obj, SendSequence) and obj.status == RESPONDED
                and (obj in session.new or inspect(obj).attrs.status.history.has_changes())):
            out.add(obj.contact_id)
    out.discard(None)
    return out


def before_flush(session) -> None:
    """반응이 새로 적히는 분의 `상태` 가 `반응없음` 이면 `활발` 로 푼다(위 머리말)."""
    ids = _reacted_in(session)
    if not ids:
        return
    with session.no_autoflush:
        for contact in session.execute(
                select(VcContact).where(VcContact.id.in_(ids),
                                        VcContact.status == STATUS_NO_RESPONSE)).scalars():
            contact.status = STATUS_ACTIVE


def listed(db: Session, user, contacts=None) -> Set[int]:
    """딜 제안 관리 대상 목록(`sheet_owner.recipients`)에 선 사람 중 **반응 없는 분**.

    딜 제안 관리의 `반응 없음` 딱지 · [반응 없는 담당자만] 단추 수와, 대시보드의
    `반응 없는 분 N명`(#213)이 **이 한 벌**을 읽는다. 대시보드가 `내 투자사 선호`
    (IR 요청한 분 순위)의 바깥을 따로 세면 딜소개를 아직 안 받은 분과 미팅 · 답 옴이
    있는 분이 섞여, 눌러 넘어간 화면과 수가 갈린다(2026-11-10 운영: 계정마다 5~41명).
    `contacts` 는 이미 구한 대상 목록을 받는 자리다(딜 제안 관리가 넘긴다).
    """
    from ..routers.contacts import contact_rows   # 순환 import 를 피해 늦게 부른다
    from .sheet_owner import recipients

    shown = contacts if contacts is not None else recipients(db, user)
    return ids(db, contact_rows(db, user)) & {c.id for c in shown}
