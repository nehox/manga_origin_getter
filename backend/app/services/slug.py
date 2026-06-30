from __future__ import annotations

import re
import unicodedata


_slug_cleanup_re = re.compile(r"[^a-zA-Z0-9_-]+")
_multi_dash_re = re.compile(r"-+")


def to_slug(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    ascii_text = ascii_text.strip().lower().replace(" ", "-")
    ascii_text = _slug_cleanup_re.sub("-", ascii_text)
    ascii_text = _multi_dash_re.sub("-", ascii_text).strip("-")
    return ascii_text or "chapter"
