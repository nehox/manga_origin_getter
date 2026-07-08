from __future__ import annotations

from pathlib import Path


def default_library_db_path() -> Path:
    return Path(__file__).resolve().parents[2] / "data" / "library.db"
