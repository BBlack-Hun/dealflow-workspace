"""표에 붙이는 추가 칸 — 개선 과제 #6 · #7 · #8 · #12 · #46.

관리자가 관리자 메뉴 `컬럼 관리`(`routers/custom_columns.py`)에서 칸을 붙이고
(이름 · 형식 메모/OX), 이름을 바꾸고, 순서를 옮기고, 자리(어느 기존 칸 뒤 —
`anchors` · `place`)를 고르고, 숨긴다. **지우는 길은 없다.**
팀원은 표에서 값만 적는다 — 칸을 눌러 적는 길은 그 표의 다른 칸과 같고
(`inline_edit.js` · `consulting.js` 의 `data-custom`), 고칠 수 있는 줄도 그 표의
판정 그대로다(`routers/custom_columns._row`).

화면 · 엑셀 · 지우기가 모두 이 모듈 하나를 읽는다:

    view(db, target, row_table)   그 화면에 보일 칸과 값(숨긴 칸은 빠진다)
    cells(view, row_id)           엑셀 한 줄 끝에 붙일 값
    forget_deleted(session)       줄이 지워지면 그 줄의 값도 함께(세션 flush)

달마다 늘어나는 칸(`ContactColumn` · `ConsultingColumn`)과는 따로 산다 — 투자컨설턴트의
[월 열 추가]는 그대로이고, 이 칸은 그 옆에 일반 칸으로만 선다(사용자 결정 · #8).
"""
from __future__ import annotations

from typing import Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from ..clock import now_iso
from ..models import CustomColumn, CustomColumnValue
from . import edit_log

#: 칸을 붙일 수 있는 **화면**과 그 화면이 그리는 줄의 표.
#:
#: IR 기업 현황은 탭 셋이 **같은 칸**을 쓴다(사용자 결정 · #12 · #6 — 탭마다 따로
#: 두지 않는다). 탭 둘은 `ir_companies` 를, `Series A 이상 딜 소싱` 탭은
#: `series_a_companies` 를 그리므로 표가 둘이다.
#:
#: `href` 는 그 화면의 주소다 — 투자컨설턴트 계정이 이 화면을 열 수 있는지를
#: 값을 적을 때 이 주소로 묻는다(`deps.can_open`).
TARGETS = {
    "companies": {"label": "IR 기업 현황", "href": "/companies",
                  "tables": ("ir_companies", "series_a_companies"),
                  "where": "IR 기업 현황 · 스타트업DB · Series A 이상 딜 소싱 — 세 탭이 같은 칸"},
    "startup": {"label": "스타트업", "href": "/startup",
                "tables": ("vc_contacts",),
                "where": "스타트업 명단 — 명단(탭)을 가리지 않고 같은 칸"},
    "consulting": {"label": "투자컨설턴트", "href": "/consulting",
                   "tables": ("consulting_companies",),
                   "where": "투자컨설턴트 현황 — 탭을 가리지 않고 같은 칸 · [월 열 추가]와 따로"},
    "sourcing": {"label": "딜 소싱", "href": "/sourcing",
                 "tables": ("sourcing_contacts",),
                 "where": "딜 소싱 명단 — 갈래(탭)를 가리지 않고 같은 칸"},
    "forecast": {"label": "매출예상리스트", "href": "/report/forecast",
                 "tables": ("revenue_forecasts",),
                 "where": "업무 보고 › 매출예상리스트"},
}

#: 줄의 표 → 화면. 표 하나는 한 화면에만 속한다.
ROW_TARGET = {table: key for key, spec in TARGETS.items() for table in spec["tables"]}

