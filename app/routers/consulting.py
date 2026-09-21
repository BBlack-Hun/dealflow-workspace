"""투자컨설턴트 현황 — 구글시트를 그대로 옮긴 표.

원본 시트를 여러 사람이 같이 고치다 보니 어디까지 반영됐는지 알기 어려웠다.
여기로 옮겨 **한 곳에서 고치고, 누가 언제 고쳤는지 남게** 한다.

정해진 사람만 보는 화면이다 — 누가 볼 수 있는지는 `deps.may_view_consulting`
한 곳에서 정한다(관리자 · 투자컨설턴트 · 관리자가 켜 준 팀원).
대표자 연락처·이메일이 들어 있어서 팀 전체에 열어 둘 표가 아니다.

시트의 값은 대부분 자유 문장이다 — 미팅일이 `9/16 PM2 (화상미팅)` 처럼 적혀 있다.
형식을 강제하면 원본을 옮길 수 없으므로 그대로 문자열로 받는다.

월별 리마인드 열(`8월 마지막주 리마인드 톡 or TEL` …)은 달마다 하나씩 늘어난다.
테이블 컬럼으로 두면 매달 마이그레이션을 해야 하므로 행으로 두고,
내용은 기업 행의 JSON 에 담는다.
"""
from __future__ import annotations

import json
import re
from typing import Dict, List, Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import clock
# 저장된 시각 글자를 **화면 꼴로 줄이는 자리는 여기 한 곳**이다
# (`app/clock.py` 의 `stamp_text`). 화면이나 브라우저에서 다시 자르면 같은
# 값이 두 꼴로 보인다 — IR 기업 현황·스타트업 명단이 같은 함수를 부른다.
from ..clock import stamp_text
from ..db import get_db
from ..deps import (NoConsulting, can_open, get_current_user,
                    may_view_all_consulting, may_view_consulting, templates)
from ..models import (ConsultingColumn, ConsultingCompany, ConsultingRowGrant,
                      User)
from ..services import consulting_sheets as cs
from ..services import consulting_status as status
from ..services import monthly_columns
from ..services import sheet_owner
from ..services import spreadsheet as sp
from ..services import startup_handoff
from ..ui import base_ctx, menu_label
# 계약을 부르는 말이 있는 곳. 여기에 다시 적지 않는다 —
# `CONTRACT_DONE_CHOICES` 주석 참고(`routers/pages.py` 도 같은 방식이다).
from .companies import CONTRACT_LABELS
# **줄을 새로 넣는 길은 저것 하나다.** 아래 `send_to_startup` 이 그대로 부른다 —
# 왜 여기서 `VcContact(...)` 를 만들지 않는지는 `services/startup_handoff.py`
# 첫머리에 적혀 있다.
from .contacts import ContactIn, create_contact

router = APIRouter(tags=["consulting"])

# 시트의 고정 열. (화면 표시 이름, 모델 속성)
FIXED_COLUMNS = [
    ("NO", "position"),
    ("지역", "region"),
    ("미팅일(화상, 회의실)", "meeting_at"),
    # 위 칸 머리글의 괄호가 **이 칸의 정체**다 — 시트가 처음부터 `미팅일` 과
    # `화상, 회의실` 두 가지를 한 칸에 적으라고 했고, 값이 `9/16 PM2 (화상미팅)`
    # 처럼 붙어 있었다. 자리를 갈라 세운다(사용자 요청: "미팅날짜 컬럼 옆에").
    #
    # **`미팅일` 의 글자는 안 지운다.** 이 저장소는 적힌 것을 고쳐 쓰지 않는다
    # (`split_contract_line` · `CONTRACT_COLUMNS` 의 `계약월` 이 같은 자리다).
    # 괄호를 읽어다 이 칸을 채우지도 않는다 — 아무 것도 안 적힌 줄이 더 많고,
    # 그 줄에 무엇을 넣어도 추측이다(0078).
    #
    # **계약 탭에는 안 선다.** 저 탭의 같은 저장 자리(`meeting_at`)는 `계약월`
    # 이라는 다른 물음을 받고 있어(값이 `미정`·`8`) 옆에 `미팅종류` 가 서면
    # 영영 안 채워지는 칸이 하나 는다. 그래서 `CONTRACT_COLUMNS` 에는 안 넣는다.
    ("미팅종류", "meeting_kind"),
    ("기업명 / 계약일 / 무료유료 / 계약금, 성과수수료 %", "company_name"),
    ("기업 관리 [ 드랍 이유 상세하게 기입 / 관리중 / 백업팀으로 전환 ]", "management"),
    # 바로 왼쪽 머리글의 **`드랍 이유 상세하게 기입`** 이 이 칸의 정체다
    # (사용자 요청: "기업관리 컬럼의 내용을 분리해서 기업 내용 컬럼을 신설").
    # 시트가 한 칸에 **상태**(관리중 · 드랍 · 백업팀 전환)와 **그 이유**를 같이
    # 적으라고 했고, 값이 `드랍 : 몇 차례 …` 처럼 `상태 : 상세` 꼴로 적혀 있다.
    #
    # 섞여 있으면 **칩·KPI·머리글 필터가 흔들린다** — 그 셋이 이 칸의 낱말로
    # 갈래를 세는데(`services/consulting_status.py`), 상세 글이 길어질수록
    # `관리`·`드랍` 이 우연히 들어가 엉뚱한 갈래에 걸린다. `딜 소개문구` 를
    # 이 칸에서 갈라낼 때 이미 적어 둔 이유다.
    #
    # **값을 옮기는 것은 여기가 아니다.** 칸만 서고(0079), 옮기는 일은 사람이
    # 확인하고 돌리는 스크립트가 한다
    # (`scripts/split_consulting_management.py`).
    #
    # **계약 탭에는 안 선다.** 저 탭의 같은 저장 자리(`management`)는
    # `계약여부`(`무료`/`유료`)라는 다른 물음이라 갈라낼 상세가 없다.
    ("기업 내용", "management_detail"),
]
TAIL_COLUMNS = [
    ("대표자", "ceo_name"),
    ("연락처", "phone"),
    ("이메일", "email"),
]

# 고르는 칸 `계약완료여부` 의 보기. **말은 이미 있는 곳에서 가져온다** —
# IR 기업 현황이 계약을 부르는 그 말이다(`routers/companies.py` 의
# `CONTRACT_LABELS`). 여기에 글자를 다시 적어 두면 한쪽에서 `무료계약완료` 를
# 고치는 날 두 화면이 서로 다른 말로 같은 것을 부르게 되고, 그때는 어느 쪽이
# 맞는지 알 수가 없다(`services/ir_monthly.py` 도 같은 이유로 저기서 가져온다).
#
# **담기는 칸은 그래도 따로다.** 저쪽은 `ir_companies` 의 기업 줄에 붙고
# 이쪽은 `consulting_companies` 의 컨설턴트 줄에 붙는데, 두 표를 잇는 열쇠가
# 없어서(기업명이 같다는 보장도 없다) 값을 끌어올 수가 없다. 가져올 수 있는
# 것은 **말**뿐이라 말만 가져온다(`models.ConsultingCompany.contract_done`).
#
# 넷 중 둘만 쓴다. 사용자가 부른 것이 `무료계약완료`·`유료계약완료` 두
# 가지이고, `계약검토중`·`미계약` 은 **아직 계약이 안 끝난 상태**라 이름이
# `계약완료여부` 인 칸에 설 값이 아니다. 그 상태는 **빈칸**(아직 안 정함)이
# 받는다 — 예전에는 옆 칸이 자유 글이라 거기에 적어 둘 수도 있었는데, 그 칸도
# `견적서 첨부 여부` 로 바뀌어 이제 `O`/`X` 만 받는다(아래 `STARTUP_COLUMNS`).
# 문장으로 적을 자리는 `기업 관리` 한 칸이다.
CONTRACT_DONE_CHOICES = (CONTRACT_LABELS["free"], CONTRACT_LABELS["paid"])

# 고르는 칸 `미팅종류` 의 보기. **여기가 이 말의 한 곳이다** — 위
# `CONTRACT_DONE_CHOICES` 는 같은 말이 `routers/companies.py` 에 이미 있어서
# 거기서 가져왔는데, 이 두 마디는 이 앱 어디에도 없던 말이다.
#
# **`services/pipeline.py` 의 `MEETING_MODES` 를 안 쓴다.** 그쪽도 "대면인가
# 화상인가" 를 묻지만 세 가지가 다르다.
#
#   · **부르는 말이 다르다.** 저기는 `대면`/`화상` 이고 여기는
#     `화상미팅`/`회의실 미팅` 이다 — 사용자가 고른 말이자 이 시트의 머리글이
#     쓰는 말이다(`미팅일(화상, 회의실)`). 저쪽 말을 끌어오면 시트에 없던
#     낱말이 이 표에 선다.
#   · **담기는 꼴이 다르다.** 저기는 `in_person`/`video` 라는 **열쇠**를 담고
#     화면에 보일 때만 옮겨 적는다. 이 표의 편집기는 칸에 보이는 글자를 그대로
#     보내므로(`static/js/consulting.js`) 말과 값을 갈라 두면 표가 보내는
#     글자가 어느 값에도 안 맞아 **조용히 안 저장된다**
#     (`routers/companies.py` 의 `CONTRACT_FROM_LABEL` 이 그 사고다).
#   · **담기는 표가 다르다.** 저기는 `meetings` 의 미팅 줄, 여기는
#     `consulting_companies` 의 컨설턴트 줄이고 둘을 잇는 열쇠가 없다
#     (`models.ConsultingCompany.kakao_joined` 주석이 같은 이야기를 한다).
#
# **빈칸이 셋째 값이다** — `아직 안 정함`. 세 번째 보기를 만들지 않는 것은
# 사용자가 두 가지로 적어 달라고 했고, 이 표의 다른 고르는 칸들이 이미 그
# 규칙이기 때문이다(머리글 필터가 `(비어 있음)` 으로 세워 준다).
MEETING_KIND_CHOICES = ("화상미팅", "회의실 미팅")

# `관리 스타트업` 탭에만 서는 칸들 — 전부 `기업 관리` **오른쪽**이다.
#
# 앞의 셋은 **견적서 첨부 여부 → 계약완료여부 → 계약서 수신완료여부**,
# 컨설턴트가 기업 하나를 붙들고 가는 흐름의 세 마디다(견적서를 보냈나 →
# 계약이 끝났나 → 서류는 왔나). 마지막 하나는 투자사에 그 기업을 어떻게
# 소개할지 적는 `딜 소개문구` 다.
#
# **첫 마디의 이름이 `계약관리` 에서 바뀌었다**(사용자 요청). 그 이름일 때는
# "계약이 어떻게 되고 있나" 라는 자유 글이었는데, 실제로 적히는 일이 한 줄도
# 없었다(128줄 중 0건). 물어야 할 것이 `견적서를 보냈는가` 하나로 정해지면서
# 뒤의 두 마디와 같은 `O`/`X` 칸이 됐다 — 그러자 세 마디가 `스타트업` 명단이
# 이미 세워 둔 차례와 같아졌다(`services/contact_columns.py` 의 `견적서 첨부여부`
# → `계약여부` → `계약서 수신여부`).
#
# **담기는 칸은 `contract_management` 그대로다.** 이름이 바뀌었다고 열쇠를
# 같이 바꾸면 이미 들어 있는 값이 통째로 끊긴다 — 지금은 비어 있어 잃을 것이
# 없지만, 이 저장소는 그 규칙을 이름마다 지킨다(`스타트업` 명단의
# `계약서 수신여부` 도 열쇠는 옛 이름 그대로 둔 자리다 —
# `services/contact_columns.py` 의 `STARTUP_LAYOUT`). 이름과 열쇠가 어긋난 것은
# 알고 둔 것이니 "오타" 로 보고 고치지 마라.
#
# 넷 다 지금까지 옆 `기업 관리` 한 칸에 문장으로 섞여 있었다
# (`관리 중 : 미팅 완. -> 견적서 보내기 완료.`). 섞여 있으면 두 가지를 잃는다.
#
#   · **아직 안 한 곳**을 골라낼 수가 없다 — 적힌 것은 검색으로 찾아지지만
#     안 적힌 것은 안 찾아진다.
#   · `기업 관리` 는 그 값으로 칩·KPI 를 세는 칸이라
#     (`services/consulting_status.py`) 문장이 길어질수록 `관리`·`드랍` 같은
#     낱말이 우연히 들어가 그 줄이 엉뚱한 갈래에 걸린다.
#
# **`계약서 수신완료여부` 는 계약 탭의 `계약서 수신여부` 와 같은 칸이다**
# (`contract_received`). 묻는 사실이 하나뿐이라 — 계약서가 왔는가 — 칸을 새로
# 만들지 않았다. 뜻이 같은데 칸을 둘로 두면 같은 기업의 같은 사실이 두 군데에
# 갈린다. 탭마다 이름이 다른 것은 이 표에서 이미 하는 일이다(같은 `meeting_at`
# 이 한 탭에서는 `미팅일`, 계약 탭에서는 `계약월` 이다).
#
# 다른 두 탭(`경영본부 전달 기업` · `월간 계약 업무현황표`)에는 나머지 셋을
# 안 세운다. 이 마디들은 아직 관리 중인 기업에 대고 쓰는 말이고, 계약 탭은
# 표 자체가 다르다. 그래서 `FIXED_COLUMNS` 에 넣지 않고 이 탭만의 묶음을 따로
# 둔다 — `FIXED_COLUMNS` 는 지금도 스타트업·경영본부 두 탭이 함께 쓴다.
STARTUP_COLUMNS = FIXED_COLUMNS + [
    # 견적서를 보냈는가. **`O`/`X` 를 골라 넣는다** — 아래 두 칸과 같은
    # 방식이다(화면의 `data-choices="O,X"` · 빈칸은 `아직 안 정함`).
    # 자유 글이 아니다: 값이 두 가지뿐인 칸을 손으로 적게 두면 같은 뜻이
    # `O`·`o`·`ㅇ`·`○` 로 갈려 머리글 필터가 못 쓰게 된다.
    #
    # 담기는 칸은 `contract_management` 그대로다(위 묶음 주석 참고).
    ("견적서 첨부 여부", "contract_management"),
    # 보기 둘 + 빈칸. 값은 `CONTRACT_DONE_CHOICES` 한 곳에서 온다.
    ("계약완료여부", "contract_done"),
    # 계약 탭과 **같은 칸**이다(이름만 탭이 정한다 — 위 참고).
    ("계약서 수신완료여부", "contract_received"),   # O / X
    ("딜 소개문구", "deal_pitch"),
    # 이 기업과 카톡방이 연결됐는가. **자리는 사용자가 정했다** — 이 묶음의
    # **맨 뒤**, `딜 소개문구` 다음이다. (처음에는 `IR 자료 회신여부` 앞이라고
    # 불렀는데 이 탭에는 그런 칸이 없어 자리를 다시 물었고, 한 번 `계약서
    # 수신완료여부` 뒤로 세웠다가 사용자가 `딜 소개문구` 다음으로 고쳐
    # 정했다. 그러니 계약 세 마디의 흐름에 낀 칸이 아니라 **그 뒤에 따로
    # 붙는 칸**이다.)
    #
    # 계약 세 마디와 같은 `O`/`X` 칸이다(빈칸은 `아직 안 정함`).
    #
    # **`VcContact.kakao_joined` 와 이름이 같지만 다른 표의 다른 칸이다.**
    # 한쪽에 `O` 를 넣어도 다른 쪽은 계속 비어 있다 — 같은 기업이 스타트업
    # 화면과 이 화면에서 다른 답을 보일 수 있고, 그것은 알고 둔 것이다.
    # 어디에 또 있고 왜 안 이었는지는 `models.ConsultingCompany.kakao_joined`
    # 주석에 한 곳으로 적혀 있다(설명을 두 벌 두면 한 벌이 낡는다).
    ("카톡 연결 여부", "kakao_joined"),   # O / X
]

