"""수정 로그 — **남의 것과 공용 자료를 고친 일을 한 곳에 모은다.**

왜 만드는가
-----------
곧 팀원이 서로의 명단을 고칠 수 있게 된다. 그 순간 **"이거 누가 바꿨지?"** 가
반드시 생기고, 이 명단은 **발송 대상**이라 잘못 바뀐 채로 지나가면 그대로
오발송이다. 공용 화면(IR 기업 현황 · 딜 소싱 · 딜 제안 문구 · 참고 자료)도
마찬가지다 — 주인이 없으니 누가 고쳐도 팀 전체에 그대로 보인다.

**자기 것만 고친 것은 남기지 않는다.** 남기면 하루에 수백 줄이 쌓여 아무도 안
본다. 볼 수 있는 로그여야 쓸모가 있다.

왜 세션 이벤트 한 곳인가 (고른 근거)
------------------------------------
공용·타인 화면의 쓰기 경로는 지금 **49개**다(companies 7 · ir 11 ·
consulting 8 · templates_crud 5 · sourcing 4 · contacts 14). 49곳에 로그 호출을
손으로 흩뿌리면 몇 개는 반드시 빠지고, **앞으로 생기는 새 경로에는 아무도 안
붙인다.** 이 저장소가 반복해서 당한 사고가 정확히 그것이다(좌측 메뉴 목록과
라우터 목록이 갈려 투자컨설턴트에게 화면이 다 열려 있던 일).

후보를 셋 견주었다.

* **의존성(`Depends`)으로 묶기** — 라우터마다 붙여야 한다. 붙이는 것을 잊으면
  그 길만 조용히 안 남는다. 목록과 라우터가 갈리는 그 사고와 같은 모양이다.
  게다가 의존성은 **무엇이 어떻게 바뀌었는지**를 모른다 — 요청이 들어온 것만
  안다.
* **미들웨어에서 쓰기 메서드를 잡기** — 새 라우트까지 저절로 지난다는 점은
  좋다(투자컨설턴트 차단을 이미 이렇게 하고 있다). 그러나 미들웨어가 아는
  것은 `POST /api/contacts/418` 까지다. **어느 줄의 어느 칸이 무엇에서
  무엇으로 바뀌었는지**는 알 수 없고, 그 줄이 남의 것인지 공용인지도 모른다.
  앞뒤 값을 알려면 요청 전후로 표를 통째로 떠 봐야 하는데 그럴 수는 없다.
* **SQLAlchemy 세션 이벤트로 바뀐 줄을 잡기** — 골랐다. ORM 으로 들어가는
  모든 INSERT · UPDATE · DELETE 가 **한 번의 flush 를 반드시 지나고**,
  그 자리에서 `get_history()` 로 **전→후 값**을 그대로 읽을 수 있다.
  라우터가 몇 개든, 앞으로 몇 개가 더 생기든 이 자리를 건너뛸 수 없다.
  세션은 `db.SessionLocal` 하나뿐이라(라우터는 전부 `Depends(get_db)`) 걸 자리도
  하나다.

세션 이벤트가 **모르는 것 하나**가 누구인가다 — 세션은 요청을 모른다. 그래서
`app/main.py` 의 미들웨어가 **쓰기 요청일 때만** 누가 어느 주소를 눌렀는지를
문맥변수에 심어 준다(`begin`/`end`). 두 조각이 하는 일이 갈라져 있다: 미들웨어는
**누구인지**만, 세션 이벤트는 **무엇이 바뀌었는지**만 안다.

문맥변수가 비어 있으면(백그라운드 스케줄러 · 가져오기 스크립트 · 검사) 아무
것도 남기지 않는다. 발송 실이 만든 줄까지 남으면 "누가 바꿨나" 를 보려고 연
목록이 기계 기록으로 덮인다.

**GET 은 아예 지나지 않는다.** 미들웨어가 쓰기 메서드에서만 문맥을 심으므로,
읽기 중에 무엇이 저장되더라도(마지막 접속 시각 같은 것) 로그에 남지 않는다.

한 번에 여러 줄이 바뀌는 일
--------------------------
시트 가져오기(`/api/import/contacts`)처럼 한 번에 수백 줄을 갈아 끼우는 길은
줄마다 한 줄씩 남는다. 잡음처럼 보이지만 **일부러 그렇게 둔다** — 가져오기가
남의 명단을 통째로 덮어쓰는 일이 이 앱에서 가장 크게 어긋날 수 있는 자리이고,
"몇 시에 누가 무엇을 덮었나" 를 줄 단위로 못 보면 되돌릴 것을 고를 수가 없다.
화면에서 화면·범위로 걸러 보는 칸이 있는 이유가 이것이다.

로그를 못 남기면 저장도 안 된다
-------------------------------
이 자리에서 예외가 나면 **그 요청의 저장이 통째로 실패한다.** 삼키지 않는다.
로그가 조용히 비는 쪽이 더 나쁘기 때문이다 — 비어 있는 로그를 보고 "아무도
안 건드렸다" 고 읽게 된다. 그래서 여기 들어오는 코드는 값을 읽을 때 기본값을
두고(`getattr(row, name, "")`), 무엇이든 글자로 바꿀 수 있게 해 둔다.

한계 — ORM 을 지나지 않는 쓰기
------------------------------
`db.execute(delete(...))` · `db.query(...).delete()` 같은 **한꺼번에 지우기**는
flush 를 지나지 않아 이 자리에서 안 잡힌다. 지금 그런 자리가 어디인지는
`tests/test_edit_log.py` 의 `KNOWN_BULK` 에 이유와 함께 적혀 있고, 새로 생기면
시험이 깨진다.
"""
from __future__ import annotations

