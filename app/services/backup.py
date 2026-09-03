"""하루 한 번 데이터를 떠 두고, 관리자가 그 지점으로 되돌린다.

**왜 컨테이너 안에서 도는가.**

백업은 원래 호스트의 크론이 하기로 되어 있었다(`deploy/README.md` 8장이
`/etc/cron.daily/dealflow-backup` 을 만드는 명령을 적어 두었다). 그런데 실제
서버에는 그 크론이 **없다** — `dealflow`·`root`·`ubuntu` 어느 크론탭에도,
`/etc/cron.d` 에도, systemd 타이머에도 없다. 지금 남아 있는 백업은 배포할
때마다 `deploy.sh` 가 뜨는 `predeploy-*.db` 뿐이라, **배포가 없는 주에는 하루도
안 뜬다.**

문서에 적힌 설치 명령은 사람이 손으로 한 번 치는 것이고, 그렇게 친 것은
저장소에 남지 않는다. 서버를 다시 세우면 같이 사라지고, 사라진 것을 아무도
모른다(지금이 그 상태다). 그 크론 스크립트에는 지우는 경로가 실제 데이터
경로와 다른 흠도 있었다 — 아무도 돌려 보지 않았다는 뜻이다.

그래서 **이미지 안**으로 들여왔다. 배포와 같이 따라가므로 서버를 통째로 다시
세워도 `docker compose up` 한 번이면 되살아나고, 호스트에 따로 설치할 것이
없다. 잊을 자리 자체를 없앤다.

**왜 정해진 시각이 아니라 '떴는지 보고 없으면 뜨는' 방식인가.**

새벽 3시에 거는 방식은 그 시각에 컨테이너가 안 떠 있으면 **그날을 조용히
건너뛴다.** 배포·재부팅이 새벽에 겹치면 그렇게 된다. 여기서는 주기적으로 깨어나
`오늘 날짜의 백업이 있는가`만 보고 없으면 뜬다 — 늦게 떠도 그날 것이 남는다.

**멈춘 것을 어떻게 아는가.** 앱이 따로 적어 두는 기록이 아니라 **파일 자체가
증거다.** 가장 새 일일 백업이 하루를 넘겨 낡으면 관리자 화면이 빨갛게 알린다.
기록을 따로 남기는 방식은 그 기록을 남기는 코드가 죽으면 같이 조용해진다.
"""
from __future__ import annotations

import re
import sqlite3
import threading
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

from .. import clock, config

# 스냅샷 파일 이름표. 앞머리로 **성격**을 가른다.
#
# 지우는 대상은 `daily-` 뿐이다. `predeploy-` 는 배포 직전에 서버의 deploy.sh 가
# 뜨는 다른 성격의 백업이라 여기서 건드리지 않는다 — 되돌릴 지점으로는 같이
# 세우되(촘촘할수록 좋다), 정리는 각자의 몫이다.
DAILY_PREFIX = "daily-"
PREDEPLOY_PREFIX = "predeploy-"
BEFORE_RESTORE_PREFIX = "before-restore-"

# 되돌리기 직전에 뜨는 백업. **이것이 있어야 잘못 되돌렸을 때 돌아올 곳이 있다.**
# `daily-` 가 아니므로 정리 대상이 아니다 — 되돌린 날의 원래 상태는 7일 규칙과
# 상관없이 남아야 한다.

# 며칠 치를 남길 것인가. 사용자가 "1주일이면 충분하다" 고 했다.
KEEP_DAILY_DAYS = int(config.BACKUP_KEEP_DAILY_DAYS)

# 얼마나 자주 깨어나 볼 것인가. 30분이면 재부팅이 겹쳐도 그날 안에 뜬다.
CHECK_INTERVAL_SEC = 30 * 60

# 이만큼 지나도록 새 일일 백업이 없으면 화면이 빨개진다.
# 하루 + 여유 2시간 — 컨테이너가 잠깐 내려갔다 온 날에 헛경고가 뜨지 않게.
STALE_AFTER_HOURS = 26

# 뜨는 것과 되돌리는 것이 겹치지 않게 한다. 둘 다 같은 파일을 만진다.
_LOCK = threading.Lock()

