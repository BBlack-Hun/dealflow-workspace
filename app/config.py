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

# Demo agent token seeded into agent_devices and shared with the mock agent container.
DEMO_AGENT_TOKEN = os.environ.get("DEALFLOW_AGENT_TOKEN", "agt_demo_token_sprint1")

# An agent is considered "connected" if it polled/heartbeat within this many seconds.
AGENT_ONLINE_WINDOW_SEC = int(os.environ.get("DEALFLOW_AGENT_ONLINE_WINDOW_SEC", "30"))

# Message length warning threshold (FEATURE_SPEC §5: 카톡 장문 붙여넣기 안정성).
MESSAGE_WARN_CHARS = 3000

STATIC_DIR = BASE_DIR / "app" / "static"
TEMPLATES_DIR = BASE_DIR / "app" / "templates"
