"""딜 소싱 — 우리 딜을 같이 볼 사람 명단.

투자사 관리 현황(딜소개를 **보내는** 명단)과는 성격이 다르다. 여기는
시리즈 A 이상·개인 참여·M&A·후속투자처럼 **찾는 것**으로 나뉘고, 같은
사람이 여러 갈래에 들어갈 수 있다.

여기서는 **보고 고친다.** 실제로 보내는 것은 딜 제안 관리의 [딜 소싱 제안]
탭이고, 그 대상이 이 표다 — 그래서 카톡방 이름 칸이 여기 있다.
"""
from __future__ import annotations

import re
from datetime import date
from typing import List, Optional

from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_current_user, no_send_as_member, templates
from ..models import SendItem, SendJob, SourcingContact, User
from ..services import (series_a_share, sourcing_buckets, sourcing_link,
                        sourcing_mail, sourcing_receipts, sourcing_rooms,
                        sourcing_sync, spreadsheet)
from ..services import custom_columns, sourcing_remind_log, taxonomy
from ..services.pipeline import current_assignee
from ..ui import base_ctx
# 방 확인 잡의 종류는 **한 곳에만 적는다**(`agent_api.VERIFY_KIND`).
from .agent_api import VERIFY_KIND

router = APIRouter(tags=["sourcing"])

# 표 컬럼 — 원본 시트 순서 그대로. 쓰던 사람이 같은 자리에서 같은 것을 찾는다.
# 앱이 만든 `참여` 칸만 예외로 **이름 바로 뒤**에 둔다 — 표가 화면보다 넓어
# 맨 오른쪽에 두면 가로로 끝까지 밀어야 보였다. 불참여인 분은 제안에서
# 빠지므로, 이름과 나란히 한눈에 보여야 한다.
#
# 네 번째 값은 **머리글에 필터를 세울 칸인가**. 여기 한 곳에서만 정한다 —
# 전에는 템플릿이 `field in ('assignee_name', 'sectors', 'round_size')` 라는 같은
# 목록을 머리글과 행에 나눠 적고 있어서, 한쪽만 고치면 선언은 있는데 행이 값을
# 안 싣는(=열어도 늘 빈 목록) 필터가 조용히 생긴다.
#
# 거는 기준은 **고를 만한 값이 몇 가지로 모이는가**다(실데이터 39행 기준):
#   담당자 5종 · 선호 투자분야 6종 · 참여 요청일 12종 · 라운드 사이즈 13종 ·
#   직함 18종                                        → 건다
#   이름 35 · 회사 29 · 휴대폰 29 · 이메일 26종      → 줄마다 달라 고를 것이 없다
#   메모(자유 문장, 최대 75자)                       → 목록 한 줄에 담기지 않는다
#   카톡방 이름(39행 모두 빈칸, 채우면 방 제목이라
#               역시 줄마다 다르다)                  → 지금도 앞으로도 거를 값이 없다
#
# 폭은 **이름이 아니라 단추**에 맞춘다. 필터가 하나뿐인 칸은 filters.js 가 이름
# 글자를 지우고 `담당자 ▾` 단추를 그 자리에 세우는데, 단추는 ` ▾` 와 자기
# padding·테두리만큼 이름보다 넓다 — 담당자(72px)가 그래서 두 줄로 접혀 있었다.
COLUMNS = [
    ("requested_at", "참여 요청일", "124px", True),
    # 이름 밑에 [삭제] · `☐ 10월 딜 받음` 단추가 선다(sourcing.html). 96px 에서는
    # 그 단추가 `10월 딜 받 / 음` 으로 접혀 줄마다 키가 늘었다 — 단추가 한 줄에 드는 폭.
    ("name", "이름", "150px", False),
    # ── 앱이 만든 칸. 원본 시트에는 없다 ──
    # `참여` · `불참여` · `참여 의사를 물어보는 중` + 사람이 적은 문구. 몇 가지로
    # 모이는 값이라 거른다. **월간 리마인드 · Series A 딜 공유는 정확히 `참여` 인
    # 분께만**(`sourcing_sync.takes_part`), 참여 안내(처음)는 제안 대기중 · 물어보는
    # 중에게만 나간다(`can_get_invite`). 잇는 세
    # 갈래(Series A · M&A · 구주·후속)의 줄은 투자사 관리 현황의 `딜 소싱` 칸 딱지가
    # 이 값에서 선다 — `불참여` 만 흐린 딱지(`services/sourcing_sync.py`).
    ("participation", "참여", "84px", True),
    ("assignee_name", "담당자", "100px", True),
    ("phone", "휴대폰", "116px", False),
    ("title", "직함", "88px", True),
    # 투자사 관리 현황과 같은 저장 칸은 **그 화면의 머리글 그대로** 부른다(#63 —
    # 사용자 결정 2026-10-20). 폭도 그 화면의 같은 칸과 같다(필터 단추가 한 줄에 든다).
    ("email", "전자 메일 주소", "170px", False),
    ("firm", "회사", "150px", False),
    ("sectors", "선호 투자분야", "134px", True),
    ("round_size", "라운드 사이즈(투자운영금액)", "204px", True),
    ("memo", "메모", "", False),
    # 여기서 딜 소싱 제안을 보낸다 — 방 이름이 없으면 보낼 길이 없다.
    # 발송 화면(딜 제안 관리)에서 고를 수 있으려면 이 칸이 먼저 차야 한다.
    ("kakao_room_name", "카톡방 이름", "170px", False),
]

# ── 월간 리마인드 이력 칸(#14) — `COLUMNS` 밖의 읽기 전용 칸 ─────────────────
# 지난 석 달(`8월 리마인드` `9월 리마인드` `10월 리마인드`) — 그 달 이 분께
# 리마인드가 나간 시각과 `자동` · `수동`(`services/sourcing_remind_log.py`).
#
# `COLUMNS` 에 넣지 않는다. 그 목록은 **고칠 수 있는 칸**이라 행마다 같은 이름의
# `data-field` 가 서고(tests/test_sourcing.py 가 지킨다), 달은 매달 바뀌어 고정된
# 이름이 없다. 머리글은 아래 자리 뒤에 끼워 세우고, 행은 그 칸 바로 뒤에 손으로
# 적는다(`sourcing.html`) — 고치지도 거르지도 않는다.
#
# 자리는 **`참여` 바로 뒤.** 이 칸은 사람마다 읽는다("이분께 이 달 리마인드가
# 갔나") — 그래서 이름 · `딜 받음`(이름 밑) · `참여`(불참여면 리마인드에서 빠진다)
# 와 나란히 있어야 한 눈에 읽힌다. 맨 오른쪽이면 `참여` 를 옮겨 온 까닭(가로로
# 끝까지 밀어야 보였다)이 그대로 되풀이된다.
REMIND_AFTER = "participation"


def buckets(db: Session) -> List[dict]:
    """갈래별 인원. 탭에 건수를 띄운다 — 어디에 사람이 있는지 알아야 한다.

    **탭 차례는 `position` 그대로다.** 갈래는 원본 시트의 탭 순서이고
    (`scripts/import_sourcing.py` 가 `시트번호 * 1000 + 줄번호` 로 넣는다),
    그 차례는 날짜와 아무 상관이 없다 — 갈래를 요청일로 세우면 누가 어느 날
    참여를 수락했느냐에 따라 왼쪽 탭이 매일 자리를 바꾼다. 명단 안에서 무엇이
    위로 오는지(아래 `rows_of`)와 **갈래가 늘어선 차례는 다른 판단**이다.

    **띄어쓰기만 다른 글자는 탭 하나다**(`sourcing_buckets.groups`) — 수는 합친
    것, 이름은 그 갈래가 쓰는 글자. `variants` 는 그 탭에 묶인 저장 글자들이다.
    """
    out = [{"key": g["label"], "label": g["label"], "count": g["count"],
            "pos": g["pos"], "variants": g["variants"]}
           for g in sourcing_buckets.groups(db)]
    return sorted(out, key=lambda x: (x["pos"], x["label"]))


