"""리마인드 — 딜소개 뒤에 무엇을 언제 보낼지 한 화면에서 본다.

사람이 달력을 보며 챙기던 일이라 빠지기 쉬웠다. 여기서 **오늘 보낼 것**을
먼저 보여주고, 눌러서 그대로 발송 화면으로 넘긴다.

'답 옴'을 눌러 멈출 수 있어야 한다 — IR 요청이나 미팅이 잡혔는데도 리마인드가
계속 나가는 것이 이 기능에서 가장 나쁜 실패다. IR 요청·미팅 기록이 생기면
자동으로도 멈추지만, 카톡으로만 답이 온 경우는 사람이 눌러 줘야 한다.
"""
from __future__ import annotations

from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_current_user, templates
from ..models import ScheduleRule, SendSequence, User
from ..services import cadence, flow
from ..ui import base_ctx

router = APIRouter(tags=["followups"])


def _owned(db: Session, sequence_id: int, user: User) -> SendSequence:
    seq = db.get(SendSequence, sequence_id)
    if seq is None or seq.user_id != user.id:
        raise HTTPException(status_code=404, detail="리마인드 건을 찾을 수 없습니다")
    return seq


def remind_context(db: Session, user: User, today: date) -> dict:
    """리마인드 구역이 쓰는 값. 딜 진행 관리 한 페이지가 통째로 가져다 쓴다.

    원래 `/followups` 라는 딴 페이지였는데, 한 담당자를 두고 "자료 보냈나 →
    답 없으면 리마인드 → 미팅 잡기" 를 오가는 흐름이라 페이지가 갈리면
    그 흐름이 끊긴다.
    """
    # 답이 왔는데도 리마인드가 나가는 것이 이 기능의 가장 나쁜 실패다.
    # 화면을 열 때마다 반응 기록을 훑어 멈춘다.
    cadence.sweep_reactions(db, user.id)
    rows = cadence.sequence_rows(db, user.id, today)

    due = [r for r in rows if r["status"] == "active" and r["due"]
           and r["due"] <= today.isoformat()]
    upcoming = [r for r in rows if r["status"] == "active" and r["due"]
                and r["due"] > today.isoformat()]
    closed = [r for r in rows if r["status"] != "active"]

    # 오늘 보낼 것을 단계별로 묶어 둔다 — 한 번에 같은 문구로 나가야 한다.
    by_stage = {}
    for row in due:
        by_stage.setdefault(row["next_stage"], []).append(row)

    return {
        "due": due,
        "due_groups": [
            {"stage": stage, "label": cadence.STAGE_LABELS.get(stage, ""),
             "mode": cadence.STAGE_MODES.get(stage, ""), "rows": items}
            for stage, items in sorted(by_stage.items())
        ],
        "upcoming": upcoming,
        "closed": closed,
        "remind_counts": {
            "due": len(due),
            "overdue": sum(1 for r in due if r["overdue"]),
            "upcoming": len(upcoming),
            "closed": len(closed),
        },
        "rules": _rule_views(db),
        "next_send": cadence.upcoming_send_dates(db, today)[0],
    }


@router.get("/followups", response_class=HTMLResponse, include_in_schema=False)
def followups_page(request: Request, db: Session = Depends(get_db),
                   user: User = Depends(get_current_user), msg: str = ""):
    """옛 주소 — 딜 진행 관리 한 페이지의 리마인드 구역으로 보낸다.

    즐겨찾기와 화면 안 링크가 여럿 걸려 있어 살려 둔다.
    """
    return RedirectResponse("/ir#remind", status_code=307)


def _clean_dates(value: str) -> Optional[str]:
    """입력한 날짜를 정리한다. 형식이 틀린 값은 버린다 — 회차일이 엉키면 안 된다."""
    out = []
    for part in (value or "").replace("\n", ",").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            out.append(date.fromisoformat(part).isoformat())
        except ValueError:
            continue
    return ",".join(sorted(set(out))) or None


