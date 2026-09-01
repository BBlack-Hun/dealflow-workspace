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
SEP = date(2026, 9, 1)          # 운영에서 두 명단만 칸이 안 선 날
JAN = date(2026, 1, 5)          # 해가 바뀌는 자리
SHEET = "스타트업"
LIST = "샘플 스타트업(9)"

# --- 운영에서 실측한 칸 구성 (2026-09-01) -----------------------------------
#
# 이름은 가상값이지만 **순서와 달의 배열은 운영 그대로**다. 이 둘만 9월 칸이
# 안 섰다. 둘 다 맨 앞이 달 없는 칸이고, 그 뒤 월별 칸의 **방향이 서로 반대**다
# — 위치로는 어느 칸이 최근인지 정할 수 없다는 것이 여기서 드러난다.

# 월별 칸이 **오름차순**(7월 → 8월)으로 선 명단. 가장 최근인 8월이 뒤에 있다.
ASC_SHEET = [
    "투자유치 진행 여부",                    # 달이 없다 — 여기서 멈춰 있었다
    "7월 문자", "7월 TEL",
    "8월 문자", "8월 TEL",                  # 가장 최근 달이 **뒤쪽**에 있다
    "카톡 연결", "담당자 메모", "비고",
]

# 월별 칸이 **내림차순**(7월 → 4월)인데, 탭 둘을 합치면서 뒤쪽에 8월이 또 붙은
# 명단. 가장 최근인 8월이 4월보다도 뒤에 있다.
DESC_SHEET = [
    "1차 딜소개",                           # 달이 없다 — 여기서 멈춰 있었다
    "7월 IR 자료 요청 기업", "7월 미팅 안내전화 TEL",
    "6월 1차 딜소개", "6월 TEL",
    "5월 1차 딜소개", "5월 TEL",
    "4월 1차 딜소개", "4월 TEL",
    "8월 1차 딜소개", "8월 TEL", "8월 문자",  # 합쳐진 탭 — 가장 최근이 여기 있다
    "담당자 메모", "비고", "업종", "홈페이지", "투자단계", "비고2",
]


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
    """그 표의 최근 달 칸들만 본뜬다 — 잘 도는 명단은 맨 앞이 그 달이다."""
    from app.services.monthly_columns import plan

    got = plan(["7월 문자", "7월 TEL", "6월 문자", "6월 TEL"], 8)
    assert got == ["8월 문자", "8월 TEL"]


def test_맨_앞이_달_없는_칸이어도_뒤에서_본을_찾는다():
    """운영 실측 — 이 두 명단만 9월 칸이 안 섰다(2026-09-01).

    맨 앞에 `투자유치 진행 여부` · `1차 딜소개` 처럼 **달과 무관한 칸**이 서 있어
    맨 앞 칸의 달만 보고 포기했다. 뒤에 멀쩡한 월별 칸이 있어도 안 봤다.

    달 없는 칸은 그 표의 고정 칸이지 달을 가리키는 표시가 아니다 — 몇 번째에
    있든 본을 고르는 데 끼지 않는다.
    """
    from app.services.monthly_columns import plan

    assert plan(ASC_SHEET, 9) == ["9월 문자", "9월 TEL"]
    assert plan(DESC_SHEET, 9) == ["9월 1차 딜소개", "9월 TEL", "9월 문자"]


def test_칸_순서가_오름차순이어도_가장_최근_달을_고른다():
    """`7월 → 7월 → 8월 → 8월`. "왼쪽 = 가장 최근" 이 이 시트에서는 안 맞는다.

    맨 앞 달(7월)을 본뜨면 그 달에 있던 칸 수만큼만 선다 — 8월에 늘어난
    `카톡 연결` 이 빠지고, 9월 그 기록이 갈 곳이 없다.
    """
    from app.services.monthly_columns import plan

    labels = ["7월 문자", "7월 TEL", "8월 문자", "8월 TEL", "8월 카톡 연결"]
    assert plan(labels, 9) == ["9월 문자", "9월 TEL", "9월 카톡 연결"]


def test_합쳐진_탭의_뒤쪽_달도_가장_최근이면_본이_된다():
    """탭 둘을 합친 명단은 `7월 → 6월 → 5월 → 4월` 뒤에 8월이 또 붙는다."""
    from app.services.monthly_columns import plan

    labels = ["7월 문자", "6월 문자", "5월 문자", "4월 문자", "8월 딜소개"]
    assert plan(labels, 9) == ["9월 딜소개"]


def test_달이_하나도_없는_명단에는_여전히_안_만든다():
    """달과 무관한 표에 달 칸이 생기면 안 된다 — 이 동작은 그대로다."""
    from app.services.monthly_columns import plan

    assert plan([], 9) == []
    assert plan(["투자유치 여부", "카톡 연결", "담당자 메모"], 9) == []


