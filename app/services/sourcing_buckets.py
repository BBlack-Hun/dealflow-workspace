"""딜 소싱 갈래(탭) 이름 — 고치는 곳 한 군데.

갈래는 표가 아니다. **`sourcing_contacts.bucket` 에 적힌 글자**이고, 원본 시트의
탭 이름이 줄마다 그대로 복사돼 있다. 갈래 목록은 그 글자를 모아 세운 것이다
(`routers/sourcing.py` 의 `buckets`).

그래서 이름을 바꾸는 일은 한 줄을 고치는 것이 아니라 **그 이름을 단 줄을 전부
옮기는 일**이다. 같은 글자가 세 곳에 따로 적혀 있다.

    sourcing_contacts.bucket                        그 갈래에 든 사람
    message_templates.name   (kind=sourcing_intro)  그 갈래로 나갈 문구
    template_choices.variant (kind=sourcing_intro)  그 갈래에 골라 둔 문구

한 곳만 고치면 갈래가 **둘로 갈린다.** 사람은 새 이름 아래 있는데 문구는 옛
이름에 남아, 화면에는 갈래가 있는데 정작 발송은 뼈대 문구로 나간다 — 갈래마다
호칭·개수·범위가 다르니(`sourcing_msg`) 그건 결례가 되는 문구다.

투자컨설턴트에서 똑같은 사고를 겪고 마이그레이션으로 되돌린 적이 있다
(`0039_consulting_startup_tab` — 이름만 바꿔 유령 탭이 생겼다). 그래서 세 곳을
**한 번에** 옮긴다. 투자사 명단(`sheet_owner.rename`)·투자컨설턴트
(`consulting_sheets.rename`)와 같은 결이다.

**갈래 이름은 문구를 고르는 열쇠이기도 하다.** `sourcing_msg` 가 이름에 든 말
('대표' · '시리즈 a' · 'm&a' …)로 호칭과 개수와 범위를 읽는다. 이름을 바꾸면
그 판단도 따라 바뀐다 — 옮기는 것과 달리 막을 수는 없으니, 화면에서 미리
보여 준다(`routers/sourcing.py`).
"""
from __future__ import annotations

from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import MessageTemplate, SourcingContact, TemplateChoice
from . import sourcing_msg

#: 갈래 이름 길이 한도. 명단 이름(`sheet_owner`)과 같은 값이다.
MAX_LABEL = 80


class RenameError(Exception):
    """이름을 바꿀 수 없는 까닭. 화면에 그대로 띄운다."""


def normalize_label(value: Optional[str]) -> str:
    """앞뒤 공백만 다듬는다.

    **가운데 공백은 건드리지 않는다.** 원본 시트의 탭 이름에는 두 칸짜리 공백이
    그대로 있고(`딜 소싱  참여 투자사 대표`), 그 글자가 곧 줄들이 달고 있는
    값이다 — 여기서 정리하면 옮기지 않은 줄과 어긋난다.
    """
    return (value or "").strip()[:MAX_LABEL]


def names(db: Session) -> List[str]:
    """지금 쓰이고 있는 갈래 이름. 사람이 든 것만 센다."""
    return [b for b in db.execute(
        select(SourcingContact.bucket).group_by(SourcingContact.bucket)
    ).scalars().all() if b]


def label_in_use(db: Session, label: str, ignore: Optional[str] = None) -> bool:
    """이 이름을 이미 쓰고 있는가 — **세 곳을 다 본다.**

    사람이 한 명도 없는 갈래여도 문구나 골라 둔 것이 남아 있을 수 있다. 그 이름
    으로 바꾸면 `template_choices` 의 (사람 · 종류 · 갈래) 유일 조건에 걸려
    옮기다 말고 터진다. 옮기기 전에 막는 편이 낫다.
    """
    if not label or label == ignore:
        return False
    if db.execute(
        select(SourcingContact.id)
        .where(SourcingContact.bucket == label).limit(1)
    ).first():
        return True
    if db.execute(
        select(MessageTemplate.id)
        .where(MessageTemplate.kind == sourcing_msg.KIND,
               MessageTemplate.name == label).limit(1)
    ).first():
        return True
    return bool(db.execute(
        select(TemplateChoice.id)
        .where(TemplateChoice.kind == sourcing_msg.KIND,
               TemplateChoice.variant == label).limit(1)
    ).first())


def rename(db: Session, before: str, after: str) -> int:
    """갈래 이름을 바꾸고 **그 이름을 단 줄을 전부 데려간다.**

    옮긴 줄 수를 돌려준다. `db.commit()` 은 부르는 쪽이 한다 — 세 표를 옮기다
    한 곳에서 막히면 통째로 되돌려야 한다.
    """
    before, after = (before or "").strip(), normalize_label(after)
    if not before or not after or before == after:
        return 0
    if before not in names(db):
        raise RenameError(f"없는 갈래입니다: {before}")
    if label_in_use(db, after, ignore=before):
        raise RenameError(f"이미 쓰고 있는 이름입니다: {after}")

    moved = 0
    for row in db.execute(
        select(SourcingContact).where(SourcingContact.bucket == before)
    ).scalars():
        row.bucket = after
        moved += 1
    # 문구와 '골라 둔 것' 도 같은 글자로 이어져 있다. 두고 가면 새 이름 갈래는
    # 문구가 없는 갈래가 되어, 뼈대 문구로 나간다.
    for tpl in db.execute(
        select(MessageTemplate).where(MessageTemplate.kind == sourcing_msg.KIND,
                                      MessageTemplate.name == before)
    ).scalars():
        tpl.name = after
    for choice in db.execute(
        select(TemplateChoice).where(TemplateChoice.kind == sourcing_msg.KIND,
                                     TemplateChoice.variant == before)
    ).scalars():
        choice.variant = after
    db.flush()
    return moved


def message_shape(bucket: str) -> dict:
    """이 이름으로 부르면 문구가 어떤 모양이 되는가.

    갈래 이름은 옮기기만 하는 글자가 아니라 **문구를 정하는 값**이다
    (`sourcing_msg` 가 이름에 든 말로 읽는다). 이름을 바꾸면 호칭이 '대표님'
    에서 '심사역님' 으로 바뀌거나 찾는 범위 줄이 사라질 수 있는데, 그건 옮기기
    로 막을 수 있는 게 아니라 **바꾸는 사람이 알고 바꿔야** 하는 것이다.
    """
    return {
        "honorific": sourcing_msg.honorific(bucket),
        "deal_count": sourcing_msg.deal_count(bucket),
        "scope": sourcing_msg.scope(bucket),
    }
