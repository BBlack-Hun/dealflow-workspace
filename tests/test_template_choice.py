"""문구를 **사람마다 골라 쓴다** — 고른 것이 실제로 나가는가.

팀 기본 문구는 한 종류에 여러 개 둘 수 있다(딜 소싱 제안은 갈래마다 하나씩
다섯 개다). 예전에는 그중 `.first()` 로 아무거나 집었다. 정렬 없는 조회의
순서는 DB 가 정하는 것이라 **같은 회차에서 사람마다 다른 문구가 나갈 수**
있었고, 무엇이 나갔는지 뒤에서 알 방법도 없었다.

여기서 못 박는 것은 다섯 가지다.

  ① 고른 문구가 실제 미리보기·발송에 나온다
  ② 두 사람이 서로 다른 것을 골랐으면 각자 다른 문구가 나간다
  ③ 아무것도 안 고른 사람에게도 문구는 나온다(빈 문구로 나가면 사고다)
  ④ 고른 문구가 지워지면 선택이 정리되고, 그래도 문구는 나온다
  ⑤ 딜 소싱은 갈래 매칭이 먼저다 — 갈래가 어긋난 문구는 결례가 된다
"""
from __future__ import annotations

import pathlib
import re

import pytest
from markupsafe import escape

from .conftest import DEMO_PASSWORD

TEAM_A = "가 문구입니다. 팀 기본 첫 번째."
TEAM_B = "나 문구입니다. 팀 기본 두 번째."
KIND = "closing_day1"


def _login(client, phone: str):
    client.post("/login", data={"phone": phone, "password": DEMO_PASSWORD})
    return client


@pytest.fixture()
def two_team_defaults(client, db, users):
    """한 종류에 팀 기본 문구가 둘 — 고르지 않으면 무엇이 나갈지 모르는 상태."""
    from app.models import MessageTemplate

    a = MessageTemplate(user_id=None, kind=KIND, name="가", body=TEAM_A, is_active=1)
    b = MessageTemplate(user_id=None, kind=KIND, name="나", body=TEAM_B, is_active=1)
    db.add_all([a, b])
    db.commit()
    return {"a": a.id, "b": b.id}


@pytest.fixture()
def contact(db, users):
    """u1·u2 각자의 담당자. 미리보기는 자기 담당자만 부를 수 있다."""
    from app.models import VcContact

    rows = {}
    for key, who in (("u1", "홍길동"), ("u2", "김서연")):
        c = VcContact(user_id=users[key].id, name=who, title="심사역",
                      firm="가나벤처스", kakao_room_name=f"{who} 방",
                      room_verified="verified")
        db.add(c)
        db.commit()
        rows[key] = c.id
    return rows


@pytest.fixture()
def company(db):
    from app.models import IrCompany

    c = IrCompany(name="샘플애그", sector_major="애그테크", series="Seed",
                  one_liner="B2B 농산물 선도거래 플랫폼", summary="요약문",
                  summary_status="done", revenue_recent=12)
    db.add(c)
    db.commit()
    return c.id


def _preview(client, contact_id: int, company_id: int) -> str:
    r = client.post("/api/deals/preview", json={
        "company_ids": [company_id], "contact_ids": [contact_id]})
    assert r.status_code == 200, r.text
    return r.json()["previews"][0]["message"]


# --- ① 고른 것이 나간다 ---------------------------------------------------

def test_고른_문구가_실제_발송_문구에_들어간다(client, db, users, two_team_defaults,
                                       contact, company):
    """골라 뒀는데 다른 것이 나가면 고른 뜻이 없다."""
    _login(client, "01000000001")
    r = client.post("/templates/choose",
                    data={"kind": KIND, "template_id": two_team_defaults["b"]},
                    follow_redirects=False)
    assert r.status_code == 303, r.text
    assert TEAM_B in _preview(client, contact["u1"], company)


