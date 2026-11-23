"""Sector metadata and S&P 500 benchmark weights for Attribution (no UI code here)."""

from __future__ import annotations

import streamlit as st
import yfinance as yf

# 11 GICS sectors -> Select Sector SPDR ETF proxy + baseline S&P 500 weight fallback.
GICS_SECTORS: dict[str, dict[str, object]] = {
    "Information Technology": {"etf": "XLK", "default_weight": 0.315},
    "Financials": {"etf": "XLF", "default_weight": 0.135},
    "Health Care": {"etf": "XLV", "default_weight": 0.110},
    "Consumer Discretionary": {"etf": "XLY", "default_weight": 0.105},
    "Communication Services": {"etf": "XLC", "default_weight": 0.090},
    "Industrials": {"etf": "XLI", "default_weight": 0.085},
    "Consumer Staples": {"etf": "XLP", "default_weight": 0.060},
    "Energy": {"etf": "XLE", "default_weight": 0.035},
    "Utilities": {"etf": "XLU", "default_weight": 0.025},
    "Real Estate": {"etf": "XLRE", "default_weight": 0.020},
    "Materials": {"etf": "XLB", "default_weight": 0.020},
}

SECTOR_NAMES: list[str] = list(GICS_SECTORS.keys())
SECTOR_ETFS: dict[str, str] = {sec: str(meta["etf"]) for sec, meta in GICS_SECTORS.items()}
ETF_TO_SECTOR: dict[str, str] = {etf: sec for sec, etf in SECTOR_ETFS.items()}
SECTOR_ETF_NAMES: dict[str, str] = {
    "XLK": "Technology Select Sector SPDR Fund",
    "XLF": "Financial Select Sector SPDR Fund",
    "XLV": "Health Care Select Sector SPDR Fund",
    "XLY": "Consumer Discretionary Select Sector SPDR Fund",
    "XLC": "Communication Services Select Sector SPDR Fund",
    "XLI": "Industrial Select Sector SPDR Fund",
    "XLP": "Consumer Staples Select Sector SPDR Fund",
    "XLE": "Energy Select Sector SPDR Fund",
    "XLU": "Utilities Select Sector SPDR Fund",
    "XLRE": "Real Estate Select Sector SPDR Fund",
    "XLB": "Materials Select Sector SPDR Fund",
}
DEFAULT_SECTOR = "Information Technology"
MULTI_SECTOR_LABEL = "Multi-Sector ETF (Look-through)"
SECTOR_OPTIONS: list[str] = [*SECTOR_NAMES, MULTI_SECTOR_LABEL]
SP500_TRACKERS: set[str] = {"SPY", "IVV", "VOO", "SPLG", "^GSPC"}

# Normalize Yahoo Finance equity info["sector"] strings and SPY funds_data keys
# (case-insensitive) to canonical GICS sector names.
YF_SECTOR_MAP: dict[str, str] = {
    "information technology": "Information Technology",
    "technology": "Information Technology",
    "financials": "Financials",
    "financial services": "Financials",
    "financial_services": "Financials",
    "health care": "Health Care",
    "healthcare": "Health Care",
    "consumer discretionary": "Consumer Discretionary",
    "consumer cyclical": "Consumer Discretionary",
    "consumer_cyclical": "Consumer Discretionary",
    "communication services": "Communication Services",
    "communication_services": "Communication Services",
    "industrials": "Industrials",
    "consumer staples": "Consumer Staples",
    "consumer defensive": "Consumer Staples",
    "consumer_defensive": "Consumer Staples",
    "energy": "Energy",
    "utilities": "Utilities",
    "real estate": "Real Estate",
    "real_estate": "Real Estate",
    "realestate": "Real Estate",
    "real-estate": "Real Estate",
    "materials": "Materials",
    "basic materials": "Materials",
    "basic_materials": "Materials",
}


def normalize_sector_name(raw_sector: str | None) -> str | None:
    """Map a raw Yahoo Finance or GICS sector label to a canonical GICS sector."""
    if not raw_sector or not isinstance(raw_sector, str):
        return None
    key = raw_sector.strip().lower()
    return YF_SECTOR_MAP.get(key)


def default_sp500_sector_weights() -> dict[str, float]:
    """Normalized baseline S&P 500 GICS sector weights (sum to 1.0)."""
    raw = {sec: float(meta["default_weight"]) for sec, meta in GICS_SECTORS.items()}
    total = sum(raw.values())
    return {sec: w / total for sec, w in raw.items()}


