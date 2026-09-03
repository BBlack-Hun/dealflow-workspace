"""발송 목록 생성 — 미리보기에서 고친 문구가 그대로 나가는지 확인한다.

자동 조합이 늘 맞을 수는 없어서 담당자별로 문장을 손보는 일이 잦다.
고친 문구가 무시되거나(원문 발송), 대상이 아닌 사람에게 붙거나, 빈 문구로
나가는 것은 모두 발송 사고다. 아래 세 가지가 그 경계다.
"""
import pytest

from .conftest import DEMO_PASSWORD


@pytest.fixture()
def seed(client, db, users):
    """u1 로 로그인 + 소개 가능한 기업 1개 + 카톡방이 등록된 담당자 1명."""
    from app.models import IrCompany, VcContact

    company = IrCompany(
        name="샘플애그", sector_major="애그테크", series="Seed",
        one_liner="B2B 농산물 선도거래 플랫폼", summary="요약문", summary_status="done",
        revenue_recent=12,
    )
    contact = VcContact(
        user_id=users["u1"].id, name="홍길동", title="심사역", firm="가나벤처스",
        kakao_room_name="홍길동 심사역님 가나벤처스", room_verified="verified",
    )
    db.add_all([company, contact])
    db.commit()
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    return {"company_id": company.id, "contact_id": contact.id}




def _sent_message(db, job_id: int) -> str:
    """실제로 에이전트가 보낼 문구 = send_items 에 저장된 스냅샷."""
    from app.models import SendItem
    from sqlalchemy import select
    db.expire_all()
    return db.execute(select(SendItem).where(SendItem.job_id == job_id)).scalars().first().message


def test_send_uses_edited_message(client, db, seed):
    """미리보기에서 고친 문구는 그대로 발송된다."""
    edited = "직접 고친 문구입니다.\n이 내용 그대로 나가야 합니다."
    r = client.post("/api/deals/send", json={
        "company_ids": [seed["company_id"]],
        "contact_ids": [seed["contact_id"]],
        "title": "수정본 회차",
        "overrides": [{"contact_id": seed["contact_id"], "message": edited}],
    })
    assert r.status_code == 200, r.text
    assert _sent_message(db, r.json()["job_id"]) == edited


def test_send_rejects_empty_override(client, seed):
    """빈 수정본은 사고다 — 조용히 원문으로 되돌리지 않고 막는다."""
    r = client.post("/api/deals/send", json={
        "company_ids": [seed["company_id"]],
        "contact_ids": [seed["contact_id"]],
        "overrides": [{"contact_id": seed["contact_id"], "message": "   "}],
    })
    assert r.status_code == 400


def test_send_ignores_override_for_untargeted_contact(client, db, seed):
    """대상에서 뺀 담당자의 수정본은 무시된다(엉뚱한 사람에게 나가면 안 된다)."""
    r = client.post("/api/deals/send", json={
        "company_ids": [seed["company_id"]],
        "contact_ids": [seed["contact_id"]],
        "overrides": [{"contact_id": 999999, "message": "대상 아님"}],
    })
    assert r.status_code == 200, r.text
    assert "대상 아님" not in _sent_message(db, r.json()["job_id"])


# --- 문구만 보내기 (선호 분야 묻기) ----------------------------------------
#
# 딜소개를 보냈는데 답이 없을 때, 목록을 또 밀어 넣기보다 무엇을 보고 싶은지
# 되묻는 편이 답이 온다. 이때 **기업 목록이 붙으면 안 된다** — 그러면 그냥
# 딜소개를 한 번 더 보내는 것이 되어 버린다.

def test_ask_mode_needs_no_companies(client, seed):
    r = client.post("/api/deals/preview", json={
        "company_ids": [], "contact_ids": [seed["contact_id"]], "mode": "ask",
    })
    assert r.status_code == 200, r.text
    assert len(r.json()["previews"]) == 1


