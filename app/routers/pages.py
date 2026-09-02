"""Server-rendered HTML pages (Jinja2 SSR)."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_current_user, may_manage_team_contacts, templates
from ..models import IrCompany, SendJob, SourcingContact, User
from ..services import (cadence, contact_columns, deal_history, deal_stage,
                        mailer, ref_panel, sheet_import, sheet_owner,
                        sourcing_link)
from ..ui import MENU, base_ctx as _base_ctx
from .companies import BLOCKED_CONTRACT
from .companies import blocked_reason as company_blocked_reason
from .contacts import contact_rows

router = APIRouter(tags=["pages"])

__all__ = ["router", "MENU"]


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
def index(request: Request, db: Session = Depends(get_db),
          user: User = Depends(get_current_user), top: int = 0):
    """메인 = 대시보드. 좌측 위 브랜드를 누르면 여기로 온다.

    투자컨설턴트를 자기 화면으로 돌려보내던 줄은 여기 없다 — 이 화면 하나만
    막아 봐야 나머지 주소가 다 열려 있었다. 지금은 app/main.py 의 미들웨어가
    허용 목록에 없는 경로를 통째로 끊는다.
    """
    from ..services import dashboard as dash

    # 몇 명까지 볼지. 기본값·선택지는 서비스가 갖는다 — 여기와 /dashboard 가
    # 각자 숫자를 박아 두면 한쪽만 고쳐진다(실제로 그랬다).
    top_n = dash.clamp_top(top or dash.TOP_DEFAULT)
    ctx = _base_ctx(request, db, user, "home")
    ctx.update(dash.user_dashboard(db, user, top_n=top_n))
    ctx["top_n"] = top_n
    ctx["top_choices"] = dash.TOP_CHOICES
    return templates.TemplateResponse("dashboard.html", ctx)


@router.get("/deals", response_class=HTMLResponse)
def deals_page(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # **딜소개 불가로 표시한 기업은 아예 안 보여준다.**
    # 내용이 부족한 기업과는 다르다 — 그건 채우면 되지만, 이건 "보내면 안 되는
    # 곳" 이라 목록에 있는 것만으로 실수로 고를 수 있다.
    companies = db.execute(
        select(IrCompany)
        .where(func.coalesce(IrCompany.contract_status, "") != BLOCKED_CONTRACT)
        .order_by(IrCompany.id)
    ).scalars().all()
    # 소개 가능한 기업을 앞에 세우되, 내용이 부족한 기업도 **감추지 않는다**.
    # 감추면 "왜 내가 넣은 기업이 없지?" 가 되고 어디를 고쳐야 하는지도 알 수 없다.
    companies = sorted(companies, key=lambda c: (not c.introducible, c.name or ""))
    # 발송 대상은 **딜소개를 보내기로 한 명단에 있고, 연결이 끝난 담당자**다.
    # 문이 둘인 것이 중요하다.
    #   ① 명단  — 딜소개 명단에 올린 적 없는 풀 사람이 연결만 됐다는 이유로
    #             목록에 떴다(실데이터 142명 중 17명). 발송은 되돌릴 수 없다.
    #   ② 연결  — 명단에 있어도 방이 없으면 못 보낸다. 연결 전 명단이 섞이면
    #             보낼 방도 없는 사람에게 체크를 하게 된다.
    # 투자사로 세지 않는 명단(스타트업 리마인드 등)과 감춘 줄도 여기 오면 안 된다.
    #
    # **그 판정을 여기 적지 않는다.** 투자사 관리 현황과 이 화면이 각자 질의를
    # 들고 있어서 같은 사람을 두고 두 수가 나왔다 — 지금은 둘 다
    # `sheet_owner` 한 곳을 지나고, 대시보드의 `연결 진행 중인 명단` 도 같은
    # 명단 판정을 읽는다. 조건이 하나 붙어도 세 화면이 같이 움직인다.
    contacts = sheet_owner.recipients(db, user)
    # 세 수는 **원래 다르다** — 여기는 `명단에서 지금 보낼 수 있는 사람`,
    # 투자사 관리 현황은 `내가 맡은 사람`이다. 다른 것 자체보다 **왜 다른지
    # 화면이 말하지 않는 것**이 문제였으므로, `명단 N명 중 M명 · 명단 밖 K명`
    # 과 막힌 사유를 함께 내놓는다.
    recipient_counts = sheet_owner.recipient_counts(
        db, user, team_wide=may_manage_team_contacts(user))
    # 딜소개를 보냈는데 IR 요청·미팅으로 이어지지 않은 담당자.
    # 이들에게는 목록을 또 밀어 넣기보다 무엇을 보고 싶은지 되묻는 편이 답이 온다.
    no_reaction_ids = {
        row["id"] for row in contact_rows(db, user)
        if row["last_deal"] and not (row["ir_total"] or row["meet_total"])
    }
    # 딜 소싱 제안의 대상. 투자사 명단과 다른 표이고 **팀 공용**이다 —
    # 우리 딜을 같이 볼 사람이라 담당을 나눌 것이 아니다.
    # 방 이름이 없으면 보낼 길이 없으므로 그것부터 보이게 정렬한다.
    sourcing_contacts = db.execute(
        select(SourcingContact).order_by(SourcingContact.position, SourcingContact.id)
    ).scalars().all()
    # 갈래는 곧 문구다. 이름을 검색창에 쳐서 찾게 하면 갈래가 몇 개인지도
    # 모른 채 골라야 하므로, 누를 수 있는 필터로 내놓는다. 순서는 명단과
    # 같게 — 좌측 [딜 소싱] 탭에서 보던 순서 그대로여야 헷갈리지 않는다.
    sourcing_buckets = []
    for c in sourcing_contacts:
        if not sourcing_buckets or sourcing_buckets[-1]["name"] != c.bucket:
            match = next((b for b in sourcing_buckets if b["name"] == c.bucket), None)
            if match is None:
                sourcing_buckets.append({"name": c.bucket, "count": 0})
                match = sourcing_buckets[-1]
        else:
            match = sourcing_buckets[-1]
        match["count"] += 1
    # 담당(우리 쪽 심사역)도 거를 수 있어야 한다 — 39명을 통째로 훑는 것과
    # 내 담당 14명만 보는 것은 다른 일이다. 많은 순으로 둔다.
    counted: dict = {}
    for c in sourcing_contacts:
        who = (c.assignee_name or "").strip()
        if who:
            counted[who] = counted.get(who, 0) + 1
    sourcing_assignees = [{"name": k, "count": v} for k, v in
                          sorted(counted.items(), key=lambda kv: (-kv[1], kv[0]))]
    # 투자사 관리 현황에서 연결해 둔 방이 있으면 여기서도 '연결됨' 이어야 한다 —
    # 목록에는 '미등록' 인데 미리보기에는 방이 뜨면 어느 쪽을 믿을지 알 수 없다.
    sourcing_linked = sourcing_link.linked_rooms(db, sourcing_contacts)
    ctx = _base_ctx(request, db, user, "deal")
    # 매 회차 같은 기업을 또 보내면 받는 쪽에서는 지난번을 기억 못 한다고 읽는다.
    history = deal_history.annotate(companies, deal_history.last_sent_map(db))
    # 회차명은 **보내는 날에서 만든다.** 손으로 적으면 "8월회차" · "8월 셋째주" ·
    # "0826" 이 섞여 남아, 나중에 몇 주차에 뭘 보냈는지 찾을 때 이력이 갈라진다.
    next_send = cadence.upcoming_send_dates(db, date.today())[0]
    ctx.update({
        "companies": companies,
        "default_batch_title": cadence.batch_title(next_send),
        "history": history,
        "recent_count": sum(1 for h in history.values() if h["recent"]),
        "recent_days": deal_history.RECENT_DAYS,
        "contacts": contacts,
        "recipient_counts": recipient_counts,
        # 그룹으로 묶어 둔 사람만 추리는 필터. 투자사 관리 현황의 `그룹` 칸이
        # 거르는 그 값이라, 양쪽에서 고른 사람이 같아야 한다.
        "contact_groups": sheet_owner.group_rows(contacts),
        "empty_group": sheet_owner.EMPTY_GROUP,
        "sourcing_contacts": sourcing_contacts,
        "sourcing_buckets": sourcing_buckets,
        "sourcing_assignees": sourcing_assignees,
        "sourcing_linked": sourcing_linked,
        "no_reaction_ids": no_reaction_ids,
        # 메일 채널은 설정이 있어야 고를 수 있다.
        # 고를 수 있는데 나가지 않는 것이 제일 나쁘다.
        "mail": mailer.status(),
        "blocked_reasons": {c.id: company_blocked_reason(c)
                            for c in companies if not c.introducible},
    })
    return templates.TemplateResponse("deals.html", ctx)


# ── 명단을 보여 주는 화면 ───────────────────────────────────────────────────
#
# 화면이 **둘**이다: 투자사 관리 현황과 스타트업. 둘 다 명단별 탭 ·
# 명단이 정한 표 · 달마다 늘어나는 칸 · 감춘 줄 · 인라인 수정 · 필터 · 수정창을
# 그대로 쓴다.
#
# **그래서 그리는 코드도 화면(`contacts.html`)도 하나다.** 새 화면에 표를 다시
# 짜면 딸려 오는 것들이 한 벌씩 더 생기고, 그중 하나만 고쳐지는 날 "화면은
# 뜨는데 고칠 수가 없다" 가 된다 — 이 저장소가 반복해 당한 부류다(투자사
# 117명·123명, 좌측 메뉴 목록과 라우터 목록, 참고 자료 질의가 화면마다 갈린 일).
#
# 화면끼리 **정말로 다른 것만** 아래 값으로 둔다. 값이 아니라 조건문으로 두면
# 화면이 하나 더 늘 때 또 심어야 한다.


@dataclass(frozen=True)
class ListPage:
    """명단 화면 하나. 두 화면의 **차이가 여기 전부** 적혀 있다."""

    key: str            # 좌측 메뉴 key — 제목이 여기서 나온다(`ui.menu_label`)
    page: str           # 주소 조각. `RefSheet.page` · `Layout.page` 와 같은 값
    # 이 화면이 **투자사를 다루는가.** 딜소개 발송·방 연결·명함 업로드는 투자사
    # 이야기라 스타트업 화면에 서면 안 된다 — 거기 있는 사람은 딜을 받는 쪽이
    # 아니라 우리가 챙기는 쪽이다. 눌러도 아무 일이 없는 단추가 더 나쁘다.
    investors: bool
    row_label: str      # 세는 것의 이름. 투자사 화면은 사람, 스타트업은 기업이다
    # 아무 명단도 안 골랐을 때의 표. 명단이 하나도 없는 화면에서만 쓰인다 —
    # 없으면 스타트업 화면이 투자사 명함 표를 그린다.
    default_layout: str

    @property
    def href(self) -> str:
        return f"/{self.page}"


CONTACTS_PAGE = ListPage(key="vc", page=contact_columns.PAGE_CONTACTS,
                         investors=True, row_label="담당자",
                         default_layout=contact_columns.DEFAULT)
STARTUP_PAGE = ListPage(key="startup", page=contact_columns.PAGE_STARTUP,
                        investors=False, row_label="기업",
                        default_layout=contact_columns.STARTUP)


def list_page(
    request: Request,
    db: Session,
    user: User,
    page: ListPage,
    *,
    sheet: str = "",
    ref: str = "",
    contact: int = 0,
    months: str = "",
    hidden: int = 0,
    msg: str = "",
):
    """명단 화면을 그린다 — 투자사 관리 현황과 스타트업 화면이 같이 쓴다.

    명단(시트)별로 탭을 나눈다. 333명을 한 표에 쏟으면 시트를 쓰던 사람이
    자기 명단을 못 찾는다 — 시트가 나뉘어 있던 구분을 그대로 살린다.

    **명단마다 표가 다르다.** 어느 명단이 어떤 칸을 쓰는지는 화면이 아니라
    그 명단의 설정(`SheetOwner.layout`)이 정한다 — 탭 이름을 화면에 심으면
    성격이 다른 명단이 하나 더 들어올 때마다 또 심어야 한다.

    **어느 명단이 이 화면에 서는지도 같은 값이 정한다**(`Layout.page`). 그래서
    명단을 옮기는 데 이름을 적을 자리가 없다 — 배치를 바꾸면 화면이 따라온다.
    """
    # 관리자는 팀 전체를 본다 — 누가 어떤 투자사를 맡고 있는지 알아야 한다.
    # 여기 뜬 줄은 그대로 고칠 수도 있어야 한다. **그래서 판정을 여기 적지 않고**
    # 라우터(`_owned`)와 같은 함수를 읽는다 — 화면이 `role == "admin"` 을 따로
    # 들고 있던 동안, 뜬 줄을 눌러 고치면 404 가 났다.
    # 발송 대상 고르기는 여전히 본인 담당분만이다(/deals 참고).
    team_wide = may_manage_team_contacts(user)
    # 이 화면 하나만 감춘 것까지 받아 온다 — 감추기는 지우기가 아니라서
    # 그 명단 탭에서는 그대로 보여야 하고, 되돌릴 자리도 여기에 있어야 한다.
    all_rows = contact_rows(db, user, team_wide=team_wide, include_hidden=True)
    # 담당은 명단(시트) 단위다 — "내 이름으로 된 탭만 내 담당 투자사".
    # 탭은 **감춘 것까지** 세어야 한다(감추기는 지우기가 아니라, 그 명단 탭에서는
    # 그대로 보여야 한다). 누구를 가져올지는 여기서 정하지 않는다 — 위의
    # `all_rows` 와 딜 제안 관리가 지나는 그 판정을 그대로 지난다.
    contacts = sheet_owner.managed(db, user, team_wide=team_wide,
                                   include_hidden=True)
    # **이 화면에 사는 명단만** 탭으로 세운다. 무엇이 여기 사는지는 그 명단의
    # 배치가 정한다(`SheetOwner.layout` → `Layout.page`) — 거르는 조건은
    # `sheet_owner.sheet_rows` 한 곳에 있어서 두 화면이 같이 움직인다.
    tabs = sheet_owner.sheet_rows(db, contacts, page=page.page)

    # 아무 것도 고르지 않았으면 **내가 담당인 명단**을 먼저 연다.
    # 전체(333명)를 먼저 보여주면 매번 자기 명단을 다시 골라야 한다.
    # `sheet=all` 은 일부러 전체를 본다는 뜻이다.
    #
    # 투자사로 세지 않기로 한 명단은 **기본으로 열지 않는다.** 투자사 관리
    # 현황을 열자마자 투자사가 아닌 명단이 떠 있으면 그것이 내 담당 투자사인
    # 줄 읽는다. 눌러서 들어가는 길은 그대로 있다.
    #
    # **투자사를 다루지 않는 화면에는 `전체` 가 없다.** 거기 `전체` 는 투자사
    # 전체를 뜻하는데(아래 `total_count`), 그 화면의 명단은 투자사로 세지 않아
    # 언제나 0명이 뜬다 — 명단이 사라진 것처럼 보인다. 대신 늘 탭 하나를 연다.
    if sheet == "all" and page.investors:
        selected = ""
    elif any(t["key"] == sheet for t in tabs):
        selected = sheet
    else:
        mine = [t for t in tabs if t["owner_id"] == user.id]
        # 감추지 않은 내 명단이 먼저. 내 명단이 전부 감춘 것뿐이면 그거라도
        # 연다 — 담당이 있는데 빈 화면이 뜨면 무엇을 봐야 할지 알 수 없다.
        selected = next((t["key"] for t in mine if not t["is_hidden"]),
                        next((t["key"] for t in mine), ""))
        # 투자사 화면에서는 담당이 없으면 `전체` 로 떨어진다(지금까지 그랬다).
        # 그쪽에는 없는 화면은 **아무 탭이라도** 연다 — 명단이 버젓이 있는데
        # 빈 표가 뜨면 옮겨 오다 만 것으로 읽힌다.
        if not selected and not page.investors and tabs:
            selected = tabs[0]["key"]
    if selected:
        rows = [r for r in all_rows if selected in r["sheets"]]
    elif page.investors:
        # `전체` 는 **투자사 전체**다. 투자사로 세지 않기로 한 명단을 여기 섞으면
        # 위의 인원 수가 그만큼 부풀어, 대시보드와 다른 수가 나온다.
        hidden_sheets = sheet_owner.hidden_labels(db)
        rows = [r for r in all_rows
                if not r["is_hidden"]
                and any(s not in hidden_sheets for s in r["sheets"])]
    else:
        # 이 화면에 명단이 하나도 없다. 남의 화면 줄을 끌어오지 않는다 —
        # 여기 뜬 줄은 여기서 고칠 수 있어야 하는데, 탭이 없으면 어느 명단의
        # 줄인지도 화면에 안 적힌다.
        rows = []

    # 감춘 줄은 기본으로 빼고, **몇 줄을 감췄는지는 적는다.** 그냥 안 보이면
    # 원본 시트에서 그랬듯 "없는 기업" 으로 읽힌다(`?hidden=1` 이 되돌리는 길).
    hidden_rows = [r for r in rows if r["is_hidden"]]
    if not hidden:
        rows = [r for r in rows if not r["is_hidden"]]

    # 이 명단이 쓰는 표 배치. 정해 두지 않은 명단은 지금까지의 투자사 명함 표다.
    # 아무 명단도 안 골랐으면 **이 화면의 기본 표**다 — 그냥 `DEFAULT` 로 두면
    # 명단이 하나도 없는 스타트업 화면이 투자사 명함 표를 그린다.
    layout = contact_columns.layout_of(
        sheet_owner.layout_of(db, selected) if selected else page.default_layout)
    # 달마다 늘어나는 칸이 있는지는 **명단이 정한다** — 그 명단에 `ContactColumn`
    # 줄이 있느냐다. 배치로 가르면 안 된다: 표에 그 칸을 안 세우는 배치(투자사
    # 명함)를 쓰면서 달마다의 기록은 가진 명단이 있고, 배치로 걸러 버리면 그
    # 기록이 **화면 어디에도 안 뜬다**(지워지지 않았는데 사라진 것처럼 보인다).
    # 칸이 없는 명단에서는 이 호출이 빈 목록이라 값이 드는 데가 없다
    # (`monthly_columns.plan` 이 본뜰 칸이 없으면 아무것도 안 만든다).
    all_months = contact_columns.month_columns(db, selected) if selected else []
    shown_months, folded_months = contact_columns.split_months(
        all_months, show_all=(months == "all"))

    # 참고 시트 — 스크립트·가이드처럼 매번 구글 시트를 열어 보던 자료.
    # 지울 수 있게 두었으므로 살아 있는 것만 가져온다. 질의는
    # `services/ref_panel.py` 한 곳에 있다(투자컨설턴트·스타트업 화면이
    # 같은 패널을 쓴다) — 화면마다 적어 두면 조건 하나가 조용히 갈린다.
    ref_ctx = ref_panel.panel_ctx(db, page.page, ref)

    stages = Counter(r["connect_stage"] for r in rows)
    # 깔때기는 **지금 탭에 보이는 사람들** 기준이다. 탭이 곧 명단이라,
    # 전체 기준으로 세면 내 명단을 보고 있는데 숫자만 남의 것이 섞인다.
    stage_funnel = deal_stage.funnel(
        {r["id"]: r["deal_stage"] for r in rows})
    ctx = _base_ctx(request, db, user, page.key)
    ctx.update({
        # 화면끼리 다른 것 전부. 화면(`contacts.html`)이 이 값 하나만 읽으면
        # 조건을 화면에 흩뿌리지 않아도 된다.
        "page": page,
        "rows": rows,
        "team_wide": team_wide,
        "tabs": tabs,
        "selected_sheet": selected,
        "members": ([{"id": u.id, "name": u.name} for u in
                     db.execute(select(User).order_by(User.id)).scalars().all()]
                    if team_wide else []),
        # 풀에서 고른 사람을 어느 명단으로 할당할지 — 내 명단만 고를 수 있다.
        "my_sheets": [t for t in tabs if t["owner_id"] == user.id],
        # 줄 하나를 넘길 곳 — **탭을 그대로 쓰지 않는다.** 탭은 지금 보이는
        # 사람들로 세어 만들어서 팀원에게는 자기 명단만 뜬다. 정작 넘겨 줄
        # 상대의 명단이 목록에 없으면 이관 자체를 할 수가 없다.
        "transfer_targets": sheet_owner.transfer_targets(db, page=page.page),
        # 풀 탭에서는 골라서 내 명단으로 할당할 수 있다.
        "pool_view": any(t["key"] == selected and t["kind"] == "pool" for t in tabs),
        # `전체` 탭에 적히는 수. **투자사로 세는 사람만** — 여기가 부풀면
        # 대시보드와 다른 수가 나온다(예전에 117명 · 123명으로 갈렸다).
        # `전체` 탭에 적히는 수도 **딜 제안 관리와 같은 판정**을 지난다 —
        # 여기서 조건을 손으로 다시 적어 두면 두 화면이 또 갈린다.
        "total_count": len(sheet_owner.managed(db, user, team_wide=team_wide)),
        # ── 명단이 정한 표 배치 ──
        "layout": layout,
        "table_columns": contact_columns.table_columns(layout, shown_months),
        "panel_columns": contact_columns.panel_columns(layout, all_months),
        "month_columns": shown_months,
        # **접었다는 것을 사람이 알아야 한다** — 그냥 안 보이면 지워진 줄 안다.
        "folded_months": folded_months,
        "show_all_months": months == "all",
        # 감춘 줄 — 몇 줄인지와, 되돌리러 갈 자리.
        "hidden_count": len(hidden_rows),
        "show_hidden": bool(hidden),
        "msg": msg,
        "funnel": stage_funnel,
        # 대시보드의 '내 투자사 선호'에서 눌러 오면 그 사람 상세를 바로 연다 —
        # 무엇을 좋아하는지(선호 분야·라운드) 보려고 누른 것이다.
        "open_contact": contact or 0,
        **ref_ctx,
        # [수정] 창의 `연결 상태` 보기. **말을 화면에 적지 않는다** — 임포트가
        # 정한 라벨을 그대로 넘긴다. 화면에 다시 적으면 필터 값·대시보드 타일과
        # 갈려서, 골라 저장해도 어느 쪽에도 안 걸린다.
        "connect_stages": [
            {"key": key, "label": label, "count": stages.get(key, 0)}
            for key, label in sheet_import.CONNECT_LABELS.items()
        ],
        # 같은 이유로 `상태` 도 말을 실어 준다. 이 값은 **발송 대상 판정이 읽는
        # 값**이라(`sheet_owner.can_send_to`), 화면이 이름을 따로 적어 두면
        # 판정과 화면이 서로 다른 것을 가리키게 된다 — 딜 제안 관리의 안내가
        # 없는 상태를 찾아 헤매게 만드는 그 부류다.
        "contact_statuses": [
            {"key": key, "label": label}
            for key, label in sheet_owner.STATUS_LABELS.items()
        ],
    })
    return templates.TemplateResponse("contacts.html", ctx)


@router.get("/contacts", response_class=HTMLResponse)
def contacts_page(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    sheet: str = "",
    ref: str = "",
    contact: int = 0,
    months: str = "",
    hidden: int = 0,
    msg: str = "",
):
    """내 투자사 (FEATURE_SPEC §3). 표는 SSR, 필터는 브라우저에서 즉시 반응."""
    return list_page(request, db, user, CONTACTS_PAGE, sheet=sheet, ref=ref,
                     contact=contact, months=months, hidden=hidden, msg=msg)


@router.get("/jobs/{job_id}", response_class=HTMLResponse)
def job_page(
    job_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    job = db.get(SendJob, job_id)
    # 관리자는 팀 현황에서 넘어와 **누구에게 보냈는지** 조회한다 — 본인 것이
    # 아니어도 읽기는 되어야 한다. 재시도·취소 같은 조작은 API 쪽에서
    # 여전히 본인 것만 허용한다(jobs.py 의 _job_or_404).
    can_view = job is not None and (job.user_id == user.id or user.role == "admin")
    verify = can_view and job.kind == "verify_room"
    ctx = _base_ctx(request, db, user, "vc" if verify else "deal")
    ctx.update({"job_id": job_id, "job_exists": can_view, "verify": verify,
                "readonly": can_view and job.user_id != user.id})
    return templates.TemplateResponse("progress.html", ctx)


@router.get("/{placeholder}", response_class=HTMLResponse)
def placeholder_page(
    placeholder: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """아직 만들지 않은 메뉴의 안내 화면."""
    item = next((m for m in MENU if m["href"] == f"/{placeholder}"), None)
    if item is None:
        # Let unknown paths 404 naturally via a minimal response.
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Not Found")
    ctx = _base_ctx(request, db, user, item["key"])
    ctx.update({"title": item["label"]})
    return templates.TemplateResponse("placeholder.html", ctx)
