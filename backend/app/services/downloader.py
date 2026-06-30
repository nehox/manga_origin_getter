from __future__ import annotations

import asyncio
from pathlib import Path
from urllib.parse import urlparse

import httpx


def _extension_from_url(url: str) -> str:
    path = urlparse(url).path
    suffix = Path(path).suffix.lower()
    if suffix in {".jpg", ".jpeg", ".png", ".webp"}:
        return suffix
    return ".jpg"


async def download_images(image_urls: list[str], destination_dir: Path, max_concurrency: int = 4) -> list[Path]:
    destination_dir.mkdir(parents=True, exist_ok=True)

    semaphore = asyncio.Semaphore(max_concurrency)
    timeout = httpx.Timeout(30.0)
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; MangaOriginGetter/0.1; +https://localhost)",
        "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
    }

    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, headers=headers) as client:

        async def _download_one(index: int, url: str) -> Path:
            async with semaphore:
                response = await client.get(url)
                response.raise_for_status()
                ext = _extension_from_url(url)
                file_path = destination_dir / f"{index:04d}{ext}"
                file_path.write_bytes(response.content)
                return file_path

        tasks = [_download_one(index, url) for index, url in enumerate(image_urls, start=1)]
        return await asyncio.gather(*tasks)
