"""Generic S3-compatible object storage backend (Huawei OBS / Alibaba OSS / MinIO).

Uses boto3 with the S3v4 signature. Public-read buckets return unsigned URLs
(``{endpoint}/{bucket}/{object}``); the ``expires`` parameter is retained for
call-site compatibility but unused.
"""
from __future__ import annotations

import os
from typing import Optional

import boto3
from botocore.exceptions import ClientError

from app.utils.logging_utils import setup_logger
from app.utils.storage.base import StorageBackend

logger = setup_logger(__name__, "./logs/app.log")

OSS_CONNECT_TIMEOUT = int(os.getenv("OSS_CONNECT_TIMEOUT", "10"))
OSS_READ_TIMEOUT = int(os.getenv("OSS_READ_TIMEOUT", "30"))


class OSSStorage(StorageBackend):
    """S3-compatible storage backend."""

    def __init__(self, config: dict) -> None:
        self.endpoint = config.get("endpoint", "")
        self.access_key = config.get("access_key")
        self.secret_key = config.get("secret_key")
        self.bucket = config.get("bucket")
        self.region = config.get("region", "")

        # Auto-add https:// when no scheme is given.
        if self.endpoint and not self.endpoint.startswith(("http://", "https://")):
            self.endpoint = f"https://{self.endpoint}"

        logger.info("OSS endpoint: %s", self.endpoint)
        logger.info("OSS bucket: %s", self.bucket)
        if self.region:
            logger.info("OSS region: %s", self.region)
        logger.info(
            "OSS connect_timeout: %ss, read_timeout: %ss", OSS_CONNECT_TIMEOUT, OSS_READ_TIMEOUT
        )

        self.client = self._create_client()
        self._verify_connection()

    def _create_client(self):
        kwargs = {
            "service_name": "s3",
            "endpoint_url": self.endpoint,
            "aws_access_key_id": self.access_key,
            "aws_secret_access_key": self.secret_key,
            "config": boto3.session.Config(
                connect_timeout=OSS_CONNECT_TIMEOUT,
                read_timeout=OSS_READ_TIMEOUT,
                signature_version="s3v4",
            ),
        }
        if self.region:
            kwargs["region_name"] = self.region
        if os.getenv("OSS_VERIFY_SSL", "true").lower() != "true":
            kwargs["verify"] = False
        return boto3.client(**kwargs)

    def _verify_connection(self) -> None:
        try:
            self.client.head_bucket(Bucket=self.bucket)
            logger.info("OSS connection verified: bucket %s accessible", self.bucket)
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "Unknown")
            if code in ("404", "NoSuchBucket"):
                logger.error("OSS verify failed: bucket %s does not exist", self.bucket)
            elif code in ("403", "AccessDenied"):
                logger.error("OSS verify failed: AccessKey denied on bucket %s", self.bucket)
            else:
                logger.error("OSS verify failed: %s", exc)
            raise
        except Exception as exc:  # noqa: BLE001
            logger.error("OSS verify failed: %s", exc)
            raise

    def upload_file(
        self,
        file_path: str,
        bucket_name: Optional[str] = None,
        overwrite_file_name: Optional[str] = None,
    ) -> Optional[str]:
        try:
            original = os.path.basename(file_path)
            ext = os.path.splitext(original)[1]
            object_name = (overwrite_file_name + ext) if overwrite_file_name else original

            if not os.path.exists(file_path):
                logger.error("file does not exist: %s", file_path)
                return None

            with open(file_path, "rb") as data:
                self.client.put_object(Bucket=self.bucket, Key=object_name, Body=data)

            logger.info("uploaded %s to bucket %s", object_name, self.bucket)
            return self.get_download_url(object_name)
        except ClientError as exc:
            logger.error("OSS error: %s", exc)
            return None
        except Exception as exc:  # noqa: BLE001
            logger.error("upload to OSS failed: %s", exc)
            return None

    def get_download_url(
        self,
        object_name: str,
        bucket_name: Optional[str] = None,
        expires: int = 3600 * 24 * 7,
    ) -> str:
        """Public bucket: unsigned URL ``{endpoint}/{bucket}/{object}``.

        ``expires`` is retained for compatibility but unused (public URL never
        expires).
        """
        del expires
        return f"{self.endpoint}/{self.bucket}/{object_name}"