@pytest.mark.parametrize("labels,month,want", [
    # 12월만 있는 표에 1월이 온다 — 12월이 **직전 달**이라 그것을 본뜬다.
    (["12월 송년 정리"], 1, ["1월 송년 정리"]),
    # 해를 넘긴 표. `max(달)` 은 12월을 고르지만 가장 최근은 1월이다.
    (["12월 송년 정리", "1월 신년 인사"], 2, ["2월 신년 인사"]),
    (["1월 신년 인사", "12월 송년 정리"], 2, ["2월 신년 인사"]),
    (["12월 송년 정리", "1월 신년 인사", "2월 정리"], 3, ["3월 정리"]),
    # 이미 있으면 그만이다 — 해가 바뀌어 같은 달 숫자가 다시 와도 안 만든다.
    # 이름에 연도가 없어 `1월` 두 칸을 이름으로 가릴 수가 없다.
    (["1월 신년 인사", "12월 송년 정리"], 1, []),
    (["12월 송년 정리", "1월 신년 인사"], 12, []),
])
def test_해가_바뀌면_큰_달이_아니라_가까운_달이_최근이다(labels, month, want):
    """연도가 없으니 **오늘 달에서 거꾸로 세어 가장 가까운 달**이 최근이다.

    `max(달)` 로 정하면 해가 바뀌는 순간 12월에 얼어붙어, 1월·2월·3월이 모두
    지난해 12월을 본뜬다.
    """
    from app.services.monthly_columns import plan

    assert plan(labels, month) == want


def test_잘_돌던_명단의_답은_그대로다():
    """운영에서 이미 잘 서던 셋 — 이번 달 칸이 있으니 아무것도 안 만든다.

    그리고 잘 도는 명단은 맨 앞이 곧 가장 최근 달이라, 다음 달이 와도 답이
    예전과 같다(왼쪽 = 가장 최근이 **맞는** 시트다).
    """
    from app.services.monthly_columns import plan

    healthy = ["9월 딜소개", "9월 문자", "8월 딜소개", "8월 문자", "담당자 메모"]
    assert plan(healthy, 9) == []                          # 이미 있다
    assert plan(healthy, 10) == ["10월 딜소개", "10월 문자"]  # 맨 앞 달 = 최근


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


def test_실측한_두_명단에_9월_칸이_선다(db):
    """2026-09-01 운영 — 이 둘만 9월 칸이 안 섰다. 화면·DB 까지 걸어 본다.

    `plan()` 만 보면 부르는 쪽에서 순서가 뒤집히는 것을 못 잡는다. 새 칸이
    **맨 앞**에 서는지까지 여기서 본다 — 지금 챙겨야 할 달이 먼저 보여야 한다.
    """
    from app.services import monthly_columns as mc

    _contact_cols(db, ASC_SHEET, sheet="샘플 스타트업(40)")
    made = mc.ensure_contact(db, "샘플 스타트업(40)", today=SEP)
    assert made == ["9월 문자", "9월 TEL"]
    assert _contact_labels(db, "샘플 스타트업(40)") == made + ASC_SHEET

    _contact_cols(db, DESC_SHEET, sheet="샘플 딜소개현황")
    made = mc.ensure_contact(db, "샘플 딜소개현황", today=SEP)
    assert made == ["9월 1차 딜소개", "9월 TEL", "9월 문자"]
    assert _contact_labels(db, "샘플 딜소개현황") == made + DESC_SHEET


def test_달_없는_명단에는_9월_칸이_안_선다(db):
    """달과 무관한 표(담당자별 스타트업 명단이 그렇다)는 그대로 둔다.

    맨 앞 칸을 건너뛰고 뒤를 보게 고쳤다고 해서, 여기까지 만들기 시작하면
    달을 쓰지 않는 표에 달 칸이 생긴다.
    """
    from app.services import monthly_columns as mc

    plain = ["투자유치 여부", "카톡 연결", "담당자 메모", "비고", "업종", "홈페이지"]
    _contact_cols(db, plain, sheet="샘플 스타트업(달 없음)")
    assert mc.ensure_contact(db, "샘플 스타트업(달 없음)", today=SEP) == []
    assert _contact_labels(db, "샘플 스타트업(달 없음)") == plain


def test_이미_9월이_선_명단은_건드리지_않는다(db):
    """운영에서 잘 돌던 셋이 이 모양이다 — 답이 바뀌면 안 된다."""
    from app.services import monthly_columns as mc

    healthy = ["9월 딜소개", "9월 문자", "8월 딜소개", "8월 문자", "담당자 메모"]
    _contact_cols(db, healthy, sheet="샘플 딜소개현황(정상)")
    assert mc.ensure_contact(db, "샘플 딜소개현황(정상)", today=SEP) == []
    assert _contact_labels(db, "샘플 딜소개현황(정상)") == healthy


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
