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
    later = [r for r in rows if r["status"] == "active" and r["due"]
             and r["due"] > today.isoformat()]
    closed = [r for r in rows if r["status"] != "active"]

    # ── 전화는 `오늘 보낼 리마인드` 에서 갈라 낸다 ──────────────────────────
    #
    # 그 구역의 묶음 머리에는 [{단계} 보내기] 가 달려 있고, 누르면 그 사람들이
    # 골라진 발송 화면으로 간다. **전화는 갈 발송 화면이 없다** — 앱이 대신
    # 걸 수 없고 사람이 건다. 같은 묶음에 세우면 누를 수 없는 단추가 서거나,
    # 눌러 봐야 보낼 문구가 없는 화면이 열린다.
    #
    # 그래서 제 구역을 준다(`templates/ir.html` 의 `전화 요청`). 거기 줄마다
    # 서는 것은 [보내기] 가 아니라 **[전화함]** 이다.
    #
    # 가르는 자리는 여기 하나다 — 화면이 제 손으로 단계를 보고 거르면, 단계가
    # 하나 더 늘어날 때 화면만 옛 갈래로 남는다.
    def is_call(row):
        return row["next_stage"] == cadence.STAGE_CALL

    calls = [r for r in due if is_call(r)]
    sends = [r for r in due if not is_call(r)]
    # 예약된 것도 같이 가른다. `예약된 리마인드` 표는 **보낼 것**을 세우는
    # 자리이고(`_upcoming_followups.html`), 전화는 아래 제 구역에 `예정` 으로
    # 선다 — 안 가르면 한 줄이 두 표에 나란히 서서 두 건으로 읽힌다.
    upcoming = [r for r in later if not is_call(r)]

    # 오늘 보낼 것을 단계별로 묶어 둔다 — 한 번에 같은 문구로 나가야 한다.
    by_stage = {}
    for row in sends:
        by_stage.setdefault(row["next_stage"], []).append(row)

    return {
        "due": due,
        "due_groups": [
            {"stage": stage, "label": cadence.STAGE_LABELS.get(stage, ""),
             "mode": cadence.STAGE_MODES.get(stage, ""), "rows": items}
            for stage, items in sorted(by_stage.items())
        ],
        # 오늘까지 **걸어야 할 전화**. 지난 날짜도 들어 있다(`due` 와 같은 기준) —
        # 놓친 전화가 목록에서 사라지면 이 단계를 둔 뜻이 없다.
        "calls": calls,
        # 아직 날이 안 온 전화. 언제 걸 곳이 몇 군데인지 미리 보여 준다.
        "calls_upcoming": [r for r in later if is_call(r)],
        "upcoming": upcoming,
        "closed": closed,
        "remind_counts": {
            # **보낼 것만 센다.** 이 수는 `오늘 보낼 리마인드` 판의 머리에
            # 뜨는데, 전화까지 더하면 그 판에 없는 줄이 수에 섞인다.
            "due": len(sends),
            "overdue": sum(1 for r in sends if r["overdue"]),
            "upcoming": len(upcoming),
            "closed": len(closed),
            "call": len(calls),
            "call_overdue": sum(1 for r in calls if r["overdue"]),
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
    # 화면의 `발송 주기` 판에 세울 규칙들. **`cadence.DEFAULT_RULES` 에 있는
    # 것은 여기도 있어야 한다** — 빠진 규칙은 화면에 안 보이고, 관리자가 고칠
    # 길도 없어 코드에 박아 둔 것과 다를 바 없어진다.
    for key in cadence.DEFAULT_RULES:
        rule = cadence.get_rule(db, key)
        if rule.get("kind") == "monthly_weekday":
            weekdays = "월화수목금토일"
            nth = ", ".join(f"{n}번째" for n in cadence._nth_list(rule.get("nth_weeks")))
            wd = rule.get("weekday")
            desc = f"매월 {nth} {weekdays[wd]}요일" if wd is not None else "-"
        else:
            lo, hi = rule.get("offset_min_days"), rule.get("offset_max_days")
            # **무엇을 기준으로 센 며칠인가.** 전에는 전부 `딜소개` 라고 적혀
            # 있었는데, 전화는 미팅 요청을 보낸 날에서 센다 — 기준 말은
            # `cadence.OFFSET_BASE` 한 곳이 쥔다.
            #
            # 폭이 없는 규칙(전화의 `3~3`)은 한 수로 적는다. `3~3일 뒤` 는
            # 무엇이 흔들린다는 말로 읽히는데 흔들리는 것이 없다.
            base = cadence.OFFSET_BASE.get(key, "딜소개")
            span = f"{lo}일" if hi in (None, lo) else f"{lo}~{hi}일"
            desc = f"{base} {span} 뒤" if lo is not None else "-"
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


@router.post("/followups/{sequence_id}/called", include_in_schema=False)
def mark_called(sequence_id: int, db: Session = Depends(get_db),
                user: User = Depends(get_current_user)):
    """**전화를 걸었다**고 적는다 — 흐름의 마지막 단계.

    `답 옴`·`중단` 과 나란히 두지만 뜻이 다르다. 그 둘은 **흐름을 멈추는** 것이고
    (답이 왔거나 더 안 하기로 했거나), 이것은 **할 일을 끝낸** 것이다. 같은
    `중단` 으로 적으면 나중에 "전화까지 다 한 곳" 과 "도중에 그만둔 곳" 이
    한 덩어리가 되어, 이 단계를 둔 뜻이 사라진다.

    그래서 상태가 `완료`(`done`)다 — 사다리 끝까지 간 건에 붙는 그 값이고,
    단계를 올리는 것도 다른 단계와 **같은 한 곳**을 지난다
    (`cadence.mark_called` → `cadence.advance`).

    **[전화 걸기] 가 아니다.** 앱이 걸 수 없으므로 이 자리가 할 수 있는 것은
    사람이 건 것을 적는 일뿐이고, 단추 이름도 그렇게 적혀 있어야 한다.
    """
    seq = _owned(db, sequence_id, user)
    cadence.mark_called(db, seq)
    db.commit()
    return RedirectResponse("/ir?msg=전화했다고+적었습니다#calls", status_code=303)


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


@router.post("/followups/{sequence_id}/delete", include_in_schema=False)
def delete_sequence(sequence_id: int, db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    """`IR 요청 투자사` 표에서 줄 하나를 없앤다.

    **지우는 것은 `SendSequence` 한 줄뿐이다.** 명단(`VcContact`)·발송 기록
    (`SendJob`·`SendItem`)·활동(`ContactActivity`)은 건드리지 않는다 — 사람이
    바라는 것은 "이 표에서 안 보이게" 이지 투자사를 지우는 것이 아니다.
    지운 뒤에도 담당자 줄을 눌러 IR 요청을 기록할 수 있어야 한다.

    **되살아난다.** 그 담당자에게 나간 딜소개 발송 기록이 남아 있으므로
    [지난 발송에서 리마인드 걸기](`/followups/backfill`)를 누르면 이 줄이 다시
    선다. 지웠는데 다시 생기면 사람은 고장으로 읽으니, 확인 문구에 그 사실을
    적어 두었다(`app/templates/_closed_followups.html`).

    누가 지울 수 있나는 **[다시 켜기]와 같은 판정**이다(`_owned`) — 남의
    담당 줄은 찾을 수 없다고 답한다. 여기서 새로 짓지 않는다.
    """
    seq = _owned(db, sequence_id, user)
    db.delete(seq)
    db.commit()
    return RedirectResponse("/followups?msg=리마인드+줄을+지웠습니다", status_code=303)


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
