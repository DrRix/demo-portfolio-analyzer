"""Optimize tab: Two-Asset and Multi-Asset (Monte Carlo) optimizers."""

import streamlit as st

from . import multi_asset_view, two_asset_view


def render() -> None:
    st.header("⏳ Portfolio Optimizer")

    tab_two, tab_multi = st.tabs(
        ["Two-Asset Optimizer", "Multi-Asset Optimizer (Monte Carlo)"]
    )
    with tab_two:
        two_asset_view.render()
    with tab_multi:
        multi_asset_view.render()

