from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import Annotated
from uuid import UUID

import httpx
from fastapi import FastAPI, Header, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.web.models import DemoAuditRequest, DemoAuditResult, HealthResponse
from app.web.repository import (
    AuditNotFoundError,
    AuditRepository,
    MemoryAuditRepository,
    RateLimitExceededError,
    SupabaseAuditRepository,
)
from app.web.sample import build_sample_audit
from app.web.service import AuditExecutionTimeoutError, DemoAuditService, hash_client
from app.web.settings import WebSettings, get_web_settings

logger = logging.getLogger(__name__)


def _create_repository(settings: WebSettings) -> AuditRepository:
    if settings.uses_supabase:
        return SupabaseAuditRepository(
            settings.supabase_url or "",
            settings.supabase_secret_key or "",
            settings.supabase_report_bucket,
        )
    return MemoryAuditRepository()


def create_app(
    settings: WebSettings | None = None,
    repository: AuditRepository | None = None,
) -> FastAPI:
    settings = settings or get_web_settings()
    repository = repository or _create_repository(settings)
    service = DemoAuditService(repository, settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        await repository.close()

    application = FastAPI(
        title="SEO Automation Demo API",
        version="1.0.0",
        lifespan=lifespan,
    )
    application.state.settings = settings
    application.state.audit_service = service
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.frontend_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "X-Audit-Token"],
    )

    @application.middleware("http")
    async def request_context(request: Request, call_next):
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    @application.get("/", include_in_schema=False)
    async def root() -> dict[str, str]:
        return {"service": "seo-automation-api", "health": "/api/health"}

    @application.get("/api/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        return HealthResponse(
            persistence="supabase" if settings.uses_supabase else "memory",
            demo_max_pages=settings.demo_max_pages,
        )

    @application.get("/api/v1/sample", response_model=DemoAuditResult)
    async def sample() -> DemoAuditResult:
        return build_sample_audit()

    @application.post(
        "/api/v1/audits",
        response_model=DemoAuditResult,
        status_code=status.HTTP_201_CREATED,
    )
    async def create_audit(
        payload: DemoAuditRequest,
        request: Request,
    ) -> DemoAuditResult:
        forwarded = request.headers.get("x-forwarded-for", "")
        client_ip = forwarded.split(",", 1)[0].strip() or (
            request.client.host if request.client else "unknown"
        )
        salt = settings.rate_limit_salt or "local-development-only"
        try:
            return await service.run(
                payload.website_url,
                client_hash=hash_client(client_ip, salt),
            )
        except RateLimitExceededError as exc:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Demo limit reached. Please try again in one hour.",
                headers={"Retry-After": str(int(timedelta(hours=1).total_seconds()))},
            ) from exc
        except AuditExecutionTimeoutError as exc:
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="The website did not finish within the public demo time limit.",
            ) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except httpx.HTTPError as exc:
            logger.exception(
                "demo_audit_external_failure",
                extra={"request_id": request.state.request_id},
            )
            raise HTTPException(
                status_code=502,
                detail="The audit service could not reach a required external resource.",
            ) from exc

    @application.get("/api/v1/audits/{audit_id}", response_model=DemoAuditResult)
    async def get_audit(
        audit_id: UUID,
        token: Annotated[
            str,
            Header(alias="X-Audit-Token", min_length=20, max_length=256),
        ],
    ) -> DemoAuditResult:
        try:
            return await service.get(audit_id, token)
        except AuditNotFoundError as exc:
            raise HTTPException(
                status_code=404, detail="Audit not found or expired."
            ) from exc

    @application.get("/api/v1/audits/{audit_id}/report")
    async def get_report(
        audit_id: UUID,
        token: Annotated[
            str,
            Header(alias="X-Audit-Token", min_length=20, max_length=256),
        ],
    ) -> Response:
        try:
            content = await service.get_pdf(audit_id, token)
        except AuditNotFoundError as exc:
            raise HTTPException(
                status_code=404, detail="Audit not found or expired."
            ) from exc
        return Response(
            content=content,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="seo-audit-{audit_id}.pdf"'
            },
        )

    @application.exception_handler(Exception)
    async def unhandled_error(request: Request, exc: Exception) -> JSONResponse:
        logger.exception(
            "unhandled_api_error",
            extra={"request_id": getattr(request.state, "request_id", "unknown")},
        )
        return JSONResponse(
            status_code=500,
            content={
                "detail": "Unexpected service error.",
                "request_id": request.state.request_id,
            },
        )

    return application


app = create_app()
