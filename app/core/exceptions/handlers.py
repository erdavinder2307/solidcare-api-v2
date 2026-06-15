import logging
from datetime import UTC, datetime

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from app.core.exceptions.errors import SolidcareException

logger = logging.getLogger(__name__)


def _problem_detail(
    status: int,
    error_code: str,
    detail: str,
    request: Request,
    errors: list | None = None,
) -> dict:
    body = {
        "status": status,
        "error_code": error_code,
        "detail": detail,
        "path": str(request.url.path),
        "timestamp": datetime.now(UTC).isoformat(),
    }
    if errors:
        body["errors"] = errors
    return body


async def solidcare_exception_handler(
    request: Request, exc: SolidcareException
) -> JSONResponse:
    if exc.status_code >= 500:
        logger.exception("Internal error: %s", exc.detail)
    return JSONResponse(
        status_code=exc.status_code,
        content=_problem_detail(exc.status_code, exc.error_code, exc.detail, request),
    )


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=_problem_detail(exc.status_code, "HTTP_ERROR", str(exc.detail), request),
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    errors = [
        {
            "field": ".".join(str(loc) for loc in error["loc"][1:]),
            "message": error["msg"],
            "type": error["type"],
        }
        for error in exc.errors()
    ]
    return JSONResponse(
        status_code=422,
        content=_problem_detail(
            422, "VALIDATION_ERROR", "Request validation failed", request, errors
        ),
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled exception: %s", exc)
    return JSONResponse(
        status_code=500,
        content=_problem_detail(500, "INTERNAL_ERROR", "An unexpected error occurred", request),
    )
