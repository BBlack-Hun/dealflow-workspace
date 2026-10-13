"""2단계 자동화 하나하나 — 각 모듈이 읽힐 때 공통 틀에 달린다.

틀은 `services/automation_runner.py`, 스위치는 `services/automation.py`.
여기 모듈을 하나 더하면 그것으로 그 자동화가 틀에 선다(아래 import 한 줄).
"""

from . import meeting_review  # noqa: F401,E402  A7 미팅 후 검토결과 문의
from . import meeting_request  # noqa: F401,E402  A2 미팅 요청 2회
from . import sourcing_remind  # noqa: F401,E402  A1 소싱 리마인드
