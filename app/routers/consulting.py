"""투자컨설턴트 현황 — 구글시트를 그대로 옮긴 표.

원본 시트를 여러 사람이 같이 고치다 보니 어디까지 반영됐는지 알기 어려웠다.
여기로 옮겨 **한 곳에서 고치고, 누가 언제 고쳤는지 남게** 한다.

정해진 사람만 보는 화면이다 — 누가 볼 수 있는지는 `deps.may_view_consulting`
한 곳에서 정한다(관리자 · 투자컨설턴트 · 관리자가 켜 준 팀원).
대표자 연락처·이메일이 들어 있어서 팀 전체에 열어 둘 표가 아니다.

시트의 값은 대부분 자유 문장이다 — 미팅일이 `9/16 PM2 (화상미팅)` 처럼 적혀 있다.
형식을 강제하면 원본을 옮길 수 없으므로 그대로 문자열로 받는다.

월별 리마인드 열(`8월 마지막주 리마인드 톡 or TEL` …)은 달마다 하나씩 늘어난다.
테이블 컬럼으로 두면 매달 마이그레이션을 해야 하므로 행으로 두고,
내용은 기업 행의 JSON 에 담는다.
"""
from __future__ import annotations

import json
import re
from typing import Dict, List, Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import clock
from ..db import get_db
from ..deps import (NoConsulting, get_current_user, may_view_all_consulting,
                    may_view_consulting, templates)
from ..models import ConsultingColumn, ConsultingCompany, User
from ..services import consulting_sheets as cs
from ..services import consulting_status as status
from ..services import monthly_columns
from ..services import spreadsheet as sp
from ..ui import base_ctx

router = APIRouter(tags=["consulting"])

# 시트의 고정 열. (화면 표시 이름, 모델 속성)
FIXED_COLUMNS = [
    ("NO", "position"),
    ("지역", "region"),
    ("미팅일(화상, 회의실)", "meeting_at"),
    ("기업명 / 계약일 / 무료유료 / 계약금, 성과수수료 %", "company_name"),
    ("기업 관리 [ 드랍 이유 상세하게 기입 / 관리중 / 백업팀으로 전환 ]", "management"),
]
TAIL_COLUMNS = [
    ("대표자", "ceo_name"),
    ("연락처", "phone"),
    ("이메일", "email"),
]

# `관리 스타트업` 탭에만 한 칸 더 선다 — `기업 관리` **바로 오른쪽**이다.
#
# 투자사에 이 기업을 어떻게 소개할지 적는 자리가 표에 없어서 지금까지 옆 칸에
# 같이 적혀 있었다. `기업 관리` 는 **지금 어떻게 되고 있는가**를 적는 칸이고
# 그 값으로 칩·KPI 를 세는 자리라(`services/consulting_status.py`), 소개 문구가
# 거기 섞이면 문구 안에 우연히 든 `관리` 한 낱말로 엉뚱한 갈래에 걸린다.
#
# 다른 두 탭(`경영본부 전달 기업` · `월간 계약 업무현황표`)에는 안 세운다.
# 소개 문구는 아직 관리 중인 기업에 대고 쓰는 말이고, 계약 탭은 표 자체가
# 다르다. 그래서 `FIXED_COLUMNS` 에 넣지 않고 이 탭만의 묶음을 따로 둔다 —
# `FIXED_COLUMNS` 는 지금도 스타트업·경영본부 두 탭이 함께 쓴다.
STARTUP_COLUMNS = FIXED_COLUMNS + [("딜 소개문구", "deal_pitch")]

# `월간 계약 업무현황표` 는 다른 두 탭과 **표 자체가 다르다.**
#
# 저 시트는 머리글 있는 표가 아니라 월 묶음 아래 슬래시 한 줄이었다
# (`scripts/import_consulting.py` 의 `parse_contract_sheet`). 그래서 다른 탭의
# 칸을 빌려 담았는데, 빌린 이름이 뜻과 어긋나 있었다 — `지역` 칸에 `6월` 이,
# `기업 관리` 칸에 `무료`/`유료` 가 들어 있고, 기업명·계약금·보수율·계약일
# 네 가지가 `기업명` 한 칸에 뭉쳐 있었다.
#
# 칸 이름을 시트가 부르는 대로 돌려놓고, 뭉쳐 있던 줄을 칸으로 나눈다.
# **머리글만 다르고 담기는 모델은 하나다** — 시트마다 테이블을 나누면 같은
# 성격의 줄이 두 곳에 흩어져 권한·필터·엑셀을 두 벌로 만들어야 한다.
CONTRACT_COLUMNS = [
    ("NO", "position"),
    ("월", "region"),            # 시트의 월 묶음 제목(`6월`)이 들어 있던 칸
    # 시트 머리글은 `계약일` 이라고 적혀 있지만 **칸에 든 값은 날짜가 아니다.**
    # 실제 값은 `미정`(4줄)과 `8`(1줄) — `8` 은 8월이라는 뜻의 달 숫자다.
    # 이름이 `계약일` 이면 `2026-08-15` 같은 날짜를 적어야 하는 칸으로 읽혀,
    # 다음에 채우는 사람이 다른 모양의 값을 넣는다. **이름을 값에 맞춘다.**
    #
    # 값은 손대지 않는다. 뜻이 바뀐 것이 아니라 이름이 값을 잘못 부르고 있던
    # 것이고, `미정` 도 그대로 남아야 한다 — 이 저장소는 적힌 것을 고쳐 쓰지
    # 않는다(`split_contract_line` 참고).
    ("계약월", "meeting_at"),
    ("기업명", "company_name"),
    ("계약여부", "management"),   # 무료 / 유료
    # 계약을 맺은 것과 **계약서를 받은 것**은 다른 사실이다. 앞 칸에 섞어 두면
    # 계약은 했는데 서류가 아직 안 온 곳을 가려낼 수가 없다.
    # 빈칸은 `아직 안 정함` 이다(`models.ConsultingCompany.contract_received`).
    ("계약서 수신여부", "contract_received"),   # O / X
    ("성공보수율", "success_fee"),
    ("계약금", "contract_fee"),
]
# 대표자·연락처·이메일은 이 탭에서 **화면에만** 안 세운다. 계약 줄에는 원래
# 값이 없는 칸이라 자리만 먹는데, 값을 지우는 것은 다른 문제다 — 이 저장소는
# 이력을 함부로 지우지 않는다. 나중에 이 탭에도 담당자를 적게 되면 칸만
# 되살리면 그만이고, 지웠으면 되살릴 것이 없다.
CONTRACT_TAIL: List[tuple] = []


def require_access(user: User) -> None:
    """관리자이거나, 이 화면을 보도록 허용된 계정이어야 한다.

    **누가 볼 수 있는지는 `deps.may_view_consulting` 한 곳에서 정한다.** 여기에
    조건을 한 번 더 적어 두었더니 팀 현황 표가 보는 조건과 갈렸고, 컨설턴트
    줄에 `막힘` 이라고 뜨는데 실제로는 열려 있었다 — 표가 거짓말을 한 것이다.
    """
    if may_view_consulting(user):
        return
    # 무엇을 돌려줄지는 여기서 정하지 않는다 — 주소창이 여는 GET 이면 안내창이
    # 있는 화면, 스크립트가 부른 것이면 403. 관리자 전용(`NotAdmin`)이 이미
    # 그렇게 갈라 두었고, 그 판단은 `deps.consulting_block_response` 한 곳에
    # 있다. 이 화면은 API 가 열두 자리라, 자리마다 답을 적으면 하나는 낡는다.
    raise NoConsulting()


