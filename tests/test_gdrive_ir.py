"""구글 드라이브 IR 수신 확인(#155) — `services/gdrive_ir.py`.

드라이브는 가짜(`FakeDrive` · `FakeSession`)로 대신한다. 폴더 id · 키는 전부 지어낸 값이다.
"""
from __future__ import annotations

import json
import logging
import unicodedata
from datetime import datetime, timedelta, timezone
from urllib.parse import unquote

import pytest
from sqlalchemy import select

from .conftest import DEMO_PASSWORD

ROOT = "rootFolderAAAA0001"
ROOT2 = "rootFolderBBBB0002"
SUB = "subFolderCCCC0003"
KST = timezone(timedelta(hours=9))
T0 = datetime(2026, 11, 4, 10, 0, tzinfo=KST)


# ── 가짜 드라이브 ────────────────────────────────────────────────────────────

def _f(fid, name, created, modified=None, parent=ROOT):
    return {"id": fid, "name": name, "mimeType": "application/pdf",
            "createdTime": created, "modifiedTime": modified or created,
            "parents": [parent], "webViewLink": f"https://drive.google.com/file/d/{fid}/view"}


class FakeDrive:
    """`gdrive_ir.Drive` 의 두 길(`folder` · `children`)만. 질의 규칙도 같게 흉내 낸다."""

    def __init__(self, files=(), folders=None):
        from app.services import gdrive_ir

        self.g = gdrive_ir
        self.files = list(files)
        self.folders = dict(folders or {ROOT: {"name": "IR 폴더", "parent": None}})
        self.calls = []
        self.fail = ""
        self.incomplete = False

    def folder(self, fid):
        self.calls.append(("folder", fid))
        if self.fail:
            raise self.g.DriveError(self.fail)
        if fid not in self.folders:
            raise self.g.DriveError(self.g.ERR_NOT_FOUND)
        return {"id": fid, "name": self.folders[fid]["name"], "mimeType": self.g.FOLDER_MIME}

    def children(self, parents, *, since=None, files_only=False):
        self.calls.append(("children", tuple(parents), since, files_only))
        if self.fail:
            raise self.g.DriveError(self.fail)

        def fresh(item):
            if since is None:
                return True
            stamps = [item.get("createdTime"), item.get("modifiedTime")]
            return any(s and datetime.fromisoformat(s.replace("Z", "+00:00")) > since for s in stamps)

        out = []
        if not files_only:
            for fid, f in self.folders.items():
                item = {"id": fid, "name": f["name"], "mimeType": self.g.FOLDER_MIME,
                        "createdTime": f.get("created", "2026-01-01T00:00:00Z"),
                        "modifiedTime": f.get("created", "2026-01-01T00:00:00Z"),
                        "parents": [f["parent"]] if f["parent"] else []}
                if f["parent"] in parents and fresh(item):
                    out.append(item)
        out += [f for f in self.files if set(f["parents"]) & set(parents) and fresh(f)]
        return out


@pytest.fixture()
def admin(db, users):
    users["u1"].role = "admin"
    db.commit()
    return users["u1"]


@pytest.fixture()
def configured(monkeypatch, tmp_path):
    """서버 설정 — 키 파일(내용 없는 가짜)과 폴더 id(가짜)."""
    key = tmp_path / "gdrive-sa.json"
    key.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("DEALFLOW_GDRIVE_SA_FILE", str(key))
    monkeypatch.setenv("DEALFLOW_GDRIVE_FOLDER_ID", ROOT)
    return key


def _company(db, name, **kw):
    from app.models import IrCompany

    row = IrCompany(name=name, **kw)
    db.add(row)
    db.commit()
    return row


def _deal(db, name, **kw):
    from app.models import SeriesACompany

    row = SeriesACompany(name=name, **kw)
    db.add(row)
    db.commit()
    return row


def _turn_on(db, admin, **kw):
    from app.services import gdrive_ir

    vals = dict(enabled=True, interval_min=30, subfolders=True, backfill=True, user_id=admin.id)
    vals.update(kw)
    return gdrive_ir.save_settings(db, **vals)


def _cell(db, row):
    from app.models import CustomColumn, CustomColumnValue

    col = db.execute(select(CustomColumn).where(CustomColumn.name == "IR 자료 수신")).scalars().first()
    if col is None:
        return None
    return db.execute(select(CustomColumnValue.value).where(
        CustomColumnValue.column_id == col.id,
        CustomColumnValue.row_table == row.__tablename__,
        CustomColumnValue.row_id == row.id)).scalar_one_or_none()


