"""Demo Portfolio Analyzer - Streamlit entry point.

Run with:
    streamlit run app.py

This script only assembles the UI: page config, header and the horizontal
tabs. Each tab lives in its own package under ``tabs/`` and exposes a single
``render()`` function.
"""

import streamlit as st

from core import session
from tabs.attribution import render as render_attribution
from tabs.optimize import render as render_optimize
from tabs.performance import render as render_performance
from tabs.ticker_search import render as render_ticker_search
from tabs.welcome import render as render_welcome

APP_TITLE = "Demo Portfolio Analyzer"

# (label, render function) - add / reorder tabs here.
TABS = [
    ("🏠 Welcome", render_welcome),
    ("🔎 Ticker Search", render_ticker_search),
    ("📈 Performance", render_performance),
    ("⚖️ Optimize", render_optimize),
    (":material/waterfall_chart: Attribution", render_attribution),
]


def main() -> None:
    st.set_page_config(page_title=APP_TITLE, page_icon="📊", layout="wide")
    session.init_state()

    st.title(f"📊 {APP_TITLE}")
    st.caption("Educational demo only - not investment advice.")

    tab_containers = st.tabs([label for label, _ in TABS])
    for container, (_, render_fn) in zip(tab_containers, TABS):
        with container:
            render_fn()


if __name__ == "__main__":
    main()

