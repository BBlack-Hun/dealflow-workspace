"""주간·월간 업무 보고 — 시트에 손으로 적던 것을 기록에서 뽑는다.

원본 시트는 이런 모양이었다.

    6월 미팅 총 4개사
      6월 첫주   미팅 완료 2개사   결과 문의전화 완료
      6월 둘째주 미팅 완료 0개사
      6월 셋째주 6/16 (주)○○ / ○○PE   6/26 결과 문의 : …

미팅을 하고 나서 사람이 다시 시트에 옮겨 적고 있었다. 이제 미팅을 기록하면
같은 표가 저절로 나온다 — 옮겨 적는 사이에 빠지는 건이 없어진다.

**결과 문의(미팅 후 열흘)를 했는지**를 함께 센다. 원본 시트에도
"결과확인전화가 없으면 계약을 잊어버리는 경우가 발생할 수 있습니다" 라고
적혀 있었다. 그게 이 보고의 목적이다.

**발송(딜 소개·딜 소싱)도 같이 뽑는다.** 회차가 끝나면 카톡으로 이런 보고를
손으로 써서 보내고 있었다.

    딜소개 업무(핵심 딜 7개사)
    - 총 126명
    116개[8/27(목) 116개 완료]

    딜 소싱 2건(8/27(목)) 완료

미팅과 같은 이유로 이것도 여기서 나와야 한다 — 손으로 세어 옮겨 적으면
틀린다. 실제로 위 보고의 `116개 완료` 는 그 회차가 18건에서 중단된 것을
모르고 대상 수를 그대로 옮겨 적은 것이었다.
"""
from __future__ import annotations

from calendar import monthrange
from collections import Counter
from datetime import date
from typing import Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (DealBatch, DealBatchCompany, IrCompany, IrRequest,
                      Meeting, SendItem, SendJob, User, VcContact)
from .pipeline import (MEETING_FOLLOWUP_DAYS, MEETING_KINDS,
                       NO_FOLLOWUP_OUTCOMES, OUTCOMES, REQUEST_STATUS)
from .weekly import WEEKDAYS

WEEK_NAMES = ["첫주", "둘째주", "셋째주", "넷째주", "다섯째주", "여섯째주"]

#: 보고에 싣는 발송 종류. 사용자가 카톡 보고에서도 둘을 나눠 적었다 —
#: 딜 소개는 투자사 명단에, 딜 소싱은 "우리 딜을 같이 볼 사람" 에게 가는
#: 다른 일이라 한 줄에 섞으면 무엇을 몇 건 했는지가 사라진다.
#:
#: IR 자료 전달(`ir_delivery`)은 여기 넣지 않는다. 아래 'IR 자료 요청' 칸이
#: 요청받은 것과 전달한 것을 이미 세고 있어, 여기 또 실으면 같은 일이 두 번
#: 세어진다. 방 연결 확인(`verify_room`)은 아무것도 보내지 않으므로 애초에
#: 발송이 아니다(`models.SEND_KINDS` 의 이유와 같다).
SEND_GROUPS = (("deal_intro", "딜 소개"), ("sourcing_intro", "딜 소싱"))

#: 회차 상태를 읽는 말로. 발송 진행 화면(`static/js/progress.js` 의
#: `JOB_STATUS_KO`)과 **같은 말을 써야 한다** — 같은 회차가 화면마다 다른
#: 말로 불리면 어느 쪽을 믿을지 알 수 없다.
SEND_STATUS = {
    "draft": "작성 중",
    "queued": "대기 중",
    "running": "보내는 중",
    "paused": "멈춤",
    "done": "완료",
    "done_with_errors": "완료(실패 있음)",
    "canceled": "중단됨",
}


def _as_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def day_label(value: Optional[str]) -> str:
    """`2026-08-27` → `8/27(목)`.

    사용자가 카톡 보고에 쓰던 표기 그대로다. **요일이 붙어야** 한다 —
    회차는 요일로 기억되는 일이라("목요일 회차"), 날짜만 있으면 그 줄이
    어느 회차였는지 다시 달력을 봐야 한다.
    """
    day = _as_date(value)
    if day is None:
        return ""
    return f"{day.month}/{day.day}({WEEKDAYS[day.weekday()]})"