import json
from contextvars import ContextVar, Token
from typing import Any, Callable, Dict, List, Optional

from sqlalchemy import event, inspect
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy.orm.attributes import get_history

from ..clock import now_iso

# 쓰기로 보는 메서드. 읽기(GET·HEAD·OPTIONS)는 여기 없으므로 문맥이 심기지
# 않고, 문맥이 없으면 아무 것도 남지 않는다.
WRITE_METHODS = frozenset({"POST", "PATCH", "PUT", "DELETE"})

SCOPE_OTHERS = "others"   # 남의 것
SCOPE_SHARED = "shared"   # 공용

ACTION_CREATE = "create"
ACTION_UPDATE = "update"
ACTION_DELETE = "delete"

#: 값 하나를 로그에 남길 때의 길이 상한. 넘으면 잘리고 `…` 이 붙는다.
#: 허용 목록에 있는 칸은 원래 짧지만, 누가 긴 글을 그 칸에 넣기 시작해도
#: 로그가 통째로 부풀지 않게 막아 둔다.
VALUE_MAX = 120


# ─────────────────────────────────────────────────────────────────────────────
# 1. 어느 표를 보는가
#
# **표마다 하나씩 이유를 대고 고른다.** 새 표가 생기면
# `tests/test_edit_log.py` 의 표 훑기 검사가 깨지므로, 만든 사람이 여기
# 둘 중 하나에 적게 된다 — 조용히 빠지지 않는다.
# ─────────────────────────────────────────────────────────────────────────────

class Watch:
    """이 표의 줄이 **누구 것인지**와 **어느 화면의 줄인지**.

    `owner` 는 주인을 담은 칸 이름이고, `None` 이면 **주인이 없는 공용 자료**다.
    판정을 여기서 새로 짓지 않는다 — 화면과 라우터가 이미 쓰는 그 칸을 그대로
    읽는다(`VcContact.user_id` · `SheetOwner.user_id` · `ConsultingCompany.user_id`).
    새로 지으면 화면의 권한과 로그의 판정이 갈린다.
    """

    __slots__ = ("owner", "href", "label", "why")

    def __init__(self, *, owner: Optional[str], href, label: Callable[[Any], str],
                 why: str) -> None:
        self.owner = owner
        #: 이 줄을 보는 화면의 주소. 줄마다 다르면 함수로 준다(참고 자료).
        self.href = href
        #: 그 줄이 무엇인가 — 사람이 읽을 이름.
        self.label = label
        self.why = why


def _attr(name: str) -> Callable[[Any], str]:
    return lambda row: str(getattr(row, name, "") or "")


