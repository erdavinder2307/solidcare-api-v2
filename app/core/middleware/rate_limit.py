"""
Simple Redis-backed sliding window rate limiter.
"""

import time

import redis.asyncio as aioredis
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.config import settings

AUTH_PATHS = {"/api/v1/auth/login", "/api/v1/auth/register", "/api/v1/auth/password-reset"}


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, redis_url: str = settings.REDIS_URL) -> None:
        super().__init__(app)
        self._redis = aioredis.from_url(redis_url, decode_responses=True)

    async def dispatch(self, request: Request, call_next):
        client_ip = request.client.host if request.client else "unknown"
        path = request.url.path
        is_auth = any(path.startswith(p) for p in AUTH_PATHS)
        limit = settings.RATE_LIMIT_AUTH_PER_MINUTE if is_auth else settings.RATE_LIMIT_PER_MINUTE
        prefix = "auth" if is_auth else "api"
        key = f"rl:{prefix}:{client_ip}"
        now = int(time.time())
        window_start = now - 60

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

        return await call_next(request)
