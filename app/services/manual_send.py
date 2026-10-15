"""손으로 보낸 것을 적는 자리.

## 왜 만드나

팀원 중에 **프로그램으로 카톡을 보내지 않고 손으로 보내는** 사람이 있다.
그 사람이 한 일은 지금 앱 어디에도 안 남는다. 그래서 그 사람만

  * 업무 보고의 `딜 소개 총 N명` 이 비어 있고,
  * 진행 단계가 `딜소개 전` 에 머물러 있고,
  * **리마인드가 아예 안 선다** — 보낸 기록이 없으니 후속을 세울 근거가 없다.

적을 자리를 새로 만들지 않는다. `ContactActivity` 가 이미 **앱이 안 보낸
일**을 적는 자리다(`ir_delivery` 는 사람이 PC 카톡에서 붙인 자료,
`meeting_ask` 는 사람이 직접 보낸 미팅 요청). 개발 자료로 재 보면 딜 소개를
"보냈다" 는 근거가 `SendItem` 8건 대 `ContactActivity` 946건이다 — 이 표가
이미 그 역할을 하고 있다.

## 갈래(`kind`)를 새로 만들지 않는다

`kind` 로 거르는 자리가 아홉 곳이다. 새 값을 만들면 그 아홉 곳이 새 값을
몰라 안 읽는다 — #162 가 `meeting_ask` 하나만 만들어 딜 소개가 남은 것이
정확히 그 모양이다. 그래서 갈래는 **있던 값 그대로** 쓰고, 사람이 적었다는
것은 `source="manual"` 로 가른다(`models.SOURCE_MANUAL`).

## 이 파일이 혼자 쥐고 있는 판정 셋

1. **합쳐 세는 것** (`counted`) — 업무 보고 발송 표와 대시보드 두 곳이
   이것을 읽는다. 세는 자리를 새로 만들지 않는다.
2. **오늘인가 지난 날인가** (`sets_reminder` · `REMIND_NOTE`) — 리마인드를
   세울지 가르는 자리이고, 화면이 미리 하는 말도 같은 곳에서 나온다.
3. **같은 것을 두 번 적었나** (`existing`) — `ir_attach` · `pipeline` 도
   이 함수를 지난다.

그리고 **되돌릴 때 시퀀스를 어떻게 되짚나**(`_release`) — 적을 때 남긴 흔적
(`ContactActivity.sequence_trace`)을 읽는 자리도 여기 하나다.
"""
from __future__ import annotations

import json
import uuid
from datetime import date
from typing import Dict, List, Optional, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..clock import now_iso, today as _today
from ..models import (SOURCE_MANUAL, ContactActivity, SendSequence, VcContact,
                      including_undone)
from . import cadence
from . import message_composer as mc

#: 사람이 손으로 적을 수 있는 것. **나간 것**만이다.
#:
#: IR 요청(`ir_request`)·미팅(`meeting`)은 여기 없다 — 그건 상대가 보인
#: 반응이지 이쪽이 보낸 것이 아니고, 적는 화면이 따로 있다(후속 관리).
DEAL_INTRO = "deal_intro"
IR_DELIVERY = "ir_delivery"
MEETING_ASK = "meeting_ask"

#: 화면에 쓰는 말. **발송 화면의 탭 이름과 같은 말이어야 한다**
#: (`routers/deals.MODE_TITLES`) — 같은 것이 화면마다 다른 이름으로 불리면
#: 어느 것을 적는 중인지 알 수 없다.
KIND_LABELS = {
    DEAL_INTRO: "딜 소개",
    IR_DELIVERY: "IR 자료 전달",
    MEETING_ASK: "미팅 요청",
}

#: 기업을 함께 적는 갈래. **미팅 요청은 기업을 안 적는다** — 나가는 카톡이
#: 담당자당 한 통이고 딸 기업이 없다(`routers/deals.MODES_WITH_COMPANIES` 에
#: 미팅이 없는 것과 같은 이유).
KINDS_WITH_COMPANIES = (DEAL_INTRO, IR_DELIVERY)

