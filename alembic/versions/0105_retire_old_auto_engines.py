"""#31 자동화 전환 — 옛 두 엔진의 설정을 **꺼진 2단계 자동화 줄**로 옮긴다(자료만)

미팅 후기 대기 목록(`auto_send` 의 `meeting_review`)과 스타트업 매월 30일 자동
(`startup_ir` 줄의 `monthly_auto`)을 걷고, 같은 일을 2단계 자동화 A7 · A5 하나씩만
맡는다(사용자 결정 2026-10-17). 표도 칸도 그대로다 — 이 판은 **값만** 옮긴다.

1. **A5(`automations.key = 'startup_monthly'`)** — 옛 `startup_ir` 설정이 있으면
   그 계정을 보내는 계정으로 적는다(A5 는 메뉴의 계정으로만 나간다 —
   `automation.startup_menu_sender`).
   - 줄이 없고 옛 설정이 있으면 세운다: **꺼짐 · 시험 모드 · 월말 순환**(`26 11:00 /
     30 13:00 / 28 14:00`) · 문구 3개. 켜는 것은 사람이다 — 11월이 A5 의 첫 달이고,
     켤 때까지 매월 자동 발송은 없다(10월은 이미 회차가 있다).
   - 줄이 있으면 켜짐 · 시험 모드는 그대로 두고, 저장된 순환이 **옛 기본값**
     (`15 11:00 / 20 13:00 / 16 14:00`)일 때만 월말로 바꾼다(옛 설정이 없어도) —
     사람이 고친 순환은 둔다. 글이 `{달} 말 기준` 이라 옛 기본값으로는 월중에 월말
     현황이 나간다.
   - 단, **메뉴가 꺼졌거나 없으면 켜진 A5 도 끈다** — 앱의 규칙(메뉴 꺼짐 ⇒ A5
     꺼짐, `automation.follow_startup_menu`)을 이주가 깨지 않게.
2. **옛 30일 자동** — `startup_ir` 줄의 `monthly_auto` 를 0 으로. 읽는 코드는 이미
   없지만, 옛 이미지로 되돌린 날 그 자동이 A5 와 나란히 다시 서지 않게 한다
   (덜 보내는 쪽). 메뉴 켜짐 · 계정은 그대로다.
3. **팀 공통 자동 발송 계정(`_team`)** — 비어 있고 **옛 `startup_ir` 설정에도 계정이
   없을 때만** 옛 `meeting_review` 설정의 계정을 넣는다(줄이 없으면 꺼짐 · 시험
   모드로 세운다). 옛 기본 계정의 차례가 스타트업 → 미팅 후기였다 — 스타트업
   계정이 있는데 미팅 후기 계정을 박으면 기본이 바뀌고 그대로 굳는다. 그때는 비운
   채 두어 지금처럼 메뉴의 계정을 따른다(PR #315 리뷰). 차 있으면 그대로.

**지우는 자료는 없다** — `auto_send_settings` · `auto_send_runs` 의 줄은 이력으로
남는다.

## 수정 로그

이주는 요청 밖에서 돌아 수정 로그(`edit_log`)에 남지 않는다 — 운영 반영 기록과
PR 이 그 자리다(앞선 자료 판들과 같다).

## 빈 DB

`0001_initial` 이 `create_all()` 로 표를 다 만든다. 설정 줄이 없으면 할 일이 없다.

## 되돌리기

아무것도 안 한다. A5 줄은 꺼진 채 남고(옛 코드도 그 줄을 읽는다 — 꺼짐이다),
`monthly_auto` 는 0 그대로다 — 옛 30일 자동을 다시 쓰려면 옛 판에서 사람이 켠다.
무엇이 1 이었는지 기억할 칸이 없고, 모르는 채로 켜는 것보다 꺼 두는 쪽이 안전하다.

Revision ID: 0105_retire_old_auto_engines
Revises: 0104_sourcing_vc_link_confirmed
"""
from __future__ import annotations

import json
from datetime import datetime

import sqlalchemy as sa
from alembic import op

revision = "0105_retire_old_auto_engines"
down_revision = "0104_sourcing_vc_link_confirmed"
branch_labels = None
depends_on = None

