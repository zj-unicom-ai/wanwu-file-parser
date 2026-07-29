"""Logging utilities: rotating file + stream handlers with a per-request trace id."""
from __future__ import annotations

import contextvars
import logging
import os
from logging.handlers import RotatingFileHandler
from typing import Optional

_trace_id_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "trace_id", default=None
)


class TraceIdFilter(logging.Filter):
    """Inject the current request's trace id into every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.trace_id = _trace_id_var.get() or "N/A"
        return True


def setup_logger(name: str, log_file: str, level: int = logging.INFO) -> logging.Logger:
    """Return a configured logger with rotating file + stream handlers.

    Idempotent: if the logger already has handlers, returns it unchanged so
    repeated imports never stack duplicate handlers.
    """
    log_dir = os.path.dirname(log_file)
    if log_dir and not os.path.exists(log_dir):
        os.makedirs(log_dir, exist_ok=True)

    logger = logging.getLogger(name)
    logger.setLevel(level)
    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(trace_id)s - %(message)s"
    )

    file_handler = RotatingFileHandler(log_file, maxBytes=1_000_000, backupCount=5)
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)

    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(level)
    stream_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)
    logger.addFilter(TraceIdFilter())
    return logger


def set_trace_id(trace_id: Optional[str]) -> None:
    _trace_id_var.set(trace_id)


def get_trace_id() -> str:
    return _trace_id_var.get() or "N/A"


def clear_trace_id() -> None:
    _trace_id_var.set(None)
