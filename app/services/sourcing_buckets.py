"""딜 소싱 갈래(탭) 이름 — 고치는 곳 한 군데.

갈래는 표가 아니다. **`sourcing_contacts.bucket` 에 적힌 글자**이고, 원본 시트의
탭 이름이 줄마다 그대로 복사돼 있다. 갈래 목록은 그 글자를 모아 세운 것이다
(`routers/sourcing.py` 의 `buckets`).

그래서 이름을 바꾸는 일은 한 줄을 고치는 것이 아니라 **그 이름을 단 줄을 전부
옮기는 일**이다. 같은 글자가 세 곳에 따로 적혀 있다.

    sourcing_contacts.bucket                        그 갈래에 든 사람
    message_templates.name   (kind=sourcing_intro)  그 갈래로 나갈 문구
    template_choices.variant (kind=sourcing_intro)  그 갈래에 골라 둔 문구

(하나 더 — `template_apply_backups.variant` 는 그 갈래에 [모든 팀원에게 적용] 한
것을 되돌릴 버퍼다. 사람이 보는 자료는 아니지만 두고 가면 새 이름 갈래에서
[되돌리기] 가 사라지고, 옛 이름으로 되돌리면 선택을 못 찾아 전부 건너뛴다.)

문구 둘(처음 안내 `sourcing_intro` · 월간 리마인드 `sourcing_remind`)이 다
갈래 이름을 열쇠로 쓴다 — 어느 종류인지는 `template_pick.NAME_IS_A_BUCKET`
한 곳이 안다(`KINDS`). 리마인드만 두고 가면 새 이름 갈래의 리마인드는 뼈대로 나간다.

한 곳만 고치면 갈래가 **둘로 갈린다.** 사람은 새 이름 아래 있는데 문구는 옛
이름에 남아, 화면에는 갈래가 있는데 정작 발송은 뼈대 문구로 나간다 — 갈래마다
호칭·개수·범위가 다르니(`sourcing_msg`) 그건 결례가 되는 문구다.

투자컨설턴트에서 똑같은 사고를 겪고 마이그레이션으로 되돌린 적이 있다
(`0039_consulting_startup_tab` — 이름만 바꿔 유령 탭이 생겼다). 그래서 세 곳을
**한 번에** 옮긴다. 투자사 명단(`sheet_owner.rename`)·투자컨설턴트
(`consulting_sheets.rename`)와 같은 결이다.

**띄어쓰기만 다른 이름은 같은 갈래다**(`key`). 같은 탭이 `딜소싱` · `딜 소싱` ·
두 칸 공백으로 갈려 들어온다 — 글자 그대로 견주면 탭이 둘 서고, 투자사 관리
현황의 O 가 코드의 글자로 새 갈래를 만들었다. 그래서 **견줄 때만** 띄어쓰기를
모두 빼고, 저장된 글자는 고치지 않는다. 새 줄은 그 갈래가 이미 쓰는 글자로
적는다(`label_of`). 갈래를 견주는 자리는 모두 여기 함수를 지난다.

**갈래 이름은 문구를 고르는 열쇠이기도 하다.** `sourcing_msg` 가 이름에 든 말
('대표' · '시리즈 a' · 'm&a' …)로 호칭과 개수와 범위를 읽는다. 이름을 바꾸면
그 판단도 따라 바뀐다 — 옮기는 것과 달리 막을 수는 없으니, 화면에서 미리
보여 준다(`routers/sourcing.py`).
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import (MessageTemplate, SourcingContact, SourcingTab,
                      TemplateApplyBackup, TemplateChoice)
from . import sourcing_msg, template_pick

#: 갈래 이름을 열쇠로 쓰는 문구 종류 — 처음 안내 · 월간 리마인드.
KINDS = tuple(sorted(template_pick.NAME_IS_A_BUCKET))

#: 갈래 이름 길이 한도. 명단 이름(`sheet_owner`)과 같은 값이다.
MAX_LABEL = 80
#: [+ 탭 추가]로 새로 만드는 탭 이름 한도 — 탭 줄 · 시트 이름에 들 만큼.
NEW_MAX = 40


class RenameError(Exception):
    """이름을 바꾸거나 새로 만들 수 없는 까닭. 화면에 그대로 띄운다."""


def normalize_label(value: Optional[str]) -> str:
    """앞뒤 공백만 다듬는다.

    **가운데 공백은 건드리지 않는다.** 원본 시트의 탭 이름에는 두 칸짜리 공백이
    그대로 있고(`딜 소싱  참여 투자사 대표`), 그 글자가 곧 줄들이 달고 있는
    값이다 — 여기서 정리하면 옮기지 않은 줄과 어긋난다.
    """
    return (value or "").strip()[:MAX_LABEL]


def key(name: Optional[str]) -> str:
    """갈래를 견줄 열쇠 — **띄어쓰기를 모두 뺀** 글자.

    한 칸으로 줄이기만 해서는 `딜소싱` 과 `딜 소싱` 이 같아지지 않는다. 대소문자는
    그대로 본다 — 띄어쓰기만 다른 것이 같은 갈래다.
    """
    return re.sub(r"\s+", "", name or "")


def same(a: Optional[str], b: Optional[str]) -> bool:
    """두 이름이 같은 갈래인가(`key`)."""
    return key(a) == key(b)


def _made(db: Session) -> List[str]:
    """[+ 탭 추가]로 만든 탭 이름(`SourcingTab`) — 만든 차례."""
    return list(db.execute(select(SourcingTab.name).order_by(SourcingTab.id)).scalars())


def names(db: Session) -> List[str]:
    """지금 쓰이고 있는 갈래 이름(저장된 글자 그대로) — 사람이 든 것과 만든 탭."""
    used = [b for b in db.execute(
        select(SourcingContact.bucket).group_by(SourcingContact.bucket)
    ).scalars().all() if b]
    return used + [n for n in _made(db) if n not in used]


def groups(db: Session) -> List[dict]:
    """갈래 목록 — 띄어쓰기만 다른 글자는 **한 갈래**로 묶는다.

    `[{"label": 부를 이름, "variants": [저장된 글자…], "count": 줄 수, "pos": 차례}]`.
    부를 이름은 **줄이 가장 많은 글자**다(같으면 시트에서 앞선 것, 그다음 글자 순)
    — 시트에서 통째로 들어온 글자가 이기고, 한두 줄 엇나간 글자가 탭 이름을
    흔들지 않는다. 새 줄도 이 글자로 적으므로(`label_of`) 이름이 굳어진다.
    """
    by_key: Dict[str, list] = {}
    for bucket, n, pos in db.execute(
        select(SourcingContact.bucket, func.count(), func.min(SourcingContact.position))
        .group_by(SourcingContact.bucket)
    ).all():
        by_key.setdefault(key(bucket), []).append((-n, pos or 0, bucket))
    out: Dict[str, dict] = {}
    for k, found in by_key.items():
        found.sort()
        out[k] = {"label": found[0][2], "variants": [b for _n, _p, b in found],
                  "count": -sum(n for n, _p, _b in found),
                  "pos": min(p for _n, p, _b in found)}
    # 만든 탭은 사람이 없어도 서고, 시트에서 온 탭들 **뒤에** 만든 차례로 선다 — 사람을
    # 넣어도 그 자리다(새 줄의 `position` 은 1 부터라 줄로 세우면 맨 앞으로 뛴다).
    last = max((g["pos"] for g in out.values()), default=0)
    for i, name in enumerate(_made(db), start=1):
        out.setdefault(key(name), {"label": name, "variants": [], "count": 0})["pos"] = last + i
    return list(out.values())


def variants(db: Session, *labels: str) -> List[str]:
    """이 이름(들)과 띄어쓰기만 다른 **저장된 글자** 전부 — 질의의 `in_` 에 쓴다."""
    want = {key(label) for label in labels}
    return [b for b in names(db) if key(b) in want]


def label_of(db: Session, name: str) -> str:
    """이 이름의 갈래가 **쓰고 있는 글자** — 탭에 서는 이름이자 새 줄에 적을 글자.
    그 갈래에 아직 사람이 없으면 받은 이름 그대로다."""
    return next((g["label"] for g in groups(db) if same(g["label"], name)), name)


def label_in_use(db: Session, label: str, ignore: Optional[str] = None) -> bool:
    """이 이름을 이미 쓰고 있는가 — **세 곳을 다 보고**, 띄어쓰기만 달라도 쓰는 것이다.

    사람이 한 명도 없는 갈래여도 문구나 골라 둔 것이 남아 있을 수 있다. 그 이름
    으로 바꾸면 `template_choices` 의 (사람 · 종류 · 갈래) 유일 조건에 걸려
    옮기다 말고 터진다. 옮기기 전에 막는 편이 낫다. 띄어쓰기만 다른 이름이면
    두 갈래가 한 탭으로 합쳐진다(`key`).
    """
    if not label or same(label, ignore):
        return False
    if variants(db, label):
        return True
    taken = db.execute(
        select(MessageTemplate.name).where(MessageTemplate.kind.in_(KINDS))
    ).scalars().all() + db.execute(
        select(TemplateChoice.variant).where(TemplateChoice.kind.in_(KINDS))
    ).scalars().all()
    return any(same(t, label) for t in taken if t)


def rename(db: Session, before: str, after: str) -> int:
    """갈래 이름을 바꾸고 **그 이름을 단 줄을 전부 데려간다.**

    옮긴 줄 수를 돌려준다. `db.commit()` 은 부르는 쪽이 한다 — 세 표를 옮기다
    한 곳에서 막히면 통째로 되돌려야 한다.
    """
    before, after = (before or "").strip(), normalize_label(after)
    if not before or not after or before == after:
        return 0
    stored = variants(db, before)
    if not stored:
        raise RenameError(f"없는 갈래입니다: {before}")
    # 투자사 관리 현황과 이어진 갈래(셋 — `sourcing_sync.BRANCHES`)는 **이름이 곧
    # 잇는 열쇠**다. 바꾸면 그쪽 `딜 소싱` 칸에서 그 갈래가 통째로 빠지고, 다음
    # 체크는 옛 이름의 새 갈래(유령 탭)를 만든다.
    from . import sourcing_sync      # noqa: PLC0415 — 서로 참조한다

    if any(same(before, bucket) for bucket in sourcing_sync.SYNC_BUCKETS):
        raise RenameError(
            f"'{before}' 은 투자사 관리 현황의 `{sourcing_sync.COLUMN_LABEL}` 칸과 "
            "이어진 갈래라 이름을 바꿀 수 없습니다")
    if sourcing_sync.branch_of(after) is not None:
        # 거꾸로 — 다른 갈래를 잇는 갈래의 이름(짧은 이름 `M&A` 포함)으로 바꾸면 그 줄이
        # 잇는 갈래로 읽힌다(`branch_of`). [+ 탭 추가]도 같은 이유로 막는다(`create`).
        raise RenameError(
            f"'{after}' 은 투자사 관리 현황과 잇는 갈래 이름이라 쓸 수 없습니다")
    if label_in_use(db, after, ignore=before):
        raise RenameError(f"이미 쓰고 있는 이름입니다: {after}")
    for tab in db.execute(select(SourcingTab)).scalars():
        if same(tab.name, before):
            tab.name = after

    # 탭 하나에 묶인 **글자 전부**를 데려간다 — 하나만 옮기면 남은 글자가 옛 이름
    # 탭으로 남는다(`groups`).
    moved = 0
    for row in db.execute(
        select(SourcingContact).where(SourcingContact.bucket.in_(stored))
    ).scalars():
        row.bucket = after
        moved += 1
    # 문구와 '골라 둔 것' 도 같은 글자로 이어져 있다. 두고 가면 새 이름 갈래는
    # 문구가 없는 갈래가 되어, 뼈대 문구로 나간다.
    for tpl in db.execute(
        select(MessageTemplate).where(MessageTemplate.kind.in_(KINDS))
    ).scalars():
        if same(tpl.name, before):
            tpl.name = after
    # 골라 둔 것은 (사람 · 종류)마다 하나만 데려간다 — 띄어쓰기만 다른 글자에 하나씩
    # 있으면 읽히던 것(`template_pick.chosen_id` — 먼저 것)만 남기고 지운다. 둘 다
    # 옮기면 (사람 · 종류 · 갈래) 유일 조건에 걸린다.
    # **지우기를 먼저 DB 에 적고 옮긴다.** flush 는 UPDATE 를 DELETE 보다 먼저 낸다 —
    # 띄어쓰기만 다른 글자로 바꾸면(`M&A  찾는` → `M&A 찾는`) 옮기는 줄이 아직 안 지운
    # 줄과 같은 글자가 되어 유일 조건에 걸렸다(PR #311 리뷰).
    kept, moving = set(), []
    for choice in db.execute(
        select(TemplateChoice).where(TemplateChoice.kind.in_(KINDS))
        .order_by(TemplateChoice.id)
    ).scalars().all():
        if not same(choice.variant, before):
            continue
        if (choice.user_id, choice.kind) in kept:
            db.delete(choice)
            continue
        kept.add((choice.user_id, choice.kind))
        moving.append(choice)
    db.flush()
    for choice in moving:
        choice.variant = after
    for backup in db.execute(
        select(TemplateApplyBackup).where(TemplateApplyBackup.kind.in_(KINDS))
    ).scalars():
        if same(backup.variant, before):
            backup.variant = after
    db.flush()
    return moved


def create(db: Session, name: Optional[str]) -> str:
    """[+ 탭 추가] — 사람이 없는 새 갈래(탭)를 만든다. 만든 이름을 돌려준다.

    앞뒤 공백만 떼고(가운데는 그대로 — `normalize_label`) `NEW_MAX` 자까지. 띄어쓰기만
    다른 이름이 이미 있으면(사람 · 문구 · 골라 둔 것 · 만든 탭 — `label_in_use`) 막는다.
    투자사 관리 현황과 잇는 갈래 이름(짧은 이름 `M&A` 포함 — `sourcing_sync.branch_of`)과
    `전체` 탭 이름도 막는다 — 그 이름의 줄이 잇는 갈래로 읽히거나 `전체` 탭과 겹친다.
    `db.commit()` 은 부르는 쪽이 한다."""
    from . import sourcing_sync      # noqa: PLC0415 — 서로 참조한다

    label = (name or "").strip()
    if not label:
        raise RenameError("탭 이름을 입력하세요")
    if len(label) > NEW_MAX:
        raise RenameError(f"탭 이름은 {NEW_MAX}자까지입니다")
    if key(label).lower() in ("all", "전체"):
        raise RenameError("'전체' 는 모든 갈래를 함께 보는 탭이라 이름으로 쓸 수 없습니다")
    if sourcing_sync.branch_of(label) is not None:
        raise RenameError(
            f"'{label}' 은 투자사 관리 현황과 잇는 갈래 이름이라 새 탭으로 만들 수 없습니다")
    if label_in_use(db, label):
        raise RenameError(f"이미 있는 탭입니다(띄어쓰기만 달라도 같은 탭): {label}")
    db.add(SourcingTab(name=label))
    db.flush()
    return label


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
