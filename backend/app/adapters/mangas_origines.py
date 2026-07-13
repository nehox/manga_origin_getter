from __future__ import annotations

import re
import os
from typing import Optional
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from app.adapters.base import ChapterDescriptor, SourceAdapter
from app.services.slug import to_slug


class MangasOriginesAdapter(SourceAdapter):
    host = "mangas-origines.fr"
    chapter_slug_re = re.compile(r"/chapitre-([^/]+)/?", re.IGNORECASE)

    def supports(self, source_url: str) -> bool:
        parsed = urlparse(source_url)
        return parsed.netloc.endswith(self.host)

    async def discover_chapters(self, source_url: str) -> tuple[str, list[ChapterDescriptor]]:
        html = await self._fetch_html(source_url)
        soup = BeautifulSoup(html, "html.parser")
        parsed_source = urlparse(source_url)
        source_base = f"{parsed_source.scheme}://{parsed_source.netloc}"
        source_path = parsed_source.path.rstrip("/")
        expected_prefix = f"{source_base}{source_path}/"

        title_tag = soup.select_one("h1")
        work_title = title_tag.get_text(strip=True) if title_tag else "manga"

        chapter_links: dict[str, ChapterDescriptor] = {}

        ajax_chapters = await self._discover_chapters_via_ajax(source_url, expected_prefix)
        for chapter in ajax_chapters:
            chapter_links[chapter.url] = chapter

        for anchor in soup.select("a[href]"):
            href = anchor.get("href", "")
            if "/chapitre-" not in href:
                continue
            chapter_url = urljoin(source_url, href)
            if not chapter_url.startswith(expected_prefix):
                continue
            raw_title = anchor.get_text(" ", strip=True)
            chapter_title = self._chapter_title_from_raw(raw_title, chapter_url)
            chapter_slug = to_slug(chapter_title)
            chapter_links[chapter_url] = ChapterDescriptor(
                title=chapter_title,
                url=chapter_url,
                slug=chapter_slug,
            )

        # Some source pages expose only first/last chapter links. In that case,
        # traverse chapter pages using next-chapter navigation to enumerate all.
        if 0 < len(chapter_links) <= 2:
            traversed = await self._traverse_chapter_chain(
                expected_prefix=expected_prefix,
                seed_urls=list(chapter_links.keys()),
            )
            for chapter in traversed:
                chapter_links[chapter.url] = chapter

        chapters = sorted(
            chapter_links.values(),
            key=lambda chapter: self._chapter_sort_key(chapter.url),
        )
        return work_title, chapters

    async def _discover_chapters_via_ajax(self, source_url: str, expected_prefix: str) -> list[ChapterDescriptor]:
        ajax_url = urljoin(source_url.rstrip("/") + "/", "ajax/chapters/?t=1")
        html = await self._fetch_ajax_html(source_url=source_url, ajax_url=ajax_url)
        if not html:
            return []

        soup = BeautifulSoup(html, "html.parser")
        chapters: dict[str, ChapterDescriptor] = {}

        for anchor in soup.select("a[href]"):
            href = anchor.get("href", "")
            if "/chapitre-" not in href:
                continue

            chapter_url = urljoin(source_url, href)
            if not chapter_url.startswith(expected_prefix):
                continue

            chapter_title = anchor.get_text(" ", strip=True) or chapter_url.rstrip("/").split("/")[-1]
            chapter_title = self._chapter_title_from_raw(chapter_title, chapter_url)
            chapters[chapter_url] = ChapterDescriptor(
                title=chapter_title,
                url=chapter_url,
                slug=to_slug(chapter_title),
            )

        return list(chapters.values())

    async def _traverse_chapter_chain(self, expected_prefix: str, seed_urls: list[str]) -> list[ChapterDescriptor]:
        if not seed_urls:
            return []

        current_url = min(seed_urls, key=self._chapter_sort_key)
        visited: set[str] = set()
        discovered: dict[str, ChapterDescriptor] = {}

        # Hard cap to avoid infinite loops when a source website is malformed.
        for _ in range(2500):
            if current_url in visited:
                break
            visited.add(current_url)

            html = await self._fetch_html(current_url)
            soup = BeautifulSoup(html, "html.parser")

            title = self._extract_chapter_title(soup, current_url)
            discovered[current_url] = ChapterDescriptor(
                title=title,
                url=current_url,
                slug=to_slug(title),
            )

            next_url = self._find_next_chapter_url(
                soup=soup,
                chapter_url=current_url,
                expected_prefix=expected_prefix,
            )
            if not next_url:
                break
            current_url = next_url

        return sorted(discovered.values(), key=lambda chapter: self._chapter_sort_key(chapter.url))

    def _extract_chapter_title(self, soup: BeautifulSoup, chapter_url: str) -> str:
        heading = soup.select_one(".reading-content h1") or soup.select_one("h1")
        if heading:
            text = heading.get_text(" ", strip=True)
            if text:
                return self._chapter_title_from_raw(text, chapter_url)
        return self._chapter_title_from_raw("", chapter_url)

    def _chapter_token_from_url(self, chapter_url: str) -> Optional[str]:
        match = self.chapter_slug_re.search(chapter_url)
        if not match:
            return None
        return match.group(1).strip().lower()

    def _chapter_title_from_raw(self, raw_title: str, chapter_url: str) -> str:
        token = self._chapter_token_from_url(chapter_url)
        cleaned = (raw_title or "").strip()

        if token:
            generic_labels = {
                "read first",
                "first chapter",
                "dernier chapitre",
                "latest chapter",
                "latest",
            }
            has_digit = bool(re.search(r"\d", cleaned))
            if not cleaned or cleaned.lower() in generic_labels or not has_digit:
                return f"Chapitre {token}"

        if cleaned:
            return cleaned

        if token:
            return f"Chapitre {token}"
        return chapter_url.rstrip("/").split("/")[-1].replace("-", " ").title()

    def _chapter_numeric_key(self, chapter_url: str) -> tuple[int, int]:
        token = self._chapter_token_from_url(chapter_url)
        if not token:
            return 10**9, 10**9

        parts = token.split("-")
        if parts and parts[0].isdigit():
            main_part = int(parts[0])
            if len(parts) > 1 and parts[1].isdigit():
                return main_part, int(parts[1])
            return main_part, 0

        match = re.search(r"(\d+)", token)
        if match:
            return int(match.group(1)), 0
        return 10**9, 10**9

    def _find_next_chapter_url(self, soup: BeautifulSoup, chapter_url: str, expected_prefix: str) -> Optional[str]:
        current_key = self._chapter_numeric_key(chapter_url)
        if current_key[0] >= 10**9:
            return None

        candidates: set[str] = set()
        for anchor in soup.select("a[href]"):
            href = anchor.get("href", "")
            if "/chapitre-" not in href:
                continue
            candidate = urljoin(chapter_url, href)
            if not candidate.startswith(expected_prefix):
                continue
            candidates.add(candidate)

        next_candidates: list[tuple[tuple[int, int], str]] = []
        for candidate in candidates:
            candidate_key = self._chapter_numeric_key(candidate)
            if candidate_key[0] >= 10**9:
                continue
            if candidate_key > current_key:
                next_candidates.append((candidate_key, candidate))

        if not next_candidates:
            return None
        next_candidates.sort(key=lambda item: item[0])
        return next_candidates[0][1]

    def _chapter_sort_key(self, chapter_url: str) -> tuple[int, str]:
        numeric = self._chapter_numeric_key(chapter_url)
        return (numeric[0] * 10000 + numeric[1]), chapter_url

    async def extract_cover_url(self, source_url: str) -> Optional[str]:
        html = await self._fetch_html(source_url)
        soup = BeautifulSoup(html, "html.parser")
        meta = soup.select_one('meta[property="og:image"]')
        if not meta:
            return None
        content = meta.get("content")
        return str(content).strip() if content else None

    async def extract_categories(self, source_url: str) -> list[str]:
        html = await self._fetch_html(source_url)
        soup = BeautifulSoup(html, "html.parser")
        genres: list[str] = []
        for a in soup.select('a[href*="/manga-genres/"]'):
            text = a.get_text(strip=True)
            if text and text not in genres:
                genres.append(text)
        return genres

    async def extract_image_urls(self, chapter_url: str) -> list[str]:
        html = await self._fetch_html(chapter_url)
        soup = BeautifulSoup(html, "html.parser")

        image_urls: list[str] = []
        selectors = [
            "img.wp-manga-chapter-img",
            "#chapter_imgs img",
            ".reading-content img",
            "img",
        ]

        for selector in selectors:
            found = self._extract_from_selector(soup, selector, chapter_url)
            if found:
                image_urls = found
                break

        if not image_urls:
            raise RuntimeError("No chapter images found in source")

        return image_urls

    def _extract_from_selector(self, soup: BeautifulSoup, selector: str, page_url: str) -> list[str]:
        image_urls: list[str] = []
        for image in soup.select(selector):
            src = (
                image.get("data-src")
                or image.get("data-lazy-src")
                or image.get("data-original")
                or image.get("src")
            )
            if not src:
                continue
            normalized_src = self._normalize_image_src(src)
            if not normalized_src:
                continue
            absolute = urljoin(page_url, normalized_src)
            if "/wp-content/uploads/WP-manga/data/" not in absolute:
                continue
            image_urls.append(absolute)

        deduped: list[str] = []
        seen = set()
        for url in image_urls:
            if url in seen:
                continue
            seen.add(url)
            deduped.append(url)
        return deduped

    def _normalize_image_src(self, src: str) -> Optional[str]:
        cleaned = src.strip().strip('"').strip("'")
        if not cleaned:
            return None

        # Defensive cleanup for malformed absolute URLs seen in lazy attributes.
        cleaned = re.sub(r"^https:/([^/])", r"https://\1", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"^http:/([^/])", r"http://\1", cleaned, flags=re.IGNORECASE)

        # Ignore data URLs and javascript pseudo URLs.
        lowered = cleaned.lower()
        if lowered.startswith("data:") or lowered.startswith("javascript:"):
            return None

        return cleaned

    async def _fetch_html(self, url: str) -> str:
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; MangaOriginGetter/0.1; +https://localhost)",
            "Accept": "text/html,application/xhtml+xml",
        }
        cookie = os.getenv("MANGA_SOURCE_COOKIE", "").strip()
        if cookie:
            headers["Cookie"] = cookie
        timeout = httpx.Timeout(30.0)
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, headers=headers) as client:
            response = await client.get(url)
            if response.status_code == 403 and "cloudflare" in response.text.lower():
                raise RuntimeError(
                    "Source blocked by Cloudflare (HTTP 403). Provide a valid MANGA_SOURCE_COOKIE session value and retry."
                )
            response.raise_for_status()
            return response.text

    async def _fetch_ajax_html(self, source_url: str, ajax_url: str) -> str:
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; MangaOriginGetter/0.1; +https://localhost)",
            "Accept": "*/*",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": source_url,
        }
        cookie = os.getenv("MANGA_SOURCE_COOKIE", "").strip()
        if cookie:
            headers["Cookie"] = cookie

        timeout = httpx.Timeout(30.0)
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, headers=headers) as client:
            response = await client.post(ajax_url)
            if response.status_code == 403 and "cloudflare" in response.text.lower():
                return ""
            response.raise_for_status()
            return response.text
