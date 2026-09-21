"""투자컨설턴트 줄 여러 개를 골라 **스타트업 명단에 세우기.**

요청은 "건바이건이 아니라 체크박스로 다건" 이었다. 그런데 두 화면은 **표가
다르다**(`ConsultingCompany` ↔ `VcContact`). 그래서 이 길은 이관이 아니라
`POST /api/contacts` 로 **줄을 새로 세우는** 일이고, 원본은 그대로 남는다.

여기서 지키는 것은 넷이다.

  · **무엇이 어느 칸에 들어가나** — 스타트업 배치는 기업이 주인공이라
    `기업명`(`firm`)이 필수고 `성함`(`name`)은 기업 쪽 사람이다. 투자사
    배치와 반대라, 뒤바뀌면 표의 고정 칸에 대표자 이름만 줄줄이 선다.
  · **이미 있는 기업** — 말없이 두 줄이 생기는 것이 제일 나쁘다.
  · **권한** — 남의 명단에 줄을 세울 수 없고, 투자컨설턴트는 이 길을 못 쓴다.
  · **원본** — 지우지 않는다. 대신 두 화면에 다 있다는 것이 표에 보인다.
"""
from __future__ import annotations

import re

import pytest

from .conftest import DEMO_PASSWORD

SEND = "/api/contacts/from-consulting"
MY_LIST = "스타트업 · 가담당"
OTHER_LIST = "스타트업 · 나담당"


@pytest.fixture()
def people(db, users):
    """관리자와 투자컨설턴트를 더한다. 권한 갈래가 넷이라 넷 다 필요하다."""
    from app.models import User
    from app.services import auth as auth_svc

    pw = auth_svc.hash_password(DEMO_PASSWORD)
    db.add_all([
        # **관리자도 이 화면은 켜 줘야 본다.** 역할이 이 판정에 안 낀다
        # (`deps.may_view_consulting` — 계정마다 켜고 끈다).
        User(id=3, name="관리자", phone="01000000003", role="admin",
             password_hash=pw, can_view_consulting=1),
        User(id=4, name="다컨설", phone="01000000004", role="consultant",
             password_hash=pw, can_view_consulting=1),
    ])
    # 이 화면을 볼 수 있는 팀원 둘. `u1` 이 보내는 사람이고 `u2` 는 남의 명단
    # 주인이다 — 남의 명단으로 못 보내는지를 재려면 주인이 따로 있어야 한다.
    users["u1"].can_view_consulting = 1
    users["u2"].can_view_consulting = 1
    db.commit()
    return users


@pytest.fixture()
def sheets(db, people):
    """스타트업 화면에 사는 명단 둘 — 하나는 내 것, 하나는 남의 것.

    `layout="startup"` 이 곧 **그 명단이 스타트업 화면에 산다**는 뜻이다
    (`contact_columns.Layout.page`). 이름으로 가르지 않는다.
    """
    from app.models import SheetOwner

    db.add_all([
        SheetOwner(label=MY_LIST, user_id=1, layout="startup", is_hidden=1),
        SheetOwner(label=OTHER_LIST, user_id=2, layout="startup", is_hidden=1),
        # 담당이 없는 명단. 고르는 목록에 **안 떠야** 한다 — 거기 세운 줄은
        # 담당이 없어 어느 팀원 화면에도 안 뜬다.
        SheetOwner(label="스타트업 · 미배정", user_id=None, layout="startup",
                   is_hidden=1),
    ])
    db.commit()


@pytest.fixture()
def tabs(db):
    """투자컨설턴트 탭 셋. 탭 이름은 DB 값이라 코드가 모른다."""
    from app.services import consulting_sheets as cs

    rows = {s.kind: s.label for s in cs.ensure(db)}
    return {"startup": rows[cs.STARTUP], "handover": rows[cs.HANDOVER],
            "contract": rows[cs.CONTRACT]}


def _company(db, tabs, *, name, owner=1, sheet=None, **kw):
    from app.models import ConsultingCompany

    row = ConsultingCompany(user_id=owner, sheet=sheet or tabs["startup"],
                            company_name=name, **kw)
    db.add(row)
    db.commit()
    return row


