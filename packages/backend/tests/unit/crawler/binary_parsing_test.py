from typing import cast
from unittest.mock import patch

import aiohttp
import pytest

from src.crawler import ClauseaCrawler
from src.document_processor import DocumentProcessor


@pytest.mark.asyncio
async def test_document_processor_pdf_fallbacks_are_invoked():
    # Ensure _extract_text delegates to pdfminer/tika fallbacks when configured
    dp = DocumentProcessor(enable_binary_parsing=True, prefer_pdfminer=True, prefer_tika=True)

    # Mock pdfplumber to return no text (empty pages), so it falls back to pdfminer
    class FakePdf:
        def __init__(self):
            self.pages = [FakePage()]

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    class FakePage:
        def extract_text(self):
            return None  # No text extracted, triggering fallback

    with patch("src.document_processor.pdfplumber.open", return_value=FakePdf()):
        # Patch pdfminer at the module level (it's imported inside the method)
        with patch("pdfminer.high_level.extract_text", return_value="pdfminer extracted text"):
            text = await dp._extract_text(b"%PDF-", "dummy.pdf", "application/pdf")
            assert text == "pdfminer extracted text"


@pytest.mark.asyncio
async def test_crawler_respects_enable_binary_crawling_flag(monkeypatch):
    # Create a crawler that enables binary crawling and disables robots.txt checking
    crawler = ClauseaCrawler(enable_binary_crawling=True, respect_robots_txt=False)

    # Mock an aiohttp response via a lightweight fake
    class FakeResponse:
        def __init__(self, status, headers, content_bytes):
            self.status = status
            self.headers = headers
            self._content = content_bytes

        async def read(self):
            return self._content

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

    class FakeSession:
        def get(self, url, **kwargs):
            # Return an async context manager (not a coroutine)
            # In aiohttp, session.get() is a regular method that returns an async context manager
            return FakeResponse(200, {"content-type": "application/pdf"}, b"%PDF-1.4 dummy")

    # Monkeypatch DocumentProcessor._extract_text to return content
    # Note: _extract_text is an instance method, so it takes 'self' as first parameter
    async def fake_extract(self, file_content, filename, content_type):
        return "legal pdf content"

    monkeypatch.setattr(DocumentProcessor, "_extract_text", fake_extract)

    session = FakeSession()
    res = await crawler._fetch_page_internal(
        cast(aiohttp.ClientSession, session), "https://example.com/privacy.pdf"
    )

    assert res.success is True
    assert "legal pdf content" in res.content
    assert res.metadata.get("content-type") == "application/pdf"
