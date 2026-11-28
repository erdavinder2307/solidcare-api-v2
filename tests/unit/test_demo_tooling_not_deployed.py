"""
The demo-tenant seed/reset is CLI-only (SE-4193): the deployed app never imports it.

Faker is not in requirements-deploy.txt, so anything the API or the Celery worker
imports (at startup or lazily at request time) must not reach app.core.demo_tenant or
faker. There is also no nightly Celery job and no reset endpoint.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEMO_IMPORT = re.compile(r"^\s*(?:from|import)\s+(?:app\.core\.demo_tenant|faker)\b", re.MULTILINE)

# Imports the deployed API / worker make at startup, with faker made unimportable.
_PROBE = """
import sys

class BlockFaker:
    def find_spec(self, name, path=None, target=None):
        if name == "faker" or name.startswith("faker."):
            raise ImportError("faker is not installed in the deployed app")

sys.meta_path.insert(0, BlockFaker())
import application  # noqa: F401  (the App Service entry point: app.main)
import app.core.background.celery_app  # noqa: F401
import app.core.background.tasks.notification_tasks  # noqa: F401
import app.core.background.tasks.report_tasks  # noqa: F401

loaded = sorted(m for m in sys.modules
                if m.split(".")[0] == "faker" or m.startswith("app.core.demo_tenant"))
print("LOADED", loaded)
sys.exit(1 if loaded else 0)
"""


def test_deployed_app_starts_without_faker_and_never_loads_the_demo_package():
    proc = subprocess.run([sys.executable, "-c", _PROBE], cwd=ROOT, capture_output=True,
                          text=True, timeout=120)
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_no_runtime_module_imports_the_demo_package_or_faker():
    offenders = [
        str(path.relative_to(ROOT))
        for path in (ROOT / "app").rglob("*.py")
        if "/app/core/demo_tenant/" not in path.as_posix() and DEMO_IMPORT.search(path.read_text())
    ]
    assert offenders == []


def test_faker_is_not_a_deploy_requirement():
    deploy = (ROOT / "requirements-deploy.txt").read_text().lower()
    assert "faker" not in deploy
    assert "faker" in (ROOT / "requirements.txt").read_text().lower()  # dev/CLI keep it


def test_no_demo_reset_job_or_endpoint():
    from app.core.background.celery_app import celery_app
    from app.main import app

    assert not [k for k in celery_app.conf.beat_schedule if "demo" in k]
    assert not [i for i in celery_app.conf.include if "demo" in i]
    assert not [r.path for r in app.routes if "demo-reset" in getattr(r, "path", "")]
