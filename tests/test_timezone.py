"""서버가 '오늘' 을 한국 날짜로 봐야 한다 — **읽을 때도 적을 때도.**

컨테이너 기본값은 UTC 다. 그러면 **자정부터 아침 9시까지 서버는 어제**라고
생각한다 — 8월 25일 아침에 대시보드가 "8/26 발송까지 2일 남음" 이라고 떴다.
하루가 어긋나면 회차를 통째로 놓친다.

컨테이너 시간대는 그때 고쳤는데 **시각을 저장하는 쪽은 UTC 로 남아 있었다.**
그래서 같은 하루 어긋남이 반대 방향으로 되살아났다 — 한국 새벽에 보내면
발송일이 어제로 적혀, 6~7일 뒤로 잡아야 할 리마인드가 5일 뒤에 잡혔다.

여기 있는 검사는 **지금 시각에 기대지 않는다.** 자정~오전 9시에만 걸리는
검사는 낮에 돌리면 통과해 버려서, 되살아나도 아무도 모른다. 그래서 UTC 날짜와
한국 날짜가 갈리는 순간을 만들어 넣고 잰다.
"""
from __future__ import annotations

import contextlib
import os
import pathlib
import re
import time
from datetime import date, datetime

import pytest

# UTC 로 적으면 **어제**가 되는 순간. 한국시간 2026-08-27 00:21:24 목요일.
DAWN_UTC = "2026-08-26T15:21:24+00:00"
DAWN_KST_DATE = "2026-08-27"

needs_tzset = pytest.mark.skipif(
    not hasattr(time, "tzset"), reason="시간대를 바꿔 끼울 수 없는 OS")


@contextlib.contextmanager
def _seoul_at(monkeypatch, utc_moment: str):
    """시계를 그 순간에 세우고 프로세스 시간대를 한국으로 둔다.

    `app/clock.py` 가 보는 `datetime` 만 바꿔 끼운다 — 진짜 `datetime.now` 와
    똑같이 굴어야 하므로 `tz` 를 주면 그 시간대로, 안 주면 지역시간 naive 로
    돌려준다. 그래야 `now().astimezone()` 이 실제와 같은 길을 지난다.
    """
    from app import clock

    moment = datetime.fromisoformat(utc_moment)

    class _Frozen(datetime):
        @classmethod
        def now(cls, tz=None):
            if tz is None:
                return moment.astimezone().replace(tzinfo=None)
            return moment.astimezone(tz)

    before = os.environ.get("TZ")
    os.environ["TZ"] = "Asia/Seoul"
    time.tzset()
    try:
        monkeypatch.setattr(clock, "datetime", _Frozen)
        yield
    finally:
        if before is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = before
        time.tzset()


def test_compose_pins_the_timezone():
    """도커 기본값(UTC)이면 한국 새벽에 날짜가 하루 밀린다."""
    compose = pathlib.Path("docker-compose.yml").read_text(encoding="utf-8")
    # 웹과 발송 프로그램 양쪽 — 발송 로그 시각도 한국 시간이어야 대조된다
    assert compose.count("TZ:") >= 2, "TZ 설정이 빠진 서비스가 있다"
    assert "Asia/Seoul" in compose


def test_the_image_can_resolve_that_timezone():
    """`TZ` 만 주고 tzdata 가 없으면 조용히 UTC 로 남는다."""
    dockerfile = pathlib.Path("Dockerfile").read_text(encoding="utf-8")
    # python:*-slim 은 tzdata 를 포함한다. 베이스를 바꾸면 이 테스트가 알려 준다.
    assert re.search(r"FROM python:3\.\d+-slim", dockerfile), \
        "베이스 이미지를 바꿨다면 tzdata 가 들어 있는지 확인하세요"


