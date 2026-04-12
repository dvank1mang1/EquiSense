"""Фильтр новостей: спам и релевантность тикеру."""

import pytest

from app.data.news_filter import filter_news_for_ticker


@pytest.mark.unit
def test_filter_drops_pypi_spam() -> None:
    items = [
        {
            "title": "nabla-quant 0.1.0",
            "url": "https://pypi.org/project/nabla-quant/",
            "content": "Release",
        },
        {
            "title": "Apple reports quarterly results",
            "url": "https://example.com/aapl",
            "content": "AAPL revenue beat",
        },
    ]
    out = filter_news_for_ticker(items, "AAPL", company_name="Apple Inc", limit=10)
    assert len(out) == 1
    assert "quarterly" in out[0]["title"].lower()


@pytest.mark.unit
def test_filter_keeps_ticker_in_title() -> None:
    items = [
        {
            "title": "Traders watch MSFT ahead of earnings",
            "url": "https://example.com/x",
            "content": "",
        }
    ]
    out = filter_news_for_ticker(items, "MSFT", company_name=None, limit=5)
    assert len(out) == 1