#: 수동 기록 한 줄을 **앱이 보낸 건과 같은 말로** 옮긴다 —
#: `(SendJob.kind, SendItem.stage)`.
#:
#: 세는 자리도 리마인드를 세우는 자리도 이미 이 두 값으로 움직인다. 여기서
#: 한 번 옮겨 주면 그 자리들이 **자기 기준을 그대로 쓰면서** 수동 기록을 함께
#: 읽는다 — 자리마다 "수동은 이렇게 세라" 를 따로 적지 않아도 된다.
#:
#: 단계 값은 문구를 짓는 쪽이 정한 것을 그대로 읽는다(`message_composer`).
#: 여기 숫자를 다시 적으면 한쪽이 바뀔 때 이쪽만 옛 값으로 남는다
#: (`services/report.py` 도 같은 이유로 `mc` 를 읽는다).
AS_SEND = {
    DEAL_INTRO: ("deal_intro", mc.STAGE_DAY1),
    # 미팅 요청은 앱에서도 `deal_intro` 잡에 `stage=3` 으로 나간다 —
    # `SendJob.kind` 가 후속을 따로 적지 않기 때문이다(`report.send_group_key`).
    MEETING_ASK: ("deal_intro", mc.STAGE_MEETING),
    IR_DELIVERY: ("ir_delivery", None),
}

#: 화면이 **미리** 하는 말. 적고 나서 알면 이미 늦다.
#:
#: 코드와 화면이 다른 숫자·다른 말을 하면 안 되므로 글자도 여기 둔다
#: (`pipeline.IR_MEETING_ASK_DAYS` 를 화면에 실어 주는 것과 같은 방식).
REMIND_NOTE = ("오늘 날짜로 적으면 리마인드가 잡힙니다 · "
               "지난 날짜는 기록만 남습니다")

#: 한 번에 적을 수 있는 줄 수의 상한. 실제로 80명을 한 번에 적는다 —
#: 넉넉히 두되 무한은 아니다(잘못 만든 요청 하나가 표를 통째로 채우면 안 된다).
MAX_ROWS = 500


def _payload(names: Sequence[str]) -> str:
    return json.dumps([str(n) for n in names], ensure_ascii=False)


# ─────────────────────────────────────────────────────────────────────────────
# ① 같은 것을 두 번 적었나 — **판정은 여기 하나다**
# ─────────────────────────────────────────────────────────────────────────────

def existing(db: Session, contact_id: int, kind: str, day: str,
             company_names: Optional[Sequence[str]] = None,
             company_count: Optional[int] = None) -> Optional[ContactActivity]:
    """**같은 날 · 같은 담당자 · 같은 기업 묶음**이면 이미 적혀 있는 그 줄.

    ★ 이 판정을 쓰는 곳이 셋이다 — 여기(묶음 입력) · `ir_attach.record_delivery`
    (자료 보내기) · `pipeline.record_meeting_ask`(미팅 요청 표시). 세 곳이 각자
    적어 두면 한쪽만 고쳐진 날 같은 줄이 두 번 쌓인다. 같은 줄이 두 번 쌓이면
    이력이 아니라 소음이고, 실패해서 다시 보내는 것은 흔한 일이다.

    기업을 안 넘기면(미팅 요청) **날짜와 갈래만** 본다 — 그 갈래에는 딸 기업이
    없어서 더 볼 것이 없다.

    개수만 적는 줄(`핵심 딜 8개사`)은 기업 이름이 없으므로 **개수로** 가린다.
    안 그러면 같은 날 `8개사` 와 `5개사` 가 둘 다 이름 없는 줄이라 뒤엣것이
    "이미 있음" 으로 빠진다.
    """
    stmt = select(ContactActivity).where(
        ContactActivity.contact_id == contact_id,
        ContactActivity.kind == kind,
        ContactActivity.happened_at == day)
    if company_names is not None:
        stmt = stmt.where(ContactActivity.company_names == _payload(company_names))
    if company_count is not None:
        stmt = stmt.where(ContactActivity.company_count == company_count)
    return db.execute(stmt).scalars().first()


# ─────────────────────────────────────────────────────────────────────────────
# ② 오늘인가 지난 날인가 — **가르는 자리도 여기 하나다**
# ─────────────────────────────────────────────────────────────────────────────

