"""2단계 자동화 하나하나 — 각 모듈이 읽힐 때 공통 틀에 달린다.

틀은 `services/automation_runner.py`, 스위치는 `services/automation.py`.
여기 모듈을 하나 더하면 그것으로 그 자동화가 틀에 선다(아래 import 한 줄).
"""

from . import meeting_review  # noqa: F401,E402  A7 미팅 후 검토결과 문의
from . import meeting_request  # noqa: F401,E402  A2 미팅 요청 2회
from . import sourcing_remind  # noqa: F401,E402  A1 소싱 리마인드
from . import channel_top  # noqa: F401,E402  A3 채널방 TOP·핵심 딜
from . import startup_monthly  # noqa: F401,E402  A5 스타트업 월간 발송 순환
from . import contract_day7  # noqa: F401,E402  #9 계약 Day7 우편 발송 + 문자 3회
from . import follow_round  # noqa: F401,E402  #94 · #98 후속라운드 시작 알림 3회
