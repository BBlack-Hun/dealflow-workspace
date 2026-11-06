"""업무 보고 · IR 기업 현황의 소개한 횟수(#165)와 소개 후보 → 딜 소개(#164) — 11/06 팀원 요청.

#165 "업무보고 > 기업명 오른쪽에 본인이 소개한 횟수 · IR 기업현황 담당별로 소개한 횟수 · 총 소개 횟수"
#164 "업무보고 > 딜소개 안한기업 > 체크박스 클릭해서 > 딜 소개를 할수 있게"

여기서 못 박는 것:

1. **두 화면이 같은 수다.** IR 기업 현황의 `총 소개 횟수` = 업무 보고 팀 전체의 `소개한 횟수`,
   `담당별 소개` 의 계정 수 = 업무 보고 그 사람의 `소개한 횟수`(기간을 다 덮으면). 셈은
   서로 다른 날 수 — 같은 날 여러 계정 · 여러 회차는 하루, 안 나간 회차는 안 센다.
2. 업무 보고 `소개한 기업` 표의 소개한 횟수는 **기업명 바로 오른쪽**이고 이름이 보기를 말한다
   (본인 · 팀). 엑셀도 같은 자리 · 같은 이름이다.
3. `소개 후보` 의 `본인 누적 소개` 는 기간 없이 센 그 계정 수 — IR `담당별 소개` 와 같다.
4. `소개 후보` 의 체크 · [딜 소개] — 보고의 주인이 지금 계정일 때만 선다(본인 · 팀원 화면으로
   보기). 관리자가 주소 `member=` 로 남의 보고를 열면 안 선다. 단추는 딜 제안 관리로 가는 링크라
   그 화면이 같은 번호의 기업 상자를 그린다.

이름은 전부 지어낸 것이다 — 저장소가 공개다.
"""
from __future__ import annotations

import io
import json
import re
from datetime import date

import pytest

from .conftest import DEMO_PASSWORD

openpyxl = pytest.importorskip("openpyxl")

TWIN = "샘플쌍둥"     # 두 계정이 같은 날 보낸 기업
BIG = "샘플큰곳"      # 7월에만 소개한 10억 이상 — 8월 소개 후보


def _login(client, phone):
    client.post("/login", data={"phone": phone, "password": DEMO_PASSWORD})


def _batch(db, user, day, company, contacts, status="sent", job_status="done"):
    from app.models import DealBatch, DealBatchCompany, SendItem, SendJob

    batch = DealBatch(user_id=user.id, title=f"회차 {day}", sent_date=day)
    db.add(batch)
    db.flush()
    db.add(DealBatchCompany(batch_id=batch.id, company_id=company.id, position=1))
    job = SendJob(user_id=user.id, kind="deal_intro", batch_id=batch.id, status=job_status)
    db.add(job)
    db.flush()
    db.add_all([SendItem(job_id=job.id, contact_id=c.id, room_name="방", message="본문",
                         status=status) for c in contacts])


def _activity(db, contact, day, company, source):
    from app.models import ContactActivity

    db.add(ContactActivity(contact_id=contact.id, kind="deal_intro", content="공유",
                           happened_at=day, source=source,
                           company_names=json.dumps([company], ensure_ascii=False)))


@pytest.fixture()
def stage(db, users):
    from app.models import IrCompany, VcContact

    twin = IrCompany(name=TWIN, raise_target="50", sector_major="AI")
    big = IrCompany(name=BIG, raise_target="30", sector_major="바이오")
    a1, a2 = (VcContact(user_id=users["u1"].id, name=f"가상{i}", firm="가나벤처스")
              for i in range(2))
    b1 = VcContact(user_id=users["u2"].id, name="가상남", firm="다라벤처스")
    db.add_all([twin, big, a1, a2, b1])
    db.flush()
    u1, u2 = users["u1"], users["u2"]
    # 8/03 — u1 이 두 회차(그룹마다), u2 도 같은 날 한 회차. 팀으로는 그날 하루.
    _batch(db, u1, "2026-08-03", twin, [a1])
    _batch(db, u1, "2026-08-03", twin, [a2])
    _batch(db, u2, "2026-08-03", twin, [b1])
    # 8/10 — 시트에서 옮긴 줄(지금 담당 u1 것).
    _activity(db, a1, "2026-08-10", TWIN, "import")
    # 8/12 — u1 이 세워만 두고 안 보낸 회차. 받은 사람이 없으니 안 센다.
    _batch(db, u1, "2026-08-12", twin, [a1], status="pending", job_status="draft")
    # 9/02 — u2 가 손으로 적은 줄.
    _activity(db, b1, "2026-09-02", TWIN, "manual")
    # 큰 곳 — 7월에 u1 이 두 번(시트 · 앱). 8월에는 아무도 안 보냈다.
    _activity(db, a1, "2026-07-15", BIG, "import")
    _batch(db, u1, "2026-07-20", big, [a2])
    db.commit()
    return {"twin": twin, "big": big}


