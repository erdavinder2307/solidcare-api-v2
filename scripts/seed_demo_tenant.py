"""Seed (or refresh) the public demo tenant with synthetic data (SE-4193, D1).

Thin CLI around app/core/demo_tenant/seed.py, which holds the data generator and
the safety checks (only the fixed demo org/clinic is ever written, a non-demo org
with the demo id or slug is refused, nothing is deleted).

Run by hand only (there is no scheduled job and no API endpoint): dry run first, then
confirm by running it again without the flag. From the repo root, with the dev
requirements installed (Faker) and DATABASE_URL pointing at the target database:

    python -m scripts.seed_demo_tenant --dry-run     # build the data, print counts; no DB access
    DEMO_SEED_PASSWORD_HASH='$2b$...' python -m scripts.seed_demo_tenant
    DEMO_SEED_PASSWORD=...            python -m scripts.seed_demo_tenant   # or this

Env vars: DATABASE_URL (target database); the staff password from DEMO_SEED_PASSWORD_HASH
(bcrypt hash) or DEMO_SEED_PASSWORD (plain, 8+ chars; the --password flag does the same).

Staff password, same source as the reset CLI: ``--password`` / DEMO_SEED_PASSWORD wins,
else the DEMO_SEED_PASSWORD_HASH setting, so the logins the seed creates are the ones
every later reset restores; there is no default. A DEMO_SEED_PASSWORD_HASH that is not a
valid bcrypt hash is a config error (exit 2), also in a dry run.
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
    PASSWORD_HASH_SETTING,
    DemoConfigError,
    DemoSeedRefused,
    SeedPlan,
    apply_plan,
    build_plan,
    configured_password_hash,
    resolve_password_hash,
    validate_plan,
)


def _print_counts(plan: SeedPlan) -> None:
    for name, count in plan.counts().items():
        print(f"  {name:<28}{count:>5}")
    dates = [a["appointment_date"] for a in plan.tables["appointments"]]
    if dates:
        print(f"  appointment dates: {min(dates)} .. {max(dates)}")


async def _run(plan: SeedPlan, password_hash: str) -> str:
    from app.database import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        async with session.begin():
            return await apply_plan(session, plan, password_hash)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true",
                        help="build the data and print counts; no database access")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--patients", type=int, default=DEFAULT_PATIENTS)
    parser.add_argument("--password", help=f"staff password (default: ${PASSWORD_ENV} when set, "
                                           f"else the {PASSWORD_HASH_SETTING} setting)")
    args = parser.parse_args(argv)

    password = args.password or os.environ.get(PASSWORD_ENV)
    if password and len(password) < 8:
        print(f"{PASSWORD_ENV} / --password must be at least 8 characters.", file=sys.stderr)
        return 2
    try:
        configured = configured_password_hash()
    except DemoConfigError as exc:
        print(f"Config error: {exc}", file=sys.stderr)
        return 2

    plan = build_plan(seed=args.seed, n_patients=args.patients)
    validate_plan(plan)
    print(f"Demo tenant {DEMO_ORG_SLUG} ({DEMO_ORG_ID}), seed {args.seed}, today {plan.today}:")
    _print_counts(plan)
    if password:
        print(f"Staff password: the one from --password / {PASSWORD_ENV}.")
    elif configured:
        print(f"Staff password: from {PASSWORD_HASH_SETTING}.")
    else:
        print(f"Staff password: not set (a real run needs {PASSWORD_HASH_SETTING}, "
              f"{PASSWORD_ENV} or --password).")
    if args.dry_run:
        print("Dry run: nothing written.")
        return 0

    if not (password or configured):
        print(f"Set {PASSWORD_HASH_SETTING} (bcrypt hash), or {PASSWORD_ENV} / --password "
              "(8+ characters).", file=sys.stderr)
        return 2
    try:
        action = asyncio.run(_run(plan, resolve_password_hash(password)))
    except DemoSeedRefused as exc:
        print(f"Refused: {exc}", file=sys.stderr)
        return 1
    print(f"Done ({action}). Staff logins (send header X-Org-Id: {DEMO_ORG_ID}):")
    for email in plan.staff_emails.values():
        print(f"  {email}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
