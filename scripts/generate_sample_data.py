"""Generate sample MES futures data for testing PropEdge.

Creates realistic-looking 5-minute candle data for the MES (Micro E-mini S&P 500).
This is SIMULATED data for testing the platform, not real market data.

Usage:
    python scripts/generate_sample_data.py [days]
    python scripts/generate_sample_data.py 90
"""
import sys
import os
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path

# Ensure project root on path
sys.path.insert(0, str(Path(__file__).parent.parent))

from data_engine.candle_store import CandleStore


def generate_mes_data(days: int = 90, start_price: float = 5600.0):
    """Generate realistic-looking MES 5-minute candle data."""
    store = CandleStore()

    candles = []
    price = start_price
    dt = datetime(2025, 10, 1, 9, 30)  # Start date

    for day in range(days):
        # Skip weekends
        while dt.weekday() >= 5:
            dt += timedelta(days=1)

        daily_vol = np.random.uniform(0.003, 0.015)  # Daily volatility
        daily_drift = np.random.normal(0, 0.001)  # Slight random drift

        # Trading session: 9:30 AM - 4:00 PM ET (78 five-minute bars)
        for bar in range(78):
            bar_time = dt + timedelta(minutes=bar * 5)

            # Time-based volatility (higher at open and close)
            hour = bar_time.hour + bar_time.minute / 60
            time_vol_mult = 1.0
            if hour < 10.5:  # First hour
                time_vol_mult = 1.5
            elif hour > 15:  # Last hour
                time_vol_mult = 1.3
            elif 12 <= hour <= 13:  # Lunch lull
                time_vol_mult = 0.6

            bar_vol = daily_vol / np.sqrt(78) * time_vol_mult
            returns = np.random.normal(daily_drift / 78, bar_vol)

            open_price = price
            close_price = price * (1 + returns)

            # High/low with realistic wicks
            wick_factor = abs(returns) * np.random.uniform(0.5, 2.0)
            high = max(open_price, close_price) + abs(np.random.normal(0, price * wick_factor * 0.5))
            low = min(open_price, close_price) - abs(np.random.normal(0, price * wick_factor * 0.5))

            # Ensure price stays on tick boundaries (0.25 for MES)
            open_price = round(open_price * 4) / 4
            high = round(high * 4) / 4
            low = round(low * 4) / 4
            close_price = round(close_price * 4) / 4

            # Volume (higher at open/close, lower at lunch)
            base_volume = np.random.randint(500, 3000)
            volume = int(base_volume * time_vol_mult)

            candles.append({
                "symbol": "MESM6",
                "timeframe": "5min",
                "timestamp": bar_time.isoformat(),
                "open": open_price,
                "high": high,
                "low": low,
                "close": close_price,
                "volume": volume,
            })

            price = close_price

        # Next trading day
        dt += timedelta(days=1)

    # Store candles
    stored = store.store_candles(candles)
    count = store.get_candle_count()
    print(f"Generated {len(candles)} candles ({days} trading days)")
    print(f"Price range: {min(c['open'] for c in candles):.2f} - {max(c['high'] for c in candles):.2f}")
    print(f"Total candles in store: {count}")


if __name__ == "__main__":
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 90
    generate_mes_data(days=days)
