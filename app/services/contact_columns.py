"""명단(시트)마다 다른 표 — **칸이 정해지는 한 곳**.

투자사 관리 현황에는 명단별 탭이 있는데, 그중 성격이 다른 명단이 섞여 있었다.
스타트업 리마인드 명단은 투자사 명함 칸(`부서`·`직함`·`근무처 팩스`·`명함
등록일`)을 그대로 쓰고 있어서 대부분의 칸이 비어 있었다. 겹치는 것은 이름과
연락처뿐이다.

## 왜 여기 모았나

탭마다 화면에 `{% if 이 탭이면 %}` 을 심으면, 성격이 다른 명단이 하나 더 들어올
때마다 화면·임포트·수정창·엑셀에 같은 조건을 또 심어야 한다. 심는 것을 잊은
곳만 조용히 옛 칸을 보여 준다 — 그런 어긋남은 화면이 멀쩡해 보여서 아무도
눈치채지 못한다.

그래서 **배치(layout)** 하나만 여기서 정하고, 어느 명단이 어느 배치를 쓰는지는
`SheetOwner.layout` 에 **값으로** 둔다. 명단 이름은 코드가 몰라도 된다.

## 칸이 어디서 오나

세 갈래다. 셋 다 `columns()` 하나로 나오므로 화면은 갈래를 몰라도 된다.

    field  VcContact 의 칸 (`firm`·`name`·`phone`·`email`·`memo`)
           투자사와 스타트업이 **같은 뜻으로** 쓰는 값이다. 따로 만들면 같은
           사람의 연락처가 두 군데에 갈린다.
    note   그 명단에만 있는 칸 (`사업분야 대분류`·`계약여부` …)
           `VcContact.notes` 에 고정 키로 담는다. 306행 전체가 한 명단에서만
           쓰는 빈 칸을 지고 다니지 않게.
    month  **달마다 늘어나는 칸** (`7월 리마인드 문자 (7/28)` …)
           `ContactColumn` 행으로 둔다 — 아래 참고.

## 달마다 늘어나는 칸을 왜 행으로 두나

`7월 리마인드 문자 (7/28)` · `7월 리마인드 TEL` · `7월 카톡 연결` 은 한 달에 세
칸씩 늘어난다. 테이블 컬럼으로 두면 **달이 바뀔 때마다 마이그레이션**을 하고
배포해야 한다.

`투자컨설턴트 현황`(`app/routers/consulting.py` · `ConsultingColumn`)이 같은
문제를 이미 그렇게 풀어 두었다. **그 방식을 그대로 따른다** — 같은 모양을 두
가지 방식으로 풀면 다음 사람이 어느 쪽을 고쳐야 할지 모른다. 열 이름을 그대로
보관하고(시트와 같아 보여야 한다), 값은 행의 JSON 에 열 id 를 키로 담고,
최근 몇 칸만 펴 두고 나머지는 접는다.

딱 한 군데만 다르다. 저쪽 열은 **사람마다**인데(각자 올린 시트의 달이 다르다)
이쪽은 **명단마다**다 — 여기서 열을 정하는 것은 올린 사람이 아니라 원본
시트이고, 명단은 담당이 바뀌어도 같은 명단이기 때문이다.

## 머리글 이름은 시트 그대로

원본 시트를 쓰던 사람이 자기 칸을 찾을 수 있어야 한다. 오타처럼 보이는 것도
(`IR dack 유무`) 고치지 않는다 — 고치는 순간 시트와 나란히 놓고 대조할 수 없다.
줄바꿈만 공백으로 편다(머리글 한 칸에 두 줄로 들어 있던 것이다).
"""
from __future__ import annotations

import json
from datetime import date
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import ContactColumn
from . import monthly_columns

# 배치를 쓰는 명단이 뜨는 화면(= 주소 조각). `Layout.page` 참고.
PAGE_CONTACTS = "contacts"
PAGE_STARTUP = "startup"

# 배치 이름. `SheetOwner.layout` 에 이 값이 들어간다.
INVESTOR = "investor"
STARTUP = "startup"
# 투자사인데 **달마다 칸이 늘어나는** 명단. 아래 INVESTOR_MONTHLY_LAYOUT 참고.
INVESTOR_MONTHLY = "investor_monthly"
DEFAULT = INVESTOR


