"""Attribution tab: Brinson-Fachler sector attribution against the S&P 500."""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core import session, theme
from tabs.performance.data import fetch_close_prices

from .calcs import (
    brinson_fachler_attribution,
    period_total_returns,
    portfolio_beta,
    portfolio_cumulative_returns,
    portfolio_volatility,
    validate_weights,
)
from .data import (
    DEFAULT_SECTOR,
    ETF_TO_SECTOR,
    MULTI_SECTOR_LABEL,
    SECTOR_ETF_NAMES,
    SECTOR_ETFS,
    SECTOR_OPTIONS,
    SP500_TRACKERS,
    fetch_etf_sector_weights,
    fetch_sp500_sector_weights,
    fetch_ticker_sectors,
)

SOURCE_SECTOR_ETFS = "11 Sector ETFs"
SOURCE_PRESELECTED = "Preselected (Ticker Search)"

LOOKBACKS: dict[str, int | None] = {
    "1M": 30,
    "3M": 91,
    "6M": 182,
    "YTD": None,
    "1Y": 365,
    "2Y": 365 * 2,
    "3Y": 365 * 3,
}
DEFAULT_LOOKBACK = "YTD"


def render() -> None:
    st.header(":material/waterfall_chart: Brinson-Fachler Attribution vs. S&P 500")
    st.caption(
        "Decompose active portfolio return against the S&P 500 across the 11 GICS "
        "sectors into **Allocation**, **Selection**, and **Interaction** effects."
    )

    source, symbols = _render_ticker_source()
    if not symbols:
        return

    edited_df, weights_valid = _render_portfolio_editor(source, symbols)
    st.divider()
    lookback, date_range = _render_period_and_run(source, edited_df, weights_valid)
    _render_results(source, edited_df, lookback, date_range)


# --- Step 1: Ticker source & row-by-row weight editor -----------------------


def _render_ticker_source() -> tuple[str, list[str]]:
    source = (
        st.segmented_control(
            "Portfolio source",
            options=[SOURCE_SECTOR_ETFS, SOURCE_PRESELECTED],
            default=SOURCE_SECTOR_ETFS,
            key="attr_source_control",
        )
        or SOURCE_SECTOR_ETFS
    )

    if source == SOURCE_SECTOR_ETFS:
        return source, list(SECTOR_ETFS.values())

    selected = session.get_selected_symbols()
    if not selected:
        st.info(
            "No tickers selected yet. Add specific stocks or ETFs in the "
            "**🔎 Ticker Search** tab, or switch to **11 Sector ETFs** above."
        )
        return source, []
    return source, selected


def _equal_weights(n: int) -> list[float]:
    if n <= 0:
        return []
    base = round(100.0 / n, 2)
    weights = [base] * n
    weights[-1] = round(100.0 - sum(weights[:-1]), 2)
    return weights


def _normalize_weights(raw_weights: list[float]) -> list[float]:
    clipped = [max(0.0, float(w)) if pd.notna(w) else 0.0 for w in raw_weights]
    total = sum(clipped)
    if total <= 0:
        return _equal_weights(len(clipped))
    scaled = [round((w / total) * 100.0, 2) for w in clipped]
    idx_max = max(range(len(scaled)), key=lambda i: scaled[i])
    scaled[idx_max] = round(scaled[idx_max] + (100.0 - sum(scaled)), 2)
    return scaled


def _sp500_matched_weights(symbols: list[str], sectors: list[str]) -> list[float]:
    """Map S&P 500 current sector weights onto the active symbols, normalized to 100%."""
    bench_weights = fetch_sp500_sector_weights()
    sector_counts: dict[str, int] = {}
    for sec in sectors:
        sector_counts[sec] = sector_counts.get(sec, 0) + 1

    raw: list[float] = []
    for sec in sectors:
        if sec == MULTI_SECTOR_LABEL:
            raw.append(1.0 / sector_counts[sec])
        else:
            raw.append(bench_weights.get(sec, 0.0) / sector_counts[sec])
    return _normalize_weights(raw)


def _resolve_ticker_names(symbols: list[str]) -> list[str]:
    selected_names = {
        t["symbol"].strip().upper(): t.get("name", "")
        for t in session.get_selected_tickers()
    }
    names: list[str] = []
    for sym in symbols:
        clean = sym.strip().upper()
        name = SECTOR_ETF_NAMES.get(clean) or selected_names.get(clean) or clean
        names.append(name)
    return names


def _source_tag(source: str) -> str:
    return "etfs" if source == SOURCE_SECTOR_ETFS else "presel"


def _widget_keys(source: str, sym: str) -> tuple[str, str, str]:
    tag = _source_tag(source)
    return (
        f"attr_w_slider_{tag}_{sym}",
        f"attr_w_num_{tag}_{sym}",
        f"attr_sec_{tag}_{sym}",
    )


def _sync_from_slider(source: str, sym: str, slider_key: str, num_key: str) -> None:
    val = round(float(st.session_state[slider_key]), 2)
    st.session_state[num_key] = val
    st.session_state.setdefault("attr_weights_map", {}).setdefault(source, {})[sym] = val


