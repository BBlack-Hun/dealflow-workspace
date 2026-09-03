"""빈 `사업분야` 에 넣을 갈래를 **제안만** 하는 기능.

이 파일이 지키는 것은 두 가지다.

  1. **저절로 쓰이지 않는다.** 한줄 소개를 고쳐도 `sector_major` 는 그대로다.
  2. **이미 고른 값은 되묻지 않는다.** 값이 있으면 제안이 아예 안 뜬다.

두 줄이 무너지면 사람이 정한 값이 소리 없이 바뀌는데, 바뀐 줄도 모른다 —
`사업분야` 는 딜 추천(`services/matcher.py`)과 발송 화면 필터가 읽는 칸이라
틀린 값 하나가 엉뚱한 투자사에게 나가는 딜이 된다.

기업명은 전부 가상값이다(이 저장소는 공개다).
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from app.models import IrCompany
from app.services import sector_hint
from app.services.sector_hint import Hints


def _c(**kw):
    return IrCompany(name=kw.pop("name", "샘플기업"), **kw)


def _taught(pairs):
    """`(한줄소개, 갈래)` 짝으로 배운 잣대."""
    return Hints.learn([_c(one_liner=text, sector_major=sector)
                        for text, sector in pairs])


# 갈래마다 MIN_EXAMPLES 이상 있어야 후보가 된다. 세 곳씩 둔다.
TEACH = [
    ("반도체 웨이퍼 검사 장비 제조", "딥테크·제조"),
    ("정밀 금형 부품 제조 공정 자동화", "딥테크·제조"),
    ("산업용 로봇 제조 및 부품 공급", "딥테크·제조"),
    ("스마트팜 양액 재배 솔루션", "ESG·푸드·애그테크"),
    ("친환경 대체육 식품 제조 브랜드", "ESG·푸드·애그테크"),
    ("농산물 산지 직거래 유통 플랫폼", "ESG·푸드·애그테크"),
]


# --- 1. 저절로 쓰지 않는다 -------------------------------------------------

def test_한줄소개만_고치면_사업분야는_그대로다(logged_in, db):
    """PATCH 로 한줄 소개를 바꿔도 `sector_major` 는 건드려지지 않는다.

    이것이 이 기능의 전부다. 제안이 아무리 잘 맞아도 **쓰는 것은 사람**이다.
    """
    # **후보가 실제로 뜨는 상태를 만들어 둔다.** 가르친 것이 없으면 제안도
    # 없어서, 저절로 쓰는 코드가 들어와도 이 검사가 조용히 통과한다.
    for text, sector in TEACH:
        db.add(_c(one_liner=text, sector_major=sector))
    company = _c(name="가상제조", one_liner="", sector_major=None)
    db.add(company)
    db.commit()
    cid = company.id

    r = logged_in.patch(f"/api/companies/{cid}",
                        json={"one_liner": "반도체 웨이퍼 검사 장비 제조 자동화"})
    assert r.status_code == 200, r.text

    db.expire_all()
    after = db.get(IrCompany, cid)
    assert after.one_liner == "반도체 웨이퍼 검사 장비 제조 자동화"
    assert after.sector_major is None, (
        "한줄 소개를 고쳤을 뿐인데 사업분야가 저절로 채워졌다 — "
        "제안은 사람이 눌러야만 들어가야 한다")

    # 그 소개로 후보는 분명히 뜬다 — 위 단언이 '후보가 없어서' 통과한 것이 아니다.
    assert logged_in.get(f"/api/companies/{cid}").json()["sector_suggestions"], (
        "후보가 뜨지 않는 상태라 위 검사가 아무것도 지키지 못했다")


def test_제안이_있어도_저장되는_값은_사람이_보낸_것뿐이다(logged_in, db):
    """제안이 뜨는 상태에서 다른 칸을 고쳐도 사업분야는 안 들어간다."""
    for text, sector in TEACH:
        db.add(_c(one_liner=text, sector_major=sector))
    target = _c(name="가상농장", one_liner="스마트팜 양액 재배 자동화 솔루션")
    db.add(target)
    db.commit()
    cid = target.id

    row = logged_in.get(f"/api/companies/{cid}").json()
    assert row["sector_suggestions"], "제안이 떠 있어야 이 검사가 뜻이 있다"

    logged_in.patch(f"/api/companies/{cid}", json={"note": "메모만 고친다"})
    db.expire_all()
    assert db.get(IrCompany, cid).sector_major is None, (
        "다른 칸을 고쳤는데 제안이 사업분야에 적혔다")


def test_서비스에는_값을_쓰는_길이_아예_없다():
    """`sector_hint` 는 글자 목록만 돌려준다 — 무엇도 고치지 않는다."""
    hints = _taught(TEACH)
    company = _c(one_liner="스마트팜 양액 재배 솔루션")
    got = hints.suggest_for(company)

    assert isinstance(got, list) and all(isinstance(x, str) for x in got)
    assert company.sector_major is None, "제안을 뽑는 것만으로 값이 들어갔다"


# --- 2. 이미 고른 값은 되묻지 않는다 ---------------------------------------

def test_사업분야가_이미_있으면_제안하지_않는다():
    hints = _taught(TEACH)
    company = _c(one_liner="스마트팜 양액 재배 솔루션",
                 sector_major="딥테크·제조")   # 글과 다른 값을 일부러 골라 뒀다
    assert hints.suggest_for(company) == [], (
        "사람이 골라 둔 값 옆에 다른 후보를 띄우면 잘못 눌러 덮게 된다")


def test_공백만_있는_사업분야는_비어_있는_것으로_본다():
    hints = _taught(TEACH)
    assert hints.suggest_for(_c(one_liner="스마트팜 양액 재배 솔루션",
                                sector_major="   ")) != []


def test_행에_실리는_제안도_값이_있으면_빈다(logged_in, db):
    """화면이 읽는 `sector_suggestions` 에도 같은 규칙이 걸려 있다."""
    for text, sector in TEACH:
        db.add(_c(one_liner=text, sector_major=sector))
    filled = _c(name="가상채움", one_liner="스마트팜 양액 재배 솔루션",
                sector_major="딥테크·제조")
    empty = _c(name="가상빈칸", one_liner="스마트팜 양액 재배 솔루션")
    db.add_all([filled, empty])
    db.commit()

    rows = {r["name"]: r for r in logged_in.get("/api/companies").json()["rows"]}
    assert rows["가상채움"]["sector_suggestions"] == []
    assert rows["가상빈칸"]["sector_suggestions"], "빈 칸에는 후보가 떠야 한다"


# --- 3. 갈래를 지어내지 않는다 ---------------------------------------------

def test_제안은_데이터에_있는_갈래에서만_나온다():
    hints = _taught(TEACH)
    used = {sector for _text, sector in TEACH}
    got = hints.suggest_for(_c(one_liner="농산물 산지 직거래 스마트팜 유통 플랫폼"))
    assert got, "견줄 글이 있으면 후보가 나와야 한다"
    assert set(got) <= used, (
        f"쓰이지 않는 갈래를 지어냈다: {set(got) - used} — "
        "지어낸 갈래는 어느 필터에도 안 걸린다")


def test_갈래_목록은_데이터를_따라_바뀐다():
    """코드에 목록이 박혀 있지 않다는 것 — 새 갈래를 가르치면 그것도 후보다."""
    plain = _taught(TEACH)
    assert "핀테크·블록체인" not in plain.sectors

    extra = TEACH + [("간편 결제 정산 솔루션", "핀테크·블록체인"),
                     ("법인 카드 지출관리 서비스", "핀테크·블록체인"),
                     ("블록체인 기반 송금 인프라", "핀테크·블록체인")]
    assert "핀테크·블록체인" in _taught(extra).sectors


def test_한_곳에만_쓰인_갈래는_후보가_되지_않는다():
    """실데이터의 `물류`(1곳) 같은 적다 만 값. 후보에 두면 오염이 늘어난다."""
    pairs = TEACH + [("새벽 배송 라우팅 최적화", "물류")]
    hints = _taught(pairs)
    assert "물류" not in hints.sectors
    assert "물류" not in hints.suggest(
        "새벽 배송 라우팅 최적화 물류 최적화 배송 플랫폼")


# --- 4. 맞아 보이는 것이 없으면 아무것도 제안하지 않는다 -------------------

def test_자료가_없다는_메모에는_제안하지_않는다():
    """실데이터의 빈 19곳 중 13곳이 이런 글이다 — 소개가 아니라 빈 칸이다."""
    hints = _taught(TEACH)
    for memo in ("회사정보 검색안됨", "메일함에 참고할 자료 없음",
                 "메일함에 없음, 자료 필요", "내용없음", "자료없음"):
        assert hints.suggest_for(_c(one_liner=memo)) == [], (
            f"{memo!r} 로 갈래를 골라 줬다 — 없는 근거로 만든 값이 칸에 들어간다")


def test_한줄소개가_비면_제안하지_않는다():
    hints = _taught(TEACH)
    assert hints.suggest_for(_c(one_liner=None)) == []
    assert hints.suggest_for(_c(one_liner="   ")) == []


def test_아는_낱말이_없으면_제안하지_않는다():
    """교재에 없는 말뿐이면 갈래 크기 순서만 남는다 — 읽지도 않고 권하는 꼴이다."""
    hints = _taught(TEACH)
    assert hints.suggest_for(_c(one_liner="zzz")) == []


def test_배운_것이_없으면_아무것도_제안하지_않는다():
    assert Hints.learn([]).suggest_for(_c(one_liner="스마트팜 양액 재배")) == []


# --- 5. 제안 자체 ----------------------------------------------------------

def test_맞는_갈래가_후보_안에_들어온다():
    hints = _taught(TEACH)
    got = hints.suggest_for(_c(one_liner="친환경 대체육 스마트팜 식품 제조 유통"))
    assert "ESG·푸드·애그테크" in got


def test_후보는_세_개를_넘지_않는다():
    """넷을 넘기면 고르는 것이 아니라 훑는 것이 된다."""
    pairs = TEACH + [("간편 결제 정산 솔루션", "핀테크·블록체인"),
                     ("법인 카드 지출관리 서비스", "핀테크·블록체인"),
                     ("블록체인 송금 인프라 구축", "핀테크·블록체인"),
                     ("원격 진료 예약 플랫폼", "헬스케어·바이오"),
                     ("의료영상 판독 보조 솔루션", "헬스케어·바이오"),
                     ("임상시험 데이터 관리 서비스", "헬스케어·바이오")]
    hints = _taught(pairs)
    assert len(hints.sectors) == 4
    assert len(hints.suggest("스마트팜 결제 진료 제조 플랫폼 솔루션 유통")) <= 3


def test_금액_토막은_견주는_글에서_빠진다():
    """한줄 소개는 `설명 | 매출 13억 | …` 로 조립된다. 뒤는 갈래와 무관하다."""
    company = _c(one_liner="스마트팜 양액 재배 솔루션 | 매출 13억 | 누적투자금액 11억")
    assert sector_hint.source_text(company) == "스마트팜 양액 재배 솔루션"


def test_한줄소개가_비어도_사업분야_설명으로_견준다():
    """스타트업DB 탭의 `사업분야`(business_desc)만 차 있는 곳이 실제로 있다."""
    hints = _taught(TEACH)
    got = hints.suggest_for(_c(one_liner=None,
                               business_desc="친환경 대체육 식품 제조 유통 브랜드"))
    assert "ESG·푸드·애그테크" in got


# --- 6. 화면이 실제로 그 값을 보이는가 -------------------------------------

def test_표에_후보와_빈칸_거르는_단추가_있다(logged_in, db):
    for text, sector in TEACH:
        db.add(_c(one_liner=text, sector_major=sector))
    db.add(_c(name="가상빈칸", one_liner="스마트팜 양액 재배 솔루션"))
    db.commit()

    html = logged_in.get("/companies").text
    assert 'data-suggest="' in html, "후보가 화면으로 안 나갔다"
    assert "data-preset=\"sector=" in html, (
        "사업분야가 빈 곳만 거르는 단추가 없다 — 빈 칸을 찾을 길이 없으면 "
        "제안이 있어도 영영 안 채워진다")
    assert "추천 " in html, "빈 칸에 후보가 있다는 표시가 없다"


def test_빈_곳의_수를_센다(logged_in, db):
    db.add_all([_c(name="가상하나", sector_major="딥테크·제조"),
                _c(name="가상둘"), _c(name="가상셋", sector_major="   ")])
    db.commit()
    html = logged_in.get("/companies").text
    assert "사업분야 없음 2" in html


def test_사업분야가_다_차_있으면_단추를_세우지_않는다(logged_in, db):
    db.add(_c(name="가상하나", sector_major="딥테크·제조"))
    db.commit()
    assert "data-preset=\"sector=" not in logged_in.get("/companies").text


def test_스타트업DB_탭에는_단추를_세우지_않는다(logged_in, db):
    """그 탭에는 사업분야 필터가 없어 눌러도 필터가 풀리기만 한다."""
    db.add(_c(name="가상빈칸"))
    db.commit()
    assert "data-preset=\"sector=" not in logged_in.get("/companies?tab=db").text


# --- 7. 화면 쪽 규칙은 node 로 돌린다 --------------------------------------
#
# 후보를 목록 맨 앞에 세우는 일은 브라우저에서 일어난다. 파이썬으로 다시
# 구현하면 두 벌이 되어 어긋나도 알아채지 못한다 — 같은 언어로 둔다.
# node 가 없는 환경(운영 도커 이미지)에서는 건너뛴다.

JS_TEST = Path(__file__).resolve().parent / "js" / "sector_suggest_test.js"


@pytest.mark.skipif(shutil.which("node") is None,
                    reason="node 미설치 — 브라우저 로직 테스트 생략")
def test_후보를_보기_맨_앞에_세우는_규칙_js():
    result = subprocess.run(
        [shutil.which("node"), str(JS_TEST)],
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