def _login(client, phone):
    client.post("/login", data={"phone": phone, "password": DEMO_PASSWORD})
    return client


@pytest.fixture()
def sender(client, sheets):
    """보내는 사람 — 이 화면을 보고, 자기 스타트업 명단을 가진 팀원."""
    return _login(client, "01000000001")


def _contacts(db, label=MY_LIST):
    from app.models import VcContact

    rows = db.query(VcContact).order_by(VcContact.id).all()
    return [c for c in rows if label in (c.source_sheet or "")]


# ── ⓐ 칸 짝짓기 ─────────────────────────────────────────────────────────────

def test_기업명은_성함이_아니라_기업명_칸에_들어간다(sender, db, tabs):
    """스타트업 배치는 **기업이 주인공**이다(`STARTUP_LAYOUT.required = firm`).

    투자사 배치와 반대라, 여기서 한 번 뒤집히면 그 명단의 고정 칸에 대표자
    이름만 줄줄이 서서 어느 기업 줄인지 알 수가 없다.
    """
    row = _company(db, tabs, name="샘플애그", ceo_name="홍길동",
                   phone="010-0000-0001", email="hong@example.com",
                   management="관리 중 : 미팅 완.\n-> 견적서 보내기 완료.")

    r = sender.post(SEND, json={"company_ids": [row.id], "label": MY_LIST})
    assert r.status_code == 200, r.text
    assert r.json()["added"] == ["샘플애그"]

    made = _contacts(db)
    assert len(made) == 1
    made = made[0]
    assert made.firm == "샘플애그", "기업명이 `기업명` 칸에 안 들어갔습니다"
    assert made.name == "홍길동", "대표자가 `성함` 칸에 안 들어갔습니다"
    assert made.phone == "010-0000-0001"
    assert made.email == "hong@example.com"
    # 자유 문장 기록끼리 짝을 짓는다. 줄바꿈은 뜻이 있어 그대로 남는다.
    assert made.memo == "관리 중 : 미팅 완.\n-> 견적서 보내기 완료."


def test_담당은_명단_주인이지_보낸_사람이_아니다(sender, db, tabs, people):
    """`sheet_owner.owner_for` 가 이미 정한 규칙이다.

    보낸 사람을 담당으로 적으면, 관리자가 팀원 명단에 보내는 순간 그 줄만
    담당이 관리자로 서서 **정작 그 팀원 화면에는 안 뜬다**.
    """
    row = _company(db, tabs, name="샘플메디")
    _login(sender, "01000000003")            # 관리자가 남의 명단으로 보낸다
    assert sender.post(SEND, json={"company_ids": [row.id],
                                   "label": MY_LIST}).status_code == 200
    assert _contacts(db)[0].user_id == 1, "명단 주인이 아니라 보낸 사람이 담당입니다"


def test_카톡방_이름은_안_짓는다(sender, db, tabs):
    """방 제목 규칙은 `이름·직함·투자사` 라 기업 명단에 쓸 것이 아니다.

    지으면 연결 상태가 `연결 완료` 로 따라 서서, 아무도 연결한 적 없는 줄이
    발송 대상에 뜬다. 막는 것은 `create_contact` 안의 `layout.page` 판정
    하나다 — 여기서는 그 길을 지나는지만 잰다.
    """
    row = _company(db, tabs, name="샘플바이오", ceo_name="김서연")
    sender.post(SEND, json={"company_ids": [row.id], "label": MY_LIST})
    made = _contacts(db)[0]
    assert not made.kakao_room_name
    assert made.connect_stage == "not_started"


def test_계약_O_X_칸은_안_옮긴다(sender, db, tabs):
    """같은 물음을 적는 칸이 이미 셋이고 **값을 주고받지 않는다**.

    (`models.IrCompany.contract_received` 주석) 여기서 한 번 베껴 넣으면
    그 뒤로 두 화면이 조용히 갈라진다 — 넷째 자리를 만들지 않는다.
    """
    row = _company(db, tabs, name="샘플테크", contract_received="O",
                   contract_done="유료계약완료", contract_management="O",
                   kakao_joined="O")
    sender.post(SEND, json={"company_ids": [row.id], "label": MY_LIST})
    made = _contacts(db)[0]
    assert not made.kakao_joined
    assert not (made.notes or "").strip("{} \n"), \
        "닮은 이름의 O/X 칸이 몰래 따라왔습니다"


