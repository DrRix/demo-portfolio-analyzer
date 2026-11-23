"""Pure portfolio optimization and simulation calculations (no UI)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from tabs.performance.calcs import annualization_factor, period_returns


def annualized_metrics(
    returns: pd.DataFrame, periodicity: str
) -> tuple[pd.Series, pd.DataFrame]:
    """Calculate arithmetic annualized mean returns and annualized covariance matrix."""
    if len(returns) < 2:
        raise ValueError("At least 2 return periods are required.")
    factor = annualization_factor(periodicity)
    mean_returns = returns.mean() * factor
    cov_matrix = returns.cov() * factor

    return mean_returns, cov_matrix


def calculate_two_asset_frontier(
    prices: pd.DataFrame,
    periodicity: str,
    num_combinations: int,
    tickers: list[str],
) -> pd.DataFrame | None:
    """Calculate the two-asset risk/return combinations using shared period returns
    and arithmetic annualized metrics.
    """
    if len(tickers) != 2:
        return None

    returns = period_returns(prices[tickers], periodicity).dropna()
    if len(returns) < 2:
        return None

    mean_returns, cov_matrix = annualized_metrics(returns, periodicity)
    if mean_returns.isna().any() or cov_matrix.isna().any().any():
        return None

    port_returns = []
    port_volatility = []
    port_weights_text = []

    weights_list = np.linspace(0, 1, num_combinations)

    for w1 in weights_list:
        w2 = 1.0 - w1
        weights = np.array([w1, w2])

        port_ret = float(np.dot(weights, mean_returns))
        port_returns.append(port_ret)

        variance = float(np.dot(weights.T, np.dot(cov_matrix, weights)))
        port_vol = float(np.sqrt(max(0.0, variance)))
        port_volatility.append(port_vol)

        w_text = f"{tickers[0]}: {w1:.1%} / {tickers[1]}: {w2:.1%}"
        port_weights_text.append(w_text)

    results_df = pd.DataFrame(
        {
            "Return": port_returns,
            "Volatility": port_volatility,
            "Weights": port_weights_text,
        }
    )

    return results_df


def monte_carlo_simulation(
    returns: pd.DataFrame,
    periodicity: str,
    num_simulations: int,
    risk_free_rate: float = 0.02,
) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """Runs a vectorized Monte Carlo simulation on N assets.

    Returns:
        results: array of shape (3, num_simulations) for [Return, Volatility, Sharpe]
        weights: array of shape (num_simulations, num_assets)
        tickers: list of ticker symbols
    """
    clean_returns = returns.dropna()
    if len(clean_returns) < 2:
        raise ValueError("At least 2 overlapping return periods are required.")
    tickers = list(clean_returns.columns)
    num_assets = len(tickers)

    mean_returns, cov_matrix = annualized_metrics(clean_returns, periodicity)
    mean_vec = mean_returns.to_numpy()
    cov_arr = cov_matrix.to_numpy()

    # Generate random portfolio weights summing to 1.0
    raw_weights = np.random.random((num_simulations, num_assets))
    weights = raw_weights / raw_weights.sum(axis=1, keepdims=True)

    # Vectorized return calculation: shape (num_simulations,)
    port_returns = weights @ mean_vec

    # Vectorized volatility calculation: sqrt(w @ cov @ w.T) for each row
    port_vol = np.sqrt(np.maximum(0.0, np.einsum("ij,jk,ik->i", weights, cov_arr, weights)))

    # Sharpe ratio
    sharpe = np.where(
        port_vol > 0, (port_returns - risk_free_rate) / port_vol, 0.0
    )

    results = np.zeros((3, num_simulations))
    results[0] = port_returns
    results[1] = port_vol
    results[2] = sharpe

    return results, weights, tickers
