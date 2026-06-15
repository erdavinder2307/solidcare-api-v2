#!/bin/bash
cd /home/site/wwwroot
export PYTHONPATH="/home/site/wwwroot:/home/site/wwwroot/.python_packages/lib/site-packages"
if [ -x "./antenv/bin/python" ]; then
  exec ./antenv/bin/python -m gunicorn application:app \
    --worker-class uvicorn.workers.UvicornWorker \
    --bind "0.0.0.0:${PORT:-8000}" \
    --workers 1 \
    --timeout 120
fi
exec python3 -m gunicorn application:app \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind "0.0.0.0:${PORT:-8000}" \
  --workers 1 \
  --timeout 120
