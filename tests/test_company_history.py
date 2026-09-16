"""기업별 소개 이력 — **어떤 기업을 / 누가 / 몇 번 / 언제** 보냈나.

## 왜 한 수로 줄이면 안 되는가

개발 자료로 재 보면 한 기업이 `보낸 날 6번 · 발송 180건` 인데 날짜별로
`[113, 44, 20, 1, 1, 1]` 이다. 뒤의 `1` 셋은 투자사 **한 명**에게만 나간 것이라
실제로는 단체 세 번 + 개별 세 번이다. 회차 수만 보이면 180건짜리와 103건짜리가
똑같이 `6회` 로 읽힌다. 그래서 이 판이 못 박는 것은 셋이다.

  1. **보낸 날 · 투자사 수 · 발송 건수**가 따로 나온다.
  2. **날짜별로 펼쳐** 그날 몇 명에게 갔는지가 그대로 읽힌다(`[113, 1, 1]`).
  3. **투자사는 수로만** 나간다 — 이름은 한 글자도 안 실린다.

## 그리고 화면이 **말해야 하는 것**

  4. 보낸 사람이 **추정**이면 그렇게 보인다(`(담당) 이름`).
  5. 개수만 적혀 기업을 알 수 없는 회차가 몇 개인지.
  6. 이력에만 있고 기업 목록에 없는 이름이 몇 곳인지.
  7. 이력이 없는 기업은 **빈칸이 아니라 문장**이다 — 빈칸은 "안 보냈다" 인지
     "이름이 안 맞았다" 인지 말하지 못한다.

값은 전부 가상값이다 — 저장소가 공개다.
"""
from __future__ import annotations

import json
import re

import pytest

from .conftest import DEMO_PASSWORD

TEMPLATE = "app/templates/companies.html"


@pytest.fixture()
def logged(client, users):
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    return client


def _company(db, name):
    from app.models import IrCompany

    row = IrCompany(name=name, one_liner="소개", revenue_recent=10)
    db.add(row)
    db.commit()
    return row


def _contacts(db, user, n, prefix="투자사"):
    from app.models import VcContact

    made = []
    for i in range(n):
        c = VcContact(user_id=user.id, name=f"{prefix}{i}", firm=f"{prefix}캐피탈{i}")
        db.add(c)
        made.append(c)
    db.commit()
    return made


def _intro(db, contacts, day, names, weekday="화", source="import"):
    from app.models import ContactActivity

    for c in contacts:
        db.add(ContactActivity(
            contact_id=c.id, kind="deal_intro", content="공유", source=source,
            happened_at=day, weekday=weekday,
            company_names=json.dumps(names, ensure_ascii=False)))
    db.commit()


# ── ① 셋을 따로 센다 ────────────────────────────────────────────────────────

def test_한_명에게만_간_날도_한_날로_세되_건수는_갈린다(db, users):
    """`[113, 1, 1]` 이 그대로 읽혀야 한다 — 이 판의 전부다."""
    from app.services import deal_history

    company = _company(db, "샘플애그")
    many = _contacts(db, users["u1"], 3)
    _intro(db, many, "2026-08-19", ["샘플애그"])
    _intro(db, many[:1], "2026-08-13", ["샘플애그"])
    _intro(db, many[:1], "2026-08-04", ["샘플애그"])

    hist = deal_history.scan(db).of("샘플애그")
    assert hist.days == 3, "보낸 날"
    assert hist.sends == 5, "발송 건수 — 3 + 1 + 1"
    assert hist.investors == 3, "서로 다른 사람 수 — 같은 사람에게 세 번 갔다"
    assert [r.investors for r in hist.rounds] == [3, 1, 1], \
        "날짜별로 몇 명에게 갔는지가 안 펼쳐진다 ★ 단체와 개별이 같아 보인다"
    assert hist.last_sent == "2026-08-19"
    assert company.id  # 줄이 실제로 그 기업에 붙었다


