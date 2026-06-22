"""
Simple Redis-backed sliding window rate limiter.

Skipped when REDIS_ENABLED=false (minimum-cost demo deployments without Redis).
Falls back to pass-through on any Redis error to prevent API hangs.
"""

import logging
import time

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.config import settings

logger = logging.getLogger(__name__)

AUTH_PATHS = {"/api/v1/auth/login", "/api/v1/auth/register", "/api/v1/auth/password-reset"}

# Hard limit: Redis commands must complete within this many seconds or the
# middleware gives up and passes the request through.  This prevents the
# Uvicorn worker from hanging indefinitely when the Redis host is unreachable.
_REDIS_OP_TIMEOUT = 2.0


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app) -> None:
        super().__init__(app)
        self._redis = None
        if settings.REDIS_ENABLED:
            import redis.asyncio as aioredis

            self._redis = aioredis.from_url(
                settings.REDIS_URL,
                decode_responses=True,
                socket_connect_timeout=_REDIS_OP_TIMEOUT,
                socket_timeout=_REDIS_OP_TIMEOUT,
            )

    async def dispatch(self, request: Request, call_next):
        if settings.ENV == "test" or not settings.REDIS_ENABLED or self._redis is None:
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        path = request.url.path
        is_auth = any(path.startswith(p) for p in AUTH_PATHS)
        limit = settings.RATE_LIMIT_AUTH_PER_MINUTE if is_auth else settings.RATE_LIMIT_PER_MINUTE
        prefix = "auth" if is_auth else "api"
        key = f"rl:{prefix}:{client_ip}"
        now = int(time.time())
        window_start = now - 60

        try:
            pipe = self._redis.pipeline()
            pipe.zremrangebyscore(key, 0, window_start)
            pipe.zadd(key, {str(now): now})
            pipe.zcard(key)
            pipe.expire(key, 60)
            results = await pipe.execute()
            count = results[2]

            if count > limit:
                return JSONResponse(
                    status_code=429,
                    content={
                        "status": 429,
                        "error_code": "RATE_LIMIT_EXCEEDED",
                        "detail": "Too many requests. Please slow down.",
                    },
                )
        except Exception as exc:
            # Redis unavailable — degrade gracefully rather than blocking the request.
            logger.warning("RateLimitMiddleware: Redis unavailable, bypassing rate limit. error=%s", exc)

        return await call_next(request)