def _sync_from_num(source: str, sym: str, slider_key: str, num_key: str) -> None:
    val = round(float(st.session_state[num_key]), 2)
    st.session_state[slider_key] = val
    st.session_state.setdefault("attr_weights_map", {}).setdefault(source, {})[sym] = val


def _apply_preset_weights(source: str, symbols: list[str], new_weights: list[float]) -> None:
    weights_map = st.session_state.setdefault("attr_weights_map", {}).setdefault(source, {})
    for sym, w in zip(symbols, new_weights):
        val = round(float(w), 2)
        s_key, n_key, _ = _widget_keys(source, sym)
        st.session_state[s_key] = val
        st.session_state[n_key] = val
        weights_map[sym] = val


def _apply_sp500_preset(source: str, symbols: list[str]) -> None:
    sectors_map = st.session_state.get("attr_sectors_map", {}).get(source, {})
    current_sectors = [
        ETF_TO_SECTOR[sym]
        if source == SOURCE_SECTOR_ETFS
        else str(
            st.session_state.get(
                _widget_keys(source, sym)[2], sectors_map.get(sym, DEFAULT_SECTOR)
            )
        )
        for sym in symbols
    ]
    matched = _sp500_matched_weights(symbols, current_sectors)
    _apply_preset_weights(source, symbols, matched)


def _apply_normalize_preset(source: str, symbols: list[str]) -> None:
    weights_map = st.session_state.get("attr_weights_map", {}).get(source, {})
    current_weights = [
        float(st.session_state.get(_widget_keys(source, sym)[1], weights_map.get(sym, 0.0)))
        for sym in symbols
    ]
    _apply_preset_weights(source, symbols, _normalize_weights(current_weights))


def _apply_optimizer_preset(source: str, symbols: list[str]) -> None:
    opt_weights = session.get_optimizer_weights() or {}
    raw = [float(opt_weights.get(sym.strip().upper(), 0.0)) for sym in symbols]
    if sum(w for w in raw if w > 0) <= 0:
        return
    _apply_preset_weights(source, symbols, _normalize_weights(raw))


def _clear_unresolved(source: str, sym: str) -> None:
    st.session_state.setdefault("attr_unresolved_sectors", {}).setdefault(source, set()).discard(
        sym
    )


def _init_row_state(
    source: str, symbols: list[str]
) -> tuple[dict[str, str], dict[str, float], list[str]]:
    sectors_map = st.session_state.setdefault("attr_sectors_map", {}).setdefault(source, {})
    weights_map = st.session_state.setdefault("attr_weights_map", {}).setdefault(source, {})
    unresolved_set: set[str] = st.session_state.setdefault(
        "attr_unresolved_sectors", {}
    ).setdefault(source, set())

    if source == SOURCE_SECTOR_ETFS:
        for sym in symbols:
            sectors_map[sym] = ETF_TO_SECTOR[sym]
        unresolved_set.clear()
    else:
        unknown = tuple(
            s for s in symbols if s not in sectors_map or sectors_map[s] not in SECTOR_OPTIONS
        )
        if unknown:
            with st.spinner("Resolving GICS sectors..."):
                resolved, unresolved = fetch_ticker_sectors(unknown)
                sectors_map.update(resolved)
                unresolved_set.update(unresolved)
        unresolved_set.intersection_update(symbols)

    known_weights = [weights_map[s] for s in symbols if s in weights_map]
    if not known_weights:
        defaults = _equal_weights(len(symbols))
        for sym, w in zip(symbols, defaults):
            weights_map[sym] = w
    else:
        for sym in symbols:
            weights_map.setdefault(sym, 0.0)

    for sym in symbols:
        s_key, n_key, sec_key = _widget_keys(source, sym)
        w = round(float(weights_map.get(sym, 0.0)), 2)
        st.session_state.setdefault(s_key, w)
        st.session_state.setdefault(n_key, w)
        if st.session_state.get(sec_key) not in SECTOR_OPTIONS:
            st.session_state[sec_key] = sectors_map.get(sym, DEFAULT_SECTOR)

    active_unresolved = [s for s in symbols if s in unresolved_set]
    return sectors_map, weights_map, active_unresolved