def _state(db):
    from app.services import gdrive_ir

    db.expire_all()
    return gdrive_ir.load_state(db)


# ── 이름 맞추기 ──────────────────────────────────────────────────────────────

def _find(db, text):
    from app.services import gdrive_ir

    return sorted(c.label for c in gdrive_ir.Index.build(db).find(text))


def test_name_matching_ignores_corp_marks_prefixes_tails_and_case(db):
    _company(db, "(주)샘플가")
    _company(db, "Sample Bio")
    _company(db, "샘플 나라")
    for name in ("TalkFile_샘플가_IR_2026.11.04_v3.pdf",
                 "IR-샘플가-261102.pdf",
                 "★샘플가 IR 투자용_2026.11.03 (2).pdf",
                 "[주식회사 샘플가] 투자유치 검토용 서면 질의 답변서.docx",
                 "샘플가IR자료.pdf",
                 "샘플가회사소개서_최종.pptx",
                 "㈜샘플가 deck FINAL.pdf"):
        assert _find(db, name) == ["(주)샘플가"], name
    assert _find(db, "SAMPLEBIO_Deck_rev12.pdf") == ["Sample Bio"]
    assert _find(db, "sample-bio IR.pdf") == ["Sample Bio"]
    assert _find(db, "샘플나라 IR.pdf") == ["샘플 나라"]
    assert _find(db, "샘플 나라_IR.pdf") == ["샘플 나라"]


def test_name_matching_reads_decomposed_hangul(db):
    _company(db, "샘플가")
    nfd = unicodedata.normalize("NFD", "샘플가_IR자료.pdf")
    assert nfd != "샘플가_IR자료.pdf"
    assert _find(db, nfd) == ["샘플가"]


def test_name_matching_never_matches_inside_a_word(db):
    _company(db, "가나")
    assert _find(db, "가나다라전자_IR.pdf") == []
    assert _find(db, "가나 IR.pdf") == ["가나"]


def test_longer_name_wins_over_the_name_inside_it(db):
    _company(db, "샘플")
    _company(db, "샘플나라")
    assert _find(db, "샘플나라_IR.pdf") == ["샘플나라"]
    assert _find(db, "샘플 나라_IR.pdf") == ["샘플나라"]
    assert _find(db, "샘플_IR.pdf") == ["샘플"]


def test_tagged_names_that_collide_are_several(db):
    _company(db, "다라텍")
    _company(db, "다라텍 [딜소개 불가/폐업함]")
    _company(db, "마바텍 [딜소개 불가/폐업위기]")
    assert _find(db, "다라텍_IR.pdf") == ["다라텍", "다라텍 [딜소개 불가/폐업함]"]
    # 꼬리표가 붙은 기업도 하나뿐이면 그 기업이다.
    assert _find(db, "마바텍 IR 2026.pdf") == ["마바텍 [딜소개 불가/폐업위기]"]


def test_two_companies_in_one_name_are_several(db):
    _company(db, "샘플가")
    _company(db, "마바텍")
    assert _find(db, "샘플가_마바텍_비교.pdf") == ["마바텍", "샘플가"]


def test_noise_words_and_one_letter_names_are_not_companies(db):
    _company(db, "IR")
    _company(db, "가")
    _company(db, "2026")
    assert _find(db, "가 IR 2026.pdf") == []


def test_series_a_companies_count_once(db):
    from app.services import gdrive_ir

    ir = _company(db, "샘플가")
    _deal(db, "샘플가")                                  # 같은 이름 — IR 기업이다
    linked = _deal(db, "샘플가바이오", ir_company_id=ir.id)  # 이은 줄 — IR 기업이다
    first = _deal(db, "사아로보")
    second = _deal(db, "사아로보", ir_file_name="사아로보_IR.pdf")
    index = gdrive_ir.Index.build(db)
    found = index.find("샘플가_IR.pdf")
    assert [c.row for c in found] == [ir]
    assert [c.row for c in index.find("샘플가바이오 deck.pdf")] == [ir]
    found = index.find("사아로보 IR.pdf")
    assert len(found) == 1 and found[0].row is second and found[0].row is not first
    assert linked.id


def test_folder_ids_accept_commas_spaces_and_urls():
    from app.services import gdrive_ir

    ids, bad = gdrive_ir.folder_ids(
        f"{ROOT}, https://drive.google.com/drive/folders/{ROOT2}?usp=sharing  bad'id {ROOT}")
    assert ids == (ROOT, ROOT2)
    assert bad == 1


