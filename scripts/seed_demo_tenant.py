"""Seed (or refresh) the public demo tenant with synthetic data (SE-4193, D1).

Thin CLI around app/core/demo_tenant/seed.py, which holds the data generator and
the safety checks (only the fixed demo org/clinic is ever written, a non-demo org
with the demo id or slug is refused, nothing is deleted).

Usage (from the repo root, with DATABASE_URL pointing at the target database):

    python -m scripts.seed_demo_tenant --dry-run     # build the data, print counts, no DB
    DEMO_SEED_PASSWORD=... python -m scripts.seed_demo_tenant

The staff password comes from ``--password`` or the ``DEMO_SEED_PASSWORD`` env var;
there is no default.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

from app.core.demo_tenant.seed import (
    DEFAULT_PATIENTS,
    DEFAULT_SEED,
    DEMO_ORG_ID,
    DEMO_ORG_SLUG,
    PASSWORD_ENV,
    DemoSeedRefused,
    SeedPlan,
    apply_plan,
    build_plan,
    validate_plan,
)


def _print_counts(plan: SeedPlan) -> None:
    for name, count in plan.counts().items():
        print(f"  {name:<28}{count:>5}")
    dates = [a["appointment_date"] for a in plan.tables["appointments"]]
    if dates:
        print(f"  appointment dates: {min(dates)} .. {max(dates)}")


async def _run(plan: SeedPlan, password: str) -> str:
    from app.core.security.password import hash_password
    from app.database import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        async with session.begin():
            return await apply_plan(session, plan, hash_password(password))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true",
                        help="build the data and print counts; no database access")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--patients", type=int, default=DEFAULT_PATIENTS)
    parser.add_argument("--password", help=f"staff password (default: ${PASSWORD_ENV})")
    args = parser.parse_args(argv)

    plan = build_plan(seed=args.seed, n_patients=args.patients)
    validate_plan(plan)
    print(f"Demo tenant {DEMO_ORG_SLUG} ({DEMO_ORG_ID}), seed {args.seed}, today {plan.today}:")
    _print_counts(plan)
    if args.dry_run:
        print("Dry run: nothing written.")
        return 0

    password = args.password or os.environ.get(PASSWORD_ENV)
    if not password or len(password) < 8:
        print(f"Set {PASSWORD_ENV} (or --password), at least 8 characters.", file=sys.stderr)
        return 2
    try:
        action = asyncio.run(_run(plan, password))
    except DemoSeedRefused as exc:
        print(f"Refused: {exc}", file=sys.stderr)
        return 1
    print(f"Done ({action}). Staff logins (send header X-Org-Id: {DEMO_ORG_ID}):")
    for email in plan.staff_emails.values():
        print(f"  {email}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
