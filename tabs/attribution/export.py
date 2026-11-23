"""Excel workbook export for Brinson-Fachler attribution reconciliation."""

from __future__ import annotations

import io
from typing import Any

import pandas as pd
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

from .data import SECTOR_ETFS

HEADER_FONT = Font(bold=True, color="FFFFFF")
HEADER_FILL = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
TOTAL_FONT = Font(bold=True)
TOTAL_FILL = PatternFill(start_color="E8EEF5", end_color="E8EEF5", fill_type="solid")


def _style_sheet(ws: Any, freeze_cell: str = "A2") -> None:
    """Apply header styling, freeze panes, and auto-fit column widths."""
    ws.freeze_panes = freeze_cell
    for cell in ws[1]:
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL

    for col_idx, col_cells in enumerate(ws.columns, start=1):
        max_len = 0
        for cell in col_cells:
            val = "" if cell.value is None else str(cell.value)
            if len(val) > max_len:
                max_len = len(val)
        ws.column_dimensions[get_column_letter(col_idx)].width = min(max(max_len + 3, 12), 42)


def _format_column_range(ws: Any, col_indices: list[int], num_format: str, start_row: int = 2) -> None:
    for row in ws.iter_rows(min_row=start_row, max_row=ws.max_row):
        for idx in col_indices:
            if idx <= len(row) and isinstance(row[idx - 1].value, (int, float)):
                row[idx - 1].number_format = num_format


