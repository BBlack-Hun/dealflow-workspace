"""FastAPI application factory (ROADMAP task 1.1)."""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from . import config
from .deps import NotAuthenticated
from .routers import auth as auth_router
from .routers import templates_crud
from .routers import setup as setup_router
from .routers import (agent_api, companies, consulting, contacts, dashboard,
                      data_io, deals, followups, jobs, pages)


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
    app.include_router(data_io.router)
    app.include_router(companies.router)
    app.include_router(dashboard.router)
    app.include_router(consulting.router)
    app.include_router(followups.router)
    # /setup, /download 는 pages 의 캐치올(/{placeholder}) 보다 먼저 등록해야 가려지지 않는다.
    app.include_router(auth_router.router)
    app.include_router(templates_crud.router)
    app.include_router(setup_router.router)
    app.include_router(pages.router)

    @app.exception_handler(NotAuthenticated)
    def _needs_login(request: Request, exc: NotAuthenticated):
        """화면 요청은 로그인 페이지로, API 요청은 401 그대로."""
        if request.url.path.startswith("/api/"):
            return JSONResponse({"detail": exc.detail}, status_code=401)
        nxt = request.url.path or "/deals"
        return RedirectResponse(f"/login?next={nxt}", status_code=303)

    return app


app = create_app()
