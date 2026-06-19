"""
ArchPilot — FastAPI Application Entry Point

Startup sequence:
1. Configure logging
2. Initialize DB (create tables)
3. Mount API routes
4. Register middleware
5. Start serving

Lifespan pattern (FastAPI 0.95+): replaces deprecated @app.on_event handlers.
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse

from app.api.routes.repositories import router as repo_router
from app.core.config import settings
from app.core.logging import get_logger, setup_logging
from app.db.database import close_db, init_db

setup_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan: startup → serve → shutdown."""
    logger.info(
        "archpilot.startup",
        version=settings.APP_VERSION,
        environment=settings.ENVIRONMENT,
    )

    await init_db()
    logger.info("archpilot.db_ready")

    yield  # Application runs here

    logger.info("archpilot.shutdown")
    await close_db()


app = FastAPI(
    title=settings.APP_NAME,
    description=(
        "Repository Architecture Intelligence Platform. "
        "Analyzes codebases using graph algorithms to answer: "
        "what breaks, what's coupled, what's risky."
    ),
    version=settings.APP_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# ─── Middleware ───────────────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(GZipMiddleware, minimum_size=1000)

# ─── Routes ───────────────────────────────────────────────────────────────────

app.include_router(
    repo_router,
    prefix=settings.API_V1_PREFIX,
    tags=["repositories"],
)


# ─── Health Endpoints ─────────────────────────────────────────────────────────

@app.get("/health", tags=["system"])
async def health_check() -> JSONResponse:
    return JSONResponse(
        content={
            "status": "healthy",
            "app": settings.APP_NAME,
            "version": settings.APP_VERSION,
            "environment": settings.ENVIRONMENT,
        }
    )


@app.get("/", tags=["system"])
async def root() -> JSONResponse:
    return JSONResponse(
        content={
            "name": settings.APP_NAME,
            "description": "Repository Architecture Intelligence Platform",
            "docs": "/docs",
            "health": "/health",
            "api": settings.API_V1_PREFIX,
        }
    )
