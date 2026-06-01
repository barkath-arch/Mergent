"""Structured JSON logging configuration for MERGENT.

Emits JSON log records with run_id, agent, status, etc. so that log lines can be
parsed by downstream observability tooling. The same fields are also persisted
on the orchestration_runs.steps[] array.
"""
from __future__ import annotations

import logging
import sys

from pythonjsonlogger import jsonlogger


_CONFIGURED = False


def setup_logging(level: int = logging.INFO) -> None:
    """Idempotently configure the root logger with a JSON formatter."""
    global _CONFIGURED
    if _CONFIGURED:
        return

    root = logging.getLogger()
    root.setLevel(level)

    # Remove default handlers (uvicorn / FastAPI install their own).
    for h in list(root.handlers):
        root.removeHandler(h)

    handler = logging.StreamHandler(sys.stdout)
    formatter = jsonlogger.JsonFormatter(
        fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
        rename_fields={"asctime": "ts", "levelname": "level"},
    )
    handler.setFormatter(formatter)
    root.addHandler(handler)

    # Quiet down very chatty libraries.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("LiteLLM").setLevel(logging.WARNING)
    logging.getLogger("litellm").setLevel(logging.WARNING)

    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    setup_logging()
    return logging.getLogger(name)