def test_days_left_counts_calendar_days(db, users):
    """'내일 발송' 이면 1일이다. 시각이 아니라 날짜로 센다."""
    from app.services import readiness

    got = readiness.report(db, users["u1"], today=date(2026, 8, 25))
    # 8/26 은 넷째 수요일 — 기본 규칙(첫째·셋째)에는 없다.
    # 여기서 재는 것은 **날짜 빼기가 맞는가** 이다.
    assert got["days_left"] == (got["next_send"] - date(2026, 8, 25)).days


# --- 저장하는 쪽 ------------------------------------------------------------

@needs_tzset
def test_saved_time_carries_the_korean_date_not_the_utc_one(monkeypatch):
    """한국 새벽에 적은 시각은 **그날**이어야 한다. UTC 로 적으면 어제가 된다."""
    from app import clock

    with _seoul_at(monkeypatch, DAWN_UTC):
        stamp = clock.now_iso()

    assert stamp == "2026-08-27T00:21:24+09:00"
    assert stamp[:10] == DAWN_KST_DATE, "UTC 로 적으면 2026-08-26 — 하루 어긋난다"


@needs_tzset
def test_saved_time_keeps_the_offset(monkeypatch):
    """오프셋을 떼면 **순간**을 잃는다.

    세션 만료와 에이전트 연결 경과시간은 `clock.now() - fromisoformat(저장값)`
    으로 재는데, naive 와 aware 를 빼면 TypeError 다. 앞 10자를 한국 날짜로
    읽으면서 순간 계산도 그대로 맞으려면 오프셋이 남아 있어야 한다.
    """
    from app import clock

    with _seoul_at(monkeypatch, DAWN_UTC):
        parsed = datetime.fromisoformat(clock.now_iso())
        assert parsed.utcoffset() is not None, "오프셋 없이 적으면 순간을 잃는다"
        # 표기는 한국시간이지만 가리키는 순간은 그대로다.
        assert parsed == datetime.fromisoformat(DAWN_UTC)
        assert (clock.now() - parsed).total_seconds() == 0


@needs_tzset
def test_the_orm_default_stamps_the_same_shape(db, users, monkeypatch):
    """모델이 알아서 찍는 시각도 라우터가 찍는 것과 같은 모양이어야 한다.

    `created_at`/`updated_at` 은 `TimestampMixin` 이 따로 찍는다 — 예전에는
    이쪽이 별도 `_now_iso()` 를 들고 있어서 라우터 쪽만 고쳐도 남았을 자리다.
    문자열 그대로 `>=` 로 거르고 정렬하는 곳이 있어(`dashboard` · `readiness`),
    한 칸만 모양이 다르면 그 칸만 조용히 다른 날로 걸린다.
    """
    from app import clock
    from app.models import VcContact

    with _seoul_at(monkeypatch, DAWN_UTC):
        contact = VcContact(user_id=users["u1"].id, name="홍길동", title="심사역")
        db.add(contact)
        db.flush()
        assert contact.created_at == clock.now_iso()

    assert contact.created_at[:10] == DAWN_KST_DATE


def test_only_one_place_reads_the_clock():
    """`datetime.now(...)` 이 흩어지면 또 한 군데만 고쳐진다.

    전에 컨테이너 시간대를 고쳤을 때 저장하는 다섯 군데(`deps`·`models`·
    `cadence`·`mail_sender`·`auth`)가 UTC 로 남아 이 버그가 살아남았다.
    부르는 자리를 `app/clock.py` 하나로 묶어 두고, 늘어나면 여기서 걸린다.
    """
    offenders = []
    for path in sorted(pathlib.Path("app").rglob("*.py")):
        if path.name == "clock.py":
            continue
        for lineno, line in enumerate(
                path.read_text(encoding="utf-8").splitlines(), start=1):
            if "datetime.now(" in line and not line.lstrip().startswith("#"):
                offenders.append(f"{path}:{lineno}")
    assert not offenders, \
        "시각은 app/clock.py 로만 읽는다 — " + ", ".join(offenders)


