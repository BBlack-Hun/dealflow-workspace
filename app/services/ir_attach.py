"""자료 파일을 **발송기가 붙여 보내는가**, 사람이 손으로 붙이는가.

두 길이 함께 산다.

    자동 첨부   발송기가 파일을 먼저 보내고 → 문구 한 통      (잡에 파일명이 실린다)
    손 첨부     사람이 PC 카톡에서 붙이고 → 앱은 문구만        (지금까지의 동작)

## 어떻게 가르나 — **자기 PC 의 자료 폴더를 정해 둔 계정만** 자동 첨부

계정을 이름으로 박지 않는다. 사람 이름을 코드에 적으면 사람이 바뀌는 날
낡고, 낡은 줄 아무도 모른다. 이 저장소가 권한을 다루는 결(계정별 칸)을
그대로 따른다 — 다만 **새 칸을 파지 않는다.** 이미 있는 칸 하나가 이 질문에
정확히 답하기 때문이다: `agent_devices.ir_root`(0055).

그 칸은 "이 PC 의 어느 폴더에 자료가 있는가" 이고, **본인만 넣는다**
(`app/routers/setup.py: save_ir_root`). 그리고 그 칸이 이 기능을 위해서만
생겼다 — 다른 쓰임이 없다. 그러니 그 칸을 채운 것이 곧 **"자료는 발송기에
맡기겠다"** 는 뜻이다.

### 왜 이 칸이 가장 안전한 문인가

**없으면 어차피 못 보낸다.** 폴더를 모르면 발송기는 파일을 한 개도 찾을 수
없다(`agent/sender/base.py: ir_root` 가 분명히 실패한다). 즉 이 문은 "될 수도
있는 것을 막는 문" 이 아니라 **"안 될 것이 확실한 길을 안 여는 문"** 이다.
문을 잘못 열어도 문구가 자료 없이 나가는 일은 생기지 않는다 — 파일이 하나라도
실패하면 발송기가 문구를 보내지 않는다(`agent/main.py: send_item`).

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

from typing import List, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import AgentDevice, User


def auto_attach_enabled(db: Session, user: User) -> bool:
    """이 계정의 자료 전달에 **파일을 실어 보내는가.**

    판단은 한 곳(이 함수)뿐이다. 발송 목록을 만드는 자리·미리보기·첨부 안내창이
    전부 여기를 묻는다 — 세 곳이 따로 판단하면 안내창은 뜨는데 파일도 나가는
    (또는 그 반대의) 어긋난 화면이 생긴다.
    """
    root = db.execute(
        select(AgentDevice.ir_root).where(AgentDevice.user_id == user.id)
    ).scalar_one_or_none()
    return bool((root or "").strip())


def file_names(companies: Sequence) -> List[str]:
    """붙여 보낼 파일명 — **고른 차례 그대로.**

    문구가 기업을 짚는 차례이자 발송기가 파일을 보내는 차례다. 여기서 다시
    정렬하면 문구의 차례와 파일의 차례가 갈린다.
    """
    return [name for name in ((c.ir_file_name or "").strip() for c in companies)
            if name]


def missing_files(companies: Sequence) -> List[str]:
    """자료 파일명이 **비어 있는** 기업 이름들. 비었으면 붙일 것이 없다."""
    return [c.name for c in companies if not (c.ir_file_name or "").strip()]
