"""선호로 그룹을 다시 매기는 일 — **판정**(`services/pref_group`)과
**넣는 스크립트**(`scripts/set_group_from_pref.py`).

이 검사가 지키는 것이 셋이다.

① **매긴 이름이 다음 업로드에 살아남는가.** `pref_group` 이 내놓은 이름이
   `group_name.KNOWN` 에 없으면 `gn.decide()` 가 그것을 문장으로 보고 메모로
   옮겨 버린다 — 매겨 둔 117줄이 조용히 되돌려진다. 두 목록을 맞춰 보는 검사가
   이 파일에서 제일 중요하다.

② **메모 전체를 읽지 않는가.** 메모에는 지난주에 소개한 기업 이름이 널려
   있어서(`○○바이오` · `○○에너지`) 분야 낱말이 우연히 걸린다. 읽는 것은
   선호 칸 셋과 **`[그룹 칸에서 옮김]` 줄뿐**이어야 한다.

③ **한 명단만·감춘 줄 빼고·되돌릴 수 있게** 건드리는가.

저장소가 공개라 **지어낸 값만** 쓴다.
"""
from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from app.services import group_name as gn
from app.services import pref_group as pg

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "set_group_from_pref.py"

#: 지어낸 명단 이름. 운영 명단 이름을 검사에 적지 않는다.
SHEET = "가상 딜소개현황-가나다"
OTHER_SHEET = "가상 딜소개현황-마바사"


class Fake:
    """`decide()` 가 보는 것만 가진 줄. 모델을 띄우지 않고 판정만 본다."""

    def __init__(self, sectors=None, round_size=None, stages=None, memo=None):
        self.sectors = sectors
        self.round_size = round_size
        self.stages = stages
        self.memo = memo


def moved(text: str) -> str:
    """예전 그룹 칸에서 옮겨 온 줄 한 개. 표시는 서비스의 그것을 쓴다."""
    return f"{gn.MOVED_MARK} {text}"


# ── ① 매긴 이름이 살아남는가 ────────────────────────────────────────────────

def test_매긴_이름은_전부_그룹_칸이_받아들이는_값이다():
    """**이 파일에서 제일 중요한 검사다.**

    하나라도 빠지면 그 그룹은 다음 시트 업로드에서 `gn.decide()` 가 문장으로
    보고 메모로 옮긴다(`MOVE`) — 매겨 둔 줄이 조용히 비워진다. 규칙에 이름을
    더할 때 `group_name.NAMED` 를 같이 안 고치면 여기서 걸린다.
    """
    for name in pg.OUTPUTS:
        assert name in gn.KNOWN, f"`{name}` 이 group_name.KNOWN 에 없습니다"
        assert gn.decide(name).action == gn.KEEP, name
        assert gn.decide(name).group == name, name


def test_이름_없는_분야로는_그룹을_만들지_않는다():
    """아직 이름이 없는 갈래는 `특정분야` 로 모인다.

    갈래 이름을 그대로 그룹으로 쓰면 그룹이 줄 수만큼 늘어난다 — 이 칸이 이미
    한 번 겪은 그것이다(문장 158줄).
    """
    for name, _words in pg.OTHER_SECTORS:
        assert name not in pg.OUTPUTS, name
        assert name not in gn.KNOWN, name


def test_사다리의_모든_칸이_어느_갈래엔가_든다():
    """한 칸이라도 빠지면 그 단계만 적어 둔 줄이 갈 데가 없어 `공통` 으로 샌다."""
    from app.services import invest_stage as st

    covered = {name for _band, members in pg.ROUND_BANDS for name in members}
    assert covered == set(st.LADDER)


# ── ② 무엇을 읽는가 ─────────────────────────────────────────────────────────

def test_메모의_기업_이름이_분야로_읽히지_않는다():
    """**메모 전체를 읽으면 안 된다.**

    실측에서 메모에만 분야가 잡힌 6줄 중 3줄이 이것이었다 — 지난주에 소개한
    기업 이름(`○○바이오` · `○○에너지`)이 분야 낱말에 걸린 것이다. 그렇게
    잡힌 분야는 그 투자사의 선호가 아니다.
    """
    row = Fake(memo="6/16 딜 소개한 가상바이오 Pre-value 문의 -> 답변 완료")
    assert pg.decide(row).group == pg.COMMON
    assert pg.decide(row).why == pg.BY_NONE


