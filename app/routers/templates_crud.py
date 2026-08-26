"""문구 템플릿 관리 — 팀이 만들어 둔 문구 중에서 **각자 하나를 고른다**.

딜소개 문구는 매번 같지 않다(첫 연락/재연락, 리마인드, 미팅 요청, 연말 인사 …).
그래서 같은 종류(kind)라도 문구를 여러 개 둔다.

여러 개 중 무엇을 쓸지는 **이 화면에서 한 번** 고른다. 회차마다 고르게 하면
다음 회차에 또 골라야 하고, 한 번이라도 잊으면 아무거나 나간다.

팀 기본 템플릿(user_id=NULL)은 모두에게 보이고, 본인이 만든 것은 본인에게만 보인다.
**고치는 것과 고르는 것은 다른 권한이다** — 팀 기본은 관리자만 고치지만,
고르는 것은 각자 한다(관리자도 제 선택을 가진다).
"""
from __future__ import annotations

from typing import List, Optional

from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_current_user, templates as jinja
from ..models import MessageTemplate, User
from ..services import template_pick
from ..ui import base_ctx
# 합쳐진 문구는 발송 화면이 쓰는 그 길로 만든다 — 여기서 다시 합치면 두 벌이
# 되고, 두 벌은 반드시 어긋난다.
from . import deals as deals_view

router = APIRouter(tags=["templates"])

# 화면에 보여줄 종류와 설명. 문구가 어디에 쓰이는지 알아야 제대로 쓴다.
KINDS = [
    ("opening_first", "인사말 — 첫 연락", "처음 딜소개를 보내는 담당자에게"),
    ("opening_re", "인사말 — 재연락", "이미 보낸 적 있는 담당자에게"),
    ("closing_day1", "안내문 — 딜소개", "기업 목록 위에 오는 안내 문구"),
    ("closing_remind", "안내문 — 리마인드", "발송 후 6~7일 뒤 후속"),
    ("closing_meeting", "안내문 — 미팅 요청", "발송 후 11~14일 뒤 후속"),
    ("meeting_review", "문구만 — 미팅 후기", "미팅 뒤 열흘쯤 지나 결과를 물을 때"),
    ("ask_preference", "문구만 — 선호 분야 묻기", "반응이 없는 담당자에게 기업 목록 없이 이 문구만"),
    ("ir_delivery", "IR 자료 전달", "자료를 먼저 보낸 뒤 뒤따라 보내는 문구"),
    # 갈래마다 하나씩이다 — 호칭·전달 개수·찾는 범위가 다르다.
    # 문구 이름에 갈래를 적어 두면 그 갈래에 쓰인다(`sourcing_msg.body_for`).
    ("sourcing_intro", "딜 소싱 제안", "갈래(시리즈 A 이상 · 투자사 대표 · 개인 참여 …)마다 하나씩"),
    ("connect_call", "연결 — 전화 응대", "카톡방 연결 전 첫 통화"),
    ("connect_sms", "연결 — 부재중 문자", "전화를 못 받으셨을 때 보내는 문자"),
    ("connect_reinvite", "연결 — 방 나가신 분", "카톡방을 나간 담당자에게 다시 연락할 때"),
    ("startup_info", "기업 — 정보 기재 요청",
     "스타트업에 회사명·매출·투자금 등을 적어 달라고 할 때"),
    ("startup_sms", "기업 리마인드 — 문자", "관리 중인 스타트업에 매월 보내는 문자"),
    ("startup_call", "기업 리마인드 — 전화", "문자 뒤 통화할 때"),
    ("mail_subject", "홍보메일 제목", "메일 발송에 쓸 제목 후보"),
]
KIND_LABELS = {k: label for k, label, _ in KINDS}
KIND_DESCS = {k: desc for k, _, desc in KINDS}

# 문구에 쓸 수 있는 치환 변수 (화면 안내용)
VARIABLES = [
    ("{기업목록}", "1번 기업 샘플애그 (IR 자료 전달에서만)"),
    ("{담당자명}", "김영주"),
    ("{직함}", "심사역님 (없으면 자동으로 '님')"),
    ("{투자사}", "가나벤처스"),
    ("{개수}", "선택한 기업 수"),
]


def _visible(db: Session, user: User) -> List[MessageTemplate]:
    """내가 쓸 수 있는 템플릿 = 팀 기본 + 내 것."""
    return db.execute(
        select(MessageTemplate)
        .where(or_(MessageTemplate.user_id.is_(None),
                   MessageTemplate.user_id == user.id))
        .order_by(MessageTemplate.kind, MessageTemplate.id)
    ).scalars().all()


def _editable(t: MessageTemplate, user: User) -> bool:
    """팀 기본(user_id=NULL)은 관리자만, 개인 것은 주인만 고칠 수 있다."""
    if t.user_id is None:
        return user.role == "admin"
    return t.user_id == user.id


def _snippet(body: str, limit: int = 40) -> str:
    """고를 때 보여줄 첫 줄. 이름이 비슷하면 이름만으로는 구별이 안 된다."""
    head = (body or "").strip().splitlines()
    first = head[0].strip() if head else ""
    return first if len(first) <= limit else first[:limit] + "…"


def _slots(kind: str, of_kind: List[MessageTemplate]) -> List[str]:
    """이 종류 안에서 문구들이 서 있는 **자리** 목록.

    보통은 자리가 하나다 — 그 종류의 문구가 전부 한 자리를 놓고 겨룬다.
    딜 소싱만 갈래마다 자리가 갈린다(갈래가 다르면 아예 다른 문구다).
    화면에 뜨는 순서를 문구 목록 순서와 맞춘다 — 순서가 어긋나면 어느
    선택기가 어느 문구를 가리키는지 눈으로 못 따라간다.
    """
    if kind not in template_pick.NAME_IS_A_BUCKET:
        return [""]
    # 문구가 하나도 없어도 자리 하나는 남긴다 — 그래야 "지금은 무엇이
    # 나가는가"(코드에 적힌 뼈대)를 볼 수 있고, 새로 만들 자리도 생긴다.
    return list(dict.fromkeys(template_pick.variant_of(kind, t.name)
                              for t in of_kind)) or [""]


def _slot_view(db: Session, user: User, kind: str, variant: str,
               of_slot: List[MessageTemplate], mode: str) -> dict:
    """한 자리의 화면 재료 — 고를 것들 · 지금 고른 것 · 합쳐진 미리보기.

    고를 것이 하나뿐이면 선택기를 만들지 않는다. 고를 것이 없는데 라디오
    버튼만 늘어서면 무엇을 해야 하는 화면인지 흐려진다. 대신 그때는 "기본
    문구를 복사해 내 문구 만들기" 를 띄운다 — 빈 칸에서 처음부터 쓰라고 하면
    아무도 쓰지 않는다.
    """
    options = template_pick.candidates(db, user.id, kind, variant)
    picked = template_pick.chosen_id(db, user.id, kind, variant)
    mine = [o for o in options if o.user_id == user.id]
    team = [o for o in options if o.user_id is None]
    return {
        "variant": variant,
        "chosen_id": picked,
        # 팀 기본이 여럿인데 아직 아무것도 고르지 않으면 코드에 적힌 기본
        # 문구가 나간다. 그 사실이 화면에 보여야 고를 이유가 생긴다.
        "undecided": template_pick.pick(db, user.id, kind, variant) is None,
        "options": [{
            "id": o.id,
            "name": o.name or "이름 없는 문구",
            # 사용자가 실제로 고르는 것은 이 둘 중 하나다 — 팀이 정해 둔
            # 문구를 쓸 것인가, 내가 손본 문구를 쓸 것인가.
            "owner": "내 문구" if o.user_id == user.id else "기본 문구",
            "snippet": _snippet(o.body),
            "selected": o.id == picked,
        } for o in options],
        # 내 문구가 아직 없을 때만 복사를 권한다. 두 벌을 만들어 두면 어느
        # 것이 나가는지 또 헷갈린다.
        "copy_from": team[0].id if (team and not mine) else None,
        "rows": [{"t": t, "editable": _editable(t, user),
                  "chosen": t.id == picked} for t in of_slot],
        # 실제로 나가는 문구 — 인사말과 본문을 합친 전문.
        "preview": (deals_view.sample_message(db, user, mode, bucket=variant)
                    if mode else ""),
        # 인사말이 붙는지는 발송 쪽 판단을 그대로 쓴다. 여기서 따로 정하면
        # 보여 준 문구와 나가는 문구가 인사말 한 덩어리만큼 어긋난다.
        "with_opening": bool(mode) and deals_view.opening_is_included(mode),
        # 기업을 고르는 방식은 미리보기에 '0개사' 가 뜬다 — 아직 아무 기업도
        # 고르지 않았기 때문이다. 그렇다고 가짜 기업을 지어 넣으면 그 숫자가
        # 진짜인 줄 안다. 무엇이 채워지는지 한 줄로 적어 둔다.
        "with_companies": mode in deals_view.MODES_WITH_COMPANIES,
    }


def _section(db: Session, user: User, rows: List[MessageTemplate],
             kind: str, title: str, tab: str, mode: str) -> dict:
    """화면의 한 구간. 딜 제안 관리의 탭 하나 또는 '그 밖의 문구' 한 종류."""
    label, desc = KIND_LABELS.get(kind, kind), KIND_DESCS.get(kind, "")
    # 키 이름을 'items' 로 두면 Jinja 에서 dict.items 메서드가 잡힌다(실제로 500 발생).
    of_kind = [t for t in rows if t.kind == kind]
    by_slot = {}
    for t in of_kind:
        by_slot.setdefault(template_pick.variant_of(kind, t.name), []).append(t)
    slots = [_slot_view(db, user, kind, variant, by_slot.get(variant, []), mode)
             for variant in _slots(kind, of_kind)]
    return {"kind": kind, "title": title, "tab": tab, "mode": mode,
            "label": label, "desc": desc, "slots": slots,
            # 갈래가 있는 종류만 자리 이름을 적는다(딜 소싱). 나머지는 자리가
            # 하나라 이름을 붙이면 없는 구분을 있는 것처럼 보이게 한다.
            "has_buckets": kind in template_pick.NAME_IS_A_BUCKET}


@router.get("/templates", response_class=HTMLResponse, include_in_schema=False)
def templates_page(request: Request, db: Session = Depends(get_db),
                   user: User = Depends(get_current_user), msg: str = ""):
    # 지워졌거나 꺼진 문구를 가리키는 선택을 여기서 치운다. 화면에는 "고름"
    # 인데 실제로는 다른 문구가 나가는 상태로 남으면 안 된다.
    if template_pick.prune(db, user.id):
        db.commit()

    rows = _visible(db, user)
    # 구간은 **딜 제안 관리의 탭**을 따른다. 문구가 열다섯 종류로 나열돼 있으면
    # 어느 것을 고쳐야 그 탭이 바뀌는지 알 수 없었다. 탭 순서도 발송 화면과
    # 같아야 한다 — 두 화면의 순서가 다르면 같은 것을 찾는 데 매번 헤맨다.
    from .deals import MODE_TEMPLATE_KIND, MODE_TITLES  # noqa: PLC0415

    tabs = [_section(db, user, rows, kind, MODE_TITLES.get(mode, ""),
                     MODE_TITLES.get(mode, ""), mode)
            for mode, kind in MODE_TEMPLATE_KIND.items()]

    # 탭에 걸리지 않은 종류들 — 인사말·연결·기업 리마인드·메일 제목. 발송
    # 화면의 탭에서 직접 고르는 것은 아니지만 쓰이는 곳이 있다.
    tabbed = set(MODE_TEMPLATE_KIND.values())
    others = [_section(db, user, rows, kind, label, "", "")
              for kind, label, _desc in KINDS if kind not in tabbed]

    ctx = base_ctx(request, db, user, active="templates")
    ctx.update({"tabs": tabs, "others": others, "variables": VARIABLES, "msg": msg})
    return jinja.TemplateResponse("templates.html", ctx)


@router.post("/templates/choose", include_in_schema=False)
def choose_template(
    kind: str = Form(...),
    template_id: int = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """이 종류에 내가 쓸 문구를 정한다 — 회차마다가 아니라 여기서 한 번.

    고치는 권한과는 상관이 없다. 팀 기본은 관리자만 고치지만 **고르는 것은
    각자** 한다 — 그래야 한 문구를 두고 사람마다 다른 것을 쓸 수 있다.
    """
    if kind not in KIND_LABELS:
        raise HTTPException(status_code=400, detail="알 수 없는 문구 종류입니다")
    t = db.get(MessageTemplate, template_id)
    # 남의 개인 문구는 고를 수 없다. 그 사람이 고칠 때마다 내 발송이 따라
    # 바뀌고, 그 사람이 지우면 내 선택이 사라진다.
    if (t is None or t.kind != kind or t.is_active != 1
            or t.user_id not in (None, user.id)):
        raise HTTPException(status_code=400, detail="고를 수 없는 문구입니다")
    # 자리는 화면이 보낸 값이 아니라 **문구 자신**에서 읽는다 — 화면 값을
    # 믿으면 '대표님·5개사' 문구가 다른 갈래의 자리에 꽂힐 수 있다.
    template_pick.set_choice(db, user.id, kind, t.id,
                             variant=template_pick.variant_of(kind, t.name))
    db.commit()
    return RedirectResponse(f"/templates?msg={quote('이 문구를 쓰기로 했습니다')}#{kind}",
                            status_code=303)


@router.post("/templates/copy", include_in_schema=False)
def copy_template(
    template_id: int = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """기본 문구를 그대로 베껴 **내 문구**를 만들고, 곧바로 그것을 고른다.

    빈 칸을 주고 처음부터 쓰라고 하면 아무도 쓰지 않는다. 지금 나가는 문구가
    이미 들어 있어야 한 줄만 고쳐서 제 것으로 만든다.

    만들자마자 고른 상태로 두는 이유: 만들어 놓고 고르지 않으면 왜 내 문구가
    안 나가는지 알 수 없다.
    """
    src = db.get(MessageTemplate, template_id)
    if src is None or src.user_id is not None:
        # 베낄 것은 팀 기본뿐이다. 내 문구를 또 베끼면 두 벌이 되고, 그때부터는
        # 어느 것이 나가는지 다시 헷갈린다.
        raise HTTPException(status_code=400, detail="복사할 수 있는 문구가 아닙니다")
    variant = template_pick.variant_of(src.kind, src.name)
    if any(t.user_id == user.id
           for t in template_pick.candidates(db, user.id, src.kind, variant)):
        return RedirectResponse(
            f"/templates?msg={quote('이미 내 문구가 있습니다')}#{src.kind}",
            status_code=303)
    # 딜 소싱은 이름이 곧 갈래라 이름을 바꾸면 그 갈래에서 쓰이지 않는다.
    # 나머지 종류의 이름은 사람이 알아보라고 붙인 딱지일 뿐이다.
    name = src.name if src.kind in template_pick.NAME_IS_A_BUCKET else "내 문구"
    mine = MessageTemplate(user_id=user.id, kind=src.kind, name=name,
                           body=src.body, is_active=1)
    db.add(mine)
    db.flush()
    template_pick.set_choice(db, user.id, src.kind, mine.id, variant=variant)
    db.commit()
    return RedirectResponse(
        f"/templates?msg={quote('기본 문구를 복사했습니다 — 이제 고쳐 쓰세요')}#{src.kind}",
        status_code=303)


@router.post("/templates/new", include_in_schema=False)
def create_template(
    kind: str = Form(...),
    name: str = Form(""),
    body: str = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if kind not in KIND_LABELS:
        raise HTTPException(status_code=400, detail="알 수 없는 문구 종류입니다")
    if not body.strip():
        return RedirectResponse("/templates?msg=내용을+입력하세요", status_code=303)
    db.add(MessageTemplate(user_id=user.id, kind=kind,
                           name=(name.strip() or None), body=body.strip(), is_active=1))
    db.commit()
    return RedirectResponse("/templates?msg=문구를+추가했습니다", status_code=303)


@router.post("/templates/{template_id}/edit", include_in_schema=False)
def edit_template(
    template_id: int,
    name: str = Form(""),
    body: str = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    t = db.get(MessageTemplate, template_id)
    if t is None:
        raise HTTPException(status_code=404, detail="문구를 찾을 수 없습니다")
    if not _editable(t, user):
        raise HTTPException(status_code=403, detail="이 문구를 수정할 권한이 없습니다")
    t.name = name.strip() or None
    t.body = body.strip()
    db.commit()
    return RedirectResponse("/templates?msg=문구를+수정했습니다", status_code=303)


@router.post("/templates/{template_id}/delete", include_in_schema=False)
def delete_template(
    template_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    t = db.get(MessageTemplate, template_id)
    if t is None:
        raise HTTPException(status_code=404, detail="문구를 찾을 수 없습니다")
    if not _editable(t, user):
        raise HTTPException(status_code=403, detail="이 문구를 삭제할 권한이 없습니다")
    # 이 문구를 골라 둔 사람들의 선택을 먼저 거둔다. 남겨 두면 없는 문구를
    # 가리킨 채로 남아 "골라 뒀는데 다른 것이 나간다" 가 되고, 외래키가 켜져
    # 있으면 삭제 자체가 막힌다.
    template_pick.forget_template(db, t.id)
    db.delete(t)
    db.commit()
    return RedirectResponse("/templates?msg=문구를+삭제했습니다", status_code=303)


@router.get("/api/templates")
def list_templates(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """발송 화면의 문구 선택기용."""
    rows = _visible(db, user)
    return {
        "templates": [
            {"id": t.id, "kind": t.kind,
             "name": t.name or ("팀 기본" if t.user_id is None else "내 문구"),
             "body": t.body, "mine": t.user_id == user.id}
            for t in rows
        ],
        "kinds": [{"kind": k, "label": label} for k, label, _ in KINDS],
    }
