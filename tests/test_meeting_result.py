"""미팅 결과 — 미팅 후기 표에서 바로 고르고(#176), 대시보드가 결과별로 센다(#183).

1. 고를 수 있는 말은 셋이다 — 투자 의사 없음 · 투자 보류 · 투자 검토 진행(+ 빈칸).
   DB 에는 예전 코드(`pass` · `hold` · `investing`)가 그대로 남는다.
2. 표의 `결과` 칸에서 고르면 **결과만** 바뀐다 — 결과 문의 기록(`followup_done`)은
   그대로다. 셋 밖의 말은 받지 않는다.
3. 자동 발송(A7)은 코드로 가르므로 하던 대로 한다 — 결과가 적히면 첫 문의를 안 하고,
   비우면 다시 묻는 대상이다.
4. 대시보드 반응 패널의 `미팅완료 리마인드 TEL` 오른쪽에 결과별 수가 선다.
"""
from __future__ import annotations

from datetime import date

import pytest

from .conftest import DEMO_PASSWORD

THREE = ["투자 의사 없음", "투자 보류", "투자 검토 진행"]


@pytest.fixture()
def logged(client, users):
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    return client


def _meeting(db, owner, name="홍길동", **kw):
    from app.models import Meeting, VcContact

    contact = VcContact(user_id=owner.id, name=name, firm="가나벤처스")
    db.add(contact)
    db.flush()
    row = Meeting(user_id=owner.id, contact_id=contact.id, kind="first",
                  scheduled_at=kw.pop("scheduled_at", "2026-10-20"),
                  status=kw.pop("status", "done"), done_at=kw.pop("done_at", "2026-10-20"),
                  **kw)
    db.add(row)
    db.commit()
    return row


def test_고를_수_있는_말은_사용자가_정한_셋이다():
    from app.services import pipeline

    assert list(pipeline.OUTCOME_CHOICES.values()) == THREE
    # 코드는 예전 그대로 — A7 · 재접촉이 코드로 가른다.
    assert list(pipeline.OUTCOME_CHOICES) == ["pass", "hold", "investing"]
    # 예전에 고를 수 있던 `검토 중` 은 이름만 남는다(이미 그렇게 적힌 미팅이 있다).
    assert pipeline.OUTCOMES["reviewing"] == "검토 중"
    assert "reviewing" not in pipeline.OUTCOME_CHOICES


@pytest.mark.parametrize("sent, stored", [
    ("투자 의사 없음", "pass"), ("투자 보류", "hold"), ("투자 검토 진행", "investing"),
    ("hold", "hold"), ("", None), ("  ", None),
])
def test_표에서_고르면_결과만_바뀐다(logged, db, users, sent, stored):
    from app.models import Meeting

    m = _meeting(db, users["u1"], outcome="investing", followup_done=0)
    r = logged.patch(f"/api/meetings/{m.id}", json={"outcome": sent})
    assert r.status_code == 200, r.text
    db.expire_all()
    got = db.get(Meeting, m.id)
    assert got.outcome == stored
    assert got.followup_done == 0, "결과만 고쳤는데 결과 문의가 닫히면 안 된다"
    assert got.followup_note is None


def test_셋_밖의_말은_받지_않는다(logged, db, users):
    from app.models import Meeting

    m = _meeting(db, users["u1"], outcome="hold")
    r = logged.patch(f"/api/meetings/{m.id}", json={"outcome": "아마 할 듯"})
    assert r.status_code == 400
    assert "투자 의사 없음" in r.json()["detail"]
    db.expire_all()
    assert db.get(Meeting, m.id).outcome == "hold"


def test_남의_미팅_결과는_못_고친다(logged, db, users):
    m = _meeting(db, users["u2"], outcome="hold")
    assert logged.patch(f"/api/meetings/{m.id}", json={"outcome": "투자 의사 없음"}).status_code == 404


def test_거절에서_되살리면_결과를_물을_날이_다시_잡힌다(logged, db, users):
    """거절로 마치면 물을 날을 안 잡는다(`complete_meeting`). 거기서 보류로 바꿨는데
    날이 비어 있으면 그 미팅은 결과 문의 목록에 영영 안 뜬다."""
    from app.models import Meeting
    from app.services import pipeline

    m = _meeting(db, users["u1"], outcome="pass", followup_due=None, done_at="2026-10-20")
    logged.patch(f"/api/meetings/{m.id}", json={"outcome": "투자 보류"})
    db.expire_all()
    got = db.get(Meeting, m.id)
    assert got.followup_due == pipeline.followup_date(date(2026, 10, 20)).isoformat()
    # 이미 잡힌 날은 건드리지 않는다.
    logged.patch(f"/api/meetings/{m.id}", json={"outcome": "투자 의사 없음"})
    db.expire_all()
    assert db.get(Meeting, m.id).followup_due == got.followup_due