def test_고르기_전에는_빈_문구가_아니라_기본_안내가_나간다(client, db, users,
                                                two_team_defaults, contact, company):
    """팀 기본이 여럿이라 못 고르는 상태여도 **문구는 나와야 한다.**

    문구가 비어 나가면 받는 쪽에는 빈 말풍선이 뜬다. 아무거나 집는 것도
    안 되지만(사람마다 달라진다), 비우는 것은 더 나쁘다 — 코드에 적힌
    같은 한 문장이 나간다.
    """
    _login(client, "01000000001")
    text = _preview(client, contact["u1"], company)
    # 팀 기본 둘 중 아무거나 집지 않는다
    assert TEAM_A not in text and TEAM_B not in text
    assert "핵심 딜" in text          # 코드에 적힌 폴백


# --- ② 사람마다 다른 문구 -------------------------------------------------

def test_두_사람이_서로_다른_팀_기본을_고르면_각자_다른_문구가_나간다(
        client, db, users, two_team_defaults, contact, company):
    """이 기능의 전부다. 선택이 사람에게 묶이지 않으면 서로의 문구를 덮어쓴다."""
    _login(client, "01000000001")
    client.post("/templates/choose",
                data={"kind": KIND, "template_id": two_team_defaults["a"]})
    first = _preview(client, contact["u1"], company)

    _login(client, "01000000002")
    client.post("/templates/choose",
                data={"kind": KIND, "template_id": two_team_defaults["b"]})
    second = _preview(client, contact["u2"], company)

    assert TEAM_A in first and TEAM_B not in first
    assert TEAM_B in second and TEAM_A not in second


def test_남이_고쳐도_내_선택은_그대로다(client, db, users, two_team_defaults,
                                  contact, company):
    """u2 가 자기 것을 고른다고 u1 의 선택이 따라 바뀌면 안 된다."""
    from app.models import TemplateChoice

    _login(client, "01000000001")
    client.post("/templates/choose",
                data={"kind": KIND, "template_id": two_team_defaults["a"]})
    _login(client, "01000000002")
    client.post("/templates/choose",
                data={"kind": KIND, "template_id": two_team_defaults["b"]})

    db.expire_all()
    rows = {c.user_id: c.template_id for c in db.query(TemplateChoice).all()}
    assert rows == {users["u1"].id: two_team_defaults["a"],
                    users["u2"].id: two_team_defaults["b"]}


def test_남의_개인_문구는_고를_수_없다(client, db, users, contact, company):
    """남이 고칠 때마다 내 발송이 따라 바뀌고, 남이 지우면 내 선택이 사라진다."""
    from app.models import MessageTemplate

    theirs = MessageTemplate(user_id=users["u2"].id, kind=KIND, name="남의 것",
                             body="남의 개인 문구", is_active=1)
    db.add(theirs)
    db.commit()

    _login(client, "01000000001")
    r = client.post("/templates/choose", data={"kind": KIND, "template_id": theirs.id})
    assert r.status_code == 400


# --- ③ 아무것도 안 고른 사람 ---------------------------------------------

def test_아무것도_안_골라도_팀_기본이_하나면_그것이_나간다(client, db, users,
                                                contact, company):
    """고를 것이 하나뿐이면 고르라고 물을 이유가 없다 — 예전 동작 그대로."""
    from app.models import MessageTemplate

    db.add(MessageTemplate(user_id=None, kind=KIND, body=TEAM_A, is_active=1))
    db.commit()
    _login(client, "01000000001")
    assert TEAM_A in _preview(client, contact["u1"], company)


def test_내_문구가_있으면_고르지_않아도_내_것이_나간다(client, db, users,
                                            two_team_defaults, contact, company):
    """자기가 만든 것을 두고 팀 기본이 나가면 왜 만들었는지 알 수 없다."""
    from app.models import MessageTemplate

    db.add(MessageTemplate(user_id=users["u1"].id, kind=KIND, name="내 것",
                           body="내가 쓴 안내문입니다.", is_active=1))
    db.commit()
    _login(client, "01000000001")
    assert "내가 쓴 안내문입니다." in _preview(client, contact["u1"], company)


# --- ④ 지워지면 정리된다 --------------------------------------------------