#: 추가 칸을 **어느 기존 칸 뒤에** 둘 수 있나 — 화면마다 탭별 머리글 이름(0110).
#:
#: 열쇠가 머리글 이름인 까닭: IR 기업 현황 · 투자컨설턴트는 머리글을 템플릿에 손으로
#: 적어서(반복문이 아니다) 칸마다 붙은 열쇠가 없다. 이름은 화면과 엑셀이 같이 쓰는
#: 말이라 엑셀도 같은 이름 뒤에 끼운다(`arranger`). 템플릿에서 이름을 고치면 그 뒤에
#: 두었던 칸은 맨 끝으로 물러난다 — tests/test_custom_columns.py 가 화면과 대조한다.
#: 고정 칸(`NO` · 고르기 칸)은 뺀다 — 그 사이에 끼면 가로 고정 자리 셈이 어긋난다.
#: 반복문으로 머리글을 그리는 표(스타트업 · 딜 소싱 · 매출예상)는 그 목록을 읽는다.
_HAND_ANCHORS = {
    "companies": {
        "IR 기업 현황": (
            "기업명", "수신일", "대분류", "소분류", "투자라운드", "수정한 날짜",
            "딜 소개 문구", "담당자", "소개 횟수", "견적서 첨부 여부", "미팅제공일자",
            "계약여부", "계약서 수신 여부", "카톡 연결 여부", "홍보메일삭제",
            "핵심/TOP Deal", "IR 자료"),
        "스타트업DB": (
            "수신일", "기업명", "대표자명", "연락처", "이메일", "기업 한줄 소개",
            "22년 매출", "23년 매출", "24년 매출", "25년 매출", "누적투자금액",
            "투자유치희망금액", "Pre Value", "특이사항 (장점)", "최근 매출액",
            "설립년도", "지역", "정책자금", "IR 자료"),
        "Series A 이상 딜 소싱": (
            "기업명", "수신 일자", "Type", "담당자", "공유 심사역", "회사", "대분류",
            "소분류", "투자라운드", "대표자명", "연락처", "이메일", "24년 매출",
            "25년 매출", "26년 매출", "27년 매출", "누적투자금액", "투자유치희망금액",
            "Pre Value", "상세 내용", "딜 소개 문구", "IR 자료"),
    },
    "consulting": {
        "스타트업": (
            "지역", "컨설팅 미팅일", "미팅종류", "기업명", "기업 관리", "기업 내용",
            "견적서 첨부 여부", "계약여부", "계약서 수신 여부", "소개 메모",
            "카톡 연결 여부", "대표자명", "연락처", "이메일"),
        "그 밖의": (
            "지역", "컨설팅 미팅일", "미팅종류", "기업명", "기업 관리", "기업 내용",
            "대표자명", "연락처", "이메일"),
        "월간 계약 업무현황표": (
            "계약월", "기업명", "계약여부", "계약서 수신 여부", "성공보수율", "계약금"),
    },
}


#: **이름을 바꾼 머리글** — `{화면: {옛 이름: 새 이름}}`(#63 · 같은 칸은 같은 이름).
#: `after_key` 는 고른 그때의 머리글 글자라, 이름이 바뀌면 그 칸이 맨 끝으로 물러난다.
#: 저장된 값은 그대로 두고 **읽을 때** 새 이름으로 본다(`anchor_of`).
RENAMED = {
    "sourcing": {"투자분야": "선호 투자분야",
                 "라운드 사이즈": "라운드 사이즈(투자운영금액)",
                 "이메일 주소": "전자 메일 주소"},
    "companies": {"핸드폰": "연락처", "프리밸류": "Pre Value",
                  # 이름 통일(10/22) — Series A 이상 딜 소싱 탭.
                  "담당팀원": "담당자", "딜소개 문구": "딜 소개 문구"},
    # 이름 통일(10/22) — 기업 쪽은 IR 기업 현황 낱말, 투자사 쪽은 투자사 관리 현황 낱말.
    "consulting": {"미팅일": "컨설팅 미팅일", "대표자": "대표자명",
                   "계약완료여부": "계약여부", "계약서 수신완료여부": "계약서 수신 여부",
                   "계약서 수신여부": "계약서 수신 여부", "딜 소개문구": "소개 메모"},
    "startup": {"성함": "대표자명", "사업분야 대분류": "대분류", "기업구분": "투자라운드",
                "IR Deck 유무": "IR 자료 유무", "IR 미팅 제공일자": "미팅제공일자",
                "견적서 첨부여부": "견적서 첨부 여부", "계약서 수신여부": "계약서 수신 여부"},
    "forecast": {"투자사명": "회사", "심사역 성함": "심사역 이름", "전화번호": "심사역 휴대폰",
                 "대표자 성함": "대표자명", "프리밸류": "Pre Value",
                 "희망 투자유치금액": "투자유치희망금액", "성공보수율(%)": "성공보수율"},
}