def test_미팅_후기_표의_결과_칸은_세_가지에서_고른다(logged, db, users):
    _meeting(db, users["u1"], name="완료함", outcome="hold")
    _meeting(db, users["u1"], name="취소함", status="canceled", done_at=None)
    body = logged.get("/ir").text
    table = body.split('id="review-table"', 1)[1].split("</table>", 1)[0]
    # 줄에 번호가 있어야 칸 편집기가 저장한다 — 없으면 조용히 안 저장됐다.
    assert 'data-id="' in table
    cell = table.split('data-field="outcome"', 1)[1].split("</td>", 1)[0]
    assert 'data-type="pick"' in cell and "data-fixed-choices" in cell
    # 보기 밖의 말은 400 이라 고르개 안내에 `새로 적어도 됩니다` 를 안 세운다(JS 쪽 검사:
    # tests/js/meeting_outcome_pick_hint_test.js).
    assert "data-choices-only" in cell
    assert f'data-choices="{",".join(THREE)}"' in cell
    assert cell.rstrip().endswith(">투자 보류")
    # 취소된 미팅에는 고를 칸이 없다.
    assert table.count('data-field="outcome"') == 1


def test_화면의_결과_고르개에_예전_말이_안_선다(logged, db, users):
    _meeting(db, users["u1"], outcome=None, followup_due="2026-10-01")
    body = logged.get("/ir").text
    for label in THREE:
        assert f">{label}</option>" in body
    for old in ("검토 중", "거절", "보류", "투자 검토"):
        assert f">{old}</option>" not in body, f"예전 말 `{old}` 이 고르개에 남았다"


@pytest.mark.parametrize("label, asks", [
    ("투자 의사 없음", False), ("투자 보류", False), ("투자 검토 진행", False), ("", True),
])
def test_자동_발송_A7_은_고른_결과를_하던_대로_읽는다(logged, db, users, label, asks):
    from app.models import Meeting, VcContact
    from app.services.automations import meeting_review as a7

    m = _meeting(db, users["u1"], outcome="reviewing")
    logged.patch(f"/api/meetings/{m.id}", json={"outcome": label})
    db.expire_all()
    got = db.get(Meeting, m.id)
    contact = db.get(VcContact, got.contact_id)
    reason = a7.why_not(db, got, contact, [got])
    assert (reason != "결과가 이미 적혀 있습니다") is asks, reason
    # 두 번째(한 달 뒤 투자 결정 문의)는 `투자 의사 없음` 만 뺀다 — 예전 `거절` 그대로.
    second = a7.why_not_decision(db, got, contact, [got])
    assert (second == "결과가 거절로 적혀 있습니다") is (label == "투자 의사 없음")


def test_대시보드_미팅완료_리마인드_TEL_오른쪽에_결과별_수가_선다(logged, db, users):
    from app.services import dashboard

    for i, outcome in enumerate(["pass", "pass", "hold", "investing", "reviewing", None]):
        _meeting(db, users["u1"], name=f"투자사{i}", outcome=outcome)
    # 취소된 미팅 · 남의 미팅은 안 센다.
    _meeting(db, users["u1"], name="취소", outcome="hold", status="canceled")
    _meeting(db, users["u2"], name="남의것", outcome="hold")

    body = logged.get("/").text
    row = body.split("미팅완료 리마인드 TEL", 1)[1].split("</div>", 1)[0]
    assert "미팅 결과" in row, "미팅완료 리마인드 TEL 바로 오른쪽(같은 줄 뒤)에 서야 한다"
    tile = row.split("meeting-results", 1)[1]
    assert 'href="/ir#reviews"' in tile
    for n, label in zip((2, 1, 1), THREE):
        assert f"<b>{n}</b>{label}" in tile

    from app.models import VcContact
    mine = [c.id for c in db.query(VcContact).filter_by(user_id=users["u1"].id)]
    got = dashboard.meeting_results(db, mine)
    assert [(r["label"], r["count"]) for r in got] == list(zip(THREE, (2, 1, 1)))
    assert all(r["count"] == 0 for r in dashboard.meeting_results(db, []))
