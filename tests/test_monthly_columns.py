"""달마다 늘어나는 칸이 **월 초에 저절로** 서는가.

두 표가 같은 모양을 쓴다 — 투자컨설턴트(`ConsultingColumn`)와 투자사 관리
현황(`ContactColumn`). 여기서 막는 것은 다섯이다.

  1. 이름을 **직전 달 칸에서** 본떠 짓는가. 코드가 형식을 정하면 시트와 글자가
     달라져 나란히 놓고 대조할 수가 없다. 대신 그 달에 보낸 날짜는 떼고 옮기는가
     — 따라가면 앱이 **일어나지 않은 날짜를 지어낸다.**
  2. **두 번 만들지 않는가.** 같은 달 칸이 둘이면 그 달 기록이 갈린다.
     화면 두 개를 동시에 열어도 하나여야 한다.
  3. 사람이 **일부러 지운 칸을 되살리지 않는가.** 지운 사람 눈에는 지워지지
     않는 칸이 된다.
  4. 본이 없으면(칸이 하나도 없으면) 만들지 않는가.
  5. 새 달이 서면 **지난달은 접히는가** — 그리고 접힌 것을 펼 수 있는가.

시각은 `app/clock.py` 로만 읽으므로, 검사는 날짜를 인자로 넣어 못 박는다.
그러지 않으면 이 검사가 **도는 달에 따라** 결과가 달라진다.
"""
from __future__ import annotations

from datetime import date

import pytest

from .conftest import DEMO_PASSWORD

AUG = date(2026, 8, 3)          # 8월 초 — 새 달이 막 시작한 날
JAN = date(2026, 1, 5)          # 해가 바뀌는 자리
SHEET = "스타트업"
LIST = "샘플 스타트업(9)"


# --- 이름 짓기 --------------------------------------------------------------

@pytest.mark.parametrize("label,month,want", [
    ("7월 마지막주 리마인드 톡 or TEL", 8, "8월 마지막주 리마인드 톡 or TEL"),
    # 시트에 두 칸짜리 공백이 그대로 들어 있다 — **누르지 않는다.**
    ("6월 마지막주 리마인드 카톡  or  TEL", 7, "7월 마지막주 리마인드 카톡  or  TEL"),
    # 괄호 안 날짜는 **그날 보냈다는 기록**이다. 다음 달로 옮겨 적으면 앱이
    # 일어나지 않은 날짜를 지어내는 것이 된다 — 떼고 옮긴다.
    ("7월 리마인드 문자 (7/28)", 8, "8월 리마인드 문자"),
    ("7월 리마인드 TEL", 8, "8월 리마인드 TEL"),
    ("12월 카톡 연결", 1, "1월 카톡 연결"),
    # 달이 두 번 적힌 이름은 둘 다 바꾼다 — 한쪽만 바꾸면 이름 안에서 갈린다.
    ("7월 리마인드 · 7월 정리", 8, "8월 리마인드 · 8월 정리"),
    # 괄호를 안 친 날짜도 **그 칸의 달과 같은 숫자면** 보낸 날 기록이다.
    # 그대로 옮기면 9월 칸에 8월 날짜가 붙는다 — 실제로 9/1 에 그렇게 났다.
    ("8월 딜소개 8/5 8/12 8/19", 9, "9월 딜소개"),
    ("12월 딜소개 12/2 12/9", 1, "1월 딜소개"),
    ("8월 딜소개 8/5 완료", 9, "9월 딜소개 완료"),
    # 달이 다르면 날짜가 아니다(비율·분수). 떼면 시트에 있던 글자를 지운다.
    ("8월 성공보수 1/2 조건", 9, "9월 성공보수 1/2 조건"),
    # 연도가 붙은 토막은 `M/D` 가 아니다 — 통째로 남긴다.
    ("8월 정리 2026/8/19", 9, "9월 정리 2026/8/19"),
    # 달이 맞아도 글자에 붙어 있으면 날짜가 아니다. 떼면 `4월분기` 가 된다.
    ("3월 3/4분기 정리", 4, "4월 3/4분기 정리"),
    # 괄호 안 날짜는 **달과 무관하게** 뗀다 — 괄호까지 쳤으면 날짜가 맞다.
    ("8월 리마인드 문자 (7/28)", 9, "9월 리마인드 문자"),
    # 날짜를 떼도 **안쪽 두 칸 공백은 그대로**다 — 고르면 시트와 글자가 달라진다.
    ("8월 리마인드 카톡  or  TEL 8/5", 9, "9월 리마인드 카톡  or  TEL"),
])
def test_직전_칸에서_달만_바꾼다(label, month, want):
    from app.services.monthly_columns import relabel

    assert relabel(label, month) == want