# 고르는 자리의 `담당 미배정`. 주인이 없는 줄(user_id NULL)을 고르는 값이다.
#
# **0 을 쓸 수 없다.** `owner` 는 안 고른 상태가 0(전체)이라, 미배정을 0 으로
# 두면 그 칩을 눌러도 전체가 나오면서 `전체` 칩까지 같이 눌린 것처럼 보인다 —
# 화면이 거짓말을 하는 자리다.
UNASSIGNED = -1


def scope(stmt, model, user: User, owner: int = 0):
    """이 사람이 **볼** 줄만 남긴다.

    이 화면은 컨설턴트 한 사람의 개인 표이면서, 그 표들을 모아 팀이 보는
    자리이기도 하다. 그래서 보는 범위가 둘로 갈린다 — 누가 어느 쪽인지는
    `deps.may_view_all_consulting` 한 곳이 정한다(여기에 역할을 다시 적으면
    메뉴·화면·라우터가 갈린다).

    - 컨설턴트  **자기 것만.** 남의 담당 기업이 보이면 안 되고, 각자 올린
                시트가 서로를 덮는다(월별 리마인드 열이 사람마다 다르다).
    - 그 외     관리자와 관리자가 켜 준 팀원. 두 사람의 표를 나란히 놓고 봐야
                하는 자리라 **전체**를 보고, `owner` 로 한 사람만 골라 본다.

    **보는 범위이지 고치는 범위가 아니다.** 팀원은 전체를 보되 자기 줄만
    고친다 — 고치는 판정은 `may_edit_row` 한 곳이다.

    주인이 없는 줄(user_id NULL)은 전체를 보는 사람에게만 보인다 — 배정해야
    할 것이 남아 있다는 뜻이라, 아무에게나 보이면 서로 자기 것인 줄 안다.
    """
    if not may_view_all_consulting(user):
        return stmt.where(model.user_id == user.id)
    if owner == UNASSIGNED:
        return stmt.where(model.user_id.is_(None))
    if owner:
        return stmt.where(model.user_id == owner)
    return stmt


def own(stmt, model, user: User):
    """**내 표 안**으로 좁힌다 — 보는 것이 아니라 손이 닿는 범위다.

    위 `scope()` 와 갈라 두는 이유가 있다. 팀원은 이제 팀 전체를 **보지만**,
    자기 열을 지우거나 시트를 올리는 일까지 전체에 닿으면 안 된다. 실제로
    그 자리다 — 열을 지우면서 표를 훑어 그 달 기록을 지우는데, 보는 범위로
    훑으면 자기 열을 지우는 것뿐인데 손이 남의 줄까지 닿는다.

    관리자는 여기서도 전체다. 관리자가 팀 전체를 고치는 것은 이 앱의 다른
    화면과 같은 규칙이다(`deps.may_manage_team_contacts`).
    """
    if user.role == "admin":
        return stmt
    return stmt.where(model.user_id == user.id)


def may_edit_row(user: User, owner_id: Optional[int]) -> bool:
    """이 줄(또는 열)을 고칠 수 있는가 — **판정은 여기 한 곳이다.**

    화면이 `읽기 전용` 이라고 그리는 줄과 서버가 404 로 막는 줄이 **같아야**
    한다. 두 곳에 적으면 하나는 반드시 낡아서, 고칠 수 있게 그려 놓고 누르면
    `찾을 수 없습니다` 가 뜨거나(팀 현황의 담당자 칸이 그랬다) 반대로 못 고치는
    것처럼 그려 놓고 실제로는 고쳐진다.

    관리자는 전부, 그 외에는 자기 줄만이다. 주인 없는 줄은 아무도 못 고친다 —
    배정할 것이 남았다는 뜻이지, 먼저 본 사람이 갖는 것이 아니다.
    """
    if user.role == "admin":
        return True
    return owner_id is not None and owner_id == user.id


def owned(db: Session, model, row_id: int, user: User, what: str):
    """고칠 수 있는 줄 하나. 아니면 **없는 것으로** 답한다.

    **화면이 쓰는 두 판정을 그대로 태운다** — 볼 수 있는가(`scope()`)와 고칠
    수 있는가(`may_edit_row`). 여기가 정확히 그것이 갈려서 났던 자리다: 보는
    쪽은 `scope()` 로 좁히는데 고치는 쪽에는 검사가 아예 없어서,
    `can_view_consulting` 이 켜진 팀원이 **번호만 바꾸면 화면에 안 뜨는 남의
    줄**을 고치거나 지울 수 있었다. 안 보이는 것을 고치는 것이라 고친 사람도,
    당한 사람도 모른다.

    판정을 여기 새로 적지 않는 이유는 이 저장소가 반복해 당한 유형이라서다
    (투자사 수가 화면마다 달랐던 일, 좌측 메뉴와 라우터 목록이 갈려 컨설턴트에게
    다 열려 있던 일, 팀 현황의 `투자현황` 칸이 거짓말한 일). 두 곳에 적으면
    한쪽은 반드시 낡는다 — 표에 `읽기 전용` 으로 그려지는 줄과 여기서 404 가
    나는 줄은 **같은 함수 하나**가 정한다.

    없는 번호와 남의 번호를 **같은 404** 로 답한다. 403 으로 갈라 주면 번호를
    훑어 남의 표가 몇 번까지 있는지 알 수 있다(routers/contacts.py 의 `_owned`
    가 같은 이유로 그렇게 한다).
    """
    row = db.execute(
        scope(select(model).where(model.id == row_id), model, user)
    ).scalar_one_or_none()
    if row is None or not may_edit_row(user, row.user_id):
        raise HTTPException(status_code=404, detail=f"{what}을 찾을 수 없습니다")
    return row


def owner_tabs(db: Session, user: User, sheet: str = "") -> List[dict]:
    """화면 위의 **사람을 고르는 자리.** 자기 것만 보는 사람에게는 없다.

    **이름은 계정 목록이 아니라 줄에서 뽑는다.** 계정으로 세우면 컨설턴트로
    만들어만 두고 아직 기업을 안 받은 사람이 `0` 으로 서서, 고를 것이 없는
    이름이 늘어난다. 줄이 곧 담당이므로 줄에 붙어 있는 사람만 세운다.

    **담당이 컨설턴트가 아닌 줄도 그 사람 이름으로 선다.** 지금 운영의 모든
    줄이 그 상태다(팀원 한 사람이 시트를 통째로 들고 있다). 그것을 `미배정`
    같은 말로 묶으면 화면이 거짓말을 한다 — 그 줄에는 실제로 주인이 있고,
    그 사람만 고칠 수 있으며, 주인 없는 줄(user_id NULL)은 "아직 배정 안 됨"
    이라는 **다른 뜻**으로 이미 서 있다. 대신 역할을 옆에 적어 둔다
    (`role_note`) — 이 화면이 컨설턴트별 표라, 이름만 있으면 그 사람이 세
    번째 컨설턴트인 줄 읽힌다.

    **숫자는 지금 보고 있는 탭의 건수다.** 눌렀을 때 나올 수와 같아야 한다 —
    탭을 가리지 않고 세면 탭에는 32 라고 적혀 있는데 이름 옆에는 55 가 붙는다.
    사람 목록 자체는 탭을 가리지 않는다. 이 탭에 줄이 없다고 이름을 빼면
    그 사람 표로 건너갈 길이 화면에서 사라진다.
    """
    if not may_view_all_consulting(user):
        return []
    counts = dict(db.execute(
        select(ConsultingCompany.user_id, func.count())
        .where(ConsultingCompany.sheet == sheet)
        .group_by(ConsultingCompany.user_id)
    ).all()) if sheet else {}
    totals = dict(db.execute(
        select(ConsultingCompany.user_id, func.count())
        .group_by(ConsultingCompany.user_id)
    ).all())
    out = []
    for uid, total in totals.items():
        who = db.get(User, uid) if uid else None
        out.append({
            "id": uid or UNASSIGNED,
            "name": who.name if who else "담당 미배정",
            # 컨설턴트가 아닌 담당에만 붙는다. 컨설턴트 이름에 `투자컨설턴트`
            # 라고 또 적으면 화면이 같은 말을 두 번 하는 것뿐이다.
            "role_note": ("" if who is None or who.role == "consultant"
                          else "팀원" if who.role != "admin" else "관리자"),
            "count": counts.get(uid, 0),
            "total": total,
        })
    # 탭을 옮겨도 **자리가 그대로**여야 한다. 이 탭의 건수로 줄을 세우면 탭마다
    # 이름 순서가 바뀌어, 같은 자리를 눌렀는데 다른 사람이 열린다.
    return sorted(out, key=lambda x: (-x["total"], x["name"]))


