"""Demo-tenant background jobs (SE-4193, D4)."""

import asyncio
import logging

from app.core.background.celery_app import celery_app

logger = logging.getLogger(__name__)

RESET_TASK_NAME = "app.core.background.tasks.demo_tasks.reset_demo_tenant_nightly"


@celery_app.task(name=RESET_TASK_NAME, bind=True, max_retries=0)
def reset_demo_tenant_nightly(self) -> dict:
    """Nightly: clear the demo org's data and re-seed it (demo org only).

    The reset itself refuses any org that is not the seeded demo tenant with
    is_demo = TRUE; a refusal (e.g. no demo org in this environment) is logged
    and reported as skipped rather than retried.
    """
    # Imported here so Faker is only loaded by the worker that runs the reset.
    from app.core.demo_tenant.reset import DemoResetRefused, run_reset

    try:
        result = asyncio.run(run_reset())
    except DemoResetRefused as exc:
        logger.warning("Demo reset skipped: %s", exc)
        return {"status": "skipped", "reason": str(exc)}
    logger.info("Demo tenant reset: deleted %s", result["deleted"])
    return {"status": "reset", **result}
