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
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import ContactColumn

# 배치 이름. `SheetOwner.layout` 에 이 값이 들어간다.
INVESTOR = "investor"
STARTUP = "startup"
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
    """한 명단이 쓰는 칸 묶음."""

    key: str
    label: str
    # 월별 칸 **앞**에 서는 고정 칸들
    head: List[Column] = field(default_factory=list)
    # 월별 칸 **뒤**에 서는 고정 칸들
    tail: List[Column] = field(default_factory=list)
    # 표에는 안 세우고 수정창에서만 보는 칸들
    extra: List[Column] = field(default_factory=list)
    # 달마다 늘어나는 칸을 쓰는 배치인가
    monthly: bool = False


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
INVESTOR_LAYOUT = Layout(key=INVESTOR, label="투자사 명함")


# ── 스타트업 리마인드 ────────────────────────────────────────────────────────
#
# 폭은 **값의 길이**로 잡았다(90%가 들어가는 선). 머리글 길이로 잡으면 값이
# 짧은 칸이 넓은 자리를 먹는다.
STARTUP_LAYOUT = Layout(
    key=STARTUP,
    label="스타트업 리마인드",
    monthly=True,
    head=[
        Column("NO", "no", 34, source="row_no"),
        # 기업명·성함이 **따로** 적힌다. 투자사 명단은 사람이 주인공이라
        # `이름`·`회사` 였는데, 여기는 기업이 주인공이라 순서가 뒤집힌다.
        Column("기업명", "firm", 180),
        Column("성함", "name", 84),
        Column("연락처", "phone", 116),
        Column("이메일", "email", 180),
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
        Column("계약여부", "contract", 0, source="note",
               kind="pick", in_table=False),
        # 금액·비율은 **적힌 그대로** 둔다. `2.5%` 인지 `2.5` 인지, `900,000` 인지
        # `90만` 인지는 계약서에 적힌 말이라 앱이 고쳐 쓸 것이 아니다.
        Column("성공보수율 %", "success_fee", 0, source="note", in_table=False),
    ],
)

LAYOUTS: Dict[str, Layout] = {
    INVESTOR_LAYOUT.key: INVESTOR_LAYOUT,
    STARTUP_LAYOUT.key: STARTUP_LAYOUT,
}


def layout_of(key: Optional[str]) -> Layout:
    """모르는 배치 이름은 투자사 명함으로 본다.

    지금 보이던 표가 갑자기 비는 것보다, 옛 표가 그대로 나오는 편이 낫다.
    """
    return LAYOUTS.get((key or "").strip(), INVESTOR_LAYOUT)


# 표에 한 번에 펴 둘 월별 칸 수. 한 달에 세 칸씩(문자·TEL·카톡 연결) 늘어나므로
# **두 달치**다. 이번 달만 펴 두면 "지난달에 뭐라고 했더라" 를 볼 수가 없고,
# 그냥 두면 한 해 뒤에 서른여섯 칸이 되어 가로로 밀어야 읽힌다.
VISIBLE_COLUMNS = 6


def month_columns(db: Session, sheet: str) -> List[ContactColumn]:
    """이 명단의 월별 칸. 시트와 같은 순서(최근 달이 왼쪽)."""
    if not sheet:
        return []
    return db.execute(
        select(ContactColumn)
        .where(ContactColumn.sheet == sheet)
        .order_by(ContactColumn.position, ContactColumn.id)
    ).scalars().all()


def split_months(columns: List[ContactColumn], show_all: bool = False) -> tuple:
    """(펴 둘 칸, 접어 둔 칸).

    **접었다는 것을 사람이 알아야 한다** — 그냥 안 보이면 지워진 줄 안다.
    화면에 몇 칸이 접혀 있는지 적고 눌러서 펼 수 있게 한다.
    """
    if show_all or len(columns) <= VISIBLE_COLUMNS:
        return columns, []
    return columns[:VISIBLE_COLUMNS], columns[VISIBLE_COLUMNS:]


def note_key(column_id: int) -> str:
    """월별 칸이 `notes` 와 화면에서 쓰는 이름. **숫자로 시작하지 않게** 한다.

    열 id 를 그대로 쓰면 `data-f-7` 같은 속성 이름이 되는데, 숫자로 시작하는
    이름은 브라우저마다 다루는 방식이 갈린다(필터가 그 칸만 조용히 안 걸린다).
    """
    return f"c{column_id}"


def as_column(row: ContactColumn) -> Column:
    """월별 칸도 고정 칸과 **같은 모양**으로 내놓는다.

    화면이 "이건 월별 칸이니 다르게 그려야지" 를 하지 않아도 되게. 갈래를
    화면이 알면, 갈래가 하나 늘 때마다 화면도 같이 고쳐야 한다.
    """
    return Column(label=row.label, key=note_key(row.id), width=186,
                  source="note", kind="pick", choices="O,X")


def table_columns(layout: Layout, months: List[ContactColumn]) -> List[Column]:
    """표에 세울 칸 — 머리글과 데이터 칸이 **이 하나**에서 같이 나온다.

    머리글은 머리글대로, 칸은 칸대로 적어 두면 하나를 지웠을 때 그 뒤가 통째로
    한 칸씩 밀린다(`tests/test_ui_layout.py` 가 오래 지켜 온 규칙이다).
    """
    return ([c for c in layout.head if c.in_table]
            + [as_column(m) for m in months]
            + [c for c in layout.tail if c.in_table])


def panel_columns(layout: Layout, months: List[ContactColumn]) -> List[Column]:
    """수정창에 세울 칸 — 표에 있는 것 + 표에서 뺀 것.

    표에서 뺀 칸이 수정창에도 없으면 **적을 자리가 아예 없다.** 값은 들어가
    있는데 화면 어디에서도 볼 수 없는 칸이 그렇게 생긴다.
    """
    return ([c for c in layout.head if c.source != "row_no"]
            + [as_column(m) for m in months]
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