@pytest.mark.parametrize("label,want", [
    ("8월 마지막주 리마인드", 8), ("12 월 정리", 12), ("리마인드 톡", None),
    ("0월 리마인드", None), ("13월 리마인드", None),
])
def test_이름에서_달을_읽는다(label, want):
    from app.services.monthly_columns import month_of

    assert month_of(label) == want


def test_같은_달_칸이_여럿이면_다_같이_만든다():
    """`문자` · `TEL` · `카톡 연결` 중 하나만 만들면 나머지 두 기록이 갈 곳이 없다."""
    from app.services.monthly_columns import plan

    got = plan(["7월 리마인드 문자 (7/28)", "7월 리마인드 TEL", "7월 카톡 연결"], 8)
    assert got == ["8월 리마인드 문자", "8월 리마인드 TEL", "8월 카톡 연결"]


def test_이미_있으면_아무것도_안_만든다():
    from app.services.monthly_columns import plan

    assert plan(["8월 리마인드", "7월 리마인드"], 8) == []


def test_본이_없으면_안_만든다():
    """칸이 하나도 없으면 그 표를 어떻게 부르는지 알 수 없다."""
    from app.services.monthly_columns import plan

    assert plan([], 8) == []
    assert plan(["담당자 메모"], 8) == []      # 가장 최근 칸에 달이 없다


def test_가장_최근_달만_본뜬다():
    """맨 앞(왼쪽)이 그 표의 최근 달이다 — 그 달의 칸들만 본뜬다."""
    from app.services.monthly_columns import plan

    got = plan(["7월 문자", "7월 TEL", "6월 문자", "6월 TEL"], 8)
    assert got == ["8월 문자", "8월 TEL"]


# --- 투자컨설턴트 -----------------------------------------------------------

def _col(db, user_id, label, position=0, sheet=SHEET):
    from app.models import ConsultingColumn

    row = ConsultingColumn(user_id=user_id, sheet=sheet, label=label,
                           position=position)
    db.add(row)
    db.commit()
    return row


def _labels(db, sheet=SHEET, user_id=1):
    """그 사람의 그 탭 열만. 열은 **사람마다·탭마다**라 둘 다 걸러야 한다."""
    from sqlalchemy import select

    from app.models import ConsultingColumn

    stmt = select(ConsultingColumn).where(ConsultingColumn.sheet == sheet)
    stmt = (stmt.where(ConsultingColumn.user_id == user_id) if user_id
            else stmt.where(ConsultingColumn.user_id.is_(None)))
    return [c.label for c in db.execute(
        stmt.order_by(ConsultingColumn.position, ConsultingColumn.id)).scalars()]


def test_컨설턴트_표에_이번_달_열이_선다(db, users):
    from app.services import monthly_columns as mc

    _col(db, users["u1"].id, "7월 마지막주 리마인드 톡 or TEL")
    made = mc.ensure_consulting(db, users["u1"].id, SHEET, today=AUG)
    assert made == ["8월 마지막주 리마인드 톡 or TEL"]
    # 새 열은 **맨 앞**이다 — 지금 챙겨야 할 달이 먼저 보여야 한다.
    assert _labels(db) == ["8월 마지막주 리마인드 톡 or TEL",
                           "7월 마지막주 리마인드 톡 or TEL"]


def test_두_번_불러도_열은_하나다(db, users):
    from app.services import monthly_columns as mc

    _col(db, users["u1"].id, "7월 리마인드")
    mc.ensure_consulting(db, users["u1"].id, SHEET, today=AUG)
    assert mc.ensure_consulting(db, users["u1"].id, SHEET, today=AUG) == []
    assert _labels(db) == ["8월 리마인드", "7월 리마인드"]