# ── ⓑ `company_name` 한 칸에 여러 값 ────────────────────────────────────────

@pytest.mark.parametrize("raw,expected", [
    ("샘플애그", "샘플애그"),
    # 실제 자료의 세 줄짜리 — **첫 줄이 기업명**이다.
    ("샘플메디\n9.19/ 유료/\n계약금/ 3.3%", "샘플메디"),
    # 한 줄에 슬래시로 이어 붙인 것.
    ("샘플바이오 / 무료 / 3%", "샘플바이오"),
    ("샘플테크 / 9.1", "샘플테크"),
    ("  샘플가   \n", "샘플가"),
    ("", ""),
])
def test_기업명을_한_칸에서_꺼낸다(raw, expected):
    """`기업명/계약일/무료유료/계약금, 성과수수료 %` — 한 칸이 아니다.

    **줄을 먼저 자르고 슬래시를 자른다.** 순서를 뒤집으면 세 줄짜리에서
    둘째 줄의 날짜가 기업명에 붙어 온다.
    """
    from app.services import startup_handoff

    assert startup_handoff.company_name_of(raw) == expected


def test_기업명을_못_꺼낸_줄만_빼고_나머지는_들어간다(sender, db, tabs):
    """`Layout.required` 가 막는 줄이다. 거기서 400 으로 멈추면 **나머지까지**
    통째로 안 들어가, 사람은 아무 일도 안 일어난 줄 안다."""
    blank = _company(db, tabs, name="   ")
    good = _company(db, tabs, name="샘플가")

    r = sender.post(SEND, json={"company_ids": [blank.id, good.id],
                                "label": MY_LIST})
    assert r.status_code == 200, r.text
    assert r.json()["added"] == ["샘플가"]
    assert r.json()["blank"] == [blank.id]
    assert [c.firm for c in _contacts(db)] == ["샘플가"]


# ── ⓕ 이미 있는 기업 ────────────────────────────────────────────────────────

def test_이미_스타트업_명단에_있는_기업은_건너뛴다(sender, db, tabs):
    """**말없이 두 줄이 생기는 것이 제일 나쁘다.**

    `(주)` 와 띄어쓰기는 같은 기업으로 본다 — 맞추는 규칙은 이 저장소가 이미
    쓰는 `deal_history._key` 하나다.
    """
    from app.models import VcContact

    db.add(VcContact(user_id=1, name="", firm="(주) 샘플애그",
                     source_sheet=MY_LIST))
    db.commit()
    row = _company(db, tabs, name="샘플애그")

    r = sender.post(SEND, json={"company_ids": [row.id], "label": MY_LIST})
    assert r.status_code == 200
    assert r.json()["added"] == []
    assert r.json()["skipped"] == ["샘플애그"], "무엇을 건너뛰었는지 안 알려 줍니다"
    assert len(_contacts(db)) == 1, "같은 기업이 두 줄이 됐습니다"


def test_다른_사람의_스타트업_명단에_있어도_건너뛴다(sender, db, tabs):
    """겹침은 **화면 단위**로 본다. 남의 명단에 이미 있는 기업을 내 명단에
    또 세우면, 같은 기업을 두 팀원이 각자 챙기게 된다."""
    from app.models import VcContact

    db.add(VcContact(user_id=2, name="", firm="샘플메디",
                     source_sheet=OTHER_LIST))
    db.commit()
    row = _company(db, tabs, name="샘플메디")

    assert sender.post(SEND, json={"company_ids": [row.id],
                                   "label": MY_LIST}).json()["skipped"] == ["샘플메디"]