def is_day(value: str) -> bool:
    """`2026-09-15` 인가. **짐작하지 않는다** — 못 읽는 값이면 오늘로 대신
    적지 않고 거절한다(`ir_monthly.is_month` 와 같은 결).

    오늘로 짐작하면 리마인드가 서는 쪽으로 기울고, 그건 되돌리기 번거롭다.
    """
    try:
        return date.fromisoformat(str(value or "")).isoformat() == value
    except (TypeError, ValueError):
        return False


def sets_reminder(day: str, today: Optional[date] = None) -> bool:
    """이 날짜로 적으면 **리마인드가 서는가**.

    ## 왜 오늘 것만 세우나

    손으로 보냈다고 적으면 리마인드가 걸려야 한다 — 지금 손으로 보내는 사람은
    리마인드가 아예 안 서고 있고, 그것이 이 기능을 만드는 까닭의 절반이다.

    그런데 **소급 입력이 문제다.** 2주 전에 보낸 80명을 오늘 몰아 적으면
    그 80건이 전부 "리마인드 기한이 이미 지난 것" 으로 서서, 여는 순간
    `밀린 리마인드 80건` 이 뜬다. 오늘 실제로 해야 할 두세 건이 거기 묻히고,
    사람은 목록 전체를 못 믿게 된다 — 한 번 그렇게 되면 다시 안 본다.

    그래서 **오늘 적은 것만 세운다.** 지난 날짜는 기록만 남는다(보고·진행
    단계·`이미 보낸 기업` 은 그대로 다 받는다 — 빠지는 것은 후속 예약뿐이다).

    화면이 이 사실을 **미리** 말한다(`REMIND_NOTE`).
    """
    return day == (today or _today()).isoformat()


# ─────────────────────────────────────────────────────────────────────────────
# ③ 적기
# ─────────────────────────────────────────────────────────────────────────────

class Result:
    """한 판의 결과. `77줄 적음 · 3줄은 이미 있었음` 을 화면이 만들 재료다."""

    __slots__ = ("batch_key", "added", "duplicated", "reminded", "day", "kind")

    def __init__(self, *, batch_key: str, added: int, duplicated: int,
                 reminded: int, day: str, kind: str) -> None:
        self.batch_key = batch_key
        self.added = added
        self.duplicated = duplicated
        self.reminded = reminded
        self.day = day
        self.kind = kind

    def as_dict(self) -> dict:
        return {"batch_key": self.batch_key, "added": self.added,
                "duplicated": self.duplicated, "reminded": self.reminded,
                "day": self.day, "kind": self.kind,
                "kind_label": KIND_LABELS.get(self.kind, self.kind),
                "note": self.note()}

    def note(self) -> str:
        """★ 사람이 읽는 한 줄을 짓는 자리도 여기 하나다 — 화면이 그대로 띄운다."""
        parts = [f"{self.added}줄 적음"]
        if self.duplicated:
            parts.append(f"{self.duplicated}줄은 이미 있었음")
        parts.append(f"리마인드 {self.reminded}건 잡힘" if self.reminded
                     else "리마인드는 잡히지 않음(지난 날짜)")
        return " · ".join(parts)


def plan(db: Session, contacts: Sequence[VcContact], kind: str, day: str,
         company_names: Optional[Sequence[str]] = None,
         company_count: Optional[int] = None,
         today: Optional[date] = None) -> dict:
    """적기 전에 **세어만 본다.** 한 줄도 쓰지 않는다.

    `routers/contacts.bulk_delete_contacts` 의 결 그대로다 — 화면은 이것을 먼저
    불러 무엇이 몇 줄인지 사람에게 보여 주고, [확인] 을 누른 뒤에야 참으로
    적는다. 확인을 화면에만 두면 번호를 직접 보내는 길로 80줄이 아무 말 없이
    들어온다.
    """
    names = list(company_names or []) if kind in KINDS_WITH_COMPANIES else []
    count = len(names) if names else (
        company_count if kind in KINDS_WITH_COMPANIES else None)
    already = sum(
        1 for c in contacts
        if existing(db, c.id, kind, day,
                    company_names=names if names else None,
                    company_count=None if names else count) is not None)
    total = len(contacts)
    return {
        "total": total,
        "already": already,
        "adding": total - already,
        "day": day,
        "kind": kind,
        "kind_label": KIND_LABELS.get(kind, kind),
        "companies": names,
        "company_count": count,
        # 화면이 확인창에 그대로 띄우는 말. 여기서 짓지 않으면 두 벌이 된다.
        "will_remind": sets_reminder(day, today),
        "remind_note": REMIND_NOTE,
    }