WATCHED: Dict[str, Watch] = {
    # ── 주인이 있는 자료 ────────────────────────────────────────────────────
    "vc_contacts": Watch(
        owner="user_id", href="/contacts", label=_attr("name"),
        why="투자사 담당자 명단 — 이 표가 곧 발송 대상이다. 남이 고치면 오발송이 된다."),
    "sheet_owners": Watch(
        owner="user_id", href="/contacts", label=_attr("label"),
        why="명단(시트)의 주인. 주인이 없는 명단은 아직 배정 전이라 공용으로 본다."),
    "consulting_companies": Watch(
        owner="user_id", href="/consulting", label=_attr("company_name"),
        why="투자컨설턴트 표의 줄. 주인 없는 줄은 배정 전이라 공용으로 본다."),
    "message_templates": Watch(
        owner="user_id", href="/templates", label=_attr("name"),
        why="딜 제안 문구. 주인이 없는 것이 **팀 기본 문구**라 공용으로 본다."),
    "ir_requests": Watch(
        owner="user_id", href="/followups", label=_attr("company_name"),
        why="IR 요청. 주인만 고치게 되어 있어(`ir._owned_request`) 대개 자기 것이지만, "
            "판정을 여기서 다시 좁히지 않는다 — 그 규칙이 넓어지면 로그가 같이 움직여야 한다."),
    "meetings": Watch(
        owner="user_id", href="/followups", label=_attr("company_name"),
        why="미팅. `ir_requests` 와 같은 이유."),
    "users": Watch(
        owner="id", href="/team", label=_attr("name"),
        why="계정. 남의 권한·투자현황·비밀번호를 바꾸는 것은 공용 화면(팀 현황)에서 "
            "남의 것을 고치는 일 그 자체다. 자기 비밀번호를 바꾸는 것은 자기 것이라 안 남는다."),

    # ── 주인이 없는 공용 자료 ──────────────────────────────────────────────
    "ir_companies": Watch(
        owner=None, href="/companies", label=_attr("name"),
        why="IR 기업. `owner_user_id` 칸이 있기는 하지만 **아무 조회도 그 칸으로 "
            "좁히지 않고**(`company_rows` 는 `user` 를 받지도 않는다) 손으로 세운 줄에만 "
            "채워진다 — 시트에서 넘어온 줄은 전부 비어 있다(`services/pipeline.py`). "
            "화면이 이미 '누구나 어느 기업이든 고친다' 로 움직이므로 공용이 맞다."),
    "sourcing_contacts": Watch(
        owner=None, href="/sourcing", label=_attr("name"),
        why="딜 소싱 명단. 주인 칸이 없고 로그인한 사람이면 누구나 고친다."),
    "consulting_sheets": Watch(
        owner=None, href="/consulting", label=_attr("label"),
        why="투자컨설턴트 화면의 탭. `탭은 사람마다가 아니라 팀 공용이다`(models)."),
    "consulting_columns": Watch(
        owner=None, href="/consulting", label=_attr("label"),
        why="월 열. 탭에 붙어 있어 주인이 없고, 하나 지우면 팀 전체 줄에서 그 달이 사라진다."),
    "contact_columns": Watch(
        owner=None, href="/contacts", label=_attr("label"),
        why="투자사 명단의 추가 열. 명단마다 하나뿐이라 그 명단을 보는 사람이 같이 쓴다."),
    "ref_sheets": Watch(
        owner=None, href=lambda row: "/" + (getattr(row, "page", "") or ""),
        label=_attr("title"),
        why="참고 자료(스크립트·표). 화면마다 하나씩 서 있고 주인이 없다. "
            "어느 화면 것인지는 줄의 `page` 칸이 말한다."),
    "auto_send_settings": Watch(
        owner=None, href="/team", label=_attr("kind"),
        why="자동 준비 설정. 팀 현황에서 관리자가 켜고 끄는 팀 공용 스위치다."),
    "schedule_rules": Watch(
        owner=None, href="/followups", label=_attr("label"),
        why="발송 일정 규칙. 팀 전체의 날짜를 정하는 자리라 공용이다."),
}


