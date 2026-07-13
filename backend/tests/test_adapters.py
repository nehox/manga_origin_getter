from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.adapters.base import SourceAdapter
from app.adapters.mangas_origines import MangasOriginesAdapter
from app.adapters.hentai_origines import HentaiOriginesAdapter


class TestMangasOriginesAdapterCover:
    @pytest.mark.asyncio
    async def test_extract_cover_url_found(self):
        adapter = MangasOriginesAdapter()
        html = '<html><head><meta property="og:image" content="https://mangas-origines.fr/wp-content/uploads/2024/08/test.gif" /></head></html>'

        with patch.object(adapter, "_fetch_html", AsyncMock(return_value=html)):
            url = await adapter.extract_cover_url("https://mangas-origines.fr/oeuvre/test/")
            assert url == "https://mangas-origines.fr/wp-content/uploads/2024/08/test.gif"

    @pytest.mark.asyncio
    async def test_extract_cover_url_not_found(self):
        adapter = MangasOriginesAdapter()
        html = "<html><head></head></html>"

        with patch.object(adapter, "_fetch_html", AsyncMock(return_value=html)):
            url = await adapter.extract_cover_url("https://mangas-origines.fr/oeuvre/test/")
            assert url is None

    @pytest.mark.asyncio
    async def test_extract_cover_url_empty_content(self):
        adapter = MangasOriginesAdapter()
        html = '<html><head><meta property="og:image" content="" /></head></html>'

        with patch.object(adapter, "_fetch_html", AsyncMock(return_value=html)):
            url = await adapter.extract_cover_url("https://mangas-origines.fr/oeuvre/test/")
            assert url is None


class TestHentaiOriginesAdapterCover:
    @pytest.mark.asyncio
    async def test_extract_cover_url_returns_none(self):
        adapter = HentaiOriginesAdapter()
        url = await adapter.extract_cover_url("https://hentai-origines.com/oeuvre/test/")
        assert url is None


class TestExtractCategories:
    @pytest.mark.asyncio
    async def test_base_raises_not_implemented(self):
        adapter = SourceAdapter()
        with pytest.raises(NotImplementedError):
            await adapter.extract_categories("http://example.com")

    @pytest.mark.asyncio
    async def test_mangas_origines_parses_genre_links(self):
        adapter = MangasOriginesAdapter()
        html = """
        <html>
        <a href="https://mangas-origines.fr/manga-genres/action/">Action</a>
        <a href="https://mangas-origines.fr/manga-genres/aventure/">Aventure</a>
        <a href="https://mangas-origines.fr/manga-genres/comedy/">Comedy</a>
        <a href="https://mangas-origines.fr/oeuvre/foo/">Bar</a>
        </html>
        """
        with patch.object(adapter, "_fetch_html", AsyncMock(return_value=html)):
            cats = await adapter.extract_categories("https://mangas-origines.fr/oeuvre/test/")
            assert sorted(cats) == sorted(["Action", "Aventure", "Comedy"])

    @pytest.mark.asyncio
    async def test_mangas_origines_empty_when_no_genres(self):
        adapter = MangasOriginesAdapter()
        html = "<html><body>No genres here</body></html>"
        with patch.object(adapter, "_fetch_html", AsyncMock(return_value=html)):
            cats = await adapter.extract_categories("https://mangas-origines.fr/oeuvre/test/")
            assert cats == []

    @pytest.mark.asyncio
    async def test_hentai_returns_adulte(self):
        adapter = HentaiOriginesAdapter()
        assert await adapter.extract_categories("http://example.com") == ["Adulte"]

    @pytest.mark.asyncio
    async def test_hentai_returns_adulte_even_with_html(self):
        adapter = HentaiOriginesAdapter()
        with patch.object(adapter, "_fetch_html", AsyncMock(return_value="<html></html>")):
            assert await adapter.extract_categories("http://example.com") == ["Adulte"]
