"""Data access for ticker search (no UI code here)."""

from __future__ import annotations

import streamlit as st
import yfinance as yf

MAX_RESULTS = 15
ALLOWED_TYPES = {"equity", "etf"}


def _is_equity_or_etf(q: dict) -> bool:
    qt = str(q.get("quoteType") or "").strip().lower()
    td = str(q.get("typeDisp") or "").strip().lower()
    return qt in ALLOWED_TYPES or td in ALLOWED_TYPES


def _format_type(q: dict) -> str:
    qt = str(q.get("quoteType") or "").strip().lower()
    td = str(q.get("typeDisp") or "").strip().lower()
    return "ETF" if ("etf" in qt or "etf" in td) else "Equity"


def _search_single(query: str, max_results: int = MAX_RESULTS) -> list[dict]:
    query = query.strip()
    if not query:
        return []

    # Fetch more from yfinance to ensure enough Equity/ETF items after filtering
    quotes = yf.Search(query, max_results=max(max_results * 2, 20), news_count=0).quotes

    results = []
    for q in quotes:
        symbol = q.get("symbol")
        if not symbol or not _is_equity_or_etf(q):
            continue
        results.append(
            {
                "symbol": symbol,
                "name": q.get("longname") or q.get("shortname") or "",
                "exchange": q.get("exchDisp") or q.get("exchange") or "",
                "type": _format_type(q),
            }
        )
        if len(results) >= max_results:
            break
    return results


@st.cache_data(ttl=3600, show_spinner=False)
def search_tickers(query: str, max_results: int = MAX_RESULTS) -> list[dict]:
    """Search Yahoo Finance for Equity and ETF instruments matching ``query``.

    Supports comma-separated queries (e.g. "AAPL, MSFT, SPY").
    Returns a list of dicts with keys: symbol, name, exchange, type.
    Raises on network / API errors so the caller can show a message.
    """
    query = query.strip()
    if not query:
        return []

    tokens = [t.strip() for t in query.split(",") if t.strip()]
    if not tokens:
        return []

    if len(tokens) == 1:
        return _search_single(tokens[0], max_results=max_results)

    # For multiple tokens, search each and aggregate unique symbols
    aggregated: list[dict] = []
    seen: set[str] = set()
    per_token_limit = max(3, max_results // len(tokens))

    for token in tokens:
        token_results = _search_single(token, max_results=per_token_limit)
        for item in token_results:
            if item["symbol"] not in seen:
                seen.add(item["symbol"])
                aggregated.append(item)

    return aggregated

