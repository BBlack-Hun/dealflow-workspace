"""IR 자료 전달의 번호는 **딜 소개의 번호와 같아야 한다.**

딜 소개 문구는 `1) …` `2) …` 로 나가고 투자사는 그 번호로 기억해서 답한다
("2번, 3번 자료 주세요"). 자료를 보낼 때 다른 번호로 짚으면 서로 다른 기업
이야기를 한다 — 받는 쪽은 자기 목록에서 찾다가 못 찾는다.

## 고치기 전에 실제로 나오던 값

기업 셋을 **거꾸로** 골라 딜 소개를 보낸다(마바로보 → 가나애그 → 다라헬스).
문구는 `1) 마바로보  2) 가나애그  3) 다라헬스` 로 나갔다. 그 뒤 가나애그·
다라헬스 자료를 보내려 할 때 번호는 이랬다.

    딜 소개 직후          2번 가나애그 · 3번 다라헬스     ← 맞았다
    리마인드를 한 통 뒤    번호가 통째로 사라짐            ← 어긋났다
    자료를 한 번 보낸 뒤   1번 가나애그 · 2번 다라헬스     ← 어긋났다

되읽는 쪽이 "이 담당자에게 **마지막으로 나간 회차**" 를 봤기 때문이다. 회차는
딜소개만 만드는 것이 아니라 리마인드·자료 전달·소싱 제안도 만든다.

이제 번호는 `services/deal_numbers.py` 한 곳에서 나온다 — 딜 소개가 붙이고,
자료 전달은 그것을 되읽기만 한다.

이름·회사명은 전부 가상이다(공개 저장소).
"""
from __future__ import annotations

import re

import pytest

from .conftest import DEMO_PASSWORD

NAMES = ("가나애그", "다라헬스", "마바로보")


@pytest.fixture()
def seed(client, db, users):
    """소개 가능한 기업 셋 + 카톡방이 등록된 담당자 하나.

    기업은 **목록에 그려지는 차례**(가 → 다 → 마)로 넣어 둔다. 검사는 이
    차례를 일부러 뒤집어 고른다 — 차례대로 고르면 목록 차례와 같아서 뒤섞여도
    아무것도 안 잡힌다.
    """
    from app.models import IrCompany, MessageTemplate, VcContact

    companies = [
        IrCompany(name=n, sector_major="분야", series="Seed",
                  one_liner=f"{n} 한줄소개", summary=f"{n} [분야] 한줄소개",
                  summary_status="done", revenue_recent=1)
        for n in NAMES
    ]
    contact = VcContact(
        user_id=users["u1"].id, name="가담당", title="심사역", firm="사아벤처스",
        connect_stage="connected", status="active", channel_kakao=1,
        source_sheet="가 명단", kakao_room_name="가담당 심사역님",
        room_verified="verified",
    )
    db.add_all(companies + [contact, MessageTemplate(
        user_id=None, kind="ir_delivery", is_active=1,
        body="{기업목록} IR deck 먼저 전달드리겠습니다.")])
    db.commit()
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    return {"ids": {c.name: c.id for c in companies}, "contact_id": contact.id}


def _deal_numbers(text: str) -> dict:
    """딜 소개 문구의 `1) 2) 3)` — `{기업명: 번호}`."""
    out = {}
    for line in text.splitlines():
        m = re.match(r"^(\d+)\)\s*(.*)$", line)
        if not m:
            continue
        for name in NAMES:
            if name in m.group(2):
                out[name] = int(m.group(1))
    return out


def _ir_numbers(text: str) -> dict:
    """자료 전달 문구의 `2번 기업 …` — 번호가 없으면 `None`."""
    out = {}
    for name in NAMES:
        m = re.search(r"(\d+)번 기업 " + name, text)
        if m:
            out[name] = int(m.group(1))
        elif name in text:
            out[name] = None            # 이름은 있는데 번호가 없다
    return out


def _preview_one(client, seed, mode, company_ids, contact_id=None) -> dict:
    """미리보기 한 통 전체 — 문구와 [보낼 자료] 목록이 **같은 응답**에 있다."""
    r = client.post("/api/deals/preview", json={
        "mode": mode, "company_ids": company_ids,
        "contact_ids": [contact_id or seed["contact_id"]]})
    assert r.status_code == 200, r.text
    return r.json()["previews"][0]


