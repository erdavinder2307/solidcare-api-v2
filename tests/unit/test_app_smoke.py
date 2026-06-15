"""Smoke tests for FastAPI app wiring — no database."""

import os

os.environ.setdefault("ENV", "test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-ci-only")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://solidcare:solidcare@localhost:5432/solidcare_test",
)

from httpx import ASGITransport, AsyncClient

from app.main import app


async def test_health_endpoint(test_engine):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ("healthy", "degraded")
    assert "version" in data


async def test_openapi_available_in_development():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    assert "paths" in schema
    assert "/api/v1/patients" in schema["paths"]


async def test_unauthenticated_patients_returns_403_or_401():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/patients")
    assert response.status_code in (401, 403)


async def test_public_prescription_share_route_is_public():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/openapi.json")
    assert response.status_code == 200
    path = "/api/v1/prescriptions/share/{share_token}"
    assert path in response.json()["paths"]
    get_op = response.json()["paths"][path]["get"]
    assert get_op.get("security") in (None, [])