#: 보지 않는 표와 그 이유. **비워 두지 않는다** — 이유를 적어 두지 않으면
#: 다음 사람이 '빠뜨린 것인지 일부러 뺀 것인지' 를 알 수 없다.
UNWATCHED: Dict[str, str] = {
    "edit_logs": "이 표 자신. 로그가 로그를 남기면 끝이 없다.",
    "sessions": "로그인 세션. 기계 기록이고 값에 세션 열쇠가 들어 있다.",
    "agent_devices": "보내는 기기의 상태(몇 초마다 오는 신호). 사람이 고친 것이 아니다.",
    "contact_activities": "담당자 줄에 딸린 활동 기록. 가져오기와 발송이 만든다 — "
                          "사람이 화면에서 고치는 자료가 아니고, 줄 자체가 바뀐 것은 "
                          "`vc_contacts` 쪽에 이미 남는다.",
    "template_choices": "어느 문구 본을 쓸지 고른 표시. 화면에 보이는 자료가 아니라 "
                        "`message_templates` 를 가리키는 손가락이고, 갈래 이름을 한 번 "
                        "바꾸면 사람 수만큼 줄이 쌓인다. 이름이 바뀐 것은 문구 쪽에 남는다.",
    "deal_batches": "딜소개 발송 회차. 보낸 기록이지 고친 기록이 아니다.",
    "deal_batch_companies": "발송 회차에 실린 기업. 위와 같다.",
    "deal_queue_items": "발송 대기 목록. 기계가 세운다.",
    "deal_queue_companies": "발송 대기에 실린 기업. 위와 같다.",
    "send_jobs": "발송 작업. 보낸 기록이다.",
    "send_items": "발송 한 건. 보낸 기록이다(문구가 통째로 들어 있기도 하다).",
    "send_sequences": "후속 문구 회차. 기계가 세우고 기계가 멈춘다.",
    "monthly_column_runs": "이달 열을 이미 세웠다는 표시. 사람이 보는 자료가 아니다.",
    "weekly_routines": "주간 업무 되풀이 — 계정마다의 개인 화면이다.",
    "weekly_tasks": "주간 업무 할 일 — 개인 화면이다.",
    "weekly_routine_runs": "주간 업무를 이번 주에 이미 세웠다는 표시.",
    "sms_notices": "문자 알림 발송 기록.",
    "one_liner_backups": "한 줄 소개 되돌리기용 버퍼. 되돌릴 값을 담아 두는 자리이고, "
                         "무엇이 바뀌었는지는 `ir_companies` 쪽에 이미 남는다.",
    "auto_send_runs": "자동 준비가 오늘 몇 건 돌았나. 기계 기록이다.",
}


# ─────────────────────────────────────────────────────────────────────────────
# 2. 어느 칸의 **값**까지 남기는가
#
# **허용 목록이다.** 막을 칸을 적는 방식이면 칸이 하나 늘 때마다 적는 것을
# 잊고, 잊은 칸은 값이 그대로 새어 나간다 — 투자컨설턴트 차단을 허용 목록으로
# 세운 것과 같은 이유다. 목록에 없는 칸은 값 없이 `바뀜` 으로만 남는다.
#
# 무엇을 남기고 무엇을 `바뀜` 으로만 둘지의 기준
#   * 남긴다 — **짧고, 고르는 값이고, 잘못되면 발송이 어긋나는** 칸.
#     담당·명단·단계·켜짐꺼짐·카톡방 이름·날짜·이름표. 이런 칸은 전→후를
#     못 보면 로그를 봐도 무슨 일이 있었는지 알 수 없다.
#   * 남기지 않는다 — **메모·연락처·긴 글.** 메모(`memo` `notes` `note` `body`
#     `summary` `one_liner` …)와 연락처(`phone` `email` `address` …)는 값이
#     길고 개인정보이며, 로그에 통째로 쌓이면 같은 자료가 두 벌이 된다.
#     `바뀜` 만 남겨도 "누가 언제 손댔나" 는 그대로 알 수 있고, 되돌릴 값이
#     필요하면 되돌리기 화면(`/team/restore`)의 그날 백업을 쓴다.
#   * **비밀값은 어떤 경우에도 남기지 않는다.** 비밀번호·토큰은 이 목록에
#     없으므로 값이 실리지 않고, 실수로 여기 적히는 것은
#     `tests/test_edit_log.py` 가 막는다.
# ─────────────────────────────────────────────────────────────────────────────

