"""Excel → Markdown direct conversion (in-CPU, no PDF / no third-party service).

Excel never goes through Stirling→PDF→OCR: OCR misaligns table cells, so we read
cells directly into a markdown table and preserve the text.

Per-format handling:
  - .xlsx: openpyxl reads cells AND detects/extracts embedded images
    (``ws._images[i]._data()``). With images, cell text (markdown) is kept and
    the image bytes are extracted to temp files for the caller to send to
    PaddleOCR-VL — we do NOT full-page-OCR the sheet (that would drop the text).
  - .xls: xlrd reads cells the same way (text/tables preserved) but cannot
    extract embedded images. So .xls drops images and returns text-only
    markdown. (Earlier this fell back to full-page OCR via Stirling→PDF; that
    path is gone now — text without images beats a lossy OCR of the whole sheet.)

Returns ``(markdown, has_images, image_paths)`` where:
  - .xlsx no images   -> (md, False, [])
  - .xlsx with images -> (md, True, [temp paths...])
  - .xls              -> (md, False, [])   # images unavailable, dropped
"""
from __future__ import annotations

import os
import tempfile
from typing import Optional

import pandas as pd

from app.utils.logging_utils import setup_logger

logger = setup_logger(__name__, "./logs/app.log")

_EXCEL_EXTENSIONS = (".xlsx", ".xls")
# Extensions the OCR image path supports (used to normalize extracted image fmt).
_OCR_IMAGE_EXTS = ("png", "jpg", "jpeg", "gif", "webp", "tif", "tiff", "bmp")


def _read_sheets(file_path: str) -> dict[str, pd.DataFrame]:
    """Read all sheets; dtype=str preserves raw text (no number/date rewrites)."""
    ext = os.path.splitext(file_path)[1].lower()
    if ext == ".xlsx":
        engine = "openpyxl"
    elif ext == ".xls":
        engine = "xlrd"
    else:
        raise ValueError(f"Unsupported excel extension: {ext}")
    # dtype=str keeps original text; keep_default_na=False avoids literal "NaN".
    return pd.read_excel(
        file_path, sheet_name=None, engine=engine, dtype=str, keep_default_na=False
    )


def extract_embedded_images(file_path: str) -> Optional[list[str]]:
    """Extract .xlsx embedded images to temp files -> [path, ...].

    - .xlsx: openpyxl reads ``ws._images``; each image's ``_data()`` gives bytes
      and ``format`` gives the extension; written to a temp file.
    - .xls: xlrd cannot extract images -> None sentinel. The caller treats .xls
      as text-only (images dropped), NOT as a full-page-OCR trigger.
    - .xlsx read failure -> None (the caller then has text from ``_read_sheets``
      but no images — same text-only outcome).

    The caller is responsible for deleting the returned temp files.
    """
    ext = os.path.splitext(file_path)[1].lower()
    if ext != ".xlsx":
        return None
    try:
        from openpyxl import load_workbook

        wb = load_workbook(file_path, read_only=False, data_only=True)
    except Exception as exc:  # noqa: BLE001
        logger.warning("read excel images failed; images will be dropped: %s", exc)
        return None

    image_paths: list[str] = []
    for ws in wb.worksheets:
        for img in (getattr(ws, "_images", None) or []):
            try:
                raw = img._data()
                fmt = (getattr(img, "format", None) or "png").lower()
                if fmt == "jpeg":
                    fmt = "jpg"
                if fmt not in _OCR_IMAGE_EXTS:
                    fmt = "png"
                tmp = tempfile.NamedTemporaryFile(suffix=f".{fmt}", delete=False)
                tmp.write(raw)
                tmp.close()
                image_paths.append(tmp.name)
            except Exception as exc:  # noqa: BLE001 — skip one bad image
                logger.warning("extract one image failed, skipping: %s", exc)
                continue
    return image_paths


def _escape_cell(value) -> str:
    """Escape a cell: newlines->space, pipes->\\|, trim; None->empty."""
    if value is None:
        return ""
    text = str(value).replace("\r", " ").replace("\n", " ").strip()
    return text.replace("|", "\\|")


def _sheet_to_markdown(sheet_name: str, df: pd.DataFrame) -> str:
    """One sheet -> markdown table; empty sheets skipped."""
    if df.empty:
        return ""
    headers = [str(c) for c in df.columns]
    rows = [[_escape_cell(v) for v in row] for row in df.itertuples(index=False, name=None)]
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(row) + " |")
    return f"## {sheet_name}\n\n" + "\n".join(lines) + "\n"


def excel_to_markdown(file_path: str) -> tuple[str, bool, Optional[list[str]]]:
    """Convert an Excel file to markdown and extract embedded images.

    Returns ``(markdown, has_images, image_paths)`` (see module docstring).
    """
    ext = os.path.splitext(file_path)[1].lower()
    image_paths = extract_embedded_images(file_path)

    # .xls (image_paths is None) -> text-only: no image extraction possible, but
    # we still read the cells into a markdown table. Images are dropped.
    if image_paths is None:
        if ext == ".xls":
            logger.info("Excel (.xls) text-only (images unavailable, dropped): %s", file_path)
        sheets = _read_sheets(file_path)
        parts = [_sheet_to_markdown(name, df) for name, df in sheets.items()]
        markdown = "\n".join(p for p in parts if p).strip()
        return markdown, False, []

    has_images = bool(image_paths)

    sheets = _read_sheets(file_path)
    parts = [_sheet_to_markdown(name, df) for name, df in sheets.items()]
    markdown = "\n".join(p for p in parts if p).strip()

    if has_images:
        logger.info(
            "Excel has %d embedded images; keeping text + sending images to OCR: %s",
            len(image_paths),
            file_path,
        )
    else:
        logger.info("Excel -> markdown done, %d sheet(s): %s", len(sheets), file_path)
    return markdown, has_images, image_paths