@dataclass(frozen=True)
class Column:
    """표의 칸 하나. 머리글·폭·고치는 방식이 여기서 한 번에 정해진다."""

    label: str                  # 머리글 — **원본 시트 그대로**
    key: str                    # 행이 싣는 이름 (field 면 모델 칸, note 면 notes 키)
    width: int                  # px. 값 길이에 맞춘다(머리글 길이가 아니라)
    source: str = "field"       # field | note | row_no | actions
    kind: str = "text"          # text | long | pick — 어떻게 고치나
    choices: str = ""           # pick 일 때 정해진 보기 (`O,X`)
    hint: str = ""              # 수정창의 placeholder. **이름이 아니다**
    in_table: bool = True       # 표에 세울까 (False = 수정창에서만)


@dataclass(frozen=True)
class Layout:
    """한 명단이 쓰는 칸 묶음 — 그리고 그 명단이 **어느 화면에 사는가**."""

    key: str
    label: str
    # 이 배치를 쓰는 명단이 뜨는 화면. 주소 조각과 같다(`contacts` · `startup`),
    # `RefSheet.page` 와 같은 값이고 같은 뜻이다.
    #
    # **왜 배치가 화면을 정하나.** 명단이 어느 화면에 사는지는 새 칸(`SheetOwner.
    # page`)으로도 둘 수 있었다. 두지 않은 이유는 그러면 명단마다 값이 **둘**이
    # 되기 때문이다 — 새 명단을 넣는 사람이 배치만 맞추고 화면을 빠뜨리면,
    # 스타트업 칸을 쓰는 명단이 투자사 관리 현황에 서거나 그 반대가 된다.
    # 화면은 멀쩡하고 아무도 눈치채지 못하는 부류다(이 저장소가 반복해 당했다).
    #
    # 배치는 이미 **그 명단이 어떤 명단인지**를 가리킨다. `startup` 배치의 이름은
    # `스타트업 리마인드` 이고 머리글이 `기업명`·`성함` 이며 투자사로 세지 않는다
    # — 아래 `INVESTOR_MONTHLY_LAYOUT` 주석이 저 배치를 돌려 쓰지 않은 이유로
    # 바로 그것을 든다. 그래서 값을 하나 더 두지 않고 배치에 붙인다.
    #
    # 사람이 화면에서 켜고 끄는 값(`SheetOwner.is_hidden`)으로 가르지 않는 이유도
    # 같다 — 그 단추 한 번에 명단이 화면을 옮겨 다니면 어디서 고쳐야 할지 모른다.
    page: str = "contacts"
    # 월별 칸 **앞**에 서는 고정 칸들
    head: List[Column] = field(default_factory=list)
    # 월별 칸 **뒤**에 서는 고정 칸들
    tail: List[Column] = field(default_factory=list)
    # 표에는 안 세우고 수정창에서만 보는 칸들
    extra: List[Column] = field(default_factory=list)
    # 달마다 늘어나는 칸을 쓰는 배치인가
    monthly: bool = False
    # 달마다 늘어나는 칸을 **어떻게 고치고 보여 주나.** 배치마다 그 칸에 들어가는
    # 값의 성격이 다르다 — 스타트업 리마인드는 `O`/`X` 한 글자라 골라 넣게 하고
    # 필터를 걸지만, 투자사 딜공유는 한 칸이 회차별 기업 목록(가장 긴 줄이 400자
    # 넘는다)이라 고르는 칸으로 두면 **고치는 순간 그 달 기록이 `O` 한 글자로
    # 덮인다.** 값이 130가지라 필터로도 고를 것이 없다.
    #
    # 칸마다가 아니라 **배치마다** 정하는 이유: `ContactColumn` 에 종류를 두면
    # 마이그레이션이 필요하고, 같은 명단 안에서 칸마다 성격이 갈릴 일은 없다
    # (한 시트의 월별 칸은 다 같은 모양이다).
    month_kind: str = "pick"
    month_choices: str = "O,X"
    month_width: int = 186