# ── 설정이 없으면 꺼짐 ────────────────────────────────────────────────────────

def test_without_server_settings_it_stays_off(db, admin):
    from app.services import gdrive_ir

    _turn_on(db, admin)
    drive = FakeDrive([_f("file000000001", "샘플가.pdf", "2026-11-04T00:00:00Z")])
    assert gdrive_ir.tick(db, now=T0, drive=drive) == {"status": "not_configured"}
    assert drive.calls == []
    assert gdrive_ir.panel(db)["status"].startswith("설정 없음")


def test_switch_off_by_default(db, admin, configured):
    from app.services import gdrive_ir

    drive = FakeDrive([_f("file000000001", "샘플가.pdf", "2026-11-04T00:00:00Z")])
    assert gdrive_ir.settings(db).enabled is False
    assert gdrive_ir.tick(db, now=T0, drive=drive) == {"status": "off"}
    assert drive.calls == []


def test_missing_key_file_is_reported_without_the_path(db, admin, monkeypatch, tmp_path):
    from app.services import gdrive_ir

    monkeypatch.setenv("DEALFLOW_GDRIVE_SA_FILE", str(tmp_path / "nowhere.json"))
    monkeypatch.setenv("DEALFLOW_GDRIVE_FOLDER_ID", ROOT)
    panel = gdrive_ir.panel(db)
    assert panel["ready"] is False and panel["key_ok"] is False
    assert "nowhere.json" not in json.dumps(panel, ensure_ascii=False)


# ── 적기 ────────────────────────────────────────────────────────────────────

def test_writes_receipt_into_the_column_not_the_ir_file_field(db, admin, configured):
    from app.models import CustomColumn, EditLog
    from app.routers.companies import last_editors
    from app.services import edit_log, gdrive_ir

    edit_log.install()   # 앱을 띄우면 거는 세션 이벤트(`create_app`)
    company = _company(db, "(주)샘플가")
    _turn_on(db, admin)
    # 한국 시각으로는 11/04 01:30 — 날짜는 한국 날짜다.
    drive = FakeDrive([_f("file000000001", "TalkFile_샘플가_IR.pdf", "2026-11-03T16:30:00Z",
                          modified="2026-10-01T00:00:00Z")])
    result = gdrive_ir.tick(db, now=T0, drive=drive)
    assert result["status"] == "ok" and result["written"] == 1
    db.expire_all()
    assert _cell(db, company) == "2026/11/04 수신완료 (드라이브: TalkFile_샘플가_IR.pdf)"
    assert company.ir_file_name in (None, "")
    col = db.execute(select(CustomColumn).where(CustomColumn.name == "IR 자료 수신")).scalars().one()
    assert (col.target, col.kind, col.after_key) == ("companies", "memo", "IR 자료")
    # 수정 기록 — 주체는 `자동`.
    logs = db.execute(select(EditLog).where(EditLog.table_name == "ir_companies")).scalars().all()
    assert len(logs) == 1 and logs[0].method == edit_log.AUTO_METHOD
    assert "추가 칸 · IR 자료 수신" in logs[0].changes_json
    shown = [r for r in edit_log.recent(db) if r["row_label"] == "(주)샘플가"]
    assert shown and shown[0]["actor"] == "자동"
    assert last_editors(db, [company]) == {company.id: "자동"}
    assert _state(db)["written"] == 1


def test_uses_an_existing_column_by_name(db, admin, configured):
    from app.models import CustomColumn
    from app.services import custom_columns, gdrive_ir

    col = custom_columns.add(db, "companies", "IR 자료 수신", "memo", admin.id)
    db.commit()
    company = _company(db, "샘플가")
    _turn_on(db, admin)
    gdrive_ir.tick(db, now=T0, drive=FakeDrive([_f("file000000001", "샘플가.pdf",
                                                     "2026-11-04T00:00:00Z")]))
    assert db.execute(select(CustomColumn)).scalars().all() == [col]
    assert _cell(db, company).startswith("2026/11/04 수신완료")


