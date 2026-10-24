"""Price ingestion module for Stage 1.

Fetches daily OHLCV data for the configured universe and stores in SQLite.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import List

import pandas as pd
import yfinance as yf

from src.config import load_stage1_config


def fetch_prices(tickers: List[str], start: str, end: str) -> pd.DataFrame:
    """Fetch daily OHLCV for tickers from Yahoo Finance.

    Args:
        tickers: List of ticker symbols.
        start: Start date (YYYY-MM-DD).
        end: End date (YYYY-MM-DD).

    Returns:
        DataFrame with columns: date, ticker, open, high, low, close, volume.
    """
    # TODO(human): Implement price fetching using yfinance.
    # - Use yf.download() with the ticker list, start, end.
    # - Handle the multi-index columns returned by yfinance.
    # - Stack/reshape to long format: one row per (date, ticker).
    # - Ensure columns are: date, ticker, open, high, low, close, volume.
    # - Drop rows where all OHLCV are NaN (delisted / no data).
    # - Return DataFrame sorted by (ticker, date).
    raise NotImplementedError("TODO(human): implement fetch_prices")


def init_db(db_path: str) -> sqlite3.Connection:
    """Initialize SQLite database with prices table.

    Args:
        db_path: Path to SQLite database file.

    Returns:
        Open sqlite3 connection.
    """
    # TODO(human): Create the prices table schema.
    # Table: prices
    # Columns:
    #   - date (TEXT, NOT NULL)
    #   - ticker (TEXT, NOT NULL)
    #   - open (REAL)
    #   - high (REAL)
    #   - low (REAL)
    #   - close (REAL)
    #   - volume (REAL)
    #   - PRIMARY KEY (date, ticker)
    # Also create index on (ticker, date) for fast lookups.
    # Enable WAL mode for better concurrent reads.
    raise NotImplementedError("TODO(human): implement init_db")


def upsert_prices(conn: sqlite3.Connection, df: pd.DataFrame) -> int:
    """Insert or update price rows in the database.

    Args:
        conn: Open sqlite3 connection.
        df: DataFrame from fetch_prices().

    Returns:
        Number of rows inserted/updated.
    """
    # TODO(human): Implement upsert logic.
    # - Use INSERT OR REPLACE INTO prices (...) VALUES (...)
    # - Execute in batches (e.g., 1000 rows) for memory efficiency.
    # - Commit after all batches.
    # - Return total row count affected.
    raise NotImplementedError("TODO(human): implement upsert_prices")


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

    # Ensure parent directory exists
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    # TODO(human): Wire the pieces together:
    # 1. Call fetch_prices(tickers, start, end)
    # 2. Call init_db(db_path)
    # 3. Call upsert_prices(conn, df)
    # 4. Close connection, return row count
    # 5. Log progress (print or use logging module)
    raise NotImplementedError("TODO(human): implement ingest_prices")


if __name__ == "__main__":
    # CLI entry point: python -m src.ingest.prices
    count = ingest_prices()
    print(f"Ingested {count} price rows")