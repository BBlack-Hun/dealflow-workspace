"""투자사 관리 현황 업로드 · 표 엑셀 내려받기.

**업로드**
팀원마다 자기 '투자사 관리 현황' 시트를 따로 관리한다. 그동안은 내가 구글 시트를
직접 읽어 임포트했지만, 팀원이 자기 시트를 스스로 올릴 수 있어야 운영이 돈다.
올린 파일은 기존 임포트 파서(sheet_import.parse_sheet_a)가 그대로 읽는다 —
구글 시트든 내려받은 엑셀이든 같은 표이기 때문이다.

두 단계로 나눈다. **미리보기(dry_run)** 로 무엇이 생기고 무엇이 바뀌는지 먼저 보고,
그 다음에 반영한다. 담당자 명단은 발송 대상이라 잘못 덮으면 그대로 오발송이 된다.

업로드한 사람의 담당분으로 붙는다. 시트에 '담당자' 컬럼이 있으면 그 이름으로 계정을
찾고, 못 찾으면 **버리지 않고** 올린 사람에게 붙인 뒤 리포트에 남긴다.

**내려받기**
화면에서 보는 표를 그대로 엑셀로 준다. 필터·정렬은 엑셀에서 하도록 머리행을 고정하고
자동 필터를 걸어 둔다.
"""
from __future__ import annotations

from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_current_user, may_manage_team_contacts
from ..models import IrCompany, SendItem, SendJob, User, VcContact
from ..services import sheet_import, spreadsheet as sp
from .contacts import contact_rows

# 경로를 /api/import, /api/export 로 따로 둔다.
# /api/contacts/export.xlsx 로 두면 기존 /api/contacts/{contact_id} 가 먼저 잡아
# "export.xlsx 는 정수가 아니다" 로 422 가 난다 — 등록 순서로 푸는 대신 경로를 가른다.
router = APIRouter(tags=["data"])


# --- 업로드 -----------------------------------------------------------------

def _read_upload(file: UploadFile, sheet: Optional[str]) -> tuple:
    data = file.file.read()
    # 내려받은 표를 그대로 다시 올리면 활동 이력이 뻥튀기된다 — 내보내기의
    # 'IR 요청(누적)' 류 컬럼을 임포트 파서가 월별 활동으로 읽기 때문이다.
    # (127명짜리 내보내기를 되올려 활동 635건이 새로 잡히는 것을 확인했다)
    if sp.is_export_file(file.filename or "", data):
        raise HTTPException(
            status_code=400,
            detail="이 파일은 dealflow 에서 내려받은 표입니다. "
                   "업로드에는 원본 '투자사 관리 현황' 시트를 올려주세요.",
        )
    try:
        rows = sp.read_rows(file.filename or "", data, sheet or None)
        names = sp.sheet_names(file.filename or "", data)
    except sp.SpreadsheetError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if not rows:
        raise HTTPException(status_code=400, detail="시트에 내용이 없습니다.")
    return rows, names


