"""투자컨설턴트 현황의 탭 — **이름을 코드에서 뺀 것**.

탭 셋(`스타트업` · `경영본부 전달 기업` · `월간 계약 업무현황표`)이 코드에 박힌
목록이었다. 이름을 고치려면 배포를 해야 했고, 실제로 한 번 고쳤을 때
(`중요 스타트업` → `스타트업`) 이름만 바꾸니 이미 들어간 줄이 **옛 이름의 유령
탭으로 갈라져서** 자료를 옮기는 마이그레이션을 따로 써야 했다(0039).

여기서 막는 것은 넷이다.

  1. **줄이 하나도 없어도 탭 셋은 선다** — 새 컨설턴트가 빈 화면을 보면
     없는 줄 알고 자기 시트를 또 만든다
  2. **이름을 바꾸면 그 탭의 줄들이 따라온다** — 안 따라오면 어느 탭에도 안 뜬다
  3. **표 모양이 이름에 안 매인다** — `월간 계약 업무현황표` 를 다른 이름으로
     불러도 계약 표 그대로여야 한다(이름으로 짝지으면 한 글자에 칸이 사라진다)
  4. **참고 자료는 모든 컨설턴트에게 같다** — 사람마다 갈리면 팀이 다른 문구를 쓴다

이름·회사·번호는 전부 지어낸 값이다 — 저장소가 공개다.
"""
from __future__ import annotations

import re

import pytest

from .conftest import DEMO_PASSWORD


def _tabs(html: str) -> list:
    """화면에 서 있는 명단 탭 이름들(참고 자료 탭은 뺀다)."""
    nav = re.search(r'<nav class="sheet-tabs">(.*?)</nav>', html, re.S)
    assert nav, "탭 줄을 찾지 못했습니다"
    return [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", cell)).strip()
            for cell in re.findall(r'<a class="sheet-tab (?!ref-tab)[^"]*"[^>]*>(.*?)</a>',
                                   nav.group(1), re.S)]


def _names(html: str) -> list:
    """탭 이름만 — 뒤에 붙은 건수를 뗀다."""
    return [re.sub(r"\s+\d+$", "", t) for t in _tabs(html)]


@pytest.fixture()
def consultant(db, users):
    """**새로 만든** 투자컨설턴트. 줄도 열도 하나 없는 상태다."""
    from fastapi.testclient import TestClient

    from app.main import create_app
    from app.models import User
    from app.services import auth as auth_svc

    db.add(User(id=71, name="컨설턴트시험", phone="01000000071", role="consultant",
                can_view_consulting=1,
                password_hash=auth_svc.hash_password(DEMO_PASSWORD)))
    db.commit()
    c = TestClient(create_app())
    assert c.post("/login", data={"phone": "01000000071",
                                  "password": DEMO_PASSWORD},
                  follow_redirects=False).status_code == 303
    return c


# ── 1. 줄이 없어도 탭은 선다 ────────────────────────────────────────────────

def test_새_컨설턴트도_탭_셋을_그대로_받는다(consultant, db):
    """빈 화면을 주면 **없는 줄 알고 자기 시트를 또 만든다.**

    탭 셋은 팀이 함께 쓰는 업무 단계라(스타트업 → 경영본부 전달 → 계약)
    사람마다 갈릴 것이 아니다.
    """
    from app.services.consulting_sheets import labels

    body = consultant.get("/consulting").text
    assert body.count("<tr data-id=") == 0, "밑자리에 줄이 있으면 이 검사가 헛돈다"
    assert _names(body) == labels(db)
    assert len(labels(db)) == 3


def test_줄이_없어도_탭에_0이_적힌다(consultant):
    """건수가 아예 없으면 탭이 고장 난 것으로 읽힌다."""
    for tab in _tabs(consultant.get("/consulting").text):
        assert tab.endswith(" 0"), tab


# ── 2. 이름을 바꾸면 줄이 따라온다 ──────────────────────────────────────────

def test_탭_이름을_바꾸면_그_탭의_줄이_따라온다(client, db, users):
    """이름만 바꾸고 줄을 안 옮기면 그 사람들이 **어느 탭에도 안 뜬다.**

    0039 마이그레이션이 고쳐야 했던 사고가 정확히 그것이다.
    """
    from app.models import ConsultingColumn, ConsultingCompany
    from app.services.consulting_sheets import STARTUP, by_kind

    users["u1"].can_view_consulting = 1
    db.commit()
    client.post("/login", data={"phone": users["u1"].phone,
                                "password": DEMO_PASSWORD})
    before = by_kind(db)[STARTUP].label
    db.add_all([
        ConsultingCompany(user_id=users["u1"].id, sheet=before, position=1,
                          company_name="샘플기업A"),
        ConsultingColumn(user_id=users["u1"].id, sheet=before,
                         label="8월 마지막주 리마인드 톡 or TEL", position=0),
    ])
    db.commit()

    after = "핵심 스타트업"
    r = client.post("/consulting/sheets/rename",
                    data={"kind": STARTUP, "label": after},
                    follow_redirects=False)
    assert r.status_code == 303

    db.expire_all()
    assert by_kind(db)[STARTUP].label == after
    assert db.query(ConsultingCompany).filter_by(
        company_name="샘플기업A").one().sheet == after, "줄이 옛 이름에 남았습니다"
    assert db.query(ConsultingColumn).one().sheet == after, "열이 옛 이름에 남았습니다"

    body = client.get(f"/consulting?sheet={after}").text
    assert after in _names(body) and before not in _names(body)
    assert "샘플기업A" in body, "이름을 바꿨더니 줄이 화면에서 사라졌습니다"
    assert "8월 마지막주 리마인드 톡 or TEL" in body