def test_only_new_or_changed_files_are_read_and_handled(db, admin, configured):
    from app.services import gdrive_ir

    a = _company(db, "샘플가")
    b = _company(db, "마바텍")
    _turn_on(db, admin)
    drive = FakeDrive([_f("file000000001", "샘플가.pdf", "2026-11-04T00:00:00Z")])
    gdrive_ir.tick(db, now=T0, drive=drive)
    assert [c[0] for c in drive.calls] == ["folder", "children"]
    assert drive.calls[1][2] is None                   # 처음은 전체
    # 간격이 안 찼으면 아무것도 안 묻는다.
    drive.calls.clear()
    assert gdrive_ir.tick(db, now=T0 + timedelta(minutes=10), drive=drive)["status"] == "not_due"
    assert drive.calls == []
    # 다음 회차 — 바뀐 것만, 기준 시각을 실어 한 번 묻는다.
    drive.files.append(_f("file000000002", "마바텍 IR.pdf", "2026-11-04T01:20:00Z",
                          modified="2026-09-01T00:00:00Z"))
    result = gdrive_ir.tick(db, now=T0 + timedelta(minutes=30), drive=drive)
    assert [c[0] for c in drive.calls] == ["children"]
    since = drive.calls[0][2]
    assert since == T0.astimezone(timezone.utc) - gdrive_ir.OVERLAP
    # 첫 파일은 다시 안 오고(시각 필터) 왔어도 본 파일이라 거른다. 새 파일은 올린 시각
    # (`createdTime`)으로 잡힌다 — 수정 시각은 PC 의 옛 시각이다.
    assert (result["written"], result["skipped"], result["review"]) == (1, 0, 0)
    assert _cell(db, b).startswith("2026/11/04 수신완료 (드라이브: 마바텍 IR.pdf)")
    assert _cell(db, a).startswith("2026/11/04")
    # 같은 파일이 겹쳐 와도(기준 시각을 앞당겨 묻는다) 두 번 세지 않는다.
    again = gdrive_ir.tick(db, now=T0 + timedelta(minutes=60), drive=drive)
    assert (again["written"], again["skipped"]) == (0, 0)
    assert _state(db)["written"] == 2


def test_a_cell_with_a_value_is_never_overwritten(db, admin, configured):
    from app.services import custom_columns, gdrive_ir

    company = _company(db, "샘플가")
    other = _company(db, "마바텍")
    col = custom_columns.add(db, "companies", "IR 자료 수신", "memo", admin.id)
    db.flush()
    custom_columns.write(db, company, col, "10/30 메일로 받음", admin.id)
    db.commit()
    _turn_on(db, admin)
    drive = FakeDrive([_f("file000000001", "샘플가_IR.pdf", "2026-11-04T00:00:00Z"),
                       _f("file000000002", "마바텍_IR_v1.pdf", "2026-11-03T00:00:00Z")])
    result = gdrive_ir.tick(db, now=T0, drive=drive)
    assert (result["written"], result["skipped"]) == (1, 1)
    assert _cell(db, company) == "10/30 메일로 받음"
    # 같은 기업의 새 판이 와도 첫 수신일은 그대로 — 건너뛰고 기록만 남긴다.
    drive.files.append(_f("file000000003", "마바텍_IR_v2.pdf", "2026-11-04T01:00:00Z"))
    later = gdrive_ir.tick(db, now=T0 + timedelta(minutes=30), drive=drive)
    assert (later["written"], later["skipped"]) == (0, 1)
    assert _cell(db, other) == "2026/11/03 수신완료 (드라이브: 마바텍_IR_v1.pdf)"
    recent = gdrive_ir.panel(db)["recent"]
    assert recent[0]["name"] == "마바텍_IR_v2.pdf"
    assert recent[0]["result"] == "건너뜀 (이미 값 있음)"


def test_unclear_files_go_to_the_review_list(db, admin, configured):
    from app.services import gdrive_ir

    _company(db, "다라텍")
    _company(db, "다라텍 [딜소개 불가/폐업함]")
    _turn_on(db, admin)
    drive = FakeDrive([_f("file000000001", "다라텍_IR.pdf", "2026-11-04T00:00:00Z"),
                       _f("file000000002", "모르는회사 투자제안서.pdf", "2026-11-04T00:10:00Z")])
    result = gdrive_ir.tick(db, now=T0, drive=drive)
    assert (result["written"], result["review"]) == (0, 2)
    review = {r["name"]: r for r in gdrive_ir.panel(db)["review"]}
    assert review["다라텍_IR.pdf"]["candidates"] == ["다라텍", "다라텍 [딜소개 불가/폐업함]"]
    assert review["다라텍_IR.pdf"]["link"].startswith("https://drive.google.com/")
    assert review["모르는회사 투자제안서.pdf"]["why"] == "기업명을 찾지 못함"
    # 그 기업이 IR 기업 현황에 들어오면 — 파일이 그대로여도 다음 회차에 적힌다.
    newcomer = _company(db, "모르는회사")
    again = gdrive_ir.tick(db, now=T0 + timedelta(minutes=30), drive=drive)
    assert again["written"] == 1
    assert _cell(db, newcomer) == "2026/11/04 수신완료 (드라이브: 모르는회사 투자제안서.pdf)"
    assert [r["name"] for r in gdrive_ir.panel(db)["review"]] == ["다라텍_IR.pdf"]