# `월간 계약 업무현황표` 는 다른 두 탭과 **표 자체가 다르다.**
#
# 저 시트는 머리글 있는 표가 아니라 월 묶음 아래 슬래시 한 줄이었다
# (`scripts/import_consulting.py` 의 `parse_contract_sheet`). 그래서 다른 탭의
# 칸을 빌려 담았는데, 빌린 이름이 뜻과 어긋나 있었다 — `지역` 칸에 `6월` 이,
# `기업 관리` 칸에 `무료`/`유료` 가 들어 있고, 기업명·계약금·보수율·계약일
# 네 가지가 `기업명` 한 칸에 뭉쳐 있었다.
#
# 칸 이름을 시트가 부르는 대로 돌려놓고, 뭉쳐 있던 줄을 칸으로 나눈다.
# **머리글만 다르고 담기는 모델은 하나다** — 시트마다 테이블을 나누면 같은
# 성격의 줄이 두 곳에 흩어져 권한·필터·엑셀을 두 벌로 만들어야 한다.
#
# **`월` 칸은 화면에서 뺐다**(사용자 요청). 시트의 월 묶음 제목(`6월`·`누적`)이
# `region` 에 담겨 서 있던 칸인데, 바로 옆 `계약월`(`meeting_at`)이 같은 물음을
# 받고 있어 달을 적을 자리는 그대로 남는다.
#
# **값은 안 지운다.** `region` 은 `관리 스타트업` 탭의 `지역` 칸과 **같은 저장
# 자리**라, 비우는 손이 그 탭의 `지역` 까지 닿는다. 여기서 하는 일은 이 탭의
# 칸 목록에서 한 줄을 빼는 것뿐이다 — 계약 줄에 적혀 있던 달(`누적` 9 · `6월` 3
# · `7월` 2)은 DB 에 그대로 남고, 엑셀에도 계속 `지역` 머리글로 내려간다
# (`CONSULTING_EXPORT_HEADERS` 는 `FIXED_COLUMNS` 에서 뽑으므로 이 목록과
# 무관하다). 대표자·연락처·이메일을 화면에서만 뺀 것과 같은 방식이다.
CONTRACT_COLUMNS = [
    ("NO", "position"),
    # 시트 머리글은 `계약일` 이라고 적혀 있지만 **칸에 든 값은 날짜가 아니다.**
    # 실제 값은 `미정`(4줄)과 `8`(1줄) — `8` 은 8월이라는 뜻의 달 숫자다.
    # 이름이 `계약일` 이면 `2026-08-15` 같은 날짜를 적어야 하는 칸으로 읽혀,
    # 다음에 채우는 사람이 다른 모양의 값을 넣는다. **이름을 값에 맞춘다.**
    #
    # 값은 손대지 않는다. 뜻이 바뀐 것이 아니라 이름이 값을 잘못 부르고 있던
    # 것이고, `미정` 도 그대로 남아야 한다 — 이 저장소는 적힌 것을 고쳐 쓰지
    # 않는다(`split_contract_line` 참고).
    ("계약월", "meeting_at"),
    ("기업명", "company_name"),
    ("계약여부", "management"),   # 무료 / 유료
    # 계약을 맺은 것과 **계약서를 받은 것**은 다른 사실이다. 앞 칸에 섞어 두면
    # 계약은 했는데 서류가 아직 안 온 곳을 가려낼 수가 없다.
    # 빈칸은 `아직 안 정함` 이다(`models.ConsultingCompany.contract_received`).
    ("계약서 수신여부", "contract_received"),   # O / X
    ("성공보수율", "success_fee"),
    ("계약금", "contract_fee"),
]
# 대표자·연락처·이메일은 이 탭에서 **화면에만** 안 세운다. 계약 줄에는 원래
# 값이 없는 칸이라 자리만 먹는데, 값을 지우는 것은 다른 문제다 — 이 저장소는
# 이력을 함부로 지우지 않는다. 나중에 이 탭에도 담당자를 적게 되면 칸만
# 되살리면 그만이고, 지웠으면 되살릴 것이 없다.
CONTRACT_TAIL: List[tuple] = []


def require_access(user: User) -> None:
    """관리자이거나, 이 화면을 보도록 허용된 계정이어야 한다.

    **누가 볼 수 있는지는 `deps.may_view_consulting` 한 곳에서 정한다.** 여기에
    조건을 한 번 더 적어 두었더니 팀 현황 표가 보는 조건과 갈렸고, 컨설턴트
    줄에 `막힘` 이라고 뜨는데 실제로는 열려 있었다 — 표가 거짓말을 한 것이다.
    """
    if may_view_consulting(user):
        return
    # 무엇을 돌려줄지는 여기서 정하지 않는다 — 주소창이 여는 GET 이면 안내창이
    # 있는 화면, 스크립트가 부른 것이면 403. 관리자 전용(`NotAdmin`)이 이미
    # 그렇게 갈라 두었고, 그 판단은 `deps.consulting_block_response` 한 곳에
    # 있다. 이 화면은 API 가 열두 자리라, 자리마다 답을 적으면 하나는 낡는다.
    raise NoConsulting()


# 고르는 자리의 `담당 미배정`. 주인이 없는 줄(user_id NULL)을 고르는 값이다.
#
# **0 을 쓸 수 없다.** `owner` 는 안 고른 상태가 0(전체)이라, 미배정을 0 으로
# 두면 그 칩을 눌러도 전체가 나오면서 `전체` 칩까지 같이 눌린 것처럼 보인다 —
# 화면이 거짓말을 하는 자리다.
UNASSIGNED = -1


def scope(stmt, model, user: User, owner: int = 0):
    """이 사람이 **볼** 줄만 남긴다.

    이 화면은 컨설턴트 한 사람의 개인 표이면서, 그 표들을 모아 팀이 보는
    자리이기도 하다. 그래서 보는 범위가 둘로 갈린다 — 누가 어느 쪽인지는
    `deps.may_view_all_consulting` 한 곳이 정한다(여기에 역할을 다시 적으면
    메뉴·화면·라우터가 갈린다).

    - 컨설턴트  **자기 것만.** 남의 담당 기업이 보이면 안 되고, 각자 올린
                시트가 서로를 덮는다(월별 리마인드 열이 사람마다 다르다).
    - 그 외     관리자와 관리자가 켜 준 팀원. 두 사람의 표를 나란히 놓고 봐야
                하는 자리라 **전체**를 보고, `owner` 로 한 사람만 골라 본다.

    **보는 범위이지 고치는 범위가 아니다.** 팀원은 전체를 보되 자기 줄만
    고친다 — 고치는 판정은 `may_edit_row` 한 곳이다.

    주인이 없는 줄(user_id NULL)은 전체를 보는 사람에게만 보인다 — 배정해야
    할 것이 남아 있다는 뜻이라, 아무에게나 보이면 서로 자기 것인 줄 안다.
    """
    if not may_view_all_consulting(user):
        return stmt.where(model.user_id == user.id)
    if owner == UNASSIGNED:
        return stmt.where(model.user_id.is_(None))
    if owner:
        return stmt.where(model.user_id == owner)
    return stmt


def own(stmt, model, user: User):
    """**내 표 안**으로 좁힌다 — 보는 것이 아니라 손이 닿는 범위다.

    위 `scope()` 와 갈라 두는 이유가 있다. 팀원은 이제 팀 전체를 **보지만**,
    자기 열을 지우거나 시트를 올리는 일까지 전체에 닿으면 안 된다. 실제로
    그 자리다 — 열을 지우면서 표를 훑어 그 달 기록을 지우는데, 보는 범위로
    훑으면 자기 열을 지우는 것뿐인데 손이 남의 줄까지 닿는다.

    관리자는 여기서도 전체다. 관리자가 팀 전체를 고치는 것은 이 앱의 다른
    화면과 같은 규칙이다(`deps.may_manage_team_contacts`).
    """
    if user.role == "admin":
        return stmt
    return stmt.where(model.user_id == user.id)


def grant_owner_ids(db: Session, user: User) -> frozenset:
    """이 사람이 **누구의 줄**을 고쳐도 되는가 — 관리자가 준 것만.

    돌려주는 것은 줄 주인의 계정 번호들이다(`ConsultingRowGrant.user_id`).
    **판정이 아니라 자료다** — 고칠 수 있는지는 아래 `may_edit_row` 하나가
    답하고, 여기는 그 함수가 읽는 값을 떠 올 뿐이다.

    한 사람에 한 번만 묻게 해 둔다. 표를 그리는 자리는 줄마다 이 판정을
    부르는데(`company_rows`), 줄마다 조회를 열면 서른 줄짜리 탭에서 서른 번
    나간다 — 그래서 부르는 쪽이 한 번 떠서 `grants=` 로 넘긴다.
    """
    rows = db.execute(
        select(ConsultingRowGrant.user_id)
        .where(ConsultingRowGrant.editor_user_id == user.id)
    ).scalars().all()
    return frozenset(rows)


def may_edit_row(db: Session, user: User, owner_id: Optional[int],
                 *, grants: Optional[frozenset] = None) -> bool:
    """이 줄(또는 열)을 고칠 수 있는가 — **판정은 여기 한 곳이다.**

    화면이 `읽기 전용` 이라고 그리는 줄과 서버가 404 로 막는 줄이 **같아야**
    한다. 두 곳에 적으면 하나는 반드시 낡아서, 고칠 수 있게 그려 놓고 누르면
    `찾을 수 없습니다` 가 뜨거나(팀 현황의 담당자 칸이 그랬다) 반대로 못 고치는
    것처럼 그려 놓고 실제로는 고쳐진다. **넓힐 때도 여기만 넓힌다** — 새 판정
    함수를 만들어 라우터 여기저기서 부르면 그것이 곧 두 번째 규칙이다.

    관리자는 전부, 그 외에는 자기 줄과 **관리자가 맡겨 준 사람의 줄**이다.
    주인 없는 줄은 아무도 못 고친다 — 배정할 것이 남았다는 뜻이지, 먼저 본
    사람이 갖는 것이 아니다(맡기는 단위도 `사람` 이라 줄 자체는 못 맡긴다).

    ## 남의 줄을 여는 문에 `may_view_all_consulting` 을 그대로 태운다

    조건을 여기에 새로 적지 않고 **보는 판정을 그대로 읽는다.** 한 줄로 둘을
    한꺼번에 답하기 때문이다.

    · **못 보면 못 고친다.** 관리자가 팀 현황에서 `투자현황` 을 끄면 그 사람은
      이 화면에 못 들어온다(`require_access`). 그때 맡긴 것만 살아 있으면,
      막아 둔 줄 알았던 사람이 주소로 남의 줄을 계속 고친다 — 화면이 거짓말을
      하는 그 자리다. 맡긴 줄을 지우지는 않는다(다시 켜면 그대로 돌아온다).
    · **투자컨설턴트는 이 길로 남의 줄에 닿지 못한다.** 그 화면은 각자의 개인
      표이고 서로를 덮는다(`deps.may_view_all_consulting` 의 설명). 맡겨 준
      줄이 있어도 여기서 먼저 끊긴다.

    반대쪽 — `맡겼는데 화면을 못 봐서 아무 소용이 없는` 상태 — 는 **주는
    자리**가 막는다. 팀 현황의 고르는 칸은 이 함수에 두 번 물어(`맡기기 전` 과
    `맡긴 뒤`) **답이 달라지는 사람만** 세운다(`routers/dashboard.py` 의
    `_grant_candidates`) — 맡겨도 안 통하는 사람은 애초에 안 선다. 거기서도
    조건을 다시 적지 않는 이유가 이것이다.
    """
    if user.role == "admin":
        return True
    if owner_id is None:
        return False
    if owner_id == user.id:
        return True
    if not may_view_all_consulting(user):
        return False
    if grants is None:
        grants = grant_owner_ids(db, user)
    return owner_id in grants


def may_edit_column(db: Session, user: User) -> bool:
    """월 칸의 **이름을 바꾸고 지울** 수 있는가 — 관리자만이다.

    세우는 쪽은 좁히지 않는다(`add_column` 참고) — 달 칸이 하나도 없는 탭은
    본이 없어 자동 생성이 안 붙고, 그 첫 칸을 심는 것이 이 화면을 쓰는
    사람이다. 여기서 막는 것은 **이미 서 있는 칸을 없애는 쪽**뿐이다.

    **새 규칙이 아니다.** 칸은 이제 탭에 붙어 있어 주인이 없고
    (`models.ConsultingColumn`), 위 `may_edit_row` 에 `주인 없음` 을 그대로
    넣으면 나오는 답이 이것이다. 판정을 여기 새로 적지 않는 이유는 이 저장소가
    반복해 당한 유형이라서다 — 같은 판단이 두 곳에 적히면 한쪽은 반드시 낡아,
    화면에는 [✕] 가 서 있는데 누르면 404 가 난다.

    **결과도 맞다.** 예전에는 칸이 사람마다라 자기 칸을 지우는 것이 자기 표만
    건드렸는데, 이제 그 칸은 팀이 함께 보는 머리글이다. 하나 지우면 그 달
    기록이 **팀 전체의 줄에서** 사라진다(`delete_column`). 한 사람이 혼자
    누를 단추가 아니다.
    """
    return may_edit_row(db, user, None)


