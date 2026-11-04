"""#152 — IR 기업 현황 · Series A 이상 딜 소싱: 검색이 **표의 글 칸 전부**를 찾는다.

팀원 요청: "IR 기업현황, Series A > 검색 (모든 컬럼에 들어가 있는 거로 이름, 성함,
메일주소, 기업소개, 연락처 등등 모두 다 검색 되게)".

검색 방식은 그대로다 — 서버가 줄마다 검색 글자(`data-search`)를 싣고 화면이 그 안에서
찾는다. 그 글자에 칸을 더 실었다. 여기서 보는 것:

  ① IR 기업 현황 — 새로 실린 칸(수신일 · 지역 · 정책자금 · 담당자 · 매출 · 계약여부 ·
     IR 자료 …)과 [수정] 창에만 있는 글(대표 카톡방 · 합치기 전 값)
  ② 안 싣는 칸 — `O` · `X` 한 글자 칸
  ③ 추가 칸(관리자가 붙인 칸) — 메모 칸 글은 실리고, O/X · 숨긴 칸은 안 실린다.
     표에서 적으면 응답이 새 검색 글자를 준다. `지금 화면 내려받기` 도 같은 글자로 거른다.
  ④ Series A — 계약여부 · 계약년월 · IR 쪽 자료 이름 · 추가 칸 · 번호 두 꼴 ·
     확정한 공유 심사역의 `휴대폰`

이름 · 회사 · 번호 · 메일은 전부 지어낸 값이다 — 저장소가 공개다.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from .test_series_a_share_review import today, world  # noqa: F401 - 픽스처


def _search_of(html: str, row_id: int) -> str:
    row = re.search(rf'<tr data-id="{row_id}" data-search="([^"]*)"', html)
    assert row, f"{row_id} 줄을 못 찾았다"
    return row.group(1)


def _memo_col(db, name="검토 메모", kind="memo", hidden=0):
    from app.models import CustomColumn

    col = CustomColumn(target="companies", name=name, kind=kind, is_hidden=hidden)
    db.add(col)
    db.commit()
    return col


@pytest.fixture()
def ir(db):
    from app.models import IrCompany

    row = IrCompany(
        name="샘플가온", received_at="2026-10-07", contact_name="김샘플",
        contact_phone="010-0000-7788", contact_email="gaon@example.com",
        region="전남 나주", guarantee="기보 3억", founded_year="2019년",
        assignee_name="샘플담당", revenue_recent="12.5", funding_total="5-10억",
        contract_status="paid", contract_ym="2026-11", success_fee="3%",
        contract_month="삭제 완료", meeting_offered_at="9월 중", top_deal_kind="핵심",
        ir_file_name="샘플가온_IR_2026.pdf", kakao_room_name="김샘플 대표 샘플가온 방",
        desc_backup=json.dumps({"one_liner": "옛 소개 수경재배",
                                "business_desc": "옛 사업분야 스마트팜"},
                               ensure_ascii=False),
        quote_attached="O", kakao_joined="X", contract_received="O")
    db.add(row)
    db.commit()
    return row


# ── ① IR 기업 현황 — 새로 실린 칸 ────────────────────────────────────────────

def test_IR_표의_글_칸과_수정창_글이_검색_글자에_실린다(logged_in, ir):
    hay = _search_of(logged_in.get("/companies").text, ir.id)
    for word in ("2026-10-07", "전남 나주", "기보 3억", "2019년", "샘플담당", "12.5",
                 "5-10억", "유료계약완료", "2026-11", "3%", "삭제 완료", "9월 중", "핵심",
                 "샘플가온_ir_2026.pdf",
                 # [수정] 창에만 있는 글
                 "김샘플 대표 샘플가온 방", "옛 소개 수경재배", "옛 사업분야 스마트팜"):
        assert word.lower() in hay, f"{word} 로 검색이 안 된다"
    # 계약여부는 칸에 보이는 말로 — 저장된 열쇠(`paid`)가 아니다.
    assert "paid" not in hay


def test_전화번호는_하이픈이_있든_없든_찾힌다(db, ir):
    """줄에는 두 꼴이 실리고, 숫자만 친 검색은 서버 쪽 거르기(`지금 화면 내려받기`)도 맞힌다."""
    from app.routers.companies import company_rows
    from app.services.company_view import match_search

    row = next(r for r in company_rows(db) if r["id"] == ir.id)
    assert "010-0000-7788" in row["search"] and "01000007788" in row["search"]
    for typed in ("01000007788", "010-0000-7788", "010 0000 7788", "7788"):
        assert match_search(row, typed), typed


# ── ② 안 싣는 칸 ─────────────────────────────────────────────────────────────

def test_OX_한_글자_칸은_안_싣는다(db):
    """`견적서 첨부 여부` · `카톡 연결 여부` · `계약서 수신 여부` — 머리글 필터가 거른다."""
    from app.models import IrCompany
    from app.routers.companies import search_text

    row = IrCompany(name="샘플나루", quote_attached="O", kakao_joined="X",
                    contract_received="O")
    db.add(row)
    db.commit()
    assert search_text(row) == "샘플나루 미계약"


# ── ③ 추가 칸 ─────────────────────────────────────────────────────────────────

def test_IR_추가_칸은_메모_글만_실리고_적으면_응답이_새_글자를_준다(logged_in, db, ir):
    from app.models import CustomColumnValue

    memo = _memo_col(db)
    ox = _memo_col(db, "투자 검토", kind="ox")
    hidden = _memo_col(db, "옛 칸", hidden=1)
    db.add_all([
        CustomColumnValue(column_id=memo.id, row_table="ir_companies", row_id=ir.id,
                          value="샘플 후속 검토"),
        CustomColumnValue(column_id=ox.id, row_table="ir_companies", row_id=ir.id,
                          value="X"),
        CustomColumnValue(column_id=hidden.id, row_table="ir_companies", row_id=ir.id,
                          value="숨긴 칸 글자"),
    ])
    db.commit()

    hay = _search_of(logged_in.get("/companies").text, ir.id)
    assert "샘플 후속 검토" in hay
    assert "숨긴 칸 글자" not in hay, "화면에 없는 칸의 글로 줄이 걸린다"

    res = logged_in.put(f"/api/custom-values/ir_companies/{ir.id}",
                        json={"column_id": memo.id, "value": "샘플 재미팅 예정"})
    assert res.status_code == 200, res.text
    assert "샘플 재미팅 예정" in res.json()["search"]
    assert "샘플 후속 검토" not in res.json()["search"]
    # 표에서 다른 칸을 고쳐도(PATCH) 추가 칸 글이 검색 글자에서 빠지지 않는다.
    res = logged_in.patch(f"/api/companies/{ir.id}", json={"region": "서울"})
    assert "샘플 재미팅 예정" in res.json()["search"] and "서울" in res.json()["search"]


def test_지금_화면_내려받기도_추가_칸_글로_거른다(db, ir):
    """화면과 서버가 같은 검색 글자(`company_rows`)를 본다 — 한쪽만 걸리면 받은 파일이 화면과 다르다."""
    from app.models import CustomColumnValue, IrCompany
    from app.routers.companies import company_rows
    from app.services.company_view import view_rows

    other = IrCompany(name="샘플다른")
    memo = _memo_col(db)
    db.add(other)
    db.add(CustomColumnValue(column_id=memo.id, row_table="ir_companies", row_id=ir.id,
                             value="샘플 후속 검토"))
    db.commit()
    shown = view_rows(company_rows(db), {}, q="후속 검토")
    assert [r["id"] for r in shown] == [ir.id]


# ── ④ Series A 이상 딜 소싱 ──────────────────────────────────────────────────

def test_SeriesA_계약_칸_번호_IR_자료_추가_칸이_실린다(logged_in, db, ir):
    from app.models import CustomColumnValue, SeriesACompany

    deal = SeriesACompany(name="샘플가온", received_at="2026-10-01",
                          ceo_name="이샘플", ceo_phone="010-0000-2233",
                          contract_status="review", contract_ym="2026-12")
    alone = SeriesACompany(name="샘플혼자", received_at="2026-10-02",
                           ir_file_name="샘플혼자_deck.pdf")
    db.add_all([deal, alone])
    db.commit()
    memo = _memo_col(db)
    db.add(CustomColumnValue(column_id=memo.id, row_table="series_a_companies",
                             row_id=deal.id, value="샘플 딜 메모"))
    db.commit()

    html = logged_in.get("/companies?tab=series-a").text
    hay = _search_of(html, deal.id)
    for word in ("계약검토중", "2026-12", "010-0000-2233", "01000002233", "샘플 딜 메모",
                 # IR 기업 현황에도 있는 기업 — `IR 자료` 칸은 IR 쪽 파일 이름을 보인다.
                 "샘플가온_ir_2026.pdf"):
        assert word.lower() in hay, f"{word} 로 검색이 안 된다"
    assert "샘플혼자_deck.pdf" in _search_of(html, alone.id)

    res = logged_in.put(f"/api/custom-values/series_a_companies/{deal.id}",
                        json={"column_id": memo.id, "value": "샘플 새 메모"})
    assert res.status_code == 200, res.text
    assert "샘플 새 메모" in res.json()["search"]
    # 표에서 칸을 고친 응답(`_result`)도 추가 칸 글을 잃지 않는다.
    res = logged_in.patch(f"/api/series-a-companies/{deal.id}", json={"memo": "샘플 줄 메모"})
    assert "샘플 새 메모" in res.json()["search"] and "샘플 줄 메모" in res.json()["search"]


def test_SeriesA_확정한_공유_심사역의_휴대폰으로_찾힌다(world, client, db):
    from app.models import SourcingContact

    own = world["c"]["own"]
    b = world["p"]["b"]
    db.get(SourcingContact, b.id).phone = "010-0000-4455"
    db.commit()

    res = client.put(f"/api/series-a-companies/{own.id}/sharer", json={"contact_id": b.id})
    assert res.status_code == 200, res.text
    assert "010-0000-4455" in res.json()["search"] and "01000004455" in res.json()["search"]
    assert "01000004455" in _search_of(client.get("/companies?tab=series-a").text, own.id)

    # 해제하면 그 번호로는 더 안 걸린다(칸이 빈칸이 된다).
    res = client.put(f"/api/series-a-companies/{own.id}/sharer", json={"contact_id": None})
    assert "01000004455" not in res.json()["search"]


def test_SeriesA_검색칸도_모든_칸이라고_말한다():
    """자리표시가 실제보다 좁게 말하면, 되는 칸도 안 되는 줄 알고 안 쳐 본다."""
    html = (Path(__file__).resolve().parent.parent / "app" / "templates"
            / "companies_series_a.html").read_text(encoding="utf-8")
    box = re.search(r'<input type="search" id="sa-search"(.*?)>', html, re.S).group(1)
    assert "모든 칸" in re.search(r'placeholder="([^"]*)"', box).group(1)
    title = re.search(r'title="([^"]*)"', box).group(1)
    for word in ("대표자명", "연락처", "이메일", "휴대폰", "추가 칸", "뒷자리"):
        assert word in title, f"검색되는데 설명에 {word} 가 없다"
