"""딜소개 메모 → 활동 이력 (개선 과제 #52).

## 왜 만드나

그룹웨어(앱 발송)로 딜을 보내지 않고 **개인적으로 보낸 뒤 탭의 월별 칸**
(`10월 1차 딜소개`)에 메모로 적는 탭이 있다. 그 메모는 `VcContact.notes` 의
글일 뿐이라 활동 이력 · 업무 보고 · 대시보드 어디에도 안 잡힌다.

## 새로 세는 자리를 만들지 않는다

메모의 회차 하나를 **손으로 보낸 기록 한 줄**(`source="manual"`)로 옮긴다.
그러면 업무 보고(`report._sends`) · 대시보드 · 팀 현황이 이미 세고
(`manual_send.counted`), 담당자 이력의 [되돌리기] 도 그대로 선다
(`manual_send.undoable`). 판정도 있던 것을 지난다 —

  * 회차 가르기 · 기업 쪼개기: `sheet_import.parse_activity_cell`(시트 가져오기와 같은 함수)
  * 이미 있나: `manual_send.existing`(같은 사람 · 날짜 · 기업, 출처 무관)
  * 거두기: `manual_send.undo`(되돌리기와 같은 숨김)

## 같은 입력이면 몇 번 돌려도 결과가 같다

나중에 밤 배치가 이 `plan` · `apply` 를 그대로 부른다. 그래서 한 번 적은 줄은
"이미 있음" 으로, 사람이 되돌린 줄은 "되돌림" 으로 빠지고, 메모에서 지워진
회차의 줄만 거둔다.
"""
from __future__ import annotations

from collections import Counter
from datetime import date, timedelta
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import clock
from ..models import SOURCE_MANUAL, ContactActivity, VcContact, including_undone
from . import contact_columns, manual_send, monthly_columns, sheet_import, sheet_owner

#: 이 날 이전 회차는 건너뛴다 — 3~9월 소급은 하지 않기로 했다(#52).
START = "2026-10-01"

#: 묶음 표시 `memo-{칸번호}-{날짜}`. 칸번호로 **어느 칸에서 온 줄인지** 안다 —
#: 메모를 고쳤을 때 그 칸에서 온 줄만 거둔다.
PREFIX = "memo-"

#: 업무 보고 · 이력에 서는 이름. 앱 발송도 손으로 고른 판도 아닌 것이 보여야 한다.
BY_MEMO = f"{manual_send.BY_HAND}(메모)"

#: 오늘 뒤로 이만큼 안의 날짜는 **앞날**(미리 적어 둔 회차)로 보고 건너뛴다.
#: 그보다 먼 날짜는 지난해의 그 날이다(1월에 읽는 `12/28`).
FUTURE_DAYS = 31

DEAL_INTRO = manual_send.DEAL_INTRO


def target_columns(columns) -> list:
    """메모를 읽을 칸 — 이름 앞에 `N월` 이 있고 `딜소개` 가 든 칸(숨긴 칸 제외).

    달은 **이름으로만** 본다. `ContactColumn.month`·`kind` 는 비었거나 틀린 칸이
    있다. IR 요청 · 미팅 칸은 대상이 아니다.
    """
    return [c for c in columns
            if not c.is_hidden
            and monthly_columns.month_of(c.label) is not None
            and "딜소개" in (c.label or "").replace(" ", "")]


def batch_key(column_id: int, day: str) -> str:
    return f"{PREFIX}{column_id}-{day}"


def is_memo(key: Optional[str]) -> bool:
    return bool(key) and key.startswith(PREFIX)


def _column_of(key: str) -> Optional[int]:
    head = key[len(PREFIX):].split("-", 1)[0]
    return int(head) if head.isdigit() else None


def resolve_day(month: int, day: int, today: date) -> Optional[date]:
    """`M/D` 의 해를 정한다 — **오늘 이전에서 가장 가까운 그 날.**

    다만 오늘 뒤 `FUTURE_DAYS` 안이면 그 날을 그대로 돌려준다(부르는 쪽이 앞날로
    건너뛴다). 미리 적어 둔 `10/25` 를 작년 것으로 읽으면 안 된다.
    없는 날짜(`2/30`)면 `None`.
    """
    for year in range(today.year + 1, today.year - 5, -1):
        try:
            got = date(year, month, day)
        except ValueError:
            continue
        if got <= today + timedelta(days=FUTURE_DAYS):
            return got
    return None


def _key(contact_id: int, day: str, names, count) -> tuple:
    return (contact_id, day, tuple(names or ()), count)


