"""자료 파일을 **발송기가 붙여 보내는가**, 사람이 손으로 붙이는가.

두 길이 함께 산다.

    자동 첨부   발송기가 파일을 먼저 보내고 → 문구 한 통      (잡에 파일명이 실린다)
    손 첨부     사람이 PC 카톡에서 붙이고 → 앱은 문구만        (지금까지의 동작)

## 어떻게 가르나 — **관리자가 켜 준 계정**이, **자기 PC 의 폴더를 정해 두었을 때**

질문이 둘이고, 답하는 자리도 둘이다.

    쓸 수 있는가   `users.can_auto_attach_ir`   관리자가 팀 현황에서 켠다 (0059)
    지금 켜졌는가  `agent_devices.ir_root`      본인이 `/setup` 에서 넣는다 (0055)

계정을 이름으로 박지 않는다. 사람 이름을 코드에 적으면 사람이 바뀌는 날
낡고, 낡은 줄 아무도 모른다. 이 저장소가 권한을 다루는 결(계정별 칸 + 팀
현황의 켜고 끄기)을 그대로 따른다 — `users.can_view_consulting` 과 같은 자리,
같은 모양이다(판정은 `deps.may_auto_attach` 한 곳).

### 왜 폴더 칸 하나로는 안 되는가

예전에는 `ir_root` 가 찼는가만 보았다. 그 칸이 이 기능을 위해서만 생겼으니
채운 것이 곧 "자료는 발송기에 맡기겠다" 는 뜻이라고 읽은 것인데, **그 칸은
본인이 넣는다**(`app/routers/setup.py: save_ir_root`). 즉 문이 곧 스위치라
**누구든 스스로 켤 수 있었다.** 이 기능은 정해진 사람만 쓰는데 그 사람을 가릴
자리가 코드에 없었다.

이제 `ir_root` 는 **"어느 폴더인가"** 라는 제 뜻만 진다. **"쓸 수 있는가"** 는
관리자가 정하고, 꺼진 계정에서는 그 폴더를 **읽지 않는다** — 지우지는 않으므로
다시 켜면 넣어 둔 값이 그대로 되돌아온다.

### 폴더 칸을 여전히 함께 보는 이유

**없으면 어차피 못 보낸다.** 폴더를 모르면 발송기는 파일을 한 개도 찾을 수
없다(`agent/sender/base.py: ir_root` 가 분명히 실패한다). 켜 주기만 하고 아직
폴더를 안 넣은 계정을 켜진 것으로 치면 **자료 없이 문구만 나간다.** 그래서
두 칸을 `and` 로 묶는다. 문을 잘못 열어도 그 사고는 생기지 않는다 — 파일이
하나라도 실패하면 발송기가 문구를 보내지 않는다(`agent/main.py: send_item`).

### 붙어 있는 발송기 종류(`agent_devices.sender`)로 가르지 않는 이유

파일 전송은 지금 macOS 에서만 확인됐다. 그래서 `sender == "kakao_mac"` 을
조건에 넣고 싶어지는데, **그러면 제일 나쁜 실패가 생긴다.** 그 칸은 발송기가
붙어야 채워진다 — 아직 한 번도 안 켠 PC 는 비어 있다. 조건에 넣으면 그 사람의
자료 전달은 **파일 없이 문구만** 나가고("자료 보내드렸습니다" 만 가고 자료가
없다), 사람은 자기가 켜 둔 줄 알고 있다.

지금처럼 두면 그 자리는 **분명한 실패**가 된다 — 지원하지 않는 발송기는
`file_send_unsupported` 로 거절하고 문구도 안 나간다. 조용히 반쪽만 나가는
것보다 낫다.
"""
from __future__ import annotations

import json
from datetime import date
from typing import List, Optional, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..deps import may_auto_attach
from ..models import AgentDevice, ContactActivity, User


def auto_attach_enabled(db: Session, user: User) -> bool:
    """이 계정의 자료 전달에 **파일을 실어 보내는가.**

    판단은 한 곳(이 함수)뿐이다. 발송 목록을 만드는 자리·미리보기·첨부 안내창이
    전부 여기를 묻는다 — 세 곳이 따로 판단하면 안내창은 뜨는데 파일도 나가는
    (또는 그 반대의) 어긋난 화면이 생긴다.

    **권한을 먼저 본다.** 관리자가 켜 주지 않은 계정에서는 폴더 칸을 아예 읽지
    않는다 — 예전에 넣어 둔 값이 남아 있어도(끄면서 지우지 않는다) 그것으로
    되살아나면 안 된다. 위 머리말의 두 질문이 여기 두 줄로 서 있다.
    """
    if not may_auto_attach(user):
        return False
    root = db.execute(
        select(AgentDevice.ir_root).where(AgentDevice.user_id == user.id)
    ).scalar_one_or_none()
    return bool((root or "").strip())