# 스케줄러는 프로세스당 하나. `create_app()` 이 여러 번 불려도(테스트) 겹쳐
# 뜨지 않게 한다.
_SCHEDULER: Optional[threading.Thread] = None

# 마지막으로 뜨려다 실패한 사유. 화면에 그대로 보여 준다.
# **이 값이 증거는 아니다** — 프로세스가 다시 뜨면 사라진다. 증거는 파일이고,
# 이것은 "왜 안 떴는지" 를 그 자리에서 알려 주는 덤이다.
_LAST_ERROR: Optional[str] = None


def db_path() -> Path:
    """지금 쓰는 SQLite 파일.

    `config.DEFAULT_DB_PATH` 를 그냥 쓰지 않는 것은 `DATABASE_URL` 이 그 값을
    덮을 수 있기 때문이다(운영 compose 가 실제로 덮는다). 되돌리기가 **엉뚱한
    파일**을 겨누는 것보다 나쁜 사고는 없다 — 실제로 쓰는 주소에서 뽑는다.
    """
    url = config.DATABASE_URL
    if not url.startswith("sqlite"):
        raise BackupError("SQLite 가 아닌 DB 에서는 이 기능을 쓸 수 없습니다")
    return Path(url.split("///")[-1])


def backup_dir() -> Path:
    """백업이 사는 곳 — DB 와 같은 자리(운영에서는 볼륨 안).

    별도 폴더로 나누지 않는 이유: `predeploy-*.db` 가 이미 여기 쌓이고 있고,
    되돌릴 지점 목록은 그것들도 같이 세워야 한다. 자리를 나누면 목록이 두
    곳을 훑어야 하고, 한 곳을 빠뜨리면 있는 지점이 안 보인다.
    """
    return config.DATA_DIR


class BackupError(RuntimeError):
    """사용자에게 그대로 보여 줄 수 있는 실패 사유."""


# --- 뜨기 -------------------------------------------------------------------

def snapshot(dst: Path, src: Optional[Path] = None, timeout: float = 30.0) -> Path:
    """지금 DB 를 `dst` 로 한 덩어리 뜬다. **멈출 필요가 없다.**

    `scripts/db_snapshot.py` 와 **같은 방법**이다(sqlite 백업 API). 파일을
    복사하면 안 되는 이유는 그쪽 문서에 적어 두었다 — WAL 에 있는 최근 쓰기가
    통째로 빠진다.
    """
    src = src or db_path()
    if not src.exists():
        raise BackupError(f"원본이 없습니다: {src}")
    if dst.exists():
        raise BackupError(f"받을 자리에 이미 파일이 있습니다: {dst.name}")

    dst.parent.mkdir(parents=True, exist_ok=True)
    source = sqlite3.connect(f"file:{src}?mode=ro", uri=True, timeout=timeout)
    target = sqlite3.connect(dst, timeout=timeout)
    try:
        source.backup(target)
    finally:
        target.close()
        source.close()
    return dst


def daily_name(day: date) -> str:
    return f"{DAILY_PREFIX}{day:%Y%m%d}.db"


def run_daily(today: date, *, keep_days: int = KEEP_DAILY_DAYS) -> Optional[Path]:
    """오늘 것이 없으면 뜬다. 있으면 아무것도 하지 않는다.

    **하루에 한 번인지를 파일로 판단한다.** 마지막으로 뜬 시각을 어딘가에
    적어 두고 견주면, 그 기록과 실제 파일이 어긋나는 순간(파일만 지워졌다든지)
    영영 안 뜨게 된다.

    `today` 를 받는 것은 검사가 날짜를 못박기 위해서다 — 자정에 결과가 바뀌는
    검사를 만들지 않는다.
    """
    global _LAST_ERROR

    with _LOCK:
        dst = backup_dir() / daily_name(today)
        made = None
        if not dst.exists():
            try:
                made = snapshot(dst)
            except (BackupError, sqlite3.Error, OSError) as exc:
                # 조용히 넘기면 지금과 같은 상태가 된다 — 사유를 남기고,
                # 낡은 파일이 화면을 빨갛게 만들도록 둔다.
                _LAST_ERROR = f"{type(exc).__name__}: {exc}"
                return None
        _LAST_ERROR = None
        prune_daily(today, keep_days=keep_days)
        return made