def _preview(client, seed, mode, company_ids) -> str:
    return _preview_one(client, seed, mode, company_ids)["message"]


def _screen_numbers(preview: dict) -> dict:
    """화면의 [보낼 자료] 목록이 적는 번호 — `{기업명: 번호}`.

    번호가 없으면 `None` 이다(딜 소개에 없던 기업). 화면은 이 값을 그대로
    적는다 — `app/static/js/deals.js` 의 `renderIrLinks`.
    """
    return {a["name"]: a["no"] for a in preview["attachments"]}


def _send(client, db, seed, mode, company_ids) -> None:
    """보내고 **실제로 나간 것으로** 만든다 — 번호는 나간 회차에서만 읽는다."""
    from app.models import SendItem

    r = client.post("/api/deals/send", json={
        "mode": mode, "company_ids": company_ids,
        "contact_ids": [seed["contact_id"]]})
    assert r.status_code == 200, r.text
    db.expire_all()
    for item in db.query(SendItem).filter_by(job_id=r.json()["job_id"]).all():
        item.status = "sent"
    db.commit()


def _reversed_pick(seed) -> list:
    """거꾸로 고른 차례 — 마 → 가 → 다. 목록 차례와 다르다."""
    ids = seed["ids"]
    return [ids["마바로보"], ids["가나애그"], ids["다라헬스"]]


@pytest.fixture()
def after_deal(client, db, seed):
    """딜 소개를 거꾸로 골라 한 회차 보낸 상태 + 그때 문구에 붙은 번호."""
    picked = _reversed_pick(seed)
    numbers = _deal_numbers(_preview(client, seed, "deal", picked))
    assert numbers == {"마바로보": 1, "가나애그": 2, "다라헬스": 3}, numbers
    _send(client, db, seed, "deal", picked)
    return numbers


def _asked(seed) -> list:
    """투자사가 자료를 청한 기업 — 딜 소개에서 2·3번이던 둘."""
    return [seed["ids"]["가나애그"], seed["ids"]["다라헬스"]]


def test_자료_전달_번호는_딜_소개_번호_그대로다(client, seed, after_deal):
    """딜 소개에서 2·3번이면 자료 전달에서도 2·3번이다."""
    got = _ir_numbers(_preview(client, seed, "ir", _asked(seed)))
    assert got == {"가나애그": after_deal["가나애그"],
                   "다라헬스": after_deal["다라헬스"]}, got


def test_요청받은_차례를_뒤집어_골라도_번호는_그대로다(client, seed, after_deal):
    """자료를 청한 차례와 투자사가 기억하는 번호는 다르다 — 다시 세지 않는다."""
    ids = seed["ids"]
    text = _preview(client, seed, "ir", [ids["다라헬스"], ids["가나애그"]])
    assert _ir_numbers(text) == {"가나애그": 2, "다라헬스": 3}, text
    # 짚는 **차례**는 고른 차례다 — 화면의 [보낼 자료] 목록과 같아야 한다.
    assert text.index("3번 기업 다라헬스") < text.index("2번 기업 가나애그"), text


def test_리마인드를_한_통_보낸_뒤에도_번호가_남는다(client, db, seed, after_deal):
    """★ 기업 없이 문구만 나가는 회차가 번호를 덮어쓰면 안 된다.

    고치기 전에는 그 회차가 '마지막 회차' 가 되어 번호가 통째로 사라졌다 —
    문구가 "가나애그, 다라헬스 IR deck …" 으로 나갔다.
    """
    _send(client, db, seed, "remind", [])

    got = _ir_numbers(_preview(client, seed, "ir", _asked(seed)))
    assert got == {"가나애그": 2, "다라헬스": 3}, got


def test_자료를_한_번_보낸_뒤에도_번호가_그대로다(client, db, seed, after_deal):
    """★ 자료 전달 회차가 번호를 다시 매기면 안 된다.

    고치기 전에는 두 번째 자료 전달이 1 부터 다시 셌다 — 딜 소개에서 2·3번이던
    기업이 1·2번이 되어, 투자사가 기억하는 번호와 다른 기업을 짚었다.
    """
    _send(client, db, seed, "ir", _asked(seed))

    got = _ir_numbers(_preview(client, seed, "ir", _asked(seed)))
    assert got == {"가나애그": 2, "다라헬스": 3}, got


