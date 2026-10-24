"""Price ingestion module for Stage 1.

Fetches daily OHLCV data for the configured universe and stores in SQLite.
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import List

import pandas as pd
import yfinance as yf

from src.config import load_stage1_config


def fetch_prices(tickers: List[str], start: str, end: str, max_retries: int = 3) -> pd.DataFrame:
    """Fetch daily OHLCV for tickers from Yahoo Finance with retry logic.

    Args:
        tickers: List of ticker symbols.
        start: Start date (YYYY-MM-DD).
        end: End date (YYYY-MM-DD).
        max_retries: Maximum number of retry attempts on failure.

    Returns:
        DataFrame with columns: date, ticker, open, high, low, close, volume.
    """
    last_error = None

    for attempt in range(max_retries):
        try:
            raw = yf.download(
                tickers,
                start=start,
                end=end,
                auto_adjust=True,
                progress=False,
                threads=True,
                timeout=30,
            )

            # If all downloads failed, raw will be empty or have unexpected structure
            if raw.empty:
                raise ValueError("yfinance returned empty DataFrame")

            # yf.download with multiple tickers returns wide format:
            # columns = MultiIndex[(OHLCV, ticker)], e.g. ('Close', 'AAPL'), ('Volume', 'AAPL')
            # Stack the ticker level (level=1) from columns to rows → long format
            df = raw.stack(level=1, future_stack=True).reset_index()
            df.columns = ["date", "ticker", "open", "high", "low", "close", "volume"]

            # Drop rows where ALL OHLCV are NaN (no data for that ticker-date, e.g. delisted)
            df = df.dropna(subset=["open", "high", "low", "close", "volume"], how="all")

            # Ensure chronological order per ticker for downstream consistency
            df = df.sort_values(["ticker", "date"]).reset_index(drop=True)

            return df

        except Exception as e:
            last_error = e
            if attempt < max_retries - 1:
                wait = 2 ** attempt  # exponential backoff: 1s, 2s, 4s
                print(f"Fetch attempt {attempt + 1} failed: {e}. Retrying in {wait}s...")
                time.sleep(wait)
            else:
                print(f"All {max_retries} fetch attempts failed.")

    raise RuntimeError(f"Failed to fetch prices after {max_retries} attempts: {last_error}")


def init_db(db_path: str) -> sqlite3.Connection:
    """Initialize SQLite database with prices table.

    Args:
        db_path: Path to SQLite database file.

    Returns:
        Open sqlite3 connection.
    """
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)

    # Enable WAL mode for better concurrent read performance
    conn.execute("PRAGMA journal_mode=WAL;")

    # Create prices table with composite PK on (date, ticker)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS prices (
            date TEXT NOT NULL,
            ticker TEXT NOT NULL,
            open REAL,
            high REAL,
            low REAL,
            close REAL,
            volume REAL,
            PRIMARY KEY (date, ticker)
        )
    """)

    # Index for fast lookups by ticker then date (common query pattern)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_prices_ticker_date
        ON prices (ticker, date)
    """)

    return conn


def upsert_prices(conn: sqlite3.Connection, df: pd.DataFrame) -> int:
    """Insert or update price rows in the database.

    Args:
        conn: Open sqlite3 connection.
        df: DataFrame from fetch_prices().

    Returns:
        Number of rows inserted/updated.
    """
    # Convert DataFrame to list of tuples with native Python types
    # sqlite3 doesn't accept numpy/pandas types directly
    df_clean = df[["date", "ticker", "open", "high", "low", "close", "volume"]].copy()

    # Convert date to string (ISO format)
    df_clean["date"] = df_clean["date"].dt.strftime("%Y-%m-%d")

    # Convert numeric columns to native Python float/int
    for col in ["open", "high", "low", "close", "volume"]:
        df_clean[col] = df_clean[col].astype(object).where(df_clean[col].notna(), None)

    rows = df_clean.values.tolist()

    # Batched INSERT OR REPLACE - handles both insert and update on PK conflict
    batch_size = 1000
    total = 0

    for i in range(0, len(rows), batch_size):
        batch = rows[i : i + batch_size]
        conn.executemany(
            """
            INSERT OR REPLACE INTO prices (date, ticker, open, high, low, close, volume)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            batch,
        )
        total += len(batch)

    conn.commit()
    return total


def ingest_prices(config_path: str = "config/stage1.toml") -> int:
    """Main entry point: fetch and store prices for the configured universe.

    Args:
        config_path: Path to stage1.toml.

    Returns:
        Total rows inserted/updated.
    """
    cfg = load_stage1_config(config_path)

    tickers = cfg["data"]["universe"]
    start = cfg["data"]["start_date"]
    end = cfg["data"]["end_date"]
    db_path = cfg["paths"]["db_path"]
    cache_dir = cfg["data"]["cache_dir"]

    # Ensure directories exist
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    Path(cache_dir).mkdir(parents=True, exist_ok=True)

    # 1. Fetch prices (uses yfinance)
    print(f"Fetching prices for {len(tickers)} tickers from {start} to {end}...")
    df = fetch_prices(tickers, start, end)
    print(f"Fetched {len(df)} price rows")

    # 2. Cache raw pull with pull date for reproducibility
    pull_date = pd.Timestamp.now().strftime("%Y%m%d")
    cache_file = Path(cache_dir) / f"prices_{pull_date}.parquet"
    df.to_parquet(cache_file, index=False)
    print(f"Cached raw pull to {cache_file}")

    # 3. Initialize DB and upsert
    conn = init_db(db_path)
    try:
        count = upsert_prices(conn, df)
        print(f"Upserted {count} rows into {db_path}")
    finally:
        conn.close()

    # 4. Gap check: verify each ticker has sufficient data
    min_days = cfg["windows"]["min_in_market_days"]
    ticker_counts = df.groupby("ticker").size()
    missing = ticker_counts[ticker_counts < min_days]
    if not missing.empty:
        print(f"WARNING: {len(missing)} tickers below min_in_market_days ({min_days}):")
        for ticker, cnt in missing.items():
            print(f"  {ticker}: {cnt} days")
    else:
        print(f"All {len(tickers)} tickers have >= {min_days} days of data")

    return count


if __name__ == "__main__":
    # CLI entry point: python -m src.ingest.prices
    count = ingest_prices()
    print(f"Ingested {count} price rows")