def record(db: Session, contacts: Sequence[VcContact], kind: str, day: str,
           company_names: Optional[Sequence[str]] = None,
           company_count: Optional[int] = None,
           today: Optional[date] = None,
           rng=None) -> Result:
    """손으로 보낸 것을 **한 판으로** 적는다. 커밋은 부르는 쪽이 한다.

    **기업은 판 하나에 한 번만 받는다.** 80명에게 같은 8개사를 보낸 것이
    보통이라, 줄마다 고르게 하면 80번 고르는 일이 된다.

    담당자 줄을 골라 오는 것도, 그 줄에 손대도 되는지 가리는 것도 부르는 쪽
    (`routers/contacts.py`)의 몫이다 — 권한 판정을 여기서 새로 지으면 화면에
    뜬 줄을 눌러도 서버가 막는 어긋남이 난다.
    """
    names = list(company_names or []) if kind in KINDS_WITH_COMPANIES else []
    count = company_count if kind in KINDS_WITH_COMPANIES else None
    # 이름이 있으면 개수는 그 수다 — 사람이 따로 적게 하지 않는다.
    if names:
        count = len(names)

    # 묶음 표시. 값 자체에는 뜻이 없다(누가 언제 적었는지는 줄이 이미 안다) —
    # **같은 판인지**만 말하면 된다.
    batch_key = f"ms-{day}-{uuid.uuid4().hex[:12]}"
    send_kind, stage = AS_SEND[kind]
    will_remind = sets_reminder(day, today)

    added = duplicated = reminded = 0
    for contact in contacts:
        if existing(db, contact.id, kind, day,
                    company_names=names if names else None,
                    company_count=None if names else count):
            duplicated += 1
            continue

        # 시퀀스를 **먼저** 움직이고 줄을 나중에 넣는다 — 시퀀스에 무엇을
        # 했는지(`trace`)를 줄에 담아 **한 번에** 넣으려는 것이다. 줄을 먼저
        # 넣고 나중에 고치면 수정 로그에 `추가` 와 `수정` 이 한 줄씩 쌓인다
        # (`edit_log.WATCHED["contact_activities"]`). `advance` 는 활동 줄을
        # 읽지 않으므로 차례를 바꿔도 판정은 그대로다.
        trace = None
        if will_remind:
            seq, trace = _advance(db, contact, send_kind, stage, rng)
            if seq is not None:
                reminded += 1

        db.add(ContactActivity(
            contact_id=contact.id, kind=kind, source=SOURCE_MANUAL,
            content=_content(kind, names, count),
            happened_at=day, month=day[:7],
            company_names=_payload(names) if names else None,
            company_count=count,
            batch_key=batch_key,
            sequence_trace=trace))
        added += 1

    db.flush()
    return Result(batch_key=batch_key, added=added, duplicated=duplicated,
                  reminded=reminded, day=day, kind=kind)


