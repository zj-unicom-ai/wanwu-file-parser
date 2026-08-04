"""API integration tests via FastAPI TestClient."""
from __future__ import annotations

import io
from unittest.mock import patch

import openpyxl
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.services import parser


@pytest.fixture()
def client():
    return TestClient(create_app())


@pytest.fixture(autouse=True)
def _reset_client():
    parser.reset_client()
    yield
    parser.reset_client()


class TestHealth:
    def test_health(self, client):
        resp = client.get("/rag/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "healthy"


class TestValidation:
    def test_missing_file(self, client):
        resp = client.post("/rag/model_parser_file")
        assert resp.status_code == 422  # FastAPI form validation (file required)

    def test_bad_extension(self, client):
        resp = client.post(
            "/rag/model_parser_file",
            files={"file": ("a.txt", b"x", "text/plain")},
            data={"file_name": "a.txt"},
        )
        assert resp.status_code == 400
        assert resp.json()["status"] == "failed"

    def test_path_traversal(self, client):
        resp = client.post(
            "/rag/model_parser_file",
            files={"file": ("../evil.pdf", b"x", "application/pdf")},
            data={"file_name": "../evil.pdf"},
        )
        assert resp.status_code == 400
        assert "非法字符" in resp.json()["message"]


class TestExcelShortcut:
    def _make_xlsx(self, path):
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["姓名", "年龄"])
        ws.append(["张三", "30"])
        wb.save(path)
        return path

    def test_xlsx_no_image_short_circuits(self, client, tmp_path):
        # The Excel shortcut must NOT call the OCR model.
        p = self._make_xlsx(tmp_path / "plain.xlsx")
        with patch("app.services.parser.get_client") as mock_get:
            with open(p, "rb") as fh:
                resp = client.post(
                    "/rag/model_parser_file",
                    files={"file": ("plain.xlsx", fh.read(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
                    data={"file_name": "plain.xlsx"},
                )
            # Model client must never be instantiated/used for no-image xlsx.
            mock_get.assert_not_called()
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "success"
        assert "张三" in body["content"]
        assert body["prefix_image_url"]  # populated from config default

    def test_xlsx_with_image_ocrs_image_and_keeps_text(self, client, tmp_path):
        import base64

        from openpyxl.drawing.image import Image as XLImage

        png = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
        )
        p = tmp_path / "mixed.xlsx"
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["姓名", "年龄"])
        ws.append(["张三", "30"])
        ws.add_image(XLImage(io.BytesIO(png)), "A5")
        wb.save(p)

        # Stub PaddleOCRVLClient so no real OCR service is needed. The client is
        # imported lazily inside ocr_excel_images, so patch at its definition site.
        with patch("app.models.paddleocrvl.client.PaddleOCRVLClient") as MockClient:
            MockClient.return_value.parse_file.return_value = {
                "code": 200,
                "message": "ok",
                "data": {"md_content": "<IMG-OCR>", "json_data": "", "images": {}},
            }
            with open(p, "rb") as fh:
                resp = client.post(
                    "/rag/model_parser_file",
                    files={"file": ("mixed.xlsx", fh.read(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
                    data={"file_name": "mixed.xlsx"},
                )
        assert resp.status_code == 200
        body = resp.json()
        assert "张三" in body["content"]      # text kept
        assert "<IMG-OCR>" in body["content"]  # image OCR appended
        # The image OCR path was exercised exactly once (one image).
        assert MockClient.return_value.parse_file.call_count == 1


class TestLegacyXls:
    def test_xls_returns_text_without_pdf_or_ocr(self, client, tmp_path):
        # .xls must be parsed to a markdown table in-CPU: no Stirling/PDF and no
        # OCR model call.
        import xlwt

        p = tmp_path / "legacy.xls"
        wb = xlwt.Workbook()
        ws = wb.add_sheet("销售")
        ws.write(0, 0, "产品")
        ws.write(0, 1, "数量")
        ws.write(1, 0, "苹果")
        ws.write(1, 1, "12")
        wb.save(p)

        with patch("app.services.parser.get_client") as mock_get:
            with open(p, "rb") as fh:
                resp = client.post(
                    "/rag/model_parser_file",
                    files={"file": ("legacy.xls", fh.read(), "application/vnd.ms-excel")},
                    data={"file_name": "legacy.xls"},
                )
            # No OCR model call for .xls (text-only shortcut).
            mock_get.assert_not_called()
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "success"
        assert "苹果" in body["content"]
        assert "## 销售" in body["content"]


class TestOfficeRejection:
    def test_docx_rejected_with_mineru_hint(self, client, monkeypatch):
        # Under the paddleocrvl backend there is no Office->PDF converter, so a
        # .docx must surface a clear 400 error pointing at the mineru backend
        # (not a silent success or a generic 500 without guidance).
        from app.config import settings

        monkeypatch.setattr(settings, "model_type", "paddleocrvl")
        # get_client() runs before convert_to_pdf() raises, so stub it to avoid
        # building a real PaddleOCRVLClient. Its return value is never used.
        with patch("app.services.parser.get_client"):
            resp = client.post(
                "/rag/model_parser_file",
                files={"file": ("doc.docx", b"%PDF-phony", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
                data={"file_name": "doc.docx"},
            )
        assert resp.status_code == 400
        body = resp.json()
        assert body["code"] == "400"
        assert body["status"] == "failed"
        assert "mineru" in body["message"]
