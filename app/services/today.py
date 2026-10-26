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

from datetime import date, datetime
from typing import List, Optional

from sqlalchemy.orm import Session

from .. import clock
from ..models import User
from . import (auto_send, automation_runner, cadence, call_flags, pipeline,
               readiness, recontact, scheduled_send, send_guard, sourcing_mail)

# 줄 하나 = 오늘 할 일 하나.
#   kind  : 화면에서 묶어 보여줄 종류
#   level : urgent(지났거나 오늘) · soon(곧) · info(참고)


def _item(kind: str, level: str, title: str, detail: str,
          href: str, count: Optional[int] = None) -> dict:
    return {"kind": kind, "level": level, "title": title,
            "detail": detail, "href": href, "count": count}


def _at(day: date) -> datetime:
    """그날 **이 시각**. 예약이 지났는지는 날짜가 아니라 시각으로 갈린다.

    오늘 것이면 진짜 지금을 쓴다(`clock.now()`). 검사가 `today=` 로 다른 날을
    못박았으면 그날 정오로 본다 — 그 날짜의 하루 안쪽이면 어느 시각이든 같은
    답이 나오게 하려는 것이다. 실제 시계에 기대는 검사를 만들지 않는다.
    """
    now = clock.now()
    if day == now.date():
        return now
    return datetime(day.year, day.month, day.day, 12, 0).astimezone()


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

    # 1-1) **답 없음 · 전화 필요**(10/17 회의 #37) — 리마인드 카톡을 보냈는데 답이
    # 없어서 팀원·담당자가 표시해 둔 곳. 그 투자사를 맡은 사람에게 선다(관리자가
    # 대신 켜도 맡은 사람에게 간다). 표시를 끄면 여기서 빠진다 — 따로 지울 것이
    # 없다. 세는 자리는 딜 진행 관리 `전화 요청` 구역과 같은 한 벌이다.
    calls = call_flags.needed_for(db, user)
    if calls:
        items.append(_item(
            "call", "urgent", "전화 필요 — 리마인드에 답 없음",
            ", ".join(f"{c['name']}({c['firm']})" if c["firm"] else c["name"]
                      for c in calls[:3])
            + (" 외" if len(calls) > 3 else ""),
            "/ir#calls", len(calls)))

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

    # **자동화(A7)가 이미 물은 미팅**(#31) — 또 묻지 말고 들은 답만 적는다.
    # 위 `미팅 결과 문의` 에서는 빠져 있다(`pipeline.today_items`).
    if ir["asked_followups"]:
        items.append(_item(
            "meeting", "soon", "자동 문의한 미팅 — 들은 답 적기",
            ", ".join(f"{m['name']} 자동 문의함 {m['auto_asked_on']}".rstrip()
                      for m in ir["asked_followups"][:3]),
            "/ir#meetings", len(ir["asked_followups"])))

    # **재접촉 시기**(#68) — 2차·후속 미팅을 보류로 마친 투자사에 90일마다. 알림만이다
    # (아무것도 안 보낸다). 판정은 `recontact.due` 한 곳 — 매출예상리스트가 같은 목록을 그린다.
    again = recontact.due(db, {user.id}, today)
    if again:
        names = []
        for r in again[:3]:
            about = " · ".join(p for p in (r["firm"], r["company_name"]) if p)
            names.append(f"{r['name']}({about})" if about else r["name"])
        items.append(_item(
            "meeting", "soon", recontact.TITLE,
            ", ".join(names) + (" 외" if len(again) > 3 else ""),
            "/report/forecast#recontact", len(again)))

    # **걷기 전에 세워 둔 옛 `미팅 후기 자동` 목록**(#31 — 결과 문의는 이제 A7
    # 하나다). 예약 시각 없는 `draft` 라 **저절로 안 나간다** — 사람이 보내거나
    # 취소할 때까지 여기 선다(`services/auto_send.waiting_for`). 누르고 취소하는 것은
    # 주인뿐이라(`routers/jobs._job_or_404`) 급한 줄은 주인에게만 서고, 관리자에게는
    # 남의 목록이 몇 개 남았는지 참고 한 줄이다(PR #315 리뷰).
    others = []
    for waiting in auto_send.waiting_for(db, user):
        if waiting["user_id"] != user.id:
            others.append(waiting)
            continue
        items.append(_item(
            "meeting", "urgent", "옛 미팅 후기 자동 준비 목록이 남아 있습니다",
            f"{waiting['count']}명 — 자동화 전환 전에 선 목록이라 저절로 나가지 "
            "않습니다. 확인하고 [발송 시작] 하거나 [취소] 하세요",
            f"/jobs/{waiting['job_id']}", waiting["count"]))
    if others:
        names = []
        for waiting in others:
            owner = db.get(User, waiting["user_id"])
            name = owner.name if owner else f"#{waiting['user_id']}"
            if name not in names:
                names.append(name)
        items.append(_item(
            "meeting", "info", "옛 미팅 후기 자동 준비 목록 — 다른 팀원 계정",
            f"{', '.join(names)} 님 계정에 {len(others)}개 — 저절로 나가지 않습니다. "
            "주인이 [발송 시작] 하거나 [취소] 합니다",
            f"/jobs/{others[0]['job_id']}", len(others)))

    # **걸어 두고 아직 안 나간 예약 발송.** 예약해 놓고 잊는 것이 그 기능에서
    # 가장 흔한 사고라, 아침에 여는 이 화면에 서 있어야 한다
    # (`services/scheduled_send.py: standing_for`).
    #
    # 급한 차례는 서비스가 정한다 — 지나 버린 것(저절로 안 나간다) > 오늘 것 >
    # 그 뒤. 여기서 다시 가리면 두 벌이 된다.
    for booked in scheduled_send.standing_for(db, user, _at(today)):
        items.append(_item(
            "send", booked["level"],
            ("예약 시각을 놓쳤습니다" if booked["state"] == "expired"
             else "예약해 둔 발송"),
            booked["sentence"], f"/jobs/{booked['job_id']}", booked["count"]))

    # **자동 회차의 사고** — 실패가 있는 채로 끝났거나(주인·관리자), 예약
    # 시각을 놓쳤다(관리자 — 주인에게는 바로 위 예약 줄이 이미 선다).
    # 자동화는 사람이 안 보는 사이에 돌기 때문에, 여기 안 뜨면 아무도 모른다.
    # 판정은 `services/send_guard.alerts_for` 한 곳이다.
    for alert in send_guard.alerts_for(db, user, today, _at(today)):
        items.append(_item(
            "send", "urgent", alert["title"], alert["detail"],
            f"/jobs/{alert['job_id']}", alert["count"]))

    # **2단계 자동화** — 못 세운 회차(0건 · 실패), 관리자에게는 오늘 선 회차,
    # 자동화가 따로 세우는 줄(내일 나갈 곳 등). 판정은 `automation_runner` 한 곳.
    for line in automation_runner.today_items(db, user, _at(today)):
        items.append(_item("send", line["level"], line["title"], line["detail"],
                           line["href"], line.get("count")))

    # **스타트업 월간 발송이 이 달 안 나갔다 · 안 나간다**(A5 — 관리자 · 메뉴의 계정).
    # 위 자동화 줄은 그날만 선다 — 이것은 그 달이 끝나거나 나갈 때까지 선다
    # (`automations.startup_monthly.today_lines`).
    from .automations import startup_monthly as a5

    for line in a5.today_lines(db, user, _at(today)):
        items.append(_item("send", line["level"], line["title"], line["detail"],
                           line["href"], line.get("count")))

    # **딜 소싱 메일 확인** — 관리자에게. 매일 18:00 회차가 **새로 딜 받음을
    # 세웠을 때만** 그 결과(오늘 · 어제), 그리고 마지막 확인이 실패했으면 고칠
    # 때까지 그 사유. 아무도 새로 안 선 날은 안 선다(`services/sourcing_mail.py`).
    for line in sourcing_mail.today_items(db, user, _at(today)):
        items.append(_item("sourcing", line["level"], line["title"], line["detail"],
                           line["href"], line.get("count")))

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