def prune_daily(today: date, *, keep_days: int = KEEP_DAILY_DAYS) -> list:
    """오래된 **일일** 백업만 지운다.

    지우는 기준을 '파일 개수' 가 아니라 **날짜**로 잡는다. 개수로 자르면 배포가
    잦아 하루에 여러 번 뜬 날(그런 이름은 안 만들지만)이나 이름이 어긋난
    파일이 섞였을 때 남는 기간이 들쭉날쭉해진다. "일주일 전까지" 가 약속이므로
    날짜로 자른다.

    **`predeploy-*` 와 `before-restore-*` 는 건드리지 않는다.** 성격이 다른
    백업이고, 특히 되돌리기 직전 백업은 7일 규칙과 상관없이 남아야 한다.
    """
    cutoff = today - timedelta(days=keep_days - 1)
    removed = []
    for path in sorted(backup_dir().glob(f"{DAILY_PREFIX}*.db")):
        day = _daily_date(path.name)
        if day is None or day >= cutoff:
            continue
        try:
            path.unlink()
            removed.append(path.name)
            # 곁딸린 `-wal`·`-shm` 도 같이 치운다. 스냅샷은 원본의 WAL 모드를
            # 물려받아서, 목록을 그리며 **읽기만 해도** 이 둘이 생긴다. 본체만
            # 지우면 주인 없는 부스러기가 폴더에 영영 쌓인다(목록에는 안 뜨므로
            # 아무도 모른 채).
            for tail in ("-wal", "-shm"):
                sibling = path.with_name(path.name + tail)
                if sibling.exists():
                    sibling.unlink()
        except OSError:
            # 못 지운 것은 넘어간다 — 지우기에 실패했다고 백업을 멈추면
            # 더 나쁘다.
            continue
    return removed


_DAILY_RE = re.compile(rf"^{DAILY_PREFIX}(\d{{8}})\.db$")


def _daily_date(name: str) -> Optional[date]:
    m = _DAILY_RE.match(name)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), "%Y%m%d").date()
    except ValueError:
        return None


# --- 백업이 실제로 돌고 있는가 ------------------------------------------------

@dataclass
class Health:
    """관리자 화면에 그대로 뿌리는 상태."""

    latest: Optional[str]        # 가장 새 일일 백업 파일 이름
    latest_at: Optional[datetime]
    age_hours: Optional[float]
    stale: bool
    count: int                   # 남아 있는 일일 백업 개수
    error: Optional[str]
    detail: str


def health(now: Optional[datetime] = None) -> Health:
    """일일 백업이 돌고 있는가 — 화면이 읽는 한 곳.

    **증거는 파일이다.** 가장 새 일일 백업이 얼마나 낡았는지만 본다. 앱이 따로
    "돌았다" 고 적어 두는 방식은 그 적는 코드가 죽으면 같이 조용해진다.
    """
    now = now or clock.now()
    files = sorted(backup_dir().glob(f"{DAILY_PREFIX}*.db"))
    dated = [(d, f) for f in files if (d := _daily_date(f.name)) is not None]
    if not dated:
        return Health(None, None, None, True, 0, _LAST_ERROR,
                      "일일 백업이 하나도 없습니다")

    day, newest = max(dated, key=lambda pair: pair[0])
    at = datetime.fromtimestamp(newest.stat().st_mtime, tz=now.tzinfo)
    age = (now - at).total_seconds() / 3600
    stale = age > STALE_AFTER_HOURS
    detail = (f"{day:%Y-%m-%d} 백업까지 있습니다 (일일 {len(dated)}개 보관)"
              if not stale else
              f"마지막 일일 백업이 {int(age)}시간 전입니다 — 백업이 멈춘 것 같습니다")
    return Health(newest.name, at, age, stale, len(dated), _LAST_ERROR, detail)


# --- 스케줄러 ---------------------------------------------------------------