# 참여 요청일은 **사람이 손으로 적은 글자**다(`String`). 그래서 표기가 이미
# 섞여 있다 — 실측 40줄 중 `2026-07-01 00:00:00` 16곳 · `2026/05/21` 9곳 ·
# 빈 곳 10곳.
#
# **글자로 정렬하면 틀린다.** `/`(0x2F) 가 `-`(0x2D) 보다 커서, 내림차순이면
# `2026/05/21` 이 `2026-08-11` 보다 위로 올라온다 — 최신순이라고 해 놓고 석 달
# 전 줄이 맨 위에 서는 것이라 정렬이 없느니만 못하다. 반드시 날짜로 읽는다.
#
# **저장된 글자는 고치지 않는다.** 표기를 맞추겠다고 값을 바꾸면 사람이 적어
# 둔 원문이 사라진다. 화면은 적힌 그대로 보여 주고, 차례를 잡을 때만 해석한다.
#
# 끝을 막지 않는다 — 뒤에 시각(`00:00:00`)이나 말이 붙어도 앞의 날짜로 자리를
# 잡는 편이, 통째로 '날짜 없음' 으로 밀어 내는 것보다 낫다. `수신일` 을 읽는
# `routers/companies.py` 의 `_DATED` 와 같은 판단이고, 거기서 보지 않는 `/` 와
# `.` 을 여기서 함께 보는 것은 이 칸의 실데이터가 그렇게 섞여 있기 때문이다.
_DATED = re.compile(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})")


def requested_on(row: SourcingContact) -> Optional[date]:
    """참여 요청일을 날짜로. 못 읽으면 `None` — 그 줄은 맨 아래로 간다."""
    found = _DATED.match((row.requested_at or "").strip())
    if found is None:
        return None
    try:
        return date(*(int(part) for part in found.groups()))
    except ValueError:
        # 달력에 없는 날(`2026-02-31`). 날짜처럼 생겼을 뿐 날짜가 아니다.
        return None


def requested_sort(row: Optional[SourcingContact]) -> str:
    """머리글 정렬 값(`data-s-*`) — 날짜로 읽히면 `YYYY-MM-DD`, 아니면 빈칸.

    화면 글자는 표기가 섞여 있어 브라우저(`table_sort.js`)가 글자로 세우면 틀린다
    (위 `_DATED` 주석). 여기서 날짜로 읽어 한 꼴로 넘긴다. 빈칸은 방향과 상관없이
    늘 끝이다. 투자사 관리 현황의 같은 칸도 이것이다(이어진 줄이 없으면 `None`)."""
    day = requested_on(row) if row is not None else None
    return day.isoformat() if day else ""


def rows_of(db: Session, bucket: str = "") -> List[SourcingContact]:
    """명단을 뿌릴 차례. **정렬 판단은 이 함수 한 곳**이다.

    딜 제안 관리의 [딜 소싱 제안] 목록도 여기를 지난다(`routers/pages.py`) —
    두 화면이 각자 `order_by` 를 들고 있으면 한쪽만 고쳐지는 날 같은 명단이
    화면마다 다른 순서로 뜬다.

    **참여 요청일 최신순.** 이 명단은 "언제 참여하겠다고 했나" 로 읽는 자리라,
    방금 수락한 사람이 맨 위에 있어야 그 사람부터 연락한다.

    날짜를 못 읽는 줄과 빈 줄(실측 40줄 중 10줄)은 **맨 아래**다. 위로 올리면
    '최신순' 이라는 말이 거짓이 되고, 사이에 섞으면 어디까지가 날짜순인지 눈으로
    가를 수 없다.

    `position` 은 뜻을 잃은 것이 아니라 **한 칸 뒤로** 물러났다. 이 칸은 원본
    시트에서 옮겨 온 차례이자 새 줄이 그 갈래 맨 아래로 가는 근거(`add_row`)이지,
    사람이 끌어 옮기는 차례가 아니다 — 고칠 길이 아예 없다(`SourcingIn` 에도
    화면에도 `position` 이 없다). 그래서 **같은 날짜 안**과 **날짜 없는 줄들
    사이**의 차례로 남긴다: 질의가 `position, id` 로 세워 둔 것을 파이썬의 **안정
    정렬**이 그대로 보존한다. 요청일이 같은 두 줄은 여전히 시트 순서이고, 요청일
    없이 방금 넣은 줄은 여전히 그 갈래 맨 아래다.
    """
    stmt = select(SourcingContact).order_by(SourcingContact.position, SourcingContact.id)
    if bucket:
        # 탭 하나에 묶인 글자 전부(띄어쓰기만 다른 것 — `buckets`).
        stmt = stmt.where(
            SourcingContact.bucket.in_(sourcing_buckets.variants(db, bucket)))
    dated: List[SourcingContact] = []
    undated: List[SourcingContact] = []
    for row in db.execute(stmt).scalars().all():
        (dated if requested_on(row) is not None else undated).append(row)
    dated.sort(key=requested_on, reverse=True)
    return dated + undated


# ── 담당 — 두 화면의 [담당] 필터가 읽는 값 ─────────────────────────────────
#
# `담당자` 칸에는 넘긴 이력이 쌓인다(`가담당 > 10/13 나담당` · `가 > 나 > 다` ·
# `백업팀 > 나담당`). 그 글자를 통째로 필터 값으로 쓰면 **넘겨받은 사람의 칩에
# 그 줄이 안 잡히고** 이력 글자가 칩 하나로 따로 선다 — 딜 소싱에서 담당을
# 바꿔도 딜 제안 관리의 [담당] 필터가 그대로인 것처럼 보였다.
#
# 지금 맡은 사람을 읽는 규칙은 **저장소에 하나**다(`pipeline.current_assignee`
# — 캘린더 제목의 담당자도 같은 함수를 지난다). 여기서 따로 자르면 화면마다
# 다른 사람이 담당으로 선다. 칸에 적힌 글자는 그대로 둔다 — 이력은 그 칸에서
# 관리하는 것이다.

def assignee_of(row: SourcingContact) -> str:
    """이 줄을 **지금** 맡은 사람. 미덥지 않으면 빈 글자(지어내지 않는다)."""
    return current_assignee(row.assignee_name)


def assignee_chips(rows: List[SourcingContact]) -> List[dict]:
    """[담당] 필터의 칩 — 지금 맡은 사람마다 몇 명인지, 많은 순.

    딜 제안 관리(`routers/pages.py`)와 아래 상태 API 가 함께 쓴다 — 화면을 그릴
    때와 다시 읽을 때 칩이 같은 규칙으로 서야 한다.
    """
    counted: dict = {}
    for row in rows:
        who = assignee_of(row)
        if who:
            counted[who] = counted.get(who, 0) + 1
    return [{"name": k, "count": v}
            for k, v in sorted(counted.items(), key=lambda kv: (-kv[1], kv[0]))]