@router.post("/api/import/contacts")
def import_contacts(
    file: UploadFile = File(...),
    sheet: str = Form(""),
    year: int = Form(0),
    dry_run: bool = Form(True),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """투자사 관리 현황 업로드. 기본은 미리보기 — 반영하려면 dry_run=false."""
    rows, names = _read_upload(file, sheet)

    try:
        parsed = sheet_import.parse_sheet_a(rows, year or date.today().year)
    except ValueError as exc:
        # 헤더를 못 찾는 경우가 대부분이다 — 어느 시트를 골라야 하는지 알려준다.
        detail = str(exc)
        if names:
            detail += f" · 이 파일의 시트: {', '.join(names)}"
        raise HTTPException(status_code=400, detail=detail)

    report = sheet_import.apply_sheet_a(
        db, parsed, user_id=user.id, dry_run=dry_run,
        source_label=(sheet or file.filename or "업로드"),
    )
    if dry_run:
        db.rollback()   # 미리보기가 DB 를 건드리고 끝나면 안 된다

    return {
        "dry_run": dry_run,
        "sheets": names,
        "sheet_used": sheet or (names[0] if names else ""),
        "header_row": parsed.header_row,
        "parsed_contacts": len(parsed.contacts),
        "created": report.created,
        "updated": report.updated,
        "activities_created": report.activities_created,
        "activities_existing": report.activities_existing,
        "notes": report.notes,
        "skipped": [{"row": s.row_no, "reason": s.reason, "preview": s.preview}
                    for s in report.skipped[:50]],
        "skipped_total": len(report.skipped),
        "summary": report.as_text("업로드"),
    }


@router.post("/api/import/contacts/sheets")
def list_upload_sheets(file: UploadFile = File(...)):
    """파일을 올리기 전에 어떤 시트가 들어 있는지 보여준다."""
    data = file.file.read()
    try:
        return {"sheets": sp.sheet_names(file.filename or "", data)}
    except sp.SpreadsheetError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# --- 내려받기 ---------------------------------------------------------------

def _xlsx(filename: str, sheet_title: str, headers, rows) -> Response:
    try:
        content = sp.write_xlsx(sheet_title, headers, rows)
    except sp.SpreadsheetError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return Response(content=content, media_type=sp.XLSX_MEDIA_TYPE,
                    headers=sp.content_disposition(filename))


# 시트에 있는 값은 **하나도 빠뜨리지 않는다.** 엑셀로 내보낸 뒤 원본 시트와
# 나란히 놓고 대조하는 일이 잦은데, 빠진 칸이 있으면 그때 알게 된다.
CONTACT_HEADERS = [
    "담당 팀원", "담당자", "연결 단계", "그룹", "이름", "직함", "투자사", "부서",
    "채널", "카톡방", "방 확인", "초대", "관심도",
    "라운드 규모", "선호 단계", "선호 분야",
    "휴대폰", "전자 메일 주소", "근무처 전화", "근무처 팩스", "근무지 주소", "명함 등록일",
    "마지막 딜소개", "회차 메모", "IR 요청(최근)", "미팅(최근)",
    "IR 요청(누적)", "미팅(누적)", "상태", "메모",
]


# 업로드용 샘플 양식.
#
# 실제 명단 시트와 **같은 모양**이어야 한다: 머리글이 2행이고, 1행에는 월
# 라벨이 온다(`8월` 이 딜소개/IR/미팅 3열 위에 걸친다). 파서가 위치가 아니라
# 머리글 이름과 그 위아래 문맥으로 컬럼을 찾기 때문에, 이름이 다르면 값이
# 통째로 버려진다 — 샘플이 실제로 통과하는 양식이어야 하는 이유다.
#
# 채워 넣은 사람은 전부 가짜다.
SAMPLE_MONTH_ROW = [
    "", "", "", "", "", "", "", "", "", "", "", "", "",
    "8월", "", "",
]
SAMPLE_HEADER_ROW = [
    "NO", "그룹", "이름", "직책", "투자사명", "부서", "담당자",
    "휴대폰", "전자 메일 주소", "근무처 전화", "근무지 주소",
    "선호 투자분야", "라운드 규모",
    "1차 딜소개", "IR 요청", "미팅",
]
SAMPLE_ROWS = [
    [1, "A그룹", "홍길동", "심사역", "가나벤처스", "투자1본부", "김담당",
     "010-0000-0001", "hong@example.com", "02-000-0001", "서울 강남구 000",
     "AI, 헬스케어", "10~30억",
     "8/13(목) 샘플가, 샘플나", "8/19(수) 2번", ""],
    [2, "A그룹", "김서연", "팀장", "다라인베스트", "", "김담당",
     "010-0000-0002", "kim@example.com", "", "",
     "소재부품, 로봇", "30~50억",
     "8/13(목) 핵심 딜 8개사", "", "8/26(수) 20분"],
    [3, "", "박지훈", "대표", "마바캐피탈", "", "이담당",
     "010-0000-0003", "", "", "",
     "", "", "", "", ""],
]
# 칸이 좁으면 머리글이 잘려서 무엇을 적는 칸인지 안 보인다.
SAMPLE_WIDTHS = [5, 9, 10, 9, 18, 12, 9, 15, 22, 15, 22, 18, 13, 24, 18, 18]


@router.get("/api/sample/contacts.xlsx")
def sample_contacts(user: User = Depends(get_current_user)):
    """투자사 관리 현황 업로드용 **빈 양식**.

    내보내기(`/api/export/contacts.xlsx`)와 다른 파일이다. 내보낸 파일에는
    되올리기 방지 표식이 붙어 있어 그대로 올리면 막힌다 — 새로 명단을 만드는
    사람에게는 올릴 수 있는 양식이 따로 있어야 한다.
    """
    try:
        content = sp.write_plain_xlsx(
            "투자사 관리 현황",
            [SAMPLE_MONTH_ROW, SAMPLE_HEADER_ROW, *SAMPLE_ROWS],
            head_row=2, widths=SAMPLE_WIDTHS)
    except sp.SpreadsheetError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return Response(content=content, media_type=sp.XLSX_MEDIA_TYPE,
                    headers=sp.content_disposition("투자사 관리 현황_업로드양식.xlsx"))


@router.get("/api/export/contacts.xlsx")
def export_contacts(db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    """내 투자사 표 → 엑셀. 화면과 같은 순서·같은 값."""
    def channel(r):
        marks = []
        if r["channel_kakao"]:
            marks.append("카톡")
        if r["channel_email"]:
            marks.append("메일")
        return "/".join(marks)

    rows = [
        [r["owner"], r["assignee"], r["connect_label"], r["group_name"],
         r["name"], r["title"], r["firm"], r["department"], channel(r),
         r["room_name"], r["room_label"], r["invited_status"], r["interest_level"],
         r["round_size"], ", ".join(r["stages"]), ", ".join(r["sectors"]),
         r["phone"], r["email"], r["office_phone"], r["office_fax"],
         r["address"], r["card_registered_at"],
         r["last_deal"] or "", r["last_deal_note"],
         r["ir_recent"], r["meet_recent"], r["ir_total"], r["meet_total"],
         r["status_label"], r["memo"]]
        # 관리자는 팀 전체를 내려받는다 — 화면과 같은 범위여야 헷갈리지 않는다.
        # **그래서 판정도 화면과 같은 것을 읽는다**(`may_manage_team_contacts`).
        # 여기 `role == "admin"` 을 따로 적어 두면 범위가 갈릴 자리가 하나 더 는다.
        for r in contact_rows(db, user, team_wide=may_manage_team_contacts(user))
    ]
    today = date.today().isoformat()
    return _xlsx(f"내 투자사_{today}.xlsx", "내 투자사", CONTACT_HEADERS, rows)


def _eok(value):
    """저장값(백만원) → 억. 엑셀에서 계산할 수 있게 **숫자로** 둔다."""
    return None if value is None else round(value / 100, 1)


COMPANY_HEADERS = [
    "기업명", "분야(대)", "분야(소)", "기업구분", "한줄소개", "소개가능",
    # 화면과 같은 단위로 내보낸다. 표는 억인데 엑셀만 백만이면, 두 개를 나란히
    # 놓고 보는 사람에게는 같은 값이 100배 차이로 보인다.
    "최근매출(억)", "누적투자(억)", "희망투자(억)", "Pre Value(억)",
    "경쟁력", "계약", "계약월", "탑딜", "투자현황", "요약상태", "IR 링크",
]


@router.get("/api/export/companies.xlsx")
def export_companies(db: Session = Depends(get_db),
                     user: User = Depends(get_current_user)):
    """IR 기업현황 → 엑셀. 소개 가능 여부를 함께 내보내 어디를 채워야 할지 보이게 한다."""
    companies = db.execute(select(IrCompany).order_by(IrCompany.name)).scalars().all()
    rows = [
        [c.name, c.sector_major or "", c.sector_minor or "", c.series or "",
         c.one_liner or "", "O" if c.introducible else "",
         _eok(c.revenue_recent), _eok(c.funding_total),
         _eok(c.raise_target), _eok(c.pre_value),
         c.competitiveness or "", c.contract_status or "", c.contract_month or "",
         "★" if c.is_top_deal else "", c.funding_status or "",
         c.summary_status or "", c.ir_drive_url or ""]
        for c in companies
    ]
    today = date.today().isoformat()
    return _xlsx(f"IR 기업현황_{today}.xlsx", "IR 기업현황", COMPANY_HEADERS, rows)


from ..services.pipeline import REQUEST_STATUS  # noqa: E402

REACTION_HEADERS = ["구분", "날짜", "담당자", "직함", "투자사", "기업", "상태"]


@router.get("/api/export/reactions.xlsx")
def export_reactions(db: Session = Depends(get_db),
                     user: User = Depends(get_current_user)):
    """대시보드의 반응 다섯 가지를 **날짜와 함께** 한 장으로.

    화면은 숫자만 보여준다. 숫자를 보고 나면 "그게 누구였지" 가 이어지는데,
    그때마다 다섯 화면을 돌아다녀야 했다.
    """
    from ..models import IrRequest, Meeting, VcContact
    from ..services.pipeline import MEETING_KINDS, OUTCOMES

    contacts = {
        c.id: c for c in db.execute(
            select(VcContact).where(VcContact.user_id == user.id)).scalars().all()
    }

    def who(contact_id):
        c = contacts.get(contact_id)
        return [c.name, c.title or "", c.firm or ""] if c else ["-", "", ""]

    rows = []
    for r in db.execute(select(IrRequest).where(
            IrRequest.user_id == user.id).order_by(IrRequest.requested_at)).scalars():
        rows.append(["IR 요청 투자사", r.requested_at or "", *who(r.contact_id),
                     r.company_name or "", REQUEST_STATUS.get(r.status, r.status)])
        rows.append(["IR 요청받은 기업", r.requested_at or "", *who(r.contact_id),
                     r.company_name or "", REQUEST_STATUS.get(r.status, r.status)])

    for m in db.execute(select(Meeting).where(
            Meeting.user_id == user.id).order_by(Meeting.scheduled_at)).scalars():
        label = ("IR 미팅완료 투자사" if m.status == "done"
                 else "IR 미팅 요청 투자사")
        rows.append([label, m.scheduled_at or "", *who(m.contact_id),
                     m.company_name or "", MEETING_KINDS.get(m.kind, m.kind)])
        # 끝난 미팅 중 아직 결과를 안 물어본 곳 — 전화할 대상이다.
        if m.status == "done" and not m.followup_done:
            rows.append(["IR 미팅완료 리마인드 TEL 투자사",
                         m.followup_due or m.scheduled_at or "", *who(m.contact_id),
                         m.company_name or "",
                         OUTCOMES.get(m.outcome or "", "결과 미정")])

    today = date.today().isoformat()
    return _xlsx(f"반응 현황_{today}.xlsx", "반응 현황", REACTION_HEADERS, rows)


JOB_HEADERS = ["담당자", "직함", "투자사", "카톡방", "상태", "발송시각", "실패사유", "문구"]


@router.get("/api/export/jobs/{job_id}.xlsx")
def export_job(job_id: int, db: Session = Depends(get_db),
               user: User = Depends(get_current_user)):
    """발송 회차 결과 → 엑셀. 어디로 무엇이 나갔는지 그대로 남긴다."""
    job = db.get(SendJob, job_id)
    if job is None or job.user_id != user.id:
        raise HTTPException(status_code=404, detail="발송 회차를 찾을 수 없습니다")

    items = db.execute(
        select(SendItem).where(SendItem.job_id == job.id).order_by(SendItem.id)
    ).scalars().all()
    contacts = {
        c.id: c for c in db.execute(
            select(VcContact).where(
                VcContact.id.in_([i.contact_id for i in items] or [0]))
        ).scalars().all()
    }
    rows = []
    for item in items:
        c = contacts.get(item.contact_id)
        rows.append([
            c.name if c else "", (c.title or "") if c else "", (c.firm or "") if c else "",
            item.room_name or "", item.status, item.sent_at or "",
            item.error or "", item.message or "",
        ])
    return _xlsx(f"발송결과_{job.id}.xlsx", f"발송 {job.id}", JOB_HEADERS, rows)
