"""투자현황을 **계정마다** 켜고 끈다 — 역할이 곧 권한이던 것을 푼다

## 무엇이 바뀌나

지금까지 투자현황(투자컨설턴트 화면)은 **역할이 곧 권한**이었다.

    관리자 · 투자컨설턴트    역할만으로 늘 열림 — 팀 현황에 단추가 뜨지 않았다
    팀원                    `users.can_view_consulting` 칸으로 켜고 끔

그래서 "그냥 투자현황을 보여줬다 말았다" 하려는데 관리자·컨설턴트는 개별로
막을 길이 없었다. 이제 판정은 칸 하나뿐이고(`deps.may_view_consulting`),
역할이 하는 일은 **새 계정의 기본값**뿐이다(`deps.consulting_default_for`).

## 왜 데이터를 손대야 하나

판정에서 역할을 빼는 순간, 칸이 `0` 인 관리자·컨설턴트는 **지금 보고 있는
화면을 잃는다.** 코드만 바꾸면 배포한 그 순간 그 사람들 사이드바에서 메뉴가
사라진다 — 아무도 끄지 않았는데.

그래서 지금까지 **역할로 열려 있던 계정을 켜 둔 상태로 옮긴다.** 옮기고 나면
화면에 보이는 것은 이전과 똑같고, 달라지는 것은 이제부터 끌 수 있다는 것뿐이다.

정지된 계정(`is_active = 0`)도 함께 켠다 — 다시 살렸을 때 예전과 같은 상태여야
한다. 되살리는 자리가 권한까지 다시 챙기게 두면 그쪽이 낡는다.

## 되돌리기

**옮겨 둔 것을 도로 끈다.** 내려가면 코드도 함께 되돌아가 판정이 다시
`역할 or 칸` 이 되는데, 그 코드에서 관리자·투자컨설턴트는 앞쪽 `역할` 에서
이미 통과한다 — 이 칸이 `1` 이든 `0` 이든 그 사람들에게 보이는 것은 똑같다.
그러니 되돌린 그 순간 달라지는 것은 없고, 올린 자리만 그대로 되짚는다.

올린 자리를 두고 내려가면 그 다음이 위험하다. 다시 올릴 때 무엇이 이 판이 켠
값이고 무엇이 사람이 켠 값인지 아무도 구분하지 못한다.

잃는 것은 하나 있다. 옮기기 전부터 이 칸이 `1` 이던 관리자·컨설턴트(팀원일 때
켜 뒀다가 역할이 올라간 계정)의 그 `1` 은 여기서 지워진다. 되돌린 코드가 그
값을 읽지 않으니 당장은 아무 일도 없고, 그 계정이 나중에 팀원으로 내려오는 날
꺼진 채로 보인다 — 그때 관리자가 팀 현황에서 다시 켜 주면 된다.

Revision ID: 0054_consulting_per_account
Revises: 0053_ir_delivery_no_links
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0054_consulting_per_account"
down_revision = "0053_ir_delivery_no_links"
branch_labels = None
depends_on = None

#: 지금까지 **역할만으로** 투자현황이 열려 있던 역할.
#: 코드 쪽 짝은 `deps.consulting_default_for` 다 — 이 마이그레이션은 한 번
#: 실행되고 끝나므로 값을 그때 상태 그대로 여기 적어 둔다(그 함수가 나중에
#: 바뀌어도 이미 옮긴 데이터가 따라 움직여서는 안 된다).
ROLES_ALWAYS_ON = ("admin", "consultant")


def _users() -> sa.TableClause:
    """이 판이 손대는 칸만 들고 있는 `users`.

    모델(`app.models.User`)을 부르지 않는다 — 마이그레이션은 **그때의 표**를
    보아야 하는데 모델은 늘 최신이라, 나중에 칸이 하나 늘면 옛 DB 에서 이 판이
    없는 칸을 찾는다.
    """
    return sa.table("users",
                    sa.column("role", sa.String),
                    sa.column("can_view_consulting", sa.Integer))


def _set(value: int) -> None:
    """역할로 열려 있던 계정의 칸을 한 값으로 맞춘다 — 올리기/내리기가 같은 줄."""
    users = _users()
    op.execute(
        users.update()
        .where(users.c.role.in_(ROLES_ALWAYS_ON))
        .values(can_view_consulting=value)
    )


def upgrade() -> None:
    _set(1)


def downgrade() -> None:
    """올린 자리를 그대로 되짚는다 — 위 `## 되돌리기` 참고."""
    _set(0)
