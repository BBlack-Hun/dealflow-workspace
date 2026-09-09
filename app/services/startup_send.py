"""스타트업 월간 발송 — **누가 보낼 수 있고, 어느 줄이 보낼 수 있는가.**

달마다 한 번, 그 달 말까지 「IR 자료를 요청한 투자사 목록」(가려서)을 그 기업
대표 카톡방으로 보낸다. 지금까지는 화면이 글을 지어 주면 사람이 [문구 복사] 로
퍼 날랐다 — 스타트업 카톡방을 담을 칸이 없어서였다(`IrCompany.kakao_room_name`
이 0070 에서 생겼다).

## 이 파일이 하는 일은 셋뿐이다

1. **누가 보낼 수 있는가** — 설정이 고른 계정 하나(`may_send`).
2. **어느 기업 줄이 보낼 수 있는가** — 방 이름이 있고 실을 줄이 있는가(`rows`).
3. 그 둘을 화면이 읽을 모양으로 내놓는다(`status`).

**글은 여기서 짓지 않는다.** `services/ir_kakao.py` 하나다 — 화면도 `/setup` 의
시험 자리도 발송도 그 함수를 지난다. 여기서 한 줄이라도 이어 붙이면 사람이 화면
에서 본 글과 대표가 받는 글이 갈린다.

**세는 것도 가리는 것도 여기서 하지 않는다.** 각각 `ir_monthly` · `ir_mask`
한 곳이다. 이 파일은 그 결과에 **방 이름**만 붙인다.

**발송 목록을 만드는 것도 여기가 아니다.** `routers/deals.create_send_list` 를
그대로 지난다(`routers/startup_send.py`) — 방 이름 확인 · 시험방 치환 · 문구
스냅숏이 전부 그 함수 안에 있어서, 한 벌 더 적으면 그중 하나가 빠진 채로 실제
대표 카톡방에 나간다. 미팅 후기 대기 목록이 같은 이유로 그 함수를 부른다.

## 왜 계정을 설정값으로 두나  ★

이 발송은 **정해진 한 PC 의 카톡**에서만 나간다 — 그 PC 에만 발송 프로그램이
붙어 있고, 스타트업 대표 방도 거기에만 있다. 그 한 사람을 코드에 적으면
(ㄱ) 이 저장소가 공개라 이름이 그대로 남고, (ㄴ) 담당이 바뀔 때마다 배포해야 한다.

그래서 **설정 한 줄**이다. 담는 표도 `auto_send_settings` 를 그대로 쓴다 —
미팅 후기 설정이 이미 `(켜짐, 어느 계정)` 을 담고 있고, 종류(`kind`)마다 한
줄이라 서로를 밟지 않는다(`models.AutoSendSetting`). 읽고 쓰는 것도
`services/auto_send.py` 의 `load`/`save` 를 그대로 부른다. 같은 표를 두 벌의
코드가 만지기 시작하면 한쪽만 고쳐지는 날이 온다.

### 다만 **때맞춰 저절로 서지는 않는다**

`auto_send.KINDS` 에 이 종류를 넣지 않는다. 넣으면 30분마다 깨어나는 실이 이
종류의 목록도 세우기 시작하는데, 이것은 **달마다 한 번 사람이 보는 일**이다 —
어느 기업에 몇 줄이 실리는지 눈으로 보고 고르는 자리라, 저절로 서면 그 확인이
사라진다. 시각·하루 상한 칸이 이 종류에서 쓰이지 않는 까닭도 같다(값은 표의
기본값 그대로 남는다).

**켜져 있다는 것은 "그 계정이 이 메뉴를 쓸 수 있다" 는 뜻일 뿐이고, 나가는 것은
사람이 진행 화면에서 [발송 시작] 을 누른 뒤다.**
"""
from __future__ import annotations

from typing import List, Optional

from sqlalchemy.orm import Session

from ..models import AutoSendSetting, IrCompany, User
from . import auto_send, ir_monthly

