"""칸마다의 **`수정한 날짜`** — 세 칸에 각각, 리마인드는 석 달치 각각.

> "투자컨설턴트 메뉴의 리스트 탭에서 **딜 소개문구랑 카톡 연결 여부 컬럼,
>  당월 리마인드 컬럼에 각각 수정한 날짜를 붙여주고 시간 까지만 보이게** 해줘,
>  리마인드 컬럼이 **최근 3개월 치**가 보이고 있는데 **수정한 날짜도 같이
>  3개월치**가 보여야 함."

## 어디서 날짜를 끌어왔나 — **줄에 담았다. `edit_logs` 는 못 쓴다**

이 파일의 `test_수정_로그로는_못_한다` 가 그것을 **실제로 돌려** 보인다.
두 가지가 다 막는다.

  · **자기 줄을 고친 것은 아예 안 남는다.** `services/edit_log.py` 의
    `_row_scope` 가 `owner_id == actor_id` 인 UPDATE 를 버린다. 이 표는 줄마다
    담당이 붙어 있고 그 담당이 자기 줄을 고치는 화면이다.
  · **달을 구분할 수가 없다.** 석 달치가 `notes` **한 칸**에 JSON 으로 들어
    있어서, 남의 줄을 고쳐 로그가 남아도 `notes 바뀜` 한 줄뿐이다.

그래서 `field_stamps` 를 줄에 담는다(0080). 덤으로 **조회가 한 번도 안 는다** —
344줄짜리 표에서 줄마다 로그를 캐물으면 344번 나간다.

## 이 파일이 지키는 것

  1. 세 칸에 **각각** 붙고, 리마인드는 **석 달치 각각**이다.
  2. **그 칸이 바뀐 때**다 — 옆 칸을 고쳐도 안 움직인다(줄 단위면 여기서 깨진다).
  3. 꼴은 `clock.stamp_text` 한 곳에서 온다 — 여기에 날짜 셈을 다시 안 적는다.
  4. 바뀐 칸만 찍는다 · 사람이 못 고친다 · 이주가 값을 안 지어 넣는다.
  5. **조회가 안 는다** — 줄이 늘어도 질의 수가 그대로다.
  6. 날짜가 값·검색·갈래에 **안 섞인다.**

이름·기업명·내용은 전부 지어낸 값이다 — 저장소가 공개다.
"""
from __future__ import annotations

import json
import pathlib
import re
import shutil
import subprocess

import pytest
from sqlalchemy import event, select

from .conftest import DEMO_PASSWORD

STARTUP = "스타트업"
ROOT = pathlib.Path(__file__).resolve().parent.parent
REVISION = "0080_consulting_field_stamps"


@pytest.fixture()
def allowed(client, db, users):
    users["u1"].can_view_consulting = 1
    db.commit()
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    return client


def _row(db, user_id, **kw):
    from app.models import ConsultingCompany

    row = ConsultingCompany(user_id=user_id, **kw)
    db.add(row)
    db.commit()
    return row


def _open(client, sheet=STARTUP):
    from urllib.parse import quote

    return client.get(f"/consulting?sheet={quote(sheet)}").text


def _stamps(db, row_id) -> dict:
    from app.models import ConsultingCompany

    db.expire_all()
    return json.loads(db.get(ConsultingCompany, row_id).field_stamps or "{}")


def _column(db, label="9월 마지막주 리마인드 톡 or TEL"):
    from app.models import ConsultingColumn

    col = ConsultingColumn(label=label, position=0, sheet=STARTUP)
    db.add(col)
    db.commit()
    return col


# --- 1. 세 칸에 각각 -----------------------------------------------------------

@pytest.mark.parametrize("field", ["deal_pitch", "kakao_joined"])
def test_고친_칸에만_날짜가_찍힌다(allowed, db, users, field):
    row = _row(db, users["u1"].id, sheet=STARTUP, position=1, company_name="샘플가")
    allowed.patch(f"/api/consulting/{row.id}", json={field: "값"})
    assert list(_stamps(db, row.id)) == [field], _stamps(db, row.id)