def test_그룹_칸에서_옮겨_온_줄은_읽는다():
    """그룹을 다시 매기는 데 **예전 그룹 칸의 글보다 맞는 재료는 없다.**

    실측 117줄 중 43줄에 남아 있고, 모양도 사람이 갈래를 적어 둔 그대로다.
    """
    row = Fake(memo="6/16 가상바이오 소개 완료\n" + moved("초기 | Pre-seed"))
    got = pg.decide(row)
    assert got.group == pg.EARLY
    assert got.why == pg.BY_ROUND


def test_옮겨_온_줄만_읽고_같은_메모의_나머지는_안_읽는다():
    """한 메모 안에서도 갈라 읽는다 — 옮겨 온 줄에 라운드가, 나머지에 기업
    이름이 있으면 **라운드만** 읽혀야 한다."""
    row = Fake(memo="가상에너지 미팅 완료\n" + moved("후기 | Series C ~"))
    got = pg.decide(row)
    assert got.group == pg.LATE
    assert got.why == pg.BY_ROUND        # `에너지` 가 분야로 안 읽혔다


def test_소싱메모와_팁스메모는_안_읽는다():
    """전화·부재중 기록이라 선호가 아니다. 칸 목록에 없다는 것을 못 박는다."""
    assert "sourcing_note" not in pg.PREF_FIELDS
    assert "tips_note" not in pg.PREF_FIELDS
    assert "memo" not in pg.PREF_FIELDS


def test_옮겨_온_줄이_여럿이면_한_칸_띄워_잇는다():
    """붙여 버리면 앞 줄 끝 낱말과 뒷 줄 첫 낱말이 한 낱말이 된다."""
    memo = "\n".join([moved("후기"), "가운데 줄", moved("딥테크")])
    assert pg.moved_text(memo) == "후기 딥테크"


# ── ③ 어떻게 가르는가 ───────────────────────────────────────────────────────

def test_분야가_라운드보다_앞선다():
    """분야가 딜의 성격을 정한다. 둘 다 읽히면 분야로 간다."""
    row = Fake(sectors="딥테크", round_size="Series C 이상")
    got = pg.decide(row)
    assert got.group == "딥테크·제조"
    assert got.why == pg.BY_SECTOR


def test_분야가_여럿이면_글에서_먼저_나온_것이_이긴다():
    """사람이 적은 차례가 곧 그 사람의 우선순위다 — 앱이 순위를 지어내지 않는다."""
    assert pg.decide(Fake(sectors="로봇, AI, 소부장")).group == pg.SMALL
    assert pg.decide(Fake(sectors="소부장, 로봇")).group == "딥테크·제조"


def test_같은_자리에서는_긴_낱말이_이긴다():
    """`헬스케어` 가 `헬스` 를 덮는다 — 안 그러면 표에 적은 차례가 판정을 흔든다."""
    got = pg.decide(Fake(sectors="헬스케어"))
    assert got.sector == "헬스케어·바이오"
    assert got.found == ("헬스케어",)


def test_선호_칸이_옮겨_온_글보다_앞에_선다():
    """선호 칸은 지금 적은 것이고 옮겨 온 글은 예전 것이다."""
    row = Fake(sectors="소부장", memo=moved("로보틱스"))
    assert pg.decide(row).group == "딥테크·제조"


def test_이름_없는_갈래는_특정분야로_가되_어느_갈래였는지_남긴다():
    """그 덩어리 안에서 무엇이 자라는지 볼 수 없으면 이름을 줄 때를 모른다."""
    got = pg.decide(Fake(sectors="로보틱스"))
    assert got.group == pg.SMALL
    assert got.sector == "모빌리티·물류"


def test_여러_단계에_걸치면_가장_높은_칸으로_둔다():
    """낮은 쪽으로 두면 작은 갈래가 실제보다 커 보여 비례가 흔들린다."""
    assert pg.decide(Fake(round_size="Seed~PreIPO")).group == pg.LATE
    assert pg.decide(Fake(round_size="Series A~B")).group == pg.MID
    assert pg.decide(Fake(round_size="Pre-seed ~ Pre-A")).group == pg.EARLY