def start_scheduler() -> Optional[threading.Thread]:
    """일일 백업 실 하나를 띄운다. 이미 떠 있으면 그대로 둔다.

    별도 프로세스·크론이 아니라 **웹과 같은 프로세스의 실**이다. 웹이 살아
    있으면 백업도 살아 있고, 웹이 죽으면 화면도 같이 안 뜨므로 백업만 조용히
    멈춰 있는 상태가 생기지 않는다 — 지금 서버가 딱 그 상태였다.

    uvicorn 을 여러 일꾼(worker)으로 띄우면 이 실도 여러 개가 된다. 지금은
    한 일꾼이라(`docker-compose.yml` 의 command) 문제가 없고, 여럿이 되더라도
    `오늘 것이 있으면 안 뜬다` 는 규칙과 파일 잠금 덕에 하루 한 개로 수렴한다.
    """
    global _SCHEDULER

    if not config.BACKUP_ENABLED:
        return None
    if _SCHEDULER is not None and _SCHEDULER.is_alive():
        return _SCHEDULER

    def loop() -> None:
        while True:
            try:
                run_daily(clock.now().date())
            except Exception:  # noqa: BLE001 - 백업 실이 죽으면 조용해진다
                pass
            time.sleep(CHECK_INTERVAL_SEC)

    _SCHEDULER = threading.Thread(target=loop, name="daily-backup", daemon=True)
    _SCHEDULER.start()
    return _SCHEDULER


# --- 되돌릴 수 있는 지점 -----------------------------------------------------
#
# 목록에는 **일일 백업뿐 아니라 배포 직전 백업도** 세운다. 성격은 다르지만
# 되돌릴 지점이라는 점에서는 같고, 배포가 잦은 주에는 그쪽이 훨씬 촘촘하다.
# 하나만 보여 주면 "어제 오후" 로 돌아갈 방법이 있는데도 없다고 알게 된다.

KIND_LABELS = {
    DAILY_PREFIX: "일일 자동",
    PREDEPLOY_PREFIX: "배포 직전",
    BEFORE_RESTORE_PREFIX: "되돌리기 직전",
}


@dataclass
class Point:
    """되돌릴 수 있는 한 지점. 화면이 이 값만 읽는다."""

    name: str
    kind: str
    at: datetime
    size: int
    revision: Optional[str]
    verdict: str          # same | behind | ahead | unknown
    safe: bool
    note: str

    @property
    def size_mb(self) -> str:
        return f"{self.size / 1024 / 1024:.1f}MB"


def _kind_of(name: str) -> str:
    for prefix, label in KIND_LABELS.items():
        if name.startswith(prefix):
            return label
    # 사람이 손으로 뜬 것. 이름 규칙이 없으므로 나머지는 전부 여기로 온다.
    return "손으로 뜬 것"


def read_revision(path: Path) -> Optional[str]:
    """그 백업이 어느 알렘빅 판인가. 읽을 수 없으면 None.

    **파일을 열어 확인한다.** 이름이나 날짜로 짐작하면 안 된다 — 옛 이름으로
    새 스키마를 담은 파일이 섞일 수 있다.
    """
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5.0)
    except sqlite3.Error:
        return None
    try:
        row = conn.execute("SELECT version_num FROM alembic_version").fetchone()
        return row[0] if row else None
    except sqlite3.Error:
        return None
    finally:
        conn.close()


def _alembic_config():
    """알렘빅 설정 — **ini 파일을 읽지 않고** 손으로 채운다.

    `Config("alembic.ini")` 로 만들면 `env.py` 가 `fileConfig()` 를 부르고, 그것이
    **돌고 있는 프로세스의 로깅 설정을 갈아엎는다**(기본값이 기존 로거를 끈다).
    되돌리기 한 번에 uvicorn 접속 로그가 조용해지는 식의 곁가지 피해가 난다.
    필요한 두 값만 주면 `config_file_name` 이 None 이라 그 줄을 건너뛴다.
    """
    from alembic.config import Config

    cfg = Config()
    # 상대경로(`script_location = alembic`)는 어디서 부르느냐에 따라 어긋난다.
    cfg.set_main_option("script_location", str(config.BASE_DIR / "alembic"))
    cfg.set_main_option("sqlalchemy.url", config.DATABASE_URL)
    return cfg