def week_of_month(day: date) -> int:
    """그 달의 몇 번째 주인가 (1부터). **1~7일이 첫주.**

    예전에는 '1일이 낀 주가 첫주'로 셌는데, 활동 이력·회차명은 1~7일을 첫주로
    센다(`sheet_import.week_of_month`, 시트 머리글의 "첫째주 수요일" 표기).
    규칙이 둘이면 같은 날이 화면마다 3주차·4주차로 갈린다 — 실제로 갈렸다.
    """
    from .sheet_import import week_of_month as by_day

    return by_day(day.isoformat()) or 1


def month_range(year: int, month: int) -> tuple:
    last = monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last)


def monthly(db: Session, year: int, month: int,
            user: Optional[User] = None, today: Optional[date] = None) -> dict:
    """한 달치 보고. `user` 를 주면 그 사람 것만, 없으면 팀 전체."""
    today = today or date.today()
    start, end = month_range(year, month)

    stmt = select(Meeting).where(Meeting.scheduled_at >= start.isoformat(),
                                 Meeting.scheduled_at <= end.isoformat())
    if user is not None:
        stmt = stmt.where(Meeting.user_id == user.id)
    meetings = db.execute(stmt.order_by(Meeting.scheduled_at)).scalars().all()

    # IR 요청도 같은 달로 함께 읽는다. 미팅만으로는 그 달의 반응이 안 보인다.
    ir_stmt = select(IrRequest).where(IrRequest.requested_at >= start.isoformat(),
                                      IrRequest.requested_at <= end.isoformat())
    if user is not None:
        ir_stmt = ir_stmt.where(IrRequest.user_id == user.id)
    requests = db.execute(ir_stmt).scalars().all()

    # 담당자는 **미팅과 요청 양쪽**에서 모은다. 미팅 것만 불러오면 요청 줄의
    # 이름이 `-` 로 비어, 보고를 그대로 옮겨 적을 수가 없다.
    need = {m.contact_id for m in meetings} | {r.contact_id for r in requests}
    contacts = {
        c.id: c for c in db.execute(
            select(VcContact).where(VcContact.id.in_(need or {0}))
        ).scalars().all()
    }
    owners = {u.id: u.name for u in db.execute(select(User)).scalars().all()}

    # 결과를 물어볼 필요가 남은 건만 센다. 규칙은 딜 진행 관리와 같아야 한다 —
    # 한쪽에서는 "물어봐야 함", 다른 쪽에서는 "끝남" 이면 어느 쪽을 믿을지 모른다.
    #   거절로 끝났다     → 물어볼 것이 없다
    #   다음 미팅을 잡았다 → 이미 이어졌다
    latest: Dict[int, str] = {}
    for m in meetings:
        when_iso = m.scheduled_at or ""
        if when_iso > latest.get(m.contact_id, ""):
            latest[m.contact_id] = when_iso

    def open_followup(m) -> bool:
        return (not m.followup_done
                and (m.outcome or "") not in NO_FOLLOWUP_OUTCOMES
                and (m.scheduled_at or "") >= latest.get(m.contact_id, ""))

    weeks: Dict[int, List[dict]] = {}
    for meeting in meetings:
        when = _as_date(meeting.scheduled_at)
        if when is None:
            continue
        contact = contacts.get(meeting.contact_id)
        due = _as_date(meeting.followup_due)
        weeks.setdefault(week_of_month(when), []).append({
            "date": meeting.scheduled_at,
            "name": contact.name if contact else "-",
            "firm": (contact.firm or "") if contact else "",
            "company": meeting.company_name or "",
            "kind": MEETING_KINDS.get(meeting.kind, meeting.kind),
            "status": meeting.status,
            "outcome": OUTCOMES.get(meeting.outcome or "", ""),
            "owner": owners.get(meeting.user_id, ""),
            "followup_due": meeting.followup_due or "",
            "followup_done": bool(meeting.followup_done),
            # 딜 진행 관리에서 적은 후기·결과 문의 내용을 그대로 가져온다.
            # 보고를 쓰려고 같은 말을 두 번 적게 하면 한쪽은 반드시 비어 있게
            # 된다 — 그러면 어느 쪽이 진짜인지 알 수 없다.
            "note": meeting.note or "",
            "followup_note": meeting.followup_note or "",
            "followup_at": meeting.followup_at or "",
            # 열흘이 지났는데 아직 안 물어봤다 — 이 보고가 잡아내야 할 것.
            # 거절로 끝났거나 다음 미팅을 잡은 건은 뺀다.
            "followup_late": bool(
                meeting.status == "done" and open_followup(meeting)
                and due is not None and due <= today),
            "needs_followup": meeting.status == "done" and open_followup(meeting),
        })

    done = [m for m in meetings if m.status == "done"]

    rows = [
        {"week": w, "label": f"{month}월 {WEEK_NAMES[w - 1] if w <= len(WEEK_NAMES) else f'{w}주'}",
         "items": sorted(items, key=lambda x: x["date"]),
         "done": sum(1 for x in items if x["status"] == "done")}
        for w, items in sorted(weeks.items())
    ]

    outcome_counts = {}
    for meeting in done:
        label = OUTCOMES.get(meeting.outcome or "", "결과 미정")
        outcome_counts[label] = outcome_counts.get(label, 0) + 1

    # 발송도 같은 규칙으로 — 관리자가 팀 전체를 볼 때는 `user` 가 없다.
    sends = _sends(db, start, end, user, owners)

    return {
        "year": year,
        "month": month,
        # 한 달에 두 번(첫째·셋째 수요일) 도는 일이라, 그 달에 무엇이 오갔는지를
        # **한눈에** 봐야 한다. 다섯 가지를 날짜와 함께 그대로 늘어놓는다.
        "buckets": _buckets(meetings, requests, contacts, owners, today,
                            open_followup),
        # 그 달에 나간 회차. 카톡으로 손으로 쓰던 보고가 이것이다.
        "sends": sends,
        # 연간 보고가 달마다 더해 쓰는 값. **월간과 같은 곳에서 나와야** 두
        # 화면의 숫자가 어긋나지 않는다(미팅 쪽이 이미 그렇게 되어 있다).
        "send_rounds": sends["rounds"],
        "send_sent": sends["sent"],
        "send_left": sends["left"],
        "weeks": rows,
        # 화면 안내문이 "미팅 뒤 N일쯤" 이라고 말할 때 쓰는 값 — 코드와
        # 화면이 다른 숫자를 말하면 안 된다.
        "followup_days": MEETING_FOLLOWUP_DAYS,
        "total": len(meetings),
        "done": len(done),
        "canceled": sum(1 for m in meetings if m.status == "canceled"),
        "followup_done": sum(1 for m in done if m.followup_done),
        # **아직 안 물어본 것 전부.** 예전엔 '날짜가 지난 것'만 셌는데, 물어볼
        # 날이 아직 안 온 건은 어느 칸에도 안 잡혀서 미팅 2건이 대기 중인데도
        # 화면에는 0 / 0 으로 떠 아무것도 없는 것처럼 보였다.
        "followup_open": sum(1 for m in done if open_followup(m)),
        # 그중 날짜가 지난 것 — 이건 급한 것이라 따로 센다.
        "followup_late": sum(
            1 for w in rows for x in w["items"] if x["followup_late"]),
        "outcomes": sorted(outcome_counts.items(), key=lambda t: -t[1]),
        "ir_requested": len(requests),
        "ir_delivered": sum(1 for r in requests if r.status == "delivered"),
        "ir_open": sum(1 for r in requests if r.status == "open"),
    }


