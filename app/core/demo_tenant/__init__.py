"""Demo tenant (SE-4193): seed and reset of the public demo clinic.

``seed`` builds and upserts the synthetic demo data; ``reset`` clears the demo
org's rows and re-seeds it. Both refuse any org that is not the fixed demo org
with ``is_demo = TRUE``. The CLIs live in scripts/seed_demo_tenant.py and
scripts/reset_demo_tenant.py.
"""