# ── 투자사 명함 (지금까지의 표) ──────────────────────────────────────────────
#
# 이 배치의 표는 `contacts.html` 에 그대로 적혀 있다. 옮겨 오지 않은 이유는
# 하나다 — 이 저장소의 화면 검사(`tests/test_ui_layout.py`)가 템플릿 글자를
# **정적으로** 읽어 머리글 폭·정렬·수정창 라벨 짝을 본다. 반복문으로 세운
# 머리글은 값이 실행 때 정해져서 그 검사들이 **조용히 건너뛴다**. 스무 칸짜리
# 표에서 그 검사를 잃는 대가가, 한 곳으로 모아 얻는 것보다 크다.
#
# 대신 여기서는 **어느 명단이 이 배치인가**만 정한다. 그것이 탭마다 하드코딩을
# 부르던 부분이다.
#
# `monthly=False` 는 **표에 안 세운다**는 뜻이지 "그런 칸이 없다"는 뜻이 아니다.
# 이 배치를 쓰면서도 달마다의 기록을 가진 명단이 있다(딜공유 명단을 이 표로
# 맞춘 것들). 그 칸들은 표에 못 선다 — 표가 여기 그대로 적혀 있어 반복문이
# 들어갈 자리가 없고, 넣는다 해도 스물다섯 칸짜리 표가 스물다섯+열다섯 칸이
# 되어 **맞추라고 한 그 모양이 아니게 된다.** 대신 **수정창에 전부 편다**
# (`contacts.html` 의 그 자리 주석 참고) — 값은 그대로 남고, 칸 이름도 시트
# 그대로 서고, 저장·되읽기는 이미 `data-note` 로 일반화돼 있다.
#
# 칸이 있는지는 **명단이 정한다**(그 명단에 `ContactColumn` 줄이 있느냐).
# 배치가 정하지 않는다 — 같은 배치를 쓰는 명단 중 어떤 것은 달 칸이 있고
# 어떤 것은 없다(`routers/pages.py` 의 `all_months` 주석 참고).
INVESTOR_LAYOUT = Layout(
    key=INVESTOR, label="투자사 명함",
    # 한 칸에 회차별 기업 목록이 줄바꿈으로 쌓인다 — 고르는 칸이 아니라 글 칸이다.
    # (`INVESTOR_MONTHLY_LAYOUT` 과 같은 값이어야 한다. 배치를 바꿨다고 같은
    # 값이 `O`/`X` 고르기로 서면, 한 번 고치는 순간 그 달 기록이 한 글자로 덮인다.)
    month_kind="long", month_choices="", month_width=240)


