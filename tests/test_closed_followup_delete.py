"""`IR 요청 투자사` 표에서 **줄 하나 지우기**.

왜 만들었나
-----------
그 표에 붙은 조작은 [다시 켜기] 하나뿐이었다. 리마인드가 끝난 담당자는 계속
쌓이기만 하고, 표에서 없애려면 사람이 자료를 직접 건드려야 했다.

여기서 잠그는 것은 여섯이다.

1. 지우면 **그 줄만** 없어진다 — 명단·발송 기록·활동은 그대로 남는다.
   사람이 바라는 것은 "이 표에서 안 보이게" 이지 투자사를 지우는 것이 아니다.
2. **남의 담당 줄은 못 지운다.** 화면에서 감추는 것으로는 모자란다 — 주소를
   아는 사람이 그대로 부를 수 있다. 서버가 막아야 한다.
3. **확인 없이는 안 지워진다**(확인창 자체는 `tests/js/closed_delete_confirm_test.js`
   가 실제로 눌러 본다 — 여기서는 그 자리가 화면에 붙어 있는지를 본다).
4. **삭제가 수정 로그에 남는다.** 지운 줄은 화면 어디에도 없다 — 무엇이
   있었는지 물을 자리가 로그밖에 없다.
5. **두 화면 양쪽에** 단추가 있다(`ir.html` · `followups.html` 이 같은 파일을
   쓴다 — 한쪽만 고쳐지는 그 사고를 막는 자리다).
6. **[다시 켜기] 가 그대로 동작한다.**

이름은 전부 지어낸 것이다(공개 저장소).
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / "app" / "templates"
SHARED = TEMPLATES / "_closed_followups.html"
CONFIRM_JS_TEST = ROOT / "tests" / "js" / "closed_delete_confirm_test.js"


# ── 무대 ────────────────────────────────────────────────────────────────────

@pytest.fixture()
def closed_row(db, users):
    """리마인드가 **끝난** 줄 하나 + 그 줄이 딛고 선 자료 전부.

    지울 때 **무엇이 남아야 하는지**를 여기서 다 세워 둔다 — 명단 줄 ·
    발송 회차 · 발송 작업 · 발송 한 건 · 활동 기록.
    """
    from app.models import (
        ContactActivity,
        DealBatch,
        SendItem,
        SendJob,
        SendSequence,
        VcContact,
    )

    contact = VcContact(user_id=users["u1"].id, name="가담당", firm="가나벤처스",
                        connect_stage="connected", kakao_room_name="가나 방")
    batch = DealBatch(user_id=users["u1"].id, title="시험 회차")
    db.add_all([contact, batch])
    db.flush()

    job = SendJob(user_id=users["u1"].id, kind="deal_intro", batch_id=batch.id,
                  status="done", total=1, sent=1)
    db.add(job)
    db.flush()

    item = SendItem(job_id=job.id, contact_id=contact.id, stage=1,
                    room_name="가나 방", message="시험 문구", status="sent",
                    sent_at="2026-09-01T10:00:00")
    activity = ContactActivity(contact_id=contact.id, kind="ir_request",
                               content="자료를 달라고 하셨습니다",
                               happened_at="2026-09-02")
    seq = SendSequence(user_id=users["u1"].id, contact_id=contact.id,
                       batch_id=batch.id, stage=2, next_stage=None,
                       next_due_date=None, status="responded",
                       day1_sent_at="2026-09-01T10:00:00",
                       stopped_reason="IR 자료를 요청했습니다")
    db.add_all([item, activity, seq])
    db.commit()
    return {"contact": contact, "batch": batch, "job": job, "item": item,
            "activity": activity, "seq": seq}


def _seq_ids(db, user_id):
    from sqlalchemy import select

    from app.models import SendSequence

    db.expire_all()
    return [s.id for s in db.execute(
        select(SendSequence).where(SendSequence.user_id == user_id)).scalars()]


# ═══════════════════════════════════════════════════════════════════════════
# 1. 지우면 **그 줄만** 없어진다
# ═══════════════════════════════════════════════════════════════════════════

def test_지우면_그_줄만_없어지고_명단과_발송_기록은_남는다(logged_in, db, users,
                                                          closed_row):
    """**투자사를 지우는 것이 아니다.**

    사람은 "이 표에서 없애고 싶다" 는 것이지 담당자를 명단에서 지우려는 것이
    아니다. 명단 줄이 같이 사라지면 발송 대상이 조용히 줄고, 그 담당자에게
    다시 IR 요청이 와도 적을 자리가 없다.
    """
    from app.models import ContactActivity, SendItem, SendJob, VcContact

    seq_id = closed_row["seq"].id
    contact_id = closed_row["contact"].id

    r = logged_in.post(f"/followups/{seq_id}/delete", follow_redirects=False)
    assert r.status_code == 303, r.text

    assert _seq_ids(db, users["u1"].id) == [], "그 줄이 안 지워졌다"

    # 남아야 하는 것들.
    assert db.get(VcContact, contact_id) is not None, "명단 줄이 같이 사라졌다"
    assert db.get(SendJob, closed_row["job"].id) is not None, "발송 작업이 사라졌다"
    assert db.get(SendItem, closed_row["item"].id) is not None, "발송 기록이 사라졌다"
    assert db.get(ContactActivity, closed_row["activity"].id) is not None, \
        "활동 기록이 사라졌다"


def test_지운_뒤에도_그_담당자에게_IR_요청을_기록할_수_있다(logged_in, db, users,
                                                          closed_row):
    """줄을 지운 것이 담당자를 지운 것이 아니라는 말의 **실제 확인**.

    표의 이름 링크가 가리키는 곳(`/ir?contact=…`)이 그대로 열려야 한다 —
    거기서 답이 온 것을 기록하는 것이 이 표를 여는 이유 그 자체다.
    """
    seq_id = closed_row["seq"].id
    contact_id = closed_row["contact"].id
    logged_in.post(f"/followups/{seq_id}/delete", follow_redirects=False)

    html = logged_in.get(f"/ir?contact={contact_id}", follow_redirects=True).text
    assert "가담당" in html, "지운 뒤 그 담당자 화면이 비었다"


def test_지운_줄은_표에서_사라진다(logged_in, db, users, closed_row):
    """지웠는데 화면에 그대로 있으면 사람은 또 누른다."""
    seq_id = closed_row["seq"].id
    assert "가나벤처스" in logged_in.get("/ir", follow_redirects=True).text

    logged_in.post(f"/followups/{seq_id}/delete", follow_redirects=False)

    html = logged_in.get("/ir", follow_redirects=True).text
    assert f'/followups/{seq_id}/delete' not in html, "지운 줄이 표에 남아 있다"


def test_지운_줄은_지난_발송에서_다시_선다(logged_in, db, users, closed_row):
    """**되살아난다** — 확인 문구가 그렇게 말했으니 실제로도 그래야 한다.

    발송 기록을 남겨 두었으므로 [지난 발송에서 리마인드 걸기] 가 같은 줄을
    다시 세운다. 이 검사가 깨지면 확인 문구가 거짓말이 된 것이다.
    """
    logged_in.post(f"/followups/{closed_row['seq'].id}/delete",
                   follow_redirects=False)
    assert _seq_ids(db, users["u1"].id) == []

    r = logged_in.post("/followups/backfill", follow_redirects=False)
    assert r.status_code == 303, r.text
    assert len(_seq_ids(db, users["u1"].id)) == 1, \
        "확인 문구는 '다시 생긴다' 고 했는데 안 생긴다"


# ═══════════════════════════════════════════════════════════════════════════
# 2. 남의 담당 줄은 못 지운다 — **서버가** 막는다
# ═══════════════════════════════════════════════════════════════════════════

def test_남의_담당_줄은_서버가_막는다(client, db, users, closed_row):
    """화면에서 안 보이는 것으로는 모자라다 — 주소를 알면 그대로 부른다.

    판정은 [다시 켜기] 가 쓰는 그것과 **같은 것**이어야 한다
    (`routers/followups._owned`). 새로 지으면 두 판정이 갈린다.
    """
    from .conftest import DEMO_PASSWORD

    seq_id = closed_row["seq"].id      # 주인은 u1
    client.post("/login", data={"phone": "01000000002",
                                "password": DEMO_PASSWORD})

    r = client.post(f"/followups/{seq_id}/delete", follow_redirects=False)
    assert r.status_code == 404, r.text
    assert _seq_ids(db, users["u1"].id) == [seq_id], "남의 줄이 지워졌다"


def test_지우기와_다시_켜기가_같은_판정을_쓴다():
    """판정을 **한 자리에서** 읽는다 — 갈리면 한쪽만 열린다.

    둘 다 `_owned` 를 그대로 불러야 한다. 라우터 안에서 `user_id` 를 다시
    비교하기 시작하면, 한쪽 규칙이 바뀔 때 다른 쪽이 따라가지 못한다.
    """
    src = (ROOT / "app" / "routers" / "followups.py").read_text(encoding="utf-8")

    for name in ("resume_sequence", "delete_sequence"):
        body = re.search(rf"def {name}\(.*?\n(.*?)(?=\n@router|\Z)", src, re.S)
        assert body, f"{name} 이 없다"
        assert "_owned(db, sequence_id, user)" in body.group(1), \
            f"{name} 이 `_owned` 를 안 쓴다 — 권한 판정이 두 벌이 된다"


def test_없는_줄을_지우려_해도_같은_답이다(logged_in):
    """있고 없고를 답으로 알려 주지 않는다 — 남의 줄과 같은 404 다."""
    assert logged_in.post("/followups/999999/delete",
                          follow_redirects=False).status_code == 404


# ═══════════════════════════════════════════════════════════════════════════
# 3. 확인 없이는 안 지워진다
# ═══════════════════════════════════════════════════════════════════════════

def test_지우기에_확인창이_붙어_있다():
    """이 저장소의 다른 위험 조작과 **같은 방식**(브라우저 `confirm()`)이다."""
    html = SHARED.read_text(encoding="utf-8")
    form = re.search(
        r'<form[^>]*action="/followups/\{\{ r\.id \}\}/delete"(.*?)</form>',
        html, re.S)
    assert form, "줄 지우기 폼이 없다"
    assert re.search(r'onsubmit="return confirm\(', form.group(1)), \
        "확인 없이 지워진다 — 이 저장소의 다른 삭제는 전부 confirm() 을 쓴다"


def test_확인_문구가_되살아난다는_것을_말한다():
    """**지웠는데 다시 생기면 사람은 고장으로 읽는다.**

    [지난 발송에서 리마인드 걸기] 를 누르면 그 발송 기록에서 같은 줄이 다시
    선다(`cadence.backfill_from_history`). 그 말이 확인 문구에 없으면, 되살아난
    줄을 보고 "안 지워졌다" 로 읽고 또 누른다.
    """
    html = SHARED.read_text(encoding="utf-8")
    form = re.search(
        r'<form[^>]*action="/followups/\{\{ r\.id \}\}/delete"(.*?)</form>',
        html, re.S)
    message = re.search(r"confirm\('(.*?)'\)", form.group(1), re.S).group(1)

    assert "지난 발송에서 리마인드 걸기" in message, \
        "되살아난다는 것을 안 말한다: " + message
    assert "IR 요청 투자사" in message, "어느 표에서 없애는지 안 말한다: " + message
    assert "명단" in message and "발송 기록" in message, \
        "무엇이 남는지 안 말한다 — 투자사를 지우는 줄 안다: " + message
    # 문구가 가리키는 그 단추가 실제로 같은 화면에 있어야 한다.
    assert "지난 발송에서 리마인드 걸기</button>" in html, \
        "확인 문구가 없는 단추를 가리킨다"


def test_취소를_누르면_정말_안_나간다():
    """확인창이 장식이 아닌지는 **눌러 봐야** 안다 — 브라우저 쪽에서 돌린다."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("node 미설치 — 브라우저 로직 테스트 생략 "
                    "(호스트에서 `node tests/js/closed_delete_confirm_test.js`)")
    result = subprocess.run([node, str(CONFIRM_JS_TEST)], capture_output=True,
                            text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr


def test_다시_켜기_옆에_붙여_두지_않는다():
    """되살리려다 지우는 것이 이 표에서 **가장 나쁜 실수**다.

    고친 값은 그 줄에 남아 다시 고치면 되지만, 지운 줄은 화면 어디에도 없다.
    그래서 겹쳐 둔다 — 사이를 벌리고, 끊어 주고, 색을 달리하고, 확인창을 세운다.
    """
    html = SHARED.read_text(encoding="utf-8")
    css = (ROOT / "app" / "static" / "css" / "app.css").read_text(encoding="utf-8")

    # 벌리는 것은 칸 안쪽 `div` 다 — `<td>` 에 `display:flex` 를 주면 그 칸이
    # 테이블 레이아웃에서 빠져 줄이 어긋난다(`tests/test_ui_layout.py`).
    cell = re.search(r'<div class="closed-actions">(.*?)</div>', html, re.S)
    assert cell, "두 단추를 담은 자리에 이름이 없다 — 사이를 벌릴 자리가 없다"
    assert '<td class="closed-actions"' not in html, \
        "`<td>` 자체에 걸면 그 칸이 테이블 레이아웃에서 빠진다"
    assert "resume" in cell.group(1) and "delete" in cell.group(1), \
        "[다시 켜기] 와 [지우기] 가 같은 칸에 나란히 있지 않다"
    assert '<span class="sep"' in cell.group(1), "두 단추 사이가 안 끊겨 있다"
    assert 'class="linkbtn danger"' in cell.group(1), \
        "지우기가 [다시 켜기] 와 같은 색이다"

    rule = re.search(r"\.closed-actions \{([^}]*)\}", css)
    assert rule, "`.closed-actions` 규칙이 없다 — 두 단추가 붙어 버린다"
    assert "gap" in rule.group(1), "두 단추 사이를 안 벌린다"


# ═══════════════════════════════════════════════════════════════════════════
# 4. 삭제가 **수정 로그에 남는다**
# ═══════════════════════════════════════════════════════════════════════════

def test_삭제가_수정_로그에_남는다(logged_in, db, users, closed_row):
    """**자기 줄을 지운 것도 남는다.**

    자기 것을 고친 것은 안 남기는 규칙이지만, 지운 줄은 화면 어디에도 없어
    무엇이 있었는지 물을 자리가 로그밖에 없다(`edit_log._row_scope`).
    """
    from app.models import EditLog
    from app.services import edit_log as svc

    seq_id = closed_row["seq"].id
    r = logged_in.post(f"/followups/{seq_id}/delete", follow_redirects=False)
    assert r.status_code == 303

    db.expire_all()
    logs = [x for x in db.query(EditLog).order_by(EditLog.id).all()
            if x.table_name == "send_sequences"]
    assert logs, "줄을 지웠는데 수정 로그에 아무 것도 없다"

    log = logs[-1]
    assert log.action == svc.ACTION_DELETE
    assert log.scope == svc.SCOPE_MINE, "자기 줄을 지운 것이 안 남았다"
    assert log.row_id == seq_id
    assert log.actor_user_id == users["u1"].id
    assert log.target_user_id == users["u1"].id
    assert log.path == f"/followups/{seq_id}/delete"


def test_로그가_어느_줄이었는지_말한다(logged_in, db, users, closed_row):
    """번호만 남기면 로그를 봐도 **누가 사라졌는지** 모른다.

    이 표에는 이름 칸이 없고 담당자 번호만 있어서, 이름을 따로 실어 준다
    (`edit_log._sequence_label`).
    """
    from app.models import EditLog

    logged_in.post(f"/followups/{closed_row['seq'].id}/delete",
                   follow_redirects=False)

    db.expire_all()
    log = [x for x in db.query(EditLog).order_by(EditLog.id).all()
           if x.table_name == "send_sequences"][-1]
    assert "가담당" in (log.row_label or ""), \
        "누구의 줄이었는지 안 남는다: " + repr(log.row_label)
    assert "가나벤처스" in (log.row_label or "")


def test_로그가_어느_화면_것인지_말한다(logged_in, db, users, closed_row):
    """걸러 보기(`화면`)에 안 잡히면 로그를 열어도 못 찾는다."""
    from app.models import EditLog
    from app.services import edit_log as svc

    logged_in.post(f"/followups/{closed_row['seq'].id}/delete",
                   follow_redirects=False)

    db.expire_all()
    log = [x for x in db.query(EditLog).order_by(EditLog.id).all()
           if x.table_name == "send_sequences"][-1]
    assert log.screen, "어느 화면 것인지 안 남는다"
    assert log.screen in svc.screens(), \
        f"걸러 보기 목록에 없는 화면 이름이다: {log.screen}"


def test_리마인드를_멈추고_켜는_것은_안_남는다(logged_in, db, users, closed_row):
    """**자기 줄을 고친 것까지 남기면 하루에 수백 줄이 쌓여 아무도 안 본다.**

    `send_sequences` 를 보는 표로 옮긴 것은 **지우는 길이 생겼기 때문**이지,
    기계가 세우고 멈추는 것을 다 남기려는 것이 아니다.
    """
    from app.models import EditLog

    seq_id = closed_row["seq"].id
    assert logged_in.post(f"/followups/{seq_id}/resume",
                          follow_redirects=False).status_code == 303
    assert logged_in.post(f"/followups/{seq_id}/responded",
                          follow_redirects=False).status_code == 303

    db.expire_all()
    logs = [x for x in db.query(EditLog).all() if x.table_name == "send_sequences"]
    assert not logs, "자기 줄을 고친 것까지 남는다 — 로그가 쓸모없어진다"


# ═══════════════════════════════════════════════════════════════════════════
# 5. 두 화면 **양쪽에** 단추가 있다
# ═══════════════════════════════════════════════════════════════════════════

def test_두_화면이_같은_파일로_그린다():
    """`ir.html` 과 `followups.html` 이 같은 파일을 include 해야 한다.

    `followups.html` 은 지금 아무 라우트도 안 그리지만(`/followups` 는
    `/ir#remind` 로 넘긴다) 함께 본다 — 되살아나는 날 한쪽에만 단추가 없는
    것을 막는 값이, 한 줄 보는 값보다 크다.
    """
    assert "/followups/{{ r.id }}/delete" in SHARED.read_text(encoding="utf-8"), \
        "지우기가 두 화면이 함께 쓰는 파일에 없다 — 한쪽만 고쳐진다"

    for name in ("ir.html", "followups.html"):
        page = (TEMPLATES / name).read_text(encoding="utf-8")
        assert '{% include "_closed_followups.html" %}' in page, \
            f"{name} 이 그 표를 따로 그리고 있다 — 한쪽만 고쳐진다"
        assert "/followups/{{ r.id }}/delete" not in page, \
            f"{name} 에 지우기가 한 벌 더 있다 — 두 벌이 되면 갈린다"


def test_두_화면_모두에서_지우기_단추가_그려진다(logged_in, db, users, closed_row):
    """`/followups` 는 옛 주소라 `/ir#remind` 로 넘긴다 — 따라가서 본다."""
    seq_id = closed_row["seq"].id
    for url in ("/ir", "/followups"):
        html = logged_in.get(url, follow_redirects=True).text
        assert f'action="/followups/{seq_id}/delete"' in html, \
            f"{url} 에 지우기 단추가 없다"
        assert f'action="/followups/{seq_id}/resume"' in html, \
            f"{url} 에 [다시 켜기] 가 없다"
        assert "return confirm(" in html, f"{url} 의 지우기에 확인창이 없다"


def test_남의_담당_줄에는_단추가_아예_안_뜬다(client, db, users, closed_row):
    """서버가 막는 것과 별개로, 애초에 남의 줄은 그 표에 담기지 않는다."""
    from .conftest import DEMO_PASSWORD

    client.post("/login", data={"phone": "01000000002",
                                "password": DEMO_PASSWORD})
    html = client.get("/ir", follow_redirects=True).text
    assert f"/followups/{closed_row['seq'].id}/delete" not in html
    assert "가나벤처스" not in html


# ═══════════════════════════════════════════════════════════════════════════
# 6. [다시 켜기] 가 그대로 동작한다
# ═══════════════════════════════════════════════════════════════════════════

def test_다시_켜기가_그대로_동작한다(logged_in, db, users, closed_row):
    """단추를 하나 더 붙였다고 옆 단추가 죽으면 안 된다."""
    from app.models import SendSequence

    seq_id = closed_row["seq"].id
    r = logged_in.post(f"/followups/{seq_id}/resume", follow_redirects=False)
    assert r.status_code == 303, r.text

    db.expire_all()
    seq = db.get(SendSequence, seq_id)
    assert seq is not None, "[다시 켜기] 가 줄을 지워 버렸다"
    assert seq.status == "active"
    assert seq.stopped_reason is None
    assert seq.next_stage is not None
