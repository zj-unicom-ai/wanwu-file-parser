"""Application configuration.

Single source of truth for all settings, loaded from environment variables via
pydantic-settings. Implements the unified OCR endpoint resolution described in
the 改造技术方案: one shared host (``OCR_BASE_URL``) plus per-model ``*_API_PATH``
and ``*_ADDRESS`` overrides.
"""
from __future__ import annotations

import os
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def resolve_ocr_endpoint(
    override: str | None,
    base_url: str | None,
    path: str | None,
    legacy_default: str,
) -> str:
    """Resolve the full endpoint URL an OCR client should call.

    Priority (keeps mineru / paddleocr addressing in one group of vars):
      1. ``override`` — model-specific full address (``PADDLEOCRVL_ADDRESS`` /
         ``MINERU_API_ADDRESS``); backwards compatible, used as-is.
      2. ``base_url + path`` — ``OCR_BASE_URL`` (host only) + the model's
         ``*_API_PATH``.
      3. ``legacy_default`` — historical fallback.

    Returns the full endpoint URL without a trailing slash. The client POSTs to
    this address directly and never appends a path itself, eliminating the
    double-path bug (default already carrying ``/file_parse`` while the client
    appends it again). base and path are split so host and endpoint path can be
    changed independently.
    """
    override = (override or "").strip()
    if override:
        return override.rstrip("/")

    base_url = (base_url or "").strip()
    if base_url:
        path = (path or "").strip().strip("/")
        return f"{base_url.rstrip('/')}/{path}" if path else base_url.rstrip("/")

    return legacy_default.rstrip("/")


class Settings(BaseSettings):
    """All settings, sourced from environment (``.env`` supported)."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ---- service ----
    app_host: str = Field(default="0.0.0.0", alias="APP_HOST")
    app_port: int = Field(default=8083, alias="APP_PORT")
    model_type: str = Field(default="mineru", alias="MODEL_TYPE")  # mineru | paddleocrvl
    version: str = Field(default="private", alias="VERSION")

    # ---- OCR unified addressing ----
    ocr_base_url: str = Field(default="", alias="OCR_BASE_URL")
    mineru_api_path: str = Field(default="file_parse", alias="MINERU_API_PATH")
    paddleocrvl_api_layout_parsing_path: str = Field(
        default="layout-parsing", alias="PADDLEOCRVL_API_LAYOUT_PARSING_PATH"
    )
    paddleocrvl_api_restructure_pages_path: str = Field(
        default="restructure-pages", alias="PADDLEOCRVL_API_RESTRUCTURE_PAGES_PATH"
    )

    # ---- PaddleOCR-VL ----
    paddleocrvl_address: str = Field(default="", alias="PADDLEOCRVL_ADDRESS")
    vl_rec_api_model_name: str = Field(
        default="PaddleOCR-VL-1.6-0.9B", alias="VL_REC_API_MODEL_NAME"
    )
    vl_rec_api_key: str = Field(default="", alias="VL_REC_API_KEY")

    # ---- MinerU ----
    mineru_api_address: str = Field(default="", alias="MINERU_API_ADDRESS")
    mineru_api_key: str = Field(default="", alias="MINERU_API_KEY")
    mineru_backend: str = Field(default="hybrid-http-client", alias="MINERU_BACKEND")
    mineru_lang_list: str = Field(default="ch", alias="MINERU_LANG_LIST")
    mineru_model_name: str = Field(default="MinerU", alias="MINERU_MODEL_NAME")
    mineru_server_url: str = Field(default="", alias="MINERU_SERVER_URL")
    mineru_effort: str = Field(default="", alias="MINERU_EFFORT")
    mineru_parse_method: str = Field(default="auto", alias="MINERU_PARSE_METHOD")

    # ---- file conversion (Office -> PDF via Stirling) ----
    stirling_address: str = Field(
        default="http://localhost:8080/api/v1/convert/file/pdf", alias="STIRLING_ADDRESS"
    )

    # ---- image URL prefix (default; real value extracted from uploads) ----
    prefix_image_url: str = Field(
        default="https://obs-nmhhht6.cucloud.cn/doc-rag-public/", alias="PREFIX_IMAGE_URL"
    )

    # ---- object storage ----
    oss_type: str = Field(default="minio", alias="OSS_TYPE")  # minio | oss
    # MinIO
    use_custom_minio: bool = Field(default=False, alias="USE_CUSTOM_MINIO")
    minio_default_bucket: str = Field(default="rag-public", alias="MINIO_DEFAULT_BUCKET")
    bff_service_minio: str = Field(
        default="http://bff-service:6667/v1/api/deploy/info", alias="BFF_SERVICE_MINIO"
    )
    minio_address: str = Field(default="minio-wanwu:9000", alias="MINIO_ADDRESS")
    minio_access_key: str = Field(default="root", alias="MINIO_ACCESS_KEY")
    minio_secret_key: str = Field(default="your_sk", alias="MINIO_SECRET_KEY")
    # OSS
    oss_endpoint: str = Field(default="oss.example.com", alias="OSS_ENDPOINT")
    oss_access_key: str = Field(default="", alias="OSS_ACCESS_KEY")
    oss_secret_key: str = Field(default="", alias="OSS_SECRET_KEY")
    oss_bucket: str = Field(default="doc-rag-public", alias="OSS_BUCKET")
    oss_region: str = Field(default="", alias="OSS_REGION")

    # ---- derived endpoints ----
    @property
    def paddleocrvl_endpoint(self) -> str:
        """PaddleOCR-VL base (host only, no sub-endpoint path).

        The two-stage client appends ``PADDLEOCRVL_API_LAYOUT_PARSING_PATH`` and
        ``PADDLEOCRVL_API_RESTRUCTURE_PAGES_PATH`` on top of this base, so only
        the host is returned here. ``PADDLEOCRVL_ADDRESS`` (if set) is used as
        the base verbatim (may include a prefix path).
        """
        return resolve_ocr_endpoint(
            override=self.paddleocrvl_address,
            base_url=self.ocr_base_url,
            path="",
            legacy_default="http://localhost:8080",
        )

    @property
    def mineru_api_endpoint(self) -> str:
        """MinerU ``/file_parse`` endpoint (full URL; client POSTs directly)."""
        return resolve_ocr_endpoint(
            override=self.mineru_api_address,
            base_url=self.ocr_base_url,
            path=self.mineru_api_path,
            legacy_default="https://192.168.0.12:8003/file_parse",
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached singleton ``Settings``."""
    return Settings()


# Backwards-friendly module-level accessor (tests/clients import `settings`).
settings = get_settings()
