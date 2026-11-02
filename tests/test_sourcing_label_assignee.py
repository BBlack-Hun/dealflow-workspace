"""i137 · i138 (11/02) — 딜 소싱 시리즈 A 탭의 보이는 이름 · 담당자 칸의 팀원 보기.

i137 — `시리즈 A 이상 딜 소싱 참여 심사역` 탭을 `Series A 이상 딜 검토 가능 심사역` 으로
부른다. **저장 글자(갈래 열쇠)는 그대로다** — 줄 · 문구 · 잇기 · 자동 리마인드가 그
글자로 찾고, 문구 모양(`sourcing_msg.is_series_a`)도 이름으로 읽는다.

i138 — 담당자 칸 고르는 창의 보기가 표에 이미 적힌 글자뿐이라, 그 탭에 없는 팀원은
고를 수 없었다. 팀 활성 계정의 사람 이름을 먼저 세운다(직접 적기도 그대로).
"""
from __future__ import annotations

import re
from urllib.parse import quote

from .conftest import DEMO_PASSWORD

SERIES_A = "시리즈 A 이상 딜 소싱 참여 심사역"
SHOWN = "Series A 이상 딜 검토 가능 심사역"


def _login(client):
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})


def test_series_a_tab_shows_new_name_but_keeps_the_key(client, db, users):
    from app.models import SourcingContact
    from app.services import sourcing_msg

    db.add(SourcingContact(bucket=SERIES_A, position=1, name="가심사"))
    db.commit()
    _login(client)
    html = client.get(f"/sourcing?tab={quote(SERIES_A)}").text
    tab = re.search(r'<a class="sheet-tab active"\s+href="([^"]*)">([^<]*)<span>', html)
    assert tab.group(2).strip() == SHOWN
    # 주소 · 추가 단추의 값은 저장 글자 그대로 — 그 글자로 갈래를 찾는다.
    assert tab.group(1) == f"/sourcing?tab={quote(SERIES_A)}"
    assert f'data-bucket="{SERIES_A}"' in html and f"{SHOWN}에 추가" in html
    # 잇는 갈래는 이름을 못 바꾼다 — 저장 글자가 보이는 [이름 저장] 칸을 세우지 않는다.
    assert 'action="/sourcing/buckets/rename"' not in html
    assert db.query(SourcingContact).one().bucket == SERIES_A
    assert sourcing_msg.is_series_a(SERIES_A)        # 문구 모양은 그대로

    picker = client.get("/deals?mode=sourcing").text
    assert f'data-value="{SERIES_A}" data-label="{SHOWN}"' in picker
    assert f'<span class="tag">{SHOWN}</span>' in picker


def test_assignee_picker_offers_team_names_and_saves_another_member(client, db, users):
    from app.models import SourcingContact, User

    db.add_all([
        User(id=3, name="팀원C_BACKUPONE", phone="01000000003", role="user"),
        User(id=4, name="컨설턴트D", phone="01000000004", role="consultant"),
        User(id=5, name="정지E", phone="01000000005", role="user", is_active=0),
    ])
    row = SourcingContact(bucket=SERIES_A, position=1, name="가심사", assignee_name="팀원A")
    db.add(row)
    db.commit()
    _login(client)
    html = client.get(f"/sourcing?tab={quote(SERIES_A)}").text
    cell = re.search(r'<td class="cell" data-field="assignee_name"[^>]*>', html).group(0)
    choices = re.search(r'data-choices="([^"]*)"', cell).group(1).split(",")
    assert "팀원C" in choices                         # `_BACKUP…` 꼬리는 뗀다
    assert not any("_BACKUP" in c or c in ("컨설턴트D", "정지E") for c in choices)

    # 일반 팀원이 다른 팀원 이름을 적어도 저장된다(표시용 글 칸 — 권한은 그대로).
    r = client.patch(f"/api/sourcing/{row.id}", json={"assignee_name": "팀원C"})
    assert r.status_code == 200 and r.json()["assignee"] == "팀원C"
    db.expire_all()
    assert db.get(SourcingContact, row.id).assignee_name == "팀원C"