def test_소싱_제안이_끼어들어도_번호가_그대로다(client, db, seed, after_deal, users):
    """소싱 제안도 회차를 남긴다 — 딜 소개가 아니므로 번호를 정하지 않는다."""
    from app.models import DealBatch, DealBatchCompany, SendItem, SendJob

    batch = DealBatch(user_id=users["u1"].id, title="딜 소싱 제안",
                      sent_date="2026-09-03")
    db.add(batch)
    db.flush()
    db.add(DealBatchCompany(batch_id=batch.id,
                            company_id=seed["ids"]["다라헬스"], position=1))
    job = SendJob(user_id=users["u1"].id, kind="sourcing_intro",
                  batch_id=batch.id, status="done", total=1, sent=1)
    db.add(job)
    db.flush()
    db.add(SendItem(job_id=job.id, contact_id=seed["contact_id"], stage=2,
                    room_name="가담당 심사역님", message="…", status="sent"))
    db.commit()

    got = _ir_numbers(_preview(client, seed, "ir", _asked(seed)))
    assert got == {"가나애그": 2, "다라헬스": 3}, got


def test_다음_회차가_나가면_그_회차의_번호를_따른다(client, db, seed, after_deal):
    """번호를 얼리는 것이 아니다 — 투자사가 마지막으로 본 목록이 기준이다."""
    ids = seed["ids"]
    _send(client, db, seed, "deal", [ids["다라헬스"], ids["가나애그"]])

    got = _ir_numbers(_preview(client, seed, "ir", _asked(seed)))
    assert got == {"다라헬스": 1, "가나애그": 2}, got


def test_번호를_만드는_곳은_한_곳이다(client, db, seed):
    """문구의 `1) 2) 3)` 과 회차에 남는 `position` 이 같은 자리에서 나온다.

    두 곳에서 따로 세면 어긋나도 아무도 모르고, 그러면 다음에 자료를 보낼 때
    엉뚱한 기업을 짚는다.
    """
    from sqlalchemy import select

    from app.models import DealBatchCompany, SendItem

    picked = _reversed_pick(seed)
    _send(client, db, seed, "deal", picked)

    text = db.execute(select(SendItem)).scalars().first().message
    said = _deal_numbers(text)
    kept = {row.company_id: row.position for row in db.execute(
        select(DealBatchCompany)).scalars().all()}

    assert {seed["ids"][name]: no for name, no in said.items()} == kept, text


# ── 화면에 적히는 번호 ──────────────────────────────────────────────────────
#
# 자료는 **사람이 PC 카톡에 손으로 붙인다.** 번호 차례대로 붙여야 하는데 화면에
# 번호가 안 적혀 있으면 어느 것이 몇 번인지 알 수가 없다 — 그래서 미리보기가
# 문구와 **같은 응답**에 번호를 실어 준다(`attachments[].no`).
#
# 화면과 문구가 갈리면 이 일을 한 뜻이 없다. 아래 검사들이 그것을 못박는다.

def test_보낼_자료_목록의_번호가_문구의_번호와_같다(client, seed, after_deal):
    """★ 화면이 `1·2` 인데 문구가 "3번 기업 …" 이면 엉뚱한 자료가 붙는다."""
    p = _preview_one(client, seed, "ir", _asked(seed))

    assert _screen_numbers(p) == _ir_numbers(p["message"]), p


def test_요청받은_차례를_뒤집어도_화면과_문구가_같이_간다(client, seed, after_deal):
    """짚는 **차례**는 고른 차례, **번호**는 딜 소개에서 붙은 것.

    번호가 오름차순이 아닐 수 있다는 뜻이라, 여기가 갈리기 제일 쉽다.
    """
    ids = seed["ids"]
    p = _preview_one(client, seed, "ir", [ids["다라헬스"], ids["가나애그"]])

    assert [a["name"] for a in p["attachments"]] == ["다라헬스", "가나애그"], p
    assert [a["no"] for a in p["attachments"]] == [3, 2], p
    assert _screen_numbers(p) == _ir_numbers(p["message"]), p