def test_고른_문구를_지우면_선택도_함께_사라지고_문구는_그대로_나온다(
        client, db, users, contact, company):
    """없는 문구를 가리킨 선택이 남으면 '골라 뒀는데 다른 것이 나간다'."""
    from app.models import MessageTemplate, TemplateChoice

    mine = MessageTemplate(user_id=users["u1"].id, kind=KIND, name="내 것",
                           body="내가 쓴 안내문입니다.", is_active=1)
    team = MessageTemplate(user_id=None, kind=KIND, body=TEAM_A, is_active=1)
    db.add_all([mine, team])
    db.commit()
    mine_id = mine.id

    _login(client, "01000000001")
    client.post("/templates/choose", data={"kind": KIND, "template_id": mine_id})
    db.expire_all()
    assert db.query(TemplateChoice).filter_by(template_id=mine_id).count() == 1

    r = client.post(f"/templates/{mine_id}/delete", follow_redirects=False)
    assert r.status_code == 303, r.text
    db.expire_all()
    assert db.query(TemplateChoice).filter_by(template_id=mine_id).count() == 0
    # 문구는 계속 나온다 — 남은 팀 기본으로 되돌아간다
    assert TEAM_A in _preview(client, contact["u1"], company)


def test_꺼진_문구를_가리키는_선택은_화면을_열_때_치워진다(client, db, users):
    """지우는 길이 화면 말고도 있다(시드 스크립트·손질). 남겨 두면 화면에는
    '고름' 인데 실제로는 다른 문구가 나가는 상태가 이어진다."""
    from app.models import MessageTemplate, TemplateChoice

    a = MessageTemplate(user_id=None, kind=KIND, name="가", body=TEAM_A, is_active=1)
    db.add(a)
    db.commit()
    db.add(TemplateChoice(user_id=users["u1"].id, kind=KIND, variant="",
                          template_id=a.id))
    a.is_active = 0
    db.commit()

    _login(client, "01000000001")
    assert client.get("/templates").status_code == 200
    db.expire_all()
    assert db.query(TemplateChoice).count() == 0


# --- ⑤ 딜 소싱은 갈래가 먼저 ---------------------------------------------

BUCKETS = ("시리즈 A 이상", "M&A 찾는 투자사")


@pytest.fixture()
def sourcing(client, db, users):
    """갈래가 둘, 갈래마다 팀 기본 문구가 하나씩."""
    from app.models import MessageTemplate, SourcingContact

    rows = {}
    for pos, bucket in enumerate(BUCKETS):
        c = SourcingContact(bucket=bucket, position=pos, name=f"담당자{pos}",
                            title="심사역", firm="가나벤처스")
        db.add(c)
        db.add(MessageTemplate(user_id=None, kind="sourcing_intro", name=bucket,
                               body=f"[{bucket}] 갈래 문구입니다.", is_active=1))
        db.commit()
        rows[bucket] = c.id
    return rows


def _sourcing_message(client, contact_id: int) -> str:
    r = client.post("/api/deals/preview",
                    json={"contact_ids": [contact_id], "mode": "sourcing"})
    assert r.status_code == 200, r.text
    return r.json()["previews"][0]["message"]


def test_소싱은_갈래에_맞는_문구가_나간다(client, db, users, sourcing):
    """'대표님·5개사' 를 개인 참여 심사역께 보내면 문구 자체가 결례가 된다."""
    _login(client, "01000000001")
    for bucket, cid in sourcing.items():
        text = _sourcing_message(client, cid)
        assert f"[{bucket}] 갈래 문구입니다." in text, bucket


def test_같은_갈래_안에_팀_기본이_둘이면_고른_것이_나간다(client, db, users, sourcing):
    """갈래 매칭이 먼저고, **그 안에서** 기본/내 문구 선택이 적용된다."""
    from app.models import MessageTemplate

    bucket = BUCKETS[0]
    second = MessageTemplate(user_id=None, kind="sourcing_intro", name=bucket,
                             body=f"[{bucket}] 두 번째 갈래 문구입니다.", is_active=1)
    db.add(second)
    db.commit()

    _login(client, "01000000001")
    client.post("/templates/choose",
                data={"kind": "sourcing_intro", "template_id": second.id})
    text = _sourcing_message(client, sourcing[bucket])
    assert "두 번째 갈래 문구입니다." in text
    # 다른 갈래는 제 문구를 그대로 쓴다 — 선택이 갈래를 넘어가면 안 된다
    other = BUCKETS[1]
    assert f"[{other}] 갈래 문구입니다." in _sourcing_message(client, sourcing[other])


