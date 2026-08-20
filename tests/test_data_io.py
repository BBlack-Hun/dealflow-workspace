"""투자사 현황 업로드 · 표 엑셀 내려받기.

여기서 지키려는 경계는 세 가지다.

1. **미리보기는 DB 를 건드리지 않는다.** 담당자 명단은 곧 발송 대상이라,
   확인하려고 눌렀는데 반영돼 버리면 그대로 오발송으로 이어진다.
2. **내려받은 표를 되올릴 수 없다.** 실제로 127명짜리 내보내기를 그대로 올렸더니
   활동 이력 635건이 '새 이력'으로 잡혔다 — 내보내기의 'IR 요청(누적)' 류 컬럼을
   임포트 파서가 월별 활동 컬럼으로 읽기 때문이다.
3. **남의 회차는 내려받을 수 없다.**
"""
from __future__ import annotations

import io

import pytest

from .conftest import DEMO_PASSWORD

openpyxl = pytest.importorskip("openpyxl")


def _sheet(rows, title="딜소개 현황") -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = title
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


HEADER = ["그룹", "담당자", "이름", "직함", "투자사명", "초대 완료여부", "메모"]
SAMPLE = [
    HEADER,
    ["A그룹", "", "홍길동", "심사역", "가나벤처스", "완료", "AI 초기"],
    ["A그룹", "", "김서연", "대표", "마바벤처스", "완료", ""],
]


@pytest.fixture()
def logged(client, users):
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    return client


def _upload(client, data: bytes, name="현황.xlsx", **form):
    return client.post(
        "/api/import/contacts",
        files={"file": (name, data,
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        data=form,
    )


def test_preview_does_not_touch_db(logged, db):
    """미리보기는 결과만 보여주고 아무 것도 남기지 않는다."""
    from app.models import VcContact

    before = db.query(VcContact).count()
    r = _upload(logged, _sheet(SAMPLE), dry_run="true")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["dry_run"] is True
    assert body["created"] == 2          # 생길 예정이라고 알려주되
    db.expire_all()
    assert db.query(VcContact).count() == before   # 실제로는 안 생긴다


def test_apply_creates_contacts(logged, db):
    from app.models import VcContact

    r = _upload(logged, _sheet(SAMPLE), dry_run="false")
    assert r.status_code == 200, r.text
    assert r.json()["created"] == 2
    db.expire_all()
    names = {c.name for c in db.query(VcContact).all()}
    assert {"홍길동", "김서연"} <= names


def test_apply_is_idempotent(logged, db):
    """같은 파일을 두 번 올려도 사람이 두 배로 늘지 않는다."""
    _upload(logged, _sheet(SAMPLE), dry_run="false")
    second = _upload(logged, _sheet(SAMPLE), dry_run="false").json()
    assert second["created"] == 0
    assert second["updated"] == 2


def test_verified_room_name_survives_upload(logged, db):
    """사람이 확인해 둔 카톡방 이름은 업로드가 덮지 않는다.

    방 제목이 실제와 어긋나면 발송이 통째로 막힌다 — 업로드로 뒤집히면 안 된다.
    """
    from app.models import VcContact

    _upload(logged, _sheet(SAMPLE), dry_run="false")
    db.expire_all()
    c = db.query(VcContact).filter_by(name="홍길동").first()
    c.kakao_room_name = "사람이 직접 고친 방 이름"
    c.room_verified = "verified"
    db.commit()

    _upload(logged, _sheet(SAMPLE), dry_run="false")
    db.expire_all()
    c = db.query(VcContact).filter_by(name="홍길동").first()
    assert c.kakao_room_name == "사람이 직접 고친 방 이름"


def test_export_cannot_be_reuploaded(logged):
    """내려받은 표를 되올리면 막는다 (활동 이력이 뻥튀기된다)."""
    _upload(logged, _sheet(SAMPLE), dry_run="false")
    exported = logged.get("/api/export/contacts.xlsx")
    assert exported.status_code == 200

    r = _upload(logged, exported.content, name="내 투자사.xlsx", dry_run="true")
    assert r.status_code == 400
    assert "내려받은 표" in r.json()["detail"]


def test_unknown_format_is_rejected(logged):
    r = logged.post("/api/import/contacts",
                    files={"file": ("메모.pdf", b"%PDF-1.4", "application/pdf")},
                    data={"dry_run": "true"})
    assert r.status_code == 400


def test_missing_header_names_the_sheets(logged):
    """헤더를 못 찾으면 어느 시트를 골라야 하는지 알려준다."""
    r = _upload(logged, _sheet([["아무", "상관", "없는"], ["값", "들", ""]], title="표지"),
                dry_run="true")
    assert r.status_code == 400
    assert "표지" in r.json()["detail"]


def test_export_contacts_is_xlsx(logged, db):
    _upload(logged, _sheet(SAMPLE), dry_run="false")
    r = logged.get("/api/export/contacts.xlsx")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/vnd.openxmlformats")

    ws = openpyxl.load_workbook(io.BytesIO(r.content)).active
    rows = list(ws.iter_rows(values_only=True))
    assert rows[0][:4] == ("그룹", "이름", "직함", "투자사")
    assert len(rows) == 3                 # 머리행 + 2명
    assert ws.freeze_panes == "A2"        # 스크롤해도 머리행이 보인다


def test_export_job_of_another_user_is_404(logged, db, users):
    """남의 발송 회차는 내려받을 수 없다."""
    from app.models import SendJob

    other = SendJob(user_id=users["u2"].id, kind="deal_intro", status="done", total=0)
    db.add(other)
    db.commit()
    assert logged.get(f"/api/export/jobs/{other.id}.xlsx").status_code == 404


def test_export_requires_login(client):
    assert client.get("/api/export/contacts.xlsx").status_code == 401
