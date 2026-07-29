"""Lazy model-client strategy selection.

The CPU image never imports ``paddleocr``. ``MineruClient`` is imported at the
top (it is HTTP-only, no heavy deps); ``PaddleOCRVLClient`` is imported lazily
inside its initializer so a misconfigured paddleocrvl path never breaks startup
of a mineru deployment.
"""
from __future__ import annotations

from typing import Any, Callable, Dict

from app.config import settings
from app.models.base import OcrClient
from app.models.mineru.client import MineruClient


def init_mineru_client(_address: str | None = None) -> OcrClient:
    """MinerU client; endpoint resolved from ``settings.mineru_api_endpoint``.

    The client POSTs to the resolved full endpoint directly (no path append).
    """
    return MineruClient(settings.mineru_api_endpoint)


def init_paddleocrvl_client(_address: str | None = None) -> OcrClient:
    """PaddleOCR-VL client (lazy import); base from ``settings.paddleocrvl_endpoint``.

    The client appends ``/layout-parsing`` and ``/restructure-pages`` on top of
    this host-only base.
    """
    from app.models.paddleocrvl.client import PaddleOCRVLClient

    return PaddleOCRVLClient(settings.paddleocrvl_endpoint)


CLIENT_STRATEGIES: Dict[str, Callable[[str | None], OcrClient]] = {
    "mineru": init_mineru_client,
    "paddleocrvl": init_paddleocrvl_client,
}