@router.get("/api/sourcing/state")
def sourcing_state(db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)):
    """딜 소싱 명단의 **지금** 담당 · 이 달 `딜 받음` — 딜 제안 관리가 다시 읽는다.

    딜 제안 관리는 화면을 그릴 때 명단을 한 번 싣는다. 그 화면을 열어 둔 채
    딜 소싱 메뉴에서 담당을 바꾸거나 `딜 받음` 을 누르면(메일 확인이 세우기도
    한다) 열어 둔 화면은 옛 값을 들고 있다 — [딜 소싱 제안] 탭을 열 때와 창으로
    돌아올 때 이것을 다시 읽어 칩과 카드를 고친다(`deals.js`).
    """
    rows = rows_of(db)
    month = sourcing_receipts.month_of()
    got = sourcing_receipts.received_ids(db, month)
    # `out` — 그 사이 어떤 글도 안 받는 분이 된 줄(`불참여` · 사람이 적은 문구 —
    # `_listed`). `invite_only` — 참여 안내(처음)만 받는 줄(제안 대기중 · 물어보는
    # 중 — `sourcing_sync.can_get_invite`). 딜 제안 관리가 그 카드를 글에 따라 막고
    # `out_label` 을 딱지로 단다(`deals.js`). 칩은 화면을 그릴 때
    # (`sendable_rows(invite=True)`)와 같은 모집단이어야 칩 수가 다시 읽을 때 흔들리지 않는다.
    return {"month": month, "month_label": f"{int(month[5:])}월",
            "rows": [{"id": r.id, "assignee": assignee_of(r),
                      "received": r.id in got,
                      "out": not _listed(r),
                      "invite_only": sourcing_sync.can_get_invite(r),
                      "out_label": out_label(r)} for r in rows],
            "assignees": assignee_chips([r for r in rows if _listed(r)])}


def _listed(row: SourcingContact) -> bool:
    """딜 제안 관리 목록에 카드가 있는가 — 어느 글이든 받는 분(참여 · 제안 대기중 · 물어보는 중)."""
    return sourcing_sync.takes_part(row) or sourcing_sync.can_get_invite(row)


def sendable_rows(db: Session, invite: bool = False) -> List[SourcingContact]:
    """딜 소싱 제안을 **받는** 분 — `참여` 인 분만(`sourcing_sync.takes_part`), 차례는
    `rows_of` 그대로. `불참여` · `참여 의사를 물어보는 중` · 사람이 적은 문구는 빠진다.

    `invite=True` 면 참여 안내(처음)를 받는 분까지(`can_get_invite` — 제안 대기중 ·
    물어보는 중). 딜 제안 관리의 [딜 소싱 제안] 목록 · 칩이 그것을 싣는다. 참여 안내를
    고르면 그 카드만, 다른 글을 고르면 `참여` 카드만 고를 수 있다(`deals.js` 의
    `data-invite-only`). 발송 길(`routers/deals.create_send_list`)도 같은 판정으로
    한 번 더 보고 막는다.
    """
    return [r for r in rows_of(db) if (_listed(r) if invite else sourcing_sync.takes_part(r))]


#: 받지 않는 분의 딱지 — 딜 제안 관리 카드(`deals.html` 의 `out-tag`)와 빠진 수 말.
LEFT_LABEL = "딜 소싱 불참여"
PENDING_LABEL = "참여 확인 전"


def out_label(row: SourcingContact) -> str:
    """받지 않는 분의 딱지 글자. 받는 분이면 빈 글자.

    `참여 확인 전 · 참여 의사를 물어보는 중` 처럼 **적힌 값을 그대로** 붙인다 —
    사람이 적은 문구(`11월 재연락`)도 무슨 사정인지 카드에서 읽혀야 한다."""
    kind = sourcing_sync.kind_of(row)
    if kind == sourcing_sync.KIND_JOINED:
        return ""
    if kind == sourcing_sync.KIND_LEFT:
        return LEFT_LABEL
    return f"{PENDING_LABEL} · {sourcing_sync.participation_of(row)}"


def held_counts(db: Session) -> dict:
    """참여 안내(처음)에서 **뺀** 분의 수 — `{"joined": 참여, "left": 불참여, "custom": 문구}`.

    딜 제안 관리가 참여 안내를 고르면 목록 위에 `참여 중 N명·불참여 M명·직접 문구 K명은
    참여 안내 대상이 아니라 뺐습니다` 로 적는다(`deals.html` 의 `sourcing-held`). 조용히
    빼면 왜 그분이 안 보이는지 모른다. 남는 것은 제안 대기중 · 물어보는 중뿐이다.
    """
    out = {"joined": 0, "left": 0, "custom": 0}
    for row in rows_of(db):
        if sourcing_sync.takes_part(row):
            out["joined"] += 1
        elif sourcing_sync.is_left(row):
            out["left"] += 1
        elif not sourcing_sync.can_get_invite(row):
            out["custom"] += 1
    return out


def _pick_tab(tabs: List[dict], tab: str) -> str:
    """주소의 `tab` → 열 갈래(`""` = 전체). 화면과 엑셀이 같은 탭을 읽는다.

    아무 것도 고르지 않았으면 첫 갈래를 연다. 전체를 먼저 보여주면 갈래가
    나뉜 뜻이 사라진다. 띄어쓰기만 다른 글자로 와도 그 탭이다(예전 주소 ·
    코드의 글자)."""
    opened = next((t["key"] for t in tabs
                   if tab and sourcing_buckets.same(t["key"], tab)), None)
    if opened is not None:
        return opened
    return tabs[0]["key"] if tabs and tab != "all" else ""


