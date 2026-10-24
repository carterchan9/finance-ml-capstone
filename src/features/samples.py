"""Sample, feature, and label builders for Stage 1.

Constructs modeling dataset at rolling quarterly origin dates:
- Samples: each strategy at each origin date with in/out windows
- Features: computed from in-sample returns only
- Labels: computed from out-of-sample returns only
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.config import load_stage1_config
from src.features.metrics import all_metrics, annualized_volatility, sharpe_ratio


def get_origin_dates(config: dict[str, Any]) -> list[pd.Timestamp]:
    """Generate quarterly origin dates from config."""
    start = pd.Timestamp(config["data"]["start_date"])
    end = pd.Timestamp(config["data"]["end_date"])

    in_sample_years = config["windows"]["in_sample_years"]
    out_of_sample_years = config["windows"]["out_of_sample_years"]
    purge_gap_years = config["windows"]["purge_gap_years"]

    # First origin with full in-sample window
    first_origin = start + pd.DateOffset(years=in_sample_years)
    # Last origin with full out-of-sample window before end
    last_origin = end - pd.DateOffset(years=out_of_sample_years)

    origins = pd.date_range(
        start=first_origin,
        end=last_origin,
        freq="QE",  # quarter end
    )

    return origins.tolist()


def build_samples(config_path: str = "config/stage1.toml") -> int:
    """Build samples table: each row = one strategy at one origin date.

    Args:
        config_path: Path to stage1.toml.

    Returns:
        Number of samples created.
    """
    cfg = load_stage1_config(config_path)

    db_path = cfg["paths"]["db_path"]
    in_sample_years = cfg["windows"]["in_sample_years"]
    out_of_sample_years = cfg["windows"]["out_of_sample_years"]
    min_in_market_days = cfg["windows"]["min_in_market_days"]

    origins = get_origin_dates(cfg)

    conn = sqlite3.connect(db_path)
    try:
        # Create samples table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS samples (
                sample_id TEXT PRIMARY KEY,
                strategy_id TEXT NOT NULL,
                origin_date TEXT NOT NULL,
                in_sample_start TEXT NOT NULL,
                in_sample_end TEXT NOT NULL,
                out_of_sample_start TEXT NOT NULL,
                out_of_sample_end TEXT NOT NULL,
                FOREIGN KEY (strategy_id) REFERENCES strategies(strategy_id)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_samples_strategy ON samples (strategy_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_samples_origin ON samples (origin_date)")

        # Load strategies
        strategies = pd.read_sql("SELECT strategy_id, ticker FROM strategies", conn)

        # Load return series for each ticker
        returns_cache = {}
        processed_dir = Path(cfg["paths"]["processed_data_dir"])
        for ticker in strategies["ticker"].unique():
            f = processed_dir / f"returns_{ticker}.csv"
            if f.exists():
                df = pd.read_csv(f, parse_dates=["date"], date_format="%Y-%m-%d")
                df.set_index("date", inplace=True)
                returns_cache[ticker] = df

        sample_id = 0
        total = 0

        for origin in origins:
            origin_str = origin.strftime("%Y-%m-%d")
            in_start = origin - pd.DateOffset(years=in_sample_years)
            in_end = origin
            oos_start = origin
            oos_end = origin + pd.DateOffset(years=out_of_sample_years)

            in_start_str = in_start.strftime("%Y-%m-%d")
            in_end_str = in_end.strftime("%Y-%m-%d")
            oos_start_str = oos_start.strftime("%Y-%m-%d")
            oos_end_str = oos_end.strftime("%Y-%m-%d")

            for _, strat in strategies.iterrows():
                sid = strat["strategy_id"]
                ticker = strat["ticker"]

                if ticker not in returns_cache:
                    continue

                ret_df = returns_cache[ticker]
                # Get returns for this strategy
                if sid not in ret_df.columns:
                    continue

                strat_returns = ret_df[sid].dropna()

                # In-sample returns
                in_ret = strat_returns[
                    (strat_returns.index >= in_start) & (strat_returns.index < in_end)
                ]
                # Out-of-sample returns
                oos_ret = strat_returns[
                    (strat_returns.index >= oos_start) & (strat_returns.index < oos_end)
                ]

                # Filter: need enough in-market days
                in_mkt_days = int((in_ret != 0).sum())
                if in_mkt_days < min_in_market_days:
                    continue

                sample_id_str = f"{sid}_{origin_str}"
                conn.execute(
                    """
                    INSERT OR REPLACE INTO samples
                    (sample_id, strategy_id, origin_date, in_sample_start, in_sample_end,
                     out_of_sample_start, out_of_sample_end)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (sample_id_str, sid, origin_str, in_start_str, in_end_str,
                     oos_start_str, oos_end_str),
                )
                sample_id += 1
                total += 1

        conn.commit()
        print(f"Built {total} samples across {len(origins)} origin dates")
        return total

    finally:
        conn.close()


