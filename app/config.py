"""Application configuration.

Single source of truth for all settings, loaded from environment variables via
pydantic-settings. Implements unified OCR endpoint resolution: one shared host
(``OCR_BASE_URL``) plus per-model ``*_API_PATH`` and ``*_ADDRESS`` overrides.
"""
from __future__ import annotations

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
    app_workers: int = Field(default=1, alias="APP_WORKERS")
    model_type: str = Field(default="mineru", alias="MODEL_TYPE")  # mineru | paddleocrvl
    version: str = Field(default="private", alias="VERSION")

    # ---- Office document processing mode ----
    # Controls how .docx/.pptx Office documents are handled:
    #   - auto            : try doc2md direct extraction first, fall back to
    #                       LibreOffice→PDF→OCR on failure (.doc/.ppt always
    #                       fall back to LibreOffice since doc2md only supports
    #                       the XML-based formats).
    #   - direct_extract  : use PaddleOCR doc2md only (no GPU, no OCR inference).
    #                       .doc/.ppt legacy binary formats are rejected.
    #   - convert_pdf     : use LibreOffice→PDF→OCR only (previous behavior).
    office_processing_mode: str = Field(
        default="auto", alias="OFFICE_PROCESSING_MODE"
    )

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

    # ---- MinerU ----
    mineru_api_address: str = Field(default="", alias="MINERU_API_ADDRESS")
    mineru_api_key: str = Field(default="", alias="MINERU_API_KEY")
    mineru_backend: str = Field(default="hybrid-http-client", alias="MINERU_BACKEND")
    mineru_lang_list: str = Field(default="ch", alias="MINERU_LANG_LIST")
    mineru_server_url: str = Field(default="", alias="MINERU_SERVER_URL")
    mineru_effort: str = Field(default="", alias="MINERU_EFFORT")
    mineru_parse_method: str = Field(default="auto", alias="MINERU_PARSE_METHOD")

    # ---- image URL prefix (default; real value extracted from uploads) ----
    prefix_image_url: str = Field(
        default="", alias="PREFIX_IMAGE_URL"
    )

    # ---- object storage ----
    oss_type: str = Field(default="minio", alias="OSS_TYPE")  # minio | oss
    # MinIO
    minio_default_bucket: str = Field(default="rag-public", alias="MINIO_DEFAULT_BUCKET")
    minio_address: str = Field(default="localhost:9000", alias="MINIO_ADDRESS")
    minio_access_key: str = Field(default="", alias="MINIO_ACCESS_KEY")
    minio_secret_key: str = Field(default="", alias="MINIO_SECRET_KEY")
    # 图片公共下载 URL 前缀(经 nginx 反代到 minio)。
    # 拼接规则:{MINIO_DOWNLOAD_URL}/{bucket}/{object}。
    minio_download_url: str = Field(
        default="http://localhost:8081/minio/download/api", alias="MINIO_DOWNLOAD_URL"
    )
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
            legacy_default="http://localhost:8003/file_parse",
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached singleton ``Settings``."""
    return Settings()


# Backwards-friendly module-level accessor (tests/clients import `settings`).
settings = get_settings()