def _render_portfolio_editor(source: str, symbols: list[str]) -> tuple[pd.DataFrame, bool]:
    st.subheader("1. Portfolio Weights & GICS Sectors")
    st.caption(
        "Adjust each weight between **0%** and **100%** using the slider or numeric input. "
        "Portfolio weights must sum to **100.00%**."
    )

    sectors_map, weights_map, active_unresolved = _init_row_state(source, symbols)
    names = _resolve_ticker_names(symbols)

    if active_unresolved:
        st.warning(
            f"Could not detect GICS sector for: **{', '.join(active_unresolved)}** "
            f"(defaulted to `{DEFAULT_SECTOR}`). Please adjust in the selector below if needed."
        )

    current_weights = [
        round(float(st.session_state.get(_widget_keys(source, sym)[1], weights_map.get(sym, 0.0))), 2)
        for sym in symbols
    ]
    positive_sum = sum(w for w in current_weights if w > 0)

    # Preset buttons bar
    if source == SOURCE_PRESELECTED:
        opt_weights = session.get_optimizer_weights() or {}
        has_opt_weights = any(
            float(opt_weights.get(sym.strip().upper(), 0.0)) > 0 for sym in symbols
        )
        col_eq, col_sp, col_opt, col_norm, col_clr = st.columns(5)
    else:
        has_opt_weights = False
        col_eq, col_sp, col_norm, col_clr = st.columns(4)

    col_eq.button(
        "Equal Weight",
        width="stretch",
        help="Split 100% evenly across all rows.",
        on_click=_apply_preset_weights,
        args=(source, symbols, _equal_weights(len(symbols))),
    )
    col_sp.button(
        "Match S&P 500 Current Sector Weights",
        width="stretch",
        help=(
            "Fetches live S&P 500 GICS sector weights from Yahoo Finance (SPY holdings "
            "sector weightings, cached 1 hour; falls back to baseline GICS weights if unavailable). "
            "Splits each sector's weight evenly across your tickers in that sector and normalizes to 100%."
        ),
        on_click=_apply_sp500_preset,
        args=(source, symbols),
    )
    if source == SOURCE_PRESELECTED:
        col_opt.button(
            "Match Optimizer",
            width="stretch",
            disabled=not has_opt_weights,
            help=(
                "Loads the Max Sharpe optimal portfolio weights from the Multi-Asset Optimizer "
                "(normalized to 100% across matching tickers). Run the Multi-Asset Optimizer first if disabled."
            ),
            on_click=_apply_optimizer_preset,
            args=(source, symbols),
        )
    col_norm.button(
        "Normalize to 100%",
        width="stretch",
        disabled=positive_sum <= 0,
        help="Rescale positive weights proportionally to sum to 100.00%.",
        on_click=_apply_normalize_preset,
        args=(source, symbols),
    )
    col_clr.button(
        "Clear (0%)",
        width="stretch",
        help="Reset all weights to 0.00%.",
        on_click=_apply_preset_weights,
        args=(source, symbols, [0.0] * len(symbols)),
    )

    # Row-by-row controls inside a bordered container
    rows: list[dict[str, object]] = []
    with st.container(border=True):
        h_tk, h_sec, h_sl, h_num = st.columns([2.2, 2.0, 2.6, 1.2])
        h_tk.markdown("**Ticker**")
        h_sec.markdown("**GICS Sector**")
        h_sl.markdown("**Weight Slider**")
        h_num.markdown("**Weight (%)**")

        for sym, name in zip(symbols, names):
            s_key, n_key, sec_key = _widget_keys(source, sym)
            c_tk, c_sec, c_sl, c_num = st.columns(
                [2.2, 2.0, 2.6, 1.2], vertical_alignment="center"
            )
            c_tk.markdown(f"**{sym}**  \n:gray[{name}]")

            if source == SOURCE_SECTOR_ETFS:
                sec_val = ETF_TO_SECTOR[sym]
                c_sec.markdown(f"`{sec_val}`")
            else:
                sec_val = c_sec.selectbox(
                    f"Sector for {sym}",
                    options=SECTOR_OPTIONS,
                    key=sec_key,
                    label_visibility="collapsed",
                    on_change=_clear_unresolved,
                    args=(source, sym),
                )
                sectors_map[sym] = sec_val

            c_sl.slider(
                f"Weight slider for {sym}",
                min_value=0.0,
                max_value=100.0,
                step=0.01,
                key=s_key,
                label_visibility="collapsed",
                on_change=_sync_from_slider,
                args=(source, sym, s_key, n_key),
            )
            w_val = c_num.number_input(
                f"Weight % for {sym}",
                min_value=0.0,
                max_value=100.0,
                step=0.5,
                format="%.2f",
                key=n_key,
                label_visibility="collapsed",
                on_change=_sync_from_num,
                args=(source, sym, s_key, n_key),
            )
            weights_map[sym] = float(w_val)

            rows.append(
                {
                    "Name": name,
                    "Symbol": sym,
                    "GICS Sector": sec_val,
                    "Weight (%)": float(w_val),
                }
            )

    edited_df = pd.DataFrame(rows)
    weights_list = [float(r["Weight (%)"]) for r in rows]
    is_valid, status_msg, total_pct = validate_weights(weights_list)

    # Live allocation progress bar + validation status
    st.progress(
        min(max(total_pct / 100.0, 0.0), 1.0),
        text=f"Allocated: **{total_pct:.2f}%** / 100.00%",
    )
    if is_valid:
        st.success(status_msg, icon=":material/check_circle:")
    else:
        st.error(status_msg, icon=":material/error:")

    return edited_df, is_valid


# --- Step 2: Period selection & attribution execution ----------------------


def _resolve_date_range(lookback: str) -> tuple[date, date]:
    today = date.today()
    days = LOOKBACKS[lookback]
    start = date(today.year - 1, 12, 31) if days is None else today - timedelta(days=int(days))
    return start, today


