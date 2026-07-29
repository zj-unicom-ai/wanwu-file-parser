"""Storage factory + backend tests (mocked, no real connections)."""
from __future__ import annotations

from unittest.mock import Mock, patch

import pytest

from app.utils.storage.factory import StorageFactory
from app.utils.storage.minio_storage import MinIOStorage
from app.utils.storage.oss_storage import OSSStorage


@pytest.fixture(autouse=True)
def _reset_factory():
    StorageFactory.reset()
    yield
    StorageFactory.reset()


class TestStorageFactory:
    def test_create_minio_storage(self):
        with patch("app.utils.storage.factory.settings") as mock_cfg:
            mock_cfg.oss_type = "minio"
            mock_cfg.minio_address = "localhost:9000"
            mock_cfg.minio_access_key = "test_access"
            mock_cfg.minio_secret_key = "test_secret"
            mock_cfg.minio_default_bucket = "test-bucket"
            mock_cfg.use_custom_minio = False
            mock_cfg.bff_service_minio = "http://test:8080/api"

            storage = StorageFactory.get_storage()
            assert isinstance(storage, MinIOStorage)
            assert storage.address == "localhost:9000"
            assert storage.default_bucket == "test-bucket"

    def test_create_oss_storage(self):
        with patch("app.utils.storage.factory.settings") as mock_cfg, \
             patch("app.utils.storage.oss_storage.boto3.client") as mock_boto:
            mock_cfg.oss_type = "oss"
            mock_cfg.oss_endpoint = "oss.example.com"
            mock_cfg.oss_access_key = "test_access_key"
            mock_cfg.oss_secret_key = "test_secret_key"
            mock_cfg.oss_bucket = "test-bucket"
            mock_cfg.oss_region = ""

            client_instance = Mock()
            mock_boto.return_value = client_instance
            client_instance.head_bucket.return_value = {}

            storage = StorageFactory.get_storage()
            assert isinstance(storage, OSSStorage)
            # endpoint auto-prefixed with https://
            assert storage.endpoint == "https://oss.example.com"
            assert storage.bucket == "test-bucket"

    def test_unsupported_storage_type(self):
        with patch("app.utils.storage.factory.settings") as mock_cfg:
            mock_cfg.oss_type = "unsupported"
            with pytest.raises(ValueError, match="不支持的 OSS_TYPE"):
                StorageFactory.get_storage()

    def test_singleton(self):
        with patch("app.utils.storage.factory.settings") as mock_cfg:
            mock_cfg.oss_type = "minio"
            mock_cfg.minio_address = "localhost:9000"
            mock_cfg.minio_access_key = "a"
            mock_cfg.minio_secret_key = "s"
            mock_cfg.minio_default_bucket = "b"
            mock_cfg.use_custom_minio = False
            mock_cfg.bff_service_minio = "http://t:8080"

            s1 = StorageFactory.get_storage()
            s2 = StorageFactory.get_storage()
            assert s1 is s2


class TestOSSStorage:
    def _make(self):
        with patch("app.utils.storage.oss_storage.boto3.client") as mock_boto:
            inst = Mock()
            mock_boto.return_value = inst
            inst.head_bucket.return_value = {}
            storage = OSSStorage(
                {
                    "endpoint": "oss.example.com",
                    "access_key": "k",
                    "secret_key": "s",
                    "bucket": "test-bucket",
                    "region": "",
                }
            )
        return storage

    def test_get_download_url_is_public_unsigned(self):
        storage = self._make()
        url = storage.get_download_url("test.jpg")
        assert url == "https://oss.example.com/test-bucket/test.jpg"

    def test_upload_file_not_found(self):
        storage = self._make()
        assert storage.upload_file("/tmp/does_not_exist_xyz.jpg") is None


class TestMinIOStorage:
    def test_get_download_url_custom(self):
        with patch("app.utils.storage.minio_storage.Minio"):
            storage = MinIOStorage(
                {
                    "address": "localhost:9000",
                    "access_key": "a",
                    "secret_key": "s",
                    "default_bucket": "bkt",
                    "use_custom": True,
                    "bff_service": "",
                }
            )
        assert storage.get_download_url("x.jpg") == "http://localhost:9000/bkt/x.jpg"
