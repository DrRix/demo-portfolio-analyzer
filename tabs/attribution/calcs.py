"""Pure Brinson-Fachler attribution and weight validation calculations (no UI)."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pandas as pd


def validate_weights(
    weights_pct: Sequence[float] | pd.Series,
    tol: float = 0.01,
) -> tuple[bool, str, float]:
    """Validate that all portfolio weights are in [0%, 100%] and sum to 100%.

    Returns:
        (is_valid, message, total_pct)
    """
    values: list[float] = []
    for raw in weights_pct:
        try:
            val = float(raw)
        except (TypeError, ValueError):
            return False, "All weights must be valid numbers between 0% and 100%.", 0.0
        if not np.isfinite(val):
            return False, "All weights must be finite numbers between 0% and 100%.", 0.0
        values.append(val)

    if not values:
        return False, "Add at least one ticker with a portfolio weight.", 0.0

    total = float(sum(values))

    for val in values:
        if val < 0.0 or val > 100.0:
            return False, "Each ticker weight must be between 0% and 100%.", total

    diff = total - 100.0
    if abs(diff) > tol:
        if diff > 0:
            return (
                False,
                f"Total weight is {total:.2f}% ({diff:+.2f}% over 100%). "
                f"Reduce weights by {diff:.2f}%.",
                total,
            )
        return (
            False,
            f"Total weight is {total:.2f}% ({diff:+.2f}% under 100%). "
            f"Add {abs(diff):.2f}% more.",
            total,
        )

    return True, f"Total weight is {total:.2f}% (valid).", total


def period_total_returns(prices: pd.DataFrame) -> pd.Series:
    """Compute cumulative simple return over the loaded price history per column.

    Uses forward-filled prices over the common overlapping window when at least
    two overlapping dates exist, falling back to each symbol's first/last valid
    close otherwise.
    """
    if prices.empty:
        return pd.Series(dtype=float)

    filled = prices.ffill()
    overlapping = filled.dropna(how="any")
    if len(overlapping) >= 2:
        start_prices = overlapping.iloc[0].replace(0, np.nan)
        return (overlapping.iloc[-1] / start_prices) - 1.0

    results: dict[str, float] = {}
    for col in filled.columns:
        series = filled[col].dropna()
        if len(series) >= 2 and series.iloc[0] != 0:
            results[col] = float((series.iloc[-1] / series.iloc[0]) - 1.0)
        else:
            results[col] = float("nan")
    return pd.Series(results, dtype=float)


def portfolio_volatility(
    daily_returns: pd.DataFrame,
    weights: dict[str, float],
    trading_days: int = 252,
) -> float:
    """Compute exact Markowitz annualized portfolio standard deviation.

    Uses the full n x n annualized variance-covariance matrix:
        sigma_p = sqrt(w^T * Sigma * w),  Sigma = Cov(R_daily) * trading_days
    """
    active = [
        (sym, float(w))
        for sym, w in weights.items()
        if sym in daily_returns.columns and abs(float(w)) > 1e-12
    ]
    if not active or len(daily_returns) < 2:
        return float("nan")

    cols = [sym for sym, _ in active]
    w_vec = np.array([w for _, w in active], dtype=float)
    cov = daily_returns[cols].cov().to_numpy(dtype=float) * trading_days
    variance = float(w_vec.T @ cov @ w_vec)
    if not np.isfinite(variance):
        return float("nan")
    return float(np.sqrt(max(0.0, variance)))


def portfolio_beta(
    daily_returns: pd.DataFrame,
    weights: dict[str, float],
    benchmark_daily_returns: pd.Series,
) -> float:
    """Compute constant-weight portfolio beta against a benchmark daily return series.

    Uses sample covariance and variance (ddof=1):
        beta = Cov(R_p, R_b) / Var(R_b), where R_p(t) = sum_i w_i * r_i(t).
    """
    active = [
        (sym, float(w))
        for sym, w in weights.items()
        if sym in daily_returns.columns and abs(float(w)) > 1e-12
    ]
    if not active or daily_returns.empty or benchmark_daily_returns.empty:
        return float("nan")

    cols = [sym for sym, _ in active]
    w_vec = np.array([w for _, w in active], dtype=float)
    port_ret = pd.Series(
        daily_returns[cols].to_numpy(dtype=float) @ w_vec,
        index=daily_returns.index,
        dtype=float,
    )
    combined = pd.DataFrame({"p": port_ret, "b": benchmark_daily_returns}).dropna()
    if len(combined) < 2:
        return float("nan")

    var_b = float(combined["b"].var(ddof=1))
    if not np.isfinite(var_b) or var_b <= 1e-18:
        return float("nan")

    cov_pb = float(combined["p"].cov(combined["b"]))
    return cov_pb / var_b if np.isfinite(cov_pb) else float("nan")


def portfolio_cumulative_returns(
    daily_returns: pd.DataFrame,
    weights: dict[str, float],
    start_date: pd.Timestamp | None = None,
) -> pd.Series:
    """Compute constant-weight (daily-rebalanced) cumulative return series."""
    active = [
        (sym, float(w))
        for sym, w in weights.items()
        if sym in daily_returns.columns and abs(float(w)) > 1e-12
    ]
    if not active or daily_returns.empty:
        return pd.Series(dtype=float)

    cols = [sym for sym, _ in active]
    w_vec = np.array([w for _, w in active], dtype=float)
    port_daily = daily_returns[cols].to_numpy(dtype=float) @ w_vec
    cum = pd.Series(
        np.cumprod(1.0 + port_daily) - 1.0,
        index=daily_returns.index,
        dtype=float,
    )
    if start_date is not None and start_date not in cum.index:
        origin = pd.Series([0.0], index=[start_date], dtype=float)
        cum = pd.concat([origin, cum])
    return cum


def brinson_fachler_attribution(
    holdings: pd.DataFrame,
    benchmark_weights: dict[str, float],
    benchmark_returns: pd.Series,
    etf_sector_weights: dict[str, dict[str, float]] | None = None,
    sp500_trackers: set[str] | None = None,
    multi_sector_label: str = "Multi-Sector ETF (Look-through)",
) -> dict[str, object]:
    """Compute single-period Brinson-Fachler (1985) sector attribution.

    Holdings assigned ``multi_sector_label`` are decomposed across GICS sectors
    using ``etf_sector_weights`` (or ``benchmark_weights`` as fallback). Symbols
    in ``sp500_trackers`` use benchmark sector returns on look-through slices so
    a 100% S&P 500 tracker portfolio yields zero active attribution effects.

    Args:
        holdings: DataFrame with columns ``symbol``, ``sector``, ``weight``
            (decimal in [0, 1], summing to 1.0), and ``return`` (decimal).
        benchmark_weights: Mapping of sector name -> benchmark decimal weight.
        benchmark_returns: Series indexed by sector name -> benchmark decimal return.
        etf_sector_weights: Optional mapping of ETF symbol -> sector weight dict.
        sp500_trackers: Optional set of S&P 500 tracker symbols (e.g. SPY, VOO).
        multi_sector_label: Sector label indicating look-through ETF decomposition.

    Returns:
        Dictionary with keys:
            - ``sector_df``: DataFrame indexed by sector with weights, returns,
              and Allocation / Selection / Interaction / Total effects.
            - ``holdings_df``: Holdings DataFrame enriched with ``contribution``.
            - ``summary``: Summary totals dict verifying sum(effects) == Rp - Rb.
    """
    required_cols = {"symbol", "sector", "weight", "return"}
    missing_cols = required_cols - set(holdings.columns)
    if missing_cols:
        raise ValueError(f"Holdings missing required columns: {sorted(missing_cols)}")

    if holdings.empty:
        raise ValueError("Holdings cannot be empty.")

    holdings_df = holdings.copy()
    holdings_df["weight"] = holdings_df["weight"].astype(float)
    holdings_df["return"] = holdings_df["return"].astype(float)

    if (holdings_df["weight"] < -1e-9).any() or (holdings_df["weight"] > 1.0 + 1e-9).any():
        raise ValueError("All holding weights must be in [0.0, 1.0].")
    if not np.isclose(holdings_df["weight"].sum(), 1.0, atol=1e-3):
        raise ValueError("Holding weights must sum to 1.0.")

    regular_sectors = [
        str(s) for s in holdings_df["sector"].tolist() if str(s) != multi_sector_label
    ]
    sectors = list(dict.fromkeys([*benchmark_weights.keys(), *regular_sectors]))
    raw_wb = {s: float(benchmark_weights.get(s, 0.0)) for s in sectors}
    wb_sum = sum(raw_wb.values())
    if wb_sum <= 0:
        raise ValueError("Benchmark weights must sum to a positive value.")
    wb = {s: raw_wb[s] / wb_sum for s in sectors}

    rb_series = benchmark_returns.reindex(sectors)
    if rb_series.isna().any():
        missing_secs = rb_series[rb_series.isna()].index.tolist()
        raise ValueError(f"Missing benchmark returns for sectors: {missing_secs}")

    rb_total = float(sum(wb[s] * float(rb_series.loc[s]) for s in sectors))

    etf_weights_map = {k.strip().upper(): v for k, v in (etf_sector_weights or {}).items()}
    tracker_set = {s.strip().upper() for s in (sp500_trackers or set())}

    slice_rows: list[dict[str, float | str]] = []
    effective_returns: list[float] = []
    for _, row in holdings_df.iterrows():
        sym = str(row["symbol"]).strip().upper()
        sec = str(row["sector"])
        w = float(row["weight"])
        r = float(row["return"])

        if sec == multi_sector_label:
            raw_sec_w = etf_weights_map.get(sym) or wb
            pos_w = {
                s: float(raw_sec_w.get(s, 0.0))
                for s in sectors
                if float(raw_sec_w.get(s, 0.0)) > 0
            }
            pos_sum = sum(pos_w.values())
            if pos_sum <= 0:
                pos_w = dict(wb)
                pos_sum = 1.0
            norm_sec_w = {s: val / pos_sum for s, val in pos_w.items()}

            if sym in tracker_set:
                tracker_ret = float(
                    sum(sw * float(rb_series.loc[s]) for s, sw in norm_sec_w.items())
                )
                effective_returns.append(tracker_ret)
                if w > 0:
                    for s, sw in norm_sec_w.items():
                        slice_rows.append(
                            {"sector": s, "weight": w * sw, "return": float(rb_series.loc[s])}
                        )
            else:
                effective_returns.append(r)
                if w > 0:
                    for s, sw in norm_sec_w.items():
                        slice_rows.append({"sector": s, "weight": w * sw, "return": r})
        else:
            effective_returns.append(r)
            if w > 0:
                slice_rows.append({"sector": sec, "weight": w, "return": r})

    holdings_df["return"] = effective_returns
    slices_df = pd.DataFrame(slice_rows)
    rp_total = float((slices_df["weight"] * slices_df["return"]).sum())

    rows: list[dict[str, float | str]] = []
    for sec in sectors:
        sec_rows = slices_df[slices_df["sector"] == sec]
        wp_s = float(sec_rows["weight"].sum())
        wb_s = wb[sec]
        rb_s = float(rb_series.loc[sec])

        allocation = (wp_s - wb_s) * (rb_s - rb_total)

        if wp_s > 1e-12:
            rp_s = float((sec_rows["weight"] * sec_rows["return"]).sum() / wp_s)
            selection = wb_s * (rp_s - rb_s)
            interaction = (wp_s - wb_s) * (rp_s - rb_s)
            active_ret = rp_s - rb_s
            display_rp: float = rp_s
            port_contrib = wp_s * rp_s
        else:
            # Standard Brinson-Fachler convention: unheld sectors have 0 selection & interaction.
            selection = 0.0
            interaction = 0.0
            active_ret = float("nan")
            display_rp = float("nan")
            port_contrib = 0.0

        bench_contrib = wb_s * rb_s
        total_effect = allocation + selection + interaction

        def _snap_zero(val: float) -> float:
            return 0.0 if pd.notna(val) and abs(val) < 1e-12 else val

        rows.append(
            {
                "Sector": sec,
                "Portfolio Weight": _snap_zero(wp_s),
                "Benchmark Weight": _snap_zero(wb_s),
                "Active Weight": _snap_zero(wp_s - wb_s),
                "Portfolio Sector Return": _snap_zero(display_rp),
                "Benchmark Sector Return": _snap_zero(rb_s),
                "Active Sector Return": _snap_zero(active_ret),
                "Portfolio Contribution": _snap_zero(port_contrib),
                "Benchmark Contribution": _snap_zero(bench_contrib),
                "Allocation Effect": _snap_zero(allocation),
                "Selection Effect": _snap_zero(selection),
                "Interaction Effect": _snap_zero(interaction),
                "Total Effect": _snap_zero(total_effect),
            }
        )

    sector_df = pd.DataFrame(rows).set_index("Sector")

    holdings_df["contribution"] = np.where(
        holdings_df["weight"] > 0,
        holdings_df["weight"] * holdings_df["return"],
        0.0,
    )
    holdings_df = holdings_df.sort_values("weight", ascending=False).reset_index(drop=True)

    summary = {
        "portfolio_return": rp_total,
        "benchmark_return": rb_total,
        "active_return": rp_total - rb_total,
        "allocation_effect": float(sector_df["Allocation Effect"].sum()),
        "selection_effect": float(sector_df["Selection Effect"].sum()),
        "interaction_effect": float(sector_df["Interaction Effect"].sum()),
        "total_effect": float(sector_df["Total Effect"].sum()),
    }

    return {
        "sector_df": sector_df,
        "holdings_df": holdings_df,
        "summary": summary,
    }
