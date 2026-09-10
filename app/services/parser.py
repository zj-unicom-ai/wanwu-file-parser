"""Parse orchestration: Excel shortcut, conversion, model dispatch."""
from __future__ import annotations

import os
from dataclasses import dataclass

from app.config import settings
from app.models.base import OcrClient
from app.models.strategy import CLIENT_STRATEGIES
from app.services.excel_service import excel_to_markdown
from app.services.file_convert import (
    MODEL_FILE_EXTENSIONS,
    OfficeConversionNotSupported,
    convert_to_pdf,
    extract_office_to_markdown,
)
from app.services.file_service import cleanup_temp_files, ocr_excel_images
from app.utils.logging_utils import setup_logger

logger = setup_logger(__name__, "./logs/app.log")

ALLOWED_FILE_EXTENSIONS = (
    ".pdf", ".png", ".jpeg", ".jpg", ".webp", ".gif", ".tif", ".tiff", ".bmp",
    ".docx", ".doc", ".ppt", ".pptx", ".xls", ".xlsx",
)
IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".tif", ".tiff", ".bmp")

# Office extensions that PaddleOCR ``doc2md`` can handle (XML-based formats).
_DOC2MD_OFFICE_EXTENSIONS = (".docx", ".pptx")
# All Office extensions that may need processing.
_OFFICE_EXTENSIONS = (".doc", ".docx", ".ppt", ".pptx")


def is_allowed_filename(name: str) -> bool:
    return name.lower().endswith(ALLOWED_FILE_EXTENSIONS)


def is_path_traversal(name: str) -> bool:
    """Reject filenames that escape the save dir (.., leading / or \\)."""
    normalized = os.path.normpath(name)
    return normalized.startswith(("..", "/", "\\"))


@dataclass
class ParseRequest:
    file_bytes: bytes
    file_name: str
    extract_image: bool
    extract_image_content: int
    return_json: bool


# Module-level client cache (lazy: built on first request, survives across
# requests). Mirrors the upstream "lazy init" design so a misconfigured backend
# never breaks process startup.
_client: OcrClient | None = None


def get_client() -> OcrClient:
    global _client
    if _client is None:
        _client = CLIENT_STRATEGIES[settings.model_type]()
    return _client


def reset_client() -> None:
    """Drop the cached client (for tests)."""
    global _client
    _client = None


def parse_document(req: ParseRequest) -> tuple[str, str, str]:
    """Run the full parse pipeline; return (md_content, json_content, prefix_image_url)."""
    file_path = _save(req)
    # Track intermediate files (e.g. Office→PDF) so the finally block can clean
    # them all up. ``file_path`` may be reassigned by convert_to_pdf below.
    extra_files: list[str] = []
    try:
        # Excel shortcut first: a no-image xlsx returns markdown without ever
        # building the model client (so a misconfigured OCR endpoint can't break
        # plain-Excel parsing).
        md, json_content, prefix = _try_excel_shortcut(req, file_path)
        if md is not None:
            return md, json_content, prefix

        # Office doc2md direct extraction shortcut: for .docx/.pptx, try
        # PaddleOCR doc2md (CPU-only, no GPU needed) to extract Markdown
        # directly. This avoids the LibreOffice→PDF→OCR pipeline entirely.
        md, json_content, prefix = _try_doc2md_shortcut(req, file_path)
        if md is not None:
            return md, json_content, prefix

        client = get_client()

        # Convert Office -> PDF for non-mineru backends (mineru handles Office
        # natively). LibreOffice headless is used when available; otherwise
        # OfficeConversionNotSupported is raised and the API returns a 400.
        if settings.model_type != "mineru":
            original_path = file_path
            file_path = convert_to_pdf(file_path)
            # If conversion produced a new file, track the original for cleanup.
            if file_path != original_path:
                extra_files.append(original_path)
            if not file_path.lower().endswith(MODEL_FILE_EXTENSIONS):
                raise RuntimeError(
                    f"File type supported, but convert to model input (pdf/image) failed. "
                    f"Check the file converter service. file_name: {req.file_name}"
                )

        # Images need no further image extraction.
        extract_image = req.extract_image
        if file_path.lower().endswith(IMAGE_EXTENSIONS):
            extract_image = False
            logger.info("image file detected, force extract_image=False")

        logger.info("start to parse file: %s", req.file_name)
        response = client.parse_file(
            file_path, req.return_json, extract_image, req.extract_image_content
        )
        logger.info("parse done; post-processing: %s", file_path)
        md, json_content, prefix = client.post_process(
            extract_image=extract_image,
            extract_image_content=req.extract_image_content,
            file_name=req.file_name,
            file_path=file_path,
            return_json=req.return_json,
            response=response,
        )
        logger.info("post process done: %s", file_path)
        return md, json_content, prefix
    finally:
        # Clean up the current file_path (may be the converted PDF) plus any
        # intermediate files (the original Office document).
        for path in [file_path, *extra_files]:
            try:
                os.remove(path)
            except OSError as exc:
                logger.error("delete file failed: %s", exc)