def test_ask_mode_message_has_no_company_list(client, db, seed):
    """번호 매긴 기업 목록이 붙으면 안 된다."""
    r = client.post("/api/deals/preview", json={
        "company_ids": [], "contact_ids": [seed["contact_id"]], "mode": "ask",
    })
    text = r.json()["previews"][0]["message"]
    assert "1)" not in text            # 번호 매긴 목록이 곧 '기업이 붙었다'는 신호다
    assert "선호하는 기업분야" in text


def test_ask_mode_ignores_companies_even_if_sent(client, db, seed):
    """실수로 기업을 함께 보내도 문구만 나간다(화면 상태와 어긋나도 안전하게)."""
    r = client.post("/api/deals/send", json={
        "company_ids": [seed["company_id"]],
        "contact_ids": [seed["contact_id"]],
        "mode": "ask",
    })
    assert r.status_code == 200, r.text
    assert "1)" not in _sent_message(db, r.json()["job_id"])


def test_deal_mode_still_requires_companies(client, seed):
    """기본 모드에서는 기업 없이 보낼 수 없다."""
    r = client.post("/api/deals/send", json={
        "company_ids": [], "contact_ids": [seed["contact_id"]],
    })
    assert r.status_code == 400


# --- 인사말 유무 ------------------------------------------------------------

def test_ask_mode_has_no_greeting_by_default(client, seed):
    """문구만 보낼 때는 이미 대화가 오간 방이라 인사를 다시 붙이지 않는다."""
    r = client.post("/api/deals/preview", json={
        "company_ids": [], "contact_ids": [seed["contact_id"]], "mode": "ask",
    })
    text = r.json()["previews"][0]["message"]
    assert "안녕하세요" not in text
    assert text.startswith("선호하는 기업분야")


def test_greeting_can_be_turned_back_on(client, seed):
    r = client.post("/api/deals/preview", json={
        "company_ids": [], "contact_ids": [seed["contact_id"]],
        "mode": "ask", "include_opening": True,
    })
    assert "안녕하세요" in r.json()["previews"][0]["message"]


def test_deal_mode_keeps_greeting_by_default(client, seed):
    r = client.post("/api/deals/preview", json={
        "company_ids": [seed["company_id"]], "contact_ids": [seed["contact_id"]],
    })
    assert "안녕하세요" in r.json()["previews"][0]["message"]


def test_greeting_can_be_turned_off_for_deals(client, db, seed):
    """딜소개에서도 인사말을 뺄 수 있고, 뺀 문구가 그대로 발송된다."""
    r = client.post("/api/deals/send", json={
        "company_ids": [seed["company_id"]], "contact_ids": [seed["contact_id"]],
        "include_opening": False,
    })
    assert r.status_code == 200, r.text
    text = _sent_message(db, r.json()["job_id"])
    assert "안녕하세요" not in text
    assert "1)" in text                # 기업 목록은 그대로 있어야 한다


# --- 리마인드 · 미팅 요청 ---------------------------------------------------
#
# 딜소개 말고는 전부 기업 목록 없이 문구만 나간다. 이미 목록을 받은 사람에게
# 같은 목록을 다시 밀어 넣는 것은 후속이 아니라 재발송이다.

@pytest.mark.parametrize("mode, expect", [
    ("remind", "지난번 공유드린"),
    ("meeting", "미팅 가능하실지요"),
    ("ask", "선호하는 기업분야"),
])
def test_follow_up_modes_send_only_text(client, seed, mode, expect):
    r = client.post("/api/deals/preview", json={
        "company_ids": [], "contact_ids": [seed["contact_id"]], "mode": mode,
    })
    assert r.status_code == 200, r.text
    text = r.json()["previews"][0]["message"]
    assert expect in text
    assert "1)" not in text            # 기업 목록이 붙으면 안 된다
    # 인사말은 **기본으로 붙는다.** 빼는 것은 선호 분야를 되물을 때뿐이다 —
    # 그건 이미 대화가 오간 방에 한 줄만 덧붙이는 것이라 다시 인사하면 어색하다.
    # 리마인드·미팅 요청은 며칠 지나 다시 거는 말이라 인사가 자연스럽다.
    if mode == "ask":
        assert "안녕하세요" not in text
    else:
        assert "안녕하세요" in text