def test_회차_수만_보면_두_기업이_같아_보인다(db, users):
    """같은 `3회` 인데 하나는 5건, 하나는 3건이다."""
    from app.services import deal_history

    _company(db, "샘플애그")
    _company(db, "샘플메디")
    many = _contacts(db, users["u1"], 3)
    for day in ("2026-08-19", "2026-08-13", "2026-08-04"):
        _intro(db, many if day == "2026-08-19" else many[:1], day, ["샘플애그"])
        _intro(db, many[:1], day, ["샘플메디"])

    scan = deal_history.scan(db)
    assert scan.of("샘플애그").days == scan.of("샘플메디").days == 3
    assert scan.of("샘플애그").sends == 5
    assert scan.of("샘플메디").sends == 3


# ── ② 투자사는 수로만 ──────────────────────────────────────────────────────

def test_투자사_이름은_한_글자도_안_나간다(logged, db, users):
    """남의 담당 투자사는 `contacts._owned` 가 404 로 답하는 값이다.

    기업 화면이 그 명단을 읽는 우회로가 되면 안 된다.
    """
    company = _company(db, "샘플애그")
    people = _contacts(db, users["u2"], 2, prefix="남의투자사")
    _intro(db, people, "2026-08-19", ["샘플애그"])

    got = logged.get(f"/api/companies/{company.id}").json()
    blob = json.dumps(got, ensure_ascii=False)
    for c in people:
        assert c.name not in blob, "투자사 담당자 이름이 기업 화면으로 샜다 ★"
        assert c.firm not in blob, "투자사명이 기업 화면으로 샜다 ★"
    assert got["history"][0]["investors"] == 2, "수는 나와야 한다"


def test_남의_담당_투자사도_수에는_들어간다(logged, db, users):
    """기업 쪽은 이미 팀 공용이다 — 조회가 `owner_user_id` 로 안 좁힌다."""
    from app.services import deal_history

    _company(db, "샘플애그")
    _intro(db, _contacts(db, users["u1"], 1, prefix="내"), "2026-08-19", ["샘플애그"])
    _intro(db, _contacts(db, users["u2"], 1, prefix="남"), "2026-08-19", ["샘플애그"])

    assert deal_history.scan(db).of("샘플애그").rounds[0].investors == 2


# ── ③ 보낸 사람 — 추정인지 아닌지가 보인다 ─────────────────────────────────

def test_시트에서_온_옛_줄은_담당으로_미뤄_적고_그렇게_보인다(db, users):
    """줄에 보낸 사람이 안 적혀 있다 — 낼 수 있는 답은 지금 담당뿐이다."""
    from app.services import deal_history

    _company(db, "샘플애그")
    _intro(db, _contacts(db, users["u2"], 2), "2026-08-19", ["샘플애그"])

    sender = deal_history.scan(db).of("샘플애그").rounds[0].senders[0]
    assert sender.name == users["u2"].name
    assert sender.guessed is True
    assert sender.label.startswith("(담당) "), \
        "추정인데 단언처럼 보인다 ★ 담당이 바뀌면 과거 발송도 통째로 옮겨 붙는다"


def test_앱으로_보낸_회차는_실제로_누른_사람이_남는다(db, users):
    from app.models import (DealBatch, DealBatchCompany, SendItem, SendJob,
                            VcContact)
    from app.services import deal_history

    company = _company(db, "샘플애그")
    # 담당은 u2 인데 **보낸 것은 u1** 이다 — 둘이 갈리는 자리를 일부러 만든다.
    contact = VcContact(user_id=users["u2"].id, name="투자사0", firm="가나캐피탈")
    batch = DealBatch(user_id=users["u1"].id, title="9월 1주차",
                      sent_date="2026-09-02")
    db.add_all([contact, batch])
    db.flush()
    job = SendJob(user_id=users["u1"].id, kind="deal_intro", batch_id=batch.id,
                  status="done")
    db.add(job)
    db.flush()
    db.add_all([
        DealBatchCompany(batch_id=batch.id, company_id=company.id, position=1),
        SendItem(job_id=job.id, contact_id=contact.id, room_name="방",
                 message="문구", status="sent", sent_at="2026-09-02T10:00:00+09:00"),
    ])
    db.commit()

    round_ = deal_history.scan(db).of("샘플애그").rounds[0]
    assert round_.batch_title == "9월 1주차"
    assert round_.source_label == "앱 발송"
    assert [s.label for s in round_.senders] == [users["u1"].name], \
        "실제로 보낸 사람이 남는데 담당으로 미뤄 적었다"
    assert round_.senders[0].guessed is False


