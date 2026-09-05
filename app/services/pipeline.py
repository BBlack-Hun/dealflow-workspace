"""IR 요청 · 미팅 — 딜소개 뒤에 오는 일.

딜소개를 보내면 답이 온다. "이 기업 자료 주세요"(IR 요청), "한번 뵙죠"(미팅).
받은 것을 놓치면 그 회차에서 가장 뜨거운 반응을 흘려보내는 셈이다.

여기서 정하는 것은 세 가지다.
- **열린 것이 먼저 보인다.** 요청받고 안 보낸 건, 오늘 미팅, 결과를 물을 때가 된 건.
- **미팅이 끝나면 열흘 뒤 결과를 묻는다.** 그 열흘을 사람이 기억하지 않아도 되게.
- **답이 왔으면 리마인드를 멈춘다.** IR 요청이 왔는데 "지난번 공유드린
  기업들 검토 중…"이 또 나가면 상대는 이쪽이 자기 답을 못 봤다고 생각한다.
"""
from __future__ import annotations

import re
from datetime import date, time, timedelta
from typing import Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import IrCompany, IrRequest, Meeting, User, VcContact
from . import cadence, calendar_link
from .sheet_import import normalize_company_name

# 미팅이 끝나고 결과를 물어보기까지. 운영에서 쓰던 간격 그대로다.
MEETING_FOLLOWUP_DAYS = 10

REQUEST_STATUS = {
    "open": "요청받음",
    "delivered": "전달함",
    "dropped": "보내지 않음",
}
MEETING_STATUS = {
    "scheduled": "예정",
    "done": "완료",
    "canceled": "취소",
}
MEETING_KINDS = {"first": "1차 미팅", "second": "2차 미팅", "etc": "기타"}

#: 만나는 방식 — **캘린더 제목 앞머리의 세 번째 자리**가 이 값이다.
#: 같은 표의 `kind`·`status`·`outcome` 과 같은 방식이다(DB 에는 코드, 화면에는
#: 우리말). 비어 있으면 `안 정함` 이고 제목에서 그 자리가 슬래시째 빠진다 —
#: 둘 중 하나를 기본값으로 두면 아무도 안 고른 미팅이 `대면` 으로 나간다.
MEETING_MODES = {"in_person": "대면", "video": "화상"}

#: 갈 곳이 없는 방식. 이 미팅만 모인 날은 **캘린더에 장소를 안 넣는다** —
#: 사무실 주소를 장소로 넣으면 아침에 그것을 본 사람이 그리로 나선다.
#: 어느 말이 화상인지 아는 곳은 여기 하나다(`calendar_link` 는 `remote` 참/거짓만 받는다).
REMOTE_MODES = {"video"}
OUTCOMES = {
    "reviewing": "검토 중",
    "investing": "투자 검토",
    "hold": "보류",
    "pass": "거절",
}


def _key(name: Optional[str]) -> str:
    return normalize_company_name(name or "").replace(" ", "").lower()


def match_company(db: Session, name: str) -> Optional[IrCompany]:
    """이름으로 우리 DB 의 기업을 찾는다. 못 찾아도 요청은 남긴다.

    투자사가 다른 이름으로 부르거나 아직 등록 안 된 기업일 수 있다.
    못 찾았다고 기록을 버리면 요청을 놓친다.
    """
    key = _key(name)
    if not key:
        return None
    for company in db.execute(select(IrCompany)).scalars().all():
        if _key(company.name) == key:
            return company
    return None


def followup_date(done_on: date) -> date:
    """미팅 결과를 물어볼 날. 주말이면 다음 영업일로 민다.

    **날짜 단위 일이다.** 미팅이 몇 시였는지와 무관하게 며칠 뒤에 묻는다 —
    시각이 끼어들면 오후 미팅만 하루 밀리는 식으로 갈린다.
    """
    return cadence.next_business_day(done_on + timedelta(days=MEETING_FOLLOWUP_DAYS))