# ── 스타트업 리마인드 ────────────────────────────────────────────────────────
#
# 폭은 **값의 길이**로 잡았다(90%가 들어가는 선). 머리글 길이로 잡으면 값이
# 짧은 칸이 넓은 자리를 먹는다.
STARTUP_LAYOUT = Layout(
    key=STARTUP,
    label="스타트업 리마인드",
    # 이 배치를 쓰는 명단은 좌측 [스타트업] 화면에 선다 — 투자사
    # 관리 현황이 아니다. 두 곳에 다 뜨면 어느 쪽이 최신인지 알 수 없다.
    page=PAGE_STARTUP,
    monthly=True,
    head=[
        Column("NO", "no", 34, source="row_no"),
        # 기업명·성함이 **따로** 적힌다. 투자사 명단은 사람이 주인공이라
        # `이름`·`회사` 였는데, 여기는 기업이 주인공이라 순서가 뒤집힌다.
        Column("기업명", "firm", 180),
        Column("성함", "name", 84),
        Column("연락처", "phone", 116),
        Column("이메일", "email", 180),
        # 계약까지 갔는가. **표에 세우고, 이메일 바로 뒤에 둔다.**
        #
        # 달마다 칸이 세 개씩 붙는 표라 월별 칸 뒤(`tail`)에 두면 표 맨 끝에
        # 선다 — 달이 쌓일수록 가로로 밀어야 닿는 자리로 물러난다. 이 칸은
        # 명단을 훑을 때 **기업을 보는 순간 같이 읽는 값**이라(계약된 곳인지에
        # 따라 그 달에 보낼 말이 다르다) 사람 정보 바로 뒤가 제자리다.
        #
        # 보기는 IR 기업 현황의 계약 상태와 **같은 말**이다
        # (`routers/companies.py` 의 `CONTRACT_LABELS`). 같은 것을 두 화면에서
        # 다른 말로 부르면 어느 쪽이 맞는지 알 수 없다.
        #
        # 딱 하나, `딜소개 불가` 는 여기 두지 않는다. 그것은 계약 상태가 아니라
        # **발송 금지 표시**이고, 발송 목록을 만드는 것은 IR 기업 현황이다
        # (`companies.BLOCKED_CONTRACT` 가 거기서 기업을 빼낸다). 여기에 두면
        # 골라 놓고 막힌 줄 아는데 실제로는 아무것도 안 막는 칸이 된다.
        #
        # 폭은 값을 고른 뒤의 단추(`계약여부 (1) ▾` = 102px)에 맞춘다.
        # 줄이면 머리글의 필터 꼬리표가 두 줄로 접힌다
        # (`tests/test_startup_tab.py` 의 `머리글은_필터_단추까지_한_줄에_들어간다`).
        Column("계약여부", "contract", 110, source="note", kind="pick",
               choices="유료계약완료,무료계약완료,계약검토중,미계약"),
    ],
    tail=[
        # 회신은 왔는가. 값이 `O`/`X` 둘뿐이라 골라 넣게 한다 —
        # 새로 타이핑하면 `o`·`△` 로 갈려 세는 것이 달라진다.
        Column("IR 자료 회신 여부", "ir_reply", 150, source="note",
               kind="pick", choices="O,X"),
        # 원본 메모가 길다(가장 긴 줄이 233자). 표에서는 두 줄까지만 보이고
        # (`.clamp2`) 전문은 수정창에서 본다 — 그대로 펼치면 줄 높이가 무너져
        # 서른두 줄을 훑을 수가 없다.
        Column("메모 ( 통화내용 /  카톡내용  /  카톡답신내용)", "memo", 250,
               kind="long"),
    ],
    extra=[
        # 표에 세우면 열여섯 칸이 되어 정작 매달 보는 칸이 눌린다.
        # 값은 그대로 들어가고, 수정창에서 보고 고친다.
        Column("사업분야 대분류", "sector_major", 0, source="note",
               kind="pick", in_table=False),
        Column("소분류", "sector_minor", 0, source="note",
               kind="pick", in_table=False),
        Column("기업구분", "company_kind", 0, source="note",
               kind="pick", in_table=False,
               hint="Angel, Seed (누적투자금 0, 년매출액 3억미만)"),
        # 머리글 한 칸에 이름과 **적는 법**이 같이 들어 있었다. 이 저장소는
        # 입력 형식 안내를 이름에 섞지 않는다 — 표 머리글과 글자가 달라져
        # 같은 칸인지 알아볼 수 없게 된다. 안내는 placeholder 로 옮긴다.
        Column("한줄 소개", "one_liner", 0, source="note",
               kind="long", in_table=False,
               hint="사업분야 | 최근년매출 | 누적투자금액 | "
                    "투자유치희망금액 I Pre value ㅣ특이사항"),
        # 시트에 `IR dack` 이라고 적혀 있다. **고치지 않는다** —
        # 시트와 나란히 놓고 대조하는 칸이라 이름이 다르면 그때마다 멈춘다.
        Column("IR dack 유무", "ir_deck", 0, source="note",
               kind="pick", choices="O,X", in_table=False),
        # 금액·비율은 **적힌 그대로** 둔다. `2.5%` 인지 `2.5` 인지, `900,000` 인지
        # `90만` 인지는 계약서에 적힌 말이라 앱이 고쳐 쓸 것이 아니다.
        Column("성공보수율 %", "success_fee", 0, source="note", in_table=False),
        # 담당자 워크북에서 온 두 칸. **달마다 늘어나는 칸이 아니라서** 여기 둔다.
        #
        # 남는 머리글은 전부 월별 칸으로 서는데(`import_startup_sheet.parse`),
        # 이 배치의 월별 칸은 `O`/`X` 고르기다(`month_kind="pick"`). 이 둘을
        # 거기 두면 **한 번 고치는 순간 적힌 글이 한 글자로 덮인다** — 위
        # `INVESTOR_LAYOUT` 주석이 든 것과 같은 사고다. 게다가 시트에서 이 둘이
        # 앞에 적혀 있어 월별 칸의 맨 앞자리를 먹는다: `VISIBLE_MONTHS` 가 1이라
        # 정작 그 달의 기록이 접히고 표에는 이 칸만 선다.
        #
        # 표에 안 세우는 이유는 옆 칸들과 같다 — 매달 보는 칸이 눌린다.
        Column("원본NO", "origin_no", 0, source="note", in_table=False,
               hint="담당자 워크북의 원본 명단 번호"),
        # **우리 팀 안에서 넘긴 이력**이다(`7/21 김담당 -> 8/19 이담당`).
        # 스타트업 쪽 담당자가 아니라서 `성함` 이 아니다 — 거기 넣으면 기업의
        # 연락 상대 자리에 우리 팀원 이름이 앉는다.
        #
        # 넘긴 날짜가 화살표로 쌓여 한 줄이 길어지므로 `long` 이다.
        Column("담당 이력", "owner_history", 0, source="note",
               kind="long", in_table=False,
               hint="7/21 김담당 -> 8/19 이담당"),
    ],
)