def test_안_나간_건은_보냈다로_안_센다(db, users):
    """`llm_brief.sent_before` 와 **같은 기준**이어야 한다.

    실제로 나갔고(`sent`) 문구가 나가는 종류의 잡(`SEND_KINDS`)이어야 한다.
    방 연결 확인·시험 발송도 `sent` 로 남는데 그것을 세면 투자사에게 보낸 적
    없는 기업이 이력에 든다.
    """
    from app.models import (DealBatch, DealBatchCompany, SendItem, SendJob,
                            VcContact)
    from app.services import deal_history

    company = _company(db, "샘플애그")
    contact = VcContact(user_id=users["u1"].id, name="투자사0", firm="가나캐피탈")
    batch = DealBatch(user_id=users["u1"].id, title="9월 1주차",
                      sent_date="2026-09-02")
    db.add_all([contact, batch])
    db.flush()
    failed = SendJob(user_id=users["u1"].id, kind="deal_intro",
                     batch_id=batch.id, status="done_with_errors")
    room = SendJob(user_id=users["u1"].id, kind="verify_room",
                   batch_id=batch.id, status="done")
    db.add_all([failed, room])
    db.flush()
    db.add_all([
        DealBatchCompany(batch_id=batch.id, company_id=company.id, position=1),
        SendItem(job_id=failed.id, contact_id=contact.id, room_name="방",
                 message="문구", status="failed"),
        # 방 확인은 아무것도 안 보내는데 `sent` 로 남는다.
        SendItem(job_id=room.id, contact_id=contact.id, room_name="방",
                 message="", status="sent"),
    ])
    db.commit()

    hist = deal_history.scan(db).of("샘플애그")
    assert hist.sends == 0, "안 나간 건이 발송으로 세어졌다 ★"
    # 회차 줄 자체는 남는다 — `마지막으로 소개한 날` 이 예전부터 회차 날짜였고,
    # 그 표시와 이 표가 갈리면 안 된다. 대신 사람 수가 0 이라 그 사실이 보인다.
    assert hist.rounds[0].investors == 0
    assert hist.last_sent == "2026-09-02"


def test_되돌린_줄은_이력에도_안_남는다(db, users):
    from app.models import ContactActivity
    from app.services import deal_history

    _company(db, "샘플애그")
    _intro(db, _contacts(db, users["u1"], 1), "2026-08-19", ["샘플애그"])
    act = db.query(ContactActivity).first()
    act.undone_at = "2026-08-20T00:00:00+09:00"
    db.commit()

    assert deal_history.scan(db).of("샘플애그").days == 0


# ── ④ 막히는 것 셋을 화면이 말한다 ─────────────────────────────────────────

def test_개수만_적힌_회차는_어느_기업_줄에도_안_붙는다(logged, db, users):
    """`핵심 딜 8개사` — 기업 이름이 없어 기업 줄에서 출발하면 안 보인다."""
    from app.models import ContactActivity
    from app.services import deal_history

    _company(db, "샘플애그")
    for c in _contacts(db, users["u1"], 3):
        db.add(ContactActivity(contact_id=c.id, kind="deal_intro",
                               content="핵심 딜 8개사", happened_at="2026-08-04",
                               weekday="화", company_count=8))
    db.commit()

    scan = deal_history.scan(db)
    assert scan.count_only.rounds == 1
    assert scan.count_only.rows == 3
    assert scan.of("샘플애그").days == 0

    page = re.sub(r"\s+", " ", logged.get("/companies").text)
    assert "기업을 알 수 없는 회차가 1개" in page, \
        "안 잡히는 회차가 있는데 화면이 말하지 않는다 ★"
    assert "3줄" in page and "2026-08-04" in page, "언제 것인지도 적어야 한다"


def test_이력에만_있는_이름은_몇_곳인지_밝힌다(logged, db, users):
    """`llm_brief` 가 `sent_before_unmatched` 로 다루는 그 문제다."""
    from app.services import deal_history

    _company(db, "샘플애그")
    _intro(db, _contacts(db, users["u1"], 1), "2026-08-19",
           ["샘플애그", "목록에없는기업", "또없는기업"])

    assert deal_history.scan(db).unmatched == 2
    page = logged.get("/companies").text
    assert "기업 목록에 없는 이름이" in page, "합계가 왜 안 맞는지 적을 자리가 없다 ★"
    assert "목록에없는기업" not in page, "못 이은 이름을 화면에 흘렸다"