def _ir_row(db, name):
    from app.routers.companies import company_rows

    return next(r for r in company_rows(db) if r["name"] == name)


def _times(rows, name):
    return {c["company"]: c["times"] for c in rows["rows"]}.get(name)


# ── 1. 두 화면이 같은 수 ────────────────────────────────────────────────────

def test_IR_총_소개_횟수는_업무_보고_팀_전체와_같다(stage, db, users):
    from app.services import report

    row = _ir_row(db, TWIN)
    team = report.yearly(db, 2026, None, date(2026, 11, 6))["intro_companies"]
    # 8/03(세 회차 · 두 계정) · 8/10 · 9/02 — 서로 다른 날 셋. 안 나간 8/12 는 없다.
    assert row["intro_total"] == _times(team, TWIN) == 3
    # 옛 셈(회차 수)은 여섯이었다 — 같은 날 회차마다 · 안 나간 회차까지 셌다.
    assert row["sent_rounds"] == 6


def test_IR_담당별_소개는_업무_보고_그_사람_수와_같다(stage, db, users):
    from app.services import report

    row = _ir_row(db, TWIN)
    u1, u2 = users["u1"], users["u2"]
    year = (date(2026, 1, 1), date(2026, 12, 31))
    mine = {u.name: _times(report.intro_companies(db, *year, u), TWIN) for u in (u1, u2)}
    assert {o["name"]: o["times"] for o in row["intro_by_owner"]} == mine == \
        {u1.name: 2, u2.name: 2}
    # 계정마다의 합(4)은 총(3)보다 크다 — 같은 날 두 계정이 보냈으면 팀으로는 하루다.
    assert sum(o["times"] for o in row["intro_by_owner"]) == 4 > row["intro_total"]
    # 많은 순 · 같으면 이름 순.
    assert [o["name"] for o in row["intro_by_owner"]] == sorted([u1.name, u2.name])


def test_달로_자르면_업무_보고는_그_달만_센다(stage, db, users):
    from app.services import report

    today = date(2026, 11, 6)
    aug_u1 = report.monthly(db, 2026, 8, users["u1"], today)["intro_companies"]
    aug_team = report.monthly(db, 2026, 8, None, today)["intro_companies"]
    sep_u2 = report.monthly(db, 2026, 9, users["u2"], today)["intro_companies"]
    assert (_times(aug_u1, TWIN), _times(aug_team, TWIN), _times(sep_u2, TWIN)) == (2, 2, 1)


def test_IR_화면과_지금_화면_내려받기(stage, client, db, users):
    _login(client, "01000000001")
    page = client.get("/companies").text
    assert re.search(r'<th style="width:100px" data-sort="sent"[^>]*>총 소개 횟수</th>', page)
    assert re.search(r"<th[^>]*>담당별 소개</th>", page)
    row = page[page.index(f'data-s-name="{TWIN}"'):]
    row = row[:row.index("</tr>")]
    assert 'data-s-sent="3"' in row, "정렬도 새 셈의 수로 선다"
    sent = re.search(r'<td class="sent-count".*?</td>', row, re.S).group(0)
    assert "3회" in sent
    owners = re.search(r'<td class="intro-by-owner".*?</td>', row, re.S).group(0)
    u1, u2 = sorted([users["u1"].name, users["u2"].name])
    assert re.sub(r"<[^>]+>", "", owners.split(">", 1)[1]).split() == \
        [u1, "2", "·", u2, "2"]

    users["u1"].role = "admin"
    db.commit()
    wb = openpyxl.load_workbook(io.BytesIO(client.get("/api/export/companies-view.xlsx").content))
    head, *rows = [list(r) for r in wb.active.iter_rows(values_only=True)]
    by = dict(zip(head, next(r for r in rows if r[1] == TWIN)))
    assert (by["총 소개 횟수"], by["담당별 소개"]) == (3, f"{u1} 2 · {u2} 2")
    assert head.index("담당별 소개") == head.index("소개 발송(명)") + 1


# ── 2. 업무 보고 표 — 기업명 바로 오른쪽 · 보기를 말하는 이름 ──────────────────

def _intro_head(page):
    at = page.index('id="intros"')
    head = page[page.index("<thead>", at):page.index("</thead>", at)]
    return [re.sub(r"<[^>]+>", "", h).strip() for h in re.findall(r"<th\b.*?</th>", head, re.S)]


