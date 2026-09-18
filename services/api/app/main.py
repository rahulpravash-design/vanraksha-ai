"""Application factory and lifecycle."""

from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from . import __version__
from .config import get_settings
from .db import Base, engine
from .routers import analytics, auth, cases, livestock, reports, surveillance

logger = logging.getLogger("vanraksha.api")
settings = get_settings()

API_PREFIX = "/api/v1"

DESCRIPTION = """
Field-to-response intelligence for livestock health.

Reports from farmers and field workers are normalised against a clinical
taxonomy, triaged by an explainable rule engine, checked against live
geo-temporal clusters, and routed to the veterinary staff who can act on them.

**This API supports decisions; it does not make clinical ones.** It does not
diagnose disease and it does not recommend treatments or doses. It identifies
syndromic patterns, scores urgency, detects clusters, and routes work.
"""


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.validate_for_runtime()
    # Suitable for development and the demo dataset. Deployments run Alembic
    # migrations instead -- see database/migrations.
    Base.metadata.create_all(bind=engine)
    logger.info("VANRAKSHA API %s started in %s mode", __version__, settings.environment)
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="VANRAKSHA AI",
        description=DESCRIPTION,
        version=__version__,
        lifespan=lifespan,
        docs_url="/docs",
        openapi_url=f"{API_PREFIX}/openapi.json",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        """Attach a request id and duration to every response.

        Field devices retry on flaky connections; when a farmer reports a
        submission that did not appear, the request id is what makes it
        traceable through the logs.
        """
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        started = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - started) * 1000
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Response-Time-ms"] = f"{elapsed_ms:.1f}"
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError):
        """Return field-level messages a form can render next to the input.

        A farmer filling in a report on a phone needs to know which field is
        wrong, not that the payload failed validation.
        """
        errors = [
            {
                "field": ".".join(str(part) for part in err["loc"][1:]) or "body",
                "message": err["msg"],
            }
            for err in exc.errors()
        ]
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"detail": "Some fields need attention.", "errors": errors},
        )

    @app.exception_handler(IntegrityError)
    async def integrity_handler(request: Request, exc: IntegrityError):
        logger.warning("integrity error on %s: %s", request.url.path, exc)
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"detail": "That record conflicts with one that already exists."},
        )

    @app.exception_handler(SQLAlchemyError)
    async def database_handler(request: Request, exc: SQLAlchemyError):
        # Never leak SQL or schema details to a client.
        logger.exception("database error on %s", request.url.path)
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"detail": "The service is temporarily unavailable. Please retry."},
        )

    for module in (auth, reports, livestock, cases, surveillance, analytics):
        app.include_router(module.router, prefix=API_PREFIX)

    @app.get("/health", tags=["meta"])
    def health() -> dict:
        return {"status": "ok", "version": __version__, "environment": settings.environment}

    @app.get("/", tags=["meta"])
    def root() -> dict:
        return {
            "name": "VANRAKSHA AI",
            "version": __version__,
            "docs": "/docs",
            "api": API_PREFIX,
            "notice": (
                "Decision support for livestock health surveillance. "
                "Not a diagnostic or prescribing system."
            ),
        }

    return app


app = create_app()