def plan(db: Session, sheet: str, today: Optional[date] = None) -> dict:
    """무엇을 적고 거둘지 **세어만 본다.** 한 줄도 안 쓴다.

    돌려주는 것: 회차 목록 `add`(새로 적음) · `already`(이미 있음) ·
    `undone`(사람이 되돌림 — 다시 안 살린다) · `no_date` · `no_company` ·
    `before_start` · `future`(건너뜀), 거둘 줄 `retract`(ORM 줄), 그리고 권한을
    봐야 할 담당자 번호 `contact_ids`.
    """
    today = today or clock.today()
    cols = target_columns(contact_columns.month_columns(db, sheet, create=False))
    people = [c for c in db.execute(select(VcContact)).scalars()
              if sheet in sheet_owner.labels_of(c.source_sheet)]
    out = {k: [] for k in ("add", "already", "undone", "no_date", "no_company",
                           "before_start", "future", "retract")}
    out.update(sheet=sheet, columns=[c.label for c in cols], start=START)

    touched = set()
    wanted = set()
    pending: List[dict] = []
    for person in people:
        notes = contact_columns.load_notes(person.notes)
        for col in cols:
            text = notes.get(contact_columns.note_key(col.id), "")
            for entry in sheet_import.parse_activity_cell(
                    text, None, DEAL_INTRO, today.year):
                touched.add(person.id)
                item = {"contact_id": person.id, "name": person.name or "",
                        "firm": person.firm or "", "column_id": col.id,
                        "column": col.label, "raw": entry.raw_text or "",
                        "day": "", "companies": entry.companies,
                        "count": entry.company_count}
                # `parse_activity_cell` 은 해를 `today.year` 로 붙인다 — 달·일만 읽는다.
                got = (resolve_day(int(entry.happened_at[5:7]),
                                   int(entry.happened_at[8:10]), today)
                       if entry.happened_at else None)
                if got is None:
                    out["no_date"].append(item)
                    continue
                item["day"] = got.isoformat()
                if got > today:
                    out["future"].append(item)
                elif item["day"] < START:
                    out["before_start"].append(item)
                elif not entry.company_count:
                    out["no_company"].append(item)
                else:
                    key = _key(person.id, item["day"], entry.companies,
                               entry.company_count)
                    if key not in wanted:      # 같은 회차를 두 칸에 적었다
                        wanted.add(key)
                        pending.append(item)

    # 그 칸에서 온 줄 중 **지금 메모에 없는** 것만 거둔다. 시트 · 앱 줄은 안 본다.
    col_ids = {c.id for c in cols}
    retract = [
        row for row in db.execute(
            select(ContactActivity).where(
                ContactActivity.contact_id.in_([p.id for p in people] or [0]),
                ContactActivity.source == SOURCE_MANUAL,
                ContactActivity.batch_key.like(f"{PREFIX}%"))
            .order_by(ContactActivity.id)).scalars()
        if _column_of(row.batch_key) in col_ids
        and _key(row.contact_id, row.happened_at, row.companies,
                 row.company_count) not in wanted]

    for item in pending:
        names = item["companies"]
        args = (db, item["contact_id"], DEAL_INTRO, item["day"])
        kw = {"company_names": names or None,
              "company_count": None if names else item["count"]}
        found = manual_send.existing(*args, **kw)
        if found is not None:
            # 개수만 적은 회차(`3개사`)는 이름 든 줄과도 맞는다 — 그 줄을 이 회차의
            # 기록으로 남긴다(거두면 다음 판에 또 적혀 결과가 판마다 달라진다).
            if found in retract:
                retract.remove(found)
            out["already"].append(item)
            continue
        with including_undone(db):
            gone = manual_send.existing(*args, **kw)
        # shortcut: 메모를 고쳤다 되돌려 놓으면 앞서 거둔 줄도 '되돌림' 으로 빠진다
        # (사람의 되돌리기와 거두기를 가르는 표시가 없다). 문제가 되면 거둔 줄에 표시를 남긴다.
        (out["undone"] if gone is not None else out["add"]).append(item)

    out["retract"] = retract
    out["contact_ids"] = sorted(touched | {row.contact_id for row in retract})
    return out


def _content(count: int) -> str:
    return f"{manual_send.KIND_LABELS[DEAL_INTRO]} — {BY_MEMO} · {count}개사"


def apply(db: Session, p: dict) -> dict:
    """`plan` 대로 적고 거둔다. 리마인드는 세우지 않는다. 커밋은 부르는 쪽이 한다."""
    for item in p["add"]:
        day, names = item["day"], item["companies"]
        db.add(ContactActivity(
            contact_id=item["contact_id"], kind=DEAL_INTRO, source=SOURCE_MANUAL,
            content=_content(item["count"]), happened_at=day, month=day[:7],
            weekday=sheet_import.weekday_of(day),
            company_names=manual_send._payload(names) if names else None,
            company_count=item["count"], raw_text=item["raw"],
            batch_key=batch_key(item["column_id"], day)))
    undone = manual_send.undo(db, p["retract"])
    db.flush()
    return {"added": len(p["add"]), "retracted": undone.rows,
            "note": f"{len(p['add'])}줄 적음 · {undone.rows}줄 거둠"}


def view(p: dict) -> dict:
    """화면 · API 가 싣는 모양(JSON). 거둘 줄은 사람이 읽을 것만 남긴다."""
    rounds = Counter((i["column"], i["day"]) for i in p["add"])
    return {
        **{k: v for k, v in p.items() if k != "retract"},
        "rounds": [{"column": c, "day": d, "people": n}
                   for (c, d), n in sorted(rounds.items(), key=lambda t: t[0][1])],
        "retract": [{"contact_id": r.contact_id,
                     "name": r.contact.name if r.contact else "",
                     "day": r.happened_at, "companies": r.companies,
                     "count": r.company_count} for r in p["retract"]],
    }