#: 이 발송의 종류. `auto_send_settings.kind` 이자 발송 잡의 종류
#: (`models.STARTUP_SEND_KIND`)다. **같은 것을 가리키므로 글자도 같다** —
#: 두 글자를 따로 두면 설정은 켜져 있는데 잡은 다른 이름으로 서서, 발송기가
#: 집어가지 않는 회차가 조용히 쌓인다.
KIND = "startup_ir"

#: 화면에 적는 이름. 좌측 메뉴가 아니라 딜 제안 관리 **안**의 자리라
#: `무엇을 보내는가`로 읽혀야 한다.
LABEL = "스타트업 월간 발송"

#: 못 보내는 까닭. **화면에 그대로 뜬다** — 숫자만 보여 주면 무엇을 고쳐야
#: 하는지 알 수 없다(`ir_monthly` 의 `SKIP_*` 와 같은 결).
NO_ROOM = "카톡방 이름 없음"
NO_LINES = "그 달 말까지 요청한 투자사가 없음"


# ── 누가 보낼 수 있는가 ──────────────────────────────────────────────────────

def setting(db: Session) -> Optional[AutoSendSetting]:
    """이 발송의 설정 줄. **없으면 `None` — 그것이 꺼짐이다.**"""
    return auto_send.load(db, KIND)


def is_on(row: Optional[AutoSendSetting]) -> bool:
    """켜져 있는가. 판정은 `auto_send.is_on` 한 곳이다 — 보내는 계정이 비어
    있으면 켜진 것이 아니라는 규칙까지 그대로 따른다."""
    return auto_send.is_on(row)


def sender_id(db: Session) -> Optional[int]:
    """보내기로 정한 계정. 안 정했으면 `None`."""
    row = setting(db)
    return row.user_id if is_on(row) else None


def may_send(db: Session, user: Optional[User]) -> bool:
    """이 사람이 이 메뉴를 쓸 수 있는가 — **정해진 그 한 계정만.**

    관리자도 예외가 아니다. 이 값은 권한의 높낮이가 아니라 **어느 PC 의 카톡에서
    나가는가**이고, 그것은 설정이 고른 계정 하나뿐이다(잡은 그 계정 것으로 서고
    그 계정의 기기 토큰으로만 내려간다 — `routers/agent_api.py: poll`). 관리자를
    통과시키면 관리자가 눌렀을 때 잡이 그 사람 것으로 서서 **아무 PC 도 집어가지
    않는 회차**가 된다.

    메뉴를 그리는 자리와 라우터를 막는 자리가 **이 함수 하나**를 읽는다. 둘로
    나누면 한쪽만 고쳐지는 날이 오고, 그때는 눌러야 막힌 것을 안다 — 이 저장소가
    되풀이해 고쳐 온 그 거짓말이다(`ui.can_see` 의 `needs` 설명).
    """
    if user is None:
        return False
    row = setting(db)
    return is_on(row) and row.user_id == user.id


def save(db: Session, *, enabled: bool, user_id: Optional[int]) -> AutoSendSetting:
    """설정을 저장한다. **쓰는 자리도 `auto_send.save` 하나다.**

    시각·하루 상한은 이 종류가 쓰지 않는다(머리말 참고). 그래도 그 함수를
    부르는 것은, 같은 표를 만지는 코드를 둘로 나누지 않기 위해서다 — 값은
    표의 기본값 그대로 들어간다.
    """
    return auto_send.save(db, KIND, enabled=enabled, user_id=user_id,
                          from_hour=auto_send.DEFAULT_FROM_HOUR,
                          until_hour=auto_send.DEFAULT_UNTIL_HOUR,
                          max_per_day=auto_send.DEFAULT_MAX_PER_DAY)


def status(db: Session) -> dict:
    """팀 현황이 읽는 것 — 켜졌는가 / 누가 보내는가.

    화면은 판정하지 않고 이 값을 읽는다. 같은 판단이 두 곳에 적히면 표에는
    `켜짐` 이라고 떠 있는데 메뉴는 안 보이는 상태가 생긴다.
    """
    row = setting(db)
    sender = db.get(User, row.user_id) if row and row.user_id else None
    return {
        "kind": KIND,
        "label": LABEL,
        "on": is_on(row),
        "enabled": bool(row and row.enabled),
        "sender_id": row.user_id if row else None,
        "sender": sender.name if sender else "",
    }


