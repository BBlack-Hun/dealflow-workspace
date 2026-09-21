"""홍보메일 **제목을 문구에서 골라 쓴다.**

격주로 나가는 홍보메일의 제목을 매번 손으로 적고 있었다. 문구 화면에는
`홍보메일 제목`(`mail_subject`) 갈래가 **등록만 돼 있고** 아무 데서도 읽지
않았다 — 만들 수는 있는데 고를 데가 없었다. 그 이음새를 잇는다.

여기서 못박는 것.

1. **비었을 때의 차례를 안 깬다** — 제목을 안 적으면 예전 그대로 회차명이,
   회차명도 없으면 `"딜 소개"` 가 나간다. 지금 그렇게 나가는 메일이 있다.
2. **적은 제목은 문구와 같은 치환을 지난다** — 문구 화면이 `{담당자명}` 을
   쓰라고 적어 두고 있는데 제목만 그것을 안 지나면, 그 글자가 **그대로**
   투자사 메일함에 꽂힌다.
3. **시험방이 켜져 있어도 제목은 그대로다** — `[테스트]` 접두를 붙이지 않는다.
4. **카톡에는 제목이 없다** — 화면이 제목을 실어 보내도 카톡 건은 `None` 이다.

고르는 손 자체는 브라우저에 있다(고르면 **칸을 채운다**) — 그 검사는
`tests/js/mail_subject_pick_test.js` 가 `deals.js` 를 그대로 돌려서 본다.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from .conftest import DEMO_PASSWORD

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def logged(client, users):
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    return client


@pytest.fixture()
def mail_on(monkeypatch):
    monkeypatch.setenv("DEALFLOW_SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("DEALFLOW_SMTP_PORT", "465")
    monkeypatch.setenv("DEALFLOW_SMTP_USER", "deal@example.com")
    monkeypatch.setenv("DEALFLOW_SMTP_FROM", "deal@example.com")
    monkeypatch.setenv("DEALFLOW_SMTP_PASSWORD", "secret")


@pytest.fixture()
def seed(db, users, monkeypatch):
    """메일로 받을 담당자 하나와 기업 둘. 발송기는 부르지 않는다."""
    from app.models import IrCompany, SheetOwner, VcContact
    from app.services import mail_sender

    monkeypatch.setattr(mail_sender, "send_job", lambda *a, **k: None)
    db.add_all([
        SheetOwner(label="내 명단", user_id=users["u1"].id),
        VcContact(user_id=users["u1"].id, name="메일받는분", firm="가나벤처스",
                  title="심사역", source_sheet="내 명단",
                  channel_email=1, channel_kakao=0,
                  email="hong@example.com", kakao_room_name="가상방",
                  connect_stage="connected"),
        IrCompany(name="샘플애그", one_liner="B2B 농산물", revenue_recent=12),
        IrCompany(name="샘플로보", one_liner="물류 로봇", revenue_recent=8),
    ])
    db.commit()
    return {
        "contact": db.query(VcContact).filter_by(name="메일받는분").first().id,
        "companies": [c.id for c in db.query(IrCompany).order_by(IrCompany.id).all()],
    }


def _send(client, seed, **extra):
    body = {"company_ids": seed["companies"], "contact_ids": [seed["contact"]],
            "channel": "email", "title": "09/16 (9월 3주차)"}
    body.update(extra)
    r = client.post("/api/deals/send", json=body)
    assert r.status_code == 200, r.text
    return r.json()["job_id"]


def _subject(db, job_id):
    from app.models import SendItem

    return db.query(SendItem).filter_by(job_id=job_id).one().subject


# ── 비었을 때의 차례 — 손대지 않은 그대로 ──────────────────────────────────

def test_제목을_비우면_회차명이_그대로_제목이_된다(logged, db, seed, mail_on):
    """★ 기존 동작. 이 길로 나가는 메일이 지금 있다."""
    assert _subject(db, _send(logged, seed)) == "09/16 (9월 3주차)"
    # 빈 글자·공백만 적은 것도 '안 적은 것' 이다.
    assert _subject(db, _send(logged, seed, subject="   ")) == "09/16 (9월 3주차)"


def test_회차명도_없으면_딜_소개(logged, db, seed, mail_on):
    assert _subject(db, _send(logged, seed, title="")) == "딜 소개"


def test_회차명은_치환을_지나지_않는다(logged, db, seed, mail_on):
    """회차명은 문구가 아니라 **사람이 그 회차에 붙인 이름**이다.

    여기에 손질을 끼우면 이미 그 이름 그대로 나가고 있는 메일의 제목이 달라진다.
    """
    job = _send(logged, seed, title="{투자사} 9월 3주차")
    assert _subject(db, job) == "{투자사} 9월 3주차"


# ── 고른 제목이 실린다 ──────────────────────────────────────────────────────

def test_적은_제목이_그대로_실린다(logged, db, seed, mail_on):
    job = _send(logged, seed, subject="9월 3주차 딜 소개")
    assert _subject(db, job) == "9월 3주차 딜 소개"


def test_제목도_문구와_같은_치환을_지난다(logged, db, seed, mail_on):
    """★ 제목만 치환을 안 지나면 `{담당자명}` 이 글자 그대로 나간다."""
    job = _send(logged, seed, subject="{투자사} {담당자명} {직함} 딜 {개수}개사")
    # '심사역' → '심사역님'(`honorific_title`), 이름과 존칭 사이 공백 정리까지
    # 문구와 **같은 손**을 지난다(`message_composer.render_template`).
    assert _subject(db, job) == "가나벤처스 메일받는분 심사역님 딜 2개사"


def test_개수는_본문이_세는_수와_같다(logged, db, seed, mail_on):
    """후속 문구(리마인드·미팅 요청)의 본문은 기업을 세지 않는다 — 제목도 같다.

    제목만 다른 수를 말하면 열어 보기도 전에 어긋난다
    (`message_composer.compose_message` 의 `count`).
    """
    job = _send(logged, seed, mode="remind", subject="딜 {개수}개사")
    assert _subject(db, job) == "딜 0개사"


def test_시험방이_켜져_있어도_제목은_그대로다(logged, db, seed, mail_on, monkeypatch):
    """★ 시험방은 제목을 건드리지 않는다 — 치환 결과가 그대로 나간다.

    예전에는 여기에 `[테스트]` 가 붙었다. 시험방이 켜져 있으면 카톡은 전부
    그 방으로 모이는데 메일만 진짜로 나갔기 때문에, 그 차이를 제목으로나마
    알리려던 것이다. 이제 카톡도 제 갈 곳으로 간다 — 알릴 차이가 없고,
    남겨 두면 **투자사 메일함 제목 줄에 `[테스트]` 가 꽂힌다.**
    """
    from app import config

    monkeypatch.setattr(config, "TEST_ROOM", "테스트방")
    job = _send(logged, seed, subject="{투자사} 딜 소개")
    assert _subject(db, job) == "가나벤처스 딜 소개"


def test_카톡에는_제목이_없다(logged, db, seed, mail_on):
    """★ 제목은 메일에만 쓴다 — 그 구분이 흐려지면 안 된다."""
    from app.models import SendItem, VcContact

    row = db.get(VcContact, seed["contact"])
    row.channel_kakao = 1
    db.commit()
    r = logged.post("/api/deals/send", json={
        "company_ids": seed["companies"], "contact_ids": [seed["contact"]],
        "channel": "kakao", "title": "09/16 (9월 3주차)",
        "subject": "{투자사} 딜 소개"})
    assert r.status_code == 200, r.text
    item = db.query(SendItem).filter_by(job_id=r.json()["job_id"]).one()
    assert item.channel == "kakao"
    assert item.subject is None


# ── 만들고 고르는 길이 이어져 있는가 ───────────────────────────────────────

def test_제목_문구를_만드는_자리가_문구_화면에_있다(logged):
    """만들 수 없으면 골라 쓸 것도 없다.

    `mail_subject` 는 딜 제안 관리의 탭과 짝이 없어 **'그 밖의 문구'** 에
    선다(`templates_crud.py` 의 `others`). 접혀 있을 뿐 만드는 자리는 있다.
    """
    html = logged.get("/templates").text
    assert 'id="mail_subject"' in html, "제목 문구를 만드는 구간이 없다"
    assert "홍보메일 제목" in html
    assert 'action="/templates/new"' in html


def test_만들어_둔_제목_문구가_발송_화면으로_실려_온다(logged, db, users):
    """발송 화면의 고르개는 `/api/templates` 한 길로 채운다 — 새 길을 내지 않는다."""
    from app.models import MessageTemplate

    db.add(MessageTemplate(user_id=users["u1"].id, kind="mail_subject",
                           name="정규 딜소개", body="우리브이씨 딜 소개", is_active=1))
    db.commit()
    rows = logged.get("/api/templates").json()["templates"]
    mine = [t for t in rows if t["kind"] == "mail_subject"]
    assert [t["name"] for t in mine] == ["정규 딜소개"]
    assert mine[0]["body"] == "우리브이씨 딜 소개"
    # 고르개에 적을 갈래 이름도 같은 응답에 실려 있다.
    kinds = {k["kind"] for k in logged.get("/api/templates").json()["kinds"]}
    assert "mail_subject" in kinds


def test_발송_화면에_제목_고르개가_그려진다(logged, db, users):
    """브라우저 검사가 세우는 아이디와 **실제 화면**이 같아야 한다.

    같지 않으면 브라우저 검사는 없는 화면 위에서 조용히 통과한다
    (`tests/js/_deals_dom.js` 머리말의 뜻).
    """
    html = logged.get("/deals").text
    for anchor in ('id="mail-subject"', 'id="mail-subject-tpl"',
                   'id="mail-subject-tpl-wrap"', 'id="mail-subject-none"'):
        assert anchor in html, f"발송 화면에 {anchor} 가 없다"
    # 제목 칸과 고르개는 **한 줄**에 선다.
    assert 'class="mail-subject-row"' in html
    css = (ROOT / "app" / "static" / "css" / "app.css").read_text(encoding="utf-8")
    assert ".mail-subject-row" in css, "한 줄로 세우는 규칙이 없다"
    # 390px 폰에서 화면이 옆으로 밀리지 않으려면 둘 다 있어야 한다.
    assert "flex-wrap: wrap" in css.split(".mail-subject-row")[1].split("}")[0]
    assert "min-width: 0" in css.split(".mail-subject-row .field")[1].split("}")[0]


# ── 고르는 손은 브라우저에 있다 ────────────────────────────────────────────

def test_고르면_제목_칸을_채운다_브라우저():
    """★ 고른 것을 그대로 보내지 않고 **칸에 채운다** — 그 뒤 손볼 수 있다."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("node 미설치 — 브라우저 로직 테스트 생략 "
                    "(호스트에서 `node tests/js/mail_subject_pick_test.js`)")
    js = Path(__file__).resolve().parent / "js" / "mail_subject_pick_test.js"
    result = subprocess.run([node, str(js)], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