def test_빈_이름과_겹치는_이름은_받지_않는다(client, db, users):
    """이름 없는 탭은 누를 자리가 없고, 겹치면 두 탭의 줄이 섞인다."""
    from app.services.consulting_sheets import CONTRACT, STARTUP, by_kind

    users["u1"].can_view_consulting = 1
    db.commit()
    client.post("/login", data={"phone": users["u1"].phone,
                                "password": DEMO_PASSWORD})
    was = by_kind(db)[STARTUP].label
    other = by_kind(db)[CONTRACT].label

    for bad in ("", "   "):
        client.post("/consulting/sheets/rename",
                    data={"kind": STARTUP, "label": bad}, follow_redirects=False)
        db.expire_all()
        assert by_kind(db)[STARTUP].label == was, f"빈 이름({bad!r})이 들어갔습니다"

    client.post("/consulting/sheets/rename",
                data={"kind": STARTUP, "label": other}, follow_redirects=False)
    db.expire_all()
    assert by_kind(db)[STARTUP].label == was, "두 탭이 같은 이름이 됐습니다"


def test_이름을_바꿔도_기본_탭은_그대로_열린다(client, db, users):
    """첫 탭을 이름으로 찾으면, 바꾼 순간 화면이 엉뚱한 탭에서 열린다."""
    from app.services.consulting_sheets import STARTUP, default_label

    users["u1"].can_view_consulting = 1
    db.commit()
    client.post("/login", data={"phone": users["u1"].phone,
                                "password": DEMO_PASSWORD})
    client.post("/consulting/sheets/rename",
                data={"kind": STARTUP, "label": "1차 스타트업"},
                follow_redirects=False)
    db.expire_all()
    assert default_label(db) == "1차 스타트업"
    body = client.get("/consulting").text
    assert 'class="sheet-tab active"' in body.replace("  ", " ") or "active" in body
    assert "1차 스타트업" in _names(body)


# ── 3. 표 모양은 이름에 안 매인다 ───────────────────────────────────────────

def test_계약_탭은_이름을_바꿔도_계약_표다(client, db, users):
    """**이름으로 짝지으면 한 글자에 칸이 사라진다.**

    `월간 계약 업무현황표` 만 칸이 다른데(`계약월`·`성공보수율`·`계약금`) 그
    짝이 이름이면, 탭 이름을 고치는 순간 조용히 일반 표로 돌아간다.
    """
    from app.models import ConsultingCompany
    from app.routers.consulting import is_contract
    from app.services.consulting_sheets import CONTRACT, by_kind

    users["u1"].can_view_consulting = 1
    db.commit()
    client.post("/login", data={"phone": users["u1"].phone,
                                "password": DEMO_PASSWORD})
    before = by_kind(db)[CONTRACT].label
    db.add(ConsultingCompany(user_id=users["u1"].id, sheet=before, position=1,
                             region="6월", management="무료",
                             company_name="샘플기업/ 무료/ 3.5%/ 미정"))
    db.commit()

    def head(name):
        html = client.get(f"/consulting?sheet={name}").text
        return [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", c)).strip()
                for c in re.findall(r"<th\b[^>]*>(.*?)</th>", html, re.S)]

    want = ("계약월", "성공보수율", "계약금")
    assert all(w in head(before) for w in want), head(before)

    after = "월간 계약 현황"
    client.post("/consulting/sheets/rename",
                data={"kind": CONTRACT, "label": after}, follow_redirects=False)
    db.expire_all()
    assert is_contract(db, after), "이름을 바꾸니 계약 탭이 아니게 됐습니다"
    assert all(w in head(after) for w in want), (
        f"이름을 바꾸니 계약 표가 일반 표로 돌아갔습니다: {head(after)}")
    assert "샘플기업" in client.get(f"/consulting?sheet={after}").text


def test_표_모양은_이름이_아니라_열쇠로_짝짓는다():
    """짝을 이름으로 두면 이름을 고칠 수 있게 만든 것이 곧 함정이 된다."""
    import inspect

    from app.routers import consulting
    from app.services import consulting_sheets as cs

    assert set(consulting.SHEET_LAYOUTS) <= {cs.STARTUP, cs.HANDOVER, cs.CONTRACT}
    src = inspect.getsource(consulting)
    assert "SHEETS = [" not in src, "탭 이름 목록이 코드에 되살아났습니다"
    assert "def is_contract" in src