def _render_period_and_run(
    source: str, edited_df: pd.DataFrame, weights_valid: bool
) -> tuple[str, tuple[date, date] | None]:
    st.subheader("2. Analysis Period")

    col_lb, col_run = st.columns([4, 1], vertical_alignment="bottom")
    lookback = (
        col_lb.segmented_control(
            "Lookback period",
            options=list(LOOKBACKS),
            default=DEFAULT_LOOKBACK,
            key="attr_lookback",
        )
        or DEFAULT_LOOKBACK
    )
    run_clicked = col_run.button(
        "Run Attribution",
        type="primary",
        icon=":material/analytics:",
        disabled=not weights_valid,
        width="stretch",
    )

    date_range = _resolve_date_range(lookback)
    if not run_clicked or date_range is None or not weights_valid:
        return lookback, date_range

    start, end = date_range
    port_symbols = [str(s) for s in edited_df["Symbol"].tolist()]
    etf_symbols = list(SECTOR_ETFS.values())
    all_symbols = tuple(dict.fromkeys(port_symbols + etf_symbols + ["SPY"]))

    fetch_start = start - timedelta(days=7) if lookback == "YTD" else start

    try:
        with st.spinner("Downloading portfolio and S&P 500 sector data..."):
            prices = fetch_close_prices(all_symbols, fetch_start, end)
            benchmark_weights = fetch_sp500_sector_weights()
    except Exception:
        st.error("Market data is unavailable right now. Please try again in a moment.")
        return lookback, date_range

    if lookback == "YTD" and not prices.empty:
        jan1 = pd.Timestamp(end.year, 1, 1)
        prior_year_dates = prices.index[prices.index < jan1]
        if len(prior_year_dates) > 0:
            prices = prices.loc[prior_year_dates[-1]:]

    if prices.empty:
        st.error("No price history returned for the selected date range.")
        return lookback, date_range

    missing_etfs = [etf for etf in [*etf_symbols, "SPY"] if etf not in prices.columns]
    if missing_etfs:
        st.error(
            "Missing S&P 500 benchmark data for: " + ", ".join(dict.fromkeys(missing_etfs))
        )
        return lookback, date_range

    weights_dec = pd.to_numeric(edited_df["Weight (%)"], errors="coerce").fillna(0.0) / 100.0
    active_symbols = [
        sym for sym, w in zip(port_symbols, weights_dec) if w > 0
    ]
    missing_port = [sym for sym in active_symbols if sym not in prices.columns]
    if missing_port:
        st.error("No price data found for: " + ", ".join(missing_port))
        return lookback, date_range

    required_cols = list(dict.fromkeys(active_symbols + etf_symbols + ["SPY"]))
    aligned_prices = prices[required_cols].ffill().dropna(how="any")
    if len(aligned_prices) < 2:
        st.warning(
            "Not enough overlapping trading days across all tickers and S&P 500 sector ETFs. "
            "Try a wider date range or remove newly listed tickers."
        )
        return lookback, date_range

    bench_aligned = prices[etf_symbols].ffill().dropna(how="any")
    full_window_start = (
        bench_aligned.index[0] if not bench_aligned.empty else aligned_prices.index[0]
    )
    full_window_days = (
        len(bench_aligned) if not bench_aligned.empty else len(aligned_prices)
    )
    truncated_tickers: list[tuple[str, str]] = []
    for sym in active_symbols:
        first_valid = prices[sym].first_valid_index()
        if first_valid is not None and first_valid > full_window_start:
            truncated_tickers.append((sym, pd.Timestamp(first_valid).strftime("%d %b %Y")))

    total_returns = period_total_returns(aligned_prices)
    if total_returns.isna().any():
        bad = total_returns[total_returns.isna()].index.tolist()
        st.error("Could not compute period returns for: " + ", ".join(bad))
        return lookback, date_range

    holdings_df = pd.DataFrame(
        {
            "symbol": port_symbols,
            "sector": [str(sec) for sec in edited_df["GICS Sector"].tolist()],
            "weight": weights_dec.to_numpy(dtype=float),
            "return": [
                float(total_returns[sym]) if sym in total_returns.index else float("nan")
                for sym in port_symbols
            ],
        }
    )

    benchmark_returns = pd.Series(
        {sec: float(total_returns[etf]) for sec, etf in SECTOR_ETFS.items()}
    )

    multi_symbols = [
        str(row["Symbol"]).strip().upper()
        for _, row in edited_df.iterrows()
        if str(row["GICS Sector"]) == MULTI_SECTOR_LABEL
    ]
    etf_sector_weights = {
        sym: fetch_etf_sector_weights(sym) or benchmark_weights
        for sym in dict.fromkeys(multi_symbols)
    }

    # Markowitz covariance-based portfolio & benchmark risk + constant-weight cumulative curves
    daily_returns = (
        aligned_prices.replace(0, np.nan)
        .pct_change()
        .replace([np.inf, -np.inf], np.nan)
        .dropna(how="any")
    )
    bench_asset_weights = {"SPY": 1.0}
    port_asset_weights: dict[str, float] = {}
    for _, row in holdings_df.iterrows():
        sym = str(row["symbol"])
        sec = str(row["sector"])
        w = float(row["weight"])
        if w <= 0:
            continue
        if sec == MULTI_SECTOR_LABEL and sym.strip().upper() in SP500_TRACKERS:
            for s_name, b_w in benchmark_weights.items():
                etf = SECTOR_ETFS[s_name]
                port_asset_weights[etf] = port_asset_weights.get(etf, 0.0) + w * float(b_w)
        else:
            port_asset_weights[sym] = port_asset_weights.get(sym, 0.0) + w

    portfolio_risk = portfolio_volatility(daily_returns, port_asset_weights)
    benchmark_risk = portfolio_volatility(daily_returns, bench_asset_weights)
    port_beta = portfolio_beta(daily_returns, port_asset_weights, daily_returns["SPY"])
    port_cum = portfolio_cumulative_returns(
        daily_returns, port_asset_weights, start_date=aligned_prices.index[0]
    )
    bench_cum = portfolio_cumulative_returns(
        daily_returns, bench_asset_weights, start_date=aligned_prices.index[0]
    )
    cum_port_return = float(port_cum.iloc[-1]) if not port_cum.empty else float("nan")
    cum_spy_return = float(bench_cum.iloc[-1]) if not bench_cum.empty else float("nan")
    cal_days = (aligned_prices.index[-1] - aligned_prices.index[0]).days
    if cal_days > 365:
        years = cal_days / 365.25
        ann_port_return = (
            (1.0 + cum_port_return) ** (1.0 / years) - 1.0
            if pd.notna(cum_port_return) and (1.0 + cum_port_return) > 0
            else float("nan")
        )
        ann_spy_return = (
            (1.0 + cum_spy_return) ** (1.0 / years) - 1.0
            if pd.notna(cum_spy_return) and (1.0 + cum_spy_return) > 0
            else float("nan")
        )
    else:
        ann_port_return = float("nan")
        ann_spy_return = float("nan")

    result = brinson_fachler_attribution(
        holdings_df,
        benchmark_weights,
        benchmark_returns,
        etf_sector_weights=etf_sector_weights,
        sp500_trackers=SP500_TRACKERS,
        multi_sector_label=MULTI_SECTOR_LABEL,
    )

    payload = {
        "data": result,
        "cum_port_return": cum_port_return,
        "cum_spy_return": cum_spy_return,
        "ann_port_return": ann_port_return,
        "ann_spy_return": ann_spy_return,
        "portfolio_risk": portfolio_risk,
        "benchmark_risk": benchmark_risk,
        "portfolio_beta": port_beta,
        "port_cum": port_cum,
        "bench_cum": bench_cum,
        "aligned_prices": aligned_prices,
        "daily_returns": daily_returns,
        "port_asset_weights": port_asset_weights,
        "bench_asset_weights": bench_asset_weights,
        "lookback": lookback,
        "effective_start": aligned_prices.index[0],
        "effective_end": aligned_prices.index[-1],
        "truncated_tickers": truncated_tickers,
        "eval_days": int(len(aligned_prices)),
        "full_window_days": int(full_window_days),
        "config_snapshot": _config_snapshot(source, edited_df, lookback, date_range),
    }
    st.session_state["attr_results"] = payload
    if truncated_tickers:
        names_str = ", ".join(sym for sym, _ in truncated_tickers)
        st.toast(
            f"Evaluation window shortened: {names_str} has fewer trading days than the selected {lookback} period.",
            icon=":material/warning:",
        )
    return lookback, date_range