VALUE_FIELDS = frozenset({
    # 누가 맡았나 · 어디 속했나 — 남이 바꾸면 발송이 통째로 딴 사람에게 간다.
    "user_id", "assignee_name", "source_sheet", "sheet", "bucket",
    "group_name", "page", "role",
    # `position`(줄·열 차례)은 일부러 뺐다. `차례 2 → 3` 은 읽는 사람에게
    # 아무 뜻이 없고, 표를 정렬하기만 해도 모든 줄에 그 한 줄이 붙는다.
    # 차례가 바뀐 것은 발송이 어긋나는 일도 아니다.

    # 이름표. 이름이 바뀌면 그 이름으로 이어진 것들이 같이 움직인다
    # (명단 이름 · 갈래 이름 · 탭 이름).
    "name", "label", "title", "firm", "company_name", "ceo_name",
    "department", "kind", "variant",

    # 어디까지 왔나.
    "status", "connect_stage", "stages", "invited_status", "interest_level",
    "contract_status", "funding_status", "summary_status", "outcome",
    "meet_mode", "firm_type", "series", "sector_major", "sector_minor",
    "top_deal_kind", "share_method", "management", "contract_management",

    # 켜짐 · 꺼짐. 하나 잘못 켜지면 안 나가야 할 곳으로 나간다.
    "is_active", "is_hidden", "is_deal_list", "is_top_deal", "enabled",
    "channel_kakao", "channel_email", "room_verified", "kakao_joined",
    "can_view_consulting", "can_auto_attach_ir",
    "contract_received", "contract_done", "followup_done", "skip_weekend",
    "weekly_goal_sends", "from_hour", "until_hour", "max_per_day",

    # **어느 방으로 나가나.** 이 앱에서 오발송에 가장 가까운 칸이라 값을 남긴다.
    "kakao_room_name",

    # 언제.
    "requested_at", "delivered_at", "scheduled_at", "scheduled_time",
    "done_at", "followup_due", "followup_at", "meeting_offered_at",
    "received_at", "contract_month", "card_registered_at", "effective_from",
    "founded_year", "last_login_at",

    # 일정 규칙의 짧은 설정값.
    "layout", "weekday", "nth_weeks", "offset_min_days", "offset_max_days",
})

#: 이름만 봐도 비밀값인 것. 위 허용 목록에 이 조각이 든 칸이 들어오면
#: 검사가 깨진다 — 목록은 사람이 손으로 늘리는 자리라 한 겹 더 둔다.
#:
#: 이 규칙 때문에 `must_change_password`(비밀번호를 바꿔야 하는가 — 참거짓 한
#: 칸)도 값이 안 남는다. 값을 남겨도 새는 것은 없지만, **예외를 하나 열면
#: 다음 사람이 두 번째 예외를 연다.** 그 칸은 비밀번호가 바뀔 때 같이 켜지고,
#: 비밀번호가 바뀐 것은 이미 `바뀜` 으로 남는다.
SECRET_HINTS = ("password", "token", "secret", "hash", "api_key", "credential")


# 화면에서 읽을 칸 이름. 없으면 칸 이름을 그대로 보여 준다 — 억지로 다 적어
# 두면 칸이 하나 늘 때 여기만 낡아서, 화면에 옛 이름이 남는다.
FIELD_LABELS = {
    "user_id": "담당", "assignee_name": "담당자 이름", "source_sheet": "명단",
    "sheet": "탭", "bucket": "갈래", "group_name": "묶음", "role": "권한",
    "name": "이름", "label": "이름", "title": "제목", "firm": "소속",
    "company_name": "기업", "connect_stage": "연결 단계", "status": "상태",
    "kakao_room_name": "카톡방 이름", "room_verified": "방 확인",
    "channel_kakao": "카톡 발송", "channel_email": "메일 발송",
    "is_hidden": "숨김", "is_active": "사용", "is_deal_list": "딜 명단",
    "can_view_consulting": "투자현황", "can_auto_attach_ir": "자료 자동 첨부",
    "must_change_password": "비밀번호 변경 필요", "password_hash": "비밀번호",
    "series": "라운드", "sector_major": "분야", "sector_minor": "세부 분야",
    "stages": "투자 단계", "interest_level": "관심도", "invited_status": "초대",
    "contract_status": "계약 상태", "funding_status": "투자 상태",
    "outcome": "결과", "meet_mode": "미팅 방식", "kind": "종류",
    "enabled": "켜짐", "firm_type": "기관 유형", "variant": "갈래",
    "memo": "메모", "notes": "칸 메모", "note": "메모", "body": "본문",
    "phone": "연락처", "email": "메일", "one_liner": "한 줄 소개",
    "summary": "요약", "business_desc": "사업 설명", "content_json": "내용",
}