@router.get("/sourcing", response_class=HTMLResponse, include_in_schema=False)
def sourcing_page(request: Request, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user), tab: str = "",
                  msg: str = ""):
    tabs = buckets(db)
    selected = _pick_tab(tabs, tab)
    rows = rows_of(db, selected)
    ctx = base_ctx(request, db, user, active="sourcing")
    # 투자사 관리 현황에서 이미 방을 연결해 둔 사람이면 다시 적을 이유가 없다.
    linked = sourcing_link.linked_rooms(db, rows)
    # 이 달 `딜 받음` — 사람이 누르거나 메일 확인이 저절로 세운다
    # (`services/sourcing_receipts.py` · `services/sourcing_mail.py`).
    month = sourcing_receipts.month_of()
    receipts = sourcing_receipts.receipts(db, month)
    ctx.update({
        "month": month,
        "month_label": f"{int(month[5:])}월",
        "received": set(receipts),
        # 메일로 선 표시는 `(메일 10/15)` 로 — 어느 메일로 섰는지.
        "mail_marks": {cid: {"day": sourcing_mail.day_stamp(r.mail_at),
                             "subject": r.mail_subject or ""}
                       for cid, r in receipts.items()
                       if r.source == sourcing_receipts.SOURCE_MAIL},
        # 머리 줄 — `메일 확인: 마지막 10/15 18:00 · 이번 달 메일로 받은 분 N명 · …`.
        "mail_check": sourcing_mail.page_status(db),
        "is_admin": user.role == "admin",
        "linked_rooms": linked,
        # 투자사 관리 현황의 줄과 **이어진** 줄 — `🔗 투자사 관리 현황: ○○ 명단`.
        # 세 갈래(Series A · M&A · 구주·후속 — `sourcing_sync.BRANCHES`)만 이어진다.
        # 풍선말(어느 칸이 같이 바뀌는지)도 여기 실려 온다(`badges` 의 `title`).
        # [연결 풀기]를 누를 수 있는지도(`can_unlink` — `_may_unlink`).
        "vc_links": _badges(db, rows, user),
        # `참여 요청일` 칸 · 거를 값 — 날짜 뒤에 붙은 시각을 뗀다(저장값은 그대로,
        # `sourcing_sync.requested_label` — 투자사 관리 현황의 같은 칸도 이것이다).
        "requested": {r.id: sourcing_sync.requested_label(r.requested_at) for r in rows},
        # 머리글을 눌러 세울 값(`requested_sort`) — 위 글자가 아니라 날짜로.
        "requested_sort": {r.id: requested_sort(r) for r in rows},
        # 저절로 못 이은 세 갈래 줄의 **후보** — [이 분으로 확정](#28).
        # 이름 · 번호가 둘 다 같아야 저절로 잇고, 나머지는 사람이 고른다.
        "vc_picks": sourcing_sync.link_candidates(db, rows),
        # **보낼 방이 없는 줄** — 자기 방 이름도 이어받을 방도 없다
        # (`sourcing_rooms.needs_room` — 발송이 방을 고르는 규칙과 같다).
        # 그 줄에 `방 없음` 과 [방 후보 찾기] 가 서고, 툴바 [방 후보 찾기]는 체크한
        # 줄 중 이 줄만 싣는다(`data-no-room`).
        "no_room": {r.id for r in sourcing_rooms.needs_room(db, rows)},
        # `참여` 칸의 갈래 — `joined` · `left` · `pending`(물어보는 중 · 사람이 적은
        # 문구). 칸 색과 [Series A 딜 소개]가 빼는 수를 이것으로 정한다
        # (`sourcing_sync.kind_of` — 규칙은 서버 한 곳).
        "part_kind": {r.id: sourcing_sync.kind_of(r) for r in rows},
        # 고르는 칸이 먼저 세우는 보기 — 이 밖의 글도 직접 적을 수 있다.
        "participation_choices": ",".join(sourcing_sync.CHOICES),
        # [방 후보 찾기] 가 담아 온 후보 · 상태(`services/sourcing_rooms.py`).
        "room_picks": {r.id: sourcing_rooms.picks(r) for r in rows},
        "tabs": tabs,
        "selected": selected,
        "columns": COLUMNS,
        "rows": rows,
        # `선호 투자분야` 를 고를 거리 — 투자사 관리 현황과 같은 분야 기준 목록(#63).
        "sector_tree": taxonomy.picker_tree(db),
        # [담당자] 필터가 거르는 값 — 칸에 적힌 글자가 아니라 **지금 맡은 사람**
        # (`assignee_of`). 딜 제안 관리의 [담당] 칩과 같은 값이다.
        "assignees": {r.id: assignee_of(r) for r in rows},
        # ── Series A 딜 공유 (`services/series_a_share.py`) ──
        # 줄마다 받은 기업 이름 — `Series A 딜 공유 N건` 과 그 풍선말.
        "shared": series_a_share.shared_companies(db, [r.id for r in rows]),
        # [Series A 딜 소개] 단추는 이 갈래 탭에만 선다 — 이 글을 받는 갈래가
        # 하나뿐이다(투자사 관리 현황과 이어진 갈래). 단추는 표 맨 왼쪽
        # **고르는 체크박스 칸**에서 체크한 참여 분만 싣는다(`sourcing.html`).
        # 그 칸은 모든 탭에 선다 — [방 후보 찾기]도 체크한 분만 찾는다.
        "share_bucket": series_a_share.BUCKET,
        "share_topic": series_a_share.KIND,
        "share_tab": series_a_share.is_share_bucket(selected),
        # 투자사 관리 현황과 잇는 갈래 탭인가 — [저절로 잇기] 단추가 선다.
        "sync_tab": bool(selected) and sourcing_sync.branch_of(selected) is not None,
        "total": sum(t["count"] for t in tabs),
        # 이름을 못 바꾼 까닭. 조용히 되돌아오면 왜 그대로인지 알 수 없다.
        "msg": msg,
    })
    # ── 월간 리마인드 이력(#14) — 지난 석 달, 표 전체에 질의 한 번 ──
    remind_months = sourcing_remind_log.months()
    ctx.update({
        "remind_months": remind_months,
        "remind_after": REMIND_AFTER,
        "reminds": sourcing_remind_log.history(db, [r.id for r in rows],
                                               remind_months),
    })
    # 관리자가 붙인 추가 칸 — 갈래(탭)를 가리지 않고 같은 칸(`_custom_cols.html`).
    ctx.update(custom_columns.view(db, "sourcing", "sourcing_contacts"))
    return templates.TemplateResponse("sourcing.html", ctx)


# ── 엑셀 내려받기 ────────────────────────────────────────────────────────────

def _export_table(db: Session, rows: List[SourcingContact], extra: dict,
                  with_bucket: bool) -> tuple:
    """표 한 장 — `(머리글, 줄)`. 칸은 **화면 표 그대로**(`COLUMNS` 차례).

    이름 칸 밑에 붙어 보이던 것(이 달 `딜 받음` · 투자사 관리 현황 연결)은 이름 바로
    뒤에, 월간 리마인드 석 달은 화면처럼 `참여` 뒤에(`REMIND_AFTER`), 관리자가 붙인
    추가 칸은 화면처럼 고른 칸 뒤(안 고르면 끝)에 선다(`custom_columns.arranger`).
    `전체` 탭이면 맨 앞에 `갈래` 를 세운다 — 한 장에 갈래가 섞인다."""
    month = sourcing_receipts.month_of()
    got = sourcing_receipts.receipts(db, month)
    months = sourcing_remind_log.months()
    reminds = sourcing_remind_log.history(db, [r.id for r in rows], months)
    links = sourcing_sync.badges(db, rows)
    rooms = sourcing_link.linked_rooms(db, rows)

    def received(r: SourcingContact) -> str:
        mark = got.get(r.id)
        if mark is None:
            return ""
        if mark.source == sourcing_receipts.SOURCE_MAIL:
            return f"받음 (메일 {sourcing_mail.day_stamp(mark.mail_at)})"
        return "받음 (직접)"

    def linked(r: SourcingContact) -> str:
        if not sourcing_sync.is_synced(r):
            return ""          # 잇지 않는 갈래
        return f"{links[r.id]['sheet']} 명단" if r.id in links else "안 이어짐"

    def cell(r: SourcingContact, field: str) -> list:
        if field == "requested_at":
            out = [sourcing_sync.requested_label(r.requested_at)]
        elif field == "participation":
            out = [sourcing_sync.participation_of(r)]
        elif field == "kakao_room_name" and not r.kakao_room_name and r.id in rooms:
            # 화면의 `🔗 방 (투자사 명단)` — 보낼 때 이 방을 쓴다(`sourcing_link.room_for`).
            out = [f"{rooms[r.id]['room']} (투자사 명단)"]
        else:
            out = [getattr(r, field) or ""]
        if field == "name":
            out += [received(r), linked(r)]
        if field == REMIND_AFTER:
            out += [", ".join(f"{s.when} {s.how}" for s in reminds.get(r.id, {}).get(m.key, []))
                    for m in months]
        return out

    heads: List[str] = ["갈래"] if with_bucket else []
    for field, label, _w, _f in COLUMNS:
        heads.append(label)
        if field == "name":
            heads += [f"{int(month[5:])}월 딜 받음", "투자사 관리 현황"]
        if field == REMIND_AFTER:
            heads += [m.label for m in months]
    put = custom_columns.arranger(heads, extra)
    lines = [put(([r.bucket] if with_bucket else [])
                 + [v for field, *_ in COLUMNS for v in cell(r, field)]
                 + custom_columns.cells(extra, r.id))
             for r in rows]
    return put(heads + custom_columns.names(extra)), lines


