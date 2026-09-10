"""File conversion / input validation for the model path.

Two Office processing strategies are supported and selected by
``OFFICE_PROCESSING_MODE``:

* ``direct_extract`` — use PaddleOCR's ``doc2md`` CLI to parse Office documents
  directly to Markdown **without OCR inference and without a GPU**.  Only the
  XML-based formats (``.docx`` / ``.xlsx`` / ``.pptx``) are supported; legacy
  binary formats (``.doc`` / ``.ppt``) are rejected.
* ``convert_pdf`` — convert Office documents to PDF via LibreOffice headless,
  then feed the PDF through the normal OCR pipeline.  This is the original
  behaviour.
* ``auto`` (default) — try ``direct_extract`` first for ``.docx`` / ``.pptx``;
  if the ``paddleocr`` CLI is not installed or the conversion fails, fall back
  to ``convert_pdf`` (LibreOffice).  ``.doc`` / ``.ppt`` always go through
  LibreOffice since ``doc2md`` cannot read them.

Excel (``.xls`` / ``.xlsx``) never reaches the model path: the parser's Excel
shortcut reads cells directly into markdown before the model path runs.
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
# Office formats supported by PaddleOCR ``doc2md`` (XML-based only).
_DOC2MD_EXTENSIONS = (".docx", ".pptx")
# Inputs the model accepts directly (returned unchanged).
_MODEL_DIRECT_EXTENSIONS = (
    ".pdf", ".png", ".jpg", ".jpeg", ".webp", ".gif", ".tif", ".tiff", ".bmp",
)
# Inputs the model accepts directly (PDF + images). Used by the parser to verify
# the post-conversion path is a valid model input.
MODEL_FILE_EXTENSIONS = _MODEL_DIRECT_EXTENSIONS

# Timeout for LibreOffice headless conversion (seconds).
_LIBREOFFICE_TIMEOUT = 120
# Timeout for PaddleOCR doc2md conversion (seconds).
_DOC2MD_TIMEOUT = 180


class OfficeConversionNotSupported(RuntimeError):
    """Raised when a legacy Office file reaches the model path and no
    ``libreoffice`` binary is available.

    Callers must either install LibreOffice in the container, use the
    ``mineru`` backend (which handles Office natively), or supply a PDF/image.
    """


class Doc2mdNotAvailable(RuntimeError):
    """Raised when ``OFFICE_PROCESSING_MODE=direct_extract`` is set but the
    ``paddleocr`` CLI (with the ``doc2md`` extra) is not installed."""


# ---------------------------------------------------------------------------
#  PaddleOCR doc2md direct extraction
# ---------------------------------------------------------------------------

def _find_paddleocr_cli() -> str | None:
    """Return the path to the ``paddleocr`` CLI, or ``None`` if absent."""
    return shutil.which("paddleocr")


def _try_doc2md_extract(file_path: str) -> str:
    """Convert an Office document to Markdown via PaddleOCR ``doc2md``.

    No OCR inference runs and no GPU is required — the document XML is parsed
    directly (headings, text, tables as HTML, images, math formulas via
    OMML→LaTeX).  Only ``.docx`` / ``.pptx`` are supported by ``doc2md``.

    Returns the path to the generated ``.md`` file (in the same directory as
    the input).  Raises :class:`Doc2mdNotAvailable` if the ``paddleocr`` CLI is
    not installed, or :class:`RuntimeError` on conversion failure.
    """
    binary = _find_paddleocr_cli()
    if binary is None:
        raise Doc2mdNotAvailable(
            "Office 文档直接提取需要 paddleocr[doc2md]（pip install "
            "\"paddleocr[doc2md]\"）。或设置 OFFICE_PROCESSING_MODE=convert_pdf "
            "使用 LibreOffice→PDF→OCR 路径。"
            f" file_name: {os.path.basename(file_path)}"
        )

    out_dir = tempfile.mkdtemp(prefix="doc2md_")
    try:
        result = subprocess.run(
            [
                binary,
                "doc2md",
                "-i", file_path,
                "-o", out_dir,
            ],
            capture_output=True,
            text=True,
            timeout=_DOC2MD_TIMEOUT,
        )
        if result.returncode != 0:
            logger.error(
                "doc2md conversion failed (rc=%d): %s",
                result.returncode,
                result.stderr or result.stdout,
            )
            raise RuntimeError(
                f"Office→Markdown 转换失败 (paddleocr doc2md rc={result.returncode}). "
                f"file_name: {os.path.basename(file_path)}"
            )

        # doc2md writes <basename>.md into the output directory.
        base = os.path.splitext(os.path.basename(file_path))[0]
        md_path = os.path.join(out_dir, f"{base}.md")
        if not os.path.exists(md_path):
            # Fall back to the first .md file in the output directory.
            for fname in os.listdir(out_dir):
                if fname.lower().endswith(".md"):
                    md_path = os.path.join(out_dir, fname)
                    break
            else:
                raise RuntimeError(
                    "Office→Markdown 转换失败：doc2md 未生成 Markdown 文件. "
                    f"file_name: {os.path.basename(file_path)}"
                )

        # Move the Markdown next to the original file so the parser's cleanup
        # logic (which deletes file_path) also cleans up the temp .md if needed.
        final_path = os.path.join(
            os.path.dirname(file_path),
            os.path.basename(md_path),
        )
        shutil.move(md_path, final_path)
        logger.info(
            "Office→Markdown extracted via doc2md: %s -> %s",
            os.path.basename(file_path),
            os.path.basename(final_path),
        )
        return final_path
    finally:
        shutil.rmtree(out_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
#  LibreOffice headless Office→PDF conversion
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
#  Public API
# ---------------------------------------------------------------------------

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


def extract_office_to_markdown(file_path: str) -> str:
    """Extract Office document content to Markdown via PaddleOCR ``doc2md``.

    This is a **CPU-only** path — no OCR model inference, no GPU required.
    PaddleOCR's ``doc2md`` parses the document XML directly to produce
    structured Markdown (headings, text, tables as HTML, images, math formulas
    via OMML→LaTeX, speaker notes).

    Supported formats: ``.docx`` (Word), ``.pptx`` (PowerPoint).
    Legacy binary formats (``.doc`` / ``.ppt``) are **not** supported by
    ``doc2md`` and will raise :class:`RuntimeError`.

    Returns the path to the generated ``.md`` file. Raises:
      * :class:`Doc2mdNotAvailable` — ``paddleocr`` CLI not installed.
      * :class:`RuntimeError` — conversion failed or format unsupported.
    """
    ext = os.path.splitext(file_path)[1].lower()
    if ext not in _DOC2MD_EXTENSIONS:
        raise RuntimeError(
            f"doc2md 不支持 {ext} 格式（仅支持 .docx / .pptx）。"
            f" 请设置 OFFICE_PROCESSING_MODE=convert_pdf 或 auto 使用 LibreOffice 路径。"
            f" file_name: {os.path.basename(file_path)}"
        )
    return _try_doc2md_extract(file_path)