def owned(db: Session, model, row_id: int, user: User, what: str):
    """고칠 수 있는 줄 하나. 아니면 **없는 것으로** 답한다.

    **화면이 쓰는 두 판정을 그대로 태운다** — 볼 수 있는가(`scope()`)와 고칠
    수 있는가(`may_edit_row`). 여기가 정확히 그것이 갈려서 났던 자리다: 보는
    쪽은 `scope()` 로 좁히는데 고치는 쪽에는 검사가 아예 없어서,
    `can_view_consulting` 이 켜진 팀원이 **번호만 바꾸면 화면에 안 뜨는 남의
    줄**을 고치거나 지울 수 있었다. 안 보이는 것을 고치는 것이라 고친 사람도,
    당한 사람도 모른다.

    판정을 여기 새로 적지 않는 이유는 이 저장소가 반복해 당한 유형이라서다
    (투자사 수가 화면마다 달랐던 일, 좌측 메뉴와 라우터 목록이 갈려 컨설턴트에게
    다 열려 있던 일, 팀 현황의 `투자현황` 칸이 거짓말한 일). 두 곳에 적으면
    한쪽은 반드시 낡는다 — 표에 `읽기 전용` 으로 그려지는 줄과 여기서 404 가
    나는 줄은 **같은 함수 하나**가 정한다.

    없는 번호와 남의 번호를 **같은 404** 로 답한다. 403 으로 갈라 주면 번호를
    훑어 남의 표가 몇 번까지 있는지 알 수 있다(routers/contacts.py 의 `_owned`
    가 같은 이유로 그렇게 한다).
    """
    row = db.execute(
        scope(select(model).where(model.id == row_id), model, user)
    ).scalar_one_or_none()
    if row is None or not may_edit_row(db, user, row.user_id):
        raise HTTPException(status_code=404, detail=f"{what}을 찾을 수 없습니다")
    return row


def _editable_column(db: Session, column_id: int, user: User) -> ConsultingColumn:
    """고칠 수 있는 월 칸 하나. 아니면 **없는 것으로** 답한다.

    줄에 쓰는 `owned()` 와 같은 모양이되 `scope()` 를 안 태운다 — 칸에는
    주인이 없어 좁힐 것이 없다(`models.ConsultingColumn`). 판정은 그대로
    `may_edit_column` 한 곳이고, 화면이 [✕] 를 세우는 근거도 같은 함수다.

    없는 번호와 못 고치는 번호를 **같은 404** 로 답한다. 403 으로 갈라 주면
    번호를 훑어 칸이 몇 번까지 있는지 알 수 있다(`owned()` 와 같은 이유다).
    """
    col = db.get(ConsultingColumn, column_id)
    if col is None or not may_edit_column(db, user):
        raise HTTPException(status_code=404, detail="열을 찾을 수 없습니다")
    return col


def owner_tabs(db: Session, user: User, sheet: str = "") -> List[dict]:
    """화면 위의 **사람을 고르는 자리.** 자기 것만 보는 사람에게는 없다.

    **이름은 계정 목록이 아니라 줄에서 뽑는다.** 계정으로 세우면 컨설턴트로
    만들어만 두고 아직 기업을 안 받은 사람이 `0` 으로 서서, 고를 것이 없는
    이름이 늘어난다. 줄이 곧 담당이므로 줄에 붙어 있는 사람만 세운다.

    **담당이 컨설턴트가 아닌 줄도 그 사람 이름으로 선다.** 지금 운영의 모든
    줄이 그 상태다(팀원 한 사람이 시트를 통째로 들고 있다). 그것을 `미배정`
    같은 말로 묶으면 화면이 거짓말을 한다 — 그 줄에는 실제로 주인이 있고,
    그 사람만 고칠 수 있으며, 주인 없는 줄(user_id NULL)은 "아직 배정 안 됨"
    이라는 **다른 뜻**으로 이미 서 있다. 대신 역할을 옆에 적어 둔다
    (`role_note`) — 이 화면이 컨설턴트별 표라, 이름만 있으면 그 사람이 세
    번째 컨설턴트인 줄 읽힌다.

    **숫자는 지금 보고 있는 탭의 건수다.** 눌렀을 때 나올 수와 같아야 한다 —
    탭을 가리지 않고 세면 탭에는 32 라고 적혀 있는데 이름 옆에는 55 가 붙는다.
    사람 목록 자체는 탭을 가리지 않는다. 이 탭에 줄이 없다고 이름을 빼면
    그 사람 표로 건너갈 길이 화면에서 사라진다.
    """
    if not may_view_all_consulting(user):
        return []
    counts = dict(db.execute(
        select(ConsultingCompany.user_id, func.count())
        .where(ConsultingCompany.sheet == sheet)
        .group_by(ConsultingCompany.user_id)
    ).all()) if sheet else {}
    totals = dict(db.execute(
        select(ConsultingCompany.user_id, func.count())
        .group_by(ConsultingCompany.user_id)
    ).all())
    out = []
    for uid, total in totals.items():
        who = db.get(User, uid) if uid else None
        out.append({
            "id": uid or UNASSIGNED,
            "name": who.name if who else "담당 미배정",
            # 컨설턴트가 아닌 담당에만 붙는다. 컨설턴트 이름에 `투자컨설턴트`
            # 라고 또 적으면 화면이 같은 말을 두 번 하는 것뿐이다.
            "role_note": ("" if who is None or who.role == "consultant"
                          else "팀원" if who.role != "admin" else "관리자"),
            "count": counts.get(uid, 0),
            "total": total,
        })
    # 탭을 옮겨도 **자리가 그대로**여야 한다. 이 탭의 건수로 줄을 세우면 탭마다
    # 이름 순서가 바뀌어, 같은 자리를 눌렀는데 다른 사람이 열린다.
    return sorted(out, key=lambda x: (-x["total"], x["name"]))


# 표에 한 번에 보여줄 월 수. 달마다 한 칸씩 늘어나는 표라, 그냥 두면 한 해
# 뒤에는 열두 칸이 되어 가로로 밀어야 읽힌다. 실제로 챙기는 것은 최근 몇
# 달뿐이다.
VISIBLE_MONTHS = 3


# 탭 이름은 **여기 없다.** 화면에서 고치는 값이라 `ConsultingSheet` 행에 있고,
# 무엇이 세워지는지는 `services/consulting_sheets.py` 한 곳이 정한다.
#
# 첫 탭은 `중요 스타트업` 이었다. `중요` 는 나머지 탭이 안 중요하다는 뜻으로
# 읽히는데 실제로는 그런 갈래가 아니다 — 시트 세 장의 성격 차이일 뿐이다.
# 그때는 **이름만 바꾸니 이미 들어간 줄이 옛 이름의 유령 탭으로 갈라져서**
# 자료를 옮기는 마이그레이션을 따로 써야 했다(0039). 이제 이름을 바꾸면
# 그 줄들이 같이 따라간다(`consulting_sheets.rename`).

# 탭의 **열쇠** → (앞 칸들, 뒤 칸들). 적어 두지 않은 탭은 지금까지의 표다.
#
# **이름이 아니라 열쇠로 짝짓는다.** 이름으로 맞춰 두면 탭 이름을 한 글자
# 고치는 순간 계약 표가 조용히 일반 표로 돌아가, `계약월`·`성공보수율` 칸이
# 화면에서 사라진다 — 이름을 고칠 수 있게 만들면서 생기는 함정이다.
SHEET_LAYOUTS = {
    cs.CONTRACT: (CONTRACT_COLUMNS, CONTRACT_TAIL),
    # 스타트업 탭만 `딜 소개문구` 를 한 칸 더 세운다. 여기 적어 두지 않으면
    # `경영본부 전달 기업`(과 사람이 시트를 올려 만든 탭)까지 같은 묶음을 받아,
    # 값이 영영 안 들어갈 칸이 그 탭들에도 선다.
    cs.STARTUP: (STARTUP_COLUMNS, TAIL_COLUMNS),
}


def layout_of(db: Session, sheet: str) -> tuple:
    """이 탭이 쓰는 칸 묶음. 모르는 탭은 지금까지의 표다.

    사람이 시트를 올려 만든 탭도 있어서, 이름을 모른다고 표를 비워 버리면
    그 탭이 통째로 안 보인다.
    """
    return SHEET_LAYOUTS.get(cs.kind_of(db, sheet), (FIXED_COLUMNS, TAIL_COLUMNS))


def is_contract(db: Session, sheet: str) -> bool:
    """이 탭이 계약 표인가. **이름으로 견주지 않는다**(위 참고)."""
    return cs.kind_of(db, sheet) == cs.CONTRACT


def is_startup(db: Session, sheet: str) -> bool:
    """이 탭이 `관리 스타트업` 인가. `딜 소개문구` 칸이 여기에만 선다.

    `is_contract` 의 반대가 아니다 — 아닌 탭이 `경영본부 전달 기업` 과 사람이
    시트를 올려 만든 탭까지 둘 이상이라, 화면에서 `not is_contract` 로 갈랐다간
    그 탭들에도 칸이 같이 선다. 여기도 **이름이 아니라 열쇠로** 본다.
    """
    return cs.kind_of(db, sheet) == cs.STARTUP


# `월간 계약 업무현황표` 의 한 줄은 슬래시로 이어 붙어 있다. **시트가 스스로
# 그 순서를 머리글로 적어 두었다** — `기업명 / 계약금액 / 성공보수율 / 계약일`.
# 그 순서를 그대로 따른다(추측이 아니라 시트에 적힌 것이다).
CONTRACT_PARTS = ["company_name", "contract_fee", "success_fee", "meeting_at"]


def split_contract_line(line: str) -> Dict[str, str]:
    """`기업명/ 유료 90만/ 3프로/ 미정` → 칸마다 하나씩. 나눌 것이 없으면 빈 dict.

    **조각 수가 줄마다 다르다.** 실제 자료에도 셋짜리와 넷짜리가 섞여 있다.

      모자라면  뒤 칸을 비워 둔다. 시트에서 빠지는 것은 늘 뒤쪽이고
                (`○○○/ 무료/ 4%` 는 계약일이 아직 없다는 뜻이다),
                앞에서 채우면 보수율 칸에 계약일이 들어간다.
      넘치면    남는 조각을 **마지막 칸에 그대로 이어 둔다.** 버리면 시트에
                있던 값이 앱에서 사라진다 — 사람이 보고 옮길 수 있게 남긴다.

    값은 **적힌 그대로** 담는다. `3%` 인지 `3프로` 인지, `유료 90만` 인지는
    계약서에 적힌 말이라 앱이 고쳐 쓸 것이 아니다. `계약금액` 칸에 `무료` 가
    적혀 있는 것도 시트가 그렇게 쓴 것이라 그대로 둔다.
    """
    parts = [p.strip() for p in (line or "").split("/")]
    if len(parts) < 2:
        return {}
    out = dict(zip(CONTRACT_PARTS, parts))
    if len(parts) > len(CONTRACT_PARTS):
        out[CONTRACT_PARTS[-1]] = " / ".join(parts[len(CONTRACT_PARTS) - 1:])
    return out


def _column_sheets(db: Session) -> List[str]:
    """이 요청에서 월 칸을 세워야 하는 **탭**들.

    칸은 이제 탭마다 한 벌이라(`models.ConsultingColumn`) 누가 열었는지와
    무관하다. 컨설턴트가 열어도 팀이 함께 쓰는 그 탭의 이번 달 칸이 서는
    것이고, 그것이 이 표에서 맞는 결과다 — 예전에는 **자기 칸만** 서서,
    아무도 안 연 사람의 표는 그 달 기록이 지난달 칸에 섞여 들어갔다.

    보는 범위(`scope()`)로 좁히지 않는다. 좁히면 컨설턴트가 연 달에는 그
    사람이 보는 탭에만 칸이 서서, **같은 탭이 사람에 따라 다른 달까지**
    자라는 표가 된다. 두 번 세우지 않는 것은 `MonthlyColumnRun` 이 본다.

    **이미 칸이 있는 탭만** 돌려준다. 칸이 하나도 없는 탭은 이름 지을 본이
    없어 어차피 만들지 못한다(`services/monthly_columns.py` 참고).
    """
    rows = db.execute(
        select(ConsultingColumn.sheet).group_by(ConsultingColumn.sheet)).all()
    return [name for (name,) in rows if name]


def sheet_tabs(db: Session, user: User, owner: int = 0) -> List[dict]:
    """시트별 인원. 탭에 건수를 띄운다.

    **줄이 하나도 없어도 탭 셋은 선다.** 새로 온 투자컨설턴트에게 빈 화면이
    뜨면 없는 줄 알고 자기 시트를 또 만든다 — 탭은 팀이 함께 쓰는 업무 단계라
    사람마다 갈릴 것이 아니다(`services/consulting_sheets.py`).

    이름은 **화면에서 고친 값**이다. 여기에 목록을 적어 두면 고친 이름이 이
    화면에만 안 반영된다.
    """
    rows = dict(db.execute(scope(
        select(ConsultingCompany.sheet, func.count())
        .group_by(ConsultingCompany.sheet), ConsultingCompany, user, owner)
    ).all())
    out = [{"key": s.label, "label": s.label, "kind": s.kind,
            "count": rows.get(s.label, 0)} for s in cs.ensure(db)]
    # 사람이 시트를 올려 만든 탭도 그대로 세운다 — 목록에 없다고 빼면 그 줄들이
    # 화면 어디에도 안 뜬다.
    known = {t["key"] for t in out}
    out += [{"key": n, "label": n, "kind": "", "count": rows[n]}
            for n in rows if n not in known]
    return out


def _column_stmt(sheet: str = ""):
    stmt = select(ConsultingColumn).order_by(ConsultingColumn.position,
                                             ConsultingColumn.id)
    return stmt.where(ConsultingColumn.sheet == sheet) if sheet else stmt


def _columns(db: Session, sheet: str = "") -> List[ConsultingColumn]:
    """화면에 세울 월 칸. **탭 하나에 한 벌**이라 누가 보든 같다.

    담당(`owner`)으로 갈리지 않는다 — 갈리는 것은 줄이지 칸이 아니다
    (`models.ConsultingColumn`). 담당을 바꿔 가며 봐도 머리글은 그대로이고,
    `담당: 전체` 에서도 같은 달이 한 번만 선다.
    """
    return db.execute(_column_stmt(sheet)).scalars().all()


