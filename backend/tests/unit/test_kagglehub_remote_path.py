from app.data.kagglehub_remote_path import format_kagglehub_remote_path


def test_format_kagglehub_remote_path_placeholders() -> None:
    assert format_kagglehub_remote_path("aapl", "stocks/{ticker}.csv") == "stocks/AAPL.csv"
    assert format_kagglehub_remote_path("MSFT", "x/{TICKER}.csv") == "x/MSFT.csv"
    assert (
        format_kagglehub_remote_path("Nvda", "Data/Stocks/{ticker_lower}.us.txt")
        == "Data/Stocks/nvda.us.txt"
    )
