"""MinerU 3.0 API client (HTTP-only, multipart /file_parse).

The endpoint is the full URL resolved by ``settings.mineru_api_endpoint`` (which
includes ``/file_parse``). The client POSTs to it directly and appends no path,
avoiding the historical double-``/file_parse`` bug.
"""
from __future__ import annotations

import base64
import mimetypes
import os
import re
import urllib.parse
from typing import Any

import requests

from app.config import settings
from app.utils.logging_utils import setup_logger
from app.utils.monitor_utils import log_time
from app.utils.storage.factory import StorageFactory

logger = setup_logger(__name__, "./logs/client.log")

_REQUEST_TIMEOUT_SECONDS = 3600


class MineruClient:
    """HTTP client for the MinerU 3.0 ``/file_parse`` API."""

    def __init__(self, base_url: str) -> None:
        # base_url is already the full endpoint (from settings.mineru_api_endpoint);
        # POST directly, never append a path.
        self.base_url = (base_url or "").rstrip("/")

    @log_time
    def parse_file(
        self,
        file_path: str,
        return_json: bool = False,
        extract_image: bool = False,
        extract_image_content: int = 0,
    ) -> dict[str, Any]:
        """Parse a document via MinerU ``/file_parse`` (multipart)."""
        # MINERU_EFFORT overrides the extract_image_content argument.
        env_effort = settings.mineru_effort.strip().lower()
        if env_effort:
            extract_image_content = 1 if env_effort in ("true", "1", "high") else 0

        endpoint = self.base_url
        file_name = os.path.basename(file_path)

        mime_type, _ = mimetypes.guess_type(file_path)
        if mime_type is None:
            mime_type = "application/octet-stream"

        payload = {
            "return_md": "true",
            "formula_enable": "true",
            "table_enable": "true",
            "return_content_list": "true" if return_json else "false",
            "return_images": "true" if extract_image else "false",
            "lang_list": [settings.mineru_lang_list],
            "backend": settings.mineru_backend,
            "effort": "high" if extract_image_content else "medium",
            "parse_method": settings.mineru_parse_method,
        }
        if settings.mineru_server_url:
            payload["server_url"] = settings.mineru_server_url

        logger.info("MinerU parse_file payload: %s", payload)

        with open(file_path, "rb") as file_obj:
            files = [("files", (file_name, file_obj, mime_type))]
            try:
                response = requests.post(
                    endpoint, data=payload, files=files, timeout=_REQUEST_TIMEOUT_SECONDS
                )
                response.raise_for_status()
                data = response.json()
                logger.info("MinerU response status: %s", data.get("status"))
                return data
            except requests.HTTPError as exc:
                logger.error("MinerU request failed, status: %s", exc.response.status_code)
                raise
            except requests.RequestException as exc:
                logger.error("MinerU request error: %s", exc)
                raise

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
        """Extract md_content, upload images to storage, rewrite image refs.

        Returns ``(md_content, json_content, prefix_image_url)``.
        """
        del extract_image_content, file_path
        file_key = os.path.splitext(file_name)[0]
        result = response.get("results", {}).get(file_key, {})
        md_content = result.get("md_content", "")
        images: dict[str, str] = result.get("images", {})

        json_content = ""
        if return_json:
            content_list = result.get("content_list")
            if content_list:
                json_content = content_list

        default_prefix = settings.prefix_image_url
        prefix_image_url = default_prefix

        if extract_image and images and md_content:
            image_output_dir = "./data/images"
            os.makedirs(image_output_dir, exist_ok=True)

            url_map: dict[str, str] = {}
            for img_filename, data_uri in images.items():
                try:
                    _, b64_data = data_uri.split(",", 1)
                    image_data = base64.b64decode(b64_data)
                    save_path = os.path.join(image_output_dir, img_filename)
                    os.makedirs(os.path.dirname(save_path) or ".", exist_ok=True)
                    with open(save_path, "wb") as fh:
                        fh.write(image_data)

                    storage = StorageFactory.get_storage()
                    download_link = storage.upload_file(save_path)
                    url_map[img_filename] = download_link
                    os.remove(save_path)
                    logger.info("image %s uploaded: %s", img_filename, download_link)
                    prefix_image_url = download_link
                except Exception as exc:  # noqa: BLE001 — skip one bad image
                    logger.error("process image %s failed, skipping: %s", img_filename, exc)
                    continue

            if url_map:
                md_content = _rewrite_image_links(md_content, url_map)

        # Only derive the prefix from an uploaded URL when one was actually
        # produced; comparing against the literal default would break if the
        # configured default ever changes.
        if prefix_image_url != default_prefix:
            prefix_image_url = _extract_base_url(prefix_image_url)

        return md_content, json_content, prefix_image_url


def _rewrite_image_links(md_content: str, url_map: dict[str, str]) -> str:
    """Replace ``![](images/x.jpg)`` / ``![](x.jpg)`` with the uploaded URL."""

    def _replace(match: re.Match[str]) -> str:
        img_path = match.group(1)
        img_name = os.path.basename(img_path)
        oss_url = url_map.get(img_name)
        return f"![]({oss_url})" if oss_url else match.group(0)

    return re.sub(r"!\[\]\(([^)]+)\)", _replace, md_content)


def _extract_base_url(url: str) -> str:
    """``https://example.com/path/file.jpg?x=1`` -> ``https://example.com/path/``."""
    if not url:
        return ""
    parsed = urllib.parse.urlparse(url)
    path_parts = parsed.path.rsplit("/", 1)
    base_path = path_parts[0] + "/" if len(path_parts) > 1 else parsed.path
    return f"{parsed.scheme}://{parsed.netloc}{base_path}"