def _split_columns(columns: List[ConsultingColumn], show_all: bool = False) -> tuple:
    """(보여줄 월, 접어 둔 월). **달 단위로** 자른다.

    **접었다는 것을 사람이 알아야 한다** — 그냥 안 보이면 지워진 줄 안다.
    화면에 몇 달이 접혀 있는지 적고, 눌러서 펼 수 있게 한다.

    지금까지는 앞에서 세 **칸**을 잘랐다. 이 표는 한 달에 한 칸이라 결과가
    같았지만, 한 달에 두 칸을 세우는 순간 달 중간이 잘려 **한 달의 기록 일부만
    보이는** 표가 된다. 투자사 관리 현황이 이미 그 모양이라(한 달에 세 칸)
    자르는 기준을 같은 것으로 맞춘다(`services/contact_columns.split_months`).

    여기만 석 달을 편다. 위 KPI 가 **지난달** 빈칸을 세므로 그 달이 표에
    보여야 하고, 한 달에 한 칸이라 석 달이어도 세 칸이다.

    사람이 펴 둔 상태(`?months=all`)는 요청에 실려 있고 DB 에 없다 — 달이
    바뀌어 열이 저절로 생겨도 편 것을 다시 접을 수가 없다.
    """
    if show_all:
        return list(columns), []
    seen: List[str] = []
    for i, col in enumerate(columns):
        month = monthly_columns.month_of(col.label)
        # 이름에서 달을 못 읽는 열은 혼자 한 묶음이다 — 옆 달에 붙이면 그 열
        # 때문에 남의 달이 통째로 접히거나 펴진다.
        key = f"{month}월" if month is not None else f"#{i}"
        if key in seen:
            continue
        if len(seen) == VISIBLE_MONTHS:
            return list(columns[:i]), list(columns[i:])
        seen.append(key)
    return list(columns), []


def _prev_month() -> int:
    """지난달 숫자. 1월이면 12월이다.

    시각은 `app/clock.py` 로만 읽는다. 표준 라이브러리의 현재시각 함수를 여기서
    바로 부르면 시간대가 또 갈린다(`tests/test_timezone.py` 가 막는다).
    """
    return clock.today().month - 1 or 12


def _prev_month_label(columns: List[ConsultingColumn]) -> str:
    """지금 기준 **지난달**에 해당하는 열의 이름.

    열 이름이 `8월 마지막주 리마인드 톡 or TEL` 처럼 자유 문장이라 달을 숫자로
    읽어 찾는다. 없으면 빈 문자열 — 화면이 그냥 '연락 기록' 으로 돈다.
    """
    month = _prev_month()
    for col in columns:
        m = re.search(r"(\d{1,2})\s*월", col.label or "")
        if m and int(m.group(1)) == month:
            return col.label
    return ""


def _prev_month_columns(columns: List[ConsultingColumn]) -> List[str]:
    label = _prev_month_label(columns)
    return [str(c.id) for c in columns if c.label == label]


# 주인이 없는 줄을 표에서 부르는 말. 고르는 자리의 `담당 미배정` 과 같은 뜻이라
# 한 곳에 적어 둔다 — 두 곳에 적으면 한쪽만 고쳐져 같은 줄이 화면에서 두 이름으로
# 불린다.
NO_OWNER = "미배정"


def _owner_name(db: Session, owner_id: Optional[int]) -> str:
    """줄에 붙은 담당의 이름. 주인이 없으면 `미배정`."""
    who = db.get(User, owner_id) if owner_id else None
    return who.name if who else NO_OWNER


def _pick_owner(db: Session, user: User, owner: int) -> int:
    """고른 사람이 **실제로 줄을 가진 사람**인가. 아니면 전체로 돌린다.

    주소에 없는 번호가 실려 오면(옛 즐겨찾기 · 담당이 다 옮겨 간 뒤) 표는 비고
    고르는 자리에는 아무것도 안 눌린 채로 남는다 — 왜 비었는지 화면 어디에도
    안 나온다. 그럴 바에는 전체를 보여 주는 편이 낫다.
    """
    if not may_view_all_consulting(user) or not owner:
        return 0
    known = {uid or UNASSIGNED for (uid,) in db.execute(
        select(ConsultingCompany.user_id)
        .group_by(ConsultingCompany.user_id)).all()}
    return owner if owner in known else 0


def _notes(company: ConsultingCompany) -> Dict[str, str]:
    try:
        return json.loads(company.notes or "{}")
    except (TypeError, ValueError):
        return {}


# 월별 리마인드 칸의 **수정한 날짜** 열쇠 앞머리. 모델 칸 이름(`deal_pitch`)과
# 섞이지 않게 앞에 붙인다 — 열 id 는 숫자라 그냥 두면 `12` 가 되고, 나중에
# `12` 라는 이름의 모델 칸이 생기지 않는다는 보장이 없다.
#
# **여기 한 곳에서 만든다.** 적는 쪽(`_assign`)과 읽는 쪽(`company_rows`)과
# 화면이 같은 글자를 써야 하는데, 세 곳에 적으면 한쪽만 고쳐질 때 날짜가
# 조용히 안 뜬다(값은 멀쩡히 들어 있는데 화면만 빈다).
NOTE_STAMP = "note:"


def note_stamp_key(column_id) -> str:
    return f"{NOTE_STAMP}{column_id}"


def _stamps(company: ConsultingCompany) -> Dict[str, str]:
    """이 줄의 **칸마다 마지막으로 바뀐 시각.** 깨진 값은 빈 dict 다.

    `_notes` 와 같은 모양이다 — 읽다 터지면 표 한 줄이 아니라 화면 전체가
    안 뜬다. 날짜가 안 보이는 것과 표가 안 열리는 것은 무게가 다르다.
    """
    try:
        return json.loads(company.field_stamps or "{}")
    except (TypeError, ValueError):
        return {}


def shown_stamps(company: ConsultingCompany) -> Dict[str, str]:
    """화면에 그대로 그릴 수 있는 꼴 — `{"deal_pitch": "2026-09-21 14:30", …}`.

    **줄이는 자리는 `clock.stamp_text` 한 곳이다.** 화면이나 브라우저에서 다시
    자르면 같은 값이 두 꼴로 보인다(`routers/companies.py` ·
    `routers/contacts.py` 가 같은 함수를 부른다). 초를 뺄지 말지도 저기서
    정한다 — 여기에 날짜 만드는 셈을 적지 않는다.

    빈 값은 **아예 안 싣는다.** 화면이 `{% if %}` 하나로 잔글씨를 세울지 말지
    정할 수 있어야 하는데, 빈 글자를 실어 두면 모든 줄에 빈 `<div>` 가 서서
    344줄짜리 표가 통째로 한 줄만큼 키가 커진다.
    """
    return {key: text for key, value in _stamps(company).items()
            if (text := stamp_text(value))}


def company_rows(db: Session, user: User, sheet: str = "",
                 owner: int = 0) -> List[dict]:
    cols = _columns(db, sheet)
    prev_keys = _prev_month_columns(cols)
    stmt = select(ConsultingCompany).order_by(ConsultingCompany.position,
                                              ConsultingCompany.id)
    if sheet:
        stmt = stmt.where(ConsultingCompany.sheet == sheet)
    companies = db.execute(scope(stmt, ConsultingCompany, user, owner)).scalars().all()
    # **줄마다 묻지 않고 한 번 떠 온다.** 아래에서 줄마다 `may_edit_row` 를
    # 부르는데, 판정이 이 자료를 볼 때마다 조회를 열면 서른 줄짜리 탭에서
    # 서른 번 나간다. 판정은 그대로 한 곳이다 — 읽는 값만 미리 준다.
    grants = grant_owner_ids(db, user)
    # **이 기업이 이미 스타트업 명단에 서 있는가.** 줄마다 묻지 않고 한 번
    # 떠 온다(바로 위 `grants` 와 같은 이유 — 쉰 줄짜리 탭에서 쉰 번 나간다).
    #
    # 표의 표시와 서버의 건너뛰기가 **같은 값**을 읽는다
    # (`services/startup_handoff.py`). 두 벌이면 표에는 아무 표시가 없는데
    # 눌러도 안 들어가는 줄이 생긴다.
    in_startup = startup_handoff.existing_firms(db)
    out = []
    for order, c in enumerate(companies, start=1):
        notes = _notes(c)
        management = c.management or ""
        # 이 탭이 계약 표인가. 줄에 적힌 탭으로 본다 — `company_rows` 는 탭을
        # 안 주고 부르는 곳이 있어서(엑셀 · 한 줄 조회), 인자로 판단하면
        # 그쪽에서만 값이 달라진다.
        contract = is_contract(db, c.sheet)
        # 이 줄이 `딜 소개문구` 칸을 세우는 탭에 있는가. 화면과 **같은 판정**을
        # 쓴다(`is_startup`) — 여기에 조건을 한 번 더 적으면 화면에는 칸이
        # 없는데 검색만 걸리는 줄이 생긴다.
        startup = is_startup(db, c.sheet)
        # 이 줄에 보이는 월별 리마인드 칸. 접힌 달도 들어 있다 — 화면에 안
        # 보인다고 기록이 없는 것은 아니다.
        seen = {str(col.id): notes.get(str(col.id), "") for col in cols}
        out.append({
            "id": c.id,
            # **누구의 줄인가.** 여러 사람의 표를 한 화면에서 보는 자리라,
            # 줄만 보고는 누구 것인지 알 수 없으면 고른 사람을 바꿀 때마다
            # 위 칩을 다시 확인해야 한다.
            "owner_id": c.user_id or 0,
            "owner_name": _owner_name(db, c.user_id),
            # **화면이 고칠 수 있다고 그리는 것과 서버가 허락하는 것이 같아야
            # 한다.** 판정은 `may_edit_row` 한 곳이고 화면은 그것을 읽기만 한다
            # (`owned()` 도 같은 함수를 태운다).
            "editable": may_edit_row(db, user, c.user_id, grants=grants),
            # 화면의 NO 는 **보이는 순서대로 1부터**다. 시트에서 옮겨 온 번호는
            # 중간이 비거나 3부터 시작해서, 몇 번째 줄인지 세는 데 쓸 수 없다.
            "no": order,
            "position": c.position,
            "region": c.region or "",
            "meeting_at": c.meeting_at or "",
            # 계약 탭에는 이 칸이 안 서지만 **늘 싣는다** — 화면이 탭마다 다른
            # dict 를 받으면 없는 칸을 꺼내다 터지는 자리가 생긴다(`deal_pitch`
            # · `success_fee` 와 같은 규칙이다). 빈 문자열이 곧 `아직 안 정함`
            # 이고, 머리글 필터가 그것을 `(비어 있음)` 으로 세워 준다.
            "meeting_kind": c.meeting_kind or "",
            "company_name": c.company_name or "",
            "management": management,
            # `기업 관리` 에서 갈라져 나온 상세. 계약 탭에는 이 칸이 안 서지만
            # **늘 싣는다** — 화면이 탭마다 다른 dict 를 받으면 없는 칸을
            # 꺼내다 터지는 자리가 생긴다(`deal_pitch` 와 같은 규칙이다).
            #
            # **`mgmt`·`managed`·`dropped` 는 이 값을 안 본다.** 갈라낸 보람이
            # 거기 있다 — 상세 글의 낱말이 다시 갈래를 흔들면 안 된다.
            "management_detail": c.management_detail or "",
            # 머리글 필터가 보는 값. 칸에 적힌 문장 그대로가 아니라 시트가 정해
            # 둔 세 마디로 추린다. 계약 탭만 예외다.
            "mgmt": status.tag_value(management, contract=contract),
            # **위 KPI 도 줄의 표시도 여기서 나온다.** 예전에는 라우터가 KPI 를,
            # 화면이 `data-dropped` 를 각자 정해서 규칙이 두 벌이었다.
            "managed": status.is_managed(management, contract=contract),
            "dropped": status.is_dropped(management, contract=contract),
            "ceo_name": c.ceo_name or "",
            "phone": c.phone or "",
            "email": c.email or "",
            # **같은 기업이 두 화면에 다 있는가.** 스타트업 명단으로 보내도
            # 이 줄은 그대로 남으므로(지우지 않는다), 두 곳에 있다는 사실이
            # 화면에 적혀 있지 않으면 사람이 알 길이 없다 — 그러면 다음 달에
            # 어느 쪽을 고쳐야 하는지 모르게 된다.
            #
            # 탭을 가리지 않고 늘 싣는다. 보내는 것은 `관리 스타트업` 탭에서만
            # 하지만, **알아야 하는 것은 그 탭 밖에서도 마찬가지**다(같은
            # 기업이 `경영본부 전달 기업` 으로 옮겨 간 뒤에도 스타트업 명단에는
            # 남아 있다). 화면이 표시를 세우는 것은 체크 칸이 서는 탭뿐이다.
            "in_startup": startup_handoff.is_in_startup(in_startup, c),
            # **보내면 어느 이름으로 서는가.** 확인창이 이 값을 읽는다
            # (`static/js/consulting_to_startup.js`). 화면이 `기업명` 칸 글자를
            # 그대로 쓰면 `라마바이오 / 무료 / 3%` 라고 물어 놓고 실제로는
            # `라마바이오` 가 서서, 확인창이 거짓말을 한다 — 꺼내는 규칙은
            # 서버 한 곳이다(`startup_handoff.company_name_of`).
            "startup_firm": startup_handoff.company_name_of(c.company_name),
            # `월간 계약 업무현황표` 탭에만 값이 있다. 다른 탭에서는 빈 문자열이라
            # 화면이 탭마다 다른 dict 를 받지 않는다 — 없는 칸을 꺼내다 터지는
            # 자리를 만들지 않으려는 것이다.
            "success_fee": c.success_fee or "",
            "contract_fee": c.contract_fee or "",
            # 빈 문자열이 곧 `아직 안 정함` 이다 — 머리글 필터가 그것을
            # `(비어 있음)` 으로 세워 준다(`static/js/filters.js`).
            "contract_received": c.contract_received or "",
            # `관리 스타트업` 탭에만 값이 있다. 위 두 칸과 같은 이유로 늘
            # 실어 둔다 — 화면이 탭마다 다른 dict 를 받으면 없는 칸을 꺼내다
            # 터지는 자리가 생긴다. 머리글·칸을 세우는 것은 화면 쪽이다.
            "deal_pitch": c.deal_pitch or "",
            # 같은 탭의 두 칸. 위와 같은 이유로 탭을 가리지 않고 늘 싣는다.
            # (`계약서 수신완료여부` 는 바로 위 `contract_received` 다 — 계약
            #  탭과 같은 칸이라 여기 또 적지 않는다.)
            #
            # `계약완료여부` 는 빈 문자열이 곧 `아직 안 정함` 이다 — 머리글
            # 필터가 그것을 `(비어 있음)` 으로 세워 준다.
            "contract_management": c.contract_management or "",
            "contract_done": c.contract_done or "",
            # 같은 탭의 `카톡 연결 여부`. 빈 문자열이 곧 `아직 안 정함` 이다.
            # (`VcContact.kakao_joined` 와 이름만 같은 다른 칸이다 —
            #  `models.ConsultingCompany.kakao_joined` 주석 참고.)
            "kakao_joined": c.kakao_joined or "",
            "notes": seen,
            # **칸마다 마지막으로 바뀐 시각** — 화면이 값 밑에 잔글씨로 세운다.
            # 줄에 붙어 있는 값이라 **조회가 한 번도 안 는다**(344줄짜리 표에서
            # 줄마다 로그를 캐물으면 344번 나간다 — 그래서 `edit_logs` 가 아니라
            # 줄에 담았다. 왜 저기서 못 끌어오는지는
            # `models.ConsultingCompany.field_stamps` 주석에 한 곳으로 적혀 있다).
            #
            # 접힌 달의 것도 들어 있다 — 화면이 세우는 것은 펴 둔 달뿐이지만,
            # 여기서 골라내면 `모두 펴기` 로 열었을 때 그 달만 날짜가 빈다.
            "stamps": shown_stamps(c),
            # 어느 달이든 기록이 있는가 — `연락 기록 없음` 칩이 보는 값이다.
            "contacted": status.contacted(seen.values()),
            # 지난달에 연락했는가. 이번 달은 아직 진행 중이라 세어 봐야
            # "아직 안 했다" 만 나온다.
            "contacted_prev": status.contacted(notes.get(k, "") for k in prev_keys),
            "updated_at": (c.updated_at or "")[:10],
            "search": " ".join(filter(None, [
                # `월`(`region`)은 계약 탭에서 **화면에 안 선다.** 칸이 없는
                # 탭에서까지 걸면 화면 어디에도 없는 글자로 줄이 걸려 왜
                # 걸렸는지 알 수가 없고, 그 탭에서 아무 칸이나 고치는 순간
                # 브라우저가 보이는 칸만 이어 붙여 이 값을 다시 적으므로
                # (`consulting.js` 의 `refreshRowFlags`) 고치기 전후로 검색
                # 결과가 달라진다 — 아래 `deal_pitch` 와 같은 규칙이다.
                c.company_name, "" if contract else c.region,
                c.management, c.ceo_name,
                # 갈라져 나온 상세도 **찾을 수 있어야 한다** — 갈라내기 전에는
                # `c.management` 에 들어 있어 검색에 걸리던 글이다. 여기서 빼면
                # 이 커밋 뒤에 "찾던 기업이 검색에 안 나온다" 가 된다.
                #
                # **칸이 서는 탭에서만** 넣는다(아래 `deal_pitch` 와 같은 이유).
                "" if contract else c.management_detail,
                c.email, c.meeting_at, c.success_fee, c.contract_fee,
                # **칸이 서는 탭에서만** 넣는다(아래 `deal_pitch` 와 같은
                # 이유 — 계약 탭에는 이 칸도 머리글도 없다). 화면에서 고치면
                # 브라우저가 `td.cell` 을 전부 이어 붙여 이 값을 다시 적으므로
                # (`consulting.js` 의 `refreshRowFlags`), 서버가 안 넣으면
                # 고치기 전후로 검색 결과가 달라진다.
                "" if contract else c.meeting_kind,
                # 칸을 고치면 브라우저가 `td.cell` 을 전부 이어 붙여 이 값을
                # 다시 적는다(`consulting.js` 의 `refreshRowFlags`). 여기서
                # 빼 두면 새로고침 전후로 검색 결과가 달라진다.
                c.contract_received,
                # **문구로 찾는 것이 이 칸을 둔 이유에 가깝다.** 필터에는 안
                # 세웠지만(값이 자유 문장이라 고를 것이 없다) 검색은 자유
                # 문장을 그대로 받는 자리라 여기에 넣는다 — 툴바의
                # `기업 · 대표자 · 내용 검색` 이 이 값을 본다.
                #
                # **칸이 서는 탭에서만** 넣는다. 탭을 옮긴 줄에는 값이 남아
                # 있을 수 있는데(이 저장소는 이력을 안 지운다), 칸이 없는
                # 탭에서까지 걸면 화면 어디에도 없는 글자로 줄이 걸려 왜
                # 걸렸는지 알 수가 없다. 게다가 그 탭에서 아무 칸이나 고치는
                # 순간 브라우저가 보이는 칸만 이어 붙여 이 값을 다시 적으므로
                # (`consulting.js` 의 `refreshRowFlags`) 고치기 전후로 검색
                # 결과가 달라진다.
                c.deal_pitch if startup else "",
                # 세 칸도 **칸이 서는 탭에서만** 넣는다(위 `deal_pitch` 와
                # 같은 이유). 화면에서 고치면 브라우저가 `td.cell` 을 전부
                # 이어 붙여 이 값을 다시 적으므로(`consulting.js` 의
                # `refreshRowFlags`), 서버가 안 넣으면 고치기 전후로 검색
                # 결과가 달라진다.
                c.contract_management if startup else "",
                c.contract_done if startup else "",
                c.kakao_joined if startup else "",
                *notes.values(),
            ])).lower(),
        })
    return out