def test_담당자마다_화면의_번호가_다르다(client, db, seed, after_deal, users):
    """★ 같은 기업이 A 담당자에겐 2번, B 담당자에겐 1번이다.

    화면이 고른 차례를 세면 두 담당자에게 같은 번호를 적는다 — 그러면 한쪽은
    반드시 틀린다. 목록은 **지금 열어 둔 미리보기**의 번호를 적어야 한다.
    """
    from app.models import VcContact

    other = VcContact(
        user_id=users["u1"].id, name="나담당", title="심사역", firm="자차벤처스",
        connect_stage="connected", status="active", channel_kakao=1,
        source_sheet="가 명단", kakao_room_name="나담당 심사역님",
        room_verified="verified",
    )
    db.add(other)
    db.commit()
    # 이 담당자에게는 **다른 차례**로 딜 소개가 나갔다.
    ids = seed["ids"]
    r = client.post("/api/deals/send", json={
        "mode": "deal", "company_ids": [ids["가나애그"], ids["다라헬스"]],
        "contact_ids": [other.id]})
    assert r.status_code == 200, r.text
    from app.models import SendItem
    db.expire_all()
    for item in db.query(SendItem).filter_by(job_id=r.json()["job_id"]).all():
        item.status = "sent"
    db.commit()

    mine = _preview_one(client, seed, "ir", _asked(seed))
    theirs = _preview_one(client, seed, "ir", _asked(seed), contact_id=other.id)

    assert _screen_numbers(mine) == {"가나애그": 2, "다라헬스": 3}, mine
    assert _screen_numbers(theirs) == {"가나애그": 1, "다라헬스": 2}, theirs
    # 각자 제 문구와 같아야 한다 — 한 통만 맞고 다른 통이 틀리면 소용없다.
    for p in (mine, theirs):
        assert _screen_numbers(p) == _ir_numbers(p["message"]), p


def test_회차에_있던_기업은_그_회차의_번호를_적는다(client, seed, after_deal):
    """자료를 청하지 않은 기업까지 섞어 골라도 번호는 그 회차의 것이다."""
    ids = seed["ids"]
    p = _preview_one(client, seed, "ir", [ids["가나애그"], ids["마바로보"]])

    # 마바로보는 그 회차에 1번이었다 — 고른 차례(2번째)가 아니다.
    assert _screen_numbers(p) == {"가나애그": 2, "마바로보": 1}, p
    assert _screen_numbers(p) == _ir_numbers(p["message"]), p


def test_회차에_없던_기업은_번호_없이_나간다(client, db, seed, after_deal):
    """★ 새로 들어온 기업 — 화면도 문구도 번호를 안 붙인다."""
    from app.models import IrCompany

    fresh = IrCompany(name="사아푸드", sector_major="분야", series="Seed",
                      one_liner="사아푸드 한줄소개", summary="사아푸드 [분야] 한줄소개",
                      summary_status="done", revenue_recent=1)
    db.add(fresh)
    db.commit()

    p = _preview_one(client, seed, "ir",
                     [seed["ids"]["가나애그"], fresh.id])

    assert _screen_numbers(p) == {"가나애그": 2, "사아푸드": None}, p
    # 문구에도 번호가 없다 — 이름만 적힌다.
    assert "사아푸드" in p["message"], p
    assert "번 기업 사아푸드" not in p["message"], p


def test_담당자를_안_고르면_번호가_없다(client, seed, after_deal):
    """기본 문구에는 번호가 없다 — 번호는 담당자를 알아야 나온다.

    화면은 이때 '번호 없음' 이라고 적지 않는다(deals.js 가 `sample` 을 본다) —
    있는 번호를 없다고 읽히면 안 된다.
    """
    r = client.post("/api/deals/preview", json={
        "mode": "ir", "company_ids": _asked(seed), "contact_ids": []})
    assert r.status_code == 200, r.text
    p = r.json()["previews"][0]

    assert p["sample"] is True, p
    assert all(a["no"] is None for a in p["attachments"]), p


def test_자료를_안_올린_기업도_번호는_적힌다(client, db, seed, after_deal):
    """첨부할 파일이 없는 것과 번호가 없는 것은 **다른 이야기**다."""
    p = _preview_one(client, seed, "ir", _asked(seed))

    # 이 저장소의 기본 자료(seed)에는 파일명이 없다 — 그래도 번호는 나온다.
    assert all(a["file"] == "" for a in p["attachments"]), p
    assert _screen_numbers(p) == {"가나애그": 2, "다라헬스": 3}, p


