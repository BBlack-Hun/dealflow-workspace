"""FastAPI application factory (ROADMAP task 1.1)."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from . import config
from .routers import setup as setup_router
from .routers import agent_api, contacts, deals, jobs, pages


def create_app() -> FastAPI:
    app = FastAPI(title="dealflow", version="0.1.0 (Sprint 1)")

    app.mount("/static", StaticFiles(directory=str(config.STATIC_DIR)), name="static")

    @app.get("/health", include_in_schema=False)
    def health():
        return {"status": "ok", "app": "dealflow", "sprint": 1}

    # API routers first (explicit prefixes), then HTML pages (which include a catch-all stub).
    app.include_router(deals.router)
    app.include_router(contacts.router)
    app.include_router(jobs.router)
    app.include_router(agent_api.router)
    # /setup, /download 는 pages 의 캐치올(/{placeholder}) 보다 먼저 등록해야 가려지지 않는다.
    app.include_router(setup_router.router)
    app.include_router(pages.router)

    return app


app = create_app()
