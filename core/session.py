"""Central place for everything stored in ``st.session_state``.

Tabs should use these helpers instead of touching session_state keys directly,
so the shape of the shared state is defined in one place.
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

SELECTED_TICKERS = "selected_tickers"
PRICE_DATA = "price_data"
OPTIMIZER_WEIGHTS = "optimizer_weights"

# Keep the public demo light on API calls.
MAX_TICKERS = 15


def init_state() -> None:
    """Create default session_state entries on first run."""
    st.session_state.setdefault(SELECTED_TICKERS, [])
    st.session_state.setdefault(PRICE_DATA, None)
    st.session_state.setdefault(OPTIMIZER_WEIGHTS, None)


# --- Selected tickers --------------------------------------------------------

def get_selected_tickers() -> list[dict]:
    """Selected tickers as a list of dicts: symbol, name, exchange, type."""
    return st.session_state[SELECTED_TICKERS]


def get_selected_symbols() -> list[str]:
    return [t["symbol"] for t in get_selected_tickers()]


def add_ticker(ticker: dict) -> bool:
    """Add a ticker if not already selected and below the limit.

    Returns True if it was added.
    """
    selected = get_selected_tickers()
    if ticker["symbol"] in get_selected_symbols() or len(selected) >= MAX_TICKERS:
        return False
    selected.append(ticker)
    return True


def remove_ticker(symbol: str) -> None:
    st.session_state[SELECTED_TICKERS] = [
        t for t in get_selected_tickers() if t["symbol"] != symbol
    ]


def clear_tickers() -> None:
    st.session_state[SELECTED_TICKERS] = []


# --- Downloaded price data ---------------------------------------------------

def set_price_data(
    prices: pd.DataFrame, symbols: list[str], lookback: str, start: date, end: date
) -> None:
    """Store daily close prices plus the parameters they were loaded with."""
    st.session_state[PRICE_DATA] = {
        "prices": prices,          # DatetimeIndex rows, one column per symbol
        "symbols": list(symbols),  # symbols requested (some may have no data)
        "lookback": lookback,
        "start": start,
        "end": end,
    }


def get_price_data() -> dict | None:
    return st.session_state[PRICE_DATA]


def price_data_is_stale() -> bool:
    """True if the ticker selection changed since prices were loaded."""
    data = get_price_data()
    return data is not None and data["symbols"] != get_selected_symbols()


# --- Optimizer optimal weights -----------------------------------------------

def set_optimizer_weights(weights: dict[str, float]) -> None:
    """Store latest Multi-Asset Optimizer Max Sharpe weights (symbol -> decimal)."""
    st.session_state[OPTIMIZER_WEIGHTS] = {
        str(sym).strip().upper(): float(w) for sym, w in weights.items()
    }


def get_optimizer_weights() -> dict[str, float] | None:
    return st.session_state.get(OPTIMIZER_WEIGHTS)
