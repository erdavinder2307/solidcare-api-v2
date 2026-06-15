import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException

# Import event handlers to register them on startup
import app.core.events.handlers.notification_handler  # noqa: F401
import app.register_models  # noqa: F401 — register all SQLAlchemy mappers
from app.config import settings
from app.core.exceptions.errors import SolidcareException
from app.core.exceptions.handlers import (
    http_exception_handler,
    solidcare_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from app.core.middleware.audit import AuditMiddleware
from app.core.middleware.rate_limit import RateLimitMiddleware
from app.core.middleware.tenant import TenantContextMiddleware

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Solidcare API v%s starting up in %s mode", settings.APP_VERSION, settings.ENV)
    # Security warning for insecure JWT secret outside production
    _insecure = {"CHANGE_ME_IN_PRODUCTION", "CHANGE_ME_IN_PRODUCTION_use_openssl_rand_hex_64", "secret", "changeme"}
    if settings.JWT_SECRET_KEY in _insecure or len(settings.JWT_SECRET_KEY) < 32:
        logger.warning(
            "⚠️  JWT_SECRET_KEY is insecure. Run: openssl rand -hex 64  and set it in .env"
        )
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
    app.add_middleware(AuditMiddleware)
    app.add_middleware(TenantContextMiddleware)
    app.add_middleware(RateLimitMiddleware)

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
    from app.modules.billing.service_charges.router import router as service_charges_router
    from app.modules.clinical.encounters.router import router as encounters_router
    from app.modules.clinical.icd10.router import router as icd10_router
    from app.modules.clinical.lab_orders.router import router as lab_orders_router
    from app.modules.clinics.router import router as clinics_router
    from app.modules.doctors.router import router as doctors_router
    from app.modules.medicines.router import router as medicines_router
    from app.modules.notifications.router import router as notifications_router
    from app.modules.organizations.router import router as organizations_router
    from app.modules.patients.router import router as patients_router
    from app.modules.prescriptions.router import router as prescriptions_router
    from app.modules.reports.router import router as reports_router
    from app.modules.users.router import router as users_router

    prefix = settings.API_V1_PREFIX

    app.include_router(auth_router, prefix=prefix)
    app.include_router(patients_router, prefix=prefix)
    app.include_router(doctors_router, prefix=prefix)
    app.include_router(appointments_router, prefix=prefix)
    app.include_router(encounters_router, prefix=prefix)
    app.include_router(icd10_router, prefix=prefix)
    app.include_router(lab_orders_router, prefix=prefix)
    app.include_router(prescriptions_router, prefix=prefix)
    app.include_router(invoices_router, prefix=prefix)
    app.include_router(payments_router, prefix=prefix)
    app.include_router(service_charges_router, prefix=prefix)
    app.include_router(notifications_router, prefix=prefix)
    app.include_router(reports_router, prefix=prefix)
    app.include_router(audit_router, prefix=prefix)
    app.include_router(clinics_router, prefix=prefix)
    app.include_router(organizations_router, prefix=prefix)
    app.include_router(medicines_router, prefix=prefix)
    app.include_router(users_router, prefix=prefix)

    @app.get("/health", tags=["Health"])
    async def health_check() -> dict:
        from sqlalchemy import text

        from app.database import AsyncSessionLocal

        db_status = "unconfigured"
        storage_status = "unconfigured"

        # 1. Check Database Connectivity
        try:
            async with AsyncSessionLocal() as session:
                await session.execute(text("SELECT 1"))
                db_status = "connected"
        except Exception as e:
            db_status = f"error: {str(e)}"
            logger.error("Health check database connection failed: %s", str(e))

        # 2. Check Blob Storage Connectivity (optional; skipped in test)
        if settings.ENV == "test":
            storage_status = "skipped"
        elif settings.AZURE_STORAGE_CONNECTION_STRING:
            try:
                from azure.storage.blob.aio import BlobServiceClient
                async with BlobServiceClient.from_connection_string(
                    settings.AZURE_STORAGE_CONNECTION_STRING
                ) as client:
                    container = client.get_container_client(settings.AZURE_STORAGE_CONTAINER_NAME)
                    await container.get_container_properties()
                    storage_status = "connected"
            except Exception as e:
                storage_status = f"error: {str(e)}"
                logger.error("Health check Azure Blob connection failed: %s", str(e))
        else:
            storage_status = "disabled"

        overall_status = "healthy" if db_status == "connected" and (
            storage_status in ("connected", "disabled", "skipped")
        ) else "degraded" if db_status == "connected" else "unhealthy"

        return {
            "status": overall_status,
            "version": settings.APP_VERSION,
            "env": settings.ENV,
            "checks": {
                "database": db_status,
                "storage": storage_status,
            }
        }

    return app


app = create_app()