@router.get("/consulting", response_class=HTMLResponse, include_in_schema=False)
def consulting_page(request: Request, db: Session = Depends(get_db),
                    user: User = Depends(get_current_user), msg: str = "",
                    months: str = "", sheet: str = "", owner: int = 0,
                    ref: str = ""):
    require_access(user)
    # 자기 것만 보는 사람(투자컨설턴트)에게는 고를 것이 없다 — 무엇을 넣든
    # 자기 줄만 나온다(`scope()` 가 같은 판정을 읽는다).
    owner = _pick_owner(db, user, owner)
    tabs = sheet_tabs(db, user, owner)
    selected = (sheet if any(t["key"] == sheet for t in tabs)
                else cs.default_label(db))
    # **달이 바뀌었으면 이번 달 열을 세운다.** 예약 실행 장치가 없는 앱이라
    # 달이 바뀐 것을 알아채는 자리는 화면을 여는 순간뿐이다(주간 업무가 같은
    # 방식이다 — `services/weekly.py` 의 `fill_week`). 두 번 만들지 않는 것과
    # 사람이 지운 열을 되살리지 않는 것은 `services/monthly_columns.py` 가 본다.
    #
    # **탭마다** 세운다. 칸은 이제 탭에 붙어 있어(`models.ConsultingColumn`)
    # 지금 고른 탭 하나만 챙기면, 아무도 안 연 탭은 그 달 기록이 지난달 칸에
    # 섞여 들어간다.
    for name in _column_sheets(db):
        monthly_columns.ensure_consulting(db, name)

    rows = company_rows(db, user, selected, owner)
    can_pick = may_view_all_consulting(user)
    people = owner_tabs(db, user, selected) if can_pick else []
    prev_label = _prev_month_label(_columns(db, selected))
    # 달마다 한 칸씩 늘어나는 표라, 최근 몇 달만 펴 둔다.
    # `months=all` 은 일부러 다 본다는 뜻이다.
    shown, hidden = _split_columns(_columns(db, selected),
                                   show_all=(months == "all"))
    fixed, tail = layout_of(db, selected)

    # **접힌 달에 기록이 있는가.** `연락 기록 없음` 칩은 줄의 `data-contacted` 를
    # 보는데, 칸을 고치면 consulting.js 가 그 값을 다시 적는다 — 그때 JS 가 볼 수
    # 있는 것은 **펴 둔 달의 칸뿐**이라, 접힌 달에만 기록이 있는 줄이 고치는 순간
    # `기록 없음` 으로 뒤집힌다(실제로 이 표 34줄 중 12줄이 그 상태였다).
    # 화면에 없는 사실을 JS 가 알 수 없으므로 여기서 실어 보낸다.
    folded_keys = [str(c.id) for c in hidden]
    for row in rows:
        row["contacted_folded"] = status.contacted(
            row["notes"].get(k, "") for k in folded_keys)
    ctx = base_ctx(request, db, user, active="consult")
    # 스크립트·가이드는 이 화면에도 있다(미팅 진행 프로세스 · 견적서 발송 톡 …).
    # 투자사 관리 현황과 같은 구조를 쓰되 화면만 나눈다.
    # 질의는 `services/ref_panel.py` 한 곳에 있다 — 화면마다 적어 두면
    # `is_active`(지운 탭 감추기)나 탭 순서 같은 조건이 화면마다 갈린다.
    from ..services import ref_panel  # noqa: PLC0415

    ctx.update({
        **ref_panel.panel_ctx(db, "consulting", ref),
        "rows": rows,
        "sheet_tabs": tabs,
        "selected_sheet": selected,
        "columns": shown,
        # **접었다는 것을 사람이 알아야 한다** — 그냥 안 보이면 지워진 줄 안다.
        "hidden_columns": hidden,
        # **[✕]·이름 고치기를 세워도 되는 월 칸.** 칸은 이제 탭에 붙어 있어
        # 주인이 없다 — 그래서 관리자만이다. 새 규칙이 아니라 이미 있는 판정에
        # `주인 없음` 을 그대로 넣은 결과다(`may_edit_row`). 팀이 함께 보는
        # 머리글을 한 사람이 지우면 그 달 기록이 **팀 전체에서** 사라지므로
        # 결과도 맞다. 판정은 줄과 같은 함수 하나다 — 화면이 따로 정하면
        # 한쪽이 낡아서, 세워 둔 단추가 눌렀을 때 404 가 난다.
        "editable_columns": ({c.id for c in shown}
                             if may_edit_column(db, user) else set()),
        "show_all_months": months == "all",
        # 화면 위의 **사람을 고르는 자리.** 숫자는 지금 탭의 건수라
        # 눌렀을 때 나올 수와 같다.
        "owner_tabs": people,
        "selected_owner": owner,
        # 고르는 자리와 `담당` 칸이 같이 서고 같이 없어진다 — 둘 다 "여러
        # 사람의 표를 같이 본다" 는 한 가지 사실에서 나온다. 컨설턴트에게는
        # 자기 줄만 나오므로 이름이 한 가지로 반복될 뿐이다.
        "can_pick_owner": can_pick,
        "selected_owner_name": next(
            (o["name"] for o in people if o["id"] == owner), ""),
        # 탭마다 표가 다르다. 화면이 `{% if 이 탭이면 %}` 을 하나 더 심지 않게
        # **어느 탭인지**만 넘긴다(칸 목록은 아래 두 줄이 정한다).
        "is_contract_sheet": is_contract(db, selected),
        # `딜 소개문구` 는 이 탭에만 선다. `not is_contract_sheet` 로 갈랐다간
        # `경영본부 전달 기업` 에도 같이 서므로 **따로** 넘긴다.
        "is_startup_sheet": is_startup(db, selected),
        # ── 스타트업 명단으로 보내기 ────────────────────────────────────────
        #
        # 고를 수 있는 명단. 비어 있으면 화면이 그 줄을 아예 안 세운다 —
        # 고를 것이 하나도 없는 자리를 세우면 눌러도 아무 일이 없는 단추가
        # 된다(위 `담당` 칩이 같은 이유로 컨설턴트에게는 안 선다).
        #
        # **그 명단에 넣어도 되는 사람인지까지 여기서 거른다.** 서버가
        # 읽는 판정과 **같은 함수**다(`sheet_owner.may_add_row`) — 화면이
        # 따로 정하면 세워 둔 단추가 눌렀을 때 403 이 난다.
        #
        # 역할 문도 같이 지난다(`deps.can_open`). 투자컨설턴트는
        # `/api/contacts` 가 허용 목록 밖이라 이 줄이 아예 안 선다 —
        # 왜 열지 않았는지는 `send_to_startup` 주석에 있다.
        "startup_targets": ([
            t for t in startup_handoff.target_sheets(db)
            if sheet_owner.may_add_row(db, user, t["label"])
        ] if can_open(user, "/api/contacts/from-consulting") else []),
        # 보낼 화면의 이름. **여기 적지 않는다** — 좌측 메뉴가 그 이름을 이미
        # 들고 있고(`ui.MENU`), 두 곳에 적으면 메뉴를 고친 날 이 단추만 옛
        # 이름으로 남는다(화면 제목이 같은 자리에서 나오는 것과 같은 방식이다).
        "startup_label": menu_label("startup"),
        # `계약완료여부` 의 보기. **화면에 글자를 적어 두지 않는다** — 계약을
        # 부르는 말은 `routers/companies.py` 의 `CONTRACT_LABELS` 한 곳이고,
        # 여기 적으면 그 말을 고치는 날 두 화면이 갈린다
        # (`CONTRACT_DONE_CHOICES` 주석 참고).
        # 월별 리마인드 칸의 **수정한 날짜** 열쇠를 만드는 함수. 화면이
        # `'note:' ~ col.id` 라고 적어 두면 앞머리를 고치는 날 그 자리만 옛
        # 열쇠를 찾아 **날짜가 조용히 빈다**(값은 멀쩡히 들어 있는데 화면만
        # 비어, 안 찍힌 것인지 못 읽은 것인지 알 수가 없다). 한 곳은
        # `note_stamp_key` 다.
        "note_stamp_key": note_stamp_key,
        "contract_done_choices": ",".join(CONTRACT_DONE_CHOICES),
        # `미팅종류` 의 보기. 위 칸과 **같은 방식**이다 — 화면에 글자를 적어
        # 두지 않는다. 한 곳은 `MEETING_KIND_CHOICES` 다.
        "meeting_kind_choices": ",".join(MEETING_KIND_CHOICES),
        "fixed_columns": fixed,
        "tail_columns": tail,
        "msg": msg,
        "counts": {
            "total": len(rows),
            # 줄에 실어 보내는 표시와 **같은 값**을 센다. 여기서 규칙을 한 번 더
            # 적으면(`"관리" in …`) 그것이 두 번째 규칙이 되어, 한쪽만 고쳐질 때
            # 위에는 14 라고 적혀 있는데 칩을 누르면 13곳이 나온다.
            "managed": sum(1 for r in rows if r["managed"]),
            "dropped": sum(1 for r in rows if r["dropped"]),
            # **아직 안 한 곳**을 센다. 다 한 수를 보여 주던 칸이었는데, 그 수는
            # 봐도 할 일이 안 나온다 — 챙겨야 하는 것은 빈칸 쪽이다.
            #
            # 기준 달은 **지난달**이다. 진행 중인 달을 세면 월 초에는 전부
            # 미완료라 늘 전체 건수가 뜬다(그 칸은 이제 자동으로 생기므로 1일부터
            # 비어 있다). 놓친 것이 드러나는 것은 이미 지나간 달이다.
            #
            # 지난달 열이 아예 없으면 0 이다. 빈칸을 세면 "열이 없다" 가
            # "전부 미완료" 로 둔갑해 전체 건수가 그대로 뜬다.
            "pending": (sum(1 for r in rows if not r["contacted_prev"])
                        if prev_label else 0),
            "prev_month_label": prev_label,
            # 지난달 열이 **표에 서 있는가.** 이 수를 칸을 고친 자리에서 다시
            # 세는 것은 브라우저인데, 브라우저가 볼 수 있는 것은 펴 둔 달의
            # 칸뿐이다. 접혀 있으면 다시 셀 근거가 화면에 없으므로 아예 맡기지
            # 않는다 — 맡기면 전부 미완료로 뒤집힌다.
            # (`_split_columns` 가 석 달을 펴는 이유가 이 KPI 다. 열 순서가
            #  뒤죽박죽인 표에서만 지난달이 접힐 수 있다.)
            "prev_month_shown": bool(prev_label) and any(
                c.label == prev_label for c in shown),
            # `0월 마지막주 리마인드톡 미완료 기업` — 그 달 숫자를 넣는다.
            "pending_label": (f"{_prev_month()}월 마지막주 리마인드톡 미완료 기업"),
        },
    })
    return templates.TemplateResponse("consulting.html", ctx)