def anchor_of(col) -> str:
    """이 칸이 설 자리(기존 칸의 머리글 이름) — 옛 이름이면 새 이름으로. 없으면 `""`."""
    key = label_key(col.after_key)
    return RENAMED.get(getattr(col, "target", None), {}).get(key, key)


def anchor_groups(target: str) -> Dict[str, tuple]:
    """`{탭: 머리글 이름들}` — 그 화면의 기존 칸."""
    if target in _HAND_ANCHORS:
        return _HAND_ANCHORS[target]
    # 순환 import 를 피해 늦게 부른다 — 그 화면들이 이 모듈을 부른다.
    if target == "startup":
        from .contact_columns import STARTUP_LAYOUT, table_columns
        return {"스타트업 명단": tuple(c.label for c in table_columns(STARTUP_LAYOUT, [])
                                  if c.source != "row_no")}
    if target == "sourcing":
        from ..routers.sourcing import COLUMNS
        return {"딜 소싱": tuple(label for _f, label, _w, _fl in COLUMNS)}
    if target == "forecast":
        from .forecast import COLUMNS
        return {"매출예상리스트": tuple(label for _f, label, _s in COLUMNS)}
    return {}


def label_key(text) -> str:
    """머리글 이름을 견줄 꼴 — 띄어쓰기를 하나로(`custom_cols.js` 의 `key` 와 같다)."""
    return " ".join(str(text or "").split())


def anchors(target: str) -> List[tuple]:
    """고를 자리 `[(이름, 안내)]`. 몇 탭에만 있는 칸은 안내에 그 탭을 적는다."""
    groups = anchor_groups(target)
    tabs: Dict[str, list] = {}
    for tab, labels in groups.items():
        for label in labels:
            tabs.setdefault(label_key(label), []).append(tab)
    return [(label, "" if len(where) == len(groups) else " · ".join(where) + " 탭만")
            for label, where in tabs.items()]


KINDS = {"memo": "메모(글)", "ox": "O/X"}
OX_CHOICES = "O,X"
NAME_MAX = 40
MEMO_MAX = 2000


class ColumnError(ValueError):
    """사람에게 그대로 보일 까닭 — 라우터가 400 · 안내 글로 돌려준다."""


# ── 읽기 ──────────────────────────────────────────────────────────────────

def columns(db: Session, target: str, include_hidden: bool = False) -> List[CustomColumn]:
    stmt = select(CustomColumn).where(CustomColumn.target == target)
    if not include_hidden:
        stmt = stmt.where(CustomColumn.is_hidden == 0)
    return list(db.execute(stmt.order_by(CustomColumn.position,
                                         CustomColumn.id)).scalars())


def values(db: Session, row_table: str, cols) -> Dict[int, Dict[int, str]]:
    """`{줄 번호: {칸 번호: 값}}` — 주어진 칸의 값만."""
    ids = [c.id for c in cols]
    if not ids:
        return {}
    out: Dict[int, Dict[int, str]] = {}
    for cell in db.execute(select(CustomColumnValue).where(
            CustomColumnValue.row_table == row_table,
            CustomColumnValue.column_id.in_(ids))).scalars():
        out.setdefault(cell.row_id, {})[cell.column_id] = cell.value
    return out


