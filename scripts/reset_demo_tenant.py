"""Reset the public demo tenant to its seeded state (SE-4193, D4).

Thin CLI around app/core/demo_tenant/reset.py, which holds the reset logic and its
safety checks (only the seeded demo org with ``is_demo = TRUE`` is ever touched;
every DELETE is scoped to it; one transaction with an advisory lock).

Run by hand only (there is no scheduled job and no API endpoint): dry run first, then
confirm by running it again without the flag. From the repo root, with the dev
requirements installed (Faker) and DATABASE_URL pointing at the target database:

    python -m scripts.reset_demo_tenant --dry-run   # list what would be cleared; no DB access
    python -m scripts.reset_demo_tenant             # clear the demo org's rows and re-seed

Env vars: DATABASE_URL (target database); optional DEMO_SEED_PASSWORD_HASH (bcrypt
hash restored on the demo staff logins) and DEMO_SEED_PASSWORD (a new plain password;
8+ chars; the --password flag does the same).

Staff password, same source as the seed CLI: ``--password`` / DEMO_SEED_PASSWORD sets a
new one; otherwise the DEMO_SEED_PASSWORD_HASH setting is restored; with neither, the
current one is kept. A DEMO_SEED_PASSWORD_HASH that is not a valid bcrypt hash is a
config error (exit 2), also in a dry run.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

from app.core.demo_tenant.reset import DemoResetRefused, delete_statements, run_reset
from app.core.demo_tenant.seed import (
    DEMO_ORG_ID,
    DEMO_ORG_SLUG,
    PASSWORD_ENV,
    PASSWORD_HASH_SETTING,
    DemoConfigError,
    configured_password_hash,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true",
                        help="list the tables that would be cleared; no database access")
    parser.add_argument("--password", help=f"new staff password (default: ${PASSWORD_ENV} when set, "
                                           f"else the {PASSWORD_HASH_SETTING} setting)")
    args = parser.parse_args(argv)

    password = args.password or os.environ.get(PASSWORD_ENV)
    if password is not None and len(password) < 8:
        print(f"{PASSWORD_ENV} / --password must be at least 8 characters.", file=sys.stderr)
        return 2
    try:
        configured = configured_password_hash()
    except DemoConfigError as exc:
        print(f"Config error: {exc}", file=sys.stderr)
        return 2

    print(f"Demo tenant {DEMO_ORG_SLUG} ({DEMO_ORG_ID}):")
    if password:
        print(f"Staff password: set to the new one from --password / {PASSWORD_ENV}.")
    elif configured:
        print(f"Staff password: restored from {PASSWORD_HASH_SETTING}.")
    else:
        print(f"Staff password: {PASSWORD_HASH_SETTING} is not set, so the current one is kept "
              "(a demo login changed by a visitor is NOT restored).")
    if args.dry_run:
        print("Would delete demo-org rows from:")
        for name, _ in delete_statements(DEMO_ORG_ID):
            print(f"  {name}")
        print("then re-run the demo seed. Dry run: nothing written.")
        return 0

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
