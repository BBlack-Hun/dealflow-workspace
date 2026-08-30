"""명단(시트) — 투자사 풀과 내 명단.

시트가 나뉘어 있던 방식을 그대로 옮긴다. 두 종류가 있다.

- **투자사 풀**: 확보해 둔 투자사 명단(150명·98명·30명 …). 분류 단위일 뿐
  누구의 담당도 아니다. 여기서 사람을 **할당**해 자기 명단을 만든다.
- **내 명단**: 풀에서 할당받아 내가 딜소개를 보내는 사람들.

대시보드의 '내 투자사'는 **내 명단**만 센다. 풀까지 세면 팀이 확보한 전체
인원이 내 담당처럼 보인다 — 실제로 한 사람의 대시보드에 333명이 잡혔다
(본인 담당은 126명).

한 사람이 풀과 내 명단에 함께 있으면(실제로 113명이 그렇다) **내 명단 쪽이
이긴다**. 그 사람에게 딜소개를 보내는 것은 내 명단 쪽 일이기 때문이다.

**딜 소개를 어느 명단으로 보내는지도 명단이 정한다**(`SheetOwner.is_deal_list`).
발송 대상을 "연결이 끝난 사람" 으로 잡아 두었더니, 딜 소개 명단에 올린 적이
없는 풀 사람까지 목록에 떴다 — 아래 `is_deal_list` 와 `recipients` 참고.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Set

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import SheetOwner, User, VcContact

# 시트에서 오지 않은 담당자
MANUAL_SHEET = "직접 추가"


def labels_of(value: Optional[str]) -> List[str]:
    """담당자 한 명이 속한 명단들. 임포트마다 시트 이름이 누적된다."""
    labels = [x.strip() for x in (value or "").split(",") if x.strip()]
    return labels or [MANUAL_SHEET]


# 명단 종류. 담당이 정해져 있으면 누군가의 명단, 아니면 아직 풀이다.
KIND_ASSIGNED = "assigned"
KIND_POOL = "pool"

KIND_LABELS = {KIND_ASSIGNED: "담당 명단", KIND_POOL: "투자사 풀"}


def kind_of(user_id: Optional[int]) -> str:
    return KIND_ASSIGNED if user_id else KIND_POOL


def owner_map(db: Session) -> Dict[str, Optional[int]]:
    """{명단 이름: 할당받은 계정 id 또는 None(풀)}."""
    return {
        row.label: row.user_id
        for row in db.execute(select(SheetOwner)).scalars().all()
    }


# ── 투자사로 세지 않는 명단 ─────────────────────────────────────────────────
#
# 명단이라고 다 투자사는 아니다. 스타트업 리마인드 명단처럼 **같은 표에 얹혀
# 있을 뿐 투자사가 아닌** 줄이 섞이면, 투자사 수가 부풀고(전체 306명에 32명이
# 함께 세어졌다) 딜소개 발송 대상 목록에도 같이 뜬다.
#
# **이름으로 거르지 않는다.** `if 이름 == "…"` 를 심으면 다음 명단에서 또
# 심어야 하고, 심는 것을 잊은 화면만 조용히 틀린 수를 보여 준다. 화면에서
# 사람이 켜고 끄는 값(`SheetOwner.is_hidden`)만 본다.
#
# 세는 곳이 열대여섯 군데다. 그래서 판정을 여기 한 번만 적고 모두가 부른다 —
# 예전에 투자사 관리 현황이 117명, 대시보드가 123명이던 사고가 판정을 두 벌로
# 적어 둔 탓이었다.

def hidden_labels(db: Session) -> Set[str]:
    """투자사로 세지 않기로 한 명단 이름들."""
    return {
        row.label
        for row in db.execute(select(SheetOwner)).scalars().all()
        if row.is_hidden
    }


def is_investor(contact: VcContact, hidden: Set[str]) -> bool:
    """이 사람을 투자사로 세는가.

    **감춘 명단에만 있을 때** 빠진다. 한 사람이 여러 명단에 겹쳐 있으면(실제로
    126명이 그렇다) 살아 있는 명단 쪽이 이긴다 — 감춘 명단에 이름이 한 번
    올랐다고 진짜 투자사가 사라지면 안 된다.

    줄 단위로 감춘 사람(`VcContact.is_hidden`)도 빠진다. 표에서 안 보이는
    사람이 수에는 들어가 있으면, 세어 보고 목록에서 찾을 수가 없다.
    """
    if contact.is_hidden:
        return False
    return any(label not in hidden for label in labels_of(contact.source_sheet))


def investors(db: Session, contacts: List[VcContact]) -> List[VcContact]:
    """투자사로 세는 사람만 남긴다. **세거나 보내는 곳은 모두 이것을 지난다.**"""
    hidden = hidden_labels(db)
    return [c for c in contacts if is_investor(c, hidden)]


def my_labels(db: Session, user: User) -> Set[str]:
    """내가 할당받은 명단들. 직접 추가한 담당자는 언제나 내 것이다."""
    mapping = owner_map(db)
    mine = {label for label, uid in mapping.items() if uid == user.id}
    mine.add(MANUAL_SHEET)
    return mine


def is_mine(contact: VcContact, mine: Set[str]) -> bool:
    return any(label in mine for label in labels_of(contact.source_sheet))


def my_contacts(db: Session, user: User) -> List[VcContact]:
    """내 명단에 있는 담당자만. 대시보드·후속의 '내 담당' 기준이다.

    풀에만 있는 사람은 아직 내 담당이 아니다 — 할당해야 내 것이 된다.
    투자사로 세지 않기로 한 명단(`is_investor`)은 여기서 빠진다 — 이 함수를
    지나는 화면이 열 곳이 넘어서, 각자 걸러 두면 한 곳만 다른 수가 나온다.
    """
    mine = my_labels(db, user)
    hidden = hidden_labels(db)
    rows = db.execute(
        select(VcContact).where(VcContact.user_id == user.id)
    ).scalars().all()
    return [c for c in rows if is_mine(c, mine) and is_investor(c, hidden)]


# ── 누가 대상인가 ───────────────────────────────────────────────────────────
#
# **판정은 여기 하나뿐이다.** 딜 제안 관리(`routers/pages.py` 의 `deals_page`)와
# 투자사 관리 현황(`routers/contacts.py` 의 `contact_rows`)이 각자 질의를 적어
# 두어서, 같은 사람을 두고 두 화면이 서로 다른 수를 냈다 — 이 저장소가 반복해
# 당한 부류다(투자사 117명·123명, 좌측 메뉴 목록과 라우터 목록, 컨설턴트 줄에
# `막힘` 오표시, 관리자가 보는데 못 고치던 줄). 두 화면이 아래 함수를 읽으면
# 조건이 하나 붙어도 같이 움직인다. 대시보드의 `연결 진행 중인 명단`
# (`services/dashboard.py`)도 같은 판정을 읽는다.
#
# **문은 둘이고 뜻이 다르다.**
#
#     ① 이 명단인가   `on_deal_list` — 딜 소개를 **보내기로 한 명단**인가.
#                     모집단을 정한다. 명단 밖 사람은 아예 목록에 안 뜬다.
#     ② 지금 보낼 수 있나  `can_send_to` — 카톡방 연결이 끝났는가.
#                     명단 안이어도 방이 없으면 못 보낸다.
#
# 예전에는 ② 하나만 문이었다. 그래서 딜 소개 명단에 올린 적도 없는 **투자사
# 풀** 사람이 연결만 됐다는 이유로 발송 목록에 떴다(실데이터 142명 중 17명).
# 발송은 되돌릴 수 없는 일이라, 모집단을 넓게 잡아 두고 상태로 거르는 것보다
# **어느 명단으로 보내기로 했는지**를 먼저 묻는 편이 맞다.
#
# 두 화면의 수는 **원래 다르다.** 투자사 관리 현황은 `내가 맡은 사람`이고 딜
# 제안 관리는 `이 명단에서 지금 보낼 수 있는 사람`이다. 그 차이를 감추지 않고
# `recipient_counts` 로 내놓아 화면이 "명단 N명 중 M명 · 명단 밖 K명" 이라고
# 적게 한다 — 수가 다른 것보다 **왜 다른지 화면이 말하지 않는 것**이 문제였다.


def is_deal_list(row: Optional[SheetOwner]) -> bool:
    """이 명단으로 딜 소개를 보내는가. **명단 이름을 보지 않는다.**

    `SheetOwner.is_deal_list` 가 비어 있으면(= 아직 사람이 정하지 않았으면)
    **할당 여부를 따른다.** 이 모듈 첫 줄의 정의가 이미 그렇다 — "내 명단은
    풀에서 할당받아 **내가 딜소개를 보내는** 사람들". 지어낸 기본값이 아니라
    이 앱이 원래 쓰던 뜻이다.

    기본값을 이렇게 두는 이유는 **조용히 빠지는 쪽이 더 위험**해서다. 명단이
    하나 늘었는데 표시하는 것을 잊으면, 원래 받아야 할 사람이 통째로 회차에서
    빠진다 — 화면은 멀쩡하고 아무도 눈치채지 못한다.

    감춘 명단(투자사로 안 세는 명단)은 언제나 아니다. 스타트업 리마인드 명단이
    발송 대상에 섞이면 투자사에게 보낼 문구가 스타트업에게 나간다.
    """
    if row is None:
        # 설정 줄이 아예 없는 이름이다(`직접 추가`, 임포트를 거치지 않은 줄).
        # 손으로 넣은 사람은 보내려고 넣은 사람이라 **뺄 근거가 없다** —
        # 풀이라고 확인된 명단만 뺀다.
        return True
    if row.is_hidden:
        return False
    if row.is_deal_list is None:
        return bool(row.user_id)
    return bool(row.is_deal_list)


def off_deal_labels(db: Session) -> Set[str]:
    """딜 소개를 **안 보내는** 명단 이름들(풀 · 사람이 끈 명단 · 감춘 명단).

    보내는 쪽이 아니라 **안 보내는 쪽을 모은다.** `is_investor` 가 감춘 명단을
    다루는 방식과 같은 이유다 — 설정 줄이 아예 없는 이름(`직접 추가`, 손으로
    넣은 줄)이 저절로 대상에 남는다. 보내는 쪽을 모으면 그런 이름이 목록에
    없어서 조용히 빠진다.
    """
    return {label for label, row in settings_map(db).items()
            if not is_deal_list(row)}


def on_deal_list(contact: VcContact, off: Set[str]) -> bool:
    """이 사람이 딜 소개 명단에 올라 있는가.

    한 사람이 풀과 딜 소개 명단에 겹쳐 있으면(실제로 113명이 그렇다) **명단
    쪽이 이긴다** — 풀에도 이름이 있다는 이유로 명단에 올린 사람이 빠지면
    안 된다. 줄 단위로 감춘 사람은 `is_investor` 가 이미 뺀다.
    """
    return any(label not in off for label in labels_of(contact.source_sheet))


def managed(db: Session, user: User, *, team_wide: bool = False,
            include_hidden: bool = False) -> List[VcContact]:
    """이 사람이 **맡고 있는 투자사** — 투자사 관리 현황이 세는 모집단.

    `team_wide` 는 관리자 전용이다. 켜 달라고 해도 권한 판정을 다시 본다
    (`deps.may_manage_team_contacts`) — 부르는 쪽이 저마다 `role == "admin"`
    을 들고 있으면 하나는 반드시 낡는다.

    `include_hidden` 은 투자사 관리 현황 화면 하나만 쓴다. 감춘 명단·감춘
    줄도 그 탭에서는 보여야 하기 때문이다(감추기는 지우기가 아니다).
    그 외에는 기본값 그대로 둔다 — 여기서 새면 세는 곳마다 수가 갈린다.

    정렬은 `그룹 → 이름`이다. 딜 제안 관리에 그룹 필터가 붙었으므로 같은
    그룹이 붙어 있어야 눈으로도 묶여 보인다.
    """
    from ..deps import may_manage_team_contacts   # deps → services 는 순환이 아니다

    stmt = select(VcContact).order_by(VcContact.group_name, VcContact.name)
    if not (team_wide and may_manage_team_contacts(user)):
        stmt = stmt.where(VcContact.user_id == user.id)
    rows = list(db.execute(stmt).scalars().all())
    return rows if include_hidden else investors(db, rows)


def can_send_to(contact: VcContact) -> bool:
    """지금 이 사람에게 문구를 보낼 수 있는가 — 카톡방 연결이 끝났는가.

    연결 전 명단(전화·초대 진행 중)이 발송 대상에 섞이면 **보낼 방도 없는
    사람에게 체크를 하게 된다.** 단계 이름은 임포트가 정한 것을 그대로 읽는다
    — 여기에 `"connected"` 를 또 적어 두면 단계가 하나 늘 때 한쪽만 고쳐진다.
    """
    from .sheet_import import STAGE_CONNECTED   # 순환 임포트라 함수 안에서

    return contact.connect_stage == STAGE_CONNECTED


def deal_list_contacts(db: Session, user: User) -> List[VcContact]:
    """**딜 소개를 보내기로 한 명단**에 올라 있는 내 담당자 — 발송의 모집단.

    딜 제안 관리의 목록도, 대시보드의 `연결 진행 중인 명단` 도 여기서 시작한다.
    두 화면이 각자 모집단을 고르던 동안 한쪽은 풀까지 세고 한쪽은 안 세어서,
    같은 사람을 두고 다른 수가 나왔다.

    여기까지는 **연결 상태를 보지 않는다.** 아직 연결 중인 사람도 이 명단
    사람이고, 대시보드는 바로 그 사람들을 보여 줘야 한다.
    """
    off = off_deal_labels(db)
    return [c for c in managed(db, user) if on_deal_list(c, off)]


def recipients(db: Session, user: User) -> List[VcContact]:
    """딜 제안 관리의 **대상 담당자**. 발송 화면이 목록으로 그리는 그 사람들이다.

    문 둘을 차례로 지난다 — **이 명단인가**(모집단) 그리고 **지금 보낼 수
    있는가**(카톡방 연결). 명단에 있어도 방이 없으면 여전히 못 보낸다.
    """
    return [c for c in deal_list_contacts(db, user) if can_send_to(c)]


def deal_list_names(db: Session, contacts: List[VcContact]) -> List[str]:
    """이 사람들이 실제로 올라 있는 딜 소개 명단 이름들.

    화면이 "어느 명단 기준인지" 를 이름으로 적을 수 있어야, 기준이 또 어긋났을
    때 쓰는 사람이 먼저 알아챈다. **인원이 많은 명단부터** 둔다.
    """
    off = off_deal_labels(db)
    counted: Dict[str, int] = {}
    for c in contacts:
        for label in labels_of(c.source_sheet):
            if label not in off:
                counted[label] = counted.get(label, 0) + 1
    return [k for k, _ in sorted(counted.items(), key=lambda kv: (-kv[1], kv[0]))]


def recipient_counts(db: Session, user: User, *,
                     team_wide: bool = False) -> dict:
    """명단 N명 중 보낼 수 있는 M명 — 화면이 그 차이를 드러내는 데 쓴다.

    수만 다르고 이유가 안 적혀 있으면 쓰는 사람은 어느 쪽이 고장인지 알 수
    없다. 남은 사람이 **어느 단계에서 막혀 있는지**까지 함께 돌려준다.

    **명단 밖 인원(`off_list`)을 반드시 함께 내놓는다.** 이 변경으로 발송
    대상이 줄었는데(실데이터 142 → 125), 줄어든 것이 화면에 안 적히면 명단을
    새로 하나 받아 표시하는 것을 잊었을 때 그 사람들이 **조용히** 빠진다 —
    회차가 통째로 잘못 나가는 길이다. 명단 밖 수가 늘면 눈에 띈다.

    `team_wide` 는 관리자가 투자사 관리 현황에서 보는 팀 전체 수다. 발송은
    관리자여도 본인 담당분뿐이라(남의 방으로 문구가 실제로 나간다) 두 수가
    갈리는데, 그 사정도 화면이 말할 수 있어야 한다.
    """
    from .sheet_import import CONNECT_LABELS

    held = managed(db, user)
    off = off_deal_labels(db)
    mine = [c for c in held if on_deal_list(c, off)]
    sendable = [c for c in mine if can_send_to(c)]
    blocked: dict = {}
    for c in mine:
        if can_send_to(c):
            continue
        label = CONNECT_LABELS.get(c.connect_stage, c.connect_stage)
        blocked[label] = blocked.get(label, 0) + 1
    return {
        "managed": len(mine),
        # 맡고는 있지만 딜 소개 명단에는 없는 사람(대부분 아직 풀에 있는 사람).
        "held": len(held),
        "off_list": len(held) - len(mine),
        "lists": deal_list_names(db, mine),
        "sendable": len(sendable),
        "blocked": len(mine) - len(sendable),
        # 많은 단계부터 — "미착수 80명" 이 먼저 보여야 어디를 손대야 하는지 안다.
        "blocked_by_stage": [{"label": k, "count": v} for k, v in
                             sorted(blocked.items(), key=lambda kv: (-kv[1], kv[0]))],
        # 투자사 관리 현황이 보여 주는 수. 관리자만 본인 담당분과 다르다.
        "team_total": (len(managed(db, user, team_wide=True)) if team_wide
                       else len(held)),
        "team_wide": bool(team_wide),
    }


# ── 그룹 ────────────────────────────────────────────────────────────────────
#
# 투자사 관리 현황이 `그룹` 칸으로 거르는 그 값이다(`contacts.html` 의
# `data-f-group`). 딜 제안 관리에서도 같은 값으로 추릴 수 있어야 "그룹으로
# 묶어 둔 사람만 골라 보내기" 가 된다.


#: 그룹이 비어 있는 사람을 부르는 말. `app/static/js/filters.js` 의 `EMPTY`
#: 와 같은 글자여야 한다 — 투자사 관리 현황에서 `(비어 있음)` 으로 거른 것과
#: 딜 제안 관리에서 거른 것이 같은 사람이어야 하기 때문이다.
EMPTY_GROUP = "(비어 있음)"


def group_of(contact: VcContact) -> str:
    """이 담당자의 그룹. 안 정해 두었으면 빈 값이다 — **지어내지 않는다.**"""
    return (contact.group_name or "").strip()


def group_rows(contacts: List[VcContact]) -> List[dict]:
    """{이름, 인원} 목록. 필터 단추에 인원을 함께 적으려고.

    그룹이 없는 사람은 하나로 묶어 **마지막**에 둔다. 306명 중 대부분이
    그룹 없음이라, 그 덩어리가 위에 오면 정작 묶어 둔 그룹이 안 보인다.
    """
    counted: dict = {}
    for c in contacts:
        counted[group_of(c)] = counted.get(group_of(c), 0) + 1
    named = [{"name": k, "count": v} for k, v in counted.items() if k]
    named.sort(key=lambda g: (-g["count"], g["name"]))
    if counted.get(""):
        # 라벨은 표 필터가 쓰는 말과 같아야 한다(`filters.js` 의 `EMPTY`) —
        # 화면마다 다른 말을 쓰면 같은 뜻인지 알 수 없다.
        named.append({"name": "", "count": counted[""], "label": EMPTY_GROUP})
    for g in named:
        g.setdefault("label", g["name"])
    return named


def ensure(db: Session, label: str, user_id: Optional[int] = None,
           assignee_name: Optional[str] = None) -> SheetOwner:
    """명단을 등록한다. 이미 있으면 할당을 **덮지 않는다**.

    시트를 다시 올렸다고 할당이 바뀌면, 명단을 한 번 올린 것만으로
    남의 담당이 넘어간다.
    """
    row = db.execute(
        select(SheetOwner).where(SheetOwner.label == label)
    ).scalars().first()
    if row is None:
        row = SheetOwner(label=label, user_id=user_id, assignee_name=assignee_name)
        db.add(row)
        db.flush()
    elif assignee_name and not row.assignee_name:
        row.assignee_name = assignee_name
    return row


def assign(db: Session, label: str, user_id: Optional[int]) -> SheetOwner:
    """명단을 팀원에게 할당한다(관리자). None 이면 다시 풀로 돌린다."""
    row = ensure(db, label)
    row.user_id = user_id
    db.flush()
    return row


def settings_map(db: Session) -> Dict[str, SheetOwner]:
    """{명단 이름: 그 명단의 설정 줄}. 배치·숨김을 한 번에 읽으려고."""
    return {row.label: row
            for row in db.execute(select(SheetOwner)).scalars().all()}


def layout_of(db: Session, label: str) -> str:
    """이 명단을 어떤 표로 보여 줄까. 정해 두지 않았으면 투자사 명함이다."""
    row = settings_map(db).get(label)
    return (row.layout if row and row.layout else "investor")


def sheet_rows(db: Session, contacts: List[VcContact]) -> List[dict]:
    """명단 목록 + 담당 + 인원. 화면의 탭과 관리 표에 함께 쓴다."""
    settings = settings_map(db)
    names = {
        u.id: u.name for u in db.execute(select(User)).scalars().all()
    }
    total: Dict[str, int] = {}
    connected: Dict[str, int] = {}
    # 줄 단위로 감춘 사람은 탭 건수에서도 빠져야 한다 — 탭에 32라고 적혀
    # 있는데 표에는 열여섯 줄이면 어느 쪽이 맞는지 알 수 없다.
    shown: Dict[str, int] = {}
    for c in contacts:
        for label in labels_of(c.source_sheet):
            total[label] = total.get(label, 0) + 1
            if not c.is_hidden:
                shown[label] = shown.get(label, 0) + 1
            if c.connect_stage == "connected":
                connected[label] = connected.get(label, 0) + 1

    out = []
    for label in sorted(total, key=lambda k: (-connected.get(k, 0), -total[k], k)):
        row = settings.get(label)
        uid = row.user_id if row else None
        out.append({
            "key": label,
            "label": label,
            "count": shown.get(label, 0),
            # 감춘 줄이 몇인지 탭에서 드러나야 한다. 안 드러나면 시트에서
            # 그랬듯 "없는 기업" 으로 읽힌다.
            "hidden_rows": total[label] - shown.get(label, 0),
            "connected": connected.get(label, 0),
            "owner_id": uid,
            "owner": names.get(uid, "") if uid else "",
            "kind": kind_of(uid),
            "kind_label": KIND_LABELS[kind_of(uid)],
            # 시트의 '담당자' 칸에 적힌 이름. 연결 작업을 한 사람이지 소유자가 아니다.
            "written_by": (row.assignee_name or "") if row else "",
            # 이 명단이 쓰는 표 배치와, 투자사로 세는지 여부.
            "layout": (row.layout if row and row.layout else "investor"),
            "is_hidden": bool(row.is_hidden) if row else False,
            # 이 명단으로 딜 소개를 보내는가 — 발송 대상의 모집단.
            "is_deal_list": is_deal_list(row),
            # 사람이 정한 값인가, 할당 여부에서 따라온 기본값인가. 화면이
            # "정해 두지 않았습니다" 를 구분해 말할 수 있어야 한다.
            "deal_list_set": bool(row is not None and row.is_deal_list is not None),
        })
    return out


def add_to_sheet(db: Session, contacts: List[VcContact], label: str,
                 user_id: int) -> int:
    """풀에 있는 담당자를 내 명단으로 **할당**한다.

    풀에서 빼지 않는다 — 풀은 확보해 둔 전체 명단이고, 거기서 뽑아 쓰는 것이지
    옮기는 것이 아니다. 그래서 출처에 내 명단 이름을 더한다.
    """
    moved = 0
    for contact in contacts:
        labels = labels_of(contact.source_sheet)
        if label in labels:
            continue
        if MANUAL_SHEET in labels:
            labels.remove(MANUAL_SHEET)
        contact.source_sheet = ",".join(labels + [label])
        contact.user_id = user_id
        moved += 1
    db.flush()
    return moved
