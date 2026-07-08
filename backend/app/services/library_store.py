from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class LibraryStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._lock, self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS library_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS library_manga (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    slug TEXT NOT NULL,
                    source_url TEXT NOT NULL UNIQUE,
                    local_subdir TEXT NOT NULL,
                    scan_interval_minutes INTEGER NOT NULL DEFAULT 60,
                    auto_download_missing INTEGER NOT NULL DEFAULT 0,
                    last_scan_at TEXT,
                    next_scan_at TEXT,
                    last_scan_status TEXT,
                    last_scan_error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS library_chapters (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    manga_id INTEGER NOT NULL,
                    chapter_url TEXT NOT NULL,
                    chapter_slug TEXT NOT NULL,
                    chapter_title TEXT NOT NULL,
                    chapter_number REAL,
                    remote_present INTEGER NOT NULL DEFAULT 1,
                    local_present INTEGER NOT NULL DEFAULT 0,
                    first_seen_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(manga_id, chapter_slug),
                    FOREIGN KEY(manga_id) REFERENCES library_manga(id) ON DELETE CASCADE
                );
                """
            )
            columns = {
                row["name"]
                for row in conn.execute("PRAGMA table_info(library_manga)").fetchall()
            }
            if "auto_download_missing" not in columns:
                conn.execute(
                    "ALTER TABLE library_manga ADD COLUMN auto_download_missing INTEGER NOT NULL DEFAULT 0"
                )
            conn.commit()

    def get_setting(self, key: str) -> Optional[str]:
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT value FROM library_settings WHERE key = ?", (key,)).fetchone()
            return str(row["value"]) if row else None

    def set_setting(self, key: str, value: str) -> None:
        now = utcnow_iso()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO library_settings(key, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = excluded.updated_at
                """,
                (key, value, now),
            )
            conn.commit()

    def upsert_manga(
        self,
        title: str,
        slug: str,
        source_url: str,
        local_subdir: str,
        scan_interval_minutes: int,
        auto_download_missing: bool,
    ) -> int:
        now = utcnow_iso()
        with self._lock, self._connect() as conn:
            existing = conn.execute(
                "SELECT id FROM library_manga WHERE source_url = ?",
                (source_url,),
            ).fetchone()

            if existing:
                manga_id = int(existing["id"])
                conn.execute(
                    """
                    UPDATE library_manga
                    SET title = ?, slug = ?, local_subdir = ?, scan_interval_minutes = ?,
                        auto_download_missing = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        title,
                        slug,
                        local_subdir,
                        scan_interval_minutes,
                        1 if auto_download_missing else 0,
                        now,
                        manga_id,
                    ),
                )
            else:
                cur = conn.execute(
                    """
                    INSERT INTO library_manga(
                        title, slug, source_url, local_subdir, scan_interval_minutes,
                        auto_download_missing,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        title,
                        slug,
                        source_url,
                        local_subdir,
                        scan_interval_minutes,
                        1 if auto_download_missing else 0,
                        now,
                        now,
                    ),
                )
                manga_id = int(cur.lastrowid)

            conn.commit()
            return manga_id

    def update_manga_schedule(
        self,
        manga_id: int,
        *,
        scan_interval_minutes: Optional[int] = None,
        auto_download_missing: Optional[bool] = None,
    ) -> None:
        if scan_interval_minutes is None and auto_download_missing is None:
            return

        now = utcnow_iso()
        fields: list[str] = ["updated_at = ?"]
        values: list[Any] = [now]

        if scan_interval_minutes is not None:
            fields.append("scan_interval_minutes = ?")
            values.append(scan_interval_minutes)

        if auto_download_missing is not None:
            fields.append("auto_download_missing = ?")
            values.append(1 if auto_download_missing else 0)

        values.append(manga_id)

        with self._lock, self._connect() as conn:
            conn.execute(
                f"UPDATE library_manga SET {', '.join(fields)} WHERE id = ?",
                values,
            )
            conn.commit()

    def delete_manga(self, manga_id: int) -> bool:
        with self._lock, self._connect() as conn:
            conn.execute("DELETE FROM library_chapters WHERE manga_id = ?", (manga_id,))
            cur = conn.execute("DELETE FROM library_manga WHERE id = ?", (manga_id,))
            conn.commit()
            return cur.rowcount > 0

    def mark_scan_result(
        self,
        manga_id: int,
        *,
        next_scan_at: Optional[str],
        status: str,
        error: Optional[str],
    ) -> None:
        now = utcnow_iso()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                UPDATE library_manga
                SET last_scan_at = ?, next_scan_at = ?, last_scan_status = ?,
                    last_scan_error = ?, updated_at = ?
                WHERE id = ?
                """,
                (now, next_scan_at, status, error, now, manga_id),
            )
            conn.commit()

    def list_manga(self) -> list[dict[str, Any]]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, title, slug, source_url, local_subdir, scan_interval_minutes,
                      auto_download_missing,
                       last_scan_at, next_scan_at, last_scan_status, last_scan_error
                FROM library_manga
                ORDER BY updated_at DESC, id DESC
                """
            ).fetchall()
            return [dict(row) for row in rows]

    def get_manga(self, manga_id: int) -> Optional[dict[str, Any]]:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                """
                SELECT id, title, slug, source_url, local_subdir, scan_interval_minutes,
                      auto_download_missing,
                       last_scan_at, next_scan_at, last_scan_status, last_scan_error
                FROM library_manga
                WHERE id = ?
                """,
                (manga_id,),
            ).fetchone()
            return dict(row) if row else None

    def list_due_manga_ids(self, now_iso: str) -> list[int]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id
                FROM library_manga
                WHERE next_scan_at IS NULL OR next_scan_at <= ?
                ORDER BY
                    CASE WHEN next_scan_at IS NULL THEN 0 ELSE 1 END ASC,
                    next_scan_at ASC,
                    id ASC
                """,
                (now_iso,),
            ).fetchall()
            return [int(row["id"]) for row in rows]

    def upsert_chapter(
        self,
        manga_id: int,
        chapter_url: str,
        chapter_slug: str,
        chapter_title: str,
        chapter_number: Optional[float],
        remote_present: bool,
        local_present: bool,
    ) -> None:
        now = utcnow_iso()
        with self._lock, self._connect() as conn:
            row = conn.execute(
                """
                SELECT id, first_seen_at
                FROM library_chapters
                WHERE manga_id = ? AND chapter_slug = ?
                """,
                (manga_id, chapter_slug),
            ).fetchone()

            if row:
                conn.execute(
                    """
                    UPDATE library_chapters
                    SET chapter_url = ?, chapter_title = ?, chapter_number = ?,
                        remote_present = ?, local_present = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        chapter_url,
                        chapter_title,
                        chapter_number,
                        1 if remote_present else 0,
                        1 if local_present else 0,
                        now,
                        int(row["id"]),
                    ),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO library_chapters(
                        manga_id, chapter_url, chapter_slug, chapter_title, chapter_number,
                        remote_present, local_present, first_seen_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        manga_id,
                        chapter_url,
                        chapter_slug,
                        chapter_title,
                        chapter_number,
                        1 if remote_present else 0,
                        1 if local_present else 0,
                        now,
                        now,
                    ),
                )
            conn.commit()

    def mark_remote_missing_for_absent(self, manga_id: int, remote_slugs: set[str]) -> None:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT id, chapter_slug FROM library_chapters WHERE manga_id = ?",
                (manga_id,),
            ).fetchall()
            for row in rows:
                chapter_slug = str(row["chapter_slug"])
                if chapter_slug in remote_slugs:
                    continue
                conn.execute(
                    "UPDATE library_chapters SET remote_present = 0, updated_at = ? WHERE id = ?",
                    (utcnow_iso(), int(row["id"])),
                )
            conn.commit()

    def list_chapters(self, manga_id: int) -> list[dict[str, Any]]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                """
                SELECT chapter_url, chapter_slug, chapter_title, chapter_number,
                       remote_present, local_present
                FROM library_chapters
                WHERE manga_id = ?
                ORDER BY chapter_number ASC, chapter_slug ASC
                """,
                (manga_id,),
            ).fetchall()
            return [dict(row) for row in rows]
