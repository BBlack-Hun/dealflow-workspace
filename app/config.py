"""Application configuration.

All values are read from environment variables with sensible local defaults.
Kakao automation numbers (delays / caps) live in the agent's config.yaml — NOT here —
per ROADMAP "스프린트 공통 원칙 2" (no hardcoded send-rate constants).
"""
from __future__ import annotations

import os
from pathlib import Path

# Project root: .../dealflow
BASE_DIR = Path(__file__).resolve().parent.parent

# SQLite file (WAL mode enabled in db.py). Override with DATABASE_URL for Postgres later.
DATA_DIR = Path(os.environ.get("DEALFLOW_DATA_DIR", BASE_DIR / "data"))
DEFAULT_DB_PATH = DATA_DIR / "dealflow.db"
DATABASE_URL = os.environ.get("DATABASE_URL", f"sqlite:///{DEFAULT_DB_PATH}")

# Sprint 1: single hardcoded user session (auth is Sprint 4).
CURRENT_USER_ID = int(os.environ.get("DEALFLOW_CURRENT_USER_ID", "1"))

# 데모 데이터(가상 담당자·기업·사용자)를 넣을지. 기본은 끈다 — 실데이터가 들어간 뒤
# 컨테이너를 다시 띄웠다가 화면에 샘플 기업이 섞여 보인 적이 있다.
SEED_DEMO = os.getenv("DEALFLOW_SEED_DEMO", "0") == "1"

# Demo agent token seeded into agent_devices and shared with the mock agent container.
DEMO_AGENT_TOKEN = os.environ.get("DEALFLOW_AGENT_TOKEN", "agt_demo_token_sprint1")

# An agent is considered "connected" if it polled/heartbeat within this many seconds.
AGENT_ONLINE_WINDOW_SEC = int(os.environ.get("DEALFLOW_AGENT_ONLINE_WINDOW_SEC", "30"))

# Message length warning threshold (FEATURE_SPEC §5: 카톡 장문 붙여넣기 안정성).
MESSAGE_WARN_CHARS = 3000

# 신규 계정의 초기 비밀번호. 전원 동일하게 발급하고, 첫 로그인 시 변경을 강제한다
# (must_change_password=1). 운영에서는 반드시 .env 로 바꿔서 쓸 것.
INITIAL_PASSWORD = os.environ.get("DEALFLOW_INITIAL_PASSWORD", "dealflow123")

# ── 테스트 모드 ───────────────────────────────────────────────────────────────
# 값이 있으면 **모든 발송이 이 카톡방 하나로만** 나간다(실제 담당자 방으로 가지 않음).
# 실투자사 150명에게 실수로 발송되는 사고를 막기 위한 안전장치.
# 예: DEALFLOW_TEST_ROOM="김정훈"  (나와의 채팅)
# 비워두면 평소대로 각 담당자의 방으로 발송된다.
TEST_ROOM = os.environ.get("DEALFLOW_TEST_ROOM", "").strip()

STATIC_DIR = BASE_DIR / "app" / "static"
TEMPLATES_DIR = BASE_DIR / "app" / "templates"
