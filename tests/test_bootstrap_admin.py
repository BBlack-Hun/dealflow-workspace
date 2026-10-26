"""첫 관리자 만들기(`scripts/bootstrap.py`) — 관리자가 없을 때만, 비밀번호는 난수로 한 번.

이 스크립트는 컨테이너가 뜰 때마다 돈다(`scripts/entrypoint.sh`). 그래서 두 번째
부터는 계정을 건드리지 않고, 비밀번호도 다시 찍지 않아야 한다.
"""
from __future__ import annotations

import re

from sqlalchemy import select

from app import config
from app.models import User
from app.services import auth as auth_svc
from scripts import bootstrap as bs

LINE = re.compile(r"첫 관리자 — 번호 (\d+) · 비밀번호 (\S+)")


def _admins(db) -> list:
    db.expire_all()
    return db.execute(select(User).where(User.role == "admin")).scalars().all()


def test_빈_DB_에는_난수_비밀번호로_한_명(db, capsys):
    bs.bootstrap(db)
    db.commit()
    found = LINE.search(capsys.readouterr().out)
    assert found, "비밀번호가 로그에 안 찍혔습니다"
    phone, password = found.groups()

    (admin,) = _admins(db)
    assert admin.phone == phone
    assert admin.must_change_password == 1
    assert password != config.INITIAL_PASSWORD
    assert auth_svc.verify_password(password, admin.password_hash)
    assert not auth_svc.verify_password(config.INITIAL_PASSWORD, admin.password_hash)

    # 다시 떠도 아무것도 안 만들고, 비밀번호도 다시 안 찍는다.
    bs.bootstrap(db)
    db.commit()
    assert not LINE.search(capsys.readouterr().out)
    assert len(_admins(db)) == 1


def test_관리자가_있으면_만들지_않는다(db, capsys):
    db.add(User(name="관리샘플", phone="01000000009", role="admin",
                password_hash=auth_svc.hash_password("sample-pass-1")))
    db.commit()
    bs.bootstrap(db)
    db.commit()
    assert not LINE.search(capsys.readouterr().out)
    assert [a.phone for a in _admins(db)] == ["01000000009"]


def test_컨테이너가_뜰_때_데모_시드와_함께(db, capsys, monkeypatch):
    """`main()` 흐름 그대로 — 데모 계정은 지금처럼 팀 공통 초기 비밀번호로 들어온다."""
    monkeypatch.setattr(config, "SEED_DEMO", True)
    bs.main()
    found = LINE.search(capsys.readouterr().out)
    assert found
    db.expire_all()
    for spec in bs.DEMO_USERS:
        user = db.execute(select(User).where(User.phone == spec["phone"])).scalar_one()
        assert auth_svc.verify_password(config.INITIAL_PASSWORD, user.password_hash)
        assert user.must_change_password == 1
    (admin,) = _admins(db)
    assert auth_svc.verify_password(found.group(2), admin.password_hash)

    bs.main()
    assert not LINE.search(capsys.readouterr().out)
