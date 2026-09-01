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

from ..models import ContactColumn, MonthlyColumnRun, SheetOwner, User, VcContact
from .monthly_columns import CONTACT

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


def blocked_stages(db: Session, rows: List[VcContact]) -> List[dict]:
    """딜 소개 명단에 있는데 **아직 못 보내는** 사람 — 단계별로, 누구인지까지.

    수와 이름이 **한 곳에서 나온다.** 수는 여기서 세고 이름은 화면이 따로
    고르게 두면, 둘이 갈리는 날 어느 쪽이 맞는지 알 수가 없다.

    **단계는 다섯이고 뜻이 두 갈래다**(`sheet_import.CONNECT_LABELS`).

        진행 중 · 미착수      아직 손이 필요하다. 연결을 이으면 대상이 된다.
        참여 안 함 · 방 나감  더 진행하지 않기로 끝났다. **아무리 기다려도
                              대상이 되지 않는다.**

    이 차이를 안 적으면 방만 다시 확인하면 될 줄 알고 움직이지 않는 수를 계속
    들여다보게 된다 — 실제로 "카톡방은 확인됐는데 왜 대상이 아니냐" 는 물음이
    여기서 나왔다. 방 확인(`room_verified`)과 연결 단계(`connect_stage`)는
    **따로 관리되는 값**이라, 방을 아무리 확인해도 이 수는 안 움직인다.

    `연결 완료` 는 여기 오지 않는다 — 그 사람들이 곧 발송 대상이다.
    """
    # 대시보드 → sheet_owner 방향이라 함수 안에서 가져온다. 주소를 여기서 다시
    # 조립하지 않는 이유는 `connect_href` 의 설명 그대로다.
    from .dashboard import connect_href, deal_sheet_scope
    from .sheet_import import CONNECT_DONE, CONNECT_LABELS

    # **세는 곳과 가는 곳의 모집단이 같아야 한다.** 여기서 세는 것은 딜 소개
    # 명단(125명)인데 링크를 `전체` 탭으로 보내면, 화면은 `미착수 4명` 이라고
    # 적어 놓고 눌러 가면 맡은 사람 전체의 미착수 84줄이 뜬다 — 대시보드가
    # 똑같이 당했던 자리다(패널 0명 → 화면 44줄).
    sheet = deal_sheet_scope(db, rows)

    grouped: Dict[str, List[VcContact]] = {}
    for c in rows:
        if can_send_to(c):
            continue
        grouped.setdefault(c.connect_stage or "", []).append(c)

    out = []
    for key, people in grouped.items():
        out.append({
            "key": key,
            # 화면에 쓸 한글 이름을 여기서 지어내지 않는다 — 임포트가 정한 것을
            # 그대로 읽는다. 모르는 값이 들어와도 **감추지 않는다**: 단계가 하나
            # 늘었는데 여기 이름이 없으면 그 사람들만 조용히 사라지는데, 빠진
            # 사람을 보이게 하려고 만든 자리에서 그러면 안 된다.
            "label": CONNECT_LABELS.get(key, key or "-"),
            "count": len(people),
            # 모르는 값은 끝난 갈래로 치지 않는다 — 할 일로 남겨 두는 쪽이 안전하다.
            "done": key in CONNECT_DONE,
            # 이름은 **전부** 준다. 앞의 몇 명만 세우고 나머지를 접으면 화면에
            # 안 뜨는 사람이 또 생긴다 — 그게 바로 고치려던 문제다. 화면에서는
            # 접어 두므로 자리를 차지하지도 않는다.
            #
            # 방 이름을 함께 싣는다. `방은 있는데 미착수` 가 눈에 보여야
            # "방을 확인했는데 왜 빠지냐" 는 물음이 화면에서 풀린다.
            "people": [{"id": c.id, "name": c.name, "firm": c.firm or "",
                        "room": c.kakao_room_name or "",
                        "href": f"/contacts?contact={c.id}"} for c in people],
            # 한 단계를 통째로 볼 곳. 필터 키와 값은 대시보드가 이미 쓰는 것을
            # 그대로 부른다 — 여기 손으로 적으면 라벨이 바뀔 때 한쪽만 낡는다.
            # 모르는 단계는 걸 값이 없다(라벨이 없으면 필터가 통째로 버린다) —
            # 0줄짜리 링크를 거느니 목록으로만 보낸다.
            "href": (connect_href(key, sheet) if key in CONNECT_LABELS
                     else "/contacts"),
        })
    # 끝난 갈래를 **뒤로** 둔다(대시보드가 `CONNECT_OPEN` → `CONNECT_DONE` 순으로
    # 세우는 것과 같은 이유 — 할 일이 먼저다). 그 안에서는 많은 순이다:
    # "미착수 80명" 이 먼저 보여야 어디를 손대야 하는지 안다.
    return sorted(out, key=lambda s: (s["done"], -s["count"], s["label"]))