def test_subfolders_and_company_named_folders(db, admin, configured):
    from app.services import gdrive_ir

    company = _company(db, "샘플가")
    moved = _company(db, "마바텍")
    _turn_on(db, admin)
    drive = FakeDrive([_f("file000000001", "IR.pdf", "2026-11-04T00:00:00Z", parent=SUB)],
                      folders={ROOT: {"name": "IR 폴더", "parent": None},
                               SUB: {"name": "샘플가", "parent": ROOT}})
    result = gdrive_ir.tick(db, now=T0, drive=drive)
    assert result["written"] == 1
    assert _cell(db, company).endswith("(드라이브: IR.pdf)")
    assert gdrive_ir.panel(db)["recent"][0]["via"] == "폴더 이름"
    # 다른 곳에서 옮겨 온 폴더 — 폴더도 안 파일도 시각이 옛날이다. 새로 보인 폴더(만든
    # 시각이 기준 뒤)는 그 안을 통째로 읽는다.
    new_sub = "subFolderDDDD0004"
    drive.folders[new_sub] = {"name": "옮긴 폴더", "parent": ROOT, "created": "2026-11-04T01:25:00Z"}
    drive.files.append(_f("file000000002", "마바텍_IR.pdf", "2025-01-01T00:00:00Z", parent=new_sub))
    later = gdrive_ir.tick(db, now=T0 + timedelta(minutes=30), drive=drive)
    assert later["written"] == 1
    assert _cell(db, moved).startswith("2025/01/01 수신완료")


def test_daily_full_check_catches_files_the_time_filter_missed(db, admin, configured):
    from app.services import gdrive_ir

    company = _company(db, "샘플가")
    _turn_on(db, admin)
    drive = FakeDrive([])
    gdrive_ir.tick(db, now=T0, drive=drive)
    # 다른 폴더에서 옮겨 온 파일 — 만든 · 고친 시각이 다 옛날이라 바뀐 것만 묻는 회차에 안 잡힌다.
    drive.files.append(_f("file000000001", "샘플가_IR.pdf", "2025-05-05T00:00:00Z"))
    assert gdrive_ir.tick(db, now=T0 + timedelta(minutes=30), drive=drive)["written"] == 0
    full = gdrive_ir.tick(db, now=T0 + timedelta(hours=24, minutes=30), drive=drive)
    assert full["full"] is True and full["written"] == 1
    assert _cell(db, company).startswith("2025/05/05")
    # 드라이브에서 지운 파일은 전체 대조 때 상태에서 걷는다.
    drive.files.clear()
    gdrive_ir.tick(db, now=T0 + timedelta(hours=49), drive=drive)
    assert _state(db)["files"] == {}


def test_backfill_off_only_marks_existing_files_as_seen(db, admin, configured):
    from app.services import gdrive_ir

    company = _company(db, "샘플가")
    _turn_on(db, admin, backfill=False)
    drive = FakeDrive([_f("file000000001", "샘플가_IR.pdf", "2026-10-01T00:00:00Z")])
    first = gdrive_ir.tick(db, now=T0, drive=drive)
    assert (first["written"], first["baseline"]) == (0, 1)
    assert _cell(db, company) is None
    drive.files.append(_f("file000000002", "샘플가_IR_v2.pdf", "2026-11-04T01:10:00Z"))
    assert gdrive_ir.tick(db, now=T0 + timedelta(minutes=30), drive=drive)["written"] == 1
    assert _cell(db, company).endswith("(드라이브: 샘플가_IR_v2.pdf)")


def test_hidden_column_stops_writing_and_says_why(db, admin, configured):
    from app.services import custom_columns, gdrive_ir

    col = custom_columns.add(db, "companies", "IR 자료 수신", "memo", admin.id)
    custom_columns.set_hidden(col, True)
    db.commit()
    company = _company(db, "샘플가")
    _turn_on(db, admin)
    drive = FakeDrive([_f("file000000001", "샘플가_IR.pdf", "2026-11-04T00:00:00Z")])
    result = gdrive_ir.tick(db, now=T0, drive=drive)
    assert result == {"status": "failed", "error": gdrive_ir.ERR_COLUMN_HIDDEN}
    custom_columns.set_hidden(col, False)
    db.commit()
    # 다시 보이게 하면 다음 회차에 전체를 다시 읽어 적는다.
    again = gdrive_ir.tick(db, now=T0 + timedelta(minutes=30), drive=drive)
    assert again["written"] == 1 and _cell(db, company)


