"""'Performance' sub-tab: charts (Price and Cumulative return) and returns table."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core import theme

from .calcs import cumulative_returns

GRID_COLUMNS = 2


def render(
    prices: pd.DataFrame,
    returns: pd.DataFrame,
    periodicity: str,
    colors: dict[str, str],
) -> None:
    col_metric, col_layout = st.columns(2)
    metric = col_metric.segmented_control(
        "Show",
        options=["Price", "Cumulative return"],
        default="Price",
        key="perf_metric",
    ) or "Price"
    layout = col_layout.segmented_control(
        "Layout",
        options=["Combined", "Separate"],
        default="Combined",
        key="perf_layout",
    ) or "Combined"

    show_price = metric == "Price"
    data = prices if show_price else cumulative_returns(returns)

    if layout == "Combined":
        _combined_chart(data, colors, show_price=show_price)
    else:
        _separate_charts(data, colors, show_price=show_price)


def _combined_chart(data: pd.DataFrame, colors: dict[str, str], show_price: bool) -> None:
    fig = go.Figure()
    for symbol in data.columns:
        s = data[symbol].dropna()
        hover = (
            f"{symbol}: $%{{y:,.2f}}<extra></extra>"
            if show_price
            else f"{symbol}: %{{y:.2%}}<extra></extra>"
        )
        fig.add_trace(go.Scatter(
            x=s.index,
            y=s,
            name=symbol,
            mode="lines",
            line=dict(color=colors.get(symbol), width=2),
            hovertemplate=hover,
        ))
    if not show_price:
        fig.add_hline(y=0, line_dash="dash", line_color=theme.NEUTRAL, line_width=1)
    fig.update_layout(
        title="Historical price" if show_price else "Cumulative return",
        yaxis_tickformat="$,.2f" if show_price else ".0%",
    )
    theme.show_chart(fig, height=480)


def _separate_charts(data: pd.DataFrame, colors: dict[str, str], show_price: bool) -> None:
    symbols = list(data.columns)
    for i in range(0, len(symbols), GRID_COLUMNS):
        cols = st.columns(GRID_COLUMNS)
        for col, symbol in zip(cols, symbols[i:i + GRID_COLUMNS]):
            with col:
                s = data[symbol].dropna()
                fig = go.Figure()
                hover = "$%{y:,.2f}<extra></extra>" if show_price else "%{y:.2%}<extra></extra>"
                fig.add_trace(go.Scatter(
                    x=s.index,
                    y=s,
                    mode="lines",
                    fill="tozeroy",
                    line=dict(color=colors.get(symbol), width=2),
                    hovertemplate=hover,
                ))
                if not show_price:
                    fig.add_hline(y=0, line_dash="dash", line_color=theme.NEUTRAL, line_width=1)
                fig.update_layout(
                    title=dict(text=symbol, font=dict(color=colors.get(symbol))),
                    showlegend=False,
                    yaxis_tickformat="$,.2f" if show_price else ".0%",
                )
                theme.show_chart(fig, height=300)