def _advance(db: Session, contact: VcContact, send_kind: str,
             stage: Optional[int], rng=None):
    """리마인드를 세우고 **세우면서 한 일**을 함께 돌려준다 — `(시퀀스, 흔적)`.

    **리마인드를 세우는 판정은 `cadence.advance` 한 곳이다.** 단계 사다리도
    다음 예정일 계산도 여기서 다시 하지 않는다 — 두 벌이 되면 손으로 보낸
    사람의 후속만 다른 날짜로 잡히고, 그 어긋남은 몇 달 뒤에 드러난다.

    시퀀스의 주인은 **그 담당자를 맡은 사람**이다(적은 사람이 아니다).
    관리자가 남의 줄을 대신 적어 줘도 후속은 담당자에게 떠야 한다.

    ## 왜 흔적을 남기나

    `advance` 는 이미 서 있던 시퀀스를 **덮어쓴다**(딜소개일을 오늘로 다시
    잡고, 미팅 요청이면 단계를 올리고, IR 자료면 멈춘다). 덮어쓴 뒤에는 그 전
    모습이 어디에도 없어서, 이 줄을 되돌릴 때 시퀀스를 어디로 돌려놓을지 알
    길이 없다. 그래서 **부르기 전 모습**을 떠 두었다가 줄에 함께 적는다.
    전 모습을 뜨는 줄은 `advance` 가 읽는 바로 그 줄이다(`cadence.latest`).
    """
    before_seq = cadence.latest(db, contact.id)
    before = cadence.snapshot(before_seq)
    seq = cadence.advance(db, user_id=contact.user_id, contact_id=contact.id,
                          batch_id=None, kind=send_kind, stage=stage,
                          sent_at=now_iso(), rng=rng)
    if seq is None:
        return None, None
    after = cadence.snapshot(seq)
    if before_seq is None or seq.id != before_seq.id:
        # **새로 세웠다.** 되돌리면 멈춘다 — 그 전에는 이 사람에게 돌던
        # 후속이 없었다(있었다면 멈춘 것이고, 그 줄은 여기서 안 건드렸다).
        before = None
    elif after == before:
        # 읽기만 하고 아무것도 안 바꿨다(멈춘 시퀀스에 미팅 요청을 적은 것
        # 같은 때). 되돌릴 것이 없으니 흔적도 없다.
        return seq, None
    return seq, json.dumps({"id": seq.id, "before": before, "after": after},
                           ensure_ascii=False)


#: 줄에 적히는 글. 이력 화면이 기업 이름을 못 찾았을 때 대신 보여 주는 값이라
#: (`routers/contacts._round_label`) **무엇을 손으로 보냈는지**가 들어가야 한다.
BY_HAND = "손으로 보냄"


def _content(kind: str, names: Sequence[str], count: Optional[int]) -> str:
    head = f"{KIND_LABELS.get(kind, kind)} — {BY_HAND}"
    if count:
        return f"{head} · {count}개사"
    return head


# ─────────────────────────────────────────────────────────────────────────────
# ④ 되돌리기 — 지우지 않고 숨긴다
# ─────────────────────────────────────────────────────────────────────────────

def rows_of(db: Session, batch_key: str,
            contact_id: Optional[int] = None) -> List[ContactActivity]:
    """그 판으로 들어온 (아직 되돌리지 않은) 줄들.

    `contact_id` 를 주면 **그 판 안의 그 담당자 줄만** — 한 사람 되돌리기다.
    80명을 적은 판에서 한 사람만 잘못 넣은 일이 흔해서, 묶음째 되돌리고 79명을
    다시 적게 하면 안 된다. 담당자 상세의 활동 이력도 이 길로 한 줄을 되돌린다
    (`static/js/contacts.js`) — 같은 줄을 고르는 조회가 두 벌이 되지 않는다.
    """
    if not batch_key:
        return []
    stmt = (select(ContactActivity)
            .where(ContactActivity.batch_key == batch_key))
    if contact_id is not None:
        stmt = stmt.where(ContactActivity.contact_id == contact_id)
    return list(db.execute(stmt.order_by(ContactActivity.id)).scalars().all())


def undoable(act: ContactActivity) -> bool:
    """이 줄을 **화면에서 되돌릴 수 있나** — 손으로 적은 판의 줄만.

    시트에서 옮겨 온 줄·앱이 적은 줄은 되돌리는 길이 없다. 그 줄들은 들어온
    길(시트 다시 올리기 · 발송 기록)이 따로 있어, 여기서 숨기면 다음 가져오기
    때 같은 줄이 또 들어오거나 발송 기록과 이력이 어긋난다.

    담당자 상세의 활동 이력이 [되돌리기] 를 세울지 이것으로 정한다
    (`routers/contacts._activity_view`). 권한은 여기서 보지 않는다 — 그 화면을
    연 것 자체가 `_owned` 를 지난 것이고, 되돌리는 요청도 같은 판정을 지난다.
    """
    return (act.source == SOURCE_MANUAL and bool(act.batch_key)
            and not act.undone_at)


#: 되돌린 기록이 **새로 세웠던** 시퀀스를 멈출 때 남기는 까닭. 후속 관리 표의
#: `중단` 줄에 그대로 선다 — 왜 멈췄는지 안 적혀 있으면 사람이 [다시 켜기] 를
#: 눌러 받은 적 없는 사람에게 리마인드를 되살린다.
UNDO_REASON = "손으로 적은 기록을 되돌렸습니다"


