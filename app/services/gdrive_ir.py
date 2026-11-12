"""구글 드라이브에 올라온 IR 자료 → IR 기업 현황 `IR 자료 수신` 칸에 저절로 (#155).

팀원 요청: "구글드라이브 IR 올려진 확인해서 그룹웨어에 IR 수신된거로 자동으로
기입되게". 사람도 Claude 도 없이 **서버가 혼자** 돈다(팀 원칙 '완전 자동 기본').

## 무엇을 하나

  1. 구글 **서비스 계정**(읽기 전용 `drive.readonly`)으로 IR 자료가 올라오는 폴더를
     읽는다. 하위 폴더까지 본다(판에서 끌 수 있다).
  2. 지난번 확인 뒤 **새로 생기거나 바뀐 파일**만 묻는다 —
     `modifiedTime > T or createdTime > T`. 둘 다 보는 까닭: 드라이브에 올린 파일은
     PC 의 수정 시각을 그대로 들고 와 `modifiedTime` 이 올린 시각보다 **이르다**
     (실제 폴더에서 확인했다). `createdTime` 만 올린 시각이다.
  3. **PDF · PPT 만**(pdf · ppt · pptx · key, 구글 슬라이드 — `is_deck`) 본다. 그 밖의
     파일은 `건너뜀 (파일 종류)` 으로 기록만 하고 확인 필요에도 안 올린다.
  4. 파일 이름에서 기업명을 찾아(`Index`) **기업이 정확히 하나일 때만** 그 기업의 줄에
     추가 칸 `IR 자료 수신` 을 `2026/11/04 수신완료 (드라이브: 파일이름)` 으로 적는다.
     두 탭은 이 추가 칸을 같은 이름의 고정 칸 안, 파일 이름 아래에 그린다(i239 —
     `custom_columns.absorb`). 적는 자리는 그대로 이 추가 칸이다.
     IR 기업 현황 줄과 그 기업으로 판정된 Series A 줄 — **두 탭 모두**. 날짜는 드라이브에
     그 파일이 생긴 날(한국 시각)이다.
  5. 0곳 · 여러 곳이면 적지 않고 **확인 필요** 목록에 남긴다(팀 현황 판에 보인다).

## 적지 않는 것

  · **파일 이름(`ir_file_name` — `IR 자료 수신` 칸 윗줄, 옛 `IR 자료`)에는 쓰지 않는다.** 그 칸이 차 있으면 딜 소개 때
    발송 PC 가 같은 이름의 **로컬 파일**을 찾아 붙인다(`agent/sender/base.py`
    `check_ir_file_name` 근처) — 드라이브에만 있는 파일이면 첨부가 실패한다.
  · **값이 있는 칸은 덮지 않는다** — 줄마다 따로 본다. 사람이 적었을 수 있다. 같은 기업에 파일이 또
    오면(새 판 · 같은 자료 사본) **건너뛰고 기록만** 남긴다 — 이 칸이 답하는 물음은
    "IR 을 받았나 · 처음 언제" 이고, 두 번째 파일로 첫 수신일을 지우면 그 답이 틀린다.
    덧붙이면 판마다 한 줄씩 쌓여 칸이 읽히지 않는다. 건너뛴 것은 판의 `최근 처리` 에 선다.
  · 드라이브에는 **읽기만** 한다. 쓰는 곳은 앱 DB 하나다.

## 언제 도나 — 자동화 실을 같이 쓴다

새 실을 띄우지 않는다. 2단계 자동화 실(`automation_runner.start_scheduler`, 5분마다)이
한 바퀴 끝에 `tick` 을 부르고, 여기서 **간격(기본 30분)** 이 찼는지만 본다. 보내는
일이 아니라 회차 틀(`run_all` — 보내는 계정 · 시험방 · 예약)에는 달지 않는다.

  · **스위치** — 팀 현황 › 자동화 아래 이 판(관리자). 기본은 꺼짐. 값은 `automations`
    표의 **예약 줄** `_gdrive_ir`(켜짐 · 간격 · 하위 폴더 · 처음 확인 때 이미 있던 파일도
    적기 · 켠 관리자)에 둔다 — `_team` 줄과 같은 방식이라 DB 구조를 바꾸지 않는다.
  · **상태** — 같은 표의 예약 줄 `_gdrive_ir_state` 의 `params`(JSON): 마지막 확인 ·
    본 파일(id → 수정 시각 · 이름 · 결과) · 폴더 트리 · 확인 필요 · 최근 처리. 실만 적고
    관리자 화면은 읽기만 한다 — 스위치 줄과 나눠 두어 서로의 저장이 덮이지 않는다.
  · **설정이 없으면 조용히 꺼져 있다** — 키 파일(`DEALFLOW_GDRIVE_SA_FILE`) · 폴더
    (`DEALFLOW_GDRIVE_FOLDER_ID`, 쉼표로 여럿)가 없으면 아무것도 안 하고 판에 그렇게
    적는다. 사용자 준비는 `docs/GDRIVE_IR.md`.

## 호출을 아낀다 (돈 드는 서비스 없음)

Drive API 읽기와 서비스 계정만 쓴다(푸시 알림 · Cloud Functions 등 없음).

  · 평소 한 회차 = 알고 있는 폴더 전부를 **한 질의**(`'a' in parents or 'b' in parents …`,
    20개씩)로, 바뀐 것만, 필요한 칸만(`FIELDS`) 묻는다. 폴더 트리는 **기억해 두고**
    회차마다 다시 훑지 않는다 — 새로 보인 하위 폴더만 그 안을 읽는다.
  · **하루 한 번 전체 대조** — 폴더 트리를 다시 훑고 목록 전체를 본 파일과 맞춘다.
    시각 필터가 못 잡는 것(다른 곳에서 옮겨 온 파일 · 이름만 바꾼 파일)을 여기서 줍고,
    지워진 파일을 상태에서 걷는다.
  · 기본값(30분 · 폴더 몇 개)이면 하루 Drive API 호출이 50건 남짓이다(문서에 셈).

## 안전

  · 키 파일 내용과 토큰은 로그 · 화면 · 오류 글에 싣지 않는다. 밖에 나가는 실패 사유는
    정해 둔 말(`ERR_*`)뿐이고, 안쪽 예외는 끊어(`from None`) 버린다.
  · 드라이브가 실패하면(권한 · 할당량 · 네트워크) 사유를 판에 적고 **다음 회차에 다시**
    한다. 앱은 멈추지 않는다(`tick` 을 부르는 실이 예외를 삼킨다).
  · 수정 기록은 `자동` 주체로 남는다(`edit_log.AUTO_METHOD` — 계정 칸은 켠 관리자).
"""
from __future__ import annotations