def test_투자사_명단에_있는_기업은_겹침이_아니다(sender, db, tabs):
    """투자사 명단은 **다른 화면**이다(`Layout.page`). 거기 같은 이름이 있다고
    스타트업 명단에 못 세우면, 세울 길이 조용히 막힌다."""
    from app.models import VcContact

    db.add(VcContact(user_id=1, name="이심사", firm="샘플애그",
                     source_sheet="투자사 30명"))
    db.commit()
    row = _company(db, tabs, name="샘플애그")

    assert sender.post(SEND, json={"company_ids": [row.id],
                                   "label": MY_LIST}).json()["added"] == ["샘플애그"]


def test_한_번에_고른_같은_기업도_두_줄이_안_된다(sender, db, tabs):
    """같은 기업이 두 줄로 적힌 표가 실제로 있다. 둘 다 골라 누르면 새 명단에
    두 줄이 선다 — 요청 안에서도 막는다."""
    a = _company(db, tabs, name="샘플가")
    b = _company(db, tabs, name="(주)샘플가")

    r = sender.post(SEND, json={"company_ids": [a.id, b.id], "label": MY_LIST})
    assert r.json()["added"] == ["샘플가"]
    assert r.json()["skipped"] == ["(주)샘플가"]
    assert len(_contacts(db)) == 1


def test_표에_이미_있음_표시가_선다(sender, db, tabs):
    """원본을 안 지우므로 **같은 기업이 두 화면에 있다는 것**이 보여야 한다.

    그리고 그 줄은 체크 칸이 아예 안 서서, 눌렀다가 조용히 건너뛰는 일도
    안 생긴다. 표시와 서버의 건너뛰기는 **같은 판정** 하나를 읽는다.
    """
    from app.models import VcContact

    db.add(VcContact(user_id=1, name="", firm="샘플애그", source_sheet=MY_LIST))
    db.commit()
    here = _company(db, tabs, name="샘플애그")
    there = _company(db, tabs, name="샘플메디")

    rows = sender.get("/consulting").text
    assert f'value="{there.id}"' in rows, "아직 안 보낸 줄에 체크 칸이 없습니다"
    assert f'value="{here.id}"' not in rows, "이미 있는 줄에 체크 칸이 섰습니다"
    # **체크 표시가 아니라 글자다.** 체크 칸 바로 옆자리라, `✓` 를 쓰면 골라
    # 놓은 줄로 읽혀 위 막대의 `0개 선택` 과 화면이 서로 다른 말을 한다.
    assert 'class="in-startup"' in rows and ">있음<" in rows
    assert ">✓<" not in rows


# ── ⓔ 원본 ──────────────────────────────────────────────────────────────────

def test_원본은_지우지도_옮기지도_않는다(sender, db, tabs):
    """이 표의 줄에는 월별 리마인드 기록과 계약 칸이 붙어 있다."""
    from app.models import ConsultingCompany

    row = _company(db, tabs, name="샘플애그", ceo_name="홍길동")
    sender.post(SEND, json={"company_ids": [row.id], "label": MY_LIST})

    kept = db.get(ConsultingCompany, row.id)
    assert kept is not None, "원본이 사라졌습니다"
    assert kept.sheet == tabs["startup"], "원본이 다른 탭으로 옮겨졌습니다"
    assert kept.company_name == "샘플애그"


# ── ⓒ 어느 탭에서 ───────────────────────────────────────────────────────────

def test_다른_탭에서는_보낼_수_없다(sender, db, tabs):
    """`경영본부 전달 기업` 은 이미 넘긴 기업이고, 계약 탭에는 연락처 칸 자체가
    없다 — 거기서 보내면 연락할 길이 없는 줄이 선다."""
    for key in ("handover", "contract"):
        row = _company(db, tabs, name=f"샘플{key}", sheet=tabs[key])
        r = sender.post(SEND, json={"company_ids": [row.id], "label": MY_LIST})
        assert r.status_code == 400, f"{key} 탭에서 보내졌습니다"
        assert tabs["startup"] in r.json()["detail"]
    assert _contacts(db) == []


def test_체크_칸은_그_탭에만_선다(sender, db, tabs):
    """화면도 서버와 같은 탭 판정을 쓴다 — 갈리면 눌러도 400 이 나는 칸이 된다."""
    _company(db, tabs, name="샘플애그")
    _company(db, tabs, name="샘플메디", sheet=tabs["handover"])

    assert "cs-startup-bar" in sender.get("/consulting").text
    other = sender.get("/consulting", params={"sheet": tabs["handover"]}).text
    assert "cs-startup-bar" not in other
    assert 'class="cs-pick"' not in other