class Undone:
    """되돌린 결과 — `3줄 되돌림 · 리마인드 2건 거둠` 을 화면이 만들 재료다."""

    __slots__ = ("rows", "sequences")

    def __init__(self, *, rows: int, sequences: int) -> None:
        self.rows = rows
        self.sequences = sequences

    def note(self) -> str:
        """★ 사람이 읽는 한 줄을 짓는 자리도 여기 하나다 — 두 화면이 그대로 띄운다."""
        text = f"{self.rows}줄을 되돌렸습니다"
        if self.sequences:
            text += f" · 리마인드 {self.sequences}건을 거뒀습니다"
        return text


def undo_plan(db: Session, rows: Sequence[ContactActivity]) -> dict:
    """되돌리기 전에 **세어만 본다.** 한 줄도 안 바꾼다.

    리마인드를 몇 건 함께 거두는지도 미리 말한다 — 그게 이 되돌리기의 절반이다.
    세는 판정은 실제로 거두는 자리와 같은 함수다(`_release(dry=True)`).
    """
    first = rows[0] if rows else None
    return {
        "rows": len(rows),
        "kind": first.kind if first else "",
        "kind_label": KIND_LABELS.get(first.kind, first.kind) if first else "",
        "day": (first.happened_at or "") if first else "",
        "sequences": sum(1 for row in rows if _release(db, row, dry=True)),
    }


def undo(db: Session, rows: Sequence[ContactActivity]) -> Undone:
    """그 줄들을 **숨기고**, 그 줄이 세운 리마인드를 거둔다. 커밋은 부르는 쪽이 한다.

    줄은 지우지 않는다. 숨긴 줄은 읽는 자리 어디에서도 안 읽힌다 — 거르는
    자리는 `models._hide_undone_activities` 한 곳이다.

    ## 시퀀스도 되짚는다

    전에는 여기서 시퀀스를 안 건드렸다. 줄만 숨기면 `cadence.sweep_reactions`
    가 정리할 줄 알았지만, 그쪽은 **반응(IR 요청·미팅)이 생긴 것만** 멈춘다 —
    되돌린 딜 소개가 세운 리마인드는 그대로 남아 받은 적 없는 사람에게
    "지난번 공유드린…" 이 나갈 수 있었다.

    그래서 **이 줄이 시퀀스에 한 일만** 되짚는다(`_release`). 실제 발송이나
    다른 기록이 세운 시퀀스는 안 건드린다.
    """
    when = now_iso()
    n = released = 0
    for row in rows:
        if row.undone_at:
            continue
        row.undone_at = when
        n += 1
        if _release(db, row):
            released += 1
    db.flush()
    return Undone(rows=n, sequences=released)


def _trace_of(row: ContactActivity) -> Optional[dict]:
    """줄에 적힌 흔적. 없거나 못 읽으면 `None` — **되짚지 않는다.**

    못 읽는 흔적으로 짐작해 시퀀스를 고치면 남의 후속을 망가뜨린다. 그러면
    줄만 숨고 시퀀스는 그대로인 이 판 전 동작으로 돌아갈 뿐이다.
    """
    if not row.sequence_trace:
        return None
    try:
        data = json.loads(row.sequence_trace)
    except (TypeError, ValueError):
        return None
    if not isinstance(data, dict) or not isinstance(data.get("id"), int):
        return None
    return data