def _config_snapshot(
    source: str,
    edited_df: pd.DataFrame,
    lookback: str,
    date_range: tuple[date, date] | None,
) -> tuple[object, ...]:
    weights = pd.to_numeric(edited_df["Weight (%)"], errors="coerce").fillna(-1.0)
    rows = tuple(
        (str(sym), str(sec), round(float(w), 4))
        for sym, sec, w in zip(edited_df["Symbol"], edited_df["GICS Sector"], weights)
    )
    return (source, lookback, date_range, rows)


# --- Step 3: Results display & charts --------------------------------------


def _fmt_pct(val: float, signed: bool = False) -> str:
    """Format percentage while preventing '-0.00%' display artifacts."""
    if pd.isna(val):
        return "—"
    if abs(val) < 1e-6:
        val = 0.0
    return f"{val:+.2%}" if signed else f"{val:.2%}"


def _fmt_num(val: float) -> str:
    """Format a decimal ratio (e.g. beta) to 2 decimal places."""
    if pd.isna(val):
        return "—"
    if abs(val) < 1e-6:
        val = 0.0
    return f"{val:.2f}"


def _render_results(
    source: str,
    edited_df: pd.DataFrame,
    lookback: str,
    date_range: tuple[date, date] | None,
) -> None:
    payload = st.session_state.get("attr_results")
    if not payload:
        return

    if payload["config_snapshot"] != _config_snapshot(source, edited_df, lookback, date_range):
        st.divider()
        st.warning(
            "Your portfolio source, tickers, sectors, weights, or period have changed since the last run. "
            "Press **Run Attribution** to refresh results."
        )
        return

    eff_start = payload["effective_start"]
    eff_end = payload["effective_end"]
    cum_port_return: float = payload.get("cum_port_return", float("nan"))
    cum_spy_return: float = payload.get("cum_spy_return", float("nan"))
    ann_port_return: float = payload.get("ann_port_return", float("nan"))
    ann_spy_return: float = payload.get("ann_spy_return", float("nan"))
    portfolio_risk: float = payload.get("portfolio_risk", float("nan"))
    benchmark_risk: float = payload.get("benchmark_risk", float("nan"))
    port_beta: float = payload.get("portfolio_beta", float("nan"))

    _render_period_kpis(
        cum_port_return,
        cum_spy_return,
        portfolio_risk,
        benchmark_risk,
        port_beta,
        ann_port_return,
        ann_spy_return,
    )

    st.divider()
    st.subheader("3. Brinson-Fachler Attribution Results")

    st.caption(
        f"Common evaluation window: **{eff_start:%d %b %Y} → {eff_end:%d %b %Y}** "
        f"({payload['lookback']} selection)."
    )

    truncated_tickers = payload.get("truncated_tickers") or []
    if truncated_tickers:
        details = ", ".join(f"**{sym}** (starts {dt})" for sym, dt in truncated_tickers)
        eval_days = payload.get("eval_days")
        full_days = payload.get("full_window_days")
        days_note = (
            f" ({eval_days} of {full_days} trading days)"
            if eval_days and full_days
            else ""
        )
        st.warning(
            f"Shorter history detected for {details}. "
            f"All attribution, risk, and beta metrics were computed over the common overlapping window{days_note}.",
            icon=":material/warning:",
        )

    result = payload["data"]
    summary = result["summary"]
    sector_df: pd.DataFrame = result["sector_df"]
    holdings_df: pd.DataFrame = result["holdings_df"]
    port_cum: pd.Series = payload.get("port_cum", pd.Series(dtype=float))
    bench_cum: pd.Series = payload.get("bench_cum", pd.Series(dtype=float))

    _render_attribution_kpis(summary)

    tab_breakdown, tab_cum, tab_weights, tab_tables = st.tabs(
        [
            "📊 Attribution Breakdown",
            "📈 Cumulative Performance",
            "⚖️ Weights & Contributions",
            "📋 Attribution Tables",
        ]
    )
    with tab_breakdown:
        _render_breakdown_charts(summary, sector_df)
    with tab_cum:
        _render_cumulative_chart(port_cum, bench_cum)
    with tab_weights:
        _render_weights_and_contributions_charts(sector_df)
    with tab_tables:
        _render_tables(sector_df, holdings_df, summary)

    st.markdown(
        "Brinson-Fachler attribution uses single period simple price returns "
        "(P₁ / P₀ − 1) of the active portfolio vs the same single period simple price returns of the benchmark and its components.  \n"
        "Period summary metrics under Section 2 use constant-weight compounded returns, "
        "SPY as the benchmark, annualized standard deviation, "
        "and Beta as covariance / variance."
    )


