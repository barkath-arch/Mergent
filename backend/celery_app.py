"""Celery application bootstrap.

Configured for resilience against transient Redis outages:
  - broker_connection_retry_on_startup=True
  - broker_connection_max_retries=None (retry forever)
  - broker_heartbeat for liveness
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

from celery import Celery  # noqa: E402
from celery.schedules import crontab as _crontab  # noqa: E402

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "mergent",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    broker_connection_retry_on_startup=True,
    broker_connection_retry=True,
    broker_connection_max_retries=None,
    broker_heartbeat=30,
    broker_pool_limit=10,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_default_queue="mergent",
    result_expires=3600,
    # Phase 6: nightly trust recompute @ 03:00 UTC.
    beat_schedule={
        "trust-recompute-nightly": {
            "task": "tasks.recompute_trust_all",
            "schedule": _crontab(hour=3, minute=0),
        },
    },
)
