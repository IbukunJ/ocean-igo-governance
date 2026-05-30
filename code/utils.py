"""
Utilities for Part II reproducibility bundle.

This module is intentionally small and dependency-light. It provides:
- stable string canonicalisation for joins
- SHA-256 file hashing
- safe directory creation
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Iterable, Optional

import pandas as pd


WHITESPACE_RE = re.compile(r"\s+")


def canon_text(s: Optional[str]) -> str:
    """Canonicalise a string for join keys: strip and collapse whitespace.

    Returns empty string for None/NaN.
    """
    if s is None:
        return ""
    try:
        # pandas can pass floats for NaN
        if pd.isna(s):
            return ""
    except Exception:
        pass
    return WHITESPACE_RE.sub(" ", str(s)).strip()


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    """Compute SHA-256 hash of a file."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            b = f.read(chunk_size)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def ensure_dir(path: Path) -> None:
    """Create a directory if it does not exist."""
    path.mkdir(parents=True, exist_ok=True)
