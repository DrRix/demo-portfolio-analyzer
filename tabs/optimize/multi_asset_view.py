"""Multi-Asset (Monte Carlo) Portfolio Optimizer sub-tab.

Functionality exactly mirrors Portfolio Dashboard (S_Optimizer).
"""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core import session, theme
from tabs.performance.calcs import PERIODICITIES, period_returns
from tabs.performance.data import fetch_close_prices

from .calcs import monte_carlo_simulation

LOOKBACKS: dict[str, int | None] = {
    "YTD": None,
    "1Y": 365,
    "2Y": 365 * 2,
    "3Y": 365 * 3,
}


def render() -> None:
    st.markdown("Run a Monte Carlo simulation on the assets selected in the **Ticker Search** tab.")

    symbols = session.get_selected_symbols()
    if len(symbols) < 2:
        st.info("💡 Please go to the **🔎 Ticker Search** tab and select 2 or more assets first.")
        return

    # Own lookback and periodicity controls, independent of the Performance tab
    st.subheader("1. Load Asset Price Data")
    col_lb, col_per, col_btn = st.columns([2, 2, 1], vertical_alignment="bottom")
    lookback = (
        col_lb.segmented_control(
            "Lookback Period",
            options=list(LOOKBACKS),
            default="YTD",
            key="opt_mc_lookback",
        )
        or "YTD"
    )
    periodicity = (
        col_per.segmented_control(
            "Return Periodicity",
            options=[p for p in PERIODICITIES if p != "Annual"],
            default="Daily",
            key="opt_mc_periodicity",
        )
        or "Daily"
    )

    if col_btn.button(
        "Load Asset Prices", type="primary", icon=":material/download:", width="stretch"
    ):
        end = date.today()
        days = LOOKBACKS[lookback]
        start = date(end.year - 1, 12, 31) if days is None else end - timedelta(days=days)
        with st.spinner("Downloading price data..."):
            try:
                prices = fetch_close_prices(tuple(symbols), start, end)
            except Exception as e:
                st.error(f"Failed to download price data: {e}")
                return

        if prices.empty or len(prices.columns) < 2:
            st.error("Could not retrieve price data for at least 2 tickers.")
            return

        st.session_state["opt_mc_price_data"] = {
            "prices": prices,
            "symbols": list(symbols),
            "lookback": lookback,
            "start": start,
            "end": end,
        }

    price_data = st.session_state.get("opt_mc_price_data")
    if price_data is None:
        st.info("Choose a lookback period and press **Load Asset Prices**.")
        return

    if price_data["symbols"] != symbols or price_data["lookback"] != lookback:
        st.warning(
            "Your ticker selection or lookback period has changed since prices were loaded. "
            "Press **Load Asset Prices** to refresh."
        )

    prices: pd.DataFrame = price_data["prices"]
    loaded_lookback: str = price_data["lookback"]
    tickers = [s for s in price_data["symbols"] if s in prices.columns]
    if len(tickers) < 2:
        st.warning("Please load 2 or more assets with valid data to run an optimization.")
        return

    # Risk-free rate
    rfr_input = st.number_input(
        "Risk-Free Rate (%)",
        min_value=0.0,
        max_value=20.0,
        value=2.0,
        step=0.25,
        format="%.2f",
        key="opt_mc_rfr",
    )
    risk_free_rate = rfr_input / 100.0

    st.subheader("2. Simulation Parameters")
    st.info(
        f"**Using loaded data:**\n"
        f"* **Assets ({len(tickers)}):** {', '.join(tickers)}\n"
        f"* **Lookback:** {loaded_lookback}\n"
        f"* **Periodicity:** {periodicity}\n"
        f"* **Risk-Free Rate:** {rfr_input:.2f}% (Using {risk_free_rate:.2%} in calculation)"
    )

    num_simulations = st.number_input(
        "Number of Simulations",
        min_value=1000,
        max_value=50000,
        value=10000,
        step=1000,
        key="opt_mc_num_sims",
        help="The more simulations, the smoother the frontier, but the longer it takes.",
    )

    current_params = (
        tuple(tickers),
        loaded_lookback,
        periodicity,
        risk_free_rate,
        int(num_simulations),
    )

    if st.button(f"Run {int(num_simulations):,} Simulations", type="primary"):
        returns = period_returns(prices[tickers], periodicity).dropna()
        if len(returns) < 2:
            st.error("Not enough return periods to run simulation.")
            return

        with st.spinner("Running Monte Carlo simulation..."):
            results, weights_record, sim_tickers = monte_carlo_simulation(
                returns, periodicity, int(num_simulations), risk_free_rate
            )

            st.session_state.mc_results = results
            st.session_state.mc_weights = weights_record
            st.session_state.mc_tickers = sim_tickers
            st.session_state.mc_params = current_params
            max_sharpe_idx = int(np.argmax(results[2]))
            session.set_optimizer_weights(
                {
                    sym: float(w)
                    for sym, w in zip(sim_tickers, weights_record[max_sharpe_idx])
                }
            )

    # Display Results
    if "mc_results" in st.session_state:
        if st.session_state.get("mc_params") != current_params:
            st.info(
                "Simulation parameters or loaded prices have changed since the last run. "
                "Click **Run Simulations** to refresh the plot."
            )
            return

        st.subheader("Multi-Asset Efficient Frontier Plot")

        results: np.ndarray = st.session_state.mc_results
        weights_record: np.ndarray = st.session_state.mc_weights
        sim_tickers: list[str] = st.session_state.mc_tickers

        # Optimal portfolio (Max Sharpe)
        max_sharpe_idx = int(np.argmax(results[2]))
        ret = float(results[0, max_sharpe_idx])
        vol = float(results[1, max_sharpe_idx])
        sharpe = float(results[2, max_sharpe_idx])
        weights_df = pd.DataFrame(
            {"Weight": weights_record[max_sharpe_idx]}, index=sim_tickers
        )

        active_text_color = theme.active_colors()["text"]
        fig = go.Figure()
        fig.add_trace(
            go.Scattergl(
                x=results[1],
                y=results[0],
                mode="markers",
                marker=dict(
                    color=results[2],
                    colorscale="Viridis",
                    showscale=True,
                    size=5,
                    opacity=0.5,
                    colorbar=dict(title="Sharpe Ratio", thickness=14),
                ),
                name="Simulations",
                hovertemplate=(
                    "<b>Portfolio</b><br>"
                    "Return: %{y:.2%}<br>"
                    "Volatility: %{x:.2%}<br>"
                    "Sharpe Ratio: %{marker.color:.2f}<extra></extra>"
                ),
            )
        )
        fig.add_trace(
            go.Scatter(
                x=[vol],
                y=[ret],
                mode="markers",
                name="Optimal Portfolio",
                marker=dict(
                    color="yellow",
                    size=13,
                    symbol="star",
                    line=dict(width=1.5, color=active_text_color),
                ),
                hovertemplate=(
                    "<b>Optimal Portfolio (Max Sharpe)</b><br>"
                    f"Return: {ret:.2%}<br>"
                    f"Volatility: {vol:.2%}<br>"
                    f"Sharpe Ratio: {sharpe:.2f}<extra></extra>"
                ),
            )
        )

        fig.update_layout(
            title=f"Efficient Frontier: {int(num_simulations):,} Simulations",
            xaxis=dict(title="Annualized Volatility (Risk)", tickformat=".1%"),
            yaxis=dict(title="Annualized Return", tickformat=".1%"),
            showlegend=False,
            height=500,
        )

        col1, col2, col3 = st.columns([1, 3, 1])
        with col2:
            theme.show_chart(fig)

        with st.expander("View Optimal Portfolio Weights"):
            filtered_weights = weights_df[weights_df["Weight"] > 0.001]
            st.dataframe(
                filtered_weights.style.format({"Weight": "{:.2%}"}),
                width="stretch",
            )
