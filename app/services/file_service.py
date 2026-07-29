"""File handling: save uploads, persist extracted images, OCR Excel images."""
from __future__ import annotations

import base64
import os
import re
from typing import Any, Iterable

from app.config import settings
from app.utils.logging_utils import setup_logger

logger = setup_logger(__name__, "./logs/app.log")

RAW_DIR = "./data/raw"
IMAGE_DIR = "./data/images"


def save_file_to_local(file_bytes: bytes, file_name: str) -> str:
    """Save uploaded file bytes to the raw dir; overwrite on name clash."""
    os.makedirs(RAW_DIR, exist_ok=True)
    file_path = os.path.join(RAW_DIR, file_name)
    with open(file_path, "wb") as fh:
        fh.write(file_bytes)
    return file_path


def save_images_res_to_local(results: dict[str, Any]) -> None:
    """Persist base64 images from a parse result to ``IMAGE_DIR``.

    Keys may include a subdirectory (e.g. ``page1/0.jpg``); nested dirs are
    created. Both ``data:image/...;base64,XXX`` and raw base64 are accepted.
    """
    images = results.get("images") or {}
    if not images:
        return
    os.makedirs(IMAGE_DIR, exist_ok=True)
    for filename, data in images.items():
        if "," in data:
            data = data.split(",", 1)[1]
        image_bytes = base64.b64decode(data)
        save_path = os.path.join(IMAGE_DIR, filename)
        save_dir = os.path.dirname(save_path)
        if save_dir:
            os.makedirs(save_dir, exist_ok=True)
        with open(save_path, "wb") as fh:
            fh.write(image_bytes)


def cleanup_temp_files(file_paths: Iterable[str] | None) -> None:
    """Delete temp files (Excel embedded-image temp files); ignore missing/failed."""
    if not file_paths:
        return
    for path in file_paths:
        try:
            os.remove(path)
        except OSError:
            pass


def ocr_excel_images(image_paths: list[str]) -> str:
    """OCR each Excel embedded image via PaddleOCR-VL; return concatenated text.

    MODEL_TYPE-independent: even under a mineru deployment we use PaddleOCR-VL
    to OCR the embedded images (PaddleOCRVLClient is HTTP-only, no heavy deps).
    A single image failing does not affect others (contributes empty text).
    """
    if not image_paths:
        return ""
    try:
        from app.models.paddleocrvl.client import PaddleOCRVLClient
    except Exception as exc:  # noqa: BLE001
        logger.error("load PaddleOCRVLClient failed, Excel images not OCR'd: %s", exc)
        return ""

    client = PaddleOCRVLClient(settings.paddleocrvl_endpoint)
    parts: list[str] = []
    total = len(image_paths)
    for idx, img_path in enumerate(image_paths):
        try:
            resp = client.parse_file(img_path, return_json=False, extract_image=False)
            if resp.get("code") == 200:
                md = resp.get("data", {}).get("md_content", "").strip()
                if md:
                    parts.append(md)
                    logger.info("Excel image %d/%d OCR done", idx + 1, total)
                else:
                    logger.warning("Excel image %d/%d OCR returned empty", idx + 1, total)
            else:
                logger.warning(
                    "Excel image %d/%d OCR failed: %s", idx + 1, total, resp.get("message")
                )
        except Exception as exc:  # noqa: BLE001 — skip one image
            logger.error("Excel image %d/%d OCR error, skipping: %s", idx + 1, total, exc)
            continue
    return "\n\n".join(parts)
