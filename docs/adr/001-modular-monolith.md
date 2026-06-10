# ADR-001: Modular Monolith Architecture

**Date:** 2026-06-09
**Status:** Accepted

## Context

Solidcare V2 needs a backend architecture that is maintainable, scalable, and can evolve over time. The team is starting small and the product is early-stage.

## Decision

We use a **Modular Monolith** architecture — a single deployable unit with strict domain module boundaries enforced by code structure rather than network boundaries.

Each domain module (`auth`, `patients`, `doctors`, `appointments`, etc.) has its own:
- `models.py` — SQLAlchemy ORM models
- `repository.py` — database access only
- `service.py` — business logic
- `schemas.py` — Pydantic request/response models
- `router.py` — FastAPI endpoints

## Rationale

- Team size (2–4 engineers) does not justify microservices operational overhead
- Avoids distributed system complexity (network failures, distributed tracing, service discovery)
- Domain boundaries are enforced structurally — easy migration path to microservices module by module
- Single deployment reduces infrastructure cost in early stages

## Consequences

- Horizontal scaling of the monolith handles >95% of healthcare practice growth
- All modules share the same database connection pool
- Background tasks run in a separate Celery process (already decoupled)
- Migration to microservices: extract one module at a time when justified by scale

## Migration Path to Microservices

When a specific module (e.g., `billing`) requires independent scaling:
1. Extract the module into its own FastAPI service
2. Replace in-process event bus with Azure Service Bus messages
3. Database: either shared schema or independent DB depending on isolation needs
