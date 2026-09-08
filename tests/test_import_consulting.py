"""투자컨설턴트 현황 가져오기 — **한 담당자 몫씩.**

같은 탭을 컨설턴트 여럿이 각자의 시트로 들고 있다. 그래서 이 스크립트가
지우고 넣는 범위는 탭 하나가 아니라 **(탭, 담당자) 하나**다.

여기서 지키는 것 다섯:

1. **다른 담당자의 줄을 지우지 않는다.** 이 파일에서 가장 중요한 검사다 —
   예전에는 탭 이름만 보고 지워서, 두 번째 사람의 시트를 넣는 순간 첫 번째
   사람의 명단이 통째로 사라졌다. 나간 뒤에는 되돌릴 수가 없다.
2. **`--owner` 없이는 아무것도 안 한다.** 담당 없이 들어간 줄은 컨설턴트
   화면에 안 뜨고 관리자만 고칠 수 있으며, 무엇을 지울지도 정해지지 않는다.
3. **시트 탭 이름과 앱 탭 이름이 달라도 같은 탭으로 간다.** 안 받아 주면
   옛 이름의 유령 탭이 생기고 같은 명단이 두 탭으로 갈린다(0039 가 고쳐야
   했던 사고다). 띄어쓰기 차이도 같은 사고를 낸다.
4. **미리보기가 지울 줄 수를 말한다.** 넣을 것만 세면 사람이 사고를 막을 수
   없다 — 무엇이 사라지는지가 화면에 나와야 한다.
5. **월 칸은 지우지 않는다.** 칸은 탭마다 한 벌이라
   (`models.ConsultingColumn`) 지우면 그 달 기록이 팀 전체의 줄에서 사라진다.

기업명·사람 이름은 전부 지어낸 값이다 — 이 저장소는 공개다.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "import_consulting.py"

openpyxl = pytest.importorskip("openpyxl")

# 원본 시트의 머리글. `header_row` 가 `기업` 이 든 줄을 찾아 머리글로 삼는다.
HEAD = ["NO", "지역", "미팅일", "기업명", "기업 관리", "대표자", "연락처",
        "이메일", "8월 마지막주 리마인드 톡 or TEL"]


def sheet_file(tmp_path: Path, tabs: dict, name="현황.xlsx") -> str:
    """{탭 이름: [줄, …]} → xlsx 한 장. 줄은 기업명만 주면 나머지를 채운다."""
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for tab, names in tabs.items():
        ws = wb.create_sheet(tab[:31])
        ws.append(["투자컨설턴트 현황"])          # 시트에 있는 제목 줄
        ws.append(HEAD)
        for i, company in enumerate(names, start=1):
            ws.append([i, "샘플지역", "9/1", company, "관리 중", "샘플대표",
                       "01000000000", f"{company}@example.com", "O"])
    path = tmp_path / name
    wb.save(path)
    return str(path)


def run(*args, db=None) -> subprocess.CompletedProcess:
    """스크립트를 **따로 뜬 프로세스로** 돌린다.

    사람이 실제로 부르는 방식 그대로다. 한 함수를 불러 보는 것과 달리,
    인자를 다루는 자리(`--owner` 를 빼먹었을 때)까지 같이 지난다.
    """
    if db is not None:
        db.commit()          # 열어 둔 트랜잭션이 있으면 저쪽에서 못 읽는다
    out = subprocess.run([sys.executable, str(SCRIPT), *args],
                         cwd=ROOT, env={**os.environ}, capture_output=True,
                         text=True)
    if db is not None:
        db.expire_all()
    return out


def _rows(db, sheet=None):
    from app.models import ConsultingCompany

    q = db.query(ConsultingCompany)
    if sheet:
        q = q.filter_by(sheet=sheet)
    return {(r.company_name, r.user_id) for r in q.all()}


def _seed(db, user_id, sheet, names):
    from app.models import ConsultingCompany

    for i, name in enumerate(names, start=1):
        db.add(ConsultingCompany(user_id=user_id, sheet=sheet,
                                 company_name=name, position=i))
    db.commit()


@pytest.fixture()
def tabs(db):
    """지금 앱이 쓰는 탭 이름들."""
    from app.services import consulting_sheets as cs

    return {s.kind: s.label for s in cs.ensure(db)}


# --- 1. 남의 줄을 지우지 않는다 ------------------------------------------------

def test_다른_담당자의_줄을_지우지_않는다(db, users, tabs, tmp_path):
    """**이 파일에서 가장 중요한 검사다.**

    같은 탭을 두 사람이 나눠 갖는다. 두 번째 사람의 시트를 넣으면서 탭 이름만
    보고 지우면 첫 번째 사람의 명단이 통째로 사라진다 — 넣은 사람은 자기 줄이
    들어간 것만 보고 지나간다.
    """
    startup = tabs["startup"]
    _seed(db, users["u1"].id, startup, ["샘플가", "샘플나", "샘플다"])

    path = sheet_file(tmp_path, {startup: ["샘플라", "샘플마"]})
    out = run(path, "--owner", str(users["u2"].id), "--apply", db=db)
    assert out.returncode == 0, out.stderr

    kept = {name for name, uid in _rows(db, startup) if uid == users["u1"].id}
    assert kept == {"샘플가", "샘플나", "샘플다"}, (
        "다른 담당자의 줄이 사라졌습니다 — 지우는 범위가 담당자로 좁혀지지 "
        "않았습니다")
    mine = {name for name, uid in _rows(db, startup) if uid == users["u2"].id}
    assert mine == {"샘플라", "샘플마"}


def test_같은_담당자의_옛_줄은_갈아_끼운다(db, users, tabs, tmp_path):
    """시트가 원본이다 — 맞춰 넣으면 시트에서 지운 줄이 앱에 남는다."""
    startup = tabs["startup"]
    _seed(db, users["u1"].id, startup, ["샘플가", "샘플나"])

    path = sheet_file(tmp_path, {startup: ["샘플나", "샘플다"]})
    assert run(path, "--owner", str(users["u1"].id), "--apply",
               db=db).returncode == 0
    assert _rows(db, startup) == {("샘플나", users["u1"].id),
                                  ("샘플다", users["u1"].id)}


def test_다른_탭의_내_줄도_안_건드린다(db, users, tabs, tmp_path):
    """지우는 범위는 (탭, 담당자) 다 — 탭 하나를 올리면서 옆 탭까지 비우면
    안 된다."""
    startup, handover = tabs["startup"], tabs["handover"]
    _seed(db, users["u1"].id, handover, ["샘플가"])

    path = sheet_file(tmp_path, {startup: ["샘플나"]})
    assert run(path, "--owner", str(users["u1"].id), "--apply",
               db=db).returncode == 0
    assert _rows(db, handover) == {("샘플가", users["u1"].id)}


# --- 2. `--owner` 를 안 주면 아무것도 안 한다 -----------------------------------

def test_담당을_안_주면_아무것도_안_한다(db, users, tabs, tmp_path):
    """예전에는 안 줘도 돌았고, 그때 줄은 주인 없이 들어갔다.

    주인 없는 줄은 컨설턴트 화면에 안 뜨고 관리자만 고칠 수 있다
    (`routers/consulting.py` 의 `may_edit_row`). 지우는 범위도 정해지지 않는다.
    지우는 것이 섞여 있는 도구는 기본값이 조용히 도는 쪽이면 안 된다.
    """
    startup = tabs["startup"]
    _seed(db, users["u1"].id, startup, ["샘플가"])

    path = sheet_file(tmp_path, {startup: ["샘플나"]})
    out = run(path, "--apply", db=db)
    assert out.returncode != 0
    assert "--owner" in out.stderr
    # 넣지도, 지우지도 않았다.
    assert _rows(db, startup) == {("샘플가", users["u1"].id)}


# --- 3. 시트 탭 이름 → 앱 탭 이름 ----------------------------------------------

@pytest.mark.parametrize("raw, kind", [
    ("IR 스타트업", "startup"),          # 시트 쪽 이름
    ("중요 스타트업", "startup"),        # 앱의 옛 이름
    ("  스타트업  ", "startup"),         # 앞뒤 공백
    ("경영본부 전달기업", "handover"),   # 가운데 띄어쓰기 하나 차이
    ("경영본부  전달  기업", "handover"),
])
def test_시트_탭_이름이_달라도_같은_탭으로_간다(db, users, tabs, tmp_path,
                                               raw, kind):
    """안 받아 주면 옛 이름의 유령 탭이 생기고 같은 명단이 두 탭으로 갈린다."""
    path = sheet_file(tmp_path, {raw: ["샘플가"]})
    assert run(path, "--owner", str(users["u1"].id), "--apply",
               db=db).returncode == 0
    assert _rows(db, tabs[kind]) == {("샘플가", users["u1"].id)}
    # 유령 탭이 생기지 않았다 — 줄이 붙어 있는 탭은 그 하나뿐이다.
    from app.models import ConsultingCompany

    assert {r.sheet for r in db.query(ConsultingCompany).all()} == {tabs[kind]}


def test_탭_이름을_고친_뒤에도_같은_탭으로_간다(db, users, tmp_path):
    """짝은 이름이 아니라 **열쇠**로 맺는다(`ConsultingSheet.kind`).

    이름을 적어 두면 누가 탭 이름을 고친 날 짝이 조용히 끊어지고, 그날부터
    들어온 줄이 유령 탭으로 간다.
    """
    from app.services import consulting_sheets as cs

    cs.rename(db, cs.STARTUP, "관리 스타트업")
    db.commit()

    path = sheet_file(tmp_path, {"IR 스타트업": ["샘플가"]})
    assert run(path, "--owner", str(users["u1"].id), "--apply",
               db=db).returncode == 0
    assert _rows(db, "관리 스타트업") == {("샘플가", users["u1"].id)}


# --- 4. 미리보기 ---------------------------------------------------------------

def test_미리보기가_지울_줄_수를_말한다(db, users, tabs, tmp_path):
    """넣을 것만 세면 사람이 사고를 막을 수 없다 — 무엇이 사라지는지가
    화면에 나와야 한다."""
    startup = tabs["startup"]
    _seed(db, users["u1"].id, startup, ["샘플가", "샘플나", "샘플다"])

    path = sheet_file(tmp_path, {startup: ["샘플라"]})
    out = run(path, "--owner", str(users["u1"].id), db=db)
    assert out.returncode == 0
    assert "지울 줄 3개" in out.stdout, out.stdout
    assert "넣을 줄 1개" in out.stdout, out.stdout
    assert str(users["u1"].id) in out.stdout      # 누구 몫인지 적혀 있다


def test_미리보기는_아무것도_안_바꾼다(db, users, tabs, tmp_path):
    startup = tabs["startup"]
    _seed(db, users["u1"].id, startup, ["샘플가"])

    path = sheet_file(tmp_path, {startup: ["샘플나"]})
    assert run(path, "--owner", str(users["u1"].id), db=db).returncode == 0
    assert _rows(db, startup) == {("샘플가", users["u1"].id)}


# --- 5. 월 칸 -----------------------------------------------------------------

def test_월_칸은_지우지_않고_이름이_같으면_그대로_쓴다(db, users, tabs, tmp_path):
    """칸은 탭마다 한 벌이다 — 두 번째 사람의 시트를 넣으면서 새로 만들면
    같은 이름의 머리글이 하나 더 서고, 팀이 쓰던 칸의 기록이 갈린다."""
    from app.models import ConsultingColumn

    startup = tabs["startup"]
    kept = ConsultingColumn(sheet=startup, label=HEAD[-1], position=0)
    db.add(kept)
    db.commit()
    kept_id = kept.id

    path = sheet_file(tmp_path, {startup: ["샘플가"]})
    assert run(path, "--owner", str(users["u2"].id), "--apply",
               db=db).returncode == 0

    cols = db.query(ConsultingColumn).filter_by(sheet=startup).all()
    assert [c.id for c in cols] == [kept_id], "같은 이름의 칸이 하나 더 섰습니다"


def test_월_칸은_탭에_붙는다(db, users, tabs, tmp_path):
    """칸에 담당이 붙으면 `담당: 전체` 화면에서 같은 달 머리글이 사람 수만큼
    선다(`models.ConsultingColumn`)."""
    from app.models import ConsultingColumn

    path = sheet_file(tmp_path, {tabs["startup"]: ["샘플가"]})
    assert run(path, "--owner", str(users["u1"].id), "--apply",
               db=db).returncode == 0
    made = db.query(ConsultingColumn).all()
    assert [c.sheet for c in made] == [tabs["startup"]]
    assert not hasattr(ConsultingColumn, "user_id"), (
        "칸에 담당 칸이 다시 생겼습니다 — 같은 달 머리글이 사람 수만큼 섭니다")