# 표에 한 번에 보여줄 월 수. 달마다 한 칸씩 늘어나는 표라, 그냥 두면 한 해
# 뒤에는 열두 칸이 되어 가로로 밀어야 읽힌다. 실제로 챙기는 것은 최근 몇
# 달뿐이다.
VISIBLE_MONTHS = 3


# 탭 이름은 **여기 없다.** 화면에서 고치는 값이라 `ConsultingSheet` 행에 있고,
# 무엇이 세워지는지는 `services/consulting_sheets.py` 한 곳이 정한다.
#
# 첫 탭은 `중요 스타트업` 이었다. `중요` 는 나머지 탭이 안 중요하다는 뜻으로
# 읽히는데 실제로는 그런 갈래가 아니다 — 시트 세 장의 성격 차이일 뿐이다.
# 그때는 **이름만 바꾸니 이미 들어간 줄이 옛 이름의 유령 탭으로 갈라져서**
# 자료를 옮기는 마이그레이션을 따로 써야 했다(0039). 이제 이름을 바꾸면
# 그 줄들이 같이 따라간다(`consulting_sheets.rename`).

# 탭의 **열쇠** → (앞 칸들, 뒤 칸들). 적어 두지 않은 탭은 지금까지의 표다.
#
# **이름이 아니라 열쇠로 짝짓는다.** 이름으로 맞춰 두면 탭 이름을 한 글자
# 고치는 순간 계약 표가 조용히 일반 표로 돌아가, `계약월`·`성공보수율` 칸이
# 화면에서 사라진다 — 이름을 고칠 수 있게 만들면서 생기는 함정이다.
SHEET_LAYOUTS = {
    cs.CONTRACT: (CONTRACT_COLUMNS, CONTRACT_TAIL),
    # 스타트업 탭만 `딜 소개문구` 를 한 칸 더 세운다. 여기 적어 두지 않으면
    # `경영본부 전달 기업`(과 사람이 시트를 올려 만든 탭)까지 같은 묶음을 받아,
    # 값이 영영 안 들어갈 칸이 그 탭들에도 선다.
    cs.STARTUP: (STARTUP_COLUMNS, TAIL_COLUMNS),
}


def layout_of(db: Session, sheet: str) -> tuple:
    """이 탭이 쓰는 칸 묶음. 모르는 탭은 지금까지의 표다.

    사람이 시트를 올려 만든 탭도 있어서, 이름을 모른다고 표를 비워 버리면
    그 탭이 통째로 안 보인다.
    """
    return SHEET_LAYOUTS.get(cs.kind_of(db, sheet), (FIXED_COLUMNS, TAIL_COLUMNS))


def is_contract(db: Session, sheet: str) -> bool:
    """이 탭이 계약 표인가. **이름으로 견주지 않는다**(위 참고)."""
    return cs.kind_of(db, sheet) == cs.CONTRACT


def is_startup(db: Session, sheet: str) -> bool:
    """이 탭이 `관리 스타트업` 인가. `딜 소개문구` 칸이 여기에만 선다.

    `is_contract` 의 반대가 아니다 — 아닌 탭이 `경영본부 전달 기업` 과 사람이
    시트를 올려 만든 탭까지 둘 이상이라, 화면에서 `not is_contract` 로 갈랐다간
    그 탭들에도 칸이 같이 선다. 여기도 **이름이 아니라 열쇠로** 본다.
    """
    return cs.kind_of(db, sheet) == cs.STARTUP


# `월간 계약 업무현황표` 의 한 줄은 슬래시로 이어 붙어 있다. **시트가 스스로
# 그 순서를 머리글로 적어 두었다** — `기업명 / 계약금액 / 성공보수율 / 계약일`.
# 그 순서를 그대로 따른다(추측이 아니라 시트에 적힌 것이다).
CONTRACT_PARTS = ["company_name", "contract_fee", "success_fee", "meeting_at"]


def split_contract_line(line: str) -> Dict[str, str]:
    """`기업명/ 유료 90만/ 3프로/ 미정` → 칸마다 하나씩. 나눌 것이 없으면 빈 dict.

    **조각 수가 줄마다 다르다.** 실제 자료에도 셋짜리와 넷짜리가 섞여 있다.

      모자라면  뒤 칸을 비워 둔다. 시트에서 빠지는 것은 늘 뒤쪽이고
                (`○○○/ 무료/ 4%` 는 계약일이 아직 없다는 뜻이다),
                앞에서 채우면 보수율 칸에 계약일이 들어간다.
      넘치면    남는 조각을 **마지막 칸에 그대로 이어 둔다.** 버리면 시트에
                있던 값이 앱에서 사라진다 — 사람이 보고 옮길 수 있게 남긴다.

    값은 **적힌 그대로** 담는다. `3%` 인지 `3프로` 인지, `유료 90만` 인지는
    계약서에 적힌 말이라 앱이 고쳐 쓸 것이 아니다. `계약금액` 칸에 `무료` 가
    적혀 있는 것도 시트가 그렇게 쓴 것이라 그대로 둔다.
    """
    parts = [p.strip() for p in (line or "").split("/")]
    if len(parts) < 2:
        return {}
    out = dict(zip(CONTRACT_PARTS, parts))
    if len(parts) > len(CONTRACT_PARTS):
        out[CONTRACT_PARTS[-1]] = " / ".join(parts[len(CONTRACT_PARTS) - 1:])
    return out


def _visible_column_scopes(db: Session, user: User,
                           owner: int = 0) -> List[tuple]:
    """이 요청에서 월 열을 세워도 되는 (사람, 탭) 묶음.

    **보는 범위를 그대로 쓴다**(`scope()`). 관리자가 열면 자기가 볼 수 있는
    표 전부를, 컨설턴트가 열면 자기 표만 챙긴다 — 여기에 따로 조건을 적으면
    보는 범위와 갈려서, 안 보이는 남의 표에 열이 생기는 자리가 된다.

    **이미 열이 있는 묶음만** 돌려준다. 열이 하나도 없는 표는 이름 지을 본이
    없어 어차피 만들지 못한다(`services/monthly_columns.py` 참고).
    """
    rows = db.execute(scope(
        select(ConsultingColumn.user_id, ConsultingColumn.sheet)
        .group_by(ConsultingColumn.user_id, ConsultingColumn.sheet),
        ConsultingColumn, user, owner)).all()
    return [(uid, name) for uid, name in rows if uid and name]