import logging
import os
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Sequence, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import clock
from ..models import Automation, CustomColumnValue, IrCompany, SeriesACompany, User
from . import automation, custom_columns, edit_log
from .deal_history import _key as raw_key
from .sheet_import import normalize_company_name

log = logging.getLogger(__name__)

# ── 설정 이름 ────────────────────────────────────────────────────────────────

ENV_SA_FILE = "DEALFLOW_GDRIVE_SA_FILE"
ENV_FOLDERS = "DEALFLOW_GDRIVE_FOLDER_ID"

#: `automations` 표의 예약 줄 — `automation.KINDS` 에 없는 열쇠라 자동화 저장 길
#: (`automation.save`)은 못 건드린다(`automation.TEAM_KEY` 와 같은 방식).
KEY = "_gdrive_ir"
STATE_KEY = "_gdrive_ir_state"

LABEL = "구글 드라이브 IR 수신 확인"
#: 적는 칸 — IR 기업 현황 · Series A 두 탭이 같이 쓰는 추가 칸(`custom_columns.TARGETS`).
COLUMN = custom_columns.IR_RECEIVED
#: 칸이 없어 새로 만들 때 설 자리(그 머리글 바로 뒤). 두 탭은 이 칸을 같은 이름의 고정 칸
#: 안에 그려(i239) 화면에서는 안 쓰이지만, `custom_columns.place` 가 받는 자리여야 한다.
AFTER = custom_columns.IR_RECEIVED
TARGET = "companies"
#: 수정 기록에 남는 주소 — 사람이 누른 길이 아니라 이 판의 자동화다.
LOG_PATH = "/team#gdrive-ir"

DEFAULT_INTERVAL_MIN = 30
MIN_INTERVAL_MIN = 10
MAX_INTERVAL_MIN = 24 * 60
#: 전체 대조(폴더 트리 다시 훑기 + 목록 전체) 사이.
FULL_EVERY = timedelta(hours=24)
#: 바뀐 것만 물을 때 기준 시각을 이만큼 앞당긴다 — 드라이브 검색 색인이 몇 초~몇 분
#: 늦게 따라온다. 겹쳐 온 파일은 본 파일 목록이 거른다.
OVERLAP = timedelta(minutes=10)

MAX_REVIEW = 200
MAX_RECENT = 30
MAX_FOLDERS = 300
#: 한 질의에 넣는 폴더 수 — 질의 글자 길이를 짧게 둔다.
CHUNK = 20
PAGE_SIZE = 1000
MAX_PAGES = 20
TIMEOUT_SEC = 30

KST = timezone(timedelta(hours=9), "KST")

SCOPE = "https://www.googleapis.com/auth/drive.readonly"
FILES_URL = "https://www.googleapis.com/drive/v3/files"
FOLDER_MIME = "application/vnd.google-apps.folder"
SHORTCUT_MIME = "application/vnd.google-apps.shortcut"
#: 받는 칸 — 이것만 묻는다(응답이 작다).
FIELDS = ("nextPageToken,incompleteSearch,"
          "files(id,name,mimeType,createdTime,modifiedTime,parents,webViewLink)")

#: 폴더 id 꼴. 질의 글자(`'…' in parents`)에 들어가므로 이 꼴만 받는다.
_ID = re.compile(r"[A-Za-z0-9_-]{10,128}")
#: 폴더 주소를 통째로 붙여 넣어도 id 를 꺼낸다.
_FOLDER_URL = re.compile(r"/folders/([A-Za-z0-9_-]{10,128})")

#: 적는 파일 종류 — **PDF · PPT 만**(11/04 사용자 결정). 확장자나 mimeType 하나만 맞으면 된다.
#: 구글 슬라이드(`…google-apps.presentation`)도 든다 — PPT 와 같은 발표 자료인데 확장자가
#: 없어 mimeType 으로만 알아본다. 빼면 슬라이드로 받은 IR 이 '파일 종류' 로 빠진다.
DECK_EXTENSIONS = frozenset({"pdf", "ppt", "pptx", "key"})
DECK_MIMES = frozenset({
    "application/pdf",
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/vnd.apple.keynote", "application/x-iwork-keynote-sffkey",
    "application/vnd.google-apps.presentation",
})

# 결과
WRITTEN = "written"     # 적음
REVIEW = "review"       # 확인 필요
SKIPPED = "skipped"     # 값이 있어 건너뜀
KIND = "kind"           # PDF · PPT 가 아니라 건너뜀(확인 필요에 안 올린다)
BASELINE = "baseline"   # 처음 확인 때 이미 있던 파일(적지 않기로 했을 때)
RESULT_LABELS = {WRITTEN: "적음", REVIEW: "확인 필요", SKIPPED: "건너뜀 (이미 값 있음)",
                 KIND: "건너뜀 (파일 종류)", BASELINE: "처음부터 있던 파일"}
#: 파일이 바뀌면(이름 · 판) 다시 보는 결과 — 나머지는 끝난 것이다.
RETRY = (REVIEW, KIND)