def test_소싱_문구를_복사하면_갈래_이름을_그대로_가져간다(client, db, users, sourcing):
    """이름이 곧 갈래다 — 이름이 바뀌면 그 갈래에서 영영 쓰이지 않는다."""
    from app.models import MessageTemplate

    bucket = BUCKETS[0]
    src = db.query(MessageTemplate).filter_by(name=bucket).one()
    _login(client, "01000000001")
    r = client.post("/templates/copy", data={"template_id": src.id},
                    follow_redirects=False)
    assert r.status_code == 303, r.text

    db.expire_all()
    mine = db.query(MessageTemplate).filter_by(user_id=users["u1"].id).one()
    assert mine.name == bucket
    assert mine.body == src.body


# --- 화면 -----------------------------------------------------------------

def _deals_tab_order() -> list:
    """발송 화면의 탭 순서. 두 화면의 순서가 다르면 매번 헤맨다."""
    html = pathlib.Path("app/templates/deals.html").read_text(encoding="utf-8")
    block = html[html.index('id="mode-tabs"'):]
    return re.findall(r'data-mode="(\w+)"', block[:block.index("</div>")])


def test_문구_화면의_구간이_발송_화면의_탭과_같은_순서다(logged_in):
    """같은 것을 두 화면에서 찾는데 순서가 다르면 매번 헤맨다."""
    from app.routers.deals import MODE_TEMPLATE_KIND

    body = logged_in.get("/templates").text
    order = _deals_tab_order()
    assert set(order) == set(MODE_TEMPLATE_KIND), "탭 집합이 어긋난다"
    at = [body.index('id="%s"' % MODE_TEMPLATE_KIND[mode]) for mode in order]
    assert at == sorted(at), "문구 화면 구간 순서가 발송 화면 탭 순서와 다르다"


def test_탭에_안_걸린_문구는_접혀_있되_사라지지는_않는다(logged_in):
    """인사말·전화·문자·메일 제목은 탭에서 고르지 않지만 쓰이는 곳이 있다.

    통째로 안 그리면 없어진 줄 알고 같은 문구를 또 만든다. 접어 두면
    "여기 있다"는 것은 보이면서 탭 고르기를 가리지 않는다.
    """
    body = logged_in.get("/templates").text
    for kind in ("opening_first", "opening_re", "connect_call", "mail_subject"):
        assert 'id="%s"' % kind in body, kind
    assert "그 밖의 문구" in body
    # 기본은 접힌 상태다 — 펴진 채로 두면 탭 구간이 뒤로 밀린다
    assert '<details id="others">' in body
    assert '<details id="others" open' not in body


def test_합쳐진_미리보기는_발송이_쓰는_그_함수를_지난다(logged_in, db, users):
    """화면 쪽에서 다시 합치면 두 벌이 되고, 두 벌은 반드시 어긋난다.

    조각(인사말/안내문)만 보여 주던 때는 최종 문구가 어떻게 생겼는지 알 수
    없었다.
    """
    from app.routers import deals

    body = logged_in.get("/templates").text
    for mode in ("deal", "remind", "meeting", "review", "ask"):
        expected = deals.sample_message(db, users["u1"], mode)
        assert str(escape(expected)) in body, mode


def test_선호_분야_묻기에는_인사말이_붙지_않는다(logged_in, db, users):
    """이미 대화가 오간 방에 한 줄만 덧붙이는 것이라 다시 인사하면 어색하다."""
    from app.routers import deals

    assert deals.opening_is_included("ask") is False
    text = deals.sample_message(db, users["u1"], "ask")
    assert "안녕하세요" not in text
    assert "안녕하세요" in deals.sample_message(db, users["u1"], "remind")


def test_미리보기의_받는_사람은_가상의_사람이다(logged_in, db, users):
    """진짜 이름이 보이면 그 사람에게 갈 문구로 읽힌다."""
    from app.models import VcContact

    db.add(VcContact(user_id=users["u1"].id, name="홍길동", title="심사역",
                     firm="가나벤처스"))
    db.commit()
    text = logged_in.get("/templates").text
    section = text[text.index('id="closing_day1"'):]
    assert "○○○" in section[:2000]


