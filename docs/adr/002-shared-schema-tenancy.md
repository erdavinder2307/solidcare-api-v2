# ADR-002: Shared-Schema Multi-Tenancy (Deprecating `Organization.schema_name`)

**Date:** 2026-08-15
**Status:** Accepted

## Context

`Organization.schema_name` (`NOT NULL UNIQUE`) has existed since the initial schema
and implies a **schema-per-tenant** isolation strategy — each org gets its own
Postgres schema, selected via `search_path` at request time.

That implementation never happened. Every domain table instead carries an
`organization_id` column and every query filters on it — **shared-schema with a
discriminator column**, the industry-default pattern for this scale. `schema_name`
has been set on every `Organization` row (generated at creation) but never read by
any query, migration, or connection-setup code. It is dead weight that actively
misleads: the next engineer who finds it will reasonably assume schema-per-tenant
is in effect and design around a guarantee that does not exist.

This was surfaced during the Phase 1 identity/tenancy review (see
`docs/STRATEGIC_REVIEW_2026-07.md` §6) while introducing the `memberships` table
(F1), which made the tenancy model's actual shape — and the gap between declared
and implemented isolation — directly relevant to get right before more code is
built on top of it.

## Decision

Formally commit to **shared-schema tenancy with an `organization_id` discriminator**
as the isolation strategy, for the reasons in ADR-001 (team size, operational
simplicity) and because migration cost for schema-per-tenant scales linearly with
tenant count — expensive exactly when the product is succeeding.

`Organization.schema_name` is **deprecated, not dropped**, in this pass:
- No code should read or write meaningful values to it going forward
- It remains `NOT NULL UNIQUE` so no data migration is forced right now
- A follow-up migration removes the column once nothing references it

## Consequences

- **Every query on a tenant-scoped table MUST filter by `organization_id`.** This
  was already true in practice; ADR-002 makes it the explicit, load-bearing
  contract rather than an implicit convention.
- **Defense-in-depth is a gap, not a feature.** A forgotten `WHERE organization_id =`
  clause is currently the *only* thing standing between two tenants' data. Postgres
  Row-Level Security (roadmap item F6) closes this — RLS policies keyed on a
  session variable make cross-tenant leakage fail at the database layer even if
  application code forgets the filter. F6 is the direct consequence of formalizing
  this ADR and should not be treated as a separate, deferrable concern.
- **`Organization.schema_name` should not be read by new code.** It will be
  removed once F6's RLS policies are in place and a grep confirms zero remaining
  references.

## Alternatives Considered

| Option | Verdict |
|---|---|
| Schema-per-tenant (the originally implied design) | Rejected. Alembic migrations across N schemas, Postgres connection-limit pressure on Azure Flexible Server, and linear migration cost per tenant — expensive exactly when growth is working. |
| Database-per-tenant | Rejected for the general case. Reserved as a possible future **on-prem/enterprise** offering for customers who require full physical isolation, not the default SaaS path. |
| Shared schema + discriminator + RLS (this decision) | Accepted. Matches what is already 95% implemented; RLS is additive and does not require rewriting existing queries. |