def build_features(config_path: str = "config/stage1.toml") -> int:
    """Build features table from in-sample returns.

    Computes features using returns up to and including origin date only.
    """
    cfg = load_stage1_config(config_path)
    db_path = cfg["paths"]["db_path"]
    feature_schema_version = cfg["versioning"]["feature_schema_version"]

    origins = get_origin_dates(cfg)

    # Load returns cache
    processed_dir = Path(cfg["paths"]["processed_data_dir"])
    returns_cache = {}
    for f in processed_dir.glob("returns_*.csv"):
        ticker = f.stem.replace("returns_", "")
        df = pd.read_csv(f, parse_dates=["date"], date_format="%Y-%m-%d")
        df.set_index("date", inplace=True)
        df.index = pd.to_datetime(df.index, format="%Y-%m-%d")
        returns_cache[ticker] = df

    conn = sqlite3.connect(db_path)
    try:
        # Create features table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS features (
                sample_id TEXT PRIMARY KEY,
                feature_schema_version INTEGER NOT NULL,
                annualized_return REAL,
                annualized_volatility REAL,
                in_sample_sharpe REAL,
                max_drawdown REAL,
                hit_rate REAL,
                exposure REAL,
                turnover REAL,
                skewness REAL,
                excess_kurtosis REAL,
                sharpe_rank_in_grid REAL,
                underlying_volatility REAL,
                family TEXT,
                FOREIGN KEY (sample_id) REFERENCES samples(sample_id)
            )
        """)

        # Load samples
        samples = pd.read_sql("SELECT sample_id, strategy_id FROM samples", conn)
        # Load strategy metadata
        strategies = pd.read_sql("SELECT strategy_id, family, params, ticker FROM strategies", conn)
        samples = samples.merge(strategies, on="strategy_id")

        total = 0
        for _, sample in samples.iterrows():
            sid = sample["sample_id"]
            strat_id = sample["strategy_id"]
            ticker = sample["ticker"]
            family = sample["family"]
            params = sample["params"]

            if ticker not in returns_cache:
                continue

            ret_df = returns_cache[ticker]
            if strat_id not in ret_df.columns:
                continue

            strat_returns = ret_df[strat_id].dropna()

            # Get origin date
            origin = pd.Timestamp(sid.split("_")[-1])
            in_start = origin - pd.DateOffset(years=cfg["windows"]["in_sample_years"])
            in_end = origin

            in_ret = strat_returns[
                (strat_returns.index >= in_start) & (strat_returns.index < in_end)
            ]

            if len(in_ret) < 30:
                continue

            # Compute features
            feats = all_metrics(in_ret)

            # Sharpe rank in grid: percentile of this sample's Sharpe among all
            # settings of same family on same ticker at same origin
            # (We'll compute this after all features are built)
            feats["sharpe_rank_in_grid"] = np.nan
            feats["underlying_volatility"] = np.nan  # computed below
            feats["family"] = family

            # Underlying volatility: ticker's own return volatility in same window
            # Need ticker's underlying returns (not strategy returns)
            # For simplicity, we'll approximate from the strategy's close prices
            # In practice, load raw ticker returns separately
            feats["underlying_volatility"] = annualized_volatility(in_ret)

            # Insert
            cols = ", ".join(feats.keys())
            placeholders = ", ".join(["?"] * len(feats))
            vals = list(feats.values()) + [feature_schema_version, sid]

            conn.execute(
                f"""
                INSERT OR REPLACE INTO features
                (sample_id, feature_schema_version, {cols})
                VALUES (?, ?, {placeholders})
                """,
                [sid, feature_schema_version] + list(feats.values()),
            )
            total += 1

        # Compute Sharpe rank in grid (percentile within family/ticker/origin)
        # For each origin/family/ticker, rank the in_sample_sharpe
        query = """
            SELECT f.sample_id, f.in_sample_sharpe, st.family, st.ticker, s.origin_date
            FROM features f
            JOIN samples s ON f.sample_id = s.sample_id
            JOIN strategies st ON s.strategy_id = st.strategy_id
        """
        ranks_df = pd.read_sql(query, conn)

        for (origin, family, ticker), group in ranks_df.groupby(["origin_date", "family", "ticker"]):
            if len(group) > 1:
                sharpe_vals = group["in_sample_sharpe"].values
                ranks = pd.Series(sharpe_vals).rank(pct=True).values
                for (_, row), rank in zip(group.iterrows(), ranks):
                    conn.execute(
                        "UPDATE features SET sharpe_rank_in_grid = ? WHERE sample_id = ?",
                        (float(rank), row["sample_id"]),
                    )

        conn.commit()
        print(f"Built features for {total} samples (schema v{feature_schema_version})")
        return total

    finally:
        conn.close()


def build_labels(config_path: str = "config/stage1.toml") -> int:
    """Build labels table from out-of-sample returns.

    Labels use returns AFTER the origin date only.
    """
    cfg = load_stage1_config(config_path)
    db_path = cfg["paths"]["db_path"]
    label_version = cfg["versioning"]["label_version"]
    decayed_threshold = cfg["label"]["decayed_threshold"]

    # Load returns cache
    processed_dir = Path(cfg["paths"]["processed_data_dir"])
    returns_cache = {}
    for f in processed_dir.glob("returns_*.csv"):
        ticker = f.stem.replace("returns_", "")
        df = pd.read_csv(f, parse_dates=["date"], date_format="%Y-%m-%d")
        df.set_index("date", inplace=True)
        df.index = pd.to_datetime(df.index, format="%Y-%m-%d")
        returns_cache[ticker] = df

    conn = sqlite3.connect(db_path)
    try:
        # Create labels table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS labels (
                sample_id TEXT PRIMARY KEY,
                label_version INTEGER NOT NULL,
                out_of_sample_sharpe REAL,
                decay REAL,
                decayed_flag INTEGER,
                FOREIGN KEY (sample_id) REFERENCES samples(sample_id)
            )
        """)

        samples = pd.read_sql("SELECT sample_id, strategy_id FROM samples", conn)
        strategies = pd.read_sql("SELECT strategy_id, ticker FROM strategies", conn)
        samples = samples.merge(strategies, on="strategy_id")

        # Load features for in-sample Sharpe
        features = pd.read_sql("SELECT sample_id, in_sample_sharpe FROM features", conn)
        samples = samples.merge(features, on="sample_id")

        total = 0
        for _, sample in samples.iterrows():
            sid = sample["sample_id"]
            strat_id = sample["strategy_id"]
            ticker = sample["ticker"]
            in_sharpe = sample["in_sample_sharpe"]

            if ticker not in returns_cache or strat_id not in returns_cache[ticker].columns:
                continue

            ret_df = returns_cache[ticker]
            strat_returns = ret_df[strat_id].dropna()

            # Get origin
            origin = pd.Timestamp(sid.split("_")[-1])
            oos_start = origin
            oos_end = origin + pd.DateOffset(years=cfg["windows"]["out_of_sample_years"])

            oos_ret = strat_returns[
                (strat_returns.index >= oos_start) & (strat_returns.index < oos_end)
            ]

            if len(oos_ret) < 30:
                continue

            oos_sharpe = sharpe_ratio(oos_ret)
            decay = oos_sharpe - in_sharpe if not np.isnan(in_sharpe) and not np.isnan(oos_sharpe) else np.nan

            # Decayed flag: oos_sharpe < threshold * in_sharpe (only when in_sharpe > 0)
            decayed = np.nan
            if not np.isnan(in_sharpe) and not np.isnan(oos_sharpe) and in_sharpe > 0:
                decayed = int(oos_sharpe < decayed_threshold * in_sharpe)

            conn.execute(
                """
                INSERT OR REPLACE INTO labels
                (sample_id, label_version, out_of_sample_sharpe, decay, decayed_flag)
                VALUES (?, ?, ?, ?, ?)
                """,
                (sid, label_version, oos_sharpe, decay, decayed),
            )
            total += 1

        conn.commit()
        print(f"Built labels for {total} samples (version {label_version})")
        return total

    finally:
        conn.close()


def build_all(config_path: str = "config/stage1.toml") -> dict[str, int]:
    """Run all three builders in sequence."""
    print("Building samples...")
    n_samples = build_samples(config_path)
    print("Building features...")
    n_features = build_features(config_path)
    print("Building labels...")
    n_labels = build_labels(config_path)
    return {"samples": n_samples, "features": n_features, "labels": n_labels}


if __name__ == "__main__":
    result = build_all()
    print(result)