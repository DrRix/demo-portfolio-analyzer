"""Pure return calculations (no Streamlit, no network).

Method follows the Portfolio Dashboard (S_Explorer / S_Optimizer):
forward-fill prices -> take the last close of each period -> simple
returns (pct_change) -> geometric annualisation.

``prices``: DatetimeIndex rows, one column per ticker.
"""

from __future__ import annotations

import pandas as pd

# periodicity -> (pandas frequency, periods per year)
PERIODICITIES: dict[str, tuple[str | None, int]] = {
    "Daily": (None, 252),
    "Weekly": ("W-FRI", 52),
    "Monthly": ("ME", 12),
    "Quarterly": ("QE", 4),
    "Annual": ("YE", 1),
}


def annualization_factor(periodicity: str) -> int:
    return PERIODICITIES[periodicity][1]


def period_prices(prices: pd.DataFrame, periodicity: str) -> pd.DataFrame:
    """Last available close of each period.

    Rows are labelled with the actual last trading date of the period
    (not the calendar period end), so the current, unfinished period shows
    today's date rather than a date in the future.
    """
    filled = prices.ffill()
    freq = PERIODICITIES[periodicity][0]
    if freq is None:
        return filled
    return filled.groupby(pd.Grouper(freq=freq)).tail(1)


def period_returns(prices: pd.DataFrame, periodicity: str) -> pd.DataFrame:
    """Simple price returns per period. First row of each ticker is NaN."""
    return period_prices(prices, periodicity).pct_change().iloc[1:]


def cumulative_returns(returns: pd.DataFrame) -> pd.DataFrame:
    """Compounded return since the start of each ticker's history (0 = flat)."""
    return (1 + returns.fillna(0)).cumprod().where(returns.notna().cummax()) - 1

