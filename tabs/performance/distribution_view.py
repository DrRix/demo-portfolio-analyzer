"""'Return Distribution' sub-tab: one histogram per ticker."""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core import theme

GRID_COLUMNS = 2


def render(returns: pd.DataFrame, periodicity: str, colors: dict[str, str]) -> None:
    col_bins, col_normal = st.columns([3, 1], vertical_alignment="bottom")
    bins = col_bins.slider("Number of bins", 10, 100, 40, step=5, key="dist_bins")
    show_normal = col_normal.toggle("Normal curve", value=True, key="dist_normal",
                                    help="Overlay a normal distribution with the same mean and volatility.")

    symbols = [s for s in returns.columns if returns[s].dropna().size >= 2]
    if not symbols:
        st.info("Not enough periods to build histograms.")
        return

    for i in range(0, len(symbols), GRID_COLUMNS):
        cols = st.columns(GRID_COLUMNS)
        for col, symbol in zip(cols, symbols[i:i + GRID_COLUMNS]):
            with col:
                _histogram(returns[symbol].dropna(), symbol, colors.get(symbol, theme.ACCENT),
                           bins, show_normal, periodicity)


def _histogram(r: pd.Series, symbol: str, color: str, bins: int,
               show_normal: bool, periodicity: str) -> None:
    edges = np.histogram_bin_edges(r, bins=bins)
    width = edges[1] - edges[0]
    mean, std = r.mean(), r.std()
    active_colors = theme.active_colors()

    fig = go.Figure(go.Histogram(
        x=r,
        xbins=dict(start=edges[0], end=edges[-1], size=width),
        histnorm="probability",
        marker=dict(color=color, line=dict(color=active_colors["background"], width=0.5)),
        opacity=0.85,
        hovertemplate="Return: %{x}<br>Share of periods: %{y:.1%}<extra></extra>",
    ))

    if show_normal and std > 0:
        x = np.linspace(edges[0], edges[-1], 200)
        pdf = np.exp(-0.5 * ((x - mean) / std) ** 2) / (std * np.sqrt(2 * np.pi))
        fig.add_trace(go.Scatter(
            x=x, y=pdf * width,  # scale density to match bar heights
            mode="lines", line=dict(color=active_colors["text"], width=1.5, dash="dot"),
            hoverinfo="skip",
        ))

    fig.add_vline(x=0, line_color=theme.NEUTRAL, line_width=1, line_dash="dash")
    fig.add_vline(x=mean, line_color=theme.ACCENT, line_width=2)

    fig.update_layout(
        title=dict(
            text=(f"{symbol}<br><sup>mean {mean:.2%} · vol {std:.2%} · "
                  f"skew {r.skew():.2f} · excess kurt {r.kurtosis():.2f}</sup>"),
            font=dict(color=color),
        ),
        showlegend=False,
        hovermode="closest",
        bargap=0.02,
        xaxis=dict(tickformat=".1%", title=f"{periodicity} return"),
        yaxis=dict(tickformat=".0%", title="Share of periods"),
    )
    theme.show_chart(fig, height=340)

