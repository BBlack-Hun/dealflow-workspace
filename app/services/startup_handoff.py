"""투자컨설턴트 줄을 **스타트업 명단에 세우는** 일 — 규칙이 정해지는 한 곳.

## 이것은 `sheet_owner.move_to` 가 아니다

`move_to` 는 **이관**이고, 그 주석이 이관을 한 문장으로 못 박아 두었다 —
*"이관은 **누가 맡는지**를 바꾸는 일이지 화면을 옮기는 일이 아니다."* 그래서
그 길은 줄 하나를 옮기되 **같은 화면 안에서만** 옮기고(`transfer_targets(page=…)`
· `routers/contacts.transfer_contact` 의 `다른 화면의 명단으로는 넘길 수
없습니다`), 옛 명단에서 뺀다.

여기서 하려는 일은 그것이 아니다.

  · 두 화면이 **같은 표를 쓰지 않는다.** 투자컨설턴트는 `ConsultingCompany`,
    스타트업은 `VcContact` 다. 옮길 `source_sheet` 자체가 없다.
  · **원본을 빼지 않는다.** 그 줄에는 월별 리마인드 기록과 계약 칸이 붙어
    있고(`ConsultingColumn`), 컨설턴트는 계속 그 표에서 그 기업을 본다.

그래서 **다른 말을 쓴다** — `이관` 이 아니라 `스타트업 명단으로 보내기` 다.
같은 말을 쓰면 다음 사람이 `move_to` 를 찾아 읽고는 옛 명단에서 빠진 줄 안다.

## 줄을 세우는 길은 새로 안 판다

`POST /api/contacts`(`routers/contacts.create_contact`)를 **그대로 부른다.**
그 길은 이미 세 가지를 지난다 — 넣어도 되는가(`sheet_owner.may_add_row`) ·
무엇이 반드시 있어야 하는가(`Layout.required`) · 담당은 누구인가
(`sheet_owner.owner_for`). 여기서 `VcContact(...)` 를 직접 만들면 그 셋이
두 벌이 되고, 한쪽만 고쳐지는 날 **이 길로 들어온 줄만** 담당이 비거나
기업명 없이 선다.

수정 로그도 같은 이유로 손대지 않는다. `services/edit_log.py` 가 세션 flush
에서 INSERT 를 잡으므로(`vc_contacts` 는 지켜보는 표다), 줄이 그 길로 들어가는
한 저절로 남는다.

## 무엇이 어느 칸에 들어가나

**두 배치의 머리글이 같은 뜻으로 쓰는 칸만** 옮긴다. 그 목록은 내가 정한 것이
아니라 `services/contact_columns.py` 첫머리에 이미 적혀 있다:

    field  VcContact 의 칸 (`firm`·`name`·`phone`·`email`·`memo`)
           투자사와 스타트업이 **같은 뜻으로** 쓰는 값이다.

그래서 아래 `contact_body` 가 채우는 것은 그 다섯 칸뿐이다. 특히 `firm` 과
`name` 이 뒤바뀌지 않게 조심한다 — 스타트업 배치는 **기업이 주인공**이라
`required="firm"`(`기업명`)이고 `name` 은 `성함`(기업 쪽 사람)이다. 투자사
배치와 반대다.

**O/X 칸들(`견적서 첨부 여부`·`계약완료여부`·`계약서 수신완료여부`·`카톡 연결
여부`)은 안 옮긴다.** 이름이 닮았다고 옮기면 같은 사실을 적는 자리가 하나 더
늘어난다 — `models.IrCompany.contract_received` 주석이 그 물음을 적는 칸이 이미
셋이고 **값을 주고받지 않는다**고, 왜 아직 하나로 못 모으는지와 함께 적어
두었다. 여기서 한 번 베껴 넣으면 그 뒤로 두 화면이 조용히 갈라지고, 보는
사람은 어느 쪽이 최신인지 알 수가 없다. 그 셋을 잇는 일은 사람이 규칙을 정해야
하는 일이지 이 판에서 곁다리로 할 일이 아니다.

월별 리마인드 칸도 안 옮긴다. 저쪽 칸은 **탭마다 한 벌**(`ConsultingColumn`)
이고 이쪽 칸은 **명단마다 한 벌**(`ContactColumn`)이라, 칸끼리 짝이 없다 —
짝을 지으려면 `9월 리마인드 문자` 라는 글자를 맞춰야 하는데 그것은 이름으로
가르는 짓이다(이 저장소가 반복해 당한 부류).
"""
from __future__ import annotations