def _render_period_kpis(
    cum_port_return: float,
    cum_spy_return: float,
    portfolio_risk: float,
    benchmark_risk: float,
    port_beta: float,
    ann_port_return: float,
    ann_spy_return: float,
) -> None:
    p1, p2, p3, p4, p5 = st.columns(5)
    p1.metric(
        "Cumulative Portfolio Return",
        _fmt_pct(cum_port_return),
        help="Total compounded constant-weight return over the evaluation window; matches the Cumulative Performance chart.",
    )
    p2.metric(
        "Cumulative SPY Return",
        _fmt_pct(cum_spy_return),
        help="Total compounded return of SPY over the evaluation window; matches the Cumulative Performance chart.",
    )

    p3.metric(
        "Portfolio Volatility",
        _fmt_pct(portfolio_risk),
        help="Annualized standard deviation using daily return covariances.",
    )
    p4.metric(
        "S&P 500 Volatility",
        _fmt_pct(benchmark_risk),
        help="Annualized standard deviation of SPY daily returns.",
    )
    p5.metric(
        "Portfolio Beta (vs. SPY)",
        _fmt_num(port_beta),
        help="Sensitivity to SPY daily returns: covariance / variance using constant-weight daily portfolio returns.",
    )

    if pd.notna(ann_port_return) or pd.notna(ann_spy_return):
        a1, a2, _ = st.columns([1, 1, 3])
        a1.metric(
            "Annualized Portfolio Return (CAGR)",
            _fmt_pct(ann_port_return),
            help="Compound annual growth rate of the constant-weight portfolio over the >1Y evaluation window.",
        )
        a2.metric(
            "Annualized SPY Return (CAGR)",
            _fmt_pct(ann_spy_return),
            help="Compound annual growth rate of SPY over the >1Y evaluation window.",
        )