def clean_time(value: Optional[str]) -> Optional[str]:
    """적어 넣은 시각을 `HH:MM` 으로 정리한다. 못 읽으면 **버린다**.

    시각은 **비어 있어도 된다.** 날짜만 아는 단계가 실제로 있고("다음 주쯤"),
    필수로 만들면 그 단계를 기록할 수 없다. 그리고 못 읽은 값을 `00:00` 같은
    것으로 채우면 **자정 미팅**이 생긴다 — 지어낸 값은 화면에서 진짜처럼
    읽히므로, 모르면 비어 있는 것이 정확하다.

    `<input type="time">` 은 `HH:MM` 또는 `HH:MM:SS` 를 보낸다. 초는 버린다 —
    쓰는 곳이 없는데 칸마다 길이가 다르면 문자열로 견주는 자리만 어려워진다.
    """
    text = (value or "").strip()
    if not text:
        return None
    try:
        return time.fromisoformat(text).strftime("%H:%M")
    except ValueError:
        return None


def when_label(scheduled_at: Optional[str], scheduled_time: Optional[str]) -> str:
    """화면에 적는 `날짜 시각`. 시각을 모르면 날짜만 — 빈칸이 정확하다."""
    return f"{scheduled_at or ''} {scheduled_time or ''}".strip()


# --- 조회 -------------------------------------------------------------------

def _contact_map(db: Session, ids: List[int]) -> Dict[int, VcContact]:
    if not ids:
        return {}
    return {
        c.id: c for c in db.execute(
            select(VcContact).where(VcContact.id.in_(ids))
        ).scalars().all()
    }


def request_rows(db: Session, user: User) -> List[dict]:
    rows = db.execute(
        select(IrRequest).where(IrRequest.user_id == user.id)
        .order_by(IrRequest.status != "open", IrRequest.requested_at.desc())
    ).scalars().all()
    contacts = _contact_map(db, [r.contact_id for r in rows])
    today = date.today()

    out = []
    for row in rows:
        contact = contacts.get(row.contact_id)
        waited = None
        try:
            waited = (today - date.fromisoformat(row.requested_at)).days
        except (TypeError, ValueError):
            pass
        out.append({
            "id": row.id,
            "contact_id": row.contact_id,
            "name": contact.name if contact else "-",
            "title": (contact.title or "") if contact else "",
            "firm": (contact.firm or "") if contact else "",
            "company_name": row.company_name,
            "company_id": row.company_id,
            "ir_file": "",
            "requested_at": row.requested_at,
            "waited": waited,
            # 사흘 넘게 안 보냈으면 눈에 띄어야 한다.
            "overdue": bool(row.status == "open" and waited is not None and waited >= 3),
            "status": row.status,
            "status_label": REQUEST_STATUS.get(row.status, row.status),
            "delivered_at": row.delivered_at or "",
            "note": row.note or "",
        })

    # 자료 **파일명**을 함께 준다 — 요청 화면에서 무엇을 보낼지 보이게.
    # (링크가 아니다: 파일은 각자 PC 의 자료 폴더에 있다 — 0056 참고)
    ids = [r["company_id"] for r in out if r["company_id"]]
    if ids:
        names = {
            c.id: (c.ir_file_name or "") for c in db.execute(
                select(IrCompany).where(IrCompany.id.in_(ids))
            ).scalars().all()
        }
        for row in out:
            row["ir_file"] = names.get(row["company_id"], "")
    return out


#: 담당을 넘긴 자국. 시트에는 `->` · `>` · `→` 가 섞여 쓰인다. **`>` 하나만
#: 갈라도 `->` 와 `=>` 가 함께 잘린다**(왼쪽 끝에 `-` 나 `=` 가 남을 뿐인데,
#: 왼쪽은 지난 담당이라 버린다). 새 모양이 들어와도 오른쪽 토막은 안 다친다.
HANDOVER = re.compile(r"[>＞→⇒»]")

