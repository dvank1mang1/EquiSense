"""Fetch ``GET /api/v1/backtesting/{ticker}/suite`` and write JSON for offline review."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import httpx


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--base-url", default="http://localhost:8000", help="API root (no /api/v1)")
    p.add_argument("--ticker", required=True)
    p.add_argument(
        "--out",
        type=Path,
        default=Path(__file__).resolve().parents[2] / "notebooks" / "results" / "backtest_suite.json",
    )
    p.add_argument("--include-ml", default="model_d", help="model_d | none | all | comma list")
    p.add_argument("--start-date", default=None)
    p.add_argument("--end-date", default=None)
    args = p.parse_args()

    url = f"{args.base_url.rstrip('/')}/api/v1/backtesting/{args.ticker.strip().upper()}/suite"
    params: dict[str, str] = {"include_ml": args.include_ml}
    if args.start_date:
        params["start_date"] = args.start_date
    if args.end_date:
        params["end_date"] = args.end_date

    with httpx.Client(timeout=300.0) as client:
        r = client.get(url, params=params)
        r.raise_for_status()
        data = r.json()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    print("wrote", args.out)


if __name__ == "__main__":
    try:
        main()
    except httpx.HTTPError as e:
        print(e, file=sys.stderr)
        sys.exit(1)