def file_names(companies: Sequence) -> List[str]:
    """붙여 보낼 파일명 — **받은 차례 그대로.**

    문구가 기업을 짚는 차례이자 발송기가 파일을 보내는 차례다. 여기서 다시
    정렬하면 문구의 차례와 파일의 차례가 갈린다.

    차례를 정하는 것은 부르는 쪽이다 — 자료 전달은 **번호 오름차순**으로 세운
    목록을 넘긴다(`routers/deals.py` 의 `ir_order`).
    """
    return [name for name in ((c.ir_file_name or "").strip() for c in companies)
            if name]


def missing_files(companies: Sequence) -> List[str]:
    """자료 파일명이 **비어 있는** 기업 이름들. 비었으면 붙일 것이 없다."""
    return [c.name for c in companies if not (c.ir_file_name or "").strip()]


# ── 활동 이력 ───────────────────────────────────────────────────────────────
#
# 자료 전달은 **누가 언제 어느 기업 자료를 보냈는가**가 나중에 필요한 일이라,
# 담당자 이력에 한 줄을 남긴다.
#
# ## 언제 남기나 — **보낸 때**다 (누른 때가 아니다)
#
# 예전에는 IR 진행 관리의 [자료 보내기] 를 **누른 순간** 남겼다. 그때는 그
# 단추가 화면을 발송 화면으로 옮기는 일만 해서, 옮겨 간 뒤에 무슨 일이 있었는지
# 여기서는 알 수 없었기 때문이다.
#
# 그런데 그 자리에서 끝내는 흐름(`static/js/ir_send.js`)이 되면서 누른 것과
# 보낸 것 사이가 더 벌어졌다 — 창을 열어 문구만 확인하고 닫는 것이 자연스러운
# 동작이 됐다. 누른 때 적으면 **보내지도 않은 건이 '자료 보냄' 으로 남는다.**
# 이력을 훑는 목적이 "이 사람에게 뭘 보냈나" 인데 거기에 안 보낸 것이 섞이면,
# 그 목록으로는 아무것도 판단할 수 없다.
#
# 그래서 **발송 목록이 만들어질 때** 적는다(`routers/deals.py`
# `create_send_list`). 그 자리는 IR 진행 관리의 창과 딜 제안 관리가 **함께
# 지나는 한 곳**이라, 어느 화면에서 보내도 같은 줄이 남는다 — 예전에는 딜 제안
# 관리에서 바로 보내면 이 줄이 아예 없었다.
#
# 발송이 실패하면 그 사실은 발송 건 자체가 이력에 들고 온다(`routers/contacts.py`
# 의 `_send_summary` — `IR 전달 실패 — …`). 여기서 또 지우고 다시 쓰면 두 곳이
# 같은 사실을 서로 다르게 말하게 된다.

#: 사람이 PC 카톡에서 파일을 직접 붙인 건.
ATTACH_ON_PC = "IR 자료 전달 — PC 에서 직접 첨부"
#: 발송기가 파일을 실어 보낸 건(자료 폴더를 정해 둔 계정).
ATTACH_BY_SENDER = "IR 자료 전달 — 발송 프로그램이 첨부"


def record_delivery(db: Session, contact_id: int, company_names: Sequence[str],
                    by_sender: bool = False,
                    when: Optional[date] = None) -> bool:
    """이 담당자에게 IR 자료를 보냈다고 이력에 적는다. 새로 적었으면 `True`.

    **두 번 눌러도 한 줄이다.** 같은 날 · 같은 담당자 · 같은 기업 묶음이면
    다시 적지 않는다 — 같은 줄이 두 번 쌓이면 이력이 아니라 소음이고, 실패해서
    다시 보내는 것은 흔한 일이다.

    `by_sender` 는 **자료를 누가 붙였는가**다. 자동 첨부를 켠 계정은 발송기가
    파일을 실어 보내고, 그 밖에는 사람이 PC 카톡에서 붙인다 — 나중에 되짚을 때
    다른 일이라 말이 달라야 한다. 판단 자체는 `auto_attach_enabled` 한 곳이고
    여기서 다시 하지 않는다(부르는 쪽이 실제로 파일을 실었는지를 넘겨준다).
    """
    day = (when or date.today()).isoformat()
    payload = json.dumps([str(n) for n in company_names], ensure_ascii=False)
    already = db.execute(
        select(ContactActivity).where(
            ContactActivity.contact_id == contact_id,
            ContactActivity.kind == "ir_delivery",
            ContactActivity.happened_at == day,
            ContactActivity.company_names == payload)
    ).scalars().first()
    if already is not None:
        return False
    db.add(ContactActivity(
        contact_id=contact_id, kind="ir_delivery", source="system",
        content=ATTACH_BY_SENDER if by_sender else ATTACH_ON_PC,
        happened_at=day, month=day[:7],
        company_names=payload, company_count=len(company_names) or None))
    return True