def test_옆_칸을_고쳐도_안_움직인다(allowed, db, users):
    """**줄 단위(`updated_at`)면 여기서 깨진다.** 딜 소개문구만 고쳤는데 카톡
    칸 밑에도 같은 날짜가 뜨면 화면이 "그때 카톡 칸을 고쳤다" 고 거짓말한다.
    이것이 이 요청의 핵심이다."""
    row = _row(db, users["u1"].id, sheet=STARTUP, position=1, company_name="샘플나")
    allowed.patch(f"/api/consulting/{row.id}", json={"kakao_joined": "O"})
    first = _stamps(db, row.id)["kakao_joined"]
    allowed.patch(f"/api/consulting/{row.id}", json={"deal_pitch": "한 줄"})
    after = _stamps(db, row.id)
    assert after["kakao_joined"] == first, "안 고친 칸의 날짜가 움직였습니다"
    assert after["deal_pitch"] != "" and "deal_pitch" in after
    # 줄 전체의 시각은 **바뀐다** — 그래서 저것을 쓰면 안 된다는 것이 요지다.
    from app.models import ConsultingCompany

    assert db.get(ConsultingCompany, row.id).updated_at


def test_달마다_제_날짜다(allowed, db, users):
    """리마인드가 석 달치 서므로 날짜도 석 달치다. 한 개만 붙이면 9월 칸을
    고쳤는데 7월 칸 밑의 날짜까지 바뀐 것처럼 보인다."""
    from app.routers.consulting import note_stamp_key

    jul, aug, sep = (_column(db, f"{m}월 마지막주 리마인드 톡 or TEL")
                     for m in (7, 8, 9))
    row = _row(db, users["u1"].id, sheet=STARTUP, position=1, company_name="샘플다")
    allowed.patch(f"/api/consulting/{row.id}", json={"notes": {str(jul.id): "7월"}})
    allowed.patch(f"/api/consulting/{row.id}", json={"notes": {str(sep.id): "9월"}})
    got = _stamps(db, row.id)
    assert note_stamp_key(jul.id) in got
    assert note_stamp_key(sep.id) in got
    assert note_stamp_key(aug.id) not in got, "안 고친 달에 날짜가 붙었습니다"


def test_화면에_세_칸_모두_잔글씨가_선다(allowed, db, users):
    """**석 달 × 리마인드 + 둘 = 다섯 자리**다. 하나라도 빠지면 그 칸만
    조용히 날짜가 없는 표가 된다."""
    from app.routers.consulting import note_stamp_key

    cols = [_column(db, f"{m}월 마지막주 리마인드 톡 or TEL") for m in (7, 8, 9)]
    row = _row(db, users["u1"].id, sheet=STARTUP, position=1, company_name="샘플라")
    allowed.patch(f"/api/consulting/{row.id}", json={"deal_pitch": "한 줄"})
    allowed.patch(f"/api/consulting/{row.id}", json={"kakao_joined": "O"})
    for col in cols:
        allowed.patch(f"/api/consulting/{row.id}",
                      json={"notes": {str(col.id): f"{col.label[:2]} 통화"}})
    body = _open(allowed)
    subs = re.findall(r'<div class="cell-sub muted"[^>]*>([^<]*)</div>', body)
    assert len(subs) == 5, (len(subs), subs)
    # 다섯 자리 전부 실제 날짜 꼴이다(`2026-09-21 14:30…`).
    for text in subs:
        assert re.match(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}", text), text
    # 열쇠도 화면과 서버가 같은 것을 쓴다.
    got = _stamps(db, row.id)
    assert {note_stamp_key(c.id) for c in cols} <= set(got)


def test_값은_cell_main_안에_들어간다(allowed, db, users):
    """값과 날짜가 한 `td` 에 같이 서므로, 편집기가 값만 읽을 수 있어야 한다
    (`consulting.js` 의 `valueBox` — `tests/js/consulting_field_stamp_test.js`
    가 실제로 돌려 본다). 감싸는 것을 잊으면 날짜가 값에 눌어붙는다."""
    _row(db, users["u1"].id, sheet=STARTUP, position=1, company_name="샘플마",
         deal_pitch="스마트팜 관제")
    body = _open(allowed)
    assert '<td class="cell multi" data-field="deal_pitch">' \
           '<div class="cell-main">스마트팜 관제</div>' in body, \
        "값이 `.cell-main` 으로 안 감싸져 있습니다"


def test_날짜가_없으면_잔글씨_상자_자체를_안_세운다(allowed, db, users):
    """344줄짜리 표다. 빈 상자를 늘 세우면 **모든 줄의 키**가 한 줄만큼 오른다
    — 이 저장소가 넓은 표의 위아래 여백을 6→4px 로 깎아 되찾은 그 자리다."""
    _row(db, users["u1"].id, sheet=STARTUP, position=1, company_name="샘플바",
         deal_pitch="아직 한 번도 안 고침")
    body = _open(allowed)
    assert "cell-sub" not in body, "고친 적 없는 칸에 빈 잔글씨 상자가 섰습니다"


# --- 2. 꼴은 한 곳에서 -------------------------------------------------------

