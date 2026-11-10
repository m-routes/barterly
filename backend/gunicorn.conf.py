"""Gunicorn config for Cloud Run: ASGI via uvicorn workers."""

import os

bind = f"0.0.0.0:{os.environ.get('PORT', '8080')}"
worker_class = "uvicorn_worker.UvicornWorker"
# Cloud Run gives each instance a fixed vCPU count; 2 workers per vCPU is a sane default.
workers = int(os.environ.get("WEB_CONCURRENCY", "2"))
# Cloud Run enforces the request timeout; this only reaps stuck workers.
timeout = int(os.environ.get("GUNICORN_TIMEOUT", "120"))
graceful_timeout = 25  # Cloud Run sends SIGTERM and waits 10s by default, up to its limit.
keepalive = 5
# Requests arrive only through Google's front end, which sets X-Forwarded-*.
forwarded_allow_ips = "*"
accesslog = "-"
errorlog = "-"
loglevel = os.environ.get("GUNICORN_LOG_LEVEL", "info")
