from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import routes_auth, routes_chat
from app.config.logging_config import get_app_logger, setup_logging
from app.config.settings import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    get_app_logger().info("api_start", version=app.version)
    yield
    get_app_logger().info("api_stop")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Nova Ombuds Assistant API",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(routes_auth.router)
    app.include_router(routes_chat.router)

    @app.get("/health", tags=["meta"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
