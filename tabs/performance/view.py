"""Performance tab: load price history, then analyse it in sub-tabs.

Sub-tabs (each in its own module):
    returns_view.py       -> "Performance"
    distribution_view.py  -> "Return Distribution"
"""

from __future__ import annotations

from datetime import date, timedelta

import streamlit as st

from core import session, theme

from . import distribution_view, returns_view
from .calcs import PERIODICITIES, period_returns
from .data import fetch_close_prices

# Lookback label -> days back (None = prior-year Dec 31 for YTD). Max 3Y.
LOOKBACKS = {
    "1M": 30,
    "3M": 91,
    "6M": 182,
    "YTD": None,
    "1Y": 365,
    "2Y": 365 * 2,
    "3Y": 365 * 3,
}
DEFAULT_LOOKBACK = "YTD"
DEFAULT_PERIODICITY = "Daily"


def render() -> None:
    st.header("Performance")

    symbols = session.get_selected_symbols()
    if not symbols:
        st.info("Select tickers in the **🔎 Ticker Search** tab first.")
        return

    selected_lookback = _render_loader(symbols)

    data = session.get_price_data()
    if data is None:
        st.info("Choose a lookback period and press **Load prices**.")
        return
    if session.price_data_is_stale():
        st.warning(
            "Your ticker selection has changed since the prices were loaded. "
            "Press **Load prices** to refresh."
        )
    elif selected_lookback != data["lookback"]:
        st.info(
            f"Lookback set to **{selected_lookback}** (currently showing "
            f"**{data['lookback']}**). Press **Load prices** to apply."
        )

    prices = data["prices"]
    missing = [s for s in data["symbols"] if s not in prices.columns]
    if missing:
        st.warning("No price data for: " + ", ".join(missing))
    if prices.empty:
        return

    st.caption(
        f"Daily closes for **{len(prices.columns)}** ticker(s), "
        f"{prices.index[0]:%d %b %Y} → {prices.index[-1]:%d %b %Y} "
        f"({data['lookback']} lookback)."
    )

    periodicity = st.segmented_control(
        "Return periodicity",
        options=list(PERIODICITIES),
        default=DEFAULT_PERIODICITY,
        key="perf_periodicity",
    ) or DEFAULT_PERIODICITY  # None if the user deselects

    returns = period_returns(prices, periodicity)
    if len(returns) < 2:
        st.warning(
            f"Not enough data for **{periodicity.lower()}** returns over this "
            "lookback. Choose a longer lookback or a shorter periodicity."
        )
        return

    colors = theme.ticker_colors(data["symbols"])
    tab_perf, tab_dist = st.tabs(["📈 Performance", "📊 Return Distribution"])
    with tab_perf:
        returns_view.render(prices, returns, periodicity, colors)
    with tab_dist:
        distribution_view.render(returns, periodicity, colors)

    st.caption(
        "Simple price returns from Yahoo Finance closes adjusted for splits and "
        "dividends. Past performance does not guarantee future results."
    )


def _render_loader(symbols: list[str]) -> str:
    """Lookback selection + button that downloads prices into session state."""
    stored = session.get_price_data()
    default = (
        stored["lookback"]
        if stored and stored.get("lookback") in LOOKBACKS
        else DEFAULT_LOOKBACK
    )

    col_lb, col_btn = st.columns([4, 1], vertical_alignment="bottom")
    lookback = col_lb.segmented_control(
        "Lookback period",
        options=list(LOOKBACKS),
        default=default,
        key="perf_lookback",
    ) or default
    load = col_btn.button(
        "Load prices", type="primary", icon=":material/download:", width="stretch"
    )
    if not load:
        return lookback

    end = date.today()
    days = LOOKBACKS[lookback]
    start = date(end.year - 1, 12, 31) if days is None else end - timedelta(days=days)

    try:
        with st.spinner("Downloading prices..."):
            prices = fetch_close_prices(tuple(symbols), start, end)
    except Exception:
        st.error("Price data is unavailable right now. Please try again in a moment.")
        return lookback

    session.set_price_data(prices, symbols, lookback, start, end)
    return lookback