from typing import Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import ConsultingCompany, VcContact
from . import contact_columns, sheet_owner
from .deal_history import _key as compare_key
from .room_name import normalize_space

#: `company_name` 한 칸에 여러 값이 들어 있을 때의 구분자.
#: 아래 `company_name_of` 주석에 실제 값의 모양을 세어 적어 두었다.
VALUE_SEP = "/"


def company_name_of(value: Optional[str]) -> str:
    """`ConsultingCompany.company_name` 에서 **기업명만** 꺼낸다.

    모델 주석이 이 칸을 `기업명/계약일/무료유료/계약금, 성과수수료 %` 라고
    적어 두었다 — 한 칸이 아니다. 개발 DB 의 57줄을 세어 본 모양은 이렇다.

        52줄   기업명 하나뿐(구분자 없음)
         3줄   `기업명\\n9.19/ 유료/\\n계약금/ 3.3%`  — **첫 줄이 기업명**
         2줄   `기업명 / 무료 / 3%`                  — 첫 조각이 기업명

    그래서 규칙은 둘뿐이다: **첫 줄을 잡고, 첫 `/` 앞을 잡는다.** 순서가
    중요하다 — `/` 를 먼저 자르면 위 3줄짜리에서 둘째 줄의 날짜가 기업명에
    붙어 온다.

    `월간 계약 업무현황표` 탭은 이미 같은 줄을 칸마다 나눠 담아 두었고
    (`routers/consulting.split_contract_line` · 0040 마이그레이션) 그 순서도
    **시트가 스스로 머리글로 적어 둔 것**이다. 여기서 하는 일은 그중 맨 앞
    조각을 집는 것뿐이라 규칙을 새로 짓지 않는다.

    **못 꺼내면 통째로 넣지 않는다 — 원문 그대로 둔다.** 이름에 `/` 가 든
    기업이 있으면 잘린 이름이 들어갈 수 있는데, 그때 고칠 자리는 스타트업
    화면의 `기업명` 칸이고 **원본은 투자컨설턴트 표에 그대로 남아 있다.**
    반대로 통째로 넣으면 `기업명` 칸에 계약금과 보수율이 같이 서서, 그 명단의
    주인공 칸이 통째로 읽을 수 없게 된다(그 칸은 표에서 고정으로 붙어 다니는
    칸이다 — `Layout.sticky`).
    """
    head = (value or "").replace("\r\n", "\n").split("\n", 1)[0]
    return normalize_space(head.split(VALUE_SEP, 1)[0])


def contact_body(company: ConsultingCompany) -> Dict[str, str]:
    """**칸 짝짓기 표.** 투자컨설턴트 줄 하나 → `POST /api/contacts` 의 몸통.

        company_name  →  firm   `기업명`   ← 이 명단이 줄을 알아보는 이름
        ceo_name      →  name   `성함`
        phone         →  phone  `연락처`
        email         →  email  `이메일`
        management    →  memo   `메모 ( 통화내용 / 카톡내용 / 카톡답신내용)`

    **`firm` 과 `name` 이 투자사 배치와 반대다.** 스타트업 배치는 기업이
    주인공이라 `required="firm"` 이고(`STARTUP_LAYOUT`), `성함` 은 그 기업
    쪽 사람이다. 반대로 넣으면 기업명 칸에 대표자 이름이 앉아, 표의 고정
    칸에 사람 이름만 줄줄이 선다.

    `management` → `memo` 는 **둘 다 자유 문장 기록**이고(`관리 중 : 미팅 완.
    -> 견적서 보내기 완료.`), 받는 칸도 여러 줄 메모다(`kind="long"`).
    `contact_columns` 첫머리가 `memo` 를 두 배치가 같은 뜻으로 쓰는 칸으로
    꼽아 둔 그 칸이다.

    **`sheet` 는 여기서 안 정한다.** 어느 명단으로 보낼지는 사람이 화면에서
    고르는 값이라 부르는 쪽이 싣는다.
    """
    return {
        "firm": company_name_of(company.company_name),
        "name": normalize_space(company.ceo_name or ""),
        "phone": normalize_space(company.phone or ""),
        "email": normalize_space(company.email or ""),
        # 줄바꿈이 뜻을 가진 칸이라 `normalize_space` 를 안 태운다 —
        # 받는 칸이 여러 줄 메모다.
        "memo": (company.management or "").strip(),
    }


