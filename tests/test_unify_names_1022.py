"""비슷한 칸 이름 통일(10/22) — 기업 쪽은 IR 기업 현황 낱말, 투자사 쪽은 투자사 관리 현황 낱말.

사용자 요청: "비슷한 명칭의 단어는 하나로 통합해줘 (전체 메뉴 대상)". 바꾸는 것은
**화면 · 엑셀 · 필터의 이름뿐**이다 — 저장 자리(모델 칸 · `notes` 열쇠)와 원본 시트를
찾는 옛 머리글은 그대로 두고, 새 이름도 읽게 더한다.

같은 말인데 다른 사실인 칸은 오히려 갈라 부른다(컨설턴트 `컨설팅 미팅일` · `소개 메모`).
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _labels(columns):
    return {field: label for label, field in columns}


def test_투자컨설턴트_머리글():
    from app.routers import consulting as c

    fixed = _labels(c.FIXED_COLUMNS)
    assert fixed["meeting_at"].startswith("컨설팅 미팅일")
    assert _labels(c.TAIL_COLUMNS)["ceo_name"] == "대표자명"
    meta = _labels(c.STARTUP_COLUMNS)
    assert meta["contract_done"] == "계약여부"
    assert meta["contract_received"] == "계약서 수신 여부"
    assert meta["deal_pitch"] == "소개 메모"
    assert _labels(c.CONTRACT_COLUMNS)["contract_received"] == "계약서 수신 여부"
    assert c.CONTRACT_EXPORT_HEADERS[-1] == "계약서 수신 여부"
    assert c.STARTUP_EXPORT_HEADERS == ["소개 메모", "견적서 첨부 여부", "계약여부",
                                        "카톡 연결 여부"]
    html = (ROOT / "app" / "templates" / "consulting.html").read_text("utf-8")
    for label in ("컨설팅 미팅일", "대표자명", "소개 메모"):
        assert f">{label}</th>" in html, label
    for flt in ("done:계약여부", "received:계약서 수신 여부"):
        assert f'data-filters="{flt}"' in html, flt
    for old in (">미팅일</th>", ">대표자</th>", ">딜 소개문구</th>", "계약완료여부<",
                "계약서 수신완료여부<", "계약서 수신여부<"):
        assert old not in html, old


def test_투자컨설턴트_올리기는_내려받은_새_머리글도_읽는다():
    """내려받은 파일(새 이름)을 다시 올려도 같은 칸으로 간다 — 옛 시트 이름도 그대로."""
    from app.routers.consulting import parse_rows

    for head in ("계약여부", "계약완료여부"):
        parsed = parse_rows([["NO", "기업명", "컨설팅 미팅일(화상, 회의실)", head,
                              "계약서 수신 여부", "대표자명"],
                             ["1", "샘플기업", "9/1", "무료계약완료", "O", "김샘플"]])
        item = parsed["companies"][0]
        assert item["contract_done"] == "무료계약완료", head
        assert item["contract_received"] == "O"
        assert item["meeting_at"] == "9/1" and item["ceo_name"] == "김샘플"
        assert parsed["columns"] == [], parsed["columns"]


def test_스타트업_명단_머리글():
    from app.services import contact_columns as cc

    layout = cc.STARTUP_LAYOUT
    by_key = {c.key: c.label for c in list(layout.head) + list(layout.tail)
              + list(layout.extra)}
    assert by_key["name"] == "대표자명"
    assert by_key["sector_major"] == "대분류"
    assert by_key["company_kind"] == "투자라운드"
    assert by_key["ir_meeting_offered_at"] == "미팅제공일자"
    assert by_key["quote_attached"] == "견적서 첨부 여부"
    assert by_key["invoice_received"] == "계약서 수신 여부"
    assert by_key["success_fee"] == "성공보수율"
    # #87(10/29) — IR 기업 현황과 같은 `IR 자료`.
    assert by_key["ir_deck"] == "IR 자료"


def test_스타트업_시트_가져오기는_옛_이름과_새_이름을_둘_다_읽는다():
    from scripts.import_startup_sheet import parse

    for heads in (["NO", "기업명", "성함", "사업분야 대분류", "기업구분", "IR 미팅 제공일자",
                   "계산서 수신"],
                  ["NO", "기업명", "대표자명", "대분류", "투자라운드", "미팅제공일자",
                   "계약서 수신 여부"]):
        out = parse([heads, ["1", "샘플기업", "김샘플", "에듀테크", "Seed", "9/1", "O"]])
        item = out["items"][0]
        assert item["fields"]["name"] == "김샘플", heads
        assert item["notes"]["sector_major"] == "에듀테크", heads
        assert item["notes"]["company_kind"] == "Seed", heads
        assert item["notes"]["ir_meeting_offered_at"] == "9/1", heads
        assert item["notes"]["invoice_received"] == "O", heads
        assert out["columns"] == [], (heads, out["columns"])


def test_매출예상리스트_머리글():
    from app.services import forecast

    labels = {f: label for f, label, _s in forecast.COLUMNS}
    assert labels["firm"] == "회사"
    assert labels["vc_name"] == "심사역 이름"
    assert labels["vc_phone"] == "심사역 휴대폰"
    assert labels["ceo_name"] == "대표자명"
    assert labels["pre_value"] == "Pre Value"
    assert labels["raise_target"] == "투자유치희망금액"
    assert labels["fee_rate"] == "성공보수율"


def test_Series_A_머리글():
    html = (ROOT / "app" / "templates" / "companies_series_a.html").read_text("utf-8")
    assert 'data-filters="assignee:담당자">담당자<' in html
    assert ">딜 소개 문구</th>" in html
    assert "담당팀원<" not in html and ">딜소개 문구</th>" not in html


def test_추가_칸의_자리는_옛_이름으로_골라_둔_것도_새_이름을_따라간다():
    """`컬럼 관리` 에서 옛 머리글 뒤에 둔 추가 칸이 맨 끝으로 물러나지 않는다."""
    from types import SimpleNamespace

    from app.services import custom_columns as cu

    cases = {
        "consulting": {"미팅일": "컨설팅 미팅일", "대표자": "대표자명",
                       "계약완료여부": "계약여부", "딜 소개문구": "소개 메모",
                       "계약서 수신완료여부": "계약서 수신 여부"},
        "startup": {"성함": "대표자명", "사업분야 대분류": "대분류",
                    "기업구분": "투자라운드", "IR Deck 유무": "IR 자료",
                    # #87(10/29)
                    "IR 자료 유무": "IR 자료",
                    "메모 ( 통화내용 /  카톡내용  /  카톡답신내용)": "메모"},
        "forecast": {"투자사명": "회사", "대표자 성함": "대표자명",
                     "희망 투자유치금액": "투자유치희망금액",
                     # #87(10/29)
                     "포스트밸류": "Post Value", "대표이사 지분율": "대표자 지분율"},
        "companies": {"담당팀원": "담당자", "딜소개 문구": "딜 소개 문구",
                      "수신 일자": "수신일"},
        "sourcing": {"이메일 주소": "이메일", "전자 메일 주소": "이메일"},
    }
    for target, names in cases.items():
        anchors = {label for _tab, labels in cu.anchor_groups(target).items()
                   for label in labels}
        for old, new in names.items():
            col = SimpleNamespace(after_key=old, target=target)
            assert cu.anchor_of(col) == new, (target, old)
            assert new in anchors, (target, new)