def recipient_counts(db: Session, user: User, *,
                     team_wide: bool = False) -> dict:
    """명단 N명 중 보낼 수 있는 M명 — 화면이 그 차이를 드러내는 데 쓴다.

    수만 다르고 이유가 안 적혀 있으면 쓰는 사람은 어느 쪽이 고장인지 알 수
    없다. 남은 사람이 **어느 단계에서 막혀 있는지**, 그리고 **그게 누구인지**
    까지 함께 돌려준다(`blocked_by_stage`) — 이름을 못 보면 수만 알고 손은 못
    쓴다. 목록에 없는 사람은 화면에서 존재조차 확인할 길이 없기 때문이다.

    **단계 이름은 전부 여기를 지난다**(`sendable_label` · `blocked_by_stage` 의
    `label`). 화면이 `연결 완료` 같은 말을 손으로 적어 두면 임포트가 그 말을
    바꾸는 날 한쪽만 낡는다.

    **명단 밖 인원(`off_list`)을 반드시 함께 내놓는다.** 이 변경으로 발송
    대상이 줄었는데(실데이터 142 → 125), 줄어든 것이 화면에 안 적히면 명단을
    새로 하나 받아 표시하는 것을 잊었을 때 그 사람들이 **조용히** 빠진다 —
    회차가 통째로 잘못 나가는 길이다. 명단 밖 수가 늘면 눈에 띈다.

    `team_wide` 는 관리자가 투자사 관리 현황에서 보는 팀 전체 수다. 발송은
    관리자여도 본인 담당분뿐이라(남의 방으로 문구가 실제로 나간다) 두 수가
    갈리는데, 그 사정도 화면이 말할 수 있어야 한다.
    """
    from .sheet_import import CONNECT_LABELS, STAGE_CONNECTED

    held = managed(db, user)
    off = off_deal_labels(db)
    mine = [c for c in held if on_deal_list(c, off)]
    sendable = [c for c in mine if can_send_to(c)]
    return {
        "managed": len(mine),
        # 맡고는 있지만 딜 소개 명단에는 없는 사람(대부분 아직 풀에 있는 사람).
        "held": len(held),
        "off_list": len(held) - len(mine),
        "lists": deal_list_names(db, mine),
        "sendable": len(sendable),
        # 어느 단계가 되어야 보낼 수 있는지 화면이 **이름으로** 적을 수 있게.
        # 화면이 `연결 완료` 라고 손으로 적어 두면, 임포트가 그 말을 바꾸는 날
        # 투자사 관리 현황의 고르는 칸과 딜 제안 관리의 안내가 서로 다른 말을
        # 하게 된다 — 쓰는 사람은 없는 단계를 찾아 헤맨다.
        "sendable_label": CONNECT_LABELS[STAGE_CONNECTED],
        "blocked": len(mine) - len(sendable),
        # 단계별 수 **와 이름**. 화면이 "미착수 19명" 이라고만 적고 누구인지는
        # 안 적으면, 빠진 사람이 누구인지 알 길이 없어 손을 쓸 수가 없다.
        "blocked_by_stage": blocked_stages(db, mine),
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


# ── 명단 이름 바꾸기 ────────────────────────────────────────────────────────
#
# **이름이 곧 열쇠다.** 명단은 `SheetOwner` 줄 하나로 사는 것이 아니라, 이름을
# **문자열로 담고 있는 네 곳**으로 산다.
#
#     SheetOwner.label          이 명단의 설정(담당 · 배치 · 숨김 · 딜소개 표시)
#     VcContact.source_sheet    그 명단에 올라 있는 사람들 (쉼표로 이어 붙는다)
#     ContactColumn.sheet       그 명단의 달마다 늘어나는 칸
#     MonthlyColumnRun.scope    그 달 칸을 이미 만들었다는 표시
#
# 그래서 설정 줄만 고치면 **나머지 셋이 옛 이름에 남는다.** 사람은 어느 탭에도
# 안 뜨고(옛 이름의 유령 탭으로 갈린다), 달 칸은 통째로 사라진 것처럼 보이고,
# 사람이 일부러 지운 달 칸이 다음 요청에서 되살아난다. 투자컨설턴트 현황이
# 정확히 이 사고를 겪었고 마이그레이션으로 고쳐야 했다
# (`0039_consulting_startup_tab` · `services/consulting_sheets.rename`).
#
# 옮기는 자리를 **여기 하나**로 둔다. 화면(`/api/contacts/sheets/rename`)과
# 스크립트(`scripts/rename_sheets.py`)가 같은 것을 부른다 — 두 벌로 적으면
# 한쪽만 고쳐지는 날 그쪽으로 바꾼 명단만 조용히 갈라진다.


#: 명단 이름의 최대 길이. 화면 입력칸(`contacts.html` 의 `maxlength`)과 같은
#: 값이다. 자르는 자리를 여기 하나로 두는 이유: 저장할 때만 자르면 화면이 보낸
#: 이름과 저장된 이름이 달라져, 바꾸고 나서 **되돌아갈 탭 주소가 어긋난다** —
#: 방금 바꾼 탭 대신 없는 탭이 열린다.
MAX_LABEL = 80


def normalize_label(label: str) -> str:
    """명단 이름을 저장하는 모양 그대로. 부르는 쪽이 모두 이것을 지난다."""
    return (label or "").strip()[:MAX_LABEL]


class RenameError(ValueError):
    """이름을 바꿀 수 없는 이유. **사람에게 그대로 보여 줄 수 있는 문장**이다.

    화면은 이 문장을 그대로 띄우고 스크립트는 그대로 찍는다. 사유를 부르는
    쪽마다 따로 적으면 같은 거절이 화면과 명령에서 다른 말로 나온다.
    """


def label_in_use(db: Session, label: str, *, ignore: str = "") -> bool:
    """이 이름을 이미 쓰고 있는 명단이 있는가.

    **설정 줄만 보지 않는다.** 임포트를 거치지 않은 이름은 `SheetOwner` 줄 없이
    `source_sheet` 에만 있을 수 있고(`직접 추가`, 손으로 넣은 줄), 달 칸만 남은
    이름도 있다. 그런 이름으로 바꾸면 남의 줄과 **한 탭에 섞인다** — 섞이고 나면
    어느 줄이 원래 어느 명단 것이었는지 되돌릴 근거가 사라진다.
    """
    if not label or label == ignore:
        return False
    if db.execute(select(SheetOwner).where(SheetOwner.label == label)) \
            .scalars().first() is not None:
        return True
    if db.execute(select(ContactColumn).where(ContactColumn.sheet == label)) \
            .scalars().first() is not None:
        return True
    return any(label in labels_of(c.source_sheet)
               for c in db.execute(select(VcContact)).scalars())


def rename(db: Session, before: str, after: str) -> Optional[SheetOwner]:
    """명단 이름을 바꾸고 **그 이름을 담고 있던 것들을 같이 옮긴다.**

    바꿀 수 없으면 `RenameError` 를 낸다(위 설명 참고). 옮길 것이 없는 부름
    (빈 이름 · 같은 이름)은 조용히 지금 설정 줄을 돌려준다 — 화면의 [이름 저장]
    은 고치지 않고도 눌리는 단추라서, 안 바뀐 것을 실패로 알릴 일이 아니다.

    쉼표는 받지 않는다. `source_sheet` 가 **쉼표로 이어 붙인 목록**이라
    (한 사람이 여러 명단에 겹친다) 이름에 쉼표가 들어가면 그 명단이 두 개로
    쪼개져 읽힌다 — 줄은 그대로인데 탭만 둘로 갈라진다.
    """
    before, after = (before or "").strip(), normalize_label(after)
    if not before or not after or before == after:
        return db.execute(
            select(SheetOwner).where(SheetOwner.label == before)
        ).scalars().first()
    if "," in after:
        raise RenameError("명단 이름에는 쉼표를 쓸 수 없습니다")
    if label_in_use(db, after, ignore=before):
        raise RenameError(f"이미 쓰고 있는 이름입니다: {after}")

    # `source_sheet` 는 **조각 단위**로 바꾼다. 통째로 바꾸면 겹친 사람의 다른
    # 명단 이름까지 뭉개진다.
    for contact in db.execute(select(VcContact)).scalars():
        parts = labels_of(contact.source_sheet)
        if before in parts:
            contact.source_sheet = ",".join(
                after if p == before else p for p in parts)
    for column in db.execute(
        select(ContactColumn).where(ContactColumn.sheet == before)
    ).scalars():
        column.sheet = after
    # 달 표시는 **투자사 관리 현황 몫만** 옮긴다. 같은 표에 투자컨설턴트 몫도
    # 들어 있고 그쪽은 이름 짓는 규칙이 다르다(`사람id:탭이름`).
    for run in db.execute(
        select(MonthlyColumnRun).where(MonthlyColumnRun.target == CONTACT,
                                       MonthlyColumnRun.scope == before)
    ).scalars():
        run.scope = after
    row = db.execute(
        select(SheetOwner).where(SheetOwner.label == before)
    ).scalars().first()
    if row is not None:
        row.label = after
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


# ── 명단이 사는 화면 ────────────────────────────────────────────────────────
#
# 명단마다 **뜨는 화면이 다르다.** 스타트업 리마인드 명단은 좌측 [스타트업] 에
# 서고, 투자사 명단은 [투자사 관리 현황] 에 선다.
#
# **이름으로 가르지 않는다.** `layout`·`is_hidden`·`is_deal_list` 와 같은
# 방식이다 — 판정은 명단에 붙은 값(`SheetOwner.layout`)에서 나오고, 그 값이
# 어느 화면을 뜻하는지는 `contact_columns.page_of` 한 곳이 정한다.
#
# 화면이 둘이 된 지금 이것이 갈리면 **명단이 두 곳에 다 뜨거나 어디에도 안
# 뜬다.** 앞쪽은 어느 값이 최신인지 알 수 없고, 뒤쪽은 고칠 자리가 사라진다.


def page_of(db: Session, label: str) -> str:
    """이 명단이 사는 화면(주소 조각). 탭도 되돌아갈 자리도 이것으로 정한다."""
    from . import contact_columns

    return contact_columns.page_of(layout_of(db, label))


def page_href(db: Session, label: str) -> str:
    """조작하고 나서 **돌아갈 화면 주소**.

    참고 자료가 이미 같은 방식이다(`routers/contacts.py` 의 `_ref_back`).
    `/contacts` 로 못 박아 두면 스타트업 화면에서 칸을 하나 고쳤을 때 남의
    화면으로 튀고, 거기에는 그 탭이 없어서 **방금 고친 것이 사라진 것처럼**
    보인다.
    """
    return f"/{page_of(db, label)}"


def sheet_rows(db: Session, contacts: List[VcContact],
               page: Optional[str] = None) -> List[dict]:
    """명단 목록 + 담당 + 인원. 화면의 탭과 관리 표에 함께 쓴다.

    `page` 를 주면 **그 화면에 사는 명단만** 남긴다(위 `page_of` 참고).
    거르는 자리를 화면마다 두지 않고 여기 하나에 둔다 — 두 화면이 각자 걸러
    두면 한쪽만 고쳐지는 날 같은 명단이 양쪽에 다 뜬다.
    """
    from . import contact_columns

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
        layout = (row.layout if row and row.layout else "investor")
        if page is not None and contact_columns.page_of(layout) != page:
            continue
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
            "layout": layout,
            # 이 명단이 사는 화면. 위에서 거른 것과 **같은 값**이어야 한다 —
            # 따로 읽으면 거른 기준과 화면에 적힌 기준이 갈린다.
            "page": contact_columns.page_of(layout),
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


# ── 명단 사이로 옮기기 ──────────────────────────────────────────────────────
#
# 위 `add_to_sheet` 이 **더하는** 일(풀에서 뽑아 내 명단을 불린다)이라면 아래
# `move_to` 는 **옮기는** 일이다 — 옛 담당에게서 빼고 새 담당에게 붙인다.
#
# 이 규칙은 원래 `scripts/import_new_list.py` 안에만 있었다. 화면에서 줄 하나를
# 넘기는 길이 생기면서 부르는 곳이 둘이 됐고, 그때 화면에 규칙을 다시 적으면
# **두 벌이 된다** — 이 저장소가 반복해 당한 사고다(투자사 수가 화면마다 갈린
# 일, 좌측 메뉴 목록과 라우터 목록이 갈린 일, 보이는데 못 고치던 줄).
# 그래서 판정을 여기 한 곳에 두고 스크립트와 화면이 **같은 함수**를 부른다.


def move_to(db: Session, contact: VcContact, label: str, user_id: int) -> str:
    """이미 있는 줄을 이 명단으로 **옮긴다.** 새로 만들지 않는다.

    카톡방·발송 이력·담당 투자사가 이 줄에 붙어 있다. 새로 만들면 그 이력이
    끊기고, 이력이 없는 새 줄로 다시 처음부터 연락하게 된다.

    출처(`source_sheet`)에서 **담당이 정해진 남의 명단은 뺀다.** 남겨 두면 그
    팀원의 대시보드와 발송 대상에 계속 잡혀 같은 사람에게 딜 소개가 두 번
    나간다 — 애초에 배정을 정한 이유가 그것이다.

    담당이 없는 명단(투자사 풀)은 **그대로 둔다.** 풀은 확보해 둔 전체 명단이지
    누구의 담당도 아니라, 거기서 빼면 그 분류 자체가 사라진다
    (`add_to_sheet` 이 풀에서 빼지 않는 것과 같은 이유다).

    돌려주는 것은 `이전 명단 → 새 명단` 한 줄이다. 스크립트는 그것을 찍고
    화면은 사람에게 보여 준다 — **무엇이 바뀌었는지 말하지 않는 이관은
    되돌릴 수도 없다.**
    """
    owners = owner_map(db)
    before = labels_of(contact.source_sheet)
    keep = [x for x in before
            if x != MANUAL_SHEET
            and x != label
            and (not owners.get(x) or owners.get(x) == user_id)]
    contact.source_sheet = ",".join(keep + [label])
    contact.user_id = user_id
    return f"{', '.join(before)} → {contact.source_sheet}"


def transfer_targets(db: Session, page: Optional[str] = None) -> List[dict]:
    """줄 하나를 넘길 수 있는 곳 — **담당이 정해진 명단**만.

    풀은 뺀다. 풀은 누구의 담당도 아니라 "저 사람에게 넘긴다" 가 성립하지
    않는다 — 넘긴 줄의 `user_id` 를 정할 수가 없다.

    **화면의 탭(`sheet_rows`)을 그대로 쓸 수 없다.** 탭은 *지금 보이는 사람들*
    로 세어 만들기 때문에, 팀원에게는 자기 명단만 뜬다 — 정작 넘겨 줄 상대의
    명단이 목록에 없다. 넘기는 곳은 내가 그 명단에 사람을 갖고 있는지와
    상관없이 서 있어야 한다.

    `page` 를 주면 **그 화면에 사는 명단만** 남긴다. 투자사 줄을 스타트업
    명단으로 넘기면 줄이 다른 화면으로 사라져, 넘긴 사람은 어디로 갔는지
    찾을 수가 없다 — 이관은 *누가 맡는지*를 바꾸는 일이지 화면을 옮기는 일이
    아니다(화면을 옮기는 것은 명단의 배치가 정한다).

    **감춘 명단은 빼지 않고 그렇다고 알린다**(`is_hidden`). 처음엔 뺐는데, 그러면
    스타트업 화면에서 넘길 곳이 하나도 남지 않는다 — 그 화면의 명단은 **원래
    전부 감춰져 있다**(투자사가 아니라서 투자사로 안 센다. 이 파일 위쪽
    `is_investor` 참고). 넘길 곳이 없으면 그 화면에서는 이관 자체가 안 된다.
    걱정한 것은 "조용히 빠지는 것" 이었지 감춘 명단 자체가 아니므로, 막는 대신
    화면이 그 명단은 투자사로 세지 않는다고 **적는다** — 이 저장소가 수를
    다루는 방식 그대로다(`recipient_counts` 의 `off_list`).
    """
    from . import contact_columns

    names = {u.id: u.name for u in db.execute(select(User)).scalars().all()}
    out = []
    for label, row in settings_map(db).items():
        if not row.user_id:
            continue
        layout = row.layout or "investor"
        if page is not None and contact_columns.page_of(layout) != page:
            continue
        out.append({"label": label, "owner_id": row.user_id,
                    "owner": names.get(row.user_id, ""),
                    # 넘기면 투자사 수와 발송 대상에서 빠지는 명단인가.
                    "is_hidden": bool(row.is_hidden)})
    # 담당자 이름 → 명단 이름 순. 사람을 먼저 찾고 그 사람의 명단을 고른다.
    out.sort(key=lambda t: (t["owner"], t["label"]))
    return out