def _render_attribution_kpis(summary: dict[str, float]) -> None:
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric(
        "Portfolio Return (Simple)",
        _fmt_pct(summary["portfolio_return"]),
        help="Single-period buy-and-hold return: sum of w_p × (P₁ / P₀ − 1).",
    )
    c2.metric(
        "S&P 500 Proxy (Simple)",
        _fmt_pct(summary["benchmark_return"]),
        help="Single-period sector composite return: sum of w_b × (P₁ / P₀ − 1) across the 11 SPDR ETFs.",
    )
    c3.metric(
        "Active Return",
        _fmt_pct(summary["active_return"], signed=True),
        help="Simple period Portfolio Return minus S&P 500 Sector Proxy Return (= Allocation + Selection + Interaction).",
    )
    c4.metric("Allocation Effect", _fmt_pct(summary["allocation_effect"], signed=True))
    c5.metric("Selection Effect", _fmt_pct(summary["selection_effect"], signed=True))
    c6.metric("Interaction Effect", _fmt_pct(summary["interaction_effect"], signed=True))


def _apply_chart_spacing(fig: go.Figure, title: str, has_legend: bool = True) -> None:
    """Give titles and horizontal legends clear vertical separation."""
    fig.update_layout(
        title=dict(text=title, y=0.97, yanchor="top"),
        margin=dict(t=80 if has_legend else 60),
    )


def _render_breakdown_charts(summary: dict[str, float], sector_df: pd.DataFrame) -> None:
    col_wf, col_sec = st.columns([2, 3], gap="large")

    with col_wf:
        fig_wf = go.Figure(
            go.Waterfall(
                orientation="v",
                measure=["absolute", "relative", "relative", "relative", "total"],
                x=[
                    "S&P 500 (Sector Proxy)",
                    "Allocation",
                    "Selection",
                    "Interaction",
                    "Portfolio",
                ],
                y=[
                    summary["benchmark_return"],
                    summary["allocation_effect"],
                    summary["selection_effect"],
                    summary["interaction_effect"],
                    summary["portfolio_return"],
                ],
                text=[
                    _fmt_pct(summary["benchmark_return"]),
                    _fmt_pct(summary["allocation_effect"], signed=True),
                    _fmt_pct(summary["selection_effect"], signed=True),
                    _fmt_pct(summary["interaction_effect"], signed=True),
                    _fmt_pct(summary["portfolio_return"]),
                ],
                textposition="outside",
                increasing=dict(marker=dict(color=theme.POSITIVE)),
                decreasing=dict(marker=dict(color=theme.NEGATIVE)),
                totals=dict(marker=dict(color=theme.ACCENT)),
                connector=dict(line=dict(color=theme.NEUTRAL, width=1, dash="dot")),
                hovertemplate="%{x}: %{y:.2%}<extra></extra>",
            )
        )
        fig_wf.add_hline(y=0, line_dash="dash", line_color=theme.NEUTRAL, line_width=1)
        fig_wf.update_layout(
            yaxis=dict(title="Return", tickformat=".1%"),
            showlegend=False,
        )
        _apply_chart_spacing(fig_wf, "Active Return Decomposition", has_legend=False)
        theme.show_chart(fig_wf, height=440)

    with col_sec:
        sorted_df = sector_df.sort_values("Total Effect", ascending=False)
        fig_sec = go.Figure()
        effects = [
            ("Allocation Effect", theme.SERIES[0]),
            ("Selection Effect", theme.SERIES[1]),
            ("Interaction Effect", theme.SERIES[2]),
        ]
        for label, color in effects:
            fig_sec.add_trace(
                go.Bar(
                    x=sorted_df.index,
                    y=sorted_df[label],
                    name=label,
                    marker_color=color,
                    hovertemplate=f"{label}: %{{y:+.2%}}<extra></extra>",
                )
            )
        active_colors = theme.active_colors()
        fig_sec.add_trace(
            go.Scatter(
                x=sorted_df.index,
                y=sorted_df["Total Effect"],
                name="Total Effect",
                mode="markers",
                marker=dict(
                    symbol="diamond",
                    size=9,
                    color=active_colors["text"],
                    line=dict(width=1, color=active_colors["background"]),
                ),
                hovertemplate="Total Effect: %{y:+.2%}<extra></extra>",
            )
        )
        fig_sec.add_hline(y=0, line_dash="dash", line_color=theme.NEUTRAL, line_width=1)
        fig_sec.update_layout(
            barmode="group",
            yaxis=dict(title="Attribution Effect", tickformat=".2%"),
            xaxis=dict(tickangle=-30),
        )
        _apply_chart_spacing(fig_sec, "Brinson-Fachler Effects by Sector")
        theme.show_chart(fig_sec, height=460)