# ── 화면 ────────────────────────────────────────────────────────────────────
#
# 문구를 맞춰 놓아도 **화면이 다른 번호를 띄우면** 사람은 그것을 믿는다.
# 딜 소개 탭의 카드 배지는 고른 차례를 띄우는데(`data-pick-order`), 자료
# 전달에서는 그 차례가 번호가 아니다 — 번호는 딜 소개에서 붙은 것이고 담당자
# 마다 다르다. deals.js 를 **그대로 실행**해서 본다.

def test_자료_전달_탭에서는_고른_차례를_번호처럼_띄우지_않는다():
    """★ 화면은 `1`, 문구는 `2번 기업 …` — 어느 쪽이 맞는지 알 수 없었다."""
    import shutil
    import subprocess
    from pathlib import Path

    node = shutil.which("node")
    if node is None:
        pytest.skip("node 미설치 — 브라우저 로직 테스트 생략 "
                    "(호스트에서 `node tests/js/deals_ir_number_test.js`)")
    js = Path(__file__).resolve().parent / "js" / "deals_ir_number_test.js"
    result = subprocess.run([node, str(js)], capture_output=True,
                            text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr


def test_배지를_비우는_규칙이_css_에_있다():
    """화면 코드가 붙이는 표시(`no-pick-badge`)를 CSS 가 실제로 읽는가.

    한쪽만 있으면 아무 일도 안 일어난다 — 표시는 붙는데 배지는 그대로 뜬다.
    """
    from pathlib import Path

    css = (Path(__file__).resolve().parents[1] / "app" / "static" / "css"
           / "app.css").read_text(encoding="utf-8")
    assert ".panel.no-pick-badge #company-list .pick-card::before" in css


def test_번호를_적을_자리가_화면에_있다():
    """번호를 실어 보내도 **화면이 그것을 그리지 않으면** 아무 일도 안 난다.

    셋이 다 이어져야 한 바퀴가 돈다: 서버가 싣고(`attachments[].no`) → 화면이
    적고(`ir_attach_list.js` 의 `renderList`) → CSS 가 배지로 보여준다.

    목록을 그리는 자리는 **한 벌뿐이다** — 딜 제안 관리와 IR 진행 관리의
    [자료 보내기] 창이 같은 것을 부른다(`deals.js` 의 `renderIrLinks` 는
    그 한 벌에 넘길 뿐이다).
    """
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "app"
    js = (root / "static" / "js" / "ir_attach_list.js").read_text(encoding="utf-8")
    deals_js = (root / "static" / "js" / "deals.js").read_text(encoding="utf-8")
    css = (root / "static" / "css" / "app.css").read_text(encoding="utf-8")
    html = (root / "templates" / "deals.html").read_text(encoding="utf-8")

    # 목록은 **미리보기의 자료 목록**에서 그린다 — 화면이 따로 세면 안 된다.
    assert "preview.attachments" in js, "[보낼 자료] 목록이 미리보기의 값을 안 쓴다"
    assert 'class="ir-no"' in js, "번호를 적는 자리가 없다"
    assert "IrAttach.renderList" in deals_js, "발송 화면이 그 한 벌을 안 쓴다"
    assert ".ir-attach .ir-no" in css, "번호 배지를 CSS 가 안 읽는다"
    assert 'id="ir-no-note"' in html, "번호가 왜 그런지 적을 자리가 없다"

    # ★ 주석이 안 닫히면 **뒤따르는 규칙이 통째로 죽는다.** 이 파일은 설명이
    # 길어 손으로 고치다 `*/` 를 흘리기 쉽고, 그러면 배지 자리는 있는데 번호가
    # 맨글자로 뜬다 — 실제로 이 일을 하며 한 번 그랬다. 검사만으로는 안 잡히고
    # 화면을 열어야 보이던 것을 여기서 잡는다.
    import re

    assert css.count("/*") == css.count("*/"), "CSS 주석이 안 닫혔다"
    bare = [ln for ln in re.sub(r"/\*.*?\*/", "", css, flags=re.S).splitlines()
            if re.search(r"[가-힣]", ln)]
    assert not bare, f"주석 밖에 설명 글이 남았다 — 뒤 규칙이 죽는다: {bare[:3]}"