def known_revisions() -> tuple:
    """코드가 아는 판 전부와 지금의 머리(head)."""
    from alembic.script import ScriptDirectory

    script = ScriptDirectory.from_config(_alembic_config())
    return {s.revision for s in script.walk_revisions()}, script.get_current_head()


def verdict_for(revision: Optional[str], known: set, head: Optional[str]) -> tuple:
    """이 판으로 되돌려도 되는가 — (판정, 사유).

    **백업이 코드보다 앞서 있으면 되돌리면 안 된다.** 코드가 모르는 판이라는
    것은 그 백업이 더 새 스키마라는 뜻이고, 지금 코드는 그 표를 읽을 줄
    모른다. 알렘빅에는 내리는 길(downgrade)이 있지만 이 저장소의 마이그레이션은
    칸을 지우고 합치는 것이 많아 되돌리면 값이 사라진다 — 목록에서 아예 막는다.

    판이 없는 백업(`alembic_version` 표 자체가 없음)도 막는다. 알렘빅이 돌기
    전의 파일이라 `upgrade head` 가 이미 있는 표를 다시 만들려다 죽는다.
    """
    if revision is None:
        return "unknown", "알렘빅 판을 읽을 수 없습니다 — 되돌릴 수 없습니다"
    if revision == head:
        return "same", "지금 코드와 같은 판입니다"
    if revision in known:
        return "behind", f"옛 판({revision})입니다 — 되돌린 뒤 최신 판으로 올립니다"
    return "ahead", (f"코드가 모르는 판({revision})입니다 — 이 백업이 지금 코드보다 "
                     f"새 것이라 되돌리면 안 됩니다")


SAFE_VERDICTS = ("same", "behind")


def restore_points(limit: int = 60) -> list:
    """되돌릴 수 있는 지점 목록 — 새 것부터.

    지금 쓰는 `dealflow.db` 자체와 그 곁딸린 `-wal`·`-shm` 은 뺀다.
    """
    live = db_path()
    known, head = known_revisions()
    points = []
    for path in backup_dir().glob("*.db"):
        if path.name == live.name:
            continue
        try:
            stat = path.stat()
        except OSError:
            continue
        revision = read_revision(path)
        verdict, note = verdict_for(revision, known, head)
        points.append(Point(
            name=path.name,
            kind=_kind_of(path.name),
            at=datetime.fromtimestamp(stat.st_mtime).astimezone(),
            size=stat.st_size,
            revision=revision,
            verdict=verdict,
            safe=verdict in SAFE_VERDICTS,
            note=note,
        ))
    points.sort(key=lambda p: p.at, reverse=True)
    return points[:limit]


def find_point(name: str) -> Optional[Point]:
    """이름으로 한 지점 찾기.

    **경로를 그대로 믿지 않는다.** 폼으로 오는 값이라 `../` 같은 것이 섞이면
    백업 폴더 밖의 파일을 겨눌 수 있다 — 목록에 실제로 있는 이름만 받는다.
    """
    return next((p for p in restore_points(limit=10_000) if p.name == name), None)


# --- 무엇이 바뀌는가 ---------------------------------------------------------

def counts(path: Path) -> dict:
    """표별 행수. 세는 표 목록은 `scripts/db_snapshot.py` 것을 **그대로 쓴다**.

    옮길 때 사람이 눈으로 세던 표와 화면이 세는 표가 다르면, 같은 백업을 두
    도구로 봤을 때 숫자가 갈린다. 목록이 둘이면 하나는 반드시 낡는다.
    """
    from scripts.db_snapshot import counts as _counts

    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=10.0)
    try:
        return _counts(conn)
    finally:
        conn.close()


