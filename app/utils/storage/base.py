"""Object storage abstraction."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional


class StorageBackend(ABC):
    """Abstract object-storage backend."""

    @abstractmethod
    def upload_file(
        self,
        file_path: str,
        bucket_name: Optional[str] = None,
        overwrite_file_name: Optional[str] = None,
    ) -> Optional[str]:
        """Upload a local file and return its download URL (None on failure)."""

    @abstractmethod
    def get_download_url(
        self, object_name: str, bucket_name: Optional[str] = None
    ) -> str:
        """Return the download URL for an object."""
