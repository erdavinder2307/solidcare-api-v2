import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException

from app.config import settings
from app.core.exceptions.errors import SolidcareException
from app.core.exceptions.handlers import (
    http_exception_handler,
    solidcare_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from app.core.middleware.audit import AuditMiddleware
from app.core.middleware.tenant import TenantContextMiddleware

# Import event handlers to register them on startup
import app.core.events.handlers.notification_handler  # noqa: F401

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Solidcare API v%s starting up in %s mode", settings.APP_VERSION, settings.ENV)
    yield
    logger.info("Solidcare API shutting down")


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description="Solidcare V2 — Enterprise Healthcare Platform API",
        docs_url="/docs" if settings.is_development else None,
        redoc_url="/redoc" if settings.is_development else None,
        openapi_url="/openapi.json" if settings.is_development else None,
        lifespan=lifespan,
    )

    # ── Middleware (order matters: outermost executes first) ──────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(TenantContextMiddleware)
    app.add_middleware(AuditMiddleware)

    # ── Exception handlers ────────────────────────────────────────────────────
    app.add_exception_handler(SolidcareException, solidcare_exception_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)

    # ── Routers ───────────────────────────────────────────────────────────────
    from app.modules.appointments.router import router as appointments_router
    from app.modules.audit.router import router as audit_router
    from app.modules.auth.router import router as auth_router
    from app.modules.billing.invoices.router import router as invoices_router
    from app.modules.billing.payments.router import router as payments_router
    from app.modules.clinical.encounters.router import router as encounters_router
    from app.modules.doctors.router import router as doctors_router
    from app.modules.notifications.router import router as notifications_router
    from app.modules.patients.router import router as patients_router
    from app.modules.prescriptions.router import router as prescriptions_router
    from app.modules.reports.router import router as reports_router

    prefix = settings.API_V1_PREFIX

    app.include_router(auth_router, prefix=prefix)
    app.include_router(patients_router, prefix=prefix)
    app.include_router(doctors_router, prefix=prefix)
    app.include_router(appointments_router, prefix=prefix)
    app.include_router(encounters_router, prefix=prefix)
    app.include_router(prescriptions_router, prefix=prefix)
    app.include_router(invoices_router, prefix=prefix)
    app.include_router(payments_router, prefix=prefix)
    app.include_router(notifications_router, prefix=prefix)
    app.include_router(reports_router, prefix=prefix)
    app.include_router(audit_router, prefix=prefix)

    @app.get("/health", tags=["Health"])
    async def health_check() -> dict:
        return {"status": "healthy", "version": settings.APP_VERSION, "env": settings.ENV}

    return app


app = create_app()