def _job_date(job: SendJob, batch: Optional[DealBatch]) -> str:
    """이 회차가 **언제 것인가**.

    회차일(`DealBatch.sent_date`)을 쓰고, 없으면 시작 시각의 날짜를 쓴다 —
    대시보드의 '최근 발송 회차'(`dashboard.recent_batches`)와 같은 기준이다.
    두 화면이 같은 회차를 다른 날로 부르면 안 된다.

    건마다 나간 시각(`SendItem.sent_at`)으로 달을 가르지 않는다. 밤에 시작해
    자정을 넘긴 회차가 두 달에 쪼개지는데, 사람이 부르는 회차는 **하루**다.
    """
    return (batch.sent_date if batch is not None else None) or (job.started_at or "")[:10]


def _sends(db: Session, start: date, end: date, user: Optional[User],
           owners: Dict[int, str]) -> dict:
    """그 달에 나간 딜 소개·딜 소싱 회차.

    카톡으로 손으로 쓰던 보고가 이 표다.

        딜소개 업무(핵심 딜 7개사)
        - 총 126명
        116개[8/27(목) 116개 완료]

    **완료는 실제로 나간 건만 센다.** 위 보고는 대상 116명을 그대로
    `116개 완료` 로 적었는데 그 회차는 18건에서 중단됐다 — 손으로 옮겨 적으면
    이런 거짓 보고가 나온다. `status="sent"` 인 건만 세고, 대상이었는데 안 나간
    건은 `left` 로 따로 드러낸다.

    회차 수·건수는 `SendJob.total`/`sent` 같은 세어 둔 칸을 믿지 않고 발송 건을
    직접 센다. 세어 둔 칸은 중단·재시도를 거치며 실제와 어긋날 수 있고, 보고는
    그 어긋남이 드러나야 할 자리다.
    """
    kinds = [kind for kind, _ in SEND_GROUPS]
    stmt = (select(SendJob, DealBatch)
            .outerjoin(DealBatch, DealBatch.id == SendJob.batch_id)
            .where(SendJob.kind.in_(kinds)))
    if user is not None:
        stmt = stmt.where(SendJob.user_id == user.id)

    lo, hi = start.isoformat(), end.isoformat()
    jobs = [(job, batch) for job, batch in db.execute(stmt).all()
            if lo <= _job_date(job, batch) <= hi]

    job_ids = [job.id for job, _ in jobs]
    counts: Dict[int, Counter] = {}
    people: Dict[int, set] = {}
    for item_id, job_id, status, contact_id, sourcing_id in db.execute(
        select(SendItem.id, SendItem.job_id, SendItem.status,
               SendItem.contact_id, SendItem.sourcing_contact_id)
        .where(SendItem.job_id.in_(job_ids or [0]))
    ).all():
        counts.setdefault(job_id, Counter())[status or ""] += 1
        # 받는 사람은 투자사 담당자이거나 소싱 명단이거나 — 서로 다른 표라
        # 어느 쪽인지까지 키에 담아야 번호가 겹치는 두 사람이 한 명이 되지 않는다.
        who = (("c", contact_id) if contact_id
               else ("s", sourcing_id) if sourcing_id else ("i", item_id))
        people.setdefault(job_id, set()).add(who)

    # 그 회차에 무엇을 소개했나 — 사용자가 `핵심 딜 7개사` 라고 적던 값.
    batch_ids = [b.id for _, b in jobs if b is not None]
    named: Dict[int, List[str]] = {}
    for batch_id, name in db.execute(
        select(DealBatchCompany.batch_id, IrCompany.name)
        .join(IrCompany, IrCompany.id == DealBatchCompany.company_id)
        .where(DealBatchCompany.batch_id.in_(batch_ids or [0]))
        .order_by(DealBatchCompany.position)
    ).all():
        named.setdefault(batch_id, []).append(name)

    groups = []
    for kind, label in SEND_GROUPS:
        # **회차마다 한 줄.** 같은 날 회차가 둘이어도 합치지 않는다 — 8/27 에
        # 두 회차가 있었고 하나는 18건에서 멈췄는데, 합치면 그 사실이 묻혀
        # `116개 완료` 가 된다. 손으로 쓰던 보고가 실제로 그렇게 틀렸다.
        picked = sorted((t for t in jobs if t[0].kind == kind),
                        key=lambda t: (_job_date(*t), t[0].id))
        rows, targeted, companies = [], set(), set()
        for job, batch in picked:
            got = counts.get(job.id, Counter())
            target = sum(got.values())
            sent = got.get("sent", 0)
            left = target - sent
            waiting = got.get("pending", 0) + got.get("sending", 0)
            names = named.get(batch.id, []) if batch is not None else []
            when = _job_date(job, batch)
            targeted |= people.get(job.id, set())
            companies.update(names)
            rows.append({
                "job_id": job.id,
                "title": (batch.title if batch is not None else "") or "회차명 없음",
                "date": when,
                "day": day_label(when),
                "companies": len(names),
                "company_names": names,
                # 대상 = 발송 목록에 오른 사람. 완료 = 실제로 도착한 건.
                "target": target,
                "sent": sent,
                "failed": got.get("failed", 0),
                "canceled": got.get("canceled", 0),
                "waiting": waiting,
                # 대상이었는데 안 나간 건 — 이 숫자가 0 이어야 `대상 = 완료` 다.
                "left": left,
                # 왜 안 나갔는가. 숫자만 있으면 다시 돌려야 할 것인지
                # (중단·대기) 못 보내는 곳인지(실패) 알 수 없다.
                "left_label": " · ".join(
                    f"{name} {n}건" for name, n in
                    (("중단", got.get("canceled", 0)),
                     ("실패", got.get("failed", 0)),
                     ("아직 안 보냄", waiting)) if n),
                "status": job.status,
                "status_label": SEND_STATUS.get(job.status, job.status),
                "owner": owners.get(job.user_id, ""),
                # 중단은 빨강, 나머지 미완은 노랑. 완료로 잘못 읽히는 것이
                # 이 보고에서 가장 비싼 실수라 눈에 띄어야 한다.
                "level": "bad" if job.status == "canceled" else ("warn" if left else ""),
            })
        groups.append({
            "key": kind,
            "label": label,
            "rows": rows,
            "rounds": len(rows),
            # 그 달에 **대상이 된 사람** 수. 사용자가 `총 126명` 이라고 적던 칸.
            #
            # 겹치면 한 명이다 — 같은 날 두 회차의 대상이 겹치므로 회차별
            # 대상을 더하면 같은 사람을 두 번 센다(97 + 116 = 213 이 아니라 116명).
            #
            # 지금 명단의 크기(발송 가능한 담당자 수)를 쓰지 않는다. 그건 오늘을
            # 세는 값이라 8월 보고를 12월에 열면 숫자가 달라진다 — 보고는 그 달에
            # 한 일의 기록이어야 하고, 명단이 지금 몇 명인지는 투자사 관리 현황이
            # 답할 질문이다.
            "contacts": len(targeted),
            "companies": len(companies),
            "target": sum(r["target"] for r in rows),
            "sent": sum(r["sent"] for r in rows),
            "left": sum(r["left"] for r in rows),
        })

    return {
        "groups": groups,
        "rounds": sum(g["rounds"] for g in groups),
        "sent": sum(g["sent"] for g in groups),
        "left": sum(g["left"] for g in groups),
        # 대상만큼 안 나간 회차가 몇 개인가. 0 이 아니면 대상 수를 완료로
        # 적으면 안 된다는 뜻이라, 화면이 그걸 먼저 말해야 한다.
        "short": sum(1 for g in groups for r in g["rows"] if r["left"]),
    }


