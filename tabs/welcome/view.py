"""Welcome tab: intro and disclaimer."""

import streamlit as st


def render() -> None:
    st.header("Welcome 👋")
    st.markdown(
        """
        This is a small **demo app** for exploring stocks, put them in a portfolio and play around with the data.
        I really hope you enjoy it!

        **How to use it**
        1. **🔎 Ticker Search** - Find stocks and ETFs and add them to your selection.
        2. **📈 Performance** - Load price history and compare prices, returns and return distributions.
        3. **⚖️ Optimize** - Calculate Two-Asset and Multi-Asset (Monte Carlo) efficient frontiers. You can use any 2 asset combination like SPY and TLT, or choose from your preselected tickers.
        4. **:material/waterfall_chart: Attribution** - Run an attribution analysis against the S&P 500. You can use the 11 sectors or your preselected tickers.

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

        This application was built combining knowledge acquired through time, the use of LLMs and agentic coding tools""",
        
        icon="⚠️",
    )