def sheet_tabs(db: Session, user: User, owner: int = 0) -> List[dict]:
    """시트별 인원. 탭에 건수를 띄운다.

    **줄이 하나도 없어도 탭 셋은 선다.** 새로 온 투자컨설턴트에게 빈 화면이
    뜨면 없는 줄 알고 자기 시트를 또 만든다 — 탭은 팀이 함께 쓰는 업무 단계라
    사람마다 갈릴 것이 아니다(`services/consulting_sheets.py`).

    이름은 **화면에서 고친 값**이다. 여기에 목록을 적어 두면 고친 이름이 이
    화면에만 안 반영된다.
    """
    rows = dict(db.execute(scope(
        select(ConsultingCompany.sheet, func.count())
        .group_by(ConsultingCompany.sheet), ConsultingCompany, user, owner)
    ).all())
    out = [{"key": s.label, "label": s.label, "kind": s.kind,
            "count": rows.get(s.label, 0)} for s in cs.ensure(db)]
    # 사람이 시트를 올려 만든 탭도 그대로 세운다 — 목록에 없다고 빼면 그 줄들이
    # 화면 어디에도 안 뜬다.
    known = {t["key"] for t in out}
    out += [{"key": n, "label": n, "kind": "", "count": rows[n]}
            for n in rows if n not in known]
    return out


def _column_stmt(sheet: str = ""):
    stmt = select(ConsultingColumn).order_by(ConsultingColumn.position,
                                             ConsultingColumn.id)
    return stmt.where(ConsultingColumn.sheet == sheet) if sheet else stmt


def _columns(db: Session, user: User, sheet: str = "",
             owner: int = 0) -> List[ConsultingColumn]:
    """화면에 세울 월 열 — **보는 범위**다."""
    return db.execute(scope(_column_stmt(sheet), ConsultingColumn, user,
                            owner)).scalars().all()


def _my_columns(db: Session, user: User,
                sheet: str = "") -> List[ConsultingColumn]:
    """**내 표의** 월 열. 자리를 밀거나 시트를 올릴 때 손이 닿는 범위다.

    보는 범위(`_columns`)를 쓰면 안 된다 — 팀원은 이제 팀 전체를 보므로, 열을
    하나 세우면서 남의 열까지 한 칸씩 밀게 된다.
    """
    return db.execute(own(_column_stmt(sheet), ConsultingColumn,
                          user)).scalars().all()


def _split_columns(columns: List[ConsultingColumn], show_all: bool = False) -> tuple:
    """(보여줄 월, 접어 둔 월). **달 단위로** 자른다.

    **접었다는 것을 사람이 알아야 한다** — 그냥 안 보이면 지워진 줄 안다.
    화면에 몇 달이 접혀 있는지 적고, 눌러서 펼 수 있게 한다.

    지금까지는 앞에서 세 **칸**을 잘랐다. 이 표는 한 달에 한 칸이라 결과가
    같았지만, 한 달에 두 칸을 세우는 순간 달 중간이 잘려 **한 달의 기록 일부만
    보이는** 표가 된다. 투자사 관리 현황이 이미 그 모양이라(한 달에 세 칸)
    자르는 기준을 같은 것으로 맞춘다(`services/contact_columns.split_months`).

    여기만 석 달을 편다. 위 KPI 가 **지난달** 빈칸을 세므로 그 달이 표에
    보여야 하고, 한 달에 한 칸이라 석 달이어도 세 칸이다.

    사람이 펴 둔 상태(`?months=all`)는 요청에 실려 있고 DB 에 없다 — 달이
    바뀌어 열이 저절로 생겨도 편 것을 다시 접을 수가 없다.
    """
    if show_all:
        return list(columns), []
    seen: List[str] = []
    for i, col in enumerate(columns):
        month = monthly_columns.month_of(col.label)
        # 이름에서 달을 못 읽는 열은 혼자 한 묶음이다 — 옆 달에 붙이면 그 열
        # 때문에 남의 달이 통째로 접히거나 펴진다.
        key = f"{month}월" if month is not None else f"#{i}"
        if key in seen:
            continue
        if len(seen) == VISIBLE_MONTHS:
            return list(columns[:i]), list(columns[i:])
        seen.append(key)
    return list(columns), []


def _prev_month() -> int:
    """지난달 숫자. 1월이면 12월이다.

    시각은 `app/clock.py` 로만 읽는다. 표준 라이브러리의 현재시각 함수를 여기서
    바로 부르면 시간대가 또 갈린다(`tests/test_timezone.py` 가 막는다).
    """
    return clock.today().month - 1 or 12


def _prev_month_label(columns: List[ConsultingColumn]) -> str:
    """지금 기준 **지난달**에 해당하는 열의 이름.

    열 이름이 `8월 마지막주 리마인드 톡 or TEL` 처럼 자유 문장이라 달을 숫자로
    읽어 찾는다. 없으면 빈 문자열 — 화면이 그냥 '연락 기록' 으로 돈다.
    """
    month = _prev_month()
    for col in columns:
        m = re.search(r"(\d{1,2})\s*월", col.label or "")
        if m and int(m.group(1)) == month:
            return col.label
    return ""


def _prev_month_columns(columns: List[ConsultingColumn]) -> List[str]:
    label = _prev_month_label(columns)
    return [str(c.id) for c in columns if c.label == label]


# 주인이 없는 줄을 표에서 부르는 말. 고르는 자리의 `담당 미배정` 과 같은 뜻이라
# 한 곳에 적어 둔다 — 두 곳에 적으면 한쪽만 고쳐져 같은 줄이 화면에서 두 이름으로
# 불린다.
NO_OWNER = "미배정"


def _owner_name(db: Session, owner_id: Optional[int]) -> str:
    """줄에 붙은 담당의 이름. 주인이 없으면 `미배정`."""
    who = db.get(User, owner_id) if owner_id else None
    return who.name if who else NO_OWNER


def _pick_owner(db: Session, user: User, owner: int) -> int:
    """고른 사람이 **실제로 줄을 가진 사람**인가. 아니면 전체로 돌린다.

    주소에 없는 번호가 실려 오면(옛 즐겨찾기 · 담당이 다 옮겨 간 뒤) 표는 비고
    고르는 자리에는 아무것도 안 눌린 채로 남는다 — 왜 비었는지 화면 어디에도
    안 나온다. 그럴 바에는 전체를 보여 주는 편이 낫다.
    """
    if not may_view_all_consulting(user) or not owner:
        return 0
    known = {uid or UNASSIGNED for (uid,) in db.execute(
        select(ConsultingCompany.user_id)
        .group_by(ConsultingCompany.user_id)).all()}
    return owner if owner in known else 0


def _notes(company: ConsultingCompany) -> Dict[str, str]:
    try:
        return json.loads(company.notes or "{}")
    except (TypeError, ValueError):
        return {}