def _release(db: Session, row: ContactActivity, dry: bool = False) -> bool:
    """이 줄이 시퀀스에 한 일을 되짚는다. 시퀀스를 고쳤으면(고칠 것이면) 참.

    ★ 되짚는 판정은 여기 하나다 — `undo` 와 `undo_plan` 이 함께 지난다.

    ## 언제 고치나 — 시퀀스가 **이 줄이 두고 간 모습 그대로**일 때만

    지금 모습이 적어 둔 `after` 와 같으면 그 뒤로 아무도 안 건드린 것이다.
    그때만 되짚는다.

    · `before` 가 없으면 이 줄이 **새로 세운** 시퀀스다 → 멈춘다
      (`stopped` — 사람이 멈춘 것과 같은 갈래다. 지우지 않는다: 후속 관리 표에
      `중단 · 손으로 적은 기록을 되돌렸습니다` 로 남아야 왜 멈췄는지 안다).
    · 있으면 그 전에 서 있던 시퀀스를 **덮어쓴** 것이다 → 그 모습으로 되돌린다
      (실제 발송이 세운 리마인드를 오늘 딜 소개가 덮었다면 원래 날짜로 돌아간다).

    ## 그 뒤에 무엇이 움직였으면 손대지 않는다

    앱이 리마인드를 실제로 보냈거나, 답이 와서 멈췄거나, 사람이 [다시 켜기] 를
    눌렀다면 시퀀스는 이미 **다른 일의 것**이다. 그걸 되돌리면 실제로 나간
    리마인드나 사람이 내린 판단을 지운다 — 그래서 그대로 둔다.

    다만 그 뒤에 움직인 것이 **손으로 적은 다른 줄**이면 고리를 잇는다
    (`_splice`). 안 이으면 A 를 먼저 되돌리고 B 를 나중에 되돌렸을 때, B 가
    A 의 모습(= 되돌린 딜 소개의 리마인드)을 되살린다.
    """
    trace = _trace_of(row)
    if trace is None:
        return False
    seq = db.get(SendSequence, trace["id"])
    if seq is None:
        # 사람이 후속 관리에서 지웠다 — 되짚을 것이 없다.
        return False
    if cadence.snapshot(seq) != trace.get("after"):
        if not dry:
            _splice(db, row, trace)
        return False
    if dry:
        return True
    before = trace.get("before")
    if before is None:
        cadence.stop(db, seq, UNDO_REASON, status="stopped")
    else:
        cadence.restore(db, seq, before)
    return True


def _splice(db: Session, row: ContactActivity, trace: dict) -> None:
    """뒤에 적힌 줄이 이 줄의 `after` 를 `before` 로 들고 있으면 그것을 이 줄의
    `before` 로 바꾼다 — 사슬에서 이 줄을 빼는 것이다.

    같은 사람에게 같은 날 두 판을 적는 일이 있다(`8개사` 다음 `5개사`, 딜 소개
    다음 IR 자료). 뒤 줄 B 가 앞 줄 A 의 시퀀스를 덮어쓰면 B 의 `before` 는
    A 의 `after` 다. A 를 먼저 되돌릴 때 시퀀스는 B 의 모습이라 손대지 않는데,
    B 의 `before` 를 그대로 두면 나중에 B 를 되돌릴 때 **이미 되돌린 A 의
    리마인드가 되살아난다.** 그래서 B 가 돌아갈 자리를 A 가 오기 전으로 옮긴다.

    되돌린 줄은 조회에 안 걸리므로(`models._hide_undone_activities`) 이미
    되돌린 줄의 흔적은 고치지 않는다.
    """
    later = db.execute(
        select(ContactActivity).where(
            ContactActivity.contact_id == row.contact_id,
            ContactActivity.id > row.id,
            ContactActivity.sequence_trace.isnot(None))
        .order_by(ContactActivity.id)
    ).scalars().all()
    for other in later:
        theirs = _trace_of(other)
        if (theirs is None or theirs["id"] != trace["id"]
                or theirs.get("before") != trace.get("after")):
            continue
        theirs["before"] = trace.get("before")
        other.sequence_trace = json.dumps(theirs, ensure_ascii=False)