@pytest.mark.parametrize("mode, title", [
    ("remind", "리마인드"), ("meeting", "미팅 요청"), ("ask", "선호 분야 묻기"),
])
def test_follow_up_batch_titles(client, db, seed, mode, title):
    """회차 이름이 무엇을 보낸 회차인지 알려줘야 한다."""
    from app.models import DealBatch

    r = client.post("/api/deals/send", json={
        "company_ids": [], "contact_ids": [seed["contact_id"]], "mode": mode,
    })
    assert r.status_code == 200, r.text
    db.expire_all()
    assert db.query(DealBatch).order_by(DealBatch.id.desc()).first().title == title


# --- IR 자료 전달 -----------------------------------------------------------
#
# 투자사는 "5) 친환경 패키지 …" 처럼 **번호로 기억하고** 답한다. 자료를 보낼 때
# 같은 번호로 짚어 줘야 서로 맞는다. 번호를 새로 매기면 받는 쪽에서는
# 자기 목록에서 찾다가 못 찾는다.

def _mark_sent(db, contact_id, companies, user_id):
    """이 담당자에게 회차를 하나 보낸 것으로 만든다."""
    from datetime import datetime, timezone

    from app.models import DealBatch, DealBatchCompany, SendItem, SendJob

    now = datetime.now(timezone.utc).isoformat()
    batch = DealBatch(user_id=user_id, title="지난 회차", sent_date=now[:10])
    db.add(batch)
    db.flush()
    for pos, company_id in enumerate(companies, start=1):
        db.add(DealBatchCompany(batch_id=batch.id, company_id=company_id, position=pos))
    job = SendJob(user_id=user_id, kind="deal_intro", batch_id=batch.id,
                  status="done", total=1, sent=1)
    db.add(job)
    db.flush()
    db.add(SendItem(job_id=job.id, contact_id=contact_id, room_name="방",
                    message="지난 회차", status="sent", sent_at=now))
    db.commit()
    return batch


def test_ir_message_uses_the_number_from_the_last_batch(client, db, seed, users):
    from app.models import IrCompany

    other = IrCompany(name="샘플메디", one_liner="뇌영상 분석", revenue_recent=42)
    db.add(other)
    db.commit()
    # 지난 회차: 1) 샘플메디  2) 샘플애그
    _mark_sent(db, seed["contact_id"], [other.id, seed["company_id"]], users["u1"].id)

    r = client.post("/api/deals/preview", json={
        "company_ids": [seed["company_id"]],
        "contact_ids": [seed["contact_id"]], "mode": "ir",
    })
    assert r.status_code == 200, r.text
    text = r.json()["previews"][0]["message"]
    assert "2번 기업 샘플애그" in text          # 새로 1번을 매기면 안 된다
    assert "IR deck 먼저 전달드리겠습니다" in text


def test_ir_message_omits_the_number_when_never_sent(client, db, seed):
    """지난 회차에 없던 기업은 번호를 지어내지 않는다."""
    r = client.post("/api/deals/preview", json={
        "company_ids": [seed["company_id"]],
        "contact_ids": [seed["contact_id"]], "mode": "ir",
    })
    text = r.json()["previews"][0]["message"]
    assert "샘플애그 IR deck" in text
    assert "번 기업" not in text


def test_ir_message_greets_once(client, seed):
    """문구 자체가 '안녕하세요' 로 시작한다 — 인사말을 또 붙이면 두 번 인사한다."""
    r = client.post("/api/deals/preview", json={
        "company_ids": [seed["company_id"]],
        "contact_ids": [seed["contact_id"]], "mode": "ir",
    })
    assert r.json()["previews"][0]["message"].count("안녕하세요") == 1


def test_ir_message_has_no_company_list(client, seed):
    """이미 목록을 본 사람이 '그 중 몇 번을 달라'고 답한 상황이다."""
    r = client.post("/api/deals/preview", json={
        "company_ids": [seed["company_id"]],
        "contact_ids": [seed["contact_id"]], "mode": "ir",
    })
    assert "1)" not in r.json()["previews"][0]["message"]


