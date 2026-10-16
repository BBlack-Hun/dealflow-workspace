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
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_current_user, templates
from ..models import SendItem, SendJob, SourcingContact, User
from ..services import (series_a_share, sourcing_buckets, sourcing_link,
                        sourcing_mail, sourcing_receipts, sourcing_rooms,
                        sourcing_sync)
from ..services import sourcing_remind_log
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
#   담당자 5종 · 투자분야 6종 · 참여 요청일 12종 · 라운드 사이즈 13종 ·
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
    ("name", "이름", "96px", False),
    # ── 앱이 만든 칸. 원본 시트에는 없다 ──
    # `참여` · `불참여` 두 값이라 거른다. 불참여인 분은 딜 소싱 제안(처음 안내 ·
    # 월간 리마인드)에서 빠진다. 시리즈 A 갈래의 줄은 투자사 관리 현황의
    # `Series A 딜 소싱` 칸(O/X)이 **이 값 그대로**다(`services/sourcing_sync.py`).
    ("participation", "참여", "84px", True),
    ("assignee_name", "담당자", "100px", True),
    ("phone", "휴대폰", "116px", False),
    ("title", "직함", "88px", True),
    ("email", "이메일 주소", "170px", False),
    ("firm", "회사", "150px", False),
    ("sectors", "투자분야", "120px", True),
    ("round_size", "라운드 사이즈", "134px", True),
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
    """
    rows = db.execute(
        select(SourcingContact.bucket, func.count(), func.min(SourcingContact.position))
        .group_by(SourcingContact.bucket)
    ).all()
    out = [{"key": b, "label": b, "count": n, "pos": pos or 0} for b, n, pos in rows]
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
        stmt = stmt.where(SourcingContact.bucket == bucket)
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
    # `out` — 그 사이 `불참여` 가 된 분. 딜 제안 관리가 그 카드를 고를 수 없게
    # 한다(`deals.js`). 칩은 **보낼 수 있는 분만** 센다 — 화면을 그릴 때
    # (`sendable_rows`)와 같은 모집단이어야 칩 수가 다시 읽을 때 흔들리지 않는다.
    return {"month": month, "month_label": f"{int(month[5:])}월",
            "rows": [{"id": r.id, "assignee": assignee_of(r),
                      "received": r.id in got,
                      "out": not sourcing_sync.takes_part(r)} for r in rows],
            "assignees": assignee_chips(
                [r for r in rows if sourcing_sync.takes_part(r)])}


def sendable_rows(db: Session) -> List[SourcingContact]:
    """딜 소싱 제안을 **받는** 분 — `불참여` 를 뺀 명단, 차례는 `rows_of` 그대로.

    딜 제안 관리의 [딜 소싱 제안] 목록 · 칩이 이것을 지나고, 발송 길
    (`routers/deals.create_send_list`)도 같은 판정(`sourcing_sync.takes_part`)으로
    한 번 더 보고 막는다 — 화면을 연 뒤에 불참여가 된 분께 나가지 않게.
    """
    return [r for r in rows_of(db) if sourcing_sync.takes_part(r)]


@router.get("/sourcing", response_class=HTMLResponse, include_in_schema=False)
def sourcing_page(request: Request, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user), tab: str = "",
                  msg: str = ""):
    tabs = buckets(db)
    # 아무 것도 고르지 않았으면 첫 갈래를 연다. 전체를 먼저 보여주면 갈래가
    # 나뉜 뜻이 사라진다.
    selected = tab if any(t["key"] == tab for t in tabs) else (
        tabs[0]["key"] if tabs and tab != "all" else "")
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
        # 시리즈 A 갈래만 이어진다(`sourcing_sync.SYNC_BUCKET`).
        "vc_links": sourcing_sync.badges(db, rows),
        # 연결 표시의 풍선말 — **어느 칸이 같이 바뀌는지**. 화면에 칸 이름을
        # 적어 두면 칸이 늘 때(#17 투자분야 · 라운드 사이즈) 말만 옛것으로 남는다.
        "vc_shared": " · ".join(sourcing_sync.SHARED_LABELS[f]
                                for f in sourcing_sync.SHARED_FIELDS),
        # **보낼 방이 없는 줄** — 자기 방 이름도 이어받을 방도 없다
        # (`sourcing_rooms.needs_room` — 발송이 방을 고르는 규칙과 같다).
        # 그 줄에 `방 없음` 과 [방 후보 찾기] 가 선다.
        "no_room": {r.id for r in sourcing_rooms.needs_room(db, rows)},
        # [방 후보 찾기] 단추에 적을 수 — 누르면 세우는 잡의 크기와 같은 함수다.
        "room_search_count": len(sourcing_rooms.targets(db, selected)),
        # [방 후보 찾기] 가 담아 온 후보 · 상태(`services/sourcing_rooms.py`).
        "room_picks": {r.id: sourcing_rooms.picks(r) for r in rows},
        "tabs": tabs,
        "selected": selected,
        "columns": COLUMNS,
        "rows": rows,
        # [담당자] 필터가 거르는 값 — 칸에 적힌 글자가 아니라 **지금 맡은 사람**
        # (`assignee_of`). 딜 제안 관리의 [담당] 칩과 같은 값이다.
        "assignees": {r.id: assignee_of(r) for r in rows},
        # ── Series A 딜 공유 (`services/series_a_share.py`) ──
        # 줄마다 받은 기업 이름 — `Series A 딜 공유 N건` 과 그 풍선말.
        "shared": series_a_share.shared_companies(db, [r.id for r in rows]),
        # [Series A 딜 소개] 단추는 이 갈래 탭에만 선다 — 이 글을 받는 갈래가
        # 하나뿐이다(투자사 관리 현황과 이어진 갈래).
        "share_bucket": series_a_share.BUCKET,
        "share_topic": series_a_share.KIND,
        # 그 탭에서만 표 맨 왼쪽에 **고르는 체크박스 칸**이 선다 — 단추가 체크한
        # 참여 분만 싣는다(`sourcing.html`). 다른 탭에는 고른 것을 쓸 곳이 없다.
        "picking": selected == series_a_share.BUCKET,
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
    return templates.TemplateResponse("sourcing.html", ctx)


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

    # 새 줄은 그 갈래의 맨 아래로. 시트의 번호를 사람이 매번 세지 않아도 되게.
    last = db.execute(
        select(func.max(SourcingContact.position))
        .where(SourcingContact.bucket == target)
    ).scalar() or 0
    row = SourcingContact(bucket=target, position=last + 1, name=name)
    for field, value in body.model_dump(exclude_unset=True).items():
        if field == "participation":
            continue
        if field != "name" and value:
            setattr(row, field, value.strip() or None)
    row.participation = _participation(body.participation or sourcing_sync.JOINED)
    db.add(row)
    # 시리즈 A 갈래에 넣은 분이 투자사 관리 현황에 **번호가 딱 한 줄** 맞으면
    # 그 줄과 잇는다 — 그쪽 `Series A 딜 소싱` 칸이 곧바로 O 가 된다.
    contact = sourcing_sync.auto_link(db, row)
    db.commit()
    out = {"id": row.id, "bucket": target}
    if contact is not None:
        out["linked_msg"] = _linked_msg(db, row)
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
            f"그쪽 `{sourcing_sync.COLUMN_LABEL}` 칸이 O/X 로 같이 보입니다.")


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
    phone_before = sourcing_sync.digits(row.phone)
    for field, value in data.items():
        # 이름은 비울 수 없다 — 누구인지 모르는 줄이 남는다.
        if field == "name" and not value.strip():
            continue
        if field == "kakao_room_name" and value.strip() != (row.kakao_room_name or ""):
            # 이름이 바뀌었으면 예전 확인 결과는 다른 방 이야기다.
            row.room_verified = "unverified"
        setattr(row, field, value.strip() or None)
    # 번호를 고쳐 투자사 관리 현황의 줄과 맞게 됐으면 잇는다(`add_row` 와 같다).
    # 이미 이어진 줄은 번호가 바뀌어도 잇기를 그대로 둔다 — 고친 번호는 이어진
    # 투자사 줄에도 그대로 넘어간다(`sourcing_sync.before_flush`).
    contact = None
    if sourcing_sync.digits(row.phone) != phone_before:
        contact = sourcing_sync.auto_link(db, row)
    db.commit()
    # 고친 줄의 **지금 담당** — 화면이 [담당자] 필터 값을 이것으로 고쳐 적는다
    # (`sourcing.html`). 화면이 글자를 다시 자르면 규칙이 두 벌이 된다.
    # `participation` 도 서버가 읽은 값으로 다시 적는다(`O` → `참여`).
    out = {"ok": True, "assignee": assignee_of(row),
           "participation": sourcing_sync.participation_of(row)}
    if contact is not None:
        out["linked_msg"] = _linked_msg(db, row)
    return out


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

    투자사 관리 현황과 이어진 줄(시리즈 A 갈래)도 같다 — 빼면 그쪽
    `Series A 딜 소싱` 칸이 빈칸이 될 뿐이고, 투자사 줄은 그대로다.
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
    """`3,5,8` → `[3, 5, 8]`. 비면 `None`(= 그 갈래의 방 없는 줄 전부)."""
    out = [int(x) for x in re.findall(r"\d+", raw or "")]
    return out or None


@router.post("/sourcing/rooms/search", include_in_schema=False)
def search_rooms(tab: str = Form(""), ids: str = Form(""),
                 db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    """[방 후보 찾기] — 방이 없는 줄을 **누른 사람 PC 의 카톡**에서 찾는다.

    잡은 누른 사람 계정에 선다(`sourcing_rooms.queue_search`) — 그 사람 PC 의
    발송기가 그 사람 카톡에서 찾고, 찾은 제목은 후보로만 담긴다. 보내는 사람이
    눌러야 그 사람 카톡의 방 제목이 나온다. **아무것도 보내지 않는다**(방 확인 잡).

    이 화면을 볼 수 있는 누구나 누른다 — 자기 PC 에 거는 일이다.
    """
    bucket = "" if tab in ("", "all") else tab
    rows = sourcing_rooms.targets(db, bucket, _ids(ids))
    job = sourcing_rooms.queue_search(db, user, rows)
    if job is None:
        return _back(tab, "찾을 줄이 없습니다 — 방 이름이 다 있습니다")
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
