"""Welcome tab: intro and disclaimer."""

import streamlit as st


def render() -> None:
    st.header("Welcome 👋")
    st.markdown(
        """
        This is a small **demo app** for exploring financial market data.

        **How to use it**
        1. **🔎 Ticker Search** - find stocks, ETFs or other instruments and add them to your selection.
        2. **📈 Performance** - load price history and compare prices, returns and return distributions.
        3. **⚖️ Optimize** - calculate Two-Asset and Multi-Asset (Monte Carlo) efficient frontiers and optimal weights.
        4. **:material/waterfall_chart: Attribution** - run Brinson-Fachler sector attribution against the S&P 500 with custom or preselected tickers.

        Your selection is kept only for this browser session and is not stored anywhere.
        """
    )

    st.warning(
        """
        **Disclaimer**

        This application is provided for **educational and demonstration purposes only**.
        Nothing shown here constitutes financial, investment, tax or legal advice, or a
        recommendation to buy or sell any security. Market data comes from third-party
        sources, may be delayed, incomplete or inaccurate, and is provided "as is" without
        warranty of any kind.

        **Do not use this app to make investment decisions.** Consult a qualified financial
        professional before making any investment.
        """,
        icon="⚠️",
    )

