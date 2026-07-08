from __future__ import annotations

from pathlib import Path
import shutil


def directory_size_bytes(root: Path) -> int:
    if not root.exists():
        return 0

    total = 0
    for path in root.rglob("*"):
        if path.is_file():
            try:
                total += path.stat().st_size
            except OSError:
                continue
    return total


def purge_directory_contents(root: Path) -> int:
    if not root.exists():
        root.mkdir(parents=True, exist_ok=True)
        return 0

    removed_entries = 0
    for child in root.iterdir():
        try:
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink(missing_ok=True)
            removed_entries += 1
        except OSError:
            continue

    root.mkdir(parents=True, exist_ok=True)
    return removed_entries