def _call_state(due: Optional[str], today: date) -> str:
    """언제 전화할 때인가. `예정` 만으로는 오늘 걸 곳인지 알 수 없다."""
    if not due:
        return "날짜 미정"
    iso = today.isoformat()
    if due < iso:
        return "지남 — 지금 거세요"
    if due == iso:
        return "오늘"
    return f"{due} 예정"


def _buckets(meetings, requests, contacts, owners, today, open_followup) -> List[dict]:
    """대시보드의 반응 다섯 가지를 **그 달치로, 날짜와 함께**.

    숫자만 보면 "그게 누구였지" 가 이어진다. 보고에서는 이름과 날짜가
    나란히 있어야 그대로 옮겨 적을 수 있다.
    """
    def who(contact_id):
        c = contacts.get(contact_id)
        if c is None:
            return {"name": "-", "title": "", "firm": ""}
        return {"name": c.name, "title": c.title or "", "firm": c.firm or ""}

    def row(when, contact_id, company, note, user_id):
        return {"date": when or "", **who(contact_id), "company": company or "",
                "note": note or "", "owner": owners.get(user_id, "")}

    ir = [row(r.requested_at, r.contact_id, r.company_name,
              REQUEST_STATUS.get(r.status, r.status), r.user_id) for r in requests]
    asked = [m for m in meetings if m.status != "done"]
    done = [m for m in meetings if m.status == "done"]

    # 끝난 미팅 중 **아직 결과를 안 물어본 곳**만. 이미 물어본 곳까지 세면
    # 전화할 곳이 몇 군데인지 알 수 없다.
    # 거절로 끝났거나 다음 미팅을 잡은 건도 뺀다 — 물어볼 것이 없다.
    call = [m for m in done if open_followup(m)]

    return [
        {"key": "ir", "label": "IR 요청 투자사", "rows": ir},
        {"key": "meet_ask", "label": "IR 미팅 요청 투자사",
         "rows": [row(m.scheduled_at, m.contact_id, m.company_name,
                      MEETING_KINDS.get(m.kind, m.kind), m.user_id) for m in asked]},
        {"key": "companies", "label": "IR 요청받은 기업",
         "rows": sorted(ir, key=lambda r: r["company"])},
        {"key": "meet_done", "label": "IR 미팅완료 투자사",
         "rows": [row(m.scheduled_at, m.contact_id, m.company_name,
                      OUTCOMES.get(m.outcome or "", "결과 미정"), m.user_id)
                  for m in done]},
        # 여기 뜨는 건 **전화할 곳**이다. 상태는 언제 걸어야 하는지를 말해야
        # 쓸모가 있다 — `예정` 만으로는 오늘 걸 곳인지 알 수 없다.
        {"key": "call", "label": "IR 미팅완료 리마인드 TEL 투자사",
         "rows": [row(m.followup_due or m.scheduled_at, m.contact_id, m.company_name,
                      _call_state(m.followup_due, today), m.user_id)
                  for m in call]},
    ]


