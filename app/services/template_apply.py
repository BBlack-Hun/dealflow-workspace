"""관리자 문구 → 팀 전체 — [모든 팀원에게 적용] 과 그 [되돌리기] 가 사는 한 곳.

왜 있나
-------
관리자가 팀 기본 문구를 고쳐도 팀원의 발송은 그대로였다. 문구를 고르는 규칙이
**고른 것 > 내 것 > 팀 것(하나뿐일 때)** 이라(`template_pick.pick`), 각자 골라 둔
것이나 만들어 둔 내 문구가 팀 문구보다 먼저 나간다. 그 규칙은 옳다 — 다만
"이번에는 모두 이 문구로" 가 필요할 때 사람마다 화면에 들어가 다시 고르라고 할
수는 없다. 그래서 관리자가 한 번에 덮는 길을 둔다.

무엇을 덮나 — 한 **자리**(종류 + 갈래)만
---------------------------------------
* 딜소개를 보내는 살아 있는 계정 **모두**(관리자 자신도)의 선택을 이 문구로
  바꾼다. 아직 아무것도 안 고른 사람에게도 선택을 만들어 준다 — 그래야 그 사람
  손에 내 문구가 있든 팀 문구가 여럿이든 이 문구가 나간다. 투자컨설턴트는 뺀다
  (`deps.sends_deals` — 보낼 문구가 없는 계정이다).
* 그 자리의 **개인 문구는 끈다**(`is_active=0`). 지우지 않는다 — 번호와 본문이
  남아 되돌릴 수 있고, 남의 문구를 끈 일이 수정 로그에 `켜짐 1→0` 으로 남는다
  (`edit_log.WATCHED["message_templates"]`). 끄지 않으면 선택을 지우는 순간
  (`template_pick.clear_choice`) 다시 내 문구가 앞선다.
* 같은 자리의 **다른 팀 문구는 그대로 둔다.** 팀 문구를 끄는 것은 관리자가 그
  문구를 직접 지우거나 고치는 일이고, 여기서는 선택만 이 문구를 가리키면 된다.
* 다른 자리(다른 갈래 · 다른 종류)는 건드리지 않는다.

나중에 들어온 사람은 선택이 없다. 그 사람은 `pick` 의 규칙대로 **내 것 > 팀
것(하나뿐일 때)** 를 탄다 — 그 자리에 팀 문구가 이것 하나면 이것이 나가고,
여럿이면 고르기 전까지 코드에 적힌 폴백이 나가며 문구 화면에 "아직 고르지
않았습니다" 가 뜬다. 적용이 앞으로 올 사람의 선택까지 미리 정해 두지 않는
까닭은 선택이 **사람에게 묶인 값**이기 때문이다 — 계정이 없는 사람의 줄을 세울
수 없고, '팀 기본' 이라는 칸을 따로 두면 고르는 규칙이 두 벌이 된다.

되돌리기
--------
덮기 **전에** `TemplateApplyBackup` 한 줄을 적는다(덮기 전의 선택 · 끈 문구).
되돌릴 때는 그 뒤에 바뀐 것은 건드리지 않는다 — 그 사이 사람이 다시 고른
선택, 주인이 지우거나 고치거나 이미 다시 켠 문구. 사람이 손으로 한 일을
되돌리기가 덮으면, 덮기를 되돌리려다 또 덮는 것이 된다.

**세는 함수와 하는 함수가 같다.** 화면이 확인창에 띄우는 숫자(`plan`)와 실제로
바꾸는 것(`apply`)이 같은 `plan` 을 지난다 — 둘이 따로 세면 "7명이 바뀐다" 고
물어 놓고 9명을 바꾸는 날이 온다.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import deps
from ..clock import now_iso
from ..models import MessageTemplate, TemplateApplyBackup, TemplateChoice, User
from . import template_pick

#: [모든 팀원에게 적용] 을 띄우는 종류 — 딜 소싱 제안(갈래마다)과 딜소개의
#: 인사말(첫 연락 · 재연락) · 안내문(딜소개). 모두가 **같은 말로** 나가야 하는
#: 글이라 관리자가 한 번에 맞출 일이 있다. 다른 종류로 넓힐 때는 여기 하나만
#: 고친다(화면 단추 · 라우터의 막기가 모두 이 목록을 읽는다).
KINDS = ("sourcing_intro", "opening_first", "opening_re", "closing_day1")


@dataclass
class Plan:
    """이 문구를 팀 전체에 적용하면 **무엇이 바뀌나** — 아직 아무것도 안 바꾼다."""

    template: MessageTemplate
    kind: str
    variant: str
    #: 선택이 이 문구로 바뀌는 사람과 그 전 선택 — `{"user_id", "template_id"}`.
    #: 전 선택이 없거나 이미 죽은 선택이었으면 `template_id` 가 None 이다.
    previous: List[dict] = field(default_factory=list)
    #: 꺼질 개인 문구.
    turn_off: List[MessageTemplate] = field(default_factory=list)

    @property
    def empty(self) -> bool:
        return not self.previous and not self.turn_off


def eligible(t: Optional[MessageTemplate]) -> bool:
    """팀 전체에 적용할 수 있는 문구인가 — 켜진 **팀** 문구이고 정해 둔 종류."""
    return (t is not None and t.user_id is None and t.is_active == 1
            and t.kind in KINDS)


def slot_of(t: MessageTemplate) -> Tuple[str, str]:
    """이 문구가 선 자리 — 갈래는 화면 값이 아니라 문구 자신에서 읽는다."""
    return t.kind, template_pick.variant_of(t.kind, t.name)


def _sig(t: MessageTemplate) -> str:
    """끌 때의 이름·본문 지문. 되돌릴 때 **그 뒤에 고쳤나**를 이것으로 본다.

    시각(`updated_at`)으로 보지 않는 이유: 초까지만 적혀서(`clock.now_iso`) 같은
    초 안에 고친 것을 못 가린다. 본문을 통째로 버퍼에 다시 적지 않으려고 지문만
    남긴다 — 본문은 문구 표에 그대로 있다.
    """
    raw = f"{t.name or ''}\x00{t.body or ''}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


def _choice(db: Session, user_id: int, kind: str,
            variant: str) -> Optional[TemplateChoice]:
    return db.execute(
        select(TemplateChoice)
        .where(TemplateChoice.user_id == user_id,
               TemplateChoice.kind == kind,
               TemplateChoice.variant == variant)
    ).scalars().first()


def plan(db: Session, t: MessageTemplate) -> Plan:
    """이 문구를 팀 전체에 적용하면 바뀔 것을 센다 — 화면의 확인창과 실제 적용이
    **같이 읽는다.**"""
    kind, variant = slot_of(t)
    out = Plan(template=t, kind=kind, variant=variant)

    # 그 자리의 켜진 개인 문구. 갈래는 이름에서 `variant_of` 로 읽는다 — 화면이
    # 문구를 자리별로 묶는 것(`templates_crud._section`)과 같은 판정이다.
    out.turn_off = [
        p for p in db.execute(
            select(MessageTemplate)
            .where(MessageTemplate.kind == kind,
                   MessageTemplate.user_id.is_not(None),
                   MessageTemplate.is_active == 1)
            .order_by(MessageTemplate.id)
        ).scalars()
        if template_pick.variant_of(kind, p.name) == variant]
    off_ids = {p.id for p in out.turn_off}

    choices = {c.user_id: c for c in db.execute(
        select(TemplateChoice)
        .where(TemplateChoice.kind == kind, TemplateChoice.variant == variant)
    ).scalars()}
    members = {u.id for u in db.execute(
        select(User).where(User.is_active == 1)).scalars() if deps.sends_deals(u)}
    # 꺼질 개인 문구를 골라 둔 사람이 위 목록 밖에 있을 수 있다(정지된 계정).
    # 그 선택을 두고 가면 **꺼진 문구를 가리키는 선택**이 남는다 — 그 사람도
    # 이 문구로 옮겨 두고, 되돌릴 때 함께 되돌린다.
    stranded = {uid for uid, c in choices.items() if c.template_id in off_ids}

    for uid in sorted(members | stranded):
        current = choices.get(uid)
        if current is not None and current.template_id == t.id:
            continue                      # 이미 이 문구 — 바뀌는 것이 없다
        before = None
        if current is not None and template_pick.usable(
                db.get(MessageTemplate, current.template_id), uid, kind, variant):
            before = current.template_id
        # 죽은 선택(지워졌거나 꺼진 문구)은 '고른 것 없음' 으로 적는다 — 그
        # 사람에게 실제로 나가던 것이 그것이고(`pick` 이 건너뛴다), 되돌릴 때
        # 죽은 선택을 다시 세우면 `prune` 이 곧바로 치운다.
        out.previous.append({"user_id": uid, "template_id": before})
    return out


def apply(db: Session, t: MessageTemplate,
          by: User) -> Tuple[Plan, Optional[TemplateApplyBackup]]:
    """팀 전체에 적용한다. 바뀔 것이 없으면 아무것도 적지 않고 백업도 None.

    `db.commit()` 은 부르는 쪽이 한다. 백업 · 끄기 · 선택이 한 번에 들어가야
    한다 — 덮기만 되고 백업이 안 남는 일이 없게.
    """
    p = plan(db, t)
    if p.empty:
        return p, None
    # **덮기 전에** 적는다 — 무엇을 덮는지는 덮은 뒤에는 알 수 없다.
    backup = TemplateApplyBackup(
        user_id=by.id, kind=p.kind, variant=p.variant, template_id=t.id,
        previous_json=json.dumps(p.previous, ensure_ascii=False),
        turned_off_json=json.dumps(
            [{"id": row.id, "sig": _sig(row)} for row in p.turn_off]))
    db.add(backup)
    db.flush()

    # 한 줄씩 ORM 으로 고친다 — 수정 로그(`edit_log`)가 flush 에서 남의 개인
    # 문구가 꺼진 것을 줄마다 읽는다. 한꺼번에 `update()` 하면 그 자리를 건너뛴다.
    for row in p.turn_off:
        row.is_active = 0
    for item in p.previous:
        template_pick.set_choice(db, item["user_id"], p.kind, t.id, variant=p.variant)
    db.flush()
    return p, backup


def latest(db: Session, kind: str, variant: str) -> Optional[TemplateApplyBackup]:
    """이 자리에서 **아직 되돌리지 않은 가장 최근** 적용.

    되돌리기는 이것 하나만 받는다. 둘을 잇달아 적용했으면 나중 것의 '전' 이
    먼저 것의 '후' 라, 먼저 것부터 되돌리면 나중 것이 남긴 선택과 안 맞아
    전부 건너뛴다 — 쌓인 차례의 거꾸로만 된다.
    """
    return db.execute(
        select(TemplateApplyBackup)
        .where(TemplateApplyBackup.kind == kind,
               TemplateApplyBackup.variant == variant,
               TemplateApplyBackup.restored_at.is_(None))
        .order_by(TemplateApplyBackup.id.desc()).limit(1)
    ).scalars().first()


def counts(backup: TemplateApplyBackup) -> Tuple[int, int]:
    """(선택이 바뀐 사람 수, 끈 개인 문구 수) — 화면이 '무엇을 되돌리나' 에 쓴다."""
    return (len(json.loads(backup.previous_json or "[]")),
            len(json.loads(backup.turned_off_json or "[]")))


@dataclass
class Restored:
    choices: int = 0
    templates: int = 0
    #: 그 사이 바뀌어 건드리지 않은 것(선택 · 문구 합).
    skipped: int = 0


def restore(db: Session, backup: TemplateApplyBackup) -> Restored:
    """적용 전으로 되돌린다 — **그 뒤에 바뀐 것은 건드리지 않는다.**

    차례가 있다. 끈 개인 문구를 먼저 되살리고, 그다음 선택을 돌린다 — 전 선택이
    그 개인 문구였으면 되살아난 뒤라야 고를 수 있는 문구로 보인다(`usable`).
    `db.commit()` 은 부르는 쪽이 한다.
    """
    done = Restored()
    kind, variant = backup.kind, backup.variant

    for item in json.loads(backup.turned_off_json or "[]"):
        row = db.get(MessageTemplate, item.get("id"))
        # 지워졌거나 · 이미 다시 켜졌거나 · 주인이 고쳤으면 그대로 둔다.
        if row is None or row.is_active == 1 or _sig(row) != item.get("sig"):
            done.skipped += 1
            continue
        row.is_active = 1
        done.templates += 1

    applied = db.get(MessageTemplate, backup.template_id)
    for item in json.loads(backup.previous_json or "[]"):
        uid, before = item.get("user_id"), item.get("template_id")
        current = _choice(db, uid, kind, variant)
        if current is None or current.template_id != backup.template_id:
            # 그 사이 다른 것을 골랐거나, 적용한 문구가 지워져 선택이 거둬졌다.
            done.skipped += 1
            continue
        if before is None:
            # 그때 고른 것이 없었다 — 다시 '내 것 > 팀 것' 규칙으로 돌아간다.
            db.delete(current)
            done.choices += 1
            continue
        if template_pick.usable(db.get(MessageTemplate, before), uid, kind, variant):
            current.template_id = before
            done.choices += 1
            continue
        # 전에 고른 문구를 이제는 고를 수 없다(지워졌거나 꺼졌다). 이 문구를
        # 그대로 둔다 — 다만 이 문구마저 죽었으면 선택을 거둔다. 죽은 선택을
        # 남기면 화면에는 "고름" 인데 다른 것이 나간다(`prune` 과 같은 까닭).
        done.skipped += 1
        if not template_pick.usable(applied, uid, kind, variant):
            db.delete(current)

    backup.restored_at = now_iso()
    db.flush()
    return done