# ── ⓖ 권한 ──────────────────────────────────────────────────────────────────

def test_투자컨설턴트는_이_길을_못_쓴다(client, db, tabs, sheets):
    """자기 화면 하나만 보는 계정이다(`deps.CONSULTANT_PATHS`).

    보이지도 않는 명단에 줄을 세우면 세워 놓고 확인할 길이 없고, 잘못 넣어도
    되돌릴 화면이 없다. 막는 것은 **주소**다 — 이 길이 `/api/contacts/…` 밑에
    있어서 미들웨어가 끊는다. 라우터에는 역할 판정이 한 줄도 없다.
    """
    row = _company(db, tabs, name="샘플애그", owner=4)
    _login(client, "01000000004")
    assert client.post(SEND, json={"company_ids": [row.id],
                                   "label": MY_LIST}).status_code == 403
    assert _contacts(db) == []
    # 화면에도 그 자리가 아예 안 선다 — 눌러도 아무 일이 없는 단추를 안 만든다.
    assert "cs-startup-bar" not in client.get("/consulting").text


def test_남의_명단으로는_못_보낸다(sender, db, tabs):
    """`sheet_owner.may_add_row` — 명단 주인이거나 관리자다.

    화면이 그 명단을 안 보여 주지만, 화면만 감추면 이름을 직접 보내는 길이
    남는다.
    """
    row = _company(db, tabs, name="샘플애그")
    r = sender.post(SEND, json={"company_ids": [row.id], "label": OTHER_LIST})
    assert r.status_code == 403
    assert _contacts(db, OTHER_LIST) == []
    # 고르는 자리에도 안 뜬다.
    page = sender.get("/consulting").text
    assert MY_LIST in page and OTHER_LIST not in page


def test_관리자는_남의_명단에도_보낼_수_있다(sender, db, tabs, people):
    row = _company(db, tabs, name="샘플애그")
    _login(sender, "01000000003")
    assert sender.post(SEND, json={"company_ids": [row.id],
                                   "label": OTHER_LIST}).status_code == 200
    assert _contacts(db, OTHER_LIST)[0].user_id == 2


def test_담당이_없는_명단으로는_못_보낸다(sender, db, tabs):
    """거기 세운 줄은 담당이 없어 어느 팀원 화면에도 안 뜬다."""
    row = _company(db, tabs, name="샘플애그")
    r = sender.post(SEND, json={"company_ids": [row.id],
                                "label": "스타트업 · 미배정"})
    assert r.status_code == 400
    assert "스타트업 · 미배정" not in sender.get("/consulting").text


def test_투자사_명단으로는_못_보낸다(sender, db, tabs):
    """명단마다 사는 화면이 다르다. 투자사 명단에 기업 줄을 세우면 그 줄이
    투자사 수와 발송 대상에 섞여 든다."""
    from app.models import SheetOwner

    db.add(SheetOwner(label="투자사 30명", user_id=1, layout="investor"))
    db.commit()
    row = _company(db, tabs, name="샘플애그")
    assert sender.post(SEND, json={"company_ids": [row.id],
                                   "label": "투자사 30명"}).status_code == 400


def test_표에_없는_번호는_조용히_지나가지_않는다(sender, db, tabs, people):
    """읽는 범위는 `scope()` 하나다 — 여기서 다시 적으면 화면에는 없는데
    번호로는 되는 길이 생긴다.

    **오늘은 이 화면을 볼 수 있는 사람이면 표 전체를 본다**
    (`deps.may_view_all_consulting` — 컨설턴트만 자기 줄로 좁혀지는데, 그
    계정은 이 주소 자체가 막혀 있다). 그래서 여기서 잴 수 있는 것은 "없는
    번호가 조용히 지나가지 않는가" 다. 범위가 좁아지는 날 이 길이 같이
    움직이는 것은 `scope()` 를 부르기 때문이지 여기 적힌 조건 때문이 아니다.
    """
    row = _company(db, tabs, name="샘플애그")
    r = sender.post(SEND, json={"company_ids": [row.id, row.id + 999],
                                "label": MY_LIST})
    assert r.status_code == 404
    assert _contacts(db) == [], "절반만 들어갔습니다"


