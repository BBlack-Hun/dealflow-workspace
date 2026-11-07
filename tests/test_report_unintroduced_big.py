"""업무 보고 `소개한 기업`(#122) — 계약 두 칸 + 맨 아래 `소개 후보`(아직 소개 안 한 기업) 묶음.

#174 부터 소개 후보는 금액과 상관없이 다 선다(금액 묶음 고르기는 tests/test_report_intro_bands.py).
이 파일의 자료에서 10억 미만인 곳은 소개 가능이 아니라서 아래 결과는 예전과 같다.

  1. 기업명(· 투자유치희망금액) 오른쪽 계약여부 · 계약서 수신 여부 — IR 값, IR 에 없으면 Series A
  2. 묶음 — 소개 가능한 IR 기업 중 투자유치희망금액(구간이면 아래값) 10억 이상이고 **보는 달에**
     그 팀원 받은 기록에 없는 곳, 금액 높은 순. 팀 전체(본인 없음)에는 안 띄운다.
  3. 화면 — 10곳만 펼치고 나머지는 `더 보기`
  4. 화면 차례 — 소개한 기업 표(없으면 빈칸 문구)가 먼저, 후보 묶음은 그 아래(11/02)

이름은 전부 지어낸 것이다 — 저장소가 공개다.
"""
from __future__ import annotations

import io
import json
from datetime import date

import pytest

from .conftest import DEMO_PASSWORD

openpyxl = pytest.importorskip("openpyxl")


@pytest.fixture()
def stage(db, users):
    from app.models import ContactActivity, IrCompany, SeriesACompany, VcContact

    db.add_all([
        IrCompany(name="샘플큰가", raise_target="30", sector_major="AI",
                  series="Series A (누적 10억 이상)", contract_status="paid"),
        IrCompany(name="샘플큰나", raise_target="10-20억", sector_major="바이오"),
        IrCompany(name="샘플보냄", raise_target="40", sector_major="AI", contract_status="free",
                  contract_received="O"),
        IrCompany(name="샘플작음", raise_target="5~15억"),                 # 아래값 5억
        IrCompany(name="샘플막힘", raise_target="50", contract_status="blocked"),
        IrCompany(name="샘플표시 [딜소개 불가]", raise_target="50"),
        IrCompany(name="샘플닫음 [26년 3월 폐업함]", raise_target="50"),
        IrCompany(name="샘플빈칸"),
        IrCompany(name="샘플보류", raise_target="60", sector_major="AI",
                  summary_status="insufficient"),                         # 소개 가능 아님
        IrCompany(name="샘플분야없음", raise_target="70"),                 # 문구 못 만듦
        SeriesACompany(name="샘플에이랩", contract_status="paid", contract_received="X"),
    ])
    who = VcContact(user_id=users["u1"].id, name="가상갑", firm="가나벤처스")
    db.add(who)
    db.flush()
    db.add(ContactActivity(contact_id=who.id, kind="deal_intro", content="공유",
                           happened_at="2026-08-12", source="manual",
                           company_names=json.dumps(["샘플보냄", "샘플에이랩"],
                                                    ensure_ascii=False)))
    db.commit()


def test_계약_두_칸은_IR_값_없으면_Series_A_값(stage, db, users):
    from app.services import report

    got = report.intro_companies(db, date(2026, 8, 1), date(2026, 8, 31), users["u1"])
    rows = {c["company"]: (c["contract_label"], c["contract_received"]) for c in got["rows"]}
    assert rows == {"샘플보냄": ("무료계약완료", "O"), "샘플에이랩": ("유료계약완료", "X")}


def test_보는_달에_안_보낸_10억_이상만_금액_높은_순(stage, db, users):
    from app.services import report

    aug = report.monthly(db, 2026, 8, users["u1"], today=date(2026, 11, 1))
    assert [(c["company"], c["raise_target"]) for c in aug["intro_left"]] == \
        [("샘플큰가", "30억"), ("샘플큰나", "10~20억")]
    assert aug["intro_left"][0]["series"] == "Series A"
    assert aug["intro_left"][0]["contract_label"] == "유료계약완료"
    # 9월에는 샘플보냄도 안 보냈다 — 기준은 보는 달이다.
    sep = report.monthly(db, 2026, 9, users["u1"], today=date(2026, 11, 1))
    assert [c["company"] for c in sep["intro_left"]] == ["샘플보냄", "샘플큰가", "샘플큰나"]
    # 팀 전체에는 '본인' 이 없다.
    assert report.monthly(db, 2026, 8, None, today=date(2026, 11, 1))["intro_left"] == []


def test_화면은_10곳만_펼치고_엑셀에_계약_칸(stage, client, db, users):
    from app.models import IrCompany

    db.add_all([IrCompany(name=f"샘플더{i:02d}", raise_target=str(11 + i), sector_major="AI") for i in range(10)])
    db.commit()
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})

    page = client.get("/report?month=2026-08").text
    assert "소개 후보 — 8월에 아직 안 보낸 기업 12곳" in page
    head, _, more = page.partition("더 보기 — 나머지 2곳")
    assert more, "10곳이 넘으면 나머지는 접혀야 한다"
    assert "샘플더09" in head and "샘플큰나" in more, "금액 높은 순으로 10곳이 먼저 선다"
    assert "소개 후보 —" not in client.get("/report?span=year&year=2026").text

    wb = openpyxl.load_workbook(io.BytesIO(
        client.get("/api/export/report.xlsx?month=2026-08").content))
    rows = [list(r) for r in wb["2026-08 소개한 기업"].iter_rows(values_only=True)]
    head = next(r for r in rows if r and r[0] == "기업명")
    # 기업명 바로 오른쪽은 소개한 횟수다(#165) — 그 옆으로 금액 · 계약 두 칸.
    assert head[:5] == ["기업명", "본인 소개 횟수", "투자유치희망금액", "계약여부", "계약서 수신 여부"]
    assert ["샘플보냄", 1, "40억", "무료계약완료", "O"] in [r[:5] for r in rows]


def test_소개_0인_달은_빈칸_문구가_후보보다_먼저(stage, client, users):
    """9월엔 보낸 게 없다 — 후보 표가 위에 서면 '소개한 기업' 처럼 읽혔다(11/02)."""
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})

    page = client.get("/report?month=2026-09").text
    empty = page.index("이 기간에 소개한 기업이 없습니다.")
    assert "9월 소개한 기업" in page[:empty]
    assert empty < page.index("소개 후보 — 9월에 아직 안 보낸 기업 3곳")
    # 보낸 달도 소개한 기업 표가 먼저다.
    aug = client.get("/report?month=2026-08").text
    assert aug.index("<summary><b>샘플보냄</b></summary>") < aug.index("소개 후보 — 8월에")
