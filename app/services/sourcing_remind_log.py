"""딜 소싱 — **월간 리마인드를 언제 보냈나.** (#14)

딜 소싱 표의 `8월 리마인드` · `9월 리마인드` · `10월 리마인드` 칸. 줄마다 그
달 그 분께 월간 리마인드가 나간 시각을 적고, 자동화가 보낸 것인지(`자동`)
사람이 딜 제안 관리에서 보낸 것인지(`수동`)를 붙인다 — `10/2 14:05 자동`.
한 달에 여러 번이면 보낸 차례대로 여러 줄이다.

이 달 `딜 받음`(`sourcing_receipts` — 받은 쪽)과 짝이 되는 **보낸 쪽**이다.
그 표와 섞지 않고 따로 둔 까닭: `딜 받음` 은 사람이 누르고 메일 확인이
세우는 **우리 표**(`sourcing_receipts`)이고, 이것은 발송 기록(`send_items`)을
읽기만 하는 것이라 적는 곳도 지우는 곳도 없다.

## 무엇을 '보냈다' 로 치나 — 이 파일에 없다

`automation_dedup.sourcing_remind_sent` 한 벌을 그대로 쓴다. 자동 리마인드는
그 달 손으로 보낸 분을 그 조건으로 빼므로(`manual_sourcing_remind`), 이 칸에
`수동` 이 선 분은 그 달 자동이 안 나간다 — 둘이 같은 조건을 지나야 그 말이
참이다. `자동` · `수동` 을 가르는 것도 그쪽 `auto_items`(자동화가 세운 건)다.

  · 보낸 것만 — 실패 · 대기 · 취소는 안 보인다(받는 쪽에 아무것도 안 갔다).
  · 처음 안내 · Series A 딜 공유는 안 보인다 — 같은 잡 종류지만 다른 글이다.
  · 시험 모드로 보낸 것은 안 보인다 — 시험방으로 갔고, 받는 줄을 가리키지
    않는다(`automation.build_job`).

## 시각

저장된 글자 그대로 읽는다(`clock.now_iso` — 지역 시각, 한국 시간). 달을 가르는
것도 그 글자의 앞 7자다 — 중복 막기가 '그 달' 을 가르는 것과 같은 셈이라, 한
건이 표에서는 9월인데 중복 막기에서는 10월로 읽히는 일이 없다. 화면 글자는
이 화면의 메일 확인 줄(`마지막 10/15 18:00`)과 같은 꼴이다(`sourcing_mail.stamp`).

## 질의는 표 전체에 한 번

줄마다 묻지 않는다 — 석 달 치 리마인드 건을 한 번에 읽어 사람별 · 달별로
나눈다. 줄 번호 목록으로 거르는 것은 파이썬에서 한다: 석 달 치 리마인드는
명단 수 × 두어 번이라 작고, `전체` 탭의 수백 줄을 `IN (…)` 으로 늘어놓을
까닭이 없다.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Dict, Iterable, List, Optional, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import clock
from ..models import SendItem, SendJob
from . import automation_dedup, report, sourcing_mail

#: 표에 세우는 달 수 — 이 달과 그 앞 두 달(사용자 결정 2026-10-16).
MONTHS = 3

#: 표시 — 자동화가 세운 건(`automation_sends.item_id`)이면 `자동`, 아니면 `수동`.
AUTO = "자동"
MANUAL = "수동"


@dataclass(frozen=True)
class Month:
    """머리글 한 칸 — `10월 리마인드`."""

    key: str        # `2026-10` — 저장된 시각 글자의 앞 7자와 견준다
    label: str      # `10월 리마인드`
    title: str      # 머리글 풍선말 — 해까지 적는다


@dataclass(frozen=True)
class Sent:
    """나간 리마인드 한 건."""

    at: str         # 저장된 시각 그대로(`2026-10-02T14:05:00+09:00`)
    auto: bool

    @property
    def when(self) -> str:
        """`10/2 14:05` — 이 화면의 다른 시각과 같은 꼴(`sourcing_mail.stamp`)."""
        return sourcing_mail.stamp(self.at)

    @property
    def how(self) -> str:
        return AUTO if self.auto else MANUAL


def months(today: Optional[date] = None) -> List[Month]:
    """표에 세울 달 — **오래된 달이 왼쪽**(`8월` `9월` `10월`).

    달을 거슬러 세는 것은 업무 보고의 규칙 하나(`report.recent_months`)를
    지난다 — 해가 바뀌는 자리(1월이면 `11월` `12월` `1월`)를 두 곳에 적으면 그
    한 달에 한쪽만 틀린다.

    **머리글에 해를 붙이지 않는다.** 석 달은 늘 이 달에서 끝나는 잇닿은 달이라
    같은 `N월` 이 두 번 설 일이 없다 — 1월에 선 `12월` 은 지난해 12월일 수밖에
    없다. 대시보드가 해를 붙이는 것(`dashboard.monthly_reactions`)은 열두 달을
    세우는 자리라 `12월` 이 둘일 수 있어서다. 그래도 헷갈릴 때를 위해 풍선말에는
    해까지 적는다.
    """
    today = today or clock.today()
    out: List[Month] = []
    for year, mon in reversed(report.recent_months(today, MONTHS)):
        out.append(Month(
            key=f"{year:04d}-{mon:02d}",
            label=f"{mon}월 리마인드",
            title=(f"{year}년 {mon}월에 이 분께 월간 리마인드가 나간 시각 — "
                   f"{AUTO}: 자동화가 보냄 · {MANUAL}: 딜 제안 관리에서 사람이 보냄"),
        ))
    return out


def history(db: Session, contact_ids: Iterable[int],
            shown: Sequence[Month]) -> Dict[int, Dict[str, List[Sent]]]:
    """사람(딜 소싱 줄 번호) → 달(`2026-10`) → 그 달 나간 리마인드(보낸 차례).

    리마인드가 하나도 없는 사람 · 달은 열쇠가 없다 — 화면은 빈 칸을 그린다.
    질의는 한 번이다(이 파일 머리말).
    """
    wanted = {int(cid) for cid in contact_ids if cid}
    if not wanted or not shown:
        return {}
    auto = SendItem.id.in_(automation_dedup.auto_items()).label("auto")
    rows = db.execute(
        select(SendItem.sourcing_contact_id, SendItem.sent_at, auto)
        .join(SendJob, SendJob.id == SendItem.job_id)
        .where(SendItem.sourcing_contact_id.isnot(None),
               *automation_dedup.sourcing_remind_sent(shown[0].key, shown[-1].key))
        .order_by(SendItem.sent_at, SendItem.id)
    ).all()
    out: Dict[int, Dict[str, List[Sent]]] = {}
    for contact_id, sent_at, is_auto in rows:
        if contact_id not in wanted:
            continue
        out.setdefault(contact_id, {}).setdefault(sent_at[:7], []).append(
            Sent(at=sent_at, auto=bool(is_auto)))
    return out
