"""Shared pytest fixtures."""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Ensure the rewrite root is importable when pytest runs from the repo root.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Tests must never hit a real storage backend or leave a cached singleton.
os.environ.setdefault("OSS_TYPE", "minio")
