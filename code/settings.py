"""Shared settings and text cleaning utilities for Part II Step 2."""

from __future__ import annotations

import re
import unicodedata

def clean_page_text(text: str) -> str:
    """Normalize and lightly clean extracted PDF page text.

    Steps:
    - Unicode normalization (NFKC)
    - soft hyphen removal
    - hyphenation repair across line breaks (word-\nwrap -> wordwrap)
    - line ending normalization and whitespace trimming
    """
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\u00ad", "")
    text = re.sub(r"([A-Za-z])-\n([A-Za-z])", r"\1\2", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = "\n".join([ln.rstrip() for ln in text.split("\n")])
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