def test_사람이_지운_열은_되살리지_않는다(db, users):
    """지운 칸이 다음 요청에서 되살아나면, 지운 사람 눈에는 지워지지 않는 칸이다."""
    from sqlalchemy import select

    from app.models import ConsultingColumn
    from app.services import monthly_columns as mc

    _col(db, users["u1"].id, "7월 리마인드")
    mc.ensure_consulting(db, users["u1"].id, SHEET, today=AUG)

    made = db.execute(select(ConsultingColumn)
                      .where(ConsultingColumn.label == "8월 리마인드")).scalar_one()
    db.delete(made)
    db.commit()

    assert mc.ensure_consulting(db, users["u1"].id, SHEET, today=AUG) == []
    assert _labels(db) == ["7월 리마인드"]


def test_사람마다_탭마다_따로_선다(db, users):
    """열은 사람마다·탭마다다 — 한 사람 것을 세웠다고 남의 표에 서면 안 된다."""
    from app.services import monthly_columns as mc

    _col(db, users["u1"].id, "7월 리마인드")
    _col(db, users["u2"].id, "7월 리마인드")
    _col(db, users["u1"].id, "7월 리마인드", sheet="경영본부 전달 기업")

    mc.ensure_consulting(db, users["u1"].id, SHEET, today=AUG)
    assert _labels(db) == ["8월 리마인드", "7월 리마인드"]      # u1 · 스타트업만
    assert _labels(db, "경영본부 전달 기업") == ["7월 리마인드"]

    mc.ensure_consulting(db, users["u1"].id, "경영본부 전달 기업", today=AUG)
    assert _labels(db, "경영본부 전달 기업") == ["8월 리마인드", "7월 리마인드"]


def test_주인_없는_표에는_안_만든다(db, users):
    """배정 전이라 누구의 표가 될지 모른다 — 미리 만들면 배정한 사람이 지워야 한다."""
    from app.services import monthly_columns as mc

    _col(db, None, "7월 리마인드")
    assert mc.ensure_consulting(db, None, SHEET, today=AUG) == []
    assert _labels(db, user_id=0) == ["7월 리마인드"]


def test_해가_바뀌어도_같은_달_숫자를_또_만들지_않는다(db, users):
    """칸 이름에 연도가 없다 — 만들면 `1월` 두 칸이 서고 이름으로 못 가린다."""
    from app.services import monthly_columns as mc

    _col(db, users["u1"].id, "1월 리마인드")
    assert mc.ensure_consulting(db, users["u1"].id, SHEET, today=JAN) == []


def test_화면을_열면_저절로_선다(client, db, users):
    """예약 실행 장치가 없다 — 달이 바뀐 것을 알아채는 자리는 요청뿐이다."""
    users["u1"].can_view_consulting = 1
    db.commit()
    _col(db, users["u1"].id, "7월 마지막주 리마인드 톡 or TEL")

    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    body = client.get("/consulting").text

    from app import clock

    month = clock.today().month
    assert f"{month}월 마지막주 리마인드 톡 or TEL" in body
    # 두 번 열어도 하나다
    client.get("/consulting")
    assert len([x for x in _labels(db) if x.startswith(f"{month}월")]) == 1


