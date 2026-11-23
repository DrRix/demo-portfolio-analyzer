"""Two-Asset Portfolio Optimizer sub-tab.

Functionality exactly mirrors Portfolio Dashboard (S_Optimizer).
"""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core import session, theme
from tabs.performance.data import fetch_close_prices

from .calcs import calculate_two_asset_frontier

LOOKBACKS: dict[str, int | None] = {
    "YTD": None,
    "1Y": 365,
    "2Y": 365 * 2,
    "3Y": 365 * 3,
}


def render() -> None:
    st.markdown("Generate a simple efficient frontier for a two-asset portfolio.")
    st.subheader("1. Select Parameters")

    pool_tickers = session.get_selected_symbols()
    options = sorted(list(set(pool_tickers + ["SPY", "TLT"])))
    default_t1 = "SPY" if "SPY" in options else options[0]
    default_t2 = "TLT" if "TLT" in options else options[min(1, len(options) - 1)]

    if st.session_state.get("two_asset_ticker1") not in options:
        st.session_state["two_asset_ticker1"] = default_t1
    if st.session_state.get("two_asset_ticker2") not in options:
        st.session_state["two_asset_ticker2"] = default_t2

    col1, col2 = st.columns(2)
    with col1:
        ticker1 = st.selectbox(
            "Asset 1 (e.g., Equities)", options=options, key="two_asset_ticker1"
        )
    with col2:
        ticker2 = st.selectbox(
            "Asset 2 (e.g., Fixed Income)", options=options, key="two_asset_ticker2"
        )

    lookback = (
        st.segmented_control(
            "Lookback Period",
            options=list(LOOKBACKS),
            default="YTD",
            key="two_asset_lookback",
        )
        or "YTD"
    )

    c3, c4 = st.columns(2)
    with c3:
        periodicity = st.radio(
            "Return Periodicity",
            ("Daily", "Weekly", "Monthly", "Quarterly"),
            horizontal=True,
            key="optimizer_periodicity",
        )
    with c4:
        num_combinations = st.number_input(
            "Number of Combinations",
            min_value=11,
            max_value=1001,
            value=101,
            step=10,
            key="two_asset_num_combinations",
            help="Number of portfolios to calculate (e.g., 101 for 0% to 100% in 1% steps).",
        )

    tickers_list = [ticker1.strip().upper(), ticker2.strip().upper()]

    # Calculation Button
    if st.button("Generate Efficient Frontier", type="primary"):
        if not ticker1 or not ticker2:
            st.error("Please enter two valid tickers.")
        elif ticker1 == ticker2:
            st.error("Please enter two *different* tickers.")
        else:
            end_date = date.today()
            days = LOOKBACKS[lookback]
            start_date = (
                date(end_date.year - 1, 12, 31)
                if days is None
                else end_date - timedelta(days=days)
            )
            with st.spinner(f"Fetching data for {tickers_list[0]} and {tickers_list[1]}..."):
                try:
                    prices = fetch_close_prices(tuple(tickers_list), start_date, end_date)
                except Exception as e:
                    st.error(f"An error occurred: {e}")
                    return

                if prices.empty or len(prices.columns) < 2:
                    st.error("Could not retrieve valid data for *both* tickers. Check your inputs.")
                    return

            with st.spinner("Calculating frontier..."):
                results_df = calculate_two_asset_frontier(prices, periodicity, num_combinations, tickers_list)

                if results_df is not None:
                    st.session_state.frontier_results = results_df
                    st.session_state.frontier_tickers = tickers_list
                else:
                    st.session_state.pop("frontier_results", None)
                    st.session_state.pop("frontier_tickers", None)
                    st.warning(
                        "Not enough overlapping return periods to calculate the frontier. "
                        "Try a longer date range or a shorter periodicity."
                    )

    # Display Results
    if "frontier_results" in st.session_state and st.session_state.get("frontier_tickers") == tickers_list:
        st.subheader("Two Asset Efficient Frontier Plot")

        results_df: pd.DataFrame = st.session_state.frontier_results

        min_vol_idx = int(results_df["Volatility"].idxmin())
        min_vol_row = results_df.loc[min_vol_idx]
        if results_df.iloc[-1]["Return"] >= results_df.iloc[0]["Return"]:
            efficient_df = results_df.loc[min_vol_idx:].copy()
        else:
            efficient_df = results_df.loc[:min_vol_idx].iloc[::-1].copy()

        fig = go.Figure()

        fig.add_trace(
            go.Scatter(
                x=efficient_df["Volatility"],
                y=efficient_df["Return"],
                mode="lines+markers",
                name="Efficient Frontier",
                customdata=efficient_df["Weights"],
                line=dict(color=theme.POSITIVE, width=2.5),
                marker=dict(color=theme.POSITIVE, size=5),
                hovertemplate=(
                    "<b>%{customdata}</b><br>"
                    "Annualized Return: %{y:.2%}<br>"
                    "Annualized Volatility: %{x:.2%}"
                    "<extra></extra>"
                ),
            )
        )

        fig.add_trace(
            go.Scatter(
                x=[min_vol_row["Volatility"]],
                y=[min_vol_row["Return"]],
                mode="markers",
                name="Min Volatility",
                customdata=[min_vol_row["Weights"]],
                marker=dict(color=theme.ACCENT, size=12, symbol="star"),
                hovertemplate=(
                    "<b>Min Volatility (%{customdata})</b><br>"
                    "Annualized Return: %{y:.2%}<br>"
                    "Annualized Volatility: %{x:.2%}"
                    "<extra></extra>"
                ),
            )
        )

        fig.update_layout(
            title=f"Efficient Frontier: {tickers_list[0]} vs. {tickers_list[1]}",
            xaxis=dict(title="Annualized Volatility (Risk)", tickformat=".1%"),
            yaxis=dict(title="Annualized Return", tickformat=".1%"),
            showlegend=True,
            height=500,
        )

        col1, col2, col3 = st.columns([1, 3, 1])
        with col2:
            theme.show_chart(fig)

        with st.expander("View Full Combination Data"):
            st.dataframe(
                results_df.style.format({"Return": "{:.2%}", "Volatility": "{:.2%}"}),
                width="stretch",
            )