def test_ir_requires_a_company(client, seed):
    """무엇을 보내는지 골라야 한다."""
    r = client.post("/api/deals/send", json={
        "company_ids": [], "contact_ids": [seed["contact_id"]], "mode": "ir",
    })
    assert r.status_code == 400


def test_ir_warns_when_the_file_link_is_missing(client, db, seed):
    """첨부할 자료가 없으면 열어 내려받을 것도 없다 — 목록을 만들기 전에 알린다."""
    r = client.post("/api/deals/preview", json={
        "company_ids": [seed["company_id"]],
        "contact_ids": [seed["contact_id"]], "mode": "ir",
    })
    warnings = r.json()["previews"][0]["warnings"]
    assert any("첨부할 IR 자료가 없는 기업" in w for w in warnings)


def test_ir_has_no_warning_once_the_link_is_set(client, db, seed):
    from app.models import IrCompany

    company = db.get(IrCompany, seed["company_id"])
    company.ir_drive_url = "https://drive.google.com/file/d/sample/view"
    db.commit()

    r = client.post("/api/deals/preview", json={
        "company_ids": [seed["company_id"]],
        "contact_ids": [seed["contact_id"]], "mode": "ir",
    })
    preview = r.json()["previews"][0]
    assert not any("첨부할 IR 자료가 없는" in w for w in preview["warnings"])
    assert preview["attachments"][0]["url"].startswith("https://drive.google.com/")


# --- 탭 순서 = 일하는 순서 -----------------------------------------------------

def test_mode_tabs_follow_the_actual_flow(client, db, seed):
    """탭 순서가 곧 일하는 순서여야 다음에 뭘 눌러야 할지 헤매지 않는다.

        딜 소개 → (요청 오면) IR 자료 전달 → (반응 없으면) 리마인드
               → 미팅 요청 → 미팅 후기 → 선호 분야 묻기
    """
    import re

    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    body = client.get("/deals").text
    block = body[body.index('id="mode-tabs"'):]
    order = re.findall(r'data-mode="(\w+)"', block[:2000])
    # 딜 소싱 제안은 맨 끝이다 — 딜소개 흐름이 다 끝난 뒤의 다른 일이다
    assert order == ["deal", "ir", "remind", "meeting", "review", "ask",
                     "sourcing"], order
    assert "disabled" not in block[:2000]

    # '기업 소개' 는 '딜 소개' 로 바뀌었다 — 다른 화면 용어와 맞춘다
    assert "딜 소개<span>" in body
    assert "기업 소개<span>" not in body


def test_meeting_review_is_a_text_only_mode(client, db, seed):
    """미팅 뒤 열흘쯤 지나 결과를 묻는다. 원본 시트에도 "결과확인전화가 없으면
    계약을 잊어버리는 경우가 발생할 수 있습니다" 라고 적혀 있었다."""
    from app.routers.deals import FOLLOW_UP_MODES, MODES_WITH_COMPANIES, MODE_REVIEW

    assert MODE_REVIEW in FOLLOW_UP_MODES
    # 기업 목록 없이 문구만 나간다
    assert MODE_REVIEW not in MODES_WITH_COMPANIES

    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    r = client.post("/api/deals/preview", json={
        "mode": "review", "contact_ids": [seed["contact_id"]], "company_ids": []})
    assert r.status_code == 200, r.text
    assert "미팅" in r.json()["previews"][0]["message"]


def test_review_template_kind_is_editable(client, db, seed):
    """문구를 고칠 수 없으면 기본 문장만 계속 나간다."""
    from app.routers.templates_crud import KIND_LABELS

    assert "meeting_review" in KIND_LABELS
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    assert "미팅 후기" in client.get("/templates").text