def test_표기가_갈려도_한_갈래로_모인다():
    """`invest_stage` 가 이미 하는 일이다 — 여기서 다시 다루지 않는다."""
    for text in ("Series C 이상 6/30", "시리즈 B-C 단계나 PRE-IPO 단계",
                 "pre-IPO단계 위주 6/23", "Pre IPO"):
        assert pg.decide(Fake(round_size=text)).group == pg.LATE, text


def test_방향만_적힌_줄도_읽는다():
    """`초기`·`후기` 만 적힌 줄이 실측에 열 넘게 있다 — 안 읽으면 통째로 샌다."""
    assert pg.decide(Fake(round_size="후기 단계")).group == pg.LATE
    assert pg.decide(Fake(memo=moved("초기 | 첫 라운드"))).group == pg.EARLY
    assert pg.decide(Fake(memo=moved("중기"))).group == pg.MID


def test_금융이라는_말은_분야로_안_읽는다():
    """`신기술금융본부` 는 부서 이름이지 핀테크 수요가 아니다 — 실측에서 걸렸다."""
    got = pg.decide(Fake(memo=moved("신기술금융본부")))
    assert got.group == pg.COMMON
    assert got.why == pg.BY_NONE


def test_아무것도_안_읽히면_공통이다():
    """**사용자가 정한 말이다** — 특이사항이 없는 투자사는 한 갈래로 묶는다."""
    assert pg.decide(Fake()).group == pg.COMMON
    assert pg.decide(Fake(sectors="   ", memo="")).group == pg.COMMON


def test_그룹을_비워_두는_갈래는_없다():
    """`group` 은 늘 값이 있다 — 비우면 '아직 안 묶은 사람' 과 섞인다."""
    for row in (Fake(), Fake(sectors="딥테크"), Fake(round_size="Seed"),
                Fake(memo=moved("보류 | 출자기관"))):
        assert pg.decide(row).group


# ── 분야도 라운드도 아닌 축 ─────────────────────────────────────────────────
#
# 사람이 예전 그룹 칸에 스스로 달아 둔 딱지 셋(`보류` · `대형` · `지역 한정`).
# 그대로 두면 전부 `공통` 에 섞이는데, **특이사항이 없는 것이 결코 아니다.**


def test_보류는_분야와_라운드보다_먼저_본다():
    """**이 파일에서 두 번째로 중요한 검사다.**

    실측 다섯 줄 중 **셋**은 선호 칸에 단계 말이 함께 적혀 있다
    (`후기 6/16` · `Series C 6/18` · `후기 단계`). 분야·라운드를 먼저 돌리면
    그 셋이 `Series C 이상` 으로 들어가고, 그 그룹으로 딜을 보낼 때마다
    **"비상장 투자 계획 없음" 이라고 적어 둔 분께 딜이 함께 나간다** — 안 묶는
    것보다 나쁘다.
    """
    for kw in ({"round_size": "후기 6/16"},
               {"round_size": "Series C 6/18", "stages": "SeriesC"},
               {"sectors": "후기 단계"},
               {"sectors": "딥테크"}):
        row = Fake(memo=moved("보류 | 비상장 투자 계획 없음"), **kw)
        assert pg.decide(row).group == pg.HOLD, kw
        assert pg.decide(row).why == pg.BY_LABEL, kw


def test_대형과_지역_한정은_분야_라운드_뒤에_본다():
    """안 보낸다는 뜻이 아니라 **조건이 있다**는 뜻이다. 사용자가 나누기로 한
    축은 분야와 라운드이므로, 그 둘로 읽히면 그쪽이 더 구체적이다.
    """
    assert pg.decide(Fake(memo=moved("대형 | 100억~1000억"))).group == pg.BIG
    # 분야가 읽히면 분야가 이긴다.
    row = Fake(sectors="딥테크", memo=moved("대형 | 100억~1000억"))
    assert pg.decide(row).group == "딥테크·제조"
    # 라운드가 읽히면 라운드가 이긴다.
    row = Fake(round_size="Series C 이상", memo=moved("지역 한정 | 비수도권"))
    assert pg.decide(row).group == pg.LATE