def _parse_sector_weightings(
    raw_weights: object,
    min_sectors: int = 1,
    min_total: float = 0.0,
) -> dict[str, float] | None:
    """Normalize Yahoo Finance ``funds_data.sector_weightings`` to GICS sectors."""
    if not raw_weights:
        return None

    # yfinance may return a dict or a list of 1-entry dicts depending on version.
    if isinstance(raw_weights, dict):
        items = list(raw_weights.items())
    elif isinstance(raw_weights, list):
        items = []
        for entry in raw_weights:
            if isinstance(entry, dict):
                items.extend(entry.items())
    else:
        return None

    flat: dict[str, float] = {}
    for key, val in items:
        sec = normalize_sector_name(str(key))
        try:
            weight = float(val)
        except (TypeError, ValueError):
            continue
        if sec and weight > 0:
            flat[sec] = flat.get(sec, 0.0) + weight

    total = sum(flat.values())
    if len(flat) < min_sectors or total <= min_total:
        return None

    return {sec: flat.get(sec, 0.0) / total for sec in SECTOR_NAMES}


@st.cache_data(ttl=3600, show_spinner=False, max_entries=100)
def _fetch_etf_sector_weights_cached(clean: str) -> dict[str, float]:
    """Fetch normalized GICS sector weights for a multi-sector ETF (raises on failure)."""
    raw_weights = yf.Ticker(clean).funds_data.sector_weightings
    parsed = _parse_sector_weightings(raw_weights, min_sectors=1, min_total=0.1)
    if parsed is None:
        raise ValueError(f"No sector weightings available for {clean}.")
    return parsed


def fetch_etf_sector_weights(symbol: str) -> dict[str, float] | None:
    """Fetch normalized GICS sector weights for a multi-sector ETF."""
    clean = symbol.strip().upper()
    if not clean:
        return None
    if clean in SP500_TRACKERS:
        return fetch_sp500_sector_weights()

    try:
        return _fetch_etf_sector_weights_cached(clean)
    except Exception:
        return None


@st.cache_data(ttl=3600, show_spinner=False, max_entries=200)
def _fetch_single_ticker_sector_cached(clean: str) -> str:
    """Resolve one ticker via Yahoo Finance (raises LookupError on miss/error so failures are not cached)."""
    try:
        info = yf.Ticker(clean).info or {}
        mapped = normalize_sector_name(info.get("sector"))
        qt = str(info.get("quoteType") or "").strip().lower()
        is_etf = qt == "etf"
    except Exception as exc:
        raise LookupError(f"Unable to resolve sector for {clean}.") from exc

    if mapped in GICS_SECTORS:
        return mapped
    if is_etf or fetch_etf_sector_weights(clean) is not None:
        return MULTI_SECTOR_LABEL
    raise LookupError(f"No GICS sector found for {clean}.")


def fetch_ticker_sectors(symbols: tuple[str, ...]) -> tuple[dict[str, str], list[str]]:
    """Resolve each ticker symbol to a canonical GICS sector or look-through ETF label.

    Checks single-sector SPDR ETFs and S&P 500 trackers first, then queries
    Yahoo Finance ``Ticker(sym).info``. Broad ETFs without a single equity sector
    are mapped to ``MULTI_SECTOR_LABEL``. Returns ``(resolved, unresolved)``;
    unresolved symbols fall back to ``DEFAULT_SECTOR`` without caching the failure.
    """
    resolved: dict[str, str] = {}
    unresolved: list[str] = []
    for sym in symbols:
        clean = sym.strip().upper()
        if not clean:
            continue
        if clean in ETF_TO_SECTOR:
            resolved[sym] = ETF_TO_SECTOR[clean]
            continue
        if clean in SP500_TRACKERS:
            resolved[sym] = MULTI_SECTOR_LABEL
            continue

        try:
            resolved[sym] = _fetch_single_ticker_sector_cached(clean)
        except Exception:
            resolved[sym] = DEFAULT_SECTOR
            unresolved.append(sym)
    return resolved, unresolved


@st.cache_data(ttl=3600, show_spinner=False)
def _fetch_sp500_sector_weights_cached() -> dict[str, float]:
    """Fetch S&P 500 sector weights via SPY holdings metadata (raises on incomplete data)."""
    raw_weights = yf.Ticker("SPY").funds_data.sector_weightings
    parsed = _parse_sector_weightings(raw_weights, min_sectors=11, min_total=0.5)
    if parsed is None:
        raise ValueError("Incomplete S&P 500 sector weightings.")
    return parsed


def fetch_sp500_sector_weights() -> dict[str, float]:
    """Fetch S&P 500 sector weights via SPY holdings metadata, with baseline fallback."""
    try:
        return _fetch_sp500_sector_weights_cached()
    except Exception:
        return default_sp500_sector_weights()
