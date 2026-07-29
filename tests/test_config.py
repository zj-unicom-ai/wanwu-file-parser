"""Config + OCR endpoint resolution tests."""
from __future__ import annotations

from app.config import resolve_ocr_endpoint


class TestResolveOcrEndpoint:
    def test_override_wins(self):
        assert resolve_ocr_endpoint(
            override="http://gpu:8080", base_url="http://other:8000",
            path="file_parse", legacy_default="http://default",
        ) == "http://gpu:8080"

    def test_override_strips_trailing_slash(self):
        assert resolve_ocr_endpoint(
            override="http://gpu:8080/", base_url="", path="", legacy_default=""
        ) == "http://gpu:8080"

    def test_base_plus_path(self):
        assert resolve_ocr_endpoint(
            override="", base_url="http://host:8000", path="file_parse",
            legacy_default="http://default",
        ) == "http://host:8000/file_parse"

    def test_base_no_path(self):
        # paddleocrvl passes path="" -> base only (host for the two-stage client)
        assert resolve_ocr_endpoint(
            override="", base_url="http://host:8000", path="",
            legacy_default="http://default",
        ) == "http://host:8000"

    def test_legacy_default_when_nothing_set(self):
        assert resolve_ocr_endpoint(
            override="", base_url="", path="", legacy_default="https://x:8003/file_parse"
        ) == "https://x:8003/file_parse"

    def test_path_leading_slash_stripped(self):
        assert resolve_ocr_endpoint(
            override="", base_url="http://h:8000", path="/file_parse",
            legacy_default="",
        ) == "http://h:8000/file_parse"


class TestSettingsDerived:
    def test_mineru_endpoint_full_with_file_parse(self):
        from app.config import settings

        # Default MINERU_API_ADDRESS includes /file_parse; client must not append.
        assert settings.mineru_api_endpoint.endswith("/file_parse")

    def test_paddleocrvl_endpoint_is_host_only(self):
        from app.config import settings

        # base must not contain a sub-endpoint path; client appends them.
        assert "/layout-parsing" not in settings.paddleocrvl_endpoint
        assert "/restructure-pages" not in settings.paddleocrvl_endpoint