def test_딱지는_맨_앞만_본다():
    """글 아무 데서나 낱말을 찾으면 `보류 해제` 같은 말까지 걸린다.

    실측으로 세 딱지 모두 **맨 앞에서만** 나오고 글 가운데서 나오는 줄은 하나도
    없어, 좁게 보아 잃는 것이 없다.
    """
    assert pg.decide(Fake(memo=moved("후기 | 보류 검토"))).group != pg.HOLD
    assert pg.lead_label("보류 | 출자기관") == "보류"
    assert pg.lead_label("") == ""


def test_딱지_안의_가운뎃점은_구분_기호가_아니다():
    """`환경·에너지` · `M&A·로보틱스` 처럼 **딱지 안에서** 쓰인다 — 그것까지
    구분 기호로 보면 딱지가 반토막 난다. 가르는 기호는 `|` 뿐이다."""
    assert pg.lead_label("환경·에너지 | 폐플라스틱") == "환경에너지"


def test_지역_한정은_띄어쓰기가_달라도_한_딱지다():
    """모양을 지우는 자는 그룹 이름을 알아보는 자와 **같다**(`group_name.squash`)."""
    for text in ("지역 한정 | 비수도권", "지역한정 | 비수도권"):
        assert pg.decide(Fake(memo=moved(text))).group == pg.REGION, text


def test_대형_둘은_한_그룹이다():
    """세부가 달라도(`매출·투자유치 규모 큰 곳` / `100억~1000억 | M&A·볼트온`)
    사람이 스스로 **같은 딱지**를 달았다. 앱이 그 판단을 쪼갤 근거가 없고,
    세부는 메모에 그대로 실려 나간다(`llm_brief` 가 메모를 함께 내보낸다).
    """
    a = pg.decide(Fake(memo=moved("대형 | 매출·투자유치 규모 큰 곳")))
    b = pg.decide(Fake(memo=moved("대형 | 100억~1000억 | M&A·볼트온")))
    assert a.group == b.group == pg.BIG


def test_신기술금융본부는_공통으로_간다():
    """부서 이름일 뿐 선호가 아니다 — 사용자가 든 딱지는 셋뿐이다."""
    got = pg.decide(Fake(memo=moved("신기술금융본부")))
    assert got.group == pg.COMMON
    assert got.why == pg.BY_NONE


def test_보류라는_이름만으로는_발송이_안_막힌다():
    """**이름은 앱의 어느 발송 판정도 지나지 않는다.**

    막는 값은 `VcContact.status` 의 `검토중단` 하나다. 이 검사는 그 사실을
    글로만 적어 두지 않고 **코드로 못 박는다** — 언젠가 누가 그룹 이름으로
    막으려 들면 여기가 먼저 말해 준다.
    """
    from app.models import VcContact
    from app.services import sheet_owner

    row = VcContact(user_id=1, name="가상", group_name=pg.HOLD,
                    connect_stage="connected", status="active")
    assert sheet_owner.can_send_to(row) is True     # 그룹 이름은 안 막는다
    row.status = sheet_owner.STATUS_PAUSED
    assert sheet_owner.can_send_to(row) is False    # 막는 것은 이 값이다


def test_이름에_뜻이_보인다():
    """이 값이 딜 소개를 맞추는 LLM 에게 그대로 나간다 — 이름만 읽고 무슨
    조건인지 알 수 있어야 한다. `보류` 만으로는 무엇을 멈춘 것인지 모른다."""
    assert "딜 소개" in pg.HOLD and "보류" in pg.HOLD
    assert "대형" in pg.BIG
    assert "지역" in pg.REGION
    # 쉼표가 들면 화면의 보기 목록이 한 값을 둘로 쪼갠다(`group_name.CHOICES`).
    for name in pg.OUTPUTS:
        assert "," not in name, name


# ── ④ 넣는 스크립트 ─────────────────────────────────────────────────────────

