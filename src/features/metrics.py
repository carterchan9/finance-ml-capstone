"""Metric functions for Stage 1.

Computes strategy performance metrics from return series.
All functions take a 1D array/Series of daily returns.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def annualized_return(returns: pd.Series | np.ndarray, periods_per_year: int = 252) -> float:
    """Annualized return from daily returns."""
    returns = np.asarray(returns)
    if len(returns) == 0:
        return np.nan
    total_return = np.prod(1 + returns) - 1
    n_years = len(returns) / periods_per_year
    return (1 + total_return) ** (1 / n_years) - 1 if n_years > 0 else np.nan


def annualized_volatility(returns: pd.Series | np.ndarray, periods_per_year: int = 252) -> float:
    """Annualized volatility from daily returns."""
    returns = np.asarray(returns)
    if len(returns) < 2:
        return np.nan
    return np.nanstd(returns, ddof=1) * np.sqrt(periods_per_year)


def sharpe_ratio(
    returns: pd.Series | np.ndarray,
    periods_per_year: int = 252,
    risk_free: float = 0.0,
) -> float:
    """Annualized Sharpe ratio (risk-free rate ignored by default)."""
    returns = np.asarray(returns)
    if len(returns) < 2:
        return np.nan
    excess = returns - risk_free / periods_per_year
    vol = np.nanstd(excess, ddof=1)
    if vol == 0:
        return np.nan
    return np.mean(excess) / vol * np.sqrt(periods_per_year)


def max_drawdown(returns: pd.Series | np.ndarray) -> float:
    """Maximum drawdown (peak-to-trough) as a positive number.

    Returns:
        Max drawdown as a positive decimal (e.g., 0.20 = 20% drawdown).
    """
    returns = np.asarray(returns)
    if len(returns) == 0:
        return np.nan
    # Cumulative wealth index starting at 1
    wealth = np.cumprod(1 + returns)
    # Running maximum
    running_max = np.maximum.accumulate(wealth)
    # Drawdown at each point
    drawdown = (running_max - wealth) / running_max
    return float(np.nanmax(drawdown))


def hit_rate(returns: pd.Series | np.ndarray) -> float:
    """Share of in-market days with positive return."""
    returns = np.asarray(returns)
    in_market = returns != 0
    if not np.any(in_market):
        return np.nan
    return float(np.mean(returns[in_market] > 0))


def exposure(returns: pd.Series | np.ndarray) -> float:
    """Share of days holding a position (non-zero return)."""
    returns = np.asarray(returns)
    if len(returns) == 0:
        return np.nan
    return float(np.mean(returns != 0))


def turnover(returns: pd.Series | np.ndarray) -> float:
    """Number of position changes per year (approximate from returns).

    Assumes position changes when return goes from 0 to non-zero or vice versa.
    """
    returns = np.asarray(returns)
    if len(returns) < 2:
        return 0.0
    # Position = 1 when in market, 0 when flat
    position = (returns != 0).astype(int)
    # Count transitions
    changes = np.sum(np.diff(position) != 0)
    # Annualize
    return float(changes / len(returns) * 252)


def skewness(returns: pd.Series | np.ndarray) -> float:
    """Skewness of daily returns (Fisher's definition, unbiased)."""
    returns = np.asarray(returns)
    if len(returns) < 3:
        return np.nan
    return float(pd.Series(returns).skew())


def kurtosis(returns: pd.Series | np.ndarray) -> float:
    """Excess kurtosis of daily returns (Fisher's definition, unbiased)."""
    returns = np.asarray(returns)
    if len(returns) < 4:
        return np.nan
    return float(pd.Series(returns).kurtosis())


def all_metrics(returns: pd.Series | np.ndarray) -> dict[str, float]:
    """Compute all metrics at once.

    Returns dict with keys matching feature schema v1.
    """
    return {
        "annualized_return": annualized_return(returns),
        "annualized_volatility": annualized_volatility(returns),
        "in_sample_sharpe": sharpe_ratio(returns),
        "max_drawdown": max_drawdown(returns),
        "hit_rate": hit_rate(returns),
        "exposure": exposure(returns),
        "turnover": turnover(returns),
        "skewness": skewness(returns),
        "excess_kurtosis": kurtosis(returns),
    }


if __name__ == "__main__":
    # Quick self-test with toy data
    toy = np.array([0.01, -0.005, 0.02, -0.01, 0.005, 0.0, 0.015])
    print("Toy returns:", toy)
    for name, func in [
        ("sharpe", sharpe_ratio),
        ("max_dd", max_drawdown),
        ("hit_rate", hit_rate),
        ("turnover", turnover),
        ("skew", skewness),
        ("kurt", kurtosis),
    ]:
        print(f"  {name}: {func(toy):.4f}")