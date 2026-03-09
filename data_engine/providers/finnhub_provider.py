"""Finnhub Data Provider - Economic Calendar & News.

Free tier: 60 API calls/minute.
Used for economic event scheduling (FOMC, NFP, CPI release dates).
This feeds into the news_blackout_minutes risk rule.

Usage:
    provider = FinnhubProvider()
    events = provider.get_upcoming_events(days=7)
    minutes_to_next = provider.minutes_to_next_event()
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

try:
    import finnhub
    HAS_FINNHUB = True
except ImportError:
    HAS_FINNHUB = False
    logger.info("finnhub-python not installed. Install with: pip install finnhub-python")


# High-impact events that affect MES/ES
HIGH_IMPACT_EVENTS = {
    "FOMC Rate Decision",
    "Non-Farm Payrolls",
    "CPI",
    "Core CPI",
    "GDP",
    "Initial Jobless Claims",
    "Retail Sales",
    "ISM Manufacturing PMI",
    "ISM Services PMI",
    "PPI",
    "Consumer Confidence",
    "PCE Price Index",
    "Core PCE Price Index",
}


class FinnhubProvider:
    """Finnhub economic calendar and market events provider."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("FINNHUB_API_KEY", "")
        self._client = None

        if not HAS_FINNHUB:
            logger.warning("finnhub-python not installed")
            return

        if self.api_key:
            self._client = finnhub.Client(api_key=self.api_key)
            logger.info("Finnhub client initialized")
        else:
            logger.warning("FINNHUB_API_KEY not set. Get free key at https://finnhub.io/")

    @property
    def is_available(self) -> bool:
        return HAS_FINNHUB and self._client is not None

    def get_economic_calendar(
        self,
        start: Optional[str] = None,
        end: Optional[str] = None,
    ) -> List[Dict]:
        """Get economic calendar events.

        Args:
            start: Start date (YYYY-MM-DD). Default: today
            end: End date (YYYY-MM-DD). Default: 7 days from now

        Returns:
            List of event dicts with keys:
            - event: Event name
            - time: Event time
            - impact: Impact level
            - actual: Actual value (if released)
            - estimate: Consensus estimate
            - prev: Previous value
        """
        if not self.is_available:
            raise RuntimeError("Finnhub not available")

        if start is None:
            start = datetime.now().strftime("%Y-%m-%d")
        if end is None:
            end = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")

        data = self._client.calendar_economic(_from=start, to=end)

        events = []
        if isinstance(data, dict) and "economicCalendar" in data:
            for item in data["economicCalendar"]:
                # Only include US events
                if item.get("country", "") == "US":
                    events.append({
                        "event": item.get("event", ""),
                        "time": item.get("time", ""),
                        "impact": item.get("impact", ""),
                        "actual": item.get("actual"),
                        "estimate": item.get("estimate"),
                        "prev": item.get("prev"),
                        "unit": item.get("unit", ""),
                    })

        logger.info(f"Finnhub: {len(events)} US economic events from {start} to {end}")
        return events

    def get_high_impact_events(self, days: int = 7) -> List[Dict]:
        """Get only high-impact economic events that affect ES/MES.

        These are the events we should blackout trading around.
        """
        all_events = self.get_economic_calendar(
            end=(datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")
        )

        high_impact = []
        for event in all_events:
            event_name = event.get("event", "")
            # Check if event matches any high-impact pattern
            for pattern in HIGH_IMPACT_EVENTS:
                if pattern.lower() in event_name.lower():
                    high_impact.append(event)
                    break

        return high_impact

    def minutes_to_next_high_impact_event(self) -> int:
        """Get minutes until the next high-impact economic event.

        Returns 999 if no events within 7 days or provider unavailable.
        Used by the risk manager for news_blackout_minutes.
        """
        if not self.is_available:
            return 999

        try:
            events = self.get_high_impact_events(days=2)
            now = datetime.now()

            for event in events:
                time_str = event.get("time", "")
                if not time_str:
                    continue

                try:
                    event_time = datetime.fromisoformat(time_str.replace("Z", "+00:00"))
                    delta = (event_time - now).total_seconds() / 60
                    if delta > 0:
                        return int(delta)
                except (ValueError, TypeError):
                    continue

            return 999

        except Exception as e:
            logger.warning(f"Could not check event schedule: {e}")
            return 999
