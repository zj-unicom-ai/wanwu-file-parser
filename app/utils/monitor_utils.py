"""Lightweight timing decorator for monitoring parse latencies."""
from __future__ import annotations

import functools
import time
from typing import Any, Callable, TypeVar

from app.utils.logging_utils import setup_logger

logger = setup_logger(__name__, "./logs/monitor.log")

F = TypeVar("F", bound=Callable[..., Any])


def log_time(func: F) -> F:
    """Log the wall-clock duration of the wrapped function."""

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        start = time.perf_counter()
        try:
            return func(*args, **kwargs)
        finally:
            logger.info("%s took %.2f seconds to complete", func.__name__, time.perf_counter() - start)

    return wrapper  # type: ignore[return-value]