def _render_cumulative_chart(port_cum: pd.Series, bench_cum: pd.Series) -> None:
    if port_cum.empty or bench_cum.empty:
        st.info("Not enough daily data to plot cumulative performance.")
        return

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=port_cum.index,
            y=port_cum,
            name="Theoretical Portfolio",
            mode="lines",
            line=dict(color=theme.ACCENT, width=2.5),
            hovertemplate="Portfolio: %{y:.2%}<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=bench_cum.index,
            y=bench_cum,
            name="S&P 500 Benchmark",
            mode="lines",
            line=dict(color=theme.NEUTRAL, width=2, dash="dash"),
            hovertemplate="S&P 500: %{y:.2%}<extra></extra>",
        )
    )
    fig.add_hline(y=0, line_dash="dot", line_color=theme.NEUTRAL, line_width=1)
    fig.update_layout(
        yaxis=dict(title="Cumulative Return", tickformat=".1%"),
        xaxis=dict(title="Date"),
    )
    _apply_chart_spacing(fig, "Cumulative Performance: Theoretical Portfolio vs. S&P 500")
    theme.show_chart(fig, height=460)


def _render_weights_and_contributions_charts(sector_df: pd.DataFrame) -> None:
    col_w, col_c = st.columns(2, gap="large")

    with col_w:
        fig_w = go.Figure()
        fig_w.add_trace(
            go.Bar(
                x=sector_df.index,
                y=sector_df["Portfolio Weight"],
                name="Portfolio",
                marker_color=theme.ACCENT,
                hovertemplate="Portfolio: %{y:.2%}<extra></extra>",
            )
        )
        fig_w.add_trace(
            go.Bar(
                x=sector_df.index,
                y=sector_df["Benchmark Weight"],
                name="S&P 500",
                marker_color=theme.NEUTRAL,
                hovertemplate="S&P 500: %{y:.2%}<extra></extra>",
            )
        )
        fig_w.update_layout(
            barmode="group",
            yaxis=dict(title="Weight", tickformat=".0%"),
            xaxis=dict(tickangle=-30),
        )
        _apply_chart_spacing(fig_w, "Sector Weights: Portfolio vs. S&P 500")
        theme.show_chart(fig_w, height=460)

    with col_c:
        fig_c = go.Figure()
        fig_c.add_trace(
            go.Bar(
                x=sector_df.index,
                y=sector_df["Portfolio Contribution"],
                name="Portfolio Contribution",
                marker_color=theme.POSITIVE,
                hovertemplate="Portfolio Contribution: %{y:+.2%}<extra></extra>",
            )
        )
        fig_c.add_trace(
            go.Bar(
                x=sector_df.index,
                y=sector_df["Benchmark Contribution"],
                name="S&P 500 Contribution",
                marker_color=theme.SERIES[1],
                hovertemplate="S&P 500 Contribution: %{y:+.2%}<extra></extra>",
            )
        )
        fig_c.add_hline(y=0, line_dash="dash", line_color=theme.NEUTRAL, line_width=1)
        fig_c.update_layout(
            barmode="group",
            yaxis=dict(title="Return Contribution (w × R)", tickformat=".2%"),
            xaxis=dict(tickangle=-30),
        )
        _apply_chart_spacing(fig_c, "Sector Return Contribution: Portfolio vs. S&P 500")
        theme.show_chart(fig_c, height=460)


def _render_tables(
    sector_df: pd.DataFrame,
    holdings_df: pd.DataFrame,
    summary: dict[str, float],
) -> None:
    st.markdown("**Sector Attribution Summary**")
    total_row = pd.DataFrame(
        {
            "Portfolio Weight": [sector_df["Portfolio Weight"].sum()],
            "Benchmark Weight": [sector_df["Benchmark Weight"].sum()],
            "Active Weight": [sector_df["Active Weight"].sum()],
            "Portfolio Sector Return": [summary["portfolio_return"]],
            "Benchmark Sector Return": [summary["benchmark_return"]],
            "Active Sector Return": [summary["active_return"]],
            "Portfolio Contribution": [sector_df["Portfolio Contribution"].sum()],
            "Benchmark Contribution": [sector_df["Benchmark Contribution"].sum()],
            "Allocation Effect": [summary["allocation_effect"]],
            "Selection Effect": [summary["selection_effect"]],
            "Interaction Effect": [summary["interaction_effect"]],
            "Total Effect": [summary["total_effect"]],
        },
        index=["Total"],
    )
    table_df = pd.concat([sector_df, total_row])
    formatted_table = pd.DataFrame(
        {col: table_df[col].map(_fmt_pct) for col in table_df.columns},
        index=table_df.index,
    )
    st.dataframe(formatted_table, width="stretch")

    with st.expander("Holdings Return & Contribution Breakdown"):
        formatted_holdings = pd.DataFrame(
            {
                "Ticker": holdings_df["symbol"],
                "GICS Sector": holdings_df["sector"],
                "Weight": holdings_df["weight"].map(_fmt_pct),
                "Asset Return": holdings_df["return"].map(_fmt_pct),
                "Return Contribution": holdings_df["contribution"].map(
                    lambda v: _fmt_pct(v, signed=True)
                ),
            }
        )
        st.dataframe(formatted_holdings, hide_index=True, width="stretch")