#: 넘긴 **날짜**. 운영에 적혀 있는 것은 `7/21` 한 가지뿐이지만, 연도가 붙거나
#: 점·한글로 적힐 자리를 함께 받아 둔다. **가름표(`/` `.` `-` `월`)를 반드시
#: 요구한다** — 안 그러면 `2팀` 같은 이름의 앞 숫자를 날짜로 읽고 뜯어낸다.
DATE_PREFIX = re.compile(
    r"^\s*(?:"
    r"(?:\d{2,4}[./-])?\d{1,2}[./-]\d{1,2}"          # 7/21 · 07-21 · 2026.07.21
    r"|(?:\d{2,4}\s*년\s*)?\d{1,2}\s*월\s*\d{1,2}\s*일?"   # 7월 21일
    r")[.)\]]?\s*")

#: 글자가 한 자라도 있어야 이름이다. 날짜를 뗀 뒤 숫자·부호만 남으면 이름이 아니다.
LETTER = re.compile(r"[^\W\d_]")


def current_assignee(value: Optional[str]) -> str:
    """`담당자` 칸에 적힌 글 → **지금 맡고 있는 사람.**

    이 칸에는 넘긴 이력이 화살표로 쌓인다 — `김담당 > 7/22 이담당` 은 김담당이
    맡던 것을 7월 22일에 이담당에게 넘겼다는 뜻이고, **지금 맡은 사람은
    화살표 뒤**다. 그대로 캘린더 제목에 실으면 앞머리가 이력으로 길어지고,
    이미 손을 뗀 사람 이름이 먼저 읽힌다.

    ::

        김담당 > 7/22 이담당  →  이담당      마지막 화살표 뒤, 날짜는 뗀다
        7/21 이담당          →  이담당      화살표가 없어도 날짜는 뗀다
        박담당               →  박담당      건드릴 것이 없다
        김담당 > 운영팀으로 전환 →  (빈 값)    잘라 낸 것이 이름 같지 않다
        7/23 최담당 ->       →  (빈 값)    잘라 낸 자리가 비어 있다

    **잘라 낸 값에만 그럴듯한지 따진다.** 화살표가 없는 값은 사람이 통째로
    적어 둔 것이라 우리가 고쳐 읽을 것이 없다 — 두 토막이든 뭐든 적힌 대로
    간다. 반면 화살표 뒤는 **우리가 해석해 집어낸 자리**라 틀릴 수 있는 곳이고,
    미덥지 않으면(빈 값 · 날짜만 · 여러 토막) **비운다 — 지어내지 않는다.**
    빈 자리는 제목에서 통째로 빠질 뿐이지만, 잘못 집은 이름은 그 사람의
    일정으로 읽힌다.

    화면의 `담당자` 칸은 **적힌 그대로** 둔다(`companies.html`). 넘긴 이력은
    그 칸에서 관리하는 것이라 여기서 줄여 보일 것이 아니다.
    """
    text = re.sub(r"\s+", " ", value or "").strip()
    if not text:
        return ""
    handed = HANDOVER.search(text) is not None
    tail = DATE_PREFIX.sub("", HANDOVER.split(text)[-1].strip(), count=1).strip()
    if not handed:
        return tail
    if not tail or " " in tail or not LETTER.search(tail):
        return ""
    return tail


def _company_assignees(db: Session, ids: List[int]) -> Dict[int, str]:
    """기업 → **IR 기업 현황의 `담당자` 칸**에서 읽은 지금 담당자.

    캘린더 제목 앞머리의 가운데 자리가 이 값이다 — 로그인한 사람의 팀이 아니라
    **그 기업을 관리하는 쪽**이다.

    `owner_user_id` 가 아니다. 그쪽은 계정을 가리키는 칸이라 화면의 `담당자`
    머리글과 이름이 비슷하지만, 시트에서 넘어온 줄에는 채워지지 않는다 —
    **운영 344곳이 전부 비어 있다.** 그 칸을 읽으면 제목의 그 자리가 늘 빈다.

    넘긴 이력이 쌓인 값은 `current_assignee` 가 마지막 담당자만 집어낸다.
    """
    picked = {i for i in ids if i}
    if not picked:
        return {}
    return {
        c.id: current_assignee(c.assignee_name)
        for c in db.execute(
            select(IrCompany).where(IrCompany.id.in_(picked))
        ).scalars().all()
    }