def test_소개한_횟수는_기업명_바로_오른쪽(stage, client, db, users):
    _login(client, "01000000001")
    page = client.get("/report?month=2026-08").text
    heads = _intro_head(page)
    assert heads[:3] == ["기업명", "본인 소개 횟수", "투자유치희망금액"]
    assert heads.count("본인 소개 횟수") == 1 and "소개한 횟수" not in heads, \
        "같은 수가 두 칸에 서면 안 된다"
    row = page[page.index(f"<summary><b>{TWIN}</b></summary>"):]
    cells = re.findall(r'<td class="num">([^<]*)</td>', row[row.index("</details>"):])
    assert cells[0] == "2", "기업명 다음 칸이 본인 소개 횟수(8/03 · 8/10)다"

    users["u1"].role = "admin"
    db.commit()
    team = client.get("/report?month=2026-08&scope=team").text
    assert _intro_head(team)[:2] == ["기업명", "팀 소개 횟수"]
    wb = openpyxl.load_workbook(io.BytesIO(
        client.get("/api/export/report.xlsx?month=2026-08&scope=team").content))
    grid = [list(r) for r in wb["2026-08 소개한 기업"].iter_rows(values_only=True)]
    assert next(r for r in grid if r and r[0] == "기업명")[:2] == ["기업명", "팀 소개 횟수"]
    assert next(r for r in grid if r and r[0] == TWIN)[1] == 2


# ── 3. 소개 후보의 누적 횟수 = IR 담당별 수 ─────────────────────────────────

def test_소개_후보_본인_누적은_IR_담당별_그_계정_수(stage, db, users):
    from app.services import report

    u1 = users["u1"]
    aug = report.monthly(db, 2026, 8, u1, date(2026, 11, 6))["intro_left"]
    assert [c["company"] for c in aug] == [BIG], "8월에 u1 이 안 보낸 10억 이상은 큰 곳뿐"
    ir = {o["name"]: o["times"] for o in _ir_row(db, BIG)["intro_by_owner"]}
    assert aug[0]["mine_times"] == ir[u1.name] == 2
    # 9월에는 쌍둥도 u1 이 안 보냈다 — 누적은 8월까지의 두 날.
    sep = {c["company"]: c["mine_times"] for c in
           report.monthly(db, 2026, 9, u1, date(2026, 11, 6))["intro_left"]}
    twin_ir = {o["name"]: o["times"] for o in _ir_row(db, TWIN)["intro_by_owner"]}
    assert sep == {TWIN: twin_ir[u1.name], BIG: 2} and sep[TWIN] == 2


# ── 4. 소개 후보 → [딜 소개] — 누가 볼 때 서나 ──────────────────────────────

def _picks(page):
    return re.findall(r'<input type="checkbox" class="js-intro-pick" value="(\d+)"', page)


def test_본인_보고에는_체크와_딜_소개_단추가_선다(stage, client):
    _login(client, "01000000001")
    page = client.get("/report?month=2026-08").text
    assert _picks(page) == [str(stage["big"].id)]
    btn = re.search(r'<a [^>]*id="intro-left-send"[^>]*>([^<]*)</a>', page)
    assert btn and btn.group(1) == "딜 소개 (선택 0개)"
    tag = btn.group(0)
    assert 'aria-disabled="true"' in tag and "href=" not in tag, "안 골랐으면 잠긴 채 선다"
    assert 'data-base="/deals"' in tag and 'data-max="10"' in tag
    assert "js/report_intro_pick.js" in page
    # 넘어갈 딜 제안 관리가 **같은 번호의 기업 상자**를 그린다 — 링크가 그 상자를 켠다.
    deals = client.get(f"/deals?companies={stage['big'].id}").text
    assert re.search(rf'class="company-cb" value="{stage["big"].id}"', deals)


def test_팀_전체에는_소개_후보가_없다(stage, client, db, users):
    users["u1"].role = "admin"
    db.commit()
    _login(client, "01000000001")
    page = client.get("/report?month=2026-08&scope=team").text
    assert 'id="intro-left"' not in page and not _picks(page)


def test_관리자가_주소로_연_남의_보고에는_안_선다(stage, client, db, users):
    """`member=` 로 열면 [딜 소개] 가 관리자 계정 명단으로 열린다 — 엉뚱하다."""
    users["u1"].role = "admin"
    db.commit()
    _login(client, "01000000001")
    page = client.get(f"/report?month=2026-08&member={users['u2'].id}").text
    assert 'id="intro-left"' in page, "u2 의 8월 소개 후보(큰 곳)는 보인다"
    assert not _picks(page) and 'id="intro-left-send"' not in page
    assert "팀원 화면으로 보기" in page[page.index('id="intro-left"'):]


def test_팀원_화면으로_보기_중에는_그_팀원_것으로_선다(stage, client, db, users):
    """관리자 대리 — 보기 · 수정, 딜 소개 발송은 그 팀원 PC 로(10/30 결정). 이 단추는 링크라
    딜 제안 관리가 그 규칙(`no_send_as_member`)대로 확인 · 발송한다."""
    from app.models import User
    from app.services import auth as auth_svc

    db.add(User(id=9, name="관리자", phone="01000000009", role="admin",
                password_hash=auth_svc.hash_password(DEMO_PASSWORD)))
    db.commit()
    _login(client, "01000000009")
    r = client.post("/account/view-as", data={"member_id": users["u2"].id, "next": "/"},
                    follow_redirects=False)
    assert r.status_code in (302, 303)
    page = client.get("/report?month=2026-08").text
    assert _picks(page) == [str(stage["big"].id)]
    assert 'id="intro-left-send"' in page
