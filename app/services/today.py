"""오늘 할 일 — 아침에 이 화면만 열면 되게.

지금까지 할 일이 화면마다 흩어져 있었다. 후속 관리에 리마인드가, IR·미팅 관리에
자료 요청이, 회차 준비 점검에 막힌 것이. 매일 세 군데를 돌아야 오늘 뭘 하는지
알 수 있었다.

여기서는 **오늘 손댈 것만** 모은다. 각 줄은 누르면 그 일을 하는 화면으로 간다.
새로 세지 않고 이미 있는 서비스가 낸 값을 그대로 쓴다 — 같은 숫자를 두 곳에서
따로 세면 반드시 어긋난다(실제로 대시보드와 투자사 관리 현황 가 6명 어긋난 적이 있다).

순서는 **급한 것부터**다. 답을 기다리는 사람 > 오늘 약속 > 오늘 보낼 것 > 준비.
"""
from __future__ import annotations

from datetime import date
from typing import List, Optional

from sqlalchemy.orm import Session

from ..models import User
from . import cadence, pipeline, readiness

# 줄 하나 = 오늘 할 일 하나.
#   kind  : 화면에서 묶어 보여줄 종류
#   level : urgent(지났거나 오늘) · soon(곧) · info(참고)


def _item(kind: str, level: str, title: str, detail: str,
          href: str, count: Optional[int] = None) -> dict:
    return {"kind": kind, "level": level, "title": title,
            "detail": detail, "href": href, "count": count}


def build(db: Session, user: User, today: Optional[date] = None) -> dict:
    today = today or date.today()

    items: List[dict] = []

    # 1) 답을 기다리는 사람 — 그 회차에서 가장 뜨거운 반응이다.
    ir = pipeline.today_items(db, user, today)
    if ir["overdue_requests"]:
        names = ", ".join(f"{r['name']}({r['company_name']})"
                          for r in ir["overdue_requests"][:3])
        items.append(_item(
            "ir", "urgent", "사흘 넘게 못 보낸 IR 자료",
            f"{names}{' 외' if len(ir['overdue_requests']) > 3 else ''}",
            "/ir", len(ir["overdue_requests"])))
    elif ir["open_requests"]:
        items.append(_item(
            "ir", "soon", "보낼 IR 자료",
            ", ".join(f"{r['name']}({r['company_name']})"
                      for r in ir["open_requests"][:3]),
            "/ir", len(ir["open_requests"])))

    # 2) 오늘 약속
    for meeting in ir["today_meetings"]:
        items.append(_item(
            "meeting", "urgent", f"오늘 미팅 · {meeting['kind_label']}",
            f"{meeting['name']} {meeting['title']} · {meeting['firm']}",
            "/ir"))

    if ir["due_followups"]:
        items.append(_item(
            "meeting", "urgent", "미팅 결과 문의",
            ", ".join(m["name"] for m in ir["due_followups"][:3]),
            "/ir", len(ir["due_followups"])))

    # 3) 오늘 보낼 리마인드
    cadence.sweep_reactions(db, user.id)
    seq_rows = cadence.sequence_rows(db, user.id, today)
    due = [r for r in seq_rows if r["status"] == "active" and r["due"]
           and r["due"] <= today.isoformat()]
    if due:
        overdue = [r for r in due if r["overdue"]]
        items.append(_item(
            "followup", "urgent" if overdue else "soon",
            "리마인드 보내기",
            ", ".join(f"{r['name']}({r['next_label']})" for r in due[:3]),
            "/followups", len(due)))

    # 4) 회차 준비 — 발송일이 가까울수록 급해진다.
    ready = readiness.report(db, user, today)
    days = ready["days_left"]
    if days <= 0:
        items.append(_item("cycle", "urgent", "오늘이 딜 제안 날입니다",
                           "기업을 고르고 발송하세요", "/deals"))
    elif days <= 3:
        items.append(_item("cycle", "soon", f"딜 제안 {days}일 전",
                           f"{ready['next_send'].strftime('%m월 %d일')} · 준비 상태를 확인하세요",
                           "/readiness"))
    for blocked in ready["blocked"]:
        items.append(_item("block", "urgent", blocked["title"],
                           blocked["detail"], blocked["href"] or "/readiness"))

    order = {"urgent": 0, "soon": 1, "info": 2}
    items.sort(key=lambda x: order.get(x["level"], 9))

    return {
        "items": items,
        "urgent": [x for x in items if x["level"] == "urgent"],
        "next_send": ready["next_send"],
        "days_left": days,
        "ready": ready["ready"],
        "nothing_to_do": not items,
    }
