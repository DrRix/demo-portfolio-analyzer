"""Shared design language: colour palette and Plotly chart styling.

Every tab should take colours and chart styling from here so the app looks
consistent. The Streamlit UI colours themselves live in
``.streamlit/config.toml`` and use the same hex values.
"""

from __future__ import annotations

import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

# --- Core palette (matches .streamlit/config.toml) --------------------------
ACCENT = "#42a5f5"      # primary / highlight (blue)
POSITIVE = "#26a69a"    # gains (teal-green)
NEGATIVE = "#ef5350"    # losses (red)
NEUTRAL = "#9e9e9e"     # reference lines, muted text
BACKGROUND = "#0e1117"
SURFACE = "#1a1d24"
TEXT = "#e6e6e6"
GRID = "rgba(255, 255, 255, 0.08)"

LIGHT_BACKGROUND = "#ffffff"
LIGHT_TEXT = "#1f2937"
LIGHT_GRID = "rgba(0, 0, 0, 0.08)"

# One colour per ticker (15 = core.session.MAX_TICKERS). Pure red/green are
# left out so they keep meaning "loss"/"gain".
SERIES = [
    "#42a5f5", "#ffa726", "#ab47bc", "#26c6da", "#ffee58",
    "#ec407a", "#9ccc65", "#7e57c2", "#ff7043", "#8d6e63",
    "#5c6bc0", "#d4e157", "#78909c", "#f06292", "#4db6ac",
]

TEMPLATE_DARK = "demo_dark"
TEMPLATE_LIGHT = "demo_light"
TEMPLATE_NAME = TEMPLATE_DARK


def _build_template(base_name: str, text_color: str, grid_color: str) -> go.layout.Template:
    template = go.layout.Template(pio.templates[base_name])
    template.layout.update(
        paper_bgcolor="rgba(0,0,0,0)",  # blend with the Streamlit background
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color=text_color, size=13),
        colorway=SERIES,
        hovermode="x unified",
        margin=dict(l=10, r=10, t=75, b=10),
        title=dict(y=0.97, yanchor="top"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, title_text=""),
        xaxis=dict(gridcolor=grid_color, zeroline=False),
        yaxis=dict(gridcolor=grid_color, zerolinecolor=NEUTRAL),
    )
    return template


def _register_templates() -> None:
    pio.templates[TEMPLATE_DARK] = _build_template("plotly_dark", TEXT, GRID)
    pio.templates[TEMPLATE_LIGHT] = _build_template("plotly_white", LIGHT_TEXT, LIGHT_GRID)


_register_templates()


def is_light_mode() -> bool:
    """Return True when the active Streamlit theme is light."""
    try:
        return st.context.theme.type == "light"
    except Exception:
        return False


def active_colors() -> dict[str, str]:
    """Return theme-aware text, background, and grid colours."""
    if is_light_mode():
        return {"text": LIGHT_TEXT, "background": LIGHT_BACKGROUND, "grid": LIGHT_GRID}
    return {"text": TEXT, "background": BACKGROUND, "grid": GRID}


def ticker_colors(symbols: list[str]) -> dict[str, str]:
    """Stable symbol -> colour mapping (based on selection order)."""
    return {s: SERIES[i % len(SERIES)] for i, s in enumerate(symbols)}


def show_chart(fig: go.Figure, height: int | None = None, key: str | None = None) -> None:
    """Render a Plotly figure with the theme-matched template."""
    template_name = TEMPLATE_LIGHT if is_light_mode() else TEMPLATE_DARK
    fig.update_layout(template=template_name)
    if height:
        fig.update_layout(height=height)
    st.plotly_chart(
        fig,
        width="stretch",
        theme=None,  # keep our template instead of Streamlit's override
        config={"displaylogo": False},
        key=key,
    )

