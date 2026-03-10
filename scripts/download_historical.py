"""Download historical futures data from free sources.

Downloads ES/MES data from Yahoo Finance and stores in DuckDB
for backtesting and strategy evolution.

Usage:
    python scripts/download_historical.py              # Download 5-min (60 days)
    python scripts/download_historical.py --all        # Download all timeframes
    python scripts/download_historical.py --tf 1hour   # Specific timeframe
    python scripts/download_historical.py --status     # Show data status
"""
import argparse
import sys
from pathlib import Path

# Ensure project root on path
sys.path.insert(0, str(Path(__file__).parent.parent))

from data_engine.providers.yfinance_provider import YFinanceProvider


def main():
    parser = argparse.ArgumentParser(
        description="Download historical MES/ES futures data"
    )
    parser.add_argument(
        "--tf", "--timeframe",
        default="5min",
        choices=["1min", "5min", "15min", "30min", "1hour", "1day"],
        help="Timeframe to download (default: 5min)",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=None,
        help="Number of days (capped by source limits)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Download all timeframes (5min + 1hour + daily)",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Show current data status and exit",
    )
    args = parser.parse_args()

    provider = YFinanceProvider()

    if args.status:
        print("\n=== PropEdge Data Status ===\n")
        status = provider.get_data_status()
        for tf, info in status.items():
            if info["count"] > 0:
                print(f"  {tf:>6s}: {info['count']:>6,d} candles  "
                      f"({info['start'][:10]} to {info['end'][:10]})")
            else:
                print(f"  {tf:>6s}: (empty)")
        print()
        return

    if args.all:
        print("\n=== Downloading all timeframes ===\n")
        results = provider.download_multi_timeframe()
        print("\n=== Download Summary ===\n")
        for tf, count in results.items():
            print(f"  {tf:>6s}: {count:>6,d} candles")
        total = sum(results.values())
        print(f"  {'TOTAL':>6s}: {total:>6,d} candles")
    else:
        print(f"\nDownloading {args.tf} data...")
        count = provider.download_and_store(
            timeframe=args.tf, days=args.days
        )
        print(f"Done: {count:,d} candles stored")

    # Show final status
    print("\n=== Current Data Status ===\n")
    status = provider.get_data_status()
    for tf, info in status.items():
        if info["count"] > 0:
            print(f"  {tf:>6s}: {info['count']:>6,d} candles  "
                  f"({info['start'][:10]} to {info['end'][:10]})")
    print()


if __name__ == "__main__":
    main()