def field_label(name: str) -> str:
    return FIELD_LABELS.get(name, name)


# ─────────────────────────────────────────────────────────────────────────────
# 3. 누가 눌렀나 — 요청 문맥
# ─────────────────────────────────────────────────────────────────────────────

_ACTOR: ContextVar[Optional[dict]] = ContextVar("dealflow_edit_log_actor",
                                                default=None)


def begin(user_id: int, method: str, path: str) -> Token:
    """이 요청 동안 남길 사람을 심는다. `app/main.py` 의 미들웨어가 부른다."""
    return _ACTOR.set({"user_id": user_id, "method": method, "path": path})


def end(token: Token) -> None:
    _ACTOR.reset(token)


def actor() -> Optional[dict]:
    return _ACTOR.get()


def actor_from_request(request) -> Optional[int]:
    """쿠키만 보고 누구인지 알아낸다 — 미들웨어는 `Depends` 를 쓸 수 없다.

    `deps.is_consultant` 가 이미 쓰는 방식 그대로다(세션을 직접 연다).
    **쿠키가 아예 없으면 조회하지 않는다** — 에이전트가 몇 초마다 두드리는
    주소와 로그인 요청이 그렇다.
    """
    from ..db import SessionLocal
    from . import auth as auth_svc

    token = request.cookies.get(auth_svc.SESSION_COOKIE)
    if not token:
        return None
    db = SessionLocal()
    try:
        user = auth_svc.user_for_token(db, token)
        return user.id if user else None
    finally:
        db.close()


# ─────────────────────────────────────────────────────────────────────────────
# 4. 무엇이 바뀌었나 — flush 를 지나는 자리
# ─────────────────────────────────────────────────────────────────────────────

def _trim(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (int, float, bool)):
        return value
    text = str(value)
    return text if len(text) <= VALUE_MAX else text[:VALUE_MAX] + "…"


def _changes(obj, action: str) -> List[dict]:
    """이 줄에서 바뀐 칸들. 값은 허용 목록에 있는 칸만 싣는다.

    **줄이 통째로 생기거나 사라질 때는 값을 남기는 칸만 적는다.** 그때는
    `메모 바뀜` 같은 줄이 아무 것도 말해 주지 않는다 — 줄 전체가 생겼거나
    사라진 것은 `추가`·`삭제` 표시가 이미 말한다. 반대로 고칠 때의 `바뀜` 은
    **어느 칸에 손이 닿았는지**를 말하므로 뜻이 있다.
    """
    out: List[dict] = []
    table = obj.__table__
    for column in table.columns:
        key = column.key
        if key in ("created_at", "updated_at", "id"):
            # 시각 두 칸은 저장할 때마다 저절로 바뀐다 — 남기면 모든 줄에
            # `updated_at 바뀜` 이 붙어 정작 무엇이 바뀌었는지가 묻힌다.
            continue
        if action == ACTION_CREATE:
            after = getattr(obj, key, None)
            if after in (None, ""):
                continue
            before = None
        elif action == ACTION_DELETE:
            before = getattr(obj, key, None)
            if before in (None, ""):
                continue
            after = None
        else:
            history = get_history(obj, key)
            if not history.has_changes():
                continue
            before = history.deleted[0] if history.deleted else None
            after = history.added[0] if history.added else None
            if before == after:
                continue

        if key in VALUE_FIELDS:
            out.append({"field": key, "before": _trim(before),
                        "after": _trim(after)})
        elif action == ACTION_UPDATE:
            # 메모 · 연락처 · 긴 글 · 비밀값. **값은 싣지 않는다.**
            out.append({"field": key, "changed": True})
    return out


def _row_scope(obj, watch: Watch, actor_id: int, action: str):
    """이 줄이 **내 것 · 남의 것 · 공용** 중 무엇인가.

    돌려주는 것은 `(남길까, 범위, 주인)`. 내 것이면 남기지 않는다.

    **고치기 전의 주인으로 판정한다.** 담당을 넘기는 일이 있어서다 — 넘긴
    뒤의 주인으로 보면, 내 줄을 남에게 넘기는 것은 `남의 것을 고쳤다` 가 되고
    남의 줄을 내게 가져오는 것은 `내 것을 고쳤다` 가 되어 **아무 것도 안
    남는다.** 물음은 언제나 "그 줄이 그때 누구 것이었나" 다.
    """
    if watch.owner is None:
        return True, SCOPE_SHARED, None
    owner_id = getattr(obj, watch.owner, None)
    if action == ACTION_UPDATE:
        history = get_history(obj, watch.owner)
        if history.has_changes() and history.deleted:
            owner_id = history.deleted[0]
    if owner_id is None:
        # 주인이 아직 없는 줄(배정 전 명단 · 배정 전 컨설팅 줄)은 공용으로 본다.
        return True, SCOPE_SHARED, None
    if owner_id == actor_id:
        return False, "", owner_id
    return True, SCOPE_OTHERS, owner_id