# ── 실패해도 멈추지 않는다 ────────────────────────────────────────────────────

def test_drive_failure_is_recorded_and_retried_next_round(db, admin, configured):
    from app.services import gdrive_ir

    company = _company(db, "샘플가")
    _turn_on(db, admin)
    drive = FakeDrive([_f("file000000001", "샘플가_IR.pdf", "2026-11-04T00:00:00Z")])
    drive.fail = gdrive_ir.ERR_QUOTA
    assert gdrive_ir.tick(db, now=T0, drive=drive) == {"status": "failed",
                                                       "error": gdrive_ir.ERR_QUOTA}
    panel = gdrive_ir.panel(db)
    assert panel["error"] == gdrive_ir.ERR_QUOTA and panel["last_run"]
    # 실패한 회차 뒤에도 간격을 지킨다(5분마다 두드리지 않는다).
    assert gdrive_ir.tick(db, now=T0 + timedelta(minutes=5), drive=drive)["status"] == "not_due"
    drive.fail = ""
    assert gdrive_ir.tick(db, now=T0 + timedelta(minutes=30), drive=drive)["written"] == 1
    assert _cell(db, company)
    assert gdrive_ir.panel(db)["error"] == ""


def test_unexpected_error_is_recorded_and_waits_for_the_interval(db, admin, configured,
                                                                 monkeypatch, caplog):
    from app.services import gdrive_ir

    company = _company(db, "샘플가")
    _turn_on(db, admin)
    drive = FakeDrive([_f("file000000001", "샘플가_IR.pdf", "2026-11-04T00:00:00Z")])
    real = gdrive_ir.Index.build

    def broken(cls, _db):
        raise RuntimeError("뜻밖의 오류")

    monkeypatch.setattr(gdrive_ir.Index, "build", classmethod(broken))
    with caplog.at_level(logging.ERROR):
        result = gdrive_ir.tick(db, now=T0, drive=drive)
    assert result == {"status": "failed", "error": gdrive_ir.ERR_INTERNAL}
    assert gdrive_ir.tick(db, now=T0 + timedelta(minutes=5), drive=drive)["status"] == "not_due"
    monkeypatch.setattr(gdrive_ir.Index, "build", real)
    assert gdrive_ir.tick(db, now=T0 + timedelta(minutes=30), drive=drive)["written"] == 1
    assert _cell(db, company)


def test_unshared_folder_is_shown_per_folder(db, admin, configured, monkeypatch):
    from app.services import gdrive_ir

    monkeypatch.setenv("DEALFLOW_GDRIVE_FOLDER_ID", f"{ROOT},{ROOT2}")
    company = _company(db, "샘플가")
    _turn_on(db, admin)
    drive = FakeDrive([_f("file000000001", "샘플가_IR.pdf", "2026-11-04T00:00:00Z")])
    assert gdrive_ir.tick(db, now=T0, drive=drive)["written"] == 1
    roots = gdrive_ir.panel(db)["roots"]
    assert [(r["name"], r["ok"]) for r in roots] == [("IR 폴더", True), ("(이름 모름)", False)]
    assert roots[1]["error"] == gdrive_ir.ERR_NOT_FOUND
    assert _cell(db, company)


class FakeResponse:
    def __init__(self, status, body):
        self.status_code = status
        self._body = body
        self.text = json.dumps(body)

    def json(self):
        return self._body


class FakeSession:
    def __init__(self, replies):
        self.replies = list(replies)
        self.requests = []

    def get(self, url, params=None, timeout=None):
        self.requests.append((url, dict(params or {}), timeout))
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


