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
                      data_io, deals, followups, ir, jobs, pages, sourcing)


def create_app() -> FastAPI:
    app = FastAPI(title="dealflow", version="0.1.0 (Sprint 1)")

    app.mount("/static", StaticFiles(directory=str(config.STATIC_DIR)), name="static")

    @app.get("/health", include_in_schema=False)
    def health():
        return {"status": "ok", "app": "dealflow", "sprint": 1}

    # API routers first (explicit prefixes), then HTML pages (which include a catch-all stub).
    app.include_router(deals.router)
    app.include_router(contacts.router)
    app.include_router(contacts.ref_router)
    app.include_router(jobs.router)
    app.include_router(agent_api.router)
    app.include_router(data_io.router)
    app.include_router(companies.router)
    app.include_router(dashboard.router)
    app.include_router(consulting.router)
    app.include_router(followups.router)
    app.include_router(ir.router)
    app.include_router(sourcing.router)
    # /setup, /download 는 pages 의 캐치올(/{placeholder}) 보다 먼저 등록해야 가려지지 않는다.
    app.include_router(auth_router.router)
    app.include_router(templates_crud.router)
    app.include_router(setup_router.router)
    app.include_router(pages.router)

    @app.middleware("http")
    async def _no_store(request: Request, call_next):
        """화면과 API 응답을 브라우저가 캐시하지 못하게 한다.

        투자사 관리 현황 에서 값을 고치고 대시보드로 돌아오면 예전 숫자가 보였다.
        서버는 매번 새로 계산하는데 브라우저가 캐시(뒤로가기 포함)를 내준 것이다.
        로그인이 필요한 화면이 캐시에 남는 것도 좋지 않다 — 로그아웃한 뒤
        뒤로가기로 다시 보일 수 있다.

        `/static/` 은 **오래** 캐시한다. 주소에 파일 내용 지문이 붙어 있어서
        (`?v=3f2a91c4`, app/assets.py) 내용이 바뀌면 주소가 달라진다 —
        낡은 파일을 계속 쓰는 일이 없다. 지문 없이 직접 부른 주소만 조심하면
        되므로, 그때는 짧게 잡는다.
        """
        response = await call_next(request)
        if not request.url.path.startswith("/static/"):
            response.headers["Cache-Control"] = "no-store, must-revalidate"
        elif request.url.query.startswith("v="):
            # 지문이 붙었다 — 내용이 바뀌면 주소가 바뀌므로 오래 둬도 안전하다.
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        else:
            # 지문 없이 부른 주소. 고친 것이 안 보이는 쪽이 느린 것보다 나쁘다.
            response.headers["Cache-Control"] = "no-cache"
        return response

    @app.exception_handler(NotAuthenticated)
    def _needs_login(request: Request, exc: NotAuthenticated):
        """화면 요청은 로그인 페이지로, API 요청은 401 그대로."""
        if request.url.path.startswith("/api/"):
            return JSONResponse({"detail": exc.detail}, status_code=401)
        nxt = request.url.path or "/deals"
        return RedirectResponse(f"/login?next={nxt}", status_code=303)

    return app


app = create_app()