def diff(point: Point) -> list:
    """지금과 그 지점의 차이 — 표마다 (이름, 지금, 그때, 증감).

    **날짜만 보고 누르게 하면 안 된다.** 되돌리면 무엇이 몇 개 사라지는지를
    먼저 보여 준다. 오늘 들어온 기업 12곳이 없어진다는 것을 누르기 전에 알아야
    한다.
    """
    now_counts = counts(db_path())
    then_counts = counts(backup_dir() / point.name)
    rows = []
    for table in sorted(set(now_counts) | set(then_counts)):
        now_n = now_counts.get(table)
        then_n = then_counts.get(table)
        rows.append({
            "table": table,
            "label": TABLE_LABELS.get(table, table),
            "now": now_n,
            "then": then_n,
            # 되돌리면 이만큼 바뀐다. 음수는 사라진다는 뜻이다.
            "delta": (then_n or 0) - (now_n or 0),
        })
    return rows


# 표 이름을 사람 말로. 화면에 `ir_companies` 라고 떠 있으면 무엇이 사라지는지
# 읽어 낼 수 없다 — 되돌릴지 말지를 이 숫자로 판단하므로 읽혀야 한다.
TABLE_LABELS = {
    "users": "계정",
    "vc_contacts": "투자사 담당자",
    "ir_companies": "IR 기업",
    "sourcing_contacts": "딜 소싱 명단",
    "message_templates": "딜 제안 문구",
    "send_jobs": "발송 회차",
    "send_items": "발송 건",
    "contact_activities": "담당자 활동 기록",
    "ir_requests": "IR 요청",
    "meetings": "미팅",
    "consulting_companies": "투자컨설턴트 기업",
    "ref_sheets": "참고 자료",
}


# --- 발송 중에는 되돌리지 않는다 ---------------------------------------------

#: 이 상태의 회차가 있으면 되돌리지 않는다.
#:
#: 회차 중간에 DB 가 통째로 옛 것으로 바뀌면 **어디까지 나갔는지 기록이
#: 어긋난다.** 이미 카톡을 받은 사람이 '아직 안 보냄' 으로 돌아가고, 에이전트가
#: 남은 건을 가져가면서 그 사람에게 **또 보낸다.** 받는 쪽은 투자사다.
ACTIVE_SEND_STATUSES = ("queued", "running")


def sending_now(db) -> list:
    """지금 돌고 있는 발송 회차. 비어 있어야 되돌릴 수 있다."""
    from sqlalchemy import select

    from ..models import SendJob

    return list(db.execute(
        select(SendJob).where(SendJob.status.in_(ACTIVE_SEND_STATUSES))
        .order_by(SendJob.id)
    ).scalars().all())


# --- 되돌리기 ---------------------------------------------------------------

def restore(point: Point, *, now: Optional[datetime] = None,
            busy_timeout: float = 10.0) -> dict:
    """그 지점으로 되돌린다. **앱을 세우지 않는다.**

    왜 파일을 바꿔치지 않는가
    -------------------------
    컨테이너 안에서 `dealflow.db` 를 옛 파일로 덮으면 두 가지가 터진다. 하나는
    이미 열려 있는 연결이 **옛 파일을 붙들고** 있어서 화면이 한동안 바뀌기 전
    내용을 계속 보여 준다는 것이고, 다른 하나가 더 나쁘다 — 곁에 남은
    `dealflow.db-wal` 이 **새로 놓인 파일에 적용되면서** 서로 다른 시점의
    페이지가 섞인다. 열리지 않는 DB 가 된다.

    그래서 파일이 아니라 **sqlite 백업 API 로 안쪽 내용을 덮는다.** 뜰 때 쓰는
    것과 같은 길을 거꾸로 쓰는 것뿐이다(`scripts/db_snapshot.py`). SQLite 가
    직접 쓰므로 WAL 도 알아서 정리되고, 열려 있던 연결은 다음 질의부터 새
    내용을 본다 — 실제로 그렇게 되는 것을 확인했다.

    왜 그래도 연결 뭉치를 버리는가
    ------------------------------
    **쓰기 트랜잭션이 열려 있으면 이 덮어쓰기가 무한정 기다린다**(직접 재
    보았다. 읽기 트랜잭션은 막지 않는다). 되돌리기 요청 하나가 영영 안 끝나는
    것보다는, 놀고 있는 연결을 미리 버려 그럴 확률을 줄이고 그래도 걸리면
    **정해진 시간 안에 실패로 알려 주는** 편이 낫다.
    """
    from ..db import engine

    now = now or clock.now()
    if not point.safe:
        raise BackupError(point.note)

    src = backup_dir() / point.name
    if not src.exists():
        raise BackupError(f"백업 파일이 없습니다: {point.name}")

    with _LOCK:
        # 1) **되돌리기 전에 지금 상태를 먼저 뜬다.** 잘못 되돌렸을 때 돌아올
        #    곳이 없으면 되돌리기는 그 자체가 사고다.
        safety = backup_dir() / f"{BEFORE_RESTORE_PREFIX}{now:%Y%m%d-%H%M%S}.db"
        snapshot(safety)

        # 2) 놀고 있는 연결을 버린다(위 설명).
        engine.dispose()

        # 3) 안쪽 내용을 덮는다.
        source = sqlite3.connect(f"file:{src}?mode=ro", uri=True, timeout=busy_timeout)
        target = sqlite3.connect(db_path(), timeout=busy_timeout)
        try:
            source.backup(target)
        except sqlite3.OperationalError as exc:
            raise BackupError(
                "다른 작업이 DB 에 쓰고 있어 되돌리지 못했습니다. "
                f"잠시 뒤 다시 해 주세요 ({exc})") from exc
        finally:
            target.close()
            source.close()

        # 4) 옛 판이면 최신으로 올린다. 안 올리면 코드가 없는 칸을 찾는다.
        migrated = None
        if point.verdict == "behind":
            engine.dispose()
            from alembic import command

            command.upgrade(_alembic_config(), "head")
            migrated = read_revision(db_path())

        # 5) 마이그레이션이 열었던 연결까지 버린다 — 스키마가 바뀌었다.
        engine.dispose()

    return {
        "restored": point.name,
        "safety": safety.name,
        "revision": point.revision,
        "migrated_to": migrated,
    }


