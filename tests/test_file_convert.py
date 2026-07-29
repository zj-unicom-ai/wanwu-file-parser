"""file_convert tests: case-insensitive Office routing."""
from __future__ import annotations

import pytest

from app.services import file_convert as fc


class TestConvertToPdf:
    @pytest.mark.parametrize("ext", [".xls", ".XLS", ".xlsx", ".XLSX", ".docx", ".DOCX", ".ppt", ".PPTX"])
    def test_office_extensions_route_to_libreoffice(self, ext, monkeypatch):
        called = {"flag": False}

        def fake_libreoffice(path):
            called["flag"] = True
            return path  # don't really convert; just verify routing

        monkeypatch.setattr(fc, "libreoffice_to_pdf", fake_libreoffice)
        result = fc.convert_to_pdf(f"/tmp/report{ext}")
        assert called["flag"] is True, f"{ext} did not route to converter"
        assert result == f"/tmp/report{ext}"

    @pytest.mark.parametrize("ext", [".pdf", ".PDF", ".png", ".PNG", ".jpg", ".webp"])
    def test_pdf_and_image_returned_unchanged(self, ext, monkeypatch):
        called = {"flag": False}
        monkeypatch.setattr(fc, "libreoffice_to_pdf", lambda p: called.__setitem__("flag", True))
        result = fc.convert_to_pdf(f"/tmp/file{ext}")
        assert result == f"/tmp/file{ext}"
        assert called["flag"] is False
