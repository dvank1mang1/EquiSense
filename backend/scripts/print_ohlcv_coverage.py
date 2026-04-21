"""Summarize date and row coverage for ``data/raw/ohlcv/*.parquet`` (validation helper)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

import pandas as pd  # noqa: E402

def _default_root(cli: Path | None) -> Path:
    if cli is not None:
        return cli.resolve()
    import os

    env = os.environ.get("EQUISENSE_DATA_ROOT", "").strip()
    if env:
        return Path(env).expanduser().resolve()
    return (_BACKEND_ROOT.parent / "data").resolve()


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data-root", type=Path, default=None)
    args = p.parse_args()
    root = _default_root(args.data_root)
    ohlcv_dir = root / "raw" / "ohlcv"
    if not ohlcv_dir.is_dir():
        print("no directory", ohlcv_dir)
        return
    rows_out: list[dict[str, object]] = []
    for path in sorted(ohlcv_dir.glob("*.parquet")):
        sym = path.stem.upper()
        try:
            df = pd.read_parquet(path, columns=["date"])
        except Exception as e:  # noqa: BLE001
            print(sym, "READ_FAIL", e, file=sys.stderr)
            continue
        dt = pd.to_datetime(df["date"], errors="coerce")
        rows_out.append(
            {
                "ticker": sym,
                "rows": int(len(df)),
                "min_date": dt.min(),
                "max_date": dt.max(),
                "null_dates": int(dt.isna().sum()),
            }
        )
    if not rows_out:
        print("no parquet files under", ohlcv_dir)
        return
    tab = pd.DataFrame(rows_out).sort_values("ticker")
    print(tab.to_string(index=False))
    print(
        "\noverall:",
        "tickers=",
        len(tab),
        "min=",
        tab["min_date"].min(),
        "max=",
        tab["max_date"].max(),
    )


if __name__ == "__main__":
    main()