def company_rows(db: Session, user: User, sheet: str = "",
                 owner: int = 0) -> List[dict]:
    cols = _columns(db, user, sheet, owner)
    prev_keys = _prev_month_columns(cols)
    stmt = select(ConsultingCompany).order_by(ConsultingCompany.position,
                                              ConsultingCompany.id)
    if sheet:
        stmt = stmt.where(ConsultingCompany.sheet == sheet)
    companies = db.execute(scope(stmt, ConsultingCompany, user, owner)).scalars().all()
    out = []
    for order, c in enumerate(companies, start=1):
        notes = _notes(c)
        management = c.management or ""
        # 이 탭이 계약 표인가. 줄에 적힌 탭으로 본다 — `company_rows` 는 탭을
        # 안 주고 부르는 곳이 있어서(엑셀 · 한 줄 조회), 인자로 판단하면
        # 그쪽에서만 값이 달라진다.
        contract = is_contract(db, c.sheet)
        # 이 줄이 `딜 소개문구` 칸을 세우는 탭에 있는가. 화면과 **같은 판정**을
        # 쓴다(`is_startup`) — 여기에 조건을 한 번 더 적으면 화면에는 칸이
        # 없는데 검색만 걸리는 줄이 생긴다.
        startup = is_startup(db, c.sheet)
        # 이 줄에 보이는 월별 리마인드 칸. 접힌 달도 들어 있다 — 화면에 안
        # 보인다고 기록이 없는 것은 아니다.
        seen = {str(col.id): notes.get(str(col.id), "") for col in cols}
        out.append({
            "id": c.id,
            # **누구의 줄인가.** 여러 사람의 표를 한 화면에서 보는 자리라,
            # 줄만 보고는 누구 것인지 알 수 없으면 고른 사람을 바꿀 때마다
            # 위 칩을 다시 확인해야 한다.
            "owner_id": c.user_id or 0,
            "owner_name": _owner_name(db, c.user_id),
            # **화면이 고칠 수 있다고 그리는 것과 서버가 허락하는 것이 같아야
            # 한다.** 판정은 `may_edit_row` 한 곳이고 화면은 그것을 읽기만 한다
            # (`owned()` 도 같은 함수를 태운다).
            "editable": may_edit_row(user, c.user_id),
            # 화면의 NO 는 **보이는 순서대로 1부터**다. 시트에서 옮겨 온 번호는
            # 중간이 비거나 3부터 시작해서, 몇 번째 줄인지 세는 데 쓸 수 없다.
            "no": order,
            "position": c.position,
            "region": c.region or "",
            "meeting_at": c.meeting_at or "",
            "company_name": c.company_name or "",
            "management": management,
            # 머리글 필터가 보는 값. 칸에 적힌 문장 그대로가 아니라 시트가 정해
            # 둔 세 마디로 추린다. 계약 탭만 예외다.
            "mgmt": status.tag_value(management, contract=contract),
            # **위 KPI 도 줄의 표시도 여기서 나온다.** 예전에는 라우터가 KPI 를,
            # 화면이 `data-dropped` 를 각자 정해서 규칙이 두 벌이었다.
            "managed": status.is_managed(management, contract=contract),
            "dropped": status.is_dropped(management, contract=contract),
            "ceo_name": c.ceo_name or "",
            "phone": c.phone or "",
            "email": c.email or "",
            # `월간 계약 업무현황표` 탭에만 값이 있다. 다른 탭에서는 빈 문자열이라
            # 화면이 탭마다 다른 dict 를 받지 않는다 — 없는 칸을 꺼내다 터지는
            # 자리를 만들지 않으려는 것이다.
            "success_fee": c.success_fee or "",
            "contract_fee": c.contract_fee or "",
            # 빈 문자열이 곧 `아직 안 정함` 이다 — 머리글 필터가 그것을
            # `(비어 있음)` 으로 세워 준다(`static/js/filters.js`).
            "contract_received": c.contract_received or "",
            # `관리 스타트업` 탭에만 값이 있다. 위 두 칸과 같은 이유로 늘
            # 실어 둔다 — 화면이 탭마다 다른 dict 를 받으면 없는 칸을 꺼내다
            # 터지는 자리가 생긴다. 머리글·칸을 세우는 것은 화면 쪽이다.
            "deal_pitch": c.deal_pitch or "",
            "notes": seen,
            # 어느 달이든 기록이 있는가 — `연락 기록 없음` 칩이 보는 값이다.
            "contacted": status.contacted(seen.values()),
            # 지난달에 연락했는가. 이번 달은 아직 진행 중이라 세어 봐야
            # "아직 안 했다" 만 나온다.
            "contacted_prev": status.contacted(notes.get(k, "") for k in prev_keys),
            "updated_at": (c.updated_at or "")[:10],
            "search": " ".join(filter(None, [
                c.company_name, c.region, c.management, c.ceo_name,
                c.email, c.meeting_at, c.success_fee, c.contract_fee,
                # 칸을 고치면 브라우저가 `td.cell` 을 전부 이어 붙여 이 값을
                # 다시 적는다(`consulting.js` 의 `refreshRowFlags`). 여기서
                # 빼 두면 새로고침 전후로 검색 결과가 달라진다.
                c.contract_received,
                # **문구로 찾는 것이 이 칸을 둔 이유에 가깝다.** 필터에는 안
                # 세웠지만(값이 자유 문장이라 고를 것이 없다) 검색은 자유
                # 문장을 그대로 받는 자리라 여기에 넣는다 — 툴바의
                # `기업 · 대표자 · 내용 검색` 이 이 값을 본다.
                #
                # **칸이 서는 탭에서만** 넣는다. 탭을 옮긴 줄에는 값이 남아
                # 있을 수 있는데(이 저장소는 이력을 안 지운다), 칸이 없는
                # 탭에서까지 걸면 화면 어디에도 없는 글자로 줄이 걸려 왜
                # 걸렸는지 알 수가 없다. 게다가 그 탭에서 아무 칸이나 고치는
                # 순간 브라우저가 보이는 칸만 이어 붙여 이 값을 다시 적으므로
                # (`consulting.js` 의 `refreshRowFlags`) 고치기 전후로 검색
                # 결과가 달라진다.
                c.deal_pitch if startup else "",
                *notes.values(),
            ])).lower(),
        })
    return out