def _seed(path: Path):
    """지어낸 명단 한 벌. 꼴마다 한 줄씩 심고 스크립트가 어떻게 가르는지 본다."""
    con = sqlite3.connect(str(path))
    try:
        con.execute(
            "CREATE TABLE vc_contacts (id INTEGER PRIMARY KEY, group_name TEXT,"
            " sectors TEXT, round_size TEXT, stages TEXT, memo TEXT,"
            " source_sheet TEXT, is_hidden INTEGER DEFAULT 0, status TEXT)")
        rows = [
            # id, group, sectors, round, stages, memo, sheet, hidden
            (1, "A", None, None, None, None, SHEET, 0),            # → 공통
            (2, "A", "딥테크 6/16", None, None, None, SHEET, 0),   # → 딥테크·제조
            (3, "A", None, "Series C 이상", None, None, SHEET, 0),  # → Series C 이상
            (4, None, None, None, None, moved("초기 | Pre-seed"), SHEET, 0),
            (5, None, None, None, None, moved("보류 | 출자기관"), SHEET, 0),
            # 선호 칸에 단계 말이 함께 있어도 `보류` 가 이겨야 한다.
            (8, None, None, "Series C 6/18", "SeriesC",
             moved("보류 | 메자닌 중심"), SHEET, 0),
            (9, None, None, None, None, moved("대형 | 100억~1000억"), SHEET, 0),
            (10, None, None, None, None,
             moved("지역 한정 | 비수도권 3년 미만"), SHEET, 0),
            (11, None, None, None, None, moved("신기술금융본부"), SHEET, 0),
            # 감춘 줄 — 건드리면 안 된다
            (6, "C", "딥테크", None, None, None, SHEET, 1),
            # 남의 명단 — 건드리면 안 된다
            (7, "E그룹", "딥테크", None, None, None, OTHER_SHEET, 0),
        ]
        con.executemany(
            "INSERT INTO vc_contacts (id, group_name, sectors, round_size,"
            " stages, memo, source_sheet, is_hidden) VALUES (?,?,?,?,?,?,?,?)",
            rows)
        con.commit()
    finally:
        con.close()


def _run(path: Path, *args, code: int = 0) -> str:
    out = subprocess.run(
        [sys.executable, str(SCRIPT), "--db", str(path), "--sheet", SHEET,
         *args],
        capture_output=True, text=True, cwd=str(ROOT), check=False)
    assert out.returncode == code, out.stdout + out.stderr
    return out.stdout


def _groups(path: Path) -> dict:
    con = sqlite3.connect(str(path))
    try:
        return dict(con.execute("SELECT id, group_name FROM vc_contacts"))
    finally:
        con.close()


@pytest.fixture()
def fake_db(tmp_path):
    path = tmp_path / "fake.db"
    _seed(path)
    return path


def test_미리보기가_기본이고_DB_에_한_글자도_안_쓴다(fake_db):
    """`--apply` 를 안 주면 읽기 전용(`mode=ro`)으로 연다 — 쓸 길 자체가 없다."""
    before = _groups(fake_db)
    _run(fake_db)
    assert _groups(fake_db) == before


def test_미리보기가_그룹별_인원과_바뀌는_줄을_센다(fake_db):
    text = _run(fake_db)
    assert "그룹별 인원" in text
    # 감춘 줄 하나와 남의 명단 하나가 빠져 다섯 줄만 남는다.
    assert "손볼 줄 9개" in text
    assert "감춰서 뺀 줄 1개" in text
    assert "바뀌는 줄 9개" in text


def test_적어_둔_글은_있는데_안_읽힌_줄을_따로_보여_준다(fake_db):
    """새로 뜨는 줄이 있으면 그것이 **다음에 갈래를 하나 더 세울 자리**다.

    씨앗에서 그런 줄은 `신기술금융본부` 하나다 — 나머지 딱지 셋은 이제 제
    갈래를 갖는다.
    """
    text = _run(fake_db)
    assert "눈으로 볼 줄 1개" in text


def test_보류로_간_줄이_정말_안_나가는지_세어_준다(fake_db):
    """**이름만으로는 안 막힌다**는 사실을 미리보기가 말해야 한다.

    막는 값은 상태 칸의 `검토중단` 하나인데, 씨앗의 두 줄은 상태가 비어 있다.
    """
    text = _run(fake_db)
    assert pg.HOLD in text
    assert "발송이 안 막힌다" in text
    assert "검토중단" in text


def test_스크립트가_상태_칸을_건드리지_않는다(fake_db):
    """세어서 보여 줄 뿐이다 — 상태를 대신 바꾸면 그 줄이 화면에서 사라진다.
    사람이 정할 일이다."""
    saved = fake_db.parent / "b.json"
    _run(fake_db, "--apply", "--save-baseline", str(saved))
    con = sqlite3.connect(str(fake_db))
    try:
        got = dict(con.execute("SELECT id, status FROM vc_contacts"))
    finally:
        con.close()
    assert set(got.values()) == {None}


