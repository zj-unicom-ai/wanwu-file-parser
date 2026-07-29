"""Model client protocol and shared helpers.

A model client talks to a remote OCR service over HTTP. The CPU process never
loads the model itself. All clients conform to the same small surface:

  - ``parse_file(...)``     -> raw provider response (dict)
  - ``post_process(...)``    -> (markdown, json_content, prefix_image_url)

``parse_result`` is the normalized intermediate we hand to ``post_process``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass
class ParseResult:
    """Normalized OCR response fed into :meth:`OcrClient.post_process`."""

    md_content: str = ""
    json_content: str = ""
    images: dict[str, str] = field(default_factory=dict)


@runtime_checkable
class OcrClient(Protocol):
    """Contract every OCR backend implements."""

    def parse_file(
        self,
        file_path: str,
        return_json: bool = False,
        extract_image: bool = False,
        extract_image_content: int = 0,
    ) -> dict[str, Any]:
        ...

    def post_process(
        self,
        *,
        extract_image: bool,
        extract_image_content: int,
        file_name: str,
        file_path: str,
        return_json: bool,
        response: dict[str, Any],
    ) -> tuple[str, str, str]:
        ...
