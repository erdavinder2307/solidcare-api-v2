"""Smoke tests for FastAPI app wiring — no database."""

import os

import pytest

os.environ.setdefault("ENV", "development")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-ci-only")

from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_health_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "version" in data


@pytest.mark.asyncio
async def test_openapi_available_in_development():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    assert "paths" in schema
    assert "/api/v1/patients" in schema["paths"]


@pytest.mark.asyncio
async def test_unauthenticated_patients_returns_403_or_401():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/patients")
    assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_public_prescription_share_no_auth():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/prescriptions/share/abc123")
    assert response.status_code == 200  # documents current public exposure