# ── 투자사 딜공유 ────────────────────────────────────────────────────────────
#
# 세 번째 모양이다. **투자사인데 달마다 칸이 늘어난다.**
#
# 위의 `투자사 명함` 은 명함 한 장(부서·직함·팩스·명함 등록일)이고, 월별 기록은
# 표에 두지 않았다 — 그 명단들은 시트에서 이미 활동 이력으로 옮겨 두었다.
# 그런데 담당자마다 쓰는 `딜공유현황` · `심사역 리스트` 시트는 **한 사람당 한
# 줄에 달마다 세 칸**(딜소개 · IR 요청 · 미팅)이 붙고, 칸 안에는 그 달에 무엇을
# 보내고 무슨 답을 들었는지가 회차별로 적혀 있다. 그 칸을 표에서 빼면 명단을
# 열었을 때 이름과 투자사명만 남는다 — 시트를 대신할 수가 없다.
#
# 스타트업 배치를 돌려 쓰지 않는 이유: 저쪽 머리글은 `기업명`·`성함` 이라
# **기업이 주인공**이고 여기는 사람이 주인공이다(`이름`·`투자사명`). 이름이
# 다르면 시트와 나란히 놓고 대조할 수가 없다. 그리고 저쪽은 투자사로 세지 않는
# 명단이고 이쪽은 **진짜 투자사**다.
INVESTOR_MONTHLY_LAYOUT = Layout(
    key=INVESTOR_MONTHLY,
    label="투자사 딜공유",
    monthly=True,
    # 한 칸에 회차별 기업 목록이 줄바꿈으로 쌓인다 — 고르는 칸이 아니라 글 칸이다.
    month_kind="long",
    month_choices="",
    month_width=240,
    head=[
        Column("NO", "no", 34, source="row_no"),
        # 사람이 주인공이다. 시트도 `이름` 이 먼저고 `투자사명` 이 뒤다.
        Column("이름", "name", 96),
        Column("투자사명", "firm", 180),
        # 시트 머리글이 세 가지를 한 칸에 적어 둔다. **쪼개지 않는다** —
        # 자유 서술이라 쪼개면 근거 없는 값이 된다(`sheet_import.split_sector_tags`
        # 가 같은 이유로 확신할 때만 쪼갠다).
        Column("그룹/투자분야/라운드사이즈", "group_name", 156),
        # 번호는 **발송의 열쇠가 아니다** — 발송은 카톡방 이름으로 나간다.
        # 여기 두는 이유는 같은 사람인지 대조할 때 눈으로 확인하는 칸이라서다.
        Column("휴대폰", "phone", 116),
    ],
    tail=[
        Column("기타", "etc", 110, source="note"),
        # 시트에서 가장 긴 칸이다(한 사람의 대화가 통째로 쌓인다). 표에서는 두
        # 줄까지만 보이고 전문은 수정창에서 본다.
        Column("대화내역 메모", "memo", 250, kind="long"),
    ],
    extra=[
        # 명함 칸들. 표에 세우면 스무 칸이 넘어 정작 매달 보는 월별 칸이 눌린다.
        # 값은 그대로 들어가고 수정창에서 보고 고친다.
        Column("전자 메일 주소", "email", 0, in_table=False),
        Column("부서", "department", 0, in_table=False),
        Column("직함", "title", 0, in_table=False),
        Column("관심도 (월말기준)", "interest_level", 0, in_table=False),
        Column("카톡방 참여여부", "kakao_joined", 0, in_table=False),
        Column("딜소싱 참여 투자사", "sourcing_note", 0, in_table=False),
        Column("선호 투자분야", "sectors", 0, in_table=False),
        Column("TIPS 운영사", "tips_note", 0, in_table=False),
        Column("라운드 사이즈", "round_size", 0, in_table=False),
        Column("근무처 전화", "office_phone", 0, in_table=False),
        Column("근무처 팩스", "office_fax", 0, in_table=False),
        Column("근무지 주소 번지", "address", 0, in_table=False),
        Column("명함 등록일", "card_registered_at", 0, in_table=False),
    ],
)