def test_감춘_줄과_남의_명단은_건드리지_않는다(fake_db):
    _run(fake_db, "--apply", "--save-baseline", str(fake_db.parent / "b.json"))
    got = _groups(fake_db)
    assert got[6] == "C"          # 감춘 줄
    assert got[7] == "E그룹"      # 남의 명단


def test_이미_값이_있어도_덮는다(fake_db):
    """빈 칸에만 얹으면 69줄이 `A` 인 채로 남아 아무것도 안 한 것이 된다."""
    _run(fake_db, "--apply", "--save-baseline", str(fake_db.parent / "b.json"))
    got = _groups(fake_db)
    assert got[1] == pg.COMMON
    assert got[2] == "딥테크·제조"
    assert got[3] == pg.LATE
    assert got[4] == pg.EARLY
    assert got[5] == pg.HOLD
    # 선호 칸에 `Series C` 가 있어도 `보류` 가 이긴다.
    assert got[8] == pg.HOLD
    assert got[9] == pg.BIG
    assert got[10] == pg.REGION
    assert got[11] == pg.COMMON


def test_되돌릴_파일_없이는_덮지_않는다(fake_db):
    before = _groups(fake_db)
    _run(fake_db, "--apply", code=2)
    assert _groups(fake_db) == before


def test_되돌리면_한_글자도_다르지_않다(fake_db):
    before = _groups(fake_db)
    saved = fake_db.parent / "b.json"
    _run(fake_db, "--apply", "--save-baseline", str(saved))
    assert _groups(fake_db) != before
    _run(fake_db, "--restore", str(saved), "--apply")
    assert _groups(fake_db) == before


def test_되돌리기도_apply_를_요구한다(fake_db):
    saved = fake_db.parent / "b.json"
    _run(fake_db, "--apply", "--save-baseline", str(saved))
    after = _groups(fake_db)
    _run(fake_db, "--restore", str(saved), code=2)
    assert _groups(fake_db) == after


def test_계획대로_바뀌었는지_맞춰_본다(fake_db):
    saved = fake_db.parent / "b.json"
    _run(fake_db, "--apply", "--save-baseline", str(saved))
    text = _run(fake_db, "--baseline", str(saved))
    assert "어긋남 0줄" in text


def test_몇_번을_돌려도_같은_자리에_선다(fake_db):
    saved = fake_db.parent / "b.json"
    _run(fake_db, "--apply", "--save-baseline", str(saved))
    once = _groups(fake_db)
    _run(fake_db, "--apply", "--save-baseline", str(fake_db.parent / "c.json"))
    assert _groups(fake_db) == once
    assert "바뀌는 줄 0개" in _run(fake_db)


def test_미리보기는_값을_안_찍는다(fake_db):
    """이 칸에는 투자사 이야기가 섞여 있다. 기본은 모양(길이)뿐이다.

    값이 실제로 찍힐 수 있는 자리는 **눈으로 볼 줄**(③)이다 — 거기에만 사람이
    적어 둔 글이 통째로 실린다.
    """
    text = _run(fake_db)
    assert "신기술금융본부" not in text
    assert "딥테크 6/16" not in text
    assert "신기술금융본부" in _run(fake_db, "--show-values")


def test_명단을_안_적으면_아무것도_안_한다(fake_db):
    """**기본값을 두지 않는다.** 이 스크립트는 값을 덮으므로, `--sheet` 를
    깜빡한 명령이 조용히 남의 명단을 덮으면 안 된다.
    """
    before = _groups(fake_db)
    out = subprocess.run(
        [sys.executable, str(SCRIPT), "--db", str(fake_db)],
        capture_output=True, text=True, cwd=str(ROOT), check=False)
    assert out.returncode == 2, out.stdout + out.stderr
    assert _groups(fake_db) == before


def test_없는_명단을_적으면_멈춘다(fake_db):
    """이름을 잘못 적으면 0줄이 나온다 — 조용히 끝나면 다 됐다고 읽는다."""
    out = subprocess.run(
        [sys.executable, str(SCRIPT), "--db", str(fake_db),
         "--sheet", "그런명단없음"],
        capture_output=True, text=True, cwd=str(ROOT), check=False)
    assert out.returncode == 2, out.stdout + out.stderr