def batches(db: Session, contact_ids: Sequence[int],
            limit: int = 20) -> List[dict]:
    """최근에 적은 판들 — **되돌린 것까지** 보여 준다.

    되돌린 판이 목록에서 통째로 사라지면 사람은 자기가 되돌렸는지 애초에 안
    적었는지를 알 수 없다. 그래서 여기서만 숨긴 줄을 함께 읽는다
    (`models.including_undone` — 읽기 전용이다).
    """
    ids = list(contact_ids)
    if not ids:
        return []
    with including_undone(db):
        rows = list(db.execute(
            select(ContactActivity)
            .where(ContactActivity.contact_id.in_(ids),
                   ContactActivity.batch_key.isnot(None))
            .order_by(ContactActivity.id.desc())
        ).scalars().all())

    out: Dict[str, dict] = {}
    for row in rows:
        got = out.get(row.batch_key)
        if got is None:
            if len(out) >= limit:
                continue
            got = out[row.batch_key] = {
                "batch_key": row.batch_key,
                "kind": row.kind,
                "kind_label": KIND_LABELS.get(row.kind, row.kind),
                "day": row.happened_at or "",
                "at": row.created_at or "",
                "companies": row.companies,
                "company_count": row.company_count,
                "rows": 0,
                "undone": 0,
            }
        got["rows"] += 1
        if row.undone_at:
            got["undone"] += 1
    for got in out.values():
        # 한 판이 **반쯤 되돌려질 수 있다** — 한 사람 되돌리기(`rows_of` 의
        # `contact_id`)가 그 길이다. 다 되돌린 판만 `되돌림` 이고, 반쯤이면
        # 남은 줄을 되돌릴 단추가 그대로 서야 한다(화면은 `undone` 을 읽어
        # `3줄 중 1줄 되돌림` 으로 말한다 — `static/js/manual_send.js`).
        got["is_undone"] = got["undone"] >= got["rows"]
    return list(out.values())


# ─────────────────────────────────────────────────────────────────────────────
# ⑤ 합쳐 세기 — **세는 자리를 새로 만들지 않는다**
# ─────────────────────────────────────────────────────────────────────────────

def counted(db: Session, *, send_kinds: Sequence[str],
            since: Optional[str] = None, until: Optional[str] = None,
            user_id: Optional[int] = None) -> List[dict]:
    """합쳐 세는 **수동 기록**. ★ 합치는 판정은 여기 하나다.

    ## 왜 한 곳인가

    읽는 곳이 셋이다 — 업무 보고의 발송 표(`report._sends`) · 대시보드의
    `이번 주 보낸 건수` · 팀 현황의 `이번 달 발송`. 셋이 각자 "수동 기록은
    이렇게 센다" 를 적어 두면 한 곳이 반드시 빠진다. 이 저장소가
    `SEND_KINDS` 에서 이미 그렇게 데였다(`models.SEND_KINDS` — *"세는 곳이
    여럿이라 각자 걸러 두면 한 곳이 빠진다 — 실제로 네 곳이 빠져 있었다"*).

    ## 무엇을 돌려주나

    부르는 쪽이 **이미 쓰던 말**로 돌려준다 — `send_kind` 는 `SendJob.kind`,
    `stage` 는 `SendItem.stage` 다(`AS_SEND` 가 옮긴다). 그래서 부르는 쪽은
    자기가 앱 발송을 거르던 그 기준(`SEND_KINDS` · `SEND_REPORT_KINDS` ·
    `send_group_key`)을 **그대로** 쓰면서 이 줄들을 함께 센다.

    `since`/`until` 은 `happened_at`(보낸 날)로 본다 — 적은 날이 아니다.
    2주 전 것을 오늘 몰아 적어도 그 달 보고에 그 달 것으로 선다.

    되돌린 줄은 애초에 안 걸린다(`models._hide_undone_activities`).
    """
    wanted = {k for k, (send_kind, _stage) in AS_SEND.items()
              if send_kind in set(send_kinds)}
    if not wanted:
        return []

    stmt = (select(ContactActivity, VcContact.user_id)
            .join(VcContact, VcContact.id == ContactActivity.contact_id)
            .where(ContactActivity.source == SOURCE_MANUAL,
                   ContactActivity.kind.in_(sorted(wanted)),
                   ContactActivity.happened_at.isnot(None)))
    if user_id is not None:
        stmt = stmt.where(VcContact.user_id == user_id)
    if since:
        stmt = stmt.where(ContactActivity.happened_at >= since)
    if until:
        stmt = stmt.where(ContactActivity.happened_at <= until)

    out = []
    for act, owner_id in db.execute(stmt.order_by(ContactActivity.id)).all():
        send_kind, stage = AS_SEND[act.kind]
        out.append({
            "activity_id": act.id,
            "contact_id": act.contact_id,
            "user_id": owner_id,
            "day": act.happened_at,
            "kind": act.kind,
            "send_kind": send_kind,
            "stage": stage,
            "batch_key": act.batch_key or "",
            "companies": act.companies,
            "company_count": act.company_count,
        })
    return out
