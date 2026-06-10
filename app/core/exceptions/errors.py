from http import HTTPStatus


class SolidcareException(Exception):
    """Base exception for all application errors."""

    status_code: int = 500
    error_code: str = "INTERNAL_ERROR"

    def __init__(self, detail: str = "An unexpected error occurred") -> None:
        self.detail = detail
        super().__init__(detail)


class ValidationError(SolidcareException):
    status_code = 422
    error_code = "VALIDATION_ERROR"


class NotFoundError(SolidcareException):
    status_code = 404
    error_code = "NOT_FOUND"

    def __init__(self, resource: str = "Resource", identifier: str = "") -> None:
        detail = f"{resource} not found"
        if identifier:
            detail = f"{resource} '{identifier}' not found"
        super().__init__(detail)


class UnauthorizedError(SolidcareException):
    status_code = 401
    error_code = "UNAUTHORIZED"

    def __init__(self, detail: str = "Authentication required") -> None:
        super().__init__(detail)


class ForbiddenError(SolidcareException):
    status_code = 403
    error_code = "FORBIDDEN"

    def __init__(self, detail: str = "You do not have permission to perform this action") -> None:
        super().__init__(detail)


class ConflictError(SolidcareException):
    status_code = 409
    error_code = "CONFLICT"


class BusinessRuleError(SolidcareException):
    status_code = 422
    error_code = "BUSINESS_RULE_VIOLATION"


class TenantError(SolidcareException):
    status_code = 403
    error_code = "TENANT_ERROR"
