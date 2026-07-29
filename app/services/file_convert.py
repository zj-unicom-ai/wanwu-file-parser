"""File conversion (Office -> PDF) via the Stirling service.

Case-insensitive extension matching so ``.XLS`` / ``.DOCX`` route into the
converter instead of bypassing it (which made the API report a spurious
"conversion failed").
"""
from __future__ import annotations

import os

import requests

from app.config import settings
from app.utils.logging_utils import setup_logger
from app.utils.monitor_utils import log_time

logger = setup_logger(__name__, "./logs/app.log")

_OFFICE_EXTENSIONS = (".docx", ".doc", ".ppt", ".pptx", ".xls", ".xlsx")
# Inputs the model accepts directly (returned unchanged).
_MODEL_DIRECT_EXTENSIONS = (
    ".pdf", ".png", ".jpg", ".jpeg", ".webp", ".gif", ".tif", ".tiff", ".bmp",
)
# Inputs the model accepts directly (PDF + images). Used by the parser to verify
# the post-conversion path is a valid model input.
MODEL_FILE_EXTENSIONS = _MODEL_DIRECT_EXTENSIONS


def convert_to_pdf(file_path: str) -> str:
    """Return a PDF/image path suitable for the model. Office files are converted
    via Stirling; PDFs/images are returned unchanged."""
    ext = os.path.splitext(file_path)[1].lower()
    if ext == ".pdf" or ext in _MODEL_DIRECT_EXTENSIONS:
        return file_path
    if ext in _OFFICE_EXTENSIONS:
        return libreoffice_to_pdf(file_path)
    return file_path


@log_time
def libreoffice_to_pdf(file_path: str) -> str:
    """Convert an Office file to PDF via the Stirling service.

    Returns the PDF path on success, or the original path on failure (caller
    will then report a conversion error for non-image inputs).
    """
    file_name = os.path.basename(file_path)
    file_dir = os.path.dirname(file_path)
    stem, _ = os.path.splitext(file_name)
    pdf_path = os.path.join(file_dir, f"{stem}.pdf")

    headers = {"accept": "*/*"}
    files = {
        "fileInput": (
            file_name,
            open(file_path, "rb"),  # noqa: SIM115 — closed in finally
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
    }
    try:
        response = requests.post(
            url=settings.stirling_address, headers=headers, files=files, timeout=300
        )
        response.raise_for_status()
        with open(pdf_path, "wb") as pdf:
            pdf.write(response.content)
        logger.info("converted %s -> %s", file_path, pdf_path)
        os.remove(file_path)
        return pdf_path
    except requests.HTTPError as exc:
        logger.error("convert_to_pdf HTTP error: %s", exc)
        return file_path
    except requests.RequestException as exc:
        logger.error("convert_to_pdf request error: %s", exc)
        return file_path
    except Exception as exc:  # noqa: BLE001
        logger.error("convert_to_pdf unknown error: %s", exc)
        return file_path
    finally:
        if "files" in locals() and not files["fileInput"][1].closed:
            files["fileInput"][1].close()