def recent_months(today: Optional[date] = None, count: int = 24) -> List[tuple]:
    """최근 달들 (연, 월). 화면의 달 고르기에 쓴다.

    2년치를 낸다 — 작년 이맘때와 견주는 일이 잦은데 6개월만 두면 화면에서
    갈 수가 없다(주소로는 어느 달이든 열린다).
    """
    today = today or date.today()
    out = []
    year, month = today.year, today.month
    for _ in range(count):
        out.append((year, month))
        month -= 1
        if month == 0:
            year, month = year - 1, 12
    return out


def yearly(db: Session, year: int, user: Optional[User] = None,
           today: Optional[date] = None) -> dict:
    """한 해치 보고 — 달마다 한 줄.

    "올해 몇 건이나 했나" 를 보려고 열두 달을 하나씩 눌러 보고 있었다.
    각 달의 요약을 그대로 쓰므로 숫자가 월간 보고와 어긋나지 않는다.

    **발송도 함께 센다.** 월간에만 두면 연말에 열두 달을 열어 손으로 더하게
    되는데, 그게 바로 이 보고가 없애려는 일이다.
    """
    today = today or date.today()
    months, totals = [], {"total": 0, "done": 0, "followup_done": 0,
                          "followup_open": 0, "followup_late": 0,
                          "ir_requested": 0, "ir_delivered": 0, "ir_open": 0,
                          "send_rounds": 0, "send_sent": 0, "send_left": 0}
    for mon in range(1, 13):
        got = monthly(db, year, mon, user, today)
        months.append({
            "month": mon,
            "label": f"{mon}월",
            **{k: got[k] for k in totals},
        })
        for k in totals:
            totals[k] += got[k]

    outcome_counts: Dict[str, int] = {}
    for mon in range(1, 13):
        for label, n in monthly(db, year, mon, user, today)["outcomes"]:
            outcome_counts[label] = outcome_counts.get(label, 0) + n

    return {
        "year": year,
        "months": months,
        "totals": totals,
        "outcomes": sorted(outcome_counts.items(), key=lambda t: -t[1]),
    }


def selectable_years(today: Optional[date] = None, back: int = 3) -> List[int]:
    """고를 수 있는 해. 앞으로도 한 해 열어 둔다 — 12월에 내년 일정을 잡는다."""
    today = today or date.today()
    return list(range(today.year - back, today.year + 2))
