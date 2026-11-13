"""Reset the public demo tenant to its seeded state (SE-4193, D4).

Thin CLI around app/core/demo_tenant/reset.py, which holds the reset logic and its
safety checks (only the seeded demo org with ``is_demo = TRUE`` is ever touched;
every DELETE is scoped to it; one transaction with an advisory lock).

Usage (from the repo root, with DATABASE_URL pointing at the target database):

    python -m scripts.reset_demo_tenant --dry-run   # list what would be cleared, no DB
    python -m scripts.reset_demo_tenant

Staff password: ``--password`` / DEMO_SEED_PASSWORD sets a new one; otherwise the
DEMO_SEED_PASSWORD_HASH setting is restored; with neither, the current one is kept.

Also run nightly by the Celery beat entry "demo-tenant-reset-nightly" and on
demand by POST /api/v1/organizations/current/demo-reset (demo org admin only).
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

from app.core.demo_tenant.reset import DemoResetRefused, delete_statements, run_reset
from app.core.demo_tenant.seed import DEMO_ORG_ID, DEMO_ORG_SLUG, PASSWORD_ENV


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true",
                        help="list the tables that would be cleared; no database access")
    parser.add_argument("--password", help=f"new staff password (default: ${PASSWORD_ENV} when set, "
                                           "else the DEMO_SEED_PASSWORD_HASH setting)")
    args = parser.parse_args(argv)

    print(f"Demo tenant {DEMO_ORG_SLUG} ({DEMO_ORG_ID}):")
    if args.dry_run:
        print("Would delete demo-org rows from:")
        for name, _ in delete_statements(DEMO_ORG_ID):
            print(f"  {name}")
        print("then re-run the demo seed. Dry run: nothing written.")
        return 0

    password = args.password or os.environ.get(PASSWORD_ENV)
    if password is not None and len(password) < 8:
        print(f"{PASSWORD_ENV} / --password must be at least 8 characters.", file=sys.stderr)
        return 2
    try:
        result = asyncio.run(run_reset(password))
    except DemoResetRefused as exc:
        print(f"Refused: {exc}", file=sys.stderr)
        return 1
    print("Deleted:")
    for name, count in result["deleted"].items():
        print(f"  {name:<28}{count:>5}")
    print("Re-seeded:")
    for name, count in result["seeded"].items():
        print(f"  {name:<28}{count:>5}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
