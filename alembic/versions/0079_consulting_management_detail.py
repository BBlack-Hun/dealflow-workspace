"""투자컨설턴트 리스트 — `기업 내용` 칸을 세운다 (`기업 관리` 에서 갈라 나온다)

## 무엇을

`consulting_companies` 에 `management_detail` 을 더한다. 자리는 `기업 관리`
바로 오른쪽이다(`routers/consulting.py` 의 `FIXED_COLUMNS`).

**이 판은 칸만 세운다. 값은 한 줄도 안 옮긴다.**

## 무엇을 "분리" 하는가 — 시트 머리글이 이미 둘을 부르고 있었다

원본 머리글이 **`기업 관리 [ 드랍 이유 상세하게 기입 / 관리중 / 백업팀으로
전환 ]`** 이다. 한 칸에 **상태**(관리중 · 드랍 · 백업팀 전환)와 **그 이유를
상세하게 적은 글**을 같이 적으라고 했고, 실제 값이 `드랍 : 몇 차례 …` 처럼
`상태 : 상세` 꼴이다.

섞여 있으면 잃는 것이 있다. 이 칸의 값으로 칩·KPI·머리글 필터가 갈래를 세는데
(`services/consulting_status.py` 가 `관리`·`드랍`·`백업팀` 이라는 **낱말**을
찾는다), 상세 글이 길어질수록 그 낱말이 우연히 들어가 엉뚱한 갈래에 걸린다 —
`딜 소개문구`(0066 무렵)를 이 칸에서 갈라낼 때 이미 적어 둔 이유다.

그래서 **상태는 `management` 에 남고 상세만 새 칸으로** 간다.

## 왜 값을 여기서 안 옮기나 — **사람이 확인하고 돌린다**

이 판이 값을 옮기면 `alembic upgrade` 한 번에 운영 자료가 바뀐다. 컨테이너가
뜨면서 저절로 도는 자리라(`RUN_MIGRATIONS=1`) 아무도 보고 있지 않을 때
바뀌고, 결과가 틀려도 알아챌 사람이 없다.

옮기는 것은 **따로 둔 스크립트**다 — `scripts/split_consulting_management.py`.
미리보기가 기본이고, `--apply` 를 줘야 쓰며, 되돌리는 길(`--revert`)과 원본을
그대로 담은 백업 파일을 같이 낸다. 0040 이 계약 줄을 나눌 때는 이주 안에서
했는데, 그때는 값이 다섯 줄이었고 지금은 마흔다섯 줄에 운영 중인 표다.

## 이미 들어 있는 줄은 어떻게 되나 — **손대지 않는다**

NULL 로 시작한다. 화면에서는 빈칸이다. `기업 관리` 의 값도 이 판에서는 한
글자도 안 바뀐다 — 칸이 서기만 하고 표는 지금 모양 그대로 돈다.

## 되돌리면

칸을 지운다. **스크립트를 이미 돌렸다면 내리기 전에 `--revert` 를 먼저
돌려야 한다** — 안 그러면 옮겨 둔 상세 글이 칸과 함께 사라진다. 스크립트의
머리글에 같은 말이 적혀 있고, 백업 파일이 있으면 거기서도 되돌아온다.
아직 안 돌렸으면 이 칸은 비어 있으므로 잃을 것이 없다.

## 두 번 돌려도 죽지 않는가

칸이 이미 있으면 건너뛴다 — 0048 · 0049 · 0065 · 0068 · 0077 · 0078 과 같은
방식이다. 스탬프가 어긋난 DB 로 컨테이너가 뜨면 `duplicate column name` 으로
죽고 다시 뜨는 크래시 루프가 된다.

Revision ID: 0079_consulting_management_detail
Revises: 0078_consulting_meeting_kind
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0079_consulting_management_detail"
down_revision = "0078_consulting_meeting_kind"
branch_labels = None
depends_on = None

TABLE = "consulting_companies"

# 세우는 칸. 문단이 들어오는 자리라 `Text` 다 — 갈라져 나오는 원본
# (`management`)과 같은 모양이어야 옮길 때 잘리지 않는다.
ADDED = [("management_detail", sa.Text())]


def _has_column(table: str, column: str) -> bool:
    return column in {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def _add(columns) -> None:
    # 한 번에 하나씩 본다. 절반만 올라간 DB 에서도 나머지가 붙어야 한다.
    for name, kind in columns:
        if _has_column(TABLE, name):
            continue
        with op.batch_alter_table(TABLE) as b:
            b.add_column(sa.Column(name, kind, nullable=True))


def _drop(columns) -> None:
    for name, _kind in columns:
        if not _has_column(TABLE, name):
            continue
        with op.batch_alter_table(TABLE) as b:
            b.drop_column(name)


def upgrade() -> None:
    _add(ADDED)


def downgrade() -> None:
    _drop(ADDED)
