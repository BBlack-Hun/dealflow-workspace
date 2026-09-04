"""팀원 계정을 만든다 (관리자용).

데모 사용자를 지우고 나면 계정을 만들 수단이 필요하다. 화면에서 계정을 만드는
관리자 페이지는 아직 없으므로 그 자리를 이 스크립트가 대신한다.

- 로그인 ID 는 휴대폰번호(숫자만). 하이픈을 넣어도 알아서 뗀다.
- 비밀번호는 팀 공통 초기값(``DEALFLOW_INITIAL_PASSWORD``)으로 넣고
  **첫 로그인 후 변경 화면으로 유도**한다(must_change_password=1).
- 에이전트 토큰을 함께 발급한다. 사용자 1명 = 에이전트 1대가 원칙이라
  같은 토큰을 두 PC 에 넣으면 잡이 어느 쪽으로 갈지 예측할 수 없다.

    python scripts/add_user.py --name 홍길동 --phone 010-1234-5678
    python scripts/add_user.py --name 관리자 --phone 01000000000 --role admin
    python scripts/add_user.py --list
"""
from __future__ import annotations

import argparse
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app import config, deps  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.models import AgentDevice, User, VcContact  # noqa: E402
from app.services import auth as auth_svc  # noqa: E402


def list_users(db) -> None:
    rows = db.execute(select(User).order_by(User.id)).scalars().all()
    if not rows:
        print("계정이 없습니다.")
        return
    print(f"{'id':>3}  {'이름':10} {'휴대폰':13} {'권한':6} {'담당자':>5}  {'비번변경':6} 토큰")
    for u in rows:
        n = db.query(VcContact).filter_by(user_id=u.id).count()
        dev = db.execute(select(AgentDevice).where(AgentDevice.user_id == u.id)).scalars().first()
        token = (dev.token[:12] + "…") if dev else "-"
        flag = "필요" if u.must_change_password else "완료"
        print(f"{u.id:>3}  {u.name or '':10} {u.phone:13} {u.role:6} {n:>5}  {flag:6} {token}")


def add_user(db, name: str, phone: str, role: str) -> User:
    normalized = auth_svc.normalize_phone(phone)
    if len(normalized) < 10:
        raise SystemExit(f"휴대폰번호가 이상합니다: {phone!r} → {normalized!r}")

    exists = db.execute(select(User).where(User.phone == normalized)).scalars().first()
    if exists:
        raise SystemExit(f"이미 있는 번호입니다: {normalized} (id={exists.id}, {exists.name})")

    # 투자현황은 **계정마다** 켜고 끈다(0054). 기본값은 팀 현황의 [계정 만들기]·
    # `bootstrap.py` 와 **같은 함수**에서 가져온다 — 계정을 만드는 자리가 셋인데
    # 하나만 제 숫자를 들고 있으면, 그 자리로 만든 관리자만 조용히 꺼진 채로
    # 나온다. 본인 것은 못 켜므로 다른 관리자를 불러야 하는 상태가 된다.
    user = User(
        name=name,
        phone=normalized,
        role=role,
        can_view_consulting=1 if deps.consulting_default_for(role) else 0,
        # 자료 자동 첨부도 같은 자리에서 가져온다(0059) — 지금은 어느 역할도
        # 켜지 않고, 관리자가 팀 현황에서 켠다.
        can_auto_attach_ir=1 if deps.auto_attach_default_for(role) else 0,
        password_hash=auth_svc.hash_password(config.INITIAL_PASSWORD),
        must_change_password=1,
    )
    db.add(user)
    db.flush()

    token = f"agt_{secrets.token_hex(16)}"
    db.add(AgentDevice(user_id=user.id, token=token, hostname="", agent_version=""))
    db.commit()

    print(f"계정 생성: id={user.id} {name} / {normalized} ({role})")
    print(f"  초기 비밀번호: {config.INITIAL_PASSWORD}  (첫 로그인 후 변경 요구)")
    print(f"  에이전트 토큰: {token}")
    print("  → 이 사용자로 로그인해 /setup 에서 에이전트를 내려받게 하세요.")
    return user


def main() -> None:
    ap = argparse.ArgumentParser(description="팀원 계정 생성")
    ap.add_argument("--name")
    ap.add_argument("--phone", help="휴대폰번호 (하이픈 있어도 됨)")
    ap.add_argument("--role", default="user", choices=["user", "admin"])
    ap.add_argument("--list", action="store_true", help="계정 목록만 출력")
    args = ap.parse_args()

    db = SessionLocal()
    try:
        if args.list:
            list_users(db)
            return
        if not (args.name and args.phone):
            ap.error("--name 과 --phone 이 필요합니다 (목록만 보려면 --list)")
        add_user(db, args.name, args.phone, args.role)
    finally:
        db.close()


if __name__ == "__main__":
    main()