# --- 편집 -------------------------------------------------------------------

class CompanyIn(BaseModel):
    # 어느 탭의 줄인가. 이게 없어서 [기업 추가] 가 늘 첫 탭으로 들어갔다 —
    # 다른 탭에서 누른 사람 눈에는 **추가가 안 된 것처럼** 보인다(줄은 만들어
    # 졌는데 보고 있지 않은 탭에 있다).
    sheet: Optional[str] = None
    position: Optional[int] = None
    region: Optional[str] = None
    meeting_at: Optional[str] = None
    # **여기 안 적으면 화면에서 고쳐도 조용히 안 저장된다** — pydantic 이
    # 모르는 칸을 그냥 버리기 때문에 오류도 안 난다.
    meeting_kind: Optional[str] = None
    company_name: Optional[str] = None
    management: Optional[str] = None
    # `기업 관리` 에서 갈라져 나온 상세. **긴 글이라 줄바꿈이 그대로 들어온다**
    # — `_assign` 이 앞뒤 공백만 떼므로 가운데 줄바꿈은 살아서 저장된다
    # (`deal_pitch` 와 같다). 여기 안 적으면 화면에서 고쳐도 조용히 안 저장된다.
    management_detail: Optional[str] = None
    ceo_name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    # `월간 계약 업무현황표` 탭의 칸. **여기 안 적으면 화면에서 고쳐도 조용히
    # 안 저장된다** — pydantic 이 모르는 칸을 그냥 버리기 때문에 오류도 안 난다.
    success_fee: Optional[str] = None
    contract_fee: Optional[str] = None
    contract_received: Optional[str] = None
    # `관리 스타트업` 탭의 칸. **긴 글이라 줄바꿈이 그대로 들어온다** —
    # `_assign` 이 앞뒤 공백만 떼므로 가운데 줄바꿈은 살아서 저장된다.
    deal_pitch: Optional[str] = None
    # 같은 탭의 두 칸. **여기 안 적으면 화면에서 고쳐도 조용히 안 저장된다.**
    # (`계약서 수신완료여부` 는 위 `contract_received` 다 — 계약 탭과 같은
    #  칸이라 여기 또 적지 않는다.)
    contract_management: Optional[str] = None
    contract_done: Optional[str] = None
    # 같은 탭의 `카톡 연결 여부`. 여기 안 적으면 화면에서 고쳐도 조용히 안
    # 저장된다(위와 같다).
    kakao_joined: Optional[str] = None
    # {"열id": "내용"} — 월별 리마인드
    notes: Optional[Dict[str, str]] = None


def _assign(company: ConsultingCompany, body: CompanyIn) -> None:
    """화면이 보낸 값을 줄에 넣고, **바뀐 칸에 시각을 찍는다.**

    ## 왜 여기서 찍나

    이 표에 값이 들어오는 길이 셋이다 — 줄 세우기(`create_company`) · 칸 고치기
    (`update_company`) · 여러 줄 보내기(`send_to_startup` 은 읽기만 한다).
    앞의 둘이 **이 함수 하나를 지난다.** 라우터마다 찍으면 한 곳은 반드시
    빠지고, 빠진 길로 들어온 값은 날짜 없이 바뀐다 — 화면은 "안 고쳤다" 고
    읽는다(이 저장소가 반복해 당한 부류다: 목록과 라우터가 갈리는 사고).

    시트 올리기(`apply_rows`)는 이 함수를 안 지난다. **일부러 그렇다** —
    통째로 갈아끼우는 길이라 한 번에 수백 칸이 같은 시각으로 찍히고, 그러면
    `수정한 날짜` 가 "누가 언제 이 칸을 챙겼나" 가 아니라 "마지막으로 시트를
    언제 올렸나" 가 된다. 물음이 다르다.

    ## 바뀐 칸만

    값이 그대로면 안 찍는다. 안 그러면 칸을 눌렀다 아무것도 안 고치고 나온
    것도 `고쳤다` 가 되고, 같은 값을 다시 저장하는 길(브라우저는 안 보내지만
    API 는 열려 있다)로 날짜를 얼마든지 밀 수 있다.

    ## 어떤 칸이든 찍는다

    화면이 지금 날짜를 보여 주는 칸은 셋뿐이지만(`딜 소개문구` ·
    `카톡 연결 여부` · 월별 리마인드), 목록을 여기 적어 두지 않는다. 적어 두면
    **그 목록이 낡는다** — 다음에 네 번째 칸을 보여 달라는 날 여기를 같이
    고쳐야 하는 것을 아무도 모른다. 무엇을 보여 줄지는 화면이 정한다.
    """
    data = body.model_dump(exclude_unset=True)
    notes = data.pop("notes", None)
    at = clock.now_iso()
    stamps = _stamps(company)
    touched = False
    for field, value in data.items():
        after = value.strip() if isinstance(value, str) else value
        if after != getattr(company, field, None):
            setattr(company, field, after)
            stamps[field] = at
            touched = True
    if notes is not None:
        # 통째로 덮지 않고 병합한다 — 화면이 보내지 않은 달의 기록이 사라지면 안 된다.
        merged = _notes(company)
        for key, raw in notes.items():
            value = (raw or "").strip()
            if merged.get(key, "") == value:
                continue
            merged[key] = value
            # **달마다 제 날짜다.** 석 달치가 `notes` 한 칸에 들어 있어도
            # 시각은 열 id 별로 따로 찍는다 — 한 개만 찍으면 9월 칸을 고쳤는데
            # 7월 칸 밑의 날짜까지 같이 바뀌어 보인다.
            stamps[note_stamp_key(key)] = at
            touched = True
        company.notes = json.dumps({k: v for k, v in merged.items() if v},
                                   ensure_ascii=False)
    if touched:
        company.field_stamps = json.dumps(stamps, ensure_ascii=False)


@router.get("/api/consulting/{company_id}")
def get_company(company_id: int, db: Session = Depends(get_db),
                user: User = Depends(get_current_user)):
    require_access(user)
    # 남의 줄을 번호로 찍어 여는 길을 남기지 않는다.
    row = next((r for r in company_rows(db, user) if r["id"] == company_id), None)
    if row is None:
        raise HTTPException(status_code=404, detail="기업을 찾을 수 없습니다")
    return row


@router.post("/api/consulting")
def create_company(body: CompanyIn, db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)):
    require_access(user)
    if not (body.company_name or "").strip():
        raise HTTPException(status_code=400, detail="기업명을 입력하세요")

    # 화면이 보내 준 탭에 넣는다. 안 보내면 예전처럼 첫 탭이다.
    #
    # 아무 값이나 받으면 오타 하나로 **없던 탭이 생긴다** — `sheet_tabs` 가
    # 줄에 있는 시트 이름을 그대로 탭으로 올리기 때문이다. 지금 **화면에 서
    # 있는 탭 이름**만 받는다(사람이 시트를 올려 만든 탭도 거기 들어 있다).
    known = {t["key"] for t in sheet_tabs(db, user)}
    sheet = (body.sheet or "").strip()
    if sheet and sheet not in known:
        raise HTTPException(status_code=400, detail="없는 탭입니다")
    body.sheet = sheet or cs.default_label(db)

    if body.position is None:
        # 새 줄은 그 탭의 맨 아래로. 시트의 NO 를 사람이 매번 세지 않아도 되게.
        # **탭 안에서** 센다 — 전체에서 세면 다른 탭의 큰 번호를 물려받아,
        # 방금 넣은 줄이 자기 탭에서는 늘 맨 아래로 밀린다.
        last = db.execute(own(
            select(ConsultingCompany.position)
            .where(ConsultingCompany.sheet == body.sheet)
            .order_by(ConsultingCompany.position.desc()).limit(1),
            ConsultingCompany, user)
        ).scalar()
        body.position = (last or 0) + 1
    company = ConsultingCompany(user_id=user.id)
    _assign(company, body)
    db.add(company)
    db.commit()
    return {"id": company.id}


@router.patch("/api/consulting/{company_id}")
def update_company(company_id: int, body: CompanyIn,
                   db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)):
    require_access(user)
    company = owned(db, ConsultingCompany, company_id, user, "기업")
    _assign(company, body)
    db.commit()
    # **고친 시각을 응답에 싣는다.** 표의 잔글씨가 이것으로 그 자리에서
    # 바뀐다 — 새로고침해야 날짜가 따라오면, 방금 고친 칸 밑에 **옛 날짜**가
    # 그대로 적혀 있어 화면이 거짓말을 한다(IR 기업 현황·스타트업 명단이 같은
    # 이유로 같은 것을 돌려준다 — `routers/companies.py` · `routers/contacts.py`).
    #
    # 꼴을 여기서 정하지 않는다 — `shown_stamps` 가 `clock.stamp_text` 한 곳을
    # 지난다. 브라우저가 다시 자르면 같은 값이 두 꼴로 보인다.
    #
    # **줄 전체를 돌려주지 않는다.** 그러면 `company_rows` 를 한 번 더 도는데,
    # 거기에는 이 응답에 필요 없는 조회가 둘 붙어 있다(줄 편집 허용 ·
    # 스타트업 명단에 이미 있는 기업).
    return {"id": company.id, "stamps": shown_stamps(company)}


@router.delete("/api/consulting/{company_id}")
def delete_company(company_id: int, db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)):
    require_access(user)
    company = owned(db, ConsultingCompany, company_id, user, "기업")
    db.delete(company)
    db.commit()
    return {"deleted": company_id}


# --- 여러 줄을 골라 스타트업 명단으로 보내기 ---------------------------------
#
# **이관이 아니다.** 이 저장소에서 `이관`(`sheet_owner.move_to`)은 줄 하나의
# 담당을 바꾸는 일이고, 그 주석이 *"이관은 **누가 맡는지**를 바꾸는 일이지
# 화면을 옮기는 일이 아니다"* 라고 못 박아 두었다 — 그래서 그 길은 같은 화면
# 안에서만 움직이고 옛 명단에서 뺀다. 여기는 표가 아예 다르고
# (`ConsultingCompany` ↔ `VcContact`) **원본을 빼지 않는다.** 그래서 화면에도
# 코드에도 다른 말을 쓴다 — `스타트업 명단으로 보내기`.
#
# 규칙(무엇이 어느 칸에 들어가나 · 기업명을 어떻게 꺼내나 · 이미 있는 기업을
# 어떻게 보나)은 전부 `services/startup_handoff.py` 한 곳이다. 여기는 문을
# 지키고 그 규칙을 부르기만 한다.


class ToStartupIn(BaseModel):
    """고른 줄들과 **보낼 명단**. 명단은 사람이 화면에서 고른다."""

    company_ids: List[int] = []
    label: str = ""