def test_꼴을_만드는_자리는_clock_stamp_text_한_곳이다(allowed, db, users):
    """`시간 까지만` 을 여기서 잘라 적으면 같은 값이 두 꼴로 보인다. 초를
    뺄지 말지는 `app/clock.py` 가 정한다 — 이 커밋은 **거기를 안 건드린다.**"""
    from app import clock
    from app.models import ConsultingCompany
    from app.routers import consulting

    row = _row(db, users["u1"].id, sheet=STARTUP, position=1, company_name="샘플사")
    allowed.patch(f"/api/consulting/{row.id}", json={"deal_pitch": "한 줄"})
    db.expire_all()
    company = db.get(ConsultingCompany, row.id)
    raw = json.loads(company.field_stamps)["deal_pitch"]
    shown = consulting.shown_stamps(company)["deal_pitch"]
    assert shown == clock.stamp_text(raw)
    # 라우터에 날짜 만드는 셈이 없다 — 부르기만 한다.
    src = (ROOT / "app" / "routers" / "consulting.py").read_text(encoding="utf-8")
    for banned in ("strftime", "[:16]", "[:19]", 'replace("T"'):
        assert banned not in src, f"날짜 꼴을 라우터에서 다시 만들고 있습니다: {banned}"
    # 담기는 값은 **자른 적 없는 원본**이다 — 자른 값을 담으면 나중에 꼴을
    # 바꿀 때 이미 담긴 것이 안 따라온다.
    assert "T" in raw and len(raw) > 19, raw


def test_브라우저도_꼴을_안_만든다():
    """서버가 보내 준 글자를 그대로 적는다 — 여기서 다시 자르면 같은 값이
    두 꼴로 보인다(`companies.js`·`contacts.js` 가 같은 규칙이다)."""
    js = (ROOT / "app" / "static" / "js" / "consulting.js").read_text(encoding="utf-8")
    body = js.split("function showStamp", 1)[1].split("\n  }", 1)[0]
    for banned in ("slice(", "substr", "toISOString", "Date("):
        assert banned not in body, f"브라우저가 날짜 꼴을 만들고 있습니다: {banned}"


def test_clock_py_에_날짜_셈을_안_더했다():
    """**다른 작업이 지금 `stamp_text` 에서 초를 빼고 있다.** 여기서 같이
    고치면 두 판이 같은 줄에서 부딪힌다 — 부르기만 한다.

    파일을 안 건드렸다는 것은 `git` 이 있을 때만 볼 수 있으므로(시험
    컨테이너에는 없다), 여기서는 **이쪽 코드가 저 함수를 부르기만 하는가**를
    본다. 그쪽이 초를 빼든 말든 이 화면은 같이 움직인다.
    """
    src = (ROOT / "app" / "routers" / "consulting.py").read_text(encoding="utf-8")
    assert "from ..clock import stamp_text" in src
    # `shown_stamps` 안에서 그 함수 말고 다른 셈을 하지 않는다.
    body = src.split("def shown_stamps", 1)[1].split("\n\n\n", 1)[0]
    assert "stamp_text(value)" in body
    node = shutil.which("git")
    if not node:
        pytest.skip("git 없음 — 파일 대조는 호스트에서 본다")
    r = subprocess.run([node, "diff", "--name-only", "origin/main...HEAD"],
                       cwd=ROOT, capture_output=True, text=True)
    if r.returncode != 0:
        pytest.skip("git 비교를 못 했습니다")
    assert "app/clock.py" not in r.stdout.split(), r.stdout


# --- 3. 바뀐 칸만 · 사람이 못 고친다 ------------------------------------------

def test_같은_값을_다시_저장하면_안_움직인다(allowed, db, users):
    """안 그러면 칸을 눌렀다 아무것도 안 고치고 나온 것도 `고쳤다` 가 되고,
    API 로 날짜를 얼마든지 밀 수 있다."""
    row = _row(db, users["u1"].id, sheet=STARTUP, position=1, company_name="샘플아")
    allowed.patch(f"/api/consulting/{row.id}", json={"deal_pitch": "한 줄"})
    first = _stamps(db, row.id)["deal_pitch"]
    allowed.patch(f"/api/consulting/{row.id}", json={"deal_pitch": "한 줄"})
    assert _stamps(db, row.id)["deal_pitch"] == first