def _calendar_groups(db: Session, rows: List[Meeting],
                     contacts: Dict[int, VcContact], user: User
                     ) -> Dict[int, Tuple[str, int]]:
    """미팅 → (캘린더 주소, 그 주소가 담은 미팅 수).

    **같은 담당자 · 같은 날**을 한 일정으로 묶는다. 투자사 한 분을 만나러 가면
    그 자리에서 기업 둘셋을 잇달아 소개하는데, 건마다 따로 넣으면 같은 장소로
    하루에 칸이 셋 생기고 정작 몇 시부터 몇 시까지 비워야 하는지가 안 보인다.

    **상태도 묶음 열쇠에 넣는다.** 안 넣으면 같은 날 취소된 건이 예정된 건과
    한 일정에 섞여, 사람이 저장하는 순간 안 가는 미팅이 캘린더에 적힌다.
    """
    assignees = _company_assignees(db, [r.company_id for r in rows])
    groups: Dict[tuple, List[Meeting]] = {}
    for row in rows:
        if not row.scheduled_at:
            continue
        groups.setdefault((row.contact_id, row.scheduled_at[:10], row.status),
                          []).append(row)

    out: Dict[int, Tuple[str, int]] = {}
    for (contact_id, _when, _status), members in groups.items():
        contact = contacts.get(contact_id)
        url = calendar_link.group_url(
            user_name=user.name or "",
            contact_name=contact.name if contact else "",
            contact_title=(contact.title or "") if contact else "",
            firm=(contact.firm or "") if contact else "",
            phone=(contact.phone or "") if contact else "",
            office_phone=(contact.office_phone or "") if contact else "",
            address=(contact.address or "") if contact else "",
            meetings=[{
                "date": m.scheduled_at,
                "time": m.scheduled_time or "",
                "company": m.company_name or "",
                "assignee": assignees.get(m.company_id or 0, ""),
                # 제목에 설 우리말 딱지. 안 골랐으면 빈 문자열이다 —
                # 제목에서 그 자리가 통째로 빠진다.
                "mode": MEETING_MODES.get(m.meet_mode or "", ""),
                # 찾아갈 자리가 있는가. **모르는 것은 화상이 아니다** —
                # 안 고른 건까지 화상으로 치면 주소가 조용히 사라진다.
                "remote": (m.meet_mode or "") in REMOTE_MODES,
            } for m in members],
        )
        for m in members:
            out[m.id] = (url, len(members))
    return out


