"""[모든 팀원에게 적용] 을 되돌릴 자리 — `template_apply_backups`

## 무엇이 문제였나

관리자가 팀 기본 문구를 고쳐도 팀원의 발송은 그대로였다. 문구를 고르는 규칙이
**고른 것 > 내 것 > 팀 것(하나뿐일 때)** 이라(`services/template_pick.py`), 각자
골라 둔 것이나 만들어 둔 내 문구가 팀 문구보다 먼저 나간다. 모두가 같은 문구로
나가야 할 때(딜 소싱 제안 · 딜소개 인사말 · 안내문) 사람마다 화면에 들어가 다시
고르라고 할 수는 없다.

그래서 관리자에게 [모든 팀원에게 적용] 을 둔다. 이것은 **사람이 손으로 정해 둔
것을 덮는 일**이다 — 각자의 선택이 이 문구로 바뀌고, 그 자리의 개인 문구는
꺼진다. 잘못 누르면 되돌릴 길이 있어야 누를 수 있는 단추가 된다.

## 왜 칸이 아니라 표인가

덮는 것이 두 표(`template_choices` · `message_templates`)에 걸쳐 있고, 한 번 누를
때 몇 사람 · 몇 문구가 바뀔지 정해져 있지 않다. 칸 하나로는 "이번 한 번에 무엇이
바뀌었나" 를 담을 수 없다 — `0052_one_liner_bulk_undo` 가 표를 둔 것과 같은
이유다. 그쪽과 다른 점은 **누른 한 번이 한 줄**이라는 것이다(사람마다의 선택과
끈 문구 번호는 JSON 으로 그 줄에 담는다 — 모델 설명 참고).

## 표의 모양

    user_id          누가 눌렀나 (언제는 created_at)
    kind · variant   어느 자리인가 — `template_choices` 와 같은 열쇠
    template_id      적용한 팀 문구 (외래키 없음 — 문구 삭제를 막지 않으려고)
    previous_json    덮기 전의 선택 [{user_id, template_id | null}]
    turned_off_json  끈 개인 문구 [{id, sig}] — sig 로 그 뒤에 고쳤는지 본다
    restored_at      되돌린 때. 비어 있으면 아직 되돌리지 않았다

## 이 판의 번호

`0100_sender_rooms` 바로 뒤다. 번호가 차례대로가 아닌 까닭은 판 계보가
`0095 → 0101 → 0102 → 0096 → … → 0100` 으로 이어져 있어서다(0101·0102 가 먼저
들어가고 열려 있던 0096 ~ 0100 이 그 뒤로 옮겨 붙었다). 머리는 `0100_sender_rooms`
이고 이 판이 그 뒤에 선다 — 머리가 하나여야 한다(`tests/test_migrations.py`).

## 빈 DB 에서는 아무 일도 하지 않는다

`0001_initial` 이 `create_all()` 로 지금 모델 전체를 만들어, 새 DB 는 이 표를 이미
갖고 시작한다. 있는지 보고 만든다(0052 와 같은 방식).

## 되돌아가나

`downgrade` 는 표를 통째로 지운다. 되돌리기 버퍼라 잃는 것은 **아직 되돌리지 않은
적용을 되돌릴 길**뿐이다 — 문구와 선택 자체는 제 표에 그대로 있다.

Revision ID: 0103_template_apply_backups
Revises: 0100_sender_rooms
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0103_template_apply_backups"
down_revision = "0100_sender_rooms"
branch_labels = None
depends_on = None

TABLE = "template_apply_backups"


def _has_table(name: str) -> bool:
    return name in sa.inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    if _has_table(TABLE):
        return
    op.create_table(
        TABLE,
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("kind", sa.String(), nullable=False),
        # NULL 이 아니라 빈 문자열 — `template_choices.variant` 와 같은 값으로
        # 맞춰 봐야 하는 칸이다.
        sa.Column("variant", sa.String(), nullable=False, server_default=""),
        sa.Column("template_id", sa.Integer(), nullable=False),
        sa.Column("previous_json", sa.Text(), nullable=False),
        sa.Column("turned_off_json", sa.Text(), nullable=False),
        sa.Column("restored_at", sa.String(), nullable=True),
        sa.Column("created_at", sa.String(), nullable=True),
        sa.Column("updated_at", sa.String(), nullable=True),
    )


def downgrade() -> None:
    if _has_table(TABLE):
        op.drop_table(TABLE)
