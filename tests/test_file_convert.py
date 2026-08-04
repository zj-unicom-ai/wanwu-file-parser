"""file_convert tests: PDF/image passthrough + Office rejection.

The Stirling→PDF conversion path is gone. Now ``convert_to_pdf`` only passes
PDFs/images through; legacy Office formats (``.doc/.docx/.ppt/.pptx``) raise
:class:`OfficeConversionNotSupported` (caller must use the mineru backend or
supply a PDF/image). Excel never reaches here (handled by the Excel shortcut).
"""
from __future__ import annotations

import pytest

from app.services import file_convert as fc
from app.services.file_convert import OfficeConversionNotSupported


class TestConvertToPdf:
    @pytest.mark.parametrize("ext", [".pdf", ".PDF", ".png", ".PNG", ".jpg", ".webp"])
    def test_pdf_and_image_returned_unchanged(self, ext):
        result = fc.convert_to_pdf(f"/tmp/file{ext}")
        assert result == f"/tmp/file{ext}"

    @pytest.mark.parametrize("ext", [".doc", ".DOCX", ".ppt", ".PPTX"])
    def test_office_extensions_are_rejected(self, ext):
        with pytest.raises(OfficeConversionNotSupported) as exc_info:
            fc.convert_to_pdf(f"/tmp/report{ext}")
        # The error message must point the caller at the mineru backend / a PDF.
        msg = str(exc_info.value)
        assert "mineru" in msg
        assert "report" in msg  # basename surfaced for context

    def test_unknown_extension_passes_through(self):
        # Non-Office, non-image types are returned unchanged (caller's model-input
        # check rejects them downstream).
        assert fc.convert_to_pdf("/tmp/file.xyz") == "/tmp/file.xyz"