def meeting_rows(db: Session, user: User) -> List[dict]:
    rows = db.execute(
        select(Meeting).where(Meeting.user_id == user.id)
        # 같은 날 두 건이 잡히면 순서가 정해져 있어야 한다 — 날짜만으로
        # 정렬하면 새로고침할 때마다 위아래가 바뀔 수 있다.
        .order_by(Meeting.status != "scheduled", Meeting.scheduled_at.desc(),
                  Meeting.scheduled_time.desc())
    ).scalars().all()
    contacts = _contact_map(db, [r.contact_id for r in rows])
    calendars = _calendar_groups(db, rows, contacts, user)
    today = date.today()

    # 담당자별 **가장 나중 미팅 날짜**. 2차 미팅을 이미 잡았다면 1차에
    # "그 뒤 어떻게 되셨나요" 를 물을 이유가 없다 — 이미 이어졌다.
    latest: Dict[int, str] = {}
    for row in rows:
        when_iso = row.scheduled_at or ""
        if when_iso > latest.get(row.contact_id, ""):
            latest[row.contact_id] = when_iso

    out = []
    for row in rows:
        contact = contacts.get(row.contact_id)
        when = _as_date(row.scheduled_at)
        due = _as_date(row.followup_due)
        # 뒤에 잡힌 미팅이 있으면 이 건은 결과 문의 관점에서 끝난 것이다.
        superseded = (row.scheduled_at or "") < latest.get(row.contact_id, "")
        out.append({
            "id": row.id,
            "contact_id": row.contact_id,
            "name": contact.name if contact else "-",
            "title": (contact.title or "") if contact else "",
            "firm": (contact.firm or "") if contact else "",
            "company_name": row.company_name or "",
            "scheduled_at": row.scheduled_at,
            # 몇 시 미팅인지. 안 적어 둔 건은 빈 문자열이다 — 화면이 날짜만
            # 보여주면 된다(없는 시각을 지어내면 그 시간에 간다).
            "scheduled_time": row.scheduled_time or "",
            "when_label": when_label(row.scheduled_at, row.scheduled_time),
            "days_left": (when - today).days if when else None,
            "kind": row.kind,
            "kind_label": MEETING_KINDS.get(row.kind, row.kind),
            # 대면인가 화상인가. 안 골랐으면 둘 다 빈 문자열이다 — 화면이
            # `안 정함` 으로 그리고, 캘린더 제목에서는 그 자리가 빠진다.
            "meet_mode": row.meet_mode or "",
            "meet_mode_label": MEETING_MODES.get(row.meet_mode or "", ""),
            "status": row.status,
            "status_label": MEETING_STATUS.get(row.status, row.status),
            "outcome": row.outcome or "",
            "outcome_label": OUTCOMES.get(row.outcome or "", ""),
            "followup_due": row.followup_due or "",
            "followup_done": bool(row.followup_done),
            # 무슨 얘기가 오갔는지. 결과 한 칸(진행/보류/거절)만으로는
            # **왜** 그런지가 남지 않는다.
            "note": row.note or "",
            "followup_note": row.followup_note or "",
            "followup_at": row.followup_at or "",
            # 구글 캘린더 '일정 추가' 주소. **규칙은 `calendar_link` 한 곳에만
            # 있다** — 화면마다 주소를 새로 조립하면 소요시간이나 시간대가
            # 한 곳에서만 고쳐져 갈린다.
            #
            # 같은 담당자·같은 날의 미팅은 **한 주소를 함께 쓴다**. 그래서 그
            # 묶음의 어느 줄에서 눌러도 같은 일정 하나가 뜬다 — 줄마다 다른
            # 일정이 나오면 하루에 칸이 여럿 생긴다.
            "gcal_url": calendars.get(row.id, ("", 0))[0],
            # 이 주소가 미팅 몇 건을 담고 있는가. 화면이 링크 옆에 적어 준다 —
            # 안 적으면 두 줄에서 두 번 눌러 같은 일정을 두 개 만든다.
            "gcal_count": calendars.get(row.id, ("", 0))[1],
            # 결과를 물어볼 필요가 남았는가.
            #   거절로 끝났다        → 물어볼 것이 없다
            #   다음 미팅을 잡았다    → 이미 이어졌다
            "needs_followup": (row.status == "done" and not row.followup_done
                               and (row.outcome or "") not in NO_FOLLOWUP_OUTCOMES
                               and not superseded),
            "superseded": superseded,
            # 결과를 물어볼 날이 지났는데 아직 안 물어봤다
            "followup_due_now": bool(
                row.status == "done" and not row.followup_done
                and (row.outcome or "") not in NO_FOLLOWUP_OUTCOMES
                and not superseded
                and due is not None and due <= today),
        })
    return out


