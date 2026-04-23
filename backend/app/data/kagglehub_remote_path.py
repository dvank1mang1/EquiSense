"""Path templates for KaggleHub per-ticker file downloads (owner/slug + relative path)."""


def format_kagglehub_remote_path(ticker: str, template: str) -> str:
    """
    Substitute ticker placeholders in a dataset-relative path.

    Supported placeholders: ``{TICKER}``, ``{ticker}`` (uppercase symbol),
    ``{ticker_lower}`` (lowercase, for boris-style ``aapl.us.txt`` paths).
    """
    u = ticker.strip().upper()
    low = u.lower()
    return template.replace("{TICKER}", u).replace("{ticker}", u).replace("{ticker_lower}", low)
