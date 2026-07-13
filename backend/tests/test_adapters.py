from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

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