@router.get("/api/sourcing/export.xlsx")
def export_sourcing(tab: str = "", ids: Optional[str] = None, every: int = 0,
                    db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    """[엑셀 내려받기] — 지금 탭의 **보이는 줄**, 또는 탭마다 한 장(`every=1`).

    머리글 필터 · 검색은 화면에서만 돈다(`filters.js`) — 서버에 같은 규칙을 또 적으면
    두 벌이 된다. 그래서 화면이 지금 보이는 줄 번호를 **보이는 차례대로** 싣고
    (`ids`), 서버는 그 탭의 줄 중에서만 고른다([방 후보 찾기]와 같은 길). `ids` 가
    없으면 그 탭 전부다. `every=1` 은 거르지 않은 전부를 탭마다 한 장씩.

    권한은 화면과 같다 — 로그인한 누구나(이 표는 팀 공용 · 투자컨설턴트는 미들웨어가
    막는다 — `deps.CONSULTANT_PATHS` 에 없다)."""
    tabs = buckets(db)
    extra = custom_columns.view(db, "sourcing", "sourcing_contacts")
    today = date.today().isoformat()
    if every:
        sheets = [(t["label"], *_export_table(db, rows_of(db, t["key"]), extra, False))
                  for t in tabs] or [("딜 소싱", *_export_table(db, [], extra, False))]
        name = f"딜 소싱_전체 탭_{today}.xlsx"
    else:
        selected = _pick_tab(tabs, tab)
        rows = rows_of(db, selected)
        if ids is not None:
            order = {int(x): i for i, x in enumerate(re.findall(r"\d+", ids))}
            rows = sorted((r for r in rows if r.id in order), key=lambda r: order[r.id])
        sheets = [(selected or "전체", *_export_table(db, rows, extra, not selected))]
        # 갈래 이름의 `/`(구주매각 / 후속…)는 파일 이름에 못 쓴다.
        name = f"딜 소싱_{re.sub(r'[/:*?<>|]+', ' ', selected or '전체')}_{today}.xlsx"
    try:
        content = spreadsheet.write_xlsx_sheets(sheets)
    except spreadsheet.SpreadsheetError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return Response(content=content, media_type=spreadsheet.XLSX_MEDIA_TYPE,
                    headers=spreadsheet.content_disposition(name))


@router.post("/sourcing/buckets/rename", include_in_schema=False)
def rename_bucket(old: str = Form(""), new: str = Form(""),
                  db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    """갈래 탭 이름 바꾸기 — 투자사 관리 현황·투자컨설턴트의 [이름 저장]과 같은 결.

    **줄이 같이 따라간다.** 갈래 이름은 사람·문구·골라 둔 것 세 곳에 같은 글자로
    적혀 있어서, 한 곳만 바꾸면 갈래가 둘로 갈린다(옛 이름의 유령 탭 —
    `0039_consulting_startup_tab` 이 되돌려야 했던 그 사고). 옮기는 것은
    `services/sourcing_buckets.rename` 한 곳이 한다.

    이 화면을 볼 수 있는 사람이면 바꿀 수 있다 — 명단 이름 바꾸기와 같은
    권한이다. 사람 수나 발송 대상이 바뀌는 조작이 아니다.
    `시리즈 A 이상 딜 소싱 참여 심사역` 은 바꿀 수 없다 — 투자사 관리 현황과
    이어진 갈래다(`sourcing_buckets.rename` 이 막는다).
    """
    before, after = (old or "").strip(), sourcing_buckets.normalize_label(new)
    if not before or not after or before == after:
        return RedirectResponse(f"/sourcing?tab={quote(before)}", status_code=303)
    try:
        sourcing_buckets.rename(db, before, after)
    except sourcing_buckets.RenameError as exc:
        db.rollback()
        return RedirectResponse(
            f"/sourcing?tab={quote(before)}&msg={quote(str(exc))}", status_code=303)
    db.commit()
    return RedirectResponse(f"/sourcing?tab={quote(after)}", status_code=303)


@router.post("/sourcing/buckets/add", include_in_schema=False)
def add_bucket(name: str = Form(""), tab: str = Form(""),
               db: Session = Depends(get_db),
               user: User = Depends(get_current_user)):
    """[+ 탭 추가] — 사람이 아직 없는 새 갈래(탭)를 만든다(`sourcing_buckets.create`).

    권한은 [이름 저장]과 같다 — 이 화면을 볼 수 있는 누구나(위 `rename_bucket`).
    새 탭은 투자사 관리 현황과 잇지 않는다 — 잇는 갈래는 셋뿐이다(`sourcing_sync.BRANCHES`).
    """
    try:
        label = sourcing_buckets.create(db, name)
        db.commit()
    except (sourcing_buckets.RenameError, IntegrityError) as exc:
        db.rollback()
        # IntegrityError — 같은 이름을 두 사람이 거의 동시에 만들었다(유일 조건).
        why = str(exc) if isinstance(exc, sourcing_buckets.RenameError) else (
            f"이미 있는 탭입니다: {(name or '').strip()}")
        return _back(tab, why)
    return RedirectResponse(f"/sourcing?tab={quote(label)}", status_code=303)


class SourcingIn(BaseModel):
    name: Optional[str] = None
    title: Optional[str] = None
    firm: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    assignee_name: Optional[str] = None
    requested_at: Optional[str] = None
    share_method: Optional[str] = None
    sectors: Optional[str] = None
    round_size: Optional[str] = None
    tips: Optional[str] = None
    memo: Optional[str] = None
    kakao_reply: Optional[str] = None
    call_note: Optional[str] = None
    kakao_room_name: Optional[str] = None
    # `참여` | `불참여` — 모르는 말은 막는다(`sourcing_sync.normalize_participation`).
    participation: Optional[str] = None


@router.post("/api/sourcing")
def add_row(body: SourcingIn, bucket: str = "",
            db: Session = Depends(get_db),
            user: User = Depends(get_current_user)):
    """갈래에 사람을 새로 넣는다.

    지금까지는 시트를 다시 올려야만 늘릴 수 있었다 — 전화로 한 명 승낙받고
    바로 적을 곳이 없어서, 메모지에 적어 뒀다가 나중에 시트에 옮겼다.

    **갈래는 반드시 있어야 한다.** 갈래가 곧 문구라, 갈래 없는 줄은 어떤
    문구로 보낼지 정할 수 없다.
    """
    name = (body.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="이름을 입력하세요")
    target = (bucket or "").strip()
    if not target:
        raise HTTPException(status_code=400, detail="갈래를 고르세요")
    # 그 갈래가 **쓰고 있는 글자**로 적는다 — 띄어쓰기만 다른 글자로 넣으면 저장된
    # 글자는 그대로인데 줄마다 글자가 갈린다(`sourcing_buckets.label_of`).
    target = sourcing_buckets.label_of(db, target)

    # 새 줄은 그 갈래의 맨 아래로. 시트의 번호를 사람이 매번 세지 않아도 되게.
    last = db.execute(
        select(func.max(SourcingContact.position))
        .where(SourcingContact.bucket.in_(sourcing_buckets.variants(db, target)))
    ).scalar() or 0
    row = SourcingContact(bucket=target, position=last + 1, name=name)
    for field, value in body.model_dump(exclude_unset=True).items():
        if field == "participation":
            continue
        if field != "name" and value:
            setattr(row, field, value.strip() or None)
    row.participation = _participation(body.participation or sourcing_sync.JOINED)
    db.add(row)
    # 잇는 갈래(Series A · M&A · 구주·후속)에 넣은 분은 **투자사 관리 현황에도** 선다 —
    # 이름 · 번호가 둘 다 같은 줄이 딱 하나면 그 줄과 잇고, 같은 분일 수 있는 줄이
    # 있으면 후보로 남기고(`link_candidates`), 아무도 없으면 넣은 사람의 `직접 추가`
    # 명단에 새로 만들어 잇는다(`sourcing_sync.add_from_sourcing`). 그쪽 `딜 소싱` 칸에
    # 곧바로 이 갈래가 선다. `(딜 소개 X)` · `딜 소개 보류` 인 분은 막는다.
    try:
        contact, note = sourcing_sync.add_from_sourcing(db, row, user)
    except sourcing_sync.SyncError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    out = {"id": row.id, "bucket": target}
    if contact is not None:
        out["linked_msg"] = note or _linked_msg(db, row)
    elif note:
        out["vc_msg"] = note
    return out


def _participation(value: str) -> str:
    try:
        return sourcing_sync.normalize_participation(value)
    except sourcing_sync.SyncError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _linked_msg(db: Session, row: SourcingContact) -> str:
    badge = sourcing_sync.badges(db, [row]).get(row.id)
    if not badge:
        return ""
    return (f"투자사 관리 현황의 '{badge['sheet']}' 명단 줄과 이었습니다 — "
            f"그쪽 `{sourcing_sync.COLUMN_LABEL}` 칸에 이 갈래가 같이 보입니다.")


@router.patch("/api/sourcing/{row_id}")
def update_row(row_id: int, body: SourcingIn, db: Session = Depends(get_db),
               user: User = Depends(get_current_user)):
    """표에서 눌러 바로 고친다 — 다른 표와 같은 조작이다."""
    row = db.get(SourcingContact, row_id)
    if row is None:
        raise HTTPException(status_code=404, detail="찾을 수 없습니다")
    data = {k: v for k, v in body.model_dump(exclude_unset=True).items()
            if v is not None}
    if "participation" in data:
        data["participation"] = _participation(data["participation"])
    # **권한은 지금까지 그대로 — 로그인한 누구나**(이 표는 팀 공용이다). 투자사
    # 관리 현황과 이어진 줄이어도 같다: 딜 소싱에 든 분은 보내는 사람 카톡의
    # 딜 소싱 방에 있는 분이라, 투자사 줄을 누가 맡았는지와 따로 관리한다
    # (사용자 원문 — "투자사 관리 현황이랑은 다르게 생각해야함").
    key_before = sourcing_sync.link_key(row)
    for field, value in data.items():
        # 이름은 비울 수 없다 — 누구인지 모르는 줄이 남는다.
        if field == "name" and not value.strip():
            continue
        if field == "kakao_room_name" and value.strip() != (row.kakao_room_name or ""):
            # 이름이 바뀌었으면 예전 확인 결과는 다른 방 이야기다.
            row.room_verified = "unverified"
        setattr(row, field, value.strip() or None)
    # 이름 · 번호를 고쳐 투자사 관리 현황의 줄과 맞게 됐으면 잇는다(`add_row` 와
    # 같다 — 둘 다 같아야 하므로 이름을 고쳐도 다시 본다). 이미 이어진 줄은
    # 번호가 바뀌어도 잇기를 그대로 둔다 — 고친 번호는 이어진 투자사 줄에도
    # 그대로 넘어간다(`sourcing_sync.before_flush`).
    contact = None
    relink = sourcing_sync.link_key(row) != key_before
    if relink:
        contact = sourcing_sync.auto_link(db, row)
    db.commit()
    # 고친 줄의 **지금 담당** — 화면이 [담당자] 필터 값을 이것으로 고쳐 적는다
    # (`sourcing.html`). 화면이 글자를 다시 자르면 규칙이 두 벌이 된다.
    # `participation` 도 서버가 읽은 값으로 다시 적는다(`O` → `참여`) — 칸 색을
    # 고르는 갈래(`participation_kind` — 참여 · 불참여 · 확인 전)도 함께. 화면이
    # 값을 보고 갈래를 다시 정하면 규칙이 두 벌이 된다(`sourcing.html`).
    out = {"ok": True, "assignee": assignee_of(row),
           "participation": sourcing_sync.participation_of(row),
           "participation_kind": sourcing_sync.kind_of(row),
           # `참여 요청일` 을 고치면 세울 값도 바뀐다(`sourcing.html` 이 줄에 다시 적는다).
           "requested_sort": requested_sort(row)}
    if contact is not None:
        out["linked_msg"] = _linked_msg(db, row)
    if relink and sourcing_sync.is_synced(row):
        # 이름 · 번호가 바뀌면 후보도 바뀐다 — 이어졌으면 연결 표시, 아니면 새
        # 후보로 그 자리를 다시 그린다(`sourcing_vc_link.js`).
        out.update(_vc_view(db, row, user))
    return out


# ── 투자사 관리 현황과 사람이 확정해 잇기 (#28) ─────────────────────────────

def _may_unlink(user: User, owner_id: Optional[int]) -> bool:
    """[연결 풀기]를 누를 수 있나 — 관리자 · 이어진 투자사 줄의 담당 팀원(그 줄의
    `user_id`, 사용자 결정 2026-10-17). 잇기([이 분으로 확정])는 표를 고치는 누구나
    하지만, 푸는 것은 남이 확정해 둔 것을 거두는 일이라 좁힌다.

    딜 소싱 `담당자` 칸(`assignee_name`)으로는 **판정하지 않는다** — 그 칸은 로그인한
    누구나 고치는 글 칸이라(`update_row`), 제 이름을 적고 누르면 뚫린다(PR #311 리뷰).
    소싱 줄에는 주인 번호가 없다(`delete_row` 머리말)."""
    return user.role == "admin" or (owner_id is not None and owner_id == user.id)


def _badges(db: Session, rows: List[SourcingContact], user: User) -> dict:
    """연결 표시(`sourcing_sync.badges`)에 [연결 풀기]를 누를 수 있는지를 얹는다."""
    out = sourcing_sync.badges(db, rows)
    for row in rows:
        if row.id in out:
            out[row.id]["can_unlink"] = _may_unlink(user, out[row.id]["owner_id"])
    return out


def _vc_view(db: Session, row: SourcingContact, user: User) -> dict:
    """줄 이름 아래 투자사 관리 현황 자리 — 화면(`sourcing_vc_link.js`)이 그린다.

    이어졌으면 연결 표시(`vc_link` — 서버가 그리는 것과 같은 `badges` 값)와 이 줄의
    같은 칸 값(`fields` — 이으면서 빈 칸이 채워졌을 수 있다), 아니면 후보(`vc_picks`).
    """
    badge = _badges(db, [row], user).get(row.id)
    if badge is None:
        return {"vc_picks": sourcing_sync.link_candidates(db, [row]).get(row.id, [])}
    return {"vc_link": badge,
            "fields": {f: getattr(row, f, None) or "" for f in sourcing_sync.SHARED_FIELDS}}


class LinkIn(BaseModel):
    """고른 투자사 관리 현황 줄 번호."""

    contact_id: Optional[int] = None


@router.post("/api/sourcing/{row_id}/link")
def confirm_vc_link(row_id: int, body: LinkIn, db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    """[이 분으로 확정] — 저절로 못 이은 잇는 갈래의 줄을 사람이 고른 투자사 줄과 잇는다.

    이름 · 번호가 둘 다 같은 줄이 딱 하나일 때만 저절로 잇는다(`sourcing_sync.
    auto_link`). 나머지는 후보를 보고 사람이 고른다 — 고른 줄이 **지금 다시 센
    후보** 안에 있어야 잇는다(`sourcing_sync.confirm_link`). 잇고 나면 그쪽
    `딜 소싱` 칸에 이 갈래가 이 줄의 참여로 선다. 잇는 것은 소싱 줄의
    `vc_contact_id` 라 수정 로그에 남는다(`edit_log.VALUE_FIELDS`).

    권한은 이 표를 고치는 것과 같다 — 로그인한 누구나(`update_row` 주석: 딜 소싱은
    팀 공용이고, 투자사 줄을 누가 맡았는지와 따로 관리한다).
    """
    row = db.get(SourcingContact, row_id)
    if row is None:
        raise HTTPException(status_code=404, detail="찾을 수 없습니다")
    try:
        sourcing_sync.confirm_link(db, row, body.contact_id)
    except sourcing_sync.SyncError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        db.commit()
    except IntegrityError as exc:
        # 두 사람이 같은 투자사 줄을 거의 동시에 확정했다 — 후보를 셀 때는 둘 다
        # 비어 있었고, 늦게 커밋한 쪽이 유일 색인(한 투자사 줄에 소싱 줄 하나)에
        # 걸린다. 다른 막힘과 같은 말로 답한다(500 이 아니라).
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail="그 사이 다른 분이 이 투자사 줄을 다른 딜 소싱 줄과 이었습니다 — "
                   "새로고침해 보세요.") from exc
    return {"id": row.id, **_vc_view(db, row, user)}


@router.post("/api/sourcing/{row_id}/unlink")
def unlink_vc(row_id: int, db: Session = Depends(get_db),
              user: User = Depends(get_current_user)):
    """[연결 풀기] — 잘못 이은 투자사 관리 현황 줄과의 잇기를 푼다(사용자 결정
    2026-10-17). **두 줄 다 지우지 않는다**(`sourcing_sync.unlink`) — 그쪽
    `딜 소싱` 칸에서 이 갈래가 빠지고, 이 줄은 다시 후보로 뜬다. 관리자 · 이어진 투자사
    줄의 담당만(`_may_unlink`). 푸는 것도 `vc_contact_id` 라 수정 로그에 남는다."""
    row = db.get(SourcingContact, row_id)
    if row is None:
        raise HTTPException(status_code=404, detail="찾을 수 없습니다")
    badge = _badges(db, [row], user).get(row.id)
    if badge is None:
        raise HTTPException(status_code=400,
                            detail="투자사 관리 현황과 이어진 줄이 아닙니다 — 새로고침해 보세요.")
    if not badge["can_unlink"]:
        raise HTTPException(status_code=403,
                            detail="연결은 관리자나 이어진 투자사 관리 현황 줄의 담당만 "
                                   "풀 수 있습니다.")
    sourcing_sync.unlink(row)
    db.commit()
    return {"id": row.id, **_vc_view(db, row, user)}


@router.delete("/api/sourcing/{row_id}")
def delete_row(row_id: int, db: Session = Depends(get_db),
               user: User = Depends(get_current_user)):
    """명단에서 한 줄을 뺀다.

    넣는 길만 있고 빼는 길이 없었다 — 전화로 급히 적다가 이름을 잘못 넣거나
    같은 사람을 두 번 넣어도 시트를 통째로 다시 올리는 것 말고는 방법이
    없었다(`scripts/import_sourcing.py` 는 갈래를 통째로 갈아엎는다).

    **지우는 것은 그 갈래의 그 줄 하나다.** 같은 사람이 여러 갈래에 들어가
    있으면 각각이 다른 줄이라(`SourcingContact` 주석 참고) 나머지는 남는다.
    이름으로 싸잡아 지우면 "시리즈 A 에서만 빼려고 눌렀는데 M&A 에서도
    사라지는" 일이 된다.

    **주인 검사는 하지 않는다 — 이 표에는 주인이 없다.**
    `sourcing_contacts` 에는 `user_id` 칸이 아예 없다. 소싱 명단은 IR 기업현황
    과 같은 **팀 공용**이라(발송도 담당자로 거르지 않는다 —
    `routers/deals.py` 의 `_load_recipients`), 여기서 볼 수 있는 경계는
    **로그인했는가** 하나뿐이고 그것은 위의 추가·수정과 똑같다.
    투자컨설턴트는 이 주소에 닿기 전에 끊긴다 — 역할 판정은 `app/main.py`
    미들웨어 한 곳에서만 한다(`deps.CONSULTANT_PATHS` 에 소싱이 없다).

    투자사 관리 현황과 이어진 줄(잇는 세 갈래)도 같다 — 빼면 그쪽
    `딜 소싱` 칸에서 그 갈래가 빠질 뿐이고, 투자사 줄은 그대로다.
    """
    row = db.get(SourcingContact, row_id)
    if row is None:
        raise HTTPException(status_code=404, detail="찾을 수 없습니다")

    # 딸린 것: 이 사람에게 보낸 발송 이력(`send_items.sourcing_contact_id`).
    #
    # **보낸 이력이 있으면 지우지 않는다.** 발송 건은 이 줄을 번호로 가리키고,
    # 화면과 기록에 뜨는 받는 사람 이름은 그 번호를 따라가 읽는다
    # (`models.py` 의 `SendItem.recipient_name`). 그래서 그냥 지우면:
    #   · 운영 DB — 이 칸에는 외래키가 서 있지 않다(alembic 0029 가 그냥
    #     Integer 로 붙였다). 막히지 않고 **조용히 넘어가고**, 발송 건은 없는
    #     번호를 가리킨 채 남아 "누구에게 보냈나" 가 빈칸이 된다.
    #   · 테스트 DB — 모델대로 외래키가 서 있어 같은 코드가 IntegrityError 로
    #     터진다. 한쪽은 넘어가고 한쪽은 500 인, 두 곳의 결과가 갈리는 상태다.
    # 이력까지 같이 지우는 길도 있지만, 발송 이력은 "누구에게 언제 보냈나" 의
    # 근거라 명단 한 줄보다 무겁다. 그래서 **막는다** — 계정 삭제가
    # `AgentDevice` 때문에 막혔던 것과 같은 자리이고, IR 기업현황도 같은
    # 이유로 같은 답을 냈다(`routers/companies.py` 의 `delete_company`).
    # 잘못 넣은 줄은 아직 아무에게도 안 보낸 줄이라 이 문에 걸리지 않는다.
    #
    # **방 찾기 건은 세지 않는다**(`verify_room` — [방 후보 찾기]). 아무것도
    # 보내지 않은 건이라 '보낸 이력' 이 아니다 — 세면 잘못 넣은 줄에서 방 찾기를
    # 한 번 누른 것만으로 지울 길이 없어진다(PR #284 리뷰). 투자사 줄의 발송
    # 이력도 같은 이유로 그 잡을 뺀다(`routers/contacts.get_contact`). 그 건은
    # 지울 때 함께 치운다(`sourcing_rooms.forget`).
    sent = db.execute(
        select(func.count()).select_from(SendItem)
        .join(SendJob, SendJob.id == SendItem.job_id)
        .where(SendItem.sourcing_contact_id == row_id,
               SendJob.kind != VERIFY_KIND)
    ).scalar_one()
    if sent:
        raise HTTPException(
            status_code=400,
            detail=f"이미 {sent}건을 보낸 사람이라 삭제할 수 없습니다 — "
                   "발송 이력이 이 줄을 가리킵니다. 더 보내지 않으려면 "
                   "카톡방 이름을 비워주세요(방이 없으면 발송이 거부됩니다).",
        )

    # 그 줄의 달마다 `딜 받음` 표시 · 본 메일도 함께 — 가리킬 곳이 없는 줄을 남기지 않는다.
    sourcing_receipts.delete_for(db, [row_id])
    sourcing_rooms.forget(db, row_id)
    db.delete(row)
    db.commit()
    return {"deleted": row_id}


# ── 이 달 딜 받음 · 메일 확인 ────────────────────────────────────────────────

def _back(tab: str, msg: str = "") -> RedirectResponse:
    url = f"/sourcing?tab={quote(tab or 'all')}"
    if msg:
        url += f"&msg={quote(msg)}"
    return RedirectResponse(url, status_code=303)


@router.post("/sourcing/{row_id}/received", include_in_schema=False)
def toggle_received(row_id: int, month: str = Form(""), on: str = Form(""),
                    tab: str = Form(""), db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    """**이 달 딜 받음** 표시를 켜고 끈다.

    이 화면을 볼 수 있는 사람이면 누른다(명단을 고치는 권한과 같다). 달은
    화면이 보낸 달을 쓴다 — 자정을 넘겨 눌러도 사람이 본 달에 적힌다. 메일로
    선 표시도 여기서 거둘 수 있다(같은 메일로는 다시 서지 않는다).
    """
    row = db.get(SourcingContact, row_id)
    if row is None:
        raise HTTPException(status_code=404, detail="찾을 수 없습니다")
    if not re.fullmatch(r"\d{4}-\d{2}", month or ""):
        month = sourcing_receipts.month_of()
    if on == "1":
        sourcing_receipts.mark(db, row.id, month, user_id=user.id)
    else:
        sourcing_receipts.unmark(db, row.id, month)
    db.commit()
    return _back(tab)


@router.post("/sourcing/vc-auto-link", include_in_schema=False)
def vc_auto_link(tab: str = Form(""), db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    """[저절로 잇기] — 이 갈래의 안 이어진 줄을 투자사 관리 현황과 잇는다.

    규칙은 줄 하나를 넣을 때와 같다(`sourcing_sync.auto_link` — 이름 · 번호가 둘 다
    같은 투자사 줄이 딱 하나일 때만). M&A · 구주·후속 갈래는 잇기가 생기기 전부터
    있던 줄이라 한 번 돌려 줘야 한다(사용자 결정 2026-10-21 — 이주로 몰래 잇지 않는다).
    못 이은 줄은 그 줄 이름 아래 후보로 남아 [이 분으로 확정]을 기다린다. `참여` 칸은
    건드리지 않는다. 권한은 [이 분으로 확정]과 같다 — 로그인한 누구나.
    """
    bucket = sourcing_sync.branch_of(tab)
    if bucket is None:
        return _back(tab, "투자사 관리 현황과 잇는 갈래(Series A · M&A · 구주·후속)에서만 "
                          "누를 수 있습니다")
    done = sourcing_sync.auto_link_all(db, bucket)
    db.commit()
    rows = [r for r in rows_of(db, tab) if not r.vc_contact_id]
    waiting = sum(1 for picks in sourcing_sync.link_candidates(db, rows).values() if picks)
    return _back(tab, f"{done}명을 투자사 관리 현황과 이었습니다 · 사람이 확정할 후보가 있는 분 "
                      f"{waiting}명 · 맞는 분이 없는 분 {len(rows) - waiting}명")


@router.post("/sourcing/mail-check", include_in_schema=False)
def mail_check_now(tab: str = Form(""), db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)):
    """[지금 메일 확인] — 받은 편지함의 머리글을 읽어 메일로 딜을 보낸 사람을 `딜 받음`.

    관리자만 — 회사 메일함에 서버가 접속하는 자리다. 요청을 붙잡지 않게 따로 띄운
    실에서 돌고, 결과는 이 화면의 머리 줄에 선다(`services/sourcing_mail.py`).
    """
    from ..deps import admin_only

    admin_only(user)
    settings = sourcing_mail.load_settings(db)
    if not settings.active:
        return _back(tab, settings.off_text)
    if sourcing_mail.start_manual(db, user) is None:
        return _back(tab, "메일 확인이 이미 돌고 있습니다 — 잠시 뒤 새로고침하세요")
    return _back(tab, "메일 확인을 시작했습니다 — 잠시 뒤 이 화면 위쪽에 결과가 섭니다")


# ── 카톡방 후보 찾기 · 확정 ────────────────────────────────────────────────

def _ids(raw: str) -> Optional[List[int]]:
    """`3,5,8` → `[3, 5, 8]`. 비면 `None`(= 아무도 안 골랐다)."""
    out = [int(x) for x in re.findall(r"\d+", raw or "")]
    return out or None


@router.post("/sourcing/rooms/search", include_in_schema=False,
             dependencies=[Depends(no_send_as_member)])
def search_rooms(tab: str = Form(""), ids: str = Form(""),
                 db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    """[방 후보 찾기] — **고른 줄**(`ids`) 중 방이 없는 줄을 **누른 사람 PC 의
    카톡**에서 찾는다.

    잡은 누른 사람 계정에 선다(`sourcing_rooms.queue_search`) — 그 사람 PC 의
    발송기가 그 사람 카톡에서 찾고, 찾은 제목은 후보로만 담긴다. 보내는 사람이
    눌러야 그 사람 카톡의 방 제목이 나온다. **아무것도 보내지 않는다**(방 확인 잡).

    **아무도 안 골랐으면 아무것도 안 세운다** — 예전처럼 그 갈래의 방 없는 줄
    전부로 대신하지 않는다(사용자: "방 후보 찾기도 선택한걸 기반으로 찾게
    해줘"). 화면도 단추를 잠그지만 여기서 한 번 더 막는다. 고른 줄도 그 탭
    (전체 탭이면 전체)의 방 없는 줄만 찾는다(`sourcing_rooms.targets`) — 방이
    이미 있거나 불참여인 줄 · 다른 갈래 줄은 빠진다.

    이 화면을 볼 수 있는 누구나 누른다 — 자기 PC 에 거는 일이다.
    """
    picked = _ids(ids)
    if not picked:
        return _back(tab, "찾을 분을 먼저 고르세요 — 표 왼쪽 체크박스로 고릅니다")
    bucket = "" if tab in ("", "all") else tab
    rows = sourcing_rooms.targets(db, bucket, picked)
    job = sourcing_rooms.queue_search(db, user, rows)
    if job is None:
        return _back(tab, "찾을 줄이 없습니다 — 고른 분은 방 이름이 다 있습니다")
    db.commit()
    return _back(tab, f"{user.name} 님 PC 의 카톡에서 {job.total}명의 방을 찾습니다"
                      f"(회차 #{job.id}) — 그 PC 의 발송 프로그램이 켜져 있어야 합니다. "
                      "끝나면 이 화면을 새로고침해 후보를 고르세요")


@router.post("/sourcing/{row_id}/room-confirm", include_in_schema=False)
def confirm_room(row_id: int, room: str = Form(""), tab: str = Form(""),
                 db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    """[이 방으로 확정] — 카톡에서 찾은 후보를 이 줄의 방 이름으로(`확인됨`)."""
    row = db.get(SourcingContact, row_id)
    if row is None:
        raise HTTPException(status_code=404, detail="찾을 수 없습니다")
    try:
        sourcing_rooms.confirm(row, room)
    except sourcing_rooms.NotPickable as exc:
        db.rollback()
        return _back(tab, str(exc))
    db.commit()
    return _back(tab, f"{row.name} — 방을 확정했습니다: {row.kakao_room_name}")
