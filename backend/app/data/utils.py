"""Shared helpers for data adapters."""


def normalize_ticker(ticker: str) -> str:
    return ticker.strip().upper()