# --- 하루 어긋나면 무엇이 깨지는가 ------------------------------------------

def _sent_item(db, user_id, contact_id, sent_at):
    """성공한 딜소개 한 건. 발송 시각만 바깥에서 정한다."""
    from app.models import DealBatch, SendItem, SendJob

    batch = DealBatch(user_id=user_id, title="회차", sent_date=sent_at[:10])
    db.add(batch)
    db.flush()
    job = SendJob(user_id=user_id, kind="deal_intro", batch_id=batch.id,
                  status="done")
    db.add(job)
    db.flush()
    item = SendItem(job_id=job.id, contact_id=contact_id, stage=1,
                    room_name="방", message="문구", status="sent",
                    sent_at=sent_at)
    db.add(item)
    db.flush()
    return item, job


@needs_tzset
def test_dawn_send_does_not_pull_the_follow_up_a_day_earlier(db, users,
                                                             monkeypatch):
    """한국 새벽에 보낸 건의 리마인드는 **그날** 기준으로 잡혀야 한다.

    UTC 로 적히면 발송일이 어제(8/26)로 읽혀 리마인드가 하루 당겨진다 —
    `test_end_to_end` 가 6~7일이어야 할 간격을 5일로 잡아 걸렸던 자리다.

    간격을 6~7일 중에서 무작위로 고르므로(`follow_up_date`), 그대로 두면
    하루 차이가 그 흔들림에 묻힌다. 최솟값만 내는 주사위를 넣어 날짜를 못박는다.
    """
    import random

    from app import clock
    from app.models import VcContact
    from app.services import cadence

    class _AlwaysMin(random.Random):
        def randint(self, lo, hi):
            return lo

    contact = VcContact(user_id=users["u1"].id, name="홍길동", title="심사역")
    db.add(contact)
    db.flush()

    with _seoul_at(monkeypatch, DAWN_UTC):
        item, job = _sent_item(db, users["u1"].id, contact.id, clock.now_iso())
        seq = cadence.start_or_advance(db, item, job, _AlwaysMin())

    # 보낸 날은 8/27(목). 최소 간격 6일 → 9/2(수). 주말 보정도 걸리지 않는다.
    assert cadence._as_date(item.sent_at) == date(2026, 8, 27)
    assert seq.next_due_date == "2026-09-02", \
        "UTC 로 적으면 8/26 기준이 되어 2026-09-01 — 하루 당겨진다"


@needs_tzset
def test_dawn_send_counts_in_the_week_it_happened(db, users, monkeypatch):
    """월요일 새벽에 보낸 건이 '이번 주 보낸 건수'에 들어가야 한다.

    UTC 로 적히면 일요일이 되어 **지난주로 빠진다** — 주간 목표가 월요일
    아침마다 0 으로 보인다. `dashboard.py` 의
    `coalesce(sent_at,'') >= week_start` 이 그 자리다: 날짜 문자열과 견주므로
    저장값이 하루 이르면 그대로 걸러진다.
    """
    from app import clock
    from app.models import VcContact
    from app.services import dashboard

    # 한국시간 2026-08-31 00:30 월요일 = UTC 2026-08-30 15:30 일요일
    monday_dawn = "2026-08-30T15:30:00+00:00"

    contact = VcContact(user_id=users["u1"].id, name="홍길동", title="심사역",
                        kakao_room_name="홍길동 심사역님 가나벤처스",
                        room_verified="verified", channel_kakao=1)
    db.add(contact)
    db.flush()

    with _seoul_at(monkeypatch, monday_dawn):
        _sent_item(db, users["u1"].id, contact.id, clock.now_iso())
    db.commit()

    got = dashboard.user_dashboard(db, users["u1"], today=date(2026, 8, 31))
    sent = next(k["value"] for k in got["kpis"] if k["key"] == "sent")
    assert sent == 1, "UTC 로 적으면 8/30(일)이 되어 지난주로 빠진다"
