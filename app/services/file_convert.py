"""File conversion / input validation for the model path.

There is **no Office→PDF conversion service anymore** (the previous Stirling-PDF
dependency was removed). The model path only ever receives PDFs and images
directly. Legacy Office formats (``.doc/.docx/.ppt/.pptx``) that reach this
point cannot be converted locally and are rejected with a clear message telling
the caller to use the ``mineru`` backend (which handles Office natively) or to
supply a PDF/image instead.

Excel (``.xls/.xlsx``) never reaches here: the parser's Excel shortcut reads
cells directly into markdown before the model path runs.
"""
from __future__ import annotations

import os

from app.utils.logging_utils import setup_logger

logger = setup_logger(__name__, "./logs/app.log")

# Office formats the model cannot ingest directly and we no longer convert.
# (Excel is handled earlier by the Excel shortcut and never reaches the model
# path, so it is intentionally absent here.)
_REJECTED_OFFICE_EXTENSIONS = (".doc", ".docx", ".ppt", ".pptx")
# Inputs the model accepts directly (returned unchanged).
_MODEL_DIRECT_EXTENSIONS = (
    ".pdf", ".png", ".jpg", ".jpeg", ".webp", ".gif", ".tif", ".tiff", ".bmp",
)
# Inputs the model accepts directly (PDF + images). Used by the parser to verify
# the post-conversion path is a valid model input.
MODEL_FILE_EXTENSIONS = _MODEL_DIRECT_EXTENSIONS


class OfficeConversionNotSupported(RuntimeError):
    """Raised when a legacy Office file reaches the model path.

    The model path has no Office→PDF converter (Stirling was removed); callers
    must use the ``mineru`` backend or supply a PDF/image.
    """


def convert_to_pdf(file_path: str) -> str:
    """Return a PDF/image path suitable for the model.

    PDFs and images are returned unchanged. Legacy Office formats
    (``.doc/.docx/.ppt/.pptx``) raise :class:`OfficeConversionNotSupported`:
    there is no conversion service, so the caller surfaces a clear error rather
    than silently dropping the file.
    """
    ext = os.path.splitext(file_path)[1].lower()
    if ext in _MODEL_DIRECT_EXTENSIONS:
        return file_path
    if ext in _REJECTED_OFFICE_EXTENSIONS:
        raise OfficeConversionNotSupported(
            "Office 文档(.doc/.docx/.ppt/.pptx)需使用 mineru 后端解析，或先转换为 PDF/图片；"
            "当前 paddleocrvl 后端不支持本地 Office 转换。"
            f" file_name: {os.path.basename(file_path)}"
        )
    # Unknown extension: return unchanged and let the caller's model-input
    # check reject it (keeps behavior for any stray non-Office, non-image type).
    logger.warning("convert_to_pdf: unhandled extension %s, passing through", ext)
    return file_path