def test_사람이_못_고친다(allowed, db, users):
    """고칠 수 있으면 "언제 고쳤나" 가 곧 거짓이 된다
    (`services/contact_columns.py` 의 `source="stamp"` 가 같은 이유로 갈래를
    따로 두었다)."""
    from app.models import ConsultingCompany
    from app.routers.consulting import CompanyIn

    assert "field_stamps" not in CompanyIn.model_fields
    row = _row(db, users["u1"].id, sheet=STARTUP, position=1, company_name="샘플자")
    allowed.patch(f"/api/consulting/{row.id}",
                  json={"field_stamps": '{"deal_pitch": "1999-01-01T00:00:00+09:00"}'})
    db.expire_all()
    assert not db.get(ConsultingCompany, row.id).field_stamps
    # 화면에도 눌러 고칠 칸으로 안 선다.
    assert 'data-field="field_stamps"' not in _open(allowed)


def test_시트_올리기는_날짜를_안_찍는다(db, users):
    """통째로 갈아끼우는 길이라 한 번에 수백 칸이 같은 시각으로 찍힌다. 그러면
    `수정한 날짜` 가 "누가 언제 이 칸을 챙겼나" 가 아니라 "마지막으로 시트를
    언제 올렸나" 가 된다 — 물음이 다르다."""
    from app.models import ConsultingCompany
    from app.routers.consulting import apply_rows, parse_rows

    parsed = parse_rows([["NO", "기업명", "기업 관리"], ["1", "샘플차", "관리 중"]])
    apply_rows(db, parsed, users["u1"])
    row = db.execute(select(ConsultingCompany)
                     .where(ConsultingCompany.company_name == "샘플차")).scalar_one()
    assert not row.field_stamps


# --- 4. 조회가 안 는다 --------------------------------------------------------

def _count_render(allowed):
    """화면 한 번 그리는 동안 나간 질의 수."""
    from app.db import engine

    seen = []

    def tally(conn, cursor, statement, params, context, executemany):
        seen.append(statement)

    event.listen(engine, "before_cursor_execute", tally)
    try:
        _open(allowed)
    finally:
        event.remove(engine, "before_cursor_execute", tally)
    return len(seen)


def test_날짜를_붙여도_질의가_한_번도_안_는다(allowed, db, users):
    """344줄짜리 표다. 줄마다 날짜를 캐물으면 344번 나간다 — 그래서 로그 표가
    아니라 **줄에** 담았고, 그러면 날짜는 이미 떠 온 줄에 얹혀 온다.

    **같은 줄 수로 두 번 잰다** — 날짜가 하나도 없을 때와 줄마다 다섯 개씩
    붙어 있을 때. 표를 그리는 다른 자리에도 줄마다 도는 조회가 있어서
    (`is_contract`/`is_startup` 이 줄마다 `cs.ensure` 를 부른다 — 이 요청
    **밖의** 자리다) 줄 수를 늘려 견주면 그쪽 몫까지 같이 잡힌다. 여기서 봐야
    하는 것은 **이 기능이 몇 번을 더 쓰는가**이고, 답은 0이다.
    """
    from app.routers.consulting import note_stamp_key

    col = _column(db)
    rows = [_row(db, users["u1"].id, sheet=STARTUP, position=i,
                 company_name=f"샘플{i}", deal_pitch="한 줄", kakao_joined="O")
            for i in range(1, 21)]
    # 한 번 그려 **준비 작업을 털어 낸다** — 화면을 처음 열 때 이번 달 칸을
    # 세우는 자리가 있어(`monthly_columns.ensure_consulting`) 첫 판에만 질의가
    # 몇 개 더 붙는다. 그것까지 같이 세면 두 번째가 더 적게 나온다.
    _open(allowed)
    bare = _count_render(allowed)

    for r in rows:
        allowed.patch(f"/api/consulting/{r.id}",
                      json={"deal_pitch": "고친 한 줄", "kakao_joined": "X",
                            "notes": {str(col.id): "통화"}})
    assert len(_stamps(db, rows[0].id)) == 3
    stamped = _count_render(allowed)

    assert stamped == bare, (
        f"날짜가 없을 때 {bare}번, 줄마다 붙었을 때 {stamped}번 — "
        "줄마다 캐묻고 있습니다")
    assert note_stamp_key(col.id) in _stamps(db, rows[0].id)


# --- 5. `edit_logs` 로는 못 한다 (실제로 돌려 보인다) --------------------------

