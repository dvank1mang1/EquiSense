"""Фильтрация ленты новостей: спам (PyPI/npm), релевантность тикеру / компании / фин. контексту."""

from __future__ import annotations

import re
from typing import Any

_FIN_KEYWORD = re.compile(
    r"\b(stock|stocks|share|shares|earnings|revenue|investor|investors|analyst|analysts|"
    r"quarter|quarterly|dividend|nasdaq|nyse|trading|sec filing|fiscal|eps|guidance|"
    r"ceo|cfo|market cap|buyback|acquisition|merger|upgrade|downgrade|forecast|"
    r"guidance|wall street|shares of)\b",
    re.I,
)


def _is_spam_news(title: str, url: str, description: str = "") -> bool:
    tl = title.lower()
    ul = url.lower()
    dl = description.lower()
    if any(x in ul for x in ("pypi.org", "npmjs.com", "packagist.org", "crates.io", "rubygems.org")):
        return True
    blob = f"{tl} {dl}"
    spam_phrases = (
        "added to pypi",
        "added to npm",
        "published on pypi",
        "published to pypi",
        "on pypi:",
        "pypi package",
    )
    return any(s in blob for s in spam_phrases)


def _company_name_hints(name: str | None) -> list[str]:
    if not name or not str(name).strip():
        return []
    raw = str(name).strip()
    if raw.upper() == raw and len(raw) <= 5:
        return []
    parts = re.split(r"[\s,]+", raw)
    hints: list[str] = []
    for p in parts:
        p = p.strip()
        if len(p) >= 4:
            hints.append(p)
    if len(raw) >= 8 and " " in raw:
        hints.append(raw)
    return hints[:6]


def _text_blob(title: str, description: str) -> str:
    return f"{title} {description}"


def _is_relevant_article(
    sym: str,
    title: str,
    description: str,
    url: str,
    company_name: str | None,
) -> bool:
    title = title or ""
    description = (description or "")[:1200]
    url = url or ""
    if _is_spam_news(title, url, description):
        return False

    blob = _text_blob(title, description)
    sym_u = sym.upper()
    if re.search(rf"\b{re.escape(sym_u)}\b", blob, re.I):
        return True

    for hint in _company_name_hints(company_name):
        if re.search(rf"\b{re.escape(hint)}\b", blob, re.I):
            return True

    if _FIN_KEYWORD.search(title):
        return True
    return False


def filter_news_for_ticker(
    items: list[dict[str, Any]],
    sym: str,
    *,
    company_name: str | None,
    limit: int,
) -> list[dict[str, Any]]:
    """Убирает нерелевантный шум (NewsAPI по «AAPL» ловит пакеты и пр.); сохраняет порядок."""
    sym = sym.strip().upper()
    kept: list[dict[str, Any]] = []
    for it in items:
        t = str(it.get("title") or "")
        u = str(it.get("url") or "")
        c = str(it.get("content") or "")
        if _is_relevant_article(sym, t, c, u, company_name):
            kept.append(it)
        if len(kept) >= limit * 3:
            break

    if len(kept) < min(limit, 5):
        relaxed: list[dict[str, Any]] = []
        for it in items:
            t = str(it.get("title") or "")
            u = str(it.get("url") or "")
            c = str(it.get("content") or "")
            if not _is_spam_news(t, u, c):
                relaxed.append(it)
        if len(relaxed) > len(kept):
            kept = relaxed

    return kept[:limit]