# ── 어느 줄이 보낼 수 있는가 ────────────────────────────────────────────────

def months(db: Session) -> List[str]:
    """고를 수 있는 달. 스타트업 화면과 **같은 목록**이다."""
    return ir_monthly.month_options(db)


def room_of(company: IrCompany) -> str:
    """이 기업 대표와의 카톡방 제목. 없으면 빈 문자열.

    앞뒤 공백을 뗀다 — 발송기는 제목이 **글자까지** 같아야 방을 찾고, 붙여
    넣을 때 딸려 온 공백 하나로 못 찾는 방이 된다.
    """
    return (company.kakao_room_name or "").strip()


def rows(db: Session, month: str) -> dict:
    """그 달에 **누구에게 무엇이 나가는가** — 누르기 전에 보는 표.

    ## 못 보내는 줄을 **빼지 않는다**  ★

    방 이름이 없는 기업도, 실을 줄이 없는 기업도 목록에 남는다. 빼 버리면
    "계약 기업인데 왜 안 보이지" 를 화면에서 물을 수가 없고, 매달 같은 기업만
    조용히 빠져도 아무도 모른다. 대신 **고를 수 없게** 하고 까닭을 적는다
    (`ir_monthly.overview` 가 요청 0곳인 기업을 남기는 것과 같은 규칙이다).

    ## 세는 것도 짓는 것도 여기가 아니다

    줄 수는 `ir_monthly.overview` 가 이미 센 값(`total_count` — **그 달 말까지
    쌓인** 수)을 그대로 쓴다. 카톡 글에 실리는 줄 수가 그것이라, 여기서 따로
    세면 화면의 수와 나가는 글의 줄 수가 갈린다.
    """
    over = ir_monthly.overview(db, month)
    out = []
    for row in over["rows"]:
        company = row["company"]
        room = room_of(company)
        # 까닭이 둘 다면 **방 이름을 먼저** 적는다. 실을 줄은 다음 달에 생길 수
        # 있지만 방 이름은 사람이 넣어 주기 전에는 영영 안 생긴다 — 손댈 수
        # 있는 쪽을 먼저 보여 준다.
        reason = ("" if room and row["msg_sendable"]
                  else NO_ROOM if not room else NO_LINES)
        out.append({
            "company": company,
            "contract_label": row["contract_label"],
            "room": room,
            # 그 달 말까지 쌓인 줄 수 — 글에 실리는 줄 수 그대로다.
            "count": row["total_count"],
            "sendable": not reason,
            "reason": reason,
        })
    return {
        "month": month,
        "rows": out,
        "sendable_count": sum(1 for r in out if r["sendable"]),
        # **방 이름이 없어 못 보내는 기업 수.** 화면이 이 수를 따로 적는다 —
        # `보낼 수 있는 곳 3` 만 보이면 나머지가 왜 빠졌는지 물을 자리가 없다.
        "no_room_count": sum(1 for r in out if r["reason"] == NO_ROOM),
        "no_lines_count": sum(1 for r in out if r["reason"] == NO_LINES),
        # 어느 기업 몫인지 몰라 어디에도 못 붙인 요청. 스타트업 화면이 이미
        # 적고 있는 값이고, 여기서도 보여야 한다 — 이 화면에서 보내는 사람은
        # 그 화면으로 돌아가지 않는다.
        "skipped": over["skipped"],
        "skipped_count": over["skipped_count"],
    }


def sendable_ids(db: Session, month: str) -> List[int]:
    """그 달에 실제로 보낼 수 있는 기업 id. **막는 자리가 읽는 것도 이것이다** —
    화면이 거른 것과 라우터가 거른 것이 갈리면, 화면에서 못 고르는 줄이 주소로는
    들어간다."""
    return [r["company"].id for r in rows(db, month)["rows"] if r["sendable"]]