def _as_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def last_batch_items(db: Session, contact_id: int) -> dict:
    """이 담당자가 **마지막으로 받은 회차**의 번호와 기업.

    투자사는 "4번, 6번 주세요" 라고 답한다. 그 번호가 어느 기업인지 사람이
    지난 카톡을 뒤져 맞추고 있었다. 회차에 번호가 그대로 남아 있으므로
    여기서 꺼내 보여준다.
    """
    from ..models import DealBatch, DealBatchCompany, SendItem, SendJob

    row = db.execute(
        select(SendJob.batch_id, DealBatch.title, DealBatch.sent_date)
        .join(SendItem, SendItem.job_id == SendJob.id)
        .join(DealBatch, DealBatch.id == SendJob.batch_id)
        .where(SendItem.contact_id == contact_id, SendItem.status == "sent",
               SendJob.kind == "deal_intro", SendJob.batch_id.isnot(None))
        .order_by(SendItem.id.desc()).limit(1)
    ).first()
    if row is None:
        return {"batch_id": None, "title": "", "sent_date": "", "items": []}

    batch_id, title, sent_date = row
    links = db.execute(
        select(DealBatchCompany, IrCompany)
        .join(IrCompany, IrCompany.id == DealBatchCompany.company_id)
        .where(DealBatchCompany.batch_id == batch_id)
        .order_by(DealBatchCompany.position)
    ).all()
    return {
        "batch_id": batch_id,
        "title": title or "지난 회차",
        "sent_date": sent_date or "",
        "items": [{"position": link.position, "company_id": company.id,
                   "name": company.name,
                   "has_file": bool((company.ir_file_name or "").strip())}
                  for link, company in links],
    }


def resolve_request_names(db: Session, contact_id: int,
                          raw: str) -> tuple:
    """적어 넣은 것을 기업으로 푼다. **번호도 이름처럼 받는다.**

    투자사는 "2, 4 주세요" 라고 답한다. 지금까지는 그 번호를 기업명으로 읽어서
    `2` 라는 이름의 요청이 그대로 만들어졌다 — 어느 기업인지 아무도 모르는
    기록이 남고, 자료 전달 문구도 만들 수 없었다.

    번호는 **그 담당자에게 마지막으로 보낸 회차**의 자리 번호로 읽는다.
    이름과 섞여 있어도 된다("2, 샘플애그, 4").

    돌려주는 것: (풀린 목록, 못 찾은 번호 목록)
    """
    tokens = [t.strip() for t in raw.replace(",", "\n").splitlines() if t.strip()]
    if not tokens:
        return [], []

    numbered = {}
    if any(t.isdigit() for t in tokens):
        batch = last_batch_items(db, contact_id)
        numbered = {str(item["position"]): item for item in batch["items"]}

    resolved, unknown = [], []
    for token in tokens:
        if token.isdigit():
            item = numbered.get(token)
            if item is None:
                # 없는 번호를 조용히 이름으로 남기면 '3' 이라는 기업이 생긴다.
                unknown.append(token)
                continue
            resolved.append({"name": item["name"], "company_id": item["company_id"]})
            continue
        company = match_company(db, token)
        resolved.append({"name": token,
                         "company_id": company.id if company else None})

    # 같은 기업을 번호와 이름으로 둘 다 적었을 수 있다.
    seen, unique = set(), []
    for row in resolved:
        key = row["company_id"] or row["name"]
        if key in seen:
            continue
        seen.add(key)
        unique.append(row)
    return unique, unknown


def group_by_contact(requests: List[dict]) -> List[dict]:
    """담당자별로 묶는다. 한 사람이 여러 기업을 한꺼번에 요청하는 일이 잦아,
    한 번에 보내야 대화가 자연스럽다."""
    grouped: Dict[int, dict] = {}
    for row in requests:
        item = grouped.setdefault(row["contact_id"], {
            "contact_id": row["contact_id"], "name": row["name"],
            "title": row["title"], "firm": row["firm"],
            "rows": [], "company_ids": [], "missing": [], "no_file": [],
        })
        item["rows"].append(row)
        if row["company_id"]:
            item["company_ids"].append(row["company_id"])
            if not row["ir_file"]:
                item["no_file"].append(row["company_name"])
        else:
            item["missing"].append(row["company_name"])
    return sorted(grouped.values(), key=lambda g: -len(g["rows"]))


