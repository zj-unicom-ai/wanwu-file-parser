"""file_convert tests: PDF/image passthrough + Office conversion via LibreOffice.

LibreOffice headless is used as an optional Office→PDF converter:
- When ``libreoffice``/``soffice`` is on ``PATH``, Office files are converted.
- When it is absent, :class:`OfficeConversionNotSupported` is raised with a
  message pointing at the ``mineru`` backend or a pre-converted PDF/image.

Excel never reaches here (handled by the Excel shortcut in the parser).
"""
from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from app.services import file_convert as fc
from app.services.file_convert import OfficeConversionNotSupported


class TestConvertToPdf:
    @pytest.mark.parametrize("ext", [".pdf", ".PDF", ".png", ".PNG", ".jpg", ".webp"])
    def test_pdf_and_image_returned_unchanged(self, ext):
        result = fc.convert_to_pdf(f"/tmp/file{ext}")
        assert result == f"/tmp/file{ext}"

    def test_unknown_extension_passes_through(self):
        # Non-Office, non-image types are returned unchanged (caller's model-input
        # check rejects them downstream).
        assert fc.convert_to_pdf("/tmp/file.xyz") == "/tmp/file.xyz"


class TestOfficeNoLibreOffice:
    """When LibreOffice is not installed, Office files raise a clear error."""

    @pytest.mark.parametrize("ext", [".doc", ".DOCX", ".ppt", ".PPTX"])
    def test_office_extensions_raise_without_libreoffice(self, ext):
        with patch.object(fc, "_find_libreoffice", return_value=None):
            with pytest.raises(OfficeConversionNotSupported) as exc_info:
                fc.convert_to_pdf(f"/tmp/report{ext}")
        msg = str(exc_info.value)
        assert "LibreOffice" in msg or "mineru" in msg
        assert "report" in msg  # basename surfaced for context


class TestOfficeWithLibreOffice:
    """When LibreOffice is installed, Office files are converted to PDF."""

    def test_docx_converted_to_pdf(self, tmp_path):
        """Simulate LibreOffice conversion: mock subprocess.run to produce a PDF."""
        docx_path = tmp_path / "report.docx"
        docx_path.write_bytes(b"fake docx content")

        def fake_run(cmd, **kwargs):
            # LibreOffice writes <basename>.pdf into --outdir
            out_dir = cmd[cmd.index("--outdir") + 1]
            base = os.path.splitext(os.path.basename(cmd[-1]))[0]
            pdf_path = os.path.join(out_dir, f"{base}.pdf")
            with open(pdf_path, "w") as f:
                f.write("%PDF-1.4 fake pdf")
            # Return a mock CompletedProcess-like object
            class _Result:
                returncode = 0
                stdout = ""
                stderr = ""
            return _Result()

        with patch.object(fc, "_find_libreoffice", return_value="/usr/bin/libreoffice"):
            with patch("subprocess.run", side_effect=fake_run):
                result = fc.convert_to_pdf(str(docx_path))

        assert result.endswith("report.pdf")
        assert os.path.exists(result)
        # The converted PDF should be in the same directory as the original file
        assert os.path.dirname(result) == str(tmp_path)

    def test_pptx_converted_to_pdf(self, tmp_path):
        """Same as docx but for .pptx extension."""
        pptx_path = tmp_path / "slides.pptx"
        pptx_path.write_bytes(b"fake pptx content")

        def fake_run(cmd, **kwargs):
            out_dir = cmd[cmd.index("--outdir") + 1]
            base = os.path.splitext(os.path.basename(cmd[-1]))[0]
            pdf_path = os.path.join(out_dir, f"{base}.pdf")
            with open(pdf_path, "w") as f:
                f.write("%PDF-1.4 fake pdf")
            class _Result:
                returncode = 0
                stdout = ""
                stderr = ""
            return _Result()

        with patch.object(fc, "_find_libreoffice", return_value="/usr/bin/libreoffice"):
            with patch("subprocess.run", side_effect=fake_run):
                result = fc.convert_to_pdf(str(pptx_path))

        assert result.endswith("slides.pdf")
        assert os.path.exists(result)

    def test_libreoffice_failure_raises_runtime_error(self, tmp_path):
        """If LibreOffice exits non-zero, RuntimeError is raised."""
        docx_path = tmp_path / "broken.docx"
        docx_path.write_bytes(b"broken content")

        class _Result:
            returncode = 1
            stdout = ""
            stderr = "conversion failed"
        with patch.object(fc, "_find_libreoffice", return_value="/usr/bin/libreoffice"):
            with patch("subprocess.run", return_value=_Result()):
                with pytest.raises(RuntimeError) as exc_info:
                    fc.convert_to_pdf(str(docx_path))
        assert "rc=1" in str(exc_info.value) or "转换失败" in str(exc_info.value)

    def test_libreoffice_no_pdf_output_raises_runtime_error(self, tmp_path):
        """LibreOffice succeeds but produces no PDF -> RuntimeError."""
        docx_path = tmp_path / "empty.docx"
        docx_path.write_bytes(b"empty content")

        def fake_run(cmd, **kwargs):
            out_dir = cmd[cmd.index("--outdir") + 1]
            # Don't create any PDF file
            os.makedirs(out_dir, exist_ok=True)
            class _Result:
                returncode = 0
                stdout = ""
                stderr = ""
            return _Result()

        with patch.object(fc, "_find_libreoffice", return_value="/usr/bin/libreoffice"):
            with patch("subprocess.run", side_effect=fake_run):
                with pytest.raises(RuntimeError) as exc_info:
                    fc.convert_to_pdf(str(docx_path))
        assert "未生成 PDF" in str(exc_info.value) or "转换失败" in str(exc_info.value)