def test_고를_것이_하나뿐이면_선택기를_띄우지_않는다(logged_in, db):
    """고를 것이 없는데 라디오만 늘어서면 무엇을 하는 화면인지 흐려진다.
    대신 '기본 문구를 복사해 내 문구 만들기' 가 보여야 한다."""
    from app.models import MessageTemplate

    db.add(MessageTemplate(user_id=None, kind=KIND, body=TEAM_A, is_active=1))
    db.commit()
    body = logged_in.get("/templates").text
    section = body[body.index('id="closing_day1"'):]
    section = section[:section.index('<details')]
    assert "이 문구로 정하기" not in section
    assert "기본 문구를 복사해 내 문구 만들기" in section


def test_지금_고른_문구가_화면에_드러난다(client, db, users, two_team_defaults):
    """무엇을 골랐는지 보이지 않으면 고른 적이 있는지도 알 수 없다."""
    _login(client, "01000000001")
    client.post("/templates/choose",
                data={"kind": KIND, "template_id": two_team_defaults["b"]})
    body = client.get("/templates").text
    assert "내가 고른 문구" in body
    # 라디오에도 지금 고른 것이 찍혀 있어야 한다 — 목록만 보여 주면
    # 고르러 들어왔다가 무엇이 켜져 있는지 몰라 또 고르게 된다.
    flat = re.sub(r"\s+", " ", body)
    assert 'value="%d" checked' % two_team_defaults["b"] in flat
    assert 'value="%d" checked' % two_team_defaults["a"] not in flat


def test_팀_기본은_여전히_관리자만_고친다(client, db, users, two_team_defaults):
    """고르는 것과 고치는 것은 다른 권한이다 — 고를 수 있게 됐다고 해서
    팀 기본을 아무나 고치면 같은 회차에서 남의 문구까지 바뀐다."""
    _login(client, "01000000001")
    body = client.get("/templates").text
    assert "팀 기본 문구입니다 — 관리자만 수정할 수 있습니다." in body
    r = client.post(f"/templates/{two_team_defaults['a']}/edit",
                    data={"name": "가", "body": "몰래 고침"}, follow_redirects=False)
    assert r.status_code == 403


def test_복사한_내_문구는_본인이_고칠_수_있다(client, db, users, two_team_defaults):
    """팀 기본을 못 고치는 대신 제 것을 만들어 고친다 — 그게 '내 문구' 다."""
    from app.models import MessageTemplate

    _login(client, "01000000001")
    client.post("/templates/copy", data={"template_id": two_team_defaults["a"]})
    db.expire_all()
    mine = db.query(MessageTemplate).filter_by(user_id=users["u1"].id).one()
    assert mine.body == TEAM_A          # 빈 칸이 아니라 지금 나가는 문구가 들어 있다

    r = client.post(f"/templates/{mine.id}/edit",
                    data={"name": "내 문구", "body": "내가 고친 문구입니다."},
                    follow_redirects=False)
    assert r.status_code == 303
    db.expire_all()
    assert db.get(MessageTemplate, mine.id).body == "내가 고친 문구입니다."


def test_복사하면_곧바로_그것을_고른_상태가_된다(client, db, users, two_team_defaults,
                                       contact, company):
    """만들어 놓고 고르지 않으면 왜 내 문구가 안 나가는지 알 수 없다."""
    from app.models import MessageTemplate

    _login(client, "01000000001")
    client.post("/templates/copy", data={"template_id": two_team_defaults["a"]})
    db.expire_all()
    mine = db.query(MessageTemplate).filter_by(user_id=users["u1"].id).one()
    mine.body = "복사한 뒤 고친 문구입니다."
    db.commit()
    assert "복사한 뒤 고친 문구입니다." in _preview(client, contact["u1"], company)


def test_갈래가_있는_종류는_한_곳에만_적혀_있다():
    """딜 소싱의 이름이 갈래라는 사실이 두 곳에 적히면 언젠가 어긋난다."""
    from app.services import sourcing_msg, template_pick

    assert sourcing_msg.KIND in template_pick.NAME_IS_A_BUCKET
