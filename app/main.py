"""FastAPI application factory (ROADMAP task 1.1)."""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from . import config, deps
from .deps import NotAdmin, NotAuthenticated
from .routers import auth as auth_router
from .routers import templates_crud
from .routers import setup as setup_router
from .routers import (agent_api, companies, consulting, contacts, dashboard,
                      data_io, deals, followups, ir, jobs, llm_brief, pages,
                      sourcing, startup)


def create_app() -> FastAPI:
    # 인터넷에 올릴 때 기본 토큰·비밀번호가 그대로면 여기서 멈춘다.
    # 저장소가 공개라 그 기본값은 이미 아무나 아는 값이다.
    config.assert_ready()

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
    app.include_router(startup.router)
    app.include_router(llm_brief.router)
    # /setup, /download 는 pages 의 캐치올(/{placeholder}) 보다 먼저 등록해야 가려지지 않는다.
    # `/startup` 도 마찬가지다 — 뒤에 두면 캐치올이 먼저 잡아 `준비 중` 안내만 뜬다.
    app.include_router(auth_router.router)
    app.include_router(templates_crud.router)
    app.include_router(setup_router.router)
    app.include_router(pages.router)

    # `_no_store` 보다 **먼저** 등록한다. 나중에 등록한 미들웨어가 바깥이라,
    # 순서를 바꾸면 여기서 바로 돌려주는 리다이렉트에 캐시 금지 헤더가 안 붙는다.
    @app.middleware("http")
    async def _consultant_guard(request: Request, call_next):
        """투자컨설턴트는 자기 화면 하나만 쓴다 — 나머지는 여기서 끊는다.

        라우터마다 검사를 흩뿌리면 새 라우터가 생길 때 빠진다(좌측 메뉴만
        걸러 두고 라우터를 안 막아서, 주소를 직접 치면 다 열려 있었다).
        미들웨어는 **나중에 붙는 라우트·마운트까지 자동으로** 지나므로
        판정이 한 곳에 남는다. 무엇을 열어 두는지는 `deps.CONSULTANT_PATHS`.
        """
        if not deps.consultant_may_open(request.url.path) and deps.is_consultant(request):
            return deps.consultant_block_response(request)
        return await call_next(request)

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

    @app.exception_handler(NotAdmin)
    def _not_admin(request: Request, exc: NotAdmin):
        """관리자 전용 — 화면 요청은 안내창이 있는 화면으로, 조작은 403 그대로.

        라우터가 아니라 여기서 답하는 이유는 컨설턴트 차단을 미들웨어 한 곳에
        둔 것과 같다: 관리자 화면이 하나 더 생겨도 `deps.admin_only` 만 부르면
        이 처리가 저절로 따라온다. 무엇을 돌려줄지는 `deps.admin_block_response`
        한 곳에 있다(컨설턴트 차단과 같은 자리, 같은 판단).
        """
        return deps.admin_block_response(request)

    @app.exception_handler(NotAuthenticated)
    def _needs_login(request: Request, exc: NotAuthenticated):
        """화면 요청은 로그인 페이지로, API 요청은 401 그대로."""
        if request.url.path.startswith("/api/"):
            return JSONResponse({"detail": exc.detail}, status_code=401)
        nxt = request.url.path or "/deals"
        return RedirectResponse(f"/login?next={nxt}", status_code=303)

    return app


app = create_app()
