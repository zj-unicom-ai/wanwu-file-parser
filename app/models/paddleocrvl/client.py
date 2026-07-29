"""PaddleOCR-VL pipeline service client (HTTP-only).

Implements the official two-stage base64 JSON protocol:

  1. ``POST {base_url}/layout-parsing``      — base64 JSON: ``{file, fileType}``
  2. ``POST {base_url}/restructure-pages``   — base64 JSON: ``{pages, concatenatePages}``

``base_url`` is host only (no path). The two sub-endpoint paths come from
settings (``PADDLEOCRVL_API_LAYOUT_PARSING_PATH`` /
``PADDLEOCRVL_API_RESTRUCTURE_PAGES_PATH``).

fileType mapping (official): ``0 = PDF``, ``1 = image (incl. TIFF)``. fileType
is optional, but when sending base64 content (not a URL) it must be set
explicitly or the server cannot infer the type.

This module is pure HTTP — it imports no paddle/paddleocr — so it is safe to
load on the CPU dispatch service under any ``MODEL_TYPE`` (used both as the
primary backend and to OCR Excel embedded images under mineru deployments).
"""
from __future__ import annotations

import base64
import json
import os
import re
import urllib.parse
from typing import Any

import requests

from app.config import settings
from app.models.base import ParseResult
from app.utils.logging_utils import setup_logger
from app.utils.monitor_utils import log_time
from app.utils.storage.factory import StorageFactory
from app.utils.table_extract import extract_text_with_tables

logger = setup_logger(__name__, "./logs/client.log")

# /layout-parsing fileType mapping (official: 0 = PDF, 1 = image incl. TIFF).
# Kept in sync with the API's advertised image extensions, else a type admitted
# by the API layer would raise ValueError inside parse_file (500 after being
# advertised as supported).
_FILE_TYPE_PDF = 0
_FILE_TYPE_IMAGE = 1

_FILE_TYPE_MAP: dict[str, int] = {
    ".pdf": _FILE_TYPE_PDF,
    ".jpg": _FILE_TYPE_IMAGE,
    ".jpeg": _FILE_TYPE_IMAGE,
    ".png": _FILE_TYPE_IMAGE,
    ".gif": _FILE_TYPE_IMAGE,
    ".webp": _FILE_TYPE_IMAGE,
    ".tif": _FILE_TYPE_IMAGE,
    ".tiff": _FILE_TYPE_IMAGE,
    ".bmp": _FILE_TYPE_IMAGE,
}

# Extensions the API admits as image inputs (must all be in _FILE_TYPE_MAP).
SUPPORTED_IMAGE_EX = (".png", ".jpeg", ".jpg", ".webp", ".gif", ".tif", ".tiff", ".bmp")

_REQUEST_TIMEOUT_SECONDS = 300


def _build_request_timeout() -> int:
    return _REQUEST_TIMEOUT_SECONDS