def today_items(db: Session, user: User, today: Optional[date] = None) -> dict:
    """지금 손대야 할 것만. 대시보드와 '오늘 할 일'이 같은 값을 쓴다."""
    today = today or date.today()
    requests = [r for r in request_rows(db, user) if r["status"] == "open"]
    meetings = meeting_rows(db, user)
    return {
        "open_requests": requests,
        "overdue_requests": [r for r in requests if r["overdue"]],
        "today_meetings": [m for m in meetings
                           if m["status"] == "scheduled"
                           and m["scheduled_at"] == today.isoformat()],
        "upcoming_meetings": [m for m in meetings
                              if m["status"] == "scheduled"
                              and m["scheduled_at"] > today.isoformat()],
        "due_followups": [m for m in meetings if m["followup_due_now"]],
    }


# --- 상태 바꾸기 ------------------------------------------------------------

def deliver(db: Session, request: IrRequest, when: Optional[date] = None) -> IrRequest:
    request.status = "delivered"
    request.delivered_at = (when or date.today()).isoformat()
    db.flush()
    return request


def close_requests_for(db: Session, job, contact_id: int,
                       when: Optional[date] = None) -> int:
    """IR 자료를 보냈으면 그 요청을 '전달함'으로 닫는다.

    보내고 나서 다시 화면으로 돌아와 버튼을 누르게 하면, 바쁠 때 그 한 번을
    빼먹는다. 그러면 이미 보낸 요청이 계속 '보낼 자료'에 남는다.

    회차에 담긴 기업과 이름이 맞는 열린 요청만 닫는다 — 같은 담당자의
    다른 기업 요청까지 함께 닫으면 안 보낸 것을 보냈다고 적는 셈이다.
    """
    from ..models import DealBatchCompany

    if job.batch_id is None:
        return 0
    sent_ids = {
        row.company_id for row in db.execute(
            select(DealBatchCompany).where(DealBatchCompany.batch_id == job.batch_id)
        ).scalars().all()
    }
    if not sent_ids:
        return 0
    sent_keys = {
        _key(c.name) for c in db.execute(
            select(IrCompany).where(IrCompany.id.in_(sent_ids))
        ).scalars().all()
    }

    closed = 0
    for row in db.execute(
        select(IrRequest).where(IrRequest.contact_id == contact_id,
                                IrRequest.status == "open")
    ).scalars().all():
        matched = row.company_id in sent_ids or _key(row.company_name) in sent_keys
        if matched:
            deliver(db, row, when)
            closed += 1
    return closed


# 결과를 물어볼 필요가 없는 결말. **거절당한 곳에 "그 뒤 어떻게 되셨나요" 를
# 묻는 것은 실례다.** 이미 답을 받았으므로 물어볼 것이 남아 있지 않다.
# 보류는 뺀다 — 다시 살아날 수 있어 물어볼 값어치가 있다.
NO_FOLLOWUP_OUTCOMES = {"pass"}


def needs_followup(meeting: Meeting) -> bool:
    """이 미팅에 결과를 물어봐야 하는가."""
    return (meeting.status == "done"
            and not meeting.followup_done
            and (meeting.outcome or "") not in NO_FOLLOWUP_OUTCOMES)


def complete_meeting(db: Session, meeting: Meeting, outcome: str = "",
                     when: Optional[date] = None) -> Meeting:
    """미팅 완료. 결말에 따라 **열흘 뒤 결과를 물을 날**을 함께 잡는다.

    거절로 끝났으면 잡지 않는다 — 물어볼 것이 남아 있지 않다.
    """
    done_on = when or date.today()
    meeting.status = "done"
    meeting.done_at = done_on.isoformat()
    if outcome in OUTCOMES:
        meeting.outcome = outcome
    if (meeting.outcome or "") in NO_FOLLOWUP_OUTCOMES:
        meeting.followup_due = None
    else:
        meeting.followup_due = followup_date(done_on).isoformat()
    meeting.followup_done = 0
    db.flush()
    return meeting