# 밖에 보이는 실패 사유 — **정해 둔 말뿐이다**(응답 원문 · 예외 글을 싣지 않는다).
ERR_LIB = "구글 인증 라이브러리(google-auth)가 설치되어 있지 않습니다"
ERR_KEY = "키 파일을 읽지 못했습니다 (경로 · JSON 형식 확인)"
ERR_AUTH = "인증 실패 — 키가 지워졌거나 바뀌었습니다 (새 키 확인)"
ERR_DENIED = "권한 없음 — 폴더를 서비스 계정에 '보기'로 공유했는지 확인"
ERR_NOT_FOUND = "폴더를 찾지 못했습니다 — 폴더 id 와 서비스 계정 공유 확인"
ERR_NOT_FOLDER = "폴더가 아닙니다 — 폴더 id 를 확인하세요"
ERR_API_OFF = "Drive API 가 꺼져 있습니다 — 구글 클라우드 콘솔에서 Drive API 사용 설정"
ERR_QUOTA = "할당량 초과 — 다음 회차에 다시 합니다"
ERR_NET = "네트워크 오류 — 다음 회차에 다시 합니다"
ERR_SERVER = "구글 드라이브 서버 오류 — 다음 회차에 다시 합니다"
ERR_REPLY = "드라이브 응답을 읽지 못했습니다 — 다음 회차에 다시 합니다"
ERR_COLUMN_KIND = f"'{COLUMN}' 칸이 메모(글) 형식이 아닙니다 — 컬럼 관리에서 확인"
ERR_COLUMN_HIDDEN = f"'{COLUMN}' 칸이 숨겨져 있습니다 — 컬럼 관리에서 다시 보이게 하세요"
ERR_NO_ACTOR = "수정 기록을 남길 관리자 계정이 없습니다"
ERR_INTERNAL = "처리하다 오류가 났습니다 — 다음 회차에 다시 합니다(서버 로그 확인)"


# ── 서버 설정(환경변수) ───────────────────────────────────────────────────────

@dataclass(frozen=True)
class Config:
    sa_file: str = ""
    folders: Tuple[str, ...] = ()
    #: 꼴이 맞지 않아 버린 폴더 값 수 — 판에 적는다.
    bad_folders: int = 0

    @property
    def key_state(self) -> str:
        """`unset`(환경변수 없음) · `missing`(그 경로에 파일 없음) · `ok`."""
        if not self.sa_file:
            return "unset"
        return "ok" if os.path.isfile(self.sa_file) else "missing"

    @property
    def ready(self) -> bool:
        return self.key_state == "ok" and bool(self.folders)


def folder_ids(raw: str) -> Tuple[Tuple[str, ...], int]:
    """`DEALFLOW_GDRIVE_FOLDER_ID` → (폴더 id 들, 버린 수). 쉼표 · 띄어쓰기로 여럿."""
    ids: List[str] = []
    bad = 0
    for part in re.split(r"[,\s]+", raw or ""):
        if not part:
            continue
        found = _FOLDER_URL.search(part)
        value = found.group(1) if found else part
        if not _ID.fullmatch(value):
            bad += 1
        elif value not in ids:
            ids.append(value)
    return tuple(ids), bad


def config() -> Config:
    """서버 환경변수. 부를 때마다 읽는다(검사가 바꿔 끼울 수 있게)."""
    ids, bad = folder_ids(os.environ.get(ENV_FOLDERS, ""))
    return Config(sa_file=os.environ.get(ENV_SA_FILE, "").strip(), folders=ids,
                  bad_folders=bad)


# ── 판의 스위치 · 값 ─────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Settings:
    enabled: bool = False
    interval_min: int = DEFAULT_INTERVAL_MIN
    subfolders: bool = True
    #: 처음 확인 때 폴더에 이미 있던 파일도 적나. 끄면 그 파일들은 본 것으로만 둔다.
    backfill: bool = True
    #: 수정 기록의 계정 칸 — 마지막으로 이 판을 저장한 관리자.
    actor_id: Optional[int] = None


def _interval(raw) -> int:
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        raise ValueError("확인 간격 — 분 단위 숫자를 넣으세요") from None
    if not MIN_INTERVAL_MIN <= value <= MAX_INTERVAL_MIN:
        raise ValueError(f"확인 간격은 {MIN_INTERVAL_MIN}~{MAX_INTERVAL_MIN}분 사이로 넣으세요")
    return value


def settings(db: Session) -> Settings:
    row = automation.load(db, KEY)
    vals = automation.params(row)
    try:
        interval = _interval(vals.get("interval_min", DEFAULT_INTERVAL_MIN))
    except ValueError:
        interval = DEFAULT_INTERVAL_MIN
    return Settings(enabled=automation.is_on(row), interval_min=interval,
                    subfolders=bool(vals.get("subfolders", True)),
                    backfill=bool(vals.get("backfill", True)),
                    actor_id=row.user_id if row is not None else None)


def save_settings(db: Session, *, enabled: bool, interval_min, subfolders: bool,
                  backfill: bool, user_id: int) -> Settings:
    """판을 저장한다. 못 받을 값이면 `ValueError`(아무것도 안 바뀐다). 커밋까지 한다.

    키가 아직 없어도 켤 수 있다 — 켜 두면 서버에 키를 넣는 순간부터 돈다.
    """
    interval = _interval(interval_min)
    row = automation.load(db, KEY)
    if row is None:
        row = Automation(key=KEY, enabled=0, test_mode=1)
        db.add(row)
    row.enabled = 1 if enabled else 0
    row.user_id = user_id
    automation.set_params(row, {"interval_min": interval, "subfolders": bool(subfolders),
                                "backfill": bool(backfill)})
    db.commit()
    return settings(db)


# ── 상태 ────────────────────────────────────────────────────────────────────

def load_state(db: Session) -> dict:
    return automation.params(automation.load(db, STATE_KEY))


def _save_state(db: Session, state: dict) -> None:
    row = automation.load(db, STATE_KEY)
    if row is None:
        row = Automation(key=STATE_KEY, enabled=0, test_mode=1)
        db.add(row)
    automation.set_params(row, state)


