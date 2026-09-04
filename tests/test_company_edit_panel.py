"""[수정] 창이 스타트업DB 칸들을 실제로 고칠 수 있는가.

## 왜 이 검사가 있나

`IR 기업 현황` 과 `스타트업DB` 는 **같은 기업 레코드의 두 가지 보기**다.
그런데 열한 칸은 **스타트업DB 표에서 눌러 고치는 것이 유일한 입구**였다 —
[수정] 창에 아예 없었다.

    수신일 · 대표자 · 연락처 · 이메일
    22·23·24·25년 매출 · 설립년도 · 기보, 신보, 중진공
    사업 설명(business_desc)

그 상태로 스타트업DB 탭을 지우면 **고칠 자리가 통째로 사라진다.** 특히
`사업 설명` 과 `23·24·25년 매출` 은 한줄 소개 자동 조합의 재료라
(`app/services/one_liner.py`), 입구 없이 탭을 지우면 자동 조합이 그 자리에서
굳는다 — 재료를 못 고치니 결과도 못 바꾼다.

## 무엇을 못 박나

1. 표에 있는 칸은 **창에도 있다.** 새 칸이 늘 때 창에 넣는 것을 잊으면 잡힌다.
2. 창의 이름은 **표 머리글과 한 글자도 다르지 않다.**
   (짝을 대조하는 것은 tests/test_ui_layout.py 가 전 화면에 걸쳐 한다.)
3. 열한 칸이 **실제로 저장되고 되읽힌다** — 창은 표와 달리 [저장] 한 번에
   모든 칸을 보내므로, 창이 못 읽는 칸이 하나라도 있으면 다른 칸을 고치려고
   누른 [저장]이 그 칸을 지운다.
4. 창에서 고친 연도별 매출·사업 설명이 **한줄 소개 자동 조합의 재료**로 쓰인다.
5. 창에서 고친 값이 **표에도 보인다**(두 입구가 같은 칸을 본다).

값은 전부 가상값이다 — 저장소가 공개다.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "app" / "templates" / "companies.html"
SCRIPT = ROOT / "app" / "static" / "js" / "companies.js"

# 스타트업DB 표에만 있던 칸들. **이 목록이 이 판의 전부**다 —
# `사업 설명`(business_desc)은 표에도 없어서(0051 이 화면에서 뗐다) 아래
# `test_사업_설명은_표에_없어도_창에는_있어야_한다` 가 따로 지킨다.
STARTUP_DB_FIELDS = [
    ("received_at", "수신일"),
    ("contact_name", "대표자"),
    ("contact_phone", "연락처"),
    ("contact_email", "이메일"),
    ("revenue_2022", "22년 매출"),
    ("revenue_2023", "23년 매출"),
    ("revenue_2024", "24년 매출"),
    ("revenue_2025", "25년 매출"),
    ("founded_year", "설립년도"),
    ("guarantee", "기보, 신보, 중진공"),
]

# 실데이터에 실제로 있는 모양들. **숫자 칸·날짜 칸으로 바꿔 둔 순간 브라우저가
# 못 읽어 빈 값이 되는** 값들을 일부러 고른다.
#   · `1,224백만원` · `150억 ~ 200억`  → 숫자 칸이면 통째로 사라진다
#   · `날짜 미정`                      → 날짜 칸이면 통째로 사라진다(운영 14곳)
#   · `2015년`                         → 숫자 칸이면 `2015` 로 깎이거나 사라진다
SAMPLE = {
    "received_at": "날짜 미정",
    "contact_name": "김가나",
    "contact_phone": "010-0000-5678",
    "contact_email": "sample@example.com",
    "revenue_2022": "8.2억",
    "revenue_2023": "1,224백만원",
    "revenue_2024": "150억 ~ 200억",
    "revenue_2025": "4월 기준 3억",
    "founded_year": "2015년",
    "guarantee": "기보 3억, 신보 2억",
}


@pytest.fixture()
def company(db):
    from app.models import IrCompany

    row = IrCompany(name="샘플가나헬스")
    db.add(row)
    db.commit()
    return row


def _panel_fields() -> list:
    """창이 저장 요청에 싣는 칸 — `companies.js` 의 `FIELDS`."""
    listed = re.search(r"var FIELDS = \[(.*?)\];", SCRIPT.read_text(encoding="utf-8"), re.S)
    assert listed, "companies.js 에서 FIELDS 를 못 찾았습니다"
    return re.findall(r'"([a-z_0-9]+)"', listed.group(1))


def _panel_save(client, company_id: int, **over):
    """창이 [저장] 때 보내는 몸통 그대로 PATCH.

    **창을 한 번 열었다 저장하는 흐름 그대로**여야 한다 — 되읽기로 칸을 채우고
    (`fill`) 그 칸들을 통째로 보낸다(`collect`). 칸 하나만 실어 보내는 검사는
    "다른 칸을 고쳤더니 이 칸이 지워졌다" 를 못 잡는다.
    """
    row = client.get(f"/api/companies/{company_id}").json()
    eok = {"revenue_recent", "funding_total", "raise_target", "pre_value"}
    body = {}
    for field in _panel_fields():
        value = row.get(field)
        body[field] = value if field in eok else ("" if value is None else str(value))
    body["is_top_deal"] = bool(row.get("is_top_deal"))
    body.update(over)
    return client.patch(f"/api/companies/{company_id}", json=body)


# --- ① 표에 있는 칸은 창에도 있다 --------------------------------------------

def _db_tab_fields(text: str) -> set:
    """스타트업DB 표가 눌러 고치게 열어 둔 칸 — `data-field="…"`.

    두 표는 `{% if co_tab == 'db' %}` … `{% else %}` 로 갈라져 있다. 앞쪽
    덩어리만 본다 — **없어질 탭은 이쪽**이라, 여기 있는 칸이 창에도 있어야
    탭을 지워도 고칠 자리가 남는다.
    """
    head = text.split("{% if co_tab == 'db' %}", 1)[1]
    return set(re.findall(r'data-field="([a-z_0-9]+)"', head.split("{% else %}", 1)[0]))


# IR 기업 현황 표에서만 고치는 칸. **왜 창에 없는지 여기 적어 둔다** — 이유 없이
# 목록만 늘면 아래 검사가 아무것도 안 지키게 된다.
#
# 이 둘은 없어질 탭(스타트업DB)이 아니라 **남는 탭**의 칸이라 급하지 않다.
IR_TAB_ONLY = {
    "assignee_name": "담당자 — 남는 탭의 칸이고, 표에서 목록으로 골라 고친다",
    "top_deal_kind": "핵심/TOP Deal — 창에는 `추천 딜 (★)` 체크박스가 그 자리다",
}


def test_없어질_탭에서_눌러_고치는_칸은_모두_창에도_있다():
    """칸이 하나 늘 때 창에 넣는 것을 잊으면 여기서 잡힌다.

    잊으면 그 칸은 **스타트업DB 표에서 눌러 고치는 것이 유일한 입구**가 된다.
    지금은 표가 있으니 티가 안 나지만, 그 탭을 지우는 날 고칠 자리가 통째로
    사라진다 — 이 판이 막으려는 것이 바로 그것이다.
    """
    text = TEMPLATE.read_text(encoding="utf-8")
    in_panel = set(re.findall(r'id="f-([a-z_0-9]+)"', text))
    missing = sorted(_db_tab_fields(text) - in_panel)
    assert not missing, (
        "스타트업DB 표에서는 눌러 고칠 수 있는데 [수정] 창에는 없는 칸입니다 — "
        f"그 탭을 지우면 고칠 자리가 사라집니다: {missing}")


def test_IR_탭에만_있는_칸은_이유가_적혀_있다():
    """예외가 조용히 늘면 위 검사가 아무것도 안 지키게 된다."""
    text = TEMPLATE.read_text(encoding="utf-8")
    in_panel = set(re.findall(r'id="f-([a-z_0-9]+)"', text))
    all_table = set(re.findall(r'data-field="([a-z_0-9]+)"', text))
    unexplained = sorted(all_table - in_panel - set(IR_TAB_ONLY))
    assert not unexplained, (
        "표에는 있는데 창에 없고, 왜 없는지도 안 적힌 칸입니다 — 창에 넣든지 "
        f"`IR_TAB_ONLY` 에 이유를 적으세요: {unexplained}")
    # 반대로, 창에 넣고 나서 예외 목록을 안 지우면 목록이 거짓말이 된다.
    stale = sorted(set(IR_TAB_ONLY) & in_panel)
    assert not stale, f"창에 이미 있는데 예외로 적혀 있습니다: {stale}"


def test_열한_칸이_모두_창에_있고_저장_목록에도_있다():
    """창에만 세우고 `FIELDS` 에 안 넣으면 **조용히 저장이 안 된다.**"""
    text = TEMPLATE.read_text(encoding="utf-8")
    fields = _panel_fields()
    for attr, label in STARTUP_DB_FIELDS + [("business_desc", "사업 설명")]:
        assert f'id="f-{attr}"' in text, f"{label}({attr}) 칸이 창에 없습니다"
        assert attr in fields, \
            f"{label}({attr}) 이 companies.js 의 FIELDS 에 없습니다 — 고쳐도 저장이 안 됩니다"


def test_창의_이름은_표_머리글과_한_글자도_다르지_않다():
    """`기보, 신보, 중진공` 을 창에서 `보증기관` 이라 부르면 같은 칸인 줄 모른다.

    짝을 **자리 순서로** 대조하는 일은 tests/test_ui_layout.py 가 전 화면에
    걸쳐 이미 한다. 여기서는 이번에 넣은 열 칸의 이름을 못 박아, 표 쪽 머리글이
    바뀌었을 때 "둘 다 같이 바꿨으니 통과" 로 조용히 넘어가지 않게 한다.
    """
    text = TEMPLATE.read_text(encoding="utf-8")
    for attr, label in STARTUP_DB_FIELDS:
        assert f"<span>{label}</span>" in text, \
            f"{attr}: 창에서 부르는 이름이 표 머리글 '{label}' 과 다릅니다"
        assert f">{label}</th>" in text, \
            f"{attr}: 표 머리글이 '{label}' 이 아닙니다 — 창 쪽도 함께 보세요"


def test_사업_설명은_표에_없어도_창에는_있어야_한다():
    """표에서 뗀 칸인데 **자동 조합의 첫 재료**다(0051).

    두 탭을 합치면서 화면에서 뗐더니, 조합은 그대로 이 칸을 읽는데 고칠 자리만
    사라진 상태가 됐다. 이름을 `사업분야` 로 두면 옆 탭의 `사업분야 대분류`
    (`sector_major`)와 같은 말이 되어 서로 다른 두 칸을 가리킨다.
    """
    from app.services.one_liner import SOURCE_FIELDS

    text = TEMPLATE.read_text(encoding="utf-8")
    assert 'id="f-business_desc"' in text
    label = re.search(r"<span>([^<]*)</span>\s*\n?\s*<textarea id=\"f-business_desc\"", text)
    assert label, "사업 설명 라벨을 못 찾았습니다"
    name = label.group(1).strip()
    assert name != "사업분야", "옆 탭의 `사업분야 대분류` 와 같은 말입니다"
    assert dict(SOURCE_FIELDS)["business_desc"] == name, (
        "화면 이름과 `one_liner.SOURCE_FIELDS` 의 이름이 갈렸습니다 — "
        "'무엇이 합쳐지는가' 를 두 곳이 다르게 부르면 안 됩니다")


# --- ② 실제로 저장되고 되읽힌다 ----------------------------------------------

def test_열한_칸이_저장되고_되읽힌다(logged_in, company):
    """`1,224백만원` 이 숫자로 바뀌거나 `날짜 미정` 이 사라지면 여기서 걸린다."""
    body = dict(SAMPLE)
    body["business_desc"] = "B2B 농산물 선도거래 플랫폼"
    r = _panel_save(logged_in, company.id, **body)
    assert r.status_code == 200, r.text

    row = logged_in.get(f"/api/companies/{company.id}").json()
    for attr, value in body.items():
        assert row[attr] == value, f"{attr}: {value!r} 로 저장했는데 {row[attr]!r} 로 돌아왔다"


def test_다른_칸을_고쳐도_열한_칸이_지워지지_않는다(logged_in, company):
    """창은 [저장] 한 번에 **모든 칸**을 보낸다.

    창이 못 읽는 칸이 하나라도 있으면(칸이 없거나 이름이 다르면) 그 칸은 빈
    글자로 실려 나가, IR 파일명 하나 고치려고 누른 [저장]이 대표자·연락처·매출을
    통째로 지운다. 표에서 눌러 고치는 쪽은 누른 칸 하나만 보내서 이런 일이
    안 나므로, **창에서만** 나는 사고다.
    """
    body = dict(SAMPLE)
    body["business_desc"] = "B2B 농산물 선도거래 플랫폼"
    _panel_save(logged_in, company.id, **body)

    file_name = "샘플애그_IR_2026.pdf"
    assert _panel_save(logged_in, company.id, ir_file_name=file_name).status_code == 200

    row = logged_in.get(f"/api/companies/{company.id}").json()
    assert row["ir_file_name"] == file_name
    gone = [attr for attr, value in body.items() if row[attr] != value]
    assert not gone, f"다른 칸을 고쳤더니 이 칸들이 지워졌습니다: {gone}"


def test_표와_창이_같은_값을_보여_준다(logged_in, company):
    """두 입구가 같은 칸을 봐야 한다 — 맞춰 주는 코드가 **없어야** 안 어긋난다."""
    _panel_save(logged_in, company.id, contact_name="김가나", revenue_2024="150억 ~ 200억",
                founded_year="2015년", guarantee="기보 3억, 신보 2억")

    html = logged_in.get("/companies?tab=db").text
    for value in ("김가나", "150억 ~ 200억", "2015년", "기보 3억, 신보 2억"):
        assert value in html, f"창에서 고친 {value!r} 가 표에 안 보입니다"

    # 반대 방향 — 표에서 눌러 고친 값이 창(=API 되읽기)에도 보인다.
    logged_in.patch(f"/api/companies/{company.id}", json={"contact_name": "이나다"})
    assert logged_in.get(f"/api/companies/{company.id}").json()["contact_name"] == "이나다"


# --- ③ 한줄 소개 자동 조합의 재료 ---------------------------------------------

def test_창에서_고친_연도별_매출이_자동_조합에_쓰인다(logged_in, company):
    """`매출 …` 토막은 **적힌 해를 다 늘어놓는다**(one_liner)."""
    _panel_save(logged_in, company.id, business_desc="B2B 농산물 선도거래 플랫폼",
                revenue_2023="2억", revenue_2024="4억", one_liner="")
    row = logged_in.get(f"/api/companies/{company.id}").json()
    assert "매출 23년 2억, 24년 4억" in row["one_liner"], row["one_liner"]
    assert row["one_liner"].startswith("B2B 농산물 선도거래 플랫폼"), row["one_liner"]

    # 25년을 채우면 **그 해가 뒤에 붙는다** — 재료를 고치면 결과가 바뀐다.
    _panel_save(logged_in, company.id, revenue_2025="11억")
    row = logged_in.get(f"/api/companies/{company.id}").json()
    assert "매출 23년 2억, 24년 4억, 25년 11억" in row["one_liner"], row["one_liner"]

    # 22년도 재료다 — 사용자 신고("22년이랑 23년 매출도 반영") 그대로.
    _panel_save(logged_in, company.id, revenue_2022="1억")
    row = logged_in.get(f"/api/companies/{company.id}").json()
    assert "매출 22년 1억, 23년 2억, 24년 4억, 25년 11억" in row["one_liner"], row["one_liner"]


def test_창에서_고친_사업_설명이_자동_조합의_첫_토막이_된다(logged_in, company):
    """이 칸을 못 고치면 조합이 늘 매출부터 시작한다."""
    _panel_save(logged_in, company.id, business_desc="뇌영상 분석 AI 솔루션",
                revenue_2024="4억", one_liner="")
    row = logged_in.get(f"/api/companies/{company.id}").json()
    assert row["one_liner"].startswith("뇌영상 분석 AI 솔루션"), row["one_liner"]

    _panel_save(logged_in, company.id, business_desc="가축 사료 B2B 유통")
    row = logged_in.get(f"/api/companies/{company.id}").json()
    assert row["one_liner"].startswith("가축 사료 B2B 유통"), row["one_liner"]


def test_사람이_쓴_소개는_재료를_고쳐도_안_덮인다(logged_in, company):
    """제일 나쁜 고장이다 — 사람이 쓴 문장이 소리 없이 사라진다.

    대신 만들어 둔 값을 `one_liner_suggestion` 으로 함께 돌려주고, 화면은
    그것으로 [자동 조합으로 바꾸기] 를 권한다.
    """
    _panel_save(logged_in, company.id, one_liner="사람이 다듬어 쓴 소개",
                business_desc="뇌영상 분석 AI 솔루션", revenue_2024="4억")
    row = logged_in.get(f"/api/companies/{company.id}").json()
    assert row["one_liner"] == "사람이 다듬어 쓴 소개"
    assert row["one_liner_auto"] is False
    assert "뇌영상 분석 AI 솔루션" in row["one_liner_suggestion"]

    # 화면이 권한 그 값을 넣고 저장하면 — 다음에 열 때 `자동` 으로 읽힌다.
    _panel_save(logged_in, company.id, one_liner=row["one_liner_suggestion"])
    row = logged_in.get(f"/api/companies/{company.id}").json()
    assert row["one_liner_auto"] is True, "되돌렸는데도 손글씨로 읽힙니다"


# --- ④ 브라우저 --------------------------------------------------------------

@pytest.mark.skipif(shutil.which("node") is None,
                    reason="node 미설치 — 브라우저 로직 테스트 생략")
def test_창의_저장은_브라우저에_있으니_거기서_잰다():
    """되읽기(`fill`) → 저장(`collect`) 을 **companies.js 를 그대로 돌려서** 본다.

    파이썬으로는 두 파일에 이름이 있는지까지만 볼 수 있다. 값이 정말 요청
    몸통에 실리는지, 한줄 소개 상태 줄이 세 상태를 제대로 말하는지는 브라우저
    코드를 돌려야 보인다(tests/js/company_edit_fields_test.js).
    로컬에서는 `node tests/js/company_edit_fields_test.js` 로도 돈다.
    """
    script = ROOT / "tests" / "js" / "company_edit_fields_test.js"
    out = subprocess.run([shutil.which("node"), str(script)],
                         capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stdout + out.stderr


# --- ⑤ 번호(NO)로도 창을 연다 -------------------------------------------------
#
# 표는 2,030px 라 오른쪽 끝의 [수정] 단추까지 가로로 밀어야 닿는데, 줄을 짚는
# 손은 이미 왼쪽 번호에 있다. 그래서 번호도 같은 창을 연다.
#
# **여는 길은 하나여야 한다.** 번호 칸에 handler 를 따로 달면 그날은 되지만,
# 다음에 창 여는 규칙이 바뀔 때 한쪽만 고쳐지고 조용히 갈린다. 그래서 번호
# 칸은 [수정] 단추와 같은 class 를 달아 companies.js 의 그 handler 를 탄다.

def test_두_탭의_번호_칸이_수정_창을_연다():
    """번호 칸이 **[수정] 단추와 같은 class** 를 달고 있는가.

    두 탭(IR 기업 현황 · 스타트업DB)에 하나씩 있다 — 같은 창을 쓰는데 한쪽
    탭에서만 열리면 고장으로 읽힌다.
    """
    text = TEMPLATE.read_text(encoding="utf-8")
    rowno = re.findall(r'<td class="(rowno[^"]*)"', text)
    assert len(rowno) == 2, f"번호 칸이 탭마다 하나씩 둘이 아닙니다: {rowno}"
    for cls in rowno:
        assert "js-co-edit" in cls.split(), \
            f"번호 칸에 js-co-edit 이 없습니다 ★ 눌러도 창이 안 열립니다: {cls}"


def test_번호_칸이_눌러도_되는_칸으로_보인다():
    """커서와 hover 색이 없으면 눌러도 되는 칸인지 알 길이 없다.

    번호는 그냥 글자라 단추처럼 생기지 않았다 — 표시가 CSS 뿐이다.
    """
    css = (ROOT / "app" / "static" / "css" / "app.css").read_text(encoding="utf-8")
    assert re.search(r"\.rowno\.js-co-edit[^{]*\{[^}]*cursor:\s*pointer", css), \
        "번호 칸에 손가락 커서가 없습니다"
    assert re.search(r"\.rowno\.js-co-edit:hover[^{]*\{[^}]*color:", css), \
        "번호 칸에 hover 색이 없습니다"


@pytest.mark.skipif(shutil.which("node") is None,
                    reason="node 미설치 — 브라우저 로직 테스트 생략")
def test_번호를_누르면_그_줄의_창이_열린다():
    """누르는 흐름은 브라우저에 있으니 **companies.js 를 그대로 돌려서** 본다.

    파이썬으로는 class 가 붙어 있는지까지만 볼 수 있다. 누른 줄의 기업이
    맞게 열리는지, [수정] 단추와 같은 창을 여는지, 그리고 눌러서 고치는
    칸(`한줄 소개`)까지 창을 열어 버리지는 않는지는 브라우저 코드를 돌려야
    보인다(tests/js/company_no_opens_edit_test.js).
    로컬에서는 `node tests/js/company_no_opens_edit_test.js` 로도 돈다.
    """
    script = ROOT / "tests" / "js" / "company_no_opens_edit_test.js"
    out = subprocess.run([shutil.which("node"), str(script)],
                         capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stdout + out.stderr
