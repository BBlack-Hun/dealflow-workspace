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
from datetime import date, timedelta
from typing import Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (DealBatch, DealBatchCompany, IrCompany, IrRequest,
                      Meeting, SendItem, SendJob, SendSequence, User, VcContact)
# 후속 단계(`STAGE_CALL`)와 그 주기는 **캐던스가 정한 것**을 읽는다 — 보고가
# 제 손으로 "미팅 요청 사흘 뒤" 를 세면, 주기를 바꾼 날 화면과 보고가 다른
# 날짜를 말한다.
from . import cadence
from . import manual_send
# 단계 값(`STAGE_*`)은 **문구를 짓는 쪽이 정한 것**을 그대로 읽는다.
# 여기 숫자를 다시 적어 두면 한쪽이 바뀔 때 보고만 옛 값으로 남는다
# (`routers/deals.py` 도 같은 곳을 `mc` 로 읽는다).
from . import message_composer as mc
from .pipeline import (IR_MEETING_ASK_DAYS, MEETING_FOLLOWUP_DAYS,
                       MEETING_KINDS, NO_FOLLOWUP_OUTCOMES, OUTCOMES,
                       REQUEST_STATUS, meeting_ask_state)
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
SEND_REPORT_KINDS = ("deal_intro", "sourcing_intro")

#: 묶음 열쇠. `SendJob.kind` 값이 아니다 — `deal_intro` 하나에 네 가지 일이
#: 들어 있어서(아래 `send_group_key`) 열쇠를 따로 둔다.
GROUP_DEAL = "deal_intro"
GROUP_REMIND = "deal_intro_remind"
GROUP_MEETING = "deal_intro_meeting"
GROUP_SOURCING = "sourcing_intro"

#: 발송 묶음 — `(열쇠, 이름, 늘 보이는가)`. 이 차례가 화면·엑셀에 그대로 나온다.
#:
#: ## 왜 `딜 소개` 를 쪼개는가
#:
#: `SendJob.kind` 는 **IR 전달·소싱·스타트업만** 갈라 적는다. 그래서 미팅
#: 요청·리마인드·선호 분야 묻기·미팅 후기가 전부 `deal_intro` 로 들어가,
#: `딜 소개` 묶음의 `회차 N개 · 대상 N명` 에 함께 세어졌다. 회차명으로 눈으로는
#: 갈라 보이지만 숫자는 뭉쳐 있어서, 카톡으로 보고하던 `딜소개 업무 총 N명` 이
#: 실제 딜 소개보다 부풀었다.
#:
#: **`kind` 를 새로 쪼개지 않는다.** 옛 회차는 이미 `deal_intro` 로 적혀 있어서
#: 새 값을 만들면 지난달이 옛 값 그대로 남는다. 대신 `SendItem.stage` 로 읽는다
#: — 회차 하나가 곧 방식 하나라(`deals.create_send_list` 가 회차마다 한 가지
#: `stage` 만 적는다) 이주 없이 옛 회차까지 그대로 갈린다.
#:
#: ## 이름은 회차명이 쓰는 말과 같다
#:
#: `deals.MODE_TITLES` 의 말을 그대로 쓴다 — 회차명은 `미팅 요청` 인데 묶음이
#: `미팅 요청 발송` 이면 같은 것이 둘로 읽힌다. 두 방식이 한 묶음인 자리는
#: **두 이름을 다 적는다**(아래 `send_group_key` 의 '아는 흠').
#:
#: ## 늘 보이는 묶음
#:
#: `딜 소개`·`딜 소싱` 은 회차가 없는 달에도 자리를 지킨다 — 사용자가 카톡
#: 보고에 늘 두 줄을 적었고, 빈 칸이 보여야 "이 달은 안 했다" 를 읽는다.
#: 후속 묶음은 있을 때만 선다. 늘 세워 두면 대부분의 달에 `이 달에는 없습니다`
#: 가 넷씩 깔려 정작 회차가 있는 줄이 묻힌다. **거르는 자리는 여기 한 곳이라
#: 화면과 엑셀이 같은 묶음을 본다.**
SEND_GROUPS = (
    (GROUP_DEAL, "딜 소개", True),
    (GROUP_REMIND, "리마인드 · 선호 분야 묻기", False),
    (GROUP_MEETING, "미팅 요청 · 미팅 후기", False),
    (GROUP_SOURCING, "딜 소싱", True),
)