def test_고른_것이_없으면_아무_일도_안_한다(sender, db, tabs):
    assert sender.post(SEND, json={"company_ids": [], "label": MY_LIST}
                       ).status_code == 400


# ── ⑨ 수정 로그 ─────────────────────────────────────────────────────────────

def test_남의_명단에_세운_줄은_수정_로그에_남는다(sender, db, tabs, people):
    """줄을 `POST /api/contacts` 로 세우므로 `vc_contacts` 의 INSERT 가 세션
    flush 를 지난다 — 로그를 따로 부르는 자리가 없다(`services/edit_log.py`)."""
    from app.models import EditLog

    row = _company(db, tabs, name="샘플애그")
    _login(sender, "01000000003")            # 관리자가 남의 명단으로 보낸다
    sender.post(SEND, json={"company_ids": [row.id], "label": MY_LIST})

    logs = [x for x in db.query(EditLog).all() if x.table_name == "vc_contacts"]
    assert logs, "남의 명단에 줄을 세웠는데 수정 로그가 비었습니다"
    assert logs[0].action == "create"
    # 줄이 **무엇인가**. 이 명단은 `성함` 이 비어 있는 줄이 흔해서, 이름만
    # 읽으면 `vc_contacts 12` 로 남는다(`edit_log._contact_label`).
    assert logs[0].row_label == "샘플애그"
    assert logs[0].actor_user_id == 3
    assert logs[0].target_user_id == 1, "누구 명단에 생긴 줄인지 안 남았습니다"
    # 어디서 눌러 일어난 일인가 — 같은 표를 여러 화면이 고친다.
    assert logs[0].path == SEND


# ── 화면 ────────────────────────────────────────────────────────────────────

def test_이관이라고_부르지_않는다():
    """이 저장소에서 `이관`(`sheet_owner.move_to`)은 **담당을 바꾸고 옛 명단에서
    빼는** 일이다. 여기는 원본이 그대로 남으므로 같은 말을 쓰면 누른 사람이
    투자컨설턴트 표에서 빠진 줄 안다."""
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    for rel in ("app/templates/consulting.html",
                "app/static/js/consulting_to_startup.js"):
        text = (root / rel).read_text(encoding="utf-8")
        # 주석에서는 "이관이 아니다" 라고 설명한다 — 화면 글자만 본다.
        shown = [line for line in text.splitlines()
                 if "이관" in line and "아니" not in line and "move_to" not in line]
        assert not shown, f"{rel} 에 `이관` 이라는 화면 글자가 있습니다: {shown}"


def test_빈_표_안내_줄이_체크_칸까지_센다(sender, db, tabs):
    """칸 수가 어긋나면 안내 줄이 짧거나 길어져 표 오른쪽이 어긋난다."""
    body = sender.get("/consulting").text
    head = body[body.index("<thead>"):body.index("</thead>")]
    # `<thead>` 도 `<th` 로 시작한다 — 여는 꺾쇠 뒤 한 글자까지 본다.
    columns = len(re.findall(r"<th[ >]", head))
    assert f'colspan="{columns}"' in body, \
        f"머리글은 {columns}칸인데 빈 표 안내 줄이 그 수가 아닙니다"


@pytest.mark.skipif(__import__("shutil").which("node") is None,
                    reason="node 미설치 — 브라우저 로직 테스트 생략")
def test_화면_코드를_그대로_돌려_본다():
    """[전체 선택]이 **검색으로 숨긴 줄까지** 켜면, 화면에 없는 기업이 남의
    명단에 선다. 규칙을 파이썬으로 옮겨 적으면 두 벌이 되어 어긋나도 모른다.
    """
    import pathlib as _p
    import shutil
    import subprocess

    js = _p.Path(__file__).resolve().parent / "js" / "consulting_to_startup_test.js"
    r = subprocess.run([shutil.which("node"), str(js)],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr
