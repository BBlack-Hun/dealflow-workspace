"""화면 공통 컨텍스트 — 사이드바 메뉴 · 에이전트 배지 · 개발용 사용자 전환.

페이지 라우터가 여럿(pages / setup)이라 공통 컨텍스트를 한 곳에 둔다. 여기가
갈라지면 화면마다 사이드바 상태가 달라진다(실제로 /setup 만 사용자 전환이 안 되는
식의 버그가 나기 쉽다).
"""
from __future__ import annotations

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import config, version
from .deps import agent_status, consultant_may_open, may_view_consulting
from .models import User

# 좌측 메뉴. 쓰는 순서대로 둔다.
#
# 화면에는 개발 용어를 쓰지 않는다. 예전에 'S2' 같은 스프린트 배지와
# '에이전트' 같은 말이 그대로 보였는데, 쓰는 사람에게는 아무 뜻이 없다.
# 아직 없는 화면은 `ready: False` 로 두고 '준비 중'으로만 표시한다.
#
# `admin_only` 인 메뉴는 관리자에게만 보인다(들어가도 403 이지만, 보이지 않는 편이 낫다).
MENU = [
    {"key": "check", "label": "주간 업무", "href": "/todo", "ready": True},
    {"key": "home", "label": "대시보드 요약", "href": "/", "ready": True},
    {"key": "deal", "label": "딜 제안 관리", "href": "/deals", "ready": True},
    {"key": "su", "label": "IR 기업현황", "href": "/companies", "ready": True},

    # 스타트업 자료가 투자사 관리 현황의 참고 탭에 같이 붙어 있었다. 그 화면의
    # 나머지 자료는 **심사역에게 딜을 보내는** 이야기인데(전화응대 · 딜소개
    # 스크립트 · 투자사 성격정리) 그 사이에 **스타트업 대표에게 보내는** 매월
    # 리마인드 가이드가 섞여 있어, 지금 누구에게 하는 말인지 탭을 열어 봐야
    # 알 수 있었다. 말 거는 상대가 다르면 집어야 할 문구도 다르다.
    #
    # 이름을 `스타트업 관리` 로 하지 않았다. 옆에 `투자사 관리 현황`·`IR
    # 기업현황` 이 있어 셋이 한 덩어리로 읽힌다 — 투자컨설턴트 메뉴를 이미 같은
    # 이유로 고쳤다. 무엇을 하는 화면인지(달마다 한 번 챙긴다)를 이름에 남긴다.
    {"key": "startup", "label": "스타트업 리마인드", "href": "/startup", "ready": True},

    {"key": "vc", "label": "투자사 관리 현황", "href": "/contacts", "ready": True},
    # 딜소개를 **보내는** 명단(투자사 관리 현황)과 다르다 — 여기는 우리 딜을
    # 같이 볼 사람이라 무엇을 찾는지로 갈래가 나뉜다.
    {"key": "sourcing", "label": "딜 소싱", "href": "/sourcing", "ready": True},
    # 후속 문구와 IR·미팅은 둘 다 **보낸 뒤에 챙기는 일**이라 한 메뉴로 묶었다.
    # 안에서 탭으로 나뉘어 있다(_flow_tabs.html) — 매일 두 군데를 열지 않게.
    {"key": "flow", "label": "딜 진행 관리", "href": "/followups", "ready": True},
    {"key": "templates", "label": "딜 제안 문구", "href": "/templates", "ready": True},

    # 이름이 `투자컨설턴트 현황` 이었다. `현황` 은 옆의 `투자사 관리 현황`·
    # `IR 기업현황` 과 겹쳐 세 메뉴가 한 덩어리로 읽혔다 — 담당자를 가리키는
    # 이 메뉴만 사람 이름으로 남긴다. 화면 제목(`page_title`)도 여기서 나오므로
    # 이 한 줄이 좌측 메뉴와 제목을 같이 바꾼다(`menu_label`).
    {"key": "consult", "label": "투자컨설턴트", "href": "/consulting", "ready": True,
     "needs": "consulting"},
    {"key": "report", "label": "업무 보고", "href": "/report", "ready": True},
    {"key": "admin", "label": "팀 현황", "href": "/team", "ready": True, "admin_only": True},
]


# `needs` 가 붙은 메뉴는 **그 화면을 막는 판정을 그대로 읽는다.** 예전에는
# 계정 속성 이름(`can_view_consulting`)을 적어 두었는데, 라우터는 역할까지 보고
# 메뉴는 칸만 봐서 두 조건이 갈릴 자리였다 — 팀 현황 표가 실제로 그렇게 갈려
# 컨설턴트 줄에 `막힘` 이라고 떴다. 메뉴도 라우터도 같은 함수를 읽게 둔다.
NEEDS = {"consulting": may_view_consulting}


def can_see(user: User, item: dict) -> bool:
    """이 사람에게 이 메뉴를 보여도 되는가.

    관리자는 전부 본다. `needs` 가 붙은 메뉴는 그 화면의 접근 판정(`NEEDS`)이
    통과한 사람만 본다 — 볼 사람 이름을 코드에 박으면 담당이 바뀔 때마다
    배포해야 한다.

    투자컨설턴트는 **자기 화면 하나만** 본다. 그 판정은 라우터를 막는 것과
    같은 목록(`deps.CONSULTANT_PATHS`)으로 한다 — 메뉴용 목록을 따로 두었더니
    메뉴는 걸러졌는데 주소를 직접 치면 열리는 상태가 됐다. 목록이 둘이면
    하나는 반드시 낡는다.
    """
    if user.role == "consultant":
        return consultant_may_open(item["href"])
    if user.role == "admin":
        return True
    if item.get("admin_only"):
        return False
    need = item.get("needs")
    return not need or NEEDS[need](user)


def visible_menu(user: User) -> list:
    return [m for m in MENU if can_see(user, m)]


def screen_label(path: str) -> str:
    """이 주소가 좌측 메뉴의 어느 화면인가 — 없으면 빈 문자열.

    권한이 없어 막힌 화면이 "팀 현황 화면은 …" 이라고 제 이름을 대려면 필요하다
    (`deps._admin_only_page`). 이름을 그 화면에 적어 두지 않고 메뉴에서
    가져오는 것은, 메뉴 이름을 고쳤을 때 안내창만 옛 이름으로 남지 않게
    하려는 것이다.
    """
    item = next((m for m in MENU if m["href"] == path), None)
    return item["label"] if item else ""


def menu_label(active: str) -> str:
    """지금 보고 있는 화면의 이름. 좌측 메뉴와 화면 제목이 어긋나지 않게 한 곳에서 가져온다."""
    item = next((m for m in MENU if m["key"] == active), None)
    return item["label"] if item else "CONTACTVC ASSET"


def base_ctx(request: Request, db: Session, user: User, active: str) -> dict:
    return {
        "page_title": menu_label(active),
        "request": request,
        "menu": visible_menu(user),
        "active": active,
        "user": user,
        "agent": agent_status(db, user.id),
        "test_room": config.TEST_ROOM,
        "current_path": request.url.path,
        "app_version": version.VERSION,
    }
