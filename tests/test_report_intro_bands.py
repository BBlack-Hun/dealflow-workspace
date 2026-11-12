"""업무 보고 `소개 후보` — 투자유치희망금액으로 골라 보기 · 안 보낸 기업 모두(#174 팀원 요청).

요청: "업무보고 > 소개후보 투자유치희망금액 5억이하 /5-10억 / 10억이상으로 검색가능하게 >
딜소개 안한스타트업 모두 볼수있게 그리고 체크해서 딜 제안관리에서 딜소개 발송가능하게".

  1. 묶음 — 5억 이하 · 5~10억 · 10억 이상 · 알 수 없음(빈칸 · `~` · 못 읽는 글자). 구간은 아래·위를
     같이 본다: 아래 ≥ 10 → 10억 이상, 위 ≤ 5 → 5억 이하, 나머지(걸친 구간) → 5~10억
  2. 후보 — 금액과 상관없이 그 달에 안 보낸 소개 가능 기업 모두, 금액 높은 순 · 모르는 곳은 맨 아래
  3. 화면 — 묶음 단추(수 포함) · `band=` 로 고르면 그 묶음 줄만 서고 체크도 그 줄에만
  4. 체크 → [딜 소개] 는 예전 그대로(#164 — tests/test_report_intro_counts.py)

이름은 전부 지어낸 것이다 — 저장소가 공개다.
"""
from __future__ import annotations

import json
import re
from datetime import date

import pytest

from .conftest import DEMO_PASSWORD


@pytest.mark.parametrize("value, band", [
    ("3", "le5"), ("5", "le5"), ("5천만원", "le5"), ("2~5억", "le5"),
    ("5-10억", "5to10"), ("7", "5to10"), ("8~15억", "5to10"), ("3~20억", "5to10"),
    ("10", "ge10"), ("10-20억", "ge10"), ("30억", "ge10"),
    (None, "unknown"), ("", "unknown"), ("~", "unknown"), ("확인필요", "unknown"),
    ("10억 이상", "unknown"),
])
def test_금액_묶음(value, band):
    from app.services import report

    assert report.raise_band(value) == band


@pytest.fixture()
def stage(db, users):
    from app.models import ContactActivity, IrCompany, VcContact

    db.add_all([
        IrCompany(name="샘플큰곳", raise_target="30", sector_major="AI"),
        IrCompany(name="샘플중간", raise_target="5-10억", sector_major="AI"),
        IrCompany(name="샘플딱오", raise_target="5", sector_major="AI"),
        IrCompany(name="샘플작은곳", raise_target="3", sector_major="AI"),
        # 금액은 모르지만 다른 숫자(누적투자금액)가 있어 소개 가능하다.
        IrCompany(name="샘플모름", raise_target="~", funding_total="5", sector_major="AI"),
        IrCompany(name="샘플빈금액", funding_total="2", sector_major="AI"),
        IrCompany(name="샘플보냄", raise_target="2", sector_major="AI"),
        IrCompany(name="샘플막힘", raise_target="3", sector_major="AI", contract_status="blocked"),
    ])
    who = VcContact(user_id=users["u1"].id, name="가상갑", firm="가나벤처스")
    db.add(who)
    db.flush()
    db.add(ContactActivity(contact_id=who.id, kind="deal_intro", content="공유",
                           happened_at="2026-08-12", source="manual",
                           company_names=json.dumps(["샘플보냄"], ensure_ascii=False)))
    db.commit()


def test_안_보낸_기업_모두_금액_높은_순_모르면_맨_아래(stage, db, users):
    from app.services import report

    left = report.monthly(db, 2026, 8, users["u1"], today=date(2026, 11, 7))["intro_left"]
    assert [(c["company"], c["band"]) for c in left] == [
        ("샘플큰곳", "ge10"),
        ("샘플딱오", "le5"), ("샘플중간", "5to10"),   # 아래값이 같은 5억 — 이름 순 그대로
        ("샘플작은곳", "le5"),
        ("샘플모름", "unknown"), ("샘플빈금액", "unknown"),
    ], "보낸 곳 · 딜소개 불가는 빠지고 나머지는 금액과 상관없이 다 선다"


def _login(client):
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})


def _names(html):
    return re.findall(r"<td><b>([^<]*)</b></td>", html[html.index('id="intro-left"'):])


def _chips(html):
    nav = re.search(r'<nav [^>]*data-testid="intro-bands"[^>]*>(.*?)</nav>', html, re.S).group(1)
    return [(re.sub(r"\s+", " ", name).strip(), int(n), "active" in cls, href)
            for cls, href, name, n in re.findall(
                r'<a class="([^"]*)"\s+href="([^"]*)"[^>]*>([^<]*)<b>(\d+)</b></a>', nav)]


def test_화면에_묶음_단추가_수와_함께_서고_전체가_기본(stage, client):
    _login(client)
    page = client.get("/report?month=2026-08").text
    assert "소개 후보 — 8월 딜소개 하지 않은 기업 6곳" in page
    chips = _chips(page)
    assert [(name, n, on) for name, n, on, _href in chips] == [
        ("전체", 6, True), ("5억 이하", 2, False), ("5~10억", 1, False),
        ("10억 이상", 1, False), ("알 수 없음", 2, False)]
    # 단추는 지금 주소(달 · 보기)를 지킨 채 `band=` 만 바꾼다.
    hrefs = {name: href for name, _n, _on, href in chips}
    assert "month=2026-08" in hrefs["5억 이하"] and "band=le5" in hrefs["5억 이하"]
    assert hrefs["5억 이하"].endswith("#intro-left")
    assert "band=" not in hrefs["전체"]
    assert _names(page) == ["샘플큰곳", "샘플딱오", "샘플중간", "샘플작은곳", "샘플모름", "샘플빈금액"]


def test_묶음을_고르면_그_줄만_서고_체크도_그_줄에만(stage, client, db):
    from app.models import IrCompany

    _login(client)
    page = client.get("/report?month=2026-08&band=le5").text
    assert _names(page) == ["샘플딱오", "샘플작은곳"]
    ids = {c.name: str(c.id) for c in db.query(IrCompany)}
    assert re.findall(r'class="js-intro-pick" value="(\d+)"', page) == \
        [ids["샘플딱오"], ids["샘플작은곳"]], "안 보이는 줄의 체크가 [딜 소개] 에 섞이면 안 된다"
    assert [on for _name, _n, on, _href in _chips(page)] == [False, True, False, False, False]
    assert 'id="intro-left-send"' in page, "체크 → 딜 소개 단추는 그대로 선다(#164)"

    assert _names(client.get("/report?month=2026-08&band=unknown").text) == ["샘플모름", "샘플빈금액"]
    # 모르는 값이면 전체.
    assert len(_names(client.get("/report?month=2026-08&band=xx").text)) == 6


def test_고른_묶음에_줄이_없으면_빈칸_문구(stage, client, db):
    from app.models import IrCompany

    db.query(IrCompany).filter(IrCompany.name == "샘플중간").delete()
    db.commit()
    _login(client)
    page = client.get("/report?month=2026-08&band=5to10").text
    assert "이 금액에 드는 소개 후보가 없습니다." in page
    assert not re.findall(r'class="js-intro-pick"', page)
