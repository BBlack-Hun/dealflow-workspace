"""IR 자료 폴더 자리를 **누가 정하고, 어떻게 발송기에 닿는가.**

자료 파일은 각자 PC 안에 있고, 그 자리는 PC 마다 다르다. 그래서 값은
**그 PC 를 쓰는 본인이 웹에서 넣고**, 발송기가 박동 응답으로 받아 간다.

`config.yaml` 에 적지 않는 이유: 발송기를 새로 내려받으면 서버가 config 를
즉석에서 다시 만들어(`CONFIG_TEMPLATE`) 손으로 적은 값이 데모 값으로 되돌아간다.

여기가 보는 것은 **값이 오가는 길**이다. 그 길에 서기 전에 관리자가 이 계정에
자동 첨부를 켜 주어야 한다(0059) — **켜고 끄는 자리 자체**는
`tests/test_ir_auto_attach_access.py` 가 본다.
"""
from __future__ import annotations

import pytest

from .conftest import DEMO_PASSWORD, DEMO_TOKEN, OTHER_TOKEN, auth

# 실제 경로를 적지 않는다 — 이 저장소는 공개다.
MY_FOLDER = "/Users/tester/Share/자료폴더"
OTHER_FOLDER = "/Users/other/Documents/자료"


@pytest.fixture(autouse=True)
def auto_attach_allowed(db, users):
    """이 파일의 전제 — 두 계정 다 자동 첨부를 **쓸 수 있는 계정**이다.

    이 칸이 꺼져 있으면 자료 폴더 칸이 화면에 그려지지도, 저장 라우터가 값을
    받지도 않는다(`deps.may_auto_attach`). 그 판정을 확인하는 것은 이 파일의
    일이 아니라 `tests/test_ir_auto_attach_access.py` 의 일이라, 여기서는 켜
    두고 **값이 오가는 길**만 본다.
    """
    users["u1"].can_auto_attach_ir = 1
    users["u2"].can_auto_attach_ir = 1
    db.commit()


def _device(db, user_id):
    from app.models import AgentDevice

    return db.query(AgentDevice).filter_by(user_id=user_id).first()


def test_i_set_my_own_folder(logged_in, db, users):
    r = logged_in.post("/setup/ir-root", data={"ir_root": MY_FOLDER},
                       follow_redirects=False)
    assert r.status_code == 303
    assert _device(db, users["u1"].id).ir_root == MY_FOLDER


def test_the_screen_shows_what_is_saved(logged_in, db, users):
    logged_in.post("/setup/ir-root", data={"ir_root": MY_FOLDER})
    assert MY_FOLDER in logged_in.get("/setup").text


def test_clearing_it_forgets_the_folder(logged_in, db, users):
    """지우면 발송기도 잊는다 — 낡은 자리를 계속 뒤지면 안 된다."""
    logged_in.post("/setup/ir-root", data={"ir_root": MY_FOLDER})
    logged_in.post("/setup/ir-root", data={"ir_root": "   "})
    assert _device(db, users["u1"].id).ir_root is None


def test_surrounding_spaces_are_trimmed(logged_in, db, users):
    """복사·붙여넣기로 앞뒤 공백이 딸려 오는 일이 잦다."""
    logged_in.post("/setup/ir-root", data={"ir_root": f"  {MY_FOLDER}  "})
    assert _device(db, users["u1"].id).ir_root == MY_FOLDER


def test_nobody_sets_it_for_somebody_else(client, db, users):
    """★ 본인만 넣는다.

    그 PC 앞에 앉은 사람만 그 경로가 맞는지 안다. 남이 대신 넣으면 틀린 자리를
    뒤지다 실패하는데, 정작 본인은 자기가 넣지도 않은 값 때문에 막힌 줄 모른다.
    그래서 이 길에는 **대상 사용자를 받는 자리가 아예 없다.**
    """
    from app.models import AgentDevice

    db.add(AgentDevice(user_id=users["u1"].id, token="agt_u1_extra",
                       ir_root=MY_FOLDER)) if not _device(db, users["u1"].id) else None
    device = _device(db, users["u1"].id)
    device.ir_root = MY_FOLDER
    db.commit()

    # u2 로 로그인해 남의 값을 노려 본다.
    client.post("/login", data={"phone": "01000000002", "password": DEMO_PASSWORD})
    client.post("/setup/ir-root",
                data={"ir_root": OTHER_FOLDER, "user_id": users["u1"].id})

    db.expire_all()
    assert _device(db, users["u1"].id).ir_root == MY_FOLDER, "남의 자리가 바뀌었다"
    assert _device(db, users["u2"].id).ir_root == OTHER_FOLDER


def test_a_logged_out_visitor_cannot_set_it(client, db, users):
    r = client.post("/setup/ir-root", data={"ir_root": MY_FOLDER},
                    follow_redirects=False)
    assert r.status_code in (302, 303, 401, 403)
    assert "/login" in r.headers.get("location", "")
    assert _device(db, users["u1"].id).ir_root is None, "로그인도 안 했는데 값이 들어갔다"


# ── 발송기가 받아 가는 길 (새 통로를 파지 않는다) ──────────────────────────

def test_the_agent_gets_it_on_the_heartbeat(client, db, users):
    """★ 이미 두드리고 있는 통로에 얹었다 — 화면에서 고치면 다음 박동에 따라간다."""
    device = _device(db, users["u1"].id)
    device.ir_root = MY_FOLDER
    db.commit()

    r = client.post("/api/agent/heartbeat", json={"hostname": "mac-test"},
                    headers=auth(DEMO_TOKEN))
    assert r.status_code == 200
    assert r.json()["ir_root"] == MY_FOLDER


def test_an_unset_folder_comes_back_empty(client, db, users):
    r = client.post("/api/agent/heartbeat", json={"hostname": "mac-test"},
                    headers=auth(DEMO_TOKEN))
    assert r.json()["ir_root"] == ""


def test_one_agent_never_sees_another_persons_folder(client, db, users):
    """연결키는 **내 것만** 받아오는 열쇠다."""
    _device(db, users["u1"].id).ir_root = MY_FOLDER
    _device(db, users["u2"].id).ir_root = OTHER_FOLDER
    db.commit()

    mine = client.post("/api/agent/heartbeat", json={}, headers=auth(DEMO_TOKEN))
    theirs = client.post("/api/agent/heartbeat", json={}, headers=auth(OTHER_TOKEN))
    assert mine.json()["ir_root"] == MY_FOLDER
    assert theirs.json()["ir_root"] == OTHER_FOLDER


def test_the_folder_is_not_baked_into_the_downloaded_config(logged_in, db, users):
    """★ config.yaml 에 넣지 않는다.

    발송기를 새로 내려받으면 서버가 config 를 다시 만든다. 거기에 값을 박아 두면
    그때마다 되돌아가고, 사람은 예전 값이 살아 있다고 생각한다.
    """
    import io
    import zipfile

    _device(db, users["u1"].id).ir_root = MY_FOLDER
    db.commit()

    body = logged_in.get("/download/agent?os_kind=mac").content
    with zipfile.ZipFile(io.BytesIO(body)) as zf:
        config = zf.read("agent/config.yaml").decode("utf-8")
    assert MY_FOLDER not in config
    assert "ir_root:" not in config