def _save(req: ParseRequest) -> str:
    from app.services.file_service import save_file_to_local

    return save_file_to_local(req.file_bytes, req.file_name)


def _try_excel_shortcut(
    req: ParseRequest, file_path: str
) -> tuple[str | None, str, str]:
    """Attempt the Excel shortcut. Returns (md, json, prefix).

    md is None when the caller should fall through to the model path.
    """
    if not file_path.lower().endswith((".xlsx", ".xls")):
        return None, "", ""

    try:
        excel_md, has_images, image_paths = excel_to_markdown(file_path)
    except Exception as exc:  # noqa: BLE001 — text-only degradation
        logger.warning("Excel -> markdown failed, returning empty text (no OCR fallback): %s", exc)
        return "", "", settings.prefix_image_url

    # .xls (image_paths is None) -> BEST-EFFORT text-only: no images to OCR, and
    # the model path can't convert .xls (no Stirling). Return whatever text we
    # got (even empty) rather than falling through to an unsupported conversion.
    # .xls is a legacy format; users should convert to .xlsx for full support.
    if image_paths is None:
        logger.info("Excel (.xls) best-effort text-only result: %s", req.file_name)
        return excel_md, "", settings.prefix_image_url

    # No images + has text -> return markdown directly.
    if not has_images and excel_md:
        logger.info("Excel has no images, returning markdown directly: %s", req.file_name)
        return excel_md, "", settings.prefix_image_url

    # Has images -> keep text, OCR each image, concatenate.
    if has_images:
        try:
            ocr_md = ocr_excel_images(image_paths)
        except Exception as exc:  # noqa: BLE001 — keep text only
            logger.error("Excel image OCR failed entirely, returning text only: %s", exc)
            ocr_md = ""
        finally:
            cleanup_temp_files(image_paths)
        final = "\n\n".join(p for p in (excel_md, ocr_md) if p)
        logger.info(
            "Excel text+image done (%d image(s) OCR'd): %s", len(image_paths), req.file_name
        )
        return final, "", settings.prefix_image_url

    # Empty .xlsx table -> no text and no images. The model path cannot convert
    # Office (no Stirling), so return empty text rather than error out.
    logger.info("Excel converted to empty, returning empty text: %s", req.file_name)
    return "", "", settings.prefix_image_url


def _try_doc2md_shortcut(
    req: ParseRequest, file_path: str
) -> tuple[str | None, str, str]:
    """Attempt Office doc2md direct extraction.

    Returns (md, json, prefix). md is None when the caller should fall through
    to the model path (i.e. the file is not an Office document, or the mode
    is ``convert_pdf``).

    Mode behaviour:
      * ``convert_pdf`` — skip doc2md entirely; return None so the caller
        falls through to LibreOffice→PDF→OCR.
      * ``direct_extract`` — use doc2md only. If the paddleocr CLI is not
        installed or the conversion fails, raise an error (no fallback).
      * ``auto`` (default) — try doc2md first for .docx/.pptx; on any failure
        (CLI missing, conversion error, unsupported format), fall back to
        the convert_pdf path (return None).
    """
    ext = file_path.lower()
    mode = settings.office_processing_mode

    # convert_pdf mode: skip doc2md, fall through to LibreOffice→PDF→OCR.
    if mode == "convert_pdf":
        return None, "", ""

    # Only .docx/.pptx are eligible for doc2md; .doc/.ppt and non-Office files
    # fall through to the model path (LibreOffice or direct).
    if not ext.endswith(_DOC2MD_OFFICE_EXTENSIONS):
        # In direct_extract mode, .doc/.ppt are unsupported by doc2md — but
        # we still return None here and let the downstream convert_to_pdf /
        # model path handle them (they'll get a clear error there).
        return None, "", ""

    # Try doc2md extraction.
    try:
        md_path = extract_office_to_markdown(file_path)
    except Exception as exc:
        # direct_extract mode: no fallback, raise.
        if mode == "direct_extract":
            raise
        # auto mode: log and fall back to convert_pdf path.
        logger.warning(
            "doc2md direct extraction failed, falling back to convert_pdf: %s",
            exc,
        )
        return None, "", ""

    # Read the extracted Markdown.
    try:
        with open(md_path, "r", encoding="utf-8") as f:
            md_content = f.read()
    finally:
        # Clean up the temp .md file.
        try:
            os.remove(md_path)
        except OSError:
            pass

    logger.info(
        "Office doc2md direct extraction done (%d chars): %s",
        len(md_content),
        req.file_name,
    )
    return md_content, "", settings.prefix_image_url