def build_attribution_excel(payload: dict[str, Any]) -> bytes:
    """Build a multi-sheet Excel workbook containing all inputs and calculations
    needed to reconcile Brinson-Fachler attribution and Markowitz portfolio risk.
    """
    result = payload["data"]
    summary: dict[str, float] = result["summary"]
    sector_df: pd.DataFrame = result["sector_df"]
    holdings_df: pd.DataFrame = result["holdings_df"]
    cum_port_return: float = payload.get("cum_port_return", float("nan"))
    cum_spy_return: float = payload.get("cum_spy_return", float("nan"))
    ann_port_return: float = payload.get("ann_port_return", float("nan"))
    ann_spy_return: float = payload.get("ann_spy_return", float("nan"))
    portfolio_risk: float = payload.get("portfolio_risk", float("nan"))
    benchmark_risk: float = payload.get("benchmark_risk", float("nan"))
    portfolio_beta: float = payload.get("portfolio_beta", float("nan"))
    eff_start = payload["effective_start"]
    eff_end = payload["effective_end"]
    lookback = payload.get("lookback", "")
    aligned_prices: pd.DataFrame = payload.get("aligned_prices", pd.DataFrame())
    daily_returns: pd.DataFrame = payload.get("daily_returns", pd.DataFrame())
    port_cum: pd.Series = payload.get("port_cum", pd.Series(dtype=float))
    bench_cum: pd.Series = payload.get("bench_cum", pd.Series(dtype=float))
    port_asset_weights: dict[str, float] = payload.get("port_asset_weights", {})
    bench_asset_weights: dict[str, float] = payload.get("bench_asset_weights", {})

    # 1. Summary sheet
    risk_diff = (
        portfolio_risk - benchmark_risk
        if pd.notna(portfolio_risk) and pd.notna(benchmark_risk)
        else float("nan")
    )
    summary_rows = [
        ("Start Date", eff_start.strftime("%Y-%m-%d"), "First common trading date in window"),
        ("End Date", eff_end.strftime("%Y-%m-%d"), "Last common trading date in window"),
        ("Lookback Selection", str(lookback), "User-selected horizon"),
        ("Trading Days (Prices)", int(len(aligned_prices)), "Number of aligned daily price observations"),
        ("Trading Days (Returns)", int(len(daily_returns)), "Number of daily return observations"),
        ("Cumulative Portfolio Return", cum_port_return, "Constant-weight compounded return (matches Cumulative Performance)"),
        ("Cumulative SPY Return", cum_spy_return, "SPY compounded return (matches Cumulative Performance)"),
        *(
            [
                ("Annualized Portfolio Return (CAGR)", ann_port_return, "(1 + Cum Port Return)^(365.25 / days) - 1 (>1Y windows)"),
                ("Annualized SPY Return (CAGR)", ann_spy_return, "(1 + Cum SPY Return)^(365.25 / days) - 1 (>1Y windows)"),
            ]
            if pd.notna(ann_port_return) or pd.notna(ann_spy_return)
            else []
        ),
        ("Portfolio Volatility", portfolio_risk, "sqrt(w_p^T * Sigma * w_p), Sigma = Cov(daily) * 252"),
        ("S&P 500 Volatility", benchmark_risk, "Annualized std of SPY daily returns"),
        ("Volatility Difference (Port - SPY)", risk_diff, "Portfolio Volatility minus SPY Volatility"),
        ("Portfolio Beta (vs. SPY)", portfolio_beta, "Cov(R_p, R_SPY) / Var(R_SPY) using constant-weight daily returns"),
        ("Brinson-Fachler Portfolio Return (Rp)", summary["portfolio_return"], "Simple period return: sum of w_p,j * R_p,j"),
        ("Brinson-Fachler S&P 500 Proxy Return (Rb)", summary["benchmark_return"], "Simple period return: sum of w_b,j * R_b,j across 11 SPDR ETFs"),
        ("Active Return (Rp - Rb)", summary["active_return"], "Portfolio Simple Return minus S&P 500 Sector Proxy Return"),
        ("Allocation Effect", summary["allocation_effect"], "Sum of (w_p,j - w_b,j) * (R_b,j - Rb)"),
        ("Selection Effect", summary["selection_effect"], "Sum of w_b,j * (R_p,j - R_b,j)"),
        ("Interaction Effect", summary["interaction_effect"], "Sum of (w_p,j - w_b,j) * (R_p,j - R_b,j)"),
        ("Total Attribution Effect", summary["total_effect"], "Allocation + Selection + Interaction (= Active Return)"),
    ]
    summary_df = pd.DataFrame(summary_rows, columns=["Metric", "Value", "Formula / Notes"])

    # 2. Sector Attribution sheet (with Benchmark ETF + Total row)
    sec_export = sector_df.copy()
    sec_export.insert(0, "Benchmark ETF", [SECTOR_ETFS.get(sec, "") for sec in sec_export.index])
    total_row = pd.DataFrame(
        {
            "Benchmark ETF": ["—"],
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
    sec_export = pd.concat([sec_export, total_row])
    sec_export.index.name = "Sector"

    # 3. Holdings sheet
    holdings_export = holdings_df.rename(
        columns={
            "symbol": "Ticker",
            "sector": "GICS Sector",
            "weight": "Weight",
            "return": "Asset Return",
            "contribution": "Return Contribution",
        }
    )

    # 4. Daily Prices sheet
    prices_export = aligned_prices.copy()
    if not prices_export.empty:
        prices_export.index = pd.to_datetime(prices_export.index).strftime("%Y-%m-%d")
        prices_export.index.name = "Date"

    # 5. Daily Returns & Cumulative Curves sheet
    returns_export = daily_returns.copy()
    if not returns_export.empty:
        if not port_cum.empty:
            port_daily = (1.0 + port_cum).pct_change().fillna(port_cum)
            returns_export["Portfolio Daily Return"] = port_daily.reindex(daily_returns.index)
            returns_export["Portfolio Cumulative Return"] = port_cum.reindex(daily_returns.index)
        if not bench_cum.empty:
            bench_daily = (1.0 + bench_cum).pct_change().fillna(bench_cum)
            returns_export["S&P 500 Daily Return"] = bench_daily.reindex(daily_returns.index)
            returns_export["S&P 500 Cumulative Return"] = bench_cum.reindex(daily_returns.index)
        returns_export.index = pd.to_datetime(returns_export.index).strftime("%Y-%m-%d")
        returns_export.index.name = "Date"

    # 6. Annualized Covariance Matrix & Risk Weights sheet (active portfolio + SPY only)
    risk_cols = [
        c
        for c in daily_returns.columns
        if abs(port_asset_weights.get(c, 0.0)) > 1e-12
        or abs(bench_asset_weights.get(c, 0.0)) > 1e-12
    ]
    cov_export = (
        daily_returns[risk_cols].cov() * 252
        if len(daily_returns) >= 2 and risk_cols
        else pd.DataFrame()
    )
    if not cov_export.empty:
        cov_export.index.name = "Ticker"
    risk_weights_df = pd.DataFrame(
        {
            "Ticker": list(cov_export.columns),
            "Portfolio Weight": [float(port_asset_weights.get(c, 0.0)) for c in cov_export.columns],
            "SPY Benchmark Weight": [float(bench_asset_weights.get(c, 0.0)) for c in cov_export.columns],
        }
    )

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        summary_df.to_excel(writer, sheet_name="Summary", index=False)
        sec_export.to_excel(writer, sheet_name="Sector Attribution", index=True)
        holdings_export.to_excel(writer, sheet_name="Holdings", index=False)
        if not prices_export.empty:
            prices_export.to_excel(writer, sheet_name="Daily Prices", index=True)
        if not returns_export.empty:
            returns_export.to_excel(writer, sheet_name="Daily Returns", index=True)
        if not cov_export.empty:
            cov_export.to_excel(writer, sheet_name="Covariance & Risk", index=True, startrow=0)
            weights_start = len(cov_export) + 3
            risk_weights_df.to_excel(
                writer, sheet_name="Covariance & Risk", index=False, startrow=weights_start
            )

        # Apply number formatting and styles
        ws_sum = writer.sheets["Summary"]
        for row_idx in range(7, ws_sum.max_row + 1):
            metric_name = ws_sum.cell(row=row_idx, column=1).value
            cell = ws_sum.cell(row=row_idx, column=2)
            if isinstance(cell.value, (int, float)):
                cell.number_format = "0.00" if metric_name == "Portfolio Beta (vs. SPY)" else "0.00%"
        _style_sheet(ws_sum)

        ws_sec = writer.sheets["Sector Attribution"]
        _format_column_range(ws_sec, list(range(3, ws_sec.max_column + 1)), "0.00%")
        for cell in ws_sec[ws_sec.max_row]:
            cell.font = TOTAL_FONT
            cell.fill = TOTAL_FILL
        _style_sheet(ws_sec, freeze_cell="C2")

        ws_hold = writer.sheets["Holdings"]
        _format_column_range(ws_hold, [3, 4, 5], "0.00%")
        _style_sheet(ws_hold)

        if "Daily Prices" in writer.sheets:
            ws_px = writer.sheets["Daily Prices"]
            _format_column_range(ws_px, list(range(2, ws_px.max_column + 1)), "#,##0.0000")
            _style_sheet(ws_px, freeze_cell="B2")

        if "Daily Returns" in writer.sheets:
            ws_ret = writer.sheets["Daily Returns"]
            _format_column_range(ws_ret, list(range(2, ws_ret.max_column + 1)), "0.0000%")
            _style_sheet(ws_ret, freeze_cell="B2")

        if "Covariance & Risk" in writer.sheets:
            ws_cov = writer.sheets["Covariance & Risk"]
            cov_end_row = len(cov_export) + 1
            for row in ws_cov.iter_rows(min_row=2, max_row=cov_end_row):
                for cell in row[1:]:
                    if isinstance(cell.value, (int, float)):
                        cell.number_format = "0.000000"
            weights_header_row = len(cov_export) + 4
            for cell in ws_cov[weights_header_row]:
                cell.font = HEADER_FONT
                cell.fill = HEADER_FILL
            for row in ws_cov.iter_rows(min_row=weights_header_row + 1, max_row=ws_cov.max_row):
                for cell in row[1:]:
                    if isinstance(cell.value, (int, float)):
                        cell.number_format = "0.00%"
            _style_sheet(ws_cov, freeze_cell="B2")

    return buf.getvalue()
