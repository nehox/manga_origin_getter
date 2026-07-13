from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


MAX_LOG_BYTES = 30 * 1024 * 1024  # 30 MB
LOG_DIR_NAME = "logs"
LOG_FILE_NAME = "app.log"


def _log_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "data" / LOG_DIR_NAME


def _log_path() -> Path:
    return _log_dir() / LOG_FILE_NAME


def _ensure_log_dir() -> None:
    _log_dir().mkdir(parents=True, exist_ok=True)


def _rotate_if_needed(path: Path) -> None:
    if path.exists() and path.stat().st_size > MAX_LOG_BYTES:
        rotated = path.with_suffix(".log.old")
        if rotated.exists():
            rotated.unlink()
        path.rename(rotated)


def _write(level: str, source: str, message: str) -> None:
    _ensure_log_dir()
    path = _log_path()
    _rotate_if_needed(path)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with path.open("a", encoding="utf-8") as f:
        f.write(f"{ts} [{level}] [{source}] {message}\n")


def info(source: str, message: str) -> None:
    _write("INFO", source, message)


def warn(source: str, message: str) -> None:
    _write("WARN", source, message)


def error(source: str, message: str) -> None:
    _write("ERROR", source, message)


LogEntry = dict[str, str]


def read_logs(
    limit: int = 100,
    offset: int = 0,
    level: Optional[str] = None,
    source: Optional[str] = None,
) -> list[LogEntry]:
    path = _log_path()
    if not path.exists():
        return []

    with path.open("r", encoding="utf-8") as f:
        lines = f.readlines()

    entries: list[LogEntry] = []
    for line in lines:
        stripped = line.rstrip("\n")
        if not stripped:
            continue
        parts = stripped.split(" ", 2)
        if len(parts) < 3:
            continue
        timestamp = parts[0].strip()
        raw_level = parts[1].strip("[]")
        rest = parts[2]
        src_end = rest.find("]")
        if src_end == -1:
            continue
        src = rest[1:src_end].strip()
        msg = rest[src_end + 1 :].strip()

        if level and raw_level != level:
            continue
        if source and src != source:
            continue

        entries.append({
            "timestamp": timestamp,
            "level": raw_level,
            "source": src,
            "message": msg,
        })

    entries.reverse()
    return entries[offset : offset + limit]


def count_logs(
    level: Optional[str] = None,
    source: Optional[str] = None,
) -> int:
    path = _log_path()
    if not path.exists():
        return 0

    total = 0
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            stripped = line.rstrip("\n")
            if not stripped:
                continue
            parts = stripped.split(" ", 2)
            if len(parts) < 3:
                continue
            raw_level = parts[1].strip("[]")
            rest = parts[2]
            src_end = rest.find("]")
            if src_end == -1:
                continue
            src = rest[1:src_end].strip()
            if level and raw_level != level:
                continue
            if source and src != source:
                continue
            total += 1
    return total


def clear_logs() -> None:
    path = _log_path()
    if path.exists():
        path.unlink()
    rotated = path.with_suffix(".log.old")
    if rotated.exists():
        rotated.unlink()


def list_sources() -> list[str]:
    return sorted(set(e["source"] for e in read_logs(limit=99999)))