@router.get("/consulting", response_class=HTMLResponse, include_in_schema=False)
def consulting_page(request: Request, db: Session = Depends(get_db),
                    user: User = Depends(get_current_user), msg: str = "",
                    months: str = "", sheet: str = "", owner: int = 0,
                    ref: str = ""):
    require_access(user)
    # 자기 것만 보는 사람(투자컨설턴트)에게는 고를 것이 없다 — 무엇을 넣든
    # 자기 줄만 나온다(`scope()` 가 같은 판정을 읽는다).
    owner = _pick_owner(db, user, owner)
    tabs = sheet_tabs(db, user, owner)
    selected = (sheet if any(t["key"] == sheet for t in tabs)
                else cs.default_label(db))
    # **달이 바뀌었으면 이번 달 열을 세운다.** 예약 실행 장치가 없는 앱이라
    # 달이 바뀐 것을 알아채는 자리는 화면을 여는 순간뿐이다(주간 업무가 같은
    # 방식이다 — `services/weekly.py` 의 `fill_week`). 두 번 만들지 않는 것과
    # 사람이 지운 열을 되살리지 않는 것은 `services/monthly_columns.py` 가 본다.
    #
    # **보이는 표마다** 세운다. 열은 사람마다·탭마다인데, 지금 고른 탭 하나만
    # 챙기면 아무도 안 연 탭은 그 달 기록이 지난달 열에 섞여 들어간다.
    for uid, name in _visible_column_scopes(db, user, owner):
        monthly_columns.ensure_consulting(db, uid, name)

    rows = company_rows(db, user, selected, owner)
    can_pick = may_view_all_consulting(user)
    people = owner_tabs(db, user, selected) if can_pick else []
    prev_label = _prev_month_label(_columns(db, user, selected, owner))
    # 달마다 한 칸씩 늘어나는 표라, 최근 몇 달만 펴 둔다.
    # `months=all` 은 일부러 다 본다는 뜻이다.
    shown, hidden = _split_columns(_columns(db, user, selected, owner),
                                   show_all=(months == "all"))
    fixed, tail = layout_of(db, selected)

    # **접힌 달에 기록이 있는가.** `연락 기록 없음` 칩은 줄의 `data-contacted` 를
    # 보는데, 칸을 고치면 consulting.js 가 그 값을 다시 적는다 — 그때 JS 가 볼 수
    # 있는 것은 **펴 둔 달의 칸뿐**이라, 접힌 달에만 기록이 있는 줄이 고치는 순간
    # `기록 없음` 으로 뒤집힌다(실제로 이 표 34줄 중 12줄이 그 상태였다).
    # 화면에 없는 사실을 JS 가 알 수 없으므로 여기서 실어 보낸다.
    folded_keys = [str(c.id) for c in hidden]
    for row in rows:
        row["contacted_folded"] = status.contacted(
            row["notes"].get(k, "") for k in folded_keys)
    ctx = base_ctx(request, db, user, active="consult")
    # 스크립트·가이드는 이 화면에도 있다(미팅 진행 프로세스 · 견적서 발송 톡 …).
    # 투자사 관리 현황과 같은 구조를 쓰되 화면만 나눈다.
    # 질의는 `services/ref_panel.py` 한 곳에 있다 — 화면마다 적어 두면
    # `is_active`(지운 탭 감추기)나 탭 순서 같은 조건이 화면마다 갈린다.
    from ..services import ref_panel  # noqa: PLC0415

    ctx.update({
        **ref_panel.panel_ctx(db, "consulting", ref),
        "rows": rows,
        "sheet_tabs": tabs,
        "selected_sheet": selected,
        "columns": shown,
        # **접었다는 것을 사람이 알아야 한다** — 그냥 안 보이면 지워진 줄 안다.
        "hidden_columns": hidden,
        # **[✕] 를 세워도 되는 월 열.** 열도 사람마다 따로 있어서, 남의 달에
        # 단추를 세워 두면 눌렀을 때 404 만 난다(`owned()`). 판정은 줄과 같은
        # 함수 하나다 — 화면이 따로 정하면 한쪽이 낡는다.
        "editable_columns": {c.id for c in shown if may_edit_row(user, c.user_id)},
        "show_all_months": months == "all",
        # 화면 위의 **사람을 고르는 자리.** 숫자는 지금 탭의 건수라
        # 눌렀을 때 나올 수와 같다.
        "owner_tabs": people,
        "selected_owner": owner,
        # 고르는 자리와 `담당` 칸이 같이 서고 같이 없어진다 — 둘 다 "여러
        # 사람의 표를 같이 본다" 는 한 가지 사실에서 나온다. 컨설턴트에게는
        # 자기 줄만 나오므로 이름이 한 가지로 반복될 뿐이다.
        "can_pick_owner": can_pick,
        "selected_owner_name": next(
            (o["name"] for o in people if o["id"] == owner), ""),
        # 탭마다 표가 다르다. 화면이 `{% if 이 탭이면 %}` 을 하나 더 심지 않게
        # **어느 탭인지**만 넘긴다(칸 목록은 아래 두 줄이 정한다).
        "is_contract_sheet": is_contract(db, selected),
        # `딜 소개문구` 는 이 탭에만 선다. `not is_contract_sheet` 로 갈랐다간
        # `경영본부 전달 기업` 에도 같이 서므로 **따로** 넘긴다.
        "is_startup_sheet": is_startup(db, selected),
        "fixed_columns": fixed,
        "tail_columns": tail,
        "msg": msg,
        "counts": {
            "total": len(rows),
            # 줄에 실어 보내는 표시와 **같은 값**을 센다. 여기서 규칙을 한 번 더
            # 적으면(`"관리" in …`) 그것이 두 번째 규칙이 되어, 한쪽만 고쳐질 때
            # 위에는 14 라고 적혀 있는데 칩을 누르면 13곳이 나온다.
            "managed": sum(1 for r in rows if r["managed"]),
            "dropped": sum(1 for r in rows if r["dropped"]),
            # **아직 안 한 곳**을 센다. 다 한 수를 보여 주던 칸이었는데, 그 수는
            # 봐도 할 일이 안 나온다 — 챙겨야 하는 것은 빈칸 쪽이다.
            #
            # 기준 달은 **지난달**이다. 진행 중인 달을 세면 월 초에는 전부
            # 미완료라 늘 전체 건수가 뜬다(그 칸은 이제 자동으로 생기므로 1일부터
            # 비어 있다). 놓친 것이 드러나는 것은 이미 지나간 달이다.
            #
            # 지난달 열이 아예 없으면 0 이다. 빈칸을 세면 "열이 없다" 가
            # "전부 미완료" 로 둔갑해 전체 건수가 그대로 뜬다.
            "pending": (sum(1 for r in rows if not r["contacted_prev"])
                        if prev_label else 0),
            "prev_month_label": prev_label,
            # 지난달 열이 **표에 서 있는가.** 이 수를 칸을 고친 자리에서 다시
            # 세는 것은 브라우저인데, 브라우저가 볼 수 있는 것은 펴 둔 달의
            # 칸뿐이다. 접혀 있으면 다시 셀 근거가 화면에 없으므로 아예 맡기지
            # 않는다 — 맡기면 전부 미완료로 뒤집힌다.
            # (`_split_columns` 가 석 달을 펴는 이유가 이 KPI 다. 열 순서가
            #  뒤죽박죽인 표에서만 지난달이 접힐 수 있다.)
            "prev_month_shown": bool(prev_label) and any(
                c.label == prev_label for c in shown),
            # `0월 마지막주 리마인드톡 미완료 기업` — 그 달 숫자를 넣는다.
            "pending_label": (f"{_prev_month()}월 마지막주 리마인드톡 미완료 기업"),
        },
    })
    return templates.TemplateResponse("consulting.html", ctx)


# --- 편집 -------------------------------------------------------------------

class CompanyIn(BaseModel):
    # 어느 탭의 줄인가. 이게 없어서 [기업 추가] 가 늘 첫 탭으로 들어갔다 —
    # 다른 탭에서 누른 사람 눈에는 **추가가 안 된 것처럼** 보인다(줄은 만들어
    # 졌는데 보고 있지 않은 탭에 있다).
    sheet: Optional[str] = None
    position: Optional[int] = None
    region: Optional[str] = None
    meeting_at: Optional[str] = None
    company_name: Optional[str] = None
    management: Optional[str] = None
    ceo_name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    # `월간 계약 업무현황표` 탭의 칸. **여기 안 적으면 화면에서 고쳐도 조용히
    # 안 저장된다** — pydantic 이 모르는 칸을 그냥 버리기 때문에 오류도 안 난다.
    success_fee: Optional[str] = None
    contract_fee: Optional[str] = None
    contract_received: Optional[str] = None
    # `관리 스타트업` 탭의 칸. **긴 글이라 줄바꿈이 그대로 들어온다** —
    # `_assign` 이 앞뒤 공백만 떼므로 가운데 줄바꿈은 살아서 저장된다.
    deal_pitch: Optional[str] = None
    # {"열id": "내용"} — 월별 리마인드
    notes: Optional[Dict[str, str]] = None


def _assign(company: ConsultingCompany, body: CompanyIn) -> None:
    data = body.model_dump(exclude_unset=True)
    notes = data.pop("notes", None)
    for field, value in data.items():
        setattr(company, field,
                value.strip() if isinstance(value, str) else value)
    if notes is not None:
        # 통째로 덮지 않고 병합한다 — 화면이 보내지 않은 달의 기록이 사라지면 안 된다.
        merged = _notes(company)
        merged.update({k: (v or "").strip() for k, v in notes.items()})
        company.notes = json.dumps({k: v for k, v in merged.items() if v},
                                   ensure_ascii=False)


@router.get("/api/consulting/{company_id}")
def get_company(company_id: int, db: Session = Depends(get_db),
                user: User = Depends(get_current_user)):
    require_access(user)
    # 남의 줄을 번호로 찍어 여는 길을 남기지 않는다.
    row = next((r for r in company_rows(db, user) if r["id"] == company_id), None)
    if row is None:
        raise HTTPException(status_code=404, detail="기업을 찾을 수 없습니다")
    return row


