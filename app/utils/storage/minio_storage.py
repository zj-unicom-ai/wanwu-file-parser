"""MinIO storage backend (SDK)."""
from __future__ import annotations

import os
from typing import Optional

import requests
from minio import Minio
from minio.error import S3Error

from app.utils.logging_utils import setup_logger
from app.utils.storage.base import StorageBackend

logger = setup_logger(__name__, "./logs/app.log")


class MinIOStorage(StorageBackend):
    """MinIO SDK-backed storage."""

    def __init__(self, config: dict) -> None:
        self.address = config["address"]
        self.access_key = config["access_key"]
        self.secret_key = config["secret_key"]
        self.default_bucket = config["default_bucket"]
        self.use_custom = config.get("use_custom", False)
        self.bff_service = config.get("bff_service")

        logger.info("MinIO address: %s", self.address)
        self.client = Minio(
            self.address,
            access_key=self.access_key,
            secret_key=self.secret_key,
            secure=False,
        )

    def upload_file(
        self,
        file_path: str,
        bucket_name: Optional[str] = None,
        overwrite_file_name: Optional[str] = None,
    ) -> Optional[str]:
        target_bucket = bucket_name or self.default_bucket
        try:
            original = os.path.basename(file_path)
            ext = os.path.splitext(original)[1]
            file_name = (overwrite_file_name + ext) if overwrite_file_name else original

            if not os.path.exists(file_path):
                logger.error("file does not exist: %s", file_path)
                return None

            size = os.stat(file_path).st_size
            with open(file_path, "rb") as data:
                self.client.put_object(target_bucket, file_name, data, size)

            logger.info("uploaded %s to bucket %s", file_name, target_bucket)
            return self.get_download_url(file_name, target_bucket)
        except S3Error as exc:
            logger.error("MinIO error: %s", exc)
            return None
        except Exception as exc:  # noqa: BLE001
            logger.error("upload to MinIO failed: %s", exc)
            return None

    def get_download_url(
        self, object_name: str, bucket_name: Optional[str] = None
    ) -> str:
        target_bucket = bucket_name or self.default_bucket
        if self.use_custom:
            return f"http://{self.address}/{target_bucket}/{object_name}"
        resp = requests.get(self.bff_service, timeout=30)
        resp.raise_for_status()
        endpoint = resp.json()["data"]["webBaseUrl"].rstrip("/")
        return f"{endpoint}/{target_bucket}/{object_name}"