def _href(watch: Watch, obj) -> str:
    return watch.href(obj) if callable(watch.href) else watch.href


def _screen(href: str) -> str:
    from ..ui import screen_label   # ui → services 는 순환이 아니다

    return screen_label(href)


def _collect(session: OrmSession, action: str, rows, ctx: dict) -> List[dict]:
    out = []
    for obj in rows:
        table = getattr(obj, "__tablename__", None)
        watch = WATCHED.get(table)
        if watch is None:
            continue
        if action == ACTION_UPDATE and not session.is_modified(
                obj, include_collections=False):
            continue
        keep, scope, owner_id = _row_scope(obj, watch, ctx["user_id"], action)
        if not keep:
            continue
        changes = _changes(obj, action)
        if not changes and action == ACTION_UPDATE:
            # 저장은 했지만 실제로 바뀐 칸이 없다 — 남길 것이 없다.
            # 줄을 세우거나 지운 것은 **칸이 하나도 없어도** 남긴다.
            continue
        href = _href(watch, obj)
        out.append({
            "obj": obj,
            "row": {
                "at": now_iso(),
                "actor_user_id": ctx["user_id"],
                "target_user_id": owner_id,
                "scope": scope,
                "action": action,
                "table_name": table,
                "screen": _screen(href),
                "row_label": _trim(watch.label(obj)) or "",
                "method": ctx["method"],
                "path": ctx["path"],
                "changes_json": json.dumps(changes, ensure_ascii=False),
            },
        })
    return out


_PENDING = "dealflow_edit_log_pending"


def _before_flush(session: OrmSession, flush_context, instances) -> None:
    """바뀐 줄을 **여기서** 읽는다 — flush 가 끝나면 전 값이 사라진다."""
    ctx = _ACTOR.get()
    if not ctx:
        return
    pending = []
    pending += _collect(session, ACTION_CREATE, list(session.new), ctx)
    pending += _collect(session, ACTION_UPDATE, list(session.dirty), ctx)
    pending += _collect(session, ACTION_DELETE, list(session.deleted), ctx)
    if pending:
        session.info.setdefault(_PENDING, []).extend(pending)


def _after_flush(session: OrmSession, flush_context) -> None:
    """줄 번호가 정해진 뒤에 적는다.

    새로 만든 줄은 flush 전에는 번호가 없다. 그래서 읽는 것은 `before_flush`,
    적는 것은 `after_flush` 로 나눈다.

    적을 때 ORM 객체를 만들지 않고 **표에 바로 넣는다**(`Table.insert`). 객체를
    만들면 그것이 다시 `before_flush` 를 지나 로그가 로그를 남긴다.
    """
    pending = session.info.pop(_PENDING, None)
    if not pending:
        return
    from ..models import EditLog

    rows = []
    for item in pending:
        row = item["row"]
        state = inspect(item["obj"])
        ident = state.identity
        row["row_id"] = int(ident[0]) if ident else 0
        rows.append(row)
    session.execute(EditLog.__table__.insert(), rows)


_INSTALLED = False


def install() -> None:
    """세션 이벤트를 건다. `create_app()` 이 한 번 부른다.

    `SessionLocal` 하나에만 걸면 되지만, 클래스에 걸어 두면 어디서 세션을 새로
    만들어도(백업 · 되돌리기가 그렇다) 같이 지난다. 문맥이 없으면 아무 일도
    일어나지 않으므로 걸어 두는 값이 싸다.
    """
    global _INSTALLED
    if _INSTALLED:
        return
    event.listen(OrmSession, "before_flush", _before_flush)
    event.listen(OrmSession, "after_flush", _after_flush)
    _INSTALLED = True