LAYOUTS: Dict[str, Layout] = {
    INVESTOR_LAYOUT.key: INVESTOR_LAYOUT,
    STARTUP_LAYOUT.key: STARTUP_LAYOUT,
    INVESTOR_MONTHLY_LAYOUT.key: INVESTOR_MONTHLY_LAYOUT,
}


def layout_of(key: Optional[str]) -> Layout:
    """모르는 배치 이름은 투자사 명함으로 본다.

    지금 보이던 표가 갑자기 비는 것보다, 옛 표가 그대로 나오는 편이 낫다.
    """
    return LAYOUTS.get((key or "").strip(), INVESTOR_LAYOUT)


def page_of(layout_key: Optional[str]) -> str:
    """이 배치를 쓰는 명단이 **어느 화면에 서는가**(주소 조각).

    두 화면(투자사 관리 현황 · 스타트업)이 각자 "내 명단은 이런
    것" 이라고 적어 두면 한쪽만 고쳐지는 날 명단이 **두 곳에 다 뜨거나 어디에도
    안 뜬다.** 어느 쪽이든 어느 값이 최신인지 알 수 없게 된다 — 그래서 판정을
    여기 한 번만 적고 두 화면이 같이 읽는다.
    """
    return layout_of(layout_key).page


def firm_leads(layout_key: Optional[str]) -> bool:
    """이 배치는 **기업이 주인공인가** — 표에서 기업명이 사람 이름보다 앞에 서는가.

    임포터가 "번호가 없는 줄을 **기업명으로** 이어도 되는가" 를 여기에 묻는다.
    사람이 주인공인 명단에서 기업명으로 맞추면 한 투자사의 심사역 여럿이 한
    줄로 뭉개진다 — 그때는 남의 이력에 남의 값이 덮인 뒤다.

    **명단 이름으로 가르지 않는다.** 이름으로 가르면 다음 명단에서 또 적어야
    하고, 적는 것을 잊은 곳만 조용히 옛 동작을 한다(`SheetOwner.layout` 주석이
    경계하는 그것이다). 배치는 이미 **그 명단이 어떤 명단인지**를 가리킨다.

    판정을 값으로 따로 두지 않고 **머리글 순서에서 읽는다.** 스타트업 명단은
    `기업명`·`성함` 순이고 투자사 딜공유는 `이름`·`투자사명` 순인데, 그 순서가
    곧 누가 주인공인가다(`INVESTOR_MONTHLY_LAYOUT` 주석이 두 배치의 차이로 바로
    그것을 든다). 값을 하나 더 두면 배치를 고칠 때 한쪽만 고쳐진다.

    둘 다 없는 배치는 **아니다**로 본다(투자사 명함 표는 머리글을 화면에 적어
    두어 `head` 가 비어 있다). 되는지 모르는 쪽에서 이으면 뭉개지는 쪽이라,
    모를 때는 안 잇는 것이 맞다.
    """
    for column in layout_of(layout_key).head:
        if column.key in ("firm", "name"):
            return column.key == "firm"
    return False


