"""**투자사 관리 현황 줄 여럿에 `Series A 딜 소싱` O 를 한꺼번에** — 미리보기가 기본이다.

화면에서 한 줄씩 O 를 넣는 것과 **같은 함수**(`sourcing_sync.set_mark`)를 지난다.
그래서 잇기 규칙도 그대로다 — 딜 소싱 `시리즈 A 이상 딜 소싱 참여 심사역` 갈래에서
이름 + 번호가 둘 다 같은 줄이 있으면 잇고, 번호만 · 이름+회사만 같으면 **막고**
(딜 소싱 화면의 [이 분으로 확정]으로 넘긴다), 아무도 없으면 새 줄을 만든다.

    # ① 미리보기 (기본) — 운영 DB 의 **복사본**에서 같은 길을 돌려 수만 센다
    python scripts/apply_sourcing_marks.py --ids-file /path/ids.txt \
        --assignee "담당 이름"

    # ② 실제로 넣는다
    python scripts/apply_sourcing_marks.py --ids-file /path/ids.txt \
        --assignee "담당 이름" --apply

## 무엇을 넣나

  · 새 줄의 `참여` — `--participation`(기본 `딜 소싱 참여 제안 대기중`). 동의 전인
    분은 딜 소싱 제안을 **받지 않는다**(`sourcing_sync.takes_part` — 정확히 `참여`
    만 받는다). 동의하시면 딜 소싱 화면에서 `참여` 로 바꾼다.
  · 새 줄의 담당 — `--assignee`. 안 주면 `--user-id` 계정 이름, 그것도 없으면
    그 투자사 줄 주인 계정 이름(`sourcing_sync.assignee_for` — 화면과 같다).
    계정 이름(`users.name`)이 팀이 딜 소싱 담당 칸에 적어 온 이름과 다를 수 있어
    직접 넘기는 길을 둔다.
  · **이미 있는 줄은 덮지 않는다** — 이어지기만 하는 줄의 담당 · 참여(참여 · 물어보는
    중 · 사람이 적은 문구)는 그대로다. 투자사 관리 현황의 담당자 칸도 안 건드린다.

## 건너뛰는 줄

  · id 가 없는 줄 · 감춘 줄(`is_hidden`) — 화면에도 안 뜨는 줄이다.
  · 이미 `불참여`(X)인 줄(이어진 줄 · O 를 넣으면 이어질 줄 모두) — **스스로 안
    하겠다고 한 분일 수 있다.** 화면의 O 는 다시 묻는 것으로 보아 `제안 대기중` 으로
    되돌리지만, 한꺼번에 넣을 때는 건드리지 않는다. 정말로 다시 물을 거면
    `--revive-left` 를 준다.

## 미리보기는 운영 DB 에 쓰지 않는다

`--apply` 가 없으면 DB 파일을 **읽기 전용으로 열어 임시 복사본을 뜨고**, 복사본에서
`set_mark` 를 그대로 돌린다(새 줄 · 잇기가 앞 줄의 결과를 보도록 줄마다 flush 한다).
끝나면 복사본을 지운다. 그래서 미리보기 수와 `--apply` 수가 같다.

`--apply` 는 **끝에 한 번** 저장한다 — 중간에 멈추면 아무것도 안 들어간다.

## 이름을 찍지 않는다

줄마다 **id 와 한 일**만 찍는다. 막힌 까닭(`SyncError`)에는 딜 소싱 줄 이름이 들어
있을 수 있어 `--show-reasons` 일 때만 찍는다. id 목록 · 담당 이름은 코드에 적지 않고
실행할 때 넘긴다(공개 저장소).
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys
import tempfile
from collections import Counter
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

#: 한 일 → 찍을 이름. 차례가 곧 요약 차례다.
LABELS = {
    "created": "새 줄",
    "linked": "기존 줄과 이음",
    "changed": "참여만 바꿈",
    "kept": "그대로(이미 갈래에 있음)",
    "blocked": "막힘",
    "skipped": "건너뜀",
}


def read_ids(path: str) -> List[int]:
    """한 줄에 하나(쉼표 · 빈칸으로 여럿도 된다). `#` 뒤는 주석. 같은 id 는 한 번만."""
    out: List[int] = []
    seen = set()
    for n, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        body = line.split("#", 1)[0]
        for token in body.replace(",", " ").split():
            try:
                value = int(token)
            except ValueError:
                raise SystemExit(f"{path}:{n} — id 가 아닙니다: {token!r}") from None
            if value not in seen:
                seen.add(value)
                out.append(value)
    return out


def sqlite_path(url: str) -> Optional[str]:
    prefix = "sqlite:///"
    return url[len(prefix):] if url.startswith(prefix) else None


def copy_db(src: str) -> str:
    """운영 DB 를 **읽기 전용으로 열어** 임시 파일로 뜬다(sqlite 백업 — WAL 까지 한 판)."""
    fd, dst = tempfile.mkstemp(prefix="sourcing-marks-", suffix=".db")
    os.close(fd)
    source = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
    target = sqlite3.connect(dst)
    try:
        source.backup(target)
    finally:
        target.close()
        source.close()
    return dst


def run(db, ids: List[int], *, participation: str, assignee: Optional[str],
        user, revive_left: bool) -> List[tuple]:
    """id 마다 `set_mark(…, "O")` — `(id, 한 일, 까닭)` 목록. 커밋은 부르는 쪽이 한다."""
    from app.models import VcContact
    from app.services import sourcing_sync

    results = []
    for cid in ids:
        contact = db.get(VcContact, cid)
        if contact is None:
            results.append((cid, "skipped", "투자사 관리 현황에 없는 id"))
            continue
        if contact.is_hidden:
            results.append((cid, "skipped", "감춘 줄"))
            continue
        linked = sourcing_sync.linked_row(db, contact)
        if linked is None:
            # 아직 안 이어진 줄도 — `set_mark` 가 이어 붙일 그 줄이 불참여면 같다.
            try:
                linked = sourcing_sync.find_row(db, contact)
            except sourcing_sync.SyncError:
                pass        # 막히는 줄은 아래 `set_mark` 가 같은 까닭으로 막는다
        if linked is not None and sourcing_sync.is_left(linked) and not revive_left:
            results.append((cid, "skipped", "이미 불참여(X) — 건드리지 않음(--revive-left)"))
            continue
        # `set_mark` 는 막을 때 **아무것도 고치기 전에** 막는다(`SyncError` 는 잇기 ·
        # 만들기 앞에서만 난다) — 그래서 되감을 것이 없고, 저장은 끝에 한 번이다.
        try:
            got = sourcing_sync.set_mark(db, contact, "O", user, assignee=assignee,
                                         participation=participation)
        except sourcing_sync.SyncError as exc:
            results.append((cid, "blocked", str(exc)))
            continue
        # 다음 줄의 잇기 · 같은 사람 찾기가 이 줄의 결과를 보도록.
        db.flush()
        results.append((cid, got["action"], got.get("participation", "")))
    return results


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="투자사 관리 현황 줄에 Series A 딜 소싱 O 를 한꺼번에")
    ap.add_argument("--ids-file", required=True, help="vc_contacts.id 목록 파일(한 줄에 하나)")
    ap.add_argument("--participation", default=None,
                    help="새 줄의 참여 칸(기본: 딜 소싱 참여 제안 대기중)")
    ap.add_argument("--assignee", default=None, help="새 줄의 딜 소싱 담당 이름")
    ap.add_argument("--user-id", type=int, default=None,
                    help="O 를 넣은 계정 — 수정 로그에 남고, --assignee 가 없으면 담당 이름")
    ap.add_argument("--revive-left", action="store_true",
                    help="이미 불참여(X)인 줄도 O 로(→ 참여 칸을 다시 묻는 값으로)")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="미리보기(기본)")
    mode.add_argument("--apply", action="store_true", help="실제로 저장")
    ap.add_argument("--show-reasons", action="store_true",
                    help="막힌 까닭을 찍는다(딜 소싱 줄 이름이 들어 있을 수 있다)")
    args = ap.parse_args(argv)

    from app import config
    from app.models import User
    from app.services import edit_log, sourcing_sync

    try:
        participation = sourcing_sync.normalize_participation(
            args.participation or sourcing_sync.OFFER_PENDING)
    except sourcing_sync.SyncError as exc:
        print(f"--participation: {exc}", file=sys.stderr)
        return 2
    ids = read_ids(args.ids_file)
    if not ids:
        print("id 가 하나도 없습니다.", file=sys.stderr)
        return 2

    copy = engine = None
    if args.apply:
        from app.db import SessionLocal

        db = SessionLocal()
    else:
        src = sqlite_path(config.DATABASE_URL)
        if src is None:
            print("미리보기는 SQLite DB 에서만 돕니다(복사본을 떠서 돌린다).", file=sys.stderr)
            return 2
        copy = copy_db(src)
        engine = create_engine(f"sqlite:///{copy}", future=True)
        db = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False,
                          future=True)()

    edit_log.install()
    token = None
    user = None
    try:
        if args.user_id is not None:
            user = db.get(User, args.user_id)
            if user is None:
                print(f"--user-id {args.user_id} 계정이 없습니다.", file=sys.stderr)
                return 2
            token = edit_log.begin(user.id, "SCRIPT", "scripts/apply_sourcing_marks.py")
        results = run(db, ids, participation=participation, assignee=args.assignee,
                      user=user, revive_left=args.revive_left)
        if args.apply:
            db.commit()
        else:
            db.rollback()
    finally:
        if token is not None:
            edit_log.end(token)
        db.close()
        if engine is not None:
            engine.dispose()        # 열린 연결을 닫아야 -wal · -shm 이 지워진다
        if copy is not None:
            for path in (copy, copy + "-wal", copy + "-shm"):
                try:
                    os.remove(path)
                except OSError:
                    pass

    counts = Counter(action for _, action, _ in results)
    print("미리보기 — 운영 DB 에는 쓰지 않았습니다(복사본에서 돌림)" if not args.apply
          else "저장했습니다.")
    print(f"새 줄 참여: {participation} · 새 줄 담당: "
          f"{args.assignee or '(넘기지 않음 — 계정 이름)'}")
    for cid, action, why in results:
        note = why
        if action == "blocked" and not args.show_reasons:
            note = "(까닭은 --show-reasons)"
        print(f"  {cid:>6}  {LABELS.get(action, action)}" + (f" — {note}" if note else ""))
    print("합계: " + " · ".join(f"{LABELS[k]} {counts.get(k, 0)}" for k in LABELS)
          + f" (모두 {len(results)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