# ─────────────────────────────────────────────────────────────────────────────
# 5. 얼마나 보관하나 (정책만 — 지우는 것은 이번에 만들지 않는다)
# ─────────────────────────────────────────────────────────────────────────────

#: **13개월.** 이 로그를 여는 상황은 "이번 달 발송이 이상하다 → 지난달에 누가
#: 뭘 바꿨나" 이고, 이 앱은 달 단위로 돈다(월별 리마인드 열 · 월간 보고).
#: 작년 같은 달과 견주는 일이 있어 12개월에 한 달을 더 얹는다. 그보다 오래된
#: 줄은 아무도 열지 않는데 이름·명단 이름 같은 개인정보만 남는다.
#:
#: **지우는 것은 이번에 만들지 않았다.** 만들 때는 백업과 같은 자리
#: (`services/backup.py` 처럼 이 프로세스 안 스케줄러)에 하루 한 번 돌리고,
#: 지우기 전에 **그날 백업이 있는지 먼저 본다** — 로그를 지우는 코드가
#: 백업 없이 도는 날이 가장 위험하다.
RETENTION_MONTHS = 13


# ─────────────────────────────────────────────────────────────────────────────
# 6. 보는 자리 — 팀 현황 안의 `수정 로그`
# ─────────────────────────────────────────────────────────────────────────────

#: 한 번에 보여 주는 줄 수. 더 보려면 범위·화면으로 걸러 본다 —
#: 페이지 나누기를 두면 "언제부터 언제까지 봤는지" 를 사람이 기억해야 한다.
PAGE_SIZE = 200


def _one_change(item: dict, names: dict) -> dict:
    """화면이 그대로 그릴 수 있게 한 줄로 편다."""
    field = item.get("field", "")
    out = {"label": field_label(field), "value_kept": "changed" not in item}
    if not out["value_kept"]:
        return out

    def shown(value):
        if value is None or value == "":
            return "(빈 값)"
        # 담당 칸은 번호로 남아 있다 — 번호를 보여 주면 아무도 못 읽는다.
        if field in ("user_id", "owner_user_id", "actor_user_id"):
            return names.get(int(value), f"#{value}")
        return str(value)

    out["before"] = shown(item.get("before"))
    out["after"] = shown(item.get("after"))
    return out


def recent(db, *, scope: str = "", screen: str = "", limit: int = PAGE_SIZE):
    """최신 줄부터. 화면이 그릴 수 있는 모양으로 돌려준다.

    걸러 보는 칸을 둘만 둔다 — **범위**(남의 것 / 공용)와 **화면**. 이 로그를
    여는 까닭이 "내가 안 한 변경이 어디서 났나" 라서, 그 둘이면 좁혀진다.
    """
    from sqlalchemy import select

    from ..models import EditLog, User

    names = {u.id: u.name for u in db.execute(select(User)).scalars().all()}

    stmt = select(EditLog).order_by(EditLog.at.desc(), EditLog.id.desc())
    if scope in (SCOPE_OTHERS, SCOPE_SHARED):
        stmt = stmt.where(EditLog.scope == scope)
    if screen:
        stmt = stmt.where(EditLog.screen == screen)
    rows = list(db.execute(stmt.limit(limit)).scalars().all())

    out = []
    for row in rows:
        try:
            changes = json.loads(row.changes_json or "[]")
        except ValueError:
            changes = []
        out.append({
            "at": row.at or "",
            "actor": names.get(row.actor_user_id, f"#{row.actor_user_id}"),
            "target": (names.get(row.target_user_id, f"#{row.target_user_id}")
                       if row.target_user_id else ""),
            "scope": row.scope,
            "action": row.action,
            "screen": row.screen or row.table_name,
            "row_label": row.row_label or f"{row.table_name} {row.row_id}",
            "path": row.path or "",
            "changes": [_one_change(c, names) for c in changes],
        })
    return out


def screens() -> list:
    """걸러 보기 목록에 세울 화면 이름 — **보는 표에서 만든다.**

    손으로 적어 두면 표가 하나 늘 때 그 화면만 목록에서 조용히 빠진다.
    """
    from ..ui import screen_label

    out = []
    for watch in WATCHED.values():
        if callable(watch.href):
            continue
        label = screen_label(watch.href)
        if label and label not in out:
            out.append(label)
    return sorted(out)