# **주소가 `/api/contacts/…` 밑이다.** 파일은 여기인데 주소가 저쪽인 것이
# 어색해 보이지만, 그것이 이 길의 **권한이 정해지는 방식**이다.
#
#   · 투자컨설턴트는 허용 목록(`deps.CONSULTANT_PATHS`)에 있는 주소만 연다.
#     `/api/consulting/…` 밑에 두면 이 길이 **저절로 열린다** — 그 사람이
#     보이지도 않는 명단에 줄을 세우게 되고, 막으려면 라우터 안에 역할 판정을
#     한 벌 더 적어야 한다. `/api/contacts/…` 밑에 두면 **새 주소의 기본값이
#     막힘**이라 아무것도 안 적어도 된다(`contacts.transfer_contact` 의
#     docstring 이 같은 말을 한다).
#   · 이 길이 실제로 하는 일도 **담당자 줄을 만드는 것**이다 — 주소가 하는
#     일과 같은 이름을 갖는다.
#
# 파일이 `contacts.py` 가 아닌 이유는 하나다. 이 길은 투자컨설턴트 줄을
# **보이는 만큼만** 읽어야 하고(`scope`) 어느 탭인지도 봐야 하는데
# (`is_startup`), 그 둘이 여기 있다. 저쪽에서 여기를 부르면 두 라우터가
# 서로를 임포트하게 된다(여기는 이미 `create_contact` 를 부른다).
@router.post("/api/contacts/from-consulting")
def send_to_startup(body: ToStartupIn, db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    """고른 투자컨설턴트 줄들을 **스타트업 명단에 세운다.** 원본은 그대로 둔다.

    ── 문이 셋이다 ─────────────────────────────────────────────────────────

    ① **이 화면을 볼 수 있는가** (`require_access`).
    ② **역할.** 여기 아무것도 안 적혀 있다 — 주소가 `/api/contacts/…` 라
       투자컨설턴트는 미들웨어에서 끊긴다(바로 위 주석). 그 사람이 보이지도
       않는 명단에 줄을 세우면, 세워 놓고 어디로 갔는지 확인할 길이 없고
       잘못 넣어도 되돌릴 화면이 없다.
    ③ **그 명단에 줄을 넣어도 되는 사람인가** (`sheet_owner.may_add_row`).
       줄마다 부르는 `create_contact` 안에 이미 있는 판정이지만 **먼저 한 번
       더 묻는다** — 거기서 걸리면 앞의 몇 줄은 이미 들어간 뒤라, 사람이 보는
       것은 "절반만 들어갔다" 가 된다.

    ── 어느 탭에서 되나 ────────────────────────────────────────────────────

    `관리 스타트업` 탭만이다(`is_startup` — 화면이 칸을 세울 때 쓰는 그 판정).
    나머지 둘을 막는 이유는 탭마다 다르다.

      · `월간 계약 업무현황표` 는 **대표자·연락처·이메일 칸 자체가 없다**
        (화면도 안 세운다). 거기서 보내면 연락할 길이 하나도 없는 줄이 선다.
      · `경영본부 전달 기업` 은 이름 그대로 **이미 경영본부로 넘긴** 기업이다.
        거기서 또 스타트업 명단으로 보내면 누가 맡는지가 두 갈래로 갈린다.

    넓혀야 하면 고칠 곳은 아래 판정 한 줄이다.
    """
    require_access(user)
    label = (body.label or "").strip()
    targets = {t["label"]: t for t in startup_handoff.target_sheets(db)}
    if label not in targets:
        # 화면이 이미 그런 곳을 안 보여 주지만, 화면만 감추면 이름을 직접
        # 보내는 길이 남는다(`contacts.transfer_contact` 가 같은 이유로 막는다).
        raise HTTPException(status_code=400,
                            detail="담당이 정해진 명단으로만 보낼 수 있습니다")
    # ③ 화면의 단추와 **같은 판정**이다. `create_contact` 안에 또 있지만,
    #    거기서 걸리면 이미 몇 줄이 들어간 뒤다.
    if not sheet_owner.may_add_row(db, user, label):
        raise HTTPException(status_code=403, detail="이 명단에는 줄을 넣을 수 없습니다")

    ids = [int(x) for x in (body.company_ids or [])]
    if not ids:
        raise HTTPException(status_code=400, detail="보낼 기업을 고르세요")

    # **보이는 줄만.** 남의 줄을 번호로 찍는 길을 남기지 않는다 — 판정은
    # 표를 그릴 때와 같은 `scope()` 하나다(`get_company` 도 같은 뜻으로 막는다).
    companies = db.execute(
        scope(select(ConsultingCompany)
              .where(ConsultingCompany.id.in_(ids))
              .order_by(ConsultingCompany.position, ConsultingCompany.id),
              ConsultingCompany, user)
    ).scalars().all()
    if len(companies) != len(set(ids)):
        raise HTTPException(status_code=404, detail="기업을 찾을 수 없습니다")
    off = [c for c in companies if not is_startup(db, c.sheet)]
    if off:
        # **탭 이름을 여기 적지 않는다.** 화면에서 고칠 수 있는 값이라
        # (`ConsultingSheet.label`) 적어 두면 이름을 바꾼 날 이 안내만 옛
        # 이름으로 남는다 — 열쇠로 찾아 지금 이름을 읽는다.
        tab = next((s.label for s in cs.ensure(db) if s.kind == cs.STARTUP), "")
        raise HTTPException(status_code=400,
                            detail=f"`{tab}` 탭에서만 보낼 수 있습니다")

    # **이미 스타트업 명단에 있는 기업은 말없이 두 줄로 만들지 않는다.**
    # 판정은 표에 `있음` 표시를 다는 것과 같은 함수다(`company_rows`) — 두
    # 벌로 적으면 표에는 아무 표시가 없는데 눌러도 안 들어가는 줄이 생긴다.
    seen = startup_handoff.existing_firms(db)
    added: List[str] = []
    skipped: List[str] = []
    blank: List[int] = []
    for company in companies:
        fields = startup_handoff.contact_body(company)
        firm = fields["firm"]
        if not firm:
            # 기업명을 못 꺼낸 줄. `create_contact` 도 같은 이유로 막지만
            # (`Layout.required`) 그쪽은 400 을 내고 멈춰서, 나머지 줄까지
            # 통째로 못 들어간다. 여기서는 **그 줄만** 빼고 그렇다고 알린다.
            blank.append(company.id)
            continue
        key = startup_handoff.compare_key(firm)
        if key in seen:
            skipped.append(firm)
            continue
        # **줄을 세우는 길은 `POST /api/contacts` 하나다.** 여기서 `VcContact`
        # 를 직접 만들면 반드시 있어야 하는 칸(`Layout.required`)·담당
        # (`owner_for`)·권한(`may_add_row`)이 두 벌이 된다.
        made = create_contact(ContactIn(sheet=label, **fields), db, user)
        # **같은 요청 안의 중복도 막는다.** 같은 기업이 두 줄로 적힌 표가
        # 실제로 있어서, 둘 다 골라 누르면 스타트업 명단에 두 줄이 선다.
        seen[key] = made["id"]
        added.append(firm)

    return {
        "ok": True,
        "label": label,
        "owner": targets[label]["owner"],
        # **무엇이 어떻게 됐는지 그대로 돌려준다.** 몇 건인지만 주면 건너뛴
        # 기업이 무엇이었는지 알 수가 없어, 사람이 다시 표를 뒤져야 한다
        # (`contacts.transfer_contact` 가 `moved` 를 돌려주는 것과 같은 뜻이다).
        "added": added,
        "skipped": skipped,
        "blank": blank,
        # 돌아가서 확인할 화면. 주소를 화면에 못 박으면 명단이 사는 화면이
        # 바뀌는 날 남의 화면으로 튄다(`sheet_owner.page_href`).
        "href": f"{sheet_owner.page_href(db, label)}?sheet={quote(label)}",
    }


# --- 월별 열 ----------------------------------------------------------------

@router.post("/consulting/sheets/rename", include_in_schema=False)
def rename_sheet(kind: str = Form(""), label: str = Form(""),
                 db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    """탭 이름 바꾸기 — 투자사 관리 현황의 [이름 저장] 과 같은 방식·같은 어휘다.

    **줄이 같이 따라간다.** `ConsultingCompany.sheet` 와 `ConsultingColumn.sheet`
    가 이름을 그대로 담고 있어서, 이름만 바꾸면 그 줄들이 어느 탭에도 안 뜬다 —
    옛 이름의 유령 탭으로 갈라진다(0039 가 고쳐야 했던 그 사고). 옮기는 것은
    `services/consulting_sheets.rename` 한 곳이 한다.

    **바꾸는 것은 화면 글자뿐이다.** 표 모양은 바뀌지 않는 열쇠(`kind`)로
    고르므로(`SHEET_LAYOUTS`), `월간 계약 업무현황표` 를 다른 이름으로 불러도
    계약 표 그대로다.

    이 화면을 볼 수 있는 사람이면 바꿀 수 있다 — 투자사 관리 현황의 명단 이름
    바꾸기와 같은 권한이다. 수나 발송 대상이 바뀌는 조작이 아니라서(그런 것은
    관리자만 한다) 여기서 더 조이지 않는다.
    """
    require_access(user)
    sheet = cs.rename(db, (kind or "").strip(), label)
    if sheet is None:
        db.rollback()
        return RedirectResponse(
            "/consulting?msg=이미+쓰고+있는+탭+이름입니다", status_code=303)
    db.commit()
    return RedirectResponse(
        f"/consulting?sheet={quote(sheet.label)}", status_code=303)


@router.post("/consulting/columns", include_in_schema=False)
def add_column(label: str = Form(...), sheet: str = Form(""),
               db: Session = Depends(get_db),
               user: User = Depends(get_current_user)):
    """달이 바뀌면 칸을 하나 늘린다. 새 칸이 **맨 앞**에 오도록 한다.

    지금 챙겨야 할 달이 먼저 보여야 한다. (시트가 늘 그 순서인 것은 아니다 —
    `services/monthly_columns.py` 참고. 새로 세우는 자리를 정하는 것뿐이다.)

    **보고 있는 탭에 세운다.** 예전에는 탭을 안 받아서 어느 탭에서 눌러도 첫
    탭에 들어갔다 — 누른 사람 화면에는 아무것도 안 늘어난다. 칸이 탭마다인
    지금은 그 어긋남이 곧 남의 탭에 칸을 하나 세우는 일이다.
    """
    # **세우는 것은 지금까지 그대로 열려 있다.** 이 화면을 쓰는 사람이면
    # 누구나다. 칸이 탭에 붙게 되었어도 여기서는 규칙을 좁히지 않는다 —
    # 달 칸이 하나도 없는 탭은 본이 없어 자동 생성이 아예 안 붙고
    # (`services/monthly_columns.py`), 그 첫 칸을 심는 것이 이 자리다.
    # 좁히면 새 탭의 첫 달을 관리자를 불러야 세울 수 있다.
    #
    # 좁힌 것은 **지우고 이름을 바꾸는 쪽**뿐이다(`may_edit_column`) — 그쪽은
    # 한 번 누르면 팀 전체의 기록이 사라진다.
    require_access(user)
    label = label.strip()
    known = {t.label for t in cs.all_sheets(db)}
    # 없는 탭 이름이 실려 오면 첫 탭으로 돌린다 — 모델 기본값(`스타트업`)에
    # 떨어뜨리면 탭 이름을 고친 뒤에는 그 이름을 쓰는 탭이 없어서 새 칸이
    # 유령 탭에 쌓인다.
    name = sheet if sheet in known else cs.default_label(db)
    back = f"/consulting?sheet={quote(name)}"
    if not label:
        return RedirectResponse(f"{back}&msg=열+이름을+입력하세요", status_code=303)
    for col in _columns(db, name):
        col.position += 1
    db.add(ConsultingColumn(label=label, position=0, sheet=name))
    db.commit()
    return RedirectResponse(f"{back}&msg={quote(label)}+열을+추가했습니다",
                            status_code=303)


@router.post("/consulting/columns/{column_id}/rename", include_in_schema=False)
def rename_column(column_id: int, label: str = Form(...),
                  db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    require_access(user)
    # 칸은 탭마다 한 벌이라 이름을 바꾸면 **팀 전체의 머리글**이 바뀐다.
    # 그래서 관리자만이다(`may_edit_column`). 없는 번호와 같은 404 로 답한다 —
    # 갈라 주면 번호를 훑어 남의 표가 몇 번까지 있는지 알 수 있다.
    col = _editable_column(db, column_id, user)
    if label.strip():
        col.label = label.strip()
        db.commit()
    return RedirectResponse("/consulting?msg=열+이름을+바꿨습니다", status_code=303)


@router.post("/consulting/columns/{column_id}/delete", include_in_schema=False)
def delete_column(column_id: int, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    """열을 지우면 그 달의 기록도 함께 사라진다 — 화면에서 한 번 더 묻는다."""
    require_access(user)
    col = _editable_column(db, column_id, user)
    key = str(col.id)
    # **탭 전체를 훑는다.** 칸이 탭마다 한 벌이라 그 칸에 적힌 기록은 담당을
    # 가리지 않고 흩어져 있다 — 자기 줄만 훑으면 남의 줄에 그 칸을 가리키는
    # 열쇠가 남아, 어느 칸의 것인지 모르는 값이 JSON 에 쌓인다
    # (`routers/contacts.py` 의 `delete_column` 이 같은 이유로 전체를 훑는다).
    # 이것을 관리자만 누를 수 있게 한 것이 `may_edit_column` 이다.
    for company in db.execute(
        select(ConsultingCompany).where(ConsultingCompany.sheet == col.sheet)
    ).scalars().all():
        notes = _notes(company)
        if key in notes:
            notes.pop(key)
            company.notes = json.dumps(notes, ensure_ascii=False)
    db.delete(col)
    db.commit()
    return RedirectResponse("/consulting?msg=열을+삭제했습니다", status_code=303)


# --- 업로드 · 내려받기 ------------------------------------------------------

@router.post("/consulting/import", include_in_schema=False)
def import_sheet(file: UploadFile = File(...), sheet: str = Form(""),
                 replace: bool = Form(False),
                 db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    """원본 시트를 올려 통째로 반영한다.

    이 표는 시트가 원본이라 '한 줄씩 맞추기'보다 **통째로 갈아끼우는** 편이 맞다.
    다만 여기서 고친 내용이 날아갈 수 있으므로 화면에서 한 번 더 확인받는다.
    """
    require_access(user)
    data = file.file.read()
    try:
        rows = sp.read_rows(file.filename or "", data, sheet or None)
    except sp.SpreadsheetError as exc:
        return RedirectResponse(f"/consulting?msg={exc}", status_code=303)

    parsed = parse_rows(rows)
    if not parsed["companies"]:
        return RedirectResponse(
            "/consulting?msg=읽을+내용을+찾지+못했습니다.+'NO'와+'기업명'이+있는+시트인지+확인하세요",
            status_code=303)

    report = apply_rows(db, parsed, user, replace=replace)
    return RedirectResponse(
        f"/consulting?msg=기업+{report['created']}건+추가·{report['updated']}건+갱신"
        f"+(열+{report['columns']}개)",
        status_code=303)


# 두 탭(`관리 스타트업` · `경영본부 전달 기업`)에 **나중에 늘어난** 고정 칸.
# 화면 차례는 `미팅일` 바로 뒤지만 **엑셀에서는 맨 뒤**다 — 이 목록의 차례는
# 화면 차례가 아니라 **이미 내려받아 둔 파일의 차례**이고, 앞에 끼우면 그 뒤
# 월 열이 통째로 한 칸씩 밀려 지난번 파일과 나란히 놓고 볼 수가 없다(아래
# `CONTRACT_EXPORT_HEADERS` · `STARTUP_EXPORT_HEADERS` 가 같은 이유로 뒤에 있다).
#
# **여기 적힌 칸은 앞 묶음에서 빠진다.** `CONSULTING_EXPORT_HEADERS` 가
# `FIXED_COLUMNS` 에서 뽑는데, 빼 두지 않으면 같은 칸이 머리글 두 자리에 서고
# (실제로 그렇게 났다) 값을 손으로 세우는 아래 줄과 칸 수가 어긋나 **그 뒤
# 값이 통째로 한 칸씩 밀린다.** 기업명 자리에 지역이 찍히는 식이다.
FIXED_EXTRA_EXPORT = [("미팅종류", "meeting_kind"), ("기업 내용", "management_detail")]
_EXTRA_EXPORT_FIELDS = {field for _label, field in FIXED_EXTRA_EXPORT}

CONSULTING_EXPORT_HEADERS = [label for label, field in FIXED_COLUMNS
                             if field not in _EXTRA_EXPORT_FIELDS]
# 계약 탭에만 값이 있는 칸. 엑셀은 탭을 가리지 않고 한 장으로 내려받으므로
# **머리글 한 벌**에 뒤로 붙인다 — 탭마다 다른 장을 만들면 내려받은 파일에서
# 어느 장이 무엇인지 다시 맞춰야 한다. 다른 탭 줄에서는 빈 칸이다.
CONTRACT_EXPORT_HEADERS = ["성공보수율", "계약금", "계약서 수신여부"]
# 스타트업 탭에만 값이 있는 칸. **엑셀에는 싣는다** — 화면에 보이는 칸이
# 내려받은 파일에만 없으면, 없다는 사실 자체를 아무도 눈치채지 못한 채 그
# 파일이 보고서로 돌아다닌다. 바로 옆 `기업 관리` 도 같은 성격의 긴 글인데
# 이미 실려 있어서, 둘 중 하나만 빠지면 그게 더 이상하다.
#
# 자리는 **맨 뒤**다. 화면 순서대로 `기업 관리` 옆에 끼우면 그 뒤 월 열이
# 통째로 한 칸씩 밀려, 지난번에 내려받아 둔 파일과 나란히 놓고 볼 수가 없다
# (계약 탭 칸들도 같은 이유로 뒤에 붙어 있다).
#
# 새로 느는 칸도 **`딜 소개문구` 뒤에** 붙인다. 화면 차례(`기업 관리` 바로 뒤)
# 대로 끼우면 그 뒤 월 열이 통째로 밀려, 지난번에 내려받아 둔 파일과 나란히
# 놓고 볼 수가 없다 — 이 목록의 차례는 화면 차례가 아니라 **이미 내려받아 둔
# 파일의 차례**다.
#
# **`계약서 수신완료여부` 는 여기 없다.** 그 칸은 계약 탭과 같은
# `contract_received` 라 위 `CONTRACT_EXPORT_HEADERS` 의 `계약서 수신여부` 로
# 이미 실린다. 엑셀은 탭을 가리지 않고 한 장이므로 여기 또 세우면 **같은 값이
# 두 칸에** 나오고, 그 파일을 여는 사람은 둘이 다른 사실인 줄 안다.
STARTUP_EXPORT_HEADERS = ["딜 소개문구", "견적서 첨부 여부", "계약완료여부",
                          "카톡 연결 여부"]


@router.get("/api/export/consulting.xlsx")
def export_consulting(db: Session = Depends(get_db),
                      user: User = Depends(get_current_user)):
    require_access(user)
    # 탭을 가리지 않고 한 장으로 내려받으므로 칸도 전부 세운다. 담당으로는
    # 안 갈린다 — 칸은 탭마다 한 벌이다(`models.ConsultingColumn`).
    cols = _columns(db)
    # **화면과 같은 칸이 선다.** 여러 사람의 표를 한 파일로 내려받으면서 담당이
    # 없으면 누구 줄인지 알 수 없다 — 화면에는 `담당` 칸이 서 있는데 받은
    # 파일에만 없으면, 그 파일을 여는 사람은 55줄을 한 사람 것으로 읽는다.
    # 자기 것만 보는 사람에게는 안 세운다(같은 이름이 줄마다 반복될 뿐이다).
    owned_col = may_view_all_consulting(user)
    headers = (CONSULTING_EXPORT_HEADERS + (["담당"] if owned_col else [])
               + [c.label for c in cols]
               + [label for label, _ in TAIL_COLUMNS] + CONTRACT_EXPORT_HEADERS
               + STARTUP_EXPORT_HEADERS
               + [label for label, _field in FIXED_EXTRA_EXPORT])
    rows = [
        [r["no"], r["region"], r["meeting_at"], r["company_name"], r["management"]]
        + ([r["owner_name"]] if owned_col else [])
        + [r["notes"].get(str(c.id), "") for c in cols]
        + [r["ceo_name"], r["phone"], r["email"]]
        + [r["success_fee"], r["contract_fee"], r["contract_received"]]
        + [r["deal_pitch"], r["contract_management"], r["contract_done"],
           r["kakao_joined"]]
        + [r[field] for _label, field in FIXED_EXTRA_EXPORT]
        for r in company_rows(db, user)
    ]
    try:
        content = sp.write_xlsx("투자컨설턴트 현황", headers, rows)
    except sp.SpreadsheetError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    from datetime import date

    return Response(content=content, media_type=sp.XLSX_MEDIA_TYPE,
                    headers=sp.content_disposition(
                        f"투자컨설턴트 현황_{date.today().isoformat()}.xlsx"))


# --- 시트 읽기 --------------------------------------------------------------

def _norm(value) -> str:
    return " ".join(str(value or "").split())


def parse_rows(rows: List[List[str]]) -> dict:
    """시트 → {열 이름들, 기업 행들}.

    머리행은 위치가 아니라 **내용**으로 찾는다. 시트 위쪽에 제목·빈 줄이 있고
    사람이 행을 넣다 빼다 하므로 '4번째 줄'이라고 못 박으면 곧 깨진다.
    """
    header_idx = None
    for i, row in enumerate(rows[:30]):
        cells = [_norm(c) for c in row]
        if "NO" in cells and any("기업" in c for c in cells):
            header_idx = i
            break
    if header_idx is None:
        return {"columns": [], "companies": []}

    header = [_norm(c) for c in rows[header_idx]]

    def find(*tokens) -> Optional[int]:
        for j, h in enumerate(header):
            if all(t in h for t in tokens):
                return j
        return None

    def fixed(*tokens, without: tuple = ()) -> Optional[int]:
        """**월 열이 아닌 것 중에서** 찾는다.

        `계약 관리`·`계약완료` 같은 말은 월별 리마인드 열 이름에도 들어갈 수
        있다(`10월 계약 관리 확인`). `find` 로 찾으면 그런 열을 채가서,
        그 달 기록이 갈 곳을 잃은 채 조용히 사라진다 — 아래 `note_cols` 는
        여기서 집어 간 열을 빼고 세기 때문이다.

        달이 적힌 이름은 월 열이라는 뜻이니 건너뛴다. 달을 읽는 규칙은
        `services/monthly_columns.py` 한 곳이고 여기서 다시 적지 않는다.

        `without` 은 **옆 칸을 채가지 않게** 하는 자리다. 이 탭의 머리글 셋은
        서로의 낱말을 품고 있어서(`계약서 수신완료여부` 안에 `계약`·`완료` 가
        들어 있다) 토막만으로 가르면 한 열을 두 칸이 집어 간다 — 그러면 같은
        값이 두 칸에 담기고, 정작 제 칸은 빈 채로 남는다.
        """
        for j, h in enumerate(header):
            if monthly_columns.month_of(h) is None \
                    and all(t in h for t in tokens) \
                    and not any(t in h for t in without):
                return j
        return None

    idx = {
        "position": find("NO"),
        "region": find("지역"),
        "meeting_at": find("미팅일"),
        "company_name": find("기업명"),
        "management": find("기업 관리"),
        # 시트에 `기업 내용` 열이 있으면 여기로 받는다. 안 받으면 월별 리마인드
        # 열로 딸려 들어가 같은 이름이 표에 두 번 선다(아래 `note_cols`).
        #
        # **위 `기업 관리` 와 안 겹친다.** 저쪽은 `기업 관리` 가 든 머리글만
        # 집고 이쪽은 `기업`+`내용` 둘 다 든 머리글만 집는다 —
        # `기업 관리 [ 드랍 이유 상세하게 기입 … ]` 에는 `내용` 이 없다.
        # 달이 적힌 이름(`9월 리마인드 내용`)은 `fixed` 가 이미 건너뛴다.
        "management_detail": fixed("기업", "내용"),
        # 원본 시트에도 이 세 칸이 있을 수 있다. 여기서 안 받으면 **월별
        # 리마인드 열로 딸려 들어간다** — 아래 `note_cols` 가 못 알아본 열을
        # 전부 월 열로 삼기 때문이다. 그러면 같은 이름이 표에 두 번 서고
        # (전용 칸은 빈 채로) 값은 엉뚱한 쪽에 담긴다.
        #
        # 토막을 둘씩 준다 — 시트에 `견적서 첨부여부` 로 붙여 적혀 있을 수도,
        # `계약 완료 여부` 로 띄어 적혀 있을 수도 있다.
        #
        # 뒤의 둘이 서로의 낱말을 품고 있어서 `without` 으로 갈라 준다. 시트에
        # `계약완료여부` 칸 없이 `계약서 수신완료여부` 만 있으면, 그냥
        # `계약`+`완료` 로 찾을 때 그 한 열을 두 칸이 같이 집어 간다.
        #
        # **첫 칸은 `계약`+`관리` 가 아니라 `견적서`+`첨부` 로 찾는다.** 화면
        # 이름이 `견적서 첨부 여부` 로 바뀌면서 값이 `O`/`X` 가 됐는데, 시트의
        # `계약 관리` 열은 아직 자유 문장(`관리 중 : 미팅 완 …`)이라 그대로
        # 받으면 두 글자만 서야 할 칸에 문단이 들어온다 — 그 순간 머리글
        # 필터가 줄마다 다른 값으로 갈려 못 쓰게 된다. 그 열은 이제 월별
        # 리마인드 열로 들어가 **기록으로 남는다**(아래 `note_cols`).
        "contract_management": fixed("견적서", "첨부"),
        "contract_done": fixed("계약", "완료", without=("수신", "관리")),
        "contract_received": fixed("계약서", "수신"),
        # 시트에 `카톡 연결 여부` 열이 있으면 여기로 받는다. 안 받으면 월별
        # 리마인드 열로 딸려 들어가 같은 이름이 표에 두 번 선다(위 참고).
        #
        # 달이 적힌 이름(`9월 카톡 연결`)은 `fixed` 가 이미 건너뛴다 — 그런
        # 이름은 `스타트업` 명단이 달마다 세우는 칸이고
        # (`services/contact_columns.py`), 이 표에서는 월별 리마인드 열로
        # 남아야 한다. 그 달 기록을 한 칸에 뭉쳐 덮으면 어느 달 값이 남았는지
        # 알 수 없게 된다.
        "kakao_joined": fixed("카톡", "연결"),
        # 시트에 `미팅종류` 열이 있으면 여기로 받는다. 안 받으면 월별 리마인드
        # 열로 딸려 들어가 같은 이름이 표에 두 번 선다(위 참고).
        #
        # **`미팅일` 과 안 겹친다.** `find("미팅일")` 은 `미팅일` 이 든 머리글만
        # 집고 이쪽은 `미팅`+`종류` 둘 다 든 머리글만 집는다 — `미팅일(화상,
        # 회의실)` 에는 `종류` 가 없고 `미팅종류` 에는 `미팅일` 이 없다.
        "meeting_kind": fixed("미팅", "종류"),
        "ceo_name": find("대표자"),
        "phone": find("연락처"),
        "email": find("이메일"),
    }
    # 나머지 = 월별 리마인드 열. 이름을 그대로 쓴다(시트와 같아 보여야 한다).
    used = {v for v in idx.values() if v is not None}
    note_cols = [(j, header[j]) for j in range(len(header))
                 if j not in used and header[j]]

    companies = []
    for row in rows[header_idx + 1:]:
        cells = list(row) + [""] * (len(header) - len(row))
        name = _norm(cells[idx["company_name"]]) if idx["company_name"] is not None else ""
        no = _norm(cells[idx["position"]]) if idx["position"] is not None else ""
        if not name and not no:
            continue
        if not name:
            continue        # 번호만 있고 기업명이 없는 줄은 빈 칸이다
        item = {"notes": {}}
        for field, j in idx.items():
            if j is None:
                continue
            raw = cells[j]
            item[field] = _norm(raw)
        for j, label in note_cols:
            text = _norm(cells[j])
            if text:
                item["notes"][label] = text
        companies.append(item)

    return {"columns": [label for _j, label in note_cols], "companies": companies}


def apply_rows(db: Session, parsed: dict, user: User,
               replace: bool = False) -> dict:
    """읽은 내용을 DB 에 반영. 기업명이 같으면 갱신, 없으면 추가.

    올린 사람의 표가 된다 — 남의 표를 덮지 않는다.
    """
    if replace:
        # **내 것만** 지운다. 예전에는 전체를 지워서, 한 사람이 다시 올리면
        # 다른 컨설턴트의 표까지 사라졌다.
        db.query(ConsultingCompany).filter(
            ConsultingCompany.user_id == user.id).delete()
        db.commit()

    # 열 먼저 — 기업의 notes 가 열 id 를 키로 쓴다.
    #
    # **이름이 같으면 이미 있는 칸을 그대로 쓴다.** 칸은 탭마다 한 벌이라
    # (`models.ConsultingColumn`) 여기서 새로 만들면 팀이 쓰던 머리글 옆에
    # 같은 이름의 칸이 하나 더 서고, 올린 사람의 기록만 새 칸으로 간다.
    sheet_name = cs.default_label(db)
    existing_cols = {c.label: c for c in _columns(db, sheet_name)}
    for pos, label in enumerate(parsed["columns"]):
        col = existing_cols.get(label)
        if col is None:
            col = ConsultingColumn(label=label, position=pos, sheet=sheet_name)
            db.add(col)
            existing_cols[label] = col
    db.flush()

    # 같은 기업명이 다른 사람 표에도 있을 수 있다 — 내 표 안에서만 맞춘다.
    by_name = {(c.company_name or "").strip(): c
               for c in db.execute(own(select(ConsultingCompany),
                                       ConsultingCompany, user)).scalars().all()}

    created = updated = 0
    for item in parsed["companies"]:
        name = item.get("company_name", "")
        company = by_name.get(name)
        if company is None:
            company = ConsultingCompany(user_id=user.id)
            db.add(company)
            by_name[name] = company
            created += 1
        else:
            updated += 1
        for field in ("region", "meeting_at", "meeting_kind", "company_name",
                      "management", "management_detail", "ceo_name", "phone", "email",
                      "contract_management", "contract_done",
                      "contract_received", "kakao_joined"):
            value = item.get(field)
            if value:
                setattr(company, field, value)
        raw_no = item.get("position") or ""
        digits = "".join(ch for ch in raw_no if ch.isdigit())
        if digits:
            company.position = int(digits)
        notes = _notes(company)
        for label, text in item["notes"].items():
            col = existing_cols.get(label)
            if col is not None:
                notes[str(col.id)] = text
        company.notes = json.dumps(notes, ensure_ascii=False)

    db.commit()
    return {"created": created, "updated": updated,
            "columns": len(parsed["columns"])}