# 표에 한 번에 펴 둘 **달** 수. 칸 수가 아니라 달로 센다.
#
# 칸 수로 자르면 **달 중간이 잘린다.** 한 달에 몇 칸이 붙는지가 명단마다 다르고
# (스타트업 리마인드는 문자·TEL·카톡 연결 셋, 딜공유는 딜소개·IR 요청·미팅 셋,
# 시트에 따라 한 칸뿐인 달도 있다), 자동 생성이 붙인 칸까지 더해지면 더 어긋난다.
# 그러면 `8월 리마인드 문자` 는 보이는데 `8월 카톡 연결` 은 접혀 있는, 한 달의
# 기록 일부만 보이는 표가 된다.
#
# **이번 달만 편다.** 매달 칸이 세 개씩 붙는 표라 두 달치면 여섯 칸이고, 그만큼
# 가로로 밀어야 이름·연락처가 보인다. 지난달은 접되 **접었다는 것을 화면에 적고
# 펴는 길을 남긴다**(`split_months` 참고) — 그냥 안 보이면 지워진 줄 안다.
#
# 사람이 펴 둔 상태(`?months=all`)는 **요청에 실려 있고 DB 에 없다.** 그래서 달이
# 바뀌어 칸이 저절로 생겨도 편 것을 다시 접을 수가 없다 — 접는 것은 이 함수뿐이고,
# 이 함수는 `show_all` 이 오면 아무것도 안 접는다.
VISIBLE_MONTHS = 1


def month_columns(db: Session, sheet: str,
                  today: Optional[date] = None,
                  create: bool = True) -> List[ContactColumn]:
    """이 명단의 월별 칸. **시트에 서 있던 순서 그대로**다.

    그 순서가 달 순서라는 보장은 없다 — 올라온 시트에 오름차순도 내림차순도
    있었다(`services/monthly_columns.py` 의 "어느 칸을 본으로 삼는가").

    **읽기 전에 이번 달 칸이 있는지 본다.** 예약 실행 장치가 없는 앱이라,
    달이 바뀐 것을 알아채는 자리는 요청이 들어오는 순간뿐이다 — 주간 업무가
    같은 방식으로 그 주 목록을 채운다(`services/weekly.py` 의 `fill_week`).

    칸을 읽는 곳이 여럿인데(화면 · [칸 추가] · 수정창) 그 자리마다 "이번 달
    있나" 를 적으면 한 곳은 반드시 빠진다. **칸이 나오는 문 하나**에 둔다.

    같은 달 칸을 두 번 만들지 않는 것과, 사람이 지운 칸을 되살리지 않는 것은
    `services/monthly_columns.py` 가 `MonthlyColumnRun` 으로 지킨다.
    """
    if not sheet:
        return []
    # `today` 는 검사에서 날짜를 못 박으려고 받는다. 안 주면 오늘이다.
    # 안 받으면 달이 바뀌는 날 검사가 통째로 깨진다 — 실제로 9월 1일에 그랬다.
    #
    # `create=False` 는 **읽기만** 한다. 시트를 가져오는 쪽이 그렇다 — 거기서
    # 칸을 세우는 것은 시트에 적힌 머리글이지 오늘 날짜가 아니다. 읽는 김에
    # 이번 달 칸까지 만들면, 8월 시트를 9월에 올렸을 때 시트에 없는 9월 칸이
    # 딸려 생기고 가져오기 결과가 돌린 날짜에 따라 달라진다.
    if create:
        monthly_columns.ensure_contact(db, sheet, today=today)
    return db.execute(
        select(ContactColumn)
        .where(ContactColumn.sheet == sheet)
        .order_by(ContactColumn.position, ContactColumn.id)
    ).scalars().all()


def split_months(columns: List[ContactColumn], show_all: bool = False) -> tuple:
    """(펴 둘 칸, 접어 둔 칸). **달 단위로** 자른다.

    **접었다는 것을 사람이 알아야 한다** — 그냥 안 보이면 지워진 줄 안다.
    화면에 몇 칸이 접혀 있는지 적고 눌러서 펼 수 있게 한다.

    이름에서 달을 못 읽는 칸은 **혼자 한 묶음**으로 본다. 옆 달에 붙이면 그
    칸 때문에 남의 달이 통째로 접히거나 펴진다 — 어느 쪽이든 이유를 알 수 없다.
    """
    if show_all:
        return list(columns), []
    seen: List[str] = []
    for i, col in enumerate(columns):
        month = monthly_columns.month_of(col.label)
        key = f"{month}월" if month is not None else f"#{i}"
        if key in seen:
            continue
        if len(seen) == VISIBLE_MONTHS:
            return list(columns[:i]), list(columns[i:])
        seen.append(key)
    return list(columns), []