def test_drive_client_asks_only_for_changes_and_needed_fields():
    from app.services import gdrive_ir

    session = FakeSession([FakeResponse(200, {"files": [{"id": "a"}], "nextPageToken": "p2"}),
                           FakeResponse(200, {"files": [{"id": "b"}]})])
    drive = gdrive_ir.Drive(session=session)
    since = datetime(2026, 11, 4, 0, 0, tzinfo=timezone.utc)
    assert [f["id"] for f in drive.children([ROOT, SUB], since=since)] == ["a", "b"]
    url, params, timeout = session.requests[0]
    assert url == gdrive_ir.FILES_URL and timeout == gdrive_ir.TIMEOUT_SEC
    assert params["q"] == (f"('{ROOT}' in parents or '{SUB}' in parents) and trashed = false"
                           " and (modifiedTime > '2026-11-04T00:00:00'"
                           " or createdTime > '2026-11-04T00:00:00')")
    assert params["fields"] == ("nextPageToken,incompleteSearch,"
                                "files(id,name,mimeType,createdTime,modifiedTime,parents,webViewLink)")
    assert params["supportsAllDrives"] == params["includeItemsFromAllDrives"] == "true"
    assert session.requests[1][1]["pageToken"] == "p2"
    # 폴더가 많으면 20개씩 나눠 묻는다.
    many = [f"folder{n:010d}" for n in range(25)]
    session = FakeSession([FakeResponse(200, {"files": []}), FakeResponse(200, {"files": []})])
    gdrive_ir.Drive(session=session).children(many, files_only=True)
    assert len(session.requests) == 2
    assert "mimeType != 'application/vnd.google-apps.folder'" in session.requests[0][1]["q"]


def test_query_refuses_odd_folder_ids():
    from app.services import gdrive_ir

    with pytest.raises(ValueError):
        gdrive_ir.query(["x' or name contains 'y"])


@pytest.mark.parametrize("reply, reason", [
    ("403-rate", "ERR_QUOTA"), ("403", "ERR_DENIED"), ("404", "ERR_NOT_FOUND"),
    ("401", "ERR_AUTH"), ("500", "ERR_SERVER"), ("403-off", "ERR_API_OFF"), ("net", "ERR_NET"),
])
def test_drive_client_failures_become_fixed_reasons(reply, reason):
    import requests

    from app.services import gdrive_ir

    replies = {
        "403-rate": FakeResponse(403, {"error": {"errors": [{"reason": "userRateLimitExceeded"}]}}),
        "403": FakeResponse(403, {"error": {"errors": [{"reason": "forbidden"}]}}),
        "404": FakeResponse(404, {"error": {"message": f"File not found: {ROOT}"}}),
        "401": FakeResponse(401, {}),
        "500": FakeResponse(500, {}),
        "403-off": FakeResponse(403, {"error": {"errors": [{"reason": "accessNotConfigured"}]}}),
        "net": requests.ConnectionError("connection reset by peer"),
    }
    drive = gdrive_ir.Drive(session=FakeSession([replies[reply]]))
    with pytest.raises(gdrive_ir.DriveError) as caught:
        drive.folder(ROOT)
    assert caught.value.public == getattr(gdrive_ir, reason)
    assert ROOT not in caught.value.public
    # 안쪽 예외(그 글에 무엇이 들었든)는 끊어서 버린다 — 로그의 추적에도 안 실린다.
    err = caught.value
    assert err.__cause__ is None and (err.__context__ is None or err.__suppress_context__)


def test_scheduler_round_survives_a_broken_tick(db, monkeypatch, caplog):
    """실 한 바퀴 — 드라이브 쪽이 넘어져도 예외가 밖으로 안 나간다(실이 살아 있다)."""
    from app.services import automation_runner, gdrive_ir

    def boom(*_a, **_k):
        raise RuntimeError("뜻밖의 오류")

    monkeypatch.setattr(gdrive_ir, "tick", boom)
    with caplog.at_level(logging.ERROR):
        automation_runner.run_round()
    assert "구글 드라이브 IR 수신 확인을 하다 실패했습니다" in caplog.text


# ── 키 내용은 어디에도 안 남는다 ──────────────────────────────────────────────

def _fake_key(tmp_path):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    pem = rsa.generate_private_key(public_exponent=65537, key_size=2048).private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption()).decode()
    info = {"type": "service_account", "project_id": "example-project",
            "private_key_id": "0123456789abcdef0123456789abcdef01234567",
            "private_key": pem,
            "client_email": "gdrive-test@example.com",
            "client_id": "000000000000000000000",
            "token_uri": "https://oauth2.googleapis.com/token"}
    path = tmp_path / "gdrive-sa.json"
    path.write_text(json.dumps(info), encoding="utf-8")
    return path, info