def test_동시에_들어온_요청_중_하나만_만든다(db, users):
    """세어 보고 넣으면 **같은 순간에 센 두 요청이 둘 다 통과한다.**

    화면 두 개를 동시에 열면 실제로 그렇게 된다. 유일 색인이 판정해야 한다.
    """
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import ConsultingColumn, MonthlyColumnRun
    from app.services import monthly_columns as mc

    _col(db, users["u1"].id, "7월 리마인드")
    key = f"{users['u1'].id}:{SHEET}"

    s1, s2 = SessionLocal(), SessionLocal()
    try:
        # 두 요청이 **같은 순간에** 목록을 읽었다 — 둘 다 "8월이 없네" 를 본다.
        def seen(session):
            return session.execute(
                select(ConsultingColumn)
                .where(ConsultingColumn.user_id == users["u1"].id,
                       ConsultingColumn.sheet == SHEET)
                .order_by(ConsultingColumn.position)).scalars().all()

        cols1, cols2 = seen(s1), seen(s2)
        made1 = mc._ensure(s1, mc.CONSULTING, key, cols1, today=AUG)
        s1.commit()
        made2 = mc._ensure(s2, mc.CONSULTING, key, cols2, today=AUG)
        s2.commit()
    finally:
        s1.close()
        s2.close()

    assert made1 == ["8월 리마인드"]
    assert made2 == [], "같은 달 칸이 두 번 만들어졌습니다 — 그 달 기록이 갈립니다"
    db.expire_all()
    assert db.query(MonthlyColumnRun).count() == 1


# --- 투자사 관리 현황 -------------------------------------------------------

def _contact_labels(db, sheet=LIST):
    from sqlalchemy import select

    from app.models import ContactColumn

    return [c.label for c in db.execute(
        select(ContactColumn).where(ContactColumn.sheet == sheet)
        .order_by(ContactColumn.position, ContactColumn.id)).scalars()]


def _contact_cols(db, labels, sheet=LIST):
    from app.models import ContactColumn

    for pos, label in enumerate(labels):
        db.add(ContactColumn(sheet=sheet, label=label, position=pos))
    db.commit()


def test_명단의_이번_달_칸_세_개가_다_선다(db):
    from app.services import monthly_columns as mc

    _contact_cols(db, ["7월 리마인드 문자 (7/28)", "7월 리마인드 TEL", "7월 카톡 연결"])
    made = mc.ensure_contact(db, LIST, today=AUG)
    assert made == ["8월 리마인드 문자", "8월 리마인드 TEL", "8월 카톡 연결"]
    assert _contact_labels(db)[:3] == made       # 새 칸이 맨 앞
    assert mc.ensure_contact(db, LIST, today=AUG) == []


def test_명단_칸을_읽는_것만으로도_선다(db):
    """칸을 읽는 곳이 여럿이라(화면 · [칸 추가] · 수정창) **칸이 나오는 문
    하나**에 둔다. 자리마다 적으면 한 곳은 반드시 빠진다."""
    from app.services import contact_columns as cc

    _contact_cols(db, ["7월 리마인드 문자"])
    got = [c.label for c in cc.month_columns(db, LIST)]
    from app import clock

    assert got[0] == f"{clock.today().month}월 리마인드 문자"


def test_명단에서_지운_칸도_안_되살아난다(db):
    from sqlalchemy import select

    from app.models import ContactColumn
    from app.services import monthly_columns as mc

    _contact_cols(db, ["7월 리마인드 문자"])
    mc.ensure_contact(db, LIST, today=AUG)
    made = db.execute(select(ContactColumn)
                      .where(ContactColumn.label == "8월 리마인드 문자")).scalar_one()
    db.delete(made)
    db.commit()
    assert mc.ensure_contact(db, LIST, today=AUG) == []
    assert _contact_labels(db) == ["7월 리마인드 문자"]


def test_보낸_날은_안_따라간다(db):
    """9/1 자동생성이 `9월 딜소개 8/5 8/12 8/19` 를 만들어 운영에 섰다.

    본이 된 8월 칸에 괄호 없이 날짜가 적혀 있었다. 그대로 옮기면 앱이
    **일어나지 않은 날짜를 지어낸다** — 9월 칸이 8월에 보냈다고 말한다.
    """
    from app.services import monthly_columns as mc

    _contact_cols(db, ["8월 딜소개 8/5 8/12 8/19"], sheet="딜소개 명단")
    made = mc.ensure_contact(db, "딜소개 명단", today=date(2026, 9, 1))
    assert made == ["9월 딜소개"]


def test_명단이_다르면_따로_선다(db):
    from app.services import monthly_columns as mc

    _contact_cols(db, ["7월 리마인드 문자"])
    _contact_cols(db, ["7월 리마인드 문자"], sheet="샘플 스타트업(40)")
    mc.ensure_contact(db, LIST, today=AUG)
    assert _contact_labels(db, "샘플 스타트업(40)") == ["7월 리마인드 문자"]