def view(db: Session, target: str, row_table: str) -> dict:
    """화면 컨텍스트 — 밑틀 조각(`_custom_cols.html`)이 이 이름들을 읽는다."""
    cols = columns(db, target)
    return {"custom_cols": cols, "custom_vals": values(db, row_table, cols),
            "custom_rows": row_table, "ox_choices": OX_CHOICES,
            "custom_after": {c.id: anchor_of(c) for c in cols}}


def names(v: dict) -> List[str]:
    return [c.name for c in v["custom_cols"]]


def cells(v: dict, row_id: int) -> List[str]:
    got = v["custom_vals"].get(row_id, {})
    return [got.get(c.id, "") for c in v["custom_cols"]]


def arranger(headers: List[str], v: dict):
    """엑셀 한 줄(`headers` 차례의 기존 칸 + `cells`)을 **화면처럼 앵커 뒤에** 끼운
    차례로 바꾸는 함수. 앵커가 이 파일 머리글에 없으면 그 칸은 지금처럼 맨 끝이다.
    """
    keys = [label_key(h) for h in headers]
    n = len(keys)
    after: Dict[int, list] = {}
    tail = []
    for j, c in enumerate(v["custom_cols"]):
        key = anchor_of(c)
        if key and key in keys:
            after.setdefault(keys.index(key), []).append(n + j)
        else:
            tail.append(n + j)
    order = [k for i in range(n) for k in [i] + after.get(i, [])] + tail
    return lambda line: [line[k] for k in order]


# ── 관리자: 붙이기 · 이름 · 순서 · 숨김 ───────────────────────────────────

def _clean_name(name: str) -> str:
    text = " ".join((name or "").split())
    if not text:
        raise ColumnError("칸 이름을 입력하세요")
    if len(text) > NAME_MAX:
        raise ColumnError(f"칸 이름은 {NAME_MAX}자까지입니다")
    return text


def _check_free(db: Session, target: str, name: str,
                except_id: Optional[int] = None) -> None:
    """같은 화면에 같은 이름이 있으면 막는다 — **숨긴 칸까지** 센다.

    숨긴 칸을 빼고 세면, 그 칸을 다시 보이게 하는 순간 머리글이 둘로 선다.
    """
    for col in columns(db, target, include_hidden=True):
        if col.id != except_id and col.name.casefold() == name.casefold():
            raise ColumnError(f"'{name}' 칸이 이미 있습니다"
                              + (" (숨긴 칸 — 다시 보이게 하세요)" if col.is_hidden else ""))


def add(db: Session, target: str, name: str, kind: str,
        user_id: Optional[int]) -> CustomColumn:
    if target not in TARGETS:
        raise ColumnError("모르는 화면입니다")
    if kind not in KINDS:
        raise ColumnError("형식은 메모 · O/X 중에서 고르세요")
    name = _clean_name(name)
    _check_free(db, target, name)
    last = max((c.position for c in columns(db, target, include_hidden=True)),
               default=0)
    col = CustomColumn(target=target, name=name, kind=kind, position=last + 1,
                       is_hidden=0, created_by=user_id)
    db.add(col)
    return col


def rename(db: Session, col: CustomColumn, name: str) -> None:
    name = _clean_name(name)
    _check_free(db, col.target, name, except_id=col.id)
    col.name = name


def move(db: Session, col: CustomColumn, step: int) -> None:
    """한 칸 앞(-1) · 뒤(+1)로. 차례를 0, 1, 2 … 로 다시 매긴다."""
    order = columns(db, col.target, include_hidden=True)
    at = order.index(col)
    to = at + (1 if step > 0 else -1)
    if 0 <= to < len(order):
        order[at], order[to] = order[to], order[at]
    for i, c in enumerate(order):
        c.position = i


def place(col: CustomColumn, after: str) -> None:
    """칸을 기존 칸 `after`(머리글 이름) 뒤로 — 비면 맨 끝. 탭에 그 칸이 없으면
    그 탭에서는 맨 끝에 선다(`custom_cols.js`)."""
    after = label_key(after)
    if after and after not in dict(anchors(col.target)):
        raise ColumnError("그 화면에 없는 칸입니다")
    col.after_key = after or None