def test_이력이_없는_기업은_빈칸이_아니라_문장이다(logged, db):
    _company(db, "샘플애그")
    page = logged.get("/companies").text
    assert "아직 딜 소개에 넣은 적이 없습니다" in page, \
        "빈칸은 '안 보냈다' 인지 '이름이 안 맞았다' 인지 말하지 못한다 ★"


# ── ⑤ 표의 `소개 횟수` 칸 ───────────────────────────────────────────────────

def test_표에_회차와_건수가_함께_선다(logged, db, users):
    _company(db, "샘플애그")
    many = _contacts(db, users["u1"], 3)
    _intro(db, many, "2026-08-19", ["샘플애그"])
    _intro(db, many[:1], "2026-08-13", ["샘플애그"])

    page = logged.get("/companies").text
    assert "소개 횟수" in page
    cell = re.search(r'<td class="num sent-count">(.*?)</td>', page, re.S)
    assert cell, "`소개 횟수` 칸이 없다"
    assert "2회" in cell.group(1) and "4건" in cell.group(1), \
        "회차 수만 보이면 180건짜리와 103건짜리가 똑같아 보인다 ★"
    assert "마지막 2026-08-19" in cell.group(1)


def test_소개_횟수_칸에는_필터를_안_건다():
    """값이 줄마다 다른 숫자라 목록으로 고를 것이 아니다.

    (`tests/test_filter_columns.py` 가 안 쓰이는 필터 속성을 따로 막는다 —
     여기서는 **세우지 않았다**는 것 자체를 못 박는다.)
    """
    from pathlib import Path

    text = Path(TEMPLATE).read_text(encoding="utf-8")
    head = re.search(r'<th class="num" style="width:84px"[^>]*>소개 횟수</th>', text)
    assert head, "`소개 횟수` 머리글 모양이 바뀌었다"
    assert "data-filters" not in head.group(0)
    assert "data-f-sent" not in text, "행에 안 쓰이는 필터 값을 싣고 있다"


# ── ⑥ `/deals` 카드의 `N회` 뱃지 ────────────────────────────────────────────

def test_고르는_카드에도_몇_번_나갔는지_선다(logged, db, users):
    """`3일 전 소개` 만으로는 이번이 두 번째인지 일곱 번째인지 알 수 없다."""
    _company(db, "샘플애그")
    many = _contacts(db, users["u1"], 3)
    _intro(db, many, "2026-08-19", ["샘플애그"])
    _intro(db, many[:1], "2026-08-13", ["샘플애그"])

    page = logged.get("/deals").text
    assert ">2회</span>" in page, "카드에 몇 번 나갔는지가 없다"
    assert "보낸 날 2번 · 투자사 3명 · 발송 4건" in page


# ── ⑦ 규칙이 **한 벌**인가 ─────────────────────────────────────────────────

def test_최근에_소개함_표시와_이력이_같은_훑기에서_나온다(db, users):
    """두 벌로 적으면 `최근에 소개함` 과 이력 수가 갈린다.

    이 저장소가 반복해서 데인 자리라, 규칙이 아니라 **같은 함수**를 지나는지를
    본다.
    """
    from app.services import deal_history

    _company(db, "샘플애그")
    _intro(db, _contacts(db, users["u1"], 2), "2026-08-19", ["샘플애그"])

    scan = deal_history.scan(db)
    assert scan.last_sent_map() == deal_history.last_sent_map(db)
    assert scan.last_sent_map()[deal_history._key("샘플애그")] == \
        scan.of("샘플애그").last_sent


def test_이름_다른_표기도_한_기업으로_묶인다(db, users):
    """`(주)` 와 띄어쓰기 차이로 다른 기업이 되면 안 된다 — `_key` 한 곳이다."""
    from app.services import deal_history

    _company(db, "(주)샘플애그")
    _intro(db, _contacts(db, users["u1"], 1), "2026-08-19", ["샘플 애그"])

    assert deal_history.scan(db).of("(주)샘플애그").days == 1
