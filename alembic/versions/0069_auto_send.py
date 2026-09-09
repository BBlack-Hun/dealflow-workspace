"""자동 발송 — 설정 한 줄(`auto_send_settings`)과 나갔다는 표시(`auto_send_runs`)

## 왜 표가 둘인가

**설정**은 종류마다 한 줄이고 사람이 고친다(켜기/끄기 · 보내는 계정 · 시각 ·
하루 상한). **표시**는 건마다 한 줄이고 기계가 넣는다 — 같은 건이 두 번 나가는
것을 막는 자리라 지워지면 안 된다. 성격이 다르니 표도 다르다.

`auto_send_runs` 의 유일 색인이 `(kind, ref_id)` 인 것이 이 판의 알맹이다.
`sms_notices` 는 `(kind, day, user_id)` 였지만, 여기에 날짜를 넣으면 **다음 날
같은 건이 또 나간다** — 결과 문의는 담당자가 결과를 적기 전까지 목록에 계속
남아 있기 때문이다. 까닭은 `models.AutoSendRun` 에 적어 두었다.

## 빈 DB 에서는 아무 일도 하지 않는다

`0001_initial` 이 `create_all()` 로 지금 모델 전체를 만들어, 새 DB 는 이 표들을
이미 갖고 시작한다. 여기서 또 만들면 `table already exists` 로 **부팅이 죽는다**
(`tests/test_migrations.py` 가 지키는 그것이다). 그래서 있는지 보고 만든다.

색인도 표를 만드는 `if` **밖에서** 따로 본다. 안에 넣어 두면 빈 DB 길에서 통째로
건너뛰어, 실제로 그렇게 12개가 빠져 있었다.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0069_auto_send"
down_revision = "0067_consulting_columns_per_sheet"
branch_labels = None
depends_on = None


def _tables() -> set:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _indexes(table: str) -> set:
    inspector = sa.inspect(op.get_bind())
    if table not in inspector.get_table_names():
        return set()
    return {ix["name"] for ix in inspector.get_indexes(table)}


def upgrade() -> None:
    tables = _tables()

    if "auto_send_settings" not in tables:
        op.create_table(
            "auto_send_settings",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("kind", sa.String(), nullable=False),
            # **기본은 꺼짐.** 줄이 있어도 켜기 전에는 아무 일도 없다.
            sa.Column("enabled", sa.Integer(), nullable=False,
                      server_default="0"),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"),
                      nullable=True),
            sa.Column("from_hour", sa.Integer(), nullable=False,
                      server_default="10"),
            sa.Column("until_hour", sa.Integer(), nullable=False,
                      server_default="17"),
            sa.Column("max_per_day", sa.Integer(), nullable=False,
                      server_default="10"),
            sa.Column("created_at", sa.String(), nullable=True),
            sa.Column("updated_at", sa.String(), nullable=True),
            sa.UniqueConstraint("kind", name="uq_auto_send_settings_kind"),
        )

    if "auto_send_runs" not in tables:
        op.create_table(
            "auto_send_runs",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("kind", sa.String(), nullable=False),
            sa.Column("ref_id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"),
                      nullable=False),
            sa.Column("day", sa.String(), nullable=False),
            sa.Column("job_id", sa.Integer(), sa.ForeignKey("send_jobs.id"),
                      nullable=True),
            sa.Column("status", sa.String(), nullable=False,
                      server_default="claimed"),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("created_at", sa.String(), nullable=True),
            sa.Column("updated_at", sa.String(), nullable=True),
            sa.UniqueConstraint("kind", "ref_id",
                                name="uq_auto_send_runs_kind_ref"),
        )

    # 하루 상한을 셀 때마다 훑는 자리다. 표를 만드는 `if` 밖에 둔다.
    if "ix_auto_send_runs_kind_day" not in _indexes("auto_send_runs"):
        op.create_index("ix_auto_send_runs_kind_day", "auto_send_runs",
                        ["kind", "day"])


def downgrade() -> None:
    # **되돌리기가 비어 있으면 그 판을 지나는 되돌리기 전체가 계획 단계에서
    # 멎는다**(0012 가 그랬다 — `tests/test_migrations.py` 참고).
    if "ix_auto_send_runs_kind_day" in _indexes("auto_send_runs"):
        op.drop_index("ix_auto_send_runs_kind_day", table_name="auto_send_runs")
    tables = _tables()
    if "auto_send_runs" in tables:
        op.drop_table("auto_send_runs")
    if "auto_send_settings" in tables:
        op.drop_table("auto_send_settings")
