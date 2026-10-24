"""Walk-forward split builder for Stage 1.

Creates time-ordered folds with purge gap, grouped by origin date.
"""

from __future__ import annotations

import sqlite3
from typing import Any

import pandas as pd

from src.config import load_stage1_config


def get_fold_boundaries(config: dict[str, Any]) -> list[dict[str, Any]]:
    """Compute fold boundaries from config.

    Returns list of dicts with: fold, train_start, train_end, gap_start, gap_end, test_start, test_end
    All dates as pd.Timestamp.
    """
    start = pd.Timestamp(config["data"]["start_date"])
    end = pd.Timestamp(config["data"]["end_date"])

    in_sample_years = config["windows"]["in_sample_years"]
    out_of_sample_years = config["windows"]["out_of_sample_years"]
    purge_gap_years = config["windows"]["purge_gap_years"]
    n_folds = config["splits"]["n_folds"]
    test_block_years = config["splits"]["test_block_years"]

    # First origin with full in-sample window
    first_origin = start + pd.DateOffset(years=in_sample_years)
    # Last origin with full out-of-sample window
    last_origin = end - pd.DateOffset(years=out_of_sample_years)

    # Total origin days span
    total_origin_days = (last_origin - first_origin).days

    folds = []
    for fold in range(1, n_folds + 1):
        # Train origins: expanding from first to fold-specific cutoff
        # Fold 1: train on first ~6 years of origins
        # Fold 2: train on first ~8 years
        # Fold 3: train on first ~10 years
        # Fold 4: train on first ~12 years
        train_frac = (fold + 1) / (n_folds + 1)  # 2/5, 3/5, 4/5, 5/5
        train_end_origin = first_origin + pd.Timedelta(days=total_origin_days * train_frac)

        # Gap: one year after train_end_origin
        gap_start = train_end_origin
        gap_end = gap_start + pd.DateOffset(years=purge_gap_years)

        # Test block: 2 years starting after gap
        test_start = gap_end
        test_end = test_start + pd.DateOffset(years=test_block_years)

        folds.append({
            "fold": fold,
            "train_origin_start": first_origin,
            "train_origin_end": train_end_origin,
            "gap_start": gap_start,
            "gap_end": gap_end,
            "test_origin_start": test_start,
            "test_origin_end": test_end,
        })

    return folds


def build_splits(config_path: str = "config/stage1.toml") -> int:
    """Build splits table with walk-forward folds and purge gap.

    Each sample gets assigned to a fold with role: 'train' or 'test'.
    Samples in purge gap are excluded.

    Args:
        config_path: Path to stage1.toml.

    Returns:
        Number of split assignments created.
    """
    cfg = load_stage1_config(config_path)
    db_path = cfg["paths"]["db_path"]
    split_id = cfg["versioning"]["split_id"]

    folds = get_fold_boundaries(cfg)

    conn = sqlite3.connect(db_path)
    try:
        # Create splits table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS splits (
                split_id TEXT NOT NULL,
                fold INTEGER NOT NULL,
                sample_id TEXT NOT NULL,
                role TEXT NOT NULL CHECK (role IN ('train', 'test')),
                purge_gap_years REAL NOT NULL,
                PRIMARY KEY (split_id, fold, sample_id),
                FOREIGN KEY (sample_id) REFERENCES samples(sample_id)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_splits_split_fold ON splits (split_id, fold)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_splits_sample ON splits (sample_id)")

        # Load samples with origin dates
        samples = pd.read_sql("SELECT sample_id, origin_date FROM samples", conn)
        samples["origin_date"] = pd.to_datetime(samples["origin_date"])

        total = 0
        for fold_info in folds:
            fold = fold_info["fold"]
            train_start = fold_info["train_origin_start"]
            train_end = fold_info["train_origin_end"]
            gap_start = fold_info["gap_start"]
            gap_end = fold_info["gap_end"]
            test_start = fold_info["test_origin_start"]
            test_end = fold_info["test_origin_end"]

            # Assign roles
            # Train: origin_date in [train_start, train_end)
            train_mask = (samples["origin_date"] >= train_start) & (samples["origin_date"] < train_end)
            # Gap: origin_date in [gap_start, gap_end) - EXCLUDED
            gap_mask = (samples["origin_date"] >= gap_start) & (samples["origin_date"] < gap_end)
            # Test: origin_date in [test_start, test_end)
            test_mask = (samples["origin_date"] >= test_start) & (samples["origin_date"] < test_end)

            # Insert train
            train_samples = samples[train_mask]["sample_id"]
            for sid in train_samples:
                conn.execute(
                    "INSERT OR REPLACE INTO splits (split_id, fold, sample_id, role, purge_gap_years) VALUES (?, ?, ?, ?, ?)",
                    (split_id, fold, sid, "train", cfg["windows"]["purge_gap_years"]),
                )
                total += 1

            # Insert test
            test_samples = samples[test_mask]["sample_id"]
            for sid in test_samples:
                conn.execute(
                    "INSERT OR REPLACE INTO splits (split_id, fold, sample_id, role, purge_gap_years) VALUES (?, ?, ?, ?, ?)",
                    (split_id, fold, sid, "test", cfg["windows"]["purge_gap_years"]),
                )
                total += 1

            # Log gap exclusion
            gap_count = gap_mask.sum()
            print(f"  Fold {fold}: train={train_mask.sum()}, gap={gap_count} (excluded), test={test_mask.sum()}")

        conn.commit()
        print(f"Built {total} split assignments across {len(folds)} folds (split_id: {split_id})")
        return total

    finally:
        conn.close()


def verify_splits(config_path: str = "config/stage1.toml") -> bool:
    """Verify split integrity: no leakage, no overlap."""
    cfg = load_stage1_config(config_path)
    db_path = cfg["paths"]["db_path"]
    split_id = cfg["versioning"]["split_id"]

    conn = sqlite3.connect(db_path)
    try:
        # Check: no sample in both train and test for same fold
        dup = pd.read_sql(f"""
            SELECT sample_id, fold, COUNT(*) as cnt
            FROM splits
            WHERE split_id = '{split_id}'
            GROUP BY sample_id, fold
            HAVING cnt > 1
        """, conn)
        if len(dup) > 0:
            print(f"ERROR: {len(dup)} samples appear multiple times in same fold")
            return False

        # Check: train origins < gap < test origins
        for fold in range(1, cfg["splits"]["n_folds"] + 1):
            train_max = pd.read_sql(f"""
                SELECT MAX(s.origin_date) as max_date
                FROM splits sp
                JOIN samples s ON sp.sample_id = s.sample_id
                WHERE sp.split_id = '{split_id}' AND sp.fold = {fold} AND sp.role = 'train'
            """, conn)["max_date"].iloc[0]

            gap_min = pd.read_sql(f"""
                SELECT MIN(s.origin_date) as min_date
                FROM splits sp
                JOIN samples s ON sp.sample_id = s.sample_id
                WHERE sp.split_id = '{split_id}' AND sp.fold = {fold} AND sp.role = 'test'
            """, conn)["min_date"].iloc[0]

            if pd.notna(train_max) and pd.notna(gap_min):
                if train_max >= gap_min:
                    print(f"ERROR: Fold {fold} train_max ({train_max}) >= test_min ({gap_min})")
                    return False

        print("Split verification passed: no leakage, proper time ordering")
        return True

    finally:
        conn.close()


if __name__ == "__main__":
    build_splits()
    verify_splits()