# --- 탭 ↔ 문구 매핑 -----------------------------------------------------------
#
# 탭마다 쓰는 문구 종류가 하나씩 정해져 있다. 이 표가 어긋나도 화면에는 아무
# 티가 안 난다 — 문구를 아무리 고쳐도 그 탭의 발송 내용만 안 바뀐다.

def test_every_tab_points_at_a_real_template_kind():
    """없는 종류를 가리키면 그 탭의 문구를 문구 관리 화면에서 찾을 수가 없다."""
    from app.routers.deals import MODE_TEMPLATE_KIND
    from app.routers.templates_crud import KIND_LABELS

    unknown = {mode: kind for mode, kind in MODE_TEMPLATE_KIND.items()
               if kind not in KIND_LABELS}
    assert not unknown, unknown


def test_every_mode_has_a_name():
    """이름이 없으면 회차 제목이 '딜소개 회차' 로만 남아 무엇을 보냈는지 모른다."""
    from app.routers.deals import MODE_TEMPLATE_KIND, MODE_TITLES

    missing = set(MODE_TEMPLATE_KIND) - set(MODE_TITLES)
    assert not missing, missing
    assert all(MODE_TITLES[mode].strip() for mode in MODE_TEMPLATE_KIND)


def test_the_tabs_and_the_mapping_are_the_same_set(logged_in):
    """탭은 있는데 매핑이 없으면 그 탭은 기본 문구로 떨어진다 — 고쳐도 안 바뀐다.

    반대로 매핑만 있고 탭이 없으면, 고칠 수 있다고 적힌 문구를 쓸 자리가 없다.
    """
    import re

    from app.routers.deals import MODE_TEMPLATE_KIND

    body = logged_in.get("/deals").text
    block = body[body.index('id="mode-tabs"'):]
    block = block[:block.index("</div>")]

    tabs = set(re.findall(r'data-mode="(\w+)"', block))
    assert tabs == set(MODE_TEMPLATE_KIND), tabs ^ set(MODE_TEMPLATE_KIND)


def test_the_template_screen_says_which_tab_uses_it(logged_in):
    """문구가 열다섯 종류인데 어느 것을 고쳐야 그 탭이 바뀌는지 알 수 없었다."""
    from app.routers.deals import MODE_TEMPLATE_KIND, MODE_TITLES

    body = logged_in.get("/templates").text
    for mode, kind in MODE_TEMPLATE_KIND.items():
        assert 'id="%s"' % kind in body, kind          # 고칠 자리가 화면에 있어야 한다
        assert MODE_TITLES[mode] in body, mode         # 어느 탭에서 쓰는지 적혀 있어야 한다


def test_멈춰_둔_사람은_오래된_탭에서_눌러도_안_나간다(client, db, seed):
    """화면에서 뺀 사람이 **서버에서도** 빠져야 진짜로 빠진 것이다.

    딜 제안 관리 목록에는 이미 안 뜨지만, 목록을 띄워 둔 채 다른 탭에서
    `검토중단` 으로 바꾸고 돌아와 [보내기]를 누르면 그대로 나갔다 — 나간 뒤에는
    되돌릴 수가 없다. 판정은 `sheet_owner` 한 곳을 지난다.
    """
    from app.models import VcContact
    from app.services import sheet_owner

    row = db.get(VcContact, seed["contact_id"])
    row.status = sheet_owner.STATUS_PAUSED
    db.commit()

    r = client.post("/api/deals/send", json={
        "company_ids": [seed["company_id"]],
        "contact_ids": [seed["contact_id"]],
    })
    assert r.status_code == 400, r.text
    # 왜 막혔는지 말한다 — 이유가 없으면 고장으로 읽고 다시 누른다.
    assert sheet_owner.STATUS_LABELS[sheet_owner.STATUS_PAUSED] in r.json()["detail"]

    # 되돌리면 다시 나간다 — 멈추기는 지우기가 아니다.
    row.status = sheet_owner.STATUS_ACTIVE
    db.commit()
    again = client.post("/api/deals/send", json={
        "company_ids": [seed["company_id"]],
        "contact_ids": [seed["contact_id"]],
    })
    assert again.status_code == 200, again.text