def test_key_contents_never_reach_logs_state_or_screen(client, db, admin, monkeypatch,
                                                       tmp_path, caplog):
    import requests

    from app.services import gdrive_ir

    path, info = _fake_key(tmp_path)
    monkeypatch.setenv("DEALFLOW_GDRIVE_SA_FILE", str(path))
    monkeypatch.setenv("DEALFLOW_GDRIVE_FOLDER_ID", ROOT)
    _turn_on(db, admin)
    asked = []

    def token_refused(self, method, url, **kwargs):
        asked.append(url)
        resp = requests.Response()
        resp.status_code = 400
        resp._content = json.dumps({"error": "invalid_grant",
                                    "error_description": "Invalid JWT Signature."}).encode()
        resp.headers["Content-Type"] = "application/json"
        return resp

    monkeypatch.setattr(requests.Session, "request", token_refused)
    gdrive_ir._CACHED.clear()
    with caplog.at_level(logging.DEBUG):
        result = gdrive_ir.tick(db, now=T0)
    assert asked and asked[0] == info["token_uri"]      # 키로 토큰을 받으려다 거절당했다
    assert result == {"status": "failed", "error": gdrive_ir.ERR_AUTH}
    body = info["private_key"].split("\n")[1]
    secrets = [body, info["private_key_id"], "BEGIN PRIVATE KEY", str(path)]
    stored = json.dumps(_state(db), ensure_ascii=False)
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    page = client.get("/team").text
    for secret in secrets:
        assert secret not in caplog.text
        assert secret not in stored
        assert secret not in page
    assert gdrive_ir.ERR_AUTH in page


def test_broken_key_file_is_a_fixed_reason(db, admin, configured):
    from app.services import gdrive_ir

    configured.write_text('{"private_key": "-----BEGIN PRIVATE KEY-----\\nnot-a-key"}',
                          encoding="utf-8")
    _turn_on(db, admin)
    gdrive_ir._CACHED.clear()
    assert gdrive_ir.tick(db, now=T0) == {"status": "failed", "error": gdrive_ir.ERR_KEY}


# ── 관리자 화면 ──────────────────────────────────────────────────────────────

def _login(client, phone):
    client.post("/login", data={"phone": phone, "password": DEMO_PASSWORD})


def test_team_page_renders_the_panel_without_settings(client, db, admin):
    _login(client, "01000000001")
    page = client.get("/team")
    assert page.status_code == 200
    text = page.text
    assert 'data-testid="gdrive-ir-panel"' in text
    assert "구글 드라이브 IR 수신 확인" in text
    assert "설정 없음" in text and "DEALFLOW_GDRIVE_SA_FILE" in text


def test_team_page_shows_status_review_and_recent(client, db, admin, configured):
    from app.services import gdrive_ir

    _company(db, "다라텍")
    _company(db, "다라텍 [딜소개 불가/폐업함]")
    _company(db, "샘플가")
    _turn_on(db, admin)
    gdrive_ir.tick(db, now=T0, drive=FakeDrive([
        _f("file000000001", "다라텍_IR.pdf", "2026-11-04T00:00:00Z"),
        _f("file000000002", "샘플가_IR.pdf", "2026-11-04T00:00:00Z")]))
    _login(client, "01000000001")
    text = client.get("/team").text
    assert "켜짐 — 30분마다 확인" in text
    assert "접근 성공" in text and "IR 폴더" in text
    assert 'data-testid="gdrive-ir-written">1<' in text
    assert 'data-testid="gdrive-ir-review"' in text
    assert "https://drive.google.com/file/d/file000000001/view" in text
    assert "다라텍 [딜소개 불가/폐업함]" in text
    assert 'data-testid="gdrive-ir-recent"' in text
    assert ROOT not in text and str(configured) not in text


def test_admin_saves_the_switch_and_members_cannot(client, db, admin):
    from app.models import EditLog
    from app.services import gdrive_ir

    _login(client, "01000000002")
    refused = client.post("/team/gdrive-ir", data={"enabled": "on"}, follow_redirects=False)
    assert refused.status_code in (303, 403)
    assert gdrive_ir.settings(db).enabled is False
    client.post("/logout")
    _login(client, "01000000001")
    answer = client.post("/team/gdrive-ir", data={"enabled": "on", "interval_min": "45",
                                                  "subfolders": "on"}, follow_redirects=False)
    assert answer.status_code == 303 and answer.headers["location"].endswith("#gdrive-ir")
    db.expire_all()
    saved = gdrive_ir.settings(db)
    assert (saved.enabled, saved.interval_min, saved.subfolders, saved.backfill,
            saved.actor_id) == (True, 45, True, False, admin.id)
    assert db.execute(select(EditLog).where(EditLog.table_name == "automations")).scalars().first()
    bad = client.post("/team/gdrive-ir", data={"enabled": "on", "interval_min": "3"},
                      follow_redirects=False)
    assert "저장하지 않았습니다" in unquote(bad.headers["location"])
    db.expire_all()
    assert gdrive_ir.settings(db).interval_min == 45