def target_sheets(db: Session) -> List[dict]:
    """보낼 수 있는 **스타트업 명단** 목록 — 사람이 여기서 하나 고른다.

    목록을 새로 만들지 않는다. `sheet_owner.transfer_targets` 가 이미
    **담당이 정해진 명단만** 내주고 `page` 로 화면까지 좁혀 준다 — 그 함수가
    화면 탭(`sheet_rows`)을 안 쓰는 이유까지 거기 적혀 있다(탭은 지금 보이는
    사람으로 세어 만들어서, 정작 보낼 상대의 명단이 목록에 없다).

    **담당이 없는 명단은 애초에 안 뜬다.** 거기 줄을 세우면 그 줄의 담당을
    아무도 정한 적이 없는 상태가 되어 어느 팀원 화면에도 안 뜬다
    (`sheet_owner.owner_for` · `managed`).
    """
    return sheet_owner.transfer_targets(db, page=contact_columns.PAGE_STARTUP)


def startup_labels(db: Session) -> set:
    """스타트업 **화면에 사는** 명단 이름들.

    이름으로 고르지 않는다(`스타트업` 으로 시작하는 명단…). 명단이 어느
    화면에 사는지는 배치가 정한다 — `sheet_owner.page_of` 한 곳이다.
    """
    return {label for label, row in sheet_owner.settings_map(db).items()
            if contact_columns.page_of(row.layout or contact_columns.DEFAULT)
            == contact_columns.PAGE_STARTUP}


def existing_firms(db: Session) -> Dict[str, int]:
    """**이미 스타트업 명단에 서 있는 기업** — 비교용 이름 → 그 줄 번호.

    비교 규칙을 새로 짓지 않는다. `deal_history._key` 가 이 저장소에서
    기업 이름을 맞추는 그 규칙이고(`(주)`·띄어쓰기·대소문자를 지운다),
    `llm_brief.sent_before` 와 `/deals` 의 `최근에 소개함` 표시가 이미 그것을
    부른다. 두 벌로 적으면 화면의 `이미 있음` 표시와 서버의 건너뛰기가 갈려서,
    표에는 아무 표시가 없는데 눌러도 안 들어가는 줄이 생긴다.

    **부분일치로 찾지 않는다** — `가나` 는 `가나다라전자` 한가운데에 우연히
    박힌다(`services/company_names.py` 가 같은 이유로 목록을 안 본다).
    맞추는 것은 비교용 이름이 **통째로 같을 때**뿐이다.
    """
    labels = startup_labels(db)
    out: Dict[str, int] = {}
    if not labels:
        return out
    rows = db.execute(
        select(VcContact.id, VcContact.firm, VcContact.source_sheet)).all()
    for row_id, firm, source in rows:
        key = compare_key(firm)
        if not key or key in out:
            continue
        if not set(sheet_owner.labels_of(source)) & labels:
            continue
        out[key] = row_id
    return out


def is_in_startup(existing: Dict[str, int],
                  company: ConsultingCompany) -> bool:
    """이 투자컨설턴트 줄의 기업이 **이미 스타트업 명단에 있는가.**

    `existing` 은 `existing_firms` 가 한 번 떠 온 것이다 — 줄마다 부르면
    쉰 줄짜리 탭에서 쉰 번 조회가 나간다(`grant_owner_ids` 가 같은 이유로
    부르는 쪽에서 한 번 뜬다).

    **표의 `있음` 표시와 서버의 건너뛰기가 이 함수 하나를 읽는다.** 두 벌로
    적으면 표에는 아무 표시가 없는데 눌러도 안 들어가는 줄이 생긴다 — 이
    저장소가 반복해 당한 부류다.
    """
    key = compare_key(company_name_of(company.company_name))
    return bool(key) and key in existing
