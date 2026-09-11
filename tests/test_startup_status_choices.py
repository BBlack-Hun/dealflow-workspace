"""스타트업 화면의 **골라 넣는 여섯 칸** — 값·옛 값·새 달·필터·두 가지 고치는 길.

자유롭게 적던 칸이라 한 칸에 `무료계약완료` · `견적 전달함` · `대표님이
초대해주심` 이 섞여 들어갔고, 세거나 거를 수가 없었다. 여섯 칸을 골라 넣는
칸으로 바꾸면서 **조용히 깨질 수 있는 다섯 가지**를 여기서 잠근다.

  1. 보기가 제안서와 글자·차례까지 같은가
  2. **목록에 없는 옛 값이 화면에서 사라지지 않는가** — 이번 판에서 제일 중요하다.
     자료를 옮기는 일은 하지 않기로 했으므로, 옛 글은 그대로 보여야 한다.
  3. **다음 달에 저절로 생기는 칸에도 보기가 붙는가** — 달마다 손으로 붙이는
     구조면 다음 달 칸에는 아무도 안 붙인다. 그 달만 조용히 자유 입력으로
     돌아가고 필터도 같이 빠진다.
  4. 고를 수 있는 칸이 되었으니 **머리글 필터가 따라 붙는가**(#171 의 기준)
  5. 표에서 눌러 고치는 길과 수정창, **두 길이 같은 보기를 말하는가**

이름·회사·번호는 전부 지어낸 값이다 — 저장소가 공개다.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

from .conftest import DEMO_PASSWORD

ROOT = Path(__file__).resolve().parent.parent

LIST = "샘플 스타트업(9)"
OTHER = "샘플 투자사 20"

# ── 제안서에 적힌 값. **여기에 다시 적는 것이 이 검사의 전부다** ─────────────
#
# 앱이 읽는 목록(`contact_columns`)과 따로 적어 두어야 검사가 된다. 앱의 값을
# 그대로 가져와 비교하면 앱이 바뀔 때 검사도 같이 바뀌어 아무것도 못 막는다.
#
# 차례도 그대로다 — 일이 진행되는 순서라(준비 → 진행 → 보류 → 완료) 가나다순
# 으로 다시 세우면 목록에서 지금 자리를 짚을 수가 없다.
PROPOSED = {
    "funding_status": (
        "투자유치 상태",
        ["미확인", "투자유치 준비 중", "투자유치 진행 중",
         "투자유치 일시 보류", "투자유치 완료", "현재 투자유치 계획 없음"]),
    "collab_status": (
        "당사 협업 상태",
        ["확인 전", "협업 논의 중", "당사 통한 진행 희망", "자체 진행 예정",
         "타사 통한 진행 중", "당사 협업 보류", "당사 협업 의사 없음", "협업 종료"]),
    "reply_status": (
        "회신 상태",
        ["회신 대기", "회신 받음", "재연락 요청", "진행 거절", "회신 불필요"]),
}
# 월별 칸 셋. 열쇠는 달마다 바뀌므로(`c12`) **칸 이름의 뒷말**로 짚는다.
PROPOSED_MONTHLY = {
    "리마인드 문자": ["미발송", "발송 예정", "발송 완료", "발송 실패", "발송 제외"],
    "리마인드 TEL": ["미시도", "통화 예정", "통화 완료", "부재중",
                     "통화 중 / 재시도 필요", "재통화 요청", "연락처 오류", "통화 거절"],
    "카톡 연결": ["미연결", "초대 요청", "초대 완료 / 입장 대기", "연결 완료",
                  "기존 연결방 이용", "연결 보류", "연결 거절", "연결 종료"],
}


def _month(offset: int = 0) -> int:
    from app import clock

    return (clock.today().month - 1 + offset) % 12 + 1


def _url(sheet: str = LIST) -> str:
    from urllib.parse import quote

    from app.services import contact_columns as cc

    return f"/{cc.page_of(cc.STARTUP)}?sheet={quote(sheet)}"


def _split(choices: str) -> list:
    return [v.strip() for v in choices.split(",") if v.strip()]


def _cells(html: str, key: str) -> list:
    """표에서 그 칸의 값들. **그려진 화면**을 본다."""
    return re.findall(
        r'data-field="' + re.escape(key) + r'"[^>]*>(.*?)</div>', html, re.S)


def _th(html: str, label: str) -> str:
    """그 이름을 가진 머리글의 속성. 없으면 빈 글자."""
    for attrs, cell in re.findall(r"<th\b([^>]*)>(.*?)</th>", html, re.S):
        flat = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", cell)).strip()
        if flat == label:
            return attrs
    return ""


# ── 밑자리 ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def sheets(client, db, users):
    """스타트업 명단 하나 + 투자사 명단 하나.

    **옛 값을 일부러 심는다.** 지금 이 칸들에는 사람이 자유롭게 적은 글이 들어
    있고(`무료계약완료` · `대표님이 초대해주심`), 고르는 칸으로 바꿨다고 그것이
    화면에서 사라지면 안 된다.
    """
    from app.models import ContactColumn, SheetOwner, VcContact
    from app.services import contact_columns as cc

    u1 = users["u1"]
    db.add_all([
        SheetOwner(label=LIST, user_id=u1.id, layout=cc.STARTUP, is_hidden=0),
        SheetOwner(label=OTHER, user_id=u1.id, layout=cc.INVESTOR, is_hidden=0),
    ])
    labels = [f"{_month()}월 리마인드 문자", f"{_month()}월 리마인드 TEL",
              f"{_month()}월 카톡 연결"]
    for pos, label in enumerate(labels):
        db.add(ContactColumn(sheet=LIST, label=label, position=pos))
    db.flush()
    cols = {c.label: c for c in cc.month_columns(db, LIST)}

    # 1번 줄에 **목록에 없는 옛 글**을 넣는다. 원본 시트에 실제로 그런 식으로
    # 적혀 있었다 — 한 칸에 결과와 할 일과 사람이 섞여 들어간다.
    db.add(VcContact(
        user_id=u1.id, source_sheet=LIST, name="김샘플1", firm="샘플기업1",
        phone="01000000101", email="sample1@example.com",
        notes=cc.dump_notes({
            cc.note_key(cols[labels[0]].id): "7/30 문자 및 명함 발송",
            cc.note_key(cols[labels[1]].id): "통화함 - 진행 의사 있음",
            cc.note_key(cols[labels[2]].id): "대표님이 초대해주심",
            "funding_status": "당분간 자체 진행 예정",
        })))
    # 2번 줄은 새 보기 그대로.
    db.add(VcContact(
        user_id=u1.id, source_sheet=LIST, name="김샘플2", firm="샘플기업2",
        phone="01000000102", email="sample2@example.com",
        notes=cc.dump_notes({
            cc.note_key(cols[labels[0]].id): "발송 완료",
            "funding_status": "투자유치 진행 중", "collab_status": "협업 논의 중",
            "reply_status": "회신 받음",
        })))
    # 투자사 명단 — 이쪽이 흔들리면 안 된다.
    db.add(VcContact(user_id=u1.id, source_sheet=OTHER, name="박투자1",
                     firm="샘플벤처스1", phone="01000000201"))
    db.commit()
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    return client


# ── 1. 보기가 제안서 그대로다 ───────────────────────────────────────────────

def test_달에_매이지_않는_세_칸의_보기가_제안서_그대로다():
    """값도 **차례도** 그대로다. 차례가 곧 일이 진행되는 순서다."""
    from app.services import contact_columns as cc

    by_key = {c.key: c for c in cc.STARTUP_LAYOUT.head}
    for key, (label, want) in PROPOSED.items():
        assert key in by_key, f"`{label}` 칸이 배치에 없습니다"
        column = by_key[key]
        assert column.label == label, f"{key} 머리글이 다릅니다: {column.label}"
        assert column.kind == "pick", f"`{label}` 이 고르는 칸이 아닙니다"
        assert _split(column.choices) == want, (
            f"`{label}` 의 보기가 제안서와 다릅니다:\n"
            f"  제안서 {want}\n  배치   {_split(column.choices)}")


def test_월별_세_칸의_보기가_제안서_그대로다():
    """칸 이름의 **뒷말**로 보기가 정해진다 — 달이 바뀌어도 뒷말은 그대로다."""
    from app.services import contact_columns as cc

    for tail, want in PROPOSED_MONTHLY.items():
        for month in (1, _month(), 12):
            label = f"{month}월 {tail}"
            got = _split(cc.month_choices(cc.STARTUP_LAYOUT, label))
            assert got == want, (
                f"`{label}` 의 보기가 제안서와 다릅니다:\n"
                f"  제안서 {want}\n  배치   {got}")


def test_통화_결과와_회신_상태는_서로의_값을_갖지_않는다():
    """**`통화 완료` 와 `진행 의사 있음` 을 같게 취급하지 마라.**

    전화가 닿았다는 것과 하겠다는 답을 들었다는 것은 다른 말이다. 한 목록으로
    합치면 "통화는 됐는데 거절" 을 적을 자리가 없어진다.
    """
    from app.services import contact_columns as cc

    call = set(_split(cc.CALL_CHOICES))
    reply = set(_split(cc.REPLY_CHOICES))
    assert not (call & reply), f"두 칸이 같은 값을 갖고 있습니다: {call & reply}"
    assert "통화 완료" in call and "통화 완료" not in reply
    assert "회신 받음" in reply and "회신 받음" not in call


def test_자체_진행_예정은_투자유치가_아니라_협업_상태에_있다():
    """`당분간 자체 진행 예정` 은 ① 이 아니라 ② 로 간다.

    그 기업이 투자유치를 하느냐가 아니라 **우리를 통해** 하느냐를 적는 말이다.
    ① 에 두면 "투자유치는 하는데 우리와는 안 한다" 를 적을 자리가 없어진다.
    """
    from app.services import contact_columns as cc

    assert "자체 진행 예정" in _split(cc.COLLAB_CHOICES)
    assert "자체 진행 예정" not in _split(cc.FUNDING_CHOICES)


def test_문자_칸에는_연결이_없다():
    """기존 문자 칸의 `연결` 은 ③ 이 아니라 ④ 로 간다.

    보냈다는 기록이 아니라 **보낸 뒤에 돌아온 반응**이기 때문이다.
    """
    from app.services import contact_columns as cc

    send = _split(cc.SEND_CHOICES)
    assert all(v.startswith("발송") or v == "미발송" for v in send), send


# ── 2. 목록에 없는 옛 값이 화면에서 사라지지 않는다 ─────────────────────────

def test_목록에_없는_옛_값도_표에_그대로_보인다(sheets, db):
    """**이번 판에서 제일 중요한 검사다.**

    자료를 옮기는 일(마이그레이션)은 하지 않기로 했다. 고르는 칸으로 바꿨다고
    옛 글이 안 보이면, 사람은 지워진 줄 알고 다시 적는다 — 그때는 이미 원래
    무엇이 적혀 있었는지 화면 어디에서도 알 수 없다.
    """
    from app.services import contact_columns as cc

    html = sheets.get(_url()).text
    months = cc.month_columns(db, LIST)
    keys = {cc.month_choices(cc.STARTUP_LAYOUT, m.label): cc.note_key(m.id)
            for m in months}
    old = {
        keys[cc.SEND_CHOICES]: "7/30 문자 및 명함 발송",
        keys[cc.CALL_CHOICES]: "통화함 - 진행 의사 있음",
        keys[cc.KAKAO_CHOICES]: "대표님이 초대해주심",
        "funding_status": "당분간 자체 진행 예정",
    }
    for key, value in old.items():
        assert value in _cells(html, key), (
            f"옛 값이 표에서 사라졌습니다: {value}\n"
            f"  그 칸에 보이는 것 {_cells(html, key)}")


def test_옛_값이_수정창에서도_저장되고_되읽힌다(sheets, db):
    """목록에 없는 말도 **그대로 쳐서 저장된다.**

    `<select>` 로 묶었으면 창을 여는 것만으로 그 값이 사라진다. 고르는 칸은
    적을 수 있는 값을 좁히는 장치가 아니라 **고를 거리를 주는** 장치다.
    """
    from app.models import VcContact

    row = db.query(VcContact).filter(VcContact.source_sheet == LIST).first()
    free = "목록에 없는 말 — 그대로 남아야 한다"
    res = sheets.patch(f"/api/contacts/{row.id}",
                       json={"notes": {"collab_status": free}})
    assert res.status_code == 200, res.text
    got = sheets.get(f"/api/contacts/{row.id}").json()["contact"]["notes"]
    assert got["collab_status"] == free


# ── 3. 새로 생기는 월별 칸에도 보기가 붙는다 ────────────────────────────────

def test_다음_달에_저절로_생기는_칸에도_보기가_붙는다(sheets, db):
    """달마다 손으로 붙이는 구조면 **다음 달 칸에는 아무도 안 붙인다.**

    새 칸은 직전 달 칸에서 달 숫자만 바뀌어 나오므로(`monthly_columns.relabel`)
    뒷말은 그대로다 — 그 뒷말을 보고 보기가 따라 붙는지 본다. 여기서 막지
    않으면 다음 달 한 달만 조용히 자유 입력으로 돌아가고, 필터도 같이 빠진다.
    """
    from datetime import date

    from app import clock
    from app.services import contact_columns as cc
    from app.services import monthly_columns

    today = clock.today()
    # 다음 달 1일로 달력을 넘긴다. 12월이면 해가 바뀐다 — 그 자리도 같이 본다.
    nxt = date(today.year + (today.month == 12), _month(1), 1)
    made = monthly_columns.ensure_contact(db, LIST, today=nxt,
                                          seed=cc.STARTUP_LAYOUT.month_seed)
    assert made, "다음 달 칸이 만들어지지 않았습니다"

    months = cc.month_columns(db, LIST, today=nxt)
    fresh = [m for m in months if m.label in made]
    assert len(fresh) == 3, [m.label for m in fresh]
    for column in fresh:
        got = _split(cc.as_column(column, cc.STARTUP_LAYOUT).choices)
        tail = column.label.split("월", 1)[1].strip()
        assert got == PROPOSED_MONTHLY[tail], (
            f"새로 생긴 `{column.label}` 에 보기가 안 붙었습니다: {got}")


def test_밑자리로_심는_칸과_보기를_고르는_말이_갈리지_않는다():
    """달 칸이 하나도 없는 **새 명단**에 처음 서는 칸에도 보기가 붙어야 한다.

    밑자리(`month_seed`)와 보기를 고르는 말(`month_picks`)을 따로 적어 두면,
    한쪽만 고쳐지는 날 새 명단의 그 칸만 조용히 자유 입력이 된다.
    """
    from app.services import contact_columns as cc

    layout = cc.STARTUP_LAYOUT
    for tail in layout.month_seed:
        label = f"{_month()}월 {tail}"
        assert cc.month_choices(layout, label) != layout.month_choices, (
            f"밑자리로 심는 `{label}` 에 보기가 안 붙습니다")
        assert _split(cc.month_choices(layout, label)) == PROPOSED_MONTHLY[tail]


def test_팀이_정한_세_모양이_아닌_칸에는_남의_보기를_안_붙인다():
    """시트에서 딸려 온 다른 칸에 카톡방 보기를 붙이면 **옛 글을 잘못 짚는다.**

    한 명단에 `리마인드 카톡(월1회-…)` 이 서 있는데 그것은 보내는 칸이지
    카톡방 연결 상태가 아니다.
    """
    from app.services import contact_columns as cc

    layout = cc.STARTUP_LAYOUT
    for label in ("리마인드 카톡(월1회-수or목or금)", "카톡방 연결여부", "샘플 옛 칸"):
        assert cc.month_choices(layout, label) == layout.month_choices, (
            f"`{label}` 에 남의 보기가 붙었습니다")


# ── 4. 고를 수 있는 칸이 되었으니 필터도 붙는다 (#171) ──────────────────────

def test_여섯_칸_전부에_머리글_필터가_붙는다(sheets, db):
    """#171 이 "고를 수 있는 칸에는 필터가 붙는다" 로 기준을 바꿔 놓았다.

    선언(머리글 `data-filters`)과 행이 싣는 값(`data-f-*`)이 **둘 다** 있어야
    한다 — 선언만 있으면 필터를 열어도 늘 빈 목록이고, 싣기만 하면 아무도 안
    보는 죽은 속성이다.
    """
    from app.services import contact_columns as cc

    html = sheets.get(_url()).text
    months = cc.month_columns(db, LIST)
    want = {key: label for key, (label, _v) in PROPOSED.items()}
    want.update({cc.note_key(m.id): m.label for m in months})

    filterable = {c.key for c in cc.filter_columns(cc.STARTUP_LAYOUT, months)}
    for key, label in want.items():
        assert key in filterable, f"`{label}` 에 필터가 안 붙습니다"
        attrs = _th(html, label)
        assert f'data-filters="{key}:' in attrs, (
            f"`{label}` 머리글에 필터 선언이 없습니다: {attrs}")
        assert f"data-f-{key}=" in html, f"행이 `{label}` 값을 안 싣습니다"


def test_필터_단추가_머리글_한_줄에_들어간다(sheets):
    """값을 고르면 이름 뒤에 `(1) ▾` 가 붙어 24px 이 더 든다.

    안 재고 이름 길이로만 폭을 잡으면 화면에서는 멀쩡하다가 **필터를 거는
    순간** 머리글이 두 줄로 접힌다. 이 표의 머리글은 반복문으로 세워서
    `tests/test_ui_layout.py` 의 정적 검사가 건너뛴다 — 같은 자로 잰다.
    """
    from .test_ui_layout import _text_px

    html = sheets.get(_url()).text
    problems = []
    for key, (label, _v) in PROPOSED.items():
        attrs = _th(html, label)
        px = re.search(r"width:\s*(\d+)px", attrs)
        assert px, f"`{label}` 머리글에 폭이 없습니다"
        need = round(_text_px(label + " (1) ▾") + 18 + 14)
        if need > int(px.group(1)):
            problems.append(f"{label} ({px.group(1)}px → {need}px 필요)")
    assert not problems, "머리글이 두 줄로 접힙니다:\n  " + "\n  ".join(problems)


# ── 5. 표에서 눌러 고치기 · 수정창 — 두 길이 같은 보기를 말한다 ─────────────

def test_표에서_눌러_고치는_칸에_보기가_실린다(sheets, db):
    """`data-type="pick"` + `data-choices` — 이미 있던 기전 그대로다."""
    from app.services import contact_columns as cc

    html = sheets.get(_url()).text
    months = cc.month_columns(db, LIST)
    want = {key: choices for key, (_l, choices) in
            ((k, (lab, ",".join(v))) for k, (lab, v) in PROPOSED.items())}
    want.update({cc.note_key(m.id): cc.month_choices(cc.STARTUP_LAYOUT, m.label)
                 for m in months})

    for key, choices in want.items():
        cell = re.search(
            r'data-field="' + re.escape(key) + r'"[^>]*data-type="pick"'
            r'[^>]*data-choices="([^"]*)"', html)
        assert cell, f"`{key}` 칸을 눌러 고를 수가 없습니다"
        assert _split(cell.group(1)) == _split(choices), (
            f"`{key}` 의 보기가 표와 배치에서 갈립니다:\n"
            f"  표   {_split(cell.group(1))}\n  배치 {_split(choices)}")


def test_수정창에서도_같은_보기를_고른다(sheets, db):
    """창만 빈 글자 칸이면 같은 칸이 `발송 완료` 와 `발송완료` 로 갈린다.

    `list=`(`<datalist>`)는 `<input>` 을 묶지 않는다 — 목록에 없는 옛 말도
    그대로 쳐서 저장된다. 묶는 `<select>` 를 쓰면 창을 여는 것만으로 옛 값이
    사라진다(#172 가 딜 기업 DB 에서 한 판단과 같다).
    """
    from app.services import contact_columns as cc

    html = sheets.get(_url()).text
    months = cc.month_columns(db, LIST)
    for column in cc.panel_columns(cc.STARTUP_LAYOUT, months):
        if not column.choices:
            continue
        assert f'list="opts-panel-{column.key}"' in html, (
            f"수정창의 `{column.label}` 칸에서 고를 수가 없습니다")
        block = re.search(
            r'<datalist id="opts-panel-' + re.escape(column.key) + r'">(.*?)</datalist>',
            html, re.S)
        assert block, f"`{column.label}` 의 보기 목록이 없습니다"
        got = re.findall(r'value="([^"]*)"', block.group(1))
        assert got == _split(column.choices), (
            f"`{column.label}` 의 보기가 표와 창에서 갈립니다:\n"
            f"  창   {got}\n  배치 {_split(column.choices)}")


def test_여섯_칸이_저장되고_되읽힌다(sheets, db):
    """스키마 · 저장 · 되읽기 — 한 곳만 빠져도 증상이 조용하다.

    PATCH 는 200 을 주는데 아무것도 안 들어가거나, 저장은 되는데 다시 열면
    빈칸이다.
    """
    from app.models import VcContact
    from app.services import contact_columns as cc

    row = db.query(VcContact).filter(VcContact.source_sheet == LIST).first()
    months = cc.month_columns(db, LIST)
    sent = {key: values[0] for key, (_l, values) in PROPOSED.items()}
    sent.update({cc.note_key(m.id):
                 _split(cc.month_choices(cc.STARTUP_LAYOUT, m.label))[0]
                 for m in months})

    res = sheets.patch(f"/api/contacts/{row.id}", json={"notes": sent})
    assert res.status_code == 200, res.text
    got = sheets.get(f"/api/contacts/{row.id}").json()["contact"]["notes"]
    for key, value in sent.items():
        assert got.get(key) == value, f"`{key}` 가 되읽기에서 빠졌습니다"


@pytest.mark.skipif(shutil.which("node") is None,
                    reason="node 미설치 — 브라우저 로직 테스트 생략")
def test_표에서_눌러_고치는_길이_실제로_도는가():
    """보기가 **정말 뜨는지**·옛 값이 **정말 같이 뜨는지**는 브라우저 코드를
    돌려야 보인다.

    파이썬으로는 `data-choices` 속성이 붙어 있는지까지만 볼 수 있다. 칸을
    눌렀을 때 목록이 실제로 채워지는지, 다른 줄에 남아 있는 자유 표기가 고를
    거리에 함께 서는지(`inline_edit.js` 의 `knownValues`), 목록에 없는 말을
    쳐도 그대로 저장되는지는 `inline_edit.js` 를 돌려 봐야 한다.
    로컬에서는 `node tests/js/startup_status_pick_test.js` 로도 돈다.
    """
    script = ROOT / "tests" / "js" / "startup_status_pick_test.js"
    out = subprocess.run([shutil.which("node"), str(script)],
                         capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stdout + out.stderr


# ── 6. 다른 화면이 안 깨진다 ────────────────────────────────────────────────

def test_투자사_관리_현황은_한_칸도_안_바뀐다(sheets):
    """같은 화면 코드(`contacts.html`)를 쓰는 표다. 매일 보는 화면이라
    스타트업 칸을 붙이다가 이쪽이 흔들리면 안 된다."""
    from urllib.parse import quote

    from app.services import contact_columns as cc

    html = sheets.get(f"/{cc.page_of(cc.INVESTOR)}?sheet={quote(OTHER)}").text
    assert "명함 등록일" in html and "관심도 (월말기준)" in html
    for key, (label, _v) in PROPOSED.items():
        assert label not in html, f"투자사 표에 `{label}` 이 끼어들었습니다"


def test_투자사_배치의_월별_칸은_지금까지_그대로_글_칸이다():
    """딜공유 명단의 월별 칸은 한 칸에 회차별 기업 목록이 쌓인다.

    고르는 칸으로 바꾸면 **고치는 순간 그 달 기록이 한 글자로 덮인다.**
    이 판에서 월별 칸의 보기를 이름으로 고르게 하면서, 저 배치가 딸려 오지
    않는지 본다 — 붙일 것을 안 적어 두었으니 붙을 리 없지만, 붙는 날의
    증상이 조용하다(고친 사람만 자기 기록이 사라진 것을 나중에 안다).
    """
    from app.services import contact_columns as cc

    for layout in (cc.INVESTOR_LAYOUT, cc.INVESTOR_MONTHLY_LAYOUT):
        assert layout.month_kind == "long"
        assert layout.month_picks == ()
        for tail in ("리마인드 문자", "리마인드 TEL", "카톡 연결", "딜소개"):
            assert cc.month_choices(layout, f"{_month()}월 {tail}") == ""