def _rule_views(db: Session) -> List[dict]:
    out = []
    for key in ("deal_cycle", "remind", "meeting"):
        rule = cadence.get_rule(db, key)
        if rule.get("kind") == "monthly_weekday":
            weekdays = "월화수목금토일"
            nth = ", ".join(f"{n}번째" for n in cadence._nth_list(rule.get("nth_weeks")))
            wd = rule.get("weekday")
            desc = f"매월 {nth} {weekdays[wd]}요일" if wd is not None else "-"
        else:
            lo, hi = rule.get("offset_min_days"), rule.get("offset_max_days")
            desc = f"딜소개 {lo}~{hi}일 뒤" if lo is not None else "-"
        extra = rule.get("extra_dates") or ""
        if extra:
            desc += f" (추가: {extra.replace(',', ', ')})"
        out.append({"key": key, "label": rule.get("label", key), "desc": desc,
                    "extra_dates": rule.get("extra_dates") or "",
                    "skip_dates": rule.get("skip_dates") or "",
                    "weekday": rule.get("weekday"),
                    "nth_weeks": rule.get("nth_weeks"),
                    "offset_min_days": rule.get("offset_min_days"),
                    "offset_max_days": rule.get("offset_max_days"),
                    "kind": rule.get("kind")})
    return out


# --- 상태 바꾸기 ------------------------------------------------------------

@router.post("/followups/{sequence_id}/responded", include_in_schema=False)
def mark_responded(sequence_id: int, db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)):
    """답이 왔으니 리마인드를 멈춘다."""
    seq = _owned(db, sequence_id, user)
    cadence.stop(db, seq, "답을 받았습니다", status="responded")
    db.commit()
    return RedirectResponse("/followups?msg=리마인드를+멈췄습니다", status_code=303)


@router.post("/followups/{sequence_id}/stop", include_in_schema=False)
def stop_sequence(sequence_id: int, reason: str = Form(""),
                  db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    seq = _owned(db, sequence_id, user)
    cadence.stop(db, seq, reason.strip() or "사람이 중단")
    db.commit()
    return RedirectResponse("/followups?msg=리마인드를+중단했습니다", status_code=303)


@router.post("/followups/{sequence_id}/resume", include_in_schema=False)
def resume_sequence(sequence_id: int, db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    seq = _owned(db, sequence_id, user)
    cadence.resume(db, seq)
    db.commit()
    return RedirectResponse("/followups?msg=리마인드를+다시+켰습니다", status_code=303)


@router.post("/followups/backfill", include_in_schema=False)
def backfill(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """이 기능을 켜기 전에 나간 회차에도 리마인드를 걸어 준다."""
    made = cadence.backfill_from_history(db, user.id)
    return RedirectResponse(f"/followups?msg=지난+발송에서+{made}건을+잡았습니다",
                            status_code=303)


# --- 주기 규칙 --------------------------------------------------------------

@router.post("/followups/rules/{key}", include_in_schema=False)
def update_rule(
    key: str,
    weekday: Optional[int] = Form(None),
    nth_weeks: str = Form(""),
    extra_dates: str = Form(""),
    skip_dates: str = Form(""),
    offset_min_days: Optional[int] = Form(None),
    offset_max_days: Optional[int] = Form(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """주기를 화면에서 바꾼다. 관리자만 — 팀 전체의 발송 일정이 바뀐다."""
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="주기 변경은 관리자만 할 수 있습니다")
    if key not in cadence.DEFAULT_RULES:
        raise HTTPException(status_code=404, detail="알 수 없는 규칙입니다")

    row = db.execute(select(ScheduleRule).where(ScheduleRule.key == key)).scalars().first()
    if row is None:
        row = ScheduleRule(key=key, **{k: v for k, v in cadence.DEFAULT_RULES[key].items()})
        db.add(row)
        db.flush()

    if row.kind == "monthly_weekday":
        if weekday is not None and 0 <= weekday <= 6:
            row.weekday = weekday
        if nth_weeks.strip():
            row.nth_weeks = nth_weeks.strip()
        row.extra_dates = _clean_dates(extra_dates)
        row.skip_dates = _clean_dates(skip_dates)
    else:
        if offset_min_days is not None and offset_min_days >= 0:
            row.offset_min_days = offset_min_days
        if offset_max_days is not None and offset_max_days >= (row.offset_min_days or 0):
            row.offset_max_days = offset_max_days
    db.commit()
    return RedirectResponse("/followups?msg=주기를+바꿨습니다", status_code=303)
