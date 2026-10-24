"""Strategy generator for Stage 1.

Builds position and return series for rule-based strategies across parameter grids.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import pandas as pd

from src.config import load_stage1_config


def load_prices(db_path: str) -> pd.DataFrame:
    """Load prices from SQLite.

    Returns:
        DataFrame with columns: date, ticker, close (adjusted).
    """
    conn = sqlite3.connect(db_path)
    try:
        df = pd.read_sql("SELECT date, ticker, close FROM prices", conn)
    finally:
        conn.close()
    df["date"] = pd.to_datetime(df["date"])
    return df.sort_values(["ticker", "date"]).reset_index(drop=True)


def ma_crossover_signals(close: pd.Series, fast: int, slow: int) -> pd.Series:
    """Moving-average crossover: long when fast > slow, else flat.

    Signal on day t uses data up to and including day t.
    Position on day t+1 follows signal from day t (no lookahead).

    Args:
        close: Series of adjusted close prices.
        fast: Fast MA window.
        slow: Slow MA window.

    Returns:
        Position series (1 = long, 0 = flat), same index as close.
    """
    fast_ma = close.rolling(fast, min_periods=fast).mean()
    slow_ma = close.rolling(slow, min_periods=slow).mean()
    signal = (fast_ma > slow_ma).astype(int)
    # Position on t+1 = signal on t → shift forward by 1
    position = signal.shift(1).fillna(0).astype(int)
    return position


def momentum_signals(close: pd.Series, lookback: int) -> pd.Series:
    """Momentum: long when trailing return > 0, else flat.

    Signal on day t uses return over lookback window ending at t.
    Position on day t+1 follows signal from day t.

    Args:
        close: Series of adjusted close prices.
        lookback: Lookback window in days.

    Returns:
        Position series (1 = long, 0 = flat).
    """
    ret = close.pct_change(lookback)
    signal = (ret > 0).astype(int)
    position = signal.shift(1).fillna(0).astype(int)
    return position


def mean_reversion_signals(close: pd.Series, window: int, threshold: float) -> pd.Series:
    """Mean reversion: long when price is threshold std below rolling mean.

    Enters when price < mean - threshold * std.
    Exits when price returns to mean (crosses above mean).

    Signal on day t uses data up to and including day t.
    Position on day t+1 follows signal from day t.

    Args:
        close: Series of adjusted close prices.
        window: Rolling window for mean/std.
        threshold: Number of standard deviations below mean to enter.

    Returns:
        Position series (1 = long, 0 = flat).
    """
    rolling_mean = close.rolling(window, min_periods=window).mean()
    rolling_std = close.rolling(window, min_periods=window).std()
    lower_band = rolling_mean - threshold * rolling_std

    # Enter signal: price below lower band
    enter = (close < lower_band).astype(int)
    # Exit signal: price back above mean
    exit_signal = (close >= rolling_mean).astype(int)

    # Build position: enter=1, exit=0, otherwise hold previous
    signal = pd.Series(0, index=close.index)
    position = pd.Series(0, index=close.index)

    for i in range(len(close)):
        if i == 0:
            position.iloc[i] = 0
        elif enter.iloc[i]:
            position.iloc[i] = 1
        elif exit_signal.iloc[i] and position.iloc[i - 1] == 1:
            position.iloc[i] = 0
        else:
            position.iloc[i] = position.iloc[i - 1]

    # Shift: position on t+1 = signal on t
    return position.shift(1).fillna(0).astype(int)


def strategy_returns(
    close: pd.Series, position: pd.Series
) -> tuple[pd.Series, int]:
    """Compute daily strategy returns from positions.

    Args:
        close: Adjusted close prices.
        position: Position series (1 = long, 0 = flat).

    Returns:
        Tuple of (returns Series, in_market_days count).
    """
    # Daily return of the asset
    asset_ret = close.pct_change()
    # Strategy return = position(t-1) * asset_return(t)
    # position is already shifted (position on t = signal on t-1)
    strat_ret = position * asset_ret
    in_market_days = int((position == 1).sum())
    return strat_ret, in_market_days


def generate_strategies(config_path: str = "config/stage1.toml") -> int:
    """Generate all strategies for all tickers and parameter combinations.

    Writes:
    - strategies table in SQLite (strategy_id, family, params, ticker)
    - Return series CSV per ticker in data/processed/returns_{ticker}.csv

    Args:
        config_path: Path to stage1.toml.

    Returns:
        Total strategies generated.
    """
    cfg = load_stage1_config(config_path)

    tickers = cfg["data"]["universe"]
    db_path = cfg["paths"]["db_path"]
    processed_dir = Path(cfg["paths"]["processed_data_dir"])
    processed_dir.mkdir(parents=True, exist_ok=True)

    # Parameter grids from config
    ma_fast = cfg["strategy_generator"]["ma_fast"]
    ma_slow = cfg["strategy_generator"]["ma_slow"]
    mom_lookback = cfg["strategy_generator"]["mom_lookback"]
    mr_window = cfg["strategy_generator"]["mr_window"]
    mr_threshold = cfg["strategy_generator"]["mr_threshold"]

    # Load prices
    prices = load_prices(db_path)

    conn = sqlite3.connect(db_path)
    try:
        # Create strategies table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS strategies (
                strategy_id TEXT PRIMARY KEY,
                family TEXT NOT NULL,
                params TEXT NOT NULL,
                ticker TEXT NOT NULL,
                FOREIGN KEY (ticker) REFERENCES prices(ticker)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_strategies_ticker ON strategies (ticker)")

        strategy_id = 0
        total_generated = 0

        for ticker in tickers:
            ticker_prices = prices[prices["ticker"] == ticker]["close"]
            if len(ticker_prices) < 200:  # need enough for slowest MA
                continue

            returns_dict = {"date": ticker_prices.index}

            # 1. MA Crossover
            for fast in ma_fast:
                for slow in ma_slow:
                    if fast >= slow:
                        continue
                    pos = ma_crossover_signals(ticker_prices, fast, slow)
                    ret, in_mkt = strategy_returns(ticker_prices, pos)
                    if in_mkt < 30:
                        continue
                    param_str = f"fast={fast},slow={slow}"
                    sid = f"MA_{ticker}_{fast}_{slow}"
                    conn.execute(
                        "INSERT OR REPLACE INTO strategies (strategy_id, family, params, ticker) VALUES (?, ?, ?, ?)",
                        (sid, "ma_crossover", param_str, ticker),
                    )
                    returns_dict[sid] = ret.values
                    strategy_id += 1
                    total_generated += 1

            # 2. Momentum
            for lookback in mom_lookback:
                pos = momentum_signals(ticker_prices, lookback)
                ret, in_mkt = strategy_returns(ticker_prices, pos)
                if in_mkt < 30:
                    continue
                param_str = f"lookback={lookback}"
                sid = f"MOM_{ticker}_{lookback}"
                conn.execute(
                    "INSERT OR REPLACE INTO strategies (strategy_id, family, params, ticker) VALUES (?, ?, ?, ?)",
                    (sid, "momentum", param_str, ticker),
                )
                returns_dict[sid] = ret.values
                total_generated += 1

            # 3. Mean Reversion
            for window in mr_window:
                for threshold in mr_threshold:
                    pos = mean_reversion_signals(ticker_prices, window, threshold)
                    ret, in_mkt = strategy_returns(ticker_prices, pos)
                    if in_mkt < 30:
                        continue
                    param_str = f"window={window},threshold={threshold}"
                    sid = f"MR_{ticker}_{window}_{threshold}"
                    conn.execute(
                        "INSERT OR REPLACE INTO strategies (strategy_id, family, params, ticker) VALUES (?, ?, ?, ?)",
                        (sid, "mean_reversion", param_str, ticker),
                    )
                    returns_dict[sid] = ret.values
                    total_generated += 1

            # Save return series for this ticker
            if len(returns_dict) > 1:
                ret_df = pd.DataFrame(returns_dict)
                ret_df.to_csv(processed_dir / f"returns_{ticker}.csv", index=False)

        conn.commit()
        print(f"Generated {total_generated} strategies across {len(tickers)} tickers")
        return total_generated

    finally:
        conn.close()


if __name__ == "__main__":
    count = generate_strategies()
    print(f"Total strategies: {count}")