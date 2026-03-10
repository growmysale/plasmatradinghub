"""MES Futures Contract Resolver.

Resolves the current front-month Micro E-mini S&P 500 (MES) contract symbol.
MES contracts expire quarterly: H=March, M=June, U=September, Z=December.

Contract code format: MES + month_letter + last_digit_of_year
  e.g., MESH6 = March 2026, MESM6 = June 2026

Rollover: typically occurs ~8 calendar days before the third Friday
of the expiration month (the actual expiry date).
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

# Quarterly expiration months and their CME month codes
QUARTER_MONTHS = {3: "H", 6: "M", 9: "U", 12: "Z"}
EXPIRY_MONTHS = sorted(QUARTER_MONTHS.keys())


class ContractResolver:
    """Resolves MES quarterly contract symbols."""

    def __init__(self, rollover_days_before_expiry: int = 8):
        self.rollover_offset = rollover_days_before_expiry

    def get_front_month(self, today: Optional[date] = None) -> str:
        """Return the front-month MES contract symbol.

        Examples:
            2026-03-09 → "MESH6"   (March 2026, before rollover)
            2026-03-15 → "MESM6"   (June 2026, after March rollover)
            2026-06-10 → "MESM6"   (June 2026, before rollover)
            2026-06-14 → "MESU6"   (September 2026, after June rollover)
        """
        today = today or date.today()

        for month in EXPIRY_MONTHS:
            expiry = self._third_friday(today.year, month)
            rollover_date = expiry - timedelta(days=self.rollover_offset)

            if today < rollover_date:
                # This quarter's contract is still the front month
                code = QUARTER_MONTHS[month]
                year_digit = today.year % 10
                symbol = f"MES{code}{year_digit}"
                return symbol

        # Past December rollover → next year's March contract
        code = QUARTER_MONTHS[3]
        year_digit = (today.year + 1) % 10
        return f"MES{code}{year_digit}"

    def _third_friday(self, year: int, month: int) -> date:
        """Compute the third Friday of a given month."""
        # First day of month
        first = date(year, month, 1)
        # Day of week: Monday=0, Friday=4
        days_until_friday = (4 - first.weekday()) % 7
        first_friday = first + timedelta(days=days_until_friday)
        third_friday = first_friday + timedelta(weeks=2)
        return third_friday

    def get_rollover_date(self, today: Optional[date] = None) -> date:
        """Get the next rollover date from today."""
        today = today or date.today()

        for month in EXPIRY_MONTHS:
            expiry = self._third_friday(today.year, month)
            rollover_date = expiry - timedelta(days=self.rollover_offset)
            if today < rollover_date:
                return rollover_date

        # Next year March
        return self._third_friday(today.year + 1, 3) - timedelta(
            days=self.rollover_offset
        )

    async def verify_contract(self, symbol: str, tradovate_rest) -> bool:
        """Verify the contract exists on Tradovate."""
        try:
            result = await tradovate_rest.find_contract(symbol)
            if result and "id" in result:
                logger.info(f"Verified contract {symbol}: id={result['id']}")
                return True
            logger.warning(f"Contract {symbol} not found on Tradovate")
            return False
        except Exception as e:
            logger.error(f"Contract verification failed for {symbol}: {e}")
            return False
