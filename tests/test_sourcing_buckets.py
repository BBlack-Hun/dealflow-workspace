"""딜 소싱 갈래 — 고른 갈래로 미리보기가 따라오고, 이름을 바꾸면 줄이 따라간다.

여기서 못 박는 것.

  ① 갈래를 고르면 **그 갈래 문구**가 미리보기에 온다(고르기 전 기본 문구에서도)
  ② 사람을 고른 뒤에는 **그 사람의 갈래**가 이긴다 — 화면이 보낸 값이 이기면
     M&A 명단에게 시리즈 A 문구가 나간다
  ③ 갈래 이름을 바꾸면 **사람 · 문구 · 골라 둔 것이 함께 따라간다**
     (한 곳만 바뀌면 옛 이름의 유령 탭이 남는다 — 0039 가 되돌린 그 사고)
  ④ 이미 쓰고 있는 이름으로는 바꾸지 않는다

이름은 전부 가상값이다(공개 저장소).
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from .conftest import DEMO_PASSWORD

BUCKET_PREVIEW_JS = (Path(__file__).resolve().parent
                     / "js" / "sourcing_bucket_preview_test.js")

SERIES_A = "시리즈 A 이상 딜소싱 참여 심사역"
MNA = "M&A 찾는 투자사"
CEO = "딜 소싱 참여 투자사 대표"


def _login(client, phone: str = "01000000001"):
    client.post("/login", data={"phone": phone, "password": DEMO_PASSWORD})
    return client


@pytest.fixture()
def buckets(client, db, users):
    """갈래 셋, 갈래마다 사람 하나와 팀 기본 문구 하나."""
    from app.models import MessageTemplate, SourcingContact

    made = {}
    for pos, bucket in enumerate((SERIES_A, MNA, CEO)):
        row = SourcingContact(bucket=bucket, position=pos * 1000,
                              name=f"담당자{pos}", title="심사역", firm="가나벤처스",
                              kakao_room_name=f"방{pos}")
        db.add(row)
        db.add(MessageTemplate(user_id=None, kind="sourcing_intro", name=bucket,
                               body=f"[{bucket}] 갈래 문구입니다.", is_active=1))
        db.commit()
        made[bucket] = row.id
    return made


def _preview(client, **body):
    r = client.post("/api/deals/preview",
                    json=dict({"contact_ids": [], "mode": "sourcing"}, **body))
    assert r.status_code == 200, r.text
    return r.json()["previews"][0]["message"]


# --- ① · ② 갈래를 고르면 그 갈래 미리보기 ------------------------------------

def test_picking_a_bucket_shows_that_buckets_message(client, db, users, buckets):
    """갈래를 누르면 그 갈래 문구가 떠야 한다.

    고치기 전에는 갈래를 눌러도 **늘 첫 갈래**의 문구가 떴다 — M&A 를 골라
    놓고 시리즈 A 문구를 보며 발송을 누르게 된다.
    """
    _login(client)
    for bucket in (SERIES_A, MNA, CEO):
        assert f"[{bucket}] 갈래 문구입니다." in _preview(client, bucket=bucket), bucket


def test_without_a_bucket_the_first_one_is_shown(client, db, users, buckets):
    """아무 갈래도 안 고른 상태는 전과 같다 — 첫 갈래."""
    _login(client)
    assert f"[{SERIES_A}] 갈래 문구입니다." in _preview(client)


def test_a_chosen_person_beats_the_screens_bucket(client, db, users, buckets):
    """사람을 고른 뒤에는 **그 사람의 갈래**가 이긴다.

    화면이 보낸 값이 이기면, M&A 명단을 체크해 놓고 갈래 칩이 시리즈 A 에
    있을 때 그 사람에게 시리즈 A 문구가 나간다.
    """
    _login(client)
    text = _preview(client, contact_ids=[buckets[MNA]], bucket=SERIES_A)
    assert f"[{MNA}] 갈래 문구입니다." in text
    assert SERIES_A not in text


# --- ③ 이름을 바꾸면 줄이 따라간다 -------------------------------------------

def test_renaming_takes_the_rows_with_it(client, db, users, buckets):
    """사람 · 문구 · 골라 둔 것이 **함께** 옮겨간다."""
    from app.models import (MessageTemplate, SourcingContact, TemplateChoice,
                            User)
    from app.services import sourcing_buckets, template_pick

    _login(client)
    user_id = db.query(User).filter_by(phone="01000000001").one().id
    tpl = db.query(MessageTemplate).filter_by(kind="sourcing_intro",
                                              name=MNA).one()
    template_pick.set_choice(db, user_id, "sourcing_intro", tpl.id, variant=MNA)
    db.commit()

    after = "M&A · 세컨더리 찾는 투자사"
    moved = sourcing_buckets.rename(db, MNA, after)
    db.commit()

    assert moved == 1
    assert db.query(SourcingContact).filter_by(bucket=MNA).count() == 0
    assert db.query(SourcingContact).filter_by(bucket=after).count() == 1
    assert db.query(MessageTemplate).filter_by(kind="sourcing_intro",
                                               name=MNA).count() == 0
    assert db.query(MessageTemplate).filter_by(kind="sourcing_intro",
                                               name=after).count() == 1
    assert db.query(TemplateChoice).filter_by(kind="sourcing_intro",
                                              variant=MNA).count() == 0
    assert db.query(TemplateChoice).filter_by(kind="sourcing_intro",
                                              variant=after).count() == 1


def test_the_message_follows_the_new_name(client, db, users, buckets):
    """이름을 바꾼 뒤에도 **그 갈래 문구가 그대로 나간다.**

    문구를 두고 가면 새 이름 갈래는 문구 없는 갈래가 되어 뼈대 문구로 나간다 —
    호칭·개수·범위가 갈래마다 다르니 그건 결례가 되는 문구다.
    """
    from app.services import sourcing_buckets

    _login(client)
    after = "M&A · 세컨더리 찾는 투자사"
    sourcing_buckets.rename(db, MNA, after)
    db.commit()

    text = _preview(client, contact_ids=[buckets[MNA]])
    assert f"[{MNA}] 갈래 문구입니다." in text     # 문구 본문은 그대로 따라왔다
    assert f"[{after}] 갈래 문구입니다." not in text


def test_the_tab_is_reachable_under_the_new_name(client, db, users, buckets):
    """화면에서도 새 이름 탭 하나만 남는다 — 옛 이름 유령 탭이 없다."""
    from app.services import sourcing_buckets
    from app.routers.sourcing import buckets as bucket_rows

    _login(client)
    after = "M&A · 세컨더리 찾는 투자사"
    sourcing_buckets.rename(db, MNA, after)
    db.commit()

    keys = [b["key"] for b in bucket_rows(db)]
    assert after in keys
    assert MNA not in keys
    assert len(keys) == 3


def test_rename_through_the_screen(client, db, users, buckets):
    """화면의 [이름 저장] 이 실제로 옮긴다 — 투자사 명단과 같은 폼 방식."""
    from app.models import SourcingContact

    _login(client)
    after = "개인 참여 심사역"
    r = client.post("/sourcing/buckets/rename",
                    data={"old": CEO, "new": after}, follow_redirects=False)
    assert r.status_code == 303
    assert db.query(SourcingContact).filter_by(bucket=after).count() == 1
    assert db.query(SourcingContact).filter_by(bucket=CEO).count() == 0


# --- ④ 막아야 하는 것 --------------------------------------------------------

def test_cannot_rename_onto_an_existing_bucket(client, db, users, buckets):
    """이미 쓰고 있는 이름으로 바꾸면 두 갈래가 한 덩어리가 된다 — 막는다."""
    from app.services import sourcing_buckets

    with pytest.raises(sourcing_buckets.RenameError):
        sourcing_buckets.rename(db, MNA, SERIES_A)


def test_cannot_rename_onto_a_name_only_a_template_holds(client, db, users, buckets):
    """사람이 없어도 **문구가 쥐고 있는 이름**이면 막는다.

    골라 둔 것에는 (사람 · 종류 · 갈래) 유일 조건이 있어, 그대로 밀면 옮기다
    말고 터진다. 옮기기 전에 막는 편이 낫다.
    """
    from app.models import MessageTemplate
    from app.services import sourcing_buckets

    db.add(MessageTemplate(user_id=None, kind="sourcing_intro",
                           name="빈 갈래", body="문구만 남아 있다", is_active=1))
    db.commit()
    with pytest.raises(sourcing_buckets.RenameError):
        sourcing_buckets.rename(db, MNA, "빈 갈래")


def test_renaming_to_the_same_name_does_nothing(client, db, users, buckets):
    from app.services import sourcing_buckets

    assert sourcing_buckets.rename(db, MNA, MNA) == 0
    assert sourcing_buckets.rename(db, MNA, "   ") == 0


def test_spacing_inside_the_name_is_kept(client, db, users, buckets):
    """가운데 두 칸 공백은 원본 시트 그대로다 — 다듬으면 줄과 어긋난다."""
    from app.services import sourcing_buckets

    assert sourcing_buckets.normalize_label("  딜 소싱  참여 투자사 대표 ") == \
        "딜 소싱  참여 투자사 대표"


# --- ① 의 화면 쪽 절반 -------------------------------------------------------
#
# 위의 검사들은 **서버가 갈래를 받으면 그 문구를 준다**까지다. 화면이 그 갈래를
# 실어 보내지 않으면 서버는 물어본 적조차 없는 셈이라, 이음새를 따로 본다.

def test_the_screen_sends_the_picked_bucket():
    """갈래 칩을 누르면 미리보기를 다시 부르고, 누른 갈래를 함께 보낸다.

    조작이 브라우저에 있으므로 검사도 같은 언어로 둔다(`tests/js`). deals.js 를
    가짜 화면 위에서 **그대로 실행**한다 — 규칙을 옮겨 적으면 두 벌이 되어
    어긋나도 모른다.
    """
    node = shutil.which("node")
    if node is None:
        pytest.skip("node 미설치 — 브라우저 로직 테스트 생략 "
                    "(호스트에서 `node tests/js/sourcing_bucket_preview_test.js`)")
    result = subprocess.run([node, str(BUCKET_PREVIEW_JS)],
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
