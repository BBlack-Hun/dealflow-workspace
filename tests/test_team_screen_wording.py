"""팀 현황 · 수정 로그 · 데이터 되돌리기 — 화면 글자가 **실제 값**을 말하는가 (UX 점검 11/16).

여기서 못 박는 것.

1. **권한 칸(§18-2).** 본인 줄은 고르개 대신 글자(`관리자 (본인)`)다 — 라우터가 본인
   권한 바꾸기를 막는 것과 같은 판단이다. 다른 관리자 줄의 고르개에는 `관리자` 가
   선택지로 있고 골라져 있다(현재 값이 목록 밖에 서지 않는다).
2. **하루 상한 기본값(§18-4).** 글자는 `send_guard.DEFAULT_DAILY_CAP` 에서 온다.
   계정마다 저장된 상한(예: 1000)은 표의 칸에 그대로 서고, 기본값 글자를 바꾸지 않는다.
3. **자동화 일정(§18-5).** 이름은 이름만이고, 일정은 **저장된 설정**으로 적힌다 —
   요일을 수요일로 바꾸면 `화요일` 이 남지 않는다.
4. **수정 로그의 칸 이름 · 코드값.** `contract_management` · `none → free` 대신 화면 이름.
   저장된 로그는 그대로다(보여 줄 때만 바꾼다).
5. **되돌리기 지점 종류.** 파일 이름 머리로 사람이 읽는 종류를 단다.
"""
from __future__ import annotations

import json

import pytest

from .conftest import DEMO_PASSWORD


def _admin(client, db, users):
    """u1 · u2 둘 다 관리자 — u1 으로 로그인한다."""
    users["u1"].role = "admin"
    users["u2"].role = "admin"
    db.commit()
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    return client


def _role_cell(page: str, member_id: int) -> str:
    """팀원 표에서 그 사람 줄의 권한 칸(다음 칸 시작 전까지)."""
    rows = [chunk for chunk in page.split("<tr") if f"/team/members/{member_id}/" in chunk]
    assert rows, f"{member_id} 줄이 없다"
    return rows[0]


# ── 1. 권한 칸 ───────────────────────────────────────────────────────────────

def test_the_own_row_shows_the_role_as_text_not_a_picker(client, db, users):
    page = _admin(client, db, users).get("/team").text
    own = [chunk for chunk in page.split("<tr") if "<b>강민준</b>" in chunk][0]
    assert 'action="/team/members/1/role"' not in own
    assert "관리자" in own and "(본인)" in own


def test_another_admin_keeps_admin_among_the_choices(client, db, users):
    page = _admin(client, db, users).get("/team").text
    row = _role_cell(page, 2)
    picker = row.split('action="/team/members/2/role"', 1)[1].split("</select>", 1)[0]
    assert '<option value="admin"      selected>관리자</option>' in picker
    assert picker.count("<option") == 3


# ── 2. 하루 상한 기본값 ───────────────────────────────────────────────────────

def test_the_default_cap_label_comes_from_the_constant_and_saved_caps_stay(client, db, users):
    from app.services import send_guard

    users["u2"].daily_send_cap = 1000
    page = _admin(client, db, users).get("/team").text
    panel = page.split('data-testid="send-guard-panel"', 1)[1].split("</section>", 1)[0]
    assert f"<b>{send_guard.DEFAULT_DAILY_CAP}건</b>" in panel
    assert "새 계정" in panel
    # 저장된 값은 표의 칸에 그대로 — 기본값 글자와 다를 수 있다.
    assert 'name="cap_2"' in panel
    cap_2 = panel.split('name="cap_2"', 1)[1].split(">", 1)[0]
    assert 'value="1000"' in cap_2


# ── 3. 자동화 일정은 설정값에서 ───────────────────────────────────────────────

def _save_params(db, key, **params):
    from app.models import Automation
    from app.services import automation

    row = automation.load(db, key) or Automation(key=key, enabled=0, test_mode=1)
    automation.set_params(row, params)
    db.add(row)
    db.commit()
    return row


def test_the_sourcing_remind_line_follows_the_saved_weekday(db, users):
    from app.services import automation, automation_runner as runner

    _save_params(db, automation.SOURCING_REMIND, weeks="2", weekday="수", time="10:30",
                 groups=["갈래"])
    summary = runner.status_of(db, automation.SOURCING_REMIND)["summary"]
    assert summary.startswith("매월 2주차 수요일 10:30")
    assert "화요일" not in summary
    # 이름에는 일정이 붙지 않는다.
    assert automation.BY_KEY[automation.SOURCING_REMIND].label == "소싱 리마인드"


def test_the_team_page_draws_the_saved_schedule(client, db, users):
    from app.services import automation

    _save_params(db, automation.SOURCING_REMIND, weeks="2,4", weekday="수", time="10:00",
                 groups=["갈래"])
    page = _admin(client, db, users).get("/team").text
    row = page.split('data-automation="sourcing_remind"', 1)[1].split("</tr>", 1)[0]
    assert "매월 2·4주차 수요일 10:00" in row
    assert "2주차 화요일" not in row