# --- 되돌리면 로그인은 어떻게 되는가 ------------------------------------------
#
# 로그인 세션은 **DB 안에 있다**(`sessions` 표). 그러니 되돌리는 순간 지금 쓰고
# 있는 세션도 그 시점 것으로 바뀐다 — 대개 없어지고, 누른 사람은 로그인 화면으로
# 튕긴다. 그것만이면 다시 들어오면 그만이다.
#
# **문제는 계정 자체가 그 백업에 없을 때다.** 지난주 백업으로 되돌리는데 내
# 관리자 계정이 이번 주에 만들어진 것이라면, 되돌린 뒤 나는 **다시 들어올 수
# 없다.** 남은 관리자가 없으면 아무도 되돌릴 수 없다 — 서버에 직접 붙어야
# 풀린다. 누르기 전에 알아야 하는 종류의 일이다.

@dataclass
class LoginRisk:
    me: bool          # 내 계정이 그 백업에 살아 있는가
    admins: int       # 그 백업에 남아 있는 활성 관리자 수
    warning: str      # 비어 있으면 문제 없음


def login_risk(point: "Point", phone: str) -> LoginRisk:
    """되돌린 뒤 다시 들어올 수 있는가."""
    path = backup_dir() / point.name
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5.0)
    except sqlite3.Error:
        return LoginRisk(True, 0, "")
    try:
        me = conn.execute(
            "SELECT COUNT(*) FROM users WHERE phone=? AND role='admin' AND is_active=1",
            (phone,)).fetchone()[0] > 0
        admins = conn.execute(
            "SELECT COUNT(*) FROM users WHERE role='admin' AND is_active=1"
        ).fetchone()[0]
    except sqlite3.Error:
        return LoginRisk(True, 0, "")
    finally:
        conn.close()

    if not admins:
        warning = ("이 백업에는 **관리자 계정이 하나도 없습니다.** 되돌리면 아무도 "
                   "관리자 화면에 들어올 수 없고, 서버에 직접 붙어야 풀립니다.")
    elif not me:
        warning = ("이 백업에는 **지금 로그인한 계정이 없습니다.** 되돌리면 이 "
                   f"계정으로는 다시 들어올 수 없습니다(그 시점의 관리자 {admins}명은 "
                   "들어올 수 있습니다).")
    else:
        warning = ""
    return LoginRisk(me, admins, warning)
