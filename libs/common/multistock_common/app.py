import logging
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from .settings import BaseServiceSettings


def create_app(settings: BaseServiceSettings, title: str, version: str = "1.0.0") -> FastAPI:
    settings.assert_production_safe()
    logging.basicConfig(
        level=logging.INFO,
        format=f'{{"ts":"%(asctime)s","service":"{settings.service_name}","level":"%(levelname)s","logger":"%(name)s","msg":"%(message)s"}}',
    )
    app = FastAPI(title=title, version=version, docs_url="/docs", openapi_url="/openapi.json")
    app.state.settings = settings
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    access_log = logging.getLogger("access")

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
        start = time.perf_counter()
        response = await call_next(request)
        response.headers["x-request-id"] = request_id
        access_log.info(
            "%s %s %s %.1fms rid=%s",
            request.method,
            request.url.path,
            response.status_code,
            (time.perf_counter() - start) * 1000,
            request_id,
        )
        return response

    @app.get("/health", tags=["ops"])
    def health():
        return {"status": "ok", "service": settings.service_name}

    return app