def test_수정_로그로는_못_한다(allowed, db, users):
    """**끌어올 수 있었는지 실제로 확인한 결과다.** 둘 다 막는다.

      ① 자기 줄을 고친 것은 로그에 **아예 안 남는다**(`_row_scope`).
         이 화면은 줄마다 담당이 붙어 있고 그 담당이 자기 줄을 고치는 자리라,
         **거의 모든 편집**이 여기 해당한다.
      ② 남의 줄이라 로그가 남아도, 월별 리마인드 석 달치가 `notes` 한 칸에
         JSON 으로 들어 있어 `notes 바뀜` 한 줄뿐이다 — **어느 달인지 모른다.**

    주석은 낡는다. 이 시험이 그 두 사실을 붙들어 둔다.
    """
    from app.models import ConsultingCompany, EditLog

    col = _column(db)
    mine = _row(db, users["u1"].id, sheet=STARTUP, position=1, company_name="샘플카")
    allowed.patch(f"/api/consulting/{mine.id}", json={"deal_pitch": "한 줄"})
    allowed.patch(f"/api/consulting/{mine.id}", json={"notes": {str(col.id): "통화"}})
    logs = db.execute(select(EditLog)
                      .where(EditLog.table_name == "consulting_companies")).scalars().all()
    assert logs == [], "① 이 사실이 바뀌었습니다 — 자기 줄 편집이 로그에 남습니다"
    # 그래도 날짜는 제대로 찍혀 있다 — 줄에 담았기 때문이다.
    assert len(_stamps(db, mine.id)) == 2

    others = _row(db, users["u2"].id, sheet=STARTUP, position=2, company_name="샘플타")
    users["u1"].role = "admin"
    db.commit()
    allowed.patch(f"/api/consulting/{others.id}",
                  json={"notes": {str(col.id): "통화"}})
    logs = db.execute(select(EditLog)
                      .where(EditLog.row_id == others.id)).scalars().all()
    assert logs, "남의 줄인데도 로그가 안 남았습니다"
    fields = [c["field"] for log in logs for c in json.loads(log.changes_json)]
    assert "notes" in fields
    assert str(col.id) not in " ".join(fields), \
        "② 이 사실이 바뀌었습니다 — 로그가 달을 구분합니다"
    # 그 줄에도 날짜는 달마다 따로 찍혀 있다 — 로그가 못 하는 일을 줄이 한다.
    db.expire_all()
    assert isinstance(db.get(ConsultingCompany, others.id).field_stamps, str)
    assert list(_stamps(db, others.id)) == [f"note:{col.id}"]


# --- 6. 이주 -----------------------------------------------------------------

def test_이주는_기존_줄에_날짜를_지어_넣지_않는다():
    """`updated_at` 을 옮겨 담으면 **한 번도 고친 적 없는 칸에** 날짜가 붙는다
    — 앱이 아무도 확인한 적 없는 사실을 단정하는 것이다."""
    src = (ROOT / "alembic" / "versions" / f"{REVISION}.py").read_text(encoding="utf-8")
    for word in ("UPDATE", "update(", "execute(", "updated_at"):
        assert word not in src.split('"""')[-1], f"이주가 값을 건드립니다: {word}"


def test_모델과_마이그레이션이_같은_자료형을_말한다():
    import importlib.util as _u

    import sqlalchemy as sa

    from app.models import ConsultingCompany

    spec = _u.spec_from_file_location(
        REVISION, ROOT / "alembic" / "versions" / f"{REVISION}.py")
    mod = _u.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert [n for n, _k in mod.ADDED] == ["field_stamps"]
    assert isinstance(mod.ADDED[0][1], sa.Text)
    col = ConsultingCompany.__table__.columns["field_stamps"]
    assert isinstance(col.type, sa.Text) and col.nullable


def test_깨진_값이_화면을_안_죽인다(allowed, db, users):
    """읽다 터지면 표 한 줄이 아니라 **화면 전체**가 안 뜬다. 날짜가 안 보이는
    것과 표가 안 열리는 것은 무게가 다르다(`_notes` 와 같은 규칙)."""
    from app.models import ConsultingCompany

    row = _row(db, users["u1"].id, sheet=STARTUP, position=1, company_name="샘플파")
    db.get(ConsultingCompany, row.id).field_stamps = "{망가진"
    db.commit()
    assert "샘플파" in _open(allowed)


# --- 7. 화면 코드 -------------------------------------------------------------

def test_화면_코드를_그대로_돌려_본다():
    """서버만 고치면 반쪽이다 — 값과 날짜가 **한 칸에** 서는 순간 편집기가
    날짜를 값으로 먹는다. `tests/js/consulting_field_stamp_test.js` 가
    consulting.js 를 실제로 돌려 본다.
    로컬에서는 `node tests/js/consulting_field_stamp_test.js` 로도 돈다."""
    node = shutil.which("node")
    if not node:
        pytest.skip("node 미설치 — 브라우저 로직 테스트 생략")
    js = ROOT / "tests" / "js" / "consulting_field_stamp_test.js"
    r = subprocess.run([node, str(js)], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr
