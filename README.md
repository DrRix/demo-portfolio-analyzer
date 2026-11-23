# Demo Portfolio Analyzer

A small, modular Streamlit demo for exploring financial data.
**Educational use only - not investment advice.**

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

On Windows you can also just double-click `run_app.bat`.

## Structure

```
app.py                  # Entry point: page config + horizontal tabs
core/
  session.py            # All st.session_state keys/helpers (tickers, prices)
  theme.py              # Colour palette + Plotly template (shared by all tabs)
tabs/
  welcome/view.py       # Intro + disclaimer
  ticker_search/
    view.py             # Search UI + selection management
    search.py           # yfinance search (cached, no UI)
  performance/
    view.py             # Lookback + price loading, periodicity, sub-tabs
    data.py             # yfinance price download (cached, no UI)
    calcs.py            # Pure return/statistics calculations
    returns_view.py     # Sub-tab: Performance (combined / separate charts)
    distribution_view.py# Sub-tab: Return Distribution (histograms)
  optimize/
    view.py             # Sub-tabs: Two-Asset & Multi-Asset Optimizer
    two_asset_view.py   # Two-Asset efficient frontier
    multi_asset_view.py # Multi-Asset Monte Carlo simulator
    calcs.py            # Mean/covariance & simulation calculations
  attribution/
    view.py             # Portfolio weights/sectors editor, charts, tables, export
    data.py             # GICS sectors, S&P 500 & ETF sector weightings
    calcs.py            # Brinson-Fachler attribution, volatility & returns
    export.py           # Multi-sheet Excel reconciliation workbook
```

### Design language

Colours live in `core/theme.py` (charts) and `.streamlit/config.toml` (UI).
Render Plotly figures with `theme.show_chart(fig)` and colour tickers with
`theme.ticker_colors(symbols)` so every tab looks the same.

### Adding a tab

1. Create `tabs/<name>/view.py` with a `render()` function and an `__init__.py`
   that re-exports it.
2. Import it in `app.py` and add a `(label, render)` entry to `TABS`.