def _parse(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        when = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return when if when.tzinfo else when.replace(tzinfo=timezone.utc)


def _iso(when: datetime) -> str:
    return when.isoformat(timespec="seconds")


def due(state: dict, st: Settings, now: datetime) -> bool:
    last = _parse(state.get("last_run_at"))
    return last is None or now - last >= timedelta(minutes=st.interval_min)


# ── 드라이브 읽기 ────────────────────────────────────────────────────────────

class DriveError(Exception):
    """드라이브를 못 읽었다. `public` 은 판 · 로그에 그대로 싣는 정해 둔 말이다."""

    def __init__(self, public: str):
        super().__init__(public)
        self.public = public


def _reason(resp) -> str:
    """HTTP 응답 → 정해 둔 말. 응답 본문은 까닭(`reason`) 낱말만 본다."""
    code = getattr(resp, "status_code", 0)
    reasons = set()
    try:
        body = resp.json()
        err = body.get("error") if isinstance(body, dict) else None
        if isinstance(err, dict):
            for item in err.get("errors") or []:
                if isinstance(item, dict):
                    reasons.add(str(item.get("reason", "")))
            for item in err.get("details") or []:
                if isinstance(item, dict):
                    reasons.add(str(item.get("reason", "")))
    except Exception:  # noqa: BLE001 - 본문이 JSON 이 아니어도 코드로 가른다
        pass
    if code == 401:
        return ERR_AUTH
    if code == 429 or reasons & {"rateLimitExceeded", "userRateLimitExceeded",
                                 "quotaExceeded", "dailyLimitExceeded",
                                 "RATE_LIMIT_EXCEEDED"}:
        return ERR_QUOTA
    if reasons & {"accessNotConfigured", "SERVICE_DISABLED"}:
        return ERR_API_OFF
    if code == 403:
        return ERR_DENIED
    if code == 404:
        return ERR_NOT_FOUND
    if code >= 500:
        return ERR_SERVER
    return f"드라이브 응답 {code} — 다음 회차에 다시 합니다"


def query(parents: Sequence[str], since: Optional[datetime] = None,
          files_only: bool = False) -> str:
    """`files.list` 의 `q` — 이 폴더들 바로 밑, 휴지통 아닌 것, (있으면) 그 뒤에 생기거나 바뀐 것."""
    ids = [p for p in parents if _ID.fullmatch(p)]
    if not ids:
        raise ValueError("폴더가 없습니다")
    q = "(" + " or ".join(f"'{p}' in parents" for p in ids) + ") and trashed = false"
    if files_only:
        q += f" and mimeType != '{FOLDER_MIME}'"
    if since is not None:
        stamp = since.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        q += f" and (modifiedTime > '{stamp}' or createdTime > '{stamp}')"
    return q


class Drive:
    """드라이브 읽기 두 가지 — 폴더 하나(`folder`) · 폴더들 바로 밑(`children`).

    `session` 은 검사가 끼워 넣는 자리다. 비면 키 파일로 `AuthorizedSession` 을 연다
    (토큰은 그 안에 있고 한 시간 동안 다시 쓴다 — 아래 `_drive` 가 객체를 기억한다).
    공유 드라이브 안 폴더도 읽게 `supportsAllDrives` · `includeItemsFromAllDrives` 를 단다.
    """

    def __init__(self, sa_file: str = "", session=None):
        self._sa_file = sa_file
        self._session = session
        #: 드라이브가 '다 못 찾았을 수 있다'고 했거나 쪽 수 상한에 닿았다.
        self.incomplete = False

    def _http(self):
        if self._session is None:
            try:
                from google.auth.transport.requests import AuthorizedSession
                from google.oauth2 import service_account
            except ImportError:
                raise DriveError(ERR_LIB) from None
            try:
                creds = service_account.Credentials.from_service_account_file(
                    self._sa_file, scopes=[SCOPE])
            except Exception:  # noqa: BLE001 - 어떤 까닭이든 키 내용을 싣지 않는다
                raise DriveError(ERR_KEY) from None
            self._session = AuthorizedSession(creds)
        return self._session

    def _get(self, url: str, params: dict) -> dict:
        session = self._http()
        try:
            resp = session.get(url, params=params, timeout=TIMEOUT_SEC)
        except Exception as exc:  # noqa: BLE001 - 바깥 글은 정해 둔 말만
            raise DriveError(_transport_reason(exc)) from None
        if getattr(resp, "status_code", 0) != 200:
            raise DriveError(_reason(resp))
        try:
            data = resp.json()
        except Exception:  # noqa: BLE001
            raise DriveError(ERR_REPLY) from None
        if not isinstance(data, dict):
            raise DriveError(ERR_REPLY)
        return data

    def folder(self, folder_id: str) -> dict:
        return self._get(f"{FILES_URL}/{folder_id}",
                         {"fields": "id,name,mimeType,trashed", "supportsAllDrives": "true"})

    def children(self, parents: Sequence[str], *, since: Optional[datetime] = None,
                 files_only: bool = False) -> List[dict]:
        out: List[dict] = []
        parents = list(parents)
        for start in range(0, len(parents), CHUNK):
            params = {"q": query(parents[start:start + CHUNK], since, files_only),
                      "fields": FIELDS, "pageSize": PAGE_SIZE, "corpora": "allDrives",
                      "supportsAllDrives": "true", "includeItemsFromAllDrives": "true"}
            for _page in range(MAX_PAGES):
                data = self._get(FILES_URL, params)
                out.extend(f for f in data.get("files") or [] if isinstance(f, dict))
                if data.get("incompleteSearch"):
                    self.incomplete = True
                token = data.get("nextPageToken")
                if not token:
                    break
                params = dict(params, pageToken=token)
            else:
                self.incomplete = True
        return out


def _transport_reason(exc: Exception) -> str:
    try:
        from google.auth import exceptions as gauth
        if isinstance(exc, gauth.RefreshError):
            return ERR_AUTH
        if isinstance(exc, gauth.TransportError):
            return ERR_NET
    except ImportError:  # pragma: no cover
        pass
    import requests

    if isinstance(exc, requests.RequestException):
        return ERR_NET
    return ERR_NET if isinstance(exc, OSError) else ERR_REPLY


#: 키 파일이 같으면 열어 둔 연결(토큰)을 다시 쓴다 — 회차마다 토큰을 새로 받지 않게.
_CACHED: Dict[str, object] = {}


def _drive(sa_file: str) -> Drive:
    try:
        stamp = f"{sa_file}:{os.path.getmtime(sa_file)}"
    except OSError:
        stamp = sa_file
    if _CACHED.get("stamp") != stamp:
        _CACHED.clear()
        _CACHED.update(stamp=stamp, drive=Drive(sa_file))
    drive = _CACHED["drive"]
    drive.incomplete = False
    return drive


# ── 기업 이름 맞추기 ─────────────────────────────────────────────────────────

#: 낱말 조각 — 한글 · 영문 · 숫자 덩어리. 그 밖의 글자(`_` `-` `.` `★` 괄호 …)는 가른다.
_TOKEN = re.compile(r"[가-힣]+|[a-z]+|[0-9]+")
#: 이름 끝에 붙은 괄호 덩어리 — 꼬리표(`[딜소개 불가/…]` · `(26년 3월 폐업함)`)와 메모.
_BRACKETS = re.compile(r"\[[^\]]*\]|\([^)]*\)|【[^】]*】|（[^）]*）|<[^>]*>")
#: 한글 이름 끝에 붙어 쓰이는 자료 이름 — 떼어 낸 조각도 맞춰 본다(`샘플가투자제안서`).
_TAILS = ("회사소개서", "사업계획서", "투자제안서", "사업소개서", "발표자료", "회사소개",
          "소개서", "제안서", "계획서", "투자용", "최종본", "수정본", "자료", "최종")
#: 기업 이름이 이 낱말 하나뿐이면 맞추지 않는다 — 파일 이름에 늘 나오는 말이다.
_NOISE = frozenset({"ir", "deck", "irdeck", "pdf", "ppt", "pptx", "doc", "docx", "hwp",
                    "key", "final", "ver", "rev", "talkfile", "자료", "투자", "투자용",
                    "회사소개서", "소개서", "제안서", "최종", "수정"})
#: 이어 붙여 볼 조각 수 상한.
MAX_SPAN = 6


def _tokens(text: str) -> List[str]:
    text = unicodedata.normalize("NFC", text or "")
    return _TOKEN.findall(normalize_company_name(text).lower())


def name_key(name: Optional[str]) -> str:
    """기업 이름 → 맞출 열쇠. 법인 표기 · 괄호 꼬리표 · 띄어쓰기 · 대소문자 · 자모 꼴을 지운다.

    맞추지 않을 이름(한 글자 · 숫자뿐 · 늘 나오는 낱말)이면 빈 글자.
    """
    text = unicodedata.normalize("NFC", name or "")
    text = _BRACKETS.sub(" ", normalize_company_name(text))
    key = "".join(_TOKEN.findall(text.lower()))
    if len(key) < 2 or key.isdigit() or key in _NOISE:
        return ""
    return key


def file_tokens(file_name: str) -> List[str]:
    """파일 이름 → 조각. 한글 조각 끝의 자료 이름은 떼어 따로 둔다(다시 이어 붙여도 맞는다)."""
    out: List[str] = []
    for tok in _tokens(file_name):
        for tail in _TAILS:
            if tok != tail and tok.endswith(tail) and len(tok) - len(tail) >= 2:
                out.extend([tok[:-len(tail)], tail])
                break
        else:
            out.append(tok)
    return out


@dataclass
class Company:
    """적을 기업 하나 — `rows` 가 그 기업의 줄 전부(IR 줄 먼저, 이어서 Series A 줄들).

    IR 기업 현황과 Series A 이상 딜 소싱 **두 탭 모두에** 같은 글을 적는다(11/04 사용자
    결정). 덮지 않는 규칙은 줄마다 따로다.
    """

    ident: tuple
    label: str
    rows: List[object] = field(default_factory=list)


class Index:
    """IR 기업 현황 + Series A 이상 딜 소싱 기업 — `{열쇠: {기업: Company}}`.

    같은 기업은 하나로 센다.
      · IR 줄 하나 = 기업 하나.
      · Series A 줄은 이어진 IR(`ir_company_id`)이나 **같은 이름**(`deal_history._key`)의
        IR 이 있으면 그 IR 기업이다(`pipeline.series_a_rows` 와 같은 규칙 — IR 이 먼저).
        없으면 같은 이름 줄끼리 한 기업(받은 딜마다 줄이 선다).
      · 적는 줄은 그 기업의 줄 전부 — IR 줄과 그 기업으로 판정된 Series A 줄들.
    꼬리표를 뗀 열쇠가 겹치는 다른 기업(`샘플가` · `샘플가 [딜소개 불가/폐업]`)은 **여럿**이다.
    """

    def __init__(self) -> None:
        self.by_key: Dict[str, Dict[tuple, Company]] = {}

    def _add(self, key: str, company: Company) -> None:
        if key:
            self.by_key.setdefault(key, {}).setdefault(company.ident, company)

    @classmethod
    def build(cls, db: Session) -> "Index":
        index = cls()
        ir = db.execute(select(IrCompany).order_by(IrCompany.id)).scalars().all()
        by_id = {}
        by_raw: Dict[str, Company] = {}
        for c in ir:
            company = Company(("ir", c.id), c.name or "", [c])
            by_id[c.id] = company
            by_raw.setdefault(raw_key(c.name), company)
            index._add(name_key(c.name), company)
        sa_groups: Dict[str, Company] = {}
        for r in db.execute(select(SeriesACompany).order_by(SeriesACompany.id)).scalars():
            raw = raw_key(r.name)
            company = by_id.get(r.ir_company_id or 0) or by_raw.get(raw)
            if company is None:
                company = sa_groups.get(raw)
                if company is None:
                    company = sa_groups[raw] = Company(("sa", raw), r.name or "")
            company.rows.append(r)
            index._add(name_key(r.name), company)
        return index

    def find(self, text: str) -> List[Company]:
        """이 글(파일 · 폴더 이름)에 든 기업들 — 서로 다른 기업만, 가장 긴 조각 기준.

        조각을 **통째로** 이어 붙여 맞춘다 — `가나` 가 `가나다라전자` 한가운데에 박혀
        맞는 일이 없다(`company_names` 머리말의 부분일치 금지와 같은 판단). 한 조각
        묶음이 더 긴 묶음 안에 들면(`샘플` ⊂ `샘플 가나다`) 긴 쪽만 센다.
        """
        toks = file_tokens(text)
        spans = []
        for i in range(len(toks)):
            for j in range(i + 1, min(len(toks), i + MAX_SPAN) + 1):
                hit = self.by_key.get("".join(toks[i:j]))
                if hit:
                    spans.append((i, j, hit))
        keep = [s for s in spans
                if not any(o is not s and o[0] <= s[0] and s[1] <= o[1]
                           and (o[1] - o[0]) > (s[1] - s[0]) for o in spans)]
        out: Dict[tuple, Company] = {}
        for _i, _j, hit in keep:
            for ident, company in hit.items():
                out.setdefault(ident, company)
        return list(out.values())


# ── 칸 ──────────────────────────────────────────────────────────────────────

def column(db: Session, actor_id: int):
    """`IR 자료 수신` 추가 칸 — 이름으로 찾고, 없으면 같은 이름의 고정 칸 뒤에 만든다.

    못 쓰는 칸이면(숨김 · O/X) `DriveError` 와 같은 꼴로 사유를 낸다.
    """
    want = custom_columns.label_key(COLUMN).casefold()
    for col in custom_columns.columns(db, TARGET, include_hidden=True):
        if custom_columns.label_key(col.name).casefold() == want:
            if col.is_hidden:
                raise DriveError(ERR_COLUMN_HIDDEN)
            if col.kind != "memo":
                raise DriveError(ERR_COLUMN_KIND)
            return col
    col = custom_columns.add(db, TARGET, COLUMN, "memo", actor_id)
    custom_columns.place(col, AFTER)
    db.flush()
    return col


def _cell(db: Session, col, row) -> str:
    value = db.execute(select(CustomColumnValue.value).where(
        CustomColumnValue.column_id == col.id,
        CustomColumnValue.row_table == row.__tablename__,
        CustomColumnValue.row_id == row.id)).scalar_one_or_none()
    return (value or "").strip()


def _actor(db: Session, st: Settings) -> Optional[int]:
    """수정 기록의 계정 칸 — 판을 저장한 관리자, 없으면 맨 앞 관리자."""
    user = db.get(User, st.actor_id) if st.actor_id else None
    if user is not None and user.is_active and user.role == "admin":
        return user.id
    first = db.execute(select(User.id).where(User.role == "admin", User.is_active == 1)
                       .order_by(User.id)).scalars().first()
    return first


def _clean_name(name: str) -> str:
    """칸 · 화면에 실을 파일 이름 — 제어 글자를 지운다."""
    text = unicodedata.normalize("NFC", name or "")
    return re.sub(r"[\x00-\x1f\x7f]+", " ", text).strip()


def receipt_text(file: dict) -> str:
    """`2026/11/04 수신완료 (드라이브: 파일이름)` — 날짜는 드라이브에 생긴 날(한국 시각)."""
    when = _parse(file.get("createdTime")) or _parse(file.get("modifiedTime"))
    day = when.astimezone(KST).strftime("%Y/%m/%d") if when else clock.today().strftime("%Y/%m/%d")
    return f"{day} 수신완료 (드라이브: {_clean_name(file.get('name', ''))})"


def is_deck(file: dict) -> bool:
    """IR 자료로 적을 파일인가 — PDF · PPT(확장자 또는 mimeType)."""
    name = _clean_name(file.get("name", ""))
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    return ext in DECK_EXTENSIONS or file.get("mimeType") in DECK_MIMES


_TABLE_LABELS = {"ir_companies": "IR", "series_a_companies": "Series A"}


def _rows_note(done: List[Tuple[str, bool]]) -> str:
    """줄마다 결과 → `IR 적음 · Series A 2줄 건너뜀`."""
    tally: Dict[Tuple[str, bool], int] = {}
    for table, wrote in done:
        tally[(table, wrote)] = tally.get((table, wrote), 0) + 1
    parts = []
    for (table, wrote), n in tally.items():
        name = _TABLE_LABELS.get(table, table)
        parts.append(f"{name}{f' {n}줄' if n > 1 else ''} {'적음' if wrote else '건너뜀'}")
    return " · ".join(parts)


def _link(file: dict) -> str:
    link = str(file.get("webViewLink") or "")
    return link if link.startswith("https://") else ""


# ── 한 회차 ─────────────────────────────────────────────────────────────────

def _walk(drive: Drive, frontier: List[str], folders: Dict[str, str], subfolders: bool,
          files: Dict[str, dict], since: Optional[datetime] = None) -> None:
    """폴더들 밑을 읽어 `files` 에 담고, 하위 폴더는 `folders` 에 더해 그 밑도 읽는다."""
    while frontier:
        found = drive.children(frontier, since=since, files_only=not subfolders)
        since = None   # 새로 만난 폴더 안은 통째로 — 옮겨 온 폴더면 안 파일의 시각이 옛날이다
        nxt: List[str] = []
        for item in found:
            fid = str(item.get("id") or "")
            if not _ID.fullmatch(fid):
                continue
            if item.get("mimeType") == FOLDER_MIME:
                if subfolders and fid not in folders and len(folders) < MAX_FOLDERS:
                    folders[fid] = _clean_name(item.get("name", ""))
                    nxt.append(fid)
            elif item.get("mimeType") != SHORTCUT_MIME:
                files[fid] = item
        frontier = nxt


def _scan(drive: Drive, cfg: Config, st: Settings, state: dict, now: datetime):
    """드라이브에서 이번에 볼 파일을 읽는다 → (파일들, 전체 대조였나, 모든 뿌리를 읽었나)."""
    roots = list(cfg.folders)
    last_full = _parse(state.get("full_at"))
    # 기준 시각(`since`)이 없으면 전체 — 처음이거나, 전체 대조 뒤 적기 전에 넘어졌다.
    full = (last_full is None or not state.get("since") or state.get("roots") != roots
            or bool(state.get("subfolders", True)) != st.subfolders
            or now - last_full >= FULL_EVERY or not state.get("folders"))
    files: Dict[str, dict] = {}
    if full:
        folders: Dict[str, str] = {}
        status = []
        first_error = ""
        for fid in roots:
            try:
                meta = drive.folder(fid)
                if meta.get("mimeType") != FOLDER_MIME or meta.get("trashed"):
                    raise DriveError(ERR_NOT_FOLDER)
            except DriveError as exc:
                if exc.public not in (ERR_DENIED, ERR_NOT_FOUND, ERR_NOT_FOLDER):
                    raise          # 인증 · 네트워크 · 할당량 — 회차 전체를 다음에
                status.append({"id": fid, "name": "", "ok": False, "error": exc.public})
                first_error = first_error or exc.public
                continue
            folders[fid] = _clean_name(meta.get("name", ""))
            status.append({"id": fid, "name": folders[fid], "ok": True, "error": ""})
        if not folders:
            state["root_status"] = status
            raise DriveError(first_error or ERR_NOT_FOUND)
        _walk(drive, list(folders), folders, st.subfolders, files)
        state.update(root_status=status, roots=roots, subfolders=st.subfolders,
                     folders=folders, full_at=_iso(now))
        return files, True, all(s["ok"] for s in status)
    folders = dict(state.get("folders") or {})
    since = (_parse(state.get("since")) or now) - OVERLAP
    found = drive.children(list(folders), since=since, files_only=not st.subfolders)
    new_folders: List[str] = []
    for item in found:
        fid = str(item.get("id") or "")
        if not _ID.fullmatch(fid):
            continue
        if item.get("mimeType") == FOLDER_MIME:
            if st.subfolders and fid not in folders and len(folders) < MAX_FOLDERS:
                folders[fid] = _clean_name(item.get("name", ""))
                new_folders.append(fid)
        elif item.get("mimeType") != SHORTCUT_MIME:
            files[fid] = item
    _walk(drive, new_folders, folders, st.subfolders, files)
    state["folders"] = folders
    return files, False, False


class _Writer:
    """적는 손 — 칸과 계정은 처음 적을 때 한 번 찾는다."""

    def __init__(self, db: Session, st: Settings):
        self.db = db
        self.st = st
        self.col = None
        self.actor = None

    def ready(self) -> None:
        if self.col is not None:
            return
        self.actor = _actor(self.db, self.st)
        if self.actor is None:
            raise DriveError(ERR_NO_ACTOR)
        self.db.flush()   # 앞서 바뀐 것은 로그 밖에서 먼저 내보낸다
        token = edit_log.begin(self.actor, edit_log.AUTO_METHOD, LOG_PATH)
        try:
            self.col = column(self.db, self.actor)
        finally:
            edit_log.end(token)

    def current(self, row) -> str:
        return _cell(self.db, self.col, row)

    def write(self, row, text: str) -> None:
        self.db.flush()
        token = edit_log.begin(self.actor, edit_log.AUTO_METHOD, LOG_PATH)
        try:
            custom_columns.write(self.db, row, self.col, text, None)
            self.db.flush()
        finally:
            edit_log.end(token)


def _decide(index: Index, writer: _Writer, file: dict, folder_name: str) -> Tuple[str, dict]:
    """파일 하나 → (결과, 기록 한 줄)."""
    name = _clean_name(file.get("name", ""))
    found = index.find(name)
    via_folder = False
    if not found and folder_name:
        # 기업마다 하위 폴더를 두고 그 안에 `IR.pdf` 처럼 둔 경우 — 폴더 이름으로 한 번 더.
        found = index.find(folder_name)
        via_folder = bool(found)
    entry = {"id": file.get("id"), "name": name, "link": _link(file),
             "folder": folder_name, "created": file.get("createdTime", "")}
    if len(found) != 1:
        entry["candidates"] = [c.label for c in found[:5]]
        entry["why"] = (f"후보 {len(found)}곳 — 하나로 못 정함" if found
                        else "기업명을 찾지 못함")
        return REVIEW, entry
    company = found[0]
    writer.ready()
    entry["company"] = company.label
    if via_folder:
        entry["via"] = "폴더 이름"
    # 두 탭 모두 — 덮지 않는 규칙은 줄마다 따로(값이 있는 줄만 건너뛴다).
    text = receipt_text(file)
    done = []
    for row in company.rows:
        wrote = not writer.current(row)
        if wrote:
            writer.write(row, text)
        done.append((row.__tablename__, wrote))
    entry["rows"] = _rows_note(done)
    return (WRITTEN if any(w for _t, w in done) else SKIPPED), entry


def run(db: Session, cfg: Config, st: Settings, now: Optional[datetime] = None,
        drive: Optional[Drive] = None) -> dict:
    """한 회차 — 읽고, 맞추고, 적고, 상태를 남긴다. 커밋까지 한다.

    넘어지면(드라이브 · 칸 · 뜻밖의 오류) 사유만 남기고 **기준 시각(`since`)은 그대로** 둔다 —
    다음 회차가 같은 자리부터 다시 읽는다. 마지막 확인 시각은 남겨 간격을 지킨다(5분마다
    두드리지 않는다).
    """
    now = now or clock.now()
    state = load_state(db)
    # `since` 는 회차가 끝까지 돈 뒤에만 선다 — 없으면 아직 한 번도 끝까지 못 돈 것이다.
    first = not state.get("since")
    state["last_run_at"] = _iso(now)
    drive = drive or _drive(cfg.sa_file)
    try:
        listing, full, all_roots = _scan(drive, cfg, st, state, now)
        writer = _Writer(db, st)
        index = Index.build(db)
        seen: Dict[str, list] = dict(state.get("files") or {})
        review = {r.get("id"): r for r in state.get("review") or [] if isinstance(r, dict)}
        recent: List[dict] = list(state.get("recent") or [])
        roots = set(cfg.folders)
        folders = state.get("folders") or {}
        counts = {WRITTEN: 0, REVIEW: 0, SKIPPED: 0, KIND: 0, BASELINE: 0}
        baseline = first and not st.backfill
        handled = set()

        def record(fid, sig, result, entry):
            handled.add(fid)
            seen[fid] = sig + [result]
            counts[result] += 1
            if result == REVIEW:
                entry["at"] = _iso(now)
                review[fid] = entry
            else:
                review.pop(fid, None)
                if result in (WRITTEN, SKIPPED, KIND):
                    recent.insert(0, {"name": entry["name"], "company": entry.get("company", ""),
                                      "result": result, "at": _iso(now),
                                      "via": entry.get("via", ""), "rows": entry.get("rows", "")})

        # 이른 파일부터 — 같은 기업이면 먼저 온 파일의 날짜가 칸에 선다.
        for file in sorted(listing.values(),
                           key=lambda f: (f.get("createdTime") or "", f.get("id") or "")):
            fid = file["id"]
            sig = [file.get("modifiedTime") or "", _clean_name(file.get("name", ""))]
            prev = seen.get(fid)
            if prev and list(prev[:2]) == sig:
                continue
            if prev and len(prev) > 2 and prev[2] not in RETRY:
                seen[fid] = sig + [prev[2]]      # 이미 끝난 파일 — 판이 바뀌어도 다시 안 적는다
                continue
            if baseline:
                record(fid, sig, BASELINE, {})
                continue
            if not is_deck(file):
                # PDF · PPT 가 아니다 — 기록만 남기고 확인 필요에는 안 올린다.
                record(fid, sig, KIND, {"name": sig[1]})
                continue
            parent = next((p for p in file.get("parents") or [] if p in folders), "")
            folder_name = folders.get(parent, "") if parent and parent not in roots else ""
            result, entry = _decide(index, writer, file, folder_name)
            record(fid, sig, result, entry)

        if full and all_roots:
            # 전체 대조 — 드라이브에서 사라진 파일은 상태에서도 걷는다.
            for fid in [f for f in seen if f not in listing]:
                seen.pop(fid, None)
                review.pop(fid, None)

        # 확인 필요로 남은 파일 — 그사이 기업이 생겼거나 이름이 고쳐졌으면 지금 적힌다.
        # 드라이브를 다시 묻지 않는다(남겨 둔 이름으로 맞춘다).
        for fid, entry in list(review.items()):
            if fid in handled:
                continue
            result, fresh = _decide(index, writer, {
                "id": fid, "name": entry.get("name", ""), "webViewLink": entry.get("link", ""),
                "createdTime": entry.get("created", "")}, entry.get("folder", ""))
            if result != REVIEW:
                prev = seen.get(fid) or ["", entry.get("name", "")]
                record(fid, list(prev[:2]), result, fresh)
    except DriveError as exc:
        return _failed(db, state, now, exc.public)
    except Exception:  # noqa: BLE001 - 회차 하나가 실을 멈추면 안 된다
        log.exception("%s — 처리하다 뜻밖의 오류", LABEL)
        return _failed(db, state, now, ERR_INTERNAL)

    state.update(
        files=seen,
        review=sorted(review.values(), key=lambda r: r.get("at", ""), reverse=True)[:MAX_REVIEW],
        recent=recent[:MAX_RECENT],
        written=int(state.get("written") or 0) + counts[WRITTEN],
        kind_skipped=int(state.get("kind_skipped") or 0) + counts[KIND],
        since=_iso(now.astimezone(timezone.utc)),
        last_ok_at=_iso(now), error="", error_at="",
        incomplete=drive.incomplete,
        last_counts=counts)
    _save_state(db, state)
    db.commit()
    if counts[WRITTEN] or counts[REVIEW]:
        log.info("%s — 적음 %d · 확인 필요 %d · 건너뜀 %d · 파일 종류 %d", LABEL,
                 counts[WRITTEN], counts[REVIEW], counts[SKIPPED], counts[KIND])
    return {"status": "ok", "full": full, **counts}


def _failed(db: Session, state: dict, now: datetime, reason: str) -> dict:
    """적던 것은 거두고 사유만 남긴다(기준 시각은 그대로 — 다음 회차가 같은 자리부터)."""
    db.rollback()
    state["error"] = reason
    state["error_at"] = _iso(now)
    _save_state(db, state)
    db.commit()
    log.warning("%s 실패: %s", LABEL, reason)
    return {"status": "failed", "error": reason}


def tick(db: Session, now: Optional[datetime] = None, drive: Optional[Drive] = None) -> dict:
    """자동화 실이 5분마다 부른다 — 설정 · 스위치 · 간격을 보고 때가 됐으면 한 회차."""
    cfg = config()
    if not cfg.ready:
        return {"status": "not_configured"}
    st = settings(db)
    if not st.enabled:
        return {"status": "off"}
    now = now or clock.now()
    if not due(load_state(db), st, now):
        return {"status": "not_due"}
    return run(db, cfg, st, now, drive=drive)


# ── 판 ──────────────────────────────────────────────────────────────────────

def _stamp(value: Optional[str]) -> str:
    when = _parse(value)
    return when.astimezone(KST).strftime("%m/%d %H:%M") if when else ""


def panel(db: Session, now: Optional[datetime] = None) -> dict:
    """팀 현황 판이 읽는 한 덩이. **키 내용 · 경로 · 폴더 id 는 싣지 않는다.**"""
    cfg = config()
    st = settings(db)
    state = load_state(db)
    now = now or clock.now()
    key_text = {"unset": f"없음 — 서버에 {ENV_SA_FILE} 가 없습니다",
                "missing": "없음 — 그 경로에 키 파일이 없습니다",
                "ok": "있음"}[cfg.key_state]
    roots = [r for r in state.get("root_status") or [] if r.get("id") in cfg.folders]
    if not cfg.ready:
        status = "설정 없음 — 돌지 않습니다(서버 준비는 docs/GDRIVE_IR.md)"
    elif not st.enabled:
        status = "꺼짐"
    else:
        status = f"켜짐 — {st.interval_min}분마다 확인"
    last = _parse(state.get("last_run_at"))
    next_label = ""
    if cfg.ready and st.enabled:
        nxt = (last + timedelta(minutes=st.interval_min)) if last else now
        next_label = "곧(5분 안)" if nxt <= now else _stamp(_iso(nxt))
    review = []
    for r in state.get("review") or []:
        review.append({"name": r.get("name", ""), "link": r.get("link", ""),
                       "why": r.get("why", ""), "candidates": r.get("candidates") or [],
                       "folder": r.get("folder", ""), "at": _stamp(r.get("at"))})
    recent = [{"name": r.get("name", ""), "company": r.get("company", ""),
               "result": RESULT_LABELS.get(r.get("result"), r.get("result", "")),
               "via": r.get("via", ""), "rows": r.get("rows", ""), "at": _stamp(r.get("at"))}
              for r in (state.get("recent") or [])[:10]]
    return {
        "label": LABEL, "column": COLUMN, "status": status,
        "enabled": st.enabled, "interval_min": st.interval_min,
        "min_interval": MIN_INTERVAL_MIN, "max_interval": MAX_INTERVAL_MIN,
        "subfolders": st.subfolders, "backfill": st.backfill,
        "ready": cfg.ready, "key_ok": cfg.key_state == "ok", "key_text": key_text,
        "env_sa": ENV_SA_FILE, "env_folders": ENV_FOLDERS,
        "folders_set": len(cfg.folders), "bad_folders": cfg.bad_folders,
        "roots": [{"name": r.get("name") or "(이름 모름)", "ok": bool(r.get("ok")),
                   "error": r.get("error", "")} for r in roots],
        "subfolder_count": max(0, len(state.get("folders") or {}) - sum(1 for r in roots if r.get("ok"))),
        "last_run": _stamp(state.get("last_run_at")), "last_ok": _stamp(state.get("last_ok_at")),
        "error": state.get("error", ""), "next": next_label,
        "written": int(state.get("written") or 0),
        "kind_skipped": int(state.get("kind_skipped") or 0),
        "seen": len(state.get("files") or {}),
        "incomplete": bool(state.get("incomplete")),
        "review": review, "recent": recent,
    }
