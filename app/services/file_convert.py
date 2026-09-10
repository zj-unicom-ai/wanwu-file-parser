"""File conversion / input validation for the model path.

Office→PDF conversion uses **LibreOffice headless** as an optional local
fallback. When ``libreoffice`` is installed in the container, ``.doc/.docx/
.ppt/.pptx`` files are automatically converted to PDF before being sent to
the OCR backend. When it is not installed, the caller gets a clear
:class:`OfficeConversionNotSupported` error pointing at the ``mineru`` backend
or a pre-converted PDF/image.

Excel (``.xls/.xlsx``) never reaches here: the parser's Excel shortcut reads
cells directly into markdown before the model path runs.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile

from app.utils.logging_utils import setup_logger

logger = setup_logger(__name__, "./logs/app.log")

# Office formats that need conversion before the model can ingest them.
_OFFICE_EXTENSIONS = (".doc", ".docx", ".ppt", ".pptx")
# Inputs the model accepts directly (returned unchanged).
_MODEL_DIRECT_EXTENSIONS = (
    ".pdf", ".png", ".jpg", ".jpeg", ".webp", ".gif", ".tif", ".tiff", ".bmp",
)
# Inputs the model accepts directly (PDF + images). Used by the parser to verify
# the post-conversion path is a valid model input.
MODEL_FILE_EXTENSIONS = _MODEL_DIRECT_EXTENSIONS

# Timeout for LibreOffice headless conversion (seconds).
_LIBREOFFICE_TIMEOUT = 120


class OfficeConversionNotSupported(RuntimeError):
    """Raised when a legacy Office file reaches the model path and no
    ``libreoffice`` binary is available.

    Callers must either install LibreOffice in the container, use the
    ``mineru`` backend (which handles Office natively), or supply a PDF/image.
    """


def _find_libreoffice() -> str | None:
    """Return the path to the LibreOffice executable, or ``None`` if absent.

    Checks common binary names (``libreoffice``, ``soffice``) on ``PATH``.
    """
    for name in ("libreoffice", "soffice"):
        path = shutil.which(name)
        if path:
            return path
    return None


def _try_libreoffice_convert(file_path: str) -> str:
    """Convert an Office file to PDF using LibreOffice headless.

    Returns the path to the generated PDF (in the same directory as the input,
    with ``.pdf`` extension). Raises :class:`OfficeConversionNotSupported` if
    LibreOffice is not installed, or :class:`RuntimeError` if the conversion
    itself fails.
    """
    binary = _find_libreoffice()
    if binary is None:
        raise OfficeConversionNotSupported(
            "Office 文档(.doc/.docx/.ppt/.pptx)需安装 LibreOffice 以支持本地转换，"
            "或使用 mineru 后端解析，或先转换为 PDF/图片。"
            f" file_name: {os.path.basename(file_path)}"
        )

    # LibreOffice cannot write into the same dir as the input in some edge
    # cases; use a temp dir for the output and then move the file.
    out_dir = tempfile.mkdtemp(prefix="lo_convert_")
    try:
        result = subprocess.run(
            [
                binary,
                "--headless",
                "--nologo",
                "--nofirststartwizard",
                "--convert-to", "pdf",
                "--outdir", out_dir,
                file_path,
            ],
            capture_output=True,
            text=True,
            timeout=_LIBREOFFICE_TIMEOUT,
        )
        if result.returncode != 0:
            logger.error(
                "LibreOffice conversion failed (rc=%d): %s",
                result.returncode,
                result.stderr or result.stdout,
            )
            raise RuntimeError(
                f"Office→PDF 转换失败 (LibreOffice rc={result.returncode}). "
                f"file_name: {os.path.basename(file_path)}"
            )

        base = os.path.splitext(os.path.basename(file_path))[0]
        pdf_path = os.path.join(out_dir, f"{base}.pdf")
        if not os.path.exists(pdf_path):
            # LibreOffice sometimes names the output differently; fall back to
            # the first .pdf file in the output directory.
            for fname in os.listdir(out_dir):
                if fname.lower().endswith(".pdf"):
                    pdf_path = os.path.join(out_dir, fname)
                    break
            else:
                raise RuntimeError(
                    "Office→PDF 转换失败：LibreOffice 未生成 PDF 文件. "
                    f"file_name: {os.path.basename(file_path)}"
                )

        # Move the PDF next to the original file so the parser's cleanup logic
        # (which deletes file_path) also cleans up the temp PDF if needed.
        final_path = os.path.join(
            os.path.dirname(file_path),
            os.path.basename(pdf_path),
        )
        shutil.move(pdf_path, final_path)
        logger.info(
            "Office→PDF converted via LibreOffice: %s -> %s",
            os.path.basename(file_path),
            os.path.basename(final_path),
        )
        return final_path
    finally:
        # Clean up the temp dir (shutil.move already removed the PDF from it).
        shutil.rmtree(out_dir, ignore_errors=True)


def convert_to_pdf(file_path: str) -> str:
    """Return a PDF/image path suitable for the model.

    PDFs and images are returned unchanged. Legacy Office formats
    (``.doc/.docx/.ppt/.pptx``) are converted to PDF via LibreOffice headless
    when available; otherwise :class:`OfficeConversionNotSupported` is raised.
    """
    ext = os.path.splitext(file_path)[1].lower()
    if ext in _MODEL_DIRECT_EXTENSIONS:
        return file_path
    if ext in _OFFICE_EXTENSIONS:
        return _try_libreoffice_convert(file_path)
    # Unknown extension: return unchanged and let the caller's model-input
    # check reject it (keeps behavior for any stray non-Office, non-image type).
    logger.warning("convert_to_pdf: unhandled extension %s, passing through", ext)
    return file_path
