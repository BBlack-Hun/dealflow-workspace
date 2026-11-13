"""계정 이름 바꾸기 — **같은 사람의 표시 이름**을 바꾸고 그 이름을 담은 곳을 같이 옮긴다.

팀 현황의 [이름·번호 수정](`routers/dashboard.edit_member_profile`)과는 다른 일이다.
그쪽은 **계정을 다른 사람에게 물려주는** 길이라 탭 이름이 따라가지 않는다(옛 담당자가
한 일이 새 사람 이름으로 바뀌면 안 된다). 여기는 사람이 그대로고 **부르는 이름만**
바뀐다 — 11/04 에 팀원 이름을 한꺼번에 바꿀 때 운영에서 손으로 옮긴 범위를 화면으로 옮겼다.

## 같이 바뀌는 것

- 계정 이름(`User.name`).
- **그 계정이 주인인 탭** 중 이름이 **토막으로** 든 탭(`스타트업 · 이름`, `이름 105명`).
  옮기는 일은 `sheet_owner.rename` 하나가 한다(사람 · 달 칸 · 달 표시가 같이 간다).
- 담당자 칸 다섯(`ASSIGNEE_COLUMNS`) — 값이 그 이름과 같은 줄, 그리고 이관 이력 꼴
  (`옛 담당 > 10/01 이름`)에 이름이 토막으로 든 줄. 11/04 에도 이력 속 이름까지 바꿨다.

## 바꾸지 않는 것

카톡방 이름 · 메모 · 비고 · 수정 기록 본문 · 스타트업 notes 의 담당 이력 — 11/04 와 같다.
**다른 계정이 주인인 탭**도 그대로 둔다. 탭 이름 바꾸기는 탭 주인과 관리자만 하는 일이고
(`sheet_owner.may_add_row`), 남의 탭에 든 이름은 대개 넘겨받은 명단의 옛 주인 표시다.
미리보기에 그 탭을 따로 적어 사람이 보게 한다.

## 토막으로만 바꾼다

`가람` 을 바꿀 때 `나가람 투자사` 의 `가람` 은 건드리지 않는다 — 앞뒤가 글자(한글 ·
영문 · 숫자)가 아닐 때만 이름이다(`_token`). 글자 속까지 바꾸면 다른 사람 이름이 뭉개진다.

## 한 판으로 남긴다

줄마다 수정 기록을 남기면 이름 하나에 수백 줄이 쌓여 그날의 다른 기록이 묻힌다 — 탭
지우기 · 시트 올리기와 같은 이유로 **한 줄**로 적는다(`edit_log.log_account_rename`).
같은 까닭으로 따라 바뀐 줄의 `수정한 날짜`(`updated_at`)는 그대로 둔다 — 이름만 바뀐
줄 수백 개가 오늘 고친 줄로 맨 위에 서면 정작 오늘 고친 줄을 못 찾는다.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import List, Tuple

from sqlalchemy import event, select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from ..models import (IrCompany, SendItem, SeriesACompany, SheetOwner, SourcingContact,
                      User, VcContact)
from . import backup, company_sync, edit_log, sheet_owner

#: 이름 길이 상한. 탭 이름(80자)에 화면 이름과 함께 들어가도 넘치지 않게 넉넉히 짧다.
MAX_NAME = 20

#: 화면이 따로 쓰는 말 — 계정 이름이 되면 읽는 사람이 헷갈린다. 사이드바는 관리자 뒤에
#: ` · 관리자` 를 붙이고, 수정 기록은 앱이 혼자 고친 일을 `자동` 으로 적고, 담당 고르개는
#: `전체` 를 세운다. `직접 추가` 는 시트에서 오지 않은 줄의 명단 이름이다.
RESERVED = ("관리자", edit_log.AUTO_ACTOR, "전체", sheet_owner.MANUAL_SHEET)

#: 담당자 칸 — (모델, 화면에 적을 이름, 수정 기록 칸 이름).
ASSIGNEE_COLUMNS = (
    (VcContact, "투자사 관리 현황", "rename_vc_contacts"),
    (SourcingContact, "딜 소싱", "rename_sourcing_contacts"),
    (IrCompany, "IR 기업 현황", "rename_ir_companies"),
    (SeriesACompany, "Series A 이상 딜 소싱", "rename_series_a_companies"),
    (SheetOwner, "명단 설정", "rename_sheet_owners"),
)

_LETTER = "0-9A-Za-z가-힣"


class RenameRefused(ValueError):
    """바꿀 수 없는 이유 — 사람에게 그대로 보여 줄 문장이다."""


def clean(name: str) -> str:
    """저장하는 모양 — 앞뒤를 자르고 겹친 띄어쓰기를 하나로."""
    return " ".join((name or "").split())


def _key(name: str) -> str:
    """겹치는지 견줄 때의 모양 — 대소문자 · 띄어쓰기를 무시한다."""
    return "".join((name or "").split()).casefold()


def _token(name: str) -> "re.Pattern":
    """이름이 **토막으로** 든 자리 — 앞뒤가 글자가 아니어야 한다(머리말)."""
    return re.compile(rf"(?<![{_LETTER}]){re.escape(name)}(?![{_LETTER}])")


def _swap(value: str, old: str, new: str) -> str:
    return _token(old).sub(lambda _m: new, value)


def check_name(db: Session, member: User, new: str) -> str:
    """새 이름을 거른다 — 저장할 모양을 돌려주거나 `RenameRefused`."""
    name = clean(new)
    if not name:
        raise RenameRefused("새 이름을 적어 주세요")
    if len(name) > MAX_NAME:
        raise RenameRefused(f"이름은 {MAX_NAME}자까지입니다")
    if "," in name:
        # 탭 이름에 들어가는데 `source_sheet` 가 쉼표로 이은 목록이다(`sheet_owner.rename`).
        raise RenameRefused("이름에는 쉼표를 쓸 수 없습니다")
    if not re.search(r"[^\d\s\-]", name):
        # 이름이 비면 로그인 ID(휴대폰번호)가 이름 자리에 들어간다(`sheet_owner.real_name`).
        raise RenameRefused("숫자만으로 된 이름은 쓸 수 없습니다")
    if _key(name) in {_key(r) for r in RESERVED}:
        raise RenameRefused(f"'{name}' 은(는) 화면에서 따로 쓰는 말이라 이름으로 쓸 수 없습니다")
    if name == (member.name or "").strip():
        raise RenameRefused("지금 이름과 같습니다")
    for other in db.execute(select(User).where(User.id != member.id)).scalars():
        if _key(other.name) == _key(name):
            # 시트 올리기는 담당 이름이 계정 이름과 **정확히 같아야** 그 계정에 붙는다
            # (`sheet_import`) — 두 계정이 같은 이름이면 먼저 찾은 쪽으로 간다.
            raise RenameRefused("다른 계정이 이미 쓰는 이름입니다")
    return name


@dataclass
class Plan:
    """바꾸기 전에 세어 둔 것 — 미리보기와 실제 바꾸기가 **같은 계획**을 지난다."""

    member_id: int
    before: str
    after: str
    tabs: List[Tuple[str, str]] = field(default_factory=list)       # (지금 이름, 새 이름)
    other_tabs: List[str] = field(default_factory=list)             # 남의 탭 — 안 바꾼다
    columns: List[dict] = field(default_factory=list)               # 담당자 칸 표마다
    already: int = 0          # 새 이름으로 이미 적힌 담당자 칸 — 바꾸고 나면 이 계정 것
    problem: str = ""         # 있으면 바꾸지 않는다
    #: 지금 이름이 사람 이름인가 — 로그인 ID(휴대폰번호)가 이름 자리에 든 계정은 같이
    #: 바꿀 것을 찾지 않는다(번호 글자로 탭 · 담당자 칸을 훑을 까닭이 없다).
    cascade: bool = True

    @property
    def total(self) -> int:
        return sum(c["equal"] + c["history"] for c in self.columns)

    @property
    def fingerprint(self) -> str:
        """미리 본 계획의 지문 — 그 사이 무엇이 바뀌었으면 [바꾸기]가 다시 묻는다."""
        body = json.dumps([self.member_id, self.before, self.after, self.tabs,
                           [(c["table"], c["equal"], c["history"]) for c in self.columns]],
                          ensure_ascii=False)
        return hashlib.sha1(body.encode("utf-8")).hexdigest()[:16]


def _assignee_hits(db: Session, model, old: str):
    """(같은 줄, 이력 속에 든 줄) — 담당자 칸 하나."""
    pattern = _token(old)
    equal, history = [], []
    for row in db.execute(select(model).where(model.assignee_name.isnot(None))).scalars():
        value = row.assignee_name or ""
        if value.strip() == old:
            equal.append(row)
        elif pattern.search(value):
            history.append(row)
    return equal, history


def sending_note(db: Session) -> str:
    """발송이 돌고 있으면 막는 사유. 회차 중간에 이름 · 탭이 바뀌면 받는 사람이 어긋난다.

    판정은 되돌리기와 같은 것을 쓴다(`backup.sending_now` — 대기 · 진행 중 회차) — 거기에
    회차 상태와 상관없이 발송기가 쥐고 있는 건(`sending`)을 더한다(탭 지우기와 같다).
    """
    jobs = [j.id for j in backup.sending_now(db)]
    jobs += [jid for (jid,) in db.execute(
        select(SendItem.job_id).where(SendItem.status == "sending").distinct())
        if jid not in jobs]
    if not jobs:
        return ""
    shown = ", ".join(f"#{j}" for j in sorted(jobs)[:5])
    return f"발송 중인 회차가 있어 지금은 바꿀 수 없습니다(회차 {shown}) — 끝난 뒤 다시 해 주세요"


def plan(db: Session, member: User, new: str) -> Plan:
    """무엇이 몇 개 같이 바뀌는지 센다 — **DB 를 고치지 않는다.**

    이름 자체가 안 되면 `RenameRefused`. 이름은 되는데 지금 바꿀 수 없으면(발송 중 ·
    탭 이름이 겹침) `problem` 에 사유를 싣고 돌려준다 — 미리보기는 무엇이 바뀔지를
    그대로 보여 주고 단추만 감춘다.
    """
    after = check_name(db, member, new)
    before = sheet_owner.real_name(member)
    out = Plan(member_id=member.id, before=(member.name or "").strip(), after=after,
               cascade=bool(before))
    if before:
        pattern = _token(before)
        for row in db.execute(select(SheetOwner).order_by(SheetOwner.id)).scalars():
            if not pattern.search(row.label or ""):
                continue
            if row.user_id != member.id:
                out.other_tabs.append(row.label)
                continue
            label = _swap(row.label, before, after)
            out.tabs.append((row.label, label))
            if not out.problem and len(label) > sheet_owner.MAX_LABEL:
                out.problem = f"탭 이름이 {sheet_owner.MAX_LABEL}자를 넘습니다: {label}"
            elif not out.problem and sheet_owner.label_in_use(db, label, ignore=row.label):
                out.problem = f"같은 이름의 탭이 이미 있어 바꿀 수 없습니다: {label}"
        for model, title, key in ASSIGNEE_COLUMNS:
            equal, history = _assignee_hits(db, model, before)
            out.columns.append({"table": model.__tablename__, "title": title, "key": key,
                                "equal": len(equal), "history": len(history)})
        for model, _title, _key_ in ASSIGNEE_COLUMNS:
            out.already += sum(1 for (v,) in db.execute(
                select(model.assignee_name).where(model.assignee_name.isnot(None)))
                if (v or "").strip() == after)
    out.problem = out.problem or sending_note(db)
    return out


def apply(db: Session, member: User, new: str, *, actor_user_id: int,
          expect: str = "", path: str = "", method: str = "") -> Plan:
    """계획대로 바꾼다 — **커밋하지 않는다**(부르는 쪽이 한 트랜잭션으로 커밋한다).

    `expect` 는 미리보기의 지문이다. 다르면(그 사이 줄이 늘었거나 다른 사람이 바꿨다)
    바꾸지 않는다 — 미리 본 것과 다른 것을 바꾸면 미리보기가 아무 뜻이 없다.
    """
    p = plan(db, member, new)
    if p.problem:
        raise RenameRefused(p.problem)
    if expect != p.fingerprint:
        raise RenameRefused("미리 본 뒤 바뀐 것이 있습니다 — 다시 확인해 주세요")
    old = sheet_owner.real_name(member)
    db.flush()   # 이 일과 상관없는 것이 아래 한 판에 섞여 줄마다 남지 않게

    def keep_stamps(session, _ctx, _instances):
        # 이름만 따라 바뀐 줄은 `수정한 날짜` 를 그대로 둔다(머리말). 값을 그대로 실어
        # 보내면 `onupdate` 가 새 시각을 찍지 않는다. `sheet_owner.rename` 이 안에서
        # flush 하므로 flush 마다 건다.
        for obj in session.dirty:
            if obj is not member and hasattr(obj, "updated_at"):
                flag_modified(obj, "updated_at")

    with edit_log.one_line():
        db.info[company_sync.NO_FOLLOW] = True
        event.listen(db, "before_flush", keep_stamps)
        try:
            member.name = p.after
            for before, after in p.tabs:
                try:
                    sheet_owner.rename(db, before, after)
                except sheet_owner.RenameError as exc:
                    raise RenameRefused(str(exc)) from exc
            if old:
                for model, _title, _key_ in ASSIGNEE_COLUMNS:
                    equal, history = _assignee_hits(db, model, old)
                    for row in equal:
                        row.assignee_name = p.after
                    for row in history:
                        row.assignee_name = _swap(row.assignee_name, old, p.after)
            db.flush()
        finally:
            event.remove(db, "before_flush", keep_stamps)
            db.info.pop(company_sync.NO_FOLLOW, None)
    edit_log.log_account_rename(
        db, actor_user_id=actor_user_id, member_id=member.id, before=p.before,
        after=p.after, tabs=p.tabs,
        counts={c["key"]: c["equal"] + c["history"] for c in p.columns},
        path=path, method=method)
    return p