def send_group_key(kind: str, stage: Optional[int]) -> str:
    """이 회차는 어느 묶음인가. ★ **가르는 판정은 여기 하나다.**

    화면(`templates/report.html`)·엑셀(`routers/data_io.py`)·연간 보고가 전부
    `_sends()` 가 만든 묶음을 그대로 읽는다. 각자 세면 같은 달이 화면마다 다른
    수로 보인다 — 이 저장소가 반복해 겪은 사고다.

    `stage` 는 그 회차 발송 건의 단계다(`services/message_composer.STAGE_*`).

        1 딜 소개   2 리마인드·선호 분야 묻기   3 미팅 요청·미팅 후기

    비어 있으면 딜 소개로 읽는다 — `stage` 칸이 생기기 전의 옛 건이고,
    `cadence.progress` 도 같은 자리에서 같은 값으로 읽는다.

    ## 아는 흠 — 두 방식이 한 `stage` 를 함께 쓴다

    `2` 는 리마인드와 선호 분야 묻기가, `3` 은 미팅 요청과 미팅 후기가 함께
    쓴다(`deals.FOLLOW_UP_MODES`). **가를 수 있는 값이 어디에도 없다** —
    발송 건에 남는 것은 `stage` 뿐이고 문구 종류는 저장되지 않는다. 억지로
    회차명으로 가르지 않는다: 회차명은 사람이 고쳐 쓸 수 있어서, 이름을 바꾼
    회차가 소리 없이 다른 묶음으로 옮겨 간다.

    그래서 **한 묶음으로 두고 이름에 둘 다 적는다.** 갈라 놓은 척하는 것보다
    낫다 — 숫자가 무엇을 세었는지가 이름에 그대로 적혀 있다.
    """
    if kind != "deal_intro":
        return kind
    if stage == mc.STAGE_REMIND:
        return GROUP_REMIND
    if stage == mc.STAGE_MEETING:
        return GROUP_MEETING
    return GROUP_DEAL

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
    # **차례를 정해 둔다.** 예전에는 여기에 차례가 없어 데이터베이스가 주는
    # 순서대로 나왔고, `기업명 순`으로 다시 늘어놓은 갈래가 하나 더 있어서
    # 기업으로 훑을 때는 그쪽을 봤다. 그 갈래를 지웠으니 이 목록이 유일한
    # 자리다 — 미팅 갈래와 같이 날짜 순으로 세우고, 같은 날은 기업명으로
    # 묶는다. 한 기업에 대한 요청이 그날 안에서 흩어지지 않는다.
    requests = db.execute(
        ir_stmt.order_by(IrRequest.requested_at, IrRequest.company_name)
    ).scalars().all()

    # 미팅 요청을 보내 놓고 답이 없어 **전화로 다시 청할** 곳. 딜 진행 관리의
    # `전화 요청` 구역과 같은 줄을 본다(`cadence.STAGE_CALL`) — 두 화면이 각자
    # 세면 한쪽에만 뜨는 사람이 생긴다.
    calls = _call_rows(db, start, end, user)

    # 담당자는 **미팅·요청·전화 세 곳**에서 모은다. 미팅 것만 불러오면 다른
    # 줄의 이름이 `-` 로 비어, 보고를 그대로 옮겨 적을 수가 없다.
    need = ({m.contact_id for m in meetings} | {r.contact_id for r in requests}
            | {c.contact_id for c in calls})
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

    # 자료를 전달한 담당자마다 **미팅 요청까지 갔는가**. `today` 를 넘겨
    # 준다 — 실제 시계를 읽으면 특정 날에만 다른 수가 나온다.
    #
    # ── 달이 걸치는 경우 ──────────────────────────────────────────────
    #
    # 8월에 받아 8월에 전달한 요청인데 미팅 요청은 9월에 나갔다면, **8월
    # 보고에 `미팅 요청 보냄 · 2026-09-03` 으로 뜬다.** 달을 자르지 않는다.
    #
    #   · 이 줄은 기록이 아니라 **아직 남은 일**이다. 이미 보낸 건이 지난달
    #     보고에서 영영 "안 보냄" 으로 남아 있으면, 그건 거짓 경보이고
    #     거짓으로 뜨는 숫자는 곧 아무도 안 본다(#162 가 적어 둔 이유와 같다).
    #   · 숫자(`ir_meeting_ask_missing`)가 이미 그렇게 센다. 줄만 달을 잘라
    #     보이면 **같은 화면 안에서 숫자와 목록이 갈린다** — 이 저장소가 반복해
    #     겪은 사고다.
    #   · 판정 자리(`pipeline.meeting_ask_state`)는 **마지막 전달일**에 맞춘다.
    #     그래서 9월에 자료를 또 보냈으면 9월치로 다시 세어지고, 8월 보고의
    #     그 줄도 새 전달일 기준으로 말한다 — 묻히는 건이 없다.
    #
    # 대신 이 판은 **지난달을 다시 열면 그때와 숫자가 다를 수 있다.** 그 달에
    # 무엇을 받았는지(`요청받음`·`전달함`)는 안 변하고, 변하는 것은 "그래서
    # 지금 남은 일" 쪽이다.
    ask = meeting_ask_state(db, requests, today=today)

    # 판에 함께 밝힐 **요청 건수** — 안 보낸 그 담당자들이 받은 요청 줄 수다.
    # 세는 곳은 `meeting_ask_state` 하나이고 여기서는 더하기만 한다. 글자는
    # `meeting_ask_count_note` 가 짓고 화면과 엑셀이 그걸 그대로 쓴다.
    ask_missing = sum(1 for st in ask.values() if not st["asked"])
    ask_rows = sum(st["requests"] for st in ask.values() if not st["asked"])
    ask_count, ask_why = meeting_ask_count_note(ask_missing, ask_rows)

    return {
        "year": year,
        "month": month,
        # 한 달에 두 번(첫째·셋째 수요일) 도는 일이라, 그 달에 무엇이 오갔는지를
        # **한눈에** 봐야 한다. 네 갈래를 날짜와 함께 그대로 늘어놓는다.
        # `ask` 를 넘겨 준다 — `IR 요청 투자사` 갈래의 상태 칸이 **누가**
        # 미팅 요청을 안 보냈는지 말한다. 갈래가 다시 세지 않고 위에서 이미
        # 한 판정을 받아 쓴다(두 곳에서 세면 숫자가 갈린다).
        "buckets": _buckets(meetings, requests, contacts, owners, today,
                            open_followup, ask, calls),
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
        # **자료를 보내 놓고 아무 말도 안 한 건.** 전달하면 리마인드가 멈춰서
        # (답이 왔으니 맞다) 미팅 요청을 안 보낸 담당자는 어느 목록에도 다시
        # 안 뜬다 — 이 보고가 잡아내야 할 것이 그것이다.
        #
        # **담당자 수다(줄 수가 아니다).** 미팅 요청 카톡은 담당자당 한 통이라
        # (`deals.MODES_WITH_COMPANIES` 에 미팅이 없다) 줄로 세면 한 번 보낼
        # 일이 세 건으로 보인다. 판정은 `pipeline.meeting_ask_state` 한 곳이
        # 하고 IR 화면도 같은 곳을 읽는다 — 두 화면이 다른 수를 말하면 안 된다.
        "ir_meeting_ask_missing": ask_missing,
        "ir_meeting_ask_overdue": sum(1 for st in ask.values() if st["overdue"]),
        # **같은 수를 두 단위로.** 위 숫자는 담당자 수고 이건 그 담당자들이
        # 받은 요청 줄 수다 — 아래 `IR 요청 투자사` 표가 그 줄 수만큼 선다.
        # 둘이 같으면 `_note`·`_why` 가 빈 글자라 화면에 아무 말도 안 붙는다.
        "ir_meeting_ask_rows": ask_rows,
        "ir_meeting_ask_rows_note": ask_count,
        "ir_meeting_ask_rows_why": ask_why,
        # 화면 안내문이 "7일" 이라고 말할 때 쓰는 값 — 코드와 화면이 다른
        # 숫자를 말하면 안 된다(`followup_days` 와 같은 방식).
        "ir_meeting_ask_days": IR_MEETING_ASK_DAYS,
        # **미팅 요청 후 전화** — 아직 안 건 곳 · 그중 날짜가 지난 곳 · 건 곳.
        # 줄은 위 `meeting_call` 갈래가 이름과 함께 보여 주고, 여기서는 수만
        # 낸다. **다시 세지 않는다** — 갈래와 같은 `calls` 한 벌을 본다.
        "call_open": sum(1 for c in calls
                         if c.next_stage == cadence.STAGE_CALL),
        "call_overdue": sum(
            1 for c in calls
            if c.next_stage == cadence.STAGE_CALL and c.next_due_date
            and c.next_due_date <= today.isoformat()),
        "call_done": sum(1 for c in calls
                         if c.next_stage != cadence.STAGE_CALL),
        # 화면 안내문이 "사흘 뒤" 라고 말할 때 쓰는 값. 규칙은 DB 에 있고
        # (`schedule_rules` 의 `call`) 관리자가 늘릴 수 있다 — 화면이 숫자를
        # 박아 두면 늘린 날 화면만 옛말을 한다.
        "call_days": cadence.get_rule(db, "call").get("offset_min_days"),
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


#: 손으로 적은 회차 줄의 상태 글자. 앱 발송의 `SEND_STATUS` 와 **같은 자리에**
#: 서는 값이라 말이 겹치면 안 된다 — `완료` 라고 적으면 발송기가 돌려준 결과로
#: 읽힌다. 이 줄은 사람이 "보냈다" 고 적어 준 것이 근거의 전부다.
MANUAL_STATUS = "손으로 보냄"


def _manual_rounds(db: Session, start: date, end: date, user: Optional[User],
                   owners: Dict[int, str]) -> Dict[str, List[dict]]:
    """손으로 보냈다고 적은 것을 **회차 줄 모양**으로. `{묶음 열쇠: [줄…]}`.

    ## 왜 판마다 한 줄인가

    한 번에 80명을 적는다(`services/manual_send.py`). 그 80줄이 표에 80줄로
    서면 보고가 아니라 명부가 된다. 사람이 카톡 보고에 적던 단위도 회차다 —
    `딜소개 업무(핵심 딜 7개사) / 총 126명`. 그래서 **한 판 = 한 줄**이고,
    그 판의 표시(`ContactActivity.batch_key`)가 곧 회차 번호 노릇을 한다.

    ## 안 나간 건이 없다

    `대상 = 완료` 다. 앱 발송은 대상에 올려 두고 실제로 안 나간 건이 생기는데
    (중단·실패·대기), 손으로 적는 것은 **이미 보낸 것을 적는 일**이라 그 틈이
    없다. `left` 를 0 으로 두는 것은 값이 없어서가 아니라 그것이 답이어서다.

    ## 회차 화면이 없다

    `job_id` 가 0 이다 — 볼 회차가 없다(`/jobs/0` 은 없는 자리다). 화면은 그
    칸을 비운다. 무엇을 보냈는지는 담당자 이력 타임라인에 줄마다 남아 있다.
    """
    rows = manual_send.counted(
        db, send_kinds=SEND_REPORT_KINDS,
        since=start.isoformat(), until=end.isoformat(),
        user_id=user.id if user is not None else None)

    # 판 + 주인 단위로 모은다. 관리자가 남의 줄까지 한 판에 적을 수 있는데,
    # 그때 `팀원` 칸이 한 사람만 가리키면 거짓말이 된다.
    packs: Dict[tuple, dict] = {}
    for row in rows:
        key = send_group_key(row["send_kind"], row["stage"])
        pack_id = (key, row["batch_key"] or f"day:{row['day']}", row["user_id"])
        got = packs.get(pack_id)
        if got is None:
            got = packs[pack_id] = {
                "group": key, "day": row["day"], "user_id": row["user_id"],
                "kind": row["kind"], "people": set(), "companies": set(),
                "count": row["company_count"] or 0,
            }
        got["people"].add(("c", row["contact_id"]))
        got["companies"].update(row["companies"])
        # 이름 없이 **개수만** 적은 판(`핵심 딜 8개사`)이 실제로 있다.
        # 그때는 셀 이름이 없으므로 적어 준 개수를 그대로 쓴다.
        got["count"] = max(got["count"], row["company_count"] or 0)

    out: Dict[str, List[dict]] = {}
    for (key, _pack, _uid), got in sorted(packs.items()):
        n = len(got["people"])
        names = sorted(got["companies"])
        when = got["day"] or ""
        label = manual_send.KIND_LABELS.get(got["kind"], got["kind"])
        out.setdefault(key, []).append({
            "row": {
                # 볼 회차가 없다 — 화면이 이 값으로 [보기] 칸을 비운다.
                "job_id": 0,
                # **손으로 적은 줄임이 이름에 그대로 적힌다.** 합쳐 센 수를
                # 되짚는 자리가 여기다(대시보드는 부제에서 밝힌다).
                "title": f"{manual_send.BY_HAND} · {label}",
                "manual": True,
                "date": when,
                "day": day_label(when),
                "companies": len(names) or got["count"],
                "company_names": names,
                "target": n,
                "sent": n,
                "failed": 0,
                "canceled": 0,
                "waiting": 0,
                "left": 0,
                "left_label": "",
                "status": "manual",
                "status_label": MANUAL_STATUS,
                "owner": owners.get(got["user_id"], ""),
                "level": "",
            },
            "people": got["people"],
            "companies": set(names),
        })
    return out


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

    **후속 발송은 딜 소개와 갈라 센다.** 미팅 요청·리마인드·선호 분야 묻기·
    미팅 후기가 전부 `SendJob.kind == "deal_intro"` 로 적히는 탓에 위 보고의
    `총 N명` 에 함께 들어 있었다 — 어느 묶음인지는 `send_group_key` 한 곳이
    정하고, 화면·엑셀·연간 보고가 그 답을 그대로 읽는다.

    **손으로 보낸 것도 여기서 함께 센다.** 프로그램으로 안 보내고 카톡에서
    손으로 보내는 사람이 있어서, 그 사람의 `딜 소개 총 N명` 이 늘 비어 있었다.
    합치는 판정은 `manual_send.counted` 한 곳이고(대시보드 두 곳도 같은 함수를
    읽는다), 어느 묶음으로 설지는 여기서도 `send_group_key` 가 정한다 —
    판정을 두 벌로 두지 않으려고 수동 기록을 **앱 발송의 말**(`SendJob.kind` ·
    `SendItem.stage`)로 옮겨 받는다.

    합쳐도 **되짚을 수 있다** — 수동 기록은 회차 줄로 따로 서고 그 줄에
    `손으로 보냄` 이 적힌다. 숫자를 가르지 않는 이유는 보고에 옮겨 적는 수가
    어차피 합계이기 때문이다(가르면 사람이 두 수를 더해야 한다).
    """
    stmt = (select(SendJob, DealBatch)
            .outerjoin(DealBatch, DealBatch.id == SendJob.batch_id)
            .where(SendJob.kind.in_(SEND_REPORT_KINDS)))
    if user is not None:
        stmt = stmt.where(SendJob.user_id == user.id)

    lo, hi = start.isoformat(), end.isoformat()
    jobs = [(job, batch) for job, batch in db.execute(stmt).all()
            if lo <= _job_date(job, batch) <= hi]

    job_ids = [job.id for job, _ in jobs]
    counts: Dict[int, Counter] = {}
    people: Dict[int, set] = {}
    stages: Dict[int, Counter] = {}
    for item_id, job_id, status, contact_id, sourcing_id, stage in db.execute(
        select(SendItem.id, SendItem.job_id, SendItem.status,
               SendItem.contact_id, SendItem.sourcing_contact_id,
               SendItem.stage)
        .where(SendItem.job_id.in_(job_ids or [0]))
    ).all():
        counts.setdefault(job_id, Counter())[status or ""] += 1
        # 받는 사람은 투자사 담당자이거나 소싱 명단이거나 — 서로 다른 표라
        # 어느 쪽인지까지 키에 담아야 번호가 겹치는 두 사람이 한 명이 되지 않는다.
        who = (("c", contact_id) if contact_id
               else ("s", sourcing_id) if sourcing_id else ("i", item_id))
        people.setdefault(job_id, set()).add(who)
        # 이 회차가 어떤 방식이었나 — 발송 건에 남은 유일한 자국이다.
        stages.setdefault(job_id, Counter())[stage] += 1

    # ── 회차 하나 = 방식 하나 ────────────────────────────────────────────
    #
    # `deals.create_send_list` 는 회차마다 한 가지 `stage` 만 적는다. 그래도
    # **섞였을 때 무엇을 할지는 정해 둔다** — 손으로 고친 자료나 옛 이주가
    # 남긴 줄이 있으면, 정해 두지 않은 쪽은 데이터베이스가 주는 순서대로
    # 갈려서 같은 달을 두 번 열면 다른 묶음에 선다. 가장 많은 쪽으로 읽고,
    # 같은 수면 앞 단계로 읽는다(비어 있는 것이 딜 소개다).
    def _stage_of(job_id: int) -> Optional[int]:
        got = stages.get(job_id)
        if not got:
            return None
        return min(got.items(), key=lambda t: (-t[1], t[0] or 0))[0]

    # **가르는 판정은 `send_group_key` 한 곳**이고, 여기서 회차마다 한 번만
    # 부른다 — 아래 묶음 고르기가 같은 답을 다시 계산하지 않는다.
    belongs = {job.id: send_group_key(job.kind, _stage_of(job.id))
               for job, _ in jobs}

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

    # 손으로 보낸 것 — 회차가 없으므로 **판(`batch_key`)마다 한 줄**로 세운다.
    manual_rounds = _manual_rounds(db, start, end, user, owners)

    groups = []
    for key, label, always in SEND_GROUPS:
        # **회차마다 한 줄.** 같은 날 회차가 둘이어도 합치지 않는다 — 8/27 에
        # 두 회차가 있었고 하나는 18건에서 멈췄는데, 합치면 그 사실이 묻혀
        # `116개 완료` 가 된다. 손으로 쓰던 보고가 실제로 그렇게 틀렸다.
        picked = sorted((t for t in jobs if belongs[t[0].id] == key),
                        key=lambda t: (_job_date(*t), t[0].id))
        # 없는 후속 묶음은 아예 세우지 않는다 — 거르는 자리가 여기 하나라
        # 화면과 엑셀이 같은 묶음을 본다(까닭은 `SEND_GROUPS`).
        if not picked and not always:
            continue
        rows, targeted, companies = [], set(), set()
        for got in manual_rounds.get(key, []):
            rows.append(got["row"])
            targeted |= got["people"]
            companies.update(got["companies"])
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
        # 손으로 적은 줄과 앱이 보낸 줄을 **날짜 순으로 섞는다.** 출처별로
        # 뭉쳐 두면 같은 주에 있었던 일이 표 위아래로 갈려서 읽을 수가 없다
        # (담당자 이력 타임라인이 같은 이유로 섞는다).
        rows.sort(key=lambda r: (r["date"] or "", r["job_id"], r["title"]))
        groups.append({
            "key": key,
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


def _call_rows(db: Session, start: date, end: date,
               user: Optional[User]) -> List[SendSequence]:
    """그 달의 **전화 요청** 줄 — 걸어야 할 곳과 이미 건 곳.

    미팅 요청 카톡을 보내고 사흘 뒤 전화로 다시 청하는 단계다
    (`services/cadence.STAGE_CALL`). 딜 진행 관리에만 두면 업무 보고를 보며
    일하는 사람에게는 이 일이 아예 안 보인다 — 사용자가 두 곳을 다 든 까닭이다.

    **달을 가르는 기준이 둘이다.** 아직 안 건 것은 `걸 날`(`next_due_date`)로,
    이미 건 것은 `건 날`(`last_sent_at`)로 그 달에 든다. 둘 다 "그 달에 이
    일이 있었나" 를 말하는 날짜이고, 한 줄이 두 기준에 함께 걸릴 일은 없다 —
    건 순간 `next_due_date` 가 비기 때문이다(`cadence.advance`).

    **여기서 세지 않는다.** 단계도 예정일도 `cadence` 가 정한 것을 읽기만
    한다 — 보고가 제 손으로 "사흘 뒤" 를 세면 주기를 바꾼 날 화면과 보고가
    다른 날짜를 말한다.

    위 `이 달의 반응` 의 `IR 미팅완료 리마인드 TEL 투자사` 와 **다른 전화다.**
    그쪽은 미팅이 끝나고 열흘 뒤 결과를 묻는 것이고, 이쪽은 미팅을 청해 놓고
    답이 없을 때 거는 것이다. 이름이 그 둘을 갈라야 한다.
    """
    lo, hi = start.isoformat(), end.isoformat()
    waiting = select(SendSequence).where(
        SendSequence.status == "active",
        SendSequence.next_stage == cadence.STAGE_CALL,
        SendSequence.next_due_date.isnot(None),
        SendSequence.next_due_date >= lo, SendSequence.next_due_date <= hi)
    # 건 날은 시각까지 적혀 있다(`2026-09-17T14:02:…`) — 그 달 마지막 날의
    # 오후가 잘려 나가지 않게 끝을 하루 밀어 잡는다.
    called = select(SendSequence).where(
        SendSequence.stage == cadence.STAGE_CALL,
        SendSequence.last_sent_at.isnot(None),
        SendSequence.last_sent_at >= lo,
        SendSequence.last_sent_at < (end + timedelta(days=1)).isoformat())
    if user is not None:
        waiting = waiting.where(SendSequence.user_id == user.id)
        called = called.where(SendSequence.user_id == user.id)

    rows = {r.id: r for r in db.execute(waiting).scalars().all()}
    rows.update({r.id: r for r in db.execute(called).scalars().all()})
    return sorted(rows.values(),
                  key=lambda r: (r.next_due_date or (r.last_sent_at or "")[:10],
                                 r.id))


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


def meeting_ask_note(state: Optional[dict]) -> tuple:
    """자료를 받은 담당자에게 **미팅 요청까지 갔는가** — 한 줄 글과 색.

    ★ 이 글자를 짓는 곳은 여기 하나다. 업무 보고 화면(`report.html`)과 엑셀
    보고(`routers/data_io._buckets_sheet`)가 **같은 문자열**을 받아 쓴다 —
    양쪽이 각자 지으면 화면에는 재촉하는 말이 떠 있는데 파일에는 아무 말도
    없는 일이 생기고, 그때 사람은 어느 쪽을 믿을지 알 수 없다.

    **세지는 않는다.** 판정은 `pipeline.meeting_ask_state` 한 곳이 하고
    여기서는 그 답을 사람 말로 옮기기만 한다.

    돌려주는 것은 `(글, 빛깔)`. 빛깔은 `ok`(보냄) · `bad`(지남) ·
    `warn`(아직 안 보냈지만 기한은 남음) 셋이다. 안 보낸 것을 전부 빨강으로
    두면 오늘 할 일과 아직 여유 있는 것이 구별되지 않는다.
    """
    if not state:
        return "", ""
    if state["asked"]:
        return f"미팅 요청 보냄 · {state['asked_at']}", "ok"
    if state["overdue"]:
        return f"미팅 요청 안 보냄 · {IR_MEETING_ASK_DAYS}일 지남", "bad"
    return f"미팅 요청 안 보냄 · {state['due']}까지", "warn"


def meeting_ask_count_note(missing: int, requests: int) -> tuple:
    """`미팅 요청 안 보냄 N명` 옆에 **요청이 몇 건인지**를 같이 밝힌다.

    ★ 이 글자를 짓는 곳도 여기 하나다(`meeting_ask_note` 와 같은 결). 업무
    보고 화면(`report.html`)과 엑셀 보고(`routers/data_io._meetings_sheet`)가
    **같은 문자열**을 받아 쓴다 — 양쪽이 각자 지으면 화면과 파일이 다른 말로
    설명하게 되고, 그때 사람은 어느 쪽을 믿을지 알 수 없다.

    ## 무엇이 안 맞아 보였는가

    사용자가 본 화면이 이랬다.

        미팅 요청 안 보냄   4명        ← 판
        IR 요청 투자사      5줄        ← 표

    **둘 다 맞는 수인데 세는 단위가 다르다.** 미팅 요청 카톡은 담당자에게
    한 통만 나가서(`deals.MODES_WITH_COMPANIES` 에 미팅이 없다) 한 투자사가
    기업 두 곳 자료를 받아도 "미팅 가능하실지요" 는 한 번이다. 그래서 판은
    담당자로 세고, 표는 어느 기업 자료였는지를 보여야 하니 요청 줄마다 선다.
    화면이 그걸 말해 주지 않아서 **안 맞아 보였다.**

    숫자는 안 바꾼다 — 바꾸면 둘 중 하나가 틀린 수가 된다. 대신 판이 건수를
    같이 밝혀 두 단위가 화면 안에서 만나게 한다.

    ## 왜 **세지는 않는가**

    건수는 `pipeline.meeting_ask_state` 가 이미 센 값(`requests`)을 받아
    쓴다. 여기서 다시 세면 판과 표의 수가 또 갈린다 — 이 저장소가 반복해
    겪은 사고다.

    ## 같을 때는 **아무 말도 안 한다**

    `4명 (요청 4건)` 은 아무것도 설명하지 않는다. 단위가 다르다는 것은 두
    수가 **다를 때만** 드러나므로, 같으면 빈 글자를 돌려주어 괄호가 아예 안
    붙는다. 늘 켜져 있는 군더더기는 곧 아무도 안 읽는다.

    돌려주는 것은 `(짧은 글, 까닭)`. 짧은 글은 판의 숫자 옆에, 까닭은 그
    아래 안내문에 선다. 할 말이 없으면 둘 다 빈 글자다.
    """
    if missing <= 0 or requests <= missing:
        return "", ""
    return (
        f"요청 {requests}건",
        f"미팅 요청 카톡은 담당자당 한 통이라 이 수는 담당자 {missing}명입니다"
        f" — 그 {missing}명이 받은 자료 요청은 {requests}건이고,"
        f" IR 요청 투자사 표는 요청 줄마다 한 줄이라 수가 더 많습니다.",
    )


def _buckets(meetings, requests, contacts, owners, today, open_followup,
             ask: Dict[int, dict], calls: List[SendSequence]) -> List[dict]:
    """반응 갈래를 **그 달치로, 날짜와 함께**.

    숫자만 보면 "그게 누구였지" 가 이어진다. 보고에서는 이름과 날짜가
    나란히 있어야 그대로 옮겨 적을 수 있다.

    **`IR 요청받은 기업` 갈래는 없다.** 그건 `IR 요청 투자사` 와 같은 목록을
    기업명 순으로 다시 늘어놓은 것뿐이라, 줄 수도 내용도 같은 표가 한 화면에
    두 번 서 있었다 — 사용자가 "내용이 겹친다" 고 말한 자리다. 한 요청에
    투자사와 기업이 함께 적히므로(표의 `투자사`·`기업` 칸) 한 표로 족하다.
    """
    def who(contact_id):
        c = contacts.get(contact_id)
        if c is None:
            return {"name": "-", "title": "", "firm": ""}
        return {"name": c.name, "title": c.title or "", "firm": c.firm or ""}

    def row(when, contact_id, company, note, user_id):
        # `ask`·`ask_state` 는 IR 갈래만 채운다. 그래도 **모든 줄에 둔다** —
        # 화면과 엑셀이 갈래를 가리지 않고 같은 고리를 도는데, 한 갈래에만
        # 있으면 파일 쪽이 `KeyError` 로 통째로 안 받아진다.
        return {"date": when or "", **who(contact_id), "company": company or "",
                "note": note or "", "owner": owners.get(user_id, ""),
                "ask": "", "ask_state": ""}

    # ── IR 요청 — **누가 미팅 요청을 안 보냈는지 여기서 보인다** ──────────
    #
    # 업무 보고에는 `미팅 요청 안 보냄 N명` 이라는 숫자만 있었다. 사용자는
    # 업무 보고를 보며 일을 하는데, 그 화면에서는 **누구인지**를 알 수 없어
    # 딜 진행 관리로 건너가 다시 찾아야 했다.
    #
    # 새 표를 만들지 않는다 — 이 갈래에 날짜·담당자·투자사·기업·상태가 이미
    # 다 있다. 상태 칸에 한 줄을 얹는 것으로 족하다.
    #
    # **줄이 아니라 담당자의 상태다.** 한 담당자가 기업 셋 자료를 받았으면
    # 세 줄에 같은 표시가 붙는다(나가는 카톡은 한 통이라 숫자는 1이다) —
    # `/ir` 의 `전달한 자료` 표와 같은 방식이라 두 화면이 같아 보인다.
    #
    # **`전달함` 인 줄에만 붙인다.** 아직 안 보낸 요청 줄에까지 붙으면
    # "자료도 안 줬는데 미팅 요청 안 보냄" 이라는 앞뒤 없는 말이 된다.
    ir = []
    for r in requests:
        one = row(r.requested_at, r.contact_id, r.company_name,
                  REQUEST_STATUS.get(r.status, r.status), r.user_id)
        if r.status == "delivered":
            one["ask"], one["ask_state"] = meeting_ask_note(ask.get(r.contact_id))
        ir.append(one)

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
        # ── 미팅 요청을 보내 놓고 답이 없어 **전화로 다시 청하는** 곳 ────────
        #
        # 위 `IR 미팅완료 리마인드 TEL 투자사` 와 **다른 전화다.** 그쪽은 미팅이
        # 끝나고 열흘 뒤 결과를 묻는 것이고, 이쪽은 미팅을 청해 놓고 사흘이
        # 지나도록 답이 없을 때 거는 것이다. 한 화면에 나란히 서므로 이름이
        # 그 둘을 갈라야 한다 — 앞에 무엇을 하고 거는 전화인지를 적는다.
        #
        # **기업 칸은 비운다.** 미팅 요청 카톡은 담당자당 한 통이고 딸 기업이
        # 없다(`deals.MODES_WITH_COMPANIES` 에 미팅이 없다) — 지어 넣으면
        # 읽는 사람은 그것을 "그 기업 건" 으로 읽는다.
        {"key": "meeting_call", "label": "미팅 요청 후 전화 투자사",
         "rows": [row(seq.next_due_date or (seq.last_sent_at or "")[:10],
                      seq.contact_id, "",
                      (f"전화함 · {(seq.last_sent_at or '')[:10]}"
                       if seq.next_stage != cadence.STAGE_CALL
                       else _call_state(seq.next_due_date, today)),
                      seq.user_id)
                  for seq in calls]},
    ]


def parse_month(month: str, today: Optional[date] = None) -> tuple:
    """`2026-08` → (2026, 8). 못 읽으면 이 달.

    화면(`/report`)과 **엑셀 내려받기가 같은 주소를 읽어야** 한다. 두 곳에서
    따로 해석하면 `?month=2026-8` 같은 값에서 갈리고, 그러면 화면과 엑셀이
    다른 달을 보여 준다 — 보고에서 가장 비싼 실수다.
    """
    today = today or date.today()
    year, mon = today.year, today.month
    if month:
        try:
            year, mon = (int(x) for x in month.split("-")[:2])
        except (ValueError, TypeError):
            pass
    return year, mon


def parse_year(year: str, today: Optional[date] = None) -> int:
    """`"2026"` → 2026. 못 읽으면 올해.

    `parse_month` 와 같은 까닭이다 — 연간 보고도 화면(`/report?span=year&year=…`)과
    **엑셀 내려받기가 같은 주소를 읽어야** 한다. 두 곳에서 따로 해석하면
    `?year=26` 같은 값에서 갈리고, 그러면 화면과 엑셀이 다른 해를 보여 준다.
    """
    today = today or date.today()
    if year:
        try:
            return int(year)
        except (ValueError, TypeError):
            pass
    return today.year


def scope_for(db: Session, user: User, scope: str = "", member: int = 0) -> tuple:
    """이 보고를 **누구 것으로** 볼 것인가 → `(who, team_wide, viewing)`.

    `who` 는 `monthly()`/`yearly()` 에 넘길 값이다(팀 전체면 None).
    `viewing` 은 "누구 것을 보고 있나" 를 화면·파일이름에 적을 때 쓴다.

    규칙은 하나뿐이어야 한다 — 관리자만 팀 전체·팀원 지정을 볼 수 있고,
    팀원을 고르면 그 사람 것 하나만 본다. 화면과 엑셀이 각자 판정하면 범위가
    갈려서, 같은 주소인데 화면은 내 것 · 엑셀은 팀 전체가 나오는 일이 생긴다.
    """
    team_wide = user.role == "admin" and scope == "team"
    target = user
    if user.role == "admin" and member:
        picked = db.get(User, member)
        if picked is not None:
            target, team_wide = picked, False
    return (None if team_wide else target), team_wide, (None if team_wide else target)


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


#: 연간 리포트가 **항목마다 한 줄**로 적는 것 — (열쇠, 이름, 빛깔).
#:
#: ★ **화면과 엑셀이 이 한 줄을 같이 읽는다.** 두 곳에 각자 늘어놓으면 항목이
#: 하나 늘 때 한쪽만 늘고, 그때 두 문서의 숫자가 갈린다 — 이 저장소가
#: 되풀이해 겪은 탈이다.
#:
#: 차례는 **일이 일어나는 차례**다(회차 → 반응 → 미팅 → 전화). 월간 보고의
#: 판 차례와 같아서, 한 해와 한 달을 나란히 놓고 볼 수 있다.
#:
#: 빛깔은 `bad`(안 나간 것·지난 것) · `warn`(아직 안 한 것) 둘뿐이다 —
#: 화면과 엑셀이 같은 값을 받아 제 방식으로 그린다.
YEARLY_ITEMS = (
    ("send", "send_rounds", "발송 회차", ""),
    ("send", "send_sent", "보낸 건수", ""),
    ("send", "send_left", "안 나감", "bad"),
    ("meeting", "total", "잡은 미팅", ""),
    ("meeting", "done", "진행한 미팅", ""),
    ("meeting", "followup_done", "결과 물어봄", ""),
    ("meeting", "followup_open", "아직 안 물어봄", "warn"),
    ("meeting", "followup_late", "그중 날짜 지남", "bad"),
    ("ir", "ir_requested", "IR 요청", ""),
    ("ir", "ir_delivered", "전달함", ""),
    ("ir", "ir_open", "안 보낸 요청", "warn"),
    ("ir", "call_done", "전화함", ""),
    ("ir", "call_open", "전화 요청 안 함", "warn"),
)

#: 연간 보고의 **판들 — 위에서 아래로.** 월간 보고와 **같은 차례**다
#: (`templates/report.html` 의 월간 쪽: 발송 → 미팅 → 미팅 결과 → IR 자료 요청).
#:
#: 사용자가 "연간도 월간 업무보고 스타일로" 라고 한 것이 이것이다. 항목 열셋이
#: 한 표에 뭉쳐 있으면 발송 이야기와 IR 이야기가 같은 칸에 섞여 서서, 월간에서
#: 판 이름이 해 주던 "이건 무슨 수인가" 를 아무도 안 해 준다.
#:
#: ★ **차례도 화면과 엑셀이 이 한 줄을 같이 읽는다**(`yearly_groups`). 두 곳에
#: 각자 늘어놓으면 판을 하나 끼울 때 한쪽만 끼워진다 — 항목 목록에서 이미 한
#: 번 정한 규칙이다.
#:
#: `(열쇠, 판 이름, 머릿수로 쓸 항목, 머릿수 꼬리말)`. `미팅 결과` 는 달마다
#: 한 칸짜리 수가 아니라 결과별 집계라 항목이 없다 — **차례에는 들어 있어야**
#: 화면과 파일의 판 순서가 갈리지 않으므로 열쇠만 두고 항목을 비운다.
YEARLY_GROUPS = (
    ("send", "발송", "send_sent", "건 완료"),
    ("meeting", "미팅", "total", "개사"),
    ("outcomes", "미팅 결과", "", ""),
    ("ir", "IR 자료 요청 · 전화 요청", "ir_requested", "건 요청"),
)


def yearly_items(months: List[dict], totals: Dict[str, int]) -> List[dict]:
    """연간 리포트의 줄들 — **항목마다 하나, 달마다 한 칸.**

    ## 무엇을 빼는가 — **항목**이지 **달**이 아니다

    사용자가 말한 것은 "각 항목마다 **내용 있는거 기준으로** 월별로 나눠서
    기록" 이다. 열두 달 × 열세 항목을 다 늘어놓으면 169칸 가운데 대부분이 빈
    칸이라 읽을 수가 없다.

    그래서 **한 해 내내 0 인 항목은 줄째로 뺀다.** 그 항목은 올해 아예 없던
    일이고, 빈 줄이 하나 서 있다고 그 사실이 더 잘 보이지도 않는다.

    **달은 열둘을 다 둔다.** 값이 없는 달을 빼면 *아무 일도 없던 달이 있었다*
    는 사실이 통째로 사라진다 — 8월이 비어 있는 것과 8월이 목록에 없는 것은
    다른 말이고, 한 해를 훑는 사람이 보려는 것에 앞엣것이 들어 있다. 달 칸이
    빠지면 옆 달과 나란히 놓고 견줄 수도 없다(그게 이 표의 전부다).

    합계가 0 인 항목만 빼므로, **어느 달에든 값이 하나라도 있으면 그 줄은
    선다** — 그 항목의 나머지 빈 달은 빈칸으로 남아 '그 달에는 없었다'를
    말한다.

    ## 왜 달이 칸이고 항목이 줄인가

    달을 줄로 세우면 한 항목의 한 해 흐름을 읽으려고 열두 줄을 세로로 훑어야
    한다. 이 보고에서 보려는 것이 바로 그 흐름이라(`올해 몇 건이나 했나`),
    항목을 줄로 두고 달을 옆으로 편다. 좁은 화면에서 어느 줄인지 잃지 않게
    맨 앞 칸을 붙박이로 둔다(`templates/report.html`).
    """
    out = []
    for group, key, label, level in YEARLY_ITEMS:
        if not totals.get(key):
            continue
        out.append({
            "key": key,
            # 어느 판에 서는 줄인가(`YEARLY_GROUPS`). 줄에 적어 두어야
            # `yearly_groups` 가 이 한 벌을 나누기만 하면 된다 — 판마다 항목을
            # 따로 늘어놓으면 목록이 두 벌이 된다.
            "group": group,
            "label": label,
            "level": level,
            # 달 차례 그대로 — 열두 칸. 값이 0 인 달은 화면·파일이 빈칸으로 둔다.
            "cells": [m[key] for m in months],
            "total": totals[key],
        })
    return out


def yearly_groups(year: int, items: List[dict], totals: Dict[str, int],
                  outcomes: List[tuple]) -> List[dict]:
    """연간 보고의 **판들** — 월간 보고와 같은 차례·같은 모양.

    ## 왜 판으로 나누는가

    월간 보고는 숫자를 **판(panel)** 으로 갈라 놓는다 — `9월 발송`,
    `9월 미팅 총 1개사`, `미팅 결과`, `IR 자료 요청`. 판 이름이 "이건 무슨
    수인가" 를 말해 주고, 묶음 머리의 알약(`count-pill`)이 그 판의 머릿수를
    든다. 연간은 그 열셋을 이름표 없는 표 하나에 뭉쳐 놓아서, 발송 이야기와
    IR 이야기가 같은 칸에 나란히 섰다.

    그래서 **판만 월간에서 가져오고, 달 열둘은 그 판 안의 작은 표로 둔다.**
    #227 이 만든 `항목 × 달` 표를 없애지 않는다 — 판별로 잘라 넣을 뿐이라
    달끼리 견주는 길이 그대로 살아 있고, 같은 수가 두 모양으로 서지도 않는다.

    ## 줄은 다시 고르지 않는다

    받은 `items` 를 `group` 으로 나누기만 한다(`yearly_items` 가 이미 무엇을
    뺄지 정했다). 여기서 또 추리면 "한 해 내내 0 인 항목은 뺀다" 가 두 곳에
    적히고, 언젠가 한쪽만 고쳐진다.

    ## 빈 판은 **서 있는다**

    줄이 하나도 안 남은 판도 자리를 지킨다 — 월간 보고의 빈 묶음이 그렇다
    (`딜 소싱 0건 완료 · 이 달에는 없습니다`). 판이 통째로 사라지면 *올해
    그 일이 아예 없었다* 가 아니라 *이 보고는 그걸 안 센다* 로 읽힌다.
    """
    out = []
    for key, label, head_key, tail in YEARLY_GROUPS:
        rows = [i for i in items if i["group"] == key]
        out.append({
            "key": key,
            # 판 이름은 **여기서 짓는다** — 화면과 파일이 각자 지으면 한쪽만
            # 옛말로 남는다(월간의 묶음 이름이 이미 그렇게 되어 있다).
            "title": f"{year}년 {label}",
            # 월간의 알약과 같은 말. 머릿수가 없는 판(`미팅 결과`)은 빈 글자라
            # 알약이 아예 안 붙는다.
            "pill": f"{totals.get(head_key, 0)}{tail}" if head_key else "",
            # 이름이 `items` 가 아닌 것은 **화면 쪽 함정** 때문이다: Jinja 에서
            # `g.items` 는 dict 의 `items()` 메서드로 먼저 잡혀 늘 참이 된다 —
            # 빈 판이 "줄이 있다" 로 읽혀 머리글만 선 표가 그려졌다. 월간 보고의
            # 묶음도 같은 이유로 `rows` 다(`_buckets`).
            "rows": rows,
            # 결과별 집계는 달 칸이 없다 — 이 판만 목록으로 그린다.
            "outcomes": outcomes if key == "outcomes" else [],
        })
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
    # 더하는 값들. **한 줄이 한 달에만 걸리는 것**만 여기 둔다 — 시퀀스 하나는
    # 걸 날(`call_open`)이든 건 날(`call_done`)이든 달 하나에만 들어가므로
    # 열두 달을 더한 값이 한 해의 수가 된다.
    months, totals = [], {"total": 0, "done": 0, "followup_done": 0,
                          "followup_open": 0, "followup_late": 0,
                          "ir_requested": 0, "ir_delivered": 0, "ir_open": 0,
                          "send_rounds": 0, "send_sent": 0, "send_left": 0,
                          "call_open": 0, "call_done": 0}
    # **달마다 한 번만 센다.** 예전에는 요약을 한 바퀴 돌고 미팅 결과를 세려고
    # 또 한 바퀴를 돌아 `monthly()` 가 열두 달에 스물네 번 불렸다 — 같은 달을
    # 두 번 세는 것이라 값이 갈릴 일은 없었지만, 한 해를 그리는 데 드는 질의가
    # 그냥 두 배였다. 엑셀 내려받기가 같은 길을 지나면서 더 눈에 띈다.
    outcome_counts: Dict[str, int] = {}
    for mon in range(1, 13):
        got = monthly(db, year, mon, user, today)
        months.append({
            "month": mon,
            "label": f"{mon}월",
            **{k: got[k] for k in totals},
        })
        for k in totals:
            totals[k] += got[k]
        for label, n in got["outcomes"]:
            outcome_counts[label] = outcome_counts.get(label, 0) + n

    outcomes = sorted(outcome_counts.items(), key=lambda t: -t[1])
    items = yearly_items(months, totals)

    return {
        "year": year,
        "months": months,
        "totals": totals,
        # 항목마다 한 줄, 달마다 한 칸. **화면과 엑셀이 이 한 벌을 같이 읽는다** —
        # 두 곳에서 따로 추리면 언젠가 두 문서의 줄이 갈린다.
        #
        # 이름이 `items` 가 아닌 것은, 이 dict 가 화면 ctx 에 통째로 부어지기
        # 때문이다(`ctx.update(report.yearly(...))`) — 흔한 이름은 다른 값을
        # 조용히 덮는다.
        "report_items": items,
        # 그 줄들을 **월간 보고와 같은 판 차례**로 나눠 담은 것
        # (`yearly_groups`). 줄을 다시 고르지 않고 위 한 벌을 나누기만 하므로,
        # 화면이 그리는 것도 파일이 적는 것도 같은 dict 다.
        "report_groups": yearly_groups(year, items, totals, outcomes),
        "outcomes": outcomes,
    }


def selectable_years(today: Optional[date] = None, back: int = 3) -> List[int]:
    """고를 수 있는 해. 앞으로도 한 해 열어 둔다 — 12월에 내년 일정을 잡는다."""
    today = today or date.today()
    return list(range(today.year - back, today.year + 2))