def test_탭_이름이_코드에_박혀_있지_않다():
    """이름을 코드가 알면, 화면에서 고친 이름이 그 자리에서만 옛 이름으로 남는다.

    **이 화면을 그리는 코드**만 본다(라우터와 템플릿). `스타트업` 은 다른 뜻으로
    쓰이는 흔한 말이라(좌측 [스타트업] 메뉴 · 투자사 갈래) 앱 전체를 훑으면
    상관없는 자리까지 걸려서, 검사를 통과시키려고 엉뚱한 곳을 고치게 된다.

    처음 세울 이름은 어딘가 적혀 있어야 하므로 `consulting_sheets.DEFAULTS`
    와 그것을 세우는 마이그레이션은 뺀다 — 그 뒤로는 아무도 안 읽는 값이다.
    """
    from pathlib import Path

    from app.services import consulting_sheets as cs

    root = Path(__file__).resolve().parent.parent
    names = [label for _, label in cs.DEFAULTS]
    hits = []
    for rel in ("app/routers/consulting.py", "app/templates/consulting.html"):
        raw = (root / rel).read_text(encoding="utf-8")
        body = re.sub(r"^\s*#.*$", "", raw, flags=re.M)
        body = re.sub(r'"""(?:.|\n)*?"""', "", body)
        body = re.sub(r"\{#.*?#\}", "", body, flags=re.S)
        for name in names:
            if name in body:
                hits.append(f"{rel} 에 `{name}`")
    assert not hits, ("탭 이름이 코드에 박혀 있습니다 — 화면에서 고쳐도 여기만 "
                      "옛 이름으로 남습니다:\n  " + "\n  ".join(hits))


def test_열을_세우면_지금_탭에_붙는다(client, db, users):
    """모델 기본값에 기대면 **탭 이름을 고친 뒤 새 열이 유령 탭에 쌓인다.**

    세운 사람 화면에는 아무것도 안 늘어나므로, 안 만들어진 줄 알고 또 누른다.
    """
    from app.models import ConsultingColumn
    from app.services.consulting_sheets import STARTUP, default_label

    users["u1"].can_view_consulting = 1
    db.commit()
    client.post("/login", data={"phone": users["u1"].phone,
                                "password": DEMO_PASSWORD})
    client.post("/consulting/sheets/rename",
                data={"kind": STARTUP, "label": "1차 스타트업"},
                follow_redirects=False)
    client.post("/consulting/columns", data={"label": "9월 리마인드"},
                follow_redirects=False)

    db.expire_all()
    col = db.query(ConsultingColumn).filter_by(label="9월 리마인드").one()
    assert col.sheet == default_label(db) == "1차 스타트업"
    assert "9월 리마인드" in client.get("/consulting?sheet=1차 스타트업").text


# ── 4. 참고 자료는 모든 컨설턴트에게 같다 ───────────────────────────────────

def test_참고_자료는_모든_컨설턴트에게_같다(consultant, db, users):
    """사람마다 갈리면 팀이 서로 다른 문구로 말하게 된다.

    `RefSheet` 에는 사람 칸이 없다 — 이 화면 자료는 처음부터 공용이다.
    새로 만든 계정에도 **똑같이** 보이는지 본다.
    """
    import json

    from fastapi.testclient import TestClient

    from app.main import create_app
    from app.models import RefSheet, User
    from app.services import auth as auth_svc

    title = "샘플 미팅 진행 스크립트"
    db.add(RefSheet(page="consulting", title=title, kind="text", position=0,
                    is_active=1,
                    content_json=json.dumps({"body": "샘플 안내문"},
                                            ensure_ascii=False)))
    db.add(User(id=72, name="컨설턴트시험2", phone="01000000072",
                role="consultant", can_view_consulting=1,
                password_hash=auth_svc.hash_password(DEMO_PASSWORD)))
    db.commit()

    other = TestClient(create_app())
    other.post("/login", data={"phone": "01000000072", "password": DEMO_PASSWORD})

    for who in (consultant, other):
        body = who.get("/consulting").text
        assert title in body, "새 컨설턴트에게 참고 자료가 안 보입니다"
    # 열어서 내용까지 같아야 한다 — 탭만 뜨고 안 열리면 본 것이 아니다.
    row = db.query(RefSheet).filter_by(title=title).one()
    for who in (consultant, other):
        assert "샘플 안내문" in who.get(f"/consulting?ref={row.id}").text


def test_참고_자료에_사람_칸이_없다():
    """사람마다 갈릴 자리가 **아예 없어야** 공용이 유지된다."""
    from app.models import RefSheet

    assert "user_id" not in RefSheet.__table__.columns