# --- 접기 ------------------------------------------------------------------

def test_명단은_이번_달만_펴_둔다(db):
    """한 달에 세 칸씩 붙는 표라 두 달치면 여섯 칸이고, 그만큼 가로로 밀린다."""
    from app.models import ContactColumn
    from app.services import contact_columns as cc

    cols = [ContactColumn(sheet=LIST, label=f"{m}월 {what}", position=i)
            for i, (m, what) in enumerate(
                [(8, "문자"), (8, "TEL"), (8, "카톡"), (7, "문자"), (7, "TEL")])]
    shown, folded = cc.split_months(cols)
    assert [c.label for c in shown] == ["8월 문자", "8월 TEL", "8월 카톡"]
    assert [c.label for c in folded] == ["7월 문자", "7월 TEL"]
    assert cc.VISIBLE_MONTHS == 1


def test_한_달의_칸은_다_같이_서거나_다_같이_접힌다(db):
    """칸 수로 자르면 달 중간이 잘려 **한 달의 기록 일부만** 보이는 표가 된다."""
    from app.models import ContactColumn
    from app.services import contact_columns as cc

    # 이번 달에 다섯 칸이 붙은 명단. 칸 수로 잘랐다면 여기서 잘렸다.
    cols = [ContactColumn(sheet=LIST, label=f"8월 칸{i}", position=i)
            for i in range(5)] + [ContactColumn(sheet=LIST, label="7월 칸",
                                                position=5)]
    shown, folded = cc.split_months(cols)
    assert len(shown) == 5 and [c.label for c in folded] == ["7월 칸"]


def test_사람이_펴_둔_것을_다시_접지_않는다(db):
    """편 상태는 **요청에 실려 있고 DB 에 없다** — 달이 바뀌어 칸이 저절로
    생겨도 접는 쪽이 손댈 수 있는 자리가 없다."""
    from app.models import ContactColumn
    from app.services import contact_columns as cc

    cols = [ContactColumn(sheet=LIST, label=f"{m}월 문자", position=i)
            for i, m in enumerate([8, 7, 6])]
    shown, folded = cc.split_months(cols, show_all=True)
    assert len(shown) == 3 and folded == []


def test_컨설턴트_표도_달_단위로_접는다(db, users):
    """한 달에 한 칸이라 결과는 같지만, 두 칸이 서는 순간 달 중간이 잘린다."""
    from app.models import ConsultingColumn
    from app.routers.consulting import VISIBLE_MONTHS, _split_columns

    cols = [ConsultingColumn(label=f"{m}월 리마인드", position=i)
            for i, m in enumerate(range(12, 0, -1))]
    shown, hidden = _split_columns(cols)
    assert len(shown) == VISIBLE_MONTHS and len(hidden) == 12 - VISIBLE_MONTHS

    # 한 달에 두 칸이 서면 **두 칸이 같이** 남는다
    two = [ConsultingColumn(label=f"{m}월 {what}", position=i)
           for i, (m, what) in enumerate(
               [(8, "톡"), (8, "TEL"), (7, "톡"), (6, "톡"), (5, "톡")])]
    shown, hidden = _split_columns(two)
    assert [c.label for c in shown] == ["8월 톡", "8월 TEL", "7월 톡", "6월 톡"]
    assert [c.label for c in hidden] == ["5월 톡"]


def test_달을_못_읽는_열은_혼자_한_묶음이다(db):
    """옆 달에 붙이면 그 열 때문에 남의 달이 통째로 접히거나 펴진다."""
    from app.models import ConsultingColumn
    from app.routers.consulting import _split_columns

    cols = [ConsultingColumn(label=x, position=i) for i, x in enumerate(
        ["담당자 메모", "8월 톡", "7월 톡", "6월 톡"])]
    shown, hidden = _split_columns(cols)
    assert [c.label for c in shown] == ["담당자 메모", "8월 톡", "7월 톡"]
    assert [c.label for c in hidden] == ["6월 톡"]
