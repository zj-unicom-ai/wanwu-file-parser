"""PaddleOCR-VL client unit tests (file-type map, key normalization, data URI)."""
from __future__ import annotations

from app.models.paddleocrvl.client import (
    PaddleOCRVLClient,
    _FILE_TYPE_IMAGE,
    _FILE_TYPE_MAP,
    _FILE_TYPE_PDF,
)


class TestFileTypeMap:
    def test_pdf_is_zero(self):
        assert _FILE_TYPE_MAP[".pdf"] == _FILE_TYPE_PDF

    def test_images_are_one(self):
        for ext in (".jpg", ".jpeg", ".png", ".gif", ".webp", ".tif", ".tiff", ".bmp"):
            assert _FILE_TYPE_MAP[ext] == _FILE_TYPE_IMAGE

    def test_covers_all_admitted_image_extensions(self):
        from app.models.paddleocrvl.client import SUPPORTED_IMAGE_EX

        missing = set(SUPPORTED_IMAGE_EX) - set(_FILE_TYPE_MAP.keys())
        assert not missing, f"admitted but unsupported: {missing}"


class TestStripImgsPrefix:
    def test_simple(self):
        assert PaddleOCRVLClient._strip_imgs_prefix("imgs/foo.jpg") == "foo.jpg"

    def test_nested_keeps_page_dir(self):
        # regression: imgs/page1/0.jpg must not collapse to 0.jpg
        assert PaddleOCRVLClient._strip_imgs_prefix("imgs/page1/0.jpg") == "page1/0.jpg"
        assert PaddleOCRVLClient._strip_imgs_prefix("imgs/page2/0.jpg") == "page2/0.jpg"

    def test_no_prefix_returned_as_is(self):
        assert PaddleOCRVLClient._strip_imgs_prefix("foo.jpg") == "foo.jpg"
        assert PaddleOCRVLClient._strip_imgs_prefix("page1/0.jpg") == "page1/0.jpg"

    def test_empty_and_backslash(self):
        assert PaddleOCRVLClient._strip_imgs_prefix("") == ""
        assert PaddleOCRVLClient._strip_imgs_prefix("imgs\\page1\\0.jpg") == "page1/0.jpg"

    def test_two_pages_same_basename_do_not_collide(self):
        raw = {"imgs/page1/0.jpg": "b64A", "imgs/page2/0.jpg": "b64B"}
        images_map = {PaddleOCRVLClient._strip_imgs_prefix(k): v for k, v in raw.items()}
        assert len(images_map) == 2
        assert images_map["page1/0.jpg"] == "b64A"
        assert images_map["page2/0.jpg"] == "b64B"


class TestToDataUri:
    def test_raw_base64_gets_prefix(self):
        assert PaddleOCRVLClient._to_data_uri("foo.png", "QUJD") == "data:image/png;base64,QUJD"

    def test_jpg_normalized_to_jpeg(self):
        assert PaddleOCRVLClient._to_data_uri("foo.jpg", "QUJD") == "data:image/jpeg;base64,QUJD"

    def test_already_prefixed_returned_as_is(self):
        uri = "data:image/png;base64,QUJD"
        assert PaddleOCRVLClient._to_data_uri("foo.png", uri) == uri

    def test_empty_returned_as_is(self):
        assert PaddleOCRVLClient._to_data_uri("foo.png", "") == ""

    def test_unknown_ext_defaults_jpeg(self):
        assert PaddleOCRVLClient._to_data_uri("foo", "QUJD") == "data:image/jpeg;base64,QUJD"
