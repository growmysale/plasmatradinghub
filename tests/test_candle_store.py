"""Test candle store data operations."""
import pytest
from datetime import datetime, timedelta


def test_insert_and_count():
    from data_engine.candle_store import CandleStore
    from core.types import Candle

    store = CandleStore()

    candles = [
        Candle(
            symbol="MES", timeframe="5min",
            ts=datetime(2025, 1, 2, 9, 30),
            open=5600.0, high=5610.0, low=5595.0, close=5605.0,
            volume=1000,
        ),
        Candle(
            symbol="MES", timeframe="5min",
            ts=datetime(2025, 1, 2, 9, 35),
            open=5605.0, high=5615.0, low=5600.0, close=5610.0,
            volume=1200,
        ),
    ]

    store.insert_candles(candles)
    count = store.get_candle_count()
    assert count >= 2


def test_get_candles_returns_dataframe():
    from data_engine.candle_store import CandleStore
    from core.types import Candle

    store = CandleStore()
    base = datetime(2025, 1, 2, 9, 30)

    candles = [
        Candle(
            symbol="MES", timeframe="5min",
            ts=base + timedelta(minutes=i * 5),
            open=5600.0 + i, high=5610.0 + i, low=5595.0 + i, close=5605.0 + i,
            volume=1000 + i * 100,
        )
        for i in range(10)
    ]

    store.insert_candles(candles)
    df = store.get_candles(limit=10)
    assert len(df) >= 10
    assert "close" in df.columns
    assert "volume" in df.columns


def test_sample_data_generation():
    """Test the built-in sample data generator."""
    from data_engine.candle_store import generate_sample_data
    count = generate_sample_data(days=2)
    assert count > 0