def set_hidden(col: CustomColumn, hidden: bool) -> None:
    col.is_hidden = 1 if hidden else 0


# ── 팀원: 값 적기 ─────────────────────────────────────────────────────────

def clean_value(col: CustomColumn, raw) -> str:
    text = str(raw or "").strip()
    if col.kind == "ox":
        text = text.upper()
        if text not in ("", "O", "X"):
            raise ColumnError("O · X 중에서 고르거나 비워 두세요")
        return text
    if len(text) > MEMO_MAX:
        raise ColumnError(f"메모는 {MEMO_MAX}자까지입니다")
    return text


def write(db: Session, row, col: CustomColumn, raw, user_id: Optional[int]) -> str:
    """줄 `row` 의 칸 `col` 에 값을 적는다 — 고칠 수 있는 줄인지는 부르는 쪽이 본다.

    빈 값은 줄째 지운다. **고친 일은 그 줄의 로그로 남긴다**(`edit_log.touched`):
    줄의 `updated_at` 을 새로 찍어 그 줄이 고친 줄로 flush 를 지나게 한다 — 그러면
    수정 로그가 그 줄의 주인 판정 그대로 남기고(자기 줄이면 안 남는다), 표의
    `수정한 날짜` 도 함께 맞는다.
    """
    table = row.__tablename__
    if ROW_TARGET.get(table) != col.target:
        raise ColumnError("이 표의 칸이 아닙니다")
    if col.is_hidden:
        raise ColumnError("숨긴 칸입니다 — 관리자 메뉴 `컬럼 관리` 에서 다시 보이게 한 뒤 적으세요")
    value = clean_value(col, raw)
    cell = db.execute(select(CustomColumnValue).where(
        CustomColumnValue.column_id == col.id,
        CustomColumnValue.row_table == table,
        CustomColumnValue.row_id == row.id)).scalar_one_or_none()
    if (cell.value if cell else "") == value:
        return value
    if not value:
        db.delete(cell)
    elif cell is None:
        db.add(CustomColumnValue(column_id=col.id, row_table=table, row_id=row.id,
                                 value=value, updated_by=user_id))
    else:
        cell.value = value
        cell.updated_by = user_id
    row.updated_at = now_iso()
    # 같은 초 안에 두 번 고치면 값이 그대로라 고친 줄로 안 잡힌다 — 못 박아 둔다.
    flag_modified(row, "updated_at")
    edit_log.touched(table, f"추가 칸 · {col.name}")
    return value


# ── 줄이 지워지면 ─────────────────────────────────────────────────────────

def forget_rows(session: Session, row_table: str, ids) -> None:
    """그 줄들의 값을 지운다. ORM 을 지나지 않고 줄을 지우는 길이 먼저 부른다."""
    ids = list(ids)
    if not ids:
        return
    with session.no_autoflush:
        gone = session.execute(select(CustomColumnValue).where(
            CustomColumnValue.row_table == row_table,
            CustomColumnValue.row_id.in_(ids))).scalars().all()
    for cell in gone:
        session.delete(cell)


def forget_deleted(session: Session) -> None:
    """flush 직전 — 지워지는 줄의 값을 함께 지운다(`models._forget_custom_values`).

    값은 외래키 없이 `(표, 번호)` 로 줄을 가리킨다. 남겨 두면 SQLite 가 맨 끝 번호를
    다시 쓰는 날 **새 줄에 지운 줄의 값이 뜬다.**
    """
    gone: Dict[str, list] = {}
    for obj in session.deleted:
        table = getattr(obj, "__tablename__", None)
        if table in ROW_TARGET and getattr(obj, "id", None):
            gone.setdefault(table, []).append(obj.id)
    for table, ids in gone.items():
        forget_rows(session, table, ids)