class PaddleOCRVLClient:
    """HTTP client for the PaddleOCR-VL pipeline service."""

    def __init__(self, base_url: str) -> None:
        self.base_url = (base_url or "").rstrip("/")

    # ------------------------------------------------------------------ #
    # public API
    # ------------------------------------------------------------------ #
    @log_time
    def extract_text_from_image(self, file_name: str) -> str:
        """Second-pass OCR of a single image; returns cleaned text (no img divs)."""
        try:
            response = self.parse_file(file_name)
        except Exception as exc:  # noqa: BLE001 — degrade to empty on failure
            logger.error("extract_text_from_image parse_file error: %s", exc)
            return ""
        if response.get("code") != 200:
            logger.error(
                "extract_text_from_image response not 200: %s", response.get("message")
            )
            return ""
        md_content = response.get("data", {}).get("md_content", "")
        # Drop <div ...><img ...></div> wrappers; we only want the text.
        pattern = r'<div[^>]*>(?:[^<]*?<(?!/?div)[^<]*?)*?<img[^>]*src[^>]*>(?:<(?!/?div)[^<]*?)*?</div>'
        return re.sub(pattern, "", md_content, flags=re.S)

    @log_time
    def parse_file(
        self,
        file_path: str,
        return_json: bool = False,
        extract_image: bool = False,
        extract_image_content: int = 0,
    ) -> dict[str, Any]:
        """Parse a document via the two-stage protocol.

        Returns a normalized structure consumed by :meth:`post_process`::

            {"code": 200, "message": "...",
             "data": {"md_content": str, "json_data": str, "images": {name: data_uri}}}
        """
        del extract_image, extract_image_content  # unused here; images always collected
        file_name = os.path.basename(file_path)
        _, file_ext = os.path.splitext(file_name)
        if file_ext.lower() not in _FILE_TYPE_MAP:
            logger.error(
                "file type not supported: %s (only pdf, jpg, jpeg, png, gif, webp, "
                "tif, tiff, bmp)",
                file_ext,
            )
            raise ValueError(
                f"File type {file_ext} is not supported. Only pdf, jpg, jpeg, png, "
                "gif, webp, tif, tiff, bmp are supported."
            )

        try:
            with open(file_path, "rb") as fh:
                image_data = base64.b64encode(fh.read()).decode("ascii")
        except OSError as exc:
            logger.error("read file failed: %s, error: %s", file_path, exc)
            raise

        file_type = _FILE_TYPE_MAP[file_ext.lower()]

        try:
            md_content, json_content, images = self._call_two_stage(image_data, file_type, return_json)
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else "unknown"
            logger.error("paddleocr request HTTPError: status=%s, %s", status, exc)
            raise
        except requests.RequestException as exc:
            logger.error("paddleocr request RequestException: %s", exc)
            raise

        return {
            "code": 200,
            "message": "转换成功",
            "data": {
                "md_content": md_content,
                "json_data": json_content,
                "images": images,
            },
        }

    @log_time
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
        """Upload extracted images to storage, rewrite md refs, clean tables.

        Returns ``(md_content, json_content, prefix_image_url)``.
        """
        del file_name, file_path, return_json
        data = response.get("data", {})
        md_content = data.get("md_content", "")
        json_content = data.get("json_data", "")
        # Default prefix from config; overwritten with a real upload URL when
        # images are extracted.
        prefix_image_url = settings.prefix_image_url

        from app.services.file_service import save_images_res_to_local

        save_images_res_to_local(data)
        if extract_image and md_content:
            logger.info("extracting images for file")
            md_content, prefix_image_url = self.extract_images_from_md(
                md_content, extract_image_content, "./data/images"
            )
        logger.info("extracting images done")
        md_content = extract_text_with_tables(md_content)
        return md_content, json_content, prefix_image_url

    # ------------------------------------------------------------------ #
    # image upload + md rewrite
    # ------------------------------------------------------------------ #
    @log_time
    def extract_images_from_md(
        self, md_content: str, extract_image_content: int, image_dir: str
    ) -> tuple[str, str]:
        """Upload ``<img src="imgs/...">`` images and rewrite tags to download URLs.

        Returns ``(rewritten_md, prefix_image_url)`` where the prefix is the base
        URL of the last successful upload (or the configured default).
        """
        img_pattern = r'<img\s+[^>]*?src="imgs/([^"]+)"[^>]*?>'
        matches = list(re.finditer(img_pattern, md_content))
        prefix_image_url = settings.prefix_image_url

        for match in reversed(matches):
            img_filename = match.group(1)
            image_path = os.path.abspath(os.path.join(image_dir, img_filename))
            logger.info("extracting image: %s", image_path)
            if not os.path.exists(image_path):
                logger.warning("image does not exist, skipping: %s", img_filename)
                continue
            try:
                storage = StorageFactory.get_storage()
                download_link = storage.upload_file(image_path)
                ocr_text = ""
                if extract_image_content:
                    raw = self.extract_text_from_image(image_path)
                    logger.info("image content extracted: %s", raw)
                    ocr_text = re.sub(r"<[^>]+>", "", raw)        # strip HTML tags
                    ocr_text = re.sub(r"[\n\r]", "", ocr_text)     # strip newlines
                    ocr_text = ocr_text.strip()
                    ocr_text = re.sub(r"[^一-龥a-zA-Z0-9\s]", "", ocr_text)
                new_tag = f"![]({download_link}) {ocr_text}".rstrip()
                md_content = md_content[: match.start()] + new_tag + md_content[match.end() :]
                prefix_image_url = download_link
            except Exception as exc:  # noqa: BLE001 — skip one bad image, keep going
                logger.error("upload image %s failed, skipping: %s", img_filename, exc)
                continue

        return md_content, _extract_base_url(prefix_image_url)

    # ------------------------------------------------------------------ #
    # two-stage HTTP
    # ------------------------------------------------------------------ #
    def _call_two_stage(
        self, image_data: str, file_type: int, return_json: bool
    ) -> tuple[str, str, dict[str, str]]:
        """Run layout-parsing then restructure-pages; return (md, json, images)."""
        # 1. layout parsing + VLM recognition
        layout_payload = {"file": image_data, "fileType": file_type}
        layout_resp = requests.post(
            f"{self.base_url}/{settings.paddleocrvl_api_layout_parsing_path}",
            json=layout_payload,
            timeout=_build_request_timeout(),
        )
        layout_resp.raise_for_status()
        layout_result = layout_resp.json().get("result", {})

        # 2. page restructure (concatenate multi-page markdown)
        pages = []
        for res in layout_result.get("layoutParsingResults", []):
            page = {
                "prunedResult": res.get("prunedResult"),
                "markdownImages": (res.get("markdown") or {}).get("images") or {},
            }
            pages.append(page)

        restructure_payload = {"pages": pages, "concatenatePages": True}
        restructure_resp = requests.post(
            f"{self.base_url}/{settings.paddleocrvl_api_restructure_pages_path}",
            json=restructure_payload,
            timeout=_build_request_timeout(),
        )
        restructure_resp.raise_for_status()
        restructure_result = restructure_resp.json().get("result", {})

        md_content = _extract_markdown_text(restructure_result)

        # Collect images: prefer /restructure-pages markdown.images (authoritative
        # post-concat set); fall back to /layout-parsing per-page markdown.images.
        restructure_pages = restructure_result.get("layoutParsingResults") or []
        raw_images = (
            (restructure_pages[0].get("markdown") or {}).get("images")
            if restructure_pages
            else None
        )
        if not raw_images:
            raw_images = {}
            for res in layout_result.get("layoutParsingResults", []):
                raw_images.update((res.get("markdown") or {}).get("images") or {})

        # Normalize keys: strip leading imgs/ prefix, keep the page subdirectory.
        # The normalized key matches both the regex capture in
        # extract_images_from_md and the on-disk path from save_images_res_to_local.
        # Using basename would collapse imgs/page1/0.jpg and imgs/page2/0.jpg into
        # one key, dropping/overwriting images.
        images_map: dict[str, str] = {}
        for img_path_key, img_b64 in (raw_images or {}).items():
            img_key = self._strip_imgs_prefix(img_path_key)
            images_map[img_key] = self._to_data_uri(img_key, img_b64)

        json_content = ""
        if return_json:
            json_content = _extract_pruned_result(restructure_result)

        return md_content, json_content, images_map

    # ------------------------------------------------------------------ #
    # static helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def _strip_imgs_prefix(img_path_key: str) -> str:
        """Strip the leading ``imgs/`` prefix, keeping the trailing relative path.

        Official keys look like ``imgs/foo.jpg`` or ``imgs/page1/0.jpg``. After
        stripping, the key matches the regex capture in extract_images_from_md
        and the on-disk path. Keeping the page subdirectory avoids multi-page
        same-name images (page1/0.jpg, page2/0.jpg) collapsing to one key. Keys
        without the prefix are returned unchanged.
        """
        if not img_path_key:
            return img_path_key
        normalized = img_path_key.replace("\\", "/")
        prefix = "imgs/"
        return normalized[len(prefix):] if normalized.startswith(prefix) else normalized

    @staticmethod
    def _to_data_uri(img_name: str, img_b64: str) -> str:
        """Normalize a base64 image into a ``data:`` URI.

        Accepts an already-prefixed ``data:`` URI or a raw base64 string.
        """
        if not img_b64:
            return img_b64
        if img_b64.startswith("data:"):
            return img_b64
        ext = os.path.splitext(img_name)[1].lstrip(".").lower() or "jpeg"
        if ext == "jpg":  # normalize MIME subtype
            ext = "jpeg"
        return f"data:image/{ext};base64,{img_b64}"


def _extract_base_url(url: str) -> str:
    """Extract the base path from a full URL.

    ``https://example.com/path/file.jpg?x=1`` -> ``https://example.com/path/``.
    """
    if not url:
        return ""
    if isinstance(url, bytes):
        url = url.decode("utf-8")
    parsed = urllib.parse.urlparse(url)
    path_parts = parsed.path.rsplit("/", 1)
    base_path = path_parts[0] + "/" if len(path_parts) > 1 else parsed.path
    return f"{parsed.scheme}://{parsed.netloc}{base_path}"


def _extract_markdown_text(restructure_result: dict[str, Any]) -> str:
    """Pull the concatenated markdown text from a restructure-pages result."""
    results = restructure_result.get("layoutParsingResults") or []
    if not results:
        return ""
    return (results[0].get("markdown") or {}).get("text", "")


def _extract_pruned_result(restructure_result: dict[str, Any]) -> str:
    """Pull the structured prunedResult list from a restructure-pages result."""
    results = restructure_result.get("layoutParsingResults") or []
    pruned = [res.get("prunedResult") for res in results]
    try:
        return json.dumps(pruned, ensure_ascii=False)
    except (TypeError, ValueError):
        return ""
