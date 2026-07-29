"""Storage factory: pick a backend by ``OSS_TYPE`` (singleton)."""
from __future__ import annotations

from typing import Optional

from app.config import settings
from app.utils.logging_utils import setup_logger
from app.utils.storage.base import StorageBackend
from app.utils.storage.minio_storage import MinIOStorage
from app.utils.storage.oss_storage import OSSStorage

logger = setup_logger(__name__, "./logs/app.log")


class StorageFactory:
    """Singleton storage backend factory."""

    _instance: Optional[StorageBackend] = None

    @classmethod
    def get_storage(cls) -> StorageBackend:
        if cls._instance is None:
            cls._instance = cls._create_storage()
        return cls._instance

    @classmethod
    def _create_storage(cls) -> StorageBackend:
        oss_type = settings.oss_type.lower()
        logger.info("creating storage instance, OSS_TYPE: %s", oss_type)

        if oss_type == "minio":
            return MinIOStorage(
                {
                    "address": settings.minio_address,
                    "access_key": settings.minio_access_key,
                    "secret_key": settings.minio_secret_key,
                    "default_bucket": settings.minio_default_bucket,
                    "use_custom": settings.use_custom_minio,
                    "bff_service": settings.bff_service_minio,
                }
            )
        if oss_type == "oss":
            return OSSStorage(
                {
                    "endpoint": settings.oss_endpoint,
                    "access_key": settings.oss_access_key,
                    "secret_key": settings.oss_secret_key,
                    "bucket": settings.oss_bucket,
                    "region": settings.oss_region,
                }
            )
        raise ValueError(f"不支持的 OSS_TYPE: {oss_type}，可选值: minio, oss")

    @classmethod
    def reset(cls) -> None:
        """Drop the cached instance (for tests)."""
        cls._instance = None
