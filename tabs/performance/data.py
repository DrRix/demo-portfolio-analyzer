"""Price data download for the Performance tab (no UI code here)."""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import streamlit as st
import yfinance as yf


class _EmptyDownloadError(Exception):
    """Raised when Yahoo Finance returns no usable price rows (never cached)."""


@st.cache_data(ttl=3600, show_spinner=False, max_entries=100)
def _fetch_close_prices_cached(symbols: tuple[str, ...], start: date, end: date) -> pd.DataFrame:
    raw = yf.download(
        list(symbols),
        start=start,
        end=end + timedelta(days=1),  # yfinance's end is exclusive
        auto_adjust=True,  # prices adjusted for splits and dividends
        progress=False,
        threads=True,
        timeout=20,
    )
    if raw is None or raw.empty or "Close" not in raw:
        raise _EmptyDownloadError()

    close = raw["Close"]
    if isinstance(close, pd.Series):  # defensive: older single-ticker shape
        close = close.to_frame(name=symbols[0])

    close.index = pd.to_datetime(close.index, utc=True).tz_localize(None)
    close = close.dropna(axis=1, how="all").sort_index()
    # Keep the user's order of tickers.
    result = close[[s for s in symbols if s in close.columns]]
    if result.empty:
        raise _EmptyDownloadError()
    return result


def fetch_close_prices(symbols: tuple[str, ...], start: date, end: date) -> pd.DataFrame:
    """Daily adjusted close prices, one column per symbol.

    ``end`` is inclusive. Symbols with no data are dropped (the caller can
    compare the returned columns with ``symbols`` to report them).
    Empty results are not cached; raises on network / API errors.
    """
    if not symbols:
        return pd.DataFrame()
    try:
        return _fetch_close_prices_cached(symbols, start, end)
    except _EmptyDownloadError:
        return pd.DataFrame()

