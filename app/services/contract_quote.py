"""계약 완료면 `견적서 첨부 여부` 를 `O` 로 — IR 기업 현황 · 투자컨설턴트(i255 · 11/13).

팀원 요청: "IR 기업현황 > 계약여부 칼럼에서 계약완료이면 견적서 첨부여부에 O 자동으로
기입되게, 투자컨설턴트 메뉴에서도 동일하게 적용해 주세요".

## 무엇을

계약여부가 **계약 완료(무료 · 유료)로 적히는 순간** 그 줄의 견적서 첨부 여부가 비어 있으면
`O` 를 적는다. 계약 완료는 `무료계약완료` · `유료계약완료` 둘이다(`contract_day7.DONE` —
계약년월 · 계약 Day7 이 보는 그 둘). 운영에서 견적서 칸이 찬 계약 완료 줄은 무료 · 유료
모두 전부 `O` 였다(11/13 — `X` 0줄). `계약진행중` · 무료 IR 미팅 단계는 아니다.

    IR 기업 현황   계약여부 `contract_status`   →  견적서 첨부 여부 `quote_attached`
    투자컨설턴트   계약여부 `contract_done`     →  견적서 첨부 여부 `contract_management`
                   (관리 스타트업 탭만 — 두 칸이 그 탭에만 선다, `company_sync.slot`)

## 규칙

· **빈칸만 채운다.** 사람이 적은 `X` 는 그대로 둔다 — 그 줄을 아는 사람이 적은 값이다.
· 고치는 길이 어디든(IR 화면 · 투자컨설턴트 화면 · 시트 올리기 · 다른 표에서 따라 고친
  계약여부) flush 한 자리에서 한다 — 이 저장소의 관례(`company_sync` 머리말).
· 새 줄도 같다 — 계약 완료로 만든 줄의 빈 견적서 칸에 `O`. 계약년월(`contract_day7`)과
  달리 날짜가 아니라 사실이라, 옛 계약이어도 맞는 값이다.
· 이어진 줄(같은 IR 기업)로 가는 것은 따라 고치기가 한다 — 이 자리는 `company_sync` 뒤에
  돌아서 `follow_late` 가 이어진 줄의 **빈칸만** 마저 채운다(`models._stamp_contract_done`).
· 이미 계약 완료인데 비어 있던 줄은 저절로 안 채운다 — 한 번 채우는 일은 스크립트가
  같은 `fill` 을 부른다.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import get_history

from ..models import ConsultingCompany, IrCompany

FIELD = "quote_attached"
MARK = "O"
#: 투자컨설턴트 줄의 탭 기본값(`models.ConsultingCompany.sheet`).
_DEFAULT_SHEET = ConsultingCompany.__table__.c.sheet.default.arg


def _done(value) -> bool:
    from ..routers.companies import contract_key   # 순환 import 를 피해 늦게 부른다
    from .automations.contract_day7 import DONE

    text = str(value or "").strip()
    return bool(text) and contract_key(text) in DONE


def place(row, kinds: Dict[str, str]) -> Optional[Tuple[str, str]]:
    """이 줄의 (계약여부 칸, 견적서 칸). 두 칸이 없는 줄이면 None."""
    if isinstance(row, IrCompany):
        return "contract_status", FIELD
    if isinstance(row, ConsultingCompany):
        from . import consulting_sheets as cs

        # 두 칸은 관리 스타트업 탭에만 선다(`company_sync.slot` 과 같은 규칙). 시트 올리기로
        # 새로 선 줄은 flush 전이라 탭 기본값이 아직 안 들었다 — 넣을 때 들 값으로 본다.
        sheet = row.sheet if row.sheet is not None else _DEFAULT_SHEET
        return ("contract_done", "contract_management") \
            if kinds.get(sheet) == cs.STARTUP else None
    return None


def fill(row, kinds: Dict[str, str]) -> bool:
    """계약 완료인 줄의 **빈** 견적서 칸에 `O` — 적었으면 True(커밋은 부르는 쪽)."""
    found = place(row, kinds)
    if found is None:
        return False
    contract, quote = found
    if not _done(getattr(row, contract)) or str(getattr(row, quote) or "").strip():
        return False
    from . import company_sync

    company_sync._set(row, quote, MARK)   # 투자컨설턴트 줄은 `수정한 날짜` 도 같이 찍는다
    return True


def before_flush(session: Session) -> List:
    """이번 flush 에서 계약여부가 **계약 완료로 적힌** 줄의 빈 견적서 칸을 채운다.

    채운 줄을 돌려준다 — 부르는 쪽이 이어진 줄에 마저 적는다(`company_sync.follow_late`).
    """
    rows = [o for o in list(session.new) + list(session.dirty)
            if o not in session.deleted and (
                (isinstance(o, IrCompany) and get_history(o, "contract_status").added)
                or (isinstance(o, ConsultingCompany) and get_history(o, "contract_done").added))]
    if not rows:
        return []
    from . import company_sync

    # 탭 종류는 투자컨설턴트 줄이 있을 때만 읽는다(IR 시트 올리기는 기업마다 flush 한다).
    kinds = (company_sync.sheet_kinds(session)
             if any(isinstance(r, ConsultingCompany) for r in rows) else {})
    return [r for r in rows if fill(r, kinds)]