A5_KEY = "startup_monthly"
TEAM_KEY = "_team"
#: `services/automations/startup_monthly.DEFAULT_SLOTS` 와 같은 글자 — 판이 굳은
#: 값을 적는다(앱의 기본값이 나중에 바뀌어도 이 판이 한 일은 그대로다).
SLOTS = ["26 11:00", "30 13:00", "28 14:00"]
OLD_SLOTS = ["15 11:00", "20 13:00", "16 14:00"]
VARIANTS = 3


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _params(raw):
    try:
        value = json.loads(raw or "{}")
    except ValueError:
        return None
    return value if isinstance(value, dict) else None


def upgrade() -> None:
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())
    if not {"automations", "auto_send_settings"} <= tables:
        return
    settings = {kind: (uid, enabled) for kind, uid, enabled in bind.execute(sa.text(
        "SELECT kind, user_id, enabled FROM auto_send_settings "
        "WHERE kind IN ('startup_ir', 'meeting_review')"))}
    senders = {kind: uid for kind, (uid, _on) in settings.items()}
    startup_uid = senders.get("startup_ir")
    review_uid = senders.get("meeting_review")
    # 메뉴가 켜져 있나 — `startup_send.is_on` 과 같은 판정(켜짐 · 계정 둘 다).
    menu_on = bool(startup_uid and settings.get("startup_ir", (None, 0))[1])
    now = _now()

    # ① A5 — 줄이 없으면 옛 스타트업 설정이 있을 때만 세운다(없으면 줄 없음 =
    # 꺼짐 · 기본값). 줄이 있으면 설정이 없어도 옛 기본 순환은 월말로 맞춘다.
    a5 = bind.execute(sa.text(
        "SELECT id, user_id, params, enabled FROM automations WHERE key = :k"),
        {"k": A5_KEY}).first()
    if a5 is None:
        if "startup_ir" in senders:
            bind.execute(sa.text(
                "INSERT INTO automations (key, enabled, user_id, test_mode, test_room, "
                "params, created_at, updated_at) VALUES (:k, 0, :u, 1, NULL, :p, :n, :n)"),
                {"k": A5_KEY, "u": startup_uid, "n": now,
                 "p": json.dumps({"slots": SLOTS, "variants": VARIANTS},
                                 ensure_ascii=False, sort_keys=True)})
    else:
        params = _params(a5.params)
        changed = {}
        if params is not None and params.get("slots") == OLD_SLOTS:
            params["slots"] = SLOTS
            changed["p"] = json.dumps(params, ensure_ascii=False, sort_keys=True)
        if startup_uid and a5.user_id != startup_uid:
            changed["u"] = startup_uid
        if a5.enabled and not menu_on:
            changed["e"] = 0
        if changed:
            sets = ", ".join(
                [s for s, k in (("params = :p", "p"), ("user_id = :u", "u"),
                                ("enabled = :e", "e"))
                 if k in changed] + ["updated_at = :n"])
            bind.execute(sa.text(f"UPDATE automations SET {sets} WHERE id = :id"),
                         {**changed, "n": now, "id": a5.id})

    # ② 옛 30일 자동은 내린다.
    bind.execute(sa.text(
        "UPDATE auto_send_settings SET monthly_auto = 0, updated_at = :n "
        "WHERE kind = 'startup_ir' AND monthly_auto != 0"), {"n": now})

    # ③ 팀 공통 자동 발송 계정 — 비어 있고 스타트업 계정도 없을 때만 옛 미팅 후기
    # 계정으로(옛 기본 계정 차례). 스타트업 계정이 있으면 비운 채 메뉴를 따른다.
    if review_uid and not startup_uid:
        team = bind.execute(sa.text(
            "SELECT id, user_id FROM automations WHERE key = :k"),
            {"k": TEAM_KEY}).first()
        if team is None:
            bind.execute(sa.text(
                "INSERT INTO automations (key, enabled, user_id, test_mode, test_room, "
                "params, created_at, updated_at) VALUES (:k, 0, :u, 1, NULL, NULL, :n, :n)"),
                {"k": TEAM_KEY, "u": review_uid, "n": now})
        elif not team.user_id:
            bind.execute(sa.text(
                "UPDATE automations SET user_id = :u, updated_at = :n WHERE id = :id"),
                {"u": review_uid, "n": now, "id": team.id})


def downgrade() -> None:
    # 머리말 `되돌리기` — 자료만 옮긴 판이라 내릴 때 할 일이 없다.
    pass