@router.post("/api/consulting")
def create_company(body: CompanyIn, db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)):
    require_access(user)
    if not (body.company_name or "").strip():
        raise HTTPException(status_code=400, detail="기업명을 입력하세요")

    # 화면이 보내 준 탭에 넣는다. 안 보내면 예전처럼 첫 탭이다.
    #
    # 아무 값이나 받으면 오타 하나로 **없던 탭이 생긴다** — `sheet_tabs` 가
    # 줄에 있는 시트 이름을 그대로 탭으로 올리기 때문이다. 지금 **화면에 서
    # 있는 탭 이름**만 받는다(사람이 시트를 올려 만든 탭도 거기 들어 있다).
    known = {t["key"] for t in sheet_tabs(db, user)}
    sheet = (body.sheet or "").strip()
    if sheet and sheet not in known:
        raise HTTPException(status_code=400, detail="없는 탭입니다")
    body.sheet = sheet or cs.default_label(db)

    if body.position is None:
        # 새 줄은 그 탭의 맨 아래로. 시트의 NO 를 사람이 매번 세지 않아도 되게.
        # **탭 안에서** 센다 — 전체에서 세면 다른 탭의 큰 번호를 물려받아,
        # 방금 넣은 줄이 자기 탭에서는 늘 맨 아래로 밀린다.
        last = db.execute(own(
            select(ConsultingCompany.position)
            .where(ConsultingCompany.sheet == body.sheet)
            .order_by(ConsultingCompany.position.desc()).limit(1),
            ConsultingCompany, user)
        ).scalar()
        body.position = (last or 0) + 1
    company = ConsultingCompany(user_id=user.id)
    _assign(company, body)
    db.add(company)
    db.commit()
    return {"id": company.id}


@router.patch("/api/consulting/{company_id}")
def update_company(company_id: int, body: CompanyIn,
                   db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)):
    require_access(user)
    company = owned(db, ConsultingCompany, company_id, user, "기업")
    _assign(company, body)
    db.commit()
    return {"id": company.id}


@router.delete("/api/consulting/{company_id}")
def delete_company(company_id: int, db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)):
    require_access(user)
    company = owned(db, ConsultingCompany, company_id, user, "기업")
    db.delete(company)
    db.commit()
    return {"deleted": company_id}


# --- 월별 열 ----------------------------------------------------------------