def note_key(column_id: int) -> str:
    """월별 칸이 `notes` 와 화면에서 쓰는 이름. **숫자로 시작하지 않게** 한다.

    열 id 를 그대로 쓰면 `data-f-7` 같은 속성 이름이 되는데, 숫자로 시작하는
    이름은 브라우저마다 다루는 방식이 갈린다(필터가 그 칸만 조용히 안 걸린다).
    """
    return f"c{column_id}"


def as_column(row: ContactColumn, layout: Optional[Layout] = None) -> Column:
    """월별 칸도 고정 칸과 **같은 모양**으로 내놓는다.

    화면이 "이건 월별 칸이니 다르게 그려야지" 를 하지 않아도 되게. 갈래를
    화면이 알면, 갈래가 하나 늘 때마다 화면도 같이 고쳐야 한다.

    고치는 방식과 폭은 **배치가 정한다**(`Layout.month_kind`). 배치를 안 주면
    지금까지의 스타트업 리마인드 값(`O`/`X` 고르기)이다 — 부르는 곳을 다 고치지
    않아도 옛 동작이 그대로 나오게.
    """
    layout = layout or STARTUP_LAYOUT
    return Column(label=row.label, key=note_key(row.id), width=layout.month_width,
                  source="note", kind=layout.month_kind,
                  choices=layout.month_choices)


def table_columns(layout: Layout, months: List[ContactColumn]) -> List[Column]:
    """표에 세울 칸 — 머리글과 데이터 칸이 **이 하나**에서 같이 나온다.

    머리글은 머리글대로, 칸은 칸대로 적어 두면 하나를 지웠을 때 그 뒤가 통째로
    한 칸씩 밀린다(`tests/test_ui_layout.py` 가 오래 지켜 온 규칙이다).

    **월별 칸은 배치가 부를 때만 선다**(`layout.monthly`). 명단에 달 칸이 있어도
    표에 안 세우는 배치가 있다 — 투자사 명함 표가 그렇다(위 주석 참고).
    """
    return ([c for c in layout.head if c.in_table]
            + ([as_column(m, layout) for m in months] if layout.monthly else [])
            + [c for c in layout.tail if c.in_table])


def panel_columns(layout: Layout, months: List[ContactColumn]) -> List[Column]:
    """수정창에 세울 칸 — 표에 있는 것 + 표에서 뺀 것.

    표에서 뺀 칸이 수정창에도 없으면 **적을 자리가 아예 없다.** 값은 들어가
    있는데 화면 어디에서도 볼 수 없는 칸이 그렇게 생긴다.

    월별 칸은 `table_columns` 와 달리 **배치를 안 가리고 전부 넣는다.** 표에
    안 세우는 배치에서는 여기가 그 값을 볼 수 있는 유일한 자리다 — 여기서도
    빼면 달마다의 기록이 화면에서 통째로 사라진다(지워지는 것은 아니지만,
    안 보이면 사람은 지워진 줄 안다).
    """
    return ([c for c in layout.head if c.source != "row_no"]
            + [as_column(m, layout) for m in months]
            + list(layout.tail) + list(layout.extra))


def note_keys(layout: Layout, months: List[ContactColumn]) -> List[str]:
    """이 배치가 `notes` 에 쓰는 키 전부. 저장·되읽기가 이 목록 하나를 본다."""
    return [c.key for c in panel_columns(layout, months) if c.source == "note"]


def load_notes(raw: Optional[str]) -> Dict[str, str]:
    """`VcContact.notes` 읽기. 깨져 있으면 빈 것으로 — 표가 안 그려지면 안 된다."""
    try:
        data = json.loads(raw or "{}")
    except (TypeError, ValueError):
        return {}
    return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}


def dump_notes(values: Dict[str, str]) -> str:
    """빈 값은 담지 않는다 — 지운 칸이 `""` 로 남으면 계속 자리를 차지한다."""
    return json.dumps({k: v for k, v in values.items() if v}, ensure_ascii=False)