def test_the_startup_monthly_line_follows_the_saved_slots(db, users):
    from app.services import automation, automation_runner as runner

    _save_params(db, automation.STARTUP_MONTHLY, slots=["2주 화 10:00", "20 15:00"],
                 variants=1)
    summary = runner.status_of(db, automation.STARTUP_MONTHLY)["summary"]
    assert "홀수 달 2주차 화요일 10:00 · 짝수 달 20일 15:00" in summary
    assert "목요일" not in summary


@pytest.mark.parametrize("key,params,needle", [
    ("channel_top", {"weekday": "금", "time": "15:00", "count": 5}, "매주 금요일 15:00"),
    ("meeting_request", {"first_days": 5, "second_days": 9, "time": "11:00",
                         "second_time": "16:00"}, "5일 뒤 11:00"),
    ("contract_day7", {"time": "11:30"}, "7일 뒤 11:30"),
    ("followup_notice", {"time": "09:30"}, "평일 09:30"),
])
def test_every_schedule_line_reads_the_saved_time(db, users, key, params, needle):
    from app.services import automation_runner as runner

    _save_params(db, key, **params)
    assert needle in runner.status_of(db, key)["summary"]


def test_the_contract_automation_has_no_english_day_word():
    from app.services import automation

    assert "Day" not in automation.BY_KEY[automation.CONTRACT_DAY7].label


# ── 4. 수정 로그는 화면 이름으로 ──────────────────────────────────────────────

def _log(db, table, changes, action="update"):
    from app.models import EditLog

    db.add(EditLog(actor_user_id=1, scope="shared", action=action, table_name=table,
                   row_id=7, screen="IR 기업 현황", row_label="가나다",
                   changes_json=json.dumps(changes, ensure_ascii=False)))
    db.commit()


def test_the_log_shows_screen_names_instead_of_column_names(db, users):
    from app.models import EditLog
    from app.services import edit_log

    _log(db, "ir_companies", [
        {"field": "contract_status", "before": "none", "after": "free"},
        {"field": "kakao_joined", "before": None, "after": "O"},
        {"field": "is_top_deal", "before": 0, "after": 1},
        {"field": "summary_status", "before": "draft", "after": "done"},
        {"field": "revenue_2024", "changed": True},
    ])
    _log(db, "consulting_companies", [
        {"field": "contract_management", "before": None, "after": "O"}])
    _log(db, "vc_contacts", [{"field": "kakao_joined", "before": "X", "after": "O"}])

    rows = edit_log.recent(db)
    seen = {(row["changes"][0]["label"]) for row in rows}
    assert "견적서 첨부 여부" in seen          # `contract_management` 의 화면 이름
    assert "카톡방 참여여부" in seen            # 투자사 쪽 `kakao_joined`
    ir = next(r for r in rows if len(r["changes"]) == 5)["changes"]
    shown = {c["label"]: (c.get("before"), c.get("after")) for c in ir}
    assert shown["계약 상태"] == ("미계약", "무료계약완료")
    assert shown["카톡 연결 여부"] == ("(빈 값)", "O")
    assert shown["추천 딜"] == ("X", "O")
    assert shown["소개 상태"] == ("작성 중", "작성 완료")
    assert "24년 매출" in shown
    # 저장된 로그는 그대로다 — 보여 줄 때만 바꾼다.
    stored = db.query(EditLog).filter_by(table_name="ir_companies").one().changes_json
    assert '"none"' in stored and '"free"' in stored


def test_the_log_page_has_no_raw_column_names(client, db, users):
    _log(db, "ir_companies", [{"field": "contract_status", "before": "none", "after": "free"},
                              {"field": "contract_management", "before": None, "after": "O"}])
    page = _admin(client, db, users).get("/team/edit-log").text
    table = page.split('class="grid-table compact log-table"', 1)[1].split("</table>", 1)[0]
    assert "contract_management" not in table
    assert "none" not in table
    assert "미계약" in table and "무료계약완료" in table and "견적서 첨부 여부" in table


# ── 5. 되돌리기 지점 종류 ─────────────────────────────────────────────────────

@pytest.mark.parametrize("name,kind", [
    ("daily-20261116.db", "일일 자동"),
    ("predeploy-20261116-0900.db", "업데이트 직전"),
    ("before-restore-20261116-0900.db", "되돌리기 직전"),
    ("snapshot-before-tab-delete-20261116-0900.db", "탭 삭제 직전"),
    ("snapshot-before-somejob-20261113-1806.db", "작업 직전"),
    ("hand-made.db", "수동 백업"),
])
def test_restore_points_get_readable_kinds(name, kind):
    from app.services import backup

    assert backup._kind_of(name) == kind