@router.post("/consulting/sheets/rename", include_in_schema=False)
def rename_sheet(kind: str = Form(""), label: str = Form(""),
                 db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    """탭 이름 바꾸기 — 투자사 관리 현황의 [이름 저장] 과 같은 방식·같은 어휘다.

    **줄이 같이 따라간다.** `ConsultingCompany.sheet` 와 `ConsultingColumn.sheet`
    가 이름을 그대로 담고 있어서, 이름만 바꾸면 그 줄들이 어느 탭에도 안 뜬다 —
    옛 이름의 유령 탭으로 갈라진다(0039 가 고쳐야 했던 그 사고). 옮기는 것은
    `services/consulting_sheets.rename` 한 곳이 한다.

    **바꾸는 것은 화면 글자뿐이다.** 표 모양은 바뀌지 않는 열쇠(`kind`)로
    고르므로(`SHEET_LAYOUTS`), `월간 계약 업무현황표` 를 다른 이름으로 불러도
    계약 표 그대로다.

    이 화면을 볼 수 있는 사람이면 바꿀 수 있다 — 투자사 관리 현황의 명단 이름
    바꾸기와 같은 권한이다. 수나 발송 대상이 바뀌는 조작이 아니라서(그런 것은
    관리자만 한다) 여기서 더 조이지 않는다.
    """
    require_access(user)
    sheet = cs.rename(db, (kind or "").strip(), label)
    if sheet is None:
        db.rollback()
        return RedirectResponse(
            "/consulting?msg=이미+쓰고+있는+탭+이름입니다", status_code=303)
    db.commit()
    return RedirectResponse(
        f"/consulting?sheet={quote(sheet.label)}", status_code=303)


@router.post("/consulting/columns", include_in_schema=False)
def add_column(label: str = Form(...), db: Session = Depends(get_db),
               user: User = Depends(get_current_user)):
    """달이 바뀌면 열을 하나 늘린다. 새 열이 **맨 앞**에 오도록 한다.

    지금 챙겨야 할 달이 먼저 보여야 한다. (시트가 늘 그 순서인 것은 아니다 —
    `services/monthly_columns.py` 참고. 새로 세우는 자리를 정하는 것뿐이다.)
    """
    require_access(user)
    label = label.strip()
    if not label:
        return RedirectResponse("/consulting?msg=열+이름을+입력하세요", status_code=303)
    for col in _my_columns(db, user):
        col.position += 1
    # **어느 탭의 열인지 여기서 정해 준다.** 안 주면 모델 기본값(`스타트업`)으로
    # 떨어지는데, 탭 이름을 고친 뒤에는 그 이름을 쓰는 탭이 없어서 새 열이
    # 유령 탭에 쌓인다 — 세운 사람 화면에는 아무것도 안 늘어난다.
    db.add(ConsultingColumn(label=label, position=0, user_id=user.id,
                            sheet=cs.default_label(db)))
    db.commit()
    return RedirectResponse(f"/consulting?msg={label}+열을+추가했습니다", status_code=303)


@router.post("/consulting/columns/{column_id}/rename", include_in_schema=False)
def rename_column(column_id: int, label: str = Form(...),
                  db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    require_access(user)
    # 열도 사람마다 다르다 — 남의 달 이름을 바꾸면 그 사람 표의 머리글이 바뀐다.
    col = owned(db, ConsultingColumn, column_id, user, "열")
    if label.strip():
        col.label = label.strip()
        db.commit()
    return RedirectResponse("/consulting?msg=열+이름을+바꿨습니다", status_code=303)


@router.post("/consulting/columns/{column_id}/delete", include_in_schema=False)
def delete_column(column_id: int, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    """열을 지우면 그 달의 기록도 함께 사라진다 — 화면에서 한 번 더 묻는다."""
    require_access(user)
    col = owned(db, ConsultingColumn, column_id, user, "열")
    key = str(col.id)
    # 기록을 지우는 범위도 **보는 범위와 같다.** 전체를 훑으면 자기 열을 지우는
    # 것뿐인데 손은 남의 줄까지 닿는다 — 열 번호가 겹치는 날 남의 기록이
    # 조용히 사라진다.
    for company in db.execute(
        own(select(ConsultingCompany), ConsultingCompany, user)
    ).scalars().all():
        notes = _notes(company)
        if key in notes:
            notes.pop(key)
            company.notes = json.dumps(notes, ensure_ascii=False)
    db.delete(col)
    db.commit()
    return RedirectResponse("/consulting?msg=열을+삭제했습니다", status_code=303)


# --- 업로드 · 내려받기 ------------------------------------------------------

@router.post("/consulting/import", include_in_schema=False)
def import_sheet(file: UploadFile = File(...), sheet: str = Form(""),
                 replace: bool = Form(False),
                 db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    """원본 시트를 올려 통째로 반영한다.

    이 표는 시트가 원본이라 '한 줄씩 맞추기'보다 **통째로 갈아끼우는** 편이 맞다.
    다만 여기서 고친 내용이 날아갈 수 있으므로 화면에서 한 번 더 확인받는다.
    """
    require_access(user)
    data = file.file.read()
    try:
        rows = sp.read_rows(file.filename or "", data, sheet or None)
    except sp.SpreadsheetError as exc:
        return RedirectResponse(f"/consulting?msg={exc}", status_code=303)

    parsed = parse_rows(rows)
    if not parsed["companies"]:
        return RedirectResponse(
            "/consulting?msg=읽을+내용을+찾지+못했습니다.+'NO'와+'기업명'이+있는+시트인지+확인하세요",
            status_code=303)

    report = apply_rows(db, parsed, user, replace=replace)
    return RedirectResponse(
        f"/consulting?msg=기업+{report['created']}건+추가·{report['updated']}건+갱신"
        f"+(열+{report['columns']}개)",
        status_code=303)


CONSULTING_EXPORT_HEADERS = [label for label, _ in FIXED_COLUMNS]
# 계약 탭에만 값이 있는 칸. 엑셀은 탭을 가리지 않고 한 장으로 내려받으므로
# **머리글 한 벌**에 뒤로 붙인다 — 탭마다 다른 장을 만들면 내려받은 파일에서
# 어느 장이 무엇인지 다시 맞춰야 한다. 다른 탭 줄에서는 빈 칸이다.
CONTRACT_EXPORT_HEADERS = ["성공보수율", "계약금", "계약서 수신여부"]
# 스타트업 탭에만 값이 있는 칸. **엑셀에는 싣는다** — 화면에 보이는 칸이
# 내려받은 파일에만 없으면, 없다는 사실 자체를 아무도 눈치채지 못한 채 그
# 파일이 보고서로 돌아다닌다. 바로 옆 `기업 관리` 도 같은 성격의 긴 글인데
# 이미 실려 있어서, 둘 중 하나만 빠지면 그게 더 이상하다.
#
# 자리는 **맨 뒤**다. 화면 순서대로 `기업 관리` 옆에 끼우면 그 뒤 월 열이
# 통째로 한 칸씩 밀려, 지난번에 내려받아 둔 파일과 나란히 놓고 볼 수가 없다
# (계약 탭 칸들도 같은 이유로 뒤에 붙어 있다).
STARTUP_EXPORT_HEADERS = ["딜 소개문구"]


@router.get("/api/export/consulting.xlsx")
def export_consulting(db: Session = Depends(get_db),
                      user: User = Depends(get_current_user)):
    require_access(user)
    cols = _columns(db, user)
    # **화면과 같은 칸이 선다.** 여러 사람의 표를 한 파일로 내려받으면서 담당이
    # 없으면 누구 줄인지 알 수 없다 — 화면에는 `담당` 칸이 서 있는데 받은
    # 파일에만 없으면, 그 파일을 여는 사람은 55줄을 한 사람 것으로 읽는다.
    # 자기 것만 보는 사람에게는 안 세운다(같은 이름이 줄마다 반복될 뿐이다).
    owned_col = may_view_all_consulting(user)
    headers = (CONSULTING_EXPORT_HEADERS + (["담당"] if owned_col else [])
               + [c.label for c in cols]
               + [label for label, _ in TAIL_COLUMNS] + CONTRACT_EXPORT_HEADERS
               + STARTUP_EXPORT_HEADERS)
    rows = [
        [r["no"], r["region"], r["meeting_at"], r["company_name"], r["management"]]
        + ([r["owner_name"]] if owned_col else [])
        + [r["notes"].get(str(c.id), "") for c in cols]
        + [r["ceo_name"], r["phone"], r["email"]]
        + [r["success_fee"], r["contract_fee"], r["contract_received"]]
        + [r["deal_pitch"]]
        for r in company_rows(db, user)
    ]
    try:
        content = sp.write_xlsx("투자컨설턴트 현황", headers, rows)
    except sp.SpreadsheetError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    from datetime import date

    return Response(content=content, media_type=sp.XLSX_MEDIA_TYPE,
                    headers=sp.content_disposition(
                        f"투자컨설턴트 현황_{date.today().isoformat()}.xlsx"))


# --- 시트 읽기 --------------------------------------------------------------

def _norm(value) -> str:
    return " ".join(str(value or "").split())


def parse_rows(rows: List[List[str]]) -> dict:
    """시트 → {열 이름들, 기업 행들}.

    머리행은 위치가 아니라 **내용**으로 찾는다. 시트 위쪽에 제목·빈 줄이 있고
    사람이 행을 넣다 빼다 하므로 '4번째 줄'이라고 못 박으면 곧 깨진다.
    """
    header_idx = None
    for i, row in enumerate(rows[:30]):
        cells = [_norm(c) for c in row]
        if "NO" in cells and any("기업" in c for c in cells):
            header_idx = i
            break
    if header_idx is None:
        return {"columns": [], "companies": []}

    header = [_norm(c) for c in rows[header_idx]]

    def find(*tokens) -> Optional[int]:
        for j, h in enumerate(header):
            if all(t in h for t in tokens):
                return j
        return None

    idx = {
        "position": find("NO"),
        "region": find("지역"),
        "meeting_at": find("미팅일"),
        "company_name": find("기업명"),
        "management": find("기업 관리"),
        "ceo_name": find("대표자"),
        "phone": find("연락처"),
        "email": find("이메일"),
    }
    # 나머지 = 월별 리마인드 열. 이름을 그대로 쓴다(시트와 같아 보여야 한다).
    used = {v for v in idx.values() if v is not None}
    note_cols = [(j, header[j]) for j in range(len(header))
                 if j not in used and header[j]]

    companies = []
    for row in rows[header_idx + 1:]:
        cells = list(row) + [""] * (len(header) - len(row))
        name = _norm(cells[idx["company_name"]]) if idx["company_name"] is not None else ""
        no = _norm(cells[idx["position"]]) if idx["position"] is not None else ""
        if not name and not no:
            continue
        if not name:
            continue        # 번호만 있고 기업명이 없는 줄은 빈 칸이다
        item = {"notes": {}}
        for field, j in idx.items():
            if j is None:
                continue
            raw = cells[j]
            item[field] = _norm(raw)
        for j, label in note_cols:
            text = _norm(cells[j])
            if text:
                item["notes"][label] = text
        companies.append(item)

    return {"columns": [label for _j, label in note_cols], "companies": companies}


def apply_rows(db: Session, parsed: dict, user: User,
               replace: bool = False) -> dict:
    """읽은 내용을 DB 에 반영. 기업명이 같으면 갱신, 없으면 추가.

    올린 사람의 표가 된다 — 남의 표를 덮지 않는다.
    """
    if replace:
        # **내 것만** 지운다. 예전에는 전체를 지워서, 한 사람이 다시 올리면
        # 다른 컨설턴트의 표까지 사라졌다.
        db.query(ConsultingCompany).filter(
            ConsultingCompany.user_id == user.id).delete()
        db.commit()

    # 열 먼저 — 기업의 notes 가 열 id 를 키로 쓴다
    existing_cols = {c.label: c for c in _my_columns(db, user)}
    for pos, label in enumerate(parsed["columns"]):
        col = existing_cols.get(label)
        if col is None:
            col = ConsultingColumn(label=label, position=pos, user_id=user.id)
            db.add(col)
            existing_cols[label] = col
    db.flush()

    # 같은 기업명이 다른 사람 표에도 있을 수 있다 — 내 표 안에서만 맞춘다.
    by_name = {(c.company_name or "").strip(): c
               for c in db.execute(own(select(ConsultingCompany),
                                       ConsultingCompany, user)).scalars().all()}

    created = updated = 0
    for item in parsed["companies"]:
        name = item.get("company_name", "")
        company = by_name.get(name)
        if company is None:
            company = ConsultingCompany(user_id=user.id)
            db.add(company)
            by_name[name] = company
            created += 1
        else:
            updated += 1
        for field in ("region", "meeting_at", "company_name", "management",
                      "ceo_name", "phone", "email"):
            value = item.get(field)
            if value:
                setattr(company, field, value)
        raw_no = item.get("position") or ""
        digits = "".join(ch for ch in raw_no if ch.isdigit())
        if digits:
            company.position = int(digits)
        notes = _notes(company)
        for label, text in item["notes"].items():
            col = existing_cols.get(label)
            if col is not None:
                notes[str(col.id)] = text
        company.notes = json.dumps(notes, ensure_ascii=False)

    db.commit()
    return {"created": created, "updated": updated,
            "columns": len(parsed["columns"])}
