"""이어진 IR 기업의 칸을 **읽기만** 하는 묶음 — 투자컨설턴트(#83) · 스타트업 명단(#85).

10/28 담당자 '추천대로': 그 칸들을 다른 표에 한 벌 더 저장하지 않고, 줄에 이어 둔 IR 기업
(`ir_company_id` — `services/ir_link.py`)의 값을 그때그때 읽어 보여 준다. 값은 IR 기업 현황
한 곳에 있어 두 벌이 갈릴 일이 없고, **고치는 곳은 IR 기업 현황**이다. 안 이은 줄은 빈칸이다.

칸 이름 · 차례 · 폭은 IR 기업 현황 표(`companies.html`) 그대로다 — 연도 매출 · 금액은
`revenue_years.columns` 가 해마다 이름을 짓는다.

빼는 칸:
  · 수신일 — 빼 달라는 요청이다(#83).
  · 대표자명 · 연락처 · 이메일 · 지역(투자컨설턴트) · 계약 칸 · 견적서 · 카톡 연결 — 그 표에
    제 칸이 있고 이미 서로 따라 고친다(`company_sync.FIELDS`). 같은 이름 칸이 두 번 서면
    어느 쪽을 고쳐야 하는지 헷갈린다.
  · 소개 횟수 · 수정한 날짜 · 수정한 팀원 — IR 줄의 발송 · 수정 기록이지 기업 칸이 아니다.
  · 담당자 — 투자컨설턴트 표의 `담당`(그 줄을 맡은 컨설턴트)과 같은 말로 읽힌다.
  · 성공보수율 — 투자컨설턴트에서는 계약 탭에만 서는 칸이다(그 탭과 따라 고친다).
"""
from __future__ import annotations

from typing import Dict, Iterable, List

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import IrCompany
from . import revenue_years
from .contact_columns import Column

#: 금액 칸의 폭(나머지 연도 매출은 74px) — IR 기업 현황 표 그대로.
_AMOUNT_WIDTH = {"revenue_recent": 108, "funding_total": 96, "raise_target": 120,
                 "pre_value": 76}
#: 두 줄까지 보이는 긴 글 칸.
_LONG = {"business_desc", "one_liner", "competitiveness", "guarantee"}
#: 스타트업DB 탭의 금액 뒤 넷(#85 요청 차례).
_STARTUP_TAIL = [("competitiveness", "특이사항 (장점)", 260), ("founded_year", "설립년도", 72),
                 ("region", "지역", 80), ("guarantee", "정책자금", 130)]
#: IR 기업 현황 탭의 금액 뒤(투자라운드 ~ IR 자료).
_IR_TAIL = [("series", "투자라운드", 150), ("one_liner", "딜 소개 문구", 300),
            ("meeting_offered_at", "미팅제공일자", 110), ("contract_month", "홍보메일삭제", 110),
            ("top_deal_kind", "핵심/TOP Deal", 110), ("ir_file_name", "IR 자료", 102)]


def _col(key: str, label: str, width: int) -> Column:
    # `source="ir"` — 표에서 `class="cell"` · `data-field` 를 안 받는다(눌러도 안 열린다).
    return Column(label, key, width, source="ir", kind="long" if key in _LONG else "text")


def _amounts() -> List[Column]:
    return [_col(f, label, _AMOUNT_WIDTH.get(f, 74)) for f, label in revenue_years.columns()]


def startup_columns() -> List[Column]:
    """스타트업 명단 `이메일` 오른쪽(#85) — 연도 매출 · 금액 넷 · 특이사항 · 설립년도 · 지역 · 정책자금."""
    return _amounts() + [_col(*c) for c in _STARTUP_TAIL]


def consulting_columns() -> List[Column]:
    """투자컨설턴트 `이메일` 오른쪽(#83) — IR 기업 현황의 칸(수신일 · 그 표에 있는 칸 빼고)."""
    return ([_col("business_desc", "기업 한줄 소개", 300), _col("sector_major", "대분류", 110),
             _col("sector_minor", "소분류", 110)]
            + _amounts()
            # 지역은 투자컨설턴트 표에 제 칸이 있다(따라 고치는 칸).
            + [_col(*c) for c in _STARTUP_TAIL if c[0] != "region"]
            + [_col(*c) for c in _IR_TAIL])


def _text(company: IrCompany, key: str) -> str:
    value = getattr(company, key, None)
    if key == "ir_file_name":
        return "있음" if (value or "").strip() else "없음"
    return str(value).strip() if value is not None else ""


def values(db: Session, ids: Iterable) -> Dict[int, Dict[str, str]]:
    """`{IR 기업 id: {칸: 보일 글자}}` — 이어진 IR 기업만, 한 번에 읽는다."""
    want = {int(i) for i in ids if i}
    if not want:
        return {}
    keys = {c.key for c in consulting_columns() + startup_columns()}
    rows = db.execute(select(IrCompany).where(IrCompany.id.in_(want))).scalars()
    return {c.id: {k: _text(c, k) for k in keys} for c in rows}
